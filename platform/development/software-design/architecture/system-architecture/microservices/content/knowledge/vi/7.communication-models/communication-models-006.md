# Quyền sở hữu thời hạn xử lý và kết quả cuối cùng

## 1. Vấn đề cốt lõi trong giao tiếp phân tán

Trong hệ thống microservices, một lời gọi không chỉ có câu hỏi “dịch vụ nào thực hiện việc này?” mà còn có hai câu hỏi quan trọng hơn:

1. **Ai quyết định người gọi được chờ bao lâu?**
2. **Ai chịu trách nhiệm xác định và lưu lại kết quả nghiệp vụ cuối cùng, kể cả khi người gọi đã ngừng chờ?**

Hai trách nhiệm này liên quan nhưng **không đồng nhất**. Một HTTP client có thể đặt request timeout 800 ms, trong khi quy trình thanh toán có thể cần nhiều giây hoặc nhiều phút để có kết quả cuối từ nhà cung cấp. Việc client ngừng chờ sau 800 ms không tự động hủy một giao dịch thanh toán đã được gửi hoặc đã được xử lý.

Ví dụ, Order Service yêu cầu Payment Service thu tiền. Sau 1 giây, Order nhận timeout. Có ít nhất bốn khả năng:

- Payment chưa nhận request.
- Payment đã nhận nhưng chưa xử lý.
- Payment đã gửi lệnh sang cổng thanh toán; kết quả còn đang chờ.
- Payment đã lưu kết quả thành công, nhưng phản hồi bị chậm hoặc mất trên mạng.

Từ góc nhìn Order, cả bốn trường hợp có thể tạo cùng một lỗi timeout. Vì vậy **timeout là kết quả của việc chờ, không nhất thiết là kết quả của nghiệp vụ**.

Một thiết kế giao tiếp đáng tin cậy phải phân định rành mạch:

- **Deadline owner:** thành phần đặt giới hạn thời gian và quyết định khi nào ngừng chờ hoặc ngừng công việc.
- **Operation owner:** thành phần chịu trách nhiệm nhận diện, thực hiện và lưu trạng thái một thao tác.
- **Final outcome owner:** thành phần có thẩm quyền ghi nhận và cung cấp trạng thái kết thúc của quy trình nghiệp vụ.
- **Recovery owner:** thành phần tiếp tục kiểm tra, retry, đối soát hoặc bù trừ khi kết quả chưa xác định.

Một thành phần có thể đóng nhiều vai trò, nhưng không được để công việc “trôi nổi” vì mỗi service tưởng service khác sẽ chịu trách nhiệm.

## 2. Phân biệt bốn loại thời gian thường bị đánh đồng

| Loại thời gian | Câu hỏi trả lời | Ví dụ | Ai thường quyết định |
| --- | --- | --- | --- |
| Request timeout | Người gọi chờ một lần trao đổi trong bao lâu? | HTTP client chờ Payment 900 ms | Caller, trong giới hạn chính sách hệ thống |
| End-to-end deadline | Toàn bộ thao tác đồng bộ còn bao nhiêu thời gian hữu ích? | Checkout API phải phản hồi trong 2 giây | Điểm khởi tạo request hoặc ứng dụng điều phối |
| Business expiration | Đối tượng nghiệp vụ còn hiệu lực đến lúc nào? | Giữ hàng hết hạn sau 15 phút | Dịch vụ sở hữu quy tắc nghiệp vụ |
| Workflow completion deadline | Quy trình có bao lâu để đi tới kết quả cuối hoặc trạng thái cần xử lý ngoại lệ? | Đối soát thanh toán trong một khoảng đã cam kết | Workflow/process owner và chính sách nghiệp vụ |

Các con số trên chỉ minh họa. Không có timeout hoặc TTL mặc định đúng cho mọi hệ thống.

### 2.1. Request timeout không đồng nghĩa business expiration

Giả sử khách hàng nhấn “Đặt hàng” và trình duyệt chờ tối đa 5 giây. Khoảng chờ này phục vụ trải nghiệm người dùng. Nếu giữ hàng có hạn 15 phút thì đây là **quy tắc nghiệp vụ về tồn kho**, không có lý do phải bằng 5 giây.

Tương tự, nếu thanh toán cần đối soát trong 10 phút, kết thúc HTTP request sau 5 giây **không** xóa nghĩa vụ đối soát 10 phút.

Một lỗi phổ biến là dùng thời điểm HTTP timeout để chuyển thẳng đơn sang FAILED, trong khi Payment hoặc Inventory có thể đã hoàn thành. Điều này khiến trạng thái đơn và thế giới bên ngoài mâu thuẫn.

### 2.2. Deadline không đồng nghĩa timeout ở từng tầng

Một request thường đi qua nhiều lớp:

~~~text
Client -> Gateway -> Order -> Payment -> Payment Provider
          1.8 s      1.4 s    0.9 s
~~~

Nếu mỗi lớp cấp lại toàn bộ 2 giây cho downstream, tác vụ có thể chạy lâu hơn nhiều so với hạn chờ ban đầu và làm lãng phí tài nguyên. **Deadline tổng** nên được truyền hoặc được tính lại thành **remaining budget**, có tính đến validation, queueing, serialization và chi phí nội bộ.

Một connection timeout chỉ giới hạn thời gian kết nối. Một read timeout ở thư viện cụ thể có thể giới hạn khoảng chờ dữ liệu, không nhất thiết bao trùm toàn bộ request. Khi thiết kế phải biết chính xác semantics của API client.

### 2.3. Clock time, duration và sai lệch đồng hồ

Deadline có thể được biểu diễn dưới dạng **thời điểm tuyệt đối** hoặc **thời lượng còn lại**. Hai lựa chọn đều có rủi ro:

- Thời điểm tuyệt đối cần xem xét đồng hồ các máy có thể lệch nhau.
- Thời lượng còn lại phải trừ thời gian đã tiêu hao khi qua gateway, queue và service.
- Thời gian lưu trong database thường cần timestamp đáng tin cậy, timezone thống nhất và quy tắc so sánh nhất quán.
- Timeout trong tiến trình nên dựa vào đồng hồ monotonic nếu runtime cung cấp, để thay đổi đồng hồ hệ thống không làm phép đo duration sai.

Đừng tin hoàn toàn deadline do client bên ngoài tự đưa ra: nó có thể yêu cầu thời hạn quá dài hoặc thay đổi header nhằm chiếm tài nguyên. Server phải áp dụng **giới hạn trên do hệ thống kiểm soát**.

## 3. Ai sở hữu từng trách nhiệm?

Một cách phân công thực dụng:

| Thành phần | Trách nhiệm phù hợp | Không nên mặc định |
| --- | --- | --- |
| Browser/mobile | Chọn thời gian chờ giao diện; lưu operationId; truy vấn lại khi cần | Đóng tab là đã hủy giao dịch |
| API Gateway/BFF | Giới hạn tài nguyên ở biên; xác thực; truyền deadline và correlation context | Gateway timeout là kết quả nghiệp vụ cuối |
| Caller service | Đặt timeout/retry budget cho lời gọi, xử lý lỗi/unknown theo contract | Có quyền tự phán quyết thao tác của service khác chưa chạy |
| Service sở hữu thao tác | Thực thi và lưu trạng thái operation, chống thực hiện trùng, cung cấp status | Trả response thành công là hoàn tất mọi tác vụ downstream |
| Saga/workflow coordinator | Duy trì trạng thái toàn workflow, lên lịch bước tiếp theo/bù trừ, quyết định chuyển trạng thái đã được định nghĩa | Dùng thread HTTP làm nơi duy nhất giữ tiến độ |
| Database/broker | Lưu bền dữ liệu và chuyển thông điệp theo hợp đồng riêng | Tự quyết định đơn hàng có được xác nhận hay không |
| Job đối soát | Tìm các trường hợp pending quá hạn và đưa chúng tới trạng thái rõ hoặc hàng chờ xử lý | Tự ý ghi FAILED khi chưa biết kết quả tiền thật |
| Đội vận hành | Quan sát SLO, xử lý ngoại lệ, sửa sự cố và kiểm toán | Bù đắp cho việc hệ thống không có owner của trạng thái |

