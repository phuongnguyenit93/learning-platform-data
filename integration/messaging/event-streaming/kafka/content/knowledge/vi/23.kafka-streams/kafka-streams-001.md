# Kafka Streams là thư viện ứng dụng và cách triển khai độc lập

Kafka Streams là thư viện Java để xây dựng ứng dụng xử lý dữ liệu liên tục từ Kafka. Nhà phát triển khai báo luồng xử lý trong code, đóng gói ứng dụng như một chương trình Java bình thường rồi chạy trên máy ảo, container hoặc nền tảng triển khai đang dùng.

Kafka Streams không phải một server cluster riêng cần cài đặt và vận hành như Kafka broker. Nó cũng không phải dịch vụ điều phối tài nguyên. Thư viện chạy bên trong JVM của ứng dụng, dùng Kafka producer, consumer và các topic nội bộ để phối hợp nhiều instance, phân phối công việc, lưu trạng thái và phục hồi sau lỗi.

Điểm khác biệt này quyết định cách thiết kế và triển khai:

- **Kafka broker** lưu trữ record, phục vụ producer/consumer và cung cấp replication, transaction, metadata và group coordination.
- **Kafka Streams library** nằm trong ứng dụng Java, thực thi topology xử lý dữ liệu.
- **Streams application instance** là một tiến trình JVM đang chạy ứng dụng có sử dụng thư viện.
- **Stream task** là đơn vị công việc được tạo từ các partition đầu vào và phân phối giữa instance/thread.
- **Internal topics** lưu changelog, repartition và dữ liệu điều phối cần thiết cho ứng dụng Streams.

Bài học này giải thích ranh giới giữa thư viện và tiến trình triển khai, cách viết topology, cấu hình application ID, cách scale instance, cách quản lý state store và cách vận hành ứng dụng Kafka Streams độc lập.

## 1. Kafka Streams là gì?

Kafka Streams là một Java client library cung cấp API xử lý stream. Ứng dụng đọc record từ một hoặc nhiều Kafka topic, áp dụng các phép biến đổi rồi có thể ghi kết quả sang topic khác hoặc tương tác với hệ thống bên ngoài.

Một stream là tập dữ liệu không có điểm kết thúc cố định. Record tiếp tục được thêm vào theo thời gian. Ứng dụng Streams có thể xử lý từng record, lọc, biến đổi, join, group, aggregate hoặc tạo kết quả theo cửa sổ thời gian.

Ví dụ hệ thống thương mại điện tử có các topic:

- **orders**: event đơn hàng được tạo.
- **payments**: event thanh toán.
- **customers**: thông tin khách hàng dạng changelog.
- **order-enriched**: event đơn hàng đã bổ sung dữ liệu khách hàng.
- **daily-revenue**: tổng doanh thu theo ngày.

Một Kafka Streams application có thể đọc orders, kết hợp với bảng khách hàng, tính tổng doanh thu theo ngày và ghi kết quả ra order-enriched hoặc daily-revenue.

~~~mermaid
flowchart LR
    A["orders topic"] --> D["Kafka Streams application"]
    B["customers topic"] --> D
    C["payments topic"] --> D
    D --> E["order-enriched topic"]
    D --> F["daily-revenue topic"]
~~~

Ứng dụng dùng Kafka làm lớp truyền và lưu event. Trạng thái phục vụ phép join/aggregate được quản lý bằng state store cục bộ, còn Kafka lưu changelog để phục hồi trạng thái khi task chuyển sang instance khác.

## 2. Thư viện, ứng dụng và server là ba khái niệm khác nhau

### 2.1. Kafka Streams là thư viện nhúng

Khi thêm dependency **kafka-streams** vào project Java, code có thể dùng các API như:

- **StreamsBuilder** để xây dựng topology bằng DSL.
- **KStream**, **KTable**, **GlobalKTable** để mô hình hóa dữ liệu.
- **Topology** để biểu diễn đồ thị xử lý.
- **KafkaStreams** để khởi động, theo dõi và đóng runtime.
- **Processor API** để viết processor tùy chỉnh.
- State store API để lưu và truy vấn trạng thái cục bộ.

Ứng dụng tự quản lý lifecycle của đối tượng KafkaStreams, cấu hình kết nối Kafka, xử lý shutdown và đóng gói artifact.

### 2.2. Không có Kafka Streams server riêng

Không cần cài một daemon Kafka Streams độc lập trên cluster rồi gửi topology lên đó. Không có thao tác submit job đến một cụm Streams server do Apache Kafka quản lý.

Một tiến trình Java tự tạo KafkaStreams từ topology và config, sau đó gọi start(). Khi cần tăng năng lực, triển khai thêm tiến trình cùng ứng dụng và cùng application.id. Các instance tự tham gia nhóm và chia sẻ task qua Kafka coordination.

### 2.3. Standalone deployment nghĩa là gì?

Trong ngữ cảnh bài học, triển khai độc lập là đóng gói ứng dụng Streams thành artifact có thể chạy riêng như một Java service:

- Chạy bằng java -jar hoặc java -cp.
- Chạy như service được quản lý bởi systemd hoặc Windows Service.
- Chạy trong Docker container.
- Chạy nhiều replica trong Kubernetes hoặc nền tảng container tương tự.
- Chạy trên VM hoặc máy vật lý.

