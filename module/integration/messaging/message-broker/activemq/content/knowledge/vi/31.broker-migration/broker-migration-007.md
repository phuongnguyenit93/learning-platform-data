# Lập kế hoạch chuyển backlog, durable subscription và thông điệp đang giao

> **Chương:** Di chuyển broker  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Tìm hiểu Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue, topic, routing và JMS. Thực hành producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi:** Lập kế hoạch và thực hiện chuyển **message đang chờ**, **từng durable topic subscription** và **delivery chưa ACK** khi thay broker, đổi persistence store hoặc chuyển từ ActiveMQ Classic sang Artemis. Trọng tâm là tính toàn vẹn dữ liệu và cutover có thể kiểm chứng; không giả định hai message store có định dạng tương thích.

## 1. Vì sao backlog và delivery state là phần khó nhất của migration?

Một broker đang chạy có nhiều loại message state khác nhau:

- Message đã được nhận vào queue nhưng chưa dispatch.
- Message đã dispatch tới consumer, đang nằm trong prefetch/client buffer hoặc callback đang xử lý.
- Message đã được consumer xử lý nhưng ACK/transaction commit chưa hoàn tất.
- Message đã lên lịch giao sau, message sắp hết hạn, message đang paging hoặc lưu thành large message.
- Message được giữ riêng cho một durable topic subscription đang offline.
- Message đã chuyển sang DLQ hoặc expiry queue và cần retention/replay theo chính sách.

Một phép copy thư mục dữ liệu hoặc một lần đếm queue depth không thể tự chứng minh rằng tất cả các nhóm này đã được chuyển đầy đủ. Migration phải trả lời ba câu hỏi:

1. **Nguồn nào đang sở hữu mỗi message tại thời điểm cutover?**
2. **Message nào đã được ACK/commit, message nào còn có thể redeliver?**
3. **Từng durable subscriber sẽ nhận đúng phần backlog của chính subscription đó hay không?**

Mục tiêu không chỉ là target broker khởi động được. Sau cutover, ứng dụng phải tiếp tục xử lý đúng các event chưa hoàn tất, không bỏ sót message và có thể phát hiện/khử duplicate.

~~~mermaid
flowchart TD
    Q["Ready messages trong queue"] --> X["Inventory + snapshot"]
    D["Delivering / prefetch / callback"] --> I["Quiesce và giải quyết in-flight"]
    T["Transacted / unacked"] --> I
    S["Durable subscription backlog"] --> M["Mapping theo từng subscription"]
    I --> X
    M --> X
    X --> P["Export/import hoặc wire transfer"]
    P --> V["Reconcile IDs, counts, order, TTL"]
    V --> C["Fence broker cũ và cutover"]
    C --> R["Theo dõi redelivery, duplicates, DLQ"]
~~~

## 2. Chốt loại migration trước khi chọn công cụ

Từ “migration” có thể chỉ nhiều công việc khác nhau. Cần tách chúng trước khi lập kế hoạch.

| Loại | Ví dụ | Phạm vi dữ liệu |
|---|---|---|
| **Broker upgrade** | Artemis 2.x lên phiên bản Artemis mới | Cùng họ broker, tuân thủ upgrade guide và journal compatibility |
| **Store migration** | Classic KahaDB sang Artemis journal | Phải export/import hoặc chuyển message qua protocol |
| **Broker replacement cùng họ** | Classic node A sang Classic node B | Có thể dùng store migration phù hợp hoặc wire transfer |
| **Topology migration** | Một broker thành nhiều broker/cluster | Phải phân chia destination, subscription ownership và routing |
| **Client/protocol migration** | OpenWire client sang Artemis Core/AMQP | Ngoài message backlog còn có API, header và semantics thay đổi |

**Không copy KahaDB journal vào thư mục journal của Artemis.** Hai broker có cách tổ chức store và paging khác nhau; message store không phải định dạng thay thế trực tiếp. KahaDB giữ journal và index riêng, trong khi Artemis có append-only journal và mô hình paging khác. Chuyển store phải qua công cụ export/import tương thích hoặc đọc message từ broker nguồn rồi gửi sang broker đích.

Cũng không nhầm `artemis upgrade` với migration Classic → Artemis. Lệnh `artemis upgrade` dùng để làm mới cấu hình/script của **một Artemis instance cũ** khi chuyển phiên bản Artemis; nó không chuyển KahaDB của Classic thành Artemis store.

### 2.1. Hai phương thức chuyển dữ liệu chính

**Offline store export/import** phù hợp khi nguồn là KahaDB/mKahaDB được công cụ hỗ trợ và có thể dừng broker để chụp store nhất quán. Ưu điểm là chuyển được backlog lớn mà không cần chạy consumer pump lâu. Hạn chế là phụ thuộc store backend, version công cụ, mapping destination và khả năng export các subscription đặc thù.

**Online wire transfer** phù hợp khi store nguồn không được hỗ trợ trực tiếp, cần chọn lọc destination hoặc cần chuyển từng luồng. Một consumer đọc nguồn và producer ghi đích; phải thiết kế transaction, retry, idempotency và checkpoint. Phương thức này có thể chạy theo từng queue/subscription, nhưng cần bảo vệ cửa sổ duplicate và bảo toàn thứ tự nếu nghiệp vụ yêu cầu.

Không có lựa chọn chung cho mọi hệ thống. Hãy chọn theo backend, số lượng message, downtime cho phép, khả năng tạo snapshot và semantics của durable subscription.

## 3. Lập inventory trước khi đụng tới dữ liệu

### 3.1. Inventory theo destination

Tạo danh sách đầy đủ từ management API/JMX/console của broker nguồn, không chỉ từ cấu hình ứng dụng:

| Thuộc tính | Ghi nhận | Vì sao quan trọng |
|---|---|---|
| Destination name và type | Queue, topic, virtual topic, composite | Xác định routing và mapping đích |
| Ready/message count | Số message đang chờ | Baseline backlog |
| Delivering/in-flight count | Đã dispatch, chưa ACK | Phải drain/rollback trước export |
| Scheduled count | Chờ thời điểm giao | Không được bỏ quên delayed messages |
| Expired/DLQ count | Retention và replay policy | Thường cần mapping riêng |
| Durable subscriptions | clientID, subscriptionName, selector | Mỗi subscription có backlog riêng |
| Message size distribution | p50/p95/max, large message | Dự trù thời gian và storage |
| Priority, expiry, group | Headers và policy | Có thể ảnh hưởng thứ tự/TTL |
| Producer/consumer count | Client ID, app version, protocol | Lập kế hoạch quiesce/fence |

Với Artemis có thể quan sát các cột `MESSAGE_COUNT`, `DELIVERING_COUNT`, `SCHEDULED_COUNT`, `MESSAGES_ACKED` qua CLI/management. Với Classic, dùng JMX/management console để ghi queue size, dispatched, inflight và durable subscriber details. Tên metric có thể khác giữa các phiên bản; lưu cả raw export và timestamp chụp.

### 3.2. Inventory theo từng message stream

