# Nâng cấp lần lượt, tương thích phiên bản và kế hoạch quay lui

## 1. Vấn đề: nâng cấp NoSQL không chỉ là thay phiên bản phần mềm

Một cụm NoSQL chạy ổn định với sáu node, ba availability zones (AZ) và hàng triệu requests mỗi ngày. Nhóm vận hành muốn nâng từ phiên bản cũ lên phiên bản mới để nhận các sửa lỗi bảo mật và chức năng truy vấn. Có hai cách tiếp cận:

```text
Không an toàn nếu thiếu phương án thay thế:
  Stop all nodes
      |
      v
  Install new version everywhere
      |
      v
  Restart cluster
```

và:

```text
Rolling upgrade có kiểm soát:
  Preflight + backup + compatibility checks
                    |
                    v
       Upgrade one eligible node
                    |
                    v
        Verify health and SLO gates
                    |
                    v
          Move to next node
                    |
                    v
     Finalize cluster-wide features
```

Cách thứ hai có thể giúp dịch vụ tiếp tục hoạt động, nhưng **không tự động bảo đảm zero downtime**. Nếu upgrade sai thứ tự, mất quorum, không còn đủ replica, thay định dạng dữ liệu quá sớm hoặc client không tương thích, cả cụm vẫn có thể ngừng phục vụ dù chỉ một node được khởi động lại tại một thời điểm.

Bài học thuộc chương **Vận hành cụm** của **Database No SQL**, tập trung vào ba năng lực thực tế:

1. Thiết kế **nâng cấp lần lượt** theo cấu trúc cluster và giới hạn availability.
2. Xác nhận **tương thích phiên bản** không chỉ giữa servers mà còn giữa protocol, storage, schema, drivers và hệ tích hợp.
3. Lập **kế hoạch quay lui/khôi phục** dựa trên điểm không thể đảo ngược, backup và dữ liệu phát sinh trong lúc rollout.

Mục tiêu cuối là đưa cluster tới phiên bản mục tiêu **mà vẫn giữ được yêu cầu về tính đúng đắn, tính sẵn sàng, bảo mật và khả năng khôi phục**.

## 2. Phân biệt rolling upgrade, rolling restart, migration và rollback

| Thuật ngữ | Ý nghĩa | Điều cần kiểm tra |
|---|---|---|
| Rolling restart | Khởi động lại các node theo từng đợt, có thể giữ nguyên version | Quorum, replica health, client routing |
| Rolling upgrade | Thay version từng node/nhóm node, chấp nhận giai đoạn mixed-version | Version path, protocol, storage compatibility |
| Canary upgrade | Nâng một node/nhóm nhỏ đại diện rồi theo dõi trước khi mở rộng | Blast radius, workload thực, rollback |
| In-place upgrade | Nâng software trên node/disk hiện có | Rollback/downgrade có thực sự được hỗ trợ không? |
| Blue-green migration | Dựng cluster mới rồi chuyển traffic/dữ liệu | Dual-write/CDC, cutover, consistency và chi phí |
| Logical/data migration | Đổi schema, partition key, index hay dữ liệu | Backfill, verification, forward/backward compatibility |
| Downgrade | Chạy phiên bản thấp hơn trên dữ liệu/metadata đã chạm bản mới | **Có thể bị cấm hoặc mất an toàn** |
| Rollback ứng dụng | Trả app/driver/config về release trước | App cũ có đọc/ghi schema mới không? |
| Restore/failback | Quay về backup/cluster cũ theo một phương án dữ liệu | RPO/RTO, writes phát sinh, reconciliations |
| Roll forward | Vá lỗi và tiếp tục lên release được hỗ trợ thay vì downgrade | Giữ dữ liệu, giới hạn rủi ro tiếp theo |

**Không dùng “rollback” như một hành động chung chung.** Cần nói rõ đang quay lại **phiên bản app**, **binary database**, **feature flag**, **topology**, **schema** hay **toàn trạng thái dữ liệu từ backup**.

### 2.1. Vì sao nâng cấp khác khởi động lại?

Khi cùng một binary restart, node cũ và node mới không nhất thiết có schema/protocol khác. Khi rolling upgrade, cluster có thể chứa **hai phiên bản cùng lúc**, và trường hợp này cần được vendor hỗ trợ trong đúng hướng di chuyển.

### 2.2. Vì sao backout có thể không phải downgrade?

Nếu bản mới đã chuyển on-disk format hoặc feature compatibility level, việc cài lại binary cũ **có thể không khởi động được** hoặc làm sai dữ liệu. Phương án hợp lệ đôi khi là sửa lỗi bằng bản mới, dựng cluster mới từ backup, hoặc failback qua replication/CDC đã được thiết kế trước.

## 3. Một rolling upgrade có những giai đoạn nào?

Mô hình tổng quát:

```text
DISCOVER
  |
  v
PLAN / COMPATIBILITY MATRIX
  |
  v
BACKUP + RESTORE DRILL
  |
  v
PRE-FLIGHT HEALTH GATE
  |
  v
CANARY NODE / CANARY GROUP
  |
  v
MIXED-VERSION WINDOW
  |
  +-- [failure] --> PAUSE / MITIGATE / APPROVED RECOVERY
  |
  v
ROLL THROUGH TOPOLOGY
  |
  v
VERIFY ALL NODES
  |
  v
ENABLE NEW FEATURES / FORMAT (only if planned)
  |
  v
POST-UPGRADE VALIDATION + HANDOFF
```

### 3.1. Chia việc thành các điểm dừng

Mỗi bước phải có điều kiện bắt đầu, bằng chứng kết thúc, một người/chương trình có quyền phê duyệt bước tiếp theo và đường xử lý nếu điều kiện thất bại.

### 3.2. Mixed-version không nên kéo dài không chủ đích

Nhiều cơ sở dữ liệu chỉ hỗ trợ cluster có phiên bản khác nhau **trong cửa sổ nâng cấp tạm thời**. Chạy mixed-version nhiều tuần có thể làm lộ các incompatibilities hoặc vi phạm ma trận support.

### 3.3. Finalization là một pha riêng

Một số sản phẩm trì hoãn bật feature compatibility level, nâng protocol floor, cập nhật schema hoặc dùng storage format mới cho đến sau khi toàn cluster nâng xong. Đây thường là **điểm quan trọng cho rollback**.

## 4. Định nghĩa “không gián đoạn” theo SLO cụ thể

Không nên cam kết “zero downtime” chỉ vì các node được restart lần lượt.

Một SLO ví dụ:

```text
Trong maintenance window:
  Availability of GetOrderById >= 99.9%
  p99 read latency <= 200 ms
  p99 write latency <= 400 ms
  Successful write acknowledgements retain durability policy
  No lost confirmed writes
  No cross-tenant data access
  CDC/search freshness lag <= 2 minutes
```

Giá trị là minh họa, không phải cam kết mặc định của một hệ NoSQL.

### 4.1. Availability có nhiều phạm vi

- HTTP/API availability.
- Database read availability.
- Database write availability.
- Strong/transactional operation availability.
- Search/index availability.
- CDC/analytics availability.
- Quorum/consensus availability.

Một cluster có thể vẫn phục vụ eventual reads nhưng không đáp ứng quorum writes; vì thế không thể báo một cờ `healthy=true` chung thay cho từng operation.

### 4.2. Latency sau restart

Node vừa tham gia lại có thể có cold caches, compaction, index warmup, replica catch-up và connection storms. API không nhất thiết khôi phục p99 ngay khi process báo `READY`.

### 4.3. Correctness là guardrail bắt buộc

Không hạ read/write concern hoặc bỏ conditional checks chỉ để duy trì throughput nếu yêu cầu nghiệp vụ không cho phép. Một con số p99 đẹp nhưng đọc stale trái hợp đồng không phải upgrade thành công.

## 5. Tính số node được phép rời cụm

Giả sử một cụm quorum với \(N\) voters và majority \(Q\):

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1
\]

Ví dụ \(N=5\):

\[
Q=3
\]

Với tất cả voters khỏe, về mặt quorum votes, có thể mất tối đa hai voters và vẫn còn ba. **Nhưng số này không tự là hạn mức node upgrade an toàn**, bởi:

- Mất một node khác do sự cố bất ngờ.
- Data replicas không trùng hoàn toàn với consensus voters.
- Shard leaders tập trung ở một node.
- Replica factor/placement theo zone khác nhau.
- Writes yêu cầu tất cả replicas hoặc một điều kiện cao hơn majority.
- Rebalance/repair đang làm giảm dự phòng.
- Ứng dụng cần headroom để xử lý lưu lượng của node rời đi.

### 5.1. Quorum trong mọi hệ không giống nhau

MongoDB replica-set voting majority khác Cassandra `LOCAL_QUORUM` cho một token range; DynamoDB managed service không để operator chọn từng node để reboot. Không áp cùng công thức lên mọi hệ.

### 5.2. Kiểm tra trước mỗi node

Một nguyên tắc bảo thủ:

```text
Before taking node X offline:
  Required quorum still available if X unavailable?
  All affected shards/ranges retain required replicas?
  At least one unexpected failure margin remains?
  Remaining nodes can handle traffic?
  Recovery path of X is known?
```

### 5.3. Không dùng RF=3 như bằng chứng đủ hai node bất kỳ

Nếu bản sao được đặt không đều hoặc một replica đang stale/down, việc bảo trì một node có thể làm phạm vi dữ liệu nhất định không đạt consistency level. Kiểm tra topology/health **theo partition/shard/range và datacenter**.

## 6. Capacity headroom và bottleneck khi một node rời đi

Một bài tính sơ bộ:

```text
6 nodes, traffic phân phối đều:
  steady CPU per node = 50%
  1 node offline -> traffic chia cho 5 nodes
  approximate CPU per surviving node = 50% × (6/5) = 60%
```

Đây chỉ là ước tính tuyến tính, chưa gồm load skew, cache misses, election, compaction hoặc recovery.

### 6.1. Ví dụ sát ngưỡng

Nếu steady CPU đã 85%, sau khi mất 1/6 capacity:

\[
85\%\times\frac{6}{5}\approx102\%
\]

Trong mô hình giản lược, không còn headroom. Rolling upgrade không được bắt đầu với giả định “nó sẽ tự cân bằng”.

### 6.2. Dung lượng khác CPU

- Network bandwidth có thể nghẽn khi chuyển traffic.
- Disk latency có thể tăng do recovery.
- Connection pools có thể quá tải khi clients reconnect.
- JVM heap/GC của node còn lại có thể tăng do cache miss.
- Leader election có thể tập trung writes tạm thời.
- Cross-AZ traffic có thể tăng và tốn chi phí.

### 6.3. Đo capacity theo SLO

Không chỉ xem average CPU. Cần successful goodput, p99, error/throttle, queue age, per-shard hotspot và replication lag trong mô phỏng mất node.

## 7. Compatibility không chỉ có “server cũ nói chuyện được với server mới”

Ít nhất có tám trục tương thích:

| Trục | Câu hỏi |
|---|---|
| Server-to-server | Hai phiên bản có trao đổi replication/gossip/consensus an toàn? |
| Wire protocol | Encoding/opcodes/feature negotiation có tương thích? |
| Client driver/SDK | Driver Java có hỗ trợ cả server old/new? |
| On-disk format | Binary cũ có đọc được storage đã được bản mới sửa? |
| Cluster metadata | Routing/shard/index/feature flags có bị nâng? |
| Schema/data | App cũ có đọc document mới, types, indexes, tombstones? |
| Security/transport | TLS, cipher suites, auth mechanisms, cert policy còn tương thích? |
| Ecosystem | CDC connector, backup agent, monitoring exporter, search sink hỗ trợ? |

### 7.1. Tương thích hai chiều khác tương thích một chiều

Có thể có tình huống **server mới hiểu dữ liệu cũ** nhưng **server cũ không hiểu dữ liệu do server mới ghi**. Khi đó upgrade là forward-compatible, không có nghĩa downgrade an toàn.

### 7.2. Version matrix phải dựa trên nhà cung cấp

Không suy “chênh một minor version thì chắc chắn rolling được”. Có sản phẩm cho phép nhảy nhiều phiên bản, có sản phẩm yêu cầu qua phiên bản trung gian hoặc điều kiện cụ thể cho mixed-version.

### 7.3. Dòng “compatible” cần scope

Viết:

```text
Server 6.x -> 7.x: supported rolling upgrade
ONLY after intermediate version, all nodes healthy,
and featureCompatibilityVersion remains old until finalization.
```

chỉ là **mẫu diễn đạt**; không khẳng định con số phiên bản này đúng cho sản phẩm cụ thể. Điền ma trận theo tài liệu của **đúng engine, edition, OS và distribution**.

## 8. Lập compatibility matrix trước khi bắt đầu

Một bảng cần hoàn thiện cho cluster thực tế:

| Thành phần | Hiện tại | Mục tiêu | Hỗ trợ phối hợp? | Điều kiện |
|---|---|---|---|---|
| NoSQL server | A.B.C | A.D.E | Phải xác minh | Official supported path |
| Storage format | F1 | F2? | Phải xác minh | Có chuyển format tự động? |
| Java driver | J1 | J2 | Phải xác minh | API/protocol/auth |
| JDK/JVM | 17 | 21? | Phải xác minh | Driver + application support |
| CDC connector | C1 | C2? | Phải xác minh | Log/resume token/schema |
| Backup tool | B1 | B2? | Phải xác minh | Restore into target version |
| Exporter | E1 | E2? | Phải xác minh | Metric names/permissions |
| Security protocol | TLS config | TLS config | Phải xác minh | Cert/ciphers/client |
| OS/kernel/container | Base image X | Y | Phải xác minh | Native dependencies |
| Client application | API v1 | API v2 | Phải xác minh | Old/new schema coexistence |

### 8.1. Nêu nguồn và ngày kiểm tra

Ở tài liệu vận hành thực tế, mỗi dòng quan trọng nên có đường dẫn/tên tài liệu vendor, version và ngày đã kiểm tra. Compatibility có thể thay đổi theo patch release hoặc managed service policy.

### 8.2. Có test thay vì chỉ đọc matrix

Ma trận hỗ trợ là điều kiện cần; thử nghiệm staging với dữ liệu/driver thật vẫn cần để phát hiện ứng dụng đang phụ thuộc behavior cũ hoặc cấu hình không hợp lệ.

### 8.3. Không lạm dụng semver

Một số sản phẩm NoSQL không tuân theo semantic versioning theo cách ứng dụng giả định. Các bước upgrade được vendor hỗ trợ quan trọng hơn suy đoán từ chữ số version.

## 9. Feature compatibility level và các “điểm không quay lại”

Một mô hình quan trọng:

```text
Old binaries + old feature level
             |
             v
Mixed old/new binaries + old feature level
             |
             v
All new binaries + old-compatible behavior
             |
             v
Enable new feature level / new storage format
             |
             v
Potentially cannot return to old binaries
```

### 9.1. Lợi ích của hoãn bật feature

Giảm khác biệt hành vi trong mixed-version phase, giữ đường rollback ở những sản phẩm hỗ trợ.

### 9.2. Không sản phẩm nào có cùng cơ chế

MongoDB có khái niệm Feature Compatibility Version (FCV) theo releases. Hệ khác có cluster feature flags, protocol floors, cluster-state versions, serialization/schema versions hoặc **không có nút tương đương**.

### 9.3. Điểm không đảo ngược cần được đánh dấu

Ví dụ:

```text
Decision point:
  All nodes target version: yes
  24h soak: passed
  Backups: verified
  Clients/connectors: compatible
  Enable new storage feature: approved

After this:
  Binary downgrade may be unsupported
  Recovery may require restore/forward fix
```

### 9.4. Đừng “bật sớm cho đủ tính năng”

Một node bản mới không có nghĩa cluster đã sẵn sàng nhận dữ liệu/metadata mà bản cũ không hiểu. Bật tính năng mới giữa mixed-version window có thể chặn rollback hoặc làm node cũ crash.

## 10. On-disk format và metadata khó quay lui

Cơ sở dữ liệu có thể thay đổi:

- SSTable/segment/storage file format.
- WAL/oplog/commitlog encoding.
- Index format và compaction metadata.
- Catalog/index definitions.
- Cluster membership metadata.
- Encryption-at-rest metadata và key identifiers.
- Feature flags hoặc schema version.
- Snapshot/backup manifest.
- Checksums/compression algorithms.

### 10.1. Vì sao chỉ thay binary cũ là nguy hiểm?

Binary cũ có thể không nhận diện file header hoặc metadata mới. Khởi động nó trên disk đã ghi bởi bản mới có thể fail hoặc đi vào trạng thái unsupported.

### 10.2. Backup được tạo trước upgrade cũng có giới hạn

Một backup của bản cũ có thể được restore lên bản mới theo các bước hỗ trợ, nhưng một backup do bản mới tạo không mặc nhiên restore được xuống bản cũ.

### 10.3. Chú ý data mutations sau cutover

Ngay cả khi có thể chạy lại binary cũ, dữ liệu phát sinh trong lúc bản mới hoạt động có thể không tương thích schema/app version cũ. Binary rollback và **data rollback** là hai vấn đề khác.

### 10.4. Quy tắc vận hành

**Không thử downgrade trên data directory production chỉ dựa vào suy đoán.** Chỉ làm khi vendor hỗ trợ rõ, điều kiện còn nguyên và runbook đã được thử nghiệm.

## 11. Wire protocol, API và phiên bản client Java

Java application có thể dùng:

- MongoDB synchronous/reactive Java Driver.
- DataStax/Apache Cassandra Java Driver CQL.
- AWS SDK DynamoDB client.
- Elasticsearch/OpenSearch Java client.
- Redis clients như Lettuce/Jedis.
- Neo4j Java Driver.
- Couchbase Java SDK.
- Cosmos DB Java SDK.

### 11.1. Driver phải hỗ trợ cả hai trạng thái

Trong rolling upgrade, Java clients có thể kết nối node old và new theo routing/replication. Driver cần được thử với:

```text
all-old
mixed-version
all-new
failover during mixed-version
```

### 11.2. Protocol negotiation

Server có thể thay wire protocol hoặc command capabilities. Driver mới có thể dùng features mà old server không hiểu; driver cũ có thể không hiểu response type của server mới.

### 11.3. Không nâng mọi thứ cùng lúc nếu có thể tách

Một trình tự thường dễ cô lập lỗi hơn:

1. Nâng client/driver tới version hỗ trợ cả old/new.
2. Deploy application và test dưới old servers.
3. Nâng server từng đợt.
4. Bật features mới sau khi cluster ổn định.
5. Dọn compatibility code khi không còn old clients.

Đây là mô hình thông dụng, **không thay thế ordering bắt buộc của một sản phẩm cụ thể**.

### 11.4. Timeout, retry và pool defaults

Driver upgrade có thể đổi default retryability, connection pool, TLS hoặc server selection. Phải ghi effective config và test unknown-write-outcome/idempotency.

## 12. TLS, authentication, authorization và certificate compatibility

Một nâng cấp có thể thay:

- TLS min/max version và cipher suites.
- X.509 certificate validation.
- Authentication protocol/mechanisms.
- Role names/permissions cho monitoring/backup.
- Token/session format.
- Default authorization enforcement.
- Client certificate trust roots.
- FIPS/crypto provider constraints.

### 12.1. Không hạ bảo mật để “upgrade thành công”

Khi client cũ không hỗ trợ TLS/cipher mới, ưu tiên nâng driver, cấu hình trust và cert rotation theo kế hoạch. Không tắt TLS hoặc cho phép insecure auth trên production chỉ để qua health check.

### 12.2. Mixed-version handshake

Test TLS/auth giữa Java driver và cả node old/new. Với một số cluster protocols, inter-node encryption/auth cũng cần compatibility matrix riêng.

### 12.3. Certificate expiration giữa maintenance

Một rolling upgrade kéo dài có thể trùng lịch rotation chứng chỉ; theo dõi thời hạn và xác minh CA chain trước khi khởi động node.

### 12.4. Least privilege

Các công cụ backup/upgrade thường cần quyền rộng hơn telemetry read-only. Đừng cấp admin lâu dài cho mọi exporter vì một bước migration yêu cầu admin.

## 13. Schema và dữ liệu trong mixed-version window

Với NoSQL, thay đổi schema không chỉ là thêm column. Có thể gồm:

- Document fields và nested shapes.
- BSON/JSON/Avro/Protobuf schema versions.
- CQL column types, materialized views, index definitions.
- Partition/shard key.
- Search mappings/analyzers.
- Graph labels/relationship properties.
- Redis key schemas.
- TTL và tombstone behavior.
- Trường numeric/decimal/date mới.
- Index rebuild hoặc backfill.

### 13.1. Expand–migrate–contract

Một chuỗi an toàn khi ứng dụng và database chạy nhiều phiên bản:

```text
EXPAND:
  Readers accept old and new shapes
  Writers continue emitting compatible data

MIGRATE:
  Backfill/dual-read where necessary
  Observe source and projection parity

CUTOVER:
  New readers/writers enabled after health gates

CONTRACT:
  Remove old fields/code only after all consumers moved
```

### 13.2. Dual-write không tự an toàn

Nếu ghi schema cũ và mới trong hai database/partitions khác nhau mà không có transaction chung, có thể xảy ra partial commit. Cần outbox/CDC/reconciliation/idempotency theo hệ.

### 13.3. Unknown fields

Old app có thể silently ignore field mới, nhưng khi lưu lại full document nó có thể xóa field ấy. Test **read old data → modify one field → write back** trên app cũ và schema mới.

### 13.4. Các thao tác không đảo ngược

Xóa field, đổi key format, nâng index format hoặc viết records mà old decoder không đọc được đều có thể trở thành rào cản rollback.

## 14. Consistency, quorum và write acknowledgement trong upgrade

Một request có thể thành công theo nhiều nghĩa:

```text
Client sends write
       |
       v
Coordinator accepts
       |
       v
Replica(s) persist according to consistency/durability
       |
       v
ACK returned
       |
       v
Other replicas catch up later
```

### 14.1. Giữ nguyên hợp đồng write/read

Trước và sau upgrade phải ghi rõ:

- Replica factor và placement.
- Write concern/consistency level.
- Read concern/consistency level.
- Commit/durability/journaling settings.
- Transaction semantics.
- Failover behavior.
- Timeout/retry settings.

Nếu thay những điều này để tăng throughput, đó là **thay đổi tính đúng đắn** cần được đánh giá riêng.

### 14.2. Cassandra `LOCAL_QUORUM` không phải majority mọi nodes

Quorum được tính theo replicas cho partition/DC tương ứng, không phải tổng số nodes toàn cluster. Roll từng node trong một datacenter phải xét RF và số replicas khỏe ở DC đó.

### 14.3. Election trong replica set

Trong hệ leader/primary, bảo trì primary có thể kích hoạt election. Service có thể gặp transient write errors hoặc connection resets; điều đó phải nằm trong SLO/test plan.

### 14.4. Timeout sau commit

Client timeout không chắc write chưa commit. Ứng dụng phải dùng operation ID, idempotency hoặc source status để xác định kết quả trước khi retry side effect.

## 15. Leader, primary và thứ tự nâng cấp

Trong một số hệ consensus/leader-based, nếu có thể và được vendor hỗ trợ, trình tự thường là:

1. Đảm bảo cluster khỏe và voters đủ.
2. Nâng followers/secondaries trước.
3. Kiểm tra followers mới catch up.
4. Step down/drain primary theo cơ chế supported.
5. Nâng node leader cũ sau khi role đã chuyển.
6. Xác minh election, routing và client retry.

### 15.1. Không áp máy móc cho mọi NoSQL

Cassandra không có một global primary như MongoDB replica set; Elasticsearch có shard primaries và cluster-manager role; Redis Cluster có masters/replicas theo slots. Trình tự thực tế phải theo model sản phẩm.

### 15.2. Leader step-down có thể gây gián đoạn ngắn

Ngay cả graceful handoff cũng có election interval, in-flight operations và cache/pool reconnect. Thử nghiệm staging và budget cho transient errors/latency.

### 15.3. Drain có thể chưa đủ

Khi ngừng nhận requests mới, vẫn cần xử lý/kiểm tra in-flight operations, shutdown hooks, WAL flush và replica catch-up. Không kill tiến trình chỉ vì load balancer đã ngừng route.

## 16. Shard placement, rebalancing và capacity theo vùng

Những hệ sharded thường có nhiều groups độc lập:

```text
Cluster
  |-- Shard A: primary + replicas
  |-- Shard B: primary + replicas
  |-- Shard C: primary + replicas
  |-- Routing/control-plane nodes
```

### 16.1. Cảnh báo khi nâng hai node “khác nhau”

Hai nodes có thể thuộc cùng replica set/shard group hoặc cùng AZ; mất chúng cùng lúc làm mất majority hoặc replica availability. Lập plan theo **failure domains và shard placement**.

### 16.2. Tránh rebalance lớn trong upgrade

Nếu vừa thêm/bỏ nodes vừa thay version, disk/network/metadata và nguyên nhân sự cố bị trộn. Một số hệ bắt buộc reallocation khi restart; cần đo và giới hạn nó thay vì giả định không xảy ra.

### 16.3. Kiểm tra placement sau mỗi node

- Required replicas đạt trạng thái healthy.
- Unassigned/under-replicated shards = 0 hoặc trong ngưỡng được phê duyệt.
- Token/range/slot coverage đầy đủ.
- Không có recovery backlog tăng mất kiểm soát.
- Hot partitions không nghẽn.
- Read/write routing đúng vùng/tenant.

### 16.4. Cross-region/DC upgrade

Thứ tự datacenters/vùng thường phải tuân theo vendor docs và traffic topology. Trong một hệ, có thể thực hiện từng DC; trong hệ khác, control plane có constraints riêng. Không suy “nâng DC phụ trước” luôn đúng.

## 17. Repair, compaction, snapshots và background jobs

Sau khi node restart với binary mới, hệ có thể:

- Replay commit log/WAL.
- Rebuild/recover indexes.
- Catch up replica changes.
- Start/continue compaction.
- Rebalance shards/ranges.
- Run storage upgrade tasks.
- Rescan security/config metadata.
- Resume backup/CDC streams.

### 17.1. “Process up” chưa phải đủ