Đây là cách triển khai tiến trình ứng dụng. Nó không phải một chế độ broker hay một server mode đặc biệt của Kafka Streams.

### 2.4. Ranh giới trách nhiệm

| Thành phần | Trách nhiệm |
|---|---|
| Kafka broker cluster | Lưu record, replication, transaction, metadata và group coordination |
| Kafka Streams library | Xây dựng và chạy topology, tạo task/thread, xử lý record, quản lý state store |
| Ứng dụng Java | Cấu hình, khởi động, xử lý lifecycle, logging, health và tích hợp nghiệp vụ |
| Nền tảng triển khai | Cấp CPU/RAM/disk, restart process, networking, secret và rollout |
| Người vận hành | Quản lý topic, ACL, replication, monitoring, capacity và recovery policy |

Kafka Streams không thay thế Kafka broker. Nếu broker ngừng hoạt động, ứng dụng Streams không có nơi để đọc/ghi dữ liệu; nếu ứng dụng Streams dừng, broker vẫn lưu record và các instance khác có thể tiếp tục xử lý.

## 3. Kafka Streams so với Kafka Connect và consumer tự viết

Ba lựa chọn này giải quyết các nhu cầu khác nhau.

| Công cụ | Mục tiêu chính | Ví dụ |
|---|---|---|
| Kafka Connect | Tích hợp và di chuyển dữ liệu giữa Kafka với hệ thống ngoài thông qua connector | Đọc CDC từ database, ghi topic vào Elasticsearch |
| Kafka Streams | Xử lý, kết hợp và tổng hợp event bằng logic ứng dụng | Tính doanh thu, join đơn hàng với khách hàng, phát hiện giao dịch bất thường |
| Kafka Consumer API tự viết | Tự kiểm soát vòng lặp đọc và xử lý record | Một worker đơn giản gọi REST API cho từng event |

Kafka Connect phù hợp khi công việc chủ yếu là ingest/export dữ liệu theo connector có sẵn. Kafka Streams phù hợp khi cần logic xử lý liên tục, có state, join, window hoặc aggregation. Consumer API phù hợp khi cần vòng lặp tùy chỉnh đơn giản và đội phát triển muốn tự quản lý offset, retry, state và partition assignment.

Kafka Streams sử dụng Kafka consumer và producer ở bên dưới nhưng tự quản lý nhiều chi tiết như group coordination, task assignment, offset commit và state recovery. Không nên tạo một consumer riêng để đọc cùng input topic rồi đồng thời cho Streams application đọc lại nếu chưa xác định rõ mục đích và semantics.

## 4. Kiến trúc runtime của Kafka Streams

Một Streams application gồm topology logic, stream threads, tasks và state stores.

~~~mermaid
flowchart TB
    subgraph JVM["Một JVM của ứng dụng"]
        A["KafkaStreams instance"]
        B["StreamThread 1"]
        C["StreamThread 2"]
        D["Task 0"]
        E["Task 1"]
        F["Task 2"]
        G["Local state stores"]
        A --> B
        A --> C
        B --> D
        B --> E
        C --> F
        D --> G
        E --> G
        F --> G
    end
    H["Kafka input partitions"] --> D
    H --> E
    H --> F
    G <--> I["Changelog topics"]
    D --> J["Kafka output topics"]
    E --> J
    F --> J
~~~

### 4.1. Topology

Topology là đồ thị xử lý logic gồm các processor node nối với nhau bằng stream. Nó mô tả ứng dụng cần làm gì:

- Source node đọc từ topic.
- Processor node lọc, biến đổi, join hoặc aggregate.
- Sink node ghi sang topic đích.

Topology là mô tả logic. Khi runtime khởi động, Kafka Streams tạo các bản thực thi của topology theo task và partition được giao.

### 4.2. Stream thread

Mỗi JVM có thể chạy một hoặc nhiều stream thread. Cấu hình **num.stream.threads** xác định số thread xử lý stream trong mỗi instance; mặc định là 1.

Mỗi stream thread có thể thực thi một hoặc nhiều task. Các thread xử lý những task khác nhau, không dùng chung state store mutable giữa các task. Kafka Streams điều phối task và partition assignment.

Tăng thread chỉ hữu ích khi có đủ task và tài nguyên CPU/RAM/disk. Thêm nhiều thread không tự làm một partition xử lý song song nhiều lần.

### 4.3. Task

Task là đơn vị xử lý logic gắn với một nhóm partition đầu vào. Kafka Streams tạo số task dựa trên partition của input topic và topology.

Với một input topic có 6 partition, ứng dụng có thể có tối đa 6 task xử lý độc lập cho luồng đó. Mỗi task xử lý các record của partition được giao theo thứ tự trong partition.

Task là đơn vị mà Kafka Streams di chuyển giữa stream thread và instance khi rebalance hoặc khi một instance gặp lỗi.

### 4.4. Partition quyết định giới hạn song song

Số partition đầu vào là một yếu tố quan trọng quyết định mức song song tối đa. Nếu chỉ có 3 task, chạy 10 instance không tạo ra 10 luồng xử lý hữu ích; một số instance có thể không được giao task và ở trạng thái nhàn rỗi.

Nếu muốn tăng parallelism, phải thiết kế số partition, key distribution và topology phù hợp. Tăng partition sau khi topic đã có dữ liệu cũng cần xem xét tác động đến key-to-partition mapping và ordering.

