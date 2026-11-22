# Đọc release note, tính năng bị loại bỏ và tham số thay đổi

> **Chương:** Nâng cấp và tương thích  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Phạm vi:** Apache Cassandra — cơ sở dữ liệu wide-column phân tán; chú trọng partition key, bảng thiết kế theo truy vấn, consistency level, CQL, replication, compaction, repair, xử lý lỗi và kết nối Java.

## 1. Vì sao phải đọc release note trước khi nâng cấp?

Một cụm Cassandra có thể hoạt động tốt trước khi nâng cấp nhưng gặp lỗi sau khi thay phiên bản dù **schema và dữ liệu không đổi**. Các nguyên nhân điển hình là:

- Tham số trong **cassandra.yaml** hoặc JVM options đã bị đổi tên, ngừng hỗ trợ hay thay giá trị mặc định.
- Phiên bản Cassandra mới đòi hỏi phạm vi **JDK** khác, làm thay đổi collector, flag JVM hoặc cách cấp phát bộ nhớ.
- CQL, cơ chế xác thực, TLS, giao thức native protocol hoặc metadata trả về có khác biệt mà ứng dụng Java/driver chưa tương thích.
- Công cụ **nodetool**, backup/restore, repair, streaming hoặc compaction có hành vi hay tùy chọn khác trước.
- Phiên bản mới sinh SSTable hoặc metadata không phù hợp với cách “quay lui” bằng việc cài lại binary cũ.
- Một thay đổi mặc định khiến ứng dụng tiếp tục chạy nhưng có timeout, latency, lượng replica tham gia hoặc chính sách bảo mật không như kỳ vọng.

Vì vậy, **release note** không chỉ là bản liệt kê tính năng mới. Với Cassandra, nó là đầu vào để xây **ma trận tương thích, danh sách thay đổi có hành động, kế hoạch kiểm thử và phương án phục hồi** trước khi đưa bất kỳ node sản xuất nào sang phiên bản mới.

### Sau bài học, bạn cần làm được gì?

1. Tìm đúng loại tài liệu cho **phiên bản nguồn, phiên bản đích và các bản phát hành trung gian bắt buộc**.
2. Phân biệt **deprecated**, **removed**, **renamed**, **default changed**, **behavior changed** và **known issue**.
3. Đối chiếu cấu hình thực tế, bao gồm những tham số **đang dùng mặc định**, với hướng dẫn phiên bản đích.
4. Nhận diện ảnh hưởng lên Cassandra cluster, Java driver, CQL/schema, replication, compaction/repair và backup.
5. Chuyển mỗi thay đổi đáng chú ý thành một phép kiểm chứng có owner, mức độ rủi ro và điều kiện dừng.
6. Giải thích vì sao **rollback bằng binary cũ** có thể không an toàn sau một số bước nâng cấp dữ liệu.

> **Lưu ý:** Bài này dạy phương pháp đọc và áp dụng tài liệu thay đổi. Tên tham số, phiên bản hỗ trợ, thứ tự thao tác và giới hạn tương thích cụ thể **phải được kiểm tra trong tài liệu của đúng bản Cassandra và bản phân phối đang sử dụng**. Các bảng ví dụ giả lập được ghi rõ để tránh coi là thông báo phát hành chính thức.

## 2. Đọc đúng tài liệu, đúng đường nâng cấp

### 2.1. Các tài liệu có chức năng khác nhau

| Loại tài liệu | Trả lời câu hỏi gì? | Đầu ra cần ghi vào kế hoạch |
|---|---|---|
| **Release notes / changelog** | Phiên bản này sửa lỗi, bổ sung hay đổi hành vi gì? | Danh sách thay đổi liên quan tới workload |
| **Upgrade guide** | Có được nâng trực tiếp từ phiên bản nguồn không? Thứ tự node, bước tương thích và lệnh hậu nâng cấp là gì? | Đường nâng cấp và runbook đã kiểm tra |
| **Breaking changes / migration notes** | API, định dạng lưu trữ, CQL, tham số hoặc tính năng nào phải chuyển đổi? | Hạng mục bắt buộc sửa |
| **Configuration reference** | Tên key, kiểu dữ liệu, phạm vi, mặc định và ràng buộc của phiên bản đích là gì? | Bảng đối chiếu cấu hình cũ/mới |
| **Compatibility matrix** | Cassandra, JDK, Java driver, native protocol, công cụ backup và hệ điều hành có tương thích không? | Ma trận phiên bản được hỗ trợ |
| **Known issues / limitations** | Trường hợp nào chưa an toàn, có workaround hoặc yêu cầu trì hoãn nâng cấp? | Risk/stop gate và phiên bản đích phù hợp |
| **Security advisories** | Có vấn đề an ninh yêu cầu bản vá hoặc thay cấu hình không? | Mức ưu tiên, biện pháp giảm rủi ro và kiểm chứng |

**Không dùng changelog thay thế upgrade guide.** Một bug fix có thể không cần hành động, nhưng một yêu cầu nâng cấp nhiều chặng có thể chỉ được nói rõ trong tài liệu migration hoặc hướng dẫn phát hành.

Khi dùng bản phân phối Cassandra do nhà cung cấp đóng gói hoặc một dịch vụ managed, còn phải đọc **tài liệu chính thức của nhà cung cấp**: khả năng sửa **cassandra.yaml**, phạm vi hỗ trợ JDK/driver, snapshot, backup và lịch rolling upgrade có thể khác bản Apache Cassandra tự quản lý.

### 2.2. Tránh nhầm giữa bốn loại “phiên bản”

- **Server Cassandra:** phiên bản chạy trên các node; bản minor/major/patch đều có ý nghĩa khi xem lỗi và tương thích.
- **JDK/JVM:** runtime của server; được ràng buộc bởi phiên bản Cassandra và cách đóng gói.
- **Driver Java:** thư viện client kết nối qua native protocol; có vòng đời và release note **riêng** với server.
- **SSTable/tooling:** định dạng tệp và công cụ nạp, backup, repair có thể thay đổi theo phiên bản; cần kiểm chứng với dữ liệu thực.

Ví dụ một cluster Cassandra mới vẫn có thể phục vụ một driver cũ trong **phạm vi giao thức được hỗ trợ**, nhưng điều đó không chứng minh mọi tính năng, codec, retry policy hay xử lý metadata của driver đều an toàn. Phải đối chiếu **server ↔ native protocol ↔ driver ↔ JDK của ứng dụng**.

