# Replay có kiểm soát

Trong hệ thống dùng application events, replay là việc chủ động giao lại một event đã được lưu để một listener hoặc consumer xử lý thêm lần nữa. Replay giúp phục hồi sau lỗi, tái tạo read model và xử lý lại dữ liệu khi logic đã được sửa. Tuy nhiên, một event được giao lại có thể kích hoạt lại side effect như trừ tồn kho, gửi email hoặc thu tiền. Vì vậy replay cần có phạm vi rõ ràng, điều kiện trước khi chạy, giới hạn tải và dấu vết kiểm toán.

Trong Spring Modulith, Event Publication Registry hỗ trợ theo dõi publication chưa hoàn tất và resubmit các publication đó. Registry phục vụ vòng đời giao event tới listener trong ứng dụng; nó không phải một event store đầy đủ để phát lại mọi event lịch sử đã hoàn tất. Khi cần replay dữ liệu lịch sử, ứng dụng phải có nguồn lưu trữ event hoặc outbox đáp ứng yêu cầu lưu giữ, tra cứu và phiên bản hợp đồng.

Bài này phân biệt retry, replay và compensation; hướng dẫn lập kế hoạch replay, chọn đúng tập event và listener, bảo vệ side effect, điều tiết tốc độ, theo dõi kết quả và kiểm thử quy trình phục hồi.

## 1. Phân biệt retry, replay và compensation

Ba thao tác này có thể xuất hiện trong cùng một quy trình khôi phục nhưng có mục tiêu khác nhau.

| Thao tác | Mục tiêu | Đầu vào | Kết quả mong đợi |
|---|---|---|---|
| Retry | Thử lại một lần giao hoặc xử lý thất bại do lỗi có thể khắc phục | Publication/message đang chờ hoặc lần thử thất bại | Hoàn tất công việc ban đầu |
| Replay | Chủ động phát lại một event đã lưu theo một phạm vi được chọn | Event lịch sử hoặc publication chưa hoàn tất | Listener/consumer xử lý lại event theo chính sách đã định |
| Compensation | Thực hiện nghiệp vụ bù để xử lý một kết quả đã xảy ra nhưng không còn phù hợp | Trạng thái nghiệp vụ và các bước đã hoàn thành | Đưa quy trình về trạng thái nghiệp vụ chấp nhận được |

Ví dụ: service đã commit đơn hàng và publication OrderPlaced được ghi nhận. Listener giữ hàng gặp timeout. Retry là thử giao lại publication đang chưa hoàn tất. Nếu listener đã hoàn tất nhưng một read model bị xây dựng sai do bug, replay là đọc lại tập event lịch sử để dựng lại read model. Nếu hệ thống đã thu tiền nhưng đơn hàng bị hủy, compensation có thể tạo yêu cầu hoàn tiền; phát lại OrderPlaced không thể tự đảo ngược khoản thu.

Không nên xem replay là một nút “chạy lại tất cả”. Trước khi thực hiện, cần biết event sẽ được giao cho ai, side effect nào có thể lặp và dữ liệu nào sẽ được tạo hoặc thay đổi.

## 2. Replay nằm ở đâu trong Spring Modulith?

### 2.1. Event Publication Registry theo dõi publication tới listener

Khi một application event được publish trong transaction và có transactional listener phù hợp, Spring Modulith Event Publication Registry ghi nhận publication cho từng listener. Với kho lưu trữ bền vững tham gia cùng transaction, bản ghi publication được commit cùng dữ liệu nghiệp vụ.

Sau khi listener xử lý thành công, publication tương ứng được đánh dấu hoàn tất. Nếu listener thất bại, publication có thể còn ở trạng thái chưa hoàn tất để hệ thống phục hồi. Spring Modulith cung cấp API IncompleteEventPublications để truy vấn và resubmit các publication chưa hoàn tất.

Đây là cơ chế phục hồi hữu ích cho các tình huống như:

- Listener ném exception do dịch vụ phụ thuộc tạm thời không sẵn sàng.
- Ứng dụng dừng sau commit nhưng trước khi listener hoàn tất.
- Một lỗi cấu hình được sửa và publication chưa hoàn tất cần được giao lại.

Resubmit publication chưa hoàn tất là retry/recovery trong vòng đời publication. Nó không đồng nghĩa với việc phát lại tất cả event từng được publish.

### 2.2. Registry không phải event store

Event Publication Registry lưu trạng thái giao event tới các listener đã đăng ký. Sau khi publication hoàn tất, việc bản ghi còn được giữ hay được dọn phụ thuộc cấu hình và chính sách lưu trữ. Không nên giả định rằng registry luôn chứa toàn bộ lịch sử event của ứng dụng.

Nếu cần replay một event đã hoàn tất, phải có nguồn dữ liệu lịch sử phù hợp, ví dụ:

- Outbox lưu integration event cùng transaction nghiệp vụ và giữ bản ghi theo chính sách retention.
- Event store chuyên dụng lưu event bất biến theo aggregate và sequence.
- Kho lưu trữ/audit riêng có hợp đồng payload, định danh và thời điểm phát sinh rõ ràng.

Bản ghi outbox đã SENT có thể là nguồn replay nếu payload được lưu đủ lâu và có thể đọc lại an toàn. Tuy nhiên, không nên biến thao tác replay thành việc đổi trạng thái SENT về PENDING hàng loạt. Cách đó dễ làm relay gửi lại thông điệp mà không có replay request, phạm vi và audit record riêng.

### 2.3. Chọn cơ chế theo tình huống

| Tình huống | Cơ chế phù hợp |
|---|---|
| Publication chưa hoàn tất vì listener thất bại | Resubmit publication qua IncompleteEventPublications |
| Một read model cần dựng lại từ event lịch sử | Replay vào projection/read model riêng từ event store hoặc archive |
| Một integration message cần gửi lại tới broker | Replay có kiểm soát từ outbox/archive qua một luồng phát lại riêng |
| Một nghiệp vụ đã hoàn tất cần đảo ngược | Compensation bằng command/event nghiệp vụ mới |
| Cần sửa một lỗi dữ liệu cụ thể | Đánh giá dữ liệu nguồn, chọn event/aggregate liên quan và lập replay request có kiểm soát |

Nếu chỉ cần phục hồi publication chưa hoàn tất, ưu tiên API phục hồi sẵn có của Spring Modulith. Nếu cần replay event lịch sử, hãy thiết kế nguồn lưu trữ và luồng replay riêng, không coi registry là kho event toàn lịch sử.

## 3. Xác định mục tiêu và phạm vi replay

Một replay request tốt trả lời được: vì sao cần replay, event nào được chọn, listener/consumer nào nhận, dữ liệu đích nào bị ảnh hưởng, và điều kiện nào khiến quy trình dừng.

### 3.1. Chọn theo định danh ổn định

Có thể giới hạn tập event theo một hoặc nhiều tiêu chí:

- Event ID hoặc danh sách event ID cụ thể.
- Aggregate ID và khoảng sequence của aggregate.
- Event type và phiên bản schema.
- Khoảng occurredAt, nếu timestamp có ý nghĩa nghiệp vụ rõ ràng.
- Tenant hoặc phân vùng dữ liệu nếu ứng dụng có nhiều tenant.
- Consumer/projection đích cần được dựng lại.

Ưu tiên định danh ổn định như event ID và aggregate sequence. Khoảng thời gian có thể chọn nhầm event ở ranh giới timestamp, đặc biệt khi có nhiều event cùng thời điểm hoặc đồng hồ giữa các node lệch nhau.

Nếu chọn bằng điều kiện động, kết quả có thể thay đổi trong khi replay đang chạy. Hãy tạo manifest cố định gồm danh sách event ID và thứ tự xử lý trước khi bắt đầu. Manifest giúp preview, resume, audit và đối chiếu số lượng.

