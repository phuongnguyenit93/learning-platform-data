# Thiết kế hạ tầng bất biến và thay thế tài nguyên an toàn

Một máy ảo, node Kubernetes hoặc database instance chạy lâu ngày thường tích lũy nhiều thay đổi: package được cài thủ công, file cấu hình được sửa trực tiếp, security group được mở tạm, phiên bản runtime khác với môi trường ban đầu. Khi cần mở rộng hoặc khôi phục, nhóm vận hành không còn biết chính xác tài nguyên đang chạy được tạo từ cấu hình nào. Việc sửa tại chỗ có thể giải quyết sự cố trước mắt nhưng làm môi trường ngày càng khó tái tạo và khó kiểm chứng.

**Hạ tầng bất biến (immutable infrastructure)** giải quyết vấn đề đó bằng cách tạo tài nguyên mới từ một định nghĩa và artifact đã được kiểm tra, chuyển workload sang tài nguyên mới, rồi loại bỏ tài nguyên cũ sau khi xác minh. Thay đổi được triển khai thành phiên bản mới thay vì chỉnh sửa thủ công máy chủ đang chạy. Cách tiếp cận này phù hợp với Infrastructure as Code (IaC), image bất biến, deployment automation và chiến lược thay thế như blue-green hoặc canary.

Thay thế tài nguyên an toàn đòi hỏi nhiều hơn việc tạo một VM mới. Cần giữ đúng identity, network, secret, dữ liệu, kết nối, state, DNS, quyền và khả năng rollback. Với database hoặc tài nguyên có state, không thể đơn giản hủy bản cũ ngay sau khi bản mới khởi động. Bài học này trình bày cách thiết kế quy trình thay thế có kiểm soát, tránh downtime, mất dữ liệu, split-brain và chi phí tài nguyên tồn đọng.

Bài học thuộc chương **Hạ tầng dưới dạng mã** của module **CLOUD_ARCHITECTURE**. Trọng tâm là thiết kế kiến trúc cloud có thể tái tạo, thay thế và phục hồi an toàn, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích immutable infrastructure và phân biệt với sửa đổi tại chỗ.
2. Xác định tài nguyên phù hợp để tạo mới/thay thế và tài nguyên cần chiến lược migration riêng.
3. Thiết kế IaC module, artifact và pipeline có version, review và validation.
4. Quản lý state, resource identity, dependency và drift an toàn.
5. Chọn rolling, blue-green, canary hoặc replacement theo workload và SLO.
6. Thiết kế cutover, health gate, rollback và cleanup có kiểm soát.
7. Bảo vệ dữ liệu, secret, encryption key, network và workload identity trong quá trình thay thế.
8. Thay thế VM, container node, load balancer, database và các tài nguyên stateful theo đúng semantics.
9. Đo hiệu quả thay thế, phát hiện drift và diễn tập tình huống thất bại.

## 2. Immutable infrastructure là gì?

### 2.1. Tư duy thay thế phiên bản

Với cách làm mutable, operator thường truy cập máy đang chạy để cài package, sửa file hoặc cập nhật runtime. Theo thời gian, hai máy cùng vai trò có thể khác nhau vì lịch sử thao tác khác nhau. Theo cách immutable, khi có thay đổi, pipeline tạo một image hoặc artifact mới, triển khai thành nhóm tài nguyên mới, xác minh rồi chuyển traffic.

~~~mermaid
flowchart LR
    OLD[Old image v1] --> OLDVM[Running instances v1]
    CHANGE[Code and config change] --> BUILD[Build image v2]
    BUILD --> TEST[Test and scan]
    TEST --> NEW[Create instances v2]
    NEW --> HEALTH[Health and smoke checks]
    HEALTH --> SWITCH[Switch traffic]
    SWITCH --> RETIRE[Retire v1 after safety window]
~~~

Tài nguyên cũ được giữ trong một khoảng thời gian phục vụ xác minh/rollback nếu chính sách cho phép, sau đó mới bị xóa. Không chỉnh sửa trực tiếp image v1 thành v2; v2 là một phiên bản được tạo mới từ định nghĩa có thể lặp lại.

### 2.2. Immutable không có nghĩa là không thay đổi

Hạ tầng vẫn thay đổi thường xuyên. Điểm khác biệt là mỗi thay đổi được thể hiện thành phiên bản mới, có nguồn gốc và quy trình phát hành. Ví dụ:

- Cập nhật OS package: build image mới.
- Thay application code: build artifact mới và deploy.
- Đổi instance size: tạo replacement theo rollout policy.
- Đổi network policy: thay IaC/config, review plan và áp dụng.
- Đổi database engine version: dùng upgrade/migration procedure riêng.

Không phải mọi tài nguyên đều có thể thay ngay. Một database chứa dữ liệu giao dịch, volume có state hoặc địa chỉ IP đã được allowlist cần quy trình chuyển đổi và giữ tính nhất quán.

### 2.3. Mutable operations vẫn có chỗ dùng

Một số dữ liệu runtime vốn cần cập nhật: autoscaling desired capacity, secret rotation, certificate renewal, feature flag, routing weight hoặc dữ liệu nghiệp vụ. Immutable infrastructure không cấm các thao tác vận hành đó. Nó yêu cầu phân biệt:

