# Commit log, thiết bị lưu trữ và mục tiêu độ bền trong Apache Cassandra

## 1. Vì sao commit log quyết định độ bền của một thao tác ghi?

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**. Dữ liệu được phân phối theo **partition key** và sao chép tới những replica thích hợp, còn ứng dụng dùng **consistency level (CL)** để quyết định số phản hồi cần nhận trước khi xem một thao tác CQL đã thành công.

Tuy nhiên, **một replica phản hồi thao tác ghi** và **dữ liệu đã an toàn trên thiết bị lưu trữ không mất điện** là hai câu hỏi khác nhau. Cassandra dùng **commit log** và **memtable** trong đường ghi:

- **Memtable** giữ dữ liệu trong bộ nhớ, giúp ghi nhanh trước khi tạo SSTable.
- **Commit log** ghi lại mutation theo dạng append-only để một node có thể phục hồi những mutation chưa được flush thành SSTable sau khi process khởi động lại.
- **SSTable** là tệp lưu trữ bất biến được tạo khi memtable flush; compaction sẽ tiếp tục hợp nhất SSTable theo thời gian.

Nếu Cassandra chỉ cập nhật memtable trong RAM, crash có thể xóa sạch dữ liệu chưa flush. Commit log là một tuyến phục hồi, nhưng hiệu lực thực tế còn phụ thuộc **chế độ đồng bộ (sync) xuống đĩa**, cấu hình `durable_writes`, thiết bị và các failure domain.

Bài thuộc chương **Tối ưu tài nguyên** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Nó kết nối kiến trúc write path với mục tiêu độ bền, mức nhất quán đọc/ghi, replication, compaction/repair, xử lý sự cố và ứng dụng Java.

Kết quả học tập:

1. Phân biệt **append vào commit log**, **fsync thành công**, **flush SSTable** và **ACK theo CL**.
2. Hiểu các chế độ commit-log sync, cùng đánh đổi latency–throughput–rủi ro mất dữ liệu.
3. Chọn thiết bị lưu trữ, dung lượng và chính sách vận hành dựa trên **RPO/RTO** thực tế.
4. Chẩn đoán commit log tăng dung lượng, đĩa đầy, fsync chậm hoặc crash/restart.
5. Thiết kế CQL và Java client không nhầm timeout, quorum hay retry với cam kết dữ liệu đã bền vững.

## 2. Đường ghi: từ Java client đến SSTable

### 2.1. Một mutation đi qua những bước nào?

Giả sử bảng `telemetry.readings_by_device_day` có replication factor 3 trong datacenter `dc1`. Java client gửi `INSERT` ở `LOCAL_QUORUM`; coordinator xác định các replica từ token của partition key, phân phối mutation rồi chờ đủ hai replica xác nhận trong DC.

Tại mỗi replica, xử lý ghi thông thường gồm những khâu logic:

1. Nhận và kiểm tra mutation.
2. Ghi mutation vào **commit log**, trừ trường hợp cấu hình/dạng dữ liệu làm hành vi khác.
3. Áp dụng mutation vào **memtable** tương ứng.
4. Xác nhận theo quy tắc ghi và commit-log sync đang áp dụng.
5. Khi memtable đủ điều kiện, flush ra **SSTable** trên data filesystem.
6. Các đoạn commit log không còn chứa dữ liệu cần replay có thể được giải phóng hoặc tái sử dụng.

~~~mermaid
flowchart LR
    A["Java client: INSERT, CL=LOCAL_QUORUM"] --> B["Coordinator"]
    B --> C["Replica A"]
    B --> D["Replica B"]
    B --> E["Replica C"]
    C --> F["Append commit log + update memtable"]
    D --> G["Append commit log + update memtable"]
    E --> H["Append commit log + update memtable"]
    F --> I["ACK theo chế độ sync"]
    G --> J["ACK theo chế độ sync"]
    I --> B
    J --> B
    B --> K["Client success khi đủ ACK"]
    F --> L["Memtable flush -> SSTable"]
    G --> M["Memtable flush -> SSTable"]
~~~

Sơ đồ là khái quát. Các replica thực hiện xử lý đồng thời; thứ tự chi tiết, ACK và một số tối ưu có thể khác theo phiên bản và loại mutation.

**Điểm then chốt:** **write CL kiểm soát số replica ACK**, còn cấu hình commit-log sync kiểm soát mức chắc chắn mutation đã được ép xuống tầng lưu trữ bền vững khi replica ACK. Một giá trị CL mạnh không tự sửa được cấu hình commit log yếu trên tất cả replica.

### 2.2. Commit log không phải SSTable

| Đặc tính | Commit log | Memtable | SSTable |
|---|---|---|---|
| Nơi lưu | Tệp log tuần tự trên filesystem | RAM và cấu trúc bộ nhớ Cassandra | Tệp dữ liệu bất biến trên disk |
| Vai trò | Phục hồi mutation chưa được flush | Nhận mutation và phục vụ read | Lưu dữ liệu đã flush để phục vụ read/compaction |
| Kiểu ghi | Append vào segment, sync theo cấu hình | Cập nhật cấu trúc in-memory | Flush/compaction tạo tệp mới |
| Sau process crash | Replay phần log hợp lệ khi node startup | Mất nội dung chưa flush | Dữ liệu SSTable bền vững còn tồn tại nếu storage tốt |
| Khi có compaction | Không trực tiếp thay thế compaction | Memtable flush khi cần | SSTable được hợp nhất và viết lại |
| Có phải bản sao dữ liệu để backup lâu dài? | **Không** | **Không** | Cần snapshot/backup và kiểm chứng restore |

Commit log **không** có mục đích thay cho backup. Nó là nhật ký phục hồi cục bộ cho mutation chưa trở thành SSTable đã được lưu an toàn.

## 3. Commit-log segment, flush và khả năng thu hồi dung lượng

### 3.1. Commit log được chia thành các segment

Cassandra không ghi mãi vào một tệp log vô hạn. Commit log được quản lý thành các **segment** trên filesystem. Mutation của nhiều bảng có thể cùng xuất hiện trong một segment, và Cassandra theo dõi dữ liệu nào còn cần replay.

Khi một memtable được flush thành SSTable an toàn, những entry commit log tương ứng không còn cần cho memtable ấy. **Một segment chỉ có thể được thu hồi/tái sử dụng khi toàn bộ dữ liệu trong segment còn cần phục hồi đã được xử lý phù hợp**.

Hệ quả quan trọng:

- Một bảng ít ghi nhưng còn memtable chưa flush có thể khiến một segment chứa nhiều mutation của bảng khác vẫn chưa giải phóng.
- Khi commit-log space cao, Cassandra có thể thúc đẩy việc flush memtable theo cơ chế quản lý tổng dung lượng.
- Commit-log size và **SSTable data size** có xu hướng tăng/giảm khác nhau; không suy luận commit log tăng tức toàn bộ dữ liệu logical tăng tương ứng.
- Flush tạo thêm write I/O. Sau flush, compaction có thể tạo write amplification và yêu cầu dung lượng tạm.

