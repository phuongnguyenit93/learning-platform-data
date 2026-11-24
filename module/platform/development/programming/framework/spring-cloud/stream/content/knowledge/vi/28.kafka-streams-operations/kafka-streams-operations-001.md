# Cấu hình StreamsBuilderFactoryBean và Kafka Streams client

Kafka Streams cần hai phần để chạy một topology: một builder mô tả nguồn dữ liệu và các phép biến đổi, cùng một runtime kết nối tới Kafka để tiêu thụ, xử lý và phát record. Trong ứng dụng Spring, Spring for Apache Kafka cung cấp StreamsBuilderFactoryBean để quản lý StreamsBuilder và vòng đời của KafkaStreams. Spring Cloud Stream Kafka Streams binder sử dụng cơ chế này phía dưới khi tạo processor từ các bean Function, BiFunction hoặc Consumer.

Khi vận hành bằng Spring Cloud Stream, ứng dụng thường khai báo topology bằng function bean và cấu hình client bằng các thuộc tính của Kafka Streams binder. Nếu cần can thiệp vào lifecycle, state listener hoặc KafkaStreams instance, có thể cung cấp StreamsBuilderFactoryBeanConfigurer. Với ứng dụng Spring Kafka dùng trực tiếp, có thể tự khai báo KafkaStreamsConfiguration và bật @EnableKafkaStreams để Spring tạo factory bean mặc định.

Bài học này giải thích vai trò của từng thành phần, cách cấu hình Kafka Streams client properties, cách tùy chỉnh factory bean đúng thời điểm, quản lý state và shutdown, cùng cách kiểm thử cấu hình khi triển khai Spring Cloud Stream.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt StreamsBuilder, Topology, KafkaStreams và StreamsBuilderFactoryBean.
- Giải thích cách factory bean quản lý lifecycle của Kafka Streams trong Spring.
- Phân biệt cấu hình Kafka Streams binder với cấu hình Spring Kafka độc lập.
- Cấu hình application.id, bootstrap servers, Serde, processing guarantee và client security.
- Chọn cấu hình cấp binder hoặc cấp từng function khi có nhiều processor.
- Dùng StreamsBuilderFactoryBeanConfigurer và KafkaStreamsCustomizer.
- Theo dõi trạng thái RUNNING, REBALANCING, ERROR và quá trình restore state.
- Quản lý state.dir, close timeout và graceful shutdown.
- Kiểm thử cấu hình client, lifecycle và topology với Kafka broker.

## 1. Các thành phần trong vòng đời Kafka Streams

Một ứng dụng Kafka Streams thường đi qua các bước:

1. Xây dựng topology từ các source topic và phép biến đổi.
2. Tạo KafkaStreams từ topology và client properties.
3. Khởi tạo các consumer, producer, admin client và state store cần thiết.
4. Tham gia consumer group, nhận partition assignment và khôi phục state.
5. Chuyển sang trạng thái RUNNING để xử lý record.
6. Đóng runtime có kiểm soát khi ứng dụng dừng.

Bốn kiểu quan trọng:

| Thành phần | Vai trò |
|---|---|
| StreamsBuilder | DSL để khai báo source, KStream, KTable và các phép biến đổi |
| Topology | Đồ thị xử lý được tạo từ StreamsBuilder |
| KafkaStreams | Runtime thực thi topology, quản lý thread, client, state và rebalance |
| StreamsBuilderFactoryBean | Factory bean Spring tạo StreamsBuilder và quản lý KafkaStreams lifecycle |

~~~mermaid
flowchart TD
    A["Spring Cloud Stream function beans"] --> B["Kafka Streams binder"]
    B --> C["StreamsBuilder"]
    C --> D["Topology"]
    E["Kafka Streams client properties"] --> F["StreamsBuilderFactoryBean"]
    D --> F
    F --> G["KafkaStreams runtime"]
    G --> H["Kafka consumers / producers"]
    H --> I["Kafka cluster"]
~~~

StreamsBuilder mô tả công việc cần làm; nó không tự kết nối broker. KafkaStreams thực thi topology. StreamsBuilderFactoryBean kết nối hai phần này với Spring ApplicationContext và lifecycle của container.

