# MessageGroup metadata và message release trong Spring Integration Runtime

## Mục tiêu bài học

Trong **SPRING_INTEGRATION_RUNTIME**, một số endpoint xử lý message ngay khi nhận được; một số endpoint phải **giữ nhiều message lại** cho đến khi đủ điều kiện xử lý. Aggregator và resequencer là hai ví dụ tiêu biểu. Chúng cần biết message thuộc **nhóm nào**, **nhóm đã nhận bao nhiêu phần**, **khi nào được phát kết quả**, và **nên giữ metadata bao lâu** để xử lý message đến muộn.

Đó là vai trò của **MessageGroup**, **MessageGroupStore**, metadata của nhóm và cơ chế **message release**. Nếu quản lý không đúng, một nhóm có thể chờ vô hạn, bị phát sớm do message trùng, bị gom nhầm correlation, hoặc bị tạo lại sau khi đã hoàn thành.

Sau bài này, bạn có thể:

- Phân biệt **MessageStore**, **MessageGroupStore**, **MessageGroup** và **MessageGroupMetadata**.
- Đọc các metadata quan trọng: thời điểm tạo/cập nhật, kích thước, cờ hoàn tất, điều kiện nhóm và tiến độ resequencing.
- Giải thích **CorrelationStrategy**, **ReleaseStrategy** và **MessageGroupProcessor** trong runtime.
- Phân biệt **release**, **complete**, **expire**, **discard** và **partial release**; hiểu hành vi với message đến muộn.
- Cấu hình aggregator với message store, release strategy, timeout và chính sách dọn state.
- Chẩn đoán các vấn đề về thread, locking, transaction, retry, persistent store, idempotency và hiệu năng khi scale nhiều instance.

> **Điểm cốt lõi:** Nhóm đã được **release** không nhất thiết đã bị **xóa hoàn toàn khỏi store**. Metadata còn lại có thể chính là thứ giúp hệ thống nhận ra và loại bỏ một message đến muộn.

## 1. Vì sao runtime cần lưu MessageGroup?

Giả sử một đơn hàng chỉ được xác nhận khi đã có ba kết quả độc lập:

1. Thanh toán thành công.
2. Kiểm tra tồn kho thành công.
3. Xác nhận địa chỉ giao hàng.

Các kết quả có thể tới khác thứ tự và từ các thread hoặc instance khác nhau.

~~~mermaid
flowchart LR
    A["PaymentResult<br/>orderId=O-42"] --> C["CorrelationStrategy<br/>groupId=O-42"]
    B["InventoryResult<br/>orderId=O-42"] --> C
    D["AddressResult<br/>orderId=O-42"] --> C
    C --> S[("MessageGroupStore<br/>messages + metadata")]
    S --> R{"ReleaseStrategy<br/>đã đủ điều kiện?"}
    R -- "Chưa" --> S
    R -- "Đủ" --> P["MessageGroupProcessor"]
    P --> O["OrderReady"]
~~~

Một **MessageGroup** là tập hợp các Spring **Message<?>** có chung một **groupId**. Group ID thường lấy từ header **correlationId**, nhưng có thể được tạo bằng quy tắc riêng, chẳng hạn **orderId** trong header. Group ID là khóa của nhóm trong store, **không đồng nghĩa** với **MessageHeaders.ID** của từng message.

Ở ví dụ trên, sau khi chỉ nhận PaymentResult và InventoryResult, aggregator chưa được gửi OrderReady. Khi AddressResult đến, nó kiểm tra lại release strategy và có thể phát kết quả. Nếu thành phần phát kết quả bị lỗi, cần biết cách store, transaction và retry quyết định trạng thái nhóm.

### MessageStore và MessageGroupStore khác nhau thế nào?

| Thành phần | Chức năng | Trường hợp tiêu biểu |
| --- | --- | --- |
| **MessageStore** | Chiến lược lưu/truy xuất các Spring Message | Lưu message để xử lý sau, nền tảng cho các store chuyên biệt |
| **MessageGroupStore** | Quản lý message theo **groupId** và metadata của nhóm | Aggregator, resequencer, delayer/correlation endpoint |
| **ChannelMessageStore** | Các thao tác lưu trữ dành cho queue channel | QueueChannel được hỗ trợ bởi store |
| **MessageGroup** | Góc nhìn runtime về một nhóm: messages, groupId, trạng thái | ReleaseStrategy và MessageGroupProcessor |
| **MessageGroupMetadata** | Giá trị metadata của nhóm, không yêu cầu tải toàn bộ payload | Quan sát nhanh kích thước, timestamp, complete, condition |

Một store có thể hỗ trợ nhiều hợp đồng, nhưng **không nên cấu hình nhầm** một ChannelMessageStore cho chức năng đòi hỏi MessageGroupStore. Với hệ thống thật, việc dùng chung **vùng lưu trữ vật lý** cũng không có nghĩa mọi aggregator nên chia sẻ cùng một **MessageGroupStore instance** và expiry callback.

## 2. Metadata của một MessageGroup gồm những gì?

Các API liên quan thuộc package **org.springframework.integration.store**. Một MessageGroup lưu message và thông tin điều khiển vòng đời. **MessageGroupMetadata** là value object mô tả metadata, được truy xuất qua:

~~~java
MessageGroupMetadata metadata =
        messageGroupStore.getGroupMetadata("O-42");
~~~

Lời gọi này có thể lấy trạng thái nhóm **mà không cần tải tất cả payload của nhóm**, hữu ích khi nhóm có hàng nghìn message nằm ở DB/Redis/MongoDB.

