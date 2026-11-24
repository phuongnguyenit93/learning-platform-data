# Topology xử lý và vai trò applicationId

Kafka Streams biến các phép xử lý event thành một **topology**: đồ thị có hướng gồm các nguồn đọc topic, các bước xử lý và các đích ghi kết quả. Topology mô tả dữ liệu đi qua những bước nào, được nhóm theo key ra sao, trạng thái nào cần lưu và kết quả được phát tới đâu. Kafka Streams chạy topology trên nhiều task và thread, phối hợp các instance thông qua Kafka.

Trong Spring Cloud Stream Kafka Streams binder, một bean Function hoặc Consumer nhận KStream, KTable hay GlobalKTable sẽ được binder nối với các input/output binding tương ứng. Kafka Streams vẫn là runtime xử lý thật sự; binder đảm nhiệm việc ánh xạ function, topic, Serde và cấu hình ứng dụng.

Thuộc tính **application.id** định danh một ứng dụng Kafka Streams logic. Nó quyết định nhóm consumer dùng để phối hợp các instance, namespace của các topic nội bộ và thư mục state cục bộ. Cấu hình đúng application.id là điều kiện để scale, phục hồi state và triển khai nhiều topology mà không làm chúng giành tài nguyên của nhau.

## 1. Topology là đồ thị xử lý event

Một topology thường có ba loại node:

- **Source:** đọc record từ một hoặc nhiều Kafka topic.
- **Processor:** lọc, biến đổi, phân nhánh, nối, gom nhóm hoặc cập nhật state.
- **Sink:** ghi record kết quả vào Kafka topic hoặc chuyển cho một sink processor.

Ví dụ luồng xử lý đơn hàng:

~~~text
orders.raw
    |
    v
[Source: KStream]
    |
    v
[filter: bỏ record không hợp lệ]
    |
    v
[mapValues: chuẩn hóa dữ liệu]
    |
    v
[Processor: nhóm theo customerId]
    |
    +------> [State store + changelog]
    |
    v
[Sink]
    |
    v
orders.summary
~~~

Topology được xây dựng từ code khi ứng dụng khởi động. Khi topology chạy, Kafka Streams chia nó thành các task dựa trên partition của topic đầu vào và phân công task cho các stream thread trên các instance đang tham gia cùng ứng dụng.

Một task xử lý một phần dữ liệu được xác định bởi các partition nguồn. Nhiều task có thể chạy song song trên nhiều thread và nhiều instance. Khi số instance thay đổi, Kafka Streams rebalance và phân công lại task.

Topology là mô tả logic xử lý. Task, thread và instance là cách runtime thực thi topology đó. Không nên nhầm một function bean với một Kafka partition hoặc một pod.

## 2. Source, processor và sink trong Kafka Streams DSL

Kafka Streams DSL xây dựng topology bằng các phép biến đổi nối tiếp nhau.

| Nhóm thao tác | Ví dụ | Tác dụng |
|---|---|---|
| Đọc dữ liệu | stream, table, globalTable | Tạo source từ topic |
| Lọc và biến đổi không state | filter, map, mapValues, flatMapValues | Xử lý từng record độc lập |
| Phân nhánh và hợp nhất | split, branch, merge | Chia luồng theo điều kiện hoặc nhập nhiều luồng |
| Gom nhóm | groupBy, groupByKey | Xác định key dùng cho aggregation |
| Tính toán có state | count, aggregate, reduce | Duy trì kết quả tích lũy |
| Join | join, leftJoin, outerJoin | Kết hợp stream và table |
| Cửa sổ thời gian | windowedBy | Gom record theo khoảng thời gian |
| Ghi kết quả | to | Ghi stream ra topic |

Ví dụ topology chỉ gồm phép biến đổi không state:

~~~java
KStream<String, String> normalized = builder
    .stream("orders.raw")
    .filter((key, value) -> key != null && value != null)
    .mapValues(String::trim)
    .filter((key, value) -> !value.isBlank());

normalized.to("orders.normalized");
~~~

Mỗi record được lọc và chuẩn hóa độc lập. Topology này không cần state store để nhớ kết quả của record trước đó.

Khi cần đếm số event theo khách hàng, topology phải giữ state:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.state.KeyValueStore;

KTable<String, Long> orderCounts = builder
    .stream("orders.events")
    .groupByKey(Grouped.with(Serdes.String(), Serdes.String()))
    .count(
        Materialized
            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                "orders-per-customer"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
    );

orderCounts.toStream().to(
    "orders.counts",
    Produced.with(Serdes.String(), Serdes.Long())
);
~~~

Mỗi event mới làm tăng số đếm của key tương ứng. Kafka Streams giữ giá trị hiện tại trong state store và phát changelog để có thể phục hồi state sau sự cố.

## 3. Phân biệt KStream, KTable và GlobalKTable

Kafka Streams DSL cung cấp ba kiểu dữ liệu quan trọng. Spring Cloud Stream Kafka Streams binder có thể bind các kiểu này trực tiếp với input topic.

