# Tiếp nhận, cấu hình, di chuyển và xóa tenant

Trong một nền tảng SaaS đa khách hàng (multi-tenant), tenant là ranh giới đại diện cho một khách hàng, tổ chức hoặc không gian làm việc. Một tenant có thể có người dùng, dữ liệu, cấu hình, gói dịch vụ, giới hạn tài nguyên và chính sách bảo mật riêng. Khi nền tảng phát triển, vận hành tenant trở thành một vòng đời có nhiều bước: tiếp nhận khách hàng mới, kiểm tra điều kiện, cấp tài nguyên, cấu hình, kích hoạt, thay đổi gói dịch vụ, di chuyển dữ liệu giữa các vùng hoặc mức cô lập, tạm ngừng và cuối cùng xóa dữ liệu theo chính sách.

Các thao tác này liên quan nhiều hệ thống: identity, billing, control plane, database, object storage, queue, search index, cache, observability và hệ thống hỗ trợ. Một quy trình chỉ tạo bản ghi tenant trong database là chưa đủ. Nếu một bước thất bại giữa chừng, tenant có thể ở trạng thái nửa cấu hình; nếu xóa nhầm, dữ liệu có thể mất hoặc còn sót ở bản sao; nếu di chuyển mà không có cutover rõ ràng, hai nơi có thể cùng nhận ghi.

Bài học thuộc chương **Kiến trúc đa khách hàng** của module **CLOUD_ARCHITECTURE**. Trọng tâm là thiết kế vòng đời tenant có thể tự động hóa, kiểm soát và phục hồi; bảo đảm tenant isolation trong suốt quá trình; đồng thời cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và công sức vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô hình hóa tenant lifecycle từ provisioning đến suspension, migration và deletion.
2. Phân biệt control plane với data plane và xác định system of record cho metadata tenant.
3. Thiết kế onboarding có idempotency, workflow state, retry, compensation và kiểm tra readiness.
4. Quản lý tenant configuration, feature, quota, secrets và thay đổi có version.
5. Lập kế hoạch di chuyển tenant giữa shard, database, region hoặc mô hình cô lập.
6. Thực hiện cutover có kiểm soát, giảm downtime, tránh split-brain và xác minh tính toàn vẹn dữ liệu.
7. Thiết kế suspension, offboarding và deletion có authorization, retention, audit và bằng chứng.
8. Quan sát tenant lifecycle, xử lý tác vụ treo, đối soát tài nguyên và tối ưu chi phí vận hành.

## 2. Tenant và vòng đời tenant

### 2.1. Tenant là một thực thể quản trị

Tenant thường đại diện cho một tổ chức hoặc khách hàng sử dụng nền tảng. Tenant có thể sở hữu:

- Tenant ID và trạng thái lifecycle.
- Domain, branding, locale, timezone và cấu hình riêng.
- Người dùng, nhóm, vai trò và chính sách truy cập.
- Subscription, billing account, plan và feature entitlements.
- Tài nguyên dữ liệu: database/schema/partition/object prefix.
- Quota, rate limit, giới hạn lưu trữ và concurrency.
- Region, data residency và mức cô lập hạ tầng.
- Audit, retention, legal hold và yêu cầu xóa dữ liệu.

Tenant ID là định danh quản trị, không tự nó chứng minh caller có quyền truy cập. Mọi request vẫn phải xác thực danh tính, xác định tenant scope từ nguồn tin cậy và kiểm tra authorization ở server-side.

### 2.2. Vòng đời tham khảo

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> VALIDATING
    VALIDATING --> PROVISIONING: Accepted
    VALIDATING --> REJECTED: Invalid / policy fail
    PROVISIONING --> CONFIGURING
    CONFIGURING --> READY
    READY --> SUSPENDING
    SUSPENDING --> SUSPENDED
    SUSPENDED --> REACTIVATING
    REACTIVATING --> READY
    READY --> MIGRATING
    MIGRATING --> READY
    READY --> DELETION_PENDING
    SUSPENDED --> DELETION_PENDING
    DELETION_PENDING --> DELETING
    DELETING --> DELETED
    DELETING --> DELETION_BLOCKED: Legal hold / failure
    DELETION_BLOCKED --> DELETING: Cleared / retry
    REJECTED --> [*]
    DELETED --> [*]
~~~

Đây là mô hình minh họa; hệ thống thực tế có thể có trạng thái bổ sung như PROVISIONING_FAILED, MIGRATION_ROLLBACK, PENDING_PAYMENT, ARCHIVED hoặc DELETION_VERIFICATION. Điều quan trọng là trạng thái phải thể hiện điều kiện nghiệp vụ rõ ràng và quy định transition được phép.

### 2.3. Tách trạng thái tenant và trạng thái workflow

Tenant metadata có thể báo PROVISIONING, còn workflow đang ở bước tạo database, tạo identity groups hoặc khởi tạo storage. Đây là hai lớp trạng thái liên quan nhưng khác nhau:

- **Tenant lifecycle state:** trạng thái nghiệp vụ được các API và control plane công bố.
- **Workflow execution state:** tiến độ kỹ thuật của một lần xử lý, gồm task, retry, timeout và compensation.
- **Resource state:** trạng thái thực tế ở database, storage, identity provider, DNS hoặc billing.

Không nên đánh dấu tenant READY chỉ vì workflow execution kết thúc thành công nếu một resource thiết yếu chưa được kiểm tra. Tương tự, một workflow timeout không chứng minh tài nguyên chưa được tạo; cần đối soát theo resource ID và idempotency key.

## 3. Control plane và data plane

### 3.1. Control plane

Control plane quản lý tenant và vòng đời của họ: tiếp nhận yêu cầu, xác minh danh tính và hợp đồng; tạo tenant record, plan, region và placement; provision database/schema/storage/identity resources; quản lý cấu hình, quota, feature flag và trạng thái; điều phối migration, suspension, restore và deletion; ghi audit, quản lý tác vụ vận hành và đối soát tài nguyên.

