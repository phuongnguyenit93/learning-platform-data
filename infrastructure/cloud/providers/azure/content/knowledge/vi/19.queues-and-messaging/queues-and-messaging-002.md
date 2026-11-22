# Gửi, nhận và quản lý visibility timeout với Queue Storage

Một API nhận yêu cầu tạo hóa đơn có thể cần gọi dịch vụ PDF, lưu tệp lên Azure Blob Storage, gửi email và cập nhật trạng thái. Nếu bắt client chờ tất cả bước này trong một HTTP request, phản hồi dễ bị chậm, timeout hoặc thất bại khi một dịch vụ phụ thuộc tạm thời quá tải. Một cách thiết kế tốt hơn là để API ghi thông điệp vào **Azure Queue Storage**, trả về mã theo dõi công việc, rồi một hoặc nhiều **worker** xử lý bất đồng bộ.

Nhưng đưa tác vụ vào hàng đợi mới là nửa đầu vấn đề. Nếu worker lấy thông điệp rồi bị crash, tác vụ có biến mất không? Nếu worker làm lâu hơn **visibility timeout**, một worker khác có thể nhận lại cùng thông điệp không? Khi một tác vụ thành công, tại sao phải gọi `Delete Message` bằng đúng **pop receipt**? Và nếu thao tác ghi dữ liệu thành công nhưng xóa thông điệp thất bại, làm sao tránh tạo hai hóa đơn?

Bài học này trả lời những câu hỏi đó bằng cơ chế **send → receive → xử lý → delete**, kết hợp **visibility timeout**, `dequeue_count`, retry, idempotency và poison-message handling. Bài thuộc chương **Hàng đợi và thông điệp**, module **CLOUD_PROVIDERS_AZURE**: hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure.

Sau bài học, bạn sẽ:

- Giải thích Queue Storage, message, producer, consumer/worker, TTL, visibility timeout, dequeue count và pop receipt.
- Phân biệt `Peek Message`, `Get/Receive Messages`, `Update Message` và `Delete Message`.
- Mô tả chính xác điều gì xảy ra khi worker crash, chạy quá thời gian ẩn hoặc xử lý trùng.
- Viết ví dụ Python SDK dùng Microsoft Entra ID để gửi/nhận/gia hạn thời gian ẩn/xóa thông điệp.
- Thiết kế retry, idempotency, poison queue, khả năng mở rộng worker và giám sát.
- Bảo vệ hàng đợi bằng RBAC, managed identity, Private Endpoint khi cần và hạn chế dữ liệu nhạy cảm.
- Xác định khi nào nên dùng Storage Queue, Azure Service Bus hoặc Event Grid thay vì dùng nhầm chức năng của từng dịch vụ.

## 1. Azure Queue Storage dùng để làm gì?

**Azure Queue Storage** là dịch vụ hàng đợi thông điệp thuộc Azure Storage. Producer đặt những thông điệp nhỏ vào queue; consumer lấy các thông điệp để xử lý bất đồng bộ. Queue tách nhịp gửi yêu cầu của producer khỏi tốc độ xử lý của worker, giúp ứng dụng hấp thụ tải tăng đột biến và có thể thử lại khi tác vụ thất bại.

~~~mermaid
flowchart LR
    USER[Người dùng] --> API[API tạo hóa đơn]
    API -->|Send message| Q[(Azure Queue Storage)]
    API -->|202 Accepted + job ID| USER
    Q -->|Receive, temporarily invisible| W1[Worker 1]
    Q -->|Receive, temporarily invisible| W2[Worker 2]
    W1 --> DB[(Azure SQL)]
    W2 --> DB
    W1 --> BLOB[(Azure Blob Storage)]
    W2 --> BLOB
    W1 -. Success: delete message .-> Q
    W2 -. Error/crash: message visible again .-> Q
~~~

Ví dụ producer ghi một thông điệp mô tả việc cần làm, **không** chứa toàn bộ tệp PDF:

~~~json
{
  "eventId": "invoice-request-98421",
  "type": "GenerateInvoice",
  "invoiceId": "INV-98421",
  "blobName": "source/invoices/INV-98421.json",
  "schemaVersion": 1,
  "correlationId": "req-fd42b"
}
~~~

Worker đọc thông điệp, lấy dữ liệu nguồn từ Blob Storage/SQL, dựng PDF, lưu kết quả rồi **xác nhận hoàn thành bằng cách xóa thông điệp**. Dữ liệu lớn và nhạy cảm nên để trong hệ lưu trữ phù hợp; message chỉ chứa định danh hoặc tham chiếu đủ an toàn.

### Khi nào dùng hàng đợi?

| Tình huống | Queue giúp ích | Cần thiết kế thêm |
|---|---|---|
| Sinh báo cáo/PDF ở nền | API trả lời nhanh, worker xử lý sau | Trạng thái job, retry, idempotency |
| Xử lý file sau upload | Tách upload khỏi resize/scan/index | Bảo vệ Blob access, thứ tự sự kiện |
| Gửi email/thông báo | Hấp thụ đợt traffic lớn | Chống gửi trùng, rate limit, trạng thái gửi |
| Batch cập nhật dữ liệu | Worker scale độc lập | Transaction, checkpoint, poison handling |
| Tích hợp hệ thống chậm | Buffer và retry khi downstream lỗi | Backoff, circuit breaker, timeout |

**Không dùng Queue Storage như database hay log giao dịch duy nhất.** Queue lưu các thông điệp cần xử lý, không cung cấp query tùy ý, thứ tự toàn cục có bảo đảm hay giao dịch ACID trải qua cả database và queue.

## 2. Cấu trúc dịch vụ và các giới hạn quan trọng

Một tài khoản lưu trữ **StorageV2** có thể chứa queues trong dịch vụ Queue Storage:

~~~text
Azure subscription
  Resource group
    Storage account: mystorageaccount
      Queue endpoint: https://mystorageaccount.queue.core.windows.net
      Queue: invoice-jobs
        Message A
        Message B
      Queue: invoice-jobs-poison
        Failed Message X
~~~

**Queue** và **Blob container** là các tài nguyên khác nhau. Queue endpoint có dạng `https://<account>.queue.core.windows.net`, khác `https://<account>.blob.core.windows.net`. Khi cấu hình private DNS hoặc RBAC, cần dùng đúng dịch vụ.

### Các đặc tính cần ghi nhớ

| Thuộc tính | Ý nghĩa | Hệ quả |
|---|---|---|
| **Message size** | Mỗi thông điệp Queue Storage hỗ trợ tối đa **64 KiB** trong phiên bản dịch vụ hiện đại | Không nhúng file lớn; cân nhắc Base64 làm tăng kích thước |
| **TTL (time-to-live)** | Thời gian message được phép tồn tại từ khi gửi | Hết TTL, message có thể bị xóa ngay cả khi chưa xử lý |
| **Initial visibility delay** | Có thể trì hoãn thời điểm message mới gửi xuất hiện để worker nhận | Không đồng nghĩa TTL hoặc thời gian xử lý |
| **Receive visibility timeout** | Tạm thời ẩn message sau khi worker nhận | Hết thời gian ẩn mà chưa delete, message có thể được nhận lại |
| **Pop receipt** | Token gắn với lần nhận/cập nhật cần dùng cho thao tác update/delete | Receipt cũ không bảo đảm còn hợp lệ |
| **Dequeue count** | Số lần message được lấy để xử lý theo thông tin dịch vụ | Hữu ích cho retry/poison policy |
| **Approximate message count** | Số message ước lượng của queue theo khả năng dịch vụ | Không phải số liệu chính xác hoặc độ trễ queue |

Storage Queue **không bảo đảm FIFO tuyệt đối**. Một message đang invisible có thể bị message được gửi sau vượt qua; nhiều workers, retries và thời gian xử lý khác nhau cũng làm thứ tự hoàn thành thay đổi. Nếu nghiệp vụ cần strict ordering/session semantics, cần thiết kế dịch vụ hoặc phân vùng khác phù hợp.

### TTL và giới hạn theo phiên bản

Thông thường message có **TTL mặc định 7 ngày** nếu không chỉ định. Với API version hiện đại, có thể đặt TTL lớn hơn 7 ngày hoặc giá trị `-1` để không tự hết hạn theo cơ chế hỗ trợ; các giới hạn phụ thuộc API/SDK và cấu hình dịch vụ, không nên giả định mọi client cũ hỗ trợ như nhau. **Visibility timeout không làm TTL được gia hạn**: khi message hết hạn, việc kéo dài thời gian ẩn không giữ nó lại.

Đối với công việc tồn đọng cần giữ lâu dài, đặc biệt có yêu cầu pháp lý, không nên dựa vào TTL vô hạn như hệ thống lưu trữ hồ sơ. Lưu bản ghi nghiệp vụ và trạng thái vào database/Blob Storage, dùng queue để báo có việc cần làm.

### Nội dung và encoding

Thông điệp gửi qua REST Queue Storage nằm trong payload XML của dịch vụ, nên ký tự và encoding phải phù hợp. SDK Python hiện đại có thể **không tự Base64-encode mọi message theo mặc định**. Khi cần gửi JSON có Unicode/định dạng đặc biệt, có thể cấu hình `TextBase64EncodePolicy` và `TextBase64DecodePolicy` ở cả producer/consumer. **Tất cả bên gửi/nhận cùng queue phải thống nhất chính sách encoding.**

Base64 thường làm nội dung tăng khoảng **một phần ba**. Vì giới hạn 64 KiB áp dụng cho nội dung sau encoding theo cách dịch vụ nhận, dung lượng JSON gốc an toàn có thể nhỏ hơn nhiều so với 64 KiB. Với message vượt ngưỡng, hãy lưu payload vào Blob Storage và chỉ truyền một định danh/tên blob; kiểm tra kích thước thực tế trước khi gửi.

## 3. Vòng đời một message: gửi, nhận, xử lý, xóa

Một message được gửi vào queue sẽ có **message ID**, thời điểm được chèn, thời điểm hết hạn và thời điểm có thể nhìn thấy. Khi worker gọi **receive**, dịch vụ trả nội dung cùng metadata và **pop receipt**; đồng thời tạm ẩn message để các worker khác thường không nhận được nó trong một khoảng thời gian.

~~~mermaid
stateDiagram-v2
    [*] --> Visible: Send (khi hết initial delay)
    Visible --> Invisible: Receive / Get Messages
    Invisible --> Deleted: Delete với pop receipt hợp lệ
    Invisible --> Visible: Visibility timeout hết
    Invisible --> Invisible: Update visibility + receipt mới
    Visible --> Expired: TTL hết
    Invisible --> Expired: TTL hết
    Deleted --> [*]
    Expired --> [*]
~~~

Các trạng thái trên mô tả cơ chế logic. Trong vận hành thực, worker có thể bị ngắt mạng, request timeout hoặc retry; vì vậy **thông điệp có thể được giao lại** và không nên xây giả định exactly-once.

### Luồng xử lý chuẩn

1. **Producer** tạo event/job ID duy nhất, xác thực, rồi gửi message vào queue.
2. **Worker** gọi receive với visibility timeout phù hợp, nhận message ID và pop receipt.
3. **Worker** kiểm tra schema, xác thực dữ liệu cần thiết, xử lý nghiệp vụ và lưu kết quả vào nơi bền vững.
4. Nếu xử lý lâu, worker **update message visibility** trước khi thời gian ẩn hết và giữ receipt mới.
5. **Chỉ sau khi kết quả đã được ghi bền vững**, worker gọi delete bằng message ID và pop receipt hiện tại.
6. Nếu worker lỗi trước delete, message xuất hiện lại sau visibility timeout hoặc thời điểm được update; worker khác có thể xử lý lại.
7. Nếu thông điệp lỗi liên tục, chính sách ứng dụng chuyển nó sang khu vực điều tra/poison queue thay vì retry vô hạn.

### “Nhận” không có nghĩa “xóa”

Trong Queue Storage, `Receive Messages` (REST thường gọi `Get Messages`) là thao tác **tạm ẩn**, không tự xóa. Nếu worker gọi receive xong rồi thoát mà chưa delete, message vẫn nằm trong queue đến khi visibility timeout hết hoặc TTL hết. Đây là cơ chế hỗ trợ retry khi worker crash, nhưng cũng là lý do bắt buộc phải lập trình **idempotent processing**.

## 4. Các thao tác Queue Storage và khác biệt dễ nhầm

