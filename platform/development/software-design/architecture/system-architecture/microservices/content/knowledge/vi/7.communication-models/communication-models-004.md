# Điều phối tập trung và phối hợp qua sự kiện

## Mục tiêu bài học

Một nghiệp vụ trong Microservices thường không thể hoàn thành chỉ bằng thao tác trong một dịch vụ. Đặt hàng cần liên hệ Ordering, Inventory, Payments, Shipping; phát hành hợp đồng cần phối hợp Customer, Billing, Document và Notification. Các dịch vụ có thể lưu dữ liệu riêng, gặp lỗi độc lập và không thể mặc nhiên dùng một giao dịch cơ sở dữ liệu duy nhất.

Hai cách tổ chức sự phối hợp thường gặp là:

- **Điều phối tập trung (orchestration):** một thành phần điều phối biết trạng thái workflow, quyết định bước tiếp theo và gửi lệnh đến dịch vụ chịu trách nhiệm.
- **Phối hợp qua sự kiện (choreography):** các dịch vụ phản ứng với sự kiện nghiệp vụ do dịch vụ khác công bố, không cần một thành phần duy nhất chỉ đạo toàn bộ chuỗi.

Cả hai là cách **tổ chức tương tác và trách nhiệm ra quyết định**. Sự khác nhau không nằm ở việc có hay không dùng message broker: một orchestrator vẫn có thể gửi command và nhận event qua broker; một kiến trúc choreography vẫn cần broker hoặc hạ tầng chuyển phát. Có broker ở giữa không làm nghiệp vụ trở thành điều phối tập trung.

Sau bài này, người học có thể:

1. Phân biệt orchestrator, command, business event, event consumer và coordinator state.
2. Vẽ cùng một workflow dưới dạng orchestration hoặc choreography.
3. Hiểu Saga, giao dịch cục bộ, bù trừ, idempotency, outbox và eventual consistency.
4. Đánh giá các hệ quả đối với coupling, khả năng thay đổi, vận hành, xử lý lỗi và quan sát.
5. Chọn hoặc kết hợp hai cách theo độ phức tạp nghiệp vụ và mức độ tự chủ dịch vụ.

## 1. Bối cảnh: Một nghiệp vụ đi qua nhiều dịch vụ

Giả sử khách đặt một sản phẩm. Hệ thống cần:

1. Tạo đơn hàng ở trạng thái PENDING.
2. Giữ hàng trong kho.
3. Khởi tạo hoặc xác nhận thanh toán.
4. Xác nhận đơn và khởi động giao hàng.
5. Nếu một bước thất bại, giải phóng nguồn lực đã giữ và chuyển đơn về trạng thái phù hợp.

Một mô hình triển khai minh họa:

~~~text
           Khách hàng
               |
               v
          Ordering
          /   |    \
         v    v     v
    Inventory Payments Shipping
       DB        DB       DB
~~~

Từng dịch vụ sở hữu dữ liệu và quy tắc riêng. Việc Ordering đã tạo đơn trong database không thể tự đảm bảo Inventory đã giữ hàng hoặc Payments đã xác nhận tiền. Khi có lỗi timeout, một dịch vụ thậm chí chưa biết dịch vụ khác đã thực hiện thành công hay chưa.

Vì vậy phải có thiết kế cho **ai quyết định bước tiếp theo, ai biết tiến độ, thông tin nào được công bố, và ai xử lý phục hồi**.

Khái niệm orchestration/choreography nói về cách đưa ra những quyết định đó. Chúng khác với câu hỏi liệu giao tiếp có dùng HTTP, gRPC hay Kafka; HTTP có thể dùng trong một orchestrator, còn Kafka có thể dùng cho cả hai cách.

## 2. Điều phối tập trung (orchestration) là gì?

Trong orchestration, một thành phần điều phối workflow biết các bước chính và trạng thái tiến trình. Nó yêu cầu từng dịch vụ thực hiện công việc cụ thể và xử lý kết quả để chọn hành động tiếp theo.

Ví dụ:

~~~text
                    Order Orchestrator
                         |
         +---------------+---------------+
         |               |               |
         v               v               v
  ReserveInventory   AuthorizePayment  CreateShipment
     command             command          command
         |               |               |
         v               v               v
     Inventory         Payments         Shipping
         |               |               |
         +---- result ---+----- result --+
                         |
                         v
                  Workflow decision
                  - Confirm order
                  - Retry/compensate
                  - Mark failed/pending
~~~

Trong một workflow checkout đơn giản:
- Orchestrator yêu cầu Inventory giữ hàng.
- Khi nhận thành công, orchestrator yêu cầu Payments xác thực giao dịch.
- Khi thanh toán thành công, orchestrator yêu cầu Ordering xác nhận đơn.
- Nếu Payments từ chối, orchestrator yêu cầu Inventory giải phóng reservation.

Đặc điểm chính là **trình tự và điều kiện chuyển bước được thể hiện rõ tại coordinator**.

### 2.1. Orchestrator thường giữ những thông tin nào?

- Định danh tiến trình: workflowId/sagaId, orderId và correlationId.
- Bước hiện tại và lịch sử sự kiện/kết quả đã xử lý.
- Trạng thái: STARTED, INVENTORY_RESERVED, PAYMENT_PENDING, COMPLETED, COMPENSATING, FAILED...
- Lệnh cần gửi và trạng thái giao hàng/đợi phản hồi.
- Deadline, timeout, retry policy và bước cần bù trừ.
- Phiên bản định nghĩa workflow để không nhầm quy trình cũ và mới.
- Thông tin phục hồi sau khi instance điều phối bị restart.

Trạng thái này cần được lưu bền vững nếu workflow sống lâu hoặc có thể có sự cố. Một biến trong bộ nhớ của một process không phải phương án đủ cho quy trình thanh toán có thể kéo dài qua nhiều phút và nhiều lần deploy.

### 2.2. Orchestrator có phải “dịch vụ trung tâm biết mọi nghiệp vụ” không?

Không nên. Orchestrator sở hữu **logic quy trình liên dịch vụ**, không thay các dịch vụ ra quyết định về bất biến nội bộ.

Ví dụ:
- Inventory quyết định có đủ tồn và có thể giữ hàng hay không.
- Payments quyết định một kết quả PSP có hợp lệ để xác thực/ghi nhận tiền hay không.
- Ordering quyết định trạng thái đơn nào được phép chuyển.
- Orchestrator quyết định sau khi nhận InventoryReserved thì gửi AuthorizePayment, hoặc sau PaymentRejected thì kích hoạt ReleaseInventory.

Orchestrator nên biết **hợp đồng** và **trạng thái workflow**; nó không nên đọc trực tiếp các bảng chi tiết của Inventory/Payments để tự áp quy tắc thay cho chúng.

### 2.3. Công nghệ không quyết định mô hình

Orchestrator có thể:
- Gọi HTTP/gRPC tuần tự và nhận response.
- Gửi command lên message broker, chờ event kết quả.
- Dùng workflow engine hỗ trợ timer, retry và lưu state bền vững.
- Là một application service/process manager được viết trong dịch vụ sở hữu quy trình.

Không phải cứ dùng công cụ workflow là đã có một kiến trúc phù hợp; cần xác định ownership, contract và cách phục hồi trạng thái.

## 3. Phối hợp qua sự kiện (choreography) là gì?

Trong choreography, không có một coordinator riêng quyết định từng bước của toàn bộ quy trình. Mỗi dịch vụ:
1. Làm phần việc mà mình sở hữu.
2. Công bố một **sự kiện nghiệp vụ** khi có thay đổi quan trọng.
3. Các dịch vụ quan tâm tự chọn hành động dựa trên sự kiện nhận được.
4. Kết quả hành động có thể tạo ra sự kiện mới.

Ví dụ:

~~~text
Ordering                Inventory                 Payments
   |                         |                        |
   | -- OrderPlaced -------->|                        |
   |                         |                        |
   |                  Reserve local stock             |
   |                         |                        |
   |<-- InventoryReserved ---+--- InventoryReserved -->|
   |                         |                        |
   |                         |                Authorize payment
   |                         |                        |
   |<---------------------- PaymentAuthorized --------|
   |                         |                        |