| Metadata / API | Ý nghĩa | Cách dùng phù hợp |
| --- | --- | --- |
| **groupId** | Khóa logic dùng để lấy nhóm trong store | Tìm theo orderId hoặc correlationId; là tham số của **getGroupMetadata(groupId)** |
| **size()** | Số message hiện có trong nhóm | Theo dõi backlog hoặc điều kiện đếm đơn giản |
| **isComplete()** | Nhóm được đánh dấu hoàn tất | Giúp ngăn thêm message vào nhóm đã kết thúc; liên quan xử lý late arrival |
| **getTimestamp()** | Thời điểm tạo nhóm, epoch milliseconds | Đo tuổi nhóm từ khi được lập |
| **getLastModified()** | Thời điểm nhóm được cập nhật gần nhất | Đánh giá nhóm đang hoạt động hay bị bỏ quên |
| **getCondition()** | Chuỗi điều kiện nghiệp vụ/tóm tắt trạng thái, nếu được cấu hình | ReleaseStrategy có thể dựa vào metadata thay vì quét toàn bộ message |
| **getMessageIds()** | Danh sách ID message theo metadata | Điều tra group; **không** phải danh sách payload |
| **getLastReleasedMessageSequenceNumber()** | Tiến độ sequence đã phát, phục vụ resequencing | Khôi phục hoặc chẩn đoán resequencer |

**Lưu ý:** Group ID là khóa của store, không phải một phương thức **getGroupId()** của lớp **MessageGroupMetadata**. Nếu cần groupId trực tiếp từ đối tượng nhóm, dùng **MessageGroup.getGroupId()**.

### Ví dụ đọc metadata để quan sát

~~~java
import java.time.Instant;
import org.springframework.integration.store.MessageGroupMetadata;
import org.springframework.integration.store.MessageGroupStore;

public final class GroupInspector {
    private final MessageGroupStore store;

    public GroupInspector(MessageGroupStore store) {
        this.store = store;
    }

    public void inspect(String orderId) {
        MessageGroupMetadata metadata = store.getGroupMetadata(orderId);
        if (metadata == null) {
            System.out.println("No group for " + orderId);
            return;
        }

        System.out.printf(
                "group=%s size=%d complete=%s created=%s modified=%s condition=%s%n",
                orderId,
                metadata.size(),
                metadata.isComplete(),
                Instant.ofEpochMilli(metadata.getTimestamp()),
                Instant.ofEpochMilli(metadata.getLastModified()),
                metadata.getCondition());
    }
}
~~~

Đây là đoạn **đọc trạng thái**, không phải cách phát nhóm. Metadata bạn vừa đọc là một **snapshot**: group có thể thay đổi bởi thread/instance khác ngay sau đó. Không viết logic kiểu “đọc size từ inspector → nếu bằng 3 thì tự gửi output” vì thao tác kiểm tra và phát không được đồng bộ với aggregator.

### Metadata nào không cho biết toàn bộ sự thật?

- **size() = 3** không bảo đảm đó là **ba bước nghiệp vụ khác nhau**. Có thể cả ba đều là PaymentResult bị giao lại với các Message ID khác nhau.
- **isComplete() = true** không bảo đảm downstream đã commit side effect nghiệp vụ. Nó chỉ nói về trạng thái **nhóm** theo store/endpoint.
- **getLastModified()** không thay thế hạn chót SLA nghiệp vụ. Thời gian còn phụ thuộc lịch poll, scheduler, timeout và độ trễ hạ tầng.
- Danh sách **Message ID** không phải danh sách **eventId/idempotencyKey**; một sự kiện phát lại có thể tạo Spring Message mới.
- **condition** là dữ liệu theo quy tắc ứng dụng/framework, không tự động có nghĩa là một biểu thức đang được thực thi hay đã thỏa mãn.

## 3. CorrelationStrategy quyết định nhóm nào nhận message

Hợp đồng cốt lõi:

~~~java
public interface CorrelationStrategy {
    Object getCorrelationKey(Message<?> message);
}
~~~

Mặc định, aggregator lấy khóa tương quan từ header **correlationId**. Có thể thay bằng quy tắc như **headers['orderId']**. Mọi message của đơn O-42 phải có cùng group ID nếu chúng cần hội tụ.

~~~text
PaymentResult  headers['orderId'] = O-42 ┐
InventoryResult headers['orderId'] = O-42 ├─ groupId O-42
AddressResult  headers['orderId'] = O-42 ┘

PaymentResult  headers['orderId'] = O-43 ── groupId O-43
~~~

### Các lỗi correlation phổ biến

- Một transformer tự tạo Message mới và **quên giữ orderId/correlationId**.
- Dùng **MessageHeaders.ID** của từng message làm khóa nhóm, khiến mỗi message thành một group riêng.
- Hai flow khác nhau cùng dùng khóa ngắn như O-42 trong một vùng store chung nên **trộn nhóm**.
- Một business key bị tái sử dụng cho phiên xử lý mới trong khi metadata của nhóm cũ vẫn còn.
- Tạo group key từ giá trị có thể thay đổi, như timestamp hoặc request attempt, khiến retry vào nhóm khác.

Nên định nghĩa rõ **namespace của khóa**, ví dụ **order-confirmation:v1:O-42** trong môi trường có nhiều loại aggregator. Đặc biệt với persistent store, thay đổi hàm tạo correlation key khi deploy phiên bản mới có thể khiến message cũ không bao giờ được release.

