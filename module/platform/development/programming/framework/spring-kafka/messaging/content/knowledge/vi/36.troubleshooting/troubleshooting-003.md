# Consumer không nhận record

Khi một ứng dụng Spring Kafka không nhận được record, nguyên nhân có thể nằm ở producer, topic, consumer group, offset, listener container, deserialization hoặc kết nối tới broker. Việc chỉ kiểm tra phương thức có annotation @KafkaListener thường chưa đủ: listener có thể chưa được start, consumer chưa được gán partition, group đang đứng ở offset cuối, record bị lọc hoặc lỗi deserialize xảy ra trước khi gọi phương thức.

Cách xử lý hiệu quả là đi theo đường đi của record và xác định điểm cuối cùng còn hoạt động: producer đã publish chưa, record có nằm trong topic không, group có assignment không, offset có tiến triển không và listener có thật sự được gọi không. Mỗi bước cần một bằng chứng cụ thể trước khi chuyển sang bước tiếp theo.

## 1. Xác định chính xác triệu chứng

Trước khi sửa cấu hình, hãy xác định "không nhận record" có nghĩa là gì:

| Triệu chứng | Hướng kiểm tra đầu tiên |
|---|---|
| Producer gửi nhưng không thấy record trong topic | Kết quả send, topic, broker và serializer |
| Topic có record nhưng consumer group không có assignment | Group membership, subscription và partition |
| Group có assignment nhưng lag không giảm | Consumer poll, listener, pause và lỗi xử lý |
| Lag bằng 0 nhưng listener không chạy | Offset đang ở cuối log, sai topic hoặc không có record mới |
| Listener không được gọi, nhưng log báo deserialize error | Deserializer và ErrorHandlingDeserializer |
| Chỉ một số key/partition không được xử lý | Partition assignment, hot partition, transaction và record filtering |
| Local chạy nhưng môi trường triển khai không chạy | Bootstrap server, advertised.listeners, ACL và TLS |
| Consumer từng chạy rồi dừng nhận | Rebalance, exception, container lifecycle và poll interval |

Ghi lại các thông tin trước khi điều tra:

- Topic và môi trường đang kiểm tra.
- Consumer group ID thực tế.
- Listener ID và container factory được sử dụng.
- Số partition của topic.
- Thời điểm producer gửi record và kết quả gửi.
- Consumer group lag, assignment và committed offset.
- Cấu hình isolation level, auto offset reset và security.

Không thay đổi offset hoặc tạo group mới ngay từ đầu. Những thao tác đó có thể làm thay đổi dữ liệu mà consumer sẽ đọc và khiến việc tìm nguyên nhân khó hơn.

## 2. Kiểm tra producer đã publish thành công chưa

Lời gọi KafkaTemplate.send() thường trả về một future vì gửi record là thao tác bất đồng bộ. Việc gọi send() mà không quan sát kết quả không chứng minh broker đã xác nhận record.

Ví dụ kiểm tra kết quả gửi:

~~~java
SendResult<String, OrderEvent> result =
        kafkaTemplate.send(
                "orders",
                event.orderId().toString(),
                event
        ).get(10, TimeUnit.SECONDS);

RecordMetadata metadata = result.getRecordMetadata();

log.info(
        "Published order event topic={} partition={} offset={}",
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
);
~~~

Trong ứng dụng production, không nhất thiết phải block bằng get() cho mọi lần gửi. Có thể xử lý future bằng callback hoặc CompletableFuture. Điều quan trọng là phải ghi nhận lỗi publish như timeout, serialization error, authorization failure hoặc broker unavailable.

Nếu gửi bất đồng bộ, hãy kiểm tra callback/future exception. Nếu không quan sát lỗi, producer có thể thất bại mà log nghiệp vụ vẫn ghi "đã gửi".

Những điểm cần xác nhận:

- Producer đang gửi đúng topic của môi trường hiện tại.
- Key/value serializer có thể serialize event.
- Broker trả acknowledgement thành công.
- Topic có tồn tại hoặc broker được phép auto-create.
- Producer có quyền WRITE và DESCRIBE topic.
- Không có exception bị nuốt trong callback.

Producer nhận acknowledgement cho biết broker đã nhận record theo cấu hình acknowledgement; điều đó vẫn chưa chứng minh consumer group đang đọc đúng topic hoặc đúng offset.

## 3. Xác nhận record thực sự có trong topic

Dùng Kafka CLI để xem metadata topic:

~~~bash
kafka-topics.sh   --bootstrap-server localhost:9092   --describe   --topic orders
~~~

Kiểm tra:

- Topic có tồn tại trên đúng cluster không.
- Số partition có đúng như mong đợi không.
- Leader của từng partition có sẵn sàng không.
- Replicas và ISR có bất thường không.

Có thể đọc thử một số record bằng console consumer:

~~~bash
kafka-console-consumer.sh   --bootstrap-server localhost:9092   --topic orders   --from-beginning   --max-messages 10   --property print.key=true   --property print.partition=true   --property print.offset=true
~~~

Lệnh này tạo một consumer để đọc dữ liệu. Không dùng group ID production để kiểm tra vì consumer chẩn đoán có thể tham gia cùng group và chia partition với ứng dụng đang chạy. Nếu cần chỉ định group, hãy dùng group tạm riêng và hiểu rằng group mới có offset riêng.

Khi dùng --from-beginning, console consumer có thể đọc dữ liệu còn retention từ đầu. Giới hạn số record và dùng đúng cluster/topic để tránh đọc nhầm dữ liệu lớn hoặc nhạy cảm.

Nếu console consumer cũng không thấy record, hãy quay lại producer, topic, cluster, ACL và thời điểm gửi. Nếu console consumer thấy record nhưng ứng dụng không thấy, tập trung vào group, subscription, offset, listener và deserialization.

## 4. Kiểm tra topic và subscription của @KafkaListener

Xác nhận annotation đang trỏ đúng topic:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service"
)
public void consume(OrderEvent event) {
    log.info("Received orderId={}", event.orderId());
    orderService.process(event);
}
~~~

Các lỗi thường gặp:

- Tên topic sai chính tả hoặc khác chữ hoa/thường.
- Profile đang chạy ghi đè property thành topic khác.
- Listener dùng topic của môi trường local trong khi producer gửi vào cluster khác.
- Listener dùng topics trong khi cấu hình thực tế cần topicPattern.
- Placeholder không được resolve như dự kiến.
- Listener được tạo bởi một containerFactory khác với factory đang được cấu hình.

Nếu dùng property:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "${app.kafka.orders-topic}",
        groupId = "${app.kafka.orders-group}"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Kiểm tra giá trị property sau khi Spring nạp profile. Có thể ghi log tên topic và group ID lúc khởi động, nhưng không ghi thông tin xác thực hoặc toàn bộ cấu hình nhạy cảm.

Nếu subscribe bằng regex, kiểm tra pattern có khớp tên topic thật và consumer có cập nhật metadata để phát hiện topic mới hay không. Nếu topic được tạo sau khi listener start, thời điểm phát hiện còn phụ thuộc subscription mode và metadata refresh.

## 5. Kiểm tra listener container có đang chạy không

Spring Kafka quản lý listener thông qua listener container. Một phương thức có annotation nhưng container chưa start thì listener không nhận record.

Ví dụ listener bị tắt auto startup:

~~~java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "order-service",
        autoStartup = "false"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Khi dùng autoStartup=false, ứng dụng phải chủ động start container. Có thể kiểm tra bằng KafkaListenerEndpointRegistry:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("orders-listener");

if (container == null) {
    log.error("Listener container was not registered");
}
else {
    log.info(
            "Listener container running={}",
            container.isRunning()
    );
}
~~~

Nếu container chưa chạy, kiểm tra:

- autoStartup của @KafkaListener hoặc container factory.
- Bean listener có được Spring component scan và tạo thành công không.
- ApplicationContext có hoàn tất startup không.
- Có lỗi tạo consumer hoặc khởi động container trong log không.
- Một thành phần khác có gọi stop() hay pause() không.
- Listener ID có trùng hoặc registry lookup sai ID không.

isRunning() chỉ cho biết lifecycle container đang chạy. Nó không chứng minh consumer đã được gán partition. Cần kiểm tra assignment hoặc consumer group để xác nhận listener có nguồn record.

## 6. Kiểm tra consumer group và partition assignment

Kafka phân phối partition cho các consumer trong cùng một group. Mỗi partition chỉ được gán cho tối đa một consumer trong group tại một thời điểm. Nếu group có nhiều consumer hơn số partition, một số consumer sẽ idle.

Xem trạng thái group:

~~~bash
kafka-consumer-groups.sh   --bootstrap-server localhost:9092   --describe   --group order-service
~~~

Kết quả thường có các cột:

| Cột | Ý nghĩa |
|---|---|
| GROUP | Consumer group ID |
| TOPIC | Topic đang tiêu thụ |
| PARTITION | Partition được mô tả |
| CURRENT-OFFSET | Offset đã commit của group |
| LOG-END-OFFSET | Offset cuối hiện tại của partition |
| LAG | Chênh lệch giữa log end và committed position theo công cụ |
| CONSUMER-ID | Consumer instance được gán |
| HOST | Host của consumer |
| CLIENT-ID | Client ID |

Cách đọc:

- Không có dòng topic/partition: group có thể chưa subscribe topic, chưa active hoặc chưa có assignment/offset được công cụ hiển thị.
- CONSUMER-ID trống: partition chưa được gán cho consumer đang hoạt động.
- LAG tăng liên tục: consumer không theo kịp producer hoặc đang không xử lý.
- CURRENT-OFFSET tiến lên: group đang commit tiến độ, dù cần kiểm tra listener có hoàn tất nghiệp vụ hay không.
- LAG bằng 0: group đã theo kịp committed view tại thời điểm đo; không có nghĩa record cũ chắc chắn đã được đọc nếu offset được khởi tạo ở cuối log.

Nếu một group được dùng bởi nhiều service không liên quan, các consumer sẽ chia partition với nhau. Mỗi service cần nhận toàn bộ event độc lập thường phải dùng group ID riêng. Ngược lại, các instance của cùng một logical service thường dùng chung group ID để chia tải.

## 7. Kiểm tra consumer group ID có đúng không

Group ID quyết định offset được sử dụng. Có thể cấu hình qua Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
~~~

Hoặc chỉ định trực tiếp trong annotation:

~~~java
@KafkaListener(
        topics = "orders",
        groupId = "order-service"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}
~~~

Nếu annotation có groupId, hãy kiểm tra nó có ghi đè group ID mặc định mà bạn đang xem trong CLI hay không.

Một lỗi thường gặp là producer và consumer đúng topic nhưng người vận hành kiểm tra nhầm group. Consumer thực tế có thể đang dùng group ID khác do profile, placeholder hoặc annotation.

Đừng tạo group ID ngẫu nhiên trong production cho mỗi lần khởi động nếu cần tiếp tục từ offset cũ. Group mới không có committed offset nên hành vi bắt đầu phụ thuộc auto.offset.reset.

## 8. Kiểm tra committed offset và auto.offset.reset

auto.offset.reset chỉ được áp dụng khi group không có committed offset hợp lệ cho partition. Nó không tự tua lại dữ liệu khi group đã có offset.

Hai giá trị thường dùng:

| Giá trị | Hành vi khi chưa có offset hợp lệ |
|---|---|
| earliest | Bắt đầu từ offset sớm nhất còn được giữ |
| latest | Bắt đầu từ cuối log theo thời điểm consumer cần reset |

Ví dụ:

1. Producer đã ghi 100 record.
2. Consumer group mới khởi động với auto.offset.reset=latest.
3. Consumer bắt đầu ở cuối log.
4. Không có record mới sau đó nên listener không được gọi.

Đây là nguyên nhân phổ biến khi topic có dữ liệu nhưng consumer mới không nhận record nào.

Cấu hình:

~~~yaml
spring:
  kafka:
    consumer:
      auto-offset-reset: earliest
~~~

Chỉ dùng earliest khi nghiệp vụ muốn đọc lại dữ liệu còn retention cho group chưa có offset. Nếu group đã có committed offset, đổi latest thành earliest không làm group tự đọc lại từ đầu.

Muốn replay, cần một thao tác reset offset có chủ đích, có kiểm tra tác động và runbook rõ ràng. Không chạy --reset-offsets trên group production chỉ để thử mà chưa xác định phạm vi partition và hậu quả xử lý trùng.

## 9. Kiểm tra deserialization trước listener

Nếu Kafka consumer không thể deserialize key hoặc value, phương thức @KafkaListener có thể không được gọi. Lỗi xảy ra ở bước chuyển bytes thành object, trước khi payload đến listener.

Ví dụ cấu hình JSON:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: "com.example.events"
        spring.json.value.default.type: "com.example.events.OrderEvent"
~~~

Hãy xác nhận producer và consumer thống nhất:

- Serializer và deserializer tương ứng.
- Schema/DTO thực tế được gửi.
- Header type mapping nếu dùng JSON type headers.
- Trusted packages và default type.
- Version class và field compatibility.
- Charset/format nếu dùng serializer tùy chỉnh.

Trong Spring Kafka, ErrorHandlingDeserializer có thể giúp chuyển lỗi deserialize thành thông tin mà error handler xử lý được:

~~~yaml
spring:
  kafka:
    consumer:
      key-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.key.delegate.class: org.apache.kafka.common.serialization.StringDeserializer
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: "com.example.events"
        spring.json.value.default.type: "com.example.events.OrderEvent"
~~~

Cần kiểm tra log consumer và error handler. Một record deserialize lỗi có thể được xử lý theo chính sách recoverer/DLT mà không gọi listener business. Nếu chỉ tìm log bên trong phương thức listener, bạn sẽ không thấy nguyên nhân.

Không mở trusted packages quá rộng trong production nếu không cần thiết. Cấu hình deserialization phải phù hợp với nguồn dữ liệu và chính sách bảo mật.

## 10. Kiểm tra isolation.level và Kafka transaction

Consumer có thể được cấu hình đọc chỉ những record thuộc transaction đã commit:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        isolation.level: read_committed
~~~

Với read_committed, consumer không trả về record thuộc transaction chưa commit hoặc đã abort. Nếu producer transaction còn mở trên một partition, Last Stable Offset (LSO) có thể giới hạn vị trí consumer được phép đọc. Record phía sau transaction đang mở có thể chưa được trả về cho tới khi transaction kết thúc.

Điều này có thể khiến consumer nhìn như không nhận record mới dù log end offset đã tăng. Kiểm tra producer transaction có bị treo, transaction timeout, lỗi commit hoặc producer fencing hay không.

Nếu ứng dụng không dùng transactional producer và không cần loại bỏ aborted records, read_uncommitted có thể phù hợp theo yêu cầu. Không đổi isolation level chỉ để làm record xuất hiện mà chưa hiểu semantics dữ liệu cần đọc.

## 11. Kiểm tra listener hoặc partition đang bị pause

Container có thể vẫn isRunning nhưng consumer đã pause. Khi pause, container tiếp tục poll để duy trì membership của group, nhưng partition được pause không trả thêm record mới cho listener.

Có thể kiểm tra trạng thái pause qua API container phù hợp với phiên bản Spring Kafka. Nếu ứng dụng dùng pause/resume cho backpressure, hãy kiểm tra controller có gọi pause() hay pausePartition() và có điều kiện resume tương ứng không.

