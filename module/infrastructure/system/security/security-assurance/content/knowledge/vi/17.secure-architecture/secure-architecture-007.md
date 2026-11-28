# Isolation boundary: Thiết kế và kiểm chứng ranh giới cô lập an toàn

## 1. Isolation boundary là gì?

**Isolation boundary** (ranh giới cô lập) là ranh giới kiến trúc, cấu hình hoặc thực thi được dùng để **ngăn một chủ thể, workload, tenant, tiến trình hay vùng dữ liệu tác động trái phép tới tài nguyên nằm ngoài phạm vi được cấp**. Ranh giới này xác định nơi một yêu cầu được tin cậy, nơi cần kiểm tra quyền và những đường mà dữ liệu hoặc quyền có thể đi qua.

Ví dụ:

- Trong SaaS nhiều khách hàng, tenant A không thể đọc, sửa hoặc suy ra dữ liệu tenant B.
- Một container bị xâm nhập không thể đọc secret của container khác hoặc điều khiển node.
- Một service ở mạng public không thể truy cập trực tiếp database chỉ dành cho private network.
- Một plugin không thể đọc file tùy ý trên máy chủ của ứng dụng chủ.
- Một môi trường development không thể sử dụng credential hoặc thay đổi tài nguyên production.
- Một tài khoản vận hành không thể tự cấp thêm quyền và xóa dấu vết kiểm toán của chính mình.

Ranh giới cô lập có thể được tạo bằng **identity, authorization, process isolation, container/VM, network segmentation, namespace, database policy, encryption key, resource quota, sandbox, API gateway hoặc cơ chế thực thi khác**. Không có một công nghệ duy nhất giải quyết tất cả các dạng cô lập.

Trong module **SECURITY_SECURITY_ASSURANCE**, isolation boundary phải được đánh giá như một security control có thể kiểm chứng: **tài sản nào cần cô lập, threat nào có thể vượt ranh giới, cơ chế nào thực thi, đường nào có thể bypass, bằng chứng nào chứng minh việc từ chối truy cập và cách khắc phục khi phát hiện ranh giới yếu**.

> **Nguyên tắc:** ranh giới chỉ có ý nghĩa khi hệ thống thực thi nó ở nơi có thẩm quyền. Một nhãn tenant trên giao diện, một subnet riêng hoặc một container riêng không tự chứng minh các chủ thể đã được cô lập an toàn.

### 1.1. Isolation, segmentation và authorization

| Khái niệm | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Isolation** | Ngăn ảnh hưởng hoặc truy cập vượt qua phạm vi đã định | Tenant A không thể truy cập dữ liệu tenant B |
| **Segmentation** | Chia hệ thống thành vùng có luồng kết nối được kiểm soát | Chỉ API tier được kết nối database tier |
| **Authorization** | Quyết định principal có được thực hiện action trên resource không | User chỉ được xem order thuộc tenant mình |
| **Sandboxing** | Giới hạn môi trường thực thi của code/process | Plugin chỉ được đọc thư mục được cấp |
| **Tenant isolation** | Cô lập dữ liệu, compute, identity và tài nguyên giữa khách hàng | Query luôn giới hạn theo tenant context đáng tin |
| **Blast-radius containment** | Hạn chế phạm vi ảnh hưởng khi một thành phần bị compromise | Workload chỉ có quyền trên một namespace |

Segmentation thường là một lớp hỗ trợ isolation. Authorization là một quyết định tại ranh giới. **Isolation end-to-end cần nhiều lớp phối hợp**: mạng có thể chặn truy cập trực tiếp, nhưng API vẫn phải kiểm tra tenant và quyền trên từng tài nguyên.

### 1.2. Ranh giới tin cậy và ranh giới cô lập

**Trust boundary** là nơi giả định về mức tin cậy thay đổi, chẳng hạn từ Internet vào API, từ user sang service, hoặc từ workload sang control plane. **Isolation boundary** là một ranh giới được thiết kế để hạn chế tương tác qua một hoặc nhiều trust boundary.

Hai khái niệm liên quan nhưng không đồng nhất:

- Một trust boundary có thể cần authentication, validation và authorization.
- Một isolation boundary có thể nằm bên trong cùng một mạng hoặc cùng một tiến trình.
- Một hệ thống có nhiều trust boundary nhưng vẫn thiếu isolation giữa tenant.
- Một ranh giới vật lý có thể vẫn có trust boundary ở control plane, hypervisor hoặc quản trị hạ tầng.

Threat model phải chỉ ra **ai đang tin ai, tài nguyên nào được chia sẻ và hành động nào được phép đi qua ranh giới**.

## 2. Vì sao cần cô lập?

Nếu một thành phần bị xâm nhập hoặc hoạt động sai, isolation giới hạn phạm vi ảnh hưởng.

Các mục tiêu chính:

1. **Confidentiality:** chủ thể không đọc dữ liệu ngoài phạm vi.
2. **Integrity:** chủ thể không sửa/xóa tài nguyên của vùng khác.
3. **Availability:** một tenant hoặc workload không làm cạn tài nguyên của tất cả tenant.
4. **Least privilege:** mỗi workload chỉ có quyền tối thiểu trong vùng cần thiết.
5. **Containment:** compromise của một thành phần không tự mở đường sang control plane hoặc dữ liệu khác.
6. **Accountability:** có thể xác định actor, resource, tenant và decision tại ranh giới.
7. **Assurance:** có thể kiểm tra cả đường được phép lẫn đường phải bị từ chối.

### 2.1. Những tình huống thiếu isolation thường gặp

| Tình huống | Điểm yếu | Hậu quả |
| --- | --- | --- |
| Query database không có tenant filter | Dựa vào ID do client gửi | Lộ dữ liệu chéo tenant |
| Cache dùng key chỉ theo object ID | Thiếu tenant/principal trong cache key | User nhận response của tenant khác |
| Service account dùng chung | Một credential có quyền trên nhiều dịch vụ | Compromise lan rộng |
| Network rule cho phép mọi subnet nội bộ | “Internal” bị coi là đáng tin | Lateral movement |
| Container chạy privileged | Workload có quyền vượt giới hạn container | Ảnh hưởng node/cluster |
| Dev và prod dùng chung credential | Ranh giới môi trường yếu | Test hoặc account dev tác động production |
| Async worker không mang tenant context | Mất ngữ cảnh authorization sau queue | Xử lý nhầm dữ liệu tenant |
| Plugin chạy cùng quyền với host | Không có sandbox hoặc API hạn chế | Plugin đọc secret/file của host |
| Control plane chung không phân quyền | Tenant operator tác động tài nguyên khác | Compromise toàn nền tảng |
| Rate limit toàn cục không theo tenant | Một tenant tiêu thụ hết tài nguyên | Denial of service diện rộng |

Một lỗi isolation có thể là **IDOR/BOLA**, lỗi cấu hình, thiếu kiểm tra quyền, confused deputy, sai cache key hoặc đường quản trị quá rộng. Không phải mọi lỗi đều đến từ firewall.

## 3. Các loại isolation boundary

### 3.1. Identity và authorization boundary

Cô lập dựa trên **principal, role, permission, resource và condition**. Mỗi service cần danh tính riêng; quyền của một workload không được tự mở rộng sang service khác.

Kiểm tra:

- Principal được xác thực từ nguồn nào?
- Ai có thể giả mạo hoặc thay đổi subject/tenant claim?
- Quyền có được kiểm tra ở server-side tại từng action?
- Có quyền gián tiếp qua service account, role binding hoặc token exchange?
- Token có audience/scope phù hợp?
- Có thể chuyển tenant context qua header do client tự khai không?

### 3.2. Tenant và data boundary