### 3.2. Xác minh dữ liệu trước khi chạy

Trước khi giao event, xác minh:

1. Event tồn tại trong nguồn lưu trữ và payload đọc được.
2. Event type và schema version được consumer đích hỗ trợ.
3. Aggregate/sequence không bị thiếu nếu luồng yêu cầu thứ tự.
4. Event không nằm ngoài tenant hoặc phạm vi dữ liệu được phép.
5. Consumer đích đang khỏe và có đủ capacity.
6. Replay không kích hoạt lại side effect không được phép.
7. Số lượng event và dung lượng payload nằm trong giới hạn đã duyệt.

Nếu một event không thể deserialize hoặc consumer không hỗ trợ schema, hãy đưa nó vào danh sách lỗi trước khi chạy. Không nên bỏ qua lỗi định dạng rồi tiếp tục mà không ghi nhận event bị loại.

### 3.3. Preview trước khi thực thi

Chế độ preview chỉ đọc nguồn và trả về kế hoạch:

- Replay request ID và lý do.
- Event type, schema version, consumer/projection đích.
- Số lượng event được chọn và số event bị loại.
- Khoảng sequence/thời gian, aggregate bị ảnh hưởng.
- Số event đã được consumer xử lý trước đó.
- Dự kiến tốc độ, thời lượng và giới hạn đồng thời.
- Các điều kiện chưa đạt hoặc cảnh báo cần người vận hành xem xét.

Preview không được phát event hoặc ghi side effect. Sau khi duyệt, manifest nên được cố định để lần chạy thật xử lý đúng tập event đã preview.

## 4. Mô hình replay request và audit

Replay là một hoạt động vận hành có thể làm thay đổi trạng thái hệ thống. Hãy biểu diễn nó thành một request có vòng đời riêng thay vì một lệnh ad hoc chạy trong console.

Một replay request có thể lưu các thông tin sau:

| Trường | Ý nghĩa |
|---|---|
| replay_id | Định danh duy nhất của lần replay |
| reason | Lý do nghiệp vụ/kỹ thuật |
| source | Event store, outbox archive hoặc publication registry |
| selection | Bộ lọc đã duyệt và manifest event ID |
| target | Listener, consumer hoặc projection đích |
| requested_by / approved_by | Người yêu cầu và người duyệt theo chính sách |
| requested_at / approved_at | Thời điểm yêu cầu và duyệt |
| status | PREVIEWED, APPROVED, RUNNING, PAUSED, COMPLETED, FAILED hoặc CANCELLED |
| cursor | Vị trí đã xử lý trong manifest |
| counters | Tổng số, thành công, bỏ qua, lỗi, retry |
| rate_limit | Giới hạn tốc độ và đồng thời |
| correlation_id | Mã liên kết log, trace và sự kiện phát sinh từ replay |

Các trạng thái trên là một mô hình tham khảo; hệ thống có thể dùng tên khác nhưng cần phân biệt rõ trạng thái duyệt, thực thi và kết thúc.

Luồng trạng thái khái quát:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PREVIEWED: Kiểm tra phạm vi
    PREVIEWED --> APPROVED: Duyệt
    PREVIEWED --> DRAFT: Sửa phạm vi
    APPROVED --> RUNNING: Bắt đầu
    RUNNING --> PAUSED: Tạm dừng
    PAUSED --> RUNNING: Tiếp tục
    RUNNING --> COMPLETED: Hoàn tất
    RUNNING --> FAILED: Lỗi không thể tự phục hồi
    FAILED --> RUNNING: Khởi động lại có kiểm soát
    DRAFT --> CANCELLED: Hủy
    PREVIEWED --> CANCELLED: Hủy
    APPROVED --> CANCELLED: Hủy
~~~