Nếu ứng dụng có `eventId`, `aggregateId`, `sequence`, `correlationId`, hãy xác định trường nào là định danh ổn định qua migration. `JMSMessageID` thường do broker/provider tạo; khi gửi lại sang broker đích, ID có thể được sinh mới. Không dùng `JMSMessageID` làm khóa dedup xuyên broker trừ khi hệ thống đã định nghĩa và bảo toàn nó một cách rõ ràng.

Nên có một khóa nghiệp vụ ổn định như:

~~~text
eventId = order-7842:shipment-created:v3
aggregateId = order-7842
sequence = 3
sourceDestination = shipment.events
~~~

Dùng `eventId` để reconcile nguồn/đích và deduplicate side effect. `JMSCorrelationID` phục vụ tương quan request/reply, không nhất thiết là unique ID của event.

### 3.3. Snapshot có thời điểm và phạm vi rõ ràng

Mỗi bản inventory cần ghi:

- Broker name, broker version, store backend, protocol và timezone.
- Timestamp UTC, trạng thái producer/consumer tại lúc chụp.
- Queue ready, delivering, scheduled; durable subscription backlog theo từng identity.
- DLQ/expiry queue và policy redelivery/expiration.
- Count theo destination và, nếu có, count theo `eventId`/partition.
- File snapshot/export checksum và người chịu trách nhiệm phê duyệt.

Một snapshot chụp khi producer vẫn hoạt động chỉ là **ảnh quan sát tại một thời điểm**, không phải ranh giới cutover. Nếu không freeze traffic, phải có cơ chế watermark/checkpoint hoặc incremental delta để biết message nào phát sinh sau snapshot.
## 4. Hiểu đúng queue backlog, durable subscription và in-flight delivery

### 4.1. Queue backlog là một luồng chia sẻ

Với JMS queue, một message thường được giao cho một consumer trong nhóm cạnh tranh. Message ready chưa dispatch có thể được browse hoặc export theo cơ chế của broker. Khi consumer nhận message nhưng chưa ACK, message đang ở trạng thái delivering/in-flight và có thể được giữ trong buffer của client.

`prefetch` của Classic có thể khiến nhiều message rời trạng thái ready trước khi application xử lý xong. Vì vậy queue `messageCount` có thể giảm trong khi tổng công việc chưa hoàn tất không giảm tương ứng. Phải kiểm tra cả `dispatch/inflight/delivering` và ACK/transaction state.

### 4.2. Durable topic subscription có backlog riêng cho từng subscriber

Đây là khác biệt cốt lõi so với queue. Với durable topic, mỗi durable subscriber đủ điều kiện nhận **một bản sao logic** của message. Subscription được nhận diện bằng cặp:

- `clientID`
- `subscriptionName` (durable subscriber name)

Classic giữ message persistent cho durable subscriber trong lúc subscriber offline; khi subscriber quay lại, nó tiếp tục nhận các message đã tích lũy. Một topic có ba durable subscriptions có thể giữ ba backlog khác nhau, tùy thời điểm đăng ký, selector, expiration và ACK của từng subscriber.

Ví dụ:

| Subscription | clientID | subscriptionName | Selector | Backlog |
|---|---|---|---|---:|
| Billing | `billing-v1` | `billing-orders` | `eventType = 'OrderCreated'` | 120 |
| Search | `search-v2` | `search-orders` | Không selector | 310 |
| Audit | `audit-v1` | `audit-all` | `priority >= 4` | 48 |

Không thể lấy 310 message của Search rồi publish lại một lần lên topic đích với hy vọng Billing và Audit tự có backlog đúng. Nếu publish lại vào multicast topic khi cả ba subscription đích đã hoạt động, mỗi message sẽ được nhân bản cho tất cả các subscriber đích; nếu chuyển từng backlog một bằng cách publish lại topic, có thể tạo duplicate hoặc làm sai selector. Phải chuyển **luồng backlog của từng subscription** vào đúng queue đích của subscription đó, hoặc dùng store exporter có mapping đã được xác minh.

Classic không hỗ trợ browse trực tiếp một topic như queue; cần dùng durable subscription/management view hoặc truy cập queue nội bộ của subscription theo cách broker hỗ trợ. Đừng giả định một lệnh queue browser trên tên topic sẽ liệt kê mọi bản sao durable.

### 4.3. In-flight delivery không phải một message stream độc lập để copy

Message đã dispatch nhưng chưa ACK vẫn thuộc trách nhiệm của broker nguồn. Nó có thể:

- Đang nằm trong prefetch/client buffer, chưa được application gọi xử lý.
- Đang chạy callback và side effect nghiệp vụ.
- Đang ở transacted session nhưng chưa commit.
- Đã xử lý side effect nhưng ACK chưa gửi hoặc commit response bị mất.
- Đã ACK ở broker nhưng management snapshot chưa phản ánh kịp thời.

Không thể chuyển một “delivery lock” đang gắn với connection/session của broker nguồn sang broker đích như cùng một lần giao. Khi migration, cần để delivery đó hoàn tất commit, hoặc rollback/đóng session có kiểm soát để broker nguồn đưa message về trạng thái có thể redeliver. Sau đó message mới được export/transfer như backlog thông thường.

**Không đếm message đang delivering ở nguồn rồi cộng với ready count ở đích mà không xác định trạng thái ACK.** Đây là nguyên nhân phổ biến của double-count hoặc mất message khi cutover.

## 5. ACK, transaction và cửa sổ in-flight trước cutover

### 5.1. Xử lý theo acknowledgment mode

| Mode | Ranh giới ACK | Hành động trước migration |
|---|---|---|
| `AUTO_ACKNOWLEDGE` | Với synchronous receive, provider ACK theo lần receive trả về; với listener, ACK theo completion semantics của provider | Dừng producer, chờ callback hoàn tất, sau đó đóng consumer sạch và kiểm tra delivering count |
| `CLIENT_ACKNOWLEDGE` | `Message.acknowledge()` có thể ACK cộng dồn các message đã nhận trong session | Chỉ ACK sau khi side effect đã commit; với message chưa ACK, dừng consumer và để provider xử lý redelivery theo semantics đã kiểm chứng; không gọi rollback trừ transacted session |
| `DUPS_OK_ACKNOWLEDGE` | ACK có thể được trì hoãn; duplicate được phép | Tính cả message chưa ACK trong inventory; downstream phải idempotent |
| `SESSION_TRANSACTED` | `Session.commit()` hoàn tất send/receive transaction; `rollback()` trả deliveries về để redeliver | Commit những công việc đã hoàn tất; rollback batch còn dở trước khi dừng |

Nếu ứng dụng sử dụng Spring listener container, transaction có thể do container sở hữu. Không gọi `Session.commit()` từ thread khác hoặc từ migration controller lên session mà listener đang dùng. Dừng listener container theo API framework, đợi callback đang chạy kết thúc, rồi mới đóng connection.

### 5.2. Prefetch và client buffer