Trong SaaS multi-tenant, dữ liệu thường dùng chung database hoặc storage. Cần kiểm tra ranh giới giữa tenant ở:

- Database row/schema/database riêng.
- Object storage path và access policy.
- Search index, vector store và analytics.
- Cache, session, file export và report.
- Event queue, topic, webhook và notification.
- Backup, restore và data warehouse.
- Support tooling và administrative API.

Tenant ID chỉ là metadata. **Nó phải được gắn với danh tính đáng tin và được kiểm tra tại nơi truy cập dữ liệu**.

### 3.3. Process, container và VM boundary

Các lớp thực thi có mức cô lập khác nhau:

| Cơ chế | Cách cô lập | Rủi ro cần đánh giá |
| --- | --- | --- |
| Process/user boundary | UID/GID, permission, process isolation | Shared kernel, privilege escalation, file permission |
| Container | Namespace, cgroups, capabilities, seccomp, MAC | Shared kernel, privileged mode, host mounts |
| Virtual machine | Hypervisor và guest boundary | Hypervisor escape, virtual device, management plane |
| MicroVM/sandbox | Môi trường thực thi tối giản hơn tùy nền tảng | Runtime/configuration, syscall và resource boundary |
| Language/runtime sandbox | Giới hạn API, module, memory hoặc execution context | Escape, unsafe native code, reflection, host API leak |

Không nên xếp hạng tuyệt đối mọi công nghệ. Mức cô lập phụ thuộc cấu hình, threat model, nền tảng và khả năng quản trị. Container không tương đương VM trong mọi mô hình đe dọa vì container thường chia sẻ kernel host.

### 3.4. Network boundary

Network isolation giới hạn **ai có thể kết nối tới đâu, qua protocol/port nào và trong điều kiện nào**.

Ví dụ:

- Public ingress chỉ tới reverse proxy/API gateway.
- API tier chỉ gọi database qua port cần thiết.
- Database không có public ingress.
- Management plane chỉ truy cập từ admin network hoặc identity-aware access path.
- Egress được giới hạn theo destination/service.
- Workload giữa các namespace không được mặc định tin nhau.

Network segmentation **không thay authorization ở ứng dụng**. Nếu API có thể đọc mọi tenant, subnet riêng không sửa được lỗi đó.

### 3.5. Control plane và data plane boundary

**Data plane** xử lý request/dữ liệu nghiệp vụ. **Control plane** quản lý cấu hình, identity, policy, deployment và tài nguyên nền tảng.

Control plane thường có quyền tác động lớn. Cần cô lập:

- Quyền deploy khỏi quyền sửa policy bảo mật.
- Quyền tenant admin khỏi quyền platform admin.
- Quyền đọc secret khỏi quyền sửa audit.
- Quản trị production khỏi dev/test.
- API quản trị khỏi API người dùng.
- Identity cấp workload khỏi identity quản lý cluster.

Nếu một tenant có thể gọi control plane API để tạo role hoặc đổi policy của tenant khác, data-plane authorization riêng là chưa đủ.

### 3.6. Shared resource và side-channel boundary

Các tenant có thể chia sẻ CPU, memory, storage, cache, scheduler, GPU hoặc network. Ngay cả khi API từ chối truy cập trực tiếp, **tài nguyên chia sẻ có thể tạo ảnh hưởng gián tiếp**:

- Một tenant làm cạn CPU/memory/connection pool.
- Cache contention làm lộ timing hoặc trạng thái.
- Side-channel qua timing, cache hoặc tài nguyên phần cứng.
- Queue backlog của một tenant làm chậm tenant khác.
- Shared search/vector index gây retrieval chéo dữ liệu.
- Tên file, object key hoặc metrics để lộ metadata tenant.

Không phải mọi hệ thống đều cần chống mọi side-channel ở cùng mức. Mức kiểm soát phải dựa trên dữ liệu, threat model, mức nhạy cảm và nền tảng.

## 4. Isolation model: shared, logical và dedicated

Một dịch vụ có thể kết hợp nhiều mô hình:

| Mô hình | Cách triển khai | Ưu điểm | Điểm cần đánh giá |
| --- | --- | --- | --- |
| **Shared infrastructure, logical isolation** | Nhiều tenant dùng chung compute/database, phân tách bằng identity, row policy và application logic | Hiệu quả chi phí, dễ vận hành | Lỗi query, cache, async context hoặc policy có thể gây cross-tenant |
| **Schema/database per tenant** | Tách schema hoặc database | Giảm một số lỗi truy vấn chéo, dễ áp dụng backup/retention riêng | Quản lý connection, migration, credential và số lượng database |
| **Dedicated workload per tenant** | Compute/service riêng | Giảm chia sẻ runtime và blast radius | Chi phí, drift cấu hình, control plane và vận hành |
| **Dedicated account/project/subscription** | Tách cloud account/project và policy | Ranh giới quản trị mạnh hơn nếu cấu hình đúng | Identity federation, central admin, network và billing/control plane |
| **Hybrid isolation** | Dữ liệu hoặc workload nhạy cảm được tách riêng, phần còn lại dùng chung | Điều chỉnh theo risk tier | Cần quản lý policy nhất quán và tránh đường chuyển đổi yếu |

Không có mô hình “dedicated” nào tự động an toàn. Một project riêng nhưng cùng admin credential toàn quyền, cùng pipeline không kiểm soát hoặc cùng logging có thể vẫn có ranh giới quản trị yếu.

### 4.1. Chọn isolation theo risk

Đánh giá:

- Loại dữ liệu và mức ảnh hưởng khi lộ/sửa.
- Mô hình tenant và khả năng khách hàng tự quản trị.
- Mức tin cậy giữa các tenant.
- Quyền workload và blast radius.
- Yêu cầu về vị trí dữ liệu, retention hoặc hợp đồng.
- Khả năng phát hiện, containment và phục hồi.
- Chi phí vận hành và khả năng kiểm chứng.

Một ứng dụng demo nội bộ có thể chấp nhận logical isolation đơn giản hơn nền tảng lưu dữ liệu nhạy cảm của nhiều tổ chức. Nhưng cả hai vẫn cần xác định trust boundary và test cross-tenant.

## 5. Threat modeling cho isolation boundary

### 5.1. Threat scenarios

| ID | Kịch bản | Đường vượt ranh giới | Control cần xem |
| --- | --- | --- | --- |
| **ISO-01** | User thay tenant ID trong request | Tin header/path/query từ client | Tenant context từ authenticated principal |
| **ISO-02** | API trả object theo ID mà không kiểm tra owner | IDOR/BOLA | Object-level authorization |
| **ISO-03** | Cache response chỉ theo resource ID | Cache key thiếu tenant/permission | Tenant-aware cache key và invalidation |
| **ISO-04** | Async worker xử lý event sai tenant | Tenant context không được ràng buộc | Signed/validated event, explicit context, reauthorization |
| **ISO-05** | Service A dùng credential đọc mọi database | Service identity quá rộng | Per-service identity và scoped grants |
| **ISO-06** | Container có hostPath/privileged | Workload vượt container boundary | Restricted capabilities, seccomp, MAC, admission policy |
| **ISO-07** | Network rule cho phép lateral movement | Trust toàn subnet nội bộ | Default-deny network policy, service identity |
| **ISO-08** | Tenant admin gọi control plane API | Data-plane role có quyền quản trị platform | Tách control-plane roles/API |
| **ISO-09** | Một tenant làm cạn tài nguyên | Không quota/rate limit theo tenant | Per-tenant quotas, fairness, backpressure |
| **ISO-10** | Search/vector retrieval trả chunk tenant khác | Index filter không gắn identity | Tenant-scoped index/query and result validation |
| **ISO-11** | Backup/restore trộn dữ liệu tenant | Restore path thiếu mapping/scope | Restore isolation và post-restore validation |
| **ISO-12** | Support operator xem dữ liệu mọi tenant | Support tool có quyền mặc định quá rộng | Justified access, JIT, approval và audit |
| **ISO-13** | Plugin thực thi code trong process host | Sandbox/API boundary yếu | Process/VM isolation và restricted host API |
| **ISO-14** | Metadata hoặc timing để lộ tenant khác | Shared resource side-channel | Resource partitioning, noise/limits hoặc dedicated tier theo risk |