### 3.2. Tại sao commit log tăng dù client vẫn ghi thành công?

Giả sử nhiều bảng cùng có mutation được ghi vào commit-log segment. Một số bảng nóng flush nhanh; một bảng ít traffic có dữ liệu chưa flush. Segment chứa cả hai vẫn có thể phải giữ vì mutation chưa an toàn trong SSTable ở bảng ít traffic.

Một số dấu hiệu khác khiến log tăng:

- Write rate cao hơn năng lực flush.
- Disk cho data SSTable chậm, flush bị trì hoãn.
- Nhiều memtable hoạt động hoặc bảng có pattern ghi khác nhau.
- I/O bị tranh với compaction, repair, bootstrap/streaming, snapshot.
- Filesystem gần đầy hoặc có lỗi, làm các bước flush/sync không theo kịp.

**Không xóa thủ công commit-log segment để lấy lại disk space.** Làm vậy có thể làm mất mutation mà memtable chưa flush; phải kiểm tra trạng thái và quy trình phục hồi phù hợp trước khi động tới tệp.

### 3.3. Vai trò của giới hạn tổng dung lượng

Các bản Cassandra có cơ chế/cấu hình giới hạn tổng vùng commit log (thường gặp khái niệm `commitlog_total_space_in_mb` hoặc tên tương ứng theo phiên bản). Khi áp lực tăng, Cassandra có thể đẩy flush để giải phóng segment, nhưng **giới hạn này không phải quota cứng bảo đảm filesystem luôn còn trống** trong mọi tình huống.

Nếu cấu hình quá thấp so với workload và tài nguyên, node có thể flush liên tục, gây write amplification và nghẽn storage. Nếu quá cao trên ổ nhỏ, log có thể lấn vào headroom cần cho các hoạt động khác. Cần đồng thời đo commit-log disk usage, flush pending, disk latency và p99 ghi.

## 4. Ba khái niệm dễ bị gộp nhầm: append, sync và ACK

### 4.1. Append vào filesystem chưa chắc đã sống qua mất điện

Một lần append có thể mới đưa bytes vào buffer của tiến trình hoặc **OS page cache**. Chỉ khi dữ liệu được đồng bộ phù hợp và thiết bị lưu trữ thực thi lệnh ghi ổn định, ta mới có cơ sở mạnh hơn để nói dữ liệu đã vượt qua rủi ro mất RAM/cache.

Vì vậy:

- **Process crash** không giống **host power loss**. OS page cache có thể còn tồn tại sau khi process riêng lẻ chết, nhưng không nên phụ thuộc vào việc nó sẽ luôn được flush kịp.
- **fsync/force** là thao tác yêu cầu hệ điều hành đẩy dữ liệu xuống tầng lưu trữ; cam kết thực tế vẫn phụ thuộc filesystem/controller/thiết bị có tuân thủ đúng durability semantics không.
- **Thiết bị có volatile write cache không được bảo vệ khi mất điện** có thể làm yếu bảo đảm mong đợi ngay cả khi phần mềm đã gọi fsync.

### 4.2. Commit-log sync mode

Cassandra có các chế độ commit-log synchronization, thường gặp **`periodic`** và **`batch`**; một số phiên bản/cấu hình cũng có **`group`**. Tên chính xác, mặc định và tham số đi kèm phải xác minh với bản Cassandra đang triển khai.

| Chế độ | Nguyên lý khái quát | Đánh đổi chính |
|---|---|---|
| **`periodic`** | Mutation có thể được xác nhận sau khi append vào đường log, trong khi lực ép dữ liệu xuống disk diễn ra theo chu kỳ | Throughput và latency tốt hơn trong nhiều workload; có **cửa sổ rủi ro** khi host/nguồn điện mất đột ngột |
| **`batch`** | Nhóm/bước ghi phải chờ đồng bộ log xuống disk theo quy tắc của chế độ trước khi xác nhận | Thu hẹp rủi ro mutation được ACK nhưng chưa durable; tăng phụ thuộc vào fsync latency |
| **`group`** (nếu hỗ trợ) | Ghép một nhóm mutation để cùng chịu chi phí đồng bộ | Cân bằng throughput với thời gian chờ nhóm; cần đọc cấu hình/semantics của phiên bản |

**Không gộp `commitlog_sync=batch` với lệnh CQL `BEGIN BATCH`.** Một cái là chính sách đồng bộ nhật ký ghi trên node; cái kia là loại câu lệnh gom mutation và có semantics riêng.

### 4.3. Nếu dùng periodic, rủi ro mất dữ liệu là gì?

Giả sử hệ thống chọn chu kỳ sync **10 giây chỉ để minh họa**, node ghi nhận các mutation rồi trả ACK theo chế độ periodic. Nếu máy mất nguồn trước lần sync kế tiếp, một số mutation đã ACK nhưng chưa nằm an toàn trên thiết bị có thể không phục hồi từ log.

**Không diễn giải “10 giây” thành cam kết luôn mất đúng 10 giây dữ liệu.** Dữ liệu có thể đã được OS/thiết bị đẩy xuống sớm hơn; có thể đã thành SSTable; hoặc có thể bị ảnh hưởng bởi độ trễ thiết bị, scheduling và lỗi khác. Con số là **khoảng rủi ro ước tính theo nhịp sync**, không phải RPO được kiểm chứng tuyệt đối.

Với replica được nhân bản, nếu **chỉ một node mất điện** và các replica khác giữ mutation, dữ liệu có thể được phục hồi từ replica. Nhưng nếu **nhiều replica cùng hỏng/mất nguồn** trước khi dữ liệu bền vững, chỉ đặt RF/CL cao không bảo đảm giữ được tất cả mutation đã ACK.

### 4.4. Nếu dùng batch, có “zero data loss” tuyệt đối không?

Không nên tuyên bố như vậy. Việc chờ fsync trước ACK củng cố độ bền trên replica đã xác nhận, nhưng:

- Disk/controller có thể báo thành công sai hoặc không bảo vệ write cache.
- Lỗi filesystem, firmware hoặc toàn bộ failure domain có thể gây mất dữ liệu.
- Những replica chưa ACK có thể còn thiếu mutation dù client đã đạt CL.
- Sự cố vận hành, xóa nhầm, corruption hoặc lỗi ứng dụng không được giải quyết chỉ bằng commit log.
- Sao lưu, repair và kiểm tra restore vẫn cần.

**Durability là thuộc tính của cả đường ghi: Cassandra + OS/filesystem + phần cứng + replication + vận hành**, không phải một cờ cấu hình đơn lẻ.

## 5. `durable_writes` của keyspace và giới hạn bảo đảm

Khi tạo keyspace, Cassandra cho phép cấu hình `durable_writes`. Với keyspace dùng để giữ dữ liệu quan trọng, thường lựa chọn **`durable_writes = true`**.