| Kiểu | Ý nghĩa | Cách diễn giải record |
|---|---|---|
| KStream | Dòng event liên tục | Mỗi record là một sự kiện độc lập |
| KTable | Bảng trạng thái theo key | Record mới cập nhật giá trị hiện tại của key |
| GlobalKTable | Bảng trạng thái được sao chép tới mỗi instance | Mỗi instance có bản sao đầy đủ để tra cứu theo key |

### KStream: chuỗi sự kiện

Giả sử topic có hai record:

~~~text
key=customer-42, value=5
key=customer-42, value=3
~~~

Với KStream, đây là hai event độc lập. Nếu cộng giá trị, kết quả là 8. Record thứ hai không ghi đè record thứ nhất.

KStream phù hợp với giao dịch, lượt truy cập, log, sự kiện tạo đơn hàng và các dữ liệu mà mỗi record đều có ý nghĩa riêng.

### KTable: trạng thái mới nhất theo key

Với KTable, hai record trên có ý nghĩa cập nhật cùng một hàng. Giá trị cuối cùng của customer-42 là 3.

~~~text
customer-42 -> ACTIVE
customer-42 -> SUSPENDED
customer-42 -> null
~~~

Record có value null là tombstone, biểu thị xóa key khỏi KTable. Vì vậy KTable thường phù hợp với topic chứa changelog hoặc trạng thái hiện hành được đồng bộ từ database.

### GlobalKTable: bản sao toàn cục

GlobalKTable sao chép dữ liệu của topic tới mọi instance của ứng dụng. Nó hữu ích khi mỗi stream task cần tra cứu bảng tham chiếu nhỏ như danh mục sản phẩm hoặc cấu hình khu vực mà không phải thực hiện co-partitioned join thông thường.

Đổi lại, mỗi instance phải nhận và lưu toàn bộ dữ liệu GlobalKTable. Với bảng lớn, chi phí mạng, bộ nhớ và thời gian khởi động có thể tăng đáng kể.

Chọn kiểu dữ liệu đầu vào theo semantics của topic. Không dùng KTable chỉ vì topic có key; phải xác định record là event độc lập hay bản cập nhật trạng thái hiện hành.

## 4. Stateless và stateful processing

Phép xử lý stateless chỉ cần record hiện tại. Ví dụ filter, map và mapValues. Khi một task chuyển sang instance khác, không cần khôi phục dữ liệu tích lũy do các phép xử lý này không giữ state nghiệp vụ.

Phép xử lý stateful cần nhớ thông tin từ các record trước:

- Count và aggregate theo key.
- Reduce giá trị của một nhóm.
- Join hai luồng theo key và cửa sổ thời gian.
- Join stream với KTable để bổ sung dữ liệu tham chiếu.
- Windowed aggregation theo thời gian event.

Kafka Streams tự tạo state store khi dùng các phép DSL cần state. State store có thể nằm trong bộ nhớ hoặc trên đĩa cục bộ, tùy loại store và cấu hình.

Ví dụ đếm event theo customer:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.state.KeyValueStore;

StreamsBuilder builder = new StreamsBuilder();
KStream<String, String> orders = builder.stream("orders.events");

KTable<String, Long> counts = orders
    .groupByKey(Grouped.with(Serdes.String(), Serdes.String()))
    .count(
        Materialized
            .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                "orders-per-customer"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
    );
~~~

Tên store là orders-per-customer. Tên ổn định giúp quan sát topology, cấu hình store và truy vấn state có chủ đích.

Nếu xuất kết quả KTable ra output topic, có thể chuyển thành KStream bằng toStream:

~~~java
KStream<String, Long> countUpdates = counts.toStream();
countUpdates.to(
    "orders.counts",
    Produced.with(Serdes.String(), Serdes.Long())
);
~~~

KTable biểu diễn giá trị hiện tại. KStream sinh ra từ toStream biểu diễn các lần cập nhật của bảng. Consumer downstream cần hiểu rằng mỗi record là một bản cập nhật số đếm, không phải một event đếm độc lập.

## 5. Key, repartition và join

Kafka phân phối record vào partition dựa trên key và partitioner. Trong Kafka Streams, nhiều phép tính stateful được thực hiện theo key. Các record cùng key cần được xử lý tại cùng partition/task để phép tính có kết quả đúng.

Khi thay đổi key, ví dụ dùng selectKey hoặc groupBy để chuyển từ orderId sang customerId, topology có thể cần repartition trước phép tính tiếp theo. Repartition ghi record vào một topic nội bộ rồi đọc lại theo key mới.

~~~text
orders topic
    |
    v
key = orderId
    |
    v
selectKey(customerId)
    |
    v
repartition topic
    |
    v
groupByKey(customerId)
    |
    v
aggregate
~~~

Không phải mọi phép map đều làm thay đổi key. mapValues chỉ đổi value nên giữ nguyên key. map có thể thay cả key và value. Hãy kiểm tra key sau mỗi bước trước khi thực hiện group hoặc join.

Hai đầu vào của join phải được phân phối tương thích. Nếu hai topic có số partition hoặc partitioner khác nhau, Kafka Streams không thể tự bảo đảm các record cùng key nằm ở cùng task. Cần repartition một phía hoặc cả hai phía theo cùng quy tắc trước khi join.

