# Đánh giá nâng cấp Classic và chuyển từ Classic sang Artemis

> **Chương:** Di chuyển broker  
> **Phạm vi:** Đánh giá nâng cấp Apache ActiveMQ Classic trong cùng dòng sản phẩm và lập kế hoạch chuyển broker từ Classic 5.x sang ActiveMQ Artemis. Trọng tâm là tiêu chí lựa chọn, tương thích client/protocol, ánh xạ destination, chuyển dữ liệu, cutover và rollback. Bối cảnh module gồm queue, topic, routing, JMS, producer/consumer, transaction, redelivery, DLQ, bảo mật và vận hành.

## 1. Hai quyết định khác nhau: upgrade hay migration?

**Nâng cấp Classic** là đưa broker đang chạy lên phiên bản Classic mới hơn. Broker vẫn thuộc cùng sản phẩm, thường tiếp tục persistence adapter và mô hình destination hiện có; tuy nhiên phải xử lý thay đổi theo release, Java runtime, dependency, cấu hình và khả năng tương thích store.

**Chuyển sang Artemis** là thay broker bằng sản phẩm có kiến trúc, message store, addressing model và cách vận hành khác. Artemis có thể nhận kết nối OpenWire từ nhiều ActiveMQ Classic JMS client, nhưng điều đó chỉ giải quyết một phần tương thích giao thức. Nó không biến KahaDB thành Artemis journal và không tự chuyển toàn bộ cấu hình hoặc semantics của Classic.

| Tiêu chí | Nâng cấp Classic | Chuyển Classic → Artemis |
|---|---|---|
| Mục tiêu | Tiếp tục dùng Classic trên bản phát hành mới | Chuyển broker sang Artemis |
| Broker runtime | Classic cũ → Classic mới | Classic → Artemis |
| Message store | Theo hướng dẫn upgrade từng phiên bản và adapter đang dùng | Store khác; cần export/import hoặc relay |
| Client | Thường ít thay đổi hơn, vẫn phải test | Có thể giữ OpenWire trước mắt, rồi đổi client/protocol sau |
| Destination/config | Giữ mô hình Classic, cập nhật theo release | Ánh xạ queue/topic sang address, routing type và queue |
| Rủi ro chính | Breaking changes, plugin/JVM/store upgrade | Semantic mismatch, data transfer, cutover và client compatibility |
| Rollback | Restore snapshot tương thích với bản Classic cũ | Quay endpoint về Classic và đối soát event phát sinh sau cutover |
| Kiểm thử | Upgrade clone, regression và load test | Contract test, reconciliation, load test, cutover/rollback drill |

### 1.1. Khi nào nên chỉ nâng cấp Classic?

Nâng cấp trong cùng dòng sản phẩm thường hợp lý khi:

- Ứng dụng phụ thuộc nhiều vào Classic-specific features, plugin hoặc tooling chưa được kiểm chứng trên Artemis.
- Thời gian chuyển đổi hạn chế nhưng cần security fixes hoặc bug fixes từ bản Classic mới.
- Persistence adapter, topology và quy trình vận hành hiện tại vẫn đáp ứng yêu cầu.
- Client đang dùng API cũ hoặc dependency chưa thể chuyển đồng thời.
- Chưa có thời gian kiểm thử mapping topic, durable subscription, virtual topic, selectors, transactions và operational tooling.

Upgrade vẫn cần clone test. Không giả định mọi bản Classic có thể mở cùng một store theo cả hai chiều. Sau khi broker mới ghi vào store, khả năng mở lại bằng binary cũ phải được xác minh theo version; rollback đáng tin cậy thường là khôi phục snapshot trước upgrade, không phải thay executable về bản cũ rồi mở store vừa bị sửa.

### 1.2. Khi nào nên chuyển sang Artemis?

Migration đáng cân nhắc khi:

- Cần kiến trúc address/routing và hỗ trợ nhiều protocol theo một mô hình thống nhất.
- Muốn dùng Artemis clustering/federation/HA phù hợp yêu cầu mới.
- Muốn hiện đại hóa client, API Jakarta Messaging hoặc chuẩn hóa AMQP 1.0.
- Chi phí duy trì Classic-specific extension lớn hơn chi phí chuyển đổi.
- Có đủ năng lực inventory semantics, chuyển dữ liệu, test tương thích và diễn tập cutover.

Không chọn Artemis chỉ dựa trên benchmark mặc định. Throughput phụ thuộc message size, persistence, batching, acknowledgement, paging, producer rate, consumer concurrency, disk và network. Phải benchmark trên workload đại diện.

## 2. Đánh giá hiện trạng trước khi chọn đường đi

Tạo inventory có thể đối chiếu giữa broker nguồn và target. Inventory trở thành đầu vào của test plan, mapping và cutover checklist.

### 2.1. Broker, runtime và dependency

| Nhóm | Cần ghi nhận | Vì sao quan trọng |
|---|---|---|
| Broker | Classic version, brokerName, uptime, topology | Xác định đường upgrade và điểm cắt |
| Runtime | Java version, JVM options, GC, heap, OS/container | Broker version có yêu cầu runtime khác nhau |
| Persistence | KahaDB, mKahaDB, JDBC, store path, disk | Quyết định cách backup và data migration |
| Plugins | Broker plugins, interceptors, authentication modules | Có thể không có bản tương đương hoặc API khác |
| Transport | OpenWire, AMQP, STOMP, MQTT, SSL/TLS, VM | Xác định client nào cần thay đổi |
| Topology | Network connectors, discovery, bridges, HA, shared store | Tránh mất route hoặc tạo loop |
| Security | Users, roles, ACL, LDAP/JAAS, certificates | Không để target mở rộng quyền vô tình |
| Operations | JMX, metrics, alert, log, backup, runbook | Đảm bảo target vận hành được |

