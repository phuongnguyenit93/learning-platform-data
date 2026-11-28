# Trust boundary

Trong **kiến trúc an toàn**, **trust boundary** (ranh giới tin cậy) là điểm hoặc vùng phân cách nơi các thành phần, danh tính, dữ liệu hay quyết định bảo mật có **mức độ tin cậy, quyền kiểm soát hoặc giả định an toàn khác nhau**. Khi một request, dữ liệu, thông điệp hay danh tính đi qua ranh giới này, hệ thống phải xác định điều gì cần được xác minh, kiểm tra, giới hạn, ghi nhận và bảo vệ.

Ví dụ, nền tảng học trực tuyến nhận request từ trình duyệt học viên qua Internet, chuyển qua reverse proxy, Java API, database và report worker. Browser, Internet, ingress, application, database và worker không có cùng quyền hoặc cùng mức kiểm soát. Một request đã qua HTTPS và đăng nhập thành công vẫn có thể chứa learnerId hoặc classId do client tự sửa. Backend cần kiểm tra quyền trên đối tượng cụ thể trước khi đọc hoặc xuất dữ liệu học viên.

Trust boundary không chỉ là firewall hay đường nối giữa hai mạng. Nó có thể nằm giữa **hai tenant trong cùng một database**, giữa user và service, giữa process và kernel, giữa control plane và workload, hoặc giữa tổ chức và vendor. Kiến trúc an toàn cần nhận diện những ranh giới này để đưa ra security requirements, chọn controls, kiểm thử các đường vượt ranh giới và thu thập bằng chứng.

Bài học thuộc module **SECURITY_SECURITY_ASSURANCE**: xây dựng cách đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục phát hiện và duy trì assurance trong phát triển/vận hành. Vì vậy, trọng tâm là **xác định ranh giới → mô hình hóa luồng và giả định → phân tích threat/risk → thiết kế controls → test/evidence → đánh giá hiệu quả → remediation và reassessment**.

**Nguyên tắc cốt lõi:** không có thành phần nào tự động đáng tin chỉ vì nó nằm “bên trong mạng”, chạy trong cloud của tổ chức, dùng cùng database hoặc đã vượt qua một bước xác thực trước đó. Mỗi ranh giới cần có **điều kiện tin cậy rõ ràng, điểm thực thi, chủ sở hữu và bằng chứng**.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích trust boundary, trust zone, security domain, trust assumption và điểm chuyển tiếp dữ liệu/quyền.
2. Phân biệt trust boundary với network perimeter, authentication boundary, authorization boundary và data classification boundary.
3. Nhận diện ranh giới giữa Internet, browser, API, service, database, queue, tenant, cloud account, control plane, vendor và môi trường build/deploy.
4. Vẽ data flow diagram (DFD), xác định actor, process, data store, data flow, entry/exit points và boundary crossings.
5. Dùng STRIDE cùng privacy/risk prompts để tìm spoofing, tampering, repudiation, information disclosure, denial of service và elevation of privilege.
6. Chuyển giả định kiến trúc thành security requirements có thể kiểm thử.
7. Thiết kế controls như segmentation, identity verification, authorization, schema validation, encryption, rate limiting, isolation, logging và fail-safe behavior.
8. Đánh giá Zero Trust, defense in depth, API gateway, service mesh, queue, cloud shared responsibility theo ranh giới thực tế.
9. Xây test matrix gồm positive/negative tests và kiểm tra đường bypass.
10. Tạo Claim–Argument–Evidence, phân biệt design, implementation và operating effectiveness.
11. Quản lý findings, exceptions, residual risks và trigger đánh giá lại khi kiến trúc thay đổi.

## 2. Trust boundary là gì?

### 2.1. Ranh giới giữa các giả định tin cậy

Một trust boundary xuất hiện khi hệ thống chuyển từ một vùng có tập **assumptions, identity, authority, policy hoặc khả năng kiểm soát** sang vùng khác. Ở điểm đó, kiến trúc phải trả lời:

- Ai hoặc thành phần nào đang gửi dữ liệu?
- Danh tính được chứng minh bằng cách nào?
- Dữ liệu có thể bị sửa trước khi tới đây không?
- Người gửi có quyền thực hiện hành động này trên đúng đối tượng không?
- Bên nhận có thể tin vào nguồn, cấu trúc và trạng thái của dữ liệu tới mức nào?
- Có thể lặp, trì hoãn, giả mạo, phát lại hoặc làm cạn tài nguyên không?
- Nếu kiểm tra thất bại, hệ thống từ chối, cách ly hay tiếp tục?
- Bằng chứng nào cho thấy control thực sự hoạt động?

Một request qua TLS có thể bảo vệ kênh và xác thực server; nó **không chứng minh người gửi có quyền xem hồ sơ của học viên khác**. Một message được ký bởi service hợp lệ có thể chứng minh nguồn trong mô hình tin cậy; nó **không chứng minh payload không cũ, không bị replay hoặc còn được phép xử lý**.

### 2.2. Ví dụ đơn giản

~~~mermaid
flowchart LR
    U["Browser / Mobile<br/>Untrusted client"] -->|"HTTPS request"| E["Internet-facing ingress"]
    E -->|"Validated request"| A["Java API"]
    A -->|"DB query"| D[("Academic database")]
    A -->|"Authorized job"| Q[["Export queue"]]
    Q --> W["Report worker"]
    W --> O[("Private object storage")]
~~~

Các vùng không có cùng mức tin cậy:

- Client chạy trên thiết bị ngoài quyền quản trị của backend.
- Ingress tiếp nhận lưu lượng từ Internet và áp dụng một số controls.
- API thực thi authentication, authorization và business rules.
- Database lưu dữ liệu có mức nhạy cảm cao.
- Queue chứa công việc được yêu cầu bởi actor/service.
- Worker có thể truy cập database và storage trong phạm vi được cấp.

Một trust boundary tồn tại **giữa client và ingress**, nhưng cũng có ranh giới giữa ingress và API, API và database, API và queue, queue và worker, worker và storage. Cùng một private network không làm các ranh giới này biến mất.

### 2.3. Ranh giới không phải đường kẻ vật lý duy nhất

Một kiến trúc có thể có nhiều loại ranh giới chồng lấn:

- Ranh giới **network**: subnet, VPC, firewall, Internet.
- Ranh giới **identity**: user, service account, workload identity.
- Ranh giới **authorization**: vai trò, tenant, object, action, purpose.
- Ranh giới **data**: public/internal/confidential/restricted, dữ liệu cá nhân, secret.
- Ranh giới **execution**: process, container, VM, kernel, sandbox.
- Ranh giới **administrative**: account, project, subscription, control plane.
- Ranh giới **supply chain**: source code, CI runner, package registry, artifact, deployment.
- Ranh giới **organizational**: tổ chức, vendor, subprocessor, khách hàng.
- Ranh giới **physical**: thiết bị, phòng máy, console và người vận hành.

Một ranh giới cần được mô tả theo **điều gì thay đổi khi vượt qua nó**. Nếu chỉ vẽ đường mạng mà không ghi identity, policy và data, mô hình có thể bỏ sót rủi ro quan trọng.

## 3. Phân biệt các khái niệm gần nhau

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Trust boundary** | Nơi giả định tin cậy hoặc quyền kiểm soát thay đổi? | Browser → API; tenant A → tenant B |
| **Trust zone** | Nhóm thành phần chia sẻ một số giả định/policy? | Public ingress zone, data zone |
| **Network perimeter** | Lưu lượng đi vào/ra qua đâu? | Firewall, VPC boundary |
| **Authentication boundary** | Danh tính được xác minh ở đâu? | OAuth/OIDC login, mTLS handshake |
| **Authorization boundary** | Quyền hành động trên đối tượng được quyết định ở đâu? | API policy enforcement point |
| **Data classification boundary** | Dữ liệu chuyển sang mức bảo vệ nào? | Internal event → Restricted learner record |
| **Administrative boundary** | Ai có quyền quản trị resource/account? | Cloud organization → project |
| **Process boundary** | Quyền và memory của process tách biệt thế nào? | JVM service → database driver |
| **Compliance scope** | Hệ thống/hoạt động nào thuộc phạm vi đánh giá? | Production data processing scope |

Các khái niệm này có thể trùng tại một điểm nhưng không đồng nhất. Ví dụ firewall tạo network boundary, nhưng nếu hai service ở cùng subnet vẫn cần authorization boundary. Ngược lại, hai tenant có thể dùng chung một IP/database cluster nhưng phải có data isolation boundary.

### 3.1. Trust boundary và security perimeter

Mô hình perimeter truyền thống thường giả định bên trong mạng tổ chức đáng tin hơn bên ngoài. Nhưng cloud, remote work, SaaS, service mesh, mobile devices và workloads động làm ranh giới thay đổi liên tục. Một attacker có thể đã ở trong network hoặc chiếm một service account.

Trust boundary giúp nhìn **mỗi lần truy cập và mỗi chuyển giao** như một điểm cần xác minh theo policy, không dựa duy nhất vào vị trí mạng. Network segmentation vẫn hữu ích; nó chỉ là một lớp control.

### 3.2. Trust không phải thuộc tính nhị phân

