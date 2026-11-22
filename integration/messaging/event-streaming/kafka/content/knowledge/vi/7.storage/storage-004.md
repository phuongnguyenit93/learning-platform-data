# Log end offset, high watermark và last stable offset

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, từ topic, partition, offset, producer và consumer group đến replication, KRaft, Java/Spring Kafka, retry, ordering, giao dịch, Kafka Connect/Streams và vận hành cụm. Bài học này giải thích ba mốc offset quan trọng trong một partition: **Log End Offset (LEO)**, **High Watermark (HW)** và **Last Stable Offset (LSO)**.

Ba mốc này trả lời ba câu hỏi khác nhau: replica đã ghi đến đâu, dữ liệu nào đã được replication xác nhận, và consumer đọc theo chế độ read_committed có thể nhìn thấy dữ liệu đến đâu. Phân biệt đúng chúng giúp bạn chẩn đoán replication lag, hiểu dữ liệu có thể đọc sau failover và tránh nhầm lẫn khi giao dịch Kafka còn đang mở.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Định nghĩa LEO, HW và LSO theo phạm vi của một partition.
- Phân biệt vị trí ghi cục bộ của replica với ranh giới dữ liệu đã được replication xác nhận.
- Giải thích vì sao LEO của leader có thể lớn hơn HW.
- Mô tả cách follower fetch record và cách HW tiến lên khi replica bắt kịp.
- Giải thích ảnh hưởng của HW đến khả năng đọc dữ liệu và phục hồi khi leader thay đổi.
- Mô tả cách giao dịch đang mở làm LSO thấp hơn HW.
- Phân biệt dữ liệu mà consumer read_uncommitted và read_committed có thể đọc.
- Dùng Kafka CLI, AdminClient và metric phù hợp để quan sát các mốc offset, đồng thời nhận biết giới hạn của từng công cụ.

## 2. Ba mốc offset trong một partition

Kafka lưu dữ liệu của mỗi partition thành một log. Producer gửi record đến partition leader; các follower sao chép log từ leader. Mỗi replica duy trì vị trí ghi cục bộ, còn Kafka theo dõi các ranh giới phục vụ replication và consumer.

Ba khái niệm cần phân biệt:

| Mốc | Tên đầy đủ | Ý nghĩa |
|---|---|---|
| LEO | Log End Offset | Offset kế tiếp mà một replica sẽ ghi vào log của chính nó. |
| HW | High Watermark | Ranh giới exclusive của dữ liệu đã được replication xác nhận trong partition; consumer thông thường không đọc vượt qua mốc này. |
| LSO | Last Stable Offset | Ranh giới exclusive mà consumer read_committed có thể đọc khi xét các giao dịch chưa hoàn tất. |

Cả ba đều được xét theo từng partition. Một topic có nhiều partition sẽ có các mốc riêng cho từng partition; không có một LEO, HW hoặc LSO chung đại diện cho toàn topic.

### 2.1. Log End Offset (LEO)

LEO là vị trí kế tiếp mà replica sẽ dùng nếu ghi thêm record. Nếu replica đã ghi các offset 0 đến 9, LEO của replica đó là 10.

LEO được theo dõi riêng trên từng replica:

- Leader có LEO của leader.
- Mỗi follower có LEO cục bộ của follower.
- Follower chưa fetch hoặc chưa ghi hết dữ liệu từ leader có thể có LEO thấp hơn leader.

Ví dụ:

~~~text
Partition orders-0

Leader:
  Record offsets: 0 1 2 3 4 5 6 7 8 9
  LEO = 10

Follower A:
  Record offsets: 0 1 2 3 4 5 6 7
  LEO = 8

Follower B:
  Record offsets: 0 1 2 3 4 5 6 7 8 9
  LEO = 10
~~~

LEO là mốc ghi cục bộ. Nó không tự động có nghĩa mọi record trước LEO đã được sao chép sang các replica khác hoặc đã sẵn sàng cho mọi consumer.

### 2.2. High Watermark (HW)

HW là ranh giới offset exclusive cho phần log đã được replication xác nhận theo tập In-Sync Replicas (ISR). Có thể hiểu: record có offset nhỏ hơn HW đã được các replica đang thuộc ISR xác nhận theo tiến độ replication; offset bằng HW là vị trí tiếp theo sau phần dữ liệu đó.