## 3. Chốt chính xác phiên bản nguồn và đích

Trước khi tìm mục “What's New”, lập một phiếu bối cảnh:

~~~text
Cluster:             <cluster-id>
Bản phân phối:       Apache Cassandra / vendor / managed service
Cassandra nguồn:     <major.minor.patch + build>
Cassandra đích:      <major.minor.patch + build>
JDK server nguồn:    <distribution + version>
JDK server đích:     <distribution + version được hỗ trợ>
Driver Java:         <artifact + version>
JDK ứng dụng:        <version>
DC / rack / RF:      <mô hình thực tế>
OS / container:      <môi trường>
SSTable:             <format hiện tại, nếu biết>
Backup/repair tools: <tên + phiên bản>
Ngày thu thập:       <UTC timestamp>
~~~

Các giá trị này phải lấy từ **cluster đang chạy và bản build sẽ triển khai**. Không lấy phiên bản ghi trong tài liệu nội bộ cách đây vài tháng làm sự thật nếu node đã được vá. Một cluster cũng có thể đang **mixed-version** sau lần bảo trì trước; phải thống kê **từng node**.

### 3.1. Lệnh quan sát an toàn

Trên cluster và thiết bị đã được cấp quyền:

~~~bash
# Trạng thái node trong cluster, datacenter và token/rack tổng quan.
nodetool status

# Thông tin của node, bao gồm phiên bản Cassandra khi phiên bản hỗ trợ.
nodetool info

# Cấu trúc cluster/schema theo khả năng cqlsh của bản đang dùng.
cqlsh
~~~

Trong **cqlsh**:

~~~sql
-- Truy vấn cục bộ: trả phiên bản server mà kết nối đang truy cập.
SELECT release_version, schema_version
FROM system.local;

-- Kiểm tra metadata keyspace đang dùng.
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'shop';
~~~

**system.local** phản ánh node được kết nối, không tự đại diện cho mọi node. Cần thu thập phiên bản và trạng thái của **từng node** bằng công cụ/metric phù hợp. Việc truy vấn bảng hệ thống có thể khác trong một số bản triển khai; hãy xác minh schema hệ thống của phiên bản đang chạy.

Nếu cấu hình được sinh bởi Helm, Ansible, container image hoặc managed service, hãy ghi cả **manifest triển khai và cấu hình hiệu lực sau khi start**, vì file trên Git không luôn giống giá trị runtime.

### 3.2. Đọc toàn bộ chặng, không chỉ hai điểm đầu-cuối

Giả sử kế hoạch được tài liệu chính thức cho phép đi theo đường:

~~~text
Phiên bản A  ->  Phiên bản B  ->  Phiên bản C
     \______________________________/
              mục tiêu cuối
~~~

Phải đọc các thay đổi **A → B**, **B → C** và mọi bản vá liên quan. Một tính năng bị **deprecated** ở B rồi **removed** ở C có thể không xuất hiện rõ trong phần tính năng mới của C.

Cần xác nhận:

1. **Đường nâng cấp trực tiếp có được hỗ trợ không?** Nếu không, những chặng bắt buộc là gì?
2. **Mixed-version window** được cho phép trong bao lâu, cùng điều kiện CQL/schema và chức năng có thể sử dụng?
3. **Thứ tự thao tác trên từng node** và công việc hậu nâng cấp có được ràng buộc không?
4. Có yêu cầu **nâng driver hoặc JDK trước/sau server** không?
5. Định dạng SSTable và giao thức giữa node có cho phép **downgrade/rollback** hay không?

Đừng tự tạo đường nâng cấp bằng giả định “bản mới hơn luôn tương thích”.

## 4. Phân loại thay đổi để biết hành động cần làm

### 4.1. Sáu nhóm quan trọng

| Nhóm | Ý nghĩa thực tế | Hành động cần làm |
|---|---|---|
| **Deprecated** | Tính năng/tham số còn có thể hoạt động trong một số phiên bản nhưng dự kiến bị loại bỏ | Xác định nơi sử dụng, lập lịch thay thế, theo dõi mốc loại bỏ |
| **Removed** | Phiên bản đích không còn hỗ trợ cơ chế cũ | Chuyển đổi **trước** khi deploy; fail gate nếu còn phụ thuộc |
| **Renamed / moved** | Tên tham số, vị trí cấu hình hoặc giao diện đổi | Chuyển key/location, bỏ key cũ, kiểm tra runtime |
| **Default changed** | Không sửa config vẫn làm hành vi khác | Ghi lại mặc định nguồn/đích; quyết định đặt giá trị tường minh hoặc chấp nhận |
| **Behavior / semantic changed** | Hành vi CQL, API, timeout, repair, compaction hoặc security đổi | Kiểm thử theo hành vi và failure case, không chỉ startup |
| **Known issue / limitation** | Bản đích có lỗi đã biết hoặc đường nâng cấp bị hạn chế | Đánh giá ảnh hưởng, chọn bản vá/workaround hoặc hoãn |

Một mục phát hành cũng có thể là **performance improvement**, **bug fix** hay **new feature**. Những mục đó vẫn cần được rà soát nếu ứng dụng từng dựa vào hành vi lỗi cũ, dùng API nội bộ hoặc có SLA latency nghiêm ngặt.

### 4.2. Deprecated chưa phải removed

**Deprecated** là một tín hiệu chuyển đổi có kế hoạch, **không phải cam kết** rằng tính năng vẫn chạy ở mọi phiên bản tiếp theo. **Removed** là điều kiện phải sửa trước khi nâng cấp đến phiên bản loại bỏ.

Ví dụ giả định, chỉ để tập cách đọc:

> “Option **old_mode** deprecated in A; removed in B. Use **new_mode** instead.”

Hành động đúng:

1. Tìm mọi nơi tham chiếu **old_mode**: file cấu hình, IaC, env, script, command line, tài liệu dựng node.
2. Kiểm tra **new_mode** có cùng kiểu dữ liệu và ngữ nghĩa không.
3. Sửa triển khai **trước** khi node chạy phiên bản B; kiểm tra startup, log và giá trị hiệu lực.
4. Xác nhận không còn code hay script phụ thuộc vào option cũ.

**old_mode/new_mode là tên giả lập, không phải tham số thật của Cassandra.** Khi áp dụng thực tế, chỉ dùng tên đúng từ tài liệu chính thức của phiên bản đích.

### 4.3. Default changed thường khó nhận thấy nhất

