# Phân chia hàm, sự kiện kích hoạt và đơn vị triển khai

Kiến trúc **serverless** cho phép nhóm phát triển tập trung vào logic nghiệp vụ trong khi nền tảng quản lý phần lớn việc cấp phát máy chủ, mở rộng và môi trường thực thi. Tuy nhiên, “không quản lý máy chủ” không có nghĩa ứng dụng tự nhiên được chia nhỏ đúng cách hoặc không còn trách nhiệm về độ tin cậy, bảo mật, chi phí và vận hành. Khi xây dựng hệ thống serverless, ba quyết định liên quan chặt chẽ là **phân chia hàm (function decomposition), sự kiện kích hoạt (triggers/events) và đơn vị triển khai (deployment units)**.

Bài học thuộc chương **Kiến trúc serverless** của lộ trình **Cloud Architecture**. Nội dung trình bày cách chuyển yêu cầu nghiệp vụ thành các handler, luồng sự kiện và gói triển khai có ranh giới hợp lý. Một hàm nên đại diện cho một thao tác hoặc phản ứng nghiệp vụ có ý nghĩa, nhận đầu vào qua hợp đồng rõ ràng, thực hiện công việc trong giới hạn tài nguyên và tạo kết quả hoặc sự kiện có thể kiểm chứng. Đơn vị triển khai cần cân bằng giữa tốc độ phát hành, phạm vi ảnh hưởng khi lỗi, quyền truy cập và mức độ độc lập.

Sau bài học, bạn có thể:

- Phân biệt function, handler, trigger, event source và deployment unit.
- Chia ứng dụng thành hàm theo năng lực và thao tác nghiệp vụ, tránh cả hàm khổng lồ lẫn hàm vụn vặt.
- Chọn trigger đồng bộ hoặc bất đồng bộ theo yêu cầu phản hồi, độ bền và khả năng chịu lỗi.
- Thiết kế event contract, retry, idempotency, ordering, dead-letter handling và quan sát.
- Quyết định hàm nào nên triển khai cùng nhau, hàm nào cần đơn vị phát hành độc lập.
- Thiết kế quyền IAM, cấu hình, secret và giới hạn tài nguyên theo từng chức năng.
- Đánh giá chi phí, hiệu năng, độ tin cậy và vận hành serverless theo tư duy Well-Architected.

## 1. Các khái niệm nền tảng

Trong mô hình function-as-a-service (FaaS), nhà cung cấp khởi tạo môi trường thực thi hàm khi có yêu cầu hoặc sự kiện, quản lý hạ tầng thực thi và tính phí theo mô hình dịch vụ cụ thể. Tên gọi và giới hạn khác nhau giữa nền tảng, nhưng các khái niệm thường gặp như sau.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Function** | Đơn vị logic có thể được nền tảng gọi để thực hiện một công việc | CreateBooking, SendReceipt |
| **Handler** | Điểm vào nhận invocation, kiểm tra đầu vào và gọi logic ứng dụng | Hàm xử lý HTTP request hoặc message |
| **Trigger** | Cấu hình hoặc nguồn kích hoạt function | HTTP route, queue message, object-created event, timer |
| **Event source** | Dịch vụ hoặc thành phần phát sinh sự kiện/đầu vào gọi hàm | API gateway, message broker, object storage |
| **Event** | Bản ghi mô tả điều đã xảy ra hoặc một yêu cầu công việc | BookingConfirmed, PaymentRequested |
| **Invocation** | Một lần function được gọi và thực thi | Một HTTP request hoặc một message |
| **Runtime** | Môi trường thực thi ngôn ngữ và mã của function | Java, Node.js, Python hoặc runtime nền tảng |
| **Deployment unit** | Artifact và cấu hình được phát hành như một đơn vị quản lý version/lifecycle | Một function package hoặc một nhóm function |
| **Workflow/state machine** | Thành phần điều phối nhiều bước, trạng thái, nhánh và lỗi | Quy trình đặt hàng, thanh toán và hoàn tiền |

Function là đơn vị logic, còn deployment unit là ranh giới phát hành. Một deployment unit có thể bao gồm một function hoặc nhiều handler cùng được đóng gói tùy nền tảng/framework. Ngược lại, một nghiệp vụ lớn có thể gồm nhiều function triển khai riêng và được điều phối qua queue, event bus hay workflow.

Không được nhầm trigger với event contract. Trigger quyết định khi nào và bằng cách nào function được gọi; event contract quyết định dữ liệu, ý nghĩa và version của thông điệp mà function nhận.

## 2. Phân chia hàm từ năng lực nghiệp vụ

Điểm xuất phát tốt là các use case và sự kiện nghiệp vụ, không phải biến mọi method trong code thành một cloud function. Ví dụ hệ thống cho thuê thiết bị có các thao tác: tạo yêu cầu đặt thuê, giữ tài sản, xác nhận thanh toán, gửi biên nhận, hết hạn giữ chỗ và tạo báo cáo.

Mỗi thao tác có thể trở thành một function hoặc một phần trong workflow. Ranh giới phụ thuộc yêu cầu dữ liệu, giao dịch, latency, quyền và cách vận hành.

### 2.1. Tiêu chí của một function có ranh giới tốt

Một function nên có:

1. **Mục đích rõ:** mô tả được bằng một hành động hoặc phản ứng nghiệp vụ.
2. **Hợp đồng ổn định:** có schema, validation, error semantics và version.
3. **Trách nhiệm kiểm thử được:** điều kiện thành công có thể xác định.
4. **Quyền hạn tối thiểu:** chỉ truy cập dữ liệu, secret và dịch vụ cần thiết.
5. **Nguồn kích hoạt phù hợp:** HTTP, queue, event, schedule hay workflow được chọn có chủ đích.
6. **Ngưỡng tài nguyên thực tế:** thời gian, memory, concurrency và payload nằm trong giới hạn nền tảng.
7. **Hành vi lỗi xác định:** biết điều gì retry, điều gì từ chối, điều gì cần xử lý thủ công.

