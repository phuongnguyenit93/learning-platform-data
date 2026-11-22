# Tích hợp công cụ điều phối như Patroni và kho đồng thuận

**Streaming replication** giữ một hoặc nhiều PostgreSQL standbys gần trạng thái primary bằng cách truyền WAL. Tuy nhiên, replication tự nó chưa giải quyết đầy đủ việc phát hiện node lỗi, quyết định ai được làm primary, ngăn hai primary cùng nhận writes, cập nhật routing cho ứng dụng và tái gia nhập node cũ. Các bước này cần một lớp điều phối.

**Patroni** là một công cụ HA phổ biến cho PostgreSQL. Patroni chạy trên các database nodes, giám sát PostgreSQL và phối hợp với một **Distributed Configuration Store (DCS)** như etcd, Consul, ZooKeeper hoặc Kubernetes API. DCS cung cấp nơi lưu trạng thái cluster và cơ chế phối hợp phân tán. Patroni dùng thông tin đó để bầu/chọn leader, quản lý leader lock/lease, theo dõi thành viên và điều khiển các thao tác PostgreSQL như start, stop, promote, demote và reinitialize.

Điều phối HA là một giao thức phân tán giữa agents, DCS, PostgreSQL processes, network và client routing. Mỗi thành phần phải có failure model và security boundary rõ ràng.

```text
                 Applications / connection pools
                             |
                       VIP / Proxy / DNS
                             |
                   Current writable primary
                             |
              +--------------+--------------+
              |                             |
          PostgreSQL                    Patroni agent
              |                             |
         WAL streaming               HA loop / REST API
              |                             |
        +-----+------+                      |
        |            |                       |
     Standby A    Standby B                  |
        |            |                       |
    Patroni A    Patroni B                   |
        |            |                       |
        +------------+-----------------------+
                             |
                     DCS cluster/quorum
                  (etcd / Consul / ZooKeeper /
                       Kubernetes API)
```

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao PostgreSQL replication cần lớp orchestration để trở thành HA solution.
2. Phân biệt database replication, leader election, distributed lock/lease, service discovery và client routing.
3. Mô tả vai trò của Patroni trên từng PostgreSQL node.
4. Giải thích DCS và các yêu cầu consistency, quorum, availability, failure detection.
5. So sánh etcd, Consul, ZooKeeper và Kubernetes API làm backend điều phối.
6. Hiểu leader key/lease, TTL, session, renewal và fencing limitations.
7. Giải thích Patroni HA loop, state transitions và REST API.
8. Hiểu bootstrap, dynamic configuration, local configuration và cluster initialization.
9. Phân biệt failover tự động, switchover có kế hoạch và reinitialize replica.
10. Hiểu synchronous mode, synchronous replication policy và failover safety.
11. Tích hợp proxy/load balancer/service discovery với Patroni.
12. Bảo vệ DCS, Patroni REST API, replication traffic và PostgreSQL credentials.
13. Thiết kế monitoring, backup, restore, disaster recovery và operational runbooks.
14. Nhận diện split-brain, DCS outage, network partition, stale leader và các tình huống quorum.
15. Thực hành triển khai và kiểm thử một Patroni cluster trong môi trường lab.

## 2. Vấn đề mà công cụ điều phối giải quyết

### 2.1. Streaming replication chỉ sao chép WAL

PostgreSQL physical streaming replication truyền WAL từ primary tới standbys. Nó giữ data files của standby gần primary và cung cấp khả năng promotion. Nhưng PostgreSQL không tự quyết định đầy đủ:

- Primary đã chết thật hay chỉ mất kết nối từ một monitor?
- Standby nào đủ điều kiện để promote?
- Có node nào khác đang giữ quyền primary không?
- Ai được phép thực hiện promotion?
- Làm thế nào cập nhật endpoint để ứng dụng kết nối tới primary mới?
- Làm thế nào đưa primary cũ quay lại làm standby?

Các câu hỏi này thuộc lớp orchestration và HA policy.

### 2.2. Hai primary có thể gây split-brain

Giả sử primary A bị network partition khỏi standby B. Nếu B tự promote trong khi A vẫn nhận writes từ một số clients, hệ thống có hai primary độc lập. Cả hai tạo WAL histories khác nhau và không tự merge.

HA manager cần một cơ chế ownership có tính phân tán để chỉ một node được giữ vai trò leader tại một thời điểm, cùng cơ chế fencing để ngăn primary cũ tiếp tục phục vụ writes khi ownership chuyển đi.

### 2.3. Failure detection không phải sự thật tuyệt đối

Một node không phản hồi health check có thể:

- PostgreSQL process đã crash.
- Host đã tắt hoặc mất điện.
- Network path giữa monitor và node bị lỗi.
- CPU/disk overload làm phản hồi chậm.
- Firewall/DNS/TLS bị thay đổi.
- DCS hoặc control plane không truy cập được.

Timeout chỉ là một tín hiệu. Nó không chứng minh node đã chết. Một thiết kế HA an toàn phải kết hợp lease/quorum, node state, fencing và quy tắc promotion.

### 2.4. Cần tách các plane

| Plane | Trách nhiệm |
| --- | --- |
| Data plane | PostgreSQL primary/standby, WAL streaming, reads/writes. |
| Control plane | Patroni agents, DCS, leader election, cluster membership. |
| Client routing plane | HAProxy/PgBouncer/VIP/DNS/service discovery, định tuyến read/write. |
| Backup/recovery plane | Base backup, WAL archive, PITR, restore testing. |
| Observability plane | Metrics, logs, alerts, audit và incident response. |

Một control plane khỏe không đảm bảo data plane khỏe. Một database có thể đang chạy nhưng không có leader lock hợp lệ; một leader lock có thể tồn tại trong khi PostgreSQL process không phục vụ query. Giám sát từng plane riêng.

## 3. Patroni là gì?

### 3.1. Patroni agent trên mỗi database node

Patroni là một daemon Python chạy cạnh PostgreSQL trên mỗi node trong cluster. Nó quản lý lifecycle PostgreSQL và tham gia HA coordination:

- Đọc local configuration và dynamic configuration từ DCS.
- Theo dõi trạng thái PostgreSQL bằng process checks và SQL connections.
- Theo dõi cluster state, leader lock và member records trong DCS.
- Chạy HA loop định kỳ để quyết định cần làm gì.
- Giữ/renew leader lock nếu node đang là leader.
- Chuyển node thành standby hoặc promote khi policy cho phép.
- Tạo/reinitialize replica qua PostgreSQL tools như `pg_basebackup`.
- Cung cấp REST API để health checks và quản trị.

Patroni agent không phải một PostgreSQL extension. Nó là process bên ngoài điều khiển PostgreSQL server.

### 3.2. Mỗi node có một Patroni instance

Một cluster ba nodes thường có ba Patroni agents:

```text
Node A: PostgreSQL + Patroni A ----+
Node B: PostgreSQL + Patroni B ----+---- DCS
Node C: PostgreSQL + Patroni C ----+
```

Các agents trao đổi trạng thái qua DCS và PostgreSQL replication. DCS không chứa database rows hay WAL; nó chứa coordination metadata.

### 3.3. Patroni không thay PostgreSQL replication

Patroni dùng PostgreSQL physical replication để giữ standby đồng bộ. Nó có thể gọi `pg_basebackup`, quản lý `primary_conninfo`, replication slots và promotion, nhưng WAL vẫn được PostgreSQL gửi/replay.

### 3.4. Patroni không tự là load balancer

Patroni REST API cung cấp thông tin node role/health. HAProxy, PgBouncer, Envoy, cloud load balancer hoặc service discovery có thể dùng thông tin đó để route clients. Cần cấu hình routing rõ ràng; chỉ cài Patroni không tự chuyển mọi client connection.

### 3.5. Patroni không thay backup

Patroni tập trung HA và orchestration. Nó không phải hệ thống backup retention/PITR hoàn chỉnh. Vẫn cần base backups, WAL archiving, immutable backup copies và restore drills.

## 4. Distributed Configuration Store (DCS)

### 4.1. DCS lưu gì?

DCS là kho trạng thái phân tán dùng để các Patroni agents phối hợp. Dữ liệu điển hình gồm:

- Cluster configuration dùng chung.
- Leader key/lease và thông tin node giữ leader.
- Member records/heartbeat của các Patroni nodes.
- Failover/switchover state hoặc metadata liên quan.
- History/timeline metadata và trạng thái cluster theo phiên bản/cấu hình.
- Synchronous replication state khi dùng synchronous mode.

Tên key/path và schema cụ thể phụ thuộc Patroni version/backend; không sửa trực tiếp DCS keys bằng tay khi cluster đang hoạt động.

### 4.2. DCS không lưu database contents

DCS không replicate PostgreSQL tables, indexes, WAL hay user data. Nếu DCS mất dữ liệu, PostgreSQL data files vẫn có thể tồn tại, nhưng Patroni có thể mất thông tin leader ownership/configuration và không thể điều phối an toàn cho tới khi trạng thái được khôi phục.

### 4.3. Vì sao cần consistency?

Giả sử hai agents cùng ghi một leader key mà không có atomic compare-and-set/quorum semantics. Cả hai có thể nghĩ mình là leader. DCS cần cung cấp operations nguyên tử và thứ tự nhất quán đủ để bảo đảm một ownership record được cập nhật theo một trình tự duy nhất.

### 4.4. Quorum

Nhiều DCS dùng consensus protocol để các nodes thống nhất một thứ tự writes. Một cluster có quorum khi đủ thành viên có thể tham gia quyết định. Ví dụ etcd/Raft thường triển khai với số voting members lẻ để chịu lỗi một số members:

| Voting members | Quorum | Số member có thể mất mà vẫn còn quorum |
| ---: | ---: | ---: |
| 1 | 1 | 0 |
| 3 | 2 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

Đây là phép tính majority quorum. Không nên tăng số DCS members tùy tiện: nhiều members làm quorum phức tạp và có thể tăng latency.

### 4.5. DCS outage ảnh hưởng gì?

Khi Patroni không thể liên lạc với DCS, agent không thể gia hạn/đọc ownership theo bình thường. Node đang giữ leader lock có thể phải demote/stop PostgreSQL để tránh tiếp tục writes khi không thể chứng minh quyền leader. Các standbys có thể không promote vì không có quorum/ownership decision.

Chính sách cụ thể phụ thuộc Patroni version, DCS backend và các safety settings. Không nên hiểu DCS outage là “database tự failover ngay”.

### 4.6. DCS phải có failure domain độc lập

Đặt toàn bộ DCS voting members trên cùng một host/rack/availability zone làm mất ý nghĩa quorum khi failure domain đó gặp sự cố. Phân bố members theo topology phù hợp và hiểu latency giữa các zones.

### 4.7. Không dùng DCS như database ứng dụng

DCS phục vụ coordination metadata nhỏ, không phải nơi lưu application data hoặc workload truy vấn tùy ý. Không tạo keys tùy tiện trong Patroni namespace.

## 5. Các DCS backend phổ biến

### 5.1. etcd

etcd là distributed key-value store dùng Raft consensus. Patroni dùng etcd để lưu cluster state, leader ownership và dynamic configuration.

Đặc điểm:

- Strong consistency cho operations được commit theo quorum.
- Lease/TTL và watch APIs hỗ trợ leader ownership/notification.
- Raft majority quorum; cluster 3 hoặc 5 voting members thường được dùng.
- Cần bảo vệ client/peer endpoints, certificates và data directory.
- Không nên dùng chung một etcd cluster không được capacity/isolation phù hợp cho mọi workload critical.

etcd là backend được dùng phổ biến trong nhiều triển khai Patroni.

### 5.2. Consul

Consul cung cấp service discovery, health checks và distributed KV store với consistency controls. Patroni có thể dùng Consul KV/session mechanisms làm DCS.

Đặc điểm:

- KV và sessions/locks hỗ trợ coordination.
- Agent/server architecture; cần hiểu server quorum và datacenter behavior.
- Có thể tích hợp service discovery nhưng vẫn cần cấu hình client routing cụ thể.
- Phải bảo vệ ACL tokens, gossip encryption, TLS và server quorum.

Consul session/lock behavior và Patroni DCS semantics cần được kiểm tra theo version.

### 5.3. ZooKeeper

ZooKeeper là coordination service dùng atomic operations và Zab protocol, cung cấp ephemeral znodes, watches và ensemble quorum.

Đặc điểm:

- Ephemeral nodes gắn với client session.
- Watches thông báo thay đổi state.
- Ensemble thường dùng số voting members lẻ.
- Cần quản lý session timeout, connection loss, ACL và snapshot/transaction logs.
- Watches có semantics one-shot; client phải đăng ký lại khi cần.

Patroni có thể dùng ZooKeeper backend theo phiên bản/tích hợp được hỗ trợ.

### 5.4. Kubernetes API

Trong Kubernetes, Patroni có thể dùng Kubernetes API/Endpoints hoặc resources liên quan làm DCS, tùy cấu hình và phiên bản Patroni. API server và backing etcd của Kubernetes cung cấp control-plane consistency.

Đặc điểm:

- Không nhất thiết phải tự vận hành thêm etcd cluster riêng cho Patroni.
- Có thể sử dụng Kubernetes objects/leases theo backend hỗ trợ.
- Cần RBAC service account tối thiểu, API availability và network connectivity.
- Kubernetes control plane outage có thể ảnh hưởng coordination; PostgreSQL pods/volumes có thể còn chạy nhưng failover decisions bị giới hạn.
- Không nhầm Kubernetes liveness/readiness probes với Patroni leader election.

### 5.5. So sánh nhanh

| Tiêu chí | etcd | Consul | ZooKeeper | Kubernetes API |
| --- | --- | --- | --- | --- |
| Coordination primitive | KV, lease, watch, transaction | KV, session, lock | Znode, ephemeral node, watch | API objects/leases theo backend |
| Consensus/quorum | Raft | Raft cho server quorum | Zab ensemble quorum | API server backed by etcd |
| Service discovery tích hợp | Cần công cụ khác | Có | Không phải trọng tâm | Kubernetes Services/Endpoints |
| Vận hành | Cluster riêng hoặc managed | Agents + servers | Ensemble riêng | Kubernetes control plane |
| Security chính | TLS, auth/RBAC | ACL, TLS, gossip encryption | ACL, TLS/auth | RBAC, service account, TLS |
| Rủi ro chính | Mất quorum, disk/latency | Server quorum/session/ACL | Session timeout/ensemble | API availability/RBAC/control plane |

Không có backend tốt nhất cho mọi tổ chức. Chọn backend mà đội vận hành hiểu rõ, có thể monitor, backup, nâng cấp và khôi phục.

## 6. Leader lock, lease và ownership

### 6.1. Leader lock là gì?

