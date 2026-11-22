# Định danh yêu cầu để chống thực hiện lặp nghiệp vụ trong NoSQL

Một người dùng nhấn nút **Đặt hàng**. Máy chủ đã lưu đơn thành công nhưng phản hồi bị mất do kết nối mạng. Ứng dụng di động tưởng thao tác thất bại nên gửi lại yêu cầu. Nếu hệ thống tạo đơn mới ở mỗi lần nhận request, cùng một lần đặt hàng của người dùng có thể tạo hai đơn, giữ tồn kho hai lần, hoặc nguy hiểm hơn là thu tiền hai lần.

Đây là vấn đề **thực hiện lặp nghiệp vụ** (*duplicate execution*). Nó có thể xuất hiện ngay cả khi mã ứng dụng chạy đúng trong từng lần gọi, vì hệ thống phân tán phải chấp nhận timeout, retry, yêu cầu đồng thời và thông điệp được giao lại. Một giải pháp quan trọng là cấp **định danh yêu cầu** (*request ID*, thường dùng dưới dạng **idempotency key**) cho một ý định nghiệp vụ và buộc máy chủ nhận ra những lần gửi lặp của cùng ý định đó.

Trong NoSQL, cách triển khai cần xét kỹ **khóa định danh**, **thao tác ghi có điều kiện**, **ranh giới giao dịch**, **thời gian giữ dấu vết xử lý**, và **mức nhất quán khi nhiều request đến cùng lúc**.

## 1. Vì sao một yêu cầu có thể được thực hiện nhiều lần?

Hãy quan sát chuỗi sự kiện sau:

~~~mermaid
sequenceDiagram
    participant C as Ứng dụng
    participant A as API
    participant D as NoSQL
    C->>A: POST /orders (lần 1)
    A->>D: Tạo đơn O900
    D-->>A: Đã ghi thành công
    Note over A,C: Phản hồi bị mất trên mạng
    C->>A: POST /orders (retry)
    A->>D: Tạo thêm đơn O901?
    D-->>A: Đã ghi
    A-->>C: Thành công
~~~

API có thể nhận cùng một ý định nhiều lần bởi:

- **Người dùng nhấn hai lần** vào nút hoặc ứng dụng gửi lại khi chưa thấy phản hồi.
- **Client retry tự động** vì timeout, mất mạng hoặc HTTP 5xx.
- **Load balancer, API gateway hoặc service** thực hiện retry sau lỗi kết nối.
- **Hàng đợi thông điệp** giao lại một message khi consumer xử lý xong nhưng chưa xác nhận (*ack*).
- **Job định kỳ** chạy lại sau khi khởi động hoặc khôi phục từ checkpoint.
- **Hai luồng đồng thời** nhận cùng một request trước khi luồng nào ghi xong.

Một timeout chỉ cho biết phía gọi **chưa nhận được kết quả**, không chứng minh phía nhận **chưa thực hiện thao tác**. Vì vậy quy tắc “gặp timeout thì gửi lại” chỉ an toàn nếu hệ thống có cơ chế chống làm lặp tác động nghiệp vụ.

### 1.1. Tính idempotent là gì?

Trong toán học, phép toán idempotent thỏa:

~~~text
f(f(x)) = f(x)
~~~

Trong xử lý API, ý tưởng thực dụng là: **thực hiện nhiều lần cùng một yêu cầu đã được định danh phải tạo ra cùng tác động nghiệp vụ như thực hiện thành công một lần**.

Ví dụ:

| Thao tác | Gửi lại y nguyên | Đã an toàn chưa? |
| --- | --- | --- |
| Đọc sản phẩm theo ID | Chỉ đọc dữ liệu | Thông thường không gây tác động ghi |
| Đặt trạng thái đơn thành PAID | Ghi cùng một trạng thái | Có thể idempotent ở mức giá trị trường, nhưng chưa đủ nếu mỗi lần đều phát hành sự kiện thu tiền |
| Tăng lượt xem thêm 1 | Mỗi lần tăng bộ đếm | Không idempotent nếu không chống lặp |
| Tạo đơn mới với ID ngẫu nhiên | Mỗi lần sinh một đơn | Không idempotent theo mặc định |
| Thu tiền 100.000 VND | Mỗi lần có thể ghi nhận một giao dịch | Phải có định danh và bảo vệ chống xử lý trùng |

Lưu ý: **trả về cùng HTTP status không đồng nghĩa nghiệp vụ không bị lặp**. Ngược lại, API có thể trả HTTP 201 ở lần đầu và HTTP 200 ở lần retry nhưng vẫn idempotent nếu cả hai đều tham chiếu cùng một đơn và chỉ có một tác động tạo đơn. Hợp đồng API quyết định cách trả kết quả.

### 1.2. “At-least-once” không có nghĩa “exactly-once”

Trong nhiều hệ thống, cách xử lý phổ biến là **giao lại ít nhất một lần** (*at-least-once delivery*) để tránh thất lạc yêu cầu. Điều đó có nghĩa cùng thông điệp có thể đến nhiều lần.

**Xử lý idempotent** cho phép nhận lại thông điệp mà không nhân đôi tác động. Tuy nhiên, chỉ thêm một cột request ID không tự tạo ra bảo đảm *exactly-once end-to-end*. Nếu một quy trình đồng thời ghi cơ sở dữ liệu và gọi cổng thanh toán bên ngoài, ta vẫn phải giải quyết ranh giới giữa hai hệ thống.

## 2. Phân biệt các loại định danh

Cùng ứng dụng có thể dùng nhiều ID, nhưng mỗi ID trả lời một câu hỏi khác nhau.

| Định danh | Trả lời câu hỏi | Ví dụ | Phạm vi |
| --- | --- | --- | --- |
| **Request ID** | Lần gửi này thuộc ý định nào? | 8b8b… | Một thao tác logic có thể được gửi nhiều lần |
| **Idempotency key** | Các lần gọi nào phải được coi là cùng một thao tác? | UUID do client sinh | Chống thực hiện lặp nghiệp vụ |
| **Entity/business ID** | Đối tượng nghiệp vụ nào được tạo hoặc sửa? | orderId = O900 | Vòng đời đơn hàng |
| **Event/message ID** | Thông điệp nào đang được xử lý? | evt-7082 | Chống xử lý lặp khi consumer nhận lại |
| **Trace/correlation ID** | Những log nào thuộc cùng chuỗi gọi? | trace-abc | Quan sát và chẩn đoán |
| **Version/ETag** | Dữ liệu ở phiên bản nào trước khi cập nhật? | version = 7 | Chống ghi đè đồng thời |

