# Chuyển policy, redelivery, DLQ, expiry, bảo mật và giới hạn tài nguyên

> **Chương:** Di chuyển broker  
> **Phạm vi:** Chuyển các chính sách vận hành từ **ActiveMQ Classic** sang **ActiveMQ Artemis** (hoặc chuẩn hóa giữa hai broker): destination policy, redelivery, dead-letter queue (DLQ), expiry, authorization và resource limits. Trọng tâm là giữ nguyên **hành vi nghiệp vụ quan sát được**, không sao chép XML theo tên thuộc tính. Ví dụ cấu hình cần được kiểm tra trên đúng phiên bản broker/client trước khi áp dụng production.

## 1. Mục tiêu migration: chuyển semantics, không chuyển nguyên văn file cấu hình

Hai broker đều hỗ trợ JMS messaging, queue/topic, persistence và xử lý message lỗi, nhưng policy model và thời điểm thực thi khác nhau. Một cấu hình Classic có thể đặt flow control ở `destinationPolicy`, redelivery chủ yếu trong client policy và DLQ ở broker; Artemis thường đặt nhiều hành vi theo `address-settings`, với redelivery attempts và dead-letter routing được broker quản lý.

Một migration đạt yêu cầu cần chứng minh:

- Message hợp lệ vẫn được gửi/nhận theo đúng queue/address và routing type.
- Message lỗi được redeliver với delay/số lần thử phù hợp; poison message đi đúng DLQ.
- Message hết hạn được chuyển/xóa theo retention contract đã thống nhất.
- Producer, consumer, operator có đúng quyền send/consume/browse/manage.
- Khi resource đạt ngưỡng, broker backpressure hoặc từ chối theo đúng chính sách; không âm thầm mất message.
- Disk, memory, paging và DLQ có capacity, alert và runbook tương ứng.

**Không coi hai giá trị cùng tên là cùng semantics.** Ví dụ `memoryLimit` của Classic và `max-size-bytes` của Artemis không phải một quota disk giống nhau; `TempUsage` Classic không có một metric Artemis tương đương 1:1; `RedeliveryPolicy` ở Classic client không phải `max-delivery-attempts` ở Artemis broker.

## 2. Lập inventory policy hiệu lực trên Classic trước khi viết cấu hình đích

Đừng chỉ đọc một block XML rồi kết luận đó là policy đang chạy. Thu thập cấu hình khởi động, plugin được nạp, URI của client, destination thực tế và override ở từng ứng dụng.

| Nhóm | Classic cần inventory | Câu hỏi phải trả lời |
|---|---|---|
| Destination mapping | Queue/topic names, wildcard `*`/`>` và virtual destinations nếu có | Destination nào thực sự được tạo và route? |
| Destination policy | `policyEntry`, `memoryLimit`, `producerFlowControl`, cursor/prefetch liên quan | Queue nào dùng policy nào? |
| Redelivery | Client `RedeliveryPolicy`, transaction rollback, maximum redeliveries, delay | Lần giao lại đầu tiên và lần cuối cùng cách nhau bao lâu? |
| DLQ | `sharedDeadLetterStrategy`/`individualDeadLetterStrategy`, prefix, process expired/non-persistent | Message nào vào DLQ? Queue DLQ tên gì? |
| Expiry | Producer TTL/JMSExpiration, `expireMessagesPeriod`, expiry plugin/consumer | Message hết hạn được scan và xử lý ra sao? |
| Security | Authentication plugin, authorization entries, groups, JAAS/LDAP/SSL | Role nào send, consume, browse, admin? |
| Resource | `systemUsage` memory/store/temp, KahaDB path, filesystem, temp path | Giới hạn logic và capacity vật lý là bao nhiêu? |
| Client behavior | Persistent delivery, transacted session, async send, failover URI, prefetch | Client có giả định gì về confirmation/retry? |

Tạo một bảng policy **theo destination pattern** với các cột: pattern nguồn, destination đích, routing type, producer role, consumer role, redelivery attempts/delay, DLQ, expiry, memory/backpressure, owner và test case. Ghi cả ngoại lệ riêng của queue quan trọng; wildcard rộng có thể che một policy cụ thể.

### 2.1 Phân biệt wildcard Classic và Artemis

| Ý nghĩa | Classic | Artemis |
|---|---|---|
| Một segment/từ | `*` | `*` |
| Nhiều segment | `>` | `#` |
| Ví dụ match `orders.created` | `orders.*` | `orders.*` |
| Ví dụ match cây `orders.eu.created` | `orders.>` | `orders.#` |