~~~cql
CREATE KEYSPACE telemetry_demo
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_demo.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    temperature double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Tên `dc1` chỉ là minh họa; nó phải khớp tên datacenter thật trong cluster.

### 5.1. `durable_writes = true`

Cassandra dùng commit log cho mutation của keyspace theo cơ chế chuẩn. **Điều này không tự chứng minh đã fsync trước ACK**: mức rủi ro còn phụ thuộc vào `commitlog_sync` và thiết bị lưu trữ.

### 5.2. `durable_writes = false`

Tùy loại thao tác và phiên bản, tắt durable writes có nghĩa mutation không được ghi vào commit log theo đường thông thường cho keyspace đó; dữ liệu chưa flush từ memtable có thể không hồi phục sau crash.

Đây là lựa chọn **chủ động từ bỏ một phần bảo vệ trước lỗi**, không phải mẹo tuning miễn phí để tăng TPS. Chỉ cân nhắc với workload thật sự có thể tái tạo dữ liệu và đã thiết kế kiểm thử/đánh giá rủi ro tương ứng.

Không tắt durable writes cho dữ liệu giao dịch, trạng thái nghiệp vụ hoặc dữ liệu khó tái tạo chỉ vì thấy write latency cao. Với dữ liệu ephemeral, vẫn cần phân tích tác động tới replica, ACK, crash và khôi phục.

### 5.3. Phân biệt theo ba tầng điều kiện

| Điều kiện | Điều nó quyết định | Điều nó **không** quyết định |
|---|---|---|
| **`durable_writes`** trên keyspace | Có dùng commit log theo đường ghi chuẩn cho keyspace hay không | Số replica ACK |
| **`commitlog_sync`** trên node | Khi nào log được ép xuống disk trong đường ghi | RF, lựa chọn replica, partition key |
| **Write CL** trên request | Điều kiện ACK để coordinator trả kết quả | Bảo vệ write cache, filesystem hoặc snapshot/backup |
| **RF + topology** trên keyspace | Số bản sao và vị trí đặt replica | Phải chờ fsync trên từng replica trước ACK hay không |

Quản lý độ bền cần xét **đồng thời cả ba tầng cấu hình** và phần cứng. Không nên suy luận một bảng có RF=3 với `LOCAL_QUORUM` đồng nghĩa hai bản sao đã được fsync nếu đang dùng `periodic`.

## 6. Đặt mục tiêu trước khi tuning: RPO, RTO và write latency

### 6.1. RPO là gì?

**Recovery Point Objective (RPO)** là lượng mất dữ liệu tối đa mà nghiệp vụ **chấp nhận** khi xảy ra sự cố ở phạm vi đã định nghĩa. Có thể mô tả theo thời gian hoặc số mutation.

Ví dụ:

- Telemetry có thể được thiết bị gửi lại: doanh nghiệp chấp nhận mất tối đa vài giây đo nếu mọi cơ chế phục hồi đều thất bại.
- Đơn hàng đã xác nhận thanh toán: yêu cầu không mất trạng thái đã ACK ngay cả khi một máy chết; có thể cần bảo đảm mạnh hơn và cơ chế đối soát.
- Log sự kiện có hệ upstream lưu bền vững: dữ liệu Cassandra có thể được backfill; RPO thực tế phụ thuộc upstream và quy trình chạy lại.

**RPO mục tiêu không tự đạt được** bằng cách đặt chu kỳ commit log tương ứng. Phải xác định **failure scenario**: chỉ process crash, mất điện một node, mất rack, mất cả DC hay xóa nhầm logic.

### 6.2. RTO là gì?

**Recovery Time Objective (RTO)** là thời gian tối đa nghiệp vụ chấp nhận để khôi phục khả năng phục vụ sau sự cố.

Commit log giúp node **replay mutation** khi restart, nhưng RTO còn phụ thuộc:

- Dung lượng log cần replay và hiệu năng disk/CPU.
- Trạng thái các replica còn sống, CL ứng dụng và khả năng failover.
- Streaming/rebuild khi node mất disk.
- Repair, kiểm tra dữ liệu, backup/restore và thủ tục cho traffic quay lại.
- Khối lượng compaction/flush sau khôi phục.

**Không đánh đồng thời gian replay commit log với RTO của dịch vụ**. Khi mất máy, ứng dụng có thể tiếp tục qua replica khác; ngược lại hệ thống có thể UP nhưng chưa đáp ứng SLO hoặc chưa phục hồi dữ liệu đầy đủ.

### 6.3. Ma trận chọn mục tiêu

| Yêu cầu nghiệp vụ | Điều cần ưu tiên | Thử nghiệm phải có |
|---|---|---|
| Phải sống qua process crash đơn lẻ | Commit log, restart/replay đúng, replica khỏe | Restart có kiểm soát trong staging |
| Phải sống qua mất điện máy/host | Sync policy và thiết bị thật sự giữ dữ liệu sau power loss | Fault injection môi trường thử nghiệm, kiểm tra dữ liệu đã ACK |
| Phải chịu lỗi một node | RF, CL, replica placement khác máy | Dừng một node trong staging rồi kiểm tra read/write |
| Phải chịu mất cả rack/DC | RF theo failure domain, routing/CL, network và restore | Mô phỏng mất rack/DC theo runbook |
| Phải khôi phục sau xóa nhầm/corruption | Backup/snapshot có kiểm chứng restore và retention | Diễn tập restore, không dựa vào commit log |
| Phải đạt p99 write thấp | Latency fsync, network, queue, commit-log device | Benchmark p50/p95/p99 cùng error rate |
| Không được để đầy ổ | Headroom và capacity cảnh báo | Load test vượt lưu lượng bình thường, theo dõi flush/compaction |

### 6.4. Rủi ro mất dữ liệu trong cửa sổ periodic: phép tính gần đúng

Giả sử trên **một replica**, traffic ghi eligible là:

- 8.000 mutation/giây.
- Trung bình 1 KiB dữ liệu ghi vào commit log cho mỗi mutation (ước lượng).
- Khoảng rủi ro sync giả định 5 giây.

~~~text
8.000 mutation/s × 1 KiB/mutation × 5 s
= 40.000 KiB ≈ 39,1 MiB mutation-log payload
~~~

**39,1 MiB không phải “sẽ mất” hay cận trên cứng**. Đó chỉ là một ước lượng tải mutation có thể nằm trong cửa sổ chưa đồng bộ. Dữ liệu thực tế có thể đã xuống disk, có replica khác giữ, có metadata, có retry hoặc cửa sổ sync không chính xác năm giây.

Không được **nhân số replica** rồi tuyên bố đó là số dữ liệu logic có thể mất; nhiều replica có thể giữ các bản sao của cùng mutation. Cần đánh giá **tập ACK, failure domain và thời điểm bền vững ở từng replica**.

## 7. Chọn thiết bị lưu trữ cho commit log

