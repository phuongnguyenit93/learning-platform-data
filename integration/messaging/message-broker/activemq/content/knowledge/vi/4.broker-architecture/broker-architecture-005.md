# Quan hệ giữa destination, subscription và vòng đời lưu giữ thông điệp

> **Chương:** Kiến trúc broker  
> **Phạm vi:** Apache ActiveMQ Classic và Apache ActiveMQ Artemis trong giao tiếp bất đồng bộ. Bài này đi từ câu hỏi “message được gửi đến đâu?” tới “ai thực sự có quyền nhận?” và “broker phải giữ message đến lúc nào?”, rồi liên hệ với JMS, acknowledgment, transaction, redelivery, DLQ, cấu hình và vận hành.

## 1. Mục tiêu và tình huống xuyên suốt

Khi kết thúc bài, bạn có thể:

1. Phân biệt **destination**, **subscription**, **consumer**, **queue** và **address**, nhất là khi chuyển từ ActiveMQ Classic sang Artemis.
2. Giải thích vì sao một message trên topic có thể được nhiều dịch vụ nhận, nhưng hai consumer trên một queue thường chia nhau công việc.
3. Dự đoán thông điệp nào còn được lưu khi consumer chưa kết nối, mất kết nối, broker khởi động lại, message hết hạn hoặc subscription bị xóa.
4. Phân biệt **durable subscription**, **durable queue**, **persistent delivery** và **time-to-live (TTL)**.
5. Thiết kế vòng đời thông điệp có acknowledgment, transaction, retry, dead-letter queue (DLQ), expiry và dọn dẹp subscription cũ.
6. Chạy được ví dụ JMS Java và hiểu cách ánh xạ một topic Classic sang address/queue multicast trong Artemis.

Hãy tưởng tượng hệ thống đơn hàng phát sự kiện `OrderCreated(orderId=O-1001)`. Dịch vụ **Billing** phải phát hành hóa đơn, **Email** phải gửi thư, còn nhóm **FraudCheck** cần một worker kiểm tra mỗi đơn. Ba câu hỏi nảy sinh:

- Nếu Billing tắt trong 15 phút, các sự kiện được gửi trong thời gian đó có còn chờ nó không?
- Nếu Billing có ba instance, mỗi instance nhận một bản hay cả ba cùng nhận?
- Nếu Billing đã lưu hóa đơn vào database nhưng chết trước khi xác nhận message, điều gì xảy ra?

Câu trả lời đến từ **destination + subscription + chính sách vòng đời message**, không chỉ từ việc chọn “queue hay topic”.

## 2. Năm khái niệm phải tách bạch

| Khái niệm | Câu hỏi mà nó trả lời | Ví dụ |
|---|---|---|
| **Destination** | Producer gửi đến địa chỉ logic nào? | JMS queue `orders.work`, JMS topic `orders.created` |
| **Subscription** | Nhóm người nhận nào đăng ký nhận message từ topic? | `billing-orders`, `email-orders` |
| **Queue** | Message đang chờ giao, đã giao nhưng chưa ACK, hay đã hoàn tất cho nhóm nào? | Queue công việc `orders.work`; queue subscription `billing.orders.created` trong Artemis |
| **Consumer** | Tiến trình/phiên kết nối nào đang lấy message? | Billing worker 1, 2, 3 |
| **Retention / vòng đời lưu giữ** | Message tồn tại tới khi nào, trên bộ nhớ hay đĩa, và rời khỏi luồng bằng cách nào? | Được ACK, hết TTL, chuyển DLQ, bị purge hoặc đích bị xóa |

**Destination là tên giao tiếp logic; subscription là quyền nhận của một đối tượng theo thời gian.** Trong một số triển khai, subscription được thể hiện thành một queue vật lý; ở triển khai khác, broker quản lý nó như trạng thái nội bộ của topic. Đừng giả định “tạo consumer” luôn tương đương với “tạo một nơi lưu giữ bền vững”.

**Consumer và subscription không đồng nhất.** Một subscription bền có thể tồn tại khi không có consumer nào kết nối. Nhiều consumer có thể cùng chia một subscription dạng shared; nhưng nếu mỗi consumer tạo một subscription riêng, mỗi subscription lại có tiến độ nhận message độc lập.

### 2.1. Một sơ đồ đọc theo ba tầng

~~~mermaid
flowchart LR
    P["Producer: Order Service"] --> D["Destination logic: orders.created"]
    D --> S1["Subscription: Billing"]
    D --> S2["Subscription: Email"]
    S1 --> Q1["Backlog của Billing"]
    S2 --> Q2["Backlog của Email"]
    Q1 --> C1["Billing worker A"]
    Q1 --> C2["Billing worker B"]
    Q2 --> C3["Email worker"]
~~~

Điểm then chốt: **fan-out diễn ra giữa các subscription**; **cạnh tranh xử lý diễn ra giữa các consumer trong cùng nhóm nhận**. Billing và Email mỗi bên có thể nhận một bản của cùng sự kiện; Billing worker A và B không nhất thiết cùng nhận một bản.

## 3. Queue destination: nơi tồn tại message theo nhóm công việc

Queue dùng cho lệnh hoặc job cần một trong nhiều worker xử lý. Với JMS queue `orders.work`:

1. Producer gửi message vào queue.
2. Broker xếp message vào backlog, trừ khi có quy tắc từ chối, hết hạn hoặc định tuyến khác.
3. Khi có consumer phù hợp, broker **dispatch** message tới consumer.
4. Message đã dispatch nhưng **chưa ACK/commit** vẫn là trách nhiệm cần theo dõi; chưa thể xem là hoàn thành nghiệp vụ.
5. Sau ACK/commit hợp lệ, broker có thể loại message khỏi backlog của queue và dọn phần lưu trữ khi thích hợp.

~~~mermaid
stateDiagram-v2
    [*] --> Accepted: Producer send được broker chấp nhận
    Accepted --> Ready: Enqueue
    Ready --> InFlight: Dispatch tới consumer
    InFlight --> Removed: ACK hoặc commit
    InFlight --> Ready: Rollback / recover / mất kết nối
    Ready --> Expired: TTL hết hạn
    InFlight --> Expired: Hết hạn theo xử lý của broker
    Ready --> DeadLetter: Chính sách lỗi / giới hạn retry
    InFlight --> DeadLetter: Vượt ngưỡng redelivery
    Removed --> [*]
    Expired --> [*]
    DeadLetter --> [*]
~~~