Với join theo thời gian, phải xác định rõ:

- Timestamp nào được dùng làm event time.
- Cửa sổ join bắt đầu và kết thúc khi nào.
- Grace period cho record đến trễ.
- Retention của state store.
- Cách xử lý record đến ngoài cửa sổ.

Không đặt window quá rộng nếu không cần thiết vì state store phải giữ nhiều dữ liệu hơn. Cũng không chọn grace period quá ngắn nếu nguồn có độ trễ đáng kể.

## 6. Dùng topology qua Spring Cloud Stream Kafka Streams binder

Kafka Streams binder cung cấp cách kết nối Kafka Streams DSL với mô hình function của Spring Cloud Stream.

Thêm dependency binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

Function bean có thể dùng các kiểu sau:

| Kiểu function | Vai trò |
|---|---|
| Consumer<KStream<K, V>> | Nhận một stream và xử lý, không khai báo output binding |
| Function<KStream<K, V>, KStream<K2, V2>> | Nhận stream, biến đổi và phát stream |
| BiFunction<KStream<K, V>, KTable<K2, V2>, KStream<K3, V3>> | Nhận hai input khác kiểu |
| BiConsumer<KStream<K, V>, KTable<K2, V2>> | Nhận hai input, không khai báo output |

Binder tạo tên binding theo tên function bean:

- normalizeOrders-in-0: input đầu tiên.
- normalizeOrders-out-0: output đầu tiên.
- enrichOrders-in-1: input thứ hai của function enrichOrders.

Với function nhiều input, chỉ số binding phản ánh vị trí tham số. Ví dụ BiFunction có hai input sẽ tạo in-0 và in-1.

### Ví dụ function chuẩn hóa đơn hàng

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderTopology {

    @Bean
    Function<KStream<String, String>, KStream<String, String>>
            normalizeOrders() {

        return orders -> orders
            .filter((key, value) -> key != null && value != null)
            .mapValues(String::trim)
            .filter((key, value) -> !value.isBlank());
    }
}
~~~

Function này đọc dữ liệu từ input binding, loại record không hợp lệ, chuẩn hóa value rồi phát kết quả qua output binding.

Cấu hình binding và application ID:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrders

    stream:
      bindings:
        normalizeOrders-in-0:
          destination: orders.raw

        normalizeOrders-out-0:
          destination: orders.normalized

      kafka:
        streams:
          binder:
            brokers: localhost:9092
            applicationId: orders-normalizer-v1
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              default.value.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Ở đây:

- Function definition chọn function cần kích hoạt.
- Input binding đọc topic orders.raw.
- Output binding ghi topic orders.normalized.
- applicationId xác định ứng dụng Kafka Streams logic.
- default.key.serde và default.value.serde khai báo Serde mặc định cho key và value.

Nếu dùng DTO, Avro, Protobuf hoặc kiểu dữ liệu riêng, cần khai báo Serde tương ứng. Không giả định StringSerde có thể serialize một object Java.

### Ví dụ function có hai input

Một topology có thể kết hợp event stream với bảng trạng thái khách hàng:

~~~java
@Bean
BiFunction<
        KStream<String, String>,
        KTable<String, String>,
        KStream<String, String>> enrichOrders() {

    return (orders, customers) -> orders
        .leftJoin(
            customers,
            (order, customerStatus) ->
                order + "|customerStatus=" + customerStatus
        );
}
~~~

Binder tạo hai input binding:

- enrichOrders-in-0 trỏ tới topic đơn hàng và được bind thành KStream.
- enrichOrders-in-1 trỏ tới topic trạng thái khách hàng và được bind thành KTable.
- enrichOrders-out-0 là output stream.

Ví dụ trên minh họa phép join. Trong ứng dụng thực tế, hãy định nghĩa DTO, Serde, null handling và chính sách dữ liệu không tìm thấy rõ ràng. Hai input phải có key và partitioning tương thích để join đúng.

## 7. application.id là gì?

Kafka Streams yêu cầu application.id cho mỗi ứng dụng xử lý stream. Đây là định danh của một **logical stream-processing application** trong một Kafka cluster.

application.id có nhiều vai trò cùng lúc:

| Vai trò | Cách Kafka Streams sử dụng |
|---|---|
| Consumer group | Là group.id để điều phối các instance và phân công task |
| Client ID | Là tiền tố cho client ID mặc định của consumer/producer nội bộ |
| Local state directory | Tạo thư mục con trong state.dir |
| Internal topics | Là tiền tố namespace của topic nội bộ như changelog và repartition |
| Quản lý ứng dụng | Phân biệt một ứng dụng stream với các ứng dụng khác |

Vì application.id được dùng ở nhiều lớp, nó không chỉ là tên hiển thị của service. Thay đổi giá trị này có thể làm thay đổi group consumer, internal topic namespace và state cục bộ mà ứng dụng sử dụng.

Kafka Streams cũng dùng application.id làm consumer group ID. Vì thế có thể dùng công cụ Kafka consumer groups để kiểm tra trạng thái và lag của ứng dụng theo application.id.