Patroni dùng một record trong DCS để thể hiện node nào đang giữ quyền leader. Các agents đọc/ghi record theo cơ chế atomic/lease của backend. Một node chỉ nên phục vụ writes như primary khi nó có ownership hợp lệ và PostgreSQL role/state phù hợp.

### 6.2. TTL và renewal

Leader ownership thường có thời hạn/TTL. Leader phải gia hạn lock định kỳ. Nếu không gia hạn trong thời gian quy định, DCS có thể coi lease đã hết hạn và cho phép một node khác giành ownership theo HA protocol.

Các tham số liên quan gồm:

- `ttl`: thời gian lease/leader lock tồn tại nếu không được renew.
- `loop_wait`: khoảng thời gian giữa các HA loop iterations.
- `retry_timeout`: giới hạn retry khi thao tác DCS/PostgreSQL gặp lỗi.
- `primary_start_timeout`: khoảng thời gian chờ primary start trong một số transitions.

Tên và constraints thay đổi theo Patroni version. Giá trị phải được cấu hình nhất quán với timeout DCS và latency thực tế.

### 6.3. Vì sao TTL quá ngắn nguy hiểm?

Nếu TTL ngắn hơn thời gian DCS/network pause bình thường, leader có thể mất lock do GC pause, CPU starvation, network jitter hoặc DCS latency. Điều này gây unnecessary demotion/failover.

TTL quá dài lại làm phát hiện leader failure chậm, kéo dài RTO. Chọn TTL dựa trên measured worst-case latency và failure detection target.

### 6.4. Compare-and-set / transaction

DCS cần bảo đảm thao tác claim/renew leader lock chỉ thành công khi các điều kiện ownership/version còn đúng. Các backend dùng transaction, revision, session hoặc lease semantics để ngăn hai agents ghi đè ownership theo kiểu last-writer-wins thiếu kiểm soát.

### 6.5. Lease hết hạn không tự dừng process cũ

Một lease trong DCS không tự ngắt CPU hoặc đóng PostgreSQL socket của node cũ. Nếu node bị partition khỏi DCS nhưng vẫn có client connections, cần cơ chế Patroni demotion/stop và/hoặc external fencing/watchdog. Đây là lý do distributed lock phải đi cùng fail-closed behavior và fencing strategy.

### 6.6. Watchdog

Patroni có thể tích hợp Linux watchdog để node tự reset/fence nếu không thể duy trì điều kiện an toàn trong thời gian cho phép. Watchdog hardware/software cần được cài và cấu hình đúng, kiểm tra thực tế và hiểu semantics của host/VM. Một config `watchdog` không có thiết bị hoạt động không tạo fencing thật.

### 6.7. Fencing ở tầng hạ tầng

Với cloud/virtualized systems, có thể cần power fencing, detach storage, revoke write access hoặc control-plane action. Fencing phải được thực hiện bởi authority đáng tin cậy và có timeout rõ. DNS/VIP switch không thay thế fencing vì primary cũ vẫn có thể nhận traffic qua đường khác.

### 6.8. Single-writer invariant

Mục tiêu cốt lõi là tại một thời điểm chỉ một node có quyền nhận writes cho cluster. Mọi failover, manual promotion, restore và maintenance đều phải giữ invariant này.

## 7. Patroni HA loop và trạng thái node

### 7.1. HA loop

Mỗi Patroni agent chạy một vòng điều phối định kỳ:

1. Đọc trạng thái local PostgreSQL.
2. Đọc dynamic configuration/member/leader state từ DCS.
3. Xác định node đang là leader, replica, candidate hay trạng thái lỗi.
4. Nếu là leader, kiểm tra và renew leader lock.
5. Nếu là replica, kiểm tra leader và replication health.
6. Áp dụng policy về failover, synchronous mode và replica selection.
7. Thực hiện hành động phù hợp: start, stop, promote, follow, reinitialize hoặc cập nhật trạng thái.
8. Publish member status/heartbeat để các agents khác quan sát.

Đây là mô tả logic; thứ tự/chi tiết chính xác tùy Patroni release và DCS backend.

### 7.2. Leader

Node leader giữ leader lock trong DCS và PostgreSQL chạy read-write primary. Patroni liên tục kiểm tra khả năng giữ ownership. Nếu không renew được lock theo policy, Patroni có thể demote/stop PostgreSQL để bảo vệ single-writer invariant.

### 7.3. Replica

Replica là node đang ở standby/recovery, theo WAL từ upstream. Patroni monitor WAL receiver, replay progress, timeline và khả năng kết nối. Nếu leader đổi, replica có thể follow leader mới hoặc được chọn làm candidate khi failover.

### 7.4. Candidate

Khi leader không còn hợp lệ, các replicas đủ điều kiện có thể tham gia quá trình chọn node mới. Candidate phải đáp ứng eligibility policy và có WAL position phù hợp để giảm data loss.

### 7.5. Initializing / creating replica

Một node mới có thể đang bootstrap hoặc được reinitialize từ leader. Trong giai đoạn này nó chưa phải replica healthy; không route application reads vào node.

### 7.6. Stopped / failed

Patroni có thể phát hiện PostgreSQL không chạy, bị crash hoặc không thể kết nối. Node không được coi là leader healthy chỉ vì DCS vẫn có một leader key cũ.

### 7.7. Role và health là hai câu hỏi khác nhau

- Role: node có phải leader/replica theo DCS và PostgreSQL state?
- Health: node có thực sự nhận query, stream/replay WAL và đáp ứng latency/SLA?

Load balancer cần health endpoint đúng với mục tiêu. Một endpoint “alive” có thể trả HTTP 200 trong khi node không phải primary; endpoint “primary” có thể từ chối khi leader ownership không hợp lệ.

## 8. Patroni configuration

### 8.1. Các nhóm cấu hình chính

Một file Patroni YAML thường có các nhóm:

| Nhóm | Nội dung |
| --- | --- |
| `scope`, `namespace`, `name` | Định danh cluster, DCS namespace và node name. |
| `restapi` | Listen/connect address, TLS và authentication cho REST API. |
| DCS backend | etcd/Consul/ZooKeeper/Kubernetes endpoints và credentials. |
| `bootstrap` | Khởi tạo cluster lần đầu, dynamic config ban đầu, initdb và users. |
| `postgresql` | Listen address, data directory, binaries, authentication và parameters. |
| `tags` | Eligibility/routing hints như `nofailover`, `noloadbalance`, `nosync`, `clonefrom`. |

Các key cụ thể phụ thuộc Patroni version và backend. Validate config bằng công cụ/version đang cài trước khi deploy.

### 8.2. Ví dụ local configuration cho một node

Ví dụ minh họa dùng etcd v3. Thay hostname, IP, paths, users, passwords và certificate paths:

```yaml
scope: app-ha
namespace: /service/
name: pg-node-a

restapi:
  listen: 10.20.0.11:8008
  connect_address: 10.20.0.11:8008
  authentication:
    username: patroni_api
    password: REPLACE_WITH_SECRET

etcd3:
  hosts:
    - 10.20.0.21:2379
    - 10.20.0.22:2379
    - 10.20.0.23:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576
    postgresql:
      use_pg_rewind: true
      use_slots: true
      parameters:
        wal_level: replica
        hot_standby: "on"
        max_wal_senders: 10
        max_replication_slots: 10
        wal_keep_size: 512MB
  initdb:
    - encoding: UTF8
    - data-checksums
  pg_hba:
    - host replication replicator 10.20.0.0/24 scram-sha-256
    - host all app_user 10.20.0.0/24 scram-sha-256

postgresql:
  listen: 10.20.0.11:5432
  connect_address: 10.20.0.11:5432
  data_dir: /var/lib/postgresql/17/data
  bin_dir: /usr/lib/postgresql/17/bin
  authentication:
    superuser:
      username: postgres
      password: REPLACE_WITH_SECRET
    replication:
      username: replicator
      password: REPLACE_WITH_SECRET
  parameters:
    unix_socket_directories: /var/run/postgresql

tags:
  nofailover: false
  noloadbalance: false
  clonefrom: false
  nosync: false
```

Đây là cấu hình học tập, không phải file production hoàn chỉnh. REST API và PostgreSQL listen addresses phải phù hợp network design. Secrets cần được inject từ secret manager hoặc file có quyền đọc hạn chế.

### 8.3. Cấu hình trên các nodes

Các nodes dùng cùng `scope` và `namespace` để tham gia cùng cluster, nhưng `name`, REST API address, PostgreSQL address và local data directory phải khác nhau. Không copy nguyên config của node A sang B/C mà quên đổi identity.

### 8.4. scope và namespace

`scope` là tên cluster logic. `namespace` xác định prefix/path trong DCS. Nếu hai Patroni clusters dùng chung DCS mà vô tình dùng cùng scope/namespace, chúng có thể đụng metadata và làm hỏng coordination.

Đặt naming convention duy nhất cho mỗi môi trường, ví dụ `prod-orders-eu1`, `staging-orders` và namespace riêng.

### 8.5. name

`name` là tên duy nhất của member trong cluster. Nó xuất hiện trong member records, logs và `patronictl list`. Không dùng hostname trùng nhau hoặc đổi tên node tùy tiện khi cluster đang hoạt động.

### 8.6. restapi listen và connect_address

- `listen`: địa chỉ/interface mà Patroni REST API bind.
- `connect_address`: địa chỉ các nodes khác/health checks dùng để kết nối.

REST API thường dùng port riêng, ví dụ 8008, không phải PostgreSQL port. Không expose endpoint này ra public network.

### 8.7. postgresql listen và connect_address

- `listen`: PostgreSQL bind address/interface.
- `connect_address`: endpoint các nodes khác dùng để kết nối PostgreSQL replication.

Giữ REST API và PostgreSQL replication addresses tách biệt. DNS/IP cần ổn định và resolve đúng từ mọi node.

### 8.8. data_dir và bin_dir

`data_dir` phải trỏ tới PGDATA của node đó. `bin_dir` giúp Patroni tìm đúng PostgreSQL binaries, đặc biệt khi host có nhiều major versions cài song song.

Không để hai Patroni nodes quản lý chung một data directory. Shared filesystem active-active không phải thiết kế physical streaming HA thông thường.

### 8.9. authentication

Patroni cần credentials cho PostgreSQL superuser/admin operations và replication. Tách credentials khỏi application role. Cấu hình REST API authentication riêng; không dùng cùng password cho API, PostgreSQL và DCS.

### 8.10. tags

Một số tags điều khiển eligibility hoặc routing policy:

- `nofailover`: node không được chọn làm failover candidate.
- `noloadbalance`: node không nên nhận read traffic từ load balancer.
- `nosync`: node không được chọn làm synchronous standby.
- `clonefrom`: đánh dấu node có thể được dùng làm source để clone replica trong cấu hình hỗ trợ.

Tags là policy hints cho Patroni/health routing, không phải firewall hay hard security boundary. Kiểm tra semantics theo release.

## 9. Bootstrap và khởi tạo cluster

### 9.1. Bootstrap chỉ diễn ra khi cluster chưa có state

`bootstrap` mô tả cách Patroni tạo cluster đầu tiên. Node được bootstrap tạo data directory, chạy initdb hoặc phương thức bootstrap được cấu hình, thiết lập users/pg_hba và ghi dynamic configuration ban đầu vào DCS.

Sau khi cluster đã được khởi tạo, các nodes còn lại join bằng cách clone/reinitialize từ một member phù hợp.

### 9.2. bootstrap.dcs

`bootstrap.dcs` chứa dynamic configuration ban đầu. Các giá trị thường gồm:

- `ttl`, `loop_wait`, `retry_timeout`.
- `maximum_lag_on_failover`.
- `check_timeline`.
- `synchronous_mode`, `synchronous_mode_strict`, `synchronous_node_count`.
- PostgreSQL parameters dùng chung.
- `use_pg_rewind`, `use_slots`, các policy khác tùy version.

Đây là initial seed. Sau khi cluster đã tồn tại, sửa file local `bootstrap.dcs` không nhất thiết thay đổi dynamic configuration đang lưu trong DCS. Dùng `patronictl edit-config` hoặc API được hỗ trợ để thay đổi dynamic config.

### 9.3. initdb

Patroni có thể truyền options cho `initdb`, ví dụ encoding, locale và data checksums. Chọn checksum từ đầu nếu muốn dùng điều kiện đó cho `pg_rewind`; không thể bật checksums tùy ý cho cluster đang tồn tại mà không có quy trình rebuild/upgrade.

### 9.4. pg_hba trong bootstrap

Patroni có thể tạo/duy trì các HBA rules theo cấu hình. Cần bảo đảm rule replication cho các node IPs và rule application phù hợp. Kiểm tra thứ tự rules, TLS requirement và authentication method.

### 9.5. Bootstrap leader

Khi cluster chưa có leader, một node sẽ thắng quá trình bootstrap/leader ownership qua DCS. Node đó tạo PostgreSQL primary đầu tiên. Các nodes khác sau đó clone từ leader và start ở standby mode.

### 9.6. Không bootstrap hai cluster cùng scope

Nếu hai node cùng khởi tạo cluster riêng với cùng scope/namespace do DCS bị xóa hoặc config nhầm, có thể tạo hai data histories không tương thích. Trước khi bootstrap lại, xác định DCS state và database data directory nào là source of truth.

### 9.7. Clone methods

Patroni hỗ trợ các phương thức tạo replica như `pg_basebackup`, pgBackRest, Barman hoặc custom replica creation methods tùy cấu hình. Lựa chọn phải đảm bảo standby nhận được base backup và WAL cần thiết.

### 9.8. Bootstrap từ backup tool

Nếu dùng pgBackRest/Barman, Patroni có thể gọi custom `create_replica_method` để restore base backup. Phải kiểm tra:

- Backup set và repository đúng cluster.
- WAL đủ để recovery.
- Tablespaces được map đúng.
- Credentials/repository access có trên mọi node cần clone.
- Method trả exit code và log phù hợp để Patroni biết kết quả.

### 9.9. Không clone từ node stale nếu có source tốt hơn

Một replica lag lớn hoặc đang gặp lỗi storage có thể không phải clone source tốt. Dùng tags/replica creation policy để chọn nguồn phù hợp và theo dõi tải trên upstream.

### 9.10. Xác minh sau bootstrap

Kiểm tra:

- `patronictl list` có một leader và các replicas.
- DCS có member/leader state.
- PostgreSQL primary/standby role đúng.
- `pg_stat_replication` và `pg_stat_wal_receiver` hoạt động.
- REST API trả role/health tương ứng.
- Application endpoint chỉ route writes tới leader.

## 10. Dynamic configuration và patronictl

### 10.1. Local configuration và dynamic configuration

Patroni có hai nguồn cấu hình quan trọng:

- **Local configuration:** node-specific settings như name, listen/connect address, data directory, DCS endpoints, REST API và credentials.
- **Dynamic configuration:** settings dùng chung của cluster, lưu trong DCS, như TTL/loop policy, failover policy, synchronous mode và PostgreSQL parameters được quản lý tập trung.