Sơ đồ biểu diễn **trạng thái logic**. Chi tiết lúc kiểm tra expiration, lúc phản hồi producer, cơ chế flush ra đĩa và cách redelivery chạy khác nhau theo broker, protocol, phiên bản và cấu hình.

**Một message không tự biến thành “đã xử lý” khi broker giao nó ra socket.** Nếu consumer bị crash trước ACK, message có thể được giao lại. Nếu ACK được gửi trước khi database commit, broker có thể xóa message dù nghiệp vụ chưa bền vững.

### 3.1. Ba consumer trên cùng queue

Ví dụ FraudCheck có ba worker đọc `orders.work`. Một message chỉ được giao thành công cho **một worker** trong nhóm, không tạo ba bản sao để cả ba cùng xử lý. Lịch phân phối không bảo đảm luân phiên A–B–C vì còn prefetch, tốc độ xử lý, message group, selector, độ ưu tiên và giao lại.

Nếu toàn bộ consumer tạm dừng, message **có thể tiếp tục nằm trong queue**. Nó có tồn tại qua broker restart hay không còn phụ thuộc delivery mode, cấu hình persistence, transaction và các chính sách xóa/hết hạn; queue không đồng nghĩa “giữ mãi vô hạn”.

## 4. Topic destination: subscriptions quyết định ai có backlog

Topic phù hợp để phát sự kiện cho nhiều nhóm chức năng. Producer gửi một message `OrderCreated` tới JMS topic `orders.created`; broker xem những subscription nào đủ điều kiện tại thời điểm gửi.

### 4.1. Non-durable subscription

Một **non-durable topic subscription** có vòng đời gắn với consumer đang hoạt động, theo semantics JMS:

- Khi subscription đang hoạt động, nó có thể nhận các message phù hợp bộ lọc.
- Khi đóng/mất subscription, broker **không có nghĩa vụ** lưu các message được xuất bản sau đó để phát lại cho subscription này.
- Khi kết nối trở lại với một non-durable subscriber mới, nó **không được nhận bù** toàn bộ sự kiện đã phát lúc không tồn tại subscription.

Ví dụ: dashboard vận hành nhận sự kiện để hiển thị trực tiếp; nếu người dùng đóng trang thì không nhất thiết cần replay các sự kiện đã qua.

**Ngoại lệ thiết kế:** một consumer đọc từ **queue được khai báo sẵn và bền** trong Artemis có thể giữ backlog dù consumer đang offline, ngay cả khi queue đó nằm trên multicast address. Trường hợp này cần phân biệt với việc tạo **JMS non-durable topic subscription** có vòng đời ngắn.

### 4.2. Durable subscription

Một **durable subscription** có danh tính đăng ký ổn định và được broker quản lý qua các lần consumer disconnect. Trong JMS 1.1, danh tính truyền thống thường gồm **client ID + subscription name**; các API JMS mới còn có shared durable subscription theo hợp đồng tương ứng.

Ví dụ:

- Billing đăng ký durable topic subscription mang tên `billing-orders` với client ID `billing-service`.
- Billing dừng hoạt động.
- Producer tiếp tục gửi sự kiện.
- Broker lưu backlog cho subscription đã tồn tại, chịu sự chi phối của TTL, message persistence, tài nguyên và chính sách broker.
- Khi Billing kết nối lại bằng **cùng danh tính subscription**, nó đọc tiếp những message còn hợp lệ.

**Durable không có nghĩa là “lấy được lịch sử trước lúc đăng ký”.** Nếu message `O-1001` đã được publish trước khi `billing-orders` lần đầu được tạo, subscription không tự có một bản lịch sử của message đó.

Durable cũng không có nghĩa là một message được giữ vĩnh viễn: nó có thể được ACK, hết hạn, bị người quản trị xóa, hết tài nguyên hoặc subscription bị hủy.

### 4.3. Shared subscription và nhiều consumer

JMS 2.0 bổ sung khái niệm shared subscription, bao gồm shared durable subscription theo provider hỗ trợ. Nhiều consumer có thể cùng khai thác **một subscription**; một message cho subscription đó được một consumer trong nhóm xử lý. Đây là mô hình khác với việc mỗi instance dùng **subscription name khác nhau** và vô tình khiến mỗi instance nhận bản sao riêng.

Trong Classic 5.x hoặc các client dùng API JMS 1.1 cũ, không mặc định có các shared-subscription API và semantics giống một Artemis Jakarta JMS client. Cần kiểm tra chính xác **broker version + API version + client library** thay vì suy từ chữ “durable”.

## 5. Ánh xạ Classic và Artemis: giống nghiệp vụ, khác cấu trúc

### 5.1. ActiveMQ Classic: queue/topic là mô hình giao tiếp nổi bật

Classic quản lý các destination và subscription theo mô hình JMS truyền thống:

- JMS queue có backlog của chính queue; nhiều consumer cạnh tranh.
- JMS topic phân phối tới các subscription.
- Durable topic subscription có trạng thái nhận riêng, kể cả khi subscriber tạm thời không kết nối.
- Classic có cơ chế **Virtual Topic** để publish như topic, nhưng mỗi nhóm xử lý thông qua một queue riêng theo quy ước cấu hình.

Ví dụ Classic Virtual Topics thường dùng:

~~~text
Producer gửi tới:
  topic  = VirtualTopic.OrderCreated

Các nhóm tiêu thụ đọc:
  queue  = Consumer.Billing.VirtualTopic.OrderCreated
  queue  = Consumer.Email.VirtualTopic.OrderCreated

Mỗi queue có backlog và nhiều competing consumers của riêng nó.
~~~

Quy ước `Consumer.<group>.VirtualTopic.<name>` là phổ biến trong Classic, nhưng cách tạo destination, matching và các tùy chọn Virtual Topic phải được xác nhận trên broker thực tế. Không giả định tạo queue **sau** khi event đã phát sẽ tự tái dựng được lịch sử trước đó.

### 5.2. Artemis: address nhận message, queue giữ message

Artemis sử dụng hai khái niệm lõi:

- **Address**: nơi producer định tuyến message tới.
- **Queue**: nơi message được lưu và consumer lấy ra.
- **Routing type**: quyết định cách message được gửi tới các queue thuộc address.

Với **anycast**, broker chọn một queue anycast phù hợp để nhận message. Với **multicast**, broker định tuyến message tới **mỗi queue multicast phù hợp** trên address. Từ đó, mỗi queue subscription có backlog và consumer độc lập.