Không nên gắn một nhãn “trusted” cho toàn bộ thành phần rồi bỏ qua context. Có thể tin một service về khả năng phát event đã xác thực nhưng không tin mọi field trong payload; tin một identity đã được xác minh nhưng không cấp quyền admin; tin database về tính toàn vẹn storage nhưng không cho phép mọi ứng dụng đọc mọi row.

Mô hình tốt nêu rõ **tin điều gì, trong điều kiện nào, với dữ liệu/actor nào, trong bao lâu và bằng evidence nào**.

## 4. Trust zones và trust levels

### 4.1. Trust zone

Một **trust zone** là nhóm tài sản/thành phần có cùng policy và assumptions tương đối giống nhau. Ví dụ:

- **External zone:** browser, mobile app, Internet client.
- **Edge/DMZ zone:** CDN, WAF, reverse proxy, API gateway.
- **Application zone:** Java APIs, workers, internal services.
- **Data zone:** database, warehouse, object storage.
- **Management zone:** cloud console, deployment controller, secrets, monitoring.
- **Build zone:** source control, CI runner, package registry, artifact signer.
- **Third-party zone:** vendor SaaS, payment, analytics, email provider.

Tên zone chỉ là quy ước. Mỗi tổ chức cần phân vùng theo **threat model và architecture thực tế**, không nhất thiết phải có đúng những tên trên.

### 4.2. Trust level và privilege

Một số hệ thống phân loại mức tin cậy theo tiêu chí nội bộ, ví dụ:

| Level minh họa | Mô tả | Điều kiện |
|---|---|---|
| **Untrusted** | Dữ liệu/actor chưa được xác minh | Client input, Internet traffic |
| **Authenticated** | Danh tính được xác minh trong phạm vi | Token/certificate hợp lệ |
| **Authorized for scope** | Được phép thực hiện action cụ thể trên resource | Policy decision và object/tenant check |
| **Privileged** | Có quyền vận hành hoặc thay đổi cấu hình quan trọng | MFA, JIT, approval, audit |
| **Trusted infrastructure** | Thành phần vận hành trong baseline đã kiểm chứng | Hardening, identity, isolation, monitoring |

Đây chỉ là **mô hình khái niệm**. Một token authenticated không được tự nâng thành authorized. Một platform admin có quyền hạ tầng cũng không mặc nhiên có quyền sử dụng dữ liệu nghiệp vụ cho mục đích riêng.

### 4.3. Không tạo trusted zone quá rộng

Nếu tất cả service chạy trong một VPC đều có thể gọi mọi API và truy cập database, một workload bị xâm nhập có thể di chuyển ngang (lateral movement). Zone quá rộng làm giảm giá trị segmentation và tăng blast radius.

Nên phân vùng theo **chức năng, độ nhạy dữ liệu, identity, criticality và quyền cần thiết**. Một worker chỉ cần đọc dataset đã phê duyệt không nên có quyền quản trị database hoặc truy cập toàn bộ object storage.

## 5. Các loại trust boundary trong hệ thống hiện đại

### 5.1. Client–server boundary

Client nằm ngoài quyền kiểm soát của backend. Mọi dữ liệu từ client cần được xem là **input không đáng tin**, ngay cả khi UI đã validate.

Ví dụ: client gửi role=ADMIN, tenantId, learnerId hoặc giá tiền. Backend không lấy những field này làm sự thật nếu chúng không được xác minh từ identity/policy source đáng tin.

### 5.2. Service–service boundary

Một service gọi service khác bằng token, mTLS hoặc workload identity. Cần xác minh peer identity, token audience/scope, replay/duplicate, quyền action/resource/tenant, quota, timeout và schema validation. Service nhận vẫn phải thực thi authorization của nó.

### 5.3. Tenant boundary

Nhiều khách hàng/lớp học dùng chung ứng dụng hoặc database. Tenant boundary là ranh giới logic rất quan trọng dù các bản ghi nằm trong cùng bảng.

Cần kiểm tra mọi query, cache key, object storage path, search index, event, export và background job có giữ tenant context hay không. Một query lọc tenant ở controller nhưng repository khác không lọc là một đường bypass.

### 5.4. Data sensitivity boundary

Một event analytics nội bộ có thể được phân loại thấp hơn hồ sơ học viên, nhưng khi gắn learnerId hoặc kết hợp với dữ liệu khác, mức nhạy cảm có thể tăng. Data flow crossing phải áp dụng classification, minimization, encryption, authorization và retention phù hợp.

### 5.5. Cloud account/project boundary

Hai cloud accounts/projects có thể khác owner, IAM, network, logging và encryption keys. VPC peering hoặc shared service không tự tạo trust. Cần xem identity federation, resource policies, organization policies, cross-account roles và audit.

### 5.6. Control plane–data plane boundary

Control plane quản lý cấu hình, identity, secrets, scheduling và policy; data plane xử lý request/dữ liệu thật. Nếu workload bị xâm nhập có thể sửa control plane hoặc lấy credential quản trị, ranh giới đã bị phá vỡ.

Cần giới hạn ai/what có quyền thay đổi deployment, trust bundles, network policy, service identity, database grants và secrets.

### 5.7. Build–deploy–runtime boundary

Source code được review không tự bảo đảm artifact chạy production giống source. Ranh giới giữa source, build runner, dependencies, artifact registry, signer, deployment controller và runtime cần có provenance, approval, signature verification và access control.

### 5.8. Organization–vendor boundary

Một API vendor qua HTTPS chỉ bảo vệ đường truyền và xác thực endpoint theo trust model; vẫn cần kiểm tra dữ liệu nào được gửi, mục đích, subprocessor, quyền truy cập, retention và incident responsibilities.

## 6. Vẽ data flow diagram và xác định boundary crossing

### 6.1. Các thành phần DFD

Một DFD đơn giản thường có:

- **External entity:** người dùng, đối tác, hệ thống ngoài.
- **Process:** API, worker, service, transformation, decision engine.
- **Data store:** database, queue, object storage, cache, log, warehouse.
- **Data flow:** request, response, event, file, replication, backup.
- **Trust boundary:** nơi trust assumptions/policy thay đổi.

DFD nên ghi cả chiều đi và về, giao thức, identity, dữ liệu nhạy cảm, điểm thực thi và người chịu trách nhiệm.

### 6.2. DFD mẫu của nền tảng học trực tuyến

~~~mermaid
flowchart LR
    subgraph Z1["External / Untrusted"]
        U["Learner browser"]
        P["Partner analytics"]
    end
    subgraph Z2["Edge zone"]
        WAF["CDN / WAF"]
        GW["API gateway"]
    end
    subgraph Z3["Application zone"]
        API["Java Learning API"]
        JOB["Export worker"]
    end
    subgraph Z4["Data zone"]
        DB[("Academic DB")]
        Q[["Job queue"]]
        OBJ[("Private object storage")]
    end
    U -->|"HTTPS, user token"| WAF
    WAF -->|"Validated edge request"| GW
    GW -->|"Service identity"| API
    API -->|"Scoped query"| DB
    API -->|"Authorized job message"| Q
    Q -->|"Queue event"| JOB
    JOB -->|"Scoped read/write"| DB
    JOB -->|"Private export object"| OBJ
    API -->|"Approved data fields only"| P
~~~

Trong sơ đồ, mỗi đường nối qua zone là một ứng viên trust boundary. Nhưng boundary cũng có thể nằm **bên trong zone**, chẳng hạn giữa hai tenant hoặc giữa service account và privileged API.

### 6.3. Ghi boundary register

| Boundary ID | From → To | Điều thay đổi | Data/identity crossing | Control/owner |
|---|---|---|---|---|
| TB-01 | Browser → Gateway | Client-controlled → server edge | Request, token, headers | WAF/API gateway, Edge owner |
| TB-02 | Gateway → Java API | Edge identity → service identity | Authenticated request context | mTLS/token validation, Platform |
| TB-03 | API → DB | App principal → DB role | SQL/data queries | DB grants, query scoping, App/Data |
| TB-04 | API → Queue | Synchronous request → asynchronous job | Job payload, actor context | Validated message, Queue owner |
| TB-05 | Queue → Worker | Message source → execution identity | Event/job reference | Producer auth, schema, replay controls |
| TB-06 | Worker → Storage | Workload → file resource | Export file, tenant path | IAM, bucket policy, encryption |
| TB-07 | App → Vendor | Organization → third party | Selected data fields | Contract, API scope, Vendor owner |
| TB-08 | Tenant A → B | Separate data domains | IDs, queries, cache/index | Tenant isolation, App owner |

Boundary register giúp nối DFD với **risk register, control catalog, test cases và evidence repository**. Nếu một boundary không có owner hoặc không có control/test, đó là điểm cần điều tra.

### 6.4. Không bỏ sót luồng phụ

DFD thường bỏ qua retry/dead-letter queues, cache/search index, logs/tracing/crash dumps, batch jobs, scheduled exports, migration, backups/snapshots/replicas, admin/debug endpoints, webhooks/vendor callbacks, CI/CD secrets, control plane APIs, failover và break-glass access.

Đánh giá assurance phải xác minh **luồng thật và bản sao**, không chỉ đường happy path trong sơ đồ.

## 7. Cách nhận diện trust boundary có hệ thống

Một quy trình discovery có thể thực hiện như sau:

1. Xác định hệ thống, mục tiêu bảo mật, data classification và scope đánh giá.
2. Liệt kê actors, human users, services, workloads, vendors, admins và automation.
3. Liệt kê assets, data stores, credentials, secrets, APIs, queues và control planes.
4. Vẽ luồng dữ liệu/identity/control giữa chúng.
5. Đánh dấu mọi nơi có thay đổi network, owner, privilege, identity, data sensitivity hoặc administrative authority.
6. Ghi assumptions tại từng boundary: ai xác minh, ai tin, điều kiện nào, TTL/scope nào.
7. Tìm các đường phụ/bypass, trust transitivity và shared credentials.
8. Xác định owner và controls hiện hữu.
9. Chuyển assumptions chưa được chứng minh thành risk/evidence questions.
10. Xác minh bằng runtime discovery, config review, tests và stakeholder interviews.

### 7.1. Câu hỏi discovery hữu ích

- Thành phần nào **được phép gửi** dữ liệu tới thành phần này?
- Hệ thống nhận dựa vào token, certificate, network location, API key hay header?
- Ai phát hành và thu hồi danh tính đó?
- Client có thể tự sửa tenant/user/role/object ID không?
- Dữ liệu được parse/deserialize ở đâu? Có schema validation?
- Có shared service account hoặc secret dùng nhiều workload không?
- Một actor có thể bỏ qua gateway bằng cách gọi service trực tiếp không?
- Queue message có thể replay hoặc giả mạo không?
- Khi một service bị chiếm, attacker có thể truy cập gì tiếp theo?
- Ai có thể sửa trust store, firewall, IAM policy hoặc deployment config?
- Các bản sao dữ liệu nào đi qua ranh giới này?
- Control nào đang được giả định nhưng chưa có evidence?

## 8. Threat modeling tại trust boundaries

### 8.1. STRIDE

STRIDE là một cách phân loại threat thường dùng:

| Threat | Ý nghĩa | Ví dụ ở trust boundary |
|---|---|---|
| **Spoofing** | Giả mạo danh tính | Service giả mạo report-worker hoặc token bị đánh cắp |
| **Tampering** | Thay đổi dữ liệu/thông điệp | Sửa tenantId trong job payload hoặc thay artifact |
| **Repudiation** | Phủ nhận hành động do thiếu bằng chứng | Không truy vết được ai yêu cầu export |
| **Information disclosure** | Tiết lộ dữ liệu | API trả điểm lớp khác hoặc log lộ token |
| **Denial of service** | Làm dịch vụ/tài nguyên không sẵn sàng | Queue flood, request quá lớn |
| **Elevation of privilege** | Tăng quyền vượt dự kiến | Worker có quyền DB admin hoặc user thành tenant admin |

STRIDE là **lăng kính gợi ý**, không phải danh sách đầy đủ mọi risk. Cần xem thêm privacy harm, safety, misuse, business logic, supply chain, insider threat và failure mode.

### 8.2. STRIDE theo thành phần và flow

Ví dụ với đường API → queue:

- Spoofing: attacker gửi message vào queue giả danh API.
- Tampering: sửa classId, tenantId, export fields.
- Repudiation: thiếu actor/request correlation.
- Information disclosure: payload chứa PII và consumer ngoài scope đọc được.
- DoS: message quá lớn hoặc lặp không giới hạn.
- Elevation: worker tin role trong payload do producer tự khai và chạy quyền quá rộng.

Các câu hỏi này chuyển thành **control statements và test cases**, thay vì dừng ở bảng brainstorm.

### 8.3. Attack tree và abuse cases

Một mục tiêu “xuất bảng điểm tenant khác” có thể có các nhánh:
- Thay tenantId ở API request.
- Gọi worker trực tiếp.
- Thay message payload.
- Lấy service token của worker.
- Khai thác cache key không có tenant.
- Lấy signed URL và dùng lại.
- Dùng quyền admin/break-glass.
- Tấn công build/deploy để thêm endpoint bypass.

Attack tree giúp tìm **đường thay thế** và tránh chỉ kiểm tra controller happy path.

## 9. Đánh giá trust assumptions

### 9.1. Mọi ranh giới đều có assumptions

Ví dụ: “Gateway xác minh token nên API tin request.” Assumption này cần làm rõ:

- Gateway xác minh issuer, signature, audience, expiry và claims nào?
- API có thể được gọi trực tiếp từ mạng khác không?
- API có xác minh gateway identity hoặc token signature riêng không?
- Headers do client tự gửi có bị tin như identity context không?
- Token có scope/audience chỉ dành cho service này không?
- Khi gateway bị compromise, blast radius thế nào?
- Ai thay đổi policy và trust configuration?

Assumption không có owner hoặc evidence nên được ghi như **unverified assumption**, không coi là control.

### 9.2. Trust transitivity

Nếu A tin B và B tin C, không tự động có nghĩa A nên tin mọi thứ C nói. Ví dụ API tin gateway đã xác thực user; gateway lại lấy header X-User-Id do client gửi mà không ghi đè từ token. Khi đó niềm tin của API vào gateway có thể bị lợi dụng để giả mạo user.

Cần xác định **bằng chứng được truyền qua ranh giới**, cách bảo vệ integrity và bên nhận có xác minh điều kiện cần thiết không.

### 9.3. Fail-open và fail-closed

Khi một control dependency lỗi, hệ thống có thể:
- **Fail closed:** từ chối hoặc hạn chế hành động khi không thể xác minh.
- **Fail open:** tiếp tục theo một đường cho phép khi dependency không sẵn sàng.
- **Degraded mode:** tiếp tục một tập chức năng được giới hạn, có điều kiện và monitoring.

Không có lựa chọn đúng cho mọi service. Với authorization dữ liệu nhạy cảm, fail-open có thể tạo nguy cơ disclosure; với một số health/availability functions, có thể cần degraded mode. Phải xác định **điều gì được phép tiếp tục, dữ liệu nào bị khóa, ai phê duyệt và bằng chứng test**.

## 10. Threats thường gặp tại từng loại boundary

| Boundary | Threats cần xem | Controls/test gợi ý |
|---|---|---|
| Browser → API | Input spoofing, CSRF, token theft, object tampering | Server validation, AuthN/AuthZ, CSRF policy, negative tests |
| Gateway → service | Header spoofing, direct bypass, token audience mismatch | mTLS/service identity, signed context, network policy |
| Service → DB | SQL injection, excessive DB grants, tenant leakage | Parameterized queries, least privilege, row/object scope tests |
| Service → queue | Forged/replayed messages, schema tampering, flood | Producer auth, schema, idempotency, quotas, consumer checks |
| Queue → worker | Poison message, stale actor permissions, privilege escalation | Validate payload, re-check authority, bounded worker role |
| Workload → storage | Public bucket, path traversal, cross-tenant object access | IAM/bucket policy, private access, object tests |
| Tenant A → B | IDOR/BOLA, cache/index mix-up, shared key | Tenant-scoped authz, cache isolation, cross-tenant tests |
| Control plane → workload | Deployment tampering, secret injection, policy drift | Admin MFA/JIT, signed deployment, audit, separation |
| Build → artifact → runtime | Dependency substitution, runner compromise, unverified artifact | Provenance, signatures, registry permissions, deploy verification |
| Organization → vendor | Excess data, weak recipient controls, unclear exit | Contract, minimization, token scopes, evidence and offboarding |
| Admin → production | Insider misuse, break-glass abuse | PAM, JIT, dual approval where needed, session logs |
| Logging → monitoring | Forged/missing events, secrets in logs | Source identity, integrity, health tests, data minimization |

## 11. Boundary crossing phải có policy và enforcement

Một trust boundary được vẽ ra nhưng không có **điểm thực thi (enforcement point)** chỉ là giả định trong tài liệu. Tại mỗi crossing cần xác định policy, decision maker, policy enforcement point (PEP), policy decision point (PDP) khi có, và evidence.

### 11.1. Policy Decision Point và Policy Enforcement Point

- **PDP:** nơi quyết định cho phép/từ chối dựa trên identity, attributes, resource, action và policy.
- **PEP:** nơi chặn/cho phép hành động theo quyết định.
- **Policy information source:** nguồn identity, group, tenant, resource attributes và risk signals.
- **Policy administration:** quy trình quản trị policy và thay đổi.

Ví dụ API gọi authorization service để hỏi user có quyền đọc learner record không. API hoặc data access layer là PEP; authorization service là PDP. Nếu API nhận quyết định “allow” nhưng không ràng buộc nó với **đúng learnerId, tenant, action và request context**, quyết định có thể bị tái sử dụng sai.

### 11.2. Kiểm soát ở nhiều lớp

Không dựa một gateway để bảo vệ toàn bộ hệ thống. Các lớp có thể gồm:

1. Edge validation và rate limits.
2. Service identity và transport protection.
3. Application authentication/authorization.
4. Object/tenant-level policy.
5. Database grants/row-level controls.
6. Queue producer/consumer validation.
7. Storage access policy.
8. Logging/monitoring và incident response.

Các lớp cần **nhất quán và có thể kiểm tra**, tránh tình trạng gateway chặn nhưng service direct path lại mở.

### 11.3. Không tin dữ liệu context chỉ vì header nội bộ

Header như X-User-Id, X-Tenant-Id, X-Role có thể hữu ích khi gateway truyền context, nhưng cần xác minh:

- Gateway có xóa/ghi đè header do client gửi không?
- Service có chỉ nhận request từ gateway identity được phép?
- Context có integrity protection hoặc nằm trong token đã xác minh?
- Claims có audience/issuer/scope đúng?
- API có kiểm tra quan hệ user–tenant–object ở nguồn authoritative?
- Header có bị ghi vào log hoặc forward sang vendor ngoài ý muốn?

## 12. Các nguyên tắc kiến trúc bảo vệ trust boundaries

### 12.1. Least privilege

Mỗi actor/service chỉ có quyền cần cho nhiệm vụ, trong scope và thời gian phù hợp. Worker xuất báo cáo chỉ cần đọc dataset được duyệt, tạo file trong prefix tenant tương ứng và ghi job status; không cần quyền admin toàn database hoặc bucket.

### 12.2. Complete mediation

Mọi truy cập tới resource cần được kiểm tra theo policy, không chỉ lần đầu hoặc ở UI. Kiểm tra phải bao phủ API, batch, queue, cache, download URL, admin path và retry/replay khi liên quan.

### 12.3. Defense in depth

Dùng nhiều lớp controls bổ trợ: identity, network segmentation, authorization, encryption, validation, quotas, logging, backup và response. Mỗi lớp có mục tiêu riêng; không dùng sự hiện diện của một lớp để tuyên bố lớp khác không cần.

### 12.4. Fail securely

Nếu không thể xác minh identity hoặc authorization cho dữ liệu nhạy cảm, hệ thống cần từ chối/hạn chế theo policy. Nếu cần degraded mode, phải **thiết kế trước, giới hạn rõ và test**, không phát sinh một fallback bất ngờ.

### 12.5. Minimize trust

Giảm số lượng thành phần được tin, quyền của chúng, dữ liệu được truyền và thời gian credential tồn tại. Một service càng có nhiều quyền thì sự cố của nó càng có thể lan sang tài sản khác.

### 12.6. Explicit trust establishment

Không suy ra trust từ IP, subnet, tên DNS hoặc việc chạy trong cluster. Dùng identity được quản lý, xác minh peer, ràng buộc audience/scope và authorization theo action/resource.

### 12.7. Assume breach và limit blast radius

Thiết kế giả định một credential/workload có thể bị xâm nhập. Segmentation, short-lived credentials, restricted service accounts, egress controls, quotas và audit giúp hạn chế phạm vi lan rộng và tăng khả năng phát hiện.

## 13. Zero Trust và trust boundaries

### 13.1. Zero Trust trong bối cảnh này

Zero Trust là cách tiếp cận không cấp niềm tin chỉ dựa vào vị trí mạng hoặc quyền truy cập trước đó. Quyết định truy cập dựa trên **identity, device/workload context, resource, action, policy và tín hiệu risk** theo kiến trúc của tổ chức.

Nó không có nghĩa “không tin ai” hoặc phải xác minh lại mọi thứ bằng một service trung tâm cho từng byte. Nó yêu cầu **trust được xác lập rõ và đánh giá theo ngữ cảnh**, đồng thời giảm quyền và giới hạn tác động.

### 13.2. Các thành phần thường có

- Identity provider và workload identity.
- Policy engine/PDP.
- PEP tại gateway, service, endpoint hoặc data layer.
- Device posture/context khi áp dụng.
- Telemetry, audit và threat/risk signals.
- Resource inventory và classification.
- Session/token lifecycle, revocation và re-evaluation.

### 13.3. Sai lầm khi triển khai Zero Trust

- Chỉ mua một gateway và gọi đó là Zero Trust.
- Bắt buộc mTLS nhưng không kiểm tra application authorization.
- Tin mọi request từ private subnet.
- Dùng token có audience/scope quá rộng và thời hạn dài.
- PDP outage khiến API tự cho phép tất cả.
- Không có inventory nên policy bỏ sót shadow services.
- Không test direct path/bypass.
- Không đo false deny/availability khi policy rollout.

Zero Trust cần **control objectives và evidence**, không chỉ một nhãn kiến trúc.

## 14. Segmentation và isolation

### 14.1. Network segmentation

Chia mạng theo zone và hạn chế traffic giữa chúng bằng subnet, security groups, network policies, firewalls, private endpoints và egress rules.

Segmentation cần được kiểm tra cả:
- East-west traffic giữa services.
- Ingress/egress, DNS và service discovery.
- Admin/management paths.
- Backup/replication.
- Failover và disaster recovery.
- Direct IP/port hoặc bypass gateway.

### 14.2. Identity segmentation

Tách service accounts, roles, namespaces, client certificates, API scopes và secrets. Không dùng chung một credential cho mọi workload nếu blast radius không chấp nhận được.

### 14.3. Tenant/data isolation

Tenant boundary cần được thực thi ở mọi data path: SQL, ORM, cache, queue, object storage, search, analytics, export, logs và backup. Có thể dùng tenant-scoped identifiers/policy checks, row-level security hoặc schema separation khi phù hợp, bucket/prefix policies, per-tenant keys, cache keys có tenant scope, separate indexes và negative cross-tenant tests.

Không nên coi tenantId trong JWT là đủ nếu backend không kiểm tra quan hệ với object thật.

### 14.4. Isolation không chỉ là cấu hình

Một firewall policy tồn tại không chứng minh nó được gắn vào mọi network interface; một Kubernetes NetworkPolicy không có hiệu lực nếu CNI hoặc namespace behavior không đáp ứng; một database RLS policy không bảo vệ query chạy bằng superuser. Cần kiểm tra **effective state và bypass path**.

## 15. API gateway và boundary enforcement

API gateway có thể thực hiện TLS termination, authentication, rate limiting, schema validation, routing, logging và một số authorization checks. Nhưng gateway thường **không hiểu đầy đủ business relationship** giữa user, lớp học và learner record.

### 15.1. Gateway làm tốt

- Chuẩn hóa ingress và policy edge.
- Xác minh token/certificate ở mức phù hợp.
- Giới hạn request size, rate và protocol.
- Chặn đường truy cập không cần thiết.
- Ghi request ID và telemetry.
- Chuyển tiếp context có bảo vệ.

### 15.2. Service vẫn phải bảo vệ

- Quyền trên object/tenant/business state.
- Endpoint nội bộ/batch/direct paths.
- Queue và worker.
- Idempotency, replay và workflow state.
- Data minimization/field filtering.
- Database và storage permissions.
- Authorization thay đổi theo thời gian hoặc trạng thái account.

Nếu gateway thêm header role nhưng backend tin mọi header từ mạng nội bộ, attacker có thể gọi backend trực tiếp hoặc giả header qua cấu hình sai. **Boundary enforcement phải ở nơi dữ liệu được sử dụng**, không chỉ nơi request đi vào.

## 16. Queue, event-driven architecture và asynchronous trust

Queue tạo trust boundary riêng vì **producer và consumer không nhất thiết chạy cùng thời điểm, cùng quyền hoặc cùng version**.

### 16.1. Rủi ro đặc thù

- Message bị giả mạo bởi producer không được phép.
- Payload bị sửa hoặc schema không tương thích.
- Message cũ được replay sau khi quyền actor bị thu hồi.
- Duplicate message gây lặp side effects.
- Queue bị flood hoặc poison messages.
- DLQ lưu PII/secret lâu hơn policy.
- Consumer có quyền rộng hơn nhu cầu.
- Correlation giữa request, actor, job và file bị mất.
- Producer gửi tenantId/role do client tự khai.

### 16.2. Controls

- Producer/consumer identity và queue ACL.
- Schema/version validation, size limits và content constraints.
- Không tin role/tenant/action trong payload nếu không có nguồn xác thực.
- Consumer kiểm tra authorization phù hợp tại thời điểm xử lý hoặc dùng delegated authorization artifact có scope/thời hạn rõ.
- Idempotency keys, replay protection và bounded retries.
- DLQ access/retention, payload minimization và encryption.
- Job ownership, correlation ID và audit trail.
- Worker role giới hạn; tách read/write permissions.
- Test message forged, duplicate, stale, oversized, malformed và wrong-tenant.

### 16.3. Thời điểm kiểm tra quyền

Một giảng viên có thể có quyền tạo export lúc request, nhưng quyền có thể bị thu hồi trước khi worker chạy. Kiến trúc cần quyết định khi nào kiểm tra quyền, delegated scope sống bao lâu, job có bị hủy khi quyền đổi và file đã tạo có được tải sau khi quyền bị thu hồi không. Quy tắc phải rõ, có owner và test.

## 17. Cloud shared responsibility và boundary

### 17.1. Cloud provider và khách hàng

Trong cloud, provider quản lý một số lớp hạ tầng, còn khách hàng chịu trách nhiệm với cấu hình, identity, data, workload và một số control khác tùy dịch vụ. Ranh giới cụ thể phụ thuộc **IaaS/PaaS/SaaS, managed service, contract và architecture**.

Không nên nói “đã lên cloud nên provider bảo vệ tất cả”. Cần lập responsibility matrix cho physical facilities/hardware/hypervisor, cloud control plane và tenant IAM, network/security groups, managed database, application code/API authorization, secrets/keys/certificates, backups/retention, logging/incident response và vendor integrations.

### 17.2. Cross-account và federation