## 5. Topology DSL và Processor API

Kafka Streams cung cấp hai cách xây dựng topology.

### 5.1. Streams DSL

DSL cung cấp các phép toán phổ biến ở mức cao:

- **filter()** và **filterNot()**: giữ hoặc loại record theo điều kiện.
- **map()** và **mapValues()**: biến đổi key/value.
- **flatMap()** và **flatMapValues()**: tạo nhiều record từ một record.
- **selectKey()**: thay đổi key.
- **groupByKey()** và **groupBy()**: nhóm dữ liệu theo key.
- **count()**, **reduce()**, **aggregate()**: tổng hợp.
- **join()**, **leftJoin()**, **outerJoin()**: kết hợp stream/table.
- **to()** và **through()**: ghi ra topic hoặc tạo điểm trung gian.

Ví dụ:

~~~java
StreamsBuilder builder = new StreamsBuilder();

KStream<String, String> orders =
        builder.stream("orders");

KStream<String, String> validOrders =
        orders.filter((key, value) -> value != null)
              .filter((key, value) -> value.contains("APPROVED"));

validOrders.to("approved-orders");
~~~

DSL phù hợp với phần lớn pipeline xử lý event thông thường. Code tập trung vào ý nghĩa nghiệp vụ thay vì tự viết vòng lặp consume/process/commit.

### 5.2. Processor API

Processor API là API mức thấp hơn, cho phép định nghĩa processor tùy chỉnh, truy cập metadata record, điều khiển forwarding và tương tác với state store.

Dùng Processor API khi:

- Cần logic xử lý đặc thù không biểu diễn gọn bằng DSL.
- Cần truy cập header, timestamp hoặc metadata của record.
- Cần quản lý state store trực tiếp.
- Cần schedule punctuation theo stream time hoặc wall-clock time.
- Cần kiểm soát cách phát một hoặc nhiều output record.

Processor API linh hoạt hơn nhưng yêu cầu code nhiều hơn và nhà phát triển phải hiểu rõ lifecycle, state store và forwarding semantics.

### 5.3. Có thể kết hợp DSL và Processor API

Một topology có thể bắt đầu bằng DSL, sau đó gọi process() hoặc processValues() để đưa một đoạn xử lý tùy chỉnh vào pipeline. Điều này giúp giữ phần lớn logic ở DSL và chỉ dùng Processor API tại nơi thực sự cần quyền kiểm soát thấp hơn.

## 6. KStream, KTable và GlobalKTable

Đây là ba abstraction quan trọng để mô hình hóa dữ liệu.

| Abstraction | Ý nghĩa | Ví dụ |
|---|---|---|
| KStream<K,V> | Chuỗi event; mỗi record là một sự kiện độc lập | OrderCreated, PaymentReceived |
| KTable<K,V> | Bảng trạng thái mới nhất theo key; record mới cập nhật giá trị của key | Trạng thái hiện tại của order |
| GlobalKTable<K,V> | Bảng được sao chép toàn bộ đến từng Streams instance | Bảng quốc gia hoặc danh mục nhỏ |

### 6.1. KStream

KStream phù hợp với event log. Nếu cùng một key xuất hiện nhiều lần, mỗi record vẫn là một event cần xử lý.

Ví dụ:

~~~text
key=order-1, value=CREATED
key=order-1, value=PAID
key=order-1, value=SHIPPED
~~~

Ba record biểu diễn ba sự kiện khác nhau của cùng đơn hàng.

### 6.2. KTable

KTable biểu diễn trạng thái mới nhất theo key. Với chuỗi record cùng key:

~~~text
key=order-1, value=CREATED
key=order-1, value=PAID
key=order-1, value=SHIPPED
~~~

Giá trị hiện tại của order-1 là SHIPPED. Record mới cập nhật giá trị cũ. KTable thường được xây dựng từ topic dạng changelog và có thể lưu trạng thái trong state store.

### 6.3. GlobalKTable

GlobalKTable đọc tất cả partition của topic và giữ bản sao đầy đủ ở mỗi Streams instance. Điều này hữu ích khi cần tra cứu theo key khác với key partition của stream hoặc muốn join với bảng nhỏ không cần co-partition.

Đánh đổi là mỗi instance phải lưu toàn bộ bảng, đọc nhiều dữ liệu hơn và tiêu tốn network, storage, CPU. Không nên dùng GlobalKTable cho bảng rất lớn nếu KTable partitioned có thể đáp ứng yêu cầu.

### 6.4. Stream-table duality

Một stream có thể được xem là changelog của một bảng. Một bảng có thể được xem là snapshot trạng thái mới nhất sau khi áp dụng changelog.

Kafka Streams dùng mối quan hệ này để xây dựng aggregation, join và state store. Ví dụ đếm số đơn hàng theo khách hàng tạo ra một KTable lưu tổng hiện tại cho từng customer ID.

## 7. Thêm Kafka Streams vào project Java

Kafka Streams là thư viện Java nên project cần dependency của Kafka Streams và Kafka client tương ứng.

