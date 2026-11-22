# Sao lưu cấu hình/dữ liệu và diễn tập khôi phục trước thay đổi

## 1. Vấn đề: nâng cấp xong, cluster lên nhưng ứng dụng không đọc được dữ liệu

Một cụm **Apache Cassandra** chạy nhiều năm, phục vụ các truy vấn sự kiện theo thiết bị và khoảng thời gian. Nhóm vận hành chuẩn bị nâng cấp Cassandra/JDK và thay một số tham số `cassandra.yaml`. Trên staging, node vẫn khởi động thành công. Nhưng ở production, sau khi nâng cấp hai node, ứng dụng Java bắt đầu gặp timeout, một số bảng không truy cập được và rollback binary cũ không khởi động như dự kiến.

Khi ấy, các câu hỏi cấp bách là:

- Phiên bản cấu hình cũ, **schema**, RF theo datacenter, snitch, token và danh sách node được lưu ở đâu?
- Có bản **SSTable snapshot** của từng node trước thay đổi hay chỉ một bản trên coordinator?
- Backup đã rời khỏi máy chủ và có **manifest/checksum**, hay chỉ là thư mục hard link trên cùng ổ?
- Nếu nguồn vẫn tiếp tục ghi trong lúc backup, **mốc khôi phục (RPO)** được bảo đảm ở đâu?
- Bản backup có tương thích **phiên bản Cassandra, định dạng SSTable và công cụ restore** mà nhóm định dùng không?
- Có ai đã **khôi phục thử trong môi trường cô lập** và đo thời gian khôi phục (RTO) chưa?

Trong Cassandra, `nodetool snapshot` rất hữu ích nhưng **snapshot không tự động là backup hoàn chỉnh, nhất quán toàn cluster hoặc đã được diễn tập khôi phục**. Một hệ thống sẵn sàng thay đổi phải có **bằng chứng** rằng có thể tái dựng cấu hình, schema, dữ liệu và quyền truy cập ở mức chấp nhận được.

Đây là bài thuộc chương **Nâng cấp và tương thích** của mô-đun Cassandra. Nội dung gắn với cách Cassandra phân phối partition theo token, lưu dữ liệu dưới SSTable, dùng replication/consistency, đồng bộ bằng repair, và cách ứng dụng Java xác minh đường đọc/ghi sau phục hồi.

**Mục tiêu sau bài học:**

1. Phân loại **backup cấu hình, schema, dữ liệu, commit log và backup metadata** theo mục tiêu khôi phục.
2. Phân biệt **snapshot, incremental backup, commit log archiving, logical export và replication**.
3. Xác định những thành phần phải bảo vệ trước nâng cấp, nhất là `system_auth`, topology, khóa mã hóa và cấu hình TLS/JMX.
4. Lập runbook tạo backup **trên đúng từng node**, đưa ra khỏi cluster, kiểm tra checksum/retention và bảo vệ quyền.
5. Diễn tập restore **cô lập**, hiểu rủi ro SSTable format, internode compatibility và schema.
6. Định nghĩa **RPO, RTO, go/no-go, rollback versus restore**, rồi kiểm chứng bằng CQL/Java và metrics trước/sau thay đổi.

> **Phạm vi:** ví dụ dùng Apache Cassandra với full replica, keyspace `NetworkTopologyStrategy` và DC `dc1`. Tên command/option, cách bật incremental backup, định dạng SSTable, commit log archival và đường nâng cấp **phụ thuộc phiên bản/phân phối**. Bài cung cấp quy trình và ví dụ lab, **không phải giấy phép chạy trực tiếp trên production**.

## 2. Ba khái niệm cần chốt trước khi chọn công cụ backup

### 2.1. Backup, snapshot và replication không phải một

| Cơ chế | Bảo vệ trước điều gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| **Replication factor** | Một partition có nhiều natural replica, hỗ trợ chịu lỗi node/DC theo RF và CL. | Không tự chống `DELETE` nhầm được nhân bản, corruption logic, schema bị xóa hoặc ransomware. |
| **Snapshot cục bộ** | Giữ một tập SSTable của **một node/bảng/keyspace** tại mốc chụp. | Không sống sót nếu chính disk/node ấy mất; không tự có snapshot toàn cluster cùng thời điểm. |
| **Backup ngoài cluster** | Lưu bản sao dữ liệu và metadata ở miền lỗi độc lập. | Không chứng minh có thể restore nếu chưa kiểm tra manifest, phiên bản và quyền giải mã. |
| **Incremental backup** | Giữ các SSTable mới được tạo sau một mốc theo cơ chế phiên bản. | Không tự thay base full backup, không phải stream mutation liên tục và không tự có log delete đầy đủ. |
| **Commit log archive / PITR** | Có thể giảm khoảng mất dữ liệu khi khôi phục tới mốc gần sự cố nếu thiết kế đầy đủ. | Không phải cứ copy file commit log đang mở là có thể phát lại an toàn. |
| **Logical export** | Dữ liệu được chuyển thành hàng/record phục vụ import hoặc tái mô hình. | Không mặc định giữ nguyên writetime, TTL, tombstone hay snapshot nhất quán toàn cluster. |

Một cụm RF = 3 có thể phục hồi sau khi một node mất, nhưng nếu người dùng có quyền `TRUNCATE` bảng, cả ba bản sao có thể không còn dữ liệu logic cần thiết. **Replication phục vụ availability/durability; backup phục vụ phục hồi sau những thay đổi hoặc sai sót mà replication không giải quyết được.**

### 2.2. RPO và RTO là yêu cầu, không phải tính năng mặc định

- **RPO (Recovery Point Objective):** chấp nhận mất tối đa bao nhiêu **thời gian dữ liệu** khi khôi phục. Ví dụ RPO 15 phút nghĩa là không được giả định một snapshot từ hôm qua đáp ứng yêu cầu.
- **RTO (Recovery Time Objective):** thời gian cho phép để dịch vụ **trở lại trạng thái phục vụ được**, bao gồm khôi phục node, schema, dữ liệu, quyền, routing và kiểm thử ứng dụng.
- **Độ nhất quán của bản khôi phục:** ứng dụng yêu cầu ảnh chụp tại một thời điểm nguyên tử, hay chấp nhận snapshot phân tán được hòa giải/đối soát?
- **Phạm vi sự cố:** mất một disk/node, một datacenter, toàn cluster, xóa nhầm schema hay upgrade không tương thích?

Ví dụ một ngày có 4 triệu write. Snapshot 24 giờ/lần có thể đủ cho dữ liệu có thể tái tạo, nhưng không đủ cho dữ liệu đơn hàng có RPO 5 phút. Nếu event stream có thể replay toàn bộ mutation với định danh ổn định, chiến lược RPO có thể dựa vào **snapshot + replay có kiểm chứng**; không phải chỉ dựa vào RF.

### 2.3. Mục tiêu khôi phục phải đo được

~~~text
Service             : telemetry-api
Sự cố mục tiêu      : mất một DC hoặc rollback nâng cấp thất bại
RPO kỳ vọng         : <= 15 phút (ví dụ)
RTO kỳ vọng         : <= 120 phút (ví dụ)
Data correctness    : đủ key/value trong phạm vi thời gian đã chốt
Schema/RBAC         : khôi phục được bảng, role và quyền ứng dụng
SLO sau restore     : read p99 và write error rate nằm trong giới hạn duyệt
Evidence            : restore rehearsal + checksum + CQL/Java canary
~~~

Đây là **mẫu yêu cầu**, không phải con số mặc định Cassandra. Nếu chưa có mục tiêu RPO/RTO rõ, nhóm không thể chứng minh quy trình backup “đủ an toàn”.

## 3. Kiểm kê đầy đủ những thứ cần sao lưu trước nâng cấp

Một bản sao của thư mục `data/` **không thể thay thế tất cả các artefact** cần cho một cluster hoạt động đúng.

| Nhóm | Thành phần cần đưa vào kế hoạch | Vì sao quan trọng |
| --- | --- | --- |
| **Schema** | `CREATE KEYSPACE`, `CREATE TABLE`, UDT, index, materialized view, function/aggregate nếu sử dụng; migration history. | Cần khớp định nghĩa bảng với SSTable và ứng dụng. |
| **Dữ liệu** | Snapshot SSTable theo **node**, keyspace/table và mốc; manifest/checksum; incremental sets nếu có. | Phục hồi dữ liệu vật lý trên từng node hoặc nhập lại theo công cụ hỗ trợ. |
| **Auth data** | `system_auth` và chính sách provisioning role/permission, backup được bảo vệ. | Mất auth metadata có thể khiến admin/client không đăng nhập được. |
| **Replication/topology** | `cluster_name`, DC/rack/snitch, RF từng keyspace, seed/contact points, token ownership, host ID, node inventory. | Đặt dữ liệu đúng replica và khôi phục hướng định tuyến. |
| **Cassandra config** | `cassandra.yaml`, `cassandra-env.sh` hoặc cấu hình tương đương, JVM options, compaction/commitlog/timeout, logging, rackdc/snitch config. | Tái dựng hành vi node và so diff trước/sau nâng cấp. |
| **Runtime & package** | Cassandra/JDK version, build/distribution, plugin, Java Driver, OS/image/helm/operator versions. | Kiểm tra đường tương thích và môi trường rollback. |
| **Security material** | TLS certificate chain, truststore/keystore, key IDs, secret references, JMX auth, encryption-at-rest metadata. | Dữ liệu có thể không đọc được hoặc client không thể kết nối nếu thiếu khóa/chứng chỉ. |
| **Backup infrastructure** | Lịch snapshot, điểm đến object storage, IAM, retention, encryption, verification logs. | Có dữ liệu không đồng nghĩa được phép/đủ khả năng khôi phục. |
| **Application contract** | CQL query templates, prepared statements, CL, schema dependency, Java Driver settings và smoke tests. | Cluster có thể “UN” nhưng ứng dụng vẫn lỗi sau upgrade. |
| **Operations history** | Trạng thái repair/streaming, alerts, backup manifest, change ticket, approval, mốc UTC. | Phân biệt lỗi nâng cấp với lỗi có sẵn trước thay đổi. |