Một hàm có thể gọi nhiều lớp domain/application nội bộ. Không cần biến mỗi bước kiểm tra hoặc helper method thành một cloud function, vì điều đó làm tăng network hop, số lần deploy và độ phức tạp debug.

### 2.2. Ví dụ phân chia cho nền tảng đặt thuê

| Năng lực/use case | Function gợi ý | Công việc |
| --- | --- | --- |
| API đặt thuê | CreateBooking | Xác thực request, kiểm tra quyền và tạo trạng thái yêu cầu |
| Giữ tài sản | ReserveInventory | Kiểm tra khả dụng và giữ chỗ với invariant nghiệp vụ |
| Thanh toán | RequestPayment | Gọi đối tác theo idempotency key, ghi trạng thái chờ |
| Callback thanh toán | HandlePaymentResult | Xác minh webhook, cập nhật trạng thái và phát sự kiện |
| Thông báo | SendBookingNotification | Gửi email/SMS sau sự kiện xác nhận |
| Hết hạn giữ chỗ | ExpireReservation | Kiểm tra hạn và giải phóng giữ chỗ hợp lệ |
| Báo cáo | BuildDailyReport | Tổng hợp dữ liệu ngoài đường xử lý giao dịch |

Đây là điểm bắt đầu. ReserveInventory có thể phải ở cùng transaction boundary với thao tác ghi booking nếu cả hai dùng cùng database và nghiệp vụ yêu cầu commit nguyên tử. Nếu triển khai riêng qua mạng, cần thiết kế trạng thái và bước bù trừ; không thể giả định hai function độc lập vẫn chia sẻ transaction ACID.

### 2.3. Tránh hai cực đoan

**Function quá lớn:** một handler nhận request đặt thuê, kiểm tra khách, giữ hàng, thu tiền, gửi email và tạo báo cáo. Hậu quả là thay đổi nhỏ ảnh hưởng nhiều chức năng; quyền IAM quá rộng; thời gian chạy dài; retry có thể thực hiện lại cả chuỗi; khó phân biệt lỗi từng bước.

**Function quá nhỏ:** một function cho mỗi phép kiểm tra hoặc câu lệnh database. Hậu quả là quá nhiều invocation, network hop, cấu hình, quyền, log và deployment; latency và chi phí điều phối có thể vượt giá trị của việc tách.

Mục tiêu là đặt ranh giới nơi **ý nghĩa nghiệp vụ, quyền sở hữu dữ liệu, cách mở rộng hoặc vòng đời vận hành thực sự khác nhau**.

## 3. Chọn trigger theo cách công việc cần được thực hiện

Trigger là nơi bắt đầu một invocation. Việc chọn sai trigger có thể khiến hệ thống khó đạt latency, mất khả năng retry hoặc vô tình cho phép một client kiểm soát quá nhiều tài nguyên.

| Trigger | Mô hình gọi | Dùng khi | Điều cần thiết kế |
| --- | --- | --- | --- |
| HTTP/API gateway | Đồng bộ request–response | Client cần câu trả lời ngay | Auth, timeout, payload limits, rate limit, status code |
| Queue/message | Bất đồng bộ, thường có retry | Công việc xử lý sau, cần hấp thụ burst | Visibility/ack, retry, dedup, DLQ, backpressure |
| Event bus | Publish–subscribe | Nhiều consumer độc lập phản ứng với sự kiện | Schema, routing, filtering, fan-out, version |
| Object storage event | Bất đồng bộ khi object thay đổi | Xử lý tệp, ảnh, tài liệu | Duplicate/order, object key/version, kích thước |
| Scheduler/timer | Gọi theo thời điểm hoặc chu kỳ | Báo cáo, cleanup, expiration, reconciliation | Time zone, missed schedule, duplicate run, overlap |
| Stream | Liên tục theo record/batch | Telemetry, clickstream, sự kiện lớn | Partition, ordering scope, checkpoint, lag |
| Workflow/state machine | Điều phối nhiều bước | Quy trình dài hoặc có nhiều trạng thái | State persistence, timeout, retry, compensation |

Một dịch vụ cụ thể có thể dùng polling hoặc push để nối event source với function. Phải kiểm tra semantics của nền tảng, đặc biệt là số lần giao nhận, thời gian chờ, cách ack và giới hạn batch. Không suy luận mọi event trigger đều đảm bảo exactly-once.

## 4. Chọn đồng bộ hay bất đồng bộ

**Đồng bộ** phù hợp khi caller cần kết quả để hoàn thành tương tác, ví dụ kiểm tra request hợp lệ hoặc lấy trạng thái hiện tại. **Bất đồng bộ** phù hợp khi công việc có thể hoàn tất sau, cần hấp thụ burst hoặc có nhiều consumer độc lập.

### 4.1. Đường đồng bộ

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant F as CreateBooking
    participant D as Database
    C->>G: POST /bookings
    G->>F: Invoke đồng bộ
    F->>D: Validate và lưu booking
    D-->>F: Commit
    F-->>G: Booking ID + status
    G-->>C: 201 Created
~~~

Ưu điểm là dễ mô hình request–response, client biết kết quả tức thời và ít thành phần trung gian. Rủi ro là thời gian phản hồi bị ràng buộc bởi timeout của nhiều lớp; function chờ database hoặc dịch vụ ngoài có thể chiếm concurrency; client retry khi timeout có thể tạo request trùng nếu không idempotent.

