# Quan hệ giữa thông điệp, lệnh, sự kiện và yêu cầu

> Mục tiêu: phân biệt lớp vỏ thông điệp với ý nghĩa nghiệp vụ mà nó mang theo; nhận biết command, event, request và reply; áp dụng các khái niệm này khi thiết kế luồng giao tiếp bằng Spring Messaging.

## 1. Bốn khái niệm không nằm cùng một cấp

Trong thiết kế hệ thống, các từ *message*, *command*, *event* và *request* thường xuất hiện cạnh nhau, nhưng chúng không phải bốn kiểu dữ liệu ngang hàng.

- **Message (thông điệp)** là vật mang dữ liệu qua một ranh giới giao tiếp. Nó có payload và có thể có headers để mô tả metadata như loại nội dung, correlation ID, nguồn gửi hoặc thông tin định tuyến.
- **Command (lệnh)** mô tả ý định yêu cầu một thành phần thực hiện hành động, thường làm thay đổi trạng thái.
- **Event (sự kiện)** mô tả một sự việc đã xảy ra và có ý nghĩa đối với các thành phần khác.
- **Request (yêu cầu)** là lời hỏi hoặc đề nghị cần một thành phần khác phản hồi. Request–reply là một kiểu tương tác trong đó bên gửi mong đợi một câu trả lời tương ứng.

Vì vậy, một command, event hoặc request có thể được đóng gói bên trong một message. `Message<T>` mô tả cách mang payload và metadata; kiểu payload và hợp đồng giao tiếp mới thể hiện message đó có ý nghĩa là command, event hay request.

| Khái niệm | Câu hỏi nó trả lời | Ý nghĩa điển hình | Phản hồi mong đợi |
|---|---|---|---|
| Message | Dữ liệu được đóng gói và chuyển đi như thế nào? | Payload cùng headers | Tùy ý nghĩa của payload và giao thức |
| Command | Muốn bên nhận thực hiện việc gì? | Ý định thực hiện một hành động | Có thể có xác nhận, kết quả hoặc lỗi |
| Event | Việc gì đã xảy ra? | Một sự thật nghiệp vụ đã xảy ra | Thường không cần kết quả nghiệp vụ trực tiếp |
| Request | Đang hỏi hoặc đề nghị điều gì? | Yêu cầu thông tin hay một kết quả | Thường mong có reply trong mô hình request–reply |

Một điểm dễ nhầm là “request” đôi khi được dùng theo nghĩa rất rộng, bao gồm cả yêu cầu thực hiện hành động. Khi phân loại message trong kiến trúc hướng thông điệp, nên tách rõ: yêu cầu thay đổi trạng thái là command; yêu cầu đọc thông tin là query; request–reply mô tả cách bên gửi chờ kết quả. HTTP request cũng là một request ở cấp giao thức, nhưng không vì vậy mà mọi HTTP request đều là message theo nghĩa message broker.

## 2. Message là lớp vỏ mang payload và headers

Trong Spring Messaging, `org.springframework.messaging.Message<T>` là abstraction biểu diễn một message. Nó cung cấp hai phần chính:

- **Payload:** dữ liệu chính mà consumer cần xử lý. Payload có thể là một object Java, chuỗi, byte array hoặc kiểu dữ liệu khác tùy ứng dụng.
- **Headers:** metadata đi kèm payload, chẳng hạn content type, ID, timestamp, correlation ID, reply channel hoặc header do ứng dụng tự định nghĩa.

`MessageHeaders` cung cấp các header chuẩn; `MessageBuilder` giúp tạo message mà không phải tự cài đặt interface `Message<T>`. Ví dụ:

```java
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record ReserveInventory(String orderId, String sku, int quantity) {}
record OrderCreated(String orderId, Instant occurredAt) {}
record GetOrderStatus(String orderId) {}

public class MessageIntentDemo {
    public static void main(String[] args) {
        String correlationId = "corr-001";

        Message<ReserveInventory> commandMessage = MessageBuilder
                .withPayload(new ReserveInventory("ORD-100", "BOOK-01", 2))
                .setHeader("messageKind", "command")
                .build();

        Message<OrderCreated> eventMessage = MessageBuilder
                .withPayload(new OrderCreated("ORD-100",
                        Instant.parse("2026-11-07T00:00:00Z")))
                .setHeader("messageKind", "event")
                .build();

        Message<GetOrderStatus> requestMessage = MessageBuilder
                .withPayload(new GetOrderStatus("ORD-100"))
                .setHeader("messageKind", "request")
                .setHeader("correlationId", correlationId)
                .setHeader("replyTo", "orders.status.replies")
                .build();

        System.out.println(commandMessage.getPayload().getClass().getSimpleName());
        System.out.println(eventMessage.getPayload().getClass().getSimpleName());
        System.out.println(requestMessage.getPayload().getClass().getSimpleName());
        System.out.println(requestMessage.getHeaders().get("correlationId"));
        System.out.println(requestMessage.getHeaders().get("replyTo"));
    }
}
```

