# KafkaAdmin và quản lý tài nguyên Kafka

Trong kiến trúc Spring Kafka, ứng dụng không chỉ gửi và nhận record. Nó còn cần những tài nguyên Kafka phù hợp để luồng sự kiện hoạt động: topic, partition, replication, retention, cleanup policy và quyền truy cập. **KafkaAdmin** là thành phần Spring Kafka giúp khai báo và tạo topic từ cấu hình ứng dụng; **AdminClient** là API quản trị của Apache Kafka để thực hiện các thao tác quản trị chi tiết hơn.

Bài học này đặt KafkaAdmin vào đúng vai trò trong module **SPRING_KAFKA_MESSAGING**: hỗ trợ xây dựng ứng dụng gửi nhận sự kiện bằng KafkaTemplate và @KafkaListener, đồng thời quản lý topic và cấu hình để các luồng messaging có thể mở rộng, phục hồi và vận hành tin cậy. Các ví dụ tập trung vào topic vì đây là tài nguyên mà ứng dụng Spring Kafka thường cần khai báo trực tiếp.

## Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích KafkaAdmin, KafkaAdmin bean, NewTopic, TopicBuilder và mối quan hệ với AdminClient.
- Khai báo topic bằng Spring configuration và hiểu thời điểm topic được tạo.
- Chọn số partition, replication factor và topic configuration theo yêu cầu xử lý.
- Phân biệt tạo topic mới với thay đổi cấu hình của topic đã tồn tại.
- Dùng AdminClient để liệt kê, mô tả và quản lý topic trong một tác vụ quản trị.
- Thiết kế cách quản lý tài nguyên khác nhau giữa local, test, staging và production.
- Kiểm thử việc tạo topic, xử lý topic đã tồn tại và phát hiện cấu hình sai.
- Vận hành topic an toàn thông qua ACL, giám sát, quy trình thay đổi và chính sách vòng đời dữ liệu.

## 1. Vì sao ứng dụng cần quản lý tài nguyên Kafka?

Kafka lưu record trong topic. Producer gửi record đến topic; consumer group đọc các partition của topic theo offset. Nếu topic chưa tồn tại, có quá ít partition, replication không phù hợp hoặc retention sai, ứng dụng có thể không đáp ứng được yêu cầu về tải, thứ tự, độ bền và lưu trữ.

Một số tình huống thường gặp:

- Một luồng sự kiện mới như orders.created cần topic riêng để producer và các consumer group cùng sử dụng.
- Consumer cần nhiều partition để xử lý song song, nhưng topic hiện tại chỉ có một partition.
- Sự kiện cần được giữ trong bảy ngày để hỗ trợ xử lý lại và điều tra sự cố.
- Topic chứa trạng thái mới nhất theo key cần cleanup policy dạng compaction.
- Môi trường production cần replication và min.insync.replicas để tăng khả năng chịu lỗi.
- Ứng dụng cần kiểm tra topic đã tồn tại và phát hiện cấu hình thực tế khác với cấu hình mong muốn.

Có thể hình dung các thành phần như sau:

~~~mermaid
flowchart TD
    APP[Spring Boot application] --> KA[KafkaAdmin]
    CONF[NewTopic beans] --> KA
    KA --> AC[Kafka Admin API]
    AC --> CL[Kafka cluster]
    CL --> TOPIC[Topics and partitions]
    PRODUCER[KafkaTemplate] --> TOPIC
    TOPIC --> CONSUMER["@KafkaListener"]
    OPS[AdminClient / Operations job] --> AC
~~~

KafkaAdmin quản lý topic được khai báo trong Spring context. KafkaTemplate và @KafkaListener sử dụng các topic đó để trao đổi record. AdminClient cung cấp thao tác quản trị chi tiết khi ứng dụng hoặc quy trình vận hành cần truy vấn hay thay đổi tài nguyên theo yêu cầu. Trong production, nên chủ động provision topic để tránh topic tự sinh với partition và cấu hình mặc định không phù hợp khi broker cho phép auto-create.

Điểm cần nhớ là KafkaAdmin không phải Kafka broker và cũng không lưu record. Nó gửi yêu cầu quản trị tới cluster thông qua Kafka Admin API.

## 2. Phân biệt KafkaAdmin và AdminClient

