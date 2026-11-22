# CPU, heap và network

Hiệu năng của một ứng dụng Spring Kafka không chỉ phụ thuộc vào số consumer hoặc số partition. Một consumer có thể đọc dữ liệu rất nhanh nhưng không xử lý kịp vì CPU bị bão hòa; có thể xử lý record ngắn nhưng thường xuyên dừng do garbage collection; hoặc có đủ CPU và heap nhưng network throughput, latency hay broker connectivity trở thành nút thắt.

**CPU, heap và network** là ba nhóm tài nguyên cần được quan sát cùng nhau khi thiết kế capacity cho producer, consumer và listener containers. Mỗi nhóm tác động lên những phần khác nhau của pipeline:

    Producer application
       |
       +--> serialize / compress / batch
       |          |
       |          +--> CPU
       |          +--> heap / buffer.memory
       |
       +--> network send --------------------+
                                              |
                                           Kafka brokers
                                              |
    Consumer application                      |
       |                                      |
       +<-- network fetch <-------------------+
       |
       +--> deserialize / listener / business logic
       |          |
       |          +--> CPU
       |          +--> heap / object allocation
       |          +--> GC pauses
       |
       +--> offset commit / downstream I/O

Khi một trong ba tài nguyên cạn, throughput có thể giảm, latency và consumer lag tăng, retry nhiều hơn hoặc pod bị OOMKilled. Tăng concurrency hay replicas mà không xác định bottleneck có thể chỉ làm hệ thống tốn tài nguyên hơn và đẩy áp lực sang broker hoặc downstream.

Bài học thuộc chương **Hiệu năng và capacity** của Spring Kafka Reliability Operations. Mục tiêu là hiểu dấu hiệu của CPU, heap và network bottleneck, biết cấu hình Kafka/Spring Kafka có ảnh hưởng đến chúng ra sao, tính capacity có cơ sở và chọn hành động vận hành an toàn.

## 1. Phân biệt throughput với resource utilization

Các khái niệm này liên quan nhưng không thể thay thế nhau:

| Chỉ số | Câu hỏi trả lời |
|---|---|
| Throughput | Hệ thống xử lý được bao nhiêu record/byte mỗi giây? |
| Latency | Một record hoặc request mất bao lâu? |
| CPU utilization | CPU đang bận bao nhiêu phần công suất được cấp? |
| Heap usage | JVM đang giữ bao nhiêu object trong heap? |
| Allocation rate | Ứng dụng tạo object nhanh đến mức nào? |
| GC pause | JVM dừng application thread bao lâu để thu gom rác? |
| Network throughput | Ứng dụng gửi/nhận bao nhiêu byte mỗi giây? |
| Network latency | Mất bao lâu để request/response đi qua mạng? |
| Consumer lag | Consumer group còn chậm bao nhiêu so với log end offset theo cách đo? |

Một service có CPU 25% không nhất thiết còn capacity gấp ba lần. Có thể một thread đơn lẻ đã dùng hết một core, trong khi các core khác nhàn rỗi. Một service heap còn 40% cũng không chắc an toàn nếu allocation rate rất cao và GC liên tục chạy.

Hãy đọc resource metrics cùng records/sec, bytes/sec, listener duration, error rate, commit progress và oldest record age. Capacity có ý nghĩa khi gắn với một mức tải và một SLO cụ thể.

## 2. CPU được dùng ở đâu trong Kafka pipeline?

CPU phía producer thường tiêu thụ cho:

- Serialization và validation payload.
- Compression của record batches.
- TLS encryption/decryption.
- Partition selection và hashing key.
- Batch construction, buffering và retry bookkeeping.
- Callback, logging, metrics và tracing.
- Business logic trước khi publish.

CPU phía consumer thường tiêu thụ cho:

- Fetch response processing và decompression.
- Deserialization, schema conversion và validation.
- Listener business logic.
- Mapping object, JSON parsing và allocation.
- TLS/network processing.
- Offset/transaction bookkeeping.
- Logging, tracing, metrics và error handling.

Nếu listener gọi database hoặc HTTP API và chờ I/O, consumer thread có thể không dùng CPU nhiều trong lúc chờ. Vì vậy CPU thấp không chứng minh consumer đang rảnh hoặc có throughput dư.

## 3. Một CPU core có thể là bottleneck dù pod CPU thấp

Giả sử pod được cấp 8 vCPU. Một consumer thread xử lý tuần tự và chiếm gần hết một core; các thread còn lại chủ yếu chờ I/O.

    Pod capacity: 8 vCPU
    Consumer thread A: 100% của 1 core
    Other cores: mostly idle

    Container CPU total: khoảng 12.5% của 8 vCPU

Dashboard có thể hiển thị CPU chỉ 12,5%, nhưng throughput của partition do thread A sở hữu đã chạm giới hạn xử lý tuần tự.

Cần quan sát:

- CPU theo thread hoặc thread dump/JFR.
- Consumer concurrency và số partition được assign.
- Processing duration theo listener.
- Hot partition/key distribution.
- CPU throttling trong container.
- CPU usage toàn pod và node.

Tăng pod CPU request/limit có thể không cải thiện một đoạn code đơn luồng. Cần tối ưu code, chia partition/workload hoặc tăng parallelism hợp lệ.

## 4. CPU request, CPU limit và throttling trong Kubernetes

Trong Kubernetes:

- **CPU request** giúp scheduler chọn node và là cơ sở cho một số cách tính CPU share.
- **CPU limit** giới hạn lượng CPU container có thể sử dụng theo cơ chế cgroup.
- Khi chạm limit, container có thể bị throttled dù node còn CPU.
- CPU throttling kéo dài có thể làm listener xử lý chậm, GC threads chạy chậm và monitor tasks trễ.

Ví dụ:

~~~yaml
resources:
  requests:
    cpu: "1"
    memory: "1Gi"
  limits:
    cpu: "2"
    memory: "2Gi"
~~~

Đây là ví dụ cấu hình, không phải khuyến nghị mặc định. Chọn request/limit từ load test và quan sát production.

Các metric quan trọng:

- Container CPU usage.
- CPU throttled periods.
- CPU throttled time.
- Node CPU pressure.
- JVM process CPU.
- Listener processing p95/p99.

Nếu pod CPU usage thấp nhưng throttling cao, cần xem giới hạn cgroup và cách metric được tính. Không kết luận thiếu CPU chỉ từ một con số utilization tổng hợp.

## 5. CPU throttling ảnh hưởng poll và consumer group

Khi consumer bị throttled, thread có thể chậm ở nhiều giai đoạn:

    CPU limit reached
          |
          v
    Consumer/listener thread được cấp ít CPU hơn
          |
          +--> deserialize chậm
          +--> listener xử lý chậm
          +--> callback/commit xử lý muộn
          +--> poll kế tiếp bị trễ
          |
          v
    Consumer lag tăng
          |
          v
    Có thể tiến sát max.poll.interval.ms

Nếu thời gian giữa các lần poll vượt `max.poll.interval.ms`, consumer group có thể thay đổi membership và rebalance theo protocol. Điều này làm partition chuyển member và record chưa commit có thể được giao lại.