### 4.2. Đường bất đồng bộ

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant Q as Queue
    participant W as Worker Function
    participant D as Database
    C->>A: Gửi yêu cầu xử lý
    A->>Q: Publish công việc
    Q-->>A: Đã chấp nhận
    A-->>C: 202 Accepted + jobId
    Q->>W: Deliver message
    W->>D: Xử lý và ghi trạng thái
    D-->>W: Commit
    W-->>Q: Ack
    C->>A: GET /jobs/{jobId}
    A-->>C: Trạng thái xử lý
~~~

Caller nhận **đã chấp nhận công việc**, không đồng nghĩa công việc đã thành công. API nên trả 202 Accepted cùng định danh theo dõi khi semantics phù hợp; cung cấp endpoint hoặc callback để lấy trạng thái. Cần xác định message đã được ghi bền vững trước khi trả lời, thời gian tồn tại, cách thông báo thất bại và trạng thái cuối.

### 4.3. Ma trận lựa chọn

| Yêu cầu | Đồng bộ | Bất đồng bộ |
| --- | --- | --- |
| Cần phản hồi ngay để tiếp tục UI | Phù hợp | Chỉ phù hợp nếu có trạng thái chờ |
| Tác vụ kéo dài hoặc khó dự đoán | Dễ vướng timeout | Phù hợp hơn |
| Hấp thụ burst | Phụ thuộc concurrency/API quota | Queue có thể buffer |
| Nhiều consumer độc lập | Caller phải phối hợp | Event bus hỗ trợ fan-out |
| Giao dịch cần kết quả ngay | Phù hợp nếu ngắn và transaction đúng | Cần mô hình trạng thái |
| Chịu lỗi dependency tạm ngừng | Caller bị ảnh hưởng nếu chờ | Retry, DLQ và retention tách thời điểm |
| Quan sát tiến trình dài | Khó nếu chỉ giữ HTTP request | Có thể lưu job state |

Có thể kết hợp hai mô hình: đồng bộ để xác thực và ghi nhận yêu cầu, bất đồng bộ để làm công việc dài hoặc fan-out. Không cần ép một use case chỉ dùng một kiểu giao tiếp.

## 5. Thiết kế hợp đồng sự kiện

Một event tốt thể hiện **điều đã xảy ra**, có định danh, thời điểm, nguồn và schema version. Tránh tên mơ hồ như UpdateData nếu không biết điều gì đã xảy ra và ai sở hữu thay đổi.

Ví dụ event nghiệp vụ:

~~~json
{
  "eventId": "evt-7f239a",
  "eventType": "BookingConfirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T08:30:00Z",
  "producer": "booking-module",
  "correlationId": "req-18273",
  "subject": {
    "bookingId": "bk-100582",
    "customerId": "cus-207"
  },
  "data": {
    "reservationId": "rs-8041",
    "confirmedAt": "2026-11-18T08:29:58Z"
  }
}
~~~

Các trường trên chỉ là ví dụ:

- **eventId:** định danh duy nhất để consumer nhận diện duplicate.
- **eventType:** tên sự kiện mang ý nghĩa nghiệp vụ.
- **schemaVersion:** version schema để consumer tương thích khi hợp đồng thay đổi.
- **occurredAt:** thời điểm nghiệp vụ xảy ra; nơi nhận có thể ghi thêm ingestion time.
- **producer:** mô đun/service chịu trách nhiệm phát event.
- **correlationId/trace context:** nối sự kiện với yêu cầu ban đầu.
- **Payload:** chỉ chứa dữ liệu consumer cần; tránh phát tán toàn bộ bản ghi và PII.

### 5.1. Event khác command

- **Event:** thông báo sự việc đã xảy ra, ví dụ BookingConfirmed.
- **Command:** yêu cầu một bên thực hiện việc gì, ví dụ RequestRefund.

Event có thể có nhiều subscriber và thường không yêu cầu producer biết từng consumer. Command có một đích chịu trách nhiệm xử lý hoặc một workflow quản lý kết quả. Đặt tên đúng giúp tránh hiểu nhầm rằng một event “đã xác nhận thanh toán” thực chất chỉ là yêu cầu thanh toán đang chờ.

### 5.2. Thay đổi schema và tương thích

Consumer có thể triển khai chậm hơn producer. Khi thêm field mới, cần xác định field có bắt buộc không, giá trị mặc định và cách consumer cũ xử lý field không nhận biết. Khi đổi kiểu hoặc bỏ field, phải có lộ trình version và đo số consumer còn dùng schema cũ.

Không gửi class nội bộ hoặc object serialization gắn chặt runtime producer làm event contract. Payload nên là schema có thể kiểm tra, version và tài liệu hóa, thường dùng JSON, Avro, Protobuf hoặc định dạng được nền tảng hỗ trợ.

## 6. Retry, duplicate và idempotency

Hệ thống event-driven thường phải giả định một message có thể được giao hơn một lần. Ví dụ worker đã cập nhật DB thành công nhưng lỗi trước khi ack; queue có thể gửi lại và consumer nhận lại cùng công việc.

**Idempotency** là tính chất khi xử lý lặp lại cùng yêu cầu/event không làm thay đổi kết quả nghiệp vụ ngoài dự kiến.

Cách triển khai thường gặp:

1. Producer gắn eventId hoặc idempotencyKey ổn định.
2. Consumer lưu ID đã xử lý trong kho dữ liệu bền vững với unique constraint phù hợp.
3. Ghi dấu idempotency và kết quả nghiệp vụ trong transaction thích hợp.
4. Nếu nhận lại cùng ID, trả/giữ kết quả trước đó thay vì thực hiện tác động lần hai.
5. Đặt retention cho dấu chống trùng đủ dài so với thời gian retry/replay.

