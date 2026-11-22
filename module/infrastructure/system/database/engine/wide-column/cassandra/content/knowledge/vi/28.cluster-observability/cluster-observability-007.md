# Dung lượng đĩa, commit log, SSTable, hints và snapshot

## 1. Khi đĩa Cassandra gần đầy, đang đầy vì điều gì?

Trong **Apache Cassandra**, một node không chỉ lưu những hàng dữ liệu đang được `SELECT` trả về. Dung lượng đĩa còn được sử dụng bởi **commit log**, nhiều **SSTable** bất biến, **hints** chờ chuyển cho replica khác, **snapshot/backup**, các file phục vụ compaction và một số dữ liệu hệ thống khác. Vì thế, nhìn một con số `disk used` không đủ để quyết định phải sửa gì.

Ví dụ, cùng là một node báo sử dụng **90% ổ đĩa**, nguyên nhân có thể hoàn toàn khác:

- Các SSTable chứa dữ liệu hợp lệ tăng theo tốc độ ghi thực.
- Compaction bị nghẽn nên nhiều phiên bản cũ, tombstone và SSTable chưa được hợp nhất.
- Commit log không thu hồi segment vì memtable chưa được flush đầy đủ.
- Một replica bị mất kết nối khiến hints tích lũy trên node khác.
- Snapshot từ nhiều lần bảo trì vẫn giữ các file SSTable cũ.
- Một thao tác streaming/compaction đang tạo thêm file mới trong khi file cũ chưa được giải phóng.

Mỗi tình huống cần **chỉ số, bằng chứng và hành động khác nhau**. Xóa thủ công file trong thư mục dữ liệu, commit log hoặc hints có thể làm mất dữ liệu/chưa đồng bộ, không phải cách xử lý an toàn.

Bài này thuộc chương **Quan sát hệ thống** trong Apache Cassandra: tìm hiểu vai trò của từng loại file, chỉ số cần theo dõi, cách chẩn đoán khi ổ đĩa tăng bất thường, các lệnh `nodetool`/CQL phục vụ kiểm tra và cách ứng dụng Java bổ sung telemetry cho hoạt động đọc/ghi.

**Mục tiêu học tập:** phân biệt số liệu đĩa ở cấp filesystem với cấp Cassandra, biết kiểm tra commit log/SSTable/hints/snapshot, dự kiến headroom khi compaction, chọn cảnh báo phù hợp và thực hiện một quy trình điều tra không gây hại dữ liệu.

**Phạm vi:** các full replica thông thường, ví dụ trên Cassandra dùng `NetworkTopologyStrategy`. Tên metric JMX, cấu hình thư mục, mặc định commit log/compaction và cú pháp `nodetool` có thể thay đổi giữa các phiên bản; cần đối chiếu với môi trường đang chạy.

## 2. Bản đồ đường ghi và những nơi tiêu thụ dung lượng

~~~mermaid
flowchart TD
    A["Java client gửi INSERT/UPDATE/DELETE"] --> C["Coordinator định tuyến tới replicas"]
    C --> R["Replica nhận mutation"]
    R --> L["Commit log: ghi nối tiếp để phục hồi"]
    R --> M["Memtable: dữ liệu trong bộ nhớ"]
    M --> F["Flush tạo SSTable bất biến"]
    F --> S["SSTable đang hoạt động"]
    S --> K["Compaction tạo SSTable kết quả"]
    K --> S
    S --> P["Snapshot: tham chiếu/hard link tới SSTable"]
    C --> H["Hint lưu tạm nếu replica đích vắng mặt"]
    H --> D["Gửi hint khi replica trở lại"]
    L --> G["Segment có thể tái sử dụng/xóa sau khi không còn dữ liệu cần replay"]
~~~

Sơ đồ là **mô hình logic**, không mô tả chính xác mọi thread hoặc thứ tự fsync. Điều quan trọng là **đường ghi dữ liệu** và **đường bảo trì** tạo ra các nhóm tiêu thụ đĩa khác nhau.

| Thành phần | Lý do tồn tại | Khi nào dung lượng có thể giảm? | Nguy cơ nếu xóa thủ công |
| --- | --- | --- | --- |
| **Commit log** | Ghi mutation để khôi phục memtable sau sự cố. | Khi segment không còn chứa dữ liệu cần replay sau flush/checkpoint phù hợp; Cassandra quản lý việc thu hồi. | Mất khả năng phục hồi ghi chưa flush. |
| **SSTable** | Dữ liệu bền vững được sắp xếp/index, có thể gồm version và tombstone. | Compaction, cleanup do thay topology hoặc thao tác vòng đời dữ liệu phù hợp. | Mất partition/row; làm lệch replica. |
| **Hints** | Ghi nhận một số mutation chưa chuyển tới replica đích. | Khi hint được gửi/loại theo chính sách và cơ chế quản lý hints. | Replica đích có thể vĩnh viễn bỏ lỡ mutation; cần repair. |
| **Snapshot** | Giữ tập file SSTable tại một mốc phục vụ sao lưu/khôi phục. | Khi snapshot được dọn theo chính sách retention và các tham chiếu cuối cùng biến mất. | Mất điểm phục hồi. |
| **Compaction/streaming output** | File đang được xây dựng/nhận trước khi thay file hoặc hoàn tất bootstrap. | Khi tác vụ hoàn tất và file không còn tham chiếu được giải phóng. | Gây hỏng tác vụ hoặc mất bản sao. |

**Đừng nhầm:** dữ liệu **hết TTL** không có nghĩa file SSTable biến mất đúng giây TTL hết; việc purge còn phụ thuộc tombstone, `gc_grace_seconds`, compaction và khả năng dữ liệu cũ đang bị che. Tương tự, node mới nhận dữ liệu qua streaming không làm dữ liệu dư trên node cũ tự bị cleanup ngay.

## 3. Hai góc nhìn dung lượng: filesystem và Cassandra

### 3.1. Filesystem trả lời “còn bao nhiêu byte có thể sử dụng?”

