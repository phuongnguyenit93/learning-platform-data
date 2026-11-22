# Null reply, reply timeout và one-way handler trong Spring Integration

## Mục tiêu học tập

Trong runtime của **Spring Integration**, một message đi qua channel, được endpoint nhận và chuyển cho handler xử lý. Kết quả xử lý không phải lúc nào cũng là một message trả về. Bài học này giúp bạn:

- Phân biệt **null reply**, **reply timeout** và **one-way handler** dựa trên hợp đồng của từng endpoint.
- Hiểu đường đi của request/reply qua `replyChannel`, `outputChannel`, gateway và channel bất đồng bộ.
- Biết khi nào runtime dừng flow một cách hợp lệ, khi nào cần báo lỗi thiếu reply và khi nào bên gọi phải chờ đến timeout.
- Thiết kế API gateway, timeout, retry và xử lý lỗi để tránh mất dữ liệu, chờ vô hạn hoặc xử lý trùng.
- Chẩn đoán tình huống flow không trả kết quả qua log, metric, luồng thực thi và kiểm thử.

## 1. Ba khái niệm giống nhau ở bề ngoài nhưng khác nhau về bản chất

Giả sử ứng dụng gửi một yêu cầu kiểm tra đơn hàng qua Spring Integration. Người gọi không nhận được kết quả. Có ít nhất ba nguyên nhân khác nhau:

| Khái niệm | Điều đã xảy ra | Kỳ vọng của bên gọi | Cách hiểu đúng |
|---|---|---|---|
| **Null reply** | Một handler có khả năng tạo reply đã chạy nhưng trả về `null` | Có thể có hoặc không cần reply | Không có message trả về để gửi tiếp; mặc định có thể kết thúc flow tại handler |
| **Reply timeout** | Bên gọi đang đợi reply và hết thời hạn chờ | Cần một reply trong thời hạn xác định | Đây là kết quả của cơ chế **chờ**; không chứng minh handler chưa chạy hoặc đã thất bại |
| **One-way handler** | Endpoint được thiết kế chỉ nhận và xử lý message | Không cần reply | Hoàn tất thao tác gửi/tiếp nhận theo hợp đồng một chiều; không có reply để đợi |

Một null reply **có thể dẫn tới** reply timeout nếu bên gọi là request/reply gateway vẫn đang chờ. Tuy nhiên hai sự kiện không đồng nghĩa: null reply mô tả **kết quả xử lý tại handler**, còn timeout mô tả **trạng thái chờ tại bên nhận kết quả**. Một one-way handler có thể không trả gì mà vẫn hoàn toàn đúng hợp đồng.

Sơ đồ tổng quát:

~~~mermaid
flowchart TD
    A[Producer hoặc gateway gửi request] --> B[Input channel]
    B --> C[Consumer endpoint gọi handler]
    C --> D{Handler có tạo reply?}
    D -->|Có, kết quả khác null| E[Output channel hoặc replyChannel]
    D -->|Không, trả null| F{requiresReply?}
    F -->|false| G[Kết thúc nhánh tại handler]
    F -->|true| H[ReplyRequiredException]
    E --> I[Bên nhận lấy được reply]
    G -.-> J{Bên gọi có chờ reply?}
    J -->|Có| K[Đợi đến reply timeout nếu không có nguồn reply khác]
    J -->|Không| L[Hoàn thành tương tác one-way]
~~~

Sơ đồ này mô tả đường đi thường gặp ở **reply-producing handler** như service activator. Một `MessageHandler` thuần một chiều không có bước tạo reply ngay từ đầu.

## 2. Reply đi qua runtime như thế nào?

Trong mô hình message của Spring Integration, **channel** chuyển message và **consumer endpoint** gọi handler. Có hai nhóm quan trọng:

1. **Reply-producing handler**: có thể trả về payload hoặc `Message<?>`, ví dụ service activator hay outbound gateway. Khi trả kết quả hợp lệ, endpoint đóng gói hoặc chuyển tiếp reply tới channel phù hợp.
2. **One-way message handler**: nhận `Message<?>`, thực hiện hành động và không có giá trị trả về, chẳng hạn logging, ghi audit, gửi tới hệ thống ngoài bằng outbound channel adapter.

Đối với luồng request/reply, bên gọi thường cung cấp header **`replyChannel`** để endpoint biết nơi trả kết quả. Khi một endpoint được cấu hình **`outputChannel`** cụ thể, đầu ra của endpoint được đưa tới channel đó theo cấu hình. Kết quả là payload hoặc message **khác null** mới có thể đi tiếp; không tồn tại một “message có payload null” tự động được phát ra chỉ vì phương thức handler trả `null`.

