# Phân tích ảnh hưởng của selector, priority, message group và topic fan-out

> **Chương:** Hiệu năng  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — tìm hiểu Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ bằng queue, topic, routing và JMS; thực hành producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi:** Phân tích bốn yếu tố ảnh hưởng trực tiếp tới routing và dispatch: **message selector**, **priority**, **message group** và **topic fan-out**. Ví dụ chính dùng Artemis 2.x, Java 17 và Jakarta JMS; phần Classic chỉ rõ khác biệt quan trọng về priority và Network/JMS behavior.

## 1. Vì sao throughput thay đổi dù số producer và consumer không đổi?

Một dịch vụ xử lý đơn hàng có một queue công việc và một topic sự kiện. Khi tải tăng, đội vận hành thử lần lượt:

- Thêm selector để mỗi consumer chỉ nhận tenant hoặc loại event của mình.
- Tăng priority cho lệnh khẩn.
- Gán `JMSXGroupID` theo order để giữ thứ tự.
- Thêm nhiều subscriber để mỗi phòng ban nhận một bản event.

Cả bốn thay đổi đều có thể làm giảm throughput hoặc tăng latency dù **số producer, kích thước message và số broker không đổi**. Lý do là broker phải làm thêm công việc khi chọn message, sắp lịch dispatch, duy trì group ownership hoặc tạo reference cho nhiều subscriber.

Một phép đo `messages/sec` tổng thể không đủ để kết luận. Cần biết message nào được chọn, message nào đang chờ, consumer nào sở hữu group, subscriber nào đang offline và thời gian từ publish tới business commit.

~~~mermaid
flowchart TD
    P["Producer: headers + properties + priority + group ID"] --> R["Broker routing"]
    R --> S["Selector/filter evaluation"]
    S --> Q["Queue references / topic subscriptions"]
    Q --> O["Priority ordering"]
    O --> G["Group ownership / consumer dispatch"]
    G --> C["Consumer processing + ACK"]
    C --> M["Metrics: rate, age, backlog, p95/p99"]
~~~

**Câu hỏi xuyên suốt bài:** mỗi tính năng có tạo ra lợi ích nghiệp vụ nào, chi phí broker nào, và chỉ số nào chứng minh cấu hình đó đáng giữ?

## 2. Message selector: giảm công việc không phù hợp, nhưng tăng chi phí lọc

### 2.1. Selector làm việc ở đâu?

JMS selector là biểu thức dạng SQL-92 subset dùng để lọc message dựa trên **header và message properties**. Selector được cung cấp khi consumer/subscription được tạo; broker/provider chỉ dispatch message thỏa điều kiện cho consumer đó.

Ví dụ:

~~~sql
tenant = 'acme'
AND eventType IN ('invoice.created', 'invoice.paid')
AND schemaVersion >= 2
~~~

Message cần có các properties tương ứng:

~~~java
TextMessage message = context.createTextMessage(payload);
message.setStringProperty("tenant", "acme");
message.setStringProperty("eventType", "invoice.created");
message.setIntProperty("schemaVersion", 2);
~~~

Selector **không phải bộ lọc tùy ý trên body JSON/XML**. Broker không tự parse body để tìm trường `customer.address.city`; nếu cần lọc theo trường đó, producer phải đưa giá trị thành message property phù hợp hoặc định tuyến tới destination riêng.

Các kiểu property phải nhất quán:

| Property | Kiểu nên gửi | Selector |
|---|---|---|
| `tenant` | String | `tenant = 'acme'` |
| `eventType` | String | `eventType IN ('created','paid')` |
| `schemaVersion` | Integer | `schemaVersion >= 2` |
| `riskScore` | Number | `riskScore BETWEEN 80 AND 100` |
| `urgent` | Boolean | `urgent = TRUE` |

Đừng gửi `schemaVersion` lúc là chuỗi `"2"`, lúc là integer `2` rồi mong phép so sánh số hoạt động giống nhau. Property names và kiểu dữ liệu cần được coi là một phần của **message contract**.

### 2.2. Selector được đánh giá khi nào?

Với queue, consumer đăng ký selector; broker xét message nào phù hợp để dispatch cho consumer đó. Message không khớp selector **không bị ACK hoặc xóa chỉ vì consumer đã nhìn thấy queue**. Nó vẫn có thể chờ consumer khác có selector phù hợp, hoặc nằm backlog nếu không có consumer nào nhận.

Với topic, selector gắn với subscription. Message chỉ được chuyển vào subscription khi thỏa filter của subscription đó. Với durable subscription, message phù hợp có thể được giữ khi subscriber offline; message không thỏa selector không phải là backlog của subscription ấy.

Không nên mô tả mọi implementation là một thuật toán scan cố định. Chi phí thực tế phụ thuộc provider, cấu trúc queue, index/cache, số selector, tỷ lệ match, message properties và concurrency. Điều cần đo là **CPU/routing cost, dispatch rate và queue age** trên đúng version broker.

### 2.3. Selector tốt và selector gây tốn kém

**Selector có phạm vi hẹp, ổn định:**

~~~sql
eventType = 'invoice'
AND tenant = 'acme'
AND schemaVersion >= 3
~~~

**Selector phức tạp, khó quản lý:**

~~~sql
(tenant = 'acme' OR tenant = 'globex' OR tenant = 'initech')
AND (eventType LIKE 'invoice.%' OR eventType LIKE 'payment.%')
AND (riskScore >= 80 OR urgent = TRUE OR sourceRegion <> 'legacy')
AND schemaVersion >= 2
~~~

Biểu thức thứ hai không mặc nhiên “chậm gấp N lần”, nhưng tăng số nhánh logic, khiến contract khó kiểm soát và khó benchmark. Nếu nhiều consumer dùng các selector gần giống nhau trên một queue lớn, hãy kiểm tra chi phí dispatch và tỷ lệ message không match.

Một số nguyên tắc:

- Đặt property cần lọc **ngay khi publish**; không dùng body parsing trong consumer để mô phỏng selector.
- Giữ tên và kiểu property thống nhất giữa các producer.
- Tránh selector chứa nhiều nhánh `OR` nếu có thể biểu diễn bằng routing/destination rõ hơn.
- Không tạo hàng trăm consumer với selector khác nhau chỉ để thay thế thiết kế partition/topic.
- Theo dõi **message age** và số message chưa được consumer nào nhận; queue count cao không nói được selector nào đang chặn tiến độ.
- Xác thực selector lúc khởi động và có test cho từng biểu thức; selector sai cú pháp có thể làm consumer không tạo được.

### 2.4. Selector có thể tạo backlog “không ai nhận”

Giả sử queue có 100.000 message:

- 80.000 message có `tenant='acme'`.
- 15.000 message có `tenant='globex'`.
- 5.000 message có `tenant='legacy'`.

Chỉ có consumer với selector `tenant='acme'`. Consumer có thể xử lý hết 80.000 message phù hợp nhưng 20.000 message còn lại vẫn tồn tại. Tăng concurrency của consumer acme **không giúp** 20.000 message kia.

Cần một trong các phương án:

1. Bổ sung consumer có selector tương ứng cho tenant khác.
2. Dùng consumer không selector cho queue catch-all có chủ đích.
3. Tách tenant thành destination riêng nếu đó là boundary vận hành/bảo mật phù hợp.
4. Có quy trình xử lý tenant không hợp lệ/legacy và cảnh báo oldest-message age.

Không dùng một consumer “bắt tất cả” nếu nó có thể lấy message của consumer chuyên biệt trước khi message được xử lý đúng.

### 2.5. Khi nào nên dùng selector, khi nào nên route thành queue riêng?

| Nhu cầu | Selector phù hợp? | Cân nhắc |
|---|---|---|
| Một vài consumer cần subset ổn định theo event type | Có thể | Selector đơn giản, test contract |
| Nhiều tenant với quota/SLA/retention riêng | Thường nên tách destination | Cách ly backlog, ACL và capacity rõ |
| Phân luồng dựa trên loại message nhỏ và ít | Có thể | Header/property đủ dùng |
| Routing phức tạp theo nhiều thuộc tính, thay đổi thường xuyên | Cần cân nhắc | Producer routing hoặc broker address/queue policy |
| Lọc theo nested JSON/body | Không trực tiếp bằng JMS selector | Parse trước khi publish hoặc routing service |
| Một nhóm message phải có thứ tự riêng | Selector không đủ | Kết hợp queue partition và message group |

Selector là **điều kiện nhận**, không tự tạo quota, fairness hay tenant isolation hoàn chỉnh.

## 3. Message priority: xử lý việc quan trọng trước, nhưng có thể làm đói việc thường

### 3.1. Priority JMS có miền giá trị nào?

JMS định nghĩa `JMSPriority` từ **0 đến 9**:

- 0: thấp nhất.
- 4: giá trị mặc định khi producer không chỉ định.
- 9: cao nhất.

Producer có thể đặt priority qua `JMSProducer`:

~~~java
JMSProducer producer = context.createProducer()
        .setDeliveryMode(DeliveryMode.PERSISTENT)
        .setPriority(9);

producer.send(queue, message);
~~~

Hoặc chọn giá trị theo từng message:

~~~java
producer.setPriority(2).send(queue, normalMessage);
producer.setPriority(8).send(queue, urgentMessage);
~~~

Giá trị priority là metadata của message, không phải quyền ưu tiên CPU của consumer và cũng không đảm bảo một message đang được xử lý sẽ bị ngắt để nhường chỗ cho message khẩn.

### 3.2. Priority ảnh hưởng thứ tự dispatch, không tạo preemption

Broker có thể ưu tiên dispatch message priority cao hơn khi chọn message kế tiếp. Tuy vậy, **không nên coi đây là total ordering tuyệt đối**:

- Message priority thấp đã được dispatch/in-flight trước đó không tự quay lại queue khi message priority cao đến.
- Prefetch/consumer window và batch dispatch có thể làm nhiều message đã được giao trước khi broker nhìn thấy message khẩn mới.
- Nhiều consumer xử lý song song có thể hoàn tất theo thứ tự khác thứ tự nhận.
- Provider và cấu hình broker có thể có khác biệt về cách áp dụng priority.

Nếu yêu cầu nghiệp vụ là “lệnh khẩn phải hoàn tất trong 2 giây”, chỉ set `JMSPriority=9` là không đủ. Cần SLO riêng, consumer capacity dành riêng, queue riêng hoặc scheduler có fairness, và đo thời gian từ publish đến business commit.

### 3.3. Starvation khi tải priority cao liên tục

Gọi:

- \(\lambda_H\): tốc độ đến của message priority cao.
- \(\lambda_L\): tốc độ đến của message priority thấp.
- \(\mu\): năng lực xử lý tổng của consumer pool.

Nếu `\(\lambda_H \geq \mu\)` trong thời gian dài, toàn bộ năng lực có thể bị message ưu tiên cao chiếm; message thấp bị trì hoãn vô hạn hoặc tăng backlog. Ngay cả khi `\(\lambda_H < \mu\)`, burst kéo dài có thể làm p99 của priority thấp tăng mạnh.

**Priority không tự cung cấp weighted fair scheduling.** Nếu cần bảo đảm mỗi lớp công việc có capacity tối thiểu, hãy tách queue:

~~~text
orders.urgent  -> consumer pool U, capacity dành riêng
orders.normal  -> consumer pool N
orders.bulk    -> consumer pool B
                    |
              shared downstream
~~~

Có thể áp dụng scheduler cấp ứng dụng hoặc quota giữa các queue, nhưng phải kiểm soát downstream. Đừng đặt tất cả message vào một queue rồi hy vọng priority giải quyết fairness.

### 3.4. Classic cần kiểm tra cấu hình priority

Trong ActiveMQ Classic, khả năng sắp xếp message theo priority có thể cần bật policy `prioritizedMessages` tùy phiên bản/cấu hình. Mảnh cấu hình minh họa trong `activemq.xml`:

~~~xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue=">" prioritizedMessages="true"/>
        </policyEntries>
    </policyMap>
</destinationPolicy>
~~~

Đây là fragment để hợp nhất với `destinationPolicy` hiện hữu. Không áp dụng cấu hình Classic này cho Artemis. Sau khi bật, benchmark lại thứ tự dispatch, throughput và fairness; ưu tiên message có thể thay đổi cách queue được tổ chức và tăng chi phí xử lý.

Với Artemis, priority là metadata JMS được broker hỗ trợ; vẫn phải kiểm tra effective behavior theo version, queue, consumer window và concurrency thực tế. Không giả định một cấu hình của Classic có thể copy sang Artemis.

## 4. Message group: giữ các message cùng khóa trên cùng consumer

### 4.1. Vấn đề cần giải quyết

Một queue `orders.work` có 8 consumer. Nếu tất cả message được phân phối tùy theo consumer sẵn sàng, hai message cập nhật cùng `order-42` có thể đến hai consumer khác nhau và hoàn tất không theo thứ tự.

Message grouping dùng property `JMSXGroupID` để chỉ định khóa nhóm:

~~~java
message.setStringProperty("JMSXGroupID", "order-42");
~~~

Broker hỗ trợ grouping sẽ gắn một group với một consumer owner tại một thời điểm, để message tiếp theo cùng group tiếp tục được chuyển cho owner đó trong vòng đời group. Những group khác vẫn có thể được phân phối cho consumer khác.

