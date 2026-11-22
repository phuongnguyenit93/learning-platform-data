# KStream, KTable và GlobalKTable

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này giải thích ba abstraction dữ liệu cốt lõi của Kafka Streams: **KStream**, **KTable** và **GlobalKTable**.

KStream biểu diễn chuỗi event độc lập theo thời gian. KTable biểu diễn trạng thái mới nhất của từng key được xây dựng từ changelog. GlobalKTable cũng biểu diễn trạng thái mới nhất theo key, nhưng mỗi Kafka Streams application instance giữ một bản sao đầy đủ của toàn bộ bảng. Chọn đúng abstraction quyết định cách join, yêu cầu partitioning, chi phí lưu trữ và ý nghĩa kết quả xử lý.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt event stream với changelog table.
- Giải thích cách KStream xử lý từng record như một sự kiện độc lập.
- Giải thích cách KTable duy trì giá trị mới nhất theo key và xử lý tombstone.
- Mô tả cách GlobalKTable sao chép toàn bộ dữ liệu bảng đến mỗi application instance.
- Chọn KStream, KTable hoặc GlobalKTable theo semantics của dữ liệu.
- Thực hiện KStream-KTable join theo key.
- Thực hiện KStream-GlobalKTable join bằng KeyValueMapper.
- Giải thích KTable-KTable join và tác động của cập nhật từ hai phía.
- Hiểu co-partitioning, repartition topic và state store.
- Viết topology Java Kafka Streams dùng ba abstraction.
- Kiểm tra kết quả bằng TopologyTestDriver và giám sát state store trong vận hành.

## 2. Cùng một dữ liệu, ba cách nhìn

Giả sử hệ thống bán hàng có hai luồng:

- Topic orders ghi nhận các sự kiện đơn hàng: OrderCreated, OrderPaid, OrderShipped.
- Topic customers ghi nhận thông tin khách hàng được tạo hoặc cập nhật theo customerId.

Một đơn hàng có thể phát sinh nhiều event trong suốt vòng đời. Một khách hàng có thể được cập nhật địa chỉ hoặc hạng thành viên nhiều lần, nhưng khi xử lý đơn hàng, ứng dụng thường chỉ cần thông tin mới nhất.

~~~text
orders:
  order-101 -> OrderCreated
  order-102 -> OrderCreated
  order-101 -> OrderPaid
  order-101 -> OrderShipped

customers:
  customer-7 -> Bronze
  customer-8 -> Silver
  customer-7 -> Gold
~~~

Cùng một topic Kafka có thể được đọc như KStream hoặc KTable tùy cách khai báo topology và semantics ứng dụng.

- Đọc orders như KStream: mỗi record là một event cần xử lý.
- Đọc customers như KTable: mỗi record cập nhật trạng thái hiện tại của một customerId.
- Đọc customers như GlobalKTable: mỗi instance của ứng dụng giữ toàn bộ trạng thái khách hàng để tra cứu cục bộ.

Điểm quan trọng là KStream và KTable không phải hai kiểu topic Kafka khác nhau. Chúng là hai cách Kafka Streams diễn giải record trong topology.

## 3. KStream: chuỗi sự kiện

**KStream<K, V>** là abstraction cho một luồng record key/value. Mỗi record được xem là một sự kiện độc lập. Nếu một key xuất hiện nhiều lần, tất cả record vẫn là các event riêng biệt.

Ví dụ:

~~~text
orders:
  key=order-101, value=OrderCreated
  key=order-101, value=OrderPaid
  key=order-101, value=OrderShipped
~~~

KStream giữ cả ba sự kiện. Nó không tự động thay OrderCreated bằng OrderShipped chỉ vì chúng có cùng key.

Kafka bảo đảm thứ tự record trong từng partition. KStream xử lý theo thứ tự record được đọc trong partition đó; không có một thứ tự toàn cục giữa các partition khác nhau.

### 3.1. Đặc điểm của KStream

- Mỗi record là một event.
- Nhiều record có cùng key vẫn được giữ và xử lý riêng.
- Phù hợp với filter, map, flatMap, branch, merge, groupBy và windowed aggregation.
- Có thể join với KStream, KTable hoặc GlobalKTable.
- Không tự duy trì bảng trạng thái mới nhất cho key nếu topology không thực hiện stateful operation.

Ví dụ các thao tác:

~~~java
KStream<String, String> orders =
    builder.stream(
        "orders",
        Consumed.with(Serdes.String(), Serdes.String())
    );

KStream<String, String> paidOrders = orders
    .filter((orderId, event) -> event.contains("PAID"));

KStream<String, String> normalized = paidOrders
    .mapValues(String::trim);

normalized.to(
    "orders-paid",
    Produced.with(Serdes.String(), Serdes.String())
);
~~~

Trong ví dụ, mọi record thỏa điều kiện được chuyển tiếp. Nếu cùng một orderId có nhiều event PAID, mỗi event vẫn được xử lý.

### 3.2. KStream phù hợp với dữ liệu nào?

Dùng KStream khi dữ liệu biểu diễn các lần xảy ra:

- Giao dịch thanh toán.
- Click, view hoặc hành vi người dùng.
- Event tạo đơn, hủy đơn, giao hàng.
- Log ứng dụng.
- Sensor reading.
- Lịch sử thay đổi cần phân tích từng event.