Gateway là một điểm vào điển hình: nó biến lời gọi Java thành message, gửi vào `requestChannel` và, nếu phương thức cần kết quả, đợi reply trên kênh phản hồi tương ứng. `replyChannel` chỉ là địa chỉ trả lời; **sự hiện diện của header này không buộc mọi handler phải tạo reply**.

Ví dụ đường đi thành công:

~~~text
gateway.confirm("O-42")
  -> orders.request
  -> Service Activator: "APPROVED:O-42"
  -> replyChannel của gateway
  -> caller nhận "APPROVED:O-42"
~~~

Nếu service activator trả `null`, endpoint không gửi reply. Gateway đang chờ vẫn phải áp dụng hợp đồng timeout của chính nó.

## 3. Null reply: khi nào được phép, khi nào là lỗi?

### 3.1. Service activator có thể kết thúc flow bằng null

Với một service activator tạo reply, kết quả `null` thường có nghĩa là **không tạo output message**. Đây có thể là chủ ý, ví dụ không tiếp tục xử lý một sự kiện không phù hợp. Khi **`requiresReply=false`** (hành vi mặc định của nhiều reply-producing endpoint), việc không tạo reply không nhất thiết ném exception.

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
class OrderLookupHandler {

    @ServiceActivator(inputChannel = "orders.lookup")
    public String lookup(String orderId) {
        if (orderId.isBlank()) {
            return null; // Không có reply từ endpoint này
        }
        return "FOUND:" + orderId;
    }
}
~~~

Nếu phía trước là gateway trả về `String`, nhánh `null` không tự gửi chuỗi rỗng, `Optional.empty()` hay một message mang lỗi. Người gọi có thể chờ đến reply timeout. Vì vậy không nên dùng `null` một cách tùy tiện để biểu diễn kết quả nghiệp vụ “không tìm thấy” khi hợp đồng API yêu cầu trả lời rõ ràng.

### 3.2. Bắt buộc phải có reply với requiresReply

Nếu handler **phải** cung cấp reply để flow hoạt động đúng, cấu hình `requiresReply=true`. Khi handler trả `null`, Spring Integration có thể phát sinh **`ReplyRequiredException`** ở endpoint đó, giúp lỗi được phát hiện gần nguyên nhân thay vì chỉ biểu hiện như timeout về sau.

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
class StrictOrderLookup {

    @ServiceActivator(inputChannel = "orders.strictLookup",
                      requiresReply = "true")
    public String lookup(String orderId) {
        return orderId.isBlank() ? null : "FOUND:" + orderId;
    }
}
~~~

Hành vi lỗi được chuyển đến đâu phụ thuộc kênh và ranh giới thực thi: với `DirectChannel`, exception có thể đi thẳng về thread gửi; khi thực thi bất đồng bộ hoặc qua poller, exception có thể đi qua cơ chế xử lý lỗi/`errorChannel` được cấu hình. **`requiresReply` không tự động biến một null thành reply hợp lệ.**

### 3.3. Không phải endpoint nào cũng cho phép null giống nhau

Không nên áp dụng quy tắc “trả null là dừng flow” cho mọi loại endpoint:

| Endpoint / thành phần | Ý nghĩa của không có kết quả |
|---|---|
| Service activator trả kết quả | Có thể không tạo reply; dùng `requiresReply` khi bắt buộc phải trả |
| `MessageHandler` thuần / outbound channel adapter | Không có giá trị trả về theo hợp đồng; đây là xử lý một chiều |
| Filter | Loại bỏ message theo predicate; có thể đặt `discardChannel` hoặc ném lỗi khi từ chối |
| Transformer | Có trách nhiệm tạo message đã biến đổi; trả `null` thường bị xem là lỗi chuyển đổi, không phải cơ chế lọc thông thường |
| Router | Quyết định kênh đích; trường hợp không tìm thấy đích cần được xử lý theo cấu hình router, không suy ra từ null reply của service activator |

Nếu mục tiêu là **lọc** message, sử dụng filter với quy tắc loại bỏ minh bạch. Nếu muốn trả kết quả nghiệp vụ “không tồn tại”, hãy trả một response rõ nghĩa. Nếu một handler bắt buộc phải tạo kết quả kỹ thuật, bật `requiresReply`.