**Group key nên phản ánh aggregate cần thứ tự**, ví dụ order ID, account ID hoặc device ID; không dùng một giá trị cố định cho toàn bộ queue nếu muốn song song.

### 4.2. Đóng group bằng sequence marker

ActiveMQ Artemis và Classic hỗ trợ convention `JMSXGroupSeq`. Giá trị âm `-1` thường được dùng làm **marker kết thúc group**, cho broker biết ownership của group có thể được giải phóng sau message đó:

~~~java
TextMessage close = context.createTextMessage("close-order-stream");
close.setStringProperty("JMSXGroupID", "order-42");
close.setIntProperty("JMSXGroupSeq", -1);
producer.send(queue, close);
~~~

Chỉ gửi marker khi luồng nghiệp vụ thực sự đóng aggregate hoặc không còn message nào cần đi tiếp trong group. Nếu phát marker quá sớm, message đến sau có thể được gán owner mới; điều đó không thay thế sequence/version validation ở business layer.

### 4.3. Parallelism bị giới hạn bởi số group hoạt động

Một xấp xỉ hữu ích:

\[
\text{consumer concurrency hữu ích}
\leq \min(\text{số group đang hoạt động}, \text{số consumer sẵn sàng}).
\]

Ví dụ có 8 consumer nhưng chỉ 2 group nóng, nhiều nhất chỉ 2 consumer có thể xử lý hai group đó cùng lúc theo group ownership. Sáu consumer còn lại có thể rảnh.

Nếu 1 group `global` chứa 70% message, tăng consumer từ 8 lên 32 không giải quyết bottleneck của group đó. Đây là **hot group**, không phải thiếu consumer tổng thể.

### 4.4. Phân phối group bị lệch

| Phân bố | Hiện tượng | Hướng xử lý |
|---|---|---|
| Nhiều group nhỏ, tải đều | Consumer pool sử dụng tốt | Duy trì số consumer và đo |
| Ít group hơn consumer | Consumer rảnh | Chấp nhận giới hạn tuần tự hoặc chia aggregate nếu domain cho phép |
| Một group chiếm đa số tải | Một consumer bị nóng | Chọn partition key phù hợp hơn, chia aggregate hoặc tối ưu handler |
| Group tồn tại rất lâu | Ownership giữ lâu, khó cân bằng | Đóng group đúng lúc, theo dõi owner và lifecycle |
| Consumer owner chết | Broker cần phục hồi/redeliver và gán ownership lại | Kiểm tra recovery, duplicate và idempotency |

Không tạo group ID ngẫu nhiên cho từng message nếu mục tiêu là thứ tự theo order: khi mỗi message một group, grouping gần như mất tác dụng. Ngược lại, dùng cùng group ID cho tất cả order sẽ biến queue thành một luồng tuần tự.

### 4.5. Group giữ thứ tự nhận, không bảo đảm thứ tự side effect nếu app tự xử lý song song

Ví dụ consumer nhận tuần tự:

~~~text
order-42 version 10 -> consumer A
order-42 version 11 -> consumer A
~~~

Nhưng nếu consumer A đưa hai message vào hai thread/HTTP call độc lập, version 11 có thể commit trước version 10. Grouping chỉ kiểm soát phân phối ở broker; **business handler không được phá thứ tự sau khi nhận**.

Cách bảo vệ:

- Xử lý tuần tự trong một consumer lane cho mỗi group.
- Ghi `aggregateVersion`/sequence trong DB và từ chối hoặc defer version đến sai thứ tự.
- Idempotency theo event ID.
- Không ACK trước khi side effect có thể phục hồi.
- Khi có retry/DLQ/replay, xác định cách xử lý gap version.

Priority khác nhau trong cùng một group cũng có thể ảnh hưởng thứ tự dispatch tùy provider. Nếu strict per-aggregate order quan trọng, dùng priority nhất quán trong group hoặc tách queue/class mà không phá sequence.

## 5. Topic fan-out: một publish có thể tạo nhiều bản giao độc lập

### 5.1. Fan-out hoạt động như thế nào?

Topic cho phép nhiều subscriber nhận cùng một event. Trong Artemis, address routing kiểu **MULTICAST** thường có queue/subscription riêng cho từng subscriber (đặc biệt durable subscription). Broker route một message tới các subscription thỏa điều kiện.

~~~text
                 Topic / address: orders.events
                              |
                         publish M1
                              |
                +-------------+-------------+
                |             |             |
             Billing       Analytics       Audit
             queue/sub     queue/sub       queue/sub
                |             |             |
             Consumer B    Consumer A    Consumer C
~~~

Một message publish có thể sinh nhiều **queue references/deliveries**. Không nhất thiết broker sao chép nguyên payload thành một file cho mỗi subscriber, nhưng routing metadata, queue references, persistence work, dispatch, network bytes và backlog có thể tăng theo số subscription nhận message.

Nếu có \(N\) subscriber đều match, số lượt giao logic xấp xỉ \(N\) cho một event; đây là cách tính workload, không phải khẳng định chi tiết storage nội bộ của mọi provider.

### 5.2. Durable và non-durable subscription khác nhau ở đâu?

- **Non-durable subscription:** subscriber thường chỉ nhận message khi đang active. Nếu không có subscription phù hợp tại thời điểm publish, broker không giữ một backlog lâu dài cho subscriber đã biến mất.
- **Durable subscription:** broker duy trì subscription identity và giữ message phù hợp khi subscriber offline, theo policy/persistence của broker. Khi subscriber quay lại, backlog có thể được dispatch.
- **Shared durable subscription:** nhiều consumer cùng chia sẻ một durable subscription theo semantics JMS/provider, hữu ích cho scale-out; vẫn cần hiểu ordering và concurrency.

Trong Artemis, durable subscription được hiện thực qua queue gắn với topic/address. Queue đó có backlog riêng, nên một subscriber offline lâu ngày có thể giữ lượng lớn message dù các subscriber khác xử lý bình thường.

### 5.3. Fan-out cost không chỉ là số subscriber

Chi phí tăng theo:

- Số subscription nhận message.
- Tỷ lệ message match selector của từng subscription.
- Persistent/non-persistent delivery và storage durability.
- Consumer rate khác nhau, đặc biệt subscriber chậm/offline.
- Kích thước payload, network egress và số vùng nhận.
- Retention/backlog của durable subscription.
- Selector complexity và routing metadata.
- ACK/transaction overhead và redelivery.

**Một subscriber chậm không nên làm đội khác mất message**, nhưng có thể làm tăng storage/disk usage và chi phí quản trị của broker. Cần theo dõi backlog theo từng subscription, không chỉ tổng topic rate.