Ví dụ logic giả mã:

~~~text
handle(event):
    begin transaction

    if processed_event exists for event.eventId:
        return previous_result

    validate business preconditions
    apply business change
    insert processed_event(event.eventId, result)

    commit transaction
    acknowledge message
~~~

Phép kiểm tra và ghi dấu phải chống race condition. Nếu hai invocation cùng nhận một ID gần đồng thời, kiểm tra ở application đơn thuần có thể không đủ; cần unique key, atomic insert hoặc cơ chế khóa tương ứng. Nếu tác động là gọi API thanh toán, phải dùng idempotency key mà đối tác hỗ trợ hoặc reconciliation, vì transaction DB nội bộ không thể hoàn tác một giao dịch bên ngoài đã xảy ra.

### 6.1. Retry và backoff

Retry vô hạn và ngay lập tức có thể tạo retry storm khi dependency lỗi. Cần:

- Retry lỗi tạm thời như timeout, throttling hoặc service unavailable theo policy.
- Không retry lỗi đầu vào vĩnh viễn như schema invalid hoặc quyền bị từ chối nếu không có thay đổi.
- Exponential backoff kèm jitter và giới hạn số lần/thời gian.
- Theo dõi retry count, queue age, error rate và DLQ depth.
- Phân biệt lỗi tạm thời với lỗi nghiệp vụ cần xử lý thủ công.

### 6.2. Dead-letter queue

Sau số lần thử hoặc thời hạn được cấu hình, message có thể chuyển sang **Dead-Letter Queue (DLQ)**. DLQ là hàng đợi cách ly để điều tra và replay có kiểm soát, không phải nơi để quên message.

Quy trình cần alert khi message xuất hiện, giữ metadata lỗi mà không lộ secret/PII, phân quyền xem/replay, kiểm tra idempotency và version schema trước khi replay, có retention và owner.

## 7. Ordering, tính nhất quán và workflow dài

Không phải queue hay event bus nào cũng bảo đảm thứ tự toàn cục. Thứ tự có thể chỉ được bảo đảm trong một partition, group hoặc session; nền tảng khác có thể giao message song song.

Nếu trạng thái nghiệp vụ phụ thuộc thứ tự, ví dụ PaymentAuthorized trước PaymentCaptured, cần chọn partition key phù hợp như bookingId, sequence number hoặc version của aggregate. Consumer cũng phải phát hiện event đến muộn hoặc sai phiên bản.

Timestamp của producer có thể lệch đồng hồ. Hai event có thời điểm gần nhau chưa chắc thứ tự nghiệp vụ đúng. Có thể cần aggregate version, sequence, partition ordering, kiểm tra trạng thái trước khi áp dụng và phân biệt event time với ingestion time.

### 7.1. Workflow/state machine

Quy trình đặt thuê có thể gồm giữ tài sản, yêu cầu thanh toán, nhận callback, xác nhận đơn và gửi thông báo. Nếu bước có thể chờ lâu, workflow/state machine lưu trạng thái giúp theo dõi tiến trình, timeout, retry từng bước và xử lý nhánh.

~~~mermaid
flowchart TD
    A["Nhận yêu cầu đặt thuê"] --> B["Giữ tài sản"]
    B --> C{"Giữ thành công?"}
    C -- "Không" --> X["Từ chối yêu cầu"]
    C -- "Có" --> D["Yêu cầu thanh toán"]
    D --> E{"Thanh toán thành công?"}
    E -- "Có" --> F["Xác nhận đơn"]
    F --> G["Phát BookingConfirmed"]
    G --> H["Gửi thông báo"]
    E -- "Không / hết hạn" --> I["Giải phóng giữ chỗ"]
    I --> J["Đơn thất bại hoặc chờ xử lý"]
~~~

Nếu workflow không có transaction xuyên dịch vụ, phải định nghĩa **compensation** cho bước đã thành công nhưng bước sau thất bại. Ví dụ thanh toán đã authorize nhưng booking không thể xác nhận thì cần void/hoàn hoặc đối soát, không chỉ đổi trạng thái local.

## 8. Đơn vị triển khai: một function hay nhiều function cùng artifact?

Function decomposition và deployment boundary không giống nhau. Nếu mỗi function là một deployment unit, nhóm có độc lập phát hành và quyền riêng rõ hơn nhưng quản lý nhiều artifact, pipeline, IAM và quan sát. Nếu gộp nhiều function cùng unit, phát hành có thể đơn giản hơn nhưng chức năng có thể chia sẻ cấu hình, runtime hoặc quyền ở mức artifact tùy nền tảng.

| Mô hình | Đặc điểm | Phù hợp khi |
| --- | --- | --- |
| **Một function / một deployment unit** | Mỗi handler có artifact, version và config độc lập | Khác quyền, scale, phụ thuộc, lịch release hoặc owner |
| **Nhiều handler cùng package** | Nhiều entrypoint trong cùng mã nguồn/artifact | Chức năng nhỏ, dependency/runtime chung, release cùng nhau |
| **Function + workflow** | Function thực thi bước; workflow điều phối trạng thái | Quy trình dài, nhánh, timeout, retry hoặc compensation |
| **Function + shared library** | Nhiều function tái sử dụng code đã version hóa | Logic nền ổn định nhưng handler độc lập |
| **Function group/module** | IaC quản lý nhóm function cùng stack | Cần quản lý tài nguyên liên quan theo một đơn vị |

Tên gọi và khả năng gói phụ thuộc nền tảng. Có dịch vụ chỉ triển khai một handler trên một function resource, nhưng nhiều function có thể được định nghĩa trong cùng project hoặc stack. Cần mô tả đúng artifact, cloud resource và release unit.

### 8.1. Khi nào nên gộp?