Trong hệ Linux của node lab:

~~~bash
# Quan sát filesystem/mount point của node Cassandra.
df -h

# Chỉ minh họa cách xem các thư mục đã biết trong cấu hình node.
# Thay đường dẫn ví dụ bằng đường dẫn THỰC TẾ đã xác minh.
du -sh /var/lib/cassandra/data
du -sh /var/lib/cassandra/commitlog
du -sh /var/lib/cassandra/hints
~~~

`df` đo dung lượng/khả dụng ở **filesystem**; `du` tổng hợp mức sử dụng của các file/thư mục theo cách công cụ đếm. Các thư mục ở trên là **ví dụ thường gặp**, không phải cấu hình bắt buộc: `data_file_directories`, `commitlog_directory`, `hints_directory` và các mount point có thể khác nhau, hoặc cùng nằm trên một volume.

**Tại sao cộng `du` không luôn bằng `df`?**

- SSTable và snapshot có thể dùng **hard link** tới cùng inode: cộng các thư mục riêng lẻ dễ **đếm trùng** byte đã cấp phát.
- File đang mở nhưng đã unlink có thể vẫn chiếm block tới khi tiến trình đóng tham chiếu; `du` có thể không nhìn thấy theo cách tương tự `df`.
- Filesystem còn metadata, reserved blocks, fragmentation, các file ứng dụng/log và overhead khác.
- Ở môi trường container, dung lượng volume được mount không đồng nhất với quota filesystem bên trong container.
- Trong cluster nhiều volume, tổng dung lượng một node không nói được **volume nóng nhất** còn bao nhiêu.

**Ưu tiên `df` trên đúng từng volume để biết rủi ro đầy đĩa**, rồi dùng số liệu thành phần để giải thích nguyên nhân. Đừng cộng tùy tiện `du(snapshot)` với `du(active SSTable)` và coi đó là dung lượng vật lý chắc chắn có thể thu hồi.

### 3.2. Cassandra trả lời “dữ liệu hoạt động và công việc nền ra sao?”

`nodetool tablestats` và metrics Cassandra thường cung cấp các góc nhìn như:

- **Live disk space used**: kích thước dữ liệu SSTable đang được sử dụng theo định nghĩa metric.
- **Total disk space used**: tổng dung lượng SSTable được công cụ tính, có thể có khác biệt về phạm vi so với live; **không** đồng nghĩa `df` của toàn filesystem.
- **SSTable count**: số SSTable của bảng (đếm file/cấu trúc, không trực tiếp là số partition).
- **Droppable tombstone ratio, estimated tombstones, partition-size statistics**: dấu hiệu về nợ compaction và thiết kế dữ liệu.
- **Pending/active compaction, flush, streaming**: công việc nền có thể giữ file cũ và cần headroom.

Tên trường, kiểu đơn vị và cách tính chính xác cần đối chiếu với **phiên bản Cassandra/monitoring exporter**. Một metric `Table.LiveDiskSpaceUsed` không bao hàm mặc nhiên commit log, hints, snapshots và log ứng dụng.

### 3.3. Bốn loại “dung lượng” cần phân biệt

| Thuật ngữ trong điều tra | Câu hỏi | Nguồn điển hình |
| --- | --- | --- |
| **Physical used/free** | Volume có còn đủ block cho write/flush/compaction không? | `df`, node/disk exporter, filesystem metrics. |
| **Active SSTable footprint** | Dữ liệu đang phục vụ đọc/ghi chiếm bao nhiêu? | `nodetool tablestats`, JMX `Table` metrics. |
| **Potentially reclaimable** | Snapshot nào hết retention, SSTable nào có thể được compaction, hints nào đã giao? | Snapshot inventory, compaction/hints state, runbook. |
| **Temporary headroom** | Có đủ dung lượng để đồng thời giữ input và output compaction/streaming? | `df`, compaction backlog, kế hoạch vận hành. |

Đặc biệt, **potentially reclaimable không đồng nghĩa có thể xóa ngay**. Compaction phải giữ tombstone còn cần thiết; snapshot chịu retention; hints có thể là thông tin duy nhất về write mà replica đích đang thiếu.

## 4. Commit log: dữ liệu chưa flush và khả năng thu hồi segment

### 4.1. Commit log tồn tại để làm gì?

Trên replica, một mutation thường được ghi vào **commit log** rồi được phản ánh vào **memtable**. Nếu node gặp sự cố trước khi memtable flush thành SSTable, Cassandra có thể **replay** commit log phù hợp khi khởi động để khôi phục mutation.

Commit log được tổ chức thành **segment**, là nhóm file ghi nối tiếp. Một segment có thể chứa mutation thuộc **nhiều bảng**; việc một bảng đã flush chưa đủ để bỏ segment nếu vẫn có mutation của bảng khác trong segment cần replay.

~~~mermaid
flowchart LR
    W["Mutation từ client"] --> L["Commit log segment"]
    W --> M["Memtable"]
    M --> F["Flush → SSTable"]
    L --> X{"Mọi dữ liệu liên quan trong segment đã an toàn trên SSTable?"}
    X -->|Chưa| K["Segment vẫn cần cho recovery"]
    X -->|Rồi| D["Cassandra có thể thu hồi/tái sử dụng segment"]
~~~

**Commit log không phải bảng lịch sử truy vấn** và không thay backup. Khi segment không còn cần cho recovery, Cassandra có thể thu hồi; không được kỳ vọng commit log giữ mãi mọi mutation.

### 4.2. `commitlog_sync` khác dung lượng commit log

Chế độ đồng bộ commit log (ví dụ `periodic` hay `batch` trong các phiên bản hỗ trợ) ảnh hưởng quan hệ giữa ACK, fsync và cửa sổ rủi ro khi mất điện. Đây là vấn đề **độ bền ghi**, không phải cơ chế xóa SSTable.

Một request `LOCAL_QUORUM` kiểm soát số **replica ACK**, không thay thế chính sách fsync trên từng replica. RF = 3 cũng không có nghĩa commit log của mỗi node không thể đầy.

