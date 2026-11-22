# Thiết kế command, event và response theo trách nhiệm nghiệp vụ

## 1. Vì sao phải phân biệt ba loại thông điệp?

Trong hệ thống hướng thông điệp, một message có thể yêu cầu một hành động, thông báo một sự việc đã xảy ra hoặc trả lời một yêu cầu trước đó. Ba mục đích này tạo ra ba hợp đồng khác nhau:

- **Command** diễn đạt ý định muốn một thành phần có thẩm quyền thực hiện một hành động nghiệp vụ.
- **Event** ghi nhận một sự kiện nghiệp vụ đã xảy ra để các thành phần quan tâm có thể phản ứng.
- **Response** trả kết quả cho bên đã gửi một request hoặc command.

Phân biệt đúng giúp xác định ai chịu trách nhiệm xử lý, ai được phép thay đổi trạng thái, ai cần nhận thông tin và mức độ phụ thuộc giữa các thành phần. Tên class chỉ là dấu hiệu; ý nghĩa nghiệp vụ và cách message được sử dụng mới quyết định loại hợp đồng.

Ví dụ trong nghiệp vụ đặt hàng:

1. Người dùng gửi command `PlaceOrder` để yêu cầu đặt hàng.
2. Thành phần quản lý đơn hàng kiểm tra quy tắc, lưu đơn hàng và phát event `OrderPlaced` khi việc đặt hàng đã được xác nhận.
3. Bên gửi nhận response `PlaceOrderResult` cho biết yêu cầu đã hoàn tất, bị từ chối hoặc mới được tiếp nhận.
4. Các thành phần khác nhận `OrderPlaced` để cập nhật tồn kho, tạo hóa đơn, gửi thông báo hoặc cập nhật báo cáo.

`PlaceOrder`, `OrderPlaced` và `PlaceOrderResult` có thể chứa một số dữ liệu giống nhau, nhưng chúng trả lời ba câu hỏi khác nhau: “hãy làm việc này”, “việc này đã xảy ra” và “yêu cầu của bạn có kết quả gì?”.

## 2. Command: yêu cầu một hành động nghiệp vụ

### 2.1. Bản chất và trách nhiệm

Command là một thông điệp mang tính mệnh lệnh. Người gửi muốn một thành phần có thẩm quyền thực hiện một hành động làm thay đổi trạng thái hoặc tạo ra một quyết định nghiệp vụ.

Ví dụ:

- `PlaceOrder`: đặt đơn hàng.
- `CancelOrder`: hủy đơn hàng.
- `ReserveInventory`: giữ hàng trong kho.
- `ChangeDeliveryAddress`: thay đổi địa chỉ giao hàng.
- `ApproveRefund`: phê duyệt hoàn tiền.

Tên command thường dùng động từ ở dạng mệnh lệnh. Command nên mô tả ý định nghiệp vụ, không mô tả thao tác lưu trữ như `UpdateOrderTable` hoặc `SetStatusTo2`.

Một command thường có các đặc điểm:

- Có một bên xử lý có thẩm quyền rõ ràng. Ví dụ, Order Service chịu trách nhiệm quyết định một đơn hàng có thể được đặt hay hủy.
- Có thể bị từ chối do dữ liệu không hợp lệ, thiếu quyền, trạng thái hiện tại hoặc quy tắc nghiệp vụ.
- Được kiểm tra trước khi thay đổi trạng thái.
- Có thể cần định danh duy nhất để chống xử lý lặp khi người gửi retry.
- Có thể trả response để người gửi biết kết quả hoặc trạng thái tiếp nhận.

Command là yêu cầu, không phải bằng chứng rằng hành động đã thành công. Việc gửi `PlaceOrder` không có nghĩa đơn hàng đã được đặt. Chỉ sau khi thành phần sở hữu nghiệp vụ xác nhận và commit thay đổi, hệ thống mới có thể công bố fact tương ứng như `OrderPlaced`.

### 2.2. Thiết kế payload command

Payload nên chứa dữ liệu cần để đánh giá và thực hiện ý định. Ví dụ:

~~~java
import java.util.List;
import java.util.UUID;

public record OrderLine(String productId, int quantity) {}

