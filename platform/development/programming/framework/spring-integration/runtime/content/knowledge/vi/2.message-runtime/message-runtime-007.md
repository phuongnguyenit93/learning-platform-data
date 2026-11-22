# Message history và trace đường đi

Trong Spring Integration, một message có thể đi qua nhiều channel, endpoint và luồng xử lý khác nhau trước khi hoàn tất. Khi hệ thống chạy đồng bộ, bất đồng bộ, có queue, poller, executor, retry hoặc nhánh lỗi, chỉ nhìn vào payload thường không đủ để biết message đã đi qua đâu, đang dừng ở đâu và vì sao kết quả bị chậm hoặc thất bại.

Message history và tracing giúp trả lời các câu hỏi đó. Message history ghi lại những component mà message đã đi qua. Log và metric cung cấp sự kiện, thời gian và số liệu vận hành. Distributed tracing liên kết các lần xử lý trong nhiều thread hoặc nhiều dịch vụ. Kết hợp đúng các lớp này giúp ta lần theo đường đi của message mà không phải ghi payload nhạy cảm vào log.

## 1. Phân biệt topology, history và trace

Trước khi chẩn đoán, cần phân biệt ba loại thông tin thường bị gọi chung là “trace”.

| Loại thông tin | Trả lời câu hỏi | Nguồn thường dùng |
|---|---|---|
| Topology | Hệ thống được nối với nhau như thế nào? | IntegrationFlow, channel, endpoint, IntegrationGraphServer |
| Message history | Message cụ thể đã đi qua những component nào? | MessageHistory trong message header |
| Runtime observability | Component xử lý lúc nào, mất bao lâu, có lỗi hoặc backlog không? | Log, metric, Micrometer Observation và tracing |

Topology mô tả cấu trúc đang được khai báo hoặc đăng ký. Nó không chứng minh một message đã thực sự đi qua mọi node. Message history mô tả hành trình của một message, nhưng không phải bản ghi kiểm toán đầy đủ và cũng không tự giải thích mọi khoảng thời gian chờ. Log, metric và trace bổ sung thời điểm, thời lượng, lỗi và quan hệ giữa các lần xử lý.

Một hệ thống quan sát tốt thường kết hợp cả ba: dùng graph để biết đường đi có thể có, history để tìm các component message đã chạm tới, rồi dùng log và metric để giải thích điều xảy ra tại từng điểm.

## 2. Nhận diện message bằng các header

Muốn tìm đúng message trong log hoặc trong một luồng có nhiều message đồng thời, trước hết phải chọn khóa nhận diện phù hợp.

| Giá trị | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Message ID | Nhận diện một message cụ thể | Tìm các log liên quan tới một message |
| Correlation ID | Liên kết nhiều message thuộc cùng một nghiệp vụ hoặc nhóm xử lý | Theo dõi một đơn hàng, một yêu cầu hoặc các message do splitter tạo ra |
| Trace ID | Liên kết các span của một lần thực thi xuyên qua thread hoặc dịch vụ | Theo dõi request xuyên qua nhiều thành phần và hệ thống |
| Sequence number/size | Vị trí và kích thước của một chuỗi message | Theo dõi các phần tử được tách ra và chờ aggregator ghép lại |

Message ID không thay thế Correlation ID. Một nghiệp vụ có thể tạo ra nhiều message, mỗi message có ID riêng nhưng cùng Correlation ID. Tương tự, Correlation ID không tự động là Trace ID: một đơn hàng có thể được xử lý qua nhiều request hoặc nhiều lần thử, trong khi mỗi lần thực thi có thể có trace riêng.

Nên tạo Correlation ID tại biên tiếp nhận nếu hệ thống chưa có mã nghiệp vụ đáng tin cậy, sau đó giữ nó qua các bước xử lý. Ví dụ, producer có thể tạo message như sau:

~~~java
Message<Order> message = MessageBuilder.withPayload(order)
    .setHeader("correlationId", businessRequestId)
    .build();

ordersInputChannel.send(message);
~~~

Tên header trong ví dụ là header nghiệp vụ do ứng dụng quy ước. Nếu cần tương thích với splitter, aggregator hoặc hệ thống tracing, hãy dùng đúng header chuẩn và cơ chế propagation mà thành phần đó yêu cầu. Không nên tự tạo một giá trị header tên traceId rồi xem nó như distributed trace hoàn chỉnh; trace phân tán còn cần quản lý span và truyền context giữa các ranh giới thực thi.

