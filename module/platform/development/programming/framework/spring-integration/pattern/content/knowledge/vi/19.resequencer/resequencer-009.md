# Late message sau khi sequence đã release

## 1. Vì sao thông điệp đến muộn là một vấn đề nghiệp vụ?

Trong chương **Resequencer** của module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai Enterprise Integration Patterns bằng **Spring Integration** để xây dựng luồng thông điệp ít phụ thuộc, dễ mở rộng và có thể kiểm thử, theo dõi được. Resequencer giúp sửa **thứ tự nhận message** khi mạng, broker hoặc các nhánh xử lý song song khiến chúng đến không đúng thứ tự ban đầu.

Giả sử một ứng dụng theo dõi tiến trình xuất kho nhận bốn sự kiện cùng một lô:

| Sequence number | Sự kiện | Ý nghĩa |
| ---: | --- | --- |
| 1 | ORDER_ACCEPTED | Đơn hàng được xác nhận |
| 2 | STOCK_RESERVED | Đã giữ đủ hàng |
| 3 | PAYMENT_CONFIRMED | Đã xác nhận thanh toán |
| 4 | SHIPMENT_CREATED | Đã tạo vận đơn |

Nếu các message đi qua nhiều channel, ExecutorChannel, hàng đợi hoặc worker, chúng có thể đến theo thứ tự **2, 4, 1, 3**. Resequencer có thể giữ các message lại và phát ra theo thứ tự sequenceNumber **1, 2, 3, 4**.

Nhưng còn chuyện gì xảy ra khi một message **đến sau khi cả sequence đã được release**?

- Message 2 bị broker gửi lại, dù nhóm 1–4 đã hoàn tất.
- Message 3 từng bị trễ do mạng nhưng vừa tới sau khi group bị timeout và đóng.
- Message 4 được gửi lại nhiều giờ sau, khi metadata group cũ đã được dọn.
- Một workflow khác vô tình dùng lại correlationId của nhóm đã hoàn tất.

Nếu xử lý sai, ứng dụng có thể **tạo nhóm mới từ một message cũ**, phát một sự kiện trùng, chờ một sequence không bao giờ đầy đủ hoặc thực hiện side effect lần thứ hai.

~~~mermaid
flowchart LR
    P["Producer: 1,2,3,4"] --> Q["Broker / network"]
    Q -->|"2,4,1,3"| R["Resequencer"]
    R -->|"1,2,3,4"| D["Downstream handler"]
    Q -.->|"2 (redelivery muộn)"| R
    R -.->|"Late discard / quarantine"| L["Late message policy"]
~~~

**Mục tiêu bài học**

1. Hiểu chính xác thế nào là **late message** sau khi group hoặc một đoạn sequence đã release.
2. Phân biệt message **đến chậm để lấp gap**, **đến lặp**, **đến sau timeout** và **đến sau khi group metadata đã bị xóa**.
3. Hiểu **releasePartialSequences**, **sendPartialResultOnExpiry**, **expireGroupsUponTimeout**, **MessageGroupStore** và **discardChannel**.
4. Giải thích tại sao giữ **empty completed group** giúp nhận diện late arrival, còn xóa quá sớm có thể tạo group mới.
5. Thiết kế retention, recovery, idempotency, error channel và quan sát message đến muộn.
6. Dùng Java DSL cấu hình Resequencer, rồi kiểm thử thứ tự, duplicate, group completion và late arrival.

## 2. Resequencer khác Aggregator ở đâu?

**Resequencer** và **Aggregator** đều có thể nhóm message theo **correlationId**, nhưng mục đích không giống nhau:

| Thành phần | Điều làm với message | Output thường gặp |
| --- | --- | --- |
| **Resequencer** | Giữ các message đến sai thứ tự rồi phát lại theo sequenceNumber | Các message riêng lẻ theo đúng thứ tự |
| **Aggregator** | Tập hợp các message cùng nhóm và kết hợp thành một kết quả | Một aggregate message, như BatchReport |
| **Splitter** | Chia một message lớn thành các message con | Nhiều message con |
| **Router** | Chọn destination | Message được gửi sang channel phù hợp |
| **Filter** | Giữ hoặc loại theo điều kiện | Message tiếp tục hoặc discard |

Ví dụ:

~~~text
Input:  B(2), D(4), A(1), C(3)

Resequencer:
  output A(1)
  output B(2)
  output C(3)
  output D(4)

Aggregator:
  output Collection[A, B, C, D] hoặc một BatchReport
~~~

Resequencer **không tự tổng hợp** payload và không tự bảo đảm sự kiện của business chưa bị xử lý trước đó. Sau resequencing, Service Activator có thể ghi database, Gateway gọi dịch vụ ngoài hoặc Router chọn một nhánh khác; các bước ấy cần cơ chế retry/idempotency riêng.

### 2.1. Resequencer giải quyết một loại thứ tự, không phải mọi loại thứ tự

Resequencer dựa vào **sequenceNumber trong một correlation group**. Nó không thể tự xác định:

- Liệu sự kiện PAYMENT_CONFIRMED thật sự đã xảy ra sau STOCK_RESERVED.
- Liệu 2 event từ hai producer có cùng một **global total order**.
- Liệu broker đã mất message số 3 vĩnh viễn.
- Liệu event số 2 được xử lý **đúng một lần** trong database.
- Liệu metadata sequence do client tự khai báo có đáng tin hay không.

Nếu upstream gắn sai sequenceNumber, Resequencer có thể phát ra **đúng theo số sai**. Cần có hợp đồng sequence của producer và ranh giới dữ liệu đáng tin.

## 3. Ba metadata quyết định việc resequence

Một message thuộc nhóm thường có:

| Header | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **correlationId** | Định danh nhóm message cần sắp xếp | shipment-880:attempt-1 |
| **sequenceNumber** | Vị trí message trong nhóm, thường bắt đầu từ 1 | 3 |
| **sequenceSize** | Số lượng phần tử dự kiến | 4 |

~~~text
Message #3
  payload: PAYMENT_CONFIRMED
  correlationId: shipment-880:attempt-1
  sequenceNumber: 3
  sequenceSize: 4
~~~

Spring Integration mặc định sử dụng các header sequencing của framework cho Resequencer. Khi dùng Splitter để tạo các message con, framework có thể thêm correlationId/sequenceNumber/sequenceSize. Khi message đến từ HTTP hoặc broker bên ngoài, ứng dụng phải **xác minh** những giá trị này thay vì sao chép nguyên vào header nội bộ.

### 3.1. Correlation ID kỹ thuật không tự động bằng business ID

Ba identity cần được phân biệt:

- **businessStreamId**: ví dụ shipment-880, ổn định cho một luồng nghiệp vụ.
- **correlationId**: phân biệt tập message cần resequence trong một attempt/epoch.
- **eventId**: định danh **một sự kiện logic** để hỗ trợ dedup/redelivery.

Nếu dùng lại một correlationId đã hoàn tất để gửi một **sequence mới** gồm các message khác, group cũ có thể coi chúng là late và discard. Ngược lại, nếu đổi correlationId cho một **redelivery của sequence cũ**, Resequencer có thể coi nó như nhóm mới.

Do đó, phải có cách xác định **generation/epoch/version** của sequence. Ví dụ:

~~~text
businessStreamId = shipment-880
sequenceEpoch = 17
correlationId = shipment-880:17
~~~

Epoch chỉ tăng khi có **chuỗi mới thực sự**, không tăng vô điều kiện khi retry cùng chuỗi. Giữ eventId ổn định qua redelivery.

### 3.2. SequenceSize có thể không biết trước

Nếu upstream không biết số message sẽ có trong nhóm hoặc dùng nguồn streaming, sequenceSize có thể thiếu/không hữu dụng. Khi đó **đợi đủ sequenceSize** không còn là cách xác định completion thích hợp.

Cần chọn một giao thức khác: **end-of-stream marker**, manifest của sequence, time window, deadline hoặc workflow state. Không giả vờ sequenceSize=4 chỉ vì hiện tại đã nhận bốn message; có thể message thứ năm vẫn đang đi tới.

## 4. “Release” có ít nhất ba ngữ cảnh

Từ **release** dễ gây nhầm vì có nhiều thời điểm:

1. **Release toàn nhóm đủ:** Resequencer đã có các message cần thiết và phát chúng theo thứ tự. Nhóm được đánh dấu complete, thường giữ lại dấu metadata một thời gian.
2. **Release một đoạn liền mạch:** với **releasePartialSequences(true)**, một prefix hợp lệ có thể được phát sớm trong khi nhóm vẫn chờ những phần sau.
3. **Release hoặc expire do timeout:** nhóm chưa đủ nhưng chính sách timeout quyết định phát những message đang có hoặc loại chúng.

Một message đến “sau release” có thể mang ý nghĩa khác nhau trong ba trường hợp này.

### 4.1. Release đầy đủ theo mặc định

Spring Integration mô tả thuộc tính **releasePartialSequences** có mặc định **false**. Khi không phát từng đoạn, Resequencer đợi nhóm đủ điều kiện theo sequence metadata rồi phát các message theo thứ tự.