Hai thành phần có liên quan nhưng phục vụ hai kiểu công việc khác nhau.

| Thành phần | Vai trò | Cách sử dụng điển hình |
|---|---|---|
| KafkaAdmin | Tích hợp quản trị topic vào Spring application context | Khai báo NewTopic bean để topic được tạo khi ứng dụng khởi tạo. |
| AdminClient | API quản trị cấp thấp của Apache Kafka | Liệt kê, mô tả, tạo, xóa topic; đọc hoặc thay đổi cấu hình và thực hiện các thao tác quản trị được broker hỗ trợ. |
| KafkaTemplate | Gửi record tới topic | Producer phát OrderCreatedEvent hoặc sự kiện nghiệp vụ khác. |
| @KafkaListener | Nhận record từ topic | Consumer xử lý sự kiện theo consumer group. |

Với Spring Boot và dependency spring-kafka, Spring Boot thường cấu hình KafkaAdmin dựa trên thuộc tính Kafka của ứng dụng. Khi ứng dụng khai báo bean NewTopic, KafkaAdmin sử dụng bean đó để gửi yêu cầu tạo topic tới cluster.

Nếu cần một tác vụ quản trị động, chẳng hạn kiểm tra một danh sách topic do hệ thống quản lý hoặc tạo topic theo một yêu cầu được phê duyệt, AdminClient cho phép gọi trực tiếp các API quản trị. Không nên tạo một AdminClient mới cho từng request nghiệp vụ; đây là client cần được quản lý vòng đời, đóng đúng cách và thường được dùng như một thành phần dùng chung trong tác vụ quản trị.

## 3. Cấu hình kết nối quản trị

KafkaAdmin cần biết địa chỉ bootstrap server và các thông tin bảo mật cần thiết để kết nối cluster. Trong Spring Boot, cấu hình cơ bản thường nằm trong application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

Khi dùng Spring Boot auto-configuration, thuộc tính bootstrap-servers được dùng để cấu hình các thành phần Kafka, bao gồm KafkaAdmin. Nếu ứng dụng cần cấu hình riêng cho kết nối quản trị, có thể khai báo KafkaAdmin bean với map cấu hình riêng.

Ví dụ cấu hình thủ công:

~~~java
@Configuration
public class KafkaAdminConfiguration {

    @Bean
    KafkaAdmin kafkaAdmin() {
        Map<String, Object> configs = new HashMap<>();
        configs.put(
                AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092"
        );
        return new KafkaAdmin(configs);
    }
}
~~~

Đoạn code trên minh họa cách tạo KafkaAdmin khi ứng dụng cần tự quản lý cấu hình admin. Trong ứng dụng Spring Boot đã có KafkaAdmin auto-configured, không nên khai báo thêm bean trùng lặp nếu không có nhu cầu thay thế hoặc tùy chỉnh rõ ràng.

Với cluster bảo vệ bằng SASL hoặc TLS, admin client cũng cần cấu hình security protocol, cơ chế xác thực, truststore và các thuộc tính liên quan theo hạ tầng. Quyền quản trị phải được cấp qua ACL hoặc cơ chế phân quyền tương ứng. Một ứng dụng chỉ gửi và nhận record thường không cần toàn bộ quyền quản trị cluster.

Một số nguyên tắc cấu hình:

- Dùng biến môi trường hoặc secret manager cho thông tin xác thực; không commit mật khẩu hoặc private key vào repository.
- Tách cấu hình theo môi trường và tránh dùng địa chỉ broker local trong production.
- Cấp đúng quyền cần thiết cho tài khoản quản trị topic.
- Đặt timeout hợp lý cho thao tác quản trị và xử lý lỗi kết nối.
- Xác định rõ ứng dụng có được phép tiếp tục khởi động khi broker tạm thời chưa sẵn sàng hay không.

## 4. Khai báo topic bằng NewTopic và TopicBuilder

Cách phổ biến nhất để tích hợp tạo topic với Spring Kafka là khai báo một bean NewTopic. NewTopic là mô hình mô tả topic cần có; TopicBuilder giúp tạo mô hình này dễ đọc hơn.

Ví dụ một topic sự kiện đơn hàng:

~~~java
@Configuration
public class KafkaTopicConfiguration {