### 4.3. Khi nào commit log phình to?

| Quan sát | Khả năng nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| Commit log tăng cùng tốc độ ghi rồi ổn định | Dữ liệu đang chờ flush, segment được tuần hoàn | Theo dõi xu hướng, tốc độ ghi và cấu hình giới hạn. |
| Commit log tiếp tục tăng, flush backlog lớn | Memtable flush bị chậm do I/O hoặc áp lực hệ thống | Kiểm tra pending flush, disk latency, logs, compaction. |
| Dung lượng commit log cao dù một bảng ít ghi | Segment chứa mutation của bảng khác chưa flush | Quan sát **toàn node**, không chỉ một bảng. |
| Flush/segment allocation lỗi hoặc disk nearly full | Thiếu block/thiết bị chậm; write path có nguy cơ gián đoạn | Giữ an toàn dữ liệu, điều tra volume, không xóa segment thủ công. |
| Sau restart có replay commit log | Phục hồi mutation chưa được SSTable hóa trước sự cố | Theo dõi startup log, lỗi corruption và tình trạng ổ. |

Trong môi trường lab, `nodetool flush <keyspace> <table>` có thể giúp quan sát memtable chuyển sang SSTable; **không** nên chạy flush cưỡng bức bừa bãi trên production để làm commit log “nhỏ đi”. Flush tạo SSTable mới, tăng I/O và có thể làm compaction tốn tài nguyên hơn.

**Cấu hình giới hạn commit log** (ví dụ mức dung lượng tổng theo phiên bản) có thể khiến Cassandra kích hoạt flush để giải phóng segment. Nó không biến commit log thành một hàng đợi có thể an toàn xóa bằng lệnh hệ điều hành.

## 5. SSTable: dung lượng sống, nợ compaction và tombstone

### 5.1. Vì sao SSTable tăng dù số row logic không đổi?

SSTable là file **bất biến**. Một `UPDATE` thường tạo phiên bản mới; `DELETE` tạo tombstone; TTL hết tạo trạng thái xóa logic. Bản ghi cũ và tombstone có thể xuất hiện ở **nhiều SSTable** cho cùng partition. Khi đọc, Cassandra phải hòa giải theo timestamp và marker xóa.

Compaction giảm số file/chồng lấn bằng cách hợp nhất SSTable và loại bỏ nội dung **đủ điều kiện**. Tuy nhiên, nó có thể cần **ghi SSTable kết quả trước khi bỏ file đầu vào**. Điều này khiến dung lượng đĩa tạm tăng; một node đang sử dụng 90% đĩa có thể **không đủ headroom để compaction giải quyết chính vấn đề đó**.

~~~text
Trước compaction:    SSTable A + SSTable B + SSTable C       (còn trên đĩa)
Trong compaction:    A + B + C + SSTable mới đang được ghi   (đỉnh sử dụng)
Sau khi hoàn tất:    SSTable mới hoạt động; input được bỏ khi an toàn
Snapshot/backup:     có thể vẫn tham chiếu A/B/C dù chúng không còn active
~~~

### 5.2. Compaction strategy làm thay đổi mẫu tiêu thụ đĩa

| Chiến lược | Đặc trưng đáng quan sát | Không nên suy luận |
| --- | --- | --- |
| **SizeTieredCompactionStrategy (STCS)** | Gom các SSTable có kích thước gần nhau; workload cập nhật có thể tạo nhiều SSTable. | SSTable count thấp tự động có nghĩa ít tombstone. |
| **LeveledCompactionStrategy (LCS)** | Tổ chức SSTable theo level để giảm chồng lấn đọc; có write amplification. | LCS luôn ít I/O ghi hơn mọi chiến lược khác. |
| **TimeWindowCompactionStrategy (TWCS)** | Nhóm dữ liệu theo cửa sổ thời gian, thường hợp time series TTL gần đồng nhất. | Qua một cửa sổ là file chắc chắn bị xóa đúng lịch. |

Khi phân tích node đầy đĩa, xem **số SSTable, compaction backlog, kích thước file, TTL/tombstone, kích thước partition và tốc độ ghi** cùng nhau. Ép major compaction khi disk còn rất ít có thể làm tình hình nguy hiểm hơn vì cần không gian tạo output.

### 5.3. Tombstone ảnh hưởng cả dung lượng lẫn read latency

Một bảng với `default_time_to_live = 2592000` (30 ngày) không nhất thiết chỉ lưu tối đa 30 ngày byte dữ liệu. Sau khi TTL hết, tombstone cần tuân theo điều kiện purge như `gc_grace_seconds`, quan hệ với dữ liệu cũ ở SSTable khác và lịch compaction.

**Tombstone scan** còn có thể làm truy vấn `LIMIT 10` phải duyệt nhiều marker trước khi tìm đủ 10 hàng còn sống. Khi disk tăng kèm read latency và tombstone warnings, nên xem lại **thiết kế partition/bucket, TTL, compaction và lịch repair** thay vì chỉ tăng ngưỡng cảnh báo.

## 6. Hints: dữ liệu chờ gửi cho replica, không phải bản sao chính thức

### 6.1. Tại sao có hints?

Giả sử RF = 3 ở `dc1`; một write `LOCAL_QUORUM` được hai replica N1, N2 ACK còn N3 tạm mất kết nối. Cassandra có thể lưu **hint** tại một node phù hợp để chuyển mutation bị bỏ lỡ cho N3 khi N3 trở lại.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant C as Coordinator
    participant N1 as Replica N1
    participant N2 as Replica N2
    participant N3 as Replica N3 (offline)
    App->>C: INSERT LOCAL_QUORUM
    C->>N1: Mutation
    C->>N2: Mutation
    C-xN3: Không tới được
    N1-->>C: ACK
    N2-->>C: ACK
    C-->>App: Write success
    Note over C: Có thể giữ hint cho N3
    Note over N3: Khi trở lại cần nhận mutation bị lỡ
    C->>N3: Phát lại hint nếu còn hợp lệ