Confirm order              (other consumers may react)
   |
   +---- OrderConfirmed ---> Shipping / Notification
~~~

Trong sơ đồ này, Ordering không ra lệnh chi tiết “Inventory hãy làm bước 2 rồi Payments làm bước 3”; Inventory và Payments phản ứng theo contract sự kiện. Mỗi nơi biết những điều kiện và hành động của chính mình.

Cần lưu ý đây chỉ là một **thiết kế minh họa**. Một lựa chọn khác có thể để Payments chỉ phản ứng sau khi nhận InventoryReserved; hoặc để Ordering phát một event riêng chỉ khi đơn đủ điều kiện thanh toán. Phải làm rõ ai sở hữu trạng thái đơn và ai chịu trách nhiệm khi toàn bộ tiến trình không hoàn tất.

### 3.1. Event mô tả điều đã xảy ra

Các ví dụ event:
- OrderPlaced
- InventoryReserved
- InventoryReservationRejected
- PaymentAuthorized
- PaymentRejected
- OrderConfirmed
- OrderCancelled

Event cần có ý nghĩa rõ trong mô hình nghiệp vụ. Nó thường ở thì quá khứ, diễn đạt sự thật đã được ghi nhận. Một event không nên ngụy trang mệnh lệnh như “DoPaymentNow” mà không làm rõ ai điều hành quy trình.

### 3.2. Choreography không có nghĩa không ai chịu trách nhiệm

Không có coordinator toàn cục không đồng nghĩa workflow “tự chạy rồi tự đúng”. Vẫn phải có:
- Dịch vụ có thẩm quyền về trạng thái cuối của business entity, ví dụ Ordering.
- Quy tắc kết thúc hoặc hủy: đơn được xác nhận khi những sự kiện nào đã xảy ra?
- Cách xử lý sự kiện đến trễ, trùng, đảo thứ tự hoặc không bao giờ đến.
- Ownership cho hợp đồng event, schema, version và dead-letter.
- Quan sát end-to-end để biết một orderId đang dừng ở đâu.

Choreography phân tán logic workflow sang nhiều consumer. Nó giảm nhu cầu một coordinator nhưng làm luồng điều khiển khó thấy tại một chỗ nếu thiếu công cụ và kỷ luật vận hành.

## 4. So sánh cùng một nghiệp vụ dưới hai cách

### 4.1. Orchestration: một nơi quyết định luồng

~~~text
Client → Checkout Orchestrator
            |
            +-- ReserveInventory command --> Inventory
            |<-- InventoryReserved result ----+
            |
            +-- AuthorizePayment command --> Payments
            |<-- PaymentAuthorized result ----+
            |
            +-- ConfirmOrder command --------> Ordering
            |<-- OrderConfirmed result --------+
            |
         COMPLETED
~~~

Orchestrator có thể biết mọi bước cần chờ, timer nào đang hoạt động và compensation nào phải gọi.

### 4.2. Choreography: mỗi dịch vụ phản ứng với sự kiện

~~~text
Ordering --OrderPlaced----------> Inventory
Inventory --InventoryReserved--> Payments
Payments --PaymentAuthorized---> Ordering
Ordering --OrderConfirmed------> Shipping
Shipping --ShipmentCreated-----> Notification
~~~

Không có một thành phần phát hành toàn bộ command; logic nằm trong consumer của Inventory, Payments, Ordering và Shipping. Nếu PaymentRejected, một hoặc nhiều consumer phù hợp phải thực thi rollback nghiệp vụ theo các quy tắc thống nhất.

### 4.3. Bảng khác biệt quan trọng

| Khía cạnh | Điều phối tập trung | Phối hợp qua sự kiện |
| --- | --- | --- |
| Nơi thể hiện trình tự | Coordinator/workflow definition | Logic phân tán qua các consumer |
| Tín hiệu thường dùng | Command và result/event | Business/integration event |
| Quyết định bước tiếp | Orchestrator | Dịch vụ nhận event |
| Theo dõi tiến độ | Có thể tập trung ở workflow state | Cần ghép sự kiện và state nhiều dịch vụ |
| Đổi quy trình nhiều bước | Sửa chủ yếu coordinator và hợp đồng cần thiết | Có thể phải sửa nhiều consumer và hợp đồng |
| Mức kết dính | Coordinator biết các participant | Các participant bị kết dính qua event schema và thời điểm |
| Khả năng thêm phản ứng mới | Thường cần lệnh hoặc bước mới nếu là workflow chính | Consumer mới có thể subscribe event hiện có |
| Kiểm soát timeout/bù trừ | Dễ tập trung chính sách | Phải phối hợp quy tắc phân tán rõ |
| Rủi ro chính | Coordinator phình to hoặc thành nút phụ thuộc | Luồng ẩn, vòng lặp event, khó debug |
| Hạ tầng | Có thể HTTP, gRPC, queue, workflow engine | Thường broker/event bus nhưng không bắt buộc |
| Độ nhất quán | Tùy giao thức và transaction strategy | Tùy semantics, thường eventual consistency |
| Nhân bản triển khai | Coordinator có thể scale với state bền vững | Consumer có thể scale độc lập theo event |

Không nên đánh giá bằng câu “phương án nào ít thành phần hơn”. Số lượng process, broker, storage, trạng thái và độ phức tạp vận hành đều ảnh hưởng tổng chi phí.

## 5. Command và event: phân biệt trước khi thiết kế

**Command** thể hiện ý định yêu cầu một chủ thể thực hiện việc gì:
- ReserveInventory(orderId, sku, quantity)
- AuthorizePayment(orderId, amount)
- ReleaseReservation(reservationId)

**Event** mô tả điều đã xảy ra:
- InventoryReserved(orderId, reservationId)
- PaymentAuthorized(orderId, paymentId)
- ReservationReleased(orderId)

| Đặc tính | Command | Event |
| --- | --- | --- |
| Nghĩa | “Hãy thực hiện…” | “Đã xảy ra…” |
| Chủ thể nhận | Thường xác định rõ chủ thể chịu trách nhiệm | Có thể nhiều subscriber |
| Ownership | Bên yêu cầu phối hợp với bên thực hiện | Bên phát công bố sự thật của mình |
| Kết quả | Có success, rejection, unknown hoặc completion event | Consumer tự xử lý theo policy |
| Ví dụ | CapturePayment | PaymentCaptured |
| Nguy cơ | Coordinator biết quá nhiều API chi tiết | Consumer bị phụ thuộc vào sự kiện của bên phát |

Nếu có một component nhận tất cả event rồi ra lệnh cho từng service, về ngữ nghĩa đó vẫn có thể là **orchestration qua messaging**. Ngược lại, mỗi service trực tiếp gửi command cho service kế tiếp không tự chứng minh kiến trúc đã choreography; cần nhìn vào nơi sở hữu quyết định workflow.

Một event như OrderPlaced không đồng nghĩa “đã thu tiền”. Consumer không được suy diễn những bảo đảm chưa được contract công bố.

## 6. Saga: hoàn thành giao dịch nghiệp vụ xuyên ranh giới

Một workflow nhiều dịch vụ thường không thể dùng cùng một ACID transaction bao phủ tất cả database và API ngoài. **Saga** là cách tổ chức chuỗi giao dịch cục bộ, trong đó mỗi bước commit dữ liệu thuộc dịch vụ của mình; khi bước sau thất bại, hệ thống thực hiện hành động bù trừ nếu cần và nếu nghiệp vụ cho phép.

Một saga có thể được xây dựng bằng:
- **Orchestration saga:** coordinator yêu cầu từng bước và quyết định compensation.
- **Choreography saga:** mỗi dịch vụ phát/nhận sự kiện để thực hiện bước hoặc bù trừ.

Saga không phải tính năng “rollback toàn hệ thống như transaction SQL”. Đã gửi email thì không thể “unsend” theo nghĩa tuyệt đối; đã capture tiền có thể phải hoàn tiền, tạo một giao dịch mới; đã giao hàng có thể cần quy trình trả hàng, không đơn giản đảo trạng thái.

### 6.1. Các bước cục bộ và bù trừ

Ví dụ:

| Bước tiến | Chủ thể | Hành động bù trừ khả dĩ |
| --- | --- | --- |
| Tạo đơn PENDING | Ordering | Hủy đơn với lý do nghiệp vụ |
| Giữ tồn kho | Inventory | Giải phóng reservation |
| Authorize thanh toán | Payments | Void authorization nếu được hỗ trợ |
| Capture thanh toán | Payments | Refund, tùy trạng thái và chính sách |
| Tạo shipment | Shipping | Hủy shipment nếu chưa giao; sau đó có thể là return |

Không phải mọi bước đều có compensation hoàn toàn đảo ngược. Cần phân loại **reversible**, **compensatable** và **irreversible/pivot step** theo chính sách nghiệp vụ.

### 6.2. Saga không đảm bảo cách ly toàn cục

Các dịch vụ có thể thấy trạng thái tạm thời trước khi saga kết thúc, chẳng hạn tồn kho đã được giữ nhưng thanh toán chưa được xác nhận. Đó là thực tế của eventual consistency và transaction cục bộ.

Cần quyết định:
- Người dùng được thấy trạng thái nào khi xử lý?
- Một reservation hết hạn sau bao lâu?
- Có cho đặt lệnh khác trong lúc đơn PENDING không?
- Khi event đến chậm hoặc payment response không rõ thì làm gì?
- Ai sở hữu trạng thái “đơn đã hoàn tất”?

Một quy trình Saga tốt cần **mô hình trạng thái nghiệp vụ tường minh**, thay vì coi những trạng thái trung gian là lỗi bất thường.

## 7. Ví dụ đầy đủ: Orchestrated checkout saga

Giả sử Ordering sở hữu đơn hàng, Inventory giữ hàng, Payments gọi nhà cung cấp thanh toán. Một coordinator thuộc boundary Checkout lưu workflow state riêng.

### 7.1. Đường thành công

~~~text
(1) CheckoutRequested
        |
        v
    Orchestrator --ReserveInventory--> Inventory
        |<-- InventoryReserved(reservationId)
        |
        +------------AuthorizePayment--> Payments
        |<-- PaymentAuthorized(paymentId)
        |
        +------------ConfirmOrder------> Ordering
        |<-- OrderConfirmed
        |
        v
     COMPLETED
        |
        +---- event OrderConfirmed ----> Shipping/Notification
~~~

OrderCreated/PENDING có thể được tạo trước khi bắt đầu saga hoặc là một bước của saga, tùy nguồn sự thật và API contract. Thành công của saga phải được xác định bằng trạng thái đã được những dịch vụ có thẩm quyền xác nhận.

### 7.2. Khi thanh toán bị từ chối

~~~text
ReserveInventory → InventoryReserved
AuthorizePayment → PaymentRejected
          |
          v
Orchestrator:
   Send ReleaseReservation
          |
          v
Inventory: ReservationReleased
          |
          v
Ordering: MarkOrderCancelled
          |
          v
Saga: COMPENSATED / FAILED
~~~

**PaymentRejected** là một kết quả nghiệp vụ có thể kết luận, khác với **PaymentTimeout**. Với timeout, PSP có thể đã xác nhận tiền nhưng response bị mất. Không nên lập tức refund hoặc gửi thanh toán lần hai khi chưa biết kết quả.

### 7.3. Khi coordinator bị restart

Nếu workflow state chỉ là một chuỗi lệnh trong RAM, restart giữa lúc Payments đang xử lý có thể làm mất tiến độ. Coordinator cần khả năng:
- Ghi bền trạng thái và action đang chờ.
- Khôi phục workflow theo workflowId.
- Nhận lại result/event mà không thực hiện bước tiếp theo hai lần.
- Có timer/schedule để phát hiện timeout hoặc trạng thái chờ lâu.
- Reconcile với trạng thái có thẩm quyền khi kết quả không chắc chắn.

Nếu dùng một workflow engine, các tính năng durable execution cần được cấu hình và kiểm chứng; chỉ đưa code vào engine không tự bảo đảm idempotency của side effect ngoài.

### 7.4. Tránh coordinator thành “god service”

Điều phối chỉ nên biết **khi nào và vì sao** gửi command. Nó không được tự tính tiền, quyết định số lượng tồn hợp lệ, hoặc thay thế domain validation của mỗi participant.

Các dịch vụ vẫn phải từ chối command vi phạm invariant, kể cả khi command do coordinator gửi đến.

## 8. Ví dụ đầy đủ: Choreographed checkout saga

Cùng nghiệp vụ có thể tổ chức bằng các event contract:

~~~text
Ordering:
  transaction local -> Order(PENDING)
  publish OrderPlaced
                |
                v
Inventory consumer:
  handle OrderPlaced
  reserve stock locally
  publish InventoryReserved
       or InventoryReservationFailed
                |
          +-----+------+
          |            |
          v            v
        success      failure
          |            |
          v            v
Payments consumer  Ordering consumer
  handle reserved   mark cancelled
  authorize
  publish PaymentAuthorized / PaymentRejected
          |
          v
Ordering consumer:
  handle payment result
  confirm or cancel order
          |
          v
publish OrderConfirmed / OrderCancelled
~~~

Nếu PaymentRejected nhưng đã giữ hàng, cần một subscriber hoặc process thuộc boundary chịu trách nhiệm **giải phóng reservation**. Có thể để Inventory subscribe PaymentRejected/OrderCancelled; hoặc Ordering gửi một command release. Cả hai cần xác định ownership và tránh event cycle.

### 8.1. Mặt thuận lợi

- Có thể thêm Notification subscriber để gửi email sau OrderConfirmed mà không sửa luồng cốt lõi ở Ordering.
- Các dịch vụ có thể tự scale và deploy theo nhu cầu của mình.
- Nhiều business reaction độc lập có thể nghe cùng một event.
- Publisher không cần biết mọi consumer hiện tại.

### 8.2. Mặt khó

- Workflow logic nằm rải rác: đặt event nào chạy trước, ai kết thúc toàn bộ quy trình?
- Một consumer mới có thể vô tình tạo phản ứng phụ hoặc chuỗi event vòng lặp.
- Thay business process có thể cần cập nhật nhiều consumer.
- Khi event thất lạc/đang chờ ở DLQ, tiến trình có thể treo không có ai tự phát hiện.
- Cần correlation, trạng thái quan sát, retry, bù trừ và chủ thể chịu trách nhiệm rõ.

Choreography không loại bỏ yêu cầu thiết kế một process model. Nó chỉ phân phối các quyết định thay vì tập trung vào một coordinator.

## 9. So sánh coupling: tường minh và ngầm

Orchestration và choreography không có bên nào “không coupling”.

**Orchestration coupling:**
- Coordinator phụ thuộc vào capability và contract của participant.
- Điều kiện chuyển bước được viết tập trung nên dễ nhìn.
- Đổi tên command, đổi semantics result hoặc thêm bước có thể đòi sửa workflow.
- Participant ít phải biết trình tự tổng thể; chỉ thực hiện năng lực được yêu cầu.

**Choreography coupling:**
- Publisher và consumer gắn qua event schema và business semantics.
- Consumer thường phụ thuộc vào giả định event nào sẽ xuất hiện, lúc nào và có thể xuất hiện nhiều lần hay không.
- Khi chỉnh workflow, có thể phải sửa nhiều event handler.
- Một publisher không cần biết danh tính consumer, nhưng đổi nghĩa event vẫn có thể phá các downstream.

Ví dụ nếu Shipping nghe trực tiếp PaymentAuthorized để tạo shipment, nó có thể gửi hàng trước khi Ordering xác nhận đơn và Inventory bảo đảm trạng thái giữ hàng. Đây là một **coupling ngữ nghĩa không được thể hiện trong kiểu dữ liệu**: Shipping giả định payment success đồng nghĩa đơn sẵn sàng giao.

Thiết kế tốt nên có sự kiện ở đúng điểm quyết định, chẳng hạn OrderReadyForFulfillment được Ordering công bố sau khi tất cả điều kiện cần đã đạt.

## 10. Ai là nguồn sự thật của trạng thái cuối?

Một hệ thống dùng event có thể có nhiều bản sao/trạng thái tổng hợp, nhưng từng sự thật nghiệp vụ quan trọng cần có chủ thể sở hữu.