Audit record cần giữ người yêu cầu, người duyệt, lý do, phạm vi, manifest, cấu hình tốc độ, kết quả và các lần resume. Không ghi đè request cũ khi thay đổi phạm vi; tạo request mới hoặc lưu phiên bản manifest mới có liên kết tới request ban đầu.

### 4.1. Ví dụ cấu trúc request

Đây là mô hình Java minh họa cho lớp ứng dụng; việc lưu trữ và kiểm soát quyền cần được triển khai theo hạ tầng của hệ thống:

~~~java
public record ReplayRequest(
        UUID replayId,
        String reason,
        String target,
        List<UUID> eventIds,
        Instant requestedAt,
        String requestedBy,
        String correlationId
) {
    public ReplayRequest {
        if (replayId == null) {
            throw new IllegalArgumentException("replayId is required");
        }
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("reason is required");
        }
        if (target == null || target.isBlank()) {
            throw new IllegalArgumentException("target is required");
        }
        eventIds = List.copyOf(eventIds);
        if (eventIds.isEmpty()) {
            throw new IllegalArgumentException("eventIds must not be empty");
        }
    }
}
~~~

Trong hệ thống thực tế, request thường tham chiếu tới manifest được lưu riêng thay vì nhúng danh sách rất lớn vào một object. Hãy giới hạn kích thước request và kiểm tra quyền truy cập theo target, tenant và loại event.

## 5. Thiết kế luồng thực thi replay

Một replay worker nên tách việc lập kế hoạch khỏi việc thực thi. Điều này giúp dừng, tiếp tục và điều tra mà không phải tạo lại phạm vi từ đầu.

### 5.1. Đọc theo batch và checkpoint

Không tải toàn bộ lịch sử event vào bộ nhớ. Đọc manifest theo batch nhỏ, ví dụ vài chục hoặc vài trăm event tùy payload và capacity. Sau mỗi batch, lưu cursor và bộ đếm trong transaction riêng.

Cursor nên dựa trên vị trí ổn định trong manifest hoặc sequence, không chỉ dựa trên offset của truy vấn có thể thay đổi. Khi worker khởi động lại, nó tiếp tục từ checkpoint đã commit gần nhất.

Trình tự xử lý:

1. Claim replay request bằng lease để chỉ một worker sở hữu request tại một thời điểm.
2. Đọc batch event tiếp theo từ manifest.
3. Kiểm tra event type, schema, target và điều kiện idempotency.
4. Giao event tới consumer đích trong giới hạn concurrency.
5. Ghi kết quả từng event hoặc batch.
6. Commit checkpoint sau khi trạng thái xử lý đã được ghi bền vững.
7. Lặp lại tới khi hết manifest hoặc request bị pause/cancel.

Không cập nhật cursor trước khi kết quả batch được ghi nhận. Nếu worker dừng giữa lúc xử lý và ghi checkpoint, một số event có thể được giao lại; consumer vẫn phải idempotent.

### 5.2. Tách replay khỏi luồng event trực tiếp

Replay lớn có thể chiếm worker, connection pool và tài nguyên broker mà luồng event trực tiếp cần. Hãy tách hàng đợi hoặc executor, giới hạn concurrency riêng và ưu tiên lưu lượng trực tiếp nếu nghiệp vụ yêu cầu.

Nếu replay tới cùng listener với event trực tiếp, phải xác định chính sách thứ tự. Có thể đưa replay vào cùng partition/queue của aggregate để tuần tự hóa, hoặc chạy vào một projection riêng. Không giả định rằng việc đọc event theo thứ tự từ database sẽ bảo đảm listener xử lý theo thứ tự khi có nhiều worker bất đồng bộ.

### 5.3. Rate limit và backpressure

Tốc độ replay phải được điều chỉnh theo sức chịu tải của consumer và hệ thống phụ thuộc. Các giới hạn thường dùng:

- Số event mỗi giây.
- Số batch đang xử lý đồng thời.
- Kích thước batch theo số event hoặc tổng byte.
- Số lần retry đồng thời.
- Ngưỡng backlog và độ trễ của consumer.
- Giới hạn riêng theo tenant hoặc aggregate nếu cần.

Khi consumer tăng latency, queue tăng nhanh hoặc tỷ lệ lỗi vượt ngưỡng, worker nên tự giảm tốc độ hoặc pause. Khi hệ thống ổn định, tốc độ có thể tăng dần theo cấu hình đã duyệt.

Một bộ điều khiển đơn giản có thể dùng giới hạn cố định trước; chỉ áp dụng adaptive rate khi đã có metric đủ tin cậy và quy tắc rõ ràng. Tránh tự tăng tốc vô hạn khi queue giảm vì có thể tạo đợt tải đột biến.

### 5.4. Pause, resume và cancel

Pause dừng nhận batch mới nhưng cho batch đang chạy hoàn tất hoặc dừng ở ranh giới an toàn. Resume tiếp tục từ checkpoint đã lưu. Cancel đánh dấu request không tiếp tục chạy; không xóa các kết quả đã xử lý và không tự động đảo ngược side effect đã xảy ra.

Nếu worker mất lease, worker khác có thể claim request sau khi lease hết hạn. Mỗi batch cần kiểm tra ownership/lease trước khi ghi checkpoint để tránh worker cũ tiếp tục cập nhật sau khi đã mất quyền sở hữu.

## 6. Idempotency và side effect khi replay

Replay thường giao lại event đã từng được xử lý. Vì vậy consumer phải có chiến lược rõ ràng cho event trùng và cho mục tiêu replay.

### 6.1. Dedupe khi phục hồi delivery

Đối với retry hoặc giao lại do lỗi mạng, cùng một event ID không được tạo side effect hai lần. Consumer có thể lưu event ID đã xử lý với unique constraint:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong cùng transaction với thay đổi nghiệp vụ, consumer ghi nhận event ID. Nếu unique key đã tồn tại, event được xem là đã xử lý. Không tách thao tác ghi deduplication khỏi thay đổi nghiệp vụ, nếu không hệ thống có thể đánh dấu đã xử lý dù side effect rollback hoặc ngược lại.

Ví dụ:

~~~java
@Transactional
public void handle(OrderPlaced event) {
    boolean firstDelivery = processedEvents.tryRegister(
            "inventory-reservation",
            event.eventId()
    );

    if (!firstDelivery) {
        return;
    }

    inventory.reserveFor(event.orderId());
}
~~~

tryRegister phải dựa trên thao tác insert có unique constraint và trả về false khi khóa đã tồn tại. Việc ghi nhận event và cập nhật inventory cần cùng transaction database.

### 6.2. Replay read model khác replay side effect

Với read model, cách an toàn thường là dựng projection mới từ đầu:

1. Tạo projection generation mới hoặc bảng/namespace mới.
2. Đọc event lịch sử theo thứ tự cần thiết.
3. Ghi dữ liệu vào projection mới.
4. Đối chiếu số lượng, sequence và các invariant.
5. Chuyển truy vấn sang projection mới bằng một bước chuyển đổi có kiểm soát.
6. Giữ projection cũ trong thời gian cần thiết để có thể rollback việc chuyển đổi.

Generation mới tạo không gian idempotency riêng cho projection. Nếu dùng cùng bảng dedupe của projection hiện tại, mọi event cũ có thể bị bỏ qua và projection mới không được dựng lại.

Với side effect như thu tiền, gửi email, tạo vận đơn hoặc trừ tồn kho, replay event lịch sử có thể lặp hành động thật. Không được bỏ qua dedupe chỉ để “cho chạy lại”. Hãy xác định mục tiêu nghiệp vụ và dùng command mới có idempotency key riêng, hoặc quy trình compensation được phê duyệt.

