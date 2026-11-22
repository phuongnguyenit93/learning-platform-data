# Chi phí thay đổi lịch sử, xây lại projection và vận hành

CQRS và Event Sourcing có thể giúp một hệ thống biểu diễn lịch sử nghiệp vụ rõ ràng, xây nhiều mô hình đọc và tái tạo trạng thái từ những sự kiện đã xảy ra. Nhưng các khả năng đó đi kèm chi phí dài hạn. Khi event đã được ghi và trở thành dữ liệu có thẩm quyền, cấu trúc và ý nghĩa của nó có thể được nhiều phiên bản ứng dụng, projection và consumer sử dụng trong nhiều năm. Thay đổi một quy tắc hoặc schema vì vậy không đơn giản là sửa một class rồi triển khai lại.

Một hệ thống Event Sourcing cần giải quyết những câu hỏi như: event cũ được đọc bằng code mới thế nào, khi nào cần upcast hoặc migration, snapshot có thực sự cần thiết không, projection có thể rebuild trong bao lâu, replay có gây gửi email hoặc thu tiền lần nữa không, dữ liệu cá nhân trong lịch sử được lưu và xóa theo chính sách nào, và đội vận hành phát hiện event stream bị lỗi bằng cách nào?

Bài học này tập trung vào **chi phí thay đổi lịch sử, xây lại projection và vận hành**. Mục tiêu là giúp bạn đánh giá tổng chi phí vòng đời trước khi chọn Event Sourcing, thiết kế đường tiến hóa dữ liệu và chuẩn bị quy trình phục hồi. Event Store không chỉ là một database khác; nó trở thành một phần quan trọng của hợp đồng nghiệp vụ và năng lực vận hành của hệ thống.

## Sau bài học này

Bạn có thể:

- Phân biệt CQRS với Event Sourcing và nhận biết khi nào chỉ cần một trong hai.
- Giải thích vì sao event đã ghi không nên bị sửa hoặc xóa tùy tiện.
- Chọn chiến lược tiến hóa event schema: tương thích ngược, upcasting hoặc migration.
- Hiểu vai trò và giới hạn của snapshot.
- Xây lại projection an toàn, có checkpoint và có khả năng chuyển đổi không gián đoạn.
- Ngăn replay tạo lại side effect như gửi email, thu tiền hoặc phát Integration Event.
- Thiết kế idempotency, thứ tự event và xử lý stream version.
- Đánh giá chi phí lưu trữ, truy vấn, backup, restore, privacy và retention.
- Theo dõi event store, projection lag, dead-letter và khả năng phục hồi.
- Quyết định có nên dùng Event Sourcing dựa trên giá trị nghiệp vụ và chi phí sở hữu.

## 1. CQRS và Event Sourcing giải quyết hai vấn đề khác nhau

Hai khái niệm thường được triển khai cùng nhau nhưng không đồng nghĩa.

**CQRS (Command Query Responsibility Segregation)** tách trách nhiệm xử lý thay đổi và truy vấn. Command side xử lý ý định thay đổi trạng thái; query side trả dữ liệu theo nhu cầu đọc. Hai phía có thể dùng cùng database, cùng ứng dụng và cùng mô hình lưu trữ.

**Event Sourcing** lưu các sự kiện đã xảy ra làm nguồn dữ liệu có thẩm quyền của aggregate. Trạng thái hiện tại được tái dựng bằng cách áp dụng chuỗi event theo thứ tự. Một lần ghi thường append event mới vào stream thay vì ghi đè toàn bộ trạng thái hiện tại.

| Câu hỏi | CQRS | Event Sourcing |
| --- | --- | --- |
| Tách đọc và ghi? | Có, đó là trọng tâm. | Không bắt buộc. |
| Lưu lịch sử thay đổi? | Không bắt buộc. | Có, event stream là nguồn sự thật. |
| Có thể dùng database quan hệ thông thường? | Có. | Có thể, nếu thiết kế được append-only event store phù hợp. |
| Có cần projection? | Có thể có. | Thường có để phục vụ truy vấn, nhưng không phải mọi query đều cần read database riêng. |
| Có cần replay? | Không nhất thiết. | Có thể replay event để dựng lại state hoặc projection. |
| Chi phí chính | Tách handler, mapping và có thể tách read model. | Thêm event schema evolution, replay, snapshot, event-store operations và data governance. |

Có thể dùng CQRS mà không dùng Event Sourcing: command handler cập nhật aggregate vào bảng trạng thái hiện tại, query handler đọc projection. Cũng có thể dùng Event Sourcing nhưng chưa cần tách dịch vụ đọc và ghi thành hai hệ thống riêng.

### Đừng chọn Event Sourcing chỉ vì muốn có audit log

Nếu mục tiêu chỉ là biết ai đã sửa một số trường và vào lúc nào, audit table hoặc change log có thể đủ. Event Sourcing phù hợp hơn khi lịch sử các sự kiện có ý nghĩa nghiệp vụ, có thể tái dựng trạng thái, cần xem lại quyết định theo thời gian hoặc cần nhiều projection độc lập.

Event log kỹ thuật và event stream nghiệp vụ cũng khác nhau. Log ghi thông tin phục vụ chẩn đoán; event nghiệp vụ phải có tên, ngữ nghĩa, identity và quy tắc tiến hóa rõ ràng.

## 2. Event history trở thành dữ liệu có thẩm quyền

Trong mô hình lưu trạng thái thông thường, một bản ghi Order có thể được cập nhật từ ACCEPTED sang CONFIRMED. Giá trị trước đó có thể không còn trong bảng chính. Với Event Sourcing, hệ thống append event như OrderPlaced, StockReserved và OrderConfirmed. Trạng thái hiện tại được dựng từ lịch sử đó.

Ví dụ một stream:

~~~text
Order-1042
  version 1: OrderPlaced
  version 2: AddressChanged
  version 3: StockReserved
  version 4: OrderConfirmed
~~~

Event stream có identity và thứ tự. Version thường tăng theo từng event trong stream. Việc append thường yêu cầu expected version để ngăn hai command cùng ghi dựa trên một trạng thái cũ.

### Tại sao lịch sử không nên bị sửa tùy tiện?

Event mô tả một sự thật đã được ghi nhận. Nếu thay đổi payload hoặc xóa event cũ mà không có quy trình, bạn có thể:

- Làm mất bằng chứng về quyết định đã xảy ra.
- Khiến projection mới tính ra kết quả khác projection cũ mà không giải thích được.
- Làm sai dữ liệu đã được consumer bên ngoài xử lý.
- Khiến audit, báo cáo và đối soát không còn tái hiện được.
- Làm snapshot không còn khớp với stream.