Ví dụ:
- Inventory xác nhận ReservationStatus theo reservationId.
- Payments xác nhận PaymentStatus theo paymentId.
- Ordering quyết định OrderStatus có được chuyển sang CONFIRMED hay không dựa trên các kết quả cần thiết.
- Shipping quyết định ShipmentStatus dựa trên quá trình giao hàng.

Orchestrator giữ **workflow state**, nhưng không nhất thiết là nguồn sự thật của mọi business entity. Một dashboard hiển thị tiến độ tổng hợp có thể đọc workflow projection; khi quyết định thu tiền/hủy đơn, vẫn cần hợp đồng có thẩm quyền.

Trong choreography, Ordering có thể nghe InventoryReserved và PaymentAuthorized để xác nhận đơn. Nhưng một lỗi rất hay gặp là giả định event đến đúng thứ tự hoặc đúng một lần. Ordering phải bảo vệ transition với state machine và điều kiện đã thỏa.

## 11. Thiết kế state machine cho workflow

Dù dùng mô hình nào, nên thể hiện trạng thái rõ. Ví dụ:

~~~text
                        CREATED
                           |
                           v
                   WAITING_INVENTORY
                     /          \
          reserved  /            \ rejected/timeout handled
                   v              v
            WAITING_PAYMENT   CANCELLING
              /      \            |
     approved /        \ rejected  v
             v          v       CANCELLED
         CONFIRMING  COMPENSATING
             |          |
             v          v
          COMPLETED  CANCELLED
~~~

Mô hình cụ thể phải đến từ nghiệp vụ. Trạng thái “timeout” đôi khi không phải thất bại cuối: nên có WAITING_RECONCILIATION hoặc PAYMENT_UNKNOWN.

Một transition cần xác định:
- Trigger và dữ liệu cần thiết.
- Điều kiện guard.
- Side effect phải thực hiện.
- Phản ứng khi trigger lặp, đến muộn hoặc không hợp lệ.
- Deadline và chính sách phục hồi.
- Có thể hủy/bù trừ hay đã vượt pivot step.

State machine giúp kiểm soát cả hai cách điều phối: orchestration có thể dùng nó ở coordinator; choreography có thể dùng state machine cục bộ của từng dịch vụ và một projection để theo dõi toàn bộ.

## 12. Đảm bảo lưu state và phát sự kiện: transactional outbox

Một lỗi kinh điển:

~~~text
1. Database commit Order(PENDING) thành công
2. Process crash trước khi publish OrderPlaced
3. Không ai biết để giữ tồn kho / xử lý tiếp
~~~

Nếu đảo thứ tự publish trước commit, consumer có thể thấy event của một đơn mà database cuối cùng không lưu.

**Transactional outbox** giải quyết khoảng trống này bằng cách ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng một giao dịch cục bộ:

~~~text
Ordering local DB transaction:
  UPDATE orders SET status='PENDING'
  INSERT INTO outbox(event_id, event_type, payload, ...)
COMMIT
         |
         v
Outbox relay / CDC
         |
         v
Message broker
         |
         v
Consumers
~~~

Outbox giúp ghi bền **ý định phát event** cùng trạng thái ứng dụng. Relay có thể gửi lại một event sau crash; consumer phải xử lý idempotent. Outbox không tự bảo đảm “toàn hệ thống xử lý chính xác một lần”.

### Ví dụ SQL minh họa

~~~sql
BEGIN;

INSERT INTO orders (
    id, customer_id, status
) VALUES (
    :order_id, :customer_id, 'PENDING'
);

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload_json, published
) VALUES (
    :event_id, :order_id, 'OrderPlaced', :payload, FALSE
);

COMMIT;
~~~

Cú pháp chỉ mô tả ý tưởng. Hệ thống thật cần unique key, xử lý concurrent transactions, khả năng claim/poll outbox an toàn, retry, backoff và lưu metadata cần thiết.

Trong orchestration, coordinator cũng có thể dùng outbox để ghi **workflow state + command pending** trước khi gửi command. Mô hình outbox không dành riêng cho choreography.

## 13. Idempotency và sự kiện lặp

Message broker và network thường có thể giao hàng ít nhất một lần (at-least-once) hoặc làm client retry do timeout. Cùng một ReserveInventory có thể xuất hiện hai lần. Nếu cứ trừ tồn thêm lần nữa thì sẽ bán thiếu hoặc giữ hàng quá mức.

Một consumer an toàn cần có quy tắc:
- Có định danh event/command bền vững.
- Biết mình đã xử lý định danh đó chưa.
- Bảo vệ thao tác domain và ghi nhận đã xử lý trong transaction thích hợp.
- Nếu nhận lại thì trả/ghi lại kết quả tương thích mà không thực hiện side effect lần hai.
- Không giả định mọi side effect bên ngoài cũng transaction được với database.

Ví dụ bảng inbox:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    message_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Pseudo-flow trong một transaction cục bộ:

~~~text
BEGIN
  nếu (consumer_name, message_id) đã xử lý:
      COMMIT; acknowledge; return

  validate command/event
  apply domain transition một cách nguyên tử
  insert processed_messages(consumer_name, message_id)
  insert outbox event nếu cần
COMMIT
ACK message
~~~

Nếu nhiều consumer xử lý cùng ID đồng thời, chỉ một ràng buộc unique hay thao tác atomic thực sự mới ngăn được race. Cần xác minh semantics của DB, retry và transaction isolation.

**Idempotency theo message ID** không luôn đủ để chống hai yêu cầu nghiệp vụ trùng nhưng có message ID khác nhau. Với thanh toán/đặt hàng, có thể cần thêm business idempotency key, unique orderId hoặc payment intent có thẩm quyền.

### 13.1. “Exactly once” cần diễn đạt chính xác

Một số broker hỗ trợ giao dịch hoặc exactly-once processing trong phạm vi nhất định. Điều đó không có nghĩa một lời gọi HTTP đến PSP hoặc một cập nhật trên database khác tự động trở thành một phần của cùng giao dịch.

Khi thiết kế workflow, nên nêu rõ phạm vi cam kết:
- Phát/nhận message trong broker.
- Ghi local DB và outbox.
- Gọi provider bên ngoài.
- Bất biến nghiệp vụ sau retry.

Mục tiêu thực tế thường là **hiệu ứng nghiệp vụ không bị nhân đôi** thông qua idempotency, deduplication, versioning và reconcile.

## 14. Thứ tự sự kiện, stale event và concurrency

Trong choreography, event của cùng một đơn có thể:
- Đến muộn do retry.
- Đến nhiều lần.
- Đến khác thứ tự dự kiến.
- Được xử lý song song bởi các instance consumer.

Ví dụ PaymentAuthorized đến trước InventoryReserved do hai topic/partition khác nhau. Không nên vì thiếu event kia mà tự xác nhận đơn.

Một phương pháp:
1. Sử dụng orderId làm correlation key.
2. Lưu những điều kiện đã hoàn tất cho từng orderId.
3. Chỉ chuyển order sang CONFIRMED khi đủ điều kiện và transition hợp lệ.
4. Dùng version/sequence hoặc optimistic locking để ngăn cập nhật cũ ghi đè state mới.
5. Nếu quá hạn chưa đạt điều kiện, kích hoạt timeout/reconciliation theo chính sách.

**Event ordering** thường chỉ được bảo đảm trong phạm vi cụ thể của broker, như một partition theo key. Không suy diễn thành thứ tự toàn cục giữa mọi topic và mọi service.

Orchestration cũng có vấn đề tương tự khi coordinator gửi hai command song song rồi nhận response lệch thứ tự. Coordinator phải giữ state theo workflowId và kiểm tra mỗi result còn hợp lệ với bước hiện tại hay không.

## 15. Timeout, retry và trạng thái chưa biết

Một phản hồi không đến đúng hạn không cho biết chắc thao tác thất bại.

Ví dụ:

~~~text
Orchestrator → AuthorizePayment
                     |
                PSP xử lý xong
                     |
               Response bị mất
                     |
Orchestrator nhận TIMEOUT
~~~

Nếu gửi AuthorizePayment mới với key khác, người dùng có thể bị giữ tiền hai lần. Nếu hủy đơn ngay, nghiệp vụ có thể mâu thuẫn với trạng thái PSP đã authorize.

