# Spring Integration runtime là gì và chịu trách nhiệm nào

Spring Integration runtime là phần thực thi các luồng tích hợp đã được khai báo trong ứng dụng Spring. Nó nhận dữ liệu từ hệ thống bên ngoài hoặc từ code nội bộ, đóng gói dữ liệu thành message, chuyển message qua các channel, gọi handler phù hợp, điều phối thời điểm và luồng thực thi, rồi chuyển kết quả đến đích tiếp theo.

Có thể xem `IntegrationFlow` là bản mô tả một quy trình, còn runtime là bộ máy làm cho quy trình đó hoạt động. Runtime quản lý các thành phần Spring, kết nối chúng thành một message flow, quyết định message được gửi đồng bộ hay bất đồng bộ, kích hoạt các endpoint cần polling, quản lý trạng thái của những pattern có lưu trữ, và đưa lỗi đến nơi xử lý thích hợp.

Spring Integration cung cấp hạ tầng cho các Enterprise Integration Patterns (EIP). Logic nghiệp vụ vẫn thuộc về ứng dụng: runtime điều phối việc gọi logic đó và quản lý cách message đi qua hệ thống.

## 1. Nhìn toàn bộ message flow

Một flow thường có các vai trò sau:

- **Nguồn dữ liệu** tạo ra sự kiện hoặc bản ghi: HTTP, file, database, message broker, TCP, ứng dụng khác hoặc code nội bộ.
- **Inbound adapter** chuyển dữ liệu từ một nguồn vào hệ thống message. **Inbound gateway** thường nhận request và có thể gửi reply về caller.
- **Message channel** chuyển message giữa các thành phần, đồng thời quyết định kiểu dispatch hoặc buffering.
- **Endpoint** kết nối channel với một consumer hoặc `MessageHandler`.
- **Handler** thực hiện một bước xử lý như transform, filter, route, enrich, split, aggregate hoặc gọi service nghiệp vụ.
- **Outbound adapter** gửi dữ liệu ra hệ thống đích theo kiểu một chiều. **Outbound gateway** hỗ trợ trao đổi request-reply với hệ thống đích.

~~~mermaid
flowchart LR
    A["Nguồn dữ liệu"] --> B["Inbound adapter / gateway"]
    B --> C["Message"]
    C --> D["Channel"]
    D --> E["Endpoint + handler"]
    E --> F["Channel tiếp theo"]
    F --> G["Endpoint + handler"]
    G --> H["Outbound adapter / gateway"]
    E -. "lỗi" .-> X["errorChannel"]
    D -. "buffer / trạng thái" .-> S["MessageStore"]
~~~

Các thành phần có thể nằm trong cùng JVM hoặc kết nối với hệ thống bên ngoài. Channel trong cùng ứng dụng thường là abstraction nội bộ; khi cần giao tiếp qua mạng hoặc lưu message bền vững, flow dùng adapter, gateway, broker hoặc store phù hợp.

### Message mang dữ liệu và ngữ cảnh

Một Spring Integration message có hai phần chính:

- `payload`: dữ liệu mà handler cần xử lý, chẳng hạn một `Order`, chuỗi JSON hoặc byte array.
- `headers`: metadata đi kèm, chẳng hạn `id`, `timestamp`, `correlationId`, `replyChannel`, `errorChannel`, thông tin sequence hoặc header riêng của ứng dụng.

Header cho phép runtime và các pattern phối hợp mà không phải nhồi mọi metadata vào payload. Ví dụ, aggregator dùng correlation ID để gom các message thuộc cùng một công việc; gateway có thể dùng reply channel để nhận kết quả.

Message và header được thiết kế theo hướng bất biến. Khi cần thay đổi header hoặc tạo message mới, hãy dùng `MessageBuilder` hoặc các API của framework thay vì sửa trực tiếp message đang được chia sẻ giữa nhiều thành phần.

## 2. Runtime chịu trách nhiệm những gì?