### 3.1. Cấu hình cần sao lưu như **đầu vào có version**

Không lấy mỗi tệp `cassandra.yaml` rồi cho rằng đủ. Tùy cách cài đặt, cấu hình có thể nằm trong **ConfigMap/Helm values/operator CRD**, file mount, JVM flags hoặc biến môi trường. Với hệ quản trị cấu hình, phải chốt **commit/image digest** đang chạy trên từng node trước upgrade.

**Không đưa private key, mật khẩu hoặc access token vào file Markdown, Git công khai hoặc ticket**. Manifest chỉ nên chứa **tham chiếu tới secret version**; secret thật nằm trong kho có mã hóa, phân quyền và khả năng khôi phục riêng. Backup secrets phải tuân thủ chính sách rotation, retention và quy trình khẩn cấp.

### 3.2. Tránh hiểu nhầm dữ liệu hệ thống

- `system_schema` thể hiện metadata schema, có thể dùng để kiểm tra; cần lưu **DDL/schema export** độc lập cùng phiên bản.
- `system_auth` là dữ liệu phân tán nhạy cảm, cần RF/backup/restore phù hợp và thử đăng nhập sau khôi phục.
- Các keyspace `system*` khác chứa nhiều loại metadata/trạng thái, **không được mù quáng copy toàn bộ file hệ thống của cluster cũ sang một cluster mới** vì có dữ liệu gắn host ID, token/topology và phiên bản.
- `system_traces` và một số dữ liệu tạm không nhất thiết cần cho RPO nghiệp vụ; phải quyết định theo chính sách thay vì backup tất cả “cho chắc”.

## 4. Snapshot SSTable: nhanh để chụp, khó nếu chưa nghĩ tới restore

### 4.1. Cơ chế cơ bản

Cassandra ghi dữ liệu vào commit log và memtable, sau đó flush thành **SSTable bất biến**. Snapshot thường tạo **hard links hoặc tham chiếu filesystem** tới SSTable trên node, giữ lại những file tại mốc snapshot.

~~~mermaid
flowchart TD
    A["Mutation vào memtable và commit log"] --> B["Flush theo cơ chế snapshot/phiên bản"]
    B --> C["SSTable hiện hành trên node N1"]
    C --> D["Snapshot tag: tham chiếu các SSTable"]
    C --> E["Compaction tạo SSTable mới"]
    D --> F["File cũ vẫn được giữ khi snapshot còn tham chiếu"]
    D --> G["Sao chép ra backup storage độc lập"]
    G --> H["Manifest + checksum + version + key IDs"]
    H --> I["Restore rehearsal trên cluster cô lập"]
~~~

Lưu ý:

1. Snapshot **cục bộ trên mỗi node**. Chạy lệnh trên một coordinator không tự chụp mọi replica/DC.
2. Hard link có thể chia sẻ block với SSTable active, nên snapshot **không nhân đôi byte ngay lập tức**; khi compaction thay SSTable cũ, snapshot có thể giữ block và làm disk khó giảm.
3. Trình tự flush/memtable và các tùy chọn skip flush **phụ thuộc phiên bản**. Một snapshot không flush đủ dữ liệu đang ở memtable có thể thiếu mutation chưa có trong SSTable nếu không có log/phương án bổ sung.
4. Trong khi các node được chụp tuần tự, ứng dụng có thể tiếp tục ghi. **Không có một giao dịch snapshot nguyên tử trên toàn cluster** chỉ vì tất cả node dùng cùng tên tag.
5. Thao tác tạo snapshot không chứng minh backup đã hoàn tất; phải **copy dữ liệu ra nơi khác** và thử đọc lại.

### 4.2. Thực hành `nodetool` trong lab

~~~bash
# Kiểm tra cú pháp thực tế trên đúng phiên bản:
nodetool help snapshot
nodetool help listsnapshots

# Kiểm tra trước thao tác:
nodetool status
nodetool info
nodetool compactionstats
nodetool listsnapshots

# Chỉ chạy trên node LAB với keyspace của bài:
nodetool snapshot -t preupgrade-lab-20261121 telemetry_recovery

# Sau khi công cụ báo hoàn tất:
nodetool listsnapshots
~~~

`nodetool snapshot -t` là một ví dụ cú pháp phổ biến; **phạm vi keyspace/table và options có thể khác** theo bản Cassandra, nên phải xem `nodetool help snapshot` của node đang chạy. Trên production, automation cần chạy trên **từng node cần backup**, ghi node ID, DC, rack, version, tag, thời gian và kết quả.

### 4.3. “Snapshot thành công” cần thêm bốn lớp bằng chứng

| Tầng | Bằng chứng | Không đủ nếu chỉ có... |
| --- | --- | --- |
| **Local snapshot** | Tag đúng node/bảng, manifest cục bộ phù hợp. | Exit code 0 của một lệnh. |
| **Export ngoài node** | Files/metadata đã có ở storage độc lập, checksum khớp, quyền truy cập đúng. | `listsnapshots` ở source node. |
| **Khôi phục được** | Import/restore thành công trên cluster cô lập với schema/version phù hợp. | `upload completed` hoặc object count. |
| **Đúng nghiệp vụ** | CQL/Java canary, data comparison, auth và p99 phù hợp. | Node lên trạng thái `UN`. |

## 5. Incremental backups và commit log archival: đừng trộn hai mục đích

### 5.1. Incremental backup là gì?

Với các phiên bản hỗ trợ, `incremental_backups` có thể bật cơ chế giữ các **SSTable mới được flush** trong khu vực backup để xuất đi; nó không phải một stream từng mutation theo thời gian thực.

~~~yaml
# Ví dụ ý tưởng cấu hình; chỉ xác minh/áp dụng theo bản Cassandra thực.
incremental_backups: true
~~~

Muốn dùng incremental backup để restore, cần có:

- Một **full/base snapshot** đáng tin, còn nguyên schema và mốc thời gian.
- Bộ incremental SSTable liên quan tới khoảng khôi phục và manifest **không có lỗ hổng**.
- Cơ chế định danh, checksum, thứ tự nạp, khả năng chống trùng và tương thích SSTable.
- Quy trình kiểm tra **retention**: không xóa base snapshot nếu incremental set vẫn phụ thuộc nó.

**Không coi incremental SSTable backups là tương đương Kafka log, CDC hoặc giao dịch PITR cấp ứng dụng.** Update/delete và TTL được thể hiện qua mutation/SSTable semantics, cần phục hồi đủ các thành phần có liên quan.

### 5.2. Commit log và khả năng PITR

Commit log phục vụ **khôi phục memtable chưa flush sau sự cố node**, không mặc nhiên là lịch sử mutation đầy đủ để backup tùy ý. Một số phiên bản/triển khai hỗ trợ **commit log archiving** với cấu hình/script riêng. Muốn thiết kế *point-in-time recovery* (PITR) cần:

1. Xác minh tính năng, `commitlog_archiving.properties` hoặc cơ chế tương đương, bản Cassandra và hướng dẫn chính thức của nhà vận hành.
2. Xác định **mốc bắt đầu archive**, base snapshot tương ứng và retention.
3. Đảm bảo archive không bỏ segment, lưu thứ tự/mốc thời gian và kiểm chứng checksum.
4. Kiểm tra **replay của đúng phiên bản**, tránh phát lại mutation không phù hợp schema/tombstone hoặc áp nhầm vào cluster đang phục vụ.
5. Thử restore thực tế tới một mốc UTC được chọn và **đo sai lệch dữ liệu** so với nguồn chuẩn.

**Không copy nóng file commit log đang mở rồi gọi đó là PITR**, cũng không thử xóa/đọc/sửa segment trong thư mục commitlog của node đang chạy. Các script archive/replay cần audit, mật khẩu và IAM riêng.

### 5.3. Logical export không thay thế native snapshot

Xuất dữ liệu bằng CQL/DSBulk/công cụ ETL có thể hữu ích để chuyển dữ liệu giữa các phiên bản/bố cục schema khác nhau. Tuy nhiên, một `SELECT` đọc **hàng đang sống** không xuất được đầy đủ lịch sử tombstone, writetime từng cell, TTL gốc hoặc trạng thái đồng thời giữa nhiều partition.

Ví dụ:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry_recovery.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

Đây là **kiểm tra dữ liệu logic**, không phải bản backup vật lý có thể restore nguyên vẹn mọi semantics Cassandra. Nếu dùng logical import, phải có hợp đồng rõ cho **expiry, timestamp, idempotency, delete và tính nhất quán**.

## 6. Nhiều datacenter: snapshot từ một node không đủ phục hồi cả cluster

Giả sử keyspace nghiệp vụ:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_recovery
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};
~~~

Một ví dụ production khác có `dc1: 3`, `dc2: 3`. Dữ liệu thuộc một partition có thể được nhân bản tới các replica của từng DC; nhưng **cùng RF không có nghĩa mỗi node chứa toàn bộ keyspace**.

~~~text
dc1: N1, N2, N3        dc2: N4, N5, N6