Nếu một sự kiện trước đây sai, thông thường hãy ghi một event điều chỉnh hoặc bù trừ diễn đạt sự thật mới. Ví dụ, nếu đã ghi PaymentCaptured với số tiền sai, nghiệp vụ có thể cần PaymentRefunded hoặc PaymentAdjustmentRecorded theo quy trình được phê duyệt. Không nên sửa lịch sử như thể khoản thu sai chưa từng xảy ra.

### Event sourcing không có nghĩa mọi thứ đều bất biến tuyệt đối

Hệ thống vẫn cần xử lý retention, dữ liệu cá nhân, yêu cầu pháp lý, lỗi ghi nhận và migration. Nhưng việc thay đổi event đã ghi phải là quy trình được kiểm soát, có audit và đánh giá ảnh hưởng đến consumer, projection, snapshot và bản sao lưu. “Append-only” là nguyên tắc thiết kế cho lịch sử nghiệp vụ, không phải lý do để bỏ qua nghĩa vụ quản trị dữ liệu.

## 3. Chi phí thay đổi quy tắc nghiệp vụ

Giả sử phiên bản đầu của hệ thống chỉ cho phép một lần xác nhận đơn. Sau đó doanh nghiệp bổ sung xác nhận từng phần, hoặc cho phép hủy một dòng hàng sau khi các dòng khác đã được giao.

Với database trạng thái hiện tại, có thể thêm cột, bảng hoặc cập nhật quy tắc ghi. Với Event Sourcing, cần xác định:

- Event cũ có còn mang ý nghĩa đúng không?
- Aggregate mới có thể replay chuỗi event cũ không?
- Quy tắc mới cần thêm event type hay chỉ thay đổi cách xử lý command?
- Projection cũ có cần tính lại không?
- Consumer tích hợp có hiểu event mới không?
- Snapshot cũ có còn sử dụng được không?
- Báo cáo lịch sử phải phản ánh quy tắc tại thời điểm xảy ra hay quy tắc hiện tại?

### Không được áp dụng quy tắc hiện tại một cách mù quáng lên quá khứ

Một event ghi nhận sự thật theo ngữ cảnh và chính sách có hiệu lực tại thời điểm đó. Nếu chính sách hoàn tiền thay đổi từ 30 ngày thành 14 ngày, replay một event OrderPlaced của hai năm trước không nên tự diễn giải lại điều kiện đủ hạn hoàn tiền theo quy tắc hiện tại rồi làm biến đổi lịch sử.

Cần phân biệt:

- **Sự thật lịch sử:** điều gì đã xảy ra và dữ liệu nào được ghi nhận.
- **Quy tắc hiện hành:** command mới được chấp nhận theo chính sách hiện tại.
- **Quy tắc diễn giải lịch sử:** cách projection hoặc báo cáo đọc event cũ.
- **Quy tắc điều chỉnh:** cách sửa một sai lệch đã phát hiện sau đó.

Nếu kết quả phụ thuộc chính sách tại thời điểm giao dịch, event có thể cần lưu policy version, rate, giá trị đã chốt hoặc các dữ kiện đầu vào quan trọng. Không nên chỉ lưu reference đến cấu hình hiện tại rồi kỳ vọng có thể tái hiện quyết định cũ.

## 4. Tiến hóa event schema

Event schema (cấu trúc sự kiện) là hợp đồng giữa code hiện tại và lịch sử đã lưu. Khi schema thay đổi, hệ thống phải tiếp tục đọc được event cũ hoặc có một quy trình chuyển đổi rõ ràng.

Ví dụ phiên bản đầu:

~~~json
{
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "orderId": "ORD-1042",
  "total": 1200000
}
~~~

Sau này, doanh nghiệp cần lưu loại tiền:

~~~json
{
  "eventType": "OrderPlaced",
  "eventVersion": 2,
  "orderId": "ORD-1042",
  "total": {
    "amount": "1200000",
    "currency": "VND"
  }
}
~~~

Đổi total từ số đơn giản sang object Money làm thay đổi schema và có thể phá vỡ code đọc phiên bản cũ.

### Chiến lược 1: thêm trường tương thích

Nếu có thể, bổ sung trường optional với default có ý nghĩa rõ ràng và giữ nguyên ý nghĩa trường cũ. Đây thường là cách ít rủi ro nhất, nhưng không phải thay đổi nào cũng tương thích.

Không nên thêm default tùy tiện. Ví dụ, thiếu currency không có nghĩa luôn là VND nếu hệ thống từng hỗ trợ nhiều loại tiền. Nếu không thể xác định đúng, cần migration hoặc xử lý event cũ bằng một chính sách được xác nhận.

### Chiến lược 2: upcasting

Upcaster chuyển event cũ sang một biểu diễn mới trong lúc đọc, mà không sửa bytes/event gốc trong event store. Ví dụ:

~~~java
public OrderPlacedV2 upcast(OrderPlacedV1 oldEvent) {
    return new OrderPlacedV2(
        oldEvent.orderId(),
        new Money(oldEvent.total(), Currency.VND)
    );
}
~~~

Đây là ví dụ chỉ đúng nếu nghiệp vụ xác nhận tất cả event V1 đều dùng VND. Upcaster cần xác định được phiên bản và ý nghĩa dữ liệu cũ; không được tự suy đoán giá trị bị thiếu.

Ưu điểm:

- Giữ nguyên lịch sử vật lý.
- Consumer mới có thể làm việc với một biểu diễn chuẩn hóa.
- Có thể triển khai từng bước mà không sửa event store ngay.

Chi phí:

- Phải duy trì và kiểm thử chuỗi upcaster.
- Đọc stream có thể cần nhiều bước chuyển đổi.
- Lỗi trong upcaster có thể ảnh hưởng mọi aggregate/projection đọc event cũ.
- Nhiều phiên bản schema làm tăng độ phức tạp vận hành.

### Chiến lược 3: migration event store

Một số trường hợp cần chuyển đổi dữ liệu lưu trữ vật lý. Đây là migration có rủi ro cao hơn vì có thể ảnh hưởng snapshot, backup, consumer và hệ thống đang đọc lịch sử.

Trước migration cần:

1. Xác định event type/version và số lượng bản ghi bị ảnh hưởng.
2. Xác định ngữ nghĩa chuyển đổi và dữ liệu không thể suy ra.
3. Kiểm thử trên bản sao dữ liệu đại diện.
4. Lưu backup và kế hoạch rollback/restore.
5. Xác định cách đồng bộ khi hệ thống vẫn nhận ghi.
6. Kiểm tra snapshot, projection và consumer.
7. Có báo cáo đối soát trước và sau.

Không nên dùng migration vật lý chỉ để tránh viết upcaster nếu lợi ích không bù được rủi ro.

### So sánh chiến lược tiến hóa

| Chiến lược | Khi phù hợp | Chi phí/rủi ro |
| --- | --- | --- |
| Thay đổi tương thích | Thêm trường optional hoặc metadata có default chắc chắn | Không giải quyết được thay đổi ngữ nghĩa lớn. |
| Upcasting | Cần đọc nhiều phiên bản cũ theo mô hình mới | Chuỗi chuyển đổi tích lũy, chi phí replay và kiểm thử. |
| Migration vật lý | Cần chuẩn hóa dữ liệu lưu trữ hoặc loại bỏ định dạng cũ | Rủi ro cao, cần backup, cutover và đối soát. |
| Event type/version mới | Ngữ nghĩa mới khác đáng kể, cần phân biệt rõ | Consumer phải hỗ trợ nhiều event type hoặc có adapter chuyển đổi. |

## 5. Version hóa event và aggregate stream

Không nên nhầm các loại version:

- **Event schema version:** phiên bản cấu trúc của một loại event.
- **Stream version/sequence:** vị trí event trong stream của aggregate.
- **Aggregate model version:** phiên bản logic của mô hình code nếu đội có quy ước riêng.
- **Projection version:** phiên bản cấu trúc hoặc logic của read model.

Một event có schema version 2 vẫn có thể là event thứ 17 trong stream của aggregate. Hai con số phục vụ mục đích khác nhau.

### Expected version bảo vệ ghi đồng thời

Khi load aggregate, hệ thống biết stream đang ở version 12. Sau khi xử lý command, nó append event mới với điều kiện expected version vẫn là 12. Nếu một request khác đã append event 13 trước đó, thao tác append phải thất bại do conflict.

~~~text
Load stream at version 12
Apply command
Append event with expectedVersion = 12
  -> success if current version is still 12
  -> conflict if another writer has advanced the stream
~~~

Application có thể tải lại stream, đánh giá lại command và thử lại nếu an toàn. Không được tự động áp dụng event đã tính từ trạng thái cũ lên stream mới mà không chạy lại logic nghiệp vụ.

### Một aggregate stream cần thứ tự rõ ràng

Event trong một stream phải được áp dụng theo thứ tự nghiệp vụ đã ghi. Nếu event store phân vùng theo aggregate ID hoặc stream ID, cần bảo đảm sequence trong stream không bị đảo. Không nhất thiết phải có thứ tự toàn cục giữa mọi aggregate; yêu cầu thứ tự nên được xác định theo consistency boundary.

## 6. Snapshot: tăng tốc khôi phục aggregate

Nếu một aggregate có hàng chục nghìn event, mỗi lần tải có thể phải replay toàn bộ stream. Snapshot lưu trạng thái đã dựng tại một version để giảm số event cần đọc.

Ví dụ:

~~~text
Event stream:
  v1 ... v10000

Snapshot:
  state at version 9500

Rehydrate:
  load snapshot at v9500
  apply events v9501 ... v10000
  -> current aggregate state
~~~

### Snapshot không thay thế event history

Snapshot là dữ liệu dẫn xuất để tăng tốc. Event stream vẫn là nguồn lịch sử có thẩm quyền. Nếu snapshot hỏng hoặc không tương thích, có thể bỏ và tạo lại từ event history.

Không nên xem snapshot là bản backup duy nhất. Snapshot thường không chứa đầy đủ lịch sử, lý do và dữ liệu cần để dựng các projection khác.

### Khi nào cần snapshot?

Snapshot có thể hữu ích khi:

- Stream của một aggregate dài và tải thường xuyên.
- Replay từ đầu gây độ trễ đáng kể.
- Có yêu cầu latency rõ cho command cần tải aggregate.
- Chi phí đọc event vượt ngưỡng vận hành chấp nhận được.

Không cần snapshot cho mọi aggregate. Stream ngắn hoặc tải hiếm có thể replay trực tiếp đơn giản hơn.

### Snapshot phải gắn với version và schema

Snapshot nên lưu:

- Aggregate/stream ID.
- Stream version đã áp dụng.
- Snapshot schema/model version.
- Payload trạng thái.
- Thời điểm tạo và metadata cần thiết.

Khi load, hệ thống phải xác nhận snapshot tương thích với mô hình hiện tại. Nếu không, cần upcast/migrate snapshot hoặc bỏ snapshot và replay từ event history.

### Snapshot không sửa được projection

Snapshot aggregate dùng để tăng tốc tái dựng một aggregate. Nó không tự động thay thế dữ liệu đầu vào để rebuild mọi read projection. Projection có thể tổng hợp dữ liệu từ nhiều aggregate và cần xử lý event theo quy tắc riêng. Muốn rebuild projection, thông thường phải đọc event history liên quan hoặc một nguồn dữ liệu đầy đủ khác.

## 7. Projection là dữ liệu dẫn xuất

Projection là mô hình đọc được tạo từ event hoặc từ nguồn dữ liệu khác. Ví dụ:

- OrderSummary cho màn hình danh sách đơn.
- CustomerOrderHistory cho hồ sơ khách hàng.
- DailySalesTotals cho báo cáo doanh thu.
- InventoryAvailabilityView cho trang tra cứu hàng.

Một event có thể cập nhật nhiều projection. Mỗi projection phục vụ một câu hỏi đọc khác nhau và có thể có cấu trúc riêng.

~~~mermaid
flowchart TD
    E[Event Store]
    P1[Order Summary Projector]
    P2[Customer History Projector]
    P3[Daily Sales Projector]
    R1[(Order Read Store)]
    R2[(Customer Read Store)]
    R3[(Analytics Store)]
    E --> P1 --> R1
    E --> P2 --> R2
    E --> P3 --> R3
~~~

Projection không phải nguồn sự thật. Nếu projection bị sai hoặc schema thay đổi, có thể rebuild từ event history nếu event còn đủ dữ liệu và logic chuyển đổi được kiểm soát.

### Projection có thể được tạo theo hai cách

**Inline projection** cập nhật cùng luồng xử lý ghi hoặc cùng transaction. Cách này có thể giảm độ trễ nhưng làm write path phụ thuộc vào projection.