Classic prefetch cao có thể làm queue ready count giảm dù consumer chưa xử lý hết. Artemis Core consumer window cũng có thể buffer message tại client. Khi lập cutover:

1. Ngừng tạo message mới ở producer.
2. Cho consumer xử lý hết các callback hiện tại trong một khoảng timeout có giới hạn.
3. Commit transaction đã hoàn tất.
4. Rollback transaction đang dở; đóng consumer/session theo thứ tự của framework.
5. Xác nhận `delivering/inflight` trở về 0 hoặc ghi lại chính xác các message còn được broker giữ.
6. Chỉ export store sau khi broker nguồn dừng sạch nếu công cụ yêu cầu offline access.

Không chỉ đặt concurrency về 0 rồi giả định buffer đã rỗng. Phải theo dõi số delivery chưa ACK và kết quả rollback.

### 5.3. Cửa sổ commit bất định

Nếu consumer đã commit DB nhưng broker chưa nhận ACK, broker có thể redeliver. Nếu producer gọi `commit()` nhưng connection rớt đúng lúc response, client không biết broker đã commit hay chưa. Migration không thể suy ra outcome chỉ từ exception của client.

Giữ `eventId` ổn định và có unique constraint/idempotency record ở downstream. Nếu phải retry batch có outcome không chắc chắn, gửi lại cùng `eventId`, không tạo ID mới cho cùng một nghiệp vụ.

## 6. Mapping Classic → Artemis: destination và durable subscription

### 6.1. Queue, topic và address routing

Artemis dùng address và queue với routing type:

| Nguồn Classic | Mô hình đích Artemis | Điểm cần kiểm tra |
|---|---|---|
| JMS Queue `orders.in` | Address + queue kiểu **ANYCAST** | Tên queue, routing, filters, consumers |
| JMS Topic `orders.events` | Address kiểu **MULTICAST** | Mỗi subscription có queue riêng |
| Durable topic subscription | Queue bound vào multicast address | Giữ clientID/name/selector và backlog của đúng subscription |
| Classic Virtual Topic `VirtualTopic.Orders` | Multicast address + consumer queue | Ánh xạ `Consumer.*` sang FQQN |
| DLQ/expiry queue | Address/queue riêng | Không nhập nhầm thành live business queue |

Trong Artemis, topic publish-subscribe được thực hiện bằng multicast address; mỗi subscription có queue riêng. Queue point-to-point thường dùng anycast. Vì vậy việc đổi tên destination không chỉ là đổi string; phải tạo đúng routing type và queue bindings.

Ví dụ fragment cấu hình queue và topic address ở target Artemis:

~~~xml
<addresses>
    <address name="orders.pending">
        <anycast>
            <queue name="orders.pending"/>
        </anycast>
    </address>
    <address name="orders.events">
        <multicast/>
    </address>
</addresses>
~~~

Đây là mảnh cấu hình trong phần `<addresses>` hiện có. Queue durable cho topic sẽ được tạo/đăng ký theo subscriber identity và policy của broker; không tự đặt tên queue nội bộ khi chưa đối chiếu management metadata.

### 6.2. Durable subscription: bảo toàn identity và selector

Với mỗi durable subscription, lưu nguyên văn:

- Topic name và `clientID`.
- Durable subscription name.
- Selector chính xác (kể cả khoảng trắng/kiểu dữ liệu nếu tooling lưu).
- `noLocal` nếu ứng dụng sử dụng.
- Durable/shared subscription type và protocol/client API.
- Queue nội bộ tương ứng trên broker nguồn và queue đích trên Artemis.
- Số message ready, delivering và scheduled của subscription.
- Expiry/redelivery/DLQ policy tương ứng.

Một durable subscription đang được target consumer sử dụng có thể khóa subscription identity hoặc khiến message bị tiêu thụ trước khi reconcile. Trong giai đoạn import, nên tạo destination/subscription đích nhưng **chưa mở business consumers** cho đến khi dữ liệu được kiểm tra xong.

Đừng xóa durable subscription cũ để “dọn broker” trước khi xác nhận backlog đã được chuyển và subscriber đích đã hoạt động. Unsubscribe thường xóa queue/backlog của subscription đó.

### 6.3. Virtual topics và FQQN

Classic Virtual Topics thường dùng topic như `VirtualTopic.Orders` và consumer queue như `Consumer.A.VirtualTopic.Orders`. Artemis có thể map consumer destination thành Fully Qualified Queue Name (FQQN):

~~~xml
<!-- Mảnh acceptor trong ARTEMIS_INSTANCE/etc/broker.xml -->
<acceptor name="openwire">
    tcp://0.0.0.0:61616?protocols=OPENWIRE;virtualTopicConsumerWildcards=Consumer.*.%3E%3B2
</acceptor>
~~~

Mapping trên chuyển `Consumer.A.VirtualTopic.Orders` thành FQQN:

~~~text
VirtualTopic.Orders::Consumer.A.VirtualTopic.Orders
~~~

Đây là ví dụ theo convention mặc định `Consumer.*.`; nếu hệ thống dùng prefix/suffix hoặc wildcard khác, phải điều chỉnh mapping và test bằng đúng tên queue hiện tại. Với selector của virtual-topic consumer, kiểm tra `selectorAware` và queue filter trên Artemis. Không áp dụng mapping virtual topic cho mọi durable topic subscription tiêu chuẩn; hai mô hình có cách định danh và queue khác nhau.

### 6.4. Các thuộc tính message cần bảo toàn hoặc ánh xạ

| Thuộc tính | Xử lý |
|---|---|
| Body/type | Bảo toàn bytes/text/map; kiểm thử `ObjectMessage` và custom serialization riêng |
| Application properties | Copy các property được hỗ trợ, giữ kiểu dữ liệu |
| `JMSCorrelationID` | Bảo toàn nếu dùng request/reply hoặc trace |
| `JMSReplyTo` | Ánh xạ sang destination đích, không copy mù tên nguồn |
| `JMSType` | Bảo toàn khi ứng dụng dùng |
| `JMSPriority` | Giữ hoặc chuẩn hóa theo policy đích |
| `JMSExpiration` | Tính TTL còn lại; không hồi sinh message đã hết hạn |
| `JMSDeliveryMode` | Quyết định policy persistence khi chuyển; ghi lại mode nguồn nếu target gửi persistent để bảo vệ transfer |
| `JMSMessageID` | Thường được broker đích sinh lại; dùng `eventId` ổn định để đối chiếu |
| `JMSRedelivered` / delivery count | Không thể xem như trạng thái delivery gốc sau khi tạo message mới; lưu số lần nguồn vào audit property nếu cần |
| `JMSXGroupID` / sequence | Bảo toàn nếu dùng message grouping/ordering |

Không copy toàn bộ header/property provider-specific mà không kiểm tra. Một số property là read-only hoặc do broker đích quản lý. Với `ObjectMessage`, cần cùng class/serialVersionUID và policy deserialization an toàn; cân nhắc chuyển sang schema-based payload trước migration.
## 7. Chọn export/import hay wire transfer