**Trường hợp thiếu key:** Một message không có correlationId/orderId như mong đợi phải được xác định là dữ liệu lỗi, phân luồng hoặc được enrich hợp lệ trước aggregator. Không tự gán một groupId dùng chung như UNKNOWN, vì có thể gom nhầm nhiều đơn hàng.

## 4. ReleaseStrategy quyết định lúc nào nhóm được phát

Hợp đồng:

~~~java
public interface ReleaseStrategy {
    boolean canRelease(MessageGroup group);
}
~~~

Sau khi message mới vào nhóm, aggregator đánh giá release strategy. Khi trả **true**, **MessageGroupProcessor** biến nội dung nhóm thành một output message hoặc kết quả phù hợp.

Một **ReleaseStrategy** quyết định **đủ điều kiện phát chưa**, còn **MessageGroupProcessor** quyết định **phát nội dung gì**. Không đặt side effect như gửi email hoặc gọi thanh toán trong **canRelease()**: strategy có thể được gọi lại trong các lần nhận message, timeout hoặc retry.

### Chiến lược mặc định: sequence headers

Với nhóm message đến từ splitter, Spring Integration thường sử dụng các header:

~~~text
correlationId = group-42
sequenceNumber = 1 / 2 / 3
sequenceSize = 3
~~~

Mặc định aggregator dùng **SimpleSequenceSizeReleaseStrategy**, quyết định release khi đủ số lượng theo sequence. Từ Spring Integration 5.0, đây là mặc định thường gặp khi không yêu cầu partial sequence release.

| Lần nhận | Sequence numbers đã đến | Kích thước | Kết quả |
| --- | --- | ---: | --- |
| 1 | [2] | 1 | Chưa release |
| 2 | [2, 1] | 2 | Chưa release |
| 3 | [2, 1, 3] | 3 | Có thể release |

**Rủi ro:** Một cơ chế release dựa trên số lượng có thể nhầm **duplicate** với một phần còn thiếu. **SimpleSequenceSizeReleaseStrategy** được tối ưu cho hiệu năng nhưng không cung cấp cùng cách kiểm tra số sequence trùng như chiến lược **SequenceSizeReleaseStrategy** cũ. Nếu nguồn có redelivery hoặc mất message, cần cơ chế deduplication thích hợp, release strategy chặt hơn hoặc chính sách partial release rõ ràng.

### Không dùng size() == 3 một cách máy móc

Với ví dụ ba bước nghiệp vụ, đây là biểu thức **dễ sai**:

~~~text
release-strategy-expression="size() == 3"
~~~

Nó có thể phát khi nhóm chứa **hai bản thanh toán trùng + một bản tồn kho** mà vẫn thiếu địa chỉ. Ngoài ra, nếu nhóm đã có hơn ba phần vì retry, điều kiện **== 3** có thể không còn đúng.

An toàn hơn là kiểm tra **đủ ba loại kết quả duy nhất** và bảo vệ chống duplicate nghiệp vụ. Ví dụ release strategy đọc từng phần:

~~~java
import java.util.EnumSet;
import java.util.Set;
import org.springframework.integration.aggregator.ReleaseStrategy;
import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

enum Step { PAYMENT, INVENTORY, ADDRESS }

record OrderPart(String orderId, String eventId, Step step) {}

public final class RequiredOrderSteps implements ReleaseStrategy {
    private static final Set<Step> REQUIRED = EnumSet.allOf(Step.class);

    @Override
    public boolean canRelease(MessageGroup group) {
        Set<Step> arrived = EnumSet.noneOf(Step.class);
        for (Message<?> message : group.getMessages()) {
            if (!(message.getPayload() instanceof OrderPart part)) {
                return false; // Payload không đúng hợp đồng.
            }
            arrived.add(part.step());
        }
        return arrived.containsAll(REQUIRED);
    }
}
~~~

**Giới hạn của ví dụ:** Nó giải quyết điều kiện “đủ loại bước”, nhưng **chưa loại bỏ các eventId trùng** và **chưa chọn kết quả hợp lệ khi cùng bước xuất hiện nhiều lần**. Bước xử lý đầu vào cần xác thực dữ liệu và có idempotency; output processor phải quy định xử lý duplicate/conflicting result.

Đối với nhóm lớn, việc đọc **getMessages()** sau mỗi message có thể tạo chi phí I/O và deserialize đáng kể, nhất là với persistent store. Khi đó nên dùng metadata/condition được cập nhật an toàn hoặc thiết kế lại cách tổng hợp để không quét toàn nhóm liên tục.

## 5. Cấu hình aggregator và message store

Một cấu hình XML tiêu biểu thể hiện đầy đủ correlation, release và vòng đời nhóm:

~~~xml
<bean id="orderGroupStore"
      class="org.springframework.integration.store.SimpleMessageStore"/>

<bean id="requiredOrderSteps"
      class="com.example.integration.RequiredOrderSteps"/>

<int:aggregator
    id="orderAggregator"
    input-channel="orderParts"
    output-channel="orderReady"
    message-store="orderGroupStore"
    correlation-strategy-expression="headers['orderId']"
    release-strategy="requiredOrderSteps"
    discard-channel="lateOrRejectedParts"
    expire-groups-upon-completion="false"/>
~~~

Điều kiện của ví dụ:

1. Bean **RequiredOrderSteps** là class Java phía trên. Trong project thật cần tổ chức package/import phù hợp và cấu hình Spring Integration XML namespace.
2. Producer gửi **OrderPart** với **orderId** header. Channel **orderParts**, **orderReady**, **lateOrRejectedParts** và các consumer tương ứng phải được định nghĩa.
3. **SimpleMessageStore** là store trong RAM, phù hợp demo/test; restart JVM sẽ mất state.
4. Mặc định aggregator sẽ dùng output processor phù hợp để kết hợp các message/payload. Nghiệp vụ phải xác định một **OrderReady** rõ ràng thay vì cho downstream tự đoán kết quả từ danh sách phần.
5. **expire-groups-upon-completion="false"** giữ metadata sau khi release hoàn chỉnh, giúp từ chối phần đến muộn cùng correlation key. Nó cần chính sách dọn metadata về sau.

Đây là **cấu hình minh họa phần aggregator**, chưa phải ứng dụng chạy độc lập; không mặc định áp dụng nguyên xi cho mọi protocol adapter, schema hoặc Spring Integration version.

### Khi cần store persistent

Một số implementation có thể dùng:

| Store | Ưu điểm | Cần kiểm soát |
| --- | --- | --- |
| **SimpleMessageStore** | Thiết lập nhẹ, không cần hạ tầng khác | Mất dữ liệu khi restart, RAM tăng theo backlog |
| **JdbcMessageStore** | Lưu message/group trong RDBMS | Schema, transaction, serialization, index, contention, cleanup |
| **RedisMessageStore** | Truy cập qua Redis, chia sẻ giữa instance | Persistence configuration, serialization, locking, TTL/cleanup |
| **MongoDbMessageStore** | Lưu document, mở rộng dữ liệu nhóm | Collection/index, schema, transaction/concurrency, kích thước document |

Persistent store giúp giảm rủi ro mất trạng thái **đã được ghi bền vững**, nhưng không tự bảo đảm “exactly once”. Nếu payload hoặc header không serialize được, việc lưu/đọc lại có thể thất bại hoặc mất metadata. Đặc biệt nên kiểm tra **replyChannel/errorChannel**, header chứa Java object hoặc tài nguyên transport vì các object này có thể chỉ hợp lệ trong JVM cũ.

**Phân vùng store:** Nếu hai aggregator có logic expiry khác nhau, nên dùng instance/region/collection riêng, hoặc ít nhất thiết kế group ID và callback một cách độc lập. Không dùng chung **MessageGroupStore instance** giữa nhiều correlation endpoint có callback expiry theo cách không được hỗ trợ.

## 6. Release, complete, expire: ba thao tác khác nhau

Trong Spring Integration, vòng đời nhóm không đơn giản là “nhận đủ → xóa”.

~~~mermaid
stateDiagram-v2
    [*] --> Accumulating: Message đầu tiên
    Accumulating --> Accumulating: Thêm message, chưa đạt release
    Accumulating --> Released: ReleaseStrategy=true
    Released --> Completed: Đánh dấu group complete
    Completed --> Retained: Giữ metadata, loại late message
    Completed --> Removed: expire-groups-upon-completion=true
    Retained --> Removed: Expiry/reaper về sau
    Accumulating --> TimedOut: Timeout hoặc reaper
    TimedOut --> Partial: Phát partial nếu cấu hình
    TimedOut --> Discarded: Bỏ partial nếu cấu hình
    Partial --> Removed: Chính sách expire upon timeout
    Discarded --> Removed: Chính sách expire upon timeout
~~~

Sơ đồ diễn giải các **trường hợp thường gặp**. Framework cũng hỗ trợ partial releases, resequencing và chiến lược force-complete nên chi tiết trạng thái có thể khác tùy endpoint/phiên bản.

| Khái niệm | Ý nghĩa | Metadata sau đó |
| --- | --- | --- |
| **Release** | Nhóm đã thỏa release strategy, các message chưa phát được chuyển cho output processor | Các message đã phát có thể được lấy khỏi group; trạng thái còn tùy group complete hay chưa |
| **Complete** | Nhóm được đánh dấu không nhận thêm message nữa | Metadata có thể vẫn tồn tại dù group rỗng |
| **Expire/remove** | Xóa hoàn toàn nhóm khỏi store | Message cùng groupId đến sau có thể mở nhóm **mới** |
| **Discard** | Không đưa message (hoặc nhóm hết hạn) vào output nghiệp vụ; có thể gửi sang discard channel | Tùy chính sách expire/retain |
| **Partial release** | Phát kết quả của nhóm chưa đủ phần do timeout/chiến lược đặc biệt | Downstream phải biết đó là **kết quả thiếu**, không coi như đã đủ |

### Giữ metadata để chặn late arrival

Nếu **expireGroupsUponCompletion=false** (mặc định cho normal completion), sau khi một nhóm đã hoàn tất, store có thể giữ một **empty completed group**. Khi bản tin cùng khóa tới quá muộn, aggregator nhận ra nhóm đã hoàn tất và chuyển tới **discard channel** nếu có, thay vì phát một kết quả mới.

Nếu **expireGroupsUponCompletion=true**, nhóm hoàn tất bị xóa ngay. Message đến sau với groupId cũ **có thể tạo nhóm mới**. Điều này có thể đúng với bài toán nhóm lặp theo phiên, nhưng rất nguy hiểm nếu groupId gắn một đơn hàng duy nhất và message bị redeliver.

**Ví dụ:**

~~~text
09:00  O-42 nhận PAYMENT + INVENTORY + ADDRESS → phát OrderReady.
09:00  Metadata O-42 được giữ ở trạng thái completed, messages có thể rỗng.
09:05  Broker redeliver PAYMENT của O-42.
       → Group completed: đưa vào discard/late handling.

Nếu metadata O-42 đã bị xóa:
09:05  PAYMENT có thể tạo một group O-42 mới, chờ thêm phần khác.
       → Tăng backlog và có rủi ro xử lý lặp khi các phần khác cũng tới lại.
