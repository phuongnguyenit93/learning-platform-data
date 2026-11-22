# Phân vùng theo địa lý và yêu cầu lưu trú dữ liệu

Một nền tảng cloud phục vụ người dùng ở nhiều quốc gia thường muốn đặt ứng dụng gần người dùng để giảm latency, tăng khả năng phục hồi và mở rộng thị trường. Tuy nhiên, dữ liệu không chỉ đi theo request tới application. Nó có thể được ghi vào database, cache, object storage, backup, log, trace, analytics, support system và dịch vụ của bên thứ ba. Nếu một nhóm dữ liệu phải được lưu hoặc xử lý trong một phạm vi địa lý nhất định, kiến trúc cần kiểm soát toàn bộ những luồng này, không chỉ vị trí của database chính.

**Data residency** nói về nơi dữ liệu được lưu trữ hoặc xử lý theo phạm vi địa lý. **Data sovereignty** nói về quyền tài phán và thẩm quyền pháp lý có thể áp dụng đối với dữ liệu, tổ chức hoặc nhà cung cấp. **Data localization** thường chỉ yêu cầu dữ liệu thuộc phạm vi nhất định phải được lưu, xử lý hoặc giữ trong một quốc gia/vùng được chỉ định. Các khái niệm có liên quan nhưng không đồng nghĩa; yêu cầu thực tế phải được xác định theo loại dữ liệu, mục đích xử lý, vai trò của tổ chức và luật áp dụng.

Bài học này thuộc chương **Kiến trúc toàn cầu** của module **CLOUD_ARCHITECTURE**. Module tập trung thiết kế kiến trúc cloud từ yêu cầu nghiệp vụ tới lựa chọn network, compute, data và mô hình triển khai, đồng thời đánh giá đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected. Bài học này hướng dẫn cách phân vùng theo địa lý, xác định data boundary, chọn home region, kiểm soát replication/cross-border transfer và bảo đảm cả backup, telemetry, support cùng các dependency tuân theo yêu cầu lưu trú.

## 1. Vì sao cần phân vùng dữ liệu theo địa lý?

Một hệ thống có thể có user ở nhiều khu vực nhưng không phải mọi dữ liệu đều có cùng yêu cầu. Ví dụ nền tảng đặt chỗ:
- Hồ sơ khách hàng có thể chịu yêu cầu lưu trú hoặc giới hạn chuyển ra nước ngoài.
- Booking và payment record có thể chịu yêu cầu lưu trữ, truy cập và audit riêng.
- Ảnh phòng/cơ sở lưu trú có thể là nội dung ít nhạy cảm hơn.
- Log bảo mật có thể chứa IP, user identifier hoặc thông tin truy cập.
- Metric tổng hợp có thể được dùng toàn cầu nếu đã loại bỏ hoặc giảm khả năng nhận diện theo policy.
- Backup có thể phải giữ cùng khu vực với dữ liệu gốc.
- Dữ liệu support có thể được truy cập bởi nhân viên ở quốc gia khác.

Nếu chỉ chọn một region cho toàn bộ hệ thống, nhóm có thể gặp latency cao hoặc không đáp ứng yêu cầu pháp lý. Nếu nhân bản mọi dữ liệu sang tất cả region, hệ thống có thể vi phạm boundary, tăng bề mặt tấn công và tạo chi phí transfer/replication lớn.

Phân vùng địa lý nhằm trả lời:
1. Dữ liệu nào được phép lưu ở region nào?
2. Dữ liệu nào được phép xử lý hoặc truy cập từ đâu?
3. Có thể chuyển dữ liệu tới support, analytics, observability hoặc provider khác không?
4. Backup, replica, cache, search index và log có cùng phạm vi kiểm soát không?
5. User/tenant được gắn với region nào và ai có quyền thay đổi?
6. Khi failover, dữ liệu có được chuyển sang region khác hay phải duy trì trong cùng jurisdiction?
7. Có thể xóa, export hoặc cung cấp dữ liệu theo yêu cầu mà vẫn giữ tính nhất quán toàn cầu không?

~~~mermaid
flowchart TB
    USER["Users / tenants"] --> ROUTER["Global entry and policy router"]
    ROUTER --> RA["Region A cell"]
    ROUTER --> RB["Region B cell"]
    RA --> DA[("Regional data A")]
    RB --> DB[("Regional data B")]
    RA --> GA["Local backup / logs / keys"]
    RB --> GB["Local backup / logs / keys"]
    RA -. "Approved aggregate only" .-> GLOBAL["Global analytics / control"]
    RB -. "Approved aggregate only" .-> GLOBAL
~~~

## 2. Phân biệt residency, sovereignty và localization

| Khái niệm | Câu hỏi chính | Ví dụ yêu cầu |
|---|---|---|
| **Data residency** | Dữ liệu được lưu ở vị trí địa lý nào? | Database và backup phải đặt trong một khu vực xác định |
| **Data sovereignty** | Luật/quyền tài phán nào có thể áp dụng lên dữ liệu hoặc nhà cung cấp? | Xem xét quyền truy cập theo luật quốc gia và hợp đồng |
| **Data localization** | Có bắt buộc giữ hoặc xử lý dữ liệu trong lãnh thổ cụ thể không? | Một nhóm dữ liệu không được chuyển ra khỏi quốc gia |
| **Data transfer restriction** | Khi nào và theo cơ chế nào dữ liệu được chuyển qua biên giới? | Chỉ chuyển một số loại dữ liệu sau đánh giá và bảo vệ |
| **Data access boundary** | Ai có thể truy cập dữ liệu và từ địa điểm nào? | Support ở nước khác cần approval và audit |