Khi CI runner hoặc workload ở account A assume role trong account B, trust policy cần giới hạn principal/source account, workload identity, audience/subject conditions, actions/resources, thời hạn, session context và audit/revoke path. Không dùng wildcard principal hoặc quyền admin rộng chỉ để pipeline deploy nhanh. Test một workload tương tự nhưng **không đúng identity** phải bị từ chối.

## 18. Supply-chain và build trust boundaries

### 18.1. Source code không phải artifact runtime

~~~mermaid
flowchart LR
    DEV["Developer workstation"] --> SC["Source control"]
    SC --> CI["CI runner"]
    CI --> DEP["Dependencies / package registry"]
    CI --> BUILD["Build artifact"]
    BUILD --> SIGN["Signing service"]
    SIGN --> REG["Artifact registry"]
    REG --> CD["Deployment controller"]
    CD --> RUN["Production workload"]
~~~

Mỗi bước là một trust boundary: developer identity/source approval; source repository/CI runner; CI runner/dependency registry; build output/signer; signed artifact/registry; registry/deployment controller; deployment controller/runtime.

### 18.2. Controls/evidence

- Branch protection, review và protected environments.
- CI runner isolation, ephemeral workers và secret scoping.
- Dependency pinning, provenance, SBOM và vulnerability checks.
- Artifact digest/signature và verification trước deploy.
- Signer identity/key custody.
- Deployment approval, immutable release mapping.
- Runtime attestation hoặc drift detection khi phù hợp.
- Audit và incident response khi pipeline bị compromise.

Một artifact có signature hợp lệ **không tự chứng minh code không độc hại**; nó chỉ hỗ trợ kiểm tra nguồn ký/nội dung theo trust model. Assurance cần nối source, build, artifact và deployment.

## 19. Trust boundaries trong data protection và privacy

### 19.1. Dữ liệu thay đổi mức nhạy cảm

Khi dữ liệu đi từ event stream sang analytics, hoặc từ hồ sơ học viên sang dashboard, có thể có liên kết định danh, tăng khả năng suy luận, mở rộng người nhận, thay đổi mục đích, sao chép sang vendor hoặc kéo dài retention.

Ranh giới dữ liệu cần policy cho **purpose, classification, minimization, recipients, retention và deletion**. Một API qua HTTPS không chứng minh các điều kiện đó được đáp ứng.

### 19.2. Privacy harm và trust boundary

Một counselor có tài khoản hợp lệ nhưng xem nhãn dự đoán của học viên không thuộc nhiệm vụ vẫn có thể tạo privacy harm. Đây là ví dụ **đúng identity nhưng sai authorization/purpose**. Test cần kiểm tra actor, action, object, tenant, purpose và workflow, không chỉ status 200/403.

### 19.3. Evidence cho data crossing

- Data map và classification.
- Source/recipient identity và owner.
- Contract/data sharing approval.
- Payload/schema allowlist.
- Authorization and negative tests.
- Retention, deletion và downstream acknowledgments.
- Logs với actor/action/purpose, không chứa dữ liệu thừa.
- Privacy impact/risk review và findings.

## 20. Từ trust boundary sang security requirements

### 20.1. Requirement tốt phải cụ thể

Một requirement “mọi traffic nội bộ phải an toàn” khó kiểm thử. Nên viết:

- Chỉ service identity thuộc namespace được duyệt được gọi endpoint export.
- API xác minh actor có quyền với learner record trong đúng tenant.
- Worker không tin tenant/role do payload client khai báo.
- Queue chỉ nhận message từ producer được phép, schema version được hỗ trợ.
- Object storage private; chỉ worker/service đúng scope đọc/ghi prefix đã phân quyền.
- Admin thay trust policy cần MFA/JIT/approval/audit theo baseline.
- Khi policy service không sẵn sàng, export dữ liệu nhạy cảm không tự động fail-open.
- Mọi boundary crossing có log đủ truy vết và không ghi secret/PII không cần thiết.

### 20.2. Risk-to-requirement mapping

| Risk | Requirement | Control owner | Verification |
|---|---|---|---|
| Client sửa tenantId | Tenant lấy từ verified identity và kiểm tra object relationship | Backend | Cross-tenant negative tests |
| Direct API bypass gateway | Backend chỉ nhận trusted ingress/service identity hoặc có policy riêng | Platform/App | Direct-path network/auth tests |
| Forged queue message | Chỉ producer identity được phép publish | Queue owner | Unauthorized producer test |
| Worker privilege quá rộng | Worker chỉ có quyền dataset/prefix cần thiết | Platform/Data | IAM effective permissions, negative access |
| Cache cross-tenant | Tenant scope là phần bắt buộc của cache key/policy | Backend | Cache collision tests |
| Vendor nhận dữ liệu thừa | Payload chỉ có field được duyệt và purpose được ghi | Data/Vendor owner | Contract/schema/runtime payload tests |
| Admin trust drift | Trust/config changes được review và audit | Cloud/Security | Change log, policy diff, access review |
| Build artifact thay đổi | Deploy chỉ nhận artifact đúng provenance/signature | DevSecOps | Signature/provenance verification |
| Authorization dependency fail-open | Quy tắc degraded mode rõ, deny sensitive actions | App owner | Dependency failure tests |
| Logs không truy vết | Security events có actor/resource/action/correlation | SecOps | Synthetic event and log integrity tests |


## 21. Kiểm thử trust boundaries

### 21.1. Test theo từng crossing

Với mỗi boundary, kiểm tra ít nhất:

1. **Expected valid path:** actor/service hợp lệ thực hiện action được phép.
2. **Wrong identity:** danh tính giả, hết hạn, sai audience hoặc untrusted certificate.
3. **Wrong authorization:** identity hợp lệ nhưng sai role, tenant, object hoặc action.
4. **Tampered input:** sửa header, path, body, queue payload hoặc file metadata.
5. **Replay/duplicate/stale:** message/request cũ hoặc lặp.
6. **Bypass:** gọi service trực tiếp, cổng khác, path legacy, cache hoặc storage.
7. **Dependency failure:** PDP, identity provider, queue, CA, database hoặc logging không sẵn sàng.
8. **Resource abuse:** oversized payload, burst, recursion hoặc retry storm.
9. **Auditability:** log/trace cho allow/deny mà không lộ secret.
10. **Recovery:** sau rotate/revoke/rollback, policy vẫn đúng.

### 21.2. Test matrix minh họa

| Test ID | Boundary | Scenario | Expected result |
|---|---|---|---|
| TB-T01 | Client → API | Client sửa learnerId | Server xác minh quyền object, không rò dữ liệu |
| TB-T02 | Client → API | Token sai issuer/audience/expired | Request bị từ chối |
| TB-T03 | Gateway → API | Gọi backend trực tiếp từ network không được phép | Bị chặn |
| TB-T04 | Gateway → API | Header X-Role do client giả | Backend không tin header giả |
| TB-T05 | API → DB | Query không có tenant scope | Không truy cập record tenant khác |
| TB-T06 | API → Queue | Producer không được phép publish | Queue từ chối |
| TB-T07 | Queue → Worker | Message sai schema/oversized | Quarantine/reject, không side effect |
| TB-T08 | Queue → Worker | Message duplicate/replay | Idempotency/replay policy được thực thi |
| TB-T09 | Worker → Storage | Worker truy cập prefix tenant khác | Deny |
| TB-T10 | Tenant A → B | Cache key trùng | Không trả dữ liệu cross-tenant |
| TB-T11 | App → Vendor | Payload chứa field ngoài allowlist | Chặn hoặc không gửi |
| TB-T12 | Admin → Control plane | Admin không đủ quyền sửa policy | Deny và audit |
| TB-T13 | Build → Deploy | Artifact sai signature/provenance | Deployment bị từ chối |
| TB-T14 | PDP failure | Authorization service unavailable | Degraded/deny theo policy, không allow mặc định |
| TB-T15 | Logging boundary | Synthetic denied action | Log đúng actor/resource/correlation |
| TB-T16 | Bypass path | Gọi internal port không qua gateway | Không vượt policy |
| TB-T17 | Service identity | Certificate đúng CA nhưng sai service identity | Deny |
| TB-T18 | Storage URL | Dùng lại signed URL sau TTL/permission change | Behavior đúng policy |
| TB-T19 | Rate/resource | Flood queue/request | Quota/backpressure bảo vệ dịch vụ |
| TB-T20 | Secrets | Workload không thuộc scope đọc secret | Deny, alert theo risk |
| TB-T21 | Backup/restore | Restore dữ liệu vào zone thấp hơn | Không lộ dữ liệu, policy giữ nguyên |
| TB-T22 | Control plane | Deployment account ngoài scope thay network policy | Deny/approval/audit |
| TB-T23 | Vendor callback | Callback giả hoặc replay | Verify sender, signature, timestamp/idempotency |
| TB-T24 | Session lifecycle | User bị revoke nhưng session cũ còn dùng | Revocation policy được thực thi |
| TB-T25 | Incident recovery | Rotate credential sau compromise | Credential cũ không còn quyền theo policy |

### 21.3. Kiểm tra side effects

Một API trả HTTP 403 chưa chắc đã an toàn nếu request đã tạo job, ghi object hoặc gửi event trước khi từ chối. Test cần xác minh **không có side effects ngoài quyền** trong database, queue, object storage, cache, vendor và logs.

### 21.4. Không chỉ test happy path