| Trách nhiệm | Runtime thực hiện | Câu hỏi vận hành cần trả lời |
|---|---|---|
| Khởi tạo flow | Đăng ký bean, tạo endpoint và liên kết channel với handler | Flow đã được tạo và start chưa? |
| Dispatch message | Gửi message đến consumer theo semantics của channel | Message được xử lý ở thread nào? Có bị buffer không? |
| Kích hoạt consumer | Đăng ký listener hoặc chạy polling task | Endpoint đang event-driven hay polling? |
| Điều phối concurrency | Dùng caller thread, scheduler hoặc executor tùy cấu hình | Có nghẽn thread pool hoặc tranh chấp tài nguyên không? |
| Quản lý trạng thái | Lưu message, message group và trạng thái correlation khi pattern yêu cầu | Message/group có bị tồn đọng hoặc hết hạn không? |
| Kiểm soát lỗi và retry | Chuyển exception thành `ErrorMessage`, áp dụng advice và recovery | Lỗi được ném về caller hay đi vào error flow? |
| Quản lý vòng đời | Start, stop và hủy các endpoint/flow | Khi ứng dụng dừng hoặc tenant bị gỡ, flow có dừng đúng không? |
| Quan sát runtime | Cung cấp graph, metrics và observation khi được cấu hình | Thành phần nào chậm, lỗi hoặc có backlog? |

Runtime không tự bảo đảm mọi message được xử lý đúng một lần. Mức độ bền vững và khả năng phục hồi phụ thuộc vào nguồn nhận, channel, transaction manager, message store, broker, retry policy và tính idempotent của handler.

## 3. Channel quyết định cách message được chuyển

`MessageChannel` là điểm nối giữa producer và consumer. Producer chỉ cần gửi message vào channel; nó không cần biết trực tiếp handler nào sẽ xử lý. Tuy nhiên, kiểu channel ảnh hưởng rõ rệt đến thread, thứ tự xử lý, buffering và cách lỗi được quan sát.

| Channel | Cách chuyển message | Hành vi đáng chú ý |
|---|---|---|
| `DirectChannel` | Dispatch trực tiếp đến một subscriber trong thread gọi `send()` | Đồng bộ; exception có thể quay về caller; thường là lựa chọn mặc định |
| `PublishSubscribeChannel` | Phát một message đến tất cả subscriber | Dùng cho broadcast/event; nếu không cấu hình executor thì subscriber chạy trong thread gửi |
| `QueueChannel` | Đưa message vào hàng đợi để consumer nhận sau | Có buffering; consumer thường dùng polling; nên đặt capacity hữu hạn |
| `PriorityChannel` | Nhận message theo thứ tự ưu tiên do store hỗ trợ | Dùng khi mức ưu tiên quan trọng hơn FIFO thuần túy |
| `RendezvousChannel` | Sender chờ đến khi receiver nhận message | Hữu ích cho handoff đồng bộ giữa hai phía |
| `ExecutorChannel` | Dispatch đến một subscriber thông qua `TaskExecutor` | Tách thread gửi và thread xử lý; transaction gắn với thread gửi không tự truyền sang handler |

Một vài khác biệt cần nhớ:

- `DirectChannel` có semantics point-to-point: mỗi lần gửi được dispatch đến một handler. Nếu có nhiều subscriber, dispatcher chọn một subscriber theo chiến lược load balancing và failover đã cấu hình.
- `PublishSubscribeChannel` có semantics broadcast: mỗi subscriber nhận một bản chuyển giao của message. Đây không phải hàng đợi lưu message để consumer đến lấy sau.
- `QueueChannel` giữ message trong queue. Nếu queue đầy, thao tác gửi có thể phải chờ hoặc thất bại tùy timeout và cách gọi. Queue không tự tạo consumer thread; một polling endpoint phải đọc queue.
- `ExecutorChannel` đổi execution context bằng executor nhưng bản thân nó không phải queue nghiệp vụ có semantics lưu trữ. Khả năng xếp hàng của task phụ thuộc vào cấu hình executor.

Với `QueueChannel`, cấu hình capacity hữu hạn giúp tạo giới hạn tải. Queue không giới hạn có thể tăng bộ nhớ sử dụng liên tục khi tốc độ producer cao hơn tốc độ consumer. Nếu message phải sống qua sự cố tiến trình, queue trong bộ nhớ không đủ; cần persistent message store hoặc broker có durability phù hợp.

## 4. Endpoint, consumer và handler