Hai wildcard nhiều segment có thể khác nhau ở trường hợp không có segment con (ví dụ destination đúng bằng `orders`). Hãy test cả `orders`, `orders.eu` và `orders.eu.created`; không giả định thay `>` bằng `#` luôn tương đương. Thứ tự ưu tiên và cách chọn address-setting cụ thể hơn cũng phải kiểm tra trên Artemis version đang triển khai.

## 3. Bảng ánh xạ policy Classic → Artemis

| Nhu cầu | ActiveMQ Classic | ActiveMQ Artemis | Việc phải xác minh |
|---|---|---|---|
| Destination-level memory | `policyEntry memoryLimit` | `address-setting max-size-bytes` | Đơn vị/đối tượng tính và address mapping |
| Producer backpressure | `producerFlowControl` + SystemUsage | `address-full-policy=BLOCK` hoặc `PAGE` | Block hay spill-to-disk là hành vi khác nhau |
| Persistent store cap | `storeUsage` + persistence adapter | Journal/paging filesystem capacity và memory/address policy | Không có một `storeUsage` byte-limit tương đương trực tiếp |
| Temporary store | `tempUsage` và cursor behavior | Memory/paging/temporary queue lifecycle | Không map `TempUsage` thành một metric giả |
| Redelivery | Client `RedeliveryPolicy` + rollback | Broker `max-delivery-attempts`, delay, multiplier | Số lần giao, lần tính đầu và rollback semantics |
| DLQ | Shared/individual dead-letter strategy | `dead-letter-address` và queue đích | Naming, routing type, ACL, retention |
| Expiry | JMS TTL + expiration scan/policy | `expiry-address`, `expiry-delay`, expiry scan | Message nào có TTL, nơi nhận expired message |
| Authentication | Simple/JAAS/LDAP plugin | Security manager/JAAS/LDAP phù hợp | Identity source và credential rotation |
| Authorization | `authorizationEntry` read/write/admin | `security-setting` permission theo address | Quyền browse/manage và auto-create |
| Topic durable backlog | Durable subscription destination | Multicast subscription queue | Offline backlog, naming và retention |

**Bảng ánh xạ là điểm bắt đầu, không phải bộ chuyển đổi tự động.** Với mỗi dòng phải có test chứng minh kết quả ở broker đích. Nếu không thể giữ semantics, ghi nhận khác biệt và xin quyết định owner nghiệp vụ trước cutover.

## 4. Redelivery: chuyển từ client policy sang broker policy có chủ đích

### 4.1 Classic client và Artemis broker quản lý retry ở đâu?

Trong Classic, `RedeliveryPolicy` thường được cấu hình trên client OpenWire để xác định delay và số lần redelivery khi session rollback/connection failure. Broker DLQ strategy xử lý message bị poison/được client từ chối sau khi vượt ngưỡng theo protocol/provider. Vì policy có thể khác giữa các consumer client, hai ứng dụng cùng đọc một queue có thể có retry behavior khác nhau.

Artemis có thể quản lý redelivery theo address setting: `max-delivery-attempts`, `redelivery-delay`, `redelivery-multiplier`, `max-redelivery-delay`. Khi chuyển, cần quyết định **một nguồn policy có thẩm quyền** và đồng bộ client behavior; không để retry loop ở application cộng dồn với broker retry một cách không kiểm soát.

### 4.2 Ví dụ Classic client policy

```java
import org.apache.activemq.ActiveMQConnectionFactory;
import org.apache.activemq.RedeliveryPolicy;

ActiveMQConnectionFactory factory =
        new ActiveMQConnectionFactory("tcp://classic.example:61616");

RedeliveryPolicy redelivery = new RedeliveryPolicy();
redelivery.setInitialRedeliveryDelay(1000);
redelivery.setRedeliveryDelay(2000);
redelivery.setUseExponentialBackOff(true);
redelivery.setBackOffMultiplier(2.0);
redelivery.setMaximumRedeliveries(5);
factory.setRedeliveryPolicy(redelivery);
```

Đây là cấu hình phía Classic client. Khi inventory, xác minh factory thực tế mà ứng dụng dùng; một consumer có thể dùng factory khác hoặc URI override. `maximumRedeliveries` phải được diễn giải cùng lần delivery đầu và broker/provider behavior, không suy ra số tổng attempts chỉ từ con số cấu hình.

### 4.3 Ví dụ Artemis address settings

Ví dụ cho các queue thuộc address `orders`:

```xml
<address-settings>
    <address-setting match="orders.#">
        <redelivery-delay>1000</redelivery-delay>
        <redelivery-multiplier>2.0</redelivery-multiplier>
        <max-redelivery-delay>30000</max-redelivery-delay>
        <max-delivery-attempts>5</max-delivery-attempts>
    </address-setting>
</address-settings>
```

