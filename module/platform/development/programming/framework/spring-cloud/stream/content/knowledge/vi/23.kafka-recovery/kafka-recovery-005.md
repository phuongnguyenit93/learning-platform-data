# Chọn xử lý lỗi tại binder hoặc listener container

Khi một consumer Spring Cloud Stream đọc message từ Kafka, lỗi có thể được xử lý ở hai lớp. **Binder-level error handling** để Kafka Binder áp dụng retry và DLQ theo thuộc tính của binding. **Listener-container error handling** giao việc quyết định retry, backoff, phục hồi và xác nhận offset cho listener container của Spring Kafka, thường thông qua CommonErrorHandler như DefaultErrorHandler.

Hai lựa chọn cùng hướng đến việc xử lý message lỗi, nhưng nằm ở hai vị trí khác nhau trong đường đi của message. Chọn đúng lớp giúp cấu hình đơn giản khi nhu cầu phổ biến, hoặc kiểm soát sâu hơn khi cần chính sách retry riêng, DLQ ở cluster khác, phân loại exception hay theo dõi từng lần thử.

## 1. Vị trí của hai lớp xử lý lỗi

Luồng xử lý rút gọn:

~~~text
Kafka topic
    |
    v
Kafka consumer / listener container
    |
    v
Kafka Binder
    |
    v
Spring Cloud Stream binding
    |
    v
Function / Consumer
    |
    v
Xử lý nghiệp vụ
~~~

Khi hàm xử lý imperative ném exception, lỗi được truyền ngược qua đường xử lý message. Kafka Binder có thể áp dụng retry và DLQ theo cấu hình binding. Ở một lựa chọn khác, listener container của Spring Kafka nhận trách nhiệm xử lý exception, quyết định có giao lại record, bỏ qua sau khi phục hồi hay gửi record sang dead-letter topic.

Sự khác biệt chính:

- **Binder-level:** chính sách được khai báo bằng các thuộc tính Spring Cloud Stream; binder quản lý retry/DLQ trong cơ chế của nó. Đây thường là lựa chọn đầu tiên cho retry hữu hạn và DLQ thông thường.
- **Listener-container-level:** ứng dụng cấu hình CommonErrorHandler, DefaultErrorHandler, recoverer và BackOff trên listener container. Cách này cho phép dùng các khả năng chuyên sâu của Spring Kafka và tùy biến theo destination/group.

Không nên cấu hình cả hai lớp cùng xử lý một binding mà không xác định rõ bên nào sở hữu retry và DLQ. Nếu cả binder và container cùng retry, số lần thử thực tế có thể khác dự kiến, gây trễ kéo dài hoặc phát lại nhiều lần.

## 2. Chọn binder-level khi chính sách xử lý đơn giản

Binder-level phù hợp khi ứng dụng cần:

- Một số lần thử hữu hạn với backoff đơn giản.
- Gửi record lỗi sang DLQ của cùng Kafka cluster.
- Một chính sách gần giống nhau cho binding hoặc một vài binding.
- Ít phụ thuộc vào chi tiết nội bộ của Kafka consumer.
- Cấu hình dễ đọc và dễ quản lý cùng application.yml.

Ví dụ consumer xử lý sự kiện đơn hàng:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderCreated(String orderId, String customerId) {}

interface OrderService {
    void process(OrderCreated order);
}

@Configuration
class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService orderService) {
        return orderService::process;
    }
}
~~~

Khai báo binding, retry và DLQ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.order-processor.dlq
~~~

Trong cấu hình này, max-attempts bằng 4 là tối đa bốn lần gọi handler, tính cả lần giao đầu tiên. Backoff bắt đầu ở 1 giây, tăng theo hệ số 2 và không vượt quá 10 giây. Khi các lần thử hết mà lỗi vẫn còn, binder chuyển record sang DLQ đã chỉ định.

Kafka Binder yêu cầu consumer group tường minh để bật DLQ. Consumer anonymous không thể bật tính năng này. Nếu không đặt dlq-name, binder dùng tên mặc định theo dạng error.<destination>.<group>. Record lỗi được gửi sang DLQ cùng metadata nguồn và thông tin exception mà binder hỗ trợ.

## 3. Cách binder thực hiện retry và DLQ