### 7.1. Commit log ghi tuần tự nhưng rất nhạy với độ trễ đồng bộ

Nhật ký append-only có tính tuần tự, song với chế độ chờ sync trước ACK, **thời gian fsync và tail latency của ổ** có thể quyết định p95/p99 write. Một SSD/NVMe có throughput cao trên brochure chưa chắc cho fsync p99 tốt dưới tải compaction, flush và streaming.

Khi chọn thiết bị, quan sát:

- **Write latency**, đặc biệt p95/p99 và độ ổn định khi gần đầy.
- **Tốc độ fsync/sustained write** trong pattern thực, không chỉ sequential MB/s.
- **Power-loss protection (PLP)** cho cache và các thao tác ghi đang bay.
- **Endurance** và mức ghi bền vững khi workload chạy nhiều ngày.
- **Filesystem + mount + storage stack** và semantics của flush/barrier.
- **Cạnh tranh I/O** với SSTable flush/compaction, snapshots và các tác vụ nền.

Một NVMe có PLP trên hạ tầng đủ tin cậy thường là ứng viên tốt cho mục tiêu fsync latency thấp. Tuy nhiên loại thiết bị, cloud volume, RAID/JBOD và tuning phù hợp cần được quyết định theo phần cứng và failure scenario thực tế.

### 7.2. Nên tách commit log khỏi data directories?

Hai kiến trúc phổ biến:

~~~text
Cách A: Cùng nhóm lưu trữ hiệu năng cao

  /data/cassandra/data       <- SSTables
  /data/cassandra/commitlog  <- Commit log

Cách B: Tách thiết bị / volume

  /data/cassandra/data       <- SSTables
  /fast/cassandra/commitlog  <- Commit log
~~~

Cách B có thể giúp **cô lập I/O commit log** khỏi compaction và streaming khi đó là các thiết bị vật lý/volume có capacity thực sự độc lập. Nhưng tách đường dẫn trên **cùng thiết bị nền** không tự tạo ra thêm IOPS hoặc giảm contention.

| Lựa chọn | Ưu điểm tiềm năng | Đánh đổi/rủi ro |
|---|---|---|
| Cùng NVMe đủ mạnh | Đơn giản, ít điểm lỗi và dễ vận hành | Flush/compaction có thể tranh I/O với commit log |
| Commit log trên thiết bị riêng | Có thể giảm tail fsync do tách workload | Chi phí, quản lý capacity, failure domain riêng, cần backup/recovery policy |
| Commit log trên ổ chậm hoặc network storage không đáp ứng sync | Tiết kiệm chi phí ban đầu | Tail write latency cao, timeout, rủi ro khi storage không đảm bảo durability |
| Commit log trên ephemeral disk | Có thể có I/O cao | Mất dữ liệu khi máy/volume biến mất nếu không có chiến lược replication/phục hồi phù hợp |

**Không chuyển commit log sang thiết bị ephemeral chỉ để lấy TPS cao** mà không xem RPO/RTO và hậu quả mất một hoặc nhiều replica. Với cloud, cần xác nhận tài liệu nhà cung cấp về flush/fsync và độ bền của volume.

### 7.3. PLP, RAID, filesystem và UPS

- **PLP** của SSD/controller giúp bảo vệ dữ liệu trong volatile cache khi mất điện. Nó bổ trợ, không thay thế replication và backup.
- **UPS** giúp tránh một số tình huống mất nguồn nhưng không bảo đảm không có crash, lỗi controller hay disk.
- **RAID/JBOD** đều có mô hình lỗi/hiệu năng. Với Cassandra đã có replication, không nên mặc định chọn RAID chỉ vì muốn “an toàn hơn”; phải xét failure domain, thao tác thay disk, khả năng chịu lỗi và mục tiêu độ bền.
- **Filesystem journaling** không đồng nghĩa mọi commit-log append đều đã bền vững. Hành vi `fsync` cùng thiết bị và controller mới là phần cần kiểm chứng.
- **Storage cache** không được báo fsync thành công trước khi dữ liệu an toàn, trừ khi cache được bảo vệ và tuân thủ cơ chế flush. Một thiết bị không tuân thủ có thể phá giả định phần mềm.

## 8. Dung lượng commit log và disk headroom

### 8.1. Không chọn volume chỉ bằng kích thước một segment

Dung lượng phải gồm:

1. Các commit-log segments đang hoạt động/chưa thể tái sử dụng.
2. Các segment phát sinh trong burst write.
3. Thời gian giữ segment do memtable flush chậm hoặc lỗi.
4. Chi phí tệp, filesystem, log và các hạng mục khác nếu dùng chung volume.
5. Headroom đủ để vận hành trong lúc điều tra và phục hồi.

Một segment có kích thước cấu hình như `commitlog_segment_size_in_mb` chỉ là đơn vị quản lý tệp, không quyết định **toàn bộ** mức dung lượng cần giữ.

### 8.2. Ví dụ capacity trong tình huống flush bị nghẽn

Giả sử node tạo trung bình **50 MiB mutation log/giây** trong burst, và một sự cố khiến backlog chưa giải phóng kéo dài 4 phút. Để tư duy sơ bộ:

~~~text
50 MiB/s × 240 s = 12.000 MiB ≈ 11,72 GiB
~~~

Con số không có nghĩa disk commit log luôn tăng đúng 11,72 GiB: log segment có thể được tái sử dụng, dữ liệu có thể nén, flush vẫn diễn ra một phần, hoặc disk đã chứa nhiều segment cũ. Dùng phép tính để thấy quy mô rủi ro rồi **đo bytes thật trên từng node**.

Một volume chỉ còn 5 GiB free rõ ràng có nguy cơ trong ví dụ này, dù dữ liệu logical của ứng dụng không tăng nhiều. Điều cần cải thiện có thể là flush throughput, compaction/streaming schedule hoặc I/O capacity, không phải chỉ tăng `commitlog_total_space`.

### 8.3. Commit log đầy có thể gây những gì?

Khi hệ thống không còn khả năng ghi log, ghi dữ liệu, flush hay tái sử dụng segment có thể bị ảnh hưởng nghiêm trọng. Tùy phiên bản và trạng thái lỗi, node có thể:

- Phát sinh write error/timeout và dropped mutations.
- Tăng flush/compaction pressure, read/write p99.
- Vào trạng thái không thể tiếp nhận một số request.
- Phát cảnh báo disk full và log exception.
- Gặp khó khăn khi khởi động/recovery nếu filesystem hoặc commit log bị lỗi.

**Không khẳng định mọi phiên bản Cassandra sẽ phản ứng giống hệt khi disk full.** Thay vì chờ lỗi, thiết lập cảnh báo free bytes, xu hướng commitlog size, flush pending, error rate và p95/p99.

## 9. Commit log khác hint, batchlog và backup