Giá trị là ví dụ: delay đầu 1 giây, tăng theo multiplier và bị chặn ở 30 giây. Test chuỗi thời gian thực tế theo broker version, transaction rollback, consumer crash và reconnect. Không chỉ kiểm tra property trong XML; phải đo timestamp từng lần nhận lại.

### 4.4 Chuyển đổi retry budget

So sánh hai cấu hình bằng **timeline**, không chỉ so `5` với `5`:

```text
attempt 1: initial delivery
attempt 2: first redelivery after delay
attempt 3..N: later redeliveries with configured backoff
final: route to DLQ or apply provider-specific terminal behavior
```

Tạo test consumer rollback có chủ ý và test process crash. Ghi delivery count, redelivered flag, delay giữa các lần nhận, thời điểm vào DLQ. Nếu Classic application còn tự gửi retry message sang queue khác, tách luồng đó khỏi broker redelivery trước khi migration; nếu không, cùng một lỗi có thể nhân số lần retry.

## 5. DLQ: chuyển destination và quyền sở hữu message lỗi

### 5.1 Classic individual dead-letter strategy

Classic có thể dùng DLQ riêng theo queue để operator biết message đến từ destination nào:

```xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue="orders.>">
                <deadLetterStrategy>
                    <individualDeadLetterStrategy
                        queuePrefix="DLQ."
                        useQueueForQueueMessages="true"
                        processExpired="false"
                        processNonPersistent="false"/>
                </deadLetterStrategy>
            </policyEntry>
        </policyEntries>
    </policyMap>
</destinationPolicy>
```

Ví dụ message từ `orders.created` được đưa tới `DLQ.orders.created` theo individual strategy. `processExpired` và `processNonPersistent` là quyết định nghiệp vụ: có đưa message hết hạn/non-persistent vào DLQ hay không. Hãy kiểm tra hành vi thực tế của phiên bản Classic và policy đang dùng; đừng lấy default của broker khác làm chuẩn.

### 5.2 Artemis dead-letter address và queue

Artemis định tuyến message vượt delivery attempts tới dead-letter address. Cần tạo address/queue đích rõ ràng và cấp quyền cho operator:

```xml
<address-settings>
    <address-setting match="orders.#">
        <dead-letter-address>DLQ</dead-letter-address>
        <max-delivery-attempts>5</max-delivery-attempts>
        <redelivery-delay>1000</redelivery-delay>
    </address-setting>
</address-settings>

<addresses>
    <address name="DLQ">
        <anycast>
            <queue name="DLQ"/>
        </anycast>
    </address>
</addresses>
```

Đây là shared DLQ address cho ví dụ. Nếu nguồn Classic có individual DLQ theo từng queue, có thể tạo DLQ address/queue riêng hoặc quy ước property/header nguồn; không dồn mọi message vào một queue mà mất khả năng truy nguyên. Xác minh routing type `ANYCAST` và mapping address/queue đúng với JMS queue đích.

### 5.3 Checklist DLQ parity

- [ ] Cùng loại message nào được chuyển vào DLQ: poison, rollback quá số lần, expired hay non-persistent?
- [ ] Tên DLQ giữ được nguồn gốc queue/address.
- [ ] Original destination, event ID, correlation ID, exception/reason và delivery count được bảo toàn hoặc bổ sung.
- [ ] DLQ có persistence phù hợp và capacity/retention riêng.
- [ ] Producer không có quyền ghi trực tiếp vào DLQ nếu không cần.
- [ ] Consumer nghiệp vụ không vô tình consume DLQ.
- [ ] Operator có quyền browse/replay/purge đúng phạm vi.
- [ ] Replay giữ event ID hoặc idempotency key; có rate limit và audit.
- [ ] Alert khi DLQ tăng theo count, bytes và oldest age.

Không replay hàng loạt trước khi sửa nguyên nhân poison message. Replay phải có phê duyệt, giới hạn tốc độ và cơ chế tránh duplicate business effect.

## 6. Expiry: chuyển TTL và xử lý message hết hạn

### 6.1 TTL do producer đặt và expiry do broker thực thi

JMS producer có thể đặt time-to-live (TTL) khi gửi. Broker ghi expiration timestamp; khi message hết hạn, nó không còn đủ điều kiện giao cho consumer. Migration phải giữ được:

- TTL do producer gửi (hoặc chính sách TTL mặc định nếu có).
- Độ chính xác thời gian và clock synchronization giữa producer/broker.
- Nơi nhận message hết hạn: bỏ, chuyển expiry destination/address hoặc workflow audit.
- Chu kỳ broker quét và dọn message hết hạn.
- Tác động của expiry tới DLQ, durable subscription và backlog.

Không nhầm **expiry** với **redelivery**. Redelivery là message chưa được xác nhận; expiry là message đã quá hạn sử dụng. Không nên replay message hết hạn như message lỗi nếu nghiệp vụ không cho phép.

### 6.2 Classic: TTL từ producer và expiration scan

Producer có thể đặt TTL theo JMS:

```java
MessageProducer producer = session.createProducer(queue);
producer.setTimeToLive(60_000); // 60 giây
producer.send(message);
```

Classic destination policy có thể điều khiển chu kỳ kiểm tra expired messages:

```xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue="orders.>"
                         expireMessagesPeriod="1000">
                <deadLetterStrategy>
                    <individualDeadLetterStrategy
                        queuePrefix="DLQ."
                        useQueueForQueueMessages="true"
                        processExpired="false"/>
                </deadLetterStrategy>
            </policyEntry>
        </policyEntries>
    </policyMap>
</destinationPolicy>
```

`expireMessagesPeriod` là chu kỳ scan tính bằng milliseconds trong cấu hình Classic. Giá trị 1000 chỉ là ví dụ lab. `processExpired` quyết định message hết hạn có được dead-letter strategy xử lý như DLQ message hay không; nếu cần audit expiry, định nghĩa rõ destination riêng và test với đúng phiên bản. Không mặc định rằng message hết hạn sẽ xuất hiện trong DLQ.

### 6.3 Artemis: expiry address

Artemis có thể chuyển message hết hạn tới expiry address. Ví dụ:

```xml
<address-settings>
    <address-setting match="orders.#">
        <expiry-address>ExpiryQueue</expiry-address>
    </address-setting>
</address-settings>

<addresses>
    <address name="ExpiryQueue">
        <anycast>
            <queue name="ExpiryQueue"/>
        </anycast>
    </address>
</addresses>
```

Nếu dùng `expiry-delay`, kiểm tra đúng semantics của phiên bản: đây là TTL áp cho message chưa có expiration được đặt sẵn, không nên vô tình ghi đè TTL do producer gửi. Expiry address cần có queue/routing type và ACL phù hợp; nếu không có expiry destination, message có thể bị loại bỏ theo broker behavior.

### 6.4 Expiry parity test

Gửi cùng một message profile với TTL 5 giây vào cả broker nguồn và đích:

1. Gửi một message persistent, không có consumer.
2. Gửi một message non-persistent nếu workload có dùng.
3. Ghi `JMSExpiration`/expiration metadata và thời điểm send.
4. Chờ quá TTL cộng scan interval; kiểm tra message không còn được giao cho consumer nghiệp vụ.
5. Kiểm tra expiry destination/address hoặc DLQ theo policy đã định.
6. Kiểm tra durable topic subscription offline: message hết hạn không được giữ lâu hơn contract.

So sánh **thời điểm message biến mất/được chuyển**, không chỉ kiểm tra XML có `expiry-address`. Chênh lệch scan interval có thể làm message tồn tại lâu hơn TTL một khoảng thời gian; nếu SLA expiry nghiêm ngặt, đo worst-case.

## 7. Bảo mật: chuyển identity, role và permission

### 7.1 Tách authentication và authorization

- **Authentication:** xác định client là ai (username/password, certificate, LDAP/JAAS hoặc identity provider).
- **Authorization:** client được phép send, consume, browse hoặc manage destination nào.
- **Transport security:** TLS bảo vệ đường truyền và xác thực server/client certificate theo cấu hình.
- **Secret lifecycle:** rotation, revoke, expiry, audit và lưu secret ngoài file cấu hình/source control.

Không chuyển user/password nguyên văn từ file Classic sang broker mới. Tạo identity/role đích, xác minh certificate/trust chain, rotate secret và kiểm tra negative permission trước cutover.

### 7.2 Classic: authentication plugin và authorization map

Ví dụ cấu hình Classic với simple authentication và authorization plugin:

```xml
<plugins>
    <simpleAuthenticationPlugin>
        <users>
            <authenticationUser username="orders-producer"
                                password="REPLACE_FROM_SECRET_STORE"
                                groups="order-producers"/>
            <authenticationUser username="orders-consumer"
                                password="REPLACE_FROM_SECRET_STORE"
                                groups="order-consumers"/>
            <authenticationUser username="dlq-operator"
                                password="REPLACE_FROM_SECRET_STORE"
                                groups="dlq-operators"/>
        </users>
    </simpleAuthenticationPlugin>

    <authorizationPlugin>
        <map>
            <authorizationMap>
                <authorizationEntries>
                    <authorizationEntry queue="orders.>"
                        read="order-consumers"
                        write="order-producers"
                        admin="broker-admins"/>
                    <authorizationEntry queue="DLQ.>"
                        read="dlq-operators"
                        write="broker-admins"
                        admin="broker-admins"/>
                </authorizationEntries>
            </authorizationMap>
        </map>
    </authorizationPlugin>
</plugins>
```

Đây là minh họa plugin local; với production có thể dùng JAAS/LDAP/certificate integration. Thay placeholder password bằng secret injection phù hợp. Producer chỉ cần quyền write vào `orders.>`; consumer cần read; operator DLQ chỉ cần read/browse/replay theo workflow được cấp. `admin` là quyền quản trị destination theo authorization map, không cấp rộng cho user ứng dụng.

### 7.3 Artemis: permission theo address pattern

Artemis định nghĩa quyền theo `security-setting` và role. Ví dụ:

```xml
<security-settings>
    <security-setting match="orders.#">
        <permission type="send" roles="order-producers"/>
        <permission type="consume" roles="order-consumers"/>
        <permission type="browse" roles="order-operators"/>
        <permission type="createDurableQueue" roles="broker-admins"/>
        <permission type="deleteDurableQueue" roles="broker-admins"/>
        <permission type="manage" roles="broker-admins"/>
    </security-setting>

    <security-setting match="DLQ">
        <permission type="consume" roles="dlq-operators"/>
        <permission type="browse" roles="dlq-operators"/>
        <permission type="send" roles="broker-admins"/>
        <permission type="manage" roles="broker-admins"/>
    </security-setting>
</security-settings>
```

Đây là permission mapping; role membership phải được cấp bởi security manager/JAAS/LDAP đang dùng. Nếu queue được auto-create, kiểm thêm quyền create address/queue cần thiết; không cấp quyền create/delete cho mọi producer chỉ để tránh lỗi provisioning. Với DLQ, operator cần browse/consume; replay có thể cần send tới destination nguồn và phải được audit.

### 7.4 Security parity phải có positive và negative tests

| Identity | Send orders | Consume orders | Browse DLQ | Manage broker |
|---|---:|---:|---:|---:|
| order-producer | Allow | Deny | Deny | Deny |
| order-consumer | Deny | Allow | Deny | Deny |
| dlq-operator | Deny | Deny | Allow | Deny |
| broker-admin | Theo policy | Theo policy | Theo policy | Allow |

Kiểm cả trường hợp bị từ chối. Một migration chỉ test user hợp lệ có thể vô tình mở quyền quá rộng. Ghi broker-side authorization failure và xác minh client không fallback sang anonymous connection.

## 8. Giới hạn tài nguyên: không chuyển byte limit một cách máy móc

### 8.1 Classic: SystemUsage và destination memory limit

Classic có thể đặt giới hạn memory/store/temp ở broker:

```xml
<systemUsage>
    <systemUsage>
        <memoryUsage>
            <memoryUsage limit="512 mb"/>
        </memoryUsage>
        <storeUsage>
            <storeUsage limit="80 gb"/>
        </storeUsage>
        <tempUsage>
            <tempUsage limit="20 gb"/>
        </tempUsage>
    </systemUsage>
</systemUsage>
```

Destination có thể có `memoryLimit` và `producerFlowControl`. Các giới hạn này điều khiển broker usage/backpressure, không phải hard quota do filesystem enforce. Khi chuyển, đo heap/RSS, store bytes, temp bytes và disk free thật; không lấy riêng phần trăm JMX làm capacity vật lý.

### 8.2 Artemis: global memory, address threshold và paging policy

Ví dụ:

```xml
<core>
    <global-max-size>536870912</global-max-size>
    <address-settings>
        <address-setting match="orders.#">
            <max-size-bytes>67108864</max-size-bytes>
            <page-size-bytes>10485760</page-size-bytes>
            <address-full-policy>BLOCK</address-full-policy>
        </address-setting>
    </address-settings>
</core>
```

- `global-max-size` giới hạn memory budget toàn broker.
- `max-size-bytes` là ngưỡng memory theo address; không phải disk quota.
- `page-size-bytes` điều khiển kích thước page file; không đặt giới hạn tổng paging store.
- `BLOCK` tạo backpressure; `PAGE` chuyển message sang disk; `FAIL` từ chối; `DROP` có thể mất message.