- Thay đổi cấu hình được quản lý và có kiểm soát.
- Dữ liệu/runtime state được phép biến đổi.
- Thay đổi thủ công làm lệch định nghĩa chuẩn và không được kiểm soát.

Mục tiêu là tránh snowflake server và thay đổi ngoài quy trình, không phải biến mọi giá trị trong hệ thống thành bất biến tuyệt đối.

## 3. Vì sao cần thay thế tài nguyên an toàn?

### 3.1. Snowflake infrastructure

Snowflake là tài nguyên có cấu hình riêng do lịch sử chỉnh sửa tích lũy. Nó có thể hoạt động nhưng không còn tương đương với IaC hoặc image hiện tại. Khi cần scale hoặc rebuild, nhóm không biết khác biệt nào là thiết yếu và khác biệt nào là vô tình.

### 3.2. Rủi ro của sửa tại chỗ

- Không tái tạo được thay đổi trong môi trường khác.
- Rollback khó vì không biết trạng thái trước đó.
- Patch hoặc package có thể thiếu nhất quán giữa instance.
- Audit không phản ánh đầy đủ thao tác.
- Tài nguyên mới khởi tạo không giống tài nguyên cũ.
- Khi có compromise, khó biết persistence nào còn sót.

### 3.3. Lợi ích của replacement

Tài nguyên được tạo từ artifact chuẩn nên dễ kiểm thử, scale ngang, thay thế khi lỗi và phục hồi sau sự cố. Việc rollout theo nhóm giúp giới hạn blast radius. Thay đổi có thể được đo, phê duyệt và ghi lại như một release.

### 3.4. Đánh đổi

Immutable model thường cần capacity tạm thời để chạy song song tài nguyên cũ và mới, registry/artifact storage, pipeline và automation. Tài nguyên stateful cần migration phức tạp hơn. DNS/cache/session có thể khiến cutover không tức thời. Do đó cần cân bằng giữa độ an toàn, thời gian chuyển, chi phí và khả năng phục hồi.

## 4. Phân loại tài nguyên trước khi thay thế

Không nên dùng một chiến lược giống nhau cho mọi resource. Hãy phân loại theo khả năng thay mới và mức độ giữ state:

| Nhóm tài nguyên | Ví dụ | Chiến lược thường phù hợp | Rủi ro cần quản lý |
|---|---|---|---|
| Stateless compute | VM chạy API, container replica | Rolling, blue-green, canary | Session, connection drain, capacity |
| Cluster node | Kubernetes worker, autoscaling group member | Cordon/drain và replace | Pod disruption, local storage, topology |
| Edge/network | Load balancer, gateway, route, WAF | Parallel resource và routing cutover | IP, DNS, allowlist, connection |
| Stateful storage | Database, volume, object store | Replication, migration, failover | Data consistency, encryption, retention |
| Control plane | IAM role, registry, IaC state backend | Staged policy/config migration | Lockout, privilege escalation, state corruption |
| External dependency | DNS registrar, SaaS integration | Reconfigure/reissue/reconcile | Ownership, credentials, SLA |

### 4.1. Stateless compute

Compute stateless là ứng viên phù hợp nhất cho immutable replacement. Nếu request state được lưu ngoài instance, instance mới có thể nhận traffic sau health check. Tuy vậy, cần bảo đảm graceful shutdown, connection draining, session handling và tương thích phiên bản.

### 4.2. Stateful resources

Database, queue hoặc volume không thể coi như một VM stateless. Tạo mới tài nguyên không tự chuyển dữ liệu. Cần backup/restore, replication, CDC, snapshot, application migration hoặc failover tùy dịch vụ. Xác định rõ nguồn dữ liệu chuẩn và write owner ở mỗi giai đoạn.

### 4.3. Control-plane resources

IAM policy, DNS zone, KMS key và state backend có thể ảnh hưởng toàn bộ môi trường. Thay thế chúng đòi hỏi staged rollout, quyền break-glass và dependency order. Không xóa resource cũ trước khi chứng minh resource mới hoạt động và quyền truy cập vẫn được giữ.

## 5. IaC làm nguồn định nghĩa chuẩn

### 5.1. Desired state và actual state

IaC mô tả trạng thái mong muốn: resource type, image/version, network, identity, scaling, encryption và dependency. Provider/API tạo tài nguyên thực tế từ định nghĩa đó. Pipeline có thể so sánh desired state với actual state để tìm thay đổi.

~~~mermaid
flowchart TD
    CODE[Versioned IaC] --> REVIEW[Review and policy checks]
    REVIEW --> PLAN[Plan / preview]
    PLAN --> APPROVE[Approval]
    APPROVE --> APPLY[Apply to target]
    APPLY --> ACTUAL[Cloud resources]
    ACTUAL --> DRIFT[Drift detection]
    DRIFT --> CODE
~~~

IaC là nguồn chuẩn cho cấu hình được quản lý, nhưng không thay thế inventory thực tế. Khi có drift, cần xác minh nguyên nhân và reconcile; không áp dụng tự động mọi plan nếu có nguy cơ xóa hoặc thay thế resource quan trọng.

### 5.2. Module và interface

Module nên có input/output rõ ràng, validation và default an toàn. Tránh module quá tổng quát với nhiều cờ không tương thích. Input cần bao gồm:

- Environment/region/account target.
- Instance class hoặc compute profile.
- Image digest/version.
- Network/subnet/security policy.
- Workload identity/service account.
- Encryption key reference.
- Scaling và health check settings.
- Tags/labels owner, service, cost center và lifecycle.

Output chỉ nên công bố thông tin cần thiết như resource ID, endpoint hoặc placement; không trả secret plaintext.

### 5.3. Version hóa module và provider

Pin module/provider version để một lần triển khai có kết quả tái lập. Update version theo pull request, review release note, test trong sandbox/canary và kiểm tra plan trước production. Tránh dùng branch nổi hoặc version range không giới hạn cho module hạ tầng nhạy cảm.

### 5.4. Tên và identity tài nguyên

Resource name nên ổn định, có namespace môi trường/service và tránh phụ thuộc dữ liệu bí mật. Nhưng tên ổn định không có nghĩa mọi lần thay thế phải giữ cùng resource ID. Với parallel deployment, tài nguyên mới cần identity riêng rồi routing chuyển qua. Cần định nghĩa resource nào có logical identity ổn định và resource nào có physical identity theo từng generation.

## 6. State file, locking và lifecycle

### 6.1. Vai trò của IaC state

Một số IaC tool lưu state để liên kết resource trong cloud với cấu hình trong code. State có thể chứa resource ID, attribute nhạy cảm và metadata quan trọng. Nếu mất state, tool có thể không biết resource nào đang tồn tại; nếu hai pipeline ghi state cùng lúc, mapping có thể bị hỏng.

### 6.2. Quản lý state an toàn

- Dùng remote backend có encryption và access control.
- Bật locking/lease nếu backend hỗ trợ.
- Version state và bảo vệ backup.
- Tách state theo environment, stack hoặc ownership boundary.
- Không commit state chứa sensitive value vào source repo.
- Giới hạn người/role có quyền read/write state.
- Ghi audit và lưu quy trình recovery state.

### 6.3. Tránh concurrent apply

Không cho hai pipeline cùng apply một state scope. Lock phải có timeout và quy trình xử lý stale lock. Không xóa lock thủ công nếu chưa xác định pipeline cũ đã dừng; thao tác này có thể tạo hai writer.

### 6.4. Import và reconcile

Nếu tài nguyên đã tồn tại nhưng chưa có trong state, import hoặc adoption cần review mapping và ownership. Không để một module mới vô tình nhận sở hữu resource của stack khác. Trước khi import, xác nhận account, region, resource ID và lifecycle owner.

## 7. Build artifact bất biến

### 7.1. Machine image và container image

Tạo image chuẩn từ pipeline đã kiểm soát:

- Base image từ nguồn đáng tin, pin digest/version.
- Cài package từ lockfile hoặc repository đã duyệt.
- Cấu hình user, filesystem, agent và runtime.
- Scan vulnerability và secret.
- Gắn build metadata/provenance.
- Ký artifact khi policy yêu cầu.
- Publish với version/digest bất biến.

Không sử dụng tag mutable như latest làm nguồn duy nhất cho production. Ghi chính xác image ID/digest trong release manifest.

### 7.2. Tách image và runtime configuration

Image chứa application và thành phần nền tảng không phụ thuộc môi trường. Runtime config như endpoint, feature policy và secret được inject khi triển khai từ config/secret manager. Không bake production password, private key hoặc environment-specific config vào image.

### 7.3. Reproducibility

Build nên dùng version pin, lockfile và dependency mirror có kiểm soát. Cùng source và toolchain cần tạo artifact có thể đối chiếu. Dù reproducible build chưa tuyệt đối khả thi, lưu commit, builder, dependency, digest và provenance sẽ giúp điều tra.

## 8. Thiết kế deployment strategy

### 8.1. Rolling replacement

Thay dần instance hoặc replica trong cùng pool. Mỗi lần chỉ loại một phần capacity, tạo bản mới và chờ health check trước khi tiếp tục.

~~~mermaid
flowchart TD
    A[Pool all v1] --> B[Create v2 capacity]
    B --> C[Wait healthy]
    C --> D[Drain subset v1]
    D --> E[Route to v2]
    E --> F{Enough healthy capacity?}
    F -->|Yes| G[Repeat for next subset]
    G --> H[Pool all v2]
    F -->|No| R[Pause / rollback / repair]
~~~

Ưu điểm là cần ít capacity dự phòng hơn blue-green. Đánh đổi là nhiều phiên bản có thể cùng chạy trong rollout; application/database protocol phải tương thích ngược trong cửa sổ đó. Nếu mỗi lần thay có lỗi, cần dừng rollout và không tiếp tục loại các instance khỏe.

### 8.2. Blue-green deployment

Tạo một môi trường mới (green) song song với môi trường hiện tại (blue). Deploy và kiểm thử green, sau đó chuyển traffic qua green. Blue được giữ để rollback trong một khoảng thời gian.

~~~mermaid
flowchart LR
    USERS[Users] --> ROUTER[Traffic router]
    ROUTER --> BLUE[Blue v1]
    ROUTER -. after cutover .-> GREEN[Green v2]
    GREEN --> CHECK[Smoke and business validation]
    CHECK --> KEEP[Keep blue during rollback window]
    KEEP --> CLEAN[Retire blue after approval]
~~~