~~~

Do đó phải chọn **thời hạn giữ metadata** theo cửa sổ redelivery, retry, broker retention và nghiệp vụ. Không giữ metadata vô hạn nếu số lượng group lớn; nhưng cũng không xóa quá sớm khi còn có thể nhận late message.

## 7. Group timeout, MessageGroupStoreReaper và partial result

Không phải nhóm nào cũng nhận đủ message. Có thể một dịch vụ downstream không gửi kết quả, một message bị filter hoặc sequence bị thiếu.

Hai cơ chế timeout thường gặp:

| Cơ chế | Phạm vi | Thời điểm |
| --- | --- | --- |
| **group-timeout / group-timeout-expression** | Lên lịch cho **từng group** khi không đạt release strategy | Thường được tính từ lần message gần nhất; expression có thể khai báo quy tắc riêng |
| **MessageGroupStoreReaper** | Quét các nhóm trong **store** theo lịch | Lịch chạy và ngưỡng tuổi nhóm quyết định khi callback expiry được gọi |

Khi timeout buộc group hoàn tất, release strategy có thể được hỏi lại. Nếu vẫn chưa đủ và **send-partial-result-on-expiry=true**, aggregator có thể phát một kết quả **partial**. Nếu false, phần còn thiếu được xử lý theo chính sách discard/expire. Không được mặc định kết quả partial là “đơn hàng hoàn chỉnh”.

Ví dụ cấu hình có chủ đích:

~~~xml
<int:aggregator
    id="orderAggregator"
    input-channel="orderParts"
    output-channel="orderReady"
    message-store="orderGroupStore"
    correlation-strategy-expression="headers['orderId']"
    release-strategy="requiredOrderSteps"
    group-timeout="30000"
    send-partial-result-on-expiry="false"
    expire-groups-upon-completion="false"
    expire-groups-upon-timeout="false"
    discard-channel="lateOrRejectedParts"/>
~~~

Ở cấu hình này, khi timeout mà group chưa đủ phần, logic thiên về **không phát OrderReady thiếu dữ liệu**. Metadata nhóm hết hạn được giữ theo chính sách timeout để quan sát và từ chối late arrival; cần cấu hình thêm quá trình cleanup. **expire-groups-upon-timeout** là tùy chọn độc lập với **expire-groups-upon-completion**; các giá trị mặc định và khả năng cấu hình có thể thay đổi theo phiên bản.

Đây là **một biến thể** của cấu hình ở phần trước, không phải tạo hai aggregator cùng dùng một store trong ứng dụng thực tế.

### Reaper chạy theo lịch, không có độ chính xác tuyệt đối

Nếu đặt ngưỡng expiry 10 phút nhưng reaper chỉ chạy mỗi giờ, một group có thể tồn tại lâu hơn ngưỡng. Ngược lại, expire quá sớm làm mất trạng thái chống late arrival. Cần đặt lịch reaper theo SLA, số group chờ và chi phí quét store.

Với persistent store, ngoài reaper còn phải xem **orphaned groups**: nhóm được lưu từ trước nhưng application restart, timeout timer trong process không còn. Spring Integration có các tùy chọn **expireTimeout/expireDuration** cho correlation handler ở những phiên bản hỗ trợ, giúp quét state cũ. Không nên tin rằng tất cả timer in-memory được khôi phục nguyên vẹn chỉ vì store bền vững.

**Lưu ý về lỗi:** TaskScheduler kích hoạt expiry có thể chạy trên thread khác. Nếu expiration callback phát message rồi downstream ném exception, lỗi cần được quan sát ở scheduler/error handling thích hợp. Exception trong callback không có nghĩa mọi dữ liệu đã phát hoặc xóa khỏi store sẽ tự rollback.

## 8. Group condition: metadata phục vụ release hiệu quả

Từ Spring Integration **5.5**, **MessageGroup** hỗ trợ trường **condition** dạng String. Tùy ứng dụng, đây có thể là số lượng kỳ vọng, mốc kết thúc hoặc trạng thái tóm tắt. API của store:

~~~java
messageGroupStore.setGroupCondition(groupId, condition);
~~~

Và release strategy có thể đọc:

~~~java
String condition = group.getCondition();
~~~

Spring Integration cũng cung cấp cơ chế **groupConditionSupplier** trên correlating handler để tính lại condition khi message mới được thêm, dựa trên message và condition hiện tại. Cơ chế này cho phép cập nhật metadata **cùng luồng xử lý nhóm** thay vì mỗi lần release phải tải và duyệt toàn bộ payload.

**Ví dụ ứng dụng:** Một splitter đọc file có marker cuối cho biết **lineCount**. Marker cuối có thể đến trước các dòng do executor xử lý song song. Khi marker tới, condition có thể chứa số dòng kỳ vọng; release strategy chỉ cần so sánh tiến độ đã nhận với số lượng đó. Các thành phần hỗ trợ như **FileMarkerReleaseStrategy** áp dụng ý tưởng này.

~~~text
groupId = import-file-42
condition = "expectedLines=1000"
messages hiện có = 995

ReleaseStrategy:
    Chưa release nếu mới có 995/1000 dòng hợp lệ.
    Release khi đã đủ 1000 dòng riêng biệt theo quy tắc nghiệp vụ.
~~~

**Phải tự định nghĩa cách mã hóa/đọc condition**. Framework không tự biến mọi String condition thành boolean. Khi sử dụng số lượng đã nhận, cần xét duplicate: condition và size chỉ chính xác nếu nguồn và store đảm bảo không đếm hai lần cùng bản ghi.