Ghi cấu hình sau khi resolve environment variables, system properties, secret references và file include. Chỉ đọc XML trong source control có thể bỏ sót cấu hình được inject lúc deploy.

### 2.2. Destination và subscription inventory

Với mỗi queue/topic, ghi:

- Tên destination, loại queue/topic/temporary destination và owner nghiệp vụ.
- Producer/consumer count, enqueue/dequeue rate, backlog, message age.
- Durable subscription: client ID, subscription name, selector, noLocal, trạng thái offline.
- Virtual topic: tên topic, pattern Consumer.*.VirtualTopic.*, queue consumer và selector.
- Wildcard subscription, composite destination, destination options và routing policy.
- Message priority, expiration/TTL, scheduled/delayed delivery, group ID, correlation ID.
- DLQ/expiry destination và chính sách redelivery.
- Message size trung vị/p95/p99, payload type và tỷ lệ large message.
- Thời gian lưu message, retention, backlog tối đa và RPO.

Không chỉ inventory destination đang có message. Queue rỗng nhưng được ứng dụng tạo động vẫn có thể xuất hiện sau cutover; kết hợp broker management, config, application source/config và log traffic.

### 2.3. Message contract và transaction

Thu thập mẫu message đã loại bỏ dữ liệu nhạy cảm và ghi lại:

| Thuộc tính | Cần xác minh |
|---|---|
| Body | TextMessage, BytesMessage, MapMessage, ObjectMessage hay custom payload |
| Headers | JMSCorrelationID, JMSReplyTo, JMSType, JMSExpiration, JMSPriority |
| Properties | Kiểu dữ liệu, tên reserved, selector expressions |
| Delivery | Persistent/non-persistent, delivery delay, expiration |
| Transaction | Local JMS transaction, XA, DB transaction phối hợp |
| Retry | Redelivery count, delay, exponential backoff, DLQ |
| Ordering | FIFO theo queue, message groups, priority, concurrent consumers |
| Idempotency | Event ID/business key, inbox/outbox, duplicate detection |

JMSMessageID do broker tạo không phải khóa nghiệp vụ ổn định để đối soát xuyên broker. Dùng eventId do producer tạo và lưu trong message property/body.

### 2.4. Đo baseline có thể so sánh

Ghi baseline trong một chu kỳ tải đại diện:

- Producer send rate và send latency.
- Consumer delivery/ack rate và business processing latency.
- Queue depth, in-flight, oldest message age và DLQ arrival.
- Broker CPU, heap, GC pause, disk latency, store usage và network.
- Connection/session/consumer count, reconnect và exception rate.
- Kết quả giao dịch nghiệp vụ, duplicate rate và retry rate.

Dùng cùng dataset, message size, persistence, consumer concurrency và test duration khi so sánh target. Nếu đổi đồng thời broker, client, JVM và schema payload, khó xác định yếu tố gây regression.

## 3. Những khác biệt kiến trúc ảnh hưởng migration

### 3.1. Message store không tương thích trực tiếp

Classic KahaDB có journal và index riêng. Artemis dùng message journal cùng các cơ chế bindings, paging và large-message storage. Hai định dạng store **không thể thay thế trực tiếp cho nhau**.

- Không copy thư mục KahaDB sang Artemis journal.
- Không trỏ Artemis vào JDBC schema của Classic rồi kỳ vọng đọc được message.
- Không mở cùng store writable bằng hai broker process.
- Không coi việc Artemis accept OpenWire là bằng chứng message store đã migrate.

Với KahaDB/mKahaDB, có công cụ export của Apache ActiveMQ CLI Tools chuyển message store sang XML format mà Artemis có thể import. Với backend khác hoặc yêu cầu đặc thù, dùng quy trình export/import hoặc relay qua client/protocol, rồi đối soát.

### 3.2. Addressing và routing model

Classic coi queue, topic và durable subscription là destination first-class. Artemis lưu queue và dùng **address + routing type** để điều phối:

- **Anycast:** mô hình point-to-point; message được định tuyến tới một queue.
- **Multicast:** mô hình publish/subscribe; message được định tuyến tới các subscription queues phù hợp.

Mapping khái quát:

| Classic | Artemis concept |
|---|---|
| JMS Queue orders.new | Address orders.new + anycast queue |
| JMS Topic orders.events | Address orders.events + multicast subscriptions |
| Durable topic subscription | Queue gắn với multicast address |
| Virtual topic consumer queue | Subscription queue/FQQN hoặc OpenWire virtual-topic mapping |
| Destination policy | address-settings, queue/address configuration |
| DLQ/expiry policy | Dead-letter-address và expiry-address/settings |

Không chỉ đổi tên queue thành address. Phải xác định routing type, queue binding, subscription ownership, auto-create/auto-delete, selector filter và security permission.

### 3.3. Paging và flow control

Hai broker xử lý backlog vượt bộ nhớ theo cách khác nhau. Classic dùng cursor/store strategy để quản lý message sẵn sàng dispatch; Artemis dùng journal và paging theo address. Vì vậy cần đánh giá lại:

- Memory limit, page size, max-size-bytes và address full policy.
- Producer flow control/blocking behavior.
- Consumer prefetch/window size và dispatch batching.
- Disk capacity, journal file size, paging directory và large-message directory.
- Message age khi paging, recovery time sau restart và tốc độ depaging.

Không sao chép một giá trị memory limit hoặc cursor policy từ Classic sang Artemis rồi coi là tương đương.

### 3.4. OpenWire giúp giữ client, không bảo đảm parity tuyệt đối