Blue-green giúp cutover rõ và rollback routing nhanh khi dữ liệu tương thích. Nhược điểm là cần capacity gần gấp đôi trong thời gian song song, đặc biệt tốn kém với database hoặc dedicated resource. Nếu green đã nhận ghi mới, quay lại blue cần replication ngược hoặc quy trình reconcile; chỉ đổi route có thể làm mất dữ liệu.

### 8.3. Canary deployment

Triển khai phiên bản mới cho một tỷ lệ nhỏ traffic hoặc nhóm người dùng trước. Quan sát error rate, latency, saturation và business metric. Tăng traffic theo từng bước nếu đạt ngưỡng; dừng hoặc rollback nếu có dấu hiệu xấu.

Canary phù hợp khi có traffic đủ lớn, routing chính xác và metric có khả năng phân biệt cohort. Với workload ít traffic, kết quả canary có thể không đủ tin cậy.

### 8.4. Chọn chiến lược

| Tiêu chí | Rolling | Blue-green | Canary |
|---|---|---|---|
| Capacity tạm thời | Vừa phải | Cao | Tùy tỷ lệ |
| Khả năng cô lập bản mới | Một phần | Cao | Theo cohort |
| Rollback | Reverse rollout hoặc redeploy | Chuyển route nếu state tương thích | Giảm traffic về bản cũ |
| Mixed versions | Thường có | Có thể tránh ở mỗi environment | Có chủ đích |
| Yêu cầu metric | Health check | Smoke test và readiness | Metric theo cohort |
| Phù hợp | Service stateless, tương thích version | Release lớn, cần cutover rõ | Thay đổi có rủi ro cần kiểm chứng với traffic thật |

## 9. Health gate và điều kiện sẵn sàng

### 9.1. Liveness, readiness và startup

- Liveness xác định process còn hoạt động để runtime quyết định restart.
- Readiness xác định instance có thể nhận traffic.
- Startup probe cho ứng dụng khởi động chậm, tránh liveness restart quá sớm.

Health endpoint không nên chỉ trả 200 khi process còn sống. Readiness cần xác minh dependency thiết yếu theo policy, nhưng tránh query sâu quá thường xuyên làm tăng tải database.

### 9.2. Smoke test

Sau khi resource mới healthy, chạy các kiểm tra nghiệp vụ có kiểm soát:

- Authentication và authorization.
- Đọc dữ liệu mẫu hoặc health transaction không gây side effect.
- Kết nối database/queue/object storage.
- Certificate và outbound integration.
- Metrics/log/trace đang được export.
- Phiên bản schema/config tương thích.

### 9.3. SLO gate

Định nghĩa trước ngưỡng dừng rollout: error rate, p95/p99 latency, saturation, restart count, queue lag hoặc business failure. So sánh với baseline và control group. Không chỉ nhìn health check màu xanh.

### 9.4. Stabilization window

Một instance có thể healthy ngay sau start nhưng lỗi sau vài phút do memory leak, cache warmup hoặc background worker. Giữ stabilization window đủ để phát hiện vấn đề trước khi loại hết capacity cũ.

## 10. Thay thế compute stateless an toàn

### 10.1. Quy trình

1. Build và xác minh image/version mới.
2. Xác nhận capacity, quota, subnet IP và load balancer target.
3. Tạo instance/pod mới với identity và security policy đúng.
4. Chờ startup/readiness và smoke test.
5. Đưa một phần traffic vào bản mới.
6. Theo dõi SLO, business metric, logs và traces.
7. Drain connection/session của bản cũ.
8. Tiếp tục thay các instance còn lại theo batch.
9. Giữ rollback target trong thời hạn đã định.
10. Xóa bản cũ và tài nguyên tạm sau khi phê duyệt.

### 10.2. Graceful shutdown

Trước khi terminate instance:

- Ngừng nhận request mới.
- Drain keep-alive connection và in-flight request.
- Ngừng claim message mới.
- Hoàn tất hoặc nhả lease cho job đang chạy.
- Flush telemetry/buffer theo timeout có giới hạn.
- Xử lý SIGTERM/shutdown hook.

Terminate đột ngột có thể làm request bị retry, message xử lý trùng hoặc transaction dở dang.

### 10.3. Session và sticky connection

Nếu session nằm trong memory của instance, replacement có thể làm người dùng mất phiên hoặc bị đăng xuất. Ưu tiên session store ngoài hoặc token stateless có rotation phù hợp. Với WebSocket/long-lived TCP, cần connection draining và timeout đủ để client reconnect.

## 11. Node và cluster replacement

### 11.1. Kubernetes node

Thay node theo quy trình:

1. Tạo node mới với image, kubelet và policy đã kiểm chứng.
2. Kiểm tra node Ready, labels, taints, CNI và storage driver.
3. Cordon node cũ để không schedule pod mới.
4. Drain có kiểm soát, tôn trọng PodDisruptionBudget và local state.
5. Xác minh workload được reschedule và ổn định.
6. Terminate node cũ sau khi xác nhận không còn workload cần giữ.

### 11.2. Pod disruption

PodDisruptionBudget giới hạn số pod có thể bị gián đoạn cùng lúc cho một workload phù hợp. Nó không bảo đảm ứng dụng có đủ replica hoặc database khỏe mạnh. Cần kiểm tra replica count, topology spread, zone failure và capacity trước khi drain.