Những nguyên nhân thường gặp:

- Queue nội bộ chạm high watermark.
- Downstream trả lỗi và controller pause consumer.
- Một partition bị pause nhưng không được resume sau recovery.
- Container được pause bởi thao tác quản trị.
- Logic điều khiển trạng thái bị lệch sau rebalance hoặc restart.

Phân biệt pause với stop: pause giữ consumer trong group; stop đóng consumer và khiến group rebalance. Khi record không được nhận, hãy kiểm tra cả hai trạng thái.

## 12. Kiểm tra poll interval và listener bị block

Kafka consumer cần poll định kỳ. Nếu xử lý listener đồng bộ quá lâu, consumer có thể không gọi poll trong giới hạn max.poll.interval.ms. Khi vượt giới hạn, consumer có thể rời group và partition được gán lại.

Các cấu hình liên quan:

| Cấu hình | Vai trò |
|---|---|
| max.poll.interval.ms | Thời gian tối đa giữa các lần poll trước khi consumer bị xem là không tiến triển |
| max.poll.records | Số record tối đa trả về trong một lần poll |
| session.timeout.ms | Thời gian coordinator chờ consumer không heartbeat trước khi loại khỏi group theo cơ chế group protocol |
| heartbeat.interval.ms | Chu kỳ heartbeat trong các protocol hỗ trợ cấu hình này |
| pollTimeout của container | Thời gian container chờ một lần poll trả dữ liệu |

Nếu listener gọi API không có timeout hoặc xử lý batch quá lâu, consumer có thể liên tục rebalance và không xử lý ổn định.

Cách khắc phục:

- Đặt timeout cho HTTP/database call.
- Giảm max.poll.records nếu mỗi record tốn nhiều thời gian.
- Tối ưu xử lý và batch.
- Tăng max.poll.interval.ms chỉ khi thời gian xử lý hợp lý và đã đo.
- Tránh sleep lâu trong listener.
- Dùng async processing có cơ chế quản lý offset và backpressure rõ ràng.

Tăng max.poll.interval.ms không làm dependency chậm nhanh hơn. Nó chỉ thay đổi giới hạn thời gian trước khi consumer bị xem là không tiến triển.

## 13. Kiểm tra listener filter và interceptor

Record có thể được nhận từ Kafka nhưng không đến phương thức listener do bị lọc hoặc thay đổi trong pipeline container.

Kiểm tra:

- RecordFilterStrategy trên listener container factory.
- FilteringMessageListenerAdapter.
- RecordInterceptor.
- Batch interceptor nếu dùng batch listener.
- Logic custom deserializer hoặc message converter.
- Error handler/recoverer có skip hoặc chuyển record đi nơi khác không.

Ví dụ filter:

~~~java
factory.setRecordFilterStrategy(
        record -> record.value() == null
);
~~~

Với cấu hình trên, record có value null bị loại khỏi listener theo filter. Tùy cấu hình ackDiscarded và container semantics, record bị loại có thể được xác nhận/commit như đã xử lý. Hãy kiểm tra filter có vô tình loại mọi record do điều kiện sai hay không.

Tạm thời instrument trước và sau filter trong môi trường test để xác định record biến mất ở bước nào. Không log toàn bộ payload nhạy cảm.

## 14. Kiểm tra bootstrap server, advertised.listeners và network

Producer có thể kết nối được bootstrap server nhưng consumer chạy ở môi trường khác không kết nối được các broker được quảng bá trong metadata.

Kafka client dùng bootstrap.servers để tìm cluster metadata, sau đó kết nối tới broker endpoint mà cluster quảng bá qua advertised.listeners. Nếu địa chỉ đó chỉ truy cập được từ mạng nội bộ hoặc sai DNS/port, consumer có thể kết nối ban đầu nhưng lỗi khi fetch từ leader.

Kiểm tra:

- spring.kafka.bootstrap-servers đúng môi trường.
- DNS và port broker có thể truy cập từ pod/VM của consumer.
- advertised.listeners công bố hostname/port có thể truy cập từ client.
- Firewall, network policy và service mesh không chặn traffic.
- TLS truststore/keystore và hostname verification.
- SASL mechanism, username/password và JAAS config.
- ACL cho phép consumer DESCRIBE/READ topic và READ group.

Nếu có lỗi authorization, authentication hoặc disconnect, xem log Kafka client và broker. Không ghi SASL password, private key hoặc token vào log.

## 15. Kiểm tra topic partition và concurrency

Consumer group chỉ có thể xử lý song song tối đa theo số partition được gán. Nếu topic có ba partition nhưng listener concurrency bằng tám, tối đa ba consumer có assignment trong group tại một thời điểm; các consumer còn lại idle.

Nếu một partition không có leader hoặc replica ISR bất thường, consumer có thể không fetch được dữ liệu từ partition đó.

Kiểm tra topic:

~~~bash
kafka-topics.sh   --bootstrap-server localhost:9092   --describe   --topic orders
~~~

Kiểm tra group:

~~~bash
kafka-consumer-groups.sh   --bootstrap-server localhost:9092   --describe   --group order-service
~~~

Nếu chỉ một partition không được xử lý, tập trung vào leader, assignment, key distribution, pause partition và lỗi record ở partition đó. Nếu toàn bộ partition không được xử lý, tập trung vào subscription, group, kết nối và lifecycle.

## 16. Kiểm tra cấu hình consumer Spring Boot

Một cấu hình cơ bản cần nhất quán giữa broker, group và serializer:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: "com.example.events"
        spring.json.value.default.type: "com.example.events.OrderEvent"
~~~

Ví dụ này chỉ phù hợp khi producer gửi JSON tương thích với OrderEvent. Nếu ứng dụng dùng Avro, Protobuf hoặc serializer riêng, thay deserializer và registry properties theo format thực tế.

Với Spring Kafka listener container, offset thường được quản lý theo AckMode của container. enable.auto.commit=false là cấu hình phổ biến để container quản lý commit. Nếu bật auto commit hoặc dùng manual acknowledgment, cần hiểu rõ thời điểm offset được xác nhận.

Không chỉnh đồng thời nhiều cấu hình khi đang chẩn đoán. Thay từng yếu tố có giả thuyết, đo lại group/lag và giữ lại kết quả để xác định thay đổi nào giải quyết vấn đề.

## 17. Một quy trình chẩn đoán từ ngoài vào trong

Có thể thực hiện theo thứ tự sau:

1. **Producer:** xác nhận future/callback send thành công và có topic/partition/offset.
2. **Topic:** kiểm tra topic đúng cluster, có partition và leader.
3. **Console read:** dùng consumer tạm riêng để xác nhận record tồn tại.
4. **Listener lifecycle:** xác nhận bean được tạo, listener ID đăng ký và container running.
5. **Subscription:** xác nhận topic/pattern mà listener thực sự subscribe.
6. **Consumer group:** kiểm tra group ID, member, partition assignment và lag.
7. **Offset:** kiểm tra committed offset và auto.offset.reset.
8. **Deserialization:** kiểm tra lỗi serializer/deserializer và error handler.
9. **Isolation:** kiểm tra read_committed và transaction đang mở.
10. **Pause/filter:** kiểm tra container/partition pause và record filter/interceptor.
11. **Poll:** kiểm tra listener bị block, max.poll.interval.ms và rebalance.
12. **Network/security:** kiểm tra advertised.listeners, ACL, TLS và SASL.

Mỗi bước cần một bằng chứng. Ví dụ, nếu console consumer đọc được record và group không có assignment, đừng sửa serializer trước; hãy điều tra subscription, group và listener lifecycle.

## 18. Ma trận triệu chứng và nguyên nhân

