# Cân bằng replica, leader và dung lượng đĩa

Kafka lưu mỗi partition thành một tập replica phân bố trên các broker. Một replica trong tập là leader, nhận produce/fetch request và điều phối replication; các replica còn lại theo kịp log của leader. Khi partition hoặc replica phân bố lệch, một số broker có thể chịu nhiều request, network và disk I/O hơn phần còn lại. Nếu dung lượng đĩa cũng lệch, broker có thể chạm ngưỡng đầy dù toàn cluster vẫn còn nhiều dung lượng trống.

Vận hành cân bằng cần xem ba lớp riêng: **replica placement** quyết định dữ liệu nằm trên broker nào; **leader placement** quyết định broker nào phục vụ traffic chính; **log directory placement** quyết định replica nằm trên ổ/đường dẫn nào bên trong một broker. Ba lớp có liên quan nhưng không phải một thao tác duy nhất. Cân bằng đúng giúp phân tán tải và headroom, đồng thời vẫn giữ replication, ISR và khả năng phục hồi.

## 1. Phân biệt replica, leader và log directory

Một topic có nhiều partition. Mỗi partition có replication factor (RF), tức số bản sao được cấu hình. Ví dụ RF=3 có một leader và hai follower:

~~~mermaid
flowchart LR
    P["Producer / Consumer"] --> L["Broker 1: Leader replica"]
    L --> F2["Broker 2: Follower replica"]
    L --> F3["Broker 3: Follower replica"]
    L --> D1[("Log directory")]
    F2 --> D2[("Log directory")]
    F3 --> D3[("Log directory")]
~~~

| Khái niệm | Ý nghĩa | Cân bằng tác động đến |
|---|---|---|
| Replica | Bản sao log của một partition trên broker | Disk, network replication, recovery |
| Leader replica | Replica đang phục vụ ghi và đọc theo cơ chế leader/follower | Produce/fetch traffic, request load |
| Follower replica | Replica fetch dữ liệu từ leader để theo kịp log | Network, disk write và replication lag |
| Log directory | Thư mục/volume lưu segment của replica trên broker | Dung lượng và I/O giữa các ổ |
| ISR | Tập replica đang đủ điều kiện đồng bộ với leader | Durability và khả năng bầu leader an toàn |

Một broker có thể giữ nhiều replica nhưng chỉ một phần trong số đó là leader. Vì vậy, cân bằng tổng replica count chưa chắc cân bằng request load. Ngược lại, leader count bằng nhau chưa chắc disk usage bằng nhau vì partition có kích thước và throughput khác nhau.

## 2. Ba loại mất cân bằng thường gặp

### Replica imbalance

Một số broker chứa quá nhiều replica, trong khi broker khác còn ít replica hoặc nhiều dung lượng trống. Điều này có thể làm disk usage, follower replication traffic và recovery time lệch nhau.

### Leader imbalance

Một broker giữ quá nhiều leader partition. Broker đó nhận phần lớn produce request và thường cả consumer fetch request, làm CPU, network và request handler bận hơn các broker khác.

### Disk/log directory imbalance

Một broker có nhiều volume hoặc log directory nhưng replica tập trung vào một volume. Một disk có thể gần đầy hoặc có latency cao trong khi volume khác còn trống.

~~~mermaid
flowchart TD
    A["Thu thập replica, leader, disk và traffic metrics"] --> B{"Loại mất cân bằng?"}
    B --> C["Replica placement"]
    B --> D["Leader placement"]
    B --> E["Log directory placement"]
    C --> F["Replica reassignment giữa broker"]
    D --> G["Preferred leader election / reassignment"]
    E --> H["Replica log-dir reassignment"]
    F --> I["Verify ISR, traffic và disk"]
    G --> I
    H --> I
~~~

Trước khi thay đổi, cần xác định đúng lớp mất cân bằng. Chạy preferred leader election không di chuyển replica sang broker khác. Di chuyển replica không nhất thiết làm leader traffic cân bằng ngay. Thêm disk vào broker cũng không tự động chuyển mọi replica cũ sang volume mới.