Ví dụ trong nền tảng bán hàng:

- **Payment Service** sở hữu kết quả của một payment attempt và tương tác với nhà cung cấp thanh toán.
- **Inventory Service** sở hữu kết quả giữ hàng, giải phóng giữ hàng và quy tắc tồn kho.
- **Order Service** hoặc một workflow coordinator được chỉ định sở hữu **trạng thái cuối của đơn hàng** dựa trên các kết quả được xác minh.
- **Gateway** sở hữu cách trả lời cho client trong thời gian HTTP được cho phép.

Không nên đặt tất cả “owner” thành một khái niệm chung. Sở hữu kết quả thanh toán khác với sở hữu kết quả đặt hàng.

## 4. Quyền sở hữu dữ liệu là nền tảng của quyền quyết định kết quả

Muốn xác định đúng kết quả cuối cùng, cần xác định **nguồn sự thật có thẩm quyền** (*source of truth*) của từng trạng thái:

- Order Service quyết định đơn ở PENDING, CONFIRMED, CANCELLED hay FAILED theo state machine của đơn.
- Payment Service quyết định một payment attempt đã được xác minh là SUCCEEDED, FAILED hay còn UNKNOWN/PENDING.
- Inventory Service quyết định reservation còn ACTIVE, RELEASED hay EXPIRED.
- Các service khác nhận thông tin qua API hoặc event thay vì tùy tiện cập nhật bảng dữ liệu của chủ sở hữu.

Ví dụ Payment báo SUCCEEDED chưa tự động đồng nghĩa Order được CONFIRMED. Order vẫn cần xem điều kiện giữ hàng, hạn nghiệp vụ và các bất biến khác. Ngược lại, nếu Order đã hết hạn, sự kiện payment success đến muộn có thể làm phát sinh yêu cầu **hoàn tiền hoặc xử lý ngoại lệ**, không nhất thiết lật ngược quyết định đã đóng.

**Không có một “trạng thái cuối chung” áp dụng cho mọi aggregate.** Hệ thống phải định nghĩa rõ kết quả cuối của từng thao tác và cách kết quả đó đóng góp vào quy trình lớn hơn.

### 4.1. Người quyết định và người thông báo

Service sở hữu kết quả có thể phát event, ví dụ:

~~~json
{
  "eventId": "evt-pay-102",
  "eventType": "PaymentSucceeded",
  "schemaVersion": 1,
  "paymentId": "pay-8421-1",
  "orderId": "8421",
  "occurredAt": "2026-11-11T10:45:00Z"
}
~~~

Event cho biết Payment đã ghi nhận điều gì theo contract của nó. Order nhận event rồi kiểm tra trạng thái đơn và áp dụng quy tắc chuyển trạng thái. **Event không nên là mệnh lệnh buộc mọi consumer sửa dữ liệu bất chấp trạng thái hiện tại.**

Để tránh cập nhật sai, các dịch vụ có thể dùng version, expected-state check, unique constraint, optimistic locking và idempotent event handling.

## 5. Phân biệt “đã tiếp nhận”, “đang xử lý” và “đã hoàn tất”

Một hợp đồng giao tiếp nên phân biệt ít nhất ba kết quả:

1. **Accepted:** yêu cầu hợp lệ đã được hệ thống nhận và lưu đủ bền để tiếp tục; công việc có thể chưa hoàn tất.
2. **In progress / pending:** hệ thống đang xử lý hoặc chờ kết quả từ bên ngoài, và có cách theo dõi.
3. **Terminal outcome:** kết quả cuối theo state machine đã được xác định và ghi bền; ví dụ SUCCEEDED, FAILED hoặc CANCELLED theo nghĩa nghiệp vụ cụ thể.

Không được trả “thanh toán thành công” chỉ vì đã đưa message vào queue. Không được coi một request timeout là “đơn hàng thất bại” nếu một giao dịch thực sự có thể đã commit.

### 5.1. HTTP 200/201/202 nên được hiểu theo contract

- **200 OK** có thể chứa trạng thái hiện tại; ý nghĩa “đã hoàn tất” hay “đang xử lý” nằm ở response contract.
- **201 Created** thường xác nhận một resource được tạo; resource đó có thể vẫn có workflow riêng đang chạy.
- **202 Accepted** phù hợp khi yêu cầu đã được tiếp nhận để xử lý sau, kết quả cuối chưa có. Nên trả operationId và đường dẫn theo dõi trạng thái.
- **4xx/5xx** mô tả trạng thái xử lý HTTP theo contract; không thể tự suy ra side effect ở tất cả dependency có hay chưa.

Ví dụ giao diện gửi yêu cầu checkout:

~~~http
POST /v1/orders
Idempotency-Key: checkout-session-321
Content-Type: application/json

{
  "cartId": "cart-321",
  "paymentMethodId": "pm-token-7"
}
~~~

Khi quy trình chưa kết thúc nhưng đã được lưu an toàn, một phản hồi có thể là:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/order-operations/op-8421
Retry-After: 2
Content-Type: application/json

{
  "operationId": "op-8421",
  "orderId": "8421",
  "status": "PENDING",
  "statusUrl": "/v1/order-operations/op-8421"
}
~~~

Cách dùng header và response cụ thể phải tuân theo contract sản phẩm. Retry-After chỉ là gợi ý thời gian kiểm tra lại khi phù hợp; hệ thống cần giới hạn tần suất polling.

Khi client gọi trạng thái:

~~~http
GET /v1/order-operations/op-8421
~~~

Ví dụ kết quả:

~~~json
{
  "operationId": "op-8421",
  "orderId": "8421",
  "status": "CONFIRMED",
  "terminal": true,
  "completedAt": "2026-11-11T10:46:20Z"
}
~~~

Ở đây, service sở hữu operation đảm bảo ý nghĩa của **terminal=true**. Đừng chỉ dựa vào một chuỗi trạng thái ở UI mà không có quy tắc nghiệp vụ và lưu trữ phía server.

## 6. Thiết kế state machine để không bỏ rơi kết quả

Một quy trình không nên chỉ có SUCCESS/FAILURE nếu nhiều bước phân tán có thể hoàn thành muộn.

Ví dụ state machine đơn hàng:

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> RESERVING
    RESERVING --> AWAITING_PAYMENT: Đã giữ hàng
    RESERVING --> REJECTED: Hết hàng
    AWAITING_PAYMENT --> CONFIRMED: Payment thành công, đơn hợp lệ
    AWAITING_PAYMENT --> CANCEL_REQUESTED: Hết hạn/khách hủy
    CANCEL_REQUESTED --> CANCELLED: Bù trừ xong
    AWAITING_PAYMENT --> FAILED: Payment thất bại rõ
    CANCEL_REQUESTED --> NEEDS_RECONCILIATION: Trạng thái chưa rõ
    NEEDS_RECONCILIATION --> CANCELLED: Đối soát và bù trừ xong
    NEEDS_RECONCILIATION --> CONFIRMED: Kết quả hợp lệ theo chính sách
    CONFIRMED --> [*]
    CANCELLED --> [*]
    REJECTED --> [*]
    FAILED --> [*]
~~~

Đây là một ví dụ để học, không phải state machine bắt buộc. Trạng thái, điều kiện chuyển và xử lý payment đến muộn phải được chốt theo nghiệp vụ thực tế.

