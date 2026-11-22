# Giới hạn downgrade/rollback và tiêu chí dừng hoặc tiếp tục triển khai

> **Chương:** Nâng cấp và tương thích  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Bối cảnh:** Apache Cassandra là cơ sở dữ liệu wide-column phân tán. Nâng cấp phải xét partition key, thiết kế bảng theo truy vấn, replication, consistency level, CQL, compaction, repair, sao lưu và ứng dụng Java.

## 1. Tình huống mở đầu và mục tiêu

Một cụm Cassandra đang được nâng từng node từ phiên bản **A** lên **B**. Node đầu tiên khởi động thành công, nhận ghi và đã flush dữ liệu ra SSTable. Sau đó ứng dụng Java gặp lỗi đọc. Một kỹ sư đề xuất hạ package về A và khởi động lại node.

Đề xuất này **chưa đủ an toàn để thực hiện**. Cassandra B có thể đã ghi SSTable, commitlog hoặc metadata mà A không hỗ trợ; schema hay tùy chọn kết nối cũng có thể thay đổi. Một bản binary cũ không tự đưa dữ liệu và trạng thái cluster về thời điểm trước nâng cấp.

Các quyết định phải tách bạch:

- **Downgrade:** chạy binary Cassandra phiên bản cũ hơn trên node đã nâng.
- **Rollback triển khai:** hoàn tác thay đổi ứng dụng, cấu hình hoặc phiên bản, tùy phần thực sự còn tương thích.
- **Roll forward:** sửa lỗi bằng cấu hình/bản vá/phiên bản mới được hỗ trợ.
- **Restore/recovery:** tái dựng dữ liệu từ điểm khôi phục và nguồn lịch sử phù hợp.
- **Pause/stop:** tạm giữ hoặc chấm dứt rollout trước khi đổi trạng thái thêm node.

Mục tiêu sau bài học:

1. Nêu được vì sao mixed-version compatibility **không đồng nghĩa** với binary downgrade được hỗ trợ.
2. Nhận diện những bước có thể khiến rollback dữ liệu/binary trở thành không an toàn.
3. Thiết kế cổng quyết định **GO, PAUSE, STOP, RECOVER** dựa trên dữ liệu đo.
4. Kiểm thử CQL/Java, replication và consistency level trong rolling upgrade.
5. Viết runbook bảo toàn dữ liệu và phương án phục hồi nếu không thể downgrade.
6. Đọc kết quả một canary và quyết định khi nào được nâng node kế tiếp.

> **Giới hạn áp dụng:** Quy định nâng cấp/hạ cấp phụ thuộc cặp phiên bản **chính xác**, bản phân phối, JDK, data format và hướng dẫn của nhà phát hành. Những phiên bản A/B và ngưỡng số liệu trong bài chỉ là mô hình giảng dạy. Không áp dụng thủ tục downgrade từ một phiên bản khác nếu chưa xác minh tài liệu chính thức và thử trong môi trường tương thích.

## 2. Thuật ngữ và ranh giới thực sự

| Thuật ngữ | Hành động | Có tự hoàn tác dữ liệu đã ghi? | Điều kiện |
|---|---|---|---|
| **PAUSE** | Không nâng thêm node; giữ trạng thái để phân tích | Không | Thiếu bằng chứng hoặc có cảnh báo cần kiểm tra |
| **STOP** | Dừng kế hoạch rollout hiện tại, giữ evidence và chọn hướng xử lý | Không | Vi phạm gate quan trọng |
| **Rollback ứng dụng/cấu hình** | Trả lại phiên bản Java service, feature flag hoặc cấu hình | Không | Phiên bản quay lại vẫn tương thích server/schema |
| **Binary downgrade** | Chạy Cassandra A trên node từng chạy B | Không | Được tài liệu hỗ trợ cho **trạng thái dữ liệu hiện tại** |
| **Roll forward** | Áp bản vá/config hoặc tiếp tục bản được hỗ trợ để sửa nguyên nhân | Không | Đường đi được hỗ trợ, đã test kịch bản gây lỗi |
| **Restore** | Khôi phục dữ liệu từ snapshot/backup/PITR hoặc nguồn ứng dụng | Có thể quay về một mốc | Backup đủ, schema/khóa hợp lệ, RPO/RTO và dữ liệu ghi sau mốc được xử lý |

**Rollback app không phải binary downgrade Cassandra.** Java driver cũ có thể vẫn hoạt động với server mới nếu compatibility matrix cho phép, trong khi binary Cassandra A có thể không đọc được SSTable do B ghi. Ngược lại, rollback Java driver cũng phải kiểm thử native protocol, TLS, prepared statement, schema và retry.

**Restore không mặc nhiên là RPO = 0.** Nếu backup có cutoff 08:00 nhưng sự cố xảy ra 10:30, các ghi hợp lệ được xác nhận trong khoảng đó có nguy cơ mất trừ khi có cơ chế bổ sung được kiểm chứng để phát lại.

## 3. Vì sao Cassandra có giới hạn downgrade?

### 3.1. SSTable: tính tương thích thường bất đối xứng

Cassandra ghi memtable ra **SSTable bất biến**, sau đó compaction có thể ghi SSTable mới. Trong một đường nâng cấp được hỗ trợ, B có thể đọc dữ liệu định dạng cũ của A. Tuy nhiên **A chưa chắc đọc được tệp B tạo**.

~~~mermaid
flowchart LR
    A["SSTable do A tạo"] --> B["Cassandra B đọc và xử lý"]
    B --> C["Flush hoặc compaction"]
    C --> D["SSTable B có thể dùng định dạng mới"]
    D --> E{"A có đọc được tệp mới?"}
    E -->|Được guide xác nhận| F["Đánh giá downgrade có điều kiện"]
    E -->|Không / không rõ| G["Không cài A đè lên data directory"]