| Thao tác | API/SDK điển hình | Có thay đổi visibility? | Có xóa message? | Khi dùng |
|---|---|---|---|---|
| **Send** | `send_message` / Put Message | Có thể đặt initial visibility delay | Không | Producer đặt công việc |
| **Peek** | `peek_messages` / Peek Messages | **Không** | Không | Quan sát một số message visible, chẩn đoán |
| **Receive** | `receive_messages` / Get Messages | **Có**, tạm ẩn và trả pop receipt | Không | Worker lấy công việc |
| **Update** | `update_message` / Update Message | **Có**, đổi thời điểm nhìn thấy; có thể thay content theo API | Không | Gia hạn ẩn/đổi visibility khi xử lý |
| **Delete** | `delete_message` / Delete Message | Không áp dụng sau khi xóa | **Có** | Acknowledge khi đã xử lý thành công |
| **Clear** | `clear_messages` / Clear Messages | Không | **Xóa các message trong queue** | Chỉ dùng khi chủ động hủy toàn bộ backlog |

**Peek không khóa message.** Hai hệ thống cùng peek có thể thấy nội dung tương tự mà không có quyền sở hữu hay pop receipt để xử lý/delete. Đừng viết worker dựa trên peek rồi giả định có thể xác nhận thành công như receive.

**Delete không giống “complete” ở Azure Service Bus.** Azure Queue Storage yêu cầu truyền **message ID + pop receipt hợp lệ**. Khái niệm pop receipt tương tự một token bảo vệ cập nhật, nhưng không phải lease vĩnh viễn. Receipt có thể thay đổi sau receive/update; dùng receipt cũ có thể khiến delete thất bại.

**Clear queue** là thao tác phá hủy backlog quy mô rộng, không phải xóa một message poison. Không chạy clear trong production chỉ vì worker đang báo lỗi; trước hết cần cách ly/khôi phục thông điệp lỗi theo cơ chế có kiểm soát.

## 5. Visibility timeout: tính theo dòng thời gian

Visibility timeout là khoảng thời gian một message **tạm không sẵn sàng cho các lần receive mới**, được tính từ thao tác receive/update tương ứng. Nó giúp worker có cơ hội xử lý mà không để những worker khác đồng thời lấy message trong khoảng đó. Nhưng đó **không phải khóa độc quyền bảo đảm cho toàn bộ giao dịch**.

Giả sử một message có TTL 1 giờ và worker A nhận lúc 10:00:00 với visibility timeout **60 giây**:

~~~text
10:00:00   A receive message M → invisible đến khoảng 10:01:00
10:00:05   A bắt đầu xử lý, gọi database
10:00:40   A đang chờ dịch vụ xuất hóa đơn
10:01:00   Visibility timeout hết; M có thể được worker B receive
10:01:05   B nhận M, có pop receipt mới
10:01:10   A hoàn thành công việc cũ và gọi delete với receipt cũ
10:01:10   Delete của A có thể bị từ chối vì receipt đã lỗi thời
10:01:20   B có thể đang thực hiện lại cùng công việc
~~~

**Kết luận:** worker A có thể tiếp tục chạy **sau khi mất quyền nhận độc quyền trên message**. Nếu A gửi email hoặc ghi hóa đơn vào database, B cũng có thể làm tương tự. Do đó, visibility timeout **giảm khả năng xử lý song song ngoài ý muốn nhưng không loại bỏ duplicate processing**.

### 5.1. Default visibility timeout

Với thao tác receive thông thường, visibility timeout mặc định của Azure Queue Storage là **30 giây** nếu không yêu cầu giá trị khác trong API/SDK tương ứng. Với job chỉ mất vài giây, mặc định có thể đủ. Với job kéo dài 2–5 phút, nên đặt khoảng ẩn ban đầu phù hợp hoặc gia hạn trong quá trình xử lý.

### 5.2. Không chọn timeout quá ngắn hoặc quá dài

| Visibility timeout | Lợi ích | Rủi ro |
|---|---|---|
| **Quá ngắn** so với thời gian xử lý | Worker crash được retry sớm | Message có thể hiện lại khi job còn chạy, tăng xử lý trùng |
| **Phù hợp** thời gian xử lý thường gặp | Giảm duplicate do timeout | Vẫn cần xử lý crash, retry, long-tail latency |
| **Quá dài** | Giảm tình huống job chậm hơn timeout | Worker chết thì message bị trì hoãn retry lâu |
| **Có heartbeat/gia hạn** | Cân bằng timeout ban đầu ngắn và job dài | Cần logic quản lý receipt, gia hạn lỗi, shutdown và monitoring |

Giả sử thời gian xử lý p99 khoảng 90 giây, đặt cố định 30 giây rất dễ tạo overlap. Nhưng đặt 2 giờ cho mọi job lại làm chậm khôi phục khi worker crash. Một phương án là nhận với 90–120 giây, đo thực tế rồi gia hạn có giới hạn khi còn làm việc. Không chọn con số chỉ bằng cảm giác.

### 5.3. Initial visibility delay khác receive visibility

**Initial visibility delay** khi gửi là việc **hoãn lần đầu message có thể nhận**. Ví dụ producer gửi job lúc 10:00 với delay 120 giây; worker bình thường chưa receive được đến khoảng 10:02. Sau khi worker nhận, một **receive visibility timeout mới** quyết định khoảng ẩn trong lúc xử lý.

TTL tiếp tục trôi qua trong cả thời gian delay và invisible. Nếu đặt initial delay quá dài so với TTL, message có thể hết hạn trước khi có cơ hội xử lý. Queue Storage không phải scheduler nghiệp vụ phức tạp: với lịch xa, recurrence hoặc workflow nhiều bước, cân nhắc Azure Functions timer, Logic Apps hoặc hệ thống điều phối thích hợp.

### 5.4. Giới hạn thời gian ẩn

Các giá trị lớn nhất/nhỏ nhất phụ thuộc phiên bản REST, SDK và thao tác. Với phiên bản Queue Storage hiện đại, visibility timeout của receive/update có thể cấu hình tới mức tính bằng **ngày** (thường tối đa 7 ngày), nhưng **không được vượt thời gian sống còn lại** và phải tuân thủ hợp đồng API. Không dùng timeout cực dài như giải pháp thay thế cho quản trị tiến độ job.

Các phép tính ở bài này là **dòng thời gian minh họa**, không phải SLA bảo đảm request được phân phối đúng tại millisecond. Khi timeout hết, message **có thể** được nhận lại; không bảo đảm một worker lập tức nhận ở thời điểm đó.

## 6. Pop receipt: vì sao phải lưu và cập nhật đúng token?

Khi một consumer nhận message, dịch vụ trả về **message ID** và **pop receipt**. Message ID chỉ ra đối tượng cần thao tác; pop receipt chứng minh consumer có phiên bản token phù hợp với lần receive/update gần đây.

### 6.1. Thứ tự nhận → gia hạn → xóa

~~~mermaid
sequenceDiagram
    participant W as Worker A
    participant Q as Azure Queue Storage
    W->>Q: Receive M (visibility 60s)
    Q-->>W: M.id + popReceipt R1
    Note over W: Xử lý chưa xong, còn quyền cập nhật
    W->>Q: Update M + R1, visibility 90s
    Q-->>W: popReceipt R2 + nextVisibleOn
    Note over W: Hoàn tất ghi kết quả nghiệp vụ
    W->>Q: Delete M + R2
    Q-->>W: Success
~~~

**Lỗi thường gặp:** gọi update thành công nhưng vẫn dùng `R1` để xóa. Sau update, dịch vụ phát sinh **pop receipt mới `R2`**; thao tác delete với `R1` có thể bị từ chối. Client phải lưu **receipt mới nhất** cho các bước tiếp theo.

### 6.2. Receipt không phải quyền sở hữu vĩnh viễn

Nếu visibility timeout hết và worker B receive lại message, B có pop receipt mới. A không còn được mặc định quyền update/delete message đó. Nếu A vẫn còn đang xử lý nghiệp vụ, hành động ghi kết quả có thể diễn ra song song với B. Pop receipt chỉ giúp kiểm soát các **thao tác message trong Queue Storage**, không tự khóa SQL row, file Blob hoặc API bên ngoài.

**Thiết kế an toàn:** kết hợp một *business operation ID* với ràng buộc duy nhất/trạng thái bền vững ở data store. Khi hai worker đồng thời xử lý cùng job, chỉ một kết quả nghiệp vụ được chấp nhận hoặc những lần gọi lại tạo ra kết quả tương đương.

### 6.3. Gia hạn visibility timeout

Worker đang xử lý lâu có thể gọi `Update Message` trước hạn để đặt khoảng ẩn mới. Giá trị visibility timeout của request update thường tính **từ thời điểm update được dịch vụ chấp nhận**, không cộng dồn nguyên xi vào mốc cũ.

Ví dụ:

~~~text
10:00:00 Receive với 60 giây       → visible khoảng 10:01:00
10:00:45 Update với 120 giây      → visible khoảng 10:02:45
10:02:00 Update với 120 giây      → visible khoảng 10:04:00
10:02:30 Xử lý thành công         → Delete bằng receipt của lần update 10:02
~~~

Không cần gia hạn sau khi delete. Nếu update thất bại vì receipt không hợp lệ, message đã hết hạn hoặc queue không truy cập được, worker phải coi mình **không còn chắc có quyền thao tác với message**. Đừng tiếp tục ghi side effect không idempotent rồi xóa bừa bằng receipt cũ.

### 6.4. Có thể dùng Update Message để đổi nội dung?

API update có thể thay nội dung message cùng với thời gian ẩn theo các điều kiện được hỗ trợ. Tuy vậy, với luồng xử lý quan trọng, đừng mặc định mọi progress update cần sửa nội dung message. Giữ **job ID** trong queue và cập nhật **job status** ở database thường rõ ràng hơn, có thể truy vấn và audit tốt hơn. Nếu message content thay đổi, producer/consumer phải thống nhất schema/encoding; kích thước message sau update vẫn chịu giới hạn dịch vụ.

## 7. Delivery semantics: at-least-once, duplicate và thứ tự

Storage Queue phù hợp với mô hình xử lý **có thể giao lại**. Ứng dụng nên giả định một message có thể được nhận nhiều lần, kể cả trong những tình huống người gửi/nhận gặp network timeout. Đừng thiết kế nghiệp vụ chỉ chạy đúng nếu message được xử lý **exactly once**.

### Những tình huống tạo xử lý trùng

1. Worker xử lý xong nhưng **crash trước khi delete**.
2. Worker ghi database thành công, nhưng request delete timeout; không chắc dịch vụ đã nhận lệnh delete.
3. Visibility timeout hết khi worker vẫn đang làm; worker khác receive lại.
4. Producer gửi message, request trả timeout; producer không biết message đã được chấp nhận và **retry send**, tạo hai message khác ID nhưng cùng business event.
5. Một worker nhận lại message sau khi retry/backoff và làm lại side effect nếu không lưu dấu xử lý.

### At-least-once không có nghĩa cứ mất mạng là chắc chắn nhận lại

Nếu message **hết TTL**, bị xóa bởi quản trị viên, queue bị clear hoặc bị hủy, nó có thể không còn để retry. Do đó, nói chính xác hơn: kiến trúc phải **chịu được việc giao lại**, đồng thời quản trị TTL, xóa dữ liệu, monitoring và lưu trạng thái công việc để tránh thất lạc kết quả.

### FIFO và thứ tự hoàn thành

Message A gửi trước B nhưng A được nhận rồi ẩn 120 giây, trong khi B được xử lý ngay. B có thể hoàn thành trước A. Với nhiều worker, không dùng Queue Storage để yêu cầu:

- Mọi message phải được xử lý đúng thứ tự gửi.
- Chỉ một consumer duy nhất toàn hệ thống xử lý một nhóm business key.
- Các message cho cùng customer/order được khóa phiên.
- Transaction nguyên tử trên nhiều message và nhiều hệ dữ liệu.

Nếu thật sự cần **sessions, duplicate detection, dead-letter queue native hoặc transaction trong hệ messaging**, hãy cân nhắc **Azure Service Bus** theo SKU/tính năng hỗ trợ; Queue Storage đơn giản và phù hợp với khối lượng tác vụ bất đồng bộ không đòi các semantics đó.

## 8. Idempotency: chống tạo hai hóa đơn khi nhận lại

**Idempotent operation** là thao tác mà khi thực hiện nhiều lần với cùng một định danh nghiệp vụ, trạng thái cuối cùng vẫn tương đương như thực hiện một lần. Đối với message-driven systems, đây là yêu cầu nền tảng.