Cần quy trình:
- Gửi stable idempotency key tới PSP khi contract hỗ trợ.
- Khi timeout, đánh dấu kết quả UNKNOWN/RECONCILING.
- Tra cứu trạng thái bằng paymentId/reference có thẩm quyền.
- Xử lý webhook/event đến muộn và duplicate.
- Chỉ xác nhận/void/refund sau khi đã kiểm tra trạng thái phù hợp.
- Có timer, retry với exponential backoff và giới hạn số lần.
- Có manual intervention path khi không thể phân giải tự động.

Chính sách này áp dụng cho cả orchestration và choreography. Sự khác biệt chủ yếu ở **nơi điều phối việc reconcile và nơi lưu tiến độ**.

## 16. Orchestrator không đồng nghĩa synchronous call chain

Một hiểu lầm là orchestration luôn như sau:

~~~text
A -> B HTTP -> C HTTP -> D HTTP -> response
~~~

Một chuỗi gọi đồng bộ như vậy có thể tạo latency và lỗi dây chuyền. Orchestration hiện đại thường dùng command bất đồng bộ, event kết quả, timer và state bền vững:

~~~text
Orchestrator --command: ReserveInventory--> Broker --> Inventory
Orchestrator <--event: InventoryReserved---- Broker <-- Inventory
Orchestrator --command: AuthorizePayment---> Broker --> Payments
Orchestrator <--event: PaymentAuthorized---- Broker <-- Payments
~~~

Bản chất vẫn là một thành phần **quyết định bước nào thực hiện tiếp**, dù transport là asynchronous.

Ngược lại, choreography cũng có thể dùng HTTP cho một số thao tác truy vấn cục bộ, dù quy trình nghiệp vụ chính được kích hoạt bằng event. Không nên dùng tên giao thức để kết luận mô hình workflow.

## 17. Ví dụ cấu trúc Java/Spring Boot cho orchestration

Một tổ chức package minh họa:

~~~text
checkout-service/
  domain/
    CheckoutWorkflow.java
    CheckoutStatus.java
  application/
    StartCheckoutUseCase.java
    OnInventoryResultUseCase.java
    OnPaymentResultUseCase.java
    CheckoutCoordinator.java
    port/
      WorkflowStore.java
      CommandOutbox.java
  adapter/
    in/rest/CheckoutController.java
    in/messaging/WorkflowEventListener.java
    out/persistence/WorkflowJpaAdapter.java
    out/messaging/CommandOutboxAdapter.java
  config/
~~~

Orchestrator có thể coi mỗi business workflow là một state machine. Những participant như Inventory và Payments tiếp tục có domain và application use cases riêng.

### 17.1. Pseudocode hướng Java

~~~java
public enum CheckoutStep {
    WAITING_INVENTORY,
    WAITING_PAYMENT,
    COMPENSATING,
    COMPLETED,
    FAILED
}

public record InventoryResult(
        String workflowId,
        String reservationId,
        boolean reserved) {}

public interface CheckoutWorkflowRepository {
    CheckoutWorkflow loadForUpdate(String workflowId);
    void save(CheckoutWorkflow workflow);
}

public interface CheckoutCommandOutbox {
    void enqueueAuthorizePayment(
            String workflowId,
            String orderId,
            String reservationId);
    void enqueueReleaseInventory(
            String workflowId,
            String reservationId);
}

public final class CheckoutCoordinator {
    private final CheckoutWorkflowRepository workflows;
    private final CheckoutCommandOutbox outbox;

    public CheckoutCoordinator(
            CheckoutWorkflowRepository workflows,
            CheckoutCommandOutbox outbox) {
        this.workflows = workflows;
        this.outbox = outbox;
    }

    // Gọi trong một giao dịch cục bộ phù hợp.
    public void onInventoryResult(InventoryResult result) {
        CheckoutWorkflow wf =
                workflows.loadForUpdate(result.workflowId());

        if (wf.step() != CheckoutStep.WAITING_INVENTORY) {
            return; // kết quả trùng/cũ được xử lý theo policy riêng
        }

        if (result.reserved()) {
            wf.inventoryReserved(result.reservationId());
            outbox.enqueueAuthorizePayment(
                    wf.id(), wf.orderId(), result.reservationId());
        } else {
            wf.inventoryRejected();
        }

        workflows.save(wf);
    }
}
~~~

Các kiểu CheckoutWorkflow và method được rút gọn để diễn đạt **điểm lưu workflow state và command intent**. Đây không phải đoạn code chạy độc lập đầy đủ: cần xây transaction boundary, idempotency/dedup, version lock, timer, schema, participant contract và error path thực tế. Nếu đã có workflow engine, có thể biểu diễn các transition trong định nghĩa workflow thay vì tự cài repository.

### 17.2. Điều phối thuộc service nào?

Có thể đặt coordinator tại:
- Dịch vụ sở hữu trải nghiệm/quy trình chính, ví dụ Ordering hoặc Checkout.
- Một workflow/process service riêng khi quy trình có vòng đời độc lập và được nhiều hệ thống sử dụng.
- Một workflow engine được vận hành như nền tảng chung, nhưng mỗi domain team vẫn sở hữu định nghĩa workflow của mình.

Không nên mặc định tạo một “super orchestrator” sở hữu mọi workflow trong công ty. Nó có thể trở thành điểm nghẽn tổ chức và triển khai.

## 18. Ví dụ Spring Boot cho choreography

Một consumer của Inventory xử lý OrderPlaced, bảo vệ reservation rồi ghi event kết quả vào outbox.

~~~java
@Component
public final class OrderPlacedListener {
    private final ReserveForOrderUseCase reserve;

    public OrderPlacedListener(ReserveForOrderUseCase reserve) {
        this.reserve = reserve;
    }

    @KafkaListener(topics = "order.placed.v1")
    public void onMessage(OrderPlacedEvent event) {
        reserve.execute(new ReserveForOrderCommand(
                event.eventId(),
                event.orderId(),
                event.items()));
    }
}
~~~

Use case (minh họa trách nhiệm):

~~~text
ReserveForOrderUseCase:
  - Kiểm tra eventId/orderId đã xử lý chưa.
  - Bảo vệ invariant tồn kho qua transaction/conditional update.
  - Lưu reservation hoặc kết quả từ chối.
  - Ghi InventoryReserved / InventoryReservationRejected vào outbox.
  - Commit local transaction, sau đó listener mới ACK đúng policy.
~~~

Với một consumer của Payments:

~~~java
@Component
public final class InventoryReservedListener {
    private final StartPaymentUseCase payment;

    public InventoryReservedListener(StartPaymentUseCase payment) {
        this.payment = payment;
    }

    @KafkaListener(topics = "inventory.reserved.v1")
    public void onMessage(InventoryReservedEvent event) {
        payment.execute(new StartPaymentCommand(
                event.eventId(),
                event.orderId(),
                event.reservationId()));
    }
}
~~~

Đoạn code chỉ minh họa cách các event kích hoạt application use case. Trong production cần định nghĩa schema rõ ràng, tương thích phiên bản, security, durable inbox/outbox, retry và đối soát thanh toán. Sự kiện chỉ thông báo “hàng đã giữ”, không tự chứa một lời bảo đảm thanh toán đã thành công.

## 19. Phân biệt broker, event bus, mediator và orchestrator

Các thuật ngữ thường bị lẫn:

| Thành phần | Vai trò chính | Có tự quyết định workflow không? |
| --- | --- | --- |
| Message broker | Nhận, lưu/chuyển phát message theo cơ chế của broker | Không tự quyết định nghiệp vụ |
| Event bus | Kênh phân phối các thông báo sự kiện cho subscriber | Không, trừ khi được gắn thêm logic nghiệp vụ |
| API gateway | Nhận, định tuyến, bảo vệ giao tiếp đầu vào | Không nên là coordinator cho business saga dài |
| Orchestrator | Lưu state và chọn bước nghiệp vụ tiếp theo | Có |
| Process manager | Theo dõi một tiến trình lâu dài và ra quyết định theo event | Có thể là một dạng orchestration |
| Event handler/consumer | Phản ứng với event theo trách nhiệm cục bộ | Có quyết định cục bộ; không nhất thiết chỉ đạo toàn bộ |
| Workflow engine | Hạ tầng thực thi workflow, timer, state, retry | Thực thi quy tắc do ứng dụng cấu hình/định nghĩa |