Đây là đoạn mã minh họa cách tạo message, không phải một ứng dụng độc lập hoàn chỉnh. Header `correlationId` là metadata do ứng dụng tự quy ước để liên kết request với reply; Spring Messaging không định nghĩa hằng `MessageHeaders.CORRELATION_ID`. Header `replyTo` trong ví dụ là metadata do ứng dụng quy ước; khi tích hợp broker, cách biểu diễn địa chỉ trả lời phải phù hợp với adapter và broker đang dùng. Không nên giả định một header Java bất kỳ sẽ tự động trở thành thuộc tính định tuyến của mọi broker.

Ba biến trên đều có kiểu ngoài là `Message<T>`, nhưng payload của chúng thể hiện ba ý nghĩa khác nhau. Việc đặt `messageKind` chỉ giúp minh họa; trong hệ thống thực tế, kiểu payload, tên destination và tài liệu hợp đồng thường đã thể hiện ý nghĩa. Không nên dựa duy nhất vào một chuỗi header để quyết định logic nghiệp vụ.

## 3. Command: yêu cầu thực hiện một hành động

Command diễn đạt điều bên gửi muốn hệ thống làm. Tên command thường dùng động từ mệnh lệnh hoặc cụm từ hành động, ví dụ `ReserveInventory`, `CancelOrder`, `ApprovePayment`.

Đặc điểm thường gặp:

- **Hướng đến một nơi chịu trách nhiệm:** một command thường được định tuyến đến một handler hoặc một nhóm consumer cạnh tranh để một consumer xử lý. Gửi cùng một command cho nhiều handler độc lập có thể khiến hành động bị thực hiện nhiều lần.
- **Có thể làm thay đổi trạng thái:** handler có thể ghi database, giữ hàng, tạo thanh toán hoặc cập nhật quy trình.
- **Có thể bị từ chối:** dữ liệu không hợp lệ, trạng thái nghiệp vụ không cho phép hoặc tài nguyên không còn sẵn có đều có thể khiến command thất bại.
- **Có thể có kết quả:** hệ thống có thể trả xác nhận đã tiếp nhận, kết quả hoàn tất hoặc lỗi. Tuy nhiên, command không mặc nhiên yêu cầu caller phải chờ kết quả cuối cùng.

Ví dụ `ReserveInventory` yêu cầu dịch vụ kho giữ hai sản phẩm cho một đơn hàng. Consumer cần kiểm tra số lượng, trạng thái đơn và quy tắc giữ hàng trước khi cập nhật dữ liệu.

Command nên mô tả ý định, không mô tả sự thật đã xảy ra. `CancelOrder` là command vì nó yêu cầu hủy đơn; `OrderCancelled` là event vì nó thông báo đơn đã được hủy thành công. Không phát event `OrderCancelled` chỉ vì có người vừa gửi yêu cầu hủy.

Vì command có thể được gửi lại sau timeout hoặc redelivery, handler nên có cơ chế idempotency. Ví dụ, dùng command ID hoặc business key ổn định để nhận ra lần xử lý lặp, đồng thời bảo đảm việc kiểm tra trùng và cập nhật trạng thái nằm trong ranh giới transaction phù hợp.

## 4. Event: thông báo một sự thật đã xảy ra

Event mô tả một sự kiện nghiệp vụ đã hoàn tất hoặc đã được ghi nhận. Tên event thường dùng thì quá khứ, ví dụ `OrderCreated`, `PaymentAuthorized`, `InventoryReserved`.

Đặc điểm thường gặp:

- **Mô tả sự thật:** event nói điều gì đã xảy ra, không ra lệnh cho consumer phải làm một hành động cụ thể.
- **Thường bất biến về ý nghĩa:** sau khi phát hành, không sửa event cũ để thay đổi lịch sử. Nếu có thông tin mới, phát event mới hoặc một phiên bản sự kiện phù hợp.
- **Có thể có nhiều subscriber:** thanh toán, email, phân tích và vận chuyển có thể cùng quan tâm đến `OrderCreated` nhưng thực hiện công việc riêng.
- **Producer ít phụ thuộc consumer:** thành phần phát event không cần biết mọi subscriber đang tồn tại hoặc cách chúng xử lý.
- **Không mặc nhiên có reply nghiệp vụ:** broker có thể xác nhận việc nhận/giao message, nhưng đó không có nghĩa mọi subscriber đã hoàn thành công việc.