### 3.2. Data plane

Data plane phục vụ request nghiệp vụ của tenant: xác thực request và xác định tenant context; định tuyến tới database/shard/region được chỉ định; áp dụng tenant isolation và authorization; đọc/ghi dữ liệu nghiệp vụ; thực thi quota và giới hạn tải theo tenant.

~~~mermaid
flowchart TB
    ADMIN[Admin / Signup API] --> CP[Control Plane]
    CP --> REG[(Tenant Registry)]
    CP --> WF[Lifecycle Workflow]
    WF --> IDP[Identity Provider]
    WF --> BILL[Billing]
    WF --> PROV[Infrastructure Provisioner]
    PROV --> DB[(Database / Shard)]
    PROV --> OBJ[(Object Storage)]
    USER[Tenant User] --> EDGE[API Gateway]
    EDGE --> DP[Data Plane]
    DP --> REG
    DP --> ROUTER[Tenant Router]
    ROUTER --> DB
    DP --> CACHE[(Cache)]
~~~

Control plane có quyền cao và có thể điều khiển nhiều tenant. Cần cô lập quyền, workload identity, approval và audit chặt chẽ. Lỗi hoặc compromise ở control plane có thể ảnh hưởng diện rộng hơn lỗi ở một tenant riêng lẻ.

### 3.3. Tenant registry

Registry là nguồn chuẩn cho metadata định tuyến và lifecycle. Một bản ghi tham khảo:

~~~json
{
  "tenantId": "tenant_7f31",
  "displayName": "Example Organization",
  "status": "READY",
  "plan": "BUSINESS",
  "region": "ap-southeast-1",
  "deploymentModel": "SHARED_DATABASE",
  "databasePlacement": {
    "clusterId": "cluster_03",
    "shardId": "shard_12"
  },
  "configVersion": 18,
  "lifecycleVersion": 6,
  "createdAt": "2026-11-18T05:00:00Z"
}
~~~

Không nên để client gửi databasePlacement rồi ứng dụng tin ngay. Control plane quản lý placement và data plane chỉ đọc mapping đã được xác thực. Có thể cache registry để giảm latency, nhưng thay đổi placement, trạng thái suspension và deletion cần invalidation/versioning để tránh request tiếp tục định tuyến tới vị trí cũ.

## 4. Tiếp nhận tenant mới (onboarding)

### 4.1. Các bước trong onboarding

Một quy trình onboarding điển hình:

1. Nhận yêu cầu và tạo onboarding request ID.
2. Xác thực người yêu cầu, tổ chức và quyền tạo tenant.
3. Kiểm tra trùng lặp theo domain, legal entity, external customer ID hoặc idempotency key.
4. Kiểm tra plan, billing, region, data residency và điều khoản.
5. Chọn placement/deployment model.
6. Tạo tenant record ở trạng thái chưa sẵn sàng.
7. Provision tài nguyên và identity boundary.
8. Áp dụng cấu hình mặc định, quota, feature và secret references.
9. Khởi tạo schema, bucket/prefix, encryption key hoặc data seed cần thiết.
10. Kiểm tra readiness, tenant isolation, kết nối và quyền.
11. Chuyển trạng thái READY, kích hoạt đăng nhập hoặc gửi thông báo welcome.

~~~mermaid
flowchart TD
    START[Signup request] --> VALIDATE[Verify identity, organization, plan]
    VALIDATE --> DUP{Already exists?}
    DUP -->|Yes| RETURN[Return existing request / conflict]
    DUP -->|No| CREATE[Create tenant PENDING]
    CREATE --> PLACE[Choose region and placement]
    PLACE --> RES[Provision identity, database, storage]
    RES --> CONFIG[Apply config, quota, features]
    CONFIG --> CHECK[Readiness and isolation checks]
    CHECK -->|Pass| READY[Mark tenant READY]
    CHECK -->|Fail| RECOVER[Retry / compensate / manual review]
    RECOVER --> CONFIG
~~~

### 4.2. Idempotency khi tiếp nhận

Signup hoặc onboarding request có thể được gửi lại do client timeout, webhook trùng hoặc người vận hành bấm submit nhiều lần. Không để mỗi request tạo tenant mới.

Cần một idempotencyKey do caller hoặc control plane tạo; unique constraint theo scope phù hợp; ghi kết quả và trạng thái của request để lần gửi lại lấy lại kết quả; các bước provision cũng dùng resource name/ID ổn định để có thể tra cứu và tái sử dụng; phân biệt retry cùng yêu cầu với yêu cầu tạo tenant khác có cùng domain.

Idempotency key không thay thế kiểm tra trùng theo quy tắc nghiệp vụ. Một người có thể gửi hai key khác nhau cho cùng tổ chức; control plane vẫn phải xử lý duplicate organization/domain theo policy.

### 4.3. Provisioning tuần tự và song song

Một số bước phụ thuộc nhau: tạo tenant ID trước khi tạo namespace; tạo key trước khi cấu hình encryption; tạo database/schema trước khi chạy migration. Những bước độc lập như tạo nhóm identity và tạo bucket có thể chạy song song nếu không vi phạm quota.

Song song giúp giảm thời gian onboarding nhưng tăng số nhánh lỗi cần xử lý. Phải định nghĩa bước nào được chạy lại, bước nào cần compensation, và tiêu chí để tổng hợp readiness.

### 4.4. Trạng thái chưa sẵn sàng

Tenant chỉ trở thành READY sau khi các kiểm tra bắt buộc đạt. API không được cho tenant truy cập data plane khi metadata mới ở PROVISIONING hoặc CONFIGURING. Có thể trả trạng thái tiến trình, retry-after hoặc link theo dõi onboarding; không trả về thông tin nội bộ như credential hay resource admin endpoint.