Kafka là hạ tầng truyền/ghi message; việc dùng Kafka không chứng minh đã có event-driven business choreography. Ngược lại, một orchestrator được triển khai qua Kafka vẫn là orchestration nếu điều phối logic nằm ở đó.

## 20. Khi nào orchestration phù hợp hơn?

Orchestration thường đáng cân nhắc khi:

1. **Workflow nhiều bước với điều kiện rẽ nhánh rõ:** ví dụ hoàn tiền một phần, xác nhận rủi ro, giữ hàng, chọn carrier và chuyển trạng thái theo chính sách.
2. **Cần theo dõi tiến độ end-to-end:** nhân viên hỗ trợ muốn biết đơn đang chờ bước nào, đến hạn khi nào và ai cần xử lý.
3. **Bù trừ phức tạp:** mỗi lỗi cần hành động khác nhau tùy các bước đã hoàn thành.
4. **Có deadline, timer, retry và manual approval:** chờ thanh toán 15 phút, cấp quyền sau kiểm duyệt, escalation khi SLA sắp hết.
5. **Quy trình có owner cụ thể:** một team chịu trách nhiệm về trạng thái hoàn thành xuyên nhiều participant.
6. **Cần thay đổi thứ tự bước mà không sửa nhiều participant:** thêm fraud check trước capture, đổi thứ tự authorization và reservation tùy sản phẩm.

Đổi lại, coordinator cần vận hành bền vững, có high availability phù hợp, quản lý version workflow và tránh coupling không cần thiết với chi tiết của participant.

### Dấu hiệu coordinator quá phức tạp

- Nó giữ copy đầy đủ domain model của mọi dịch vụ.
- Nó đọc trực tiếp DB của participant.
- Mọi thay đổi nhỏ ở domain bắt buộc sửa coordinator dù contract không đổi.
- Nó quyết định thay cho participant liệu một inventory reservation có hợp lệ hay không.
- Tất cả workflow của nhiều bộ phận nằm trong một service khổng lồ và phải deploy cùng nhau.

Khi đó cần xem lại ownership và phân ranh giới quy trình.

## 21. Khi nào choreography phù hợp hơn?

Choreography thường phù hợp khi:

1. **Phản ứng độc lập đối với sự kiện đã xảy ra:** OrderConfirmed dẫn tới gửi email, cập nhật analytics, tạo loyalty points.
2. **Có nhiều subscriber không cần biết nhau:** thêm reporting consumer không cần thay publisher.
3. **Dịch vụ có boundary và ownership rõ:** mỗi domain tự quyết định logic phản ứng, không cần một luồng điều khiển duy nhất.
4. **Chấp nhận eventual consistency:** projection cập nhật sau, dữ liệu tìm kiếm và analytics chậm một khoảng.
5. **Sự kiện là business fact ổn định:** hợp đồng có ý nghĩa rõ, không cần rò rỉ cấu trúc nội bộ của publisher.
6. **Có năng lực vận hành event-driven:** schema governance, outbox, retry, DLQ, tracing, monitoring và kiểm thử chuỗi event.

Choreography dễ phù hợp cho các **phản ứng phụ độc lập** hơn là các workflow có quá nhiều rẽ nhánh, điều kiện hoàn thành và compensation. Tuy nhiên vẫn có thể sử dụng cho các Saga tương đối đơn giản với ownership rõ ràng.

### Dấu hiệu choreography bị lạm dụng

- Muốn hiểu luồng đặt hàng phải mở code của mười consumer khác nhau.
- Nhiều event có tên giống command nhưng không có owner tổng thể.
- Thay một bước quy trình bắt buộc thay hàng loạt service.
- Hai consumer phát event kích hoạt lẫn nhau gây vòng lặp.
- Không ai phát hiện order treo ở trạng thái PENDING.
- Event schema phụ thuộc trực tiếp vào JPA entity hoặc bảng DB.

Khi ấy nên cân nhắc tập trung một phần workflow vào process manager hoặc orchestrator, giữ các event thuần để công bố kết quả.

## 22. Kết hợp hai cách trong một hệ thống

Trong thực tế, **hybrid** thường là lựa chọn hợp lý:
- Orchestrator điều hành **critical path** của checkout.
- Các participant phát event khi command đã được thực thi.
- Notification, Search, Analytics và Loyalty subscribe OrderConfirmed độc lập.
- Một số domain khác có choreography riêng, miễn semantics rõ.

~~~text
                  Checkout Orchestrator
                    /      |       \
                   v       v        v
               Inventory Payments Ordering
                  |        |        |
                  +-- result events--+
                             |
                             v
                     OrderConfirmed
                             |
                     Event broker
                    /      |      \
                   v       v       v
             Notification Search Analytics
                consumer   consumer consumer
~~~

Đây là một ví dụ phân chia trách nhiệm, không bắt buộc mỗi consumer hay orchestrator là một deploy riêng. Trong mô hình này:
- **Coordinator** chịu trách nhiệm quy trình tới OrderConfirmed.
- **Participant** giữ bất biến của miền mình.
- **Events** mô tả các kết quả đã có thể công bố.
- **Downstream consumers** phản ứng độc lập và không nên ảnh hưởng kết quả checkout trừ khi business contract yêu cầu.

Cách kết hợp này tránh bắt critical flow phụ thuộc vào mọi hành động phụ như gửi email hoặc cập nhật dashboard, đồng thời giúp giữ một nguồn quan sát rõ cho trạng thái đặt hàng.

## 23. Các tiêu chí lựa chọn nên đo

Bảng sau giúp chuyển tranh luận kiến trúc thành quyết định có căn cứ.

| Tiêu chí | Câu hỏi đánh giá | Tín hiệu thường nghiêng về |
| --- | --- | --- |
| Mức phức tạp | Có nhiều nhánh, timeout, compensation không? | Orchestration |
| Phản ứng độc lập | Nhiều hệ thống chỉ cần nghe một sự thật đã xảy ra? | Choreography |
| Ownership workflow | Một nhóm chịu trách nhiệm end-to-end? | Orchestration |
| Độc lập thay đổi | Các consumer thêm/bớt liên tục mà publisher không cần biết? | Choreography |
| Quan sát tiến độ | Cần một dashboard trạng thái từng bước, SLA/timer? | Orchestration thuận tiện hơn |
| Tải bất đồng bộ | Nhiều consumer xử lý background với workload khác nhau? | Choreography/event-driven |
| Coupling hiện có | Có cần sửa nhiều service khi đổi thứ tự bước? | Cân nhắc orchestration |
| Rủi ro lỗi | Compensation khó, có trạng thái UNKNOWN? | Orchestration thường dễ kiểm soát |
| Năng lực vận hành | Team có broker governance, tracing, DLQ, replay không? | Ảnh hưởng mạnh đến choreography |
| Latency mục tiêu | Có yêu cầu trả kết quả ngay hay chấp nhận trạng thái PENDING? | Quyết định sync/async, không quyết định duy nhất orchestration/choreography |

Không nên mặc định choreography “scale vô hạn” hay orchestration “luôn chậm”. Một coordinator có thể scale ngang với workflow state bền vững; một choreography có thể nghẽn ở database consumer hoặc message partition. Hiệu năng phải được đo theo workload, throughput, latency và thời gian hoàn tất nghiệp vụ.

## 24. Độ tin cậy khi broker hoặc dịch vụ bị lỗi

Cả hai cách cần định nghĩa rõ failure behavior.

| Sự cố | Orchestration | Choreography |
| --- | --- | --- |
| Participant tạm thời không phản hồi | Coordinator lưu trạng thái, timeout/retry/reconcile | Consumer giữ message/offset và retry theo policy |
| Coordinator chết giữa quy trình | Phục hồi từ durable workflow state | Không có coordinator chung, nhưng từng consumer phải khôi phục state |
| Event bị gửi lặp | Coordinator/result consumer deduplicate | Mỗi subscriber idempotent |
| Event bị gửi trễ/đảo thứ tự | Kiểm tra state và version tại coordinator | Kiểm tra state và version ở consumer liên quan |
| Compensation thất bại | Coordinator có timer và retry/manual path | Phải có subscriber/owner theo dõi compensation |
| Một consumer xuống dài | Critical step có thể chờ; workflow hiện trạng thái | Broker giữ backlog nếu chính sách lưu trữ cho phép, consumer bắt kịp sau |
| Hợp đồng event đổi không tương thích | Result/command adapters có thể lỗi | Nhiều consumer có thể lỗi đồng loạt |