### 5.2. Các câu hỏi STRIDE tại ranh giới

Có thể dùng STRIDE để cấu trúc threat review:

- **Spoofing:** actor có thể giả tenant, workload hoặc service identity không?
- **Tampering:** actor có thể sửa tenant claim, policy, route, object owner hoặc event metadata không?
- **Repudiation:** có thể phủ nhận hành động vì audit thiếu actor/tenant/correlation không?
- **Information disclosure:** có thể đọc dữ liệu, secret, metadata hoặc timing của vùng khác không?
- **Denial of service:** một tenant có thể chiếm tài nguyên chung hoặc làm gián đoạn tenant khác không?
- **Elevation of privilege:** có thể chuyển từ quyền tenant/user sang platform/admin hoặc host không?

STRIDE là cách đặt câu hỏi, không phải bằng chứng rằng mọi threat đã được tìm thấy. Cần gắn threat với asset, trust boundary, precondition, impact và control cụ thể.

### 5.3. Abuse case và confused deputy

**Confused deputy** xảy ra khi một service có quyền mạnh hơn caller bị lừa sử dụng quyền của chính nó cho tài nguyên mà caller không được phép truy cập.

Ví dụ: report service có quyền đọc tất cả tenant. User A gửi tenant ID của B; service dùng quyền service account để truy vấn dữ liệu B mà không kiểm tra quyền của user A.

Cách giảm rủi ro:

- Không dùng quyền service account để thay thế authorization của caller.
- Truyền principal/tenant context đáng tin qua boundary.
- Kiểm tra quyền ở resource/action cụ thể.
- Giới hạn quyền service identity.
- Ghi audit cả **requesting actor** và **executing workload**.
- Test cross-tenant và delegated access.

## 6. Thiết kế isolation boundary theo defense in depth

### 6.1. Xác định principal và context đáng tin

Tenant context nên được lấy từ identity đã xác thực hoặc policy service đáng tin, sau đó gắn với request context ở server. Header X-Tenant-ID do client gửi có thể là gợi ý định tuyến, nhưng **không phải bằng chứng quyền truy cập**.

Cần xác minh:

- Issuer, audience, signature, expiry và claims của token.
- Quan hệ user–tenant và trạng thái membership.
- Role/permission theo tenant.
- Context được giữ đúng qua async, queue và service-to-service.
- Không cho client thay đổi subject hoặc tenant sau xác thực.
- Reauthorization khi quyền hoặc membership thay đổi theo yêu cầu.

### 6.2. Kiểm soát ở nhiều lớp

Một mô hình tốt có thể kết hợp:

1. **Edge:** authentication, request validation, rate limit và route.
2. **Application:** authorization theo action/resource/tenant.
3. **Data access:** query scope, row-level security hoặc database/schema tách.
4. **Cache/search:** key/filter theo tenant và quyền.
5. **Service identity:** workload identity riêng, least privilege.
6. **Network:** default-deny, allowlist luồng cần thiết.
7. **Runtime:** process/container/VM sandbox và hardening.
8. **Control plane:** tách admin API, policy, deployment và audit.
9. **Monitoring:** event, anomaly detection, quota và alert.
10. **Assurance:** negative tests, bypass tests, configuration review và retest.

Các lớp phải nhất quán. Nếu application cho phép tenant B nhưng database row policy từ chối, hệ thống có thể lỗi nghiệp vụ; nếu application cho phép sai nhưng database policy chặn, đó là defense-in-depth hữu ích nhưng vẫn cần sửa application gap.

### 6.3. Default deny và failure behavior

Khi không xác định được tenant, principal, resource ownership hoặc policy decision, thao tác nhạy cảm phải bị từ chối theo baseline. Nếu policy engine hoặc identity provider lỗi, hệ thống cần hành vi được thiết kế trước.

Không mặc định:

- Dùng tenant mặc định.
- Bỏ filter để “cho request chạy”.
- Chuyển sang service account rộng.
- Bỏ qua network policy.
- Cho phép mọi internal service.
- Cache quyết định allow vô thời hạn.

Với availability-critical workloads, có thể cần thiết kế degraded mode có giới hạn và được đánh giá rủi ro. Degraded mode phải có scope, thời hạn, monitoring và điều kiện quay lại bình thường.

## 7. Tenant isolation trong ứng dụng nhiều khách hàng

### 7.1. Nguồn tenant context

Có thể có nhiều nguồn thông tin:

- Claim tenant trong access token được issuer đáng tin ký.
- Membership/organization mapping trong identity service.
- API key hoặc workload identity gắn với tenant cụ thể.
- Context được xác minh tại API gateway hoặc backend.

Không dùng trực tiếp tenant ID từ URL/header/body để quyết định quyền. Nếu URL có tenant ID, backend phải xác minh principal hiện tại có quyền trên tenant đó.

### 7.2. Object-level authorization

Kiểm tra quyền không nên dừng ở role chung như CUSTOMER_SUPPORT. Cần biết actor có quyền trên **đối tượng cụ thể**.

Ví dụ:

- User A có thể đọc order thuộc tenant A.
- User A không thể đọc order thuộc tenant B dù biết UUID.
- Tenant admin có thể quản lý thành viên trong tenant mình, không được sửa membership tenant khác.
- Support operator chỉ có quyền truy cập case được phê duyệt và trong thời gian cần thiết.

### 7.3. Data isolation patterns

| Pattern | Cách bảo vệ | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Shared table + tenant column | Mỗi row có tenant ID; mọi query phải scope | Query thiếu filter, join sai, bulk operation |
| Row-level security (RLS) | Database policy áp dụng filter theo session/context | Context session sai, connection pool không reset, owner/bypass role |
| Schema per tenant | Tách schema và mapping tenant | Search path sai, migration và connection routing |
| Database per tenant | Tách database và credential | Pool/config nhầm tenant, admin/backup tập trung |
| Storage prefix per tenant | Object path riêng và policy | Path traversal, bucket policy rộng, signed URL |
| Search index per tenant | Index riêng hoặc filter bắt buộc | Query bypass filter, alias sai, index rebuild |
| Encryption key per tenant | Tách key hoặc data key theo tenant | Key policy, key selection và metadata binding |

RLS và database isolation là defense-in-depth. Không được mặc định chúng thay thế hoàn toàn authorization nghiệp vụ, audit và test.

### 7.4. Cache isolation

Cache key phải phản ánh mọi yếu tố ảnh hưởng đến kết quả và quyền truy cập, thường gồm:

- Tenant ID.
- Resource ID.
- User/role hoặc permission version khi response khác theo quyền.
- Locale/purpose hoặc context liên quan nếu ảnh hưởng kết quả.
- Version/schema hoặc invalidation generation.

Không đưa secret hoặc dữ liệu nhạy cảm vào cache key theo cách dễ lộ. Cache cần kiểm soát TTL, invalidation khi đổi membership/role và không trả response đã cache trước khi kiểm tra authorization hiện tại nếu chính sách yêu cầu.

### 7.5. Async và event-driven isolation

Khi request tạo message để worker xử lý, cần giữ **tenant, subject, purpose và correlation context** có nguồn gốc tin cậy.