Không nên suy luận rằng dữ liệu được lưu trong một region thì chắc chắn chỉ chịu luật của region đó. Nhà cung cấp, tổ chức kiểm soát dữ liệu, nhà thầu phụ, nơi nhân viên truy cập và các cơ chế chuyển giao có thể ảnh hưởng tới phân tích pháp lý. Đây là bài toán cần legal/privacy owner xác nhận, không thể quyết định chỉ bằng sơ đồ cloud.

### 2.1. Data residency không chỉ là database location

Một record có thể xuất hiện trong:
- Primary database và read replica.
- Cache và session store.
- Object storage và CDN cache.
- Search index và materialized view.
- Queue, event stream và dead-letter queue.
- Backup, snapshot và point-in-time log.
- Application log, audit log, trace và crash dump.
- Analytics warehouse, data lake và notebook.
- Support export, ticket attachment và local download.
- Dịch vụ SaaS hoặc API bên thứ ba.

Mỗi bản sao có thể có lifecycle và access path riêng. Data map phải ghi cả primary, secondary, ephemeral copy, backup và derived data.

## 3. Bắt đầu từ phân loại dữ liệu và mục đích xử lý

Không thể chọn region trước khi hiểu dữ liệu. Hãy phân loại theo sensitivity, business criticality, legal category, retention và mục đích sử dụng.

Ví dụ:

| Nhóm dữ liệu | Ví dụ | Cần đánh giá |
|---|---|---|
| Public content | Mô tả phòng, ảnh công khai | CDN, cache, license và integrity |
| Account/profile | Tên, contact, địa chỉ | PII, access, residency, deletion |
| Transaction | Booking, invoice, payment reference | Financial record, retention, audit |
| Authentication | Credential metadata, session, auth event | Security, secret, log access |
| Sensitive support | Ticket, attachment, identity document | Support location, subprocessor, export |
| Telemetry | IP, device ID, trace attributes | Re-identification, minimization, region |
| Derived analytics | Aggregated demand, conversion | Anonymization/pseudonymization, joins |
| ML data | Feature, training sample, model artifact | Source lineage, memorization, model access |

### 3.1. Phân loại theo khả năng nhận diện

Tên, email hoặc số điện thoại là identifier trực tiếp. IP, device ID, geolocation, event timestamp hoặc combination của nhiều field có thể nhận diện gián tiếp khi liên kết với dữ liệu khác. Hashing một identifier không tự động làm dữ liệu trở thành anonymous.

Cần ghi:
- Direct identifiers.
- Quasi-identifiers.
- Sensitive attributes.
- Free text và attachment.
- Derived/inferred attributes.
- Data subject/tenant linkage key.
- Mức độ có thể tái nhận diện sau aggregation.

### 3.2. Data purpose và lifecycle

Cùng một trường dữ liệu có thể được sử dụng cho nhiều mục đích: thực hiện booking, chống gian lận, hỗ trợ khách hàng, analytics hoặc marketing. Mỗi mục đích có thể có căn cứ, quyền truy cập, retention và transfer boundary khác nhau.

Tách purpose khi cần giúp:
- Giảm lượng dữ liệu copy vào hệ analytics.
- Đặt retention riêng cho support export.
- Giới hạn ai có thể đọc thông tin định danh.
- Xóa hoặc de-link dữ liệu khi mục đích kết thúc.
- Phân biệt dữ liệu transaction cần giữ với dữ liệu tạm có thể xóa.

## 4. Xây dựng data flow map và residency matrix

Một data flow map cần cho thấy dữ liệu bắt đầu ở đâu, đi qua service nào, được lưu ở đâu, ai truy cập và đi ra ngoài bằng đường nào.

### 4.1. Ví dụ data flow của Booking Platform

~~~mermaid
flowchart LR
    U["Customer in Country A"] --> EDGE["Regional edge / gateway"]
    EDGE --> API["Booking API - Region A"]
    API --> DB[("Customer and booking DB - A")]
    API --> OBJ[("Documents - A")]
    API --> Q[("Regional event stream - A")]
    Q --> ANALYTICS["Approved transformation"]
    ANALYTICS --> AGG["Minimized aggregate"]
    AGG --> GLOBAL["Global reporting"]
    API --> PAY["Payment provider"]
    API --> SUPPORT["Support platform"]
~~~

Các mũi tên sang payment, analytics hoặc support là điểm cần kiểm tra transfer và access. Không được mặc định vì destination là SaaS hoặc dịch vụ nội bộ nên dữ liệu được phép chuyển.

### 4.2. Residency matrix

