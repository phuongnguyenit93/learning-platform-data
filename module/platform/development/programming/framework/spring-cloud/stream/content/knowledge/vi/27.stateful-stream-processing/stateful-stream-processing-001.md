# Biến đổi không trạng thái trong topology Kafka Streams

Kafka Streams DSL cho phép xây dựng một topology bằng cách nối các phép biến đổi trên KStream và KTable. Nhiều bước xử lý chỉ cần xem record hiện tại, kiểm tra điều kiện, đổi key/value hoặc định tuyến record sang nhánh khác. Những bước đó được gọi là **stateless transformations** (biến đổi không trạng thái).

Một phép biến đổi không trạng thái không cần nhớ các record đã xử lý trước đó và không cần state store riêng để tính kết quả. Cùng một record đầu vào, cùng dữ liệu và cùng logic sẽ tạo ra cùng kết quả, độc lập với lịch sử của stream. Ví dụ điển hình là lọc đơn hàng hợp lệ, chuẩn hóa mã khách hàng, đổi định dạng payload, tách một chuỗi thành nhiều token hoặc phân luồng sự kiện theo loại.

Trong Spring Cloud Stream, Kafka Streams binder cho phép khai báo topology theo functional model bằng các bean Supplier, Function hoặc Consumer có tham số KStream/KTable. Bài này tập trung vào các phép biến đổi không trạng thái trong topology, cách chúng tác động tới key, partition, Serde và thứ tự record, đồng thời phân biệt chúng với aggregation, join và windowing có trạng thái.

## 1. Topology và ý nghĩa của stateless

Topology là đồ thị xử lý liên tục: dữ liệu đi từ source topic qua một hoặc nhiều processor node rồi tới sink topic hoặc một đích khác. DSL biểu diễn các node bằng những lời gọi nối tiếp như filter, mapValues, flatMapValues, branch và merge.

~~~mermaid
flowchart LR
    A[orders.created] --> B[filter: amount hợp lệ]
    B --> C[mapValues: chuẩn hóa dữ liệu]
    C --> D[branch: phân loại]
    D --> E[orders.accepted]
    D --> F[orders.review]
~~~

Các bước trên xử lý từng record mà không cần tra cứu hoặc cập nhật trạng thái tích lũy từ các record trước. Kafka Streams vẫn điều phối task, consumer, producer và offset; “không trạng thái” ở đây nói về phép biến đổi nghiệp vụ, không có nghĩa ứng dụng không có bất kỳ trạng thái runtime nào.

Một phép biến đổi được xem là stateless khi kết quả của record hiện tại không phụ thuộc vào:

- Tổng số record đã đến trước đó.
- Giá trị trước đó của cùng key.
- Một cửa sổ thời gian hoặc khoảng thời gian đã tích lũy.
- Kết quả tra cứu từ state store do topology duy trì.

Ví dụ:

| Nhu cầu | Phép biến đổi |
|---|---|
| Bỏ sự kiện có amount không hợp lệ. | filter |
| Chuyển mã tiền tệ sang chữ hoa. | mapValues |
| Tách một dòng thành nhiều từ. | flatMapValues |
| Đổi key sang orderId. | selectKey hoặc map |
| Đưa sự kiện vào nhánh phù hợp. | split/branch |
| Hợp nhất hai luồng đầu vào. | merge |
| Ghi log/metric khi record đi qua. | peek |

Ngược lại, count, aggregate, reduce, windowed aggregation và join cần duy trì hoặc tra cứu trạng thái theo key, cửa sổ hay bảng. Những thao tác này thuộc nhóm stateful transformations.

## 2. KStream và KTable trước khi chọn phép biến đổi

KStream biểu diễn một chuỗi record sự kiện. Mỗi record được hiểu như một sự kiện độc lập, thường tương ứng với một lần phát sinh trong thực tế. Hai record cùng key vẫn là hai sự kiện riêng biệt.

KTable biểu diễn một changelog theo key. Record mới có cùng key cập nhật giá trị hiện tại của key đó; record có value null có thể được hiểu là tombstone để xóa key khỏi bảng.

