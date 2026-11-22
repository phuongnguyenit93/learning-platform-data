# missingTopicsFatal

Trong Spring Kafka, **missingTopicsFatal** là thuộc tính của listener container dùng để quyết định container có được phép khởi động khi một hoặc nhiều topic được khai báo rõ ràng cho listener chưa tồn tại trên Kafka broker hay không. Khi bật thuộc tính này, container sẽ từ chối khởi động nếu kiểm tra phát hiện topic bắt buộc bị thiếu. Khi tắt, container có thể ghi cảnh báo và tiếp tục khởi động; consumer sau đó tiếp tục hoạt động theo cơ chế subscription và metadata của Kafka.

Thuộc tính này hữu ích khi ứng dụng phụ thuộc vào một tập topic phải có sẵn trước khi nhận traffic. Nó giúp phát hiện sớm lỗi triển khai như sai tên topic, quên tạo topic hoặc triển khai consumer trước hạ tầng Kafka. Tuy nhiên, missingTopicsFatal chỉ kiểm tra sự tồn tại của topic trong giai đoạn khởi động container. Nó không tự tạo topic, không kiểm tra đầy đủ cấu hình partition/replication, không thay thế ACL và không phải cơ chế giám sát liên tục khi topic bị xóa sau đó.

## 1. Vì sao listener container cần kiểm tra topic?

Một listener container cần biết topic nào sẽ được subscribe. Với khai báo topic tường minh, ứng dụng thường mong đợi các topic đã được provision trước:

~~~java
@KafkaListener(topics = "orders.created", groupId = "billing-service")
public void handle(OrderCreated event) {
    billingService.process(event);
}
~~~

Nếu topic orders.created chưa tồn tại, ứng dụng có thể gặp nhiều tình huống:

- Tên topic trong cấu hình bị viết sai.
- Hạ tầng chưa tạo topic trước khi deploy consumer.
- Consumer khởi động sớm hơn quy trình provisioning.
- Topic bị xóa nhầm hoặc chưa được tạo ở cluster mà ứng dụng đang kết nối.
- Ứng dụng trỏ nhầm môi trường hoặc cluster.

Nếu không có kiểm tra startup, consumer có thể khởi động và tiếp tục chờ metadata/topic theo cơ chế Kafka. Điều này đôi khi là hành vi mong muốn trong môi trường topic được tạo sau, nhưng cũng có thể khiến lỗi cấu hình chỉ được phát hiện khi hệ thống đã chạy.

missingTopicsFatal cho phép chọn hành vi startup phù hợp với yêu cầu của ứng dụng:

| Cấu hình | Hành vi khi topic được khai báo nhưng chưa tồn tại |
|---|---|
| false | Container có thể ghi cảnh báo và tiếp tục khởi động; consumer chờ topic/metadata theo cơ chế Kafka |
| true | Container báo lỗi và không khởi động nếu kiểm tra xác định topic bắt buộc bị thiếu |

Trong nhiều phiên bản Spring Kafka, mặc định của thuộc tính này là false; mặc định đã thay đổi từ Spring Kafka 2.3. Với dự án dùng phiên bản cũ hoặc có cấu hình riêng, hãy xác nhận Javadoc và cấu hình thực tế thay vì dựa vào mặc định của một phiên bản khác.

## 2. missingTopicsFatal hoạt động ở thời điểm nào?

Thuộc tính được dùng trong quá trình khởi động listener container, khi container kiểm tra các topic đã cấu hình. Với danh sách topic tường minh, container có thể hỏi broker về metadata/partition của topic để xác định topic có tồn tại hay không.

Luồng khái quát:

~~~
Spring khởi động listener container
             |
             v
Container kiểm tra topic đã khai báo
             |
       +-----+-----+
       |           |
   Topic tồn tại  Topic bị thiếu
       |           |
       v           v
    Subscribe    missingTopicsFatal?
    và chạy          |
                +---+---+
                |       |
               false   true
                |       |
                v       v
             Cảnh báo  Báo lỗi,
             và tiếp   container
             tục       không start
~~~

