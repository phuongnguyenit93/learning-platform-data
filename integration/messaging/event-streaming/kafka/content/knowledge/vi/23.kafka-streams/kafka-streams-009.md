# Repartition topic và điều kiện phát sinh phân vùng lại

Kafka Streams chia topology thành các task dựa trên partition của topic đầu vào. Mỗi task xử lý một hay nhiều partition và giữ state cục bộ cho các key mà task sở hữu. Muốn aggregation hoặc join theo một key, mọi record có cùng key phải được đưa về cùng partition để cùng một task xử lý.

Vấn đề xuất hiện khi key hiện tại của record không còn phù hợp với partition đang chứa record. Ví dụ topic đầu vào được partition theo orderId, nhưng ứng dụng muốn đếm đơn hàng theo customerId. Hai đơn hàng của cùng khách hàng có thể nằm ở hai partition khác nhau. Nếu mỗi task tự cộng vào state cục bộ, kết quả sẽ bị chia nhỏ và không tạo ra một phép đếm toàn cục theo customerId.

Kafka Streams giải quyết việc này bằng repartition topic: một topic nội bộ nhận record sau khi key được xác định lại, rồi phân phối record theo key mới. Các task phía sau đọc topic đó và xử lý những record cùng key trên cùng partition.

Bài viết tập trung vào điều kiện cần repartition, cách Kafka Streams tự động chèn repartition, cách yêu cầu repartition tường minh và những hệ quả về partition count, Serde, ordering, hiệu năng và vận hành.

## 1. Vì sao cần phân vùng lại?

Một topic Kafka được chia thành nhiều partition. Producer chọn partition cho record, thường dựa trên key đã serialize và partitioner. Kafka Streams tạo các task dựa trên partition của các source topic.

Ví dụ topic orders có sáu partition:

~~~text
orders
  P0: order-10, order-18, order-25
  P1: order-11, order-19, order-26
  P2: order-12, order-20, order-27
  P3: order-13, order-21, order-28
  P4: order-14, order-22, order-29
  P5: order-15, order-23, order-30
~~~

Giả sử producer dùng orderId làm key. Kafka phân phối các orderId trên sáu partition. Ứng dụng cần tổng hợp số đơn hàng theo customerId. CustomerId nằm trong value:

~~~json
{
  "orderId": "order-10",
  "customerId": "customer-7",
  "amount": 250000
}
~~~

Hai record của customer-7 có thể nằm ở hai partition khác nhau:

~~~text
orders
  P0: order-10, customer-7
  P4: order-22, customer-7
~~~

Mỗi task chỉ nhìn thấy partition được giao cho nó. Nếu aggregation theo customerId chạy trực tiếp trên phân bố cũ, cùng customer có thể được đếm ở nhiều state store khác nhau.

Cần chuyển key từ orderId sang customerId rồi phân phối lại:

~~~text
Input topic, partition theo orderId
             |
             v
       selectKey(customerId)
             |
             v
       repartition topic
       partition theo customerId
             |
       +-----+-----+
       |           |
       v           v
      P1          P4
  customer-7   customer-8
       |
       v
  Aggregation theo customerId
~~~

Sau repartition, các record có cùng customerId được gửi tới cùng partition của repartition topic theo partitioning strategy đang dùng. Nhờ đó một task có thể duy trì một state nhất quán cho key đó.

### 1.1. Key thay đổi chưa có nghĩa record đã chuyển partition

Một thao tác như selectKey() tạo key mới cho record trong topology. Record vẫn đang ở luồng xử lý và task hiện tại tại thời điểm thao tác đó. Việc đổi key trong bộ nhớ không tự di chuyển record giữa các task.

Kafka Streams đánh dấu luồng cần repartition khi dùng một số thao tác đổi key của DSL. Khi một thao tác phía sau cần dữ liệu được phân phối theo key mới, framework chèn producer và consumer qua một internal topic.

Đây là lý do cần phân biệt:

- **Re-key:** thay đổi giá trị key gắn với record.
- **Repartition:** ghi record sang topic trung gian để partition lại theo key/partitioner.
- **Scale out:** tăng số instance hoặc thread để xử lý nhiều task hơn.
- **Tăng partition của topic:** thay đổi số partition của một topic Kafka đã tồn tại.

Bốn việc này có liên quan nhưng không đồng nghĩa với nhau.

## 2. Repartition topic là gì?

Repartition topic là topic nội bộ do Kafka Streams quản lý để chuyển record từ một phân bố partition hiện tại sang phân bố mới.

Luồng điển hình:

1. Task upstream xử lý record và xác định key mới.
2. Record được serialize bằng key/value Serde tương ứng.
3. Producer nội bộ ghi record vào repartition topic.
4. Partitioner chọn partition dựa trên key hoặc cấu hình tùy chỉnh.
5. Task downstream đọc partition tương ứng.
6. Grouping, aggregation hoặc join tiếp tục với dữ liệu đã được phân phối lại.

Repartition topic là một điểm nối vật lý trong topology. Dữ liệu đi qua Kafka broker nên có chi phí serialization, network, disk I/O, replication và consumer fetch.

### 2.1. Repartition topic khác changelog topic

Cả hai đều là internal topic nhưng có mục đích khác nhau.