public record PlaceOrder(
    UUID commandId,
    UUID customerId,
    List<OrderLine> lines,
    String idempotencyKey
) {}
~~~

`commandId` định danh lần gửi command; `idempotencyKey` có thể được dùng để nhận diện những lần retry cùng một ý định. Hai trường có thể được gộp nếu hệ thống đã có một quy ước định danh duy nhất, nhưng ý nghĩa chống trùng phải được xác định rõ.

Các đoạn Java trong bài minh họa contract và cách tích hợp Spring. Các kiểu domain, service và cấu hình transport còn lại thuộc ứng dụng cụ thể, vì vậy snippet controller không phải một chương trình độc lập có thể chạy nguyên trạng.

Một command tốt nên:

1. Diễn đạt một ý định nghiệp vụ có thể hiểu độc lập.
2. Mang đủ dữ liệu để handler kiểm tra quyền và quy tắc nghiệp vụ.
3. Tránh gửi toàn bộ entity hoặc object persistence chỉ vì tiện serialize.
4. Không yêu cầu client tự quyết định các trường mà domain owner phải tính, như tổng tiền cuối cùng, trạng thái được phép hoặc quyền sở hữu.
5. Có quy tắc rõ ràng về retry, timeout và xử lý trùng.

Nếu cần kiểm tra phiên bản dữ liệu trước khi thay đổi, có thể gửi `expectedVersion` hoặc một điều kiện tương đương. Handler dùng điều kiện đó để phát hiện cập nhật đồng thời; không nên tin một trạng thái do client tự khai báo mà không kiểm tra ở domain owner.

### 2.3. Ai được xử lý command?

Một command nên được định tuyến tới thành phần chịu trách nhiệm cho hành vi được yêu cầu. Ví dụ, `ReserveInventory` phải được gửi tới thành phần sở hữu quy tắc tồn kho. Thành phần gọi không nên tự sửa dữ liệu kho bằng cách ghi trực tiếp vào database của service khác.

Một command có thể kích hoạt nhiều bước nội bộ hoặc một workflow, nhưng trách nhiệm quyết định vẫn phải rõ ràng. Nếu một quy trình dài cần nhiều service phối hợp, có thể dùng process manager hoặc saga để điều phối các command tiếp theo và theo dõi event kết quả.

## 3. Event: thông báo một sự thật nghiệp vụ đã xảy ra

### 3.1. Bản chất và trách nhiệm

Event là bản ghi về một fact đã xảy ra trong miền nghiệp vụ. Event không yêu cầu consumer thực hiện một hành động cụ thể và cũng không phải lời đề nghị thay đổi trạng thái.

Ví dụ:

- `OrderPlaced`: đơn hàng đã được đặt.
- `OrderCancelled`: đơn hàng đã bị hủy.
- `InventoryReserved`: hàng đã được giữ.
- `PaymentCaptured`: khoản thanh toán đã được thu.
- `AddressChanged`: địa chỉ đã được thay đổi.

Tên event thường dùng thì quá khứ hoặc diễn đạt một trạng thái đã xảy ra. Nếu command là `CancelOrder`, event tương ứng có thể là `OrderCancelled`.

Event thường có các đặc điểm:

- Được tạo bởi thành phần sở hữu sự thật nghiệp vụ.
- Chỉ được phát sau khi sự kiện tương ứng thực sự xảy ra.
- Được coi là bất biến sau khi công bố; nếu có sự kiện tiếp theo thì phát event mới.
- Có thể có nhiều consumer độc lập.
- Consumer có thể phản ứng khác nhau mà producer không cần biết từng consumer là ai.
- Có thể được lưu, phát lại hoặc xử lý bất đồng bộ tùy kiến trúc.

Ví dụ, sau khi Order Service phát `OrderPlaced`, Inventory Service có thể giữ hàng, Notification Service gửi email và Analytics Service cập nhật báo cáo. Producer không cần gọi trực tiếp từng service để yêu cầu chúng làm việc.

### 3.2. Event không phải command broadcast

Không nên phát event `PleaseReserveInventory` nếu ý nghĩa thực sự là yêu cầu Inventory Service giữ hàng. Đó là command và cần một handler chịu trách nhiệm quyết định có thể thực hiện hay không.