Với Kafka Binder, khi retry và enable-dlq được cấu hình trên consumer binding, các thao tác này mặc định được thực hiện bên trong binder, không cần listener container hoặc Kafka consumer trực tiếp điều khiển retry. Về khái niệm:

~~~text
Nhận record
    |
    v
Gọi Function / Consumer
    |
    +---- thành công ----------------> tiếp tục
    |
    v
Handler ném exception
    |
    v
Binder retry theo max-attempts / backoff
    |
    +---- lần thử sau thành công ----> tiếp tục
    |
    v
Hết lần thử
    |
    v
Gửi record tới DLQ
~~~

Binder-level giúp người phát triển không phải tự cài DefaultErrorHandler cho trường hợp phổ biến. Tuy nhiên, nó không cung cấp mọi khả năng tùy biến của listener container. Khi cần quyết định theo record, exception, partition hoặc trạng thái consumer, cần cân nhắc chuyển sang container-level.

Một chi tiết riêng của Kafka Binder cần nhớ: nếu DLQ không bật, max-attempts không điều khiển retry theo cách binder-level như khi DLQ được bật. Trong trường hợp đó, retry có thể quay về mặc định của listener container Spring Kafka. Tài liệu Kafka Binder hiện hành mô tả mặc định container là mười lần retry. Vì vậy, đặt max-attempts bằng 1 trong binding mà không bật DLQ không có nghĩa là đã tắt hoàn toàn retry. Nếu muốn thay đổi chính sách này, hãy cấu hình error handler của container.

## 4. Khi nào nên chuyển retry/DLQ sang listener container?

Listener-container-level phù hợp hơn trong các tình huống:

| Nhu cầu | Vì sao container-level phù hợp |
|---|---|
| Tổng thời gian retry/backoff có thể vượt max.poll.interval.ms | Có thể dùng cơ chế backoff/pause của listener container để kiểm soát consumer và rebalance |
| Gửi dead letter sang Kafka cluster khác | Có thể cấu hình KafkaTemplate/recoverer riêng cho cluster đích |
| Cần RetryListener hoặc callback theo từng lần thử | Spring Kafka error handler cung cấp hook chuyên sâu |
| Phân loại exception phức tạp | DefaultErrorHandler cho phép phân biệt lỗi retryable và non-retryable |
| Cần logic phục hồi theo record, partition hoặc offset | Recoverer có quyền truy cập ConsumerRecord |
| Cần tùy biến cách seek, commit hoặc xác nhận offset | Listener container quản lý vòng đời consumer và acknowledgement |
| Dùng batch listener | Retry nội bộ binder không hỗ trợ batch mode; cần cơ chế ở container hoặc acknowledgement phù hợp |

Nếu chính sách chỉ là “thử lại vài lần rồi gửi DLQ cùng cluster”, binder-level thường đủ. Nếu yêu cầu đụng đến hành vi consumer, offset, thời gian poll hoặc cluster đích, container-level thường thích hợp hơn.

## 5. CommonErrorHandler và DefaultErrorHandler

Spring Kafka cung cấp CommonErrorHandler làm giao diện chung cho xử lý lỗi ở record listener và batch listener. DefaultErrorHandler là một triển khai phổ biến, hỗ trợ:

- Backoff giữa các lần giao lại.
- Recoverer được gọi khi hết lần thử.
- Phân loại exception có thể retry hoặc không retry.
- Xử lý record lỗi và các record còn lại trong batch theo semantics của container.
- Điều chỉnh cách seek hoặc giữ lại record để giao lại.

Với Spring Kafka từ phiên bản 2.8, CommonErrorHandler thay thế các API cũ như SeekToCurrentErrorHandler. Khi viết code mới, dùng DefaultErrorHandler và kiểm tra tương thích với phiên bản Spring Kafka được Spring Cloud Stream quản lý.

Ví dụ tạo handler có retry và recoverer:

~~~java
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class KafkaErrorHandlerConfiguration {

    @Bean
    CommonErrorHandler orderErrorHandler(KafkaTemplate<Object, Object> template) {
        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        template,
                        (record, exception) -> new TopicPartition(
                                record.topic() + ".dlq",
                                record.partition()));

        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1000L, 2L));
    }
}
~~~