~~~

Đặc biệt, **không mặc định rằng chỉ sau khi chạy công cụ chuyển đổi SSTable mới có nguy cơ**. Một node mới có thể tạo SSTable qua flush/compaction bình thường. Nếu phiên bản yêu cầu một bước hậu nâng cấp bằng công cụ như **nodetool upgradesstables**, bước ấy có thể làm tăng I/O và thu hẹp lựa chọn quay lui; phải đọc hướng dẫn chính xác trước khi chạy.

Những câu hỏi bắt buộc:

1. A đọc được những SSTable format nào, B tạo format nào?
2. Node đã flush hoặc compact dữ liệu sau khi chạy B chưa?
3. Có thao tác hậu nâng cấp nào thay đổi định dạng hoặc cần disk headroom lớn?
4. Binary A có được nhà phát hành hỗ trợ trên data directory đó không?
5. Nếu không, restore cần chạy Cassandra/loader phiên bản nào và bằng bộ backup nào?

### 3.2. Commitlog và metadata

Các thành phần khác cũng có thể tạo chướng ngại:

- **Commitlog:** định dạng ghi, replay hoặc cấu hình có thể khác giữa phiên bản.
- **Schema/system metadata:** CQL, UDT, index, table ID, các bảng hệ thống hoặc schema version có thể thay đổi.
- **Internode protocol/gossip:** khả năng liên lạc giữa node khác phiên bản có giới hạn.
- **Streaming, hints và repair:** định dạng trao đổi dữ liệu hoặc trạng thái bảo trì có thể bị ràng buộc theo phiên bản.
- **Cấu hình/JVM:** JDK được hỗ trợ, flag đã loại bỏ, cấu hình Cassandra, TLS và plugin khác nhau.
- **Topology/token ownership:** nếu đợt nâng cấp đi kèm thay node, bootstrap, decommission hoặc đổi RF, khôi phục không còn là thay package đơn giản.

**Package manager chỉ quản lý binary; nó không khôi phục lại trạng thái dữ liệu/metadata cũ.** Nếu binary cũ chạy lại và báo lỗi vì dữ liệu mới, không tùy ý xóa commitlog, SSTable hoặc system table để ép khởi động. Hành động đó có thể làm mất ghi hợp lệ và phá dữ liệu.

### 3.3. Mixed-version không phải quyền downgrade

Một upgrade guide có thể cho phép **A và B đồng thời tồn tại trong thời gian rolling upgrade** để phục vụ request trong lúc thay node. Điều này **không chứng minh** rằng một node đã chạy B, ghi SSTable mới rồi có thể an toàn khởi động lại bằng A.

Phải kiểm tra riêng:

- Đường **A → B** có được hỗ trợ trực tiếp hay cần bản trung gian?
- A/B được phép mixed-version trong bao lâu và có hạn chế schema/feature nào?
- Những bước hậu nâng cấp nào chỉ thực hiện khi mọi node đã ở B?
- Có hướng dẫn **downgrade** tường minh hay không?
- Có thời điểm một chiều sau schema migration, SSTable conversion hoặc thay đổi topology?
- Driver Java, native protocol và TLS có hoạt động trong giai đoạn hỗn hợp?

Nếu tài liệu không có câu trả lời, đánh dấu **UNKNOWN**, không tự suy ra là được phép.

## 4. Những điểm có thể trở thành “không thể quay lui”

Bảng sau mô tả các **cổng đánh giá**, không khẳng định mọi bước luôn một chiều ở mọi bản Cassandra.

| Cổng | Trạng thái | Điều phải chứng minh trước khi tiếp tục |
|---|---|---|
| **G0 — trước nâng cấp** | Toàn cluster còn ở A | Backup/restore drill, đường nâng, inventory và baseline đủ |
| **G1 — node đầu tiên ở B** | Cluster có thể đang mixed-version | Compatibility internode, CL, driver và điều kiện downgrade |
| **G2 — B đã nhận ghi/flush** | Có thể xuất hiện SSTable/commitlog mới | Tài liệu xác nhận trạng thái còn đọc ngược được hoặc chuyển sang kế hoạch recovery |
| **G3 — schema/feature mới** | Ứng dụng có thể dùng cấu trúc chỉ B hỗ trợ | Không bật trái hướng dẫn khi còn node A; có kế hoạch quay về/di trú dữ liệu |
| **G4 — hậu nâng cấp** | Upgrade SSTables, tác vụ metadata/maintenance theo guide | Phê duyệt riêng cho thao tác có thể một chiều, disk headroom, backup |
| **G5 — topology mới** | Thêm/bớt node, đổi DC/RF hoặc token ownership | Đánh giá lại khả năng phục hồi và phạm vi ảnh hưởng |

Không có “một điểm không thể quay lui” chung cho mọi phiên bản. Đội vận hành phải ghi **tên bước, hướng dẫn chính thức, data format hiện tại, bằng chứng và người chịu trách nhiệm**.

**Lưu ý về compaction/repair:** chúng là cơ chế quản lý dữ liệu phân tán quan trọng nhưng không tự hiểu tính đúng đắn nghiệp vụ. Đặc biệt, chạy repair khi có nghi ngờ dữ liệu đã bị xóa sai có thể phát tán trạng thái không mong muốn. Không dùng repair như một nút “undo”.

## 5. Bốn trạng thái quyết định: GO, PAUSE, STOP, RECOVER

### 5.1. GO — tiếp tục đợt node kế tiếp

Chỉ **GO** khi mọi gate đã chốt đều đạt:

- **Tương thích:** source/target, JDK và bản phân phối đúng; upgrade guide cho phép trạng thái hiện tại.
- **Topology:** node đã join theo kỳ vọng, schema agreement ổn, DC/rack/token ownership đúng.
- **Availability:** đủ replica khỏe để phục vụ consistency level yêu cầu sau khi đưa node tiếp theo ra bảo trì.
- **Correctness:** CQL/Java fixtures, dữ liệu theo partition key, TTL/DELETE và invariant nghiệp vụ không sai.
- **Hiệu năng:** latency p95/p99, throughput, timeout/retry trong ngân sách đã thỏa thuận.
- **Tài nguyên:** heap/GC, native RSS, disk, network, compaction, repair/streaming còn đủ dư địa.
- **Recovery:** backup hoàn chỉnh và khả năng khôi phục vẫn còn hợp lệ trước các bước rủi ro.

Quyết định GO phải ghi **đợt node, thời điểm, các chỉ số, phạm vi và người phê duyệt**. Nó không tự động áp dụng cho toàn chiến dịch.

### 5.2. PAUSE — tạm dừng để biết chuyện gì đang xảy ra

Chọn PAUSE khi chưa có bằng chứng về mất dữ liệu/nguy cơ nghiêm trọng nhưng chưa đủ điều kiện GO, ví dụ:

- p99 tăng và chưa biết do phiên bản mới hay compaction/truy vấn nóng.
- Chỉ số giám sát bị đổi tên nên thiếu telemetry cần dùng.
- Schema agreement hoặc node state dao động, chưa biết có kéo dài hay không.
- Một integration test chưa chạy xong, còn cảnh báo startup chưa được giải thích.
- Backup/restore evidence chưa đủ để vượt bước hậu nâng cấp.

Trong PAUSE, **không nâng node tiếp theo**. Ghi timeline/log/metrics, phân công owner, hạn đánh giá lại và điều kiện chuyển sang GO hoặc STOP.

### 5.3. STOP — chấm dứt mở rộng rollout

Phải STOP nếu có bằng chứng:

- Sai dữ liệu, mất row, TTL/tombstone bất thường, invariant nghiệp vụ bị vi phạm.
- Replica không đủ để đáp ứng CL, read/write unavailable hoặc timeout vượt stop gate.
- Đường nâng cấp/mixed-version bị phát hiện không được hỗ trợ.
- Node liên tục crash/OOM, disk full, lỗi bảo mật nghiêm trọng hoặc kết nối internode hỏng.
- Binary mới tạo dữ liệu/metadata mà kế hoạch rollback không xử lý được.
- Backup sạch hoặc quyền giải mã đã mất trước thao tác một chiều.

**STOP không đồng nghĩa chạy binary cũ.** Có thể giữ node đã nâng để chẩn đoán, sửa cấu hình, áp fix/roll forward được hỗ trợ, rollback app hoặc dùng backup.

### 5.4. RECOVER — khi trạng thái hiện tại không thể cứu an toàn tại chỗ

Chọn RECOVER khi cần phục hồi trạng thái dữ liệu/hạ tầng, như corruption, xóa sai đã replicate, thiếu replica hợp lệ hoặc dữ liệu không phù hợp để downgrade. Dựng môi trường phục hồi cô lập, chọn recovery point rõ ràng, nạp bằng công cụ phù hợp phiên bản, kiểm tra dữ liệu, tính RPO/RTO và chỉ chuyển traffic sau nghiệm thu.

~~~mermaid
flowchart TD
    A["Có vấn đề trong nâng cấp"] --> B["PAUSE: không nâng node mới"]
    B --> C{"Sai dữ liệu / mất quorum / lỗi bảo mật nghiêm trọng?"}
    C -->|Có| D["STOP: bảo toàn dữ liệu và evidence"]
    C -->|Không| E["Chẩn đoán theo số liệu"]
    E --> F{"Mọi gate đã đạt?"}
    F -->|Có| G["GO: đợt tiếp theo"]
    F -->|Chưa| H["Tiếp tục PAUSE hoặc STOP theo mức độ"]
    D --> I{"Fix forward hoặc rollback phần liên quan được hỗ trợ?"}
    I -->|Có và đã kiểm thử| J["Sửa có kiểm soát, xác minh lại"]
    I -->|Không| K["RECOVER từ backup/nguồn độc lập"]
~~~

## 6. Định nghĩa gate bằng chứng, baseline và ngưỡng

| Nhóm gate | Phép đo hoặc kiểm tra | Lý do |
|---|---|---|
| **Binary/topology** | Version từng node, nodetool status, schema agreement, DC/rack | Phát hiện node không join hoặc cluster mixed-version ngoài kế hoạch |
| **Replication/CL** | Available replicas, read/write timeout và unavailable theo DC | RF cấu hình không chứng minh replica thực tế khỏe |
| **Dữ liệu** | So event ID, giá trị, thứ tự clustering, TTL/DELETE, partition mẫu | SELECT chạy không exception vẫn có thể trả sai dữ liệu |
| **Ứng dụng Java** | Handshake, auth/TLS, prepared/bind, paging, retry, query correctness | Kiểm chứng các đường truy cập quan trọng |
| **Latency/throughput** | p50/p95/p99 theo query shape, RPS, tải tương đương | Trung bình toàn cluster dễ che regression |
| **JVM/OS** | GC pause, heap, native/RSS, cgroup, page cache, disk/network | Phát hiện OOM và mất I/O headroom |
| **Bảo trì** | Compaction backlog, repair, streaming, pending tasks, hints | Công việc nền có thể khiến đợt tiếp theo mất availability |
| **Backup/restore** | Manifest, checksum, schema, khóa, kết quả restore drill | Chứng minh có đường phục hồi khi cần |