## 3. Thu thập trạng thái hiện tại

Bắt đầu bằng việc chụp lại phân bố partition, replica, leader và ISR:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --describe
~~~

Kết quả có các trường quan trọng:

- Partition: partition index.
- Leader: broker ID đang làm leader.
- Replicas: danh sách broker giữ replica theo thứ tự assignment.
- Isr: tập replica hiện đồng bộ.

Ví dụ:

~~~text
Topic: orders  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
Topic: orders  Partition: 1  Leader: 1  Replicas: 1,3,4  Isr: 1,3,4
Topic: orders  Partition: 2  Leader: 2  Replicas: 2,3,4  Isr: 2,3,4
~~~

Trong ví dụ, broker 1 đang làm leader cho hai partition, còn broker 2 làm leader cho một partition. Chỉ ba dòng chưa đủ kết luận cluster mất cân bằng; cần thống kê toàn bộ topic, partition, leader, replica size và traffic.

### Kiểm tra log directory và kích thước replica

~~~bash
bin/kafka-log-dirs.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --describe \
  --broker-list 1,2,3,4
~~~

Lệnh trả về log directory, replica partition và kích thước log theo broker. Dùng kết quả để tìm:

- Volume nào gần đầy.
- Replica nào chiếm nhiều dung lượng.
- Broker nào chứa nhiều dữ liệu hơn dự kiến.
- Log directory nào offline hoặc có lỗi.

Kiểm tra cả filesystem metrics ở hệ điều hành: dung lượng còn trống, inode, disk utilization, read/write latency và queue depth. Kafka log size không bao gồm toàn bộ chi phí ngoài filesystem như log ứng dụng, file tạm hoặc dữ liệu khác cùng volume.

### Thu thập leader và traffic metrics

Theo dõi ít nhất:

- Số leader partition trên mỗi broker.
- Tổng replica count và tổng replica bytes trên mỗi broker.
- Produce/fetch bytes và request rate theo broker/topic.
- Request handler idle, network processor idle và request latency.
- Under-replicated partitions, ISR shrink/expand và offline partitions.
- Disk free bytes, I/O latency và throughput theo từng log directory.

Đếm leader chỉ là proxy. Một leader của partition có traffic rất cao có thể nặng hơn nhiều leader partition ít hoạt động. Khi có metrics theo topic/partition, ưu tiên cân bằng theo traffic và kích thước dữ liệu thay vì chỉ đếm số lượng.

## 4. Lập bảng cân bằng trước khi thay đổi

Tạo inventory cho từng broker:

| Broker | Leader count | Replica count | Replica bytes | Disk used | Disk free | Produce/fetch load |
|---|---:|---:|---:|---:|---:|---|
| 1 | 120 | 360 | 4,2 TB | 78% | 22% | Cao |
| 2 | 95 | 340 | 3,8 TB | 70% | 30% | Trung bình |
| 3 | 70 | 310 | 3,1 TB | 61% | 39% | Thấp |
| 4 | 75 | 320 | 3,4 TB | 66% | 34% | Trung bình |

Đây là dữ liệu minh họa. Bảng thực tế cần tính theo volume/log directory và ghi rõ thời điểm snapshot.

Một cluster có thể có replica count gần bằng nhau nhưng replica bytes chênh lệch lớn. Tương tự, leader count bằng nhau nhưng throughput khác nhau do partition hot key hoặc workload không đồng đều. Đặt mục tiêu cân bằng theo nhiều chỉ số:

1. Không broker nào vượt ngưỡng disk capacity đã định.
2. Replica bytes phân bố hợp lý theo dung lượng và hiệu năng volume.
3. Leader traffic không tập trung quá mức vào một số broker.
4. Replica của cùng partition không vi phạm fault domain/rack placement.
5. ISR ổn định trong suốt quá trình thay đổi.

Không cố đạt các con số bằng nhau tuyệt đối. Dung lượng disk, network và phần cứng broker có thể khác nhau; cân bằng phải xét capacity thực tế của từng broker.

## 5. Tính dung lượng đĩa và headroom

