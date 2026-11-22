# Phân bổ partition không đều

Trong Kafka, partition là đơn vị lưu trữ, đọc và xử lý song song. Một topic có nhiều partition có thể được consumer group xử lý đồng thời bởi nhiều consumer. Tuy nhiên, số partition nhiều không tự bảo đảm tải được chia đều. Một số partition có thể nhận phần lớn record, chứa record lớn hơn, hoặc được gán nhiều hơn cho một consumer. Kết quả là một consumer hoặc broker bị quá tải trong khi các consumer khác còn nhàn rỗi.

Khi điều tra hiện tượng này, cần phân biệt ba lớp vấn đề:

1. **Producer phân phối dữ liệu không đều:** key hoặc partitioner khiến một số partition nhận nhiều record/byte hơn.
2. **Consumer group phân công partition không đều:** assignment strategy hoặc topology topic khiến một consumer giữ nhiều partition hơn consumer khác.
3. **Broker phân bố leader/replica không đều:** một broker chịu nhiều lưu lượng đọc/ghi hơn các broker còn lại.

Ba vấn đề có thể xuất hiện đồng thời nhưng cần cách xử lý khác nhau. Tăng `concurrency` chỉ có ích khi có partition chưa được consumer nào xử lý; nó không làm một partition nóng tự chia thành nhiều luồng độc lập.

## 1. Partition là ranh giới song song và thứ tự

Kafka chỉ bảo đảm thứ tự record bên trong cùng một partition. Một consumer group tại một thời điểm chỉ giao một partition cho tối đa một consumer member xử lý. Vì vậy, số partition giới hạn mức song song tối đa của group đối với topic đó.

Ví dụ, topic `orders` có sáu partition:

```text
Topic orders
  partition 0  ----> consumer A
  partition 1  ----> consumer A
  partition 2  ----> consumer B
  partition 3  ----> consumer B
  partition 4  ----> consumer C
  partition 5  ----> consumer C
```

Ba consumer có thể xử lý sáu partition song song, mỗi consumer giữ hai partition. Nếu chỉ có hai partition, thêm consumer thứ ba không làm tăng số luồng đọc đồng thời của group: ít nhất một consumer sẽ không được giao partition.

Tuy nhiên, cân bằng số partition không đồng nghĩa cân bằng tải. Nếu partition 0 nhận 70% record, consumer A vẫn có thể quá tải dù mỗi consumer giữ đúng hai partition. Hãy xem cả số partition được giao lẫn lượng công việc thực tế của từng partition.

## 2. Phân biệt ba dạng mất cân bằng

| Dạng mất cân bằng | Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý chính |
|---|---|---|---|
| Data skew ở producer | Một vài partition có records/bytes cao hơn hẳn | Hot key, key cardinality thấp, partitioner hoặc dữ liệu có phân bố lệch | Thiết kế lại key, routing hoặc cách chia tải. |
| Assignment skew ở consumer | Một consumer giữ nhiều partition hơn hoặc tổng tải được giao lệch | Assignment strategy, nhiều topic với số partition khác nhau, số consumer không phù hợp | Chọn assignor phù hợp, điều chỉnh số partition/consumer. |
| Broker skew | Một broker có leader traffic, disk hoặc network cao hơn | Leader partition tập trung, replica placement hoặc tải client lệch | Reassign partition và cân bằng leader/replica. |

Trước khi thay đổi cấu hình, hãy xác định lớp nào đang gây nghẽn. Ví dụ, đổi `RangeAssignor` sang `RoundRobinAssignor` có thể cân bằng số partition giữa consumer member nhưng không thay đổi việc một hot key tiếp tục ghi vào cùng partition.

## 3. Producer phân phối record vào partition

Khi producer gửi record có key, partitioner mặc định thường dùng hash của key để chọn partition. Các record có cùng key sẽ được định tuyến nhất quán vào cùng partition trong cùng topology partition, nhờ đó Kafka giữ được thứ tự của các record thuộc key đó.

Ví dụ:

```java
kafkaTemplate.send("orders", order.getCustomerId(), order);
```

Nếu một khách hàng tạo phần lớn đơn hàng, partition chứa key của khách hàng đó có thể nóng hơn nhiều partition khác. Nếu key chỉ có vài giá trị như `region`, `status` hoặc một hằng số, lượng record có thể tập trung vào rất ít partition.

