# Xử lý gần đầy đĩa và thay retention an toàn

Kafka lưu log segment trên disk của broker. Khi một filesystem gần đầy, broker có thể không append được record, follower không bắt kịp leader, partition rời ISR và producer/consumer bắt đầu gặp timeout hoặc lỗi. Nếu xử lý vội bằng cách xóa file log thủ công hoặc thay retention trên toàn cluster, có thể làm mất dữ liệu, khiến replica không phục hồi được hoặc phá vỡ yêu cầu replay.

Vận hành an toàn cần làm rõ ba câu hỏi:

1. Broker và log directory nào đang thiếu dung lượng?
2. Dữ liệu nào đang chiếm dung lượng và có thể giải phóng theo chính sách?
3. Thay retention sẽ ảnh hưởng đến thời gian replay, consumer lag, state store và nghĩa vụ lưu trữ như thế nào?

Bài này xây dựng runbook xử lý disk pressure và quy trình thay retention cho Kafka cluster dùng KRaft hoặc ZooKeeper. Các lệnh minh họa theo Kafka CLI; kiểm tra tùy chọn help của đúng phiên bản đang chạy trước khi đưa vào production.

## 1. Vì sao disk pressure nguy hiểm?

Kafka append record vào partition log. Mỗi partition có leader và có thể có follower replica trên broker khác. Broker cần dung lượng cho:

- Segment đang ghi và các segment đã đóng.
- Replica của topic nghiệp vụ.
- Internal topics như consumer offsets, transaction state, Kafka Streams changelog/repartition và Connect config/status/offsets.
- Index và metadata file.
- Log compaction tạo file segment mới trong khi xử lý segment cũ.
- Replica reassignment, recovery và catch-up.
- Dung lượng dự phòng cho traffic burst và hoạt động vận hành.

Khi disk gần đầy, hệ quả có thể lan rộng:

- Produce request thất bại vì broker không thể ghi thêm dữ liệu.
- Follower không thể ghi replica mới, dẫn đến ISR shrink và under-replicated partitions.
- Leader election hoặc broker restart có thể làm tình trạng nghiêm trọng hơn nếu replica còn lại cũng thiếu dung lượng.
- Log cleaner thiếu không gian hoặc không thể hoàn tất compaction.
- Broker có thể mất log directory hoặc partition trên directory bị lỗi.
- KRaft controller cần lưu metadata log; nếu metadata directory cùng filesystem bị đầy, khả năng điều khiển cluster cũng có thể bị ảnh hưởng.

Một broker có nhiều log.dirs có thể vẫn phục vụ các partition ở directory còn hoạt động khi một directory bị offline, nhưng các partition đặt trên directory lỗi sẽ không khả dụng. Không giả định broker còn online nghĩa là mọi partition đều khỏe.

## 2. Phân biệt filesystem, log directory và partition

Một broker có thể có một hoặc nhiều thư mục log:

~~~properties
log.dirs=/data/kafka-1,/data/kafka-2
~~~

Mỗi log directory có thể nằm trên filesystem hoặc volume riêng. Disk usage tổng host không cho biết directory nào đầy. Cần đối chiếu ba lớp:

| Lớp | Cần biết | Công cụ |
|---|---|---|
| Filesystem/volume | Dung lượng còn lại, inode, mount và I/O | df, df -i, iostat, Performance Monitor |
| Kafka log directory | Broker nào, directory nào, replica nào chiếm dung lượng | kafka-log-dirs.sh |
| Topic/partition | Partition nào lớn, leader/replica/ISR ra sao | kafka-topics.sh, JMX, log-dir output |

KRaft có thể dùng metadata.log.dir để đặt metadata log riêng. Nếu không cấu hình, metadata log được lưu trong log directory đầu tiên. Vì vậy không được xóa hoặc di chuyển file trong thư mục này theo suy đoán; xác định rõ broker config và vai trò của directory trước khi thao tác.

## 3. Nhận diện sớm disk pressure

Không đợi filesystem đạt 100% mới hành động. Thiết lập cảnh báo theo headroom còn lại và tốc độ tăng dữ liệu.

Các tín hiệu nên theo dõi:

- Disk used percentage và free bytes theo từng mount/log directory.
- Tốc độ tăng dung lượng theo giờ/ngày.
- Inode usage, nhất là khi có nhiều segment/index file.
- Disk write/read latency, IOPS, throughput và queue depth.
- Kích thước log directory theo broker.
- Kích thước replica theo topic/partition.
- Under-replicated partitions và ISR shrink.
- Offline log directory count.
- Log cleaner backlog hoặc compaction throughput.
- Produce error rate, request latency và consumer lag.

Ví dụ chính sách cảnh báo có thể dùng warning ở mức 70%, critical ở 85% và emergency ở 95%, nhưng đây chỉ là mốc tham khảo. Ngưỡng thật phải dựa trên tốc độ ingest, thời gian cần để mở rộng volume, kích thước replica lớn nhất và dung lượng cần cho recovery/reassignment.

Một filesystem còn 15% có thể đã nguy hiểm nếu ingest tăng nhanh và chỉ còn vài phút trước khi đầy. Ngược lại, một volume archive tăng chậm có thể dùng ngưỡng khác.

## 4. Runbook: xác định broker và directory đang đầy

### 4.1. Kiểm tra filesystem trên từng broker

Linux:

~~~bash
df -h
df -i
iostat -xz 1
~~~

Kiểm tra mount của Kafka data directory và metadata directory. Khi cần tìm thư mục lớn, dùng du có giới hạn đúng filesystem; tránh quét toàn bộ storage đang quá tải nếu thao tác đó tạo thêm I/O đáng kể.

Windows broker có thể kiểm tra dung lượng volume bằng File Explorer hoặc PowerShell:

~~~powershell
Get-Volume
Get-PSDrive -PSProvider FileSystem
~~~

### 4.2. Xem dung lượng replica qua Kafka CLI

~~~bash
bin/kafka-log-dirs.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --broker-list 1,2,3
~~~

Lệnh trả về thông tin log directory và replica size theo broker. Dùng kết quả để xác định directory và partition nào chiếm nhiều dung lượng. Tùy phiên bản Kafka, định dạng JSON và tùy chọn CLI có thể khác.

### 4.3. Kiểm tra topic, leader và ISR

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --describe \
  --topic orders
~~~

Xem partition leader, replicas và ISR. Với disk pressure, cần kiểm tra xem replica nào đã rời ISR và broker nào đang giữ leader của partition quan trọng.

### 4.4. Kiểm tra cấu hình retention hiệu lực

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
~~~

Ghi lại các cấu hình cleanup.policy, retention.ms, retention.bytes, segment.bytes, segment.ms và các override khác. Cần phân biệt topic đang dùng cấu hình riêng hay đang kế thừa broker default.

## 5. Xác định topic nào đang tiêu thụ dung lượng

Dung lượng trên một broker không bằng dung lượng logical của topic. Mỗi partition có thể có nhiều replica; replica được phân bố trên các broker khác nhau. Một topic có replication factor 3 tạo khoảng ba bản lưu trữ cho mỗi byte logical, chưa tính overhead và phân bố không đồng đều.

Phân tích theo thứ tự:

1. Liệt kê các topic và partition.
2. Lấy replica size từ log directory của từng broker.
3. Tổng hợp dung lượng theo topic và theo broker.
4. So sánh với ingress rate và retention policy.
5. Xác định topic tăng nhanh, topic có retention vô hạn hoặc topic có partition lệch tải.
6. Kiểm tra internal topics và DLT/retry topics; chúng cũng có thể chiếm dung lượng đáng kể.

Một số metric JMX hữu ích gồm kích thước log theo topic/partition, bytes in/out, replica traffic và trạng thái ISR. Tên metric cụ thể có thể thay đổi theo Kafka release và exporter; đối chiếu metric catalog của phiên bản đang chạy.

Không kết luận topic nào gây đầy disk chỉ từ số lượng record. Record size, compression ratio, replication factor, partition distribution và retention đều ảnh hưởng đến dung lượng.

## 6. Ưu tiên xử lý khi disk gần đầy

Runbook tổng quát:

~~~mermaid
flowchart TD
    A["Cảnh báo disk pressure"] --> B["Xác định broker / filesystem / log dir"]
    B --> C["Kiểm tra ISR, leaders và replica sizes"]
    C --> D{"Còn đủ dung lượng an toàn?"}
    D -->|Có| E["Phân tích topic và retention"]
    D -->|Không| F["Giảm ingress hoặc tạm dừng producer không thiết yếu"]
    F --> G["Mở rộng volume / thêm capacity"]
    E --> H["Chọn topic có thể cleanup theo policy"]
    H --> I["Thay retention có kiểm soát"]
    G --> J["Theo dõi replica và ISR"]
    I --> J
    J --> K["Xác minh disk headroom và consumer replay"]
~~~

Thứ tự ưu tiên thực tế:

1. **Ổn định cluster:** kiểm tra broker health, ISR, leader và controller quorum.
2. **Giảm tốc độ tăng:** throttle hoặc tạm dừng producer không thiết yếu theo quyết định của service owner.
3. **Mở rộng capacity:** tăng dung lượng volume hoặc cung cấp storage mới nếu có thể.
4. **Giải phóng dữ liệu theo policy:** thay retention cho topic được phép giảm thời gian lưu hoặc xóa topic đã hết vòng đời sau khi xác minh owner.
5. **Cân bằng replica:** reassignment khi các broker đích còn đủ headroom.
6. **Xác minh:** kiểm tra dung lượng, ISR, request error, consumer lag và khả năng replay.

Nếu mọi broker đều gần đầy, reassignment giữa các broker trong cùng cluster không tạo thêm dung lượng tổng. Nó chỉ chuyển áp lực từ broker này sang broker khác và có thể làm tăng network/disk I/O.

## 7. Các cách giải phóng hoặc bổ sung dung lượng

### 7.1. Giảm ingress trước khi disk đầy

Khi tốc độ ingest cao hơn tốc độ cleanup, giảm ingress có thể mua thời gian để mở rộng storage:

- Throttle producer theo tenant/topic nếu hệ thống hỗ trợ.
- Tạm dừng luồng backfill hoặc replay không cấp thiết.
- Dừng producer tạo duplicate hoặc retry storm.
- Giảm payload không cần thiết ở upstream sau khi có thay đổi contract được kiểm soát.

Không tắt replication hoặc hạ min.insync.replicas chỉ để tiếp tục ghi khi disk đầy. Điều đó có thể biến một vấn đề capacity thành mất dữ liệu khi broker tiếp tục lỗi.

### 7.2. Mở rộng volume hiện tại

Mở rộng volume thường là phương án ít tác động tới phân bố partition nhất nếu storage platform cho phép tăng dung lượng online. Cần xác minh:

- Volume/filesystem có hỗ trợ expand online không.
- Filesystem đã được grow để nhận dung lượng mới chưa.
- IOPS/throughput có tăng theo dung lượng hay vẫn giữ quota cũ.
- Tất cả broker cần thiết có đủ capacity, không chỉ broker đang alert.
- Có đủ thời gian và headroom để hoàn tất thao tác.

Không coi việc tăng dung lượng volume là hoàn tất cho tới khi filesystem báo đúng free space và Kafka tiếp tục ghi/replicate ổn định.

### 7.3. Thêm log directory hoặc volume mới

Broker có thể cấu hình nhiều log directory để lưu partition replica trên nhiều directory:

~~~properties
log.dirs=/data/kafka-a,/data/kafka-b,/data/kafka-c
~~~

Thêm directory mới có thể giúp Kafka đặt các partition mới hoặc replica được di chuyển vào storage mới theo cơ chế phân bổ của broker. Tuy nhiên, thêm log.dirs không tự động di chuyển toàn bộ partition hiện có sang volume mới.

Cần kiểm tra yêu cầu restart, mount permissions, ownership, filesystem và cấu hình theo Kafka version. Với KRaft, giữ riêng metadata directory nếu kiến trúc đã tách; không di chuyển metadata log bằng thao tác file thủ công.

### 7.4. Reassign replica sang broker còn headroom

Nếu broker A gần đầy nhưng broker B còn dung lượng, có thể di chuyển replica bằng partition reassignment. Reassignment tạo thêm network và disk I/O, nên cần throttle và theo dõi ISR.

Ví dụ lệnh thực thi với file reassignment đã được tạo, review và lưu:

~~~bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --reassignment-json-file reassignment.json \
  --execute \
  --throttle 50000000
~~~