| Tiêu chí | Repartition topic | Changelog topic |
|---|---|---|
| Mục đích | Phân phối lại record theo key/partition | Khôi phục state store |
| Dữ liệu | Record đang đi qua topology | Thay đổi của state store |
| Nơi được đọc | Downstream task trong topology | State restoration |
| Cleanup policy mặc định | delete | compact với key-value store thông thường |
| Vai trò | Transport giữa các sub-topology | Durability của local state |
| Tạo khi nào | Cần repartition trong topology | Có state store cần changelog, trừ khi cấu hình khác |

Không dùng changelog topic để thay thế repartition topic. Changelog lưu lịch sử thay đổi state theo key; repartition topic mang record đến task sở hữu key mới.

### 2.2. Repartition topic là internal resource

Tên topic thường có dạng:

~~~text
<application.id>-<operator-name>-repartition
~~~

Phần operator-name có thể được Kafka Streams sinh tự động hoặc lấy từ tên do ứng dụng cung cấp. Quy tắc tên nội bộ có thể thay đổi giữa các phiên bản; hãy dùng Topology.describe() hoặc metadata của cluster để kiểm tra tên thực tế.

Repartition topic thuộc về một Kafka Streams application có application.id tương ứng. Ứng dụng không nên xem topic này như public API để service khác subscribe hoặc ghi dữ liệu trực tiếp.

## 3. Khi nào Kafka Streams tự động repartition?

Kafka Streams DSL theo dõi một số thao tác làm thay đổi key và đánh dấu stream cần repartition trước các thao tác downstream cần phân phối theo key.

Các thao tác thường gặp:

| Thao tác | Tác động đến key | Repartition |
|---|---|---|
| selectKey() | Gán key mới | Đánh dấu cần repartition cho grouping/join phía sau |
| map() | Có thể đổi key và value | Đánh dấu cần repartition cho grouping/join phía sau |
| groupBy() | Tạo key grouping mới | Luôn yêu cầu repartition |
| groupByKey() | Dùng key hiện tại | Chỉ repartition nếu stream đã được đánh dấu |
| mapValues() | Chỉ đổi value, giữ key | Không tự đánh dấu repartition |
| filter() | Bỏ record, giữ key | Không tự đánh dấu repartition |
| peek() | Quan sát record, không đổi key | Không tự đánh dấu repartition |
| repartition() | Chủ động ghi và đọc internal topic | Luôn repartition |

Bảng mô tả semantics của DSL. Các thao tác Processor API tùy chỉnh không nhất thiết được DSL nhận diện là đã đổi key; khi cần bảo đảm phân phối lại, hãy gọi repartition() tường minh.

### 3.1. selectKey() rồi groupByKey()

Đây là trường hợp phổ biến nhất. Topic orders đang partition theo orderId. Ứng dụng cần aggregation theo customerId:

~~~java
KStream<String, OrderEvent> orders =
    builder.stream(
        "orders",
        Consumed.with(Serdes.String(), orderEventSerde)
    );

KStream<String, OrderEvent> byCustomer =
    orders.selectKey(
        (orderId, event) -> event.customerId()
    );

KTable<String, Long> orderCounts =
    byCustomer
        .groupByKey(
            Grouped.with(
                Serdes.String(),
                orderEventSerde
            )
        )
        .count();

orderCounts
    .toStream()
    .to(
        "customer-order-counts",
        Produced.with(
            Serdes.String(),
            Serdes.Long()
        )
    );
~~~

Giải thích:

- Source stream có key là orderId.
- selectKey() đổi key thành customerId.
- Kafka Streams đánh dấu stream cần repartition.
- groupByKey() yêu cầu các record cùng key được xử lý cùng nơi.
- Framework chèn repartition topic trước aggregation.
- count() duy trì số lượng theo customerId trong state store.
- KTable đầu ra biểu diễn giá trị mới nhất của từng customerId.

Nếu bỏ qua repartition, các record customerId giống nhau có thể được xử lý trên các task khác nhau dựa trên partition orderId cũ.

### 3.2. groupBy() luôn repartition

groupBy() cho phép tạo grouping key mới ngay trong lời gọi:

~~~java
KTable<String, Long> orderCounts =
    orders
        .groupBy(
            (orderId, event) -> event.customerId(),
            Grouped.with(
                Serdes.String(),
                orderEventSerde
            )
        )
        .count();
~~~

groupBy() luôn gây repartition vì nó nhóm theo một key được tính từ mapper. Nếu key đầu vào đã đúng và chỉ muốn nhóm theo key hiện tại, groupByKey() thường phù hợp hơn.

### 3.3. groupByKey() chỉ repartition khi cần

~~~java
KTable<String, Long> counts =
    orders
        .groupByKey()
        .count();
~~~

Nếu source topic đã partition theo key đang dùng và stream chưa có thao tác đổi key trước đó, Kafka Streams không cần tạo repartition topic chỉ để group.

Nếu stream đã đi qua selectKey() hoặc thao tác DSL đánh dấu key thay đổi, groupByKey() sẽ là điểm kích hoạt repartition.

Điều này giúp tránh ghi/đọc Kafka trung gian khi partition mapping hiện tại đã đúng.

### 3.4. mapValues() giữ key nên thường không cần repartition

~~~java
KStream<String, EnrichedOrder> enriched =
    orders.mapValues(
        event -> new EnrichedOrder(
            event.orderId(),
            event.customerId(),
            event.amount(),
            "NORMALIZED"
        )
    );
~~~

mapValues() giữ nguyên key. Nếu key ban đầu đã là orderId và downstream vẫn xử lý theo orderId, không cần repartition chỉ vì value được chuyển đổi.