### 6.1. “Cuối cùng” nghĩa là gì?

**Terminal state** thường có nghĩa workflow đã đạt một kết cục được định nghĩa và không tiếp tục chuyển theo đường xử lý thông thường. Tuy nhiên, thế giới thực có thể phát sinh hoàn tiền, chargeback, giao hàng trả lại hoặc lỗi phát hiện sau đó.

Thay vì sửa ngược một giao dịch lịch sử từ SUCCEEDED thành “chưa từng thành công”, một mô hình có thể ghi **sự kiện bù trừ riêng** như REFUND_SUCCEEDED và giữ lịch sử kiểm toán. Cách mô hình hóa chi tiết phải theo quy tắc kế toán và sản phẩm.

### 6.2. Chuyển trạng thái phải được bảo vệ

Khi callback, poller, retry worker và timeout handler có thể chạy đồng thời, cần:

- Một nguồn dữ liệu lưu state có quyền sở hữu rõ.
- Transition hợp lệ theo **trạng thái hiện tại**, không theo thứ tự message đến.
- Idempotency cho event/command lặp.
- Version hoặc optimistic locking để ngăn hai handler ghi đè lẫn nhau.
- Ghi audit gồm operationId, nguyên nhân, actor, timestamp.
- Cơ chế xử lý sự kiện đến muộn, kể cả sau terminal state.

Ví dụ, một timeout handler không được chuyển đơn sang FAILED chỉ vì nó chạy muộn hơn callback PaymentSucceeded đã xác nhận thành công.

## 7. Phân bổ deadline theo chuỗi gọi

Giả sử hệ thống cam kết trả phản hồi API trong 1.500 ms tại một mức tải đã định. Có thể lập ngân sách minh họa:

| Bước trong critical path | Ngân sách |
| --- | ---: |
| Gateway và xác thực | 100 ms |
| Order validate và lưu trạng thái | 160 ms |
| Inventory reserve | 300 ms |
| Payment init | 500 ms |
| Network, serialization, dư địa | 240 ms |
| Đệm an toàn và phản hồi | 200 ms |
| **Tổng** | **1.500 ms** |

Đây là ngân sách giả định, không phải SLO chuẩn. Nếu thanh toán cần lâu hơn, Order có thể trả **202 + operationId** và tiếp tục xử lý bền vững thay vì chờ vượt hạn. Phải diễn đạt rõ người dùng đang thấy đơn **được tiếp nhận** hay đơn **đã xác nhận**.

### 7.1. Quy tắc phân chia giữa caller và callee

**Caller** quyết định nó có bao lâu để đợi và bao nhiêu tài nguyên chờ một lần gọi. **Callee** quyết định cách xử lý yêu cầu trong giới hạn năng lực và contract của nó. Nếu callee không thể hoàn tất trong deadline, nó có thể:

- Từ chối ngay nếu yêu cầu sẽ không còn giá trị và chưa gây side effect.
- Nhận yêu cầu rồi cấp **operationId** theo một hợp đồng bất đồng bộ rõ.
- Trả trạng thái hiện tại cùng cách tra cứu và deadline nghiệp vụ.
- Hủy phần công việc có thể hủy an toàn, nhưng giữ nghĩa vụ đối soát các side effect đã xảy ra.

Caller không được dùng timeout của nó như lệnh trực tiếp xóa state nghiệp vụ mà callee sở hữu. Callee cũng không nên giữ vô hạn request đồng bộ khi có thể chủ động từ chối, queue bền vững hoặc báo pending.

### 7.2. Deadline propagation và quyền đặt giới hạn

Trong gRPC có thể truyền deadline và cancellation metadata. Với REST có thể dùng timeout ở client và metadata về thời gian còn lại trong nội bộ tin cậy. Một quy tắc thực dụng:

~~~text
effectiveDeadline = min(
    upstreamDeadline,
    localMaximumDeadline,
    businessCutoffIfApplicable
)
~~~

Nếu downstream không nhận được deadline hợp lệ, phải dùng giới hạn nội bộ an toàn. Ở mỗi tầng cần trừ thời gian đã tiêu hao. Không cho một header bên ngoài kéo dài thời gian làm việc vô hạn.

Không cần biến mọi message bất đồng bộ thành request có deadline bằng thời gian chờ HTTP. Workflow bền vững có lịch hết hạn và cơ chế xử lý chậm riêng.

## 8. Ai sở hữu quyền hủy?

**Cancel request** và **cancel completed** là hai sự kiện khác nhau.

- Người dùng nhấn “Hủy” có thể là **ý định hủy**, chưa phải xác nhận toàn bộ side effect đã được bù trừ.
- Caller timeout có thể ngừng chờ response, nhưng work ở callee đã commit không tự bị xóa.
- Nếu một bước chưa bắt đầu, hệ thống thường có thể ngừng.
- Nếu đã gọi provider bên ngoài, phải làm rõ provider có hỗ trợ cancel hay cần refund/compensation.
- Nếu Order đã CONFIRMED và đã vận chuyển, “hủy đơn” có thể trở thành một quy trình hoàn trả khác.

Một API an toàn có thể trả:

~~~json
{
  "orderId": "8421",
  "status": "CANCEL_REQUESTED",
  "terminal": false,
  "message": "Yêu cầu hủy đã được tiếp nhận và đang xử lý"
}
~~~

Khi đã hoàn tất các bước cần thiết, Order mới trả CANCELLED theo định nghĩa của domain. Tránh hiển thị “Đã hủy hoàn toàn” trong lúc tiền vẫn chưa được hoàn hoặc hàng vẫn đang giữ mà không giải thích trạng thái.

### 8.1. Cancellation và race condition

Giả sử hai tiến trình chạy gần nhau:

~~~text
T1: Payment callback báo thành công
T2: Timer thấy đơn quá hạn, đề nghị hủy
T3: Handler callback và timer cùng đọc PENDING
T4: Cả hai muốn ghi trạng thái mới
~~~

Nếu dùng cập nhật không có điều kiện, hai handler có thể ghi đè nhau. Một thiết kế cần **compare-and-set trên version/state**, kiểm tra invariant và quyết định xử lý trường hợp đến muộn.

Một transition thất bại vì version thay đổi không nhất thiết là lỗi hệ thống: handler nên nạp state mới và đánh giá lại quy tắc thay vì ghi đè cưỡng bức.

## 9. Kết quả cuối phải có người chịu trách nhiệm

Một quy trình thường đi qua nhiều service. Nếu mỗi bên chỉ “fire and forget” rồi quên, các hoạt động chưa kết thúc có thể tồn tại vô hạn.

Có hai cách tổ chức phổ biến:

**Orchestration:** một workflow coordinator giữ trạng thái toàn quy trình và chỉ đạo các bước. Ví dụ Order Process Manager yêu cầu giữ hàng, khởi tạo thanh toán, theo dõi kết quả, thực hiện bù trừ và chốt đơn. Nó chịu trách nhiệm cho workflow cuối, còn từng service vẫn sở hữu giao dịch riêng.

**Choreography:** các dịch vụ phản ứng theo event. Ví dụ InventoryReserved dẫn tới PaymentRequested, PaymentSucceeded dẫn tới OrderConfirmed. Không nhất thiết có coordinator điều khiển mọi bước, nhưng **vẫn phải chỉ định rõ thành phần chịu trách nhiệm cho trạng thái cuối và quy trình xử lý khi thiếu event**.

Choreography không có nghĩa không cần owner. Nếu một event bị lỗi hoặc tới muộn, cần có nơi biết order nào đang treo, ai xử lý, và ai có quyền quyết định kết cục.

### 9.1. Workflow owner và step owner