Không tăng `max.poll.interval.ms` để che CPU starvation kéo dài. Hãy xác định CPU limit, processing time, max.poll.records và deadline của listener.

## 6. JVM heap gồm những gì?

Heap là vùng bộ nhớ JVM dùng để cấp phát phần lớn object Java. Trong Spring Kafka, heap có thể chứa:

- ConsumerRecord và payload đã deserialize.
- ProducerRecord và serialized buffers ở tầng ứng dụng.
- String, byte arrays, JSON trees và DTOs.
- Batch/list các record trả về từ poll.
- Object trong listener và downstream client.
- Retry/recovery metadata.
- Cache, application state và queue.
- Một phần object do Kafka client, Spring, Micrometer và tracing tạo.

Heap không phải toàn bộ memory của container. Process còn dùng:

- Metaspace cho class metadata.
- Thread stacks.
- Direct/off-heap buffers.
- Native libraries.
- TLS/native networking buffers.
- Code cache và JVM internal structures.
- Memory allocator overhead.

Vì vậy `-Xmx` bằng memory limit của container có thể khiến process OOMKilled dù heap chưa đạt max.

## 7. Heap, RSS và container memory khác nhau

| Bộ nhớ | Ý nghĩa |
|---|---|
| Java heap used | Object đang được sử dụng trong heap |
| Java heap committed | Heap JVM đã cam kết/được cấp cho sử dụng |
| Java heap max (`-Xmx`) | Giới hạn heap tối đa |
| Metaspace | Class metadata |
| Thread stack | Stack của mỗi thread |
| Direct memory | Buffer ngoài heap, ví dụ ByteBuffer |
| Native memory | JVM, TLS, libraries, allocator |
| RSS | Resident memory đang nằm trong RAM |
| Container memory usage | Memory container được tính theo cgroup |

Ví dụ:

    Container memory limit = 2 GiB
    Java heap max          = 1.2 GiB
    Metaspace + stacks     = 250 MiB
    Direct/native          = 300 MiB
    Other overhead         = 150 MiB

    Total potential ~= 1.9 GiB

Các con số chỉ minh họa. Khi thread count tăng, stack memory tăng; khi producer/consumer dùng nhiều direct buffers, off-heap usage có thể tăng. Đặt Xmx cần để lại headroom cho phần memory ngoài heap.

## 8. Chọn Xms và Xmx

Ví dụ JVM flags:

~~~text
-Xms512m
-Xmx1536m
-XX:MaxDirectMemorySize=256m
~~~

- `-Xms`: heap ban đầu.
- `-Xmx`: heap tối đa.
- `MaxDirectMemorySize`: giới hạn direct buffer memory trong phạm vi JVM quản lý theo cấu hình phù hợp.

Không dùng các giá trị này như công thức cho mọi pod. Cần xét container limit, thread count, metaspace, native memory, TLS, Kafka client buffers và GC.

Trong container-aware JVM hiện đại, JVM có thể tự nhận biết memory limit và chọn heap ergonomics dựa trên phần trăm memory. Tuy nhiên, nếu ứng dụng đặt `-Xmx` rõ ràng, giá trị đó có thể ghi đè lựa chọn tự động.

Kiểm tra flags thực tế lúc runtime, không chỉ đọc Dockerfile hoặc Helm values.

## 9. Heap tăng vì allocation rate cao

Một consumer xử lý JSON có thể tạo nhiều object tạm:

    byte[] Kafka payload
       |
       v
    JSON parser nodes
       |
       v
    DTO graph
       |
       v
    Validation / mapping objects
       |
       v
    Business result
       |
       v
    Temporary objects become garbage

Ngay cả khi mỗi record chỉ giữ ít dữ liệu lâu dài, allocation rate cao có thể làm GC chạy thường xuyên. Ví dụ 10.000 record/giây, mỗi record tạo 20 KB object tạm:

    Allocation rate = 10.000 * 20 KB
                    = 200 MB/s

Đây là phép tính minh họa. Object allocation thực tế có thể cao hơn hoặc thấp hơn do payload, parser và JVM optimization.

Cần quan sát allocation rate và GC pause, không chỉ heap used sau GC. Nếu heap sau GC ổn định nhưng allocation rate rất cao, ứng dụng có thể vẫn tốn CPU cho GC.

## 10. Heap leak khác với heap pressure

**Heap pressure:** heap sử dụng tăng trong lúc xử lý tải cao rồi giảm sau GC. Đây có thể là hành vi bình thường.

**Memory leak:** object không còn cần thiết vẫn được giữ tham chiếu, khiến live set sau GC tăng dần theo thời gian.

Dấu hiệu leak:

- Heap after GC tăng dần qua nhiều chu kỳ.
- Old generation occupancy không trở về baseline.
- OOM xảy ra ngay cả khi traffic không tăng tương ứng.
- Heap dump cho thấy collection/cache/queue giữ object lớn.
- Dominator tree có một số root giữ nhiều payload/record.

Các nguồn leak phổ biến:

- Cache không có eviction.
- Map giữ eventId/ConsumerRecord vô hạn.
- Listener giữ references trong static collection.
- CompletableFuture hoặc callback không được giải phóng.
- Queue async không giới hạn.
- Retry state hoặc tracing baggage bị giữ lâu.

Đừng tăng Xmx như giải pháp duy nhất nếu live set tăng liên tục. Heap lớn hơn chỉ kéo dài thời gian trước khi OOM.

## 11. Queue không giới hạn là rủi ro capacity

Một pattern nguy hiểm:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(8);

@KafkaListener(topics = "orders.created")
public void consume(OrderCreated event) {
    executor.submit(() -> orderService.process(event));
}
~~~

Thread pool cố định thường dùng queue không giới hạn theo factory mặc định của `newFixedThreadPool`. Nếu producer gửi nhanh hơn worker xử lý, queue giữ object event tăng mãi.

Hậu quả:

- Heap tăng liên tục.
- GC pressure tăng.
- Latency từ lúc poll đến khi xử lý tăng.
- Process có thể OOM.
- Listener có thể ack/commit record trước khi async task hoàn tất nếu container coi method return là success.

Dùng bounded queue, giới hạn in-flight, backpressure và acknowledgment đúng sau khi xử lý bền vững. Không giải quyết bằng cách tăng heap vô hạn.

## 12. max.poll.records ảnh hưởng heap như thế nào?

`max.poll.records` giới hạn số record tối đa mà một lần `poll()` trả về cho application. Giá trị lớn có thể làm consumer giữ nhiều ConsumerRecord/payload cùng lúc, đặc biệt khi listener xử lý tuần tự cả batch.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        max.poll.records: 200
~~~

Nếu record trung bình 100 KB, 200 record tương đương khoảng 20 MB payload thô, chưa tính object overhead, deserialized graph, batch collections và các buffer khác.

Không thể tính heap chỉ bằng payload bytes. JSON DTO có thể dùng nhiều object hơn kích thước byte đầu vào.

Giảm max.poll.records có thể hạ peak heap và thời gian xử lý mỗi poll, nhưng có thể tăng overhead poll và giảm throughput. Hãy load test với phân bố record size thực tế, bao gồm record lớn nhất hợp lệ.