## 4. Reply timeout: hạn chờ của bên gọi

Với request/reply gateway, **`replyTimeout`** là thời gian tối đa gateway đợi một reply trong giai đoạn nhận kết quả. Khi hết hạn mà chưa có reply, gateway hoàn tất việc chờ theo cấu hình của nó; có cấu hình trả `null`, có trường hợp phát sinh exception/báo lỗi timeout. Hãy kiểm tra phiên bản và hợp đồng gateway đang dùng, đồng thời xử lý cả trường hợp không có dữ liệu trả về.

Điều quan trọng là **reply timeout không có nghĩa handler đã bị hủy**, transaction đã rollback hoặc yêu cầu bên ngoài chắc chắn thất bại. Handler có thể đang chạy trên thread khác và gửi reply muộn.

### 4.1. Ví dụ gateway với thời hạn chờ minh bạch

Trong một ứng dụng đã bật Spring Integration, khai báo cổng Java:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface OrderPort {

    @Gateway(requestChannel = "orders.request", replyTimeout = "800")
    String confirm(String orderId);

    @Gateway(requestChannel = "audit.events")
    void recordAudit(String event);
}
~~~

Flow minh họa ở hai file cấu hình/kiểu riêng biệt:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
class OrderFlows {

    @Bean
    IntegrationFlow requestReplyFlow() {
        return IntegrationFlow.from("orders.request")
            .handle((payload, headers) -> {
                String id = (String) payload;
                return id.isBlank() ? null : "CONFIRMED:" + id;
            })
            .get();
    }

    @Bean
    IntegrationFlow auditFlow(AuditSink sink) {
        return IntegrationFlow.from("audit.events")
            .handle((MessageHandler) message ->
                sink.record((String) message.getPayload()))
            .get();
    }
}

interface AuditSink {
    void record(String event);
}
~~~

Đây là ví dụ **hai hợp đồng khác nhau**: `confirm` là request/reply; `recordAudit` là one-way. Với `confirm("")`, handler trả `null`, không tạo reply và gateway có thể phải chờ hết `800 ms` ở giai đoạn nhận reply. Hãy khai báo kênh và quản lý lỗi tương ứng khi đưa vào ứng dụng thật.

### 4.2. Phân biệt request timeout, reply timeout và thời gian handler chạy

| Tham số / khoảng thời gian | Được tính tại đâu? | Mục đích |
|---|---|---|
| **Request/send timeout** | Khi sender cố gửi message đến channel có khả năng chờ, ví dụ queue bị đầy | Giới hạn thời gian cố gửi/đưa message vào channel |
| **Reply timeout** | Khi gateway hoặc consumer chờ message phản hồi | Giới hạn thời gian nhận kết quả |
| **Thời gian chạy handler** | Trong thread đang gọi handler | Thời lượng xử lý nghiệp vụ; không mặc nhiên bị hai timeout trên ngắt |
| **Timeout của hệ thống ngoài** | HTTP client, JDBC, broker, RPC... | Giới hạn riêng cho I/O bên ngoài |

**Bẫy quan trọng với `DirectChannel`:** người gửi và handler thường chạy cùng thread. Lệnh `send` có thể chỉ quay về sau khi handler hoàn tất; khi đó đặt `replyTimeout=800` **không bảo đảm tổng thời gian gọi gateway luôn dưới 800 ms**. Nếu cần deadline end-to-end, phải kiểm soát cả thời gian xử lý, thời gian gửi và timeout của I/O, hoặc thiết kế ranh giới bất đồng bộ phù hợp.

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant C as Request channel
    participant W as Worker
    G->>C: send(request)
    C->>W: dispatch
    Note over W: Có thể xử lý trên thread khác
    C-->>G: send hoàn tất
    G->>G: chờ reply tối đa replyTimeout
    G-->>G: hết hạn chờ
    Note over W: Worker có thể vẫn đang chạy
    W-->>G: reply đến muộn (không được bảo đảm sẽ được nhận)
~~~

Sơ đồ thời gian trên áp dụng cho kịch bản **dispatch bất đồng bộ** (ví dụ `ExecutorChannel` hoặc công việc qua poller). Với `DirectChannel`, bước xử lý thường nằm trong lời gọi `send`, trước khi gateway bước vào pha chờ nhận reply.

### 4.3. Vì sao gateway timeout dù handler “đã chạy xong”?

Một số nguyên nhân phổ biến:

- Handler trả `null` hoặc một thành phần filter đã loại bỏ message mà không có reply nào khác.
- Handler đã gửi reply vào `outputChannel` khác nơi gateway đang đợi; hoặc flow bị rẽ nhánh sang sink một chiều.
- Reply đi qua queue/poller nhưng poller không chạy, chậm hoặc bị nghẽn.
- Executor bị quá tải, hàng đợi dài, thread bị block ở I/O, gây trễ vượt deadline.
- Flow có aggregator/resequencer đang chờ đủ nhóm theo correlation, nên chưa phát ra reply.
- Một dịch vụ ngoài đang treo, retry quá lâu hoặc trả lỗi trên thread bất đồng bộ nhưng chưa có đường chuyển lỗi đúng.

Không kết luận “mất message” chỉ từ một sự kiện reply timeout. Cần truy theo message ID, các header định tuyến, điểm bắt đầu/kết thúc xử lý và tình trạng channel/poller.

## 5. One-way handler: chủ ý không tạo reply

Một `MessageHandler` một chiều có chữ ký xử lý dạng:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;

class AuditHandler implements MessageHandler {
    @Override
    public void handleMessage(Message<?> message) {
        // Ghi audit, phát sự kiện, gửi tới hệ thống khác...
        // Không trả về payload hay Message để làm reply.
    }
}
~~~

Các ví dụ thực tế gồm ghi log nghiệp vụ, outbound channel adapter gửi Kafka/JMS, lưu một bản ghi audit hoặc phát notification. Nếu nghiệp vụ cần xác nhận từ bên nhận ngoài, phải chọn **outbound gateway** hoặc thiết kế một flow xác nhận độc lập; việc một adapter đã gọi phương thức gửi không đồng nghĩa hệ thống đích đã hoàn tất xử lý.

Gateway Java trả kiểu `void` (như `recordAudit` ở trên) phù hợp cho tương tác **fire-and-forget về mặt reply**. Tuy nhiên “không đợi reply” **không đồng nghĩa gọi luôn không block**:

- Qua `DirectChannel`, việc gửi message có thể trực tiếp gọi handler và chờ nó xử lý xong trong cùng thread.
- Qua `ExecutorChannel` hay queue, bên gọi thường tách khỏi phần xử lý sau khi message được tiếp nhận, nhưng vẫn có thể gặp lỗi gửi, từ chối task hoặc timeout do tắc nghẽn.
- Exception ở đường đồng bộ vẫn có thể quay về người gọi; lỗi ở đường bất đồng bộ cần chính sách xử lý và kênh lỗi riêng.

Đừng sử dụng một gateway yêu cầu `String` hoặc `OrderResult` để gọi vào nhánh kết thúc ở one-way outbound adapter rồi kỳ vọng reply tự xuất hiện. Hãy đồng bộ **hợp đồng gateway** với **năng lực endpoint**.

### 5.1. Null reply khác NullChannel

`null` do handler trả về nghĩa là **không có message nào được tạo**. Ngược lại, **`nullChannel`** là một message channel đặc biệt có thể **nhận một message có thật rồi bỏ qua**. Ví dụ, chuyển một bản sao audit tới `nullChannel` là thao tác định tuyến; trả `null` từ service activator là quyết định không tạo kết quả ở endpoint. Hai cơ chế phục vụ mục đích khác nhau.

## 6. Lựa chọn thiết kế theo hợp đồng nghiệp vụ

| Nhu cầu | Thiết kế thích hợp | Điều cần chú ý |
|---|---|---|
| Cần kết quả ngay cho người gọi | Request/reply gateway + handler tạo reply | Cấu hình reply timeout và quy ước kết quả lỗi/không tìm thấy |
| Không có reply là lỗi lập trình | Reply-producing handler + `requiresReply=true` | Theo dõi `ReplyRequiredException`; phân biệt với lỗi nghiệp vụ |
| Muốn bỏ qua message theo điều kiện | Filter + discard flow/channel khi cần | Dễ truy vết hơn việc ẩn ý nghĩa “bỏ qua” trong giá trị `null` |
| Chỉ cần gửi sự kiện/lưu audit | One-way gateway hoặc channel adapter | Quy định rõ “đã tiếp nhận” khác “đã xử lý thành công ở đích” |
| Xử lý lâu, không muốn chặn request thread | Executor/queue và mô hình kết quả bất đồng bộ | Quản lý queue, error channel, correlation, deadline và retry |
| Cần phản hồi “không tìm thấy” | Trả response có trạng thái rõ nghĩa | Không nhầm `null` với timeout hoặc lỗi kỹ thuật |