    @Bean
    NewTopic ordersCreatedTopic() {
        return TopicBuilder.name("orders.created")
                .partitions(6)
                .replicas(3)
                .build();
    }
}
~~~

Khi Spring context khởi tạo, KafkaAdmin phát hiện NewTopic bean và yêu cầu Kafka tạo topic nếu topic đó chưa tồn tại. Với cấu hình trên, topic có sáu partition và replication factor bằng ba. Cluster phải có đủ broker phù hợp để đáp ứng replication factor.

Đối với Kafka chạy trên máy cá nhân chỉ có một broker, hãy dùng replicas(1). Không dùng cấu hình ba replica trên cluster một broker vì broker không thể đáp ứng yêu cầu đó.

Có thể cấu hình thêm các thuộc tính của topic:

~~~java
@Bean
NewTopic ordersCreatedTopic() {
    return TopicBuilder.name("orders.created")
            .partitions(6)
            .replicas(3)
            .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
            .config(TopicConfig.MIN_IN_SYNC_REPLICAS_CONFIG, "2")
            .build();
}
~~~

Đây là một ví dụ cấu hình khác cho topic orders.created, minh họa thời gian retention bảy ngày và min.insync.replicas bằng hai; trong một class cấu hình, hãy dùng một định nghĩa bean cho mỗi topic. Đây là cấu hình minh họa cho cluster có replication factor ba và producer dùng acknowledgement phù hợp, chẳng hạn acks=all. Giá trị thực tế cần dựa trên yêu cầu mất dữ liệu cho phép, số broker, dung lượng lưu trữ và lưu lượng record.

TopicBuilder còn hỗ trợ cách khai báo cleanup policy dạng compaction:

~~~java
@Bean
NewTopic customerStateTopic() {
    return TopicBuilder.name("customer.state")
            .partitions(6)
            .replicas(3)
            .compact()
            .build();
}
~~~

Compaction giữ lại giá trị mới nhất theo key trong log theo cơ chế compact bất đồng bộ của Kafka; record cũ không nhất thiết biến mất ngay khi record mới được ghi. Nó phù hợp với topic biểu diễn trạng thái hiện tại theo key, ví dụ trạng thái cấu hình hoặc trạng thái khách hàng. Producer cần gửi key ổn định; record có value null có thể được dùng như tombstone để đánh dấu key cần xóa theo quy tắc compaction và thời gian lưu tombstone được cấu hình.

Các cấu hình topic thường gặp:

| Cấu hình | Mục đích | Điều cần cân nhắc |
|---|---|---|
| retention.ms | Thời gian giữ record theo chính sách retention | Phù hợp với nhu cầu lưu trữ, replay và dung lượng. |
| retention.bytes | Giới hạn dung lượng log theo partition | Cần tính tổng dung lượng trên tất cả partition và replica. |
| cleanup.policy | Chọn delete, compact hoặc kết hợp theo phiên bản/cấu hình broker | Compaction cần key và mô hình dữ liệu phù hợp. |
| min.insync.replicas | Số replica tối thiểu phải ở trạng thái ISR để đáp ứng ghi với acks=all | Phải tương thích với replication factor và yêu cầu sẵn sàng. |
| segment.bytes | Kích thước segment log | Ảnh hưởng tới việc quản lý segment và retention. |
| max.message.bytes | Giới hạn kích thước record batch được chấp nhận ở topic | Cần tương thích với producer, broker và consumer. |

Không nên thêm mọi thuộc tính vào từng topic theo thói quen. Hãy xác định yêu cầu dữ liệu, khả năng phục hồi và chi phí lưu trữ trước khi chọn cấu hình.

## 5. Chọn partition và replication factor

Partition và replication factor quyết định nhiều đặc tính quan trọng của topic.

**Partition** chia topic thành các log độc lập, tạo khả năng xử lý song song. Một consumer group có thể có tối đa số consumer đang được gán bằng số partition của topic đó. Nếu topic có sáu partition, group không thể sử dụng hiệu quả mười consumer để đọc riêng topic này cùng lúc.

Số partition cần được chọn dựa trên:

- Lưu lượng record dự kiến và tốc độ xử lý của mỗi consumer.
- Mức concurrency cần thiết của consumer group.
- Yêu cầu giữ thứ tự theo key.
- Chi phí quản lý partition, file log, metadata và tài nguyên broker.
- Kế hoạch tăng trưởng tải trong tương lai.