Kiểm tra tiến độ:

~~~bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --reassignment-json-file reassignment.json \
  --verify
~~~

Giá trị throttle trong ví dụ là byte/giây và chỉ mang tính minh họa. Tùy Kafka release, cú pháp hoặc cách sinh reassignment JSON có thể khác; xác minh bằng help của CLI.

Trước khi reassignment:

- Kiểm tra broker đích có đủ dung lượng sau khi cộng replica mới.
- Giữ rack awareness và failure domain mong muốn.
- Không chuyển mọi replica của cùng partition vào một broker/rack.
- Chọn batch nhỏ và throttle để không làm replication traffic áp đảo client traffic.
- Theo dõi ISR và disk utilization trong suốt quá trình.

### 7.5. Xóa topic đã hết vòng đời

Nếu topic không còn cần thiết, xác minh owner, retention obligation, consumer dependency và backup policy trước khi xóa. Topic deletion là thao tác ảnh hưởng toàn bộ dữ liệu topic, không phải cách dọn một vài record.

Không xóa internal topics như __consumer_offsets, transaction state hoặc Kafka Streams changelog để giải phóng disk. Xóa các topic này có thể làm hỏng consumer group state, transaction hoặc state restoration.

### 7.6. Tuyệt đối không xóa segment bằng filesystem command

Không dùng rm, del hoặc thao tác file manager để xóa segment/index khỏi Kafka log directory đang hoạt động. Broker quản lý offset, index, checkpoint, replica state và metadata của các file này. Xóa thủ công có thể gây log corruption, replica failure hoặc mất dữ liệu không nhất quán.

Dùng retention, DeleteRecords trong đúng tình huống, topic deletion hoặc reassignment theo API Kafka. DeleteRecords chỉ cắt prefix của partition tới offset được chỉ định; nó không xóa chọn lọc một event ở giữa log.

## 8. Hiểu retention trước khi thay đổi

Với topic dùng cleanup.policy=delete, Kafka có thể xóa segment đã đủ điều kiện theo thời gian hoặc kích thước.

Hai cấu hình chính:

- retention.ms: thời gian giữ log.
- retention.bytes: giới hạn dung lượng log cho mỗi partition.

Nếu cả hai được đặt, điều kiện nào khiến segment đủ điều kiện trước có thể kích hoạt cleanup. retention.bytes là giới hạn theo partition, không phải tổng dung lượng toàn topic.

Giới hạn kích thước này thuộc cơ chế delete cleanup. Với topic chỉ dùng compact, không dựa vào retention.bytes để giới hạn số key hoặc dung lượng trạng thái đã compact; cần quản lý key cardinality, tombstone và nhu cầu lưu state riêng.

Ví dụ topic có 12 partition và retention.bytes=10737418240 (10 GiB) có thể giữ tới khoảng 120 GiB logical log trước replication theo giới hạn kích thước, nếu mọi partition đều đạt mức đó. Dung lượng thực tế còn phụ thuộc retention time, segment, compression và phân bố dữ liệu.

Các giá trị -1 thường biểu thị không giới hạn theo thuộc tính tương ứng. Không đặt retention.ms=-1 hoặc retention.bytes=-1 cho topic lớn nếu chưa có kế hoạch capacity rõ ràng.

### 8.1. Ví dụ cấu hình delete retention

~~~properties
cleanup.policy=delete
retention.ms=604800000
retention.bytes=10737418240
segment.bytes=1073741824
segment.ms=3600000
~~~

Ví dụ giữ tối đa 7 ngày hoặc 10 GiB mỗi partition theo điều kiện cleanup, với segment mục tiêu 1 GiB hoặc 1 giờ. Đây là cấu hình minh họa; segment.ms và segment.bytes ảnh hưởng thời điểm log roll, không phải retention của record riêng lẻ.

### 8.2. Retention không xóa ngay record khi vừa đổi config

Kafka cleanup theo segment, không xóa tùy ý từng record. Segment đang active thường cần được roll trước khi có thể bị xóa. Broker kiểm tra retention theo chu kỳ, vì vậy sau khi giảm retention.ms, disk không nhất thiết giảm ngay.

Các yếu tố ảnh hưởng:

- segment.bytes và segment.ms.
- log.retention.check.interval.ms.
- Segment đã đóng hay còn active.
- Cleanup policy của topic.
- Log cleaner và tình trạng I/O.
- Replica trên các broker khác.
- Snapshot, backup và các bản sao downstream.

Không hứa một thời điểm giải phóng disk chính xác chỉ dựa trên giá trị retention mới.

## 9. Retention cho compacted topic khác delete topic

cleanup.policy có thể là delete, compact hoặc compact,delete.

| Policy | Hành vi |
|---|---|
| delete | Xóa segment theo retention time/size |
| compact | Giữ giá trị mới nhất theo key sau log compaction |
| compact,delete | Kết hợp compaction và xóa segment theo retention |

Với topic chỉ dùng compact, không áp dụng suy luận rằng retention.ms sẽ xóa dữ liệu cũ như delete policy. Compaction giữ trạng thái mới nhất theo key và có thể vẫn giữ rất nhiều key.

Tombstone (record có key và value null) biểu thị key đã bị xóa. delete.retention.ms quyết định thời gian tombstone được giữ để consumer có cơ hội quan sát delete; đây không phải thời gian retention thông thường của mọi record.

Với compact,delete, cả compaction và delete cleanup cùng tác động. Thay đổi policy có thể làm mất lịch sử mà consumer hoặc state rebuild đang phụ thuộc. Phải kiểm tra semantics của topic và consumer trước khi chỉnh.

## 10. Thay retention an toàn ở cấp topic

Ưu tiên thay retention theo từng topic thay vì giảm broker-wide default trên toàn cluster.

### 10.1. Lưu lại cấu hình hiện tại

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
~~~

Ghi lại cấu hình hiện tại và phân biệt explicit topic config với broker default. Xác định topic có dùng compact hay delete và có yêu cầu replay nào đang hoạt động không.

### 10.2. Đánh giá tác động trước khi giảm retention

Trước khi giảm từ 14 ngày xuống 3 ngày, kiểm tra:

- Consumer group nào có thể offline lâu hơn 3 ngày?
- Có consumer cần reset offset để replay không?
- Kafka Streams có cần input history để rebuild state không?
- Có DLT/retry hoặc workflow điều tra cần dữ liệu lâu hơn không?
- Có yêu cầu pháp lý, audit hoặc business retention không?
- Có archive/sink độc lập lưu dữ liệu cần thiết không?
- Disk đang đầy do topic này hay do topic khác?

Nếu consumer lag đã vượt retention mới, record mà consumer cần có thể bị xóa trước khi consumer xử lý. Consumer sau đó có thể gặp offset out of range và cần reset/recovery theo chính sách.

### 10.3. Cập nhật retention topic

Ví dụ thay retention time:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --add-config retention.ms=259200000
~~~

Ví dụ thay cả time và size limit:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --add-config retention.ms=259200000,retention.bytes=10737418240
~~~

Các lệnh trên thay đổi topic config. Kiểm tra cú pháp quoting/escaping của shell và Kafka version trước khi chạy. Không đưa credential hoặc password vào command history.

### 10.4. Rollback cấu hình

Nếu topic trước đó có explicit override, khôi phục đúng giá trị đã ghi nhận trước thay đổi. Nếu topic vốn kế thừa broker default, có thể bỏ override vừa thêm bằng lệnh:

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --entity-type topics \
  --entity-name orders \
  --alter \
  --delete-config retention.ms,retention.bytes
~~~

Sau rollback, chạy lại lệnh describe để xác nhận topic đã kế thừa broker default mong muốn. Không dùng delete-config nếu topic đã có explicit value cần được giữ; hãy khôi phục giá trị cũ thay thế.

### 10.5. Xác minh sau thay đổi

~~~bash
bin/kafka-configs.sh \
  --bootstrap-server broker-1.example.net:9092 \
  --entity-type topics \
  --entity-name orders \
  --describe
~~~

Sau đó theo dõi:

- Disk usage từng broker/log directory.
- Topic/partition size.
- Log segment cleanup và log cleaner activity.
- Consumer lag và offset out of range errors.
- Under-replicated partitions/ISR.
- Produce/fetch latency và error rate.
- State restoration hoặc replay job nếu có.

Nếu disk không giảm ngay, kiểm tra segment roll và retention check interval trước khi tiếp tục giảm retention nhiều lần.