### 7.1. Classic KahaDB/mKahaDB sang Artemis

Với Classic dùng KahaDB hoặc mKahaDB, dự án Apache ActiveMQ CLI Tools cung cấp công cụ export message store sang định dạng XML exchange mà Artemis có thể import. Công cụ có bộ lọc chọn destination; từ phiên bản 0.2.0 có hỗ trợ mapping virtual-topic consumer queues. Hãy đối chiếu phiên bản tool với store backend và convention virtual topic đang chạy.

Quy trình offline tổng quát:

1. Freeze producer và xử lý consumer/in-flight theo mục 5.
2. Dừng Classic broker sạch; sao lưu nguyên trạng data directory trước khi export.
3. Chạy KahaDB exporter trên **bản store đã dừng**, chọn đúng queue/subscription cần chuyển.
4. Lưu XML export, checksum, log và manifest destination mapping.
5. Chuẩn bị Artemis target với address/queue, routing type, security và policy đã tạo sẵn.
6. Khởi động Artemis; import XML vào broker đang chạy bằng CLI data import.
7. Reconcile số lượng và message IDs trước khi cho consumer target hoạt động.

Ví dụ import file XML vào Artemis:

~~~bash
cd /opt/artemis-instance
./bin/artemis data imp \
  --input /migration/classic-store-export.xml \
  --host artemis-target.internal \
  --port 61616 \
  --user migration-import \
  --verbose
~~~

CLI sẽ yêu cầu password nếu không truyền qua tham số. Trong production, ưu tiên cơ chế prompt/secret injection của môi trường, không ghi password rõ vào shell history hoặc script. `artemis data imp` import message data XML vào **broker đích đang chạy**. Tùy chọn `--transaction` gom toàn bộ import vào một transaction commit cuối; chỉ dùng sau khi đã thử với kích thước store tương tự vì một transaction rất lớn có thể tăng thời gian commit và tài nguyên cần thiết.

Công cụ `artemis data exp` là công cụ export message data từ **Artemis store** ra XML exchange; nó không tự đọc KahaDB. Với backend Classic không được exporter hỗ trợ hoặc cần xử lý selector/subscription đặc thù, dùng wire transfer có kiểm soát hoặc công cụ migration được xác minh riêng.

### 7.2. Kiểm tra exporter có thực sự bao phủ durable subscriptions

Đừng mặc định rằng “export all queues” có nghĩa là mọi durable topic subscription đã được xuất. Hãy xác minh manifest và output cho từng subscription:

- Subscription có được biểu diễn như một queue trong export không?
- Selector và mapping destination có được giữ không?
- Queue đó là backlog riêng của subscriber nào?
- Message có selector không match bị loại đúng như kỳ vọng không?
- Virtual topic consumer queue có giữ đúng tên/prefix không?
- Standard durable subscription có được exporter phiên bản đang dùng hỗ trợ hay cần xử lý riêng?

Tài liệu Artemis nêu rõ KahaDB exporter có hỗ trợ mapping **virtual topic consumer queue**. Đây không phải cam kết rằng mọi kiểu durable subscriber, shared subscription, custom destination hay plugin đều tự động được ánh xạ chính xác. Với loại không được xác minh, lập một luồng wire transfer riêng cho subscription đó.

### 7.3. Wire transfer: quy tắc commit để tránh mất message

Một pump chuyển queue có thể dùng hai transacted sessions: source nhận message trong transaction, target gửi message trong transaction. Thứ tự an toàn hơn cho at-least-once là:

1. Receive từ source transaction.
2. Send các bản sao sang target transaction.
3. `targetSession.commit()` để target xác nhận lô.
4. Chỉ sau đó `sourceSession.commit()` để ACK source.

Nếu target commit thành công nhưng source commit thất bại hoặc response bị mất, source có thể redeliver và target có duplicate. Nếu ACK source trước rồi target send/commit thất bại, message có thể mất. Vì vậy không đảo thứ tự commit chỉ để tránh duplicate; hãy giữ `eventId` ổn định và deduplicate tại consumer/target theo contract nghiệp vụ.

Không có bảo đảm exactly-once xuyên hai broker chỉ vì cả hai session đều transacted. Muốn có atomic transaction qua hai resource managers cần XA/transaction manager và hỗ trợ tương ứng của cả hai provider; ngay cả khi dùng XA, phải kiểm thử recovery log và in-doubt transactions. Với phần lớn migration, at-least-once + idempotency là mô hình dễ kiểm soát hơn.

## 8. Ví dụ Java/JMS: chuyển một queue theo lô

Artemis hỗ trợ OpenWire để ActiveMQ Classic JMS client có thể kết nối trực tiếp tới Artemis. Vì vậy một ví dụ dùng `javax.jms` và Classic client có thể nhận từ Classic nguồn rồi gửi tới Artemis target qua OpenWire, miễn là acceptor/protocol và client version đã được kiểm tra. Ví dụ dưới đây chỉ chuyển **một queue**, không thay thế quy trình riêng cho durable topic subscription.

Acceptor OpenWire mặc định của Artemis thường lắng nghe cổng 61616; nếu target đã giới hạn protocols, xác nhận có `OPENWIRE`:

~~~xml
<!-- Mảnh acceptor trong ARTEMIS_INSTANCE/etc/broker.xml -->
<acceptor name="openwire">
    tcp://0.0.0.0:61616?protocols=OPENWIRE
</acceptor>
~~~

### 8.1. Cấu hình kết nối và transaction

Ví dụ Maven dùng ActiveMQ Classic client hỗ trợ JMS `javax.jms`:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>activemq-client</artifactId>
    <version>5.18.7</version>
</dependency>
~~~

Chọn client version tương thích với JDK và broker thực tế. Dùng biến môi trường/secret store cho URL và credentials; không hardcode mật khẩu.

~~~java
import javax.jms.*;
import org.apache.activemq.ActiveMQConnectionFactory;

String sourceUri = System.getenv("SOURCE_BROKER_URL");
String targetUri = System.getenv("TARGET_OPENWIRE_URL");

ConnectionFactory sourceFactory =
    new ActiveMQConnectionFactory(sourceUri);
ConnectionFactory targetFactory =
    new ActiveMQConnectionFactory(targetUri);

Connection sourceConnection = sourceFactory.createConnection(
    System.getenv("SOURCE_USER"), System.getenv("SOURCE_PASSWORD"));
Connection targetConnection = targetFactory.createConnection(
    System.getenv("TARGET_USER"), System.getenv("TARGET_PASSWORD"));

sourceConnection.start();
targetConnection.start();

Session sourceSession =
    sourceConnection.createSession(true, Session.SESSION_TRANSACTED);
Session targetSession =
    targetConnection.createSession(true, Session.SESSION_TRANSACTED);

Queue sourceQueue = sourceSession.createQueue("orders.pending");
Queue targetQueue = targetSession.createQueue("orders.pending");

MessageConsumer consumer = sourceSession.createConsumer(sourceQueue);
MessageProducer producer = targetSession.createProducer(targetQueue);
~~~