Một architecture diagram có thể cho thấy mọi request đi qua gateway, nhưng thực tế có port nội bộ, debug endpoint, worker callback, scheduled job hoặc direct database path. Cần discovery và test các đường **ngoài luồng chuẩn**.

## 22. Assurance evidence cho trust boundaries

### 22.1. Claim–Argument–Evidence

**Claim mẫu:**

> Trong phạm vi production Learning Platform được xác định, mọi crossing quan trọng giữa client, gateway, Java services, database, queue, worker và storage đều áp dụng identity/authorization, validation và isolation theo policy; các đường bypass trọng yếu đã được kiểm tra trong kỳ.

**Argument:**

1. Inventory/DFD xác định actors, services, stores, trust zones và flows.
2. Mỗi boundary có owner, assumptions và requirements.
3. PEP thực thi policy dựa trên identity/context được xác minh.
4. Network/data isolation và least privilege hạn chế lateral movement.
5. Input/message/data được validate, bảo vệ và xử lý đúng lifecycle.
6. Positive/negative tests bao phủ sai identity, sai quyền, tampering, replay, bypass và dependency failure.
7. Monitoring/logging cung cấp khả năng phát hiện và điều tra.
8. Findings được khắc phục/retest hoặc residual risk được quyết định đúng thẩm quyền.

**Evidence:**

- Versioned DFD, boundary register, asset/service inventory.
- Trust assumptions, threat model, risk register và architecture decisions.
- IAM/role/policy/network/storage configurations.
- Token/certificate/service identity settings.
- API/DB/queue/storage authorization tests.
- Direct-path/bypass/negative tests và side-effect checks.
- CI/CD provenance/signature, deployment records.
- Logs/telemetry health, alert test, incident records.
- Change/review/approval, findings, remediation, retest.
- Assessor report với scope, period, population, exclusions và limitations.

### 22.2. Ba lớp effectiveness

| Lớp | Câu hỏi | Evidence | Không chứng minh |
|---|---|---|---|
| **Design effectiveness** | Boundary, threats, requirements và controls có phù hợp risk? | DFD, threat model, policy, architecture review | Chưa chứng minh đã cấu hình/triển khai |
| **Implementation effectiveness** | Enforcement có tồn tại trên tất cả đường cần thiết? | Config, code, IAM, network policy, tests | Chưa chứng minh hoạt động ổn định suốt kỳ |
| **Operating effectiveness** | Controls có được review/monitor và xử lý drift/incident? | Access reviews, change logs, alert tests, retests | Không bao phủ những thành phần ngoài scope |

Một sơ đồ kiến trúc được duyệt là evidence thiết kế; nó không tự chứng minh network policy được gắn vào mọi pod hoặc mọi endpoint có authorization.

### 22.3. Evidence metadata

Mỗi artifact nên có:
- Evidence ID và link tới boundary/risk/control/requirement.
- System, environment, region, tenant, service/build/version.
- Actor identity, resource, action và data flow được test.
- Method/tool/version, fixture, expected/actual, timestamps.
- Population/sample và cách chọn mẫu.
- Config/policy version và source of truth.
- Owner, collector, reviewer, approval.
- Logs/screenshots/query outputs được xử lý dữ liệu nhạy cảm.
- Limitations, exclusions, error/coverage và finding/retest.
- Retention/access policy cho evidence.

Evidence có thể chứa token, PII, network topology, secrets hoặc thông tin hệ thống nhạy cảm; cần **data minimization và access control** cho chính evidence repository.

## 23. Mẫu boundary register và assurance YAML

~~~yaml
boundary_id: TB-LEARNING-API-QUEUE-01
name: "Java API to export queue"
system: "Learning Platform"
from_component: "learning-api"
to_component: "export-queue"
trust_change:
  - "Synchronous user request becomes asynchronous job"
  - "API process identity becomes worker execution identity"
assets:
  data:
    - "export-request-metadata"
    - "learner-record-reference"
  identities:
    - "authenticated-user"
    - "learning-api-workload"
    - "report-worker-workload"
assumptions:
  - "Only the approved API workload can publish"
  - "Queue payload is untrusted until schema and authority checks pass"
  - "Worker permissions are narrower than database administration"
risks:
  - "Forged or replayed job message"
  - "Cross-tenant export"
  - "Stale user authorization"
requirements:
  - id: TB-REQ-01
    statement: "Only approved producer identity can publish"
  - id: TB-REQ-02
    statement: "Worker validates schema, tenant and job scope"
  - id: TB-REQ-03
    statement: "Unauthorized or duplicate jobs create no unauthorized side effects"
controls:
  - id: TB-CTRL-01
    owner: "Platform Messaging"
    mechanism: "Queue ACL and workload identity"
  - id: TB-CTRL-02
    owner: "Learning Backend"
    mechanism: "Job authorization and idempotency"
  - id: TB-CTRL-03
    owner: "Report Worker"
    mechanism: "Scoped storage/database permissions"
tests:
  - "Unauthorized producer denied"
  - "Malformed and oversized message rejected"
  - "Replay/duplicate job has bounded side effects"
  - "Cross-tenant job cannot read or write data"
evidence:
  period: "Populate actual assessment period"
  status: "Pending validation"
  sources:
    - "Queue IAM policy and producer identity"
    - "Worker runtime role and configuration"
    - "Negative tests and database/storage side-effect checks"
    - "Audit logs and alert health"
limitations:
  - "Do not claim other queues are covered without inventory reconciliation"
review_triggers:
  - "Producer or consumer identity changes"
  - "Queue schema or permission changes"
  - "New tenant data or export destination"
  - "Incident, replay finding or control failure"
~~~

Mẫu là **artifact học tập**. Thay các giá trị placeholder bằng ID, owner, config, test report và evidence thật trước khi dùng trong chương trình assurance.

## 24. Java: thực thi ranh giới tin cậy ở API

### 24.1. Không tin tenantId và role do client khai báo

~~~java
// Anti-pattern: client tự khai tenantId và role.
@GetMapping("/learners/{learnerId}")
public Learner getLearner(
        @PathVariable long learnerId,
        @RequestHeader("X-Tenant-Id") String tenantId,
        @RequestHeader("X-Role") String role) {
    return learnerRepository.findByTenantAndId(tenantId, learnerId);
}
~~~

Nếu backend tin headers do client kiểm soát, actor có thể sửa tenant hoặc role. Gateway cũng không cứu được nếu service direct path tồn tại hoặc gateway không ghi đè header.

### 24.2. Phác thảo policy check tại server

~~~java
@GetMapping("/learners/{learnerId}")
public LearnerView getLearner(
        @PathVariable long learnerId,
        @AuthenticationPrincipal AuthenticatedPrincipal principal) {

    var learner = learnerRepository.findById(learnerId)
            .orElseThrow(NotFoundException::new);

    // Principal được tạo sau quá trình xác thực phía server.
    // Quyền phải được kiểm tra trên object và tenant thực.
    if (!learnerAccessPolicy.canRead(principal, learner)) {
        throw new AccessDeniedException("Not permitted");
    }

    return learnerMapper.toRestrictedView(learner);
}
~~~

Đoạn mã chỉ minh họa. Production cần xử lý object enumeration, transaction/race conditions, field-level minimization, tenant context, error behavior và logging. Có thể query theo principal và scope trước để giảm nguy cơ tải object ngoài quyền trước khi kiểm tra.

### 24.3. Test negative và side effects

~~~java
@Test
void learnerFromAnotherTenantIsNotReturned() {
    var actor = fixtures.teacherFromTenantA();
    var learner = fixtures.learnerFromTenantB();

    assertThrows(AccessDeniedException.class,
        () -> learnerController.getLearner(
            learner.id(), actor));

    verifyNoInteractions(learnerExportService);
}

@Test
void clientSuppliedRoleDoesNotGrantAccess() {
    var learner = fixtures.restrictedLearner();
    var actor = fixtures.basicLearnerPrincipal();

    assertThrows(AccessDeniedException.class,
        () -> learnerController.getLearner(
            learner.id(), actor));
}
~~~

Tên fixture/controller là ví dụ. Test đầy đủ phải xác minh HTTP behavior, response body, database queries, cache, logs, queue và export/storage side effects.

## 25. Case study: trust boundaries trong export bảng điểm

### 25.1. Bối cảnh

Nền tảng học có browser/mobile, ingress/WAF/API gateway, Java Learning API, database dùng chung nhiều tenant, queue xử lý export, report worker, private object storage và analytics vendor nhận dữ liệu tổng hợp.

Yêu cầu nghiệp vụ: giảng viên chỉ xuất bảng điểm các lớp được phân công; học viên chỉ xem hồ sơ của mình; file export chỉ tải bởi actor được cấp quyền trong thời hạn phù hợp.

### 25.2. Các trust boundaries

| ID | Crossing | Giả định nguy hiểm nếu tin quá mức |
|---|---|---|
| TB-1 | Browser → ingress | UI validation đảm bảo client input hợp lệ |
| TB-2 | Gateway → API | Request qua gateway luôn có quyền trên mọi object |
| TB-3 | API → DB | TenantId từ request có thể dùng trực tiếp trong query |
| TB-4 | API → queue | Message do API gửi luôn đúng quyền khi worker chạy |
| TB-5 | Queue → worker | Payload role/tenant là sự thật và không bị replay |
| TB-6 | Worker → storage | Worker có quyền ghi thì có thể đọc mọi file |
| TB-7 | API → vendor | HTTPS nghĩa dữ liệu được chia sẻ đúng mục đích |
| TB-8 | Admin → control plane | Admin account có thể sửa policy mà không cần kiểm soát bổ sung |

