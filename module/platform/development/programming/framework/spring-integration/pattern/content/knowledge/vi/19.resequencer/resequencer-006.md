# Timeout khi thiếu một phần sequence

> **Chương:** Resequencer  
> **Module:** `SPRING_INTEGRATION_PATTERN` — học triển khai Enterprise Integration Patterns (EIP) bằng Spring Integration để xây dựng luồng thông điệp ít phụ thuộc và dễ mở rộng; thực hành Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, đồng thời kiểm thử và theo dõi các nhánh. Bài này tập trung vào **điều gì xảy ra khi Resequencer chờ một số thứ tự không đến**, cách đặt timeout, chọn chính sách kết thúc và tránh âm thầm phá thứ tự nghiệp vụ.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích chức năng **Resequencer**: gom các message cùng correlation group và phát chúng **theo sequence number**, khác với Aggregator gộp nội dung thành một kết quả.
2. Xác định **gap** (lỗ hổng trong dãy), **contiguous prefix** (tiền tố liên tiếp), **sequence size**, **đã phát/đang đợi**, **late arrival** và **duplicate**.
3. Phân biệt `releasePartialSequences(true)`, `sendPartialResultOnExpiry(true)`, `groupTimeout`, `discardChannel` và timeout tại Gateway hoặc broker.
4. Chọn giữa **đợi thêm**, **fail/đưa vào reconciliation**, **phát tiền tố an toàn** hoặc **bỏ qua gap có đánh dấu** theo rủi ro nghiệp vụ.
5. Viết một flow Spring Integration Java DSL `.resequence(...)` và hiểu phạm vi đảm bảo của MessageGroupStore, TaskScheduler, xử lý lỗi và correlation.
6. Kiểm thử **out-of-order, thiếu số đầu/giữa/cuối, timeout, duplicate, late reply, restart và race gần deadline**; không nhầm phát thành công với hoàn thành nghiệp vụ.
7. Thiết kế quan sát, backpressure và idempotency để một sequence thiếu phần không làm treo hệ thống hoặc chạy sai lệnh.

## 2. Tình huống thực tế: phần số 2 chưa đến

Một hệ thống xử lý các sự kiện thay đổi trạng thái vận đơn theo thứ tự. Producer phát bốn sự kiện thuộc cùng một quy trình `shipment-901`:

~~~text
Sequence 1: CREATED
Sequence 2: VERIFIED
Sequence 3: LABEL_ISSUED
Sequence 4: HANDED_TO_CARRIER
~~~

Do broker, retry hoặc xử lý bất đồng bộ, Resequencer nhận theo thứ tự thực tế:

~~~text
Arrival time:    t0    t1    t2       ? 
Sequence no:      3     1     4      2 chưa đến
Expected size:    4     4     4
~~~

Nếu consumer thực hiện `LABEL_ISSUED` trước khi nhận `VERIFIED`, nó có thể cập nhật trạng thái thiếu điều kiện tiên quyết. Resequencer giúp sắp xếp thứ tự, nhưng đến một lúc phải trả lời: **nếu số 2 không đến thì xử lý thế nào?**

~~~mermaid
flowchart LR
    A["Nhận #3"] --> B["Buffer #3"]
    C["Nhận #1"] --> D["Phát #1 khi cho phép contiguous release"]
    D --> E["Đang chờ #2"]
    F["Nhận #4"] --> G["Buffer #3, #4"]
    G --> T{"Deadline/timeout?"}
    T -->|"Chưa"| E
    T -->|"Có"| P["Fail / reconcile / partial policy"]
    H["#2 đến đúng hạn"] --> I["Phát #2 → #3 → #4"]
~~~

**Không có một đáp án chung**: với luồng chỉ dùng để hiển thị các thống kê độc lập, một số phần đến được có thể vẫn hữu ích; với các **lệnh thay đổi trạng thái có phụ thuộc thứ tự**, tuyệt đối không tự coi `3` hợp lệ sau `1` khi `2` đã mất.

## 3. Resequencer làm gì, khác Aggregator ở đâu?

Cả Resequencer và Aggregator đều cần **correlation** và có thể dùng MessageGroupStore để giữ các message. Nhưng:

| Tiêu chí | Resequencer | Aggregator |
| --- | --- | --- |
| Mục tiêu | **Sắp thứ tự** các message đầu ra | **Gom** nhiều message thành một kết quả |
| Dạng đầu ra thường gặp | Các message riêng lẻ, theo thứ tự sequence | Một message tổng hợp hoặc một kết quả nhóm |
| Căn cứ sắp xếp | `sequenceNumber` hoặc chiến lược xác định thứ tự | Release strategy và output processor |
| Xử lý khi thiếu phần | Chờ phần còn thiếu; timeout/expiry theo policy | Chờ đủ dữ liệu để tổng hợp; partial aggregation theo policy |
| Rủi ro | Phát nhảy số khiến consumer áp sai thứ tự | Tổng hợp thiếu phần nhưng coi là đầy đủ |
| Ví dụ | Sự kiện `1,3,2` → `1,2,3` | Ba kết quả tồn kho → một `BatchResult` |

**Resequencer không tự tạo lại phần bị mất**, không đảm bảo broker phát message đúng một lần, không thực thi transaction và không biến một chuỗi sai thứ tự thành dữ liệu nghiệp vụ đúng. Nó chỉ sắp xếp/giữ/phát các message **đã nhận được** theo điều kiện cấu hình.

Trong Spring Integration, Resequencer sử dụng metadata `CORRELATION_ID` và `SEQUENCE_NUMBER` của hệ thống messaging theo những chiến lược mặc định và tùy biến, và có thể chọn **đợi đủ toàn bộ sequence** hoặc **phát một tiền tố liên tiếp ngay khi có thể**.

### 3.1. “Cùng nhóm” phải có ý nghĩa chính xác

Một event của `shipment-901` trong lần đồng bộ `RUN-001` không nhất thiết thuộc cùng nhóm với event mới của cùng shipment trong `RUN-002`. Không nên dùng duy nhất `shipmentId` làm correlation key nếu các lần đồng bộ/replay có thể chồng lấn.

~~~text
businessKey = shipment-901      // đối tượng nghiệp vụ
executionId = RUN-001           // một lần xử lý sequence
correlationId = RUN-001         // khóa của group tại Resequencer
operationId = cmd-991          // khóa idempotency nếu có side effect
~~~

Correlation để **gom phần**, còn idempotency để **ngăn thực hiện lặp thao tác** là hai mục đích khác nhau.

## 4. Metadata sequence và hợp đồng đầu vào

Một message có thể mang những headers như:

~~~text
payload: ShipmentEvent(type=LABEL_ISSUED, shipmentId=shipment-901)
headers:
  correlationId: RUN-001
  sequenceNumber: 3
  sequenceSize: 4
  businessCorrelationId: shipment-901
  schemaVersion: v1
~~~

| Metadata | Ý nghĩa | Quy tắc cần kiểm |
| --- | --- | --- |
| `correlationId` | Xác định nhóm cần sắp xếp | Không null, không trộn nhiều execution |
| `sequenceNumber` | Vị trí của phần trong sequence | Theo hợp đồng `1..N`, không âm/0/vượt N |
| `sequenceSize` | Tổng số phần dự kiến | Nhất quán trong nhóm, biết rõ nếu cần hoàn tất |
| `businessCorrelationId` | Liên kết nghiệp vụ/log/tracing | Không thay thế khóa group hoặc idempotency |
| `eventId` | Định danh sự kiện nguồn | Hữu ích để dedup qua redelivery |
| `schemaVersion` | Kiểu biểu diễn/phần tử | Dùng đúng Transformer để hiểu payload |
| `createdAt/deadlineAt` | Thời gian của một execution, nếu có | Được tạo bởi nguồn tin cậy |

