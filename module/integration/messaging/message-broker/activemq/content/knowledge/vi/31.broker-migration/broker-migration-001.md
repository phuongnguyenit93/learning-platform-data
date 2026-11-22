# Kiểm kê destination, subscription, client, giao thức và tính năng đang dùng

> **Chương:** Di chuyển broker  
> **Phạm vi:** Lập baseline cho hệ thống đang chạy Apache ActiveMQ Classic trước khi đánh giá chuyển sang Apache Artemis. Công việc ở đây là **khám phá và ghi nhận hiện trạng có bằng chứng**: destination, subscription, client, giao thức, tính năng, lưu lượng và phụ thuộc vận hành. Một danh sách queue từ Web Console hoặc một bản cấu hình broker riêng lẻ không đủ mô tả toàn bộ hệ thống.

## 1. Mục tiêu kiểm kê và tiêu chí hoàn thành

Di chuyển broker thường vướng ở những phần không xuất hiện trong sơ đồ kiến trúc: durable subscriber cũ vẫn giữ backlog, ứng dụng batch dùng client ID cố định, bridge chỉ chạy khi DR hoạt động, consumer dựa vào Virtual Topic convention, hoặc client dùng transport đặc thù. Nếu chỉ đếm queue và topic, các phụ thuộc này dễ bị bỏ sót.

Baseline cần trả lời được:

1. **Destination nào đang tồn tại?** Queue, Topic, temporary destination, Virtual/Composite Destination, advisory, DLQ, expiry và destination được tạo động.
2. **Ai đang sử dụng chúng?** Producer, consumer, service owner, client ID, durable/shared subscription, selector, nhóm consumer và kết nối từ hệ thống ngoài.
3. **Dữ liệu và tải có đặc điểm gì?** Message count, tốc độ vào/ra, kích thước, persistent ratio, backlog, TTL, scheduled message, transaction và thời gian giữ dữ liệu.
4. **Client nói chuyện bằng gì?** OpenWire, AMQP, STOMP, MQTT, WebSocket, VM hoặc transport riêng; phiên bản thư viện, TLS, endpoint, reconnect và các tùy chọn client.
5. **Hệ thống đang phụ thuộc tính năng nào?** Virtual Topic, advisory, message group, prefetch, XA, network connector, flow control, scheduler, plugin, interceptor, paging và policy theo destination.
6. **Mục nào có thể chuyển nguyên trạng, mục nào cần thử nghiệm hoặc thiết kế lại?** Mỗi kết luận phải có nguồn bằng chứng, owner và mức độ tin cậy.

Kiểm kê hoàn tất khi có snapshot timestamp rõ ràng, bao phủ đủ cửa sổ tải đại diện, từng tài sản có owner hoặc trạng thái chưa rõ, tính năng quan trọng được xác nhận với application owner, và mọi khoảng trống đều có người chịu trách nhiệm. **Không dùng trạng thái “không thấy trong JMX” để kết luận “không được sử dụng”.**

## 2. Phạm vi và nguồn bằng chứng

### 2.1. Thu thập từ nhiều lớp

| Nguồn | Dữ liệu thu được | Giới hạn |
|---|---|---|
| Broker runtime / JMX / management API | Destination, connection, session, producer, consumer, subscription đang hiện diện; metrics và cấu hình runtime | Snapshot chỉ phản ánh thời điểm đọc; client offline hoặc destination đã GC có thể không xuất hiện |
| Cấu hình broker | Connector/acceptor, destination policy, address settings, security, plugin, bridge, persistence, HA | Có thể khác cấu hình thực tế nếu file không phải file broker đang chạy |
| Cấu hình ứng dụng / secret reference | URL, protocol, destination name, client ID, prefetch, ACK, transaction, TLS, reconnect | Có thể bị override bằng biến môi trường hoặc cấu hình runtime |
| Source code / dependency manifest | API tạo destination, selectors, message properties, custom converter, client library/version | Không chứng minh code path đang chạy hoặc tần suất sử dụng |
| Log / metrics / tracing | Hoạt động theo thời gian, lỗi producer/consumer, destination động, retry, DLQ, connection churn | Log có thể thiếu, sampling hoặc đã hết retention |
| Application owner / vận hành | Mục đích nghiệp vụ, criticality, SLA, DR, replay, cửa sổ bảo trì | Cần đối chiếu với bằng chứng kỹ thuật |
| Network / firewall / DNS / load balancer | Endpoint, port, NAT, route, allowlist, TLS termination | Không cho biết semantics JMS hoặc destination bên trong broker |

**Dùng cửa sổ quan sát đủ dài.** Một snapshot trong giờ thấp điểm không phát hiện consumer chỉ chạy cuối ngày, lịch batch cuối tháng hoặc kết nối DR chỉ mở khi diễn tập. Chọn cửa sổ tối thiểu bao phủ chu kỳ nghiệp vụ quan trọng; nếu có batch tuần/tháng thì phải quan sát hoặc lấy log đủ dài để thấy chu kỳ đó.

### 2.2. Phân biệt “đã cấu hình”, “đang hoạt động” và “được nghiệp vụ sử dụng”

Một destination có thể:

- Được khai báo trong XML nhưng chưa từng có producer/consumer.
- Được tạo tự động khi client kết nối nhưng chỉ là tên sai do typo.
- Không có consumer tại thời điểm snapshot nhưng vẫn chứa durable backlog.
- Có connection hiện tại nhưng không phát sinh message trong cửa sổ quan sát.
- Có message được gửi vào nhưng ứng dụng không còn owner hoặc không có quy trình xử lý.

Ghi trạng thái theo từng chiều:

| Trạng thái | Ý nghĩa |
|---|---|
| CONFIGURED | Tìm thấy trong cấu hình hoặc deployment manifest |
| OBSERVED_ACTIVE | Có producer/consumer/traffic trong snapshot hoặc cửa sổ quan sát |
| OBSERVED_IDLE | Tồn tại nhưng không thấy traffic trong cửa sổ đã ghi |
| PERSISTED_BACKLOG | Có message hoặc durable subscription backlog |
| OWNER_CONFIRMED | Application owner xác nhận mục đích và trách nhiệm |
| CANDIDATE_UNUSED | Có bằng chứng chưa sử dụng, nhưng chưa được phê duyệt xóa |
| UNKNOWN | Chưa đủ dữ liệu để kết luận |

