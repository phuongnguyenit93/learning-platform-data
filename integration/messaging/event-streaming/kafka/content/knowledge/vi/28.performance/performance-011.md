# Nhận diện nút thắt bằng metrics trước khi thay cấu hình

Kafka có thể chậm vì nhiều nguyên nhân khác nhau: producer tạo record nhanh hơn broker có thể nhận, broker phải chờ disk hoặc network, follower không theo kịp leader, consumer fetch không đủ dữ liệu, xử lý nghiệp vụ quá lâu hoặc một vài partition bị nóng. Các nguyên nhân này có thể tạo ra triệu chứng giống nhau như throughput giảm, latency tăng và consumer lag lớn.

Tối ưu hiệu năng hiệu quả bắt đầu bằng đo lường. Cần tạo baseline cho workload, xác định metric nào thay đổi cùng thời điểm xảy ra vấn đề, khoanh vùng thành phần bị nghẽn rồi kiểm chứng giả thuyết bằng một thay đổi có kiểm soát. Tăng thread, buffer, partition hoặc batch size khi chưa biết bottleneck có thể chỉ chuyển hàng đợi sang nơi khác, làm tăng memory, tail latency hoặc rủi ro durability.

## 1. Performance là nhiều mục tiêu khác nhau

Không có một metric duy nhất đại diện cho hiệu năng Kafka. Cần phân biệt:

| Mục tiêu | Cách đo | Câu hỏi cần trả lời |
|---|---|---|
| Throughput | records/s, messages/s, bytes/s | Hệ thống xử lý được bao nhiêu dữ liệu mỗi giây? |
| Latency | p50, p95, p99, max | Một record/request phải chờ bao lâu? |
| Backlog | Consumer lag, queue depth, pending records | Công việc đang tích tụ ở đâu? |
| Availability | Error rate, offline partition, timeout | Request có được phục vụ ổn định không? |
| Durability | ISR, acks, replication, transaction errors | Mức xác nhận dữ liệu có đáp ứng yêu cầu không? |
| Resource efficiency | CPU, memory, disk I/O, network | Tài nguyên nào đang bão hòa hoặc bị lãng phí? |
| Fairness | Per-partition throughput, skew | Một partition hoặc broker có đang gánh tải không đều? |

Một hệ thống có throughput cao nhưng p99 latency quá lớn vẫn có thể không đáp ứng SLO. Ngược lại, giảm latency bằng cách giảm acks hoặc replication có thể làm suy giảm durability. Trước khi tuning, phải xác định mục tiêu nghiệp vụ và giới hạn không được vi phạm.

## 2. Đường đi của một record và các điểm có thể nghẽn

Một luồng producer → broker → consumer có nhiều hàng đợi và bước xử lý:

~~~mermaid
flowchart LR
    A[Application] --> B[Producer accumulator]
    B --> C[Network request]
    C --> D[Broker request queue]
    D --> E[Broker processing]
    E --> F[Partition log / disk]
    F --> G[Replication to followers]
    E --> H[Produce response]
    G --> I[Consumer fetch]
    I --> J[Consumer application]
    J --> K[Database / downstream]
~~~

| Vị trí | Triệu chứng | Metric cần xem |
|---|---|---|
| Application/producer | Record chờ trước khi gửi | record-queue-time, bufferpool-wait-time, buffer-available-bytes |
| Producer network | Request chậm hoặc lỗi | request-latency, request-rate, retry-rate, error-rate |
| Broker queue | Request phải chờ trước khi xử lý | RequestQueueTimeMs, request queue size, network processor idle |
| Broker processing | Broker bận CPU hoặc xử lý lâu | LocalTimeMs, request handler idle, CPU |
| Disk/log | Append hoặc fetch chậm | Disk latency, IOPS, utilization, log flush metrics |
| Replication | Follower tụt lại | ISR, replication bytes, follower fetch latency |
| Consumer fetch | Không lấy đủ dữ liệu | fetch latency, fetch rate, bytes consumed |
| Consumer processing | Poll được record nhưng xử lý chậm | records-consumed-rate, processing duration, application queue |
| Downstream | DB/API chậm làm consumer bị nghẽn | DB pool wait, HTTP latency, retry/error rate |

Đừng mặc định consumer lag lớn là do consumer thiếu instance. Lag có thể do producer đột ngột tăng tải, broker fetch chậm, partition skew hoặc consumer downstream đang chờ database.

## 3. Lập baseline trước khi thay đổi

Baseline là bộ số liệu mô tả hệ thống khi workload và cấu hình ở trạng thái được xem là bình thường. Không có baseline thì khó biết metric hiện tại là bất thường hay chỉ là đặc tính của workload.

Ghi nhận tối thiểu:

- Kafka broker/client version và cấu hình quan trọng.
- Số broker, partition, replication factor và phân bố leader.
- Producer count, consumer count, consumer group và subscription.
- Record size trung bình, phân bố record size và key distribution.
- Produce/consume throughput theo records/s và bytes/s.
- p50/p95/p99 producer latency, consumer processing latency và end-to-end latency.
- Consumer lag theo partition và tuổi của record cũ nhất chưa xử lý.
- CPU, heap, GC, disk latency/throughput/free space và network throughput.
- ISR, under-replicated partitions, offline partitions và producer error rate.
- Thời điểm deploy, rebalance, reassignment, backup hoặc batch workload.