### 6.3. Gọi hệ thống bên ngoài

Consumer có thể cập nhật database nội bộ rồi gọi API thanh toán hoặc gửi email. Transaction database không thể bao trọn lời gọi HTTP bên ngoài. Nếu consumer bị dừng sau khi dịch vụ ngoài đã thực hiện nhưng trước khi ghi nhận kết quả, lần replay tiếp theo có thể gọi lại.

Ưu tiên idempotency key do ứng dụng tạo và gửi tới API bên ngoài nếu nhà cung cấp hỗ trợ. Lưu request ID, response ID và trạng thái kết quả để đối chiếu. Nếu API không hỗ trợ idempotency, cần thiết kế bước tra cứu hoặc đối soát trước khi gửi lại.

## 7. Thứ tự, phiên bản và tính nhất quán

### 7.1. Giữ thứ tự trong phạm vi aggregate

Event của cùng aggregate có thể cần xử lý theo sequence tăng dần. Nếu replay song song các event cùng aggregate, event phiên bản sau có thể đến trước phiên bản trước và làm sai trạng thái.

Dùng aggregate sequence hoặc version để:

- Sắp xếp event theo aggregate.
- Phát hiện sequence bị thiếu hoặc trùng.
- Giữ xử lý tuần tự theo aggregate khi cần.
- Ghi checkpoint riêng theo aggregate nếu replay phân vùng.

Không cần áp đặt thứ tự toàn cục nếu nghiệp vụ chỉ yêu cầu thứ tự trong một aggregate. Thứ tự toàn cục thường giảm thông lượng và làm tăng điểm nghẽn.

### 7.2. Quản lý schema version

Event lịch sử có thể được tạo từ phiên bản ứng dụng cũ. Consumer replay phải hiểu schema version tương ứng hoặc chuyển đổi payload qua một lớp upcaster/adapter có kiểm soát.

Không sửa payload gốc trong event store để phù hợp với consumer mới. Giữ event bất biến và áp dụng chuyển đổi khi đọc. Kiểm thử cả payload cũ và mới, bao gồm trường thiếu, giá trị mặc định và thay đổi enum.

Nếu không thể chuyển đổi an toàn, đưa event vào trạng thái cần xử lý thủ công và ghi rõ lý do. Bỏ qua event có thể làm projection thiếu dữ liệu; tiếp tục không kiểm soát có thể tạo trạng thái sai.

### 7.3. Event đến muộn và event ngoài thứ tự

Nếu replay event lịch sử cùng lúc với event trực tiếp, consumer có thể nhận một event cũ sau khi đã xử lý event mới. Cần xác định chính sách:

- Projection có thể rebuild từ một snapshot/sequence cố định rồi catch up các event mới.
- Consumer có thể từ chối event có sequence thấp hơn checkpoint hiện tại.
- Luồng replay có thể chạy vào projection generation riêng để tránh tranh chấp với luồng trực tiếp.

Không dùng occurredAt làm tiêu chí duy nhất để quyết định event mới hay cũ. Đồng hồ hệ thống có thể lệch; sequence/aggregate version đáng tin cậy hơn khi có sẵn.

## 8. Compensation khi replay không phải cách sửa đúng

Replay không đảo ngược trạng thái nghiệp vụ. Khi một bước đã tạo ra kết quả bên ngoài, hệ thống thường cần một hành động bù có ngữ nghĩa riêng.

Ví dụ quy trình đặt hàng:

~~~mermaid
sequenceDiagram
    participant O as Order
    participant P as Payment
    participant I as Inventory
    participant S as Shipping

    O->>P: Capture payment
    P-->>O: PaymentCaptured
    O->>I: Reserve inventory
    I-->>O: ReservationFailed
    O->>P: Request refund
    P-->>O: RefundCompleted
    O->>O: Mark order as compensation completed
~~~

