# subBatchPerPartition

Trong Spring Kafka, **subBatchPerPartition** là tùy chọn của listener container dành cho **batch listener**. Khi được bật, container chia tập record nhận được từ một lần poll thành các nhóm nhỏ, mỗi nhóm chỉ chứa record thuộc cùng một **TopicPartition**, rồi gọi listener riêng cho từng nhóm.

Một lần poll có thể trả về record từ nhiều partition mà consumer đang sở hữu. Với hành vi batch thông thường, listener nhận một batch gồm record từ tất cả partition xuất hiện trong poll. Khi bật **subBatchPerPartition**, listener nhận nhiều lần gọi nhỏ hơn: mỗi lần gọi chỉ đại diện cho một partition. Điều này giúp ứng dụng xử lý, quan sát và trong một số cấu hình giao dịch, tạo ranh giới transaction theo partition.

Tùy chọn này thay đổi cách container phân chia batch và gọi listener. Nó không tạo thêm partition, không tăng số consumer, không thay đổi assignment của Kafka và không cung cấp thứ tự toàn cục giữa các partition.

## 1. Bối cảnh: một poll có thể chứa nhiều partition

Kafka lưu record theo topic và partition. Một consumer group phân phối các partition cho các consumer thành viên. Một consumer có thể được giao nhiều partition; trong một lần gọi poll, nó có thể nhận record từ một số hoặc tất cả partition đang được giao.

Ví dụ consumer thuộc group **billing-service** được giao ba partition:

- **orders.created-0**
- **orders.created-1**
- **orders.created-2**

Một lần poll có thể trả về:

| TopicPartition | Các offset trong poll |
|---|---|
| orders.created-0 | 10, 11, 12 |
| orders.created-1 | 25, 26 |
| orders.created-2 | 41, 42, 43, 44 |

Nếu dùng batch listener với cách gom batch thông thường, listener nhận một collection chứa cả chín record. Ứng dụng phải tự nhóm record theo topic và partition nếu muốn xử lý riêng từng partition.

Khi **subBatchPerPartition** được bật, container thực hiện việc chia nhóm trước khi gọi listener:

~~~mermaid
flowchart TD
    A["Kafka consumer poll"] --> B["Batch từ nhiều partition"]
    B --> C["orders.created-0<br/>offset 10, 11, 12"]
    B --> D["orders.created-1<br/>offset 25, 26"]
    B --> E["orders.created-2<br/>offset 41, 42, 43, 44"]
    C --> F["Listener invocation 1"]
    D --> G["Listener invocation 2"]
    E --> H["Listener invocation 3"]
~~~

Mỗi lần gọi listener tương ứng với một partition. Thứ tự các nhóm được container chuyển tới listener phụ thuộc thứ tự các partition trong batch; ứng dụng không nên dựa vào một thứ tự cố định giữa các partition.

## 2. subBatchPerPartition giải quyết vấn đề gì?

### Xử lý riêng theo partition

Một số nghiệp vụ cần gom record thành batch để giảm chi phí gọi database hoặc xử lý theo lô, nhưng vẫn cần biết chính xác batch thuộc partition nào. Ví dụ, một processor duy trì trạng thái theo partition hoặc cần ghi nhận tiến độ xử lý riêng theo partition.

Nếu listener nhận một batch hỗn hợp, ứng dụng phải nhóm record bằng code:

~~~java
Map<TopicPartition, List<ConsumerRecord<String, OrderEvent>>> grouped =
        records.stream().collect(Collectors.groupingBy(
                record -> new TopicPartition(
                        record.topic(),
                        record.partition()
                )
        ));
~~~

Với **subBatchPerPartition**, container đã chia batch theo partition, nên listener có thể xử lý một nhóm đồng nhất ngay trong mỗi invocation.

### Transaction boundary theo partition

Một lý do quan trọng để dùng tùy chọn này là khi ứng dụng sử dụng batch listener với Kafka transaction manager. Container có thể xử lý từng sub-batch trong transaction riêng theo partition. Khi một partition sub-batch thất bại, transaction của sub-batch đó có thể rollback theo cấu hình, trong khi các sub-batch khác đã hoàn tất transaction riêng có thể được commit độc lập.