Đo trong một khoảng thời gian đủ đại diện cho peak, off-peak và chu kỳ batch. Ghi lại cùng timezone và đồng bộ clock giữa host để so sánh timeline.

### Baseline phải gắn với workload

Hai lần benchmark chỉ so sánh được nếu điều kiện tương đương:

- Cùng số broker và partition.
- Cùng replication factor, acks và compression.
- Cùng record size, key distribution và schema.
- Cùng số producer/consumer và concurrency.
- Cùng retention, transaction và security settings.
- Cùng loại storage/network và tải nền.

Nếu workload khác nhau, thay đổi latency có thể đến từ dữ liệu chứ không phải cấu hình.

## 4. Dùng p95/p99 thay vì chỉ nhìn average

Average có thể che giấu một nhóm request rất chậm. Ví dụ 99 request mất 5 ms và một request mất 500 ms có average khoảng 10 ms, nhưng người dùng gặp tail latency 500 ms.

| Percentile | Cách hiểu | Giá trị vận hành |
|---|---|---|
| p50 | Một nửa request nhanh hơn mức này | Độ trễ điển hình |
| p95 | 95% request nhanh hơn mức này | Tail latency phổ biến |
| p99 | 99% request nhanh hơn mức này | Tail latency nghiêm trọng hơn |
| max | Request chậm nhất trong cửa sổ | Dễ bị outlier chi phối |

Luôn xem latency cùng throughput và error rate. p99 tăng trong lúc throughput giảm có thể chỉ ra saturation; p99 tăng khi throughput cũng tăng có thể là queueing do tải. Nếu chỉ nhìn latency, không thể phân biệt hai tình huống.

Không cộng các percentile của từng giai đoạn để suy ra percentile end-to-end. p99 của producer request, broker queue và database query có thể đến từ các request khác nhau. Muốn biết p99 end-to-end, phải đo trực tiếp bằng trace hoặc timestamp cùng correlation/event ID.

## 5. Producer metrics: nghẽn ở client hay broker?

Producer có accumulator để gom record thành batch trước khi gửi. Khi broker chậm hoặc network bão hòa, buffer có thể đầy; send() bắt đầu chờ buffer và latency phía ứng dụng tăng.

Các metric producer thường cần quan sát:

| Metric | Ý nghĩa | Dấu hiệu bất thường |
|---|---|---|
| record-send-rate | Số record gửi mỗi giây | Giảm trong khi ứng dụng vẫn tạo record |
| byte-rate | Lưu lượng gửi | Không tăng tương ứng với record rate |
| request-rate | Số request gửi broker mỗi giây | Rất cao với batch nhỏ |
| request-latency-avg/max | Thời gian request tới broker và nhận response | Tăng cùng broker queue/local/remote time |
| record-queue-time-avg/max | Thời gian record nằm trong accumulator trước khi gửi | Tăng khi batching hoặc broker/network chậm |
| batch-size-avg | Kích thước batch trung bình | Quá nhỏ có thể làm tăng request overhead |
| compression-rate-avg | Hiệu quả nén | Thấp hoặc CPU nén quá cao |
| buffer-available-bytes | Buffer còn trống | Gần 0 kéo dài |
| bufferpool-wait-time | Thời gian chờ buffer memory | Tăng là dấu hiệu backpressure ở producer |
| record-retry-rate | Tốc độ retry record | Tăng có thể do timeout hoặc broker lỗi |
| record-error-rate | Tỷ lệ record lỗi | Tăng cho biết delivery không ổn định |
| produce-throttle-time-avg/max | Thời gian broker throttle producer | Tăng khi quota áp dụng |

Tên JMX/client metric và cách export phụ thuộc Kafka client version. Kiểm tra metric catalog của đúng phiên bản trước khi viết dashboard.

### Cách đọc tổ hợp metric producer

| Quan sát | Giả thuyết cần kiểm chứng |
|---|---|
| buffer-available-bytes thấp, bufferpool-wait-time tăng | Producer buffer không đủ hoặc broker/network không giải phóng batch đủ nhanh |
| record-queue-time tăng, request-latency ổn định | Batching/linger hoặc producer scheduling đang làm record chờ |
| request-latency tăng cùng broker RequestQueueTimeMs | Broker quá tải hoặc request queue tích tụ |
| batch-size nhỏ, request-rate cao | Record size nhỏ, linger thấp hoặc partition spread rộng |
| retry-rate tăng, error-rate tăng | Broker/network instability, timeout hoặc ISR issue |
| produce-throttle-time tăng | Quota đang giới hạn producer |

Không tăng buffer.memory chỉ vì buffer wait tăng. Nếu broker không thể xử lý nhanh hơn, buffer lớn chỉ giữ backlog trong heap lâu hơn và làm thời gian phục hồi dài hơn.

## 6. Broker request metrics: queue hay xử lý thực tế?

Kafka broker chia request thành các giai đoạn như queue, local processing, remote wait và response. JMX RequestMetrics cung cấp thời gian theo request type, ví dụ Produce, FetchConsumer và FetchFollower.

Các metric thường gặp:

| Metric | Ý nghĩa |
|---|---|
| RequestQueueTimeMs | Thời gian request chờ trong request queue |
| LocalTimeMs | Thời gian broker xử lý phần local |
| RemoteTimeMs | Thời gian chờ hoạt động remote cần thiết, ví dụ replication/remote response |
| ResponseQueueTimeMs | Thời gian response chờ trước khi gửi |
| ResponseSendTimeMs | Thời gian gửi response qua network |
| TotalTimeMs | Tổng thời gian request theo định nghĩa broker |

Metric được export theo request name và percentile, ví dụ Produce hoặc FetchConsumer. ObjectName và attribute cụ thể phụ thuộc release/exporter.

### Phân rã latency

~~~text
Request latency =
  queue time
  + local processing time
  + remote wait time
  + response queue time
  + response send time
~~~

Đây là cách nhìn phân rã các giai đoạn request; không nên cộng percentile độc lập để tính percentile tổng. Hãy xem histogram/percentile của từng stage để tìm thành phần thay đổi cùng thời điểm.

| Metric tăng | Nên kiểm tra |
|---|---|
| RequestQueueTimeMs | Request handler/thread capacity, CPU, queued requests |
| LocalTimeMs | CPU, disk append/read, lock contention, request type |
| RemoteTimeMs của Produce | Follower replication, ISR, network giữa broker |
| ResponseQueueTimeMs | Network processor/response queue pressure |
| ResponseSendTimeMs | Network bandwidth, client receive rate, socket backpressure |

## 7. Broker throughput và request rate

Các metric BrokerTopicMetrics giúp xác định broker đang nhận/gửi bao nhiêu dữ liệu:

| Metric thường dùng | Ý nghĩa |
|---|---|
| BytesInPerSec | Bytes được produce vào broker |
| BytesOutPerSec | Bytes được fetch từ broker |
| MessagesInPerSec | Số message/record đi vào |
| TotalProduceRequestsPerSec | Tốc độ produce request |
| TotalFetchRequestsPerSec | Tốc độ fetch request |
| FailedProduceRequestsPerSec | Produce request thất bại |
| FailedFetchRequestsPerSec | Fetch request thất bại |
| ReplicationBytesInPerSec | Dữ liệu replication broker nhận |
| ReplicationBytesOutPerSec | Dữ liệu replication broker gửi |
| BytesRejectedPerSec | Dữ liệu bị từ chối theo metric/broker semantics |

Đừng so sánh records/s mà bỏ qua bytes/s. 10.000 record 100 byte khác rất nhiều so với 10.000 record 1 MB. Compression cũng khiến bytes trên wire khác bytes trước nén.

Phân tích theo broker và topic nếu exporter hỗ trợ label. Cluster aggregate có thể che một broker nóng hoặc một topic có throughput vượt trội.

## 8. Request handler và network processor

Hai metric thường được xem cùng lúc:

- RequestHandlerAvgIdlePercent: tỷ lệ thời gian request handler thread nhàn rỗi.
- NetworkProcessorAvgIdlePercent: tỷ lệ thời gian network processor nhàn rỗi.

Giá trị thấp kéo dài cho thấy pool tương ứng đang bận. Tuy nhiên, không nên chỉ nhìn một gauge rồi tăng số thread.

| Dấu hiệu | Khả năng | Bước tiếp theo |
|---|---|---|
| Handler idle thấp, RequestQueueTime tăng | Request handler không theo kịp | Xem CPU, local time, số request và thread pool |
| Network processor idle thấp, response queue/send time tăng | Network processing hoặc socket bị nghẽn | Xem NIC, bandwidth, connection count, response size |
| Cả hai idle thấp | Broker tổng thể bị saturation | Xác định CPU/network/disk và request type |
| Idle cao nhưng latency cao | Có thể nghẽn disk/remote dependency hoặc client-side | Xem stage metrics, OS và client |

num.network.threads và num.io.threads là cấu hình broker có ảnh hưởng đến concurrency. Tăng chúng chỉ hợp lý khi đã chứng minh thread pool là giới hạn và broker còn CPU/memory để chạy thêm thread. Nhiều thread hơn không làm disk hoặc NIC nhanh hơn.

## 9. Disk và log I/O

Kafka ghi log tuần tự theo partition, nhưng hiệu năng disk còn phụ thuộc số partition, segment roll, page cache, replication fetch, compaction và retention deletion.

Metric OS/disk cần quan sát:

| Metric | Ý nghĩa |
|---|---|
| Disk read/write throughput | Dung lượng đọc/ghi mỗi giây |
| IOPS | Số thao tác I/O mỗi giây |
| await / average I/O latency | Thời gian chờ mỗi thao tác |
| utilization | Mức bận của thiết bị |
| queue depth | Số I/O đang chờ |
| free space | Dung lượng còn lại |
| filesystem errors | Lỗi mount/I/O |

Không kết luận disk bottleneck chỉ vì utilization 100%; một thiết bị NVMe có thể đạt throughput cao ở mức utilization đó. Hãy so sánh latency, queue depth, throughput và giới hạn thiết bị.

Các metric Kafka có thể bổ sung log flush rate/time, log directory errors và replica fetch throughput. Với cloud volume, xem cả provisioned IOPS/throughput cap và burst credit.

### Dấu hiệu disk bottleneck

- Produce LocalTimeMs tăng đồng thời disk write latency tăng.
- Fetch latency tăng cùng disk read latency, nhất là khi page cache miss.
- Broker CPU còn thấp nhưng request chờ I/O.
- Replica follower fetch lag tăng trên broker có disk chậm.
- Disk queue depth và await tăng trong peak.