Nếu cần grouping theo customerId, đổi key bằng selectKey() hoặc groupBy() và để DSL/ứng dụng thực hiện repartition ở điểm phù hợp.

## 4. Tại sao đổi key trước aggregation hoặc join?

Aggregation theo key cần một điểm state duy nhất cho mỗi key trong cùng partition. Join theo key cần hai phía có cùng key nằm trên cùng partition number để task có thể ghép dữ liệu cục bộ.

### 4.1. Aggregation cần co-location

Giả sử customer-7 có 100 đơn hàng:

~~~text
Trước repartition:
orders P0 -> customer-7: 20 records
orders P1 -> customer-7: 30 records
orders P2 -> customer-7: 50 records

Sau repartition:
orders-by-customer P3 -> customer-7: 100 records
~~~

Sau khi dữ liệu được phân phối theo customerId, một task sở hữu partition P3 có thể cập nhật một state store cho customer-7.

### 4.2. Join cần co-partitioning

Với KStream-KStream, KStream-KTable và KTable-KTable joins thông thường, dữ liệu đầu vào phải co-partitioned.

Co-partitioning có hai điều kiện cốt lõi:

1. Hai topic đầu vào có cùng số partition.
2. Các producer dùng cùng partitioning strategy để cùng key đi vào cùng partition number.

Ví dụ:

~~~text
orders-by-customer              customers-by-id
P0: customer-1                  P0: customer-1
P1: customer-2                  P1: customer-2
P2: customer-3                  P2: customer-3
P3: customer-4                  P3: customer-4
~~~

Khi customer-2 xuất hiện ở partition P1 của cả hai topic, task xử lý P1 có thể thực hiện join cục bộ.

Nếu một topic có 4 partition và topic còn lại có 8 partition, hoặc partitioner phân phối cùng key khác nhau, join có thể bị từ chối hoặc tạo kết quả không đúng như mong đợi.

KTable-KTable foreign-key join và GlobalKTable join có semantics riêng, không áp dụng cùng yêu cầu co-partitioning như các join thông thường. Cần xem đúng loại join đang sử dụng.

### 4.3. Ví dụ repartition hai luồng trước join