Nếu node báo `RUNNING` nhưng chưa ready phục vụ partition, không được đánh dấu upgrade thành công. Cần data plane health và catch-up checks.

### 17.2. Compaction pressure

Một phiên bản mới có thể đọc/ghi format khác hoặc chạy background rewrite. Quá nhiều node upgrade liên tiếp có thể làm disk I/O và p99 tăng lâu dài.

### 17.3. Repair scheduling

Tránh khởi động nhiều repairs/full compactions không cần thiết giữa upgrade. Nếu hệ yêu cầu repair/rebuild ở một bước cụ thể, đưa vào plan và capacity budget.

### 17.4. Checkpoint tiến độ

Theo dõi last-progress time, backlog age, bytes/ranges/shards complete, retries và lỗi; không chỉ `isRunning`.

## 18. Backup, snapshot và khả năng restore có kiểm chứng

Trước nâng cấp, cần một điểm khôi phục đáng tin. “Backup job thành công” chưa đủ nếu chưa từng restore.

### 18.1. Câu hỏi bắt buộc

- Backup có consistent theo mong đợi không?
- Là cluster-wide, per-shard hay per-node snapshot?
- Có WAL/oplog/commitlog cần kèm không?
- Có backup encryption key và credential để restore không?
- Snapshot hỗ trợ restore sang version nào?
- Có giữ data schema và index/catalog metadata cần thiết không?
- RTO thực tế của restore bao lâu?
- RPO có chấp nhận mất writes sau snapshot không?
- Có quyền truy cập storage và mạng đến recovery region không?

### 18.2. Restore drill

Thực hiện thử restore trên môi trường tách biệt:

```text
Create backup
      |
      v
Restore into isolated cluster
      |
      v
Verify schema, indexes, key counts,
sample queries and business invariants
      |
      v
Record duration, capacity and missing dependencies
```

### 18.3. Không lấy copy data directory nóng như backup chung

Việc copy file tùy tiện khi database đang ghi có thể không giữ consistent state. Dùng phương pháp backup/snapshot được hỗ trợ bởi engine.

### 18.4. Backup trước upgrade không giữ các writes mới

Nếu restore về T0 sau khi hệ đã ghi các đơn hàng T1–T3, có thể mất confirmed writes nếu không có log replay/CDC capture và quy trình reconciliation.

## 19. RPO, RTO và kế hoạch quay lui

Hai đại lượng:

- **RPO — Recovery Point Objective:** mất tối đa bao nhiêu dữ liệu theo thời gian/khối lượng?
- **RTO — Recovery Time Objective:** mất bao lâu để phục hồi khả năng phục vụ?

Ví dụ minh họa:

```text
RPO = 0 for confirmed payments
RTO = 30 minutes for order read/write
```

Nếu phương án duy nhất là restore snapshot tạo một giờ trước, nó **không đáp ứng RPO=0** nếu đã có confirmed writes sau snapshot.

### 19.1. Phải tính thời gian phát hiện lỗi

RTO của một kế hoạch không chỉ là thời gian restore. Còn detection, decision, provisioning, data transfer, validation, DNS/routing cutover và client recovery.

### 19.2. Nếu RPO=0 thật sự cần

Có thể cần parallel cluster replication/CDC, durable transactional event log, dual-write được thiết kế đúng, hoặc roll-forward correction. Mỗi lựa chọn có consistency/ordering/gap risks phải chứng minh được.

### 19.3. Không chỉ ghi “có backup”

Một kế hoạch rollback có thể đạt RPO nhưng không đạt RTO nếu khôi phục hàng chục TiB mất nhiều giờ. Cần đo restore throughput và resource prerequisites.

## 20. Bốn kiểu rollback và giới hạn

| Kiểu | Ví dụ | Khi nào phù hợp | Rủi ro |
|---|---|---|---|
| Revert app/driver | Đưa Spring service về release trước | App cũ tương thích DB/schema mới | Old app ghi sai data mới |
| Revert config/feature flag | Tắt tính năng/query path mới | Flag reversible, không thay data format | Side effects đã phát sinh vẫn còn |
| Supported binary downgrade | Cài binary cũ theo vendor-supported procedure | Chưa vượt compatibility boundary | Storage/metadata không đọc được |
| Restore/failback | Dựng cụm cũ từ backup/replication | Downgrade không hỗ trợ hoặc data corrupt | RPO/RTO, writes mới, cutover divergence |

### 20.1. Roll forward là lựa chọn thứ năm

Khi đã dùng format mới không đảo ngược, có thể an toàn hơn nếu dùng hotfix/upgrade patch trên version mới và giữ data state thay vì khôi phục bản cũ.

### 20.2. Không lẫn application rollback với database downgrade

Có thể rollback app dễ dàng trong vài phút mà **không chạm database** nếu đã thiết kế backward-compatible schema. Đây thường là hướng giảm blast radius quan trọng.

### 20.3. Quay lại binary không quay lại dữ liệu

Nếu dữ liệu đã được chuyển sang schema mới, binary rollback dù chạy được cũng có thể khiến app không hiểu fields/semantics. Data migration cần kế hoạch riêng.

### 20.4. Side effects không thể “quay lui” bằng restore

Đơn hàng đã giao, email đã gửi, thanh toán đã capture, cache invalidation đã phát ra — restore DB không xóa tác động bên ngoài. Cần reconciliation/compensation theo nghiệp vụ.

## 21. Quyết định rollback trước khi bắt đầu

Một bảng quyết định mẫu:

| Tình huống | Hành động đề xuất |
|---|---|
| Canary node không join được; chưa ghi format mới | Dừng rollout, chẩn đoán; chỉ downgrade nếu vendor support |
| Driver lỗi sau deploy, database chưa nâng | Revert app/driver nếu schema tương thích |
| p99 tăng 3× trên một node, data safety ổn | Pause, xem cache/GC/compaction/config; quyết định rollback hoặc fix |
| Mixed-version replication errors | Dừng ngay, giữ quorum; recovery theo docs/support |
| Đã enable new incompatible feature | Không tùy tiện downgrade; roll forward/restore plan |
| Phát hiện index/schema divergence | Freeze cutover, reconcile và khôi phục an toàn |
| Mất confirmed writes hoặc invariant bị phá | Kích hoạt incident dữ liệu, stop unsafe writes, điều tra authoritative log |

### 21.1. Đặt trigger theo ngưỡng

Ví dụ:

```text
PAUSE if:
  API error rate > agreed SLO for 5 minutes
  OR p99 > 2x baseline for sustained window
  OR under-replicated shard count > threshold
  OR replica lag grows without bound
  OR disk free falls below recovery budget
  OR any correctness invariant fails
```

Các ngưỡng là **mẫu**, phải điều chỉnh theo SLO và nguồn dữ liệu thật. Với mất quorum hoặc corruption, hành động có thể cần tức thời.

### 21.2. Ai được quyết định?

Chỉ định primary operator, reviewer, incident commander/on-call và data owner. Không để automated rollout âm thầm chạy tiếp khi một validation gate không có dữ liệu.

## 22. Preflight: những điều phải biết trước khi nâng node đầu tiên

Một preflight nên trả lời:

1. Version current/target và upgrade path được hỗ trợ?
2. Mixed-version window được phép trong bao lâu?
3. Server/client/connector compatibility được xác minh?
4. Feature compatibility level/new storage features đang ở trạng thái nào?
5. Cluster health: đủ replicas/quorum, không có node suspect?
6. Storage/disk free, CPU, network, replication lag và cache headroom?
7. Có repair/rebalance/compaction/restore đang chạy cạnh tranh không?
8. Backup mới nhất và restore drill đạt RPO/RTO?
9. Schema migrations đã expand và rollback-compatible?
10. Monitor/alert/logging và health gates hoạt động?
11. Rolling order có xét AZ/DC/shard/leader roles?
12. Ai sở hữu action, approval, communications?
13. Thời gian/cửa sổ bảo trì có phù hợp traffic?
14. Có staging rehearsal và kết quả?
15. Có runbook cho node không join/rollback không?
16. Có giới hạn concurrency và điều kiện dừng tự động?

### 22.1. Không bắt đầu từ cụm đã suy giảm

Nếu có một replica down trước upgrade, bảo trì thêm node có thể làm mất quorum. Sửa hoặc hiểu rõ degradation trước khi mở rộng rủi ro.

### 22.2. Disk free bao nhiêu là đủ?

Không có phần trăm đúng cho mọi engine. Recovery, compaction, index build và data copy có thể cần temporary disk gấp nhiều lần delta. Dùng dự báo theo data size và operations thực.

### 22.3. Staging nên sát topology

Một single-node staging không kiểm thử được election, quorum, cross-zone routing, shard ownership hoặc mixed-version replication.

## 23. Lập một lệnh vận hành “node-by-node”

Cho mỗi node được phép nâng:

```text
1. Acquire maintenance lock / prevent concurrent upgrades
2. Record baseline health, metrics and current versions
3. Confirm target node is eligible and enough redundancy remains
4. Drain client traffic / leadership when supported
5. Stop/replace/upgrade using vendor-supported procedure
6. Start node with intended config, TLS, permissions, data path
7. Wait for process + membership + data readiness
8. Wait for replication/shard/streaming catch-up
9. Verify client read/write operations and correctness
10. Hold soak window; compare SLO to baseline
11. Record node version and outcome
12. Release maintenance lock and proceed only if all gates pass
```

### 23.1. Không có một lệnh chung để mọi NoSQL

`systemctl restart`, container rolling restart hoặc Kubernetes StatefulSet update mới chỉ điều phối process. Cần wrapper/health gates/leader election/ordering phù hợp engine.

### 23.2. Health check đa tầng

- **Process:** binary chạy, port lắng nghe.
- **Membership:** node tham gia cluster và metadata tương thích.
- **Data plane:** node có thể phục vụ partitions được giao.
- **Replication:** đã catch up theo ngưỡng.
- **Application:** driver requests thành công với correctness.
- **Operations:** p99, error, disk/CPU trong SLO.

### 23.3. Dừng khi thiếu tín hiệu

Một exporter chết không được diễn giải là `replicationLag=0`. Nếu không xác minh được safety gate, trạng thái là `UNKNOWN`, hành động mặc định là **PAUSE**.

## 24. Canary: chọn node đầu tiên thế nào?

Canary hữu ích nhưng không nên tùy tiện chọn một node “chẳng ai dùng”.

### 24.1. Tránh chọn sai vai trò

Một canary chỉ phục vụ read replica ít traffic có thể không bắt được lỗi write coordinator, shard primary, query planner hoặc index path. Cần workload coverage phù hợp.

### 24.2. Cân bằng blast radius và giá trị học

Chọn một node có thể thu thập đủ tín hiệu mà việc mất node không làm tổn hại quorum/critical shard. Nếu cần test leader semantics, làm trong staging hoặc maintenance với runbook chặt chẽ.

### 24.3. Canary không tự cô lập thay đổi cluster-wide

Một feature flag hoặc schema/catalog thay toàn cụm ngay cả khi mới nâng một node. Canary của binary không phải canary an toàn của metadata migration.

### 24.4. Soak time

Một vài request pass không chứng minh ổn định. Kiểm tra workload hỗn hợp, replication catch-up, GC/compaction, CDC lag và peak patterns phù hợp.

## 25. Mixed-version window: đây là giai đoạn có luật riêng

Trong lúc một phần nodes chạy bản mới và phần còn lại chạy bản cũ:

```text
               Cluster metadata / protocol
                   (compatible baseline)
                            |
                +-----------+-----------+
                |           |           |
                v           v           v
             Old A       New B       Old A
                |           |           |
                +-----------+-----------+
                            |
                    Java client traffic
```

### 25.1. Những thao tác nên trì hoãn

Tùy sản phẩm, có thể cần tránh:

- Bật cluster-wide feature yêu cầu toàn node mới.
- Chuyển storage/index/transaction format không hỗ trợ rollback.
- Áp schema breaking changes hoặc đổi keyspace format.
- Dùng query/command mới mà old nodes không hiểu.
- Chạy repair/rebuild/compaction đặc biệt không tương thích mixed-version.
- Nâng connector/backup pipeline theo cấu hình loại bỏ source compatibility quá sớm.
- Thay TLS/auth protocol trong khi old clients chưa hỗ trợ.

Đây là **các nhóm rủi ro**, không phải một danh sách cấm chung; tài liệu chính thức có thể yêu cầu hoặc cho phép những việc khác.

### 25.2. Kiểm tra version thực tế thay vì version deploy mong muốn

Một orchestrator có thể báo rollout đã gửi binary B, nhưng node vẫn đang restart hoặc chạy image cũ. Đọc **running server version trên từng node**, không chỉ Helm values/container manifest.

### 25.3. Cần quan sát compatibility errors

Log signatures có thể cho thấy unknown opcode, unsupported feature, failed handshake, schema version mismatch, election incompatibility hoặc serialization errors. Cần baseline log noise trước rollout để phân biệt vấn đề mới.

### 25.4. Giới hạn thời gian mixed-version

Thường đặt một maintenance window và trigger dừng nếu không hội tụ. Một mixed cluster lâu ngày làm rối incident response, backup recovery và support boundaries.

## 26. Cassandra: lưu ý riêng khi nâng cấp lần lượt