## 5. Cấu hình tenant và feature entitlement

### 5.1. Phân loại cấu hình

| Loại | Ví dụ | Cách quản lý |
|---|---|---|
| Platform default | Locale mặc định, feature cơ bản | Template/version do platform quản lý |
| Plan entitlement | Số user tối đa, chức năng nâng cao | Billing/entitlement service |
| Tenant override | Branding, timezone, retention preference | Tenant configuration có validation |
| Security policy | SSO required, IP allowlist, MFA | Policy có audit và quyền thay đổi riêng |
| Runtime setting | Rate limit, concurrency, routing | Config service/cache có version |
| Secret | API credential, signing key reference | Secret manager, không lưu plaintext trong registry |

### 5.2. Versioning cấu hình

Mỗi lần thay đổi cấu hình nên có version, người/tiến trình thay đổi, thời điểm, lý do và nguồn phê duyệt. Consumer có thể nhận configVersion trong tenant context hoặc cache key để nhận biết cấu hình cũ.

Không nên để các service tự đọc và merge nhiều file cấu hình theo thứ tự không rõ. Cần quy định precedence, ví dụ platform defaults → plan entitlements → tenant overrides → enforced security policies.

Policy bảo mật bắt buộc phải có quyền ưu tiên cao hơn override tenant không được phép nới lỏng.

### 5.3. Rollout cấu hình

Với thay đổi ảnh hưởng nhiều tenant:

1. Validate schema và policy.
2. Dry-run để xác định tenant bị ảnh hưởng.
3. Thử trên tenant nội bộ/canary.
4. Triển khai theo batch hoặc cohort.
5. Quan sát lỗi, latency, quota và kết quả.
6. Dừng rollout nếu vượt ngưỡng.
7. Rollback hoặc forward-fix có audit.

Thay đổi cấu hình không tương thích cần migration rõ ràng. Không được giả định mọi service cùng đọc phiên bản mới tại cùng một thời điểm.

## 6. Quản lý quota và placement

### 6.1. Quota theo tenant

Quota có thể áp dụng cho số user, project, listing hoặc object; storage bytes và số file; API request rate và concurrency; background jobs, queue messages và compute units; số kết nối, subscription, export hoặc integration.

Quota cần được thực thi ở data plane hoặc service sở hữu tài nguyên, không chỉ hiển thị ở billing portal. Counter phân tán có thể eventual consistent; thao tác cần hard limit phải có cơ chế atomic reservation hoặc kiểm soát ở nguồn có thẩm quyền.

### 6.2. Placement

Control plane quyết định tenant nằm ở region, cluster, shard, database/schema hoặc dedicated environment nào dựa trên data residency và contract; SLO và latency với người dùng; kích thước/throughput và mức cô lập; plan/entitlement; capacity, quota và failure domain; khả năng backup, restore và DR.

Placement nên được biểu diễn bằng mapping có version, có audit và được data plane đọc qua router đáng tin cậy. Không suy placement trực tiếp từ tenantId bằng thuật toán hash nếu hệ thống có khả năng di chuyển tenant giữa shard mà không thay đổi ID.

## 7. Suspension và reactivation

### 7.1. Khi nào suspension?

Tenant có thể bị tạm ngừng do yêu cầu khách hàng, thanh toán, vi phạm policy, sự cố bảo mật hoặc yêu cầu điều tra. Suspension khác deletion: dữ liệu thường vẫn được giữ theo hợp đồng và retention.

Trước khi suspend, xác định phạm vi: chặn đăng nhập hay chỉ chặn ghi; token hiện hữu được thu hồi thế nào; background jobs và scheduled task có dừng không; webhook/integration có bị pause không; người dùng có được export hoặc truy cập read-only không; dữ liệu và backup còn phải giữ trong bao lâu.

### 7.2. Quy trình suspension

~~~mermaid
flowchart TD
    REQUEST[Authorized suspension request] --> CHECK[Validate reason and approval]
    CHECK --> MARK[Set SUSPENDING]
    MARK --> BLOCK[Block new sessions and writes]
    BLOCK --> REVOKE[Revoke credentials / disable integrations]
    REVOKE --> DRAIN[Drain or cancel background work]
    DRAIN --> VERIFY[Verify access blocked and data retained]
    VERIFY --> SUSPENDED[Set SUSPENDED]
~~~

Nên cập nhật trạng thái control plane sớm để ngăn request mới, sau đó thực hiện các bước thu hồi credential, dừng job và xác minh. Nếu một bước thất bại, tenant ở trạng thái SUSPENDING hoặc SUSPENSION_BLOCKED; không tuyên bố đã suspend hoàn chỉnh khi session hoặc API key vẫn hoạt động ngoài dự kiến.

### 7.3. Reactivation

Reactivation cần kiểm tra nguyên nhân suspension đã được giải quyết, subscription hợp lệ, credential được cấp lại đúng cách và dữ liệu còn ở trạng thái mong đợi. Không tự khôi phục session/token đã thu hồi. Có thể cần provisioning lại integration và chạy health check trước khi chuyển READY.

## 8. Di chuyển tenant (tenant migration)

### 8.1. Lý do di chuyển

Tenant có thể cần di chuyển từ shared database sang dedicated database khi tăng quy mô hoặc yêu cầu cô lập; từ một shard quá tải sang shard còn capacity; sang region khác theo data residency hoặc độ trễ; sang phiên bản database mới hoặc storage tier khác; từ shared schema sang schema/database riêng; hoặc sang một deployment cell mới để giảm blast radius.

Migration không chỉ là copy bảng. Cần di chuyển dữ liệu, index, constraint, object, search projection, cache, credential, routing metadata, scheduled job, integration endpoint và những resource liên quan.