Event nên diễn đạt kết quả: `InventoryReserved` hoặc `InventoryReservationRejected`. Consumer có thể dùng fact đó để cập nhật trạng thái hoặc phát command khác nếu cần.

Sự khác biệt quan trọng là quyền quyết định:

- Với command, người gửi yêu cầu một hành động; bên nhận có thể chấp nhận hoặc từ chối.
- Với event, producer thông báo fact mà nó chịu trách nhiệm xác nhận; consumer quyết định phản ứng phù hợp trong phạm vi của mình.

### 3.3. Thiết kế payload event

Ví dụ event đơn hàng:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    UUID customerId,
    Instant occurredAt,
    long aggregateVersion,
    String correlationId
) {}
~~~

Các trường thường hữu ích:

| Trường | Mục đích |
|---|---|
| `eventId` | Định danh duy nhất để consumer nhận diện bản tin đã xử lý |
| `occurredAt` | Thời điểm fact xảy ra theo quy ước thời gian của hệ thống |
| `aggregateId` | Định danh đối tượng nghiệp vụ liên quan |
| `aggregateVersion` | Phiên bản hoặc thứ tự thay đổi của aggregate |
| `correlationId` | Liên kết event với request hoặc workflow ban đầu |
| `causationId` | Định danh command/event trực tiếp gây ra event hiện tại |
| `schemaVersion` | Phiên bản cấu trúc hợp đồng để hỗ trợ tiến hóa schema |

Không phải event nào cũng cần tất cả trường. Chỉ thêm metadata có ý nghĩa vận hành hoặc nghiệp vụ thực tế. Không đưa password, access token, dữ liệu bí mật hoặc toàn bộ hồ sơ khách hàng vào event chỉ để consumer khỏi phải truy vấn.

### 3.4. Event và tính bất biến

Sau khi `OrderPlaced` được công bố, không sửa event cũ thành `OrderCancelled`. Hủy đơn là một fact mới và phải được biểu diễn bằng event mới.

Nếu payload cũ thiếu thông tin, hãy cân nhắc bổ sung field tương thích, phát event phiên bản mới hoặc xây dựng projection phù hợp. Việc thay đổi ý nghĩa của một field đã phát hành có thể làm hỏng consumer cũ và dữ liệu lịch sử.

## 4. Response: kết quả dành cho người gửi request

### 4.1. Bản chất và trách nhiệm

Response là thông điệp trả lời một request hoặc command. Nó thường được liên kết với request gốc qua correlation ID, request ID hoặc cơ chế request-response của giao thức.

Ví dụ:

- `PlaceOrderResult`: kết quả của command đặt hàng.
- `GetOrderResult`: dữ liệu trả về từ truy vấn đơn hàng.
- `ReserveInventoryResult`: kết quả yêu cầu giữ hàng.

Response trả lời người gửi: request đã hoàn tất, bị từ chối hay mới được tiếp nhận? Nó có thể chứa dữ liệu mà người gọi cần để tiếp tục quy trình.

Ví dụ:

~~~java
import java.util.UUID;

public record PlaceOrderResult(
    UUID commandId,
    UUID orderId,
    Status status,
    String rejectionCode
) {
    public enum Status {
        ACCEPTED,
        COMPLETED,
        REJECTED
    }
}
~~~

Các trạng thái phải có ý nghĩa rõ ràng:

- `ACCEPTED`: hệ thống đã tiếp nhận trách nhiệm xử lý; công việc có thể vẫn đang chạy.
- `COMPLETED`: hành động nghiệp vụ đã hoàn tất theo cam kết của API.
- `REJECTED`: yêu cầu bị từ chối vì lý do nghiệp vụ hoặc dữ liệu.

Không dùng `ACCEPTED` như thể công việc đã hoàn tất. Nếu command được xử lý bất đồng bộ, response có thể trả `ACCEPTED` kèm command ID hoặc operation ID; kết quả cuối cùng được thông báo bằng event hoặc endpoint truy vấn trạng thái.

### 4.2. Response không phải event