| Data class | Primary location | Replica/backup | Processing/access | Cross-border rule |
|---|---|---|---|---|
| Public catalog | Region phục vụ nội dung | Có thể global CDN | Public read | Theo license và cache policy |
| Customer profile | Home region của tenant | Backup trong boundary đã duyệt | Service và support theo quyền | Chỉ theo cơ chế được phê duyệt |
| Booking ledger | Region sở hữu transaction | DR location theo policy | Booking/payment services | Kiểm tra legal và recovery constraints |
| Security audit | Regional audit store | Archive ở boundary được duyệt | Security team theo case | Redact/minimize và transfer review |
| Aggregate analytics | Global analytics zone nếu được phép | Theo retention | Analyst/BI | Chỉ dữ liệu đã xử lý theo policy |
| Temporary cache | Cùng region với source | Có thể không replicate | Application runtime | TTL và tránh chứa dữ liệu vượt mức cần thiết |

Ma trận cần là tài liệu sống, có owner, version, approval và ngày review. Nó không phải một lần ghi rồi bỏ quên; thay đổi service, provider hoặc subprocessor có thể tạo luồng dữ liệu mới.

## 5. Chọn mô hình phân vùng: theo region, tenant, cell hay data domain

### 5.1. Region-per-tenant / home region

Mỗi tenant hoặc nhóm tenant được gán một home region. Request được định tuyến về region này để đọc/ghi dữ liệu authoritative.

Ưu điểm:
- Data ownership rõ ràng.
- Dễ áp dụng residency policy theo tenant.
- Giảm cross-region write và conflict.
- Có thể chọn region theo hợp đồng/địa lý.

Đánh đổi:
- Cần quản lý tenant-to-region mapping.
- Tenant chuyển region là migration phức tạp.
- Traffic ở region home có thể lệch tải.
- Global feature cần tổng hợp dữ liệu qua boundary.
- Support và admin tool phải hiểu tenant context.

### 5.2. Regional cell architecture

Mỗi cell là một nhóm hạ tầng tương đối độc lập: gateway, application, database, queue, cache, observability và policy. Tenant được đặt vào một cell/region. Một lỗi hoặc thay đổi có thể giới hạn trong cell thay vì tác động toàn bộ nền tảng.

~~~mermaid
flowchart TB
    G["Global routing / tenant directory"] --> C1["Cell A"]
    G --> C2["Cell B"]
    G --> C3["Cell C"]
    C1 --> D1[("Data A")]
    C2 --> D2[("Data B")]
    C3 --> D3[("Data C")]
    C1 -.-> AGG["Approved aggregate plane"]
    C2 -.-> AGG
    C3 -.-> AGG
~~~

Cell architecture hỗ trợ blast-radius isolation và residency, nhưng nhân bản control/operations có thể tăng chi phí. Các shared service toàn cầu như identity, DNS, deployment và support access vẫn cần được xem xét.

### 5.3. Data domain partition

Có thể phân vùng theo loại dữ liệu hoặc bounded context:
- Transaction database theo tenant home region.
- Public media ở object storage/CDN toàn cầu.
- Analytics dùng bản aggregate đã giảm định danh.
- Security audit giữ theo region và policy.
- Feature store theo nơi xử lý và mục đích.

Cách này linh hoạt nhưng một workflow có thể đi qua nhiều data domain/region. Phải định nghĩa data contract, source of truth và transfer semantics.

### 5.4. So sánh lựa chọn

| Mô hình | Phù hợp khi | Đánh đổi chính |
|---|---|---|
| Một region trung tâm | Phạm vi pháp lý đơn giản, traffic tập trung | Latency và single-region dependency |
| Multi-region cùng chia sẻ data plane | Cần user proximity, data được phép phân tán | Cross-region consistency và transfer |
| Home region per tenant | Residency và ownership theo tenant | Tenant placement/migration |
| Regional cells | Isolation và blast-radius là ưu tiên | Platform duplication và vận hành |
| Hybrid theo data domain | Các loại dữ liệu có rule khác nhau | Data flow và governance phức tạp |

## 6. Global control plane và regional data plane

Một mô hình thường dùng là tách:
- **Global control plane:** quản lý tenant directory, deployment intent, policy catalog, routing metadata và fleet governance.
- **Regional data plane:** xử lý request, transaction và dữ liệu thuộc region.

Tuy nhiên, control plane toàn cầu không nên trở thành đường truy cập mặc định tới mọi dữ liệu tenant. Global directory chỉ cần giữ metadata tối thiểu để định tuyến, ví dụ tenant ID, home region, service tier và trạng thái routing; không nên chứa bản sao hồ sơ khách hàng nếu không cần.

~~~mermaid
flowchart TB
    ADMIN["Platform operators"] --> CP["Global control plane"]
    CP --> DIR[("Tenant-to-region directory")]
    CP --> DEP["Regional deployment controllers"]
    USER["Customer request"] --> EDGE["Global entry"]
    EDGE --> DIR
    DIR --> ROUTE["Route to home region"]
    ROUTE --> DP1["Regional data plane A"]
    ROUTE --> DP2["Regional data plane B"]
    DP1 --> DATA1[("A data boundary")]
    DP2 --> DATA2[("B data boundary")]
~~~

### 6.1. Rủi ro của global plane