### 8.2. Các chiến lược migration

| Chiến lược | Cách làm | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Offline/cold migration | Dừng ghi, copy, kiểm tra, cutover | Dễ đảm bảo nhất quán hơn | Downtime dài hơn, cần cửa sổ bảo trì |
| Snapshot + delta | Copy snapshot rồi áp dụng thay đổi phát sinh | Rút ngắn downtime | Phức tạp về CDC, ordering và replay |
| Dual-write | Ghi đồng thời nguồn/đích trong giai đoạn chuyển | Có thể giảm thời gian cutover | Dễ lệch dữ liệu, cần idempotency và reconciliation |
| Blue-green | Dựng đích đầy đủ, xác minh, chuyển traffic | Rollback routing nhanh hơn nếu nguồn còn nguyên | Tốn tài nguyên song song; cần xử lý write consistency |
| Tenant-by-tenant | Di chuyển một tenant/cohort mỗi lần | Blast radius nhỏ và dễ quan sát | Nhiều lần lặp vận hành |

Không có chiến lược migration nào tự an toàn. Chọn theo downtime cho phép, write rate, data volume, khả năng CDC, consistency và khả năng rollback.

### 8.3. Quy trình migration theo giai đoạn

~~~mermaid
flowchart TD
    PLAN[Inventory and migration plan] --> PREP[Prepare destination]
    PREP --> SNAP[Copy snapshot]
    SNAP --> CATCH[Replicate delta changes]
    CATCH --> VERIFY[Validate counts, checksums, invariants]
    VERIFY --> READY{Within acceptance criteria?}
    READY -->|No| FIX[Fix or restart migration]
    FIX --> CATCH
    READY -->|Yes| FREEZE[Freeze writes / drain in-flight requests]
    FREEZE --> FINAL[Apply final delta and verify]
    FINAL --> ROUTE[Switch tenant placement]
    ROUTE --> SMOKE[Smoke test and monitor]
    SMOKE -->|Pass| DONE[Complete migration]
    SMOKE -->|Fail| ROLLBACK[Controlled rollback / forward recovery]
~~~

Các bước chi tiết:

1. **Inventory:** xác định mọi tài nguyên thuộc tenant, kích thước, tốc độ thay đổi, dependency và owner.
2. **Prepare:** tạo đích, schema, index, encryption, IAM, quota và network.
3. **Snapshot:** copy dữ liệu nhất quán hoặc dùng snapshot/backup được hỗ trợ.
4. **Delta replication:** chuyển các thay đổi phát sinh sau snapshot bằng CDC/log hoặc công cụ migration.
5. **Validation:** so sánh row count, checksum theo partition, aggregate, constraint và sample record.
6. **Quiesce:** chặn ghi mới hoặc đưa tenant vào maintenance/read-only; drain request đang xử lý.
7. **Final sync:** áp dụng delta cuối, xác nhận không còn lag vượt ngưỡng.
8. **Cutover:** đổi tenant placement/router theo một version hoặc epoch rõ ràng.
9. **Verification:** smoke test đọc/ghi, authorization, integrations, background jobs và metrics.
10. **Cleanup:** chỉ xóa nguồn cũ sau thời gian giữ an toàn và sau khi rollback window kết thúc.

### 8.4. Tránh split-brain

Trong migration, rủi ro lớn là source và destination cùng nhận ghi độc lập. Khi đó hai nơi có thể phát triển thành hai lịch sử khác nhau.

Biện pháp:

- Chỉ định một write owner tại mỗi thời điểm.
- Dùng migration epoch/version để từ chối request tới placement cũ sau cutover.
- Chặn ghi và drain in-flight requests trước final sync.
- Dùng idempotency key cho lệnh có thể retry.
- Có fencing token hoặc routing generation để request cũ không ghi vào source sau khi quyền sở hữu đã đổi.
- Kiểm tra background worker, queue consumer và scheduled job cũng tuân theo placement mới.

Đổi registry trước khi mọi consumer được cập nhật có thể tạo cửa sổ định tuyến không đồng nhất. Có thể dùng router service, cache versioning, epoch validation và quy trình rollout để điều phối.

### 8.5. Rollback không phải lúc nào cũng chỉ đổi route

Sau khi destination đã nhận ghi mới, quay lại source cũ có thể làm mất dữ liệu phát sinh sau cutover. Trước migration, phải xác định thời điểm rollback còn an toàn; có đồng bộ ngược hay không; cách đóng băng ghi và hợp nhất delta nếu rollback; điều kiện quyết định rollback hay forward-fix; ai có quyền phê duyệt thao tác.

Giữ source cũ read-only trong rollback window có thể hữu ích, nhưng cần kiểm soát credential và chi phí. Nếu đã có write mới ở destination, forward recovery thường an toàn hơn đổi route mù quáng.

## 9. Quản lý cấu hình trong khi di chuyển

Migration thường thay đổi nhiều metadata: database host/cluster, schema version, region, encryption key, cache namespace, queue topic và endpoint. Không nên cập nhật từng service thủ công.

Một migration manifest có thể ghi:

~~~json
{
  "migrationId": "mig_2026_031",
  "tenantId": "tenant_7f31",
  "from": {
    "region": "ap-southeast-1",
    "shardId": "shard_12"
  },
  "to": {
    "region": "ap-southeast-2",
    "shardId": "shard_04"
  },
  "phase": "CATCHING_UP",
  "epoch": 3,
  "startedAt": "2026-11-18T05:00:00Z"
}
~~~

Manifest là metadata điều phối; secret và connection string nên nằm trong secret manager/config service có phân quyền. Các service đọc tenant placement theo cùng một contract/version, không tự suy ra host.

## 10. Xóa tenant và offboarding

### 10.1. Xóa tenant là workflow có hậu quả lớn