**Không lấy node UN (Up/Normal) làm bằng chứng duy nhất.** Node có thể lên bình thường nhưng dữ liệu theo một số token range thiếu hoặc Java service vẫn lỗi.

### 6.1. Ví dụ ngưỡng minh họa

Giả sử đội vận hành đã chọn một tiêu chí kiểm chứng riêng cho workload:

~~~text
Sau mỗi node, quan sát ít nhất 15 phút ổn định ở tải tương đương baseline.
- Query shape trọng yếu: p99 tăng tối đa 20% so với baseline.
- Read/write timeout phải nằm trong error budget của ứng dụng.
- Không sai fixture hoặc invariant nghiệp vụ.
- Không mất quorum/replica availability.
- Disk, GC, streaming/compaction và node health trong ngưỡng nội bộ.
- Backup/khóa/restore path vẫn sẵn sàng.

Nếu thiếu telemetry hoặc phép test => PAUSE
Nếu sai dữ liệu, mất quorum, lỗi bảo mật nghiêm trọng => STOP
Nếu tất cả đạt và chủ sở hữu nghiệm thu => GO
~~~

**15 phút và 20% là số giả định cho bài thực hành**, không phải ngưỡng chuẩn của Cassandra. Thời gian quan sát và mức chấp nhận phải lấy từ SLO/error budget, baseline tải, phân phối kích thước partition, loại ổ đĩa và độ ổn định môi trường. Lỗi dữ liệu nghiêm trọng phải STOP ngay, không chờ hết cửa sổ.

## 7. Trước canary: kiểm kê và phương án khôi phục

### 7.1. Phiếu phiên bản và môi trường

~~~text
Cluster:                   <id / môi trường>
Cassandra nguồn:          <version + build, từng node>
Cassandra đích:           <version + build>
Bản phân phối:            <Apache/vendor/managed>
JDK server nguồn/đích:    <runtime và flags>
Driver/JDK ứng dụng:      <artifact + version>
DC/rack/node/RF/CL:       <cấu hình và trạng thái thực>
SSTable/commitlog/schema: <format và trạng thái hiện tại>
OS/container/config:      <image, cassandra.yaml, JVM options>
Tài liệu nâng/downgrade:  <URL/section chính thức>
Mixed-version window:     <điều kiện theo guide>
Điểm không thể quay lui:  <bước, bằng chứng>
Backup:                   <ID, cutoff, checksum, schema, KMS>
Restore drill:            <ngày, kết quả, RPO/RTO>
Runbook/owner:            <version, người quyết định>
~~~

Mọi phiên bản phải lấy từ hệ thống thực tế và build chuẩn bị deploy. Nếu một cluster đang mixed-version từ một lần bảo trì trước, phải biết rõ trạng thái **từng node**.

### 7.2. Kiểm tra chỉ đọc trước rollout

Trên cluster được phép kiểm tra, với cú pháp đúng phiên bản:

~~~bash
nodetool status
nodetool info
nodetool compactionstats
nodetool tpstats
nodetool tablestats shop.events_by_tenant_day
~~~

Trong **cqlsh**:

~~~sql
SELECT release_version, schema_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'shop';
~~~

**system.local chỉ cho biết node được kết nối**, không chứng minh version của mọi node. Thu số liệu và metadata từ các node/nguồn telemetry phù hợp.

Không chạy lệnh có tác dụng thay đổi dữ liệu/topology như **repair, upgradesstables, cleanup, decommission** chỉ để xem baseline. Những thao tác này cần runbook riêng, I/O headroom và điều kiện phê duyệt.

### 7.3. Replication và consistency level trong cửa sổ bảo trì

Với RF = 3 trong một local DC, request dùng **LOCAL_QUORUM** thường cần phản hồi từ ít nhất **hai replica** tại DC đó. Khi một node dừng để nâng cấp, hai replica còn lại phải thực sự khỏe với dữ liệu hợp lệ. RF không bảo đảm những replica còn lại đều online, không bị GC pause hoặc disk saturation.

Tương tự, tăng consistency level không chữa được dữ liệu sai đã replicate. Repair đồng bộ replica chứ không hiểu thao tác DELETE nào sai về nghiệp vụ.

### 7.4. Backup trước bước rủi ro

Một backup đáng tin cậy cần:

1. Bao phủ đủ node/token ranges và bảng; snapshot một node không mặc nhiên là backup toàn cluster.
2. Có manifest, checksum, schema, phiên bản, khóa giải mã và cutoff dữ liệu được xác nhận.
3. Được lưu **ngoài miền lỗi phù hợp**, tách quyền xóa/đọc và retention.
4. Được kiểm thử **restore trên môi trường cô lập**, dùng phiên bản tương thích với SSTable.
5. Có kế hoạch đối soát/khôi phục các ghi hợp lệ sau mốc backup.

Nếu bản backup cuối chưa đủ hoặc không giải mã được, **NO-GO** cho bước có thể một chiều. Replica không thay thế backup khi cả cluster nhận lệnh xóa/ghi đè sai.

## 8. Rolling upgrade theo các cổng quyết định

**Thứ tự nâng node, điều kiện mixed-version, lệnh shutdown/startup và thao tác hậu nâng cấp phải theo guide đúng cặp phiên bản**. Quy trình sau là cấu trúc kiểm soát, không phải bộ lệnh nâng cấp áp dụng cho mọi bản.