Một số settings chỉ có thể đặt local; một số khác có thể được quản lý dynamic. Không giả định mọi YAML key đều sửa được bằng `edit-config`.

### 10.2. patronictl list

```bash
patronictl -c /etc/patroni/patroni.yml list
```

Lệnh hiển thị member name, role, state, timeline, lag và thông tin cluster tùy version. Đây là lệnh vận hành đầu tiên để xem topology; vẫn phải kiểm tra PostgreSQL và DCS khi sự cố.

### 10.3. patronictl show-config

```bash
patronictl -c /etc/patroni/patroni.yml show-config
```

Hiển thị dynamic configuration đang lưu trong DCS. So sánh với file local khi điều tra vì thay đổi trong local YAML có thể không được áp dụng cho dynamic fields.

### 10.4. patronictl edit-config

```bash
patronictl -c /etc/patroni/patroni.yml edit-config
```

Lệnh mở editor để thay dynamic config. Thay đổi phải được review, validate và áp dụng có kiểm soát. Một số PostgreSQL parameters cần restart; Patroni có thể lên lịch/restart theo policy.

### 10.5. Set config từ command line

Một số versions hỗ trợ:

```bash
patronictl -c /etc/patroni/patroni.yml \
  edit-config --set maximum_lag_on_failover=1048576
```

Kiểm tra help của đúng release vì CLI flags/semantics có thể thay đổi. Không dùng ví dụ này như lệnh chung cho mọi version.

### 10.6. patronictl reload

```bash
patronictl -c /etc/patroni/patroni.yml reload app-ha
```

Reload yêu cầu Patroni nạp lại cấu hình được hỗ trợ mà không restart toàn bộ node. Một số PostgreSQL parameters cần restart hoặc chỉ có hiệu lực khi PostgreSQL reload; đọc output và kiểm tra pending_restart.

### 10.7. patronictl restart

```bash
patronictl -c /etc/patroni/patroni.yml restart app-ha pg-node-b
```

Restart một node cần hiểu role và failover policy. Không restart leader trong production nếu chưa có kế hoạch HA/switchover phù hợp.

### 10.8. patronictl switchover

Switchover có kế hoạch chuyển leader sang một replica đã được chọn. Xác nhận candidate, lag, timeline và application readiness trước khi thực hiện. Dùng lệnh help và cú pháp theo version.

### 10.9. patronictl failover

Failover command hỗ trợ promotion có chủ đích khi leader không còn khả dụng hoặc operator quyết định chọn node. Đây là thao tác nhạy cảm: chỉ thực hiện sau khi đánh giá primary cũ, fencing và RPO.

### 10.10. patronictl reinit

Reinitialize một replica bằng cách tạo lại data directory từ upstream/clone method. Nó phá hủy dữ liệu local replica hiện tại. Xác nhận đúng member, backup/recovery method và maintenance window trước khi chạy.

### 10.11. Không sửa DCS keys trực tiếp

DCS keys là state machine của Patroni. Thay đổi thủ công có thể tạo leader ownership giả, xóa config hoặc làm nodes hiểu sai topology. Dùng `patronictl`/API được hỗ trợ; chỉ can thiệp DCS trực tiếp theo runbook recovery chính thức.

## 11. Tích hợp DCS backend

### 11.1. etcd cluster riêng

Với etcd, triển khai một cluster voting members độc lập với PostgreSQL nodes. Ví dụ ba members:

```text
etcd-a 10.20.0.21:2379
etcd-b 10.20.0.22:2379
etcd-c 10.20.0.23:2379

Patroni nodes -> client endpoints :2379
etcd members -> peer endpoints :2380
```

Port mặc định có thể thay đổi. Client port và peer port là hai luồng khác nhau; firewall rules phải cho đúng traffic.

### 11.2. etcd client vs peer TLS

etcd có thể dùng TLS cho client-to-server và peer-to-peer traffic. Patroni cần trust CA và client credentials phù hợp với etcd endpoint. Peer certificates cần SAN phù hợp với advertised peer URLs.

Không bật TLS cho client mà quên peer links; etcd members có thể không form quorum.

### 11.3. etcd quorum health

Giám sát:

- Member count và leader.
- Raft applied/committed index.
- Proposal failures/latency.
- Disk fsync latency.
- DB size/quota alarms.
- Peer network latency và packet loss.
- Snapshot/compaction health.

Một etcd endpoint trả lời request không nhất thiết có nghĩa cluster còn quorum và có thể commit writes.

### 11.4. etcd backup

Backup etcd snapshot theo hướng dẫn chính thức của etcd, lưu an toàn và test restore. Snapshot DCS không thay PostgreSQL backup. Khi restore DCS, cần đối chiếu cluster metadata với database data histories để tránh khôi phục một leader lock cũ không còn đúng.

### 11.5. Consul servers và agents

Consul triển khai server agents có quorum và client agents trên nodes hoặc network segment. Patroni có thể kết nối tới Consul servers theo backend config. Đảm bảo:

- Server count/quorum đủ.
- ACL token cho Patroni chỉ có quyền cần thiết trên namespace/prefix.
- Gossip encryption và TLS đúng.
- Session TTL/lock delay phù hợp.
- Snapshot/restore và upgrades có runbook.

### 11.6. Consul session semantics

Consul sessions có thể gắn lock ownership với session lifecycle/health checks. Khi session invalidates hoặc hết hạn, lock có thể được giải phóng. Agent cần xử lý network partitions và session renewals đúng; không suy luận chỉ từ một key còn hiện diện.

### 11.7. ZooKeeper ensemble

ZooKeeper triển khai ensemble với quorum. Patroni kết nối tới ensemble servers; cần cấu hình session timeout, ACL/authentication và TLS theo phiên bản. Giám sát:

- Quorum/leader/follower state.
- Outstanding requests và latency.
- Session expirations/reconnects.
- Transaction log/snapshot storage.
- Disk capacity và compaction/cleanup policy.

### 11.8. Kubernetes API backend

Khi dùng Kubernetes backend, Patroni agents tương tác với Kubernetes API bằng service account. Tạo RBAC role/binding cho đúng namespace và resources mà Patroni cần quản lý. Không cấp cluster-admin nếu không có lý do rõ ràng.

Một số triển khai dùng Endpoints/ConfigMaps hoặc Lease resources theo Patroni release/backend options. Dùng đúng schema/permissions trong documentation của phiên bản cài đặt; không trộn YAML từ một release với release khác.

### 11.9. Kubernetes API outage

Khi API server unavailable, Patroni có thể không cập nhật leader state hoặc gia hạn ownership. Pod PostgreSQL có thể vẫn đang chạy và phục vụ connection hiện có, nhưng orchestration không thể đảm bảo failover an toàn. Thiết kế availability cho Kubernetes control plane cũng là một phần của database HA.

### 11.10. Chọn backend

Ưu tiên backend:

- Đã có operational expertise.
- Có quorum/failure domain rõ ràng.
- Có TLS/authn/authz và audit.
- Có metrics/alerts và backup/restore runbook.
- Được Patroni version hỗ trợ chính thức.
- Có latency ổn định trong failure domain được thiết kế.

Không chọn DCS chỉ vì nó đã được cài sẵn ở đâu đó mà không xác định ai chịu trách nhiệm vận hành.

## 12. Patroni REST API và health checks

### 12.1. REST API dùng để làm gì?

Mỗi Patroni agent cung cấp REST API trên port cấu hình trong `restapi`. API cho phép:

- Health/load balancer kiểm tra node role.
- Operator đọc trạng thái node/cluster.
- HA tooling gửi một số thao tác quản trị được hỗ trợ.
- Monitoring thu thập thông tin runtime.

API này là control surface nhạy cảm. Chỉ expose trong management network và bật authentication/TLS phù hợp.

### 12.2. Các endpoint health phổ biến

Các endpoint thông dụng trong nhiều Patroni releases:

| Endpoint | Mục đích thường dùng |
| --- | --- |
| `/health` | Kiểm tra process/health cơ bản của Patroni node. |
| `/primary` | Trả success khi node là primary/leader theo trạng thái Patroni. |
| `/replica` | Trả success khi node là replica đủ điều kiện theo endpoint semantics. |
| `/replica?lag=...` | Kiểm tra replica và áp dụng ngưỡng lag nếu release hỗ trợ. |
| `/read-only` | Node có thể phục vụ read-only role. |
| `/read-write` | Node có thể phục vụ read-write role. |
| `/leader` | Kiểm tra leader status theo API semantics. |
| `/liveness` và `/readiness` | Health probes trên các releases có hỗ trợ. |

Danh sách, status code và semantics phải xác nhận với REST API documentation của Patroni version đang chạy. Không coi mọi endpoint tương đương nhau.

### 12.3. Health endpoint và routing

Load balancer cho writes nên kiểm tra endpoint primary/leader thích hợp; read pool có thể kiểm tra replica endpoint và lag threshold. Endpoint `/health` đơn thuần không đủ để định tuyến writes vì node khỏe có thể là standby.

### 12.4. Ví dụ curl

```bash
curl --fail http://10.20.0.11:8008/primary
curl --fail http://10.20.0.12:8008/replica
```

Nếu REST API yêu cầu auth/TLS, thêm credentials/certificates theo policy. Không dùng `curl -k` như giải pháp production vì nó bỏ qua certificate verification.

### 12.5. REST API authentication

Cấu hình username/password hoặc cơ chế authentication được Patroni release hỗ trợ. Bảo vệ credentials, giới hạn nguồn truy cập và bật TLS khi đi qua network không tin cậy. Chỉ endpoint đọc trạng thái cũng có thể tiết lộ topology và addresses.

### 12.6. Không public expose API

REST API có các thao tác điều khiển cluster trong một số cấu hình. Nếu attacker truy cập được API với quyền phù hợp, họ có thể gây gián đoạn hoặc thay đổi role. Đặt API sau private network/firewall, authentication và audit.

## 13. Tích hợp HAProxy và client routing

### 13.1. Vì sao cần routing layer?

Ứng dụng thường cần một endpoint ổn định dù primary thay đổi. HAProxy hoặc proxy tương tự kiểm tra Patroni REST API rồi route write connections tới node leader. Các read connections có thể đi tới standby pool.

### 13.2. Ví dụ HAProxy backend cho primary

```conf
frontend postgres_write
    bind *:5000
    default_backend postgres_primary

backend postgres_primary
    mode tcp
    option httpchk GET /primary
    http-check expect status 200
    default-server inter 3s fall 3 rise 2 on-marked-down shutdown-sessions
    server pg_a 10.20.0.11:5432 check port 8008
    server pg_b 10.20.0.12:5432 check port 8008
    server pg_c 10.20.0.13:5432 check port 8008
```

Đây là mẫu minh họa; kiểm tra cú pháp theo HAProxy version. HTTP health checks gọi REST API port 8008 trong khi PostgreSQL traffic đi qua port 5432.

### 13.3. Ví dụ backend cho read replicas

```conf
frontend postgres_read
    bind *:5001
    default_backend postgres_replicas

backend postgres_replicas
    mode tcp
    balance roundrobin
    option httpchk GET /replica
    http-check expect status 200
    server pg_b 10.20.0.12:5432 check port 8008
    server pg_c 10.20.0.13:5432 check port 8008
```

Không đưa primary vào read pool trừ khi policy cho phép. Nếu read query cần freshness/consistency, route theo lag/remote_apply policy chứ không chỉ round-robin.

### 13.4. Kiểm soát lag

Một replica có thể ở recovery nhưng lag quá lớn. Endpoint `/replica?lag=...` có thể giúp loại replica vượt ngưỡng nếu Patroni release hỗ trợ. Đặt ngưỡng theo workload/RPO; health check lag không thay metrics đầy đủ.

### 13.5. PgBouncer

PgBouncer quản lý connection pooling, còn Patroni quản lý PostgreSQL HA. Có thể đặt PgBouncer phía sau HAProxy hoặc tích hợp auth/query routing theo kiến trúc. PgBouncer không tự biết primary đã đổi nếu endpoint phía sau không cập nhật; cần connection reset/reconnect strategy.

### 13.6. VIP và keepalived

Một số triển khai dùng VIP chuyển giữa nodes. Keepalived/VRRP có thể di chuyển địa chỉ mạng, nhưng phải dựa trên Patroni role checks và fencing. VRRP election riêng không thay DCS leader election; không để VIP trỏ vào hai primaries hoặc node không có leader lock.

### 13.7. DNS và service discovery

DNS record có TTL/cache behavior; failover không thể chỉ đổi DNS và mong mọi clients chuyển ngay. Connection pools có thể giữ IP cũ. Dùng proxy/VIP hoặc service discovery có health-aware endpoints; hiểu cache TTL và retry behavior.

### 13.8. Connection pool sau failover

Sau promotion, connections cũ tới primary cũ có thể bị reset hoặc vẫn còn open tùy network/fencing. Ứng dụng cần:

- Reconnect với endpoint mới.
- Retry transaction idempotently khi outcome unknown.
- Không retry mù các non-idempotent operations.
- Phát hiện read-only/standby errors và chuyển write traffic về endpoint đúng.

### 13.9. Tách read và write pools

Đặt endpoint riêng cho writes và reads giúp kiểm soát routing. Read pool có thể chọn replicas theo lag, locality hoặc workload. Write pool chỉ route tới node được Patroni xác nhận leader.

### 13.10. Routing không phải fencing

HAProxy mark primary cũ down chỉ ngăn traffic đi qua proxy đó. Client có thể kết nối trực tiếp tới IP cũ, hoặc proxy khác vẫn route tới node đó. Fencing phải ngăn old primary writes ở tầng database/host/network authority.

## 14. Synchronous mode trong Patroni

### 14.1. PostgreSQL synchronous replication và Patroni policy

PostgreSQL cung cấp `synchronous_standby_names` và `synchronous_commit`. Patroni có thể quản lý các tham số này và theo dõi synchronous standby membership để kết hợp với failover eligibility.

### 14.2. synchronous_mode

Dynamic setting `synchronous_mode` bật synchronous replication management của Patroni. Patroni chọn standby phù hợp và cấu hình PostgreSQL synchronous standby policy theo trạng thái cluster.

### 14.3. synchronous_mode_strict

Strict mode có thể giữ yêu cầu synchronous acknowledgement khi không có synchronous standby đủ điều kiện, khiến writes chờ thay vì tự chuyển sang asynchronous behavior theo policy. Điều này tăng durability guarantees nhưng giảm write availability khi standby không sẵn sàng.

Kiểm tra semantics và default theo Patroni release trước khi bật.

### 14.4. synchronous_node_count

Setting này xác định số synchronous standbys Patroni cần theo policy/release. Số lượng lớn hơn có thể tăng redundancy nhưng cũng tăng commit latency và phụ thuộc availability của nhiều nodes.

