# Phân biệt RPC command với event notification

Trong một hệ thống gRPC, client có thể **yêu cầu server thực hiện một hành động** hoặc **nhận thông báo về một sự kiện đã xảy ra**. Hai nhu cầu này nhìn bề ngoài đều có thể được biểu diễn bằng RPC và Protobuf message, nhưng mang ngữ nghĩa khác nhau:

- **Command** diễn tả ý định hoặc yêu cầu thay đổi trạng thái. Client hỏi server: “Hãy thực hiện việc này”.
- **Event notification** diễn tả một sự thật đã xảy ra. Server thông báo cho client: “Việc này đã xảy ra”.

Phân biệt đúng giúp thiết kế tên method, request/response, status, khả năng retry và luồng streaming phù hợp trong **Spring gRPC**. Một command thường được gọi trực tiếp bằng unary RPC; một luồng event thường được cung cấp qua server streaming. Tuy nhiên, loại RPC chỉ mô tả cách truyền message; nó không tự quyết định ngữ nghĩa command hay event.

## 1. Command là yêu cầu, event là sự thật

Ví dụ trong hệ thống kho:

| Khía cạnh | Command | Event notification |
| --- | --- | --- |
| Ý nghĩa | Yêu cầu giữ 5 sản phẩm | Kho đã giữ 5 sản phẩm |
| Tên | **ReserveStock** | **StockReserved** |
| Thời điểm | Trước khi trạng thái thay đổi | Sau khi sự kiện đã xảy ra |
| Người phát | Client/consumer có quyền yêu cầu | Thành phần ghi nhận sự thay đổi |
| Người nhận | Một service có thẩm quyền xử lý command | Một hoặc nhiều subscriber quan tâm |
| Kết quả | Được chấp nhận, từ chối hoặc lỗi | Thông tin về điều đã xảy ra |

Command thường dùng động từ mệnh lệnh như **Reserve**, **Cancel**, **Approve**, **Create**. Event thường dùng tên sự việc ở dạng quá khứ như **StockReserved**, **OrderCancelled**, **PaymentApproved**. Quy ước tên này giúp người đọc nhận ra client đang yêu cầu hành động hay đang nhận thông báo.

Một command không bảo đảm trạng thái đã thay đổi chỉ vì client gửi request. Server phải xác thực, kiểm tra điều kiện và thực hiện nghiệp vụ. Event chỉ nên được phát sau khi hệ thống đã xác định sự kiện thực sự xảy ra theo quy tắc nhất quán của domain.

## 2. Biểu diễn command và event bằng Protobuf

Một service có thể cung cấp cả RPC command và RPC đăng ký nhận event:

~~~proto
syntax = "proto3";

package acme.inventory.v1;

option java_package = "com.acme.inventory.v1";
option java_multiple_files = true;

import "google/protobuf/timestamp.proto";

service InventoryService {
  // Command: yêu cầu thay đổi tồn kho.
  rpc ReserveStock(ReserveStockRequest)
      returns (ReserveStockResponse);

  // Subscription: nhận các event đã xảy ra.
  rpc WatchStockEvents(WatchStockEventsRequest)
      returns (stream StockEvent);
}

message ReserveStockRequest {
  string product_id = 1;
  int32 quantity = 2;
  string idempotency_key = 3;
}

message ReserveStockResponse {
  string reservation_id = 1;
  int64 stock_version = 2;
}

message WatchStockEventsRequest {
  string product_id = 1;
  int64 after_sequence = 2;
}

message StockEvent {
  string event_id = 1;
  string product_id = 2;
  int64 sequence = 3;
  google.protobuf.Timestamp occurred_at = 4;

  oneof payload {
    StockReserved stock_reserved = 5;
    StockReleased stock_released = 6;
  }
}

message StockReserved {
  int32 quantity = 1;
  string reservation_id = 2;
}

message StockReleased {
  int32 quantity = 1;
  string reservation_id = 2;
}
~~~

Trong contract này:

- **ReserveStock** là **command RPC**: client gửi một yêu cầu và nhận một kết quả xử lý.
- **WatchStockEvents** là **RPC đăng ký nhận event**: client gửi bộ lọc/điểm bắt đầu, server phát nhiều **StockEvent**.
- **StockEvent** là envelope dùng chung, có **event_id** để nhận diện, **sequence** để sắp thứ tự trong phạm vi sản phẩm và **occurred_at** để ghi thời điểm.
- **oneof payload** phân biệt loại sự kiện và giữ dữ liệu đặc thù của từng event.
- **idempotency_key** giúp server nhận diện các lần gửi lại cùng một command nếu client mất phản hồi.

Không đặt tên event là **ReserveStockRequest** hoặc tái sử dụng command request làm event. Request thể hiện ý định trước khi xử lý; event mô tả kết quả đã xảy ra và có thể được nhiều consumer sử dụng.

## 3. Vòng đời command RPC

Một command thường được gọi bằng unary RPC vì client cần gửi một yêu cầu và nhận kết quả của chính yêu cầu đó:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as InventoryService
    participant D as Domain / database
    C->>S: ReserveStock(command)
    S->>S: Xác thực và kiểm tra quyền
    S->>D: Kiểm tra tồn kho, thực hiện giữ hàng
    alt Được chấp nhận
        D-->>S: Reservation đã được ghi nhận
        S-->>C: ReserveStockResponse
        S-->>C: status OK
    else Không đủ tồn kho
        D-->>S: Từ chối theo nghiệp vụ
        S-->>C: status FAILED_PRECONDITION
    end
~~~

Server nên phân biệt:

- **Lỗi giao thức/đầu vào:** ví dụ thiếu **product_id**, dùng **INVALID_ARGUMENT**.
- **Không đủ điều kiện nghiệp vụ:** ví dụ tồn kho không đủ, có thể dùng **FAILED_PRECONDITION** hoặc trả một kết quả từ chối có cấu trúc nếu đó là kết quả bình thường của domain.
- **Không có quyền:** dùng **PERMISSION_DENIED**.
- **Lỗi hạ tầng tạm thời:** có thể dùng **UNAVAILABLE** khi phù hợp.

Không nên trả **OK** với một response trông như thành công khi command thực tế bị từ chối. Nếu từ chối là một kết quả nghiệp vụ bình thường mà client cần xử lý trực tiếp, schema có thể biểu diễn rõ **accepted**, **rejection_reason** hoặc một enum trạng thái. Nếu dùng gRPC status, client cần đọc status để biết command không hoàn tất.

### Retry command an toàn

Client có thể gửi lại command khi gặp timeout hoặc mất kết nối, nhưng server có thể đã thực hiện thao tác trước khi phản hồi bị mất. **idempotency_key** giúp server nhận diện request lặp và trả lại kết quả đã ghi nhận thay vì giữ hàng lần thứ hai.

Chính sách idempotency phải được thực thi ở tầng nghiệp vụ/lưu trữ; chỉ thêm field vào Protobuf không tự tạo bảo đảm chống lặp. Cần xác định phạm vi khóa, thời gian lưu, cách xử lý cùng khóa nhưng payload khác và tính nguyên tử giữa cập nhật dữ liệu với lưu kết quả command.

## 4. Vòng đời event notification

Event notification không yêu cầu consumer ra lệnh thay đổi trạng thái. Consumer đăng ký theo dõi và nhận các sự kiện khi chúng xảy ra:

~~~mermaid
sequenceDiagram
    participant C as Event consumer
    participant S as InventoryService
    participant E as Event source
    C->>S: WatchStockEvents(product_id, after_sequence)
    S->>E: Đăng ký theo dõi
    E-->>S: StockReserved(sequence=41)
    S-->>C: StockEvent 41
    E-->>S: StockReleased(sequence=42)
    S-->>C: StockEvent 42
    Note over C,S: Stream tiếp tục cho đến cancel, lỗi hoặc kết thúc
~~~

**WatchStockEvents** dùng **server streaming** vì client gửi một request đăng ký, còn server gửi nhiều event. Client có thể xử lý từng event khi nhận được thay vì đợi toàn bộ lịch sử.

Event notification cần mang đủ thông tin để consumer:

1. Xác định event bằng **event_id**.
2. Xác định đối tượng bị tác động bằng **product_id**.
3. Kiểm tra thứ tự hoặc phát hiện khoảng trống bằng **sequence**.
4. Biết loại và nội dung sự kiện qua **oneof payload**.
5. Biết thời điểm sự kiện xảy ra qua **occurred_at**.

Không nên giả định event luôn đến đúng một lần hoặc consumer luôn online. Nếu cần replay, resume hoặc đảm bảo không mất sự kiện, server phải có nguồn lưu event và giao thức cursor/sequence rõ ràng. Một stream gRPC đang mở tự nó không phải hàng đợi sự kiện bền vững.

## 5. Command và event có thể dùng các loại RPC khác nhau

| Nhu cầu | Kiểu RPC thường phù hợp | Lý do |
| --- | --- | --- |
| Gửi một command và nhận kết quả xử lý | **Unary** | Một yêu cầu, một kết quả |
| Đăng ký nhận các event liên tục | **Server streaming** | Một subscription, nhiều notification |
| Gửi một lô command rồi nhận báo cáo tổng hợp | **Client streaming** | Nhiều request, một kết quả cuối |
| Gửi tín hiệu điều khiển và nhận event/ack trong cùng phiên | **Bidirectional streaming** | Hai chiều cần trao đổi đan xen |

Không đồng nhất **event** với **server streaming**. Event là ngữ nghĩa dữ liệu; server streaming là cách truyền nhiều response message. Một event cũng có thể được chuyển qua message broker, webhook, server streaming hoặc một cơ chế khác tùy kiến trúc.

Tương tự, command không nhất thiết luôn unary. Một API upload lệnh theo batch có thể dùng client streaming, nhưng từng phần tử vẫn là command nếu nó biểu thị yêu cầu thực hiện hành động. Loại RPC phải được chọn theo cardinality và thời điểm trao đổi; command/event mô tả ngữ nghĩa nghiệp vụ.

## 6. Event notification không phải durable event bus

Một method **WatchStockEvents** giữ một RPC mở và phát event cho client đang kết nối. Nó **không tự cung cấp**:

- Lưu trữ event bền vững để replay sau khi client offline.
- Fan-out tới nhiều consumer với offset độc lập.
- Exactly-once delivery hoặc tự động chống xử lý trùng.
- Xác nhận consumer đã xử lý và commit event.
- Retention, dead-letter hoặc chính sách retry bền vững.

Nếu hệ thống cần các năng lực này, dùng event log hoặc message broker phù hợp làm nguồn phát; gRPC có thể đóng vai trò API stream cho client. Nếu chỉ cần thông báo trực tiếp cho một client đang online, server streaming có thể đủ.

Một mô hình triển khai phổ biến:

1. Command được xử lý và cập nhật trạng thái domain.
2. Event tương ứng được ghi bền vững cùng giao dịch hoặc qua **transactional outbox**.
3. Publisher đọc outbox/event log và phát tới subscriber hoặc broker.
4. gRPC server streaming chuyển event đến consumer online.
5. Consumer lưu **event_id/sequence** đã xử lý và dùng cursor để tiếp tục khi kết nối lại.

Transactional outbox giúp tránh tình huống database đã cập nhật nhưng event không được phát do tiến trình dừng giữa hai thao tác. Nó không tự bảo đảm exactly-once end-to-end; consumer vẫn cần xử lý lặp an toàn.

## 7. Thiết kế contract và tên gọi dễ hiểu

Tên command thường dùng động từ mệnh lệnh:

- **ReserveStock**
- **ReleaseReservation**
- **CancelOrder**
- **ApprovePayment**

Tên event thường mô tả điều đã xảy ra:

- **StockReserved**
- **ReservationReleased**
- **OrderCancelled**
- **PaymentApproved**

Tên subscription method có thể dùng **Watch...** hoặc **Subscribe...**, ví dụ **WatchStockEvents**. Request của subscription chứa tiêu chí lọc và cursor, không nên chứa lệnh thay đổi trạng thái.

Một số nguyên tắc:

- Event nên **immutable**: khi đã phát hành, không sửa ý nghĩa sự kiện cũ.
- Có **event_id** ổn định để deduplicate.
- Có sequence/version theo aggregate nếu cần phát hiện thiếu hoặc sai thứ tự.
- Phân biệt **occurred_at** (thời điểm domain event xảy ra) với thời điểm consumer nhận event.
- Không nhét dữ liệu nhạy cảm hoặc thông tin không cần thiết vào event payload.
- Khi schema event mở rộng, tuân thủ quy tắc tương thích Protobuf: không tái sử dụng field number đã xóa; dùng **reserved** khi cần.

## 8. Bảo mật, deadline và xử lý lỗi

Command và event đều cần xác thực, phân quyền và quan sát:

- **Command:** kiểm tra caller có quyền thực hiện hành động trên tài nguyên cụ thể không. Gắn deadline theo ngân sách thao tác và dùng idempotency khi retry.
- **Event subscription:** kiểm tra caller có quyền xem event của sản phẩm/tenant nào; giới hạn số stream đồng thời và thời gian sống phù hợp.
- **Metadata/interceptor:** truyền identity, request ID và trace context ở cấp RPC; không dùng metadata thay cho dữ liệu event thay đổi theo từng message.
- **TLS/mTLS:** bảo vệ dữ liệu trên đường truyền và xác thực peer theo yêu cầu triển khai.

Với server streaming, client có thể đã nhận một phần event rồi gặp **UNAVAILABLE** hoặc **DEADLINE_EXCEEDED**. Khi kết nối lại, client nên dùng **after_sequence** hoặc cursor đã lưu để tiếp tục; server cần xác định hành vi khi cursor quá cũ hoặc event không còn trong retention.

Với command, timeout không chứng minh thao tác chưa xảy ra. Client nên truy vấn trạng thái theo idempotency key hoặc gửi lại cùng key theo chính sách server, không tạo key mới cho cùng một hành động chưa rõ kết quả.

## 9. Kiểm thử command và event riêng biệt

Kiểm thử command cần xác nhận **tác động nghiệp vụ và kết quả**:

- Command hợp lệ tạo đúng reservation.
- Command không đủ điều kiện trả status/kết quả từ chối đúng.
- Gửi lại cùng idempotency key không tạo reservation trùng.
- Caller không đủ quyền bị từ chối.

Kiểm thử event cần xác nhận **nội dung, thứ tự và vòng đời subscription**:

- Consumer nhận event sau khi thay đổi domain được ghi nhận.
- **event_id** và **sequence** ổn định, không bị đảo trong phạm vi đã cam kết.
- Hủy stream giải phóng subscription.
- Mất kết nối rồi resume không bỏ sót event theo chính sách lưu trữ.
- Consumer xử lý được event trùng mà không lặp tác động.

Có thể dùng gRPC in-process để kiểm tra stub/server streaming, nhưng cần integration test với kho lưu trữ hoặc event publisher thật để xác nhận transactional outbox, replay và resume. Unit test chỉ gọi trực tiếp hàm xử lý command không chứng minh event đã được phát đúng thời điểm.

## 10. Ghi nhớ và tự kiểm tra

**Command** là ý định yêu cầu thay đổi trạng thái; **event notification** là thông tin về sự thật đã xảy ra. Một command thường dùng unary RPC để nhận kết quả, còn một subscription event thường dùng server streaming để nhận nhiều notification. Tuy nhiên, ngữ nghĩa command/event độc lập với cardinality của RPC.

Tự kiểm tra:

1. **ReserveStock** và **StockReserved** khác nhau ở thời điểm và ngữ nghĩa như thế nào?
2. Vì sao **WatchStockEvents** là server streaming nhưng bản thân event không đồng nghĩa với streaming?
3. Client gặp timeout khi gọi **ReserveStock**: vì sao không thể kết luận server chưa giữ hàng?
4. Vì sao một gRPC stream đang mở không thay thế được event log hoặc durable message broker?
5. Những trường nào giúp consumer deduplicate và resume event sau khi mất kết nối?

Thiết kế rõ ranh giới giữa **yêu cầu thực hiện** và **thông báo điều đã xảy ra** giúp contract Spring gRPC dễ hiểu, retry an toàn hơn và hỗ trợ nhiều consumer mà không trộn lẫn trách nhiệm command với phân phối event.