Artemis hỗ trợ OpenWire để ActiveMQ Classic JMS client có thể kết nối trực tiếp. Tài liệu Artemis nêu OpenWire JMS client library từ ActiveMQ 5.12.x trở lên có thể sử dụng với Artemis; broker cần acceptor bật OpenWire.

Điều này giúp migration theo giai đoạn:

1. Giữ client OpenWire để giảm thay đổi ứng dụng trong lần cutover đầu.
2. Chạy compatibility suite cho từng client version và feature đang dùng.
3. Sau khi broker migration ổn định, quyết định có chuyển ứng dụng sang Artemis Core JMS/Jakarta Messaging hoặc AMQP hay không.

OpenWire là **compatibility path**, không phải cam kết mọi plugin, advisory, destination option hoặc behavior của Classic được thực hiện giống hệt. Tài liệu Artemis cũng nêu rõ không đặt mục tiêu tái triển khai 100% mọi tính năng Classic.

### 3.5. JMS và Jakarta Messaging là API, không phải wire protocol

JMS/Jakarta Messaging định nghĩa API lập trình; chúng không tự định nghĩa giao thức truyền mạng. Một client dùng javax.jms và client dùng jakarta.jms có thể không tương thích binary/classpath dù cùng khái niệm JMS.

- Spring Boot 2 và ứng dụng Java EE cũ thường dùng javax.jms.
- Spring Boot 3 dùng jakarta.jms.
- Classic OpenWire client cũ thường xây dựng trên javax.jms; xác minh version/client artifact khi ứng dụng đã chuyển sang Jakarta.
- Artemis cung cấp client/API phù hợp với các thế hệ Jakarta Messaging tương ứng.

Không đổi import hàng loạt từ javax sang jakarta rồi coi migration hoàn tất. Chọn đúng client library, dependency tree, framework version và broker protocol.

## 4. Ma trận tương thích phải kiểm tra

Dùng bảng này làm checklist cho từng workload; trạng thái cuối cùng phải đến từ test trên đúng version/client/configuration.

| Tính năng | Điểm cần kiểm chứng trên Artemis |
|---|---|
| Queue send/receive | Destination mapping, auto-create, routing anycast |
| Topic publish/subscribe | Multicast address và queue per subscription |
| Durable subscription | Client ID, subscription name, offline backlog |
| Virtual topic | FQQN hoặc virtualTopicConsumerWildcards cho OpenWire |
| Selector | Property type, syntax, wildcard và filter semantics |
| Message groups | JMSXGroupID, ordering và consumer ownership |
| Exclusive/priority consumer | Consumer priority, exclusive behavior và dispatch |
| Scheduled message | Scheduled delivery header/property mapping |
| Expiration | TTL, expiry-address và expiry handling |
| Redelivery | Delivery count, delay, retry policy và DLQ |
| Advisory | OpenWire advisory compatibility và management notifications |
| Composite destination | Mapping sang diverts/address routing nếu cần |
| Temporary queue/topic | Lifecycle, connection ownership và reply-to |
| ObjectMessage | Java serialization, class allowlist và compatibility |
| XA | Transaction manager, recovery, resource identity và crash test |
| Network of Brokers | Thiết kế lại bằng Artemis clustering/federation hoặc bridge phù hợp |
| JMX/metrics | MBean names, metrics names, dashboards và automation |
| Security | User/role, address permissions, TLS, LDAP/JAAS integration |
| Client reconnect | Failover URI, reconnect timing và in-flight behavior |

### 4.1. Virtual Topic cần kiểm thử riêng

Ví dụ Classic:

- Publisher gửi tới topic VirtualTopic.Orders.
- Consumer A đọc queue Consumer.A.VirtualTopic.Orders.
- Consumer B đọc queue Consumer.B.VirtualTopic.Orders.

Trong Artemis, có thể biểu diễn consumer subscription bằng queue gắn với multicast address hoặc dùng FQQN. Ví dụ queue subscription A:

```java
Queue subscriptionQueue =
    session.createQueue(
        "VirtualTopic.Orders::Consumer.A.VirtualTopic.Orders");
MessageConsumer consumer =
    session.createConsumer(subscriptionQueue);
```

Nếu chưa thể sửa OpenWire clients, Artemis có cấu hình virtualTopicConsumerWildcards để chuyển destination Classic sang FQQN. Với prefix mặc định Consumer.*., ví dụ acceptor:

```xml
<acceptors>
  <acceptor name="openwire">
    tcp://0.0.0.0:61616?protocols=OPENWIRE;virtualTopicConsumerWildcards=Consumer.*.%3E%3B2
  </acceptor>
</acceptors>
```

Giá trị > và ; được URL-encode thành %3E và %3B. Mapping trên là ví dụ cho naming convention mặc định; nếu ứng dụng dùng prefix/path khác, phải tính lại filter và số segment. Kiểm thử consumer destination thực tế, selector, offline backlog và behavior khi reconnect.

## 5. Lựa chọn chiến lược chuyển đổi

Không có một đường migration phù hợp cho mọi workload. Chọn theo data volume, yêu cầu downtime, persistence adapter, số client và mức chấp nhận duplicate.

| Chiến lược | Cách thực hiện | Phù hợp | Giới hạn |
|---|---|---|---|
| **Stop-the-world + export/import** | Dừng nguồn, export dữ liệu, import target, đổi endpoint | Cần chuyển pending messages, chấp nhận maintenance window | Downtime phụ thuộc volume/import |
| **OpenWire cutover** | Cấu hình Artemis OpenWire, đổi broker endpoint, giữ Classic clients | Muốn thay broker trước, giảm thay đổi client | Phải test feature parity và client version |
| **Application relay** | Consumer đọc Classic, producer gửi Artemis, đối soát event ID | Store không được tool export hỗ trợ hoặc cần chuyển dần | Duplicate tại ranh giới hai broker |
| **Protocol bridge/federation** | Dùng bridge/federation phù hợp để chuyển tiếp | Cần chuyển luồng trong giai đoạn chuyển đổi | Phải quản lý routing, loops, duplicate và ownership |
| **Blue-green theo domain** | Chuyển từng nhóm destination/service | Hệ thống lớn, có thể phân vùng ownership | Cần mapping và quan sát theo nhóm |
| **Client migration sau broker migration** | Giữ OpenWire trước, chuyển dần sang Artemis-native/AMQP | Hiện đại hóa nhiều đợt | Duy trì nhiều client stack trong giai đoạn chuyển |