~~~java
KStream<String, OrderEvent> ordersByCustomer =
    orders
        .selectKey(
            (orderId, event) -> event.customerId()
        )
        .repartition(
            Repartitioned.<String, OrderEvent>as(
                "orders-by-customer"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(orderEventSerde)
            .withNumberOfPartitions(12)
        );

KStream<String, CustomerEvent> customersByCustomer =
    customers
        .selectKey(
            (customerId, event) -> event.customerId()
        )
        .repartition(
            Repartitioned.<String, CustomerEvent>as(
                "customers-by-customer"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(customerEventSerde)
            .withNumberOfPartitions(12)
        );

KStream<String, EnrichedOrder> enriched =
    ordersByCustomer.join(
        customersByCustomer,
        (order, customer) ->
            new EnrichedOrder(order, customer),
        JoinWindows.ofTimeDifferenceWithNoGrace(
            Duration.ofMinutes(5)
        ),
        StreamJoined.with(
            Serdes.String(),
            orderEventSerde,
            customerEventSerde
        )
    );
~~~

Hai repartition topic được yêu cầu có 12 partition. Cùng key customerId được gửi theo partitioner tương thích. Với ví dụ dùng default partitioner và cùng key Serde, hai luồng có thể co-partition nếu không có cấu hình partitioner khác.

Không chỉ nhìn số partition. Nếu một phía dùng custom partitioner và phía còn lại dùng default partitioner, cùng key vẫn có thể nằm ở partition khác nhau.

### 4.4. Repartition và thứ tự record

Repartition không sắp xếp record theo event timestamp và cũng không tạo ra thứ tự toàn cục giữa các partition.

- Trong một source partition, record được đọc theo thứ tự offset. Producer nội bộ chuyển chúng sang repartition topic theo luồng xử lý của task.
- Nếu cùng key mới đến từ nhiều source partition khác nhau, các record được hợp nhất vào một destination partition theo thứ tự chúng đến producer của partition đó. Không có thứ tự nghiệp vụ toàn cục được bảo đảm giữa các source partition.
- Sau repartition, các record cùng key nằm trên cùng destination partition và downstream xử lý chúng theo thứ tự append/offset của partition đó.
- Event đến muộn hoặc event được phát từ nhiều partition có thể xuất hiện theo thứ tự khác với timestamp nghiệp vụ.

Ví dụ, order-10 và order-22 vốn ở hai source partition khác nhau nhưng cùng được đổi key thành customer-7. Repartition đưa cả hai về cùng partition mới, nhưng thứ tự giữa chúng phản ánh thứ tự gửi tới partition đích, không nhất thiết là order-10 trước order-22 theo thời gian tạo đơn.

Nếu nghiệp vụ cần thứ tự theo version hoặc sequence, đưa sequence/version vào event và kiểm tra nó trong processor/aggregation. Không dùng repartition như một cơ chế sort hoặc event-time ordering.

## 5. Repartition tường minh bằng Repartitioned

DSL có thể tự chèn repartition khi phát hiện key-changing operation tiếp theo cần grouping/join. Trong một số trường hợp, ứng dụng cần chủ động quyết định vị trí và cấu hình repartition.

KStream.repartition() luôn tạo điểm repartition, ngay cả khi framework không tự yêu cầu.

### 5.1. Chỉ định tên internal topic

~~~java
KStream<String, OrderEvent> repartitioned =
    byCustomer.repartition(
        Repartitioned.<String, OrderEvent>as(
            "orders-by-customer"
        )
    );
~~~

Tên được dùng làm phần tên của processor và repartition topic. Tên tường minh giúp topology dễ đọc và thuận tiện khi điều tra.

Tên nội bộ cuối cùng còn gắn với application.id và hậu tố do Kafka Streams quản lý.

### 5.2. Chỉ định số partition

~~~java
KStream<String, OrderEvent> repartitioned =
    byCustomer.repartition(
        Repartitioned.<String, OrderEvent>as(
            "orders-by-customer"
        )
        .withNumberOfPartitions(12)
    );
~~~

Số partition xác định mức độ song song tối đa của downstream sub-topology theo topic này. Chọn số partition theo throughput, key cardinality, số task mong muốn, kích thước state và tài nguyên cluster.

Tăng partition count không làm một key được xử lý song song hơn. Tất cả record cùng key vẫn cần đi cùng partition để giữ semantics aggregation/join.

### 5.3. Chỉ định key/value Serde

~~~java
KStream<String, OrderEvent> repartitioned =
    byCustomer.repartition(
        Repartitioned.<String, OrderEvent>as(
            "orders-by-customer"
        )
        .withKeySerde(Serdes.String())
        .withValueSerde(orderEventSerde)
    );
~~~

Serde của repartition topic cần khớp với kiểu key/value tại điểm repartition. Nếu default Serde của application không tương thích với kiểu mới sau selectKey() hoặc map(), cần chỉ định Serde tường minh.

Lỗi Serde có thể xuất hiện khi serialize trước khi ghi repartition topic hoặc deserialize khi downstream đọc topic.

### 5.4. Chỉ định StreamPartitioner

Có thể cung cấp StreamPartitioner riêng khi cần quy tắc phân phối đặc biệt:

~~~java
KStream<String, OrderEvent> repartitioned =
    byCustomer.repartition(
        Repartitioned.<String, OrderEvent>as(
            "orders-by-customer"
        )
        .withKeySerde(Serdes.String())
        .withValueSerde(orderEventSerde)
        .withNumberOfPartitions(12)
        .withStreamPartitioner(customerPartitioner)
    );
~~~

Custom partitioner phải được thiết kế nhất quán trên tất cả các luồng cần co-partition. Nếu hai phía của join dùng thuật toán khác nhau, cùng key có thể không nằm cùng partition.

Chỉ dùng custom partitioner khi có yêu cầu cụ thể như kiểm soát routing theo tenant hoặc tương thích với partitioning strategy đã tồn tại. Partitioner tùy chỉnh làm tăng trách nhiệm kiểm thử và bảo trì.

## 6. Điều kiện phát sinh repartition trong topology

Có thể đọc topology theo chuỗi operation:

~~~text
Source
  |
  v
selectKey()
  |
  |  Stream được đánh dấu cần repartition
  v
filter()
  |
  v
groupByKey()
  |
  v
Repartition source/sink
  |
  v
Aggregation
  |
  v
State store + changelog
~~~

Một số trường hợp điển hình:

| Chuỗi thao tác | Có repartition? | Lý do |
|---|---|---|
| stream → groupByKey → count | Thường không nếu key source đã đúng | Group theo key hiện tại |
| stream → selectKey → groupByKey → count | Có | Key đã thay đổi |
| stream → groupBy → count | Có | Group theo key mapper mới |
| stream → mapValues → groupByKey | Không phát sinh chỉ do mapValues | Key không đổi |
| stream → filter → groupByKey | Không phát sinh chỉ do filter | Key không đổi |
| stream → selectKey → filter → groupByKey | Có | Cờ key-changing vẫn cần được xử lý |
| stream → repartition → aggregate | Có | repartition() luôn materialize internal topic |
| stream → Processor API đổi key → aggregate | Không nên giả định tự động | Processor API tùy chỉnh có thể không đánh dấu key change cho DSL |

### 6.1. Processor API và key-changing operation

Khi dùng Processor API, ứng dụng có thể tạo record mới bằng ProcessorContext.forward() hoặc API tương ứng của phiên bản đang dùng. DSL không nhất thiết biết processor tùy chỉnh đã đổi key.

Nếu sau processor cần grouping hoặc join theo key mới, gọi repartition() rõ ràng:

~~~java
KStream<String, OrderEvent> processed =
    source.process(
        OrderEnrichmentProcessor::new
    );

KStream<String, OrderEvent> correctlyPartitioned =
    processed.repartition(
        Repartitioned.<String, OrderEvent>as(
            "after-custom-processor"
        )
        .withKeySerde(Serdes.String())
        .withValueSerde(orderEventSerde)
    );

KTable<String, Long> counts =
    correctlyPartitioned
        .groupByKey(
            Grouped.with(
                Serdes.String(),
                orderEventSerde
            )
        )
        .count();
~~~

Ví dụ minh họa vị trí cần repartition. Processor implementation và generic signature cần khớp Kafka Streams version của project.

## 7. Chọn partition count cho repartition topic

Số partition tác động trực tiếp đến mức song song và phân bố state.

Các yếu tố cần cân nhắc:

- Throughput đầu vào và throughput xử lý trên mỗi task.
- Số lượng key khác nhau.
- Mức độ skew của key.
- Số stream thread và instance dự kiến.
- Kích thước state store.
- Tần suất rebalance và chi phí restore.
- Khả năng chịu tải của broker.
- Số partition của các topic cần join.

### 7.1. Số partition không phải số thread

Nếu repartition topic có 12 partition, downstream sub-topology có tối đa 12 task tương ứng với các partition đó. Số thread thực tế có thể ít hơn hoặc bằng số task đang được phân công.

Ví dụ:

| Repartition partitions | Stream threads | Ý nghĩa |
|---:|---:|---|
| 3 | 1 | Một thread có thể xử lý nhiều task |
| 6 | 3 | Có thể phân bổ khoảng hai task mỗi thread |
| 12 | 6 | Có thể phân bổ khoảng hai task mỗi thread |
| 12 | 16 | Một số thread không có task từ sub-topology này |

Số task thực tế còn phụ thuộc source topics, topology và assignment. Không dùng công thức số thread = số partition cho mọi topology.

### 7.2. Tăng partition count không chia nhỏ một key nóng

Nếu một customerId tạo 40% traffic, mọi record của customerId đó vẫn đi vào cùng partition theo semantics grouping. Tăng từ 12 lên 24 partition có thể giúp các key khác phân bố rộng hơn, nhưng không tự chia customerId nóng thành nhiều task.

Cách giải quyết hot key cần thay đổi mô hình nghiệp vụ, ví dụ:
- Chia key thành shard có kiểm soát rồi thực hiện bước tổng hợp cuối.
- Dùng hai tầng aggregation.
- Tách tenant lớn sang luồng riêng.
- Giảm payload hoặc chi phí xử lý mỗi record.

Việc thêm suffix ngẫu nhiên vào key có thể phá vỡ aggregation theo key gốc nếu không có bước hợp nhất sau đó.

### 7.3. Partition count của join

Hai đầu vào của join thông thường phải co-partition. Nếu một bên có 12 partition và bên kia 6, chỉ tăng concurrency không sửa được khác biệt này.

Có thể repartition cả hai stream về cùng số partition và cùng partitioner. Nếu topic được ghi bởi các ứng dụng khác nhau, cần bảo đảm producer của chúng dùng cùng key encoding và partitioning strategy.

### 7.4. Thay đổi partition count sau khi triển khai

Không xem việc tăng partition của source topic như một thay đổi vô hại. Nó có thể ảnh hưởng:
- Key-to-partition mapping của producer.
- Co-partitioning của joins.
- Số task và assignment.
- Internal repartition topic đã được tạo trước đó.
- State store placement và thời gian restore.

Repartition topic là internal resource được tạo theo topology và metadata lúc khởi tạo. Khi thay đổi partition count của upstream topic hoặc topology, hãy kiểm tra trạng thái internal topic và compatibility với Kafka Streams version. Không tự tăng partition của internal topic bằng lệnh quản trị nếu chưa có kế hoạch topology/recovery rõ ràng.

## 8. Serde và partitioner quyết định mapping

Repartition không chỉ dựa trên object key trong Java. Key phải được serialize thành byte trước khi producer chọn partition.

Ví dụ hai key Java đều hiển thị là customer-42 nhưng được serialize khác nhau:

~~~text
Serde A: UTF-8("customer-42")
Serde B: JSON({"id":"customer-42"})
~~~

Byte khác nhau có thể dẫn tới partition khác nhau.

Vì vậy, với các stream cần co-partition:
- Dùng cùng key type.
- Dùng cùng key serialization format.
- Dùng cùng partitioner hoặc thuật toán tương đương.
- Dùng cùng số partition.
- Không chuẩn hóa key khác nhau giữa các producer.
- Kiểm thử key bytes và partition assignment.

Value Serde cũng quan trọng vì repartition topic phải serialize value để truyền qua Kafka, nhưng value Serde không quyết định partition khi partitioner chỉ dựa trên key.

### 8.1. Null key

Aggregation/grouping theo key cần key hợp lệ. Record có null key thường không thể được phân phối theo key như mong muốn và có thể bị bỏ qua ở các thao tác grouping. Hãy xác định rõ chính sách:
- Loại bỏ record không có customerId.
- Gửi sang topic quarantine riêng.
- Tạo key thay thế có semantics rõ ràng.
- Ghi metric để theo dõi tỷ lệ key null.

Không gán một key mặc định chung cho mọi record lỗi nếu điều đó khiến chúng dồn vào một partition và tạo hot key.

## 9. Internal topic được tạo và quản lý như thế nào?

Kafka Streams tự quản lý repartition topic. Ứng dụng không cần tự tạo topic bằng AdminClient cho mỗi toán tử DSL thông thường.

Các đặc điểm chính:

- Topic được tạo theo application.id và tên processor/repartition.
- Số partition mặc định dựa trên partition count của upstream topics; có thể chỉ định rõ qua Repartitioned.
- Repartition topic là internal topic dành cho application đó.
- Dữ liệu được ghi rồi đọc bởi các sub-topology.
- Kafka Streams quản lý việc purge record đã được tiêu thụ.
- Topic thường dùng cleanup.policy=delete và retention time vô hạn, vì framework quản lý việc xóa record đã xử lý.
- Không dùng repartition topic làm kho lưu trữ lâu dài.

### 9.1. Replication factor

Repartition topic vẫn là Kafka topic nên chịu ảnh hưởng của broker failure. Kafka Streams cung cấp cấu hình replication.factor cho các internal topics.

~~~java
Properties props = new Properties();

props.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "order-analytics"
);
props.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "kafka-1:9092,kafka-2:9092,kafka-3:9092"
);
props.put(
    StreamsConfig.REPLICATION_FACTOR_CONFIG,
    3
);
~~~