Với nhóm cực lớn, việc dùng condition hoặc metadata có thể giúp tránh quét toàn bộ group; tuy nhiên cập nhật metadata mỗi message cũng tạo write load. Đo độ trễ và contention trước khi tối ưu.

## 9. Persistent MessageGroupStore: metadata và payload có thể có đường truy cập khác nhau

Một persistent store có thể lưu **metadata nhóm** và **các message thực tế** theo cấu trúc riêng. **getGroupMetadata(groupId)** cho phép đọc thông tin nhóm mà không nhất thiết deserialize toàn bộ payload. Điều này khác với **getMessageGroup(groupId)** hoặc **getMessagesForGroup(groupId)**.

Với nhiều implementation persistent, Spring Integration hỗ trợ **lazy loading**. Từ phiên bản **5.5**, MessageGroupStore còn có:

~~~java
try (var stream = store.streamMessagesForGroup(groupId)) {
    stream.forEach(message -> {
        // Xử lý/đếm theo mục đích; tránh giữ cả nhóm trong RAM.
    });
}
~~~

Đối với persistent store, phải **đóng Stream** để giải phóng tài nguyên truy xuất của DB/client. Không dùng stream khi mục tiêu chỉ là đọc số lượng/complete; API metadata thường phù hợp hơn.

### Một số tình huống khi restart/deploy

**1. Nhóm dang dở:** Store vẫn chứa các phần đã đến. Ứng dụng mới cần cùng **correlation strategy**, schema/serializer tương thích và cơ chế expiry/release hoạt động sau restart.

**2. Header không serialize được:** Một Message chứa transport object, replyChannel hoặc exception có thể không thể lưu như dự kiến. Cần header mapping, channel name hoặc cấu hình serializer phù hợp; test đọc lại dữ liệu đã ghi bởi phiên bản cũ.

**3. Version schema thay đổi:** Class payload đổi package/trường khiến deserialization message cũ thất bại. Cần schema evolution, migration hoặc hợp đồng định dạng ổn định.

**4. Store được chia sẻ:** Hai instance cùng đọc một group có thể cùng đánh giá release. **Locking, transaction và duplicate side effect** phải được xử lý phối hợp.

**5. Nhóm đã complete vẫn chiếm tài nguyên:** Metadata rỗng được giữ để loại late messages; cần TTL/dọn state mà không làm hỏng cửa sổ chống lặp.

## 10. Thread safety, LockRegistry và transaction khi release

Hai producer có thể gửi message vào cùng **DirectChannel** đồng thời. **ExecutorChannel** còn cho phép xử lý ở nhiều worker; poller có thể có nhiều task. Khi scale nhiều replica, các message cùng orderId có thể đến **hai JVM khác nhau**.

~~~mermaid
flowchart TD
    A["Instance A / worker 1"] --> K["groupId=O-42"]
    B["Instance B / worker 2"] --> K
    K --> L["LockRegistry phù hợp"]
    L --> S[("Shared MessageGroupStore")]
    S --> R["Đánh giá release + cập nhật group"]
    R --> O["Output processor"]
~~~

Với một JVM, đồng bộ theo group có thể đủ để bảo vệ state trong bộ nhớ. Với nhiều JVM, **DefaultLockRegistry** chỉ cung cấp lock **nội bộ**; cần một **LockRegistry phân tán** phù hợp hạ tầng nếu nhiều instance cùng thao tác trên group chung. Spring Integration hỗ trợ cấu hình LockRegistry cho correlating handlers và trong những phiên bản mới có hỗ trợ lock ở lớp store.

**Đừng giả định store persistent đã thay thế locking.** Store bảo quản dữ liệu, lock phối hợp thao tác đồng thời, còn transaction quyết định atomicity và rollback của các thay đổi được bao phủ. Cần kiểm thử:

- Hai message cùng groupId vào gần như đồng thời.
- Hai instance cùng thấy nhóm sắp đủ điều kiện release.
- Một instance chết giữa lưu message, đánh dấu complete và gửi output.
- Một output bị retry sau khi store đã cập nhật metadata.

Ngay cả khi group được khóa đúng, **một output message có thể bị phát lại** khi caller/broker retry hoặc khi kết quả gửi ra hệ thống ngoài không rõ ràng. Downstream vẫn cần **business idempotency**, ví dụ unique constraint theo **orderId + eventType + version**.

### Transaction boundary không chạy xuyên executor

Nếu poller bắt đầu transaction ở thread A rồi gửi sang **ExecutorChannel**, thread B xử lý aggregator về sau không tự tham gia transaction của thread A. Muốn nhóm và output được xử lý bền vững, cần thiết kế transaction **ở bên consumer phù hợp**, xác định store/broker/resource nào được bao phủ và cách khôi phục khi gửi output lỗi.

**MessageGroupStore** không tự làm các lời gọi HTTP hoặc publish broker trở thành một distributed transaction với DB. Dùng transactional outbox, inbox/idempotency và đối soát khi kết quả gửi có thể không chắc chắn.

## 11. Retry, message release và lỗi correlation

Một failure có thể xảy ra trước hoặc sau khi nhóm được release:

| Lỗi | Tác động có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Source redeliver cùng một phần | Group có thể nhận message trùng với Message ID mới | Dùng **eventId/idempotencyKey**, kiểm tra duplicate trước khi đếm |
| Transformer mất correlationId | Message vào group khác hoặc bị từ chối | Giữ key ổn định, kiểm tra headers trước aggregator |
| Output processor thất bại | Không tạo được kết quả nghiệp vụ | Exception/error flow/transaction phải được thiết kế; kiểm thử store state sau lỗi |
| Timeout khi chưa đủ phần | Group chờ mãi hoặc bị partial release | Chọn SLA, sendPartialResultOnExpiry và discard/recovery rõ ràng |
| Group complete nhưng phần khác đến muộn | Có thể discard hoặc tạo group mới khi metadata đã xóa | Chọn retention phù hợp, cung cấp **discard channel** |
| App restart giữa chừng | Timer/group state có thể cần được khôi phục | Persistent store + cơ chế purge/reaper/reconcile |
| Hai instance đánh giá release đồng thời | Có thể phát output trùng hoặc cập nhật group cạnh tranh | Distributed LockRegistry, transaction, downstream idempotency |

**Đặc biệt:** Retry ở handler, broker redelivery và replay từ DLQ là **các tầng khác nhau**. Nếu mỗi tầng thử lại toàn bộ flow, bạn có thể thấy nhiều lần release hoặc nhiều message cùng group key. Mỗi lần retry nên giữ **business correlation**, nhưng tạo attempt ID riêng nếu cần chẩn đoán.

Với error flow, đừng chỉ đọc headers của **ErrorMessage** rồi giả định có correlation. Hãy tìm **originalMessage** hoặc **MessagingException.failedMessage** khi có, đồng thời giữ requestId/orderId trong FailureJournal bền vững.

### Tái sử dụng groupId có chủ đích

Nếu nghiệp vụ cần chạy **nhiều đợt tổng hợp cho cùng orderId**, không nên chỉ dùng orderId làm group key. Một khóa như **orderId + workflowVersion/runId** giúp phân biệt hai lần chạy, trong khi metadata của nhóm cũ vẫn còn và late events không bị gom nhầm.

Không xóa metadata của nhóm chỉ để “cho phép xử lý lại” mà chưa có chiến lược chống duplicate; cách đó có thể làm mất bằng chứng group đã từng hoàn tất.

## 12. Quan sát hiệu năng và trạng thái runtime

Khi vận hành aggregator, cần nhìn cả **tốc độ message đến**, **thời gian chờ release**, **trạng thái store** và **đường lỗi**:

| Metric/tín hiệu | Gợi ý chẩn đoán |
| --- | --- |
| Số group **incomplete** | Group chờ đầu vào; tăng liên tục có thể là thiếu phần hoặc lỗi correlation |
| Tuổi group P95/P99, lastModified age | Nhận diện group cũ không có tiến triển |
| Group size và phân phối kích thước | Phát hiện duplicate, quá nhiều phần, memory pressure |
| Release rate và latency | Có bottleneck trong release strategy hoặc output processor không? |
| Partial/timeout/discard/late arrival counts | Kiểm tra SLA, expiry policy và tỷ lệ input đến muộn |
| Store read/write latency, serialization failures | DB/Redis/MongoDB đang quá tải hoặc schema lỗi |
| Lock wait time / contention | Quá nhiều message cùng key hay nhiều instance tranh lock |
| Retry và output duplicate | Transaction, redelivery, idempotency chưa phù hợp |
| Orphaned/retained completed groups | Cleanup thiếu hoặc retention quá dài |

Một log cấu trúc có thể chứa:

~~~text
flow=orderAggregation endpoint=orderAggregator
groupId=order-confirmation:v1:O-42
orderId=O-42 correlationId=checkout-42
groupSize=2 expectedStages=3 groupComplete=false
groupAgeMs=42000 lastModifiedAgeMs=12000
decision=WAITING_FOR_ADDRESS thread=aggregator-worker-2
~~~

Log cần phân biệt **groupId**, **messageId**, **businessId** và **attemptId**. Tránh ghi toàn bộ payload chứa thông tin cá nhân hoặc bí mật. Nếu release strategy phải deserialize hàng nghìn message mỗi lần, ưu tiên cấu trúc metadata/condition thích hợp và đo CPU, allocation, DB I/O trước khi tăng executor pool.

### Những câu hỏi nên hỏi khi nhóm không release

1. Message của nhóm có **cùng correlation key** và đúng namespace không?
2. Đã nhận đủ phần **duy nhất** hay chỉ đủ số lượng tính cả duplicate?
3. **ReleaseStrategy** đang được gọi không, và trả false vì điều kiện nào?
4. **Metadata** có complete/condition/timestamp như kỳ vọng?
5. Group đã timeout, bị discard hoặc đã bị xóa rồi tạo lại chưa?
6. Persistent store có đọc/ghi thành công và khôi phục sau restart không?
7. Có lock contention, error flow hoặc transaction rollback không?
8. Splitter/filter ở trước aggregator có bỏ message làm **sequenceSize** không còn phù hợp?

## 13. Bài thực hành: tổng hợp ba phần đơn hàng

**Đề bài:** Ba nguồn PAYMENT, INVENTORY, ADDRESS gửi message bất đồng bộ. Một số message bị redeliver; có hai instance ứng dụng chạy chung persistent store. SLA cho mỗi đơn là 2 phút. Nếu thiếu phần, không được phát **OrderReady** đầy đủ.

### Thiết kế tham chiếu