~~~

Sơ đồ minh họa. Hints phụ thuộc cấu hình, tình trạng node, phiên bản, giới hạn thời gian/dung lượng và chính sách phát lại. Không phải mọi write thiếu replica đều luôn có hint được giữ vĩnh viễn.

### 6.2. Đọc số liệu hints như thế nào?

| Tín hiệu | Diễn giải | Câu hỏi vận hành |
| --- | --- | --- |
| Dung lượng thư mục hints tăng | Có mutation đang chờ phát lại hoặc chưa dọn | Replica đích nào đang chậm/down? |
| Backlog hints không giảm dù node đích đã lên | Handoff có thể bị lỗi, nghẽn hoặc không kịp truyền | Network/streaming, authentication, disk và logs có bình thường không? |
| Tốc độ tạo hints vượt tốc độ giao thành công | Sự cố replica kéo dài hoặc write rate quá cao | Có cần xử lý node/đường truyền trước khi backlog tràn? |
| Hint bị hết hạn hoặc không thể phát lại | Cơ chế handoff không còn đủ để đồng bộ | Cần đánh giá anti-entropy repair, đặc biệt tombstone. |

`nodetool netstats` và các metrics/logs hints của phiên bản đang chạy có thể giúp quan sát handoff/streaming. Một số bản Cassandra có lệnh liệt kê pending hints; **hãy xác minh bằng `nodetool help` trước khi sử dụng**, không giả định mọi phiên bản có đúng một tên lệnh hay một trường metric.

### 6.3. Không coi hints là repair

Hint là cơ chế **best-effort, có giới hạn** cho mutation bị bỏ lỡ. Nếu replica offline quá lâu hoặc hint bị giới hạn/hết thời gian lưu, **anti-entropy repair** vẫn cần thiết để đối chiếu dữ liệu. Điều này đặc biệt quan trọng với `DELETE`/TTL: replica từng bỏ lỡ tombstone có thể giữ dữ liệu cũ và gây **zombie data** nếu tombstone đã bị purge quá sớm ở các replica khác.

**Không xóa trực tiếp thư mục hints khi disk đầy.** Hành động ấy có thể xóa cơ hội giao những mutation chưa nhận. Nếu cần can thiệp đặc biệt, phải xử lý theo runbook sự cố, đánh giá replica đích, độ bền dữ liệu và kế hoạch repair sau đó.

## 7. Snapshot: vì sao đã compaction mà đĩa vẫn không giảm?

### 7.1. Snapshot Cassandra là gì?

Một snapshot của bảng thường giữ **tham chiếu/hard link** tới các file SSTable tại thời điểm tạo snapshot, cùng metadata phục vụ khôi phục. Vì hard link có thể trỏ tới cùng inode:

1. Tạo snapshot **không nhất thiết nhân đôi ngay toàn bộ byte SSTable**.
2. Khi compaction tạo SSTable mới và muốn bỏ SSTable cũ, file cũ **vẫn được giữ** nếu snapshot còn tham chiếu.
3. Tổng dung lượng filesystem có thể tăng dần sau nhiều vòng compaction và nhiều snapshot, dù bảng logic chỉ có một tập dữ liệu hiện hành.

~~~mermaid
flowchart TD
    A["SSTable X đang active"] --> H["Tạo snapshot S: hard link tới X"]
    A --> C["Compaction tạo SSTable Y"]
    C --> N["Y là SSTable active mới"]
    H --> O["X vẫn chiếm đĩa do snapshot tham chiếu"]
    O --> R["Dọn snapshot theo retention"]
    R --> F["X giải phóng block khi không còn tham chiếu"]
~~~

Snapshot không có nghĩa ứng dụng có thể tự `SELECT` dữ liệu cũ từ snapshot qua bảng hiện tại. Để khôi phục phải có **quy trình restore** phù hợp với cấu trúc file, schema, phiên bản và kế hoạch backup.

### 7.2. Quan sát snapshot

~~~bash
# Xem snapshot đang có trên node.
nodetool listsnapshots

# Chỉ dùng trong lab hoặc theo runbook backup đã duyệt.
nodetool snapshot -t obs-lab-01 telemetry_obs
~~~

`nodetool listsnapshots` thường cho biết snapshot tag, keyspace/table và số liệu kích thước. Tuy nhiên, **số size báo cáo không nhất thiết bằng byte có thể lấy lại khi xóa một snapshot**, vì file có thể được chia sẻ giữa active SSTable và nhiều snapshot.

Khi cần dọn snapshot, phải xác định **retention, lịch sao lưu ra ngoài cluster và nhu cầu phục hồi**. Dùng lệnh `nodetool clearsnapshot` với tham số đúng theo `nodetool help clearsnapshot` của phiên bản; không tự xóa thư mục snapshot bằng `rm -rf` trên production.

### 7.3. Snapshot khác backup đã hoàn tất

- Snapshot nằm **cùng node/volume** không bảo vệ được trước hỏng toàn bộ đĩa hoặc mất cả máy.
- Backup đáng tin cậy thường cần chuyển dữ liệu ra hệ lưu trữ độc lập, kiểm tra tính toàn vẹn, giữ schema/cấu hình và thử restore.
- Snapshot của một cluster phân tán **không mặc nhiên là transaction snapshot nguyên tử của mọi partition/DC**; quy trình chụp nhất quán theo ứng dụng cần thiết kế riêng.
- Khi snapshot được sao lưu ra ngoài và retention cho phép, việc xóa snapshot cục bộ có thể giải phóng dung lượng, nhưng **không được xóa trước khi xác minh bản backup ngoài đã khả dụng**.

## 8. Bộ lệnh quan sát tối thiểu

Trong lab/staging, với node được cấp quyền phù hợp:

~~~bash
# Membership, ring và tình trạng node:
nodetool status
nodetool info

# Dữ liệu hiện hành ở cấp bảng, SSTable và tombstone:
nodetool tablestats telemetry_obs.readings_by_sensor_day