Điều này giúp giới hạn phạm vi một transaction vào record của một partition. Cách hoạt động cụ thể còn phụ thuộc phiên bản Spring Kafka, loại transaction manager, error handler và cấu hình container. Cần xác minh semantics của phiên bản đang chạy trước khi dựa vào nó cho yêu cầu delivery guarantee.

### Đơn giản hóa quan sát và phục hồi

Mỗi lần listener được gọi có thể gắn với một topic-partition cụ thể. Log, metric và xử lý lỗi vì thế có thể ghi nhận rõ partition đang được xử lý. Khi điều tra một partition bị chậm hoặc có dữ liệu lỗi, đội vận hành dễ khoanh vùng hơn.

## 3. Cấu hình subBatchPerPartition

Tùy chọn này được đặt trên **ContainerProperties** của listener container factory. Nó có ý nghĩa khi factory được cấu hình làm batch listener.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;

@Configuration
public class BatchListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderBatchListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);

        factory.getContainerProperties()
                .setSubBatchPerPartition(true);

        factory.getContainerProperties()
                .setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}
~~~

Ba thiết lập cần phân biệt:

- **setBatchListener(true)** chọn kiểu listener nhận batch.
- **setSubBatchPerPartition(true)** yêu cầu container chia batch thành các nhóm theo topic-partition trước khi gọi listener.
- **AckMode.BATCH** chọn cách container xác nhận offset sau khi batch được xử lý theo semantics của chế độ đó. Đây là lựa chọn acknowledgement độc lập với việc chia sub-batch.

Nếu bật **subBatchPerPartition** nhưng endpoint vẫn dùng record listener, tùy chọn này không tạo ra các invocation batch theo partition. Hãy bảo đảm method signature và kiểu listener tương thích với batch mode.

### Đặt giá trị rõ ràng

Trong các ứng dụng có nhiều factory, hãy cấu hình giá trị trên đúng factory được endpoint sử dụng. Đừng suy luận rằng mọi listener đều dùng chung giá trị mặc định. Giá trị mặc định hoặc hành vi liên quan transaction có thể phụ thuộc phiên bản Spring Kafka và cách container được cấu hình. Khi hành vi này quan trọng, đặt rõ true hoặc false và kiểm tra factory hiệu lực.

## 4. Batch listener nhận dữ liệu như thế nào?

Một batch listener có thể nhận danh sách payload hoặc danh sách **ConsumerRecord**, tùy cách ứng dụng cần sử dụng metadata.

Nếu cần partition, offset, timestamp hoặc key cho từng record, dùng **ConsumerRecord** là lựa chọn rõ ràng:

~~~java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {

    @KafkaListener(
        id = "orderBatchListener",
        topics = "orders.created",
        groupId = "billing-service",
        containerFactory = "orderBatchListenerFactory"
    )
    public void onOrders(
            List<ConsumerRecord<String, OrderEvent>> records) {

        if (records.isEmpty()) {
            return;
        }

        ConsumerRecord<String, OrderEvent> first = records.get(0);

        String topic = first.topic();
        int partition = first.partition();

        // Với subBatchPerPartition=true, records thuộc cùng topic-partition.
        for (ConsumerRecord<String, OrderEvent> record : records) {
            billingService.process(
                    record.value(),
                    record.offset()
            );
        }

        log.debug(
                "Processed {} records from {}-{}",
                records.size(),
                topic,
                partition
        );
    }
}
~~~

Với **subBatchPerPartition=true**, listener có thể lấy topic và partition từ record đầu tiên để gắn ngữ cảnh cho toàn bộ invocation. Vẫn nên giữ kiểm tra hoặc assertion trong code nếu tính đồng nhất của batch là điều kiện quan trọng đối với nghiệp vụ, đặc biệt khi factory có thể được cấu hình lại.

Nếu listener chỉ cần payload, có thể nhận **List<OrderEvent>**:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service",
    containerFactory = "orderBatchListenerFactory"
)
public void onOrderPayloads(List<OrderEvent> events) {
    billingService.processBatch(events);
}
~~~