Nếu yêu cầu là đếm số đơn hàng theo khách hàng, KStream có thể được group và aggregate để tạo một KTable kết quả.

### 3.3. Aggregate KStream để tạo KTable

Một aggregation như count() biến chuỗi event thành trạng thái tổng hợp theo key. Kết quả là KTable và được cập nhật mỗi khi có event mới:

~~~java
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.Materialized;

KTable<String, Long> orderCountByCustomer = orders
    .selectKey((orderId, orderValue) ->
        orderValue.substring(0, orderValue.indexOf('|'))
    )
    .groupByKey(
        Grouped.with(Serdes.String(), Serdes.String())
    )
    .count(
        Materialized.as("order-count-by-customer")
    );
~~~

Ở đây, value của order được giả định bắt đầu bằng customerId. selectKey() đổi key sang customerId; groupByKey() nhóm event theo key mới và có thể yêu cầu repartition trước khi aggregate. KTable đầu ra giữ số đơn hiện tại theo từng customerId, không phải danh sách từng event.

## 4. KTable: trạng thái mới nhất theo key

**KTable<K, V>** là abstraction biểu diễn một bảng trạng thái được định danh bằng key. Mỗi record đầu vào cập nhật giá trị hiện tại của key tương ứng.

Ví dụ topic customers:

~~~text
offset 0: key=customer-7, value=Bronze
offset 1: key=customer-8, value=Silver
offset 2: key=customer-7, value=Gold
~~~

Sau khi đọc ba record, trạng thái KTable là:

| Key | Giá trị hiện tại |
|---|---|
| customer-7 | Gold |
| customer-8 | Silver |

Record Bronze không còn là giá trị hiện tại của customer-7. KTable giữ Gold vì đây là cập nhật mới hơn được xử lý cho key đó.

### 4.1. KTable là changelog, không phải snapshot tĩnh

KTable được duy trì từ các record cập nhật liên tục. Mỗi record có thể:

- Tạo một key mới.
- Thay thế giá trị hiện tại của key.
- Xóa key khi value là null (tombstone).

KTable không có nghĩa dữ liệu chỉ tải một lần. Nó tiếp tục cập nhật khi topic nguồn có record mới.

### 4.2. Tombstone xóa key

Trong Kafka, record có key và value null được gọi là **tombstone** trong ngữ cảnh log-compacted topic. Khi KTable nhận tombstone, key tương ứng bị xóa khỏi trạng thái bảng.

Ví dụ:

~~~text
customer-7 -> Bronze
customer-7 -> Gold
customer-7 -> null
~~~

Trạng thái cuối cùng không còn customer-7.

Tombstone khác với chuỗi rỗng, JSON null hoặc một object có trường deleted=true. Chỉ record có Kafka value null mới có semantics tombstone chuẩn của KTable.

Giá trị “mới nhất” của KTable được xác định theo thứ tự record được xử lý trong partition, không tự động là record có event timestamp lớn nhất. Nếu một update cũ đến muộn và được append sau update mới, nó có thể ghi đè state hiện tại. Nếu nghiệp vụ cần ưu tiên version hoặc event time, hãy kiểm tra version/timestamp trong processor hoặc chọn lọc update trước khi cập nhật table.

### 4.3. KTable thường dùng với topic compacted

Topic nguồn của KTable thường được cấu hình cleanup.policy=compact để Kafka giữ lại giá trị mới nhất theo key sau quá trình compaction. Điều này giúp khôi phục state store mà không phải giữ vô hạn mọi bản cập nhật.

Compaction không diễn ra ngay lập tức. Trong log có thể vẫn tồn tại nhiều phiên bản của cùng key cho đến khi cleaner xử lý. Tombstone cũng được giữ trong một khoảng thời gian theo delete.retention.ms trước khi có thể bị loại bỏ.

KTable vẫn có thể đọc topic không compacted, nhưng topic compacted thường phù hợp hơn với changelog state dài hạn. Chọn retention và cleanup policy theo yêu cầu replay, recovery và lưu trữ.

### 4.4. Khai báo KTable

~~~java
KTable<String, String> customers =
    builder.table(
        "customers",
        Consumed.with(Serdes.String(), Serdes.String())
    );
~~~

Kafka Streams đọc topic customers và duy trì state theo key. Khi một record mới đến, giá trị của key trong KTable được cập nhật.

KTable thường được materialize vào state store cục bộ. Store cho phép topology tra cứu giá trị hiện tại theo key mà không cần quét toàn bộ topic mỗi lần join.

## 5. GlobalKTable: bảng đầy đủ trên mỗi instance

**GlobalKTable<K, V>** cũng biểu diễn trạng thái mới nhất theo key, nhưng khác KTable ở phạm vi dữ liệu được phân phối.

Với KTable thông thường, partition của state được phân phối theo task và instance. Mỗi instance chỉ lưu phần state tương ứng với các partition được giao cho nó.

Với GlobalKTable, mỗi Kafka Streams application instance đọc toàn bộ partition của topic nguồn và giữ một bản sao đầy đủ của bảng.

~~~text
Topic customers có 3 partitions:

customers-0
customers-1
customers-2