## 2. Vì sao cần StreamsBuilderFactoryBean?

Nếu tự khởi tạo KafkaStreams trong một phương thức cấu hình rồi gọi start(), ứng dụng phải tự chịu trách nhiệm:
- Khởi động sau khi topology đã được khai báo.
- Dừng runtime khi Spring context đóng.
- Đóng client và thread đúng thời điểm.
- Theo dõi trạng thái và lỗi.
- Phối hợp nhiều processor trong cùng ứng dụng.

StreamsBuilderFactoryBean giải quyết phần quản lý lifecycle bằng cách triển khai Spring SmartLifecycle. Factory bean cung cấp StreamsBuilder cho các bean topology và tạo KafkaStreams khi được khởi động. Khi Spring context dừng, factory bean đóng KafkaStreams theo cấu hình.

Một quy tắc quan trọng là phải khai báo các KStream/KTable trước khi KafkaStreams bắt đầu chạy. Với factory bean tự động khởi động, topology phải được tạo trước khi ApplicationContext refresh hoàn tất.

Trong Spring Cloud Stream Kafka Streams binder, binder quản lý factory bean cho processor. Function bean của ứng dụng mô tả topology; binder ánh xạ các input/output binding và tạo runtime. Vì vậy, ứng dụng thường không cần tự tạo thêm một StreamsBuilderFactoryBean song song.

## 3. Hai cách tích hợp: Kafka Streams binder và Spring Kafka trực tiếp

Hai mô hình có mục tiêu gần nhau nhưng quyền quản lý lifecycle khác nhau.

| Nội dung | Spring Cloud Stream Kafka Streams binder | Spring Kafka trực tiếp |
|---|---|---|
| Khai báo topology | Function bean nhận/trả KStream hoặc KTable | StreamsBuilder và KStream bean |
| Input/output | Binding do binder ánh xạ | Topic được khai báo trong DSL |
| Client properties | Prefix kafka.streams.binder và function-specific configuration | KafkaStreamsConfiguration bean |
| Factory bean | Binder tạo và quản lý processor factory bean | Spring Kafka tạo qua @EnableKafkaStreams hoặc bean tự khai báo |
| Tùy chỉnh lifecycle | StreamsBuilderFactoryBeanConfigurer | StreamsBuilderFactoryBeanConfigurer trực tiếp |
| Phù hợp | Ứng dụng Spring Cloud Stream dùng binder | Ứng dụng cần tích hợp Kafka Streams trực tiếp |

Không nên cấu hình cả hai mô hình như thể chúng cùng sở hữu một processor. Nếu đã dùng Kafka Streams binder, hãy để binder tạo topology từ function và dùng customizer được hỗ trợ để can thiệp factory bean. Chỉ tự khai báo StreamsBuilderFactoryBean khi ứng dụng chủ động dùng Spring Kafka trực tiếp hoặc có một processor độc lập ngoài binder.

## 4. StreamsBuilderFactoryBean trong Spring Kafka trực tiếp

Khi dùng Spring Kafka mà không dùng Kafka Streams binder, có thể bật @EnableKafkaStreams. Spring tạo factory bean mặc định nếu có bean KafkaStreamsConfiguration mang tên chuẩn.

~~~java
import java.util.HashMap;
import java.util.Map;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.annotation.EnableKafkaStreams;
import org.springframework.kafka.config.KafkaStreamsConfiguration;
import org.springframework.kafka.config.KafkaStreamsDefaultConfiguration;

@Configuration
@EnableKafkaStreams
class DirectKafkaStreamsConfiguration {

    @Bean(name = KafkaStreamsDefaultConfiguration.DEFAULT_STREAMS_CONFIG_BEAN_NAME)
    KafkaStreamsConfiguration kafkaStreamsConfiguration() {
        Map<String, Object> props = new HashMap<>();

        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "order-projection");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
        props.put(
            StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
            Serdes.String().getClass().getName()
        );
        props.put(
            StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
            Serdes.String().getClass().getName()
        );

        return new KafkaStreamsConfiguration(props);
    }
}
~~~

Với cấu hình này, Spring Kafka tạo StreamsBuilderFactoryBean mặc định và cung cấp StreamsBuilder cho các bean topology. Nếu cần thêm factory bean, có thể khai báo riêng và đặt tên rõ ràng.