Replication factor bằng 3 tăng khả năng chịu lỗi broker nhưng cần thêm disk/network. Cần kết hợp với broker count, min.insync.replicas và producer acknowledgments theo chính sách durability của cluster.

Ở các phiên bản Kafka cũ, default replication factor của internal topics có thể khác. Từ các broker version hỗ trợ default replication factor phù hợp, giá trị -1 có thể dùng broker default. Với production, đặt rõ replication factor sau khi kiểm tra Kafka Streams và broker version.

### 9.2. ACL cho internal topics

Khi bật security, Kafka Streams client cần quyền tạo và sử dụng internal topics. Tùy cấu hình cluster, cần cấp quyền phù hợp cho:
- Tạo repartition topic.
- Ghi và đọc repartition topic.
- Đọc metadata và mô tả topic.
- Tạo changelog topic nếu topology có state store.
- Thực hiện các thao tác quản trị cần thiết cho internal resources.

Lỗi ACL có thể khiến application không khởi động hoặc task không thể tiến triển. Không cấp quyền rộng cho mọi topic nếu chỉ cần quyền với namespace của application.

### 9.3. Purge và retention

Repartition topic thường có retention vô hạn vì Kafka Streams cần dữ liệu cho đến khi downstream tiêu thụ. Framework sẽ purge các record đã được xử lý theo cơ chế internal topic.