Không bật flush mỗi message hoặc thay đổi log flush policy để chữa latency khi chưa hiểu durability và filesystem semantics. Kafka dựa nhiều vào OS page cache và replication; thay đổi fsync policy có thể làm giảm throughput đáng kể.

## 10. Network bottleneck và replication traffic

Kafka sử dụng network cho client produce/fetch, follower replication, controller traffic và inter-broker operations. Khi client traffic và replication tranh cùng NIC, throughput có thể giảm ở cả hai phía.

Theo dõi:

- Bytes/s và packets/s theo NIC.
- Network utilization so với line rate.
- Packet drops, retransmissions và TCP resets.
- RTT giữa broker và giữa broker/client.
- Connection count và connection creation rate.
- ReplicationBytesInPerSec/ReplicationBytesOutPerSec.
- ResponseSendTimeMs và network processor idle.

Nếu broker leader gửi replication traffic lớn tới nhiều follower, network egress có thể trở thành giới hạn. Nếu consumer ở xa cluster, BytesOutPerSec và cross-zone transfer có thể tăng chi phí và latency.

Không kết luận network chỉ từ throughput gần line rate; cần xem retransmission, RTT và request stage latency. Một network link có utilization thấp vẫn có thể có packet loss hoặc route bất ổn.

## 11. Replication và durability metrics

Hiệu năng producer acks=all phụ thuộc việc các replica trong ISR xác nhận theo protocol. Nếu follower chậm, produce latency có thể tăng hoặc producer nhận lỗi khi ISR thấp hơn min.insync.replicas.

Theo dõi cùng nhau:

- UnderReplicatedPartitions.
- UnderMinIsrPartitionCount nếu broker/version export metric này.
- IsrShrinksPerSec và IsrExpandsPerSec.
- ReplicationBytesInPerSec và ReplicationBytesOutPerSec.
- Follower fetch latency/rate.
- Producer NotEnoughReplicas và NotEnoughReplicasAfterAppend.
- Produce RemoteTimeMs.

Nếu URP tăng cùng remote wait time, follower replication có thể là một phần bottleneck. Nếu URP bằng 0 nhưng producer latency cao, vẫn cần xem broker local time, request queue, disk và network.

Không đổi acks=all sang acks=1 để làm dashboard latency đẹp hơn nếu yêu cầu durability chưa thay đổi. Cũng không giảm min.insync.replicas để né NotEnoughReplicas khi cluster đang mất replica.

## 12. Consumer metrics và lag

Consumer có thể chậm do fetch, deserialize, xử lý nghiệp vụ, commit hoặc downstream dependency. Cần phân biệt consumer lag với processing latency.

Client metrics thường gặp:

| Metric | Ý nghĩa |
|---|---|
| records-consumed-rate | Số record consumer đọc mỗi giây |
| bytes-consumed-rate | Bytes consumer đọc mỗi giây |
| fetch-rate | Số fetch request mỗi giây |
| fetch-latency-avg/max | Latency fetch request |
| records-lag / records-lag-max | Khoảng cách offset theo metric consumer |
| commit-latency-avg/max | Thời gian commit offset |
| assigned-partitions | Số partition được gán |
| heartbeat-rate / heartbeat-response-time-max | Sức khỏe giao tiếp group coordinator, nếu client expose |

Metric names/availability phụ thuộc consumer version và client instrumentation. Đừng giả định mọi exporter đều dùng cùng naming convention.

### Consumer lag không phải số record chính xác còn lại trong mọi trường hợp

Lag thường là khoảng cách offset giữa log end/committed progress theo cách metric định nghĩa. Compaction, transaction visibility, retention, read_committed và offset gaps có thể khiến offset delta khác số record thực sự còn đọc được.

Đọc consumer lag cùng:

- Records consumed per second.
- Processing time per record/batch.
- Commit latency và commit failure.
- Partition assignment và rebalance.
- Oldest pending event age hoặc event-time lag nếu ứng dụng đo.
- Downstream DB/API latency và error rate.

Nếu lag tăng nhưng consumer throughput cũng tăng, producer có thể đang tăng nhanh hơn. Nếu lag tăng trong khi records-consumed-rate giảm, consumer hoặc fetch path có thể đang nghẽn.

## 13. Partition skew và mức song song

Kafka phân phối record theo partition. Consumer group truyền thống không thể có nhiều consumer member cùng xử lý một partition trong một thời điểm theo assignment model thông thường; số consumer active bị giới hạn bởi số partition được assign.

Một partition nóng có thể tạo lag lớn dù các partition khác rảnh. Tổng consumer lag hoặc tổng throughput có thể che giấu skew.

Kiểm tra:

- BytesIn/BytesOut theo topic-partition.
- Records/s theo partition nếu có instrumentation.
- Consumer lag từng partition.
- Key frequency và partitioner behavior.
- Leader distribution giữa broker.
- Consumer assignment và processing time từng partition.

Nếu một key có tần suất rất cao, key-based partitioning sẽ gửi toàn bộ record đó về một partition. Tăng consumer count không giải quyết hot key. Có thể cần thiết kế key/sharding mới, nhưng phải cân nhắc ordering theo entity.

Tăng partition count có thể thay đổi key-to-partition mapping của record mới và ảnh hưởng ordering. Đây là thay đổi thiết kế dữ liệu, không chỉ là tuning hiệu năng.