| Thành phần | Dùng để làm gì? | Có thay commit log được không? |
|---|---|---|
| **Commit log** | Replay mutation chưa flush sau restart của một node | Là cơ chế đang xét |
| **Hints / hinted handoff** | Phát lại mutation tới replica đã vắng mặt tạm thời | **Không**: phục hồi khác biệt giữa các replica, không phải nhật ký crash cho memtable |
| **Batchlog** | Hỗ trợ cơ chế phân phối lại logged batch trong tình huống phù hợp | **Không**: khác mục đích và phạm vi |
| **SSTable** | Lưu dữ liệu đã flush và phục vụ read | Cùng hệ lưu trữ nhưng không ghi lại toàn bộ mutation chưa flush |
| **Repair** | Đối chiếu các replica và đồng bộ sai lệch | **Không**: không phục hồi bằng chứng của mutation đã mất ở tất cả replica |
| **Snapshot/backup** | Khôi phục khi mất dữ liệu hoặc xóa nhầm, theo retention | **Không thay commit log** cho write path; cũng không thể bỏ backup vì đã có commit log |

Nếu một mutation được ACK tại một số replica rồi node còn thiếu hồi phục, **hinted handoff và repair** có thể giúp đồng bộ. Nhưng nếu một mutation chưa được giữ bền vững ở **bất kỳ replica nào còn sống**, repair không thể tạo lại mutation ấy từ hư không.

## 10. Consistency level, replication và durability: ba lớp rủi ro

Giả sử keyspace RF=3 trong một DC.

| Tình huống | Write CL | Điều đã được xác nhận | Điều chưa được bảo đảm |
|---|---|---|---|
| A ACK, B/C chưa ACK | `ONE` | Ít nhất một replica đã đáp ứng đường ghi của nó | Không biết B/C đã có dữ liệu; cũng phải xét sync policy của A |
| A/B ACK, C chưa ACK | `LOCAL_QUORUM` | Hai ACK phù hợp trong DC | C chưa chắc nhận mutation; A/B có thể chưa fsync nếu periodic |
| A/B/C ACK | `ALL` | Cả ba ACK theo CL | Không thay PLP, sync policy, backup, chống xóa nhầm |
| Chỉ A sống và CL `LOCAL_QUORUM` | `LOCAL_QUORUM` | Không thể thỏa quorum | Hints không thay ACK và không tạo durability |
| A/B ACK, DC khác chưa xác nhận | `LOCAL_QUORUM` | Quorum của DC cục bộ | Không đảm bảo DC xa đã xác nhận theo quorum |

### 10.1. Độ bền không đồng nghĩa linearizability

Ngay cả khi commit log được sync trước ACK và write dùng `QUORUM`, Cassandra vẫn áp dụng quy tắc timestamp/last-write-wins cho các ghi thông thường. Hai client ghi cạnh tranh vào cùng cell có thể có kết quả phụ thuộc timestamp và thời gian; **durability không tự tạo cơ chế compare-and-set**.

Nếu nghiệp vụ yêu cầu “chỉ cập nhật khi version hiện tại bằng X”, dùng LWT với `IF` / `IF NOT EXISTS` và serial consistency phù hợp. Commit log và storage bền vững vẫn cần xét, nhưng không thay cơ chế đồng thuận.

### 10.2. Phân vùng phần cứng theo failure domain

RF=3 có ý nghĩa thực tế khác nhau nếu cả ba replica cùng nằm trên một nguồn điện, cùng rack hoặc cùng filesystem nền. Với `NetworkTopologyStrategy`, topology DC/rack và placement cần được cấu hình đúng để phân bố rủi ro; CL phải phù hợp mục tiêu chịu lỗi.

**Không dùng số replica như một con số thay thế phân tích failure domain**. Một sự cố điện toàn rack có thể gây mất nhiều bản sao cùng lúc dù RF cao.

## 11. Thiết lập và xác minh cấu hình theo phiên bản

Tên tham số, giá trị mặc định, đơn vị và sự hỗ trợ **thay đổi theo phiên bản Cassandra**. Dưới đây là các khái niệm thường gặp để định hướng kiểm tra, **không phải cấu hình production có thể sao chép nguyên xi**.

| Nhóm cấu hình | Ý nghĩa | Câu hỏi khi thay đổi |
|---|---|---|
| `commitlog_directory` | Đường dẫn commit log | Có đủ disk, PLP và khả năng chịu lỗi không? |
| `commitlog_sync` | Phương thức đồng bộ (periodic/batch/khác theo bản) | Khi nào ACK và sync được thực hiện? |
| Tham số **sync period** | Khoảng giữa các lần sync periodic, tên/đơn vị theo bản | Cửa sổ rủi ro và write latency thay đổi thế nào? |
| Tham số **batch/group window** | Nhóm mutation chờ sync, nếu được hỗ trợ | p99 và throughput thay đổi thế nào? |
| `commitlog_segment_size_in_mb` hoặc tên tương ứng | Quy mô segment quản lý | Có phù hợp log churn/mutation size không? |
| `commitlog_total_space_in_mb` hoặc tên tương ứng | Ngưỡng quản lý tổng log/flush | Tăng ngưỡng có gây thiếu disk headroom không? |
| Tùy chọn commit-log compression theo phiên bản | Nén log trước khi lưu | CPU và I/O trade-off ra sao? |
| `durable_writes` của keyspace | Sử dụng commit log theo đường chuẩn | Có chấp nhận mất dữ liệu chưa flush không? |

Khối sau là **minh họa ý tưởng** và chủ ý bỏ trống những tham số phụ thuộc phiên bản:

~~~yaml
# CÁC DÒNG MINH HỌA — đối chiếu cassandra.yaml của phiên bản đang chạy.
commitlog_directory: /var/lib/cassandra/commitlog
commitlog_sync: periodic

# Ví dụ những KHÁI NIỆM cần kiểm tra, không tự suy ra cú pháp:
# - chu kỳ sync nếu dùng periodic
# - batch/group window nếu dùng batch/group
# - segment size và tổng commit log space
~~~

Không tự sửa `cassandra.yaml` trên một node đang phục vụ traffic mà chưa có benchmark, kiểm tra cú pháp/khởi động, kế hoạch rollout và rollback. Một số thay đổi cần restart; hành vi chính xác phải theo tài liệu của release đang chạy.

### Quy trình thay đổi có kiểm soát

1. Ghi trạng thái baseline (write p50/p95/p99, TPS, errors, commit-log size, fsync/disk latency).
2. Xác định RPO/RTO và failure scenario được phép.
3. Kiểm tra đúng phiên bản, tên key/đơn vị và topology.
4. Thử trong staging với payload, CL, concurrency và thiết bị tương tự production.
5. Đổi từng yếu tố có kiểm soát, đánh giá throughput **và** lỗi/crash recovery.
6. Rollout theo change window/canary nếu phù hợp, giữ khả năng rollback.
7. Cập nhật runbook, monitoring và xác nhận thực tế sau triển khai.

## 12. Quan sát commit log, flush và lưu trữ bằng metrics

### 12.1. Nhóm metrics nên có