Partition A → các natural replicas của A ở từng DC
Partition B → các natural replicas của B ở từng DC

Snapshot N1 chỉ gồm những SSTable của N1.
Snapshot N4 chỉ gồm những SSTable của N4.
Muốn bảo vệ toàn keyspace phải thiết kế backup trên tập node đủ phạm vi.
~~~

**Không giả định ba snapshot trên ba node có cùng một điểm nhất quán nguyên tử.** Mỗi node có thể nhận mutation và flush khác thời điểm. Một write `LOCAL_QUORUM` success chỉ yêu cầu quorum local DC; các replica remote có thể chưa thấy mutation tại đúng thời điểm snapshot của họ.

### 6.1. Mục tiêu backup theo phạm vi rủi ro

| Sự cố muốn chịu được | Phạm vi backup/restore cần thiết |
| --- | --- |
| Mất một node | Có thể dùng replication/replace, nhưng vẫn cần backup chống corruption/deletion và quy trình rebuild/repair. |
| Mất cả DC | Backup phải nằm ngoài **miền lỗi DC**, không dựa duy nhất vào node trong DC đã mất. |
| Xóa nhầm bảng | Backup trước thời điểm xóa, schema và kế hoạch khôi phục có kiểm soát. |
| Mất quyền `system_auth` | Backup hệ thống auth và phương án quản trị/break-glass đã thử. |
| Upgrade sai định dạng SSTable | Bản backup **đọc được bằng công cụ/version được hỗ trợ** và quy trình nhập/restore phù hợp. |
| Yêu cầu snapshot ứng dụng nguyên tử | Cơ chế điều phối/barrier/đóng băng write hoặc source-of-truth replay được thiết kế riêng. |

Trong môi trường đa DC, cần kiểm tra **RF theo từng DC, placement, repair và khoảng mất kết nối** trước snapshot. Nếu replica đang thiếu mutation, backup từ một node có thể là ảnh không đầy đủ mặc dù file/manifest đều hợp lệ.

## 7. Tương thích trước nâng cấp: kiểm tra theo ma trận thay vì chỉ so số version

Một bản backup có giá trị chỉ khi có **đường phục hồi được hỗ trợ**. Khi đổi Cassandra, JDK, driver hoặc topology, cần kiểm tra ít nhất các lớp sau:

| Lớp tương thích | Câu hỏi bắt buộc | Nếu bỏ qua |
| --- | --- | --- |
| **Upgrade path** | Source version → target version có được hỗ trợ trực tiếp không? Có cần qua phiên bản trung gian? | Node không khởi động hoặc cluster mixed-version ngoài hỗ trợ. |
| **SSTable format** | Target version đọc được format đã backup? Có `upgradesstables` hay công cụ chuyển đổi được khuyến nghị? | Không thể dùng binary cũ để đọc file mới nếu format đã nâng. |
| **Internode protocol** | Phiên bản mới và cũ có được chạy chung trong rolling window không? Trong bao lâu? | Messaging/streaming/gossip không tương thích. |
| **CQL/native protocol** | Java Driver, protocol negotiation, TLS, auth provider và prepared statements có tương thích? | Ứng dụng lỗi dù các node vẫn `UN`. |
| **JDK/JVM** | JDK version, GC flags, JVM options và container memory có được hỗ trợ? | Process không khởi động hoặc GC/latency hồi quy. |
| **Schema/features** | UDT, indexes, materialized views, functions, counters, LWT, CDC, TTL có ràng buộc phiên bản không? | Query failure, data divergence hoặc workflow biến đổi semantics. |
| **Storage/capacity** | Có đủ disk cho compaction, streaming, snapshot, hints và bảng tạm? | Đầy disk khi cần compaction/khôi phục. |
| **Security/operations** | JMX, TLS, authorization, backup scripts, `nodetool` options có thay đổi? | Không kết nối/không lấy được dữ liệu khi cần restore. |

**Không suy rằng một đường nâng cấp 3.x → 4.x hoặc 4.x → 5.x luôn được phép trong mọi bản minor.** Chỉ khi kiểm tra **release notes, upgrade guide và version matrix của bản phát hành cụ thể** mới chốt trình tự và mức mixed-version hỗ trợ.

### 7.1. `upgradesstables` không phải thao tác vô hại

Một số phiên bản Cassandra có công cụ `nodetool upgradesstables` để chuyển SSTable sang format phù hợp bản đang chạy. Nó có thể gây **đọc/ghi SSTable lớn, disk I/O, compaction pressure** và làm dữ liệu vật lý không còn đọc được bằng binary cũ.

Vì vậy:

- Không chạy bất kỳ biến đổi SSTable format nào trước khi chốt **khả năng rollback và bản backup pre-upgrade**.
- Không mặc định đổi binary về bản cũ là rollback thành công sau khi data files/schema đã được upgrade.
- Nếu bắt buộc restore từ snapshot cũ, phải biết **tool và phiên bản nào nhận được SSTable format ấy**, đồng thời thử trong lab.
- Theo dõi các thao tác có thể thay file **ngay cả khi command khởi chạy thành công**; hậu kiểm mới xác định đã xử lý xong.

### 7.2. Tương thích dữ liệu không đồng nghĩa tương thích ứng dụng

Giả sử cluster đã lên `UN`, nhưng Java Driver cấu hình local DC sai hoặc truststore không còn khớp chứng chỉ. Ứng dụng vẫn lỗi. Ngược lại, ứng dụng kết nối được qua CQL không chứng minh snapshot/repair hoạt động.

Điều kiện go/no-go phải gồm **hai lớp độc lập**: *cluster data/operations health* và *application contract/latency health*.

## 8. Trước backup: preflight và tính dung lượng thực

### 8.1. Checklist node/cluster

~~~bash
# Chạy trên các node được cấp quyền, trong lab hoặc theo runbook production.
nodetool status
nodetool info
nodetool compactionstats
nodetool tpstats
nodetool netstats
nodetool listsnapshots

# Ví dụ Linux: phải thay đường dẫn/mount point theo cấu hình thật.
df -h
~~~

Ghi lại:

1. **UTC timestamp**, cluster name, datacenter, rack, node/host ID, source version/JDK.
2. Mọi keyspace RF theo DC, trạng thái `UN`/`DN`/`UJ`, đang bootstrap/rebuild/replace/decommission không.
3. Pending repair, compaction, flush, streaming và số lỗi client; không backup vào giữa một sự cố chưa rõ nguyên nhân mà không đánh giá ảnh hưởng.
4. Tốc độ ghi, p95/p99, timeout, error rate và disk free/headroom của **từng volume**, không chỉ trung bình cluster.
5. Snapshot cũ, retention, dung lượng giữ lại do hard links, capacity của nơi backup ngoài cluster.
6. Quyền người chạy, backup destination IAM/TLS, encryption key và trạng thái kiểm thử restore gần nhất.

### 8.2. CQL kiểm tra metadata

~~~sql
-- Chạy bằng tài khoản có quyền đọc metadata phù hợp.
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'telemetry_recovery';

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'system_auth';
~~~

Trong `cqlsh` còn có thể dùng:

~~~sql
DESCRIBE KEYSPACE telemetry_recovery;
DESCRIBE TABLE telemetry_recovery.events_by_device_day;
~~~

`DESCRIBE` thuộc **cqlsh**, không phải CQL statement gửi nguyên văn qua Java Driver. Schema export cần giữ **đầy đủ DDL, tên keyspace/table, UDT/index, thứ tự tạo resource và version**. Không chỉ chụp ảnh màn hình `DESC` mà thiếu file DDL có kiểm soát.

### 8.3. Ước lượng disk headroom

Giả sử một node có volume dữ liệu **1.000 GB**, đang dùng **820 GB**. Nhóm dự kiến tạo/giữ thêm **120 GB** SSTable cũ do snapshot, phát sinh **70 GB** output compaction và tăng **40 GB** dữ liệu mới trước khi file cũ có thể giải phóng:

~~~text
Free ban đầu                      : 180 GB
Snapshot giữ thêm file cũ (ước)    : 120 GB
Compaction output tạm (ước)        :  70 GB
Write mới trong window (ước)      :  40 GB
Tổng nhu cầu tăng có thể xảy ra    : 230 GB
Thiếu headroom theo mô hình        :  50 GB
~~~

Đây là ví dụ **biên trên đơn giản hóa**: hard links không nhân đôi file tại thời điểm snapshot, và thời điểm giải phóng file/phạm vi output khác nhau. Nhưng nó chỉ ra một vấn đề quan trọng: **sao lưu an toàn trên node gần đầy có thể khiến các lần compaction sau đó không còn chỗ ghi**, dù snapshot ban đầu tạo rất nhanh.

## 9. Lab CQL: dữ liệu chuẩn trước thay đổi

### 9.1. Bảng theo thiết bị/ngày

Sau khi tạo keyspace `telemetry_recovery` ở mục 6, tạo bảng lab:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_recovery.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

`(device_id, event_day)` là partition key kép; `(event_time, event_id)` là clustering key. Cùng một thiết bị ở hai ngày có thể thuộc **token/natural replicas khác nhau**. Điều này quan trọng khi sao lưu/khôi phục vì không thể lấy snapshot từ một node bất kỳ rồi giả định nó chứa mọi partition của bảng.

### 9.2. Ghi các hàng sentinel

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_recovery.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T08:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'heartbeat', 'ok');

INSERT INTO telemetry_recovery.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-7', '2026-11-21', '2026-11-21T08:05:00Z',
   123e4567-e89b-42d3-a456-426614174002, 'temperature', '21.2');