Apache Cassandra có kiến trúc peer-to-peer và lưu dữ liệu phân tán theo token ranges, datacenters cùng replication factor.

```text
DC1:
  C1 (old)   C2 (old)   C3 (old)

Upgrade C1, validate -> C2, validate -> C3
```

Đây là minh họa topology đơn giản, không phải thứ tự node bắt buộc cho mọi cluster.

### 26.1. Kiểm tra upgrade path

Tùy Cassandra major/minor/distribution, có thể cần qua **một số release trung gian**; storage format, CQL protocol và schema features có giới hạn cụ thể. Không nhảy trực tiếp từ một major rất cũ sang major mới chỉ vì package installer cho phép.

### 26.2. Duy trì đúng consistency level

Với RF=3 và `LOCAL_QUORUM`, việc dừng một replica có thể vẫn cho write/read hợp lệ trong nhiều tình huống, nhưng không nếu một replica khác ở cùng token range/DC đã down. Dựa trên `nodetool status` và thông tin placement/replication phù hợp, không chỉ số nodes alive tổng.

### 26.3. Công cụ quan sát

Ví dụ các lệnh đọc để kiểm tra tình trạng, khi phiên bản hỗ trợ:

```bash
nodetool status
nodetool netstats
nodetool tpstats
nodetool compactionstats
nodetool describecluster
```

`nodetool` kết nối JMX và cần quyền/cấu hình tương ứng. Output/fields tùy phiên bản và distribution.

### 26.4. Chuẩn bị dừng node

Quy trình được hỗ trợ có thể yêu cầu thao tác drain như `nodetool drain`, chờ flush và stop dịch vụ đúng cách trước khi thay binary. **Đọc runbook của đúng phiên bản** để biết thao tác nào bắt buộc, thao tác nào không được làm ở trạng thái đó.

### 26.5. SSTable format và compaction

Nâng cấp binaries không đồng nghĩa mọi SSTables được chuyển format ngay. Một số version có lệnh/chính sách rewrite SSTables riêng như `upgradesstables`; đây là thao tác I/O nặng và có thể làm **downgrade bất khả thi**, nên không chạy tùy tiện trong giai đoạn thử rollback.

### 26.6. Repair và tombstones

Sau khi một node offline dài, đồng bộ bằng hints/repair hoặc các cơ chế được hỗ trợ có thể cần thiết. Không tự giảm tombstone grace để “tiết kiệm” disk giữa upgrade, vì có nguy cơ resurrect dữ liệu cũ nếu replica bỏ lỡ delete.

### 26.7. Cassandra success gate

- Node phiên bản mới ở trạng thái khỏe.
- Gossip/membership và schema agreement phù hợp.
- Reads/writes theo consistency level yêu cầu thành công.
- Không tăng dropped messages/blocked pools.
- Streaming/compaction/repair metrics trở về mức chấp nhận được.
- Java driver có thể discover nodes/execute prepared statements.
- Disk/CPU/latency còn headroom cho node kế tiếp.

## 27. MongoDB replica set: thứ tự primary–secondary và FCV

Một MongoDB replica set có primary và secondaries, cùng voting/election semantics. Một kế hoạch thường gặp khi **được version docs hỗ trợ**:

```text
Healthy replica set
       |
       v
Upgrade eligible secondary
       |
       v
Wait secondary startup and replication catch-up
       |
       v
Upgrade next eligible secondary
       |
       v
Step down primary using supported procedure
       |
       v
Upgrade former primary
       |
       v
Verify elections, replication and majority write concerns
       |
       v
Adjust Feature Compatibility Version only at approved gate
```

### 27.1. Vì sao upgrade secondaries trước?

Giảm rủi ro gián đoạn writes khi có một primary còn phục vụ, đồng thời cho phép quan sát phiên bản mới trên replica trước.

### 27.2. Majority votes chưa chắc giống majority data

Replica set có thể chứa arbiters hoặc voters cấu hình đặc biệt; không suy từ số host bất kỳ rằng có đủ data-bearing replicas để đáp ứng durability/read concern.

### 27.3. FCV và rollback

MongoDB có Feature Compatibility Version, nhưng điều kiện đổi FCV, các phiên bản cho phép chuyển và binary downgrade path **phụ thuộc release**. Không coi “hạ FCV” là bảo đảm tuyệt đối rằng mọi dữ liệu/metadata sau đó đều downgrade được.

### 27.4. Sharded MongoDB

Ngoài shards/replica sets còn có config server replica set và `mongos`. **Thứ tự nâng các thành phần trong sharded deployment phải theo tài liệu của đúng target version**; không dùng trình tự replica set đơn lẻ cho toàn sharded cluster.

### 27.5. Quan sát

```javascript
db.adminCommand({ hello: 1 })
db.adminCommand({ replSetGetStatus: 1 })
db.adminCommand({ getParameter: 1, featureCompatibilityVersion: 1 })
```

Các commands/version/permissions có thể khác; đây là gợi ý quan sát chứ không phải script upgrade hoàn chỉnh. Lưu election events, replication lag, driver server selection failures, query p99 và write concern errors.

### 27.6. Change Streams/oplog

CDC consumers cần tiếp tục từ resume token hợp lệ, không mất events giữa elections/restarts. Downtime dài hoặc oplog history window nhỏ có thể làm token hết hiệu lực, buộc resnapshot/reconciliation.

### 27.7. Query planner và index

Bản mới có thể thay query planning/execution. Kiểm tra `explain`, key/doc examination, index usage, latency trên workload đại diện. Nâng replica set thành công nhưng p99 tăng là một regression có thật.

## 28. MongoDB sharding: tránh nhầm migration với upgrade

Một sharded cluster có thêm:

- Config servers lưu metadata.
- `mongos` routers.
- Shard replica sets.
- Balancer và chunk/range migrations.

### 28.1. Nâng các thành phần theo hướng được hỗ trợ

Một release có thể yêu cầu thứ tự cụ thể của config server, shards và routers, cùng constraints khi cluster đang mixed-version. **Không khái quát một thứ tự duy nhất** cho mọi major release.

### 28.2. Balancer và chunk migration

Trong upgrade, nếu balancer/range migrations chạy nền, chuyển động metadata và data có thể tranh network/disk. Phải xác định việc tạm dừng/tiếp tục balancer có được hướng dẫn hay bắt buộc trong upgrade path cụ thể.

### 28.3. Routing compatibility

`mongos` và drivers phải hiểu routing metadata của shards ở trạng thái chuyển tiếp. Nếu ứng dụng gặp `StaleConfig`/routing-related errors, cần phân biệt transient retryable errors và incompatibility.

### 28.4. Kiểm tra nghiệm thu

- Mọi shard và config server đạt target version.
- Routing/mongos trạng thái phù hợp.
- No unfinished data migrations beyond threshold.
- Cluster schema/config metadata hợp lệ.
- Read/write latency, sharding distribution và errors trong SLO.
- FCV mới chỉ bật sau final compatibility approval.

## 29. Elasticsearch/OpenSearch: shard recovery, cluster-manager và index formats

Elasticsearch và OpenSearch có rolling upgrade quy trình riêng theo version. Một cụm phân bố shards và replicas, đồng thời có cluster-manager/master-eligible nodes.

```text
Indices -> Primary/replica shards -> Data nodes
                                  \
                                   Cluster-manager/control plane
```

### 29.1. Không chỉ thay image của tất cả pods

Một rolling process restart thiếu cluster health gates có thể khiến shards unassigned, recovery backlog lớn và p99 search tăng kéo dài.

### 29.2. Thứ tự role/tier

Một số release có thứ tự nâng data tiers và master-eligible nodes được chỉ định rõ. Phải theo tài liệu target release, không dùng danh sách vai trò của một release cũ áp cho release khác.

### 29.3. Tương thích index format

Indices được tạo bởi phiên bản quá cũ có thể **không tương thích** với target. Có thể cần reindex trước khi nâng, snapshot restore hoặc công cụ migration chính thức. Đây là lý do cần **inventory creation versions của indices**, không chỉ server version.

### 29.4. Quan sát read-only

```http
GET /_cluster/health
GET /_cat/nodes?v
GET /_cat/shards?v
GET /_cat/recovery?v
GET /_cluster/pending_tasks
```

Các APIs phản ánh các mặt khác nhau, cần auth/permissions phù hợp. Không kết luận toàn cluster đã khỏe chỉ từ HTTP 200.

### 29.5. Shard relocation/recovery

Trong một số quy trình supported, operator có thể tạm điều chỉnh shard allocation hoặc flush để giảm copy thừa rồi hoàn nguyên; **không tự áp một hướng dẫn cũ** vì lệnh sai có thể làm shards không phục hồi.

### 29.6. Downgrade thường không phải đường quay lui

Với những thay đổi data/index/cluster-state format, việc hạ binary tại chỗ có thể không hỗ trợ. Phương án đáng thử trước là snapshot/restore lên cụm tương thích, rollback query traffic hoặc roll forward.

### 29.7. Search correctness và latency

Kiểm tra mappings, analyzers, vector index settings, query DSL/client compatibility và index-refresh behavior. Một cluster green không chứng minh relevance, hit count hay search freshness tương đương.

## 30. Redis Cluster/Sentinel: module, persistence và slot ownership

Redis có mô hình khác: standalone, Sentinel-managed primary/replica hoặc Redis Cluster chia keyspace theo hash slots.

### 30.1. Redis Cluster không có một global quorum cho mọi key giống MongoDB

Cần kiểm tra masters/replicas cho từng slot coverage và topology, không áp công thức majority voters chung. Failure behavior còn phụ thuộc persistence, replication và client routing.

### 30.2. Trình tự role-aware

Một pattern được **version/vendor docs** hỗ trợ có thể nâng replicas trước, đảm bảo sync, chuyển vai trò primary/master có kiểm soát rồi nâng node cũ. Nhưng cách failover/switchover và commands phải tuân theo version và topology.

### 30.3. Redis module compatibility

Một module có thể phụ thuộc API/ABI của Redis. Binary Redis mới có thể chạy được nhưng module không load hoặc dữ liệu module không tương thích. Đưa modules/scripts/Redis Functions vào compatibility matrix.

### 30.4. Persistence/RDB/AOF

Các format RDB/AOF hoặc metadata sau upgrade có thể không đọc lại được bằng phiên bản cũ. Kiểm tra khả năng restore riêng và không coi thay binary là rollback đáng tin.

### 30.5. Redis Cluster clients

Java Lettuce/Jedis clients có cơ chế xử lý `MOVED`/`ASK` và cập nhật slot cache. Kiểm tra client reconnect khi node restart/role change; không để stale topology gây timeout hàng loạt.

### 30.6. Read-only status

```text
INFO server
INFO replication
INFO persistence
CLUSTER INFO
CLUSTER NODES
CLUSTER SLOTS
```

Các lệnh cluster chỉ áp dụng khi ở cluster mode. Test ephemeral cache vs authoritative Redis data storage khác nhau về yêu cầu durability/recovery.

## 31. Couchbase: service-aware upgrade và rebalance

Couchbase là distributed NoSQL với KV, Query, Index và các services khác theo cấu hình deployment.

### 31.1. Nâng từng node không đồng nghĩa chỉ ảnh hưởng KV

Nếu node chứa Index service hoặc Query service, restart có thể ảnh hưởng truy vấn dù KV replicas vẫn có. Lập danh sách roles/services per node.

### 31.2. Rebalance và failover

Trong một số deployment, upgrade yêu cầu/khuyến nghị phối hợp rebalance và thao tác trên nodes. Không giả định một `kubectl rollout restart` thay thế phương pháp Couchbase được hỗ trợ.

### 31.3. Storage engine và backup tools

Couchbase có storage/index format và backup utility compatibility theo version; kiểm tra target path, edition, cluster encryption và restore procedures trước khi nâng.

### 31.4. DCP và connectors

Các thay đổi feed protocol, vBucket ownership hoặc index service có thể ảnh hưởng Kafka connector/CDC; cần test resume/checkpoint/rollback.

### 31.5. Health gates

KV read/write p99, bucket readiness, active/replica vBuckets, index/Query availability, rebalance progress, DCP lag, disk/memory headroom và SDK retry behavior.

## 32. Neo4j và HBase: các đặc điểm khác Cassandra/MongoDB

### 32.1. Neo4j

Neo4j cluster thường có leader/follower roles theo RAFT/replication model tùy version/edition. Nâng cấp cần xét:

- Cluster protocol compatibility.
- Store format / database upgrade finalization.
- Server/driver compatibility với Bolt.
- APOC/procedures/extensions version.
- Transaction log và leader election.
- Backup/restore compatibility.
- Graph indexes và Cypher query behavior.

Một số major upgrades có thể yêu cầu **offline migration** hoặc những điều kiện đặc biệt; không coi rolling upgrade luôn được hỗ trợ.

### 32.2. HBase

HBase dựa trên region assignment, RegionServers, HMaster, WAL, HDFS/ZooKeeper hoặc kiến trúc phiên bản tương ứng. Nâng cấp cần:

- Compatibility HBase/Hadoop/Java.
- WAL/HFile formats.
- Region assignment/regions in transition.
- Master/RegionServer coordination.
- Replication và compaction backlog.
- Table availability theo region.

