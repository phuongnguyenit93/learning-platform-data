# Destination policy và cách khớp chính sách theo tên

> **Chương:** Định tuyến Classic  
> **Phạm vi:** Apache ActiveMQ **Classic**, tập trung vào `destinationPolicy`, `policyMap` và `policyEntry` trong `activemq.xml`. Bài sử dụng cú pháp wildcard của **Classic** và ví dụ JMS Java; không áp dụng nguyên xi cấu hình này cho ActiveMQ Artemis.

## 1. Bài toán: cùng một broker, mỗi destination cần chính sách khác nhau

Giả sử một hệ thống xử lý đơn hàng dùng ActiveMQ Classic. Producer gửi công việc vào các JMS queue:

- `ORDERS.NORMAL`: đơn thường, lưu lượng lớn.
- `ORDERS.HIGH`: đơn ưu tiên, muốn giới hạn bộ nhớ riêng để không bị một queue chiếm quá nhiều tài nguyên.
- `ORDERS.RETRY.PAYMENT`: công việc thanh toán cần thử lại.
- `AUDIT.LOG`: ghi nhật ký tác vụ, không thuộc nhóm `ORDERS`.

Ứng dụng còn publish sự kiện vào JMS topic `EVENTS.ORDER.CREATED`.

Các destination này có cùng broker nhưng tính chất tải khác nhau. ActiveMQ Classic cho phép **gán cấu hình theo loại destination và tên destination** bằng một tập hợp các `policyEntry`. Chẳng hạn, mọi queue nhận giới hạn bộ nhớ cơ bản, các queue có tiền tố `ORDERS.` nhận chính sách riêng, và `ORDERS.HIGH` được xử lý đặc biệt hơn.

Điểm quan trọng: **destination policy quyết định broker áp dụng cấu hình gì cho destination đã được chọn; nó không quyết định producer gửi message đến destination nào.** Producer vẫn phải gửi tới tên queue/topic thích hợp. Việc khai báo chính sách cho `ORDERS.>` không tự tạo ra queue `ORDERS.HIGH`, không chuyển hướng message và không tự làm fan-out.

Sau bài này, bạn cần có khả năng:

1. Đọc được cấu trúc `destinationPolicy → policyMap → policyEntries → policyEntry`.
2. Giải thích chính xác `queue`, `topic`, dấu chấm `.`, ký tự `*` và `>` trong tên khớp chính sách.
3. Tìm chính sách có độ cụ thể cao nhất khi một tên khớp nhiều quy tắc.
4. Dự đoán trường hợp **không khớp**, sai chữ hoa/chữ thường và nhầm queue với topic.
5. Nhận ra vì sao chính sách cụ thể hơn **không tự động kế thừa** toàn bộ thuộc tính từ chính sách bao quát.
6. Viết một bài thử JMS để tạo destination có tên khác nhau và xác minh cấu hình đang có hiệu lực.

## 2. Destination trong Classic và vị trí của policy

Trong JMS, `Destination` là giao diện trừu tượng; hai kiểu thường dùng là:

- `Queue`: message được xử lý bởi một trong các consumer cạnh tranh đọc cùng queue.
- `Topic`: message được phân phối cho các subscription phù hợp của topic.

ActiveMQ Classic quản lý queue và topic theo **physical destination name**. Hai tên giống nhau về chuỗi ký tự nhưng khác loại vẫn là hai destination khác nhau:

~~~text
JMS Queue: ORDERS.NORMAL
JMS Topic: ORDERS.NORMAL
~~~

Một `policyEntry queue="ORDERS.NORMAL"` áp dụng cho **queue** tên đó; nó không đồng thời áp dụng cho **topic** cùng tên. Muốn cấu hình topic, phải có `policyEntry topic="..."` phù hợp hoặc dùng mặc định dành cho topic.

Một `policyEntry` mô tả các thông số quản lý destination, ví dụ:

| Nhóm hành vi | Thuộc tính hoặc thành phần thường gặp trong Classic | Ý nghĩa khái quát |
|---|---|---|
| Sử dụng bộ nhớ | `memoryLimit` | Giới hạn phần memory usage của destination, trong khuôn khổ usage chung của broker |
| Điều tiết producer | `producerFlowControl` | Cho phép broker gây backpressure khi gặp điều kiện thiếu tài nguyên |
| Paging/dispatch | `maxPageSize` và các policy liên quan | Điều chỉnh số message được đưa vào vùng xử lý/dispatch theo cơ chế tương ứng |
| Đọc trước | `queuePrefetch`, `topicPrefetch` hoặc cấu hình client | Ảnh hưởng số message consumer có thể được cấp trước; phải xem precedence của client |
| Message quá hạn/lỗi | `expireMessagesPeriod`, `deadLetterStrategy` | Kiểm soát quét expiration hoặc chọn DLQ theo policy |
| Subscription/chậm tiêu thụ | Các pending-message/slow-consumer policies | Hỗ trợ quản lý backlog và subscriber chậm, với semantics riêng cho queue/topic |

Các thuộc tính được hỗ trợ và giá trị mặc định có thể khác nhau theo **phiên bản ActiveMQ Classic**. Bài này dùng `memoryLimit` và `producerFlowControl` để giải thích cơ chế **khớp tên**; việc tuning thực tế cần xem chính xác bản Classic đang chạy.

### 2.1. Cơ chế nhìn từ broker