Endpoint là thành phần nối channel với logic xử lý. Handler tập trung vào hành động trên message; endpoint quản lý cách handler được gọi và cách nó tham gia vào runtime.

Hai kiểu consumer phổ biến được chọn dựa trên loại channel đầu vào:

- **`EventDrivenConsumer`** đăng ký handler với một `SubscribableChannel`. Khi message được gửi đến channel, handler được gọi theo cơ chế dispatch của channel.
- **`PollingConsumer`** đọc message từ một `PollableChannel` theo lịch. Endpoint này cần poller để xác định lúc nào gọi `receive()` và có thể đọc bao nhiêu message trong một chu kỳ.

Một số loại endpoint khác thường gặp:

- **Channel adapter** nối nguồn hoặc đích bên ngoài với message channel. Inbound adapter thường tạo message; outbound adapter thường nhận message và gửi dữ liệu đi.
- **Messaging gateway** tạo ranh giới request-reply giữa code ứng dụng và message flow hoặc hệ thống bên ngoài.
- **Service activator** gọi một method/service để thực hiện nghiệp vụ.
- **Transformer** chuyển đổi payload hoặc cấu trúc message.
- **Filter** quyết định message có được đi tiếp hay bị loại.
- **Router** chọn channel tiếp theo dựa trên nội dung hoặc metadata.
- **Splitter và aggregator** tách một message thành nhiều message rồi gom các message liên quan thành kết quả.

Những endpoint này là các thành phần runtime có thể được quản lý như Spring bean. Vì vậy, cấu hình endpoint cũng ảnh hưởng đến lifecycle, transaction advice, retry advice, metrics và khả năng chẩn đoán.

## 5. Poller và executor điều phối thời gian, thread

Poller và executor thường cùng xuất hiện trong một flow nhưng giải quyết hai vấn đề khác nhau:

- **Poller** quyết định khi nào endpoint đọc message từ nguồn pollable hoặc `PollableChannel`.
- **TaskScheduler** lên lịch lần chạy tiếp theo của polling task.
- **TaskExecutor** quyết định task hoặc message handler được thực thi trên thread nào và với chính sách pool/queue ra sao.

Poller có thể dùng trigger theo fixed delay, fixed rate hoặc cron. Các thuộc tính thường cần quan tâm:

- `maxMessagesPerPoll`: số message tối đa được nhận trong một chu kỳ polling. Giá trị này điều chỉnh kích thước batch, không trực tiếp quy định số thread.
- `receiveTimeout`: thời gian chờ khi gọi receive mà chưa có message.
- `taskExecutor`: executor dùng để thực thi công việc polling khi cấu hình.
- `adviceChain`: nơi gắn các concern xuyên suốt như transaction hoặc retry vào polling endpoint.

Ví dụ một nguồn `MessageSource` được đọc theo lịch:

~~~java
@Bean
IntegrationFlow pollingOrders(
        MessageSource<Order> orderSource,
        OrderService orderService) {

    return IntegrationFlow.from(orderSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofMillis(500))
                                    .maxMessagesPerPoll(25)))
            .handle(orderService, "process")
            .get();
}
~~~

Ví dụ này đọc tối đa 25 message trong một chu kỳ, với khoảng delay 500 ms giữa các lần kích hoạt theo cấu hình poller. Nó không có nghĩa là luôn có 25 thread xử lý song song. Muốn tăng concurrency, cần xem loại endpoint, executor và cách phân phối message.

### Phân biệt ba đường thực thi thường gặp

1. **DirectChannel:** producer gọi `send()`, handler chạy ngay trên thread của producer. Lời gọi chỉ hoàn tất sau khi handler xử lý xong.
2. **QueueChannel:** producer gửi message vào queue; polling consumer nhận message ở một thời điểm khác. Producer có thể tiếp tục sau khi message được chấp nhận vào queue.
3. **ExecutorChannel:** producer chuyển message cho dispatcher dùng executor; handler chạy trên thread do executor cấp. Việc gửi thành công thường chỉ xác nhận handoff, không chứng minh xử lý downstream đã thành công.

Không nên thêm executor vào mọi channel theo cảm tính. Một ranh giới bất đồng bộ có thể tăng khả năng xử lý song song, nhưng cũng làm thay đổi thứ tự quan sát, cách trả lỗi, transaction boundary và nhu cầu quản lý backlog.