- Tenant mapping bị sửa sai có thể định tuyến dữ liệu tới region không phù hợp.
- Một admin global có thể có quyền quá rộng.
- Global telemetry có thể nhận PII từ mọi region.
- Control plane outage có thể chặn provisioning hoặc failover.
- Deployment pipeline có thể triển khai cùng policy sai vào tất cả region.

Biện pháp:
- Metadata minimization.
- Signed/versioned routing policy.
- Least privilege theo region/cell.
- Approval cho tenant migration và residency override.
- Local cached routing metadata có TTL và integrity.
- Regional operation tiếp tục trong giới hạn khi global control plane unavailable.
- Audit riêng cho thao tác cross-region administration.

## 7. Routing và tenant placement

Routing cần sử dụng policy đã được kiểm chứng. Đừng suy region từ IP của user cho mọi request; người dùng có thể đi roaming, dùng VPN hoặc đại diện cho tenant có home region cố định.

### 7.1. Tenant directory

Directory có thể lưu:
- Tenant ID.
- Home region/cell.
- Data classification/policy profile.
- Placement status: active, migrating, restricted.
- Version/epoch của mapping.
- Allowed failover region set.
- Reference tới contract/approval thay vì chứa legal document.
- Timestamp và actor của thay đổi.

Không nên cho application client tự gửi region để chọn nơi ghi dữ liệu. Backend phải xác thực tenant và tra routing policy phía server.

### 7.2. Region migration

Khi tenant cần chuyển home region:
1. Xác định legal/business approval và data inventory.
2. Chọn destination nằm trong boundary được phép.
3. Kiểm tra dependency, quota, keys và service availability.
4. Thiết kế full copy và incremental change capture.
5. Giữ source là authoritative trong giai đoạn copy.
6. Kiểm tra checksum, record count và business invariants.
7. Chọn cutover window, dừng hoặc buffer writes.
8. Đồng bộ final delta và chuyển ownership.
9. Cập nhật directory với version/epoch mới.
10. Chuyển traffic và quan sát.
11. Giữ source read-only trong migration retention window.
12. Xóa source theo policy sau khi legal, operational và reconciliation checks hoàn tất.

Không cập nhật directory sang region mới trước khi dữ liệu và dependency sẵn sàng. Nếu source và destination cùng nhận write, có thể tạo hai nguồn authoritative.

## 8. Replication và cross-border data transfer

Replication là một data transfer operation. Nó cần được đánh giá theo residency, purpose, security, access và retention giống như request đọc dữ liệu.

### 8.1. Replication types

- **Synchronous replication:** giảm khả năng mất dữ liệu đã commit theo semantics của engine, nhưng tăng phụ thuộc latency và availability giữa các failure domains.
- **Asynchronous replication:** giảm độ trễ write, nhưng replica có thể lag và failover có RPO lớn hơn 0.
- **Logical replication/CDC:** chọn table/event cần đồng bộ, có thể lọc hoặc transform nhưng phải giữ semantics và lineage.
- **Object replication:** sao chép file/version/metadata; cần xem encryption key, ACL và delete marker.
- **Aggregate export:** chỉ chuyển dữ liệu đã giảm định danh cho analytics nếu policy cho phép.

Không dùng replication như giải pháp mặc định cho mọi dữ liệu. Có thể một loại data chỉ cần backup tại chỗ, một loại khác có thể được tổng hợp toàn cầu, một loại không được chuyển ra khỏi home region.

### 8.2. Transfer review

Trước khi bật replication hoặc export, trả lời:
- Data class nào được gửi?
- Source và destination ở jurisdiction nào?
- Ai là controller/processor hoặc vai trò tương ứng?
- Purpose và legal/contract basis đã được xác nhận chưa?
- Có subprocessor nào nhận dữ liệu?
- Encryption và key custody ra sao?
- Có transfer mechanism/contractual safeguard cần áp dụng không?
- Retention và deletion được thực hiện ở cả hai đầu thế nào?
- Có thể giảm field hoặc aggregate trước transfer không?
- Audit event nào chứng minh ai bật và sử dụng luồng transfer?

Đánh giá pháp lý cụ thể do legal/privacy owner thực hiện. Kiến trúc sư cần cung cấp data flow, destination, access path và technical controls để quyết định có cơ sở.

## 9. Backup, snapshot và disaster recovery trong boundary địa lý

Yêu cầu residency có thể giới hạn vị trí backup hoặc bản sao DR. Một thiết kế multi-region DR thông thường không mặc nhiên được phép replicate dữ liệu sang mọi region.

Các lựa chọn:
- Backup trong cùng region, tách account/project.
- Backup trong cùng country/jurisdiction nhưng khác failure domain.
- Cross-region copy sang một region được phê duyệt trước.
- Backup mã hóa với key được quản lý theo boundary.
- Logical backup/portable export được lưu ở nơi được phép.
- Rebuild từ nguồn dữ liệu tại chỗ nếu có thể.

### 9.1. RTO/RPO và residency có thể xung đột

Nếu region DR gần nhất nằm ngoài permitted boundary, không thể tự động failover dữ liệu nhạy cảm sang đó chỉ vì cần giảm RTO. Business owner cần chọn một phương án được phép:
- Multi-AZ trong cùng boundary.
- Một region DR khác nằm trong boundary.
- Degraded mode hoặc read-only service.
- Backup/restore trong cùng jurisdiction với RTO dài hơn.
- Rebuild service từ dữ liệu local và chấp nhận một phần chức năng gián đoạn.