### 5.4. Selector trên topic subscription

Một subscription có thể lọc event:

~~~java
Topic topic = context.createTopic("orders.events");

JMSConsumer billing = context.createConsumer(
        topic, "eventType IN ('invoice.created','invoice.paid')");

JMSConsumer fraud = context.createConsumer(
        topic, "riskScore >= 80");
~~~

Trong ví dụ, mỗi subscriber chỉ quan tâm một tập message. Nếu event không match selector của billing, nó không tạo backlog trong subscription billing; nhưng có thể vẫn match fraud/audit subscription khác.

Selector phải được định nghĩa ổn định trong contract. Nếu thay selector của durable subscription, cần hiểu việc tạo lại/đổi identity subscription và backlog cũ theo provider; không đổi tên subscription ngẫu nhiên mỗi lần deploy vì có thể tạo queue durable mới và để queue cũ tồn tại.

### 5.5. Fan-out lớn: khi nào tách topic hoặc tạo projection?

| Nhu cầu | Thiết kế nên cân nhắc |
|---|---|
| 3–5 nhóm nhận event giống nhau, tải vừa | Một topic, subscription rõ ràng |
| Nhiều subscriber, mỗi subscriber filter khác nhau | Selector subscription hoặc topic/address phân loại |
| Subscriber có SLA/retention riêng | Queue/address riêng để cô lập backlog |
| Một consumer cần replay dài hạn, audit | Durable subscription hoặc kho event chuyên dụng theo yêu cầu retention |
| Subscriber bên ngoài có bandwidth thấp | Relay/egress riêng, batch/rate control |
| Subscriber không đáng tin hoặc quyền riêng | Tách destination/security boundary |

Đừng nhân topic chỉ để tránh một selector đơn giản; nhưng cũng đừng gom hàng chục workload có retention, SLA và security khác nhau vào một address nếu không có kiểm soát.

## 6. Bốn cơ chế tương tác và các trade-off

| Cơ chế | Tăng khả năng | Chi phí/rủi ro | Khi nào nên dùng |
|---|---|---|---|
| Selector | Consumer nhận đúng subset | Evaluation/routing overhead, message không match bị backlog | Subset ổn định theo property |
| Priority | Dispatch công việc quan trọng sớm hơn | Starvation, reorder, in-flight thấp priority | Một số lớp urgency có SLA |
| Message group | Ordering/affinity theo aggregate | Hot group, giảm parallelism, ownership lifecycle | Cần xử lý tuần tự theo key |
| Topic fan-out | Nhiều subscriber độc lập nhận event | Nhiều references, storage/network/dispatch cost | Event cần nhiều bounded consumers |

### 6.1. Selector + group

Nếu selector khác nhau giữa consumer cùng queue, phải xác minh mỗi group có consumer phù hợp cho mọi message của nó. Một group có thể bị giữ backlog vì message tiếp theo không khớp selector của consumer đang nhận group hoặc topology selector không nhất quán.

Khi cần strict order, ưu tiên **một selector policy thống nhất** cho các consumer cùng queue/group, hoặc route các nhóm nghiệp vụ sang queue riêng trước khi áp dụng grouping.

### 6.2. Priority + group

Priority chọn message nào được dispatch sớm hơn; group ràng buộc consumer ownership. Hai cơ chế có mục tiêu khác nhau. Nếu một group có message priority 2 và 9, thứ tự message được dispatch có thể không còn là thứ tự publish theo cách ứng dụng mong đợi. Không trộn priority biến động với strict per-order sequence nếu chưa test.

### 6.3. Selector + topic fan-out

Selector giúp mỗi subscriber chỉ nhận event liên quan, giảm số delivery ở các subscription không match. Tuy vậy, broker vẫn cần xử lý routing/filter và duy trì subscription state. Nếu hàng trăm subscriber có selector phức tạp, đo chi phí trên broker thay vì chỉ nhìn số message tới consumer.

### 6.4. Group + topic fan-out

Topic fan-out nhân bản **luồng tham chiếu** tới các subscription; grouping áp dụng trong phạm vi queue/subscription xử lý. Group ID giống nhau trên hai subscription **không tạo một global owner duy nhất** giữa các subscriber độc lập. Mỗi subscription có thể xử lý aggregate riêng; nếu cần đồng bộ side effect giữa các subscriber, dùng version/coordination ở business layer.

## 7. Cấu hình Artemis: queue filter và multicast subscription

### 7.1. Queue ANYCAST cho workload cần selector

Mảnh cấu hình trong phần `<addresses>` của `broker.xml` Artemis:

~~~xml
<address name="perf.work">
    <anycast>
        <queue name="perf.work" durable="true"/>
    </anycast>
</address>
~~~

JMS queue `perf.work` được producer/consumer sử dụng. Consumer selector có thể lọc các properties của message.

### 7.2. Multicast address với filter tĩnh cho từng queue

Khi muốn route theo một số loại event ổn định, broker có thể có queue filter:

~~~xml
<address name="perf.events">
    <multicast>
        <queue name="perf.events.billing" durable="true">
            <filter string="eventType IN ('invoice.created','invoice.paid')"/>
        </queue>
        <queue name="perf.events.risk" durable="true">
            <filter string="riskScore >= 80"/>
        </queue>
        <queue name="perf.events.audit" durable="true"/>
    </multicast>
</address>
~~~

Đây là ví dụ cấu hình queue filter Artemis; kiểm tra cú pháp/schema và queue provisioning của phiên bản broker đang dùng. Filter queue và JMS consumer selector đều là biểu thức filter ở broker nhưng **được gắn vào hai điểm khác nhau**: queue routing và consumer subscription. Không cấu hình cả hai chồng lấn mà không có lý do, vì message có thể bị lọc ở tầng routing trước khi tới consumer.

Nếu các queue đã được tạo bằng management API/auto-create, không tạo trùng trong XML. Hợp nhất với address và security settings hiện có.

### 7.3. Classic priority policy

Với ActiveMQ Classic, nếu cần priority ordering, kiểm tra policy hỗ trợ và cấu hình:

~~~xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue=">" prioritizedMessages="true"/>
        </policyEntries>
    </policyMap>
</destinationPolicy>
~~~

Đây là cấu hình Classic trong `activemq.xml`, không phải `broker.xml` Artemis. Khi bật, benchmark lại cả throughput và starvation; không mặc định bật cho mọi queue vì một queue không cần priority có thể không được lợi.

## 8. Lab Java/Jakarta JMS: đo selector, priority, group và fan-out

Lab dùng **Artemis 2.40.0**, Java 17, Jakarta JMS 3.1. Broker cần queue `perf.work` và topic/address `perf.events` được provision; user lab có quyền send/consume. Các ví dụ chạy với broker lab, không dùng queue production.