Không nên mặc định **trace ID** là **idempotency key**: một trace mới có thể được tạo mỗi khi retry, trong khi idempotency key cần **giữ nguyên giữa các lần retry của cùng một ý định**.

Ngược lại, khi người dùng đặt thêm một đơn thật sự, ứng dụng **phải sinh idempotency key mới**. Nếu dùng mã khách hàng làm khóa chống lặp cho mọi lần đặt hàng, hệ thống có thể ngăn nhầm các đơn hợp lệ.

### 2.1. Một ý định, một khóa

Quy tắc dễ áp dụng:

~~~text
Ý định A: tạo một đơn gồm P101 x 2
  lần gửi 1 -> Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
  lần gửi 2 -> Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
  lần gửi 3 -> Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

Ý định B: tạo một đơn khác, dù giỏ hàng giống hệt
  lần gửi 1 -> Idempotency-Key: b36ed48c-876d-48a2-9a1d-8fc5ad9675ac
~~~

Khóa ngẫu nhiên có đủ entropy, chẳng hạn UUID phiên bản 4 từ bộ sinh số ngẫu nhiên an toàn, thường phù hợp. Không nên sinh khóa chỉ bằng timestamp giây hoặc số đếm trong một tiến trình vì có thể trùng giữa thiết bị và tiến trình.

Nếu client có thể mất khóa sau khi ứng dụng khởi động lại, nên lưu khóa cùng tác vụ đang chờ retry. Sau khi nhận kết quả chắc chắn cho tác vụ đó, có thể kết thúc vòng đời khóa và sinh khóa mới cho ý định tiếp theo.

## 3. Chọn phạm vi định danh để không chống lặp nhầm

Một chuỗi khóa giống nhau có thể đến từ hai khách hàng, hai tenant hoặc hai loại tác vụ. Vì vậy máy chủ nên định nghĩa **phạm vi khóa** rõ ràng:

~~~text
deduplicationKey = tenantId + operationType + idempotencyKey

Ví dụ:
TENANT#shop-12#OP#create-order#KEY#550e8400-e29b-41d4-a716-446655440000
~~~

Các thành phần:

- **tenantId:** do hệ thống lấy từ thông tin xác thực, không tin mù quáng giá trị client gửi.
- **operationType:** ví dụ CREATE_ORDER, CAPTURE_PAYMENT, REFUND_PAYMENT. Cùng khóa client nhưng hai loại thao tác là hai ý định khác nhau.
- **idempotencyKey:** khóa ổn định giữa các lần gửi lại của một ý định.

Tùy nghiệp vụ, có thể bổ sung tài khoản, kênh thanh toán, vùng hoặc namespace của API. Điều quan trọng là **không cho hai chủ thể khác nhau vô tình dùng chung bản ghi chống trùng** và **không cho người dùng truy cập kết quả của chủ thể khác chỉ bằng cách đoán khóa**.

### 3.1. Cùng key nhưng payload khác nhau

Một lỗi thường gặp:

~~~http
POST /orders
Idempotency-Key: K-123

{"items":[{"productId":"P101","quantity":1}]}
~~~

Sau đó client tái sử dụng khóa ấy:

~~~http
POST /orders
Idempotency-Key: K-123

{"items":[{"productId":"P101","quantity":10}]}
~~~

Nếu chỉ nhìn key rồi trả kết quả cũ, client có thể tưởng hệ thống đã đặt 10 sản phẩm. Nếu xử lý lại như yêu cầu mới, key mất ý nghĩa chống lặp.

Giải pháp là lưu thêm **dấu vân tay của nội dung yêu cầu** (*request fingerprint/payload hash*) và kiểm tra trước khi trả kết quả cũ:

~~~text
same scope + same key + same payload  -> cùng thao tác, trả kết quả đã ghi nhận
same scope + same key + payload khác -> từ chối xung đột
different key                       -> thao tác mới, xử lý theo quy tắc nghiệp vụ
~~~

Có thể dùng SHA-256 trên dạng payload đã chuẩn hóa, nhưng phải xác định rõ những trường nào tham gia:

1. Bao gồm các **đầu vào có ý nghĩa nghiệp vụ**: người nhận, các mặt hàng, số lượng, địa chỉ, đơn vị tiền tệ, phương thức giao hàng.
2. Chuẩn hóa thứ tự trường JSON, kiểu dữ liệu, Unicode, biểu diễn số và giá trị mặc định nếu hợp đồng API coi chúng tương đương.
3. Chỉ sắp xếp phần tử mảng khi **thứ tự không có nghĩa nghiệp vụ**. Đừng tự sắp xếp một danh sách mà thứ tự làm thay đổi tác động.
4. Xác định cách xử lý giá/tổng tiền do server tính, dữ liệu phụ phát sinh sau request hoặc các trường như timestamp/logging không làm thay đổi ý định.
5. Nếu payload chứa bí mật có thể bị đoán từ một không gian nhỏ, cân nhắc **HMAC với khóa bí mật** hoặc cơ chế lưu vân tay thích hợp thay vì lưu nội dung nhạy cảm trực tiếp.

Không nên chỉ hash toàn bộ chuỗi JSON thô nếu hợp đồng coi hai thứ tự field JSON khác nhau là cùng một yêu cầu.

## 4. Mô hình bản ghi chống trùng trong NoSQL

Một collection/table dành cho idempotency có thể chứa:

~~~json
{
  "pk": "TENANT#shop-12#OP#create-order#KEY#550e8400-e29b-41d4-a716-446655440000",
  "tenantId": "shop-12",
  "operation": "CREATE_ORDER",
  "payloadHash": "sha256:...",
  "status": "COMPLETED",
  "resourceType": "ORDER",
  "resourceId": "O900",
  "httpStatus": 201,
  "responseBody": {
    "orderId": "O900",
    "status": "CREATED"
  },
  "createdAt": "2026-11-14T02:30:00Z",
  "completedAt": "2026-11-14T02:30:01Z",
  "expiresAt": 1794710000
}
~~~

Đây là **cấu trúc minh họa**, không phải schema bắt buộc. Giá trị thời gian hết hạn trong ví dụ chỉ biểu thị trường Unix epoch giây; khi triển khai phải tính chính xác từ chính sách lưu giữ.

Các trường thường cần:

| Trường | Mục đích |
| --- | --- |
| **pk / composite key** | Xác định duy nhất ý định trong một phạm vi |
| **payloadHash** | Phát hiện reuse key với nội dung khác |
| **status** | Đánh dấu đang xử lý, hoàn tất, hoặc thất bại theo hợp đồng |
| **resourceId** | Liên kết đến đơn hàng/giao dịch đã tạo |
| **response snapshot** | Cho phép retry nhận lại kết quả của lần xử lý đầu |
| **createdAt / completedAt** | Kiểm tra vòng đời và điều tra sự cố |
| **expiresAt / TTL** | Tự dọn bản ghi khi kết thúc thời gian chống lặp |
| **leaseOwner / leaseUntil / version** | Chỉ cần khi công việc kéo dài và có worker cạnh tranh |

### 4.1. Dùng PK hoặc unique index, không dùng “SELECT rồi INSERT”

Phần cốt lõi phải là một **ràng buộc duy nhất được thực thi nguyên tử** tại nơi ghi dữ liệu.

Ví dụ sai:

~~~text
if FIND(idempotencyKey) == null:
    CREATE_ORDER()
    SAVE(idempotencyKey)
~~~

Hai request đồng thời có thể đều thấy chưa có key, rồi cùng tạo hai đơn.

Ví dụ ý tưởng đúng hơn:

~~~text
INSERT_IF_ABSENT(deduplicationKey, requestRecord)
~~~

Chỉ một request có thể giành quyền cho khóa. Các request còn lại cần đọc trạng thái đã tồn tại để quyết định trả kết quả cũ, báo đang xử lý hoặc xung đột payload.

Nhưng **chèn bản ghi khóa thành công chưa đủ** nếu bước tạo đơn tiếp theo có thể thất bại độc lập. Ta còn phải thiết kế cách kết nối dấu vết xử lý và tác động nghiệp vụ. Hai mẫu dưới đây giải quyết các trường hợp khác nhau.

## 5. Mẫu A — Ghi bản ghi chống trùng và đối tượng trong cùng giao dịch

Đây là trường hợp thuận lợi nhất khi **toàn bộ tác động nghiệp vụ thuộc một NoSQL store có hỗ trợ giao dịch thích hợp**. Giả sử lệnh CREATE_ORDER chỉ ghi một đơn vào bảng Orders và một bản ghi chống trùng vào IdempotencyRequests.

Ý tưởng:

~~~text
TRANSACTION:
    PUT IdempotencyRequests[deduplicationKey]
        IF NOT EXISTS
        value = {payloadHash, status=COMPLETED, orderId, response}

    PUT Orders[orderId]
        IF NOT EXISTS
        value = {customerId, lines, total, status=CREATED}

COMMIT ALL OR ROLLBACK ALL
~~~

Đây là **mã giả**. Cần hệ quản trị hỗ trợ ghi nguyên tử cả hai mục dữ liệu và điều kiện “chưa tồn tại”. Nếu transaction thành công, dấu vết chống trùng và đơn hàng xuất hiện cùng nhau. Nếu giao dịch thất bại, cả hai không được tạo.

### 5.1. Luồng khi API nhận yêu cầu

~~~mermaid
flowchart TD
    A["Nhận POST /orders và Idempotency-Key"] --> B["Xác thực tenant, kiểm tra dữ liệu, tính payloadHash"]
    B --> C["Thử giao dịch: ghi bản ghi key + tạo đơn"]
    C -->|Thành công| D["Trả kết quả đơn vừa tạo"]
    C -->|Xung đột điều kiện| E["Đọc nhất quán bản ghi key hiện có"]
    E --> F{"Có bản ghi cùng key?"}
    F -->|Không| G["Phân loại lỗi khác và retry an toàn khi thích hợp"]
    F -->|Có| H{"Hash có giống?"}
    H -->|Khác| I["Trả lỗi reuse key với payload khác"]
    H -->|Giống| J["Trả lại kết quả đã lưu"]
~~~

Điểm rất quan trọng: **lỗi giao dịch không phải lúc nào cũng là “key đã tồn tại”**. Giao dịch còn có thể thất bại do điều kiện khác, quota, xung đột hoặc sự cố tạm thời. Phải phân loại nguyên nhân và kiểm tra trạng thái thật, tránh trả bừa kết quả thành công.

### 5.2. Ví dụ pseudocode theo phong cách Java

Giả sử có một lớp NoSqlStore hỗ trợ giao dịch nhiều item, put-if-absent và đọc nhất quán:

~~~java
public CreateOrderResult createOrder(
        AuthContext auth, String idempotencyKey, CreateOrderInput input) {

    validateInput(input);
    String scope = auth.tenantId() + "#CREATE_ORDER#" + idempotencyKey;
    String payloadHash = canonicalBusinessHash(input);

    // Phần đọc trước này giúp trả kết quả nhanh cho retry phổ biến.
    // Nó KHÔNG thay thế điều kiện ghi nguyên tử bên dưới.
    RequestRecord old = store.getRequestStronglyConsistent(scope);
    if (old != null) {
        return replayOrReject(old, payloadHash);
    }

    String orderId = newOrderId();
    Order order = buildOrder(orderId, auth, input);
    CreateOrderResult result = new CreateOrderResult(orderId, "CREATED");

    RequestRecord request = RequestRecord.completed(
            scope, payloadHash, orderId, 201, result, retentionDeadline());

    try {
        store.transaction(tx -> {
            tx.putIfAbsent("IdempotencyRequests", scope, request);
            tx.putIfAbsent("Orders", orderId, order);
        });
        return result;
    } catch (ConditionalConflictException collision) {
        RequestRecord winner = store.getRequestStronglyConsistent(scope);
        if (winner != null) {
            return replayOrReject(winner, payloadHash);
        }
        // Có thể là xung đột khác, ví dụ ID đơn hàng trùng.
        throw collision;
    }
}

private CreateOrderResult replayOrReject(
        RequestRecord record, String expectedHash) {
    if (!record.payloadHash().equals(expectedHash)) {
        throw new IdempotencyConflictException(
                "Key đã được dùng cho nội dung yêu cầu khác");
    }
    return record.storedResult();
}
~~~

Đây là **pseudocode phục vụ tư duy thiết kế**, không phải mã Java biên dịch trực tiếp: NoSqlStore, các kiểu dữ liệu, xử lý ngoại lệ và giao dịch cần ánh xạ sang SDK thực tế. Phần kiểm tra quyền truy cập đối tượng và hợp đồng phản hồi cũng phải được thực hiện trong hệ thống thật.

Một điểm tinh tế: lần đầu có thể sinh orderId = O900, còn request khác đồng thời sinh O901. Nếu hai request dùng **cùng idempotency key**, chỉ một giao dịch được ghi thành công; đơn còn lại không được tạo. Request thua đọc lại bản ghi của request thắng và lấy **orderId thực sự đã được ghi**.

### 5.3. Điều kiện áp dụng