Cần ghi rõ RTO/RPO khả thi trong giới hạn residency, không đặt mục tiêu vượt khả năng pháp lý/kỹ thuật.

### 9.2. Backup và key

Backup chỉ hữu ích nếu có thể decrypt trong recovery. Key access cần có ở destination theo policy, nhưng không sao chép private key hoặc cấp quyền decrypt toàn cầu tùy tiện. Kiểm tra:
- Key region và replication support.
- IAM/workload identity tại DR site.
- Key rotation và backup key version.
- Recovery access và break-glass.
- Data residency của key metadata/audit.
- Quy trình key revocation khi compromise.

## 10. CDN, cache và edge data

CDN/cache có thể đưa dữ liệu tới vị trí gần người dùng, nhưng không phải mọi data type đều phù hợp với global caching.

Có thể phù hợp:
- Ảnh và tài nguyên public.
- Nội dung không gắn với danh tính.
- Static asset có version và integrity.
- Data aggregate đã được phê duyệt.

Cần thận trọng với:
- Profile, booking, invoice và document riêng tư.
- Auth token, session và personal preference.
- Response có PII hoặc tenant-specific data.
- Data có yêu cầu deletion/retention nghiêm ngặt.

Cache key cần bao gồm các yếu tố phân quyền/tenant khi cần. Không cache response nhạy cảm vào shared CDN chỉ vì có thể tăng hit ratio. Dùng cache-control, private/no-store, signed access, TTL và invalidation theo data classification. Kiểm tra cả edge log và origin log vì telemetry của CDN có thể lưu IP, header hoặc URL chứa identifier.

## 11. Logs, metrics, traces và security telemetry

Observability thường là luồng bị bỏ sót trong thiết kế residency. Một API có thể chỉ trả một ID nhưng log/trace lại chứa email, IP, query parameter, document URL hoặc body.

### 11.1. Thiết kế telemetry theo vùng

- Thu thập log/trace trong region trước.
- Redact và minimize ở collector gần source.
- Giữ security/audit event theo jurisdiction/policy.
- Chỉ export metric aggregate/low-cardinality nếu được phép.
- Phân biệt metadata vận hành với nội dung dữ liệu.
- Kiểm soát quyền analyst support theo region và case.
- Đặt archive/backup telemetry theo retention và residency.
- Kiểm soát access log của CDN, WAF, DNS, API gateway và SaaS.

Không cho rằng metric không phải personal data chỉ vì nó là số. Label chứa tenant ID, user ID, URL hoặc email có thể làm metric thành dữ liệu nhận diện được.

### 11.2. Global observability

Có thể tập trung dashboard toàn cầu mà không tập trung raw logs. Ví dụ mỗi region gửi:
- Availability/error rate aggregate.
- Latency histogram tổng hợp.
- Resource utilization.
- Queue age.
- Deployment version và incident reference.
- Security finding count theo severity.

Nếu cần điều tra chi tiết, analyst truy cập regional log store theo quyền và case. Cách này giảm cross-border raw data movement nhưng vẫn giữ khả năng quan sát hoạt động toàn hệ thống.

## 12. Analytics, data lake và machine learning

Analytics và ML thường cần dữ liệu tổng hợp từ nhiều thị trường, nhưng không phải lúc nào cũng cần raw personal data.

Các pattern:
- **In-region processing:** dữ liệu thô được xử lý trong region; chỉ output được phê duyệt mới rời đi.
- **Aggregation:** chuyển số đếm, histogram hoặc summary theo cohort đủ lớn.
- **Pseudonymization:** thay identifier trực tiếp bằng key/token có kiểm soát; vẫn có thể là dữ liệu cá nhân nếu tái liên kết được.
- **Federated query:** query tại nơi dữ liệu cư trú, chỉ trả kết quả theo policy.
- **Federated learning:** model training phân tán với cập nhật được tổng hợp; không tự động loại bỏ privacy risk.
- **Regional model serving:** inference gần dữ liệu, tránh export raw feature.
- **Global model artifact:** chuyển model đã kiểm định nhưng cần xem model có memorization hoặc data leakage không.

### 12.1. Derived data vẫn cần quản trị

Feature, embedding, score, model artifact và analytics table có thể chứa hoặc suy ra thông tin từ dữ liệu gốc. Trước khi xem chúng là “an toàn để chuyển”, đánh giá:
- Có thể reverse/lookup lại người dùng hoặc record không?
- Có chứa rare combination hoặc sensitive attribute không?
- Có thể trích xuất training data từ model không?
- Retention và deletion của derived data ra sao?
- Có lineage tới dataset nguồn để thực hiện correction/deletion không?

Không mặc định model đã train xong là hoàn toàn tách khỏi yêu cầu dữ liệu nguồn. Cần governance theo use case và luật áp dụng.

## 13. Support, human access và nhà thầu phụ

Ngay cả khi database nằm trong region, nhân viên hoặc support vendor ở nước khác có thể xem record qua console/API. Đây là một access path cần được đánh giá riêng.