Target queue/address phải được tạo đúng kiểu **ANYCAST** trước khi chạy pump. Nếu dùng Artemis auto-create, vẫn phải xác nhận routing type và security policy thực tế; không để một lỗi chính tả vô tình tạo address khác.

### 8.2. Copy body và application properties

Mỗi provider có thể có header riêng. Không thể đặt lại một số header do broker quản lý như `JMSMessageID`, `JMSDestination`, `JMSRedelivered` hoặc delivery count. Tạo message mới theo body type đã hỗ trợ, copy application properties được phép, rồi để target sinh ID mới.

Ví dụ helper chỉ chấp nhận `TextMessage` và `BytesMessage`; loại khác dừng pump để không âm thầm làm hỏng payload:

~~~java
static Message copyBody(Message source, Session target)
        throws JMSException {

    if (source instanceof TextMessage) {
        return target.createTextMessage(
            ((TextMessage) source).getText());
    }

    if (source instanceof BytesMessage) {
        BytesMessage input = (BytesMessage) source;
        input.reset();

        BytesMessage output = target.createBytesMessage();
        byte[] buffer = new byte[8192];
        int read;

        while ((read = input.readBytes(buffer)) != -1) {
            output.writeBytes(buffer, 0, read);
        }
        return output;
    }

    throw new JMSException(
        "Unsupported body type; add an explicit codec before migration: "
        + source.getClass().getName());
}

static void copyProperties(Message source, Message target)
        throws JMSException {

    java.util.Enumeration<?> names = source.getPropertyNames();
    while (names.hasMoreElements()) {
        String name = (String) names.nextElement();

        // Delivery metadata thuộc broker đích phải được tạo lại.
        if ("JMSXDeliveryCount".equals(name)
                || "JMSXUserID".equals(name)) {
            continue;
        }

        Object value = source.getObjectProperty(name);
        if (value instanceof String || value instanceof Boolean
                || value instanceof Byte || value instanceof Short
                || value instanceof Integer || value instanceof Long
                || value instanceof Float || value instanceof Double) {
            target.setObjectProperty(name, value);
        }
    }

    if (source.getJMSCorrelationID() != null) {
        target.setJMSCorrelationID(source.getJMSCorrelationID());
    }
    if (source.getJMSType() != null) {
        target.setJMSType(source.getJMSType());
    }
}
~~~

Nếu hệ thống dùng `JMSXGroupID`/`JMSXGroupSeq`, `JMSReplyTo`, MapMessage, ObjectMessage hoặc custom headers, bổ sung mapping cụ thể và test bằng consumer thật. `JMSReplyTo` cần map sang queue/topic đích, không copy destination object từ broker nguồn. Với `ObjectMessage`, kiểm tra classpath, serialization compatibility và deserialization allowlist.

### 8.3. Chuyển theo batch và bảo toàn TTL

Đoạn vòng lặp sau minh họa thứ tự commit target trước source. `eventId` phải là property ổn định do ứng dụng sinh. Lưu `migrationSourceMessageId` để audit; nó không thay thế eventId.

~~~java
int batchSize = 100;
long migrated = 0;

while (true) {
    int inBatch = 0;

    while (inBatch < batchSize) {
        Message source = consumer.receive(500);
        if (source == null) {
            break;
        }

        String eventId = source.getStringProperty("eventId");
        if (eventId == null || eventId.isBlank()) {
            throw new JMSException(
                "Missing stable eventId; stop and define deduplication key");
        }

        long expiration = source.getJMSExpiration();
        long ttl = 0L;
        if (expiration > 0) {
            ttl = expiration - System.currentTimeMillis();
            if (ttl <= 0) {
                throw new JMSException(
                    "Expired source message requires explicit expiry handling: "
                    + eventId);
            }
        }

        Message copy = copyBody(source, targetSession);
        copyProperties(source, copy);
        if (source.getJMSMessageID() != null) {
            copy.setStringProperty("migrationSourceMessageId",
                source.getJMSMessageID());
        }
        copy.setStringProperty("migrationBatchEventId", eventId);
        copy.setIntProperty("migrationSourceDeliveryMode",
            source.getJMSDeliveryMode());

        // Persistent trong lúc chuyển để bảo vệ dữ liệu target.
        // Ghi lại mode nguồn ở property để audit/đối chiếu.
        producer.send(copy, DeliveryMode.PERSISTENT,
            source.getJMSPriority(), ttl);

        inBatch++;
    }

    if (inBatch == 0) {
        break;
    }

    targetSession.commit();  // Target phải commit trước.
    sourceSession.commit();  // Sau đó mới ACK nguồn.
    migrated += inBatch;

    System.out.printf("Committed batch=%d total=%d%n",
        inBatch, migrated);
}
~~~

Nếu TTL đã hết trong lúc migration, ví dụ dừng và đưa message vào quy trình expiry/reconciliation đã phê duyệt; không tự gia hạn bằng cách gửi TTL mới. Nếu target luôn gửi persistent để bảo vệ quá trình chuyển, property `migrationSourceDeliveryMode` giữ lại mode gốc cho audit. Quyết định có tiếp tục giữ persistent sau cutover phải theo delivery contract của ứng dụng.

Trong code production cần đóng consumer/session/connection trong `finally`, ghi checkpoint cho từng batch, lưu tập eventId đã target commit, xử lý `JMSException` bằng rollback có kiểm soát và dừng khi outcome commit không rõ. Không ghi log toàn bộ payload nhạy cảm.

### 8.4. Cửa sổ duplicate của pump

Giả sử `targetSession.commit()` trả thành công, nhưng process chết trước `sourceSession.commit()`. Khi restart, source redeliver batch; target nhận thêm bản sao. Đây là expected at-least-once behavior, không phải lỗi ngẫu nhiên của broker.

Cách xử lý:

- Target/consumer ghi unique `eventId` hoặc `(consumerName,eventId)` trong cùng transaction với side effect.
- Checkpoint batch chỉ được đánh dấu complete sau khi target commit và source commit đã xác nhận.
- Nếu source commit outcome không rõ, đối chiếu eventId giữa hai broker rồi quyết định replay/skip.
- Nếu cần giữ order theo `aggregateId`, chỉ chạy một pump trên partition đó hoặc giữ grouping/sequence và kiểm tra sequence ở consumer đích.

Không tăng số pump đồng thời trên cùng queue khi yêu cầu FIFO chưa được chứng minh; nhiều worker có thể làm đảo thứ tự commit dù message được receive theo thứ tự.
### 8.5. Rollback khi batch lỗi

Đặt vòng lặp pump trong `try/catch` của method điều phối. Khi receive/send thất bại trước khi target commit được xác nhận, rollback cả hai session để source trả delivery về và target bỏ lô chưa commit:

~~~java
catch (JMSException failure) {
    try {
        targetSession.rollback();
    } catch (JMSException rollbackTargetFailure) {
        failure.addSuppressed(rollbackTargetFailure);
    }

    try {
        sourceSession.rollback();
    } catch (JMSException rollbackSourceFailure) {
        failure.addSuppressed(rollbackSourceFailure);
    }

    throw failure;
}
~~~