FixedBackOff với 1000 ms và 2 lần retry chờ 1 giây giữa các lần thử, cho phép tối đa ba lần xử lý tính cả lần đầu. Khi hết retry, DeadLetterPublishingRecoverer gửi record đến topic có hậu tố .dlq, giữ partition ID tương ứng. Topic DLQ phải tồn tại hoặc được provisioning theo chính sách của hệ thống và phải có đủ partition để nhận partition ID được chọn.

Ví dụ minh họa CommonErrorHandler và recoverer; KafkaTemplate cần được cấu hình với serializer phù hợp cho key/value thực tế. Nếu dùng native encoding hoặc payload nhị phân, hãy bảo đảm template có thể publish cả record lỗi theo đúng định dạng.

## 6. Gắn handler vào đúng listener container

Có thể dùng ListenerContainerCustomizer để tùy biến container sau khi binder đã tạo và áp dụng cấu hình cơ bản:

~~~java
import org.springframework.cloud.stream.config.ListenerContainerCustomizer;
import org.springframework.kafka.listener.AbstractMessageListenerContainer;
import org.springframework.kafka.listener.CommonErrorHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderContainerConfiguration {

    @Bean
    ListenerContainerCustomizer<AbstractMessageListenerContainer<?, ?>>
    orderContainerCustomizer(CommonErrorHandler orderErrorHandler) {

        return (container, destinationName, group) -> {
            if ("orders.created".equals(destinationName)
                    && "order-processor".equals(group)) {
                container.setCommonErrorHandler(orderErrorHandler);
            }
        };
    }
}
~~~

Customizer nhận tên destination và group nên có thể chỉ áp dụng handler cho binding cần thiết. Tránh gắn một handler chuyên biệt lên mọi container nếu các binding có chính sách khác nhau.

Với Kafka Binder hiện hành, có thể dùng thuộc tính common-error-handler-bean-name trên từng consumer binding để chọn bean CommonErrorHandler theo tên:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              common-error-handler-bean-name: orderErrorHandler
~~~

Khi thuộc tính này được đặt, handler do ứng dụng cung cấp sẽ được ưu tiên so với các error handler khác mà binder định nghĩa. Đây là lựa chọn gọn khi chỉ cần gắn một bean CommonErrorHandler vào binding cụ thể. Handler đó phải tự chịu trách nhiệm về retry, recover và DLQ mà ứng dụng cần.

Nếu chỉ dùng ListenerContainerCustomizer chung để đặt handler trong khi bật enable-dlq ở binder, binder vẫn có thể giữ quyền điều khiển retry/DLQ theo cấu hình của nó. Nếu mục tiêu là chuyển cả retry và DLQ sang container nhưng vẫn dùng retry metadata và DLQ resolver do binding tạo, hãy dùng ListenerContainerWithDlqAndRetryCustomizer và trả về false từ retryAndDlqInBinding() cho binding tương ứng.

## 7. Chuyển cả retry và DLQ từ binder sang container

Nếu muốn giữ cấu hình retry/backoff/DLQ ở binding nhưng thực thi bằng listener container, Kafka Binder cung cấp ListenerContainerWithDlqAndRetryCustomizer. Customizer này nhận:

- Listener container được tạo cho binding.
- Tên destination và consumer group.
- Hàm xác định topic/partition đích cho DLQ, nếu DLQ được bật.
- Backoff được tạo từ retry properties của binding.

Điểm quan trọng là retryAndDlqInBinding() phải trả về false cho binding được chuyển sang container. Nếu vẫn trả về true, binder tiếp tục sở hữu retry/DLQ trong binding.