application.id không tự bật exactly-once processing. Nếu topology cần semantics exactly-once, phải cấu hình processing.guarantee phù hợp với phiên bản Kafka Streams và kiểm tra yêu cầu broker, transaction và sink. Danh tính ứng dụng và bảo đảm xử lý là hai phần cấu hình khác nhau.

## 8. Quy tắc quan trọng: cùng ứng dụng thì cùng application.id

Giả sử ứng dụng order-enricher có ba replica:

~~~text
application.id = order-enricher-prod-v1

Replica A --------\
Replica B ---------+---- Consumer group order-enricher-prod-v1
Replica C --------/              |
                                 v
                      Kafka phân công các task
                      theo partition và topology
~~~

Ba replica phải dùng cùng application.id. Kafka Streams xem chúng là các instance của cùng một ứng dụng, phối hợp membership và chia task.

Nếu mỗi pod tự thêm tên riêng vào application.id:

~~~text
order-enricher-pod-a
order-enricher-pod-b
order-enricher-pod-c
~~~

Kafka sẽ xem đây là ba ứng dụng độc lập. Mỗi ứng dụng có consumer group và state riêng, vì vậy mỗi ứng dụng có thể đọc lại toàn bộ input partitions và phát kết quả trùng lặp.

Quy tắc thực tế:

- Các replica của cùng một topology production dùng cùng application.id.
- Hai topology độc lập cần application.id khác nhau.
- Không thêm pod name, hostname hoặc instance ID vào application.id của các replica cùng ứng dụng.
- Các môi trường cùng dùng một Kafka cluster nên có namespace riêng, ví dụ orders-enricher-dev và orders-enricher-prod.
- Đặt tên dễ nhận biết, ổn định và dùng ký tự chữ/số, dấu chấm, gạch ngang hoặc gạch dưới.

Không dùng application.id giống nhau cho hai processor logic khác nhau chỉ vì chúng nằm trong cùng một Spring Boot project. Mỗi processor Kafka Streams cần định danh phù hợp với topology và state mà nó quản lý.

## 9. Cấu hình applicationId trong Spring Cloud Stream binder

Spring Cloud Stream Kafka Streams binder cho phép khai báo application ID theo hai cách chính.

### Một processor trong ứng dụng

Nếu ứng dụng chỉ có một Kafka Streams processor, có thể đặt ở cấp binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: orders-normalizer-prod-v1
~~~

Có thể dùng spring.application.name làm giá trị tiện lợi cho processor đơn. Tuy vậy, production nên cấu hình applicationId rõ ràng để tránh việc đổi tên ứng dụng Spring ngoài ý muốn làm thay đổi danh tính Kafka Streams.

Nếu không khai báo applicationId, binder có thể tự tạo một ID tĩnh theo tên function bean, ví dụ process-applicationID. Cách này tiện khi thử nghiệm và vẫn ổn định qua restart, nhưng không nên dựa vào giá trị tự sinh cho production vì đổi tên function có thể làm đổi danh tính ứng dụng. Hãy đặt ID tường minh trong cấu hình môi trường.

### Nhiều processor trong cùng Spring Boot application

Giả sử ứng dụng có hai function độc lập:

~~~java
@Bean
Function<KStream<String, String>, KStream<String, String>>
        normalizeOrders() {
    return input -> input.mapValues(String::trim);
}

@Bean
Function<KStream<String, String>, KStream<String, String>>
        redactOrders() {
    return input -> input.mapValues(value ->
        value.replace("secret", "***")
    );
}
~~~

Mỗi function tạo một Kafka Streams processor riêng. Cần cấp application ID riêng cho từng function:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrders;redactOrders

    stream:
      kafka:
        streams:
          binder:
            functions:
              normalizeOrders:
                applicationId: orders-normalizer-prod-v1

              redactOrders:
                applicationId: orders-redactor-prod-v1
~~~

Cấu hình theo function giúp mỗi processor có consumer group và internal topic namespace riêng. Các replica của normalizeOrders cùng dùng orders-normalizer-prod-v1; các replica của redactOrders cùng dùng orders-redactor-prod-v1.

Không đặt một applicationId toàn cục rồi mong binder tự tạo namespace riêng cho nhiều function. Nếu có nhiều processor, hãy khai báo applicationId theo function bean name.

Thuộc tính binder-level configuration áp dụng cho toàn bộ processor trong ứng dụng. Vì vậy, không đặt một application.id chung trong configuration map khi các function cần ID khác nhau; dùng thuộc tính functions.<function-name>.applicationId dành riêng cho từng function.

Binder cũng có thể đặt applicationId ở binding input trong một số mô hình cũ hoặc khi dùng StreamListener. Với functional model hiện đại, cấu hình functions.<function-name>.applicationId thường dễ quản lý hơn.

## 10. application.id và binding group không phải một khái niệm

Spring Cloud Stream có cấu hình group ở cấp binding cho các binder message-channel thông thường. Kafka Streams lại dùng application.id làm danh tính consumer group của Kafka Streams runtime.

Đối với Kafka Streams binder, hãy cấu hình applicationId theo hướng dẫn của binder. Không dựa vào một group property thông thường để thay thế applicationId bắt buộc.