## 11. Thay broker default retention có phạm vi rộng

Broker có default như:

~~~properties
log.retention.ms=604800000
log.retention.bytes=-1
log.retention.check.interval.ms=300000
log.segment.bytes=1073741824
~~~

Các default này áp dụng cho topic không override thuộc tính tương ứng. Thay broker default có thể ảnh hưởng nhiều topic cùng lúc; vì vậy cần inventory topic trước khi thay.

Quy trình:

1. Liệt kê topic và effective config.
2. Xác định topic có explicit override.
3. Tính dung lượng và replay impact của các topic kế thừa default.
4. Thử thay trên một topic đại diện hoặc môi trường staging.
5. Nếu thực sự cần broker-wide change, dùng quy trình config management/rolling procedure của cluster.
6. Xác minh effective config và theo dõi disk/consumer/ISR sau rollout.

Không dùng thay broker default như biện pháp khẩn cấp nếu chưa biết topic nào kế thừa default. Topic quan trọng có thể mất replay window ngoài dự kiến.

## 12. Ước lượng dung lượng trước khi tăng retention

Ước lượng ban đầu cho topic dùng delete retention:

~~~text
Logical storage ≈
  ingress bytes/second sau compression
  × retention seconds
~~~

Dung lượng cluster có replication:

~~~text
Cluster storage ≈
  tổng logical storage của các topic
  × replication factor trung bình
  + internal topics
  + index/segment overhead
  + compaction/recovery headroom
~~~

Ví dụ:

- Ingress sau compression: 5 MB/s.
- Retention: 7 ngày = 604.800 giây.
- Replication factor: 3.

~~~text
5 MB/s × 604.800 s = 3.024.000 MB ≈ 3,0 TB logical
3,0 TB × 3 ≈ 9,1 TB trên cluster
~~~

Đây là ước lượng payload thô, chưa tính overhead, internal topics, phân bố replica, segment, compaction và headroom. Dung lượng theo broker có thể lệch nếu partition assignment hoặc traffic không đều.

Khi tăng retention, tính thêm dung lượng trên từng broker chứ không chỉ tổng cluster. Cluster phải còn chỗ cho replica catch-up, reassignment và broker failure trong suốt thời gian retention mới.

## 13. Tình huống disk gần đầy: chọn hành động nào?

| Tình huống | Hành động phù hợp | Tránh |
|---|---|---|
| Một broker đầy, broker khác còn nhiều headroom | Xác định replica lớn và reassignment có throttle | Di chuyển quá nhiều replica cùng lúc |
| Tất cả broker đều đầy | Giảm ingress, mở rộng volume/capacity, xem xét retention được phê duyệt | Reassign vòng quanh trong cùng cluster |
| Một topic log tăng bất thường | Kiểm tra producer rate, record size, compression và topic retention | Giảm retention toàn cluster |
| Consumer lag vượt replay window | Đánh giá xử lý lag, tăng consumer capacity hoặc mở rộng storage | Giảm retention khiến consumer mất dữ liệu cần đọc |
| Compacted topic chiếm nhiều dung lượng | Kiểm tra key cardinality, update churn, cleaner backlog và tombstone | Đổi sang delete mà không kiểm tra semantics |
| Disk đầy do retry/DLT | Xác định nguyên nhân lỗi và policy của topic phụ | Xóa DLT trước khi xác minh dữ liệu cần điều tra |
| Log directory offline | Kiểm tra storage, mount, permissions và replica health | Xóa hoặc sửa file log thủ công |
| Disk đầy trên metadata volume KRaft | Khôi phục capacity của metadata filesystem và bảo vệ quorum | Xóa metadata log hoặc file snapshot theo phỏng đoán |

## 14. Sau khi giải phóng disk: xác minh cluster phục hồi

Không kết thúc runbook ngay khi df báo còn dung lượng. Cần xác minh Kafka hoạt động bình thường:

- Tất cả log directories cần thiết online.
- Controller quorum ổn định nếu dùng KRaft.
- Under-replicated partitions trở về 0 hoặc mức kỳ vọng.
- ISR không tiếp tục shrink.
- Leader partition được phân bố hợp lý.
- Produce và fetch request latency trở về mức bình thường.
- Consumer lag giảm hoặc có kế hoạch xử lý.
- Không có OffsetOutOfRange ngoài dự kiến.
- Log cleaner có thể theo kịp workload.
- Disk free bytes có xu hướng ổn định, không tiếp tục tăng nhanh.
- Replica reassignment hoàn tất hoặc đã dừng an toàn.
- Backup/retention policy và owner đã được ghi nhận.

Nếu đã giảm retention, cập nhật runbook và thông báo cho owner các consumer/replay job bị ảnh hưởng. Ghi lại config trước/sau, thời điểm thay đổi và dung lượng giải phóng thực tế.

## 15. Bài lab: mô phỏng disk pressure và thay retention

Dùng cluster test, không thực hiện trên production.

1. Tạo topic test có vài partition và replication factor phù hợp số broker.
2. Produce dữ liệu có tốc độ ổn định trong một khoảng thời gian.
3. Ghi nhận topic size và disk usage từng broker.
4. Đặt retention time ngắn và segment nhỏ trong môi trường lab để quan sát cleanup nhanh hơn.
5. Đổi retention time lớn hơn, tiếp tục produce và đo tốc độ tăng disk.
6. Hạ retention về mức thấp hơn và theo dõi segment roll/cleanup.
7. Tạo consumer cố ý lag để kiểm tra ảnh hưởng của retention tới replay.
8. Kiểm tra topic describe, effective config, ISR và consumer offset.
9. Thử reassignment một partition trong môi trường test và quan sát network/disk impact.
10. Ghi lại thời gian từ lúc đổi config đến khi dung lượng thực sự giảm.

Bảng ghi kết quả:

| Lần chạy | Retention | Segment | Ingress | Disk trước | Disk sau | Cleanup delay | Consumer lag |
|---|---|---|---:|---:|---:|---:|---:|
| A | 1 giờ | 64 MiB | | | | | |
| B | 6 giờ | 64 MiB | | | | | |
| C | 1 giờ | 16 MiB | | | | | |

Giữ record size, compression, partition count, replication factor và producer rate giống nhau để kết quả có thể so sánh. Segment nhỏ trong lab giúp quan sát cleanup, nhưng không mặc định phù hợp production vì tạo thêm file và metadata overhead.

## 16. Checklist vận hành

- [ ] Có cảnh báo free bytes, disk usage và inode theo từng log directory.
- [ ] Theo dõi tốc độ tăng dung lượng và thời gian còn lại trước khi đầy.
- [ ] Biết vị trí log.dirs và metadata.log.dir của từng broker.
- [ ] Có inventory topic, partition, replica size và retention config.
- [ ] Kiểm tra ISR/leader/controller health trước khi thay đổi.
- [ ] Có kế hoạch giảm ingress khi cần.
- [ ] Volume expansion và thêm log directory có quy trình đã kiểm thử.
- [ ] Reassignment được review, chia batch, throttle và verify.
- [ ] Không xóa log segment/index thủ công.
- [ ] Không xóa internal topics để giải phóng dung lượng.
- [ ] Hiểu retention.ms và retention.bytes áp dụng theo partition.
- [ ] Hiểu retention cleanup phụ thuộc segment roll và retention check interval.
- [ ] Phân biệt delete, compact và compact,delete.
- [ ] Kiểm tra consumer lag, replay, Streams state và DLT trước khi giảm retention.
- [ ] Thay topic retention trước khi cân nhắc broker-wide default.
- [ ] Tính capacity theo từng broker và giữ headroom cho recovery.
- [ ] Xác minh disk, ISR, latency, consumer lag và log cleaner sau thay đổi.
- [ ] Lưu lại cấu hình trước/sau, owner, lý do và kết quả.

Xử lý disk pressure an toàn bắt đầu bằng việc xác định đúng filesystem, log directory, replica và topic gây tăng dung lượng. Ưu tiên ổn định cluster, giảm ingress và bổ sung capacity; chỉ cleanup theo retention hoặc reassignment sau khi hiểu tác động đến ISR, consumer lag và replay. Retention là chính sách giữ log theo segment, không phải lệnh xóa record tức thời. Thay đổi theo từng topic, xác minh config hiệu lực và theo dõi đến khi disk, replication và consumer trở lại trạng thái ổn định.