# Backlog compaction / công việc nền:
nodetool compactionstats
nodetool tpstats

# Streaming/handoff và snapshot:
nodetool netstats
nodetool listsnapshots

# Xác minh cú pháp theo đúng phiên bản:
nodetool help tablestats
nodetool help snapshot
~~~

| Công cụ | Trả lời tốt nhất | Không tự trả lời |
| --- | --- | --- |
| `df -h` | Volume đang còn bao nhiêu dung lượng? | Nguyên nhân nào trong Cassandra chiếm phần đó. |
| `du` theo thư mục | Nhóm đường dẫn nào đang lớn? | Dung lượng thu hồi chính xác khi có hard links. |
| `nodetool status` | Node/DC/rack nào đang up/down/joining? | Dữ liệu trên mọi replica đã đồng bộ chưa. |
| `nodetool tablestats` | SSTable/ước lượng kích thước và trạng thái bảng? | Tổng byte commit log, hints, snapshots và toàn filesystem. |
| `nodetool compactionstats` | Compaction có active/pending hay không? | Chính xác bao nhiêu byte chắc chắn sẽ được thu hồi. |
| `nodetool netstats` | Tình trạng streaming/handoff theo bản Cassandra? | Mọi mutation bị lỡ đã được repair đầy đủ chưa. |
| `nodetool listsnapshots` | Snapshot tag/bảng nào còn được giữ? | Mọi snapshot đã được backup ngoài cluster hay chưa. |

**Quan sát theo node trước, rồi tổng hợp theo cluster.** Một token range có nhiều replica, nhưng mỗi node có disk, commit log, hints và snapshot riêng. Cluster còn nhiều disk tổng cộng không cứu được một node mà volume dữ liệu đã hết chỗ.

## 9. Thí nghiệm CQL: phân biệt dữ liệu logic và dung lượng file

### 9.1. Tạo bảng lab