**Không dual-write cùng một event vào hai broker mà không có idempotency và reconciliation.** Hai send không nằm trong cùng transaction nguyên tử: một broker có thể commit còn broker kia lỗi. Nếu cần fan-out, dùng outbox/relay có trạng thái và event ID ổn định.

### 5.1. Chọn phương án theo persistence adapter

| Classic source | Phương án dữ liệu |
|---|---|
| KahaDB | Apache ActiveMQ CLI Tools export sang Artemis XML, sau đó artemis data imp |
| mKahaDB | CLI Tools có lệnh export mkahadb; kiểm tra mapping store/filter |
| JDBC persistence | KahaDB exporter không áp dụng trực tiếp; dùng relay/export được kiểm chứng cho backend |
| Memory store | Không có durable store để khôi phục; drain/relay nếu cần giữ message đang tồn tại |
| Custom store/plugin | Xác minh khả năng export của plugin hoặc viết adapter/relay có kiểm thử |

Công cụ KahaDB exporter chỉ xử lý KahaDB/mKahaDB. Không truyền đường dẫn JDBC schema vào --source của exporter rồi mong nhận XML hợp lệ.

## 6. Chuyển message từ KahaDB sang Artemis

### 6.1. Chuẩn bị

1. Clone broker nguồn và tạo môi trường Artemis target cô lập.
2. Xác định queue/topic cần chuyển và pattern lọc.
3. Backup KahaDB, cấu hình và security material.
4. Dừng broker nguồn sạch trước khi lấy bản store dùng để export; không chạy exporter trên store đang bị broker ghi.
5. Kiểm tra target đã có address/queue, routing type, security và address settings phù hợp.
6. Đảm bảo target không nhận producer/consumer nghiệp vụ trong lúc import thử.
7. Ghi manifest gồm backup ID, broker version, queue list, expected counts và event ID markers.

### 6.2. Export KahaDB

Apache ActiveMQ CLI Tools cung cấp export kahadb và export mkahadb, tạo XML format dùng cho Artemis import. Ví dụ export toàn bộ KahaDB:

```bash
./bin/export kahadb \
  --source /migration/source/kahadb \
  --target /migration/export/classic-store.xml
```

Export một tập queue theo pattern:

```bash
./bin/export kahadb \
  --source /migration/source/kahadb \
  --target /migration/export/orders-only.xml \
  --queuePattern 'orders.>'
```

Có thể dùng --topicPattern để lọc topic và --virtualTopicConsumerWildcards để map queue consumer của virtual topic sang durable subscription tương ứng. Xác minh cú pháp với ./bin/export help kahadb của đúng bản CLI Tools.

Export XML không tự tạo target broker đã cấu hình đầy đủ. Address/queue policy, security, expiry, DLQ, acceptor và plugin phải được chuẩn bị/kiểm thử riêng.

### 6.3. Import vào Artemis

Chạy import từ CLI của Artemis instance đã được tạo; target broker phải chạy và endpoint import được mở trong mạng migration:

```bash
./artemis data imp \
  --input /migration/export/classic-store.xml \
  --host artemis-target.internal \
  --port 61616 \
  --user migration_user \
  --password "$ARTEMIS_MIGRATION_PASSWORD"
```

Đặt credential qua secret manager hoặc biến môi trường của job; không ghi password trực tiếp vào script được commit. User migration cần quyền tạo/ghi queue/address mà import yêu cầu.

artemis data imp import XML vào broker Artemis đang chạy. Tùy chọn --transaction yêu cầu toàn bộ import nằm trong một transaction; cân nhắc kích thước dữ liệu và chi phí giữ transaction trước khi bật. Với dữ liệu lớn, thử nghiệm commit behavior, thời gian import và khả năng chạy lại sau lỗi trên staging.

### 6.4. Không nhầm các công cụ export/import

| Lệnh/công cụ | Nguồn dữ liệu | Mục tiêu |
|---|---|---|
| activemq-cli-tools export kahadb | Classic KahaDB | Tạo XML format có thể import vào Artemis |
| activemq-cli-tools export mkahadb | Classic MultiKahaDB | Tạo XML format có thể import vào Artemis |
| artemis data exp | Artemis store | Export message data của Artemis ra XML |
| artemis data imp | XML migration/import format | Import message vào Artemis target đang chạy |

artemis data exp không phải lệnh đọc trực tiếp KahaDB Classic. Khi migration KahaDB, dùng exporter chuyên dụng của Classic CLI Tools rồi import XML vào Artemis.

### 6.5. Đối soát sau import

- Queue/address và routing type có đúng mapping không?
- Tổng message theo từng destination có hợp lý không?
- Persistent/non-persistent, priority, expiration và timestamp có đúng contract không?
- Body/properties/header còn đúng kiểu dữ liệu không?
- Virtual topic consumer queues có map đúng durable subscriptions không?
- Message có selector filter có tiếp tục được consumer mong đợi nhận không?
- DLQ/expiry destination có đúng không?
- Message groups và thứ tự có đáp ứng contract không?
- Consumer đã xử lý message trước snapshot có bị phát lại không?
- Event ID bị thiếu/trùng được ghi nhận thế nào?

