# Quy tắc đặt tên, tạo trước và quản lý vòng đời destination

> **Chương:** Queue và Topic  
> **Phạm vi:** Quản trị tên, khai báo và vòng đời của queue, topic, address và subscription trong Apache ActiveMQ Classic và Apache ActiveMQ Artemis. Ví dụ áp dụng cho ứng dụng Java/JMS, có phân biệt những thao tác riêng của từng broker.

Trong hệ thống tích hợp bất đồng bộ, một destination là **hợp đồng kết nối giữa các dịch vụ**. Chỉ cần producer đổi tên queue, consumer tạo nhầm topic, hoặc một subscription bị xóa khi còn message chưa xử lý, hệ thống có thể im lặng tích tụ backlog hoặc mất đường nhận dữ liệu. Vì vậy, đặt tên và tạo destination phải được quản lý giống một thay đổi giao diện API: có quy ước, người sở hữu, khai báo phiên bản, kiểm tra quyền, kế hoạch chuyển đổi và điều kiện thu hồi.

Bài này tập trung trả lời ba câu hỏi thực hành:

1. Đặt tên destination thế nào để **ổn định, dễ tra cứu, tránh xung đột và an toàn khi mở rộng**?
2. **Ai tạo**, tạo **trước thời điểm nào**, và bằng cách nào để phát hiện tên sai hoặc cấu hình sai trước khi ứng dụng xử lý dữ liệu thật?
3. Khi thêm phiên bản mới, ngừng một subscriber hoặc dọn queue cũ, làm thế nào để **không xóa nhầm backlog, không tạo destination rác và không bỏ sót nhóm nhận**?

## 1. Destination có những “danh tính” nào?

Trước khi đặt tên, phải xác định **đối tượng thực sự được đặt tên**. Một tên xuất hiện trong Java code không nhất thiết tương ứng một đối tượng vật lý duy nhất trên broker.

| Đối tượng | Ý nghĩa | Ai thường quản lý vòng đời? |
|---|---|---|
| **JMS Queue / JMS Topic** | Destination logic mà producer/consumer tham chiếu qua API JMS | Nhóm ứng dụng theo hợp đồng tích hợp |
| **Classic queue / topic** | Destination vật lý tương ứng với tên trong ActiveMQ Classic | Quản trị broker, cấu hình hoặc công cụ quản lý |
| **Artemis address** | Điểm nhận message và áp dụng routing type | Quản trị broker / nền tảng messaging |
| **Artemis queue** | Nơi các message được giữ để consumer tiêu thụ, gắn với một address | Nền tảng hoặc cơ chế tạo subscription |
| **Durable subscription** | Danh tính nhận bền vững của một nhóm subscriber trên topic | Nhóm consumer, phối hợp với người quản trị |
| **Temporary destination** | Đích tạm gắn với vòng đời kết nối JMS | Ứng dụng tạo/đóng kết nối |

### 1.1. Một tên JMS có thể ánh xạ khác nhau giữa Classic và Artemis