### 14.5. maximum_lag_on_failover

Đặt ngưỡng lag tối đa để một replica được xem là candidate khi failover. Giá trị thường tính theo bytes WAL. Đây là một guardrail để tránh promote replica quá stale, không phải cam kết RPO chính xác trong mọi race/failure.

### 14.6. check_timeline

Policy kiểm tra timeline giúp Patroni đánh giá replica có history phù hợp trước promotion. Timeline check đặc biệt quan trọng sau failover/rejoin, khi nodes có thể diverge.

### 14.7. Synchronous node tags

Tag `nosync` có thể loại node khỏi synchronous standby selection. Dùng tags để thể hiện policy, ví dụ node DR xa không nên nằm trên commit path vì latency cao.

### 14.8. Synchronous mode không giải quyết mọi data loss

Durability còn phụ thuộc:

- PostgreSQL `synchronous_commit` level.
- Node nào thực sự xác nhận commit.
- Candidate nào được promote.
- Fencing/leader ownership.
- Application transactions có dùng local/off không.
- External side effects ngoài PostgreSQL.

Không quảng bá “zero data loss” nếu chưa xác định đầy đủ các điều kiện.

### 14.9. Strict mode và mất standby

Nếu strict mode yêu cầu synchronous standby mà tất cả standbys mất kết nối, transactions cần remote acknowledgement có thể block. Đây là trade-off được chọn để ưu tiên durability. Runbook phải nêu rõ ai được phép tạm giảm policy và cách khôi phục sau incident.

### 14.10. Synchronous state trong patronictl

`patronictl list`/dynamic config và PostgreSQL `pg_stat_replication.sync_state` giúp kiểm tra synchronous membership. So sánh cả hai vì DCS policy và PostgreSQL runtime state có thể tạm thời chưa đồng bộ khi node chuyển trạng thái.

## 15. Automatic failover và switchover

### 15.1. Automatic failover

Failover tự động xảy ra khi Patroni xác định leader không còn hoạt động/không giữ được ownership theo policy. Các replica agents trao đổi trạng thái qua DCS, đánh giá candidate eligibility và một node được phép lấy leader lock rồi promote.

Một luồng khái niệm:

```text
Leader A không renew được leader lock
             |
             v
      Ownership hết hạn
             |
             v
  Replica agents quan sát DCS state
             |
             v
  Candidate eligibility / WAL position
             |
             v
  Một node claim leader ownership
             |
             v
      Promote PostgreSQL
             |
             v
  Publish new leader/member state
             |
             v
  Proxy chuyển write traffic
```

Đây là mô hình logic. Chi tiết election và candidate selection do Patroni release/backend thực hiện.

### 15.2. Điều kiện candidate

Candidate có thể bị loại vì:

- Node đã được tag `nofailover`.
- PostgreSQL không chạy/không ở trạng thái replica phù hợp.
- WAL lag vượt `maximum_lag_on_failover`.
- Timeline không phù hợp với `check_timeline` policy.
- Node không thể truy cập DCS hoặc không thể claim ownership.
- Synchronous policy yêu cầu một node khác/đủ điều kiện khác.

Không coi replica gần nhất về địa lý là candidate tốt nhất nếu WAL history của nó cũ hơn.

### 15.3. maximum_lag_on_failover

Setting này giới hạn WAL lag mà Patroni chấp nhận khi xem xét replica cho promotion. Mục tiêu là tránh promote một replica đã quá stale. Giá trị cần dựa trên:

- WAL generation rate ở giờ cao điểm.
- RPO chấp nhận.
- Network/storage capacity.
- Thời gian DCS/election và detection.
- Synchronous mode policy.

Một ngưỡng byte cố định không tự biểu diễn thời gian mất dữ liệu nếu WAL rate thay đổi mạnh.

### 15.4. No candidate đủ điều kiện

Nếu không có replica nào đáp ứng policy, Patroni có thể không tự promote. Đây là hành vi an toàn khi không thể chứng minh candidate đủ gần primary. Operator cần quyết định theo RPO và runbook, không ép promotion mù quáng.

### 15.5. Manual failover

Manual failover dùng khi operator cần chọn candidate cụ thể hoặc automatic failover không thể hoàn tất. Trước thao tác:

1. Xác định primary cũ còn sống hay đã chết.
2. Fence primary cũ nếu có khả năng nó vẫn nhận writes.
3. Kiểm tra DCS quorum/leader state.
4. So sánh replica lag và timeline.
5. Chọn đúng candidate.
6. Thực hiện failover bằng `patronictl`/API theo version.
7. Xác minh new leader và routing.

### 15.6. Switchover có kế hoạch

Switchover chuyển leader khi primary cũ vẫn hoạt động. Patroni có thể kiểm tra replicas, chờ WAL đồng bộ và phối hợp chuyển role theo một lịch trình có kiểm soát.

Dùng switchover cho:

- Bảo trì host/OS.
- Nâng cấp kernel hoặc storage.
- Di chuyển primary sang availability zone khác.
- Kiểm thử DR/HA định kỳ.

### 15.7. Switchover và failover khác nhau

| Khía cạnh | Switchover | Failover |
| --- | --- | --- |
| Primary cũ | Thường còn hoạt động và phối hợp được. | Có thể đã chết hoặc không truy cập được. |
| WAL position | Có thể chờ replica bắt kịp. | Có thể không biết WAL cuối cùng của primary. |
| RPO | Có thể tiến gần zero nếu đồng bộ hoàn tất và procedure đúng. | Phụ thuộc replica được promote và replication mode. |
| Quy trình | Planned/controlled. | Incident response. |
| Mục tiêu | Bảo trì/chuyển vai trò. | Khôi phục dịch vụ sau sự cố. |

### 15.8. Reinitialize replica

Nếu replica diverged, thiếu WAL hoặc không thể follow primary mới, Patroni có thể reinitialize nó bằng clone method. Reinitialize xóa/ghi lại data directory replica. Chỉ thực hiện trên member đúng và xác nhận source/backup trước.

### 15.9. Failover không đồng nghĩa traffic đã chuyển

Sau khi PostgreSQL promote, ứng dụng vẫn có thể kết nối vào endpoint cũ. Cần proxy/VIP/DNS/service discovery và connection pool xử lý role change. Đo RTO tới lúc application-ready, không chỉ thời điểm promotion hoàn tất.

### 15.10. Patroni không giải quyết transaction outcome unknown

Nếu client mất connection đúng lúc COMMIT, client có thể không biết transaction đã commit trên primary cũ hay chưa. Ứng dụng cần idempotency keys hoặc query business state trước khi retry để tránh duplicate payment/order/events.

## 16. DCS outage, network partition và failsafe

### 16.1. Mất một DCS member

Trong DCS có quorum, mất một member vẫn có thể duy trì writes nếu majority còn hoạt động. Ví dụ etcd cluster 3 members có thể tiếp tục khi một member lỗi. Cần sửa member lỗi sớm trước khi mất thêm một member.

### 16.2. Mất quorum

Khi DCS không còn quorum, DCS không thể commit coordination writes. Patroni không thể gia hạn leader ownership theo cơ chế bình thường. Automatic failover có thể bị đình trệ vì không có authority chung để cấp quyền leader mới.

### 16.3. Primary vẫn chạy khi DCS mất

PostgreSQL process trên primary có thể tiếp tục chạy và existing clients vẫn có kết nối. Nhưng khả năng phục vụ writes an toàn phụ thuộc Patroni leader lock/failsafe behavior và policy. Không được suy ra “database trả lời query nên primary vẫn hợp lệ”.

### 16.4. failsafe_mode

Một số Patroni versions cung cấp `failsafe_mode` để xử lý một số tình huống DCS unavailable. Khi bật, leader có thể tiếp tục hoạt động nếu đáp ứng các điều kiện liên lạc/consensus giữa cluster members theo cơ chế failsafe của Patroni, thường qua REST API member checks.

Đây là một policy đặc biệt, không phải cách bỏ qua DCS. Phải đọc tài liệu đúng release, xác định network reachability requirements và test các partition scenarios trước khi bật.

### 16.5. DCS outage không được tự động xử lý bằng cách xóa leader key

Xóa leader key bằng tay trong lúc primary vẫn chạy có thể tạo điều kiện cho node khác claim leadership trong khi old primary chưa bị fence. Chỉ dùng recovery procedure chính thức sau khi xác định trạng thái tất cả nodes.

### 16.6. Network partition giữa database nodes

Một node có thể truy cập DCS nhưng không truy cập được primary; node khác có thể truy cập primary nhưng mất DCS. Phải phân tích connectivity matrix, không chỉ ping từ một máy.

### 16.7. Network partition giữa Patroni và PostgreSQL

Patroni có thể mất SQL connection tới PostgreSQL trong khi process vẫn chạy. Cần xác định process health, socket, disk stall và leader lock. Patroni có thể stop/restart process theo policy; tránh tự kill PostgreSQL khi chưa hiểu trạng thái recovery.

### 16.8. Network partition giữa DCS members

DCS quorum protocol quyết định partition nào có thể commit. Một minority partition không được phép cấp leader ownership mới. Giám sát quorum và không chạy hai DCS clusters độc lập với cùng Patroni scope.

### 16.9. Failsafe và watchdog là hai lớp khác nhau

Failsafe mode định nghĩa Patroni behavior khi DCS unavailable theo điều kiện của nó. Watchdog/fencing là cơ chế buộc node không tiếp tục làm leader khi không thể chứng minh ownership. Hai lớp bổ trợ nhau; không thay thế quorum hoặc fencing hạ tầng.

### 16.10. Runbook khi DCS mất quorum

1. Không xóa DCS keys hoặc bootstrap lại cluster.
2. Kiểm tra member status, logs, network, disk và quorum.
3. Xác định primary có đang giữ ownership hợp lệ hay không.
4. Giữ nguyên single-writer rule; không promote standby tùy tiện.
5. Khôi phục DCS quorum theo backend-specific runbook.
6. Sau khi DCS ổn định, kiểm tra Patroni leader/member state và PostgreSQL roles.
7. Xác minh replication và routing trước khi mở traffic rộng.

## 17. Fencing và watchdog

### 17.1. Vì sao leader lock cần fencing?

DCS lease chỉ điều khiển quyền ownership trong control plane. Nếu old primary bị pause hoặc partition nhưng vẫn có thể ghi vào local storage và nhận client traffic, lease expiration ở DCS không tự dừng nó. Fencing bảo đảm old primary không thể tiếp tục làm writer sau khi quyền chuyển sang node khác.

### 17.2. Patroni watchdog

Patroni có thể tích hợp watchdog để reset node nếu không thể renew leader lock trong giới hạn an toàn. Watchdog giúp ràng buộc thời gian mà một node có thể tiếp tục chạy khi mất ownership.

### 17.3. Hardware watchdog

Hardware watchdog được host/firmware cung cấp. Patroni có thể mở watchdog device và yêu cầu hệ thống reset nếu không được keep-alive đúng hạn. Cần kiểm tra driver, permissions, device path và hành vi reset thật.

### 17.4. Software watchdog

Software watchdog có thể dùng cơ chế kernel/system service tùy nền tảng. Nó có thể không bảo vệ trước mọi dạng kernel/host failure như hardware watchdog. Xác nhận failure model và test bằng môi trường disposable.

### 17.5. watchdog.mode

Patroni releases có các mode watchdog như `off`, `automatic` và `required` theo phiên bản. Required mode có thể ngăn node khởi động/giữ leader nếu watchdog không hoạt động đúng; automatic có behavior fallback khác. Kiểm tra semantics của version trước khi đặt.

### 17.6. watchdog safety margin

Watchdog timeout và Patroni TTL/loop_wait/retry_timeout cần được phối hợp. Nếu watchdog timeout dài hơn leader lease safety window, node có thể tiếp tục hoạt động quá lâu sau khi mất ownership. Nếu quá ngắn, node có thể reset do scheduler pause/network jitter bình thường.

### 17.7. Fencing ngoài Patroni

Ở tầng hạ tầng, fencing có thể gồm:

- Tắt VM/instance cũ.
- Power off node bằng out-of-band management.
- Revoke storage write access.
- Network isolation khỏi application clients.
- Detach volume khỏi old primary.

Chỉ dùng phương pháp có thể xác minh kết quả. Gửi lệnh stop qua network đang partition mà không nhận xác nhận không phải fencing chắc chắn.

### 17.8. Test fencing

Diễn tập ít nhất:

- Patroni process chết nhưng PostgreSQL còn chạy.
- Node bị pause lâu hơn TTL.
- DCS partition.
- Host mất kết nối management network.
- Watchdog device không tồn tại.
- Proxy chuyển traffic nhưng old primary còn accessible trực tiếp.

Mục tiêu là chứng minh không có hai writers đồng thời.

## 18. Kubernetes và PostgreSQL orchestration

### 18.1. Hai lớp điều phối có thể cùng tồn tại

Trong Kubernetes, có thể có:

- Kubernetes control plane quản lý Pods, StatefulSets, Services, PersistentVolumes và scheduling.
- Patroni quản lý PostgreSQL roles, leader lock, replication và database failover.
- Một PostgreSQL operator quản lý lifecycle của Patroni cluster thông qua Custom Resources.

Mỗi lớp có trách nhiệm khác nhau. Pod restart không tự động đồng nghĩa PostgreSQL role đã an toàn; Patroni leader election không tự tạo PersistentVolume hay Service routing.

### 18.2. Patroni chạy trong Pods

Một số kiến trúc chạy Patroni sidecar/agent cùng PostgreSQL container trong mỗi Pod. Patroni quản lý PostgreSQL process trong container và dùng DCS backend được cấu hình (có thể là Kubernetes API). Pod identity và storage identity phải ổn định theo thiết kế.

### 18.3. Kubernetes Service cho primary

Một Service có thể chọn Pod labels được cập nhật theo role. Tuy nhiên, label update phải dựa trên trạng thái Patroni đáng tin cậy và có thời gian propagation. Không để hai pods mang label primary trong cùng một failover.

### 18.4. Readiness và liveness probes

- Liveness kiểm tra container/process có cần restart hay không.
- Readiness quyết định Pod có nhận traffic qua Service không.
- Patroni REST role endpoints kiểm tra node có phải primary/replica đủ điều kiện hay không.

Không dùng một TCP probe tới port PostgreSQL làm primary health check; standby cũng có thể mở port PostgreSQL.

### 18.5. StatefulSet không phải leader election

StatefulSet cung cấp stable ordinal/network identity và volume association. Nó không tự quyết định PostgreSQL primary. Replica role và leader ownership do Patroni/DCS hoặc operator đảm nhiệm.

### 18.6. PersistentVolumes