Ví dụ dùng DC tên `dc1` và RF = 3. Nếu lab không đủ ba node, phải điều chỉnh topology/RF/CL cho hợp lệ trước khi thử:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_obs
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_obs.readings_by_sensor_day (
    sensor_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    reading decimal,
    PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 2592000
  AND gc_grace_seconds = 864000;
~~~

Ở đây `(sensor_id, event_day)` là **partition key kép**, `event_time` và `event_id` là clustering columns. Cách chia partition theo ngày phù hợp ví dụ đọc dữ liệu từng cảm biến/ngày, đồng thời tránh cho một partition tăng vô hạn. RF = 3 là **ba bản sao mục tiêu**, không phải ba SSTable của cùng dữ liệu trên một node.

### 9.2. Ghi và đọc TTL

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_obs.readings_by_sensor_day
  (sensor_id, event_day, event_time, event_id, reading)
VALUES
  ('sensor-9', '2026-11-21', '2026-11-21T08:30:00Z',
   123e4567-e89b-42d3-a456-426614174001, 21.70);

SELECT event_time, reading,
       TTL(reading) AS ttl_remaining_seconds,
       WRITETIME(reading) AS write_time_us
FROM telemetry_obs.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21';
~~~

Nếu chưa có ghi khác cạnh tranh, `TTL(reading)` trả **số giây còn lại của cell** và `WRITETIME(reading)` trả timestamp ghi ở đơn vị microsecond. Chúng không nói khi nào SSTable hoặc commit log segment trên đĩa sẽ bị xóa.

### 9.3. Tạo chuỗi quan sát có kiểm soát

Trong **lab riêng**, có thể thực hiện các bước:

1. Ghi nhiều hàng vào cùng và khác partition; chụp số liệu `df`, `tablestats`, commit log và compaction.
2. Chạy `nodetool flush telemetry_obs readings_by_sensor_day` **chỉ trong lab**, rồi so sánh memtable/SSTable count, commit log và dung lượng thực.
3. Chạy `nodetool snapshot -t obs-lab-01 telemetry_obs`, kiểm tra `listsnapshots`.
4. Tiếp tục ghi, update hoặc delete một số hàng, rồi quan sát các SSTable và tombstone sau các flush/compaction do hệ thống thực hiện.
5. Kiểm tra rằng snapshot giữ lại file cũ ngay cả khi dữ liệu logic đã bị thay đổi; **không** suy rằng snapshot làm mọi file tăng gấp đôi ngay lúc tạo.
6. Chỉ dọn snapshot lab khi xác nhận không cần restore và dùng đúng lệnh của phiên bản; quan sát `df` thay đổi bao nhiêu.

Trong các phép thử này, **không tự tạo lỗi replica hoặc xóa commit log/hints** để làm số liệu “đẹp hơn”. Nếu cần mô phỏng hints do node down, dùng cluster lab biệt lập, có bản phục hồi và xác nhận quy trình repair.

## 10. Từ metric Cassandra đến dashboard thực tế

### 10.1. Các nhóm metric cần đặt cạnh nhau

| Nhóm dashboard | Ví dụ metric/tín hiệu | Lý do đặt cạnh nhau |
| --- | --- | --- |
| **Capacity** | Used/free disk từng volume, tốc độ tăng GB/ngày, dự đoán thời điểm hết chỗ | Đánh giá khả năng tiếp tục flush và compaction. |
| **SSTable & read** | Live/total disk, SSTable count, partition-size distribution, tombstone scan | Tìm nguyên nhân version/tombstone/partition lớn. |
| **Write & commit log** | Write latency/timeouts, commit log size/pending tasks, memtable flush backlog | Phát hiện không giải phóng segment vì write/flush nghẽn. |
| **Compaction** | Pending tasks, active compaction, bytes read/written, throughput | Đánh giá compaction debt và headroom tạm thời. |
| **Hints & replica** | Hints generated/delivered/pending, disk hints, node down, handoff failures | Tách sự cố replica khỏi tăng trưởng dữ liệu thông thường. |
| **Snapshots/backup** | Tổng số snapshot tag, tuổi snapshot, retention, backup success/restore tests | Hiểu vì sao file cũ vẫn được giữ và khả năng dọn có kiểm soát. |
| **Node resources** | CPU, heap/GC, disk latency/IOPS, filesystem error, network bandwidth | Xác định bottleneck của flush, compaction, repair hoặc handoff. |

Tên JMX thường được sử dụng trong Cassandra có thể bao gồm các metric thuộc nhóm **`Table`**, **`CommitLog`**, **`Compaction`**, **`ThreadPools`** và các nhóm liên quan hints. Ví dụ các tên `LiveDiskSpaceUsed`, `TotalDiskSpaceUsed`, `PendingTasks`, `TotalCommitLogSize` có mặt trong nhiều phiên bản, nhưng **schema MBean, label exporter và đơn vị phải xác minh tại node thật**.

Ví dụ logic gắn nhãn dashboard:

~~~text
cluster      = cassandra-main
datacenter   = dc1
rack         = rack-a
node         = cassandra-01
filesystem   = /data
keyspace     = telemetry_obs
table        = readings_by_sensor_day
component    = commitlog | sstable | hints | snapshot
~~~

Đây là **bộ nhãn thiết kế**, không phải tên nhãn Prometheus có sẵn ở mọi exporter. Với metric ở cấp node không có keyspace/table, không được gắn nhãn bảng tùy tiện. Khi dashboard tổng hợp disk theo DC, tránh cộng lại các replica như thể đó là dung lượng logic chưa nhân bản.

### 10.2. Ba quy tắc để cảnh báo hữu ích

1. **Đo tốc độ tăng và mức free, không chỉ % used.** Hai volume cùng 85% used nhưng một volume chỉ còn 20 GB, volume kia còn 2 TB có mức rủi ro khác nhau.
2. **Kết hợp nhân quả.** Disk tăng + hints tăng + một replica down gợi ý điều tra handoff; disk tăng + compaction pending + SSTable count tăng gợi ý nợ compaction; disk tăng + snapshot count/age tăng gợi ý retention.
3. **Cảnh báo theo node/volume trước rồi xem service impact.** Một node gần full có thể gây write timeout dù tổng dung lượng toàn cluster còn dư.

### 10.3. Ví dụ ngưỡng cảnh báo minh họa

| Mức cảnh báo | Điều kiện minh họa | Việc cần làm |
| --- | --- | --- |
| **Theo dõi** | Disk vượt 75% và tăng nhanh so với baseline | Xác định tốc độ tăng, snapshot/hints/compaction trends. |
| **Cần xử lý** | Disk vượt 85% hoặc free thấp hơn headroom dự kiến cho compaction | Kiểm tra thành phần chiếm chỗ, giảm tải/điều chỉnh lịch bảo trì có kế hoạch. |
| **Khẩn cấp** | Disk trên 95%, allocation/flush lỗi hoặc write timeout tăng | Ưu tiên bảo toàn dữ liệu, đánh giá khả năng phục vụ và runbook sự cố. |

Các ngưỡng **75/85/95% chỉ để minh họa**, không phải chuẩn Cassandra. Ngưỡng production phải dựa vào kích thước volume, tốc độ ghi, compaction strategy, SSTable lớn nhất, yêu cầu streaming, thời gian phản ứng và dự phòng khi một replica down.

### 10.4. Dự kiến headroom khi compaction

Ví dụ một volume **1.000 GB** đã dùng **820 GB**, còn **180 GB**. Một lượt compaction dự kiến phải tạo file kết quả **150 GB**, trong khi hệ thống tiếp tục ghi thêm **40 GB** trước khi xóa được input.

~~~text
Free ban đầu                         : 180 GB
Ước lượng output compaction tạm      : 150 GB
Ghi mới trong cùng giai đoạn         :  40 GB
Nhu cầu bổ sung tối thiểu minh họa    : 190 GB
Kết luận                             : thiếu ít nhất 10 GB headroom
~~~

Đây là phép ước lượng **đơn giản hóa**: input/output có thể được giải phóng theo các thời điểm khác, filesystem overhead, snapshot và nhiều compaction song song khiến đỉnh thực tế thay đổi. Tuy vậy, bài học rõ ràng: **không thể trông chờ một compaction lớn giải cứu một volume đã không đủ chỗ tạo output**.

## 11. Java Driver: quan sát từ phía ứng dụng

Disk, hints và SSTable là chỉ số **server-side**; ứng dụng Java nên đồng thời đo **end-to-end latency, timeout, CL, tỷ lệ lỗi và truy vấn chủ đạo** để phát hiện tác động tới người dùng.

Ví dụ dùng **Apache Cassandra Java Driver 4.x**; đoạn code in số liệu đơn giản thay cho hệ thống metrics thực. Nó không cần quyền quản trị cluster.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.concurrent.TimeUnit;

public final class ObservedCassandraRead {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement statement = session.prepare(
                "SELECT event_time, event_id, reading " +
                "FROM telemetry_obs.readings_by_sensor_day " +
                "WHERE sensor_id = ? AND event_day = ? LIMIT 50");

            BoundStatement request = statement.bind(
                    "sensor-9", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            long startedAt = System.nanoTime();
            boolean success = false;
            try {
                for (Row row : session.execute(request)) {
                    System.out.println(row.getInstant("event_time")
                        + " => " + row.getBigDecimal("reading"));
                }
                success = true;
            } catch (RuntimeException error) {
                // Production: phân loại timeout/unavailable/overloaded,
                // ghi metric có label query_name, DC, consistency level.
                // Không log payload nhạy cảm hoặc retry mù mọi lỗi.
                System.err.println("reading query failed: "
                    + error.getClass().getSimpleName());
                throw error;
            } finally {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - startedAt);
                System.out.println("query=readings_by_sensor_day"
                    + " consistency=LOCAL_QUORUM"
                    + " success=" + success
                    + " elapsed_ms=" + elapsedMs);
            }
        }
    }
}
~~~

**Giải thích cách đo:**