### 8.1. Phân biệt message ID và business event ID

| Định danh | Do ai cấp? | Dùng cho |
|---|---|---|
| **Queue message ID** | Azure Queue Storage khi send | Receive/update/delete đúng message trong queue |
| **Pop receipt** | Azure Queue Storage trên receive/update | Chứng thực phiên thao tác update/delete message |
| **Business event/job ID** | Producer hoặc hệ thống nghiệp vụ | Chống duplicate qua nhiều message, retry send, khôi phục |
| **Correlation ID** | Hệ thống quan sát phân tán | Ghép logs/traces qua API, queue, worker, database |

Nếu producer retry và tạo hai Queue messages với **hai message IDs khác nhau** nhưng cùng `eventId=invoice-request-98421`, chỉ dựa trên Queue message ID để dedup là **không đủ**. Cần idempotency key ổn định ở mức nghiệp vụ.

### 8.2. Database làm rào chắn xử lý trùng

Ví dụ thiết kế dữ liệu:

~~~sql
-- Pseudocode SQL: cú pháp transaction/upsert phụ thuộc database.
CREATE TABLE ProcessedJobs (
    EventId VARCHAR(128) PRIMARY KEY,
    State VARCHAR(32) NOT NULL,
    ResultLocation VARCHAR(1024),
    UpdatedAtUtc DATETIME2 NOT NULL
);
~~~

Luồng xử lý khuyến nghị:

1. Parse message, lấy `eventId` và xác minh schema.
2. Trong transaction dữ liệu thích hợp, kiểm tra/ghi nhận trạng thái theo `EventId` với **unique constraint** hoặc cơ chế claim có điều kiện.
3. Nếu job đã `Completed`, bỏ qua side effect và xem xét delete message hiện tại.
4. Nếu job được claim để xử lý, thực hiện tác vụ với **idempotency key** của downstream (khi hỗ trợ).
5. Lưu kết quả và trạng thái `Completed` bền vững, bảo đảm chỉ có một kết quả có hiệu lực.
6. Sau commit, delete Queue message bằng receipt hiện tại.

**Không áp dụng ngây thơ “đánh dấu Processed trước khi thực hiện side effect”.** Nếu worker chết giữa hai bước, job có thể bị bỏ qua dù chưa tạo kết quả. Dùng state machine (`Pending`, `Processing`, `Completed`, `Failed`), ownership/lease expiry phù hợp, transaction hoặc outbox khi cần, và đảm bảo có thể resume an toàn.

### 8.3. Một giao dịch không bao trùm SQL + Storage Queue

Ghi SQL thành công và xóa message là **hai thao tác trên hai dịch vụ**, không nằm trong một ACID transaction chung mặc định.

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant DB as Azure SQL
    participant Q as Queue Storage
    W->>Q: Receive M (receipt R)
    Q-->>W: eventId E
    W->>DB: Commit invoice result for E
    DB-->>W: Success
    Note over W: Worker crash/network failure
    Q-->>W: Message M may reappear
    Note over DB: Result for E already exists
~~~

Nếu worker khác xử lý lại E, database nên trả về kết quả đã có, **không** tạo hóa đơn mới. Với side effect bên ngoài (gửi SMS, thanh toán), cần idempotency key, outbox/inbox hoặc trạng thái xác nhận được với đối tác. **Visibility timeout không thay thế cơ chế chống xử lý trùng ở tầng dữ liệu.**

### 8.4. Retry của producer

Khi `send_message` timeout, producer không luôn biết liệu Azure đã nhận message hay chưa. Retry cùng business event có thể tạo bản sao mới. Vì vậy producer cần gắn event ID bền vững, ghi trạng thái publish theo kiến trúc, và worker phải dedup theo event ID, không dựa vào giả định mỗi HTTP send tạo đúng một công việc.

Đối với yêu cầu cần bảo đảm **database commit và message publication** nhất quán, có thể dùng **transactional outbox**: ghi thay đổi nghiệp vụ và outbox event cùng transaction trong database, sau đó publisher đọc outbox và gửi Queue message với event ID ổn định. Outbox cũng có thể gửi trùng khi crash sau send; worker vẫn cần idempotency.

## 9. Thực hành Python SDK: cấu hình danh tính và queue

Ví dụ tiếp theo dùng **`azure-storage-queue`** và **`azure-identity`** trên Python 3. Đoạn mã mang tính hướng dẫn, **không được chạy trong lúc biên soạn bài**. Người học cần một Azure Storage account thử nghiệm, quyền tạo queue và quyền message phù hợp, Azure CLI/credential đã đăng nhập.

### 9.1. Cài thư viện và chuẩn bị

~~~bash
python -m pip install azure-storage-queue azure-identity

# Đăng nhập trong môi trường lab khi dùng Azure CLI credential.
az login
~~~

Tại máy local, `DefaultAzureCredential` có thể sử dụng nguồn đăng nhập phát triển được hỗ trợ. Trên Azure App Service, Functions, AKS hoặc VM, ưu tiên **managed identity / Workload Identity** theo khả năng nền tảng thay vì key hardcoded. Danh tính được cấp role Azure Storage Queue data-plane thích hợp; tài khoản storage và network phải cho phép kết nối.

Ví dụ thiết lập environment variable:

~~~bash
export AZURE_STORAGE_ACCOUNT="<lab-storage-account-name>"
export AZURE_QUEUE_NAME="invoice-jobs"
~~~

Trong PowerShell có thể dùng `$env:AZURE_STORAGE_ACCOUNT="..."` và `$env:AZURE_QUEUE_NAME="invoice-jobs"`. Các giá trị trong dấu `<...>` là placeholder, không chạy nguyên xi.

### 9.2. Tạo QueueClient bằng Entra ID

~~~python
import os

from azure.identity import DefaultAzureCredential
from azure.storage.queue import (
    QueueClient,
    TextBase64EncodePolicy,
    TextBase64DecodePolicy,
)

account_name = os.environ["AZURE_STORAGE_ACCOUNT"]
queue_name = os.environ.get("AZURE_QUEUE_NAME", "invoice-jobs")

credential = DefaultAzureCredential()
queue = QueueClient(
    account_url=f"https://{account_name}.queue.core.windows.net",
    queue_name=queue_name,
    credential=credential,
    message_encode_policy=TextBase64EncodePolicy(),
    message_decode_policy=TextBase64DecodePolicy(),
)
~~~

**Quan trọng:** ví dụ dùng Base64 cho text message. Nếu producer dùng policy Base64 nhưng worker không dùng decode policy, worker có thể đọc ra chuỗi Base64 thay vì JSON. Nếu dùng decode policy trên queue chứa message raw không phải Base64, việc nhận có thể lỗi. Đồng bộ encoding trong contract của producer/consumer và có kế hoạch migrate schema trước khi đổi.

Ở production, tái sử dụng client/credential phù hợp vòng đời worker thay vì tạo mới trên từng message. Không ghi connection string chứa storage account key, SAS token hoặc bearer token vào source/log.

### 9.3. Tạo queue lab có kiểm soát

~~~python
from azure.core.exceptions import ResourceExistsError

try:
    queue.create_queue()
    print("Queue created:", queue_name)
except ResourceExistsError:
    print("Queue already exists:", queue_name)
~~~

Đoạn này yêu cầu quyền **tạo queue** (mức quyền quản lý đối tượng queue), có thể rộng hơn quyền của producer chỉ gửi message. Trong production nên dùng **IaC/nhóm nền tảng** tạo queue, rồi cấp cho ứng dụng role chỉ cần gửi hoặc xử lý. Worker không nhất thiết có quyền tạo/xóa queue.

Một queue đã tồn tại **không nên bị xóa/tạo lại chỉ để chạy được ví dụ** vì có thể chứa backlog của ứng dụng khác.

## 10. Gửi message: producer và initial visibility delay

Tiếp tục sử dụng biến `queue` đã được tạo ở phần 9.2.

### 10.1. Gửi một job JSON

~~~python
import json
import uuid

job = {
    "schemaVersion": 1,
    "eventId": f"invoice-request-{uuid.uuid4()}",
    "invoiceId": "INV-98421",
    "type": "GenerateInvoice",
    "sourceBlob": "source/invoices/INV-98421.json",
}

payload = json.dumps(job, ensure_ascii=False, separators=(",", ":"))
result = queue.send_message(
    payload,
    time_to_live=3600,      # TTL = 1 giờ
    visibility_timeout=0,   # Message có thể được nhận ngay
)
print("Sent message ID:", result.id)
~~~

`TextBase64EncodePolicy` của client sẽ mã hóa text trước khi gửi. `time_to_live=3600` được tính theo giây; `visibility_timeout=0` ở thao tác send là **initial visibility delay bằng 0**, không phải receive lock bằng 0.

**Lưu ý idempotency:** ví dụ tạo `uuid4` mỗi lần chạy để minh họa một công việc mới. Trong nghiệp vụ thật, nếu retry **cùng một yêu cầu** sau timeout, phải **giữ nguyên eventId đã cấp cho yêu cầu đó**. Nếu mỗi lần retry tạo UUID mới, worker không nhận diện được hai message thuộc một công việc logic.

### 10.2. Gửi job có trì hoãn

~~~python
delayed_job = {
    "schemaVersion": 1,
    "eventId": "invoice-reminder-98421",
    "invoiceId": "INV-98421",
    "type": "SendReminder",
}

queue.send_message(
    json.dumps(delayed_job),
    visibility_timeout=120,  # Hoãn lần đầu nhìn thấy khoảng 2 phút
    time_to_live=1800,       # Message tồn tại tối đa 30 phút
)
~~~

Tại thời điểm gửi, dịch vụ bắt đầu đếm TTL. Đừng để initial delay lớn hơn hoặc bằng TTL theo cách khiến message hết hạn trước khi có thể xử lý. Với lịch nghiệp vụ kéo dài nhiều tuần hoặc có recurrence, cần một workflow scheduler chuyên biệt thay vì chỉ đặt delay rất dài.

### 10.3. Một producer tốt cần ghi trạng thái

| Điểm kiểm soát | Vì sao quan trọng? |
|---|---|
| `eventId` ổn định trên retry | Chống duplicate message/side effect |
| `schemaVersion` | Consumer biết cách parse, tương thích khi rollout |
| `correlationId` | Theo dõi log xuyên API → queue → worker |
| `time_to_live` hợp lý | Không để job hết hạn trước khi xử lý |
| Payload nhỏ, không chứa secret | Phù hợp 64 KiB và giảm rủi ro dữ liệu |
| Lưu trạng thái job vào database khi cần | Cho user xem Pending/Completed/Failed |
| Retry send theo chính sách | Phân biệt transient error với auth/network/config |

Không trả response `200 Completed` cho client khi mới gửi job nếu nghiệp vụ cần biết công việc đã hoàn thành. Thường API trả **202 Accepted** và một job ID để client có thể tra cứu tiến độ hoặc nhận callback theo cơ chế ứng dụng.

## 11. Peek và Receive: quan sát khác với xử lý

### 11.1. Peek không làm ẩn message

~~~python
for m in queue.peek_messages(max_messages=3):
    print("Visible message:", m.id, m.content)
~~~

`peek_messages` đọc một số message có thể nhìn thấy mà không làm chúng invisible hay tăng dequeue count như một lần receive. Đây là công cụ kiểm tra nhanh; **không phải cơ chế quét toàn bộ backlog** hoặc đảm bảo bạn luôn thấy mọi message. Nó cũng không trao cho ứng dụng pop receipt để delete.

Đừng dùng peek để đo chính xác số lượng job đang xử lý: message invisible không giống message visible, nhiều worker có thể đang làm song song, và approximate count không phải transactionally consistent.

### 11.2. Receive với visibility timeout 60 giây

~~~python
received = queue.receive_messages(
    messages_per_page=1,
    visibility_timeout=60,
)
message = next(iter(received), None)

if message is None:
    print("No visible message currently")
else:
    print("ID:", message.id)
    print("Dequeue count:", message.dequeue_count)
    print("Next visible at:", message.next_visible_on)
    print("Content:", message.content)
    print("Pop receipt received:", bool(message.pop_receipt))
~~~

Lần receive làm message **tạm ẩn**. Vì ví dụ này chưa gọi delete, thông điệp sẽ **có thể được nhận lại** sau khi hết visibility timeout, trừ khi đã bị xóa/hết TTL hoặc có một worker khác xử lý. Khi thử lab, hãy ghi nhớ rằng chính hành động receive kiểm tra cũng tác động trạng thái message và dequeue count.