Cấu hình **repartition.purge.interval.ms** điều khiển tần suất purge các record đã tiêu thụ hoàn toàn. Giá trị mặc định thường là 30 giây trong các phiên bản hiện đại, nhưng cần xác minh theo version.

Không thay cleanup policy hoặc retention của repartition topic bằng chính sách thông thường của business topic nếu chưa hiểu lifecycle nội bộ. Xóa record chưa được tiêu thụ có thể làm topology mất dữ liệu đang chờ xử lý.

## 10. Chi phí hiệu năng của repartition

Mỗi repartition thêm một lượt ghi và đọc qua Kafka. Với throughput lớn, đây có thể là một phần đáng kể của tổng chi phí xử lý.

Các chi phí thường gặp:

1. Serialize key và value.
2. Producer gửi record tới broker.
3. Broker append log và replicate.
4. Consumer downstream fetch record.
5. Deserialize key và value.
6. Task scheduling và context switching.
7. Disk, network và page cache sử dụng thêm.

Ví dụ một luồng có 100.000 record/giây và mỗi record trung bình 1 KB. Repartition tạo thêm lưu lượng nội bộ cỡ hàng trăm MB/s trước khi tính overhead protocol và replication. Con số thực tế phụ thuộc compression, batching, kích thước record và broker topology.

### 10.1. Tránh repartition không cần thiết

- Dùng groupByKey() khi key hiện tại đã đúng.
- Dùng mapValues() nếu chỉ cần đổi value.
- Không gọi repartition() lặp lại nếu không có thay đổi partitioning cần thiết.
- Đặt key đúng từ producer nếu có thể.
- Dùng cùng key/partitioning strategy cho các topic sẽ join.
- Kiểm tra topology để phát hiện repartition topic dư thừa.

### 10.2. Compression và batching

Internal producer/consumer sử dụng cấu hình Kafka Streams và các cấu hình producer/consumer tương ứng. Có thể tối ưu compression, batch size, linger và fetch settings sau khi đo tải thực tế.

Không tăng batch hoặc buffer một cách tùy tiện. Repartition là đường nội bộ của topology; thay đổi cấu hình có thể ảnh hưởng latency, memory và thời gian xử lý task.

### 10.3. Topology optimization

Kafka Streams có topology optimization nhằm loại bỏ hoặc hợp nhất một số bước không cần thiết, bao gồm các cơ hội giảm repartition topic trong topology phù hợp.

Có thể bật tối ưu hóa khi build topology:

~~~java
Properties props = new Properties();

props.put(
    StreamsConfig.TOPOLOGY_OPTIMIZATION_CONFIG,
    StreamsConfig.OPTIMIZE
);

Topology topology = builder.build(props);
KafkaStreams streams = new KafkaStreams(topology, props);
~~~

Cấu hình optimization phải được truyền vào overload build(Properties) để topology builder áp dụng tối ưu hóa. Chỉ đặt property khi gọi KafkaStreams mà build topology bằng overload không có Properties có thể không tạo ra topology tối ưu như mong muốn.

Sau khi bật optimization, kiểm tra Topology.describe() và kiểm thử semantics. Không giả định mọi repartition đều có thể loại bỏ; một số repartition là cần thiết để bảo đảm grouping/join đúng.

## 11. Quan sát topology và xác nhận repartition

Dùng Topology.describe() để xem các sub-topology, source, processor, sink và internal topic:

~~~java
StreamsBuilder builder = new StreamsBuilder();

// Xây dựng các stream operations ở đây.

Topology topology = builder.build();

System.out.println(topology.describe());
~~~

Trong topology description, tìm các thành phần:
- Sink node ghi vào repartition topic.
- Source node đọc lại repartition topic.
- Processor node phía sau grouping hoặc join.
- Tên internal topic được sinh hoặc đặt tường minh.