Ví dụ: sau khi đơn hàng được tạo và lưu thành công, hệ thống phát `OrderCreated`. Consumer thanh toán có thể bắt đầu ủy quyền thanh toán; consumer thông báo có thể gửi email; consumer phân tích có thể cập nhật chỉ số. Những consumer này phản ứng độc lập với cùng một sự thật.

Một event tốt thường chứa định danh của đối tượng nghiệp vụ, thời điểm xảy ra, định danh event và các dữ liệu cần thiết để consumer hiểu sự kiện. Tránh đưa dữ liệu nhạy cảm không cần thiết vào payload. Nếu payload có thể thay đổi theo thời gian, cần quy tắc versioning và tương thích ngược.

### Event khác command ở điểm nào?

| Command | Event |
|---|---|
| “Hãy giữ hàng cho đơn ORD-100” | “Hàng cho đơn ORD-100 đã được giữ” |
| Thể hiện ý định cần xử lý | Thể hiện sự thật đã xảy ra |
| Thường hướng đến một handler chịu trách nhiệm | Có thể được nhiều subscriber quan tâm |
| Có thể bị từ chối trước khi hoàn tất | Không nên được phát hành như sự thật nếu việc đó chưa xảy ra |
| Tên thường mang nghĩa mệnh lệnh | Tên thường ở dạng quá khứ |

## 5. Request: hỏi hoặc đề nghị và mong đợi câu trả lời

Request là thông điệp hoặc lời gọi mà bên gửi mong muốn nhận được một reply tương ứng. Nội dung request có thể là câu hỏi về dữ liệu hoặc đề nghị thực hiện một việc. Để tránh mơ hồ trong mô hình nghiệp vụ, nên phân biệt hai trường hợp:

- **Query request:** yêu cầu đọc thông tin, ví dụ `GetOrderStatus`. Theo nguyên tắc CQRS/CQS, query không nên làm thay đổi trạng thái nghiệp vụ.
- **Command request:** yêu cầu thực hiện hành động, ví dụ `ReserveInventory`. Về ngữ nghĩa nghiệp vụ, đây là command dù giao thức gọi nó là request.

Request–reply là mẫu tương tác: requester gửi request, receiver xử lý và gửi reply. Reply có thể mang dữ liệu, kết quả, thông tin từ chối hoặc lỗi. Nếu request được gửi qua message broker, hai bên thường cần:

1. **Correlation ID:** mã liên kết reply với request ban đầu.
2. **Reply destination:** nơi requester nhận reply, có thể là reply queue, topic hoặc channel tùy hạ tầng.
3. **Timeout:** thời gian tối đa requester chờ kết quả.
4. **Quy tắc lỗi:** phân biệt từ chối nghiệp vụ, lỗi kỹ thuật, timeout và trường hợp không có reply.
5. **Idempotency:** xử lý an toàn nếu request bị gửi lại hoặc consumer nhận trùng.

Ví dụ `GetOrderStatus` yêu cầu trạng thái của `ORD-100`. Reply có thể là `OrderStatusResult` chứa trạng thái `SHIPPED`, hoặc một kết quả không tìm thấy. Requester dùng correlation ID để ghép reply đúng với request, đặc biệt khi nhiều request đang chạy đồng thời.

### Request–reply không phải lúc nào cũng là đồng bộ

Với lời gọi hàm trực tiếp hoặc HTTP đồng bộ, caller thường chờ kết quả trong cùng luồng tương tác. Với messaging, request và reply có thể đến ở hai thời điểm khác nhau; requester có thể chờ bất đồng bộ, lưu trạng thái chờ hoặc tiếp tục xử lý công việc khác. Nếu timeout, requester chỉ biết chưa nhận được reply đúng hạn; điều đó không chứng minh receiver chưa xử lý request.

Nếu chỉ cần biết broker đã tiếp nhận message, acknowledgement có thể đủ. Nếu cần biết nghiệp vụ đã hoàn tất hay chưa, phải có reply hoặc cơ chế tra cứu trạng thái riêng. **Transport acknowledgement không đồng nghĩa business response.**

## 6. Quan hệ giữa các khái niệm trong một luồng nghiệp vụ

Xét quy trình đặt hàng:

1. Client gửi request `PlaceOrder` để yêu cầu tạo đơn hàng.
2. Ứng dụng xử lý yêu cầu và có thể phát command `ReserveInventory` đến dịch vụ kho.
3. Dịch vụ kho xử lý command. Nếu thành công, nó phát event `InventoryReserved`; nếu không, nó trả kết quả từ chối hoặc phát thông tin thất bại theo hợp đồng.
4. Khi đơn hàng được ghi nhận, hệ thống phát event `OrderCreated`.
5. Consumer email, thanh toán hoặc phân tích nhận các event liên quan và thực hiện công việc của mình.
6. Client có thể gửi query request `GetOrderStatus` sau đó để đọc trạng thái hiện tại.

Mỗi loại payload đều có thể được đóng gói thành `Message<T>` khi đi qua Spring Messaging. Tuy nhiên, không phải mọi bước đều bắt buộc dùng broker. Request từ client có thể đi qua HTTP; lời gọi nội bộ có thể là method call; command hoặc event có thể được chuyển qua message channel hay broker.

Một sơ đồ đơn giản về ý nghĩa nghiệp vụ:

```text
Client
  | request: PlaceOrder
  v
Order Service
  | command: ReserveInventory
  v
Inventory Service
  | event: InventoryReserved
  v
Order workflow
  | event: OrderCreated
  +--------------------+
  v                    v
Email consumer      Analytics consumer

Client -- query request: GetOrderStatus --> Order Service
Client <-- reply: OrderStatusResult ----- Order Service
```

Sơ đồ là ví dụ về ý nghĩa và luồng xử lý. Cách triển khai cụ thể có thể dùng HTTP, Spring Messaging, Spring Integration, JMS hoặc broker khác.

## 7. Áp dụng với các abstraction của Spring

Spring Messaging đặt ra các abstraction cơ bản để xây dựng luồng message:

- `Message<T>` biểu diễn payload và headers.
- `MessageHeaders` cung cấp metadata chuẩn và metadata tùy chỉnh.
- `MessageBuilder` tạo message.
- `MessageChannel` là abstraction cho nơi gửi message.
- `MessageHandler` là abstraction cho thành phần xử lý message.

Ví dụ, một thành phần có thể gửi message qua một `MessageChannel`:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

class InventoryCommandSender {
    private final MessageChannel inventoryCommands;

    InventoryCommandSender(MessageChannel inventoryCommands) {
        this.inventoryCommands = inventoryCommands;
    }