Khi chỉ nhận payload, listener không có trực tiếp metadata topic-partition và offset trong từng phần tử. Nếu cần các giá trị đó cho logging, recovery hoặc kiểm toán, hãy dùng ConsumerRecord hoặc các header batch phù hợp với message converter và phiên bản Spring Kafka.

## 5. So sánh batch thông thường và sub-batch theo partition

| Khía cạnh | Batch thông thường | subBatchPerPartition bật |
|---|---|---|
| Dữ liệu listener nhận | Các record từ nhiều partition trong một poll | Một nhóm record từ một topic-partition cho mỗi invocation |
| Số lần gọi listener | Thường một invocation cho batch poll | Có thể nhiều invocation, theo số partition có record trong poll |
| Nhóm record | Ứng dụng tự nhóm nếu cần | Container nhóm theo partition |
| Metadata partition | Có trong từng ConsumerRecord | Các record trong một invocation cùng topic-partition |
| Transaction | Có thể xử lý cả batch trong transaction theo cấu hình | Có thể tạo transaction riêng cho từng partition sub-batch khi dùng cấu hình transaction phù hợp |
| Chi phí gọi listener | Ít invocation hơn | Có thể nhiều invocation hơn |
| Phạm vi lỗi | Có thể ảnh hưởng batch hỗn hợp | Có thể khoanh invocation vào một partition sub-batch |
| Thứ tự toàn cục | Không có giữa các partition | Vẫn không có giữa các partition |

Giả sử poll trả về 12 record từ ba partition, mỗi partition có bốn record:

- Batch thông thường: listener được gọi một lần với 12 record.
- subBatchPerPartition: listener được gọi ba lần, mỗi lần với bốn record thuộc một partition.

Số invocation không nhất thiết bằng số partition được giao cho consumer. Nó phụ thuộc partition nào thực sự có record trong kết quả poll đó.

## 6. subBatchPerPartition không làm tăng concurrency

Cần phân biệt ba khái niệm:

- **Partition** là đơn vị lưu trữ và thứ tự trong Kafka.
- **Consumer concurrency** là số consumer chạy song song trong một listener container.
- **Sub-batch** là nhóm record mà container chuyển cho một lần gọi batch listener.

Bật **subBatchPerPartition** chỉ thay đổi cách container phân chia kết quả poll. Nó không tạo thêm consumer, không thay đổi số partition và không khiến các sub-batch của cùng một consumer tự động chạy song song.

Ví dụ, một consumer được giao bốn partition và poll nhận record từ cả bốn partition. Container có thể gọi listener bốn lần cho bốn sub-batch. Những invocation này được thực hiện theo luồng xử lý của consumer đó. Nếu muốn tăng mức song song, cần đánh giá concurrency và số partition, không chỉ bật sub-batch.

Nếu tăng concurrency từ hai lên bốn trong khi topic có bốn partition, group có thể phân phối tối đa bốn partition cho bốn consumer. Mỗi consumer vẫn có thể nhận record từ partition được giao và tạo sub-batch tương ứng. Tổng số consumer trên toàn deployment còn phụ thuộc số instance và concurrency của mỗi instance.

## 7. Quan hệ với partition ordering

Kafka bảo đảm thứ tự record trong cùng một partition. Khi container chia sub-batch theo partition, các record trong một invocation giữ thứ tự tương ứng với thứ tự đọc của partition.

Ví dụ:

| Partition | Record theo thứ tự offset |
|---|---|
| orders.created-0 | 100, 101, 102 |
| orders.created-1 | 200, 201 |
| orders.created-2 | 300, 301, 302 |

Listener nhận các nhóm riêng:

- Sub-batch partition 0: 100, 101, 102.
- Sub-batch partition 1: 200, 201.
- Sub-batch partition 2: 300, 301, 302.

Không có cam kết rằng toàn bộ record của partition 0 phải được xử lý trước partition 1 trong một hệ thống nhiều consumer. Thứ tự giữa các partition không được Kafka bảo đảm. Nếu nghiệp vụ cần thứ tự giữa các sự kiện của cùng một đơn hàng, producer phải dùng key ổn định để các sự kiện đó được ghi vào cùng partition.