## 14. JVM, GC và CPU

Broker và client đều chạy trên JVM. CPU thấp không có nghĩa ứng dụng không nghẽn; thread có thể chờ disk/network hoặc lock. CPU cao cũng không nhất thiết là lỗi nếu throughput tăng tương ứng.

Theo dõi:

- Process CPU và container CPU throttling.
- Heap used/committed và old generation occupancy.
- Allocation rate.
- GC pause p95/p99 và số lần full GC.
- Thread count, blocked/waiting threads.
- Direct buffer/native memory nếu có.
- File descriptors và socket count.

### Dấu hiệu GC gây latency

- p99 latency tăng trùng thời điểm stop-the-world pause.
- Network/handler idle giảm hoặc request queue tăng trong GC pause.
- Heap thường xuyên chạm ngưỡng cao.
- Full GC hoặc allocation rate tăng đột biến.

Không tăng heap ngay khi thấy GC. Heap lớn hơn có thể kéo dài full GC và giữ nhiều object lâu hơn. Trước tiên xác định object allocation, buffer, record size, batch và memory leak.

Container cần có memory limit đủ cho heap, direct memory, thread stacks, page cache và native allocations. Kafka broker phụ thuộc OS page cache; cấp toàn bộ RAM cho JVM heap có thể làm disk read performance xấu đi.

## 15. Phân loại bottleneck bằng triệu chứng

| Triệu chứng | Metrics đi kèm | Vùng nghi ngờ đầu tiên |
|---|---|---|
| Producer p99 tăng, buffer wait tăng | buffer available thấp, bufferpool wait cao | Producer backpressure hoặc broker/network chậm |
| Producer p99 tăng, broker request queue tăng | RequestQueueTimeMs cao | Broker request capacity |
| Produce remote time tăng, ISR shrink tăng | Replication lag, follower fetch chậm | Replication/network/disk follower |
| Broker CPU cao, handler idle thấp | LocalTimeMs cao, request rate cao | CPU/handler saturation |
| Broker CPU thấp, disk await cao | I/O queue cao, local time tăng | Storage |
| Broker network egress cao, response send time tăng | NIC gần giới hạn, retransmit | Network |
| Consumer lag tăng, consumed rate giảm | Fetch latency hoặc processing time tăng | Consumer fetch/app/downstream |
| Một partition lag cao, phần còn lại thấp | Per-partition throughput skew | Hot key/partition |
| Lag tăng nhưng consumer metrics bình thường | Producer throughput tăng | Ingress cao hơn capacity |
| Latency tăng cùng GC pause | Heap/GC metrics bất thường | JVM memory/GC |
| Throttle time tăng | Quota throttle metrics | Quota policy |

Đây là bảng định hướng, không phải kết luận tự động. Mỗi triệu chứng cần đối chiếu timeline và loại trừ nguyên nhân khác.

## 16. Dùng CLI để xác định phân bố tải

### Xem partition, leader và replica

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic orders.events
~~~

Lệnh này giúp xem partition count, leader, replicas và ISR. Nó không thay thế metrics throughput theo partition.

### Xem consumer lag theo partition

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --group payments-service
~~~

Đọc CURRENT-OFFSET, LOG-END-OFFSET và LAG cùng trạng thái consumer. Nếu group đang rebalance hoặc không có member active, số liệu có thể thay đổi giữa các lần chạy.

### Xem topic-level config

~~~bash
kafka-configs.sh \
  --bootstrap-server kafka-1:9092 \
  --entity-type topics \
  --entity-name orders.events \
  --describe \
  --all
~~~

Kiểm tra compression/retention/cleanup và min.insync.replicas override. Đừng chỉ xem broker defaults vì topic có thể có cấu hình riêng.

### Xem replica log directory

~~~bash
kafka-log-dirs.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --broker-list 1,2,3 \
  --topic-list orders.events
~~~

Lệnh này giúp xem replica log directory và kích thước log theo broker; không cung cấp đầy đủ latency/IOPS của thiết bị. Kết hợp OS/cloud storage metrics.

## 17. JMX và Prometheus: thu thập có chủ đích

Kafka broker và Java clients cung cấp JMX metrics. Có thể dùng JMX Exporter để expose metric cho Prometheus, hoặc dùng agent/telemetry integration phù hợp.

Các nhóm nên thu thập:

| Thành phần | Nhóm metric |
|---|---|
| Broker request | RequestMetrics theo Produce/Fetch request |
| Broker throughput | BrokerTopicMetrics |
| Replication | ReplicaManager, ISR, fetcher |
| Network | SocketServer, network processor, connection |
| JVM | Heap, GC, threads, process CPU |
| Producer | Buffer, batch, request latency, retry, throttle |
| Consumer | Fetch, records consumed, lag, commit |
| OS | CPU, disk, network, memory, file descriptors |

Không export mọi MBean và mọi tag một cách không kiểm soát. Metric cardinality có thể tăng rất nhanh nếu label theo client ID, topic, partition, request, broker và exception cùng lúc. Chỉ giữ dimension phục vụ chẩn đoán; dùng log/trace cho chi tiết từng request hoặc record.

### Một số JMX ObjectName thường dùng

Các ObjectName tiêu biểu trong broker:

~~~text
kafka.server:type=BrokerTopicMetrics,name=BytesInPerSec
kafka.server:type=BrokerTopicMetrics,name=BytesOutPerSec
kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions
kafka.server:type=ReplicaManager,name=IsrShrinksPerSec
kafka.server:type=KafkaRequestHandlerPool,name=RequestHandlerAvgIdlePercent
kafka.network:type=SocketServer,name=NetworkProcessorAvgIdlePercent
kafka.network:type=RequestMetrics,name=TotalTimeMs,request=Produce
kafka.network:type=RequestMetrics,name=RequestQueueTimeMs,request=Produce
~~~

Client metrics thường nằm dưới domain producer/consumer và được phân biệt theo client ID:

~~~text
kafka.producer:type=producer-metrics,client-id=orders-producer-1
kafka.consumer:type=consumer-fetch-manager-metrics,client-id=payments-consumer-1
~~~

ObjectName chính xác có thể thay đổi theo Kafka/client release, client ID và exporter. Dùng JConsole/JMX tooling hoặc endpoint của JMX Exporter để liệt kê MBean thực tế trước khi viết rule. Một số metric là rate/time-window sensors có nhiều attribute như Count, OneMinuteRate, MeanRate, 50thPercentile, 95thPercentile và 99thPercentile; cần chọn đúng attribute thay vì chỉ scrape một giá trị.

### Ví dụ PromQL minh họa

~~~promql
# Broker produce bytes/s
sum by (instance) (
  rate(kafka_server_brokertopicmetrics_bytesin_total[5m])
)

# Consumer lag lớn nhất theo group/topic
max by (group, topic) (
  kafka_consumer_group_lag
)

# Tỷ lệ ISR shrink
sum by (instance) (
  rate(kafka_server_replicamanager_isrshrinks_total[5m])
)
~~~

Tên metric trên phụ thuộc quy tắc đặt tên của JMX Exporter và cấu hình mapping. Đây là ví dụ logic truy vấn; hãy kiểm tra /metrics của exporter để dùng đúng tên và label thực tế. Không copy PromQL vào production mà chưa xác minh series tồn tại.

## 18. Benchmark để kiểm chứng giả thuyết

Benchmark giúp đo capacity và so sánh trước/sau, nhưng chỉ có giá trị khi workload đại diện.

Producer benchmark minh họa:

~~~bash
kafka-producer-perf-test.sh \
  --topic perf.orders \
  --num-records 1000000 \
  --record-size 1024 \
  --throughput -1 \
  --producer-props \
    bootstrap.servers=kafka-1:9092,kafka-2:9092 \
    acks=all \
    compression.type=lz4 \
    linger.ms=5 \
    batch.size=65536
~~~

Consumer benchmark minh họa:

~~~bash
kafka-consumer-perf-test.sh \
  --bootstrap-server kafka-1:9092 \
  --topic perf.orders \
  --messages 1000000 \
  --group perf-consumer
~~~

Các option có thể khác theo Kafka release/distribution; kiểm tra --help của đúng binary. Chạy trên topic benchmark riêng, không tạo tải thử tùy tiện lên topic production.

### Benchmark phải đo cả hai phía

- Producer throughput và p50/p95/p99 latency.
- Consumer throughput và lag.
- Broker CPU, disk, network và request metrics.
- ISR/replication health.
- Record size và compression ratio.
- Error/retry/throttle rate.

Benchmark producer riêng có thể đạt throughput cao nhưng consumer không theo kịp. Benchmark consumer riêng có thể đọc nhanh từ cache nhưng không đại diện cho peak production. Cần end-to-end test với producer và consumer cùng chạy.

## 19. Quy trình điều tra bottleneck có kiểm soát

~~~mermaid
flowchart TD
    A[Đặt SLO và ghi baseline] --> B[Phát hiện symptom]
    B --> C[Khoanh vùng producer / broker / disk / network / consumer]
    C --> D[Đối chiếu metric cùng timestamp]
    D --> E[Đưa ra một hypothesis]
    E --> F[Thiết kế test và chọn một thay đổi]
    F --> G[Đo trước/sau với workload tương đương]
    G --> H{SLO tốt hơn và guardrail giữ nguyên?}
    H -->|Có| I[Giữ thay đổi và ghi lại]
    H -->|Không| J[Rollback và cập nhật hypothesis]
    J --> C
~~~

Quy trình thực tế:

1. Mô tả symptom bằng con số: p99 tăng từ bao nhiêu lên bao nhiêu, lag tăng ở partition nào.
2. Xác định thời điểm bắt đầu và thay đổi triển khai gần đó.
3. Đối chiếu producer, broker, OS và consumer metrics trên cùng timeline.
4. Khoanh vùng stage có latency/queue tăng đầu tiên.
5. Viết một giả thuyết có thể bác bỏ, ví dụ follower disk latency làm Produce RemoteTimeMs tăng.
6. Chọn một thay đổi nhỏ nhất có thể kiểm chứng.
7. Chạy cùng workload và cửa sổ đo như baseline.
8. So sánh p50/p95/p99, throughput, errors, lag, resource và durability.
9. Giữ hoặc rollback; cập nhật runbook và baseline.

Không thay đồng thời batch size, linger, compression, thread count và partition count. Khi nhiều biến thay đổi cùng lúc, không biết biến nào tạo ra kết quả.