| Phạm vi | Step owner | Workflow owner |
| --- | --- | --- |
| Giữ hàng | Inventory Service | Order/Saga theo dõi kết quả để đi tiếp |
| Thu tiền | Payment Service | Order/Saga chờ hoặc đối soát trước khi chốt đơn |
| Gửi email | Notification Service | Workflow có thể không cần chờ email để chốt đơn |
| Chốt đơn | Order Service | Order hoặc coordinator được ủy quyền |
| Hoàn tiền | Payment Service | Order/Returns workflow theo dõi hoàn tất chính sách |
| Khôi phục Pending | Mỗi service xử lý phần mình sở hữu | Workflow owner tìm và xử lý mọi operation còn mở |

Cần xác nhận nghiệp vụ nào **bắt buộc** cho terminal state. Ví dụ một lỗi gửi email không nên làm thay đổi sự thật rằng tiền đã thu và đơn đã xác nhận.

### 9.2. Quy trình không nên sống chỉ trong một HTTP request

Nếu coordinator lưu tiến độ duy nhất trong RAM hoặc trên call stack của thread HTTP, một lần restart có thể làm mất trạng thái và bỏ dở công việc. Với workflow kéo dài hoặc có side effect:

- Lưu **operationId và state** bền vững.
- Ghi bước đã hoàn tất và kết quả đã xác minh.
- Có timer/job scheduler đáng tin để kiểm tra quá hạn.
- Có cơ chế tái chạy idempotent sau restart.
- Lưu dữ kiện đủ để tra cứu, đối soát và bù trừ.
- Có chính sách giữ dữ liệu và audit phù hợp.

Đây là phần phân biệt một API “đã nhận việc” với một hệ thống thật sự **chịu trách nhiệm hoàn thành hoặc xử lý ngoại lệ**.

## 10. Ví dụ xuyên suốt: tạo đơn, giữ hàng và thanh toán

Giả định khách đặt đơn 8421, cần giữ hàng và thanh toán. Hệ thống có Client, Gateway, Order, Inventory, Payment và nhà cung cấp thanh toán.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant G as Gateway
    participant O as Order/Workflow Owner
    participant I as Inventory
    participant P as Payment
    participant X as Payment Provider
    U->>G: POST /orders, idempotencyKey
    G->>O: Submit order (remaining deadline)
    O->>O: Persist order PENDING + operationId
    O->>I: Reserve(orderId, reservationKey)
    I-->>O: Reservation ACTIVE
    O->>P: Authorize(paymentId, paymentKey)
    P->>X: Request payment
    Note over U,O: HTTP deadline có thể hết trong khi Payment còn xử lý
    O-->>G: ACCEPTED + status URL
    G-->>U: 202 PENDING
    X-->>P: Provider result
    P->>P: Persist payment outcome
    P-->>O: PaymentSucceeded event
    O->>O: Verify inventory and transition CONFIRMED
    U->>O: GET /operations/{operationId}
    O-->>U: CONFIRMED (terminal)
~~~

Trong sơ đồ, bước trả 202 phụ thuộc vào deadline và tiến độ thực tế, không bắt buộc lúc nào cũng xảy ra. Nếu kết quả cuối có ngay trong thời gian cho phép, API có thể trả kết quả cuối theo contract.

### 10.1. Những định danh phải phân biệt

| Định danh | Mục đích | Phạm vi gợi ý |
| --- | --- | --- |
| orderId | Danh tính đơn hàng nghiệp vụ | Xuyên vòng đời đơn |
| operationId | Danh tính một yêu cầu/quy trình theo dõi | Xuyên retry, polling và recovery |
| paymentId | Danh tính payment attempt hoặc payment intent | Payment Service và provider |
| reservationId | Danh tính giữ hàng | Inventory Service |
| idempotencyKey | Ngăn tác dụng trùng của cùng yêu cầu | Theo contract của từng operation |
| traceId | Nối spans để chẩn đoán | Theo chuỗi kỹ thuật được instrument |
| eventId | Chống xử lý trùng event và phục vụ kiểm toán | Broker/consumer và storage |

**traceId không thay cho idempotencyKey.** Một workflow có thể trải qua nhiều request, retry và scheduled job, mỗi lần có trace khác nhau nhưng cùng operationId.

### 10.2. Nhánh thành công

1. Order lưu đơn PENDING cùng operationId.
2. Inventory xác nhận reservationId.
3. Payment xác minh giao dịch và lưu kết quả SUCCEEDED.
4. Order nhận kết quả đáng tin, kiểm tra trạng thái và điều kiện nghiệp vụ.
5. Order chuyển CONFIRMED trong transaction của mình và phát event cần thiết.
6. Client truy vấn hoặc nhận thông báo và thấy terminal outcome.

Từng service quyết định trạng thái cục bộ; Order sở hữu terminal outcome của **đơn hàng**.

### 10.3. Nhánh timeout ngay sau khi Payment xử lý

1. Order gọi Payment với paymentId cố định.
2. Payment ghi kết quả thanh toán thành công.
3. Network bị ngắt trước khi Order nhận response.
4. Order hết deadline chờ.
5. Order ghi trạng thái chờ xác minh, trả PENDING hoặc trạng thái rõ theo hợp đồng.
6. Worker truy vấn Payment bằng paymentId, hoặc đợi callback/event đã xác thực.
7. Khi đủ bằng chứng, Order chuyển trạng thái thích hợp.

**Điểm mấu chốt:** lỗi truyền phản hồi không phải bằng chứng tiền chưa được thu. Không phát sinh paymentId khác chỉ để thử lại nhanh.

### 10.4. Nhánh hết hạn nhưng thanh toán thành công muộn

Một đơn có thể hết hạn giữ hàng trước khi Payment xác nhận. Khi PaymentSucceeded đến muộn, Order phải áp dụng quy tắc đã chốt:

- Nếu còn hợp lệ và có thể hoàn tất, chốt theo policy đã được chấp thuận.
- Nếu đơn không thể hoàn tất, yêu cầu hoàn tiền/bù trừ.
- Nếu trạng thái provider chưa rõ, để NEEDS_RECONCILIATION.
- Ghi audit để giải thích vì sao kết quả cuối được chọn.
- Không lặng lẽ bỏ event thanh toán thành công chỉ vì đơn đã CANCELLED.

Quy trình refund có trạng thái và owner riêng; đơn CANCELLED không chứng minh refund đã hoàn tất.

### 10.5. Nhánh callback đến trùng hoặc sai thứ tự

Payment provider có thể gửi nhiều callback. Payment Service cần xác minh chữ ký, định danh event, quản lý trạng thái theo contract provider và bỏ qua/báo cáo các chuyển trạng thái không hợp lệ.

Order nhận hai lần PaymentSucceeded phải xử lý idempotent. Nếu một event cũ tới sau event mới, Order không được ghi đè terminal state dựa đơn thuần vào thứ tự nhận.

## 11. Ai sở hữu retry và kết quả sau retry?

Caller có thể retry một network request, nhưng **owner của side effect** phải bảo đảm cùng operation không bị thực hiện trùng ngoài ý muốn.

Một chính sách retry tối thiểu cần:

- Phân loại lỗi retryable và non-retryable theo contract.
- Giới hạn số attempt, backoff, jitter và deadline.
- Dùng idempotencyKey ổn định cho thao tác có side effect.
- Tránh gateway, SDK và service cùng retry không kiểm soát.
- Không tạo operationId mới khi retry một operation cũ.
- Ghi lại trạng thái và attempt để phục vụ đối soát.

Ví dụ Gateway retry 3 lần và Order retry Payment 3 lần có thể gây tối đa 9 lời gọi Payment cho một request đầu vào. Điều này tạo rủi ro **retry amplification** khi dependency quá tải. Nên xác định tầng chịu trách nhiệm retry và budget chung.