- Timer ở đây đo **thời gian client xử lý toàn bộ iterator**, nên có thể gồm cả fetch các page và thời gian in kết quả; khác latency nội bộ một request trên replica. Với production, instrument tại lớp driver/request để phân biệt server latency, network, paging và xử lý của client.
- `LOCAL_QUORUM` với RF = 3 tại `dc1` cần hai replica phản hồi; timeout ở CL này **không tự kết luận** đĩa đầy, vì nguyên nhân có thể là node down, network, read path hay compaction.
- Label `query_name` nên có số lượng hữu hạn; tránh gắn partition key/UUID làm label metric vì tạo **cardinality cao** và nguy cơ lộ dữ liệu.
- Không cấp cho ứng dụng Java quyền `nodetool`, xóa snapshot, truncate hints hoặc can thiệp file storage. Quản trị disk thuộc kênh vận hành có phân quyền riêng.

## 12. Runbook: đĩa tăng nhanh, phân biệt nguyên nhân trong vài bước

### Bước 1 — Xác định phạm vi và mức độ nguy hiểm

- Node nào, DC/rack nào, **volume nào** gần đầy? Có disk write errors, memtable flush failures hoặc request timeout tăng không?
- `df` còn bao nhiêu GB? Tốc độ tăng GB/giờ so với thời gian phản ứng?
- Có node down, bootstrap, rebuild, repair, streaming hoặc major compaction đang chạy không?

Nếu đã có nguy cơ hết dung lượng khiến write path ngừng hoạt động, xử lý theo **quy trình sự cố có người chịu trách nhiệm**, ưu tiên bảo vệ dữ liệu và duy trì dịch vụ; không chạy các lệnh dọn phá hủy khi chưa hiểu nguyên nhân.

### Bước 2 — Tách các thành phần lưu trữ

- So `du` theo các thư mục thực với metric disk, có lưu ý hard links.
- Dùng `tablestats` xác định SSTable footprint tăng ở bảng nào.
- Kiểm tra commit log, flush metrics/queue và compaction backlog.
- Xem hints size/queue và tình trạng replica đích.
- Xem snapshot tags, tuổi snapshot, bản backup ngoài và retention.

### Bước 3 — Đối chiếu dấu hiệu với nguyên nhân

| Dấu hiệu kết hợp | Giả thuyết ưu tiên | Hành động tương đối an toàn |
| --- | --- | --- |
| Disk tăng, SSTable count và pending compaction tăng | Compaction không theo kịp write/update/delete | Đo I/O, workload, partition size, compaction; điều chỉnh tải/lịch theo runbook. |
| Commit log tăng, pending flush tăng | Flush không theo kịp, segment còn dữ liệu chưa SSTable hóa | Kiểm tra flush errors, disk latency và tài nguyên; không xóa commit log. |
| Hints tăng, node đích down | Handoff chưa hoàn tất | Khôi phục replica/network, theo dõi replay; đánh giá repair nếu bỏ lỡ. |
| Hints tăng dù node đích up | Delivery throttled/lỗi hoặc backlog lớn | Kiểm tra logs, throughput, phiên bản và repair policy. |
| Snapshot count/size tăng sau backup định kỳ | Retention không được dọn hoặc backup chưa hoàn tất | Xác minh bản backup ngoài, dọn theo retention có phê duyệt. |
| Disk tăng lúc compaction/streaming, sau đó giảm | Output mới cùng tồn tại với input cũ | Đảm bảo headroom, tránh tạo thêm tác vụ nặng. |
| SSTable live giảm nhưng `df` không giảm | Snapshot/hard links hoặc open-file references còn giữ block | Kiểm tra retention/references; không xóa active SSTable. |
| Nhiều tombstone, read latency cao, SSTable phình | Xóa/TTL và chồng lấn phiên bản | Xem schema, TTL, bucketing, compaction và lịch repair. |

### Bước 4 — Khắc phục nguyên nhân, không chỉ triệu chứng

Nếu snapshot đã được sao lưu/kiểm chứng và hết hạn, có thể dọn **đúng snapshot** theo runbook. Nếu hints tồn đọng, khôi phục replica và tổ chức repair theo nhu cầu. Nếu flush/compaction nghẽn, xử lý I/O/partition design/capacity trước khi chạy nhiều lệnh bảo trì. Nếu dữ liệu thực tăng bền vững, cần **mở rộng capacity** hoặc sửa retention/schema, không phải xóa SSTable thủ công.

### Bước 5 — Xác minh sau can thiệp

- Tốc độ tăng disk có giảm và free headroom đủ cho các tác vụ tiếp theo?
- Client latency/timeouts, write failures và replica health có hồi phục?
- Commit log/hints/compaction backlog có giảm theo thời gian?
- Snapshot retention có được ghi nhận và khả năng restore còn nguyên?
- Có cần theo dõi repair sau khi replica bỏ lỡ mutation/tombstone?

Ghi lại **trước/sau**, phiên bản Cassandra, DC/node/volume, hành động, thời điểm và người phê duyệt để lần sau không phải suy đoán lại nguyên nhân.

## 13. Những quan niệm sai dễ gây sự cố