~~~java
import org.springframework.cloud.stream.binder.kafka.ListenerContainerWithDlqAndRetryCustomizer;
import java.util.function.BiFunction;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.TopicPartition;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.AbstractMessageListenerContainer;
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.BackOff;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderRetryContainerConfiguration {

    @Bean
    ListenerContainerWithDlqAndRetryCustomizer orderRetryCustomizer(
            KafkaTemplate<?, ?> template) {

        return new ListenerContainerWithDlqAndRetryCustomizer() {

            @Override
            public void configure(
                    AbstractMessageListenerContainer<?, ?> container,
                    String destinationName,
                    String group,
                    BiFunction<ConsumerRecord<?, ?>, Exception, TopicPartition>
                            dlqDestinationResolver,
                    BackOff backOff) {

                if ("orders.created".equals(destinationName)
                        && "order-processor".equals(group)) {

                    ConsumerRecordRecoverer recoverer =
                            new DeadLetterPublishingRecoverer(
                                    template,
                                    dlqDestinationResolver);

                    container.setCommonErrorHandler(
                            new DefaultErrorHandler(recoverer, backOff));
                }
            }

            @Override
            public boolean retryAndDlqInBinding(
                    String destinationName,
                    String group) {

                return !("orders.created".equals(destinationName)
                        && "order-processor".equals(group));
            }
        };
    }
}
~~~

Đồng thời khai báo retry và DLQ trên binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-processor
          consumer:
            max-attempts: 4
            back-off-initial-interval: 1000
            back-off-max-interval: 30000
            back-off-multiplier: 2
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.created.order-processor.dlq
~~~

Trong cách này, binder tạo BackOff và DLQ destination resolver từ binding properties rồi truyền chúng cho customizer. DefaultErrorHandler trong listener container dùng các đối tượng đó để thực hiện retry và recover. Nhờ vậy, cấu hình retry vẫn tập trung trong application.yml, còn thực thi được giao cho Spring Kafka.

Nếu configure() nhận null cho DLQ resolver hoặc backoff, hãy kiểm tra binding đã bật DLQ và khai báo retry đúng chưa trước khi tạo handler. Chỉ dùng customizer này cho binding mà chính sách DLQ/retry được thiết kế tương ứng.

Nếu ứng dụng cấu hình nhiều binder có tên riêng, việc đưa customizer vào binder Kafka có thể cần một BinderCustomizer để gắn nó trực tiếp vào KafkaMessageChannelBinder. Hãy kiểm tra tài liệu phiên bản đang dùng và xác nhận customizer thực sự được gọi cho đúng binder.

## 8. Vì sao tổng thời gian retry liên quan đến max.poll.interval.ms?

Kafka consumer phải tiếp tục poll broker trong giới hạn max.poll.interval.ms. Nếu consumer không poll trong khoảng thời gian quá dài, group coordinator có thể xem consumer là không còn hoạt động và bắt đầu rebalance partition.

Giả sử một message có bốn lần xử lý, mỗi khoảng backoff là 20 giây, cộng thêm thời gian nghiệp vụ. Tổng thời gian xử lý có thể vượt giới hạn poll. Khi đó, partition có thể bị thu hồi và giao cho consumer khác trong lúc ứng dụng vẫn đang chờ retry.

Khi retry dài, cần:

- Tính tổng thời gian xử lý và backoff, so với max.poll.interval.ms.
- Dùng listener-container-level nếu cần kiểm soát pause/resume và backoff dài.
- Xem xét ContainerPausingBackOffHandler của Spring Kafka khi thời gian chờ dài hơn chu kỳ poll.
- Điều chỉnh max.poll.interval.ms chỉ sau khi đánh giá thời gian xử lý và tác động rebalance.
- Theo dõi rebalance, consumer lag và số lần retry thực tế.

Không tăng max.poll.interval.ms tùy tiện để che một consumer xử lý quá chậm. Nếu message có thể cần nhiều phút để hoàn tất, cân nhắc chuyển tác vụ dài sang workflow bất đồng bộ và chỉ xác nhận message sau khi công việc đã được lưu bền vững.

## 9. Phân loại exception và quyết định retry

Không phải mọi lỗi đều có thể khắc phục bằng retry. DefaultErrorHandler cho phép thêm exception vào nhóm không retry được:

Ví dụ sau giả định ứng dụng đã đăng ký một bean ConsumerRecordRecoverer để gửi record đã hết retry đến DLQ:

~~~java
import org.springframework.kafka.listener.ConsumerRecordRecoverer;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderExceptionClassificationConfiguration {

@Bean
DefaultErrorHandler orderDefaultErrorHandler(
        ConsumerRecordRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1000L, 2L));

    handler.addNotRetryableExceptions(
            IllegalArgumentException.class,
            UnsupportedOperationException.class);

    return handler;
}
}
~~~