## 13. fetch.max.bytes và max.partition.fetch.bytes

Kafka consumer có các cấu hình fetch giới hạn lượng dữ liệu broker trả về:

- `fetch.max.bytes`: giới hạn bytes tối đa cho một fetch response theo cấu hình client.
- `max.partition.fetch.bytes`: giới hạn bytes tối đa cho mỗi partition trong fetch.
- `fetch.min.bytes`: lượng dữ liệu tối thiểu broker cố gắng gom trước khi trả response.
- `fetch.max.wait.ms`: thời gian broker có thể chờ để đáp ứng fetch.min.bytes.

Các cấu hình này ảnh hưởng network, batching và memory buffers. Chúng không thay thế `max.poll.records`, vì một fetch có thể được buffer trước khi application nhận records qua poll.

Kafka có thể trả batch đầu tiên lớn hơn giới hạn fetch per-partition để bảo đảm consumer có thể tiến triển khi batch đầu tiên quá lớn. Vì vậy không coi các fetch byte limits là hard memory cap tuyệt đối.

Khi điều chỉnh, cân nhắc record batch size, partition count, concurrent fetches và heap headroom.

## 14. Producer buffer.memory và max.block.ms

Kafka producer giữ record trong buffer trước khi gửi tới broker. Các cấu hình liên quan:

- `buffer.memory`: tổng memory producer dành cho buffering record batches theo client config.
- `max.block.ms`: thời gian tối đa một số lời gọi như `send()` có thể block khi chờ metadata hoặc buffer allocation.
- `batch.size`: kích thước batch mục tiêu theo partition.
- `linger.ms`: thời gian producer chờ thêm record để gom batch.
- `compression.type`: thuật toán nén record batch.

Khi broker unavailable hoặc producer gửi nhanh hơn khả năng gửi đi, buffer có thể đầy. `send()` có thể block tới max.block.ms trong một số điều kiện rồi ném exception.

Ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        buffer.memory: 67108864
        batch.size: 32768
        linger.ms: 5
        max.block.ms: 10000
        compression.type: lz4
~~~

Các giá trị là ví dụ. Buffer.memory không phải toàn bộ memory của producer JVM; còn object payload, serialization buffers, compression buffers và native/direct allocations.

Nếu tăng buffer.memory, producer có thể chịu burst lâu hơn nhưng cũng tiêu thụ nhiều memory hơn trước khi backpressure xuất hiện. Cần đặt giới hạn và theo dõi buffer availability/wait time.

## 15. Compression là trade-off CPU và network

Compression giảm số bytes truyền/lưu trên Kafka nhưng cần CPU để nén và giải nén.

| Codec | Đặc điểm tổng quát | Khi cân nhắc |
|---|---|---|
| none | Không tốn CPU nén | Payload nhỏ hoặc CPU là bottleneck |
| gzip | Tỷ lệ nén thường tốt nhưng CPU tốn hơn | Network/storage quan trọng hơn CPU |
| snappy | Tốc độ nén/giải nén nhanh, tỷ lệ vừa phải | Workload throughput cao |
| lz4 | Thường ưu tiên tốc độ, overhead thấp | Cân bằng CPU và network |
| zstd | Tỷ lệ nén tốt, có mức compression level | Cần cân bằng theo CPU/bytes |

Kết quả phụ thuộc payload. JSON lặp field thường nén tốt hơn payload đã nén hoặc dữ liệu ngẫu nhiên.

Producer cấu hình codec bằng `compression.type`. Consumer thường tự giải nén batch dựa trên codec metadata; không cần cấu hình codec riêng để giải nén các record bình thường.

Benchmark bằng payload thật, đo CPU, network bytes/sec, broker disk throughput và end-to-end latency. Đừng chọn codec chỉ theo tỷ lệ nén trên một file mẫu.

## 16. TLS có chi phí CPU và latency

Nếu Kafka dùng TLS, client phải thực hiện encryption/decryption và handshake. Chi phí tăng tùy:

- TLS version và cipher suite.
- Kích thước record batches.
- Connection churn.
- CPU capability của node.
- Session resumption và connection reuse.
- Network RTT và packet size.

Restart loop có thể làm TLS handshakes tăng mạnh vì mỗi pod tạo lại connections liên tục. Đây là một lý do khác tránh restart theo từng broker disconnect.

Không tắt TLS để cải thiện throughput production nếu cluster yêu cầu mã hóa. Hãy đo CPU/network và cấu hình connection lifecycle hợp lý.

## 17. Network throughput: byte rate quan trọng hơn record rate

Hai topic đều có 10.000 records/giây nhưng network load có thể khác nhau rất lớn:

    Topic A: 10.000 * 1 KB  = 10 MB/s
    Topic B: 10.000 * 100 KB = 1.000 MB/s

Record rate không phản ánh đầy đủ network capacity. Cần đo:

- Producer bytes sent/sec.
- Consumer bytes received/sec.
- Broker bytes in/out.
- Network interface throughput.
- Retransmissions, packet drops và errors.
- RTT tới broker.
- Connection count và connection churn.
- TLS handshake rate.

Đơn vị phải được chuẩn hóa: bit/s khác byte/s; MB khác MiB. Khi tính capacity, thêm overhead protocol, headers, replication traffic và compression.

## 18. Broker replication làm network traffic lớn hơn producer input

Producer gửi record vào partition leader, sau đó Kafka replication chuyển dữ liệu tới followers theo replication factor và ISR policy.

Nếu producer input là 100 MB/s và replication factor là 3, tổng traffic nội bộ broker có thể lớn hơn đáng kể so với 100 MB/s; con số thực tế phụ thuộc topology, rack placement, batching, protocol và hướng traffic.

Đừng so producer egress với broker NIC throughput rồi kỳ vọng hai số bằng nhau. Broker còn replication, consumer fetch, inter-broker communication, controller/metadata và traffic từ các consumer groups khác.

Khi broker network saturated, tăng consumer concurrency có thể làm fetch traffic tăng mà không cải thiện throughput hữu ích.

## 19. Network latency và vị trí consumer

Consumer đặt xa cluster có thể chịu RTT cao hơn. Với synchronous operations như commitSync, latency mạng có thể trực tiếp tăng thời gian consumer thread chờ.

Với fetch, Kafka client thường giữ các request outstanding và poll behavior có thể overlap một số hoạt động; tuy nhiên RTT, packet loss và bandwidth vẫn ảnh hưởng throughput.

Hãy cân nhắc:

- Đặt consumer gần Kafka cluster theo network topology.
- Dùng route ổn định và DNS phù hợp.
- Tránh cross-region traffic không cần thiết.
- Đo RTT theo broker, không chỉ ping một VIP.
- Kiểm tra TLS handshake và connection reuse.
- Đánh giá data transfer cost giữa regions.

Không kết luận network tốt chỉ vì ping thấp. Kafka traffic còn chịu TLS, broker request queue, packet retransmission và server processing.

## 20. Bandwidth-delay product và số request outstanding

Trên đường mạng có RTT cao, muốn đạt throughput lớn cần có đủ dữ liệu/request đang bay để lấp đầy bandwidth-delay product.

    Bandwidth-delay product = Bandwidth * RTT