Không nên chọn số partition quá thấp khiến hệ thống khó mở rộng, nhưng cũng không nên tạo quá nhiều partition khi chưa có nhu cầu. Mỗi partition tạo thêm công việc cho broker, controller, consumer và hệ thống giám sát.

**Replication factor** là số bản sao của mỗi partition trên các broker. Replication giúp topic tiếp tục phục vụ khi một broker gặp sự cố, trong giới hạn replica còn khả dụng và chính sách ISR.

Ví dụ cluster có ba broker và topic có replication factor ba:

~~~mermaid
flowchart LR
    P0[Partition 0] --> B1[Broker 1: Leader]
    P0 --> B2[Broker 2: Follower]
    P0 --> B3[Broker 3: Follower]
~~~

Trong thực tế, các partition khác có thể phân bố leader và replica khác nhau để cân bằng tải. Kafka quản lý ISR (in-sync replicas), tức tập replica theo kịp leader theo các điều kiện của cluster.

Khi kết hợp replication factor ba, min.insync.replicas hai và producer acks=all, một lần ghi chỉ được xác nhận khi điều kiện ISR phù hợp được đáp ứng. Nếu ISR giảm dưới ngưỡng, producer có thể nhận lỗi thay vì ghi với mức bảo vệ thấp hơn. Đây là lựa chọn giữa tính sẵn sàng ghi và mức độ bền dữ liệu.

Một lưu ý quan trọng: tăng số partition của topic hiện có không thể hoàn tác bằng cách giảm số partition. Việc tăng partition cũng có thể làm thay đổi kết quả định tuyến key theo partitioner mặc định, vì phép tính phân vùng phụ thuộc số partition. Nếu thứ tự của các sự kiện cùng key là yêu cầu nghiệp vụ, hãy lập kế hoạch thay đổi partition cẩn thận.

## 6. Vòng đời topic khi Spring application khởi động

Một luồng khởi tạo điển hình:

1. Spring Boot đọc cấu hình Kafka và tạo các bean cần thiết.
2. Các class cấu hình khai báo NewTopic bean.
3. KafkaAdmin phát hiện các topic được khai báo.
4. KafkaAdmin kết nối broker qua Admin API và gửi yêu cầu tạo topic.
5. Kafka broker kiểm tra tên topic, partition, replication và cấu hình.
6. Topic sẵn sàng để producer và consumer sử dụng khi broker hoàn tất thao tác.

~~~mermaid
sequenceDiagram
    participant App as Spring Application
    participant KA as KafkaAdmin
    participant Broker as Kafka Broker
    participant Producer as KafkaTemplate
    participant Consumer as Listener Container
    App->>KA: Khởi tạo context và NewTopic beans
    KA->>Broker: CreateTopics
    Broker-->>KA: Kết quả tạo topic
    KA-->>App: Hoàn tất khởi tạo admin
    Producer->>Broker: Gửi record
    Broker-->>Producer: Send result
    Consumer->>Broker: Poll record
    Broker-->>Consumer: Records
~~~

Tạo topic ở giai đoạn khởi động giúp cấu hình tài nguyên được đặt cạnh cấu hình ứng dụng. Cách này thuận tiện trong local, integration test và các dịch vụ nhỏ có quyền sở hữu topic rõ ràng.

Tuy nhiên, cần thiết kế hành vi khi broker không sẵn sàng. Ứng dụng có thể cần fail fast nếu không thể chạy mà thiếu Kafka; một ứng dụng khác có thể cần khởi động để phục vụ các chức năng không phụ thuộc Kafka và kết nối lại sau. Spring Kafka cung cấp tùy chọn cấu hình hành vi KafkaAdmin khi broker không khả dụng, chẳng hạn thuộc tính fatalIfBrokerNotAvailable. Hãy chọn hành vi dựa trên yêu cầu khởi động và readiness của service.

Không nên giả định rằng chỉ cần context khởi động thành công là mọi topic đã được tạo đúng như mong muốn. Hãy ghi log kết quả quản trị, kiểm tra topic trong môi trường triển khai và có health/readiness phù hợp với kiến trúc của ứng dụng.

## 7. Topic đã tồn tại và thay đổi cấu hình