Kafka Streams instance A:
  GlobalKTable = dữ liệu từ P0 + P1 + P2

Kafka Streams instance B:
  GlobalKTable = dữ liệu từ P0 + P1 + P2

Kafka Streams instance C:
  GlobalKTable = dữ liệu từ P0 + P1 + P2
~~~

### 5.1. Đặc điểm của GlobalKTable

- Mỗi instance có toàn bộ dữ liệu bảng.
- Có thể tra cứu theo một key được tính từ record KStream.
- Không yêu cầu co-partitioning giữa KStream và GlobalKTable.
- Phù hợp với bảng tham chiếu tương đối nhỏ, cần tra cứu từ nhiều stream partition.
- Tăng network traffic, local storage và thời gian khôi phục khi số instance hoặc kích thước bảng tăng.
- Cập nhật của GlobalKTable được phân phối đến mọi instance theo tiến độ tiêu thụ của từng instance.

### 5.2. Khai báo GlobalKTable

~~~java
GlobalKTable<String, String> customerDirectory =
    builder.globalTable(
        "customers",
        Consumed.with(Serdes.String(), Serdes.String())
    );
~~~

Mỗi instance sẽ duy trì bản sao local của toàn bộ bảng customers.

### 5.3. Khi nào dùng GlobalKTable?

Ví dụ phù hợp:

- Bảng quốc gia, tỉnh/thành hoặc mã tiền tệ.
- Danh mục sản phẩm tương đối nhỏ.
- Bảng cấu hình hoặc feature flag.
- Bảng ánh xạ mã đối tác.
- Customer reference data có kích thước vừa phải và cần tra cứu từ nhiều partition.

Không nên dùng GlobalKTable cho bảng hàng trăm triệu dòng nếu mỗi instance không đủ tài nguyên để giữ bản sao. Khi bảng lớn, KTable phân vùng thường phù hợp hơn hoặc có thể cần một hệ thống lookup chuyên dụng.

## 6. So sánh KStream, KTable và GlobalKTable

| Tiêu chí | KStream | KTable | GlobalKTable |
|---|---|---|---|
| Ý nghĩa | Chuỗi event | Trạng thái mới nhất theo key | Trạng thái mới nhất đầy đủ trên mỗi instance |
| Record cùng key | Mỗi record là event riêng | Record mới thay giá trị hiện tại | Record mới thay giá trị hiện tại |
| Tombstone | Là record có value null; không tự mang semantics xóa bảng | Xóa key khỏi table state | Xóa key khỏi global table state |
| State store | Không bắt buộc nếu chỉ xử lý stateless | Thường có state store | Có global state store trên từng instance |
| Phạm vi state | Theo luồng record được xử lý | Phân vùng theo task/instance | Toàn bộ bảng trên mỗi instance |
| Join phổ biến | Stream-stream, stream-table, stream-global-table | Table-table và stream-table | Stream-global-table |
| Co-partitioning | Cần cho các join partitioned phù hợp | Cần với KTable join | Không cần với KStream-GlobalKTable join |
| Chi phí lưu trữ | Phụ thuộc stateful operation | Chia state theo partition | Nhân bản toàn bộ state trên mỗi instance |
| Use case | Event, transaction, log | Customer/account/order current state | Lookup/reference data nhỏ |

Có thể nhớ:

- KStream trả lời: “Điều gì đã xảy ra?”
- KTable trả lời: “Giá trị hiện tại của key là gì?”
- GlobalKTable trả lời: “Giá trị hiện tại của bất kỳ key tham chiếu nào có trong bản sao đầy đủ là gì?”

## 7. KStream-KTable join theo key

Một trường hợp phổ biến là mỗi order event cần được bổ sung thông tin khách hàng hiện tại.

Giả sử:

- KStream orders có key là orderId.
- Value chứa customerId và thông tin đơn hàng.
- KTable customers có key là customerId.

KStream và KTable cần dùng cùng key để join. Vì orders đang key theo orderId, topology phải đổi key sang customerId trước khi join.

### 7.1. Ví dụ dữ liệu

~~~text
orders:
  key=order-101, value=customer-7|1200
  key=order-102, value=customer-8|800

customers:
  key=customer-7, value=Gold
  key=customer-8, value=Silver
~~~

Sau khi đổi key của stream:

~~~text
ordersByCustomer:
  key=customer-7, value=customer-7|1200
  key=customer-8, value=customer-8|800
~~~

Kết quả join:

~~~text
customer-7 -> customer-7|1200|Gold
customer-8 -> customer-8|800|Silver
~~~

### 7.2. Java code

~~~java
KStream<String, String> orders =
    builder.stream(
        "orders",
        Consumed.with(Serdes.String(), Serdes.String())
    );

KTable<String, String> customers =
    builder.table(
        "customers",
        Consumed.with(Serdes.String(), Serdes.String())
    );

KStream<String, String> ordersByCustomer = orders.selectKey(
    (orderId, orderValue) ->
        orderValue.substring(0, orderValue.indexOf('|'))
);

KStream<String, String> enrichedOrders =
    ordersByCustomer.leftJoin(
        customers,
        (orderValue, customerTier) ->
            customerTier == null
                ? orderValue + "|UNKNOWN"
                : orderValue + "|" + customerTier
    );