`PlaceOrderResult` là response dành cho bên gọi `PlaceOrder`. `OrderPlaced` là fact dành cho bất kỳ consumer nào quan tâm tới việc đơn hàng đã được đặt.

Hai message có thể được tạo gần nhau nhưng không thay thế nhau:

- Response có quan hệ trực tiếp với request và thường được gửi về đúng bên gọi.
- Event có thể được gửi tới nhiều consumer, không cần bên gọi ban đầu còn kết nối.
- Response có thể nói `REJECTED`; event `OrderPlaced` chỉ được phát khi đơn hàng thật sự được đặt.
- Consumer của event không nên phụ thuộc vào response riêng của một client.

Một event không nên được dùng làm response chỉ vì cả hai cùng chứa `orderId`. Ngược lại, response cũng không thay thế event nếu các service khác cần biết sự thay đổi nghiệp vụ đã xảy ra.

### 4.3. Lỗi nghiệp vụ và lỗi kỹ thuật

Nên phân biệt:

- **Từ chối nghiệp vụ:** ví dụ khách hàng không đủ điều kiện hoặc đơn hàng không thể hủy ở trạng thái hiện tại. Có thể trả response có trạng thái `REJECTED` và mã lý do ổn định.
- **Lỗi xác thực/phân quyền:** người gọi không được phép thực hiện command. Xử lý theo cơ chế bảo mật và lỗi của transport/API.
- **Lỗi kỹ thuật tạm thời:** broker không khả dụng, timeout hoặc dependency lỗi. Có thể retry theo chính sách, nhưng phải đảm bảo idempotency.
- **Lỗi giao thức/serialization:** payload không thể giải mã hoặc message không đúng hợp đồng; cần log và xử lý theo cơ chế lỗi của transport.

Timeout không chứng minh command thất bại. Server có thể đã commit nhưng response bị mất trên đường truyền. Khi retry, hãy dùng cùng idempotency key hoặc truy vấn trạng thái theo command ID để tránh thực hiện hành động hai lần.

## 5. So sánh ba loại hợp đồng

| Tiêu chí | Command | Event | Response |
|---|---|---|---|
| Ý nghĩa | Yêu cầu hành động | Fact đã xảy ra | Kết quả của request |
| Cách đặt tên | Động từ mệnh lệnh | Sự kiện ở dạng đã xảy ra | Tên kết quả hoặc result |
| Người tạo | Caller hoặc thành phần điều phối | Thành phần sở hữu fact | Handler của request |
| Người nhận | Một owner/handler có thẩm quyền | Một hoặc nhiều consumer | Bên gọi request |
| Có thể bị từ chối? | Có | Không phải yêu cầu để từ chối | Có thể biểu diễn kết quả từ chối |
| Thay đổi trạng thái | Mục tiêu của command | Ghi nhận thay đổi đã xảy ra | Không tự nó biểu thị thay đổi |
| Quan hệ request | Là request/ý định | Độc lập với một caller cụ thể | Gắn với request gốc |
| Ví dụ | `PlaceOrder` | `OrderPlaced` | `PlaceOrderResult` |

Có thể dùng ba câu hỏi để phân loại một message:

1. Người gửi muốn bên nhận làm điều gì? Đó thường là command.
2. Message đang thông báo một fact nào đã xảy ra? Đó thường là event.
3. Message đang trả lời request nào và kết quả là gì? Đó thường là response.

Nếu chưa xác định được message thuộc loại nào, hãy làm rõ chủ thể sở hữu hành vi, ý nghĩa của message và bên cần nhận nó trước khi chọn tên class hoặc destination.

## 6. Thiết kế luồng nghiệp vụ hoàn chỉnh

### 6.1. Luồng đặt hàng đồng bộ

Giả sử ứng dụng xử lý đặt hàng trong một request-response:

~~~text
Client
  |
  | PlaceOrder (command)
  v
Order Service
  |-- kiểm tra dữ liệu và quyền
  |-- kiểm tra quy tắc nghiệp vụ
  |-- lưu đơn hàng
  |-- ghi OrderPlaced vào outbox cùng transaction
  |
  | PlaceOrderResult (response)
  v
Client