Với record không có key, producer partitioner có thể dùng chiến lược phân phối/batching khác. Vì vậy, hãy kiểm tra key thực tế, serializer, partitioner và cấu hình producer trước khi kết luận rằng Kafka đang chia đều record.

### 3.1 Hot key và cardinality thấp

Hot key là một key xuất hiện với tần suất rất cao so với các key còn lại. Ví dụ, một hệ thống có hàng triệu khách hàng nhưng một khách hàng lớn tạo ra 40% tổng sự kiện. Nếu partitioner dùng `customerId`, tất cả record của khách hàng này sẽ đi vào cùng partition.

```text
customerId = C-001  -> partition 2: 40% traffic
customerId = C-002  -> partition 5:  2% traffic
customerId = C-003  -> partition 0:  1% traffic
customerId = C-004  -> partition 4:  1% traffic
other customers    -> các partition còn lại
```

Partition nóng có thể gây:

- Consumer xử lý partition đó có lag tăng liên tục.
- Consumer giữ partition nóng có CPU hoặc thời gian xử lý cao hơn các consumer khác.
- Producer gửi vào partition đó chịu độ trễ cao hoặc batching không hiệu quả.
- Các record của cùng key phải xếp hàng theo thứ tự, làm throughput bị giới hạn bởi một consumer thread.

Tăng số partition không tự giải quyết hot key. Cùng một key vẫn được hash vào một partition trong topology mới; việc tăng partition chỉ có thể làm key được ánh xạ sang partition khác, chứ không chia các record của cùng key ra nhiều partition.

### 3.2 Chọn key theo yêu cầu thứ tự

Key cần phản ánh đơn vị mà nghiệp vụ yêu cầu giữ thứ tự. Nếu cần thứ tự theo đơn hàng, `orderId` có thể phù hợp. Nếu cần thứ tự theo khách hàng, `customerId` là lựa chọn tự nhiên, nhưng một khách hàng có tải rất lớn có thể tạo hot partition.

Không chọn key chỉ để đạt histogram đẹp nếu điều đó phá vỡ ngữ nghĩa nghiệp vụ. Khi chuyển từ `customerId` sang một key khác, các sự kiện của cùng khách hàng có thể nằm ở nhiều partition và được xử lý song song, làm mất thứ tự toàn cục theo khách hàng.

Nếu một key nóng bắt buộc phải giữ thứ tự, cần cân nhắc giới hạn throughput của key đó, tối ưu xử lý, tách riêng tenant lớn hoặc phân luồng bằng một thiết kế nghiệp vụ có bước tổng hợp/tuần tự hóa rõ ràng.

### 3.3 Salting và chia một hot key

Khi nghiệp vụ cho phép xử lý song song các sự kiện của một key, có thể thêm shard/salt vào routing key:

```java
int shard = Math.floorMod(event.getEventId().hashCode(), 8);
String partitionKey = event.getCustomerId() + "-" + shard;

kafkaTemplate.send("customer-events", partitionKey, event);
```

Cách này có thể phân tán tải của một khách hàng qua nhiều partition. Tuy nhiên, các record của khách hàng đó không còn được bảo đảm thứ tự với nhau. Nếu downstream cần trạng thái tổng hợp theo khách hàng, cần có bước merge, versioning hoặc cơ chế đồng bộ phù hợp.

Các lựa chọn khác gồm:

- Tách tenant rất lớn sang topic riêng để cấp số partition và consumer riêng.
- Chia sự kiện theo loại công việc nếu mỗi loại có thể xử lý độc lập.
- Dùng một tầng xử lý trung gian để gom hoặc điều tiết tốc độ của key nóng.
- Giới hạn tốc độ từ nguồn phát để partition nóng không vượt quá khả năng xử lý.

Salting chỉ phù hợp khi semantics cho phép mất thứ tự theo key gốc. Không dùng nó như một thao tác tối ưu thuần kỹ thuật mà không kiểm tra tác động nghiệp vụ.

## 4. Tăng partition có thể làm thay đổi phân bố key

Với partitioner dựa trên hash và số partition, thay đổi số partition có thể làm nhiều key được ánh xạ sang partition khác. Ví dụ, một key trước đây được đưa vào partition 2 của topic có sáu partition có thể được đưa sang partition khác sau khi topic tăng lên mười partition.

Điều này có một số hệ quả:

- Các record mới của cùng key có thể nằm ở partition khác với record cũ.
- Không có thứ tự tổng thể giữa record cũ và mới nếu chúng nằm ở hai partition.
- Consumer group có thể rebalance khi topology thay đổi hoặc khi consumer phát hiện partition mới.
- Stateful processing dựa trên partition ownership có thể cần di chuyển/rebuild state.

Vì vậy, tăng partition là một thay đổi topology cần kế hoạch. Hãy xem xét liệu ứng dụng có dựa vào thứ tự lâu dài theo key, local state theo partition hoặc quy trình replay hay không. Với một key bắt buộc giữ thứ tự qua thời gian, thay đổi số partition cần được kiểm thử và triển khai có kiểm soát.

## 5. Consumer assignment có thể không đều

Kafka consumer group dùng partition assignor để phân chia các partition được subscribe cho các member. Spring Kafka tạo consumer từ listener container; khi cấu hình `concurrency`, một container có thể tạo nhiều consumer thread/member tham gia group.

Ví dụ cấu hình concurrency:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, Order> orderFactory(
        ConsumerFactory<String, Order> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<String, Order>();
    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(6);
    return factory;
}
```

Với một replica ứng dụng, factory trên tạo tối đa sáu consumer cho listener container. Nếu có ba replica dùng cùng group, tổng số member có thể lên tới 18 cho listener đó. Số partition và assignment strategy quyết định member nào nhận partition.

### 5.1 RangeAssignor

`RangeAssignor` chia partition của từng topic thành các dải liên tiếp cho các consumer member. Với một topic, kết quả thường khá cân bằng về số lượng; nếu partition không chia hết cho số consumer, một vài member nhận nhiều hơn một partition.

Vấn đề dễ thấy hơn khi một group subscribe nhiều topic với số partition tương tự. Range assignor phân chia riêng từng topic, vì vậy cùng một member có thể nhận phần dư của nhiều topic.

Ví dụ hai topic `orders` và `payments`, mỗi topic có ba partition, được xử lý bởi hai consumer:

```text
Range assignment (minh họa)

Consumer A: orders-0, orders-1, payments-0, payments-1  -> 4 partitions
Consumer B: orders-2, payments-2                        -> 2 partitions
```

Số partition mỗi member nhận khác nhau dù hai topic có cùng số partition.

### 5.2 RoundRobinAssignor

`RoundRobinAssignor` phân phối lần lượt các partition trên các subscription tương thích của group. Trong ví dụ trên, các partition có thể được xen kẽ để hai consumer nhận số lượng gần bằng nhau:

```text
Round-robin assignment (minh họa)

Consumer A: orders-0, orders-2, payments-1  -> 3 partitions
Consumer B: orders-1, payments-0, payments-2 -> 3 partitions
```

Đây là lựa chọn đáng cân nhắc khi group subscribe nhiều topic và RangeAssignor tạo ra phân bổ lệch về số partition. Tuy nhiên, RoundRobinAssignor vẫn cân bằng số lượng partition, không cân bằng số record, kích thước record hay thời gian xử lý.

### 5.3 CooperativeStickyAssignor

`CooperativeStickyAssignor` cố gắng giữ lại assignment hiện tại khi có thể, đồng thời phân bổ lại partition để cân bằng member khi group thay đổi. Cơ chế cooperative giúp rebalance có thể diễn ra theo từng phần, giảm việc thu hồi toàn bộ partition trong một lần so với eager rebalance.

Assignor này hữu ích khi ứng dụng cần giảm gián đoạn trong quá trình scale hoặc rollout. Tuy nhiên, tính sticky ưu tiên giữ assignment ổn định; nó không tự phát hiện partition có lưu lượng cao và cũng không chia một partition nóng ra nhiều consumer.

### 5.4 Chọn assignor trong Spring Kafka

Có thể cấu hình consumer property `partition.assignment.strategy` qua Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.RoundRobinAssignor
```

Hoặc chọn cooperative sticky nếu phiên bản Kafka client và toàn bộ consumer group hỗ trợ chiến lược này:

```yaml
spring:
  kafka:
    consumer:
      properties:
        partition.assignment.strategy: org.apache.kafka.clients.consumer.CooperativeStickyAssignor
```