INSERT INTO telemetry_recovery.events_by_device_day
  (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
  ('device-8', '2026-11-21', '2026-11-21T08:07:00Z',
   123e4567-e89b-42d3-a456-426614174003, 'alarm', 'over_limit');
~~~

`LOCAL_QUORUM` với RF = 3 tại `dc1` cần **hai replica ACK** cho mỗi write. Nó không chứng minh **mọi replica** đã ghi tại đúng mốc chụp snapshot; do đó chụp các node tuần tự vẫn cần kế hoạch nhất quán dữ liệu.

### 9.3. Ghi baseline dữ liệu và đường đọc

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry_recovery.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z';
~~~

Bộ dữ liệu sentinel gồm **hai hàng** của `device-7`, theo thứ tự `event_time DESC`, có event ID/payload cố định. Trong diễn tập restore, so lại **tập khóa và giá trị** để phát hiện nhầm keyspace, bucket, clustering order hoặc dữ liệu không đủ. Với production, vài hàng sentinel **không thay thế** đối soát ở quy mô đầy đủ.

## 10. Quy trình tạo backup trước rolling upgrade

### Giai đoạn A — Đóng băng thông tin và ranh giới

1. Ghi **change ID**, phiên bản nguồn/đích và **upgrade path đã được hỗ trợ**.
2. Chốt **RPO/RTO**, time window và xử lý write trong khi snapshot: tạm dừng ghi, write barrier, durable event stream hoặc phương án khác phù hợp.
3. Chốt **phạm vi bảng/keyspace/node/DC**, including `system_auth` và metadata cần thiết.
4. Chụp baseline RF, token, schema, auth/JMX/TLS và tình trạng replica.
5. Bảo đảm có đủ disk headroom, đường backup không làm nghẽn read/write, và kho backup có quyền đúng.

### Giai đoạn B — Tạo snapshot ở đúng từng node

~~~bash
# VÍ DỤ node lab; automation production phải thực thi trên tập node đủ phạm vi.
nodetool snapshot -t preupgrade-lab-20261121 telemetry_recovery
nodetool listsnapshots
~~~

Không dùng snapshot tag đơn lẻ làm id duy nhất của toàn cluster. Trong backup manifest cần lưu:

~~~text
change_id       = CHG-2026-11-21-CASS-UPGRADE
snapshot_tag    = preupgrade-lab-20261121
node            = cassandra-dc1-n1
datacenter      = dc1
rack            = rack-a
host_id         = <recorded-node-host-id>
cassandra_src   = <exact-version-and-build>
jdk_src         = <exact-jdk-build>
keyspace        = telemetry_recovery
schema_hash     = <hash-of-versioned-schema-export>
snapshot_start  = <UTC>
snapshot_end    = <UTC>
backup_format   = native-sstable-snapshot
manifest_state  = LOCAL_SNAPSHOT_VERIFIED
~~~

`<...>` là các placeholder phải được điền từ kết quả thực, **không** phải giá trị copy nguyên vào manifest. Lưu thêm **một record cho mỗi node/bảng/artefact**; nếu node N3 failed snapshot, toàn backup set có thể chưa đạt mục tiêu, dù N1/N2 thành công.

### Giai đoạn C — Xuất và kiểm tra ngoài cluster

1. Xác minh **đúng các file snapshot và metadata** của từng node theo manifest phiên bản, không copy đại cả thư mục `data` đang biến đổi.
2. Chuyển dữ liệu ra **object storage/backup appliance độc lập về lỗi**, mã hóa khi truyền và lưu.
3. Kiểm tra **checksum file** và kiểm đếm file/bytes ở cả nguồn và đích, không chỉ dựa vào exit code của `copy`.
4. Giữ **schema/config/version manifest** cùng reference tới secret/key; phân quyền đọc/xóa và retention/immutability.
5. Đánh dấu `BACKUP_EXPORTED` sau khi dữ liệu đến nơi, nhưng chỉ dùng `RESTORE_VERIFIED` sau khi diễn tập phục hồi thành công.

Trên máy lab Linux, cách kiểm tra hash của **một file mẫu**:

~~~bash
# Đường dẫn ví dụ phải thay bằng file snapshot/backup thực đã xác định.
sha256sum /backup-staging/example-sstable-file.db
~~~

Trong production, nên có hệ backup tạo **manifest hash tự động**, đối chiếu đầu–cuối, kiểm tra retention và khả năng phục hồi. Không đưa key encryption vào manifest dạng plaintext, không để backup chỉ nằm trên cùng volume với Cassandra.

### Giai đoạn D — Hoàn tất điều kiện trước thay đổi

Không nâng cấp node đầu tiên cho đến khi có:

- Backup set đạt **phạm vi node/DC, keyspace và metadata** yêu cầu.
- Checksum/manifest và bản ngoài cluster đã xác minh, có quyền giải mã/đọc thật.
- **Restore rehearsal** chạy thành công với source/target version được hỗ trợ.
- Mức mất dữ liệu có thể xảy ra so với **RPO** đã được chứng minh; nguồn ghi còn tiếp tục thì có log/replay hoặc cửa sổ đóng băng phù hợp.
- Rolling plan, một hoặc nhiều **canary query Java**, ngưỡng dừng và tài liệu rollback/restore.

## 11. Làm sao biết bản backup có thực sự nhất quán?

### 11.1. Node snapshot không bằng application transaction snapshot

Giả sử hai thao tác nghiệp vụ liên quan:

~~~text
10:00:00.100  Ghi order header vào partition A
10:00:00.150  Ghi order items vào partition B
10:00:00.120  Snapshot N1
10:00:00.170  Snapshot N2
~~~

Nếu backup kết hợp các SSTable ở hai node vào cùng tập phục hồi, có thể có **header mà thiếu items** hoặc ngược lại, tùy vị trí partition, replica và thời gian từng write. Cassandra không tự cung cấp snapshot **nguyên tử xuyên nhiều partition/DC** cho workflow này.

Để có trạng thái nhất quán nghiệp vụ, phải thiết kế rõ một trong các phương án:

- **Quiesce writes:** dừng/tạm hoãn mutation trong một cửa sổ có kiểm soát, xác minh inflight đã xử lý và chụp dữ liệu.
- **Application barrier/watermark:** ghi mốc nghiệp vụ vào nguồn dữ liệu chuẩn, giữ mutation log để replay về trạng thái mong muốn.
- **Transaction/outbox ở upstream:** dùng nguồn giao dịch có thứ tự/offset và tái dựng projection Cassandra sau restore.
- **Chấp nhận eventual consistency có đối soát:** nếu nghiệp vụ cho phép, xác định điều kiện data completeness và remediation sau khi restore.

Không có phương án nào tự xuất hiện chỉ vì dùng `QUORUM` hoặc `ALL`: CL kiểm soát **số phản hồi replica cho từng request**, không cung cấp distributed transaction snapshot cho mọi bảng.

### 11.2. Tombstone và TTL ảnh hưởng kết quả backup/restore

Một hàng đã bị `DELETE` có thể còn tombstone trong SSTable, và TTL hết hạn không làm file biến mất ngay. Restore native SSTable có thể mang **timestamp/tombstone/TTL metadata** đi cùng, nhưng tính đúng còn phụ thuộc đủ SSTable, version, mốc phục hồi và cách nạp/merge.

Trong khi đó **logical export các hàng còn sống** có thể thiếu tombstone và thông tin expiry. Nếu import lại bằng `INSERT` mới, TTL có thể bị **tính lại từ thời điểm import** và gây hồi sinh dữ liệu vốn đã bị xóa khi xử lý sai mutation order.

Vì vậy restore test phải kiểm tra:

1. Hàng còn sống có giá trị chính xác tại thời điểm mốc.
2. Hàng đã xóa/hết hạn **không** xuất hiện lại không hợp lệ.
3. TTL còn lại và retention phù hợp với yêu cầu nghiệp vụ.
4. Replica được repair/hội tụ theo phạm vi và phiên bản.
5. Mọi nguồn mutation mới sau snapshot đã được replay/đối soát đúng **watermark**.

**Không giảm `gc_grace_seconds` tùy tiện để đẩy nhanh reclaim trước backup**: replica bỏ lỡ tombstone có thể làm dữ liệu cũ xuất hiện lại khi đồng bộ sau đó.

## 12. Diễn tập khôi phục: môi trường cô lập quan trọng hơn một câu lệnh restore

**Restore rehearsal** là việc khôi phục thật từ backup đã lưu, trên một môi trường có kiểm soát, sau đó chứng minh dịch vụ đọc/ghi được và dữ liệu đáp ứng mốc yêu cầu. Nó khác hoàn toàn việc chỉ chạy `nodetool listsnapshots` hay tải một file từ object storage xuống.

### 12.1. Ba kiểu restore phục vụ ba mục tiêu

| Kiểu khôi phục | Kịch bản | Điều kiện/đánh đổi |
| --- | --- | --- |
| **Phục hồi node vật lý theo quy trình hỗ trợ** | Một node hỏng disk, cần thay host/khôi phục các file có cấu trúc phù hợp. | Phải hiểu host ID, token ownership, file paths, topology và version; có thể ưu tiên replace/streaming hơn copy file. |
| **Khôi phục sang cluster lab cô lập bằng SSTable import/streaming** | Thử backup hoặc phục hồi dữ liệu sang cụm độc lập. | Tạo schema/target topology tương thích, dùng công cụ được version hỗ trợ như `sstableloader` hoặc quy trình tương đương. |
| **Khôi phục logic theo record/export** | Chuyển sang mô hình schema khác, cần transform dữ liệu. | Không tự giữ tombstone/TTL/writetime; cần dữ liệu nguồn chuẩn và kiểm chứng semantics. |

Không có một lệnh `restore everything` áp dụng cho mọi bản Cassandra. Trước diễn tập phải viết **restore plan theo nguồn dữ liệu, snapshot layout, source/target version, schema, encryption và topology**.

### 12.2. Các lớp cách ly bắt buộc

~~~mermaid
flowchart LR
    A["Backup storage: read-only snapshot + manifest"] --> B["Restore staging được phê duyệt"]
    B --> C["Cluster Cassandra TEST có network riêng"]
    D["Production gossip/internode/CQL"] -.->|"Không được kết nối"| C
    E["Secret manager: test credentials"] --> C
    C --> F["CQL/Java canary + data reconciliation"]
    F --> G["RPO, RTO và bằng chứng restore"]
~~~

Khi dựng cluster test:

- Dùng **cluster identity, network, seed/contact points và service DNS riêng**; chặn kết nối internode/gossip vào production. Không để test node vô tình join ring production.
- Xác minh **`cluster_name`, địa chỉ listen/broadcast, DC/rack/snitch** và cấu hình TLS phù hợp với topology test.
- Không đưa production secrets hoặc private keys vào lab không đủ bảo vệ. Chỉ lấy bản backup đã được phép, mã hóa và redaction khi cần.
- Nếu test cluster ít node hơn RF sản xuất, chuẩn bị **kế hoạch RF/CL phù hợp** mà không làm thay đổi bản backup gốc hoặc môi trường production; không giả định `LOCAL_QUORUM` của dc1:3 sẽ thành công trên một node.
- Ghi lại **version và cách convert/import SSTable** trong lab. Không tự đổi target version chỉ để công cụ “chịu đọc file”.
- Tách storage output và log của rehearsal khỏi backup nguồn; nguồn backup phải được giữ **read-only/immutable** để có thể diễn tập nhiều lần.

**Cảnh báo:** thao tác copy file hoặc chạy restore trực tiếp vào thư mục SSTable của node Cassandra đang sống có thể làm sai trạng thái file/SSTable tracker. Dùng **cơ chế import/streaming/restore chính thức hỗ trợ phiên bản**, và đối với phục hồi offline phải tuân runbook dừng node/metadata/topology. Không chỉ dùng `cp` hay `rsync` vào thư mục đang active.

## 13. Runbook restore rehearsal theo từng bước

### Bước 1 — Chọn một backup set và cố định mục tiêu

Không chọn “bản mới nhất” một cách mơ hồ. Mỗi lần diễn tập phải cố định:

~~~text
rehearsal_id      = DRILL-2026-11-21-01
backup_set_id     = PREUPG-2026-11-21-telemetry
source_cluster    = cassandra-prod
source_version    = <exact-source-build>
target_cluster    = cassandra-restore-lab
target_version    = <supported-restore-version>
target_rpo_point  = <UTC watermark / snapshot set + mutation-log position>
required_tables   = telemetry_recovery.events_by_device_day, system_auth policy
success_criteria  = checksum + data match + role checks + application canary
restore_deadline  = <UTC deadline representing RTO>
~~~

Nguồn backup phải có **manifest theo node, DDL, config/version và mã băm**. Nếu backup được ghi trong lúc production vẫn có write, kế hoạch phải nói rõ **mốc mutation nào được phục hồi**, không chỉ lấy thời gian tạo thư mục snapshot.

### Bước 2 — Kiểm tra khả năng tải, giải mã và đọc metadata

1. Dùng **identity backup/restore được cấp quyền ngắn hạn**; không đăng nhập bằng superuser ứng dụng.
2. Truy cập bản ngoài cluster, kiểm tra object count, byte size, checksums và **tính toàn vẹn manifest**.
3. Xác minh key ID/envelope key/trust chain cần để giải mã vẫn còn và có quyền sử dụng.
4. Kiểm tra đầy đủ schema DDL, mapping `keyspace/table-UUID`, version, RF/DC, SSTable components, snapshot tag.
5. Kiểm tra **base snapshot và chuỗi incremental/archived log** nếu mục tiêu là restore nhiều bước.
6. Không chấp nhận chỉ một file `Data.db`: một SSTable có thể gồm **nhiều component** như index/statistics/compression metadata và các component phụ thuộc phiên bản.

**Kết quả:** ghi `BACKUP_BYTES_VERIFIED` hoặc `BACKUP_INCOMPLETE`, **không** vội ghi `RESTORE_SUCCESS`.

### Bước 3 — Dựng môi trường đích đúng khả năng tương thích

- Dựng cluster test cô lập với Cassandra/JDK **theo ma trận hỗ trợ** đã duyệt.
- Áp dụng **schema cùng keyspace/table** theo DDL phiên bản; xác minh key và clustering columns trước khi nạp.
- Kiểm tra cluster test có đủ disk cho **import/streaming/compaction**, gồm file tạm và backup staging.
- Quyết định cách xử lý `system_auth`: khôi phục thật trong môi trường quản trị được cách ly hoặc tái provision test identities phù hợp. **Không trộn auth metadata production với policy test vô tình.**
- Chọn **CL/driver version** phù hợp với số replica test và mục tiêu smoke test.

### Bước 4 — Nạp dữ liệu bằng quy trình đúng loại backup

Đối với native SSTable backup, có thể tồn tại các lựa chọn như **SSTable streaming/import** hoặc phục hồi offline theo phiên bản. Công cụ `sstableloader` thường được dùng để **stream SSTable vào target cluster**, nhưng cú pháp đường dẫn, yêu cầu DDL, source/target format, authentication và khả năng sử dụng snapshot directory phải được xác minh tại bản Cassandra thật.

Không được:

- Chép file từ một version bất kỳ vào node version khác rồi thử restart cho đến khi nó nhận.
- Dùng `nodetool refresh` hoặc copy file trực tiếp mà không biết trạng thái node/bảng và hướng dẫn nhập của phiên bản.
- Copy dữ liệu hệ thống gắn với **host identity/ring metadata** sang cluster test có identity khác.
- Tải snapshot của **chỉ một node** rồi tuyên bố khôi phục đủ dữ liệu toàn keyspace.
- Chạy restore test và công cụ admin bằng credentials production ở môi trường không kiểm soát.

**Kết quả:** ghi rõ những table/window/token ranges đã nạp, skipped/failed files, số byte và log session/streaming.

### Bước 5 — Hòa giải và chờ các công việc nền cần thiết

Sau ingest:

~~~bash
# Trên node TEST.
nodetool status
nodetool info
nodetool netstats
nodetool compactionstats
nodetool tpstats
nodetool tablestats telemetry_recovery.events_by_device_day
~~~

Khi có trạng thái replica lệch hoặc import nhiều SSTable, quy trình có thể cần **repair/compaction theo đúng hướng dẫn version**. Không tự ép major compaction chỉ để “dọn dữ liệu restore”; nó có thể cần rất nhiều disk tạm, ảnh hưởng TTL/tombstone và kéo dài RTO.

**`UN` chỉ chứng minh node đang ở trạng thái up/normal theo membership**, chưa chứng minh mọi partition/role đã được phục hồi đúng.

### Bước 6 — Đối soát dữ liệu và kiểm tra ứng dụng

1. Đọc các partition **sentinel** biết trước theo partition key và clustering range.
2. So `event_time`, `event_id`, `event_type`, `payload` theo **key/value**, không chỉ số hàng.
3. Đối soát representative partitions, hot/cold partitions, thời gian đầu/cuối kỳ, TTL, xóa và late-arriving events.
4. Nếu có **source-of-truth ngoài Cassandra**, so với state tại watermark đã định nghĩa; không chỉ so hai snapshot không đồng bộ.
5. Thử Java Driver/CQL với **quyền đọc/ghi tối thiểu**, TLS, local DC và CL thích hợp; kiểm tra cả lỗi Unauthorized khi thiếu quyền.
6. Đo p50/p95/p99, error rate, timeout, disk I/O, GC và request rate dưới workload lab kiểm soát.

### Bước 7 — Ghi RPO/RTO và quyết định đạt/chưa đạt

~~~text
Tool outcome              : import command success / failed / unknown
Data verification         : key/value match / mismatch / not measured
Recovery point validated  : last event/offset verified at <UTC>
Recovery elapsed          : measured wall time to service canary readiness
Auth/TLS verification     : passed / failed / not applicable
SLO/functional canary     : passed / failed / incomplete
Final verdict             : RESTORE_VERIFIED / FAILED / INCONCLUSIVE
~~~

**Đừng đánh đồng lệnh restore hoàn tất với RTO.** RTO chỉ đạt khi **ứng dụng có thể phục vụ đúng** theo tiêu chí đã duyệt. Nếu phát hiện mismatch hoặc chưa kiểm tra được deletion/TTL, trạng thái phù hợp là `INCONCLUSIVE`, không phải `VERIFIED`.

## 14. Java Driver 4.x: smoke test sau restore

Cụm test đã có bảng `telemetry_recovery.events_by_device_day` và các hàng sentinel ở mục 9. Ví dụ Java sau kiểm tra **đúng hai event** của `device-7` ở một ngày. Code chỉ chạy read, không cần quyền DDL/JMX và không thay đổi dữ liệu backup.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class RestoreSmokeTest {
    public static void main(String[] args) {
        // Chỉ dùng host/DC của cluster TEST cô lập.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement statement = session.prepare(
                "SELECT event_time, event_id, event_type, payload " +
                "FROM telemetry_recovery.events_by_device_day " +
                "WHERE device_id = ? AND event_day = ?");

            BoundStatement read = statement.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            Map<UUID, String> expected = new HashMap<>();
            expected.put(
                UUID.fromString("123e4567-e89b-42d3-a456-426614174001"),
                "heartbeat|ok");
            expected.put(
                UUID.fromString("123e4567-e89b-42d3-a456-426614174002"),
                "temperature|21.2");
            Map<UUID, String> actual = new HashMap<>();
            long started = System.nanoTime();

            for (Row row : session.execute(read)) {
                Instant time = row.getInstant("event_time");
                if (time.isBefore(Instant.parse("2026-11-21T08:00:00Z"))
                        || !time.isBefore(
                            Instant.parse("2026-11-21T09:00:00Z"))) {
                    throw new IllegalStateException(
                        "Unexpected event outside sentinel window");
                }
                UUID eventId = row.getUuid("event_id");
                String value = row.getString("event_type")
                    + "|" + row.getString("payload");
                if (actual.put(eventId, value) != null) {
                    throw new IllegalStateException("Duplicate event ID");
                }
            }

            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);

            if (!actual.equals(expected)) {
                throw new IllegalStateException(
                    "RESTORE_MISMATCH: sentinel key/value mismatch");
            }
            System.out.println("RESTORE_SENTINEL_OK"
                + " query=events_by_device_day"
                + " cl=LOCAL_QUORUM"
                + " rows=" + actual.size()
                + " elapsed_ms=" + elapsedMs);
        }
    }
}
~~~