~~~mermaid
flowchart TB
    P["JMS Topic producer"] --> A["Artemis address: orders.created"]
    A -->|multicast| QB["Durable queue: billing.orders.created"]
    A -->|multicast| QE["Durable queue: email.orders.created"]
    QB --> B1["Billing worker 1"]
    QB --> B2["Billing worker 2"]
    QE --> E["Email worker"]
~~~

Đối với Artemis, JMS topic thường được ánh xạ sang **multicast address** và subscription được thể hiện bằng queue. Một **explicit durable queue** dưới multicast address có thể tồn tại khi chưa có consumer nào từng mở kết nối, vì queue đã được cấu hình trước. Ngược lại, JMS topic subscription tạo động có vòng đời do quy tắc subscription và auto-create/auto-delete điều khiển.

**FQQN** (Fully Qualified Queue Name) thường viết `address::queue` để định danh chính xác một queue của một address, ví dụ `orders.created::billing.orders.created`. Đây là cú pháp mở rộng của Artemis; không xem là cú pháp JMS chuẩn cho mọi provider.

### 5.3. Queue, topic, subscription tương ứng thế nào?

| Nhu cầu | Classic | Artemis | Backlog thuộc về |
|---|---|---|---|
| Một nhóm worker xử lý job | JMS queue `orders.work` | Address `orders.work` + queue anycast | Queue công việc |
| Billing và Email đều nhận event | JMS topic + hai subscriptions | Address multicast + hai subscription queues | Mỗi subscription / queue |
| Hai worker trong cùng nhóm Billing | Cơ chế shared subscription phù hợp hoặc Virtual Topic queue với competing consumers | Hai consumer trên cùng durable queue Billing | Một backlog chung của Billing |
| Billing không kết nối vẫn cần nhận sau | Durable topic subscription đã đăng ký; hoặc queue Virtual Topic đã tồn tại | Durable queue/subscription đã tồn tại | Tồn tại qua thời gian consumer offline, nếu message chưa hết hạn/xóa |
| Xóa hẳn quyền nhận của Billing | Unsubscribe durable subscription / xóa queue Virtual Topic đúng quy trình | Unsubscribe hoặc xóa queue tương ứng | Backlog chưa ACK có thể bị loại bỏ |

Điều đáng nhớ nhất khi migration là **tên topic đơn thuần không mô tả đầy đủ các nhóm được giữ backlog**. Phải kiểm kê từng durable subscription hoặc queue nhóm nhận.

## 6. Bốn trục “durable” và “retention” thường bị nhầm

Trong thực tế, một message có thể được mô tả đồng thời bằng bốn thuộc tính khác nhau:

| Trục | Được cấu hình ở đâu? | Bảo đảm hoặc ảnh hưởng gì? | Không bảo đảm điều gì? |
|---|---|---|---|
| **Durable subscription** | Khai báo subscription/topic consumer | Danh tính và backlog subscription tồn tại qua disconnect | Không tự lưu event trước lúc tạo subscription |
| **Durable queue** | Cấu hình queue trong broker | Tài nguyên queue được bảo tồn qua chu kỳ vận hành phù hợp | Không biến message NON_PERSISTENT thành dữ liệu chắc chắn còn sau crash |
| **PERSISTENT delivery** | Producer/JMS delivery mode | Broker dùng chính sách lưu bền cho message được chấp nhận | Không bảo đảm business transaction ở database đã thành công |
| **TTL/expiration** | Producer hoặc chính sách broker | Xác định lúc message hết hiệu lực và không còn phải deliver theo đường thông thường | Không phải là cơ chế redelivery, và TTL bằng 0 không nghĩa là “an toàn vĩnh viễn” |

### 6.1. Persistent vs non-persistent

JMS có hai delivery mode chính:

- `DeliveryMode.PERSISTENT`: producer yêu cầu broker xử lý message với semantics lưu bền của JMS. Trong điều kiện broker cấu hình đúng và đã xác nhận message thành công, đây là lựa chọn phổ biến cho dữ liệu nghiệp vụ cần tồn tại qua lỗi broker.
- `DeliveryMode.NON_PERSISTENT`: tối ưu các trường hợp chấp nhận mất message khi broker thất bại; đừng kỳ vọng backlog vẫn còn sau restart.

Trong thực tế, cơ chế journal, transaction commit, sync-to-disk, replication và filesystem ảnh hưởng ranh giới bảo đảm. **Không diễn giải PERSISTENT thành “database downstream chắc chắn đã xử lý đúng một lần”.**

### 6.2. TTL/expiration

Producer có thể đặt TTL; JMS tính expiration time dựa trên thời điểm gửi và TTL theo hợp đồng API. TTL bằng `0` thường thể hiện **không có giới hạn expiration do producer đặt**.

Một message tới hạn có thể:

- được loại khỏi queue/subscription theo cơ chế expiry;
- được đưa tới **expiry address** riêng nếu broker hỗ trợ và đã cấu hình;
- không còn được deliver như message đang hợp lệ.

Nếu TTL của `OrderCreated` là 30 phút và Billing ngừng 45 phút, durable subscription **không bắt broker phát một message đã hết hạn**. Điều này cho thấy “durable subscriber” và “giữ đủ lâu để nghiệp vụ xử lý” là hai yêu cầu riêng.

Hết hạn do **TTL** khác với thất bại do **poison message**: message lỗi nhiều lần thường đi DLQ; message quá hạn có thể đi expiry queue hoặc bị discard theo chính sách. Không trộn hai luồng điều tra.

### 6.3. Retention theo người nhận, không theo producer

Nếu publish một message tới ba subscription durable hợp lệ, có thể tồn tại ba quyền nhận/bản ghi backlog logic độc lập. Billing ACK xong không có nghĩa Email và Analytics đã ACK. Mỗi subscription tiến triển theo tốc độ riêng.

Một subscription tiêu thụ rất chậm có thể làm tăng không gian lưu, dù các subscription khác theo kịp. Vì thế, retention phải được quan sát **theo từng queue/subscription** chứ không chỉ theo tốc độ publish chung của topic.

## 7. Dòng thời gian: message còn hay mất?

Giả sử topic `orders.created`, publisher gửi bốn message:

~~~text
10:00   Publish M1
10:02   Billing đăng ký durable subscription lần đầu
10:05   Publish M2, Billing đang online
10:07   Billing disconnect bình thường
10:10   Publish M3
10:20   Publish M4
10:30   Billing reconnect cùng client ID + subscription name
~~~

Giả định M1–M4 đều `PERSISTENT`, TTL đủ dài, broker đủ tài nguyên, không có purge/unsubscribe và subscription không có selector loại bỏ chúng:

- **M1:** durable subscription chưa tồn tại lúc publish ⇒ không tự nhận lại M1.
- **M2:** nếu Billing đã nhận và ACK/commit xong ⇒ không còn pending; nếu chưa ACK ⇒ có thể được giao lại.
- **M3, M4:** subscription đã tồn tại khi Billing offline ⇒ thường được lưu để giao khi Billing trở lại.
- Nếu Billing reconnect dưới **subscription name khác**, broker xem đó là một subscription khác; không mặc định đọc được backlog của subscription cũ.

### 7.1. Ma trận hành vi

| Tình huống khi publish | Queue thường | Non-durable topic subscription | Durable topic subscription đã tồn tại |
|---|---|---|---|
| Consumer đang online | Message có thể dispatch, cần ACK/commit | Nhận khi subscription đang active và phù hợp | Nhận khi active và phù hợp |
| Không có consumer online | Queue giữ message hợp lệ theo chính sách | Không tích backlog cho subscription không còn active | Có thể giữ message để giao sau |
| Producer gửi **trước** khi subscription được tạo | Queue tồn tại có thể giữ message | Không có subscription để nhận | Không có lịch sử tự phát lại |
| Broker restart khi còn message pending | Phụ thuộc persistent/transaction/store/expiry | Không kỳ vọng subscriber cũ tồn tại chỉ vì từng online | Subscription vẫn được duy trì theo durable semantics; message còn phụ thuộc persistence/expiry |
| ACK/commit thành công | Message rời backlog của queue | Message được coi đã tiêu thụ bởi subscription đang hoạt động | Message rời backlog của subscription đó |
| Message hết TTL | Không còn giao theo luồng thông thường | Tương tự | Tương tự, dù durable |
| Subscription bị unsubscribe / queue bị xóa | Queue bị xóa có thể làm mất backlog | Subscription vốn ngắn hạn | Xóa durable subscription có thể làm mất toàn bộ backlog chưa tiêu thụ |

**Lưu ý:** đối với Artemis, một durable multicast queue khai báo sẵn có thể giữ thông điệp từ lúc queue được tạo ngay cả khi chưa có JMS durable subscriber. Bảng mô tả **JMS topic subscription** nhằm làm rõ semantics API.

### 7.2. Kiểm thử broker restart cho đúng

Để chứng minh khả năng lưu giữ, đừng chỉ chạy producer và consumer cùng lúc. Cần:

1. Tạo subscription/queue **trước** khi gửi.
2. Gửi message PERSISTENT, bảo đảm send/transaction commit hoàn tất.
3. Cho consumer offline, kiểm tra backlog.
4. Khởi động lại broker bằng phương pháp được khuyến nghị, dùng storage bền đúng cấu hình.
5. Kết nối lại bằng đúng subscription identity và đọc message.
6. Lặp lại với NON_PERSISTENT, TTL ngắn và unsubscribe để thấy các ranh giới khác nhau.

Trong thí nghiệm thực tế, một broker bị kill đột ngột hoặc ổ đĩa mất dữ liệu tạo ra tình huống khác một lần restart sạch. Hãy ghi chính xác kịch bản.

## 8. Vòng đời tài nguyên subscription khác vòng đời message

Hai đồng hồ chạy đồng thời:

**Đồng hồ thứ nhất — tài nguyên:** destination/queue/subscription được tạo khi nào? Ai sở hữu? Có tự xóa khi consumer cuối cùng disconnect không? Admin có xóa được không?

**Đồng hồ thứ hai — message:** message đi vào backlog khi nào, được ACK khi nào, hết TTL khi nào, được move tới DLQ/expiry khi nào?

Ví dụ sau cho thấy hai đồng hồ không luôn cùng nhịp:

~~~text
09:00  Queue Billing được tạo                         [resource exists]
09:10  Publish M1; Billing offline                    [M1 pending]
09:15  Publish M2; Billing offline                    [M1,M2 pending]
09:20  Consumer Billing kết nối, nhận và ACK M1       [M2 pending]
09:25  Consumer Billing disconnect                    [queue still exists]
10:00  TTL của M2 hết; broker expire M2              [queue empty]
10:30  Queue Billing vẫn tồn tại                      [resource exists]
11:00  Admin xóa queue Billing                        [resource removed]
~~~

Một subscription/queue bền có thể **rỗng nhưng vẫn tồn tại**. Ngược lại, có message đang được dispatch nhưng consumer session biến mất; message cần recovery dù connection resource đã mất.

### 8.1. Đóng consumer có xóa subscription không?

- Đóng JMS **consumer non-durable** thông thường chấm dứt subscription ngắn hạn đó.
- Đóng consumer của **durable subscription** không tự xóa subscription; nó vẫn có thể nhận message tương lai khi consumer offline.
- Gọi `Session.unsubscribe(subscriptionName)`, khi thỏa điều kiện API/provider, sẽ hủy durable subscription, thường đồng nghĩa bỏ backlog chưa nhận.
- Xóa queue bằng console/management có thể loại toàn bộ backlog của queue; đây là hành động quản trị dữ liệu, không tương đương với ACK từng message.

Với Artemis, cần biết queue được **khai báo tĩnh** hay **auto-created**. Các thiết lập auto-delete queues/addresses có thể khiến tài nguyên tạo tự động bị dọn khi không còn consumer, sau độ trễ hoặc khi đạt điều kiện nhất định. Không được dựa vào tên “durable” để bỏ qua việc kiểm tra chính sách auto-delete và lifecycle.

### 8.2. Subscriber “mồ côi”

Một service đổi tên từ `billing-v1` sang `billing-v2` nhưng quên xóa durable subscription cũ. Broker có thể tiếp tục giữ backlog cho `billing-v1` dù không còn consumer nào quay lại, làm tăng disk usage và queue lag.

Biện pháp vận hành:

- Đặt tên subscription dựa trên **vai trò nghiệp vụ ổn định**, không gắn ngẫu nhiên theo process ID mỗi lần chạy.
- Lưu inventory: owner, topic/address, queue, client ID, selector, thời điểm còn dùng và chính sách giữ.
- Khi ngừng một luồng, xác minh owner, drain/replay hoặc lưu trữ nếu cần; chỉ sau đó hủy subscription/queue cũ.
- Cảnh báo cho durable queue có backlog tăng liên tục nhưng consumer count bằng 0.

## 9. Cấu hình Artemis: cho hai subscription có backlog độc lập