Khi dùng @EnableKafkaStreams, không tạo thêm bean mặc định trùng tên. Cũng không khai báo một StreamsBuilderFactoryBean thủ công rồi đồng thời mong annotation tạo bean mặc định thứ hai. Chọn một cách quản lý cho từng processor.

## 5. Cấu hình client properties trong Spring Cloud Stream

Kafka Streams sử dụng các thuộc tính của StreamsConfig. Spring Cloud Stream Kafka Streams binder cho phép đặt chúng ở cấp binder hoặc cấp từng function.

Các thuộc tính phổ biến:

| Thuộc tính Kafka Streams | Ý nghĩa |
|---|---|
| application.id | Định danh processor và consumer group nội bộ |
| bootstrap.servers | Danh sách broker để kết nối |
| default.key.serde | Serde mặc định cho key |
| default.value.serde | Serde mặc định cho value |
| processing.guarantee | Mức bảo đảm xử lý, ví dụ at_least_once hoặc exactly_once_v2 |
| num.stream.threads | Số stream thread trong một instance |
| state.dir | Thư mục lưu state local |
| commit.interval.ms | Khoảng thời gian commit theo cấu hình processing |
| replication.factor | Replication factor cho internal topics do Streams tạo |
| security.protocol | Giao thức bảo mật kết nối |

Ví dụ cấu hình binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            brokers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              default.value.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
              processing.guarantee: exactly_once_v2
              num.stream.threads: 2
              state.dir: ${KAFKA_STREAMS_STATE_DIR:/var/lib/app/kafka-streams}
~~~

Đây là cấu hình cấp binder. Những thuộc tính trong binder configuration có thể áp dụng cho mọi processor thuộc binder đó. Nếu ứng dụng có nhiều function processor, hãy cân nhắc tách application ID và các cấu hình riêng theo function để tránh dùng chung nhầm.

Kafka Streams binder có thuộc tính brokers riêng. Các thuộc tính Kafka Streams API khác được đặt dưới configuration. Không dùng nhầm prefix của regular Kafka message-channel binder cho các StreamsConfig properties.

## 6. Application ID toàn cục và theo từng function

application.id xác định danh tính Kafka Streams application. Nó ảnh hưởng đến consumer group, internal topics, state store changelog và khả năng khôi phục tiến độ.

Nếu chỉ có một processor, có thể đặt application ID ở cấp binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: order-projection
~~~

Nếu có nhiều function processor, nên đặt ID riêng:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder;aggregatePayment
    stream:
      kafka:
        streams:
          binder:
            functions:
              enrichOrder:
                applicationId: order-enricher
              aggregatePayment:
                applicationId: payment-aggregator
~~~

Mỗi processor có application ID riêng sẽ có tiến độ tiêu thụ và internal state riêng. Không dùng cùng một application ID cho hai topology độc lập nếu chúng không được thiết kế để cùng một Kafka Streams application.

Thay đổi application ID không đơn giản là đổi tên log. Kafka Streams có thể xem đó là một ứng dụng mới và đọc lại dữ liệu theo chính sách offset, tạo internal topics và state mới. Trước khi đổi, đánh giá retention, replay và tác dụng phụ downstream.

## 7. Cấu hình riêng cho từng processor

Khi có nhiều processor, binder hỗ trợ function-specific configuration. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            functions:
              enrichOrder:
                applicationId: order-enricher
                configuration:
                  processing.guarantee: exactly_once_v2
                  num.stream.threads: 2
              aggregatePayment:
                applicationId: payment-aggregator
                configuration:
                  processing.guarantee: at_least_once
                  num.stream.threads: 1
~~~

Cấu hình riêng hữu ích khi:
- Processor có tải và độ trễ khác nhau.
- Processor có yêu cầu xử lý khác nhau.
- Cần application ID riêng.
- Một topology cần exactly-once trong Kafka, topology khác chấp nhận at-least-once.
- Muốn tránh cấu hình cấp binder ảnh hưởng ngoài ý muốn.