Outbox relay
  |
  | OrderPlaced (event)
  +------> Inventory Service
  +------> Notification Service
  +------> Analytics Service
~~~

Order Service là owner của quyết định đặt hàng. Nó chỉ trả `COMPLETED` sau khi transaction chứa thay đổi nghiệp vụ đã commit theo cam kết của ứng dụng. Event `OrderPlaced` được phát cho consumer qua outbox relay.

Response không cần chờ email hoặc báo cáo hoàn tất nếu các công việc đó là phản ứng bất đồng bộ độc lập. Nếu nghiệp vụ yêu cầu phải giữ hàng thành công trước khi xác nhận đặt đơn, workflow phải thể hiện điều kiện đó rõ ràng; không được phát `OrderPlaced` sớm rồi giả định mọi consumer sẽ hoàn thành.

### 6.2. Luồng xử lý bất đồng bộ

Với tác vụ kéo dài, caller có thể nhận response `ACCEPTED` cùng operation ID. Sau đó:

1. Handler ghi nhận command và trạng thái xử lý.
2. Worker xử lý workflow.
3. Khi có kết quả, service phát event như `OrderPlaced` hoặc `OrderPlacementFailed`.
4. Caller theo dõi bằng subscription, callback hoặc endpoint truy vấn trạng thái.

Cần quy định thời hạn lưu trạng thái, cách retry, cách tra cứu operation ID và event nào thể hiện kết quả cuối cùng. Không để client suy diễn rằng `ACCEPTED` có nghĩa là nghiệp vụ đã hoàn tất.

### 6.3. Khi nào nên dùng request-response, fire-and-forget hoặc event?

- Dùng request-response khi caller cần kết quả để tiếp tục và có thể chấp nhận độ gắn kết theo thời gian của request.
- Dùng command bất đồng bộ khi caller chỉ cần biết hệ thống đã tiếp nhận yêu cầu, còn kết quả sẽ đến sau.
- Dùng event khi một fact cần được phân phối cho các thành phần quan tâm và producer không cần chờ từng consumer trả lời.
- Dùng query khi mục đích chỉ là đọc dữ liệu; tránh đặt tên query như một command gây thay đổi trạng thái.

Không chọn event chỉ để tránh thiết kế response. Nếu caller cần biết command có được tiếp nhận hay không, hãy cung cấp acknowledgement hoặc response phù hợp.

## 7. Metadata, correlation và định tuyến message

### 7.1. Payload và envelope

Trong Spring Messaging, `Message<T>` là envelope chứa payload và headers:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<PlaceOrder> message = MessageBuilder
    .withPayload(command)
    .setHeader("correlationId", correlationId)
    .setHeader("tenantId", tenantId)
    .build();
~~~

Payload mô tả nội dung nghiệp vụ. Headers mang metadata phục vụ định tuyến, correlation, tracing, tenant hoặc thông tin vận hành. Đừng chuyển mọi field nghiệp vụ vào headers; consumer cần hợp đồng payload rõ ràng để hiểu message.

`MessageHeaders` là cấu trúc header của Spring. Hãy tạo message qua `MessageBuilder` thay vì tự thay đổi map header sau khi message đã được xây dựng. Việc một header có được truyền qua transport hay không phụ thuộc adapter và cấu hình giao thức; không giả định mọi header nội bộ đều tự động đi qua mạng.

### 7.2. Những ID cần phân biệt

| ID | Vai trò |
|---|---|
| `messageId` | Định danh message cụ thể |
| `commandId` | Định danh yêu cầu nghiệp vụ |
| `eventId` | Định danh fact được phát |
| `correlationId` | Liên kết các message thuộc cùng request hoặc workflow |
| `causationId` | Chỉ ra message trực tiếp gây ra message hiện tại |
| `aggregateId` | Xác định đối tượng nghiệp vụ liên quan |

Không cần tạo một ID mới cho mọi mục đích nếu một ID có thể đáp ứng nhiều vai trò, nhưng phải giữ semantics nhất quán. Ví dụ, retry của cùng command thường giữ idempotency key/command ID; mỗi event được phát là một message riêng có event ID riêng.

### 7.3. Quy tắc định tuyến

