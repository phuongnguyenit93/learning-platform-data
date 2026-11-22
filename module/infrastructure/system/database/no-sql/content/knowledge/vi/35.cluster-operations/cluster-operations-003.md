# Cấu hình môi trường, tham số và quản lý thay đổi có kiểm soát

Một cụm NoSQL có thể vận hành ổn định nhiều tháng rồi gặp sự cố chỉ sau một thay đổi tưởng như nhỏ: tăng số connection của ứng dụng khiến database bị quá tải; giảm timeout làm SDK retry hàng loạt; bật một tham số compaction nhưng quên rằng nó chỉ có hiệu lực sau khi khởi động lại node; hoặc sử dụng nhầm cấu hình staging trên production. Khi có nhiều máy, nhiều vùng, nhiều dịch vụ và hàng trăm tham số, việc thay đổi cấu hình trở thành một bài toán **tính đúng đắn, tính sẵn sàng và quản trị rủi ro**, không đơn thuần là chỉnh một file YAML.

Bài học thuộc chương **Vận hành cụm**, module **Database No SQL**, hướng dẫn cách thiết kế cấu hình theo môi trường, phân loại tham số, lưu phiên bản, triển khai có kiểm soát và xác minh kết quả. Các kỹ thuật được đặt trong bối cảnh hệ NoSQL phân tán: replica sets, shards, partitions, consistency levels, cache/storage engines, managed database và những ứng dụng dùng driver để truy cập cluster.

> **Nguyên tắc chính:** Mỗi thay đổi cấu hình cần có **mục tiêu**, **phạm vi tác động**, **giới hạn an toàn**, **người chịu trách nhiệm**, **kế hoạch triển khai/hoàn tác**, và **bằng chứng đo lường sau thay đổi**. Cấu hình có hiệu lực trên máy chủ có thể khác cấu hình đang nằm trong Git; cần xác nhận cả hai.

Các tham số và giá trị trong ví dụ chỉ là **minh họa để học**, không được áp dụng trực tiếp lên production. Cách đặt tên, khả năng reload nóng, restart, rolling update, consistency và API quản trị khác nhau theo engine/phiên bản/topology. Khi vận hành thực tế, phải tra cứu tài liệu đúng phiên bản và kiểm tra các điều kiện của cụm.

## 1. Cấu hình môi trường là gì?

**Cấu hình** là tập các giá trị quy định ứng dụng hoặc cơ sở dữ liệu hoạt động như thế nào mà không nhất thiết phải thay mã nguồn:

- Endpoint/seed nodes, database/cluster name, topology và region.
- Số connection, timeout, retry, concurrency, pool limits.
- Cache size, memory limits, compaction/flush/tombstone policy.
- Replication, consistency, write concern/read preference khi phù hợp.
- Authentication, TLS/mTLS, permissions, key references và network policy.
- Logging, metrics, tracing sampling và audit.
- Retention, TTL, backup, snapshot/restore, CDC.
- Feature flags và tốc độ rollout.
- Quotas, rate limits, maintenance jobs và capacity budgets.

**Environment (môi trường)** là tập tài nguyên và chính sách triển khai có mục tiêu riêng như local, development, test, staging, production, disaster recovery (DR). Không phải mỗi môi trường chỉ là một giá trị `ENV=prod`. Mỗi môi trường có thể khác **quyền**, **network**, **khả năng phục hồi**, **dữ liệu**, **quy mô**, **SLO** và **quy trình thay đổi**.

Một cấu hình production không tốt nếu nó “đúng cú pháp” nhưng vượt memory budget hoặc phá điều kiện có quorum.

## 2. Các lớp cấu hình của một hệ NoSQL

Một API truy cập NoSQL thường có ít nhất các lớp:

| Lớp | Nội dung | Ví dụ |
|---|---|---|
| Ứng dụng | Business flag, pagination, timeout tổng | `checkout.requestDeadlineMs` |
| Driver/SDK | Connection pool, retry, read/write policy | `maxConnections`, `requestTimeout` |
| Database | Storage engine, memory, compaction, replication | Cache, replica/member settings |
| Cluster/topology | Node roles, rack/AZ, sharding, routing | Replica placement, seed/discovery |
| Hạ tầng | CPU/memory/disk/network, process/container | Resource limits, storage class |
| Bảo mật | Identity, certs, policy, KMS refs | TLS, service account, permissions |
| Dữ liệu/pipeline | TTL, CDC, index mappings, data retention | Backup frequency, consumer lag |
| Vận hành | Metrics, log levels, alert/rate limits | Slow query sampling, job concurrency |

Một thay đổi ở tầng driver có thể tạo tác động ở database; một thay đổi container memory có thể khiến cache engine bị OOM dù DB config không đổi. **Phải đánh giá cấu hình theo đường đi end-to-end, không theo file chứa tham số.**

## 3. Desired state, observed state và effective state

Ba trạng thái quan trọng:

1. **Desired state**: cấu hình mong muốn đã được review và lưu trong hệ quản lý.
2. **Deployed/observed state**: artifact/file/ConfigMap/parameter group hiện đang gắn cho workload.
3. **Effective runtime state**: giá trị thực sự đang được process/cluster áp dụng.

Ví dụ:

~~~text
Git desired:
  maxConnections = 50

ConfigMap deployed:
  maxConnections = 50

Running JVM:
  maxConnections = 20 (đã khởi động trước khi config được cập nhật)
~~~

Đây là **configuration drift hoặc pending reload**. Vì vậy việc merge Git không đủ chứng minh thay đổi đã có hiệu lực. Cần cách đọc hoặc suy ra **effective config** từ admin API, startup log được kiểm soát, runtime metrics hay trạng thái do nhà cung cấp cung cấp.

Ngược lại, một operator sửa trực tiếp production thành 100 trong khi Git vẫn 50 có thể khiến deploy tiếp theo bất ngờ đưa giá trị về 50.

## 4. Cấu hình không phải tất cả đều là giá trị tùy ý

Có những ràng buộc:

- **Type**: integer, duration, boolean, enum, URL, list.
- **Range**: TTL không âm, pool size hợp lệ, rate limit có mức tối thiểu.
- **Unit**: ms khác s; bytes khác MiB.
- **Dependency**: tổng memory budget không vượt container limit.
- **Compatibility**: tham số có thể đổi tên/semantics giữa versions.
- **Scope**: per-request, per-client, per-node, per-cluster, per-tenant.
- **Lifecycle**: dynamic reload, restart process, rolling restart, cluster migration.
- **Security**: giá trị public config hay secret reference.
- **Invariants**: quorum, replication placement, dữ liệu chưa được xác nhận backup.

Ví dụ một timeout 200 không rõ đơn vị là 200 ms hay 200 s, và hành vi retry có thể làm tổng thời gian vượt ngân sách. **Một hệ thống cấu hình phải ghi type, đơn vị, default và phạm vi**.

## 5. Cấu hình khác feature flag và business data

| Loại | Ý nghĩa | Ai quản lý | Ví dụ |
|---|---|---|---|
| Static deployment config | Gắn với bản triển khai/process | Platform/ops | DB endpoint, memory limit |
| Dynamic runtime config | Có thể đổi khi service đang chạy nếu hỗ trợ | Ops/automation | Rate limit |
| Feature flag | Điều chỉnh luồng ứng dụng có kiểm soát | Product/engineering | Enable new read model |
| Business reference data | Dữ liệu domain, có version/owner | Domain team | Tax table, shipping regions |
| Secret | Credential/key có yêu cầu bảo vệ riêng | Security/platform | DB password, API token |
| Schema/index definition | Mô tả dữ liệu và truy cập | DBA/engineering | Index keys, TTL index |
| Infrastructure as Code | Desired topology/infra | Platform/SRE | Cluster capacity, network |

Tách những loại này để tránh để một trang feature flag trở thành nơi thay credential, hoặc một bảng dữ liệu nghiệp vụ được dùng làm bảng điều khiển thông số cluster không có kiểm soát.

## 6. Inventory cấu hình: biết tham số nằm ở đâu và ai sở hữu

Một **configuration inventory** nên có:

| Trường | Mục đích |
|---|---|
| Name/key | Tên canonical của tham số |
| Layer/component | App, driver, node, cluster, infra |
| Owner | Team chịu trách nhiệm |
| Type/unit/default | Ngăn sai đơn vị và suy đoán |
| Allowed values/range | Kiểm tra hợp lệ |
| Effective scope | Node, cluster, tenant, request |
| Change method | Git/IaC/API/console/secret rotation |
| Application mode | Hot reload, restart, rolling, migration |
| Dependencies | Tham số/nguồn lực liên quan |
| Security classification | Public/internal/secret |
| Risk tier | Có ảnh hưởng dữ liệu, quorum, SLO? |
| Evidence source | Cách kiểm tra effective config |
| Rollback approach | Hoàn tác logic/hạ tầng/dữ liệu |
| Last-reviewed | Tuổi của giả định |

Inventory không nhất thiết là bảng thủ công duy nhất; có thể kết hợp schema validation, IaC, catalog nội bộ và runtime discovery. Điểm cốt lõi là **không có “tham số vô chủ” ảnh hưởng production**.

## 7. Phân loại thay đổi theo blast radius

| Cấp | Đặc điểm | Ví dụ | Kiểm soát điển hình |
|---|---|---|---|
| Thấp | Chỉ ảnh hưởng UI/debug, dễ hoàn tác | Tăng log level có giới hạn thời gian | Review/monitor |
| Trung bình | Có thể ảnh hưởng hiệu năng cục bộ | Driver pool limit của một canary | Canary, metrics, rollback |
| Cao | Ảnh hưởng nhiều services/nodes | Compaction settings, global cache size | Change plan, maintenance window |
| Rất cao | Có thể ảnh hưởng dữ liệu, bảo mật hoặc availability cụm | Replication layout, cert rotation, destructive index/data migration | Approval, backups, recovery rehearsal |