Không thay assignor mà không kiểm tra khả năng tương thích giữa các member trong cùng group và phiên bản Kafka client. Khi rollout, các member có thể chạy phiên bản ứng dụng khác nhau trong một khoảng thời gian; cần bảo đảm cấu hình chiến lược assignment tương thích trong giai đoạn chuyển tiếp.

## 6. Concurrency phải khớp với số partition

Với một topic có tám partition, một consumer group có thể xử lý tối đa tám partition đồng thời. Nếu tổng concurrency trên tất cả replica là bốn, một số consumer có thể giữ hai partition. Nếu tổng concurrency là mười hai, ít nhất bốn consumer sẽ không nhận partition của topic đó.

Ví dụ:

| Số partition | Tổng consumer trong group | Hệ quả |
|---:|---:|---|
| 8 | 4 | Mỗi consumer có thể nhận khoảng hai partition. |
| 8 | 8 | Có thể đạt một consumer cho mỗi partition. |
| 8 | 12 | Có consumer không được giao partition. |
| 8 | 2 | Chỉ hai consumer xử lý; mỗi consumer giữ nhiều partition. |

Đây là giới hạn song song theo partition. Nếu tăng concurrency mà throughput không tăng, hãy kiểm tra xem group đã có một consumer cho mỗi partition chưa. Nếu đã đạt giới hạn này, tăng consumer thêm không giúp topic xử lý nhanh hơn; cần tối ưu công việc, thay đổi partitioning hoặc chia luồng nghiệp vụ.

Đừng chỉ nhìn `factory.setConcurrency()` của một instance. Tổng member của group còn phụ thuộc số replica, số listener container dùng cùng group và các listener khác cùng subscribe topic. Số consumer thực tế có thể khác cấu hình dự kiến nếu ứng dụng có nhiều container.

## 7. Broker leader và replica cũng có thể mất cân bằng

Mỗi partition có một leader broker chịu trách nhiệm nhận ghi và phục vụ đọc thông thường; các replica khác sao chép dữ liệu. Nếu nhiều leader partition có tải lớn cùng nằm trên một broker, broker đó có thể bị quá tải dù consumer assignment cân bằng.

Ví dụ:

```text
Broker 1: leader p0, p1, p2, p3  -> nhiều write/read
Broker 2: leader p4             -> ít write/read
Broker 3: leader p5             -> ít write/read
```

Hãy phân biệt:

- **Replica assignment:** partition có bản sao trên broker nào.
- **Leader distribution:** broker nào đang là leader của mỗi partition.
- **Consumer assignment:** consumer group member nào đọc partition.

Đổi consumer assignor không di chuyển leader giữa các broker. Nếu broker leader bị lệch, cần kiểm tra replica placement, preferred leader, partition reassignment và tình trạng broker. Reassignment cần xem xét replication factor, ISR, network và tải disk để tránh gây thêm áp lực lên cluster.

## 8. Đo lường phân bố tải theo partition

Consumer lag tổng của group có thể che giấu partition nóng. Ví dụ, tổng lag là 10.000 record nghe có vẻ ổn định, nhưng nếu 9.500 record nằm ở một partition và các partition còn lại gần bằng 0, một luồng nghiệp vụ có thể đang bị nghẽn.

Theo dõi tối thiểu các chỉ số sau theo topic, partition, consumer member và broker:

| Chỉ số | Ý nghĩa | Cách dùng |
|---|---|---|
| Records in per partition | Số record ghi vào từng partition | Phát hiện producer skew và hot key. |
| Bytes in/out per partition | Lượng byte ghi/đọc | Phát hiện partition có record lớn hoặc tải byte cao. |
| Consumer lag per partition | Khoảng cách giữa log end offset và committed offset | Tìm partition mà consumer không theo kịp. |
| Processing latency per partition | Thời gian xử lý record/batch theo partition | Phân biệt nhiều record với record có nghiệp vụ chậm. |
| Records consumed per member | Số record mỗi consumer xử lý | Phát hiện assignment hoặc tốc độ xử lý lệch. |
| CPU, network, disk theo broker | Tài nguyên broker | Tìm broker leader/replica chịu tải lớn. |
| Rebalance count/duration | Số lần và thời gian rebalance | Phát hiện assignment thay đổi liên tục. |