### 14.1. Điều kiện để hiểu đúng phép thử

- `CqlSession.builder()` phải trỏ tới **cluster rehearsal**, không phải production. IP loopback ở đây là cấu hình lab.
- `LOCAL_QUORUM` với `dc1:3` cần hai replica; nếu cluster test chỉ có một node, **phải thiết kế RF/CL test hợp lệ** thay vì hạ CL âm thầm khi đối chiếu correctness.
- Hai hàng sentinel giúp phát hiện một số lỗi rõ ràng nhưng **không chứng minh toàn bộ backup hoàn chỉnh**. Cần đối soát dữ liệu theo partition/window hoặc checksum canonicalization ở quy mô lớn.
- Chương trình đo elapsed client bao gồm decode/iteration; không phải đo độc lập disk latency của replica.
- Trong production, phải cấu hình **TLS, authentication, secret manager và timeout** của driver; bỏ qua chúng trong đoạn lab này không có nghĩa không cần bảo mật.
- Nếu backup không chứa sentinel ở thời điểm snapshot, phép thử phải được điều chỉnh theo **đúng backup set và watermark**, không dùng dữ liệu phát sinh sau đó để kết luận lỗi restore.

### 14.2. Test thêm trường hợp bị từ chối

Nếu auth/RBAC thuộc mục tiêu restore, chạy bằng **role chỉ đọc** và xác nhận:

1. `SELECT` bảng được cấp quyền thành công.
2. `INSERT/DELETE/ALTER TABLE` không được phép **thực sự bị từ chối** khi test an toàn trên bảng lab.
3. Tài khoản admin break-glass hoạt động theo quy trình; tài khoản mặc định/secret đã thu hồi không còn đăng nhập được.
4. Kết nối Java dùng truststore/certificate phù hợp; không dùng TLS `trust-all`.

**Restore `system_auth` sai** có thể khiến dữ liệu còn nguyên nhưng toàn bộ ứng dụng/admin không truy cập được; đây là một phần của RTO, không phải việc có thể bỏ qua.

## 15. Kiểm tra dữ liệu: count không đủ, checksum file cũng không đủ

### 15.1. Hai cấp độ kiểm chứng khác nhau

- **Checksum ở backup file level:** xác nhận byte được copy từ nguồn đến đích **không bị biến đổi ngoài ý muốn**. Nó không chứng minh backup đã chụp đúng bảng, đúng thời điểm hoặc đủ mọi replica/token.
- **Đối soát logic ở record level:** xác nhận các key/value cần có **thực sự truy vấn được** ở cluster phục hồi, bao gồm logic TTL/delete và mutation replay tới watermark.

~~~text
File checksum PASS
  != backup coverage PASS
  != data consistency PASS
  != application availability PASS
  != RPO/RTO PASS
~~~

### 15.2. Vì sao `COUNT(*)` toàn bảng là bẫy?

Cassandra không duy trì một counter tổng hàng sống chính xác của mọi bảng theo cách có thể trả miễn phí. Một lệnh `SELECT COUNT(*)` trên dữ liệu lớn có thể phải quét nhiều partition/SSTable, gây I/O, GC, tombstone pressure và thậm chí timeout.

Trong restore rehearsal, nên:

1. Chọn **scope có ranh giới**: thiết bị/ngày, token ranges, bảng/tenant theo inventory.
2. So **tập primary keys**, `event_time`, payload canonicalization và các field nghiệp vụ quan trọng.
3. Tính **fingerprint có thứ tự** từ dữ liệu chuẩn hóa trong công cụ ngoài Cassandra khi phù hợp; ghi thuật toán/serialization.
4. Đảm bảo source và restore được đối chiếu ở **cùng watermark**. Nếu write tiếp diễn, một chênh lệch có thể do thời điểm đọc khác nhau chứ không phải mất dữ liệu.
5. Kiểm tra **hàng không được tồn tại**: event đã delete/hết TTL phải không xuất hiện lại trái hợp đồng.

### 15.3. Phân biệt repair với khôi phục dữ liệu logic

`nodetool repair` giúp các replica của **cùng một keyspace/table** đối chiếu theo phạm vi repair; nó **không** tái tạo schema đã drop, không sửa một bản backup thiếu bảng, không biến logical export thành snapshot nguyên tử. Sau restore, repair có thể là một bước trong kế hoạch đồng bộ, **không thay** kiểm chứng đầy đủ dữ liệu ứng dụng.

## 16. Trước rolling upgrade: go/no-go và khái niệm rollback

### 16.1. Hai kịch bản đảo ngược khác nhau

| Thao tác | Khi nào khả thi? | Rủi ro |
| --- | --- | --- |
| **Rollback cấu hình** | Khi có config cũ, cấu hình mới chưa tạo trạng thái không tương thích, và version cho phép. | Vẫn có thể cần restart và tác động availability. |
| **Rollback binary** | Chỉ khi **đường downgrade cụ thể được hỗ trợ**, dữ liệu/schema/format chưa vượt ngưỡng tương thích. | Bản cũ có thể không đọc SSTable hoặc schema đã bị nâng. |
| **Restore từ backup** | Khi có backup pre-change đã kiểm thử và môi trường restore phù hợp. | Có RPO/RTO, có thể cần rehydrate/stream/replay; không phải thao tác tức thì. |
| **Replace/rebuild replica** | Khi cluster vẫn còn replica đủ dữ liệu và topology hỗ trợ. | Không giúp khi mutation xóa nhầm được lan tới toàn bộ replicas. |

**Không viết “nếu upgrade lỗi thì cài lại phiên bản cũ” như một chiến lược rollback hoàn chỉnh.** Sau khi format SSTable, schema hoặc internode compatibility thay đổi, downgrade có thể không được hỗ trợ. Phải đánh giá giới hạn riêng của source/target versions và có restore rehearsal.

### 16.2. Điều kiện GO trước node đầu tiên

~~~text
[ ] Upgrade path source -> target được bản phát hành hỗ trợ.
[ ] JDK/driver/native protocol/TLS/JMX tương thích đã thử.
[ ] Config source, schema DDL, RF/DC, topology, role và secret references lưu đủ.
[ ] system_auth được bảo vệ, backup và break-glass đã diễn tập.
[ ] Snapshot/backup đủ node/partition/keyspace theo chiến lược được duyệt.
[ ] Base/incremental/archived-log chain đầy đủ nếu RPO cần.
[ ] Backup off-cluster checksums, manifest, retention, encryption được xác minh.
[ ] Restore rehearsal trên cluster cô lập đạt dữ liệu + auth + Java canary.
[ ] RPO và RTO thực đo đáp ứng mục tiêu.
[ ] Có capacity/disk headroom cho snapshot, compaction, streaming.
[ ] Replica/DC health, repair và hint/compaction backlog chấp nhận được.
[ ] Canary node/order duy trì quorum, không restart nhiều replica rủi ro.
[ ] Có điều kiện dừng, actor/approval, rollback/restore plan cụ thể.
~~~

Nếu một mục tiêu **chưa có bằng chứng**, không đánh dấu `GO` chỉ vì lịch bảo trì đã tới. Với thay đổi rủi ro cao, cần người phê duyệt chịu trách nhiệm quyết định các ngoại lệ.

### 16.3. Điều kiện STOP trong quá trình rolling upgrade

- Một node mới không join ring theo cách tương thích hoặc gossip/internode connection thất bại.
- RF/CL đang dùng không còn đủ replica; read/write timeout hoặc unavailable vượt baseline.
- Disk free giảm dưới headroom bảo trì, compaction/streaming backlog tăng mất kiểm soát.
- Ứng dụng Java không kết nối được hoặc prepared statements/TLS/auth bắt đầu lỗi.
- Snapshot/export/restore/backup access bị hỏng do thay đổi cấu hình hoặc quyền.
- Có khác biệt dữ liệu/canary không giải thích được.

**Dừng mở rộng rollout** không nhất thiết có nghĩa phải restart/rollback ngay node đang nâng. Việc đảo ngược phải theo **đường được hỗ trợ** và trạng thái SSTable/schema thực tế.

## 17. Các lỗi diễn tập thường gặp và cách xử lý