Spring Integration hỗ trợ các header correlation và sequence cho những luồng có chia tách, định tuyến và tổng hợp message. Khi splitter tạo nhiều message con, các message này có thể có cùng correlation nhưng khác message ID và sequence number. Aggregator dựa vào thông tin nhóm để biết những message nào thuộc cùng một tập hợp. Khi điều tra, hãy giữ cả message ID lẫn Correlation ID để phân biệt một phần tử với toàn bộ nghiệp vụ.

## 3. Bật và đọc Message History

Spring Integration cung cấp Message History để ghi nhận các component được theo dõi mà message đi qua. Lịch sử được lưu trong header của message, nên có thể được đọc ở các endpoint phía sau mà không cần một kho tra cứu riêng cho từng bước.

Có thể bật tính năng này bằng annotation trong cấu hình Java:

~~~java
@Configuration
@EnableIntegration
@EnableMessageHistory
public class IntegrationConfiguration {
}
~~~

Khi Message History được bật, các component có khả năng tham gia ghi history sẽ bổ sung thông tin của chúng vào message. Một mục history thường cung cấp tên component, kiểu component và thời điểm được ghi nhận. Tên component ổn định giúp đối chiếu history với IntegrationFlow và log dễ hơn. Vì vậy, nên đặt tên rõ ràng cho bean, channel và endpoint thay vì để mọi thành phần dùng tên tự sinh khó đọc.

Có thể đọc history từ một message tại endpoint cần kiểm tra:

~~~java
@Service
public class TraceInspector {

    private static final Logger log =
        LoggerFactory.getLogger(TraceInspector.class);

    @ServiceActivator(inputChannel = "orders.inspect")
    public void inspect(Message<?> message) {
        MessageHistory history = MessageHistory.read(message);

        log.info("messageId={}, correlationId={}, history={}",
            message.getHeaders().getId(),
            message.getHeaders().get("correlationId"),
            history == null ? "disabled" : history);
    }
}
~~~

Các import chính trong ví dụ thuộc Spring Messaging và Spring Integration:

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.history.MessageHistory;
import org.springframework.messaging.Message;
~~~

MessageHistory.read(message) trả về lịch sử gắn với message; nếu history chưa được bật hoặc không có trên message thì kết quả có thể là null. Hãy kiểm tra null trước khi đọc. Đoạn code trên ghi message ID, Correlation ID và history, không ghi payload. Trong ứng dụng thực tế, TraceInspector chỉ là một endpoint quan sát mẫu; hãy đặt nó tại điểm mà ứng dụng thực sự cần kiểm tra.

Nếu không muốn theo dõi mọi component, có thể giới hạn các component được ghi bằng cấu hình MessageHistoryConfigurer và các component name pattern phù hợp với phiên bản Spring Integration đang sử dụng. Chỉ bật history cho các flow hoặc khu vực cần điều tra sẽ giúp giảm kích thước header và chi phí xử lý trên luồng có lưu lượng lớn.

### Message History ghi được và không ghi được gì?

History hữu ích để biết message đã chạm tới các component nào và thứ tự các mục history được ghi. Nó không tự ghi nội dung payload, không đảm bảo mọi thao tác nội bộ đều có một mục riêng, và không thay thế log lỗi hay metric. Một component không được theo dõi, không có tên phù hợp hoặc nằm ngoài ranh giới ứng dụng có thể không xuất hiện trong history.

Không nên suy ra thời gian xử lý chính xác của một endpoint chỉ bằng cách lấy hiệu hai timestamp liên tiếp. Khoảng chênh có thể bao gồm thời gian xử lý, thời gian chờ trong queue, thời gian chờ poller, scheduling và độ trễ giữa các thread. Muốn đo thời lượng một bước, hãy dùng metric hoặc span được đặt quanh thao tác đó.

Vì history nằm trong header, message phải giữ được header khi được chuyển đổi hoặc truyền qua adapter. Các bước tạo message mới bằng code tùy chỉnh cần giữ lại những header nghiệp vụ và tracing cần thiết. Khi đi qua broker, HTTP hoặc một ranh giới serialization, hãy kiểm tra header nào thực sự được truyền và khôi phục ở phía nhận; không mặc định mọi header nội bộ đều được bảo toàn.