Artemis không có bộ ba `memoryUsage/storeUsage/tempUsage` cùng semantics với Classic. Persistent journal, paging, large-message store và filesystem phải được đo riêng. Sizing disk dựa trên mount capacity trừ reserve và workload khác, không dựa vào `max-size-bytes`.

### 8.3 Bảng đối chiếu capacity

| Tài nguyên | Classic | Artemis | Cách nghiệm thu |
|---|---|---|---|
| Memory | `memoryUsage` + destination `memoryLimit` | `global-max-size` + address `max-size-bytes` | Heap/RSS và broker/address usage dưới ngưỡng |
| Persistent storage | `storeUsage` + KahaDB/JDBC | Journal filesystem | Persistent backlog test và disk growth |
| Temporary/non-persistent | `tempUsage` + cursor | Queue/address memory, paging và lifecycle | Test non-persistent và temporary destination |
| Paging | Cursor/store behavior tùy policy | Address paging theo PAGE | Page bytes, depage rate và disk reserve |
| Producer backpressure | `producerFlowControl` | BLOCK/FAIL hoặc PAGE | Send latency/exception và ingress rate |
| Disk exhaustion | Filesystem thực tế | Journal/paging/large-message filesystem | Free bytes/inodes, I/O latency và time-to-full |

Không quy đổi `storeUsage=80 gb` thành `max-size-bytes=80 gb`. Đó là hai lớp khác nhau. Đặt address memory threshold dựa trên heap/headroom; đặt disk capacity dựa trên backlog bytes, persistence overhead, page growth, DLQ và safety reserve.

## 9. Chuẩn hóa policy manifest trước khi triển khai

Không để policy chỉ tồn tại trong hai file XML. Tạo manifest có version, owner và test evidence để đối chiếu giữa source và target. Ví dụ một dòng cho luồng order:

| Trường | Giá trị minh họa |
|---|---|
| Source destination pattern | `orders.>` |
| Target address pattern | `orders.#` |
| Routing | Queue/ANYCAST |
| Producer role | `order-producers` |
| Consumer role | `order-consumers` |
| Redelivery | 5 attempts theo timeline đã đo; delay tăng tối đa 30 s |
| DLQ | `DLQ.orders.*` hoặc queue DLQ theo nguồn |
| Expiry | TTL do producer; hết hạn chuyển `ExpiryQueue` |
| Backpressure | Classic flow control; Artemis BLOCK |
| Capacity | Memory/address threshold và disk reserve đã benchmark |
| Owner | Team nghiệp vụ sở hữu order |
| Evidence | Test IDs R1–R8, S1–S4, C1–C5 |

Manifest cần ghi **effective policy**, không chỉ intended policy. Khi policy có ngoại lệ theo destination, tạo dòng riêng và ghi rõ pattern cụ thể hơn. Lưu phiên bản manifest cùng release để biết policy nào đang chạy tại thời điểm incident.

### 9.1 Kiểm tra xung đột wildcard

Giả sử có các pattern:

- `orders.#`: policy chung cho order.
- `orders.payment.#`: policy payment riêng.
- `orders.payment.refund`: policy cho refund queue.

Tạo test destination cho từng mức specificity, đồng thời kiểm tra destination không match pattern nào. Với Artemis, xác minh address-setting nào được chọn; với Classic, xác minh policyEntry được áp dụng. Không chỉ nhìn pattern trong file mà suy ra thứ tự ưu tiên.

### 9.2 Định nghĩa routing type tường minh

Queue Classic thường được chuyển thành address/queue ANYCAST trong Artemis; topic publication thường dùng MULTICAST với subscription queues. Nếu address có nhiều routing type hoặc JMS client auto-create destination, cần kiểm tra routing type mà client thực sự dùng. Không tạo một address có routing type không tương thích rồi coi lỗi send/consume là lỗi policy.

Ví dụ address/queue tường minh:

```xml
<addresses>
    <address name="orders">
        <anycast>
            <queue name="orders.created"/>
            <queue name="orders.payment"/>
        </anycast>
    </address>
    <address name="order-events">
        <multicast>
            <queue name="billing-subscription"/>
            <queue name="analytics-subscription"/>
        </multicast>
    </address>
</addresses>
```

Đây là minh họa mô hình routing; address/queue mapping thực tế cần khớp JMS destination và client configuration. Không tạo queue subscription mới mà không quyết định retention, consumer owner và expiry behavior.

## 10. Ma trận kiểm thử policy parity

Chạy trên broker lab/staging với cùng message profile, producer transaction mode, consumer behavior và thời gian đo. Ghi source/target result cạnh nhau; không chỉ ghi PASS/FAIL mà phải lưu số liệu và message IDs.