Không nên chuyển việc xử lý từng record trong sub-batch sang executor bất đồng bộ rồi trả khỏi listener ngay nếu cần giữ thứ tự và acknowledgement đúng. Container có thể xem invocation đã hoàn tất trong khi side effect thực tế vẫn còn chạy. Nếu xử lý bất đồng bộ, ứng dụng phải quản lý completion và lỗi trước khi xác nhận tiến độ.

## 8. Transaction theo sub-batch

Khi dùng batch listener với Kafka transaction manager, **subBatchPerPartition** có thể được dùng để tạo transaction boundary theo partition. Thay vì một transaction bao trùm các record từ nhiều partition trong poll, container xử lý từng sub-batch trong transaction riêng theo semantics của phiên bản và cấu hình transaction.

Điều này có thể hữu ích khi:

- Mỗi partition là một luồng xử lý độc lập.
- Ứng dụng ghi kết quả trở lại Kafka và muốn commit output cùng offset đầu vào trong cùng Kafka transaction.
- Một partition sub-batch thất bại không nên buộc rollback các partition sub-batch khác đã được commit riêng.
- Đội vận hành cần xác định transaction thất bại thuộc partition nào.

Sơ đồ minh họa:

~~~mermaid
flowchart TD
    A["Poll batch: partition 0, 1, 2"] --> B["Sub-batch partition 0"]
    A --> C["Sub-batch partition 1"]
    A --> D["Sub-batch partition 2"]
    B --> E["Transaction 0"]
    C --> F["Transaction 1"]
    D --> G["Transaction 2"]
    E --> H["Commit hoặc rollback"]
    F --> I["Commit hoặc rollback"]
    G --> J["Commit hoặc rollback"]
~~~

Mỗi transaction được minh họa độc lập theo sub-batch. Việc commit hay rollback thực tế phụ thuộc kết quả listener, transaction manager, error handler và trạng thái Kafka. Nếu listener không sử dụng transaction manager, không nên suy luận rằng bật sub-batch tự tạo ra transaction.

### Kafka transaction không bao trùm database tự động

Nếu listener cập nhật database quan hệ và đồng thời ghi Kafka, Kafka transaction không tự làm cho database transaction trở thành một phần của cùng giao dịch nguyên tử. Cần dùng outbox/inbox hoặc cơ chế phối hợp giao dịch phù hợp.

Với Kafka-to-Kafka processing, transaction có thể phối hợp record đầu ra và offset đầu vào theo cấu hình Spring Kafka. Consumer downstream nên dùng **isolation.level=read_committed** nếu cần chỉ nhìn thấy record thuộc transaction đã commit.

### Cân nhắc chi phí transaction

Transaction cho từng partition sub-batch có thể làm tăng số transaction so với một transaction cho toàn batch poll. Cần đo transaction rate, commit latency, broker load và throughput. Một partition có batch nhỏ hoặc chỉ một record cũng có thể tạo một transaction nếu cấu hình yêu cầu.

Chọn phạm vi transaction dựa trên ranh giới nghiệp vụ và yêu cầu phục hồi, không chỉ dựa trên mong muốn giảm số lần gọi listener.

## 9. Error handling khi xử lý sub-batch

Batch listener có thể gặp lỗi ở một record trong nhóm. Khi bật **subBatchPerPartition**, invocation lỗi tương ứng với một partition sub-batch, giúp xác định rõ partition liên quan. Tuy nhiên, cách container giữ offset, retry hoặc recover record vẫn phụ thuộc error handler và acknowledgement mode.

Các câu hỏi cần xác định:

- Listener ném exception ở record nào?
- Cả sub-batch có được retry hay chỉ record lỗi?
- Error handler có seek lại partition hay recover record?
- Offset nào được commit sau khi recovery?
- Nếu dùng transaction, transaction của sub-batch đã rollback hay commit?
- Những sub-batch khác trong cùng poll đã được xử lý hoặc commit chưa?

Ví dụ error handler dùng **DefaultErrorHandler**:

~~~java
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

factory.setCommonErrorHandler(
        new DefaultErrorHandler(
                new FixedBackOff(1_000L, 2L)
        )
);
~~~