Ví dụ phần tử XML bên trong `<core>` của `etc/broker.xml`, giả định phiên bản Artemis đang dùng chấp nhận các phần tử và cú pháp tương ứng:

~~~xml
<addresses>
  <!-- Topic nghiệp vụ: gửi một bản vào mỗi queue multicast đã tạo -->
  <address name="orders.created">
    <multicast>
      <queue name="billing.orders.created" durable="true"/>
      <queue name="email.orders.created" durable="true"/>
    </multicast>
  </address>

  <!-- Job: một queue anycast, nhiều worker cạnh tranh -->
  <address name="orders.work">
    <anycast>
      <queue name="orders.work" durable="true"/>
    </anycast>
  </address>

  <!-- Đích xử lý lỗi và hết hạn được khai báo tách biệt -->
  <address name="orders.DLQ">
    <anycast>
      <queue name="orders.DLQ" durable="true"/>
    </anycast>
  </address>
  <address name="orders.Expiry">
    <anycast>
      <queue name="orders.Expiry" durable="true"/>
    </anycast>
  </address>
</addresses>

<address-settings>
  <address-setting match="orders.created">
    <dead-letter-address>orders.DLQ</dead-letter-address>
    <expiry-address>orders.Expiry</expiry-address>
    <max-delivery-attempts>4</max-delivery-attempts>
    <redelivery-delay>2000</redelivery-delay>
  </address-setting>
</address-settings>
~~~

Ý nghĩa:

1. Producer gửi tới multicast address `orders.created`. **Hai queue đã tồn tại** nên Billing và Email đều có nơi giữ message khi consumer offline.
2. Billing có thể dùng nhiều consumer trên cùng queue `billing.orders.created` mà không nhân bản mỗi message cho từng worker.
3. `orders.work` là queue dành cho tác vụ cạnh tranh; không đi theo multicast.
4. Message vượt chính sách redelivery có thể sang `orders.DLQ`; message hết hạn có thể sang `orders.Expiry`. Quy tắc move, xóa và metadata cần được kiểm chứng theo version.
5. Ví dụ chỉ đặt `address-setting` cho `orders.created`. Nếu muốn chính sách riêng cho `orders.work` hoặc destination khác, cần khai báo thêm chính sách phù hợp.
6. TTL được đặt từ producer trong ví dụ Java bên dưới; durable queue **không ghi đè TTL**.

**Cẩn trọng khi dùng auto-create:** nếu ứng dụng lỡ ghi `order.created` thay vì `orders.created`, broker có thể tự tạo tài nguyên ngoài dự kiến nếu bật auto-create. Production nên quyết định rõ có cho phép tạo tự động hay bắt buộc khai báo trước, kèm quyền hạn riêng.

### 9.1. Vì sao cấu hình multicast cần queue trước thời điểm gửi?

Tại 10:00 nếu chỉ có Billing queue, message multicast sẽ được định tuyến cho Billing. Nếu đến 10:05 mới tạo Email queue, Email không mặc nhiên nhận các message cũ từ 10:00. Durable queue là **hộp thư từ thời điểm tồn tại trở đi**, không phải kho sự kiện bất biến cho các subscriber đăng ký muộn.

Nếu nghiệp vụ yêu cầu replay lịch sử theo ngày/tháng, hãy thiết kế thêm event log, archive hoặc cơ chế replay có quản trị. Message broker queue/topic thông thường **không tự là hệ thống event sourcing có khả năng đọc lại toàn bộ lịch sử**.

### 9.2. Artemis JMS subscription tự tạo khác queue tĩnh

Khi ứng dụng gọi API JMS `createDurableConsumer(topic, subscriptionName)`, Artemis có thể tạo queue nội bộ với tên và routing mapping riêng. Trong ví dụ này ta **chủ động cấu hình** hai queue multicast rồi consumer dùng **FQQN** để đọc queue đích. Hai phương án thể hiện cùng mục đích fan-out theo nhóm nhưng khác cách quản lý vòng đời. Chọn một cách rõ ràng, tránh vô tình tạo thêm subscription thứ ba bên cạnh hai queue tĩnh.

## 10. Ví dụ Java: publish topic Artemis và đọc queue subscription

Ví dụ dùng Jakarta JMS API (`jakarta.jms`) và Artemis Jakarta client, ví dụ dependency Maven `org.apache.activemq:artemis-jakarta-client` ở **phiên bản tương thích** với broker/JDK. Chạy sau khi tạo broker có cấu hình mục 9 và cấp cho user `app` quyền gửi tới address và tiêu thụ queue.

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import jakarta.jms.Topic;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ArtemisSubscriptionsDemo {
    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(
                        "tcp://localhost:61616",
                        "app", "lab-secret"); // Chỉ dùng secret giả lập trong lab

        // Gửi event persistent tới multicast address orders.created.
        try (JMSContext producerContext =
                     factory.createContext(JMSContext.AUTO_ACKNOWLEDGE)) {
            Topic events = producerContext.createTopic("orders.created");

            producerContext.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setTimeToLive(10 * 60_000L) // 10 phút
                    .send(events, "orderId=O-1001");
        }

        // Đọc từ queue của Billing bằng FQQN do Artemis hỗ trợ.
        try (JMSContext consumerContext =
                     factory.createContext(JMSContext.CLIENT_ACKNOWLEDGE)) {
            Queue billingQueue = consumerContext.createQueue(
                    "orders.created::billing.orders.created");
            JMSConsumer consumer = consumerContext.createConsumer(billingQueue);

            Message message = consumer.receive(5_000L);
            if (message == null) {
                System.out.println("Chưa nhận được message");
                return;
            }

            if (!(message instanceof TextMessage)) {
                throw new IllegalStateException("Sai kiểu message");
            }

            String payload = ((TextMessage) message).getText();
            persistInvoiceIdempotently(payload); // Làm xong mới xác nhận
            message.acknowledge();
            System.out.println("Billing đã ACK: " + payload);
        }
    }

    private static void persistInvoiceIdempotently(String payload) {
        // Ví dụ minh họa: production ghi DB với unique eventId/orderId.
        System.out.println("Billing xử lý: " + payload);
    }
}
~~~

Quan sát:

- Email queue `email.orders.created` cũng được lưu một bản nếu đã tồn tại khi gửi, dù chương trình này chỉ tiêu thụ queue của Billing.
- `JMSContext.CLIENT_ACKNOWLEDGE` xác nhận **mọi message đã nhận trong cùng session/context kể từ lần ACK trước** theo JMS; không xem `message.acknowledge()` là ACK độc lập từng message trong một session có nhiều receive.
- Nếu lưu invoice xong rồi crash trước ACK, message có thể được redeliver; `persistInvoiceIdempotently` phải thực sự chống xử lý trùng ở hệ thống thật.
- Nếu consumer khởi động sau quá 10 phút, message có thể đã hết TTL và được chuyển expiry; queue durable không cứu message đã hết hạn.
- `address::queue` là cú pháp Artemis; ứng dụng đa provider cần lớp cấu hình/binding riêng thay vì hard-code khắp mã nguồn.
- Trong ứng dụng chạy lâu dài, framework có thể quản lý connection/context pool, concurrency và exception handling. Demo tạo context ngắn chỉ để thấy rõ ranh giới send và consume.

## 11. Ví dụ Java: JMS durable topic subscription trên Classic

Ví dụ độc lập này minh họa mô hình JMS 1.1 truyền thống, dùng `javax.jms` và Classic `org.apache.activemq:activemq-client` thuộc dòng phiên bản phù hợp. **Không trộn `javax.jms` với `jakarta.jms`** trong cùng ví dụ. Đảm bảo broker Classic và client tương ứng, cấu hình quyền cho user lab.

### 11.1. Đăng ký và tiêu thụ durable subscription