Mỗi PostgreSQL node cần storage phù hợp, có lifecycle độc lập. Khi Pod reschedule, volume được attach lại theo policy. Không mount cùng một PGDATA read-write vào nhiều PostgreSQL instances như cách tạo HA.

### 18.7. Operator và Patroni

PostgreSQL operators có thể dùng Patroni bên trong để quản lý HA, hoặc dùng một architecture khác. Operator thường quản lý:

- Custom Resource/desired state.
- Pod/StatefulSet/Service lifecycle.
- Backup/restore integration.
- Certificates/secrets.
- Upgrades và configuration rollouts.
- Monitoring/maintenance windows.

Trước khi cài Patroni độc lập bên trong một cluster đã do operator quản lý, xác định rõ ai là controller của PostgreSQL lifecycle. Không để hai controllers cùng start/stop/promote một instance.

### 18.8. RBAC cho Kubernetes DCS

Service account của Patroni chỉ được cấp quyền cần thiết trên namespace/resources backend sử dụng. Không cấp cluster-admin mặc định. Tách quyền operator/controller khỏi quyền Patroni agent khi có thể.

### 18.9. Kubernetes API outage

Nếu API server hoặc control plane không available, Pod và PostgreSQL process có thể vẫn chạy, nhưng Patroni có thể không cập nhật được DCS ownership. Điều này ảnh hưởng failover. Cần monitor control-plane health như một dependency của database HA.

### 18.10. Không stack nhiều leader elections

Nếu Kubernetes operator, Patroni, keepalived và một script tự viết đều cố quyết định primary, các controllers có thể đưa ra quyết định trái ngược. Chọn một authority cho database leader election và định nghĩa các lớp khác chỉ consume trạng thái đó.

## 19. Thay đổi cấu hình và lifecycle operations

### 19.1. Thay đổi dynamic config

Sửa dynamic config bằng `patronictl edit-config` hoặc API được hỗ trợ. Trước khi áp dụng:

1. Export/lưu config hiện tại.
2. Xác định parameter nào dynamic và parameter nào cần restart.
3. Kiểm tra constraints giữa TTL, loop_wait và retry_timeout.
4. Kiểm tra tác động tới synchronous replication/failover.
5. Thay đổi trong maintenance/change window nếu cần.
6. Xác nhận runtime state trên mọi node.

### 19.2. Thay đổi local config

Node-specific fields như listen/connect address, data_dir, DCS endpoint và REST API settings thường nằm trong local config. Thay đổi có thể cần reload/restart Patroni. Đảm bảo không làm node mất DCS connectivity hoặc đổi identity ngoài ý muốn.

### 19.3. PostgreSQL parameter changes

Một số PostgreSQL parameters chỉ reload; một số cần restart. Patroni theo dõi dynamic PostgreSQL parameters và có thể yêu cầu restart. Kiểm tra `pending_restart`, `pg_settings.context` và Patroni output trước khi thao tác.

### 19.4. Rolling restart

Với replica:

1. Restart từng replica một.
2. Đợi replica quay lại streaming và bắt kịp.
3. Chỉ chuyển sang node tiếp theo khi topology đủ redundancy.
4. Tránh restart toàn bộ standbys cùng lúc.

Với leader, cân nhắc switchover trước khi restart để giảm downtime.

### 19.5. PostgreSQL minor upgrade

Minor upgrade trong cùng major thường thay binaries/package và restart node theo rolling plan. Kiểm tra compatibility và release notes. Giữ ít nhất một replica healthy trong quá trình rolling upgrade.

### 19.6. PostgreSQL major upgrade

Major upgrade cần quy trình riêng vì physical data format thay đổi. Patroni không biến major upgrade thành một package update bình thường. Lập kế hoạch bằng `pg_upgrade`, logical migration hoặc phương pháp được vendor/operator hỗ trợ; kiểm thử rollback và replication topology.

### 19.7. Patroni upgrade

Nâng cấp Patroni version có thể thay đổi DCS backend APIs, config validation, REST API và failover behavior. Đọc release notes, kiểm tra compatibility với PostgreSQL/DCS, thử staging và rolling upgrade theo tài liệu.

### 19.8. DCS upgrade

DCS upgrade là một operation độc lập có thể ảnh hưởng quorum. Thực hiện rolling upgrade theo hướng dẫn backend, monitor member health và tránh nâng cấp nhiều voting members cùng lúc.

### 19.9. Node maintenance

Trước khi tắt một node:

- Xác định role.
- Nếu là leader, thực hiện switchover có kế hoạch.
- Xác nhận các replicas còn lại và DCS quorum đủ.
- Đảm bảo backup/WAL archive hoạt động.
- Thực hiện maintenance.
- Start node, xác minh role/replication và routing.

### 19.10. Thay đổi DCS endpoint

Đổi DCS endpoints có thể khiến tất cả Patroni agents mất coordination nếu rollout sai. Cần bảo đảm backend mới chứa đúng cluster state hoặc thực hiện migration theo procedure chính thức. Không tạo một DCS rỗng rồi cho nodes production kết nối vào.

## 20. Backup, restore và disaster recovery cho Patroni cluster

### 20.1. Có hai loại dữ liệu cần bảo vệ

1. **PostgreSQL data:** base backups, WAL archive, tablespaces, configs, extensions và external dependencies.
2. **DCS/control-plane state:** dynamic configuration, cluster metadata và backend-specific state.

Chúng có lifecycle và consistency requirements khác nhau.

### 20.2. Patroni không tự backup database

Dùng pgBackRest, Barman, pg_basebackup hoặc giải pháp backup phù hợp. Cấu hình WAL archiving liên tục và retention đủ cho PITR. Kiểm tra backup từ primary/standby theo tool support.

### 20.3. DCS snapshot không phải database backup

etcd/Consul/ZooKeeper snapshots chỉ bảo vệ coordination state. Chúng không chứa PostgreSQL table data. Ngược lại, PostgreSQL base backup không tự chứa DCS leader metadata.

### 20.4. Khôi phục PostgreSQL cluster

Restore database data theo backup tool và PostgreSQL recovery procedure. Sau đó cấu hình Patroni để quản lý đúng data directory/cluster identity. Tránh để Patroni tự bootstrap một cluster mới trên data directory chứa dữ liệu cần phục hồi.

### 20.5. Khôi phục DCS

Restore DCS theo backend documentation. Trước khi cho Patroni agents hoạt động:

- Xác định cluster scope/namespace.
- Xác minh leader key/lease không stale hoặc trỏ node cũ.
- Đối chiếu member records với PostgreSQL roles/timelines.
- Đảm bảo không có primary khác đang nhận writes.
- Dùng runbook Patroni/DCS recovery chính thức.

### 20.6. Restore DCS và PostgreSQL không đồng thời tùy tiện

DCS snapshot tại thời điểm T1 và PostgreSQL data restore tại T2 có thể không tương ứng cùng topology/leader/timeline. Lập manifest ghi thời điểm, scope, system identifier, timeline và backup IDs để reconcile.

### 20.7. DR ở region khác

Có thể đặt asynchronous standby ở region DR và DCS quorum/control plane theo topology phù hợp. Nếu DCS chỉ ở region primary và region đó mất hoàn toàn, Patroni DR có thể không có quorum để promote. Cần thiết kế control plane/witness/DR procedure để quyết định rõ trong region-loss scenario.

### 20.8. Không kéo DCS quorum qua WAN mà không đo

Quorum members ở nhiều regions có thể tăng RTT của mọi DCS writes và làm failover/renew latency lớn. Đánh đổi giữa locality, quorum survival và WAN failure. Thiết kế theo backend recommendations và đo network.

### 20.9. Backup restore drill

Kiểm tra:

- Restore base backup vào host mới.
- Replay WAL tới recovery target.
- Khởi tạo Patroni management theo đúng scope/namespace.
- Tạo lại replicas.
- Khôi phục routing.
- Test app role/permissions và business invariants.
- Đo RTO/RPO thực tế.

### 20.10. Immutable backups

Replication và DCS không bảo vệ trước ransomware/credential compromise. Giữ backup copies ở account/storage failure domain độc lập, immutability/object lock nếu phù hợp, mã hóa và access audit.

## 21. Security và hardening

### 21.1. Phân vùng mạng

Tách hoặc giới hạn các luồng:

- PostgreSQL client traffic.
- PostgreSQL replication traffic.
- Patroni REST API.
- DCS client traffic.
- DCS peer traffic.
- Backup repository access.
- Monitoring/admin access.

Chỉ mở source/destination/port cần thiết.

### 21.2. DCS credentials

Dùng etcd client certificates/authentication, Consul ACL tokens, ZooKeeper ACL/authentication hoặc Kubernetes service account/RBAC. Không dùng anonymous write access cho Patroni namespace.

### 21.3. DCS namespace isolation

Mỗi Patroni cluster nên có scope/namespace riêng. DCS permissions phải giới hạn vào prefix/resources của cluster. Một cluster không nên có quyền ghi metadata của cluster khác.

### 21.4. Patroni REST API

Bật authentication và TLS khi cần. Chỉ cho HAProxy/monitoring/admin networks truy cập. Không public expose endpoint có thể điều khiển cluster.

### 21.5. PostgreSQL replication role

Dùng role chuyên dụng với REPLICATION, giới hạn HBA source addresses. Password phải được quản lý và rotate theo policy. Role replication có quyền lấy base backup nên xem là quyền truy cập dữ liệu nhạy cảm.

### 21.6. Secrets distribution

Inject secrets qua secret manager/Kubernetes Secret với encryption at rest, filesystem permissions và rotation plan. Tránh ghi password vào Git, container image, logs hoặc command line.

### 21.7. TLS certificate rotation

Certificate expiry hoặc CA rotation có thể làm DCS/replication/API connections thất bại đồng loạt. Rollout CA trust trước, sau đó rotate leaf certificates, kiểm tra mọi nodes và giữ rollback window.

### 21.8. OS privileges

Chạy PostgreSQL dưới OS account chuyên dụng. Patroni cần quyền điều khiển PostgreSQL service và watchdog device theo deployment; không cấp root toàn thời gian nếu có thể dùng systemd permissions/sudo rules giới hạn.

### 21.9. Audit

Lưu audit trail cho:

- Dynamic configuration changes.
- Manual failover/switchover.
- DCS snapshot/restore.
- Node reinitialize/rewind.
- REST API administrative calls.
- Credential/certificate rotation.
- HAProxy/Service routing changes.

### 21.10. Supply chain

Pin Patroni/DCS/PostgreSQL versions, verify packages/images, theo dõi security advisories và nâng cấp theo staging. Không dùng container image không rõ nguồn cho database control plane.

## 22. Monitoring và observability

### 22.1. Monitor cả ba lớp

Một dashboard HA phải tổng hợp:

1. PostgreSQL data plane.
2. Patroni orchestration state.
3. DCS quorum/health.
4. Client routing.
5. Backup/recovery.

Chỉ monitor PostgreSQL port không cho biết DCS có quorum hay Patroni đang giữ leader lock hợp lệ.

### 22.2. PostgreSQL metrics

Theo dõi:

- Primary/standby role bằng `pg_is_in_recovery()`.
- `pg_stat_replication` và `pg_stat_wal_receiver`.
- Sent/write/flush/replay LSN và lag.
- WAL generation rate và `pg_wal` disk usage.
- Replication slot retained WAL.
- Checkpoint, I/O, CPU, memory và connection saturation.
- Recovery conflicts trên standby.
- Synchronous wait/commit latency.

### 22.3. Patroni metrics và API

Thu thập thông tin từ Patroni REST API/metrics endpoint theo version và exporter được dùng:

- Member role/state.
- Leader lock/leader name.
- HA loop duration và failures.
- DCS access errors/latency.
- PostgreSQL process state.
- Replica lag/candidate eligibility.
- Synchronous mode state.
- Pending restart/config changes.
- REST API request failures.

Tên metric cụ thể phụ thuộc Patroni release/exporter. Không hard-code metric names từ một phiên bản khác mà chưa xác nhận.

### 22.4. DCS metrics

Với etcd:

- Quorum/member health.
- Raft leader changes.
- Proposal latency/failures.
- Disk fsync/backend commit latency.
- Database size/quota.
- Peer RTT/traffic.

Với Consul:

- Server quorum/leader.
- Raft apply/commit latency.
- Session expiration/lock behavior.
- ACL/TLS errors.
- Agent/server health.

Với ZooKeeper:

- Ensemble quorum and leader/follower.
- Request latency/queue.
- Session expiration.
- Transaction log/snapshot storage.

Với Kubernetes:

- API server availability/latency.
- Request throttling/errors.
- Service account authorization failures.
- Control-plane etcd health.

### 22.5. Routing metrics

Monitor HAProxy backend state, active sessions, health check failures, queue length và connection errors. Kiểm tra write endpoint chỉ có một backend healthy tại một thời điểm.

### 22.6. Backup metrics

Theo dõi:

- Last successful base backup.
- WAL archive success/lag.
- Backup verification/restore test age.
- Repository capacity.
- Retention/immutability status.
- PITR target coverage.

### 22.7. Alert severity

| Mức | Ví dụ |
| --- | --- |
| Critical | Không có leader writable, split-brain suspicion, DCS mất quorum, `pg_wal` gần đầy. |
| High | Synchronous standby unavailable, replica lag vượt RPO, backup/WAL archive failure kéo dài. |
| Medium | Một DCS member down nhưng còn quorum, replica reconnect, HA loop chậm. |
| Low | Certificate sắp hết hạn, planned restart pending, backup/restore drill sắp đến hạn. |

Ngưỡng cụ thể phải dựa vào RPO/RTO, workload và backend baseline.

### 22.8. Log correlation

Đồng bộ clock trên database nodes, DCS members, proxies và orchestration hosts. Dùng cluster scope, node name, timeline, LSN, leader changes và incident ID để liên kết logs.

### 22.9. Alert fatigue

Không alert mọi lần replica reconnect ngắn nếu đó là behavior bình thường. Alert phải phản ánh impact: không còn quorum, mất leader, lag vượt SLA, WAL retention tăng hoặc app write endpoint không có backend.

### 22.10. Dashboard tối thiểu

Một dashboard vận hành nên có:

- Sơ đồ topology hiện tại và leader.
- Trạng thái DCS quorum.
- PostgreSQL roles và replication state.
- Lag theo bytes/time từng replica.
- WAL slot/archive retention.
- HAProxy primary/read backends.
- Backup/WAL archive freshness.
- RPO/RTO thực tế từ restore/failover drills.

## 23. Failure scenarios và cách xử lý

### 23.1. PostgreSQL primary crash

Patroni phát hiện PostgreSQL không còn healthy, DCS/HA policy quyết định leader ownership. Nếu candidate đủ điều kiện, một replica được promote. Xác minh fencing, WAL lag, new timeline và routing.

### 23.2. Host primary mất điện