Không tự động xóa CANDIDATE_UNUSED. Destination có thể được dùng theo lịch, trong DR hoặc bởi client bên ngoài chưa được đưa vào danh sách.

## 3. Lập danh mục broker và topology

Mỗi broker instance cần một bản ghi riêng, kể cả các node trong cùng HA pair hoặc network of brokers.

| Nhóm trường | Trường cần ghi |
|---|---|
| Nhận diện | brokerId, brokerName, product, version/build, hostname, environment, region/zone, owner |
| Topology | Standalone/HA/cluster/network of brokers, primary/backup, node ID, failover endpoint, bridge/federation peer |
| Storage | Persistence adapter, data directory, KahaDB/mKahaDB/JDBC, database/schema, volume type, dung lượng và mức sử dụng |
| Capacity | CPU/RAM limit, memory/store/temp limit, disk IOPS/latency, connection limit, message size limit |
| Runtime | Uptime, current connections, producer/consumer counts, enqueue/dequeue rate, backlog, paging/store pressure |
| Security | Authentication source, authorization plugin, user/role mapping, TLS/mTLS, certificate owner/expiry, secret reference |
| Operations | Startup config path, service/container identity, monitoring endpoint, log location, backup/restore owner, maintenance window |

Với Classic, ghi rõ broker dùng KahaDB, mKahaDB, JDBC hay persistence adapter khác. Với Artemis đích, storage là journal/paging model riêng; **KahaDB và Artemis journal không phải hai định dạng có thể thay thư mục dữ liệu trực tiếp cho nhau**. Vì vậy dung lượng store, số message, backlog và yêu cầu giữ dữ liệu phải được kiểm kê trước khi chọn export/import hoặc chuyển message qua wire.

### 3.1. Ghi connector/acceptor đang chạy

Classic thường khai báo transport connectors trong cấu hình broker. Ví dụ:

~~~xml
<transportConnectors>
    <transportConnector name="openwire"
        uri="tcp://0.0.0.0:61616"/>
    <transportConnector name="amqp"
        uri="amqp://0.0.0.0:5672"/>
    <transportConnector name="stomp"
        uri="stomp://0.0.0.0:61613"/>
    <transportConnector name="mqtt"
        uri="mqtt://0.0.0.0:1883"/>
</transportConnectors>
~~~

Đây là ví dụ minh họa các loại connector, **không phải cấu hình đề nghị thay vào production**. Thu thập cả connector trong runtime, URI sau khi resolve property, port thực sự listen và cấu hình load balancer/firewall. Một transport connector có thể có TLS, maximum connections, frame size, wire format, inactivity timeout và các option khác làm thay đổi khả năng tương thích.

Artemis dùng acceptors trong cấu hình broker; một Netty acceptor có thể nhận nhiều protocol nếu được cho phép:

~~~xml
<acceptors>
    <acceptor name="legacy-openwire">
        tcp://0.0.0.0:61616?protocols=OPENWIRE
    </acceptor>
    <acceptor name="amqp">
        tcp://0.0.0.0:5672?protocols=AMQP
    </acceptor>
</acceptors>
~~~

Trong XML thực tế, URI acceptor thường đặt trên một dòng hoặc trong CDATA theo cách cấu hình broker hỗ trợ. Đừng suy luận port 61616 luôn chỉ là OpenWire: Artemis có thể cấu hình một acceptor hỗ trợ nhiều protocol. Ghi danh sách protocol được phép của từng acceptor.

## 4. Kiểm kê destination

### 4.1. Những loại destination phải tìm

| Loại | Ví dụ/đặc điểm | Vì sao quan trọng |
|---|---|---|
| Queue tĩnh | orders.work | Công việc point-to-point, competing consumers |
| Queue động | Tạo khi client yêu cầu hoặc qua auto-create | Có thể phát sinh từ tenant, phiên bản ứng dụng hoặc typo |
| Topic | orders.events | Fan-out tới từng subscription |
| Durable Topic subscription | clientID + subscription name (JMS 1.1) | Giữ backlog khi subscriber offline; cần map identity khi chuyển đổi |
| Shared durable subscription | Nhiều consumer cùng subscription | Cần xác nhận client API/provider hỗ trợ và cách scale |
| Temporary Queue/Topic | Request/reply, reply-to | Có vòng đời gắn với connection; không được coi như queue tĩnh |
| Virtual Topic / Virtual Destination | VirtualTopic.Orders, consumer queues | Có quy ước tên và routing khác queue/topic thuần |
| Composite destination | Một tên logic route tới nhiều destination | Một send có thể tạo nhiều bản hoặc fan-out |
| Advisory destination | ActiveMQ.Advisory.* | Ứng dụng có thể subscribe sự kiện broker/connection/consumer |
| DLQ / expiry | ActiveMQ.DLQ, expiry destination hoặc per-queue DLQ | Chứa dữ liệu cần replay/đối soát, có thể có policy riêng |
| Scheduled destination/message | Message có scheduled delivery property | Lịch giao có thể ảnh hưởng thời điểm cutover |
| Destination do bridge tạo | Queue/topic phục vụ network connector | Có thể chứa bản sao hoặc demand từ broker khác |

Đối với Classic, liệt kê cả Queue, Topic, temporary queue/topic, durable subscriber active và inactive. Đối với Artemis, cần ghi **address và queue binding** riêng: một address có thể bind nhiều queue, queue có routing type ANYCAST hoặc MULTICAST, filter, durability, auto-created/auto-delete và thuộc tính riêng. Không coi một dòng queue trong Artemis luôn tương đương một dòng destination Classic.

### 4.2. Trường dữ liệu cho từng destination

Tạo một bản ghi cho mỗi destination vật lý, không chỉ mỗi tên logic:

| Trường | Mô tả |
|---|---|
| broker_id, environment | Broker và môi trường đang sở hữu |
| destination_name, destination_type | Tên vật lý và Queue/Topic/Temporary/Virtual/Advisory/DLQ |
| address_name, queue_name, routing_type | Trường tương ứng khi map sang Artemis |
| configured, auto_created, temporary, durable | Nguồn tạo và vòng đời |
| owner_service, business_owner, technical_owner | Hệ thống sở hữu và người chịu trách nhiệm |
| purpose, criticality, SLA | Ý nghĩa nghiệp vụ và độ quan trọng |
| producers, consumers, consumer_groups | Ứng dụng và nhóm sử dụng |
| selector, queue_filter, exclusive, max_consumers | Điều kiện nhận và giới hạn consumer |
| message_count, in_flight, enqueue_rate, dequeue_rate | Snapshot và xu hướng tải |
| average_size, max_size, oldest_age, persistent_ratio | Đặc điểm dữ liệu |
| TTL, scheduled, priority, message_group | Semantics giao message |
| DLQ, expiry, redelivery_policy | Đường đi khi lỗi/hết hạn |
| policy, memory_limit, store_usage, paging | Hành vi capacity |
| evidence, observed_at, confidence | Nguồn bằng chứng và thời điểm |

### 4.3. Ghi traffic theo cửa sổ, không chỉ một con số

Với queue/topic quan trọng, thu thập tối thiểu:

- Message count và in-flight tại nhiều thời điểm.
- Enqueue/dequeue rate theo giờ cao điểm, thấp điểm và chu kỳ batch.
- Average/p95/p99 message size nếu ứng dụng hoặc metrics có hỗ trợ.
- Persistent/non-persistent ratio.
- TTL/expiry count, scheduled count, DLQ rate.
- Consumer count, producer count, thời gian xử lý, redelivery.
- Backlog oldest age và thời gian để drain khi dừng producer.

Không browse toàn bộ body message chỉ để thống kê kích thước. Dùng metrics/metadata, log hoặc sample đã được phê duyệt; payload có thể chứa thông tin cá nhân, bí mật hoặc dữ liệu kinh doanh. Nếu chỉ có một snapshot QueueSize, không thể suy ra throughput hoặc backlog age.

## 5. Kiểm kê subscription và consumer identity

### 5.1. Durable subscription

Trong JMS 1.1, durable Topic subscription được nhận diện bằng cặp clientID và subscriptionName. Cặp này cần được ghi **chính xác**, gồm cả chữ hoa/thường nếu broker coi chúng là khác nhau. Với mỗi subscription, lưu:

- Topic/address nguồn.
- clientID, subscription name, client library/version.
- Selector và noLocal nếu có.
- Durable/shared hay non-durable; active/inactive.
- Consumer group/service owner và số replica.
- Backlog, last active time, expiry/retention, message count.
- Ai có quyền unsubscribe hoặc thay identity.

Đừng chỉ đếm số Topic. Một Topic có thể có nhiều durable subscription độc lập, mỗi subscription giữ một luồng backlog khác nhau. Trong Artemis, subscription queue là queue nội bộ gắn với address; khi migrate cần ánh xạ identity và backlog của từng subscriber.

### 5.2. Virtual Topic và consumer queue

Classic Virtual Topic thường dùng quy ước:

~~~text
Producer sends to: VirtualTopic.Orders

Consumer group Billing:
    Consumer.Billing.VirtualTopic.Orders

Consumer group Analytics:
    Consumer.Analytics.VirtualTopic.Orders
~~~

Mỗi consumer group đọc queue riêng để các replica trong cùng group cạnh tranh message, trong khi các group nhận bản độc lập. Kiểm kê phải ghi:

- Virtual Topic producer destination và interceptor/configuration liên quan.
- Prefix/wildcard consumer, ví dụ Consumer.*.
- Queue thực tế đã được tạo cho từng group.
- Selector-aware behavior nếu đang bật.
- Backlog và consumer count theo từng group.
- Network connector/bridge có thể forward cả Topic và consumer queues hay không.

Artemis có thể hỗ trợ mapping Virtual Topic qua OpenWire handler bằng virtualTopicConsumerWildcards, hoặc ứng dụng có thể dùng shared subscription/FQQN. Đây là **quyết định mapping cần kiểm thử**, không phải phép đổi tên cơ học. Ví dụ consumer queue Consumer.A.VirtualTopic.Orders có thể được ánh xạ thành FQQN VirtualTopic.Orders::Consumer.A.VirtualTopic.Orders khi cấu hình wildcard phù hợp.

### 5.3. Temporary destination và request/reply

Temporary destination thường không xuất hiện trong file cấu hình vì được tạo khi ứng dụng chạy. Tìm bằng:

- JMX/runtime destination MBeans trong nhiều thời điểm.
- Source code createTemporaryQueue() / createTemporaryTopic().
- Message property JMSReplyTo.
- Correlation ID, request timeout và client connection lifecycle.
- Log khi ứng dụng reconnect/restart.

Ghi nhận ứng dụng có giữ TemporaryQueue qua reconnect hay tạo lại mỗi request, reply consumer có sống cùng connection không, và có bridge/network connector cần forward temporary destination không. Không tự tạo durable queue thay thế temporary queue nếu chưa hiểu request/reply semantics.

## 6. Kiểm kê client, connection, producer và consumer

### 6.1. Client inventory

| Nhóm | Trường cần ghi |
|---|---|
| Danh tính | Service/application, module, team owner, môi trường, version triển khai |
| Client library | Artifact, version, javax.jms hay jakarta.jms, framework/Spring version |
| Kết nối | Broker URL, protocol, endpoint, DNS alias, load balancer, TLS/mTLS |
| Identity | clientID, username/role (không ghi password), certificate subject/alias |
| Producer | Destination, delivery mode, async/sync send, transaction, batch, compression |
| Consumer | Destination/subscription, selector, ACK mode, transacted/XA, prefetch/credit |
| Recovery | Failover/reconnect URL, retry interval, max attempts, connection timeout |
| Hành vi | Ordering/message group, idempotency, duplicate detection, TTL, priority, redelivery |
| Quan sát | Connection count, sessions, producers, consumers, remote address, last seen |

Một process có thể tạo nhiều JMS connection, mỗi connection có nhiều session, producer và consumer. Đừng quy connection count thành application instance count. Dùng clientID, username, remote address, session count, deployment metadata và log để nhóm đúng.