Cần phân biệt:

| Thuộc tính | Mục đích |
|---|---|
| application.id | Danh tính logical Kafka Streams application; điều phối task và state |
| Function bean name | Tên function trong Spring context; binder dùng để tạo binding mặc định và cấu hình per-function |
| Binding name | Tên input/output binding, ví dụ process-in-0 |
| Topic | Nơi chứa record đầu vào hoặc đầu ra |
| Pod/instance name | Nhận diện một bản triển khai cụ thể; không dùng làm application.id chung của replica |

Một function bean có thể đọc nhiều topic thông qua nhiều input binding nhưng vẫn là một Kafka Streams application với một applicationId. Ngược lại, một Spring Boot process có nhiều function Kafka Streams có thể tạo nhiều ứng dụng logic, mỗi ứng dụng có applicationId riêng.

## 11. application.id ảnh hưởng đến state store và internal topics

Stateful topology cần lưu state để tính toán. Kafka Streams thường lưu state cục bộ trên instance và ghi changelog vào Kafka để phục hồi.

~~~text
Topology
   |
   +---- State store: orders-per-customer
   |          |
   |          +---- Local state directory
   |          |
   |          +---- Changelog topic
   |
   +---- Repartition processor
              |
              +---- Repartition topic
~~~

Các topic nội bộ có thể gồm:

- Changelog topic: lưu thay đổi của state store để khôi phục state.
- Repartition topic: phân phối lại record theo key mới để các bước stateful hoặc join xử lý đúng.

application.id là tiền tố namespace cho các topic nội bộ này. Nhờ đó hai ứng dụng độc lập không ghi đè state hoặc repartition data của nhau.

State store cục bộ nằm dưới thư mục state.dir, mặc định thường là /tmp/kafka-streams. Kafka Streams tạo thư mục con theo application.id và task. Nếu nhiều instance dùng chung filesystem, state.dir của từng instance phải được đặt sao cho không ghi vào cùng một thư mục.

Không đặt cùng một thư mục state.dir dùng chung cho nhiều instance đang chạy đồng thời. Mỗi instance cần vùng local state riêng để tránh xung đột file và dữ liệu RocksDB.

## 12. Phục hồi state khi restart hoặc rebalance

Khi một instance bị dừng, task của nó có thể được chuyển sang instance khác. Instance mới cần state để tiếp tục tính toán.

Quá trình phục hồi thường diễn ra như sau:

1. Kafka Streams nhận task assignment từ group coordinator.
2. Instance kiểm tra local state store tương ứng.
3. Nếu local state hợp lệ và còn dùng được, nó có thể tiếp tục từ state hiện có.
4. Nếu state thiếu hoặc không hợp lệ, Kafka Streams restore từ changelog topic.
5. Khi restore hoàn tất, task tiếp tục xử lý input theo offset đã commit.

Vì application.id xác định namespace changelog và consumer group, các replica phải dùng cùng ID để phối hợp và phục hồi đúng state.

Khi scale out, task có thể được chuyển sang replica mới. Khi scale in, task được chuyển sang replica còn lại. State restoration có thể tạo độ trễ trong giai đoạn rebalance; với topology lớn, cần theo dõi thời gian restore và kích thước changelog.

Không xóa local state hoặc changelog topic trong lúc ứng dụng đang chạy. Việc đó có thể làm state không nhất quán và khiến topology không phục hồi được theo cách dự kiến.

## 13. Scale ứng dụng và giới hạn song song

Số replica không tự động tạo thêm partition cho topic. Mức song song của Kafka Streams bị giới hạn bởi số task có thể tạo từ partition của các topic nguồn và topology.

Ví dụ topic có bốn partition:

~~~text
orders.events: 4 partitions

3 replicas, mỗi replica 1 stream thread
    |
    +-- Replica A: một số task
    +-- Replica B: một số task
    +-- Replica C: một số task

Nếu số task chỉ là 4, tổng cộng chỉ có 4 task hoạt động.
Tăng replica vượt quá số task không tạo thêm task xử lý.
~~~

Có thể điều chỉnh số stream thread trên mỗi instance bằng cấu hình StreamsConfig như num.stream.threads. Tuy nhiên, tăng thread không thay thế việc thiết kế số partition phù hợp.

Khi lập kế hoạch scale:

- Xác định số partition của các topic nguồn.
- Xác định số task thực tế mà topology tạo ra.
- Cân nhắc số replica và num.stream.threads.
- Đo CPU, memory, network, state restore và processing latency.
- Theo dõi rebalance khi thêm/bớt instance.
- Đảm bảo state.dir là vùng local riêng của từng instance.

Với join nhiều input, số partition và partitioner của các nguồn cần tương thích. Một topic có nhiều partition hơn không tự động làm join chính xác hoặc tăng throughput nếu các input không co-partitioned.

## 14. Khi nào giữ nguyên hoặc thay đổi application.id?

Đây là quyết định triển khai quan trọng.