~~~mermaid
flowchart TD
    A["G0: preflight version/backup/topology"] --> B{"Đủ điều kiện?"}
    B -->|Không| X["NO-GO: khắc phục blocker"]
    B -->|Có| C["Nâng canary theo upgrade guide"]
    C --> D["Kiểm tra join, CQL, Java, CL, tài nguyên"]
    D --> E{"Sai dữ liệu / mất quorum?"}
    E -->|Có| S["STOP và đánh giá recovery"]
    E -->|Không| F{"Có cảnh báo UNKNOWN hoặc gate chưa đạt?"}
    F -->|Có| P["PAUSE, không nâng node tiếp theo"]
    F -->|Không| G["GO node kế tiếp"]
    G --> H{"Đã hoàn tất tất cả node?"}
    H -->|Không| C
    H -->|Có| I["Post-upgrade gate; đánh giá bước một chiều"]
    I --> J["Xác minh cluster + backup/restore + sign-off"]
~~~

### G0 — Trước canary

Chốt đường nâng, tất cả known issues/removed options, trạng thái cluster, baseline, backup/restore drill, app/driver compatibility và người quyết định. Còn mục **UNKNOWN quan trọng** thì chưa GO.

### G1 — Node canary

Sau khi nâng một node:

1. Xác nhận binary, JDK, config đúng và không có startup warning chưa hiểu.
2. Kiểm tra node join, DC/rack/token, schema agreement và gossip/internode connectivity.
3. Đo CL, read/write timeout, số retry, p95/p99, GC, disk, compaction và streaming.
4. Chạy CQL fixture và Java integration test với các partition key đại diện.
5. Xem đã ghi SSTable/commitlog/metadata mới chưa để cập nhật trạng thái downgrade.
6. Chỉ GO node kế tiếp sau khi owner nghiệm thu đủ gate.

### G2 — Các đợt node tiếp theo

Lặp kiểm tra trên từng đợt, đồng thời quan sát **toàn cluster**. Một canary khỏe không chứng minh hệ thống vẫn ổn khi nhiều node có backlog streaming, compaction, hinted handoff hoặc repair. Giữ những tính năng/schema chỉ phiên bản mới có **chưa bật** nếu upgrade guide yêu cầu.

### G3 — Hoàn tất bản đích

Kiểm tra mọi node đã ở bản đích, không có mixed-version không dự kiến; thực hiện lại CQL/Java fixture, đo SLO, thử backup/restore và các công cụ quản trị. Chỉ làm **post-upgrade actions có thể một chiều** khi đã có gate riêng, bằng chứng và phương án recovery.

## 9. Chọn rollback ứng dụng, roll forward hay restore khi gặp lỗi

### 9.1. Bảng quyết định theo triệu chứng

| Tín hiệu | Hành động tức thời | Hướng giải quyết sau khi đánh giá |
|---|---|---|
| Java app handshake lỗi do cấu hình TLS/CA | PAUSE, không nâng node thêm | Sửa cấu hình/driver; rollback app nếu vẫn tương thích server đích |
| Node canary không join vì flag JVM bị loại bỏ | PAUSE; STOP nếu mất replica availability | Sửa runtime/config của bản đích hoặc xử lý theo downgrade guide |
| p99 tăng trong lúc compaction, dữ liệu vẫn đúng | PAUSE, đo disk/GC/I/O và so tải | Giảm áp lực theo runbook, sửa nguyên nhân hoặc dùng fix forward |
| Read/write unavailable, thiếu local quorum | STOP | Phục hồi replica availability trước khi xem xét triển khai tiếp |
| Fixture phát hiện dữ liệu sai/row bị hồi sinh | STOP ngay, giữ evidence | Phân tích và chọn restore/roll forward an toàn theo tình huống |
| Binary cũ không đọc được SSTable đã ghi bởi bản mới | Không downgrade trực tiếp | Giữ phiên bản đọc được dữ liệu, sửa/roll forward hoặc restore bản sạch |
| Backup không giải mã được trước công việc một chiều | NO-GO/STOP | Khôi phục năng lực DR, không tiến qua cổng |
| Lỗi bảo mật nghiêm trọng ở auth/TLS/role | STOP | Khôi phục kiểm soát truy cập bằng cơ chế được hỗ trợ |

**STOP không tự động làm node được cài lại phiên bản trước.** Một binary downgrade không được hỗ trợ có thể làm tình hình xấu hơn và cản trở recovery. Chỉ sử dụng đường hạ phiên bản được tài liệu xác nhận **với dữ liệu hiện tại**.

### 9.2. Rollback chỉ ứng dụng Java khi phù hợp

Nếu server B khỏe nhưng bản cập nhật Java service hoặc driver gây lỗi, có thể rollback tầng ứng dụng **nếu**:

- Driver cũ có compatibility matrix hỗ trợ server B/native protocol.
- Schema/CQL/codec/UDT, prepared metadata và paging của app cũ còn hợp lệ.
- Xác thực, chứng chỉ TLS, hostname validation và quyền vẫn đúng.
- Retry policy/idempotency không tạo dữ liệu trùng; event ID cho cùng yêu cầu được giữ ổn định.
- Các phép test đọc/ghi và invariant chạy được sau rollback app.

Điều này không đòi hỏi hạ binary Cassandra nếu vấn đề được cô lập hoàn toàn ở client.

### 9.3. Khi nào roll forward?

Nếu có bản vá hoặc cấu hình mới **được nhà phát hành hỗ trợ** và xử lý đúng nguyên nhân, roll forward có thể an toàn hơn một downgrade không tương thích dữ liệu. Nhưng vẫn phải kiểm tra release notes, known issues, JDK/config, mixed-version, backup, test tại staging/canary và stop gates. **Không mặc định “cứ cài bản mới nhất là sửa được”.**

### 9.4. Khi nào recovery từ backup?

Chọn restore khi cần quay về mốc dữ liệu sạch, khi binary cũ không đọc được trạng thái hiện tại, hoặc khi các replica không còn bản dữ liệu đúng/khả dụng.

Các bước khái niệm:

1. Dừng nguồn gây hỏng dữ liệu, bảo toàn log, backup và timeline sự cố.
2. Chọn backup **COMPLETE** có mốc cutoff, schema, manifest, checksum, độ phủ token và khóa giải mã đầy đủ.
3. Dựng cluster phục hồi **cô lập** bằng Cassandra/JDK/loader tương thích.
4. Nạp SSTable, incremental data hoặc commitlog archive theo runbook đúng phiên bản, không phát lại mù thay đổi gây lỗi.
5. Đối soát partition key, tombstone/TTL, các bảng theo truy vấn và những ghi hợp lệ sau cutoff.
6. Chạy test CQL/Java, đo RPO/RTO thực tế, rồi mới chuyển traffic có kiểm soát.

**Không copy tùy tiện SSTable cũ vào cluster production đang nhận ghi**: thời điểm dữ liệu khác nhau có thể gây lỗi schema/tombstone và hồi sinh dữ liệu đã DELETE hợp lệ. Repair cũng không tự biết giá trị nào đúng về nghiệp vụ.

## 10. Kiểm chứng CQL theo khóa phân vùng

Xét bảng cho access pattern “lấy sự kiện gần nhất của một tenant trong một ngày”:

~~~sql
-- Giả sử keyspace shop đã tồn tại và replication phù hợp topology.
CREATE TABLE IF NOT EXISTS shop.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);

-- Fixture chỉ tạo trên môi trường staging/kiểm thử.
INSERT INTO shop.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'ORDER_CREATED',
    '{"order":"test-001"}'
);
~~~

Truy vấn kiểm chứng:

~~~sql
SELECT happened_at, event_id, event_type, payload
FROM shop.events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

Cả **tenant_id** và **event_day** thuộc partition key; driver có thể sử dụng routing key khi truy vấn được chuẩn bị và bind đủ khóa, tùy metadata. **Clustering columns** quyết định thứ tự trong partition.

Phép kiểm chứng cần so **event_id, event_type, payload, thứ tự hàng** với fixture trước nâng cấp. Dùng nhiều partition/token range, không chỉ một tenant, và bao gồm dữ liệu đã UPDATE, DELETE, TTL hết hạn, collection/UDT nếu workload sử dụng. Câu SELECT trả 0 hàng mà không có exception **không chứng minh** dữ liệu đúng nếu fixture phải tồn tại.

Trong production, ưu tiên truy vấn đọc theo partition key và kiểm tra invariant không phá dữ liệu. Không chạy scan toàn bảng hoặc ghi thử hàng loạt lên dữ liệu thật chỉ để kiểm tra canary.

## 11. Ví dụ Java driver 4.x làm gate cho rollout

Một smoke test nhỏ nên **kiểm tra dữ liệu mong đợi**, không chỉ mở được kết nối.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class UpgradeGoGateSmokeTest {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        UUID expectedEventId = UUID.fromString(
            "22222222-2222-4222-8222-222222222222");
        LocalDate day = LocalDate.of(2026, 11, 21);

        // Chỉ trỏ đến cluster thử nghiệm, không dùng production.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_id, event_type, payload " +
                "FROM shop.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            ResultSet result = session.execute(
                query.bind(tenantId, day, 20)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM));

            boolean matched = false;
            for (Row row : result) {
                if (expectedEventId.equals(row.getUuid("event_id"))
                    && "ORDER_CREATED".equals(
                        row.getString("event_type"))
                    && "{\"order\":\"test-001\"}".equals(
                        row.getString("payload"))) {
                    matched = true;
                    break;
                }
            }

            if (!matched) {
                throw new IllegalStateException(
                    "STOP: dữ liệu khác fixture sau nâng cấp");
            }
            System.out.println("PASS: đã kiểm tra event mẫu");
        }
    }
}
~~~

**Điều kiện chạy:**

- Ví dụ dùng package của Java driver **4.x** và schema/fixture ở mục 10.
- Cluster có datacenter **dc1**, đủ replica để đáp ứng **LOCAL_QUORUM**; nếu chỉ một node, cần mô hình RF/CL khác và không suy kết quả ra production.
- Cần thiết lập authentication và TLS theo chính sách của cluster thực tế; ví dụ lược bỏ để tập trung vào truy vấn. Không được vô hiệu hóa xác minh chứng chỉ để cho test chạy.
- Trong ứng dụng thật, **CqlSession** và **PreparedStatement** nên được tái sử dụng, thay vì khởi tạo trong mỗi request.
- Một fixture thành công **không** chứng minh throughput, timeout dưới tải, paging lớn hay dữ liệu của mọi partition. Cần integration/soak tests với nhiều khóa và failure cases.

Trong giai đoạn mixed-version được hỗ trợ, chạy cùng bộ test tại bản nguồn, sau canary và sau khi toàn cluster lên bản đích. Thu mã kết thúc, latency, retry, exception type và người nghiệm thu để đưa vào gate.

## 12. Tình huống ra quyết định có số liệu

**Kịch bản giả định:** local DC có RF = 3, ứng dụng Java đọc/ghi **LOCAL_QUORUM**. Cluster đang nâng theo một đường đã được xác minh; N1 chạy B, N2 và N3 còn A.

Trước nâng cấp, một truy vấn trọng yếu đạt **p99 = 80 ms** ở tải **2.000 request/giây**. Đội vận hành chốt gate thử nghiệm: p99 không vượt baseline hơn **25%** dưới tải tương đương, không mất quorum, không sai dữ liệu.

Sau khi nâng N1:

| Tín hiệu | Quan sát | Đánh giá |
|---|---|---|
| N1 | UP/NORMAL, binary B | Chỉ đạt gate khởi động cơ bản |
| N2 | Disk I/O cao, có write timeout | Replica còn lại chưa khỏe |
| p99 read | Tăng từ 80 lên 125 ms | Vượt ngưỡng 100 ms |
| CQL fixture | Event ID và payload khớp | Chưa thấy lỗi dữ liệu trong phạm vi mẫu |
| Compaction | Backlog tăng trên N2 | Cần phân tích I/O |
| Backup | COMPLETE, restore drill PASS | Có đường recovery đã kiểm tra |

**Quyết định: PAUSE, không nâng N2.** Vấn đề p99 và tải N2 chưa được giải thích. Nếu tiếp tục nâng node khác, cluster có thể mất đủ replica để phục vụ local quorum.

Các bước tiếp theo:

1. Thu timeline, log, p99 theo query shape, disk latency, compaction và timeout theo replica.
2. Phân biệt regression của B với vấn đề N2 có từ trước.
3. Nếu phát hiện **mất quorum hoặc dữ liệu sai**, chuyển **STOP** ngay.
4. Nếu xác định nguyên nhân và khắc phục bằng biện pháp được hỗ trợ, chạy lại gate với workload tương đương.
5. Chỉ chuyển sang GO khi owner đã xem bằng chứng, đồng thời xác nhận đường recovery còn hoạt động.

**Không tự hạ N1 về A chỉ vì p99 tăng.** Trước đó phải xác minh bản A có đọc được trạng thái SSTable/commitlog/schema của N1 hiện tại hay không.

### 12.1. Tình huống thứ hai: lỗi dữ liệu sau bước một chiều

Cluster đã hoàn tất bản B, thực hiện một bước hậu nâng cấp được tài liệu xác định là làm thay đổi định dạng không tương thích với A. Sau đó fixture cho thấy hàng đã DELETE hợp lệ xuất hiện lại.

Hành động:

- **STOP** mọi thay đổi tiếp theo và chặn nguồn gây sai dữ liệu.
- Bảo toàn evidence và xác minh phạm vi/timing trên nhiều token range.
- **Không cài lại A** lên data directory đã đổi định dạng.
- Đánh giá fix/roll forward có hỗ trợ hoặc khôi phục từ điểm sạch trên cluster cô lập.
- Chú ý TTL/tombstone và dữ liệu hợp lệ phát sinh sau cutoff.
- Chỉ mở traffic khi kiểm tra ứng dụng/replica và invariant đã đạt.

Chạy repair ngay khi chưa biết dữ liệu nào đúng có thể làm khó điều tra. Repair chỉ giúp hội tụ trạng thái replica theo ngữ nghĩa Cassandra, không hiểu tính hợp lệ của một DELETE nghiệp vụ.

## 13. Mẫu ghi nhận quyết định GO/PAUSE/STOP/RECOVER

~~~yaml
change_id: "cassandra-upgrade-drill-2026-11-21"
environment: "staging"
source_version: "<exact-source-build>"
target_version: "<exact-target-build>"
documentation:
  upgrade_guide: "<verified-url-and-section>"
  downgrade_policy: "<verified-url-and-section>"
  mixed_version_constraints: "<documented-limit>"
node_batch:
  nodes: ["node-01"]
  started_at_utc: "<actual-time>"
  verified_at_utc: "<actual-time>"
compatibility:
  sstable_readable_by_source: "UNKNOWN"
  new_schema_feature_enabled: false
  irreversible_post_upgrade_action_done: false
recovery:
  backup_id: "<verified-backup-id>"
  cutoff_utc: "<verified-cutoff>"
  restore_drill: "PASS"
gates:
  node_health: "PASS"
  schema_agreement: "PASS"
  quorum_availability: "PASS"
  java_driver_tls_auth: "PASS"
  cql_fixture: "PASS"
  latency_error_budget: "PAUSE"
  compaction_disk_memory: "INVESTIGATE"
decision:
  state: "PAUSE"
  reason: "p99 vượt ngưỡng, replica cũ chịu I/O cao"
  owner: "<responsible-role>"
  evidence: "<logs-metrics-tests>"
  next_review_utc: "<scheduled-time>"
  next_action: "chẩn đoán I/O trước khi nâng node tiếp"
~~~

Đây là **mẫu hồ sơ nội bộ để tham khảo**, không phải cấu hình Cassandra. Giá trị **UNKNOWN** ở trường sstable_readable_by_source có nghĩa **binary downgrade chưa được phép xem như kế hoạch phục hồi đã phê duyệt**.

### 13.1. Vai trò trong quyết định

- **DBA/SRE:** topology, storage, replica availability, compaction, repair và compatibility format.
- **Java/application owner:** query correctness, driver/TLS, retry/timeout, consistency level, SLO.
- **Security owner:** nếu có thay đổi authenticator/authorizer, chứng chỉ, KMS và quyền truy cập.
- **Change/incident owner:** tổng hợp bằng chứng, ghi thời gian, quyết định state và điều phối hướng xử lý.

Một câu “tiếp tục được” không có baseline, phạm vi, version, bằng chứng và owner sẽ khó kiểm tra khi có sự cố.

## 14. Bài tập tình huống

### Bài 1 — Mixed-version có phải downgrade support?

Tài liệu cho phép A và B cùng hoạt động trong rolling upgrade. Node B đã tạo SSTable mới, người vận hành muốn cài A trở lại.

**Câu hỏi:** Có đủ cơ sở để thực hiện không?

**Đáp án gợi ý:** Chưa. Phải kiểm tra hỗ trợ binary downgrade với trạng thái SSTable/commitlog/metadata đang có. Mixed-version không tự bảo đảm định dạng B đọc ngược được bởi A.

### Bài 2 — Node UN nhưng CL lỗi