### 25.3. Threat scenarios

- **BOLA/IDOR:** giáo viên sửa classId để đọc lớp khác.
- **Header spoofing:** client gửi X-Tenant-Id của tenant khác.
- **Queue replay:** một job hợp lệ được gửi lại nhiều lần, tạo nhiều file.
- **Stale authorization:** giảng viên bị gỡ khỏi lớp sau khi tạo job nhưng trước khi worker chạy.
- **Storage leakage:** object key đoán được hoặc bucket policy public.
- **Signed URL reuse:** URL tải file còn dùng được sau khi quyền bị thu hồi, vượt TTL policy.
- **Vendor over-sharing:** API gửi email/ghi chú ngoài tập dữ liệu đã duyệt.
- **Admin misuse:** thay trust/network policy để mở direct path.

### 25.4. Controls và verification

| Control | Implementation | Test |
|---|---|---|
| Client input untrusted | Server derives identity/tenant từ authenticated principal | Forged headers/path/body tests |
| Object authorization | Kiểm tra user–class–learner relationship ở server | Cross-tenant/object negative tests |
| Gateway boundary | Direct API paths bị chặn hoặc policy riêng | Direct-path tests |
| Queue integrity | Producer ACL, schema validation, idempotency | Forged/replay/duplicate/malformed tests |
| Worker least privilege | Role giới hạn dataset và storage prefix | IAM effective access tests |
| Fresh authorization | Re-check hoặc delegated scope có TTL | Revoke-between-request-and-execution tests |
| Private storage | Block public access, scoped object permissions | Anonymous/cross-tenant download tests |
| Signed URL lifecycle | TTL, scope, binding/revocation design | Expiry/reuse/permission-change tests |
| Vendor minimization | DTO/schema allowlist và purpose review | Payload inspection |
| Admin governance | MFA/JIT/approval/audit và separation | Unauthorized change tests |

### 25.5. Kết luận assurance

Một báo cáo có thể nêu:

> Trong phạm vi API, queue, worker và object storage production được inventory và kiểm tra trong kỳ, các đường export yêu cầu server-side object/tenant authorization, producer identity và storage isolation. Các negative tests đã xác minh những trường hợp cross-tenant, forged producer và duplicate job không tạo side effects ngoài quyền. Luồng legacy batch export chưa có runtime evidence, nên chưa được bao phủ trong claim.

Không nên viết “toàn bộ nền tảng không thể truy cập chéo tenant” nếu chưa kiểm tra search index, cache, reporting jobs, admin tools và vendor exports.

## 26. Findings, remediation và residual risk

### 26.1. Phân loại

| Trạng thái | Ví dụ | Hành động |
|---|---|---|
| **Control failure** | Worker đọc được object tenant khác | Contain, fix, retest |
| **Evidence gap** | Chưa biết có direct API path hay không | Discovery, test, giới hạn claim |
| **Design gap** | Queue job không có quy tắc quyền khi actor bị revoke | Thiết kế lại policy/workflow |
| **Implementation gap** | Policy có nhưng cache path không kiểm tra tenant | Sửa code/config, regression tests |
| **Operating failure** | Network policy bị drift sau deployment | Khôi phục baseline, monitoring, review |
| **Ownership gap** | Không ai chịu trách nhiệm trust store | Giao owner, inventory và review |
| **Exception** | Legacy consumer chưa hỗ trợ mTLS | Scope/time limit, compensating controls, approval |

### 26.2. Ví dụ finding

**Finding:** API kiểm tra tenant ở controller, nhưng report worker đọc job payload và dùng tenantId không được xác minh để truy vấn database.

**Evidence:** crafted job payload, queue identity, worker trace, SQL query, records được truy cập trong fixture và side effects.

**Impact:** một producer hoặc actor có thể gây export dữ liệu tenant khác qua worker.

**Remediation:** xác minh producer identity; ràng buộc job với approved export record; worker kiểm tra schema/tenant/scope và quyền theo policy; thu hẹp DB role; test direct/forged/replay/stale messages.

**Retest:** xác minh cả request, queue, worker, DB, file và signed URL. PR merged không đủ; cần build/deploy evidence và runtime tests trong scope.

### 26.3. Residual risk

Một residual risk record nên nêu boundary, asset, data và actor; threat/harm, likelihood, impact và uncertainty; controls/evidence/limitations; options; người có thẩm quyền và thời hạn; compensating controls, monitoring, trigger review và kế hoạch khắc phục.

Risk acceptance không làm test fail thành pass, không xóa nghĩa vụ bắt buộc và không thay bằng chứng control đang hoạt động.

## 27. Continuous assurance và quản trị thay đổi

### 27.1. Những thay đổi kích hoạt review

- Thêm API, service, queue, database, cache hoặc storage.
- Tạo tenant, role, service identity hoặc trust anchor mới.
- Thay token audience, mTLS, gateway, network policy hoặc authorization logic.
- Đổi schema, event, data classification, vendor hoặc mục đích sử dụng.
- Thay deployment, CI/CD runner, signer, artifact registry.
- Thay cloud account, IAM, secret store, region hoặc backup path.
- Thêm admin/debug route hoặc break-glass mechanism.
- Có incident, penetration test finding, privacy complaint hoặc control drift.
- Thay PDP/identity provider, policy engine, logging hoặc monitoring.

### 27.2. Gắn assurance vào SDLC

| Giai đoạn | Hoạt động | Evidence |
|---|---|---|
| Discovery | Asset, actor, purpose, criticality, trust assumptions | Context/risk record |
| Architecture | DFD, zones, boundary register, threat modeling | Versioned diagrams, design decisions |
| Development | Input validation, identity, authz, safe data flow | Code review, unit/integration tests |
| CI | SAST/DAST/API/contract tests, policy checks | Pipeline output, build mapping |
| Release | Change review, approvals, config validation | Release record, deployment evidence |
| Operations | Runtime probes, access reviews, drift/alerts | Logs, telemetry, config snapshots |
| Incident | Containment, scope, impact, recovery | Incident record, retest |
| Periodic assessment | Evidence quality, sample coverage, findings | Assurance report |
| Decommission | Revoke identity, remove paths/secrets, handle data | Exit evidence, inventory update |

### 27.3. Kiểm tra health của evidence collection

Một dashboard không có cảnh báo có thể là do sensor/collector đã ngừng hoạt động. Cần synthetic tests cho allow/deny và boundary crossings; health checks cho log, probe, policy engine và event collector; đối chiếu số endpoints/services đã inventory với số được test; alert khi policy/config/version thay mà test coverage không thay; kiểm tra false negatives/data loss/clock skew; lưu provenance/version cho script và bảo vệ evidence repository.

## 28. Metrics cho trust boundary assurance

| Metric | Ý nghĩa | Giới hạn |
|---|---|---|
| % critical systems có DFD và boundary register được review | Độ phủ kiến trúc | DFD có thể cũ hoặc thiếu flow |
| % boundary crossings có owner/requirements/controls | Accountability | Có record không chứng minh enforcement |
| % services có verified identity và least privilege | Identity governance | Config chưa chắc là effective state |
| % APIs có object/tenant negative tests | Kiểm tra authorization | Test một API không bao phủ toàn data paths |
| Số direct/bypass paths phát hiện | Visibility và segmentation | Số thấp có thể do discovery yếu |
| % queues có producer/consumer controls và replay tests | Event trust | Không đo mọi failure modes |
| % secrets/identities có owner và rotation evidence | Credential hygiene | Owner không chứng minh key không bị lộ |
| % production changes có security review | Change governance | Changes ngoài pipeline có thể bị bỏ sót |
| Số trust boundary findings quá hạn | Nợ rủi ro | Severity/impact cần được phân biệt |
| % remediation có retest trên runtime | Chất lượng fix | Ticket Done không thay verification |
| % evidence collectors health-checked | Tin cậy monitoring | Health green không bảo đảm source completeness |
| Số tenant/data isolation failures | Phát hiện disclosure risk | Cần scope/sample context |
| % vendor crossings có data/security evidence | Third-party assurance | Contract không thay runtime controls |
| Thời gian phát hiện và giới hạn lateral movement | Detection/containment | Phụ thuộc telemetry coverage |

Tránh một con số “100% boundaries secured” nếu không công bố mẫu số, scope, kỳ, các ranh giới chưa inventoried và những control chưa được test.

## 29. Những sai lầm thường gặp

**“Trust boundary là firewall.”** Firewall chỉ là một dạng boundary/control; identity, tenant, data, process, control plane và vendor cũng tạo ranh giới.

**“Bên trong VPC là trusted.”** Network location không chứng minh identity hoặc quyền. Workload nội bộ vẫn có thể bị chiếm.

**“Đã đăng nhập thì được xem mọi record.”** Authentication không thay object/tenant/action authorization.

**“API gateway xử lý hết security.”** Service, worker, DB, storage và direct paths vẫn cần enforcement.