enrichedOrders.to(
    "orders-enriched",
    Produced.with(Serdes.String(), Serdes.String())
);
~~~

Ví dụ dùng leftJoin để vẫn giữ order khi chưa tìm thấy customer. Với join() inner, record stream không có giá trị tương ứng trong KTable sẽ không tạo output.

### 7.3. Semantics của KStream-KTable join

- Mỗi record KStream kích hoạt phép join.
- KTable được tra cứu theo key tại thời điểm record stream được xử lý.
- Cập nhật KTable không tự phát lại các record stream cũ để tạo output mới.
- Nếu customer chưa tồn tại trong state store tại thời điểm join, leftJoin nhận giá trị bên phải là null.
- Kết quả phụ thuộc tiến độ cập nhật của hai input topic; Kafka Streams không tạo một thứ tự thời gian nghiệp vụ toàn cục giữa hai topic.

Ví dụ, event order có thể đến trước cập nhật customer mới. Join có thể thấy giá trị cũ hoặc null. Nếu nghiệp vụ cần chờ dữ liệu tham chiếu, cần thiết kế retry, buffering hoặc quy tắc xử lý riêng.

## 8. Co-partitioning và repartitioning

KStream-KTable join theo key cần các partition được phân phối tương thích. Với join thông thường, stream và table phải co-partitioned:

- Cùng số partition.
- Cùng quy tắc partitioning cho cùng key.
- Cùng serialization/partitioning assumptions.
- Record có cùng key phải đến partition tương ứng trên cả hai input.

Ví dụ:

~~~text
ordersByCustomer: 6 partitions
customers:        6 partitions
~~~

Nếu customer-7 được route vào partition 2 của ordersByCustomer, key customer-7 trong topic customers cũng phải ở partition 2.

### 8.1. selectKey có thể tạo nhu cầu repartition

Khi dùng selectKey() để thay key, record đang ở partition cũ có thể không còn đúng partition theo key mới. Kafka Streams có thể chèn repartition topic nội bộ trước operation cần partition theo key mới.

Repartitioning gồm:

1. Ghi record vào internal repartition topic theo key mới.
2. Đọc lại record theo partition mới.
3. Thực hiện join hoặc aggregation trên partition tương ứng.

Repartition có chi phí network, serialization, disk và latency. Hãy xem topology description để biết Kafka Streams có tạo repartition topic hay không.

### 8.2. Ép repartition rõ ràng

Có thể khai báo repartition để đặt tên và Serde:

~~~java
KStream<String, String> ordersByCustomer = orders
    .selectKey((orderId, orderValue) ->
        orderValue.substring(0, orderValue.indexOf('|'))
    )
    .repartition(
        Repartitioned.with(
            Serdes.String(),
            Serdes.String()
        ).withName("orders-by-customer")
    );
~~~

Khi thiết kế production, kiểm tra partition count của topic customers và repartition topic. Nếu hai phía không co-partitioned, join có thể không hợp lệ hoặc kết quả không đúng như kỳ vọng.

## 9. KStream-GlobalKTable join bằng KeyValueMapper

GlobalKTable cho phép stream tra cứu bảng bằng một key được tính từ record stream. Khác KTable join, không cần đổi key của KStream để partition khớp với bảng global.

Ví dụ:

- KStream orders có key là orderId.
- Value chứa customerId.
- GlobalKTable customers có key là customerId.

Khi xử lý order, KeyValueMapper trích customerId từ value rồi tra cứu GlobalKTable local.

### 9.1. Java code

~~~java
KStream<String, String> orders =
    builder.stream(
        "orders",
        Consumed.with(Serdes.String(), Serdes.String())
    );

GlobalKTable<String, String> customerDirectory =
    builder.globalTable(
        "customers",
        Consumed.with(Serdes.String(), Serdes.String())
    );

KStream<String, String> enrichedOrders =
    orders.leftJoin(
        customerDirectory,
        (orderId, orderValue) ->
            orderValue.substring(0, orderValue.indexOf('|')),
        (orderValue, customerTier) ->
            customerTier == null
                ? orderValue + "|UNKNOWN"
                : orderValue + "|" + customerTier
    );

enrichedOrders.to(
    "orders-enriched-global",
    Produced.with(Serdes.String(), Serdes.String())
);
~~~

Trong overload này:

- Tham số đầu tiên của mapper là stream key (orderId).
- Tham số thứ hai là stream value (orderValue).
- Mapper trả về key dùng để tra cứu GlobalKTable.
- ValueJoiner kết hợp stream value với global table value.
- Output vẫn giữ key của KStream, tức orderId.

### 9.2. Ưu điểm

- Không cần repartition stream chỉ để khớp partition với bảng tham chiếu.
- Có thể tra cứu theo foreign key được trích từ stream record.
- Phù hợp với bảng tham chiếu nhỏ cần dùng bởi nhiều stream partition.
- Join thực hiện trên bản sao local của GlobalKTable.

### 9.3. Chi phí và giới hạn

Mỗi instance phải đọc và lưu toàn bộ bảng. Khi tăng số instance:

- Tổng lượng dữ liệu truyền từ topic global tăng theo số instance.
- Mỗi instance tiêu thụ local disk/heap hoặc tài nguyên state store theo cấu hình.
- Startup và restore có thể lâu hơn khi bảng lớn.
- Mỗi cập nhật phải được áp dụng trên các bản sao local.
- GlobalKTable không phải cache đồng bộ tức thời giữa mọi instance.

GlobalKTable phù hợp khi chi phí replicate toàn bộ bảng nhỏ hơn chi phí repartition stream hoặc lookup từ dịch vụ ngoài. Hãy đo kích thước state, thời gian restore và tốc độ cập nhật trước khi chọn.

## 10. KTable-KTable join

Hai KTable có thể join theo primary key khi được partition tương thích. Kết quả cũng là KTable biểu diễn trạng thái kết hợp.

Ví dụ:

- customers: customerId -> customer profile.
- customer-tiers: customerId -> tier.
- joined table: customerId -> profile + tier.

~~~java
KTable<String, String> customers =
    builder.table(
        "customers",
        Consumed.with(Serdes.String(), Serdes.String())
    );

KTable<String, String> tiers =
    builder.table(
        "customer-tiers",
        Consumed.with(Serdes.String(), Serdes.String())
    );

KTable<String, String> customerView =
    customers.leftJoin(
        tiers,
        (profile, tier) ->
            tier == null ? profile + "|UNKNOWN" : profile + "|" + tier
    );

customerView.toStream().to(
    "customer-view",
    Produced.with(Serdes.String(), Serdes.String())
);
~~~

KTable-KTable join có semantics khác KStream-KTable:

- Cập nhật từ bảng bên trái có thể làm thay đổi kết quả.
- Cập nhật từ bảng bên phải cũng có thể làm thay đổi kết quả.
- Kết quả là một changelog table.
- toStream() chuyển các thay đổi của table thành record stream để ghi ra topic.

Đây là cách phù hợp khi cần duy trì một view được cập nhật từ nhiều bảng trạng thái.

## 11. KStream, KTable và GlobalKTable trong một topology

Một topology có thể kết hợp nhiều abstraction.

Ví dụ:

1. Đọc order events dưới dạng KStream.
2. Join với KTable customer profile theo customerId.
3. Join với GlobalKTable country directory để lấy tên quốc gia.
4. Ghi kết quả enriched event sang topic khác.
5. Aggregate order count theo customerId để tạo KTable thống kê.

~~~mermaid
flowchart TD
    O[(orders topic)] --> KS[KStream orders]
    C[(customers topic)] --> KT[KTable customers]
    D[(country-directory topic)] --> GT[GlobalKTable countries]
    KS --> RK[selectKey customerId]
    RK --> J1[KStream-KTable join]
    KT --> J1
    J1 --> J2[KStream-GlobalKTable join]
    GT --> J2
    J2 --> OUT[(orders-enriched topic)]
    RK --> AGG[groupByKey / count]
    AGG --> CT[KTable order counts]
    CT --> OUT2[(customer-order-counts topic)]
~~~

Cần lưu ý: đây là sơ đồ logic. Topology thực tế có thể chèn repartition topic, changelog topic và state store để thực hiện join hoặc aggregate.

## 12. State store, changelog và khôi phục

KTable và GlobalKTable thường dựa vào state store để tra cứu giá trị hiện tại.

Kafka Streams quản lý state store theo topology. Khi state cần fault-tolerance, Kafka Streams sử dụng changelog topic nội bộ để lưu thay đổi state và khôi phục sau khi instance gặp sự cố.

### 12.1. KTable state store

Với KTable partitioned:

- Mỗi task duy trì state của các partition được giao.
- State store thường được lưu local.
- Changelog topic giúp khôi phục state khi task chuyển instance hoặc local state không còn dùng được.
- Khi rebalance, task có thể cần restore state trước khi xử lý bình thường.

### 12.2. GlobalKTable state store

Với GlobalKTable:

- Mỗi instance có state store chứa toàn bộ key/value.
- Mỗi instance đọc mọi partition của global source topic.
- Khi instance mới khởi động, nó cần restore toàn bộ bảng.
- Tăng số instance đồng nghĩa tăng số bản sao state.

### 12.3. Không xóa internal topics tùy tiện

Các internal topic của Kafka Streams có thể chứa repartition data hoặc changelog state. Xóa nhầm có thể làm topology không thể khôi phục đúng trạng thái hoặc buộc phải rebuild từ source.

Dùng application.id ổn định cho cùng một logical application. Nếu đổi application.id, Kafka Streams xem đó là application khác với consumer group và internal topic namespace mới. Chỉ đổi khi có chủ đích tạo ứng dụng mới hoặc thực hiện migration.

## 13. Ordering và thời điểm cập nhật bảng

Join giữa stream và table phụ thuộc trạng thái local đã được cập nhật tại thời điểm record được xử lý.

Ví dụ:

~~~text
Topic orders:
  order-1 -> customer-7|1200

Topic customers:
  customer-7 -> Gold
~~~

Nếu order được xử lý trước khi cập nhật customer-7 đến state store, join có thể trả null hoặc giá trị cũ. Kafka không đảm bảo thứ tự tuyệt đối giữa hai topic khác nhau.

Các cách xử lý theo yêu cầu nghiệp vụ:

- Chấp nhận dữ liệu tham chiếu gần nhất tại thời điểm xử lý.
- Đưa record chưa đủ dữ liệu vào retry topic hoặc stateful buffer.
- Dùng event timestamp và grace period nếu bài toán cần chờ dữ liệu đến trễ.
- Dùng version hoặc effective time trong payload để xác định bản ghi nào phù hợp.
- Thiết kế event source để gửi dữ liệu tham chiếu trước event nghiệp vụ nếu có thể.

GlobalKTable cũng có tính nhất quán theo tiến độ cập nhật local của từng instance; không nên giả định mọi instance nhìn thấy cùng một update tại cùng thời điểm.

## 14. Chọn join phù hợp

| Yêu cầu | Abstraction / phép join | Lý do |
|---|---|---|
| Xử lý từng event độc lập | KStream | Giữ mỗi record như một sự kiện. |
| Tra cứu trạng thái hiện tại theo key đã partition | KStream-KTable | Join theo key, state phân vùng. |
| Tra cứu bảng tham chiếu nhỏ theo key bất kỳ trong stream | KStream-GlobalKTable | Mapper chọn lookup key, không cần co-partition. |
| Duy trì view từ hai bảng trạng thái | KTable-KTable | Cập nhật từ hai phía làm thay đổi kết quả table. |
| Ghép hai event stream theo thời gian | KStream-KStream | Cần join window và retention phù hợp. |
| Bảng lookup quá lớn để nhân bản toàn instance | KTable hoặc dịch vụ lookup chuyên dụng | Tránh replicate toàn bộ state trên mọi instance. |

Trước khi chọn, hãy trả lời:

1. Dữ liệu là event hay current state?
2. Key join có trùng với key hiện tại của stream không?
3. Bảng tham chiếu lớn đến mức nào?
4. Có chấp nhận repartition không?
5. Có thể chấp nhận độ trễ cập nhật giữa các input topic không?
6. Có yêu cầu ordering hoặc event-time semantics không?
7. Mỗi instance có đủ tài nguyên để giữ global state không?

## 15. Cấu hình Kafka Streams cơ bản

Ví dụ cấu hình application:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsConfig;

import java.util.Properties;

Properties properties = new Properties();

properties.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "orders-enrichment-v1"
);
properties.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
properties.put(
    StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
    Serdes.String().getClass()
);
properties.put(
    StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
    Serdes.String().getClass()
);
~~~

Các cấu hình cần chú ý:

| Cấu hình | Ý nghĩa |
|---|---|
| application.id | Định danh logical Kafka Streams application và consumer group. |
| bootstrap.servers | Broker dùng để kết nối cluster. |
| default.key.serde | Serde mặc định cho key nếu operation không khai báo rõ. |
| default.value.serde | Serde mặc định cho value nếu operation không khai báo rõ. |
| state.dir | Thư mục local lưu state store. |
| num.stream.threads | Số stream thread trong một instance. |
| processing.guarantee | Chế độ xử lý, ví dụ at_least_once hoặc exactly_once_v2 tùy phiên bản. |

Nên khai báo Serde rõ ở source, join và sink khi kiểu dữ liệu khác nhau. Serde sai có thể khiến topology lỗi khi deserialize, repartition hoặc ghi output.

### 15.1. Khởi chạy topology

~~~java
StreamsBuilder builder = new StreamsBuilder();

// Khai báo KStream, KTable, GlobalKTable và các phép join tại đây.

Topology topology = builder.build();

System.out.println(topology.describe());

KafkaStreams streams = new KafkaStreams(topology, properties);
streams.start();

Runtime.getRuntime().addShutdownHook(
    new Thread(streams::close)
);
~~~

Trong production, cần thêm uncaught exception handler, state listener, health check và shutdown timeout phù hợp. Không khởi tạo nhiều KafkaStreams instance với cùng application.id trong cùng process nếu không có thiết kế lifecycle rõ ràng.

## 16. Kiểm thử topology bằng TopologyTestDriver

Kafka Streams cung cấp TopologyTestDriver để kiểm thử logic topology mà không cần chạy broker thật cho các test topology cơ bản.

Một bài test có thể:

1. Tạo StreamsBuilder.
2. Khai báo KStream, KTable hoặc GlobalKTable.
3. Build topology.
4. Khởi tạo TopologyTestDriver với Properties.
5. Tạo TestInputTopic cho input.
6. Tạo TestOutputTopic cho output.
7. Pipe record đầu vào.
8. Đọc output và assert kết quả.

Ví dụ khung test cho KStream-KTable:

~~~java
Properties testProperties = new Properties();
testProperties.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "orders-test"
);
testProperties.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "dummy:9092"
);
testProperties.put(
    StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
    Serdes.String().getClass()
);
testProperties.put(
    StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
    Serdes.String().getClass()
);