RefundRequested là một hành động nghiệp vụ mới, không phải phát lại PaymentCaptured. Compensation có thể thất bại hoặc bị timeout nên bản thân nó cũng cần publication bền vững, retry, idempotency và audit.

Một số nguyên tắc:

- Compensation phải có định danh riêng và tham chiếu tới hành động gốc.
- Không giả định bù trừ luôn khôi phục chính xác trạng thái ban đầu; có nghiệp vụ chỉ cho phép hành động bù gần tương đương.
- Xác định thứ tự bù ngược với các bước đã hoàn tất trong quy trình.
- Mỗi bước compensation cần idempotent và có trạng thái theo dõi riêng.
- Nếu compensation không thể tự hoàn tất, tạo cảnh báo và chuyển sang xử lý thủ công.

Với quy trình dài qua nhiều module, có thể dùng saga/process manager để theo dõi tiến trình, timeout, retry và compensation. Event mô tả kết quả đã xảy ra; command yêu cầu bước tiếp theo; compensation là command/event nghiệp vụ riêng để xử lý hậu quả.

## 9. Theo dõi và điều tra một lần replay

Mọi log và metric của replay cần gắn với replay_id và correlation_id. Với mỗi event, ghi event_id, aggregate_id, sequence, event_type, schema_version, target và kết quả xử lý.

Các chỉ số nên theo dõi:

- Tổng event trong manifest, đã xử lý, bỏ qua, lỗi và còn chờ.
- Tốc độ event/giây và kích thước batch.
- Độ trễ consumer, queue depth và số worker đang hoạt động.
- Số event duplicate được dedupe.
- Số event không deserialize được hoặc không hỗ trợ schema.
- Số lần retry và tuổi event lỗi lâu nhất.
- Tiến độ theo aggregate/partition và checkpoint hiện tại.

Một dashboard nên cho biết replay request đang chạy, paused hay failed; event nào đang lỗi; và lý do lần gần nhất thất bại. Log cần đủ thông tin để tìm lại event gốc nhưng tránh ghi payload nhạy cảm.

Khi replay hoàn tất, đối chiếu:

- Số event trong manifest với số thành công, bỏ qua và lỗi.
- Sequence đầu/cuối và các khoảng bị thiếu.
- Tổng số record hoặc checksum của projection nếu có.
- Các invariant nghiệp vụ quan trọng.
- Backlog event trực tiếp sau khi replay kết thúc.

Không coi status COMPLETED là bằng chứng duy nhất cho tính đúng đắn dữ liệu. Nó chỉ cho biết worker đã xử lý xong manifest theo chính sách của request; việc đối chiếu kết quả vẫn cần thực hiện.

## 10. Kiểm thử replay có kiểm soát

Cần kiểm thử cả logic chọn event, điều khiển worker và hành vi consumer khi nhận event lặp. Một số kịch bản quan trọng:

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Preview một tập event cố định | Manifest có đúng event ID, target và số lượng |
| Event không hỗ trợ schema | Bị đánh dấu lỗi trước khi giao hoặc được đưa vào luồng xử lý lỗi |
| Worker dừng sau khi giao batch nhưng trước checkpoint | Event có thể được giao lại mà không lặp side effect |
| Pause trong lúc đang xử lý | Không nhận batch mới sau ranh giới an toàn |
| Resume sau restart | Tiếp tục từ checkpoint bền vững |
| Lease hết hạn và worker khác claim | Worker cũ không thể ghi checkpoint sau khi mất ownership |
| Hai event cùng aggregate | Thứ tự theo sequence được giữ nếu nghiệp vụ yêu cầu |
| Consumer đã xử lý event | Delivery trùng được dedupe |
| Projection generation mới | Event lịch sử được áp dụng vào generation mới |
| Side effect gọi API ngoài | Idempotency key hoặc cơ chế đối soát ngăn hành động trùng |
| Compensation thất bại | Trạng thái được lưu, có retry và cảnh báo |
| Cancel request | Dừng ở ranh giới an toàn và giữ lại audit/kết quả đã có |