~~~mermaid
flowchart TD
    A["Producer/consumer dùng JMS Destination"] --> B["Broker xác định loại và physical name"]
    B --> C{"Queue hay topic?"}
    C -->|Queue| D["Xét các policyEntry queue=..."]
    C -->|Topic| E["Xét các policyEntry topic=..."]
    D --> F["Khớp tên theo exact / wildcard"]
    E --> F
    F --> G{"Có policy phù hợp?"}
    G -->|Có| H["Chọn policy phù hợp cụ thể nhất"]
    G -->|Không| I["Dùng hành vi mặc định của broker"]
    H --> J["Destination vận hành theo policy đã chọn"]
    I --> J
~~~

Đây là sơ đồ tư duy cho **cấu hình destination**. Nó không mô tả đường đi từng message: sau khi destination được thiết lập, broker xử lý send, enqueue, dispatch, acknowledgment và persistence theo cơ chế riêng.

## 3. Cấu trúc cấu hình `destinationPolicy`

Trong phân phối ActiveMQ Classic dùng Spring/XBean XML, các phần tử dưới đây thường nằm **bên trong phần tử `broker`** của `conf/activemq.xml`:

~~~xml
<destinationPolicy>
  <policyMap>
    <policyEntries>
      <!-- Chính sách cho mọi queue -->
      <policyEntry queue=">"
                   producerFlowControl="true"
                   memoryLimit="32mb"/>

      <!-- Chính sách cho nhóm queue ORDERS có tên phân cấp -->
      <policyEntry queue="ORDERS.>"
                   producerFlowControl="true"
                   memoryLimit="64mb"/>

      <!-- Chính sách riêng cho queue ORDERS.HIGH -->
      <policyEntry queue="ORDERS.HIGH"
                   producerFlowControl="true"
                   memoryLimit="16mb"/>

      <!-- Chính sách cho các topic sự kiện -->
      <policyEntry topic="EVENTS.>"
                   producerFlowControl="true"
                   memoryLimit="8mb"/>
    </policyEntries>
  </policyMap>
</destinationPolicy>
~~~

Đây là **đoạn cấu hình**, không phải toàn bộ tệp `activemq.xml` có thể tự chạy. Nó giả định broker đã có bộ khung XML/XBean hợp lệ, transport connector, persistence và tài nguyên hệ thống phù hợp. `memoryLimit` dùng cú pháp dung lượng được Classic hỗ trợ như `32mb`.

Tách riêng vai trò của từng lớp:

- `destinationPolicy`: gắn bộ policy của broker với các destination.
- `policyMap`: cấu trúc chọn chính sách theo destination.
- `policyEntries`: tập các quy tắc có điều kiện khớp tên.
- `policyEntry`: **một cấu hình hoàn chỉnh** cho một kiểu và mẫu tên destination.

Từ đoạn XML trên, `ORDERS.HIGH` và `ORDERS.NORMAL` đều là queue trong cùng một nhóm tiền tố, nhưng không nhất thiết được áp dụng cùng `memoryLimit`.

### 3.1. Một policy không phải là một destination

Đoạn này:

~~~xml
<policyEntry queue="ORDERS.>" memoryLimit="64mb"/>
~~~

có nghĩa: “với **queue** có tên khớp mẫu `ORDERS.>`, dùng cấu hình này nếu nó là entry được chọn”. Nó **không có nghĩa**:

- Tạo một queue tên `ORDERS.>` rồi chứa mọi message của `ORDERS.NORMAL`.
- Chuyển message `ORDERS.NORMAL` tới `ORDERS.HIGH`.
- Tạo topic hay subscription cho mọi hậu tố.
- Tạo trước tất cả queue tương lai có tên khớp mẫu.

Các tên wildcard trong policy là **mẫu khớp**, còn queue/topic mà JMS client sử dụng vẫn là destination thật với tên cụ thể.

## 4. Ngữ pháp tên và wildcard của ActiveMQ Classic

ActiveMQ Classic dùng dấu chấm `.` để chia tên destination thành các thành phần (segment). Ví dụ:

~~~text
ORDERS.RETRY.PAYMENT

ORDERS  |  RETRY  |  PAYMENT
segment1   segment2   segment3
~~~

Các mẫu thường dùng:

| Mẫu | Ý nghĩa | Ví dụ khớp | Ví dụ không khớp |
|---|---|---|---|
| `queue="ORDERS.HIGH"` | Khớp tên cụ thể | Queue `ORDERS.HIGH` | `ORDERS.NORMAL` |
| `queue=">"` | Wildcard rộng cho mọi tên queue | `AUDIT.LOG`, `ORDERS.HIGH` | Topic cùng tên |
| `queue="ORDERS.>"` | Các queue có phần tên tiếp sau tiền tố `ORDERS.` | `ORDERS.NORMAL`, `ORDERS.RETRY.PAYMENT` | `AUDIT.LOG` |
| `queue="ORDERS.*"` | Một segment ngay sau `ORDERS` | `ORDERS.NORMAL`, `ORDERS.HIGH` | `ORDERS.RETRY.PAYMENT` |
| `queue="PAYMENTS.*.RETRY"` | Đúng một segment tại vị trí `*` | `PAYMENTS.EU.RETRY` | `PAYMENTS.EU.SEPA.RETRY` |
| `queue="Consumer.*.VirtualTopic.>"` | Một segment nhóm consumer, sau đó là hậu tố sự kiện | `Consumer.Billing.VirtualTopic.OrderCreated` | `Consumer.Billing.Team.VirtualTopic.OrderCreated` |
| `topic="EVENTS.>"` | Các topic có tiền tố phân cấp `EVENTS.` | `EVENTS.ORDER.CREATED` | Queue `EVENTS.ORDER.CREATED` |

Quy tắc quan trọng:

1. **`*` khớp đúng một segment** (giới hạn bởi dấu chấm). Nó không tự nuốt nhiều cấp phân cấp.
2. **`>` khớp phần tên nhiều cấp phía sau**, thường dùng cuối mẫu. `queue=">"` là mẫu bao phủ toàn bộ queue.
3. **`queue=` và `topic=` là hai miền khớp khác nhau**. Không có bước tự đổi topic thành queue trong policy.
4. **Tên có phân biệt chữ hoa/chữ thường**. `ORDERS.HIGH` khác `orders.high`.
5. **Dấu chấm có ý nghĩa cấu trúc** khi dùng wildcard. `ORDERS.*` không tương đương một phép tìm chuỗi kiểu “bắt đầu bằng ORDERS”.
6. Đối với **tên đúng bằng tiền tố mà không có segment phía sau** (ví dụ queue chỉ tên `ORDERS`), nên khai báo/kiểm thử riêng thay vì suy diễn từ `ORDERS.>`; cách đọc rõ ràng nhất trong ví dụ là dùng tên có hậu tố như `ORDERS.NORMAL`.

**Không sử dụng wildcard ở tên thật của queue chỉ để “kế thừa cấu hình”.** App gửi tới `ORDERS.NORMAL`, không gửi tới “queue wildcard” `ORDERS.>`. Ở phía consumer, Classic cũng có tính năng wildcard subscriptions, nhưng đó là một **tình huống sử dụng khác** với wildcard trong `policyEntry`.

### 4.1. Ví dụ đọc mẫu bằng cách tách segment

Xét hai mẫu:

~~~text
queue="PAYMENTS.*.RETRY"
queue="PAYMENTS.>"
~~~

Các queue:

~~~text
PAYMENTS.EU.RETRY
PAYMENTS.ASIA.RETRY
PAYMENTS.EU.SEPA.RETRY
~~~

Mẫu thứ nhất chỉ khớp hai tên đầu (đúng ba segment); mẫu thứ hai khớp cả ba vì phần sau `PAYMENTS.` có độ sâu khác nhau.

Từ đó có một quy tắc đặt tên hữu ích: **quy ước segment chính là một phần của thiết kế policy**. Nếu nhóm phát triển tự do đặt tên `PAYMENTS_EU_RETRY`, `payments.eu.retry` và `PAYMENTS.EU.RETRY`, chúng sẽ không được khớp như nhau.

## 5. Khi nhiều `policyEntry` cùng khớp: độ cụ thể quyết định

Một destination có thể khớp nhiều mẫu trong `policyMap`. Với đoạn cấu hình ở mục 3, queue `ORDERS.HIGH` khớp cả:

~~~text
queue=">"
queue="ORDERS.>"
queue="ORDERS.HIGH"
~~~

Đây là các mẫu có mức cụ thể phân biệt rõ: entry tên **chính xác** là lựa chọn cụ thể nhất; mẫu tiền tố `ORDERS.>` cụ thể hơn mẫu toàn cục `>`.

Bảng xác định kết quả của **cấu hình đã khai báo ở mục 3**:

| Destination thật | Các entry phù hợp | Policy được chọn | `memoryLimit` |
|---|---|---|---|
| Queue `ORDERS.HIGH` | `>`, `ORDERS.>`, `ORDERS.HIGH` | `queue="ORDERS.HIGH"` | `16mb` |
| Queue `ORDERS.NORMAL` | `>`, `ORDERS.>` | `queue="ORDERS.>"` | `64mb` |
| Queue `ORDERS.RETRY.PAYMENT` | `>`, `ORDERS.>` | `queue="ORDERS.>"` | `64mb` |
| Queue `AUDIT.LOG` | `>` | `queue=">"` | `32mb` |
| Queue `EVENTS.ORDER.CREATED` | `>` | `queue=">"` | `32mb` |
| Topic `EVENTS.ORDER.CREATED` | `topic="EVENTS.>"` | `topic="EVENTS.>"` | `8mb` |
| Topic `ORDERS.NORMAL` | Không có topic entry khớp | Mặc định của broker | Không lấy `64mb` từ queue policy |
| Queue `orders.high` | `>` | `queue=">"` | `32mb` |

**Lưu ý về thứ tự XML:** không nên coi “entry nào viết sau cùng thì thắng”. Cách lập luận đúng là kiểm tra kiểu destination và mức độ cụ thể của mẫu. Đối với các mẫu chồng chéo nhưng **không có quan hệ bao hàm rõ ràng**, chẳng hạn hai wildcard ràng buộc các segment khác nhau, đừng dựa vào cảm giác hay thứ tự trong `policyEntries`: hãy loại bỏ sự mơ hồ khi thiết kế, hoặc kiểm thử trên chính phiên bản Classic đang dùng.

### 5.1. Trường hợp khó: hai wildcard chéo nhau

Giả sử có:

~~~xml
<policyEntry queue="ORDERS.*.RETRY" memoryLimit="32mb"/>
<policyEntry queue="ORDERS.EU.>"    memoryLimit="48mb"/>
~~~

Queue `ORDERS.EU.RETRY` khớp **cả hai**. Hai policy mô tả hai chiều phân loại khác nhau: một bên nhắm tới trạng thái RETRY, bên kia nhắm tới vùng EU. Đây là kiểu cấu hình khó đọc, dễ tạo kết quả ngoài dự đoán khi chỉnh sửa policy hoặc đổi phiên bản.

Cách làm rõ ý định là thêm một entry khớp chính xác:

~~~xml
<policyEntry queue="ORDERS.EU.RETRY" memoryLimit="24mb"/>
~~~