Topology description giúp phát hiện một repartition topic được chèn ngoài dự kiến hoặc một key-changing operation chưa có điểm repartition trước stateful operation.

### 11.1. Kiểm tra trên Kafka cluster

Có thể liệt kê topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --list
~~~

Mô tả một internal topic:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-1:9092 \
  --describe \
  --topic order-analytics-orders-by-customer-repartition
~~~

Tên topic trong lệnh chỉ là ví dụ. Hãy lấy tên thực tế từ Topology.describe() hoặc metadata của cluster.

Kiểm tra:
- Partition count.
- Leader và replicas.
- ISR.
- Topic config.
- Throughput và log size.
- ACL.
- Consumer lag của downstream task nếu metric có thể hiện.

Không chỉnh sửa hoặc xóa internal topic bằng tay chỉ vì tên của nó xuất hiện trong danh sách. Kafka Streams sở hữu lifecycle của topic này.

## 12. Kiểm thử repartition

Kiểm thử cần chứng minh record cùng key được đưa tới đúng downstream state/partition semantics, và Serde có thể serialize/deserialize thành công.

### 12.1. TopologyTestDriver

TopologyTestDriver hữu ích để kiểm thử logic DSL mà không cần broker thật:

~~~java
@Test
void shouldAggregateOrdersByCustomer() {
    StreamsBuilder builder = new StreamsBuilder();

    KStream<String, OrderEvent> orders =
        builder.stream(
            "orders",
            Consumed.with(Serdes.String(), orderEventSerde)
        );

    KTable<String, Long> counts =
        orders
            .selectKey(
                (orderId, event) -> event.customerId()
            )
            .groupByKey(
                Grouped.with(
                    Serdes.String(),
                    orderEventSerde
                )
            )
            .count();

    counts
        .toStream()
        .to(
            "customer-order-counts",
            Produced.with(
                Serdes.String(),
                Serdes.Long()
            )
        );

    Properties props = new Properties();
    props.put(
        StreamsConfig.APPLICATION_ID_CONFIG,
        "order-count-test"
    );
    props.put(
        StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
        "dummy:9092"
    );

    try (TopologyTestDriver driver =
             new TopologyTestDriver(builder.build(), props)) {

        TestInputTopic<String, OrderEvent> input =
            driver.createInputTopic(
                "orders",
                new StringSerializer(),
                orderEventSerde.serializer()
            );

        TestOutputTopic<String, Long> output =
            driver.createOutputTopic(
                "customer-order-counts",
                new StringDeserializer(),
                new LongDeserializer()
            );

        input.pipeInput(
            "order-1",
            new OrderEvent("order-1", "customer-7", 100L)
        );
        input.pipeInput(
            "order-2",
            new OrderEvent("order-2", "customer-7", 200L)
        );

        List<KeyValue<String, Long>> results =
            output.readKeyValuesToList();

        assertThat(results)
            .contains(
                KeyValue.pair("customer-7", 1L),
                KeyValue.pair("customer-7", 2L)
            );
    }
}
~~~

Ví dụ minh họa; cần có model, Serde, JUnit và AssertJ phù hợp với project. TopologyTestDriver kiểm tra semantics của topology và state/output, không mô phỏng đầy đủ broker, network, replication, ACL hoặc assignment nhiều partition.

### 12.2. Integration test với broker thật

Dùng EmbeddedKafka hoặc Testcontainers khi cần xác nhận:
- Internal repartition topic được tạo.
- Partition count đúng.
- ACL và replication factor phù hợp.
- Producer/consumer thực sự serialize và deserialize qua broker.
- Task assignment và consumer lag.
- Application restart và state recovery.
- Rebalance khi scale instance.
- Ordering của key khi dữ liệu đi qua nhiều partition.

Với join, test ít nhất hai topic có cùng key nhưng record được publish từ các producer độc lập. Xác nhận cùng key tới cùng partition ở cả hai phía.

## 13. Những lỗi thường gặp

### 13.1. Đổi key rồi aggregation nhưng không repartition

Triệu chứng:
- Kết quả count bị chia theo task.
- Một customer có nhiều kết quả state không như mong đợi.
- Join thiếu kết quả vì hai record cùng key nằm ở partition khác.

Khắc phục:
- Dùng DSL operation có semantics tự động repartition.
- Hoặc gọi repartition() tường minh trước stateful operation.
- Kiểm tra Topology.describe().

### 13.2. Serde của key mới không đúng

Triệu chứng:
- SerializationException.
- DeserializationException.
- Task fail khi bắt đầu xử lý repartition topic.

Khắc phục:
- Chỉ định key/value Serde qua Grouped hoặc Repartitioned.
- Kiểm tra key type sau selectKey()/map().
- Kiểm tra serializer và deserializer tương ứng.

### 13.3. Join hai topic không co-partition

Triệu chứng:
- Kafka Streams báo lỗi co-partitioning.
- Kết quả join thiếu hoặc không khớp.
- Hai topic có số partition khác nhau.

Khắc phục:
- Đảm bảo cùng partition count.
- Dùng cùng key encoding.
- Dùng cùng partitioner.
- Repartition cả hai stream với cùng số partition và partitioning strategy nếu cần.

### 13.4. Dùng groupBy() thay vì groupByKey()

Triệu chứng:
- Topology có repartition topic không cần thiết.
- Tăng network và broker I/O.
- Latency cao hơn.