Ví dụ Maven dùng Apache Kafka 4.4.0:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.kafka</groupId>
        <artifactId>kafka-streams</artifactId>
        <version>4.4.0</version>
    </dependency>

    <dependency>
        <groupId>org.apache.kafka</groupId>
        <artifactId>kafka-clients</artifactId>
        <version>4.4.0</version>
    </dependency>

    <dependency>
        <groupId>org.apache.kafka</groupId>
        <artifactId>kafka-streams-test-utils</artifactId>
        <version>4.4.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Khi dùng Spring Boot hoặc BOM quản lý dependency, hãy để dependency management khóa version tương thích và tránh override kafka-streams khác release line với kafka-clients.

Ứng dụng cần serializer/deserializer phù hợp với wire format của topic. Kafka Streams cung cấp Serdes có sẵn như String, Long, Integer, ByteArray và một số kiểu cơ bản. Với JSON, Avro hoặc Protobuf, cần chọn Serde tương ứng và bảo đảm producer/consumer cùng hiểu định dạng.

## 8. Ví dụ một ứng dụng Kafka Streams độc lập

Ví dụ sau đọc chuỗi từ topic orders, loại bỏ record null, chuẩn hóa nội dung và ghi sang orders-normalized.

~~~java
package com.example.streams;

import java.time.Duration;
import java.util.Locale;
import java.util.Properties;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Produced;

public class OrdersNormalizerApplication {

    public static void main(String[] args) {
        Properties props = new Properties();
        String bootstrapServers = System.getenv().getOrDefault(
            "KAFKA_BOOTSTRAP_SERVERS",
            "localhost:9092"
        );
        String applicationId = System.getenv().getOrDefault(
            "KAFKA_STREAMS_APPLICATION_ID",
            "orders-normalizer-v1"
        );
        String stateDir = System.getenv().getOrDefault(
            "KAFKA_STREAMS_STATE_DIR",
            "/var/lib/orders-normalizer"
        );

        props.put(
            StreamsConfig.APPLICATION_ID_CONFIG,
            applicationId
        );
        props.put(
            StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
        );
        props.put(
            StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
            Serdes.String().getClass().getName()
        );
        props.put(
            StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
            Serdes.String().getClass().getName()
        );

        props.put(
            StreamsConfig.NUM_STREAM_THREADS_CONFIG,
            2
        );
        props.put(
            StreamsConfig.STATE_DIR_CONFIG,
            stateDir
        );

        StreamsBuilder builder = new StreamsBuilder();

        KStream<String, String> orders = builder.stream(
            "orders",
            Consumed.with(Serdes.String(), Serdes.String())
        );

        KStream<String, String> normalized = orders
            .filter((key, value) -> value != null)
            .mapValues(value -> value.trim().toUpperCase(Locale.ROOT));

        normalized.to(
            "orders-normalized",
            Produced.with(Serdes.String(), Serdes.String())
        );

        Topology topology = builder.build();

        System.out.println(topology.describe());

        KafkaStreams streams = new KafkaStreams(topology, props);

        streams.setStateListener((newState, oldState) -> {
            System.out.println(
                "Kafka Streams state changed from "
                    + oldState + " to " + newState
            );
        });

        Runtime.getRuntime().addShutdownHook(
            new Thread(() -> streams.close(Duration.ofSeconds(30)))
        );

        streams.start();
    }
}
~~~

Ví dụ trên minh họa một ứng dụng có thể chạy độc lập bằng JVM. Trong production, cần bổ sung cấu hình security, exception handlers, metrics, logging, Serdes thực tế và resource limits phù hợp.

StreamsBuilder tạo topology. KafkaStreams khởi tạo runtime, tham gia nhóm theo application.id, tạo task và bắt đầu xử lý. Shutdown hook gọi close() để đóng client và giải phóng tài nguyên theo cách có kiểm soát.

## 9. Cấu hình quan trọng của Kafka Streams

Hai cấu hình bắt buộc:

| Config | Ý nghĩa |
|---|---|
| application.id | Định danh logic của Streams application |
| bootstrap.servers | Địa chỉ broker để kết nối cluster |

Các cấu hình thường dùng khác:

| Config | Ý nghĩa |
|---|---|
| default.key.serde | Serde mặc định cho key |
| default.value.serde | Serde mặc định cho value |
| num.stream.threads | Số stream thread trong mỗi JVM |
| state.dir | Thư mục lưu state store cục bộ |
| processing.guarantee | Chọn at-least-once hoặc exactly-once |
| num.standby.replicas | Số standby state replica cho task |
| replication.factor | Replication factor cho internal changelog/repartition topics |
| commit.interval.ms | Chu kỳ commit trạng thái/offset theo semantics đã chọn |
| client.id | Prefix nhận diện client nội bộ để quan sát |

### 9.1. application.id phải ổn định giữa các replica

application.id được dùng làm consumer group ID, prefix cho internal topics và thư mục con trong state.dir. Tất cả instance thuộc cùng một logic application phải dùng cùng giá trị.

Ví dụ:

~~~properties
application.id=orders-enrichment-v1
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
~~~

Nếu mỗi pod tự tạo application.id khác nhau, chúng không còn chia sẻ task. Mỗi pod trở thành một ứng dụng logic riêng và có thể đọc lại toàn bộ input topic, tạo output trùng và tạo internal topics riêng.

Nếu muốn hai pipeline độc lập cùng đọc một topic, chúng phải có hai application ID khác nhau. Nếu muốn scale một pipeline thành nhiều replica, chúng phải dùng chung application ID.