Khi đọc một trang message, dịch vụ Queue Storage có giới hạn số message trong một lần lấy; với API hiện đại thường tối đa **32 messages mỗi request**. SDK có thể phân trang/iterator; không nên giả định mỗi lần gọi SDK sẽ luôn trả đúng số lượng yêu cầu nếu queue không đủ message visible.

### 11.3. Acknowledge bằng Delete sau khi thành công

~~~python
import json

received = queue.receive_messages(
    messages_per_page=1,
    visibility_timeout=60,
)
message = next(iter(received), None)

if message is not None:
    job = json.loads(message.content)

    # LAB: giả lập xử lý thành công bằng cách in kết quả.
    # PRODUCTION: thay bằng xử lý idempotent có transaction/commit.
    print("Would process:", job["eventId"], job["type"])

    queue.delete_message(
        message.id,
        message.pop_receipt,
    )
    print("Deleted message:", message.id)
~~~

**Cảnh báo:** ví dụ trên gọi delete sau khi `print` nhằm minh họa API, **không phải worker nghiệp vụ an toàn**. Trong production, cần xử lý thật, lưu kết quả bền vững, đảm bảo idempotency, rồi mới delete. Nếu lỗi xảy ra, **đừng delete chỉ để queue trông sạch**.

### 11.4. Khi receive nhưng chưa xử lý xong

Nếu worker không thể xử lý trong thời gian được cấp, có ba lựa chọn:

1. **Gia hạn invisibility** bằng Update Message trong khi job còn tiến triển.
2. **Để timeout** để retry khi lỗi transient hoặc worker crash; cần backoff/poison policy.
3. **Chuyển sang poison queue** khi message không thể xử lý sau số lần thử hợp lý, rồi xóa bản gốc theo thứ tự an toàn.

Lựa chọn thứ ba không nên xảy ra chỉ dựa trên một lần lỗi mạng. Cần phân biệt lỗi vĩnh viễn (schema sai, tham chiếu thiếu không thể sửa) với lỗi tạm thời (database unavailable, API rate limited).

## 12. Update visibility trong một job dài

Giả sử một báo cáo mất 4 phút để tạo, nhưng worker receive message với timeout ban đầu 90 giây. Nếu không gia hạn, message có thể hiện lại trước khi job kết thúc. Giải pháp là dùng `update_message` trước khi hết hạn và **giữ lại pop receipt mới**.

### 12.1. Ví dụ cập nhật bằng Python SDK

~~~python
received = queue.receive_messages(
    messages_per_page=1,
    visibility_timeout=90,
)
message = next(iter(received), None)

if message is not None:
    current_receipt = message.pop_receipt

    # Giả sử ứng dụng đã xử lý một giai đoạn và cần thêm thời gian.
    update_result = queue.update_message(
        message.id,
        current_receipt,
        visibility_timeout=120,
    )
    current_receipt = update_result.pop_receipt
    print("Extended visibility until:", update_result.next_visible_on)

    # Chỉ khi xử lý đã được commit thành công và receipt còn hợp lệ:
    # queue.delete_message(message.id, current_receipt)
~~~

Ở đây, `update_message` **không xóa message**. Đoạn lab cố ý để lệnh delete ở dạng comment vì chưa có xử lý nghiệp vụ. Message sẽ có thể hiện lại sau khoảng thời gian mới nếu không được xóa.

### 12.2. Heartbeat cho công việc kéo dài

Một worker production cần đồng thời theo dõi tiến độ xử lý và thời gian invisibility. Mô hình khái niệm:

~~~text
Receive message with visibility_timeout = 90 s
    receipt = message.pop_receipt
    deadline = next_visible_on

While job is not completed:
    process one bounded, recoverable chunk
    if approaching deadline:
        response = UpdateMessage(message_id, receipt, 90 s)
        receipt = response.new_pop_receipt
        deadline = response.next_visible_on
    if lease/receipt update fails:
        stop unsafe side effects; checkpoint and investigate

If business result committed:
    DeleteMessage(message_id, latest_receipt)
Else:
    keep retryable state and let message reappear
~~~

Đây là **pseudocode**, không phải script chạy nguyên xi. Với job có call kéo dài/blocked lâu hơn timeout, cần heartbeat tách khỏi phần xử lý chặn hoặc chia công việc thành các bước ngắn/checkpoint. Heartbeat cũng có thể lỗi vì process crash, timeout mạng hoặc receipt đã hết hiệu lực.

### 12.3. Nên gia hạn vào lúc nào?

Ví dụ visibility 90 giây, công việc chia thành các bước 30 giây. Worker có thể gia hạn khi còn khoảng **30–45 giây** trước `nextVisibleOn` để dự phòng network latency, retry và scheduling. Cần đồng bộ đồng hồ/đọc timestamp trả về, tránh dựa vào logic “sleep đúng 89 giây rồi mới cập nhật”.

Không gia hạn mãi một job không có tiến triển. Thiết lập **maximum processing duration**, số lần heartbeat tối đa, deadline nghiệp vụ và chuyển sang trạng thái lỗi/điều tra khi đã vượt ngưỡng.

### 12.4. Delete có thể thất bại dù job đã thành công

Trong đường đi thực tế:

~~~text
T1: Worker hoàn tất ghi PDF vào Blob Storage
T2: Worker commit trạng thái Completed vào SQL
T3: Worker gọi Delete Message
T4: Request delete timeout / receipt không hợp lệ
T5: Message có thể được nhận lại
~~~

Worker khác phải nhận ra `eventId` đã Completed và **không dựng/thanh toán lại**. Sau đó nó có thể xóa message hiện tại với receipt hợp lệ sau khi xác minh trạng thái. Đây là ví dụ rõ nhất vì sao **delete là bước xác nhận giao message**, còn **idempotency là trách nhiệm của hệ thống nghiệp vụ**.

## 13. Dequeue count, retry policy và poison messages

Khi worker nhận một message, metadata `dequeue_count` cho biết số lần message đã được lấy để xử lý theo cơ chế dịch vụ. Nếu một message liên tục thất bại rồi xuất hiện lại, số lần nhận có thể tăng. Ứng dụng sử dụng thông tin này cùng **loại lỗi** và thời gian tồn tại của job để quyết định thử lại hay cách ly.

### 13.1. Lỗi tạm thời và lỗi khó phục hồi

| Loại lỗi | Ví dụ | Chính sách gợi ý |
|---|---|---|
| **Transient** | SQL timeout, HTTP 503 từ dịch vụ bên ngoài | Retry có backoff/jitter và giới hạn |
| **Rate limit** | API đối tác trả 429 kèm `Retry-After` | Tôn trọng yêu cầu backoff và quota |
| **Dependency outage** | Storage/Key Vault tạm không kết nối | Circuit breaker, giảm worker concurrency, alert |
| **Schema invalid** | Thiếu `eventId` hoặc `schemaVersion` không hỗ trợ | Không retry vô hạn; chuyển poison sau khi xác minh |
| **Reference invalid** | Blob không tồn tại do sai ID cố định | Kiểm tra race/eventual dependency; nếu chắc không phục hồi, cách ly |
| **Business rejection** | Hóa đơn đã hủy, không được tạo lại | Ghi trạng thái kết thúc hợp lệ; có thể delete thay vì retry |
| **Credential/RBAC error** | Worker liên tục trả 403 | Sửa identity/quyền, không gọi retry tốc độ cao |

**Không đồng nhất mọi exception thành “retry”.** Một lỗi parse JSON ở lần thứ 100 vẫn không thể được sửa bằng cách nhận lại cùng nội dung nếu schema không thay đổi.

### 13.2. Poison message là gì?

**Poison message** là message không thể được xử lý thành công theo chính sách sau nhiều lần thử hoặc do lỗi nội dung/nghiệp vụ. Ví dụ `eventId=invoice-request-98421` tham chiếu tệp sai định dạng và luôn làm worker crash.

Một ứng dụng dùng Queue Storage trực tiếp thường tự tạo queue cách ly, ví dụ `invoice-jobs-poison`:

~~~mermaid
flowchart TD
    MAIN[(invoice-jobs)] --> WORKER[Worker nhận message]
    WORKER --> CHECK{Nội dung và trạng thái?}
    CHECK -->|Hợp lệ| PROCESS[Xử lý idempotent]
    PROCESS -->|Thành công| DELETE[Delete original message]
    PROCESS -->|Lỗi tạm thời| RETRY[Backoff / visibility timeout]
    RETRY --> MAIN
    CHECK -->|Lỗi vĩnh viễn hoặc vượt ngưỡng| POISON[(invoice-jobs-poison)]
    POISON --> ACK[Chỉ delete bản gốc sau khi ghi poison thành công]
    ACK --> REVIEW[Alert + điều tra + xử lý lại có phê duyệt]
~~~

Azure Queue Storage **không cung cấp dead-letter queue native** như Azure Service Bus. Queue tên `-poison` ở đây là một queue thường, được ứng dụng hoặc framework tạo và quản lý. **Azure Functions Queue Storage trigger** có hành vi poison queue riêng theo cấu hình trigger, thường dùng queue tên `<original-queue>-poison` sau ngưỡng `maxDequeueCount`; không suy rộng rằng dịch vụ Storage Queue tự chuyển message khi bạn gọi SDK trực tiếp.

### 13.3. Mẫu chuyển vào poison queue

Khi quyết định cách ly một message, thứ tự quan trọng:

1. Nhận diện message bằng `eventId`; lưu message ID, dequeue count, error category và timestamp.
2. Gửi một bản ghi **đủ thông tin để điều tra nhưng không lộ secret** vào poison queue hoặc hệ dữ liệu trạng thái.
3. Xác minh thao tác ghi bản poison đã thành công.
4. **Chỉ sau đó** xóa bản gốc bằng pop receipt hiện hành.
5. Phát cảnh báo có owner và runbook khắc phục.

Nếu gửi poison thành công nhưng delete bản gốc thất bại, hai bản có thể tồn tại. Vì thao tác chuyển queue **không phải transaction nguyên tử**, hệ thống poison processing cũng cần idempotency theo `eventId`.

Ví dụ Python **đơn giản hóa** (phải có `queue` và `poison_queue` đã được cấu hình cùng encoding policy):

~~~python
import json
from datetime import datetime, timezone

def move_to_poison(main_queue, poison_queue, message, reason):
    payload = {
        "originalMessageId": message.id,
        "eventId": None,
        "dequeueCount": message.dequeue_count,
        "reason": reason,
        "failedAtUtc": datetime.now(timezone.utc).isoformat(),
        "content": message.content,
    }
    try:
        parsed = json.loads(message.content)
        payload["eventId"] = parsed.get("eventId")
    except (ValueError, TypeError):
        pass

    # Bảo vệ payload khỏi dữ liệu nhạy cảm và giới hạn 64 KiB
    # trước khi dùng trong production.
    poison_queue.send_message(json.dumps(payload))
    main_queue.delete_message(message.id, message.pop_receipt)
~~~

**Đây không phải thuật toán chuyển queue “exactly once”.** Nếu payload lớn hoặc chứa thông tin cá nhân/secret, cần ghi bản gốc an toàn trong Blob Storage có RBAC thích hợp rồi gửi vào poison queue **một tham chiếu**. Cần thêm retry/exception handling, idempotency và giới hạn retention cho bản poison.

### 13.4. Không retry mãi với dequeue count

Một chính sách ví dụ:

~~~text
Max attempts: 5 (quy tắc ứng dụng)
Attempt 1: xử lý bình thường
Attempt 2: delay khoảng 30 giây nếu transient
Attempt 3: delay khoảng 60 giây
Attempt 4: delay khoảng 120 giây
Attempt 5: nếu vẫn thất bại, cách ly + cảnh báo
~~~

Những con số trên chỉ là ví dụ. Khi Queue message TTL còn 90 giây, không thể áp lịch retry kéo dài nhiều phút mà không cân nhắc hết hạn. Đừng gia hạn vô hạn hoặc bỏ qua số lần thử chỉ để message không bị đánh dấu poison. Với lỗi nghiêm trọng gây mất tiền/dữ liệu, cần cảnh báo sớm hơn ngưỡng retry thông thường.

## 14. Retry, backoff và polling khi queue tạm trống

Một worker không nên liên tục gọi receive hàng trăm lần mỗi giây khi queue trống: nó tiêu thụ transactions, network và gây nhiễu monitoring. Thay vào đó, dùng **bounded polling** có backoff/jitter; khi có message thì xử lý, khi không có thì nghỉ tăng dần trong giới hạn.