### 8.1. Maven

Cấu trúc:

~~~text
jms-dispatch-performance/
├── pom.xml
└── src/main/java/lab/DispatchFeaturesLab.java
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab</groupId>
  <artifactId>jms-dispatch-performance</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>artemis-jakarta-client</artifactId>
      <version>2.40.0</version>
    </dependency>
    <dependency>
      <groupId>jakarta.jms</groupId>
      <artifactId>jakarta.jms-api</artifactId>
      <version>3.1.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 8.2. Java producer và các consumer mode

Tạo `src/main/java/lab/DispatchFeaturesLab.java`:

~~~java
package lab;

import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSProducer;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class DispatchFeaturesLab {
    private static final String QUEUE = "perf.work";
    private static final String TOPIC = "perf.events";

    private DispatchFeaturesLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            throw new IllegalArgumentException(
                    "send | selector | group | topic-publish | topic-subscribe");
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = required("BROKER_USER");
        String password = required("BROKER_PASSWORD");
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        switch (args[0]) {
            case "send" -> sendQueue(factory, user, password);
            case "selector" -> consumeSelector(factory, user, password);
            case "group" -> consumeGroup(factory, user, password);
            case "topic-publish" -> publishTopic(factory, user, password);
            case "topic-subscribe" -> subscribeTopic(factory, user, password);
            default -> throw new IllegalArgumentException(
                    "Unknown mode: " + args[0]);
        }
    }

    private static void sendQueue(
            ConnectionFactory factory, String user, String password) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
            Queue queue = context.createQueue(QUEUE);
            JMSProducer producer = context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT);

            for (int i = 1; i <= 100; i++) {
                String tenant = (i % 4 == 0) ? "globex" : "acme";
                String eventType = (i % 3 == 0)
                        ? "invoice" : "shipment";
                int priority = (i % 10 == 0) ? 9 : 4;
                String orderId = "order-" + (i % 12);

                TextMessage message = context.createTextMessage(
                        "payload-" + i);
                message.setStringProperty("tenant", tenant);
                message.setStringProperty("eventType", eventType);
                message.setIntProperty("schemaVersion", 2);
                message.setStringProperty("JMSXGroupID", orderId);
                message.setIntProperty("sequence", i);

                producer.setPriority(priority).send(queue, message);
            }
            System.out.println("QUEUE_SEND_COMPLETED count=100");
        }
    }

    private static void consumeSelector(
            ConnectionFactory factory, String user, String password)
            throws Exception {
        String selector =
                "tenant = 'acme' AND eventType = 'invoice' "
                + "AND schemaVersion >= 2";

        try (JMSContext context = factory.createContext(
                    user, password, JMSContext.AUTO_ACKNOWLEDGE);
             JMSConsumer consumer = context.createConsumer(
                    context.createQueue(QUEUE), selector)) {

            System.out.println("SELECTOR_ACTIVE " + selector);
            for (int i = 0; i < 20; i++) {
                Message message = consumer.receive(1000);
                if (message == null) {
                    break;
                }
                System.out.println("SELECTED sequence="
                        + message.getIntProperty("sequence")
                        + " tenant=" + message.getStringProperty("tenant")
                        + " type=" + message.getStringProperty("eventType")
                        + " priority=" + message.getJMSPriority());
            }
        }
    }

    private static void consumeGroup(
            ConnectionFactory factory, String user, String password)
            throws Exception {
        try (JMSContext context = factory.createContext(
                    user, password, JMSContext.AUTO_ACKNOWLEDGE);
             JMSConsumer consumer = context.createConsumer(
                    context.createQueue(QUEUE))) {

            System.out.println("GROUP_CONSUMER_READY");
            for (int i = 0; i < 30; i++) {
                Message message = consumer.receive(2000);
                if (message == null) {
                    break;
                }
                System.out.println("GROUP_DELIVERY group="
                        + message.getStringProperty("JMSXGroupID")
                        + " sequence="
                        + message.getIntProperty("sequence"));
            }
        }
    }

    private static void publishTopic(
            ConnectionFactory factory, String user, String password) {
        try (JMSContext context = factory.createContext(
                user, password, JMSContext.AUTO_ACKNOWLEDGE)) {
            Topic topic = context.createTopic(TOPIC);
            JMSProducer producer = context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT);

            for (int i = 1; i <= 30; i++) {
                TextMessage message = context.createTextMessage(
                        "event-" + i);
                message.setStringProperty("eventId",
                        "evt-" + UUID.randomUUID());
                message.setStringProperty("eventType",
                        (i % 2 == 0) ? "invoice" : "shipment");
                message.setIntProperty("riskScore", (i % 10) * 10);
                producer.send(topic, message);
            }
            System.out.println("TOPIC_PUBLISH_COMPLETED count=30");
        }
    }

    private static void subscribeTopic(
            ConnectionFactory factory, String user, String password)
            throws Exception {
        try (JMSContext context = factory.createContext(
                    user, password, JMSContext.AUTO_ACKNOWLEDGE);
             JMSConsumer billing = context.createConsumer(
                    context.createTopic(TOPIC),
                    "eventType = 'invoice'");
             JMSConsumer risk = context.createConsumer(
                    context.createTopic(TOPIC),
                    "riskScore >= 80")) {

            System.out.println("TOPIC_SUBSCRIPTIONS_READY");
            for (int i = 0; i < 10; i++) {
                Message invoice = billing.receive(1000);
                if (invoice != null) {
                    System.out.println("BILLING eventId="
                            + invoice.getStringProperty("eventId"));
                }

                Message highRisk = risk.receive(100);
                if (highRisk != null) {
                    System.out.println("RISK eventId="
                            + highRisk.getStringProperty("eventId"));
                }
            }
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing " + key);
        }
        return value;
    }
}
~~~

**Cách đọc lab:**

- Mode `send` phát 100 message có tenant/eventType/schemaVersion/priority/group ID. Đây là dữ liệu thử, không đại diện benchmark production.
- Mode `selector` chỉ nhận message thỏa selector. Message khác vẫn có thể còn trong queue.
- Mode `group` nhận từ queue không selector; để kiểm tra group ownership, chạy **nhiều process consumer đồng thời** và ghi lại process ID/consumer ID cùng group ID. Một process một consumer không chứng minh phân phối giữa nhiều consumer.
- Mode `topic-subscribe` tạo hai non-durable subscriptions có selector; phải khởi động subscriber **trước** publisher nếu muốn nhận toàn bộ 30 event.
- Topic sample dùng `AUTO_ACKNOWLEDGE` và chỉ minh họa fan-out; muốn kiểm tra durable backlog cần tạo durable subscription với identity ổn định, publish khi subscriber offline, rồi reconnect bằng đúng identity.
- Producer tạo UUID cho mỗi event mới; nếu retry cùng một event do timeout, caller phải giữ **eventId ban đầu**, không gọi lại UUID generator.