Với một flow `Splitter` sinh chuỗi, các sequence headers có thể được tạo bởi cơ chế **applySequence**. Khi qua HTTP, Kafka, AMQP, JMS hay custom Transformer, chúng có thể bị serialize/mapping khác đi. Phải kiểm thử **header thực tế lúc đi vào Resequencer**; không suy rằng `sequenceSize` chắc chắn có vì payload từng chứa một danh sách.

### 4.1. Khác với order của business event

`sequenceNumber=2` chỉ đáng tin nếu nó thực sự diễn đạt thứ tự nghiệp vụ được nguồn phát xác nhận. Nếu broker có ba partition độc lập, mỗi partition dùng offset riêng, việc ghép offset của ba partition thành một số thứ tự toàn cục **không có căn cứ**.

Muốn sắp thứ tự của một entity, cần một nguồn đánh số/version phù hợp — ví dụ `shipmentVersion` tăng đơn điệu theo shipment — cùng chính sách gap và replay rõ ràng.

### 4.2. Đừng tin headers nhạy cảm do client tùy ý khai

Nếu một bên ngoài có thể tự gắn `sequenceSize=1` cho một chuỗi thực tế bốn phần, ứng dụng có thể release quá sớm. Tại ingress, phải xác thực quyền gửi, kiểm tra tính nhất quán với schema/contract và ánh xạ metadata từ nguồn đáng tin. Nếu cần, giữ expected sequence size ở một **execution registry** do hệ thống sở hữu.

## 5. Gap là gì? Phân biệt thiếu đầu, giữa và cuối

Giả sử `sequenceSize=5` và sequence bắt đầu từ 1:

| Đã nhận | Dạng thiếu | Tiền tố liên tiếp có thể phát từ đầu | Bị chặn nếu giữ thứ tự nghiêm ngặt |
| --- | --- | --- | --- |
| `[1,2,3,4,5]` | Không thiếu | 1–5 | Không |
| `[1,3,4,5]` | Thiếu giữa: 2 | 1 | 3,4,5 |
| `[2,3,4,5]` | Thiếu đầu: 1 | Không có | 2,3,4,5 |
| `[1,2,3,4]` | Thiếu cuối: 5 | 1–4 | Chưa thể tuyên bố hoàn tất |
| `[1,2,4]` | Thiếu giữa và cuối | 1–2 | 4 |
| `[]` | Không nhận phần nào | Không có | Toàn bộ; có thể **chưa tồn tại group** |
| `[1,1,2]` | Duplicate số 1 | 1–2 nếu duplicate được xử lý | Cần dedup, không đếm là 3 phần |

**Tiền tố liên tiếp (contiguous prefix)** là dãy tăng không có khoảng trống bắt đầu từ số mong đợi kế tiếp. Nếu chưa phát gì, dãy cần bắt đầu từ `1`; nếu đã phát đến `k`, dãy tiếp theo phải bắt đầu từ `k+1`.

### 5.1. Khác nhau giữa “có dữ liệu” và “được phép phát”

Nếu đã nhận `1,3,4`, phần `3` và `4` tồn tại trong buffer. Nhưng nếu downstream yêu cầu **không bỏ qua số 2**, hai message này **chưa được phép phát**. Timeout không tự thay đổi ràng buộc đó.

### 5.2. Hai hình thức partial rất khác nhau

1. **Phát tiền tố liên tiếp sớm:** có thể phát `1` trước khi đủ cả sequence, nhưng giữ `3,4` cho đến khi `2` xuất hiện. Đây là lựa chọn giữ thứ tự.
2. **Phát phần đang giữ khi group expire:** nếu cấu hình cho phép, có thể phát những message đã có **theo thứ tự số của chúng** mặc dù còn lỗ hổng. Đó là “đã sắp xếp các phần hiện có”, **không đồng nghĩa sequence hoàn chỉnh hoặc liên tiếp**.

Chính khác biệt này khiến các thuộc tính **releasePartialSequences** và **sendPartialResultOnExpiry** không được dùng như từ đồng nghĩa.

## 6. Decision table cho timeout khi thiếu phần

Giả định nghiệp vụ: các sự kiện của một shipment được áp **theo đúng thứ tự**, không được nhảy qua event bắt buộc.

| Điều kiện | Chính sách strict được khuyến nghị | Chính sách tolerant (chỉ khi được cho phép) |
| --- | --- | --- |
| Đủ `1..N` trước hạn | Phát theo thứ tự, kết thúc `COMPLETE` | Tương tự |
| Nhận `1,3,4`; còn thời gian | Có thể phát `1`, giữ 3/4, đòi `2` | Có thể hiển thị thông tin “pending gap” |
| Đến hạn, vẫn thiếu `2` | **FAIL/RECONCILE**, không phát 3/4 như đã đủ | Có thể phát các phần được phép và **đánh dấu gap**, không apply side effect phụ thuộc |
| Thiếu `1` từ đầu | Chờ/replay; không apply 2/3/4 | Chỉ hiển thị raw events với cảnh báo thiếu đầu |
| Thiếu phần cuối `N` | Các phần trước có thể đã phát; batch không `COMPLETE` | Báo `PARTIAL/WAITING` theo contract |
| Một duplicate cùng số | Không đếm là thêm phần | Dedup có kiểm tra nội dung |
| Cùng số nhưng payload khác | Quarantine/conflict; không chọn ngẫu nhiên | Chỉ dùng version/attempt nếu contract quy định |
| Không phần nào đến | Deadline watcher cấp execution báo `NO_PARTS` | Không mong Resequencer tự expire group chưa tồn tại |
| Phần thiếu đến sau timeout | Late path/reconciliation; không âm thầm đảo thứ tự đã commit | Có thể phát event cập nhật có version, không phải final cũ |

Một chính sách “bỏ qua phần số 2 sau 5 giây” **phải được quyết định theo nghiệp vụ**, có audit, dữ liệu bù/placeholder nếu cần và xác nhận consumer chịu được gap. Không nên chọn chỉ vì triển khai dễ.

## 7. Phân biệt bốn loại timeout

Không chỉ có một “timeout” trong hệ thống messaging:

| Timeout | Bắt đầu và đo cái gì | Hệ quả |
| --- | --- | --- |
| **Group timeout** tại Resequencer | Lịch expire của một group đã có message | Xử lý các phần đang chờ trong group |
| **MessageGroupStoreReaper** | Quét/dọn các group theo tuổi/chính sách store | Expire/cleanup có thể chậm theo chu kỳ quét |
| **Request/business deadline** | Từ khi một execution/command được tạo bởi nguồn tin cậy | Quyết định SLA ngay cả khi **không phần nào tới** |
| **Gateway reply timeout** | Caller chờ phản hồi đồng bộ | Caller có thể bỏ chờ dù sequence vẫn đang được xử lý |
| **Channel send timeout** | Chờ gửi vào channel hữu hạn dung lượng | Không phải timeout chờ đủ các số sequence |
| **External provider timeout** | Chờ broker/HTTP/handler riêng | Không chứng minh message chưa được xử lý ở bên nhận |

### 7.1. Group timeout không mặc nhiên tính từ T0

~~~text
T0    Batch RUN-001 được tạo, deadline=T0+30s
T+10  Message #3 đến: group được tạo
T+20  Message #1 đến: group cập nhật
T+30  Business deadline phải được đánh giá
T+35  Message #2 đến trễ
~~~

Tùy cấu hình/phiên bản, timeout group có thể được lên lịch hoặc đánh giá lại khi group có message mới. Do đó **`groupTimeout(30_000L)` không phải lời hứa “đúng 30 giây sau khi batch được sinh”**.