## 6. Vòng đời của IntegrationFlow

Trong cấu hình thông thường, `IntegrationFlow` được khai báo như một Spring bean. Khi `ApplicationContext` khởi tạo, Spring Integration đăng ký các thành phần cần thiết, tạo endpoint, liên kết channel và handler, rồi quản lý lifecycle của các endpoint theo cơ chế lifecycle của Spring.

`@EnableIntegration` kích hoạt hạ tầng Spring Integration khi ứng dụng dùng cấu hình Java. Hạ tầng này có thể đăng ký các bean nền như channel mặc định, error channel và task scheduler. Trong ứng dụng Spring Boot, cần hiểu rõ phần auto-configuration đang cung cấp những thành phần nào để tránh cấu hình trùng lặp.

Endpoint thường có các thuộc tính lifecycle như `autoStartup` và `phase`. Chúng quyết định endpoint có tự chạy khi context được khởi động và thứ tự tương đối khi các thành phần được start/stop. Khi dừng ứng dụng, cần để các nguồn vào ngừng nhận công việc và các thành phần đang chạy có cơ hội hoàn tất hoặc xử lý phần việc còn lại theo chính sách của hệ thống.

### Đăng ký flow động

Một số ứng dụng cần tạo flow theo tenant, cấu hình khách hàng, kết nối mới hoặc yêu cầu runtime. Khi đó, `IntegrationFlowContext` cho phép đăng ký một `IntegrationFlow` cùng các bean phụ thuộc trong lúc ứng dụng đang chạy.

Quy trình thường là:

1. Tạo `IntegrationFlow` từ cấu hình hoặc dữ liệu nghiệp vụ đã được kiểm tra.
2. Đăng ký flow qua `IntegrationFlowContext`, đặt ID ổn định và chọn `autoStartup` phù hợp.
3. Lấy registration để truy cập flow hoặc điều khiển lifecycle khi cần.
4. Khi flow không còn cần thiết, gọi `IntegrationFlowRegistration.destroy()` để dừng và gỡ flow cùng các bean phụ thuộc đã đăng ký.

ID rõ ràng giúp nhận diện flow trong log và tránh xung đột tên bean khi tạo nhiều flow tương tự. Với flow động, ứng dụng phải quản lý thời điểm đăng ký và hủy một cách nhất quán; nếu chỉ ngừng tham chiếu đến registration mà không hủy flow, endpoint hoặc tài nguyên liên quan có thể tiếp tục tồn tại.

## 7. Transaction và ranh giới thực thi

Transaction trong Spring Integration dựa trên cơ chế transaction của Spring. Điểm quan trọng là transaction thông thường gắn với thread hiện tại.

Với flow chạy qua `DirectChannel`, các handler tiếp theo được gọi trong cùng thread. Nếu không có ranh giới thread khác, transaction context có thể tiếp tục qua các bước đồng bộ của flow.

Với `QueueChannel`, `ExecutorChannel` hoặc code tự tạo thread mới, flow đã chuyển sang execution context khác. Transaction gắn với thread ban đầu không tự đi theo message. Vì vậy, nếu producer gửi message vào queue trong một transaction rồi consumer xử lý sau, transaction của producer không bao trùm phần xử lý của consumer.

Poller hỗ trợ cấu hình transaction advice để bao một chu kỳ nhận và chuyển tiếp message trong transaction. Điều này đặc biệt hữu ích khi thao tác nhận message từ một persistent store có thể tham gia cùng transaction. Ví dụ, nếu message được lấy khỏi JDBC-backed channel store trong transaction và xử lý thất bại, rollback có thể khôi phục thao tác lấy message khi store và transaction manager được cấu hình tương thích.

Khi thiết kế transaction, hãy xác định rõ:

- Transaction bắt đầu ở đâu: lúc nhận từ nguồn, lúc handler chạy hay lúc ghi kết quả?
- Những tài nguyên nào thực sự tham gia cùng transaction manager?
- Có channel hoặc executor nào làm thay đổi thread giữa các bước không?
- Nếu gửi sang broker hoặc gọi API bên ngoài, hệ thống xử lý tình huống commit database thành công nhưng gửi bên ngoài thất bại như thế nào?