Queue count bằng nhau không đủ chứng minh dữ liệu tương đương. So sánh tập event ID hoặc hash/manifest theo từng destination; với payload nhạy cảm, dùng hash/metadata thay vì lưu raw body vào báo cáo.

## 7. Relay qua ứng dụng khi không export trực tiếp

Với JDBC store hoặc backend đặc thù, có thể viết relay dùng JMS client để đọc Classic và gửi sang Artemis. Hai broker không chia sẻ một transaction.

### 7.1. Nguyên tắc at-least-once

1. Tạo source consumer trong transacted session.
2. Nhận message từ Classic.
3. Chuyển body, headers và allowlisted properties sang message mới.
4. Gửi message persistent vào Artemis trong target transacted session.
5. Commit target session.
6. Chỉ sau khi target commit thành công mới commit source session để ACK message nguồn.
7. Ghi event ID, source destination, target destination và trạng thái relay vào audit store.

Nếu target đã commit nhưng process chết trước khi source ACK, message nguồn được giao lại và relay có thể gửi duplicate sang Artemis. Cần duplicate detection/idempotency ở target hoặc consumer nghiệp vụ. Nếu source ACK trước target send/commit, lỗi target có thể làm mất message.

### 7.2. Mã giả relay

```java
while (running) {
    Message sourceMessage = sourceConsumer.receive(timeout);

    if (sourceMessage == null) {
        continue;
    }

    String eventId = readStableEventId(sourceMessage);

    try {
        Message targetMessage = copyAllowedFields(
            sourceMessage, targetSession);

        targetMessage.setStringProperty("migrationEventId", eventId);
        targetProducer.send(targetMessage);

        targetSession.commit();  // Target đã nhận bền vững.
        sourceSession.commit();  // Chỉ sau target commit mới ACK source.

        audit.recordForwarded(eventId);
    } catch (Exception failure) {
        rollbackQuietly(targetSession);
        rollbackQuietly(sourceSession);
        audit.recordRetry(eventId, failure);
        backoff();
    }
}
```

Đây là pseudocode, không phải lớp Java compile trực tiếp. Implementation phải xử lý connection loss với **outcome unknown**: target commit có thể thành công nhưng client không nhận được response. Cần event ID ổn định và duplicate detection.

### 7.3. Không copy mù quáng mọi header

Không cố giữ nguyên provider-specific header như JMSMessageID, JMSDestination hoặc internal broker property. Broker đích sẽ cấp message ID/destination mới. Chọn allowlist gồm:

- eventId, correlationId, business type/version.
- JMSCorrelationID, JMSReplyTo sau khi ánh xạ destination.
- JMSPriority, expiration/TTL theo quy tắc chuyển đổi.
- Application properties có kiểu dữ liệu được hỗ trợ.
- Body bytes/text hoặc serialized payload theo schema contract.

Nếu source dùng ObjectMessage, kiểm tra Java class compatibility và deserialization policy. Không bật deserialization unrestricted chỉ để migration pass.

## 8. Cấu hình Artemis target cho OpenWire

### 8.1. Bật OpenWire acceptor

Trong broker.xml của Artemis target, cấu hình acceptor:

```xml
<acceptors>
  <acceptor name="openwire">
    tcp://0.0.0.0:61616?protocols=OPENWIRE
  </acceptor>
</acceptors>
```

Đây là fragment trong core configuration của broker; nếu file đã có acceptors, hợp nhất vào phần hiện hữu. Không mở port ra mọi network interface nếu không cần; dùng firewall, TLS và network policy.

### 8.2. Queue anycast và topic multicast

Ví dụ address/queue anycast cho đơn hàng:

```xml
<addresses>
  <address name="orders.new">
    <anycast>
      <queue name="orders.new"/>
    </anycast>
  </address>
</addresses>
```

Ví dụ multicast address với subscription queues:

```xml
<addresses>
  <address name="orders.events">
    <multicast>
      <queue name="Consumer.A.orders.events"/>
      <queue name="Consumer.B.orders.events"/>
    </multicast>
  </address>
</addresses>
```

Các fragment cần tích hợp vào core trong broker.xml; không tạo hai khối addresses trùng nhau. Với durable subscriptions được tạo tự động qua JMS, policy auto-create và queue naming phải được kiểm thử thay vì tạo binding thủ công không cần thiết.

### 8.3. Address settings cho DLQ và expiry

Ví dụ address setting cho nhóm queue orders:

```xml
<address-settings>
  <address-setting match="orders.#">
    <dead-letter-address>DLQ</dead-letter-address>
    <expiry-address>ExpiryQueue</expiry-address>
    <max-delivery-attempts>5</max-delivery-attempts>
    <redelivery-delay>1000</redelivery-delay>
    <max-size-bytes>104857600</max-size-bytes>
    <address-full-policy>PAGE</address-full-policy>
  </address-setting>
</address-settings>
```

Các ngưỡng là giá trị lab, không phải production recommendation. Phải provision address/queue DLQ và ExpiryQueue, xác minh security permission và test retry/expiry. Mapping DLQ của Classic có thể là individual DLQ theo destination; một address setting chung có thể không tái tạo đúng chính sách cũ.

### 8.4. Mapping virtual topic cho OpenWire

Nếu Classic dùng consumer queue mặc định Consumer.*.VirtualTopic.*, thêm tham số mapping vào OpenWire acceptor:

```xml
<acceptors>
  <acceptor name="openwire">
    tcp://0.0.0.0:61616?protocols=OPENWIRE;virtualTopicConsumerWildcards=Consumer.*.%3E%3B2
  </acceptor>
</acceptors>
```