Có thể gộp function khi cùng runtime và dependency, release cadence gần nhau, cùng owner, cấu hình và quyền có thể dùng chung mà không quá rộng, scaling behavior tương tự và một thay đổi không gây rủi ro lớn cho handler khác.

Ví dụ hai handler nội bộ phục vụ đọc metadata và chuẩn hóa response có thể nằm chung package nếu release cùng nhau. Tuy nhiên, SendNotification và ProcessPayment có thể cần tách vì quyền, dữ liệu và hậu quả sự cố rất khác nhau.

### 8.2. Khi nào nên tách?

Cân nhắc deployment unit riêng nếu IAM của function A cần quyền nhạy cảm mà function B không được có; scale profile khác biệt; runtime/dependency conflict; team, lịch phát hành hoặc SLO khác; cần giảm blast radius; hoặc quy định dữ liệu yêu cầu isolation ở mức hạ tầng.

Đừng tách chỉ vì một function có tên khác. Mỗi unit bổ sung sẽ có quyền, pipeline, logs, alarms, config, version, retry và chi phí quản trị cần duy trì.

## 9. Quy trình deployment và quản lý phiên bản

Một deployment unit serverless thường gồm mã/compiled artifact, runtime, handler entrypoint, memory/timeout/concurrency, environment configuration, IAM, trigger binding, observability và các liên kết tới nguồn dữ liệu.

Đưa phần lớn cấu hình có thể tái lập vào **Infrastructure as Code (IaC)** để review và phát hành có kiểm soát. Không nên phụ thuộc hoàn toàn vào cấu hình sửa tay trong console.

~~~mermaid
flowchart LR
    C["Commit / Pull Request"] --> T["Unit, contract và integration tests"]
    T --> S["Build artifact"]
    S --> Q["Scan dependency và policy"]
    Q --> I["Deploy staging"]
    I --> V["Trigger, load và failure test"]
    V --> P["Phê duyệt và promote version"]
    P --> R["Alias / traffic rollout"]
    R --> M["Theo dõi SLO và rollback"]
~~~

Pipeline nên compile/package và pin dependency; unit test logic nghiệp vụ; contract test event/request schema; scan dependency, artifact, IaC và secret; deploy staging; kiểm tra IAM, networking, timeout, memory, concurrency và observability; promote artifact/version đã kiểm thử; rollout canary; theo dõi lỗi, latency, throttle, retry, DLQ và chi phí; rollback nếu vượt tiêu chí.

Function version và event schema version là hai phiên bản khác nhau. Deploy function mới không nhất thiết làm payload source đổi; thay đổi schema cần lộ trình tương thích giữa producer và consumer. Ưu tiên thêm field không bắt buộc trước, consumer hỗ trợ cả dạng cũ/mới, quan sát adoption rồi mới deprecate field cũ. Với breaking change, dùng versioned event type/topic hoặc adapter theo khả năng hệ thống.

## 10. Bảo mật theo function và deployment unit

Serverless giảm việc quản trị máy chủ nhưng không xóa trách nhiệm bảo mật mã, dữ liệu, danh tính, trigger và cấu hình.

### 10.1. Least privilege

Một function xử lý webhook thanh toán có thể cần đọc secret xác minh chữ ký và cập nhật bảng Payment. Function gửi email chỉ cần đọc dữ liệu thông báo đã được phép và quyền gọi email provider. Nếu cả hai dùng một execution role có quyền đọc mọi dữ liệu khách hàng và hoàn tiền, phạm vi ảnh hưởng khi lộ credential sẽ lớn hơn cần thiết.

Nguyên tắc:

- Mỗi function/deployment unit dùng execution identity riêng khi nền tảng hỗ trợ và lợi ích isolation đáng kể.
- Cấp quyền theo resource và action cụ thể, tránh wildcard rộng.
- Tách quyền publish/subscribe, read/write database và secret retrieval.
- Không đặt credential trong source, artifact, event payload hoặc log.
- Xác thực caller cho HTTP trigger, kiểm tra JWT/claims, tenant và authorization nghiệp vụ.
- Xác minh webhook/signature trước khi tin nội dung bên ngoài.
- Chỉ principal cần thiết được publish hoặc subscribe queue/event source.
- Audit thay đổi IAM, trigger, secret và cấu hình mạng.

### 10.2. Event payload không phải vùng tin cậy

Dù event đến từ nội bộ, nó vẫn có thể được phát sai, gửi trùng, chứa dữ liệu lỗi hoặc chịu ảnh hưởng từ producer bị xâm nhập. Consumer cần validate schema, giới hạn payload, kiểm tra nguồn và quyền đối với hành động. Trường customerId trong message không phải bằng chứng rằng producer được phép thao tác dữ liệu khách hàng đó.

### 10.3. Mạng và dữ liệu

Function truy cập database private có thể cần gắn vào VPC/VNet hoặc dùng endpoint private của nền tảng. Khi đó phải đánh giá địa chỉ mạng, DNS, security group, connection pool, egress, subnet exhaustion và cold start do network setup. Gắn VPC không tự động làm function an toàn; phải kiểm soát route và quyền mạng.

Nếu event hoặc log chứa PII, cần tối thiểu hóa trường dữ liệu, mã hóa, retention và access. Hạn chế gửi payload thô qua nhiều queue hoặc log sink nếu consumer chỉ cần một định danh và vài thuộc tính nghiệp vụ.

## 11. Hiệu năng: cold start, timeout và concurrency

### 11.1. Cold start

**Cold start** là thời gian khởi tạo môi trường thực thi khi nền tảng cần chuẩn bị một execution environment mới. Nó có thể gồm lấy runtime, tải code/dependency, khởi tạo framework, mở kết nối hoặc tải cấu hình.