Khắc phục:
- Nếu grouping theo key hiện tại, dùng groupByKey().
- Chỉ dùng groupBy() khi thực sự tính key grouping mới.

### 13.5. Quá nhiều repartition topic

Triệu chứng:
- Nhiều internal topics.
- Topology nhiều sub-topology.
- Throughput thấp, network và disk tăng.
- Application startup và recovery lâu hơn.

Khắc phục:
- Đọc Topology.describe().
- Tránh đổi key nhiều lần.
- Đưa key cần thiết vào source topic ngay từ producer nếu có thể.
- Cân nhắc topology optimization.
- Đặt tên operator để dễ theo dõi.

### 13.6. Internal topic không tạo được

Nguyên nhân:
- ACL thiếu.
- Replication factor lớn hơn số broker khả dụng.
- Broker không đáp ứng min.insync.replicas.
- Topic config không hợp lệ.
- Application ID hoặc internal topic cũ xung đột với topology mới.

Khắc phục:
- Kiểm tra worker/application logs.
- Kiểm tra ACL và quyền Admin.
- Kiểm tra broker health, replication và ISR.
- Kiểm tra application.id và topology version.
- Dùng quy trình migration/recovery phù hợp thay vì xóa topic thủ công.

### 13.7. Hot key

Triệu chứng:
- Một partition có lag cao hơn rõ rệt.
- Một task chiếm phần lớn CPU.
- Tăng stream threads nhưng throughput không tăng tương ứng.

Khắc phục:
- Kiểm tra phân phối key.
- Xem xét hai tầng aggregation hoặc sharding có kiểm soát.
- Đo skew trước khi tăng partition count.
- Không phá vỡ semantics grouping chỉ để chia tải.

## 14. Quy trình thiết kế repartition cho một luồng mới

1. Xác định key của source topic và partitioner đang dùng.
2. Xác định key cần cho aggregation hoặc join downstream.
3. Kiểm tra key hiện tại có đúng với yêu cầu chưa.
4. Nếu key đổi, dùng selectKey() hoặc groupBy().
5. Chọn groupByKey() nếu đã có key đúng; tránh groupBy() không cần thiết.
6. Chỉ định Serde cho key/value mới.
7. Với join, xác nhận co-partitioning của cả hai phía.
8. Chỉ định partition count nếu cần kiểm soát downstream parallelism.
9. Kiểm tra custom partitioner nếu có.
10. Dùng Topology.describe() để xác nhận internal repartition nodes.
11. Test với TopologyTestDriver và broker thật theo nhu cầu.
12. Đo throughput, lag, latency, disk và network sau triển khai.
13. Ghi nhận internal topic name, ACL, replication và runbook.

## 15. Checklist production

| Hạng mục | Câu hỏi cần xác nhận |
|---|---|
| Key nguồn | Topic đầu vào đang partition theo key nào? |
| Key đích | Aggregation/join cần key nào? |
| Key-changing | Có selectKey(), map() hoặc groupBy() không? |
| DSL behavior | groupByKey() có kích hoạt repartition vì upstream đã đổi key không? |
| Explicit repartition | Có cần kiểm soát tên, Serde, partition count hoặc partitioner không? |
| Serde | Key/value Serde có tương thích kiểu mới không? |
| Co-partition | Join inputs có cùng partition count và partitioning strategy không? |
| Partition count | Số partition có đủ cho downstream tasks và throughput không? |
| Hot key | Có key nào chiếm phần lớn traffic không? |
| Internal topics | Tên, replication factor, ACL và topic configs có đúng không? |
| Lifecycle | Đã hiểu Streams quản lý purge và cleanup chưa? |
| Optimization | Có thể giảm repartition mà vẫn giữ semantics không? |
| Observability | Có theo dõi internal topic throughput, lag và task metrics không? |
| Recovery | Application restart có thể restore và tiếp tục xử lý không? |
| Migration | Thay partition count hoặc topology có kế hoạch rollout không? |

## 16. Kết luận

Repartition topic là internal topic giúp Kafka Streams chuyển record sang partition phù hợp với key mới. Nó cần thiết khi dữ liệu phải được nhóm hoặc join theo key nhưng partition mapping hiện tại không bảo đảm cùng key nằm cùng task.

DSL có thể tự động repartition sau các thao tác đổi key như selectKey() hoặc map() khi grouping/join phía sau cần phân phối lại. groupBy() luôn repartition; groupByKey() chỉ repartition khi stream đã được đánh dấu cần repartition. repartition() cho phép ứng dụng chủ động đặt tên, số partition, Serde và partitioner.

Mỗi repartition tạo thêm lượt ghi/đọc Kafka và ảnh hưởng latency, network, disk, replication và recovery. Hãy chọn key đúng từ đầu, giữ Serde và partitioner nhất quán, bảo đảm co-partitioning khi join, kiểm tra topology trước khi deploy và theo dõi internal topics trong production.

## Tài liệu tham khảo

- Apache Kafka Streams DSL: https://kafka.apache.org/44/streams/developer-guide/dsl-api/
- Apache Kafka Streams configuration: https://kafka.apache.org/44/streams/developer-guide/config-streams/
- Apache Kafka Streams internal topics: https://kafka.apache.org/44/streams/developer-guide/manage-topics/
- Kafka Streams KStream API: https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/kstream/KStream.html
- Kafka Streams Repartitioned API: https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/kstream/Repartitioned.html