Xóa tenant có thể gồm dữ liệu ở primary database, read replica và shard; object storage, file upload, export và backup; cache, search index, analytics projection và data lake; queue, topic, DLQ, scheduled jobs và workflow history; identity provider, users, groups, API keys, OAuth clients và certificates; billing, subscription, invoice và audit; third-party integration, webhook và hệ thống support.

Một câu lệnh DELETE tenant trong registry không xóa mọi dữ liệu trên. Có thể còn orphan object, index, log hoặc backup chứa dữ liệu tenant.

### 10.2. Phân biệt trạng thái deletion

Nên có các trạng thái như DELETION_REQUESTED, DELETION_PENDING, DELETION_BLOCKED, DELETING, DELETION_VERIFICATION và DELETED. Mỗi trạng thái cần định nghĩa rõ điều kiện đi vào/đi ra và owner xử lý.

DELETED phải có nghĩa cụ thể. Nếu backup bất biến còn tồn tại đến hết retention, hệ thống cần ghi rõ dữ liệu được cô lập và sẽ hết hạn theo lịch, nếu policy/contract cho phép. Không tuyên bố xóa vật lý hoàn toàn khi bản sao vẫn được giữ.

### 10.3. Quy trình offboarding

~~~mermaid
flowchart TD
    REQ[Deletion request] --> AUTH[Verify authority and scope]
    AUTH --> HOLD{Legal or retention hold?}
    HOLD -->|Yes| BLOCK[DELETION_BLOCKED]
    HOLD -->|No| PEND[Deletion pending / notice period]
    PEND --> APPROVE[Approval and final confirmation]
    APPROVE --> SUSPEND[Disable access and integrations]
    SUSPEND --> EXPORT[Optional customer export]
    EXPORT --> DELETE[Delete tenant data and resources]
    DELETE --> VERIFY[Verify primary and derived stores]
    VERIFY -->|Complete| CERT[Record evidence / deletion certificate]
    CERT --> DONE[DELETED]
    VERIFY -->|Incomplete| BLOCK
~~~

Thứ tự cụ thể phụ thuộc hợp đồng và chính sách retention. Phải xác định trước việc xuất dữ liệu, hóa đơn chưa thanh toán, legal hold, audit bắt buộc và lịch xóa backup.

### 10.4. Xác thực và phê duyệt

Yêu cầu xóa cần được xác minh bởi người có thẩm quyền tenant hoặc quy trình hợp đồng. Với tenant lớn hoặc thao tác có ảnh hưởng diện rộng, có thể yêu cầu dual approval (hai người độc lập) và xác nhận lại qua kênh đáng tin cậy.

Không cho phép một request chỉ chứa tenantId là đủ để xóa. Kiểm tra identity, tenant ownership, role, reason, approval record và scope tài nguyên. Ghi audit bất biến phù hợp với chính sách.

### 10.5. Xóa dữ liệu ở bản sao và backup

- Xóa/invalidate cache và search document.
- Gỡ tenant khỏi analytics projection, data lake và export theo policy.
- Dừng queue consumer và scheduled task để không tái tạo dữ liệu sau deletion.
- Xóa object và multipart upload dang dở.
- Vô hiệu hóa identity, API credential, webhook và integration.
- Xác định cách xử lý backup snapshot, PITR log và archive.
- Ngăn restore backup cũ làm tenant đã xóa xuất hiện trở lại.

Nếu một bản backup chung chứa nhiều tenant, không thể xóa chọn lọc dữ liệu của một tenant khỏi snapshot bất biến một cách đơn giản. Cần policy retention, cryptographic erasure hoặc quy trình restore-and-purge tùy kiến trúc và nghĩa vụ pháp lý; quyết định phải được chuyên gia bảo mật/pháp chế xác nhận.

### 10.6. Cryptographic erasure

Trong một số thiết kế, dữ liệu tenant được mã hóa bằng data encryption key riêng hoặc envelope key theo tenant. Khi deletion được phê duyệt, hủy key có thể khiến bản sao ciphertext không thể giải mã trong điều kiện key không còn bản sao khả dụng.

Biện pháp này chỉ phù hợp nếu key thực sự riêng cho phạm vi dữ liệu cần xóa; không còn bản sao key trong backup, export, cache hoặc log; không có dữ liệu nhạy cảm plaintext ở hệ thống khác; key destruction được audit và đáp ứng tiêu chuẩn pháp lý/contract.

Hủy key không đồng nghĩa xóa mọi metadata, log hoặc bản sao plaintext. Không dùng cryptographic erasure như lời khẳng định tổng quát khi chưa kiểm tra toàn bộ data lifecycle.

## 11. Retention, legal hold và quyền xuất dữ liệu

### 11.1. Retention

Retention xác định dữ liệu được giữ bao lâu và vì mục đích gì. Có thể khác nhau giữa dữ liệu nghiệp vụ, hóa đơn, audit, log, backup và telemetry. Deletion workflow phải tra cứu policy theo loại dữ liệu và jurisdiction.

### 11.2. Legal hold

Legal hold hoặc yêu cầu điều tra có thể ngăn xóa một phần dữ liệu. Khi gặp hold, ghi rõ phạm vi, người phê duyệt và thời điểm bắt đầu; chỉ khóa phần dữ liệu cần thiết; tiếp tục xóa những tài nguyên không nằm trong hold nếu policy cho phép; chặn trạng thái DELETED cho đến khi điều kiện hoàn tất; audit việc đặt, thay đổi và gỡ hold.

### 11.3. Export trước khi offboarding

Khách hàng có thể cần xuất dữ liệu trước khi tenant bị xóa hoặc hợp đồng hết hạn. Export cần xác thực requester và quyền; xác định định dạng, phạm vi, schema/version và giới hạn kích thước; mã hóa file, link có thời hạn và audit download; hạn chế truy cập bởi support/operator; đặt retention cho bản export tạm và xóa sau thời hạn.