Cold start phụ thuộc runtime, kích thước package, framework, network attachment, initialization logic, mức sử dụng và tính năng nhà cung cấp. Không có một con số chung cho mọi function.

Để kiểm soát, giảm dependency và công việc khởi tạo không cần; khởi tạo client có chủ đích; tái sử dụng connection trong cùng execution environment nếu được phép nhưng không giả định environment tồn tại mãi; đo p95/p99 thay vì chỉ benchmark lần gọi nóng; cân nhắc provisioned/warm capacity nếu SLO và chi phí hợp lý; kiểm tra ảnh hưởng của VPC/network integration.

### 11.2. Timeout và memory

Mỗi function cần timeout lớn hơn thời gian thực tế kỳ vọng nhưng vẫn giới hạn để tránh chiếm tài nguyên quá lâu. Timeout không thay thế cancellation hoặc idempotency. Nếu platform timeout sau khi side effect đã xảy ra, caller có thể retry và gây lặp tác vụ.

Memory limit có thể liên quan tới CPU/network allocation tùy nền tảng. Tăng memory đôi khi tăng throughput và giảm thời gian chạy đủ để tổng chi phí giảm; cần benchmark theo workload thay vì luôn chọn cấu hình nhỏ nhất.

### 11.3. Concurrency và downstream capacity

Nếu queue phát 1.000 message cùng lúc và function cho phép concurrency lớn, database có thể nhận quá nhiều kết nối. Function scale nhanh hơn DB không đồng nghĩa hệ thống tổng thể có khả năng mở rộng.

Phối hợp concurrency limit của function, inflight message/batch size, connection pool/DB proxy, rate limit đối tác, retry/backoff, backpressure và circuit breaker ở dependency phù hợp. Mục tiêu là **giữ toàn chuỗi trong giới hạn chịu tải**, không chỉ function.

## 12. Chi phí serverless

Serverless thường tính phí theo một hoặc nhiều yếu tố như invocation, thời gian chạy, memory/CPU, dữ liệu truyền, queue/event, API gateway, workflow và storage. Cách tính, free tier, quota và mức giá phụ thuộc nhà cung cấp, region và thời điểm.

**Tổng chi phí use case = invocation/compute + trigger/orchestration + lưu trữ/truyền dữ liệu + observability + downstream services.**

Một function ngắn nhưng được gọi hàng tỷ lần có thể không rẻ. Một function có dependency và cold start tốn thời gian có thể làm chi phí cao hơn dự kiến. Ngược lại, workload bursty hoặc không liên tục thường hưởng lợi khi không phải giữ VM chạy liên tục.

Nếu một use case được chia thành 8 function gọi nhau qua event/API, có thể phát sinh thêm invocation, queue/event request, workflow transitions, network/data transfer, log/trace và thời gian vận hành. Tách có thể đúng khi tạo isolation, scale riêng và giảm blast radius. Phải so sánh **TCO của toàn luồng**, không chỉ giá một invocation.

## 13. Observability từ trigger tới kết quả

Một hệ thống serverless có nhiều function có thể tạo hàng chục bước cho một giao dịch. Nếu không truyền correlation ID và trace context, operator khó biết request nào tạo message nào, consumer nào xử lý, lần retry nào gây lỗi và nghiệp vụ cuối cùng đạt trạng thái gì.

| Lớp | Chỉ số/tín hiệu |
| --- | --- |
| API trigger | Request count, 4xx/5xx, latency p95/p99, throttling |
| Function | Invocation, duration, error, timeout, cold start nếu quan sát được, concurrency |
| Queue/stream | Age of oldest message, backlog, retry, DLQ depth, consumer lag |
| Event bus | Delivery failure, matched/unmatched rules, target latency |
| Workflow | Failed state, retry count, elapsed time, stuck execution |
| Downstream | DB connection, query latency, provider error/rate limit |
| Chi phí | Invocation, compute duration, workflow transition và log volume |

Log cần có cấu trúc và tránh đưa token, secret hoặc toàn bộ payload chứa thông tin cá nhân. Mỗi invocation nên ghi định danh tương quan, function name/version, event ID, kết quả và thời gian. Với workflow dài, ghi trạng thái từng bước và lỗi cuối theo định dạng thống nhất.

Đặt SLO theo outcome, ví dụ tỷ lệ yêu cầu tạo đơn được chấp nhận trong thời gian mục tiêu và tỷ lệ thông báo được gửi trong giới hạn sau xác nhận, thay vì chỉ theo dõi function có tỷ lệ lỗi bằng không.

## 14. Ví dụ triển khai: luồng đặt thuê serverless

Giả sử ứng dụng cần nhận yêu cầu đặt thuê, giữ tài sản, xử lý thanh toán, phát thông báo và cập nhật báo cáo.

~~~mermaid
flowchart TB
    U["Web / Mobile"] --> API["API Gateway"]
    API --> CREATE["CreateBooking"]
    CREATE --> DB[("Booking DB")]
    CREATE --> Q["Booking workflow / queue"]
    Q --> RESERVE["ReserveInventory"]
    RESERVE --> PAY["RequestPayment"]
    PAY --> PSP["Payment provider"]
    PSP --> WEBHOOK["PaymentCallback"]
    WEBHOOK --> EVT["Event bus: BookingConfirmed"]
    EVT --> N["SendNotification"]
    EVT --> R["UpdateReport"]
    TIMER["Scheduler: reservation expiry"] --> EXPIRE["ExpireReservation"]
~~~