Đây là kiểm tra tại startup, không phải một bộ giám sát chạy liên tục. Nếu topic bị xóa sau khi container đã khởi động, missingTopicsFatal không tự động chạy lại như một health check. Consumer có thể nhận lỗi metadata, lỗi fetch hoặc các trạng thái khác từ Kafka client; ứng dụng cần quan sát log, metric và trạng thái container để phát hiện.

Nếu container được cấu hình autoStartup=false, việc kiểm tra gắn với thời điểm container thực sự được start. Việc bean đã được tạo hoặc Spring context đã hoàn tất khởi tạo không có nghĩa listener container đã kiểm tra topic.

Khi autoStartup=true, listener container thường được start trong lifecycle của Spring. Nếu missingTopicsFatal=true và topic bắt buộc không có, lỗi startup container có thể làm quá trình khởi động ứng dụng thất bại tùy cách listener registry/container được khởi động và cách ứng dụng quản lý lifecycle. Hãy xác minh hành vi này trong môi trường chạy thực tế, đặc biệt nếu ứng dụng có nhiều listener container với chính sách startup khác nhau.

## 3. Cấu hình trong Spring Kafka

Có thể đặt thuộc tính trực tiếp trên ContainerProperties của listener container factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
ordersListenerFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);

    factory.getContainerProperties().setMissingTopicsFatal(true);

    return factory;
}
~~~

Các listener sử dụng factory này sẽ kế thừa cấu hình missingTopicsFatal của container properties, trừ khi ứng dụng tạo và cấu hình container theo cách riêng.

Nếu muốn container tiếp tục khởi động trong khi topic có thể được tạo sau, có thể đặt false:

~~~java
factory.getContainerProperties().setMissingTopicsFatal(false);
~~~

Không nên đặt một giá trị duy nhất cho mọi listener nếu các topic có yêu cầu khác nhau. Một listener đọc topic nghiệp vụ bắt buộc có thể cần fail-fast; một listener đọc topic được tạo động theo tenant có thể cần chờ topic xuất hiện. Có thể dùng các container factory riêng để biểu đạt chính sách đó.

### 3.1. Cấu hình qua Spring Boot

Với Spring Boot, thuộc tính listener có thể được khai báo trong application.yml:

~~~yaml
spring:
  kafka:
    listener:
      missing-topics-fatal: true
~~~

Giá trị này áp dụng cho listener container được Boot auto-configure theo cấu hình tương ứng. Nếu ứng dụng tự tạo nhiều factory hoặc ghi đè ContainerProperties trong code, hãy kiểm tra factory thực tế mà từng @KafkaListener sử dụng.

Ví dụ listener chọn factory cụ thể:

~~~java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderCreated event) {
    billingService.process(event);
}
~~~

Nếu listener dùng một factory khác với factory được cấu hình missingTopicsFatal, giá trị ở factory mặc định có thể không áp dụng. Cần kiểm tra containerFactory trên annotation, registry và cấu hình bean.

Tên property của Spring Boot và khả năng bind phụ thuộc phiên bản Boot. Với dự án cũ, hãy kiểm tra configuration metadata của phiên bản đang dùng. Nếu property không được bind, cấu hình YAML có thể tồn tại mà không ảnh hưởng đến listener.

## 4. missingTopicsFatal không tạo topic

Một hiểu nhầm phổ biến là bật missingTopicsFatal sẽ làm Spring Kafka tạo topic nếu chưa tồn tại. Thuộc tính này chỉ quyết định cách container phản ứng với topic bị thiếu trong quá trình kiểm tra startup.

Nó không thay thế:

- KafkaAdmin.
- NewTopic bean.
- Quy trình tạo topic bằng Kafka CLI.
- Terraform, Helm hoặc công cụ quản lý hạ tầng.
- Chính sách auto.create.topics.enable ở broker.

Nếu topic phải có trước khi consumer chạy, hãy provision topic bằng quy trình hạ tầng rõ ràng rồi dùng missingTopicsFatal=true để phát hiện sai lệch.

### 4.1. Khai báo topic bằng NewTopic