Với deadline tuyệt đối, lưu `deadlineAt` khi tạo execution, đánh giá bằng một watcher/scheduler tương ứng và kiểm tra cả group đang có lẫn những execution **chưa có message**.

### 7.2. Không có message đầu tiên thì chưa có group

Nếu nguồn định tạo một sequence `1..4` nhưng không phần nào tới Resequencer, cơ chế lưu group có thể **chưa biết đến execution ấy**. Per-group timeout không thể tự sinh sự kiện `NO_PARTS` từ một group chưa tồn tại.

Một execution registry cần ghi nhận:

~~~text
ExecutionStarted(
  executionId="RUN-001",
  expectedSize=4,
  deadlineAt="...",
  status=OPEN
)

DeadlineWatcher at deadlineAt:
  if no parts -> SequenceTimedOut(NO_PARTS)
  if gaps -> SequenceTimedOut(MISSING_NUMBERS)
  if complete -> no-op
~~~

Watcher và Resequencer cần phối hợp **chỉ một quyết định cuối** cho execution.

## 8. Resequencer trên Spring Integration: các thuộc tính quan trọng

| Cấu hình | Tác dụng | Cần cảnh giác |
| --- | --- | --- |
| `.resequence()` | Tạo Resequencer trong Java DSL | Cần sequence headers và correlation hợp lệ |
| `releasePartialSequences(true)` | Cho phép phát **chuỗi liên tiếp hợp lệ** trước khi đủ toàn bộ | **Không** cho phép nhảy qua gap tùy ý |
| `releasePartialSequences(false)` | Chờ điều kiện complete theo default sequence release | Dễ giữ group lâu nếu thiếu một số |
| `groupTimeout(...)` | Lên lịch expiry group theo framework | Không nhất thiết bằng deadline nghiệp vụ từ ingress |
| `sendPartialResultOnExpiry(true)` | Khi group expire, phát các phần đã có theo cơ chế resequencing | Có thể còn **lỗ hổng**; consumer phải biết |
| `sendPartialResultOnExpiry(false)` | Không phát phần đang thiếu điều kiện release khi group expire | Phải có discard/error/notification theo contract |
| `discardChannel(...)` | Nhận những message bị loại theo cấu hình | Không tự sinh `GapReport` chứa danh sách missing |
| `expireGroupsUponTimeout(...)` | Quản lý việc giữ/xóa metadata group sau timeout | Xóa quá sớm khiến late arrival có thể tạo group mới |
| `messageStore(...)` | Đặt nguồn lưu nhóm | In-memory không bền qua restart |
| `taskScheduler(...)` | Scheduler phục vụ timeout/lifecycle | Cần kiểm tra shutdown, drift, failure |
| `MessageGroupStoreReaper` | Dọn nhóm cũ theo chu kỳ | Cần phối hợp với timeout và retention |

**Lưu ý:** tên phương thức, default và lifecycle có thể khác ở những phiên bản Spring Integration. Ví dụ Java DSL ở dưới nhắm tới họ API Spring Integration hiện đại có `ResequencerSpec`; hãy kiểm tra trên version cụ thể khi triển khai. Bài tập trung vào **hiểu đúng chính sách khi thiếu sequence**, chưa chạy build hoặc Content QA chuyên sâu ở STEP 4 NEW.

### 8.1. Hai cờ dễ nhầm nhất