hoặc đổi quy ước tên / tách chính sách để các nhóm không còn đè nhau. Khi sửa ví dụ này trong cấu hình thực tế, phải giữ các entry đang dùng khác và kiểm thử trạng thái effective policy. **Chỉ dựa vào việc XML hợp lệ là chưa đủ.**

### 5.2. Không có cơ chế cộng dồn toàn bộ thuộc tính từ ba entry

Giả sử:

~~~xml
<policyEntry queue=">" producerFlowControl="true"
             memoryLimit="32mb"/>

<policyEntry queue="ORDERS.>" memoryLimit="64mb"/>
~~~

Với queue `ORDERS.NORMAL`, policy cụ thể cho `ORDERS.>` được chọn. **Không mặc định hiểu** cấu hình hiệu lực là `memoryLimit="64mb"` từ entry thứ hai và `producerFlowControl="true"` kế thừa từ entry thứ nhất. `PolicyEntry` cụ thể là một cấu hình riêng, và những thuộc tính không chỉ định sẽ theo cách khởi tạo/mặc định của loại entry đó trong phiên bản hiện tại.

Nếu cần bảo đảm `producerFlowControl="true"` ở nhóm `ORDERS.>`, hãy khai báo trực tiếp tại entry này:

~~~xml
<policyEntry queue="ORDERS.>"
             memoryLimit="64mb"
             producerFlowControl="true"/>
~~~

Đây là khác biệt quan trọng giữa **chọn một policy** và **kế thừa theo kiểu CSS**. Đừng thiết kế policy với giả định mọi thuộc tính từ entry rộng sẽ hợp nhất vào entry hẹp.

## 6. Policy được chọn ảnh hưởng gì ở runtime?

Bài này chỉ chọn hai ví dụ thông số để theo sát cơ chế khớp tên.

### 6.1. `memoryLimit` là hạn mức memory usage theo destination

Ví dụ `memoryLimit="16mb"` cho `ORDERS.HIGH` nhằm kiểm soát phần bộ nhớ của destination này trong hệ thống quản lý tài nguyên Classic. Nó **không phải**:

- Giới hạn kích thước tối đa của **một** message là 16 MB.
- Giới hạn dung lượng file KahaDB trên đĩa đúng 16 MB.
- Cam kết rằng tổng RAM của broker bằng tổng `memoryLimit` tất cả queues.
- Cam kết message sẽ bị xóa khi backlog vượt 16 MB.

Classic còn có các giới hạn tổng theo `systemUsage`, cursor/persistence, store usage và các chính sách flow control. Khi destination bắt đầu thiếu tài nguyên, hành vi cụ thể phụ thuộc cả **loại message, persistence, memory/store usage và chính sách producer**.

### 6.2. `producerFlowControl` liên quan backpressure

Khi áp lực tài nguyên tăng, cấu hình `producerFlowControl="true"` cho phép cơ chế flow control của Classic tác động tới producer trong các tình huống thích hợp. Producer có thể chờ hoặc nhận tín hiệu lỗi/timeout tùy đường truyền, loại message và lựa chọn của client/broker.

**Không** kiểm thử bằng cách gửi đúng một message nhỏ rồi kết luận `producerFlowControl` không hoạt động. Cần tải đủ lớn, consumer chậm hoặc tạm ngắt, store và memory usage được quan sát đồng thời.

**Không** tắt flow control chỉ để producer “không bị chặn” mà chưa thiết kế giới hạn disk, backlog và đường phục hồi. Việc producer tiếp tục gửi nhanh hơn consumer trong thời gian dài sẽ làm tăng tồn đọng ở một nơi khác.

### 6.3. Cùng tên queue nhưng thuộc nhóm nào?

Giả sử Java code tạo:

~~~java
Queue target = session.createQueue("ORDERS.HIGH");
producer.send(target, message);
~~~

Broker chọn chính sách của queue `ORDERS.HIGH`, dựa trên **loại Queue** và **physical name**. Thuộc tính `JMSPriority`, `JMSCorrelationID` hoặc message selector của consumer không khiến broker chọn sang `queue="ORDERS.NORMAL"`. Những thông tin đó liên quan gửi/nhận message, không phải điều kiện `policyEntry` theo tên.

Tương tự, hai producer khác nhau cùng gửi vào `ORDERS.HIGH` sử dụng policy của destination đó; policy không chọn riêng theo user ID của từng producer. Quyền gửi/nhận phải cấu hình qua **security/authorization**, là một cơ chế khác.

## 7. Trường hợp Classic hay gặp: Virtual Topic và tên queue nhóm nhận

**Virtual Topics** là một tính năng quen thuộc của ActiveMQ Classic: producer gửi tới topic logic, trong khi các nhóm consumer có thể đọc từ các queue theo quy ước. Ví dụ:

~~~text
Producer gửi topic:
  VirtualTopic.OrderCreated

Billing đọc queue:
  Consumer.Billing.VirtualTopic.OrderCreated

Email đọc queue:
  Consumer.Email.VirtualTopic.OrderCreated
~~~

Nếu mục tiêu là áp dụng memory policy cho **queue nhóm nhận** của Virtual Topic, phải khớp **queue name**:

~~~xml
<policyEntry queue="Consumer.*.VirtualTopic.>"
             memoryLimit="48mb"
             producerFlowControl="true"/>
~~~

Giải thích:

- `Consumer` là segment cố định đầu tiên.
- `*` là tên một nhóm như `Billing` hoặc `Email`.
- `VirtualTopic` là segment cố định tiếp theo.
- `>` bao phủ phần đuôi tên sự kiện.