## 20. Tuning producer sau khi đã xác định bottleneck

| Cấu hình | Tác động | Khi nào xem xét |
|---|---|---|
| batch.size | Kích thước batch tối đa theo partition | Batch nhỏ, request rate cao và còn latency budget |
| linger.ms | Thời gian chờ thêm record để gom batch | Workload nhiều record nhỏ, cần tăng batch efficiency |
| compression.type | CPU/throughput/network trade-off | Network là bottleneck hoặc cần giảm bytes trên wire |
| buffer.memory | Bộ nhớ accumulator | Producer buffer thực sự quá nhỏ và broker có capacity |
| max.in.flight.requests.per.connection | Số request đồng thời | Cần tăng concurrency; phải giữ idempotence/order constraints |
| delivery.timeout.ms | Tổng thời gian giao record được phép | Điều chỉnh theo SLO và retry/timeout policy |
| acks | Durability/latency trade-off | Chỉ thay đổi theo yêu cầu durability, không dùng để che bottleneck |

Thay đổi batch/linger có thể tăng throughput nhưng tăng thời gian chờ record. Compression giảm network bytes nhưng tiêu thụ CPU. Tuning phải cân bằng p99, CPU, network và error rate.

Nếu dùng idempotence, tuân thủ các ràng buộc producer version về acks, retries và max in-flight requests. Không vô hiệu hóa idempotence chỉ để tăng throughput khi ứng dụng cần bảo vệ duplicate do retry.

## 21. Tuning consumer sau khi đã xác định bottleneck

| Cấu hình | Tác động | Khi nào xem xét |
|---|---|---|
| max.poll.records | Số record tối đa trả về mỗi poll | Cần điều chỉnh batch xử lý và thời gian poll |
| fetch.min.bytes | Ngưỡng dữ liệu tối thiểu consumer muốn nhận | Workload throughput cao, chấp nhận chờ thêm để gom dữ liệu |
| fetch.max.wait.ms | Thời gian broker chờ đạt fetch.min.bytes | Điều chỉnh latency/throughput của fetch |
| max.partition.fetch.bytes | Giới hạn dữ liệu fetch từ một partition | Record/batch lớn cần fetch đủ |
| fetch.max.bytes | Giới hạn dữ liệu cho một fetch response | Cần xử lý batch tổng lớn hơn |
| max.poll.interval.ms | Giới hạn khoảng cách giữa các poll | Xử lý batch lâu; phải đánh giá rebalance và heartbeat model |

Tăng max.poll.records có thể làm một poll batch quá lớn, kéo dài processing time và gây rebalance nếu vượt max.poll.interval.ms. Tăng fetch size có thể tăng memory pressure. Tuning consumer cần nhìn cả processing duration, downstream pool và commit latency.

Nếu application processing là bottleneck, thêm consumer không nhất thiết giúp khi số partition không đủ hoặc database connection pool đã bão hòa.

## 22. Tuning broker chỉ khi metric chứng minh giới hạn

Một số cấu hình broker có thể ảnh hưởng concurrency và buffering:

| Cấu hình | Ảnh hưởng | Điều kiện cân nhắc |
|---|---|---|
| num.network.threads | Network request processing concurrency | Network processor bão hòa và CPU còn dư |
| num.io.threads | Request handler concurrency | Request queue tăng do handler capacity |
| queued.max.requests | Request queue capacity | Phải hiểu backpressure và memory khi queue lớn |
| socket.send.buffer.bytes / socket.receive.buffer.bytes | Socket buffer | Network path/RTT cần điều chỉnh và OS limit phù hợp |
| num.replica.fetchers | Follower replication concurrency | Replication fetch throughput bị giới hạn và broker còn capacity |
| replica.lag.time.max.ms | Thời gian follower có thể không tiến triển trước khi out of ISR | Chỉ sau khi phân tích fetch/GC/network jitter |

Tăng queued.max.requests có thể làm queue dài hơn chứ không tăng service rate. Tăng thread có thể tăng context switching và heap/native memory. Thay đổi broker config cần rolling plan, rollback và theo dõi từng broker.

## 23. Partition count, replication và capacity planning

Partition count ảnh hưởng mức song song, leader distribution, file handles, metadata và chi phí recovery. Tăng partition có thể giúp consumer parallelism nhưng cũng tăng overhead và có thể làm key chuyển partition khi mapping thay đổi.

Replication factor làm tăng disk usage, replication network và follower I/O. Tăng RF có thể tăng durability nhưng không phải giải pháp throughput miễn phí.

Capacity planning nên tính:

- Ingress bytes/s và record size distribution.
- Egress bytes/s theo số consumer group.
- Replication traffic theo RF và leader/follower placement.
- Compression ratio và CPU cost.
- Retention bytes theo tốc độ ingest và thời gian lưu.
- Reassignment/recovery headroom.
- Peak multiplier và tăng trưởng dự kiến.

Ví dụ ước tính dung lượng thô:

~~~text
Raw retained bytes =
  average ingress bytes/second
  × retention seconds

Approximate replicated storage =
  raw retained bytes
  × replication factor
~~~

Ước tính trên chưa bao gồm segment/index overhead, compression, compaction, skew, temporary reassignment copies và free-space headroom. Không dùng phép tính thô này làm sizing cuối cùng.

## 24. Những thay đổi dễ làm tình hình tệ hơn