### 14.1. Pseudocode worker loop

~~~text
pollDelay = 1 second
while service is running:
    messages = Receive(maxBatch, visibilityTimeout)
    if no messages:
        sleep(min(pollDelay + jitter, 15 seconds))
        pollDelay = min(pollDelay * 2, 15 seconds)
        continue

    pollDelay = 1 second
    for each received message:
        if event already Completed:
            Delete using current pop receipt
        else:
            process with idempotency + bounded timeout
            if success committed:
                Delete using current pop receipt
            else:
                retry by controlled visibility/backoff
                or move to poison after policy threshold
~~~

Không nên dùng `sleep` trên toàn bộ worker pool theo cách khiến message khác bị chặn. Có thể dùng nhiều worker instances hoặc asynchronous I/O phù hợp, nhưng phải hạn chế concurrency theo DB/API downstream, không chỉ theo số CPU.

### 14.2. Backoff trên message và polling backoff là hai thứ khác nhau

- **Polling backoff:** giảm số request receive khi queue trống hoặc lỗi service.
- **Message retry backoff:** trì hoãn một message thất bại trước lần receive tiếp theo, có thể dùng `Update Message` với visibility timeout mới hoặc để timeout đã đặt hết.

Khi hai loại backoff bị nhầm, một worker có thể polling ít nhưng cứ nhận ngay một message lỗi, hoặc ngược lại mọi job tốt bị trì hoãn dù chỉ một job đang lỗi.

### 14.3. Giới hạn thời gian và cancellation

Một worker production cần xử lý:

- **Graceful shutdown** khi App Service/Container Apps/AKS dừng instance.
- Thời gian tối đa dành cho mỗi job và khả năng checkpoint.
- Bản ghi `Processing`/`Completed` ở database để khôi phục an toàn.
- Không cho retry vô hạn trong HTTP client hoặc SDK khi vượt deadline job.
- Giới hạn tối đa số message xử lý đồng thời và số connection đến downstream.
- Cơ chế tạm dừng consumer khi database/partner API đang sự cố diện rộng.

Nếu worker nhận batch 32 messages với visibility 60 giây nhưng chỉ có một luồng xử lý tuần tự, những message cuối có thể bị lộ lại **trước khi đến lượt**. Batch size, concurrency và visibility phải được thiết kế cùng nhau.

## 15. Tạo Azure Queue Storage bằng Azure CLI trong môi trường lab

Phần này tạo **storage account và queue thử nghiệm**, sau đó dùng SDK ở các phần trước để thao tác. **Không thực thi trong lúc soạn bài.** Tạo resource thật có thể phát sinh phí; phải xác nhận subscription và quyền trước khi chạy.

### 15.1. Chuẩn bị

- Có Azure CLI và đăng nhập Microsoft Entra ID vào đúng tenant/subscription.
- Có quyền tạo resource group/storage account theo chính sách tổ chức.
- Có role **data-plane Queue Storage** tương ứng để tạo queue hoặc gửi/nhận messages.
- Môi trường cho phép truy cập endpoint `https://<account>.queue.core.windows.net`.
- Tên storage account hợp lệ, duy nhất trên Azure; tên queue tuân theo quy tắc tên Storage Queue.

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-queue-lab"
LOCATION="southeastasia"
ACCOUNT="<globallyuniquestorageaccount>"
QUEUE="invoice-jobs"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id, name:name, tenantId:tenantId}" -o table
~~~

Không chạy nguyên xi placeholder `<...>`. Tên và region chỉ là ví dụ; nếu tổ chức dùng landing zone hoặc resource group được cấp sẵn, **không tự tạo thêm resource group bên ngoài phạm vi**.

### 15.2. Tạo StorageV2 account

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION"

az storage account create \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --https-only true \
  --min-tls-version TLS1_2
~~~

`Standard_LRS` thích hợp cho **lab đơn giản**, không phải khuyến nghị mặc định cho workload cần chịu lỗi availability zone hoặc thảm họa vùng. Khi production, chọn redundancy/replication dựa trên RPO/RTO, khả năng hỗ trợ và chi phí thực. Đừng thay đổi cấu hình network/keys trên một storage account đang dùng chung chỉ để chạy bài này.

### 15.3. Tạo queue với Microsoft Entra authentication

~~~bash
az storage queue create \
  --account-name "$ACCOUNT" \
  --name "$QUEUE" \
  --auth-mode login
~~~

Nếu bản Azure CLI đang sử dụng có khác biệt ở lệnh hoặc option, kiểm tra `az storage queue create --help`. Nếu gặp lỗi `AuthorizationPermissionMismatch`, cần kiểm tra **vai trò data plane**, scope, thời gian lan truyền role assignment, tenant/subscription và network. Quyền quản lý storage account ở control plane **không mặc nhiên** có quyền đọc/ghi tất cả queue messages qua token Entra.

Kiểm tra bằng câu lệnh đọc (khi CLI hỗ trợ):

~~~bash
az storage queue list \
  --account-name "$ACCOUNT" \
  --auth-mode login \
  --output table
~~~

Phần gửi/nhận/gia hạn/delete sử dụng Python SDK vì nó làm rõ pop receipt và visibility timeout. Không cần bật storage account key hoặc lưu connection string có key để chạy bài với Entra ID nếu role và tính năng được hỗ trợ.

### 15.4. Kiểm tra RBAC trước khi đổ lỗi SDK

Một người có thể tạo StorageV2 account bằng `Contributor` rồi gặp 403 khi gửi Queue message. Đây là vấn đề tách **control plane** và **data plane**. Hãy yêu cầu quản trị viên cấp vai trò **Storage Queue Data Message Sender/Processor/Contributor** đúng nhu cầu và phạm vi theo cấu hình Azure hiện hành, rồi chờ quyền lan truyền trước khi thử lại.

Không cấp `Owner` toàn subscription hoặc bật Shared Key vô thời hạn để né lỗi phân quyền trong lab.

## 16. Bảo mật Queue Storage với Entra ID, RBAC và Private Endpoint

Queue Storage là thành phần trung gian, thường nằm giữa API và các worker chạy trên Azure App Service, Azure Functions, Azure Container Apps, AKS hoặc VM. Thiết kế bảo mật cần trả lời:

1. **Ai được gửi** message?
2. **Ai được nhận và xóa** message?
3. **Ai được tạo/xóa queue hoặc clear backlog?**
4. **Đường mạng nào** có thể kết nối đến queue endpoint?
5. **Message chứa gì** và dữ liệu nhạy cảm được bảo vệ thế nào?

### 16.1. Role data-plane theo nguyên tắc tối thiểu

Azure Storage Queue hỗ trợ Microsoft Entra authorization và các vai trò dữ liệu phù hợp.

| Principal | Nhu cầu | Vai trò/cơ chế xem xét |
|---|---|---|
| **API producer** | Gửi message vào queue cụ thể | `Storage Queue Data Message Sender` ở phạm vi nhỏ nhất được hỗ trợ |
| **Worker consumer** | Peek/receive/delete message | `Storage Queue Data Message Processor` theo phạm vi cần xử lý |
| **Provisioning pipeline** | Tạo queue và quản lý metadata/permissions theo IaC | Role có quyền quản trị queue phù hợp, ví dụ `Storage Queue Data Contributor` khi thật sự cần |
| **Nhóm giám sát** | Xem metrics/logs; không xử lý message | Azure Monitor/Reader phù hợp và quyền data-plane tối thiểu nếu cần peek |
| **Điều tra poison** | Đọc và quyết định replay poison message | Role giới hạn trên poison queue, quy trình phê duyệt |

Tên vai trò và các `DataActions` chính xác cần được kiểm tra với Azure RBAC tại thời điểm triển khai. **Role có quyền gửi** không nên tự động có quyền **clear queue**. Một worker thường cũng không cần quyền xóa toàn bộ queue resource.

**Microsoft Entra ID/managed identity** giảm nhu cầu giữ account key hoặc SAS dài hạn. Với Azure Functions/App Service/VM/Container Apps/AKS, chọn cơ chế workload identity được nền tảng hỗ trợ. Producer và consumer có thể dùng **hai managed identities khác nhau** để tránh một principal vừa gửi vừa xóa toàn bộ message không cần thiết.

### 16.2. Shared Key và SAS

Azure Storage hỗ trợ các phương án chứng thực khác theo cấu hình, gồm account key và Shared Access Signature (SAS). Nếu sử dụng:

- Không nhúng key/SAS vào Docker image, source code, log, repository hoặc URL công khai.
- Giới hạn quyền, thời hạn, scope và điều kiện SAS theo khả năng hỗ trợ.
- Ưu tiên credential ngắn hạn/managed identity khi workload hỗ trợ.
- Lập kế hoạch rotate/revoke và phát hiện truy cập bất thường.
- Cân nhắc chính sách vô hiệu hóa Shared Key authorization nếu phù hợp workload và toàn bộ ứng dụng phụ thuộc; không thay đổi một account dùng chung khi chưa kiểm tra tác động.

**SAS URL là bearer credential** trong phạm vi hiệu lực của nó. Dù chỉ có quyền send, việc để lộ SAS có thể cho phép người khác bơm hàng nghìn message rác, gây chi phí hoặc tắc worker.

### 16.3. Network isolation và private DNS

Storage account có thể được bảo vệ bằng network rules và **Private Endpoint** cho subresource `queue`. Khi dùng private endpoint:

~~~text
API / Worker trong VNet
         |
         | HTTPS + managed identity
         v
Private DNS: mystorageaccount.queue.core.windows.net
         |
         v
Private Endpoint (subresource: queue)
         |
         v
Azure Queue Storage
~~~

Private DNS zone thường liên quan `privatelink.queue.core.windows.net`. Nhưng hostname ứng dụng sử dụng vẫn thường là `<account>.queue.core.windows.net` để TLS/SNI và routing được xử lý theo hợp đồng dịch vụ; DNS phân giải nó về private IP khi đường private được cấu hình đúng.

**Private Endpoint cho Blob không tự bảo vệ endpoint Queue.** Nếu hệ thống cần cả Blob Storage và Queue Storage đi qua mạng riêng, cần đánh giá **hai subresources** và DNS tương ứng. Cũng cần phân biệt VNet Integration outbound của App Service với Private Endpoint inbound cho Storage; một subnet chứa Private Endpoint không tự tạo quyền dữ liệu.

Các điểm cần kiểm thử:

- DNS của **đúng worker runtime**, không chỉ máy quản trị, phân giải queue endpoint như mong muốn.
- Route/NSG/firewall/proxy cho phép HTTPS 443 từ workload tới queue.
- Public network access của storage account ở trạng thái đúng chính sách.
- Worker có Entra token/role data-plane hợp lệ.
- Azure Monitor và các thành phần vận hành vẫn có đường truy cập theo thiết kế.
- Khi thay đổi DNS hoặc private endpoint, các Pods/VM/App Service instances có thể cần làm mới kết nối/resolve theo hành vi client.

### 16.4. Bảo vệ nội dung message

Hàng đợi có thể chứa ID khách hàng, mã đơn hàng, địa chỉ Blob và correlation ID. Cần:

- Chỉ gửi các trường tối thiểu để thực hiện job; không đưa mật khẩu, access token hoặc PII không cần thiết vào message.
- Dùng HTTPS/TLS và encryption at rest theo khả năng Azure Storage.
- Phân loại dữ liệu trong main/poison queue, quy định TTL và quyền xem log.
- Nếu payload lớn/nhạy cảm, lưu trong Blob Storage có quyền hạn chế; message chỉ mang reference/ID.
- Không log toàn bộ body khi có lỗi parse hoặc poison nếu body có thể chứa thông tin nhạy cảm.
- Kiểm tra quyền xóa/clear queue bởi operator và ghi audit cho thao tác thay đổi quản trị.

**Base64 không phải mã hóa bảo mật.** Nó chỉ biểu diễn bytes dưới dạng text thuận tiện truyền qua giao thức. Dữ liệu cần bí mật phải được bảo vệ bằng quyền, mạng, TLS, mã hóa và quản trị khóa phù hợp.

## 17. Giám sát queue, worker và kết quả nghiệp vụ

Một pipeline queue có thể “không báo lỗi” nhưng đang tích tụ hàng trăm nghìn job chậm xử lý. Giám sát không chỉ nhìn kích thước queue mà phải đo **thời gian chờ, tốc độ xử lý, số lần retry, số job poison và tỷ lệ thành công nghiệp vụ**.