Nếu lỗi xảy ra **sau khi target commit đã thành công** nhưng trước khi source commit được xác nhận, rollback source sẽ làm message có thể redeliver; rollback target không thể đảo một transaction đã commit. Khi restart, pump có thể gửi lại message đã có ở target. Reconcile bằng `eventId` và idempotency record trước khi tiếp tục. Nếu kết quả `targetSession.commit()` không rõ vì connection bị mất đúng lúc trả response, coi batch là **in-doubt**, giữ checkpoint ở trạng thái cần đối chiếu; không đánh dấu thất bại rồi tự tạo eventId mới.
## 9. Runbook cutover có điểm dừng kiểm soát

Một cutover an toàn phải có **một nguồn có thẩm quyền tại mỗi thời điểm**. Đừng để producer gửi đồng thời vào cả hai broker rồi hy vọng backlog tự hội tụ; nếu cần dual-write, phải thiết kế transactional outbox và reconciliation như một kiến trúc riêng.

### 9.1. Chuẩn bị target trước ngày chuyển

- Tạo addresses/queues theo mapping, đúng ANYCAST/MULTICAST và tên destination.
- Tạo durable subscriptions/virtual-topic queues, giữ đúng selector, client identity và queue filters.
- Port security roles, user, TLS/acceptor, quotas, DLQ, expiry, redelivery, paging, max delivery attempts và message expiry.
- Cấu hình consumer chưa chạy business handler hoặc khóa quyền consume cho tới khi import/reconciliation hoàn tất.
- Kiểm tra target có đủ dung lượng cho backlog, large messages, scheduled messages và DLQ retention.
- Chạy rehearsal với snapshot copy có kích thước gần production; đo thời gian export, import, validation và rollback.
- Chuẩn bị endpoint switch, DNS/config/secret, firewall/ACL và cơ chế fence broker nguồn.

### 9.2. Trình tự cutover theo thời gian

| Bước | Hành động | Điều kiện để sang bước kế |
|---|---|---|
| 1. Freeze ingress | Dừng producer, scheduler, retry job và service có thể publish | Producer count bằng 0; xác nhận không còn outbox drain |
| 2. Drain consumers | Cho consumer xử lý callback đang chạy; commit các transaction thành công | Không còn business work đang xử lý |
| 3. Resolve in-flight | Rollback batch dở, đóng sessions/connections sạch | Delivering/inflight = 0 hoặc đã ghi rõ ngoại lệ |
| 4. Stop source | Dừng broker nguồn sạch nếu export offline | Process đã dừng; store snapshot nhất quán |
| 5. Export/transfer | Chạy store exporter hoặc wire pump theo manifest | Export log/checksum hoàn tất; số lượng source khớp manifest |
| 6. Import target | Import vào broker đích; chưa mở business consumers | Import exit code thành công, target queue/subscription tồn tại |
| 7. Reconcile | Đối chiếu counts, IDs, headers, TTL, ordering, DLQ | Không còn chênh lệch không giải thích |
| 8. Fence source | Chặn client reconnect, disable acceptor/credentials hoặc isolate network | Không thể có producer/consumer ghi/đọc nhầm broker cũ |
| 9. Switch endpoint | Chuyển producer và consumer sang target | Health check, auth, send/receive smoke test PASS |
| 10. Resume | Mở producers trước/consumer theo runbook đã định | Backlog drain đúng, không phát sinh duplicate/loss bất thường |

Một số hệ thống có thể bật consumers đích trước producers để drain backlog cũ, sau đó mới mở ingress; hệ thống khác cần bật producers trước để test routing. Chọn thứ tự theo dependency, nhưng giữ nguyên nguyên tắc **không có hai broker cùng xử lý một logical subscription**.

### 9.3. Watermark khi không thể dừng producer lâu

Nếu downtime ngắn hơn thời gian export/import, có thể dùng hai pha:

1. Chụp/export backlog ban đầu tại watermark W0.
2. Chuyển producers sang cơ chế ghi outbox/checkpoint hoặc bridge có thể xác định chính xác message mới sau W0.
3. Chuyển backlog snapshot sang target.
4. Chuyển delta sau W0 theo sequence/eventId, bảo đảm không có khoảng trống và có dedup.
5. Dừng ingress ngắn, chốt watermark cuối W1, chuyển phần delta còn lại.
6. Reconcile source/target tới W1 rồi mới mở hoàn toàn.

Chỉ dùng phương án này khi có **watermark có thể kiểm chứng** (sequence/offset/outbox ID) và cơ chế chống dual processing. Timestamp message không phải watermark an toàn nếu clock lệch, message đến trễ hoặc producer retry sau thời điểm snapshot.

## 10. Chuyển durable subscription đúng cách

### 10.1. Một subscription là một luồng dữ liệu độc lập

Tạo manifest riêng cho từng durable subscription:

~~~yaml
topic: orders.events
clientId: billing-v1
subscriptionName: billing-orders
selector: "eventType = 'OrderCreated'"
noLocal: false
sourceQueueOrSubscription: "<resolved-by-source-management>"
targetAddress: orders.events
targetQueueOrFqqn: "<resolved-on-artemis>"
readyCount: 120
deliveringCount: 0
scheduledCount: 0
~~~

Các placeholder trong manifest phải được thay bằng queue/subscription thật do management API của broker trả về. Không đoán tên internal queue của Classic hoặc Artemis dựa trên một subscription khác.

### 10.2. Dừng và chuyển từng subscription

1. Ghi `clientID`, subscription name, selector, topic, durable/shared type và queue nội bộ.
2. Ngừng subscriber ứng dụng trên source; chờ callback hoàn tất.
3. Commit transaction đã xong; rollback transaction đang dở; xác nhận không còn delivery đang hoạt động.
4. Dùng exporter có mapping đã test, hoặc wire-consume đúng **subscription đó**.
5. Tạo/kiểm tra target subscription với identity/selector tương ứng; giữ consumer target ở trạng thái dừng.
6. Nạp backlog vào đúng target subscription queue (FQQN/queue mapping) theo manifest.
7. So sánh count và eventId của subscription nguồn với queue đích.
8. Sau khi endpoint chuyển, chỉ subscriber target được mở lại với identity đã thống nhất.

Không đọc durable backlog bằng cách subscribe tạm thời vào topic chung rồi publish lại từng message lên target topic khi nhiều durable subscriptions đang tồn tại. Cách đó có thể nhân mỗi message cho tất cả subscriptions, kể cả subscriber không có bản sao message ấy ở nguồn.

### 10.3. Virtual topic khác durable topic subscription tiêu chuẩn

Classic Virtual Topic thường tạo một consumer queue riêng theo tên như `Consumer.A.VirtualTopic.Orders`. Mỗi queue consumer là backlog chia sẻ cho nhóm consumer của queue đó. Với Artemis, queue này có thể được biểu diễn bằng FQQN `VirtualTopic.Orders::Consumer.A.VirtualTopic.Orders` và OpenWire acceptor có thể map convention bằng `virtualTopicConsumerWildcards`.