Trong **ActiveMQ Classic**, tên như \`billing.charge.commands.v1\` thường là tên một queue đích JMS. Trong **Artemis**, JMS queue thường được ánh xạ tới một **address ANYCAST** và queue tương ứng; JMS topic được ánh xạ tới một **address MULTICAST** cùng các subscription queue thích hợp.

Ví dụ Artemis:

~~~text
JMS Queue: billing.charge.commands.v1
  Address: billing.charge.commands.v1  [ANYCAST]
  Queue:   billing.charge.commands.v1

JMS Topic: orders.events.v1
  Address: orders.events.v1           [MULTICAST]
  Queue:   inventory.orders.v1        [durable subscriber / queue]
  Queue:   notifications.orders.v1    [durable subscriber / queue]
~~~

Sơ đồ trên thể hiện **quy hoạch logic**. Hai queue multicast được khai báo tĩnh có thể dùng làm các luồng nhận riêng, nhưng chúng **không tự động có cùng danh tính và vòng đời** với durable subscription được tạo bằng mọi phiên bản JMS client. Khi ứng dụng dùng \`createDurableSubscriber\` hoặc \`createSharedDurableConsumer\`, broker có thể quản lý subscription queue theo quy tắc định danh nội bộ của client và phiên bản. Không đoán tên queue nội bộ chỉ từ tên subscription hiển thị.

### 1.2. Tên đích, tên subscription và tên consumer cần tách riêng

Giả sử dịch vụ kho cần nhận sự kiện đơn hàng:

- **Topic/address:** \`orders.events.v1\` — hợp đồng phát sự kiện, do producer và nhiều consumer cùng biết.
- **Durable subscription name:** \`inventory-order-events-v1\` — danh tính của luồng nhận mà nhóm kho sở hữu.
- **JMS client ID:** \`inventory-service-prod\` — thành phần danh tính của subscription không chia sẻ trong mô hình JMS tương ứng.
- **Consumer instance:** \`inventory-worker-03\` — danh tính triển khai tạm thời để theo dõi log/metrics, **không phải** tên destination.

Nếu mỗi lần deploy ứng dụng lại đặt một durable subscription name mới theo tên pod, broker có thể giữ nhiều subscription cũ và backlog tăng theo thời gian. Vì thế **danh tính của durable subscription phải ổn định qua các lần khởi động lại**, trong khi danh tính tiến trình có thể thay đổi.

## 2. Quy tắc đặt tên destination

Một quy ước tên tốt phải đồng thời giúp người đọc xác định **miền nghiệp vụ, mục đích, phạm vi tương thích và loại đối tượng**. Không có một cú pháp bắt buộc cho mọi ActiveMQ deployment; nhóm nên chọn một quy ước rồi kiểm tra tính hợp lệ trên broker và protocol đang dùng.

### 2.1. Một convention dễ áp dụng

Đề xuất cho hệ thống cần nhiều team vận hành:

~~~text
<domain>.<resource>.<purpose>.v<major>
~~~

Ví dụ:

| Tên | Loại dự kiến | Chủ sở hữu | Ý nghĩa |
|---|---|---|---|
| \`billing.payment.commands.v1\` | Queue | Billing | Lệnh yêu cầu xử lý thanh toán |
| \`orders.lifecycle.events.v1\` | Topic | Orders | Sự kiện vòng đời đơn hàng |
| \`inventory.reservation.commands.v1\` | Queue | Inventory | Yêu cầu giữ tồn kho |
| \`shipping.label.jobs.v1\` | Queue | Shipping | Công việc tạo nhãn vận chuyển |
| \`risk.order-review.events.v1\` | Topic | Risk | Sự kiện phục vụ đánh giá rủi ro |

Các thành phần:

- **domain:** bounded context hoặc nhóm nghiệp vụ có trách nhiệm, ví dụ \`billing\`, \`orders\`.
- **resource:** thực thể/luồng chính, ví dụ \`payment\`, \`reservation\`.
- **purpose:** nhóm message, thường là \`commands\`, \`events\`, \`jobs\` hoặc tên sự kiện/tác vụ rõ nghĩa.
- **v<major>:** phiên bản hợp đồng nhận mà producer và consumer phải thống nhất khi có thay đổi không tương thích.

Đây là **quy ước đề xuất**, không phải cú pháp bắt buộc của JMS. Nếu tổ chức đã có cách đặt tên khác, điều quan trọng là có tài liệu và cơ chế kiểm tra nhất quán.

### 2.2. Quy tắc cú pháp nên áp dụng

1. Dùng chữ thường ASCII, chữ số, dấu chấm phân đoạn và dấu gạch nối trong phân đoạn nếu broker/protocol đã được kiểm thử. Ví dụ \`orders.lifecycle.events.v1\`.
2. Tránh khoảng trắng, tiếng Việt có dấu, ký tự điều khiển và cách viết có thể khác nhau về chữ hoa/chữ thường. Broker có thể coi hai tên khác case là hai đích khác nhau.
3. Không đưa **user ID, email, số điện thoại, token, tenant cá nhân** hoặc dữ liệu nhạy cảm vào tên destination. Tên thường lộ trong log, dashboard, metric labels và cấu hình.
4. Tránh ký tự **wildcard** trong tên tĩnh. Classic có cú pháp wildcard destination với \`*\` và \`>\`; Artemis sử dụng ký tự wildcard trong address matching, phổ biến là \`*\` và \`#\` với phân tách dấu chấm. Ký tự hợp lệ và cách diễn giải phụ thuộc cấu hình.
5. Không dùng những prefix/reserved namespace dành riêng cho thành phần quản trị, advisory, DLQ, hệ thống hoặc mapping nội bộ của phiên bản đang chạy. Quy ước nên quy định rõ những vùng tên này.
6. Giới hạn độ dài tên ở mức mà công cụ triển khai, metric backend và ứng dụng quản trị đều xử lý được. Không giả định có một giới hạn ký tự thống nhất cho Classic, Artemis, tất cả protocol và mọi hệ thống giám sát.
7. Không nhúng địa chỉ host, port, node broker hoặc tên pod vào destination. Địa chỉ kết nối thuộc cấu hình triển khai; định danh luồng nghiệp vụ nên sống lâu hơn một máy chủ.

**Lưu ý quan trọng:** dấu chấm làm tên dễ đọc nhưng cũng có thể là **ranh giới wildcard** trong routing/authorization policy. Vì vậy kiểm tra ACL với cả tên cụ thể và các mẫu \`orders.#\` hoặc \`orders.>\` (tùy sản phẩm), nhất là trước khi cho phép auto-create.

### 2.3. Có nên đặt môi trường vào tên?

Nếu **dev, staging và production dùng broker hoặc namespace cô lập**, có thể giữ cùng tên hợp đồng \`orders.lifecycle.events.v1\` ở mỗi môi trường, vì phần môi trường đã do kết nối/broker quản lý.

Nếu nhiều môi trường **bắt buộc dùng chung một broker**, cần phân vùng tường minh, ví dụ:

~~~text
dev.orders.lifecycle.events.v1
staging.orders.lifecycle.events.v1
prod.orders.lifecycle.events.v1
~~~

Tuy nhiên việc dùng chung broker phải đi kèm ACL, hạn mức, tài nguyên và quy trình vận hành tách biệt. **Tiền tố \`prod.\` tự nó không tạo cô lập bảo mật.** Mỗi môi trường cần kiểm tra queue/address/subscription, không chỉ tên producer.

### 2.4. Không biến tên destination thành payload

Ví dụ không nên tạo hàng ngàn queue theo từng đơn:

~~~text
payment.commands.OD-10010001
payment.commands.OD-10010002
payment.commands.OD-10010003
...
~~~

Cách này gây **destination explosion**: tăng số queue, bindings, metric labels, ACL và chi phí dọn dẹp. Thay vào đó dùng một queue hợp đồng:

~~~text
payment.commands.v1
~~~

và truyền \`orderId\`, \`eventId\`, \`tenantId\`, \`traceId\` trong payload hoặc message property thích hợp. Chỉ tạo queue theo tenant/customer nếu đây là yêu cầu **cô lập thực sự** được thiết kế và có quota, owner, TTL, automation thu hồi.

## 3. Một destination phải có “hồ sơ” gì?

Chỉ một tên queue là chưa đủ để hai team tích hợp. Cần lưu **destination catalog** như một hợp đồng có thể review và triển khai bằng tự động hóa.

| Trường | Tại sao cần |
|---|---|
| **name, kind** | Tên chính xác và loại queue/topic |
| **broker/product/environment** | Phân biệt Classic/Artemis, phạm vi và nơi tạo |
| **address, routingType, queueName** | Bắt buộc diễn tả rõ khi dùng Artemis |
| **owner, producer(s), consumer group(s)** | Xác định quyền thay đổi và người xử lý sự cố |
| **durability, subscription identity** | Xác định backlog còn tồn tại khi consumer offline |
| **contract/schema version** | Mức tương thích của message; quy tắc nâng cấp |
| **ACL, auto-create policy** | Ai có quyền send, consume, create, delete |
| **redelivery/DLQ/expiry/retention** | Điều gì xảy ra khi lỗi hoặc quá hạn |
| **resource limits, alerts, SLO** | Ngăn queue tăng vô hạn và phát hiện tắc nghẽn |
| **lifecycle state, deprecation date** | Xác định đích đang dùng hay chờ thu hồi |

Ví dụ file **mô tả nghiệp vụ**, không phải cấu hình broker trực tiếp:

~~~yaml
# destination-catalog.yaml: định dạng do dự án tự quy định
environment: production
product: activemq-artemis
destinations:
  - name: billing.payment.commands.v1
    kind: queue
    address: billing.payment.commands.v1
    routingType: ANYCAST
    queueName: billing.payment.commands.v1
    owner: team-billing
    producers: [order-api]
    consumers: [payment-worker]
    durable: true
    autoCreate: false
    dlq: billing.payment.dlq
    maxDeliveryAttempts: 5
    sla:
      maxPendingAgeSeconds: 120
    state: ACTIVE

  - name: orders.lifecycle.events.v1
    kind: topic
    address: orders.lifecycle.events.v1
    routingType: MULTICAST
    owner: team-orders
    producers: [order-service]
    subscribers:
      - owner: team-inventory
        subscription: inventory-order-events-v1
        mode: durable
      - owner: team-notification
        subscription: notification-order-events-v1
        mode: durable
    state: ACTIVE
~~~

Không gửi file này trực tiếp cho Artemis rồi kỳ vọng broker tự hiểu. Nó là **nguồn sự thật ở cấp nhóm phát triển**; automation sẽ chuyển thành broker configuration, lệnh quản trị hoặc API thích hợp cho sản phẩm và phiên bản. Nếu deploy thay đổi mà catalog chưa cập nhật, cần coi đó là **configuration drift**.

## 4. “Tạo trước” nghĩa là gì và vì sao cần?

**Pre-provisioning** là tạo/khai báo trước destination trên broker, thiết lập routing, durability, ACL và policy rồi **xác minh trạng thái thực** trước khi producer/consumer của phiên bản mới chạy.

~~~mermaid
flowchart LR
    C["Destination catalog<br/>được review"] --> P["Provision broker<br/>và ACL"]
    P --> V["Verify address / queue<br/>routing / permission"]
    V --> D["Deploy consumer<br/>subscription ổn định"]
    D --> U["Cho phép producer gửi"]
    U --> M["Giám sát backlog<br/>và lỗi"]
~~~

Trình tự **consumer trước producer** thường giảm cửa sổ message tồn đọng khi giới thiệu luồng mới. Nhưng không phải mọi hệ thống đều bắt buộc consumer đang online trước khi gửi: với queue/durable subscription được tạo sẵn và lưu trữ đúng policy, broker có thể giữ message trong thời gian consumer offline.

### 4.1. Các lựa chọn tạo destination

| Cách tạo | Khi nào hợp lý | Rủi ro cần kiểm soát |
|---|---|---|
| **Khai báo tĩnh** trong broker config | Queue/topic quan trọng, ít thay đổi, có review/rollout | Có thể cần reload/restart tùy broker và phương pháp triển khai |
| **Provision bằng management API/JMX/CLI** | Hạ tầng tự động tạo trước khi deploy | Cần idempotent, kiểm tra drift, lưu audit và quản lý quyền admin |
| **Auto-create khi app truy cập** | Sandbox, test, môi trường thử nghiệm có kiểm soát | Gõ sai tên tạo queue rác, thiếu ACL/policy, khó theo dõi owner |
| **Temporary destination do JMS tạo** | Reply-to ngắn hạn theo connection | Không dùng cho backlog quan trọng hoặc subscriber offline |

**JMS \`session.createQueue(name)\` và \`session.createTopic(name)\` chỉ tạo đối tượng tham chiếu destination trong ứng dụng**. Chúng không được xem là bước provision server đáng tin cậy. Broker có thể auto-create khi thao tác send/consume tiếp theo diễn ra, nhưng điều này tùy cấu hình và sản phẩm. Không sử dụng hai API đó làm phép kiểm tra rằng queue vật lý đã được tạo đúng.

### 4.2. Lợi ích cụ thể của tạo trước

- Tên sai \`billing.payments.commands.v1\` thay vì \`billing.payment.commands.v1\` bị phát hiện trong deploy/verification.
- ACL đã tồn tại trước khi producer bắt đầu gửi, tránh khả năng user được kết nối nhưng không đủ quyền send.
- DLQ và expiry address/queue có thể kiểm tra trước, tránh đến lúc phát sinh message lỗi mới thấy chưa có nơi tiếp nhận.
- Backlog/retention và quota được áp dụng ngay từ message đầu tiên, hạn chế nguy cơ lưu dữ liệu ngoài ý muốn.
- Chủ sở hữu subscription tạo đúng định danh bền vững trước khi sự kiện bắt đầu phát.
- Có thể ghi lại **change ID, version, người thực hiện và kết quả kiểm chứng** cho mỗi lần thay đổi.

### 4.3. Khi nào vẫn cần auto-create?

Auto-create có thể hữu ích cho môi trường phát triển hoặc các luồng động như subscription do client quản lý. Điều quan trọng là **phân vùng quyền và phạm vi**:

- Môi trường production: nên ưu tiên **pre-provision** cho destination quan trọng; ứng dụng runtime chỉ có quyền cần thiết để gửi/nhận.
- Môi trường sandbox: có thể auto-create trong prefix riêng, kèm quota và chính sách dọn dẹp.
- Với JMS durable subscription: việc tạo subscription có thể dẫn tới broker tạo queue nội bộ, nên quyết định tắt hoàn toàn auto-create phải kiểm tra tương tác với **API subscription** và quyền \`createDurableQueue\` tương ứng ở Artemis.
- Nếu dùng Kubernetes/ephemeral worker, không để mỗi replica có quyền tùy ý tạo queue bền vững và không dùng tên subscription theo pod.

Không có một “mặc định auto-create” chắc chắn cho mọi phiên bản, plugin và cấu hình Classic/Artemis. Khi triển khai, ghi rõ **chính sách thực tế** trong catalog rồi kiểm thử bằng tên chưa tồn tại trên môi trường thử nghiệm.

## 5. Pre-provision trong ActiveMQ Artemis

Artemis tách **address** và **queue**. Muốn thiết lập đích nhận rõ ràng phải xác nhận cả **routing type** và **queue binding**.

### 5.1. Cấu hình tĩnh cho queue nhận lệnh và topic phát sự kiện

Đoạn sau là phần \`<addresses>\` trong \`broker.xml\` Artemis:

~~~xml
<addresses>
    <!-- Một luồng command, nhiều worker cạnh tranh trên cùng queue -->
    <address name="billing.payment.commands.v1">
        <anycast>
            <queue name="billing.payment.commands.v1"
                   durable="true"/>
        </anycast>
    </address>

    <!-- Một event được giữ riêng cho hai nhóm nhận -->
    <address name="orders.lifecycle.events.v1">
        <multicast>
            <queue name="inventory.order-events.v1"
                   durable="true"/>
            <queue name="notification.order-events.v1"
                   durable="true"/>
        </multicast>
    </address>
</addresses>
~~~

Kết quả dự kiến:

~~~text
billing.payment.commands.v1  [address, ANYCAST]
  └── billing.payment.commands.v1       [queue]
        ├── payment-worker-1
        └── payment-worker-2

orders.lifecycle.events.v1   [address, MULTICAST]
  ├── inventory.order-events.v1         [queue]
  └── notification.order-events.v1      [queue]
~~~

**Lưu ý về Topic JMS:** hai multicast queue khai báo tĩnh ở đây tạo **hai luồng nhận vật lý**. Nếu Java client dùng \`Topic\` và \`createDurableSubscriber\`, danh tính subscription và queue mà Artemis quản lý có thể được tạo/ánh xạ khác theo cấu hình, API và phiên bản. Phải chọn rõ một trong hai mô hình:

1. **Quản lý queue tĩnh**: ứng dụng tiêu thụ chính queue đó bằng cơ chế hỗ trợ phù hợp (có thể dùng fully qualified queue name của Artemis khi cần); hoặc
2. **Quản lý JMS durable subscriptions**: khai báo danh tính \`clientId\`/subscription, quyền tạo subscription, chính sách durable và vòng đời unsubscribe.

Không được giả định rằng khai báo queue \`inventory.order-events.v1\` sẽ tự động làm cho một lệnh \`createDurableSubscriber(topic, "inventory-v1")\` dùng đúng queue ấy.

### 5.2. Kiểm soát auto-create và auto-delete ở address settings

Artemis cho phép cấu hình policy theo mẫu tên address, ví dụ một **fragment** trong \`<address-settings>\`:

~~~xml
<address-settings>
    <address-setting match="billing.#">
        <auto-create-addresses>false</auto-create-addresses>
        <auto-create-queues>false</auto-create-queues>
        <auto-delete-addresses>false</auto-delete-addresses>
        <auto-delete-queues>false</auto-delete-queues>
    </address-setting>
</address-settings>
~~~

Ý nghĩa với **prefix billing**: application được kỳ vọng dùng các address/queue đã provision; broker không tự tạo hoặc tự thu hồi chúng qua những cơ chế auto-create/auto-delete chịu ảnh hưởng của policy này.

Cần thận trọng ba điểm:

- \`match="billing.#"\` là **mẫu address** của Artemis theo wildcard syntax hiện hành, không phải tên queue cụ thể; chọn phạm vi chính xác để không tác động luồng khác.
- Các khóa cấu hình và mặc định có thể khác giữa phiên bản; kiểm tra cấu hình hiệu lực sau khi broker khởi động/reload.
- Tắt auto-create queues có thể tác động các JMS durable subscription mới hoặc cơ chế subscription động. Với topic, cần thiết kế **policy và quyền** phù hợp thay vì sao chép cài đặt queue sang mọi address.

Đừng bật \`auto-delete-queues\` chỉ để dọn hàng đợi cũ trong production. Auto-delete liên quan điều kiện consumer và trạng thái queue; cần hiểu rõ loại queue, ngưỡng và phiên bản. Một queue bền vững chứa backlog quan trọng phải được quản lý thu hồi theo quy trình riêng.

### 5.3. Xác minh sau khi provision

Với mỗi đích, dùng console, CLI hoặc management API phù hợp **để đọc trạng thái**, kiểm tra:

- Address tồn tại đúng tên, routing type đúng \`ANYCAST\` hoặc \`MULTICAST\`.
- Queue tồn tại, \`durable\` đúng, thuộc address đúng, filter và max-consumers nếu có đúng yêu cầu.
- User producer chỉ có quyền send cần thiết; user consumer chỉ có quyền consume phù hợp, cùng quyền create subscription nếu kiến trúc yêu cầu.
- DLQ/expiry destination, redelivery policy và giới hạn address đã sẵn sàng.
- Test producer gửi một **message thử riêng** và test consumer nhận/ack trên đúng queue; sau đó xử lý dữ liệu thử theo runbook để không nhầm backlog thật.

Nếu câu lệnh quản trị báo đã tạo thành công nhưng queue ràng buộc sai address, bước provision **chưa đạt**. Tạo thành công và đúng kiến trúc là hai điều kiện khác nhau.

## 6. Pre-provision trong ActiveMQ Classic

Classic sử dụng tên queue/topic trực tiếp hơn ở tầng destination. Có thể khai báo destination tĩnh trong cấu hình broker, hoặc tạo bằng công cụ quản trị/JMX.

Ví dụ **fragment** nằm trong phần cấu hình broker của Classic:

~~~xml
<destinations>
    <queue physicalName="billing.payment.commands.v1"/>
    <topic physicalName="orders.lifecycle.events.v1"/>
</destinations>
~~~

Điểm cần nhớ:

- Khai báo topic trước **không đồng nghĩa** mọi durable subscriber đã được tạo. Mỗi subscriber có danh tính và trạng thái lưu riêng.
- Classic có thể **tự tạo destination theo nhu cầu** trong nhiều cấu hình. Một lỗi đánh máy ở producer hoặc consumer có thể sinh ra destination mới. Khi cần quản trị chặt, phải kiểm tra cơ chế tự tạo, quyền quản trị destination và policy của đúng bản Classic đang chạy.
- **Network of Brokers** và wildcard subscription có thể ảnh hưởng danh mục destination nhìn thấy giữa các broker. Không suy luận rằng queue có cùng tên trên hai broker sẽ tự hợp nhất backlog.
- Những thao tác remove/purge thực hiện qua JMX/admin cần phân biệt rõ **xóa message** và **xóa chính destination**.

Với các nhóm muốn quản lý theo \`configuration as code\`, mẫu trên là một phần đầu vào, nhưng cần quy trình **đưa cấu hình vào broker**, xác minh có hiệu lực và ghi lịch sử thay đổi. Cấu hình ở đĩa chưa được broker load không có giá trị tương đương destination đã tồn tại.

## 7. Ví dụ Java/JMS: tham chiếu tên ổn định không có nghĩa là tạo trước

Ví dụ sau sử dụng JMS 2.x với namespace \`javax.jms\` và client Artemis tương ứng. Nếu hệ thống dùng Jakarta Messaging, chọn client/library tương thích \`jakarta.jms\`, đổi import nhất quán; không trộn hai API.

~~~java
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSContext;
import javax.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public class PaymentCommandPublisher {
    // Tên là hợp đồng giữa producer, broker và consumer.
    private static final String DESTINATION =
        "billing.payment.commands.v1";

    public static void main(String[] args) {
        String url = required("MQ_URL");
        String user = required("MQ_USER");
        String password = required("MQ_PASSWORD");

        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        try (JMSContext context = factory.createContext(
                 user, password, JMSContext.SESSION_TRANSACTED)) {
            // Chỉ tạo Java Destination handle, KHÔNG xác nhận server có queue.
            Queue destination = context.createQueue(DESTINATION);

            context.createProducer()
                .setDeliveryMode(DeliveryMode.PERSISTENT)
                .send(destination,
                      "{\"commandId\":\"cmd-1001\",\"paymentId\":\"pay-42\"}");

            context.commit();
            System.out.println("Committed command to " + DESTINATION);
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return value;
    }
}
~~~

Để chạy cần broker hoạt động, client library đúng phiên bản và biến môi trường tương ứng. Ví dụ không hardcode mật khẩu. Với **policy tắt auto-create** và queue chưa provision, thao tác send/commit có thể thất bại; cần quan sát lỗi thực tế. Với auto-create bật, cùng chương trình có thể gửi thành công vào queue được tạo ngoài ý muốn nếu tên bị viết sai.

Trong production, nên có **bước xác minh provisioning độc lập ở pipeline** bằng management API/CLI. Một thao tác \`createQueue()\` phía JMS **không phải health check cho cấu hình destination**.

### 7.1. Cách phát hiện tên lệch ngay trong CI/CD

Thay vì để từng service tự viết chuỗi tên, có thể dùng constant hoặc configuration key chung, kết hợp bước đối chiếu catalog:

~~~text
Destination catalog đã được review
    ↓
CI: xác minh tên producer và consumer tham chiếu nằm trong catalog
    ↓
Provision: tạo address/queue/topic/subscription + ACL trên broker
    ↓
Verify: đọc lại state thực tế, so với catalog
    ↓
Deploy: consumer → producer
    ↓
Monitor: detect drift và các destination không có owner
~~~

Một bước CI mang tính khái niệm có thể kiểm tra:

~~~text
expected = {
  "billing.payment.commands.v1": { type: "QUEUE", durable: true },
  "orders.lifecycle.events.v1": { type: "TOPIC" }
}

for each referencedDestination:
    assert referencedDestination in expected

for each brokerDestination:
    if brokerDestination not in expected and not allowlistedSystemDestination:
        report as unmanaged destination
~~~

Đoạn trên là **thuật toán minh họa**, không phải mã chạy trực tiếp. Cần loại trừ rõ các internal, temporary, advisory, DLQ và subscription queues do broker quản lý để tránh coi mọi đối tượng nội bộ là lỗi.

## 8. Quản lý danh tính và vòng đời durable subscription

Đối với topic, thay đổi destination **chưa đủ**: cần quản lý ai đang subscribe, danh tính đó có tồn tại khi consumer offline không, và khi nào được hủy.

### 8.1. Durable subscriber trong Java

Ví dụ dùng API JMS 1.1/2.x dạng \`javax.jms\` để thấy rõ \`clientID\`, \`subscriptionName\` và bước nhận:

~~~java
import javax.jms.Connection;
import javax.jms.ConnectionFactory;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Session;
import javax.jms.Topic;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public class InventoryDurableSubscriber {
    private static final String TOPIC = "orders.lifecycle.events.v1";
    private static final String CLIENT_ID = "inventory-service-prod";
    private static final String SUBSCRIPTION = "inventory-order-events-v1";

    public static void main(String[] args) throws Exception {
        String url = required("MQ_URL");
        String user = required("MQ_USER");
        String pass = required("MQ_PASSWORD");

        ConnectionFactory factory = new ActiveMQConnectionFactory(url);
        Connection connection = factory.createConnection(user, pass);
        try {
            // Đặt trước khi sử dụng connection/session.
            connection.setClientID(CLIENT_ID);
            Session session = connection.createSession(
                false, Session.CLIENT_ACKNOWLEDGE);
            try {
                Topic topic = session.createTopic(TOPIC);
                MessageConsumer consumer =
                    session.createDurableSubscriber(topic, SUBSCRIPTION);
                try {
                    connection.start();
                    Message msg = consumer.receive(5000);
                    if (msg != null) {
                        // Ứng dụng thật: xử lý idempotent rồi commit DB.
                        System.out.println("Message ID=" + msg.getJMSMessageID());
                        msg.acknowledge();
                    }
                } finally {
                    consumer.close();
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return value;
    }
}
~~~

Các điều kiện vận hành:

- **Không đổi \`CLIENT_ID\` hoặc \`SUBSCRIPTION\` theo tên pod/restart**; nếu thay đổi, broker có thể coi đó là subscriber mới, còn subscriber cũ tiếp tục giữ backlog.
- Với subscription bền vững **không chia sẻ** theo semantics JMS truyền thống, không mở hai active subscriber đồng thời với cùng danh tính \`clientID\` và \`subscriptionName\`. Nếu cần chia tải, xem xét **shared durable subscription** được phiên bản JMS/provider hỗ trợ, hoặc một queue riêng với nhiều competing consumers.
- **JMS client ID phải duy nhất trong phạm vi áp dụng của provider và cấu hình** đối với các kết nối đồng thời. Nếu nhiều replica cần cùng một subscription, hãy thiết kế cách chia sẻ được hỗ trợ thay vì cấp cùng client ID tùy tiện.
- Tạo \`Topic\` handle không bảo đảm topic/address đã provision; tạo durable subscriber có thể yêu cầu quyền **tạo subscription queue** ở broker.
- Nếu cần thay đổi selector của durable subscription, kiểm tra giới hạn JMS/provider và quy trình hủy/tạo lại; không tự đổi trong lúc còn backlog mà thiếu kế hoạch xử lý.

### 8.2. Unsubscribe khác với disconnect

- **Đóng consumer hoặc connection**: ngừng nhận; durable subscription thông thường vẫn còn, broker tiếp tục giữ message phù hợp.
- **Unsubscribe**: hủy danh tính subscription bền vững; backlog chưa nhận của subscription đó có thể bị loại bỏ theo semantics/provider.
- **Xóa topic/address**: thao tác cấp broker, có thể ảnh hưởng **nhiều subscription**, thường có hậu quả rộng hơn unsubscribe một nhóm.

Trong JMS, sau khi **đảm bảo subscription không còn consumer active** và hoàn tất kế hoạch thu hồi, có thể dùng API:

~~~java
// Ví dụ API, chỉ chạy trong thủ tục thu hồi có phê duyệt,
// trên Session gắn đúng connection/clientID.
session.unsubscribe("inventory-order-events-v1");
~~~

Không đặt lệnh \`unsubscribe\` trong \`finally\` của một consumer production, vì mỗi lần ứng dụng tắt có thể xóa luôn backlog và danh tính subscriber. Với shared durable subscription, yêu cầu định danh và điều kiện unsubscribe được quyết định bởi API/provider tương ứng; phải dùng đúng API và kiểm thử trên broker thực tế.

## 9. Vòng đời chuẩn của một destination

Nên mô tả vòng đời bằng các trạng thái có tiêu chí rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> PROPOSED
    PROPOSED --> APPROVED: review contract / owner / ACL
    APPROVED --> PROVISIONED: provision + readback
    PROVISIONED --> ACTIVE: consumer ready + producer enabled
    ACTIVE --> DEPRECATED: announce migration
    DEPRECATED --> DRAINING: stop new writes
    DRAINING --> RETIRED: verify all pending/in-flight work
    RETIRED --> REMOVED: delete under change control
~~~

Đây là **quy trình quản trị gợi ý**, không phải các trạng thái hệ thống mà Classic/Artemis tự triển khai. Có thể bổ sung \`ROLLBACK\`, \`PAUSED\`, \`ARCHIVED\` theo quy trình tổ chức.

### 9.1. Khi tạo mới

**Trước khi active:**

1. Có **owner** chịu trách nhiệm message contract, consumer và xử lý DLQ.
2. Quyết định queue/topic, routing type, subscription identity, durability và số consumer dự kiến.
3. Chỉ rõ policy về quyền, retry, DLQ, TTL/expiry, retention, backlog limit và cảnh báo.
4. Provision bằng công cụ có **idempotency**: chạy lại cùng một khai báo phải cho kết quả nhất quán, không tạo bản sao khác tên.
5. Readback broker thực tế; test gửi/nhận trên đúng queue/subscription; ghi kết quả vào change record.
6. Triển khai consumer có khả năng xử lý message, rồi mới mở đường gửi của producer nếu phù hợp.

### 9.2. Khi thay đổi thuộc tính

Có thay đổi có thể cập nhật tại chỗ (ví dụ điều chỉnh hạn mức/backoff theo khả năng broker), nhưng cũng có thay đổi cần **tạo destination mới**:

| Thay đổi | Hướng xử lý |
|---|---|
| Tăng ngưỡng cảnh báo hoặc metric metadata | Thường không đổi tên destination |
| Điều chỉnh retry/TTL theo policy nhưng vẫn giữ contract | Review tác động tới message đang chờ; cập nhật có kiểm soát |
| Đổi tên destination | Coi là đổi địa chỉ hợp đồng; chuyển producer/consumer có kế hoạch |
| Chuyển queue sang topic hoặc thay ANYCAST/MULTICAST | **Thay đổi semantics lớn**, thường cần destination mới |
| Đổi schema không tương thích với consumer cũ | Tăng phiên bản hợp đồng hoặc áp dụng chiến lược tương thích |
| Đổi chủ sở hữu, phạm vi bảo mật hoặc tenant isolation | Review ACL, storage và phương án di chuyển dữ liệu |

Không tự động tăng \`v2\` chỉ vì đổi mô tả hoặc thêm một trường optional tương thích. Mục tiêu của version trong tên là giúp phân biệt **hợp đồng không tương thích**; quy tắc chi tiết cần gắn với schema registry hoặc hợp đồng message của nhóm.

### 9.3. Khi ngừng sử dụng

Không xóa queue vì “không thấy consumer online” hoặc “message count đang bằng 0”. Trước khi thu hồi phải kiểm tra **toàn bộ nguồn tạo message và mọi trạng thái chưa hoàn thành**:

- Không còn producer, job scheduler, retry publisher, bridge/federation, batch hoặc luồng failover gửi vào đích cũ.
- Không còn consumer/subscription đang active hoặc có kế hoạch quay lại nhận backlog.
- Pending, delivering/in-flight, scheduled/redelivery và các bản sao liên quan đã được xử lý, di chuyển hoặc chấp nhận loại bỏ theo quyết định rõ ràng.
- DLQ/expiry/replay công cụ không còn tham chiếu tên cũ.
- Đã rà soát các broker trong cluster/network/federation; tên giống nhau không có nghĩa dữ liệu chỉ tồn tại ở một nơi.
- Đã lưu bằng chứng quan sát: timestamp, metric, danh sách producer/consumer, người duyệt và kết quả kiểm chứng.

**Purge message**, **unsubscribe**, **delete queue** và **delete address/topic** là **bốn loại thao tác khác nhau**; đều có thể gây mất dữ liệu nhưng phạm vi khác nhau. Quy trình vận hành phải ghi đúng thao tác dự định.

## 10. Di chuyển từ destination v1 sang v2

Đổi tên destination không làm producer và consumer tự “đổi theo”. Đây là một thay đổi hợp đồng phân tán.

### 10.1. Ví dụ: thay payload lệnh thanh toán

Giả sử \`billing.payment.commands.v1\` chỉ mang \`paymentId\`, trong khi v2 cần thêm \`currency\`, \`amountMinor\` và yêu cầu kiểm tra schema mới.

**Không** xóa v1 rồi tạo v2 trong cùng lúc deploy. Có thể dùng lộ trình:

1. **Đăng ký v2** trong catalog: owner, schema, queue/address, policy, ACL, DLQ, SLO.
2. **Provision v2** và readback. Kiểm tra v2 không tự tạo sai routing type.
3. **Triển khai consumer v2** có khả năng idempotent; giữ consumer v1 xử lý backlog cũ.
4. **Chuyển producer** theo feature flag hoặc rollout để gửi message mới vào v2. Đảm bảo dữ liệu nghiệp vụ gốc vẫn được ghi trước khi publish (ví dụ outbox).
5. **Theo dõi song song** v1/v2: producer error, queue age, in-flight, DLQ, business outcome.
6. **Ngừng ghi vào v1**, kiểm tra mọi đường gửi, sau đó drain v1 tới điều kiện đã thống nhất.
7. **Retire v1**: vô hiệu hóa quyền gửi v1, tắt consumer cũ sau khi đã xác minh, rồi xóa theo thủ tục nếu đủ điều kiện.

~~~mermaid
flowchart LR
    P["Producer"] --> F{"Feature flag / rollout"}
    F -->|Giai đoạn đầu| V1["Queue v1"]
    F -->|Giai đoạn chuyển| V2["Queue v2"]
    V1 --> C1["Consumer v1<br/>drain backlog"]
    V2 --> C2["Consumer v2"]
~~~

Nếu dự án chọn **dual publish** cùng một lệnh lên cả v1 và v2 trong thời gian chuyển đổi, cả hai consumer có thể thực hiện **hai lần cùng nghiệp vụ**. Chỉ dual publish khi đã có cơ chế **dedup/idempotency theo business command ID** và mục tiêu rõ ràng (ví dụ chạy shadow consumer không gây side effect). Với thanh toán, thường an toàn hơn khi **route một yêu cầu nghiệp vụ đến một phiên bản xử lý chính** tại mỗi thời điểm.

### 10.2. Ví dụ: chuyển topic sự kiện

Với topic \`orders.lifecycle.events.v1\` sang \`orders.lifecycle.events.v2\`, nhiều nhóm consumer phải tự cập nhật:

- Mỗi subscriber cần có kế hoạch **đọc v1/v2** và duy trì subscription identity ổn định tương ứng.
- Nếu producer phát song song v1 và v2 để tương thích, consumer nào nhận cả hai có thể thấy **cùng một sự kiện nghiệp vụ** ở hai định dạng.
- Gắn **eventId** xuyên phiên bản và version schema cụ thể; idempotency phải dựa vào danh tính nghiệp vụ, không dựa duy nhất vào \`JMSMessageID\` của hai message phát khác nhau.
- Không unsubscribe durable subscription v1 chỉ vì consumer v2 đã chạy; phải kiểm tra backlog v1 và điều kiện thu hồi.

Trường hợp không có dual publish, cần một chiến lược cutover/bridge rõ ràng để không bỏ lỡ sự kiện trong khoảng các nhóm nâng cấp lệch nhau.

## 11. Destination động, temporary destination và quy trình dọn dẹp

### 11.1. Temporary destination dùng cho request/reply, không thay queue nghiệp vụ

JMS hỗ trợ \`TemporaryQueue\` hoặc \`TemporaryTopic\` để tạo đích tạm, thường dùng làm \`JMSReplyTo\` cho một connection.

~~~java
import javax.jms.Connection;
import javax.jms.ConnectionFactory;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TemporaryQueue;
import javax.jms.TextMessage;

// Đoạn code trong một method đã có ConnectionFactory factory.
Connection connection = factory.createConnection(user, password);
try {
    Session session = connection.createSession(
        false, Session.AUTO_ACKNOWLEDGE);
    try {
        TemporaryQueue replyTo = session.createTemporaryQueue();
        MessageConsumer replies = session.createConsumer(replyTo);
        try {
            Queue requests = session.createQueue("shipping.quote.requests.v1");
            MessageProducer producer = session.createProducer(requests);
            try {
                TextMessage request = session.createTextMessage("quote:OD-1001");
                request.setJMSReplyTo(replyTo);
                request.setJMSCorrelationID("request-1001");

                connection.start();
                producer.send(request);

                Message response = replies.receive(3000);
                if (response == null) {
                    System.out.println("No response within timeout");
                }
            } finally {
                producer.close();
            }
        } finally {
            replies.close();
            replyTo.delete();
        }
    } finally {
        session.close();
    }
} finally {
    connection.close();
}
~~~

Mã minh họa **phía caller**; để có phản hồi cần một responder đọc queue \`shipping.quote.requests.v1\`, gửi vào \`request.getJMSReplyTo()\` và gắn đúng \`JMSCorrelationID\`.

Không dùng temporary queue để nhận job khi client offline. Temporary destination có vòng đời gắn với connection tạo nó (và có quy tắc truy cập riêng); khi connection biến mất, reply có thể không còn đường nhận. \`delete()\` là thao tác chủ động thu hồi; đóng connection cũng làm destination tạm hết vòng đời theo hợp đồng JMS. Ở production phải xử lý timeout/retry và bảo mật \`JMSReplyTo\`.

### 11.2. Auto-delete queue khác với dọn backlog

Ở Artemis, chính sách auto-delete cho queue/address động có thể giúp thu hồi đối tượng không còn sử dụng, nhưng **điều kiện** phụ thuộc loại queue, cấu hình (ví dụ giới hạn thời gian/độ trễ auto-delete) và phiên bản. Với Classic, có thể cấu hình chính sách garbage collection các destination không hoạt động theo policy/version.

Không bật chính sách thu hồi tự động cho **business queue bền vững** khi chưa chứng minh được rằng backlog, các message đang xử lý, scheduled redelivery và consumer offline không bị ảnh hưởng. Nếu cần tự dọn đích động, hãy giới hạn trong **namespace riêng** và có quy tắc:

- Destination phải có owner hoặc trường hợp sử dụng đã khai báo;
- Không có subscription cần giữ khi offline;
- Có TTL/retention và quota rõ ràng;
- Có log audit thao tác tạo/xóa;
- Có cơ chế cảnh báo trước khi vượt số lượng destination dự kiến.

### 11.3. Quy trình thu hồi an toàn cho queue business

Một mẫu runbook có thể là:

~~~text
1. Freeze new writes: disable producer routes + revoke send permission.
2. Confirm no hidden producers: batch, retry, bridge, scheduler, failover.
3. Drain: pending=0, delivering=0, scheduled/redelivery=0
   (đối chiếu ý nghĩa counter theo broker/version).
4. Resolve DLQ/replay references; lưu kết quả xử lý backlog.
5. Review durable subscribers, consumer deployment và các node liên quan.
6. Snapshot/backup nếu policy yêu cầu; ghi rõ khả năng phục hồi.
7. Execute targeted delete bằng công cụ quản trị phù hợp.
8. Readback: destination thật sự đã biến mất; không auto-create trở lại.
9. Monitor: application errors, unexpected sends, orphan subscriptions.
~~~

Điều kiện \`pending=0\` là **cần nhưng chưa đủ**; message có thể đang in-flight hoặc đã được chuyển sang DLQ. Ngay cả khi các counter bằng 0 tại một thời điểm, phải **chặn nguồn gửi mới trước**, nếu không có thể phát sinh cuộc đua giữa kiểm tra và xóa.

## 12. Phân quyền và chống destination rác

Một quy tắc đặt tên chỉ có giá trị khi broker **thực thi** được nó qua provisioning và ACL.

### 12.1. Ma trận quyền tham khảo

| Vai trò | Send | Consume | Create destination/subscription | Delete | Manage |
|---|---:|---:|---:|---:|---:|
| Producer của \`billing.payment.commands.v1\` | Có, đúng queue | Không | Không | Không | Không |
| Payment worker | Không, nếu không cần | Có, đúng queue | Không | Không | Không |
| Inventory subscriber | Không, nếu không cần | Có, trên subscription được chỉ định | Chỉ khi cơ chế đăng ký JMS yêu cầu và đã cho phép | Không tự do xóa | Không |
| Provisioning service | Theo thủ tục | Theo thủ tục | Có, theo prefix/catalog | Có, theo change control | Có giới hạn |
| Broker administrator | Theo chính sách vận hành | Theo chính sách | Có | Có | Có |

Cột trên là **chính sách đề xuất**; tên permission thực tế khác nhau. Artemis có quyền theo address như \`send\`, \`consume\`, \`createDurableQueue\`, \`deleteDurableQueue\`, \`createNonDurableQueue\`, \`deleteNonDurableQueue\`, \`manage\` (tùy phiên bản). Classic thường quản lý authorization theo \`read\`, \`write\`, \`admin\` và destination patterns. Cần áp dụng đúng ACL của **sản phẩm đang triển khai**.

### 12.2. Bốn kiểu lỗi phổ biến

| Sai sót | Hậu quả | Cách phát hiện/phòng ngừa |
|---|---|---|
| Producer gõ sai một ký tự, auto-create đang bật | Tạo queue mới; consumer cũ không thấy message | Catalog validator; không cấp quyền tạo queue tùy tiện |
| Durable subscriber dùng tên theo pod | Mỗi lần rollout tạo subscription mới, tăng backlog | Subscription ID ổn định và audit orphan subscription |
| Xóa queue khi consumer count bằng 0 | Mất message dành cho consumer đang offline | Kiểm tra backlog, trạng thái durable và change approval |
| Đổi queue sang topic nhưng giữ nguyên tên | Thay đổi semantics, phát sai hoặc mất nhánh nhận | Yêu cầu type/routingType là trường bắt buộc trong catalog |

### 12.3. Giám sát drift và destination không có owner

Ít nhất mỗi ngày hoặc trong pipeline release, có thể **so danh sách broker thực tế với catalog**:

~~~text
Declared: billing.payment.commands.v1 (ANYCAST, durable)
Actual:   billing.payments.commands.v1 (ANYCAST, durable)
Result:   DRIFT: declared queue missing + unexpected queue present
Action:   stop rollout; điều tra producer/consumer nào dùng tên sai
~~~

Cần phân loại:

- **Declared but missing:** chưa provision, xóa nhầm hoặc sai broker.
- **Unexpected static destination:** không có owner, có thể do tự tạo/tài khoản có quyền rộng.
- **Subscription orphaned:** durable subscription không còn consumer/owner nhưng vẫn giữ message.
- **Policy mismatch:** route, durability, DLQ, auto-create, TTL hoặc ACL khác catalog.
- **Duplicate naming across environments:** ứng dụng dev đang gửi vào queue production do endpoint/credential sai.

Không xóa tự động mọi đích “không có trong catalog”: nhiều broker có destination hệ thống, advisory, DLQ và các subscription queue hợp lệ do provider quản lý. Cần có allowlist và cách nhận diện theo **broker version/protocol** trước khi thực thi dọn dẹp.

## 13. Bài thực hành có tiêu chí kiểm chứng

### Lab A — Phát hiện auto-create do typo

**Thiết lập:** trong sandbox Artemis, tạo trước \`billing.payment.commands.v1\` với ANYCAST; cấu hình cho phép hoặc không cho phép auto-create theo hai lượt thử.

1. Dùng producer gửi thử vào \`billing.payment.commands.v1\`.
2. Đổi một chữ thành \`billing.payments.commands.v1\`.
3. Khi auto-create bật, xem có address/queue mới không và routing type thực tế là gì.
4. Khi tắt auto-create cho prefix đó, quan sát lỗi ở send/commit theo client/protocol và xác nhận queue lạ không tồn tại.

**Kết quả cần giải thích:** tại sao \`createQueue(name)\` trong Java không phát hiện typo? Cần bước nào trong pipeline để phát hiện trước deploy?

### Lab B — Topic có hai nhóm nhận và một nhóm offline

**Thiết lập:** \`orders.lifecycle.events.v1\` MULTICAST và hai queue riêng \`inventory.order-events.v1\`, \`notification.order-events.v1\`, hoặc hai durable subscription JMS với định danh ổn định.

1. Dừng consumer inventory nhưng giữ luồng nhận durable của nó đã được tạo đúng.
2. Gửi ba sự kiện \`OrderCreated\`.
3. Consumer notification nhận và ack.
4. Khởi động inventory, kiểm tra ba sự kiện còn chờ theo queue/subscription tương ứng.
5. So sánh metric pending/delivering của từng luồng nhận.

**Kết quả cần giải thích:** vì sao đã ack ở notification mà inventory vẫn còn message? Và nếu dùng non-durable subscription chưa online thì điều gì thay đổi?

### Lab C — Rollout v2 không làm mất việc cũ

**Thiết lập:** queue \`billing.payment.commands.v1\` đã có backlog, muốn chuyển sang v2 có schema khác.

1. Provision queue v2 và consumer v2 trước.
2. Bật feature flag chuyển **một phần lưu lượng mới** sang v2, theo dõi metric cả hai bên.
3. Chuyển hết producer sang v2 sau khi đã đánh giá an toàn.
4. Tiếp tục consumer v1 đến khi **pending, in-flight, scheduled** và những đường retry liên quan được giải quyết.
5. Thu thập bằng chứng trước khi retire v1; không cần thực sự xóa trên môi trường dùng chung khi thực hành.

**Kết quả cần giải thích:** tại sao chỉ thấy \`pending=0\` chưa đủ để xóa v1? Điều gì xảy ra nếu một batch cũ còn gửi vào v1 sau ngày cutover?

### Lab D — Dọn orphan durable subscription

**Thiết lập:** tạo một durable subscription thử nghiệm trong sandbox, sau đó tắt consumer mà **không unsubscribe**.

1. Gửi message mới vào topic, kiểm tra backlog của subscription thử nghiệm.
2. Khởi động lại client với **cùng danh tính**, kiểm tra nó vẫn nhận được message.
3. Thử đổi subscription ID, quan sát một subscription mới xuất hiện trong management view.
4. Quay lại ID cũ để xử lý backlog và thực hiện quy trình retire có kiểm soát.
5. Chỉ unsubscribe tên thử nghiệm sau khi chắc chắn không còn message cần giữ và không có consumer active.

**Kết quả cần giải thích:** tại sao subscription name là một phần của vòng đời tài nguyên, không phải chuỗi đặt ngẫu nhiên khi khởi động ứng dụng?

## 14. Checklist đưa một destination vào production

- [ ] Tên đúng convention, ổn định qua các lần deploy, không chứa dữ liệu nhạy cảm hoặc wildcard ngoài ý muốn.
- [ ] Catalog ghi rõ **owner**, producer, consumer/subscriber, loại đích và contract/schema version.
- [ ] Đã tách rõ **Classic queue/topic** hoặc **Artemis address + routing type + queue**.
- [ ] Queue/topic được provision trước, hoặc chính sách auto-create có giới hạn và lý do rõ ràng.
- [ ] Với topic, danh tính và chế độ durable/shared subscription được ghi và kiểm tra đúng API/provider.
- [ ] Quyền \`send\`, \`consume\`, \`create\`, \`delete\`, \`manage\` được cấp tối thiểu theo broker đang dùng.
- [ ] Routing, durability, retry, DLQ, expiry, TTL và hạn mức được readback từ broker thực.
- [ ] CI/CD kiểm tra mọi destination được tham chiếu trong ứng dụng có trong catalog và không lệch type.
- [ ] Đã thử typo destination trong sandbox, failover/reconnect khi phù hợp và quan sát counter.
- [ ] Có kế hoạch rollback và migration cho tên/schema phiên bản mới.
- [ ] Điều kiện retire bao gồm ngừng nguồn gửi, drain pending/in-flight/scheduled, xử lý DLQ/replay và xác nhận subscription.
- [ ] Có audit thao tác tạo/xóa, dashboard phát hiện destination không owner và người chịu trách nhiệm khôi phục.

**Quy tắc cốt lõi:** Destination phải được xem như một **tài nguyên có hợp đồng và vòng đời**, không phải một chuỗi tên tùy ý trong source code. Đặt tên nhất quán giúp tránh nhầm lẫn; **pre-provision + readback** giúp phát hiện sai cấu hình trước khi xử lý message thật; **retire có kiểm chứng** giúp bảo toàn những message còn đang chờ, đang xử lý hoặc nằm trong subscription. Khi làm việc với cả ActiveMQ Classic và Artemis, luôn xác minh thao tác trên đúng mô hình destination và đúng phiên bản broker.