**“mTLS là đủ, không cần authorization.”** Certificate hợp lệ chứng minh peer theo trust model, không quyết định quyền dữ liệu.

**“Queue message do service gửi thì có thể tin payload.”** Message có thể bị sửa, replay, duplicate hoặc stale; consumer cần xác minh.

**“Một HTTP 403 là không có side effects.”** Job/file/event có thể đã được tạo trước khi deny; cần kiểm tra toàn đường.

**“Private subnet đảm bảo database không thể bị truy cập chéo tenant.”** Tenant isolation là policy ở data layer và mọi bản sao, không chỉ network.

**“Dữ liệu chỉ cần validate ở frontend.”** Client do người dùng kiểm soát; server phải xác minh lại.

**“Cloud provider bảo vệ toàn bộ stack.”** Shared responsibility phụ thuộc dịch vụ và cấu hình; khách hàng vẫn có nhiều nghĩa vụ.

**“Artifact có chữ ký nghĩa code an toàn.”** Signature không thay code review, dependency checks, provenance và deployment controls.

**“Zero Trust chỉ là triển khai gateway.”** Cần identity, policy, enforcement, resource context, monitoring và test bypass.

**“Một DFD được duyệt nghĩa runtime giống sơ đồ.”** Phải đối chiếu discovery, config, logs, deployments và tests.

**“Fail-open chỉ là cách tăng availability.”** Có thể cho phép truy cập nhạy cảm khi không xác minh; phải định nghĩa degraded mode và test.

**“Không có alert nghĩa không có bypass.”** Collector có thể thiếu scope hoặc ngừng chạy.

**“Thiếu evidence tức chắc chắn control fail.”** Đó là evidence gap, nhưng không thể kết luận pass.

**“Risk acceptance biến finding thành đạt.”** Acceptance là quyết định quản trị, không thay sự thật kỹ thuật.

## 30. Bài tập thực hành

### Bài tập A — Vẽ trust boundaries

Vẽ DFD cho nền tảng có browser, API gateway, Java API, Redis cache, PostgreSQL, queue, report worker, object storage và vendor analytics. Đánh dấu mọi trust zones, boundary crossings, identity và dữ liệu đi qua. Ghi owner và ít nhất một assumption tại mỗi crossing.

### Bài tập B — Phân biệt identity và authorization

Một học viên đăng nhập hợp lệ, sửa learnerId trên URL và đọc được profile người khác. Xác định boundary nào thất bại, threat STRIDE nào phù hợp, requirement và negative tests cần bổ sung. Phân biệt lỗi authentication, authorization và tenant isolation.

### Bài tập C — Queue replay và stale authorization

Một giảng viên tạo job export lúc đang được phân công lớp. Trước khi worker chạy, quyền bị thu hồi; một message duplicate được gửi lại.

Thiết kế quy tắc authorization theo thời điểm, idempotency, replay protection, job expiry, file access và audit. Viết expected/actual và side-effect tests.

### Bài tập D — Direct-path bypass

Gateway kiểm tra OAuth token nhưng Java service có port nội bộ có thể truy cập từ một subnet rộng. Một workload bị chiếm gọi trực tiếp port này.

Xác định trust assumptions sai, network/identity controls, direct-path tests, owner và evidence cần có. Nêu cách kiểm tra cả admin/debug/legacy endpoints.

### Bài tập E — Cloud cross-account trust

CI runner account A assume role deploy production account B. Trust policy dùng wildcard principal và role admin. Đề xuất giới hạn identity, audience/subject, actions/resources, session duration, approval, audit và negative tests.

### Bài tập F — Boundary của data classification

Event stream chứa learnerId, courseId, timestamp được gửi sang analytics. Nhóm kỹ thuật gọi đó là “technical metadata”.

Phân tích khả năng liên kết/suy luận, classification, purpose, minimization, recipients và retention. Đề xuất test payload và evidence cho vendor boundary.

### Bài tập G — Supply chain

Một developer có thể sửa build script; CI runner có quyền lấy production secrets; artifact registry cho phép overwrite tag; deploy controller không kiểm tra digest/signature.

Vẽ trust chain, STRIDE threats, controls và tests. Viết một CAE claim có scope rõ. Phân biệt signature validity với source/build provenance.

### Bài tập H — Fail-open

Authorization PDP ngừng hoạt động trong giờ cao điểm. API đang fallback cho phép mọi request để giữ uptime.

Đánh giá impact theo dữ liệu/chức năng; đề xuất degraded mode, cache policy decision có TTL/scope, break-glass và test dependency failure. Xác định ai có quyền chấp nhận residual risk.

### Bài tập I — Assurance report

Giả sử inventory có 50 services; 45 có DFD, 40 có identity policy, 32 có tenant negative tests, 5 có direct path chưa review và logging collector của một zone đã ngừng 2 ngày.

Phân loại design/implementation/operating evidence, control failure và evidence gap. Viết claim không vượt scope, ưu tiên remediation và evidence cần bổ sung.

### Bài tập J — Case review toàn diện

Một API export bảng điểm dùng mTLS từ report-worker, queue và object storage. Test cho thấy client cert đúng CA nhưng worker có thể đọc object tenant khác; signed URL còn hiệu lực sau khi user bị thu hồi quyền.

Hãy xác định:
- Ranh giới identity, authorization, queue, storage và user download.
- Threat/harms và mức impact.
- Controls ở producer, consumer, DB, storage, URL issuance và download.
- Test positive/negative/replay/revoke/bypass.
- Evidence cần cho retest và điều kiện đóng finding.
- Cách báo residual risk nếu một legacy download path chưa thể kiểm tra.

## 31. Checklist thiết kế và đánh giá trust boundaries

- [ ] Scope, assets, actors, data classifications và criticality được xác định.
- [ ] Có DFD/data flow và versioned architecture context.
- [ ] Network, identity, tenant, data, process, control-plane, supply-chain và vendor boundaries được xem xét.
- [ ] Mỗi boundary có trust assumptions, owner và policy rõ.
- [ ] Trust không suy ra chỉ từ IP, subnet, cluster hoặc login.
- [ ] Client input, headers, message payload và file metadata được xem là untrusted tới khi xác minh.
- [ ] Identity validation tách biệt với application/object/tenant authorization.
- [ ] Có PEP/PDP hoặc điểm enforcement rõ tại nơi truy cập resource.
- [ ] Có least privilege, segmentation và giới hạn blast radius.
- [ ] Gateway không phải lớp duy nhất; direct/bypass/legacy paths được kiểm tra.
- [ ] Database, cache, queue, worker, storage và export giữ tenant/data scope.
- [ ] Message có schema, producer identity, replay/idempotency và stale-authority rules.
- [ ] Cloud shared responsibility và cross-account trust được ghi rõ.
- [ ] Build/source/dependency/artifact/signing/deploy boundaries được kiểm soát.
- [ ] Vendor crossings có purpose, data minimization, contract và evidence.
- [ ] Fail-open/degraded mode được quyết định trước và test.
- [ ] Logging/monitoring có integrity, health checks và không ghi thừa secrets/PII.
- [ ] Threat modeling bao gồm STRIDE và các harms/business/privacy scenarios.
- [ ] Requirements có expected behavior, control owner và test method.
- [ ] Có positive/negative, tampering, replay, bypass, failure và side-effect tests.
- [ ] Test mapping tới build, config, environment, tenant và thời điểm.
- [ ] Có Claim–Argument–Evidence cho mục tiêu quan trọng.
- [ ] Phân biệt design, implementation và operating effectiveness.
- [ ] Evidence có provenance, completeness, freshness, reliability và limitations.
- [ ] Findings có owner, impact, remediation, retest và residual risk decision.
- [ ] Thay đổi service/identity/data/tenant/vendor/control plane kích hoạt reassessment.
- [ ] Báo cáo nói rõ boundaries nào đã kiểm tra và phần nào chưa có bằng chứng.

## 32. Ghi nhớ

- **Trust boundary là nơi giả định tin cậy, identity, authority hoặc mức kiểm soát thay đổi**, không chỉ là ranh giới mạng.
- Network zone, identity, authorization, tenant, data, process, cloud control plane, supply chain và vendor đều có thể tạo boundary.
- **Authenticated không đồng nghĩa authorized**; identity hợp lệ vẫn cần quyền đúng action/resource/tenant/purpose.
- Mọi crossing cần policy, enforcement point, owner, validation, monitoring và evidence.
- DFD/boundary register là nền tảng cho threat modeling, requirements, tests và assurance, nhưng phải đối chiếu với runtime.
- STRIDE giúp nhận diện threat; cần bổ sung privacy harms, misuse, insider, supply-chain và failure modes.
- Gateway, mTLS, private subnet hay Zero Trust label **không thay kiểm soát tại service, data store, queue, worker và storage**.
- Queue, cache, export, backup và direct path thường là những nơi dễ bị bỏ sót khi đánh giá boundary.
- Fail-open/degraded mode phải được thiết kế và test theo risk; không tự cho phép dữ liệu nhạy cảm khi không xác minh được.
- Assurance cần **risk → requirement → control → test/evidence → assessment → finding/remediation → continuous reassessment**, với scope và limitations rõ.
- Một kiến trúc an toàn được chứng minh bằng **hành vi thực và evidence trong vận hành**, không chỉ bằng sơ đồ hoặc tuyên bố rằng mọi thành phần đều trusted.