### 9.2. Không tự đặt group.id và enable.auto.commit

Kafka Streams quản lý consumer group ID dựa trên application.id và tắt auto commit để tự kiểm soát offset theo processing semantics. Các cấu hình này do thư viện kiểm soát; không nên cố override như một KafkaConsumer thông thường.

### 9.3. state.dir

state.dir là nơi lưu state store cục bộ. Mỗi instance/process cần thư mục local riêng để tránh nhiều tiến trình ghi vào cùng một local store directory.

Có thể dùng local SSD hoặc volume gắn vào container. Nếu local state bị mất, Kafka Streams có thể phục hồi từ changelog topic, nhưng quá trình restore có thể mất thời gian tùy kích thước state và tốc độ đọc Kafka.

Không dùng một shared network folder làm state directory chung cho nhiều instance.

## 10. Cách Kafka Streams scale độc lập

Kafka Streams scale bằng cách chạy thêm instance hoặc thêm stream thread. Tất cả instance cùng application.id sẽ tham gia một nhóm và tự chia sẻ task.

Ví dụ input topic có 12 partition:

| Triển khai | Tổng stream threads | Kết quả |
|---|---:|---|
| 1 JVM × 1 thread | 1 | Một thread xử lý các task được giao |
| 1 JVM × 4 threads | 4 | Một tiến trình có bốn luồng xử lý |
| 3 JVM × 2 threads | 6 | Sáu stream threads chia sẻ task |
| 6 JVM × 2 threads | 12 | Có thể dùng đủ 12 task nếu topology tạo 12 task |
| 10 JVM × 2 threads | 20 | Các thread/instance dư có thể không được giao task hữu ích |

Số task được tạo phụ thuộc input partitions và topology. Số thread là sức chứa thực thi bên trong các JVM. Tăng thread hoặc instance không tạo thêm partition và không làm một partition xử lý song song vượt quá ordering boundary của nó.

### 10.1. Key và ordering

Kafka Streams giữ thứ tự record trong từng partition. Key quyết định record được định tuyến đến partition nào khi producer dùng partitioner mặc định.

Nếu cần tất cả event của cùng order được xử lý theo thứ tự, hãy dùng orderId làm key nhất quán. Nếu thay key giữa pipeline, có thể cần repartition topic trước phép group/join.

### 10.2. Repartition topic

Một số phép toán yêu cầu record được phân vùng lại theo key mới. Kafka Streams có thể tạo repartition topic nội bộ để ghi record theo key mới rồi đọc lại theo partition mới.

Internal topic này là một phần topology runtime. Không xóa thủ công khi application đang chạy. Nếu cấu hình ACL hoặc replication, phải tính cả internal topics.

## 11. State store và khả năng phục hồi

Nhiều phép xử lý cần nhớ trạng thái giữa các record:

- Tổng doanh thu theo khách hàng.
- Số lần đăng nhập thất bại theo tài khoản.
- Trạng thái đơn hàng mới nhất.
- Dữ liệu phục vụ stream-table join.
- Kết quả tính toán theo cửa sổ thời gian.

Kafka Streams dùng state store cục bộ để lưu trạng thái. State store có thể là key-value store, window store, session store hoặc store tùy chỉnh.

### 11.1. Changelog topic

Khi state store được cấu hình fault-tolerant, Kafka Streams ghi thay đổi state vào changelog topic. Nếu instance bị lỗi và task chuyển sang instance khác, thư viện replay changelog để tái tạo state trước khi tiếp tục xử lý.

~~~mermaid
flowchart LR
    A["Input records"] --> B["Stream task"]
    B --> C["Local state store"]
    C --> D["Changelog topic"]
    D --> E["Restore state on new instance"]
    E --> F["Task resumes"]
~~~

Changelog topic thường dùng log compaction để giữ trạng thái mới nhất theo key và tránh tăng trưởng vô hạn. Cấu hình replication cho internal topics là một phần của thiết kế độ bền.

### 11.2. Standby replicas

num.standby.replicas cho phép duy trì bản sao state store ở instance khác. Khi active task bị chuyển, instance đã có state gần nhất có thể tiếp quản nhanh hơn, giảm thời gian phải restore toàn bộ changelog.

Đổi lại, standby cần thêm CPU, disk và network để cập nhật state. Nếu cấu hình một standby cho mỗi task, cần đủ số instance để phân bố active và standby theo yêu cầu.

### 11.3. Khôi phục state và local disk

Local state là cache/state phục vụ xử lý, còn changelog topic là nguồn phục hồi bền vững. Nếu pod restart nhưng volume giữ lại, startup có thể nhanh hơn. Nếu volume mất, Streams vẫn có thể restore từ changelog nhưng cần tính thời gian catch-up.

Không xóa state.dir hoặc gọi cleanUp() trong production một cách tùy tiện. Xóa local state làm mất cache và buộc restore; xóa internal topics có thể phá hủy dữ liệu phục hồi.

## 12. At-least-once và exactly-once

Kafka Streams hỗ trợ hai processing guarantee chính:

| Guarantee | Hành vi | Khi nào dùng |
|---|---|---|
| at_least_once | Record có thể được xử lý lại khi lỗi giữa processing và commit | Mặc định; phù hợp khi output/operation idempotent |
| exactly_once_v2 | Input offsets, output Kafka records và state updates được commit nguyên tử trong Kafka transaction | Pipeline Kafka-to-Kafka cần tránh duplicate/mất output do retry |