Node không còn renew lock. Khi lease hết hạn, một replica có thể được promote theo policy. Sau khi host trở lại, không start PostgreSQL cũ read-write; rejoin bằng rewind/rebuild.

### 23.3. Primary bị network partition khỏi DCS nhưng vẫn nhận client

Đây là tình huống nguy hiểm. Patroni phải fail closed/demote hoặc dùng failsafe policy được thiết kế rõ. Nếu một node khác được promote trong khi old primary vẫn nhận writes, split-brain có thể xảy ra. Cần watchdog/fencing và test partition.

### 23.4. DCS mất một member

Nếu quorum còn, cluster có thể tiếp tục. Khôi phục member lỗi và kiểm tra raft/ensemble health; không chờ tới khi mất quorum.

### 23.5. DCS mất quorum

Không có authority để cấp leader ownership mới. Giữ single-writer invariant, khôi phục quorum backend, kiểm tra leader state và PostgreSQL roles trước khi mở failover.

### 23.6. DCS leader thay đổi

DCS consensus leader election có thể xảy ra mà không có PostgreSQL primary change. Monitor hai loại leader riêng: DCS consensus leader và Patroni/PostgreSQL leader. Chúng là hai khái niệm khác nhau.

### 23.7. Patroni agent chết nhưng PostgreSQL còn chạy

PostgreSQL process có thể tiếp tục hoạt động trong một khoảng thời gian, nhưng node không còn được quản lý bởi HA loop. Watchdog/fencing policy cần xử lý trường hợp này. Không kill/restart tùy tiện nếu chưa biết node có leader lock hợp lệ hay không.

### 23.8. Replica lag quá lớn

Kiểm tra network, WAL sender, disk replay throughput, slot retention và recovery conflicts. Nếu vượt `maximum_lag_on_failover`, node có thể không đủ điều kiện candidate. Khắc phục lag hoặc reinitialize theo policy.

### 23.9. Replica mất WAL segment

Nếu segment không còn ở primary và archive không có, replica không thể tiếp tục từ vị trí hiện tại. Reinitialize từ base backup mới.

### 23.10. REST API unavailable

HAProxy health checks hoặc monitoring có thể đánh dấu node down dù PostgreSQL còn chạy. Kiểm tra Patroni process, listen/connect address, firewall, TLS, authentication và DCS. Không suy ra database đã chết chỉ từ HTTP failure.

### 23.11. HAProxy vẫn route tới old primary

Kiểm tra endpoint health check, port REST API, status code expectation, server check interval và session shutdown. Xác minh old primary đã bị fence; không chỉ dựa vào proxy state.

### 23.12. Synchronous commit bị block

Kiểm tra `synchronous_standby_names`, `sync_state`, standby network/storage latency và synchronous mode strict policy. Quyết định chờ, khôi phục standby hoặc tạm thay đổi durability policy theo incident authorization.

### 23.13. DCS disk full

DCS có thể từ chối writes hoặc không thể commit proposals. Kiểm tra quota/backend size, compaction/defragmentation procedure, disk free space và logs. Không xóa Patroni keys tùy tiện để giải phóng dung lượng.

### 23.14. Certificate hết hạn

DCS, Patroni REST API hoặc replication connections có thể fail đồng loạt. Kiểm tra expiry, trust chain, SAN/hostname và clock. Rollout trust/certificates theo thứ tự và xác minh mọi connection.

### 23.15. DCS restore từ snapshot cũ

Snapshot cũ có thể chứa leader metadata/leases không còn đúng với PostgreSQL timelines hiện tại. Giữ cluster cô lập, reconcile DCS state với database nodes và dùng recovery procedure chính thức trước khi cho Patroni agents tự điều phối.

### 23.16. Restore database nhưng DCS trỏ node khác

Đây là control-plane/data-plane mismatch. Xác định source of truth, fence writers, sửa topology bằng runbook và không để hai nodes cùng nghĩ là primary.

### 23.17. Manual pg_ctl promote ngoài Patroni

Promote PostgreSQL trực tiếp khi Patroni vẫn quản lý node có thể làm DCS role state không khớp. Thực hiện promotion qua Patroni/patronictl/HA manager theo quy trình. Nếu node đã bị promote ngoài quản lý, cô lập và reconcile ngay.

### 23.18. Pod bị reschedule

Kubernetes có thể restart Pod hoặc attach volume trên node khác. Xác minh volume identity, Patroni config, DCS member state và PostgreSQL role. Không cho Pod cũ và Pod mới cùng mount/write cùng PGDATA.

### 23.19. Primary restart trong khi DCS outage

Node có thể không khởi động/không lấy được leader ownership. Đừng bypass Patroni bằng cách start PostgreSQL thủ công để nhận writes. Khôi phục DCS/ownership hoặc dùng emergency runbook có fencing.

### 23.20. Toàn bộ region mất

Đánh giá DCS quorum còn ở đâu, standby DR có WAL tới đâu, backup/WAL archive sẵn không, và ai có authority promote. Fencing region cũ nếu nó có thể trở lại. Định tuyến clients tới DR sau khi promotion và business validation.

## 24. Lab 1: dựng Patroni cluster với etcd trong môi trường disposable

Lab này mô tả một topology ba PostgreSQL nodes và ba etcd members. Dùng VM/container lab riêng, không triển khai trên production.

### 24.1. Sơ đồ

```text
PostgreSQL/Patroni:
  pg-a 10.20.0.11:5432 / REST 8008
  pg-b 10.20.0.12:5432 / REST 8008
  pg-c 10.20.0.13:5432 / REST 8008

etcd:
  etcd-a 10.20.0.21:2379
  etcd-b 10.20.0.22:2379
  etcd-c 10.20.0.23:2379

Application:
  HAProxy :5000 (writes)
  HAProxy :5001 (reads)
```

### 24.2. Chuẩn bị DCS

Khởi tạo etcd cluster ba members theo etcd documentation. Cấu hình peer/client URLs, unique member names, data directories riêng, TLS/authentication và firewall. Xác nhận quorum và health trước khi chạy Patroni.

### 24.3. Cài PostgreSQL và Patroni

Trên mỗi PostgreSQL node:

- Cài cùng PostgreSQL major.
- Cài Patroni version đã chọn.
- Tạo OS user và data directory.
- Cấu hình PostgreSQL binaries/data paths.
- Cấu hình network/firewall cho replication và REST API.
- Chuẩn bị secret files.

### 24.4. Viết config node-specific

Tạo local config riêng cho từng node. Cùng scope/namespace/DCS cluster; khác name, listen/connect addresses và data_dir. Dùng ví dụ ở phần configuration làm mẫu, bổ sung DCS TLS credentials và PostgreSQL HBA rules.

### 24.5. Bootstrap một node

Start Patroni trên node được chọn làm bootstrap candidate. Theo dõi logs, DCS state và PostgreSQL initdb. Xác nhận node giữ leader lock và PostgreSQL chạy read-write.

### 24.6. Join hai replicas

Start Patroni trên hai nodes còn lại. Chúng phải phát hiện cluster đã tồn tại, clone từ leader bằng configured method và start standby. Xác nhận WAL receiver và replication state.

### 24.7. Kiểm tra cluster

```bash
patronictl -c /etc/patroni/patroni.yml list
patronictl -c /etc/patroni/patroni.yml show-config
```

Kỳ vọng một leader và hai replicas. Kiểm tra trực tiếp trên PostgreSQL:

```sql
SELECT pg_is_in_recovery();
```

Leader trả false; replicas trả true.

### 24.8. Tạo test table

Trên leader:

```sql
CREATE TABLE public.patroni_lab (
    id bigint PRIMARY KEY,
    note text NOT NULL
);

INSERT INTO public.patroni_lab
VALUES (1, 'created-on-leader');
```

Đọc trên replicas sau khi replay. Không ghi vào replicas.

### 24.9. Lưu baseline

Ghi lại:

- DCS quorum/member health.
- Leader name và lock state.
- Replica lag.
- WAL generation rate.
- HA loop timing.
- REST API endpoints.
- Application write/read endpoints.

### 24.10. Dọn lab

Stop Patroni/PostgreSQL/etcd lab theo thứ tự đã lập. Chỉ xóa data directories, DCS data và test tables thuộc lab disposable. Không chạy cleanup trên production.

## 25. Lab 2: health checks và HAProxy routing

### 25.1. Kiểm tra REST API trực tiếp

```bash
curl --fail http://10.20.0.11:8008/primary
curl --fail http://10.20.0.12:8008/replica
curl --fail http://10.20.0.13:8008/replica
```

Thay địa chỉ bằng nodes trong lab. Nếu API dùng auth/TLS, thêm credentials/certificates.

### 25.2. Cấu hình HAProxy

Dùng ví dụ primary/read backends ở phần 13. Đặt frontend port riêng và health-check REST API port. Validate HAProxy config bằng công cụ phù hợp trước reload.

### 25.3. Kiểm tra write endpoint

Kết nối tới HAProxy write port:

```bash
psql -h haproxy-lab -p 5000 -U app_user -d appdb
```

Kiểm tra server thực sự được chọn bằng `inet_server_addr()` và `pg_is_in_recovery()`.

### 25.4. Kiểm tra read endpoint

Kết nối read port, chạy SELECT và xác nhận node là standby/recovery. Read pool phải loại nodes không đủ điều kiện theo policy.

### 25.5. Quan sát failover routing

Thực hiện switchover có kế hoạch trong lab. Quan sát HAProxy backend state chuyển từ old leader sang new leader. Kiểm tra client reconnect và session reset behavior.

### 25.6. Giới hạn

Health check thành công không chứng minh old primary đã bị fence. Thử kết nối trực tiếp old primary sau switchover/failover để xác minh fencing/role transition.

## 26. Lab 3: planned switchover

### 26.1. Pre-check

Trước khi switchover:

- Một leader và ít nhất một replica healthy.
- DCS quorum đủ.
- Replica candidate đã bắt kịp hoặc lag nằm trong policy.
- Backup/WAL archive healthy.
- HAProxy/API health checks hoạt động.
- Có rollback/recovery plan.

### 26.2. Thực hiện switchover

Dùng `patronictl switchover` theo cú pháp đúng release. Chọn leader cũ và candidate mới một cách tường minh nếu CLI yêu cầu. Xác nhận prompt và thời điểm maintenance.

### 26.3. Kiểm tra sau switchover

```bash
patronictl -c /etc/patroni/patroni.yml list
```

Xác nhận node mới là leader, node cũ là replica và replication state ổn định. Kiểm tra write endpoint route tới leader mới.

### 26.4. Kiểm tra dữ liệu

So sánh test row/transaction markers trên primary mới và replicas. Kiểm tra application smoke tests và unknown COMMIT handling.

### 26.5. Ghi RTO

Đo thời gian từ khi bắt đầu switchover tới lúc ứng dụng write/read hoạt động bình thường qua endpoint ổn định. Ghi downtime và connection errors.

## 27. Lab 4: failover và rejoin primary cũ

Lab này cần một cluster disposable có ít nhất hai PostgreSQL nodes. Không dùng kill/power-off experiments trên production.

### 27.1. Ghi nhận trạng thái trước failover

Lưu:

- Leader name.
- Replica receive/flush/replay LSN.
- DCS member/leader state.
- Synchronous state.
- Current timeline.
- HAProxy backend health.

### 27.2. Mô phỏng lỗi

Trong môi trường lab, stop primary bằng cách được Patroni quản lý hoặc dùng failure injection có kiểm soát. Quan sát Patroni logs và DCS lock transition.

### 27.3. Xác nhận promotion

Một replica đủ điều kiện được promote theo policy. Kiểm tra `patronictl list`, `pg_is_in_recovery()` và PostgreSQL logs. Chỉ có một leader.

### 27.4. Kiểm tra routing

Kết nối qua write endpoint và xác nhận nó route tới primary mới. Kiểm tra old primary không nhận writes.

### 27.5. Rejoin old primary

Nếu node cũ đã diverge, dùng Patroni reinitialize/pg_rewind theo policy và preconditions. Nếu không thể rewind, clone base backup mới. Đừng start old primary như read-write.

### 27.6. Xác minh cluster ổn định

Kỳ vọng một leader và replica(s) streaming. Kiểm tra timeline, slots, WAL retention, lag và routing.

### 27.7. Ghi kết quả

Ghi detection time, DCS election time, promotion time, client routing time, data loss/uncertainty và rejoin duration. Đây là baseline cho RTO/RPO.

## 28. Lab 5: DCS outage và quorum

### 28.1. Dùng DCS disposable

Chỉ thử trên etcd/Consul/ZooKeeper cluster lab. Xác định rõ member nào có thể stop và còn lại có quorum không.

### 28.2. Mất một member

Stop một DCS member. Xác nhận majority còn lại vẫn có quorum và Patroni agents tiếp tục đọc/renew state theo thiết kế. Khởi động member lại và quan sát catch-up.

### 28.3. Mất quorum

Trong lab, cô lập đủ DCS members để mất majority. Quan sát logs/Patroni behavior. Không tự xóa leader key hoặc promote replica bằng tay.

### 28.4. Khôi phục quorum

Khôi phục network/member state theo backend procedure. Xác nhận DCS quorum trước khi kiểm tra Patroni leader/member records.

### 28.5. So sánh database và DCS health

Trong lúc DCS outage, PostgreSQL process có thể còn chạy. Kiểm tra database health và control-plane health riêng; không coi query success là bằng chứng có thể failover an toàn.

### 28.6. Failsafe mode

Nếu lab bật failsafe_mode, lặp lại scenario và quan sát điều kiện REST API member reachability. Ghi rõ hành vi thực tế của Patroni version; không bật trên production chỉ vì lab có vẻ hoạt động.

## 29. Lab 6: dynamic configuration và restart policy

### 29.1. Xem dynamic config

```bash
patronictl -c /etc/patroni/patroni.yml show-config
```

Ghi lại TTL, loop_wait, retry_timeout, failover lag và PostgreSQL parameters.

### 29.2. Thay một giá trị an toàn trong lab

Dùng `patronictl edit-config` để thay đổi một setting lab đã xác định. Tránh đổi TTL/loop_wait tùy tiện khi chưa hiểu constraints.

### 29.3. Xác minh config đã lưu

Chạy show-config và kiểm tra trên từng node. So sánh dynamic config với local YAML.

### 29.4. Kiểm tra pending restart

Dùng Patroni output hoặc PostgreSQL `pg_settings.pending_restart` để xem parameter có cần restart. Không restart leader ngoài kế hoạch.

### 29.5. Rollback

Khôi phục config đã ghi lại trước đó bằng edit-config. Xác nhận các agents đã nhận giá trị và PostgreSQL runtime state phù hợp.

## 30. Lab 7: quan sát DCS và Patroni API

### 30.1. REST API