Ước lượng dung lượng topic trước replication. Tốc độ đầu vào trong công thức nên là tốc độ byte thực sự được lưu trên log sau compression, hoặc phải được điều chỉnh từ ingress rate theo compression ratio:

\[
LogicalStorage \approx IngressBytesPerSecond \times RetentionSeconds
\]

Dung lượng vật lý toàn cluster cho topic có thể ước lượng:

\[
PhysicalStorage \approx LogicalStorage \times ReplicationFactor
\]

Đây là ước lượng ban đầu. Cần điều chỉnh theo compression, compaction, retention.bytes, segment/index overhead, transaction metadata, internal topics và phân bố thực tế.

Ví dụ topic tăng dữ liệu trên log trung bình 20 MiB/s sau compression, retention 3 ngày và RF=3:

\[
LogicalStorage \approx 20 \times 86.400 \times 3
= 5.184.000\ MiB \approx 4,94\ TiB
\]

\[
PhysicalStorage \approx 4,94 \times 3 = 14,82\ TiB
\]

Nếu có 6 broker với phân bố lý tưởng, mỗi broker giữ trung bình khoảng 2,47 TiB cho topic này. Thực tế phải cộng các topic khác, internal topics và headroom; leader/follower placement và partition size có thể làm từng broker lệch khỏi trung bình.

### Dành headroom cho vận hành

Không lập kế hoạch để disk chạy sát 100%. Kafka cần khoảng trống để:

- Tiếp nhận dữ liệu mới trong lúc retention chưa xóa segment cũ.
- Reassign replica và giữ đồng thời nguồn/đích trong thời gian copy.
- Phục hồi sau broker failure hoặc rolling maintenance.
- Chịu burst traffic và thay đổi retention.
- Cho hệ điều hành và tiến trình khác hoạt động ổn định.

Mức headroom 20–30% có thể dùng làm điểm bắt đầu cho một số môi trường, nhưng không phải ngưỡng phổ quát. Chọn theo tốc độ tăng dữ liệu, thời gian phát hiện/phản ứng, tốc độ reassignment, dung lượng volume và kịch bản mất một broker.

Với từng broker hoặc volume, tính:

\[
RequiredFreeSpace \geq GrowthDuringResponseWindow + ReassignmentReserve
\]

Nếu broker có thể phải nhận thêm replica khi một broker khác mất, capacity planning phải mô phỏng tình huống degraded cluster, không chỉ trạng thái bình thường.

## 6. Replica placement và rack awareness

Replica placement quyết định broker nào giữ bản sao của mỗi partition. Mục tiêu không chỉ là chia đều số replica mà còn phải tách failure domain.

Nếu có ba rack, partition RF=3 nên được phân bố qua ba rack khi hạ tầng và cấu hình hỗ trợ:

~~~text
orders-0:
  leader   -> broker-1 / rack-a
  follower -> broker-4 / rack-b
  follower -> broker-7 / rack-c
~~~

Cấu hình broker rack:

~~~properties
broker.rack=rack-a
~~~

Mỗi broker phải khai báo rack đúng với vị trí vật lý/availability zone. Kafka có thể dùng rack awareness trong replica assignment để tránh đặt các replica của cùng partition trong cùng rack khi đủ broker và điều kiện phù hợp.

Kiểm tra:

- Mỗi broker có broker.rack chính xác và nhất quán.
- Số rack và số broker mỗi rack đủ cho replication factor.
- Reassignment JSON không vô tình đưa hai replica cùng partition về cùng failure domain.
- Broker mới được khai báo đúng rack trước khi đưa vào assignment.

Rack awareness không thay thế replication factor, ISR hoặc backup. Nếu toàn bộ rack mất, partition vẫn cần replica ở rack khác đủ đồng bộ để tiếp tục hoạt động.

## 7. Di chuyển replica giữa broker bằng reassignment

Replica reassignment thay đổi danh sách broker lưu replica cho một partition. Đây là thao tác phù hợp khi:

- Thêm broker mới và muốn phân phối lại dữ liệu.
- Chuẩn bị loại bỏ broker cũ.
- Một broker gần đầy trong khi broker khác còn capacity.
- Cần sửa replica placement hoặc rack distribution.