| Triệu chứng quan sát | Nguyên nhân có thể | Kiểm tra tiếp theo |
|---|---|---|
| Producer send timeout | Broker/network hoặc metadata | Producer logs, broker health |
| Topic không tồn tại | Sai tên/cluster hoặc chưa provision | kafka-topics --describe |
| Console đọc được, app không đọc | Group/subscription/offset/listener | Consumer group và container |
| Group không có member | Container chưa start hoặc kết nối lỗi | Listener registry và client logs |
| Group có member nhưng không có assignment | Subscription mismatch, partition metadata hoặc rebalance | Topic describe và group state |
| Lag bằng 0 nhưng không có callback | Offset ở cuối log hoặc không có record mới | Current offset, log end và thời điểm gửi |
| Lag tăng liên tục | Consumer không poll hoặc xử lý chậm | Processing time, poll, rebalance |
| Deserialization exception | Payload/schema không tương thích | Delegate deserializer và DLT |
| Chỉ record trong transaction chưa commit không xuất hiện | read_committed/LSO | Producer transaction state |
| Listener running nhưng không nhận | Paused, filter hoặc chưa assignment | Pause state, interceptor, assignment |
| Lỗi disconnect/authentication | Network, TLS, SASL, ACL | Client/broker security logs |

## 19. Những thao tác cần thận trọng

Một số thao tác có thể làm thay đổi hành vi đọc dữ liệu:

- Reset offset về earliest có thể phát lại toàn bộ dữ liệu còn retention.
- Tạo group ID mới có thể đọc từ đầu hoặc cuối tùy auto.offset.reset.
- Chạy console consumer cùng group production có thể chia partition với ứng dụng.
- Xóa topic làm mất dữ liệu và metadata topic.
- Tăng partition có thể thay đổi key-to-partition mapping và ordering.
- Tắt read_committed có thể làm consumer nhìn thấy record thuộc transaction bị abort.
- Tắt filter hoặc đổi deserializer có thể đưa dữ liệu lỗi vào business listener.

Chỉ thực hiện các thao tác này sau khi xác định mục tiêu, phạm vi partition và khả năng xử lý duplicate. Với production, cần runbook và người chịu trách nhiệm cho thao tác offset/topic.

## 20. Checklist xử lý nhanh

- [ ] Producer đã nhận acknowledgement và log topic/partition/offset.
- [ ] Topic tồn tại trên đúng cluster và có leader cho các partition.
- [ ] Console consumer tạm riêng đọc được record.
- [ ] @KafkaListener subscribe đúng topic hoặc pattern.
- [ ] Listener bean đã được đăng ký và container đang running.
- [ ] Container không bị pause hoặc stop.
- [ ] Consumer group ID đúng với group đang kiểm tra.
- [ ] Group có member và partition assignment.
- [ ] Committed offset và log end offset đã được đối chiếu.
- [ ] auto.offset.reset được hiểu đúng; không nhầm với reset committed offset.
- [ ] Key/value deserializer và schema tương thích.
- [ ] ErrorHandlingDeserializer/error handler không âm thầm chuyển record sang DLT.
- [ ] isolation.level và transaction state không chặn record chưa commit.
- [ ] Listener không bị block vượt max.poll.interval.ms.
- [ ] Filter/interceptor không loại record ngoài ý muốn.
- [ ] Bootstrap server, advertised.listeners, TLS, SASL và ACL hợp lệ.
- [ ] Không dùng chung group production khi chạy công cụ chẩn đoán.
- [ ] Có metric lag, assignment, processing time và log lỗi để theo dõi sau khi sửa.

Khi consumer không nhận record, hãy lần theo record từ producer tới topic, rồi từ topic qua group, assignment, offset và listener container. Phân biệt rõ không có record mới với consumer đang đứng ở offset cuối, consumer chưa được gán partition, record bị pause/lọc hay lỗi deserialize trước listener. Chẩn đoán theo từng lớp và xác minh bằng metric/CLI/log giúp tìm đúng nguyên nhân mà không phải reset offset hoặc thay đổi topology một cách rủi ro.