| Nhóm | Nên đo | Dấu hiệu cần điều tra |
|---|---|---|
| **Commit log** | Disk bytes, segment count, append/sync latency, sync failures (nếu exporter hỗ trợ) | Log tăng liên tục hoặc fsync p99 tăng |
| **Write path** | Write latency p50/p95/p99, timeout, unavailable, mutation errors | Nhiều request chờ hoặc thất bại |
| **Memtable/flush** | Pending flush, flush time, bytes flushed | Log không thu hồi được vì dữ liệu chưa vào SSTable |
| **Disk** | Free bytes, throughput, IOPS, await/utilization, fsync latency | Thiết bị cạn headroom hoặc tail latency lớn |
| **Compaction/repair** | Pending compaction, streaming, repair load | Tác vụ nền tranh I/O với commit log/flush |
| **Node health** | GC pause, heap, CPU, dropped messages, status | Áp lực ở nơi khác cũng kéo write latency |
| **Replication** | CL và RF, node UP/DOWN, hints, repair state | ACK có đủ và dữ liệu đồng bộ đến đâu |

Metric JMX/Prometheus cụ thể **phụ thuộc Cassandra version và exporter**. Một metric tên `CommitLog...` có thể được thu thập theo node, không phải keyspace; cần xác nhận scope và đơn vị trước khi tổng hợp.

Đừng chỉ xem **write throughput**: một cấu hình periodic có thể làm TPS tăng nhưng đổi lấy rủi ro mất dữ liệu khi mất điện. Ngược lại, một cấu hình batch có thể làm TPS thấp hơn nhưng phù hợp yêu cầu RPO nghiêm ngặt hơn. Cần đánh giá **performance và độ bền cùng nhau**.

### 12.2. Lệnh chẩn đoán ít xâm lấn

Ví dụ trên node có quyền vận hành:

~~~bash
# Tình trạng node và DC/rack.
nodetool status

# Tải node, thông tin cache/heap và trạng thái chung.
nodetool info

# Thread pool, pending và dropped messages.
nodetool tpstats

# Thống kê ghi/đọc và SSTable theo bảng.
nodetool tablestats telemetry_demo.readings_by_device_day

# Tác vụ compaction cạnh tranh disk I/O.
nodetool compactionstats

# Streaming khi bootstrap, repair hoặc thay đổi topology.
nodetool netstats

# Trợ giúp và khả năng của đúng phiên bản.
nodetool help
~~~

Lệnh vận hành như `nodetool flush` có thể chủ động tạo SSTable và load; **không chạy tự phát trên cluster đang gặp vấn đề disk-full** chỉ để “test commit log”. Đánh giá tác động và thủ tục runbook trước khi thực hiện.

Trên Linux có thể kiểm tra filesystem chứa commit log sau khi xác nhận đúng đường dẫn:

~~~bash
df -h /var/lib/cassandra/commitlog
du -sh /var/lib/cassandra/commitlog

# Ví dụ nếu công cụ đã được cài và operator có quyền:
# iostat -x 1
# lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
~~~

`du` đo dung lượng thư mục, `df` đo free space filesystem; `iostat` giúp xem disk await/utilization. Các chỉ số này không tự cho biết bao nhiêu mutation chưa được fsync. Không suy luận sức khỏe commit log từ một ảnh chụp dung lượng duy nhất.

### 12.3. Lập timeline để xác định nguyên nhân gốc

~~~text
10:00 write traffic tăng gấp ba
10:05 commit log bytes tăng nhưng chưa giảm trở lại
10:07 memtable flush backlog tăng
10:09 compaction/streaming cùng chiếm disk I/O
10:12 write p99 tăng và timeout xuất hiện
10:15 filesystem chứa commit log còn 8% free

Giả thuyết cần kiểm chứng:
  flush bị nghẽn -> segment không thể thu hồi
  -> commit log tăng -> disk headroom thấp
  -> read/write latency và error tăng
~~~

Ví dụ mô tả chuỗi phân tích, **không phải log thật của Cassandra**. Cần kiểm tra đồng thời những tác nhân khác như GC, network, kernel disk error và volume throttling.

## 13. Ví dụ CQL và Java: thao tác thành công không thay mục tiêu độ bền

### 13.1. Ghi dữ liệu theo partition key

Trong keyspace minh họa `telemetry_demo`:

~~~cql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_demo.readings_by_device_day (
    device_id, event_day, event_time, temperature
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:15:00Z',
    24.6
);

SELECT event_time, temperature
FROM telemetry_demo.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Phân vùng được xác định bởi `(device_id, event_day)`. Cấu trúc này có thể giúp truy vấn theo thiết bị/ngày hiệu quả, nhưng **mô hình partition tốt không thay thế commit log**. Ngược lại, storage cực bền cũng không làm truy vấn thiếu partition key trở nên hiệu quả.

### 13.2. Java Driver 4.x và tính mơ hồ của timeout

Ví dụ dùng `CqlSession session` đã khởi tạo với contact point/local DC chính xác:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement insert = session.prepare(
    "INSERT INTO telemetry_demo.readings_by_device_day " +
    "(device_id, event_day, event_time, temperature) " +
    "VALUES (?, ?, ?, ?)"
);

UUID deviceId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");
Instant eventTime = Instant.parse("2026-11-21T10:15:00Z");

BoundStatement statement = insert.bind(
        deviceId,
        LocalDate.of(2026, 11, 21),
        eventTime,
        24.6)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(statement);
~~~

Trong ví dụ này, CQL có key ổn định theo thiết bị/ngày/thời gian đo và ghi cùng giá trị có thể được thiết kế để retry an toàn theo ngữ nghĩa nghiệp vụ. Tuy nhiên:

- **Thành công của `execute`** có nghĩa server/driver đã đáp ứng điều kiện request; không phải một chứng nhận hardware PLP hay mọi replica đã fsync.
- **Write timeout** không chứng minh không replica nào ghi mutation. Có thể đã có một số ACK hoặc mutation được áp dụng dù client hết thời gian chờ.
- Retry cần **idempotency**, khóa ổn định và tránh side effects bên ngoài bị lặp. Đặc biệt không retry counter increment/mutation không idempotent một cách mù quáng.
- Nếu dịch vụ cần biết “đơn hàng đã chấp nhận có bền vững không?”, đáp án liên quan đến cả **write CL, commitlog sync, replication, thiết bị và cơ chế đối soát**, không chỉ Java exception.
- Driver không có một tùy chọn per-statement biến `periodic` thành `batch` cho các replica; đây là chính sách tầng Cassandra node được vận hành riêng.

### 13.3. Khi phục hồi sau crash

Một node restart có thể replay commit log còn hợp lệ để tái tạo memtable state chưa flush. Sau khi hoạt động lại:

1. Kiểm tra node health và log startup/replay.
2. Đối chiếu dữ liệu và sự chênh lệch replica, nhất là nếu máy mất điện hoặc disk lỗi.
3. Duy trì repair theo lịch để xử lý anti-entropy.
4. Không giả định một query `SELECT` thành công chứng minh toàn cluster đã đầy đủ dữ liệu.
5. Nếu dữ liệu mất trên tất cả replica, cần backup/upstream replay; commit log của node đã hỏng không thể tự khôi phục từ một thiết bị không còn đọc được.

## 14. Runbook: commit-log disk gần đầy, write p99 tăng

**Tình huống:** Một Cassandra node có filesystem commit log chỉ còn 7% free, p99 write từ 20 ms lên 900 ms, bảng nóng vẫn ghi liên tục, compaction tăng và một replica khác đang streaming.

### Bước 1 — Xác định rủi ro hiện tại

Kiểm tra write timeout/unavailable, số node khỏe, CL của ứng dụng, log I/O error, filesystem free bytes và tốc độ tăng commit log. Nếu một replica không thể ghi bền vững, xác định tác động lên quorum thay vì chỉ nhìn node UP.

### Bước 2 — Định lượng tốc độ lấp đầy

Lấy `du`/`df` theo chuỗi thời gian và metric commitlog segments; so bytes mới, flush backlog và disk write throughput. Dự báo khoảng an toàn còn lại bằng dữ liệu đo, **không mặc định ngưỡng tổng log là giới hạn cứng**.

### Bước 3 — Tìm lý do segment không được thu hồi

Kiểm tra memtable flush, latency data disk, compaction/streaming/repair, I/O throttle và log lỗi. Nếu data disk rất chậm, commitlog disk còn nhanh cũng không giúp segment được giải phóng đúng nhịp.

### Bước 4 — Giảm áp lực có kiểm soát

Theo quy trình vận hành, cân nhắc giảm/tạm dừng backfill, batch job không quan trọng, giảm concurrency, điều tiết streaming/repair khi an toàn và khắc phục disk bottleneck. Tránh đẩy tất cả tải sang node khác khiến toàn cluster quá tải.

**Không giải phóng dung lượng bằng cách xóa commit-log segment thủ công** và không tùy tiện tắt durable writes. Đây là hành động có thể làm mất dữ liệu chưa flush.

### Bước 5 — Khắc phục vấn đề capacity/thiết bị

Nếu filesystem gần đầy do workload hợp lệ, mở rộng/điều chỉnh lưu trữ theo runbook với backup, downtime/rollout và kiểm chứng restart phù hợp. Nếu thiết bị lỗi hoặc mất log, có thể cần thay node/restore/repair tùy trạng thái data và replica; không mặc định fsck hoặc restart lặp lại là đủ.

### Bước 6 — Xác minh sau khôi phục

Yêu cầu:

- Dung lượng commit log ổn định và filesystem có headroom.
- Flush queue không tăng vô hạn.
- Disk latency, compaction và streaming trở về phạm vi chịu tải.
- p50/p95/p99 write cùng timeout/unavailable giảm về SLO.
- Node health, replication và dữ liệu cần thiết được đối chiếu.
- Nếu có crash hoặc mất replica, recovery plan theo RPO/RTO đã được kiểm chứng.

Sau sự cố cần cập nhật capacity alert và thử nghiệm khôi phục, không chỉ sửa một lần rồi đóng incident.

## 15. Khi tuning khiến ghi nhanh hơn nhưng dữ liệu kém bền hơn

Một đội đo được:

~~~text
Cấu hình A:
  p99 write = 18 ms
  commit log sync = periodic
  RPO qua mất nguồn host chưa được kiểm chứng

Cấu hình B:
  p99 write = 45 ms
  commit log sync = batch
  Đã kiểm chứng lưu trên thiết bị có PLP trong staging

Mục tiêu API:
  p99 write <= 60 ms
  Dữ liệu đã ACK phải chịu được một host mất điện
~~~

**Trong kịch bản minh họa**, B có thể phù hợp mục tiêu nghiệp vụ hơn dù chậm hơn. Nhưng không thể kết luận “batch luôn tốt hơn periodic”: nếu workload có thiết kế upstream replay và RPO chấp nhận mất một số giây, periodic có thể là lựa chọn có chủ đích.

Quan trọng là **tuyên bố bảo đảm đúng với failure scenario được kiểm thử**:

- RPO chấp nhận mất dữ liệu đã ACK ở lỗi nào?
- Có bao nhiêu replica nằm trên các failure domain độc lập?
- Các replica có cùng commitlog policy và storage semantics không?
- Sau mất nguồn, dữ liệu đã ACK có thực sự còn đọc được?
- Độ trễ tail của commit log có làm vi phạm SLO ghi không?
- Có backup và thủ tục khôi phục sau lỗi logic không?

Một benchmark TPS chỉ đo khi cluster khỏe **không trả lời** các câu hỏi này.

## 16. Những hiểu nhầm cần tránh

| Nhận định | Đúng/sai | Giải thích |
|---|---|---|
| “Cassandra ACK nghĩa là SSTable đã flush.” | **Sai** | Ghi thông thường có thể được ACK khi mutation nằm ở commit log + memtable theo policy |
| “Có commit log nghĩa là fsync trước ACK.” | **Sai** | Còn phụ thuộc chế độ sync |
| “`LOCAL_QUORUM` tự đồng bộ mọi ACK xuống thiết bị bền vững.” | **Sai** | CL và sync policy là hai tầng khác nhau |
| “`durable_writes=false` chỉ ảnh hưởng tốc độ.” | **Sai** | Có thể mất mutation chưa flush sau crash |
| “Commit log là backup dài hạn.” | **Sai** | Log được giải phóng khi không còn cần replay, không phải bản sao lưu độc lập |
| “Có RF=3 thì khỏi cần backup.” | **Sai** | Replication không bảo vệ khỏi xóa nhầm/corruption đồng loạt |
| “Cứ tăng commitlog_total_space là hết disk-full.” | **Sai** | Có thể trì hoãn flush nhưng vẫn hết volume |
| “Commit log tăng luôn do disk log quá chậm.” | **Sai** | Dữ liệu chưa flush ở SSTable cũng có thể giữ segment |
| “Tách thư mục log trên cùng disk chắc chắn tăng IOPS.” | **Sai** | Cùng tài nguyên phần cứng vẫn cạnh tranh |
| “SSD nhanh thì fsync luôn an toàn qua mất điện.” | **Sai** | Cần kiểm tra PLP/cache và độ tin cậy firmware |
| “Chế độ batch sync tạo transaction ACID cho mọi CQL.” | **Sai** | Không phải LWT hoặc multi-row transaction |
| “Tăng write CL có thể chữa lỗi log disk.” | **Sai** | Không thay được phần cứng và đường ghi tại từng replica |
| “Mất một replica thì repair sẽ tái tạo mọi mutation bất kể các replica khác.” | **Sai** | Không thể sửa dữ liệu mà mọi bản sao đều đã mất |
| “Một lần SELECT thành công nghĩa là recovery hoàn toàn.” | **Sai** | Query chỉ kiểm tra một phạm vi, không xác minh toàn bộ replica |
| “Giảm chu kỳ sync bảo đảm RPO theo đúng số mili giây đã đặt.” | **Sai** | RPO thực tế còn phụ thuộc hạ tầng, replica và failure domain |