~~~text
releasePartialSequences(true)
    -> khi có prefix liên tiếp (ví dụ #1), cho phát #1
    -> vẫn giữ #3, #4 vì đang thiếu #2

sendPartialResultOnExpiry(true)
    -> khi expire, cho phép phát các phần còn trong group
    -> những phần này có thể không tạo một dãy không có gap
    -> cần policy/notification để downstream không hiểu là COMPLETE
~~~

Dùng cả hai thuộc tính mà không có contract sẽ tạo hành vi khó đoán: đầu ra có thể gồm một tiền tố đã phát sớm và thêm những phần còn lại lúc expiry, nhưng **không bảo đảm dữ liệu đã từng có mặt đầy đủ**.

### 8.2. Resequencer không tự tạo “gap marker”

Spring Integration Resequencer quản lý sequence và phát messages, **không mặc định sinh một message nghiệp vụ** kiểu:

~~~json
{
  "executionId": "RUN-001",
  "missingSequenceNumbers": [2],
  "status": "EXPIRED_WITH_GAP"
}
~~~

Nếu cần thông báo như vậy, hãy xây một **gap detector/deadline watcher** dựa trên execution contract và trạng thái đã nhận, sau đó phát `SequenceGapDetected` hoặc `SequenceFailed` theo một error/reconciliation flow riêng.

## 9. Java DSL: flow không phát những phần vượt gap

Ví dụ dùng `DirectChannel` nhận các message có đủ sequence headers, Resequencer chọn **release contiguous partial sequences**, và `QueueChannel` làm điểm quan sát output. Khi timeout, không tự phát các message vượt gap.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ResequencerGapConfiguration {

    @Bean("events.resequence.in")
    DirectChannel resequenceInput() {
        return new DirectChannel();
    }

    @Bean("events.ordered.out")
    QueueChannel orderedOutput() {
        // Demo/test output: chưa có business consumer.
        return new QueueChannel();
    }

    @Bean("events.expired")
    QueueChannel expiredMessages() {
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow reorderEvents() {
        return IntegrationFlow.from("events.resequence.in")
            .resequence(r -> r
                .releasePartialSequences(true)
                .groupTimeout(30_000L)
                .sendPartialResultOnExpiry(false)
                .discardChannel("events.expired")
                .expireGroupsUponTimeout(false))
            .channel("events.ordered.out")
            .get();
    }
}
~~~

**Ý định của cấu hình minh họa:** phát phần liên tiếp khi sẵn có và **không tự đẩy một đoạn còn lỗ hổng vào consumer đòi thứ tự** chỉ vì hết hạn. Những phần bị expire/discard phải được quan sát và xử lý bằng chính sách riêng. `expireGroupsUponTimeout(false)` minh họa giữ metadata sau timeout để có cơ sở chặn late replies; việc retention và cleanup thực tế vẫn cần cấu hình phù hợp.

Không nên coi `events.expired` là một error-report channel tự tạo sẵn `missingNumbers`: nó là **discard channel theo semantics framework**. Nếu cần một báo cáo gap có dữ liệu đầy đủ, dùng execution registry/gap watcher như mục 12.

### 9.1. Tạo message có sequence headers

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record ShipmentEvent(String shipmentId, String eventType) {}

Message<ShipmentEvent> event(int index, int total,
                             String executionId, String type) {
    return MessageBuilder
        .withPayload(new ShipmentEvent("shipment-901", type))
        .setHeader(IntegrationMessageHeaderAccessor.CORRELATION_ID,
            executionId)
        .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER, index)
        .setHeader(IntegrationMessageHeaderAccessor.SEQUENCE_SIZE, total)
        .setHeader("businessCorrelationId", "shipment-901")
        .build();
}
~~~

Hàm `event(...)` là helper cho ví dụ/test trong class chứa nó, **không** phải bean độc lập. Những headers này được dựng thủ công để minh họa; trong một flow production, producer/Splitter/adapter phải thống nhất nguồn tạo metadata và nguồn tin cậy.

### 9.2. Dòng thời gian minh họa

~~~text
send #3 -> output empty
send #1 -> output #1 (nếu contiguous release có hiệu lực)
send #4 -> output empty; #3/#4 vẫn đợi #2
send #2 -> output #2, #3, #4 theo thứ tự

Nếu #2 không đến và group timeout:
  đã phát #1 -> không tự thu hồi được side effect của #1
  #3/#4 -> chưa đủ an toàn để phát ở strict flow
  deadline watcher -> SequenceFailed(missing=[2]) / reconcile
~~~

**Đặc biệt:** output `QueueChannel` có thể nhận message đã phát theo thứ tự, nhưng sau đó nếu thay bằng `ExecutorChannel`, broker nhiều partition hoặc nhiều consumer, **thứ tự hoàn thành nghiệp vụ** không tự được bảo đảm chỉ vì Resequencer đã phát đúng thứ tự.

## 10. Java DSL: khi nghiệp vụ có thể cho phép dữ liệu thiếu

Một hệ thống hiển thị báo cáo không đòi áp state transition có thể muốn phát những message đã nhận khi hết hạn, **theo thứ tự các phần hiện có**.

~~~java
@Bean
IntegrationFlow reorderForBestEffortReporting() {
    return IntegrationFlow.from("reports.raw.in")
        .resequence(r -> r
            .releasePartialSequences(false)
            .groupTimeout(5_000L)
            .sendPartialResultOnExpiry(true))
        .channel("reports.bestEffort.out")
        .get();
}
~~~

Đây là **đoạn cấu hình minh họa riêng**, giả định input/output channels và beans đã được khai báo ở một configuration khác. Vì `releasePartialSequences(false)`, những message trong group được giữ đến khi đủ điều kiện release hoặc expiry; `sendPartialResultOnExpiry(true)` cho phép **phát các message đang có khi expire**.

### 10.1. Rủi ro “đã sắp xếp nhưng chưa đầy đủ”

Giả sử chỉ có `2,4`. Khi hết hạn, output có thể là `2,4` theo số tăng dần. Nhưng không có `1,3`; do đó downstream **không được suy ra `2,4` là một sequence hoàn chỉnh**.

Muốn hỗ trợ best-effort an toàn, nên có **thông báo gap riêng** từ watcher, gắn `completeness=PARTIAL` vào kết quả tổng hợp hoặc cho consumer xử lý theo contract chịu được thiếu phần. Resequencer không tự biến `SequenceGapDetected` thành một business message gắn với từng output.

### 10.2. “Skip gap” phải rõ ràng và có giới hạn

Nếu sau 5 giây muốn bỏ qua `2` để xử lý `3,4`, cần định nghĩa:

- `2` có phải một **lệnh bắt buộc** không?
- Nếu `2` tới ở giây thứ 6, sẽ làm gì?
- Consumer có thể chạy `3` mà không biết kết quả `2` không?
- Có phát `GapSkipped(from=2,to=2)` để lưu audit không?
- Có cảnh báo hoặc reconciliation nào bắt buộc trước khi đánh dấu `COMPLETE` không?

Nếu câu trả lời không rõ, **đừng bật phát partial khi expire cho luồng nghiệp vụ đòi thứ tự**.

## 11. Mô hình thuần Java để hiểu gap và timeout

Cấu hình framework có các chi tiết về scheduling/group store. Ta tách một mô hình Java nhỏ để kiểm thử **bất biến của dãy** mà không cần Spring context.

Ở đây, `GapBuffer` mô tả:

- Sequence có `total` cố định và biết trước.
- Chỉ phát các message **liên tiếp từ `nextExpected`**.
- Một lần gửi cùng vị trí và cùng nội dung khi đang buffer được xem là duplicate.
- Cùng vị trí nhưng nội dung khác → lỗi `CONFLICT`.
- Khi hết hạn, buffer **đóng** và trả diagnostic; nó **không tự phát các phần vượt gap**.
- Bộ đệm giữ trong RAM của một JVM; không mô phỏng storage/retry multi-node.

### 11.1. DTO và buffer

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

record SequencedPart(
    String executionId,
    int position,
    int total,
    String eventId,
    String value
) {
    SequencedPart {
        if (executionId == null || executionId.isBlank()
                || eventId == null || eventId.isBlank()
                || value == null || value.isBlank()
                || total < 1 || position < 1 || position > total) {
            throw new IllegalArgumentException("INVALID_PART");
        }
    }
}

record GapReport(
    int nextExpected,
    int total,
    List<Integer> buffered,
    List<Integer> missing,
    boolean complete
) {
    GapReport {
        buffered = List.copyOf(buffered);
        missing = List.copyOf(missing);
    }
}

final class GapBuffer {
    private final String executionId;
    private final int total;
    private final Map<Integer, SequencedPart> pending = new TreeMap<>();

    private int nextExpected = 1;
    private boolean closed;

    GapBuffer(String executionId, int total) {
        if (executionId == null || executionId.isBlank() || total < 1) {
            throw new IllegalArgumentException("INVALID_SEQUENCE");
        }
        this.executionId = executionId;
        this.total = total;
    }

    synchronized List<SequencedPart> accept(SequencedPart part) {
        if (closed) {
            throw new IllegalStateException("LATE_PART_AFTER_CLOSE");
        }
        if (!executionId.equals(part.executionId())
                || total != part.total()) {
            throw new IllegalArgumentException("CORRELATION_OR_SIZE_MISMATCH");
        }
        if (part.position() < nextExpected) {
            // Đã phát trước đó: eventId/idempotency thật phải được
            // kiểm soát bởi consumer hoặc một store bền vững.
            return List.of();
        }

        SequencedPart old = pending.putIfAbsent(part.position(), part);
        if (old != null && !old.equals(part)) {
            throw new IllegalArgumentException("CONFLICTING_SEQUENCE_PART");
        }

        List<SequencedPart> ready = new ArrayList<>();
        while (pending.containsKey(nextExpected)) {
            ready.add(pending.remove(nextExpected));
            nextExpected++;
        }
        return List.copyOf(ready);
    }

    synchronized GapReport report() {
        List<Integer> buffered = new ArrayList<>(pending.keySet());
        List<Integer> missing = new ArrayList<>();
        for (int i = nextExpected; i <= total; i++) {
            if (!pending.containsKey(i)) {
                missing.add(i);
            }
        }
        return new GapReport(
            nextExpected, total, buffered, missing,
            nextExpected > total);
    }

    synchronized GapReport closeOnTimeout() {
        GapReport result = report();
        closed = true;
        return result;
    }
}
~~~

`GapBuffer` là **mô hình giải thích contiguous emission và timeout**, không thay thế `ResequencingMessageHandler` của Spring Integration và **không** phải thành phần production. Một production buffer sẽ phải xử lý storage, locks/distributed coordination, bounded capacity, upstream acknowledgment, duplicate sau restart, monitoring và chính sách phát lỗi.

### 11.2. Các tình huống mô phỏng

~~~java
GapBuffer buffer = new GapBuffer("RUN-001", 4);

buffer.accept(new SequencedPart("RUN-001", 3, 4, "ev-3", "LABEL"));
List<SequencedPart> first = buffer.accept(
    new SequencedPart("RUN-001", 1, 4, "ev-1", "CREATED"));
// first chứa position=1

buffer.accept(new SequencedPart("RUN-001", 4, 4, "ev-4", "HANDED"));
GapReport report = buffer.report();
// report.nextExpected() == 2
// report.buffered() == [3,4]
// report.missing() == [2]

List<SequencedPart> ready = buffer.accept(
    new SequencedPart("RUN-001", 2, 4, "ev-2", "VERIFIED"));
// ready chứa position=[2,3,4] theo thứ tự
~~~

Một timeout xảy ra khi vẫn chờ `2`:

~~~java
GapBuffer waiting = new GapBuffer("RUN-GAP", 4);
waiting.accept(new SequencedPart("RUN-GAP", 1, 4, "ev-1", "CREATED"));
waiting.accept(new SequencedPart("RUN-GAP", 3, 4, "ev-3", "LABEL"));
waiting.accept(new SequencedPart("RUN-GAP", 4, 4, "ev-4", "HANDED"));

GapReport timedOut = waiting.closeOnTimeout();
// missing=[2], buffered=[3,4], complete=false
// Đã phát #1 trước đó; không phát #3/#4 trong strict policy.
~~~

**Phân biệt việc “đóng state” và “phát event timeout”:** `closeOnTimeout` chỉ trả report trong JVM. Caller cần đưa report tới log/metrics, reconciliation/error channel, và **atomically finalize** execution. Không nên hiểu đoạn code là một scheduler tự chạy.

## 12. Chọn hành động khi group expire

Nên thiết kế **kết quả timeout có kiểu rõ**, không chỉ log một exception.

~~~text
SequenceGapDetected
  executionId = RUN-001
  expectedSize = 4
  emittedUpTo = 1
  missingNumbers = [2]
  blockedNumbers = [3,4]
  reasonCode = GAP_TIMEOUT
  decision = RECONCILE_REQUIRED
  policyVersion = strict-sequence-v2
~~~

### 12.1. Ba chính sách có ý nghĩa khác nhau

| Policy | Lúc hết hạn | Khi nên dùng |
| --- | --- | --- |
| **STRICT_FAIL** | Không phát các phần vượt gap; đóng hoặc suspend execution, báo lỗi/reconcile | State transitions, ledger, workflows có điều kiện tiên quyết |
| **CONTIGUOUS_PREFIX_ONLY** | Giữ những phần đã phát liên tiếp; các phần còn lại không apply; trả partial diagnostic | Có thể chấp nhận tiến độ nhưng không được đánh dấu complete |
| **SKIP_GAP_WITH_MARKER** | Có thể phát message sau gap **kèm thông báo thiếu** và policy rõ | Báo cáo/best-effort độc lập với điều kiện tiên quyết |
| **REPLAY_THEN_FAIL** | Yêu cầu phát lại những số thiếu; hết lượt thì fail/reconcile | Nguồn có thể replay theo position/event ID |

Có thể kết hợp: đợi ngắn → request replay → đến deadline thì fail; hoặc đợi ngắn → phát prefix an toàn → tiếp tục chờ trong cửa sổ dài hơn → cuối cùng reconcile.

### 12.2. Chính sách hoàn tất phải được pin theo execution

Nếu hôm nay cho phép skip gap nhưng ngày mai đổi thành strict, một execution đã bắt đầu không nên đổi ngữ nghĩa giữa chừng mà không có migration rule. Hãy lưu `policyVersion`, `deadlineAt` và expected sequence size cùng execution.

### 12.3. Retry từ nguồn khác với re-run handler

Để xin lại `#2`, có thể gửi `ReplayRequested(executionId, missing=[2])` tới producer hoặc một event store. Nhưng replay một business **command đã có side effect** không được đồng nghĩa “thực hiện lại lệnh từ đầu”. Nguồn replay phải trả **event/output đã ghi nhận**, hoặc consumer dùng idempotency key và tra cứu trạng thái để tránh lặp side effect.

## 13. Late arrival sau khi timeout

Giả sử group hết hạn ở T0+30 và phát `SequenceGapDetected(missing=[2])`. Đến T0+31, `#2` mới tới.

**Không được** mặc định:

- Đưa `#2` vào một group mới có cùng key rồi phát `#2` sau `#3/#4` đã gửi.
- Đảo ngược các side effect đã commit để “sửa” thứ tự.
- Tuyên bố sequence hoàn chỉnh nếu execution đã đóng thất bại.
- Phát một final outcome thứ hai không có version.

### 13.1. Closed-group registry / tombstone

~~~text
Message arrives with executionId
             |
             v
    Execution state registry
             |
       +-----+------+
       |            |
      OPEN         CLOSED / EXPIRED
       |            |
    Resequencer   Late/reconcile path
       |
     Ordered flow
~~~

State registry cần xác định:

- `OPEN`: nhận và buffer phần hợp lệ.
- `COMPLETE`: sequence đã xử lý đủ theo contract.
- `EXPIRED`: deadline đã kết thúc, có gap.
- `RECONCILING`: đang tìm phần thiếu hoặc xác minh tác dụng phụ.
- `UNKNOWN`: không có execution hợp lệ; quarantine/reject.

Tombstone phải được lưu ít nhất theo **cửa sổ late arrival/replay**, không chỉ theo thời gian của một process. Dọn metadata quá sớm có thể khiến late message tạo lại group trống.

### 13.2. Race ở ranh giới timeout

~~~text
Thread A: #2 vừa tới, giải phóng được #2,#3,#4
Thread B: deadline watcher đã thấy missing #2
~~~

Trong cùng một JVM, `synchronized` có thể bảo vệ một cấu trúc đơn giản, nhưng **không giải quyết multi-node** hoặc phát event ra broker/DB thành hai bước không nguyên tử.

Cần một **transition duy nhất** trên execution, ví dụ `OPEN → COMPLETE` hoặc `OPEN → EXPIRED` bằng transaction/CAS, và outbox/idempotent finalizer nếu cần exactly-once *business effect*. Ở tầng messaging vẫn phải thiết kế chấp nhận at-least-once/redelivery.

## 14. MessageGroupStore, scheduler và nhóm không kết thúc

Resequencer có thể giữ nhiều message đang đợi trong MessageGroupStore. Một lỗ hổng có thể khiến các phần phía sau tiếp tục tích tụ:

~~~text
Expected 1..100
Received 1,3,4,5,...,100
Missing #2
=> Buffer giữ 98 phần dù chỉ thiếu một số.
~~~

Điều này đặc biệt nguy hiểm khi có hàng nghìn execution song song. Thực tế Resequencer phù hợp nhất với **những dãy tương đối ngắn và ít gap**; nếu sequence quá lớn và nhiều lỗ hổng, cần cân nhắc checkpoint/partition-aware stream processing hoặc cơ chế workflow khác.

| Hạng mục | Thiết kế cần có |
| --- | --- |
| `MessageGroupStore` | In-memory hay persistent? Có chịu được restart không? |
| Task scheduler | Có chạy ổn định, phát hiện missed deadlines không? |
| Locking | Nhiều thread/node cập nhật cùng group có race không? |
| Group cleanup | Khi nào metadata group hoàn thành/expired được xóa? |
| Retention | Late replies/replay sau bao lâu còn được nhận diện? |
| Memory quota | Tối đa bao nhiêu phần/byte mỗi group và toàn hệ thống? |
| Backpressure | Quá tải thì producer/broker/consumer phản ứng thế nào? |
| Replay | Có nguồn sự kiện bền vững để xin lại phần bị thiếu? |

### 14.1. MessageGroupStoreReaper

Reaper có thể quét/expire các group theo tuổi và chu kỳ. Nhưng nó không thay thế **deadline tính từ lúc execution bắt đầu**, và phải phối hợp với `groupTimeout` để không phát hai thông báo kết thúc hoặc xóa state khi consumer còn xử lý late reply.

Việc giữ metadata group đã phát hết có thể cần thiết để **chặn message đến muộn**; đồng thời giữ vô hạn gây rò rỉ bộ nhớ/store. Tạo retention rõ ràng và đo `oldestGroupAge`, `closedStateCount`, `cleanupFailures`.

### 14.2. Persistence không tự tạo thứ tự cuối cùng ở consumer

Ngay cả khi Resequencer đã sắp lại đúng và store bền vững, nếu output đi vào một executor đa thread rồi ba handler làm việc đồng thời, `#3` có thể commit trước `#2`.

Nếu logic đòi state transition theo thứ tự, downstream cần **serialize theo entity key**, version checks/optimistic locking hoặc một cơ chế bảo toàn thứ tự khác. Resequencer chỉ kiểm soát ranh giới **phát message** của nó.

## 15. Kiểm thử unit cho mô hình gap

Dùng JUnit 5 với `GapBuffer` ở mục 11. Các test không cần Spring context và không phải đợi thời gian thực.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class GapBufferTest {

    private static SequencedPart part(int index) {
        return new SequencedPart(
            "RUN-TEST", index, 4, "event-" + index, "value-" + index);
    }

    @Test
    void releasesOnlyTheContiguousPrefix() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);

        assertTrue(buffer.accept(part(3)).isEmpty());

        List<SequencedPart> first = buffer.accept(part(1));
        assertEquals(List.of(1),
            first.stream().map(SequencedPart::position).toList());

        assertTrue(buffer.accept(part(4)).isEmpty());
        assertEquals(List.of(2), buffer.report().missing());
        assertEquals(List.of(3, 4), buffer.report().buffered());

        List<SequencedPart> rest = buffer.accept(part(2));
        assertEquals(List.of(2, 3, 4),
            rest.stream().map(SequencedPart::position).toList());

        assertTrue(buffer.report().complete());
        assertTrue(buffer.report().missing().isEmpty());
    }

    @Test
    void missingFirstElementBlocksAllLaterOnes() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);

        assertTrue(buffer.accept(part(2)).isEmpty());
        assertTrue(buffer.accept(part(3)).isEmpty());
        assertEquals(1, buffer.report().nextExpected());
        assertEquals(List.of(1, 4), buffer.report().missing());
    }

    @Test
    void timeoutPreservesEvidenceOfGapAndRejectsLatePart() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);
        buffer.accept(part(1));
        buffer.accept(part(3));

        GapReport timedOut = buffer.closeOnTimeout();
        assertEquals(List.of(2, 4), timedOut.missing());
        assertEquals(List.of(3), timedOut.buffered());
        assertFalse(timedOut.complete());

        assertThrows(IllegalStateException.class,
            () -> buffer.accept(part(2)));
    }

    @Test
    void duplicatePendingPartDoesNotCountTwice() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);
        assertTrue(buffer.accept(part(3)).isEmpty());
        assertTrue(buffer.accept(part(3)).isEmpty());

        assertEquals(List.of(3), buffer.report().buffered());
    }

    @Test
    void conflictingDuplicateIsRejected() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);
        buffer.accept(part(3));

        SequencedPart changed = new SequencedPart(
            "RUN-TEST", 3, 4, "different-id", "other-value");

        assertThrows(IllegalArgumentException.class,
            () -> buffer.accept(changed));
    }

    @Test
    void foreignExecutionCannotJoinThisSequence() {
        GapBuffer buffer = new GapBuffer("RUN-TEST", 4);

        assertThrows(IllegalArgumentException.class,
            () -> buffer.accept(new SequencedPart(
                "OTHER-RUN", 1, 4, "event-1", "value-1")));
    }
}
~~~