Ví dụ xem IllegalArgumentException và UnsupportedOperationException là lỗi không nên thử lại. Cần chọn exception dựa trên hợp đồng nghiệp vụ:

| Loại lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Timeout, kết nối DB gián đoạn | Retry có backoff và giới hạn |
| Lỗi dữ liệu | Payload thiếu trường bắt buộc | Không retry; phục hồi dữ liệu hoặc DLQ |
| Lỗi hợp đồng/schema | Version không được hỗ trợ | Không retry đến khi schema/consumer được sửa |
| Lỗi lập trình | Mapping sai, NullPointerException | Cảnh báo, sửa code; tránh retry vô ích |
| Lỗi phụ thuộc bên ngoài | API đối tác tạm ngừng | Retry theo ngân sách thời gian và rate limit |

DefaultErrorHandler có các exception mặc định được xem là fatal, chẳng hạn lỗi deserialize, message conversion hoặc class cast; những lỗi này thường được chuyển thẳng tới recoverer thay vì retry nhiều lần. Có thể điều chỉnh classification nhưng phải cẩn thận: retry một payload không thể giải mã sẽ không làm dữ liệu tự trở nên hợp lệ.

## 10. Deserialization error xảy ra trước Function

Một số lỗi xảy ra trước khi message được chuyển thành Spring Message<?> và gọi Function. Ví dụ, Kafka consumer không thể deserialize value hoặc key. Trong trường hợp đó, handler nghiệp vụ không nhận được payload đã chuyển đổi để tự kiểm tra.

Với Kafka, có thể dùng ErrorHandlingDeserializer để giữ thông tin lỗi deserialize trong header và cho phép error handler/recoverer của Spring Kafka xử lý record lỗi. Cấu hình cụ thể phụ thuộc serializer/deserializer của ứng dụng:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              configuration:
                key.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                value.deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
                spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
                spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
~~~

Ví dụ minh họa cấu trúc delegate; JsonDeserializer cần được cấu hình target type/trusted packages phù hợp với ứng dụng. Không sao chép nguyên cấu hình này nếu consumer dùng Avro, Protobuf hoặc native deserializer khác. Khi xử lý poison pill, cần kiểm thử việc recoverer có thể publish record gốc sang DLQ và giữ đủ metadata.

## 11. Batch listener và giới hạn retry của binder

Kafka Binder hỗ trợ batch mode để Function nhận một danh sách record từ một lần poll. Tuy nhiên, retry nội bộ binder không hỗ trợ batch mode; max-attempts có thể bị ép về 1. Nếu cần retry batch, phải dùng cơ chế container-level, ví dụ DefaultErrorHandler với batch semantics hoặc manual acknowledgement phù hợp.

Trong batch listener, cần biết record nào trong batch thất bại. Spring Kafka cung cấp BatchListenerFailedException để chỉ ra record/index lỗi trong batch, giúp container commit phần đã xử lý và giao lại phần còn lại theo cấu hình. Nếu dùng manual AckMode, có thể dùng Acknowledgment.nack(index, sleep) để xác định phần batch cần giao lại. Các API và semantics này cần được kiểm tra theo phiên bản Spring Kafka.

Không giả định batch retry giống hệt record retry. Một lỗi ở một record có thể khiến một phần batch hoặc toàn batch được xử lý lại, tùy handler và cách listener báo lỗi.

## 12. Kafka transaction thay đổi cách retry và DLQ

Khi Kafka Binder bật transaction, retry và dead lettering không hoạt động giống đường binder retry thông thường. Nếu retry nằm trong transaction gốc, exception có thể rollback transaction và các record DLQ được publish trong transaction đó cũng rollback.

Với transactional binder, retry properties được dùng để cấu hình DefaultAfterRollbackProcessor ở listener container. Việc publish dead-letter cũng được chuyển sang giai đoạn sau rollback. Vì vậy:

- Không áp dụng máy móc ví dụ binder-level retry/DLQ cho transactional binder.
- Xác định rõ transaction manager và transaction boundary.
- Kiểm tra offset được commit khi record được recover.
- Kiểm thử trường hợp transaction rollback, recoverer thất bại và broker restart.
- Bảo đảm producer/consumer transactional ID và cấu hình transaction phù hợp giữa các instance.