1. **Correlation:** Dùng khóa ổn định **order-confirmation:v1:{orderId}:{runId}**; kiểm tra business key trước aggregator.
2. **Deduplication:** Mỗi phần mang **eventId**. Lưu/check eventId theo cách atomic/idempotent để một redelivery không được tính là bước mới.
3. **Store:** Dùng **MessageGroupStore persistent** đã cấu hình schema, serializer và vùng dữ liệu riêng.
4. **Release:** Chỉ phát khi tồn tại đủ ba loại kết quả hợp lệ. Không dùng size() == 3 nếu nguồn có duplicate.
5. **Timeout:** Sau 2 phút, ghi một **OrderAssemblyTimedOut** hoặc chuyển trạng thái vào quarantine; không tự phát OrderReady thiếu phần.
6. **Late arrivals:** Giữ metadata đã complete/timed-out đủ lâu so với cửa sổ redelivery rồi dọn có kiểm soát.
7. **Concurrency:** Phối hợp lock theo groupId trên các instance và dùng transaction phù hợp.
8. **Output:** Xử lý idempotent theo **orderId + runId**, lưu outbox event nếu gửi broker phải phục hồi sau crash.
9. **Monitoring:** Theo dõi group chờ quá hạn, group thiếu stage, duplicate, expiry callback failures và backlog.

### Bộ ca kiểm thử cần có

| Ca | Input | Kỳ vọng |
| --- | --- | --- |
| Thứ tự bất kỳ | INVENTORY → PAYMENT → ADDRESS | Chỉ một OrderReady sau phần thứ ba |
| Thiếu phần | PAYMENT + INVENTORY | Không release trước timeout |
| Message trùng | PAYMENT (event E1) hai lần, INVENTORY | Không nhận nhầm thành đủ ba bước |
| Late arrival | ADDRESS đến sau group đã kết thúc | Đi đúng nhánh discard/quarantine; không tự tạo nghiệp vụ trùng |
| Hai group độc lập | O-42 và O-43 xen kẽ | Không trộn payload/correlation |
| Hai instance cùng key | Gửi đồng thời các phần của O-42 | Không lost update, không phát trùng |
| Store restart | Lưu 2/3 phần rồi restart | Khôi phục đúng 2 phần và chỉ release sau phần thứ ba |
| Hết timeout | Chỉ nhận 2/3 phần đến hết SLA | Có kết quả timeout rõ ràng, có cách xử lý partial state |
| Output failure | Nhóm đủ nhưng consumer ném exception | Error/transaction/recovery có dấu vết, không làm mất trạng thái âm thầm |
| Schema migration | Message từ phiên bản trước còn trong store | Đọc lại được hoặc có quy trình migration/quarantine |

**Câu hỏi tự kiểm tra:** Sau khi aggregator đã phát OrderReady, metadata cho group bị giữ lại nhưng size() = 0. Đây có phải dữ liệu hỏng không?

**Giải thích:** **Không nhất thiết.** Một **completed empty group** có thể được giữ lại chủ đích để nhận diện và discard message đến muộn. Cần xem **isComplete()**, chính sách **expireGroupsUponCompletion** và lịch cleanup, thay vì chỉ nhìn size().

## 14. Checklist trước khi đưa vào production

- Đã chọn đúng store cho aggregator (**MessageGroupStore**) và biết state có bền vững khi restart không?
- Group ID được tạo ổn định, có namespace và không xung đột giữa các flow/version?
- ReleaseStrategy xác định **đủ điều kiện nghiệp vụ**, không chỉ dựa vào số message gồm cả duplicate?
- Phân biệt rõ **release**, **complete** và **expire**; có chính sách cho late arrivals không?
- **expireGroupsUponCompletion** và **expireGroupsUponTimeout** đã chọn phù hợp chưa?
- Có **groupTimeout/reaper** và lịch cleanup cho incomplete, orphaned và completed groups?
- Có quyết định rõ ràng về **partial release** và cách downstream nhận biết kết quả thiếu phần?
- Metadata/condition có được cập nhật an toàn và không buộc load toàn bộ group khi quan sát không?
- Persistent store có schema, serializer, index, region và chiến lược migration phù hợp không?
- Với nhiều instance, có **LockRegistry** phân tán hoặc cơ chế phối hợp tương đương?
- Retry/transaction ở handler, poller và broker có thể làm output lặp không; downstream có idempotency không?
- Có log/metric cho pending groups, timeout, release, discard, lock contention và failedMessage/correlation không?
- Integration test đã phủ trường hợp out-of-order, duplicate, late arrival, restart và concurrent release chưa?

## Kết luận

**MessageGroup metadata** là phần trạng thái giúp Spring Integration biết một nhóm đã nhận gì, được cập nhật lúc nào, hoàn tất chưa và có cần giữ lại để nhận diện late message hay không. **ReleaseStrategy** quyết định thời điểm kết quả được phát; **MessageGroupProcessor** tạo kết quả; còn **MessageGroupStore** bảo quản message và metadata qua vòng đời nhóm.

Để xử lý chính xác trong runtime, cần thiết kế cùng lúc **correlation key**, **release condition**, **retention/expiry**, **locking**, **transaction**, **retry/idempotency** và khả năng quan sát. Đặc biệt, phải phân biệt nhóm **đã release** với nhóm **đã xóa metadata**: sự khác biệt này quyết định cách hệ thống phản ứng trước message đến muộn và việc xử lý lặp.

## Tài liệu tham khảo

- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration API — MessageGroup](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/store/MessageGroup.html)
- [Spring Integration API — MessageGroupMetadata](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/store/MessageGroupMetadata.html)
- [Spring Integration API — MessageGroupStore](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/store/MessageGroupStore.html)
- [Spring Integration API — AbstractCorrelatingMessageHandler](https://docs.spring.io/spring-integration/docs/6.5.x/api/org/springframework/integration/aggregator/AbstractCorrelatingMessageHandler.html)