| Đặc điểm | KStream | KTable |
|---|---|---|
| Ý nghĩa record | Sự kiện/entry mới trong stream. | Thay đổi giá trị hiện tại theo key. |
| Hai record cùng key | Cả hai đều là sự kiện. | Record sau cập nhật record trước. |
| Null value | Là record có value null; cách xử lý phụ thuộc phép toán. | Thường biểu thị tombstone/xóa key. |
| Phép biến đổi stateless | Tạo KStream mới. | Có thể tạo KTable mới và giữ semantics changelog. |
| Ví dụ | Lịch sử giao dịch, page view, log. | Trạng thái hiện tại của tài khoản hoặc hồ sơ khách hàng. |

Các phép mapValues và filter có thể áp dụng cho cả KStream lẫn KTable, nhưng không làm thay đổi bản chất của abstraction. Khi biến đổi KTable, cần hiểu rằng output vẫn phản ánh cập nhật theo key chứ không phải một chuỗi sự kiện append-only thông thường.

## 3. filter và filterNot: giữ hoặc loại record

filter đánh giá một predicate cho từng record và chỉ giữ record có kết quả true. filterNot giữ record khi predicate trả false. Cả hai đều không cần state store.

Ví dụ chỉ giữ giao dịch có số tiền dương:

~~~java
KStream<String, Long> positiveAmounts = transactions
    .filter((accountId, amount) -> amount != null && amount > 0);

KStream<String, Long> rejectedAmounts = transactions
    .filterNot((accountId, amount) -> amount != null && amount > 0);
~~~

Predicate nhận cả key và value. Nếu điều kiện chỉ phụ thuộc value, có thể dùng lambda bỏ qua key. Cần quyết định rõ cách xử lý null; đừng để một phép so sánh tự động unbox null gây NullPointerException.

filter không sửa record. Key, value và metadata của record được chuyển tiếp theo semantics của Kafka Streams. Record không thỏa điều kiện bị loại khỏi nhánh output đó; nó không tự động được đưa vào DLQ. Nếu cần giữ record bị loại để điều tra, hãy tạo một nhánh riêng bằng split/branch hoặc một topology xử lý lỗi có chủ đích.

Ví dụ lọc theo loại sự kiện:

~~~java
KStream<String, OrderEvent> paidOrders = orders
    .filter((orderId, event) -> event != null
        && "PAID".equals(event.status()));
~~~

Nếu muốn loại một nhóm điều kiện, filterNot có thể giúp biểu đạt trực tiếp:

~~~java
KStream<String, OrderEvent> nonCancelledOrders = orders
    .filterNot((orderId, event) -> event != null
        && "CANCELLED".equals(event.status()));
~~~

## 4. mapValues: biến đổi value và giữ nguyên key

mapValues nhận value của từng record và tạo value mới. Key gốc được giữ nguyên. Đây thường là lựa chọn phù hợp khi cần chuẩn hóa hoặc làm giàu nội dung value mà không đổi partitioning key.

~~~java
KStream<String, String> normalizedNames = customerNames
    .mapValues(name -> name == null ? "" : name.trim().toUpperCase());
~~~

Ví dụ với sự kiện đơn hàng:

~~~java
record OrderCreated(String orderId, String customerId, long amount) {}
record OrderSummary(String customerId, long amount, String category) {}

KStream<String, OrderSummary> summaries = orderEvents
    .mapValues(event -> new OrderSummary(
        event.customerId(),
        event.amount(),
        event.amount() >= 1_000_000 ? "LARGE" : "STANDARD"
    ));
~~~

Trong ví dụ, key của record vẫn là order key. Việc đưa customerId vào value không làm thay đổi key của Kafka record. Nếu bước sau cần nhóm theo customerId, phải đổi key hoặc group theo trường customerId và chấp nhận repartition khi cần.

mapValues thường hiệu quả hơn map khi không cần đổi key vì nó không đánh dấu stream cần repartition. Một overload của phép toán cho phép mapper nhận thêm key gốc bên cạnh value; dùng overload này khi phép biến đổi cần đọc key nhưng vẫn muốn giữ nguyên key đầu ra.

## 5. map: biến đổi cả key và value

map nhận key và value rồi trả về một KeyValue mới. Có thể đổi key, value hoặc kiểu dữ liệu của cả hai.

~~~java
import org.apache.kafka.streams.KeyValue;