Giả sử **tham số P** được bỏ khỏi file vì cluster đang dùng mặc định của phiên bản cũ. Khi nâng cấp, mặc định mới của P khác:

| Trước nâng cấp | Sau nâng cấp | Điều quan trọng |
|---|---|---|
| P không ghi trong config, mặc định là X | P không ghi trong config, mặc định là Y | Hành vi tự đổi dù Git diff không đổi |
| P được đặt tường minh thành X | P giữ giá trị X nếu còn hợp lệ | Có thể giữ hành vi cũ, nhưng phải xác minh hỗ trợ |
| P đã bị đổi tên hoặc loại bỏ | Còn key cũ trong file | Có thể startup lỗi, warning hoặc không còn tác dụng tùy phiên bản |

**So sánh hai bản cassandra.yaml không đủ**; phải so cả **default source, default target và giá trị thực tế được nạp**. Không nên copy nguyên một file config cũ sang binary mới vì có thể giữ key lỗi thời hoặc thiếu mục mới cần cấu hình.

## 5. Trích xuất thay đổi thành ma trận có thể kiểm thử

Trong review release note, mỗi phát hiện nên thành **một dòng có thể giao việc**:

| Trường | Câu hỏi phải trả lời |
|---|---|
| **Nguồn tài liệu** | Release note/upgrade guide phiên bản nào, mục/đường dẫn nào, ngày xem? |
| **Loại thay đổi** | Deprecated, removed, renamed, default, semantic, known issue? |
| **Thành phần** | CQL/schema, driver, JVM, cassandra.yaml, nodetool, storage, backup, bảo mật? |
| **Đang dùng?** | Có bằng chứng từ config/schema/log/code/metrics không? |
| **Ảnh hưởng** | Startup fail, sai dữ liệu, latency, availability, security, compatibility? |
| **Hành động** | Sửa gì, ở đâu, trước hay sau nâng cấp? |
| **Owner** | DBA/SRE, Java team, security, nền tảng hoặc vendor? |
| **Kiểm thử** | Lệnh/fixture và kết quả mong đợi cụ thể? |
| **Rollback/stop gate** | Dừng khi nào; nếu đã đổi định dạng dữ liệu thì quay lui thế nào? |

Ví dụ **giả lập** về cách viết phiếu, không khẳng định đây là thay đổi thật ở bất kỳ bản Cassandra nào:

~~~yaml
change_id: "COMPAT-EXAMPLE-001"
source_document: "<official-upgrade-guide-url-and-section>"
from_version: "<source>"
to_version: "<target>"
classification: "default_changed"
component: "server-config"
config_key: "<documented-key>"
old_effective_value: "<measured>"
new_default_value: "<from-target-doc>"
used_by_cluster: true
risk: "request-latency"
action: "decide explicit value; update deployment template"
owner: "database-platform"
validation:
  - "record effective value after startup"
  - "measure p95/p99 at representative load"
stop_gate: "latency regression exceeds agreed threshold"
status: "open"
~~~

Không để **used_by_cluster: false** chỉ vì không tìm thấy key trong Git; tính năng có thể đang chạy nhờ mặc định, tham số từ môi trường hoặc cấu hình được sinh lúc start.

### 5.1. Đặt mức ưu tiên theo ảnh hưởng

- **P0 — block upgrade:** có tính năng bị removed mà workload cần; đường nâng cấp không được hỗ trợ; thiếu bản backup/rollback có thể tin cậy; lỗi an toàn dữ liệu hoặc lỗ hổng bảo mật nghiêm trọng chưa có biện pháp.
- **P1 — phải sửa và kiểm thử trước rollout:** mặc định đổi ảnh hưởng throughput/latency/CL, config mất hiệu lực, driver/TLS không kết nối, repair/backup không vận hành.
- **P2 — kiểm chứng vận hành:** cảnh báo mới, câu lệnh quản trị đổi cú pháp, metric/dashboard đổi tên, script cần cập nhật.
- **P3 — thông tin theo dõi:** tính năng mới chưa dùng, deprecated có thời gian chuyển đổi nhưng không bị loại bỏ ở phiên bản đích.

Ưu tiên là quyết định theo hệ thống đang vận hành, không chỉ theo tiêu đề “Critical” hay “Minor” của tài liệu.

## 6. Rà soát các vùng tương thích đặc thù của Cassandra

### 6.1. CQL, schema và thiết kế bảng theo truy vấn

Cassandra là database wide-column: **partition key** quyết định phạm vi dữ liệu và replica; **clustering columns** quyết định cách sắp xếp trong partition. Một thay đổi parser/CQL, collection, index, UDT hoặc hành vi truy vấn có thể ảnh hưởng tính đúng đắn và latency.

Khi đọc release note, tìm các cụm:

- **CQL syntax**, prepared statements, bind markers, collection/UDT, timestamp, TTL và tombstone;
- Secondary index, materialized view hoặc tính năng tìm kiếm/index mà hệ thống **thực sự đang dùng**;
- Schema agreement, migration metadata, giới hạn/guardrails mới;
- Thay đổi cơ chế xử lý query, paging, read repair, timeout hoặc exception behavior.

Dùng một truy vấn theo partition key làm fixture:

~~~sql
CREATE TABLE IF NOT EXISTS shop.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);

SELECT happened_at, event_id, event_type
FROM shop.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;
~~~

**shop** phải tồn tại với replication phù hợp trước khi tạo bảng; đoạn trên là ví dụ schema/truy vấn, không phải toàn bộ script dựng cluster. Khi kiểm thử thực tế, cần kiểm tra query trả **đúng hàng, thứ tự, kiểu dữ liệu, paging và latency** trước/sau. Prepared statement không bảo đảm một truy vấn thiếu partition key sẽ được định tuyến tối ưu.

Nếu bản mới thêm guardrail hoặc thay hạn chế truy vấn, một câu CQL trước đây chỉ cảnh báo có thể bị từ chối; hãy kiểm tra **log và lỗi thực thi** trên staging đại diện.

### 6.2. Replication, topology và mức nhất quán

Một nâng cấp node không làm thay đổi **replication factor** của keyspace chỉ vì phiên bản binary khác, nhưng các cơ chế liên quan có thể ảnh hưởng hành vi vận hành:

- Topology/rack/snitch và metadata node có còn được đọc nhất quán?
- Phần mềm có giới hạn mixed-version và giao thức internode cụ thể?
- Hints, streaming, node replace/bootstrap, read repair và repair có hướng dẫn chuyển đổi?
- Consistency level **ONE, LOCAL_QUORUM, EACH_QUORUM, ALL** có được dùng đúng ngữ cảnh datacenter?
- Khi một node dừng để nâng cấp, còn đủ replica để đáp ứng CL của ứng dụng không?

Ví dụ RF = 3 ở một datacenter, **LOCAL_QUORUM** cần đa số **2** replica xác nhận theo ngữ nghĩa request. Nếu các replica còn lại đã lỗi trước khi dừng một node, rollout có thể khiến truy vấn không đủ replica hoặc tăng timeout. Vì vậy, nâng cấp phải dựa trên **trạng thái thực của cluster**, không dựa vào dự đoán “RF 3 chắc chắn chịu được dừng bất kỳ node nào”.

### 6.3. SSTable, commitlog, compaction và repair

Đọc release note để xác định:

| Thành phần | Câu hỏi cần hỏi |
|---|---|
| **SSTable format** | Binary mới có đọc được tệp cũ không? Khi ghi định dạng mới thì binary cũ còn đọc được không? |
| **Commitlog / recovery** | Có thay định dạng, cơ chế replay hoặc giới hạn liên quan không? |
| **Compaction strategy** | Có đổi tham số, hành vi, cảnh báo, yêu cầu disk headroom hay bước hậu nâng cấp không? |
| **Repair** | Công cụ/cú pháp/hành vi anti-entropy và phiên bản mixed-node có tương thích không? |
| **Streaming / bootstrap** | Node phiên bản khác có thể trao đổi dữ liệu trong giai đoạn được hỗ trợ không? |
| **Backup / restore** | Snapshot, incremental backup, sstableloader hoặc công cụ bên thứ ba có hỗ trợ định dạng mới không? |

Ví dụ một release note có thể yêu cầu công việc hậu nâng cấp như **chuyển SSTable cũ sang định dạng mới**. Trong các phiên bản có lệnh **nodetool upgradesstables**, lệnh này có thể tạo I/O và cần dung lượng đĩa đáng kể. **Không chạy máy móc**: phải xác nhận lệnh, options, thứ tự, điều kiện, thời gian bảo trì và khả năng quay lui **của đúng bản Cassandra**.

Một khi dữ liệu hoặc metadata đã ghi ở định dạng không được binary cũ hỗ trợ, “rollback” bằng cách cài lại package cũ có thể làm node không khởi động hoặc không đọc được tệp. Hướng phục hồi phải được xác định **trước** thao tác có khả năng không đảo ngược.

### 6.4. Java/JVM, bộ nhớ và hiệu năng

Thay phiên bản Cassandra có thể kéo theo phạm vi JDK/GC khác. Review các mục:

- JDK được hỗ trợ, yêu cầu runtime của bản phân phối và hệ điều hành;
- JVM flags bị loại bỏ/không còn hiệu lực; collector được khuyến nghị;
- Heap/off-heap, direct buffers, memtable/cache và page cache;
- Thread pool, scheduler, concurrency, connection/timeouts và guardrails;
- Default metrics, log format, GC logs và khả năng quan sát.

**-Xmx không giới hạn toàn bộ RAM tiến trình.** Một thay đổi mặc định khiến bộ nhớ native, số kết nối hoặc compaction tăng có thể đẩy container tới OOM dù heap không đầy. Kiểm chứng phải nhìn **heap, GC, RSS/cgroup, MemAvailable, disk I/O và p95/p99** cùng lúc.

Dùng **JDK server phù hợp chính thức**; không sao chép nguyên JVM flags từ một major JDK cũ sang JDK mới rồi bỏ qua warning.

### 6.5. Bảo mật, quyền truy cập và TLS

Release note có thể chứa thay đổi về:

- Authenticator/authorizer, role/permission, hành vi truy cập CQL;
- Client-to-node và internode TLS, cipher/protocol/certificate;
- JMX/management endpoint và công cụ quản trị;
- Audit log, security defaults và thư viện phụ thuộc;
- Quyền đọc backup, mã hóa và tích hợp KMS của bản phân phối.

Sau nâng cấp, ứng dụng Java phải kiểm tra **xác thực, TLS certificate validation và quyền tối thiểu**. Không khắc phục lỗi kết nối bằng cách tạm tắt authentication/TLS trên production để “nâng cấp cho xong”.

### 6.6. Công cụ vận hành và observability

Sửa hoặc kiểm tra lại script gọi **nodetool**, lệnh cqlsh, export/restore, backup scheduler, metric scraper, alert và dashboard. Một node có thể báo **UN** trong nodetool status nhưng các công cụ backup/repair/driver chưa tương thích. Hãy coi công cụ vận hành là một phần của sản phẩm cần nâng cấp và kiểm thử, không chỉ là tiện ích đi kèm.

## 7. Rà soát cấu hình: giá trị khai báo, mặc định và hiệu lực

### 7.1. Đừng bê nguyên cassandra.yaml từ bản cũ

Cấu hình có thể đến từ nhiều nguồn: **cassandra.yaml, cassandra-env.sh, JVM options, environment variables, templating/Helm, flags của dịch vụ hoặc managed API**. Trước khi thay:

1. **Lập inventory** mọi nguồn cấu hình của node hiện tại; lưu bản đã xử lý secret.
2. **Lấy config reference phiên bản đích** và hướng dẫn migration.
3. **Đánh dấu key removed/renamed/type changed**. Không giữ key chỉ vì parser có thể bỏ qua hoặc cảnh báo.
4. **Đối chiếu default** cho cả key có giá trị tường minh lẫn key bị bỏ trống.
5. **Sinh template mới dựa trên phiên bản đích**, đưa vào những giá trị có chủ đích; review riêng tham số về bảo mật/replication/timeout/repair.
6. **Start node staging** để xem startup log, warning, effective configuration và hành vi thực tế.
7. **Thử lại trên rollout canary**; giữ config snapshot/manifest để điều tra.

Đừng ghi password, private key, access token hoặc URI có chữ ký vào bảng diff hay report.

### 7.2. Checklist phân nhóm cấu hình

Những nhóm sau thường đáng rà soát khi so sánh **tài liệu phiên bản nguồn và đích**; đây là nhóm ví dụ, **không khẳng định mọi tên key xuất hiện ở mọi bản**:

| Nhóm | Ví dụ nội dung cần tra | Tác động có thể thấy |
|---|---|---|
| Identity / network | Cluster name, listen/broadcast address, seed discovery, native transport | Node không join hoặc driver không kết nối |
| Topology / replication | DC/rack/snitch, RF và metadata cluster | Replica không phân bố như mong muốn |
| Security | Authenticator, authorizer, client/internode encryption | Login fail, quyền sai, TLS mismatch |
| Disk / commitlog | Data directories, commitlog location/segment/flush, disk thresholds | Disk pressure, data path/commitlog lỗi |
| Memtable / cache | Heap, off-heap, cache budgets | GC, OOM, page cache thiếu |
| Request / guardrail | Timeout, giới hạn batch/mutation/partition, CQL guardrails | Câu lệnh bắt đầu bị reject hoặc chậm |
| Compaction / streaming | Throughput, concurrency, maintenance tools | Backlog, I/O tăng trong rollout |
| Logging / metrics | Loggers, metrics/JMX, tracing | Không quan sát được hoặc lộ dữ liệu nhạy cảm |

**RF và consistency level không phải cùng một tham số:** RF thuộc replication strategy của **keyspace**; CL thường chọn theo request/client. Cần kiểm tra **CQL keyspace metadata và ứng dụng Java** cùng với file cấu hình server.

### 7.3. Bảng đối chiếu ví dụ

Giả sử có ba tham số **giả lập**:

| Key giả lập | Bản nguồn | Bản đích | Cách xử lý |
|---|---|---|---|
| **alpha_timeout** | Chấp nhận đơn vị ms | Chấp nhận đơn vị s | Chuyển đúng đơn vị sau khi xác minh tài liệu, kiểm tra timeout runtime |
| **legacy_cache_mode** | Deprecated | Removed | Loại bỏ key, chuyển sang cơ chế được hỗ trợ |
| **beta_limit** | Mặc định 100 | Mặc định 50 | Quyết định đặt tường minh hay chấp nhận mặc định mới, đo workload |

Những tên trên **không phải tên cấu hình thật của Cassandra**. Ví dụ nhấn mạnh cách suy nghĩ: chỉ thay chữ trong file có thể khiến timeout từ 5.000 ms thành 5.000 s nếu thay đổi đơn vị mà không được phát hiện.

## 8. Đọc một release note theo quy trình năm lượt

Cách làm này giảm nguy cơ bỏ sót các thay đổi nằm ở phần khác nhau của tài liệu.

### Lượt 1 — Ranh giới tương thích

Đọc **Supported upgrade paths**, prerequisites, JDK, driver, OS, compatibility, mixed-version limitations và known issues. Trước khi tiếp tục, phải biết phiên bản đích **có thể nâng lên an toàn từ nguồn** theo đường nào.

### Lượt 2 — Các thay đổi phá vỡ hoạt động

Tìm **breaking, removed, incompatible, no longer supported, deprecated, requires migration, cannot downgrade**. Đối chiếu với config/script/schema/Java code. Những mục này có thể chặn kế hoạch.

### Lượt 3 — Mặc định và hành vi âm thầm thay đổi

Tìm **default, timeout, guardrail, warning, compaction, concurrency, memory, TLS, authentication, protocol, consistency, paging**. Bất kỳ thứ gì ứng dụng đang phụ thuộc vào **giá trị mặc định** đều cần kiểm chứng.

### Lượt 4 — Lỗi được sửa và lỗi còn tồn tại

Tìm các bug fix ảnh hưởng dữ liệu/repair/streaming/timeout/GC và phần **known issues** của bản đích. Một lỗi đã sửa có thể thay kết quả so với hành vi trước, hoặc một bản patch sau đó có thể khắc phục regression. Chọn **bản đích cuối** theo mức ổn định thực tế và chính sách hỗ trợ.

### Lượt 5 — Chuyển thành kế hoạch kiểm thử

Không kết thúc ở “đã đọc release notes”. Mỗi mục liên quan phải có **bằng chứng hệ thống có/không sử dụng, owner, phép thử và tiêu chí pass/fail**. Nếu chưa xác minh được, ghi **UNKNOWN** chứ không tự chuyển thành **NOT APPLICABLE**.

~~~mermaid
flowchart TD
    A["Chốt source/target + bản phân phối"] --> B["Thu release notes, upgrade guide, config reference"]
    B --> C["Đọc ranh giới tương thích"]
    C --> D{"Đường upgrade hợp lệ?"}
    D -->|Không| X["Chặn kế hoạch, chọn đường được hỗ trợ"]
    D -->|Có| E["Rà breaking, removed, defaults, behavior"]
    E --> F["Tìm nơi đang dùng + đánh giá rủi ro"]
    F --> G["Ma trận hành động và kiểm thử"]
    G --> H["Staging và canary"]
    H --> I{"Mọi stop gate đều PASS?"}
    I -->|Không| X
    I -->|Có| J["Rolling upgrade theo runbook phiên bản"]
    J --> K["Kiểm chứng cluster, dữ liệu, app và bảo trì"]
~~~

## 9. Ví dụ thực hành: phân tích một ghi chú phát hành giả định

Giả sử trong tài liệu của một phiên bản **X.Y.Z giả định** có ba dòng sau:

~~~text
[HYPOTHETICAL — không phải release note thật của Cassandra]

1. "The legacy FOO transport setting was removed; configure BAR instead."
2. "The default READ_TIMEOUT policy changed."
3. "The new on-disk format is not readable by the previous major version."
~~~

Cách viết kết quả review:

| Ghi chú giả lập | Câu hỏi | Hành động và phép thử |
|---|---|---|
| FOO removed | Có nơi nào sử dụng FOO? BAR có tương đương không? | Tìm trong deployment/config, chuyển cấu hình; xác nhận node khởi động và app kết nối |
| READ_TIMEOUT default changed | Workload đang dựa default nào? | So trước/sau, kiểm tra Java driver và server timeout, thử query p95/p99/timeout |
| SSTable format không tương thích ngược | Có bước ghi lại/upgrade SSTable không? | Phê duyệt kế hoạch backup/restore, không hứa rollback binary cũ, kiểm thử load/stream |

Nếu ghi chú mang tính **security fix** và có yêu cầu đặt setting mới, phải thêm owner security và phép thử xác thực/TLS/authorization. Nếu yêu cầu **data migration**, phải tính dung lượng đĩa, thời gian và điểm không thể quay lại.

