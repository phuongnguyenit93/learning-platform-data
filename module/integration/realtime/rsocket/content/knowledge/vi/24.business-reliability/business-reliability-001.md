# Phân biệt độ tin cậy truyền tải, tiếp tục phiên và lưu trữ bền vững

## Mục tiêu bài học

Một kết nối RSocket có thể truyền frame đáng tin cậy trong khi transport còn hoạt động, có thể tiếp tục một session sau gián đoạn ngắn nếu bật resumption, và vẫn có thể mất một lệnh nghiệp vụ nếu ứng dụng chưa lưu lệnh đó vào nơi lưu trữ bền vững. Ba khả năng này giải quyết ba lớp vấn đề khác nhau.

Sau bài này, bạn có thể:

- Phân biệt xác nhận ở tầng TCP, vòng đời frame RSocket và xác nhận nghiệp vụ.
- Giải thích RSocket session resumption giúp tiếp tục kết nối bị gián đoạn như thế nào.
- Nhận biết giới hạn của resume buffer và trạng thái session trong bộ nhớ.
- Thiết kế lưu trữ bền vững bằng database, inbox/outbox hoặc message broker.
- Xử lý kết quả chưa xác định khi client mất kết nối sau khi server đã thực hiện nghiệp vụ.
- Dùng idempotency key, command ID, sequence và trạng thái nghiệp vụ để tránh tác dụng phụ trùng.
- Kết hợp reconnect, resumption, retry và durable delivery thành một quy trình có thể kiểm soát.

## Ba lớp độ tin cậy khác nhau

Khi nói một hệ thống realtime “đáng tin cậy”, cần hỏi chính xác dữ liệu được bảo vệ ở lớp nào. RSocket chạy trên transport như TCP hoặc WebSocket, quản lý các session và stream, còn nghiệp vụ nằm trong ứng dụng và hệ thống lưu trữ.

~~~mermaid
flowchart TB
    A[Độ tin cậy nghiệp vụ]
    A --> B[Lưu trữ bền vững]
    B --> C[Database / Outbox / Broker / Inbox]
    A --> D[Tiếp tục phiên RSocket]
    D --> E[Resume token và frame buffer]
    A --> F[Độ tin cậy truyền tải]
    F --> G[TCP hoặc WebSocket]
~~~

| Lớp | Câu hỏi được giải quyết | Cơ chế điển hình | Điều không được bảo đảm |
|---|---|---|---|
| Truyền tải | Byte/frame có đi qua kết nối đang hoạt động không? | TCP reliability, WebSocket framing, kiểm tra lỗi transport | Server đã xử lý hoặc commit nghiệp vụ |
| Phiên RSocket | Có thể tiếp tục session sau gián đoạn ngắn không? | RSocket resumption, resume token và buffer | Dữ liệu sống sót qua restart hoặc được lưu bền vững |
| Nghiệp vụ | Lệnh và kết quả có tồn tại qua lỗi process/máy chủ không? | Database transaction, inbox/outbox, durable broker, idempotency | Exactly-once end-to-end nếu các hệ thống không phối hợp transaction |

Không nên dùng một từ “acknowledged” cho cả ba lớp. TCP ACK, việc một stream hoàn tất, phản hồi `ACCEPTED` và việc transaction đã commit là những sự kiện khác nhau.

## Độ tin cậy truyền tải: TCP ACK không phải xác nhận nghiệp vụ

TCP cung cấp byte stream có thứ tự và retransmit các segment bị mất khi kết nối còn có thể phục hồi. TCP ACK cho biết TCP stack phía nhận đã nhận được một vùng byte. Nó không chứng minh:

- Ứng dụng server đã đọc các byte đó.
- RSocket đã giải mã và chấp nhận frame.
- Handler Spring đã được gọi.
- Database đã commit thay đổi.
- Một tác vụ nền đã hoàn thành.

Ví dụ, client gửi một lệnh tạo đơn hàng. TCP có thể xác nhận toàn bộ byte của frame đã tới máy server. Ngay sau đó process server bị dừng trước khi handler ghi đơn hàng vào database. Client đã thấy TCP ACK nhưng đơn hàng chưa tồn tại.