## 17. Bài tập có đáp án

### Câu 1 — ACK và fsync

Một keyspace `durable_writes=true`, write CL=`LOCAL_QUORUM`, commitlog sync dùng `periodic`. Hai replica trả ACK. Có thể cam kết cả hai đã fsync mutation trước ACK không?

**Đáp án:** Không. Quorum cho biết hai replica đã xác nhận theo đường ghi; periodic có thể xác nhận trước khi log được ép xuống thiết bị ổn định. Muốn đánh giá độ bền phải xem sync policy và storage thực tế.

### Câu 2 — Ước lượng rủi ro trong cửa sổ sync

Node có 8.000 mutation/s, mỗi mutation tương ứng 1 KiB log payload và cửa sổ giả định 5 giây. Payload thô khoảng bao nhiêu?

**Đáp án:** Khoảng `8000 × 1 × 5 = 40000 KiB ≈ 39,1 MiB`. Đây là lượng mutation *có thể nằm trong khoảng rủi ro*, không phải dữ liệu chắc chắn mất hay cận trên cứng.

### Câu 3 — Commit log tăng dù memtable của bảng nóng đã flush

Tại sao segment vẫn chưa thể xóa?

**Đáp án:** Segment có thể chứa mutation của **nhiều bảng**; một số mutation thuộc memtable khác chưa được flush/đánh dấu an toàn. Cần xem trạng thái flush toàn node, không chỉ một bảng nóng.

### Câu 4 — Tác động của `durable_writes=false`

Một ứng dụng giao dịch muốn tăng TPS bằng cách tắt durable writes. Rủi ro gì?

**Đáp án:** Mutation chưa flush có thể thiếu nhật ký phục hồi sau crash. Nếu mất nhiều replica hoặc không có upstream replay, dữ liệu nghiệp vụ có thể mất. Không nên áp dụng cho dữ liệu cần bền vững chỉ vì TPS.

### Câu 5 — Thiết bị có write cache không bảo vệ

Cassandra đã yêu cầu sync nhưng controller báo thành công khi dữ liệu vẫn nằm trên volatile cache. Khi mất nguồn, rủi ro nào xuất hiện?

**Đáp án:** Dữ liệu tưởng bền vững có thể mất. Cần kiểm tra flush semantics, PLP/BBU và tính đúng của thiết bị/firmware; RAID hoặc UPS không phải câu trả lời tuyệt đối.

### Câu 6 — Bảo vệ sau xóa nhầm

RF=3 và batch sync đều tốt, nhưng một operator xóa nhầm toàn bộ bảng, thao tác DELETE được replicate thành công. Commit log có giúp khôi phục phiên bản trước một cách chắc chắn không?

**Đáp án:** Không. Commit log không phải backup có thể quay về thời điểm tùy ý. Cần snapshot/backup và kiểm chứng restore cùng chiến lược phục hồi nghiệp vụ.

### Câu 7 — Disk đầy, có nên xóa segment?

Commitlog filesystem còn 2% free và write timeout tăng. Có người đề nghị xóa vài tệp commit log cũ nhất.

**Đáp án:** Không tự xóa. Chúng có thể chứa mutation chưa flush. Phải xác minh flush/backlog, disk health, giảm tải và làm theo runbook khôi phục/an toàn dữ liệu.

### Câu 8 — RPO với mất cả DC

Cluster có hai DC. Ứng dụng chỉ ghi `LOCAL_QUORUM` ở DC1, chưa yêu cầu ACK từ DC2. DC1 mất hoàn toàn ngay sau write success. Có chắc DC2 có mutation mới nhất không?

**Đáp án:** Không. LOCAL_QUORUM chỉ bảo đảm quorum của DC cục bộ theo chính sách ACK; DC2 có thể chưa nhận. Cần chọn CL/topology/replication và failure-domain phù hợp mục tiêu RPO mất DC.

### Câu 9 — Batch sync và CQL batch

Bật `commitlog_sync=batch` có làm mọi `INSERT` trở thành thao tác nguyên tử nhiều bảng hoặc CAS không?

**Đáp án:** Không. Batch là chính sách sync log; CQL batch và LWT có semantics riêng. Không nên suy luận tính nguyên tử nghiệp vụ từ tên “batch”.

### Câu 10 — Lựa chọn theo SLO

Benchmark giả định A có p99 18 ms (periodic), B có p99 45 ms (batch với PLP), SLO p99 không quá 60 ms và cần chịu mất điện một host. Phải chọn A vì nhanh hơn?

**Đáp án:** Không. B có thể đáp ứng cả SLO lẫn mục tiêu độ bền đã kiểm chứng. Quyết định cuối phải dựa trên bài test failure scenario thực tế, topology và rủi ro, không dựa riêng TPS/p99.

## 18. Tổng kết

Commit log là một thành phần trọng yếu của **độ bền ghi cục bộ** trong Cassandra, nằm giữa mutation đang ở memtable và dữ liệu đã được flush thành SSTable. Khi tuning tài nguyên:

1. **Phân biệt append, fsync, memtable flush và ACK theo CL.** Chúng là các mốc khác nhau.
2. **Hiểu `periodic` so với `batch`/`group` theo phiên bản:** throughput và p99 phải được cân cùng cửa sổ rủi ro mất dữ liệu.
3. **Giữ `durable_writes` phù hợp yêu cầu nghiệp vụ**; tắt commit log là quyết định về độ bền, không đơn thuần là tuning tốc độ.
4. **Chọn storage theo fsync latency, PLP và failure domain**, không chỉ số MB/s hoặc IOPS quảng cáo.
5. **Tính disk headroom cho segment tồn đọng và flush backlog**, nhất là khi compaction/repair/streaming cùng hoạt động.
6. **RF và CL không thay cho durability policy và backup**; xóa nhầm, corruption và sự cố liên DC cần kế hoạch riêng.
7. **Đo p50/p95/p99 write, timeout, free disk, commitlog bytes và flush activity** trước/sau mọi thay đổi.
8. **Xác định RPO/RTO theo kịch bản lỗi cụ thể** và kiểm chứng bằng diễn tập an toàn trong staging.

Câu hỏi cuối cùng không phải “commit log nên đặt trên ổ nhanh bao nhiêu?”, mà là **“khi ứng dụng Java nhận một ACK, mutation đã được giữ trên những replica nào, qua cơ chế sync và thiết bị nào, và điều gì còn tồn tại sau kiểu sự cố mà nghiệp vụ yêu cầu phải chịu đựng?”**. Chỉ khi trả lời được câu hỏi ấy, việc tối ưu commit log mới vừa hiệu quả vừa đúng mục tiêu độ bền.