Ví dụ đường mạng 1 Gbit/s và RTT 40 ms:

    1 Gbit/s * 0.04 s = 40 Mbit
    ~= 5 MB dữ liệu đang bay

Nếu client/broker chỉ cho phép rất ít dữ liệu outstanding, throughput có thể thấp hơn năng lực link. Kafka fetch/request batching và socket buffers có vai trò, nhưng không nên tự tăng mọi buffer một cách tùy tiện.

Đo bytes/sec và RTT trước. Nếu link không saturated, tăng socket buffer chưa chắc giúp. Nếu request queue/broker processing mới là bottleneck, bandwidth-delay product không phải nguyên nhân.

## 21. Số connection và broker fan-out

Một consumer group có nhiều consumers, mỗi consumer có thể duy trì kết nối tới nhiều broker/leader/coordinator theo nhu cầu. Khi replicas và concurrency tăng, số client connections có thể tăng.

Ví dụ:

    30 pods * concurrency 4 = 120 consumers

Mỗi consumer có thể tương tác với broker phục vụ các partition và coordinator. Không thể lấy 120 làm số TCP connections chính xác vì Kafka client quản lý connection theo node/client; nhưng nó cho thấy số member/client tăng có thể tạo thêm connection và request load.

Khi scale:

- Kiểm tra connection count trên broker.
- Theo dõi request rate và network throughput.
- Tránh rollout toàn bộ pod cùng lúc.
- Dùng jitter/backoff khi reconnect.
- Giới hạn replicas theo partition và downstream capacity.
- Kiểm tra file descriptors và ephemeral ports trên host.

Nhiều connection không tự tạo throughput nếu partition count và dependency không tăng tương ứng.

## 22. Concurrency tác động cả CPU, heap và network

Spring Kafka `concurrency` tạo child consumers trong một concurrent listener container:

~~~java
factory.setConcurrency(4);
~~~

Tăng concurrency có thể:

- Tăng số listener threads chạy business logic song song.
- Tăng số fetch requests và buffer hoạt động.
- Tăng object allocation và heap pressure.
- Tăng network connections/request activity.
- Tăng CPU cho deserialize/processing.
- Tăng group membership và rebalance overhead.

Tuy nhiên, số consumer có assignment trong một group bị giới hạn bởi số partition phù hợp. Nếu concurrency vượt partition capacity, consumer dư không tạo thêm parallel processing hữu ích.

Tăng concurrency cần được kiểm chứng bằng throughput tăng và SLO vẫn đạt, không chỉ vì CPU utilization còn thấp.

## 23. Partition skew tạo bottleneck không đều

Một topic có 24 partition không đảm bảo mỗi partition có tải bằng nhau. Nếu key distribution lệch, một partition có thể nhận 60% traffic.

    P0: 60% records
    P1-P23: chia 40% còn lại

Consumer sở hữu P0 có thể CPU cao và lag lớn, trong khi những consumer khác nhàn rỗi.

Kiểm tra:

- Records/bytes in per partition.
- Consumer lag per partition.
- Processing duration per partition nếu có.
- Key distribution và partitioner.
- Hot business key.
- Số consumer đang được assign.

Tăng replicas không giải quyết hot partition nếu key ordering yêu cầu mọi record của key đó vào cùng partition. Có thể cần thay đổi partition key hoặc business design, nhưng phải giữ semantics ordering.

## 24. Batch size và linger ảnh hưởng throughput

Producer `batch.size` và `linger.ms` phối hợp để gom record theo partition trước khi gửi.

- Batch lớn có thể tăng hiệu quả network/compression.
- Linger cao hơn tạo thêm cơ hội gom batch nhưng tăng send latency.
- Nhiều partition phân tán traffic khiến mỗi partition batch khó đầy.
- Batch quá lớn tăng memory và có thể làm burst network.
- Batch quá nhỏ tăng request overhead.

Ví dụ:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 65536
        linger.ms: 10
        compression.type: lz4
~~~

Đây là điểm bắt đầu để benchmark, không phải giá trị chuẩn. `batch.size` là mục tiêu batch theo partition; producer có thể gửi batch nhỏ hơn khi hết linger hoặc buffer pressure.

Đo records/batch, bytes/batch, request rate, CPU compression và end-to-end latency.

## 25. Consumer fetch batching và heap headroom

Consumer fetch có thể gom nhiều bytes từ nhiều partition trong một response. Cấu hình fetch ảnh hưởng cả network efficiency lẫn lượng data có thể buffer.

Ví dụ:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        fetch.min.bytes: 65536
        fetch.max.wait.ms: 100
        fetch.max.bytes: 52428800
        max.partition.fetch.bytes: 1048576
        max.poll.records: 200
~~~

Cần hiểu:

- `fetch.min.bytes` có thể giúp broker gom dữ liệu trước khi trả fetch, đổi lại latency.
- `fetch.max.wait.ms` giới hạn thời gian chờ để đạt fetch.min.bytes.
- `fetch.max.bytes` giới hạn tổng fetch response theo client configuration, có ngoại lệ để đảm bảo tiến triển với batch đầu tiên.
- `max.partition.fetch.bytes` áp dụng giới hạn per partition với ngoại lệ batch đầu tiên.
- `max.poll.records` giới hạn số record trả về cho application, không phải tổng bytes.

Chọn fetch size theo record size distribution, partition count và heap. Đặt fetch lớn mà Xmx nhỏ có thể làm heap pressure; đặt fetch quá nhỏ có thể tăng request overhead.

## 26. Record size và payload design

Record lớn ảnh hưởng đồng thời:

- Heap do byte arrays và DTO graph.
- CPU do serialization/deserialization/compression.
- Network bandwidth và request latency.
- Broker memory/disk và replication.
- GC do allocation lớn.
- Max request/record size constraints.

Nếu một event chứa file/image hoặc hàng trăm KB dữ liệu lặp, cân nhắc lưu payload lớn ở object storage/database và chỉ gửi reference cùng metadata cần thiết qua Kafka.

Khi thay đổi schema/payload:

1. Đo p50/p95/p99 record size.
2. Kiểm tra max message/request size ở producer, broker và consumer.
3. Đo bytes/sec và compression ratio.
4. Đo heap allocation per record.
5. Đánh giá compatibility và retention.
6. Không log toàn bộ payload lớn trong listener.

Một giới hạn record size nên dựa trên contract và capacity, không chỉ dựa vào giá trị mặc định.

## 27. Direct memory và Kafka network buffers

Kafka Java client và networking stack có thể dùng ByteBuffer/direct memory. Direct buffers nằm ngoài Java heap nên heap graph có thể trông bình thường trong khi container memory tăng.

Theo dõi:

- Direct buffer pool count/used/capacity qua JVM BufferPoolMXBean.
- `MaxDirectMemorySize` nếu được đặt.
- Native memory tracking khi bật.
- Container RSS và memory working set.
- Số connection và socket buffers.

Không tăng direct memory vô hạn để chữa `OutOfMemoryError: Direct buffer memory`. Cần xem ai đang giữ buffer, allocation rate, client count và lifecycle của consumer/producer.

Direct memory và kernel socket buffers là hai vùng khác nhau; đừng cộng hoặc so sánh chúng mà không hiểu metric source.