Gọi `/health`, `/primary`, `/replica` trên từng node và ghi status code. Xác nhận primary endpoint chỉ thành công trên leader và replica endpoint chỉ thành công trên nodes phù hợp theo version.

### 30.2. DCS state

Dùng công cụ backend chính thức để đọc health/member state. Tránh ghi/sửa keys. Ghi lại revision/term/session/lease metadata ở mức cần thiết.

### 30.3. Correlate state

So sánh:

- Patroni node name/role.
- DCS leader/member state.
- PostgreSQL `pg_is_in_recovery()`.
- `pg_stat_replication`.
- HAProxy backend state.

Mọi lớp phải phản ánh cùng một single-writer topology.

### 30.4. Audit

Thực hiện một dynamic config change và một planned switchover trong lab. Xác nhận logs/audit trail cho biết ai thực hiện, lúc nào và kết quả.

## 31. Những sai lầm thường gặp

### 31.1. Nghĩ streaming replication tự tạo HA

Replication chỉ giữ standby nhận/replay WAL. Nó không tự giải quyết leader election, fencing, client routing, backup và rejoin. Cần orchestration và operational runbooks.

### 31.2. Dùng Patroni mà không có DCS khỏe

Patroni cần DCS để coordinate leader/member/config state. DCS không có quorum có thể làm failover không thể diễn ra an toàn. Monitor DCS như dependency critical.

### 31.3. Coi DCS là nơi lưu database data

DCS chỉ lưu coordination metadata/configuration. Nó không chứa table rows/WAL và không thay PostgreSQL backups.

### 31.4. Đặt tất cả DCS members trên cùng host

Một host failure có thể làm mất quorum. Phân bố members qua failure domains phù hợp, nhưng phải cân nhắc latency và network partitions.

### 31.5. Dùng hai DCS clusters độc lập với cùng Patroni scope

Hai control planes có thể chứa leader states khác nhau. Đảm bảo mọi Patroni agents của một cluster dùng đúng một DCS authority và namespace.

### 31.6. Nhầm DCS leader với PostgreSQL leader

etcd/Consul/ZooKeeper có leader của consensus protocol; Patroni cluster có PostgreSQL primary. Đây là hai loại leader khác nhau.

### 31.7. TTL quá ngắn

Network jitter, CPU pause hoặc DCS latency có thể làm leader không renew kịp, gây demotion/failover không cần thiết. Đo worst-case latency trước khi tuning.

### 31.8. TTL quá dài

Failure detection và promotion có thể chậm, kéo dài RTO. Chọn TTL cùng `loop_wait`/`retry_timeout` theo failure budget.

### 31.9. Tin rằng lease hết hạn tự fence primary cũ

DCS lease không tự dừng PostgreSQL process. Cần Patroni fail-closed behavior, watchdog và/hoặc external fencing.

### 31.10. Không kiểm tra watchdog thật

Chỉ khai báo watchdog config không chứng minh device hoạt động. Kiểm tra permissions, timeout, reset behavior và failure scenarios.

### 31.11. Bootstrap hai lần

Bootstrap lại một scope đã có data/history có thể tạo cluster metadata mới không tương thích. Xác định source of truth trước khi bootstrap/reinitialize.

### 31.12. Nghĩ sửa bootstrap.dcs sẽ đổi config đang chạy

`bootstrap.dcs` chủ yếu seed dynamic configuration ban đầu. Sau khi cluster tồn tại, dùng `patronictl edit-config`/API để đổi dynamic settings.

### 31.13. Copy cùng name/data_dir cho mọi nodes

Member name và data directory phải unique. Trùng identity có thể làm Patroni member state và process management xung đột.

### 31.14. Mở REST API ra public

REST API là control surface và tiết lộ topology. Giới hạn network, bật auth/TLS và audit administrative actions.

### 31.15. Dùng /health làm write routing check

Node healthy có thể là standby. Write pool phải dùng endpoint xác nhận primary/leader theo semantics của Patroni version.

### 31.16. Nghĩ HAProxy health check là fencing

Proxy chỉ ngừng route traffic qua proxy đó. Old primary có thể nhận direct connections hoặc traffic từ proxy khác. Fencing phải xử lý ở database/host/network authority.

### 31.17. Chồng nhiều leader election controllers

Patroni, operator, keepalived và custom scripts cùng quyết định primary có thể đưa cluster vào trạng thái không nhất quán. Chỉ một authority được quyết định database leader.

### 31.18. Không hiểu DCS quorum

Mất một member trong cluster ba nodes khác với mất hai members. Thiết kế và diễn tập cả majority/minority partition.

### 31.19. Tự xóa leader key khi DCS lỗi

Có thể cấp quyền leader mới trong khi primary cũ vẫn nhận writes. Không sửa DCS keys thủ công khi chưa có recovery procedure và fencing.

### 31.20. Bỏ qua candidate lag

Promote replica stale có thể làm mất nhiều committed transactions. Theo dõi LSN/lag và `maximum_lag_on_failover`; không ép candidate vượt policy mà không chấp nhận RPO.

### 31.21. Không cấu hình synchronous policy rõ ràng

Synchronous mode có thể block commits khi standby không available hoặc không mang lại remote durability như mong muốn nếu application dùng local/off. Viết rõ durability/availability policy.

### 31.22. Bật synchronous_mode_strict mà không có runbook

Writes có thể chờ khi không còn synchronous standby. Cần biết ai được quyền thay đổi policy trong incident và cách bật lại sau đó.

### 31.23. Dùng tags như security boundary

`nofailover`, `nosync`, `noloadbalance` là policy hints. Chúng không thay HBA, firewall, RBAC hay fencing.

### 31.24. Đổi DCS endpoint sang DCS rỗng

Patroni agents có thể thấy cluster state mất và cố bootstrap/điều phối sai. Migration phải chuyển đúng state theo backend procedure.

### 31.25. Restore DCS snapshot cũ mà không reconcile

Leader/member metadata có thể không khớp PostgreSQL timeline hiện tại. Cô lập nodes, xác định database source of truth và khôi phục control plane theo runbook.

### 31.26. Nghĩ Kubernetes StatefulSet tự tạo PostgreSQL HA

StatefulSet chỉ quản lý Pod identity/storage lifecycle. Cần Patroni/operator để quản lý database leader election và replication.

### 31.27. Dùng liveness probe thay Patroni role check

Liveness xác định process có cần restart; nó không nói node có phải primary. Dùng readiness/Patroni endpoint đúng mục tiêu.

### 31.28. Reinitialize nhầm node

Reinit có thể phá hủy data directory replica. Xác minh member name, upstream, backup và maintenance approval trước.

### 31.29. Nâng cấp tất cả nodes cùng lúc

Rolling upgrade giữ redundancy. Restart đồng thời mọi replicas/primary có thể làm mất toàn bộ HA và gây outage.

### 31.30. Chỉ test failover, không test rejoin

Một failover thành công chưa chứng minh old primary có thể rewind/rebuild và topology trở lại healthy. Diễn tập cả failover, fencing, routing và rejoin.

### 31.31. Quên backup vì đã có ba replicas

DELETE/DROP nhầm được replicate tới mọi nodes. Cần base backups, WAL archive, PITR và immutable copies.

### 31.32. Không kiểm tra unknown COMMIT outcome

Client mất connection trong COMMIT có thể không biết transaction đã commit hay chưa. Retry mù có thể tạo duplicate operations; dùng idempotency key và reconciliation.

### 31.33. Monitor PostgreSQL nhưng không monitor DCS

Database có thể trả query trong khi DCS mất quorum. HA failover không còn được đảm bảo. Alert riêng cho DCS.

### 31.34. Không monitor WAL slot retention

Replica mất kết nối nhưng slot giữ WAL có thể làm đầy disk primary. Theo dõi inactive slots, retained bytes và disk headroom.

### 31.35. Chỉ kiểm tra /primary mà không kiểm tra client path

Endpoint có thể đúng nhưng HAProxy/DNS/pool vẫn route sai. Test qua endpoint ứng dụng và xác minh `inet_server_addr()`/role.

## 32. Bài tập thực hành

Các câu hỏi sau dùng topology lab. Những bài về partition, promotion, DCS restore và watchdog chỉ thực hiện trong môi trường disposable.

### Bài 1. Orchestration

Vì sao PostgreSQL streaming replication chưa đủ để tạo thành một HA cluster hoàn chỉnh?

### Bài 2. Data plane và control plane

Phân biệt data plane, control plane và client routing plane trong kiến trúc Patroni.

### Bài 3. Patroni agent

Liệt kê ít nhất năm nhiệm vụ của Patroni agent trên mỗi database node.

### Bài 4. DCS

DCS lưu những loại metadata nào? DCS có lưu PostgreSQL table data không?

### Bài 5. Quorum

Một DCS có ba voting members. Cần bao nhiêu members để đạt majority quorum? Có thể mất bao nhiêu member mà vẫn còn quorum?

### Bài 6. Backend comparison

So sánh etcd, Consul, ZooKeeper và Kubernetes API theo coordination primitive và failure mode.

### Bài 7. Leader lock

Leader lease/TTL có tác dụng gì? Vì sao TTL hết hạn không tự dừng old primary process?

### Bài 8. Timing

Giải thích quan hệ giữa ttl, loop_wait và retry_timeout. Hậu quả khi TTL quá ngắn hoặc quá dài?

### Bài 9. Patroni HA loop

Liệt kê các bước chính của HA loop.

### Bài 10. Patroni config

Phân biệt scope, namespace, name, restapi.listen, postgresql.listen và connect_address.

### Bài 11. Bootstrap

`bootstrap.dcs` được dùng khi nào? Vì sao sửa nó sau khi cluster đã tạo không tự động cập nhật dynamic config?

### Bài 12. Dynamic config

Dùng công cụ nào để xem và sửa dynamic config? Vì sao không nên sửa DCS keys trực tiếp?

### Bài 13. REST API

Phân biệt `/health`, `/primary` và `/replica` trong routing.

### Bài 14. HAProxy

Vì sao HAProxy kiểm tra Patroni REST API trên port 8008 nhưng chuyển PostgreSQL traffic tới port 5432?

### Bài 15. Read routing

Một standby có thể trả dữ liệu stale. Nêu hai cách xử lý read-after-write requirement.

### Bài 16. Synchronous mode

Phân biệt `synchronous_mode` và `synchronous_mode_strict` ở mức policy tổng quát.

### Bài 17. Candidate eligibility

`maximum_lag_on_failover` có vai trò gì? Vì sao nó không phải cam kết RPO tuyệt đối?

### Bài 18. Failover vs switchover

Phân biệt hai thao tác theo primary availability, WAL synchronization và RPO.

### Bài 19. DCS outage

Vì sao DCS mất quorum có thể ngăn automatic failover dù PostgreSQL replicas vẫn chạy?

### Bài 20. failsafe_mode

Mục tiêu của failsafe_mode là gì? Vì sao phải test theo Patroni version và network topology?

### Bài 21. Fencing

Nêu ba phương pháp fencing và giải thích vì sao DNS switch không đủ.

### Bài 22. Watchdog

Watchdog hỗ trợ gì cho leader safety? Nêu một điều kiện cần kiểm tra ngoài YAML config.

### Bài 23. Kubernetes

Phân biệt vai trò của StatefulSet, Kubernetes Service, Patroni và PostgreSQL operator.

### Bài 24. Backup

Vì sao etcd snapshot không thay PostgreSQL base backup? Ngược lại, base backup có lưu DCS leader state không?

### Bài 25. DCS restore

Tại sao không thể restore một DCS snapshot cũ rồi bật tất cả Patroni agents ngay lập tức?

### Bài 26. Security

Nêu các endpoints/traffic cần bảo vệ trong Patroni + DCS topology.

### Bài 27. Monitoring

Liệt kê ít nhất tám signals cần có trên dashboard HA.

### Bài 28. Split-brain

Mô tả một network partition có thể tạo hai primary như thế nào và cách ngăn chặn.

### Bài 29. Rejoin

Sau failover, vì sao old primary cần pg_rewind hoặc base backup mới trước khi quay lại làm standby?

### Bài 30. Thiết kế tổng hợp

Thiết kế một PostgreSQL HA cluster ba nodes bằng Patroni, DCS quorum, HAProxy, backup và monitoring. Nêu cách xử lý primary crash, DCS outage, network partition và region failure.

## 33. Gợi ý lời giải bài tập

### Đáp án 1. Orchestration

Replication chỉ truyền WAL và giữ standby gần primary. HA còn cần phát hiện lỗi, leader ownership/election, fencing, candidate selection, promotion, routing, rejoin và backup/recovery.

### Đáp án 2. Data plane và control plane

- Data plane: PostgreSQL processes, data files, WAL streaming và client SQL.
- Control plane: Patroni agents, DCS, leader lease, member records và failover policy.
- Client routing plane: HAProxy/proxy/VIP/DNS/service discovery đưa writes tới leader và reads tới replicas phù hợp.

### Đáp án 3. Patroni agent

Ví dụ: đọc config, monitor PostgreSQL, đọc/renew leader lock, publish member state, điều khiển start/stop/promote/follow, tạo replica, cung cấp REST API và phối hợp synchronous mode.

### Đáp án 4. DCS

DCS lưu dynamic config, leader key/lease, member records/heartbeat, failover metadata và synchronous state theo backend/version. Nó không lưu PostgreSQL table data, indexes hay WAL.

### Đáp án 5. Quorum

Ba voting members cần majority 2. Có thể mất một member và vẫn còn quorum; mất hai thì không còn quorum.

### Đáp án 6. Backend comparison

- etcd: Raft KV, leases, watches; mất majority thì không commit writes.
- Consul: Raft server quorum, KV/sessions/locks; chú ý session/ACL/TLS.
- ZooKeeper: Zab ensemble, ephemeral znodes/watches; chú ý session expiration và ensemble quorum.
- Kubernetes API: API resources/leases backed by control-plane etcd; chú ý API availability/RBAC/throttling.

### Đáp án 7. Leader lock

Lease/TTL cho biết node nào đang giữ ownership và cần renew định kỳ. Lease hết hạn chỉ thay đổi control-plane state; nó không tự dừng process/socket của old primary. Cần Patroni demotion/watchdog/external fencing.

### Đáp án 8. Timing

`loop_wait` là chu kỳ HA loop; `retry_timeout` giới hạn retry khi thao tác gặp lỗi; `ttl` là thời gian ownership/lease. TTL quá ngắn gây failover giả do jitter; TTL quá dài kéo dài detection/RTO. Chọn theo latency/failure budget và constraints của release.

### Đáp án 9. Patroni HA loop

Đọc PostgreSQL local state, đọc DCS/member/leader state, xác định role, renew leader lock nếu là leader, kiểm tra replicas, áp dụng failover/sync policy, thực hiện start/stop/promote/follow/reinit và publish heartbeat/member state.

### Đáp án 10. Patroni config