Cấu hình cấp function chỉ áp dụng cho function được chỉ định. Hãy kiểm tra tên bean trong Spring context và tên function trong cấu hình trùng khớp. Nếu một function bị composition hoặc binding override, tên function cuối cùng cần được đối chiếu với binding thực tế.

## 8. Bootstrap servers và bảo mật client

Kafka Streams tạo các Kafka client bên trong. Các client này cần kết nối đúng cluster và có quyền đọc input topic, ghi output topic, truy cập group và quản lý internal topics.

Ví dụ cấu hình SASL_SSL với secret được inject qua environment:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            brokers: ${KAFKA_BOOTSTRAP_SERVERS}
            configuration:
              security.protocol: SASL_SSL
              sasl.mechanism: SCRAM-SHA-512
              sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
              ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
              ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
~~~

Không ghi username, password, JAAS string hoặc truststore password trực tiếp vào file cấu hình được commit. Đưa chúng qua secret manager, Kubernetes Secret hoặc cơ chế cấp phát bí mật của môi trường.

ACL cần cho phép:
- Đọc các input topics.
- Ghi các output topics.
- Sử dụng application ID/consumer group.
- Tạo hoặc truy cập changelog và repartition topics.
- Thực hiện các thao tác metadata cần thiết theo cấu hình cluster.

Khi gặp lỗi authorization, kiểm tra cả topic nghiệp vụ và internal topics. Một topology có thể đọc được input nhưng vẫn không khởi động nếu không tạo hoặc ghi được changelog/repartition topic.

## 9. Processing guarantee và cấu hình producer/consumer

Thuộc tính processing.guarantee xác định mức bảo đảm của Kafka Streams.

- at_least_once cho phép xử lý lại record khi xảy ra lỗi ở ranh giới commit.
- exactly_once_v2 phối hợp offset, state store và output record trong Kafka transaction theo khả năng cluster/client hỗ trợ.

Exactly-once của Kafka Streams bảo vệ luồng xử lý nằm trong phạm vi Kafka Streams và Kafka transaction. Nó không tự bao gồm một lần gọi REST API, gửi email hoặc cập nhật database bên ngoài. Side effect ngoài Kafka vẫn cần idempotency, outbox hoặc cơ chế phối hợp riêng.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              processing.guarantee: exactly_once_v2
              replication.factor: 3
~~~

Exactly-once cần cluster hỗ trợ transaction và cấu hình replication phù hợp. Với production, kiểm tra broker version, transaction state log replication, min ISR và replication factor của internal topics. Không chỉ bật property rồi kết luận hệ thống đã đạt exactly-once end-to-end.

## 10. Tùy chỉnh StreamsBuilderFactoryBean trong Kafka Streams binder

Kafka Streams binder tạo StreamsBuilderFactoryBean cho processor. Khi cần cài đặt state listener, close timeout, KafkaStreamsCustomizer hoặc các tùy chọn factory bean khác, cung cấp bean StreamsBuilderFactoryBeanConfigurer.

Ví dụ theo dõi trạng thái:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class StreamsLifecycleConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(StreamsLifecycleConfiguration.class);

    @Bean
    StreamsBuilderFactoryBeanConfigurer streamsBuilderFactoryBeanConfigurer() {
        return factoryBean -> factoryBean.setStateListener(
            (newState, oldState) ->
                log.info("Kafka Streams state changed: {} -> {}", oldState, newState)
        );
    }
}
~~~

Binder gọi configurer trước khi factory bean khởi động. Ở thời điểm này, có thể thay đổi các thuộc tính được hỗ trợ của factory bean. Đây là nơi thích hợp để gắn listener hoặc cấu hình customizer.

Nếu ứng dụng có nhiều processor, mỗi processor có factory bean riêng. Có thể kiểm tra application ID từ factory bean rồi chỉ áp dụng cấu hình cho processor cần thiết. Không áp dụng một exception policy hoặc state listener đặc thù cho mọi processor nếu các topology có yêu cầu vận hành khác nhau.

## 11. Tùy chỉnh KafkaStreams bằng KafkaStreamsCustomizer

StreamsBuilderFactoryBean có thể nhận KafkaStreamsCustomizer để tùy chỉnh KafkaStreams instance ngay trước khi runtime bắt đầu.