Kiểm soát:
- Role-based access và purpose limitation.
- Just-in-time elevation, approval và session expiry.
- Masking hoặc field-level redaction.
- Regional support team hoặc follow-the-sun với access policy rõ.
- Customer consent/contractual restriction nếu áp dụng.
- Audit mọi query, view, export và download nhạy cảm.
- Break-glass có thời hạn và review hậu kiểm.
- Dữ liệu ticket/attachment không tự động copy sang global SaaS.
- Subprocessor inventory và location transparency.

Có thể cần support metadata tối thiểu ở global system nhưng nội dung hồ sơ vẫn truy cập qua regional service. Không dùng export file tạm làm workaround vì file có thể nằm trong laptop, email, chat hoặc ticket attachment ngoài boundary.

## 14. Encryption, key management và quyền truy cập theo region

Encryption là control quan trọng nhưng không tự chứng minh compliance/residency. Cần xem ai giữ key, ai có quyền decrypt, key nằm ở đâu và đường truy cập nào tồn tại.

### 14.1. Regional key strategy

- Dùng key scope phù hợp với region/data class.
- Tách principal theo workload và purpose.
- Không cấp một global role có quyền decrypt mọi tenant.
- Audit key use, policy update, grant/revoke và rotation.
- Kiểm tra backup restore bằng identity hợp lệ ở DR region.
- Quản lý envelope encryption và key version.
- Có quy trình emergency access nếu identity/control plane chính gián đoạn.
- Thực hiện cryptographic erasure chỉ khi semantics, backup và retention cho phép.

### 14.2. Tenant-level key

Với một số workload, customer-managed key hoặc key scope theo tenant có thể tăng isolation và hỗ trợ yêu cầu hợp đồng. Đổi lại:
- Quản lý số lượng key/grant lớn hơn.
- Rotation và recovery phức tạp.
- Key disable có thể làm tenant không truy cập được dữ liệu.
- Cross-region DR phụ thuộc key replica/policy.
- Audit và support cần phân biệt key owner.

Không tạo key theo tenant nếu không có mô hình vận hành đủ khả năng quản lý vòng đời, quota và incident.

## 15. Deletion, retention và quyền dữ liệu

Yêu cầu xóa có thể phức tạp hơn khi dữ liệu đã được sao chép qua nhiều vùng hoặc chuyển thành derived data.

Cần inventory:
- Primary records.
- Read replicas và region copies.
- Object versions và CDN cache.
- Backup/snapshot theo retention.
- Search index/materialized view.
- Queue/event log.
- Analytics/ML feature và training dataset.
- Export/support ticket.
- Third-party processor.

Một deletion workflow có thể:
1. Xác thực yêu cầu và phạm vi.
2. Xác định legal/contract retention exception.
3. Tạo deletion job có idempotency và audit.
4. Xóa hoặc de-link ở source of truth.
5. Propagate tới derived store theo SLA.
6. Invalidate cache/CDN và search index.
7. Ghi nhận backup expiry/cryptographic erasure policy phù hợp.
8. Xử lý bên thứ ba theo hợp đồng/API.
9. Xác minh completion và phát report theo policy.

Không hứa rằng mọi backup immutable có thể xóa tức thời. Retention/legal hold có thể yêu cầu giữ bản backup tới khi hết kỳ; cần giới hạn access và bảo đảm dữ liệu không quay lại production sau restore bằng cách áp dụng deletion ledger/tombstone.

## 16. Governance và quản lý thay đổi địa lý

Một architecture có thể tuân thủ hôm nay nhưng sai vào ngày mai khi thêm region, provider, subprocessor hoặc analytics integration.

Cần quản lý:
- Data inventory và classification owner.
- Residency matrix và approved region list.
- Data transfer assessment.
- Provider/subprocessor register.
- Region enablement/change approval.
- Tenant placement and migration workflow.
- Key/access policy.
- Retention and deletion.
- Incident/breach response theo jurisdiction.
- Review định kỳ khi luật, hợp đồng hoặc sản phẩm thay đổi.

### 16.1. Policy as code

Có thể tự động kiểm tra:
- Resource nhạy cảm chỉ được tạo trong approved region.
- Backup destination nằm trong allowlist.
- Log sink và storage bucket không cấu hình sai region.
- Replication target được phê duyệt.
- Public access bị chặn theo policy.
- Tag data class/owner/region hiện diện.
- Cross-region route chỉ mở với approved service.
- KMS key policy và workload role phù hợp.

Policy as code giảm lỗi cấu hình nhưng không thay thế legal interpretation. Cần mapping policy nghiệp vụ sang rule kỹ thuật, test false positive và quy trình exception có approval.

## 17. Đánh đổi theo Well-Architected