Export không nên trở thành đường vòng cho người dùng lấy dữ liệu ngoài tenant scope.

## 12. Workflow orchestration và khả năng phục hồi

### 12.1. Vì sao cần workflow?

Provisioning, migration và deletion gồm nhiều bước bất đồng bộ, một số bước mất nhiều phút/giờ. Workflow engine có thể quản lý state, timeout, retry, wait, callback, parallel task và execution history. Không nên giữ một HTTP request hoặc function chạy liên tục trong toàn bộ quy trình dài.

### 12.2. Task idempotent

Mỗi thao tác provision/delete cần resource key ổn định. Ví dụ, bước tạo bucket cho tenant không nên tạo bucket mới mỗi lần retry; trước khi tạo lại, kiểm tra resource đã tồn tại và có đúng owner/tenant tag hay chưa.

Side effect bên ngoài cần idempotency key hoặc reconciliation. Timeout không chứng minh thao tác chưa xảy ra.

### 12.3. Retry và compensation

Retry các lỗi tạm thời như network reset hoặc throttling có giới hạn và backoff. Không retry vô hạn lỗi permission, quota, invalid config hoặc policy. Compensation phù hợp với bước có thể đảo ngược, ví dụ giải phóng reservation; nhưng không phải thao tác xóa dữ liệu nào cũng có thể undo.

Với deletion, một khi dữ liệu đã bị xóa an toàn, workflow không nên cố rollback bằng cách tạo lại tenant rỗng. Cần trạng thái tiến trình, backup/recovery policy và phê duyệt riêng.

### 12.4. Manual intervention

Những trạng thái như MIGRATION_BLOCKED, DELETION_BLOCKED hoặc PROVISIONING_FAILED cần owner, reason, deadline và runbook. Operator action phải có authorization, reason code, audit và idempotency. Không sửa trực tiếp trạng thái registry để ép workflow kết thúc khi resource thực tế chưa được đối soát.

## 13. Bảo mật và tenant isolation xuyên suốt lifecycle

### 13.1. Tenant context

Tenant context nên được xác định từ identity/token đã xác thực và mapping trong control plane. Không tin header hoặc query parameter tenantId do caller tự gửi nếu chưa kiểm tra. Mọi data access cần gắn tenant scope theo nguyên tắc fail closed.

### 13.2. Isolation khi provisioning

- Gắn owner/tenant tag vào resource.
- Dùng IAM role riêng hoặc policy condition theo tenant khi khả thi.
- Tạo namespace, schema, database hoặc key theo mô hình isolation.
- Kiểm tra bucket policy, database role và encryption context.
- Không tái sử dụng secret hay credential giữa tenant khi mức cô lập yêu cầu riêng.
- Chạy isolation test trước khi đưa tenant vào READY.

### 13.3. Isolation trong migration

Migration cần kiểm tra source và destination đều gắn với đúng tenant. Export/import phải dùng job identity có scope, file tạm có mã hóa và retention ngắn. Không log nội dung dữ liệu trong error hoặc progress output.

### 13.4. Isolation trong deletion

Xóa theo tenant ID không được phép wildcard sang tenant khác. Nên dùng inventory tài nguyên dựa trên registry/ownership tag, allowlist loại resource, dry-run và kiểm đếm trước khi thực hiện. Với thao tác destructive, có thể yêu cầu xác nhận số lượng tài nguyên và tenant name đã xác minh.

## 14. Quan sát, audit và đối soát

### 14.1. Lifecycle metrics

| Nhóm | Metric | Mục đích |
|---|---|---|
| Onboarding | Request accepted/rejected, provisioning duration | Đo thời gian kích hoạt và lỗi |
| Provisioning | Resource creation success/failure, retry, orphan count | Phát hiện tài nguyên nửa chừng |
| Configuration | Config version lag, rollout failure | Theo dõi áp dụng cấu hình |
| Suspension | Time to block access, remaining active sessions | Xác minh khóa truy cập |
| Migration | Bytes copied, delta lag, validation mismatch, cutover duration | Đo tiến độ và tính đúng đắn |
| Deletion | Resource inventory, deletion progress, blocked age | Theo dõi xóa và retention |
| Isolation | Cross-tenant access denied/attempt, policy violations | Phát hiện lỗi bảo mật |
| Cost | Resource cost by tenant, idle resource, storage growth | Kiểm soát chi phí |

### 14.2. Correlation và audit

Mỗi lifecycle request nên có lifecycleRequestId hoặc operationId xuyên suốt workflow, resource provisioner và log. Audit cần thể hiện ai yêu cầu, tenant nào, hành động gì, lý do, approval, version trước/sau và kết quả.

Audit không nên chứa secret, token, full database connection string hoặc payload nhạy cảm. Dữ liệu audit có thể cần retention riêng và quyền truy cập hạn chế.

### 14.3. Reconciliation

Chạy đối soát định kỳ giữa tenant registry và tài nguyên thực tế:

- Tenant READY phải có đủ database, bucket, identity và routing resource bắt buộc.
- Resource có tag tenant nhưng registry không còn tenant tương ứng cần được điều tra.
- Tenant đã DELETED không được còn active credential, queue consumer hoặc resource có thể truy cập dữ liệu.
- Migration hoàn tất phải có mapping placement nhất quán và source không còn nhận ghi.
- Quota/billing phải phản ánh resource đang hoạt động.

Đối soát cần có chế độ dry-run, owner xử lý orphan, approval trước khi xóa tài nguyên không rõ nguồn gốc và audit kết quả.

## 15. Capacity, blast radius và chi phí

### 15.1. Shared resource