### 11.3. Local storage và daemon

Pod dùng local ephemeral storage có thể mất dữ liệu khi node bị thay. DaemonSet, local PV và workload stateful có quy tắc khác với Deployment stateless. Xác định dữ liệu nào cần chuyển, backup hoặc giữ node trước khi drain.

## 12. Thay thế load balancer, IP và DNS

### 12.1. Parallel edge resources

Khi thay load balancer/gateway, có thể dựng resource mới song song và đăng ký target mới. Kiểm tra TLS, health checks, WAF, header handling, timeout và routing policy trước khi đổi DNS hoặc frontend reference.

### 12.2. IP và allowlist

Nếu provider cấp IP mới, đối tác hoặc firewall ngoài có thể chưa allowlist. Có thể dùng static IP/reserved address, cập nhật allowlist trước cutover hoặc giữ cả IP cũ và mới trong giai đoạn chuyển.

### 12.3. DNS TTL không phải thời gian chuyển chính xác

Client, resolver và ứng dụng có thể cache DNS khác TTL khai báo. Hạ TTL trước cutover giúp giảm một phần thời gian cache nhưng không đảm bảo mọi client cập nhật ngay. Giữ endpoint cũ hoạt động trong overlap window nếu có thể và quan sát traffic còn đi tới endpoint cũ.

### 12.4. Connection draining

DNS cutover không chuyển các TCP connection đang mở. Load balancer cần connection draining/termination policy; client cần reconnect/backoff; session và request in-flight phải được xử lý theo SLO.

## 13. Thay thế database và tài nguyên stateful

### 13.1. Không dùng quy trình rolling stateless

Database chứa state có thẩm quyền. Tạo instance mới không tự đồng bộ dữ liệu. Cần một trong các phương án:

- Snapshot/restore khi downtime chấp nhận được.
- Native replication hoặc managed database replica promotion.
- Logical replication/CDC để chuyển delta.
- Database engine upgrade với compatibility/migration procedure.
- Partition/shard migration theo tenant hoặc phạm vi dữ liệu.

### 13.2. Quy trình replica và cutover

~~~mermaid
flowchart TD
    SRC[Current primary] --> SNAP[Initial snapshot / replication]
    SNAP --> DEST[New database target]
    SRC --> DELTA[Replicate ongoing changes]
    DELTA --> DEST
    DEST --> VALIDATE[Validate schema and data]
    VALIDATE --> LAG{Replication lag acceptable?}
    LAG -->|No| WAIT[Wait / tune / abort]
    WAIT --> DELTA
    LAG -->|Yes| FREEZE[Quiesce writes]
    FREEZE --> FINAL[Apply final delta]
    FINAL --> PROMOTE[Promote new primary]
    PROMOTE --> ROUTE[Switch application endpoint]
    ROUTE --> VERIFY[Smoke test and reconcile]
~~~

### 13.3. Write ownership và split-brain

Tại mọi thời điểm cần chỉ có một primary/write owner. Khi cutover:

- Dừng hoặc khóa write tại nguồn.
- Drain transaction đang xử lý.
- Chờ replication lag về ngưỡng chấp nhận.
- Apply delta cuối.
- Fence nguồn cũ để không nhận write.
- Promote đích và đổi endpoint/secret reference.
- Xác minh app và business invariant.

Nếu hai database cùng nhận write độc lập, dữ liệu sẽ phân nhánh. Chỉ đổi DNS mà không fence primary cũ là không đủ.

### 13.4. Rollback sau khi database đích nhận write

Sau cutover, nếu đích đã nhận transaction mới thì quay về nguồn cũ có thể mất dữ liệu. Cần xác định trước reverse replication, dual-write protocol đã kiểm chứng, hoặc forward recovery. Nếu không thể đồng bộ ngược an toàn, rollback window có thể kết thúc ngay khi write mới được chấp nhận; khi đó cần sửa lỗi trên primary mới thay vì chuyển mù quáng về nguồn.

### 13.5. Schema compatibility

Trong rolling deployment, phiên bản app cũ và mới có thể chạy đồng thời. Dùng expand-and-contract:

1. Expand schema theo cách app cũ vẫn tương thích.
2. Deploy app mới đọc/ghi theo schema mở rộng.
3. Chuyển toàn bộ traffic và background worker.
4. Xác minh không còn consumer dùng schema cũ.
5. Contract/xóa cột hoặc constraint cũ trong release sau.

Không gộp việc xóa schema cũ với deploy app mới nếu mixed-version window còn tồn tại.

## 14. Secret, identity và encryption trong replacement

### 14.1. Workload identity

Tài nguyên mới cần identity riêng hoặc workload identity được cấp đúng scope. Không clone machine với credential dài hạn của instance cũ nếu không có cơ chế rotation/revoke. Khi bản cũ bị retire, thu hồi credential, session và certificate không còn cần.

### 14.2. Secret delivery

Runtime lấy secret từ secret manager bằng identity của workload; secret không được bake vào image hoặc IaC state plaintext. Kiểm tra network path, permission và secret version trước khi cutover.

### 14.3. Key compatibility

Nếu dữ liệu được mã hóa bằng key cũ, instance mới cần quyền decrypt key version tương ứng. Không xóa key chỉ vì đã tạo instance mới. Đối với key rotation, dùng giai đoạn overlap và xác minh khả năng đọc dữ liệu cũ.