| Khía cạnh | Lợi ích của regional partitioning | Rủi ro/chi phí | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Cell isolation, local operation, recovery theo region | Region thiếu capacity, global router/control plane lỗi, DR bị giới hạn | Regional failover drill, SLO/RTO/RPO |
| **Bảo mật** | Data boundary, least privilege và key scope | Access cross-border, copy/log leakage, key policy drift | Data flow review, IAM/KMS audit |
| **Hiệu quả hiệu năng** | Data gần user, giảm round-trip | Cross-region calls, home-region latency, cache misses | p95/p99 theo region, transfer path |
| **Tối ưu chi phí** | Chỉ replicate dữ liệu cần thiết, localize workload | Nhiều cell/region, duplicate capacity và operations | Cost per region/tenant, egress/replica cost |
| **Vận hành xuất sắc** | Ownership rõ, policy automation và inventory | Nhiều biến thể cấu hình, migration phức tạp | Region runbook, policy coverage, audit |
| **Bền vững** | Giảm copy dư thừa và truyền dữ liệu không cần | Dự phòng phân tán làm tăng compute/storage | Resource utilization, data lifecycle, transfer volume |

Các đánh đổi thường gặp:
- Home region rõ ràng giảm conflict nhưng có thể tăng latency cho user ở xa.
- Global replication cải thiện read availability nhưng mở rộng data boundary và transfer cost.
- Regional observability giảm raw data movement nhưng đòi hỏi nhiều store/collector.
- Warm standby trong jurisdiction được phép tăng DR readiness nhưng tốn baseline.
- Pseudonymization giảm exposure nhưng không đảm bảo dữ liệu không còn định danh.
- Một global control plane giúp quản lý nhất quán nhưng có thể trở thành shared dependency và nơi tập trung metadata.

## 18. Quy trình review kiến trúc phân vùng địa lý

1. **Thu thập yêu cầu nghiệp vụ và pháp lý:** xác định thị trường, data subject, purpose, contract và jurisdiction.
2. **Phân loại dữ liệu:** PII, transaction, sensitive, public, telemetry, derived và retention.
3. **Vẽ data flow:** primary, replica, cache, backup, log, support, analytics và third-party.
4. **Tạo residency matrix:** allowed location, processing/access, replication và transfer rule.
5. **Chọn partition model:** home region, cell, region-per-tenant hoặc hybrid theo data domain.
6. **Thiết kế routing:** tenant mapping, authentication và policy enforcement server-side.
7. **Thiết kế data plane:** source of truth, consistency, replication, migration và deletion.
8. **Đánh giá control plane:** metadata minimization, admin access, deployment và outage behavior.
9. **Bảo vệ key/identity:** regional keys, least privilege, audit và break-glass.
10. **Đánh giá backup/DR:** RTO/RPO trong permitted boundary và restore test.
11. **Thiết kế telemetry:** local collection, redaction, global aggregates và incident access.
12. **Quản lý support/processor:** access location, subprocessor, ticket và export.
13. **Policy as code:** enforce approved region, transfer và resource metadata.
14. **Đo lường:** SLO, transfer bytes, replication lag, policy violation, cost và audit access.
15. **Diễn tập:** region outage, tenant migration, key failure, deletion và data transfer incident.
16. **Ghi ADR:** lựa chọn, assumption, exception, owner và review trigger.

### Checklist production

| Hạng mục | PASS khi |
|---|---|
| Data classification | Có owner, purpose, sensitivity và retention |
| Residency matrix | Primary, replica, backup, log, cache và derived data được ghi |
| Legal review | Các restriction/transfer mechanism được owner có thẩm quyền xác nhận |
| Tenant placement | Home region được xác định server-side, có approval và audit |
| Regional isolation | Cell/data plane có boundary và least privilege |
| Replication | Destination, semantics, lag và transfer policy đã rõ |
| Backup/DR | Restore test đạt mục tiêu trong permitted boundary |
| Observability | Raw logs không vô tình chuyển ra ngoài boundary |
| Support access | Human access và subprocessor được kiểm soát |
| Encryption | Key, decrypt identity và recovery path phù hợp |
| Deletion | Có propagation tới replica/derived store và backup policy |
| Policy automation | Region/transfer misconfiguration có thể bị phát hiện/chặn |
| Cost | Replica, transfer, storage và per-region cost được đo |
| Governance | Owner, exception, audit và review date rõ |

## 19. ADR minh họa — Home region cho dữ liệu khách hàng Booking

> **Bối cảnh:** Booking Platform phục vụ khách ở nhiều quốc gia. Một số hợp đồng/yêu cầu áp dụng giới hạn địa lý với hồ sơ khách hàng và transaction record. Catalog công khai cần phân phối toàn cầu để giảm latency.
>
> **Phương án A:** Một global database và multi-region replica cho tất cả dữ liệu. Đơn giản cho analytics và failover, nhưng mở rộng phạm vi bản sao và transfer cho cả dữ liệu nhạy cảm.
>
> **Phương án B:** Home region per tenant cho profile/booking; public catalog ở object/CDN global; regional audit/log store; global analytics chỉ nhận aggregate được duyệt.
>
> **Quyết định minh họa:** Chọn B. Tenant directory giữ mapping tối thiểu tới home region; mọi read/write của profile và booking được backend định tuyến theo mapping đã xác thực.
>
> **Replication/DR:** Mỗi tenant chỉ failover tới region trong approved set. Nếu không có region DR được phép, hệ thống chuyển degraded/read-only theo business policy thay vì tự chuyển dữ liệu qua biên giới.
>
> **Support:** Nhân viên toàn cầu chỉ thấy metadata cần thiết; truy cập nội dung hồ sơ qua regional service với JIT approval và audit.
>
> **Analytics:** Region xử lý raw data; chỉ aggregate/minimized dataset đã review được gửi tới global warehouse.
>
> **Kiểm chứng:** Test tenant isolation, wrong-region routing, backup/restore, global log leakage, deletion propagation, KMS access và failover.
>
> **Điều kiện xem xét lại:** Thị trường/contract thay đổi, provider mở region phù hợp, data classification mới hoặc yêu cầu RTO/RPO thay đổi.