Tenant lifecycle có thể tạo burst lớn nếu nhiều tenant onboard cùng lúc. Cần giới hạn concurrency theo region/cluster, tránh provisioning đồng loạt làm hết quota hoặc làm database control plane quá tải.

### 15.2. Dedicated resource

Tenant dedicated có thể cần database, key, cluster hoặc network riêng. Chi phí không chỉ là compute/storage mà còn backup, monitoring, patching, DR, idle capacity và on-call. Tự động hóa provisioning/deletion và chuẩn hóa template giúp giảm công việc thủ công.

### 15.3. Migration capacity

Snapshot copy và delta replication tiêu thụ I/O, CPU, network và storage ở cả nguồn/đích. Chạy migration hàng loạt có thể cạnh tranh với traffic nghiệp vụ. Cần giới hạn số tenant di chuyển song song; chọn cửa sổ tải thấp; throttle copy và delta apply; đo replication lag và database headroom; tính chi phí truyền dữ liệu cross-zone/region; có pause/resume và checkpoint.

### 15.4. Deletion và cleanup

Deletion workflow cũng tạo tải: scan object, xóa partition, rebuild index, thu hồi key và dọn backup metadata. Xóa hàng loạt không có throttle có thể ảnh hưởng tenant còn lại trên shared infrastructure. Cần batch, rate limit và đo tác động.

## 16. Runbook cho các tình huống thường gặp

### 16.1. Onboarding bị kẹt

1. Tra lifecycleRequestId và tenant state.
2. Xác định task cuối cùng đã thành công và resource ID đã tạo.
3. Kiểm tra quota, IAM, network, billing và provider error.
4. Xác minh tác vụ retry có idempotent không.
5. Resume task phù hợp hoặc chuyển manual review; không chạy lại toàn bộ mù quáng.
6. Chỉ chuyển READY sau readiness và isolation checks.

### 16.2. Migration lag không giảm

1. Kiểm tra write rate nguồn, throughput CDC và apply rate đích.
2. Kiểm tra connector, partition, network và quota.
3. Giảm số migration song song hoặc throttle background load.
4. Đánh giá thời gian còn lại so với migration window.
5. Không cutover khi delta lag vượt acceptance criteria.
6. Hoãn migration hoặc lập lại capacity plan nếu không thể bắt kịp an toàn.

### 16.3. Cutover thất bại

1. Xác định tenant đang ở source hay destination và epoch hiện tại.
2. Chặn ghi ở cả hai nơi nếu chưa xác định write owner.
3. Kiểm tra in-flight request, queue consumer và scheduled task.
4. Đối soát delta và version trước khi quyết định rollback/forward.
5. Chỉ đổi routing khi mapping và fencing token nhất quán.
6. Chạy smoke test, thông báo và ghi audit.

### 16.4. Deletion bị block

1. Xác minh lý do: legal hold, retention, export pending hay provider error.
2. Chỉ rõ tài nguyên nào được phép xóa và tài nguyên nào phải giữ.
3. Xác nhận approval để gỡ hold nếu có.
4. Retry các bước an toàn, xử lý provider lỗi hoặc chuyển manual action.
5. Chạy inventory lại và chỉ đánh dấu DELETED khi tiêu chí đã đạt.

## 17. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Tạo tenant record rồi đánh dấu READY ngay | Data plane truy cập khi resource chưa sẵn sàng | Readiness gate và state machine |
| Onboarding không idempotent | Retry tạo nhiều tenant/resource | Idempotency key, unique constraint và deterministic resource ID |
| Config nằm rải rác trong từng service | Cấu hình lệch phiên bản, khó rollback | Tenant registry/config service có version |
| Trust tenantId từ request | Truy cập chéo tenant | Xác định context từ identity và server-side authorization |
| Migrate bằng copy rồi đổi DNS ngay | Mất delta, ghi kép hoặc dữ liệu cũ | Snapshot + delta + quiesce + validation + epoch cutover |
| Không tính background worker khi migrate | Job tiếp tục ghi vào source cũ | Cập nhật routing cho cả API, worker, schedule và queue |
| Giả định rollback chỉ cần đổi placement | Mất dữ liệu phát sinh ở destination | Reverse sync hoặc forward recovery có kế hoạch |
| Xóa tenant chỉ ở registry | Orphan data ở DB, object, cache, queue và backup | Resource inventory và deletion verification |
| Bỏ qua legal hold/retention | Vi phạm hợp đồng hoặc nghĩa vụ lưu trữ | Policy gate và approval |
| Coi DELETED đồng nghĩa mọi backup biến mất ngay | Khẳng định xóa không chính xác | Định nghĩa backup lifecycle và lịch expiry |
| Không có đối soát orphan resource | Tốn chi phí và tăng bề mặt tấn công | Scheduled reconciliation và owner |
| Chạy nhiều lifecycle job không giới hạn | Quota exhaustion và ảnh hưởng tenant khác | Concurrency/rate limit theo region và cell |

## 18. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Ai sở hữu workflow, tenant registry, runbook và reconciliation? | Tự động hóa, audit, lifecycle metrics; nhiều trạng thái cần công cụ điều tra tốt |
| **Security** | Ai được tạo, migrate, suspend và delete tenant? | Least privilege, approval, tenant scope, secret manager, resource ownership tag |
| **Reliability** | Retry, timeout, partial provisioning, cutover và deletion lỗi được phục hồi ra sao? | Idempotency, checkpoint, state machine, readiness gate và reconciliation |
| **Performance Efficiency** | Provisioning/migration có làm ảnh hưởng data plane không? | Throttle, batch, capacity window và placement-aware routing |
| **Cost Optimization** | Có orphan, idle dedicated resource hoặc backup giữ quá lâu không? | Resource inventory, lifecycle cleanup và cost attribution theo tenant |
| **Sustainability** | Có copy dữ liệu, chạy job hoặc giữ tài nguyên không cần thiết? | Incremental migration, retention hợp lý, cleanup có kiểm soát |