~~~java
import javax.jms.Connection;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.Session;
import javax.jms.TextMessage;
import javax.jms.Topic;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicDurableBilling {
    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            // Client ID phải ổn định và không trùng với connection đồng thời.
            connection.setClientID("billing-service");

            Session session =
                    connection.createSession(false, Session.CLIENT_ACKNOWLEDGE);
            try {
                Topic topic = session.createTopic("orders.created");

                // Tên subscription ổn định qua các lần kết nối.
                MessageConsumer consumer =
                        session.createDurableSubscriber(
                                topic, "billing-orders");
                try {
                    connection.start();
                    Message message = consumer.receive(5_000L);
                    if (message instanceof TextMessage) {
                        String payload = ((TextMessage) message).getText();
                        handleInvoiceIdempotently(payload);
                        message.acknowledge();
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

    private static void handleInvoiceIdempotently(String payload) {
        System.out.println("Billing xử lý: " + payload);
    }
}
~~~

**Vòng đời cần kiểm tra bằng tay:** chạy chương trình lần đầu để tạo subscription; đóng chương trình; gửi message trong lúc không có consumer; chạy lại với **cùng** client ID `billing-service` và subscription name `billing-orders` để nhận message còn pending.

Đóng `MessageConsumer` ở cuối lần chạy **không** tự xóa durable subscription. Nếu thực sự muốn hủy nó, phải đóng consumer trước và dùng API hủy subscription khi đáp ứng điều kiện JMS/provider, chẳng hạn `session.unsubscribe("billing-orders")` trên client ID tương ứng. Hành động này thường loại backlog, vì thế không dùng như thao tác “disconnect tạm thời”.

### 11.2. Producer Classic gửi message PERSISTENT có TTL

~~~java
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.MessageProducer;
import javax.jms.Session;
import javax.jms.Topic;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicEventPublisher {
    public static void main(String[] args) throws Exception {
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        Connection connection =
                factory.createConnection("app", "lab-secret");
        try {
            Session session =
                    connection.createSession(true, Session.SESSION_TRANSACTED);
            try {
                Topic topic = session.createTopic("orders.created");
                MessageProducer producer = session.createProducer(topic);
                try {
                    producer.setDeliveryMode(DeliveryMode.PERSISTENT);
                    producer.setTimeToLive(15 * 60_000L);

                    producer.send(
                            session.createTextMessage("orderId=O-1002"));
                    session.commit(); // Transaction gửi hoàn tất
                } catch (Exception e) {
                    session.rollback();
                    throw e;
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

Trong JMS transacted session, `commit()` là ranh giới hoàn tất transaction gửi của broker. Producer nhận thành công không có nghĩa consumer đã xử lý. Nếu publisher lỗi giữa `send` và `commit`, chưa thể suy ra message đã có mặt trong subscription. Nếu mất kết nối đúng lúc commit mà client không biết kết quả, cần idempotency/event ID để xử lý trường hợp gửi lặp do retry ở tầng ứng dụng.

### 11.3. Ba thí nghiệm với mã Classic

1. **Publish trước khi tạo subscription:** chạy publisher trước lần chạy đầu của `ClassicDurableBilling`. Billing không tự có event quá khứ đó.
2. **Publish lúc subscription offline:** tạo subscription bằng cách chạy consumer một lần; tắt consumer; chạy publisher; mở consumer lại trước TTL 15 phút. Message còn hợp lệ sẽ được giao.
3. **Đổi danh tính:** thay `billing-orders` thành `billing-orders-v2` rồi chạy consumer. Backlog của tên cũ không tự chuyển sang tên mới.

Nếu cả hai broker cùng chạy trên một máy, đổi port hoặc chỉ chạy một broker tại một thời điểm để tránh kết nối nhầm.

## 12. Acknowledgment và transaction thay đổi retention ra sao?

### 12.1. Thời điểm ACK là ranh giới quan trọng

Xét một worker:

~~~text
Receive M1 -> Ghi invoice DB -> ACK M1
~~~

Có bốn khả năng thường gặp:

| Tình huống | Trạng thái trên broker | Hậu quả nghiệp vụ |
|---|---|---|
| Lỗi trước khi ghi DB và trước ACK | Message thường có thể redeliver | Có cơ hội xử lý lại |
| DB commit thành công, crash trước ACK | Broker vẫn có thể xem M1 chưa hoàn tất | Nguy cơ tạo hóa đơn trùng |
| ACK thành công, rồi ghi DB lỗi | Broker có thể đã loại M1 | Nguy cơ mất công việc |
| DB commit thành công và ACK thành công | Message được hoàn tất trong subscription/queue | Luồng bình thường, nhưng không tự chứng minh tính đúng một lần qua mọi lỗi |

JMS session transacted có thể gộp các thao tác send/receive trên **cùng JMS transaction**; `commit()` xác nhận receive và publish tương ứng, `rollback()` cho phép giao lại message đã consume trong transaction. **Local JMS transaction không tự gộp database transaction**. Nếu cần tính nhất quán database–messaging, dùng idempotent consumer, transactional outbox/inbox hoặc cơ chế transaction phân tán được hỗ trợ có kiểm soát.

### 12.2. Prefetch, in-flight và queue depth

Một broker/client có thể chuyển trước nhiều message vào bộ đệm consumer (prefetch). Lúc này:

- Queue metric `messages ready` có thể giảm dù ứng dụng chưa xử lý xong.
- Một số broker/console đếm riêng **delivering/in-flight/unacknowledged**.
- Khi consumer bị ngắt, message in-flight chưa ACK có thể quay lại trạng thái sẵn sàng và được giao lại.
- Prefetch lớn có thể làm một consumer giữ nhiều message trong khi consumer khác ít việc, ảnh hưởng fairness và thứ tự xử lý.

Đừng chỉ dùng queue depth bằng 0 để kết luận “mọi event đã xử lý xong”; cần theo dõi cả unacknowledged, tốc độ ACK, tuổi message và tình trạng downstream.

### 12.3. Redelivery, poison message và DLQ

Nếu Billing luôn thất bại khi parse message, việc rollback lặp vô hạn khiến backlog tăng và gây tải. Broker/client có thể dùng:

- **Redelivery delay/backoff:** khoảng cách giữa các lần thử.
- **Maximum delivery attempts:** giới hạn số lần giao trước xử lý lỗi đặc biệt.
- **DLQ:** đích dành cho message vượt ngưỡng lỗi hoặc bị đánh dấu poison theo chính sách.

Trong Classic, chính sách redelivery có thể nằm ở **ActiveMQ client** kết hợp chính sách dead-letter của broker; trong Artemis, `address-settings` thường quản lý `max-delivery-attempts`, `redelivery-delay` và `dead-letter-address`. Đây là khác biệt cấu hình cần kiểm tra khi migration.

**DLQ không tự giải quyết lỗi nghiệp vụ:** người vận hành cần xem nguyên nhân, sửa dữ liệu/code, xác định message đã xử lý phần nào và replay với khóa idempotency. Đừng replay hàng loạt vào queue chính mà không kiểm soát duplicate.

## 13. Expiry, DLQ, paging và purge khác nhau thế nào?

| Cơ chế | Kích hoạt | Message đi đâu / còn gì? | Mục đích |
|---|---|---|---|
| **ACK/commit** | Consumer hoàn tất theo JMS | Rời backlog của queue/subscription đã ACK | Kết thúc trách nhiệm giao message |
| **Expiration/expiry** | TTL/expiration đến hạn | Có thể bị discard hoặc chuyển expiry address/queue | Loại message quá hạn |
| **DLQ** | Retry vượt ngưỡng hoặc poison policy | Chuyển sang khu xử lý lỗi nếu đã cấu hình | Điều tra và replay message lỗi |
| **Paging** | Address/queue áp lực bộ nhớ theo policy | Message được lưu qua cơ chế paging, chưa đồng nghĩa đã tiêu thụ | Kiểm soát RAM và backlog lớn |
| **Purge** | Thao tác admin/chính sách xóa | Message pending bị xóa khỏi đích | Dọn theo yêu cầu vận hành |
| **Unsubscribe/delete queue** | Hủy subscription/tài nguyên | Có thể xóa luôn backlog chưa nhận | Kết thúc hẳn quyền nhận |
| **Retention/archive bên ngoài** | Chính sách dữ liệu nghiệp vụ | Lưu lịch sử độc lập với broker | Audit, replay lịch sử dài hạn |

**Paging không phải retention policy theo thời gian**: nó giúp broker xử lý backlog lớn bằng disk. **DLQ không phải kho lưu lịch sử chuẩn**: chỉ chứa nhóm message bị lỗi theo chính sách. **Purge không phải ACK**: purge có thể làm mất công việc chưa được consumer xử lý.

Trong Classic, persistent store thường dùng KahaDB; Artemis có journal và paging store của mình. Bộ đệm, index, checkpoint/compaction và việc thu hồi file storage có thể diễn ra muộn hơn ACK logic. Vì thế “message đã được ACK” không buộc disk file thu nhỏ ngay tại thời điểm đó.

## 14. Những tình huống khó cần suy luận đúng

### 14.1. Hai subscription có cùng topic nhưng selector khác nhau

Ví dụ Billing chỉ cần `eventType='OrderCreated'`, Analytics nhận cả `OrderCreated` và `OrderCancelled`. Hai subscription có thể lưu hai tập message khác nhau vì **selector/filter**.

Khi thay selector của durable subscription, không tự cho rằng backlog cũ được bảo toàn hoặc lọc lại một cách giống nhau ở mọi provider. Với JMS truyền thống, việc tái sử dụng cùng subscription identity nhưng thay đổi topic/selector có thể kéo theo thay thế hoặc yêu cầu xóa–tạo subscription tùy quy tắc API/provider. Phải đọc và thử semantics đúng phiên bản trước khi thay đổi trên production.

### 14.2. Consumer reconnect với client ID khác

Trên JMS durable subscription truyền thống, `clientID` là phần của danh tính, không chỉ là nhãn log. Đổi `billing-service` thành `billing-service-7` có thể tạo một subscription khác. Nếu đặt client ID theo UUID ngẫu nhiên mỗi lần boot, broker có thể tích lũy hàng loạt durable subscriptions “mồ côi”.

### 14.3. Một event phát khi chỉ có hai trong ba dịch vụ đăng ký

Nếu Email và Billing đã có durable subscription, còn Analytics chưa đăng ký, event đã gửi chỉ có backlog cho các subscription đủ điều kiện. Khi Analytics đăng ký ngày mai, broker queue/topic thông thường không tự truy hồi event hôm qua.

### 14.4. Một subscriber rất chậm

Nếu producer phát 300 event/giây và Billing ACK 250 event/giây, backlog Billing tăng xấp xỉ 50 message/giây khi tải giữ nguyên. Email vẫn có thể bắt kịp vì backlog tách biệt. Tuy nhiên, disk chung của broker có thể đầy bởi Billing, làm ảnh hưởng publisher và các luồng khác. Thiết kế cần kiểm tra **address-full policy, flow control, disk limit, paging và cảnh báo backlog age**.

### 14.5. Thứ tự event theo đơn hàng

Các consumer có thể nhận và hoàn tất không theo thứ tự toàn cục do cạnh tranh, prefetch, rollback, priority, selector và failover. Nếu nghiệp vụ yêu cầu `OrderCreated` trước `OrderPaid` theo cùng `orderId`, hãy thiết kế message grouping/partitioning hoặc cơ chế sequencing ở tầng ứng dụng, và kiểm thử khi có redelivery.

### 14.6. Dừng broker khi message đang in-flight

Nếu broker/client mất kết nối khi đang trao đổi ACK hoặc commit, cả hai phía có thể tạm thời **không chắc kết quả cuối cùng**. Hệ thống cần coi thao tác xử lý có thể lặp; định danh sự kiện và cơ chế idempotency quan trọng hơn kỳ vọng “broker luôn xử lý đúng một lần”.

## 15. Kiểm thử vòng đời: chạy có kiểm soát và quan sát

Thực hành dưới đây có thể dùng Classic hoặc Artemis, nhưng chuẩn bị đúng destination/subscription tương ứng. Ghi log đủ các mốc: send, commit, receive, business commit, ACK, expiry/DLQ.

### Bài A — Queue không có consumer

1. Tạo queue công việc và tắt toàn bộ consumer.
2. Gửi ba message PERSISTENT có TTL đủ dài, chờ sender xác nhận.
3. Kiểm tra queue depth. Khởi động consumer, ACK hai message, dừng trước message còn lại.
4. Khởi động lại broker rồi mở consumer; đối chiếu message chưa ACK còn tồn tại.

**Quan sát cần ghi:** message nào pending, message nào in-flight, ACK được ghi nhận lúc nào, khác biệt giữa restart sạch và lỗi kết nối bất ngờ.

### Bài B — Durable vs non-durable topic

1. Tạo durable subscription `billing-orders` bằng danh tính ổn định, sau đó cho consumer offline.
2. Không tạo (hoặc đóng) non-durable subscription của dashboard.
3. Publish hai event PERSISTENT trong thời gian offline.
4. Reconnect durable Billing; tạo lại dashboard non-durable.
5. Kiểm tra Billing có backlog và dashboard không tự nhận các event trước lúc nó kết nối.

**Điều kiện:** TTL chưa hết, đã thực sự tạo subscription durable trước lúc publish, subscription không bị xóa và client kết nối đúng broker.

### Bài C — Thêm subscription sau khi publish

1. Khai báo một multicast address với chỉ Billing queue.
2. Publish `M1`.
3. Tạo thêm Email durable queue dưới cùng address.
4. Publish `M2`.
5. Kiểm tra Billing nhận `M1` và `M2`, còn Email thông thường chỉ có `M2`.

**Bài học:** destination đã tồn tại không đồng nghĩa mọi subscription tương lai sẽ được nhận lại lịch sử.

### Bài D — TTL, expiry và DLQ

1. Với subscription durable, gửi một message TTL rất ngắn trong khi consumer offline.
2. Đợi quá TTL rồi kết nối; kiểm tra message không được xử lý như event còn hạn và xem expiry queue nếu đã cấu hình.
3. Gửi một message khác với TTL đủ dài; cho consumer cố ý rollback nhiều lần.
4. Quan sát redelivery count, độ trễ và việc message sang DLQ theo policy.

**Bài học:** expired message và poison message có vòng đời kết thúc khác nhau.

### Bài E — Mất ACK và chống xử lý trùng

1. Consumer nhận `OrderCreated(eventId=E-1001)` và ghi bản ghi hóa đơn có unique key `E-1001`.
2. Cố ý crash sau DB commit nhưng trước ACK.
3. Khởi động consumer lại, quan sát redelivery.
4. Kiểm tra unique key ngăn ghi hóa đơn lần hai; sau đó ACK để thông điệp kết thúc ở broker.

**Bài học:** retention/redelivery của broker cần được kết hợp tính idempotent của nghiệp vụ.

## 16. Checklist thiết kế và vận hành

Khi review một luồng dùng ActiveMQ, hãy ghi đủ các quyết định sau:

| Câu hỏi | Lý do |
|---|---|
| Producer gửi đến tên destination/address nào, protocol nào? | Tránh nhầm logical destination với queue cụ thể |
| Luồng là queue/anycast hay topic/multicast? | Quyết định one-of-many hay fan-out |
| Mỗi nhóm nghiệp vụ có subscription/queue riêng chưa? | Tạo backlog độc lập cho từng nhóm |
| Subscription là durable, shared durable hay non-durable? | Quyết định hành vi khi offline và concurrency |
| Subscription/queue được tạo trước khi publish chưa? | Không đánh mất event đối với nhóm mới |
| Tên client ID, subscription name, queue name có ổn định không? | Tránh subscriptions mồ côi và backlog phân mảnh |
| Delivery mode PERSISTENT hay NON_PERSISTENT? | Xác định yêu cầu tồn tại qua broker failure |
| TTL, expiry address và dead-letter address là gì? | Xác định đường đi khi quá hạn hoặc xử lý lỗi |
| ACK/commit xảy ra trước hay sau business transaction? | Đánh giá mất việc và redelivery |
| Có event ID/idempotency key không? | Chống duplicate khi retry/failover |
| Có chính sách auto-create/auto-delete và quyền xóa queue không? | Giữ đúng vòng đời tài nguyên |
| Có metric pending, delivering, ACK, expiry, DLQ, disk và lag theo subscription không? | Phát hiện subscriber chậm hoặc đã ngừng hoạt động |
| Có runbook drain, replay, unsubscribe và xóa queue an toàn không? | Tránh purge nhầm dữ liệu chưa xử lý |
| Đã kiểm thử broker restart, consumer crash, reconnect và network partition chưa? | Xác nhận bảo đảm thực tế của hệ thống |

## 17. Tổng kết bản chất kiến trúc

**Destination định tuyến nơi message đi vào. Subscription xác định nhóm nào có quyền nhận một bản. Consumer là tiến trình lấy message từ phần backlog tương ứng. Retention là tập hợp các quy tắc quyết định message còn chờ, còn bền, hết hạn hay được xử lý lỗi.**

Trong ActiveMQ Classic, bạn thường tư duy qua **JMS queue/topic và durable subscriptions**, hoặc **Virtual Topics với queue cho từng nhóm**. Trong Artemis, bạn nhìn rõ hơn mô hình **address → routing type → queue**, nơi mỗi queue multicast có backlog độc lập, còn consumer chỉ đọc từ queue đích.

Thiết kế đáng tin cậy cần trả lời được cả hai câu: **“Ai phải nhận?”** và **“Broker phải giữ cho đến khi nào?”**. Nếu chỉ chọn queue/topic mà chưa quyết định danh tính subscription, thời điểm tạo queue, persistence, TTL, ACK, DLQ và idempotency, hệ thống vẫn có thể mất event hoặc xử lý trùng ngay cả khi broker hoạt động bình thường.