### 17.1. Những nguồn thông tin quan sát

| Nguồn | Câu hỏi có thể trả lời |
|---|---|
| **Azure Monitor metrics cho Storage Queue** | Request rate, transactions, latency, availability, ingress/egress có bất thường? |
| **Storage diagnostic/resource logs** | Request nào bị 403/404/5xx, caller và latency theo khả năng logging? |
| **Queue properties** | Approximate message count đang tăng hay giảm? |
| **Worker application logs** | Event ID nào được nhận, retry/extend/delete bao nhiêu lần, thất bại vì sao? |
| **Application Insights/OpenTelemetry** | Trace API → queue → worker → SQL/Blob/API đối tác |
| **Business database** | Job nào Pending/Processing/Completed/Failed và thời gian xử lý thực? |
| **Azure Activity Log** | Ai thay đổi storage account, network policy, role hoặc cấu hình queue control plane? |
| **Azure Cost Management** | Transactions, storage, egress, logging và compute workers phát sinh thế nào? |

Không mặc định tạo Log Analytics workspace là Queue Storage logs tự chảy vào đó: phải cấu hình diagnostic settings, workspace, retention và quyền truy cập theo tính năng được hỗ trợ. Tùy Azure Monitor metric, dimension của Queue service có thể khác; xác minh tên metric/schema trước khi viết KQL hoặc alert.

### 17.2. Approximate count không phải backlog age

Đọc số lượng ước lượng bằng SDK:

~~~python
properties = queue.get_queue_properties()
print("Approximate message count:", properties.approximate_message_count)
~~~

Con số này là **ước lượng**, có thể chậm so với thay đổi thực tế và không cho biết **message lâu nhất đang chờ bao nhiêu phút**, có bao nhiêu message invisible, hoặc số job đã xử lý xong nhưng chưa delete.

Để đo queue latency có ý nghĩa, producer ghi timestamp UTC và event ID; worker ghi nhận thời điểm nhận và thời điểm xử lý xong, sau đó tính:

~~~text
Time to start = firstProcessingStartedAt - enqueuedAt
Processing duration = completedAt - firstProcessingStartedAt
End-to-end latency = completedAt - API acceptedAt
Retry count ≈ dequeueCount - 1, nhưng phải đọc ngữ cảnh và retry send
~~~

**Không dùng tin tưởng tuyệt đối vào timestamp client không đồng bộ giờ** khi đo SLA. Nên dùng thời điểm do hệ thống server/log tin cậy ghi, đồng bộ clock, phân biệt enqueue time của Queue Storage và event time từ nguồn.

### 17.3. Các KPI và cảnh báo tối thiểu

| KPI/cảnh báo | Ý nghĩa | Cách phản ứng |
|---|---|---|
| **Approximate backlog tăng kéo dài** | Producer nhanh hơn consumer hoặc workers chết | Kiểm tra worker health, throughput, dependency |
| **Oldest job age vượt SLA** | Message đang chờ quá lâu | Scale worker, phân tích poison/priority |
| **Retry/dequeue count tăng** | Job lỗi lặp lại hoặc visibility quá ngắn | Phân loại lỗi, kiểm tra receipt/timeout |
| **Poison queue tăng** | Có dữ liệu lỗi hoặc code regression | Cảnh báo owner, review schema, replay có kiểm soát |
| **Delete failure tăng** | Receipt cũ, network lỗi hoặc worker mất visibility | Kiểm tra visibility extension và idempotency |
| **Processor success rate giảm** | Business operations thất bại | Kiểm tra SQL/Blob/downstream và recent deployment |
| **Worker CPU/memory quá tải** | Worker không theo kịp | Scale/tối ưu batch/concurrency |
| **Storage transaction 403 tăng** | Identity/RBAC/firewall policy lỗi | Kiểm tra token, scope, private network |

**Alert phải có người xử lý và runbook.** Ví dụ cảnh báo “poison queue > 0” nên hướng dẫn cách xác định message, bảo vệ PII, sửa producer/worker và replay an toàn, chứ không chỉ hướng dẫn xóa toàn bộ poison queue.

### 17.4. Structured logs

Một record log worker nên có:

~~~json
{
  "eventId": "invoice-request-98421",
  "queueName": "invoice-jobs",
  "messageId": "<storage-message-id>",
  "dequeueCount": 2,
  "operation": "GenerateInvoice",
  "status": "Completed",
  "processingMs": 1842,
  "correlationId": "req-fd42b",
  "errorCategory": null
}
~~~

Không log `pop_receipt`, SAS, account key, customer details hoặc payload nhạy cảm vào nơi nhiều người truy cập khi không cần thiết. Nếu cần trace theo message ID, các trường ID và trạng thái đã đủ trong nhiều tình huống.

## 18. Năng lực xử lý, batch size và chi phí

Queue Storage giúp producer và worker scale độc lập, nhưng việc tăng số worker có thể gây nghẽn cho SQL, Redis, Key Vault hoặc đối tác API. Mục tiêu là tối ưu **throughput với correctness**, không chỉ tối đa số message được receive mỗi giây.

### 18.1. Ước tính công suất

Giả sử:

- Producer tạo trung bình **300 jobs/phút**.
- Một worker có thể xử lý **1 job trong 2 giây** khi có đủ tài nguyên.
- Một worker xử lý một job tại một thời điểm.

Khả năng xử lý lý thuyết một worker:

\[
\frac{60\ \text{giây}}{2\ \text{giây/job}} = 30\ \text{jobs/phút}.
\]

Để cân bằng tải trung bình cần ít nhất:

\[
\frac{300}{30} = 10\ \text{worker lanes}.
\]

Nhưng **10 chỉ là ngưỡng lý thuyết**; còn network, retries, slow tail, giới hạn DB và yêu cầu dự phòng. Nên kiểm thử tải thực tế, chọn concurrency/capacity headroom và giới hạn autoscale tránh làm quá tải downstream.

### 18.2. Batch receive không phải batch transaction

Một lần receive có thể trả nhiều message, nhưng **mỗi message có pop receipt và trạng thái xử lý riêng**. Không coi batch 32 messages như transaction nguyên tử: một job trong batch có thể thành công và được delete, job khác thất bại và xuất hiện lại.

Khi worker nhận nhiều message mà xử lý tuần tự, cần đảm bảo thời gian xử lý toàn batch không vượt visibility của những message chưa đến lượt. Một lựa chọn là batch nhỏ + concurrency phù hợp, hoặc mỗi worker chỉ receive khi đã có capacity xử lý.

### 18.3. Giá thành tác vụ

Tổng chi phí vận hành có thể gồm:

| Thành phần | Nguồn phát sinh |
|---|---|
| **Queue Storage** | Dung lượng message và transactions như send/peek/receive/update/delete theo mô hình giá |
| **Compute workers** | Azure Functions, App Service Plan, Container Apps, AKS nodes hoặc VM |
| **Network** | Egress, NAT Gateway, Firewall, Private Endpoint, kết nối liên vùng |
| **Data services** | Azure SQL/Blob Storage/Redis và các thao tác liên quan |
| **Observability** | Application Insights, Log Analytics, metrics/alerts, retention |
| **Recovery** | Poison processing, replay, backup, công vận hành incident |

Không gán chính sách **Hot/Cool/Archive blob tiers** cho queue messages như thể chúng là Blob Storage objects. Queue và Blob có mô hình dữ liệu/giá/tính năng khác nhau dù cùng storage account.

Để dự toán, dùng Azure Pricing/Cost Management theo region, redundancy, loại account và giá hiện hành; không hardcode giá trên mỗi transaction vào tài liệu vì có thể thay đổi.

### 18.4. Tối ưu thực tế

- Producer gửi **payload nhỏ** thay vì file lớn.
- Tái sử dụng QueueClient và HTTP connections khi SDK cho phép.
- Worker nhận batch **vừa với năng lực xử lý** để hạn chế message bị lộ lại quá sớm.
- Khi queue trống, polling backoff thay vì vòng gọi receive liên tục.
- Visibility timeout dựa trên phân phối thời gian xử lý thực và heartbeat có giới hạn.
- Retry có backoff/jitter và poison policy để ngăn retry storm.
- Scale worker theo backlog/queue age/CPU nhưng giới hạn concurrency của downstream.
- Ghi metrics theo queue, loại job và môi trường; không đổ toàn bộ JSON message vào logs.

## 19. So sánh Queue Storage, Service Bus, Event Grid và Event Hubs

Các dịch vụ messaging Azure giải quyết những bài toán khác nhau. Không nên chọn chỉ theo “tất cả đều truyền message”.

| Nhu cầu | Queue Storage | Azure Service Bus | Event Grid | Event Hubs |
|---|---|---|---|---|
| **Hàng đợi tác vụ đơn giản** | Rất phù hợp | Phù hợp khi cần semantics nâng cao | Không phải queue worker truyền thống | Không phải lựa chọn mặc định |
| **Receive rồi ẩn tạm + delete** | Có, qua visibility/pop receipt | Có receive modes/locks theo mô hình Service Bus | Event delivery/retry theo mô hình riêng | Consumer đọc stream theo offsets |
| **Dead-letter queue native** | Không; tự quản poison hoặc dùng framework | Có theo tính năng hỗ trợ | Có dead-letter destination theo cấu hình | Không phải cơ chế DLQ queue truyền thống |
| **Duplicate detection / sessions** | Tự thiết kế ở tầng ứng dụng | Có tính năng tương ứng theo SKU/điều kiện | Không tương đương message queue sessions | Dựa trên partition/consumer/event semantics |
| **Pub/sub theo sự kiện dịch vụ** | Producer tự gửi vào queue | Topics/subscriptions nếu cần | Đặc biệt phù hợp event routing | Streaming/telemetry nhiều consumer |
| **Lưu/đọc lại luồng sự kiện** | Không có offset replay như event stream | Theo retention/message lifecycle riêng | Không phải event log phân tích dài hạn | Phù hợp với streaming retention/replay |
| **Thứ tự có yêu cầu nghiêm ngặt** | Không FIFO tuyệt đối | Có session/sequence mechanisms phù hợp | Không mặc định thứ tự toàn cục | Thứ tự trong partition theo mô hình stream |

### Quy tắc chọn nhanh

- **Queue Storage:** background jobs đơn giản, tích hợp ứng dụng lưu trữ Azure, chi phí và vận hành gọn; ứng dụng tự xử lý retries/idempotency/poison.
- **Service Bus:** workflow enterprise cần **sessions, dead-letter queue native, duplicate detection, scheduled messages hoặc transaction messaging** theo tính năng/SKU hỗ trợ.
- **Event Grid:** “có sự kiện xảy ra” (BlobCreated, resource changed), muốn route tới endpoint, Function, queue hoặc service subscriber.
- **Event Hubs:** thu thập luồng sự kiện/telemetry thông lượng lớn, nhiều consumer groups, đọc lại theo offset/checkpoint.

Ví dụ khi Blob được upload, **Event Grid** có thể phát sự kiện `BlobCreated` tới **Queue Storage** hoặc Azure Function; worker sau đó xử lý nội dung Blob. Đây là cách kết hợp các dịch vụ, không nhất thiết chỉ chọn một sản phẩm.

## 20. Troubleshooting: gửi được nhưng không xử lý, delete thất bại hoặc job bị lặp

Khi một pipeline bị lỗi, hãy chia đường đi thành bốn lớp: **producer gửi → Queue Storage lưu/ẩn → worker nhận và xử lý → worker xác nhận/xóa**. Không thay cùng lúc quyền, visibility timeout, code và firewall vì sẽ khó xác định nguyên nhân.