~~~text
Nhận: 3 -> 1 -> 4 -> 2
Sau nhận 3: chờ
Sau nhận 1: chờ
Sau nhận 4: chờ
Sau nhận 2: đủ nhóm 1..4
Phát: 1, 2, 3, 4
Group: COMPLETED
~~~

Sau đó, một bản **message 2 lặp lại** với cùng correlationId là một late arrival tới nhóm đã complete.

### 4.2. Phát từng prefix liên tục

Với **releasePartialSequences(true)**, framework có thể phát phần sequence **liền mạch từ vị trí hợp lệ tiếp theo**, thay vì chờ toàn bộ sequence. Ví dụ sau minh họa:

~~~text
Nhận 2: chưa có prefix 1..n -> chờ
Nhận 1: có 1,2 -> phát 1,2
Nhận 4: thiếu 3 -> giữ 4
Nhận 3: có 3,4 -> phát 3,4
Group: COMPLETED
~~~

Message 3 ở ví dụ này **đến sau khi 1,2 đã release** nhưng **không phải late message cần discard**: nó đến để lấp gap của một nhóm đang hoạt động.

Nếu người vận hành thấy “3 đến sau khi 1,2 phát ra” rồi chặn 3 như duplicate, pipeline sẽ **mất dữ liệu hợp lệ**.

### 4.3. Phát partial khi hết hạn

Giả sử đã nhận 1,2,4 nhưng **3 không bao giờ đến**, và timeout buộc nhóm phải kết thúc:

~~~text
Expected 1..4
Arrived 1,2,4
Group timeout
Policy: sendPartialResultOnExpiry = true
Output tại expiry: những message có thể được phát theo thứ tự
Group: đóng theo timeout policy
Tới sau: message 3
~~~

Lúc này message 3 là **late arrival sau timeout**. Nếu framework giữ empty-group metadata, nó có thể bị discard thay vì làm thay đổi output đã phát.

**Lưu ý:** không suy diễn rằng mọi cấu hình timeout phát đúng “1,2,4” mà không xét release strategy, sequence gap và phiên bản Spring Integration. Cần kiểm thử thực tế những gì được phát khi hết hạn và cách group được đóng.

## 5. Bảng quyết định: một message đến muộn sẽ đi đâu?

| Tình trạng group | Message đến | Hành vi/kỳ vọng cần thiết |
| --- | --- | --- |
| Đang chờ 1–4, mới có 2,4 | 1 | Bổ sung 1; nếu partial release có thể phát 1,2 |
| Prefix 1,2 đã release, đang giữ 4 | 3 | Bổ sung gap, sau đó có thể phát 3,4 |
| Group 1–4 đã complete, metadata còn | 2 lặp | Late/duplicate → discardChannel nếu cấu hình |
| Group timeout, metadata tombstone còn | 3 rất muộn | Late → discard/quarantine theo policy |
| Group bị xóa hoàn toàn khỏi store | 2 cũ | Có thể tạo group mới, rất nguy hiểm nếu không có dedup |
| CorrelationId mới nhưng cùng eventId | Event cũ | Có thể vào nhóm mới; cần event-level dedup |
| Group đang chờ nhưng nhận cùng sequenceNumber 2 lần | Duplicate trước release | Cần dedup/validation; không coi là hai vị trí khác |
| Group hoàn tất nhưng một sequence mới dùng nhầm correlationId | Message hợp lệ của epoch mới | Có thể bị discard nhầm; phải tách epoch |

**Nguyên tắc:** Resequencer biết **nhóm và thứ tự**, không tự quyết định một message cũ nên được *reopen*, *drop*, *replay* hay *đối soát* theo nghiệp vụ. Chính sách late arrival phải được công bố và kiểm thử.

## 6. Vì sao Spring Integration giữ empty group metadata?

Giả sử một sequence đã được phát đủ 1,2,3,4. Những payload đang chờ đã được đưa ra output. Tuy nhiên, nếu hệ thống **xóa sạch mọi dấu vết của group ngay lập tức**, khi message số 2 bị redeliver, resequencer không còn biết nhóm này **đã hoàn tất**.

~~~mermaid
flowchart TD
    A["Group G-880 có 1,2,3,4"] --> B["Release 1,2,3,4"]
    B --> C{"Giữ metadata complete?"}
    C -->|"Có"| D["Empty completed group / tombstone"]
    C -->|"Không, hoặc đã cleanup"| E["Group không còn trong store"]
    D --> L["Late msg #2"] --> X["Discard / audit late"]
    E --> M["Late msg #2"] --> N["Tạo group G-880 mới"]
    N --> O["Chờ thiếu 1,3,4; hoặc timeout lần nữa"]
~~~

Spring Integration giữ trạng thái nhóm đã release để **phát hiện và loại những message đến sau**. Tài liệu Aggregator/Resequencer gọi đây là các **empty groups**: phần message đã được release có thể không còn trong store, nhưng metadata về group đã complete vẫn có giá trị cho việc xử lý late arrival.

Đây là khái niệm tương tự **tombstone** trong quản lý trạng thái phân tán: dấu mốc “nhóm này từng tồn tại và đã kết thúc”.

### 6.1. Giữ metadata không có nghĩa giữ payload vĩnh viễn

Một group đã hoàn tất có thể không còn các message payload đang chờ, nhưng vẫn chiếm bộ nhớ/không gian trong MessageGroupStore vì metadata của group. Giữ metadata đủ lâu giúp phát hiện late replies, nhưng giữ **vĩnh viễn** có thể gây tăng bộ nhớ/DB.

Vì vậy cần:

- Một khoảng retention đủ bao phủ **thời gian redelivery tối đa** theo thực tế.
- Cơ chế cleanup/reaper theo retention.
- Một nguồn **dedup nghiệp vụ bền hơn** nếu message có thể được giao lại sau khi metadata của group bị dọn.
- Metrics đo số completed groups còn được giữ và số late messages.

Không thể đồng thời **xóa hoàn toàn mọi trạng thái** và vẫn bảo đảm nhận biết chính xác mọi redelivery cũ vô thời hạn.

### 6.2. expireGroupsUponTimeout(false) giúp gì?

Khi một group **timeout**, thuộc tính **expireGroupsUponTimeout** ảnh hưởng điều xảy ra với trạng thái group sau timeout. Tài liệu mô tả mặc định **false**: giữ metadata empty group để message đến muộn có thể bị nhận diện và discard. Khi đặt **true**, framework có thể xóa hoàn toàn group, và một message đến sau với cùng correlationId có thể tạo ra **một nhóm mới**.

Với trường hợp timeout vì thiếu sequence #3:

~~~text
Group cũ: 1,2,4
Timeout, đánh dấu đóng và giữ metadata
Message #3 đến sau:
  -> biết group cũ đã đóng
  -> discard/quarantine nếu được cấu hình
~~~

Trái lại:

~~~text
Group cũ: 1,2,4
Timeout, xóa sạch group
Message #3 đến sau:
  -> không thấy group cũ
  -> có thể tạo group mới chỉ chứa #3
  -> group mới khó đủ 1..4, tiếp tục chờ hoặc timeout
~~~

**Không cấu hình expireGroupsUponTimeout(true) chỉ để giảm memory** nếu chưa có cơ chế dedup/late-arrival khác. Đối với workflow quan trọng, hãy xem nó là **quyết định thay đổi semantics**, không chỉ là tối ưu tài nguyên.

### 6.3. Completed bình thường khác expired do timeout

Cần phân biệt hai loại kết thúc:

| Kiểu kết thúc | Vì sao kết thúc? | Câu hỏi sau kết thúc |
| --- | --- | --- |
| **Completed** | Đã đủ thông điệp theo release strategy | Có cần chống duplicate sequence lâu hơn? |
| **Timeout/Expired** | Không nhận đủ trước hạn nhưng policy buộc đóng | Message thiếu đến muộn có được xử lý bù hay không? |
| **Manually closed** | Operator/workflow quyết định chấm dứt | Có được phép mở lại bằng một epoch mới không? |

Các cấu hình giữ metadata sau completion và sau timeout không phải lúc nào cũng có cùng API hay cùng hành vi ở mọi phiên bản. Khi cài đặt, đọc JavaDoc của **ResequencerSpec/AbstractCorrelatingMessageHandler** tương ứng với dependency thực tế.

## 7. MessageGroupStore và dọn group đúng lúc

Spring Integration có các MessageGroupStore cho trạng thái nhóm:

- **In-memory store**: đơn giản, phù hợp demo hoặc các sequence ngắn, nhưng mất trạng thái khi restart.
- **Persistent store** như JDBC/Redis/Mongo tùy module: dùng khi cần khôi phục state và giữ tombstone qua restart.
- **Shared store**: hữu ích khi nhiều instance cùng xử lý nhóm, nhưng còn cần locking và concurrency control phù hợp.

Một persistent store **không tự** bảo đảm exactly-once end-to-end: nó giúp giữ trạng thái, còn side effect của downstream vẫn phải được thiết kế idempotent.

### 7.1. MessageGroupStoreReaper

Tài liệu Spring Integration đề cập **MessageGroupStoreReaper** để dọn các group tồn tại quá lâu. Với resequencer, reaper không chỉ là công cụ xóa message:

- Nó có thể làm hết hạn các **partial groups** chưa release.
- Nó có thể dọn **empty completed groups** sau một khoảng thời gian.
- Khi xóa group metadata, năng lực nhận biết một late arrival bằng chính group đó **không còn**.

**minimumTimeoutForEmptyGroups / empty-group-min-timeout** cho phép giữ completed group metadata lâu hơn partial groups trong những cấu hình hỗ trợ. Thời điểm dọn thực tế còn phụ thuộc lịch chạy reaper/scheduler và các timeout; không mặc định reaper xóa chính xác từng mili giây.

### 7.2. Lập ngân sách retention từ đặc tính broker

Không chọn retention 30 giây chỉ vì ví dụ chạy trong 30 giây. Với một hệ thống thực:

| Tham số | Câu hỏi cần trả lời |
| --- | --- |
| **Max redelivery delay** | Broker có thể giao lại message sau bao lâu? |
| **Offline recovery window** | Một consumer có thể offline bao lâu trước khi được phục hồi? |
| **Retry/DLQ replay** | Sau bao lâu operator có thể đưa message từ DLQ trở lại? |
| **Business correction window** | Có cho phép sửa một event đã hoàn tất không? |
| **Available store capacity** | Lưu metadata của bao nhiêu group cùng lúc? |
| **Dedup ledger lifetime** | Nếu group đã bị dọn, business key còn được bảo vệ bao lâu? |

Ví dụ mô hình retention minh họa:

~~~text
Resequencer active group timeout:        2 phút
Completed-group metadata retention:     24 giờ
Business dedup ledger retention:        30 ngày
Operator reprocess window:              30 ngày
~~~

Các con số trên **không phải mặc định Spring Integration** và không phù hợp cho mọi hệ thống. Điểm quan trọng là completed-group metadata chỉ có thể bảo vệ **trong khoảng còn tồn tại**; sau đó một ledger bền theo eventId/business key phải tiếp tục bảo vệ side effect nếu có.

### 7.3. Mất trạng thái khi restart

Kịch bản:

1. JVM A release xong 1,2,3,4; metadata completed nằm trong in-memory store.
2. JVM A restart, store trống.
3. Broker redeliver message 2 với cùng correlationId.
4. Resequencer không còn tombstone và có thể tạo group mới.

Khi có yêu cầu không nhận lại side effect cũ sau restart, dùng persistent store/ledger và thiết kế ack/transaction. Đừng đánh giá hành vi late chỉ trong một process sống liên tục.

### 7.4. Nhiều instance và ranh giới ownership

Nếu message 1,2 đến instance A còn 3,4 đến B, mỗi instance dùng in-memory MessageGroupStore riêng, không có instance nào biết đủ 1..4.

Các lựa chọn phổ biến:

1. Broker partition/route theo **correlationId** để cùng group về một owner.
2. Shared MessageGroupStore và **LockRegistry/transaction** thích hợp để tránh race giữa các instance.
3. Một workflow coordinator lưu state bền theo businessStreamId/epoch.

Chỉ chia sẻ database mà không có lock/ownership không tự sửa được race giữa hai worker cùng cập nhật một group. Cần integration test concurrent arrivals và failover.

## 8. Discard channel là chỗ quan sát late message

Nếu một message đến sau group đã được đánh dấu complete, Spring Integration có thể gửi nó tới **discardChannel** khi được cấu hình. Điều này khác với:

- **errorChannel**: nơi nhận ErrorMessage khi xử lý có exception trong các trường hợp tương ứng.
- **dead-letter queue (DLQ)**: nơi broker hoặc ứng dụng lưu message không xử lý được theo retry policy.
- **outputChannel**: đường message được release bình thường theo sequence.

~~~mermaid
flowchart TD
    M["Incoming sequenced message"] --> R["Resequencer"]
    R -->|"Hợp lệ & đã đủ để release"| O["orderedOutputChannel"]
    R -->|"Group đã complete/late"| D["lateDiscardChannel"]
    R -.->|"Exception khi xử lý"| E["errorChannel / caller"]
    D --> P["Audit / metric / quarantine"]
~~~

### 8.1. Tại sao không bỏ late message im lặng?

Một late arrival có thể cho biết:

- Broker redelivery là bình thường, consumer vẫn an toàn.
- Ack bị mất sau khi downstream đã xử lý.
- Retention group quá ngắn.
- Producer dùng lại correlationId sai.
- Một nhánh quá chậm hoặc bị queue starvation.
- Có dữ liệu nghiệp vụ bị thiếu sau một timeout.

Không phải lúc nào late message cũng cần được xử lý lại, nhưng nó **nên được quan sát và phân loại**. Tối thiểu đo **late_messages_total** theo loại, component và nguồn có tập giá trị hữu hạn.

### 8.2. Không route mọi late message quay lại Resequencer

Phản ví dụ:

~~~text
Resequencer -> discardChannel -> same resequencer input
~~~

Nếu group còn completed tombstone, message sẽ lại bị discard, tạo vòng lặp. Nếu group đã bị xóa, nó có thể tạo nhóm mới rồi lại timeout. Đường discard nên kết thúc ở audit/quarantine hoặc một **replay coordinator** có chính sách rõ, không đưa message quay vòng vô điều kiện.

### 8.3. Discard không có nghĩa toàn bộ request thất bại

Nếu sequence 1..4 đã được release và xử lý thành công, một bản message 2 trùng được discard là hành vi **mong muốn**. Không tự đánh dấu toàn bộ workflow thất bại chỉ vì metric late tăng; trước tiên phân loại **duplicate redelivery** với **first-time missing event đến sau timeout**.

## 9. Late message có thể hợp lệ: đừng loại vì tên gọi “late”

Một message đến sau deadline kỹ thuật chưa chắc là sự kiện không còn giá trị nghiệp vụ. Ví dụ:

- Event xác nhận thanh toán đến sau khi báo cáo được phát dưới dạng INCOMPLETE.
- Sensor telemetry gửi dữ liệu muộn nhưng analytics vẫn muốn cập nhật bảng historical.
- Một bản điều chỉnh nghiệp vụ được phê duyệt sau khi sequence ban đầu đã kết thúc.

Với các trường hợp này, có ba chính sách phổ biến:

| Chính sách | Khi áp dụng | Cần thêm gì? |
| --- | --- | --- |
| **Freeze** | Output đã phát được coi là cuối cùng | Discard/audit late, không thay output |
| **Correction** | Cho phép cập nhật kết quả đã công bố | Revision/compensation, downstream hỗ trợ sửa |
| **New epoch** | Sự kiện thuộc chuỗi mới, không phải bản gửi lại cũ | Correlation mới, mapping từ businessStreamId |

Không thể chỉ đổi **expireGroupsUponTimeout(true)** là biến message cũ thành correction hợp lệ. Khi muốn sửa kết quả lịch sử, cần một **quy trình nghiệp vụ** tạo correction/revision với identity mới, audit và side effect đúng nghĩa.

### 9.1. Ví dụ freeze

Sequence #1–#4 tạo ra một báo cáo vận chuyển cuối; một bản copy của #2 đến muộn chỉ được lưu vào log:

~~~text
Result version 1: FINAL
Late event #2: DUPLICATE_REDELIVERY
Action: DISCARD_AND_COUNT
~~~

### 9.2. Ví dụ correction

Sau timeout, hệ thống đã phát báo cáo INCOMPLETE thiếu #3. Khi #3 thực sự đến sau:

~~~text
Result version 1: INCOMPLETE, missing=[3]
Late event #3: FIRST_ARRIVAL_AFTER_DEADLINE
Action: create correction proposal
Result version 2: RECONCILED, nếu nghiệp vụ cho phép
~~~

Không tự thay đổi version 1 nếu downstream có thể đã dùng nó để lập hóa đơn/thanh toán. Một correction cần theo dõi ai được thông báo và có cần side effect bù.

### 9.3. Ví dụ new epoch

Nhóm shipment-880:17 đã complete. Một chuỗi trạng thái mới bắt đầu khi chuyển sang kho khác:

~~~text
Old correlationId: shipment-880:17
New correlationId: shipment-880:18
~~~

Nếu message mới còn dùng shipment-880:17, nó có thể bị coi là late. Producer phải tạo epoch 18 có chủ đích và giữ ổn định qua retry của epoch ấy.

## 10. Java 17: model sự kiện và dữ liệu để kiểm thử

Để tách **thứ tự kỹ thuật** khỏi **identity nghiệp vụ**, mô hình ví dụ gồm:

~~~java
record ShipmentStepEvent(
        String eventId,
        String shipmentId,
        int epoch,
        int position,
        String eventType) {

    ShipmentStepEvent {
        if (eventId == null || eventId.isBlank()
                || shipmentId == null || shipmentId.isBlank()
                || epoch <= 0
                || position < 1
                || position > 4
                || eventType == null || eventType.isBlank()) {
            throw new IllegalArgumentException(
                    "INVALID_SHIPMENT_STEP_EVENT");
        }
    }
}
~~~