### 14.4. Revocation sau khi retire

Sau khi old resource không còn phục vụ:

- Thu hồi role/credential không cần thiết.
- Xóa authorized key/certificate cũ theo policy.
- Gỡ firewall rule hoặc allowlist chỉ dành cho endpoint cũ.
- Kiểm tra snapshot/image cũ có chứa secret không.
- Giữ audit và evidence theo retention.

## 15. Drift detection và remediation

### 15.1. Drift là gì?

Drift là khác biệt giữa desired state trong IaC và actual state của cloud resource. Nguyên nhân có thể là thao tác console, automation khác, thay đổi provider default hoặc resource được chỉnh ngoài quy trình.

### 15.2. Phân loại drift

- **Expected operational change:** autoscaling count, runtime status hoặc ephemeral address được thiết kế để thay đổi.
- **Approved change chưa cập nhật IaC:** sửa khẩn cấp có ticket nhưng source of truth chưa được cập nhật.
- **Unapproved change:** thay đổi ngoài quyền hoặc quy trình.
- **Provider-managed change:** thuộc tính do provider điều chỉnh theo service behavior.

Không phải mọi diff đều cần reset về IaC. Cần hiểu semantics của resource trước khi remediation.

### 15.3. Quy trình xử lý

1. Phát hiện drift và xác định resource/attribute.
2. Phân loại expected, approved hay suspicious.
3. Xác định owner, change record và blast radius.
4. Nếu hợp lệ, cập nhật IaC qua review.
5. Nếu trái phép, cô lập/khôi phục theo incident procedure.
6. Chạy plan/validation và audit kết quả.

Không auto-apply plan có destructive replacement khi không có policy hoặc approval rõ ràng.

## 16. Rollback, recovery và cleanup

### 16.1. Rollback decision

Rollback được kích hoạt khi health/SLO gate fail, error rate tăng, data invariant không đạt, security policy bị vi phạm hoặc business workflow hỏng. Phải định nghĩa metric, cửa sổ quan sát, ngưỡng và người có quyền quyết định trước release.

### 16.2. Rollback stateless

Nếu ứng dụng stateless và schema tương thích, có thể chuyển traffic về old pool hoặc redeploy digest cũ. Đảm bảo old pool vẫn được giữ, còn capacity, secrets và network access trong rollback window.

### 16.3. Rollback stateful

Nếu đã có write ở tài nguyên mới, rollback cần reverse sync/reconcile hoặc forward-fix. Không restore snapshot cũ và đè dữ liệu mới trừ khi có quyết định nghiệp vụ rõ về mất dữ liệu.

### 16.4. Cleanup

Chỉ cleanup sau khi:

- Traffic không còn tới resource cũ.
- Connection/in-flight work đã drain.
- Background job/queue consumer không còn phụ thuộc endpoint cũ.
- Data consistency và business validation đạt.
- Rollback window kết thúc hoặc owner chấp nhận rủi ro.
- Backup/retention và security evidence được giữ đúng policy.

Sau đó xóa old resource, IP, volume, snapshot tạm, security rule và secret không còn dùng. Cleanup cần idempotent và có inventory để tránh xóa nhầm resource khác.

## 17. Capacity và chi phí của replacement

### 17.1. Temporary headroom

Rolling/blue-green cần tài nguyên tạm để old và new coexist. Tính trước compute, IP/subnet, quota, connection limit, database replica, storage, load balancer target và autoscaling maximum.

### 17.2. Cost window

Chi phí song song có thể kéo dài nếu validation hoặc approval chậm. Đặt deadline cho rollout, rollback window và cleanup owner. Theo dõi cost theo release/resource generation.

### 17.3. Rate limit replacement

Thay quá nhiều instance cùng lúc có thể làm mất capacity, gây connection surge hoặc overload dependency. Giới hạn batch size/max unavailable, pause giữa các nhóm và monitor saturation.

### 17.4. Quota và IP exhaustion

Parallel environment có thể hết quota hoặc IP trước khi deployment bắt đầu. Preflight check cần kiểm tra quota regional, subnet available IP, registry pull bandwidth và DB connection budget.

## 18. Observability cho replacement workflow

### 18.1. Correlation

Mỗi lần thay thế nên có deployment ID/release ID và resource generation. Gắn correlation vào log, event và audit để nối các thao tác create, validate, shift traffic, drain và delete.

### 18.2. Metrics cần có

| Metric | Ý nghĩa |
|---|---|
| Replacement duration | Thời gian từ tạo tài nguyên mới tới hoàn tất |
| Healthy capacity | Capacity sẵn sàng theo từng generation |
| Traffic share by version | Tỷ lệ traffic tới phiên bản cũ/mới |
| Error rate and latency by version | So sánh SLO giữa các generation |
| Drain duration | Thời gian đóng kết nối và in-flight request |
| Replication lag | Độ trễ đồng bộ stateful resource |
| Rollback count | Tần suất rollout không đạt |
| Orphan resource count | Tài nguyên còn sót sau cleanup |
| Drift count/age | Quy mô và thời gian tồn tại drift |

### 18.3. Audit và change record

Ghi actor/pipeline identity, commit, IaC plan hash, artifact digest, target account/region, resource IDs, approval, thời điểm cutover, rollback decision và cleanup. Không đưa secret vào log hoặc change record.