Ví dụ partition orders-0 hiện có replicas 1,2,3; muốn chuyển sang 2,3,4:

~~~json
{
  "version": 1,
  "partitions": [
    {
      "topic": "orders",
      "partition": 0,
      "replicas": [2, 3, 4]
    }
  ]
}
~~~

Lưu JSON vào file reassignment đã được review, sau đó thực hiện:

~~~bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --reassignment-json-file reassignment.json \
  --execute
~~~

Kiểm tra tiến độ:

~~~bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --reassignment-json-file reassignment.json \
  --verify
~~~

Kafka tạo replica ở broker đích, copy dữ liệu và đưa replica mới vào trạng thái phù hợp trước khi hoàn tất thay đổi assignment. Trong quá trình copy, broker nguồn và đích cùng chịu thêm disk/network I/O. Không xóa dữ liệu replica cũ bằng tay để ép reassignment hoàn thành.

### Sinh assignment gợi ý

Với danh sách topic cần di chuyển và danh sách broker đích, có thể dùng chế độ generate:

~~~bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --topics-to-move-json-file topics-to-move.json \
  --broker-list "1,2,3,4,5,6" \
  --generate
~~~

Kết quả generate là đề xuất assignment, không phải lệnh đã áp dụng. Review JSON để kiểm tra replica count, rack distribution, broker capacity và leader placement trước khi chạy execute.

### Throttle reassignment

Replica copy có thể tranh network và disk với traffic production. Khi chạy reassignment lớn, đặt throttle phù hợp theo hỗ trợ của Kafka version:

~~~bash
bin/kafka-reassign-partitions.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --reassignment-json-file reassignment.json \
  --execute \
  --throttle 10485760
~~~

Ví dụ giới hạn replication reassignment ở khoảng 10 MiB/s theo cơ chế CLI tương ứng. Kiểm tra help và tài liệu đúng Kafka release vì option, phạm vi và cách áp dụng throttle có thể thay đổi. Bắt đầu với tốc độ thấp, quan sát ISR, request latency, disk/network và tăng dần nếu cluster còn headroom.

Không throttle quá thấp khiến reassignment kéo dài nhiều ngày trong khi broker nguồn sắp đầy. Không throttle quá cao làm replication traffic ảnh hưởng producer/consumer và ISR.

## 8. Cân bằng leader bằng preferred leader election

Khi replica placement đã đúng nhưng leader tập trung vào một số broker, có thể đưa leader về preferred replica. Danh sách replica trong assignment có thứ tự; replica đầu tiên là preferred replica.

Ví dụ partition có replicas [1,2,3], broker 1 là preferred replica. Nếu broker 2 đang làm leader nhưng broker 1 đã trong ISR, preferred leader election có thể chuyển leader về broker 1.

~~~bash
bin/kafka-leader-election.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --election-type preferred \
  --all-topic-partitions
~~~

Có thể giới hạn theo topic/partition bằng option tương ứng của CLI:

~~~bash
bin/kafka-leader-election.sh \
  --bootstrap-server kafka-1.example.com:9092 \
  --election-type preferred \
  --topic orders \
  --partition 0
~~~

Preferred leader election không copy dữ liệu và không thay đổi replica assignment. Nó chỉ chuyển leadership về preferred replica nếu replica đó đủ điều kiện. Nếu preferred replica không nằm trong ISR, election có thể không thực hiện được cho partition đó.

### Tự động cân bằng preferred leader

Broker có các cấu hình liên quan tới preferred replica election, thường gồm:

~~~properties
auto.leader.rebalance.enable=true
leader.imbalance.per.broker.percentage=10
leader.imbalance.check.interval.seconds=300
~~~

Tự động cân bằng có thể giúp leader quay về preferred replica sau khi broker phục hồi. Nhưng nếu preferred replica assignment ban đầu vốn không cân bằng theo traffic hoặc broker capacity, auto rebalance không giải quyết được gốc rễ. Hãy thiết kế assignment hợp lý trước.

### Không nhầm preferred election với unclean election