Nên quan sát cả giá trị tuyệt đối lẫn tỷ lệ. Một partition có lag lớn nhưng đang giảm nhanh có thể ít đáng lo hơn partition có lag nhỏ nhưng tăng đều. Cũng cần phân biệt lag theo offset với lag theo thời gian: record có kích thước và tốc độ đến khác nhau khiến cùng một số offset lag có ý nghĩa vận hành khác nhau.

Log và trace nên chứa topic, partition, offset, key hoặc event ID. Không ghi payload nhạy cảm chỉ để chẩn đoán skew. Nếu cần tìm hot key, có thể thống kê key đã băm hoặc dùng metric có cardinality được kiểm soát thay vì tạo một metric label cho từng key duy nhất.

## 9. Quy trình điều tra partition không đều

Khi một consumer hoặc partition có lag cao, điều tra theo trình tự:

1. **Xem lag theo partition.** Xác định một partition nóng hay tất cả partition đều tăng lag.
2. **So sánh records và bytes in.** Nếu một partition nhận nhiều dữ liệu hơn, điều tra key, partitioner và nguồn phát.
3. **So sánh processing latency.** Nếu lượng record tương đương nhưng thời gian xử lý lệch, xem nghiệp vụ, dependency hoặc kích thước payload.
4. **Kiểm tra consumer assignment.** Xem member nào giữ partition nào và số partition mỗi member nhận.
5. **Kiểm tra số member thực tế.** Đối chiếu concurrency của từng replica, số replica và các container cùng group.
6. **Kiểm tra broker leader.** Nếu một broker có network/disk/CPU cao, xem leader distribution và replica placement.
7. **Xác định giới hạn thứ tự.** Trước khi đổi key hoặc salt, xác định nghiệp vụ có yêu cầu giữ thứ tự theo entity nào.
8. **Thay đổi một yếu tố có kiểm soát.** Điều chỉnh key, assignor, concurrency hoặc topology riêng rẽ để đo tác động.

Ví dụ, nếu partition 3 có lag tăng nhanh, records-in cao và consumer đang giữ partition 3 có throughput gần bằng các consumer khác, khả năng cao nguồn phát đang tạo hot partition. Nếu mọi partition có lượng record tương tự nhưng một consumer giữ bốn partition trong khi member khác chỉ giữ một, hãy kiểm tra assignment strategy và subscription. Nếu consumer lag tương đương nhưng broker 1 có disk latency cao, điều tra broker placement.

## 10. Biện pháp khắc phục theo nguyên nhân

| Nguyên nhân | Biện pháp | Tác động cần cân nhắc |
|---|---|---|
| Hot key do một entity tạo nhiều sự kiện | Tách luồng entity lớn, shard key nếu nghiệp vụ cho phép, hoặc điều tiết tốc độ | Có thể thay đổi thứ tự theo entity; cần bước merge nếu chia shard. |
| Key cardinality thấp | Chọn key có phân bố phù hợp với đơn vị giữ thứ tự | Có thể thay đổi semantics thứ tự và partition mapping. |
| Range assignment lệch giữa nhiều topic | Đánh giá `RoundRobinAssignor` hoặc assignor khác phù hợp | Có thể gây rebalance và cần tương thích cấu hình toàn group. |
| Quá nhiều consumer so với partition | Giảm concurrency/replica hoặc tăng partition có kế hoạch | Tăng partition có thể thay đổi ánh xạ key và topology. |
| Quá ít consumer so với partition | Tăng concurrency/replica đến giới hạn partition | Có thể tăng tải lên broker và dependency. |
| Leader partition tập trung trên broker | Reassign replica và cân bằng leader | Reassignment tiêu thụ network/disk và cần theo dõi ISR. |
| Record lớn hoặc xử lý nặng ở một loại sự kiện | Tách topic hoặc tối ưu payload/processor | Tăng độ phức tạp vận hành và quản lý schema. |

Không áp dụng mọi biện pháp cùng lúc. Hãy thay đổi một yếu tố, đo lại phân bố records/bytes, lag, processing latency và tài nguyên broker, sau đó mới quyết định bước tiếp theo.

## 11. Giữ thứ tự khi tái phân phối dữ liệu

Partition là ranh giới thứ tự của Kafka. Khi đổi key, dùng custom partitioner hoặc tăng số partition, các record của cùng một entity có thể chuyển sang nhiều partition. Consumer group có thể xử lý chúng đồng thời và hoàn tất không theo thứ tự ban đầu.

Trước khi thay đổi routing, trả lời:

- Thứ tự cần bảo đảm là theo event, order, customer, account hay aggregate nào?
- Các sự kiện cùng entity có thể xử lý song song không?
- Nếu dùng shard, hệ thống tổng hợp kết quả và kiểm soát version như thế nào?
- Replay từ topic cũ và topic mới có thể chạy đồng thời không?
- Có cần drain topic cũ hoặc chuyển traffic theo giai đoạn không?

Nếu thứ tự theo key là yêu cầu cứng, hãy giữ key ổn định và tối ưu consumer/processor của partition nóng trước. Nếu có thể nới lỏng thứ tự, hãy thiết kế shard key cùng cơ chế tổng hợp rõ ràng.

## 12. Kiểm thử phân bổ partition

Kiểm thử phân bố cần dùng dữ liệu đại diện. Một test chỉ gửi vài record với key ngẫu nhiên không thể phát hiện hot key trong production.

Các kịch bản nên có:

1. Gửi một tập record có cardinality key cao và đo số record/byte theo partition.
2. Gửi dữ liệu có một hot key chiếm tỷ lệ lớn và xác nhận metric phát hiện partition nóng.
3. Chạy consumer group với nhiều topic và số partition khác nhau; so sánh assignment của RangeAssignor và RoundRobinAssignor.
4. Đặt concurrency thấp hơn, bằng và cao hơn số partition; quan sát member nào nhận partition và member nào idle.
5. Tăng partition trong môi trường thử nghiệm; kiểm tra mapping key, thứ tự theo entity và rebalance.
6. Tạo leader distribution lệch có kiểm soát; quan sát tải broker và kiểm tra quy trình reassignment.
7. Replay dữ liệu sau khi đổi routing; xác nhận idempotency, versioning và thứ tự nghiệp vụ.

Nên chờ điều kiện cụ thể và dùng timeout hữu hạn trong integration test. Với phân tích skew, dùng đủ số lượng record để histogram có ý nghĩa và giữ seed dữ liệu cố định để có thể so sánh trước/sau thay đổi.

## 13. Những sai lầm thường gặp

- **Chỉ tăng concurrency khi lag cao:** nếu một partition nóng, thêm consumer không thể chia partition đó thành nhiều consumer.
- **Chỉ nhìn tổng lag:** lag tổng che giấu partition bị nghẽn.
- **Cho rằng số partition bằng nhau nghĩa là tải bằng nhau:** key skew và kích thước record có thể làm tải lệch lớn.
- **Dùng RoundRobinAssignor để xử lý hot key:** assignor chỉ phân chia partition cho member, không thay đổi partitioner của producer.
- **Tăng partition mà không đánh giá thứ tự:** key có thể được ánh xạ sang partition khác và làm thay đổi thứ tự theo thời gian.
- **Salting key mà không có bước merge:** sự kiện của cùng entity có thể hoàn tất không theo thứ tự.
- **Nhầm consumer assignment với broker leader distribution:** hai lớp cần công cụ và biện pháp khác nhau.
- **Tăng số consumer vượt số partition:** consumer dư không tạo thêm khả năng song song cho topic.
- **Đổi assignor đồng loạt mà không kiểm tra compatibility:** các member cùng group có thể không thống nhất chiến lược assignment trong giai đoạn rollout.

## 14. Cách thiết kế phân bổ partition cho production

Một thiết kế ổn định bắt đầu từ yêu cầu thứ tự và tải dự kiến. Chọn key theo entity cần giữ thứ tự; ước lượng số partition theo throughput và mức song song mong muốn; đặt concurrency tổng thể phù hợp với số partition; chọn assignor theo topology subscription; và phân bố replica/leader trên broker để tránh điểm nóng.

Sau triển khai, theo dõi records, bytes, lag và processing latency theo partition. Khi thấy skew, xác định đó là producer, consumer assignment hay broker skew trước khi thay đổi. Với hot key, cân nhắc kỹ tác động của salting và partition expansion lên thứ tự. Với assignment skew, kiểm tra số member và assignor. Với broker skew, xem leader/replica placement.

Mục tiêu không phải làm mọi partition có số record tuyệt đối giống nhau. Mục tiêu là phân phối công việc trong giới hạn nghiệp vụ, giữ được thứ tự cần thiết và bảo đảm không có partition, consumer hoặc broker nào trở thành nút thắt kéo dài.