| Tình huống | Cách xử lý |
|---|---|
| Restart cùng ứng dụng | Giữ nguyên application.id |
| Scale thêm replica cùng topology | Giữ nguyên application.id |
| Thay đổi số replica | Giữ nguyên application.id |
| Hai topology độc lập cùng đọc một topic | Dùng application.id khác nhau |
| Chạy canary song song với ứng dụng cũ | Dùng ID khác nếu muốn hai nhóm xử lý độc lập; cô lập output để tránh ghi trùng |
| Tạo ứng dụng mới và không dùng state cũ | Dùng application.id mới, lập kế hoạch input offset và output |
| Muốn replay từ đầu | Dùng quy trình reset có kiểm soát; không chỉ đổi tên application.id |

### Giữ application.id khi muốn tiếp tục state cũ

Khi giữ nguyên ID, ứng dụng tiếp tục sử dụng consumer group và internal topic namespace hiện có. State store có thể được khôi phục từ changelog, còn input offsets tiếp tục từ vị trí đã commit.

Khi thay đổi topology, phải đánh giá khả năng tương thích của state store, changelog và repartition topics. Nếu topology mới không thể dùng state cũ, cần một kế hoạch migration hoặc một application ID phiên bản mới.

### Đổi application.id tạo ra một ứng dụng logic mới

Khi dùng ID mới, Kafka Streams tạo consumer group và namespace internal topics mới. Ứng dụng không kế thừa committed offsets của ID cũ. Nếu chưa có offset cho group mới, vị trí bắt đầu do auto.offset.reset quyết định; Kafka Streams và Kafka Streams binder mặc định dùng earliest trong các cấu hình được tài liệu hóa.

Điều đó có nghĩa ứng dụng mới có thể đọc lại lịch sử input và phát lại output. Nếu output topic vẫn là topic cũ, consumer downstream có thể nhận các kết quả trùng với ứng dụng trước.

Trước khi đổi ID, cần xác định:

- Input sẽ đọc từ earliest hay latest.
- Output topic có cần tách phiên bản hay không.
- Downstream có thể nhận record lặp hay không.
- State cũ có cần giữ để đối soát không.
- Internal topics cũ sẽ được giữ hay xóa theo kế hoạch.
- Khi nào có thể dừng và thu hồi ứng dụng cũ.

Đừng thay application.id chỉ để phân biệt pod hoặc lần triển khai. Việc đó tạo một consumer group độc lập và có thể khiến dữ liệu được xử lý lại.

## 15. Reset ứng dụng để replay dữ liệu từ đầu

Kafka có công cụ Kafka Streams application reset để đưa ứng dụng về trạng thái xử lý lại. Đây là thao tác vận hành có ảnh hưởng tới offsets và internal topics, cần thực hiện có kế hoạch.

Công cụ reset có thể:

- Đưa input topic offsets về vị trí đã chọn, mặc định là đầu topic.
- Xóa internal topics được xác định là thuộc ứng dụng, bao gồm changelog/repartition topics theo phạm vi công cụ.
- Xóa committed offsets gắn với internal topics.

Công cụ reset không tự xóa output topic và không tự xóa local state trên máy chạy ứng dụng. Vì vậy output downstream có thể vẫn chứa kết quả cũ, còn local state phải được dọn theo quy trình phù hợp.

Quy trình an toàn:

1. Dừng tất cả instance của application.id cần reset.
2. Xác nhận consumer group không còn member hoạt động.
3. Chạy Kafka Streams application reset với chế độ dry-run để xem các thay đổi.
4. Kiểm tra chính xác application.id, input topics và internal topics.
5. Chọn vị trí input offset cần replay.
6. Chạy reset thật sau khi đã xác nhận.
7. Dọn local state directory của các instance theo hướng dẫn.
8. Xem xét output topic và downstream consumer trước khi khởi động lại.
9. Theo dõi restore state, consumer lag và output sau khi ứng dụng chạy.

Ví dụ lệnh dry-run:

~~~bash
bin/kafka-streams-application-reset.sh \
  --application-id orders-normalizer-prod-v1 \
  --bootstrap-server localhost:9092 \
  --dry-run
~~~

Sau khi kiểm tra kế hoạch, có thể chọn reset input về earliest bằng tùy chọn tương ứng của công cụ. Không chạy reset khi một instance vẫn hoạt động. Không giả định chỉ xóa committed offsets là đủ để xóa state cục bộ.

Kafka Streams binder cũng có thuộc tính startOffset để quyết định vị trí đọc khi chưa có committed offset. Thuộc tính resetOffsets của consumer binding thông thường không có tác dụng seek đầu/cuối đối với Kafka Streams binder như với Kafka message-channel binder.

## 16. Quản lý topology version và triển khai blue/green

Topology có thể thay đổi khi thêm processor, đổi key, đổi store hoặc thay đổi aggregation. Những thay đổi này có thể tác động đến internal topics và state store.

Một chiến lược versioning phổ biến là gắn version vào application.id:

~~~text
orders-aggregate-prod-v1
orders-aggregate-prod-v2
~~~

Khi chạy v2 song song với v1:

- Hai phiên bản có consumer group và state độc lập.
- Cả hai có thể đọc cùng input topic.
- Mỗi phiên bản có internal topics riêng.
- Nếu cả hai ghi cùng output topic, downstream có thể nhận kết quả trùng.
- Cần tách output topic hoặc có cơ chế chuyển đổi traffic rõ ràng.
- Sau khi v2 được xác nhận, dừng v1 và xử lý state cũ theo retention/cleanup policy.

Nếu topology chỉ thay đổi code nhưng vẫn tương thích state và cần tiếp tục offset, có thể giữ ID. Tuy nhiên, phải xác minh schema state store, tên store, key/value Serde và topology compatibility trước khi rollout.

Không dùng version suffix một cách máy móc cho mọi bản build. Mỗi lần thay ID đều tạo danh tính ứng dụng mới và có thể làm phát sinh việc đọc lại input.

## 17. Quan sát topology và application.id trong production

Có thể quan sát topology, trạng thái và mức tiêu thụ để xác định ứng dụng có đang chạy đúng hay không.

### Xem topology qua Actuator

Kafka Streams binder cung cấp endpoint lấy mô tả topology:

~~~text
/actuator/kafkastreamstopology
/actuator/kafkastreamstopology/<application-id>
~~~

Để dùng endpoint, ứng dụng cần Spring Boot Actuator và web dependency, đồng thời expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,kafkastreamstopology
~~~

Endpoint mặc định không được expose. Trong production, bảo vệ actuator bằng authentication và network policy; không mở toàn bộ endpoint quản trị ra Internet.

Topology description giúp kiểm tra source, processor, sink, store và repartition node. Dùng nó để đối chiếu topology thực tế với thiết kế, đặc biệt sau khi đổi function hoặc thêm join.

### Theo dõi consumer group

Vì application.id cũng là group ID, có thể kiểm tra lag bằng Kafka CLI:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-normalizer-prod-v1 \
  --describe
~~~

Cần theo dõi:

- Input lag theo partition.
- Số task đang hoạt động và standby.
- Thời gian rebalance.
- Thời gian restore state store.
- Tốc độ xử lý và output throughput.
- Lỗi deserialize, processing exception và producer error.
- Dung lượng changelog/repartition topics.
- Dung lượng local state directory.

Nếu một topology liên tục rebalance, kiểm tra instance restart, session timeout, processing latency, số thread và tình trạng broker. Nếu restore state quá lâu, kiểm tra kích thước changelog, local state và replication.

## 18. Kiểm thử topology và application.id

Có thể kiểm thử ở nhiều cấp độ.

### Unit test với TopologyTestDriver

TopologyTestDriver chạy topology trong bộ nhớ, không cần Kafka broker thật. Test có thể tạo input topic, gửi record và đọc output topic.

Ví dụ kiểm thử một topology chuẩn hóa:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.TopologyTestDriver;
import org.apache.kafka.streams.test.TestInputTopic;
import org.apache.kafka.streams.test.TestOutputTopic;

TopologyTestDriver testDriver =
    new TopologyTestDriver(topology, streamsProperties);

TestInputTopic<String, String> input =
    testDriver.createInputTopic(
        "orders.raw",
        new StringSerializer(),
        new StringSerializer()
    );

TestOutputTopic<String, String> output =
    testDriver.createOutputTopic(
        "orders.normalized",
        new StringDeserializer(),
        new StringDeserializer()
    );

input.pipeInput("order-1", "  PAID  ");

KeyValue<String, String> result = output.readKeyValue();

assertEquals("order-1", result.key);
assertEquals("PAID", result.value);

testDriver.close();
~~~

Ví dụ này tập trung vào logic topology. Test cần khởi tạo topology và Serde tương ứng với code đang kiểm thử.

### Integration test với Kafka thật

Dùng Testcontainers Kafka hoặc broker thử nghiệm để xác minh:

- Binder tạo đúng input/output binding.
- application.id được cấu hình đúng.
- Các replica dùng cùng ID tham gia cùng consumer group.
- Các function độc lập dùng ID khác nhau.
- Internal topics được tạo đúng namespace.
- State được phục hồi sau restart.
- Rebalance không làm mất hoặc nhân đôi hiệu ứng ngoài mong muốn.
- Output topic nhận đúng key, value và số lượng record.

Với test chạy song song, dùng application.id riêng cho từng test nếu chúng dùng chung Kafka cluster. Nếu tái sử dụng cùng ID, test có thể tranh consumer group, internal topics và committed offsets của nhau.

### Kiểm thử state recovery

Đối với topology có aggregation hoặc join:

1. Gửi một tập event và kiểm tra state store/output.
2. Dừng processor sau khi state đã được ghi.
3. Khởi động lại với cùng application.id.
4. Xác nhận Kafka Streams restore state và tiếp tục từ offset đã commit.
5. Gửi event tiếp theo và xác nhận aggregate tiếp tục đúng.

Không chỉ kiểm tra output của lần chạy đầu. Phục hồi state sau restart là một phần cốt lõi của topology stateful.