| ID | Nhóm | Kịch bản | Bằng chứng phải so sánh |
|---|---|---|---|
| R1 | Redelivery | Consumer rollback một lần | Redelivered flag, delivery count, delay |
| R2 | Redelivery | Consumer process crash sau receive | Reconnect time và lần giao lại |
| R3 | Redelivery | Vượt maximum attempts | Lần cuối cùng được giao và DLQ arrival |
| R4 | Redelivery | Backoff exponential | Timestamp từng attempt, max delay |
| D1 | DLQ | Poison message từ queue chính | DLQ name, original destination, eventId |
| D2 | DLQ | Message non-persistent lỗi | Có/không chuyển DLQ theo contract |
| D3 | DLQ | Message expired | Expiry destination hay DLQ hay discard |
| D4 | DLQ | Operator replay | Audit, rate limit, idempotent business effect |
| E1 | Expiry | TTL ngắn, không consumer | Expiration timestamp và thời điểm cleanup |
| E2 | Expiry | Durable subscription offline | Expired message không tồn tại quá contract |
| E3 | Expiry | Message không có TTL | Default expiry policy có đúng không |
| S1 | Security | Producer role send đúng address | Send success |
| S2 | Security | Producer thử consume | Authorization denied |
| S3 | Security | Consumer thử send | Authorization denied |
| S4 | Security | User thường browse/manage DLQ | Authorization denied |
| C1 | Capacity | Classic memory/store/temp threshold | Block/error, usage manager và recovery |
| C2 | Capacity | Artemis BLOCK | Producer block và resume sau drain |
| C3 | Capacity | Artemis PAGE | Page growth, disk reserve, depage |
| C4 | Capacity | Artemis FAIL | Exception và retry/backoff |
| C5 | Capacity | Disk gần đầy | Alert trước threshold, broker không corrupt |

### 10.1 Tiêu chí so sánh redelivery

Với cùng lỗi consumer, so:

- Số lần nhận tổng cộng (tách initial delivery và redelivery).
- Delay giữa từng lần nhận.
- Thời điểm message bị đưa vào DLQ.
- Header/property delivery count và redelivered flag.
- Queue backlog trong lúc retry và ảnh hưởng message khác.

Không đòi `JMSXDeliveryCount` phải có cùng giá trị ở mọi provider/version nếu semantics khác nhau; điều cần giữ là retry budget và tác động nghiệp vụ đã thỏa thuận. Nếu cần exact count cho audit, lưu attempt record ở ứng dụng với event ID.

### 10.2 Tiêu chí security

Test positive và negative cho từng role. Nếu Classic authorization dựa trên group trong plugin còn Artemis dựa trên role từ JAAS/LDAP, cần chứng minh mapping identity → role → permission. Kiểm tra cả:

- Queue và topic destination.
- Durable/non-durable subscription create/delete.
- Browse DLQ và replay tới queue nguồn.
- Auto-create address/queue.
- Management API/JMX/console.
- TLS trust, client certificate và credential rotation.

Migration security PASS khi user chỉ có đúng quyền cần thiết; mọi quyền ngoài scope bị từ chối và có log/audit phù hợp.

## 11. Quy trình triển khai và cutover

### 11.1 Trước cutover

1. Chốt policy manifest, destination inventory và owner cho từng queue/topic.
2. Tạo address/queue/DLQ/expiry destination trên Artemis; xác minh routing type.
3. Áp dụng security roles, credential và TLS; chạy positive/negative tests.
4. Áp dụng redelivery, expiry và capacity settings; restart/reload theo yêu cầu phiên bản.
5. Chạy toàn bộ parity matrix trên staging bằng payload và transaction mode giống production.
6. Benchmark message size, store/page growth, consumer ACK rate và DLQ growth.
7. Kiểm tra alert, dashboard, backup/restore và operator replay workflow.
8. Chuẩn bị rollback plan có người quyết định và tiêu chí dừng rõ ràng.

### 11.2 Cutover không tạo hai consumer group xử lý cùng nghiệp vụ

Một trình tự an toàn có thể là:

1. Giảm producer ingress hoặc bật maintenance window.
2. Dừng/đóng producer cũ theo cơ chế graceful; xác nhận transaction đã commit hoặc outcome unknown đã được ghi lại.
3. Drain queue cũ nếu chọn chuyển backlog bằng xử lý hết trên Classic; hoặc dùng quy trình bridge/migration dữ liệu đã kiểm thử nếu cần chuyển message chưa xử lý.
4. Dừng consumer cũ và xác nhận không còn active consumer xử lý cùng business partition.
5. Chuyển producer sang Artemis; gửi canary event có event ID riêng.
6. Xác nhận send/commit, routing, security, consumer ACK và business effect.
7. Mở dần ingress; theo dõi redelivery, DLQ, expiry, address size, paging và disk.
8. Chỉ đóng broker cũ sau khi backlog, in-flight và transaction state đã được đối soát.