Không gán cấp chỉ bằng tên tham số. Tăng log level từ INFO lên DEBUG có thể là rủi ro cao nếu tạo I/O lớn hoặc lộ PII. Một thay đổi “chỉ application flag” vẫn có thể khiến mọi requests chuyển qua query scan đắt.

**Blast radius** gồm số node, tenant, request, region, dữ liệu và privilege bị ảnh hưởng nếu thay đổi sai.

## 8. Tại sao môi trường staging cần giống production nhưng không sao chép toàn bộ?

Staging hữu ích khi giống production ở các **semantics quan trọng**:

- Engine/driver phiên bản tương thích.
- Topology/replication class gần với điều cần kiểm tra.
- TLS/authentication và policy shape.
- Schema, index, partition keys.
- Feature flags mặc định và config loading.
- Query/update patterns.
- Memory/disk/network boundaries ở tỷ lệ phù hợp.
- Monitoring/alerts và rollback mechanism.

Nhưng staging không nên copy nguyên production secrets hoặc raw PII. Nó cũng có thể nhỏ hơn production và có traffic khác, vì vậy **test qua staging không chứng minh production sẽ có cùng hiệu năng hoặc failure behavior**.

Một cách là chia rõ **functional parity** (semantics) và **capacity parity** (khối lượng/tải). Không chấp nhận claim “đã test staging” cho thay đổi compaction 10 TB khi staging chỉ có 1 GB dữ liệu.

## 9. Ma trận khác biệt theo môi trường

Ví dụ:

| Thuộc tính | Local | Test/Staging | Production | DR |
|---|---|---|---|---|
| Dataset | Synthetic nhỏ | Anonymized/representative | Real có kiểm soát | Replicated/backup |
| Authentication | Dùng tài khoản dev giới hạn | Bám policies production | Least privilege + audited | Recovery identity riêng |
| Database endpoints | Local/emulator | Staging cluster | Production cluster | DR endpoint |
| Replication | Có thể đơn giản | Tương tự điều cần test | Theo availability contract | Theo RPO/RTO |
| TLS | Đúng test boundary | Bật/validate | Bắt buộc theo policy | Bắt buộc theo policy |
| Backup | Tùy use case | Restore drill | Theo policy đã kiểm chứng | Restore/failover plan |
| Quotas | Nhỏ | Đủ load test mục tiêu | Từ capacity plan | Từ recovery plan |
| Debug logs | Có thể chi tiết | Giới hạn | Redacted, rate-limited | Theo incident policy |
| Change approval | Developer | Engineering review | Controlled approval | Incident/recovery workflow |

Không dùng production DB làm môi trường development vì tiện: vừa rủi ro dữ liệu vừa khiến job thử nghiệm cạnh tranh tài nguyên.

## 10. Quy tắc ưu tiên cấu hình (precedence)

Một application có thể đọc config từ nhiều nguồn:

~~~text
1. Built-in defaults
2. Versioned base config
3. Environment-specific overlay
4. Deployment parameters
5. Secret references
6. Runtime overrides / operator setting
~~~

Đây là **thứ tự minh họa**, không phải thứ tự tự động của mọi framework. Phải biết chính xác precedence của Java/Spring, CLI, container, cloud parameter group hoặc engine đang dùng.

Vấn đề thường gặp:

- Environment variable vô tình ghi đè config file.
- Một flag CLI giữ giá trị cũ dù Git đã đổi.
- Secrets manager trả phiên bản khác với mong đợi.
- Node A được reload, node B vẫn dùng giá trị cũ.
- Default thay đổi sau nâng cấp driver/DB version.
- Operator override chỉ tồn tại tới lần restart.

Nên có startup record/an toàn về **tên cấu hình, hash/version và trạng thái áp dụng**, nhưng không log raw secrets.

## 11. Configuration as Code và GitOps: phiên bản, review, truy vết

Một cấu trúc logic:

~~~text
config/
  base/
    order-api.yaml
    db-client.yaml
  environments/
    dev/
      overrides.yaml
    staging/
      overrides.yaml
    production/
      overrides.yaml
  schemas/
    app-config.schema.json
  policies/
    allowed-parameters.yml
~~~

Lợi ích:

- Lịch sử thay đổi, ai đề xuất/duyệt, lý do.
- Diff rõ old→new.
- Automated validation trên types/units/policies.
- Tái tạo được desired state.
- Có thể dùng một commit để rollback với thay đổi có tính đảo ngược.
- Giảm “cấu hình bí mật chỉ nằm trên máy operator”.

Giới hạn:

- Git **không phải nơi lưu plaintext secrets**.
- Merge không đồng nghĩa deploy thành công hay effective config đã đổi.
- Một số thay đổi phụ thuộc data migration/quorum, không rollback được chỉ bằng revert.
- Config drift vẫn có thể xảy ra qua console/hotfix.
- Approval trong Git không thay monitoring ở production.

## 12. Secrets phải có vòng đời riêng với tham số thông thường

Các giá trị nhạy cảm gồm password, token, private keys, client certificates, encryption credentials.

Không nên:

~~~yaml
database:
  password: "production-secret-here"
~~~

Nên dùng **reference tới secret đã được cấp quyền** theo cơ chế cụ thể:

~~~yaml
database:
  endpoint: "orders-db.internal.example"
  credentials:
    source: "managed-secret-reference"
    reference: "orders-api/prod/db-auth"
~~~

Ví dụ YAML chỉ mô tả khái niệm; tên key và cơ chế resolve không chuẩn hóa cho mọi ứng dụng.

Quản lý secrets cần:

- Ai được đọc/sửa/rotate/revoke.
- Thời hạn và phiên bản.
- Cơ chế refresh khi process đang chạy.
- Cách chuyển đổi trong cửa sổ overlap nếu có hai credentials hợp lệ.
- Logs/audit mà không in secret.
- Cách xử lý compromise và break-glass.
- DR/backup có key tương ứng để decrypt.
- Không làm hiện token trong command-line arguments, crash dumps hoặc metrics labels.

**Secret rotation là một thay đổi production**, có thể làm connections rớt hoặc authentication thất bại; cần canary, quan sát auth failures và rollback/recovery cụ thể.

## 13. Schema validation: kiểm tra trước khi cấu hình đi tới production

Một cấu hình không hợp lệ nên bị chặn **trước** khi khởi chạy service hoặc thay đổi database:

- Key không tồn tại hoặc bị gõ sai.
- Duration thiếu đơn vị.
- Number nằm ngoài range.
- Tham số mới không tương thích với phiên bản engine hiện tại.
- Cấu hình mâu thuẫn: max heap và off-heap vượt container memory.
- TLS bật nhưng thiếu trust material hợp lệ.
- Retry attempts × request timeout vượt deadline nghiệp vụ.
- Endpoint sản xuất bị gắn vào môi trường staging.
- Duplicate/contradictory settings giữa CLI/env/file.
- Một cấu hình phá policy security, retention hoặc replication.

Ví dụ file **dùng cho bài thực hành**:

~~~yaml
service:
  name: order-api
  environment: staging
database:
  clusterRef: orders-staging
  connectTimeout: 2s
  requestTimeout: 700ms
  maxPoolConnections: 40
resilience:
  maxAttempts: 2
  totalDeadline: 1200ms
observability:
  slowOperationThreshold: 400ms
~~~

Schema policy có thể kiểm tra `maxPoolConnections` là số nguyên dương, `environment` thuộc enum, `totalDeadline` không vượt request budget, và `clusterRef` trùng environment. **Không suy cấu hình này là cú pháp hợp lệ cho một framework cụ thể**; nó mô tả các constraints cần đưa vào cấu hình thật.

## 14. Static, dynamic và rolling-change parameters

Phân loại:

| Loại | Đặc điểm | Cách xác minh |
|---|---|---|
| **Static/startup** | Được đọc khi process khởi động | Kiểm tra deployment/restart và runtime settings |
| **Dynamic/hot-reload** | Có thể đổi khi process đang chạy | Runtime introspection, metrics, audit |
| **Node-local** | Tác động một node | Xem từng node, không suy từ cluster average |
| **Cluster-wide** | Cần đồng bộ/chấp thuận theo topology | Kiểm tra toàn bộ members và consensus/control plane |
| **Persistent** | Giá trị còn qua restart theo engine | So trạng thái sau restart |
| **Ephemeral override** | Có thể mất sau restart/redeploy | Ghi rõ thời hạn và mechanism |
| **Data-coupled** | Có thể cần migration/reindex/rebuild | Theo dõi data state, không chỉ config state |

Một tham số có thể vừa “dynamic” vừa “cluster-wide”, hoặc “node-local” và “persistent”. Không coi bảng là các nhóm loại trừ nhau.

### 14.1. Không đoán hot reload

Ví dụ thay một file được mount trong container không đồng nghĩa ứng dụng đã reload. Có framework quan sát file; có framework chỉ đọc lúc startup. Một số cloud DB parameter groups có cờ cần reboot; các group khác áp ngay nhưng gây hệ quả sau một khoảng thời gian.

Trước thay đổi, xác minh: **cách cập nhật, tác động lên connections, restart requirement, và dấu hiệu runtime đã dùng giá trị mới**.

## 15. Timeout budget xuyên ứng dụng, driver và database

Một stack có nhiều timeout:

~~~text
Client HTTP deadline
  -> API request budget
      -> service queue/acquire
          -> DB driver request timeout
              -> network and server execution
      -> retries/backoff
  -> response serialization
~~~

Nếu API deadline 900 ms nhưng SDK cho phép 3 attempts × 800 ms cùng hai lần backoff, worker có thể tiếp tục work sau khi client đã bỏ cuộc (tùy cancellation semantics), gây tải vô ích.

Một budget giả định:

~~~text
Total HTTP budget:           1000 ms
Auth/validation:              100 ms
DB pool + attempts + retry:   650 ms
Serialization/downstream:     150 ms
Reserved margin:             100 ms
~~~