Ở đây **position** là metadata nghiệp vụ để test và audit; việc Resequencer sắp xếp thực tế dựa trên **sequenceNumber header**. Trong production, phải kiểm tra position và header sequenceNumber khớp nhau. Nếu producer có thể gắn sai hoặc giả mạo headers, validate ở ingress trước khi gửi vào Resequencer.

Một hàm dựng message nội bộ:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class ShipmentMessages {
    private ShipmentMessages() {}

    static Message<ShipmentStepEvent> sequenced(
            ShipmentStepEvent event) {

        String group = event.shipmentId() + ":" + event.epoch();

        return MessageBuilder.withPayload(event)
                .setHeader(
                        IntegrationMessageHeaderAccessor.CORRELATION_ID,
                        group)
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER,
                        event.position())
                .setHeader(
                        IntegrationMessageHeaderAccessor.SEQUENCE_SIZE,
                        4)
                .setHeader("businessEventId", event.eventId())
                .build();
    }
}
~~~

**Lưu ý trust boundary:** ví dụ dựng headers bằng code nội bộ. Đừng dùng dữ liệu từ HTTP client để quyết định tùy ý correlationId, sequenceSize, replyChannel hoặc errorChannel mà không xác thực/validate. Nếu một luồng cần nhiều loại sequence với kích thước khác nhau, đưa sequenceSize vào manifest đáng tin thay vì hard-code 4.

## 11. Java DSL: Resequencer chỉ release khi đủ nhóm

Với yêu cầu **không phát thông điệp khi nhóm chưa đủ**, bắt đầu bằng cấu hình rõ ràng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class CompleteSequenceResequencerConfig {

    @Bean
    MessageChannel sequenceInputChannel() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel orderedStepsChannel() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel lateSequenceDiscardChannel() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow resequenceShipmentSteps() {
        return IntegrationFlow.from("sequenceInputChannel")
                .resequence(r -> r
                        .releasePartialSequences(false)
                        .sendPartialResultOnExpiry(false)
                        .expireGroupsUponTimeout(false)
                        .discardChannel("lateSequenceDiscardChannel"))
                .channel("orderedStepsChannel")
                .get();
    }
}
~~~

**Các điểm quan trọng:**

1. **releasePartialSequences(false)**: đợi đủ điều kiện group complete trước khi phát sequence.
2. **sendPartialResultOnExpiry(false)**: không chủ động gửi phần còn thiếu như một sequence thành công chỉ vì group hết hạn.
3. **expireGroupsUponTimeout(false)**: nếu group bị timeout/expired theo cơ chế đã cấu hình, giữ metadata cho late-arrival handling.
4. **discardChannel**: có nơi quan sát message bị xem là late/không được nhận vào group.
5. **QueueChannel** ở output/discard chỉ để ví dụ dễ test. Production cần consumer hoặc store với bounded capacity, không để queue tăng vô hạn.

**Cần phân biệt:** mẫu trên chưa khai báo groupTimeout/reaper. Vì vậy, một nhóm mất hẳn message 3 có thể nằm chờ nếu không có chính sách expiration. Cấu hình timeout/reaper phải được bổ sung khi ứng dụng thực cần giải quyết nhóm thiếu message.

### 11.1. Thêm deadline và xử lý group không hoàn chỉnh

Mảnh cấu hình DSL sau minh họa policy khi nhóm chờ quá lâu:

~~~java
.resequence(r -> r
        .releasePartialSequences(false)
        .groupTimeout(30_000)
        .sendPartialResultOnExpiry(false)
        .expireGroupsUponTimeout(false)
        .discardChannel("lateSequenceDiscardChannel"))
~~~

Với policy này, một nhóm thiếu message có thể bị expire thay vì được release như sequence hoàn chỉnh. **groupTimeout có semantics kích hoạt theo hoạt động của group và scheduler**; không nên suy luận đó là deadline cố định chính xác 30 giây tính từ sự kiện đầu tiên. Nếu yêu cầu deadline nghiệp vụ bất biến, dùng một state/deadline riêng theo businessStreamId.

Trong hệ thống cần replay, thêm persistent MessageGroupStore và timeout/reaper phù hợp; cấu hình phương thức **messageStore(...)**, **taskScheduler(...)**, **minimumTimeoutForEmptyGroups(...)** tùy phiên bản và loại store.

### 11.2. XML là một lựa chọn cấu hình khác

Một ứng dụng dùng XML có thể cấu hình resequencer tương ứng:

~~~xml
<int:resequencer
    input-channel="sequenceInputChannel"
    output-channel="orderedStepsChannel"
    discard-channel="lateSequenceDiscardChannel"
    release-partial-sequences="false"
    send-partial-result-on-expiry="false"
    expire-group-upon-timeout="false" />
~~~

Đây là **mảnh XML** giả định đã khai báo namespace int và các channel. Nếu muốn expiration chủ động, cần cấu hình group timeout/scheduler hoặc reaper riêng. Tên option trong Java DSL và XML có thể khác nhau; dùng đúng API của Spring Integration đang sử dụng.

## 12. Java DSL: cho phép phát partial sequence liên tục

Một hệ thống hiển thị tiến trình đơn hàng có thể muốn phát ngay **các bước liên tục từ đầu**, không chờ toàn bộ 4 bước.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class ContiguousPrefixResequencerConfig {

    @Bean
    MessageChannel prefixInputChannel() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel prefixOutputChannel() {
        return new QueueChannel();
    }

    @Bean
    QueueChannel prefixLateDiscardChannel() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow prefixResequenceFlow() {
        return IntegrationFlow.from("prefixInputChannel")
                .resequence(r -> r
                        .releasePartialSequences(true)
                        .sendPartialResultOnExpiry(false)
                        .discardChannel("prefixLateDiscardChannel"))
                .channel("prefixOutputChannel")
                .get();
    }
}
~~~

Ví dụ gửi sequence theo thứ tự:

~~~text
Send 1  -> phát 1
Send 2  -> phát 2
Send 4  -> chờ 3
Send 3  -> phát 3,4
Group   -> completed
~~~

**Ý nghĩa:** message 3 không phải lỗi chỉ vì nó đến sau khi 1,2 đã release. Nó là **phần tử còn thiếu đang được đợi**. Chỉ khi group đã complete/expired theo policy và metadata đóng còn hiệu lực, message mới thuộc diện late discard.

### 12.1. Không dùng partial release cho mọi nghiệp vụ

Nếu bước #2 là **giữ tiền**, bước #3 là **xác minh fraud**, nhưng nghiệp vụ chỉ cho phép ghi nhận toàn bộ chuỗi khi đủ 1..4, việc phát prefix 1,2 sớm có thể tạo side effect không thể rollback sau đó.

Hãy chọn:

- **Full release** khi downstream cần tính toàn vẹn của toàn chuỗi trước khi làm gì tiếp.
- **Partial contiguous release** khi mỗi bước hợp lệ có thể đi tiếp ngay mà không cần biết tương lai và ứng dụng đã thiết kế recovery nếu bước sau không tới.

Không chọn true chỉ vì nó giảm latency trung bình; phải đánh giá semantic của các hành động downstream.

## 13. Integration test: late message sau complete group bị discard

Test sau sử dụng **JUnit 5 + spring-test** và cấu hình ở mục 11. Gửi các sự kiện 3,1,2 rồi kiểm tra chưa có output; gửi 4 để hoàn tất và nhận 1,2,3,4 theo thứ tự. Sau đó gửi **bản lặp #2** trong cùng group và xác nhận nó không xuất hiện trên output mà đi tới discard channel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(CompleteSequenceResequencerConfig.class)
class LateAfterCompleteResequencerTest {

    @Autowired
    @Qualifier("sequenceInputChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("orderedStepsChannel")
    QueueChannel output;

    @Autowired
    @Qualifier("lateSequenceDiscardChannel")
    QueueChannel discarded;

    @BeforeEach
    void clearQueues() {
        while (output.receive(0) != null) {
            // Dọn queue test.
        }
        while (discarded.receive(0) != null) {
            // Dọn queue test.
        }
    }

    private ShipmentStepEvent event(int n) {
        return new ShipmentStepEvent(
                "evt-880-" + n, "shipment-880", 17, n,
                "STEP_" + n);
    }

    private void send(int n) {
        assertTrue(input.send(
                ShipmentMessages.sequenced(event(n))));
    }

    @Test
    void completedGroupDiscardsLateDuplicate() {
        send(3);
        send(1);
        send(2);
        assertNull(output.receive(0));

        send(4);
        List<Integer> emitted = new ArrayList<>();
        for (int i = 0; i < 4; i++) {
            Message<?> next = output.receive(0);
            assertNotNull(next);
            emitted.add(
                    ((ShipmentStepEvent) next.getPayload()).position());
        }
        assertEquals(List.of(1, 2, 3, 4), emitted);
        assertNull(output.receive(0));

        send(2); // Cùng correlationId và sequenceNumber.
        assertNull(output.receive(0));

        Message<?> late = discarded.receive(0);
        assertNotNull(late);
        assertEquals(2,
                ((ShipmentStepEvent) late.getPayload()).position());
    }
}
~~~

**Điều test này chứng minh trong một JVM không restart:**

- Khi releasePartialSequences=false, output chưa phát trước khi nhóm đủ.
- Resequencer phát ra các message theo sequenceNumber tăng dần.
- Sau khi nhóm completed và metadata còn, bản lặp đến sau không được phát như message bình thường.
- Discard channel cho phép quan sát message late.

Test này **chưa chứng minh** persistent store/reaper sau restart, duplicate khi hai workers gửi đồng thời hoặc side effect downstream idempotent. Những trường hợp ấy cần integration tests riêng.

### 13.1. Chú ý về tính độc lập của test

Nếu dùng cùng correlationId cho nhiều test trên cùng Spring context, completed-group metadata còn lại có thể khiến test khác bị discard bất ngờ. Mỗi test nên dùng **correlationId/epoch duy nhất**, hoặc tạo context/store riêng trong test. Không chỉ dọn QueueChannel output là đã xóa MessageGroupStore.

## 14. Integration test: gap-filling khác late duplicate

Với cấu hình ContiguousPrefixResequencerConfig ở mục 12, thứ tự gửi **1, 2, 4, 3** cho thấy:

- 1 được phát vì prefix đã bắt đầu.
- 2 được phát khi liền sau 1.
- 4 cần đợi message 3.
- 3 đến sau nhưng **là một phần tử hợp lệ chưa phát**; 3 và 4 được phát đúng thứ tự.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ContiguousPrefixResequencerConfig.class)
class PrefixGapResequencerTest {