- Tăng buffer.memory khi broker đã bão hòa: backlog chỉ chuyển về producer heap.
- Tăng queued.max.requests khi broker không xử lý kịp: queue và latency tăng.
- Tăng num.io.threads khi disk đã bão hòa: nhiều thread tranh I/O hơn.
- Tăng partition count mà không xem key distribution: có thể tạo overhead hoặc làm ordering thay đổi.
- Tăng linger.ms khi SLO latency rất chặt: record chờ lâu hơn trước khi gửi.
- Bật compression nặng khi CPU đang là bottleneck: network giảm nhưng CPU tăng.
- Giảm acks hoặc min.insync.replicas để bỏ lỗi: durability suy giảm.
- Tăng max.poll.records khi xử lý từng record chậm: poll batch lâu và có nguy cơ rebalance.
- Tăng heap để chữa GC mà chưa phân tích allocation: pause có thể dài hơn và page cache giảm.
- Tắt metric để giảm overhead mà không đo: mất khả năng xác nhận hiệu quả và phát hiện regression.

## 25. Bài thực hành: tìm bottleneck bằng metrics

Tạo cluster lab ba broker, một topic benchmark và producer/consumer riêng:

1. Ghi baseline producer/consumer throughput, p95/p99, broker CPU, disk/network và consumer lag.
2. Giữ nguyên workload, giảm consumer processing rate có chủ đích; xác minh lag tăng và consumed rate giảm.
3. Tạo producer batch nhỏ bằng cách giảm batch.size/linger.ms; quan sát request rate và batch-size-avg.
4. Thử compression khác nhau; so sánh CPU, compression ratio, bytes/s và latency.
5. Tạo disk I/O contention trong lab; quan sát disk await và broker LocalTimeMs.
6. Tăng producer load đến khi bufferpool-wait-time tăng; xác định saturation point.
7. Dừng follower broker trong lab; quan sát ISR, remote time và producer error behavior.
8. Phân phối key lệch để tạo hot partition; xem per-partition lag và leader load.
9. Thay đúng một cấu hình dựa trên metric; chạy lại cùng workload.
10. So sánh p50/p95/p99, throughput, error rate, lag và durability guardrails.
11. Rollback cấu hình nếu SLO hoặc guardrail xấu đi.
12. Viết lại baseline, hypothesis, thay đổi và kết quả để lần sau có thể lặp lại.

Chỉ tạo contention, dừng broker hoặc tăng tải mạnh trong lab. Không chạy benchmark gây tải trên cluster production nếu chưa có kế hoạch và giới hạn tải.

## 26. Checklist trước khi tuning production

- Xác định SLO throughput, p95/p99 latency, error rate và durability.
- Lưu baseline với workload, version và config rõ ràng.
- Đo producer, broker, consumer và OS trên cùng timeline.
- Xem p50/p95/p99 cùng throughput và error rate.
- Phân biệt queue time, local processing, remote wait và response send.
- Xem lag từng partition, không chỉ tổng lag.
- Kiểm tra partition skew và key distribution.
- Kiểm tra ISR, under-min-ISR và producer replication errors.
- Kiểm tra disk latency, network retransmission, CPU, GC và memory.
- Viết một hypothesis có thể kiểm chứng.
- Thay một biến tại một thời điểm.
- Dùng workload benchmark tương đương trước/sau.
- Giữ guardrail durability, ordering và availability.
- Có rollback và người chịu trách nhiệm.
- Ghi lại kết quả vào baseline/runbook.

## 27. Những nhầm lẫn thường gặp

- **Consumer lag lớn nghĩa là cần thêm consumer:** có thể producer tăng tải, partition skew hoặc downstream chậm.
- **Average latency đủ để đánh giá:** p95/p99 mới cho thấy tail latency.
- **CPU thấp nghĩa là broker còn capacity:** broker có thể đang chờ disk, network hoặc lock.
- **Disk utilization cao chắc chắn là bottleneck:** cần xem latency, queue depth, throughput và device limit.
- **Tăng thread luôn tăng throughput:** thread có thể chỉ tranh CPU, disk và memory.
- **Tăng buffer giải quyết broker chậm:** buffer chỉ giữ thêm backlog ở client.
- **Batch lớn luôn tốt:** throughput có thể tăng nhưng latency và memory cũng tăng.
- **Compression luôn giảm latency:** nó giảm network bytes nhưng tiêu thụ CPU.
- **acks=1 là cách tối ưu an toàn:** durability khác acks=all và phụ thuộc yêu cầu nghiệp vụ.
- **Lag offset bằng số record đang chờ:** compaction, transaction và retention có thể tạo offset gaps.
- **Một benchmark producer chứng minh E2E capacity:** consumer/downstream có thể là bottleneck riêng.
- **Có thể thay nhiều config cùng lúc:** không xác định được nguyên nhân tạo cải thiện hoặc regression.

Hiệu năng Kafka cần được chẩn đoán theo đường đi của record và theo từng lớp tài nguyên. Producer metrics chỉ ra backpressure ở client; broker request metrics tách queue, local và remote time; OS metrics cho thấy disk/network/CPU; consumer metrics giải thích fetch, processing và lag. Khi có baseline, hypothesis và phép đo trước/sau, việc tuning mới có thể cải thiện throughput hoặc latency mà vẫn giữ durability, ordering và availability theo yêu cầu.