Đây chỉ là cấu hình retry minh họa. Với batch listener, nếu cần chỉ rõ vị trí record lỗi trong batch, có thể sử dụng cơ chế phù hợp như **BatchListenerFailedException** theo phiên bản Spring Kafka. Nếu cần DLT, phải bảo đảm publisher có quyền ghi và recovery metadata đủ để điều tra/replay.

Không coi sub-batch per partition là cơ chế tự động cô lập mọi lỗi. Nó chia phạm vi listener invocation; semantics retry, commit và rollback vẫn do container, error handler và transaction configuration quyết định.

## 10. AckMode và offset commit

**subBatchPerPartition** và **AckMode** là hai cấu hình khác nhau:

- subBatchPerPartition quyết định cách chia record trước khi gọi batch listener.
- AckMode quyết định thời điểm container xác nhận và commit offset.

Ví dụ factory:

~~~java
factory.setBatchListener(true);

var properties = factory.getContainerProperties();
properties.setSubBatchPerPartition(true);
properties.setAckMode(ContainerProperties.AckMode.BATCH);
~~~

Trong cấu hình không giao dịch, BATCH thường xác nhận batch sau khi listener xử lý thành công theo semantics của container. Khi batch được chia thành sub-batch, cần hiểu phiên bản Spring Kafka xử lý acknowledgement và offset qua các invocation ra sao. Với transaction manager, offset có thể được phối hợp vào transaction theo cơ chế transactional container.

Không nên thay đổi AckMode chỉ để có sub-batch. Chọn acknowledgement theo delivery semantics mong muốn, sau đó bật chia partition nếu cần invocation hoặc transaction boundary theo partition.

### Vì sao vẫn có thể redelivery?

Nếu side effect đã hoàn tất nhưng offset chưa commit thành công, consumer có thể nhận lại record khi restart hoặc rebalance. Sub-batch không loại bỏ cửa sổ này. Consumer vẫn cần idempotency, đặc biệt khi batch ghi database hoặc gọi API bên ngoài.

## 11. Payload list hay ConsumerRecord list?

Lựa chọn kiểu tham số listener ảnh hưởng thông tin mà ứng dụng có thể sử dụng.

| Kiểu listener | Có thể truy cập | Phù hợp khi |
|---|---|---|
| **List<V>** | Payload của từng record | Chỉ cần xử lý nghiệp vụ trên dữ liệu |
| **List<ConsumerRecord<K,V>>** | Payload, key, topic, partition, offset, timestamp và headers | Cần định tuyến, logging, checkpoint hoặc chẩn đoán theo partition |
| Batch message có headers | Payload và headers được chuyển đổi theo converter | Ứng dụng dùng Spring Messaging abstraction |

Khi bật **subBatchPerPartition**, dùng **List<ConsumerRecord<K,V>>** giúp code có thể kiểm tra rằng các record cùng topic và partition. Điều này hữu ích nếu batch được ghi sang database với khóa partition hoặc cần log offset đầu/cuối.

Nếu dùng payload list, hãy cân nhắc thêm header hoặc metadata phù hợp nếu nghiệp vụ cần biết partition. Không suy ra partition từ key vì key có thể không duy nhất hoặc partitioner có thể thay đổi.

## 12. Ví dụ đầy đủ với batch listener

Ví dụ dưới đây minh họa một factory batch listener, chia sub-batch theo partition và một listener ghi log metadata của nhóm:

~~~java
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;
import org.springframework.kafka.listener.ContainerProperties;
import org.springframework.stereotype.Component;

@Configuration
class OrderBatchKafkaConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
    orderBatchListenerFactory(
            ConsumerFactory<String, OrderEvent> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();

        factory.setConsumerFactory(consumerFactory);
        factory.setBatchListener(true);
        factory.setConcurrency(3);

        var properties = factory.getContainerProperties();
        properties.setSubBatchPerPartition(true);
        properties.setAckMode(ContainerProperties.AckMode.BATCH);

        return factory;
    }
}

@Component
class OrderBatchConsumer {