| Tình huống | Nguyên nhân khả dĩ | Hành động an toàn |
| --- | --- | --- |
| `listsnapshots` có tag nhưng object storage trống | Chỉ chụp local, chưa export hoặc uploader thất bại. | Giữ `BACKUP_INCOMPLETE`, sửa export và xác minh checksum. |
| Snapshot N1/N2 có, N3 thiếu | Automation chưa bao phủ đủ node hoặc node lỗi. | Xác định coverage theo token/replicas, không tự tuyên bố toàn cluster đủ. |
| Checksum file PASS nhưng thiếu hàng sentinel | Backup sai node/window/schema hoặc replica snapshot chưa có mutation. | Đối soát manifest, watermark, full/incremental/replay và natural replicas. |
| Restore test vô tình nhìn thấy production | DNS/seed/cluster identity/network isolation sai. | **Ngừng ngay**, cô lập kết nối; điều tra ảnh hưởng trước khi thử lại. |
| Node test khởi động nhưng không đọc được SSTable | Version/format/schema/path/metadata không tương thích. | Dùng import/upgrade path được hỗ trợ; không ép copy file nóng. |
| `system_auth` restore làm admin bị khóa | Auth metadata, RF/role cache hoặc credential sai. | Break-glass runbook, isolate môi trường, kiểm tra role provisioning. |
| Khôi phục xong TTL như được “gia hạn” | Logical import tạo mutation mới với TTL mới. | Thiết kế expiry/remaining TTL, test semantics, không coi logical export native. |
| Hàng đã `DELETE` xuất hiện lại | Replay/tombstone không đầy đủ, timestamp conflict hoặc replica lệch. | Dừng cutover, điều tra mutation order/repair và mốc dữ liệu. |
| Recovery mất nhiều giờ hơn RTO | Import/streaming I/O, nhiều SSTable, network hoặc startup quá lâu. | Đo bottleneck, cải thiện phương án backup/parallelism có kiểm soát. |
| Binary cũ không chạy sau nâng cấp | File/schema đã đổi format hoặc downgrade không hỗ trợ. | Restore từ backup pre-change theo phiên bản phù hợp, không tiếp tục thử “downgrade mù”. |
| Kho backup không giải mã được | Thiếu key ID/KMS/IAM, cert hết hạn hoặc key bị rotate/xóa. | Kiểm tra backup encryption/recovery key lifecycle, cập nhật quy trình. |
| Restore test chỉ chạy một hàng nhưng vẫn kết luận GO | Tiêu chí correctness quá yếu. | Mở rộng theo scope, deleted/TTL/hot partition, application SLO và auth. |

### 17.1. Khi một lệnh thất bại hoặc mất kết nối

Nếu automation mất SSH/JMX connection lúc đang snapshot/import, lệnh có thể **chưa bắt đầu, đang chạy hoặc đã hoàn tất một phần**. Ghi trạng thái `UNKNOWN` và xác minh bằng logs, session ID, snapshot inventory, file manifest/streaming status trước khi retry. Không tự chạy lại thao tác nặng trong cluster đang chịu tải.

## 18. Thiết kế backup bền vững ngoài cluster

### 18.1. Nguyên tắc 3-2-1 theo nhu cầu thực tế

Một nguyên tắc phổ biến là có **nhiều bản sao**, trên **nhiều miền lỗi/loại lưu trữ**, và **ít nhất một bản nằm ngoài cluster/site**. Đây là định hướng dự phòng, không phải số lượng chính xác bắt buộc cho mọi tổ chức; cần gắn với RPO/RTO, chi phí và yêu cầu pháp lý.

Các kiểm soát thực tế:

1. **Isolation:** destination backup không phụ thuộc hoàn toàn vào disk, node, DC hoặc tài khoản quản trị của Cassandra.
2. **Encryption:** dữ liệu và metadata được mã hóa khi truyền/lưu, có KMS/secret recovery độc lập.
3. **Immutability/retention:** ngăn sửa/xóa ngoài ý muốn, có lịch retention và kiểm tra policy thực tế.
4. **Least privilege:** backup writer không mặc nhiên có quyền xóa tất cả backup; restore reader tách khỏi ứng dụng.
5. **Integrity:** file checksum, signed/versioned manifest nếu có, định kỳ kiểm tra toàn vẹn.
6. **Observability:** cảnh báo backup overdue, export incomplete, thiếu node, RPO gap, secret/cert expiry.
7. **Restore rehearsal:** định kỳ và **trước thay đổi lớn**, với bản backup chọn ngẫu nhiên hoặc theo rủi ro.

### 18.2. Manifest backup nên chứa gì?

~~~text
backup_set_id
change_id + reason
source_cluster + environment
source Cassandra/JDK exact build
keyspace/table/schema export hash
per-node: host_id, DC, rack, token/ring metadata
per-node: snapshot tag + UTC start/end + state
SSTable component list + byte sizes + checksums
incremental set IDs / archived segment ranges (nếu có)
source of mutation watermark/RPO definition
encryption key references (không chứa raw key)
off-cluster destination + retention/immutability
verified_by + verified_at_utc + verification method
restore rehearsal ID + target version + verdict
~~~

Việc giữ **manifest độc lập** còn giúp biết bản backup nào phải dùng nếu sau nâng cấp các node có SSTable format khác nhau. Không suy ra version chỉ từ ngày backup hoặc tên file.

## 19. Case study: nâng cấp Cassandra giữa hai DC, snapshot hợp lệ nhưng không đạt RPO

Giả sử cluster có `dc1:3` và `dc2:3`. Ứng dụng ghi ở `dc1` với `LOCAL_QUORUM`. Công ty cần RPO 10 phút, RTO 90 phút. Nhóm chụp snapshot trước upgrade như sau:

| Mốc UTC | Sự kiện giả lập | Điều phải đánh giá |
| --- | --- | --- |
| 09:00 | Snapshot lần lượt N1–N3 tại dc1. | Có writer đang ghi? Có mutation chưa tới các replica khác? |
| 09:05 | Snapshot lần lượt N4–N6 tại dc2. | Các write từ dc1 đã đến dc2 chưa? |
| 09:10 | Tất cả các node có tag cùng tên. | Tag giống nhau **không** tạo snapshot nguyên tử toàn cluster. |
| 09:15 | Export các file được báo hoàn tất. | Checksum/manifest và mọi SSTable components đã đủ chưa? |
| 09:20 | Upgrade bắt đầu; ứng dụng vẫn tiếp tục ghi. | Mutation sau mốc snapshot nào sẽ được replay nếu cần rollback? |
| 10:00 | Sự cố upgrade làm ứng dụng không phục vụ được. | Restore test trước đó có chứng minh 90 phút RTO và 10 phút RPO không? |

**Sai lầm trong kịch bản:** nhóm chỉ kiểm tra số tag/snapshot và một lệnh `SELECT` sentinel trước 09:00, rồi tuyên bố RPO 10 phút. Nếu cần phục hồi lúc 10:00 từ backup 09:00 nhưng không có một **mutation log liên tục và recoverable** tới 09:50, RPO 10 phút **chưa được bảo đảm**.

**Cách cải thiện:** dùng snapshot + kế hoạch catch-up/archive/replay đã thử, hoặc thực hiện thay đổi trong một window đóng băng writes có kiểm soát nếu SLA cho phép. Trong restore rehearsal, kiểm chứng **mốc mutation gần mục tiêu**, sự nhất quán giữa DC và ứng dụng, không chỉ sự tồn tại của file.

### 19.1. Kết luận sự cố phải có giới hạn bằng chứng

~~~text
Observation:
  Snapshot tồn tại trên cả 6 nodes, exported và checksum PASS.

Not yet proven:
  Có thể restore tất cả writes trước 09:50.
  Schema/permissions sau restore đúng trên cả hai DC.
  Khôi phục xong trong 90 phút dưới tải thật.

Decision:
  BACKUP_EXPORTED, RESTORE_RPO_UNVERIFIED
  => NO-GO cho thay đổi cần RPO 10 phút.
~~~

Không có gì sai khi **chưa thể bảo đảm** một RPO; sai là đánh dấu đạt khi chưa có bằng chứng.

## 20. Những nhận định dễ nhầm

| Nhận định | Đúng/sai | Giải thích |
| --- | --- | --- |
| “RF = 3 thay thế backup.” | **Sai** | Replication không bảo vệ trước xóa nhầm hoặc logic corruption lan sang replicas. |
| “Một `nodetool snapshot` trên coordinator chụp toàn cluster.” | **Sai** | Snapshot là thao tác theo node, phạm vi phải được tổ chức. |
| “Snapshot luôn nhân đôi ngay dung lượng trên đĩa.” | **Sai** | Hard links có thể chia sẻ block, file cũ được giữ qua compaction. |
| “Hai DC dùng chung snapshot tag nghĩa dữ liệu cùng thời điểm.” | **Sai** | Không có atomic application snapshot xuyên node/DC mặc định. |
| “Backup ở cùng disk Cassandra vẫn bảo vệ khi disk chết.” | **Sai** | Cùng failure domain thì có thể mất cả hai. |
| “Incremental backup là commit log mutation stream.” | **Sai** | Thường là SSTable được tạo sau flush, cần base snapshot. |
| “Copy commit log đang mở là đã có PITR.” | **Sai** | Archival/replay cần cấu hình, mốc và kiểm thử riêng. |
| “`DESCRIBE TABLE` cho thấy dữ liệu đã backup đầy đủ.” | **Sai** | DDL chỉ cho biết schema. |
| “File checksum đúng chứng minh RPO đạt.” | **Sai** | Checksum không nói backup có đủ thời điểm và phạm vi cần thiết. |
| “`SELECT COUNT(*)` toàn bảng là cách verify rẻ.” | **Sai** | Có thể tạo scan rất lớn trên Cassandra. |
| “Có thể downgrade binary bất kỳ khi rolling upgrade lỗi.” | **Sai** | SSTable/schema/compatibility có thể không hỗ trợ downgrade. |
| “`LOCAL_QUORUM` biến nhiều SELECT thành snapshot nguyên tử.” | **Sai** | CL là số phản hồi replica của từng request, không phải transaction snapshot đa bảng. |
| “Bật TLS giúp backup tự khôi phục được.” | **Sai** | Còn metadata, khóa giải mã, schema, SSTable, RF và restore test. |
| “Có backup nhưng chưa diễn tập thì RTO vẫn chưa được chứng minh.” | **Đúng** | RTO chỉ đo được khi dữ liệu/ứng dụng đã thực sự phục vụ. |
| “Trước upgrade lớn nên lưu config/schema, dữ liệu và diễn tập restore cô lập.” | **Đúng** | Giảm rủi ro khóa cluster hoặc rollback bất khả thi. |