## 20. Bài tập thực hành: thiết kế residency cho Booking Platform toàn cầu

Một nền tảng đặt chỗ dự kiến phục vụ ba nhóm thị trường:
- Nhóm A yêu cầu hồ sơ khách hàng và transaction record được lưu trong một country boundary.
- Nhóm B cho phép lưu ở một danh sách region đã duyệt, nhưng hạn chế support access từ một số địa điểm.
- Nhóm C chưa có localization constraint cụ thể nhưng vẫn phải đáp ứng privacy, security và contractual controls.

Hệ thống hiện tại dùng:
- Một global relational database.
- CDN và cache phân phối toàn cầu.
- Centralized logging ở Region A.
- Analytics warehouse ở Region B.
- Cross-region database replica cho DR.
- Support SaaS có nhân viên ở nhiều quốc gia.
- Backup copy ở một region thứ ba.

**Yêu cầu:**
1. Xác định data inventory cho profile, booking, payment, public catalog, audit, logs và derived analytics.
2. Lập residency matrix cho từng nhóm thị trường.
3. Đề xuất home region/cell cho tenant và cách định tuyến request.
4. Đánh giá global database, cache và CDN có thể làm dữ liệu vượt boundary ở đâu.
5. Thiết kế backup/DR trong các region được phép.
6. Xử lý central logging và analytics mà không chuyển raw personal data sai policy.
7. Thiết kế support access và subprocessor controls.
8. Đề xuất key management, deletion và region migration workflow.
9. Xác định policy-as-code rules và audit evidence.
10. So sánh latency, cost, resilience và operations của hai topology.

### Hướng giải quyết

- Phân loại trường dữ liệu trước khi chọn provider; xác định primary, replica, cache, backup, log, ticket và analytics copy.
- Group A dùng home region trong country boundary; replica/backup chỉ tới location được phê duyệt. Nếu không có DR location phù hợp, đánh đổi RTO với read-only/degraded mode.
- Group B dùng approved region set và access policy theo địa điểm/role; data access support được audit, không suy từ storage location.
- Group C có thể dùng mô hình regional cells hoặc multi-region linh hoạt hơn nhưng vẫn cần purpose, retention, privacy và security controls.
- Public catalog có thể dùng CDN toàn cầu nếu không chứa tenant-specific/private data; cache key và response policy phải tách nội dung nhạy cảm.
- Chuyển raw log qua regional collector, redact/minimize, global dashboard chỉ dùng aggregate được phê duyệt; kiểm tra label và trace attributes.
- Analytics thực hiện gần source rồi export summary/approved dataset; kiểm tra khả năng re-identification của aggregate.
- Backup và DR phải nằm trong approved boundary, encryption key có recovery path và restore test đạt RPO/RTO thực tế.
- Support SaaS cần subprocessor review, location/access controls, field masking, approval và audit; tránh đưa attachment thô vào ticket toàn cầu.
- Policy as code chặn resource/replica/log sink sai region; audit tenant mapping, exception và cross-border transfer.
- So sánh cost theo regional cell, replication, egress, support và duplicated operations; cân bằng với latency, isolation và recovery objectives.

### Câu hỏi tự kiểm tra

1. Data residency, data sovereignty và data localization khác nhau thế nào?
2. Vì sao database location không đủ để chứng minh residency?
3. Những telemetry nào có thể chứa dữ liệu nhận diện được?
4. Home region per tenant giải quyết vấn đề gì và tạo đánh đổi nào?
5. Regional cell architecture giảm blast radius như thế nào?
6. Global control plane nên giữ loại metadata nào?
7. Replication có phải luôn được phép nếu hai region cùng một cloud provider không?
8. Vì sao DR region phải nằm trong approved boundary?
9. CDN/cache có thể làm dữ liệu rời khỏi region bằng cách nào?
10. Derived data, embedding và model artifact có cần đánh giá residency không?
11. Làm sao quản lý support access và subprocessor ở nhiều quốc gia?
12. Deletion workflow phải xử lý những bản sao nào?
13. Pseudonymization có tự động biến dữ liệu thành anonymous không?
14. Các bằng chứng nào chứng minh policy địa lý được thực thi trong production?

Phân vùng địa lý không chỉ là chọn region đặt database. Kiến trúc cần quản lý **toàn bộ vòng đời và đường đi của dữ liệu**, bao gồm primary, replica, cache, backup, log, analytics, support và nhà thầu phụ. Khi data classification, residency matrix, tenant placement, transfer policy và key/access boundary được thiết kế rõ, nhóm có thể triển khai đa vùng mà vẫn duy trì yêu cầu lưu trú, độ tin cậy và hiệu năng. Các quyết định phải được kiểm chứng bằng data-flow review, policy automation, audit và diễn tập phục hồi trong đúng phạm vi địa lý được phép.