Mẫu A phù hợp khi:

- Các ghi nghiệp vụ cần bảo vệ đều nằm **trong phạm vi transaction** mà sản phẩm hỗ trợ.
- Có ràng buộc unique/conditional write cho deduplication key.
- Có cách xử lý read-after-write và lỗi giao dịch phù hợp.
- Dữ liệu phản hồi đủ nhỏ hoặc có thể lưu một tham chiếu ổn định đến kết quả.

Nó **chưa** tự bảo vệ thao tác gửi email, gọi API vận chuyển, trừ tiền bên thứ ba hoặc gửi message nếu các tác động này xảy ra **ngoài transaction**.

## 6. Mẫu B — Ghi trạng thái PROCESSING cho nghiệp vụ kéo dài

Không phải nghiệp vụ nào cũng hoàn thành trong một giao dịch ngắn. Ví dụ xác nhận đơn phải kiểm tra tồn kho, xử lý thanh toán và gọi dịch vụ giao hàng. Khi đó có thể dùng một **state machine** cho request.

~~~mermaid
stateDiagram-v2
    [*] --> PROCESSING: Claim key thành công
    PROCESSING --> COMPLETED: Tác động đã xác nhận
    PROCESSING --> FAILED_FINAL: Lỗi nghiệp vụ kết thúc
    PROCESSING --> RETRYABLE: Lỗi tạm thời, có quy tắc retry
    RETRYABLE --> PROCESSING: Retry/worker nhận quyền
    COMPLETED --> [*]
    FAILED_FINAL --> [*]
~~~

Các trạng thái cần được **định nghĩa theo nghiệp vụ**; một số hệ thống dùng tên RESERVED, IN_PROGRESS, SUCCEEDED, FAILED hoặc trạng thái chi tiết hơn.

Ví dụ bản ghi khi đang xử lý:

~~~json
{
  "pk": "TENANT#shop-12#OP#capture-payment#KEY#K-009",
  "payloadHash": "sha256:...",
  "status": "PROCESSING",
  "owner": "worker-3",
  "leaseUntil": "2026-11-14T02:30:30Z",
  "version": 4,
  "paymentId": "PAY-700",
  "attempts": 1
}
~~~

Một luồng xử lý khái niệm:

1. **Claim** bằng ghi có điều kiện: chỉ người đầu tiên tạo được bản ghi hoặc được phép nhận lại lease mới có quyền tiếp tục.
2. **Phân biệt retry đồng thời:** request thứ hai cùng key đọc trạng thái PROCESSING; có thể trả HTTP 202 kèm Retry-After, chờ kết quả theo thời gian giới hạn, hoặc trả 409 theo hợp đồng API.
3. **Thực hiện tác vụ:** worker cập nhật progress/checkpoint có kiểm soát, gọi dịch vụ phụ trợ bằng định danh ổn định.
4. **Hoàn tất có điều kiện:** chỉ owner/version hợp lệ mới chuyển PROCESSING → COMPLETED và lưu kết quả.
5. **Khôi phục:** khi worker chết, lease hết hạn cho phép worker khác tiếp tục từ trạng thái nghiệp vụ đã xác nhận.

### 6.1. Lease không tự ngăn tác động trùng

Giả sử worker A giữ lease 30 giây, xử lý chậm và bị mất kết nối. Lease hết hạn, worker B nhận lại. Sau đó A sống lại và cả hai đều muốn cập nhật kết quả.

Để ngăn worker cũ ghi dữ liệu sai, có thể dùng **fencing token/version tăng dần**:

~~~text
worker A nhận token = 4
worker B nhận lại sau khi lease hết hạn, token = 5
ghi từ worker A với token 4 phải bị từ chối
ghi từ worker B với token 5 mới được chấp nhận
~~~

Phía nhận ghi phải **thực sự kiểm tra token**. Nếu dịch vụ thanh toán bên ngoài không hỗ trợ fencing hay idempotency, chỉ tăng version trong database không thể đảm bảo worker A không gọi thanh toán trùng.

Không được coi lease hết hạn là bằng chứng tác vụ cũ chưa hoàn tất. Phục hồi phải dựa trên **trạng thái đã được xác nhận của nghiệp vụ**, đối chiếu với dịch vụ bên ngoài nếu cần.

### 6.2. Khi nào coi một lỗi là kết thúc?

- **Lỗi validation trước khi có tác động:** có thể từ chối ngay, không nhất thiết tạo record chống lặp; hợp đồng API cần nhất quán.
- **Lỗi nghiệp vụ chắc chắn, chẳng hạn không đủ số dư:** có thể lưu FAILED_FINAL để retry cùng key nhận kết quả tương ứng, nếu đó là chính sách đã công bố.
- **Timeout không biết thanh toán thành công hay chưa:** đây là trạng thái **chưa xác định**, không nên đánh dấu thất bại cuối cùng rồi thanh toán lại vô điều kiện.
- **Lỗi hạ tầng tạm thời:** có thể retry an toàn khi đã kiểm tra/thiết kế tính idempotent của từng bước.
- **Lỗi sau khi tạo đơn nhưng trước khi lưu kết quả:** phải đọc lại đơn theo ID/khóa nghiệp vụ ổn định thay vì tạo đơn khác.

Trạng thái FAILED_FINAL và thời gian giữ dấu vết tùy sản phẩm; không có một quy tắc cache tất cả HTTP 4xx/5xx áp dụng chung.

## 7. Vì sao NoSQL phải quan tâm đến atomicity?

NoSQL không phải một kiểu cơ sở dữ liệu duy nhất. Mỗi sản phẩm có mức hỗ trợ ghi có điều kiện, transaction và consistency khác nhau. Muốn tránh race condition, phải xác định **điểm nào quyết định một request là người thắng** và **điểm nào xác nhận tác động nghiệp vụ**.

### 7.1. Key–value: khóa xác nhận duy nhất

Ví dụ với một hệ key–value có primitive put-if-absent:

~~~text
PUT_IF_ABSENT("idem:shop-12:create-order:K-009", record)
~~~

Một hệ như Redis có thể dùng thao tác nguyên tử dạng:

~~~text
SET idem:shop-12:create-order:K-009 processing NX EX 86400
~~~

Lệnh trên chỉ tạo key nếu chưa tồn tại và đặt thời gian hết hạn. **Nó mới là bước claim**, chưa tự bảo đảm tác động đặt hàng đã hoàn tất, cũng chưa xử lý kết quả của retry, phục hồi sau crash hoặc sự cố mất dữ liệu. Nếu key có thể bị eviction/mất do chính sách lưu trữ, cần kiểm tra mức độ bền vững trước khi dùng làm nguồn chống trùng cho thanh toán.