    boolean send( Message<ReserveInventory> command ) {
        return inventoryCommands.send(command);
    }
}
```

Đoạn mã trên chỉ minh họa cách gọi API `MessageChannel`; việc tạo channel, kết nối consumer và cấu hình adapter phụ thuộc ứng dụng. Giá trị `true` cho biết thao tác gửi qua channel được chấp nhận theo hợp đồng của channel đó. Nó không chứng minh nghiệp vụ giữ hàng đã hoàn tất.

`MessageChannel` cũng không đồng nghĩa với message broker. Một channel có thể nối các thành phần trong cùng tiến trình; adapter của Spring Integration hoặc Spring JMS có thể kết nối luồng Spring với hệ thống messaging bên ngoài. Cần phân biệt abstraction trong ứng dụng với hạ tầng vận chuyển thực tế.

### Spring application event và messaging event

Spring Framework còn có cơ chế application event với `ApplicationEventPublisher` và `@EventListener`. Đây là cách các bean trong một Spring `ApplicationContext` thông báo sự kiện cho nhau. Theo mặc định, listener được gọi trong luồng phát event; xử lý bất đồng bộ cần cấu hình phù hợp, chẳng hạn `@Async` và executor.

Application event trong bộ nhớ không tự trở thành message bền vững trên broker. Nó không mặc nhiên có lưu trữ, redelivery sau khi tiến trình khởi động lại hoặc khả năng truyền sang ứng dụng khác. Nếu cần giao tiếp liên tiến trình hoặc độ bền của message, cần tích hợp messaging infrastructure phù hợp.

## 8. Thiết kế payload và hợp đồng message

Một hợp đồng message rõ ràng giúp producer và consumer phát triển độc lập hơn:

- **Đặt tên theo ý nghĩa:** `ReserveInventory` cho command, `InventoryReserved` cho event, `GetOrderStatus` cho query request và `OrderStatusResult` cho reply.
- **Tách kiểu payload:** tránh dùng một class chung với nhiều field tùy chọn rồi dựa vào một cờ để đoán loại message.
- **Định danh rõ ràng:** cân nhắc message ID, command ID, event ID, correlation ID và causation ID theo mục đích. ID của message và ID của nghiệp vụ không nhất thiết giống nhau.
- **Quản lý version:** thay đổi field, kiểu dữ liệu hoặc ý nghĩa phải có chiến lược tương thích giữa producer và consumer đang chạy các phiên bản khác nhau.
- **Chỉ gửi dữ liệu cần thiết:** không mặc định consumer có quyền truy cập toàn bộ entity hoặc dữ liệu nội bộ của producer.
- **Xác thực và phân quyền:** kiểm tra nguồn gửi, quyền thực hiện command và tính hợp lệ của payload ở ranh giới tin cậy.
- **Theo dõi luồng:** dùng correlation ID để nối request/reply và trace context để theo dõi các bước qua nhiều tiến trình.

Với message đi qua broker, payload Java thường cần được chuyển đổi hoặc serialize thành định dạng truyền tải như JSON, XML hoặc byte array. `Message<T>` trong Spring là abstraction trong ứng dụng; nó không tự quy định định dạng wire hay bảo đảm mọi object Java đều có thể gửi qua mọi broker.

## 9. Lỗi thường gặp

- **Coi message và event là từ đồng nghĩa:** message là vật mang dữ liệu; event chỉ là một loại ý nghĩa mà payload có thể mang.
- **Phát event trước khi sự kiện thực sự xảy ra:** consumer có thể tin vào một sự thật không tồn tại. Chỉ phát `OrderCreated` sau khi đơn hàng đã được ghi nhận theo quy tắc nghiệp vụ.
- **Đặt tên command như event:** `SendInvoice` là yêu cầu hành động; `InvoiceSent` là sự thật đã xảy ra.
- **Dùng event để ra lệnh cho một consumer cụ thể:** nếu producer cần một thành phần nhất định thực hiện hành động, command thường thể hiện ý định rõ hơn.
- **Dùng command như broadcast event:** nhiều consumer cùng xử lý một command có thể gây lặp side effect. Chọn destination và mô hình consumer phù hợp.
- **Coi request timeout là request chưa được xử lý:** receiver có thể đã hoàn thành nhưng reply bị trễ hoặc thất lạc. Cần correlation, idempotency và cơ chế tra cứu.
- **Nhầm acknowledgement với kết quả nghiệp vụ:** broker xác nhận message đã được nhận hoặc xử lý theo mức giao nhận; điều đó không nhất thiết cho biết yêu cầu nghiệp vụ thành công.
- **Không xử lý message trùng:** command và request có thể được gửi lại; consumer cần thiết kế idempotent khi phù hợp.
- **Coi Spring application event là message broker:** event nội bộ trong `ApplicationContext` không tự có độ bền hoặc khả năng giao tiếp qua mạng.
- **Đưa quá nhiều dữ liệu vào payload:** payload lớn và chứa dữ liệu không cần thiết làm tăng chi phí truyền tải, rủi ro bảo mật và phụ thuộc schema.

## 10. Cách chọn đúng khái niệm

Khi thiết kế một luồng giao tiếp, hãy tự hỏi:

1. Dữ liệu đang được chuyển đi là gì và cần metadata nào? Đây là câu hỏi về **message envelope**.
2. Bên gửi muốn một thành phần thực hiện hành động làm thay đổi trạng thái? Hãy mô hình hóa thành **command**.
3. Một sự thật nghiệp vụ đã xảy ra và nhiều thành phần có thể quan tâm? Hãy mô hình hóa thành **event**.
4. Bên gửi cần hỏi dữ liệu hoặc chờ một kết quả tương ứng? Hãy mô hình hóa thành **query/request** và xác định hợp đồng **reply**.
5. Kết quả cần ngay trong luồng gọi hay có thể đến sau? Câu trả lời giúp chọn direct call, HTTP request–response hoặc messaging request–reply.
6. Nếu message bị giao lại, xử lý nhiều lần hoặc đến trễ, hệ thống có còn đúng không? Hãy thiết kế idempotency, timeout, retry và dead-letter phù hợp.

## 11. Kết luận

Message là lớp vỏ mang payload và headers. Command biểu đạt ý định thực hiện hành động; event ghi nhận sự thật đã xảy ra; request biểu đạt câu hỏi hoặc đề nghị và thường đi cùng một reply trong mô hình request–reply. Một command, event hay request có thể đều được biểu diễn bằng `Message<T>` trong Spring Messaging.

Khi đặt tên và thiết kế hợp đồng, hãy làm rõ ý nghĩa nghiệp vụ trước, sau đó chọn cách vận chuyển. Phân biệt đúng các khái niệm giúp consumer hiểu chính xác điều cần làm, giảm xử lý trùng, tránh nhầm xác nhận giao nhận với kết quả nghiệp vụ và giúp các thành phần Spring giao tiếp với nhau có chủ đích.