| Function | Trigger | Phản hồi | Quyền chính | Deployment unit gợi ý |
| --- | --- | --- | --- | --- |
| CreateBooking | HTTP/API | Đồng bộ | Tạo booking, đọc thông tin khách cần thiết | booking-api |
| ReserveInventory | Workflow/queue | Bất đồng bộ hoặc workflow step | Đọc/ghi inventory reservation | inventory-reservation |
| RequestPayment | Workflow/queue | Bất đồng bộ | Gọi payment provider, lấy credential liên quan | payment-request |
| PaymentCallback | HTTP/webhook | Xác nhận tiếp nhận | Verify webhook, cập nhật payment state | payment-callback |
| SendNotification | Event bus/queue | Bất đồng bộ | Gửi email/SMS | notification-worker |
| UpdateReport | Event/stream/schedule | Bất đồng bộ | Ghi read model/reporting store | reporting-worker |
| ExpireReservation | Scheduler/queue | Bất đồng bộ | Kiểm tra và giải phóng giữ chỗ | reservation-expiry |

Tên deployment unit chỉ là gợi ý. PaymentRequest và PaymentCallback có thể được triển khai riêng do khác trigger và bề mặt tấn công, dù cùng owner. Nếu một function dùng quyền thanh toán nhạy cảm, không nên gộp với notification để tiện chia sẻ role.

### 14.1. Xử lý lỗi tại từng bước

| Bước | Lỗi | Hành vi đề xuất |
| --- | --- | --- |
| CreateBooking | Client gửi lặp do timeout | Idempotency key để trả cùng kết quả |
| ReserveInventory | Không còn tài sản trống | Từ chối nghiệp vụ, không retry vô hạn |
| RequestPayment | Timeout provider, chưa rõ giao dịch thành công | Tra cứu/reconcile theo provider reference trước khi gửi lại |
| PaymentCallback | Webhook trùng | Verify chữ ký, dedup event/reference |
| SendNotification | Provider tạm lỗi | Retry có giới hạn, DLQ; không đổi trạng thái thanh toán |
| UpdateReport | Consumer lag hoặc message trùng | Idempotent update, theo dõi lag và replay |
| ExpireReservation | Scheduler chạy hai lần | Kiểm tra trạng thái và expiry trước khi giải phóng |

Tách function không tự xử lý những lỗi trên. Chúng phải được mô hình hóa trong contract, lưu trạng thái và chính sách retry.

## 15. Khi nào dùng workflow?

Có thể điều phối bằng code trong một function, nhưng quy trình kéo dài thường khó theo dõi nếu trạng thái chỉ nằm trong bộ nhớ hoặc code flow. Workflow/state machine phù hợp khi cần chờ callback lâu, retry khác nhau theo từng bước, timeout và nhánh điều kiện, parallel fan-out/join, compensation, audit trạng thái và thay đổi flow có kiểm soát.

Workflow cũng có chi phí, giới hạn state/payload và semantics retry riêng. Không đưa dữ liệu lớn vào state history nếu có thể lưu ở storage và chỉ truyền reference. Chọn workflow theo nhu cầu điều phối, không chỉ vì sơ đồ trông serverless hơn.

## 16. Kiểm thử và bảo vệ ranh giới

Kiểm thử serverless cần bao gồm handler logic, trigger contract và semantics nền tảng.

- **Unit test:** nghiệp vụ, validation, transition và idempotency logic.
- **Contract test:** HTTP schema, event schema, version compatibility và lỗi đầu vào.
- **Integration test:** queue, database, secret manager, event bus, webhook và quyền.
- **Trigger test:** batch size, duplicate, retry, timeout, ordering và scheduler overlap.
- **Failure test:** dependency unavailable, throttling, DLQ, malformed event và timeout sau side effect.
- **Load test:** concurrency burst, cold start, downstream saturation và queue lag.
- **Security test:** IAM quá rộng, giả mạo webhook, tenant boundary, secret leakage và truy cập trái phép.

Emulator/local test hữu ích cho logic nhưng không thay thế kiểm thử trên nền tảng thật đối với retry, timeout, concurrency, visibility và IAM enforcement. Các khác biệt phải được xác minh ở staging tương đương.

Function có thể tái sử dụng thư viện kiểm tra schema, domain logic hoặc tracing, nhưng shared library lớn có thể khiến thay đổi nhỏ buộc triển khai hàng loạt function. Nên chia sẻ logic ổn định, có semantic version và contract rõ; không chia sẻ execution role chỉ để giảm cấu hình.

## 17. Quy trình thiết kế từ yêu cầu tới phát hành

1. **Phân rã use case:** xác định hành động, sự kiện, invariant, dữ liệu và kết quả cần trả về.
2. **Xác định trigger:** client cần chờ hay có thể nhận job ID? Có queue, event, timer hoặc workflow phù hợp?
3. **Chia function:** chọn đơn vị logic có mục đích, contract và lỗi rõ.
4. **Chọn deployment unit:** đánh giá runtime, IAM, scale, owner, release cadence, blast radius và dependency.
5. **Thiết kế event semantics:** schema, event ID, ordering, retry, dedup, retention và DLQ.
6. **Định nghĩa trạng thái nghiệp vụ:** phân biệt accepted, processing, succeeded, failed, expired và cần xử lý thủ công.
7. **Thiết kế bảo mật:** execution role, trigger permission, secret, network, data access và audit.
8. **Định cỡ vận hành:** timeout, memory, concurrency, batch, queue, quota và downstream capacity.
9. **Tạo IaC/CI/CD:** build, scan, test, publish version, rollout và rollback.
10. **Đo outcome:** trace end-to-end, error budget, latency, backlog, cost và tỷ lệ xử lý hoàn tất.
11. **Review và điều chỉnh:** gộp/tách deployment unit khi có dữ liệu chứng minh lợi ích.