### 6.2. ActiveMQ Classic: nguồn JMX chỉ đọc

Classic thường đăng ký Broker MBean với ObjectName:

~~~text
org.apache.activemq:type=Broker,brokerName=<broker-name>
~~~

BrokerViewMBean cung cấp các method đọc danh mục:

| Method | Dữ liệu |
|---|---|
| getQueues() / getTopics() | ObjectName của queue/topic |
| getTemporaryQueues() / getTemporaryTopics() | Temporary destinations |
| getDurableTopicSubscribers() | Durable subscribers đang hoạt động |
| getInactiveDurableTopicSubscribers() | Durable subscribers hiện không active |
| getQueueSubscribers() / getTopicSubscribers() | Consumer/subscriber đang đăng ký |
| getQueueProducers() / getTopicProducers() | Producer đang gắn với destination |
| getTransportConnectors() | Connector và URI runtime |
| getCurrentConnectionsCount() / getUptimeMillis() | Trạng thái broker tổng quan |

Destination MBean có dạng:

~~~text
org.apache.activemq:type=Broker,brokerName=<broker-name>,destinationType=Queue,destinationName=<queue-name>
org.apache.activemq:type=Broker,brokerName=<broker-name>,destinationType=Topic,destinationName=<topic-name>
~~~

Đọc QueueSize, EnqueueCount, DequeueCount, ConsumerCount, InFlightCount, ExpiredCount và MemoryPercentUsage khi có. QueueSize là chỉ số queue; không áp dụng như backlog của mọi Topic subscription.

**Chỉ dùng getter/attribute khi kiểm kê.** Không gọi purge, removeQueue, removeTopic, destroyDurableSubscriber, resetStatistics, stop hoặc operation thay đổi trạng thái. Remote JMX không được bật mặc định trong nhiều cấu hình Classic; nếu cần remote access, dùng endpoint được bảo vệ và role chỉ đọc.

### 6.3. Artemis: management API và JMX

Artemis management API cung cấp các operation đọc hữu ích trên ActiveMQServerControl:

| Operation | Mục đích |
|---|---|
| getQueueNames() / listQueues(...) | Danh sách queue và metadata |
| listAddresses(...) | Address, routing type, queue count |
| listConnections(...) | Connection ID, protocol, client ID, remote/local address |
| listSessions(...) | Session, user, protocol, consumer/producer count |
| listConsumers(...) | Consumer, queue/address, selector/filter, protocol, client ID |
| listProducers(...) | Producer, address/destination, protocol, client ID |
| getVersion() / broker attributes | Phiên bản và thông tin server |

MBean server thường có domain org.apache.activemq.artemis. QueueControl ObjectName có dạng:

~~~text
org.apache.activemq.artemis:broker=<brokerName>,component=addresses,address="<address>",subcomponent=queues,routing-type="anycast",queue="<queue>"
~~~

Với multicast queue, routing-type tương ứng là multicast. ObjectName thực tế nên được tạo/đọc qua management API hoặc ObjectNameBuilder; cẩn thận escape tên address/queue chứa ký tự đặc biệt.

Các method listConnections, listQueues, listConsumers, listProducers có thể lọc theo protocol, address, queue, clientID, user hoặc remote address tùy operation. Ghi lại cả page/pageSize để tránh snapshot bị thiếu khi danh sách lớn.

Quyền view phù hợp cho truy vấn đọc; không cấp manage/edit chỉ để thu thập baseline. Management API cũng có các operation removeMessages, moveMessages, destroyQueue, pause, disable và reset counter; **không dùng chúng trong giai đoạn inventory**.

## 7. Kiểm kê giao thức và transport

### 7.1. Các protocol phải tìm

| Protocol/transport | Cần ghi | Điểm cần xác minh khi chuyển |
|---|---|---|
| OpenWire | Classic client version, wire format, transport URI, prefetch, failover, advisory | Artemis có OpenWire protocol handler; tương thích client không chứng minh mọi tính năng/hành vi giống Classic |
| AMQP | Version (thường AMQP 1.0), client library, link/settlement, address mapping | Artemis hỗ trợ AMQP 1.0; kiểm tra settlement, dynamic node, durable link và routing mapping |
| STOMP | Version 1.0/1.1/1.2, subscription header, ACK mode, destination prefix | Kiểm tra mapping queue/topic, receipt, ACK/NACK, virtual host và WebSocket |
| MQTT | 3.1/3.1.1/5.0, QoS, retained message, clean session/start, client ID | Phiên bản và semantics retained/session phải được test theo client/broker |
| WebSocket | STOMP/MQTT/AMQP client, path, proxy, TLS termination | Artemis Netty transport có thể xử lý WebSocket cho protocol được hỗ trợ; Classic connector riêng có thể cần đổi |
| VM/In-VM | Embedded broker, classloader, process boundary | Classic vm gắn OpenWire; Artemis InVM có mô hình transport khác |
| HTTP/OpenWire tunnel | URL, servlet/proxy, client option | Không mặc định có mapping một-một sang Artemis acceptor |
| Core | Protocol native của Artemis | Chỉ client Artemis Core dùng trực tiếp |

Artemis hỗ trợ Core, OpenWire, AMQP 1.0, MQTT và STOMP; protocol module và tham số protocols trên acceptor quyết định giao thức nào được bật. OpenWire client library của ActiveMQ 5.12.x trở lên có thể kết nối trực tiếp tới Artemis theo tài liệu OpenWire. Tuy vậy, hãy kiểm kê **đúng version thực tế** và kiểm thử các tính năng mà ứng dụng sử dụng.

### 7.2. Khác biệt connector/acceptor cần ghi thành mapping

| Classic | Artemis | Việc phải kiểm tra |
|---|---|---|
| OpenWire connector | Netty acceptor protocols=OPENWIRE | Frame size, inactivity timeout, reconnect, TLS |
| AMQP connector | Acceptor protocols=AMQP | AMQP 1.0 client và settlement |
| STOMP connector | Acceptor protocols=STOMP | Destination mapping và ACK semantics |
| MQTT connector | Acceptor protocols=MQTT | MQTT version, QoS, retained/session |
| vm:// | InVM transport | Embedded broker lifecycle và protocol |
| NIO transport riêng | Netty non-blocking transport | Không có lựa chọn TCP/NIO tương đương theo cùng cách |
| WebSocket connector | Netty TCP acceptor có WebSocket detection cho protocol phù hợp | Reverse proxy, path, TLS và protocol support |
| HTTP transport dựa trên OpenWire | Không có mapping trực tiếp tương đương trong migration guide | Thiết kế endpoint/client thay thế |