Tính đúng đắn của bài thực hành là **quy trình suy luận và kiểm chứng**, không phải nội dung thay đổi giả lập. Khi làm việc thật, thay X.Y.Z bằng release note chính thức đã xác minh.

## 10. Kiểm chứng Java driver và CQL trước/sau nâng cấp

### 10.1. Checklist phía ứng dụng

- Driver version có nằm trong **compatibility matrix** với Cassandra đích và native protocol không?
- JDK của ứng dụng có còn được driver hỗ trợ?
- Contact points, local datacenter, TLS, authentication và connection pool hoạt động trong cấu hình mới?
- Prepared statement, bind types (**uuid, date, timestamp, collections, UDT**) và paging vẫn đúng?
- Retry/speculative execution có thể khuếch đại lỗi khi node mixed-version hoặc tạm thiếu replica không?
- Read/write consistency level đang dùng có phù hợp với RF/DC và kế hoạch dừng lần lượt từng node?
- Các bảng denormalized theo access pattern có trả đúng dữ liệu, kể cả điều kiện ranh giới partition/time bucket?
- Metrics và log driver có còn đủ để phân biệt **timeout, unavailable, auth/schema/protocol error** không?

### 10.2. Ví dụ smoke test Java driver 4.x

Đoạn sau minh họa **đọc theo partition key**, truy vấn được prepare/bind và thông tin coordinator; không thay thế bộ kiểm thử production. Trước khi chạy, cần có keyspace/table cùng một ít dữ liệu test như mục 6, Java driver phù hợp và cluster test có **dc1** cùng số replica đáp ứng LOCAL_QUORUM.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class CassandraUpgradeSmokeTest {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
                "11111111-1111-4111-8111-111111111111");
        LocalDate day = LocalDate.of(2026, 11, 21);

        // Chỉ trỏ đến cluster thử nghiệm đã kiểm chứng.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM shop.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement request = prepared.bind(tenantId, day, 20)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            ResultSet result = session.execute(request);
            System.out.println(
                "Coordinator: " +
                result.getExecutionInfo().getCoordinator());

            int rows = 0;
            for (Row row : result) {
                // Chỉ đo đếm; xác minh event_id/giá trị qua fixture riêng.
                if (row.getUuid("event_id") == null) {
                    throw new IllegalStateException(
                        "Dữ liệu bất thường: thiếu event_id");
                }
                rows++;
            }
            System.out.println("Rows read: " + rows);
        }
    }
}
~~~

**Giới hạn kiểm thử:**

- Một truy vấn trả **0 hàng** mà không lỗi không chứng minh dữ liệu được giữ nguyên. So sánh **bộ fixture có order/event ID đã biết** và kỳ vọng rõ.
- Khi nâng từ server phiên bản cũ sang mới, phải chạy **cùng bộ kiểm thử** ở bản nguồn, mixed-version (nếu được hỗ trợ) và bản đích sau hoàn tất.
- Driver phải xác thực server certificate/TLS và credentials như môi trường thật; ví dụ tối giản chỉ trình bày truy vấn.
- Kiểm tra p95/p99, error rate và số retry dưới tải đại diện; một smoke test thành công không chứng minh performance.
- Ứng dụng thật nên tái sử dụng **CqlSession** và PreparedStatement; ví dụ main đóng session sau khi chạy một lần chỉ phục vụ thực hành.

## 11. Quy trình nâng cấp có điểm kiểm chứng

### 11.1. Trước rollout

1. **Chốt tài liệu:** release notes, upgrade guide, migration/compatibility, known issues và config reference cho **đúng build**.
2. **Lập ma trận thay đổi:** tất cả mục **removed/renamed/default changed/behavior changed** liên quan, owner, phương án kiểm thử.
3. **Kiểm tra trạng thái cluster:** node health, gossip/schema agreement theo công cụ hỗ trợ, DC/rack/RF, hints, streaming, repair backlog, compaction backlog, disk free, heap/GC.
4. **Xác minh backup:** backup hoàn chỉnh, schema, snapshot/incremental/commitlog theo RPO đã chọn, thử restore độc lập; không coi replica là backup.
5. **Kiểm thử staging:** dùng bản sao schema, workload theo partition key, thao tác đọc/ghi, TTL/tombstone, batch, compaction/repair, failure scenarios và Java driver.
6. **Chốt runbook:** thứ tự node, thời điểm dừng, người chịu trách nhiệm, stop gate, công việc hậu nâng cấp và **điểm không thể đảo ngược**.

### 11.2. Trong rolling upgrade

**Rolling upgrade** thay các node theo thứ tự và giới hạn mà **upgrade guide của phiên bản** cho phép. Không tự kết luận mọi cặp phiên bản đều chạy mixed-version được.

Ở mỗi node hoặc mỗi đợt được phép:

- Xác minh replica còn lại đủ phục vụ CL và không có sự cố nền.
- Đưa node ra bảo trì, thay binary/config/JDK theo runbook chính thức.
- Khởi động, xem log warning/error, kiểm tra phiên bản và trạng thái node.
- Theo dõi schema agreement, client errors, read/write latency, GC, disk I/O, compaction/streaming/hints.
- Chỉ nâng node kế tiếp khi **các điều kiện nghiệm thu của đợt trước đạt**.
- Không vội thực hiện một bước chuyển đổi SSTable được tài liệu coi là **hậu nâng cấp** trong giai đoạn còn mixed-version.

Nếu node không join, CQL bind lỗi, timeout tăng quá ngưỡng hoặc không đủ replica, **dừng rollout** và điều tra theo phương án đã được chuẩn bị. Không tự tắt security hoặc consistency checks để tiếp tục.

### 11.3. Sau rollout

- Xác minh **mọi node** chạy bản đích và topology đúng; thống kê không còn bản binary cũ ngoài dự kiến.
- Kiểm tra schema, read/write theo CL mục tiêu, consistency trên các partition mẫu và hoạt động của Java driver.
- Đối chiếu latency p50/p95/p99, throughput, error/retry, GC/heap/native/RSS, disk, compaction/repair, pending tasks với baseline.
- Thực hiện **post-upgrade actions** chỉ khi được tài liệu yêu cầu, theo thứ tự và giới hạn đã chấp thuận.
- Kiểm thử snapshot, backup upload/restore, repair, nodetool, metric scraper và cảnh báo.
- Cập nhật runbook, cấu hình, SBOM/inventory, dashboard và tài liệu nội bộ theo các thay đổi đã chứng minh.