## 19. Ví dụ: thay thế Booking API trên cloud

### 19.1. Kiến trúc

Booking API chạy ba replica stateless sau load balancer, dùng database managed, Redis session/cache, queue và object storage. Release mới đổi runtime base image và thêm một field schema có tính tương thích.

### 19.2. Kế hoạch

1. Cập nhật IaC và image digest qua pull request.
2. Chạy formatting/validation, policy scan và plan trong staging.
3. Mở rộng database schema theo expand migration.
4. Build, scan và ký image mới.
5. Tạo một replica green, kiểm tra workload identity, secret, network và readiness.
6. Chạy smoke test đọc/ghi trên dữ liệu kiểm thử.
7. Đưa 5% traffic vào green; theo dõi error rate, p95, payment event và DB connection.
8. Tăng traffic theo các bước được phê duyệt nếu canary đạt gate.
9. Drain replica cũ, chuyển toàn bộ traffic và kiểm tra worker/queue.
10. Giữ old pool trong rollback window, sau đó retire và cleanup.

### 19.3. Sơ đồ triển khai

~~~mermaid
flowchart TD
    IAC[Reviewed IaC + release manifest] --> CREATE[Create green resources]
    CREATE --> VERIFY[Verify identity, config, network]
    VERIFY --> TEST[Smoke test]
    TEST --> CANARY[Route small traffic share]
    CANARY --> GATE{SLO and business gate pass?}
    GATE -->|No| BACK[Route back to blue and investigate]
    GATE -->|Yes| RAMP[Increase traffic gradually]
    RAMP --> FULL[Green receives production traffic]
    FULL --> DRAIN[Drain blue and background workers]
    DRAIN --> WINDOW[Rollback window and monitoring]
    WINDOW --> CLEAN[Approve cleanup of blue]
~~~

### 19.4. Tiêu chí hoàn thành

- Green chạy đúng image digest và config version đã phê duyệt.
- Health/readiness và smoke test đạt.
- Error rate/latency trong SLO ở từng traffic step.
- Database schema tương thích với phiên bản chạy trong rollout.
- Queue, session và background work không phụ thuộc vào old pool.
- Không còn traffic hoặc connection cần giữ ở blue.
- Rollback window và cleanup được owner xác nhận.
- IaC/state phản ánh đúng tài nguyên đang hoạt động.

## 20. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Sửa trực tiếp server production | Snowflake và drift tích lũy | Build image mới và replace |
| Dùng tag mutable cho image | Deploy không xác định được artifact | Pin digest/version bất biến |
| Replace database như stateless VM | Mất dữ liệu hoặc split-brain | Replication, quiesce, fencing và cutover |
| Xóa tài nguyên cũ ngay sau create | Mất rollback target | Health gate và rollback window |
| Chỉ dùng liveness làm health gate | Instance sống nhưng không phục vụ được | Readiness, smoke test và SLO gate |
| Không drain connection | Request đang xử lý bị cắt | Graceful shutdown và connection draining |
| Không tính mixed version | App cũ không tương thích schema mới | Expand-and-contract |
| Apply IaC state cũ mù quáng | Thay/xóa nhầm resource | Review plan, drift reconcile và đúng backend |
| Hai pipeline apply cùng state | State corruption hoặc race | Locking và ownership boundary |
| Không fence primary cũ | Hai nơi cùng nhận write | Một write owner và epoch/fencing |
| DNS TTL được coi là cutover tức thời | Client vẫn tới endpoint cũ | Overlap window và traffic observation |
| Không thu hồi credential cũ | Tăng bề mặt tấn công | Revoke và audit sau retire |
| Parallel capacity không được tính trước | Hết quota/IP, rollout dở dang | Preflight capacity check |
| Cleanup không có inventory | Orphan hoặc xóa nhầm tài nguyên | Resource generation/tag và dry-run |

## 21. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Biện pháp và đánh đổi |
|---|---|---|
| **Operational Excellence** | Thay thế có tự động hóa, version, owner và audit không? | IaC pipeline, plan review, release record và drift process |
| **Security** | Image, identity, secret, network và quyền deploy có được xác minh? | Artifact signing, least privilege, workload identity và credential revocation |
| **Reliability** | Có health gate, rollback, data consistency và single write owner không? | Rolling/blue-green, replication, fencing và rehearsal |
| **Performance Efficiency** | Replacement có đủ headroom và không gây connection surge? | Capacity planning, batch size, rate limit và traffic ramp |
| **Cost Optimization** | Tài nguyên cũ/tạm có được cleanup đúng thời điểm? | Cost tagging, rollback deadline và orphan reconciliation |
| **Sustainability** | Có build/redeploy/giữ tài nguyên dư thừa không cần thiết? | Artifact reuse, right-sized overlap window và lifecycle cleanup |

Immutable infrastructure tăng khả năng tái tạo và giảm drift, nhưng chỉ thực sự an toàn khi quy trình thay thế bảo vệ state, identity, dependency và traffic. Automation phải có gate, audit và khả năng dừng khi điều kiện không đạt.

## 22. Bài tập áp dụng

### Bài tập A — VM đã bị sửa thủ công

Ba VM cùng một autoscaling group có package version khác nhau do operator từng patch trực tiếp.