### 8.3. Chạy các mode

PowerShell:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "lab"
$env:BROKER_PASSWORD = "LAB_ONLY_PASSWORD"
mvn -q -DskipTests package

# Terminal 1: gửi vào queue.
mvn -q exec:java "-Dexec.mainClass=lab.DispatchFeaturesLab" "-Dexec.args=send"

# Terminal 2: chỉ nhận tenant acme + invoice.
mvn -q exec:java "-Dexec.mainClass=lab.DispatchFeaturesLab" "-Dexec.args=selector"

# Chạy hai hoặc nhiều process group consumer để quan sát ownership.
mvn -q exec:java "-Dexec.mainClass=lab.DispatchFeaturesLab" "-Dexec.args=group"

# Terminal subscriber phải chạy trước.
mvn -q exec:java "-Dexec.mainClass=lab.DispatchFeaturesLab" "-Dexec.args=topic-subscribe"

# Terminal publisher.
mvn -q exec:java "-Dexec.mainClass=lab.DispatchFeaturesLab" "-Dexec.args=topic-publish"
~~~

Queue và topic phải được broker provision đúng; user lab có quyền cần thiết. Nếu chạy selector sau group consumer, một phần queue có thể đã bị consume. Hãy reset **queue lab** theo procedure quản trị trước mỗi lần so sánh để dataset giống nhau.

## 9. Benchmark: đo từng tính năng riêng rồi mới đo tổ hợp

### 9.1. Baseline phải cố định

Trước khi bật selector/priority/group/fan-out, ghi baseline:

- Broker và client version, JVM, CPU/memory/disk/network.
- Queue/address, routing type, persistence mode, page policy.
- Message size distribution (p50/p95), headers/properties và serialization.
- Producer rate, transaction/batch size, number of producers.
- Consumer count, concurrency, prefetch/window/ack mode.
- Tỷ lệ message xử lý thành công, redelivery, DLQ.
- Warm-up, thời gian đo, dataset, số lần lặp và điều kiện tải.

Không so sánh một lượt non-persistent 1 KiB với một lượt persistent 64 KiB rồi quy toàn bộ chênh lệch cho selector.

### 9.2. Thứ tự benchmark đề xuất

| Lượt | Biến thay đổi duy nhất | Câu hỏi |
|---|---|---|
| B0 | Không selector, priority mặc định, không group, 1 subscriber | Baseline throughput/latency |
| B1 | Selector đơn giản, match 90% | Chi phí lọc ở tỷ lệ match cao |
| B2 | Selector đơn giản, match 10% | Backlog và dispatch khi phần lớn không phù hợp |
| B3 | Nhiều selector/consumer khác nhau | CPU và routing overhead có tăng? |
| B4 | Priority 0/4/9 theo tỷ lệ cố định | Dispatch order và starvation |
| B5 | Group count = consumer count | Parallelism/affinity |
| B6 | Group count ít hơn consumer | Consumer idle/hot group |
| B7 | Topic subscriber tăng 1→5→20 | Routing, storage refs và network egress |
| B8 | Durable subscriber offline trong một khoảng | Backlog retention và disk |
| B9 | Kết hợp selector + group + priority + fan-out | Tương tác, không suy từ kết quả riêng lẻ |

Chỉ thay một biến trong B1–B8. B9 mới là phép thử cấu hình gần production.

### 9.3. Chỉ số bắt buộc

| Metric | Diễn giải | Cần tách theo |
|---|---|---|
| Publish rate | Producer gửi message/giây | Producer, destination, priority |
| Dispatch/delivery rate | Broker giao message/giây | Queue/subscription, selector |
| Business completion rate | Consumer commit nghiệp vụ/giây | Consumer group, event type |
| End-to-end latency | Event created → business commit | p50/p95/p99, tenant, priority |
| Queue depth | Message chưa hoàn tất tại queue | Queue, subscription |
| Oldest message age | Tuổi message lâu nhất | Selector/durable subscription |
| Delivering/in-flight | Message đang giao/chưa ACK | Consumer và group |
| Consumer utilization | Thời gian consumer bận/rảnh | Consumer ID, group ownership |
| Broker CPU/GC | Chi phí xử lý/filter/routing | Node và process |
| Storage I/O/bytes | Journal/page/large-message | Queue/subscription persistent |
| Network bytes | Ingress/egress | Subscriber, vùng, protocol |
| DLQ/redelivery | Lỗi xử lý hoặc delivery lặp | Event type/group |

Không dùng tổng queue depth để kết luận selector nhanh/chậm. Message không match vẫn nằm lại và có thể khiến oldest age tăng trong khi consumer match đang báo throughput cao.

### 9.4. Cách tính thông lượng fan-out

Giả sử publisher phát \(R\) message/giây, trung bình có \(N_m\) subscription match mỗi message. Delivery workload logic xấp xỉ:

\[
R_{\text{deliveries}} \approx R \times N_m.
\]

Ví dụ 2.000 event/s, trung bình 6 subscription match:

\[
R_{\text{deliveries}} \approx 12.000 \text{ delivery/s}.
\]

Đây là ước lượng số lượt delivery logic, **không** phải dự báo chính xác CPU hoặc disk. Message persistence, payload size, ACK batch, durable/offline subscriber và protocol overhead có thể làm cost khác nhiều.

### 9.5. Tính match ratio và backlog

Gọi \(r\) là tỷ lệ message match selector, \(R\) là ingress rate và \(\mu\) là năng lực consumer đối với message phù hợp. Consumer chỉ có thể xử lý tối đa phần phù hợp:

\[
R_{\text{eligible}} = R \times r.
\]

Nếu \(\mu < R_{\text{eligible}}\), backlog phù hợp tăng. Nếu \(\mu\) lớn nhưng selector không bao phủ một tập message, **unmatched backlog** vẫn tồn tại. Phải đo cả match ratio và số message không có consumer phù hợp.

## 10. Tối ưu từng cơ chế theo mục tiêu

### 10.1. Tối ưu selector

- Chuẩn hóa schema property và type ở producer.
- Giữ selector nhỏ, rõ, có test; hạn chế selector động được sinh từ cấu hình tùy ý.
- Với phân vùng lớn và ổn định, ưu tiên destination riêng để tách backlog, ACL và capacity.
- Không tạo consumer selector chồng lấn mà không biết message nào thuộc owner nào.
- Theo dõi oldest age của message không match; tạo consumer catch-all/quarantine có chủ đích.
- Tránh filter theo property không được producer luôn set; selector với giá trị NULL có thể không match như kỳ vọng.