HBase có rolling upgrade restrictions và major version migration requirements riêng; dùng ma trận chính thức.

### 32.3. Không ghép mọi engine vào một orchestration script duy nhất

Một “stop one pod, replace image, wait ready” chưa đánh giá role-aware election, storage migration hoặc index recovery của từng engine.

## 33. Managed NoSQL: DynamoDB, Cosmos DB và các dịch vụ khác

Với managed NoSQL, người dùng thường **không có quyền nâng binary trên từng node**. Provider chịu trách nhiệm nhiều thay đổi bên trong; khách hàng vẫn phải quản trị:

- SDK/driver và API versions.
- IaC/schema/index changes.
- Throughput/capacity tier.
- Feature/consistency settings.
- Regional topology/replication.
- CDC feeds/change streams.
- Backup/PITR và data migrations.
- Query behavior và service limits.

### 33.1. DynamoDB

Không lên kế hoạch `nodetool` hoặc rolling restart workers của DynamoDB. Khi thay đổi GSI, table capacity, global tables mode, TTL, Streams hoặc application SDK, theo dõi build/replication/throttle/latency và rollback khả thi của **schema/feature**.

### 33.2. Azure Cosmos DB

Database partitioning/patching được service quản lý; ứng dụng có thể phải đổi SDK, consistency, indexing policy hoặc throughput. Test RU consumption, request latency, 429, physical partition growth, multi-region behavior và Change Feed Processor leases.

### 33.3. Firestore/other serverless NoSQL

Tập trung vào API/schema/index migrations, SDK compatibility, security rules, export/import/recovery và quotas. Không giả định vendor cho phép rollback service binary.

### 33.4. Change advisory

Ngay cả khi provider tự nâng, vẫn cần biết maintenance notice, API deprecations, planned changes và SLO impact nếu có. Các đường recovery thường là cấu hình/ứng dụng/backup thay vì package downgrade.

## 34. CDC, search, cache và backup agents trong một nâng cấp cụm

Một cluster không sống độc lập:

```text
Java application
       |
       v
Source NoSQL Cluster ----> CDC Connector ----> Kafka
       |                                          |
       v                                          v
    Redis Cache                              Search Index
       |
       v
Backup/Monitoring/Restore Tools
```

### 34.1. CDC source format

Oplog/commitlog/change feed hoặc protocol có thể thay đổi behavior/metadata sau server upgrade. Connector đang dùng resume token hoặc offsets phải được test trước.

### 34.2. Checkpoints còn hợp lệ?

Không giả định checkpoint từ phiên bản cũ luôn dùng được trên connector mới hoặc sau snapshot/index migration. Nếu source retention gap xảy ra, connector cần nhận diện và resnapshot/reconcile.

### 34.3. Search sinks

Đổi BSON/JSON field type, timezone, decimal hay null handling có thể làm Elasticsearch mappings reject documents. Monitor indexing failures và DLQ, không chỉ source DB QPS.

### 34.4. Cache format

Java DTO mới có thể không đọc được cached documents/serialized bytes cũ. Dùng versioned cache keys/schema hoặc safe migration; không vô tình invalidation toàn bộ cache gây stampede lên NoSQL vừa upgrade.

### 34.5. Backup agents

Một agent cũ có thể không hỗ trợ server mới hoặc restore artifacts được tạo bằng version mới. Test backup sau upgrade và khả năng restore ở target cụ thể.

## 35. Java application compatibility: test matrix quan trọng

Một ứng dụng Spring Boot có thể hoạt động trong ít nhất bốn trạng thái:

| Database state | App/driver cũ | App/driver mới |
|---|---|---|
| All-old server | Baseline | Must work if driver-first rollout |
| Mixed-version cluster | Chỉ trong supported window | Must work if released first |
| All-new server, old-compatible features | Must work until app cutover | Expected |
| All-new + new features/schema | Có thể không được hỗ trợ | Target state |

### 35.1. Test không chỉ `ping()`

Cần kiểm tra:

- Point reads/writes với nhiều payload sizes.
- Conditional updates và conflict handling.
- Transactions và commit retries.
- Query theo index, pagination/continuation tokens.
- Batch operations.
- Change Stream/CDC subscriptions.
- Authentication/TLS.
- Failover/reconnect/resume.
- Schema old/new read/write.
- Timeouts/unknown write outcomes.
- Health metrics và trace propagation.

### 35.2. Prepared statements/query plans

CQL prepared statement metadata hoặc server-side cached plans có thể đổi sau schema/server version change. Đảm bảo driver reprepare/refresh schema theo semantics supported, không tự suy lỗi query là transient vô hạn.

### 35.3. Backward read compatibility

Old app cần đọc documents có field mới mà không xóa chúng khi ghi lại. Nếu không, rollback app có thể gây data loss dù server binary còn tương thích.

### 35.4. Connection surge

Sau leader election, hàng nghìn JVM instances có thể reconnect đồng thời. Thiết kế pool backoff/jitter và driver retry để không gây connection storm.

## 36. Java: đặt measurement boundary cho upgrade gates

Đo từ **trước khi gọi repository/driver** đến lúc có result/error:

```java
import java.util.concurrent.Callable;

public final class TimedCall {

    public static <T> T invoke(
            Callable<T> action,
            TimingSink sink
    ) throws Exception {
        long startedAt = System.nanoTime();
        String outcome = "success";

        try {
            return action.call();
        } catch (Exception error) {
            outcome = "error";
            throw error;
        } finally {
            long elapsedNanos =
                    System.nanoTime() - startedAt;

            sink.record(elapsedNanos, outcome);
        }
    }

    public interface TimingSink {
        void record(long durationNanos, String outcome);
    }
}
```

### 36.1. Cách dùng

Đặt wrapper quanh repository operation đại diện, không chỉ đo một `health ping`. Đối với correctness, phải kiểm tra nội dung response và consistency contract trước khi đếm goodput.

### 36.2. Không tính p99 từ một mẫu

Cần histogram/timer phù hợp để tổng hợp trong cửa sổ và tách success, timeout, conflicts. Không lấy trung bình p99 per-minute.

### 36.3. `nanoTime` chỉ đo duration trong cùng JVM

Không trừ `System.nanoTime()` trên hai processes. Với CDC freshness xuyên services, cần correlation IDs, source versions và phép đo phù hợp clock skew.

### 36.4. Mẫu code chỉ minh họa đo

Không bao gồm retries, request IDs, cancellation, histogram hoặc startup. Production nên dùng Micrometer/OpenTelemetry và instrumentation có labels cardinality hữu hạn.

## 37. Java Micrometer: gate theo phiên bản rollout

Giả sử API có metric per-operation; một cách instrument:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.Callable;

public final class UpgradeGateMetrics {
    private final MeterRegistry registry;
    private final String appRelease;

    public UpgradeGateMetrics(
            MeterRegistry registry,
            String appRelease
    ) {
        this.registry = registry;
        this.appRelease = appRelease;
    }

    public <T> T observe(
            String operation,
            Callable<T> action
    ) throws Exception {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            return action.call();
        } catch (Exception ex) {
            outcome = "error";
            throw ex;
        } finally {
            sample.stop(
                Timer.builder("nosql.client.operation")
                    .tag("operation", operation)
                    .tag("release", appRelease)
                    .tag("outcome", outcome)
                    .publishPercentileHistogram()
                    .register(registry)
            );
        }
    }
}
```

### 37.1. Release tag phải hữu hạn

Dùng canonical release label (v1/v2 hoặc release digest có retention policy), không gắn mỗi request ID hoặc document key làm metric label.

### 37.2. Không lấy metrics từ một instance canary để đại diện toàn cluster

Need sample mix, tenant/operation distribution, shard participation và số lượng requests đủ. So with baseline trong cùng điều kiện phù hợp.

### 37.3. Gate thiếu telemetry = không pass

Nếu Prometheus scrape thất bại hoặc histogram không đủ mẫu, kết luận nên là `UNKNOWN/PAUSE`, không mặc định xanh.

## 38. Kubernetes StatefulSet không thay engine upgrade protocol

Nhiều cụm NoSQL chạy trên Kubernetes. Các khái niệm:

- StatefulSet ordinal/Pod identity.
- PersistentVolume/PVC.
- PodDisruptionBudget (PDB).
- Readiness/liveness/startup probes.
- RollingUpdate partition.
- Operator/controller.
- Affinity và topology spread.
- Graceful termination.

### 38.1. `maxUnavailable=1` chưa chắc an toàn

Một Pod ở shard group đang mất replica khác vẫn có thể là thành phần cuối giữ quorum. PDB cũng không thay cluster-specific data health gates.

### 38.2. PVC vẫn ở version storage mới

Đưa Pod image từ B về A giữ PVC đã được B ghi. Nếu format incompatible, Pod cũ không chạy. **Rolling back Helm/chart không đồng nghĩa downgrading database an toàn.**

### 38.3. Operator-aware workflows

Một operator chuyên dụng có thể tự điều phối readiness, maintenance mode, role transfers và version validations. Đừng song song tự `kubectl delete pod` nếu phá state machine của operator.

### 38.4. Control plane outage

Một kube API outage có thể ngăn automation quan sát/tiếp tục, dù DB vẫn phục vụ. Plan cần cho trạng thái `PAUSED` mà không tự retry phá dữ liệu.

## 39. Automation workflow có checkpoints

Một upgrade orchestrator nên có state persistent:

```text
UpgradePlan
  targetVersion
  allowedVersionPath
  approvedStart
  currentPhase
  nextEligibleNode
  lastSuccessfulNode
  changedFeatureFlags
  backupReference
  lastGoodMetricsWindow
  pausedReason
  incidentReference
```

Một state machine:

```text
PREFLIGHT
  |
  v
CANARY
  |
  v
VALIDATING
  |
  +---- failed ----> PAUSED
  |
  v
ROLLING_NODE_N
  |
  v
CATCH_UP
  |
  v
VERIFY_GATE
  |        |
  |        +---- unknown/failed --> PAUSED
  v
NEXT_NODE or FINALIZE
```

### 39.1. Idempotency của automation

Restart worker không được upgrade cùng một node hai lần theo các hành động không idempotent. Trước mỗi step, đọc **actual cluster state** và job record.

### 39.2. Distributed lock/fencing

Hai operators/automation jobs không nên cùng nâng node khác nhau mà làm mất redundancy. Lock phải có ownership/lease semantics và fencing, không chỉ một file flag trên máy chạy script.

### 39.3. Không hardcode `sleep 30`

Một node có thể khởi động trong 10 giây hoặc 20 phút. Wait theo **health/replication state** với timeout, exponential checks và human escalation.

### 39.4. Có thể dừng an toàn

Giữa nodes là checkpoint lý tưởng. Khi một node đang chuyển on-disk format, kill giữa chừng có thể gây hậu quả khác; theo vendor recovery instructions.

## 40. Health gates: định lượng và không thể bỏ qua

Một template:

```yaml
upgradeGate:
  cluster:
    requiredReplicasHealthy: true
    requiredQuorumPresent: true
    unknownDataHealthAllowed: false

  foreground:
    successfulGoodputMinRatioToBaseline: 0.95
    readP99MsMax: 200
    writeP99MsMax: 400
    errorRateMax: 0.001

  background:
    replicationLagWithinBudget: true
    criticalShardUnassigned: false
    backlogNotGrowingWithoutBound: true

  capacity:
    diskHeadroomWithinPolicy: true
    networkWithinPolicy: true
    cpuWithinPolicy: true

  observation:
    stableForSeconds: 600
    metricDataFresh: true