### 11.1. Retry không có nghĩa kéo dài business deadline

Giả sử reservation chỉ còn hiệu lực đến 10:15. Nếu một retry bắt đầu lúc 10:16, nó không nên tự động kéo dài reservation vì HTTP client muốn hoàn thành. **Thời hạn nghiệp vụ** phải được Inventory/Order kiểm soát theo hợp đồng.

Tương tự, payment có thể cần tiếp tục đối soát sau HTTP timeout; nhưng cũng không nên chạy vô hạn không có điều kiện kết thúc, cảnh báo hoặc người chịu trách nhiệm.

### 11.2. Nhóm lỗi cần xử lý khác nhau

| Sự kiện | Ý nghĩa | Người xử lý chính |
| --- | --- | --- |
| Invalid request | Không đáp ứng hợp đồng đầu vào | Caller sửa request |
| Business rejection rõ ràng | Ví dụ hết hàng hoặc thẻ bị từ chối rõ | Domain owner ghi kết quả; workflow phản ứng |
| Retryable network error | Có thể phục hồi khi thử lại | Caller retry có giới hạn và idempotency |
| Ambiguous after side effect | Không biết giao dịch đã xử lý chưa | Operation owner cung cấp status; workflow đối soát |
| Business expiry | Quy tắc nghiệp vụ hết hiệu lực | Domain/workflow owner áp dụng state transition |
| Callback chưa tới | Chưa có thông tin kết thúc | Payment/provider adapter và recovery worker |
| Poison message | Event không xử lý được nhiều lần | Consumer owner và quy trình dead-letter |
| Không thể xác minh cuối | Ngoại lệ cần điều tra | Workflow owner, vận hành và nghiệp vụ |

Không nên đưa toàn bộ vào một lỗi chung TIMEOUT và cho workflow kết thúc FAILED.

## 12. Hệ thống trả kết quả cuối qua kênh nào?

Một workflow có thể kéo dài quá thời gian HTTP chờ. Một số cách phổ biến:

### 12.1. Polling trạng thái

Client giữ operationId và định kỳ gọi GET. API cần trả trạng thái hiện tại, terminal flag, thời gian cập nhật, mã lỗi đã phân loại nếu có, và giới hạn polling phù hợp.

Ưu điểm: dễ triển khai, có thể phục hồi sau đóng tab. Nhược điểm: thêm traffic và độ trễ nhận thông tin giữa hai lần poll. Phải có rate limit/backoff; không polling liên tục với interval cực nhỏ.

### 12.2. Webhook/callback

Một service hoặc provider gọi endpoint đã đăng ký để thông báo. Ưu điểm: giảm polling, cho kết quả gần thời điểm hoàn tất. Nhược điểm: callback có thể trễ, gửi trùng, bị mất tạm thời hoặc đến sai thứ tự.

Phía nhận cần xác thực nguồn, chống replay, xử lý idempotent và có cơ chế đối soát nếu callback không đến. **Callback không nhất thiết là nguồn sự thật cuối; phải kiểm tra hợp đồng và trạng thái của owner.**

### 12.3. Event/message

Owner phát event khi state chuyển. Consumer xử lý theo eventId và version. Có thể dùng transactional outbox để giảm rủi ro commit database thành công nhưng publish thất bại. Event có thể đến muộn hoặc được phát lại, nên trạng thái consumer phải được bảo vệ.

### 12.4. SSE/WebSocket

Giao diện realtime có thể nhận push trạng thái qua SSE hoặc WebSocket. Tuy nhiên khi mất kết nối hoặc client offline, cần phương án **reconnect và tải lại trạng thái từ nguồn có thẩm quyền**. Kênh realtime chỉ là cách phân phối thông báo; không nên là nơi duy nhất lưu outcome.

### 12.5. Kết hợp nhiều kênh

Một thiết kế thực tế có thể dùng:

- GET status như hợp đồng đáng tin cậy khi cần phục hồi.
- Event/webhook để giảm thời gian nhận biết kết quả.
- Polling dự phòng khi event/webhook trễ.
- Reconciliation job kiểm tra các operation tồn đọng.

Các kênh có thể gửi cùng một kết quả nhiều lần; consumer phải coi điều đó là bình thường.

## 13. Durable state và timer để công việc không bị quên

Một workflow kéo dài không nên phụ thuộc duy nhất vào memory của một process hay timer tạm trong một instance.

Ví dụ bảng trạng thái logic:

~~~text
order_operations
-------------------------
operation_id        PK
order_id
status
version
business_expires_at
next_check_at
created_at
updated_at
last_error_code
retry_count
~~~

Đây là cấu trúc minh họa; production có thể tách event history, payment states và audit logs thành các bảng phù hợp.

Một scheduled worker có thể:

1. Chọn các operation chưa terminal có next_check_at đến hạn.
2. Claim công việc theo lease/lock để tránh worker trùng xử lý cùng lúc.
3. Tra cứu trạng thái owner của bước đang chờ.
4. Áp dụng transition hợp lệ, cập nhật attempt và thời gian kiểm tra tiếp.
5. Nếu đã hết business deadline, thực hiện quy trình hết hạn hoặc bù trừ.
6. Nếu không thể xác minh, chuyển trạng thái ngoại lệ có cảnh báo.
7. Ghi metrics và audit, tránh retry vô hạn.

### 13.1. Timer firing không phải lệnh chuyển FAILED vô điều kiện

Giả sử timer dự định xử lý đơn hết hạn lúc 10:15. Đến 10:15:01, callback thanh toán thành công cũng đến. Worker phải kiểm tra state mới và quy tắc chuyển trạng thái tại lúc xử lý, không chỉ dựa trên một snapshot cũ.

Ở database quan hệ, có thể dùng **conditional update**, optimistic locking hoặc transaction phù hợp để chỉ một transition hợp lệ được commit. Sau xung đột, worker đọc state mới và quyết định xử lý tiếp.

### 13.2. Mất kết nối trong lúc ghi kết quả

Nếu worker đã commit trạng thái cuối nhưng nhận lỗi mạng từ database, chính worker cũng có kết quả chưa xác định. Nó phải đọc lại bằng operationId hoặc dùng lệnh idempotent để xác minh. Quy tắc “timeout không chứng minh chưa xử lý” áp dụng cả giữa worker và database.

### 13.3. Phục hồi sau restart

Sau khi instance chết và khởi động lại, operation còn PENDING phải tìm thấy từ lưu trữ bền vững. Scheduler/worker được phép chạy lại, nhưng mỗi bước phải chống trùng. Đây là lý do việc giữ state chỉ trên thread HTTP hoặc biến RAM không đủ cho workflow có tác dụng ngoài đời thực.

## 14. Transactional Outbox, Inbox và tính nhất quán

Có một rủi ro phổ biến:

~~~text
Order COMMIT trạng thái CONFIRMED
Order định publish OrderConfirmed
Process crash trước khi gửi message
~~~

Nếu publish là lời gọi thứ hai tách rời transaction, hệ thống có thể mất thông báo. **Transactional Outbox** lưu business state và outbox record trong cùng transaction cục bộ, publisher gửi event về broker sau đó.

~~~text
BEGIN TRANSACTION
  UPDATE orders SET status = CONFIRMED
  INSERT INTO outbox(event_id, order_id, event_type, payload)
COMMIT

Publisher:
  đọc outbox -> publish broker -> ghi dấu đã phát

Consumer:
  dedupe event_id -> xử lý -> ghi checkpoint/inbox
~~~

Publisher có thể gửi lại event nếu mất acknowledgment. Vì vậy consumer cần xử lý lặp idempotent; **Inbox/deduplication table** có thể giúp ghi nhận event đã xử lý. Cơ chế cụ thể cần xác định transaction và storage boundary phù hợp.