    @Autowired
    @Qualifier("prefixInputChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("prefixOutputChannel")
    QueueChannel output;

    @Autowired
    @Qualifier("prefixLateDiscardChannel")
    QueueChannel late;

    private void send(int position) {
        ShipmentStepEvent event = new ShipmentStepEvent(
                "evt-prefix-" + position,
                "shipment-prefix", 1, position,
                "STEP_" + position);
        assertTrue(input.send(
                ShipmentMessages.sequenced(event)));
    }

    private int nextPosition() {
        Message<?> message = output.receive(0);
        assertNotNull(message);
        return ((ShipmentStepEvent) message.getPayload()).position();
    }

    @Test
    void missingPositionIsNotDiscardedWhileGroupIsOpen() {
        send(1);
        assertEquals(1, nextPosition());

        send(2);
        assertEquals(2, nextPosition());

        send(4);
        assertNull(output.receive(0)); // Vẫn chờ bước #3.

        send(3);
        assertEquals(List.of(3, 4),
                List.of(nextPosition(), nextPosition()));
        assertNull(output.receive(0));
        assertNull(late.receive(0));
    }
}
~~~

**Test này bổ sung góc nhìn quan trọng:** không nên có một interceptor tự loại mọi message có sequenceNumber lớn hơn hoặc nhỏ hơn một giá trị dự đoán theo thời gian. Phải kiểm tra group đang mở, những vị trí đã release, những gap còn chờ và chính sách timeout.

### 14.1. Sau partial release nhưng chưa complete, duplicate cũ thì sao?

Giả sử 1 và 2 đã phát, nhưng 3 và 4 chưa đến. Nếu message 1 bị giao lại:

~~~text
Released prefix: 1,2
Expected next: 3
Incoming: 1 (duplicate)
~~~

Một ứng dụng cần bảo đảm **không phát lại 1**; tuy nhiên việc framework chọn discard/ignore hoặc cách group xử lý duplicate trước complete còn tùy cấu hình release strategy và phiên bản. Nếu cần lưu vết chắc chắn, đặt **dedup theo eventId/position** ở ranh giới phù hợp, đồng thời test trực tiếp trên version đang dùng.

Không tự khẳng định mọi bản trùng ở một group chưa complete luôn được gửi tới discardChannel theo cùng cách như late message của completed group. Đó là hai trạng thái khác nhau cần test riêng.

## 15. Kiểm thử timeout và late arrival sau expiry

Test dùng đồng hồ thật với Thread.sleep dễ không ổn định trong môi trường CI. Một kế hoạch integration test đáng tin nên kiểm soát **TaskScheduler** hoặc sử dụng công cụ hỗ trợ chờ có thời hạn, tạo group thiếu rồi kích hoạt expiration một cách xác định.

### 15.1. Bộ tình huống cốt lõi

| Bước | Tác động | Kết quả cần quan sát |
| --- | --- | --- |
| 1 | Gửi sequence 1,2,4 của group G | Group chưa đủ do thiếu #3 |
| 2 | Đạt groupTimeout khi sendPartialResultOnExpiry=false | Không phát nhầm full ordered sequence |
| 3 | expireGroupsUponTimeout=false | Group metadata còn để nhận diện late |
| 4 | Gửi #3 sau timeout | Không tự bổ sung vào một kết quả đã đóng |
| 5 | Bật discardChannel | Late #3 được quan sát hoặc lưu theo policy |
| 6 | Thử với expireGroupsUponTimeout=true | Group cũ bị xóa, #3 có thể tạo group mới |
| 7 | Kiểm tra reaper cleanup | Metadata cuối cùng được dọn theo retention |

**Điểm cần cẩn trọng:** với timeout, một group có thể được xử lý theo scheduler; test phải chờ **sự kiện group expired** hoặc quan sát store trạng thái, không chỉ ngủ đúng bằng số mili giây trong cấu hình.

### 15.2. Tránh test “không phát message” bằng một chờ không giới hạn

Nếu test chờ indefinite trên QueueChannel và group không release, test có thể treo. Dùng:

~~~java
Message<?> unexpected = orderedOutput.receive(200);
assertNull(unexpected);
~~~

Ở đây **200 ms** là thời gian kiểm tra ví dụ; test cần được thiết kế với scheduler, event và timeout thực tế để không bị flaky. Kết quả receive(200)==null chỉ nói **không quan sát được output trong cửa sổ đó**, không chứng minh output sẽ không xuất hiện muộn hơn nếu scheduler tiếp tục chạy.

### 15.3. Test hai chính sách timeout

Với cùng sequence thiếu #3:

- **Không phát partial, giữ metadata:** nhóm phải đóng theo policy, late #3 không tạo output thành công.
- **Phát partial:** các message đã có có thể được phát theo chính sách timeout; báo cáo downstream phải thể hiện **thiếu #3** và không coi sequence này hoàn tất đầy đủ.

Resequencer không tự sinh một **BatchReport INCOMPLETE**. Nếu nghiệp vụ cần biết vị trí thiếu, hãy có **sequence manifest** hoặc một workflow state store riêng để đối chiếu. Chỉ quan sát output 1,2,4 không đủ chứng minh #3 chưa từng tồn tại.

## 16. Khi metadata group bị dọn: chống lặp ở tầng nghiệp vụ

Ngay cả khi Resequencer đang vận hành đúng, một broker redelivery sau khi completed-group metadata đã hết retention có thể được coi là một group mới. Nếu downstream thực hiện side effect, cần bảo vệ ở **chính điểm tạo effect**.

Giả sử handler sau Resequencer ghi một bản ghi kiểm toán vận đơn:

~~~text
Event: evt-880-2
Business stream: shipment-880
Epoch: 17
Sequence position: 2
Operation: record-shipment-step
~~~

Một identity ổn định:

~~~text
effectKey =
    trustedTenantId
    + ":" + businessStreamId
    + ":" + epoch
    + ":" + eventId
    + ":" + logicalActionId
~~~

Nếu eventId đã được định danh duy nhất toàn bộ tenant và hành động, có thể giản lược khóa; nếu eventId chỉ duy nhất theo stream, cần thêm stream/epoch. Phải công bố phạm vi duy nhất thay vì dùng một chuỗi ghép bất kỳ.

### 16.1. Bảng lưu effect đã thực hiện

~~~sql
CREATE TABLE shipment_step_execution (
    tenant_id VARCHAR(80) NOT NULL,
    shipment_id VARCHAR(80) NOT NULL,
    epoch INTEGER NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    action_id VARCHAR(80) NOT NULL,
    sequence_position INTEGER NOT NULL,
    status VARCHAR(24) NOT NULL,
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (
        tenant_id, shipment_id, epoch, event_id, action_id
    )
);
~~~

Ví dụ một transaction ghi event lần đầu:

~~~sql
INSERT INTO shipment_step_execution (
    tenant_id, shipment_id, epoch, event_id,
    action_id, sequence_position, status, processed_at
) VALUES (
    :tenant, :shipment, :epoch, :eventId,
    :action, :position, 'COMPLETED', CURRENT_TIMESTAMP
)
ON CONFLICT DO NOTHING;
~~~

Nếu đã có bản ghi cùng khóa, ứng dụng kiểm tra trạng thái hiện hữu và không thực hiện side effect trùng. Nhưng **ON CONFLICT DO NOTHING** chỉ bảo vệ thao tác INSERT này; nếu còn UPDATE tồn kho, gửi HTTP hoặc tạo vận đơn, phải phối hợp transaction, outbox hoặc idempotency của dịch vụ ngoài đúng cách.

### 16.2. Ghi idempotency record và effect trong cùng transaction

Với effect thuộc cùng một database, một service có thể ghi ledger và cập nhật nghiệp vụ trong **cùng transaction**. Nếu transaction rollback, cả hai thay đổi cùng rollback. Nếu commit thành công rồi message bị redeliver, unique constraint/ledger ngăn effect lặp.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant R as Resequencer
    participant S as Domain Service
    participant DB as Database
    B->>R: event E (first delivery)
    R->>S: ordered E
    S->>DB: TX: claim E + apply effect
    DB-->>S: Commit
    B->>R: event E (late redelivery)
    Note over R: Nếu metadata còn: discard
    R-->>B: late discard
    Note over S: Nếu metadata đã mất và E tới lại
    R->>S: E một lần nữa
    S->>DB: TX: claim E
    DB-->>S: Already completed
~~~

**Hai lớp bảo vệ bổ sung nhau:**

- **Resequencer metadata** giúp quản lý ordering/group lifecycle.
- **Business idempotency** giúp bảo vệ side effect ngay cả khi metadata của group đã hết hạn.

### 16.3. External side effect không thể rollback bằng DB

Nếu downstream gửi email hoặc gọi payment provider, một transaction database không tự thu hồi được tác động đã diễn ra ở dịch vụ ngoài.

Cần:

1. **Idempotency key** tương thích với provider.
2. Trạng thái UNKNOWN khi request có thể đã thực hiện nhưng response bị mất.
3. Tra cứu/đối soát trước khi gửi lệnh mới có side effect.
4. Outbox hoặc cơ chế reliable delivery nếu cần phục hồi qua crash.
5. Chính sách xử lý late event theo business operation, không chỉ sequenceNumber.

Không có cấu hình Resequencer nào tự tạo exactly-once effects trên toàn hệ thống.

## 17. Phát hiện late bằng dữ liệu nào?

Đừng chỉ so sánh **event timestamp** với đồng hồ nhận message. Một message có timestamp cũ có thể đến đúng hạn đối với group chưa complete; một message có timestamp mới vẫn có thể là bản lặp.

Nên phân loại bằng:

| Tín hiệu | Dùng để kết luận gì? | Hạn chế |
| --- | --- | --- |
| **correlationId + epoch** | Message thuộc group nào? | Có thể tái sử dụng sai |
| **sequenceNumber** | Vị trí trong group | Không phải identity duy nhất toàn hệ thống |
| **eventId** | Logical event đã seen/completed chưa? | Cần bảo đảm ổn định/duy nhất |
| **Group status** | ACTIVE, COMPLETED hay EXPIRED? | Có thể mất sau cleanup/restart |
| **Last released position** | Prefix nào đã phát? | Cần trạng thái bền nếu quan trọng |
| **Business deadline** | Cho phép sửa kết quả đến lúc nào? | Không đồng nghĩa groupTimeout |
| **Ledger effect status** | Side effect đã commit chưa? | Phải cùng transaction/đối soát đúng |

### 17.1. Một thuật toán quyết định ở mức ứng dụng

~~~text
Nhận sequenced message
  -> xác minh tenant, eventId, epoch và sequence bounds
  -> xem business event/operation đã COMPLETED chưa?
      -> Có: đánh dấu duplicate, không tạo side effect mới
      -> Chưa:
          -> group ACTIVE, position còn thiếu: đưa vào Resequencer
          -> group COMPLETED/EXPIRED:
               -> policy FREEZE: audit/discard
               -> policy CORRECTION: tạo revision workflow
               -> policy NEW_EPOCH: chỉ chấp nhận nếu có epoch mới
          -> group không tồn tại:
               -> kiểm tra ledger/manifest trước khi coi là group mới
~~~

Đây là **policy ở tầng ứng dụng**, không phải thuật toán mặc định của Resequencer. Trong deployment thực, xử lý concurrency, ownership và transaction trước khi dùng dữ liệu này để quyết định.

### 17.2. Duplicate khác first-time missing event

Hai loại late arrival có yêu cầu khác nhau:

~~~text
LATE_DUPLICATE:
  eventId đã xử lý trước khi group close
  → không thực hiện lại, chỉ audit/count

LATE_FIRST_ARRIVAL:
  eventId chưa từng xử lý
  group đã expired vì thiếu position
  → freeze/quarantine hoặc correction theo policy
~~~

Nếu chỉ nhìn thấy cả hai đều đến muộn và bỏ ngay, hệ thống có thể **mất cơ hội đối soát một sự kiện thực sự chưa được xử lý**. Nếu lại xử lý mọi thứ, nguy cơ duplicate effect xuất hiện. Phân loại bằng event identity và trạng thái bền là chìa khóa.

## 18. Lỗi thường gặp trong pipeline với Resequencer

### 18.1. Thêm Filter ở trước Resequencer mà không cập nhật completion

Giả sử producer gửi bốn message với sequenceSize=4, nhưng Filter loại message #3. Resequencer chỉ nhận 1,2,4 và có thể chờ mãi.

~~~mermaid
flowchart LR
    P["Producer 1,2,3,4"] --> F["Filter"]
    F -->|"1,2,4"| R["Resequencer"]
    F -.->|"3 bị loại"| D["Discard"]
    R --> X["Chờ #3 hoặc timeout"]
~~~

Nếu message #3 **thật sự không cần** cho nghiệp vụ, hãy định nghĩa lại manifest/sequence trước khi gắn sequence metadata, hoặc cung cấp một failure/skip marker có identity theo hợp đồng. Không tự sửa sequenceSize thành 3 ở từng message để che việc một thành viên đã mất.

### 18.2. Đổi sequenceNumber trong Transformer

Transformer có thể tạo Message mới và thay headers. Nếu sequenceNumber biến thành thứ tự arrival thay vì thứ tự logic của producer, Resequencer sẽ không sửa được tình trạng đảo thứ tự.

Kiểm thử **header propagation** qua Transformer, Router, Splitter, Gateway và adapter; tránh tạo business eventId/correlationId mới không có chủ đích ở giữa một group.

### 18.3. Dùng chung correlationId cho các yêu cầu độc lập

Hai lô hàng có thể cùng sequenceNumber=1..4. Nếu chúng đều dùng correlationId="current", Resequencer có thể trộn các message của hai lô vào một group.

~~~text
shipment-A seq1 --> group "current"
shipment-B seq1 --> group "current"  // Sai
~~~

Chọn correlationId dựa trên **business stream + epoch** đủ duy nhất. Tenant ID cần được xác minh nếu hệ thống đa tenant.

### 18.4. Xóa group để “sửa” message bị thiếu

Nếu một group đang thiếu #3, operator xóa group thủ công rồi phát lại #3:

- Group mới không còn #1,#2,#4.
- Nó có thể tiếp tục chờ vô hạn.
- Đã mất thông tin rằng #1,#2 có thể từng release hoặc thực hiện effect.

Muốn replay, dùng một quy trình có manifest, event state và dedup, không coi **xóa group** là một lệnh sửa dữ liệu chung.

### 18.5. Đặt timeouts nhưng không theo dõi late arrivals

Group timeout giúp ứng dụng không chờ mãi, nhưng một message đến sau deadline vẫn cần được phân loại. Nếu không có discardChannel hoặc audit, những sự kiện bị mất do policy timeout có thể không được phát hiện cho đến khi đối soát nghiệp vụ.

### 18.6. Coi việc emit ordered output là commit nghiệp vụ

Resequencer chỉ phát message theo thứ tự. Nếu handler sau đó ghi database hoặc gọi service và thất bại, việc order đúng không có nghĩa effect đã hoàn tất. Ack/retry/transaction ở consumer downstream cần được thiết kế riêng.

### 18.7. Cho phép late replay tái sử dụng eventId mới

Nếu operator phát lại một event cũ nhưng đổi eventId, business ledger có thể xem đó là event mới và thực hiện side effect lần hai. Replay cùng logical event phải giữ identity ổn định; correction có chủ đích nên có **operation/revision identity mới** nhưng liên kết với event cũ.

## 19. Quan sát và cảnh báo

Một Resequencer hoạt động tốt không chỉ thể hiện ở số message output theo thứ tự. Cần đo **bao nhiêu group đang chờ, bao nhiêu message bị giữ, bao nhiêu message đến sau khi group đã đóng**.

| Tín hiệu | Ý nghĩa vận hành |
| --- | --- |
| **resequencer_inbound_total** | Số message đến Resequencer |
| **resequencer_released_total** | Số message đã phát đúng release policy |
| **resequencer_late_discard_total{reason}** | Số late messages bị discard theo loại |
| **resequencer_duplicate_total** | Bản lặp theo eventId/sequence identity |
| **resequencer_gap_waiting_groups** | Số group đang thiếu vị trí |
| **resequencer_group_pending** | Số MessageGroup chưa hoàn tất |
| **resequencer_group_age_seconds** | Tuổi group đang chờ |
| **resequencer_group_timeout_total** | Số group hết hạn |
| **resequencer_partial_release_total** | Số lần phát prefix/partial theo policy |
| **resequencer_empty_group_count** | Số completed group metadata được giữ |
| **resequencer_group_reaped_total** | Số group/metadata đã được dọn |
| **resequencer_correlation_rejected_total** | Message có group identity không hợp lệ |
| **resequencer_store_operation_failed_total** | Lỗi đọc/ghi MessageGroupStore |
| **resequencer_discard_handler_failed_total** | Đường xử lý late/discard thất bại |
| **resequencer_recovery_attempts_total** | Các lần thử khôi phục có chủ đích |
| **downstream_idempotency_skip_total** | Số side effect trùng được ngăn |

Các labels nên có tập giá trị nhỏ: component, source, reason, deployment version. **Không đặt eventId, shipmentId, tenantId hoặc correlationId không giới hạn làm metric label**, vì cardinality có thể tăng cực lớn. Những ID này có thể nằm trong log/tracing có quyền truy cập và retention phù hợp.

### 19.1. Log cho một late duplicate

~~~json
{
  "eventId": "evt-880-2",
  "businessStreamId": "shipment-880",
  "sequenceEpoch": 17,
  "sequenceNumber": 2,
  "groupStatus": "COMPLETED",
  "classification": "LATE_DUPLICATE",
  "action": "DISCARD_AND_AUDIT"
}
~~~

### 19.2. Log cho một first-time late arrival

~~~json
{
  "eventId": "evt-880-3",
  "businessStreamId": "shipment-880",
  "sequenceEpoch": 17,
  "sequenceNumber": 3,
  "groupStatus": "EXPIRED",
  "classification": "LATE_FIRST_ARRIVAL",
  "action": "QUARANTINE_FOR_RECONCILIATION"
}
~~~

Đây là các log mẫu về **quyết định nghiệp vụ sau khi đã phân loại**, không phải cấu trúc ErrorMessage hoặc Discard Message mặc định của framework. Chỉ log metadata cần thiết; tránh ghi token, payload nhạy cảm, headers điều khiển từ nguồn chưa tin cậy.

### 19.3. Tình huống đáng cảnh báo

1. Late duplicates tăng mạnh sau thay đổi ack/retry của broker.
2. Late first-time arrivals tăng sau deploy một nhánh xử lý chậm.
3. Số group pending tăng liên tục, không có timeout/cleanup.
4. Completed empty groups tăng nhưng reaper không chạy.
5. Discard rate tăng sau khi giảm retention hoặc restart.
6. MessageGroupStore không khả dụng, nhưng consumer vẫn ack messages.
7. Sau failover, một số correlation groups xuất hiện lại như nhóm mới.
8. SequenceNumber trùng hoặc sequenceSize mâu thuẫn trong cùng group.
9. Có side effect đã commit được ghi lại lần thứ hai sau replay.
10. Một operator correction không có audit và revision identity rõ ràng.

## 20. Runbook điều tra một message đến muộn

Khi nhận alert late message, đừng vội gửi lại message về Resequencer. Xác định:

### Bước 1 — Xác minh message identity

Thu thập eventId, trusted tenant, businessStreamId, epoch, correlationId, sequenceNumber, sequenceSize, schemaVersion và trace ID. Kiểm tra source của headers có đáng tin không. Không dùng message timestamp đơn lẻ để kết luận duplicate.

### Bước 2 — Xác định group lifecycle

Tìm group đang ACTIVE, COMPLETED hay EXPIRED; metadata còn hay đã bị reaper dọn; có restart/failover gần đây không. Nếu group không tồn tại, xem ledger/manifest và lịch sử xử lý trước khi quyết định message này là một sequence mới.

### Bước 3 — Phân loại

| Nhãn | Điều kiện minh họa | Hành động khởi điểm |
| --- | --- | --- |
| DUPLICATE_REDELIVERY | Event effect đã COMMITTED | Discard có audit |
| GAP_FILLER_ACTIVE | Group mở và vị trí chưa release | Cho đi qua resequencing |
| LATE_FIRST_ARRIVAL | Group đã timeout, effect chưa chạy | Quarantine/correction theo policy |
| NEW_EPOCH_MESSAGE | Sequence epoch khác được phê duyệt | Xử lý như group mới |
| CORRELATION_COLLISION | Hai luồng dùng chung group ID | Chặn, sửa producer và đối soát |
| UNKNOWN_STATE | Không xác định effect đã xảy ra chưa | Đối soát trước khi retry |

### Bước 4 — Kiểm tra tác động downstream

Một message đã được Resequencer release chưa chắc đã hoàn thành ở database. Đối chiếu service ledger, transaction commit, provider idempotency response và outbox; không chỉ đọc log “dispatched successfully”.

### Bước 5 — Chọn hành động

- **Freeze:** giữ kết quả trước đó, discard/audit.
- **Correction:** tạo version/revision mới và các hiệu ứng điều chỉnh cần thiết.
- **Replay:** retry với eventId ổn định nếu chưa xử lý và policy cho phép.
- **New epoch:** chỉ khi là nghiệp vụ mới, không phải bản gửi lại một message cũ.

### Bước 6 — Theo dõi sau khắc phục

Đối chiếu số sự kiện expected, received, released, discarded, completed và pending theo từng logical stream. Xác minh không xuất hiện side effect trùng hoặc missing event âm thầm.

## 21. Ma trận test cần có trước production

| Kịch bản | Quan sát quan trọng |
| --- | --- |
| 3,1,4,2 với full release | Output 1,2,3,4 sau đủ nhóm |
| 1,2,4,3 với partial release | 1,2 trước; 3,4 sau; 3 không bị discard |
| Bản lặp #2 sau full completion | Không emit lần hai; late discard được ghi |
| Duplicate #2 khi group còn ACTIVE | Không có duplicate effect; behavior được kiểm chứng |
| #3 đến sau timeout, metadata còn | Được phân loại late, không mở lại group cũ |
| #3 đến sau timeout, metadata bị xóa | Có thể tạo group mới; business ledger bảo vệ |
| Restart với in-memory store | Quan sát nguy cơ mất group state |
| Restart với persistent store | Trạng thái completed/expired còn theo retention |
| Hai instance xử lý một group | Không release sai thứ tự hoặc cùng message hai lần |
| Hai group cùng lúc | Không trộn correlation |
| CorrelationId tái sử dụng cho epoch khác | Validation bắt lỗi hoặc tách group mới đúng |
| SequenceNumber ngoài 1..sequenceSize | Bị reject/quarantine trước resequencer |
| SequenceSize không nhất quán trong một group | Chặn/alert, không release sai |
| Reaper cleanup completed group | State được dọn theo retention, ledger vẫn bảo vệ |
| Error/discard channel không có consumer | Phát hiện lỗi giám sát, không mất dữ liệu âm thầm |
| Message #2 redelivery sau DB commit | Downstream không ghi effect lần hai |
| Late correction có chủ đích | Có revision và audit, không ghi đè kết quả cũ âm thầm |

### 21.1. Cách kiểm thử restart

Một bài test tích hợp với database MessageGroupStore và container ứng dụng có thể:

1. Gửi 1,2,3,4; đợi release thành công và completed marker được lưu.
2. Dừng ứng dụng, **không xóa database**.
3. Khởi động lại ứng dụng dùng cùng store.
4. Gửi lại message 2 với cùng correlationId.
5. Xác minh nó không được phát như một message bình thường trong thời hạn marker còn tồn tại.
6. Sau retention/reaper, gửi lại và xác minh **business dedup ledger** vẫn chặn effect trùng.

Đây là **kế hoạch test**, không được suy ra từ unit test với QueueChannel in-memory. Trong STEP 4, chúng ta viết hướng dẫn và ví dụ; vòng content QA hoặc test thực tế có thể được tổ chức ở bước riêng.

### 21.2. Cách kiểm thử nhiều instance

Tạo hai consumer cùng nhận messages của một correlation group. Nếu có shared store, cần cấu hình lock registry/transaction để tránh race. Gửi xen kẽ 1–4 từ hai instance, sau đó duplicate #2. Kiểm tra:

- Một logical sequence chỉ được release theo đúng order.
- Không có duplicate effect.
- Khi một node crash, node còn lại khôi phục được nhóm hoặc xử lý theo failover policy.
- Late messages được phân loại nhất quán, không phụ thuộc node nào nhận.

Không coi việc một test local trên JVM đơn chạy pass là bằng chứng xử lý phân tán an toàn.

## 22. Bài thực hành: phát hiện late message trong quy trình xuất kho

Xây dựng một IntegrationFlow theo dõi các bước của **một shipment** gồm 5 sự kiện:

| Sequence | Event type | Ý nghĩa |
| ---: | --- | --- |
| 1 | SHIPMENT_REQUESTED | Đã tiếp nhận yêu cầu |
| 2 | STOCK_CHECKED | Đã kiểm tra tồn kho |
| 3 | STOCK_RESERVED | Đã giữ hàng |
| 4 | LABEL_CREATED | Đã tạo nhãn giao |
| 5 | SHIPMENT_DISPATCHED | Đã bàn giao vận chuyển |

Input có thể được nhận theo thứ tự **3,1,2,5,4**, một hoặc nhiều message có thể bị broker redeliver, và message 4 có thể đến sau khi timeout.

### 22.1. Yêu cầu chức năng

1. Group được xác định theo **shipmentId + sequenceEpoch**.
2. Mỗi message có **eventId ổn định** và sequenceNumber trong khoảng 1..5.
3. Cấu hình Resequencer ở chế độ đợi toàn nhóm hoặc phát prefix liên tục, có test chứng minh lựa chọn.
4. Một message đến muộn **để lấp gap khi group còn active** phải đi tiếp theo đúng thứ tự.
5. Một bản lặp đến sau khi group completed phải được quan sát qua **discardChannel**, không phát bình thường.
6. Group timeout phải có chính sách rõ: freeze hoặc correction; không ngầm tạo một sequence thành công giả.
7. Retention completed group phải phù hợp khoảng redelivery thực tế.
8. Sau restart, side effect vẫn được bảo vệ bằng **idempotency ledger bền**.
9. Epoch mới được tạo khi shipment bắt đầu một chu kỳ nghiệp vụ khác, không phải chỉ do retry.
10. Test bao phủ duplicate, gap, timeout, late arrival và correlation collision.

### 22.2. Các bước thực hiện

1. Thiết kế ShipmentEvent và sequence manifest có expectedSequenceSize=5, schemaVersion và trusted tenantId.
2. Tạo helper sinh Message với các header correlationId, sequenceNumber và sequenceSize nội bộ.
3. Dựng IntegrationFlow từ một DirectChannel → Resequencer → QueueChannel.
4. Khai báo discardChannel có consumer/queue để ghi late event theo hợp đồng.
5. Viết test gửi 3,1,2,5,4 và xác minh output 1,2,3,4,5.
6. Gửi lại event #2 sau completion; kiểm tra không được emit lần nữa.
7. Tạo cấu hình releasePartialSequences(true), gửi 1,2,5,4,3; xác minh prefix 1,2 có thể đi trước, sau đó 3,4,5.
8. Thêm groupTimeout phù hợp và mô phỏng mất event #4; xác minh không báo whole sequence COMPLETE.
9. So sánh expireGroupsUponTimeout(false) với true khi event #4 tới sau timeout.
10. Thiết kế MessageGroupStore bền và retention completed group.
11. Viết ledger theo tenantId + shipmentId + epoch + eventId + actionId, test redelivery sau commit.
12. Thử restart khi metadata còn và sau khi metadata đã được reaper dọn.
13. Thử hai instance nhận xen kẽ events, kiểm tra locking/correlation.
14. Thêm metrics late duplicate, late first arrival, active groups và group cleanup.
15. Ghi runbook hướng dẫn operator quyết định freeze/correction/new epoch.

### 22.3. Thử nghiệm với ba trường hợp late

**Case A — Late but still needed:**

~~~text
Release policy: partial contiguous
Arrivals: 1,2,5,4,3
After 1,2: output 1,2
After 5,4: chờ 3
After 3: output 3,4,5
Expected: Không discard 3
~~~

**Case B — Duplicate after completed:**

~~~text
Release policy: wait full group
Arrivals: 3,1,2,5,4
Output: 1,2,3,4,5
Arrive #2 again with same correlationId:
Expected: Discard/audit; no second business effect
~~~

**Case C — Missing event arrives after expiry:**

~~~text
Arrivals: 1,2,3,5 (missing 4)
Group timeout -> EXPIRED
Arrive #4 after group closes
Expected: Late classification, no silent "complete" report
Next step: freeze or correction per business policy
~~~

Ở Case C, nếu operator muốn sửa kết quả cũ, việc tạo **correction workflow** phải được thể hiện rõ thay vì chỉ đẩy #4 vào một Resequencer mới và hy vọng sequence ban đầu tự hồi phục.

## 23. Các câu hỏi tự kiểm tra

1. Resequencer khác Aggregator ở output message như thế nào?
2. Vì sao việc message tới theo thứ tự 2,4,1,3 không tự đồng nghĩa event xảy ra sai thứ tự nghiệp vụ?
3. correlationId, sequenceNumber và sequenceSize có vai trò gì?
4. Khi nào nên dùng releasePartialSequences(false)?
5. Với releasePartialSequences(true), vì sao message 3 đến sau prefix 1,2 vẫn có thể là hợp lệ?
6. Vì sao một duplicate #2 sau khi group complete khác với một message #3 còn thiếu khi group ACTIVE?
7. Empty completed group metadata giúp ngăn điều gì?
8. Xóa group ngay sau completion có thể gây ra hậu quả gì cho late messages?
9. expireGroupsUponTimeout(false) và true khác nhau như thế nào về late arrival?
10. MessageGroupStoreReaper ảnh hưởng gì tới thời gian có thể phát hiện message muộn?
11. Tại sao in-memory store không bảo đảm late message bị discard sau restart?
12. Vì sao phải phân biệt eventId nghiệp vụ với MessageHeaders.ID?
13. Một message bị đưa tới discardChannel có đồng nghĩa luôn là input xấu không?
14. Có nên route discardChannel quay lại input Resequencer không? Vì sao?
15. Có thể sử dụng timestamp để quyết định một message chắc chắn là duplicate không?
16. Tại sao Resequencer không đủ để bảo đảm exactly-once side effects?
17. Khi nào cần correction/revision thay vì silent replay?
18. Nếu cùng group được xử lý bởi hai instance, cần bổ sung ownership/locking như thế nào?
19. Vì sao sequenceSize không phù hợp nếu upstream không biết lúc nào nguồn kết thúc?
20. Một sequence release đúng thứ tự có chứng minh external API đã được commit không?

## 24. Checklist trước khi đưa Resequencer vào production

- Đã xác định rõ **đơn vị correlation group** và epoch của sequence.
- SequenceNumber và sequenceSize được sinh hoặc xác minh bởi nguồn đáng tin.
- Đã xác định liệu **full release** hay **partial contiguous release** phù hợp nghiệp vụ.
- Đã kiểm thử một message đến sau để lấp gap mà vẫn được phát.
- Đã kiểm thử duplicate sau khi group completed được discard/audit.
- Có discardChannel thực sự được xử lý; không có loop tự quay về resequencer.
- Có groupTimeout/expiry/reaper nếu một message có thể không bao giờ đến.
- sendPartialResultOnExpiry được chọn theo hợp đồng; không đánh đồng partial với complete.
- expireGroupsUponTimeout được chọn sau khi đánh giá late arrival, không chỉ để giảm memory.
- Completed empty-group retention đủ cho redelivery window thực tế.
- Có giới hạn số group chờ, số message chờ và tài nguyên MessageGroupStore.
- Khi store là in-memory, đã hiểu rủi ro restart; khi store bền, đã test recovery.
- Nhiều instance có partition ownership hoặc shared store/lock phù hợp.
- Có **event identity và idempotency ledger** độc lập để bảo vệ side effects.
- Late first-time arrival được phân biệt với duplicate redelivery.
- Đã công bố chính sách freeze, correction hoặc new epoch cho kết quả đã phát.
- Log và metrics đo group tuổi lâu, pending gap, late discards và duplicate.
- Gateway, Router, Transformer, Filter và broker adapter không làm mất metadata cần thiết.
- Unit/integration tests bao phủ out-of-order, complete, partial, timeout, late, restart, concurrency.
- Runbook không hướng dẫn operator xóa group/replay trực tiếp khi chưa kiểm tra ledger.

**Kết luận:** “Late message sau khi sequence đã release” không phải một tình huống duy nhất. Nếu Resequencer mới phát **một prefix** nhưng group còn active, message đến sau để **lấp gap** vẫn cần được xử lý. Nếu cả nhóm đã **completed hoặc expired**, late message có thể bị discard nhờ **metadata empty group** còn được giữ. Nếu metadata đã bị dọn, message cũ có thể bị xem như thành viên của một nhóm mới, do đó **idempotency nghiệp vụ** và **correlation epoch** là lớp bảo vệ quan trọng. Thiết kế đúng release policy, retention, timeout, discard channel, correction và test theo từng trạng thái giúp Resequencer sắp xếp được message mà không làm mất sự kiện hợp lệ hay xử lý lặp tác động nghiệp vụ.

## Tài liệu tham khảo

- [Spring Integration Reference — Resequencer](https://docs.spring.io/spring-integration/reference/resequencer.html): nguyên tắc resequencing, releasePartialSequences, group expiry, empty group và late arrivals.
- [Spring Integration Reference — Aggregators and Resequencers (Java DSL)](https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html): ví dụ resequence() và aggregate() trong IntegrationFlow.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): correlation groups, group completion, MessageGroupStore, expiry và late arrivals.
- [Spring Integration API — ResequencerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ResequencerSpec.html): releasePartialSequences và các cấu hình kế thừa cho correlation handler.
- [Spring Integration API — SequenceSizeReleaseStrategy](https://docs.spring.io/spring-integration/api/org/springframework/integration/aggregator/SequenceSizeReleaseStrategy.html): semantics phát partial sequence và chiến lược release.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): DirectChannel, QueueChannel, ExecutorChannel và ảnh hưởng tới thứ tự.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): phân biệt ErrorMessage, errorChannel và message bị discard.
- [Spring Integration Reference — Idempotent Receiver](https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html): chống lặp message và những giới hạn của cơ chế idempotent advice.
- [Enterprise Integration Patterns — Resequencer](https://www.enterpriseintegrationpatterns.com/patterns/messaging/Resequencer.html): pattern nền tảng về phát thông điệp theo thứ tự.