**Async projection** tiêu thụ event sau commit. Cách này tách tải đọc/ghi và cho phép retry độc lập, nhưng tạo eventual consistency và cần theo dõi lag.

Đừng mặc định projection nào cũng phải async. Chọn theo yêu cầu độ trễ, khả năng chịu lỗi và mức độ độc lập mong muốn.

## 8. Vì sao phải rebuild projection?

Projection có thể cần xây lại khi:

- Logic tính toán bị sai và đã được sửa.
- Bổ sung field hoặc thay đổi cấu trúc read model.
- Cần một màn hình/báo cáo mới.
- Dữ liệu projection bị hỏng hoặc mất.
- Thay đổi quy tắc tổng hợp.
- Cần kiểm tra lại lịch sử theo một phiên bản logic đã được phê duyệt.

Rebuild là khả năng quan trọng của Event Sourcing, nhưng không miễn phí. Nếu event history lớn, projection cần nhiều thời gian đọc, CPU, network và ghi dữ liệu. Trong lúc rebuild, hệ thống còn phải xử lý event mới để không bị tụt mãi phía sau.

### Tách replay để dựng projection khỏi side effect

Một projector chỉ nên cập nhật read model và checkpoint. Replay không được gửi email, thu tiền, gọi API đối tác hoặc phát Integration Event như thể nghiệp vụ vừa xảy ra.

Nếu một event handler vừa cập nhật projection vừa gọi dịch vụ ngoài, rebuild có thể tạo hàng nghìn tác động lặp. Hãy tách:

- Projection handler: tính dữ liệu dẫn xuất, có thể chạy lại.
- Domain/application workflow: xử lý command mới và side effect thật.
- Integration publisher: gửi event đã được ghi bền vững qua outbox theo luồng live.

### Replay phải xác định rõ nguồn và phạm vi

Trước khi rebuild, xác định:

- Event store/stream nào là nguồn dữ liệu có thẩm quyền?
- Có cần replay toàn bộ stream hay chỉ một nhóm aggregate?
- Có cần lọc event type hoặc thời gian không?
- Event nào bị bỏ qua và vì sao?
- Projection logic version nào đang được dùng?
- Dữ liệu nào cần giữ để đối soát với projection hiện tại?

Không nên replay một phần tùy ý nếu projection phụ thuộc vào thứ tự hoặc tổng hợp toàn cục mà phần event còn lại không đủ để tính đúng.

## 9. Checkpoint và xử lý event lặp

Projector thường lưu checkpoint để biết đã xử lý đến vị trí nào. Checkpoint có thể là global position của event store, partition offset hoặc stream version tùy cơ chế.

Điểm quan trọng là cập nhật projection và checkpoint phải nhất quán. Nếu checkpoint được ghi trước khi projection commit, event có thể bị bỏ qua sau khi restart. Nếu projection commit nhưng checkpoint chưa cập nhật, event có thể được xử lý lại.

### Idempotent projection

Một projector nên có khả năng áp dụng event lặp mà không làm sai dữ liệu. Có thể dùng:

- Event ID đã xử lý.
- Aggregate stream version.
- Upsert theo khóa nghiệp vụ.
- Cập nhật projection và checkpoint trong cùng transaction.
- Tính lại giá trị từ event thay vì cộng dồn không kiểm soát.

Ví dụ projector:

~~~java
public void apply(OrderConfirmed event) {
    transaction.required(() -> {
        if (processedEvents.exists(event.eventId())) {
            return;
        }

        orderSummary.upsertConfirmed(
            event.orderId(),
            event.confirmedAt()
        );
        processedEvents.markProcessed(event.eventId());
        checkpoint.advance(event.globalPosition());
    });
}
~~~

Đây là ví dụ minh họa. Ba cập nhật projection, event marker và checkpoint cần cùng transactional boundary nếu chúng được lưu trong một database. Nếu checkpoint nằm ở broker riêng, cần thiết kế ack/commit và deduplication tương ứng.

### Event đến sai thứ tự

Nếu projection nhận event version 8 trước version 7, cách xử lý phụ thuộc projection:

- Nếu cần thứ tự tuyệt đối theo aggregate, giữ lại hoặc retry event 8 cho đến khi version 7 được áp dụng.
- Nếu event chứa state đủ để upsert và version lớn hơn, có thể chỉ áp dụng version mới hơn.
- Nếu projection là phép cộng dồn, bỏ event 7 có thể làm sai tổng; cần xử lý gap hoặc rebuild.

Không thể chọn một chiến lược chung cho mọi projection. Hãy xác định tính chất phép chiếu và yêu cầu thứ tự.

## 10. Rebuild an toàn với blue-green projection

Không nên xóa projection đang phục vụ người dùng rồi rebuild trực tiếp nếu quá trình mất nhiều thời gian. Một chiến lược phổ biến là tạo projection phiên bản mới song song.

~~~mermaid
flowchart TD
    A[Live Event Stream]
    B[Projection V1 - đang phục vụ]
    C[Projection V2 - đang rebuild]
    D[Replay lịch sử vào V2]
    E[Catch up event mới]
    F{V2 đã bắt kịp và đối soát đạt?}
    G[Chuyển read traffic sang V2]
    H[Giữ V1 tạm thời để rollback]
    A --> B
    A --> C
    D --> C
    A --> E --> C
    C --> F
    F -->|Có| G --> H
    F -->|Chưa| E
~~~

Một quy trình triển khai có thể gồm:

1. Tạo read store hoặc namespace projection V2.
2. Chốt một event position làm mốc bắt đầu.
3. Replay lịch sử đến mốc đó vào V2.
4. Đồng thời lưu hoặc tiêu thụ các event phát sinh sau mốc.
5. Catch up V2 đến gần live head.
6. Đối soát số lượng, tổng hợp và các invariant của projection.
7. Chuyển read traffic sang V2 bằng cấu hình/alias có kiểm soát.
8. Theo dõi lỗi và độ trễ sau cutover.
9. Giữ V1 trong thời gian rollback đã định rồi mới dọn.

Chi tiết cách đồng bộ live event phụ thuộc event store và broker. Cần tránh gap giữa mốc replay và luồng mới, cũng như tránh áp dụng trùng mà không idempotent.

### Rebuild projection không nên ảnh hưởng write path

Replay có thể tạo tải đọc rất lớn. Cần giới hạn tốc độ, chạy theo batch, ưu tiên tài nguyên cho command path và theo dõi database/broker. Nếu rebuild làm chậm thao tác ghi quan trọng, phải có throttle hoặc chạy trên bản sao dữ liệu phù hợp.