Tạo mới và thay đổi một topic đã tồn tại là hai tình huống khác nhau.

Khi topic chưa tồn tại, KafkaAdmin có thể tạo topic theo NewTopic bean. Khi topic đã tồn tại, ứng dụng cần xác minh cấu hình thực tế và quyết định có được phép thay đổi hay không. Hành vi cụ thể của KafkaAdmin đối với partition và topic configs phụ thuộc phiên bản Spring Kafka cùng các tùy chọn quản trị được bật.

Một số nguyên tắc cần nhớ:

- Kafka không hỗ trợ giảm số partition của một topic hiện có.
- Tăng partition cần được xem là thay đổi kiến trúc vì có thể ảnh hưởng phân vùng theo key.
- Topic config có thể được thay đổi bằng Admin API nếu broker và quyền truy cập cho phép.
- Thay đổi retention hoặc cleanup policy có thể làm thay đổi cách dữ liệu được giữ và xóa.
- Thay đổi replication factor thường liên quan tới phân bổ replica và quy trình reassignment, không chỉ là đổi một con số trong bean.
- Không để nhiều ứng dụng cùng tự ý quản lý cấu hình của một topic nếu chưa xác định rõ ownership.

Với Spring Kafka, có các tùy chọn của KafkaAdmin để kiểm soát việc sửa topic config hiện có. Trước khi bật hành vi sửa cấu hình, cần đọc tài liệu đúng phiên bản đang dùng và hiểu chính xác thuộc tính nào sẽ được thay đổi. Một thay đổi ngoài dự kiến có thể tác động tới consumer group hoặc chính sách lưu trữ.

Nên quản lý thay đổi topic như một migration:

1. Ghi nhận cấu hình hiện tại của topic.
2. Xác định cấu hình đích và lý do thay đổi.
3. Đánh giá ảnh hưởng tới partition, key ordering, retention, replication và consumer.
4. Thử nghiệm trên staging với dữ liệu đại diện.
5. Thực hiện thay đổi qua tài khoản có quyền phù hợp.
6. Đọc lại cấu hình sau thay đổi và theo dõi metric.
7. Cập nhật tài liệu vận hành và ownership.

## 8. Dùng AdminClient cho tác vụ quản trị chủ động

Khi cần thao tác ngoài vòng đời Spring context, có thể sử dụng AdminClient. AdminClient là API của Apache Kafka; nó hỗ trợ các thao tác như liệt kê topic, mô tả topic, tạo hoặc xóa topic, đọc và thay đổi cấu hình theo quyền và phiên bản broker.

Ví dụ một tác vụ quản trị tạo topic và đọc thông tin mô tả:

~~~java
public void ensureAuditTopic(
        String bootstrapServers) throws Exception {

    Map<String, Object> configs = new HashMap<>();
    configs.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
    );

    NewTopic topic = new NewTopic(
            "audit.events",
            3,
            (short) 1
    );

    try (AdminClient admin = AdminClient.create(configs)) {
        admin.createTopics(List.of(topic))
                .all()
                .get(10, TimeUnit.SECONDS);

        Map<String, TopicDescription> descriptions =
                admin.describeTopics(List.of("audit.events"))
                        .all()
                        .get(10, TimeUnit.SECONDS);

        TopicDescription description =
                descriptions.get("audit.events");

        System.out.println(
                "Topic=" + description.name()
                + ", partitions=" + description.partitions().size()
        );
    }
}
~~~

Ví dụ này phù hợp để minh họa một tác vụ độc lập. Trong ứng dụng thực tế, cần xử lý riêng trường hợp topic đã tồn tại, timeout, lỗi xác thực và lỗi broker. Không nên xem TopicExistsException là lỗi nghiêm trọng nếu mục tiêu là bảo đảm topic đã có mặt; hãy kiểm tra trạng thái hiện tại và xác minh cấu hình.

AdminClient trả kết quả theo cơ chế bất đồng bộ thông qua KafkaFuture. Gọi get với timeout giúp tác vụ quản trị có giới hạn thời gian chờ. Nếu thao tác nằm trong luồng vận hành dài, cần ghi nhận lỗi, retry có giới hạn và tránh gửi lặp một thay đổi không idempotent.

Một số thao tác AdminClient thường gặp:

| Nhu cầu | Nhóm API |
|---|---|
| Liệt kê topic | listTopics |
| Đọc partition, leader, replica và ISR | describeTopics |
| Tạo topic | createTopics |
| Xóa topic | deleteTopics |
| Đọc cấu hình topic hoặc broker | describeConfigs |
| Thay đổi cấu hình | alterConfigs hoặc incrementalAlterConfigs tùy API và phiên bản |
| Tăng số partition | createPartitions |
| Quản lý ACL | describeAcls, createAcls, deleteAcls |
| Theo dõi consumer group | describeConsumerGroups, listConsumerGroups |

Tên API và kiểu dữ liệu có thể thay đổi theo phiên bản Kafka client. Khi viết code, cần dùng đúng phiên bản kafka-clients được Spring Boot dependency management chọn và kiểm tra tài liệu tương ứng.

Xóa topic là thao tác có thể làm mất dữ liệu và ảnh hưởng tới producer, consumer đang sử dụng topic. Chỉ thực hiện qua quy trình quản trị có kiểm soát, xác nhận đúng môi trường, tên topic và ownership.

## 9. Quản lý topic theo môi trường

Một topic có thể cần cấu hình khác nhau ở local, test, staging và production. Ví dụ local dùng một broker, ít partition và một replica; production dùng nhiều broker, nhiều partition, replication factor cao hơn và retention phù hợp với dung lượng thực tế.

Có thể dùng Spring profiles hoặc biến môi trường để tách cấu hình. Ví dụ:

~~~yaml
spring:
  config:
    activate:
      on-profile: local

  kafka:
    bootstrap-servers: localhost:9092
~~~

Ví dụ trên chỉ thể hiện cách chọn profile cho cấu hình local. Trong dự án thực tế, các giá trị partition, replica và retention có thể được đưa vào cấu hình riêng hoặc được cung cấp từ hạ tầng triển khai. Không nên nhân bản nguyên một cấu hình production vào local nếu môi trường local không có đủ broker.

Một cách tổ chức thường gặp:

| Môi trường | Partition | Replication | Mục tiêu |
|---|---:|---:|---|
| Local | 1-3 | 1 | Phát triển nhanh, dễ dựng môi trường. |
| Integration test | Theo kịch bản test | 1 hoặc theo broker test | Kiểm tra hành vi producer, consumer và admin. |
| Staging | Gần production | Gần production | Kiểm chứng cấu hình và tải trước triển khai. |
| Production | Theo tải và mức song song | Theo yêu cầu sẵn sàng | Vận hành ổn định, có khả năng phục hồi. |

Các con số trong bảng là gợi ý để định hướng, không phải giá trị mặc định cho mọi hệ thống.

Đối với hệ thống lớn, nên quản lý topic bằng quy trình hạ tầng hoặc migration chuyên biệt. Ứng dụng nghiệp vụ có thể chỉ cần quyền đọc/ghi; một deployment job hoặc tài khoản quản trị riêng chịu trách nhiệm tạo và thay đổi topic. Cách này giúp tránh nhiều replica của service cùng thực hiện các thay đổi quản trị không cần thiết.

## 10. Quyền truy cập và bảo mật khi quản lý tài nguyên

Quản trị topic cần quyền cao hơn gửi và nhận record. Trong cluster có ACL, các thao tác có thể cần quyền CREATE, DESCRIBE, ALTER hoặc DELETE tùy công việc. Tài khoản consumer và producer chỉ nên có quyền cần thiết trên các topic và consumer group liên quan.

Nên phân tách vai trò:

- **Ứng dụng producer:** quyền ghi vào topic được giao.
- **Ứng dụng consumer:** quyền đọc topic và sử dụng consumer group tương ứng.
- **Tác vụ quản trị:** quyền tạo hoặc thay đổi topic theo phạm vi được phê duyệt.
- **Tác vụ giám sát:** quyền đọc metadata và metric cần thiết.

Không nên cấp quyền quản trị toàn cluster cho mọi service chỉ vì KafkaAdmin cần tạo topic lúc khởi động. Có thể tách tác vụ provisioning khỏi runtime service, hoặc cấu hình quyền riêng theo môi trường và ownership.