## 4. Đọc đường đi qua channel và endpoint

Message thường đi qua channel để được chuyển giao cho endpoint. Channel quyết định cách message được chuyển tiếp; endpoint thực hiện công việc như filter, transformer, router, service activator, splitter hoặc aggregator. Khi lần theo history, cần biết loại channel nằm giữa hai endpoint vì nó quyết định thread nào tiếp tục xử lý và message có thể phải chờ ở đâu.

| Channel | Cách chuyển giao | Hệ quả khi trace |
|---|---|---|
| DirectChannel | Gọi subscriber trên thread gửi message | Lỗi xử lý thường có thể truyền ngược về bên gửi; đường đi dễ lần theo trong cùng call stack |
| ExecutorChannel | Giao việc cho executor | Xử lý có thể tiếp tục trên worker thread; cần tìm log theo ID thay vì dựa vào thread gửi ban đầu |
| QueueChannel | Giữ message trong queue cho consumer nhận sau | Có thể có khoảng chờ giữa send và receive; cần xem queue depth và poller |
| PublishSubscribeChannel | Phân phối message tới nhiều subscriber | Một message có thể tạo ra nhiều nhánh xử lý; các nhánh có thể chạy đồng thời nếu cấu hình executor |

Một đường đi minh họa có cả xử lý đồng bộ lẫn bất đồng bộ:

~~~mermaid
flowchart LR
    P[Producer thread] --> D[DirectChannel]
    D --> F[Filter / Transformer]
    F --> E[ExecutorChannel]
    E --> W[Worker thread]
    W --> Q[QueueChannel]
    Q -->|Poller nhận message| T[Polling thread]
    T --> S[Service Activator]
    S --> R[Kết quả hoặc reply channel]
~~~

Ở đoạn DirectChannel, producer thường chờ endpoint xử lý xong. Khi đi qua ExecutorChannel, công việc có thể được thực thi trên worker thread và producer không còn là thread thực hiện phần xử lý tiếp theo. Với QueueChannel, message có thể nằm trong queue cho tới khi Poller/consumer nhận được. Do đó, một khoảng thời gian dài giữa hai mục history không nhất thiết có nghĩa endpoint trước đó chạy chậm; message có thể đang chờ được lấy ra.

Khi đọc flow, hãy xác định lần lượt:

1. Channel đầu vào nhận message là channel nào và có subscriber hoặc consumer đang hoạt động không.
2. Endpoint tiếp theo là loại nào: filter, transformer, router, service activator hay endpoint khác.
3. Channel sau endpoint là DirectChannel, ExecutorChannel, QueueChannel hay PublishSubscribeChannel.
4. Có Poller, TaskExecutor hoặc cơ chế scheduling nào tạo ra ranh giới thread không.
5. Có nhánh router, publish-subscribe, splitter hoặc aggregator nào khiến message đi theo nhiều đường không.

Không nên xem IntegrationFlow như một call stack tuyến tính duy nhất. Router có thể chọn một nhánh; PublishSubscribeChannel có thể phát message tới nhiều subscriber; splitter tạo message con; aggregator chờ nhiều message rồi tạo kết quả tổng hợp. Trong các trường hợp đó, mỗi nhánh có thể có history và thời điểm hoàn tất riêng. Hãy dùng Correlation ID để gom các message cùng nghiệp vụ, sau đó dùng Message ID để lần từng nhánh.

## 5. Kết hợp history với log và ChannelInterceptor

History cho biết message đã qua component nào; log cung cấp sự kiện có ngữ cảnh tại một thời điểm cụ thể. Log nên có cấu trúc và chứa tối thiểu message ID, Correlation ID, tên channel hoặc endpoint, kết quả xử lý và mã lỗi nếu có. Nhờ đó, có thể tìm cùng một message qua nhiều thread mà không phụ thuộc vào thứ tự log xuất hiện.

ChannelInterceptor là một điểm mở rộng phù hợp để quan sát việc gửi và nhận qua channel. Ví dụ, trong phương thức preSend có thể ghi nhận tên channel cùng các khóa nhận diện:

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    log.debug("send channel={} messageId={} correlationId={}",
        channel,
        message.getHeaders().getId(),
        message.getHeaders().get("correlationId"));
    return message;
}
~~~