**Phạm vi:** unit tests chứng minh invariant của một mô hình `GapBuffer` đồng bộ trong JVM. Chúng **không** chứng minh Spring Integration Resequencer có cùng lifecycle ở mọi phiên bản, group timeout chính xác hay consumer có idempotency.

## 16. Integration test Spring Integration: out-of-order và gap

Với `ResequencerGapConfiguration` ở mục 9, có thể gửi message có headers giống như đã được Splitter tạo và quan sát output queue.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ResequencerGapConfiguration.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ResequencerGapIntegrationTest {

    @Autowired @Qualifier("events.resequence.in")
    MessageChannel input;

    @Autowired @Qualifier("events.ordered.out")
    PollableChannel ordered;

    @Test
    void buffersOutOfOrderMessagesUntilGapIsFilled() {
        String group = "RUN-SEQ-TEST";

        assertTrue(send(group, 3));
        assertNull(ordered.receive(0));

        assertTrue(send(group, 1));
        assertEquals(1, number(ordered.receive(1000)));

        assertTrue(send(group, 4));
        assertNull(ordered.receive(0),
            "Seq 3/4 must wait while seq 2 is missing");

        assertTrue(send(group, 2));
        assertEquals(2, number(ordered.receive(1000)));
        assertEquals(3, number(ordered.receive(1000)));
        assertEquals(4, number(ordered.receive(1000)));

        assertNull(ordered.receive(0), "No extra output");
    }

    private boolean send(String group, int number) {
        return input.send(MessageBuilder
            .withPayload(new ShipmentEvent(
                "shipment-901", "EVENT-" + number))
            .setHeader(
                IntegrationMessageHeaderAccessor.CORRELATION_ID, group)
            .setHeader(
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER, number)
            .setHeader(
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE, 4)
            .setHeader("businessCorrelationId", "shipment-901")
            .build());
    }

    private int number(Message<?> message) {
        assertNotNull(message);
        Object raw = message.getHeaders().get(
            IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER);
        assertInstanceOf(Number.class, raw);
        return ((Number) raw).intValue();
    }
}
~~~