Spring Kafka hỗ trợ khai báo topic qua NewTopic bean để KafkaAdmin có thể tạo topic khi ứng dụng khởi động:

~~~java
@Bean
NewTopic ordersCreatedTopic() {
    return TopicBuilder.name("orders.created")
            .partitions(6)
            .replicas(3)
            .build();
}
~~~

Ví dụ này yêu cầu broker cluster có đủ broker để đáp ứng replication factor 3. Trong môi trường local một broker, cần đặt replicas phù hợp với hạ tầng thử nghiệm.

KafkaAdmin sử dụng quyền quản trị topic để kiểm tra và tạo topic. Tài khoản chạy ứng dụng phải có quyền tương ứng nếu ứng dụng chịu trách nhiệm provisioning. Trong môi trường production, nhiều tổ chức tách quyền tạo topic khỏi quyền consume/produce; khi đó topic được tạo bởi pipeline hạ tầng và ứng dụng chỉ cần quyền sử dụng.

Nếu dựa vào NewTopic bean, cần bảo đảm quá trình tạo topic hoàn tất trước khi listener cần subscribe. Spring Boot và Spring Kafka có cơ chế tích hợp KafkaAdmin với lifecycle, nhưng thứ tự cụ thể còn phụ thuộc cách cấu hình context và container. Với quy trình triển khai nghiêm ngặt, provisioning topic ở bước deploy hạ tầng trước khi khởi động ứng dụng thường dễ kiểm soát hơn.

### 4.2. Auto-create topic ở broker

Kafka broker có thể được cấu hình cho phép tự tạo topic khi client truy cập topic chưa tồn tại. Cơ chế này tiện cho môi trường thử nghiệm nhưng có thể tạo topic với partition count, replication factor và retention không phù hợp với yêu cầu production.

Không nên dựa vào auto-create như cơ chế provisioning chính cho topic nghiệp vụ quan trọng. Nếu auto-create bật, một lần kiểm tra metadata có thể dẫn tới việc topic được tạo tùy theo broker/client behavior và quyền truy cập. Khi đó missingTopicsFatal có thể không phát hiện tình trạng topic chưa được provision đúng như mong đợi vì topic đã xuất hiện nhưng có cấu hình mặc định.

Tách hai trách nhiệm sẽ rõ ràng hơn:

1. Hạ tầng hoặc KafkaAdmin tạo topic với cấu hình mong muốn.
2. Listener container kiểm tra topic bắt buộc tồn tại trước khi start.
3. Monitoring xác nhận topic và partition vẫn hoạt động sau startup.

## 5. Topic tồn tại không có nghĩa topic đã sẵn sàng

missingTopicsFatal kiểm tra sự tồn tại của topic theo khả năng kiểm tra của container. Nó không phải validator đầy đủ cho topology Kafka.

Một topic có thể tồn tại nhưng vẫn không đáp ứng yêu cầu:

- Có ít partition hơn dự kiến.
- Replication factor thấp hơn chính sách durability.
- ISR không đủ hoặc một số replica offline.
- Retention hoặc cleanup policy sai.
- Message size limit không phù hợp payload.
- ACL không cho phép consumer đọc hoặc group commit offset.
- Topic tồn tại trên cluster khác với cluster mà ứng dụng cần dùng.

Ví dụ, listener mong đợi topic orders.created có 12 partition để xử lý song song, nhưng topic thực tế chỉ có 3 partition. missingTopicsFatal=false hay true đều không nhất thiết phát hiện sai lệch số partition nếu topic đã tồn tại.

Nếu yêu cầu startup phải xác nhận partition count, replication hoặc topic configuration, hãy thêm bước preflight dùng AdminClient hoặc kiểm tra trong pipeline provisioning. Tách rõ kiểm tra tồn tại của container và kiểm tra readiness của hạ tầng.

## 6. Topic tường minh và topicPattern

Spring Kafka hỗ trợ đăng ký listener bằng danh sách topic tường minh hoặc bằng regex pattern.

Topic tường minh:

~~~java
@KafkaListener(topics = {"orders.created", "orders.updated"})
public void handle(OrderEvent event) {
    service.process(event);
}
~~~

Topic pattern:

~~~java
@KafkaListener(topicPattern = "orders\\..*")
public void handle(OrderEvent event) {
    service.process(event);
}
~~~

Với danh sách topic tường minh, container biết chính xác tên topic cần kiểm tra. Với topicPattern, tập topic phù hợp có thể thay đổi theo thời gian và broker có thể phát hiện topic mới khớp pattern trong quá trình metadata refresh.

Không nên mặc định rằng missingTopicsFatal kiểm tra mọi topic mà regex có thể khớp như một danh sách tĩnh. Cách kiểm tra và hành vi khi pattern chưa khớp topic nào có thể phụ thuộc loại subscription và phiên bản Spring Kafka. Nếu ứng dụng cần bảo đảm ít nhất một topic tồn tại khi startup, hãy thực hiện preflight riêng bằng AdminClient và xác minh hành vi của phiên bản đang dùng.

Pattern subscription phù hợp với topic động, nhưng cần kiểm soát phạm vi regex để consumer không vô tình subscribe vào topic không liên quan. Khi dùng pattern, theo dõi danh sách topic thực tế được subscribe và quyền truy cập của principal.

## 7. Phân biệt topic bị thiếu với broker hoặc metadata không sẵn sàng

Không phải mọi lỗi khi container kiểm tra topic đều có nghĩa topic không tồn tại.

Các tình huống khác nhau:

| Tình huống | Dấu hiệu có thể gặp | Hướng điều tra |
|---|---|---|
| Topic thật sự chưa được tạo | Metadata không tìm thấy topic hoặc container báo missing topic | Kiểm tra tên topic và provisioning |
| Broker không kết nối được | Timeout, disconnect, bootstrap/metadata request thất bại | Kiểm tra DNS, network, broker listener và TLS |
| Authentication thất bại | SASL/SSL authentication exception | Kiểm tra credential, mechanism, truststore |
| Authorization thất bại | Topic/group authorization exception | Kiểm tra ACL và principal |
| Topic tồn tại nhưng chưa có leader | Leader unavailable hoặc metadata chưa ổn định | Kiểm tra partition state và broker |
| Topic tồn tại nhưng topology sai | Listener start được nhưng số partition/replication không đáp ứng yêu cầu | Kiểm tra bằng AdminClient hoặc công cụ quản trị |

Nếu broker đang khởi động hoặc metadata chưa sẵn sàng, việc kiểm tra topic có thể thất bại do lỗi kết nối thay vì kết luận chính xác topic không tồn tại. Hãy đọc exception gốc và log Kafka client trước khi thay đổi missingTopicsFatal.

Tắt missingTopicsFatal không chữa được broker mất kết nối, sai credential hoặc thiếu ACL. Nó chỉ thay đổi phản ứng với tình trạng topic bị thiếu trong kiểm tra startup.

## 8. Tác động đến startup và triển khai

Chọn missingTopicsFatal là quyết định giữa fail-fast và cho phép listener chờ topic xuất hiện.

### 8.1. Khi nên bật true

Bật true phù hợp khi:

- Topic là dependency bắt buộc để ứng dụng thực hiện chức năng chính.
- Topic phải được tạo trước bởi pipeline hạ tầng.
- Khởi động consumer khi topic chưa tồn tại sẽ là lỗi triển khai.
- Muốn readiness/startup phản ánh việc thiếu dependency quan trọng.
- Không muốn ứng dụng chạy ở trạng thái tưởng như bình thường nhưng không consume được dữ liệu.

Trong mô hình này, quy trình deploy nên tạo topic trước khi triển khai consumer. Nếu topic thiếu, startup failure tạo tín hiệu rõ ràng để pipeline dừng và người vận hành sửa provisioning.

### 8.2. Khi nên để false

false phù hợp khi:

- Topic được tạo động sau khi ứng dụng khởi động.
- Môi trường cho phép consumer chờ topic xuất hiện.
- Listener có thể chưa cần chạy ngay trong giai đoạn bootstrap.
- Topic pattern hoặc subscription có tập topic thay đổi.
- Hệ thống có quy trình retry/monitoring riêng để theo dõi việc topic xuất hiện.