```

Đây là **ví dụ tài liệu policy**, không phải cấu hình chạy trực tiếp của Cassandra/operator nào. Ngưỡng phải dựa trên SLO thật, operational baselines và capacity risk.

### 40.1. Điều kiện hard gate

Mất quorum, replication corruption, authentication failures rộng hoặc mất confirmed writes là vấn đề phải dừng ngay, không chờ trung bình p99 10 phút.

### 40.2. Điều kiện soft gate

p99 tăng tạm trong election window có thể nằm trong SLO đã dự kiến; decision xem duration, error budget và trend.

### 40.3. Dữ liệu metric stale

Nếu exporter crash, dashboards có thể trống. Gate phải kiểm tra thời điểm sample cuối cùng; không biến missing data thành zero errors/zero lag.

### 40.4. Dùng baseline đúng

So cùng operation, payload, region, consistency, load shape. Upgrade lúc traffic cao điểm phải đánh giá với time-of-day normalization hoặc controlled workload, không chỉ mean hôm qua.

## 41. Runbook khẩn cấp: node mới không join cluster

Tình huống:

```text
Node C3 stopped cleanly
Binary target B installed
Process starts but C3 fails membership/join
Other nodes currently healthy
```

### 41.1. Bảo toàn trạng thái

- **Dừng mở rộng rollout.**
- Không thử upgrade tiếp node khác.
- Giữ quorum/traffic trên các nodes còn lại.
- Ghi logs, version, config, exit codes, cluster membership.
- Không xóa data directory hoặc metadata để ép join.

### 41.2. Điều tra theo lớp

1. Process start: OS/JVM/library permissions.
2. Network/TLS: ports, certificates, peer authentication.
3. Compatibility: có đi sai upgrade hop/cluster metadata version?
4. Storage: SSTable/index/WAL format, disk free, corruption.
5. Cluster state: decommission/replace vs normal join path.
6. Clock/time/auth settings và resource limits.
7. Logs từ peers bị từ chối/handshake errors.

### 41.3. Recovery decision

- Nếu chỉ config mismatch: sửa config và restart theo runbook.
- Nếu data format mới nhưng incompatible: dùng forward-compatible corrective release hoặc vendor-supported recovery, không tự downgrade.
- Nếu node data không còn usable: rebuild/rejoin từ replicas/backup theo plan, kiểm tra đủ quorum và capacity.
- Nếu bị mất redundancy gần ngưỡng: incident escalated, cân nhắc hạn chế writes/traffic theo business policy.

### 41.4. Verify

Membership + replicas + application operations + replication lag + background recovery. Không chỉ process `RUNNING`.

## 42. Runbook khẩn cấp: primary election kéo dài

Khi upgrade một primary/leader, clients có thể gặp:

```text
Server selection timeout
NotPrimary/NotLeader
Connection reset
Write concern timeout
Unknown commit result
```

Tên lỗi phụ thuộc driver/DB.

### 42.1. Đừng retry mù quáng

Một write có thể đã commit trước khi failover. Với order/payment/inventory, cần idempotency key/conditional version và authoritative status lookup trước khi phát lại business side effects.

### 42.2. Chẩn đoán

- Election logs và quorum health.
- Primary/voter reachability.
- Replica lag và disk/network pressure.
- TLS/auth/version handshake.
- Driver topology refresh/connection pools.
- Client retry/backoff và timeouts.

### 42.3. Không ép election liên tục

Lặp đi lặp lại step-down/failover có thể kéo dài outage hoặc mất headroom. Hành động thay leadership phải tuân runbook và cluster safety.

### 42.4. Sau election

Test writes với expected durability, reads theo consistency, client retries, p99/timeout và data correctness. Theo dõi một khoảng soak trước node kế tiếp.

## 43. Runbook khẩn cấp: dữ liệu/index không tương thích

Một phiên bản mới có thể bắt đầu ghi index/documents với schema không đọc được bởi app/cluster cũ.

### 43.1. Phát hiện

- Deserialization/codec errors.
- Query planner/index mapping errors.
- CDC converter rejection/DLQ growth.
- App old release cannot parse new events.
- New binary writes metadata unsupported by old.
- Backup restore target rejects format.

### 43.2. Giữ nguyên bằng chứng và ngừng thay đổi phá hủy

Không chạy script “fix” xóa fields/index hoặc force-compaction khi chưa hiểu. Xác định phiên bản/feature gây format change và phạm vi dữ liệu bị ảnh hưởng.

### 43.3. Lựa chọn

1. Tắt feature flag nếu reversible.
2. Roll forward code để đọc cả old/new formats.
3. Migration dữ liệu theo quy trình verified.
4. Rebuild projection từ authoritative source.
5. Restore/failback nếu chấp nhận RPO/RTO và có reconciliation.
6. Xin vendor support nếu binary/storage compatibility bị nghi ngờ.

### 43.4. Quan trọng với search

Search index là projection có thể rebuild; không nhất thiết cần rollback source NoSQL vì lỗi index. Nhưng nếu search là critical user path, cần graceful fallback hoặc capacity.

## 44. Runbook khẩn cấp: CDC consumer không theo kịp

Trong upgrade, CDC connectors có thể:

- Disconnect/reconnect.
- Replay duplicates.
- Lose resume position nếu retention hết.
- Reject schema mới.
- Gặp sharding/partition assignment changes.

### 44.1. Quan sát

- Source current position vs connector checkpoint.
- Oldest retained source history.
- Publish and sink lag.
- DLQ/errors by schema version.
- Search-visible freshness.
- Duplicate/stale event rejection.

### 44.2. Không bỏ qua gap

Khi checkpoint quá cũ so với retention, restart từ “now” có thể **bỏ mất UPDATE/DELETE**, làm projection sai âm thầm. Cần snapshot+tail/reconciliation.

### 44.3. Tách lỗi nguồn và lỗi đích

NoSQL source có thể healthy, connector lag vì sink overload. Không kết luận upgrade DB thất bại chỉ từ Kafka lag, nhưng đây là guardrail nếu business cần freshness.

### 44.4. Sau recovery

Đối soát counts/source versions, deletes/tombstones và end-to-end freshness; không chỉ `consumer lag=0`.

## 45. Observability: những chỉ số phải thu theo thời gian

| Tầng | Metrics | Ý nghĩa |
|---|---|---|
| Cluster control plane | Node versions, membership, elections | Mixed-version và quorum |
| Replication | Lag, health, under-replicated ranges/shards | Data availability/durability |
| Client | Driver errors, retries, pool wait, p95/p99 | User-visible impact |
| Query | Latency per operation, index plans, scanned docs | Query regression |
| Storage | Disk I/O, free disk, compaction, WAL replay | Capacity/format impact |
| JVM | Heap, GC pause, CPU, threads | Load from new binary/driver |
| Network | RTT, errors, bandwidth, TLS handshakes | Inter-node/client connectivity |
| Maintenance | Repair, relocation, index build, backlog | Recovery progress |
| CDC | Source checkpoint, retained window, sink lag | Projection correctness |
| Business | Lost/duplicate operations, oversell, authorization | Invariant safety |
| Security | Auth errors, permissions, TLS failures | Client/peer compatibility |
| Cost | Additional replica/backup/transfer/compute | Migration economics |

### 45.1. Theo từng node và từng region

Cluster average có thể đẹp trong khi một shard hot hoặc một zone thiếu replicas. Tách roles, replica groups và tenant paths theo nhu cầu.

### 45.2. Hành vi đã thay đổi nhưng version metric chưa phản ánh

Một feature flag hoặc server default mới có thể tác động toàn cluster trước khi tất cả nodes upgraded; annotate timeline của mọi config/feature changes.

### 45.3. Không bỏ synthetic probes

Một health probe chỉ `ping` không phát hiện transaction failure, query planner regression hoặc stale reads. Probe các operations quan trọng bằng test keys và dữ liệu an toàn.

## 46. Báo cáo phiên bản và cấu hình đã triển khai

Một upgrade report nên lưu:

```yaml
change:
  id: nosql-cluster-upgrade-2026-11
  objective: "Apply security/stability fixes"
  owner: "data-platform"
  approvedWindow: "record exact timezone and UTC interval"
  vendorGuide: "record version-specific official reference"

versions:
  source: "exact version/build"
  target: "exact version/build"
  intermediateVersions: []
  driverVersions: []
  connectorVersions: []

topology:
  cluster: "orders-prod"
  regions: ["region-a"]
  availabilityZones: ["az-a", "az-b", "az-c"]
  nodes: "record per node, role, shard and version"
  replicaSettings: "record exact"

compatibility:
  serverToServer: "verified"
  driver: "verified"
  storageFormat: "verified"
  authenticationTls: "verified"
  schema: "verified"
  cdc: "verified"

recovery:
  backupId: "actual backup reference"
  restoreDrill: "date, result, duration"
  rpo: "business requirement"
  rto: "business requirement"
  rollbackBoundary: "feature/storage format change"
  fallbackMethod: "documented and rehearsed"

rollout:
  maxUnavailable: "engine-specific constraint"
  initialCanary: "selected node/role"
  nodeOrder: "approved sequence"
  gatePolicy: "health + SLO + correctness"
  stopTrigger: "unknown, failed or threshold exceeded"

artifacts:
  configHash: "actual hash"
  appRevision: "actual git commit"
  metricsDashboard: "actual reference"
  operationLog: "actual reference"
  postmortem: "if needed"
```

Đây là mẫu tài liệu, không phải YAML trực tiếp điều khiển một cluster.

### 46.1. Lưu configuration diff

Ghi các thay đổi thực tế ở JVM flags, encryption, pool sizes, TTL/compaction, indexes, GC, network settings. `image tag changed` chưa phản ánh mọi thay đổi.

### 46.2. Lưu những điều không biết

Nếu rollback compatibility chưa xác minh, ghi rõ `UNKNOWN/BLOCKER` thay vì `probably supported`.

### 46.3. Metadata nhạy cảm

Không đưa secrets, credentials, private key hoặc raw customer payloads vào báo cáo. Dùng secret references và quyền đọc hạn chế.

## 47. Kiểm tra dữ liệu trước/sau: không chỉ so số bản ghi

Một upgrade phải có cơ chế chứng minh dữ liệu và invariants vẫn đúng.

### 47.1. Những kiểm tra cơ bản

- Số lượng records/items theo collection/table/partition.
- Kích thước và phân phối partitions/shards.
- Số indexes và trạng thái usable.
- Sampling reads theo stable keys.
- Số dòng/đơn hàng theo tenant và trạng thái.
- Version/ETag/last update theo key.
- Quorum/replication health.
- Delete/TTL/tombstone behavior.
- Search projection sourceVersion so với source DB.
- Count của failed writes và unknown outcomes.

### 47.2. Count bằng nhau không đủ

Hai datasets đều có 10 triệu documents nhưng một record bị mất và một record khác bị nhân đôi vẫn có cùng count. Nên kết hợp keys, sampled content hashes và business invariant checks.

### 47.3. Checksum phải có scope

Nếu tính checksum trên dữ liệu đang thay đổi liên tục, hai lần đọc ở thời điểm khác có thể khác nhau hợp lệ. Cần point-in-time snapshot, version watermark, per-range check hoặc reconciliation algorithm phù hợp.

### 47.4. Business invariants

Ví dụ:

```text
A confirmed payment has exactly one authoritative order.
An inventory reservation never makes available count negative.
A deleted user must not reappear in search projection.
Tenant U can only access data owned by U.
An idempotency key maps to at most one committed operation.
```

Các invariants này quan trọng hơn việc mọi node đã mang version mục tiêu.

## 48. Diễn tập sự cố trước production

Trong staging có topology tương đương, nên thử:

1. Dừng node không phải leader giữa heavy writes.
2. Dừng primary và quan sát election/retry.
3. Chặn một số inter-node connections để kiểm tra quorum và timeouts.
4. Restart node mới khi cache chưa warm.
5. Làm chậm disk để quan sát compaction/recovery backlog.
6. Cho một replica đang trễ bị bảo trì.
7. Tạo CDC lag trước khi upgrade.
8. Restart connector tại giữa change stream.
9. Đổi schema theo expand–migrate–contract và thử app cũ đọc/ghi.
10. Thử một roll-forward patch khi rollback binary không hỗ trợ.
11. Thử restore backup vào isolated target.
12. Thử rollback app với dữ liệu do app mới vừa ghi.
13. Tạo client reconnect storm.
14. Duy trì tải peak và một node unavailable.
15. Cố tình làm monitoring exporter mất kết nối để kiểm tra gate `UNKNOWN`.

### 48.1. Không diễn tập phá dữ liệu trên production không được phép

Chỉ thực hiện fault injection trong môi trường được phê duyệt với data giả hoặc scope được kiểm soát, có kế hoạch phục hồi và owner trực.

### 48.2. Đo failure recovery

- Detection time.
- Election/unavailable duration.
- Backlog drain time.
- Error/timeouts/unknown-write-outcome count.
- p99/p99.9 trong và sau lỗi.
- Replication catch-up time.
- Data integrity mismatches.
- RTO/RPO quan sát thực tế.

### 48.3. Thử đúng phiên bản mục tiêu

Một upgrade thành công trong staging trên phiên bản khác không thay việc kiểm tra binary/config/driver chính xác sẽ deploy.

## 49. Ma trận lỗi và lựa chọn ứng phó

| Biểu hiện | Nguyên nhân cần xác minh | Hành động đầu tiên | Những hành động cần thận trọng |
|---|---|---|---|
| Node mới không join | Protocol/TLS/config/storage mismatch | Pause và thu logs | Xóa data directory, downgrade tự do |
| Replica lag tăng | I/O, network, replay, write burst | Giữ node kế tiếp, đo catch-up | Restart nhiều replicas |
| Quorum thiếu | Node down, election, network split | Incident safety, dừng rollout | Force leader/unsafe writes |
| Read p99 tăng | Cache cold, query planner, shard hotspot | Correlate client/server metrics | Đổi consistency cho nhanh |
| Write p99 tăng | Quorum, index maintenance, WAL, retry | So write concern và disk pressure | Tắt durability không có approval |
| Index incompatible | Old index format/mapping | Pause, xem supported reindex/restore | Force-open file bằng binary sai |
| CDC lag/gap | Connector incompatibility/retention | Đo source position và gap | Skip thẳng tới latest |
| Backup không restore | Tool/version/keys/format | Dừng tại gate, sửa recovery | Bật feature không đảo ngược |
| Disk sắp đầy | Recovery copy/compaction/index rewrite | Pause, bảo vệ headroom | Xóa SSTable/WAL thủ công |
| Client auth errors | TLS mechanism, certs, driver | Kiểm tra trust/auth configs | Tắt TLS hoặc quyền kiểm soát |
| Rollback app parse lỗi | Schema mới không backward compatible | Stop rollout, migration/dual-reader | Blind overwrite dữ liệu |
| Managed service throttle | Capacity/RU/hot key | Phân tích quotas/capacity | Kết luận binary vendor lỗi |

### 49.1. “Hành động đầu tiên” thường là dừng mở rộng

Khi mới phát hiện bất thường, **không tiếp tục nâng node kế tiếp** chỉ vì muốn hoàn tất maintenance window đúng giờ.

### 49.2. Dùng incident mode khi invariant bị phá

Với dữ liệu thanh toán/kho/quyền truy cập, sai lệch correctness là sự cố bảo mật/nghiệp vụ cần owner và điều tra, không chỉ performance regression.

## 50. Kế hoạch quay lui mẫu: upgrade ứng dụng và NoSQL có tách pha

Giả sử tổ chức có:

```text
Order API (Java)
      |
      v