KStream<String, Long> normalized = amounts.map((accountId, amount) ->
    KeyValue.pair(
        accountId.trim().toUpperCase(),
        amount == null ? 0L : amount
    )
);
~~~

Khác với mapValues, map có thể thay đổi key. Điều này quan trọng vì Kafka partitioner thường sử dụng key để xác định partition. Tuy nhiên, việc gọi map hoặc selectKey không tự lập tức chuyển record sang partition mới. Kafka Streams đánh dấu topology cần repartition khi có thao tác downstream yêu cầu dữ liệu được phân phối theo key mới, ví dụ groupByKey hoặc một số dạng join.

Nếu chỉ đổi value, hãy ưu tiên mapValues. Nếu đổi key để chuẩn bị cho grouping/join, hãy hiểu rằng repartition topic có thể được tạo và phát sinh thêm network I/O, serialization và độ trễ.

## 6. selectKey: đổi key mà giữ nguyên value

selectKey tạo stream mới với key được tính từ record hiện tại, còn value được giữ nguyên.

~~~java
KStream<String, OrderCreated> ordersByCustomer = orders
    .selectKey((oldOrderKey, event) -> event.customerId());
~~~

Trước phép biến đổi, record có thể được partition theo orderId. Sau phép biến đổi, key logic là customerId. Nếu topology tiếp tục groupByKey hoặc join theo customerId, Kafka Streams có thể cần repartition để bảo đảm các record cùng customerId đến đúng partition.

Không nên thay key chỉ để thuận tiện hiển thị. Key quyết định locality, partitioning và khả năng giữ thứ tự theo entity. Trước khi đổi key, hãy xác định bước downstream sẽ dùng key mới như thế nào.

## 7. flatMapValues và flatMap: một record tạo nhiều record

flatMapValues biến một record thành không, một hoặc nhiều record mới nhưng giữ key ban đầu. Đây là lựa chọn tốt khi cần tách hoặc mở rộng value mà không đổi key.

~~~java
import java.util.Arrays;

KStream<String, String> wordsByDocument = documents
    .flatMapValues(text -> Arrays.asList(text.split("\\s+")));
~~~

Nếu document có key doc-1 và value "kafka streams stateless", topology tạo ba record với cùng key doc-1, mỗi record mang một từ. Do key không đổi, phép toán này không cần repartition chỉ vì tách value.

flatMap cho phép tạo nhiều cặp key/value mới:

~~~java
KStream<String, Integer> tokens = documents.flatMap((documentId, text) -> {
    List<KeyValue<String, Integer>> result = new ArrayList<>();
    for (String word : text.split("\\s+")) {
        result.add(KeyValue.pair(word.toLowerCase(), 1));
    }
    return result;
});
~~~

Đoạn mã minh họa giả định đã import `java.util.ArrayList`, `java.util.List` và `org.apache.kafka.streams.KeyValue`.

Ở ví dụ này, mỗi từ trở thành key mới. Nếu sau đó gọi groupByKey hoặc join, Kafka Streams có thể cần repartition để gom các từ giống nhau về cùng partition. Dùng flatMapValues khi key phải được giữ; chỉ dùng flatMap khi thực sự cần thay key.

| Phép toán | Số record đầu ra mỗi record đầu vào | Có thể đổi key? | Repartition do đổi key? |
|---|---:|---|---|
| mapValues | 1 | Không | Không |
| map | 1 | Có | Có thể cần ở bước grouping/join tiếp theo |
| flatMapValues | 0..n | Không | Không do đổi key |
| flatMap | 0..n | Có | Có thể cần ở bước grouping/join tiếp theo |
| filter | 0 hoặc 1 | Không | Không |

## 8. split/branch: định tuyến record theo điều kiện

split tạo một nhánh phân luồng từ KStream. Các predicate được kiểm tra theo thứ tự khai báo. Mỗi record đi vào nhánh đầu tiên có predicate trả true; nó không tự động được nhân bản sang tất cả nhánh khớp.

~~~java
import org.apache.kafka.streams.kstream.Branched;
import org.apache.kafka.streams.kstream.Named;

Map<String, KStream<String, OrderEvent>> branches = orders
    .split(Named.as("order-"))
    .branch(
        (key, event) -> event != null && event.amount() >= 1_000_000,
        Branched.as("large")
    )
    .branch(
        (key, event) -> event != null && event.amount() > 0,
        Branched.as("standard")
    )
    .defaultBranch(Branched.as("invalid"));