Đây là ví dụ test cho **resequence theo sequence headers trong message**, không kiểm chứng một transport broker thực. Nếu một phiên bản Spring Integration hoặc cấu hình `popSequence` thay đổi/loại header sequence khi phát, hãy xác định output contract và dùng một **business position** trong payload để assert thứ tự mà không phụ thuộc metadata đã bị pop.

### 16.1. Kiểm thử timeout với test configuration riêng

Để test thiếu `#2` khi group timeout, tạo **test profile/config** với thời hạn ngắn nhưng đủ ổn định và TaskScheduler phù hợp. Không dùng timeout production 30 giây trong unit suite.

~~~text
Given:
  group=RUN-TIMEOUT, expected 1..4
  releasePartialSequences=true
  sendPartialResultOnExpiry=false
  configured short groupTimeout
  discard/error path observed

When:
  send #3
  send #1   -> #1 may be released
  send #4
  do not send #2
  await group expiry with bounded timeout

Then:
  #3 and #4 never appear on ordered output
  Expiry/discard behavior matches configuration/version
  Gap watchdog emits SequenceGapDetected(missing=[2])
  One execution final outcome only
~~~

Đây là **kịch bản kiểm thử**, không phải khẳng định đã chạy scheduler trong STEP 4 NEW. Chạy thêm integration test trên đúng Spring Integration version để xác minh group timing, headers và discard semantics, nhất là nếu dùng persistent MessageGroupStore.

### 16.2. Khi bật `sendPartialResultOnExpiry(true)`

Dùng một test **khác topology**: gửi `#2,#4`, thiếu `#1,#3` rồi để group expire. Kết quả phải được xử lý như **best-effort partial**; test cần chứng minh consumer **không đánh dấu `COMPLETE`** và watcher báo missing list tương ứng. Không dùng luồng này cho state transitions nếu nghiệp vụ cấm skip.

## 17. Ma trận kiểm thử toàn diện