Không nên chỉ cộng worst-case trừu tượng để suy mọi giao thức đều hoàn thành đúng 1.000 ms; network, cancellation và failover có thể khiến deadline khác. Mục tiêu là **tạo một tổng ngân sách có giới hạn và được quan sát**, thay vì các timer độc lập khiến tail latency không kiểm soát.

### 15.1. Idempotency khi thay retry config

Một write sau timeout có thể đã commit. Tăng retry từ 1 lên 5 mà thiếu stable business id/idempotency có thể tạo duplicate charge/order. Một thay đổi thuần SDK có thể phá invariant.

Với conditional conflicts, retry chỉ hợp lệ nếu quy tắc nghiệp vụ cho phép. Với throttling, dùng backoff có jitter và retry budget; không bật retry vô hạn để “nâng availability”.

## 16. Connection pools và tổng sức ép lên cluster

Một API chạy 12 pods, mỗi pod có 60 connections tối đa:

\[
C_{\mathrm{potential}}=12\times60=720.
\]

Nếu autoscale thành 36 pods:

\[
C_{\mathrm{potential}}=36\times60=2160.
\]

Số connections này không nhất thiết đều active, nhưng là **giới hạn tiềm năng** có thể vượt dự toán nguồn. Tăng pool size có thể giúp giảm wait cục bộ nhưng đẩy DB vào queue/saturation.

Khi đổi pool:

- So số pods/instances và server-side connection limits.
- Đo pool acquire p95/p99, active/idle, waiting requests.
- Kiểm tra queries giữ connection lâu, transaction lifetime, leaks.
- Giới hạn concurrency ở API/job layer.
- Theo dõi network/TLS handshakes và connection churn.
- Xem driver multiplexing/pooling semantics theo phiên bản.

**Pool size không phải throughput knob độc lập**. Ngân sách capacity cần xét cả số workload replicas và database topology.

## 17. Consistency, replication và durability là thay đổi rủi ro cao

Tham số consistency/read preference/write concern không chỉ ảnh hưởng latency; chúng có thể đổi **bảo đảm nhìn thấy dữ liệu và khả năng chịu lỗi**.

Ví dụ các lựa chọn theo engine:

- MongoDB: read concern/write concern/read preference và replica set topology.
- Cassandra/ScyllaDB: consistency levels và replication strategy/keyspace RF.
- DynamoDB: strongly consistent read khi API hỗ trợ, eventual reads, global table semantics.
- Redis: persistence/replication/failover configuration nếu dùng làm nguồn có ý nghĩa durability.
- Search/read model: refresh, replica và index update visibility; thường khác transactional source.

Một thay đổi “để request nhanh hơn” có thể chuyển từ read hiện thời sang read stale hoặc thay write acknowledgement. Trước khi phê duyệt phải trả lời:

1. Invariant nghiệp vụ nào cần bảo vệ?
2. Có cần read-your-writes, monotonic reads, conditional updates?
3. Khi replica lỗi, điều kiện quorum/failover có còn đúng?
4. Khi ACK success, điều gì đã được ghi bền theo engine?
5. Thay đổi này có làm tăng khả năng unknown outcome?
6. Đường rollback có cần data reconciliation không?

**Không tự hạ consistency để sửa p99** nếu business operation cần bảo đảm mạnh hơn.

## 18. Replication factor và placement: không coi là sửa một số

Trong một NoSQL cluster, replication factor (RF) và placement/rack/AZ ảnh hưởng:

- Số bản sao có thể phục vụ khi node/zone lỗi.
- Write/read quorum theo hệ.
- Dung lượng lưu trữ và network replication.
- Recovery/rebalance/streaming time.
- Partition placement và hot-spot skew.
- Cost và thời gian bảo trì.

Giả sử policy yêu cầu chịu mất một AZ. Tăng RF nhưng dồn các replicas vào cùng AZ **không đạt mục tiêu**. Thay đổi RF/placement có thể đòi data streaming/repair, không chỉ đổi metadata.

Rolling updates phải bảo đảm **các replicas còn khả dụng đáp ứng consistency** trong khi một node bảo trì. Tính số lỗi có thể chịu theo topology thực tế, không dùng công thức đơn giản áp dụng cho mọi hệ.

## 19. Cache, memory và disk: budget tài nguyên phải được tính chung

Ví dụ một NoSQL engine trong container 16 GiB:

~~~text
Application/DB heap:           8 GiB
Off-heap/direct memory:        2 GiB
Thread stacks/native overhead: 1 GiB
OS page cache and buffers:     3 GiB
Safety margin:                 2 GiB
Total:                        16 GiB
~~~

Đây là **phân bổ minh họa**, không phải một memory layout bắt buộc. Một engine có thể sử dụng mmap, OS page cache hoặc block cache với cơ chế khác. Tăng cache từ 3 lên 8 GiB mà không xét off-heap, native và compaction memory có thể dẫn tới OOM hoặc swap/reclaim.

Thay tham số memory cần:

- Đo RSS/working set/heap/off-heap trước.
- Có headroom theo peak workload.
- Xem process và cgroup/container limits.
- Xem GC pauses, allocation và page faults.
- Xem cache hit/eviction, disk read pressure.
- Thử cold cache sau restart và failover.
- Hiểu liệu giảm cache size có áp ngay hay cần restart.

Tương tự, compaction/index build/backup có thể dùng disk I/O nhiều hơn foreground workload; storage budget phải tính cả background maintenance.

## 20. Retention, TTL, CDC và backups là tham số có hậu quả dữ liệu

Các thay đổi này có thể ảnh hưởng không đảo ngược:

- Giảm TTL khiến dữ liệu bị xóa sớm.
- Giảm event/CDC retention khiến consumer chưa xử lý mất lịch sử.
- Thay backup policy có thể tạo khoảng trống RPO.
- Đổi compaction/tombstone settings có thể tăng chi phí phục hồi hoặc read amplification.
- Tắt audit logs có thể mất bằng chứng điều tra.
- Đổi snapshot/backup encryption key có thể ảnh hưởng restore.
- Giảm search/report retention có thể xóa báo cáo đang được dùng.

**Rollback cấu hình không tự phục hồi dữ liệu đã bị xóa**. Nếu TTL giảm từ 30 ngày còn 2 ngày và dữ liệu đã hết hạn bị loại, tăng TTL lại lên 30 ngày không làm records trở về. Cần backup/restore/replay hợp lệ hoặc chấp nhận mất theo policy.

Với data-coupled changes, phải có **data migration/recovery plan riêng**, không chỉ lệnh revert commit.

## 21. Cấu hình schema và index có thể tạo workload nặng

Thêm index, đổi partition key, bật TTL index hoặc sửa search mapping có thể:

- Quét toàn bộ data để build.
- Tăng write amplification.
- Tạo disk/network traffic lớn.
- Thay plan của các truy vấn hiện hữu.
- Gây block/queue hoặc ảnh hưởng failover.
- Làm consumer/schema không tương thích trong giai đoạn rolling.
- Cần backfill, reindex hoặc rebuild read model.

Nên coi **schema/index change** như một thay đổi có data-phase và traffic-phase: trước tiên deploy readers/writers tương thích, build/backfill có throttle, verify, rồi chuyển query. “Index đã tạo thành công” chưa đủ chứng minh p99 đạt SLO hoặc các readers không gặp schema mismatch.

## 22. Cấu hình và thay đổi do con người: chống nhầm môi trường

Các lỗi thường gặp:

- Dùng production connection string trong job staging.
- CLI context đang trỏ tới cluster khác.
- Script có wildcard thay vì tenant scope.
- Chạy lệnh trên tất cả nodes trong khi cần một canary.
- Export dữ liệu thật ra local folder không được phép.
- Tắt audit/TLS tạm thời rồi quên bật.
- Mở firewall rule 0.0.0.0/0 “để debug”.
- Giữ temporary admin credentials không có expiry.

Controls:

- Env isolation bằng accounts/projects/network/identity.
- Hiển thị rõ target environment, cluster ID, region trước thao tác.
- IaC policy có guardrails reject prohibited configs.
- Temporary access có TTL và auto revoke.
- Privileged change qua JIT/approval khi thích hợp.
- Scripts có explicit scope, dry-run và safety limits.
- Audit action, actor, diff, change ticket và thời gian.

**Confirmation dialog không thay authorization và phạm vi thực thi**. Lệnh đúng cú pháp vẫn có thể tác động nhầm cluster nếu context không được kiểm chứng.

## 23. Change management: request, approval, execution và verification

Một thay đổi có kiểm soát thường đi qua các trạng thái:

~~~mermaid
flowchart TD
    P["Proposed: mục tiêu và phạm vi"] --> R["Review: impact/dependencies"]
    R --> A{"Approved?"}
    A -->|Không| H["Revise / reject"]
    A -->|Có| V["Validate staging/policy"]
    V --> C["Canary / small scope"]
    C --> G{"Guardrails đạt?"}
    G -->|Không| B["Pause / rollback / mitigate"]
    G -->|Có| W["Rolling/full rollout"]
    W --> O["Observe and verify"]
    O --> D["Document effective state"]
~~~

Các bước có thể tự động hóa nhưng cần **dấu vết và điểm dừng**. Change request tối thiểu có:

- **What:** tham số nào, old→new, scope node/tenant/region.
- **Why:** vấn đề/SLI cần cải thiện, giả thuyết.
- **Risk:** availability, durability, consistency, security, cost.
- **When:** lịch triển khai, traffic, maintenance window.
- **How:** commands/automation, rollout order.
- **Verify:** metric, probe, acceptance criteria.
- **Stop:** guardrail nào buộc pause/rollback.
- **Recovery:** rollback/restore/rebuild/failover plan.
- **Owner:** người thực hiện, phê duyệt và trực incident.

Emergency change có thể rút ngắn approval theo policy nhưng vẫn cần lưu lý do, kiểm soát an toàn và hậu kiểm.

## 24. Một change proposal minh họa

Giả sử giảm driver pool max từ 120 xuống 60 để bảo vệ nguồn NoSQL khi autoscale:

~~~yaml
changeId: CHG-2026-0114-01
service: order-api
environment: production
target: database-driver-client
parameter: maxPoolConnections
from: 120
to: 60
scope:
  initial: 1-canary-instance
  next: 10-percent-traffic
  final: all-order-api-instances
reason: reduce-source-connection-pressure
owner: backend-platform
risk: medium
expected:
  - source-connections-not-increasing
  - api-p99-within-slo
guardrails:
  - pool-acquire-p99-within-approved-threshold
  - no-error-budget-burn-regression
rollback:
  - restore-previous-config-version
  - progressive-redeploy
evidence:
  - runtime-effective-config
  - canary-vs-control-dashboards
~~~

YAML chỉ là **mẫu mô tả thay đổi**, không phải cấu hình công cụ cụ thể. Nếu giảm pool làm wait tăng, canary phải dừng; nếu server tiếp tục quá tải, nguyên nhân có thể là query/retries chứ không chỉ pool size.

## 25. Diff không đủ: phải hiểu quan hệ phụ thuộc

Một thay đổi có thể gây chuỗi tác động:

~~~text
Increase app replicas
 -> multiply total driver connections
 -> increase concurrent DB reads
 -> increase source queue/disk/network pressure
 -> increase timeout/retries
 -> increase p99
~~~

Hoặc:

~~~text
Reduce CDC retention
 -> consumer backlog may exceed shorter retention
 -> missing historical events
 -> search/report rebuild becomes incomplete
~~~

Bảng review:

| Thay đổi | Phụ thuộc | Risk phải đánh giá |
|---|---|---|
| Driver pool | Pod replicas, DB connection limit | Pool wait/source saturation |
| Retry/timeout | HTTP deadline, idempotency, throttle budget | Retry storm/duplicates |
| Cache/heap | Cgroup memory, native/OS page cache | OOM/GC/disk misses |
| Replica factor/placement | AZ/rack topology, quorum, streaming | Availability/recovery |
| TTL/CDC retention | Consumer lag, archive, backup | Data loss/unrecoverable gap |
| Index build | Data size, disk headroom, write amplification | Tail latency/space |
| TLS/cert rotation | Client trust stores, overlap | Authentication outage |
| Engine upgrade | Mixed-version and format compatibility | Rolling availability |

Review nên có người hiểu **source, client và operational constraints**. Chỉ xem cú pháp YAML chưa đủ.

## 26. Canary rollout: thay đổi phạm vi nhỏ trước

Canary có thể là một application pod, một phần traffic, một region hạn chế hoặc một node được chọn theo topology; không có nghĩa chọn ngẫu nhiên primary/leader rồi restart.

Quy trình:

1. Ghi baseline cùng operation, traffic mix và khung giờ.
2. Có control group chưa đổi nếu khả thi.
3. Chọn phạm vi nhỏ nhưng đại diện.
4. Theo dõi p95/p99, errors, retries, pool wait, correctness.
5. Quan sát cả server resources và replica health.
6. Định nghĩa số samples/thời gian đủ để kết luận.
7. Mở rộng nếu đạt, dừng/revert khi vượt guardrail.

Không có lỗi trong một phút chưa chứng minh an toàn nếu lỗi chỉ hiện khi peak, compaction, node failover hoặc TTL expiry.

## 27. Rolling update: thứ tự node ảnh hưởng quorum

Một rolling change:

~~~text
Precheck quorum, replicas and disk/network health
  -> drain/coordinate node A
  -> apply config/restart A if required
  -> wait A healthy and caught up
  -> verify reads/writes/replica state
  -> proceed node B
  -> ...
  -> verify all members and effective config
~~~

Phải xác nhận theo engine/topology:

- Khi một member offline, có đủ replica/quorum phục vụ traffic không?
- Có cần controlled primary step-down/leader handoff?
- Một rack/AZ có thể bảo trì bao nhiêu members?
- Node trở lại cần resync và warm cache bao lâu?
- Mixed config/version có tương thích?
- Có chờ replica lag/repair/streaming xong không?
- Có disruption budget/redundancy contract không?
- Tiêu chí nào buộc dừng trước node kế?

**Rolling update không tự bảo đảm zero downtime** nếu topology chưa đủ dự phòng hoặc read/write policy đòi quorum đang thiếu.

## 28. Change budget: không thay mọi thứ cùng lúc

Nếu đồng thời nâng driver, đổi read preference, tăng pool size, chạy index build và bật compression, p99 tăng sau deploy rất khó xác định vì đâu; rollback càng phức tạp.

Một chính sách hợp lý: **mỗi lần chỉ thực hiện một thay đổi rủi ro đáng kể trong một failure domain**, trừ các thay đổi có phụ thuộc chặt và đã được review chung. Có thể bundle những thay đổi nhỏ nhưng vẫn phải biết tác động/rollback của từng phần.

Change freeze có thể cần trong mùa cao điểm, nhưng nên có đường emergency exception được phê duyệt. Không biến quy trình thành việc cấm sửa sự cố khi hệ đang gặp nguy hiểm.

## 29. Maintenance window: tải thấp không đồng nghĩa an toàn

Một khung giờ ít request chưa chắc là lúc có ít background work:

- Backup/snapshot thường chạy ban đêm.
- Compaction, repair và TTL cleanup có thể tăng disk I/O.
- CDC replay/backfill có thể đang đuổi backlog.
- ETL/batch analytics có thể quét source.
- Region A ít traffic nhưng region B cao điểm và chia sẻ cluster.
- Flash sale hoặc event bên ngoài có thể lệch chu kỳ thường.

Trước triển khai, kiểm tra **tải thực**, job schedules, node health, replica lag và khả năng failover. Maintenance window phải đủ để canary, rollout, resync, verification **và rollback** nếu cần; không chỉ đủ thời gian chạy một command.

## 30. Preflight trước thay đổi production

Các kiểm tra điều hành:

1. Change request, owner, approval và lịch còn hiệu lực.
2. Target cluster/region/environment/node roles chính xác.
3. Current desired, observed và effective config đã được ghi.
4. Syntax/type/range/schema validated.
5. Version compatibility, hot reload/restart semantics rõ.
6. Quorum/replica health, lag, disk/memory headroom đạt ngưỡng.
7. Source CPU/I/O/network, app pool/queue, retries ở baseline bình thường.
8. Backup/snapshot và restore prerequisites phù hợp mức risk.
9. Không có job bảo trì mâu thuẫn ngoài kế hoạch.
10. Dashboards/probes/alerts và incident contacts sẵn sàng.
11. Canary scope, rollout order và stop thresholds rõ.
12. Recovery commands/runbook đã chuẩn bị và có quyền thực hiện.
13. JIT admin access/audit đã sẵn sàng.
14. Có kế hoạch nếu node không trở lại hoặc catch-up bị kéo dài.

Không phải mọi mục đều cần cho thay đổi low-risk; với cluster changes ảnh hưởng dữ liệu/quorum thì **preflight quan trọng hơn tốc độ chỉnh tham số**.

## 31. Guardrails: tiêu chí tiếp tục và dừng

| Tín hiệu | Bảo vệ điều gì? | Policy điển hình |
|---|---|---|
| API error-budget burn | Người dùng | Dừng khi burn tăng vượt ngưỡng |
| Read/write p95/p99 | Tail latency | So với SLO và control group |
| DB throttling/rejections | Capacity | Pause nếu kéo dài |
| Replica lag/CDC age | Freshness/recovery | Không restart member kế khi chưa catch up |
| Quorum/member health | Availability | Dừng khi cluster degraded |
| Memory/GC/OOM | Runtime | Dừng khi vượt safety budget |
| Disk free/I/O queue | Storage | Dừng index/build nếu pressure tăng |
| Pool wait/retry amplification | Client load | Dừng nếu queue/retries tăng |
| Business invariants | Correctness | Dừng khi duplicate/oversell/unknown outcomes tăng |
| Security/auth failures | Quyền và secrets | Dừng khi TLS/auth/audit regression |

**Không dùng chung CPU 70% hay p99 200 ms làm ngưỡng production mặc định.** Threshold lấy từ baseline, SLO và risk budget, xét sample count/window và hysteresis để tránh policy bật/tắt do nhiễu.

## 32. Rollback: với config thường dễ, với data không phải vậy

| Loại thay đổi | Hoàn tác thế nào | Hạn chế |
|---|---|---|
| App flag/timeout | Revert config, redeploy | Cần verify process dùng giá trị cũ |
| Driver pool | Trả setting, controlled restart | Connection churn/cold start |
| Static DB parameter | Đổi và restart theo topology | Quorum/replica health |
| Index/schema | Backfill/rebuild hoặc switch schema path | Không phải mọi operation đảo được |
| TTL/retention giảm | Restore/replay nếu data đã mất | Có thể không còn nguồn |
| Replica placement | Data streaming/migration | Disk/network và thời gian |
| TLS/key rotation | Điều chỉnh trust/keys theo overlap | Compromise có thể buộc revoke key cũ |
| Engine upgrade | Theo upgrade/downgrade support | Storage format có thể không đảo ngược |

Một rollback plan phải ghi **điều kiện kích hoạt, các bước, expected effective state, người thực hiện, thời gian kiểm chứng và phương án nếu thất bại**.

**Lệnh revert Git không làm dữ liệu bị xóa bởi TTL quay trở lại.** Data-coupled changes cần recovery plan riêng.

## 33. Roll forward và repair khi rollback không còn an toàn

Một số tình huống:

- Storage format đã được ghi bằng engine version mới.
- Schema migration đã xóa hoặc đổi ý nghĩa fields.
- TTL đã xóa dữ liệu.
- Key cũ bị revoke để xử lý compromise.
- CDC log retention đã mất đoạn lịch sử.
- Một tập writes nghiệp vụ đã commit qua phiên bản ứng dụng mới.

Khi ấy có thể cần **roll forward** bằng bản vá tương thích, data reconciliation/rebuild, restore từ backup theo RPO/RTO và policy, thay vì cố chạy binary cũ.