Giả sử:

- Leader LEO = 10.
- Follower A LEO = 8.
- Follower B LEO = 10.
- Cả ba replica đang thuộc ISR.

Trong ví dụ đơn giản, HW chưa thể vượt qua 8 vì follower A mới ghi đến vị trí kế tiếp 8. Các record offset 0 đến 7 đã được xác nhận trên cả ISR; record offset 8 và 9 chưa được xác nhận trên follower A.

~~~text
Partition orders-0

Leader LEO     = 10
Follower A LEO = 8
Follower B LEO = 10
High Watermark = 8

Offsets:
  0 1 2 3 4 5 6 7 | 8 9
  <--- dưới HW --->   <--- chưa được HW xác nhận --->
~~~

Trong ví dụ, consumer đọc thông thường có thể đọc các record dưới HW, tức offset 0 đến 7. Record 8 và 9 có thể đã tồn tại trên leader nhưng chưa nằm trong phần log được xác nhận bởi HW.

Khi follower A fetch và ghi xong record 8, 9, LEO của follower A tăng lên 10. Nếu các điều kiện ISR vẫn thỏa mãn, HW có thể tiến lên 10.

**Điểm cần nhớ:** LEO cho biết replica đã ghi cục bộ đến đâu; HW cho biết ranh giới replication đã xác nhận. Hai mốc có thể khác nhau trong lúc follower đang bắt kịp.

### 2.3. Last Stable Offset (LSO)

LSO liên quan đến giao dịch Kafka. Với consumer có thuộc tính **isolation.level=read_committed**, Kafka không trả về record vượt qua ranh giới của giao dịch chưa hoàn tất sớm nhất trong partition.

- Nếu không có giao dịch đang mở, LSO thường bằng HW.
- Nếu có giao dịch đang mở, LSO là ranh giới tại offset đầu tiên của giao dịch chưa hoàn tất sớm nhất.
- Consumer read_committed chỉ đọc đến trước LSO và bỏ qua record thuộc transaction đã abort.

Ví dụ partition có HW bằng 10, nhưng một transaction bắt đầu tại offset 6 và chưa commit hoặc abort:

~~~text
Partition orders-0

Offsets:
  0 1 2 3 4 5 | 6 7 8 9
  <--- ổn định ---> <--- giao dịch đang mở / phía sau nó --->

HW  = 10
LSO = 6
~~~

Consumer **read_uncommitted** có thể đọc dữ liệu đến trước HW, bao gồm record thuộc transaction chưa hoàn tất. Consumer **read_committed** chỉ đọc đến trước LSO, vì thế trong ví dụ chỉ đọc được phần offset 0 đến 5.

Khi transaction được commit hoặc abort và transaction marker được ghi, LSO có thể tiến lên. Nếu không còn transaction nào đang mở, LSO sẽ bắt kịp HW.

## 3. Quan hệ giữa LEO, HW và LSO

Trong cách quan sát thông thường trên leader, có thể hình dung thứ tự các ranh giới:

\[
LSO \leq HW \leq LEO
\]

- LEO là vị trí ghi cục bộ kế tiếp của replica.
- HW không vượt quá phần log được xác nhận theo ISR.
- LSO không vượt quá HW và có thể thấp hơn HW nếu còn transaction đang mở.

Quan hệ này mô tả các mốc của một partition leader trong trạng thái vận hành thông thường. LEO của từng follower có thể khác LEO của leader; khi leader thay đổi, log được phục hồi và các mốc có thể được tính toán lại theo replica được chọn.

Ví dụ tổng hợp:

~~~text
Partition orders-0

LEO = 15
HW  = 12
LSO = 8

Offsets:
  0 1 2 3 4 5 6 7 | 8 9 10 11 | 12 13 14
  <--- read_committed --->  <--- read_uncommitted có thể đọc --->
                            <--- vượt HW, chưa được xác nhận --->
~~~

Trong ví dụ:

- Offset 0 đến 7 nằm trước LSO nên có thể được consumer read_committed đọc, sau khi áp dụng quy tắc lọc record aborted.
- Offset 8 đến 11 nằm dưới HW nhưng từ LSO trở đi; read_uncommitted có thể đọc, còn read_committed phải chờ transaction sớm nhất được hoàn tất.
- Offset 12 đến 14 nằm từ HW trở đi; chưa thuộc vùng đọc thông thường được xác nhận.

Bảng so sánh:

| Câu hỏi | Mốc trả lời |
|---|---|
| Replica này đã ghi đến vị trí kế tiếp nào? | LEO của replica đó |
| Phần log nào đã được replication xác nhận theo ISR? | HW |
| Consumer read_uncommitted có thể đọc đến đâu? | Trước HW |
| Consumer read_committed có thể đọc đến đâu? | Trước LSO |
| Giao dịch đang mở sớm nhất bắt đầu tại đâu? | LSO thường bị giữ tại offset đầu tiên của giao dịch đó |

## 4. Replication làm HW tiến lên như thế nào?

Mỗi partition có một leader và có thể có nhiều follower. Producer gửi record đến leader. Follower chủ động fetch dữ liệu từ leader và ghi vào log cục bộ.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant L as Partition Leader
    participant F1 as Follower A
    participant F2 as Follower B
    participant C as Consumer

    P->>L: Produce records
    L->>L: Append record, tăng LEO
    F1->>L: Fetch records
    L-->>F1: Trả records mới
    F1->>F1: Append records, tăng LEO
    F2->>L: Fetch records
    L-->>F2: Trả records mới
    F2->>F2: Append records, tăng LEO
    L->>L: Cập nhật HW khi ISR đã xác nhận
    L-->>C: Chỉ phục vụ dữ liệu trong ranh giới HW
~~~

Các bước chính:

1. Producer gửi batch đến leader.
2. Leader append batch vào log cục bộ và LEO của leader tăng.
3. Follower fetch dữ liệu từ leader theo vị trí fetch của từng replica.
4. Follower append dữ liệu vào log cục bộ và cập nhật LEO riêng.
5. Khi replica trong ISR đã bắt kịp đến một ranh giới, leader có thể cập nhật HW đến ranh giới đó.
6. Consumer đọc dữ liệu trong phạm vi được phép theo isolation level.

Việc cập nhật HW không đơn giản là lấy LEO lớn nhất. Nếu follower còn nằm trong ISR nhưng chưa bắt kịp, HW phải chờ. Nếu follower không bắt kịp trong thời gian cấu hình, broker có thể loại follower khỏi ISR; sau khi ISR thay đổi, điều kiện cập nhật HW được đánh giá lại trên tập ISR mới.

### 4.1. Ví dụ HW tiến lên

Ban đầu:

| Replica | LEO |
|---|---:|
| Leader | 10 |
| Follower A | 8 |
| Follower B | 10 |
| HW | 8 |

Follower A fetch và append thêm hai record:

| Replica | LEO |
|---|---:|
| Leader | 10 |
| Follower A | 10 |
| Follower B | 10 |
| HW | 10 |

Khi follower A đã bắt kịp, phần log đến offset 9 được xác nhận theo ISR và HW tiến lên 10.

### 4.2. Vì sao follower có thể bị loại khỏi ISR?

Follower có thể chậm do:

- Mạng giữa broker bị gián đoạn hoặc độ trễ cao.
- Broker follower thiếu CPU, RAM hoặc năng lực I/O đĩa.
- Ổ đĩa bị nghẽn hoặc gần hết dung lượng.
- Follower khởi động lại và cần bắt kịp log.
- Broker leader hoặc follower quá tải do throughput tăng đột biến.

Kafka theo dõi khả năng bắt kịp của follower và có thể loại replica không còn đồng bộ khỏi ISR. Khi follower phục hồi, nó cần fetch đủ dữ liệu để bắt kịp trước khi được đưa trở lại ISR.

Không nên chỉ nhìn LEO của leader để kết luận cluster đang khỏe. Cần quan sát ISR, under-replicated partitions, offline partitions và độ trễ replication.

## 5. HW, producer acknowledgment và độ bền dữ liệu

Cấu hình producer **acks** quyết định producer chờ xác nhận ở mức nào:

- **acks=0:** producer không chờ broker xác nhận record.
- **acks=1:** leader xác nhận sau khi append vào log cục bộ.
- **acks=all** (hoặc **-1**): leader chờ các replica cần thiết theo chính sách ISR và **min.insync.replicas** trước khi trả thành công.

**acks=all** không có nghĩa mọi broker trong cluster đều phải xác nhận. Nó liên quan đến tập ISR của partition và ngưỡng **min.insync.replicas**.

Ví dụ:

- Replication factor = 3.
- ISR hiện có 3 replica.
- min.insync.replicas = 2.
- Producer dùng acks=all.

Trong điều kiện bình thường, leader cần bảo đảm yêu cầu ghi thỏa mãn chính sách ISR. Nếu ISR giảm xuống còn 1, yêu cầu ghi với acks=all có thể bị từ chối vì không đủ min ISR.

HW là ranh giới replication được xác nhận; producer acknowledgment và HW liên quan chặt chẽ nhưng không nên coi chúng là cùng một khái niệm. Producer nhận kết quả của request theo cơ chế acks, còn HW biểu thị tiến độ replication mà broker quản lý cho partition.

Các cấu hình thường gặp:

| Cấu hình | Vai trò |
|---|---|
| replication.factor | Số replica được gán cho partition. |
| min.insync.replicas | Số replica tối thiểu trong ISR để chấp nhận ghi với acks=all. |
| acks | Mức xác nhận producer yêu cầu. |
| replica.lag.time.max.ms | Ngưỡng thời gian liên quan đến việc follower bị coi là không còn theo kịp leader; tên và hành vi cần đối chiếu phiên bản Kafka. |

Một cấu hình có replication factor lớn nhưng min ISR quá thấp vẫn có thể chấp nhận ghi với mức dự phòng thấp hơn mong muốn. Hãy chọn replication factor, min ISR và acks cùng nhau theo yêu cầu durability và availability.

## 6. HW và khả năng phục hồi khi leader thay đổi

Giả sử leader cũ có LEO bằng 15 nhưng HW chỉ bằng 12. Các record offset 12 đến 14 đã được append trên leader nhưng chưa được replication xác nhận đến ranh giới HW.

Nếu leader cũ bị mất và một replica trong ISR được bầu làm leader mới, Kafka phục hồi partition theo trạng thái log được xác nhận. Record nằm ngoài HW không được bảo đảm sẽ tồn tại sau leader change; chúng có thể bị truncate trong quá trình phục hồi nếu không có trên replica được chọn.

~~~text
Trước sự cố:

Leader cũ:
  LEO = 15
  HW  = 12
  offsets 12, 13, 14 chưa được HW xác nhận

Follower được bầu làm leader:
  LEO = 12
  HW  = 12

Sau phục hồi:
  Leader mới tiếp tục từ ranh giới log đã được xác nhận.
~~~

Đây là lý do producer acknowledgment, ISR và HW quan trọng đối với durability. Khi dùng unclean leader election, Kafka có thể chọn replica không nằm trong ISR nếu không còn replica ISR khả dụng; lựa chọn này tăng availability nhưng có nguy cơ mất dữ liệu đã được xác nhận trước đó. Trong hệ thống cần độ bền cao, cần hiểu rõ chính sách unclean leader election và failure domain.

## 7. LSO và giao dịch Kafka

LSO chỉ có ý nghĩa khi xét transaction và consumer isolation. Mỗi partition theo dõi transaction đang mở ảnh hưởng đến khả năng đọc ổn định.

Giả sử một producer bắt đầu transaction T1 và ghi hai record vào partition orders-0:

- Offset 5: OrderPaid.
- Offset 6: OrderReadyToShip.

Sau đó producer chưa commit hoặc abort. Trong khi đó, một producer khác có thể ghi record không thuộc transaction tại offset 7. Nếu HW đã tiến đến 8, LSO vẫn có thể bị giữ ở offset 5 do T1 là transaction chưa hoàn tất sớm nhất.

~~~text
Partition orders-0

Offset 0-4 : record ổn định
Offset 5   : T1 bắt đầu
Offset 6   : record thuộc T1
Offset 7   : record không thuộc T1
HW = 8
LSO = 5
~~~