Preferred election chỉ chọn preferred replica đủ điều kiện. Unclean leader election có thể chọn replica không thuộc ISR khi không còn replica ISR khả dụng; việc này có nguy cơ mất dữ liệu đã được ghi ở leader cũ nhưng chưa replicate tới replica được chọn.

Không dùng unclean election như công cụ cân bằng leader. Chỉ xem xét trong quy trình disaster recovery đã chấp nhận rõ rủi ro mất dữ liệu và có phê duyệt vận hành.

## 9. Cân bằng log directory trong một broker

Broker có thể cấu hình nhiều đường dẫn log:

~~~properties
log.dirs=/data/kafka-1,/data/kafka-2,/data/kafka-3
~~~

Một partition replica được lưu trong một log directory trên broker. Nếu một volume gần đầy, có thể di chuyển replica sang log directory khác trong cùng broker bằng replica log-dir reassignment, không cần đổi broker placement.

Ví dụ reassignment JSON chỉ định log directory đích cho từng replica:

~~~json
{
  "version": 1,
  "partitions": [
    {
      "topic": "orders",
      "partition": 0,
      "replicas": [1, 2, 3],
      "log_dirs": ["/data/kafka-2", "any", "any"]
    }
  ]
}
~~~

Trong ví dụ, replica trên broker 1 được chỉ định sang /data/kafka-2; các replica khác giữ lựa chọn directory do broker quyết định. Danh sách log_dirs tương ứng theo thứ tự với danh sách replicas. Kiểm tra cú pháp, khả năng hỗ trợ và đường dẫn hợp lệ theo Kafka version và OS.

Thực hiện bằng kafka-reassign-partitions với JSON file như ví dụ reassignment; theo dõi tiến độ bằng verify và kafka-log-dirs. Một số phiên bản có throttle riêng cho replica alter log dirs; xác nhận option trước khi sử dụng.

Không xóa thư mục partition thủ công để giải phóng disk. Việc đó có thể làm replica offline hoặc mất dữ liệu. Dùng API reassignment để Kafka quản lý quá trình copy và cập nhật metadata.

## 10. Thêm broker, loại broker và rebalance

### Khi thêm broker

Broker mới không tự động nhận lại toàn bộ replica cũ. Nó có thể tham gia cluster và nhận partition mới hoặc replica khi có assignment mới, nhưng để phân bố lại dữ liệu hiện có thường cần reassignment hoặc công cụ cân bằng như Cruise Control.

Quy trình:

1. Cài broker, cấu hình ID duy nhất, listener, storage, rack và security.
2. Xác nhận broker đã đăng ký và hoạt động ổn định.
3. Kiểm tra disk/network/capacity trước khi nhận replica.
4. Sinh reassignment plan cho các topic cần phân phối lại.
5. Review RF, rack placement, leader distribution và bytes.
6. Execute theo batch có throttle.
7. Verify ISR, disk và traffic sau từng batch.

### Khi loại broker

Không dừng hoặc xóa broker khỏi hạ tầng trước khi di chuyển các replica cần giữ khỏi broker đó. Broker có thể đang là leader hoặc replica duy nhất còn ISR cho một partition.

Quy trình tổng quát:

1. Liệt kê mọi replica và leader trên broker cần loại.
2. Chọn broker đích còn đủ capacity và đúng rack policy.
3. Reassign tất cả replica cần giữ sang broker đích.
4. Chờ reassignment hoàn tất và xác nhận ISR đủ.
5. Xác nhận broker không còn replica được quản lý và không còn leader.
6. Thực hiện quy trình decommission theo Kafka release và kiến trúc KRaft đang dùng.

Nếu cluster không đủ capacity để chứa dữ liệu sau khi loại một broker, cần mở rộng broker/disk hoặc giảm dữ liệu theo retention policy trước khi decommission.

## 11. Cân bằng theo dung lượng, không chỉ số replica

Hai partition có thể khác nhau nhiều lần về kích thước. Ví dụ broker A có 100 replica mỗi replica 10 GB, broker B có 80 replica mỗi replica 100 GB. Broker B giữ ít replica hơn nhưng chứa nhiều dữ liệu hơn.