try (TopologyTestDriver driver =
         new TopologyTestDriver(topology, testProperties)) {

    TestInputTopic<String, String> customerInput =
        driver.createInputTopic(
            "customers",
            Serdes.String().serializer(),
            Serdes.String().serializer()
        );

    TestInputTopic<String, String> orderInput =
        driver.createInputTopic(
            "orders",
            Serdes.String().serializer(),
            Serdes.String().serializer()
        );

    TestOutputTopic<String, String> output =
        driver.createOutputTopic(
            "orders-enriched",
            Serdes.String().deserializer(),
            Serdes.String().deserializer()
        );

    customerInput.pipeInput("customer-7", "Gold");
    orderInput.pipeInput("order-101", "customer-7|1200");

    KeyValue<String, String> result = output.readKeyValue();
    assertEquals("customer-7", result.key);
    assertTrue(result.value.contains("Gold"));
}
~~~

TestInputTopic cho table phải được pipe trước record stream trong ví dụ để state có sẵn khi join. Test này xác minh semantics của topology trong điều kiện input đã được xử lý theo thứ tự đó; nó không chứng minh hai topic production luôn được đồng bộ theo cùng thứ tự.

Với GlobalKTable, TopologyTestDriver cũng hỗ trợ input topic và global store theo topology. Hãy kiểm thử trường hợp key không tồn tại, tombstone, update và nhiều stream key khác nhau.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| KStream-KTable join không có kết quả | Key stream không khớp key table hoặc table chưa được cập nhật. | Kiểm tra key, Serde, partitioning và thứ tự dữ liệu. |
| Join lỗi do partition mismatch | Hai input không co-partitioned. | Đồng bộ partition count và partitioner; repartition stream khi đổi key. |
| selectKey xong join vẫn sai | Record không được repartition theo key mới hoặc key serialization khác nhau. | Kiểm tra topology và internal repartition topic. |
| KTable không xóa key | Producer gửi chuỗi rỗng hoặc JSON null thay vì Kafka value null. | Gửi tombstone thực sự với key và value null. |
| KStream bị hiểu nhầm là current state | Ứng dụng mong record cùng key thay thế nhau. | Dùng KTable nếu cần semantics latest value per key. |
| GlobalKTable làm startup lâu | Bảng lớn và mỗi instance phải tải toàn bộ dữ liệu. | Dùng KTable partitioned hoặc giảm kích thước reference data. |
| GlobalKTable tăng network/storage | Mỗi instance đọc và giữ toàn bộ bảng. | Tính tổng số bản sao và đánh giá chi phí. |
| Join thấy dữ liệu tham chiếu cũ | Update ở topic table chưa được xử lý tại thời điểm stream record chạy. | Xác định consistency requirement và thiết kế buffer/retry/version. |
| KTable state restore chậm | State lớn, changelog lớn hoặc local state không còn. | Kiểm tra restore lag, disk, changelog và state.dir. |
| Serialization error | Serde key/value không tương thích giữa input, store và output. | Khai báo Serde rõ và kiểm tra schema/format. |
| Output KTable thiếu thay đổi | Topology chưa chuyển table thành stream hoặc sink không được cấu hình đúng. | Dùng toStream() khi cần xuất changelog dưới dạng record. |

## 18. Checklist thiết kế production

Trước khi triển khai topology, hãy xác nhận:

1. Đã phân loại từng input là event stream hay changelog state chưa?
2. KTable có key ổn định và đúng semantics primary key chưa?
3. Topic KTable có cleanup policy phù hợp, thường là compact, chưa?
4. Tombstone được gửi và xử lý đúng chưa?
5. KStream-KTable join có key tương thích không?
6. Hai phía partitioned join có cùng partition count và partitioner không?
7. selectKey/groupBy có tạo repartition topic không?
8. Repartition có Serde và partition count phù hợp không?
9. GlobalKTable có đủ nhỏ để replicate toàn bộ trên mọi instance không?
10. Đã tính network, local disk và restore time cho GlobalKTable chưa?
11. Join có chấp nhận dữ liệu tham chiếu cập nhật trễ không?
12. State store và changelog có đủ durability không?
13. application.id có ổn định và duy nhất cho logical application không?
14. Có kiểm thử tombstone, key không tồn tại và update từ cả hai phía không?
15. Có metric cho state restore, processing latency, rebalance và record throughput không?
16. Có kiểm thử restart/rebalance trong môi trường staging không?

## 19. Bài tập thực hành

### Bài 1: So sánh KStream và KTable

1. Tạo topic customers-lab.
2. Gửi customer-7 -> Bronze.
3. Gửi customer-8 -> Silver.
4. Gửi customer-7 -> Gold.
5. Đọc topic bằng KStream và in cả ba record.
6. Đọc topic bằng KTable và truy vấn trạng thái hiện tại.
7. Giải thích vì sao KStream có ba event còn KTable chỉ có hai key hiện tại.

### Bài 2: Tombstone

1. Tạo KTable từ topic customers-lab.
2. Gửi customer-7 -> null.
3. Quan sát state store hoặc kết quả join.
4. Gửi lại customer-7 -> Platinum.
5. Xác nhận key xuất hiện trở lại.
6. Phân biệt tombstone với value chuỗi rỗng.

### Bài 3: KStream-KTable join

1. Tạo topic orders-lab và customers-lab.
2. Cho orders key theo orderId và value chứa customerId.
3. Đọc customers thành KTable.
4. Dùng selectKey để chuyển orders sang customerId.
5. Join và ghi output.
6. Thử order đến trước customer update.
7. Thử cập nhật customer sau khi order đã join.
8. Quan sát vì sao KStream-KTable join không tự phát lại order cũ.