Interceptor có thể được đăng ký trực tiếp trên channel hoặc áp dụng toàn cục theo pattern bằng cơ chế global channel interceptor. Nên giới hạn pattern vào các channel cần quan sát để tránh tạo quá nhiều log trên toàn bộ hệ thống. Nếu cần hiểu cả hai chiều, hãy cân nhắc các callback gửi và nhận phù hợp của ChannelInterceptor, đồng thời nhớ rằng callback nhận chỉ áp dụng cho loại channel hỗ trợ receive.

Không ghi toàn bộ payload vào log một cách mặc định. Payload có thể chứa thông tin cá nhân, bí mật nghiệp vụ hoặc dữ liệu lớn. Hãy ghi ID, loại message, kích thước, trạng thái và một số trường đã được cho phép. Nếu phải ghi một giá trị nghiệp vụ để điều tra, hãy áp dụng quy tắc che dữ liệu và thời hạn lưu log của hệ thống.

Khi dùng MDC hoặc ThreadLocal để gắn Correlation ID vào log, cần chú ý ranh giới executor. Context gắn với thread gửi không tự động xuất hiện trên worker thread. Hãy dùng cơ chế context propagation phù hợp với TaskExecutor hoặc thư viện tracing của ứng dụng; đồng thời bảo đảm context được xóa sau khi tác vụ hoàn tất để tránh rò rỉ ID sang message khác.

## 6. Theo dõi lỗi, retry và transaction

Một message xuất hiện trong history không đồng nghĩa nghiệp vụ đã commit thành công. History có thể đã được ghi trước khi transaction kết thúc. Nếu transaction rollback, message có thể được nhận lại hoặc xử lý lại, trong khi log của lần thử trước vẫn còn. Vì vậy, khi điều tra kết quả cuối cùng, phải kiểm tra cả transaction outcome, retry và trạng thái lưu trữ.

### Error flow

Khi endpoint phát sinh exception, cách lỗi được quan sát phụ thuộc vào ranh giới thực thi. Với xử lý đồng bộ trên DirectChannel, exception thường có thể truyền ngược về bên gọi. Với xử lý bất đồng bộ qua executor hoặc poller, bên gửi ban đầu có thể đã kết thúc trước khi lỗi xảy ra; khi đó cần kiểm tra errorChannel và error handler tương ứng.

Spring Integration biểu diễn lỗi được gửi vào error flow bằng ErrorMessage. Phần payload của ErrorMessage thường là exception; với MessagingException, có thể kiểm tra failedMessage để tìm message gây lỗi và cause để tìm nguyên nhân gốc. Khi log lỗi, nên ghi message ID, Correlation ID, tên endpoint, exception type và failed message metadata. Không chỉ ghi stack trace mà thiếu khóa để nối lỗi về message ban đầu.

### Retry

Retry có thể khiến cùng một thao tác được thực hiện nhiều lần. Không nên chỉ nhìn một dòng history rồi kết luận message chỉ được xử lý một lần. Hãy ghi rõ số lần thử bằng cơ chế retry/advice đang dùng, phân biệt lỗi tạm thời với lỗi cuối cùng và kiểm tra chính sách backoff. Với thao tác có side effect, cần bảo đảm tính idempotent hoặc có khóa chống xử lý trùng để retry không tạo ra kết quả nghiệp vụ lặp.

### Transaction và Message Store

Poller có thể được cấu hình chạy trong transaction. Khi điều tra, cần phân biệt thời điểm endpoint bắt đầu xử lý với thời điểm transaction commit. Một log “đã xử lý” được ghi trước commit chưa đủ để chứng minh dữ liệu đã được xác nhận. Nếu cần bằng chứng chắc chắn, hãy ghi nhận kết quả sau commit hoặc dùng cơ chế audit/outbox phù hợp với transaction của ứng dụng.

MessageStore và MessageGroupStore phục vụ lưu message hoặc nhóm message cho các trường hợp như aggregator, resequencer và xử lý cần giữ trạng thái. Chúng hữu ích cho phục hồi và quản lý trạng thái, nhưng không tự động trở thành nhật ký kiểm toán đầy đủ. Nếu yêu cầu là truy vấn lịch sử nghiệp vụ lâu dài, cần thiết kế kho audit riêng với retention, khóa tra cứu và tính toàn vẹn phù hợp.