Policy này có thể khớp queue `Consumer.Billing.VirtualTopic.OrderCreated` và `Consumer.Email.VirtualTopic.OrderCreated`. Nó không áp dụng trực tiếp cho topic producer `VirtualTopic.OrderCreated`, vì đó là **Topic**, còn entry khai báo `queue`.

Nếu cần policy dành cho **topic producer**, có thể viết entry khác:

~~~xml
<policyEntry topic="VirtualTopic.>"
             memoryLimit="16mb"
             producerFlowControl="true"/>
~~~

**Một lỗi rất phổ biến:** chỉ cấu hình `topic="VirtualTopic.>"` rồi kỳ vọng các queue `Consumer.Billing.VirtualTopic.*` cũng bị giới hạn cùng thông số. Đó là hai loại destination khác nhau. Hệ thống có thể xuất hiện backlog chủ yếu tại queue nhóm nhận, vì vậy cần kiểm soát các queue này một cách tường minh.

Cũng cần phân biệt **policy name matching** và **quy tắc Virtual Topic routing**. Entry `Consumer.*.VirtualTopic.>` chỉ chọn cấu hình cho queue nào đã được tạo/được broker quản lý; nó không tự cài đặt cơ chế Virtual Topic hay tự sinh nhóm consumer.

## 8. Thay đổi policy ảnh hưởng tới DLQ, subscription và prefetch thế nào?

Các chức năng này có thể được điều khiển qua `policyEntry`, nhưng **điểm cần nhớ ở bài này vẫn là cách khớp tên**.

### 8.1. DLQ là một destination có tên riêng

Giả sử queue `ORDERS.HIGH` có chính sách dead-letter chuyển message không xử lý được sang `DLQ.ORDERS.HIGH`. Khi message đã nằm trong DLQ, đó là **một queue khác**.

- `queue="ORDERS.>"` khớp `ORDERS.HIGH`.
- `queue="ORDERS.>"` **không khớp** `DLQ.ORDERS.HIGH`.
- `queue="DLQ.>"` mới là một mẫu có thể khớp queue DLQ này.
- `queue=">"` vẫn có thể là policy dự phòng áp dụng cho DLQ nếu không có entry cụ thể hơn.

Ví dụ một entry dành cho **source queue**, dùng chiến lược DLQ riêng của Classic:

~~~xml
<policyEntry queue="ORDERS.>"
             producerFlowControl="true"
             memoryLimit="64mb">
  <deadLetterStrategy>
    <individualDeadLetterStrategy
        queuePrefix="DLQ."
        useQueueForQueueMessages="true"/>
  </deadLetterStrategy>
</policyEntry>
~~~

Đây là ví dụ **thay thế** entry `queue="ORDERS.>"` ở mục 3, không thêm song song hai entry có cùng mẫu. Nếu trong cấu hình vẫn tồn tại entry cụ thể hơn `queue="ORDERS.HIGH"`, hãy kiểm tra/khai báo dead-letter strategy tại entry cụ thể đó theo yêu cầu nghiệp vụ: **không giả định phần tử `deadLetterStrategy` từ `ORDERS.>` sẽ tự cộng dồn**.

Cơ chế retry/redelivery của Classic còn có thể phụ thuộc client ActiveMQ và các tùy chọn khác; riêng việc đặt DLQ strategy không đồng nghĩa đã chỉ định đầy đủ số lần retry.

### 8.2. Durable topic subscriber và chính sách topic

Một topic có nhiều durable subscribers vẫn là **topic destination** khi xét `topic="EVENTS.>"`. Nhưng cấu hình pending-message cursor, sự tồn đọng của từng subscription và hành vi durable subscription có đặc thù riêng; không suy từ queue `EVENTS.ORDER.CREATED` cùng tên.

Nếu muốn quản lý backlog độc lập bằng queue nhóm nhận, Classic Virtual Topics là một thiết kế cần cân nhắc, nhưng không phải thay thế tự động của durable subscriptions. Trong cả hai cách, **đối tượng được policy áp dụng** phải được xác định rõ là topic hay queue.

### 8.3. Client destination options khác broker destination policy

ActiveMQ Classic Java client có hỗ trợ một số **destination options** qua tên destination, ví dụ:

~~~java
Queue queue = session.createQueue(
        "ORDERS.HIGH?consumer.prefetchSize=20");
~~~

Trong client Classic hỗ trợ cú pháp này, phần `consumer.prefetchSize=20` là tùy chọn phía consumer/destination client, **không phải** khai báo một entry mới trong `policyMap`. Tùy chọn như vậy có thể tương tác với prefetch do broker policy/default định nghĩa; cần kiểm tra thứ tự ưu tiên và client library đang dùng.

Không đưa dấu `?consumer.prefetchSize=20` vào `policyEntry queue="..."` để tìm cách khớp queue: policy phải nhắm tới physical name `ORDERS.HIGH`.

## 9. Ví dụ Java JMS kiểm chứng tên queue và topic

Chương trình dưới đây dùng **ActiveMQ Classic 5.x với client truyền thống `org.apache.activemq:activemq-client` và API `javax.jms`**. Đây là ví dụ gửi message để **tạo/sử dụng destination có tên cụ thể**, sau đó đối chiếu broker console/JMX với bảng ở mục 5. Với bản Classic hoặc client chuyển sang namespace `jakarta.jms`, phải chọn lại dependency/import tương ứng; không trộn hai namespace.