Tương tự, WebSocket chạy trên TCP có framing và giữ thứ tự dữ liệu, nhưng việc WebSocket send hoàn tất cũng không phải bằng chứng server đã commit nghiệp vụ.

### RSocket request completion cũng có phạm vi riêng

Các interaction type có ngữ nghĩa khác nhau:

- **Request-response:** responder phát tối đa một response. Nếu handler commit transaction trước khi trả response, response có thể được dùng làm xác nhận nghiệp vụ. Nếu handler trả response trước khi commit hoặc chỉ xác nhận đã đưa việc vào queue, ý nghĩa phải được ghi rõ.
- **Fire-and-forget:** requester không nhận response nghiệp vụ. Việc publisher gửi hoàn tất không chứng minh server đã xử lý thành công.
- **Request-stream:** response Flux phát nhiều payload; complete cho biết luồng response đã kết thúc bình thường, không tự chứng minh mọi event đã được lưu bền vững.
- **Request-channel:** hai chiều có thể hoàn tất độc lập. Complete một chiều không phải xác nhận commit của mọi command đã gửi.

Nếu cần xác nhận server đã nhận lệnh, hãy định nghĩa một acknowledgement ở tầng ứng dụng. Nếu cần xác nhận đã commit, hãy phát trạng thái sau khi transaction commit thành công.

## Tiếp tục phiên RSocket bằng resumption

RSocket có extension resumption cho phép hai peer tiếp tục một session sau khi transport bị gián đoạn tạm thời. Thay vì tạo một session mới hoàn toàn, peer kết nối lại và trao đổi thông tin resume để xác định session cũ và vị trí frame đã được trao đổi.

Các thành phần quan trọng:

- **Resume token:** định danh session mà peer muốn tiếp tục.
- **Resume position:** vị trí trong luồng frame được dùng để xác định dữ liệu đã nhận và phần cần phát lại.
- **Resume buffer:** giữ các frame cần thiết để có thể truyền lại sau khi kết nối gián đoạn.
- **Session state:** trạng thái giao thức cần được giữ để peer tiếp tục trao đổi.

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant S as RSocket Server
    C->>S: SETUP (session hỗ trợ resume)
    S-->>C: Session sẵn sàng
    C->>S: REQUEST / PAYLOAD
    Note over C,S: Transport bị gián đoạn
    C->>S: RESUME (token + position)
    S-->>C: RESUME_OK
    Note over C,S: Tiếp tục session, phát lại frame còn thiếu
    C->>S: REQUEST / PAYLOAD tiếp theo
~~~

Resumption chỉ hoạt động khi cả hai phía và transport implementation hỗ trợ, đồng thời được cấu hình phù hợp. Các giới hạn quan trọng gồm:

- Session cũ phải còn được peer giữ lại.
- Resume token phải xác định đúng session.
- Buffer còn đủ dữ liệu cần truyền lại.
- Khoảng gián đoạn không vượt quá thời gian giữ session.
- Hai phía phải có trạng thái giao thức tương thích để tiếp tục.

Nếu peer đã xóa session state, process khởi động lại và mất resume buffer, hoặc buffer không còn đủ dữ liệu, resume có thể thất bại. Ứng dụng khi đó cần tạo session mới và khôi phục trạng thái nghiệp vụ bằng cơ chế riêng.

### Resumption không phải durable storage

Resume buffer thường là trạng thái phục vụ việc tiếp tục session, không phải kho lưu trữ nghiệp vụ. Không được xem buffer trong RAM như một hàng đợi bền vững.