Cần phân biệt trước deploy: **reversible config**, **reversible with data repair**, và **potentially irreversible**. Một flag runtime không tự biến một migration dữ liệu thành reversible.

## 34. Post-change verification: kiểm tra điều đã thay thật sự hoạt động

Sau deploy, không dừng ở “command exit code 0” hoặc “pod Running”.

Các bước:

1. Đọc effective runtime config của tất cả đối tượng trong phạm vi.
2. Kiểm tra node/replica/quorum/leader state.
3. Kiểm tra authentication/TLS và kết nối clients.
4. Chạy synthetic read/write theo quyền và consistency contract.
5. So p50/p95/p99, errors, retries, pool waits với baseline.
6. So CPU/disk/memory/network và hot partition signals.
7. Theo dõi background task/compaction/repair tăng theo thay đổi.
8. Kiểm tra business outcomes, data freshness và replication lag.
9. Xác minh audit có record change/actor/time.
10. So observed state với desired state, lưu evidence.
11. Theo dõi thêm đủ lâu để thấy delayed effects.
12. Update change request thành succeeded/rolled back/partial với lý do.

**Pod healthy không có nghĩa query hiệu quả; replica online không có nghĩa dữ liệu đã catch up; config deployed không đồng nghĩa config effective.**

## 35. Configuration drift: phát hiện và đưa về trạng thái kiểm soát

**Drift** xảy ra khi observed/effective config khác desired state.

Nguồn drift:

- Hotfix qua cloud console, DB admin command.
- Một node restart dùng file local khác.
- Manual CLI override không cập nhật Git.
- Provider đổi service default sau upgrade.
- Parameter group gắn sai cluster.
- Secret rotation chỉ cập nhật một phần clients.
- ConfigMap đổi nhưng service chưa reload.
- Region/DR môi trường cũ chưa nhận chính sách mới.

Cách xử lý:

~~~text
Inventory desired state
  -> observe deployed/runtime state
  -> compute safe diff (redact secrets)
  -> classify intended temporary override vs unexpected drift
  -> alert/approval if risk high
  -> reconcile in controlled rollout
  -> verify effective state
~~~

Không tự động “đưa mọi node về Git ngay” nếu Git đang thiếu một hotfix khẩn cấp có chủ đích; trước hết reconcile ownership và giữ audit. Với drift security-critical (tắt auth, public endpoint), có thể cần containment khẩn theo policy.

## 36. MongoDB: cấu hình replica set và sharding

Các lớp MongoDB cần xem cùng nhau:

- Driver URI, read preference, retry, pool size và timeouts.
- Authentication/TLS, permissions và cluster member identity.
- Replica set membership, elections, priority và sync status.
- Read/write concern theo business contract.
- WiredTiger/cache/storage settings được phiên bản hỗ trợ.
- Sharding/routing/balancer và chunk movement.
- Index builds, query plans, profiler/logging.
- Oplog, change streams và backup/restore.

Một thay đổi giảm request timeout có thể khiến requests tới secondary ở AZ xa hơn liên tục retry, tăng source QPS. Cần đo **logical calls vs physical attempts**, pool acquire, server selection, p99 và replication lag.

### 36.1. Rolling member restart cần bảo vệ quorum

~~~text
Precheck:
  healthy members, replication caught up, enough voting capacity

Canary:
  select node by role/topology
  apply supported setting and restart if required
  wait for healthy state and sync completion

Continue:
  one safe member at a time
  handle primary step-down/election explicitly if needed
  stop if cluster becomes degraded
~~~

Đây là **quy trình logic**, không phải lệnh áp dụng nguyên xi cho mọi MongoDB version. Đặc biệt, không restart đồng loạt voting members khi read/write operations phụ thuộc đa số còn khả dụng.

**Thay read/write concern không chỉ là tối ưu latency**; nó có thể thay đổi durability và consistency. Phải có test business invariants trước khi chấp nhận.

## 37. Cassandra/ScyllaDB: node, keyspace và topology

Nhóm tham số cần mô hình:

- Seed/discovery, rack/DC information.
- Replication strategy/factor (RF) theo keyspace.
- CQL consistency levels và token-aware driver routing.
- Memtable/commitlog/SSTable, compaction/repair.
- Read/write concurrency và backpressure.
- Client-to-node/node-to-node TLS/auth.
- Memory/GC/runtime specifics theo engine.
- Tombstone thresholds, TTL và partition sizes.
- Streaming/rebalance/repair network capacity.

**Cassandra và ScyllaDB không có bộ tham số server/hot reload giống nhau**, dù có các đặc điểm CQL/data model chung. Chọn hướng dẫn của sản phẩm/phiên bản thực tế.

Thay RF có thể cần data streaming/repair và ảnh hưởng quorum/consistency. Hỏi:

1. Bao nhiêu replicas còn healthy tại từng DC?
2. Client dùng consistency nào?
3. Bao nhiêu nodes/racks có thể offline mà vẫn đáp ứng SLO?
4. Data streaming thêm bao nhiêu disk/network work?
5. Có pending compactions/repairs hoặc hot partitions?
6. Khi tăng RF, dữ liệu đã được truyền/xác minh đủ chưa?

Một cấu hình RF mới hiển thị thành công **chưa chứng minh mọi replicas chứa dữ liệu tương ứng**.

## 38. DynamoDB: managed API, capacity và SDK settings

Ở managed NoSQL như DynamoDB, người dùng thường không chỉnh daemon/OS; thay vào đó kiểm soát:

- Capacity mode, provisioned capacity/autoscaling nếu dùng.
- API/SDK timeouts, retries, HTTP connection limits.
- Table/GSI/index design và partition key distribution.
- Backups/PITR/restore policy.
- Streams/consumer capacity và retention.
- IAM/KMS, endpoint/network controls.
- TTL và data expiration contract.
- Global replication/region semantics nếu triển khai.
- Monitoring throttles, consumed capacity, error rates.

Một table còn dư tổng capacity không chứng minh hot partition có thể chịu mọi burst. Một change plan nên xét **throttle reasons, key skew và retry amplification** chứ không chỉ tăng capacity hoặc retries.

Không đặt ra một “DynamoDB OS cache size” để cấu hình qua SDK; đó không phải knob thông thường trong dịch vụ managed.

## 39. Redis: memory, eviction và persistence tùy vai trò

Redis có thể là cache tái tạo được hoặc nơi giữ state cần durability. Cùng một thay đổi có risk khác nhau theo vai trò.

Các nhóm:

- `maxmemory`, eviction policy, TTL.
- ACL/TLS, service identity, network access.
- RDB/AOF/persistence semantics theo triển khai.
- Replication, failover và client reconnect.
- Network buffers/connected clients.
- Cluster hash slots/hot keys.
- CPU/slow commands, memory fragmentation.

Ví dụ:

~~~text
Before: cache memory near limit, few evictions
Change: lower maxmemory by 20%
Result: more evictions -> source misses spike
        -> NoSQL read QPS rises -> API p99 worsens
~~~

Canary phải đo Redis evictions **và source DB p99/QPS**, không chỉ memory sau thay đổi. Nếu Redis giữ state không thể tái tạo, eviction/persistence change có thể gây mất dữ liệu.

## 40. Search/analytics: refresh, mapping và derived data

Một read model như Elasticsearch/OpenSearch có các knobs:

- Shard/replica layout, routing.
- Indexing/search queues, bulk size/concurrency.
- Refresh/visibility delay.
- Cache/heap/circuit breakers.
- Index lifecycle, mappings/analyzers.
- Snapshot/reindex/restore.
- Tenant ACL, source-to-index CDC freshness.

Giảm refresh frequency có thể cải thiện indexing throughput nhưng làm document mới visible chậm hơn. Tăng replicas có thể làm storage/network indexing work tăng trong giai đoạn sync.

**Không dùng search index eventual làm authority cho quyết định stock/payment**. SLO của dữ liệu dẫn xuất cần bao gồm freshness, không chỉ query latency.

## 41. Kubernetes: ConfigMap, Secret và runtime config

Một ConfigMap/Secret có thể được mount thành file hoặc truyền thành environment variable. Process có thể không hot-reload khi nội dung đổi.

Một Deployment minh họa cho ứng dụng giả định:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: api
          image: example.invalid/order-api:v12
          env:
            - name: DB_ENDPOINT
              value: orders-db.internal.example
            - name: DB_SECRET_REF
              value: orders-api/prod/db-auth
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
~~~

YAML này chỉ cho thấy hình dạng, **không có logic tự resolve DB_SECRET_REF, đầy đủ RBAC, secret injection hay probes**. Trong production, dùng cơ chế secret management thật và kiểm soát image provenance.

Thay ConfigMap không đồng nghĩa JVM đã đọc giá trị mới. Environment variables thường được chụp lúc process start; mounted files có thể cập nhật nhưng application còn cần reload. Có thể gắn config version/hash vào Pod template để trigger rollout, rồi xác minh effective config.

## 42. Kubernetes và quorum: tránh restart đồng loạt

Một StatefulSet 3 pods không bảo đảm quorum nếu:

- Pods cùng node/AZ.
- External automation restart quá nhiều pods.
- Readiness probe chỉ kiểm tra cổng, chưa kiểm tra data catch-up.
- Volume detach/attach kéo dài.
- Node bootstrapping chưa xong mà Pod đã Running.
- PodDisruptionBudget không bao phủ một số loại gián đoạn.

Cần topology-aware scheduling, explicit disruption budget, **cluster-level replica/quorum health check trước khi cập nhật member tiếp theo**. Pod Ready là một tín hiệu, không thay semantics của NoSQL cluster.

## 43. Infrastructure as Code và policy as code

~~~mermaid
flowchart TD
    PR["Config/IaC PR"] --> V["Type/schema validation"]
    V --> S["Security/cost/availability policy"]
    S --> D["Plan/diff"]
    D --> A["Review and approval"]
    A --> E["Apply staging"]
    E --> C["Production canary"]
    C --> M{"SLO guardrails pass?"}
    M -->|Có| R["Controlled rollout"]
    M -->|Không| B["Pause/rollback"]