Ví dụ acceptor Artemis chỉ bật OpenWire:

~~~xml
<acceptors>
    <acceptor name="openwire">
        tcp://0.0.0.0:61616?protocols=OPENWIRE
    </acceptor>
</acceptors>
~~~

Không mở tất cả protocol trên cùng port chỉ vì dễ cấu hình. Chỉ bật protocol mà inventory xác nhận có client cần dùng; ghi rõ firewall, TLS, authentication và authorization theo từng endpoint.

### 7.3. API namespace và client library

JMS/Jakarta Messaging là API chuẩn, **không phải wire protocol**. Ghi rõ mỗi ứng dụng dùng:

- javax.jms (JMS 2.0 hoặc các phiên bản trước).
- jakarta.jms (Jakarta Messaging 3.0/3.1).
- ActiveMQ Classic client artifact/version.
- Artemis Core JMS/Jakarta client artifact/version.
- Spring JMS/JmsTemplate/listener container version và converter.
- Framework khác, JCA resource adapter hoặc application server module.

Giữ Classic OpenWire client trong giai đoạn đầu có thể giảm thay đổi ứng dụng, nhưng chuyển sang Artemis client/Jakarta API là một workstream riêng. Không nâng namespace hoặc thay client jar cùng lúc với cutover broker nếu chưa có ma trận kiểm thử tương thích.

## 8. Kiểm kê tính năng và semantics đang được ứng dụng phụ thuộc

Một tính năng “broker có hỗ trợ” chưa đủ. Cần ghi **ứng dụng nào dùng, dùng ở destination nào, cấu hình thực tế và cách xác minh**.

| Nhóm | Tính năng cần kiểm kê | Bằng chứng/điểm chú ý |
|---|---|---|
| Routing | Queue, Topic, ANYCAST/MULTICAST, Virtual Topic, Composite Destination, wildcard | Destination API, XML, address binding, consumer queue convention |
| Subscription | Durable, shared durable, retroactive, selector, noLocal | clientID, subscription name, selector, backlog và lifecycle |
| Delivery | ACK mode, transacted session, XA/JTA, optimized ACK, prefetch/credit | Client URI, listener container, transaction manager, retry/rollback |
| Ordering | Message group, exclusive consumer, consumer priority, total ordering assumption | JMSXGroupID, group buckets, consumer count, retry behavior |
| Scheduling | Delay, scheduled delivery, TTL, expiry, priority | Message properties, scheduler store, expiry policy |
| Failure | Redelivery policy, DLQ, poison ACK, max redelivery, expiry destination | Policy theo destination, số retry, DLQ owner và replay runbook |
| Flow control | Producer flow control, memory limit, cursor/paging, large message, slow consumer | Destination policy, system usage, paging threshold, payload size |
| Persistence | Persistent/non-persistent, KahaDB/mKahaDB/JDBC, journal, sync | Durability requirement, backup/restore, volume, recovery time |
| HA/scale | Master/slave, shared store, replication, network of brokers, cluster, federation | Topology, split brain/fencing, bridge direction, client failover |
| Security | Authentication, authorization, TLS/mTLS, LDAP/JAAS, serialization trust | User/role, destination ACL, certificate, plugin, trusted package |
| Broker extension | Plugin, interceptor, transformer, scheduler, advisory, management notification | Class/JAR, config entry, startup order, custom code owner |
| Message contract | Text/Bytes/Object/Map/Stream message, properties, schema, compression | Payload format, Java class serialization, headers và producer/consumer compatibility |

### 8.1. Advisory và management notification

Classic có advisory destinations (ví dụ ActiveMQ.Advisory.*) để thông báo sự kiện về connection, consumer, producer, destination và broker. Một ứng dụng có thể subscribe advisory để tự động cấp tài nguyên hoặc đồng bộ trạng thái.

Artemis có management notifications và management API; semantics, loại event, tên property và quyền nhận notification khác nhau. Ghi từng advisory destination đang được subscribe, selector, client owner và hành động downstream. Không giả định advisory Classic tự được chuyển thành notification Artemis với cùng payload.

### 8.2. Message groups và ordering

Ghi:

- Có dùng JMSXGroupID hay không, giá trị group có quy tắc nào.
- Message group được dùng để giữ thứ tự theo order/customer/key hay chỉ để chia tải.
- Có exclusive consumer, consumer priority hoặc dispatch policy tùy chỉnh.
- Ứng dụng có giả định thứ tự toàn queue hay chỉ theo group.
- Khi redelivery/failover, thứ tự nào là yêu cầu bắt buộc.

Artemis có message grouping và thuộc tính tương ứng, nhưng phải xác minh cách map và cấu hình cụ thể. Một bài test “hai message đến đúng thứ tự” trên một consumer không đủ chứng minh ordering khi nhiều consumer, rollback và failover.

### 8.3. Prefetch, credit và ACK

Classic client thường cấu hình prefetch theo destination/consumer; Artemis dùng consumer credits/window và có option tương ứng nhưng không nên sao chép nguyên một con số mà không đo. Ghi:

- Prefetch/credit hiện tại theo từng consumer type.
- ACK mode (AUTO_ACKNOWLEDGE, CLIENT_ACKNOWLEDGE, DUPS_OK_ACKNOWLEDGE, transacted).
- Transaction batch size, commit interval, XA branch usage.
- Listener concurrency và số consumer/instance.
- Message size và processing latency.
- Redelivery delay, max attempts và DLQ policy.

Các biến này quyết định số message in-flight, fairness, memory pressure, throughput và thời gian drain; chúng thường quan trọng hơn tên destination.

### 8.4. Plugin, interceptor và code tùy chỉnh

Đọc cấu hình plugin/interceptor trong broker XML và inventory mọi JAR tùy chỉnh:

- Destination interceptor / Virtual Destination interceptor.
- Broker plugin, authorization plugin, authentication plugin.
- Message transformer, logging/statistics plugin.
- Network bridge filter, custom discovery, scheduler extension.
- Spring/JCA resource adapter, custom connection factory wrapper.

Ghi class name, JAR checksum/version, nguồn build, owner, cấu hình khởi tạo, side effect và dependency bên ngoài. Nếu plugin không có mã nguồn hoặc không còn owner, đánh dấu rủi ro cao; không giả định Artemis có plugin thay thế chỉ vì cùng tên khái niệm.

## 9. Cấu hình broker cần đọc để đối chiếu runtime

### 9.1. ActiveMQ Classic

Trong file cấu hình đang được service sử dụng, tìm và ghi:

| Thành phần | Cấu hình liên quan |
|---|---|
| Broker identity/runtime | brokerName, useJmx, persistent, scheduler |
| Storage | persistenceAdapter, KahaDB/mKahaDB/JDBC, data directory |
| Destination | destinations, destinationPolicy, policy map, destination options |
| Transport | transportConnectors, SSL context, frame size, inactivity |
| Bridge/cluster | networkConnectors, discovery, network TTL, conduit subscriptions |
| Security | plugins, authentication, authorization, authorizationMap, LDAP/JAAS |
| Resource limits | systemUsage, memory/store/temp limits, cursor/pending policy |
| Extensions | destination interceptors, broker plugins, custom classpath |
| Advisory/temporary | advisory support, temp destination policy, GC inactive destinations |

Không chỉ grep một file activemq.xml: cấu hình có thể import file khác, dùng environment placeholder, Spring/XBean bean hoặc command-line override. Ghi giá trị đã resolve khi broker chạy nếu có thể.

### 9.2. Artemis đích: các vùng cấu hình cần mapping

Khi đối chiếu, xác định nơi tương ứng trong broker.xml/bootstrap:

| Nhóm | Vùng cấu hình Artemis |
|---|---|
| Broker identity | broker-name, instance/data directory |
| Address/queue | addresses, anycast/multicast, queue filters |
| Policy | address-settings, auto-create/delete, max-size, dead-letter, expiry |
| Protocol | acceptors, protocol modules, connectors |
| Security | security-settings, role mapping, authentication manager |
| Cluster/bridge | cluster-connections, bridges, diverts, federation |
| HA | ha-policy, replication/shared-store, quorum/fencing |
| Storage | journal, bindings, paging, large messages, JDBC nếu dùng |
| Resource | global max size, paging, disk limits, thread/connection limits |
| Management | JMX, management address, RBAC, Web Console/Jolokia |

Đây là danh sách vùng để so sánh, không phải cấu hình đầy đủ cho broker mới. Chưa tạo cấu hình Artemis chỉ từ inventory; cần đánh giá từng semantics và test trước khi chọn giá trị đích.

## 10. Mẫu inventory có thể đưa vào spreadsheet/CSV

Nên tách thành nhiều bảng có khóa liên kết, thay vì một file có hàng trăm cột và lặp thông tin broker.

### 10.1. brokers.csv

~~~csv
broker_id,product,version,environment,host,region,ha_mode,storage_adapter,data_location,owner,snapshot_at
classic-prod-a,ActiveMQ Classic,5.x,production,mq-a,ap-southeast,shared-store,KahaDB,/data/activemq,platform-team,2026-11-17T10:00:00Z
~~~

Dòng trên chỉ là ví dụ giả định. Không sao chép hostname, path hoặc version này làm giá trị thực tế.

### 10.2. destinations.csv

~~~csv
broker_id,name,type,address,routing_type,durable,temporary,configured,auto_created,owner_service,criticality,producer_count,consumer_count,message_count,in_flight,enqueue_rate,dequeue_rate,avg_message_bytes,ttl_policy,dlq,expiry,evidence,confidence
classic-prod-a,orders.work,Queue,,,true,false,true,false,order-service,critical,,,,,,,,,orders.dlq,,JMX+config,high
~~~

Trong file thực, không để trống mà không giải thích: dùng unknown, not_applicable hoặc cột notes tùy schema nhóm. Không gán ANYCAST cho Classic destination; routing type là trường mapping sang Artemis.

### 10.3. subscriptions.csv

~~~csv
broker_id,topic,subscription_type,client_id,subscription_name,selector,no_local,active,consumer_count,backlog,owner_service,last_seen,evidence
classic-prod-a,orders.events,durable,billing-prod,billing-v1,,false,false,0,12000,billing-service,2026-11-16T23:00:00Z,JMX
~~~

### 10.4. clients.csv

~~~csv
client_ref,service,owner,client_library,client_version,api_namespace,protocol,endpoint,client_id,ack_mode,transacted,prefetch_or_credit,tls,failover_uri_ref,last_seen,destinations,evidence
order-worker,order-service,orders-team,activemq-client,5.x,javax.jms,OpenWire,tcp://broker.example:61616,order-worker-prod,SESSION_TRANSACTED,true,100,true,secret-config-ref,2026-11-17T09:55:00Z,orders.work,config+JMX
~~~

Không ghi password, token, private key, full secret URI hoặc payload thật trong inventory. Dùng reference tới secret manager/secret key name đã được phân quyền.

### 10.5. features.csv

~~~csv
feature_id,service,destination,feature,configured,observed,criticality,artemis_mapping,verification_status,evidence,owner
F-001,billing,orders.events,durable_topic_subscription,true,true,high,subscription_queue,needs_test,JMX+source,billing-team
F-002,order-service,VirtualTopic.Orders,virtual_topic,true,true,high,virtual_topic_openwire_or_fqqn,needs_test,broker-config+source,orders-team
~~~

Trạng thái needs_test có chủ đích: inventory ghi nhận hiện trạng và mapping giả định, chưa phải sign-off tương thích.

## 11. Runbook thu thập chỉ đọc

### W0 — Chốt phạm vi và snapshot