N1 chạy B và báo **UN**, N2 chập chờn, ứng dụng có read timeout ở **LOCAL_QUORUM**.

**Câu hỏi:** GO, PAUSE hay STOP?

**Đáp án gợi ý:** Ít nhất **PAUSE**. Nếu quorum/availability gate đã bị vi phạm hoặc lỗi có tính nghiêm trọng, **STOP**. Trạng thái của riêng N1 không chứng minh cluster đủ replica.

### Bài 3 — Rollback Java driver

Bản Cassandra B vẫn khỏe, nhưng bản driver Java mới lỗi khi giải mã UDT. Driver cũ từng hoạt động tốt với A.

**Câu hỏi:** Có thể rollback driver mà không downgrade Cassandra không?

**Đáp án gợi ý:** Có thể cân nhắc nếu driver cũ được hỗ trợ với B và test schema/CQL/UDT/TLS/CL/paging đạt. Không suy từ việc driver cũ từng chạy tốt với A.

### Bài 4 — Bước một chiều và backup

Một thao tác hậu nâng cấp được guide ghi là tạo SSTable không đọc được bằng A. Bản backup ngoài miền lỗi mới nhất chưa thử giải mã/restore.

**Câu hỏi:** Có nên chạy ngay?

**Đáp án gợi ý:** **NO-GO.** Cần một bộ backup COMPLETE có schema, checksum, khóa; thử restore và chốt RPO/RTO trước khi vượt cổng một chiều.

### Bài 5 — Tính ngưỡng latency

Baseline p99 = 100 ms. Gate minh họa cho phép tăng không quá 20%. Sau canary, p99 = 135 ms với tải tương đương.

**Câu hỏi:** Quyết định nào phù hợp?

**Đáp án gợi ý:** Ngưỡng là **120 ms**. 135 ms vượt giới hạn nên PAUSE điều tra; nếu xuất hiện sai dữ liệu hoặc mất availability, STOP.

### Bài 6 — Recovery point

Backup sạch có cutoff **08:00 UTC**, cluster gặp sự cố lúc **10:30 UTC**, có ghi hợp lệ đã xác nhận trong khoảng đó và không có log/PITR bổ sung.

**Câu hỏi:** Restore có bảo đảm RPO = 0 không?

**Đáp án gợi ý:** Không. Khoảng **2 giờ 30 phút** thay đổi có nguy cơ mất nếu không có nguồn phục hồi độc lập; cần đối soát các ghi và báo RPO thực tế.

### Bài 7 — Repair có hoàn tác DELETE được không?

Trong mixed-version, một hàng đã bị DELETE hợp lệ trước khi nâng cấp bỗng xuất hiện lại trong một phần kết quả đọc.

**Câu hỏi:** Có nên chạy repair ngay để sửa?

**Đáp án gợi ý:** **STOP**, xác minh phạm vi và nguồn đúng của dữ liệu, giữ evidence. Repair đồng bộ trạng thái replica theo cơ chế Cassandra, không hiểu DELETE nào đúng hoặc sai về nghiệp vụ.

## 15. Checklist go/no-go trước từng bước

- [ ] Đã xác minh version/build Cassandra và JDK thực tế của **từng node**.
- [ ] Có upgrade/downgrade guide **đúng cặp phiên bản và bản phân phối**.
- [ ] Đường nâng trực tiếp/chặng trung gian và mixed-version constraints đều rõ.
- [ ] Đã nhận diện thay đổi SSTable, commitlog, schema, data format và các bước có thể một chiều.
- [ ] Không bật tính năng/schema mới trái hướng dẫn khi còn mixed-version.
- [ ] Java driver, CQL bind, prepared statement, TLS/auth và native protocol đều được kiểm thử.
- [ ] DC/rack, RF, token ownership, schema agreement và CL còn đáp ứng mục tiêu.
- [ ] Kiểm tra dữ liệu qua nhiều partition key, gồm UPDATE/DELETE/TTL và bảng denormalized.
- [ ] Latency p95/p99, timeout, retry, throughput trong ngưỡng theo tải tương đương.
- [ ] Heap/GC, native/RSS, disk, compaction, streaming và repair còn đủ dư địa.
- [ ] Backup COMPLETE, checksum/schema/khóa hợp lệ và restore drill đã đạt.
- [ ] Có phương án sửa, roll forward, rollback app hoặc restore **được hỗ trợ**, không mặc định binary downgrade.
- [ ] Có owner, mốc quan sát, số liệu và điều kiện **GO/PAUSE/STOP/RECOVER**.
- [ ] Mọi bước hậu nâng cấp có nguy cơ một chiều được phê duyệt riêng.
- [ ] Đã kiểm thử lại ứng dụng Java, backup/repair, dashboard và cảnh báo sau khi nâng hết node.

## 16. Tổng kết

Giới hạn downgrade Cassandra đến từ **SSTable, commitlog, schema/metadata, giao thức internode, runtime/config và tương thích client**. Việc cluster hỗ trợ A/B cùng tồn tại trong rolling upgrade **không đồng nghĩa** node đã ghi dữ liệu bằng B có thể chạy lại A. Mỗi đường quay lui phải có nguồn tài liệu đúng phiên bản và bằng chứng trạng thái dữ liệu thực tế.

**GO** chỉ khi correctness, availability, hiệu năng, tài nguyên và khả năng phục hồi đều đạt. **PAUSE** khi cần chẩn đoán và chưa đủ chứng cứ; **STOP** khi có vi phạm nghiêm trọng; **RECOVER** khi phải xây lại trạng thái dữ liệu hoặc hạ tầng. Từ thiết kế partition key, replication và consistency level đến compaction, repair và kết nối Java, mọi lớp đều phải được kiểm tra trước khi nâng node kế tiếp.