| Kịch bản | Input/diễn biến | Điều cần assert |
| --- | --- | --- |
| Happy path | `1,2,3,4` | Output theo 1–4, complete |
| Out-of-order | `3,1,4,2` | Output theo 1–4, không phát 3 trước 2 |
| Thiếu phần đầu | `2,3,4` | Strict output không nhảy qua 1; expiry có gap |
| Thiếu phần giữa | `1,3,4` | Có thể phát 1, nhưng 3/4 bị chặn |
| Thiếu phần cuối | `1,2,3` | Có thể phát prefix, không đánh dấu complete |
| Không phần nào đến | `[]` | Watcher phát NO_PARTS; group timer không phải nguồn duy nhất |
| Duplicate pending | `3,3` | Không tính thành hai vị trí |
| Duplicate after release | Gửi lại `1` | Không apply business effect lần hai |
| Conflicting duplicate | Hai nội dung khác cho cùng position | Quarantine/error, không chọn bừa |
| Sai `sequenceSize` | Một message có 5, phần khác có 4 | Reject/alert, không release sai |
| Sai correlation | Phần của RUN-B vào RUN-A | Không trộn execution |
| Out-of-range | position=0 hoặc > N | Reject tại ingress |
| Timeout strict | Thiếu 2 đến deadline | Không phát 3/4 vượt gap |
| Timeout partial | Đã nhận 2/4, không đủ | Nếu policy cho phép, nhận partial và thông báo missing |
| Late arrival | `2` đến sau expire | Không tự tạo group mới/final thứ hai |
| Timeout/reply race | `#2` đến sát thời điểm expire | Finalization đúng một lần |
| Restart giữa group | Store in-memory vs persistent | Recovery đúng hợp đồng |
| Nhiều instance | Hai node xử lý cùng group | Lock/store/ownership và dedup đúng |
| Output executor | Dispatch đúng, consumer hoàn tất lệch | Có bảo toàn thứ tự side effect theo key |
| Queue đầy | Output bounded queue | Send timeout/error/backpressure đúng |
| Gateway chờ reply | Chỉ có prefix, thiếu hậu tố | Reply/error rõ, không treo vô hạn |
| Resequencer + Aggregator | Một phần bị drop | Aggregator không chờ mãi hoặc nhận completion giả |
| Header mapping | Qua Kafka/HTTP | Sequence metadata tồn tại đúng kiểu |

### 17.1. Assert cả đầu ra **không được phát**

Đối với Resequencer, một test chỉ kiểm tra `#1` đã ra **chưa đủ**. Nếu đang thiếu `#2`, phải kiểm chứng `#3,#4` **không** vào consumer strict. Sự vắng mặt ở output trong một khoảng test phù hợp là một phần quan trọng của contract.

### 17.2. Test race không dựa vào `Thread.sleep` ngẫu nhiên

Các sự kiện timeout thường khó test ổn định. Nên dùng clock/scheduler có thể điều khiển, state machine unit tests, hoặc bounded await với timeouts được cấu hình đủ dư. Với multi-node, cần test hệ thống thực về **chỉ một final outcome**, chứ không chỉ pass một unit test của buffer trong JVM.

## 18. Error handling, retry và idempotency

Một số sequence part bị thiếu có thể do:

1. Producer chưa phát `#2`.
2. Producer đã phát nhưng broker chưa giao.
3. Consumer nhận rồi lỗi trước khi đưa vào Resequencer.
4. Adapter mất `sequenceNumber` hoặc `correlationId`.
5. Filter drop part vì dữ liệu sai, nhưng không tạo outcome lỗi.
6. Duplicate/out-of-order vượt khả năng buffer hoặc message store.

Không thể suy ra nguyên nhân chỉ bằng `gap=[2]`.

### 18.1. Đặt retry đúng bước

- Nếu **publish transient failure**, retry publish với event ID ổn định.
- Nếu **missing part có sẵn trong event log**, request replay theo position.
- Nếu **part invalid schema**, quarantine và sửa nguồn; không retry vô hạn cùng bytes.
- Nếu **downstream side effect có thể đã commit**, tra cứu trạng thái và dùng idempotency; không phát lại command mù quáng.
- Nếu Resequencer timeout, phát một **GapDetected/SequenceExpired** theo contract và chuyển reconciliation, không tự mở lại group trừ khi có quy tắc rõ.

### 18.2. Error channel không tự lấp lỗ hổng

Một `ErrorMessage` ở error channel chứa thông tin lỗi xử lý không tự biến thành phần `sequenceNumber=2`. Muốn Aggregator/Resequencer hiểu rằng phần đã thất bại, hệ thống phải **chủ động mô hình hóa outcome** phù hợp với dãy, hoặc kết thúc execution có lý do.

### 18.3. Splitter và Aggregator có thể phụ thuộc sequence

~~~text
Batch -> Splitter (sequence 1..4)
      -> Async handlers
      -> Resequencer (ordered child results)
      -> Aggregator (optional: combined result)
~~~

Một Aggregator chờ đủ 4 phần sẽ không tự release nếu Resequencer giữ `#3,#4` vì thiếu `#2`, trừ khi có timeout/release policy thích hợp. Hệ thống có thể cần một **Error/Partial Result** có kiểu rõ để hoàn tất nhóm hoặc trả lỗi cho Gateway thay vì chờ vô hạn.

Nếu chỉ cần gom kết quả **không phụ thuộc thứ tự**, việc chèn Resequencer trước Aggregator có thể không cần thiết. Hãy tránh thêm buffer và timeout khi ứng dụng không cần bảo toàn thứ tự.

## 19. Quan sát gap và kiểm soát tài nguyên

Một hệ thống có thể chạy ổn nhưng âm thầm tích lũy hàng nghìn group thiếu một phần. Cần theo dõi **tình trạng nhóm đang chờ**, không chỉ số message được gửi ra.

| Điểm đo | Thông tin | Mục đích |
| --- | --- | --- |
| Ingress | Sequence parts/second, invalid metadata | Phát hiện nguồn lỗi |
| Resequencer | Open groups, buffered parts, next expected | Thấy đang chờ số nào |
| Gap detector | Missing positions, gap age, count by reason | Tách nghẽn tạm thời và mất message |
| Timeout/expiry | Expired groups, discarded parts, partial releases | Phát hiện chính sách đang dùng |
| MessageGroupStore | Size, oldest group age, cleanup lag | Giới hạn tài nguyên |
| Replay service | Replay requests, success/failure | Xác nhận có phục hồi gap |
| Late path | Late parts, tombstone hits, reconciliation | Tránh group mở lại |
| Output consumer | Commit order, retries, idempotent dedup | Chứng minh hiệu lực nghiệp vụ |
| Scheduler | Deadline/check success, misfires | Tránh timeout không chạy |

### 19.1. Log một gap đủ để điều tra

~~~json
{
  "event": "sequence_gap_timeout",
  "executionId": "RUN-001",
  "businessId": "shipment-901",
  "expectedSize": 4,
  "emittedUpTo": 1,
  "missingPositions": [2],
  "bufferedPositions": [3,4],
  "policy": "STRICT_FAIL",
  "decision": "RECONCILE_REQUIRED"
}
~~~

**Lưu ý:** Resequencer không tự tạo toàn bộ các trường này; chúng đến từ gap detector/registry do ứng dụng thiết kế. Log cần kiểm soát quyền; business ID/trace ID có cardinality cao, không nên đưa trực tiếp vào metric tags.

### 19.2. Metric cardinality

Tag `policyName`, `endpoint`, `outcome`, `sourceType` có thể có tập giá trị hữu hạn. `executionId`, `shipmentId`, `messageId` thường khác nhau trên từng message; đặt chúng trong log/trace có phân quyền thay vì tags của time-series metric.

### 19.3. Backpressure không phải lỗi nghiệp vụ

Nếu một group thiếu `#2` và các phần tiếp theo cứ tới, buffer tăng. Đặt quota `maxPendingPartsPerGroup`, `maxOpenGroups`, `maxBufferedBytes` và phản ứng rõ khi quá tải: tạm ngừng consumer, chuyển dead-letter, xin replay hoặc fail execution. Đừng mặc định drop phần cũ nhất rồi âm thầm nhận phần mới; làm vậy có thể tạo thêm gap không thể hồi phục.