## 28. Thread count và stack memory

Tăng Spring Kafka concurrency cũng tăng consumer threads. Ngoài ra ứng dụng có web threads, scheduler, producer callbacks, database pool, async executor và tracing/exporter workers.

Mỗi Java thread có stack memory native. Nếu thread count tăng quá cao, process có thể tiêu thụ nhiều memory ngoài heap và gặp lỗi tạo thread.

Kiểm tra:

- JVM thread count.
- Thread states.
- `-Xss` và stack memory budget.
- Executor queue depth.
- Database connection pool size.
- Kafka concurrency toàn group.
- Thread churn do tạo executor liên tục.

Không đặt consumer concurrency bằng số vCPU một cách máy móc. Workload I/O-bound có thể cần nhiều thread hơn CPU, nhưng vẫn phải giới hạn heap, connections và downstream capacity.

## 29. GC pause và throughput

Garbage collector ảnh hưởng latency và CPU. Khi heap pressure cao, GC có thể chạy thường xuyên hoặc pause lâu.

Dấu hiệu:

- GC pause p95/p99 tăng.
- Allocation rate cao.
- Old generation occupancy tăng.
- Throughput giảm theo từng đợt GC.
- Listener duration có spikes cùng thời điểm GC.
- Container memory cao dù heap used sau GC không quá lớn.

Dùng GC logs và JVM metrics để phân tích. Với Java hiện đại, G1 thường là lựa chọn mặc định phổ biến; không đổi collector chỉ dựa vào một lần pause cao.

Cần tối ưu allocation trước khi tinh chỉnh collector:

- Tránh parse cùng payload nhiều lần.
- Tránh tạo object trung gian không cần thiết.
- Giới hạn batch/queue.
- Không giữ ConsumerRecord/payload lâu hơn cần thiết.
- Dùng serializer/deserializer hiệu quả.
- Kiểm tra cache và collection retention.

GC tuning không thể bù cho queue không giới hạn hoặc memory leak.

## 30. Tối ưu deserialization và serialization

Serialization/deserialization có thể là CPU hotspot, đặc biệt khi payload JSON lớn hoặc schema conversion phức tạp.

Các lựa chọn:

- Jackson JSON với cấu hình phù hợp.
- Avro/Protobuf/Schema Registry nếu hợp đồng schema và hệ sinh thái phù hợp.
- Tránh serialize cùng object nhiều lần.
- Giới hạn custom validation tốn CPU trong consumer hot path.
- Dùng schema evolution rõ ràng.
- Đo allocation và CPU bằng JFR/profiler.

Không chọn binary format chỉ vì kỳ vọng nó luôn nhanh hơn JSON. Payload, schema, library, compression và business logic quyết định kết quả.

Đảm bảo deserializer xử lý lỗi schema rõ ràng; retry vô hạn một poison record sẽ tiêu tốn CPU mà không làm record hợp lệ hơn.

## 31. Logging, tracing và metrics cũng dùng CPU/heap/network

Observability có chi phí:

- Structured log tạo object/string và ghi I/O.
- Trace span tạo metadata, sampling state và exporter queue.
- Metrics cập nhật counters/timers và giữ time series.
- Exporter gửi telemetry qua network.
- High-cardinality labels tăng memory và backend cost.

Ở throughput cao, log một dòng cho mọi record có thể trở thành bottleneck. Tracing sample 100% có thể tạo lượng spans lớn. Metrics label bằng eventId/offset có thể tạo cardinality bùng nổ.

Khuyến nghị:

- Log INFO cho lifecycle/sự kiện quan trọng, DEBUG cho per-record khi điều tra có giới hạn.
- Dùng metrics cardinality thấp.
- Dùng sampling policy phù hợp.
- Giới hạn exporter queue và batch.
- Theo dõi dropped telemetry và exporter failures.
- Không để exporter outage làm listener business path block vô hạn.

Observability phải đủ để chẩn đoán nhưng không được chiếm phần lớn capacity của pipeline.

## 32. Tính capacity theo CPU

Một ước lượng đơn giản cho CPU cost:

    CPU cores required
      ~= records_per_second * CPU_seconds_per_record

Ví dụ đo benchmark cho thấy mỗi record dùng trung bình 2 ms CPU:

    Input rate = 5.000 records/s
    CPU per record = 0.002 CPU-seconds

    CPU demand = 5.000 * 0.002
               = 10 CPU cores

Đây là CPU time thực sự, không phải elapsed processing duration. Nếu listener chờ database 50 ms nhưng chỉ dùng 2 ms CPU, không được lấy 50 ms nhân records/sec để tính CPU cores.

Cần headroom cho:

- GC và JVM runtime.
- Poll/fetch/commit.
- TLS và compression.
- Logging/metrics/tracing.
- Traffic bursts.
- Node contention và CPU throttling.

Nếu workload có p99 CPU cost cao hoặc record size biến động, sizing theo average đơn thuần sẽ thiếu an toàn.

## 33. Tính capacity theo network

Một ước lượng:

    Network bytes/s
      ~= records/s * average serialized bytes/record

Ví dụ:

    8.000 records/s * 12 KB
      = 96.000 KB/s
      ~= 96 MB/s (decimal)

Sau đó điều chỉnh theo compression ratio, protocol overhead, replication, consumer groups và hướng traffic.

Cần phân biệt:

- Producer client egress.
- Broker ingress.
- Inter-broker replication.
- Broker egress tới consumers.
- Consumer client ingress.
- Telemetry/network traffic khác.

Nếu một topic có ba consumer groups, broker có thể phải phục vụ dữ liệu cho cả ba group. Network egress không chỉ bằng producer ingress.

## 34. Tính capacity theo heap

Heap sizing khó hơn CPU/network vì phụ thuộc số object sống đồng thời.

Một mô hình gần đúng:

    Live heap
      ~= in-flight records * average retained object size
         + application cache
         + framework/client objects
         + queue contents

Ví dụ:

    4 consumer threads
    max.poll.records = 200 per consumer
    in-flight record count upper estimate = 800
    retained object graph = 80 KB/record

    Record objects ~= 64 MB

Đây chỉ là phần record graph ước lượng, chưa tính deserialization transient allocations, producer buffers, caches, thread stacks, native memory và các object khác. Listener có thể giữ thêm references khiến live set lớn hơn.

Để sizing:

1. Đo object graph size bằng profiler/heap analysis.
2. Đo peak records in-flight.
3. Đo allocation rate và GC.
4. Kiểm tra queue/cache retention.
5. Để headroom cho bursts và native memory.
6. Test với payload p99/max hợp lệ.

Không lấy `max.poll.records * average payload bytes` rồi coi đó là Xmx cần thiết.

## 35. Cân bằng CPU, heap và network

Tối ưu một tài nguyên có thể làm tăng áp lực lên tài nguyên khác:

| Thay đổi | Lợi ích có thể có | Chi phí/rủi ro |
|---|---|---|
| Compression mạnh hơn | Giảm network bytes | Tăng CPU |
| Batch lớn hơn | Giảm request overhead | Tăng heap và latency |
| Concurrency cao hơn | Tăng parallelism | Tăng threads, heap, connections |
| max.poll.records cao hơn | Giảm poll overhead | Tăng in-flight memory và poll work |
| Producer buffer lớn hơn | Chịu burst lâu hơn | Tăng memory trước backpressure |
| Tracing sample cao hơn | Nhiều dữ liệu chẩn đoán | Tăng CPU/heap/network/storage |
| Tăng replicas | Tăng consumer capacity khi còn partition | Tăng broker connections và downstream load |
| Tăng Xmx | Thêm heap headroom | Có thể tăng GC working set và chạm container limit |

Mỗi thay đổi nên có giả thuyết rõ: bottleneck nào được giảm, tài nguyên nào có thể tăng và metric nào xác nhận kết quả.

## 36. Ví dụ capacity cho consumer group

Giả sử:

- Topic có 24 partitions.
- 6 pod.
- Mỗi pod concurrency=4, tổng 24 consumers.
- Mỗi consumer xử lý trung bình 250 records/s.
- CPU cost là 1,5 ms/record.
- Payload trung bình sau deserialize giữ 40 KB trong thời gian xử lý.

Năng lực lý thuyết:

    Max record rate = 24 * 250
                    = 6.000 records/s

CPU demand:

    6.000 * 0.0015 CPU-seconds
      = 9 CPU cores

In-flight record estimate nếu mỗi consumer xử lý một poll 100 records:

    24 * 100 * 40 KB
      = 96 MB record graph estimate

Các số này chưa tính skew, GC, batch/queue overhead, broker capacity, network, retry và downstream. Nếu partition skew làm một consumer xử lý chậm, group throughput có thể thấp hơn 6.000 records/s.

Đây là capacity model để định hướng load test, không phải lời hứa throughput production.

## 37. Backpressure khi CPU hoặc heap gần cạn

Khi listener xử lý nhanh hơn khả năng downstream hoặc JVM sắp cạn memory, không nên tiếp tục poll và đưa thêm việc vào queue không giới hạn.

Các cơ chế:

- Giới hạn `max.poll.records`.
- Bounded async executor queue.
- Giới hạn in-flight requests.
- Rate limiter ở điểm gọi downstream.
- Spring Kafka container pause/resume theo ngưỡng.
- Giảm concurrency nếu resource pressure cao.
- Giảm producer input ở upstream nếu có khả năng.

Pause container cần được dùng qua API Spring Kafka và vẫn hiểu semantics poll/heartbeat. Không pause bằng cách block tùy tiện consumer thread.

Khi resume, giữ giới hạn downstream và theo dõi backlog drain; đừng để toàn bộ consumer cùng xả burst ngay lập tức.

## 38. Phân biệt CPU bottleneck với I/O wait

Dấu hiệu CPU bottleneck:

- CPU usage/throttling cao.
- Thread chạy runnable liên tục.
- Processing time tăng cùng CPU.
- Profile cho thấy serializer, compression, JSON parse hoặc business computation nóng.

Dấu hiệu I/O bottleneck:

- CPU thấp nhưng thread ở WAITING/TIMED_WAITING hoặc socket read.
- Database/HTTP latency cao.
- Connection pool cạn.
- Network RTT/packet loss tăng.
- Listener duration cao nhưng CPU time thấp.

Một listener có elapsed duration 500 ms không đồng nghĩa dùng 500 ms CPU. Hãy dùng JFR/profiler hoặc thread diagnostics để tách CPU time và wait time.

Nếu I/O là bottleneck, tăng CPU request có thể không cải thiện throughput; cần tối ưu timeout, connection pool, downstream capacity hoặc async design có bounded concurrency.

## 39. Dùng Java Flight Recorder để điều tra CPU và allocation

Java Flight Recorder (JFR) có thể giúp xem:

- Hot methods và CPU samples.
- Allocation samples.
- GC pauses.
- Thread park/block events.
- Socket I/O và file I/O.
- Lock contention.
- Thread lifecycle.

Có thể bật recording theo cơ chế JVM phù hợp với môi trường:

~~~bash
jcmd <pid> JFR.start name=kafka-capacity settings=profile duration=120s filename=/tmp/kafka-capacity.jfr
~~~

Lệnh là ví dụ cho môi trường có `jcmd` và quyền attach phù hợp. Trong container production cần bảo đảm file path có dung lượng, quyền truy cập và retention phù hợp. Không chạy profiler nặng liên tục nếu chưa đánh giá overhead.

JFR giúp xác định CPU/GC/thread bottleneck; nó không thay thế broker metrics, consumer lag và network diagnostics.

## 40. Heap dump và Native Memory Tracking

Khi nghi ngờ heap leak, có thể thu heap dump trong môi trường được kiểm soát:

~~~bash
jcmd <pid> GC.heap_dump /tmp/kafka-heap.hprof
~~~

Heap dump có thể chứa payload, event data và thông tin nhạy cảm trong memory. Bảo vệ file, hạn chế truy cập và xóa theo retention policy.

Native Memory Tracking (NMT) có thể giúp điều tra memory ngoài heap nếu JVM được khởi động với tùy chọn phù hợp:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Sau đó dùng `jcmd <pid> VM.native_memory summary` nếu JVM hỗ trợ. NMT có overhead và không phản ánh mọi allocation native bên ngoài JVM.

Không thu heap dump mỗi khi memory tăng nhẹ. Trước tiên quan sát GC, heap after GC, RSS, direct buffers và container memory.

## 41. Network diagnostics

Khi nghi network bottleneck, cần phân biệt:

- DNS resolution failure.
- TCP connection refused/reset.
- TLS handshake failure.
- Packet loss/retransmission.
- RTT tăng.
- Bandwidth saturation.
- Broker request processing chậm.
- Network policy/firewall chặn endpoint.

Một số công cụ môi trường có thể dùng gồm `ss`, `netstat`, `tcpdump`, `curl` cho endpoint phù hợp, hoặc network telemetry của Kubernetes/cloud. Công cụ cụ thể phụ thuộc image/container và quyền vận hành.

Ping thành công không chứng minh Kafka port/TLS/advertised listener hoạt động. Kiểm tra đúng hostname và port broker client nhận từ metadata.

Không dump packet production có payload nhạy cảm nếu không có quyền và chính sách phù hợp.

## 42. Kafka client metrics cần xem

Kafka producer/consumer cung cấp nhiều client metrics. Tên và group có thể thay đổi theo version; xác nhận metric thực tế trong runtime.

Một số nhóm metric hữu ích:

| Nhóm | Ví dụ metric | Mục đích |
|---|---|---|
| Producer throughput | `outgoing-byte-rate`, `record-send-rate` | Tốc độ gửi |
| Producer batch | `batch-size-avg`, `records-per-request-avg` | Hiệu quả batching |
| Producer buffer | `buffer-available-bytes`, `bufferpool-wait-time` | Áp lực buffer |
| Producer request | `request-latency-avg/max` | Độ trễ broker response |
| Consumer throughput | `bytes-consumed-rate`, `records-consumed-rate` | Tốc độ đọc |
| Consumer fetch | `fetch-latency-avg/max`, `fetch-rate` | Hiệu năng fetch |
| Consumer lag | `records-lag-max` | Lag theo client/partition metric |
| Coordinator | `commit-latency-avg/max`, `commit-rate` | Offset commit |
| Connection | connection count/creation metrics nếu client version hỗ trợ | Connection churn |