Ví dụ gắn uncaught exception handler:

~~~java
import org.apache.kafka.streams.errors.StreamsUncaughtExceptionHandler;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class StreamsExceptionConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(StreamsExceptionConfiguration.class);

@Bean
StreamsBuilderFactoryBeanConfigurer streamsBuilderFactoryBeanConfigurer() {
    return factoryBean -> factoryBean.setKafkaStreamsCustomizer(
        kafkaStreams -> kafkaStreams.setUncaughtExceptionHandler(exception -> {
            log.error("Uncaught Kafka Streams exception", exception);
            return StreamsUncaughtExceptionHandler.StreamThreadExceptionResponse
                .SHUTDOWN_APPLICATION;
        })
    );
}
}
~~~

Kafka Streams cung cấp các lựa chọn phản hồi cho lỗi không được xử lý của stream thread. Ví dụ:
- REPLACE_THREAD: thay thread bị lỗi bằng thread mới nếu phù hợp.
- SHUTDOWN_CLIENT: dừng KafkaStreams client hiện tại.
- SHUTDOWN_APPLICATION: yêu cầu dừng toàn application.

Chính sách cần được chọn theo loại lỗi và khả năng khôi phục. Không trả về REPLACE_THREAD cho mọi lỗi một cách máy móc: lỗi cấu hình hoặc lỗi dữ liệu lặp lại có thể làm thread mới tiếp tục thất bại. Với lỗi nghiêm trọng, dừng ứng dụng để orchestrator restart có kiểm soát có thể an toàn hơn.

KafkaStreamsCustomizer được gọi gần thời điểm start, vì vậy không lấy KafkaStreams instance quá sớm từ ApplicationContext. Nếu cần truy cập StreamsBuilder hoặc Topology để bổ sung hạ tầng, dùng KafkaStreamsInfrastructureCustomizer thay vì gọi factoryBean.getObject() trong lúc factory bean còn khởi tạo.

## 12. Chọn đúng processor khi có nhiều factory bean

Một ứng dụng có thể có nhiều function processor. Binder tạo factory bean tương ứng cho từng processor, do đó customizer chung cần kiểm tra application ID trước khi áp dụng cấu hình riêng.

~~~java
import org.apache.kafka.streams.StreamsConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class OrderProcessorConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(OrderProcessorConfiguration.class);

@Bean
StreamsBuilderFactoryBeanConfigurer orderProcessorConfigurer() {
    return factoryBean -> {
        String applicationId = factoryBean.getStreamsConfiguration()
            .getProperty(StreamsConfig.APPLICATION_ID_CONFIG);

        if ("order-enricher".equals(applicationId)) {
            factoryBean.setStateListener((newState, oldState) ->
                log.info("order-enricher: {} -> {}", oldState, newState)
            );
        }
    };
}
}
~~~

Hãy dùng application ID đã được cấu hình cho processor tương ứng. Nếu application ID được tạo tự động, hãy kiểm tra giá trị thực tế trong StreamsConfiguration trước khi so sánh. Không giả định mọi factory bean đều thuộc cùng một topology.

Có thể dùng Ordered để sắp xếp nhiều configurer nếu chúng cùng thay đổi factory bean. Khi nhiều customizer sửa cùng một thuộc tính, thứ tự thực thi ảnh hưởng tới kết quả cuối; gom các thay đổi liên quan vào một configurer thường dễ kiểm soát hơn.

## 13. Tùy chỉnh StreamsBuilder và Topology

Có hai nhóm tùy chỉnh khác nhau:

- StreamsBuilderFactoryBeanConfigurer chỉnh factory bean và runtime lifecycle.
- KafkaStreamsInfrastructureCustomizer chỉnh StreamsBuilder hoặc Topology trước khi KafkaStreams được tạo.

Ví dụ khung infrastructure customizer:

~~~java
import org.springframework.kafka.config.KafkaStreamsInfrastructureCustomizer;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class StreamsInfrastructureConfiguration {

@Bean
StreamsBuilderFactoryBeanConfigurer globalStoreConfigurer() {
    return factoryBean -> factoryBean.setInfrastructureCustomizer(
        new KafkaStreamsInfrastructureCustomizer() {
            @Override
            public void configureBuilder(StreamsBuilder builder) {
                // Đăng ký store hoặc source cần thiết trước khi topology được build.
            }

            @Override
            public void configureTopology(Topology topology) {
                // Kiểm tra hoặc tùy chỉnh topology đã được build.
            }
        }
    );
}
}
~~~

Trong ứng dụng Spring Cloud Stream, function bean vẫn là cách chính để mô tả topology nghiệp vụ. Infrastructure customizer dành cho yêu cầu hạ tầng đặc biệt như global state store hoặc can thiệp topology ở mức thấp.

Không gọi factoryBean.getObject() trong configurer chỉ để lấy StreamsBuilder. Factory bean có thể đang trong quá trình khởi tạo và việc truy cập sớm có thể tạo vòng phụ thuộc. Dùng infrastructure customizer để thao tác trên builder/topology theo lifecycle mà Spring Kafka cung cấp.

## 14. Theo dõi state và quá trình restore

KafkaStreams có các trạng thái phản ánh tiến trình hoạt động. Một số trạng thái thường gặp:

| State | Ý nghĩa vận hành |
|---|---|
| CREATED | Runtime đã được tạo nhưng chưa chạy |
| REBALANCING | Đang tham gia hoặc thay đổi partition assignment |
| RUNNING | Topology sẵn sàng xử lý record |
| PENDING_SHUTDOWN | Đang dừng |
| NOT_RUNNING | Không còn chạy |
| ERROR | Runtime gặp lỗi nghiêm trọng |

State listener giúp ghi nhận chuyển trạng thái và phát metric/alert. Ví dụ:
- Ứng dụng ở REBALANCING quá lâu có thể do broker, group coordination hoặc state restore.
- Không chuyển sang RUNNING có thể do lỗi kết nối, ACL, Serde hoặc internal topics.
- Chuyển sang ERROR cần xem log exception và chính sách uncaught exception handler.

Với topology stateful, theo dõi StateRestoreListener để biết tiến độ khôi phục state store. Khi instance mới nhận partition, nó có thể cần đọc changelog để tái tạo local state trước khi xử lý bình thường.

Không đánh đồng trạng thái Spring ApplicationContext đã started với Kafka Streams đã RUNNING. Ứng dụng web có thể mở cổng HTTP trong khi processor vẫn đang rebalance hoặc restore state.

## 15. State directory và phục hồi local state

Kafka Streams lưu state store local trong thư mục state.dir. Đây là dữ liệu làm việc của instance, gắn với application ID và task/partition.

Nguyên tắc vận hành:
- Mỗi instance cần thư mục local riêng, tránh hai process cùng ghi một state directory.
- Cấp quyền filesystem phù hợp cho user chạy ứng dụng.
- Dung lượng đĩa phải đủ cho state store, cache và quá trình restore.
- Theo dõi disk usage và tốc độ restore.
- Không xóa state directory đang được process sử dụng.
- Có kế hoạch khôi phục từ changelog khi local state mất.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              state.dir: /var/lib/my-service/kafka-streams
~~~

Trong container, có thể dùng volume local hoặc ephemeral storage tùy yêu cầu. Nếu local state mất, Kafka Streams có thể tái tạo từ changelog khi cấu hình và dữ liệu còn đủ. Điều này có thể làm thời gian khởi động dài hơn; không có nghĩa cần backup thủ công mọi thư mục state như một nguồn dữ liệu chính.

Không chia sẻ cùng state.dir giữa nhiều replica. Nếu cần persist qua restart, bảo đảm volume gắn đúng instance và không bị hai pod mount ghi đồng thời.

## 16. Graceful shutdown và close timeout

Khi Spring context dừng, StreamsBuilderFactoryBean gọi KafkaStreams.close() để cho thread dừng và giải phóng client. Có thể cấu hình close timeout để kiểm soát thời gian chờ shutdown.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.config.StreamsBuilderFactoryBeanConfigurer;

@Configuration
class StreamsShutdownConfiguration {

@Bean
StreamsBuilderFactoryBeanConfigurer shutdownConfigurer() {
    return factoryBean -> factoryBean.setCloseTimeout(30);
}
}
~~~