~~~

Policy có thể chặn hoặc yêu cầu ngoại lệ khi:

- Database endpoint public ngoài policy.
- TLS/auth/audit bị tắt.
- Backup/retention thấp hơn mức bắt buộc.
- Production topology không đủ fault-domain redundancy.
- Admin permissions quá rộng.
- Memory/disk limits có vẻ không khả thi.
- Key/secret nằm plaintext trong state hoặc logs.

**IaC state có thể chứa secrets và cần encryption/RBAC/audit.** Policy as code giúp ngăn sai sót lặp, nhưng không thay load/failover/correctness testing.

## 44. Audit thay đổi: lưu bằng chứng không chứa secrets

Một sự kiện triển khai có thể là:

~~~json
{
  "changeId": "CHG-2026-0114-01",
  "environment": "production",
  "component": "order-api",
  "configVersion": "git-a1b2c3d",
  "effective": true,
  "appliedAt": "2026-11-14T10:00:00Z",
  "actorType": "pipeline",
  "result": "SUCCESS",
  "scope": {"region": "region-A", "instances": 12}
}
~~~

Nên lưu:

- Actor/workload identity thực hiện.
- Config diff đã che dữ liệu nhạy cảm, from→to versions.
- Cluster/region/tenant scope.
- Approval/ticket reference.
- Preflight, canary và post-change evidence.
- Thời gian áp dụng và node nào chưa hoàn tất.
- Rollback reason, incident link.
- Manual overrides/temporary grants còn hiệu lực.

Audit có quyền đọc chặt, retention và alert nếu bị tắt; tránh ghi password, token hoặc nguyên văn connection string. Command API thành công **không chứng minh asynchronous apply đã hoàn thành**; cần trạng thái effective runtime.

## 45. Metrics và alert cho change rollout

Gắn deployment annotations lên dashboard:

- Config/release/driver/engine version.
- Node restart/election.
- Index/compaction/repair/backup jobs.
- Canary step/traffic percentage.
- Feature flag, TLS/secret rotation.
- Autoscaling và capacity changes.

| Nhóm | Metrics theo dõi |
|---|---|
| Người dùng | API p95/p99, error-budget burn, business outcomes |
| Driver | Pool wait/active, retry amplification, timeouts |
| NoSQL | Query p99, read/write QPS, hot key/partition, throttles |
| Replication | Health, quorum, lag, elections |
| OS/runtime | CPU per core, memory/GC, disk I/O, network drops |
| Dữ liệu | Invariant violations, stale read, CDC backlog |
| Bảo mật | Auth/TLS failures, permission denies, audit pipeline |
| Chi phí | Capacity consumption, storage, network egress |

Một thay đổi có thể cải thiện p50 nhưng làm p99 hoặc unknown write outcomes xấu đi. Không chỉ nhìn latency trung bình hoặc “số errors vẫn bằng 0” mà kết luận thành công.

## 46. Configuration rollout ở client có thể làm server quá tải

Ví dụ:

~~~text
Before:
  10 pods, 30 max connections per pod
  potential client connections = 300

After:
  HPA scales to 40 pods, config max pool = 80
  potential client connections = 3.200
~~~

Không phải tất cả connections đều active, nhưng driver có thể tạo reconnect storms, làm TLS handshakes, server memory và request queues tăng. Nếu mỗi pod còn tự retry, physical DB attempts càng tăng mạnh.

Controls:

1. Scale app và DB capacity có kế hoạch phối hợp.
2. Đặt global DB concurrency/rate limits phù hợp.
3. Giới hạn pool acquire time và pending work.
4. Bật canary trước khi thay tất cả pods.
5. Theo dõi per-node connections, retries, server throttling.
6. Cân nhắc jitter và gradual rollout để tránh cùng reconnect.
7. Nếu cần, tách pool/budget cho foreground và background jobs.

Đừng tối ưu một tầng mà chuyển toàn bộ contention sang tầng khác.

## 47. Config toggle và circuit breaker khi DB bị quá tải

Một số thay đổi dynamic có thể giảm tải khẩn cấp:

- Hạ tốc độ report scans hoặc CDC backfills.
- Tắt feature đọc/tính toán tốn tài nguyên.
- Giảm max concurrent analytics queries.
- Bật circuit breaker/backpressure khi nguồn quá tải.
- Tạm ngừng refresh-ahead/cache warmup.
- Giảm retry budget khi hệ đang throttled.
- Điều chỉnh traffic routing tới healthy nodes **nếu đúng consistency/routing contract**.

Mỗi toggle cần:

- Owner, expiration và audit.
- Mức ảnh hưởng tới user/business.
- Dấu hiệu bật/tắt thành công.
- Policy khi control plane không khả dụng.
- Tránh oscillation bằng cooldown/hysteresis.
- Không làm mất durable writes hoặc che unknown outcome.

**Feature flag phải được test cả hai trạng thái**. Một kill switch chưa từng được bật trong staging không thể coi chắc chắn hoạt động lúc production incident.

## 48. Disaster recovery: config phải phục hồi được cùng dữ liệu

Backup dữ liệu không đủ nếu không khôi phục được:

- Database engine/driver versions tương thích.
- Cluster topology, users/roles và network routes.
- KMS keys/trust stores cho backup.
- Secrets và service identity references.
- CDC/connector checkpoints khi cần.
- Index/schema definitions.
- Storage class/retention settings.
- Application endpoints/read/write policy.
- Alerting và operational access.

Một restore drill nên dùng **versioned config + data backup cùng một recovery plan**. Nếu data được restore nhưng app trỏ vào old primary hoặc driver vẫn dùng stale credentials, service có thể thất bại dù restore thành công.

Đánh giá RPO/RTO với config dependencies. Giữ cấu hình hạ tầng và quyền cần thiết trong quản lý phiên bản an toàn, nhưng không đưa private keys vào Git plaintext.

## 49. Cấu hình theo vùng và triển khai đa region

Multi-region làm tăng các chiều config:

- Primary/secondary endpoints, routing preference.
- Replica/write propagation hoặc conflict resolution.
- Regional capacity quotas và traffic weights.
- Network latency, egress cost.
- Certs/identity/trust giữa regions.
- Data residency/retention policy.
- Region-specific maintenance windows và dashboards.
- Failover, failback và read-your-writes semantics.

Một config giống hệt mọi region có thể sai nếu AZ topology, quota hoặc data residency khác nhau. Ngược lại, quá nhiều overrides riêng lẻ tăng drift. Chọn **base shared policy + regional overrides được giải thích**.

Thay region routing cần kiểm tra user-visible consistency: dữ liệu mới ghi ở region A có thể chưa xuất hiện ở region B. Không điều chỉnh DNS/driver read endpoint chỉ để giảm latency nếu có yêu cầu mạnh hơn về dữ liệu.

## 50. Khác biệt dynamic parameter và policy cấp tenant

Một số hệ cho phép thay rate limit theo tenant:

~~~text
tenant standard:
  maximum report jobs = 2
tenant enterprise:
  maximum report jobs = 10
~~~

Đây là **business/application policy** có thể dynamic, khác với cluster-wide max connections. Khi thay:

- Kiểm tra effective limits và burst behavior.
- Đặt fairness để tenant lớn không làm source quá tải.
- Phân quyền ai được sửa policy.
- Ghi audit và expiration với temporary overrides.
- Bảo đảm policy không cho phép vượt hard cluster safety cap.
- Tách tenant metadata khỏi environment secrets.

Một per-tenant config bị nhập nhầm có thể thành security/availability issue dù database topology không đổi.

## 51. Safety automation: tự dừng rollout khi dữ liệu vượt ngưỡng

Một deployment controller có thể:

~~~text
for each rollout step:
  apply scoped desired change
  wait until new instances/replicas ready
  check effective config version
  observe SLI and resource metrics for defined window
  if guardrails violated:
      stop rollout
      execute approved rollback or safe pause
      alert incident owner
  else:
      expand to next scope
~~~

Đây là **pseudocode về chính sách**, không phải controller sẵn chạy. Điều kiện kiểm tra nên tách:

- Hard safety: lost quorum, excessive write errors, unauthorized access.
- Soft/performance: p99, pool wait, CPU/disk/GC regression.
- Data: lag, mismatch hoặc lost CDC checkpoint.
- Confidence: số requests đủ, time window đủ và traffic representative.

Tự động rollback khi sai một sample metric có thể tạo vòng lặp rollout/revert. Cần window, minimum volume, hysteresis và manual intervention path.

## 52. Incident runbook: cấu hình mới làm p99 tăng

Tình huống giả định:

~~~text
At 10:00, driver config changed.
API p99:            120ms -> 900ms
Pool acquire p99:    10ms -> 600ms
Pool waiting:         0 -> 350
Server query p99:    20ms -> 24ms
Retry count:       1.0x -> 1.1x
~~~

Điều tra:

1. Xác nhận config version và thời điểm rollout.
2. So canary với control group cùng traffic.
3. Xem pool max/active/waiting và server-side connections.
4. Xác nhận config effective hay chỉ deployed.
5. Tìm requests giữ connections lâu, slow transactions/leaks.
6. Đánh giá app concurrency và pool headroom.
7. Nếu guardrail vượt ngưỡng, pause rollout.
8. Rollback theo plan có controlled redeploy.
9. Kiểm tra pool wait, p99 và server load sau rollback.
10. Ghi nguyên nhân vào change record, không chỉ “đổi lại là hết”.

Nếu server query p99 vẫn thấp mà pool wait cao, không kết luận “NoSQL query chậm”. Có thể need tune client pool hoặc giảm contention trước driver.

## 53. Incident runbook: rolling restart làm cụm mất quorum

Tình huống:

~~~text
Cluster starts healthy with multiple replicas.
Node A restarted for config.
Node A has not caught up.
Automation restarts Node B.
Write requests requiring quorum start failing.
Driver retries and client timeouts increase.
~~~