## 21. Bài tập có đáp án

**Bài 1.** Cluster RF = 3, chỉ chụp snapshot từ node N1. Có thể coi đây là bản sao đầy đủ mọi partition của keyspace không?

**Đáp án:** **Không.** N1 có thể chỉ giữ một phần các token ranges. Cần chiến lược backup bao phủ đủ tập node/replica/token và kiểm chứng dữ liệu.

**Bài 2.** Snapshot hoàn tất lúc 09:00, sự cố lúc 10:00, RPO yêu cầu 10 phút. Chỉ có snapshot 09:00 thì đủ chưa?

**Đáp án:** **Chưa.** Có thể mất tới khoảng 60 phút mutation nếu không có nguồn replay/archival hoặc chiến lược chốt mốc khác. RPO 10 phút cần chứng minh khôi phục tới ít nhất khoảng 09:50 trong ví dụ.

**Bài 3.** Vì sao snapshot cùng tag trên N1 và N2 không chứng minh hai node có trạng thái dữ liệu giống hệt tại một thời điểm?

**Đáp án:** Snapshot diễn ra tại mốc riêng trên từng node; replication/flush/CL và ghi đồng thời có thể làm dữ liệu khác nhau. Tag chỉ là nhãn quản trị.

**Bài 4.** Một operator khẳng định `system_auth` không cần backup vì đã xuất `CREATE TABLE` của tất cả bảng nghiệp vụ. Rủi ro là gì?

**Đáp án:** Có thể mất roles/permissions và không đăng nhập được. Phải bảo vệ auth data và có quy trình bootstrap/break-glass, đồng thời không copy mù metadata cluster cũ vào topology mới.

**Bài 5.** Full snapshot giữ bằng hard links. Sau major compaction, dung lượng `df` không giảm. Vì sao?

**Đáp án:** Snapshot còn giữ tham chiếu tới SSTable cũ, nên các block chưa được giải phóng dù active SSTable đã thay. Cần retention và xuất backup ngoài cluster, không xóa snapshot production tùy tiện.

**Bài 6.** Một backup file tải từ object storage có SHA-256 đúng, nhưng CQL restore không có hàng sentinel. Vì sao hash vẫn PASS?

**Đáp án:** Checksum chỉ kiểm tra byte của **file đã chọn**. Bản backup có thể sai node, thiếu files/ranges, sai schema hoặc snapshot trước lúc event được ghi. Cần manifest và dữ liệu logic.

**Bài 7.** Sau khi đổi SSTable format bằng công cụ nâng cấp, node chạy binary cũ không khởi động. Có thể quay lại version cũ chỉ bằng cách sửa package không?

**Đáp án:** **Không thể giả định vậy.** Downgrade có thể không hỗ trợ format/schema mới; phải theo version-specific recovery path và bản backup trước nâng cấp.

**Bài 8.** Dữ liệu có TTL 30 ngày, logical export rồi import lại hôm nay với TTL 30 ngày. Điều gì có thể sai?

**Đáp án:** Thời gian sống có thể bị gia hạn từ thời điểm import, trái retention gốc. Cần tính remaining TTL/expiry và xử lý delete/tombstone theo contract.

**Bài 9.** Restore rehearsal tạo cluster mới nhưng dùng cùng seed list và broadcast addresses của production. Đâu là nguy cơ?

**Đáp án:** Node test có thể giao tiếp hoặc cố join production, làm rối topology/identity và tăng rủi ro dữ liệu. Phải **cách ly network/cluster identity** và kiểm tra trước khi khởi động.

**Bài 10.** Lệnh import báo exit 0, `nodetool status` hiển thị `UN`. Có đủ để ghi `RESTORE_VERIFIED`?

**Đáp án:** **Chưa.** Cần kiểm tra file/token coverage, data key/value, TTL/delete, auth/TLS, ứng dụng Java và RPO/RTO.

**Bài 11.** Vì sao không chạy `SELECT COUNT(*)` toàn bộ bảng nhiều TB khi production đang cao tải?

**Đáp án:** Cassandra có thể phải quét lượng dữ liệu/SSTable rất lớn để đếm, gây I/O, CPU, tombstone scan và timeout. Nên đối soát phân mảnh theo scope/window với rate limit.

**Bài 12.** Nhóm đo restore hết 45 phút để start node, nhưng API mất thêm 60 phút mới phục vụ ổn định. RTO thực là 45 hay 105 phút?

**Đáp án:** Theo định nghĩa RTO **đến khi dịch vụ sẵn sàng theo tiêu chí nghiệp vụ**, thời gian trong ví dụ là khoảng **105 phút**, nếu mọi giai đoạn liên tiếp. Không đo RTO bằng start process đơn thuần.

## 22. Checklist cuối: tài liệu sẵn sàng để thay đổi hay chưa?

~~~text
PHẠM VI
[ ] Có RPO/RTO rõ ràng, phạm vi sự cố và yêu cầu consistency.
[ ] Có upgrade/downgrade path được version release hỗ trợ.
[ ] Ghi source/target Cassandra, JDK, driver, SSTable/feature compatibility.

CẤU HÌNH VÀ BẢO MẬT
[ ] Lưu schema DDL, topology/DC/rack/snitch/RF, seed và phiên bản config.
[ ] system_auth, role/permission và break-glass có phương án an toàn.
[ ] TLS/JMX/secret references, encryption key lifecycle và backup IAM đủ.

BACKUP
[ ] Snapshot đúng node/keyspace/table, tag, thời gian và đủ token coverage.
[ ] Snapshot đã xuất sang miền lỗi độc lập, không chỉ hard links cục bộ.
[ ] File components/checksum/manifest khớp, không có bản missing/unknown.
[ ] Nếu RPO yêu cầu: base + incremental + archive/replay chain có bằng chứng.
[ ] Retention/immutability, quyền truy cập và kiểm tra backup job đạt.

DIỄN TẬP KHÔI PHỤC
[ ] Cluster rehearsal thực sự cô lập khỏi production.
[ ] Restore tool và phiên bản phù hợp định dạng SSTable/schema.
[ ] Dữ liệu, TTL/delete và tính nhất quán theo watermark đã đối soát.
[ ] CQL/Java canary, RBAC/TLS, RF/CL, replica health và SLO đạt.
[ ] RPO và RTO được đo từ một lần phục hồi thực, có action log.

GO / NO-GO
[ ] Disk headroom, compaction, network/streaming, repair có capacity.
[ ] Có rollback cấu hình, recovery data, bản backup không bị biến đổi.
[ ] Có owner/approver, maintenance window, node order và stop criteria.
[ ] Nếu một tiêu chí thiếu bằng chứng, ghi NO-GO/EXCEPTION rõ ràng.
~~~

~~~mermaid
flowchart TD
    A["Chuẩn bị nâng cấp Cassandra"] --> B["Chốt RPO/RTO và version matrix"]
    B --> C["Inventory config, schema, system_auth, DC/RF và secret refs"]
    C --> D["Snapshot theo node + xuất backup ngoài cluster"]
    D --> E["Checksum, manifest, incremental/PITR nếu cần"]
    E --> F["Restore rehearsal trên cluster cô lập"]
    F --> G["CQL/Java canary, correctness, auth và RPO/RTO"]
    G --> H{"Các tiêu chí đều được chứng minh?"}
    H -->|Không| I["NO-GO: sửa coverage, restore path, capacity"]
    I --> D
    H -->|Có| J["GO: rolling change theo canary, giữ stop criteria"]
    J --> K["Postcheck từng node/DC, theo dõi SLO và khả năng phục hồi"]
~~~

**Tổng kết:** trước khi đổi phiên bản hoặc cấu hình Cassandra, cần bảo vệ không chỉ **SSTable**, mà cả **schema, `system_auth`, topology/DC/RF, runtime configuration và khóa/mật mã liên quan**. Snapshot theo node là một công cụ tốt để giữ SSTable, nhưng phải được **xuất ra miền lỗi độc lập, xác minh checksum/manifest, bao phủ đủ replica/token và gắn với RPO có nghĩa**. Quan trọng hơn, một **diễn tập restore cô lập** phải chứng minh dữ liệu và ứng dụng thực sự hoạt động với version được hỗ trợ, bao gồm **TTL/delete, quyền truy cập, consistency và p99**. Chỉ khi đó mới có cơ sở để quyết định **GO**; **rollback binary** và **restore data** là hai đường khác nhau, không được đánh đồng khi nâng cấp đã thay đổi định dạng SSTable.