Ví dụ bật EOS:

~~~properties
processing.guarantee=exactly_once_v2
~~~

EOS v2 yêu cầu broker hỗ trợ transaction protocol tương ứng (Kafka broker 2.5 trở lên). Khi bật, Kafka Streams cấu hình producer idempotence và consumer isolation phù hợp.

Để độ bền production tốt, cần cấu hình replication factor và min.insync.replicas phù hợp cho broker topics, transaction state topic, consumer offsets topic và internal topics. Tài liệu Kafka khuyến nghị replication factor 3 và min ISR 2 cho cluster production.

Exactly-once của Kafka Streams bảo đảm atomicity trong phạm vi Kafka và state store được quản lý bởi Streams. Nó không tự bao trùm một database ngoài Kafka, HTTP API, email service hoặc hệ thống thanh toán. Nếu processor gọi side effect bên ngoài, cần idempotency key, outbox/inbox hoặc cơ chế transaction riêng.

## 13. Đóng gói và chạy ứng dụng độc lập

### 13.1. Build JAR

Với Maven:

~~~bash
mvn clean package
~~~

Nếu dùng Maven Shade hoặc Spring Boot packaging, hãy tạo artifact có đầy đủ dependency runtime cần thiết. Kiểm tra main class và cấu hình môi trường trước khi triển khai.

### 13.2. Chạy trực tiếp trên VM hoặc máy vật lý

Ví dụ:

~~~bash
java -jar orders-streams.jar
~~~

Có thể quản lý tiến trình bằng systemd, Windows Service hoặc process supervisor. Nền tảng quản lý process cần cấu hình restart policy, log rotation, environment variables và shutdown timeout.

### 13.3. Chạy bằng container

Docker image chứa JRE phù hợp, ứng dụng JAR và cấu hình entrypoint:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/orders-streams.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Đây là ví dụ cấu trúc image. Hãy chọn JRE theo yêu cầu Java của Kafka Streams version và build toolchain của project. Không đóng gói broker trong cùng container ứng dụng.

### 13.4. Chạy nhiều replica trên Kubernetes

Có thể triển khai ứng dụng bằng Kubernetes Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-streams
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-streams
  template:
    metadata:
      labels:
        app: orders-streams
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example.com/orders-streams:1.0.0
          env:
            - name: KAFKA_BOOTSTRAP_SERVERS
              value: kafka-bootstrap:9092
            - name: KAFKA_STREAMS_APPLICATION_ID
              value: orders-enrichment-v1
            - name: KAFKA_STREAMS_STATE_DIR
              value: /var/lib/kafka-streams
          volumeMounts:
            - name: streams-state
              mountPath: /var/lib/kafka-streams
      volumes:
        - name: streams-state
          emptyDir: {}
~~~

YAML trên minh họa cấu trúc triển khai, không phải manifest production hoàn chỉnh. Cần bổ sung resources, security context, secret, network policy, probes và storage policy theo môi trường.

Các replica của cùng một Deployment phải dùng cùng application.id. Nếu dùng local ephemeral storage, task vẫn có thể phục hồi từ changelog nhưng có thể mất thời gian restore sau khi pod bị thay thế. Persistent volume có thể giữ local state giữa lần restart tùy kiến trúc, nhưng mỗi replica cần vùng lưu state riêng.

### 13.5. Không dùng readiness chỉ dựa trên process alive

Một JVM đang chạy chưa chắc topology đã sẵn sàng. Có thể dùng KafkaStreams.StateListener để theo dõi trạng thái RUNNING, REBALANCING, ERROR và expose readiness phù hợp.

Liveness và readiness cần có ý nghĩa khác nhau:

- Liveness: process có còn sống và có thể tự phục hồi hay không.
- Readiness: Streams instance đã tham gia nhóm, nhận task và sẵn sàng xử lý hay chưa.

Tránh restart liên tục chỉ vì trạng thái REBALANCING ngắn trong một lần rollout bình thường.

## 14. Graceful shutdown và lifecycle

Khi triển khai như một service độc lập, cần xử lý tín hiệu dừng từ hệ điều hành hoặc container runtime.

KafkaStreams.close(Duration) cho thư viện thời gian hoàn tất công việc đang xử lý và đóng client. Nếu process bị kill ngay lập tức, Kafka Streams có thể phải phục hồi task và state khi instance khác tiếp quản.

Cần chú ý:

- Đặt shutdown timeout đủ lớn cho workload thực tế.
- Cấu hình termination grace period của container dài hơn thời gian close dự kiến.
- Không giữ thread nghiệp vụ chặn shutdown vô thời hạn.
- Không xóa state store trong shutdown hook production.
- Theo dõi rebalance và state restoration sau rollout.
- Nếu dùng custom state store hoặc external client, đóng tài nguyên đúng lifecycle.

Kafka Streams có các trạng thái như CREATED, REBALANCING, RUNNING, PENDING_SHUTDOWN, NOT_RUNNING, PENDING_ERROR và ERROR. Dùng state listener để log và tích hợp health status.

## 15. Internal topics và quyền truy cập

Kafka Streams có thể tạo các topic nội bộ cho:

- Changelog state store.
- Repartition giữa các bước xử lý.
- Dữ liệu điều phối và metadata theo ứng dụng.