## 7. Xem topology và trạng thái runtime

Khi history dừng ở một component, bước tiếp theo là xác minh component kế tiếp có tồn tại và đang hoạt động hay không. Spring Integration cung cấp IntegrationGraphServer để biểu diễn các component và liên kết của integration context. Trong ứng dụng có cấu hình Spring Boot Actuator, topology này cũng có thể được công bố qua endpoint integration graph nếu endpoint đã được bật và expose.

Graph hữu ích để phát hiện channel không có consumer, endpoint không được đăng ký như dự kiến hoặc đường nối khác với thiết kế. Graph không hiển thị đầy đủ hành trình của một message cụ thể, cũng không thay thế metric về queue depth hay executor. Hãy đối chiếu graph với MessageHistory và log.

Với flow được đăng ký động, cần kiểm tra vòng đời của flow trong IntegrationFlowContext: flow đã được đăng ký chưa, endpoint đã start chưa, có bị stop hoặc unregister trong lúc điều tra không. Khi flow thay đổi, topology runtime cũng thay đổi. Một message cũ có thể mang history của cấu trúc trước đó, trong khi message mới đi qua cấu trúc sau khi flow được đăng ký lại.

Để kiểm tra điểm nghẽn, hãy xem thêm các số liệu vận hành phù hợp:

- QueueChannel: số lượng message đang chờ, tốc độ enqueue/dequeue và thời gian chờ.
- ExecutorChannel: kích thước pool, số worker đang bận, hàng đợi task và số task bị từ chối.
- Poller: chu kỳ polling, số message mỗi lần poll, thời gian xử lý và số lần poll không có message.
- Endpoint: số message nhận/xử lý, số lỗi và thời lượng xử lý nếu instrumentation đã được bật.
- Error flow: số lỗi theo loại, số message đi vào errorChannel và kết quả xử lý lỗi.

Micrometer metrics và Micrometer Observation có thể bổ sung số liệu và span cho các thành phần được instrument. Khi cần trace xuyên dịch vụ, hãy tích hợp với Micrometer Tracing hoặc OpenTelemetry và bảo đảm trace context được truyền qua các giao thức liên quan. Message History vẫn hữu ích trong phạm vi Spring Integration, còn distributed trace cung cấp quan hệ cha-con và thời lượng qua nhiều ranh giới thực thi.

## 8. Quy trình chẩn đoán một message bị chậm hoặc thất lạc

Giả sử một đơn hàng đã được gửi vào flow nhưng không thấy kết quả. Có thể lần theo theo trình tự sau:

1. **Chốt khóa tìm kiếm.** Lấy message ID nếu đang điều tra một message cụ thể; lấy Correlation ID nếu cần gom toàn bộ các message của đơn hàng hoặc một lần xử lý.
2. **Đọc history.** Tìm component cuối cùng xuất hiện trong history. Xác minh Message History đã bật, component có được theo dõi và header còn được giữ qua các adapter hay không.
3. **Đối chiếu topology.** Dùng tên component trong history để tìm channel và endpoint tiếp theo trên IntegrationFlow hoặc IntegrationGraphServer.
4. **Kiểm tra kiểu channel.** Nếu là DirectChannel, kiểm tra call stack và exception của thread gửi. Nếu là ExecutorChannel, tìm worker, task queue và log theo ID. Nếu là QueueChannel, kiểm tra queue depth và consumer poller.
5. **Kiểm tra nhánh.** Nếu có router hoặc publish-subscribe, xác định nhánh nào được chọn hoặc subscriber nào đã nhận message. Nếu có splitter/aggregator, kiểm tra sequence và trạng thái nhóm theo Correlation ID.
6. **Kiểm tra lỗi và retry.** Tìm ErrorMessage, failedMessage, exception cause, số lần thử và trạng thái cuối cùng của retry.
7. **Kiểm tra transaction và lưu trữ.** Xác minh transaction commit hay rollback, message có được nhận lại không và MessageStore/MessageGroupStore có đang giữ trạng thái chờ hay không.
8. **Đo khoảng thời gian.** Dùng metric hoặc span để xác định message đang chờ trong queue, chờ executor, chờ poller hay đang chạy trong endpoint. Không gán toàn bộ khoảng chênh timestamp của history cho thời gian thực thi endpoint.