MongoDB replica set
      |
      +---- Change Streams ---> Kafka ---> Search index
      |
      +---- Backup/PITR
```

Mục tiêu: nâng driver và MongoDB server trong một chuỗi có thể quan sát.

### 50.1. Pha A — trước thay đổi

- Xác nhận upgrade path/FCV/driver được hỗ trợ.
- Tạo backup, diễn tập restore vào cluster riêng.
- Lưu source versions, config, node roles và metrics baseline.
- Ghi CDC checkpoint/retention window.
- Test app mới có thể chạy với old MongoDB.
- Test old app đọc được data mà app mới sẽ tạo, nếu dự kiến rollback app.

### 50.2. Pha B — driver/application trước

- Deploy driver có hỗ trợ old/new.
- Giữ schema/write format ở dạng tương thích.
- Canary app và test transactions/queries/watch/resume.
- Nếu regression: revert application build trong khi database chưa đổi.
- Nếu ổn: chuyển tới DB rollout.

### 50.3. Pha C — rolling database binaries

- Một secondary nâng xong, catch up, soak.
- Secondary kế tiếp nâng xong, catch up, soak.
- Step-down primary theo procedure hỗ trợ rồi nâng.
- Confirm all members target version và majority write behavior.
- Verify CDC/source resume và search freshness.

### 50.4. Pha D — compatibility finalization

- Chỉ nâng FCV/bật features mới sau khi đã xác định không còn cần binary rollback cũ.
- Ghi rõ điểm chuyển rollback strategy: từ **possible supported downgrade** sang **roll forward/restore** nếu feature/format không đảo ngược.
- Validate query plans, index/read model consistency, backup tool và restore mới.

### 50.5. Pha E — thất bại ở đâu thì xử lý khác nhau

| Thời điểm lỗi | Lựa chọn ưu tiên |
|---|---|
| Sau deploy app nhưng trước DB | Revert app và sửa driver settings |
| Secondary canary lỗi, chưa format change | Pause, sửa config; supported recovery/downgrade theo docs |
| Giữa mixed-version | Dừng rollout, giữ quorum, tương thích protocol; không tự bật FCV mới |
| Sau all-new, trước irreversible feature | Vendor-supported backout path nếu tồn tại, hoặc forward fix |
| Sau irreversible feature / storage rewrite | Roll forward, failback/restore có reconciliation |
| CDC sink lỗi nhưng source khỏe | Rebuild projection/connector, giữ source data, không rollback DB vô cớ |

### 50.6. Data writes phát sinh trong thời gian rollback

Một restore T0 khi đã có confirmed Orders ở T1 không đạt RPO=0. Nếu cần failback, phải có cách reconcile/replay dữ liệu sau T0 và giải quyết side effects ngoài DB. Viết rõ **chủ sở hữu quyết định data loss** trước khi sự cố xảy ra.

## 51. Kế hoạch quay lui blue-green cluster

Khi binary downgrade không hỗ trợ, dựng song song cụm mới có thể cho đường backout tốt hơn — nhưng không tự bảo đảm.

```text
Old Cluster (source) -------> CDC/replication -------> New Cluster
      |                                                |
   Old App                                          New App
      |                                                |
      +-------------- Traffic router -------------------+