Giá trị > và ; được URL-encode thành %3E và %3B. Mapping trên là ví dụ cho naming convention mặc định; nếu ứng dụng dùng prefix/path khác, phải tính lại filter và số segment.

## 9. Kiểm tra client OpenWire trước khi đổi endpoint

Một smoke test xác nhận Classic client tạo connection/session với Artemis acceptor. Ví dụ dùng ActiveMQ Classic client trên namespace javax.jms; dependency phải khớp ứng dụng hiện hữu.

### 9.1. Maven dependency cho probe

```xml
<dependency>
  <groupId>org.apache.activemq</groupId>
  <artifactId>activemq-client</artifactId>
  <version>5.18.5</version>
</dependency>
```

Version là ví dụ để minh họa Classic OpenWire client; trong migration thật, dùng đúng client version production và thêm các version khác vào compatibility matrix. Không nâng client cùng lúc nếu muốn tách rủi ro broker migration.

### 9.2. Java probe gửi và nhận qua Artemis

```java
import javax.jms.Connection;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;

import org.apache.activemq.ActiveMQConnectionFactory;

public final class OpenWireCompatibilityProbe {

    public static void main(String[] args) throws Exception {
        String brokerUrl = args.length > 0
            ? args[0]
            : "tcp://artemis-target.internal:61616";

        String user = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(brokerUrl);

        try (Connection connection =
                 user == null
                    ? factory.createConnection()
                    : factory.createConnection(user, password)) {

            Session session = connection.createSession(
                true, Session.SESSION_TRANSACTED);

            try {
                Queue queue = session.createQueue("orders.new");
                MessageProducer producer = session.createProducer(queue);
                MessageConsumer consumer = session.createConsumer(queue);

                connection.start();

                TextMessage sent = session.createTextMessage(
                    "migration-probe");
                sent.setStringProperty(
                    "eventId", "migration-probe-0001");

                producer.send(sent);
                session.commit();

                Message received = consumer.receive(5000L);
                if (!(received instanceof TextMessage)) {
                    throw new IllegalStateException(
                        "Expected a TextMessage from Artemis");
                }

                TextMessage text = (TextMessage) received;
                if (!"migration-probe".equals(text.getText())) {
                    throw new IllegalStateException("Unexpected body");
                }

                if (!"migration-probe-0001".equals(
                        text.getStringProperty("eventId"))) {
                    throw new IllegalStateException("Missing eventId");
                }

                session.commit();
                producer.close();
                consumer.close();
            } catch (Exception failure) {
                session.rollback();
                throw failure;
            } finally {
                session.close();
            }
        }
    }
}
```

Probe kiểm tra OpenWire connection, send/receive, property và local JMS transaction cơ bản. Nó **không** chứng minh virtual topic, XA, advisory, scheduled message, DLQ, selector, ordering hoặc failover tương thích. Mỗi feature cần test riêng.

Nếu dùng javax.jms client này với ứng dụng Spring Boot 3/Jakarta, hãy tách probe/module hoặc dùng client/API tương thích; không đưa hai namespace vào cùng dependency graph chỉ để chạy thử.

## 10. Kiểm thử migration theo contract nghiệp vụ

### 10.1. Test matrix tối thiểu

| Nhóm | Ca thử | Tiêu chí đạt |
|---|---|---|
| Queue | Persistent send/receive, competing consumers | Không mất event, phân phối đúng contract |
| Topic | Nhiều subscribers, durable/offline subscriber | Mỗi subscription nhận đúng số event |
| Virtual topic | Consumer A/B, offline backlog, selector | Mapping và queue ownership đúng |
| Header/property | Priority, correlation ID, custom properties | Kiểu dữ liệu và giá trị được giữ theo contract |
| Transaction | Commit, rollback, crash giữa send/ACK | Không mất event; duplicate được xử lý |
| Redelivery | Retry, delay, max attempts | Delivery count và DLQ đúng |
| Expiry | TTL hết hạn, expiry address | Message hết hạn đi đúng đích |
| Ordering | Message group, concurrent consumers | Thứ tự trong phạm vi đã cam kết |
| Scheduled | Delay/delivery time | Message không tới sớm/muộn ngoài SLA |
| Large message | Payload lớn và disk pressure | Body đọc được, store/page không lỗi |
| Security | User/role, send/consume, TLS | Quyền đúng và không mở rộng ngoài ý muốn |
| HA/failover | Kill active, restart, reconnect | RTO/RPO trong ngưỡng |
| Load | Peak rate, burst, sustained backlog | Latency/throughput đạt baseline/SLO |
| Operations | JMX/metrics/log/alerts/backup | Runbook hoạt động trên target |

### 10.2. So sánh với baseline

Ghi cùng phép đo trên Classic và Artemis:

- Throughput producer và consumer ở cùng tải.
- p50/p95/p99 send latency và business processing latency.
- Queue backlog và oldest message age.
- CPU, heap, GC, disk write latency, store usage, paging.
- Consumer prefetch/window, in-flight và redelivery rate.
- Event ID reconciliation: missing, duplicate, unexpected.
- Reconnect, exception và thời gian recovery.

Target có throughput cao hơn nhưng DLQ tăng, ordering sai hoặc p99 latency vượt SLA vẫn là migration thất bại.

## 11. Cutover theo giai đoạn

### 11.1. Giai đoạn 1 — Chuẩn bị target

- Tạo Artemis broker/HA topology độc lập.
- Cấu hình acceptor/protocol, address/queue, security, TLS, DLQ/expiry, paging và resource limits.
- Cài metrics, alert, backup và log routing.
- Kiểm tra client OpenWire với đúng version.
- Chạy test matrix trên staging.

### 11.2. Giai đoạn 2 — Chạy thử dữ liệu