Với broker, cần xem retention, delivery semantics, offset/ack và cách replay. Một message đã ACK nhưng consumer chưa commit nghiệp vụ có thể bị mất tác dụng; một message commit nghiệp vụ nhưng chưa ACK có thể được gửi lại. Điều này giải thích vì sao local transaction, inbox/outbox và idempotency quan trọng.

## 25. Quan sát luồng end-to-end

Một thao tác qua nhiều dịch vụ cần có dấu vết thống nhất. Những trường hữu ích trong command/event envelope:

~~~json
{
  "eventId": "evt-6c2",
  "eventType": "InventoryReserved",
  "schemaVersion": 1,
  "aggregateId": "order-471",
  "workflowId": "checkout-471",
  "correlationId": "corr-471",
  "causationId": "evt-order-placed",
  "occurredAt": "2026-01-01T10:00:00Z",
  "producer": "inventory-service",
  "data": {
    "reservationId": "res-888"
  }
}
~~~

Ví dụ chỉ là một contract mẫu; trong hệ thống thực phải quản trị PII, kích thước payload, version compatibility và nguồn thời gian đáng tin cậy.

Ý nghĩa:
- **eventId:** định danh duy nhất để deduplicate event.
- **workflowId:** nối các bước của cùng một tiến trình.
- **correlationId:** nối logs/traces theo một request hoặc business transaction.
- **causationId:** chỉ ra event/command nào làm phát sinh hành động hiện tại.
- **aggregateId:** định danh thực thể để partition/order theo key khi cần.
- **schemaVersion:** hỗ trợ thay đổi contract có kiểm soát.

Với orchestration, dashboard có thể đọc workflow state trực tiếp. Với choreography, thường cần dựng projection hoặc truy vấn trace từ nhiều service. Cả hai nên có:
- Structured logs theo correlationId, orderId, workflowId.
- Distributed tracing cho cả RPC và messaging context.
- Metric về pending workflows, age của event trong queue, DLQ, retry, compensation và business failure.
- Alert khi một trạng thái tồn tại quá deadline được thỏa thuận.
- Khả năng truy vấn “order-471 đang ở bước nào?” bằng dữ liệu có thẩm quyền.

Không đưa toàn bộ thông tin nhạy cảm hoặc token vào event chỉ vì thuận tiện debug. Các consumer có quyền truy cập khác nhau nên event contract phải giới hạn dữ liệu cần thiết.

## 26. Bảo mật và tính tin cậy của sự kiện

Trong hệ thống đa dịch vụ, broker và API không tự làm cho message đáng tin về nghiệp vụ.

Cần xác định:
- Publisher nào được quyền phát sự kiện OrderConfirmed hoặc PaymentCaptured?
- Consumer có kiểm tra schema, version và nguồn phát không?
- Có cơ chế ACL theo topic, mTLS hoặc xác thực service-to-service không?
- Dữ liệu cá nhân trong payload có vượt nhu cầu của consumer không?
- Có chống replay và lệnh trùng gây hiệu ứng tài chính không?
- Trong orchestration, ai có quyền gửi command hoàn tiền hoặc hủy shipment?
- Có audit log cho quyết định nhạy cảm và human override không?

Ví dụ một thông điệp PaymentAuthorized giả không được khiến Ordering tự chuyển đơn sang CONFIRMED nếu nguồn phát không đáng tin hoặc trạng thái giao dịch chưa được Payments xác nhận theo contract.

Bảo mật phải đi cùng invariant của domain: xác thực message là cần thiết, nhưng chưa đủ để biết một business transition là hợp lệ.

## 27. Kiểm thử orchestration và choreography

### 27.1. Orchestration

Nên kiểm thử các transition của coordinator:
- InventoryReserved → gửi AuthorizePayment.
- InventoryRejected → không gọi thanh toán, kết thúc/hủy theo policy.
- PaymentRejected → gửi compensation.
- PaymentTimeout → chuyển sang UNKNOWN/RECONCILING, không tự nhân đôi tiền.
- Result trùng → không thực hiện bước kế tiếp hai lần.
- Crash/restart → khôi phục đúng trạng thái và command còn chờ.
- Workflow cũ chạy tiếp đúng version khi triển khai định nghĩa mới.

Mock/fake port phù hợp cho unit test, nhưng cần integration test thực cho workflow persistence, broker, timer và transaction boundary.

### 27.2. Choreography

Nên kiểm thử mỗi consumer:
- Đúng loại event, đúng schema → áp dụng business transition hợp lệ.
- Event trùng, đến trễ, đảo thứ tự → hiệu ứng vẫn đúng.
- Local DB commit nhưng relay chưa publish → outbox gửi lại.
- Consumer lỗi giữa xử lý và ACK → retry không nhân đôi.
- Event không hợp lệ/không thể xử lý → DLQ và alert đúng.
- Schema version mới/cũ → consumer tương thích trong thời gian triển khai lệch.
- Nhiều consumer cùng phản ứng → không có vòng lặp hoặc side effect ngoài dự kiến.

Contract tests giữa publisher và consumer giúp phát hiện trường bị đổi tên, enum mới, hành vi thay đổi mà unit test riêng của từng service không nhận ra.

### 27.3. End-to-end và chaos test

Chạy workflow ở các kịch bản:
1. Happy path.
2. Inventory thiếu hàng.
3. Payment rejected.
4. Payment đã thành công nhưng phản hồi bị mất.
5. Broker tạm ngừng rồi phục hồi.
6. Consumer hoặc coordinator restart giữa quá trình.
7. Duplicate và out-of-order event.
8. Compensation thất bại rồi hồi phục.
9. Một workflow kéo dài vượt deadline.
10. Triển khai phiên bản mới khi vẫn còn workflow cũ.

Đánh giá cả **business correctness**, không chỉ “HTTP trả 200” hay “message được tiêu thụ”. Ví dụ một đơn bị hủy phải có trạng thái reservation và payment phù hợp, không tồn tại side effect bị bỏ quên.

## 28. Lộ trình chuyển đổi khi hệ thống đã có chuỗi RPC dài

Giả sử hệ thống ban đầu như sau:

~~~text
Gateway -> Ordering -> Inventory -> Payments -> Shipping
                  (nhiều HTTP call chờ đồng bộ)
~~~

Một lỗi tại Payments có thể kéo dài response và làm giữ tài nguyên ở Ordering. Không nhất thiết phải chuyển mọi thứ sang choreography ngay.

Có thể tiến hành:

1. **Phân loại bước bắt buộc trước phản hồi:** bước nào quyết định trực tiếp sự thành công mà người dùng cần biết ngay; bước nào có thể chuyển sang PENDING?
2. **Làm rõ dữ liệu sở hữu và transaction:** ghi state cục bộ, loại bỏ giả định rollback toàn hệ thống.
3. **Định nghĩa command/event contract:** không publish thẳng JPA entity; có định danh và version.
4. **Thêm state machine cho workflow:** xác định trạng thái chưa hoàn tất, timeout, bù trừ và reconcile.
5. **Áp dụng outbox/inbox cho đường chuyển trạng thái cần độ tin cậy cao.**
6. **Chọn nơi giữ workflow logic:** orchestrator nếu cần điều phối chặt; event consumers nếu phản ứng độc lập.
7. **Thiết lập metrics/tracing, kiểm thử duplicate và failure path.**
8. **Tách các side effect phụ:** notification, analytics, search projection qua event nếu phù hợp.
9. **Đo lại latency, throughput, tỷ lệ đơn hoàn tất, số đơn treo và chi phí vận hành.**

Mục tiêu là cải thiện đúng vấn đề: giảm coupling bất lợi, hạn chế lỗi dây chuyền và bảo vệ invariant. Việc dùng message broker chỉ là một công cụ thực hiện.

## 29. Các sai lầm phổ biến

### “Có Kafka nghĩa là choreography”