Định tuyến command đến owner có thẩm quyền. Định tuyến event đến topic hoặc subscription của consumer quan tâm. Response cần được liên kết với request và quay lại đúng caller hoặc destination được quy định.

Không dựa vào tên destination để thay thế xác thực và phân quyền. Header tenant, user hoặc role do client gửi có thể bị giả mạo; phải xác minh chúng bằng cơ chế bảo mật tin cậy ở phía server.

## 8. Áp dụng với Spring Framework Messaging

### 8.1. Message và MessageChannel

Spring Messaging cung cấp abstraction `Message<T>` để đóng gói payload và headers, cùng các abstraction channel để gửi message giữa các thành phần. Ví dụ ở mức API:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

boolean sent = commandChannel.send(
    MessageBuilder.withPayload(command)
        .setHeader("correlationId", correlationId)
        .build()
);
~~~

`sent` cho biết thao tác gửi vào channel có thành công theo contract của channel hay không. Nó không chứng minh command đã được xử lý hoặc nghiệp vụ đã commit. Kết quả nghiệp vụ cần được xác nhận qua response hoặc trạng thái/event phù hợp.

### 8.2. RSocket: command và response bằng request-response

Spring hỗ trợ định tuyến RSocket bằng `@MessageMapping`. Controller có thể nhận command và trả về `Mono` chứa response:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    private final OrderApplicationService orderService;

    public OrderRSocketController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.place")
    public Mono<PlaceOrderResult> place(PlaceOrder command) {
        return orderService.place(command);
    }
}
~~~

Caller gửi command và nhận response bằng `RSocketRequester`:

~~~java
Mono<PlaceOrderResult> result = requester
    .route("orders.place")
    .data(command)
    .retrieveMono(PlaceOrderResult.class);
~~~

Trong ví dụ này, `orders.place` là route của command. `PlaceOrderResult` là response tương ứng. Việc handler trả `Mono` giúp xử lý bất đồng bộ theo Reactor; nó không tự biến response thành event.

### 8.3. STOMP: tách reply và event topic

Với STOMP, client có thể gửi command tới destination do `@MessageMapping` quản lý. Nếu muốn trả response về user cụ thể, dùng destination reply phù hợp, ví dụ `@SendToUser`:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class OrderStompController {

    private final OrderApplicationService orderService;

    public OrderStompController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders.place")
    @SendToUser("/queue/order-results")
    public PlaceOrderResult place(PlaceOrder command) {
        return orderService.placeSynchronously(command);
    }
}
~~~

Khi có event cần phân phối tới nhiều subscriber, ứng dụng có thể dùng `SimpMessagingTemplate` để gửi event đến topic:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;

public class OrderEventPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(OrderPlaced event) {
        messagingTemplate.convertAndSend("/topic/orders", event);
    }
}
~~~

Ở đây `/queue/order-results` là destination response theo user, còn `/topic/orders` là destination phân phối event. Cấu hình broker, prefix application destination và bảo mật destination cần thống nhất với cấu hình STOMP của ứng dụng.

`@MessageMapping` là annotation của Spring Messaging; cách định tuyến và cơ chế response cụ thể phụ thuộc transport. RSocket route và STOMP destination không nên được coi là cùng một giao thức chỉ vì cùng sử dụng annotation.

### 8.4. Application event và message gửi qua broker

`ApplicationEventPublisher` phát event trong phạm vi Spring ApplicationContext. Nó hữu ích cho giao tiếp giữa các bean trong cùng ứng dụng, nhưng tự nó không phải cơ chế gửi event qua broker đến service khác.

Nếu event phải đi qua tiến trình hoặc service khác, hãy sử dụng integration/broker phù hợp hoặc một cơ chế phát message đáng tin cậy. Có thể dùng `@TransactionalEventListener` để phản ứng sau commit cho các event nội bộ; tuy nhiên, listener sau commit không tự cung cấp bảo đảm bền vững nếu tiến trình dừng trước khi publish ra broker.

## 9. Đảm bảo độ tin cậy khi gửi command và event

### 9.1. Idempotency và xử lý trùng

Message có thể được gửi lại do timeout, retry hoặc cơ chế giao nhận của broker. Vì vậy, handler command và consumer event cần có chiến lược idempotency.