### 10.2. Tối ưu priority

- Chỉ dùng một vài lớp priority có ý nghĩa nghiệp vụ (ví dụ urgent/normal/bulk).
- Đặt capacity riêng hoặc weighted scheduler nếu cần fairness.
- Đặt SLA cho priority thấp; cảnh báo starvation khi oldest age vượt ngưỡng.
- Tránh để producer tùy ý đặt mọi message thành 9; kiểm soát quyền/contract ở application.
- Không dùng priority để thay partition hoặc queue riêng khi backlog phải được cô lập.
- Đo reorder và số message in-flight sau khi đổi policy.

### 10.3. Tối ưu message group

- Chọn group key đủ phân tán nhưng vẫn trùng với aggregate cần thứ tự.
- Đếm số group hoạt động và phân phối message/group (p50/p95/max).
- Theo dõi consumer owner và group có tuổi cao; phát hiện hot key.
- Giữ xử lý trong group tuần tự; không đẩy callback vào executor không kiểm soát.
- Đóng group khi lifecycle thật sự kết thúc nếu semantics ứng dụng cho phép.
- Nếu một aggregate quá nóng, xem lại mô hình domain; chia group chỉ khi chấp nhận thay đổi ordering invariant.

### 10.4. Tối ưu topic fan-out

- Chỉ tạo subscription cho consumer có nhu cầu thực.
- Dùng durable khi cần nhận offline; quản lý retention/expiry và dọn subscription đã bỏ.
- Theo dõi backlog từng durable subscription; một subscriber cũ có thể giữ storage lâu dài.
- Selector subscription đơn giản, schema rõ.
- Dùng queue/address riêng khi cần quota, retention, SLA hoặc ACL khác.
- Đo network egress theo số subscriber và region; payload lớn có thể làm fan-out đắt hơn routing metadata.

## 11. Tương tác gây hiểu lầm trong production

### 11.1. Selector + priority

Consumer selector chỉ nhận subset; priority sắp thứ tự trong tập message có thể dispatch. Nếu message priority 9 không match selector của consumer khẩn, nó vẫn không được consumer đó nhận. Priority không vượt qua selector hoặc ACL.

### 11.2. Priority + group

Một group có message priority khác nhau. Broker có thể ưu tiên message cao hơn trong queue, trong khi group giữ owner. Nếu nghiệp vụ cần version tuần tự, ưu tiên phải được thiết kế sao cho không phá sequence; không suy từ group ownership rằng thứ tự publish luôn được giữ khi priority khác nhau.

### 11.3. Group + fan-out

Một topic multicast có nhiều durable subscriptions. Mỗi subscription có queue/dispatch riêng; group ownership được thực thi **trong từng queue**, không phải giữa tất cả subscriber. Cùng một order có thể được xử lý song song bởi billing và audit, nhưng từng subscription cần idempotency và sequence guard riêng.

### 11.4. Durable fan-out + selector

Một durable subscription giữ backlog khi subscriber offline. Nếu selector của subscription chỉ match 10% event, nó chỉ giữ phần phù hợp; các event không match có thể được giao cho subscription khác. Thay selector/identity có thể để lại subscription queue cũ. Trước khi xóa subscription, phải xác định backlog nào bị loại.

### 11.5. Một queue, nhiều consumer và selector lệch nhau

Consumer A selector tenant=acme, consumer B selector tenant=globex. Đây có thể là cách chia workload nhưng phải xác nhận mọi tenant đều có consumer phù hợp và group không bị phân chia sai. Nếu một consumer ngừng, tenant tương ứng có thể backlog dù consumer khác đang rảnh. Destination riêng thường dễ capacity planning hơn khi tenant là boundary lớn.

## 12. Runbook khi throughput giảm sau khi bật một tính năng

### Bước 1 — xác nhận dataset và thay đổi

Ghi rõ release, config revision, producer rate, message size, persistent mode, selector, priority mix, group count và số subscription. So với baseline cùng điều kiện.

### Bước 2 — phân biệt backlog loại nào

- Queue backlog toàn bộ tăng: consumer capacity hoặc broker bottleneck.
- Chỉ message không match tăng: selector coverage thiếu.
- Priority thấp tăng trong khi priority cao ổn: starvation.
- Một group/consumer có tuổi cao: hot group hoặc owner bị nghẽn.
- Một durable subscription tăng: subscriber chậm/offline hoặc selector không còn phù hợp.
- Broker network egress tăng: fan-out/subscriber count hoặc payload lớn.

### Bước 3 — xem delivering và consumer utilization

Nhiều message in-flight nhưng business commit thấp có thể do handler/DB chậm hoặc prefetch/window lớn. Consumer rảnh trong khi backlog tồn tại có thể do selector mismatch, group count thấp hoặc subscriber không hoạt động.

### Bước 4 — kiểm tra broker resource

CPU/GC, disk I/O, journal/page, network bytes, address size, connection churn và flow control. Không chỉ tăng consumer nếu bottleneck là broker routing hoặc network egress.

### Bước 5 — thay một biến và đo lại

Giảm độ phức tạp selector, tách queue, cân bằng group key, giới hạn priority classes hoặc dọn durable subscription đã hết vòng đời theo policy. Chỉ thay một yếu tố để biết nguyên nhân.

### Bước 6 — xác nhận correctness

Sau tối ưu, kiểm tra message không mất, không bị xử lý sai tenant, per-group order còn đúng, durable subscriber vẫn nhận đủ và priority SLA/fairness đạt yêu cầu. Throughput cao hơn nhưng sai business ordering không phải tối ưu thành công.

## 13. Những anti-pattern nên tránh

- **Selector trên body:** JMS selector không phải JSONPath; chuyển property cần lọc thành header/property hoặc routing trước.
- **Selector không có consumer bao phủ:** message nằm backlog vô hạn; cần coverage test và alert oldest age.
- **Priority 9 cho mọi producer:** phá ý nghĩa ưu tiên, có thể làm đói message thường.
- **Một group ID cho toàn queue:** tuần tự hóa toàn workload, làm giảm parallelism.
- **Group ID ngẫu nhiên mỗi message:** không giữ được ordering theo aggregate.
- **Xử lý async ngoài listener mà không version guard:** broker dispatch đúng nhưng business commit đảo thứ tự.
- **Topic với quá nhiều durable subscriber không owner:** queue/subscription tích backlog, chiếm storage.
- **Tạo durable subscription mới mỗi lần deploy:** để lại subscription cũ và backlog không được quản lý.
- **Dùng selector để mô phỏng quota tenant:** không có capacity isolation; tách queue khi cần SLA riêng.
- **Benchmark chỉ nhìn messages/sec:** bỏ qua p99, unmatched backlog, DLQ và network/storage cost.