Với SASL/TLS, cần bảo vệ thông tin xác thực, giới hạn quyền đọc secret, xoay vòng credential và kiểm tra log để tránh ghi ra mật khẩu hoặc payload nhạy cảm. Khi chạy AdminClient trong ứng dụng, hãy chắc chắn client sử dụng đúng security configuration của cluster đích.

## 11. Kiểm thử KafkaAdmin và tài nguyên topic

Kiểm thử quản trị topic nên xác minh hành vi thật của broker, không chỉ kiểm tra rằng bean NewTopic được tạo trong Spring context.

Các lớp kiểm thử có thể gồm:

| Loại kiểm thử | Điều cần xác minh |
|---|---|
| Unit test cấu hình | Tên topic, số partition, replication factor và config được khai báo đúng. |
| Integration test | KafkaAdmin tạo được topic trên broker test. |
| Existing-topic test | Khởi động lại ứng dụng không làm hỏng topic đã tồn tại. |
| AdminClient test | Có thể mô tả topic và đọc partition/replica/ISR. |
| Permission test | Tài khoản thiếu quyền nhận lỗi phù hợp; tài khoản đúng quyền thực hiện được thao tác. |
| Failure test | Broker không sẵn sàng hoặc timeout được xử lý theo chính sách. |

Có thể dùng EmbeddedKafka hoặc Testcontainers để chạy broker trong kiểm thử. Testcontainers hữu ích khi cần môi trường gần với Kafka broker thực tế hơn. Khi dùng EmbeddedKafka, hãy bảo đảm topic test và consumer group được cô lập giữa các test để tránh kết quả phụ thuộc thứ tự chạy.

Một ví dụ kiểm thử có thể xác minh topic đã được tạo bằng AdminClient:

~~~java
@Test
void shouldCreateOrdersTopic() throws Exception {
    try (AdminClient admin = AdminClient.create(adminConfigs)) {
        Set<String> topics = admin.listTopics()
                .names()
                .get(10, TimeUnit.SECONDS);

        assertThat(topics).contains("orders.created");

        Map<String, TopicDescription> descriptions =
                admin.describeTopics(List.of("orders.created"))
                        .all()
                        .get(10, TimeUnit.SECONDS);

        assertThat(
                descriptions.get("orders.created").partitions()
        ).hasSize(6);
    }
}
~~~

Đây là ví dụ minh họa; adminConfigs và broker phải được cung cấp từ test context. Nếu bài test chạy song song, hãy dùng tên topic duy nhất hoặc cơ chế cô lập tài nguyên phù hợp.

Không nên để test tự động xóa topic dùng chung hoặc topic có dữ liệu cần giữ. Mỗi test cần có chiến lược tạo và dọn tài nguyên rõ ràng.

## 12. Giám sát và xử lý sự cố quản trị

Sau khi tạo topic, vẫn cần theo dõi trạng thái cluster và tài nguyên. Một số chỉ số cần quan sát:

- Số topic và số partition trên mỗi broker.
- Số offline partition và under-replicated partition.
- Số replica trong ISR và hiện tượng ISR shrink.
- Leader distribution và tải giữa các broker.
- Dung lượng log, tốc độ tăng dữ liệu và mức sử dụng disk.
- Tỷ lệ request lỗi hoặc timeout của AdminClient.
- Consumer lag trên các group sử dụng topic.
- Tình trạng retention và compaction theo mục tiêu dữ liệu.

Một số tình huống thường gặp:

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tạo được topic | Broker không truy cập được, thiếu quyền CREATE, replication factor vượt số broker | Kiểm tra kết nối, ACL, số broker và lỗi Admin API. |
| Topic tồn tại nhưng cấu hình khác | Topic được tạo trước đó hoặc thay đổi ngoài ứng dụng | Describe topic và config thực tế; đối chiếu với cấu hình đích. |
| Producer nhận NotEnoughReplicas | ISR thấp hơn min.insync.replicas khi dùng acks phù hợp | Kiểm tra broker, replica lag và ISR. |
| Consumer xử lý không song song như dự kiến | Partition ít hơn consumer hoặc partition assignment chưa như mong muốn | Kiểm tra partition count, consumer group và rebalance. |
| Dung lượng tăng nhanh | Retention dài, lưu lượng tăng, replica nhiều hoặc compaction chưa theo kịp | Kiểm tra log size, retention, segment và disk. |
| Thay đổi config không có hiệu lực | KafkaAdmin chưa được cấu hình để sửa config hiện có hoặc thay đổi không được broker hỗ trợ | Kiểm tra phiên bản, tùy chọn modify và kết quả Admin API. |