Outbox/Inbox không bảo đảm “exactly once” end-to-end cho mọi side effect ngoài database. Vẫn cần quản lý transaction cục bộ, payment provider semantics, idempotency và reconciliation.

## 15. Bù trừ, hoàn tiền và quy trình cuối có nhiều lớp

Trong một đơn hàng, **một bước đã hoàn tất không nhất thiết bị xóa khỏi lịch sử khi quy trình lớn thất bại**.

Ví dụ:

- Inventory đã giữ hàng; Payment bị từ chối rõ -> giải phóng reservation.
- Payment đã thu thành công nhưng Order không thể xác nhận -> khởi tạo refund hoặc xử lý nghiệp vụ khác.
- Refund API bị timeout -> trạng thái hoàn tiền chưa biết, cần tra cứu; không tuyên bố refund thất bại hoặc thành công nếu chưa có bằng chứng.
- Notification email thất bại -> có thể retry email mà không thay đổi kết quả thanh toán hay đơn.

Một **Saga** có thể điều phối các bước cục bộ và hành động bù trừ. Tuy nhiên bù trừ không phải rollback nguyên tử xuyên nhiều hệ thống; hoàn tiền và giao hàng có hậu quả pháp lý, tài chính và vận hành riêng.

Cần định nghĩa riêng:

1. Khi nào order workflow terminal?
2. Refund/return workflow có trạng thái nào?
3. Người dùng nhìn thấy trạng thái nào khi refund còn pending?
4. Ai nhận cảnh báo nếu refund quá hạn?
5. Thông tin kiểm toán được lưu thế nào?

Nếu sản phẩm quyết định cho Order kết thúc CANCELLED trước khi refund hoàn tất, API/UI phải trình bày rõ **refund đang xử lý**, không để hiểu lầm tiền đã về tài khoản.

## 16. Thiết kế API status để nhiều kênh cùng dùng

Một API theo dõi operation có thể có contract minh họa:

~~~http
GET /v1/operations/op-8421
Accept: application/json
~~~

~~~json
{
  "operationId": "op-8421",
  "kind": "PLACE_ORDER",
  "resourceId": "8421",
  "status": "AWAITING_PAYMENT",
  "terminal": false,
  "businessExpiresAt": "2026-11-11T11:00:00Z",
  "nextSuggestedPollSeconds": 3,
  "updatedAt": "2026-11-11T10:46:20Z"
}
~~~

Khi đã đóng:

~~~json
{
  "operationId": "op-8421",
  "kind": "PLACE_ORDER",
  "resourceId": "8421",
  "status": "CANCELLED",
  "terminal": true,
  "outcomeCode": "PAYMENT_NOT_CONFIRMED_BEFORE_EXPIRY",
  "completedAt": "2026-11-11T11:00:10Z",
  "relatedProcess": {
    "kind": "REFUND",
    "status": "IN_PROGRESS"
  }
}
~~~

Dữ liệu ví dụ minh họa một contract, không tuyên bố mọi trường hợp timeout đều phải CANCELLED. **OutcomeCode phải có semantics được định nghĩa và không mâu thuẫn với kết quả thanh toán đã xác nhận.**

### 16.1. Các trường hữu ích

- operationId ổn định qua retry.
- State rõ ràng, terminal flag được tính từ state machine.
- Mã kết quả nghiệp vụ ổn định để client xử lý.
- Timestamp có ý nghĩa, không làm lộ giờ hệ thống nội bộ không cần thiết.
- Tùy chọn liên kết tài nguyên liên quan theo phân quyền.
- Retry-After hoặc gợi ý polling có giới hạn.
- Version/ETag nếu muốn hỗ trợ conditional request.
- Trạng thái compensation riêng nếu có side effect phải hoàn trả.

### 16.2. Bảo mật status API

OperationId không tự tạo quyền truy cập. API phải xác thực và phân quyền người gọi để không lộ trạng thái giao dịch hoặc dữ liệu khách hàng của người khác. Không nhúng dữ liệu thẻ, secret hoặc token vào operationId, URL, logs và callback payload.

Webhook phải xác minh chữ ký, timestamp và chống replay theo hợp đồng provider. Event trên broker cần phân quyền producer/consumer, bảo vệ dữ liệu nhạy cảm và cơ chế rotation secret phù hợp.

## 17. Ví dụ code với Java/Spring Boot: tách tiếp nhận khỏi hoàn tất

Trong Spring Boot, một endpoint có thể lưu operation rồi trả 202. Ví dụ sau là **mã minh họa trách nhiệm**, không phải ứng dụng hoàn chỉnh:

~~~java
@RestController
@RequestMapping("/v1/order-operations")
class OrderOperationController {

    private final OrderOperationService service;

    OrderOperationController(OrderOperationService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<OperationAccepted> start(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody CreateOrderCommand command) {
        OperationAccepted accepted = service.accept(key, command);
        return ResponseEntity
            .accepted()
            .location(URI.create("/v1/order-operations/"
                    + accepted.operationId()))
            .body(accepted);
    }

    @GetMapping("/{operationId}")
    OperationView status(@PathVariable String operationId) {
        return service.getAuthorizedView(operationId);
    }
}

record OperationAccepted(
        String operationId,
        String orderId,
        String status) {}

record OperationView(
        String operationId,
        String orderId,
        String status,
        boolean terminal) {}
~~~

Trong production, việc nhận yêu cầu cần kết hợp authentication/authorization, validation, transaction bền vững, chống idempotency key race, và chính sách rate limit. **Nhận xong rồi dùng một tác vụ nền không bền vững** chưa đủ cho những workflow có tác dụng tài chính.

Một service có thể có ranh giới nghiệp vụ như sau:

~~~java
interface OrderWorkflow {
    OperationAccepted accept(String idempotencyKey,
                             CreateOrderCommand command);

    void onInventoryReserved(String operationId,
                             String reservationId);

    void onPaymentSucceeded(String operationId,
                            String paymentId);

    void onPaymentFailed(String operationId,
                         String reasonCode);

    void reconcilePending(String operationId);

    OperationView getAuthorizedView(String operationId);
}
~~~

Các phương thức trên chỉ biểu thị use case. Triển khai đúng còn cần:

- Transaction lưu state và outbox.
- Transition guard theo current state và version.
- Xử lý message/callback lặp.
- Scheduled timer và reconciliation.
- Phân quyền cho read/write.
- Xử lý callback đến muộn và compensation.
- Quan sát theo operationId và traceId.

Không nên suy ra chỉ cần các method này là workflow đã bền vững; phần quan trọng nằm ở **storage contract và quy tắc state machine**.

## 18. Pseudocode xử lý callback và timer cạnh tranh

Ví dụ một handler nhận PaymentSucceeded:

~~~text
onPaymentSucceeded(event):
    verifyEventSourceAndSchema(event)

    if inboxAlreadyProcessed(event.eventId):
        return ACK

    transaction:
        markEventForDeduplication(event.eventId)
        op = loadOperationForUpdate(event.operationId)

        if op.status == CONFIRMED:
            recordDuplicateAsNoop()
            commit
            return ACK

        if op.status is still eligible for confirmation
           and inventory reservation is valid:
            transition(op, CONFIRMED)
            appendOutbox(OrderConfirmed)

        else:
            recordLatePaymentOutcome(op, event)
            startCompensationOrEscalationAccordingToPolicy(op)

    commit
    return ACK
~~~

Ví dụ timer hết hạn:

~~~text
onBusinessExpiry(operationId):
    transaction:
        op = loadOperationForUpdate(operationId)

        if op is terminal:
            return NOOP

        if currentTime < op.businessExpiresAt:
            scheduleNextCheck(op)
            return

        if payment result is definitely failed:
            transition(op, CANCELLATION_IN_PROGRESS)
            scheduleInventoryRelease(op)