Quy trình ưu tiên:

1. **Dừng ngay các bước restart tiếp theo** và chặn automation mở rộng rollout.
2. Xác định health, role, sync lag và quorum thực tế theo engine/topology.
3. Bảo vệ dữ liệu: không tự giảm write concern/consistency để ép write success.
4. Xác định node nào có thể hồi phục an toàn, dùng runbook chuẩn theo engine.
5. Giới hạn retry storms và noncritical background jobs.
6. Phân loại write outcomes UNKNOWN cần reconciliation.
7. Khi member hồi phục, chờ sync/repair và kiểm tra data/leader state.
8. Kiểm tra client topology discovery, pool reconnect và auth.
9. Chạy probes đọc/ghi phù hợp consistency contract.
10. Chỉ tiếp tục rollout sau khi xác minh lại headroom/quorum.
11. Ghi incident timeline, config version, rollback/recovery steps.
12. Sửa automation để không chỉ dựa vào trạng thái Pod Running.

Không khởi tạo lại cluster, xóa replica data, force reconfigure hoặc ép failover tùy tiện khi chưa theo hướng dẫn sản phẩm và xác định dữ liệu nào có thẩm quyền.

## 54. Incident runbook: TTL hoặc retention giảm ngoài dự kiến

Tình huống:

~~~text
Production records expected retention: 30 days
New config applied:            2 days
Expiration starts before issue is noticed
Some records already deleted
CDC consumer had unprocessed backlog
~~~

Phản ứng:

1. Pause các thao tác xóa/retention có thể dừng an toàn theo sản phẩm.
2. Xác minh effective setting, phạm vi và thời điểm áp dụng.
3. Dùng audit để xác định người/process và change ID.
4. Xác định records/events đã mất và window bị ảnh hưởng.
5. Không tuyên bố phục hồi chỉ vì đổi TTL lại thành 30 ngày.
6. Đánh giá nguồn backup/snapshot/archive và retention hợp lệ.
7. Nếu consumer mất CDC history, xác định bootstrap/reconciliation path.
8. Ngăn replay dữ liệu đã bị xóa hợp lệ theo privacy policy.
9. Dựng bản khôi phục trong môi trường cô lập nếu risk cao.
10. So counts/versions/business invariants theo cutoff.
11. Khôi phục production theo runbook được phê duyệt.
12. Thêm policy-as-code chặn retention dưới giới hạn tối thiểu.

Đây là ví dụ điển hình của **thay đổi cấu hình có hậu quả dữ liệu**, không được giải quyết bằng rollback key-value đơn giản.

## 55. Incident runbook: rotate TLS/DB secrets làm lỗi kết nối

Một thay đổi credential/cert có thể phát sinh:

- App instances dùng key cũ.
- Một số nodes có trust store mới, số khác chưa reload.
- Cert chain/SAN/hostname mismatch.
- Secrets manager có version mới nhưng process giữ cache.
- Driver pool tạo connections cũ đang sống, sau restart mới lỗi.
- DR region hoặc backup agent chưa cập nhật identity.

Quy trình:

1. Xác định ảnh hưởng theo service, region, node, credential version.
2. Dừng rollout tiếp và bảo toàn client connections còn hợp lệ theo policy.
3. Xem TLS handshake/auth failure classes, không log private keys.
4. Kiểm tra chain, trust anchors, hostname, expiration, clock sync.
5. Xác định có được phép overlap old/new credentials không; nếu compromise thì có thể phải revoke ngay.
6. Rotate/redeploy theo đúng sequence hỗ trợ từ dịch vụ.
7. Probe read/write, backup/CDC/monitoring connectors.
8. Xem các service accounts phụ và batch jobs dùng credential cũ.
9. Khôi phục availability mà không giảm TLS verification hoặc bật public access.
10. Ghi audit, revoke temporary privileges và cập nhật rotation runbook.

**Không giải quyết certificate validation failures bằng cách tắt kiểm tra chứng chỉ trên production**. Làm vậy chuyển sự cố availability thành nguy cơ bảo mật.

## 56. Những sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm | Thực hành thay thế |
|---|---|---|
| “Merge Git là config đã hiệu lực” | App có thể chưa reload | Runtime effective-state checks |
| “YAML hợp lệ là thay đổi an toàn” | Có thể phá SLO/quorum/data | Policy + staging/canary |
| “Cùng config mọi môi trường” | Topology, IAM và dữ liệu khác | Shared base + scoped overrides |
| “Copy prod secrets sang staging” | Rò quyền và dữ liệu | Separate identities/synthetic data |
| “Tăng pool luôn tăng throughput” | Đẩy tải tới DB | Capacity + global concurrency |
| “Timeout giảm thì API luôn nhanh” | Retry/unknown outcomes tăng | End-to-end deadline |
| “Retry nhiều làm hệ reliable hơn” | Storm và duplicate effects | Retry budget, jitter, idempotency |
| “Node restart một lần thì không ảnh hưởng cluster” | Có thể thiếu quorum | Topology-aware rolling |
| “Pod Running nghĩa replica sẵn sàng” | Có thể chưa catch up | DB-level readiness |
| “RF tăng thì dữ liệu được replicate tức thì” | Data streaming/repair cần thời gian | Verify physical placement |
| “Consistency level chỉ là performance knob” | Thay tính đúng đắn | Business contract review |
| “Tăng heap tới container limit” | Native/off-heap bị OOM | Memory headroom |
| “Giảm retention rồi rollback là phục hồi” | Data có thể đã xóa | Restore/replay plan |
| “Index build là config nhỏ” | Scan/write amplification lớn | Bounded backfill/measure |
| “Staging pass chứng minh peak production” | Dữ liệu/tải khác | Representative load + canary |
| “Đổi một pod ngẫu nhiên để thử” | Có thể là leader/hot owner | Select topology-aware canary |
| “Rolling update luôn zero downtime” | Quorum/placement có thể yếu | Preflight and stop gates |
| “Chạy đêm luôn an toàn” | Backup/ETL có thể đang bận | Check actual load |
| “Thay nhiều knobs cùng lúc sẽ nhanh hơn” | Khó attribution/rollback | Controlled change budget |
| “Rollback chỉ cần git revert” | Data/state/versions đã đổi | Recovery plan |
| “Không cần audit vì là internal SRE” | Khó truy vết và accountability | Change record and logs |
| “Git là nơi lưu secrets tiện nhất” | Plaintext/leak và quyền rộng | Secret manager and refs |
| “Config drift tự động ghi đè không cần xem” | Có thể xóa emergency hotfix | Classify/reconcile/audit |
| “Cấu hình managed DB có OS knobs giống self-hosted” | API surface khác | Provider-specific docs |
| “Cache memory giảm chỉ ảnh hưởng cache” | Miss storm lên source | End-to-end monitoring |
| “Bật debug log chỉ giúp quan sát” | PII, CPU, disk, cost | Redaction, TTL, sampling |
| “Một change request là thành công khi API trả 200” | Async apply chưa xong | Effective state and probes |
| “SLO chỉ đo latency trung bình” | Tail errors và data correctness bị che | SLI by operation/p99/outcome |
| “Hạ durability để chữa timeout” | Có thể làm mất dữ liệu | Preserve business invariants |

## 57. Bài thực hành A — Thiết kế ma trận cấu hình

Cho ba môi trường: development, staging và production, cùng một API đặt hàng đọc MongoDB/DynamoDB hoặc engine NoSQL tương đương.

Hãy:

1. Xác định 12 cấu hình thuộc app, driver, DB, OS/network và security.
2. Phân loại giá trị nào là secret, dynamic, static hay data-coupled.
3. Thiết kế base config và environment overrides.
4. Ghi type, unit, default, allowed range, owner cho mỗi tham số.
5. Xác định identity và network rules khác nhau giữa môi trường.
6. Với production, đặt những thông số cần approval cấp cao.
7. Viết chính sách chặn staging trỏ vào production endpoint.
8. Đặt phương án đưa secret reference vào app, không commit plaintext.
9. Xác định cách đọc effective runtime config.
10. Đề xuất một drift alert và một runbook reconcile.

Đầu ra mong đợi là **bảng inventory có owner, constraints và evidence**, không chỉ ba file YAML chứa số khác nhau.

## 58. Bài thực hành B — Connection pool và autoscaling

Giả định:

~~~text
Before:
  10 application pods
  max pool 40 connections/pod
  DB recommended operational concurrency budget = 300 active calls

After HPA scaling:
  24 pods
  proposed pool = 80 connections/pod
~~~

Yêu cầu:

1. Tính tổng số potential connections trước/sau.
2. Phân biệt potential connections và active queries.
3. Nếu tất cả pods tăng connection nhanh, server có nguy cơ gì?
4. Thiết kế canary chỉ đổi ba pods.
5. Chọn metrics driver pool wait, retry, source p99 và throttling.
6. Xem liệu request-level concurrency cap có cần thiết không.
7. Đề xuất policy không để batch report tranh hết pool checkout.
8. Nếu pool chờ cao nhưng server còn rảnh, giả thuyết nào cần kiểm tra?
9. Nếu server đã bão hòa, tăng pool có nên làm không?
10. Viết điều kiện dừng/rollback canary và xác nhận sau rollback.

Một phương án tốt phải bảo vệ cả hai phía: ứng dụng không chờ pool vô hạn, database không bị dồn tải vượt capacity.

## 59. Bài thực hành C — Rolling restart và quorum

Một cụm có 3 data-bearing replicas ở 3 AZ. Ứng dụng có một loại write cần acknowledgement từ nhiều replicas theo policy.

Hãy:

1. Liệt kê state/health cần kiểm tra trước node đầu.
2. Giải thích tại sao không restart 2 nodes cùng lúc.
3. Chọn canary node có xét vai trò/leader.
4. Khi node đầu lên lại nhưng replication lag còn lớn, có được đi node tiếp không?
5. Driver có thể gặp transient server-selection error nào?
6. Retry policy phải bảo vệ điều gì?
7. Nếu một AZ đã degraded trước rollout, nên xử lý ra sao?
8. Các metric và probes nào chứng minh đủ quorum?
9. Nếu node không trở lại, làm sao giữ availability và mở incident?
10. Mô tả rollback nếu setting yêu cầu restart và app đang peak.