## 14. Ma trận kiểm thử hiệu năng và tính đúng

| ID | Kịch bản | PASS khi |
|---|---|---|
| SEL-01 | Selector match 100% | Throughput/latency baseline được ghi |
| SEL-02 | Selector match 10% | Unmatched message được giữ/định tuyến đúng; oldest age có metric |
| SEL-03 | Không có consumer match | Alert phát hiện backlog không có owner |
| PRI-01 | Priority 0/4/9 | Dispatch behavior đúng provider; không giả định preemption |
| PRI-02 | High-priority sustained load | Đo được starvation/latency của priority thấp |
| PRI-03 | Chia queue urgent/normal | Fairness và SLA của từng lớp đạt |
| GRP-01 | N group phân đều trên M consumer | Group không bị xử lý đồng thời sai invariant |
| GRP-02 | Một hot group | Nhận diện giới hạn parallelism và oldest age |
| GRP-03 | Consumer owner restart | Redelivery/reassignment đúng; side effect idempotent |
| GRP-04 | Gửi `JMSXGroupSeq=-1` | Group ownership được giải phóng theo provider behavior |
| FAN-01 | 1, 5, 20 subscriber | Đo delivery rate, CPU, egress và storage |
| FAN-02 | Durable subscriber offline | Backlog được giữ đúng và phục hồi khi subscriber online |
| FAN-03 | Selector khác nhau theo subscription | Mỗi subscriber chỉ nhận message phù hợp |
| MIX-01 | Selector + priority + group | Không phá routing và ordering contract |
| MIX-02 | Fan-out + slow subscriber | Subscriber khác tiếp tục; backlog chậm được cô lập/alert |

Không đánh dấu PASS chỉ vì test không ném exception. Cần kiểm tra **message IDs, event IDs, counts, order/version, business effects, queue/subscription depth và latency**.

## 15. Câu hỏi tự kiểm tra

**1. Selector `tenant='acme'` không nhận message tenant=globex. Message có bị xóa không?**  
Không. Với queue, message không match consumer selector vẫn có thể nằm trong queue để consumer phù hợp khác nhận. Nếu không có consumer phù hợp, backlog sẽ tồn tại.

**2. Có thể dùng JMS selector để lọc trường nested trong JSON body không?**  
Không trực tiếp. Selector dựa trên JMS headers/properties; producer cần đưa trường cần lọc thành property hoặc định tuyến trước.

**3. Priority 9 có thể ngắt consumer đang xử lý priority 2 không?**  
Không. Priority ảnh hưởng lựa chọn dispatch tiếp theo theo provider; không phải preemption của business handler.

**4. Vì sao 16 consumer nhưng throughput chỉ bằng 2 consumer?**  
Có thể chỉ có 2 active group, một hot group, downstream bottleneck hoặc selector làm phần lớn consumer không có message phù hợp. Kiểm tra group distribution và consumer utilization.

**5. Topic có 10 durable subscribers, mỗi event match tất cả. Chi phí logic gần bao nhiêu delivery?**  
Khoảng 10 delivery/subscription references cho một event; storage và CPU cụ thể tùy provider, persistence và consumer backlog.

**6. Hai subscriber dùng cùng `JMSXGroupID` có được cùng một owner không?**  
Không. Group ownership có scope queue/subscription; mỗi subscriber độc lập có thể xử lý group đó riêng.

**7. Vì sao bật priority có thể làm message thường tăng tuổi dù consumer vẫn khỏe?**  
High-priority arrivals có thể chiếm phần lớn dispatch capacity; JMS priority không bảo đảm weighted fairness.

**8. Durable subscriber offline có ảnh hưởng broker disk không?**  
Có thể. Message match subscription được giữ làm backlog theo persistence/retention policy, dù các subscriber khác đã nhận xong.

**9. Khi nào nên tách queue thay vì tăng độ phức tạp selector?**  
Khi tenant/class có SLA, quota, security, retention hoặc scaling độc lập; queue riêng làm boundary capacity rõ hơn.

**10. Vì sao cần đo p99 và oldest age cùng throughput?**  
Throughput trung bình có thể tăng trong khi message priority thấp, unmatched tenant hoặc durable subscriber bị đói lâu; p99/age phát hiện phần bị bỏ lại.

## 16. Checklist thiết kế và vận hành

- [ ] Selector chỉ dùng JMS headers/properties, property type/name được chuẩn hóa.
- [ ] Có consumer coverage cho mọi selector; unmatched backlog có alert.
- [ ] Selector expression đơn giản, được test với positive/negative cases.
- [ ] Priority nằm trong 0–9, có quy tắc lớp urgency và fairness.
- [ ] Đã kiểm tra provider có bật/áp dụng priority đúng kỳ vọng, nhất là Classic policy.
- [ ] Có giám sát starvation và oldest age của priority thấp.
- [ ] Group ID là aggregate key có phân bố tốt; không dùng một group toàn queue.
- [ ] Đã đo active group count, hot key và consumer owner distribution.
- [ ] Business handler không xử lý song song phá thứ tự sau dispatch.
- [ ] Group close marker chỉ phát khi lifecycle thật sự kết thúc.
- [ ] Topic subscriber được quản lý identity, selector và lifecycle.
- [ ] Durable subscription có owner, retention và quy trình retire.
- [ ] Fan-out được sizing theo số subscription match, payload, persistence và network egress.
- [ ] Đã benchmark riêng từng tính năng và tổ hợp trên đúng broker/client version.
- [ ] Có throughput, p95/p99, queue depth, oldest age, delivering, CPU/GC, I/O, disk và network metrics.
- [ ] Có test restart, redelivery, duplicate, offline subscriber và slow consumer.
- [ ] Không đánh đổi correctness/order/security chỉ để tăng messages/sec.

## 17. Kết luận

**Selector quyết định message nào đủ điều kiện tới consumer; priority ảnh hưởng thứ tự dispatch; message group ràng buộc consumer ownership theo khóa; topic fan-out nhân số subscription cần nhận event.** Mỗi tính năng giải quyết một nhu cầu riêng và tạo một loại chi phí riêng.

Muốn hiệu năng ổn định, hãy giữ selector đơn giản và có coverage, dùng priority có fairness, chọn group key phân tán nhưng giữ đúng aggregate order, quản lý durable subscriber và sizing fan-out theo storage/network thực tế. Benchmark phải đo **throughput cùng p95/p99, oldest-message age, backlog theo từng queue/subscription và tính đúng nghiệp vụ**. Một cấu hình nhanh hơn nhưng để message không match nằm vô hạn, group nóng bị nghẽn hoặc subscriber offline chiếm đầy đĩa là một cấu hình chưa đạt yêu cầu.