- Producer xác minh actor và quyền trước khi phát event.
- Event có schema/version, tenant binding và integrity phù hợp.
- Consumer xác thực nguồn message và kiểm tra tenant/resource scope.
- Không tin event payload có tenant do client tự khai.
- Retry/dead-letter không làm mất hoặc trộn context.
- Worker dùng identity riêng và chỉ có quyền cần thiết.
- Audit liên kết actor ban đầu, producer, consumer và action.

Không nên dùng ThreadLocal tùy tiện làm nguồn context duy nhất trong async execution; context có thể không được truyền hoặc bị tái sử dụng sai qua thread pool.

## 8. Network isolation và service-to-service

### 8.1. Phân vùng mạng

Các vùng thường được tách theo chức năng:

- **Public/edge:** load balancer, reverse proxy, API gateway.
- **Application:** service xử lý nghiệp vụ.
- **Data:** database, cache, message broker, storage.
- **Management:** control plane, admin endpoints, deployment.
- **Security/observability:** SIEM, monitoring, audit collectors.

Luồng giữa các vùng cần **allowlist theo source, destination, protocol và port**, có owner và lý do. Không nên dùng một quy tắc “allow all nội bộ” chỉ vì các subnet cùng VPC/VNet.

### 8.2. Network policy và identity-aware access

Network policy có thể kiểm soát pod/service theo namespace, label hoặc selector. Tuy nhiên label/config có thể bị thay đổi bởi principal có quyền. Cần:

- Bảo vệ quyền sửa network policy và namespace labels.
- Kiểm tra default-deny ingress/egress có thực thi.
- Xác minh traffic thực tế, không chỉ manifest.
- Kết hợp workload identity/mTLS và authorization ở service.
- Kiểm tra DNS, metadata endpoint, egress proxy và service discovery.
- Test từ workload không được phép, kể cả trong cùng subnet/cluster.

**mTLS xác thực peer và bảo vệ kênh**, nhưng không tự quyết định peer được phép đọc mọi dữ liệu hoặc gọi mọi action.

### 8.3. Egress và SSRF

Một service có quyền gọi mạng rộng có thể bị lợi dụng làm confused deputy hoặc SSRF proxy. Cần:

- Egress allowlist theo nhu cầu.
- Chặn hoặc giới hạn truy cập metadata/control endpoints.
- Kiểm tra redirect, DNS rebinding và địa chỉ IP sau resolve.
- Không tin URL do user cung cấp.
- Tách quyền fetch URL khỏi quyền đọc secret nội bộ.
- Giám sát destination mới và lượng dữ liệu outbound.
- Test IPv4/IPv6, redirect, hostname nội bộ và proxy behavior theo threat model.

## 9. Process, container, VM và plugin isolation

### 9.1. Container hardening

Các biện pháp thường được xem xét:

- Chạy non-root khi khả thi.
- Drop Linux capabilities không cần.
- Tránh privileged container.
- Hạn chế hostPath, host network và host PID.
- Dùng seccomp, AppArmor/SELinux hoặc cơ chế tương ứng.
- Read-only root filesystem nếu phù hợp.
- Giới hạn CPU, memory, process và ephemeral storage.
- Không mount Docker/container runtime socket vào workload không cần.
- Giới hạn quyền service account và secret mount.
- Kiểm soát image, provenance và patch level.

Cấu hình cụ thể tùy runtime và nền tảng. Một pod có runAsNonRoot vẫn có thể có host mount hoặc capability nguy hiểm nếu các control khác không được áp dụng.

### 9.2. VM và hypervisor

VM tạo boundary mạnh hơn một số mô hình container vì guest có kernel riêng, nhưng vẫn có rủi ro ở:

- Hypervisor và virtual device.
- Management API và orchestration.
- Shared storage/network.
- Guest agent và host integration.
- Snapshot, template và image.
- Admin credential và backup.

Không kết luận VM “không thể escape”. Cần xem threat model, patch, configuration, vendor advisories và bằng chứng kiểm tra.

### 9.3. Plugin và untrusted code

Nếu ứng dụng cho phép plugin hoặc script của người dùng:

- Ưu tiên process/VM sandbox riêng cho code không tin cậy.
- Expose API hẹp thay vì object host đầy quyền.
- Hạn chế filesystem, network, syscall và environment.
- Có CPU/memory/time quota và kill switch.
- Tách secret và identity của plugin khỏi host.
- Kiểm tra output trước khi host sử dụng.
- Giới hạn khả năng gọi plugin khác hoặc truy cập metadata.
- Có audit, versioning và kiểm tra nguồn plugin.

**Chỉ dùng language sandbox** có thể không đủ khi runtime cho phép native extension, reflection hoặc truy cập API host. Mức cô lập phải phù hợp threat model và implementation cụ thể.

## 10. Control plane, deployment và environment isolation

### 10.1. Tách quyền control plane

Cần xem:

- Tenant admin không có quyền sửa global IAM hoặc platform policy.
- Developer không mặc định đọc production secret.
- Pipeline staging không có credential deploy production.
- Người sửa policy không thể tự xóa audit trail.
- Support access được cấp theo case/time/scope.
- Admin API không lộ qua public route không cần thiết.
- Break-glass có approval, alert và hậu kiểm.

### 10.2. Tách dev, test, staging và production

Một số control:

- Tài khoản/cloud project/subscription riêng theo environment khi phù hợp.
- Secret, key và certificate tách biệt.
- Data test synthetic hoặc đã được phê duyệt, hạn chế dữ liệu production.
- Deployment role riêng, approval cho production.
- Network route và database endpoint tách.
- Không cho staging dùng production database bằng credential rộng.
- Kiểm soát backup/restore và dữ liệu được sao chép.
- CI/CD artifact promotion có integrity và approval.

Một environment tag trong tên resource không phải ranh giới nếu quyền và credential vẫn dùng chung.

## 11. Ví dụ Java/Spring Boot: tenant isolation cho Orders API

### 11.1. Bối cảnh

Một SaaS quản lý đơn hàng phục vụ nhiều tổ chức. Orders API chạy trên Java/Spring Boot và dùng một bảng orders chung, mỗi row có tenant_id.

**Security claim ISO-APP-01:**

> “Mọi thao tác đọc hoặc thay đổi đơn hàng chỉ được thực hiện khi tenant của đơn hàng khớp với tenant mà principal đã được xác minh có quyền truy cập; tenant ID do client tự khai không thể mở rộng phạm vi.”

**Security claim ISO-APP-02:**

> “Các worker, cache và đường quản trị không tạo ra đường bypass làm dữ liệu tenant này hiển thị hoặc bị sửa bởi tenant khác.”

### 11.2. Luồng tin cậy

~~~mermaid
flowchart LR
    U["Client"] --> GW["API Gateway / Authentication"]
    GW --> P["Verified Principal"]
    P --> T["Tenant Membership / Policy"]
    U --> API["Orders Controller"]
    T --> API
    API --> S["Order Application Service"]
    S --> R["Tenant-scoped Repository"]
    R --> DB[("Orders DB")]
    S --> CACHE["Tenant-aware Cache"]
    S --> AUDIT[("Audit Store")]
    Q["Validated Event"] --> W["Tenant-scoped Worker"]
    W --> R
~~~

Client có thể gửi tenant ID trong URL để chọn ngữ cảnh, nhưng backend phải xác minh membership và gắn context đáng tin. Repository và database policy là lớp bổ sung để giảm lỗi khi một endpoint quên filter.

### 11.3. Lấy tenant từ principal đã xác minh

Ví dụ domain model:

~~~java
public record VerifiedPrincipal(
        String subjectId,
        UUID activeTenantId,
        Set<String> authorities) {
}
~~~

VerifiedPrincipal phải được tạo sau khi xác minh token và membership theo kiến trúc. Không bind trực tiếp object này từ JSON request hoặc header tùy ý.

Một resolver minh họa:

~~~java
@Component
public class CurrentPrincipal {
    public VerifiedPrincipal require() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal()
                        instanceof VerifiedPrincipal principal)) {
            throw new AccessDeniedException("Verified principal required");
        }

        return principal;
    }
}
~~~

Ví dụ giả định authentication provider đã đặt VerifiedPrincipal sau khi kiểm tra issuer, audience, signature, expiry và membership. Trong hệ thống thực, cách mapping principal phụ thuộc cấu hình Spring Security; không được tin một object do controller/client tự tạo.

### 11.4. Tenant-scoped repository

~~~java
@Repository
public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {

    Optional<OrderEntity> findByIdAndTenantId(
            UUID orderId,
            UUID tenantId);

    Page<OrderEntity> findAllByTenantId(
            UUID tenantId,
            Pageable pageable);
}
~~~

Không cung cấp một phương thức truy vấn theo orderId cho các luồng tenant-scoped nếu caller có thể vô tình sử dụng mà không kiểm tra quyền. Có thể có use case quản trị riêng, nhưng cần authorization và audit khác biệt rõ.

Service minh họa:

~~~java
@Service
public class OrderQueryService {
    private final CurrentPrincipal currentPrincipal;
    private final OrderRepository repository;