Ví dụ hợp đồng phản hồi rõ nghĩa, thay vì dùng null:

~~~java
record LookupResult(boolean found, String orderId, String reason) {}

@ServiceActivator(inputChannel = "orders.lookupExplicit",
                  requiresReply = "true")
public LookupResult lookupExplicit(String id) {
    if (id.isBlank()) {
        return new LookupResult(false, id, "EMPTY_ID");
    }
    return new LookupResult(true, id, "OK");
}
~~~

Khi đó gateway có thể nhận phản hồi nhất quán, metrics tách được **không tìm thấy** khỏi **không nhận được reply**, và bên gọi không cần đợi timeout để suy đoán kết quả nghiệp vụ.

## 7. Retry, transaction và error channel: các ranh giới dễ hiểu nhầm

### Retry

Retry advice quanh handler thường được kích hoạt bởi **exception** trong phạm vi được advice bao bọc. Một handler trả `null` hợp lệ với `requiresReply=false` không mặc nhiên kích hoạt retry. Nếu bật `requiresReply=true`, lỗi thiếu reply có thể được retry khi advice bao quanh đúng endpoint. Cần giới hạn số lần thử và bảo đảm idempotency cho side effect như ghi DB, phát sự kiện hoặc thanh toán.

Reply timeout ở gateway cũng không tự động làm handler bị retry hay hủy bỏ. Nếu client tự gửi lại vì đã timeout, yêu cầu đầu tiên có thể vẫn xử lý thành công: dùng **business key/idempotency key** để tránh xử lý hai lần.

### Transaction

Transaction gắn với **ranh giới thread và điểm xử lý được quản lý transaction**. Với một flow đồng bộ, exception trong cùng ranh giới có thể khiến transaction rollback theo cấu hình. Với `ExecutorChannel`, queue hoặc poller, phần xử lý tiếp theo thường chạy trên thread/transaction khác. Gateway hết hạn chờ reply không đủ để suy ra transaction ở worker đã rollback.

### Error channel

`errorChannel` phục vụ truyền **ErrorMessage** khi hạ tầng/flow chuyển lỗi vào kênh lỗi. Nó không phải “kênh dành cho mọi handler trả null”. Trong đường đồng bộ, exception có thể propagate trực tiếp về sender; trong đường bất đồng bộ, lỗi thường được xử lý bởi error handler và error channel phù hợp. Cần kiểm tra cấu hình của endpoint, poller, executor và gateway để biết lỗi thực sự đến đâu.

Với hệ thống cần trả lỗi về người gọi, nên xác định trước liệu lỗi sẽ được ném như exception, được ánh xạ thành reply nghiệp vụ, hay được công bố sang luồng bù trừ riêng. Tránh để một gateway chờ reply trong khi error flow đã nuốt exception và không phát phản hồi.

## 8. Chẩn đoán flow không trả lời

Khi gặp hiện tượng “request đã gửi nhưng không có kết quả”, thực hiện theo thứ tự sau:

1. **Xác nhận hợp đồng:** method gateway trả `void` hay một kiểu kết quả? Endpoint cuối là service activator/outbound gateway hay one-way handler?
2. **Xác định nơi có reply:** kiểm tra `replyChannel`, `outputChannel` và các nhánh route; nơi nào thực sự tạo message đầu ra?
3. **Kiểm tra null:** đặt log/metric ở biên handler để phân biệt “handler đã hoàn tất và trả null” với “handler chưa chạy”. Không ghi payload nhạy cảm vào log.
4. **Theo dõi thời gian:** ghi nhận lúc send, lúc handler bắt đầu/kết thúc và lúc gateway hết hạn chờ; đo `requestTimeout` và `replyTimeout` độc lập.
5. **Kiểm tra lịch chạy:** xem thread name, poller, độ sâu queue, executor active count/queue size, số task bị từ chối, backlog của aggregator.
6. **Kiểm tra lỗi:** tìm exception trực tiếp trên thread đồng bộ và `ErrorMessage` trên error flow bất đồng bộ; chú ý `ReplyRequiredException`, exception I/O và lỗi gửi channel.
7. **Kiểm tra reply đến muộn:** tìm theo request ID/correlation key và timestamp; đừng giả định việc timeout đồng nghĩa không có side effect.

Ví dụ bản ghi quan sát có ích:

~~~text
requestId=REQ-88  event=sent              thread=http-12       t=0ms
requestId=REQ-88  event=handler-start     thread=worker-3      t=15ms
requestId=REQ-88  event=gateway-timeout   thread=http-12       t=815ms
requestId=REQ-88  event=handler-complete  thread=worker-3      t=1240ms
requestId=REQ-88  event=reply-attempt     thread=worker-3      t=1241ms
~~~

Ở ví dụ này, timeout đã xảy ra **trước khi** worker kết thúc. Việc reply muộn được phát hay được bên gọi nhận còn tùy channel và vòng đời của kênh reply tạm thời. Cần theo dõi cả nỗ lực gửi reply lẫn kết quả nhận ở phía gọi.

### Phân biệt triệu chứng nhanh

| Triệu chứng | Hướng điều tra đầu tiên |
|---|---|
Gateway luôn đợi đúng thời hạn, handler kết thúc rất sớm | Handler trả null, filter loại message, reply đi sai channel |
Handler chưa bắt đầu mà gateway đã hết hạn | Queue backlog, poller, executor, route/channel không có consumer |
Gateway gọi lâu hơn `replyTimeout` dù dùng `DirectChannel` | Handler đang chạy đồng bộ trong `send`; timeout chỉ áp dụng ở pha chờ reply |
Chỉ xảy ra dưới tải cao | Bão hòa thread pool, queue, I/O, contention, batch/correlation chưa hoàn tất |
Lỗi rõ ràng khi bật `requiresReply=true` | Truy nhánh trả null, quy tắc rẽ nhánh và hợp đồng handler |
Người gọi timeout nhưng DB vẫn có bản ghi | Worker đã commit sau timeout; kiểm tra idempotency và retry từ phía client |

## 9. Thực hành kiểm chứng

Thiết lập ba kênh thử nghiệm riêng biệt để tránh hai consumer cạnh tranh trên cùng input channel:

**Tình huống A — Null reply được phép.** Gateway có method trả `String`, `replyTimeout` hữu hạn; service activator trả `null` và không bật `requiresReply`. Xác nhận endpoint không phát output message, đo thời điểm gateway kết thúc chờ và quan sát cách gateway phản ánh việc thiếu reply trong cấu hình đang dùng.

**Tình huống B — Reply bắt buộc.** Thay bằng endpoint `requiresReply=true` và vẫn trả `null`. Xác nhận exception thiếu reply xảy ra tại endpoint. Thử một lần qua `DirectChannel` và một lần qua `ExecutorChannel` để quan sát khác biệt của đường lỗi.

**Tình huống C — One-way.** Gateway trả `void`, endpoint sử dụng `MessageHandler` ghi một bản ghi audit. Kiểm tra lời gọi không đợi phản hồi nghiệp vụ. Sau đó thay `DirectChannel` bằng dispatch bất đồng bộ và so sánh thời gian caller trở về, thời điểm audit hoàn tất, cũng như cách xử lý exception.

**Tình huống D — Reply muộn.** Dùng executor để handler ngủ lâu hơn reply timeout rồi mới trả kết quả. Kiểm tra gateway hết hạn chờ trong khi worker vẫn xử lý; sau đó thử cơ chế idempotency nếu client gửi lại cùng request ID.

Khi viết test, nên assert cả **kết quả bên gọi**, **số lần handler thực thi**, **số message thực sự phát ra**, **exception/error flow**, và **thời điểm side effect**. Chỉ assert “gateway trả null” sẽ bỏ sót trường hợp message đã được xử lý nhưng reply bị trễ.

## 10. Ghi nhớ

- **Null reply** là trạng thái không tạo message trả về ở một reply-producing handler; nó có thể hợp lệ hoặc bị báo lỗi bởi `requiresReply`.
- **Reply timeout** xảy ra tại nơi đang **chờ kết quả**; timeout không xác nhận rằng handler đã dừng, transaction rollback hay thao tác bên ngoài thất bại.
- **One-way handler** không có hợp đồng tạo reply; dùng method gateway trả `void` hoặc kiến trúc sự kiện phù hợp, và vẫn tính đến khả năng send bị block/lỗi.
- `requestTimeout`, `replyTimeout` và timeout của I/O bên ngoài giải quyết **những khoảng chờ khác nhau**.
- Để runtime dễ vận hành, hãy thiết kế kết quả nghiệp vụ tường minh, đặt deadline hợp lý, đo queue/thread/poller, định tuyến lỗi rõ ràng và bảo đảm idempotency khi có retry.