Đối với command:

- Lưu idempotency key/command ID cùng kết quả xử lý.
- Nếu nhận lại cùng key, trả kết quả đã biết thay vì thực hiện thay đổi lần nữa.
- Xác định phạm vi duy nhất của key, ví dụ theo tenant và loại command.
- Không xóa dấu vết chống trùng trước khi hết khoảng thời gian retry được hỗ trợ.

Đối với event:

- Dùng event ID để nhận diện event đã xử lý.
- Ghi nhận việc xử lý và thay đổi dữ liệu consumer trong cùng transaction khi có thể.
- Nếu nhận event cũ hoặc trùng, không áp dụng side effect lần nữa.

Không giả định hệ thống phân tán luôn giao nhận đúng một lần. Thiết kế idempotent thường thực tế hơn việc dựa vào một lời hứa exactly-once xuyên suốt nhiều hệ thống.

### 9.2. Transactional outbox

Một lỗi phổ biến là cập nhật database thành công nhưng publish event thất bại, hoặc publish event thành công trong khi transaction nghiệp vụ rollback. Hai hành động này nằm ở hai hệ thống khác nhau nên không tự động nguyên tử.

Transactional outbox giải quyết bằng cách ghi dữ liệu nghiệp vụ và một bản ghi outbox trong cùng transaction database:

1. Handler kiểm tra command và cập nhật aggregate.
2. Trong cùng transaction, ghi event cần phát vào bảng outbox.
3. Sau commit, relay đọc outbox và publish lên broker.
4. Relay đánh dấu đã gửi hoặc tiếp tục retry khi lỗi.
5. Consumer xử lý idempotent vì relay có thể publish lại sau sự cố.

Outbox giúp không mất ý định phát event giữa commit nghiệp vụ và publish, nhưng vẫn cần quản lý retry, duplicate, thứ tự và dọn dẹp bản ghi đã gửi.

### 9.3. Thứ tự và phiên bản

Nếu các event của cùng một aggregate cần được xử lý theo thứ tự, hãy mang aggregate version hoặc sequence number và dùng partition key phù hợp với broker. Không mặc định có thứ tự toàn cục giữa các partition hoặc giữa các consumer.

Consumer có thể:

- Phát hiện event bị lặp bằng event ID.
- Phát hiện khoảng trống hoặc event đến sai thứ tự bằng aggregate version.
- Bỏ qua event cũ đã áp dụng.
- Retry hoặc lưu tạm event đến trước khi phiên bản trước đó được xử lý.

Chỉ yêu cầu thứ tự ở phạm vi nghiệp vụ thật sự cần; thứ tự toàn cục thường làm giảm khả năng mở rộng.

### 9.4. Tiến hóa hợp đồng

Command, event và response đều là API giữa các thành phần. Khi thay đổi:

- Ưu tiên thêm field tùy chọn có default hợp lý.
- Không đổi ý nghĩa field hiện hữu.
- Không tái sử dụng tên event cho một fact khác.
- Có schema version hoặc quy tắc tương thích rõ ràng.
- Kiểm tra consumer cũ trước khi phát hành thay đổi.
- Giữ khả năng đọc message lịch sử nếu hệ thống cần replay.

Event thường tồn tại lâu hơn một request-response ngắn hạn vì có thể được lưu và phát lại. Do đó, cần đặc biệt cẩn thận với schema event và dữ liệu nhạy cảm.