### 7.2. Document: unique index hoặc ID của bản ghi request

Với document database, thường tạo collection idempotency có trường khóa duy nhất:

~~~javascript
// Ví dụ cú pháp MongoDB
db.idempotencyRequests.createIndex(
  { tenantId: 1, operation: 1, key: 1 },
  { unique: true }
);
~~~

Khi hai request cùng chèn một khóa, unique index chặn việc tạo hai bản ghi. Nếu tạo đơn và lưu bản ghi idempotency trong **cùng transaction** mà hệ quản trị hỗ trợ, có thể áp dụng mẫu A. Nếu không, cần khôi phục giữa các bước hoặc sử dụng khóa đơn hàng có tính duy nhất làm bảo vệ bổ sung.

Một câu lệnh dạng find-then-insert không an toàn khi concurrent. Cần unique constraint hoặc phép cập nhật có điều kiện nguyên tử, và xử lý đúng lỗi duplicate key.

### 7.3. Wide-column: conditional insert/LWT theo phạm vi hỗ trợ

Với hệ kiểu Cassandra, có thể dùng lightweight transaction (LWT) để tạo bản ghi key một lần:

~~~sql
-- Minh họa CQL; schema cần định nghĩa partition key phù hợp
INSERT INTO idempotency_by_key (
  tenant_operation_key, payload_hash, status
) VALUES (
  'shop-12#create-order#K-009', 'sha256:...', 'PROCESSING'
) IF NOT EXISTS;
~~~

Kết quả điều kiện cho biết lệnh có thực sự được áp dụng hay không. Tuy nhiên, **LWT của một bản ghi không tự mang lại transaction tổng quát gồm nhiều bảng và dịch vụ**. Cần thiết kế lưu trạng thái, khôi phục và tính nhất quán của dữ liệu nghiệp vụ tương ứng.

### 7.4. DynamoDB: conditional write và transaction có điều kiện

DynamoDB hỗ trợ conditional put như:

~~~text
PutItem:
  TableName: IdempotencyRequests
  Item: { pk: "shop-12#create-order#K-009", ... }
  ConditionExpression: "attribute_not_exists(pk)"
~~~

Nếu nghiệp vụ nằm trong phạm vi hỗ trợ của DynamoDB transactions, có thể dùng **TransactWriteItems** để ghi record chống trùng và order trong cùng giao dịch. Cần quan sát kết quả condition failure và đọc bản ghi đã tạo với mức nhất quán phù hợp. Nên kiểm tra các giới hạn hiện hành của giao dịch, TTL, partition và kích thước item trong tài liệu phiên bản đang dùng.

### 7.5. Graph: unique constraint kết hợp transaction

Trong graph database, có thể dùng node Request có khóa duy nhất, ví dụ:

~~~text
(:Request {scopeKey, payloadHash, status})
    -[:CREATED]->(:Order {id})
~~~

Unique constraint trên scopeKey giúp không có hai node request cùng định danh; transaction quyết định việc tạo Request và Order có thể được commit cùng nhau hay không. Với thao tác duyệt rồi ghi, còn phải kiểm tra locking, ràng buộc và phiên bản để tránh hai luồng xử lý gây tác động phụ ngoài graph.

**Điểm chung của bốn cách:** tên mô hình NoSQL không quyết định khả năng chống trùng. Cần một **điều kiện ghi nguyên tử được hệ quản trị thực thi** cùng với cách giữ kết quả/tác động nghiệp vụ đủ bền vững.

## 8. Ví dụ API tạo đơn idempotent

Giả sử API:

~~~http
POST /v1/orders
Authorization: Bearer <token>
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{
  "customerId": "U42",
  "lines": [
    {"productId": "P101", "quantity": 2},
    {"productId": "P205", "quantity": 1}
  ],
  "deliveryAddressId": "ADDR7"
}
~~~

Máy chủ xác thực người gọi, xác định tenant, kiểm tra tồn tại/giá sản phẩm và tính số tiền theo chính sách nghiệp vụ. Những dữ liệu dùng để tạo đơn phải được xử lý nhất quán với cơ chế bảo vệ tạo đơn.

### 8.1. Lần đầu thành công

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/O900
Content-Type: application/json

{
  "orderId": "O900",
  "status": "CREATED",
  "totalVnd": 1000000
}
~~~

Đơn O900 được lưu, đồng thời bản ghi chống trùng lưu key, payloadHash và kết quả liên quan đến O900.

### 8.2. Retry cùng key, cùng payload

~~~http
POST /v1/orders
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

{ ... cùng nội dung nghiệp vụ ... }
~~~

API tìm bản ghi đã hoàn tất và **trả về O900**. Nó không tạo O901. Một hợp đồng API có thể trả y nguyên status/body HTTP đã lưu ở lần đầu; hợp đồng khác có thể trả cùng resource ID cùng metadata cho biết đây là replay. Dù chọn cách nào, cần công bố và thực hiện nhất quán.

Nếu đơn O900 đã chuyển sang PAID sau khi tạo, API retry của **CREATE_ORDER** nên trả kết quả ổn định theo hợp đồng đã định nghĩa; nó không được hiểu yêu cầu cũ là lệnh tạo đơn mới. Một API **GET /orders/O900** riêng có thể trả trạng thái hiện tại.

### 8.3. Retry cùng key nhưng payload khác

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "IDEMPOTENCY_KEY_REUSED",
  "message": "Khóa yêu cầu đã được sử dụng với nội dung khác."
}
~~~

Mã 409 chỉ là một lựa chọn hợp lý; một số API dùng 422 hoặc mã khác theo hợp đồng. Điều quan trọng là client hiểu **không được âm thầm xử lý payload mới bằng khóa cũ**.

### 8.4. Retry trong khi request đầu đang chạy

Với mẫu B, máy chủ có thể trả:

~~~http
HTTP/1.1 202 Accepted
Retry-After: 2
Content-Type: application/json

{
  "code": "REQUEST_IN_PROGRESS",
  "requestId": "550e8400-e29b-41d4-a716-446655440000"
}
~~~

Client có thể truy vấn trạng thái hoặc retry sau khoảng chỉ dẫn. Một số API chọn 409 để biểu thị thao tác cùng key đang xử lý; đây là quyết định giao thức. Không được trả **thành công giả** khi tác động chưa được xác nhận.

## 9. Chống xử lý lặp với message queue và worker

Request HTTP không phải điểm duy nhất cần idempotency. Ví dụ dịch vụ Orders phát sự kiện:

~~~json
{
  "eventId": "evt-7082",
  "eventType": "OrderPaid",
  "orderId": "O900",
  "paymentId": "PAY-700",
  "occurredAt": "2026-11-14T02:31:00Z"
}
~~~

Consumer Inventory nhận event và giảm tồn kho. Nếu consumer giảm tồn kho thành công nhưng mất kết nối trước khi ACK, broker có thể giao lại chính event đó. Giảm tồn kho lần hai là sai nghiệp vụ.

### 9.1. Inbox / processed-message

Consumer có thể ghi một bản ghi xử lý với khóa duy nhất **consumerName + eventId**:

~~~text
TRANSACTION:
    INSERT processed_messages["inventory#evt-7082"] IF ABSENT
    UPDATE inventory FOR ORDER O900
COMMIT
~~~

Với điều kiện **cả việc ghi dedup và thay đổi tồn kho thuộc cùng transaction**, event được nhận lại sẽ không trừ tồn kho thêm. Nếu hai tác động nằm ở hai hệ thống khác nhau, vẫn cần cơ chế đồng bộ, key nghiệp vụ bền vững hoặc xử lý sự cố giữa các bước.

Định danh event phải ổn định khi broker giao lại; nếu publisher tạo event mới với một eventId khác cho **cùng tác động nghiệp vụ**, consumer còn có thể cần khóa duy nhất theo **orderId + loại chuyển trạng thái**, ví dụ:

~~~text
inventory-deduction#O900
~~~

Điều này ngăn cùng nghiệp vụ bị áp dụng hai lần dù xuất hiện ở nhiều thông điệp khác nhau.

### 9.2. Transactional outbox

Một lỗi kinh điển khi tạo đơn:

~~~text
Bước 1: lưu Order O900 thành công
Bước 2: gửi OrderCreated sang broker
       -> service chết trước khi gửi, sự kiện bị mất
~~~

Chiều ngược lại cũng nguy hiểm: gửi event trước rồi lưu order thất bại khiến consumer xử lý sự kiện cho đối tượng chưa được xác nhận.

Với **transactional outbox**, ghi đơn và outbox event trong cùng transaction của database:

~~~text
TRANSACTION:
    INSERT Orders[O900]
    INSERT IdempotencyRequests[requestKey] IF ABSENT
    INSERT Outbox[eventId=evt-order-O900-created]
COMMIT

Worker outbox:
    đọc event chưa phát
    gửi tới broker
    đánh dấu đã phát hoặc lưu tiến độ
~~~

Worker outbox có thể gửi một event **nhiều lần** khi mất ACK, nên phía nhận vẫn cần xử lý idempotent. Outbox giúp tránh lỗ hổng “đã commit dữ liệu nhưng quên phát sự kiện”, chứ **không tự biến broker và consumer thành hệ exactly-once**.

## 10. Khi tác động nằm ở cổng thanh toán hoặc dịch vụ bên ngoài

Xét tiến trình:

~~~text
1. Claim request K-009 trong NoSQL
2. Gọi payment provider để charge 100.000 VND
3. Provider charge thành công
4. API bị crash trước khi cập nhật request K-009 = COMPLETED
5. Worker khác thử lại K-009
~~~

Nếu worker thực hiện bước 2 lần nữa bằng một request hoàn toàn mới, khách có nguy cơ bị thu tiền hai lần. **Bản ghi idempotency nội bộ không bao trùm tác động ngoài NoSQL**.

Cách thiết kế an toàn hơn phụ thuộc khả năng của nhà cung cấp:

1. Tạo **payment operation ID ổn định**, ví dụ payment intent của đơn, với ràng buộc duy nhất trong hệ nội bộ.
2. Gửi **cùng idempotency key** tới payment provider nếu provider hỗ trợ đúng nghiệp vụ và đúng thời hạn.
3. Khi timeout, **truy vấn trạng thái thanh toán bằng payment operation ID/provider reference** trước khi quyết định thử lại.
4. Cập nhật trạng thái nội bộ theo kết quả được xác nhận và kiểm tra chuyển trạng thái hợp lệ.
5. Có cơ chế đối soát/reconciliation cho trường hợp provider đã thành công nhưng thông tin không đồng bộ về hệ thống.

Nếu provider **không cung cấp tra cứu đáng tin cậy, idempotency hay định danh giao dịch ổn định**, không thể đảm bảo không charge trùng chỉ nhờ một khóa trong database nội bộ. Cần lựa chọn quy trình và giới hạn retry theo rủi ro nghiệp vụ thực tế.

### 10.1. Idempotency không đồng nghĩa kiểm tra nghiệp vụ duy nhất

Giả sử khách gửi hai request **khác idempotency key** nhưng đều để thanh toán **cùng một payment intent**. Mỗi key riêng lẻ là hợp lệ, nhưng nghiệp vụ không muốn capture cùng khoản tiền hai lần.

Cần thêm ràng buộc như:

~~~text
UNIQUE(paymentIntentId, captureType)
~~~

hoặc state machine chỉ cho phép một chuyển trạng thái có tác dụng từ AUTHORIZED → CAPTURED, tùy yêu cầu. **Request ID chống lặp cùng ý định đã định danh**, còn **business unique key** bảo vệ quy tắc “một đơn chỉ được thanh toán/capture theo cách được phép”.

## 11. Thời gian giữ key, TTL và khả năng tái sử dụng

Không thể lưu vô hạn mọi request trong mọi hệ thống, nhưng dọn quá sớm sẽ làm mất khả năng nhận ra retry cũ.

Giả sử key hết hạn sau 10 phút. Client offline 30 phút rồi gửi lại:

~~~text
02:30  Đã tạo đơn O900 với key K-009
02:40  Bản ghi idempotency hết thời hạn logic
03:00  Client reconnect, gửi lại key K-009
03:00  Nếu không còn dấu vết -> nguy cơ tạo O901
~~~

Thời gian giữ dấu vết cần bao phủ **cửa sổ retry thực tế**, gồm thời gian client offline, broker redelivery, retry job, timeout và chính sách nhà cung cấp. Với tác động tài chính, thường cần một **định danh nghiệp vụ bền vững** hoặc lịch sử giao dịch không phụ thuộc hoàn toàn vào TTL của cache request.

| Quyết định | Điều phải trả lời |
| --- | --- |
| **TTL bao lâu?** | Retry có thể đến muộn tối đa bao lâu? Có batch/replay sau vài ngày không? |
| **Khi TTL hết, key được dùng lại?** | Hợp đồng API có cho phép tạo tác động mới bằng key cũ không? |
| **Dọn dữ liệu thế nào?** | TTL được xử lý ngay hay dọn trễ? Bản ghi hết hạn có còn hiển thị không? |
| **Kết quả giữ bao nhiêu?** | Lưu snapshot HTTP, resourceId hay chỉ trạng thái? Có chứa dữ liệu nhạy cảm không? |
| **Tác động nghiệp vụ sống bao lâu?** | Order/payment còn tồn tại sau khi bản ghi request đã bị xóa? |