| Tình huống | Resumption có thể giúp? | Cần lưu trữ bền vững? |
|---|---|---|
| Wi-Fi chập chờn trong thời gian ngắn, process vẫn sống | Có, nếu session và buffer còn hợp lệ | Không nhất thiết cho dữ liệu tạm thời |
| TCP connection bị reset nhưng hai peer còn session state | Có thể | Tùy yêu cầu nghiệp vụ |
| Server process restart và mất session state trong RAM | Thường không thể tiếp tục session cũ | Có, nếu lệnh/kết quả phải tồn tại |
| Client restart và mất dữ liệu chưa gửi trong RAM | Không thể khôi phục dữ liệu đó chỉ bằng server resume | Có, ở client hoặc một durable producer |
| Một request đã commit nhưng response bị mất | Resume có thể giúp khôi phục frame nếu còn buffer; không thay thế kiểm tra trạng thái nghiệp vụ | Cần idempotency/status khi kết quả chưa rõ |

Resumption giảm gián đoạn và nhu cầu mở lại tương tác. Nó không thay thế transaction, outbox, inbox, broker hoặc cơ chế replay từ event store.

## Ba loại xác nhận nghiệp vụ cần định nghĩa rõ

Ứng dụng nên đặt tên trạng thái theo điều thực sự đã xảy ra:

| Trạng thái | Ý nghĩa chính xác | Có thể trả khi nào? |
|---|---|---|
| RECEIVED | Server đã nhận payload vào bộ nhớ hoặc handler | Sau khi decode/validate cơ bản |
| ACCEPTED | Server đã ghi nhận lệnh vào hàng đợi bền vững hoặc transaction | Sau khi durable write/commit thành công |
| COMPLETED | Công việc nghiệp vụ đã thực hiện và kết quả đã commit | Sau khi transaction nghiệp vụ hoàn tất |

Không dùng `ACCEPTED` nếu server chỉ đưa lệnh vào một queue trong RAM. Nếu process crash, lệnh có thể mất. Hãy định nghĩa rõ “accepted” là đã lưu vào database, broker hoặc storage bền vững nào.

Một response `ACCEPTED` từ request-response chỉ có giá trị bền vững nếu handler phát response sau khi thao tác lưu trữ đã commit. Ví dụ:

~~~java
record SubmitCommand(
    String commandId,
    String accountId,
    long amount
) {}

record CommandReceipt(
    String commandId,
    String status
) {}

@MessageMapping("payments.submit")
Mono<CommandReceipt> submit(SubmitCommand command) {
    return paymentCommandService.persist(command)
        .map(saved -> new CommandReceipt(
            saved.commandId(),
            "ACCEPTED"
        ));
}
~~~

Trong ví dụ, `persist()` phải hoàn tất sau commit. Nếu nó chỉ ghi vào một queue in-memory, response không thể được hiểu là xác nhận durable acceptance.

## Lưu trữ bền vững: database, outbox và broker

Khi một lệnh phải sống sót qua restart, hãy ghi nó vào storage bền vững trước khi xác nhận đã tiếp nhận.

Có một số lựa chọn:

- **Database transaction:** phù hợp khi thay đổi nghiệp vụ và trạng thái lệnh nằm trong cùng database.
- **Transactional outbox:** ghi thay đổi nghiệp vụ và event cần phát vào cùng transaction; một publisher nền gửi outbox ra RSocket hoặc broker.
- **Inbox/deduplication table:** ghi nhận command/event đã xử lý để loại bỏ lần gửi trùng.
- **Durable message broker:** giữ message trên storage bền vững, hỗ trợ consumer acknowledgement và redelivery theo cấu hình.
- **Event store:** lưu chuỗi event có sequence để replay hoặc tái dựng trạng thái.

RSocket là giao thức giao tiếp realtime; nó không tự cung cấp một durable broker hay transaction log cho nghiệp vụ.

### Mẫu Transactional Outbox

Giả sử một service cập nhật trạng thái đơn hàng và cần phát event `OrderPaid` sang service khác. Nếu ghi database rồi gửi RSocket riêng rẽ, có một khoảng lỗi:

1. Database commit thành công.
2. Process crash trước khi gửi RSocket.
3. Trạng thái đơn hàng đã đổi nhưng service nhận không bao giờ thấy event.

Nếu gửi RSocket trước rồi mới commit database, lỗi ngược lại có thể xảy ra: consumer xử lý event trong khi transaction nguồn rollback.

Transactional Outbox giải quyết khoảng lỗi này bằng cách ghi trạng thái nghiệp vụ và outbox record trong cùng một transaction:

~~~mermaid
sequenceDiagram
    participant A as Order Service
    participant DB as Database
    participant P as Outbox Publisher
    participant R as RSocket Consumer
    A->>DB: BEGIN
    A->>DB: UPDATE orders
    A->>DB: INSERT outbox event
    A->>DB: COMMIT
    P->>DB: Đọc event chưa gửi
    P->>R: Gửi event qua RSocket
    R-->>P: ACK đã lưu/tiếp nhận
    P->>DB: Đánh dấu event đã gửi
~~~

Bảng outbox thường có các trường:

| Trường | Mục đích |
|---|---|
| event_id | ID duy nhất của event |
| aggregate_id | ID đơn hàng hoặc aggregate |
| sequence | Thứ tự event trong aggregate |
| event_type | Loại event |
| payload | Nội dung event đã serialize |
| created_at | Thời điểm tạo |
| published_at | Thời điểm publisher xác nhận đã gửi |
| status / attempts | Trạng thái và số lần thử |

Publisher đọc các record chưa gửi, gửi lại khi lỗi và đánh dấu đã gửi sau khi nhận acknowledgement phù hợp. Nếu process crash sau khi consumer xử lý nhưng trước khi publisher đánh dấu published, event có thể được gửi lại. Do đó consumer phải idempotent.

Nếu publisher cần biết consumer đã lưu event bền vững, hãy dùng một request-response có receipt hoặc một hợp đồng acknowledgement tương đương. Fire-and-forget không cung cấp response nghiệp vụ để publisher xác nhận durable acceptance. Nếu request-response timeout sau khi consumer đã commit inbox, publisher gửi lại cùng `event_id`; consumer nhận diện duplicate và trả receipt đã có.

Ví dụ luồng gửi và nhận receipt:

~~~java
Mono<Void> publish(Event event) {
    return requester
        .route("events.accept")
        .data(event)
        .retrieveMono(ConsumerReceipt.class)
        .flatMap(receipt -> {
            if (!receipt.accepted()) {
                return Mono.error(
                    new EventNotAcceptedException(event.eventId())
                );
            }
            return outboxRepository.markPublished(event.eventId());
        });
}
~~~

Đoạn code là phác thảo; `markPublished` chỉ chạy sau khi nhận receipt có ý nghĩa đã được consumer commit. Publisher cũng cần giữ outbox record nếu response lỗi hoặc timeout để lần quét sau gửi lại cùng event ID.

### Mẫu Inbox và idempotent consumer

Consumer lưu event ID đã xử lý cùng với thay đổi nghiệp vụ trong một transaction:

~~~java
@Transactional
public ProcessingResult handle(OrderPaid event) {
    // Atomic INSERT protected by a UNIQUE constraint on event_id.
    if (!inboxRepository.insertIfAbsent(event.eventId())) {
        return ProcessingResult.DUPLICATE;
    }

    orderProjection.apply(event);

    return ProcessingResult.APPLIED;
}
~~~

`insertIfAbsent` đại diện cho thao tác insert nguyên tử, được bảo vệ bởi unique constraint trên `event_id` (ví dụ `INSERT ... ON CONFLICT DO NOTHING`). Không dùng cặp `SELECT exists` rồi `INSERT` như hai thao tác không được bảo vệ: hai consumer đồng thời có thể cùng thấy event chưa tồn tại. Việc ghi inbox và cập nhật projection phải nằm trong cùng transaction. Nếu cập nhật projection thất bại, transaction rollback cả inbox record để event có thể được thử lại.

Nếu consumer cần gửi response `ACCEPTED`, chỉ trả sau khi transaction lưu inbox và cập nhật trạng thái cần thiết đã commit. Publisher outbox chỉ đánh dấu event đã được consumer tiếp nhận sau acknowledgement đó.

## At-most-once, at-least-once và exactly-once

Các thuật ngữ delivery guarantee cần được gắn với phạm vi cụ thể:

| Guarantee | Ý nghĩa | Đánh đổi |
|---|---|---|
| At-most-once | Không gửi lại sau khi thử một lần | Có thể mất message nếu lỗi xảy ra |
| At-least-once | Retry cho đến khi có acknowledgement theo chính sách | Có thể nhận trùng |
| Effectively-once | Có thể nhận trùng nhưng deduplicate để tác dụng phụ chỉ áp dụng một lần theo khóa | Cần idempotency và lưu trạng thái |
| Exactly-once end-to-end | Mọi thành phần cùng phối hợp để một nghiệp vụ chỉ xảy ra đúng một lần | Rất khó nếu qua nhiều hệ thống độc lập; thường cần transaction hoặc protocol chuyên biệt |

Không nên tuyên bố RSocket hoặc TCP cung cấp exactly-once cho nghiệp vụ. Một response bị mất không cho client biết server đã commit hay chưa. Một lần retry có thể tạo tác dụng phụ trùng nếu server không nhận diện command cũ.

Trong nhiều hệ thống, mục tiêu thực tế là at-least-once delivery kết hợp idempotent consumer để đạt effectively-once effect.

## Cửa sổ lỗi: request đã gửi nhưng response bị mất

Đây là tình huống quan trọng nhất khi thiết kế retry.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    participant DB as Database
    C->>S: Submit commandId=cmd-42
    S->>DB: Commit payment
    DB-->>S: Commit OK
    Note over S,C: Connection lost trước response
    C->>C: Không biết lệnh đã commit hay chưa
    C->>S: Retry commandId=cmd-42
    S->>DB: Kiểm tra commandId
    DB-->>S: Đã xử lý trước đó
    S-->>C: Trả lại receipt cũ
~~~

Client nhìn thấy timeout hoặc connection error, nhưng không thể suy ra server chưa thực hiện lệnh. Trạng thái này gọi là **unknown outcome**.

Cách xử lý:

1. Mỗi lệnh nghiệp vụ có một command ID/idempotency key ổn định.
2. Client giữ nguyên ID đó qua mọi lần retry.
3. Server lưu ID và kết quả xử lý trong transaction.
4. Nếu nhận lại cùng ID, server trả receipt/kết quả đã lưu thay vì thực hiện tác dụng phụ lần nữa.
5. Nếu client vẫn không biết kết quả, cung cấp route truy vấn trạng thái theo command ID.

Ví dụ handler idempotent:

~~~java
@MessageMapping("payments.submit")
Mono<PaymentReceipt> submit(PaymentCommand command) {
    return paymentService.submitIdempotently(
        command.commandId(),
        command
    );
}
~~~

`submitIdempotently()` phải kiểm tra và ghi command ID một cách atomic. Chỉ kiểm tra trước bằng một câu SELECT rồi mới INSERT mà không có unique constraint hoặc transaction bảo vệ sẽ vẫn có race condition khi hai request trùng đến đồng thời.

## Chọn RSocket interaction type theo mức xác nhận cần thiết

| Nhu cầu | Interaction phù hợp | Điều cần bổ sung |
|---|---|---|
| Gửi telemetry best-effort | Fire-and-forget | Chấp nhận mất hoặc có buffer bền vững nếu cần |
| Gửi command và nhận receipt đã commit | Request-response | Handler chỉ trả sau durable commit |
| Gửi command rồi theo dõi tiến độ | Request-response lấy job ID, sau đó request-stream | Lưu trạng thái job và replay/cursor |
| Trao đổi command và event hai chiều | Request-channel | Command ID, sequence, durable inbox/outbox nếu cần |
| Phát event tới nhiều consumer | RSocket hoặc broker tùy kiến trúc | Durable subscription/retention nếu cần replay |

Fire-and-forget có thể phù hợp cho tín hiệu có thể mất. Với lệnh thanh toán, tạo đơn hàng hoặc thay đổi quyền truy cập, cần acknowledgement có ý nghĩa rõ ràng và lưu trạng thái bền vững.

Một mẫu thường dùng cho tác vụ lâu:

1. Client gửi request-response `jobs.submit`.
2. Server ghi job và command ID vào database, commit.
3. Server trả `ACCEPTED` kèm job ID.
4. Client mở request-stream `jobs.watch` để nhận tiến độ.
5. Nếu mất kết nối, client reconnect/resume nếu có thể; nếu session không còn, truy vấn hoặc subscribe lại theo job ID và cursor.

## Replay và sequence cho stream nghiệp vụ

Khi stream có thể bị gián đoạn lâu hơn thời gian giữ session, ứng dụng cần khả năng tiếp tục từ vị trí nghiệp vụ.

Một event có thể có dạng:

~~~java
record DomainEvent(
    String aggregateId,
    long sequence,
    String eventId,
    String eventType,
    String payload
) {}
~~~

Client lưu sequence cuối đã xử lý. Khi mở lại stream, nó gửi cursor để yêu cầu event sau sequence đó:

~~~java
record EventSubscription(
    String aggregateId,
    long afterSequence
) {}

Flux<DomainEvent> events = requester
    .route("orders.events")
    .data(new EventSubscription("order-42", lastSequence))
    .retrieveFlux(DomainEvent.class);
~~~

Server đọc event từ event store hoặc log bền vững và phát từ sequence tiếp theo. Nếu client nhận lại event đã xử lý do acknowledgement bị mất, event ID hoặc sequence giúp deduplicate.

Cần xác định rõ:

- Sequence tăng theo aggregate, partition hay toàn hệ thống?
- Có bảo đảm không có gap không?
- Event retention trong bao lâu?
- Nếu cursor quá cũ, server trả lỗi, snapshot hay bắt đầu lại?
- Client commit sequence đã xử lý ở thời điểm nào?

Không cập nhật cursor trước khi tác dụng phụ của event đã commit. Nếu lưu cursor trước rồi process crash trước khi cập nhật nghiệp vụ, event sẽ bị bỏ qua khi replay.

## Reconnect, resume và durable replay phối hợp ra sao?

Ba chiến lược có thể được xếp theo thời gian gián đoạn:

| Tình huống | Cơ chế ưu tiên |
|---|---|
| Kết nối vẫn hoạt động | Tiếp tục trao đổi trên session hiện tại |
| Mất transport ngắn, session state còn giữ | Thử RSocket resumption |
| Resume thất bại hoặc session hết hạn | Reconnect và tạo session mới |
| Cần khôi phục command/event qua process restart | Đọc durable outbox, inbox hoặc event store |
| Kết quả command chưa rõ | Query theo command ID hoặc retry idempotent |
| Client bỏ lỡ event lâu hơn retention của session | Replay từ cursor nghiệp vụ nếu event còn được lưu |

Quy trình tổng quát:

~~~mermaid
flowchart TD
    A[Transport bị gián đoạn] --> B{Resume session còn hợp lệ?}
    B -->|Có| C[Thử RSocket RESUME]
    C -->|Thành công| D[Tiếp tục session]
    C -->|Thất bại| E[Tạo session mới]
    B -->|Không| E
    E --> F[Khôi phục command/job/event từ storage]
    F --> G[Deduplicate bằng ID/sequence]
    G --> H[Tiếp tục nghiệp vụ]
~~~

Resumption là tối ưu cho continuity ở tầng session. Durable replay là cơ chế khôi phục ở tầng nghiệp vụ. Có thể dùng cả hai: resume trước để giảm gián đoạn, rồi fallback sang durable replay nếu session cũ không còn.

## Lập kế hoạch lưu trữ bền vững

Không phải mọi payload đều cần lưu bền vững. Hãy phân loại theo hậu quả nếu dữ liệu mất:

| Loại dữ liệu | Nếu mất thì sao? | Chính sách gợi ý |
|---|---|---|
| Mouse movement, telemetry tần suất cao | Có thể chấp nhận mất một số mẫu | Best-effort, gộp hoặc drop có giới hạn |
| Trạng thái UI tạm thời | Có thể tái dựng từ snapshot | Reconnect và tải snapshot mới |
| Lệnh tạo đơn hàng/thanh toán | Có tác dụng phụ và nghĩa vụ nghiệp vụ | Durable command record, idempotency, receipt |
| Event trạng thái đơn hàng | Consumer cần replay và không bỏ sót | Outbox/event log, sequence và retention |
| Job chạy lâu | Cần theo dõi sau khi client rời đi | Lưu job state, job ID và event history |