KStream<String, OrderEvent> largeOrders = branches.get("order-large");
KStream<String, OrderEvent> standardOrders = branches.get("order-standard");
KStream<String, OrderEvent> invalidOrders = branches.get("order-invalid");
~~~

Nhánh large được kiểm tra trước standard để record amount lớn không bị nhận ở nhánh standard. Nếu không có default branch, record không khớp predicate nào sẽ bị loại khỏi các nhánh được tạo.

Branch chỉ tạo các stream logic trong topology. Muốn lưu chúng ra Kafka, cần nối mỗi nhánh tới sink topic bằng to(...) hoặc cấu hình output binding tương ứng trong mô hình binder. Không nhầm một nhánh logic với một queue/topic đã được tạo sẵn.

## 9. merge: hợp nhất các luồng

merge kết hợp record từ hai KStream thành một stream lớn hơn:

~~~java
KStream<String, OrderEvent> allOrders =
    onlineOrders.merge(storeOrders);
~~~

Merge không sắp xếp lại toàn bộ record theo timestamp và không tạo thứ tự toàn cục giữa hai nguồn. Thứ tự tương đối trong từng input stream được giữ, nhưng record từ onlineOrders và storeOrders có thể xen kẽ theo lịch xử lý. Nếu nghiệp vụ cần thứ tự theo event time hoặc aggregate version, phải thiết kế quy tắc sắp xếp/kiểm tra riêng.

Merge không tự khử trùng lặp. Nếu hai nguồn phát cùng một event, output vẫn có thể chứa cả hai record. Muốn loại duplicate, cần một khóa idempotency hoặc stateful deduplication có thời hạn phù hợp; deduplication theo lịch sử là một thao tác cần state.

## 10. peek và foreach: quan sát so với tác dụng phụ

peek thực hiện một hành động quan sát trên từng record rồi trả lại stream không thay đổi. Nó phù hợp để log, debug hoặc tăng metric:

~~~java
KStream<String, OrderEvent> observed = orders.peek((key, event) ->
    log.debug("orderKey={}, eventId={}", key, event.eventId())
);
~~~

foreach cũng thực hiện hành động cho từng record nhưng là terminal operation, không trả về stream để nối tiếp topology:

~~~java
orders.foreach((key, event) ->
    log.info("Received order {}", event.orderId())
);
~~~

Không dùng peek/foreach để ghi dữ liệu nghiệp vụ vào một hệ thống ngoài rồi giả định Kafka sẽ đưa tác dụng phụ đó vào processing guarantee của topology. Kafka Streams không thể rollback một HTTP call hoặc database write chỉ vì Kafka transaction bị abort. Side effect bên ngoài có thể được thực hiện lại khi record được replay hoặc task phục hồi.

Nếu cần ghi ra Kafka, ưu tiên DSL sink như to() hoặc output binding của binder để Kafka Streams quản lý producer và transaction. Nếu cần ghi database/API ngoài, hãy dùng outbox, idempotency hoặc cơ chế phối hợp phù hợp.

## 11. Kết hợp nhiều phép biến đổi thành một pipeline

Một topology thực tế thường nối nhiều phép stateless:

~~~java
KStream<String, OrderCreated> acceptedOrders = orders
    .filter((orderId, event) ->
        event != null && event.amount() > 0)
    .mapValues(event -> new OrderCreated(
        event.orderId(),
        event.customerId().trim(),
        event.amount()
    ))
    .peek((orderId, event) ->
        log.debug("Accepted order {}", event.orderId()));
~~~

Pipeline này:

1. Loại record null hoặc amount không hợp lệ.
2. Chuẩn hóa customerId trong value.
3. Giữ nguyên key đầu vào.
4. Ghi log quan sát mà không thay đổi record.

Không có phép nào cần nhớ record trước đó. Mỗi record có thể được xử lý độc lập. Nếu thêm countByKey, aggregate hoặc windowedBy, topology sẽ chuyển sang một bước stateful và cần state store.

## 12. Dùng stateless topology trong Spring Cloud Stream Kafka Streams binder