Consumer **read_uncommitted** có thể đọc record dưới HW, bao gồm record của T1 khi transaction chưa hoàn tất. Consumer **read_committed** dừng trước LSO, do đó chưa đọc offset 5 trở đi.

Khi T1 commit:

1. Transaction coordinator ghi nhận quyết định commit.
2. Coordinator yêu cầu partition leader ghi commit marker.
3. Partition cập nhật trạng thái transaction.
4. LSO có thể tiến lên, trong ví dụ có thể tiến đến HW nếu không còn transaction chưa hoàn tất khác.
5. Consumer read_committed tiếp tục đọc dữ liệu ổn định.

Khi T1 abort, marker abort được ghi và consumer read_committed bỏ qua các record thuộc T1. Sau khi transaction được hoàn tất, LSO cũng có thể tiến lên để consumer đọc các record sau đó.

### 7.1. Một transaction có thể ảnh hưởng nhiều partition

Một transaction có thể ghi vào nhiều partition. Mỗi partition có LSO riêng, phụ thuộc transaction chưa hoàn tất có record trên partition đó.

Transaction coordinator quản lý quyết định chung của transaction, còn từng partition lưu marker và trạng thái cần thiết để phục vụ consumer. Vì vậy, LSO của các partition trong cùng transaction không nhất thiết có cùng giá trị số.

### 7.2. Transaction mở quá lâu

Một transaction bị treo có thể giữ LSO ở một vị trí trong thời gian dài. Consumer read_committed trên partition đó không thể đọc vượt qua ranh giới này, kể cả khi phía sau đã có nhiều record khác được ghi và HW tiếp tục tiến.

Hậu quả có thể gồm:

- Consumer read_committed tăng độ trễ quan sát dữ liệu.
- Consumer lag tăng dù broker vẫn nhận record.
- Các record phía sau transaction chưa hoàn tất bị giữ lại khỏi read_committed.
- Bộ xử lý downstream có thể trễ so với tốc độ producer.

Do đó, nên giữ transaction ngắn, cấu hình timeout hợp lý và theo dõi transaction duration, abort rate, LSO cùng consumer lag.

## 8. Hai chế độ đọc: read_uncommitted và read_committed

Kafka consumer có thuộc tính **isolation.level**:

| Isolation level | Ranh giới đọc | Transaction bị abort |
|---|---|---|
| read_uncommitted | Trước HW | Có thể nhìn thấy record thuộc transaction chưa hoàn tất hoặc đã abort. |
| read_committed | Trước LSO | Bỏ qua record thuộc transaction bị abort; chỉ trả về record ngoài transaction và record thuộc transaction đã commit. |

Ví dụ cấu hình Java:

~~~java
Properties properties = new Properties();

properties.put(
    ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
properties.put(
    ConsumerConfig.GROUP_ID_CONFIG,
    "orders-reader"
);
properties.put(
    ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);
properties.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    StringDeserializer.class.getName()
);
properties.put(
    ConsumerConfig.ISOLATION_LEVEL_CONFIG,
    "read_committed"
);
~~~

Nếu consumer đọc output từ transactional producer và nghiệp vụ chỉ chấp nhận kết quả đã commit, hãy cấu hình read_committed. Nếu dùng read_uncommitted, consumer có thể nhìn thấy record mà producer sau đó abort.

Cả hai chế độ đều bị giới hạn bởi dữ liệu mà broker cho phép đọc; read_committed có thêm ranh giới LSO để không đi qua transaction chưa hoàn tất.

## 9. Quan sát các offset bằng Kafka CLI

Không phải mọi Kafka CLI đều hiển thị trực tiếp cả LEO, HW và LSO. Cần hiểu công cụ đang trả về loại offset nào trước khi dùng số liệu để kết luận.

### 9.1. Xem leader, replica và ISR

Linux hoặc macOS:

~~~bash
bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-topics.bat --bootstrap-server localhost:9092 --describe --topic orders
~~~

Kết quả mô tả topic thường có:

- Partition ID.
- Leader broker.
- Danh sách replica.
- Danh sách ISR.

Lệnh này giúp kiểm tra trạng thái replica và ISR. Nó không phải lệnh đọc trực tiếp HW hoặc LSO.