Đổi lại, ứng dụng có thể chạy nhưng listener chưa nhận dữ liệu từ topic còn thiếu. Cần có metric/alert cho tình trạng consumer không được assign partition hoặc không có tiến triển, thay vì chỉ dựa vào trạng thái Spring application là UP.

### 8.3. Bảng chọn chính sách

| Đặc điểm hệ thống | Gợi ý |
|---|---|
| Topic nghiệp vụ cố định, provision trước deploy | true |
| Topic được tạo bởi pipeline IaC trước khi app start | true |
| Topic được tạo theo tenant trong runtime | false hoặc preflight theo tenant |
| Subscription pattern nhận topic mới theo thời gian | Đánh giá hành vi pattern; thường cần monitoring riêng |
| Local development với topic được tạo tự động | false có thể tiện, nhưng không phản ánh production policy |
| Topic bắt buộc cho chức năng cốt lõi và thiếu topic phải chặn deploy | true |

Không nên chọn false chỉ để che lỗi deploy. Cũng không nên bật true một cách máy móc nếu kiến trúc chủ động cho phép topic được tạo sau startup.

## 9. Cấu hình khác có liên quan

missingTopicsFatal chỉ là một phần của cấu hình listener container. Cần hiểu các thuộc tính lân cận để không gán nhầm chức năng.

| Thuộc tính/cơ chế | Vai trò |
|---|---|
| autoStartup | Quyết định listener container có tự start theo lifecycle hay không |
| missingTopicsFatal | Quyết định container có fail khi topic khai báo bị thiếu trong startup check hay không |
| topics / topicPattern | Chọn topic tường minh hoặc topic khớp regex |
| KafkaAdmin / NewTopic | Provision topic từ ứng dụng khi được cấu hình |
| auto.create.topics.enable | Cho phép broker tự tạo topic theo chính sách broker |
| ConsumerFactory | Tạo Kafka consumer với bootstrap, security và consumer properties |
| group.id | Định danh consumer group |
| startup timeout / API timeout | Ảnh hưởng thời gian các thao tác metadata/admin có thể chờ |
| readiness/liveness probe | Phản ánh trạng thái ứng dụng/container theo chính sách triển khai |

autoStartup=false không có nghĩa topic được bỏ qua vĩnh viễn; khi container được start thủ công, startup check có thể được thực hiện tại thời điểm đó. KafkaAdmin tạo topic không phải tác dụng của missingTopicsFatal. Readiness probe cũng cần được thiết kế riêng để phân biệt app process đang chạy với listener thực sự được gán partition và xử lý được record.

## 10. Ví dụ thiết kế hai nhóm listener

Một ứng dụng có thể có topic orders.created bắt buộc và topic tenant-events được tạo động theo tenant. Hai listener có thể cần chính sách khác nhau.

Factory cho topic bắt buộc:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
requiredTopicFactory(
        ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMissingTopicsFatal(true);
    return factory;
}
~~~

Factory cho topic có thể xuất hiện sau:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, TenantEvent>
dynamicTopicFactory(
        ConsumerFactory<String, TenantEvent> consumerFactory) {

    var factory =
        new ConcurrentKafkaListenerContainerFactory<String, TenantEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setMissingTopicsFatal(false);
    return factory;
}
~~~

Listener dùng factory tương ứng:

~~~java
@KafkaListener(
    topics = "orders.created",
    containerFactory = "requiredTopicFactory"
)
public void handleOrder(OrderCreated event) {
    orderService.handle(event);
}

@KafkaListener(
    topicPattern = "tenant-events\\..*",
    containerFactory = "dynamicTopicFactory"
)
public void handleTenantEvent(TenantEvent event) {
    tenantService.handle(event);
}
~~~