Test cần dùng kho lưu trữ và transaction thực tế cho các bảo đảm quan trọng. Mock một replay service chỉ chứng minh điều phối gọi đúng port; nó không chứng minh checkpoint, unique constraint hoặc atomic commit hoạt động như mong muốn.

## 11. Quy trình vận hành mẫu

Một quy trình replay trong production có thể tổ chức như sau:

1. Xác định lỗi và mục tiêu: phục hồi publication chưa hoàn tất, dựng lại projection hay gửi lại integration message.
2. Chọn nguồn event phù hợp và xác minh retention, schema, sequence.
3. Tạo replay request với lý do, target và phạm vi cụ thể.
4. Chạy preview, tạo manifest cố định và đối chiếu số lượng.
5. Xác nhận consumer idempotent, giới hạn side effect, rate limit và thứ tự.
6. Duyệt request theo chính sách vận hành.
7. Chạy theo batch, lưu checkpoint, quan sát metric và log.
8. Pause khi vượt ngưỡng tải hoặc phát hiện lỗi dữ liệu; resume sau khi xử lý nguyên nhân.
9. Đối chiếu kết quả, backlog và invariant nghiệp vụ.
10. Đóng request, lưu audit và giữ lại báo cáo để truy vết.

Nếu replay thất bại, không tự động mở rộng phạm vi hoặc tăng tốc để “bắt kịp”. Trước tiên hãy xác định event gây lỗi, trạng thái side effect và checkpoint cuối cùng đã commit.

## 12. Các lỗi thiết kế thường gặp

**Dùng Event Publication Registry như event store.** Registry theo dõi publication tới listener; nó không mặc nhiên giữ mọi event đã hoàn tất. Cần một nguồn lịch sử riêng nếu yêu cầu replay dài hạn.

**Resubmit toàn bộ publication không lọc.** Có thể tạo tải đột biến và gọi lại listener ngoài phạm vi cần phục hồi. Hãy lọc theo tuổi, event hoặc listener nếu API hỗ trợ và giới hạn tốc độ.

**Replay trực tiếp từ truy vấn thời gian đang thay đổi.** Tập event có thể thay đổi giữa preview và thực thi. Hãy cố định manifest bằng ID/sequence.

**Bỏ qua idempotency vì đã có replay_id.** Replay ID định danh lần chạy; nó không tự ngăn cùng event tạo side effect hai lần. Consumer vẫn cần khóa dedupe phù hợp.

**Tắt dedupe để dựng lại projection.** Việc này có thể làm lặp side effect. Hãy dùng generation/namespace riêng cho read model.

**Replay event lịch sử để đảo ngược nghiệp vụ.** Event cũ mô tả điều đã xảy ra. Dùng command và compensation mới cho hành động bù.

**Chạy replay không giới hạn.** Replay có thể làm nghẽn listener và hệ thống phụ thuộc. Dùng batch, rate limit, backpressure và pause.

**Không giữ audit.** Khi không biết ai replay, lý do và phạm vi, việc điều tra side effect hoặc giải thích dữ liệu thay đổi trở nên khó khăn. Lưu request, manifest, người duyệt và kết quả.

**Không kiểm tra phiên bản event.** Payload cũ có thể không tương thích với consumer hiện tại. Dùng schema version và chuyển đổi có kiểm thử.

Replay có kiểm soát là một quy trình vận hành có trạng thái, phạm vi cố định, consumer an toàn khi nhận lặp và kết quả có thể đối chiếu. Spring Modulith hỗ trợ phục hồi publication chưa hoàn tất; replay event lịch sử cần nguồn lưu trữ phù hợp và luồng thực thi riêng. Khi mục tiêu là sửa kết quả nghiệp vụ đã xảy ra, hãy tạo hành động compensation có ngữ nghĩa rõ ràng thay vì phát lại event cũ.