1. Liệt kê tất cả broker instance, HA peer, cluster/network connector, region và environment.
2. Chọn cửa sổ quan sát bao phủ giờ cao điểm, batch, lịch tháng và DR drill.
3. Ghi timestamp UTC, version, uptime, config revision và công cụ thu thập.
4. Xin quyền JMX/management **read-only**; không dùng credential quản trị để chạy consumer/producer test.

### W1 — Thu thập cấu hình đã triển khai

1. Lưu bản sao có checksum của cấu hình broker đang chạy và các file import.
2. Resolve connector/acceptor URI, placeholder, TLS reference, plugin class và security policy.
3. Lưu dependency manifest/client config từ từng service owner.
4. Ghi những cấu hình không đọc được hoặc chỉ tồn tại trong secret manager thành gap; không đoán giá trị.

### W2 — Lấy snapshot runtime

**Classic:** dùng BrokerView MBean để liệt kê queues/topics/temp destinations/durable subscribers; lấy destination/connection MBeans và các getter cần thiết. Ghi uptime để phát hiện broker restart giữa các snapshot.

**Artemis:** dùng ActiveMQServerControl để liệt kê addresses, queues, connections, sessions, consumers, producers; dùng QueueControl để đọc queue attributes và counts. Với danh sách lớn, dùng filter/pagination và lưu số trang đã lấy.

**Không browse toàn bộ message body hoặc chạy operation thay đổi dữ liệu.** Nếu cần xác minh payload/schema, xin phê duyệt và dùng sample đã được ẩn dữ liệu trên môi trường phù hợp.

### W3 — Đối chiếu với ứng dụng

1. Group connection theo clientID, protocol, user, remote address, session count và service owner.
2. So destination runtime với cấu hình/source code để tìm dynamic destination, typo và resource không còn owner.
3. Hỏi owner về batch/DR/seasonal consumers không xuất hiện trong snapshot.
4. Xác nhận selectors, durable subscriptions, JMSReplyTo, message group, transaction, retry và redelivery.
5. Ghi từng feature vào features.csv với bằng chứng cụ thể.

### W4 — Review tính đầy đủ

1. Đối chiếu tổng connection/session/producer/consumer với dashboard và log.
2. Kiểm tra queue/topic/durable subscription active và inactive.
3. Kiểm tra bridge, advisory, DLQ, expiry, scheduler, temporary destination và plugin.
4. Đảm bảo mọi destination critical có owner, SLA, retention, backlog và replay procedure.
5. Ghi gap và người chịu trách nhiệm đóng gap; chưa đánh dấu compatible khi chưa có test.

## 12. Phân loại mức độ quan trọng và khoảng trống migration

Không phải destination nào cũng có cùng rủi ro. Gán criticality theo hậu quả nghiệp vụ, không theo message count.

| Mức | Tiêu chí ví dụ | Yêu cầu kiểm kê |
|---|---|---|
| Critical | Thanh toán, đơn hàng, giao dịch XA, dữ liệu phải giữ/replay | Owner rõ, volume/rate/backlog, durability, DLQ, transaction, ordering và test plan |
| High | Event tích hợp liên hệ thống, inventory, billing projection | Subscription/consumer group, idempotency, TTL, redelivery, replay |
| Medium | Notification, reporting, async job có thể retry | Owner, retention, retry, throughput và dependency |
| Low | Telemetry/cache event có thể tái tạo | Xác nhận loss tolerance, expiry và policy |

### 12.1. Trạng thái đánh giá mapping

Mỗi feature/destination được phân loại:

- DIRECT_CANDIDATE: semantics có mapping rõ và chưa thấy phụ thuộc đặc thù; vẫn cần test.
- CONFIG_REQUIRED: Artemis cần cấu hình address, queue, acceptor, policy hoặc plugin tương ứng.
- CLIENT_CHANGE: cần đổi client library, URI, API namespace hoặc subscription code.
- REDESIGN: mô hình khác về bản chất, ví dụ durable subscriber độc quyền sang shared subscription/queue model.
- CUSTOM_EXTENSION: phụ thuộc plugin/interceptor cần port hoặc thay thế.
- UNSUPPORTED_OR_NO_EQUIVALENT: chưa tìm thấy mapping phù hợp; phải quyết định loại bỏ hoặc thiết kế khác.
- UNKNOWN: chưa đủ bằng chứng.

Không gắn DIRECT_CANDIDATE chỉ vì Artemis nhận được TCP connection từ client. Connection thành công không xác minh selector, transaction, ordering, advisory, prefetch, DLQ hay redelivery semantics.

### 12.2. Những khác biệt phải đưa thành câu hỏi kiểm thử

| Hiện trạng Classic | Điều cần xác minh ở Artemis |
|---|---|
| KahaDB/mKahaDB | Export/import hoặc wire migration; không dùng trực tiếp data directory |
| Queue/Topic first-class | Address + queue + ANYCAST/MULTICAST mapping |
| Durable Topic subscriber | Subscription queue, identity và shared subscription strategy |
| Virtual Topic | OpenWire wildcard mapping, FQQN hoặc JMS shared subscription |
| Advisory topics | Management notifications hoặc cơ chế event khác |
| Network of brokers | Cluster/federation/bridge; kiểm tra topology, duplicate và routing |
| VM/HTTP/NIO connector | InVM/Netty hoặc endpoint redesign |
| Destination policy/cursor | Address settings, paging, max-size, flow control |
| Prefetch/optimized ACK | Client credit/ack batching và tác động throughput/fairness |
| Plugin/interceptor | Tính năng Artemis tương ứng hoặc custom extension |
| javax.jms client | Jakarta API/client artifact nếu cần; hoặc giữ OpenWire client trong giai đoạn đầu |

## 13. Ví dụ tổng hợp: kiểm kê một luồng Order Events

Giả sử hệ thống có:

- Producer Order Service gửi VirtualTopic.Orders.
- Billing dùng queue Consumer.Billing.VirtualTopic.Orders.
- Analytics dùng queue Consumer.Analytics.VirtualTopic.Orders.
- Một batch consumer có durable Topic subscription legacy.
- Một ứng dụng khác dùng OpenWire client, còn thiết bị warehouse gửi MQTT.

Inventory phải tạo các bản ghi riêng:

1. Destination logic VirtualTopic.Orders (Topic/Virtual Topic).
2. Consumer queue Billing và Analytics, mỗi queue có backlog, selector, policy và owner riêng.
3. Durable subscription của batch consumer với cặp clientID/subscription name.
4. OpenWire client record gồm library/version, URI, prefetch, ACK/transaction và failover.
5. MQTT client group gồm protocol version, QoS, client ID, clean session/start, retained message và endpoint.
6. Bridge/network connector nếu các queue/topic được forward giữa broker.

Artemis target có thể cần một address multicast và queue subscription tương ứng, hoặc Virtual Topic OpenWire mapping để giữ client legacy. Nhưng nếu batch consumer đang dựa trên exclusive durable subscription, nhóm phải quyết định có chuyển sang shared subscription/queue hay giữ một consumer độc quyền. Nếu MQTT retained/session semantics đang được dùng, cần test riêng; không coi nó là JMS Topic chỉ vì cả hai có fan-out.

| Hiện trạng | Mapping ứng viên | Bằng chứng cần có trước sign-off |
|---|---|---|
| VirtualTopic.Orders | Artemis multicast address | Producer OpenWire/JMS và từng subscriber nhận đúng bản |
| Consumer.Billing.VirtualTopic.Orders | Subscription queue hoặc Virtual Topic FQQN mapping | Billing replicas cạnh tranh trong cùng group; backlog không bị nhân đôi |
| Consumer.Analytics.VirtualTopic.Orders | Queue multicast độc lập | Analytics nhận đủ message, không bị queue Billing tiêu thụ |
| Durable batch subscriber | Durable subscription queue/shared subscription | Offline backlog, identity, selector và reconnect |
| MQTT warehouse client | Artemis MQTT acceptor | QoS, retained, session expiry/clean start và client ID |

Đây là **bản đồ giả định để kiểm tra**, không phải cấu hình đích đã được nghiệm thu.

## 14. Checklist hoàn tất kiểm kê

- [ ] Tất cả broker instance, HA peer, network connector/bridge, cluster/federation và environment có owner.
- [ ] Destination gồm queue, topic, temporary, dynamic, Virtual/Composite, advisory, DLQ, expiry và scheduled được kiểm kê.
- [ ] Artemis target mapping ghi riêng address, queue, routing type, filter, durability và auto-create behavior.
- [ ] Durable/shared subscriptions có clientID, subscription name, selector, active/inactive, backlog và owner.
- [ ] Virtual Topic consumer queues, prefix/wildcard và network bridge behavior đã được ghi.
- [ ] Client inventory có library/version, javax.jms/jakarta.jms, protocol, endpoint, client ID, TLS, ACK, transaction, prefetch/credit và reconnect.
- [ ] Protocol inventory có OpenWire, AMQP, STOMP, MQTT, WebSocket, VM/InVM, HTTP-based transport và Core nếu có.
- [ ] Tính năng delivery, ordering, scheduler, TTL, redelivery, DLQ, flow control, paging, persistence, HA, plugin và advisory đã được đối chiếu.
- [ ] Metrics lấy theo cửa sổ đại diện, có timestamp, uptime, peak/low/batch/DR; không chỉ một snapshot.
- [ ] Cấu hình runtime đã được so với source code, app config, logs, network và owner confirmation.
- [ ] Mỗi tài sản critical có business owner, technical owner, SLA, retention, replay procedure và mapping status.
- [ ] Gap được ghi UNKNOWN/needs_test với người chịu trách nhiệm; không suy đoán là không sử dụng.
- [ ] Không thay đổi broker state, purge message, reset counters hoặc tạo consumer/producer thử trên production trong giai đoạn read-only inventory.

**Kết luận:** Kiểm kê trước migration là việc dựng lại **bức tranh sử dụng thực tế**, không chỉ sao chép danh sách destination. Cần nối destination với subscription, client, protocol, tính năng, dữ liệu và owner; đối chiếu runtime với cấu hình/source code trong một cửa sổ tải đại diện. Baseline đủ tốt sẽ chỉ ra chỗ giữ OpenWire client được, chỗ phải cấu hình Artemis, chỗ cần thay client/API và chỗ phải thiết kế lại. Mỗi mapping vẫn cần test tương thích trước khi được coi là an toàn.

## Tài liệu chính thức

1. [Apache Artemis Migration Guide — Preface](https://artemis.apache.org/components/artemis/migration-documentation/preface.html): phạm vi broker migration từ ActiveMQ 5.x và giả định OpenWire client.
2. [Apache Artemis Migration Guide — Key Differences](https://artemis.apache.org/components/artemis/migration-documentation/key-differences.html): khác biệt storage, paging, addressing/routing giữa Classic và Artemis.
3. [Apache Artemis — Protocols and Interoperability](https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html): protocol modules, OpenWire, AMQP, MQTT, STOMP, Core và acceptor protocol list.
4. [Apache Artemis Migration Guide — Connectors](https://artemis.apache.org/components/artemis/migration-documentation/connectors.html): transport connector Classic và acceptor Artemis, VM/InVM, NIO, WebSocket, HTTP mapping.
5. [Apache Artemis Migration Guide — Virtual Topics](https://artemis.apache.org/components/artemis/migration-documentation/VirtualTopics.html): Virtual Topic, durable subscription, shared subscription và FQQN mapping.
6. [Apache Artemis — Management](https://artemis.apache.org/components/artemis/documentation/latest/management.html): ActiveMQServerControl, list queues/addresses/connections/sessions/consumers/producers, QueueControl và JMX.
7. [ActiveMQ Classic — JMX](https://activemq.apache.org/components/classic/documentation/jmx): BrokerView, destination/connection MBeans và quyền truy cập JMX.
8. [ActiveMQ Classic — BrokerViewMBean API](https://activemq.apache.org/components/classic/documentation/maven/apidocs/org/apache/activemq/broker/jmx/BrokerViewMBean.html): getter cho queue/topic, temporary destinations, durable subscribers, producers và consumers.
9. [Apache Artemis Migration Guide — Message Store Migration](https://artemis.apache.org/components/artemis/migration-documentation/message-store.html): xuất KahaDB/mKahaDB sang định dạng trao đổi Artemis và lưu ý mapping Virtual Topic.