### Bài 4: KStream-GlobalKTable join

1. Tạo customer-directory có một số key tham chiếu.
2. Đọc bằng GlobalKTable.
3. Đọc orders dưới dạng KStream với key là orderId.
4. Dùng KeyValueMapper lấy customerId từ value.
5. Join và giữ output key là orderId.
6. Chạy hai Kafka Streams instance.
7. Quan sát mỗi instance có bản sao đầy đủ của customer directory.
8. So sánh với KTable partitioned.

### Bài 5: KTable-KTable join

1. Tạo customers và customer-tiers.
2. Đọc cả hai bằng KTable.
3. Join theo customerId.
4. Cập nhật profile ở bảng thứ nhất.
5. Cập nhật tier ở bảng thứ hai.
6. Quan sát output changelog thay đổi từ cả hai phía.

### Bài 6: Đo chi phí GlobalKTable

1. Tạo bảng tham chiếu với kích thước tăng dần.
2. Chạy một, hai rồi bốn application instance.
3. Đo thời gian startup/restore, local disk và network traffic.
4. Ước lượng chi phí nhân bản theo số instance.
5. Đề xuất ngưỡng kích thước bảng nên chuyển sang KTable hoặc dịch vụ lookup.

## 20. Câu hỏi tự kiểm tra

1. KStream biểu diễn loại dữ liệu nào?
2. Vì sao hai record cùng key trong KStream vẫn là hai event riêng?
3. KTable biểu diễn trạng thái gì?
4. Record mới cùng key ảnh hưởng KTable như thế nào?
5. Tombstone có ý nghĩa gì với KTable?
6. Vì sao topic nguồn của KTable thường dùng cleanup.policy=compact?
7. GlobalKTable khác KTable ở phạm vi state như thế nào?
8. Vì sao GlobalKTable không cần co-partitioning với KStream?
9. KeyValueMapper trong KStream-GlobalKTable join làm nhiệm vụ gì?
10. KStream-KTable join được kích hoạt bởi phía nào?
11. Vì sao cập nhật KTable không tự phát lại KStream record cũ?
12. Co-partitioning yêu cầu những điều kiện gì?
13. selectKey có thể làm phát sinh repartition topic vì sao?
14. KTable-KTable join có thể thay đổi output khi phía nào cập nhật?
15. Vì sao GlobalKTable có thể làm startup và network cost tăng?
16. State store và changelog topic hỗ trợ khôi phục như thế nào?
17. Khi nào nên dùng KStream thay vì KTable?
18. Khi nào nên chọn GlobalKTable cho bảng tham chiếu?
19. Vì sao join có thể thấy dữ liệu table cũ hoặc null?
20. Cần kiểm thử những trường hợp nào trước khi đưa topology vào production?

## Kết luận

KStream, KTable và GlobalKTable biểu diễn ba cách nhìn khác nhau về dữ liệu trong Kafka Streams. KStream giữ mỗi record như một event độc lập. KTable duy trì trạng thái mới nhất theo key và xử lý tombstone như thao tác xóa. GlobalKTable duy trì cùng loại trạng thái nhưng sao chép toàn bộ bảng đến mỗi application instance để tra cứu cục bộ.

KStream-KTable join phù hợp với lookup theo key khi hai phía co-partitioned. KStream-GlobalKTable join dùng KeyValueMapper để chọn lookup key và không cần repartition stream theo key của bảng, đổi lại mỗi instance phải lưu toàn bộ bảng. KTable-KTable join tạo view trạng thái được cập nhật từ cả hai phía.

Khi thiết kế topology, hãy bắt đầu từ semantics của dữ liệu, sau đó kiểm tra key, Serde, partitioning, kích thước state, chi phí repartition và khả năng khôi phục. Chọn đúng abstraction giúp kết quả join đúng với nghiệp vụ và giữ chi phí vận hành trong giới hạn.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| KStream | Abstraction chuỗi record, mỗi record là một event độc lập. |
| KTable | Abstraction trạng thái mới nhất theo key, được duy trì từ changelog. |
| GlobalKTable | Bảng trạng thái đầy đủ được replicate trên mỗi Kafka Streams instance. |
| Changelog | Chuỗi cập nhật biểu diễn thay đổi trạng thái theo key. |
| Tombstone | Record có key và Kafka value null, dùng để xóa key khỏi table state. |
| State store | Kho trạng thái local mà topology dùng để tra cứu và aggregate. |
| Changelog topic | Topic lưu thay đổi state store để hỗ trợ khôi phục. |
| Co-partitioning | Điều kiện các input partition cùng key được route tương ứng ở hai phía join. |
| Repartition | Ghi và đọc lại stream theo key mới để phân phối record đúng partition. |
| KeyValueMapper | Hàm chọn lookup key cho KStream-GlobalKTable join. |
| ValueJoiner | Hàm kết hợp giá trị từ hai phía join. |
| Materialization | Việc lưu kết quả table hoặc aggregation vào state store. |
| application.id | Định danh Kafka Streams application và namespace tài nguyên nội bộ. |
| TopologyTestDriver | Công cụ kiểm thử topology Kafka Streams không cần broker thật cho test logic. |