### Đối soát trước cutover

Không chỉ so sánh số dòng. Cần so sánh các chỉ số nghiệp vụ quan trọng:

- Tổng số đơn theo trạng thái.
- Tổng tiền theo currency và kỳ.
- Số lượng khách hàng có giao dịch.
- Tổng reservation đang mở.
- Số event đã xử lý và checkpoint cuối.
- Một tập mẫu aggregate được tính lại độc lập.

Nếu V1 và V2 khác nhau, cần xác định đó là lỗi cũ được sửa, thay đổi định nghĩa nghiệp vụ hay bug mới. Không nên chuyển traffic chỉ vì rebuild đã chạy đến cuối stream.

## 11. Projection versioning và thay đổi logic

Khi cấu trúc hoặc cách tính read model thay đổi, nên nhận diện version của projection. Ví dụ OrderSummaryV1 có trường total, còn V2 tách subtotal, tax và shippingFee.

Không nên ghi đè projection hiện tại trong lúc chưa xác định consumer nào đang phụ thuộc schema cũ. Có thể:

- Tạo bảng/namespace V2 và chuyển traffic sau khi rebuild.
- Duy trì song song V1/V2 trong thời gian chuyển đổi.
- Dùng adapter chuyển đổi giữa projection nội bộ và API DTO.
- Version hóa API response nếu hợp đồng bên ngoài thực sự thay đổi.

### Thay đổi định nghĩa nghiệp vụ cần giải thích

Giả sử báo cáo “doanh thu ngày” trước đây tính theo thời điểm đặt đơn, sau này đổi sang thời điểm thu tiền. Rebuild projection sẽ tạo ra số liệu khác. Đây không chỉ là migration schema; đó là thay đổi định nghĩa chỉ số.

Hãy lưu projection logic version, tài liệu định nghĩa chỉ số và thời điểm áp dụng. Báo cáo lịch sử có thể cần phân biệt số liệu được tính theo quy tắc cũ và quy tắc mới.

## 12. Side effect và replay an toàn

Replay là chạy lại event qua một phần logic. Nếu logic đó có side effect, replay có thể làm lặp tác động.

Ví dụ nguy hiểm:

- Replay OrderPlaced rồi gửi email xác nhận lần nữa.
- Replay PaymentCaptured rồi gọi payment provider capture thêm lần nữa.
- Replay ShipmentRequested rồi tạo shipment mới ở đối tác.
- Replay CustomerRegistered rồi gửi welcome reward lần nữa.

### Tách handler theo mục đích

Một cách tổ chức:

| Handler | Mục đích | Có nên chạy khi rebuild? |
| --- | --- | --- |
| Aggregate rehydration | Tái dựng trạng thái aggregate từ event stream | Có |
| Projection handler | Tạo read model/checkpoint | Có |
| Audit/report projection | Tính dữ liệu dẫn xuất | Có, nếu replay được kiểm soát |
| Email/notification handler | Gửi thông báo thật | Không tự động |
| Payment/shipping integration handler | Gọi hệ thống ngoài | Không tự động |
| Live process manager | Điều phối command mới và bước tiếp theo | Chỉ chạy theo cơ chế workflow, không bật side effect khi replay projection |

### Chế độ replay phải rõ ràng

Không nên chỉ truyền một boolean replayMode khắp code rồi hy vọng mọi handler kiểm tra đúng. Tốt hơn là tách pipeline và quyền thực thi:

- Projection rebuild chạy bằng consumer/handler chỉ có quyền ghi read store.
- Live integration workflow chạy bằng worker có quyền gửi command hoặc gọi hệ thống ngoài.
- Replay job không có credential cần thiết để thu tiền hoặc gửi thông báo.
- Nếu cần phát lại Integration Event, dùng một quy trình replay riêng có phê duyệt, idempotency và phạm vi cụ thể.

### Replay event không có nghĩa phát lại mọi Integration Event

Một Integration Event đã được công bố có thể đã được consumer bên ngoài xử lý. Rebuild projection nội bộ không nên phát lại event đó. Nếu cần consumer mới nhận lịch sử, hãy cung cấp event archive/replay channel riêng hoặc tạo snapshot/export có version và thông báo rõ semantics cho consumer.

## 13. Chi phí lưu trữ và truy vấn Event Store

Event Store thường tăng trưởng theo số lượng sự kiện, không chỉ theo số lượng aggregate hiện tại. Một aggregate hoạt động lâu có thể có stream dài; một hệ thống giao dịch lớn có thể tạo lượng event rất lớn mỗi ngày.

Các chi phí cần tính:

- Dung lượng payload và metadata.
- Index theo stream ID, event type, global position và thời gian.
- Chi phí replication, backup và restore.
- Chi phí đọc stream để tái dựng aggregate.
- Chi phí chạy projection và replay.
- Chi phí lưu schema, upcaster và tooling tương thích.
- Chi phí vận hành, cảnh báo, xử lý lỗi và đối soát.

### Không phải mọi thay đổi kỹ thuật đều cần thành domain event

Nếu một field cache, heartbeat hoặc telemetry thay đổi liên tục nhưng không có ý nghĩa nghiệp vụ, không nên đưa nó vào event stream chỉ vì hệ thống đang dùng Event Sourcing. Event cần diễn đạt sự thật nghiệp vụ có giá trị và có vòng đời rõ.

### Phân vùng và truy vấn

Event Store thường tối ưu cho đọc stream theo aggregate ID và append event theo thứ tự. Truy vấn dạng “tìm mọi đơn của khách hàng X có trạng thái Y” có thể không phù hợp với event store thuần. Read model/projection được thiết kế cho truy vấn đó.

Không nên coi event store là database báo cáo tổng quát. Việc scan toàn bộ event history cho mỗi màn hình sẽ làm tăng độ trễ và tải.

### Stream dài và aggregate nóng

Stream quá dài làm tải aggregate tốn thời gian. Một aggregate có tần suất ghi rất cao có thể trở thành điểm nóng do các command phải tuần tự hóa theo stream version. Snapshot có thể giảm chi phí đọc nhưng không giải quyết được contention khi ghi.

Nếu aggregate liên tục bị ghi đồng thời, cần xem lại consistency boundary, cách phân chia trách nhiệm hoặc mô hình command. Không nên chỉ thêm snapshot để giải quyết vấn đề ghi.

## 14. Backup, restore và disaster recovery