Đặt retention phù hợp. Lưu mọi telemetry vô thời hạn làm tăng chi phí storage và khiến replay khó kiểm soát. Ngược lại, xóa outbox hoặc event quá sớm có thể khiến consumer offline không thể bắt kịp.

## Kiểm thử độ tin cậy qua các điểm lỗi

Để xác nhận thiết kế, hãy thử dừng kết nối hoặc process ở từng cửa sổ:

1. Client mất kết nối trước khi request được gửi.
2. Request đã được TCP nhận nhưng server chưa gọi handler.
3. Handler đã bắt đầu nhưng chưa commit.
4. Database đã commit nhưng response chưa tới client.
5. Consumer đã commit inbox nhưng acknowledgement gửi về bị mất.
6. Publisher nhận acknowledgement nhưng crash trước khi đánh dấu outbox event đã gửi.
7. Session resume buffer đầy hoặc session hết hạn.
8. Server restart và mất in-memory resume state.
9. Client replay từ cursor cũ, khiến event được gửi lại.
10. Hai bản sao cùng command ID đến đồng thời.

Mỗi test phải có assertion ở database hoặc durable store, không chỉ assertion trên log hoặc response Flux. Xác minh số lần tác dụng phụ xảy ra, trạng thái command, event ID, sequence và khả năng replay.

## Quan sát và vận hành

Các metric cần theo dõi:

- Số kết nối bị ngắt và số lần resume thành công/thất bại.
- Số session hết hạn hoặc resume buffer không đủ.
- Số command đang ở trạng thái RECEIVED, ACCEPTED, PROCESSING, COMPLETED hoặc FAILED.
- Độ sâu và tuổi của outbox queue.
- Số lần publish retry và số event chưa được acknowledgement.
- Số duplicate bị inbox/idempotency loại bỏ.
- Consumer lag và sequence gap.
- Tỷ lệ command có unknown outcome sau timeout.
- Thời gian từ durable acceptance tới completion.

Log nên có connection/session ID, stream ID, command ID, event ID, aggregate ID và sequence khi phù hợp. Không dùng stream ID làm ID nghiệp vụ lâu dài: stream ID chỉ có ý nghĩa trong session RSocket và có thể thay đổi khi tạo tương tác mới.

## Checklist thiết kế

Trước khi tuyên bố một luồng RSocket có độ tin cậy nghiệp vụ, hãy trả lời:

1. “Đã gửi” nghĩa là TCP nhận byte, peer nhận frame, handler nhận request hay database đã commit?
2. Client nhận acknowledgement ở giai đoạn RECEIVED, ACCEPTED hay COMPLETED?
3. Nếu transport đứt sau commit nhưng trước response, client tra cứu kết quả bằng ID nào?
4. RSocket resumption có bật ở cả hai phía và buffer/session retention đủ không?
5. Điều gì xảy ra khi process restart làm mất session state?
6. Command/event nào phải được lưu bền vững?
7. Có Transactional Outbox hoặc durable broker cho event cần phát không?
8. Consumer có inbox hoặc unique idempotency key để chống xử lý trùng không?
9. Stream có sequence/cursor và chính sách replay không?
10. Các failure window đã được kiểm thử bằng trạng thái database thực tế chưa?

Độ tin cậy truyền tải giúp byte đến peer trên kết nối đang hoạt động. RSocket resumption giúp tiếp tục một session khi gián đoạn còn trong giới hạn trạng thái được giữ. Lưu trữ bền vững bảo vệ lệnh và kết quả qua lỗi process hoặc máy chủ. Khi kết hợp acknowledgement có ý nghĩa rõ ràng, outbox/inbox, idempotency và replay theo sequence, ứng dụng RSocket mới có thể đáp ứng yêu cầu độ tin cậy nghiệp vụ thay vì chỉ dựa vào một kết nối mạng ổn định.