    @KafkaListener(
        id = "orderBatchConsumer",
        topics = "orders.created",
        groupId = "billing-service",
        containerFactory = "orderBatchListenerFactory"
    )
    public void consume(
            List<ConsumerRecord<String, OrderEvent>> records) {

        if (records.isEmpty()) {
            return;
        }

        String topic = records.get(0).topic();
        int partition = records.get(0).partition();

        long firstOffset = records.get(0).offset();
        long lastOffset = records.get(records.size() - 1).offset();

        billingService.processPartitionBatch(
                topic,
                partition,
                records
        );

        log.info(
                "Processed {} records from {}-{} offsets {}..{}",
                records.size(),
                topic,
                partition,
                firstOffset,
                lastOffset
        );
    }
}
~~~

Trong ví dụ:

- Factory bật batch mode.
- Concurrency bằng ba tạo tối đa ba consumer con cho mỗi instance của listener container.
- Container chia batch thành sub-batch theo topic-partition.
- Listener nhận một nhóm record cùng partition.
- Ứng dụng có thể log partition và khoảng offset của invocation.

Đây là ví dụ cấu hình cơ bản, chưa bao gồm transaction manager, error handler, serializer/deserializer và dependency injection cho service. Các thành phần đó cần được bổ sung theo môi trường thực tế.

## 13. Khi nào nên bật và khi nào nên tắt?

### Nên cân nhắc bật khi

- Listener là batch listener và cần xử lý mỗi partition như một đơn vị riêng.
- Ứng dụng muốn dùng transaction boundary theo partition với Kafka transaction manager.
- Nghiệp vụ hoặc logging cần biết rõ mỗi invocation thuộc một topic-partition.
- Việc nhóm record trong ứng dụng hiện đang lặp lại và có thể giao cho container.
- Error handling cần khoanh invocation theo partition, với semantics retry/recovery đã được kiểm chứng.

### Có thể giữ tắt khi

- Listener cần xử lý toàn bộ batch poll như một đơn vị.
- Ứng dụng không cần tách record theo partition.
- Một transaction cho toàn bộ batch là ranh giới đã được thiết kế và kiểm chứng.
- Việc tăng số invocation làm tăng overhead mà không đem lại lợi ích.
- Listener đã có logic nhóm và xử lý đa partition phù hợp.

Không có lựa chọn đúng cho mọi workload. Hãy xác định ranh giới xử lý và transaction mong muốn trước khi bật.

## 14. Những giới hạn cần hiểu

**Không tạo song song tự động.** Sub-batch được gọi riêng nhưng thường vẫn được xử lý tuần tự trên consumer thread. Muốn tăng song song phải xem concurrency, partition count và cách ứng dụng xử lý bất đồng bộ.

**Không tạo thứ tự giữa partition.** Mỗi partition có thứ tự riêng. Sub-batch không tạo một thứ tự toàn cục cho các event trong topic.

**Không thay đổi assignment.** Kafka vẫn quyết định partition nào được giao cho consumer. Tùy chọn chỉ chia batch của những partition consumer đã nhận.

**Chỉ có ý nghĩa với batch listener.** Record listener vốn được gọi từng record; chia batch theo partition không áp dụng theo cách tương tự.

**Không tự tạo transaction nếu không cấu hình transaction manager.** Sub-batch là đơn vị invocation. Transaction boundary cần transaction manager và cấu hình phù hợp.

**Không loại bỏ duplicate.** Side effect đã hoàn tất trước commit vẫn có thể bị thực hiện lại sau sự cố. Idempotency vẫn là yêu cầu của ứng dụng.

**Không bảo đảm các sub-batch luôn có kích thước bằng nhau.** Số record phụ thuộc dữ liệu có sẵn, phân bố partition, fetch và giới hạn poll.

## 15. Quan sát và chẩn đoán production

Khi bật **subBatchPerPartition**, log nên xác định invocation nào đang xử lý partition nào. Với ConsumerRecord list, có thể lấy topic, partition, offset đầu và cuối của nhóm.

Các thông tin nên quan sát:

| Thông tin | Mục đích |
|---|---|
| Listener ID | Xác định endpoint |
| Consumer group | Xác định phạm vi phân phối partition |
| Topic và partition | Khoanh vùng sub-batch |
| Số record trong sub-batch | Theo dõi batch size theo partition |
| Offset đầu/cuối | Theo dõi tiến độ xử lý |
| Processing duration | Phát hiện partition chậm |
| Retry/recovery count | Xác định lỗi lặp |
| Commit/transaction result | Xác định tiến độ đã được lưu hay chưa |
| Consumer lag | Phát hiện partition tồn đọng |

### Dấu hiệu bất thường

- Một partition có sub-batch lớn hơn hẳn các partition khác: kiểm tra key distribution, producer traffic và partition skew.
- Một partition thường xuyên xử lý chậm: kiểm tra dữ liệu nóng, downstream query hoặc lock contention theo khóa.
- Nhiều invocation rất nhỏ: xem throughput, poll behavior và chi phí listener call.
- Transaction rate tăng mạnh: xác định mỗi sub-batch có tạo transaction riêng theo cấu hình hay không.
- Một partition liên tục retry: kiểm tra poison record, error handler và recovery policy.
- Duplicate tăng sau rebalance: đối chiếu offset commit và side effect idempotency.

Không dùng tổng consumer lag để kết luận một partition cụ thể bị chậm. Xem lag theo partition và liên kết với thời gian xử lý sub-batch.

## 16. Kiểm thử subBatchPerPartition

Kiểm thử nên dùng Kafka broker thật hoặc test container tương đương để xác minh container chia batch đúng cách. Unit test cho hàm xử lý list không chứng minh listener container đang tạo sub-batch theo partition.

Một bài kiểm thử cơ bản:

1. Tạo topic có ít nhất ba partition.
2. Gửi record với key được chọn để phân bố vào các partition khác nhau.
3. Cấu hình batch listener với **subBatchPerPartition=true**.
4. Đảm bảo consumer group có assignment cho các partition cần thử.
5. Ghi nhận topic-partition của từng invocation.
6. Xác nhận mọi record trong một invocation thuộc cùng topic-partition.
7. Xác nhận có nhiều invocation khi poll nhận record từ nhiều partition.
8. Kiểm tra thứ tự offset trong từng invocation.
9. Dừng consumer trong lúc có record chưa commit và xác nhận khả năng redelivery.
10. Nếu dùng transaction, kiểm tra commit/rollback của từng sub-batch theo cấu hình.

Có thể kiểm tra invariant ngay trong listener:

~~~java
private void assertSinglePartition(
        List<ConsumerRecord<String, OrderEvent>> records) {

    if (records.isEmpty()) {
        return;
    }

    var first = records.get(0);

    boolean mixedPartition = records.stream().anyMatch(record ->
            !record.topic().equals(first.topic())
                    || record.partition() != first.partition()
    );

    if (mixedPartition) {
        throw new IllegalStateException(
                "Expected a single TopicPartition per sub-batch"
        );
    }
}
~~~

Dùng kiểm tra này trong test hoặc assertion có kiểm soát nếu tính đồng nhất partition là điều kiện bắt buộc. Không nhất thiết phải ném exception ở production chỉ để kiểm tra một giả định cấu hình; có thể ghi metric hoặc log cảnh báo tùy yêu cầu.

## 17. Lỗi triển khai thường gặp

**Bật subBatchPerPartition nhưng quên batch mode.** Factory cần bật batch listener và method phải nhận kiểu dữ liệu batch phù hợp.

**Giả định mỗi lần poll chỉ chứa một partition.** Một consumer có thể được giao nhiều partition và poll nhận record từ nhiều partition.

**Tự suy ra partition từ key.** Partition có thể được chọn bằng partitioner và metadata record mới là nguồn chính xác.

**Cho rằng mỗi sub-batch chạy trên thread riêng.** Container tách invocation, không tự biến chúng thành các tác vụ song song.

**Bật tùy chọn rồi kỳ vọng tăng throughput.** Số consumer và assignment không thay đổi. Overhead invocation còn có thể tăng.

**Không kiểm tra transaction manager.** Tùy chọn không tự tạo transaction nếu listener container không được cấu hình transaction phù hợp.