Khi xử lý sự cố, hãy lấy trạng thái thực tế từ broker. Không nên suy luận rằng topic có cấu hình đúng chỉ vì mã nguồn chứa một NewTopic bean.

## 13. Bài tập tổng hợp: quản lý topic cho hệ thống đơn hàng

Hãy xây dựng một cấu hình topic cho luồng sự kiện đơn hàng gồm:

- orders.created: sự kiện đơn hàng vừa được tạo.
- inventory.reserved: kết quả giữ hàng.
- payment.authorized: kết quả xác nhận thanh toán.
- orders.failed: sự kiện nghiệp vụ cần xử lý tiếp hoặc đối soát.

Yêu cầu thực hành:

1. Khai báo NewTopic bean cho các topic bằng TopicBuilder.
2. Chọn partition và replication factor theo môi trường local và production.
3. Cấu hình retention cho event topic; giải thích vì sao retention cần phù hợp với thời gian replay và dung lượng.
4. Thử cleanup policy compact cho một topic trạng thái theo key và so sánh với delete.
5. Khởi động lại ứng dụng để xác minh KafkaAdmin xử lý topic đã tồn tại.
6. Dùng AdminClient đọc mô tả topic, partition, replica và ISR.
7. Tạo một tình huống thiếu quyền quản trị để quan sát lỗi ACL.
8. Viết integration test xác minh topic tồn tại và có đúng số partition.
9. Ghi lại quy trình thay đổi partition hoặc retention mà không gây gián đoạn ngoài dự kiến.
10. Kết nối KafkaTemplate và @KafkaListener vào các topic để kiểm tra luồng sự kiện hoàn chỉnh.

Khi hoàn thành, hãy có một bảng tài nguyên ghi rõ tên topic, owner, producer, consumer group, key, số partition, replication factor, retention, cleanup policy và người chịu trách nhiệm vận hành.

## 14. Thứ tự học và tiêu chí hoàn thành

| Chặng | Nội dung | Tiêu chí tự kiểm tra |
|---|---|---|
| 1. Vai trò quản trị | KafkaAdmin và AdminClient | Giải thích được sự khác nhau giữa quản lý khai báo lúc khởi động và quản trị chủ động. |
| 2. Cấu hình kết nối | bootstrap servers, security, ACL | KafkaAdmin kết nối được đúng cluster bằng credential phù hợp. |
| 3. Khai báo topic | NewTopic, TopicBuilder | Ứng dụng tạo được topic theo cấu hình. |
| 4. Thiết kế tài nguyên | partition, replication, retention, compaction | Giải thích được ảnh hưởng của từng thuộc tính tới tải và độ bền dữ liệu. |
| 5. Vòng đời topic | create, describe, alter, delete | Phân biệt được tạo mới, kiểm tra và thay đổi topic hiện có. |
| 6. Tự động hóa | profiles, migration, ownership | Mỗi môi trường có cấu hình rõ ràng và thay đổi được kiểm soát. |
| 7. Testing | EmbeddedKafka, Testcontainers, AdminClient | Có kiểm thử cho topic mới, topic tồn tại và lỗi quản trị. |
| 8. Operations | ACL, metrics, ISR, disk, consumer lag | Có thể kiểm tra trạng thái topic và chẩn đoán lỗi phổ biến. |

Bài học hoàn thành khi bạn có thể khai báo topic bằng KafkaAdmin, giải thích cách topic được tạo trong vòng đời Spring, dùng AdminClient để kiểm tra trạng thái broker, chọn partition/replication/retention có căn cứ và xây dựng quy trình thay đổi tài nguyên an toàn.

KafkaAdmin giúp đưa việc khai báo topic vào cấu hình Spring Kafka; AdminClient mở rộng khả năng quản trị khi cần thao tác chủ động. Độ tin cậy của messaging còn phụ thuộc vào cách thiết kế partition, replica, retention, quyền truy cập, kiểm thử và giám sát. Nắm vững các phần này giúp producer và consumer làm việc trên một nền tài nguyên có thể dự đoán và vận hành được.