Không chạy song song hai consumer fleet cùng xử lý một logical queue nếu không có idempotency/partitioning contract. Nếu cần dual-publish để shadow test, dùng destination và consumer cô lập; không để side effect nghiệp vụ bị chạy hai lần.

### 11.3 Rollback

Rollback phải trả lời trước:

- Message nào đã được Artemis nhận và commit?
- Message nào đã được consumer xử lý ở Artemis?
- Message nào còn pending/in-flight hoặc nằm trong DLQ/expiry address?
- Có producer send/commit outcome unknown nào chưa đối soát?
- Làm thế nào đưa event chưa xử lý về Classic mà không mất thứ tự hoặc tạo duplicate effect?

Nếu Artemis đã nhận message mới, không chỉ đổi URI producer về Classic rồi bỏ quên message ở Artemis. Cần drain, bridge ngược hoặc replay có kiểm soát với event ID ổn định. Không cho cả hai broker cùng nhận cùng producer traffic mà không có thiết kế deduplication và routing rõ ràng.

## 12. Lỗi migration thường gặp và cách xử lý

| Triệu chứng sau cutover | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Message không vào DLQ | Address pattern không match hoặc max attempts khác | Kiểm address-setting hiệu lực và test rollback |
| Message vào một DLQ chung, mất nguồn | Dùng shared DLQ thay individual mapping | Tách DLQ theo address hoặc lưu source metadata |
| Message expired bị mất | Chưa cấu hình expiry address hoặc policy khác | So TTL, expiry-address và routing |
| Producer bị block sớm hơn Classic | Artemis BLOCK/address max thấp hơn hoặc consumer lag | Đo memory/address threshold, ACK rate, không tăng bừa limit |
| Disk tăng nhanh sau đổi PAGE | Paging volume thiếu headroom hoặc ingress vượt egress | Giảm ingress, tăng consumer/storage, kiểm page growth |
| Consumer bị authorization denied | Role mapping hoặc permission address sai | Kiểm security-setting và identity provider |
| Producer gửi được nhưng consumer không nhận | Routing type/queue mapping không đúng | Kiểm ANYCAST/MULTICAST và JMS destination |
| Retry dày hơn nhiều | Application retry cộng với broker redelivery | Chọn một retry owner, tính lại timeline |
| DLQ replay tạo duplicate effect | Event ID thay đổi hoặc consumer thiếu inbox | Giữ idempotency key và audit replay |
| Queue cũ trống nhưng message chưa tới Artemis | Chưa chuyển backlog hoặc bridge sai | Đối soát source/target event IDs và count/bytes |

## 13. Checklist nghiệm thu cuối cùng

- [ ] Inventory Classic hoàn chỉnh: destination patterns, effective policy, client overrides, plugins và resource usage.
- [ ] Mapping wildcard Classic/Artemis đã test với destination có/không có child segment.
- [ ] Routing type và queue/subscription mapping đúng.
- [ ] Redelivery attempts, delay, multiplier và thời điểm DLQ đã được đo.
- [ ] DLQ giữ source destination, event ID và quyền operator đúng.
- [ ] Expiry TTL, scan timing và expiry destination đã được test.
- [ ] Authentication, authorization và TLS có positive/negative tests.
- [ ] Memory/address threshold, store/page capacity và filesystem reserve đã được benchmark.
- [ ] Producer backpressure không biến thành silent drop hoặc OOM.
- [ ] DLQ/expiry queues có retention, alert và replay workflow.
- [ ] Canary event có business effect đúng một lần.
- [ ] Backlog/in-flight/unknown outcomes được đối soát trước khi đóng broker cũ.
- [ ] Rollback đã được diễn tập với event ID ổn định và không tạo dual-consumer side effect.

**Kết luận:** Chuyển policy từ Classic sang Artemis là chuyển **hành vi** của redelivery, DLQ, expiry, authorization và resource control. Classic thường kết hợp destination policy, client redelivery và dead-letter strategy; Artemis thường quản lý nhiều hành vi qua address settings, DLQ/expiry address và security settings. Không có phép đổi byte limit hoặc retry count 1:1. Migration chỉ đạt khi parity tests chứng minh retry timeline, message routing, expiry, quyền truy cập và backpressure; cutover/rollback đối soát được mọi message pending, in-flight và outcome chưa rõ.