## 20. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách tránh |
| --- | --- | --- |
| Bật `sendPartialResultOnExpiry(true)` mà tưởng vẫn giữ sequence liên tiếp | Phát các phần có gap sang consumer strict | Phân biệt contiguous prefix và partial-on-expiry |
| Xem `groupTimeout` là deadline từ lúc tạo request | Tính SLA sai, đặc biệt khi phần đầu tới trễ | Deadline watcher ở ingress |
| Chỉ cấu hình group timeout cho case 0 phần | Không có group để expire | Execution registry có deadline |
| Đếm số message thay vì unique sequence numbers | Duplicate làm tưởng đủ phần | Validate, dedup, kiểm tra range |
| Trộn `shipmentId` với `executionId` | Hai phiên replay có thể lẫn nhau | Correlation theo execution |
| Dùng `sequenceNumber` làm business idempotency key duy nhất | Số 2 của hai đơn khác nhau trùng nhau | Dùng business operation ID + entity/part ID |
| Dùng `HashSet` như nguồn thứ tự | Thứ tự không có contract ổn định | Gắn sequence từ nguồn có thẩm quyền |
| Resequencer phát đúng mà executor xử lý song song không có khóa | Downstream commit sai thứ tự | Serialize per entity / version guards |
| Expire/xóa group rồi bỏ qua late arrivals | Group mới hoặc final outcome thứ hai | Tombstone, late/reconciliation flow |
| Retry toàn batch chỉ vì thiếu một part | Gây lặp side effect ở phần đã xử lý | Replay đúng phần thiếu, idempotency |
| Một Filter drop part mà không ghi lý do | Resequencer chờ mãi không rõ vì sao | Error/reject event và metrics |
| Không đặt quota buffer | Heap/store cạn khi gap kéo dài | Bounded state, backpressure và timeout |
| Coi `send()` thành công là handler hoàn tất | Kết luận sai về thứ tự nghiệp vụ | Theo dõi commit/business outcome |
| Không test missing first/middle/last | Bỏ sót các biên quan trọng | Ma trận test đủ dạng gap |
| Dùng timeout test dựa sleep cố định | Flaky CI, race hiếm không được phát hiện | Bounded await/test scheduler |

## 21. Checklist khi triển khai

- [ ] Có hợp đồng sequence rõ: bắt đầu từ số nào, `sequenceSize` và định danh execution.
- [ ] `correlationId`, `sequenceNumber` và `sequenceSize` được tạo/validate từ nguồn tin cậy.
- [ ] Chỉ dùng Resequencer khi thực sự cần **thứ tự**, không vì muốn “gom lại”.
- [ ] Biết nơi nào **release contiguous prefix**, nơi nào **wait all** và tác động với downstream.
- [ ] Chọn explicit policy khi timeout: strict fail, prefix-only, replay, hoặc best-effort có gap marker.
- [ ] Không mặc định partial-on-expiry vẫn là một dãy hoàn chỉnh.
- [ ] Có deadline watcher từ execution creation, đặc biệt khi không nhận part đầu tiên.
- [ ] Có error/quarantine/replay path khi thiếu hoặc sai metadata.
- [ ] Có chính sách duplicate, conflicting duplicate, out-of-range và late arrival.
- [ ] Có state transition đóng execution đúng một lần và tombstone/retention phù hợp.
- [ ] Group store/scheduler/lock/multi-node được thiết kế cho SLA/restart.
- [ ] Downstream có bảo đảm **thực thi thứ tự** tương ứng nếu nghiệp vụ đòi hỏi.
- [ ] Có quota nhóm và buffer, backpressure, monitoring `oldestGapAge`.
- [ ] Có unit test invariant và integration test Spring Integration thực với cả trường hợp không được phát output.
- [ ] Không dùng `MessageHeaders.id` thay business identity hoặc idempotency key.
- [ ] Có observability không lộ payload/PII và không tạo metric tag cardinality cao.

## 22. Bài tập thực hành

Một nền tảng phát hành hóa đơn nhận `InvoiceEvent` theo `invoiceVersion` tăng từ 1 đến 5:

~~~text
1: DRAFT_CREATED
2: LINE_ITEMS_CONFIRMED
3: TAX_CALCULATED
4: INVOICE_ISSUED
5: CUSTOMER_NOTIFIED
~~~

Các event có thể bị delivery out-of-order hoặc redelivery; `INVOICE_ISSUED` **không** được apply khi chưa xử lý `TAX_CALCULATED`. SLA nhận đủ chuỗi là 20 giây từ lúc execution được tạo.

**Yêu cầu:**

1. Thiết kế `executionId` và `invoiceId` riêng; xác định nguồn tạo `sequenceNumber` và `sequenceSize`.
2. Vẽ flow `Inbound → Validate headers → Resequencer → Invoice state handler` cùng gap/error/replay path.
3. Giả lập arrival `[4,1,5,3]`, thiếu `2`; chỉ ra số nào có thể phát trong strict contiguous mode.
4. Chọn `releasePartialSequences` và `sendPartialResultOnExpiry` sao cho không bao giờ apply `#3/#4/#5` trước `#2`.
5. Khi quá 20 giây, phát một event `InvoiceSequenceExpired(missing=[2])` và quyết định có phát yêu cầu replay `#2` hay không.
6. Nếu `#2` tới ở giây 21, chỉ ra cách late path/closed-state xử lý mà không phát hai final outcomes.
7. Viết unit test `GapBuffer` cho missing first/middle/last, duplicate, conflicting duplicate, out-of-range và timeout.
8. Viết integration test `.resequence(...)`, assert thứ tự message ra, cùng những message **không được phép ra** khi có gap.
9. Giả sử downstream dùng 4 threads và `#4` commit trước `#3` dù Resequencer phát đúng: thiết kế serialization/version validation ở handler.
10. Với 500.000 invoice executions/ngày, đề xuất quota, MessageGroupStore bền, cleanup, reaper, backpressure và metrics gap age.
11. Nếu invoice engine đã phát hành hóa đơn ở một lần xử lý trước đó và event bị replay, đề xuất idempotency key để không phát hành hai lần.

**Gợi ý:** Với các trạng thái có điều kiện tiên quyết, **đợi/replay/fail** khi thiếu event là an toàn hơn “skip gap”. Nếu cần hiển thị dữ liệu đến muộn, dùng một **read model/projection** có thông báo `PARTIAL` riêng, đừng phát nó vào handler ghi trạng thái có side effect.

## 23. Tổng kết

**Timeout khi thiếu một phần sequence** không chỉ là cấu hình một con số. Nó là quyết định về **tính đầy đủ, thứ tự, khả năng mất dữ liệu và hành vi khi một phần không bao giờ đến**. Spring Integration Resequencer dùng correlation và sequence metadata để phát message theo thứ tự; có thể đợi đủ, phát tiền tố liên tiếp hoặc xử lý những phần đang có khi group expire theo cấu hình. **Phát các message được sắp theo số khi hết hạn không có nghĩa dãy đã hoàn chỉnh hoặc không có gap.**

Một thiết kế vững chắc phân biệt `releasePartialSequences` và `sendPartialResultOnExpiry`, có **deadline watcher** cho trường hợp không message nào tới, xác thực metadata, lưu state/tombstone cho late replies, giới hạn bộ nhớ, retry/replay có idempotency và kiểm thử đúng thứ tự *lẫn* những output phải bị giữ lại. Kết hợp Filter/Transformer để chuẩn hóa đầu vào, Router/Gateway cho nhánh nghiệp vụ, Splitter/Aggregator khi xử lý nhiều phần, error channel và observability để hệ thống xử lý mất thứ tự mà **không âm thầm áp sai các bước phụ thuộc**.

**Tài liệu tham khảo:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Resequencer, Message Sequence, Correlation Identifier, Aggregator); Spring Integration Reference — [Resequencer](https://docs.spring.io/spring-integration/reference/resequencer.html), [Aggregators and Resequencers (Java DSL)](https://docs.spring.io/spring-integration/reference/dsl/java-aggregators.html), [Aggregator / Expiring Groups](https://docs.spring.io/spring-integration/reference/aggregator.html); Spring Integration Javadoc `ResequencerSpec`, `CorrelationHandlerSpec` và `AbstractCorrelatingMessageHandler`.