**Xử lý bất đồng bộ rồi trả về ngay.** Container có thể xác nhận invocation trước khi side effect hoàn tất nếu ứng dụng không phối hợp completion đúng cách.

**Không thiết kế idempotency.** Redelivery vẫn có thể xảy ra khi offset chưa commit hoặc transaction rollback.

**Bỏ qua partition skew.** Một partition nóng có thể tạo sub-batch lớn và chậm, dù các partition khác xử lý nhanh.

## 18. Runbook khi sub-batch hoạt động không như mong đợi

1. Xác định listener ID, container factory và consumer group.
2. Xác minh endpoint đang dùng batch listener.
3. Kiểm tra giá trị **subBatchPerPartition** trên đúng ContainerProperties.
4. Xác nhận ConsumerRecord metadata của các record trong từng invocation.
5. Kiểm tra topic-partition assignment của consumer.
6. So sánh số invocation với số partition thực sự có record trong poll.
7. Đo batch size và processing time theo từng partition.
8. Kiểm tra AckMode, error handler và transaction manager.
9. Đối chiếu commit/rollback và offset khi có lỗi.
10. Kiểm tra idempotency nếu record được giao lại.
11. Điều chỉnh concurrency hoặc partitioning chỉ khi dữ liệu đo được cho thấy cần tăng khả năng song song.
12. Sau thay đổi, xác minh cả throughput, lag, transaction rate, retry và duplicate.

Nếu listener chỉ nhận một sub-batch dù consumer được giao nhiều partition, kiểm tra xem các partition khác có record trong poll hay không. Việc được giao partition không có nghĩa poll nào cũng chứa record từ partition đó.

## 19. Checklist trước khi đưa vào production

**Cấu hình listener**

- [ ] Factory được chọn đúng bởi endpoint **@KafkaListener**.
- [ ] Batch mode được bật và method signature nhận kiểu batch phù hợp.
- [ ] **subBatchPerPartition** được đặt rõ ràng trên đúng ContainerProperties.
- [ ] ConsumerFactory và partition assignment được xác định.
- [ ] AckMode phù hợp với cách listener xác nhận offset.

**Nghiệp vụ và transaction**

- [ ] Listener xử lý đúng một topic-partition trong mỗi invocation khi tùy chọn bật.
- [ ] Side effect an toàn khi record được giao lại.
- [ ] Transaction manager được cấu hình nếu cần transaction boundary theo sub-batch.
- [ ] Error handler có retry/recovery phù hợp với batch.
- [ ] Không giả định Kafka transaction bao trùm database transaction.

**Hiệu năng và quan sát**

- [ ] Đã đo số invocation, batch size và processing time theo partition.
- [ ] Đã đánh giá partition skew và downstream capacity.
- [ ] Không dựa vào subBatchPerPartition để tạo concurrency.
- [ ] Log có listener ID, group, topic, partition và offset.
- [ ] Theo dõi lag, transaction rate, retry, recovery và duplicate.

**Kiểm thử**

- [ ] Có test với nhiều partition được consumer nhận.
- [ ] Xác nhận từng invocation chỉ chứa một topic-partition.
- [ ] Kiểm tra thứ tự offset trong partition.
- [ ] Kiểm tra redelivery khi dừng trước commit.
- [ ] Nếu dùng transaction, kiểm tra commit và rollback theo từng sub-batch.

## 20. Nguyên tắc sử dụng

**subBatchPerPartition** hữu ích khi batch listener cần nhận từng nhóm record theo một partition, đặc biệt khi xử lý hoặc transaction cần ranh giới theo partition. Container thực hiện việc nhóm, nên listener không phải tự tách batch hỗn hợp sau mỗi poll.

Tùy chọn này chỉ ảnh hưởng cách listener nhận batch. Nó không thay đổi partition assignment, không tạo consumer song song và không loại bỏ redelivery. Hãy cấu hình rõ batch mode, AckMode, error handler và transaction manager; dùng metadata record để theo dõi partition; và giữ side effect idempotent. Đo batch size, thời gian xử lý, lag và transaction rate theo từng partition trước khi kết luận rằng cấu hình phù hợp với production.