Event Store là nguồn dữ liệu có thẩm quyền nên backup và phục hồi cần được kiểm thử kỹ.

Một kế hoạch cần xác định:

- Backup event store, metadata, schema registry và cấu hình liên quan.
- Mức replication và vùng lỗi được bảo vệ.
- Recovery Point Objective (RPO): có thể mất tối đa bao nhiêu dữ liệu đã commit?
- Recovery Time Objective (RTO): hệ thống cần phục hồi trong bao lâu?
- Cách khôi phục checkpoint của projector.
- Cách xác minh stream sequence không bị thiếu hoặc trùng.
- Cách rebuild projection sau restore.
- Cách phối hợp với outbox, broker và consumer offset.

### Restore event store và projection

Nếu event store được restore về thời điểm T nhưng read store hoặc broker offset ở thời điểm T+1, có thể xuất hiện trạng thái không đồng bộ. Cần xác định nguồn nào được xem là có thẩm quyền và cách đưa projection/checkpoint về vị trí tương thích.

Một cách an toàn là phục hồi event store, xác minh stream, tạo projection mới từ nguồn đã phục hồi, sau đó bắt kịp event mới và chuyển traffic. Quy trình cụ thể phụ thuộc RPO/RTO và kiến trúc lưu trữ.

### Backup phải được kiểm thử bằng restore

Backup thành công không chứng minh có thể phục hồi. Cần chạy diễn tập restore định kỳ, đo thời gian, kiểm tra checksum/sequence và đối soát các aggregate/projection mẫu.

## 15. Privacy, retention và yêu cầu xóa dữ liệu

Event history có thể chứa dữ liệu cá nhân hoặc dữ liệu nhạy cảm. Vì event thường được lưu lâu và sao chép qua backup, broker, projection và log, việc xóa dữ liệu sau này phức tạp hơn một bảng CRUD thông thường.

Ngay từ thiết kế cần:

- Chỉ ghi dữ liệu thực sự cần để tái hiện nghiệp vụ.
- Hạn chế đưa thông tin nhạy cảm trực tiếp vào event payload.
- Dùng reference đến hồ sơ được quản lý riêng khi phù hợp.
- Xác định retention theo loại event và nghĩa vụ pháp lý.
- Kiểm soát quyền đọc event store và log.
- Mã hóa dữ liệu khi lưu và khi truyền.
- Có quy trình xử lý yêu cầu xóa/ẩn danh theo luật và chính sách áp dụng.

### Tách dữ liệu định danh khỏi event khi có thể

Thay vì ghi tên, email và số điện thoại vào mọi event, event có thể chứa CustomerId. Hồ sơ cá nhân được lưu trong context có quyền quản lý và có chính sách xóa riêng. Tuy nhiên, cách này chỉ phù hợp nếu event vẫn có thể được diễn giải đúng sau khi hồ sơ bị xóa hoặc ẩn danh.

### Crypto-shredding và giới hạn của nó

Một số hệ thống mã hóa phần dữ liệu cá nhân bằng khóa riêng theo subject/customer. Khi cần xóa theo chính sách, có thể hủy khóa để dữ liệu đã mã hóa không còn giải mã được. Đây là kỹ thuật có thể hỗ trợ privacy, nhưng cần thiết kế từ đầu và được đánh giá pháp lý/bảo mật.

Crypto-shredding không tự động xóa mọi bản sao plaintext, log, cache, export hoặc backup đã giải mã. Cũng cần xem xét metadata còn có thể nhận diện cá nhân hay không. Không nên coi đây là giải pháp thay thế toàn diện cho retention và data deletion policy.

### Tombstone hoặc event xóa

Có thể ghi event như CustomerPersonalDataErased để các projection và consumer biết cần xóa/ẩn danh dữ liệu liên quan. Event này không nhất thiết xóa mọi event lịch sử; cách xử lý phải phù hợp nghĩa vụ pháp lý và chính sách lưu trữ. Một số dữ liệu giao dịch có thể phải giữ vì yêu cầu kế toán/pháp lý, trong khi thông tin liên hệ có thể cần xóa.

### Backup và bản sao

Chính sách xóa phải tính đến backup, replica, event archive, data warehouse, message retention và dead-letter queue. Cần xác định thời hạn dữ liệu được loại khỏi bản sao lưu theo vòng đời backup và cách ngăn dữ liệu bị phục hồi trở lại sau khi đã xử lý yêu cầu xóa.

## 16. Vận hành Event Store và projection

Event Sourcing làm tăng số thành phần cần quan sát. Ngoài database, hệ thống có thể có event store, projection workers, checkpoint store, schema registry, outbox/inbox, broker và read database.

### Các chỉ số cần theo dõi

| Khu vực | Chỉ số/quan sát | Điều cần phát hiện |
| --- | --- | --- |
| Event Store | Append latency, read latency, lỗi expected-version, stream growth | Ghi chậm, conflict tăng, stream bất thường. |
| Projection | Lag, processing rate, lỗi theo event type, checkpoint age | Read model bị trễ hoặc dừng. |
| Replay | Số event đã xử lý, tốc độ, ETA, lỗi upcast | Rebuild không tiến triển hoặc quá tải. |
| Outbox | Số message pending và tuổi message lâu nhất | Event chưa được publish. |
| Inbox/consumer | Duplicate count, retry, dead-letter | Consumer lỗi hoặc message không hợp lệ. |
| Storage | Dung lượng, tăng trưởng, index, backup age | Hết dung lượng hoặc không đáp ứng retention. |
| Workflow | Process pending quá hạn, compensation thất bại | Quy trình liên context bị kẹt. |

Không chỉ đo số event mỗi giây. Cần đo độ trễ từ lúc event xảy ra đến khi read model hoặc workflow hoàn tất, vì đó là điều người dùng và nghiệp vụ cảm nhận.

### Cảnh báo cần gắn với hành động

Một alert hữu ích phải chỉ rõ:

- Projection nào đang trễ và checkpoint cuối là gì?
- Event type nào gây lỗi?
- Có bao nhiêu message trong dead-letter?
- Stream/aggregate nào gặp expected-version conflict bất thường?
- Rebuild job đang ở batch nào?
- Có quy trình nghiệp vụ nào pending quá deadline?
- Ai sở hữu context cần xử lý?

Alert chỉ báo “consumer lag cao” nhưng không có runbook hoặc owner sẽ khó giúp đội phục hồi.

## 17. Runbook cho replay và rebuild

Một quy trình rebuild có thể được chuẩn hóa:

1. Xác định mục tiêu: sửa bug, thay schema hay tạo read model mới.
2. Xác định projection version và phạm vi event cần replay.
3. Kiểm tra event history, upcaster và snapshot tương thích.
4. Ước lượng dung lượng, thời gian và tải đọc/ghi.
5. Tạo projection store mới hoặc namespace riêng.
6. Chọn event position bắt đầu và lưu checkpoint ban đầu.
7. Chạy replay theo batch có giới hạn tài nguyên.
8. Theo dõi lỗi event, duplicate, lag và tốc độ xử lý.
9. Catch up event mới trong khi replay.
10. Đối soát các chỉ số và mẫu dữ liệu.
11. Chuyển traffic bằng cutover có kiểm soát.
12. Giữ bản projection cũ theo thời hạn rollback.
13. Ghi lại kết quả, version logic và các sai lệch đã xử lý.

### Khi replay thất bại giữa chừng

Không cần bắt đầu lại từ đầu nếu projector có checkpoint đáng tin cậy và thao tác idempotent. Có thể tiếp tục từ vị trí cuối đã commit. Nhưng nếu logic projector thay đổi hoặc dữ liệu đã được ghi sai, cần tạo namespace mới hoặc xóa/rebuild projection trong phạm vi an toàn; không chỉ tiếp tục checkpoint cũ với logic mới mà không đánh giá.

### Khi cần replay một phần

Replay một aggregate stream có thể phù hợp để kiểm tra hoặc tái dựng aggregate. Projection tổng hợp nhiều aggregate có thể cần toàn bộ event liên quan. Phải hiểu projection dependency trước khi chọn phạm vi.

## 18. Chi phí phát triển và kiểm thử

Event Sourcing đòi hỏi nhiều năng lực ngoài việc viết aggregate:

- Event contract và versioning.
- Event store adapter và concurrency control.
- Aggregate rehydration và snapshot.
- Upcaster và kiểm thử lịch sử cũ.
- Projection handler và checkpoint.
- Outbox/inbox, retry và dead-letter.
- Replay tooling và reconciliation.
- Backup/restore, retention và privacy.
- Monitoring, alert và runbook.

Mỗi event type mới có thể trở thành một hợp đồng tồn tại lâu. Đội cần xem xét event name, payload, semantics, version và consumer trước khi ghi event vào production.

### Bộ kiểm thử nên bao gồm

- Unit test cho command decision và aggregate invariant.
- Test rehydrate từ stream có event cũ.
- Test upcaster với từng schema version được hỗ trợ.
- Test snapshot tại nhiều stream version.
- Test projection replay và idempotency.
- Test checkpoint crash giữa lúc cập nhật projection.
- Test event đến trùng hoặc sai thứ tự.
- Test side effect không chạy trong replay.
- Test rebuild song song và cutover.
- Test backup/restore và reconciliation.
- Test retention, masking hoặc xóa dữ liệu theo chính sách.

Không nên chỉ test luồng command mới nhất trên database trống. Lỗi thường xuất hiện khi đọc lịch sử nhiều năm hoặc khi replay qua các phiên bản event khác nhau.

## 19. Khi nào Event Sourcing không đáng với chi phí?

Event Sourcing có giá trị khi lịch sử nghiệp vụ là tài sản quan trọng và cần được diễn giải, tái dựng hoặc khai thác theo nhiều cách. Nhưng không phải hệ thống nào cũng cần.

| Điều kiện | Event Sourcing có thể phù hợp | CRUD/audit log có thể đủ |
| --- | --- | --- |
| Cần lịch sử nghiệp vụ đầy đủ và có ý nghĩa | Rất phù hợp | Audit log có thể thiếu ngữ nghĩa để tái dựng. |
| Cần nhiều projection từ cùng lịch sử | Phù hợp | Có thể dùng CDC hoặc query projection nếu yêu cầu đơn giản. |
| Cần tái hiện trạng thái tại thời điểm trước | Phù hợp nếu event đủ dữ liệu và semantics ổn định | Có thể dùng temporal table/version history. |
| Quy tắc và schema thay đổi thường xuyên | Chi phí versioning/replay cao | CRUD thường dễ migration hơn. |
| Đội chưa có năng lực vận hành event store | Rủi ro cao | Bắt đầu với transaction database và audit phù hợp. |
| Dữ liệu chỉ là cấu hình CRUD đơn giản | Thường không cần | CRUD đơn giản phù hợp. |
| Side effect và workflow phân tán phức tạp | Có thể hữu ích nếu event là sự thật nghiệp vụ | Outbox + trạng thái hiện tại cũng có thể đáp ứng. |

### Tính tổng chi phí sở hữu

Không chỉ tính chi phí triển khai ban đầu. Hãy tính:

- Chi phí phát triển event schema và upcaster.
- Chi phí lưu trữ và backup lịch sử.
- Chi phí rebuild projection và phục hồi.
- Chi phí kiểm thử tương thích nhiều phiên bản.
- Chi phí hỗ trợ privacy/retention.
- Chi phí vận hành consumer, dead-letter và reconciliation.
- Chi phí onboarding để đội hiểu semantics và quy trình.

Nếu lợi ích audit/replay/projection không đủ bù, một mô hình trạng thái hiện tại cùng audit log có thể là lựa chọn tốt hơn.

## 20. Ví dụ xuyên suốt: thay đổi cách tính doanh thu

Giả sử hệ thống ban đầu tính doanh thu khi đơn được xác nhận. Sau một thời gian, doanh nghiệp quyết định chỉ tính doanh thu khi thanh toán được capture, đồng thời tách thuế và phí vận chuyển.

### Lịch sử event

~~~text
OrderPlaced
OrderConfirmed
PaymentCaptured
OrderCancelled
PaymentRefunded
~~~

### Projection V1

V1 cộng total khi nhận OrderConfirmed. V2 chỉ ghi nhận doanh thu khi PaymentCaptured, trừ các khoản refund và phân tách tax/shipping theo dữ liệu có trong event.

Đội cần xác định:

1. Event PaymentCaptured cũ có chứa đủ amount, currency và thời điểm không?
2. Refund event có reference đến capture gốc không?
3. Event lịch sử có chứa tax/shipping breakdown hay phải lấy từ snapshot khác?
4. Doanh thu được tính theo thời điểm capture hay theo ngày hạch toán?
5. Báo cáo cũ cần giữ nguyên hay được thay bằng định nghĩa mới?