Không tự suy một quorum formula chung cho mọi engine; đọc chính sách replica/consensus/read-write cụ thể của hệ đang sử dụng.

## 60. Bài thực hành D — Retention và CDC

Một pipeline reporting tiêu CDC chậm:

~~~text
Current CDC retention:    72 hours
Oldest unprocessed age:   30 hours
Proposed new retention:   24 hours
Peak consumer outages:    can last 18 hours
Daily backup:             available
~~~

Hãy:

1. Tại sao giảm retention từ 72 giờ xuống 24 giờ không an toàn theo số liệu này?
2. Cần headroom như thế nào trước khi xem xét?
3. Retention có tự đảm bảo replay được mọi business history không?
4. Nếu consumer mất một đoạn log, snapshot có phục hồi history-based report không?
5. Đặt condition policy-as-code cho minimum retention.
6. Đề xuất test pause consumer và recovery.
7. Khi records đã expired, rollback retention có phục hồi được không?
8. Backup có đủ để tái tạo current-state projection không, với điều kiện nào?
9. Monitoring nào cần alert trước khi oldest event vượt window?
10. Với yêu cầu deletion/privacy, replay archive cần điều kiện nào?

## 61. Bài thực hành E — Thay config với GitOps và canary

Một team muốn tăng cache heap cho database từ 6 lên 10 GiB, nhưng Pod memory limit là 12 GiB; process có native/off-heap và data pages.

Hãy:

1. Viết change proposal có mục tiêu, phạm vi, owner và risk.
2. Tính memory budget với native/off-heap/OS cache.
3. Nêu tại sao heap = 10 GiB có thể gây OOM dù limit 12 GiB.
4. Tạo policy kiểm tra config range và giới hạn Pod.
5. Thử trên staging với workload đại diện như thế nào?
6. Chọn canary node phù hợp về topology.
7. Cần đo GC, RSS, page faults, cache hit, disk I/O nào?
8. Nếu effective config không đổi sau ConfigMap update, cần kiểm tra gì?
9. Đặt guardrail OOM/p99/replication lag.
10. Viết rollback steps và cách xác nhận runtime đã quay lại.
11. Một thay đổi cache ảnh hưởng source read QPS như thế nào?
12. Ghi change audit evidence nào?

## 62. Bài thực hành F — Tài khoản quản trị và certificate rotation

Một ứng dụng có 15 pods, 2 vùng, các drivers sử dụng TLS với một root CA cũ. Team chuẩn bị chuyển sang CA mới.

Hãy:

1. Vẽ client→DB và node→node TLS paths cần được bảo vệ.
2. Liệt kê app, backup, CDC, reporting và admin clients đang dùng trust store.
3. Xác định có thể dùng khoảng thời gian trust overlap không.
4. Đặt thứ tự cập nhật trust store/certificate theo engine version.
5. Thiết kế canary với một nhóm app instances.
6. Chọn metrics TLS handshake failures, auth errors, connections và p99.
7. Nếu region DR chưa cập nhật, có rủi ro gì?
8. Quy trình revoke/rotation khác thế nào nếu key cũ đã bị compromise?
9. Vì sao không tắt hostname verification để sửa sự cố?
10. Ghi audit và kiểm tra effective credential/cert version thế nào?

Một kế hoạch hoàn chỉnh phải nêu cả **hướng kết nối ít khi sử dụng** (backup, DR, admin), không chỉ API chính.

## 63. Checklist tự kiểm tra trước khi kết thúc một change

Một change owner nên trả lời được:

| Câu hỏi | Bằng chứng tối thiểu |
|---|---|
| Đã thay đúng môi trường/node/region? | Target identity + inventory |
| Ai yêu cầu, phê duyệt, thực thi? | Change/audit record |
| Có cần restart hay migration? | Engine/version-specific plan |
| Desired và effective config có khớp? | Runtime readback/introspection |
| Cluster/quorum khỏe sau mỗi bước? | Member health/lag |
| Client behavior còn đúng? | SLI, retries, pool wait, auth |
| Business correctness không xấu? | Synthetic/real invariant metrics |
| Có phát sinh hot partition/throttling? | Per-node/partition metrics |
| Storage/backup/CDC không bị ảnh hưởng trái dự kiến? | Capacity, lag, restore policy |
| Canary có đủ traffic/samples? | Comparative dashboard |
| Rollback/recovery vẫn khả thi? | Tested runbook, prerequisites |
| Đã ghi exceptions và residual risks? | Ticket/owner/due date |

Đây là **bảng vận hành trong bài học**, không phải yêu cầu người học chạy Content QA. Những phép kiểm nêu ở đây là kiểm tra production change thực tế nếu có trách nhiệm vận hành hệ.

## 64. Câu hỏi tự kiểm tra kiến thức

1. Desired, deployed và effective config khác nhau ở đâu?
2. Vì sao một tham số cần type, unit, scope và lifecycle?
3. Cấu hình runtime khác business reference data thế nào?
4. Thế nào là static, dynamic, cluster-wide và node-local parameter?
5. Vì sao hot reload không thể suy từ việc file vừa được cập nhật?
6. Một configuration inventory nên có những trường nào?
7. Vì sao staging không nên sao chép production secrets?
8. Functional parity khác capacity parity thế nào?
9. Config precedence có thể tạo drift ra sao?
10. GitOps giúp gì và có giới hạn nào?
11. Vì sao không lưu plaintext secrets trong IaC repository?
12. Secret rotation có thể làm p99/auth failures tăng ra sao?
13. API deadline và driver timeout phải phối hợp thế nào?
14. Retry config có liên hệ gì với idempotency?
15. Tại sao tăng pool size chưa chắc tăng throughput?
16. HPA tăng pods ảnh hưởng tổng database connections như thế nào?
17. Consistency và durability knobs có thể thay business contract ra sao?
18. RF và replica placement phải xét cùng topology thế nào?
19. Tại sao đổi RF không kết thúc chỉ bằng việc sửa metadata?
20. Cần tính những nhóm memory nào khi tăng heap/cache?
21. Retention/TTL khác những config có thể đảo được ở điểm nào?
22. Vì sao thay schema/index có thể là data migration?
23. Một thay đổi có blast radius cao cần approval và guardrails nào?
24. Canary có thể là app pod, tenant hoặc DB member trong điều kiện nào?
25. Rolling restart có bảo đảm zero downtime không?
26. Vì sao một node Running chưa đủ chứng minh DB healthy?
27. Maintenance window có thể có những background jobs nào?
28. Preflight cụm phân tán phải xét quorum/replication ra sao?
29. Guardrails nên đo end-user SLI hay chỉ CPU?
30. Data-coupled change cần rollback/repair plan thế nào?
31. Drift do console hotfix có nên tự overwrite ngay không?
32. MongoDB read/write concern đổi có thể tạo rủi ro gì?
33. Cassandra/ScyllaDB RF và CL có quan hệ gì?
34. DynamoDB capacity mode có giải được mọi hot partition không?
35. Redis maxmemory/eviction thay đổi có ảnh hưởng NoSQL source không?
36. Search refresh/indexing settings có làm data freshness thay đổi không?
37. K8s ConfigMap environment variables có tự hot reload không?
38. PDB có thay thế quorum health checks không?
39. IaC state có thể chứa dữ liệu nhạy cảm không?
40. Một change audit nên lưu những gì nhưng không lộ secrets?
41. Những metric nào cho thấy thay đổi driver gây retry storm?
42. Region failover cần xem consistency/endpoint contract nào?
43. Sự khác nhau giữa rollback và roll forward?
44. Vì sao backup dữ liệu chưa đủ nếu thiếu config/keys tương thích?
45. Khi một change xấu, làm sao chứng minh đã khôi phục effective state?

## 65. Tổng kết: cấu hình là một phần của tính đúng đắn hệ NoSQL

Cấu hình quyết định cách ứng dụng, driver, database, cluster, storage và hệ điều hành cùng hoạt động. Một thay đổi vài dòng có thể tác động tới quorum, read freshness, số lượng kết nối, khả năng phục hồi, retention hoặc quyền bảo mật. Vì vậy **quản lý cấu hình là quản lý sự thay đổi của cả hệ phân tán**, không chỉ lưu tập tin trong repository.

Một chu trình an toàn:

~~~text
1. Xác định mục tiêu, SLI, môi trường và failure domain.
2. Inventory tham số: type/unit/default/scope/lifecycle/owner.
3. Tách secrets, feature flags, schema và runtime config.
4. Lưu desired state có phiên bản và policy-as-code.
5. Kiểm tra dependencies, capacity, quorum, data consequences.
6. Review risk, approval, rollout/canary và rollback plan.
7. Preflight node health, traffic, backup/CDC và quyền operator.
8. Áp thay đổi theo scope nhỏ; rolling theo topology.
9. Đọc effective runtime config, không chỉ trạng thái Git/deploy.
10. Theo dõi p99, errors, retry amplification, replica lag, disk/CPU.
11. Dừng/rollback hoặc roll forward khi guardrails bị vi phạm.
12. Lưu audit/evidence và xử lý configuration drift.
13. Cập nhật runbook, policy và bài học từ incident.
~~~

**Nguyên tắc cốt lõi:** *Một thay đổi cấu hình chỉ thực sự hoàn tất khi đúng đối tượng đã nhận đúng giá trị, hệ thống vẫn giữ các bảo đảm dữ liệu và khả năng phục vụ, và có bằng chứng đo lường cùng đường khôi phục nếu giả thuyết ban đầu sai.* Đây là nền tảng để vận hành cụm NoSQL ổn định khi hệ tăng trưởng, mở rộng nhiều vùng và thường xuyên triển khai phiên bản mới.