Nếu cần đồng bộ ghi database với Kafka, cần hiểu rõ transaction đang bao phủ hệ thống nào. Kafka transaction không tự làm cho một transaction cơ sở dữ liệu bên ngoài trở thành nguyên tử.

## 13. Reactive Function có cơ chế xử lý lỗi riêng

RetryTemplate và các thuộc tính retry/DLQ dành cho Message handler imperative như Consumer<T> hoặc Function<T, R>. Reactive function nhận và trả Flux không xử lý từng message theo cùng cách; framework kết nối publisher của nó với stream đầu vào.

Với reactive function, dùng operator của Reactor:

~~~java
import java.time.Duration;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

record OrderEvent(String orderId, String status) {}

record OrderResult(String orderId, String status) {}

interface ReactiveOrderService {
    Mono<OrderResult> processReactive(OrderEvent event);
}

@Configuration
class ReactiveOrderConfiguration {

    @Bean
    Function<Flux<OrderEvent>, Flux<OrderResult>> processOrdersReactive(
            ReactiveOrderService orderService) {

        return events -> events.concatMap(event ->
                orderService.processReactive(event)
                        .retryWhen(Retry.backoff(
                                3,
                                Duration.ofSeconds(1))
                                .maxBackoff(Duration.ofSeconds(10))));
    }
}
~~~

Ví dụ dùng concatMap để xử lý tuần tự các event trong publisher; retry được áp dụng cho publisher xử lý từng event. Nếu muốn song song, có thể cân nhắc flatMap, nhưng phải đánh giá thứ tự và giới hạn concurrency. Cần thiết kế riêng cách đưa event thất bại vào DLQ hoặc luồng lỗi; không giả định enable-dlq và max-attempts của imperative handler tự áp dụng cho reactive pipeline.

## 14. ErrorMessage handler không đồng nghĩa với listener-container handler

Spring Cloud Stream cho phép khai báo một Consumer<ErrorMessage> để nhận lỗi ở cấp function binding:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.messaging.support.ErrorMessage;

@Bean
Consumer<ErrorMessage> orderErrorMessages() {
    return errorMessage -> {
        // Ghi audit hoặc phát cảnh báo theo chính sách ứng dụng.
    };
}
~~~

Có thể gắn handler bằng thuộc tính error-handler-definition của binding. Tuy nhiên, custom ErrorMessage handler của Spring Cloud Stream là cơ chế riêng và loại trừ các error handler mặc định của framework/binder cho binding đó. Khi khai báo handler này, gửi message lỗi vào DLQ bằng cơ chế binder sẽ không hoạt động như trước, kể cả khi DLQ được cấu hình.

Ví dụ gắn handler vào binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          error-handler-definition: orderErrorMessages
~~~

Vì vậy, không nhầm ba khái niệm:

- Consumer<ErrorMessage>: handler ở cấp Spring Cloud Stream binding.
- CommonErrorHandler/DefaultErrorHandler: handler ở cấp Spring Kafka listener container.
- Binder retry/DLQ properties: chính sách xử lý lỗi do Kafka Binder quản lý.

Chọn một cơ chế chính cho từng binding, rồi bổ sung logging/metrics theo cách không làm mất đường recover đã chọn.

## 15. Theo dõi hành vi retry và container

Sau khi triển khai, cần quan sát:

- Số lần retry trung bình và phân bố thời gian backoff.
- Số record vào DLQ theo topic, group, exception type.
- Tuổi của record cũ nhất trong DLQ.
- Consumer lag và thời gian xử lý một record.
- Số lần rebalance và dấu hiệu vượt max.poll.interval.ms.
- Tỷ lệ recover thành công và lỗi khi publish DLQ.
- Số lần lỗi deserialize, conversion và lỗi nghiệp vụ.

Log nên có topic, partition, offset, key/event ID, consumer group, binding, exception class và attempt number. Không ghi toàn bộ payload nếu chứa dữ liệu nhạy cảm. Khi container-level handler recover record, cần ghi rõ record đã được publish DLQ thành công hay recoverer thất bại.

## 16. Kiểm thử chính sách xử lý lỗi

Kiểm thử cần xác nhận đúng nơi thực thi retry và đúng kết quả cuối:

1. Handler lỗi lần đầu nhưng thành công ở lần tiếp theo; xác nhận số lần gọi và thời gian backoff.
2. Handler lỗi đến hết retry; xác nhận record được gửi đến đúng DLQ.
3. Exception không retry được; xác nhận recoverer được gọi ngay theo classification.
4. DLQ không bật; xác nhận container policy thực tế thay vì chỉ nhìn max-attempts.
5. Container-level customizer chỉ áp dụng cho đúng destination/group.
6. Khi retryAndDlqInBinding trả false, xác nhận binder không đồng thời thực hiện retry/DLQ.
7. Mô phỏng retry dài để quan sát max.poll.interval.ms và rebalance.
8. Mô phỏng lỗi deserialize trước khi Function chạy.
9. Kiểm thử batch mode, transactional binder và reactive function theo đúng cơ chế riêng.
10. Mô phỏng DLQ publish failure để bảo đảm record không bị mất âm thầm.

Test binder có thể kiểm tra logic Function và một số wiring, nhưng không thay thế integration test cho DefaultErrorHandler, Kafka offset, consumer rebalance, native deserialization và DLQ topic. Dùng Kafka broker thật hoặc môi trường kiểm thử tương đương cho các bảo đảm ở listener container.

## 17. Bảng quyết định

| Tiêu chí | Binder-level | Listener-container-level |
|---|---|---|
| Retry hữu hạn đơn giản | Phù hợp | Có thể dùng nhưng nhiều cấu hình hơn |
| DLQ cùng cluster theo tên chuẩn | Phù hợp | Có thể tùy biến sâu hơn |
| Cần recoverer tùy chỉnh | Hạn chế hơn | Phù hợp |
| Cần gửi DLQ sang cluster khác | Không thuận tiện | Phù hợp với KafkaTemplate riêng |
| Retry dài, liên quan poll interval | Cần cân nhắc chuyển sang container | Có thể dùng container backoff/pause |
| Retry listener hoặc classification phức tạp | Hạn chế | Phù hợp |
| Batch listener | Binder retry không hỗ trợ | Dùng handler/acknowledgement phù hợp |
| Transactional binder | Cần semantics riêng sau rollback | Dùng cơ chế container/AfterRollbackProcessor |
| Reactive Function | RetryTemplate/DLQ imperative không áp dụng | Dùng Reactor operators và luồng lỗi riêng |

## 18. Checklist trước khi phát hành

- Xác định binding dùng imperative hay reactive function.
- Chọn một lớp sở hữu retry và DLQ cho từng binding.
- Nếu dùng binder-level DLQ, đặt consumer group rõ ràng và bật enable-dlq.
- Hiểu max-attempts tính cả lần giao đầu tiên và kiểm tra hành vi khi DLQ tắt.
- Chọn backoff phù hợp với thời gian phục hồi của dependency.
- Nếu chuyển sang container, cấu hình CommonErrorHandler và đúng customizer.
- Với ListenerContainerWithDlqAndRetryCustomizer, trả false cho retryAndDlqInBinding() ở binding được chuyển.
- Kiểm tra tổng thời gian retry so với max.poll.interval.ms.
- Phân loại exception retryable và non-retryable.
- Kiểm thử deserialization error, batch mode và transactional binder nếu ứng dụng dùng các chế độ đó.
- Theo dõi lag, rebalance, DLQ và lỗi recoverer sau triển khai.

Binder-level là lựa chọn phù hợp cho retry và DLQ phổ biến, được khai báo gọn trong binding. Listener-container-level phù hợp khi ứng dụng cần kiểm soát sâu hơn cách Spring Kafka giao lại record, backoff, recoverer, offset hoặc nơi nhận DLQ. Với Kafka Binder, có thể chuyển retry/DLQ từ binder sang container bằng ListenerContainerWithDlqAndRetryCustomizer, đồng thời giữ retry metadata từ binding. Hãy quyết định rõ một lớp chịu trách nhiệm cho mỗi binding và kiểm thử với Kafka thật để xác nhận hành vi retry, acknowledgement, rebalance và DLQ.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Binder: Retry and Dead Letter Processing](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/overview.html)
- [Spring Cloud Stream — Kafka Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html)
- [Spring Cloud Stream — General Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Kafka — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