Nếu dữ liệu cũ không đủ để tính V2 chính xác, không nên tự suy ra. Có thể cần migration/backfill từ nguồn có thẩm quyền, đánh dấu dữ liệu chưa đầy đủ hoặc duy trì hai định nghĩa báo cáo.

### Rebuild V2

1. Tạo SalesRevenueProjectionV2 riêng.
2. Replay event history bằng projector V2.
3. Dùng upcaster nếu schema event cũ có thể chuyển đổi an toàn.
4. Catch up event mới trong khi replay.
5. Đối soát với dữ liệu payment ledger có thẩm quyền.
6. Phân tích các chênh lệch và ghi nhận nguyên nhân.
7. Chuyển dashboard sang V2 sau khi owner nghiệp vụ phê duyệt.
8. Giữ V1 trong thời gian cần thiết để so sánh hoặc rollback.

Ví dụ này cho thấy thay đổi projection có thể là thay đổi định nghĩa nghiệp vụ, không chỉ là thêm một cột database.

## 21. Những sai lầm thường gặp

- **Coi event history như bảng có thể update tùy ý:** làm mất khả năng giải thích lịch sử.
- **Dùng Event Sourcing chỉ để có audit:** tạo chi phí replay/versioning không cần thiết.
- **Nhầm CQRS với Event Sourcing:** tách read/write không bắt buộc phải lưu event làm nguồn sự thật.
- **Thay đổi schema mà không version:** code mới có thể không đọc được lịch sử cũ.
- **Upcast bằng default suy đoán:** làm sai dữ liệu lịch sử.
- **Replay handler có side effect:** gửi lại email, thu tiền hoặc tạo shipment ngoài ý muốn.
- **Dùng snapshot thay event history:** snapshot không đủ để tái tạo mọi projection hoặc audit.
- **Không gắn snapshot với stream version/schema:** khôi phục từ snapshot sai mô hình.
- **Rebuild trực tiếp projection đang phục vụ:** gây downtime hoặc dữ liệu nửa cũ nửa mới.
- **Không đồng bộ checkpoint với projection:** bỏ sót hoặc áp dụng lặp event sau crash.
- **Không xử lý event sai thứ tự:** projection tổng hợp có thể sai dù từng event hợp lệ.
- **Replay toàn bộ lịch sử mà không giới hạn tải:** làm ảnh hưởng command path và database.
- **Không có backup/restore diễn tập:** event store có thể không phục hồi được khi sự cố.
- **Ghi quá nhiều dữ liệu cá nhân vào event:** khó đáp ứng retention và deletion.
- **Không có reconciliation:** projection hoặc workflow sai lệch tồn tại lâu.
- **Không version hóa định nghĩa chỉ số:** báo cáo lịch sử thay đổi mà không giải thích.
- **Không tính chi phí vận hành:** đội chỉ nhìn lợi ích kỹ thuật ban đầu mà bỏ qua chi phí vòng đời.

## 22. Quy trình thiết kế khả năng tiến hóa và vận hành

Khi chọn Event Sourcing hoặc thay đổi một hệ thống đang dùng nó, hãy thực hiện theo các bước:

1. **Xác nhận giá trị nghiệp vụ:** vì sao cần event history và khả năng replay?
2. **Xác định nguồn có thẩm quyền:** stream nào sở hữu sự thật và aggregate nào ghi event?
3. **Định nghĩa event contract:** tên, semantics, identity, schema version và metadata.
4. **Đặt quy tắc tiến hóa:** thay đổi tương thích, upcast hay migration; ai phê duyệt?
5. **Thiết kế rehydration:** aggregate đọc event cũ và snapshot theo version nào?
6. **Thiết kế projection:** mỗi read model có mục đích, schema version và owner rõ.
7. **Thiết kế replay an toàn:** projector không gọi side effect; checkpoint và idempotency được bảo vệ.
8. **Thiết kế rebuild/cutover:** chạy song song, catch up, đối soát và rollback.
9. **Đánh giá dữ liệu:** retention, PII, encryption, backup, archive và deletion.
10. **Đánh giá năng lực vận hành:** event-store growth, replay capacity, monitoring và runbook.
11. **Kiểm thử lịch sử:** event nhiều phiên bản, snapshot cũ, duplicate, ordering và crash recovery.
12. **Tính tổng chi phí sở hữu:** so sánh với CRUD, audit log hoặc outbox trước khi mở rộng.

## Checklist rà soát

- [ ] Đã xác định rõ lý do nghiệp vụ cần Event Sourcing.
- [ ] Không nhầm CQRS với Event Sourcing.
- [ ] Event history được coi là nguồn dữ liệu có thẩm quyền và không sửa tùy tiện.
- [ ] Event có semantics, identity và schema version rõ.
- [ ] Có chiến lược tương thích, upcasting hoặc migration cho event cũ.
- [ ] Không áp dụng quy tắc hiện tại lên quá khứ mà thiếu chính sách.
- [ ] Snapshot có stream version và schema version; có thể bỏ và tạo lại.
- [ ] Projection có version, owner và nguồn rebuild rõ.
- [ ] Replay không kích hoạt side effect hoặc Integration Event ngoài ý muốn.
- [ ] Projection update và checkpoint có cơ chế nhất quán.
- [ ] Consumer/projector idempotent và xử lý event sai thứ tự theo semantics.
- [ ] Rebuild có namespace mới, catch-up, đối soát và cutover có kiểm soát.
- [ ] Có giới hạn tài nguyên để replay không ảnh hưởng write path.
- [ ] Backup/restore đã được diễn tập và có RPO/RTO.
- [ ] Privacy, retention, deletion và backup copies được quản lý.
- [ ] Có monitoring cho event store, projection lag, outbox, dead-letter và workflow.
- [ ] Có runbook cho replay, rebuild, reconciliation và phục hồi.
- [ ] Tổng chi phí vòng đời đã được so sánh với phương án đơn giản hơn.

## Kết luận

Event Sourcing mang lại lịch sử nghiệp vụ có thể tái dựng và tạo nhiều projection, nhưng lịch sử đó trở thành hợp đồng dữ liệu dài hạn. Thay đổi event cần chiến lược tương thích, upcasting hoặc migration; snapshot chỉ tăng tốc rehydration và không thay thế event history; projection cần checkpoint, idempotency, replay an toàn và quy trình rebuild có đối soát. Vận hành còn bao gồm backup/restore, privacy, retention, monitoring và runbook. Chỉ nên chọn Event Sourcing khi giá trị của lịch sử và khả năng tái dựng đủ lớn để bù chi phí phát triển và vận hành trong suốt vòng đời hệ thống.