Một số CSDL thực hiện xóa TTL **không tức thời**. Vì vậy không nên dựa vào thời điểm vật lý của thao tác xóa để định nghĩa chính xác quyền tái sử dụng key; dịch vụ cần có quy tắc xử lý expired record rõ ràng.

Nếu đơn hàng là dữ liệu dài hạn, có thể lưu **unique business identifier** hoặc trường originalRequestKey gắn với order (theo chính sách bảo mật và lưu giữ) để hỗ trợ truy vết dài hạn. Với nghiệp vụ quan trọng, đừng trông chờ vào key cache ngắn hạn như lớp bảo vệ duy nhất.

## 12. Kiểm soát đồng thời và nhất quán khi retry

### 12.1. Race condition của hai request giống nhau

~~~mermaid
sequenceDiagram
    participant R1 as Request 1
    participant DB as NoSQL
    participant R2 as Request 2
    R1->>DB: PUT_IF_ABSENT(K)
    R2->>DB: PUT_IF_ABSENT(K)
    DB-->>R1: Được ghi (winner)
    DB-->>R2: Conditional conflict
    R1->>DB: Commit nghiệp vụ theo mẫu đã chọn
    R2->>DB: Đọc trạng thái/kết quả của K
    DB-->>R2: COMPLETED hoặc PROCESSING
~~~

Chỉ một request được **quyền claim**, nhưng hệ thống còn cần quy tắc khôi phục nếu request thắng crash. Tránh dùng kiểu lock vĩnh viễn khiến request mãi nằm PROCESSING mà không có người chịu trách nhiệm.

### 12.2. Nhất quán của lần đọc sau khi xung đột

Một số NoSQL mặc định cho phép đọc eventually consistent. Ngay sau khi request khác tạo record chống trùng, một replica chậm có thể vẫn trả “không tồn tại”.

Do đó, sau conditional failure cần **đọc với mức nhất quán đáp ứng hợp đồng** hoặc dùng kết quả ghi nguyên tử làm căn cứ. Nếu một lần đọc chưa thấy record, không được kết luận chắc chắn rằng key chưa được dùng và tự tạo tác động mới.

### 12.3. Không dùng idempotency key thay cho kiểm soát phiên bản

Hai thao tác có key khác nhau có thể cùng sửa một đối tượng:

~~~text
Request A: đổi địa chỉ đơn O900 sang A, key KA
Request B: đổi địa chỉ đơn O900 sang B, key KB
~~~

Cả KA và KB đều độc nhất, nên **chống trùng không giải quyết lost update**. Cần optimistic concurrency bằng version/ETag, conditional update hoặc transaction tùy tính đúng đắn của nghiệp vụ:

~~~text
UPDATE Order O900
SET address = B, version = 8
WHERE version = 7
~~~

Idempotency key và version có hai nhiệm vụ khác nhau: **chống lặp cùng yêu cầu** và **kiểm soát nhiều yêu cầu khác nhau tranh chấp dữ liệu**.

## 13. Các tình huống lỗi và cách xử lý

| Tình huống | Hệ thống có thể đang ở đâu? | Cách xử lý mong muốn |
| --- | --- | --- |
| Client gửi lại sau khi đã nhận 201 | Đã COMPLETED | Cùng key + cùng payload → trả kết quả cũ |
| Client timeout sau khi DB commit | Đã COMPLETED nhưng client không biết | Đọc lại record/key và trả resourceId cũ |
| Hai request đến đồng thời | Chỉ một request thắng conditional write | Request còn lại đọc trạng thái, không thực hiện tác động thứ hai |
| Client dùng cùng key cho payload khác | Record đã gắn với fingerprint cũ | Từ chối và ghi log xung đột có kiểm soát |
| Worker chết khi PROCESSING | Trạng thái còn dở | Khôi phục theo lease/version và đối chiếu tác động đã hoàn tất |
| DB lỗi trước khi giao dịch commit | Có thể chưa ghi gì | Phân loại lỗi, kiểm tra trạng thái trước khi retry |
| Ghi order thành công nhưng ghi request record lỗi | Thiết kế hai bước không nguyên tử | Khôi phục theo business ID; cân nhắc transaction/outbox |
| Payment provider charge rồi timeout | Trạng thái bên ngoài chưa rõ | Tra cứu bằng ID ổn định, không charge lại mù quáng |
| Queue giao lại một event | Consumer có thể đã áp dụng sự kiện | Dedup event/business ID cùng transaction với tác động |
| Key TTL hết trước khi retry muộn | Dấu vết chống trùng mất | Chính sách retention phù hợp và unique business ID dài hạn |
| Bản sao đọc chậm không thấy key mới | Dữ liệu chưa đồng bộ ở replica | Strong/consistent read theo khả năng, không suy diễn “chưa tồn tại” |

Điểm khó nhất thường là trạng thái **“không biết tác động đã xảy ra hay chưa”**, không phải lỗi chắc chắn. Khi chưa biết, giải pháp đúng là **quan sát trạng thái và tiếp tục an toàn**, chứ không tự ý làm lại tác động.

## 14. Thiết kế API và quản trị key

Một hợp đồng API có idempotency rõ ràng nên định nghĩa:

1. **Endpoint nào bắt buộc key:** thường là tạo đơn, thanh toán, hoàn tiền, đặt lịch, gửi lệnh có tác động không thể đơn giản đảo ngược.
2. **Ai sinh key:** client hay server; khi nào sinh mới; thời điểm giữ key để retry.
3. **Phạm vi khóa:** tenant, tài khoản, endpoint/operation, môi trường.
4. **Nội dung nào phải giống nhau:** nguyên tắc canonicalization và fingerprint.
5. **Thời hạn hiệu lực:** bao lâu hệ thống đảm bảo nhận ra retry.
6. **Cách phản hồi:** thành công lần đầu, replay, đang xử lý, payload xung đột và lỗi chưa xác định.
7. **Tác động nhiều hệ thống:** cơ chế đối soát và nguồn sự thật cuối cùng.

### 14.1. Những lưu ý về bảo mật