Kafka Streams binder cho phép dùng functional programming model. Một bean Function nhận KStream và trả về KStream biểu diễn processor có input và output binding.

Ví dụ:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderValidationTopology {

    @Bean
    Function<KStream<String, Long>, KStream<String, Long>> positiveAmounts() {
        return input -> input
            .filter((accountId, amount) -> amount != null && amount > 0)
            .mapValues(amount -> amount * 100L);
    }
}
~~~

Function bean có tên positiveAmounts nên binder mặc định tạo:

- positiveAmounts-in-0: binding đầu vào.
- positiveAmounts-out-0: binding đầu ra.

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: positiveAmounts
    stream:
      bindings:
        positiveAmounts-in-0:
          destination: account.amounts
        positiveAmounts-out-0:
          destination: account.amounts.normalized
      kafka:
        streams:
          binder:
            application-id: account-amount-normalizer
~~~

application-id xác định Kafka Streams application, consumer group logic và namespace state/runtime của ứng dụng. Dù topology chỉ có stateless operations, application ID vẫn cần ổn định giữa các lần triển khai để Kafka Streams quản lý task và offset nhất quán.

## 13. Serde khi thay đổi kiểu dữ liệu

Kafka lưu byte array; Kafka Streams cần Serializer/Deserializer (Serde) để chuyển đổi key/value ở đầu vào, các điểm repartition và output topic. Một phép biến đổi có thể thay đổi kiểu dữ liệu, vì vậy phải bảo đảm Serde tương ứng đã được cấu hình.

Ví dụ, input topic chứa key String và value Long, output cũng giữ String/Long thì có thể dùng built-in Serdes. Nếu mapValues chuyển OrderCreated thành OrderSummary, output value cần một Serde đọc/ghi OrderSummary.

Trong Kafka Streams binder, cấu hình Serde theo binding có thể được đặt dưới:

- Consumer: spring.cloud.stream.kafka.streams.bindings.<binding-name>.consumer.keySerde và valueSerde.
- Producer: spring.cloud.stream.kafka.streams.bindings.<binding-name>.producer.keySerde và valueSerde.
- Default cho nhiều output có thể đặt dưới spring.cloud.stream.kafka.streams.default.producer.

Ví dụ minh họa với String Serde:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            positiveAmounts-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$LongSerde
            positiveAmounts-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$LongSerde
~~~

Nếu dùng JSON, Avro, Protobuf hoặc type-specific Serde, hãy cấu hình đúng class và schema registry/client tương ứng. Không giả định Serde của input tự động phù hợp với output sau khi thay đổi kiểu dữ liệu.

## 14. Đổi key và repartition: ảnh hưởng hiệu năng

Kafka phân phối record vào partition dựa trên key và partitioner. Nếu key được giữ nguyên bằng mapValues hoặc flatMapValues, topology có thể tiếp tục xử lý dữ liệu theo partition hiện tại.

Khi map, flatMap hoặc selectKey đổi key, các record đang nằm ở partition cũ có thể không còn được phân bố theo key mới. Nếu bước tiếp theo cần các record cùng key nằm cùng partition, Kafka Streams phải repartition qua một topic nội bộ.

~~~mermaid
flowchart LR
    A[Input topic partition theo orderId] --> B[selectKey: customerId]
    B --> C{Có grouping/join theo key mới?}
    C -->|Không| D[Tiếp tục topology]
    C -->|Có| E[Repartition topic]
    E --> F[Record phân phối theo customerId]
    F --> G[Group / join / aggregate]
~~~

Repartition phát sinh serialize, gửi broker, đọc lại và có thể tăng latency. Chỉ đổi key khi yêu cầu nghiệp vụ cần. Nếu bước sau chỉ biến đổi value, dùng mapValues để tránh tạo repartition không cần thiết.

Để kiểm tra topology, có thể xem topology description và các internal topic do Kafka Streams tạo. Với production, theo dõi throughput, network, lag và số internal repartition topics khi thay đổi key.

## 15. Stateless không đồng nghĩa deterministic hoặc không có lỗi

Một hàm có thể không dùng state store nhưng vẫn tạo kết quả không ổn định nếu đọc thời gian hệ thống, random, biến mutable hoặc gọi dịch vụ ngoài:

~~~java
KStream<String, OrderEvent> unstable = orders.mapValues(event ->
    event.withProcessedAt(Instant.now())
);
~~~

Phép biến đổi này không dùng state store, nhưng cùng một record được replay ở thời điểm khác sẽ có processedAt khác. Nếu yêu cầu kết quả có thể tái lập, dùng timestamp của record hoặc một trường thời gian nghiệp vụ đã được ghi trong event.

Tương tự, gọi HTTP API trong mapValues làm topology phụ thuộc dịch vụ ngoài, có thể block stream thread và tạo side effect lặp khi replay. Nên tránh gọi I/O blocking trong các mapper stateless. Nếu cần làm giàu dữ liệu, cân nhắc phát event sang service chuyên trách, dùng KTable/global table cho dữ liệu tham chiếu hoặc thiết kế cơ chế retry/idempotency riêng.

Stateless chỉ mô tả việc phép toán không duy trì trạng thái tích lũy giữa các record. Nó không tự đảm bảo deterministic, exactly-once cho API ngoài hoặc không phát sinh exception.

## 16. Phân biệt stateless và stateful operators

| Nhu cầu | Stateless | Stateful |
|---|---|---|
| Chọn record theo điều kiện | filter/filterNot | — |
| Đổi key/value | map/mapValues/selectKey | — |
| Tạo nhiều record từ một record | flatMap/flatMapValues | — |
| Phân luồng/hợp nhất | split/branch/merge | — |
| Quan sát record | peek | — |
| Đếm record theo key | — | count |
| Tính tổng/giá trị tích lũy | — | aggregate/reduce |
| Gom record theo khoảng thời gian | — | windowedBy |
| Kết hợp các stream/table theo key | — | join |
| Khử trùng lặp dựa trên lịch sử | — | deduplication với state store/window |

Một topology có thể chứa cả hai loại. Ví dụ, filter và mapValues có thể chạy trước groupByKey và count. Khi đến bước count, topology bắt đầu cần state store để lưu số đếm theo key. Các bước stateless trước đó không biến thành stateful chỉ vì đứng trước aggregation.

## 17. Kiểm thử stateless topology

Kafka Streams cung cấp TopologyTestDriver để kiểm thử topology mà không cần chạy Kafka broker. Spring Cloud Stream Kafka Streams binder cũng có thể kiểm thử logic function và binding, nhưng cần phân biệt kiểm thử function với kiểm thử runtime/broker.

Với TopologyTestDriver, kiểm thử nên xác minh:

- Record hợp lệ được giữ, record không hợp lệ bị loại.
- mapValues giữ nguyên key và đổi đúng value.
- map/selectKey tạo key mới đúng mong muốn.
- flatMapValues tạo đủ số record và vẫn giữ key gốc.
- branch áp dụng predicate theo đúng thứ tự và route vào default branch khi cần.
- merge không được giả định có thứ tự toàn cục giữa hai nguồn.
- Serde đầu vào/đầu ra đọc và ghi đúng kiểu.
- Record null/tombstone được xử lý theo semantics mong muốn.

Ví dụ test khái niệm với TopologyTestDriver:

~~~java
TestInputTopic<String, Long> input =
    testDriver.createInputTopic(
        "account.amounts",
        stringSerializer,
        longSerializer
    );

TestOutputTopic<String, Long> output =
    testDriver.createOutputTopic(
        "account.amounts.normalized",
        stringDeserializer,
        longDeserializer
    );

input.pipeInput("account-1", 10L);
input.pipeInput("account-2", -5L);

assertThat(output.readKeyValue())
    .isEqualTo(KeyValue.pair("account-1", 1000L));
assertThat(output.isEmpty()).isTrue();
~~~

Đoạn test minh họa giả định topology đã được dựng bằng testDriver và có các serializer/deserializer tương ứng. Trong dự án, tạo driver với Properties có application ID, bootstrap servers giả lập và default Serdes hoặc Serde tường minh; đóng driver sau test để giải phóng tài nguyên.

Với topology có repartition, cần kiểm tra cả key và kết quả downstream để chắc chắn record cùng key mới được phân phối đúng. Với branch/merge, test riêng từng nhánh và không assert một thứ tự liên nguồn mà API không bảo đảm.