    public OrderQueryService(
            CurrentPrincipal currentPrincipal,
            OrderRepository repository) {
        this.currentPrincipal = currentPrincipal;
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderView getOrder(UUID orderId) {
        VerifiedPrincipal principal = currentPrincipal.require();

        OrderEntity order = repository
                .findByIdAndTenantId(
                        orderId, principal.activeTenantId())
                .orElseThrow(ResourceNotFoundException::new);

        return OrderView.from(order);
    }
}
~~~

Việc trả 404 thay vì 403 có thể giảm lộ sự tồn tại của object trong một số API, nhưng phải nhất quán với thiết kế và không thay thế authorization. Cần cân nhắc audit và thông điệp lỗi để không tạo enumeration qua timing hoặc side channel.

### 11.5. Vì sao không tin tenant ID từ request?

Một anti-pattern:

~~~java
@GetMapping("/orders/{orderId}")
public OrderView getOrder(
        @PathVariable UUID orderId,
        @RequestHeader("X-Tenant-ID") UUID tenantId) {
    return orderService.getOrder(orderId, tenantId);
}
~~~

Nếu tenantId được dùng trực tiếp mà không xác minh membership, user có thể thay header để truy cập tenant khác. Nếu header chỉ là lựa chọn tenant, backend phải xác minh principal được phép chọn tenant đó rồi tạo context tin cậy.

### 11.6. Cache key có tenant scope

~~~java
public record OrderCacheKey(
        UUID tenantId,
        UUID orderId,
        String permissionVersion) {
}
~~~

Cache lookup phải sử dụng tenant từ principal đã xác minh. Nếu response phụ thuộc role/permission, cần đưa permission version hoặc cơ chế invalidation phù hợp. Không dùng orderId đơn lẻ nếu object ID có thể được truyền giữa tenant hoặc response có khác biệt theo quyền.

### 11.7. Database row-level security

Một database hỗ trợ Row-Level Security có thể thêm policy theo tenant context. Ví dụ PostgreSQL minh họa:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

Đây là ví dụ cấu hình, cần điều chỉnh theo phiên bản database và cách triển khai. Những điểm phải kiểm chứng:

- Role ứng dụng không phải superuser và không có quyền bypass RLS.
- Tenant context được thiết lập server-side sau xác minh principal.
- Context được reset đúng khi connection pool tái sử dụng connection.
- Transaction-local setting được dùng phù hợp để tránh rò context giữa request.
- Background job và migration có role/policy riêng, không vô tình chạy bằng quyền bỏ qua RLS.
- Mọi query, join, bulk update và function được kiểm tra trong phạm vi.

RLS là defense-in-depth; nếu connection context có thể bị giả mạo hoặc role ứng dụng có thể bypass policy, lớp bảo vệ này có thể mất tác dụng.

### 11.8. Async event cần giữ context đáng tin

Không lấy tenantId từ payload không được xác minh rồi cho worker truy vấn dữ liệu. Event nên được tạo bởi service tin cậy sau authorization, gắn subject/tenant, event ID và schema version. Consumer xác thực nguồn, kiểm tra tenant binding và dùng workload identity hẹp.

Với message queue, cần test:

- Event tenant A không thể yêu cầu worker đọc order B.
- Retry và dead-letter giữ nguyên context.
- Consumer không dùng một quyền admin toàn cục để bỏ qua tenant.
- Event cũ không còn hợp lệ khi membership/policy thay đổi nếu yêu cầu cần reauthorization.
- Audit ghi actor ban đầu, producer và consumer.

## 12. Kubernetes và cloud isolation

### 12.1. Namespace không tự là security boundary hoàn chỉnh

Namespace giúp tổ chức tài nguyên và là selector cho nhiều policy, nhưng cần kết hợp:

- RBAC giới hạn ai tạo/sửa workload, RoleBinding và Secret.
- NetworkPolicy ingress/egress default-deny.
- Pod Security Standards/admission policy phù hợp.
- Service account riêng và workload identity.
- ResourceQuota/LimitRange để giảm noisy neighbor.
- Secret scope và volume mount tối thiểu.
- Node pool/cluster riêng nếu threat/risk yêu cầu.
- Audit cho API server và control plane.

Nếu một principal có quyền cluster-admin, namespace separation có thể không bảo vệ tenant trước principal đó.

### 12.2. Ví dụ NetworkPolicy default-deny

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-by-default
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Policy này minh họa ý định mặc định chặn ingress/egress trong namespace với CNI hỗ trợ NetworkPolicy. Để service hoạt động, cần thêm allow rules chính xác cho DNS, gateway, database và dependency cần thiết. **Không coi việc manifest tồn tại là bằng chứng policy đang được CNI thực thi**; phải kiểm tra runtime traffic và nền tảng.

### 12.3. Resource isolation

ResourceQuota và limit có thể giới hạn CPU, memory, storage, số pod và object. Kiểm tra:

- Quota có áp dụng cho mọi namespace/tenant trong scope?
- Workload có thể tạo resource ngoài quota qua controller khác?
- Request/limit có phù hợp tải thực tế?
- Một tenant có thể gây queue, DB connection hoặc thread pool exhaustion?
- Autoscaling và shared node có tạo ảnh hưởng chéo?
- Có alert trước khi tenant khác bị ảnh hưởng?

Quota giúp availability isolation nhưng không thay network/data isolation.

## 13. Isolation trong cache, search, analytics và AI retrieval

### 13.1. Search và vector database

Khi nhiều tenant dùng chung search index hoặc vector store, query phải có **tenant filter bắt buộc** được gắn từ identity đã xác minh.

Kiểm tra:

- Filter được áp dụng ở server-side, không chỉ client.
- Mọi query path, reranking, fallback và hybrid search giữ filter.
- Index rebuild/backfill không trộn tenant.
- Cache embedding và retrieval result có tenant scope.
- Tool/plugin gọi search không thể bỏ filter.
- Kết quả trả ra được kiểm tra lại ownership khi phù hợp.

### 13.2. AI/RAG isolation

Một hệ thống RAG có thể lộ dữ liệu nếu retriever, vector index, prompt cache hoặc tool execution không giữ tenant context.

Các control cần xem:

- Tenant identity được xác minh ở request boundary.
- Retrieval filter được bắt buộc bởi backend.
- Context đưa vào model chỉ chứa dữ liệu caller có quyền.
- Prompt injection không thể yêu cầu tool truy xuất tenant khác.
- Conversation memory và cache tách theo user/tenant theo policy.
- Tool identity có scope hẹp, không dùng quyền admin toàn cục.
- Citation/source references không tiết lộ object ngoài phạm vi.
- Logging/telemetry không lưu prompt chứa dữ liệu nhạy cảm vượt yêu cầu.

**Prompt instruction không phải isolation boundary.** Ranh giới phải được thực thi ở retrieval, tool authorization, data store và service layer.

## 14. Kiểm thử isolation boundary

### 14.1. Nguyên tắc kiểm thử

Kiểm tra cả:

- **Allowed path:** chủ thể hợp lệ truy cập đúng tài nguyên được cấp.
- **Denied path:** chủ thể khác tenant/role/workload bị từ chối.
- **Boundary condition:** đổi ID, tenant, role, environment, resource hoặc token.
- **Bypass path:** gọi endpoint khác, worker, admin API, cache, export hoặc storage trực tiếp.
- **Failure mode:** identity/policy/network service unavailable.
- **Concurrency/race:** membership đổi trong lúc request, cache cũ hoặc event retry.
- **Runtime configuration:** cấu hình triển khai thực sự áp dụng.
- **Observability:** audit cho phép truy vết mà không làm lộ thêm dữ liệu.

### 14.2. Test matrix cho multi-tenant API

| Kịch bản | Kết quả kỳ vọng | Bằng chứng |
| --- | --- | --- |
| User A đọc order của tenant A | Allow | Positive authorization test |
| User A đọc order của tenant B | Deny/không tiết lộ nội dung | Cross-tenant negative test |
| User A sửa tenant ID trong header | Không mở rộng quyền | Header tampering test |
| User A gửi UUID hợp lệ của B | Deny | BOLA/IDOR test |
| User A gọi bulk export chứa B | Không có bản ghi B | Export scope test |
| Cache đã có response của B | User A không nhận response B | Cache isolation test |
| Async event A chứa resource B | Worker từ chối hoặc cách ly | Event binding test |
| Membership A bị thu hồi | Quyền cũ mất hiệu lực theo semantics | Revocation/cache test |
| API policy service lỗi | Không fail-open sang tenant mặc định | Failure-mode test |
| Support operator truy cập tenant A | Chỉ theo case/scope/time được duyệt | Privileged access test |
| Admin API từ tenant role | Deny | Control-plane separation test |
| Search/vector query | Không trả chunk tenant khác | Retrieval isolation test |
| RLS context bị thiếu | Query không trả dữ liệu ngoài scope | Database policy test |
| Connection pool tái sử dụng | Không giữ tenant context request trước | Pool/context leakage test |
| Worker retry/dead-letter | Không mất tenant binding | Async lifecycle test |

Một test 403 không đủ nếu request bị từ chối vì CSRF, validation hoặc lỗi không liên quan isolation. Cần kiểm tra **đúng policy path đã thực thi** và có positive test tương ứng.

### 14.3. Test matrix cho container/network boundary

| Kịch bản | Kết quả kỳ vọng | Bằng chứng |
| --- | --- | --- |
| Pod A kết nối service được phép | Allow đúng port/protocol | Connectivity test |
| Pod A kết nối database không được phép | Deny | NetworkPolicy runtime test |
| Pod không có quyền đọc Kubernetes Secret | Deny | RBAC negative test |
| Container thử mount host path trái policy | Admission từ chối | Admission policy test |
| Container thử chạy privileged | Bị từ chối theo baseline | Pod security test |
| Workload thử truy cập metadata endpoint | Bị chặn/giới hạn theo policy | SSRF/egress test |
| Service account staging đọc secret prod | Deny | Identity scope test |
| Tenant gây cạn quota | Bị giới hạn, tenant khác còn khả dụng trong tiêu chí | Load/fairness test |
| Network policy engine unavailable/drift | Phát hiện và xử lý theo thiết kế | Health/config drift evidence |

### 14.4. Kiểm thử theo thay đổi và fuzzing

Khi thay đổi router, repository, ORM, cache, queue hoặc network policy, cần regression tests. Fuzzing có thể hỗ trợ tìm trường hợp input không dự kiến, nhưng không thay thế kiểm tra quyền và threat model. Dynamic security testing cần được giới hạn trong môi trường được phép, tránh gây ảnh hưởng dịch vụ khác.

## 15. Bằng chứng assurance cho isolation boundary

### 15.1. Ba lớp đánh giá

| Lớp | Câu hỏi | Evidence |
| --- | --- | --- |
| **Design effectiveness** | Boundary có đặt đúng vị trí, giảm đúng threat và có đường kiểm soát rõ? | Architecture/DFD, threat model, trust boundary, policy design |
| **Implementation effectiveness** | Code, IAM, network, database, runtime và deployment có thực thi boundary? | Code/config review, IaC, RBAC/NetworkPolicy, RLS, integration tests |
| **Operating effectiveness** | Boundary có duy trì qua thời gian và thay đổi? | Runtime flow logs, audit, drift detection, access reviews, incident/retest |

Một diagram cho thấy subnet riêng chỉ là design evidence. Một YAML NetworkPolicy chỉ là configuration artifact. Muốn kết luận runtime isolation, cần bằng chứng CNI áp dụng, traffic thực tế và negative test.

### 15.2. Evidence cần gắn metadata

- Control ID, threat ID và security claim.
- Asset, tenant, principal, action, resource và boundary.
- Policy/config/code version, build và environment.
- Test run ID, test fixture, expected/actual result.
- Runtime event, flow log, audit correlation.
- Population, sampling method và phạm vi.
- Reviewer, thời điểm, confidence và giả định.
- Finding, owner, due date, remediation và retest.
- Những đường không kiểm tra hoặc ngoại lệ còn hiệu lực.

Không đưa dữ liệu tenant thật vào evidence nếu có thể dùng synthetic data hoặc reference được bảo vệ. Audit cần đủ để xác định actor/tenant/resource nhưng không tạo một kho dữ liệu nhạy cảm mới.

### 15.3. Trạng thái kết luận

- **Effective in assessed scope:** có bằng chứng đủ cho mục tiêu và boundary đã kiểm tra.
- **Partially effective:** một số lớp hoặc đường đạt, còn gap/coverage thiếu.
- **Ineffective:** có bằng chứng truy cập vượt boundary hoặc control không thực thi.
- **Insufficient evidence:** chưa đủ căn cứ kết luận.
- **Exception approved:** residual risk được phê duyệt theo thẩm quyền; không đồng nghĩa boundary đạt.
- **Not applicable:** có lý do được phê duyệt rằng control không áp dụng.

**Không có sự cố cross-tenant được báo cáo** không tự chứng minh tenant isolation hiệu quả. Detection có thể không quan sát được hoặc thiếu test.

## 16. KPI/KRI cho isolation assurance

| Chỉ số | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **Boundary inventory coverage** | Tỷ lệ boundary/luồng quan trọng đã được xác định | Inventory có thể bỏ sót đường gián tiếp |
| **Cross-tenant negative test coverage** | Các endpoint/operation có test từ chối tenant khác | Test coverage không tự chứng minh production |
| **Unauthorized access attempts denied** | Các lần truy cập trái scope bị chặn | Số thấp không có nghĩa rủi ro thấp |
| **Policy drift findings** | Cấu hình khác baseline | Cần đánh giá mức ảnh hưởng |
| **Overprivileged service identities** | Workload có quyền vượt nhu cầu | Một identity có thể có blast radius rất lớn |
| **Network rule coverage** | Luồng cần thiết được allow và luồng khác bị chặn trong scope | Manifest không chứng minh runtime |
| **Tenant cache isolation findings** | Số lỗi/thiếu tenant-aware key | Phụ thuộc coverage |
| **Async context integrity** | Event/worker giữ đúng tenant và actor context | Cần test retry và replay |
| **Resource fairness / noisy neighbor** | Một tenant có làm ảnh hưởng availability tenant khác | Phải định nghĩa workload và SLO |
| **Control-plane privilege review** | Quyền quản trị được review theo kỳ | Không chỉ đếm số admin |
| **Time to contain boundary breach** | Thời gian phát hiện và giới hạn ảnh hưởng | Cần định nghĩa mốc |
| **Verified remediation time** | Thời gian đến retest đạt | Ticket Done chưa đủ |
| **Evidence freshness** | Evidence phù hợp build/config hiện hành | Báo cáo cũ không đại diện runtime mới |

Ví dụ: trong 40 API operations có thể đọc hoặc sửa dữ liệu tenant, 34 operation đã có positive và cross-tenant negative tests được review; 4 operation mới chưa kiểm tra, 2 operation có finding. **Verified test coverage = 34/40 = 85%** trong population đã xác định. Không được diễn giải thành “tenant isolation an toàn 85%”; hai finding và bốn operation chưa kiểm tra cần được phân tích theo dữ liệu và tác động.

## 17. Quản trị finding, exception và response

### 17.1. Khi phát hiện boundary bị vượt

1. Xác định principal, tenant, resource, action và thời gian.
2. Bảo toàn audit/evidence phù hợp, không nhân bản dữ liệu nhạy cảm tùy tiện.
3. Giới hạn đường truy cập hoặc thu hồi credential theo thẩm quyền.
4. Xác định scope ảnh hưởng và các tenant/resource có thể liên quan.
5. Kiểm tra khả năng lateral movement, persistence và dữ liệu đã bị đọc/sửa.
6. Phối hợp incident response, privacy/legal và risk owner khi phù hợp.
7. Sửa root cause ở đúng boundary, không chỉ block một request cụ thể.
8. Test lại đường tấn công và các biến thể tương tự.
9. Theo dõi deployment/config drift và residual risk.

### 17.2. Phân loại gap

| Gap type | Ví dụ | Hành động |
| --- | --- | --- |
| **Identity gap** | Client tự khai tenant ID | Ràng buộc tenant với principal đã xác minh |
| **Authorization gap** | Query theo ID không kiểm tra owner | Object-level authorization và query scoping |
| **Data boundary gap** | RLS không bật hoặc role bypass | Sửa DB policy và test runtime |
| **Cache gap** | Cache key thiếu tenant | Tenant-aware key và invalidation |
| **Async gap** | Worker không kiểm tra context | Signed/validated event và consumer authorization |
| **Network gap** | Subnet nội bộ được allow all | Default-deny và allowlist |
| **Runtime gap** | Container privileged/host mount | Admission/hardening và rebuild |
| **Control-plane gap** | Tenant role có quyền platform | Tách admin plane và permission |
| **Availability gap** | Tenant gây noisy neighbor | Quota, backpressure, isolation tier |
| **Evidence gap** | Chỉ có sơ đồ, chưa có negative test | Bổ sung test và runtime evidence |
| **Operating gap** | Network policy drift không được phát hiện | Drift monitoring và response |

### 17.3. Ngoại lệ

Ngoại lệ phải có owner, lý do, scope, thời hạn, control bù trừ, phê duyệt và kế hoạch loại bỏ. Ví dụ một hệ thống cũ chưa thể tách database có thể được chấp nhận rủi ro có điều kiện nếu có các lớp kiểm soát bù trừ được kiểm chứng. Ngoại lệ không biến một ranh giới chưa đạt thành effective và không miễn trừ yêu cầu bắt buộc.

## 18. RACI và trách nhiệm

| Vai trò | Trách nhiệm | Giới hạn |
| --- | --- | --- |
| **Security architect** | Xác định trust boundary, threat, design và security requirements | Không tự chứng minh runtime |
| **Application owner** | Enforce tenant/resource authorization và data isolation | Không mặc định network/platform đã bảo vệ |
| **Platform/SRE owner** | Quản lý network, cluster, runtime, quota và control plane | Không thay logic nghiệp vụ của ứng dụng |
| **Identity/IAM owner** | Workload/user identity, role, token và trust policy | Không thay object-level authorization |
| **Database/data owner** | Schema/RLS, backup/restore, data scope và access | Phối hợp app owner về context |
| **Engineering** | Implement, test, sửa và cung cấp evidence | Merge code không tự đóng finding |
| **Risk owner** | Quyết định residual risk/exception trong thẩm quyền | Không thay technical validation |
| **Assurance/auditor** | Review evidence, scope, independence và kết luận | Không tự chịu trách nhiệm sửa control |
| **Incident response** | Containment, investigation và bảo toàn evidence | Theo quy trình và quyền được giao |

RACI minh họa:

| Hoạt động | Security architect | App owner | Platform/SRE | IAM/DB owner | Risk owner | Assurance |
| --- | --- | --- | --- | --- | --- | --- |
| Threat model và boundary design | **A/R** | C | C | C | C | C |
| Tenant authorization | C | **A/R** | I | C | I | C |
| Network/container isolation | C | C | **A/R** | C | I | C |
| Identity và database policy | C | C | C | **A/R** | I | C |
| Khắc phục application gap | C | **A/R** | C | C | I | C |
| Chấp nhận residual risk | C | C | C | C | **A/R** | I |
| Đánh giá độc lập | C | C | C | C | I | **A/R** |

Cần điều chỉnh theo cơ cấu thật và các yêu cầu separation of duties.

## 19. Mẫu hồ sơ isolation assurance

Mẫu YAML sau là dữ liệu giả định, chưa phải bằng chứng của hệ thống thực:

~~~yaml
assessment_id: "ISOLATION-ASSURANCE-DEMO-007"
control_id: "CTRL-TENANT-ISOLATION-01"
title: "Orders API tenant isolation"
service: "orders-api"
control_owner: "Orders API Technical Owner"
platform_owner: "Platform Engineering"
risk_owner: "Product Risk Owner"
policy_ref: "POL-MULTI-TENANT-ACCESS"
standard_ref:
  id: "STD-ISOLATION-BOUNDARIES"
  version: "demo-1.0"
scope:
  environment: "integration"
  build: "demo-build-not-verified"
  components:
    - "api"
    - "database"
    - "cache"
    - "event-worker"
security_claims:
  - "Tenant A cannot read or modify tenant B resources"
  - "Client supplied tenant identifiers cannot expand authority"
  - "Async workers preserve verified tenant context"
  - "Shared cache and search do not cross tenant boundaries"
evidence_plan:
  - "Cross-tenant positive and negative API tests"
  - "Repository and database policy review"
  - "Cache key and invalidation tests"
  - "Async event binding and replay tests"
  - "Network and runtime policy validation"
design_review: "PENDING"
implementation_review: "NOT_VERIFIED"
operating_review: "NOT_VERIFIED"
evidence_refs: []
assessment_conclusion: "INSUFFICIENT_EVIDENCE"
confidence: "LOW"
findings: []
next_action: "Execute cross-tenant and bypass test suite"
exception:
  approved: false
  approver: null
~~~

Hồ sơ thực cần build, thời gian, reviewer, test run, population, kết quả, runtime evidence, giới hạn và risk decision. Không đưa dữ liệu tenant thật vào YAML nếu reference được bảo vệ đã đủ.

## 20. Các sai lầm phổ biến

### 20.1. Tin tenant ID từ client

Client thay header/path để truy cập tenant khác.

**Khắc phục:** tenant context từ principal đáng tin, kiểm tra membership và object-level authorization.

### 20.2. Chỉ kiểm tra ở controller

Worker, scheduled job hoặc internal API có thể bypass.

**Khắc phục:** đặt authorization ở service/data boundary phù hợp, test mọi entry point.

### 20.3. Nghĩ container đồng nghĩa VM

Container thường chia sẻ kernel host và có thể được cấp capability/host mount rộng.

**Khắc phục:** hardening, sandbox theo threat model, tách VM/node khi rủi ro yêu cầu.

### 20.4. Coi subnet nội bộ là đáng tin

Lateral movement có thể xảy ra giữa workload cùng mạng.

**Khắc phục:** default-deny, identity-aware service access và allowlist.

### 20.5. RLS bật là xong

Superuser/bypass role, session context sai hoặc connection pool có thể làm policy mất hiệu lực.

**Khắc phục:** kiểm tra role thực, transaction context, pool reuse và negative tests.

### 20.6. Cache chỉ dùng object ID

Response của tenant A có thể được trả cho tenant B.

**Khắc phục:** cache key và invalidation theo tenant/permission context.

### 20.7. Async làm mất tenant context

Message thiếu tenant binding hoặc worker dùng service account quá rộng.

**Khắc phục:** explicit verified context, event integrity, consumer authorization và audit.

### 20.8. Namespace là ranh giới tuyệt đối

Cluster admin hoặc policy thiếu có thể vượt namespace.

**Khắc phục:** RBAC, network policy, admission, service account, secret và node controls.

### 20.9. Tách data plane nhưng bỏ control plane

Tenant admin có thể sửa IAM, policy hoặc pipeline chung.

**Khắc phục:** tách quyền và API quản trị, audit và approval.

### 20.10. Không xét noisy neighbor

Một tenant có thể gây ảnh hưởng availability toàn hệ thống.

**Khắc phục:** quota, rate limit, backpressure, pool partitioning và load tests.

### 20.11. Sơ đồ kiến trúc được coi là bằng chứng runtime

Manifest hoặc diagram không chứng minh rule thực thi.

**Khắc phục:** runtime connectivity tests, audit, drift monitoring và negative tests.

### 20.12. Không kiểm tra restore và downstream

Backup, search index, analytics và event replay có thể tái tạo dữ liệu sai tenant.

**Khắc phục:** test restore, rebuild, replay và reconciliation theo tenant.

## 21. Checklist thiết kế và đánh giá Isolation boundary

- [ ] Đã xác định asset, tenant, principal, workload và ranh giới tin cậy.
- [ ] Có DFD/architecture view và data/control plane separation.
- [ ] Threat model gồm spoofing, tampering, disclosure, DoS và privilege escalation.
- [ ] Tenant context được lấy từ identity đã xác minh.
- [ ] Client không thể tự mở rộng quyền bằng header, path hoặc body.
- [ ] Mọi endpoint/object operation có object-level authorization.
- [ ] Database query, RLS/schema/database boundary được kiểm tra.
- [ ] Connection pool không giữ tenant context giữa request.
- [ ] Cache key và invalidation giữ đúng tenant/permission scope.
- [ ] Search/vector/analytics filter được enforce server-side.
- [ ] Event/worker giữ tenant context và được reauthorize khi cần.
- [ ] Service identity riêng và least privilege.
- [ ] Network ingress/egress default-deny theo khả năng nền tảng.
- [ ] Metadata endpoint, SSRF và egress được kiểm soát.
- [ ] Container/VM/plugin có isolation và runtime hardening phù hợp.
- [ ] Kubernetes RBAC, NetworkPolicy, admission, quota và secret mount được review.
- [ ] Control plane, admin API, CI/CD và production credentials được tách.
- [ ] Shared resource có quota/fairness và giám sát noisy neighbor.
- [ ] Backup/restore/replay không làm mất tenant isolation.
- [ ] Có positive, negative, boundary, bypass, race và failure-mode tests.
- [ ] Bằng chứng gắn policy/config/build/environment/test run và reviewer.
- [ ] Audit có actor, tenant, action, resource và correlation nhưng không lộ dữ liệu quá mức.
- [ ] Findings có owner, deadline, risk treatment và retest.
- [ ] Ngoại lệ có scope, approver, thời hạn và control bù trừ.
- [ ] Kết luận nêu rõ coverage, confidence, giới hạn và residual risk.
- [ ] Có trigger review khi đổi tenant model, data store, cache, queue, network hoặc identity.

Checklist hỗ trợ tổ chức công việc; đánh dấu đủ ô không thay thế kiểm thử trên hệ thống và cấu hình thực tế.

## 22. Câu hỏi tự kiểm tra

1. Isolation boundary khác trust boundary và network segmentation thế nào?
2. Vì sao một API có authentication vẫn có thể lộ dữ liệu tenant khác?
3. Tại sao tenant ID do client gửi không được coi là bằng chứng authorization?
4. Phân biệt shared logical isolation, database per tenant và dedicated workload.
5. Một service account có quyền đọc tất cả tenant tạo ra confused deputy như thế nào?
6. Vì sao cache key chỉ gồm object ID có thể gây cross-tenant data leak?
7. RLS có thể bị vô hiệu hóa hoặc áp sai trong những tình huống nào?
8. Connection pool tái sử dụng có thể làm rò tenant context ra sao?
9. Async worker cần những metadata và kiểm tra nào để giữ isolation?
10. Container khác VM ở ranh giới kernel và threat model thế nào?
11. Namespace trong Kubernetes cần kết hợp với control nào?
12. mTLS có đủ để cho phép mọi service gọi mọi API không? Vì sao?
13. Network default-deny có thay thế object-level authorization không?
14. Control plane và data plane khác nhau ở tác động bảo mật nào?
15. Một tenant làm cạn tài nguyên chung là lỗi confidentiality hay availability isolation?
16. Search/vector/RAG cần kiểm tra gì để tránh retrieval chéo tenant?
17. Vì sao prompt instruction không phải isolation boundary?
18. Một 403 trong negative test có đủ chứng minh isolation không? Cần kiểm tra thêm gì?
19. Những bằng chứng nào cho thấy NetworkPolicy đang thực thi ở runtime?
20. Khi nào nên chọn dedicated infrastructure thay logical isolation?
21. Sau khi sửa một lỗi BOLA, những đường bypass nào cần retest?
22. Làm sao chứng minh một ngoại lệ isolation không mở rộng blast radius ngoài thời hạn?

## 23. Tổng kết

**Isolation boundary** là cơ chế giới hạn cách danh tính, tenant, workload và vùng dữ liệu tương tác với tài nguyên ngoài phạm vi được phép. Thiết kế hiệu quả cần nhận diện đúng trust boundary, threat và blast radius; kết hợp **identity, object-level authorization, data isolation, cache/async context, network segmentation, process/container/VM, control-plane separation và resource quotas**. Không một lớp đơn lẻ như subnet riêng, container, namespace hay RLS tự bảo đảm cô lập end-to-end. Trong **SECURITY_SECURITY_ASSURANCE**, mỗi ranh giới phải được gắn với **security claim, test cho đường hợp lệ và đường bị từ chối, kiểm tra bypass/failure, runtime evidence, finding và retest**. Kết luận cần nêu rõ hệ thống, tenant, workload, environment và thời kỳ đã đánh giá, cùng những đường chưa được xác minh và residual risk. Khi kiến trúc, tenant model, service identity hoặc data flow thay đổi, isolation assurance cũng phải được đánh giá lại.