Ví dụ minh họa cách tách chính sách ở cấp factory. Với topicPattern, cần xác minh hành vi subscription và kiểm tra startup của phiên bản Spring Kafka cụ thể. Nếu ứng dụng cần xác nhận một tenant topic đã tồn tại trước khi xử lý tenant, nên có bước kiểm tra riêng theo tenant thay vì dựa vào một flag toàn cục.

## 11. Kiểm tra topic trước khi listener khởi động

Với hệ thống cần điều kiện readiness nghiêm ngặt, có thể dùng AdminClient để xác minh topic và topology trước khi cho phép listener start.

Ví dụ kiểm tra topic tồn tại:

~~~java
public boolean topicExists(Admin admin, String topic) throws Exception {
    return admin.listTopics()
            .names()
            .get(10, TimeUnit.SECONDS)
            .contains(topic);
}
~~~

Ví dụ trên là minh họa đơn giản. Trong production cần xử lý timeout, authorization, cluster không sẵn sàng và danh sách topic lớn. Nếu chỉ cần kiểm tra một topic cụ thể, có thể dùng API describeTopics phù hợp phiên bản Kafka client và phân biệt lỗi TopicDoesNotExistException với lỗi kết nối/quyền truy cập.

Để kiểm tra số partition:

~~~java
TopicDescription description = admin.describeTopics(
        List.of("orders.created")
    ).allTopicNames()
     .get(10, TimeUnit.SECONDS)
     .get("orders.created");

int partitionCount = description.partitions().size();
~~~

Kiểm tra replication factor có thể dựa trên danh sách replica của từng partition trong TopicDescription. Nếu chính sách yêu cầu cùng replication factor trên mọi partition, hãy kiểm tra tất cả partition thay vì chỉ kiểm tra partition đầu tiên.

Không nên dùng AdminClient preflight như một kiểm tra rồi đóng client và giả định trạng thái sẽ không đổi mãi mãi. Topic có thể bị xóa hoặc thay đổi sau bước kiểm tra. Preflight là cổng xác nhận trước startup; monitoring vẫn cần phát hiện thay đổi trong runtime.

## 12. Quy trình điều tra khi listener không start

Khi container không khởi động và log nhắc đến missing topic, hãy điều tra theo trình tự:

### Bước 1: Xác định listener và factory

- Listener nào không start?
- Annotation dùng topics hay topicPattern?
- Listener đang dùng containerFactory nào?
- missingTopicsFatal có được set trực tiếp trong factory không?
- Có property Boot bị ghi đè bởi cấu hình Java không?

### Bước 2: Xác nhận tên topic và cluster

- Topic có đúng chính tả, dấu chấm và quy ước tên không?
- Bootstrap servers có trỏ đúng môi trường không?
- Topic có tồn tại trên cluster mà consumer đang kết nối không?
- Topic có vừa được tạo nhưng metadata chưa cập nhật không?

### Bước 3: Kiểm tra quyền và kết nối

- Principal có quyền describe/consume topic và quyền group cần thiết không?
- TLS/SASL có được cấu hình đúng không?
- Broker có sẵn sàng và có leader cho partition không?
- Log có chỉ ra timeout hoặc authentication failure thay vì topic không tồn tại không?

### Bước 4: Kiểm tra provisioning

- Pipeline tạo topic đã chạy thành công chưa?
- KafkaAdmin có được cấu hình và có quyền tạo topic không?
- NewTopic bean có được load trong application context không?
- Topic có đúng partition, replication và config không?

### Bước 5: Chọn phản ứng phù hợp

- Nếu topic bắt buộc và thiếu là lỗi deploy, giữ missingTopicsFatal=true và sửa provisioning.
- Nếu topic được tạo sau startup theo thiết kế, cân nhắc false và thêm monitoring.
- Nếu lỗi là broker/auth/ACL, sửa dependency tương ứng; không đổi flag để che lỗi.
- Nếu topic tồn tại nhưng topology sai, thêm kiểm tra readiness riêng.

### Bước 6: Xác nhận listener hoạt động

Sau khi container start, xác nhận consumer group có member, partition được assign, listener nhận record thử nghiệm và committed offset tiến triển. Trạng thái container started chưa đủ để chứng minh consumer đã đọc được dữ liệu.