### 9.2. Xem log end offset

Một số bản phân phối Kafka có **kafka-get-offsets**:

Linux hoặc macOS:

~~~bash
bin/kafka-get-offsets.sh --bootstrap-server localhost:9092 --topic orders --time -1
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-get-offsets.bat --bootstrap-server localhost:9092 --topic orders --time -1
~~~

**--time -1** yêu cầu vị trí latest; **--time -2** thường yêu cầu earliest. Đây là offset đầu/cuối được công cụ truy vấn qua API, không nên mặc định coi kết quả là HW hoặc LSO. Tên script và tham số có thể khác theo phiên bản Kafka.

### 9.3. Xem consumer group và lag

Linux hoặc macOS:

~~~bash
bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group orders-reader
~~~

Windows PowerShell:

~~~powershell
.\bin\windows\kafka-consumer-groups.bat --bootstrap-server localhost:9092 --describe --group orders-reader
~~~

Kết quả thường có CURRENT-OFFSET, LOG-END-OFFSET và LAG. Đây là thông tin hữu ích để theo dõi tiến độ group so với log end offset mà công cụ truy vấn. Không nên diễn giải LOG-END-OFFSET hoặc LAG trong output này thành HW hoặc LSO nếu công cụ không công bố rõ như vậy.

### 9.4. Giới hạn của Kafka Consumer và Admin API