```

### 51.1. Đường dữ liệu một chiều

Nếu writes chỉ ở Old rồi mirror sang New, có thể cutover khi New catch up. Nhưng sau cutover, writes mới vào New sẽ không tự quay về Old. Phải thiết kế reverse sync hoặc chấp nhận failback với data reconciliation.

### 51.2. Dual-write có rủi ro

Hai databases khác nhau thường không có transaction chung. Nếu một write thành công ở New nhưng thất bại ở Old, rollback có thể mất dữ liệu. Cần idempotency, ordering, conflict resolution và reconciliation.

### 51.3. Read shadowing

Có thể shadow **reads** sang candidate cluster để so results/latency mà không ảnh hưởng write authority. Không nhân đôi transactions/payments/shipments chỉ để thử benchmark.

### 51.4. Cutover gate

- Reconciliation gần/đạt zero mismatches theo policy.
- CDC lag không vượt ngưỡng.
- Schema/client compatible.
- New cluster đủ capacity.
- Rollback route và data-divergence handling rõ.
- Routing/DNS connection draining đã test.

### 51.5. Không gọi “blue-green” là zero-risk

Chi phí cao hơn, cùng với replication lag, ordering, duplicate updates và split brain tại thời điểm chuyển quyền ghi. Đây là đánh đổi cần được thiết kế, không phải nút rollback kỳ diệu.

## 52. Checklist trước nâng cấp

- [ ] Đã chốt mục tiêu business/security của upgrade.
- [ ] Đã ghi exact source/target/intermediate version builds.
- [ ] Có official supported upgrade path và support matrix.
- [ ] Biết mixed-version được hỗ trợ trong phạm vi/thời gian nào.
- [ ] Có inventory cluster roles, shards, replica sets, AZ/DC.
- [ ] Có consistency/replication/quorum và capacity budget.
- [ ] Không có node thiếu redundancy hoặc trạng thái chưa giải thích.
- [ ] Đã ghi storage/index/catalog format constraints.
- [ ] Đã đánh dấu mọi irreversible feature/format gate.
- [ ] Có driver/SDK/JVM/connector/backup/exporter compatibility.
- [ ] Có TLS/auth/cert/permissions compatibility.
- [ ] Có schema expand-migrate-contract và app rollback compatibility.
- [ ] Dataset/backup/snapshot và restore drill đã xác minh.
- [ ] Có RPO/RTO được business owner chấp nhận.
- [ ] Đã lên kế hoạch xử lý confirmed writes sau backup.
- [ ] Có baseline HTTP/driver/server p99, goodput, error rate.
- [ ] Có replication lag, quorum, shard allocation, disk headroom metrics.
- [ ] Có backup/CDC/search freshness và DLQ alerts.
- [ ] Có node eligibility/order/maintenance windows rõ.
- [ ] Có staging rehearsal với failover/mixed-version.
- [ ] Có owners, approvals, escalation và runbook.
- [ ] Có automation lock/fencing và pause-on-unknown behavior.
- [ ] Có plan khi binary downgrade không hỗ trợ.

## 53. Checklist trong rolling upgrade

- [ ] Kiểm tra maintenance lock thuộc một owner duy nhất.
- [ ] Xác nhận phiên bản chạy thực trên từng node.
- [ ] Chỉ mở một node/replica group được phép mỗi lúc.
- [ ] Đảm bảo quorum và đủ replica trước khi drain node.
- [ ] Dùng bước drain/leader transfer được vendor hỗ trợ.
- [ ] Chờ membership/data readiness, không chỉ process startup.
- [ ] Kiểm tra replication/shard streaming catch-up.
- [ ] Soak theo traffic và background task thực tế.
- [ ] Đo errors, p95/p99, goodput, timeouts, retries.
- [ ] Xác minh read/write/conditional transaction correctness.
- [ ] Kiểm tra disk/compaction/GC/network/headroom.
- [ ] Theo dõi CDC/checkpoints/search freshness.
- [ ] Không bật tính năng/format không tương thích trong mixed-version.
- [ ] Ghi node upgrade status, timestamp và decision.
- [ ] Pause nếu telemetry stale, gate fail hoặc safety unknown.
- [ ] Không upgrade node tiếp theo để “chữa” một node mới không join.
- [ ] Mỗi hành động khôi phục phải có runbook và rollback impact.
- [ ] Không xóa raw data files hoặc hạ binary unsupported.

## 54. Checklist hậu nâng cấp

- [ ] Mọi node/role đang chạy exact target version.
- [ ] Không còn mixed-version ngoài policy.
- [ ] Quorum, replica placement và shards/ranges khỏe.
- [ ] No pending critical recovery hoặc unreconciled divergence.
- [ ] Read/write/query/index/transaction workloads đạt SLO.
- [ ] Không có dữ liệu confirm bị mất/trùng/trái invariant.
- [ ] Java drivers/SDKs qua được mixed/all-new integration tests.
- [ ] CDC source-to-sink fidelity và delete propagation đã xác minh.
- [ ] Cache/schema/cursor/continuation token compatibility ổn.
- [ ] Query plans và index behavior không có regression quan trọng.
- [ ] Backup agents chạy với server mới và restore drill được cập nhật.
- [ ] Feature compatibility/storage migration chỉ bật sau phê duyệt.
- [ ] Rollback/roll-forward decision được cập nhật theo điểm không đảo ngược.
- [ ] Có số liệu p99, goodput, error, disk, CPU, cost trước/sau.
- [ ] Có lịch theo dõi hậu rollout với người chịu trách nhiệm.
- [ ] Có upgrade log, config diffs, version hashes, incident notes.
- [ ] Tài liệu vận hành, alert thresholds và recovery process đã cập nhật.
- [ ] Tắt maintenance mode/temporary permissions/flags theo kế hoạch.

## 55. Những hiểu nhầm dễ làm hỏng một cuộc upgrade

**“Mỗi lần chỉ restart một node nên không thể mất quorum.”** Sai khi một replica khác đã down hoặc topology placement không đủ.

**“5 nodes có majority 3 nghĩa lúc nào cũng nâng 2 nodes cùng lúc được.”** Không; safety margin, data replicas và SLO còn ràng buộc.

**“Rollout image theo StatefulSet là toàn bộ upgrade procedure.”** Không; cần server version compatibility, data health, leader/replication gates.

**“Node chạy binary mới nên đã phục vụ bình thường.”** Chưa chắc; có thể đang rebuild/catch up.

**“All nodes healthy nghĩa ứng dụng không có lỗi.”** Không; query planner, drivers và schema có thể regression.

**“Chỉ cần latest server đọc được old data.”** Chưa đủ; mixed-version và rollback còn đòi các chiều compatibility khác.

**“Thay old binary trở lại là rollback chắc chắn.”** Không khi on-disk/catalog format đã thay.

**“Có snapshot thì RPO=0.”** Không nếu writes sau snapshot không được reconcile/replay.

**“Backup thành công nghĩa restore thành công.”** Chưa có restore drill.

**“Tắt TLS tạm thời là cách nâng cấp client.”** Không phù hợp security requirement.

**“Nâng driver đồng thời nâng mọi DB nodes mới nhanh.”** Có thể làm khó cô lập nguyên nhân incompatibility.

**“Mixed-version có thể chạy lâu dài vì cluster chưa báo đỏ.”** Không nếu nằm ngoài support window.

**“Cassandra có một primary global.”** Không; replication theo token/DC.

**“MongoDB replica set nâng primary trước luôn tối ưu.”** Có thể gây election/write downtime không cần thiết; theo thứ tự được docs hỗ trợ.

**“Elasticsearch green nghĩa mọi query chắc chắn đúng.”** Không; mappings, queries, stale data và freshness cần kiểm tra.

**“Redis master/replica ACK là durability giống transaction của mọi DB.”** Không; persistence/replication mode khác.

**“DynamoDB cần operator reboot từng node để upgrade.”** Không; backend managed.

**“FCV là một nút undo tuyệt đối.”** Không; binary downgrade còn phụ thuộc version, data/feature state.

**“Rebalance và compaction không liên quan performance.”** Chúng cạnh tranh CPU/disk/network và ảnh hưởng tail latency.

**“CDC lag=0 nghĩa mọi search index đều đúng.”** Không; deletes/schema/failed sink events có thể sai.

**“Có idempotent retry thì không cần theo dõi unknown write outcomes.”** Cần biết mỗi operationId thực sự đã commit chưa.

**“App cũ đọc được field mới là rollback schema an toàn.”** Old app có thể overwrite làm mất field khi save full document.

**“Tất cả metric gauges bằng 0 nghĩa không có lỗi.”** Metrics có thể missing/stale.

**“Chỉ cần kiểm tra p50.”** Tail latency và timeouts có thể tăng mạnh sau leader election.

**“Đã chọn canary không quan trọng nên không có blast radius.”** Cluster metadata/feature changes có thể ảnh hưởng tất cả.

**“Rollback DB sẽ hủy email/payment đã gửi.”** External side effects không đảo ngược theo cách ấy.

**“Sau upgrade là xong; không cần theo dõi nữa.”** Cache warmup/compaction/index rebuild và workload peak có thể lộ regression về sau.

## 56. Bài tập và tình huống thực hành

### Bài tập 1 — Rolling upgrade có gì khác rolling restart?

Một cluster thay image cùng version từng node.

**Câu hỏi:** Đây có phải rolling upgrade version không?

**Gợi ý:** Không nếu version không đổi; đây là rolling restart và vẫn cần health checks.

### Bài tập 2 — Đếm quorum

Một nhóm 5 voters có majority 3.

**Câu hỏi:** Có thể mất mấy votes mà vẫn còn majority trong mô hình đơn giản?

**Gợi ý:** Hai; chưa tính data placement và failure margin.

### Bài tập 3 — Quorum không đồng nghĩa availability

RF=3, `LOCAL_QUORUM`, một replica đã down. Team muốn nâng một replica nữa cùng DC.

**Câu hỏi:** Vì sao không nên tiến hành mù quáng?

**Gợi ý:** Có thể mất quorum cho partitions liên quan.

### Bài tập 4 — Capacity calculation

6 nodes, steady CPU 85% mỗi node, một node tạm rời cụm.

**Câu hỏi:** Ước tính CPU bình quân còn lại nếu traffic chia đều?

**Gợi ý:** \(85\%\times6/5\approx102\%\), không đủ headroom theo mô hình đơn giản.

### Bài tập 5 — Mixed-version

Một server cũ và hai server mới cùng chạy.

**Câu hỏi:** Có nên bật feature mà server cũ không hỗ trợ không?

**Gợi ý:** Không nếu docs yêu cầu trì hoãn tới finalization.

### Bài tập 6 — Version compatibility

Java driver hỗ trợ new server nhưng không hỗ trợ old server.

**Câu hỏi:** Có thể nâng driver trước toàn cluster không?

**Gợi ý:** Không theo trình tự đó; cần version bridge/hợp đồng tương thích.

### Bài tập 7 — On-disk format

Bản mới ghi SSTable/segment format cũ không đọc được.

**Câu hỏi:** Cài lại binary cũ có an toàn không?

**Gợi ý:** Không nếu vendor không hỗ trợ downgrade trên format đó.

### Bài tập 8 — Backup vs data loss

Snapshot chụp 10:00, upgrade lỗi 11:00 sau khi nhận 1000 writes.

**Câu hỏi:** Restore snapshot 10:00 có đạt RPO=0 không?

**Gợi ý:** Không nếu writes mới không có cơ chế khôi phục.

### Bài tập 9 — RTO

Restore mất 90 phút, SLO RTO 30 phút.

**Câu hỏi:** Kế hoạch đã đủ chưa?

**Gợi ý:** Chưa; cần đường phục hồi nhanh hơn hoặc yêu cầu được phê duyệt thay đổi.

### Bài tập 10 — Revert application

App v2 ghi field `payment.state`, app v1 chỉ hiểu `status`.

**Câu hỏi:** Rollback app v1 có tự an toàn không?

**Gợi ý:** Không; cần backward read/write compatibility.

### Bài tập 11 — Canonical auth

Database upgrade thay TLS min version, client cũ không handshake.

**Câu hỏi:** Có nên tắt TLS tạm thời không?

**Gợi ý:** Không; nâng driver/trust config đúng chính sách.

### Bài tập 12 — Cassandra tools

Muốn xem node status và streaming.

**Câu hỏi:** Lệnh quan sát nào hữu ích?

**Gợi ý:** `nodetool status`, `nodetool netstats`; không chạy repair để “xem”.

### Bài tập 13 — Cassandra compaction

Cluster vừa nâng một node, pending compactions tăng và disk giảm.

**Câu hỏi:** Có nên nâng node tiếp ngay khi process `UP`?

**Gợi ý:** Chưa; đánh giá headroom và stability gates.

### Bài tập 14 — Cassandra consistency

Một node down kéo dài khiến hints có thể hết thời hạn.

**Câu hỏi:** Hints có thay định kỳ repair không?

**Gợi ý:** Không; cần anti-entropy theo runbook.

### Bài tập 15 — MongoDB upgrade order

Một replica set có primary và hai secondaries.

**Câu hỏi:** Vì sao thường nâng secondaries trước theo docs hỗ trợ?

**Gợi ý:** Giảm tác động tới write leader và thử binary mới trước.

### Bài tập 16 — MongoDB FCV

Toàn cluster nâng binary xong nhưng chưa nâng FCV.

**Câu hỏi:** Vì sao finalization cần decision gate riêng?

**Gợi ý:** FCV/new features có thể ảnh hưởng rollback compatibility.

### Bài tập 17 — MongoDB Change Streams

Sau failover, listener resume token cũ không còn trong oplog.

**Câu hỏi:** Có được tiếp tục từ now rồi tuyên bố đồng bộ không?

**Gợi ý:** Không; cần gap detection và resnapshot/reconciliation.

### Bài tập 18 — Elasticsearch index format

Old index được tạo rất lâu trước target version.

**Câu hỏi:** Cần làm gì trước rolling upgrade?

**Gợi ý:** Kiểm tra index compatibility và reindex/restore path theo docs.

### Bài tập 19 — Elasticsearch yellow

Sau restart một data node, cluster yellow.

**Câu hỏi:** Có đồng nghĩa source data mất không?

**Gợi ý:** Không nhất thiết; xem replicas/shard allocation và SLO.

### Bài tập 20 — Redis persistence

Redis binary mới ghi RDB file không tương thích binary cũ.

**Câu hỏi:** Có thể rollback binary trong Pod giữ PVC không?

**Gợi ý:** Không nếu storage format không đọc được.

### Bài tập 21 — Redis Cluster

Java client không cập nhật `MOVED` redirects sau switchover.

**Câu hỏi:** Nó có thể gây lỗi gì?

**Gợi ý:** Routing/timeouts dù cluster nodes còn khỏe.

### Bài tập 22 — Couchbase KV vs Query

Upgrade node Query service, KV vẫn healthy nhưng SQL++ queries lỗi.

**Câu hỏi:** Vì sao một số health dashboards vẫn xanh?

**Gợi ý:** Health per-service cần tách, không chỉ KV.

### Bài tập 23 — Neo4j extensions

Bolt driver kết nối thành công, nhưng APOC procedure không load.

**Câu hỏi:** Compatibility matrix thiếu gì?

**Gợi ý:** Extensions/procedures và query-path tests.

### Bài tập 24 — Managed NoSQL

DynamoDB tự quản node upgrades.

**Câu hỏi:** Khách hàng còn phải kiểm tra những gì?

**Gợi ý:** SDK, GSI/Streams/API/schema, quotas, backup, query behavior.

### Bài tập 25 — Kubernetes

StatefulSet báo rollout hoàn tất, một replica vẫn catching up.

**Câu hỏi:** Có nên báo upgrade hoàn thành?

**Gợi ý:** Chưa; DB data-plane/replication gates chưa pass.

### Bài tập 26 — Driver retry

Payment write timeout sau election nhưng đã commit.

**Câu hỏi:** Retry bằng operation ID mới có an toàn không?

**Gợi ý:** Không; cần idempotency/authoritative outcome.

### Bài tập 27 — Metric stale

Monitoring exporter ngừng scrape trong canary.

**Câu hỏi:** Health gate nên pass hay pause?

**Gợi ý:** Unknown → pause.

### Bài tập 28 — Disk headroom

Bản mới bắt đầu rewrite indexes, disk free 7%.

**Câu hỏi:** Có nên tiếp tục upgrade hàng loạt?

**Gợi ý:** Không nếu thấp hơn recovery/temporary-space budget; điều tra.

### Bài tập 29 — Quorum vs shards

Cluster 9 nodes nhưng hai replicas của cùng shard group đều chuẩn bị restart.

**Câu hỏi:** Vì sao tính theo tổng node sai?

**Gợi ý:** Shard-specific replication/quorum placement.

### Bài tập 30 — CDC pipeline

Source nâng thành công, Kafka connector vẫn chạy nhưng DLQ tăng mạnh do schema.

**Câu hỏi:** Có nên đánh dấu success toàn hệ?

**Gợi ý:** Không; cross-system correctness/freshness guardrail.

### Bài tập 31 — Blue-green writes

Sau cutover sang New cluster, Old cluster không nhận writes mới.

**Câu hỏi:** Failback về Old có RPO=0 không?

**Gợi ý:** Không nếu không có reverse replication/reconciliation.

### Bài tập 32 — Side effects

Database restore trước một `ShipmentCreated` event đã gửi.

**Câu hỏi:** Restore có hủy shipment không?

**Gợi ý:** Không; cần compensation/reconciliation.

### Bài tập 33 — Canary coverage

Canary node chỉ phục vụ ít read traffic, còn production có heavy writes và transactions.

**Câu hỏi:** Kết quả canary có đủ không?

**Gợi ý:** Chưa; test operation/role coverage.

### Bài tập 34 — Query regression

All nodes new, cluster green, p99 của aggregation tăng 4×.

**Câu hỏi:** Bước phân tích nào cần làm?

**Gợi ý:** Query plans, index usage, CPU/disk, data distribution và SLO.

### Bài tập 35 — Feature enablement

Sau all-new, team muốn bật feature mới ngay mà chưa test app rollback.

**Câu hỏi:** Nên quyết định thế nào?

**Gợi ý:** Tách approval cho irreversible gate; kiểm tra clients/backups/restore.

### Bài tập 36 — Thiết kế runbook hoàn chỉnh

Một Java/Spring Boot service dùng MongoDB cho Orders, Redis Cluster cho cache và CDC sang Elasticsearch. Đội vận hành muốn nâng MongoDB và Redis trong cùng tháng.

**Yêu cầu:** Viết version matrix, node order, canary scope, driver tests, health/SLO gates, backups/RPO/RTO, CDC monitoring, cache compatibility, unsupported-downgrade recovery và post-upgrade acceptance.

**Gợi ý:** Tách hai changes; upgrade Java driver khi cần bridge; kiểm tra MongoDB replica set/FCV/Change Streams; Redis slots/replicas/persistence/Lettuce routing; rebuild search khi CDC gap; luôn giữ rollback app độc lập và xác minh writes phát sinh sau snapshot.

## 57. Mẫu một trang quyết định “Go / No-Go / Pause”

```text
Upgrade: NoSQL orders-prod, source -> target version
Window: UTC + local time explicitly recorded
Owner: primary operator + reviewer

GO only when:
  [ ] Upgrade path officially supported
  [ ] Mixed-version matrix approved
  [ ] Data-plane health and quorum pass
  [ ] SLO headroom with one node unavailable
  [ ] Restore drill and RPO/RTO accepted
  [ ] Driver/CDC/backup compatibility verified
  [ ] No unknown security/storage format blocker
  [ ] Canary and irreversible feature gates defined

PAUSE immediately when:
  [ ] Quorum/data safety unknown or violated
  [ ] Node fails to rejoin or catch up
  [ ] Replication/recovery backlog grows unchecked
  [ ] Critical client auth/protocol errors
  [ ] p99/error/goodput SLO gate failed
  [ ] CDC gap or correctness mismatch
  [ ] Disk/temp-space budget breached
  [ ] Telemetry unavailable/stale

FINALIZE only when:
  [ ] All nodes target version
  [ ] No unhealthy replica/shard/partition
  [ ] Business invariants and end-to-end SLO pass
  [ ] Post-upgrade backups and restore path confirmed
  [ ] Feature flag / FCV enablement separately approved
  [ ] Rollback strategy updated for new format boundary
```

Không dùng biểu mẫu này như một script tự chạy; đây là **gợi ý review checklist** trước mỗi decision gate.

## 58. Tổng kết

Nâng cấp NoSQL **lần lượt** là chiến lược giảm rủi ro bằng cách thay phiên bản từng node hoặc từng nhóm nhỏ, nhưng chỉ an toàn khi **cluster topology, quorum/replica placement, khả năng chịu tải còn lại, clients và dữ liệu** cùng đáp ứng các điều kiện của phiên bản đích.

Có ba điều phải luôn tách biệt:

1. **Khả năng hoạt động của cluster:** node còn lại đủ quorum/replicas, shard routing đúng và p95/p99/goodput/error rate đáp ứng SLO.
2. **Khả năng tương thích:** server-to-server, Java driver, TLS/auth, protocol, storage format, schema, CDC, backup, index và các thành phần tích hợp. Một mixed-version window được vendor hỗ trợ không đồng nghĩa các tính năng mới có thể bật ngay.
3. **Khả năng quay lui:** rollback application/config, supported binary downgrade, roll forward và restore/failback là các cơ chế khác nhau. Khi storage/catalog/schema đã đi qua điểm không tương thích, **downgrade tại chỗ có thể bị cấm**; backup chỉ hữu ích khi restore đã được kiểm chứng và dữ liệu phát sinh trong thời gian upgrade được bảo vệ theo RPO/RTO.

Một kế hoạch production cần có **upgrade path chính thức, compatibility matrix, staging rehearsal, backup/restore drill, capacity/quorum preflight, node-by-node health gates, canary, telemetry, stop conditions, application/CDC correctness checks, và runbook phục hồi theo phiên bản**. Finalization các tính năng/định dạng mới phải là quyết định riêng, không chỉ là bước cuối của một script.

**Nguyên tắc cốt lõi:** *Chỉ nâng node kế tiếp khi đã chứng minh node vừa nâng và toàn cluster vẫn phục vụ đúng hợp đồng. Chỉ đi qua điểm không quay lại khi đã chứng minh được đường phục hồi dữ liệu, ứng dụng và nghiệp vụ — không phải vì mong rằng cài lại binary cũ sẽ luôn hoạt động.*