## 19. Các lỗi thường gặp khi thiết kế topology và application.id

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Mỗi pod đều xử lý toàn bộ input | Mỗi pod dùng application.id khác nhau | Dùng cùng ID cho mọi replica |
| Hai processor tranh state hoặc task | Hai topology độc lập dùng chung application.id | Cấp ID riêng cho từng processor |
| Restart xong đọc lại dữ liệu | application.id thay đổi hoặc group chưa có committed offset | Kiểm tra ID và auto.offset.reset |
| State store restore chậm | Changelog lớn hoặc local state bị mất | Theo dõi restore và cân nhắc standby/state retention |
| Join thiếu hoặc sai dữ liệu | Input không co-partitioned | Repartition theo cùng key và partitioner |
| Tăng replica nhưng throughput không tăng | Số task/partition không đủ | Điều chỉnh partition và thread sau khi đo tải |
| Output xuất hiện trùng sau blue/green | Hai application ID cùng đọc và ghi chung output | Tách output hoặc thiết kế cutover |
| Function không chạy | Chưa kích hoạt function trong function definition | Kiểm tra danh sách function được activate |
| Không đọc được object | Serde không phù hợp với key/value type | Khai báo Serde rõ ràng |
| Reset xong vẫn còn output cũ | Reset tool không xóa output topics | Có kế hoạch xử lý output và downstream |
| Topology không phục hồi sau reset | Local state chưa được dọn hoặc internal topic xử lý sai | Dừng mọi instance và làm đủ các bước reset |

## 20. Checklist trước khi triển khai

| Hạng mục | Câu hỏi |
|---|---|
| Topology | Source, processor, state store và sink có đúng với luồng nghiệp vụ không? |
| Data model | Đầu vào cần KStream, KTable hay GlobalKTable? |
| Key | Key có ổn định và phù hợp với group/join không? |
| Partition | Các input join có co-partitioned không? |
| Serde | Key/value Serde có tương thích với producer và consumer không? |
| application.id | Có duy nhất cho logical processor trong cluster không? |
| Replicas | Tất cả replica của cùng processor có dùng cùng application.id không? |
| Multiple functions | Mỗi function độc lập đã có applicationId riêng chưa? |
| Internal topics | Changelog và repartition topics có replication/retention phù hợp không? |
| Local state | state.dir có riêng cho từng instance không? |
| Upgrade | Thay đổi topology có tương thích state cũ không? |
| Replay | Có quy trình reset, dry-run và kiểm soát output/downstream không? |
| Observability | Có topology endpoint, health, lag, restore time và error metrics không? |
| Tests | Có unit test topology và integration test với Kafka thật không? |

## 21. Bài thực hành và tiêu chí hoàn thành

Xây dựng topology đếm số đơn hàng theo khách hàng:

1. Tạo topic orders.events, dùng customerId làm Kafka key.
2. Tạo function nhận KStream<String, String> bằng Kafka Streams binder.
3. Lọc record không hợp lệ và kiểm tra key.
4. Dùng groupByKey và count để tạo KTable trạng thái số đơn hàng theo khách.
5. Materialize state store với tên orders-per-customer.
6. Chuyển KTable thành KStream và ghi cập nhật ra orders.counts.
7. Cấu hình Serde cho key và value.
8. Đặt applicationId orders-counter-dev-v1.
9. Chạy hai replica cùng applicationId và xác nhận Kafka phân công task trong cùng consumer group.
10. Chạy một processor độc lập với applicationId khác và xác nhận nó có group/state riêng.
11. Dừng một replica, khởi động lại và quan sát rebalance/state restoration.
12. Kiểm tra topology qua Actuator và theo dõi consumer lag.
13. Thử thay applicationId trong môi trường test, quan sát việc tạo group/internal topics mới và vị trí bắt đầu đọc.
14. Thực hiện một reset dry-run và giải thích input offsets, internal topics, output topics và local state bị ảnh hưởng thế nào.

Hoàn thành bài khi có thể mô tả topology dưới dạng source-processor-sink; phân biệt KStream, KTable và GlobalKTable; xác định khi nào cần repartition; giải thích state store và changelog; cấu hình applicationId cho một hoặc nhiều function; và dự đoán đúng tác động khi scale, restart, đổi ID hoặc reset ứng dụng.

## 22. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Kafka Streams Binder Reference](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html) — functional binding, application ID, state store, topology visualization và cấu hình binder.
- [Spring Cloud Stream Kafka Streams Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html) — Function, Consumer, KStream, KTable, GlobalKTable và nhiều input binding.
- [Spring Cloud Stream Kafka Streams Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html) — binder configuration, applicationId toàn cục và per-function.
- [Apache Kafka Streams — Configuring a Streams Application](https://kafka.apache.org/41/streams/developer-guide/config-streams/) — application.id, bootstrap.servers, state.dir và cấu hình runtime.
- [Apache Kafka Streams — Streams DSL](https://kafka.apache.org/41/streams/developer-guide/dsl-api/) — KStream, KTable, stateful/stateless transformations, windowing, join và repartition.
- [Apache Kafka Streams — Processor API](https://kafka.apache.org/41/streams/developer-guide/processor-api/) — processor topology và state stores tùy chỉnh.
- [Apache Kafka Streams — Application Reset Tool](https://kafka.apache.org/41/streams/developer-guide/app-reset-tool/) — reset offsets, internal topics và local state.