Không nên giả định một transaction cục bộ bao trùm mọi hệ thống bên ngoài. Với tích hợp nhiều hệ thống, thường cần idempotency, outbox/inbox, xác nhận message hoặc cơ chế bù trừ tùy yêu cầu nghiệp vụ.

## 8. Retry, recovery và error channel

Retry là chính sách gọi lại một handler khi thao tác thất bại. Spring Integration hỗ trợ retry thông qua handler advice, điển hình là `RequestHandlerRetryAdvice`, dựa trên cơ chế retry của Spring Framework.

Có hai kiểu cần phân biệt:

- **Stateless retry:** advice thực hiện các lần thử lại trong cùng lần gọi. Thread có thể phải chờ trong thời gian backoff.
- **Stateful retry:** advice lưu trạng thái retry theo khóa của message. Khi một lần xử lý thất bại, exception được trả về cho nguồn; nguồn có thể phát lại message và lần giao tiếp sau tiếp tục trạng thái retry đã lưu.

Khi hết số lần thử, recovery callback có thể chuyển lỗi sang một channel chuyên xử lý, ví dụ thông qua `ErrorMessageSendingRecoverer`. Retry nên giới hạn số lần, có backoff phù hợp và chỉ áp dụng cho lỗi có khả năng hồi phục. Nếu handler đã tạo side effect trước khi ném exception, lần retry có thể lặp side effect; do đó thao tác quan trọng cần có tính idempotent hoặc cơ chế chống trùng.

### Lỗi được chuyển đi đâu?

Cách quan sát exception phụ thuộc vào flow đang chạy đồng bộ hay bất đồng bộ:

- Với flow đồng bộ qua `DirectChannel`, exception từ handler có thể truyền ngược theo call stack về caller.
- Với flow bất đồng bộ qua executor hoặc polling task, caller ban đầu không còn chờ cùng call stack. Runtime chuyển lỗi thành `ErrorMessage` và gửi đến error channel theo cơ chế xử lý lỗi của endpoint.
- Nếu message có header `errorChannel`, runtime ưu tiên channel đó. Nếu không, lỗi thường được gửi đến bean channel toàn cục tên `errorChannel`.

Error channel mặc định là `PublishSubscribeChannel` và có `LoggingHandler` để ghi log ở mức ERROR. Ứng dụng có thể đăng ký thêm handler, router hoặc error flow để phân loại lỗi, ghi nhận trạng thái, gửi cảnh báo hoặc chuyển message đến dead-letter queue.

Một error flow hữu ích nên giữ lại ngữ cảnh cần chẩn đoán: exception gốc, message gây lỗi, tên component, correlation ID và thông tin nguồn. Cần tránh chỉ ghi log rồi bỏ message nếu nghiệp vụ yêu cầu retry, redelivery hoặc xử lý thủ công.

## 9. MessageStore và correlation quản lý trạng thái

Nhiều pattern chỉ hoạt động khi runtime nhớ các message đã đến trước đó. Ví dụ, aggregator phải giữ các message thuộc cùng một nhóm cho đến khi đủ điều kiện tạo kết quả. `MessageStore` và `MessageGroupStore` cung cấp abstraction để lưu trạng thái đó.

- **`MessageStore`** lưu message, ví dụ message được buffer trong một `QueueChannel`.
- **`MessageGroupStore`** lưu các nhóm message và metadata của nhóm, thường dùng cho aggregator, resequencer và các pattern tương quan khác.
- **In-memory store** dễ dùng nhưng trạng thái có thể mất khi tiến trình dừng.
- **Persistent store** như các triển khai JDBC có thể giữ trạng thái qua lần restart và có thể tham gia transaction nếu được cấu hình tương thích.

### Correlation và aggregator

Correlation xác định message nào thuộc cùng một công việc. Mặc định, correlation handler thường dựa trên header `correlationId`; ứng dụng có thể thay bằng `CorrelationStrategy` riêng.

Aggregator thường làm việc theo trình tự:

1. Nhận message và xác định correlation key.
2. Thêm message vào nhóm tương ứng trong `MessageGroupStore`.
3. Gọi `ReleaseStrategy` để kiểm tra nhóm đã đủ điều kiện phát kết quả chưa.
4. Khi đủ điều kiện, xử lý nhóm và phát message tổng hợp.
5. Quản lý nhóm đã hoàn tất, message đến trễ và thời hạn lưu trạng thái.

Các header `sequenceNumber` và `sequenceSize` thường hỗ trợ nhận biết vị trí message và số phần dự kiến trong một sequence. Chỉ dựa vào số lượng message có thể chưa đủ nếu flow có filter làm rơi một phần sequence; khi đó cần release strategy phù hợp với nghiệp vụ.

Message group có thể tồn tại lâu nếu thiếu message hoặc release condition không bao giờ đúng. Cần cấu hình timeout, expiry và cơ chế dọn nhóm cũ như `MessageGroupStoreReaper` khi phù hợp. Trong môi trường nhiều instance, shared persistent store cần cơ chế lock/correlation nhất quán để nhiều node không cập nhật cùng nhóm một cách sai lệch.

Persistent store giúp lưu trạng thái, nhưng không tự tạo bảo đảm exactly-once cho toàn bộ flow. Vẫn cần xử lý duplicate, message đến trễ, retry và sự cố giữa các bước.

## 10. Quan sát và chẩn đoán runtime

Khi flow không chạy như mong đợi, hãy kiểm tra theo đường đi của message thay vì chỉ xem stack trace cuối cùng.

1. **Nguồn có tạo message không?** Kiểm tra inbound adapter/gateway, kết nối ngoài, lịch polling và log nhận dữ liệu.
2. **Message đã vào channel chưa?** Kiểm tra tên channel, kết quả send, capacity, timeout và backlog.
3. **Endpoint có được tạo và đang chạy không?** Kiểm tra lifecycle, `autoStartup`, poller và subscription.
4. **Handler có được gọi không?** Kiểm tra thread name, thời gian xử lý, exception và retry.
5. **Có ranh giới bất đồng bộ không?** Xác định `QueueChannel`, `ExecutorChannel`, poller hoặc executor nào đã nhận trách nhiệm xử lý tiếp.
6. **Transaction có bao đúng thao tác không?** Kiểm tra transaction manager, thread boundary và tài nguyên tham gia.
7. **Có trạng thái bị giữ lại không?** Kiểm tra message store, số message trong group, correlation key và thời điểm hết hạn.
8. **Error flow có nhận lỗi không?** Kiểm tra header `errorChannel`, global `errorChannel`, recovery callback và dead-letter path.

Spring Integration cung cấp `IntegrationGraphServer` để biểu diễn các component và liên kết trong runtime graph. Graph giúp đối chiếu flow thực tế đã được đăng ký với flow mà nhóm phát triển nghĩ rằng mình đã cấu hình.

Về metrics và tracing, Spring Integration tích hợp Micrometer Observation. Khi có `ObservationRegistry` và cấu hình integration management phù hợp, các producer, handler, gateway và một số endpoint có thể được instrument để thu thập thời gian xử lý, outcome và trace. Có thể dùng `@EnableIntegrationManagement` cùng `observationPatterns()` để chọn nhóm component cần theo dõi. Hãy gắn correlation ID hoặc trace context xuyên suốt các ranh giới hệ thống để nối log và trace của cùng một công việc.

### Dấu hiệu của các vấn đề hiệu năng phổ biến

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Queue tăng liên tục | Producer nhanh hơn consumer; handler bị chặn hoặc downstream chậm | Đo tốc độ vào/ra, giới hạn capacity, tăng consumer có kiểm soát hoặc giảm tải |
| Heap tăng theo thời gian | Queue không giới hạn, message payload lớn hoặc message group không hết hạn | Dùng bounded queue, giới hạn kích thước payload, đặt expiry và dọn group |
| Polling phản hồi chậm | Trigger quá thưa, receive timeout dài hoặc poller xử lý batch lớn | Điều chỉnh trigger, timeout và `maxMessagesPerPoll` theo độ trễ mục tiêu |
| Executor thường xuyên bão hòa | Pool quá nhỏ, queue task đầy hoặc handler blocking lâu | Đo thời gian handler, điều chỉnh pool/queue và chính sách từ chối task |
| Lỗi xuất hiện ở thread khác caller | Flow đã chuyển sang executor hoặc polling task | Theo dõi error channel, trace ID và log ở consumer thread |
| Transaction không rollback bước sau | Flow đã vượt qua ranh giới thread hoặc tài nguyên không cùng transaction | Đặt transaction ở consumer boundary và thiết kế idempotency/outbox |
| Aggregator giữ group quá lâu | Thiếu message, correlation sai hoặc release strategy không đạt | Kiểm tra sequence/header, release condition và expiry |