        else if payment result is unknown:
            transition(op, NEEDS_RECONCILIATION)
            schedulePaymentStatusCheck(op)

        else:
            applyExplicitLateSuccessPolicy(op)

    commit
~~~

Pseudocode nhấn mạnh: **kiểm tra điều kiện tại thời điểm commit**, không coi sự kiện timeout là lệnh ghi FAILED. Nếu callback và timer đua nhau, chỉ những chuyển trạng thái hợp lệ theo lock/version mới được commit.

## 19. “Không có kết quả cuối” là trạng thái vận hành cần quản lý

Một workflow không thể được phép mắc kẹt vô thời hạn mà không ai biết. Hãy định nghĩa **ngưỡng cảnh báo và con đường xử lý ngoại lệ**:

| Trạng thái bất thường | Thước đo | Hành động |
| --- | --- | --- |
| Payment pending lâu hơn kỳ vọng | Số payment và tuổi pending | Truy vấn provider, đối soát, cảnh báo |
| Reservation đã giữ nhưng order không tiến triển | Thời gian giữ và số reservation tồn | Kiểm tra workflow, release theo policy |
| Event chưa được consumer xử lý | Broker lag, DLQ, retry count | Khôi phục consumer/replay có idempotency |
| Refund pending quá thời gian cam kết | Số refund và tuổi trạng thái | Đối soát với provider, escalations |
| Không thể xác minh kết quả | Queue NEEDS_MANUAL_REVIEW | Giao người/nhóm có thẩm quyền xử lý |
| Operation đã terminal nhưng event đến muộn | Late-event count và loại | Ghi audit, đánh giá compensation |
| Nhiều lần tạo cùng operation | Idempotency hit/conflict rate | Kiểm tra client retry và nguy cơ duplicate |

Một **manual review** không nên là trạng thái “quên đi” trong hệ thống. Cần có owner, thời điểm tạo, mức ưu tiên, dữ kiện đi kèm và cách đóng vấn đề.

### 19.1. SLI/SLO về hoàn tất nghiệp vụ

Ngoài HTTP latency và error rate, nên đo:

- Tỷ lệ operation đi tới terminal state trong khoảng thời gian mục tiêu.
- p95/p99 thời gian từ ACCEPTED tới terminal outcome.
- Số operation chưa terminal theo tuổi.
- Tỷ lệ phải reconciliation hoặc manual review.
- Số duplicate side effect ngăn được hoặc lọt qua.
- Thời gian hoàn tất compensation/refund.
- Số lần client thấy trạng thái không nhất quán với owner.

Ví dụ giả định: “99% đơn đã được tiếp nhận đi tới trạng thái terminal hoặc được đưa vào quy trình ngoại lệ có owner trong 10 phút.” Trước khi áp dụng phải xác định scope, cửa sổ đo và tiêu chuẩn nghiệp vụ. Không tự dùng mục tiêu minh họa làm SLO production.

## 20. Khi nào nên trả kết quả đồng bộ, khi nào nên giao lại theo dõi?

| Tình huống | Cách thường phù hợp | Lý do |
| --- | --- | --- |
| Đọc thông tin sản phẩm | Đồng bộ GET với timeout | Kết quả cần ngay và không có side effect |
| Kiểm tra dữ liệu đơn giản | Đồng bộ nếu xử lý ngắn và ổn định | Client nhận kết quả rõ trong deadline |
| Tạo báo cáo dài | 202 + operationId + status API | Vượt thời hạn chờ HTTP |
| Gửi email | Background worker/event | Không nhất thiết chặn tác vụ chính |
| Thanh toán qua bên thứ ba | Có thể đồng bộ có giới hạn, sau đó pending + đối soát | Kết quả có thể đến muộn hoặc response bị mất |
| Giữ kho cho checkout | Tùy invariant, có thể đồng bộ hoặc theo workflow | Phải phân biệt đã giữ và đang chờ |
| Batch import lớn | Tiếp nhận bền vững, tiến độ và terminal result | Có thể tốn nhiều phút/giờ |
| Hủy đơn đã giao cho vận chuyển | Workflow có state/cancellation policy | Hủy yêu cầu không đồng nghĩa đã đảo mọi tác dụng |

Đây là định hướng, không có một giao thức duy nhất tối ưu cho mọi trường hợp. Điều kiện chọn là **nghiệp vụ cần xác nhận điều gì, độ trễ chấp nhận, chi phí vận hành và mức độ tin cậy**.

## 21. Những sai lầm thường gặp

**Sai lầm 1 — “Caller timeout thì giao dịch thất bại.”**  
Timeout chỉ nói caller hết thời gian chờ. Phải truy vấn owner hoặc chờ kết quả để xác minh tác dụng nghiệp vụ.

**Sai lầm 2 — “Client đóng tab là hệ thống hủy đơn.”**  
HTTP cancellation không nhất thiết rollback database hoặc API ngoài. Cần workflow hủy có trạng thái riêng và contract rõ.

**Sai lầm 3 — “Đã publish event thì công việc xong.”**  
Broker acknowledgment có phạm vi riêng; consumer có thể chưa chạy. Phân biệt đã ghi event, đã được broker nhận, đã được xử lý và nghiệp vụ đã terminal.

**Sai lầm 4 — “Mỗi service tự quyết định kết quả đơn hàng.”**  
Một payment success không có nghĩa mọi điều kiện của Order đều đã thỏa. Chỉ owner của order aggregate được thực hiện transition của đơn theo quy tắc.

**Sai lầm 5 — “Dùng choreography nên không cần workflow owner.”**  
Dù không có coordinator tập trung, vẫn cần nơi theo dõi tiến độ, xử lý timeout, compensation và pending không có event.

**Sai lầm 6 — “Hết hạn tức là có thể xóa dữ liệu pending.”**  
Một side effect muộn có thể xuất hiện. Cần lưu operationId và history đủ lâu theo yêu cầu đối soát, kiểm toán và bảo mật.

**Sai lầm 7 — “Retry với id mới để nhanh hết lỗi.”**  
Tạo id mới dễ tạo operation mới và side effect trùng. Retry cùng mục đích phải tuân theo idempotency contract.

**Sai lầm 8 — “Dùng một timeout chung cho mọi thứ.”**  
Thời gian chờ socket, deadline HTTP, hạn giữ hàng và thời gian đối soát có mục đích khác nhau. Đặt chúng bằng nhau tùy tiện sẽ tạo lỗi.

**Sai lầm 9 — “Một event muộn chỉ cần bỏ qua.”**  
Nếu event phản ánh một khoản tiền thật, bỏ qua có thể mất dấu nghĩa vụ refund. Phải theo state và xử lý compensation/escalation.

**Sai lầm 10 — “GET status không cần phân quyền vì operationId khó đoán.”**  
OperationId không thay thế authentication/authorization. Trạng thái đơn và thanh toán là dữ liệu cần bảo vệ.

**Sai lầm 11 — “HTTP 202 có nghĩa chắc chắn sẽ thành công.”**  
202 thể hiện tiếp nhận xử lý, không bảo đảm final success. Hệ thống cần contract status và cơ chế xử lý cuối.

**Sai lầm 12 — “Khi có callback thì không cần polling hay reconciliation.”**  
Callback có thể không đến, đến lặp hoặc trễ; một cơ chế kiểm tra trạng thái dự phòng vẫn hữu ích cho workflow quan trọng.

## 22. Cách triển khai theo từng bước

**Bước 1: Xác định aggregate và owner.** Ai có quyền ghi trạng thái đơn, payment, reservation? Những bất biến nào thuộc từng service?

**Bước 2: Định nghĩa kết quả cuối.** Những state nào terminal? Lỗi nào là nghiệp vụ cuối, lỗi nào chỉ là unknown? Có compensation độc lập không?

**Bước 3: Chốt các loại deadline.** Chờ đồng bộ tối đa bao lâu; business expiry là gì; workflow cần được đối soát trong thời hạn nào?

**Bước 4: Định danh và lưu bền.** Tạo operationId, idempotency key, state và dữ kiện cần thiết trước khi phản hồi accepted.

**Bước 5: Thiết kế kênh tiến độ.** Status API, event/callback hoặc realtime push; có cơ chế phục hồi sau mất kết nối.

**Bước 6: Thiết kế failure path.** Timeout sau commit, callback trùng, event trễ, provider lỗi, worker restart và bản ghi pending quá hạn.

**Bước 7: Cài đặt transition guard.** Kiểm tra version/current state trong transaction; không cho hai handler ghi đè tùy tiện.

**Bước 8: Đặt reconciliation và ownership vận hành.** Có worker tìm pending, alert, escalations và runbook.

**Bước 9: Thử nghiệm và đo.** Load test, fault injection, xác minh status API, audit và outcome nghiệp vụ sau lỗi.

**Bước 10: Ghi quyết định.** Với các lựa chọn quan trọng về deadline, terminal state và compensation, ghi ADR ngắn nêu bối cảnh, trade-off và điều kiện xem lại.

Không nhất thiết dùng một workflow engine lớn ngay từ đầu. Với yêu cầu nhỏ, một state machine trong service, bảng operation bền vững, scheduler và outbox phù hợp có thể đáp ứng. Chỉ tăng độ phức tạp khi rủi ro và quy mô thực tế đòi hỏi.

## 23. Kịch bản kiểm thử cần có

| Kịch bản | Trạng thái mong đợi |
| --- | --- |
| Server chưa nhận request nhưng client timeout | Có thể retry theo contract; không tạo hai operation |
| Server đã commit accepted nhưng response mất | Client dùng cùng idempotency key nhận operationId cũ |
| Payment đã thành công nhưng callback đến muộn | Order đối soát theo policy; không coi timeout là payment failure |
| Timer hết hạn và callback thành công chạy đồng thời | Transition có guard; chỉ một đường hợp lệ commit |
| Broker phát event trùng hai lần | Consumer idempotent; không phát sinh side effect trùng |
| Worker restart giữa các bước | Workflow tiếp tục từ state bền vững, không bắt đầu tùy tiện từ đầu |
| Provider trả kết quả không rõ | Để trạng thái pending/unknown và truy vấn lại |
| Order cancelled, payment success đến sau | Compensation hoặc manual review theo policy; không mất dấu tiền |
| Client mở lại ứng dụng sau một giờ | Có thể truy vấn operationId/status theo quyền |
| Cùng idempotency key với payload khác | Bị từ chối theo contract, không dùng kết quả sai |
| Không có kết quả quá hạn xử lý | Alert/escalation có owner, không treo im lặng |
| GET status từ tài khoản khác | Bị từ chối theo authorization |

Một phép thử tốt kiểm tra cả **trạng thái lưu trữ, audit, event, side effect và thông báo cho client**, không chỉ kiểm tra mã HTTP.

## 24. Bài tập tình huống

### Bài tập A — Checkout vượt thời gian chờ

Client có timeout 3 giây. Payment provider thường trả kết quả trong 1–8 giây và đôi khi gửi callback trễ. Hãy thiết kế:

1. Response ban đầu của Order nếu Payment chưa xong sau 3 giây.
2. OperationId, paymentId và idempotency key được tạo/giữ như thế nào.
3. Ai sở hữu request deadline, ai sở hữu payment outcome, ai sở hữu order terminal state.
4. State machine và status API cho người dùng theo dõi.
5. Cách xử lý callback đến sau business expiry, cùng yêu cầu compensation.
6. Metrics và cảnh báo cho pending quá lâu.

### Bài tập B — Timer và callback xung đột

Đơn có hạn giữ hàng đến 10:15. Payment callback success và expiration worker chạy gần đồng thời. Hãy viết transition guard để không vừa CONFIRMED vừa CANCELLED; xác định khi nào cần refund và vì sao không thể chỉ dựa vào thứ tự event.

### Bài tập C — Choreography không có coordinator

Inventory phát InventoryReserved, Payment phát PaymentSucceeded, Notification nghe OrderConfirmed. Sau sự cố broker, một số event bị trễ. Hãy xác định nguồn sự thật của từng state và service chịu trách nhiệm tìm những đơn PENDING quá hạn. Tại sao việc mọi consumer đều idempotent vẫn chưa đủ để bảo đảm workflow cuối cùng không bị quên?

### Bài tập D — Thiết kế hợp đồng bất đồng bộ

Một chức năng xuất báo cáo mất 20 phút. Hãy đề xuất POST tạo operation, GET status, cách hủy, trạng thái terminal, bảo mật kết quả và cơ chế dọn tài nguyên hết hạn. Phân biệt thời hạn tải file sau hoàn tất với deadline của job.

## 25. Tự kiểm tra kiến thức

1. Vì sao HTTP timeout không thể coi là kết quả thất bại của một lệnh thanh toán?
2. Request timeout, end-to-end deadline, business expiry và workflow deadline khác nhau như thế nào?
3. Ai nên sở hữu trạng thái kết thúc của đơn hàng khi Payment và Inventory có trạng thái riêng?
4. Vì sao phải lưu operationId bền vững trước khi trả 202?
5. Callback đã được gửi có chứng minh consumer đã xử lý và Order đã terminal chưa?
6. Cancellation của client có tự động rollback mọi side effect server không?
7. Một late PaymentSucceeded sau khi đơn CANCELLED cần được xử lý ra sao?
8. Vì sao cần optimistic locking hoặc transition guard khi timer và callback cạnh tranh?
9. Orchestration và choreography khác nhau ở điểm nào về điều phối, và điều gì vẫn cần owner?
10. Transactional Outbox giải quyết rủi ro nào, và tại sao vẫn phải dedupe consumer?
11. traceId khác operationId và idempotencyKey ra sao?
12. Vì sao chỉ có retry có backoff chưa đủ để bảo đảm đúng nghiệp vụ?
13. Những SLI nào phản ánh việc workflow có kết quả cuối đúng hạn?
14. Khi nào API nên trả 202 thay vì chờ để trả kết quả cuối?
15. Một service gửi payment success nhưng Order vẫn pending: bạn cần kiểm tra những nguồn dữ liệu và cơ chế khôi phục nào?

## 26. Kết luận

**Quyền sở hữu thời hạn xử lý** xác định một lời gọi hoặc một quy trình được chờ và được thực hiện đến khi nào. **Quyền sở hữu kết quả cuối cùng** xác định ai có thẩm quyền ghi nhận trạng thái nghiệp vụ đã hoàn tất và ai phải tiếp tục xử lý khi kết quả chưa rõ.

Hai trách nhiệm phải được phân tách trong hệ thống phân tán: người gọi có quyền ngừng chờ, nhưng **không có quyền suy đoán giao dịch của bên nhận chưa diễn ra**; service thực hiện thao tác sở hữu kết quả cục bộ, còn workflow owner chịu trách nhiệm đưa toàn bộ quy trình tới một kết cục hợp lệ hoặc trạng thái ngoại lệ có người xử lý.

Một mô hình giao tiếp tốt cần **deadline hữu hạn, operationId ổn định, idempotency, trạng thái bền vững, state machine có guard, kênh theo dõi kết quả, timer/reconciliation và observability**. Khi đã thiết kế rõ những cơ chế này, timeout, phản hồi muộn, restart và sự kiện trùng trở thành những trường hợp hệ thống biết cách xử lý, thay vì biến thành đơn hàng treo hoặc giao dịch sai.