Với durable subscription JMS tiêu chuẩn, identity dựa vào cặp `clientID + subscriptionName`; không áp dụng tên queue virtual topic vào mọi subscription. Nếu hệ thống đang dùng JMS 2 shared subscription, ghi rõ shared/unshared semantics và test cách Artemis tạo queue. Nếu ứng dụng thay đổi `clientID` hoặc subscription name sau migration, broker có thể tạo một subscription mới và backlog cũ sẽ không tự xuất hiện.

### 10.4. Persistent và non-persistent publications

Classic durable topic subscription giữ lại các publication **persistent** khi subscriber offline. Non-persistent message không có bảo đảm lưu backlog cho subscriber offline. Vì vậy:

- Inventory durable backlog phải phân biệt delivery mode.
- Không dựa vào số message producer đã gửi để suy ra số message subscriber phải nhận.
- Nếu migration gửi persistent tất cả message để bảo vệ transfer, lưu mode nguồn vào audit và thống nhất contract target.
- Không “khôi phục” non-persistent publication đã mất trước migration bằng cách replay từ log ứng dụng nếu nghiệp vụ không cho phép tạo event mới.


## 11. Reconciliation: chứng minh dữ liệu đã chuyển đủ

### 11.1. Đối chiếu theo destination và subscription

| Kiểm tra | Nguồn | Đích | Điều kiện |
|---|---:|---:|---|
| Queue ready count | Snapshot/final export | Imported queue count | Chênh lệch phải giải thích |
| Delivering count | Final source | Target trước resume | Không mang delivery lock qua broker |
| Durable backlog | Từng source subscription | Từng target subscription queue | So riêng từng identity |
| Scheduled count | Scheduled source | Scheduled/translated target | Không mất due time |
| DLQ/expiry count | DLQ/expiry source | DLQ/expiry target | Không nhập nhầm vào live queue |
| Event ID set | Stable IDs | Stable IDs | Không thiếu ID; duplicate được định lượng |
| Payload checksum | Body hash theo codec | Body hash theo codec | Hash khớp trên mẫu/toàn bộ nếu khả thi |

Không so tổng count của topic với tổng count của mọi durable subscriptions rồi gọi đó là số message gốc. Một publication có thể tạo nhiều bản sao logic trên nhiều durable subscriptions. Hãy so **từng queue/subscription**.

### 11.2. Kiểm tra thứ tự và thời hạn

Nếu nghiệp vụ yêu cầu thứ tự theo `aggregateId`, đối chiếu sequence liên tiếp trên từng partition/key. Message priority, redelivery và concurrent consumers có thể khiến thứ tự quan sát khác với thứ tự publish. Nếu không có sequence do ứng dụng cấp, không thể chứng minh strict business order chỉ bằng `JMSMessageID`.

Kiểm tra:

- Message đã hết hạn không bị hồi sinh do TTL được tính lại từ đầu.
- `JMSPriority`, group ID và group sequence được bảo toàn theo mapping.
- Scheduled/delayed messages không bị chuyển thành ready ngay lập tức.
- DLQ, expiry queue và redelivery policy không bị nhập nhầm destination.
- Body bytes/text, application properties, correlation ID và reply-to mapping đúng.
- `ObjectMessage`/custom codec được deserialize ở consumer target.

### 11.3. Bộ đếm và digest theo eventId

Nếu mỗi message có eventId, tạo manifest đã sort theo destination và ID, sau đó so sánh count và digest. Pseudocode:

~~~text
for each logical stream:
    sourceIds = sorted(eventId from frozen source export)
    targetIds = sorted(eventId from target before consumers start)

    assert count(sourceIds) == count(targetIds)
    assert sourceIds == targetIds
    assert hash(sourceIds) == hash(targetIds)
~~~

Nếu duplicate là kết quả at-least-once đã được chấp nhận, so sánh tập ID duy nhất và số lần xuất hiện riêng. Không xóa duplicate trước khi lưu audit. Nếu không có eventId, tạo checksum trên tuple destination + body hash + correlation + application properties; nhưng hai message nghiệp vụ giống hệt payload có thể hợp lệ, nên checksum không thay thế unique business identity.

## 12. Rollback và tiêu chí dừng migration

### 12.1. Trước khi mở ingress trên target

Nếu validation thất bại trước khi producers/consumers chuyển sang target:

1. Giữ source broker nguyên trạng và không cho ghi mới.
2. Dừng target consumers và pump.
3. Lưu log, import manifest, counts và eventId đã chuyển.
4. Nếu source vẫn còn dữ liệu đầy đủ, đưa endpoint về source theo quyết định cutover owner.
5. Xóa/reset target chỉ trong môi trường migration đã được xác nhận không có business writes; không purge destination mù.
6. Điều tra mapping, selector, unsupported message type hoặc store export trước lần thử lại.

### 12.2. Sau khi target đã nhận business writes

Không chỉ đổi DNS về source. Target có thể đã nhận message mới và consumers có thể đã commit side effects; source đã lỗi thời. Rollback lúc này là **một migration ngược**:

- Freeze ingress/consumer ở target.
- Chốt watermark cuối, eventId và các transaction chưa ACK.
- Chuyển message mới/đang chờ từ target về source theo cùng at-least-once + dedup.
- Reconcile source/target và side effects của downstream.
- Chỉ bật source sau khi chứng minh không còn consumer target xử lý cùng logical stream.

Nếu không có reverse-transfer plan và business idempotency, đặt rollback window trước cutover; sau khi target nhận dữ liệu mới, có thể phải chọn forward-fix thay vì rollback.

### 12.3. Các điều kiện phải dừng cutover

- Source vẫn còn producer hoặc consumer không thể fence.
- Delivering/in-flight không giải thích được.
- Durable subscription không xác định được identity hoặc queue backlog.
- Exporter bỏ sót virtual topic/subscription hoặc selector mapping.
- Message body type không hỗ trợ, TTL/priority/scheduled delivery bị thay đổi ngoài dự kiến.
- Count/eventId digest có chênh lệch không giải thích.
- Target disk capacity/security/authorization chưa sẵn sàng.
- Không có phương án xử lý commit outcome bất định và duplicate.

## 13. Lịch thực hành migration cho một hệ thống mẫu

Giả sử Classic có queue `orders.pending`, topic `orders.events`, ba durable subscriptions Billing/Search/Audit và DLQ `ActiveMQ.DLQ`. Artemis target có address/queue đã cấu hình.