- Clone dữ liệu Classic hoặc tạo dataset có event IDs đã biết.
- Export/import hoặc chạy relay theo phương án đã chọn.
- So sánh counts và event ID sets.
- Test selector, durable subscriptions, virtual topics và message properties.
- Chạy tải đại diện và fault injection.
- Ghi sai khác vào migration exception register.

### 11.3. Giai đoạn 3 — Quiesce nguồn và chốt điểm cắt

Với stop-the-world migration:

1. Thông báo maintenance và chặn producer theo kế hoạch.
2. Đợi producer transactions đang chạy kết thúc.
3. Dừng/đóng consumer theo trình tự để tránh xử lý song song hai broker.
4. Chờ in-flight và transaction được xử lý hoặc ghi nhận rõ.
5. Dừng Classic sạch và tạo snapshot/export cuối.
6. Ghi last confirmed event ID/time theo producer partition hoặc ledger.
7. Import phần dữ liệu cuối vào Artemis.
8. Đối soát event IDs, queue mapping, DLQ và subscription state.

Không chỉ đợi QueueSize=0: durable subscriber có thể offline, queue có thể chứa message đã lên lịch, và in-flight có thể redeliver sau restart.

### 11.4. Giai đoạn 4 — Đổi endpoint và mở traffic

- Cập nhật DNS/service discovery/config endpoint cho producer/consumer.
- Chuyển một nhóm workload có kiểm soát nếu hỗ trợ canary theo domain.
- Xác minh connection, auth/TLS, queue routing và metrics.
- Mở producer/consumer theo cutover design; không để consumer xử lý trước khi target import hoàn tất.
- Theo dõi backlog, oldest age, redelivery, DLQ và business commit.
- Ghi event ID đầu tiên/cuối cùng ở mỗi phía.

### 11.5. Giai đoạn 5 — Ổn định và đóng migration

- Giữ Classic ở trạng thái fenced/read-only hoặc dừng theo kế hoạch.
- Đối soát event, duplicate và business side effects.
- Theo dõi qua ít nhất một chu kỳ tải/retention quan trọng.
- Cập nhật runbook, dashboard, alert routing, backup/restore và service ownership.
- Chỉ giải phóng hạ tầng Classic sau rollback window và phê duyệt.

## 12. Rollback và xử lý duplicate/lost message

### 12.1. Rollback trước khi Artemis nhận traffic nghiệp vụ

Nếu target chưa nhận producer/consumer production và chưa tạo side effects:

- Dừng Artemis target.
- Giữ dữ liệu/metrics/log để điều tra.
- Trả endpoint về Classic.
- Khởi động Classic bằng store cũ/snapshot đã xác minh.
- Kiểm tra producer/consumer và backlog trước khi mở traffic.

Đây là rollback đơn giản nhất vì Classic vẫn là source of truth.

### 12.2. Rollback sau khi Artemis đã nhận traffic

Sau khi producer gửi message vào Artemis hoặc consumer đã commit DB từ message trên Artemis, không thể chỉ đổi endpoint về Classic. Cần:

1. Chặn producer/consumer có kiểm soát.
2. Xác định event IDs đã commit ở Artemis và side effects DB đã xảy ra.
3. Xác định message còn pending/in-flight/DLQ ở Artemis.
4. Chọn relay ngược sang Classic hoặc tiếp tục khắc phục trên Artemis.
5. Dùng idempotency/inbox để ngăn xử lý trùng.
6. Đối soát business database trước khi mở traffic ở broker quay về.

Không ghi message ngược về Classic bằng cách copy Artemis journal vào KahaDB. Relay ngược vẫn là chuyển message qua protocol/application boundary và có rủi ro duplicate.

### 12.3. Định nghĩa rollback gate trước cutover

| Gate | Điều kiện |
|---|---|
| **G0 — Pre-cutover** | Classic vẫn là source of truth; target chưa nhận production traffic |
| **G1 — Canary** | Một workload nhỏ đã chạy; event ID reconciliation và business DB đối soát được |
| **G2 — Partial cutover** | Nhiều domain đã chuyển; có route/ownership rõ để rollback từng domain |
| **G3 — Full cutover** | Artemis là source of truth; rollback cần replay/reconciliation và approval |
| **G4 — Rollback window closed** | Classic store/archive giữ theo retention; rollback chỉ qua DR/migration plan |

Xác định trước ai có quyền tuyên bố rollback, tiêu chí kích hoạt và giới hạn thời gian ra quyết định. Không tùy ý đổi DNS khi chưa biết broker nào đang sở hữu event mới nhất.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Copy KahaDB sang Artemis journal | Target không đọc được store | Dùng export/import hoặc relay |
| Nghĩ OpenWire đồng nghĩa feature parity | Advisory/virtual destination/options khác behavior | Compatibility test từng feature |
| Chỉ đổi endpoint | Queue/topic mapping hoặc security sai | Tạo mapping và test destination |
| Bỏ qua virtual topics | Consumer không nhận offline backlog | FQQN hoặc virtualTopicConsumerWildcards |
| Chuyển javax sang jakarta không kiểm dependency | API/classpath incompatibility | Tách client migration và broker migration |
| Dual-write hai broker không idempotency | Duplicate hoặc lệch dữ liệu | Outbox/relay và event ID |
| Source ACK trước target commit | Mất message khi target lỗi | Target commit trước source ACK; chấp nhận duplicate |
| Dùng queue count làm đối soát duy nhất | Bỏ sót duplicate/missing event | Reconcile event IDs/business ledger |
| Import khi consumer production đã chạy | Side effect trước khi import xong | Import trong isolation, mở consumer sau cutover gate |
| Giữ connector hai chiều tùy tiện | Loop/duplicate/ownership không rõ | Vẽ topology và xác định data ownership |
| Không test DLQ/expiry | Message lỗi bị xử lý sai | Test poison message, retry, expiry và redrive |
| Không thử rollback sau target writes | Không biết quay lại bằng cách nào | Diễn tập rollback trước/sau cutover |