Sai. Kafka chuyển message. Nếu một coordinator nhận result và ra lệnh bước kế tiếp, logic vẫn là orchestration.

### “Orchestration bắt buộc gọi HTTP đồng bộ”

Sai. Coordinator có thể gửi command bất đồng bộ, chờ event và dùng durable workflow state.

### “Choreography nghĩa là không có business process owner”

Sai. Mỗi trạng thái nghiệp vụ có owner; việc hoàn tất workflow vẫn phải được xác định và quan sát.

### “Eventual consistency nghĩa là có thể để dữ liệu sai tùy ý”

Sai. Nó cho phép trạng thái tạm thời ở các nơi khác nhau, nhưng business invariant và mức chấp nhận độ trễ phải được xác định. Bán vượt tồn hoặc ghi nhận tiền sai không thể biện minh chỉ bằng nhãn eventual.

### “Saga là distributed ACID transaction”

Sai. Saga là chuỗi local transaction và compensation; side effect ngoài có thể không đảo ngược hoàn toàn và trạng thái trung gian có thể quan sát được.

### “Một event chỉ phát một lần”

Không nên giả định. Network, broker và retry có thể tạo duplicate. Thiết kế idempotency ở nơi thực thi side effect.

### “Timeout nghĩa là thao tác thất bại”

Không chắc. Có thể kết quả đã thành công nhưng phản hồi bị mất. Với thanh toán cần trạng thái UNKNOWN và reconcile.

### “Thêm consumer không ảnh hưởng ai”

Một consumer mới có thể tạo tải, gọi API, phát event mới, tạo chu trình hoặc ảnh hưởng quyền truy cập dữ liệu. Choreography giúp giảm coupling về danh tính consumer nhưng không loại bỏ coupling nghiệp vụ.

### “Tập trung workflow làm hệ thống luôn dễ bảo trì hơn”

Không đúng nếu orchestrator trở thành nơi chứa mọi domain rule của mọi dịch vụ, gây nghẽn team và deploy. Cần phân tách trách nhiệm.

### “Chia nhỏ mọi bước thành event là tốt”

Nếu các bước bắt buộc phải thực hiện nguyên tử trong cùng một bounded context, chia thành nhiều event có thể chỉ làm tăng eventual consistency, độ trễ và recovery logic. Không nên phân tán vì lý do hình thức.

## 30. Checklist lựa chọn cách phối hợp

Trước khi quyết định, hãy trả lời:

- [ ] Đã xác định rõ bounded context, owner và dữ liệu có thẩm quyền của từng bước chưa?
- [ ] Workflow có bao nhiêu trạng thái, nhánh và deadline?
- [ ] Những bước nào cần phản hồi đồng bộ, những bước nào có thể bất đồng bộ?
- [ ] Có trạng thái PENDING/UNKNOWN và đường reconcile khi kết quả không chắc chắn không?
- [ ] Từng side effect có thể đảo ngược hoặc bù trừ tới mức nào?
- [ ] Ai chịu trách nhiệm khi toàn bộ quy trình bị treo?
- [ ] Event có diễn đạt business fact, command có người nhận và ý nghĩa rõ không?
- [ ] Mỗi bước có idempotency key và khả năng nhận event trùng không?
- [ ] DB commit và việc publish command/event đã có cơ chế đảm bảo tương ứng chưa?
- [ ] Có xử lý message đến muộn hoặc khác thứ tự không?
- [ ] Có thể tìm tiến độ một orderId từ logs/state/traces trong thời gian chấp nhận được không?
- [ ] Có schema versioning, consumer contract test, retry/DLQ và alert không?
- [ ] Lợi ích giảm coupling hoặc tăng tự chủ có lớn hơn chi phí vận hành phân tán không?
- [ ] Nếu dùng hybrid, ranh giới giữa critical path và reaction phụ đã được nêu rõ chưa?

## 31. Bài tập tình huống

### Bài tập 1 — Nhận diện mô hình

Một dịch vụ Checkout nhận OrderCreated, gửi ReserveInventory, chờ InventoryReserved, rồi gửi AuthorizePayment. Khi PaymentRejected, Checkout gửi ReleaseInventory và đánh dấu thất bại.

**Câu hỏi:** Đây là orchestration hay choreography, dù dùng Kafka cho tất cả message?

**Gợi ý:** Đây là orchestration vì Checkout giữ state và quyết định từng bước. Broker chỉ là phương tiện truyền command/event.

### Bài tập 2 — Thêm email xác nhận

Sau OrderConfirmed, EmailService và AnalyticsService đều cần phản ứng độc lập. Nếu EmailService ngừng hoạt động, không nên khiến đơn đã xác nhận bị rollback.

**Câu hỏi:** Phương thức phối hợp nào hợp lý và điều gì cần đảm bảo?

**Gợi ý:** Công bố OrderConfirmed qua integration event có schema/version, dùng outbox tại Ordering và idempotent consumer. Email/Analytics xử lý async, có retry/DLQ; critical state không phụ thuộc gửi email.

### Bài tập 3 — Thanh toán timeout

Checkout gửi AuthorizePayment và nhận timeout. Người dùng đã được ngân hàng giữ tiền nhưng webhook đến muộn.

**Câu hỏi:** Vì sao không nên lập tức gửi payment mới hoặc cancel cứng?

**Gợi ý:** Kết quả là UNKNOWN, không phải rejected. Dùng stable idempotency key, tra cứu payment intent, xử lý webhook idempotent và reconcile trước khi chốt trạng thái.

### Bài tập 4 — Event đến đảo thứ tự

Ordering nhận PaymentAuthorized trước InventoryReserved.

**Câu hỏi:** Có thể confirm order ngay không?

**Gợi ý:** Chỉ khi điều kiện nghiệp vụ cho phép. Nếu cần cả hai, lưu trạng thái đã nhận payment và chờ inventory; kiểm tra transition và version để tránh event muộn ghi đè.

### Bài tập 5 — Chuyển từ choreography sang orchestration

Một quy trình hoàn tiền hiện phân tán qua bảy consumer. Đổi thứ tự bước thường làm hỏng nhiều service; khi refund bị treo rất khó biết ai chịu trách nhiệm.

**Câu hỏi:** Có lý do chuyển một phần sang orchestration không?

**Gợi ý:** Có thể tập trung trạng thái workflow, deadline và compensation vào process manager, giữ mỗi participant tự bảo vệ domain rules và tiếp tục công bố business event cho consumer độc lập.

### Bài tập 6 — Thiết kế hybrid

Một hệ thống có quy trình tạo đơn với bước giữ tồn và thanh toán nhạy cảm, đồng thời cần loyalty points, email và tìm kiếm.

**Câu hỏi:** Nên áp dụng một mô hình duy nhất cho tất cả hay tách critical path với side effects?

**Gợi ý:** Có thể dùng orchestrator cho core Saga và event choreography cho loyalty/email/search. Nêu rõ thời điểm OrderConfirmed được công bố, owner và các chính sách reliability.

## 32. Kết luận

**Orchestration** làm rõ một nơi điều khiển tiến trình: ai đang chờ, bước nào tiếp theo, khi nào timeout và cần bù trừ ra sao. Nó đặc biệt hữu ích cho workflow có nhiều nhánh, thời gian chờ và điều kiện hoàn thành. **Choreography** cho phép các dịch vụ phản ứng với business events, thích hợp với những hoạt động có thể phát triển độc lập và chấp nhận eventual consistency, nhưng đòi hỏi quản trị hợp đồng và khả năng quan sát tốt.

Hai mô hình **không đối lập tuyệt đối** và không được phân biệt chỉ bằng HTTP so với Kafka. Một kiến trúc có thể điều phối tập trung phần nghiệp vụ trọng yếu, đồng thời công bố event để các chức năng khác phản ứng độc lập.

Để cả hai hoạt động đáng tin cậy, phải thiết kế rõ **nguồn sự thật, local transaction, state machine, timeout/UNKNOWN, idempotency, outbox/inbox, compensation, correlation và recovery**. Câu hỏi quyết định không phải “cách nào hiện đại hơn”, mà là “nơi nào nên sở hữu quyết định workflow để nghiệp vụ đúng, dễ thay đổi và có thể vận hành khi lỗi xảy ra?”.