Một số dấu hiệu thường gặp:

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Không có history | Chưa bật history, component bị loại khỏi pattern, message bị tạo mới làm mất header hoặc message đi qua ranh giới không truyền header |
| History dừng ở channel đầu vào | Chưa có subscriber/consumer, endpoint chưa start, flow chưa đăng ký hoặc message đang chờ consumer |
| History có bước ExecutorChannel nhưng không thấy bước sau | Executor quá tải, task bị từ chối, worker lỗi hoặc log ở thread khác chưa được nối bằng ID |
| History có QueueChannel nhưng bước sau xuất hiện muộn | Queue backlog, poller chạy chậm, consumer dừng hoặc giới hạn số message mỗi lần poll |
| Cùng Correlation ID nhưng nhiều Message ID | Có thể là splitter, retry, publish-subscribe hoặc nhiều message của cùng nghiệp vụ; cần phân loại theo sequence và nhánh |
| Có history nhưng nghiệp vụ không hoàn tất | Kiểm tra exception, retry, transaction rollback, aggregator chưa đủ message hoặc side effect chưa commit |

## 9. Giữ tracing hữu ích và an toàn khi chạy production

Message History làm tăng metadata trên mỗi message. Với flow dài hoặc lưu lượng cao, bật history toàn cục có thể làm tăng chi phí tạo message, sao chép header, serialization và log. Hãy giới hạn component pattern, chỉ bật mức chi tiết cao trong khoảng thời gian cần thiết nếu có thể, và theo dõi tác động lên throughput cùng bộ nhớ.

Đặt tên channel và endpoint theo nghiệp vụ hoặc chức năng, ví dụ orders.validate, orders.persist hoặc orders.error. Dùng cùng một quy ước tên giữa flow, log và dashboard để người trực vận hành có thể đối chiếu nhanh. Tránh đặt tên chứa dữ liệu runtime như mã khách hàng hoặc ID của từng request.

Không dùng Message History làm kho audit bất biến. Header có thể bị loại bỏ, thay đổi hoặc không được truyền qua một adapter; lịch sử cũng không chứng minh transaction đã commit. Nếu nghiệp vụ yêu cầu bằng chứng xử lý, hãy ghi audit event có cấu trúc vào nơi lưu trữ bền vững và gắn message ID/Correlation ID để truy vấn.

Với distributed tracing, bảo đảm trace context được truyền đúng qua HTTP, messaging broker và executor. Kiểm tra sampling để biết trace nào được giữ lại; một trace không xuất hiện có thể do sampling hoặc propagation chưa cấu hình, chứ không nhất thiết message chưa được xử lý. Tránh ghi token, thông tin xác thực, payload nhạy cảm hoặc dữ liệu cá nhân vào span attribute.

## 10. Checklist khi triển khai

- [ ] Đặt tên ổn định cho channel, endpoint và IntegrationFlow.
- [ ] Tạo hoặc nhận Correlation ID tại biên tiếp nhận và giữ nó qua các bước xử lý.
- [ ] Bật Message History ở phạm vi cần thiết và xác minh bằng MessageHistory.read(message).
- [ ] Ghi log có cấu trúc với message ID, Correlation ID, component, kết quả và mã lỗi.
- [ ] Xác định các ranh giới DirectChannel, ExecutorChannel, QueueChannel và Poller trong flow.
- [ ] Kiểm tra ErrorMessage, retry và transaction outcome khi có lỗi hoặc xử lý lặp.
- [ ] Dùng IntegrationGraphServer để đối chiếu topology runtime; dùng metric/span để đo thời gian và backlog.
- [ ] Kiểm tra header propagation qua adapter và ranh giới serialization.
- [ ] Giới hạn dữ liệu log/history, tránh ghi payload nhạy cảm và đánh giá chi phí khi chạy production.

Khi kết hợp Message History, Correlation ID, log có cấu trúc, IntegrationGraphServer và metric/tracing, ta có thể lần theo message từ điểm tiếp nhận tới endpoint cuối cùng, nhận diện nơi message đang chờ, phân biệt lỗi đồng bộ với lỗi bất đồng bộ và xác minh kết quả xử lý cùng transaction. Mỗi công cụ trả lời một phần khác nhau của câu hỏi; dùng chúng cùng nhau sẽ tạo được bức tranh runtime đáng tin cậy hơn.