### 20.1. Bảng lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| `403 AuthorizationPermissionMismatch` | Thiếu RBAC data-plane, sai tenant/principal/scope | Xem managed identity, role Queue Data, thời gian lan truyền; kiểm tra network riêng |
| `401 AuthenticationFailed` hoặc lỗi token | Credential không hợp lệ/hết hạn hoặc cấu hình SDK sai | Kiểm tra DefaultAzureCredential, tenant, token source, không log token |
| Queue endpoint timeout | Firewall/DNS/Private Endpoint/route/proxy lỗi | Kiểm tra DNS của worker đến `<account>.queue.core.windows.net` và HTTPS 443 |
| Send trả lỗi size | JSON hoặc Base64 vượt 64 KiB | Đo encoded size; đưa payload vào Blob Storage rồi gửi reference |
| Send lỗi ký tự/XML | Producer dùng encoding không hợp lệ | Cấu hình text Base64 policy nhất quán giữa hai phía |
| Producer gửi thành công, worker không thấy | Initial visibility delay, worker sai queue, message invisible, TTL hết | Kiểm tra queue/account, timestamp, delay, receive/peek semantics |
| Peek thấy message nhưng receive không như mong đợi | Worker khác đã receive, poll race, visibility hoặc môi trường khác | Đối chiếu logs và queue account; không suy từ peek là quyền xử lý |
| Worker xử lý xong nhưng message trở lại | Chưa delete, delete lỗi, receipt stale, timeout quá ngắn | Xem receipt lifecycle, update/delete status, idempotency |
| Delete báo pop receipt không hợp lệ | Receipt cũ sau update/receive hoặc message đã hết hạn | Lưu receipt mới; đừng xóa bằng token cũ hoặc retry vô hạn |
| Dequeue count tăng nhanh | Message crash liên tục, no backoff, visibility ngắn | Thêm retry policy/poison queue, sửa exception |
| Nhiều hóa đơn/email trùng | Producer retry send hoặc worker được giao lại | Dùng business eventId, unique constraint/idempotency |
| Backlog tăng liên tục | Consumer ít năng lực, lỗi downstream, worker không chạy | Theo dõi queue age, worker health, DB/API bottlenecks |
| Poison queue phình to | Schema regression hoặc job lỗi vĩnh viễn | Phân loại error, sửa producer/worker, replay có kiểm soát |
| Message hết hạn trước khi xử lý | TTL quá ngắn hoặc backlog/delay dài | Điều chỉnh SLA/TTL, cảnh báo queue age, lưu job status bền vững |
| Không có log nào dù worker lỗi | Chưa bật diagnostics hoặc logging bị mất | Kiểm tra worker stdout, App Insights, diagnostic settings, sampling |

### 20.2. Runbook từng bước

**Bước 1 — Xác nhận môi trường.** Lấy subscription, storage account, tên queue, worker instance, thời điểm UTC và business event ID. Không suy từ tên queue vì dev/staging/prod có thể cùng tên queue ở các storage account khác nhau.

**Bước 2 — Kiểm tra producer.** API có trả enqueue success hay timeout? Có ghi `eventId` và timestamp? Có retry tạo duplicate message? Credentials gửi có quyền send?

**Bước 3 — Kiểm tra queue.** Queue tồn tại, storage account có network policy đúng, TTL/delay có hợp lý? Approximate count tăng hay giảm? Peek chỉ để quan sát, không dùng thay receive.

**Bước 4 — Kiểm tra worker.** Worker có đang chạy không? CPU/memory đủ, có kết nối SQL/Blob/Key Vault không? SDK Base64 decode policy có khớp producer không?

**Bước 5 — Kiểm tra visibility và receipt.** Log thời gian receive, `nextVisibleOn`, dequeue count, số lần gia hạn và trạng thái delete. Nếu xử lý thường vượt visibility, giảm batch size hoặc heartbeat phù hợp.

**Bước 6 — Kiểm tra idempotency.** Tra business job status theo `eventId`. Nếu đã Completed nhưng queue còn message, không tạo side effect mới; xử lý xác nhận an toàn với receipt hiện hành.

**Bước 7 — Phân loại lỗi.** Lỗi transient thì backoff/jitter; lỗi vĩnh viễn thì poison queue + alert; lỗi quyền/mạng thì sửa cấu hình chứ không retry vô hạn.

**Bước 8 — Khôi phục và xác minh.** Giảm backlog, kiểm chứng số job hoàn tất theo nghiệp vụ, không chỉ số message giảm. Ghi incident và bổ sung tests/alerts.

### 20.3. Tình huống điều tra cụ thể: receipt đã đổi

~~~text
Worker A receive M, receipt R1, timeout 60s.
Worker A gọi update visibility 120s → nhận receipt R2.
Worker A xử lý thành công.
Worker A dùng R1 để delete → lỗi pop receipt mismatch.
Đến hạn mới, M có thể xuất hiện lại.
~~~

Giải pháp là **dùng R2 để delete** khi receipt vẫn hợp lệ; không cần resend message. Nếu worker đã mất R2 và không chắc trạng thái, phải để message được nhận lại rồi thực hiện quy trình idempotent/ack, không cố brute-force token hoặc clear queue.

### 20.4. Tình huống điều tra: worker chậm nhưng được scale thêm

Queue có 100.000 jobs; nền tảng tăng worker từ 5 lên 50 nhưng database chỉ chịu tối đa 20 kết nối xử lý nặng. Tăng worker có thể làm SQL timeout, retry tăng, visibility hết, queue age tăng hơn nữa.

Cách khắc phục:

- Giới hạn số công việc đồng thời theo năng lực database.
- Tăng worker thận trọng dựa trên **downstream capacity** và mục tiêu queue age.
- Dùng retry backoff/circuit breaker để tránh retry storm.
- Xem xét batch/chia tác vụ thành job nhỏ, xử lý dữ liệu theo khóa ổn định.
- Kiểm tra index, transaction duration và connection pool trên SQL; đừng chỉ mở rộng compute.

## 21. Kiến trúc thực tế: API tạo hóa đơn có hai worker và Azure SQL

**Bối cảnh giả định:** Doanh nghiệp dùng Azure App Service để phục vụ API. Khi người dùng yêu cầu tạo hóa đơn, API ghi metadata vào Azure SQL rồi gửi Queue message. Hai workers chạy trên Azure Container Apps hoặc Azure Functions/VM được hỗ trợ xử lý PDF, lưu vào Blob Storage và cập nhật trạng thái.

### 21.1. Các thành phần

~~~mermaid
flowchart TB
    CLIENT[Khách hàng] --> API[Azure App Service API]
    API --> SQL[(Azure SQL: job state + unique EventId)]
    API -->|Entra identity: Send| QUEUE[(Queue Storage: invoice-jobs)]
    QUEUE -->|Receive 90s + pop receipt| WA[Worker A]
    QUEUE -->|Receive 90s + pop receipt| WB[Worker B]
    WA -->|Idempotent update| SQL
    WB -->|Idempotent update| SQL
    WA --> BLOB[(Blob Storage: output PDF)]
    WB --> BLOB
    WA -. Delete after commit .-> QUEUE
    WB -. Delete after commit .-> QUEUE
    WA -->|After max attempts| POISON[(invoice-jobs-poison)]
    WB -->|After max attempts| POISON
    API -. Request traces .-> MON[Azure Monitor + App Insights]
    WA -. Metrics / logs .-> MON
    WB -. Metrics / logs .-> MON
~~~

Network và identity:

- Producer chỉ được **send**, workers chỉ được **receive/delete** trên main queue và quyền khác theo nhiệm vụ.
- Worker cần quyền Azure SQL/Blob Storage tương ứng, không sử dụng chung account key có quyền rộng nếu managed identity phù hợp.
- Queue/SQL/Blob có thể được kết nối qua private endpoints và DNS/VNet Integration theo kiến trúc mạng.
- Poison queue chỉ cho những người/worker được phép điều tra và replay; không công bố nội dung công khai.
- Gắn `eventId`/`correlationId` vào logs và lưu trạng thái `Pending/Processing/Completed/Failed` trong SQL.

### 21.2. Luồng thành công

1. Client gửi yêu cầu tạo hóa đơn với **idempotency key** ở cấp HTTP/API.
2. API xác thực, ghi bản ghi job vào SQL dưới unique key, lưu payload lớn vào Blob nếu cần.
3. Publisher gửi message nhỏ chứa `eventId`, `invoiceId`, `sourceBlob` và `schemaVersion`.
4. Worker A receive message M với invisibility 90 giây, nhận receipt R1.
5. Worker A xác thực schema, tìm job trong SQL và claim công việc theo quy tắc atomic/idempotent.
6. Worker đọc dữ liệu, tạo PDF và ghi vào Blob với tên ổn định, ví dụ `invoices/INV-98421.pdf`, bảo vệ cập nhật đồng thời bằng điều kiện/phương án versioning phù hợp.
7. Worker commit `Completed` và URL/reference kết quả vào SQL.
8. Worker xóa M bằng R1 hoặc receipt mới nếu đã gia hạn; API trả trạng thái Completed cho client khi được hỏi.

Với xử lý lâu, worker có thể update visibility sau bước 5 hoặc trong lúc tạo PDF; nhớ thay receipt hiện hành sau mỗi update.

### 21.3. Worker A chết sau khi ghi PDF

~~~mermaid
sequenceDiagram
    participant Q as Queue Storage
    participant A as Worker A
    participant B as Worker B
    participant DB as Azure SQL / Blob
    A->>Q: Receive M, receipt R1
    Q-->>A: Hidden during visibility window
    A->>DB: Write PDF + commit Completed(eventId)
    DB-->>A: Success
    Note over A: Crash before Delete
    Note over Q: Visibility timeout expires
    B->>Q: Receive M again, receipt R2
    Q-->>B: Same business eventId, higher dequeue count
    B->>DB: Check Completed(eventId)
    DB-->>B: Already Completed
    B->>Q: Delete M using R2
~~~

Kết quả đúng: hệ thống không sinh hóa đơn thứ hai hoặc gửi email hai lần. Nếu downstream gửi email, cần cơ chế idempotency/outbox riêng cho email. Việc SQL đã Completed mà email chưa gửi phải được mô hình hóa thành các bước/trạng thái rõ ràng, thay vì coi một boolean Completed bao trùm mọi side effect.

### 21.4. Worker A xử lý quá chậm

Giả sử A mất bốn phút, receive timeout 90 giây. Nếu A không cập nhật visibility, B có thể nhận lại cùng job ở phút thứ hai. Ngay cả khi B thấy SQL `Processing`, không nên mặc định bỏ qua mãi: cần có **processing owner/deadline/lease trong database** để nhận biết A đã chết hay vẫn đang làm.

Thiết kế:

- Chia job thành các bước nhỏ có checkpoint khi khả thi.
- Gia hạn message visibility trước khi hết hạn, giữ pop receipt mới.
- Có processing ownership/expiry bền vững trong SQL để chống hai worker cùng ghi.
- Khi mất quyền/gia hạn thất bại, A dừng side effects không idempotent.
- Khi quá giới hạn xử lý, đánh dấu Failed hoặc chuyển poison theo runbook.

### 21.5. Vận hành sau khi triển khai

| Lớp | Câu hỏi kiểm tra |
|---|---|
| API | Tỷ lệ `202 Accepted` và lỗi enqueue/SQL có bình thường? |
| Queue | Approximate backlog và oldest job age có tăng? |
| Workers | Số jobs/phút, p95 xử lý, retry/dequeue count, CPU/memory? |
| SQL | Unique EventId, số Pending/Completed/Failed và transaction failures? |
| Blob | File tồn tại, checksum/nội dung và quyền đọc phù hợp? |
| Security | Managed identities/RBAC và private DNS/firewall đúng? |
| FinOps | Queue transactions, worker scale, database/logging/network phí bao nhiêu? |
| Recovery | Có thể xử lý lại job poison, restore dữ liệu và chứng minh không duplicate? |

### 21.6. Chọn worker runtime

**Azure Functions Queue Storage trigger** có thể tự polling, nhận message và quản lý retry/poison theo cấu hình extension; phù hợp với nhiều tác vụ ngắn/bất đồng bộ. **Azure Container Apps/AKS/VM** cho phép bạn vận hành worker tùy biến, long-running, với SDK để tự điều khiển visibility/receipt/concurrency. Chọn theo thời lượng job, điều kiện scale, network, operational overhead và chi phí.

Không trộn lẫn logic SDK receive/delete thủ công với Queue-trigger runtime trên cùng một message theo cách tạo **hai chủ thể điều phối cùng lúc** mà không thiết kế concurrency và idempotency rõ ràng.

## 22. Bài thực hành: kiểm chứng visibility timeout và pop receipt

**Đề bài:** Bạn có queue `invoice-jobs`, mỗi message chứa `eventId` và `invoiceId`. Một worker xử lý mỗi hóa đơn trong 75–180 giây. Hệ thống có ba worker instances và phải tránh tạo hai PDF hoặc gửi hai email cho cùng một hóa đơn.

Thực hiện các yêu cầu sau trong **storage account lab riêng**, với thông điệp thử nghiệm không chứa dữ liệu thật:

1. Tạo QueueClient bằng `DefaultAzureCredential` và thống nhất Base64 encode/decode cho producer/worker.
2. Tạo queue nếu có quyền, hoặc xác minh queue đã được provisioning từ IaC.
3. Gửi message với `time_to_live=3600` và initial `visibility_timeout=0`. Ghi lại `eventId` và message ID.
4. Gọi `peek_messages` trước và sau một lần receive; quan sát khác biệt về visibility và vì sao peek không cung cấp quyền delete.
5. Receive message với visibility timeout 60 giây, ghi `next_visible_on` và `dequeue_count`.
6. Cố tình không delete message, đợi hết khoảng ẩn và receive lại trong lab; ghi dequeue count mới.
7. Receive message khác với timeout 90 giây, gọi update để đặt 120 giây và giữ **pop receipt mới**.
8. Nêu vì sao delete bằng receipt cũ có thể thất bại; sau khi xử lý lab hoàn thành, thử delete bằng receipt hiện hành.
9. Mô phỏng worker crash sau SQL commit nhưng trước delete; trình bày unique constraint/idempotency key sẽ ngăn tạo hai hóa đơn thế nào.
10. Thiết kế poison policy khi một message schema sai bị receive 5 lần.
11. Tính toán worker capacity nếu hệ thống nhận 600 jobs/phút và một luồng worker xử lý 20 jobs/phút, chưa tính overhead.
12. Trình bày cách scale số worker nhưng không vượt quota kết nối SQL.
13. Thiết kế Azure RBAC cho producer chỉ send, consumer receive/delete, platform team tạo queue.
14. Nếu storage account private-only, vẽ đường mạng từ App Service/AKS tới Queue Private Endpoint và DNS.
15. Liệt kê tối thiểu năm KPI/alert giúp xác định tình trạng backlog, retry, poison, xử lý chậm và lỗi quyền.
16. Lập kế hoạch dọn lab, nhưng không xóa queue hoặc resource group có dữ liệu/tài nguyên dùng chung.

### 22.1. Câu hỏi dòng thời gian

Message M có TTL một giờ và initial visibility delay bằng 0:

~~~text
10:00:00  Worker A receive M với visibility 45 giây, receipt R1
10:00:30  Worker A update visibility 90 giây, receipt mới R2
10:01:00  Worker A đã ghi kết quả vào SQL
10:01:10  Worker A gọi delete dùng R1
10:02:00  Worker B thử receive M
~~~

Hãy trả lời:

- M dự kiến có thể xuất hiện lại lúc nào nếu không được delete?
- Lệnh delete dùng R1 có chắc thành công không?
- Nếu B nhận được M, B cần làm gì trước khi ghi hóa đơn?
- Nếu A đã delete thành công bằng R2 lúc 10:01:15, B có còn nhận được M theo luồng bình thường không?

### 22.2. Lời giải tham khảo

**Dòng thời gian:** A update ở 10:00:30 với visibility 90 giây, nên M có thể xuất hiện lại **khoảng 10:02:00** nếu không bị xóa hoặc hết TTL. Delete với **R1 đã cũ** có thể bị từ chối do update đã phát hành **R2**. Khi B nhận M sau thời điểm đó, B có receipt mới; nó phải kiểm tra SQL theo `eventId` xem job đã Completed chưa. Nếu đã Completed, không tạo hóa đơn thứ hai và có thể delete bằng receipt của B. Nếu A đã delete hợp lệ bằng R2 trước đó, M không còn trong queue để B nhận trong luồng bình thường.

**Capacity:** 600 jobs/phút, 20 jobs/phút mỗi worker lane:

\[
\frac{600}{20}=30\ \text{worker lanes tối thiểu theo lý thuyết}.
\]

Cần dự phòng cho retries, spike, biến thiên thời gian xử lý và khả năng SQL. Nếu SQL chỉ chịu 15 thao tác nặng đồng thời thì tăng ngay 30 lanes có thể gây overload; phải tối ưu job/DB, giới hạn concurrency, backlog SLA hoặc mở rộng downstream theo thiết kế.

**Poison:** sau các lần xử lý thất bại theo policy, ghi metadata an toàn sang poison queue, gửi cảnh báo và xóa bản gốc **chỉ sau khi poison write đã được xác nhận**, đồng thời cho phép dedup nếu hai thao tác gửi/xóa không nguyên tử. Không clear cả queue.

### 22.3. Các lỗi người học nên tự phát hiện

| Sai lầm trong thiết kế | Vì sao không đúng? |
|---|---|
| Xử lý công việc 3 phút với visibility 30 giây, không gia hạn | Có thể nhận lại khi worker A vẫn chạy |
| Dùng `peek_messages` để lấy job rồi delete | Peek không cung cấp pop receipt/không khóa message |
| Gia hạn message nhưng giữ receipt cũ | Delete/update sau đó có thể thất bại |
| Retry send cùng business event với UUID mới | Không thể dedup theo business key ổn định |
| Xóa message trước khi ghi kết quả | Worker crash sau delete khiến job không còn để retry |
| Ghi SQL xong là đủ, không cần idempotency | Crash trước delete gây xử lý lại/duplicate |
| `dequeue_count >= 5` thì clear queue | Hủy cả các thông điệp tốt khác |
| Tin rằng Queue Storage có DLQ native | Poison queue cần ứng dụng/framework quản lý |
| Để producer có Storage Account key quyền rộng | Vi phạm least privilege và tăng blast radius |
| Chỉ nhìn queue count mà không đo job age | Không biết SLA xử lý bị trễ ra sao |

## 23. Checklist vận hành producer, consumer và queue

### Trước khi triển khai

- [ ] Đã xác định yêu cầu queue hay Service Bus/Event Grid/Event Hubs phù hợp hơn.
- [ ] API/job contract có `eventId` ổn định, `schemaVersion`, correlation ID và payload nhỏ.
- [ ] Producer và consumer dùng chính sách encoding giống nhau.
- [ ] TTL, initial delay, visibility timeout và maximum job duration tương thích.
- [ ] Worker có logic idempotency, transaction/unique key và checkpoint nếu job dài.
- [ ] Có retry policy theo loại lỗi, backoff/jitter và ngưỡng poison.
- [ ] Đã tạo poison queue/runbook xử lý và phân quyền xem dữ liệu nhạy cảm.
- [ ] Managed identities/RBAC của producer/consumer được tách tối thiểu.
- [ ] VNet/Private Endpoint/private DNS/firewall truy cập được từ runtime.
- [ ] Có giám sát backlog age, retry, delete errors, poison count, worker health và chi phí.
- [ ] Có bài test worker crash trước delete và timeout dẫn đến duplicate.

### Trong lúc chạy

- [ ] Đo thời gian xử lý thực tế p50/p95/p99, điều chỉnh visibility theo dữ liệu.
- [ ] Nếu gia hạn visibility, luôn lưu **receipt mới nhất**.
- [ ] Delete chỉ sau khi business outcome đã được commit bền vững.
- [ ] Không chia batch quá lớn khiến message hết visibility trước khi xử lý.
- [ ] Không tăng consumer concurrency vượt capacity của database/đối tác.
- [ ] Phân loại lỗi transient/permanent, không retry 403/schema error vô hạn.
- [ ] Đảm bảo graceful shutdown và giới hạn tổng thời gian xử lý.
- [ ] Kiểm tra poison, thông điệp hết hạn và job quá SLA hằng ngày/theo yêu cầu.

### Khi có incident

- [ ] Xác nhận đúng subscription, storage account, queue và worker runtime.
- [ ] Lưu event ID/correlation ID, timestamps, dequeue count và error category.
- [ ] Kiểm tra đường mạng và credential trước khi thay đổi timeout.
- [ ] Đối chiếu SQL/Blob state để tránh replay tạo side effect trùng.
- [ ] Tạm giảm/pause consumer khi downstream outage gây retry storm.
- [ ] Không clear queue hoặc xóa toàn bộ poison backlog để làm sạch dashboard.
- [ ] Khôi phục message theo quy trình có idempotency và audit.
- [ ] Báo cáo nguyên nhân, ảnh hưởng và biện pháp phòng ngừa.

## 24. Dọn dẹp lab và tránh mất dữ liệu

Sau khi thực hành, cần xác định **tài nguyên được phép xóa**. Một storage account có thể chứa không chỉ queue lab mà còn Blob containers, file shares hoặc queue của ứng dụng khác; xóa cả resource group có thể phá hủy nhiều tài nguyên không liên quan.

### 24.1. Kiểm kê trước khi xóa

~~~bash
az account show --query "{id:id,name:name}" -o table

az resource list \
  --resource-group "$RG" \
  --output table

az storage queue list \
  --account-name "$ACCOUNT" \
  --auth-mode login \
  --output table
~~~

Khi kiểm tra backlog, dùng queue properties/monitoring trong phạm vi quyền được phép. **Không xem việc queue đang trống gần đúng là bằng chứng không còn job quan trọng**: có thể có message invisible hoặc producer đang gửi mới. Nên tạm dừng producer/consumer, xác minh trạng thái nghiệp vụ và thay đổi sở hữu trước khi xóa.

### 24.2. Lệnh dọn dẹp chỉ để tham khảo

~~~bash
# CHỈ dành cho tài nguyên lab riêng, sau phê duyệt và kiểm kê.
# Lệnh dưới đây được comment, KHÔNG tự thực thi:

# az storage queue delete \
#   --account-name "$ACCOUNT" \
#   --name "$QUEUE" \
#   --auth-mode login

# Chỉ xóa resource group nếu 100% tài nguyên trong đó do lab sở hữu.
# az group delete --name "$RG" --yes
~~~

Xóa queue làm mất các message còn trong đó, bao gồm những thông điệp chưa nhìn thấy do visibility timeout; dữ liệu có thể không khôi phục được. Nếu queue phục vụ production hoặc có yêu cầu lưu giữ bằng chứng, cần retention/runbook và phê duyệt của chủ hệ thống. Không xóa poison queue trước khi xử lý các công việc lỗi còn tồn đọng.

Đừng quên các tài nguyên đi kèm có thể tính phí: Storage account, App Service/Functions/Container Apps/VM workers, Private Endpoint, NAT/Firewall, Azure SQL/Blob Storage, logs và backup. **Xóa ứng dụng worker không đồng nghĩa dừng mọi chi phí** nếu các tài nguyên nền tảng vẫn tồn tại.

## 25. Ghi nhớ

**Azure Queue Storage** giúp tách producer và worker trong một kiến trúc bất đồng bộ đơn giản, nhưng để vận hành an toàn phải hiểu rõ **thông điệp được ẩn tạm chứ không bị xóa ngay khi nhận**.

Những nguyên tắc quan trọng:

1. **Send:** producer gửi message nhỏ, có `eventId`/schema version, TTL và initial visibility delay phù hợp; không gửi payload lớn/secret.
2. **Peek khác Receive:** peek chỉ quan sát message visible; receive làm message invisible và trả **message ID + pop receipt**.
3. **Visibility timeout:** hết hạn mà chưa delete, message có thể được nhận lại; không phải exclusive lock bảo đảm exactly-once.
4. **Update visibility:** gia hạn trước khi hết hạn, lưu **pop receipt mới** và tôn trọng TTL/giới hạn dịch vụ.
5. **Delete sau commit:** chỉ xóa khi kết quả nghiệp vụ đã được lưu bền vững, bằng receipt hiện hành; xóa thất bại phải xử lý idempotent khi message trở lại.
6. **At-least-once/duplicate:** Queue Storage không bảo đảm FIFO tuyệt đối hoặc đúng một lần xử lý; dùng business event ID, unique constraint, transaction/outbox và idempotency.
7. **Retry và poison:** phân loại lỗi, backoff/jitter, giới hạn số lần thử; Storage Queue không có dead-letter queue native.
8. **Security:** ưu tiên Entra/managed identity, RBAC data-plane theo nhiệm vụ, network/private endpoint cho `queue` và payload không chứa bí mật.
9. **Operations:** theo dõi queue age, approximate backlog, dequeue count, poison, worker errors, delete failures, throughput và chi phí.
10. **Kiến trúc:** chọn Queue Storage cho background jobs đơn giản; dùng Service Bus, Event Grid hoặc Event Hubs khi cần những semantics khác.

Một hệ thống hàng đợi chỉ được coi là hoàn tất về mặt vận hành khi có thể trả lời **message nào đã gửi, ai đang xử lý, khi nào message sẽ xuất hiện lại, kết quả nghiệp vụ đã được ghi bền vững chưa, và xử lý thế nào nếu cùng công việc được giao lại**.