## 12. Rollback và phục hồi: đừng đánh đồng

### 12.1. Binary rollback có thể bị giới hạn

**Rollback** thường được hiểu là trả node/cluster về phiên bản binary/config trước đó. Nhưng một số thay đổi **định dạng dữ liệu, metadata, schema hoặc cơ chế đồng bộ** có thể không tương thích ngược. Trong trường hợp đó, downgrade trực tiếp không an toàn.

Cần phân biệt:

| Tình huống | Hướng xử lý khả dĩ |
|---|---|
| Chưa đổi dữ liệu/metadata, tài liệu cho phép quay lui | Thực hiện rollback theo đúng thủ tục hỗ trợ, kiểm chứng node/app |
| Đã đổi định dạng SSTable hay schema không tương thích | Không tự cài binary cũ; đánh giá phục hồi từ backup vào môi trường tương thích |
| Ứng dụng Java lỗi nhưng server chạy ổn | Có thể rollback riêng ứng dụng/driver nếu vẫn tương thích với server đích |
| Config mới sai hoặc key bị removed | Sửa config theo bản đích hoặc quay lại theo đường được hỗ trợ; kiểm tra startup và CL |
| Có dữ liệu ghi mới trong lúc nâng cấp | Xác định recovery point, cách bảo tồn ghi hợp lệ và hòa giải dữ liệu khi restore |

**Không hứa RPO = 0 chỉ vì có snapshot.** Snapshot là điểm dữ liệu tại mốc; phải tính các ghi xác nhận sau snapshot và quy trình incremental/commitlog archive nếu có. Nếu khôi phục một backup cũ vào cluster mới, phải kiểm tra TTL/tombstone và dữ liệu đã xóa đúng nghiệp vụ để tránh hồi sinh dữ liệu không mong muốn.

### 12.2. Điểm dừng bắt buộc

Những dấu hiệu nên chặn rollout:

- Đường nâng cấp hoặc mixed-version hiện tại **không được hỗ trợ**.
- Không có backup sạch, hoàn chỉnh và khả năng restore đã kiểm chứng theo yêu cầu RPO/RTO.
- Node còn lại không đủ replica để đáp ứng mức nhất quán dịch vụ.
- Startup cảnh báo tham số removed/unsupported mà chưa biết ảnh hưởng.
- Schema agreement, CQL read/write, authentication/TLS hoặc Java driver kiểm thử thất bại.
- Timeout, unavailable, dữ liệu sai, GC/OOM, disk full hoặc latency vượt ngưỡng đã chốt.
- Bước hậu nâng cấp có thể ghi định dạng không tương thích khi phương án phục hồi chưa sẵn sàng.

## 13. Đọc release note dưới góc độ vận hành thực tế

Một số thay đổi nghe nhỏ nhưng có thể tác động gián tiếp:

### 13.1. Timeout mới và truy vấn phân tán

Cassandra tính token từ partition key và driver có thể thực hiện **token-aware routing** khi statement bind đủ khóa. Nếu mặc định timeout hoặc retry thay đổi, truy vấn trải nhiều phân vùng hoặc partition lớn sẽ dễ lộ vấn đề hơn. Đo **latency riêng theo query shape** và kiểm tra thiết kế bảng trước khi nâng các giới hạn vô điều kiện.

### 13.2. Compaction / repair và dung lượng đĩa

Một thay đổi liên quan compaction có thể tạo lượng I/O lớn khi dữ liệu đã nhiều SSTable. Tính **disk headroom**, lịch repair, kích thước partition/tombstone và thời gian maintenance. Tăng concurrency có thể giảm thời gian một tác vụ nhưng lại đẩy latency truy vấn lên cao nếu thiếu I/O.

### 13.3. Security defaults và lỗi kết nối Java

Một thay đổi TLS/cipher/auth mặc định có thể khiến client cũ không handshake. Kiểm tra bằng driver/config tương thích và cơ chế cấp certificate đúng. **Không giải quyết bằng cách tắt xác thực hostname hoặc chấp nhận mọi chứng chỉ**.

### 13.4. Backup tool hỗ trợ định dạng mới

Ngay cả khi node mới trả SELECT tốt, công cụ backup cũ có thể không hiểu metadata/SSTable mới hoặc restore không thành công. Phải có **ít nhất một lần restore rehearsal vào cluster cô lập** tương thích bản đích; đánh dấu backup là có thể dùng khi checksum/schema/dữ liệu và ứng dụng đều kiểm chứng được.

## 14. Mẫu báo cáo đánh giá release note

Những mục tối thiểu của một báo cáo trình duyệt nâng cấp:

~~~markdown
# Cassandra upgrade readiness — <cluster> / <source> -> <target>

**Tài liệu kiểm tra:** <release notes, upgrade guide, migration guide,
config reference, driver/JDK matrix, known issues, thời điểm đọc>

**Phạm vi:** <DC, số node, RF, application/driver, backup/tooling>

**Đường nâng cấp được hỗ trợ:** <các chặng và điều kiện>
**Mixed-version plan:** <điều kiện được phép, thời hạn, stop gates>

| ID | Loại thay đổi | Đang dùng? | Rủi ro | Owner | Bằng chứng | Trạng thái |
|----|---------------|------------|--------|-------|------------|------------|
| 01 | removed       | yes/no/?   | ...    | ...   | ...        | OPEN/PASS |
| 02 | default       | yes/no/?   | ...    | ...   | ...        | OPEN/PASS |
| 03 | behavior      | yes/no/?   | ...    | ...   | ...        | OPEN/PASS |

**Baseline:** <p95/p99, throughput, error/retry, GC, I/O, repair>
**Backup/restore:** <backup ID, recovery point, restore drill result>
**CQL/Java tests:** <fixture, CL, schema, paging, driver/TLS>
**Post-upgrade actions:** <lệnh/tác động/điều kiện thực hiện>

**Rollback feasibility:** <được hỗ trợ đến mốc nào>
**Recovery alternative:** <backup và RPO/RTO chấp nhận>
**Go/No-Go:** <decision + người phê duyệt + thời điểm>
~~~

Template chỉ nêu cấu trúc báo cáo; giá trị thực phải điền từ cluster và tài liệu đã xác minh. Nếu một mục không có nguồn hoặc bằng chứng, ghi **UNKNOWN** và phân công xác minh; tránh đánh dấu PASS theo cảm tính.

## 15. Bài tập thực hành