Tên internal topics thường có prefix từ application.id. Cấu hình replication.factor điều khiển replication của changelog/repartition topics do Streams tạo.

Trong production:

- Đảm bảo replication factor và min ISR đáp ứng durability.
- Cấp ACL cho principal của Streams application trên input/output topics và internal topics.
- Không cấp quyền rộng hơn mức cần thiết.
- Không xóa hoặc chỉnh sửa internal topic khi ứng dụng đang chạy nếu chưa có quy trình được kiểm chứng.
- Đặt retention/compaction phù hợp với loại internal topic.
- Theo dõi under-replicated partitions và lỗi tạo internal topic.

Nếu broker không cho phép tự tạo topic hoặc ACL không đủ, Streams application có thể không khởi động hoặc không tạo được topology resources. Có thể tạo topic input/output trước bằng quy trình quản lý topic của cluster.

## 16. Monitoring và vận hành

Kafka Streams cung cấp metrics và callback để theo dõi runtime.

### 16.1. Metrics cần quan sát

| Nhóm | Chỉ số cần theo dõi |
|---|---|
| Runtime | Số instance, stream threads, task, trạng thái RUNNING/REBALANCING/ERROR |
| Consumer | Input records rate, consumer lag, fetch latency, commit latency |
| Processing | Process latency, punctuate latency, skipped records, exception count |
| Producer | Output records rate, send errors, retry rate, transaction commit/abort |
| State | State store size, RocksDB disk usage, restore duration, changelog lag |
| Rebalance | Rebalance count, thời gian rebalance, task migration |
| Infrastructure | CPU, heap, GC pause, local disk, network, broker health |

### 16.2. State restoration

Khi task chuyển sang instance khác, state store có thể cần restore từ changelog. Theo dõi StateRestoreListener để biết restore bắt đầu, tiến độ và kết thúc.

Restore kéo dài có thể làm task chưa xử lý input. Nguyên nhân thường gặp là changelog lớn, disk chậm, network yếu, broker quá tải hoặc standby replica không đủ gần trạng thái mới nhất.

### 16.3. Exception handlers

Kafka Streams có handler cho các loại lỗi khác nhau:

- Deserialization exception handler: record không giải mã được.
- Processing exception handler: lỗi trong logic xử lý.
- Production exception handler: lỗi khi gửi output.
- Uncaught exception handler: exception thoát khỏi stream thread.

Không nên dùng một policy continue cho mọi lỗi. Bỏ qua poison pill có thể phù hợp với một pipeline analytics, nhưng không phù hợp nếu record là event tài chính bắt buộc phải đối soát.

## 17. Kiểm thử topology trước khi triển khai

Kafka cung cấp artifact kafka-streams-test-utils với TopologyTestDriver.

Test driver cho phép:

1. Tạo topology từ DSL hoặc Processor API.
2. Tạo input topic test với Serde.
3. Đẩy record giả lập vào topology.
4. Đọc output topic test.
5. Kiểm tra state store.
6. Điều khiển timestamp và wall-clock time cho test window/punctuation.

Ví dụ:

~~~java
Properties testProps = new Properties();
testProps.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "orders-normalizer-test"
);
testProps.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "dummy:9092"
);

TopologyTestDriver driver =
        new TopologyTestDriver(topology, testProps);

TestInputTopic<String, String> input =
        driver.createInputTopic(
            "orders",
            Serdes.String().serializer(),
            Serdes.String().serializer()
        );

TestOutputTopic<String, String> output =
        driver.createOutputTopic(
            "orders-normalized",
            Serdes.String().deserializer(),
            Serdes.String().deserializer()
        );

input.pipeInput("order-1", " approved ");

KeyValue<String, String> result = output.readKeyValue();

assertEquals("order-1", result.key);
assertEquals("APPROVED", result.value);

driver.close();
~~~

TopologyTestDriver kiểm tra logic topology trong bộ nhớ. Nó không thay thế integration test với Kafka broker thật. Cần test thêm group coordination, transaction, ACL, replication, internal topics, restart và state restore.

## 18. Lab: viết và chạy một Kafka Streams application độc lập

Mục tiêu: tạo một Java application đọc event, chuẩn hóa nội dung và ghi output topic.

### Bước 1: Tạo project Java

Thêm dependency kafka-streams theo phiên bản Kafka client của môi trường. Tạo main class để khởi tạo StreamsBuilder, Topology và KafkaStreams.

### Bước 2: Tạo input/output topics

Tạo topic orders và orders-normalized. Dùng ít nhất 3 partition trong môi trường thử nghiệm nếu muốn quan sát task assignment.

### Bước 3: Viết topology

Đọc từ orders, bỏ value null, chuẩn hóa chuỗi và ghi sang orders-normalized.

### Bước 4: Cấu hình application.id

Đặt application.id=orders-normalizer-lab. Giữ cùng giá trị khi chạy nhiều instance của cùng ứng dụng.

### Bước 5: Build và chạy một instance

Build JAR rồi chạy bằng Java. Gửi một số record vào input topic và xác nhận output topic nhận dữ liệu đã chuẩn hóa.

### Bước 6: Chạy thêm instance

Khởi động instance thứ hai với cùng application.id. Quan sát rebalance và task assignment. Gửi thêm record để kiểm tra cả hai instance cùng chia sẻ công việc.