Để lập kế hoạch, dùng các trọng số:

- Replica bytes trên disk.
- Leader bytes ingress/egress hoặc request rate.
- Follower replication bytes.
- Disk throughput và latency.
- Broker CPU, network và request handler utilization.
- Dung lượng volume và tốc độ tăng dữ liệu.

Với broker có phần cứng không đồng nhất, có thể dùng capacity weight thay vì chia đều. Broker có disk nhỏ hoặc network yếu không nên nhận cùng số replica bytes như broker lớn.

### Partition hotness và key skew

Nếu một partition có traffic cao do key phân bố lệch, di chuyển replica sang broker khác có thể chuyển tải sang broker mới nhưng không loại bỏ hot partition. Cần xem producer key distribution, partitioner, consumer assignment và khả năng tăng partition/repartition. Tăng partition có thể ảnh hưởng key ordering và stateful consumer; không dùng như biện pháp tức thời khi chưa đánh giá.

## 12. KRaft metadata quorum không phải data replica

Trong KRaft, controller quorum lưu metadata log của cluster và bầu controller leader. Đây là một mặt phẳng điều khiển riêng với replica log của topic.

| Thành phần | Vai trò | Cân bằng liên quan |
|---|---|---|
| Broker data replicas | Lưu partition data và phục vụ produce/fetch | Replica reassignment, leader election, log-dir movement |
| KRaft controller quorum | Lưu metadata và điều phối metadata changes | Controller membership, quorum availability và controller placement |

Di chuyển replica của topic không làm di chuyển controller quorum. Tương tự, cân bằng controller không tự phân phối lại dữ liệu partition. Với cluster KRaft, theo dõi controller quorum health riêng; không thực hiện thao tác broker decommission nếu chưa hiểu vai trò controller/broker của node và yêu cầu quorum theo phiên bản triển khai.

## 13. Tác động của reassignment tới ISR và durability

Reassignment làm phát sinh replication traffic. Trong thời gian copy:

- Replica đích cần bắt kịp dữ liệu từ leader.
- Broker nguồn/đích tiêu thụ disk và network.
- ISR có thể thay đổi nếu replica chậm hoặc broker chịu tải.
- Request latency producer/consumer có thể tăng.

Giữ replication factor và kiểm tra min.insync.replicas. Ví dụ RF=3, min.insync.replicas=2 và producer acks=all yêu cầu tối thiểu hai replica trong ISR để chấp nhận write theo policy tương ứng. Nếu ISR tụt dưới ngưỡng, producer có thể nhận NotEnoughReplicas hoặc NotEnoughReplicasAfterAppend thay vì tiếp tục ghi với durability thấp hơn.

Không giảm min.insync.replicas hoặc bật unclean election chỉ để reassignment dễ hoàn thành. Nếu replica lag, tìm nguyên nhân disk/network/broker trước khi thay durability policy.

## 14. Theo dõi tiến độ và xác minh sau thay đổi

Trong khi reassignment:

- Theo dõi kafka-reassign-partitions verify để biết partition nào còn pending.
- Theo dõi under-replicated partitions và ISR shrink/expand.
- Theo dõi network throughput và disk utilization ở broker nguồn/đích.
- Theo dõi produce/fetch latency và error rate.
- Theo dõi dung lượng từng log directory.

Sau khi hoàn tất:

1. Chạy kafka-topics describe để xác nhận replica assignment và ISR.
2. Chạy kafka-log-dirs describe để xác nhận kích thước và vị trí log.
3. Thống kê leader count/traffic theo broker.
4. Kiểm tra disk free và headroom theo volume.
5. Kiểm tra consumer lag, producer latency và business SLO.
6. Xác nhận không còn reassignment hoặc replica alter log dir đang chạy.

Không chỉ dựa vào thông báo execute thành công. Execute có thể bắt đầu thao tác; verify mới cho biết reassignment đã hoàn tất hay chưa.

## 15. Thứ tự thao tác khuyến nghị

Nếu cluster vừa lệch replica, vừa lệch leader và disk, xử lý theo thứ tự có kiểm soát:

1. **Ổn định cluster:** xử lý offline partition, broker lỗi, ISR thiếu hoặc disk sắp đầy trước.
2. **Giải quyết capacity:** bổ sung broker/disk hoặc giải phóng dung lượng theo retention đã phê duyệt.
3. **Cân bằng replica:** reassignment theo batch, giữ rack placement và replication factor.
4. **Cân bằng log directory:** chuyển replica khỏi volume nóng/đầy nếu cần.
5. **Cân bằng leader:** preferred leader election sau khi replica placement ổn định.
6. **Đánh giá lại:** so sánh disk bytes, leader traffic, ISR, latency và SLO với baseline.

Không thực hiện tất cả thay đổi cùng lúc. Nếu vừa reassignment vừa leader election diện rộng, khó xác định thao tác nào gây ra traffic spike hoặc ISR churn.

## 16. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Broker gần đầy dù cluster còn disk trống | Replica bytes phân bố lệch hoặc volume imbalance | Dùng kafka-log-dirs, inventory replica bytes và reassignment |
| Leader count cân bằng nhưng latency lệch | Partition hotness hoặc traffic khác nhau | Xem produce/fetch bytes và request rate theo partition |
| Reassignment chậm | Throttle thấp, network/disk yếu, replica lag hoặc broker bận | Kiểm tra verify, replication traffic, disk latency và ISR |
| Under-replicated partitions tăng | Follower không theo kịp leader | Kiểm tra network, disk, CPU và throttle |
| Preferred election không chuyển leader | Preferred replica không ở ISR hoặc election chưa đủ điều kiện | Kiểm tra ISR và replica order |
| Disk đầy sau khi thêm volume | Replica cũ không tự chuyển sang volume mới | Dùng log-dir reassignment và xác minh đường dẫn |
| Một rack mất làm nhiều partition unavailable | Replica placement không trải qua failure domain | Kiểm tra broker.rack và assignment |
| Decommission broker làm partition offline | Di chuyển replica chưa hoàn tất hoặc thiếu broker đích | Khôi phục broker nếu có thể, kiểm tra ISR và reassignment |
| Producer gặp NotEnoughReplicas | ISR thấp hơn min.insync.replicas | Phục hồi follower/replication; không hạ durability policy tùy tiện |

## 17. Production checklist

- [ ] Có inventory replica, leader, ISR, replica bytes và log directory theo broker.
- [ ] Theo dõi disk free, I/O latency và growth rate theo từng volume.
- [ ] Tính capacity gồm retention, replication factor, compression, compaction và headroom.
- [ ] Kiểm tra broker.rack và failure-domain placement.
- [ ] Phân biệt replica reassignment, preferred leader election và log-dir reassignment.
- [ ] Review JSON assignment trước execute; giữ đúng replication factor và rack separation.
- [ ] Chạy reassignment theo batch và throttle theo capacity thực tế.
- [ ] Theo dõi ISR, under-replicated partitions, request latency, network và disk trong quá trình copy.
- [ ] Không xóa log directory hoặc replica file thủ công.
- [ ] Không dùng unclean leader election như công cụ cân bằng.
- [ ] Cân bằng leader sau khi replica placement ổn định.
- [ ] Xác minh assignment, ISR, leader distribution và log directory sau thay đổi.
- [ ] Có kế hoạch decommission broker chỉ sau khi replica đã được di chuyển và verify.
- [ ] Theo dõi KRaft controller quorum riêng với data replica.
- [ ] Kiểm thử kịch bản mất broker/rack và bảo đảm cluster còn đủ capacity để phục hồi.

Cân bằng Kafka cluster cần đồng thời xét replica bytes, leader traffic và dung lượng từng log directory. Replica reassignment thay đổi broker giữ dữ liệu; preferred leader election thay đổi broker phục vụ partition; log-dir reassignment di chuyển dữ liệu giữa các volume trên cùng broker. Thực hiện theo từng bước, có throttle và xác minh ISR, headroom cùng SLO sau mỗi đợt để cải thiện phân bố mà không đánh đổi durability.