## 14. Checklist nghiệm thu migration

### Đánh giá trước migration

- [ ] Đã chọn rõ Classic in-place upgrade hay Classic → Artemis.
- [ ] Đã inventory broker/client/JVM/plugin/protocol/persistence/topology.
- [ ] Đã thống kê queue/topic/durable/virtual topic và workload.
- [ ] Đã xác định JMS API namespace và client versions.
- [ ] Đã có mapping address, routing type, queue, selector, DLQ/expiry.
- [ ] Đã xác định store migration tool hoặc relay path.
- [ ] Đã có baseline throughput/latency/backlog/business success.
- [ ] Đã có backup/restore và rollback plan.

### Trước cutover

- [ ] Artemis acceptor/client OpenWire được test với version thực tế.
- [ ] Destination/security/TLS/HA/paging/flow control đã cấu hình.
- [ ] Export/import hoặc relay chạy thành công trên staging.
- [ ] Virtual topic, durable subscription, selectors, transactions, redelivery và DLQ đã test.
- [ ] Event ID reconciliation không có missing/duplicate chưa giải thích.
- [ ] Load/fault test đạt SLO.
- [ ] Monitoring, alert, backup, runbook và owner đã sẵn sàng.
- [ ] Rollback gates, decision owner và maintenance window được duyệt.

### Sau cutover

- [ ] Producer/consumer kết nối target đúng endpoint.
- [ ] Business commit và event throughput bình thường.
- [ ] Backlog/oldest age không tăng ngoài dự kiến.
- [ ] DLQ/expiry/redelivery không tăng bất thường.
- [ ] Không có duplicate/missing event chưa đối soát.
- [ ] TLS/security/authorization được xác minh.
- [ ] Backup target đã chạy và có restore evidence.
- [ ] Classic được fence/giữ theo rollback retention.
- [ ] Runbook và dashboard đã cập nhật.

## 15. Bài tập vận dụng

1. Một hệ thống Classic dùng KahaDB, virtual topics, OpenWire clients và nhiều durable subscriptions. Bạn sẽ chọn upgrade hay Artemis migration? Nêu dữ liệu cần inventory.
2. Vì sao Artemis nhận OpenWire client không có nghĩa KahaDB store có thể copy trực tiếp?
3. Một queue Classic được map sang Artemis address có multicast routing. Điều gì sai về semantics và sửa thế nào?
4. Một producer dùng Classic javax.jms, trong khi ứng dụng khác đã chuyển Spring Boot 3/Jakarta. Thiết kế test matrix và dependency separation ra sao?
5. Với KahaDB, mô tả export/import workflow và những điều phải kiểm tra sau import.
6. Với JDBC store không được exporter hỗ trợ, thiết kế relay at-least-once và giải thích crash window giữa target commit và source ACK.
7. Virtual topic consumer Consumer.A.VirtualTopic.Orders cần được ánh xạ thế nào trong Artemis? Khi nào dùng FQQN và khi nào dùng OpenWire wildcard mapping?
8. Sau cutover, Artemis xử lý một phần message nhưng p99 latency vượt SLO. Những bằng chứng nào cần thu thập trước quyết định rollback?
9. Vì sao không thể chỉ đổi DNS về Classic sau khi Artemis đã nhận message mới?
10. Đề xuất rollback gate và reconciliation plan cho migration nhiều domain, yêu cầu không mất business event và chấp nhận duplicate delivery có kiểm soát.

## 16. Tài liệu tham khảo

- [Apache ActiveMQ Artemis Migration Guide](https://artemis.apache.org/components/artemis/migration-documentation/): hướng dẫn chuyển ActiveMQ 5.x sang Artemis.
- [Key Differences from ActiveMQ 5](https://artemis.apache.org/components/artemis/migration-documentation/key-differences.html): khác biệt message store, paging và addressing/routing.
- [Message Store Migration](https://artemis.apache.org/components/artemis/migration-documentation/message-store.html): KahaDB/mKahaDB export sang Artemis XML.
- [Apache ActiveMQ CLI Tools](https://github.com/apache/activemq-cli-tools): lệnh export kahadb/export mkahadb và filter.
- [Artemis Data Tools](https://artemis.apache.org/components/artemis/documentation/latest/data-tools.html): artemis data exp và artemis data imp.
- [Artemis Protocols and Interoperability](https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html): OpenWire, AMQP, MQTT, STOMP và acceptors.
- [Artemis OpenWire](https://artemis.apache.org/components/artemis/documentation/latest/openwire.html): advisory, destination cache và virtual topic mapping.
- [Virtual Topics Migration](https://artemis.apache.org/components/artemis/migration-documentation/VirtualTopics.html): JMS shared subscriptions, FQQN và durable subscriber mapping.
- [Artemis Version History](https://artemis.apache.org/components/artemis/documentation/latest/versions.html): các bước nâng cấp theo từng release.

**Ghi nhớ:** Nâng cấp Classic và chuyển sang Artemis là hai dự án khác nhau. Upgrade giữ cùng broker family nhưng vẫn cần kiểm tra release notes, runtime và store; migration phải xử lý **message store không tương thích**, ánh xạ destination/routing, client OpenWire/JMS, virtual topic, transaction, DLQ và vận hành. Hãy chọn đường dữ liệu phù hợp với persistence adapter, kiểm thử theo business event ID, cutover theo ownership rõ ràng và chuẩn bị rollback trước khi Artemis nhận traffic production.