| Nhận định | Đánh giá | Lý do |
| --- | --- | --- |
| “`df` lớn hơn `tablestats` nghĩa Cassandra báo sai.” | **Sai** | Filesystem còn commit log, hints, snapshot, file tạm và thứ khác. |
| “Snapshot luôn nhân đôi ngay dung lượng active SSTable.” | **Sai** | Hard links có thể chia sẻ block; byte cũ được giữ sau compaction. |
| “Xóa snapshot làm mọi byte báo cáo của snapshot được trả lại.” | **Sai** | Block có thể còn được tham chiếu bởi active SSTable/snapshot khác. |
| “Xóa commit log segment bằng tay giúp giảm disk mà không ảnh hưởng dữ liệu.” | **Sai** | Có thể phá khả năng replay mutation chưa flush. |
| “Hints là replica bổ sung, không cần repair.” | **Sai** | Hints có thời hạn/giới hạn và không thay anti-entropy repair. |
| “`LOCAL_QUORUM` bảo đảm mọi replica đã nhận mutation.” | **Sai** | RF 3 chỉ cần 2 ACK tại local DC để đạt CL. |
| “TTL hết là SSTable sẽ biến mất ngay.” | **Sai** | Tombstone, gc grace và compaction quyết định thu hồi vật lý. |
| “Major compaction luôn là cách tốt nhất khi node đầy đĩa.” | **Sai** | Có thể cần nhiều disk tạm và ảnh hưởng I/O nghiêm trọng. |
| “Cluster còn 40% disk là ổn, dù một node đã 97%.” | **Sai** | Write/flush có thể lỗi tại node/volume gần đầy. |
| “Disk tăng vì hints nên cứ xóa thư mục hints.” | **Sai** | Replica đích có thể mất mutation chưa được giao. |
| “Quản trị viên cần xem trạng thái backup ngoài trước khi dọn snapshot.” | **Đúng** | Snapshot tại node có thể là điểm phục hồi cuối cùng. |

## 14. Bài tập có đáp án

**Bài 1.** Sau khi compaction hoàn tất, `tablestats` báo active SSTable giảm mạnh nhưng `df` gần như không đổi. Tại sao?

**Đáp án:** Snapshot hoặc backup cục bộ có thể còn tham chiếu SSTable đầu vào qua hard links; file được thay trong active set nhưng block chưa được giải phóng. Cần xem `listsnapshots`, retention và những tham chiếu còn lại.

**Bài 2.** RF = 3 trong `dc1`. N3 offline, write `LOCAL_QUORUM` success ở N1/N2. Hints của coordinator tăng. Có thể khẳng định N3 đã ghi bền mutation chưa?

**Đáp án:** **Không.** Quorum chỉ cần 2 ACK, hints là mutation chờ giao. Cần phục hồi N3, theo dõi hint delivery và repair nếu cần.

**Bài 3.** Tại sao một commit log segment chưa thể thu hồi dù một bảng vừa flush?

**Đáp án:** Segment có thể chứa mutation của **nhiều bảng**; vẫn còn dữ liệu của bảng khác cần replay. Cassandra quản lý thu hồi dựa vào trạng thái an toàn của các mutation liên quan.

**Bài 4.** Volume có 180 GB free; compaction output dự kiến 150 GB, write mới khoảng 40 GB trước khi input được giải phóng. Có đủ headroom theo ước lượng đơn giản không?

**Đáp án:** **Không.** Nhu cầu tối thiểu minh họa là 190 GB, thiếu ít nhất 10 GB, còn chưa tính metadata và tác vụ khác. Không nên ép compaction lớn trên volume ấy.

**Bài 5.** Vì sao `LIMIT 10` không bảo đảm read chỉ xử lý 10 hàng/tombstone?

**Đáp án:** Cassandra có thể phải duyệt nhiều phiên bản/tombstone trước khi tìm đủ mười hàng **còn sống**. Cần kiểm tra tombstone scanned và partition/SSTable design.

**Bài 6.** Dung lượng hints tăng nhanh sau khi một node down. Hướng xử lý đầu tiên nên là xóa file hints hay sửa nguyên nhân replica down?

**Đáp án:** **Điều tra và phục hồi replica/network** trước, theo dõi handoff; không xóa file hints thủ công. Sau offline dài, đánh giá lịch repair và `gc_grace_seconds`.

**Bài 7.** Một dashboard cộng `du -sh` của thư mục data với `du -sh` snapshots rồi trừ khỏi free của `df`. Điều gì có thể sai?

**Đáp án:** Có thể **đếm trùng** SSTable được hard link ở cả active và snapshot; `df` lại đo block ở cấp filesystem. Cần hiểu inode và cách metric tính dung lượng.

**Bài 8.** Một bảng đặt TTL 30 ngày nhưng disk vẫn tăng suốt 45 ngày. Có chắc TTL không hoạt động?

**Đáp án:** **Không.** Dữ liệu có thể đã hết hạn logic nhưng tombstone/SSTable chưa đủ điều kiện purge, snapshot giữ file hoặc write rate vượt tốc độ thu hồi. Kiểm tra `TTL()`, compaction, gc grace, dữ liệu khác TTL và retention.

## 15. Sơ đồ lựa chọn đường điều tra

~~~mermaid
flowchart TD
    A["Cassandra node sắp đầy disk"] --> B["Kiểm tra df/free GB, tốc độ tăng và error"]
    B --> C{"Thành phần nào tăng nổi bật?"}
    C -->|Commit log| L["Kiểm tra memtable flush, segment và disk I/O"]
    C -->|SSTable| S["Kiểm tra compaction debt, TTL, tombstone, partition size"]
    C -->|Hints| H["Kiểm tra replica down, handoff, repair"]
    C -->|Snapshot| P["Kiểm tra backup thành công, hard links, retention"]
    C -->|Streaming/compaction output| T["Kiểm tra headroom và công việc nền"]
    L --> X["Khắc phục nguyên nhân; không xóa file dữ liệu thủ công"]
    S --> X
    H --> X
    P --> X
    T --> X
    X --> V["Xác minh disk free, latency, backlog và dữ liệu còn an toàn"]
~~~

**Tóm tắt:** `df` nói **node còn chỗ để ghi hay không**; `tablestats` và metrics SSTable nói **dữ liệu đang hoạt động lớn ra sao**; commit log cho biết **mutation nào còn cần phục hồi**, hints phản ánh **mutation đang chờ replica khác**, còn snapshot cho biết **file cũ nào được giữ lại để phục hồi**. Compaction và streaming có thể cần thêm disk tạm, vì vậy quan sát phải kết hợp **dung lượng hiện tại, tốc độ tăng, headroom, công việc nền và tình trạng replica**. Khi điều tra đầy đĩa, ưu tiên bảo toàn dữ liệu và khắc phục nguyên nhân thay vì xóa thủ công những file Cassandra còn cần.