Lifecycle automation giảm thao tác thủ công nhưng quyền của control plane rất mạnh. Cần kiểm soát change, audit, approval và blast radius tương xứng.

## 19. Bài tập áp dụng

### Bài tập A — Onboarding retry

Signup request timeout sau khi database và bucket đã được tạo, nhưng API chưa trả kết quả. Client gửi lại cùng yêu cầu.

**Câu hỏi:** Làm thế nào tránh tạo tenant và bucket thứ hai?

**Gợi ý:** Dùng idempotency key cho onboarding, tenant ID ổn định, deterministic resource name, kiểm tra resource ownership và resume từ lifecycle state đã lưu. Không chỉ retry toàn bộ workflow.

### Bài tập B — Readiness

Identity group đã tạo và database kết nối được, nhưng bucket policy chưa áp dụng. Workflow báo thành công một phần.

**Câu hỏi:** Tenant đã được chuyển READY chưa?

**Gợi ý:** Chưa nếu bucket policy là điều kiện bắt buộc. Tenant ở CONFIGURING/PROVISIONING_FAILED, retry hoặc manual repair, sau đó chạy lại readiness và isolation checks.

### Bài tập C — Migration hai nơi cùng ghi

Tenant được đổi routing sang shard mới nhưng một worker cũ vẫn ghi vào shard nguồn.

**Câu hỏi:** Rủi ro và biện pháp nào?

**Gợi ý:** Split-brain và mất cập nhật khi nguồn bị bỏ qua. Dùng migration epoch/fencing, drain hoặc pause worker, xác định một write owner, kiểm tra mọi consumer/scheduler và đối soát delta trước cutover.

### Bài tập D — Deletion và backup

Tenant được đánh dấu DELETED nhưng backup snapshot chung vẫn chứa dữ liệu của tenant đến hết retention 90 ngày.

**Câu hỏi:** Cần công bố trạng thái và kiểm soát gì?

**Gợi ý:** Định nghĩa rõ DELETED đối với hệ thống active và bản sao backup; cô lập backup theo policy, kiểm soát restore để không hồi sinh tenant, ghi expiry schedule và bằng chứng. Không tuyên bố mọi bản sao đã bị xóa vật lý ngay.

### Bài tập E — Legal hold

Admin tenant yêu cầu xóa toàn bộ dữ liệu nhưng một phần audit đang nằm trong legal hold.

**Câu hỏi:** Workflow nên hành xử thế nào?

**Gợi ý:** Xác thực requester, xác định đúng phạm vi hold, xóa phần được phép, chuyển phần bị giữ sang DELETION_BLOCKED/retention state, lưu approval và chỉ tiếp tục sau khi hold được gỡ hợp lệ.

### Bài tập F — Cost orphan resources

Một tenant đã bị xóa nhưng còn bucket, queue và encryption key. Không có log nào ghi nhận owner.

**Câu hỏi:** Cần bổ sung gì trong thiết kế?

**Gợi ý:** Resource inventory, mandatory tenant/operation tags, deterministic names, deletion checklist, orphan reconciliation, audit và owner cho từng resource type. Xác minh trước khi xóa tài nguyên không rõ nguồn.

## 20. Checklist trước khi vận hành tenant lifecycle

- [ ] Tenant ID, owner, plan, region, deployment model và system of record được xác định.
- [ ] Lifecycle state machine có transition hợp lệ, trạng thái lỗi và manual intervention.
- [ ] Control plane và data plane có ranh giới quyền, network và trách nhiệm rõ.
- [ ] Onboarding có xác thực, idempotency, duplicate check và readiness gate.
- [ ] Provisioning dùng resource ID/ownership tag ổn định và có retry/compensation.
- [ ] Cấu hình, entitlement, quota và secret có version, precedence, audit và rollout.
- [ ] Data plane xác định tenant context từ identity tin cậy; mọi truy vấn bảo toàn tenant scope.
- [ ] Suspension thu hồi session/token, dừng job và xác minh access blocked.
- [ ] Reactivation kiểm tra nguyên nhân, subscription, credential và health.
- [ ] Migration có inventory, snapshot, delta sync, validation, quiesce và cutover epoch.
- [ ] Một write owner được xác định trong mọi giai đoạn migration; split-brain được ngăn chặn.
- [ ] Rollback window, reverse sync hoặc forward recovery đã được quyết định.
- [ ] Deletion xác minh authority, legal hold, export, retention và approval.
- [ ] Deletion inventory bao gồm database, object, cache, search, queue, identity, logs và backup.
- [ ] DELETED có định nghĩa chính xác; backup expiry và restore-purge policy được ghi rõ.
- [ ] Lifecycle workflow có idempotency, retry budget, checkpoint, timeout và manual recovery.
- [ ] Có audit, correlation ID, dashboard, alert và reconciliation resource.
- [ ] Provisioning, migration và deletion có concurrency/rate limit theo region/cell.
- [ ] Chi phí resource được gắn tenant/owner và có orphan cleanup.
- [ ] Đã diễn tập onboarding fail, migration fail, cutover rollback, suspension và deletion blocked.

**Điểm cốt lõi:** tenant lifecycle là một quy trình quản trị có trạng thái, trải qua nhiều hệ thống và nhiều ranh giới bảo mật. Onboarding cần idempotency và readiness; cấu hình cần version và policy precedence; migration cần snapshot, delta, validation, một write owner và cutover có fencing; deletion cần xác thực, retention/legal hold, inventory và bằng chứng ở cả bản sao. Khi các bước này được điều phối và quan sát tốt, nền tảng có thể phục vụ nhiều tenant an toàn, mở rộng có kiểm soát và giảm rủi ro vận hành.