Tăng số thread không phải lúc nào cũng làm flow nhanh hơn. Nếu bottleneck nằm ở database, API bên ngoài hoặc lock của message group, nhiều thread hơn có thể làm tăng contention và số tác vụ đang chờ. Hãy đo từng endpoint, channel và dependency trước khi thay đổi concurrency.

## 11. Ví dụ flow đồng bộ tối giản

Ví dụ dưới đây khai báo một flow nhận đơn hàng, chuẩn hóa dữ liệu, gọi service nghiệp vụ rồi gửi kết quả đến channel đầu ra. Các channel đều là `DirectChannel`, nên các bước trong flow chạy đồng bộ trên thread gửi message.

Trong ví dụ, giả sử `OrderService.process(Order)` trả về một kết quả để flow chuyển tiếp. Nếu method xử lý trả về `void`, sẽ không có reply message để channel đầu ra nhận.

~~~java
@Configuration
@EnableIntegration
class OrderFlowConfiguration {

    @Bean
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel ordersOut() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow.from(ordersIn())
                .<Order, Order>transform(order -> order.normalized())
                .handle(orderService, "process")
                .channel(ordersOut())
                .get();
    }
}
~~~

Để chuyển flow này sang xử lý bất đồng bộ, cần chọn channel hoặc endpoint phù hợp và xác định rõ nơi consumer tiếp tục xử lý. Nếu dùng `QueueChannel`, hãy cấu hình poller cho endpoint đọc queue và chọn store nếu cần persistence. Nếu dùng `ExecutorChannel`, hãy cấu hình executor, giới hạn tài nguyên và error handling. Sau mỗi thay đổi, cần đánh giá lại transaction boundary, thứ tự xử lý và khả năng retry.

## 12. Checklist khi thiết kế một flow

Trước khi đưa flow vào vận hành, hãy trả lời được các câu hỏi sau:

- Nguồn vào là adapter, gateway, `MessageSource` hay code chủ động gửi message?
- Channel nào cần đồng bộ, broadcast, buffering hoặc dispatch qua executor?
- Consumer nào event-driven, consumer nào polling? Poller dùng trigger và batch size nào?
- Thread pool, queue capacity và timeout có giới hạn rõ ràng không?
- Transaction bắt đầu và kết thúc ở đâu? Những tài nguyên nào tham gia transaction?
- Retry áp dụng cho lỗi nào, tối đa bao nhiêu lần và recovery đi đâu?
- Message hoặc message group có cần persistence, expiry và cleanup không?
- Correlation key có duy nhất và ổn định cho từng công việc không?
- Error channel có giữ đủ ngữ cảnh để retry, cảnh báo hoặc xử lý thủ công không?
- Có graph, metrics, trace và log đủ để xác định component đang chậm hoặc lỗi không?

Khi trả lời được các câu hỏi này, nhóm phát triển có thể giải thích flow đang chạy thế nào, message đang nằm ở đâu, thread nào đang xử lý, trạng thái nào đang được giữ và lỗi sẽ đi theo đường nào. Đó chính là phạm vi trách nhiệm cốt lõi của Spring Integration runtime.

## Tài liệu tham khảo

Các liên kết dưới đây trỏ đến Spring Integration Reference Guide. Hãy đối chiếu với phiên bản Spring Integration mà ứng dụng đang sử dụng vì một số API và chi tiết cấu hình có thể thay đổi theo phiên bản.

- [Overview of Spring Integration Framework](https://docs.spring.io/spring-integration/reference/overview.html)
- [Message Endpoints và Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Retry Advice](https://docs.spring.io/spring-integration/reference/handler-advice/classes.html)
- [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Integration Graph](https://docs.spring.io/spring-integration/reference/graph.html)
- [Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)