Java **KafkaConsumer.beginningOffsets()** và **endOffsets()**, hoặc AdminClient **listOffsets()** với **OffsetSpec.earliest()**/**latest()**, hữu ích để lấy vị trí đầu và cuối log cho partition.

Ví dụ với AdminClient:

~~~java
Map<TopicPartition, OffsetSpec> request = new HashMap<>();

request.put(
    new TopicPartition("orders", 0),
    OffsetSpec.latest()
);

Map<TopicPartition, ListOffsetsResult.ListOffsetsResultInfo> result =
    adminClient.listOffsets(request).all().get();

result.forEach((partition, info) ->
    System.out.printf(
        "topic=%s partition=%d latestOffset=%d%n",
        partition.topic(),
        partition.partition(),
        info.offset()
    )
);
~~~

API này giúp quan sát latest offset, thường tương ứng log end offset được broker trả về. Consumer API tiêu chuẩn không cung cấp một phương thức chung để đọc trực tiếp HW và LSO cho mọi partition. Đừng đặt tên một giá trị endOffsets() thành high watermark nếu chưa có nguồn dữ liệu xác nhận.

Để quan sát sâu hơn, hãy kết hợp broker metrics, log broker, công cụ giám sát Kafka và API phù hợp với phiên bản đang chạy. Tên metric, cách expose LSO/HW và mức chi tiết có thể thay đổi theo phiên bản hoặc nền tảng quản lý.

## 10. Các chỉ số cần theo dõi khi vận hành

Ba mốc offset giúp phân tích nhiều loại vấn đề:

| Tín hiệu | Dấu hiệu | Hướng điều tra |
|---|---|---|
| LEO leader tăng nhanh, follower LEO chậm | Follower không theo kịp tốc độ ghi. | Kiểm tra network, disk I/O, CPU và fetch lag. |
| HW cách xa LEO leader | Có phần log leader đã ghi nhưng chưa được ISR xác nhận. | Kiểm tra replica lag, ISR và broker đang chậm. |
| ISR liên tục co lại | Replica thường xuyên bị loại khỏi ISR. | Kiểm tra broker restart, network, storage và cấu hình replica lag. |
| LSO thấp hơn HW trong thời gian dài | Có transaction chưa hoàn tất giữ ranh giới đọc ổn định. | Kiểm tra transaction duration, producer lỗi và timeout. |
| Consumer read_committed lag tăng | Consumer không thể đọc vượt qua LSO hoặc xử lý chậm. | So sánh LSO/HW, transaction state, throughput và thời gian xử lý consumer. |
| Under-replicated partitions tăng | Replica không nằm trong ISR hoặc chưa theo kịp. | Kiểm tra tình trạng broker, partition reassignment và tải cụm. |

Không nên dùng một metric đơn lẻ để kết luận mất dữ liệu. Hãy đối chiếu leader, ISR, replica LEO, HW, LSO, producer acknowledgment và consumer isolation level.

## 11. Tình huống thực tế: phân tích consumer bị chậm

Giả sử hệ thống có các số liệu minh họa cho partition orders-0:

| Mốc | Giá trị |
|---|---:|
| Leader LEO | 50.000 |
| High Watermark | 49.980 |
| Last Stable Offset | 49.500 |
| Consumer committed offset | 49.300 |

Có thể phân tích:

1. Leader đã ghi đến vị trí kế tiếp 50.000.
2. HW ở 49.980, nên có khoảng cách 20 offset giữa LEO leader và vùng đã được replication xác nhận.
3. LSO ở 49.500, thấp hơn HW 480 offset. Điều này gợi ý có transaction chưa hoàn tất sớm nhất đang giữ ranh giới read_committed tại đó.
4. Consumer group đã commit vị trí 49.300, thấp hơn LSO 200 offset. Consumer còn có thể đọc dữ liệu ổn định trong khoảng này, nhưng vẫn cần xét tốc độ xử lý.
5. Nếu consumer đang dùng read_committed, nó không thể đọc vượt qua LSO cho đến khi transaction được hoàn tất.

Hướng xử lý:

- Kiểm tra producer transactional có bị treo hoặc giữ transaction quá lâu.
- Kiểm tra transaction timeout và coordinator errors.
- Kiểm tra ISR, follower fetch và broker đang làm leader.
- Xác minh consumer isolation level và tốc độ xử lý.
- Theo dõi các mốc sau khi transaction commit/abort và follower bắt kịp.

Ví dụ này cho thấy consumer lag có thể đến từ xử lý chậm, replication chậm hoặc transaction chưa hoàn tất. Cần tách từng nguyên nhân thay vì chỉ tăng số consumer.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| LEO chính là HW. | LEO là vị trí ghi cục bộ của replica; HW là ranh giới replication được xác nhận. |
| Record đã có trên leader thì mọi consumer đều đọc được. | Consumer thông thường bị giới hạn bởi HW; read_committed còn bị giới hạn bởi LSO. |
| HW bằng offset của record cuối cùng đã commit. | HW thường là ranh giới exclusive, tức vị trí kế tiếp sau phần log đã được xác nhận. |
| LSO luôn bằng HW. | LSO có thể thấp hơn HW khi còn transaction chưa hoàn tất. |
| read_committed chỉ đọc record transaction. | Nó đọc cả record không thuộc transaction và record thuộc transaction đã commit, đồng thời bỏ qua record aborted. |
| kafka-consumer-groups --describe hiển thị trực tiếp HW và LSO. | Công cụ thường hiển thị committed offset, log end offset và lag; không mặc định là HW/LSO. |
| Producer nhận ACK nghĩa là mọi replica trong cluster đã ghi. | Mức xác nhận phụ thuộc acks và ISR, không phải toàn bộ broker của cluster. |
| LEO cao hơn HW nghĩa là dữ liệu chắc chắn đã mất. | Đây có thể là replication lag tạm thời; dữ liệu ngoài HW chưa được bảo đảm sau leader change. |

## 13. Bài tập thực hành

### Bài 1: Quan sát LEO và HW qua replication

Tạo topic có một partition và replication factor 2 hoặc 3 trong cluster thực hành nhiều broker.

1. Gửi một lượng record liên tục vào topic.
2. Dùng kafka-topics --describe để theo dõi leader và ISR.
3. Quan sát các metric/log replica của từng broker theo công cụ giám sát sẵn có.
4. Ghi lại LEO của leader và follower tại một số thời điểm.
5. Giải thích vì sao HW có thể thấp hơn LEO của leader khi follower chưa bắt kịp.

Không dừng broker production hoặc tạo sự cố trên cụm dùng chung để thực hiện bài tập. Có thể dùng môi trường lab cô lập để thử follower chậm hoặc broker restart.

### Bài 2: Quan sát LSO với transaction đang mở

1. Tạo topic test có một partition.
2. Khởi chạy transactional producer.
3. Bắt đầu transaction và gửi một record.
4. Giữ transaction chưa commit hoặc abort.
5. Chạy hai consumer: một dùng read_uncommitted, một dùng read_committed.
6. Gửi thêm record phía sau transaction từ luồng phù hợp để quan sát ranh giới đọc.
7. Commit hoặc abort transaction và quan sát consumer read_committed tiếp tục đọc.

Ghi lại sự khác nhau giữa HW và LSO trong thời gian transaction mở.

### Bài 3: Phân tích sự cố

Một partition có các số liệu:

~~~text
Leader LEO = 1200
Follower A LEO = 1200
Follower B LEO = 1170
HW = 1170
LSO = 1100
~~~

Trả lời:

1. Replica nào đang chậm?
2. Vì sao HW chưa tiến lên 1200 nếu cả ba replica vẫn thuộc ISR?
3. LSO thấp hơn HW gợi ý điều gì?
4. Consumer read_uncommitted có thể đọc đến ranh giới nào?
5. Consumer read_committed có thể đọc đến ranh giới nào?
6. Cần kiểm tra những metric hoặc log nào trước khi kết luận có mất dữ liệu?

### Bài 4: Đọc kết quả CLI

Chạy kafka-topics --describe, kafka-get-offsets và kafka-consumer-groups --describe trên cùng một topic. Ghi rõ mỗi lệnh cung cấp thông tin nào và thông tin nào không thể suy ra trực tiếp từ output.

## 14. Câu hỏi tự kiểm tra

1. LEO là vị trí nào trong log của một replica?
2. Vì sao một partition có thể có LEO khác nhau giữa leader và follower?
3. HW có ý nghĩa gì đối với dữ liệu được replication xác nhận?
4. Vì sao HW thường không vượt qua LEO thấp nhất của các replica đang thuộc ISR trong ví dụ replication cơ bản?
5. LSO được tính dựa trên điều kiện nào?
6. Khi không có transaction đang mở, quan hệ giữa LSO và HW thường là gì?
7. Consumer read_uncommitted và read_committed khác nhau ở ranh giới đọc nào?
8. Vì sao transaction mở lâu có thể làm consumer read_committed bị chậm?
9. Record nằm sau HW có được bảo đảm tồn tại sau leader change không?
10. Vì sao endOffsets() không nên được gọi là HW hoặc LSO?
11. acks=all có nghĩa mọi broker trong cluster đều phải xác nhận không?
12. Khi consumer lag tăng, cần đối chiếu những mốc và chỉ số nào?

## Kết luận

LEO, HW và LSO là ba ranh giới khác nhau trong một partition. LEO cho biết vị trí ghi cục bộ kế tiếp của replica; HW xác định phần log đã được replication xác nhận; LSO giới hạn dữ liệu mà consumer read_committed có thể đọc khi còn transaction chưa hoàn tất.

Khi follower bắt kịp, HW có thể tiến lên. Khi transaction commit hoặc abort, LSO có thể tiến lên để consumer read_committed tiếp tục đọc. Trong vận hành, hãy kết hợp các mốc này với ISR, producer acks, transaction duration và consumer lag để phân tích replication, durability và độ trễ đọc.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| LEO (Log End Offset) | Vị trí kế tiếp mà một replica sẽ ghi vào log cục bộ. |
| HW (High Watermark) | Ranh giới exclusive của phần log được replication xác nhận theo ISR. |
| LSO (Last Stable Offset) | Ranh giới exclusive cho consumer read_committed, bị giữ bởi transaction chưa hoàn tất sớm nhất. |
| ISR | Tập replica đang được xem là đồng bộ với leader theo điều kiện Kafka. |
| Leader | Replica nhận request ghi/đọc chính của partition. |
| Follower | Replica fetch và sao chép log từ leader. |
| Transaction marker | Control record đánh dấu commit hoặc abort của giao dịch. |
| read_uncommitted | Isolation level cho phép đọc record transactional chưa hoàn tất hoặc đã abort, trong phạm vi HW. |
| read_committed | Isolation level chỉ trả về record ngoài transaction hoặc thuộc transaction đã commit, trong phạm vi LSO. |
| Consumer lag | Chênh lệch giữa tiến độ consumer group và vị trí log cuối theo cách tính của công cụ. |