## 13. Monitoring sau startup

Vì missingTopicsFatal không giám sát liên tục, production cần theo dõi các tín hiệu runtime:

- Listener container running/stopped state.
- Consumer group member count và partition assignment.
- Consumer lag và thời gian record cũ nhất chưa xử lý.
- Lỗi metadata, topic authorization, fetch và commit.
- Số lần container restart hoặc start failure.
- Topic/partition state và under-replicated partitions.
- Thời gian từ lúc deploy đến khi consumer nhận record đầu tiên.

Nếu topic bị xóa sau startup, consumer có thể không còn đọc được dữ liệu hoặc nhận lỗi khi metadata thay đổi. Cần alert khi listener không có assignment ngoài dự kiến, group lag tăng hoặc consumer không có tiến triển trong khoảng thời gian vượt SLO.

Readiness probe có thể kiểm tra trạng thái listener container và assignment nếu ứng dụng có actuator/custom health indicator. Không nên dùng một phép kiểm tra đơn giản rằng Spring context đã chạy để kết luận consumer sẵn sàng xử lý.

## 14. Các lỗi cấu hình thường gặp

| Cách làm | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ missingTopicsFatal tự tạo topic | Topic vẫn thiếu hoặc được tạo với cấu hình mặc định không phù hợp | Provision bằng KafkaAdmin/NewTopic hoặc IaC |
| Đặt false để che sai tên topic | App khởi động nhưng listener không nhận dữ liệu như mong đợi | Kiểm tra topic name và thêm alert cho consumer assignment |
| Đặt true cho topic động | Startup có thể thất bại trước khi topic được tạo theo thiết kế | Dùng policy phù hợp hoặc preflight riêng |
| Chỉ kiểm tra topic tồn tại | Bỏ sót partition count, replication, retention hoặc ACL | Thêm kiểm tra topology và quyền |
| Nhầm broker unavailable với topic missing | Thay đổi flag nhưng lỗi kết nối vẫn còn | Đọc exception gốc và kiểm tra network/metadata |
| Cho rằng flag giám sát runtime | Không phát hiện topic bị xóa sau startup | Theo dõi container, group, metadata và lag |
| Cấu hình Boot nhưng listener dùng factory khác | Giá trị không áp dụng cho listener cần kiểm soát | Kiểm tra containerFactory và ContainerProperties thực tế |
| Dựa vào auto-create ở production | Topic có thể có partition/replication/config sai | Tắt hoặc kiểm soát auto-create và provision rõ ràng |

## 15. Checklist thiết kế

Trước khi chọn missingTopicsFatal, hãy trả lời:

1. Topic của listener là dependency bắt buộc hay có thể xuất hiện sau startup?
2. Listener khai báo topics tường minh hay topicPattern?
3. Container thực tế dùng factory nào và giá trị missingTopicsFatal đang là gì?
4. Phiên bản Spring Kafka/Spring Boot đang dùng có mặc định và property binding như thế nào?
5. Topic được tạo bởi IaC, KafkaAdmin/NewTopic hay broker auto-create?
6. Provisioning có hoàn tất trước khi listener start không?
7. Ứng dụng có cần kiểm tra partition count, replication factor, retention hoặc ACL không?
8. Nếu broker tạm thời không sẵn sàng, log có phân biệt được lỗi kết nối với topic missing không?
9. Khi để false, monitoring có phát hiện consumer không có assignment hoặc không tiến triển không?
10. Khi topic bị xóa sau startup, ai phát hiện và quy trình phục hồi là gì?

missingTopicsFatal là một công tắc chính sách startup cho listener container. Bật true phù hợp khi topic phải tồn tại trước khi ứng dụng nhận traffic và việc thiếu topic cần chặn triển khai. Để false phù hợp khi topic có thể xuất hiện sau hoặc subscription mang tính động, với điều kiện ứng dụng có quan sát runtime đủ tốt. Dù chọn giá trị nào, topic vẫn cần được provision đúng cách và được giám sát về partition, replication, quyền truy cập và trạng thái hoạt động.