## 18. Quan sát topology và vận hành

Các phép biến đổi không trạng thái thường ít tốn tài nguyên hơn aggregation/join, nhưng vẫn có thể tạo bottleneck do xử lý CPU, serialize/deserialize, repartition hoặc side effect.

Nên theo dõi:

- Input/output records per second theo processor node.
- Số record bị filter hoặc không khớp branch.
- Processing latency và stream thread idle time.
- Consumer lag và thời gian xử lý theo partition.
- Repartition topic count, throughput và internal topic traffic.
- Serialization/deserialization error.
- Exception trong mapper/predicate và số lần task restart.
- Tỷ lệ output/input để phát hiện filter hoặc branch làm mất record ngoài dự kiến.

Đặt tên processor node có ý nghĩa khi topology phức tạp để metric và topology description dễ đọc. Không log toàn bộ payload ở mọi record trong production; dùng sample, log level phù hợp và metric có cardinality thấp.

## 19. Những lỗi thường gặp

1. Dùng map khi chỉ cần đổi value, làm topology có thể phải repartition ở bước grouping/join sau đó.
2. Dùng flatMap để tách value dù key cần giữ; flatMapValues thường phù hợp hơn.
3. Giả định selectKey lập tức di chuyển record sang partition mới; repartition chỉ phát sinh khi topology cần phân phối theo key mới.
4. Nghĩ branch gửi record tới tất cả predicate khớp; thực tế record đi vào nhánh đầu tiên khớp.
5. Giả định merge sắp xếp record từ hai nguồn theo timestamp; không có thứ tự toàn cục như vậy.
6. Dùng peek/foreach để ghi database hoặc gọi API rồi kỳ vọng Kafka rollback side effect.
7. Quên cấu hình Serde sau khi thay đổi kiểu key/value.
8. Xử lý KTable như KStream và bỏ qua semantics update/tombstone.
9. Đưa logic phụ thuộc thời gian hệ thống/random vào mapper nhưng kỳ vọng replay cho cùng kết quả.
10. Dùng filter để loại message lỗi nhưng không có nhánh lưu lại khi nghiệp vụ yêu cầu điều tra.
11. Cho rằng stateless có nghĩa topology không cần quản lý application ID, task, partition hoặc offset.

## 20. Quy trình thiết kế một topology stateless

1. Xác định input type: KStream hay KTable; key/value và Serde hiện tại.
2. Viết rõ điều kiện record nào được giữ, loại hoặc chuyển nhánh.
3. Xác định bước nào chỉ đổi value và bước nào thực sự cần đổi key.
4. Ưu tiên mapValues/flatMapValues khi giữ key để tránh repartition không cần thiết.
5. Nếu đổi key, xác định grouping/join downstream có cần repartition hay không.
6. Xác định branch predicates theo thứ tự ưu tiên và tạo default branch khi cần.
7. Xác định merge có chấp nhận không có thứ tự toàn cục giữa nguồn hay không.
8. Chọn Serde phù hợp với mọi kiểu dữ liệu ở input, internal repartition và output.
9. Giữ mapper/predicate ngắn, deterministic và tránh I/O blocking/side effect bên ngoài.
10. Kiểm thử từng phép biến đổi bằng TopologyTestDriver và integration test khi cần xác minh broker.
11. Quan sát topology description, internal topics, processing latency và tỷ lệ input/output sau triển khai.

Biến đổi không trạng thái là các khối xây dựng cơ bản của topology Kafka Streams. Khi hiểu rõ mỗi phép toán tác động tới record, key, partition và Serde ra sao, bạn có thể tạo pipeline dễ kiểm thử, tránh repartition không cần thiết và giữ ranh giới rõ ràng trước khi thêm state store, aggregation, join hoặc windowing.

## Tài liệu tham khảo

- [Apache Kafka Streams DSL – Stateless transformations](https://kafka.apache.org/documentation/streams/developer-guide/dsl-api/)
- [Spring Cloud Stream Kafka Streams Binder – Functional Style](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/functional.html)
- [Spring Cloud Stream Kafka Streams Binder – Serialization and Deserialization](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/record-serialization-and-deserialization.html)
- [Apache Kafka Streams – Testing](https://kafka.apache.org/documentation/streams/developer-guide/testing/)