## 10. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Đặt command ở dạng quá khứ như `OrderPlaced` | Không rõ đây là yêu cầu hay fact | Dùng `PlaceOrder` cho command |
| Dùng event `PleaseSendEmail` để yêu cầu hành động | Consumer bị biến thành handler command không rõ quyền | Gửi command tới service có thẩm quyền hoặc phát fact thực tế |
| Dùng response như event cho tất cả service | Các consumer phụ thuộc vào vòng đời caller | Phát event độc lập sau khi fact xảy ra |
| Phát event trước khi transaction commit | Consumer nhìn thấy dữ liệu chưa được xác nhận | Dùng outbox hoặc cơ chế publish sau commit đáng tin cậy |
| Gọi command lặp tạo đơn hàng trùng | Retry gây side effect nhiều lần | Idempotency key và lưu kết quả xử lý |
| Trả `ACCEPTED` nhưng client hiểu là hoàn tất | Trạng thái workflow bị hiểu sai | Định nghĩa rõ accepted/completed/rejected |
| Nhét toàn bộ entity database vào payload | Contract gắn chặt với schema nội bộ | Thiết kế DTO theo nhu cầu nghiệp vụ |
| Đưa thông tin bí mật vào event | Tăng phạm vi lộ dữ liệu và khó thu hồi | Tối thiểu hóa payload, kiểm soát quyền truy cập |
| Dùng một event cho nhiều ý nghĩa khác nhau | Consumer không biết phải diễn giải ra sao | Mỗi event mô tả một fact rõ ràng |
| Coi việc gửi vào channel thành công là nghiệp vụ thành công | Caller nhận xác nhận sai | Phân biệt send acknowledgement và business response |

## 11. Quy trình thiết kế hợp đồng message

Khi bắt đầu một tính năng, có thể thực hiện theo trình tự:

1. **Mô tả hành vi nghiệp vụ:** người dùng hoặc service muốn điều gì xảy ra?
2. **Xác định owner:** thành phần nào chịu trách nhiệm quyết định và thay đổi trạng thái?
3. **Định nghĩa command:** tên theo ý định, payload cần thiết, quyền, validation, idempotency và quy tắc retry.
4. **Định nghĩa kết quả:** caller cần biết đã tiếp nhận, hoàn tất hay bị từ chối? Cần dữ liệu gì trong response?
5. **Định nghĩa event:** fact nào thực sự đã xảy ra và thành phần nào có thể quan tâm?
6. **Chọn thời điểm phát event:** event phải tương ứng với thay đổi đã commit hay với một mốc workflow cụ thể?
7. **Định nghĩa metadata:** message ID, correlation ID, causation ID, aggregate ID và version nào thực sự cần?
8. **Xác định giao thức và destination:** request-response, stream, queue hay topic; ai gửi, ai nhận và ai có quyền?
9. **Thiết kế lỗi và độ tin cậy:** duplicate, timeout, retry, outbox, thứ tự, dead-letter và replay.
10. **Kiểm tra tương thích:** consumer hiện tại có đọc được payload mới không? Có cần version hoặc migration không?

## 12. Kiểm thử hợp đồng và luồng xử lý

Nên kiểm tra cả semantics của message lẫn hành vi của handler:

- **Command unit test:** dữ liệu hợp lệ, dữ liệu sai, quyền không đủ, trạng thái không cho phép và command trùng.
- **Response test:** correlation đúng, status có ý nghĩa, rejection code ổn định và không trả `COMPLETED` trước khi commit.
- **Event test:** chỉ phát event khi fact xảy ra; payload và aggregate version đúng.
- **Outbox integration test:** transaction rollback không tạo event được phát; relay retry không làm mất event.
- **Consumer test:** xử lý duplicate an toàn, event sai version được xử lý theo chính sách và side effect không lặp.
- **Contract test:** producer và consumer tương thích khi thêm field hoặc đổi schema.
- **Transport integration test:** route/destination đúng, authentication/authorization đúng và lỗi được ánh xạ theo quy ước.

Khi debug, log message ID, command/event ID, correlation ID, aggregate ID và route/destination ở mức phù hợp. Tránh log toàn bộ payload nếu có dữ liệu cá nhân hoặc bí mật.

## 13. Tài liệu tham khảo

- [Spring Framework Reference — Messaging flow and abstractions](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): các abstraction `Message`, `MessageChannel`, `MessageHandler` và luồng message trong Spring.
- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): request-response, routing, annotated responders và `RSocketRequester`.
- [Spring Framework Reference — STOMP annotated controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): `@MessageMapping`, `@SendToUser` và xử lý giá trị trả về.
- [Spring Framework Javadoc — Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html): payload và headers của Spring Message.
- [Spring Framework Javadoc — MessageBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html): xây dựng message và thiết lập header.
- [Spring Framework Javadoc — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html): lắng nghe application event theo transaction phase.