Kafka client metric names thường được hiển thị qua JMX/Micrometer binder và exporter có thể đổi dấu gạch hoặc unit. Không copy alert query từ version khác mà chưa xác nhận.

## 43. JVM và container metrics

Theo dõi tối thiểu:

- Heap used/committed/max.
- Old generation occupancy.
- Allocation rate.
- GC pause count/time.
- Thread count và deadlock detection.
- Direct buffer pool usage.
- Process RSS.
- Container memory working set/limit.
- CPU usage và throttling.
- Restart/OOMKilled count.

Nếu heap ổn định nhưng RSS tăng, xem direct/native memory, thread stacks và allocator. Nếu RSS ổn định nhưng heap after GC tăng, xem retained objects/leak.

Cần dùng cùng timestamp để đối chiếu resource spikes với Kafka lag và processing latency. Nếu không, có thể gán nhầm nguyên nhân do metric scrape interval khác nhau.

## 44. Dashboard capacity nên có những lớp nào?

Một dashboard cho Spring Kafka worker nên có:

**Workload**

- Input records/sec và bytes/sec.
- Processed records/sec.
- Consumer lag và oldest record age.
- Partition distribution/hot partition.
- Retry/DLT rate.

**Application performance**

- Listener duration p50/p95/p99.
- Serialization/deserialization duration nếu có.
- Database/HTTP latency.
- In-flight request count.
- Executor queue depth.

**JVM/resources**

- CPU usage/throttling.
- Heap used/after GC.
- Allocation rate.
- GC pause p95/p99.
- Direct memory/RSS.
- Thread count.

**Kafka/network**

- Producer send/fetch rate.
- Request latency/errors.
- Buffer pool wait.
- Bytes in/out.
- Reconnect/disconnect count.
- Commit latency/failures.
- Rebalance count.

Một dashboard tốt giúp trả lời: input có tăng không, consumer có theo kịp không, resource nào chạm giới hạn, và bottleneck nằm ở application hay broker/downstream.

## 45. Đặt alert theo triệu chứng và SLO

Không nên paging chỉ vì CPU vượt 80% trong một phút. CPU cao có thể là workload bình thường nếu throughput tăng tương ứng và latency vẫn đạt SLO.

Alert hữu ích kết hợp:

- CPU/throttling cao **và** listener latency tăng.
- Heap after GC tăng liên tục **và** container memory gần limit.
- GC pause tăng **và** poll cadence/lag xấu đi.
- Producer buffer wait tăng **và** send errors/latency tăng.
- Network throughput sát link capacity **và** request latency tăng.
- Consumer lag/oldest age vượt SLO dù resource còn headroom.

Dùng warning/critical với thời gian duy trì, baseline và scope. Alert một pod riêng có thể khác alert toàn consumer group.

## 46. Tuning theo thứ tự có cơ sở

Một quy trình điều chỉnh:

1. Xác định SLO: throughput, freshness, latency, error rate.
2. Đo baseline ở tải đại diện.
3. Xác định bottleneck bằng CPU, heap/GC, network và downstream metrics.
4. Thay đổi một nhóm cấu hình tại một thời điểm.
5. Chạy cùng workload/payload distribution để so sánh.
6. Đo throughput, p95/p99, GC, bytes/sec, lag và error rate.
7. Kiểm tra duplicate/rebalance/offset behavior.
8. Giữ thay đổi chỉ khi lợi ích đo được và reliability không suy giảm.

Không tăng đồng thời concurrency, max.poll.records, fetch sizes, Xmx và producer batch size rồi không biết thay đổi nào gây ra kết quả.

## 47. Ví dụ chẩn đoán: CPU cao, lag tăng

Triệu chứng:

- CPU pod sát limit.
- CPU throttling cao.
- Listener p95 tăng.
- Consumer lag tăng.
- Heap và GC tương đối ổn định.

Khả năng:

- JSON parsing/compression tốn CPU.
- Business computation nặng.
- Concurrency tăng nhưng CPU limit không đổi.
- TLS hoặc tracing overhead tăng.

Điều tra:

1. Dùng JFR CPU profile.
2. Kiểm tra thread nào chiếm CPU.
3. So sánh processing duration với CPU time.
4. Xem records/sec và payload size.
5. Kiểm tra CPU throttling.
6. Benchmark serializer/compression.
7. Tối ưu hot method hoặc tăng CPU capacity có kiểm soát.
8. Xác nhận lag giảm mà downstream không bị overload.

## 48. Ví dụ chẩn đoán: Heap tăng và OOMKilled

Triệu chứng:

- Container memory tăng dần.
- Heap after GC tăng.
- GC pause nhiều.
- Pod bị OOMKilled.
- Consumer lag tăng sau restart.

Khả năng:

- Async queue không giới hạn.
- Listener giữ payload trong cache.
- max.poll.records quá lớn so với payload size.
- In-flight tasks không được giải phóng.
- Batch hoặc retry state giữ object.
- Memory leak trong ứng dụng.

Điều tra:

1. So sánh heap used với RSS.
2. Xem heap after GC.
3. Thu heap dump ở môi trường an toàn nếu cần.
4. Phân tích dominator/retained objects.
5. Kiểm tra queue depth, cache size, in-flight tasks.
6. Kiểm tra direct buffers và thread count.
7. Giới hạn queue/batch và sửa reference retention.
8. Test soak đủ lâu để xác nhận live set ổn định.

Chỉ tăng Xmx khi có bằng chứng workload cần heap lớn hơn và container limit có headroom. Không dùng Xmx để che leak.

## 49. Ví dụ chẩn đoán: CPU thấp nhưng consumer chậm

Triệu chứng:

- CPU 20%.
- Heap ổn định.
- Listener duration cao.
- Consumer lag tăng.
- Thread dump có nhiều thread chờ socket/connection pool.

Khả năng:

- Database/API chậm.
- Connection pool cạn.
- Network RTT cao.
- Rate limiter đang chờ permit.
- External lock hoặc future wait.

Điều tra:

1. Đọc thread dump.
2. Xem dependency latency và pool saturation.
3. So sánh wall-clock duration với CPU time.
4. Kiểm tra network RTT/retransmissions.
5. Kiểm tra retry/backoff và circuit breaker.
6. Giới hạn timeout/in-flight concurrency.
7. Chỉ tăng consumer concurrency nếu dependency còn capacity.

CPU thấp không phải lý do đủ để tăng replicas; có thể làm downstream quá tải hơn.

## 50. Ví dụ chẩn đoán: Producer buffer chờ và send timeout

Triệu chứng:

- `bufferpool-wait-time` tăng.
- `buffer-available-bytes` giảm.
- `send()` block gần `max.block.ms`.
- Delivery timeout/error tăng.
- Broker/network throughput không theo kịp input.

Khả năng:

- Broker unavailable hoặc request latency cao.
- Producer send rate vượt network/broker capacity.
- Compression/serialization chậm.
- Batch/partition distribution không hiệu quả.
- Broker throttling/quota.