Tham số của setCloseTimeout là số giây. Ví dụ trên đặt thời gian chờ đóng KafkaStreams tối đa là 30 giây.

Trong môi trường production:
- Đặt termination grace period của container lớn hơn thời gian shutdown dự kiến.
- Dừng nhận công việc mới trước khi process bị kill nếu có cơ chế điều phối.
- Cho Kafka Streams hoàn tất xử lý và commit theo processing guarantee.
- Theo dõi thời gian từ PENDING_SHUTDOWN tới NOT_RUNNING.
- Tránh kill -9 hoặc hard stop trong quy trình triển khai thông thường.

Không gọi KafkaStreams.close() tùy tiện từ business handler nếu factory bean đang sở hữu lifecycle. Dùng Spring lifecycle hoặc binding control phù hợp để dừng processor. Nếu cần stop/start có điều kiện, thao tác trên factory bean đúng cách và kiểm tra state sau mỗi lần chuyển.

## 17. Health, metrics và quan sát client

Một processor có thể gặp vấn đề dù JVM vẫn sống. Cần kết hợp:
- Kafka Streams state.
- Consumer lag theo input partition.
- Throughput đầu vào/đầu ra.
- Processing latency.
- State restore duration.
- Rebalance count và thời gian rebalance.
- RocksDB/state store disk usage.
- Producer errors và commit failures.
- Thread uncaught exception.
- DLQ hoặc skipped record count nếu có recovery handler.

Spring for Apache Kafka hỗ trợ Micrometer listener cho KafkaStreams instance do factory bean quản lý. Có thể đăng ký listener với MeterRegistry và tag theo processor/application ID. Cần xác minh metric names theo phiên bản thư viện đang dùng.

Health indicator không thay thế business-level monitoring. Processor có thể ở RUNNING nhưng output vẫn không tiến triển do input không có dữ liệu, logic filter loại hết record hoặc downstream topic bị cấu hình sai. Theo dõi cả trạng thái runtime và lưu lượng dữ liệu.

## 18. Những lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| KafkaStreams không khởi động | Thiếu application ID hoặc bootstrap servers | Kiểm tra StreamsConfig và binder properties |
| Processor không tạo đúng group | Application ID trùng hoặc thay đổi ngoài ý muốn | Dùng ID ổn định, riêng cho từng processor |
| Serde exception | Default/key/value Serde không khớp dữ liệu | Cấu hình Serde rõ cho binding |
| Không tạo được changelog topic | ACL hoặc replication factor không phù hợp | Kiểm tra quyền và cluster configuration |
| Processor ở REBALANCING lâu | Broker, group coordinator hoặc restore chậm | Kiểm tra broker, lag và StateRestoreListener |
| Factory bean customizer không chạy | Sai interface, package hoặc bean chưa được scan | Kiểm tra dependency Spring Kafka và component scan |
| Customizer áp dụng sai processor | Không lọc theo application ID | Kiểm tra StreamsConfiguration trước khi chỉnh |
| State restore rất lâu | Changelog lớn hoặc local state bị mất | Theo dõi restore, storage và retention |
| Shutdown kéo dài | Close timeout quá ngắn hoặc thread đang bận | Điều chỉnh timeout và termination grace period |
| Hai instance xung đột state | Dùng chung state.dir | Tạo thư mục riêng cho từng process |
| Exactly-once vẫn có duplicate ở API ngoài | Transaction Kafka không bao phủ external side effect | Dùng idempotency/outbox |
| Đọc được input nhưng không ghi output | ACL thiếu cho output/internal topics | Kiểm tra quyền producer và internal topics |

## 19. Kiểm thử cấu hình và lifecycle

Nên chia kiểm thử thành ba lớp.

### Kiểm tra cấu hình

- Xác minh application ID được đặt đúng cho mỗi function.
- Kiểm tra bootstrap servers, Serde và processing guarantee.
- Kiểm tra các secret/security properties được inject đúng mà không log giá trị bí mật.
- Kiểm tra cấu hình cấp binder không vô tình ghi đè cấu hình function-specific.
- Xác minh state.dir tồn tại và có quyền ghi.

### Integration test với Kafka