### Bài 1 — Deprecated khác Removed thế nào?

Release note giả lập ghi: “Tham số **P** deprecated ở phiên bản A, removed ở phiên bản C; phiên bản B vẫn hỗ trợ có cảnh báo.” Cluster hiện dùng A và định nâng thẳng C.

**Câu hỏi:** Đội vận hành cần làm gì trước khi deploy C? Có thể chỉ bỏ dòng P mà không kiểm tra default không?

**Gợi ý:** Tìm mọi nơi dùng P, chuyển sang cơ chế mới, kiểm tra đường nâng cấp A → C có được hỗ trợ và so mặc định/hành vi. Bỏ P nhưng không hiểu tác động có thể làm thay đổi vận hành âm thầm.

### Bài 2 — Tham số không có trong file

Một tính năng dựa vào timeout mặc định. Ở bản nguồn timeout = 1.000 ms; giả sử bản đích timeout = 500 ms. File cấu hình không ghi tham số này.

**Câu hỏi:** Vì sao Git diff = 0 không chứng minh không có thay đổi? Kiểm thử nào cần thiết?

**Gợi ý:** Mặc định thuộc binary/config reference, không thuộc Git. So giá trị hiệu lực và đo p95/p99, timeout/retry trên query representative.

### Bài 3 — Java test chạy nhưng sai dữ liệu

Sau nâng cấp, smoke test chỉ gọi **SELECT...LIMIT 10** và kết quả không có exception, nhưng không kiểm tra các event ID dự kiến.

**Câu hỏi:** Test này thiếu gì?

**Gợi ý:** Có thể trả 0 hàng hoặc sai tập hàng mà vẫn thành công. Cần bộ fixture xác định, so giá trị/order/paging, nhiều partition token range, CL và failure case.

### Bài 4 — Nâng cấp node khi RF = 3

Một datacenter RF = 3 có hai node không ổn định, ứng dụng dùng LOCAL_QUORUM. Người vận hành muốn dừng thêm một node để nâng cấp.

**Câu hỏi:** Có nên làm ngay không? Vì sao?

**Gợi ý:** Không; phải kiểm tra số replica sẵn sàng theo từng partition và CL. RF chỉ là số bản sao cấu hình, không bảo đảm có đủ replica sống/khỏe trong lúc maintenance.

### Bài 5 — “Rollback chỉ cần cài binary cũ”

Upgrade guide của bản đích yêu cầu chuyển SSTable sang format mà phiên bản cũ không đọc được. Đội vận hành vẫn viết rollback là “reinstall phiên bản cũ”.

**Câu hỏi:** Điều gì sai? Cần bổ sung những bước chuẩn bị nào?

**Gợi ý:** Có điểm không tương thích ngược; phải xác định thủ tục rollback có được hỗ trợ không, giữ backup sạch, thử restore và đo RPO/RTO, tránh thực hiện chuyển đổi không thể quay lại khi chưa có kế hoạch.

### Bài 6 — Chọn nguồn tài liệu phù hợp

Hệ thống chạy một bản phân phối Cassandra được vendor tùy biến, app dùng Java driver riêng, và backup bằng công cụ của bên thứ ba. Một kỹ sư chỉ đọc release notes của Apache Cassandra server.

**Câu hỏi:** Thiếu những nguồn nào và nguy cơ gì?

**Gợi ý:** Tài liệu vendor/managed, driver/JDK compatibility, backup tool, known issues/security advisories, upgrade/migration guide và config reference. Nguy cơ unsupported path, driver lỗi, backup/restore thất bại và thiếu hướng xử lý.

## 16. Checklist trước khi duyệt kế hoạch nâng cấp

- [ ] Đã ghi **phiên bản thực tế của từng node**, build/bản phân phối, JDK server, OS, driver Java và công cụ vận hành.
- [ ] Đã kiểm tra **đường nâng cấp được hỗ trợ**, các chặng trung gian và mixed-version limitations.
- [ ] Đã đọc **release notes, upgrade guide, migration/breaking changes, known issues, security advisories** phù hợp.
- [ ] Tất cả mục **deprecated/removed/renamed/default changed/behavior changed** đã có owner và trạng thái.
- [ ] Đã đối chiếu cấu hình khai báo, cấu hình sinh tự động, **default** và **giá trị hiệu lực**; không mang nguyên config cũ sang.
- [ ] Schema, CQL, partition key, collection, TTL, tombstone và các chỉ mục/tính năng đang dùng được kiểm thử.
- [ ] Replication strategy, DC/rack/RF, consistency level và điều kiện dừng từng node được kiểm tra.
- [ ] Cassandra/JDK, Java driver/native protocol và TLS/auth tương thích với môi trường đích.
- [ ] Đã kiểm tra khả năng backup/restore, sửa lỗi và tương thích của SSTable, compaction/repair/streaming.
- [ ] Staging chạy workload đại diện, đối chiếu latency p95/p99, timeout, throughput, GC, disk I/O và memory headroom.
- [ ] Có **backup sạch + restore drill** được xác minh và phương án phục hồi khi binary rollback không an toàn.
- [ ] Runbook có thứ tự node, phép thử, stop gate, người quyết định và công việc hậu nâng cấp.
- [ ] Có kế hoạch cập nhật metrics, dashboard, log, quyền, script nodetool/cqlsh và tài liệu nội bộ.
- [ ] Kết quả Go/No-Go dựa trên **bằng chứng**, không phải chỉ dựa vào việc node khởi động thành công.

## 17. Tổng kết

Đọc release note Cassandra hiệu quả là chuyển **thông tin phiên bản thành hành động có thể xác minh**. Phải bắt đầu từ đường nâng cấp được hỗ trợ và các hệ phụ thuộc, rồi phân loại thay đổi thành **deprecated, removed, renamed, default changed, behavior changed và known issue**. Với từng mục, tìm bằng chứng hệ thống có đang dùng, đánh giá rủi ro và viết phép thử cụ thể.

Cassandra là hệ phân tán wide-column, nên quyết định nâng cấp liên quan tới **partition key, thiết kế bảng theo truy vấn, replication/consistency, SSTable, compaction, repair, backup và ứng dụng Java**. Một cấu hình hợp lệ hay một node báo trạng thái UP chưa đủ: chỉ khi **dữ liệu, truy vấn, khả năng chịu lỗi và phục hồi** được kiểm chứng trên phiên bản đích thì mới có cơ sở tuyên bố nâng cấp tương thích và an toàn.