Hướng xử lý:

1. Xác nhận broker và network health.
2. Đọc request latency và outgoing bytes.
3. Kiểm tra buffer.memory, batch size và linger.
4. Kiểm tra partition leader distribution.
5. Xem compression CPU cost.
6. Giảm input hoặc áp dụng outbox/backpressure khi cần.
7. Không tăng buffer.memory vô hạn.
8. Xử lý send future failure rõ ràng và giữ event ID ổn định.

## 51. Capacity của downstream có thể giới hạn trước CPU/network

Một consumer có CPU dư và network tốt vẫn có thể bị giới hạn bởi database/API.

Ví dụ:

    Kafka input = 4.000 records/s
    Listener CPU capacity = 8.000 records/s
    Network capacity = 10.000 records/s
    Database safe capacity = 1.500 transactions/s

Nếu mỗi record tạo một DB transaction, throughput bền vững chỉ khoảng 1.500 records/s hoặc thấp hơn, tùy overhead và transaction batching.

Tăng concurrency sẽ làm số request đồng thời tới database tăng và có thể làm latency cao hơn. Hãy xem pool, lock contention, DB CPU, connection count và transaction latency.

Capacity end-to-end bị giới hạn bởi thành phần yếu nhất của pipeline, không phải tài nguyên đang dư ở consumer pod.

## 52. Autoscaling cần tính partition và resource limits

Autoscaling theo lag có thể giúp khi workload tăng, nhưng cần có giới hạn:

- Không scale consumer threads vượt số partition hữu ích mà không có lý do.
- Không scale vượt downstream capacity.
- Có startup/assignment time và rebalance cost.
- Có CPU/memory requests đủ để scheduler cấp tài nguyên.
- Có cooldown để tránh scale up/down liên tục.
- Có network/broker connection budget.
- Có giới hạn số replicas theo operational policy.

Một HPA dựa CPU có thể không scale khi consumer bị I/O-bound và CPU thấp dù lag cao. Một scaler dựa lag có thể scale quá mức khi downstream đang overload.

Dùng nhiều tín hiệu: lag, oldest age, processing rate, CPU, memory, downstream saturation và partition count.

## 53. Load test và soak test

Load test giúp tìm capacity ở một mức tải; soak test giúp phát hiện vấn đề chỉ xuất hiện sau thời gian dài như memory leak, cache growth hoặc connection leak.

Một kịch bản:

1. Dùng payload size gần p50/p95/p99 production.
2. Tạo input rate tăng theo từng bậc.
3. Đo CPU, throttling, heap, allocation và GC.
4. Đo producer/consumer bytes/sec và network RTT.
5. Theo dõi listener latency, lag và commit rate.
6. Tăng concurrency có kiểm soát.
7. Mô phỏng broker chậm/disconnect.
8. Mô phỏng downstream latency.
9. Chạy soak đủ lâu để live heap ổn định.
10. Xác nhận pod không OOM/restart và offset vẫn đúng.
11. Ghi lại điểm bão hòa và headroom.
12. Lặp lại với compression/batch/fetch configuration khác.

Không dùng dữ liệu synthetic quá nhỏ hoặc dễ nén để đại diện cho production nếu payload thực tế khác nhiều.

## 54. Những lỗi tuning thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ nhìn CPU toàn pod | Bỏ sót một thread/core bão hòa | Xem thread profile và throttling |
| Tăng concurrency vô hạn | Tăng threads, connections và rebalance | Ràng buộc partition/downstream |
| Đặt Xmx bằng container memory limit | OOM ngoài heap/OOMKilled | Chừa native/stack/direct headroom |
| Tăng heap để chữa leak | Chỉ trì hoãn OOM | Tìm retained objects |
| Queue async không giới hạn | Heap tăng không kiểm soát | Bounded queue/backpressure |
| Tăng max.poll.records không đo heap | Peak in-flight memory tăng | Benchmark payload distribution |
| Tăng fetch limits tối đa | Buffer và memory pressure | Tune theo record size/partition |
| Compression mạnh nhất luôn tốt nhất | CPU có thể thành bottleneck | Benchmark codec |
| Tăng producer buffer để chữa broker down | Chỉ trì hoãn buffer full | Sửa capacity/network, backpressure |
| CPU thấp nghĩa consumer còn dư | Có thể đang chờ I/O | Đọc thread states/dependency metrics |
| Ping thấp nghĩa Kafka network tốt | Bỏ sót TLS/broker/request delay | Đo Kafka client request metrics |
| Scale theo lag không giới hạn | Broker/DB overload | Kết hợp partition và dependency capacity |
| Chỉ dùng avg | Che tail latency và hot partition | Theo dõi p95/p99 và per-partition |
| Log mọi record ở INFO | CPU/I/O/storage bottleneck | Sampling/log level phù hợp |
| Tracing 100% không tính cost | Exporter/heap/network overload | Sampling và bounded exporter |

## 55. Checklist capacity cho production

Trước khi xác nhận capacity một Spring Kafka service, cần biết:

- Input peak records/sec và bytes/sec?
- Record size p50/p95/p99/max?
- Số partition và phân phối key có đều?
- Consumer replicas × concurrency có hợp lý?
- CPU time thực tế mỗi record?
- CPU request/limit và throttling?
- Heap after GC, allocation rate và GC pause?
- Container RSS có headroom ngoài heap?
- Direct memory, thread count và stack memory?
- max.poll.records/fetch limits có phù hợp payload?
- Producer buffer/batch/linger/compression có benchmark?
- Network throughput, RTT, packet loss và broker request latency?
- Downstream capacity, pool và concurrency limit?
- Retry, DLT và async queues có bounded?
- Consumer lag/oldest age có đáp ứng SLO?
- Observability overhead có được tính?
- Có load test và soak test với payload gần production?
- Có runbook khi CPU, heap hoặc network bão hòa?
- Autoscaling có giới hạn theo partition và downstream?
- Sau broker outage, backlog drain có đủ nhanh và an toàn?

## 56. Kết luận

**CPU, heap và network là ba giới hạn tài nguyên có thể quyết định throughput và độ ổn định của Spring Kafka.** CPU ảnh hưởng serialization, compression, deserialization và business logic; heap ảnh hưởng object retention, batch, queue và GC; network ảnh hưởng producer send, consumer fetch, replication, coordinator requests và latency giữa các region.

Không thể tuning đúng chỉ bằng cách tăng concurrency, heap hoặc buffer. Hãy đo workload theo record rate và byte rate, tách CPU time khỏi I/O wait, quan sát heap after GC và RSS, theo dõi Kafka client metrics và broker/network health. Capacity phải được tính theo bottleneck end-to-end, bao gồm cả database/API và chi phí observability.

Một cấu hình production tốt giữ headroom cho burst, giới hạn in-flight work, dùng backpressure khi cần và được kiểm chứng bằng load/soak tests. Khi CPU, heap hoặc network chạm giới hạn, hãy xác định tài nguyên nào đang bão hòa và thay đổi đúng tầng. **Mục tiêu là throughput bền vững với latency và data reliability nằm trong SLO, không phải mức sử dụng tài nguyên cao nhất có thể đạt được.**