**Chuẩn bị:** một broker Classic đang chạy tại `tcp://localhost:61616`; cấu hình policy ở mục 3 đã được nạp; user `app` có quyền gửi tới queue/topic thử nghiệm. Mật khẩu trong code chỉ là giá trị lab, không dùng trong production.

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.Destination;
import javax.jms.JMSException;
import javax.jms.MessageProducer;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicDestinationPolicyProbe {
    public static void main(String[] args) throws JMSException {
        if (args.length != 2 ||
                (!"queue".equals(args[0]) && !"topic".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: java ClassicDestinationPolicyProbe "
                  + "<queue|topic> <destinationName>");
        }

        String type = args[0];
        String name = args[1];

        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            // Producer có thể gửi mà không cần connection.start():
            // start() dùng để bắt đầu delivery cho consumer.
            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            try {
                Destination destination = "queue".equals(type)
                        ? session.createQueue(name)
                        : session.createTopic(name);

                MessageProducer producer =
                        session.createProducer(destination);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);

                    for (int i = 1; i <= 3; i++) {
                        TextMessage message = session.createTextMessage(
                                "probe=" + name + "; seq=" + i);
                        message.setStringProperty("testRun", "policy-demo");
                        producer.send(message);
                    }

                    System.out.println("Sent 3 messages to "
                            + type + ":" + name);
                } finally {
                    producer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }
}
~~~

Ví dụ cách chạy **sau khi build bằng dependency Classic/JMS tương thích**:

~~~text
java ClassicDestinationPolicyProbe queue ORDERS.NORMAL
java ClassicDestinationPolicyProbe queue ORDERS.HIGH
java ClassicDestinationPolicyProbe queue AUDIT.LOG
java ClassicDestinationPolicyProbe topic EVENTS.ORDER.CREATED
java ClassicDestinationPolicyProbe topic ORDERS.NORMAL
~~~

Tùy hệ thống build, lệnh chạy thực tế cần classpath chứa ứng dụng và JMS/ActiveMQ client. Chuỗi lệnh trên trình bày **đối số**, không thay thế cấu hình Maven/Gradle hoặc classpath.

Quan sát các điểm sau:

1. Hai destination `Queue ORDERS.NORMAL` và `Topic ORDERS.NORMAL` là hai đối tượng khác loại.
2. `ORDERS.HIGH` phải được xem dưới nhóm Queue; entry exact có mức cụ thể cao nhất trong cấu hình mục 3.
3. `AUDIT.LOG` không bắt đầu bằng `ORDERS.` nên chỉ nhận entry queue rộng `>`.
4. Topic `EVENTS.ORDER.CREATED` được khớp bởi `topic="EVENTS.>"`.
5. Topic `ORDERS.NORMAL` **không** lấy `memoryLimit="64mb"` từ `queue="ORDERS.>"`.

**Hạn chế quan trọng:** ba message nhỏ gửi thành công **không trực tiếp chứng minh** limit hay flow control đang được áp dụng; chúng chỉ tạo/tác động các destination có tên dự kiến. Cần quan sát cấu hình runtime qua JMX/Web Console hoặc tạo tải có kiểm soát mới xác minh chính sách thực sự.

### 9.1. Khi cần kiểm chứng cả consumer

Một consumer JMS queue có thể được viết ngắn như sau; đoạn code giả định đã có `Connection connection` và `Session session` hợp lệ:

~~~java
// Khởi tạo consumer trên queue cụ thể; không dùng tên wildcard policy.
javax.jms.Queue queue = session.createQueue("ORDERS.HIGH");
javax.jms.MessageConsumer consumer = session.createConsumer(queue);
try {
    connection.start();
    javax.jms.Message received = consumer.receive(5_000L);
    if (received != null) {
        process(received);      // Logic nghiệp vụ phải hỗ trợ idempotency.
        received.acknowledge(); // Dùng khi session là CLIENT_ACKNOWLEDGE.
    }
} finally {
    consumer.close();
}
~~~

Đoạn này **chỉ là minh họa**, không đặt vào cùng session `AUTO_ACKNOWLEDGE` của producer nếu muốn kiểm soát ACK thủ công. Với `CLIENT_ACKNOWLEDGE`, `acknowledge()` có phạm vi session theo JMS, không nhất thiết chỉ ACK duy nhất message đó. Trong ví dụ kiểm chứng policy, **consumer không thay đổi entry đã chọn theo tên queue**.

## 10. Quy trình xác minh policy có thực sự được áp dụng

Chỉ nhìn XML chưa đủ, nhất là khi broker chạy với cấu hình tùy biến hoặc nhiều instance. Có thể kiểm tra theo quy trình sau.

### Bước 1 — Xác định broker và tệp cấu hình

Ghi lại phiên bản Classic, thư mục cấu hình/broker instance, broker name, port và cách khởi động. Xác nhận tiến trình đang chạy thật sự sử dụng `activemq.xml` chứa `destinationPolicy` đã sửa.

Đừng chỉnh một bản `activemq.xml` trong package hoặc thư mục development rồi mặc định production instance sử dụng bản đó.

### Bước 2 — Rà soát toàn bộ entry đang có

Lập bảng `(queue/topic, pattern, thuộc tính)`; đánh dấu entry rộng `>`, entry tiền tố, entry exact và các wildcard giao nhau. Đừng chỉ xem entry mới thêm mà bỏ qua entry cụ thể hơn vốn có.

Nếu hai entry có **cùng pattern và cùng loại** nhưng cấu hình khác nhau, đó là tín hiệu cần hợp nhất/sửa: việc dựa vào vị trí trong XML để “override” không phải quy ước quản trị an toàn.

### Bước 3 — Khớp tên bằng tay

Với một destination thử nghiệm:

1. Ghi chính xác **loại** Queue hay Topic.
2. Ghi chính xác **physical name**, kể cả chữ hoa và dấu chấm.
3. Lọc các `policyEntry` cùng loại.
4. Tách tên và mẫu theo dấu chấm, kiểm tra exact, `*` và `>`.
5. Với các mẫu phân cấp rõ ràng, chọn entry cụ thể nhất; với wildcard chéo nhau, xem lại thiết kế và kiểm chứng runtime.
6. Ghi bảng thông số dự kiến của **entry được chọn**, không trộn thuộc tính từ các entry khác.

### Bước 4 — Nạp lại cấu hình theo cơ chế phiên bản đang dùng

Trong vận hành thông thường, thay `activemq.xml` có thể cần **khởi động lại broker** theo quy trình có kiểm soát; đừng mặc định mọi thay đổi `policyMap` tự áp dụng nóng cho destination đã tồn tại. Nếu nền tảng có cơ chế reload riêng, phải chứng minh loại cấu hình nào được reload và destination nào được tái áp dụng policy.

Với hệ thống đang có message PERSISTENT, restart/failover cần kế hoạch tránh gián đoạn dịch vụ và kiểm tra backlog sau khi broker trở lại.

### Bước 5 — Đối chiếu runtime bằng JMX hoặc console

Dùng Web Console/JMX của chính broker để kiểm tra:

- Queue/topic có đúng tên và loại.
- Thuộc tính runtime tương ứng (nếu phiên bản/MBean cung cấp), chẳng hạn memory limit, memory usage, producer flow control hoặc các dấu hiệu policy.
- Độ sâu queue, số consumer và số message in-flight khi thử gửi.
- Broker log có cảnh báo về cấu hình, store/memory hoặc producer flow control không.

**Không có mặt một thuộc tính trên Web Console không chứng minh policy không áp dụng**: bộ UI/MBean có thể không hiển thị mọi giá trị. Khi cần, dùng MBean hoặc thí nghiệm tải để kiểm chứng.

### Bước 6 — Kiểm thử giới hạn theo tải và theo tên

Để phân biệt `ORDERS.HIGH` (16 MB) với `ORDERS.NORMAL` (64 MB), dùng payload có kích thước thực tế, tạm làm chậm consumer, ghi lại enqueue rate, broker memory/store usage, producer latency/timeout và recovery khi consumer trở lại. Dừng thử trước khi đầy disk hoặc gây lỗi dịch vụ khác.

Cần tách yếu tố **per-destination limit** khỏi **system-wide limit**. Nếu giới hạn tổng của broker thấp hơn hoặc tình trạng disk đã đầy, hai queue có thể cùng bị điều tiết bởi tài nguyên chung, khiến thí nghiệm không phân biệt được chính sách theo tên.

## 11. Các sai lầm hay gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Dùng `queue="ORDERS.*"` cho cả `ORDERS.RETRY.PAYMENT` | `*` chỉ là một segment | Dùng `ORDERS.>` nếu muốn nhiều cấp |
| Dùng `topic="EVENTS.>"` rồi mong queue `EVENTS.ORDER.CREATED` nhận policy | Queue/topic là hai loại destination khác nhau | Tạo `policyEntry queue=...` riêng nếu cần |
| Ghi `queue="orders.>"` nhưng app dùng `ORDERS.NORMAL` | Tên phân biệt hoa/thường | Chuẩn hóa naming convention |
| Dùng entry cụ thể chỉ ghi `memoryLimit` và nghĩ các thuộc tính từ `queue=">"` tự được kế thừa | `PolicyEntry` được chọn theo entry, không phải merge thuộc tính | Khai báo tường minh các thông số quan trọng ở entry cụ thể |
| Coi `memoryLimit="16mb"` là kích cỡ tối đa của một message | Memory usage và message size khác nhau | Theo dõi memory/store và message size riêng |
| Coi `producerFlowControl` là routing | Flow control là điều tiết tài nguyên | Phân biệt chính sách tài nguyên với destination của producer |
| Gửi tới `ORDERS.>` với ý định tạo “queue nhóm” | Wildcard trong policy là mẫu khớp, không phải queue tổng hợp | Gửi tới queue thật như `ORDERS.HIGH` |
| Áp `topic="VirtualTopic.>"` để kiểm soát queue `Consumer.Billing.VirtualTopic.*` | Queue consumer có tên khác và loại khác | Dùng queue pattern `Consumer.*.VirtualTopic.>` |
| Nghĩ XML entry viết sau cùng chắc chắn thắng | Matching dựa theo loại và mức cụ thể | Tránh overlap mơ hồ, kiểm thử effective policy |
| Thử gửi ba message rồi kết luận flow control đúng | Chưa đủ áp lực để kích hoạt limit | Đo tải và metric broker có kiểm soát |
| Đổi XML mà không kiểm tra broker instance đang chạy | Có thể sửa sai tệp hoặc policy chưa được nạp | Xác định runtime configuration và kiểm tra sau reload/restart |

## 12. Bài thực hành có đáp án giải thích

### Thực hành 1 — Dự đoán entry được chọn

Giả định broker có các entry:

~~~xml
<policyEntry queue=">" memoryLimit="24mb"/>
<policyEntry queue="PAYMENTS.>" memoryLimit="48mb"/>
<policyEntry queue="PAYMENTS.EU.RETRY" memoryLimit="12mb"/>
<policyEntry topic="PAYMENTS.>" memoryLimit="6mb"/>
~~~

Hãy xác định policy cho:

1. Queue `PAYMENTS.US.NEW`.
2. Queue `PAYMENTS.EU.RETRY`.
3. Queue `AUDIT.LOG`.
4. Topic `PAYMENTS.EU.RETRY`.
5. Topic `AUDIT.LOG`.

**Đáp án:**

| Destination | Entry được chọn | Giải thích |
|---|---|---|
| Queue `PAYMENTS.US.NEW` | `queue="PAYMENTS.>"`, 48 MB | Khớp tiền tố và entry rộng, chọn tiền tố |
| Queue `PAYMENTS.EU.RETRY` | `queue="PAYMENTS.EU.RETRY"`, 12 MB | Tên exact cụ thể nhất |
| Queue `AUDIT.LOG` | `queue=">"`, 24 MB | Không thuộc nhóm `PAYMENTS` |
| Topic `PAYMENTS.EU.RETRY` | `topic="PAYMENTS.>"`, 6 MB | Topic không lấy chính sách queue exact |
| Topic `AUDIT.LOG` | Không có entry topic phù hợp | Sử dụng cấu hình mặc định của broker |

### Thực hành 2 — Phát hiện sai lầm wildcard

Cho mẫu:

~~~xml
<policyEntry queue="NOTIFY.*" memoryLimit="8mb"/>
~~~

Người phát triển cho rằng nó khớp cả `NOTIFY.EMAIL` lẫn `NOTIFY.EMAIL.RETRY`.

**Phân tích:** `NOTIFY.EMAIL` có hai segment, phù hợp với một `*`; `NOTIFY.EMAIL.RETRY` có ba segment, nên không khớp mẫu đó. Nếu muốn xử lý nhóm tên dài hơn, cân nhắc `NOTIFY.>` hoặc thêm entry cụ thể.

### Thực hành 3 — Sửa cấu hình Virtual Topic

Một broker dùng queue `Consumer.Billing.VirtualTopic.OrderCreated`. Admin cấu hình:

~~~xml
<policyEntry topic="Consumer.*.VirtualTopic.>"
             memoryLimit="16mb"/>
~~~

**Lỗi:** entry khai báo `topic` nhưng destination thật là **queue**.

**Sửa:**

~~~xml
<policyEntry queue="Consumer.*.VirtualTopic.>"
             memoryLimit="16mb"
             producerFlowControl="true"/>
~~~

Sau khi sửa, cần kiểm tra broker đã nạp cấu hình và queue thực tế khớp theo phiên bản hiện tại.

### Thực hành 4 — Không được suy cơ chế kế thừa

Có:

~~~xml
<policyEntry queue=">" memoryLimit="32mb"
             producerFlowControl="true"/>
<policyEntry queue="INVOICE.>" memoryLimit="64mb"/>
~~~

**Câu hỏi:** Có chắc `INVOICE.NEW` dùng `producerFlowControl=true` chỉ vì entry `queue=">"` có cấu hình này không?

**Đáp án:** **Không.** Entry cụ thể `INVOICE.>` là nơi khai báo cần xem; các thuộc tính không chỉ định được xác định bởi mặc định/cách khởi tạo của entry, không tự merge từ entry rộng. Muốn bảo đảm thì khai báo `producerFlowControl="true"` trực tiếp ở `INVOICE.>`.

## 13. Checklist trước khi đưa policy theo tên vào production

- Đã xác định **physical name** của từng queue/topic từ mã producer/consumer?
- Naming convention dùng segment nhất quán, phân biệt hoa/thường và được review?
- Mọi policy pattern đều dùng đúng `queue` hoặc `topic`?
- Đã kiểm tra `*` (một segment) và `>` (phần hậu tố nhiều cấp), đặc biệt với queue có nhiều dấu chấm?
- Đã có quy tắc exact cho destination đặc biệt, và tránh các wildcard chéo nhau gây mơ hồ?
- Các thuộc tính quan trọng được khai báo đầy đủ trong **entry thực sự được chọn**, không dựa vào “kế thừa” ngầm?
- Đã phân biệt `memoryLimit` với giới hạn tổng broker, store/disk và giới hạn kích cỡ message?
- Nếu dùng Virtual Topics, đã thiết kế policy cho **queue nhóm nhận** và **topic producer** theo nhu cầu thực?
- Đã kiểm tra broker instance nạp đúng `activemq.xml`, có kế hoạch reload/restart, và đối chiếu bằng JMX/console?
- Đã thử tên chính xác, wildcard và một trường hợp **không khớp**, cả queue lẫn topic?
- Đã thử tải có kiểm soát và theo dõi backpressure, backlog, latency, disk, memory?

## 14. Kết luận kỹ thuật

Trong ActiveMQ Classic, `destinationPolicy` cung cấp **cấu hình theo loại và tên destination**. `policyMap` chọn `policyEntry` theo quy tắc tên, trong đó `*` đại diện **một segment**, còn `>` đại diện phần hậu tố có nhiều cấp. Với các mẫu lồng nhau rõ ràng, entry có tên cụ thể nhất là entry cần xem trước; kiểu **Queue** và **Topic** được đối chiếu riêng.

Ba nguyên tắc giúp tránh lỗi cấu hình là: **(1)** định nghĩa naming convention trước khi viết wildcard, **(2)** coi mỗi `policyEntry` là một cấu hình riêng thay vì chồng/merge thuộc tính từ entry rộng, và **(3)** kiểm chứng kết quả với chính broker đang chạy. Làm đúng ba việc này giúp giới hạn tài nguyên và điều tiết producer đúng nhóm queue/topic, mà không nhầm cơ chế cấu hình destination với việc định tuyến message hoặc quản lý subscription.