| Pha | Việc thực hiện | Bằng chứng lưu lại |
|---|---|---|
| T-7 ngày | Inventory, rehearsal, destination mapping, test message types | Manifest, thời gian export/import, checklist |
| T-1 ngày | Freeze config, backup store, kiểm tra disk và credentials | Backup ID, checksums, broker versions |
| T0-30 phút | Dừng producers, drain consumers, rollback transaction dở | Producer=0, delivering=0, session status |
| T0 | Stop Classic sạch; export KahaDB hoặc bắt đầu wire transfer | Export file/checksum, export log |
| T+ | Import target; nạp từng durable backlog đúng queue | Import log, queue/subscription counts |
| T+ validation | So eventId, payload, TTL, priority, scheduled, DLQ | Reconciliation report |
| T+ cutover | Fence Classic, đổi endpoint, mở target consumers/producers | Connection audit, smoke tests |
| T+1 giờ | Theo dõi redelivery, duplicate, queue age, throughput | Metrics và incident log |
| T+rollback window | Giữ source snapshot read-only, chưa purge | Sign-off của owner |

### 13.1. Smoke test sau cutover

- Gửi một event mới vào queue đích; xác nhận đúng một consumer xử lý.
- Publish một event vào topic; xác nhận từng durable subscription đủ điều kiện nhận một bản.
- Tắt một durable subscriber, publish persistent event, bật lại và xác nhận subscriber nhận backlog offline.
- Gửi message có TTL ngắn và scheduled delay; xác nhận expiry/delivery time.
- Rollback một transacted receive trong target lab; xác nhận redelivery và delivery count.
- Gửi message lỗi vượt max delivery attempts; xác nhận DLQ routing.
- Kiểm tra `eventId`, correlation, group ID và payload codec ở consumer target.

## 14. Checklist trước khi ký nghiệm thu

### Data inventory và mapping

- [ ] Mọi queue/topic/virtual topic/DLQ/expiry destination đã có manifest.
- [ ] Queue ready, delivering, scheduled và in-flight được ghi riêng.
- [ ] Mỗi durable subscription có clientID, name, selector, noLocal, type và backlog riêng.
- [ ] Target address/queue routing type ANYCAST/MULTICAST đã xác minh.
- [ ] Large messages, custom codecs, ObjectMessage, scheduled và TTL có test riêng.

### Cutover và transaction

- [ ] Producer ingress được freeze hoặc có watermark/delta đáng tin cậy.
- [ ] Consumer callback đã drain; transacted batch dở đã rollback.
- [ ] Delivering count bằng 0 hoặc có danh sách ngoại lệ được xử lý.
- [ ] Export chỉ chạy trên store snapshot/stopped broker khi công cụ yêu cầu.
- [ ] Wire pump commit target trước source và ghi checkpoint/eventId.
- [ ] Source được fence trước khi target nhận toàn bộ traffic.

### Reconciliation và rollback

- [ ] Count theo từng queue/subscription khớp.
- [ ] EventId set/digest, payload, TTL, priority, ordering đã kiểm tra.
- [ ] Duplicate window và idempotency downstream đã được test.
- [ ] DLQ/expiry/scheduled messages không bị bỏ sót.
- [ ] Có rollback/reverse-transfer plan sau khi target bắt đầu nhận writes.
- [ ] Source snapshot được giữ read-only trong rollback window; chưa purge khi chưa ký nghiệm thu.

## 15. Câu hỏi tự kiểm tra

1. Vì sao không thể copy trực tiếp KahaDB journal sang Artemis journal?
2. Vì sao ba durable subscriptions trên cùng topic có thể có ba backlog khác nhau?
3. Vì sao một topic browse không đủ để chứng minh durable subscription backlog đã chuyển?
4. Prefetch lớn có thể làm queue ready count giảm dù application chưa xử lý xong như thế nào?
5. Nếu target commit thành công nhưng source commit thất bại, rủi ro nào xuất hiện?
6. Vì sao `JMSMessageID` không nên là idempotency key xuyên broker?
7. Vì sao phải giữ `clientID`, subscription name và selector?
8. Tại sao publish lại backlog của từng durable subscription lên multicast topic có thể tạo duplicate?
9. Nếu producer không thể dừng, watermark phải dựa vào thông tin nào?
10. Sau khi target đã nhận business writes, vì sao không thể chỉ đổi DNS quay về source?
11. Message hết hạn trong lúc migration cần xử lý ra sao?
12. Điều kiện nào chứng minh một cutover đã an toàn: queue count tổng hay reconciliation theo từng logical stream?

**Gợi ý đáp án:** (1) Store format/paging khác; (2) mỗi subscriber giữ bản sao theo thời điểm, selector và ACK; (3) topic không browse như queue, cần kiểm tra subscription queue; (4) dispatch/prefetch đưa message vào client buffer; (5) source redeliver tạo duplicate target; (6) target có thể sinh ID mới; (7) broker dùng chúng để nhận diện durable subscription; (8) multicast nhân message tới mọi subscription đang hoạt động; (9) sequence/outbox/offset ổn định; (10) target đã có message mới và side effects; (11) giữ TTL còn lại hoặc đưa vào expiry workflow; (12) đối chiếu count, IDs, payload và state của từng queue/subscription.

## 16. Tài liệu chính thức

- [Apache ActiveMQ Artemis — Message Store Migration](https://artemis.apache.org/components/artemis/migration-documentation/message-store.html): KahaDB/mKahaDB export, XML exchange và virtual-topic consumer mapping.
- [Apache ActiveMQ Artemis — Data Tools](https://artemis.apache.org/components/artemis/documentation/latest/data-tools.html): `artemis data exp`, `artemis data imp`, các tùy chọn import và lưu ý broker đang chạy.
- [Apache ActiveMQ Artemis — OpenWire](https://artemis.apache.org/components/artemis/documentation/latest/openwire.html): Classic JMS client kết nối Artemis, acceptor và virtual topic consumer mapping.
- [Apache ActiveMQ Artemis — Key Differences](https://artemis.apache.org/components/artemis/migration-documentation/key-differences.html): KahaDB vs Artemis journal, paging và address/routing model.
- [Apache ActiveMQ Artemis — Virtual Topics](https://artemis.apache.org/components/artemis/migration-documentation/VirtualTopics.html): FQQN và ánh xạ virtual-topic consumer queue.
- [ActiveMQ Classic — Durable Queues and Topics](https://activemq.apache.org/components/classic/documentation/how-do-durable-queues-and-topics-work): durable queue, durable topic, clientID và subscription name.
- [ActiveMQ Classic — Durable Topic Subscription Persistence](https://activemq.apache.org/components/classic/documentation/why-do-i-not-receive-messages-on-my-durable-topic-subscription): persistent delivery mode cho subscriber offline.
- [Apache ActiveMQ CLI Tools](https://github.com/apache/activemq-cli-tools): công cụ export KahaDB/mKahaDB sang Artemis XML format.

**Kết luận:** Migration backlog đáng tin cậy phải giữ được **quyền sở hữu message, ranh giới ACK/transaction và backlog riêng của từng durable subscription**. Freeze ingress, giải quyết in-flight, export/import hoặc wire-transfer theo manifest, giữ eventId ổn định, reconcile từng logical stream và fence broker cũ trước khi mở target. Chấp nhận at-least-once với idempotency có kiểm chứng; không coi hai transaction JMS độc lập là exactly-once xuyên broker.