### Bước 7: Thử dừng một instance

Dừng một process bằng tín hiệu shutdown bình thường. Quan sát instance còn lại tiếp quản task. Khởi động lại process đã dừng và theo dõi rebalance.

### Bước 8: Quan sát internal topics

Kiểm tra các topic nội bộ được tạo bởi application ID. Nếu topology stateless, có thể chưa có changelog state store; thêm một aggregation để quan sát state store và changelog topic.

### Bước 9: Thử exactly-once

Đặt processing.guarantee=exactly_once_v2, kiểm tra broker hỗ trợ transaction và cấu hình replication phù hợp. Gửi input records, dừng instance trong một lần xử lý có kiểm soát và xác nhận output không bị duplicate trong phạm vi Kafka transaction.

### Bước 10: Ghi lại kết quả

Ghi số partition, số task, số instance, số stream thread, trạng thái ứng dụng, output records, consumer lag và thời gian phục hồi.

## 19. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Kafka Streams là một server cần cài riêng | Đây là thư viện chạy trong JVM ứng dụng |
| Mỗi pod phải có application.id riêng | Replica của cùng logical app dùng chung application.id |
| Tăng instance luôn tăng throughput | Parallelism bị giới hạn bởi số task và partition |
| Stream thread bằng task | Một thread có thể chạy nhiều task |
| Kafka Streams tự quản lý CPU/RAM cluster | Nền tảng triển khai vẫn cấp và quản lý tài nguyên |
| State store chỉ nằm trên local disk | Changelog topic hỗ trợ phục hồi state |
| Xóa state.dir là cách reset app an toàn | Việc này buộc restore và có thể gây downtime; reset cần quy trình riêng |
| Exactly-once bao gồm database/API ngoài Kafka | EOS của Streams bảo đảm atomicity trong phạm vi Kafka và state store |
| Kafka Connect và Kafka Streams giống nhau | Connect tích hợp nguồn/đích; Streams thực thi logic xử lý event |
| Có thể đổi application.id để scale | Đổi ID tạo logical application/group mới |
| Embedded/test driver chứng minh production ready | Cần integration test với broker thật và môi trường vận hành mục tiêu |

## 20. Checklist trước production

- [ ] Xác định Kafka Streams là thư viện nhúng trong ứng dụng Java.
- [ ] Chọn Kafka Streams version và Kafka client tương thích.
- [ ] Định nghĩa topology có thứ tự operator ổn định giữa các instance.
- [ ] Chọn DSL hoặc Processor API phù hợp.
- [ ] Chọn Serde đúng với wire format của input/output topics.
- [ ] Đặt application.id duy nhất cho từng logical application và dùng chung giữa các replica.
- [ ] Không override group ID hoặc auto commit như consumer thông thường.
- [ ] Tính số partition/task và số stream threads cần thiết.
- [ ] Chọn state.dir local riêng cho mỗi process.
- [ ] Cấu hình replication cho changelog/repartition/internal topics.
- [ ] Đánh giá num.standby.replicas nếu cần failover state nhanh.
- [ ] Chọn at_least_once hoặc exactly_once_v2 theo yêu cầu.
- [ ] Kiểm tra EOS với transaction topic, replication factor và min ISR.
- [ ] Đóng gói ứng dụng JAR/container và cấu hình secret/ACL.
- [ ] Có graceful shutdown và timeout phù hợp.
- [ ] Có readiness dựa trên trạng thái Streams application.
- [ ] Theo dõi lag, rebalance, processing latency, state restore và RocksDB disk.
- [ ] Kiểm thử topology bằng TopologyTestDriver.
- [ ] Kiểm thử integration với broker thật, transaction và restart.
- [ ] Có quy trình rollout/rollback và quản lý thay đổi topology.

## 21. Tài liệu tham khảo

- [Apache Kafka 4.4 – Kafka Streams Overview](https://kafka.apache.org/44/streams/)
- [Apache Kafka 4.4 – Core Concepts](https://kafka.apache.org/44/streams/core-concepts/)
- [Apache Kafka 4.4 – Architecture](https://kafka.apache.org/44/streams/architecture/)
- [Apache Kafka 4.4 – Write a Streams Application](https://kafka.apache.org/44/streams/tutorial/)
- [Apache Kafka 4.4 – Writing a Streams Application](https://kafka.apache.org/44/streams/developer-guide/write-streams-app/)
- [Apache Kafka 4.4 – Configuring a Streams Application](https://kafka.apache.org/44/streams/developer-guide/config-streams/)
- [Apache Kafka 4.4 – Running Streams Applications](https://kafka.apache.org/44/streams/developer-guide/running-app/)
- [Apache Kafka 4.4 – Testing a Streams Application](https://kafka.apache.org/44/streams/developer-guide/testing/)
- [Apache Kafka 4.4 – StreamsConfig Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/StreamsConfig.html)

Kafka Streams là thư viện xử lý event nằm trong ứng dụng Java. Ứng dụng có thể được đóng gói và triển khai độc lập như một tiến trình service; nhiều tiến trình cùng application.id sẽ phối hợp để chia sẻ task. Khi thiết kế production, cần tính đồng thời topology, partition, state store, internal topics, processing guarantee và lifecycle của JVM để ứng dụng vừa scale được vừa phục hồi đúng khi có lỗi.