## 18. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Một function làm cả quy trình lớn | Quyền rộng, timeout, retry lặp nhiều side effect | Chia theo thao tác nghiệp vụ và workflow |
| Một function cho mỗi helper method | Nhiều hop, invocation, IAM và pipeline | Chỉ tách khi có ranh giới nghiệp vụ/vận hành |
| Đồng bộ mọi bước | Caller chờ lâu, timeout dây chuyền | Queue/event cho việc xử lý sau |
| Trả 202 khi message chưa bền vững | Client tưởng job đã được nhận nhưng job mất | Xác nhận theo semantics và durability |
| Giả định exactly-once | Duplicate gây thu tiền/gửi thông báo hai lần | Idempotency và reconciliation |
| Retry mọi lỗi | Retry storm và chi phí tăng | Phân loại lỗi, backoff, max attempts, DLQ |
| Không có event schema version | Producer đổi payload làm consumer lỗi | Contract/versioning và rollout tương thích |
| Dùng chung IAM role quá rộng | Function bị xâm nhập có quyền của function khác | Least privilege theo function/unit |
| Gộp function có SLO/quyền khác nhau | Blast radius và rollout không phù hợp | Tách deployment boundary có chủ đích |
| Tách mọi function thành pipeline riêng | Gánh nặng phát hành và vận hành | Nhóm unit theo owner, runtime và vòng đời |
| Không theo dõi queue age/DLQ | Message kẹt nhưng API vẫn khỏe | Metric và alert theo outcome |
| Không giới hạn concurrency | Downstream bị quá tải | Function concurrency, queue và DB capacity |
| Lưu payload/secret trong log | Rò rỉ dữ liệu | Data minimization, masking và retention |
| Không thiết kế callback trùng/đến muộn | Trạng thái nghiệp vụ không nhất quán | Dedup, version, transition và reconciliation |

## 19. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi cần trả lời |
| --- | --- |
| **Độ tin cậy** | Retry và timeout có an toàn? Event có thể mất/trùng? DLQ và replay có quy trình? Workflow có recovery/compensation? |
| **Bảo mật** | Mỗi function có quyền tối thiểu? Trigger có auth? Event/secret/log có làm lộ dữ liệu? Deployment unit có blast radius rõ? |
| **Hiệu quả hiệu năng** | Cold start, latency p95/p99, concurrency, batch và downstream capacity có đạt SLO? |
| **Tối ưu chi phí** | Tính cả invocation, compute, queue, workflow, API, log và transfer? Việc tách nhỏ có tăng tổng cost không? |
| **Khả năng vận hành** | Có trace từ request tới consumer? Có version, owner, alert, rollout/rollback và DLQ runbook? |

### Checklist nghiệm thu

- [ ] Mỗi function có mục đích, contract, owner và failure behavior rõ.
- [ ] Trigger phù hợp với nhu cầu synchronous/asynchronous và semantics được kiểm chứng.
- [ ] Event có ID, schema version, timestamp/correlation và payload tối thiểu.
- [ ] Consumer idempotent; duplicate, retry, timeout và ordering có quy tắc.
- [ ] DLQ có retention, alert, owner và quy trình replay.
- [ ] Deployment unit được chọn theo quyền, scaling, release cadence và blast radius.
- [ ] Execution identity tuân thủ least privilege; secrets không nằm trong artifact/payload/log.
- [ ] Timeout, memory, concurrency và downstream quota được load test.
- [ ] Workflow có trạng thái, retry, timeout và compensation phù hợp.
- [ ] IaC/CI/CD quản lý version, trigger binding, rollout và rollback.
- [ ] Trace/correlation cho phép theo dõi toàn bộ luồng nghiệp vụ.
- [ ] SLO và TCO được đo ở cấp use case, không chỉ từng function.

## 20. Bài tập áp dụng

Một ứng dụng bán vé có luồng nghiệp vụ: nhận yêu cầu đặt vé, giữ chỗ 5 phút, thanh toán qua đối tác, gửi email xác nhận và cập nhật báo cáo doanh thu. Webhook thanh toán đôi khi đến trùng; email provider có thể gián đoạn vài phút; báo cáo có thể chậm tối đa 15 phút.

Hãy thiết kế:

1. Các function cần có và trách nhiệm từng function.
2. Trigger của từng function: HTTP, queue, event bus hay scheduler.
3. Bước nào phải đồng bộ để phản hồi người dùng và bước nào có thể chạy sau.
4. Event contract khi thanh toán hoàn tất; idempotency key nào xử lý webhook trùng?
5. Deployment unit và IAM role nào cần tách để giảm quyền và blast radius?
6. Chính sách retry, DLQ và replay cho email, báo cáo và payment callback.
7. Chỉ số chứng minh luồng đặt vé hoàn tất đúng và trong SLO.

Một phương án hợp lý có thể trả ngay mã booking ở trạng thái PENDING_PAYMENT, dùng workflow quản lý timeout/giữ chỗ, xử lý webhook idempotent, phát event sau commit, rồi để email và báo cáo chạy bất đồng bộ. Điều quan trọng là phân biệt rõ **đã nhận yêu cầu**, **đã giữ chỗ**, **đã thanh toán** và **đã xác nhận vé**.

**Điểm cốt lõi:** phân chia function quyết định công việc nào có logic và trách nhiệm riêng; trigger xác định công việc bắt đầu khi nào và với semantics giao nhận nào; deployment unit quyết định cách phát hành, cấp quyền, mở rộng và khoanh vùng lỗi. Ba quyết định cần được thiết kế cùng nhau từ hợp đồng nghiệp vụ, dữ liệu và trạng thái, để hệ thống serverless đạt tốc độ phát triển mà vẫn giữ độ tin cậy, bảo mật, hiệu năng, chi phí và khả năng vận hành có thể kiểm chứng.