`scope` định danh cluster; `namespace` là DCS prefix; `name` là member identity; `restapi.listen` là REST API bind address; `postgresql.listen` là PostgreSQL bind address; connect_address là endpoint các nodes khác dùng để kết nối.

### Đáp án 11. Bootstrap

`bootstrap.dcs` seed dynamic config lúc cluster khởi tạo lần đầu. Sau khi cluster đã có state, dynamic config nằm trong DCS; sửa local bootstrap block không tự cập nhật state hiện hành. Dùng edit-config/API.

### Đáp án 12. Dynamic config

Dùng `patronictl show-config` để xem và `patronictl edit-config` để sửa. Không sửa DCS keys trực tiếp vì có thể phá leader ownership, member state hoặc config schema.

### Đáp án 13. REST API

`/health` là health cơ bản; `/primary` xác nhận node primary/leader theo semantics của version; `/replica` xác nhận replica đủ điều kiện. Write routing phải dùng primary endpoint, read routing dùng replica endpoint/lag policy.

### Đáp án 14. HAProxy

PostgreSQL TCP traffic chạy trên port database (ví dụ 5432). HAProxy dùng HTTP health check gọi Patroni REST API trên port riêng (ví dụ 8008) để xác định role trước khi chọn backend.

### Đáp án 15. Read routing

Có thể đọc lại từ primary; hoặc dùng synchronous replication với `synchronous_commit=remote_apply` cho transaction cần read-after-write; hoặc chờ standby replay tới LSN commit.

### Đáp án 16. Synchronous mode

`synchronous_mode` bật Patroni quản lý synchronous standby selection. `synchronous_mode_strict` giữ yêu cầu synchronous acknowledgement khi không có standby phù hợp, có thể làm writes chờ và giảm availability.

### Đáp án 17. Candidate eligibility

`maximum_lag_on_failover` loại replicas quá stale khỏi candidate set theo WAL lag. Nó không phải RPO tuyệt đối vì WAL generation, timing, race, timeline, sync policy và candidate selection tại thời điểm failure vẫn ảnh hưởng.

### Đáp án 18. Failover vs switchover

Switchover có kế hoạch, primary cũ phối hợp và có thể chờ standby bắt kịp. Failover xảy ra khi primary không còn available; WAL cuối có thể không biết, nên RPO phụ thuộc replication mode và replica được chọn.

### Đáp án 19. DCS outage

Không có quorum thì DCS không commit leader ownership changes. Replicas không có authority thống nhất để claim leadership; tự promote có thể tạo split-brain.

### Đáp án 20. failsafe_mode

Failsafe mode có thể cho leader tiếp tục trong một số DCS outage nếu điều kiện liên lạc/member checks theo Patroni release được đáp ứng. Network partitions khác nhau tạo kết quả khác nhau; cần đọc docs và test.

### Đáp án 21. Fencing

Ví dụ power off old host, revoke storage write access, network isolation khỏi application clients hoặc watchdog reset. DNS switch chỉ đổi routing thông thường; clients có thể còn kết nối trực tiếp old primary.

### Đáp án 22. Watchdog

Watchdog buộc node reset nếu không được keep-alive trong safety window, giảm nguy cơ old leader tiếp tục chạy sau mất ownership. Kiểm tra device/driver, permissions, timeout và reset behavior thật.

### Đáp án 23. Kubernetes

StatefulSet quản lý Pod identity/storage; Service route traffic; Patroni quản lý PostgreSQL roles/leader/replication; operator quản lý desired state và lifecycle của database cluster. Cần tránh hai controllers cùng điều khiển primary.

### Đáp án 24. Backup

etcd snapshot chỉ lưu control-plane metadata, không có PostgreSQL table data/WAL. PostgreSQL base backup lưu data files, không tự lưu DCS leader lock/config state.

### Đáp án 25. DCS restore

Snapshot cũ có thể chứa leader/member state không khớp PostgreSQL timeline/roles hiện tại. Phải fence writers, reconcile source of truth và xác minh metadata trước khi bật agents để tránh hai leaders.

### Đáp án 26. Security

Bảo vệ PostgreSQL client/replication ports, Patroni REST API, DCS client/peer ports, backup repository, monitoring/admin endpoints, credentials, certificates và Kubernetes API/RBAC.

### Đáp án 27. Monitoring

Ví dụ: Patroni leader/member state, DCS quorum, DCS proposal latency, PostgreSQL role, replication LSN lag, slot retained WAL, WAL archive status, HAProxy backend state, disk free, synchronous waits, recovery conflicts và backup freshness.

### Đáp án 28. Split-brain

Primary A bị partition khỏi DCS nhưng vẫn nhận writes; replica B mất liên lạc với A nhưng còn DCS quorum và được promote. Nếu A chưa bị fence, cả A và B nhận writes. Ngăn bằng quorum/lease semantics, Patroni fail-closed, watchdog/external fencing và single-writer routing.

### Đáp án 29. Rejoin

Old primary có thể chứa WAL history diverged sau promotion. `pg_rewind` hoặc base backup mới đưa nó về history của primary hiện tại trước khi start như standby; không thể merge hai histories bằng cách start process cũ.

### Đáp án 30. Thiết kế tổng hợp

Một thiết kế khả thi:

1. Ba PostgreSQL nodes cùng major, mỗi node có Patroni agent.
2. DCS etcd ba voting members ở failure domains phù hợp; bật TLS/auth và monitor quorum.
3. Một leader và hai replicas physical streaming; chọn synchronous mode cho replica gần primary nếu RPO thấp yêu cầu.
4. Replica DR ở region khác có thể asynchronous để tránh WAN latency trên mọi commits; chấp nhận RPO phù hợp và WAL archive liên tục.
5. HAProxy write backend kiểm tra `/primary`; read backend kiểm tra `/replica` và lag threshold.
6. Base backup/WAL archive độc lập, immutable copies và restore drills.
7. Monitoring PostgreSQL, Patroni, DCS, HAProxy, slots, archive, disk và backup freshness.
8. Primary crash: xác nhận incident, DCS quorum, candidate lag, fencing, promotion và route traffic.
9. DCS outage: giữ single-writer, khôi phục quorum; chỉ dùng failsafe nếu policy đã được test.
10. Network partition: dùng watchdog/external fencing và không promote khi không có authority.
11. Region failure: kiểm tra DR control-plane quorum, WAL/backup, fence region cũ, promote đúng standby, update routing và validate business data.

## 34. Checklist thiết kế và vận hành Patroni

### 34.1. Cluster topology

1. Mỗi PostgreSQL node có Patroni agent và identity riêng không?
2. PostgreSQL nodes cùng major version không?
3. Data directories/tablespaces/storage failure domains có độc lập không?
4. Scope/namespace có unique cho từng cluster không?
5. Có đúng một authority quyết định PostgreSQL leader không?

### 34.2. DCS

6. DCS backend được Patroni version hỗ trợ không?
7. Quorum members phân bố đúng failure domains không?
8. Client/peer TLS và authentication có bật không?
9. DCS ACL/RBAC chỉ cấp quyền cần thiết không?
10. DCS metrics, snapshot/restore và upgrade runbooks có không?
11. Có alert cho mất member/quorum/proposal latency/disk quota không?

### 34.3. Patroni

12. Local config và dynamic config đã phân biệt chưa?
13. Bootstrap chỉ thực hiện trên cluster mới chưa có state chưa?
14. TTL/loop_wait/retry_timeout đã tuning theo measured latency chưa?
15. maximum_lag_on_failover/check_timeline có policy rõ không?
16. failsafe_mode/watchdog có được hiểu và test không?
17. REST API authentication/TLS/firewall có phù hợp không?
18. Tags có phản ánh failover/sync/read routing policy không?

### 34.4. PostgreSQL

19. Base backup/replication slots/WAL retention đã cấu hình chưa?
20. Synchronous mode và synchronous_commit có durability policy rõ không?
21. Replication lag và recovery conflicts có được monitor không?
22. pg_rewind preconditions có sẵn nếu dùng không?
23. Backup/WAL archive độc lập có hoạt động không?

### 34.5. Routing và application

24. Write endpoint chỉ route tới Patroni primary endpoint không?
25. Read endpoint chỉ route tới replica đủ điều kiện không?
26. Lag threshold và stale read semantics có được định nghĩa không?
27. Connection pools reconnect sau failover không?
28. Application có idempotency cho unknown COMMIT outcomes không?
29. Routing có được test end-to-end, không chỉ health check không?

### 34.6. Operations

30. Có runbook bootstrap, failover, switchover, DCS outage và rejoin không?
31. Có rolling upgrade cho PostgreSQL/Patroni/DCS không?
32. Có audit cho manual failover và dynamic config changes không?
33. Có fencing test và split-brain exercise không?
34. Có restore/PITR/DR drill định kỳ không?
35. RTO/RPO thực tế đã được đo và so với SLA chưa?

## 35. Runbook tổng quát khi HA cluster bất thường

### Bước 1. Xác định phạm vi sự cố

Kiểm tra PostgreSQL, Patroni, DCS, network, proxy và backup. Phân biệt database process failure với control-plane failure hoặc routing failure.

### Bước 2. Xác định leader hiện tại

So sánh:

- `patronictl list`.
- DCS leader/member state.
- `pg_is_in_recovery()` trên từng node.
- `pg_stat_replication`.
- REST API `/primary`.

Nếu các lớp không thống nhất, cô lập writes và điều tra trước khi promote.

### Bước 3. Xác nhận quorum

Kiểm tra DCS voting members, leader và ability to commit. Không xóa keys hoặc bootstrap lại khi quorum chưa được hiểu.

### Bước 4. Đánh giá fencing

Xác định old primary có thể còn nhận writes không. Thực hiện fencing đáng tin cậy trước khi chuyển leader ownership.

### Bước 5. Chọn candidate

So sánh LSN/lag/timeline/synchronous state và policy. Không ép promote một node không đủ điều kiện nếu chưa chấp nhận data loss.

### Bước 6. Thực hiện promotion qua Patroni

Dùng `patronictl` hoặc API theo runbook/version. Chỉ một node được promote. Không dùng `pg_ctl promote` ngoài Patroni khi cluster còn được quản lý.

### Bước 7. Chuyển traffic

Xác nhận HAProxy/Service/DNS cập nhật, connection pools reconnect và writes đi tới primary mới. Test từ ứng dụng.

### Bước 8. Reconcile data

Kiểm tra transaction outcomes không rõ, idempotency keys, external events và business invariants. Đánh giá RPO thực tế.

### Bước 9. Rejoin nodes

Repoint replicas theo timeline mới. Rewind/rebuild old primary. Xác nhận toàn bộ nodes về đúng roles.

### Bước 10. Restore redundancy

Xác nhận DCS quorum, replica health, backup/WAL archive và monitoring. Đừng đóng incident khi chỉ có một primary hoạt động mà chưa khôi phục redundancy.

### Bước 11. Ghi incident report

Lưu timeline, node roles, DCS events, LSNs, RTO/RPO, data loss/uncertainty, fencing evidence và corrective actions.

## 36. Tổng kết

**Patroni điều phối PostgreSQL HA; DCS cung cấp coordination state/quorum; PostgreSQL streaming replication truyền WAL; proxy/service discovery đưa clients tới node đúng role; fencing ngăn old primary tiếp tục ghi.** Những thành phần này phải được thiết kế và vận hành như một hệ thống thống nhất.

Các nguyên tắc cốt lõi:

- PostgreSQL replication không tự bầu leader hoặc cập nhật client routing.
- Patroni agent chạy trên từng database node và quản lý PostgreSQL lifecycle/HA loop.
- DCS lưu leader/member/config metadata, không lưu database contents.
- Quorum giúp các agents thống nhất ownership; mất quorum có thể ngăn failover an toàn.
- Leader TTL/lease cần renewal; lease expiration không tự tắt old primary.
- Watchdog/external fencing bảo vệ single-writer invariant.
- `bootstrap.dcs` seed config ban đầu; dynamic config sau đó được quản lý qua DCS/patronictl/API.
- REST API cung cấp role/health endpoints; load balancer phải kiểm tra đúng endpoint cho write/read routing.
- Synchronous mode là durability/availability trade-off; strict policy có thể block writes.
- Automatic failover cần candidate eligibility, WAL lag/timeline policy và DCS authority.
- DCS outage, network partition và Kubernetes API outage cần runbooks riêng.
- Backup database và backup DCS là hai việc khác nhau; cả hai cần restore/reconciliation plan.
- Kubernetes StatefulSet/Service không thay Patroni leader election; operator và Patroni không được tranh quyền điều khiển.
- Monitor PostgreSQL, Patroni, DCS, routing, backup và fencing; diễn tập failover/rejoin end-to-end.

Nguyên tắc thực hành:

> **Một HA cluster chỉ an toàn khi ownership được phối hợp qua quorum, old primary được fence, clients route tới leader hợp lệ và mọi node có thể rejoin theo runbook đã kiểm thử.**

## 37. Tài liệu tham khảo

Tài liệu chính thức; chọn đúng version Patroni/PostgreSQL/DCS đang vận hành:

- [Patroni Documentation](https://patroni.readthedocs.io/en/latest/): architecture, configuration, DCS, HA loop, REST API và operations.
- [Patroni Configuration](https://patroni.readthedocs.io/en/latest/yaml_configuration.html): local/dynamic config, bootstrap, PostgreSQL và tags.
- [Patroni Dynamic Configuration](https://patroni.readthedocs.io/en/latest/dynamic_configuration.html): DCS-backed cluster settings và configuration changes.
- [Patroni REST API](https://patroni.readthedocs.io/en/latest/rest_api.html): health/role endpoints và administrative API.
- [Patroni Replication Modes](https://patroni.readthedocs.io/en/latest/replication_modes.html): asynchronous/synchronous behavior và failover policy.
- [Patroni DCS](https://patroni.readthedocs.io/en/latest/dcs_failsafe_mode.html): DCS behavior và failsafe mode.
- [etcd Documentation](https://etcd.io/docs/): Raft, quorum, leases, TLS, snapshots và operations.
- [Consul Documentation](https://developer.hashicorp.com/consul/docs): KV, sessions, ACL, TLS và server quorum.
- [Apache ZooKeeper Documentation](https://zookeeper.apache.org/doc/current/): ensemble, sessions, znodes, watches và security.
- [Kubernetes Documentation](https://kubernetes.io/docs/): API server, StatefulSets, Services, probes, RBAC và storage.
- [PostgreSQL Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): physical streaming replication và standby operation.
- [PostgreSQL Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION): commit acknowledgement semantics.
- [PostgreSQL pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): rejoin cluster sau timeline divergence.
- [PostgreSQL Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): base backup, WAL archive và recovery.
- [HAProxy Configuration Manual](https://www.haproxy.org/documentation.html): TCP backends và HTTP health checks.