**Câu hỏi:** Làm thế nào đưa môi trường về trạng thái có thể tái tạo?

**Gợi ý:** Kiểm tra drift và xác định cấu hình mong muốn; cập nhật image pipeline/IaC; build image mới; rollout thay thế theo batch; kiểm tra SLO rồi retire instance cũ. Không cố sửa từng VM để làm chúng giống nhau mà không lưu quy trình.

### Bài tập B — Blue-green và database

Green đã nhận 10 phút ghi giao dịch nhưng ứng dụng mới gặp lỗi nghiêm trọng. Blue vẫn chạy nhưng database của nó không nhận các giao dịch mới.

**Câu hỏi:** Có thể chuyển route về blue ngay không?

**Gợi ý:** Không nếu chưa đồng bộ các write phát sinh ở green. Cần reverse replication/reconcile hoặc forward-fix; xác định write owner và freeze trước khi chuyển. Blue-green ở tầng compute không tự tạo rollback an toàn cho data layer.

### Bài tập C — Node drain bị kẹt

Kubernetes node không thể drain vì một pod stateful dùng local storage.

**Câu hỏi:** Cần kiểm tra trước khi terminate node?

**Gợi ý:** Xác định dữ liệu local có thể mất không, workload/controller, persistent volume mode, PDB và quy trình chuyển state. Backup/migrate dữ liệu hoặc xử lý stateful workload trước khi xóa node.

### Bài tập D — DNS cutover

DNS TTL được hạ xuống 30 giây nhưng một số client vẫn gọi endpoint cũ sau 10 phút.

**Câu hỏi:** Vì sao và nên làm gì?

**Gợi ý:** Resolver/client có thể cache khác TTL; connection đang mở không bị DNS thay đổi. Giữ endpoint cũ trong overlap window, quan sát request, drain connection và chỉ cleanup khi traffic đã hết theo tiêu chí.

### Bài tập E — IaC plan muốn replace database

Một thay đổi input khiến plan đề xuất destroy database hiện tại rồi tạo lại vì thuộc tính không hỗ trợ update.

**Câu hỏi:** Có nên approve plan ngay?

**Gợi ý:** Không. Xác định resource lifecycle semantics, backup/PITR, data migration, replica, downtime, retention và cutover. Tách database replacement thành migration có kế hoạch; review destructive action và phê duyệt riêng.

### Bài tập F — Drift do hotfix

Operator mở tạm firewall rule để xử lý incident nhưng quên ghi vào IaC.

**Câu hỏi:** Quy trình sau incident nên gồm gì?

**Gợi ý:** Ghi change record, đánh giá rule còn cần không, đóng hoặc cập nhật IaC qua review, chạy drift check và audit. Nếu rule đã hết mục đích, xóa theo quy trình được phê duyệt.

## 23. Checklist trước khi thay thế tài nguyên production

- [ ] Đã phân loại resource stateless/stateful/control-plane và xác định owner.
- [ ] Desired state nằm trong IaC có version, module/provider được pin và review.
- [ ] State backend được mã hóa, backup, access-controlled và locking hoạt động.
- [ ] Drift đã được phân loại; plan không chứa destructive replacement ngoài dự kiến.
- [ ] Image/artifact có digest/version bất biến, scan và evidence phù hợp.
- [ ] Runtime config/secret/key được inject an toàn, không bake vào image.
- [ ] Capacity, quota, subnet IP, connection và dependency headroom đã được kiểm tra.
- [ ] Replacement strategy (rolling, blue-green, canary hoặc migration riêng) được chọn theo SLO/state.
- [ ] Readiness, smoke test, SLO gate và stabilization window được định nghĩa.
- [ ] Graceful shutdown, connection draining, session và queue handling đã được kiểm tra.
- [ ] Database/stateful resource có backup, replication, validation và write-owner/fencing plan.
- [ ] Schema tương thích với mixed-version window hoặc dùng expand-and-contract.
- [ ] DNS, IP allowlist, certificate, WAF và route có overlap/cutover plan.
- [ ] Workload identity, secret version và encryption key tương thích ở tài nguyên mới.
- [ ] Rollback có điều kiện, owner, thời hạn và phương án với dữ liệu đã ghi mới.
- [ ] Deployment ID/resource generation được gắn vào log, metric và audit.
- [ ] Cleanup chỉ chạy sau drain, validation, rollback window và approval.
- [ ] Credential, network rule và artifact cũ được revoke/retire theo policy.
- [ ] Có reconciliation để phát hiện orphan resource, drift và cost tồn đọng.
- [ ] Đã diễn tập replacement failure, stateful cutover và rollback trước release quan trọng.

**Điểm cốt lõi:** immutable infrastructure thay đổi bằng cách tạo phiên bản tài nguyên mới, xác minh rồi chuyển workload, sau đó mới retire phiên bản cũ. Quy trình an toàn phải phân loại state, quản lý IaC state và drift, pin artifact, kiểm tra health/SLO, drain traffic và giữ một write owner cho dữ liệu. Blue-green hoặc rolling chỉ giải quyết cách thay compute; database, identity, DNS, key và dependency cần kế hoạch riêng. Chỉ cleanup khi đã chứng minh phiên bản mới hoạt động, dữ liệu nhất quán và rollback window được xử lý.