Dùng Kafka broker test hoặc Testcontainers để:
1. Khởi động Spring context và binder.
2. Xác minh StreamsBuilderFactoryBean được tạo và processor chuyển sang RUNNING.
3. Gửi record vào input topic.
4. Xác minh topology xử lý và ghi output.
5. Khởi động lại processor và kiểm tra state/offset restoration.
6. Dừng context và xác minh runtime shutdown.
7. Mô phỏng broker unavailable hoặc lỗi Serde để kiểm tra state/error handling.

### Kiểm thử customizer

- Xác minh state listener nhận chuyển trạng thái.
- Xác minh customizer chỉ áp dụng cho application ID dự kiến.
- Kiểm tra uncaught exception policy trong môi trường test.
- Kiểm tra close timeout và graceful shutdown.
- Với stateful topology, kiểm tra restore listener và thời gian phục hồi.

Không chỉ kiểm tra ApplicationContext khởi động thành công. Một cấu hình client chỉ được xác nhận khi processor kết nối broker, nhận partition, xử lý record và dừng đúng cách.

## 20. Bài thực hành: vận hành processor order-projection

Xây dựng processor Spring Cloud Stream Kafka Streams đọc topic orders và ghi order-projections:

1. Khai báo function bean tạo topology từ KStream.
2. Đặt application ID là order-projection.
3. Cấu hình bootstrap servers qua biến môi trường.
4. Cấu hình key/value Serde tương ứng schema.
5. Chọn processing guarantee theo yêu cầu và khả năng cluster.
6. Đặt state.dir riêng cho instance.
7. Khai báo StreamsBuilderFactoryBeanConfigurer để theo dõi state.
8. Lọc factory bean theo application ID nếu ứng dụng có nhiều processor.
9. Gắn KafkaStreamsCustomizer cho uncaught exception policy phù hợp.
10. Chạy integration test với Kafka broker.
11. Gửi record và xác minh output topic.
12. Restart processor và quan sát state restoration.
13. Dừng Spring context và xác minh graceful shutdown.
14. Kiểm tra metric, lag và log để xác nhận processor hoạt động ổn định.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Factory bean ownership | Binder hoặc Spring Kafka quản lý đúng một lifecycle cho processor |
| Topology | Được khai báo trước khi runtime start |
| Application ID | Ổn định và không xung đột |
| Client properties | Broker, Serde, guarantee và security đúng |
| Function configuration | Processor-specific properties không ảnh hưởng processor khác |
| Customizer | Được gọi trước khi factory bean start |
| State listener | Ghi nhận transition và lỗi |
| State directory | Riêng cho từng instance, đủ dung lượng |
| Shutdown | Close timeout và termination grace period phù hợp |
| Integration test | Có xử lý input, output, restore và stop thực tế |

## Kết luận

StreamsBuilderFactoryBean kết nối topology Kafka Streams với lifecycle của Spring. StreamsBuilder định nghĩa luồng xử lý; KafkaStreams thực thi topology và quản lý consumer, producer, state, rebalance; factory bean tạo runtime, khởi động và dừng nó theo vòng đời ứng dụng.

Với Spring Cloud Stream Kafka Streams binder, hãy để binder quản lý factory bean và cấu hình client bằng prefix kafka.streams.binder hoặc function-specific configuration. Khi cần tùy chỉnh lifecycle, dùng StreamsBuilderFactoryBeanConfigurer và KafkaStreamsCustomizer; lọc theo application ID khi có nhiều processor. Theo dõi state và restore, cấp state.dir riêng, cấu hình security/processing guarantee đúng và kiểm thử graceful shutdown trên Kafka broker thực tế.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0.4 – StreamsBuilderFactoryBean configurer](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/streamsbuilderfactorybean-customizer.html)
- [Spring Cloud Stream 5.0.4 – Kafka Streams binder configuration options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring for Apache Kafka 4.2 – Apache Kafka Streams Support](https://docs.spring.io/spring-kafka/reference/streams.html)
- [Apache Kafka – StreamsConfig API](https://kafka.apache.org/documentation/#streamsconfigs)
- [Apache Kafka Streams – Developer Guide](https://kafka.apache.org/documentation/streams/)