- Không cho client tự quyết định tenant/owner trong deduplication scope nếu thông tin đó phải lấy từ danh tính đã xác thực.
- Không dùng key có thể đoán dễ dàng làm bằng chứng quyền truy cập: yêu cầu xác thực và kiểm tra quyền với resource vẫn bắt buộc.
- Giới hạn độ dài/định dạng key và request size để tránh bị dùng làm nguồn tiêu thụ dung lượng vô hạn.
- Tránh lưu dữ liệu thanh toán, mã bí mật hoặc toàn bộ payload nhạy cảm trong bản ghi chống trùng nếu không cần thiết.
- Đặt quyền đọc/ghi, mã hóa, retention và masking log cho record phù hợp với dữ liệu nghiệp vụ.
- Hạn chế người dùng cố tình gây nhiều key khác nhau bằng rate limit/quota và kiểm soát abuse; idempotency không ngăn một client chủ động gửi vô hạn ý định mới.

### 14.2. Quan sát và vận hành

Các metric có ích:

| Metric | Điều được phản ánh |
| --- | --- |
| request_first_seen_total | Số thao tác có key mới được nhận |
| idempotency_replay_total | Số retry được nhận diện và trả kết quả cũ |
| idempotency_conflict_total | Số key được dùng lại với payload khác |
| idempotency_in_progress_total | Số lần yêu cầu trùng đến khi thao tác chưa xong |
| processing_age_p95/p99 | Các tác vụ PROCESSING bị kéo dài hoặc mắc kẹt |
| conditional_write_conflict_total | Mức độ cạnh tranh khi claim khóa |
| reconciliation_pending_total | Số giao dịch chưa xác minh được trạng thái bên ngoài |
| dedup_store_size / TTL lag | Chi phí lưu dấu vết và tốc độ dọn |

Log nên có tenant/operation, hash hoặc mã tham chiếu key, business ID và trace ID để liên kết sự kiện, nhưng không nên phát tán nguyên payload nhạy cảm. Một dashboard có tỷ lệ replay tăng đột biến có thể chỉ ra lỗi client retry, gateway timeout hoặc bottleneck tại một service.

## 15. Thử nghiệm các tình huống chống trùng

Trước khi triển khai một API có tác động tài chính hoặc điều chỉnh tồn kho, cần thử ít nhất các kịch bản sau:

| Kịch bản | Tác động mong đợi |
| --- | --- |
| Gửi cùng key/payload 10 lần liên tiếp | Chỉ một order/business effect; tất cả lần gọi hợp lệ tham chiếu cùng kết quả |
| Gửi cùng key/payload trong 100 request đồng thời | Chỉ một request giành quyền tạo; không có dữ liệu nghiệp vụ trùng |
| Gửi cùng key nhưng payload khác | Bị từ chối, dữ liệu ban đầu không đổi |
| Cắt mạng sau khi DB commit nhưng trước HTTP response | Retry nhận lại kết quả của lần đầu |
| Crash sau khi claim PROCESSING | Có thể khôi phục, không treo vô hạn, không thực hiện trùng |
| Crash sau khi provider báo charge thành công nhưng trước khi ghi DB | Retry/đối soát không charge thêm lần hai |
| Broker phát lại cùng event | Inventory/payment projection không áp dụng trùng |
| Hai thao tác khác key cập nhật cùng order | Cơ chế version/transaction xử lý đúng xung đột |
| Retry sau TTL | Hành vi đúng với retention đã công bố, không vô ý tạo tác động trùng gây thiệt hại |

**Chỉ đếm số dòng idempotency là chưa đủ**. Cần kiểm tra thực tế số order, lần giữ tồn kho, bản ghi thanh toán, thông điệp gửi ra và trạng thái sau khi phục hồi. Việc này đặc biệt quan trọng với tác động ngoài transaction.

## 16. Bài tập thiết kế: đặt vé có giới hạn ghế

Một hệ thống bán vé có API:

~~~http
POST /tickets/purchase
Idempotency-Key: 7b9e8ce6-411e-4386-b4c8-d840fc91f4ad

{"showId":"S100","seatId":"A12","customerId":"U42"}
~~~

Yêu cầu:

- Retry cùng key không tạo thêm vé hoặc charge tiền lần hai.
- Hai khách hàng có **key khác nhau** cùng mua ghế A12 thì tối đa một người giữ được ghế.
- Cổng thanh toán có thể trả timeout sau khi đã trừ tiền.
- Kết quả vé/đơn được giữ lâu hơn TTL của bản ghi chống trùng.

Hãy thiết kế ít nhất ba loại định danh:

1. **Idempotency key:** nhận diện việc U42 gửi lại cùng ý định mua.
2. **Business uniqueness key:** ràng buộc ghế A12 của suất S100 chỉ được phân cho một vé hiệu lực theo chính sách bán vé.
3. **Payment operation ID:** dùng lại khi gọi provider và đối soát.

Với NoSQL có hỗ trợ conditional write/transaction, hãy mô tả điểm nguyên tử để cấp ghế, nơi lưu trạng thái thanh toán và luồng khôi phục sau timeout. Nếu hệ thống không thể transaction qua database và provider, hãy nêu cách dùng state machine, provider idempotency key và đối soát để tránh thực hiện lặp.

Điểm mấu chốt của bài tập là: **chỉ có một request key không đủ để đảm bảo một ghế không bị bán cho hai khách**; phải có cả ràng buộc nghiệp vụ độc lập với định danh request.

## Kết luận

**Định danh yêu cầu** cho phép nhận ra “đây là cùng một ý định được gửi lại”, từ đó tránh tạo thêm đơn, trừ tồn kho hoặc thu tiền chỉ vì retry. Để cơ chế thật sự hoạt động trong NoSQL, phải kết hợp:

- **Key có phạm vi rõ ràng**, ổn định qua retry, và **payload fingerprint** để phát hiện reuse sai.
- **Conditional write/unique constraint nguyên tử** để ngăn nhiều request đồng thời cùng thắng.
- **Kết quả hoặc trạng thái bền vững** để trả lại kết quả cũ và khôi phục sau crash.
- **Transaction hoặc quy trình phục hồi** để gắn dấu vết chống trùng với tác động nghiệp vụ.
- **Business unique key, outbox/inbox, idempotency bên ngoài và đối soát** cho các tác động vượt ranh giới một cơ sở dữ liệu.
- **TTL và cơ chế vận hành** phù hợp với cửa sổ retry và mức độ quan trọng của nghiệp vụ.

Một hệ thống được thiết kế đúng không suy luận rằng “request lỗi thì tác động chưa xảy ra”. Nó dùng **định danh và trạng thái có thể kiểm chứng** để trả lời điều gì đã xảy ra, rồi quyết định retry hoặc tiếp tục xử lý một cách an toàn.
