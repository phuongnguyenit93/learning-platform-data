# Khóa chống xử lý trùng bằng mã yêu cầu nghiệp vụ trong MongoDB

Trong hệ thống thực tế, **một yêu cầu nghiệp vụ có thể được gửi đến server nhiều lần** dù người dùng chỉ muốn thực hiện một hành động. Ví dụ: khách hàng nhấn nút “Đặt hàng”, ứng dụng đã tạo đơn thành công nhưng phản hồi HTTP bị mất; trình duyệt, API gateway hoặc worker gửi lại request. Nếu backend tạo đơn mới ở mỗi lần nhận, hệ thống sẽ sinh **đơn hàng trùng**, có thể kéo theo giữ hàng, trừ tiền hoặc gửi thông báo nhiều lần.

MongoDB cung cấp những công cụ giúp phòng tránh tình huống này: **unique index**, **ghi nguyên tử trên một document**, **upsert**, **conditional update**, **transaction** khi nhiều document phải thay đổi đồng thời và các cơ chế phối hợp với hàng đợi/sự kiện. Nhưng MongoDB không tự biết hai HTTP request “cùng một ý định nghiệp vụ”. Ứng dụng phải đưa ra một **mã yêu cầu ổn định** và thiết kế hợp đồng xử lý lại rõ ràng.

Bài học đi từ vấn đề cạnh tranh đến các mẫu triển khai cụ thể:

- Gắn **requestId/idempotency key** cho một ý định nghiệp vụ và tái sử dụng mã đó khi retry.
- Dùng **unique compound index** để không thể tạo hai bản ghi của cùng một yêu cầu trong cùng phạm vi.
- Xử lý **hai request đồng thời** mà không dựa vào thao tác “find trước, insert sau”.
- Phân biệt yêu cầu đã **COMPLETED**, đang **PROCESSING**, bị lỗi và **cùng mã nhưng khác payload**.
- Kết hợp **transaction, outbox, lease và cơ chế chống trùng ở hệ thống ngoài** khi nghiệp vụ phức tạp.
- Hiểu giới hạn của **retryable writes**, **TTL** và các tuyên bố “exactly once”.

Các ví dụ sử dụng **mongosh**, tiếp theo là **MongoDB Java Sync Driver** và **Spring Data MongoDB**. Mọi thao tác ghi đều chỉ dành cho database thử nghiệm; không chạy trên collection sản xuất khi chưa có kế hoạch quản lý dữ liệu và index.

## 1. Tại sao gửi lại request là chuyện bình thường?

Một chuỗi xử lý có thể diễn ra như sau:

~~~text
Người dùng              Backend                  MongoDB
    |                      |                       |
    | POST /orders         |                       |
    | requestId=R-100      |                       |
    |--------------------->| insert order          |
    |                      |---------------------->|
    |                      |<--- ghi thành công ---|
    |              X-------|                       |
    |  Phản hồi mạng bị mất |                       |
    |                      |                       |
    | POST /orders lần nữa |                       |
    | requestId=R-100      |                       |
    |--------------------->|                       |
    |                      |                       |
~~~

Ở thời điểm retry, client **không biết** lần đầu backend đã ghi thành công hay chưa. Nếu server cứ tạo một mã đơn mới và insert lại, hai đơn có thể cùng đại diện cho một ý định đặt hàng.

Những nguồn request lặp thường gặp:

1. Client retry khi timeout, mất kết nối hoặc nhận lỗi 5xx.
2. Người dùng nhấn nhiều lần vì chưa thấy kết quả.
3. API gateway/proxy thực hiện retry theo chính sách.
4. Message broker giao lại một message khi consumer chưa xác nhận.
5. Worker crash sau khi ghi thành công nhưng trước khi ghi nhận đã xử lý.
6. Hệ thống đồng bộ phát lại một sự kiện cũ sau khi reconnect.

Không nên coi retry là một lỗi bất thường cần loại bỏ hoàn toàn. Trong hệ thống phân tán, **thiết kế cho retry an toàn** thường khả thi hơn cố bảo đảm request chỉ xuất hiện một lần.

## 2. Idempotency là gì và “không xử lý trùng” nghĩa là gì?

Một thao tác **idempotent** khi việc thực hiện lại cùng một yêu cầu không tạo thêm những hiệu ứng nghiệp vụ ngoài kết quả dự kiến của lần thực hiện hợp lệ đầu tiên.

Ví dụ, với yêu cầu có requestId **R-100**:

- Lần đầu: tạo **một** đơn hàng O-100.
- Lần thứ hai cùng requestId và cùng nội dung: **không tạo đơn thứ hai**.
- Lần thứ ba: vẫn tham chiếu đến **đúng đơn O-100**.

Điều này **không có nghĩa mọi lần HTTP response phải có cùng mã trạng thái**. Một API có thể trả **201 Created** ở lần đầu, **200 OK** ở lần retry, hoặc trả lại nguyên trạng phản hồi đã ghi nhận. Điều cốt lõi là hợp đồng của API rõ ràng và **không nhân đôi hiệu ứng nghiệp vụ**.

### 2.1. Phân biệt ba khái niệm

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **At-most-once effect** | Một hiệu ứng nghiệp vụ không được phát sinh quá một lần | Một mã yêu cầu chỉ tạo tối đa một đơn |
| **At-least-once delivery** | Hệ thống có thể giao request/message nhiều lần để tăng khả năng hoàn tất | Broker gửi lại message khi chưa được ack |
| **Exactly-once business outcome** | Kết quả nghiệp vụ vừa không bị trùng vừa không mất khi có lỗi | Một lần thanh toán thực sự được ghi nhận đúng một lần |

Unique index giúp giới hạn **số bản ghi trùng khóa trong một collection**, nhưng không tự bảo đảm một email, lệnh thanh toán ở cổng ngoài hoặc thay đổi trên hệ thống khác chỉ xảy ra một lần. Muốn đạt bảo đảm end-to-end, phải phối hợp các thành phần có liên quan.

### 2.2. “Một request” được nhận diện bằng khóa nào?

Các ứng viên thường gặp:

- **Idempotency-Key** do client tạo cho một hành động và giữ nguyên khi retry.
- **clientRequestId** được sinh ở mobile/frontend khi người dùng bắt đầu thao tác.
- **orderReference** hoặc **paymentInstructionId** là mã nghiệp vụ do hệ thống nguồn cấp.
- **eventId** của một message/event được phát một lần rồi có thể giao lại.
- **externalTransactionId** do đối tác thanh toán trả về.

Điều quan trọng không phải tên field mà là **tính duy nhất trong phạm vi được định nghĩa** và **tính ổn định qua các lần gửi lại của cùng hành động**.

Một mã UUID ngẫu nhiên mới được backend tạo **sau mỗi lần nhận retry** không giúp phân biệt request trùng: mỗi lần retry sẽ có một khóa khác và unique index không ngăn tạo bản ghi mới.

## 3. Thiết kế hợp đồng requestId

Trước khi viết code, hãy chốt quy tắc:

1. **Ai cấp mã?** Frontend, hệ thống nguồn, gateway hay backend khi tiếp nhận lần đầu?
2. **Khi nào sinh mã?** Một lần cho **một ý định nghiệp vụ**, trước thao tác có thể retry.
3. **Phạm vi duy nhất?** Toàn hệ thống, theo tenant, theo merchant hay theo loại thao tác?
4. **Có được tái sử dụng mã cho payload khác?** Thông thường **không**.
5. **Giữ mã trong bao lâu?** Phụ thuộc khoảng retry, điều kiện pháp lý và yêu cầu nghiệp vụ.
6. **Trạng thái xử lý đang chạy được phản hồi thế nào?** 202, 409 hoặc cách API quy định.
7. **Kết quả hoàn tất được lấy lại bằng cách nào?** Response snapshot, businessId hoặc GET theo requestId.

Ví dụ header HTTP:

~~~http
POST /v1/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 018f0d9a-bafd-7f32-a6e1-dc1234567890

{
  "customerId": "C-201",
  "amountCents": 250000,
  "currency": "VND"
}
~~~

Khi client retry **cùng ý định tạo đơn**, client gửi lại **cùng Idempotency-Key**. Khi người dùng cố tình tạo **một đơn mới khác**, kể cả các sản phẩm trùng nhau, client phải dùng mã mới.

### 3.1. Phạm vi tenant và loại thao tác

Nếu mỗi tenant có thể tự sinh requestId giống nhau, khóa toàn cục chỉ gồm requestId sẽ vô tình làm tenant A chặn tenant B.

Có thể định nghĩa:

~~~text
(tenantId, requestId)
~~~

Nếu một requestId được phép trùng giữa các loại thao tác, dùng:

~~~text
(tenantId, operationType, requestId)
~~~

Nhưng cần xác định chủ ý: nếu requestId phải duy nhất cho **toàn bộ các endpoint của một tenant**, không nên đưa operationType vào khóa vì điều đó lại cho phép tái sử dụng mã giữa các endpoint.

**Phạm vi duy nhất là một phần của hợp đồng nghiệp vụ**, không phải quyết định ngẫu nhiên khi chọn index.

### 3.2. Khóa phải có giới hạn và được validate

Đừng nhận tùy ý một chuỗi hàng megabyte làm requestId. Nên kiểm tra định dạng, độ dài, mã hóa, ký tự được phép và quan hệ với người dùng đã xác thực. Với đa tenant, **tenantId phải được xác định từ ngữ cảnh xác thực/ủy quyền đáng tin cậy**, không chỉ tin vào một field do client tự khai báo.

Không log toàn bộ token nhạy cảm, thông tin thẻ hoặc payload bí mật chỉ để phục vụ chống trùng. RequestId có thể được ghi log nếu chính sách bảo mật cho phép, nhưng không được dùng nó thay cho cơ chế xác thực.

## 4. Vì sao “find trước, insert sau” bị race condition?

Cách làm dễ sai:

~~~javascript
const existed = db.orders.findOne({
  tenantId: "T-A",
  clientRequestId: "R-100"
});

if (!existed) {
  db.orders.insertOne({
    tenantId: "T-A",
    clientRequestId: "R-100",
    amountCents: 250000
  });
}
~~~

Ở môi trường một luồng, đoạn trên có vẻ hợp lý. Nhưng hai tiến trình có thể xen kẽ:

~~~text
Worker A                         Worker B
   |                                |
   | findOne() -> không thấy       |
   |                                | findOne() -> không thấy
   | insertOne(R-100)               |
   |                                | insertOne(R-100)
   |                                |
      Cả hai đều nghĩ mình được tạo đơn
~~~

MongoDB bảo đảm tính nguyên tử của thao tác ghi trên **một document**, nhưng **không biến cặp lệnh findOne rồi insertOne thành một critical section**. Nếu không có unique constraint, hai insert có thể tạo hai document có cùng tenantId và clientRequestId.

**Nguyên tắc:** dùng một ràng buộc duy nhất được MongoDB cưỡng chế bằng **unique index**, thay vì dùng kiểm tra tồn tại ở tầng ứng dụng làm hàng rào chống cạnh tranh.

## 5. Cách đơn giản nhất: unique compound index trên bản ghi nghiệp vụ

Nếu một yêu cầu chỉ cần tạo **một document đơn hàng** và không có nhiều thay đổi khác phải commit đồng thời, có thể đặt mã yêu cầu ngay trên order.

Chọn database thực hành:

~~~javascript
use idempotency_lab
~~~

Tạo index duy nhất trước khi xử lý dữ liệu:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    clientRequestId: 1
  },
  {
    unique: true,
    name: "uq_orders_tenant_request"
  }
);
~~~

Ý nghĩa: **không thể có hai document orders với cùng cặp (tenantId, clientRequestId)**. Hai requestId giống nhau ở hai tenant khác nhau vẫn có thể tồn tại.

Ví dụ ghi đơn đầu:

~~~javascript
db.orders.insertOne({
  _id: "ORDER-100",
  tenantId: "T-A",
  clientRequestId: "R-100",
  customerId: "C-201",
  amountCents: 250000,
  currency: "VND",
  status: "CREATED",
  createdAt: new Date()
});
~~~

Gửi lại cùng yêu cầu nhưng cố tạo document khác:

~~~javascript
db.orders.insertOne({
  _id: "ORDER-100-RETRY",
  tenantId: "T-A",
  clientRequestId: "R-100",
  customerId: "C-201",
  amountCents: 250000,
  currency: "VND",
  status: "CREATED",
  createdAt: new Date()
});
~~~

Lần thứ hai bị từ chối vì **duplicate key**, thường thấy thông báo **E11000** với code **11000**. Dữ liệu gốc vẫn chỉ có **một document** cho cặp khóa:

~~~javascript
db.orders.find({
  tenantId: "T-A",
  clientRequestId: "R-100"
});
~~~

Đừng diễn giải E11000 thành lỗi hệ thống cần lặp lại insert vô hạn. Trong thiết kế idempotent, duplicate key thường là tín hiệu **mã đã được ghi trước hoặc có request khác vừa thắng cuộc cạnh tranh**. Ứng dụng phải đọc trạng thái/bản ghi hiện hữu, kiểm tra payload và trả kết quả phù hợp.

### 5.1. Unique index là nơi quyết định cuối cùng

Trong trường hợp hai insert cạnh tranh, có thể cả hai request đều không thấy bản ghi trước khi ghi. Nhưng unique index khiến chỉ **một** bản ghi với khóa đó được chấp nhận. Như vậy, ứng dụng không cần một khóa mutex riêng ở bộ nhớ để bảo đảm tính duy nhất của document trong MongoDB.

### 5.2. Tạo unique index trên collection đã có dữ liệu

Nếu collection đã chứa hai đơn cùng cặp (tenantId, clientRequestId), lệnh tạo unique index có thể thất bại. Không nên tự xóa các bản ghi trùng để index tạo được mà chưa phân tích trạng thái đơn, thanh toán và dữ liệu liên quan.

Khi triển khai cho hệ thống có dữ liệu cũ, thường cần:

1. Kiểm kê duplicate bằng aggregation thích hợp.
2. Xác định quy tắc hợp nhất/đánh dấu bản ghi cũ.
3. Ngăn nguồn ghi phát sinh duplicate mới trong lúc migration.
4. Tạo unique index và xác nhận thành công.
5. Chỉ sau đó mở xử lý request theo hợp đồng mới.

Nếu không tạo được unique index, **đừng tuyên bố cơ chế chống trùng đã được bảo đảm** chỉ vì code có kiểm tra findOne().

## 6. Upsert nguyên tử với $setOnInsert

Một cách khác để tạo bản ghi nếu chưa tồn tại là **updateOne + upsert + $setOnInsert**:

~~~javascript
db.orders.updateOne(
  {
    tenantId: "T-A",
    clientRequestId: "R-101"
  },
  {
    $setOnInsert: {
      _id: "ORDER-101",
      customerId: "C-201",
      amountCents: 250000,
      currency: "VND",
      status: "CREATED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

Nếu chưa có order với cặp khóa, MongoDB có thể insert document mới. Nếu đã có, phép update khớp bản ghi cũ và **$setOnInsert không thay đổi nội dung** của document hiện hữu.

Kết quả thao tác thường có:

- **upsertedCount = 1** khi có insert mới.
- **matchedCount = 1** khi tìm thấy document đã có.
- **modifiedCount = 0** cho một update chỉ dùng $setOnInsert trên document khớp sẵn.

Ví dụ thực hành chạy lại cùng thao tác với requestId R-101: bạn nên quan sát **matchedCount** thay vì số lượng đơn tăng thêm. Dù vậy, không được coi mọi kết quả matched là “retry hợp lệ”: phải kiểm tra nội dung request có giống lần đầu không.

### 6.1. Cần unique index ngay cả khi dùng upsert

**Upsert không có nghĩa mọi cuộc đua upsert sẽ luôn được tự động hợp nhất khi thiếu unique index**. Nếu hai request đồng thời cùng nhìn thấy chưa có bản ghi, cả hai có thể tạo document với cùng mã nghiệp vụ nếu không có ràng buộc duy nhất.

Vì vậy, phần cốt lõi vẫn là:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, clientRequestId: 1 },
  { unique: true }
);
~~~

Trong một số điều kiện cụ thể, MongoDB có thể cho một upsert cạnh tranh chuyển thành cập nhật document vừa được request khác tạo. Nhưng không nên thiết kế dựa trên kỳ vọng **mọi** upsert race sẽ tự hoàn tất mà không có duplicate-key error. Ứng dụng cần có nhánh xử lý khi một tiến trình khác thắng cuộc đua.

### 6.2. Vì sao không dùng $set để ghi lại payload ở mỗi retry?

Ví dụ không an toàn:

~~~javascript
db.orders.updateOne(
  {
    tenantId: "T-A",
    clientRequestId: "R-101"
  },
  {
    $set: {
      amountCents: 999999,
      status: "CREATED"
    }
  },
  { upsert: true }
);
~~~

Nếu bản ghi đã tồn tại, thao tác trên **ghi đè số tiền và trạng thái**. Một client dùng lại requestId nhưng thay payload có thể vô tình hoặc cố ý thay đổi yêu cầu đã được chấp nhận trước đó.

Nguyên tắc tốt hơn:

- Dùng **$setOnInsert** cho những trường bất biến của yêu cầu đầu tiên.
- Nếu requestId đã tồn tại, **đọc và đối chiếu dữ liệu gốc**.
- Chỉ thay đổi trạng thái nghiệp vụ bằng các thao tác chuyên biệt, có kiểm tra quyền, trạng thái và điều kiện cập nhật nguyên tử.

### 6.3. Insert hay upsert?

| Cách ghi | Ưu điểm | Điểm cần xử lý |
|---|---|---|
| insertOne + unique index | Ý nghĩa rõ: lần đầu tạo, lần sau duplicate | Bắt E11000 và tra kết quả |
| updateOne + $setOnInsert + upsert | Diễn đạt “tạo nếu chưa có” gọn | Phân biệt inserted/matched, xử lý cạnh tranh và payload |
| findOneAndUpdate + upsert | Có thể trả về document kết quả | Cần chú ý ReturnDocument và unique index |
| findOne rồi insertOne không có unique index | Dễ viết ban đầu | **Không chống được race** |

Với ứng dụng đơn giản chỉ tạo một document, **insertOne + unique index** thường dễ hiểu. Với quy trình muốn trả record hiện có hoặc tạo mới, upsert có thể tiện nhưng vẫn phải thiết kế đầy đủ các trạng thái.

## 7. Không cho cùng requestId đại diện hai nội dung khác nhau

Giả sử lần đầu:

~~~json
{
  "requestId": "R-200",
  "customerId": "C-201",
  "amountCents": 250000,
  "currency": "VND"
}
~~~

Một request sau đó dùng **cùng R-200** nhưng amountCents = 900000:

~~~json
{
  "requestId": "R-200",
  "customerId": "C-201",
  "amountCents": 900000,
  "currency": "VND"
}
~~~

Unique index chỉ biết **khóa trùng**, không biết payload mới có giống payload cũ. Nếu ứng dụng cứ coi duplicate là thành công, request sau có thể nhận kết quả không liên quan đến số tiền nó yêu cầu.

Vì vậy, cần thêm **kiểm tra tính nhất quán của nội dung**.

### 7.1. Lưu dữ liệu chính hoặc payload fingerprint

Một bản ghi idempotency có thể có:

~~~javascript
{
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-200",
  requestFingerprint: "sha256:<digest-of-canonical-business-payload>",
  status: "COMPLETED",
  resourceId: "ORDER-200",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

Trong ví dụ, **"sha256:<digest-of-canonical-business-payload>" chỉ là ký hiệu minh họa**, không phải mã băm có thể dùng trực tiếp.

Một phương án khác là lưu nguyên các **trường nghiệp vụ cần đối chiếu**: customerId, currency, amountCents, line items đã chuẩn hóa... và so sánh chúng khi requestId xuất hiện lần nữa.

### 7.2. Canonical payload là gì?

Hash cùng nội dung nghiệp vụ phải ra cùng kết quả dù JSON khác thứ tự key hoặc cách định dạng. Ví dụ:

~~~json
{"currency":"VND","amountCents":250000}
~~~

và:

~~~json
{"amountCents":250000,"currency":"VND"}
~~~

có cùng dữ liệu nghiệp vụ, nhưng chuỗi JSON thô khác nhau. Nếu hash byte thô không có quy tắc canonicalization, có thể báo “xung đột payload” giả.

Nên định nghĩa rõ:

1. Những field nào thực sự quyết định ý định nghiệp vụ.
2. Cách chuẩn hóa thứ tự key/array có hoặc không có ngữ nghĩa thứ tự.
3. Cách biểu diễn số tiền: **số nguyên ở đơn vị nhỏ nhất** hoặc decimal chuẩn, tránh float tùy ý.
4. Cách biểu diễn timestamp, timezone, null và trường bị thiếu.
5. Phiên bản định dạng canonicalization khi thay đổi schema.

Một fingerprint thường bao gồm cả **operationType** và những trường quan trọng. Trong hệ thống nhạy cảm, nên tránh đưa secret vào log; hashing không tự biến payload chứa dữ liệu nhạy cảm thành dữ liệu công khai tuyệt đối.

### 7.3. Bảng xử lý khi requestId đã tồn tại

| Khóa | Fingerprint | Trạng thái cũ | Cách phản hồi hợp lý |
|---|---|---|---|
| Chưa có | Không áp dụng | Không áp dụng | Thử giành quyền xử lý lần đầu |
| Đã có | Giống | COMPLETED | Trả kết quả đã ghi nhận, không làm lại |
| Đã có | Giống | PROCESSING | Báo đang xử lý/chờ hoặc cho client kiểm tra sau |
| Đã có | Khác | Bất kỳ | **409 Conflict** hoặc lỗi tương đương theo hợp đồng |
| Đã có | Giống | FAILED | Theo chính sách retry, không tự tạo hiệu ứng mới nếu trạng thái chưa xác định |

Ví dụ API có thể trả:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "code": "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
  "message": "Request ID đã được dùng với nội dung khác."
}
~~~

Chọn HTTP status theo hợp đồng API; ví dụ trên minh họa lựa chọn phổ biến, không phải quy tắc bắt buộc của MongoDB.

### 7.4. Nếu payload trùng nhưng user khác?

Nếu hệ thống nhiều người dùng, cần kiểm tra quyền **truy cập kết quả gốc**. Không nên cho một client chỉ vì đoán được requestId mà đọc thông tin đơn hàng của người khác. Trạng thái và response lấy lại phải được giới hạn bởi tenant, principal hoặc phạm vi ủy quyền thích hợp.

**Idempotency key không phải authorization token.**

## 8. Tách request registry ra khỏi bản ghi nghiệp vụ

Trong trường hợp một request có nhiều bước, có thể dùng một collection chuyên ghi nhận mã đã tiếp nhận:

~~~javascript
db.requestResults.createIndex(
  {
    tenantId: 1,
    operationType: 1,
    requestId: 1
  },
  {
    unique: true,
    name: "uq_request_results"
  }
);
~~~

Document mẫu:

~~~javascript
{
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-300",
  fingerprint: "sha256:<fingerprint-placeholder>",
  state: "PROCESSING",
  resourceId: null,
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

Request registry giúp tách **trạng thái yêu cầu** khỏi trạng thái nghiệp vụ của order/payment:

| Registry state | Ý nghĩa |
|---|---|
| PROCESSING | Yêu cầu đã được tiếp nhận, chưa kết luận hiệu ứng nghiệp vụ cuối cùng |
| COMPLETED | Kết quả đã được ghi nhận để trả lại cho retry |
| FAILED_RETRYABLE | Có lỗi có thể xử lý lại theo chính sách và điều kiện an toàn |
| FAILED_FINAL | Yêu cầu thất bại dứt điểm, trả lại lỗi đã ghi nhận hoặc theo API |
| UNKNOWN | Trạng thái tác động bên ngoài chưa được xác minh; cần đối soát |

**Những trạng thái trên là thiết kế ứng dụng, không phải enum có sẵn của MongoDB.** Có thể dùng tên khác, nhưng ý nghĩa và chuyển trạng thái phải được định nghĩa rõ.

### 8.1. Giành quyền xử lý bằng insert nguyên tử

Giả sử mỗi worker muốn xử lý cùng request R-300:

~~~javascript
db.requestResults.insertOne({
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-300",
  fingerprint: "fp-v1-R300",
  state: "PROCESSING",
  createdAt: new Date(),
  updatedAt: new Date()
});
~~~

Worker insert thành công là worker **giành được quyền khởi tạo** bản ghi request. Worker khác có cùng khóa sẽ gặp duplicate key. Nó không nên chạy lại logic nghiệp vụ khi chưa đọc trạng thái và xác định quyền xử lý.

### 8.2. Đọc lại khi gặp duplicate

~~~javascript
db.requestResults.findOne({
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-300"
});
~~~

Nếu state = PROCESSING, API có thể trả **202 Accepted** kèm resource để theo dõi; nếu COMPLETED, trả resourceId hoặc response đã lưu; nếu fingerprint khác, trả lỗi xung đột.

Với hệ thống có nhiều replica, lưu ý rằng **write concern/read concern và read preference** ảnh hưởng đến thời điểm nhìn thấy kết quả vừa ghi. Khi đọc lại sau duplicate hoặc kết quả ghi mơ hồ, nên thiết kế mức nhất quán phù hợp; đừng mặc định một secondary đọc trễ sẽ ngay lập tức hiển thị request vừa được primary chấp nhận.

### 8.3. Registry không tự hoàn tất nghiệp vụ

Một worker có thể insert state PROCESSING rồi bị tắt trước khi tạo order. Nếu API cứ thấy PROCESSING và không bao giờ có cơ chế xử lý tiếp, request sẽ kẹt vĩnh viễn. Ngược lại, nếu mọi request thấy PROCESSING đều lập tức xử lý lại, nhiều worker lại chạy trùng.

Đây là lý do hệ thống dài hạn cần **retry/recovery, lease hoặc job scheduler**, không chỉ một unique index và một cột state.

## 9. Atomic conditional update trên một document

MongoDB bảo đảm **một thao tác cập nhật document đơn lẻ là nguyên tử**. Có thể tận dụng filter chứa trạng thái hiện tại để thực hiện chuyển trạng thái có điều kiện.

Ví dụ worker đã nắm quyền xử lý R-300 và hoàn thành thành công:

~~~javascript
db.requestResults.updateOne(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-300",
    state: "PROCESSING"
  },
  {
    $set: {
      state: "COMPLETED",
      resourceId: "ORDER-300",
      updatedAt: new Date(),
      completedAt: new Date()
    }
  }
);
~~~

Filter **state: "PROCESSING"** yêu cầu bản ghi vẫn ở trạng thái được phép hoàn tất. Nếu một tiến trình khác đã chuyển sang trạng thái khác, **matchedCount = 0**, và worker cần đối soát thay vì ghi đè.

### 9.1. Không dùng ghi đè trạng thái vô điều kiện

Một thao tác rủi ro:

~~~javascript
db.requestResults.updateOne(
  { requestId: "R-300" },
  { $set: { state: "COMPLETED" } }
);
~~~

Vì filter thiếu tenant/operation và không kiểm tra trạng thái hiện tại, nó có thể cập nhật sai request hoặc đè lên thay đổi của worker khác.

Khi thiết kế state machine, filter nên bao gồm **khóa định danh đầy đủ** và **điều kiện trạng thái/phiên bản** cần thiết cho transition.

### 9.2. Kiểm tra kết quả cập nhật

~~~javascript
const result = db.requestResults.updateOne(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-300",
    state: "PROCESSING"
  },
  {
    $set: {
      state: "COMPLETED",
      resourceId: "ORDER-300",
      updatedAt: new Date()
    }
  }
);

printjson({
  matchedCount: result.matchedCount,
  modifiedCount: result.modifiedCount
});
~~~

Nếu **matchedCount = 0**, không thể khẳng định document đã được cập nhật. Một request khác, một recovery worker hoặc một transition trước đó có thể đã thay đổi trạng thái.

Nếu có nhiều owner cạnh tranh, chỉ kiểm tra state có thể chưa đủ. Cần so thêm **ownerToken/leaseVersion** để worker cũ không được hoàn tất thay worker mới sau khi lease bị tiếp quản; xem phần về lease và fencing token.

## 10. Một request ghi nhiều document: unique index chưa đủ

Giả sử tạo đơn hàng cần:

1. Ghi một bản ghi **requestResults**.
2. Tạo document **orders**.
3. Ghi document **inventoryReservations** để giữ hàng.

Nếu ba thao tác thực hiện riêng lẻ:

~~~text
insert requestResults  -> thành công
insert orders          -> thành công
insert reservations    -> lỗi mạng hoặc lỗi validation
~~~

MongoDB không tự rollback hai document đầu chỉ vì document thứ ba ghi thất bại. Tính nguyên tử của một thao tác trên một document **không mở rộng thành một transaction nhiều collection**.

Trong tình huống cần cả ba ghi cùng thành công hoặc cùng không hiển thị, sử dụng **multi-document transaction** khi deployment hỗ trợ và thiết kế dữ liệu cần mức bảo đảm đó.

### 10.1. Gộp các ghi có liên quan trong transaction

Ví dụ mongosh trên MongoDB triển khai hỗ trợ transaction (thường là replica set hoặc sharded cluster phù hợp):

~~~javascript
// Chuẩn bị unique index trước khi thử transaction.
db.requestResults.createIndex(
  { tenantId: 1, operationType: 1, requestId: 1 },
  { unique: true }
);

db.orders.createIndex(
  { tenantId: 1, clientRequestId: 1 },
  { unique: true }
);
~~~

Giả sử hai collection không chứa request R-400. Trong mongosh:

~~~javascript
const session = db.getMongo().startSession();
const sessionDb = session.getDatabase("idempotency_lab");

try {
  await session.withTransaction(async () => {
    const requestId = "R-400";
    const tenantId = "T-A";

    sessionDb.requestResults.insertOne({
      tenantId,
      operationType: "CREATE_ORDER",
      requestId,
      fingerprint: "fp-v1-R400",
      state: "COMPLETED",
      resourceId: "ORDER-400",
      createdAt: new Date()
    });

    sessionDb.orders.insertOne({
      _id: "ORDER-400",
      tenantId,
      clientRequestId: requestId,
      customerId: "C-201",
      amountCents: 100000,
      currency: "VND",
      status: "CREATED",
      createdAt: new Date()
    });
  });
} finally {
  await session.endSession();
}
~~~

Đây là ví dụ **ghi request record và order trong cùng transaction**. Việc thực thi callback/transaction có thể được driver retry theo nhãn lỗi và chính sách của API. **Không đưa gửi email, gọi cổng thanh toán hoặc tác vụ ngoại hệ vào callback được retry**: callback có thể chạy lại, khiến side effect bị lặp.

Lưu ý về môi trường:

- Transaction nhiều document yêu cầu deployment MongoDB và phiên bản/feature tương thích; không áp dụng như một giao dịch nhiều collection trên mọi standalone mongod.
- Phải xác định write concern, thời gian transaction, tài nguyên và giới hạn vận hành.
- Unique index là cơ chế chặn request trùng; transaction là cơ chế gộp các ghi có liên quan. **Hai cơ chế giải quyết hai bài toán khác nhau**.

### 10.2. Hai transaction cạnh tranh cùng requestId

Giả sử A và B cùng cố insert một request R-400 trong transaction. Cơ chế unique constraint và kiểm soát đồng thời của MongoDB sẽ không cho cả hai transaction commit thành công hai document cùng khóa unique. Một transaction có thể gặp **duplicate key**, **write conflict** hoặc một lỗi transaction cần xử lý theo nhãn tùy tình huống.

Ứng dụng không được coi **mọi lỗi transaction đều là “request chưa hề được thực hiện”**. Đặc biệt, một lỗi mạng khi commit có thể khiến kết quả commit mơ hồ, cần đọc lại bằng requestId để xác minh.

### 10.3. Lưu response nghiệp vụ cùng transaction

Nếu client cần lấy lại kết quả đầu tiên, document idempotency có thể giữ:

~~~javascript
{
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-400",
  fingerprint: "fp-v1-R400",
  state: "COMPLETED",
  response: {
    orderId: "ORDER-400",
    status: "CREATED"
  },
  completedAt: ISODate("2026-11-14T09:00:00Z")
}
~~~

Nếu response có dữ liệu nhạy cảm hoặc quá lớn, chỉ lưu thông tin đủ để **tái dựng response theo quyền truy cập hiện tại**. Việc lưu snapshot phản hồi đầu tiên so với trả trạng thái hiện tại của đơn là lựa chọn hợp đồng API cần được định nghĩa.

### 10.4. Transaction không bảo đảm side effect bên ngoài

MongoDB transaction chỉ bao gồm những thao tác dữ liệu thuộc phạm vi transaction được MongoDB hỗ trợ. Ví dụ:

~~~text
Transaction MongoDB
  insert order
  insert requestResult
  commit

Sau đó gọi Payment Provider
~~~

Nếu ứng dụng commit rồi crash trước khi gọi Payment Provider, order đã tồn tại nhưng thanh toán chưa thực hiện. Nếu gọi Payment Provider trước rồi commit MongoDB thất bại, tiền có thể đã bị trừ mà MongoDB chưa ghi nhận.

Không thể biến một API thanh toán bên ngoài thành thao tác nguyên tử của MongoDB bằng cách đặt lời gọi HTTP giữa hai câu lệnh trong transaction.

## 11. Xử lý kết quả mơ hồ khi mạng bị ngắt

Một tình huống khó là **lệnh ghi đã tới server và có thể thành công, nhưng client không nhận được phản hồi**:

~~~text
Client                         MongoDB
  |                               |
  |--- insert request R-500 ----->|
  |                               | Ghi dữ liệu
  |<---------- X -----------------|
  |      Mất phản hồi             |
  |                               |
  |  Client không biết ghi        |
  |  đã thành công hay chưa       |
~~~

Không được tự kết luận **“timeout nghĩa là database không ghi gì”**. Đây chính là một động lực thiết kế idempotency.

### 11.1. Kịch bản retry an toàn

Giả sử insert request có unique key. Khi client/backend retry cùng mã:

- Nếu bản ghi cũ đã commit và nhìn thấy, unique index ngăn bản ghi thứ hai; ứng dụng tìm bản ghi gốc và phản hồi.
- Nếu lần trước chưa ghi, lần retry có thể tạo bản ghi đầu tiên.
- Nếu lần trước vẫn đang chạy hoặc commit chưa rõ, thao tác mới có thể gặp lỗi cạnh tranh; ứng dụng cần retry có giới hạn và tra cứu trạng thái.

Ứng dụng phải **xem dữ liệu bền vững đã ghi theo mã nghiệp vụ** là nguồn đối soát, không tự dựa vào ký ức của một process vừa timeout.

### 11.2. Retryable writes không thay thế idempotency key

MongoDB Driver hỗ trợ **retryable writes** trong những deployment phù hợp. Cơ chế này sử dụng thông tin session/transaction number của driver để thực hiện lại một số lệnh ghi trong điều kiện được hỗ trợ mà không lặp hiệu ứng của chính lệnh đã nhận diện.

Nhưng hai điều khác nhau:

| Retryable writes của driver | Idempotency nghiệp vụ |
|---|---|
| Liên quan một lệnh ghi và ngữ cảnh retry/session của driver | Liên quan một **ý định nghiệp vụ** kéo qua HTTP, worker, process hoặc hệ thống |
| Hữu ích khi lỗi mạng tạm thời ở thao tác được hỗ trợ | Hữu ích khi người dùng nhấn lại, gateway retry, message giao lại |
| Không tự biết hai request ứng dụng khác nhau là cùng một đơn hàng | Dùng requestId chung để nhận diện yêu cầu trùng |
| Không bảo vệ lệnh gọi dịch vụ ngoài sau khi ghi | Cần kết hợp downstream idempotency/outbox |

Ví dụ hai request HTTP khác nhau có thể tạo hai MongoDB session và hai thao tác insert khác nhau. Dù driver bật retryable writes, MongoDB không tự biết đó là cùng ý định nếu **ứng dụng không đưa vào một khóa nghiệp vụ ổn định**.

### 11.3. Chọn mức bền vững dữ liệu

Với yêu cầu quan trọng như thanh toán hoặc đơn hàng, cần xem xét **write concern** và khả năng failover. Một ghi được xác nhận ở mức chưa đủ bền vững có thể gặp trường hợp rollback sau khi primary thay đổi trong những tình huống phù hợp.

Ví dụ áp dụng write concern majority trên collection khi cần:

~~~javascript
db.getCollection("orders").insertOne(
  {
    _id: "ORDER-501",
    tenantId: "T-A",
    clientRequestId: "R-501",
    status: "CREATED"
  },
  { writeConcern: { w: "majority" } }
);
~~~

Các mức write concern cần được chọn theo deployment, cấu hình majority, latency và yêu cầu độ bền của ứng dụng. **Majority không có nghĩa mọi workflow đa dịch vụ đã đạt exactly once**, nhưng giúp xây nền tảng bền vững hơn cho việc xác nhận một ghi trong MongoDB.

Khi đọc lại sau timeout hoặc failover, cần cân nhắc read preference/read concern và sự nhất quán mong muốn. Một secondary có độ trễ có thể chưa phản ánh ngay ghi vừa được xác nhận ở primary.

## 12. Khi có thanh toán, email hoặc message: dùng outbox và downstream idempotency

Giả sử đơn hàng phải kích hoạt thanh toán:

~~~text
API tạo đơn
    |
    v
MongoDB: order + requestResult
    |
    v
Payment Provider: charge(amount)
~~~

Nếu backend gọi cổng thanh toán trực tiếp trong request và timeout, có thể không biết tiền đã bị trừ hay chưa. Nếu retry charge không có khóa, khách hàng có thể bị trừ tiền hai lần dù MongoDB chỉ có một order.

### 12.1. Transactional outbox

Một mô hình thường dùng:

1. Trong một MongoDB transaction, ghi **order**, **requestResult** và **outbox event** cần phát.
2. Commit transaction để ba bản ghi xuất hiện nhất quán.
3. Worker đọc outbox, gửi lệnh/sự kiện sang hệ thống khác.
4. Worker ghi nhận trạng thái gửi hoặc kết quả; nếu crash, có thể gửi lại.
5. Hệ thống nhận phải chống trùng bằng **eventId/operationId** hoặc có cơ chế idempotency riêng.

~~~text
                 MongoDB transaction
          +--------------------------------+
Request ->| Order + RequestResult + Outbox |
          +--------------------------------+
                          |
                        commit
                          |
                          v
                     Outbox worker
                          |
                gửi với operationId
                          |
                          v
                  Payment / Email / Broker
                    (dedupe cùng ID)
~~~

Outbox giúp tránh lỗi “order đã commit nhưng sự kiện không được tạo để gửi”, với điều kiện order và outbox được ghi trong cùng transaction. Nó **không tự làm quá trình giao sự kiện trở thành đúng một lần**: worker có thể gửi lại sau lỗi và downstream cần dedupe/idempotency.

### 12.2. Cùng một khóa qua các lớp

Ví dụ định danh:

~~~text
Request:      (tenantId=T-A, requestId=R-600)
Order:        ORDER-600
Outbox event: EVENT-600-CHARGE
Payment op:   CHARGE-ORDER-600
~~~

**Payment op** phải ổn định khi worker retry cùng hành động charge. Nếu gateway hỗ trợ idempotency key, hãy gửi cùng khóa **CHARGE-ORDER-600** cho các lần thử lại của chính lệnh thanh toán đó.

Không nên dùng một khóa duy nhất một cách mù quáng cho **những thao tác khác nhau** như charge, refund, capture hoặc send-email nếu nhà cung cấp định nghĩa scope/retention khác nhau. Mỗi hiệu ứng phải có một định danh duy nhất đúng phạm vi.

### 12.3. Khi downstream không hỗ trợ idempotency

Nếu một dịch vụ ngoài không cho tra cứu bằng operationId và cũng không hỗ trợ khóa chống trùng, hệ thống khó bảo đảm chính xác một hiệu ứng trong mọi trường hợp mạng mất phản hồi. Có thể cần:

- Quy trình **đối soát** với hệ thống ngoài.
- Trạng thái **UNKNOWN/NEEDS_REVIEW** thay vì tự retry vô hạn.
- Một cơ chế inbox/outbox ở phía downstream nếu có thể thay đổi kiến trúc.
- Thao tác **bù trừ (compensation)** cho một số loại nghiệp vụ.

Không nên tuyên bố MongoDB unique index đã “giải quyết trùng thanh toán” nếu cổng thanh toán thực tế có thể nhận lệnh trùng từ worker.

### 12.4. MongoDB transaction chỉ là một phần của luồng

Một ví dụ document outbox:

~~~javascript
{
  _id: "EVT-ORDER-600-CHARGE",
  tenantId: "T-A",
  requestId: "R-600",
  resourceId: "ORDER-600",
  eventType: "PAYMENT_CHARGE_REQUESTED",
  operationId: "CHARGE-ORDER-600",
  state: "PENDING",
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
~~~

Nên đảm bảo eventId/operationId có tính duy nhất bằng index hoặc quy tắc _id phù hợp. Khi worker xử lý lại một event, nó phải dùng **đúng operationId đã lưu**, không tạo một mã charge mới khiến downstream coi như thao tác khác.

## 13. Worker xử lý lâu: lease và fencing token

Một request hoặc event có thể cần hàng phút để xử lý. Nếu worker A chết, hệ thống muốn worker B tiếp quản. Nhưng nếu A chỉ bị chậm rồi trở lại, có thể **cả A và B cùng chạy**, tạo nguy cơ ghi kết quả trùng.

Một mô hình thường dùng là **lease** — quyền xử lý tạm thời có thời hạn:

~~~javascript
{
  tenantId: "T-A",
  requestId: "R-700",
  state: "PROCESSING",
  ownerId: "worker-A",
  leaseUntil: ISODate("2026-11-14T10:05:00Z"),
  leaseVersion: 3
}
~~~

Các field:

- **ownerId**: worker đang được giao quyền.
- **leaseUntil**: hạn xử lý tạm thời.
- **leaseVersion**: phiên bản quyền sở hữu tăng lên khi có worker khác tiếp quản.

### 13.1. Nhận lease bằng thao tác có điều kiện

Khi thời hạn đã hết, worker khác có thể cố giành quyền bằng **findOneAndUpdate**:

~~~javascript
const now = new Date();
const leaseUntil = new Date(now.getTime() + 60_000);

const claimed = db.requestResults.findOneAndUpdate(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-700",
    state: "PROCESSING",
    leaseUntil: { $lte: now }
  },
  {
    $set: {
      ownerId: "worker-B",
      leaseUntil,
      updatedAt: now
    },
    $inc: { leaseVersion: 1 }
  },
  { returnDocument: "after" }
);
~~~

Vì cập nhật một document là nguyên tử, nếu nhiều worker tranh nhau giành cùng lease từ trạng thái đã hết hạn, chỉ worker có cập nhật filter thành công tại thời điểm đó mới có thể coi mình đã nhận quyền.

**Đừng coi chỉ việc đọc leaseUntil đã hết hạn là đã sở hữu job**; phải kiểm tra kết quả của thao tác cập nhật có điều kiện. Ngoài ra, hệ thống cần kiểm tra thời gian server/client, quyền xử lý và giới hạn TTL theo nghiệp vụ.

### 13.2. Fencing token ngăn worker cũ ghi đè

Sau khi worker B nhận leaseVersion = 4, worker A vẫn có thể trở lại với thông tin cũ leaseVersion = 3. Khi hoàn tất, mỗi worker phải đưa **phiên bản quyền** vào filter:

~~~javascript
db.requestResults.updateOne(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-700",
    state: "PROCESSING",
    ownerId: "worker-B",
    leaseVersion: 4
  },
  {
    $set: {
      state: "COMPLETED",
      resourceId: "ORDER-700",
      updatedAt: new Date()
    }
  }
);
~~~

Khi worker A cố hoàn tất với leaseVersion 3, nó không còn khớp document đã được B tiếp quản. Đây là cách dùng **compare-and-set** dựa trên trạng thái và phiên bản.

### 13.3. Giới hạn rất quan trọng của lease

Lease và fencing token ở MongoDB **chỉ bảo vệ những cập nhật có kiểm tra token ở nơi bạn kiểm soát**. Nếu worker A sau khi mất quyền vẫn gọi một API thanh toán bên ngoài không kiểm tra fencing token/idempotency, nó vẫn có thể tạo side effect.

Để bảo vệ end-to-end:

- Downstream cần hỗ trợ idempotency hoặc từ chối token phiên bản cũ nếu kiến trúc cho phép.
- Worker phải kiểm tra quyền hiện tại trước và sau những bước nhạy cảm, nhưng kiểm tra riêng lẻ không thể loại hoàn toàn race với side effect bên ngoài.
- Cần quy trình đối soát khi trạng thái ngoài không chắc chắn.

Với tác vụ chỉ sửa một document MongoDB, có thể đơn giản hơn nhiều: dùng một cập nhật nguyên tử có điều kiện thay vì thiết kế lease phức tạp.

### 13.4. Không hồi sinh FAILED một cách tùy tiện

Giả sử request R-700 ở state FAILED_FINAL vì card bị từ chối. Nếu một worker tự reset nó sang PROCESSING chỉ vì có retry, hệ thống có thể làm lại hành động mà hợp đồng xác định là thất bại dứt điểm.

Một state machine hợp lý cần phân biệt:

~~~text
NEW -> PROCESSING -> COMPLETED
            |
            +------> FAILED_RETRYABLE -> PROCESSING (khi đủ điều kiện)
            |
            +------> FAILED_FINAL
            |
            +------> UNKNOWN -> RECONCILIATION -> ...
~~~

Transition nào được phép phải được thiết kế theo nghiệp vụ và thực hiện bằng thao tác cập nhật có điều kiện. **Không phải mọi lỗi 5xx, timeout hoặc worker crash đều có thể chuyển trực tiếp thành FAILED_RETRYABLE** nếu một side effect bên ngoài có thể đã xảy ra.

## 14. TTL và thời hạn lưu khóa chống trùng

Collection requestResults có thể lớn dần theo số yêu cầu. MongoDB hỗ trợ **TTL index** để tự xóa document khi tới thời điểm hết hạn được chỉ định.

Ví dụ mỗi request có field **expiresAt**:

~~~javascript
db.requestResults.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_request_expiration"
  }
);
~~~

Document:

~~~javascript
{
  tenantId: "T-A",
  operationType: "CREATE_ORDER",
  requestId: "R-800",
  state: "COMPLETED",
  resourceId: "ORDER-800",
  createdAt: ISODate("2026-11-14T10:00:00Z"),
  expiresAt: ISODate("2026-12-14T10:00:00Z")
}
~~~

TTL index kiểm soát vòng đời lưu trữ của document theo thời điểm, nhưng có những giới hạn rất quan trọng:

1. **TTL deletion không chính xác đến từng mili giây.** Một tiến trình nền của server xóa document đủ điều kiện, nên bản ghi có thể tồn tại thêm sau expiresAt.
2. **Khi document đã bị xóa, unique index không còn khóa đó.** Một requestId cũ có thể được chấp nhận lại.
3. **TTL không tự dừng worker** đang dùng một document như trạng thái khóa.
4. TTL index là cơ chế xóa dữ liệu, **không bảo đảm lưu đủ lâu cho yêu cầu audit/pháp lý**.
5. Một unique index nhiều field và một TTL index trên expiresAt là **hai index khác nhau**; TTL không phải unique constraint.

### 14.1. Rủi ro replay sau khi khóa hết hạn

~~~text
Ngày 1: requestId=R-800 -> charge thành công
Ngày 2: client timeout/retry -> dedupe, không charge lần nữa
Ngày 31: TTL xóa requestResult
Ngày 40: requestId=R-800 xuất hiện lại
~~~

Nếu chỉ dựa trên requestResult và không còn thông tin nghiệp vụ khác, backend có thể hiểu lần ngày 40 là yêu cầu mới và phát sinh side effect trùng.

Muốn dùng TTL an toàn, cần **hợp đồng retention window rõ ràng** và các biện pháp bổ sung khi có khả năng yêu cầu cũ xuất hiện lại, ví dụ:

- Khóa nghiệp vụ vĩnh viễn hoặc dài hạn trên order/paymentInstruction.
- Cơ chế chống trùng riêng tại downstream.
- Lưu sổ cái hoặc lịch sử tối thiểu theo chính sách.
- Quy tắc từ chối request quá cũ dựa trên mã/sự kiện có thời hạn rõ.

**Không nên xóa bản ghi chống trùng quan trọng chỉ vì muốn giảm số document**, nếu nghiệp vụ cần ngăn phát lại trong thời gian dài hơn TTL.

### 14.2. Chọn retention theo loại thao tác

| Tình huống | Hướng retention |
|---|---|
| API tạo bản xem trước không có side effect | Có thể đặt thời hạn ngắn theo hợp đồng |
| Tạo đơn hàng | Thường cần unique business reference lâu dài hoặc gắn vào order |
| Thanh toán, hoàn tiền | Cần phối hợp lưu dấu theo sổ cái, đối tác và quy định lưu trữ |
| Event đồng bộ có thể phát lại sau nhiều tuần | Giữ eventId theo ít nhất thời gian replay thực tế, có phương án reprocessing |
| Request registry chỉ lưu response tạm thời | Có thể TTL response registry nếu uniqueness của hiệu ứng được bảo vệ ở nơi khác |

Không có một TTL chung tối ưu cho mọi nghiệp vụ. Phải phân biệt **thời hạn lưu response để trả lại client** và **thời hạn cần bảo vệ một hiệu ứng nghiệp vụ khỏi được thực hiện lần hai**.

## 15. Null, missing và unique index không thay schema validation

Một document thiếu requestId không nên được xem là “requestId rỗng hợp lệ”. Tuy nhiên, MongoDB index có những quy tắc xử lý giá trị null và field thiếu trong khóa. Trong một unique compound index, các tổ hợp giá trị khóa (bao gồm phần thiếu/null theo ngữ nghĩa index) vẫn có thể tạo xung đột.

Ví dụ index:

~~~javascript
{ tenantId: 1, clientRequestId: 1 }
~~~

**không tự bắt buộc** mọi order phải có tenantId và clientRequestId. Nếu ứng dụng được phép ghi document thiếu requestId, hệ thống có thể vừa chứa dữ liệu khó chống trùng vừa gặp các xung đột index ngoài dự kiến.

### 15.1. Bắt buộc field bằng $jsonSchema

Với collection mới:

~~~javascript
db.createCollection("strictRequests", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "operationType",
        "requestId",
        "fingerprint",
        "state"
      ],
      properties: {
        tenantId: {
          bsonType: "string",
          minLength: 1
        },
        operationType: {
          bsonType: "string",
          minLength: 1
        },
        requestId: {
          bsonType: "string",
          minLength: 1
        },
        fingerprint: {
          bsonType: "string",
          minLength: 1
        },
        state: {
          enum: [
            "PROCESSING",
            "COMPLETED",
            "FAILED_RETRYABLE",
            "FAILED_FINAL",
            "UNKNOWN"
          ]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

db.strictRequests.createIndex(
  { tenantId: 1, operationType: 1, requestId: 1 },
  { unique: true }
);
~~~

Schema validation giúp chặn record thiếu hoặc sai kiểu, còn unique index chặn trùng **giá trị khóa**. Cả hai đều cần thiết nếu hợp đồng yêu cầu mã không null, không rỗng, luôn là String.

### 15.2. Partial unique index có thể tạo lỗ hổng chống trùng

Giả sử chỉ đánh unique cho state = PROCESSING:

~~~javascript
db.requestResults.createIndex(
  { tenantId: 1, requestId: 1 },
  {
    unique: true,
    partialFilterExpression: {
      state: "PROCESSING"
    }
  }
);
~~~

Khi request chuyển sang **COMPLETED**, document không còn thuộc tập index partial. Điều đó có thể cho phép insert một document mới state PROCESSING với cùng khóa, gây nguy cơ thực hiện lại một yêu cầu đã hoàn tất.

**Nếu mục tiêu là ngăn cùng mã trong toàn bộ vòng đời**, unique index cần bảo vệ **mọi trạng thái liên quan**, không chỉ trạng thái đang chạy. Partial index chỉ nên dùng khi có quy tắc nghiệp vụ rõ về những document được và không được tham gia uniqueness.

### 15.3. Không đưa state vào unique key khi muốn mã dùng một lần

Index này thường **không phù hợp** cho idempotency theo request:

~~~javascript
db.requestResults.createIndex(
  {
    tenantId: 1,
    requestId: 1,
    state: 1
  },
  { unique: true }
);
~~~

Nó cho phép tồn tại **cùng tenantId/requestId** trong các trạng thái khác nhau, chẳng hạn một bản ghi PROCESSING và một bản ghi COMPLETED. Nếu mục tiêu là chỉ có **một bản ghi cho mỗi mã**, state không được là thành phần cho phép phân biệt các bản ghi ấy.

Index phù hợp hơn với hợp đồng đó:

~~~javascript
{ tenantId: 1, requestId: 1 }
~~~

hoặc thêm operationType nếu định nghĩa phạm vi cho phép.

## 16. Kiến trúc sharded và phạm vi unique

Khi collection được **shard**, khả năng cưỡng chế uniqueness phụ thuộc cấu hình shard key và các quy tắc unique index của MongoDB. Với sharded collection, unique index thông thường cần đáp ứng những ràng buộc về **shard key prefix** trong các tình huống được hỗ trợ.

Ví dụ nếu yêu cầu idempotency được định nghĩa theo:

~~~text
(tenantId, operationType, requestId)
~~~

thì thiết kế shard key và unique index phải được lựa chọn đồng bộ. Không được mặc định có thể tạo mọi unique compound index tùy ý trên các shard mà vẫn có một constraint toàn cục đúng như mong muốn.

### 16.1. Các câu hỏi khi dùng sharding

1. **Shard key** có bao gồm những field dùng định danh request không?
2. Unique index đề xuất có **prefix shard key** theo ràng buộc của phiên bản/kiểu sharding không?
3. Bộ lọc tìm request có đủ shard key để **target một shard** hay bị scatter-gather?
4. Tenant có phân bố rất lệch khiến một shard quá nóng không?
5. RequestId được tạo ở đâu và có thể trùng giữa những producer không?

Nếu hệ thống cần deduplication toàn cục nhưng shard key không hỗ trợ constraint đó, cần điều chỉnh mô hình hoặc dùng một registry có phương án uniqueness được MongoDB bảo đảm, thay vì tin vào kiểm tra trùng ứng dụng trên từng shard.

### 16.2. Không dùng ObjectId mặc định thay cho mã nghiệp vụ

MongoDB tạo _id riêng cho từng document; hai lần insert khác nhau thường nhận hai _id khác nhau. Điều đó **không ngăn** hai order có cùng requestId nếu requestId không bị ràng buộc unique.

Trong một số thiết kế có thể dùng một _id dẫn xuất ổn định từ requestId và scope, nhưng phải bảo đảm mã hóa không nhập nhằng, không xung đột và phù hợp shard key. Unique compound index thường rõ nghĩa hơn cho phạm vi tenant/operation.

## 17. Một nghiệp vụ trùng nhưng requestId khác: giới hạn cần biết

Giả sử khách hàng gửi:

~~~text
Request A: requestId=R-901, orderRef=SHOP-10001
Request B: requestId=R-902, orderRef=SHOP-10001
~~~

Nếu chỉ có unique index trên requestId, MongoDB sẽ coi đây là **hai request khác nhau**. Nhưng nghiệp vụ có thể quy định **orderRef=SHOP-10001 chỉ được tạo một lần**.

Do đó, có thể cần một **unique business constraint độc lập**:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderRef: 1 },
  {
    unique: true,
    name: "uq_tenant_order_reference"
  }
);
~~~

Phân biệt:

- **requestId** bảo vệ retry của cùng hành động do client gửi.
- **orderRef/invoiceNumber/paymentInstructionId** bảo vệ bất biến nghiệp vụ ngay cả khi client gửi mã request mới.

Một hệ thống tin cậy thường cần **cả hai** nếu hai loại trùng lặp đều nguy hiểm.

### 17.1. Không coi toàn bộ request giống payload là trùng nghiệp vụ

Khách hàng có thể cố tình mua cùng sản phẩm hai lần trong hai ngày, hoặc chuyển cùng một số tiền hai lần. Hai request có payload giống nhau nhưng **requestId khác nhau** không nhất thiết là duplicate.

Không nên chỉ hash payload rồi cấm mọi lần xuất hiện hash trùng, vì có thể chặn giao dịch hợp lệ. Mã nghiệp vụ cần phản ánh **một ý định cụ thể**, không phải chỉ trùng nội dung.

## 18. Mô hình nguyên tử trong một document để ghi nhận side effect

Trong một số bài toán, tất cả trạng thái cần bảo vệ có thể nằm ở **cùng một document**. Khi đó có thể cập nhật điều kiện và dữ liệu trong một lệnh thay vì dùng transaction nhiều collection.

Ví dụ, document hàng tồn kho:

~~~javascript
db.inventory.insertOne({
  _id: "SKU-100",
  available: 10,
  appliedRequestIds: []
});
~~~

Một lệnh giữ một đơn vị hàng, chống thực hiện hai lần cùng requestId:

~~~javascript
db.inventory.updateOne(
  {
    _id: "SKU-100",
    available: { $gte: 1 },
    appliedRequestIds: { $ne: "R-1000" }
  },
  {
    $inc: { available: -1 },
    $addToSet: { appliedRequestIds: "R-1000" }
  }
);
~~~

Filter và update được đánh giá nguyên tử trên **một document**. Khi hai worker cùng giữ SKU-100 cho request R-1000, chỉ một lần cập nhật có thể giảm available và thêm mã request, vì lần sau không còn thỏa điều kiện **appliedRequestIds: {$ne: "R-1000"}**.

### 18.1. Đọc kết quả matchedCount

Nếu matchedCount = 1, đã có một cập nhật hợp lệ. Nếu matchedCount = 0, có ít nhất ba khả năng:

- Kho không đủ số lượng.
- Mã request đã được áp dụng.
- SKU không tồn tại.

Không nên mặc định matchedCount = 0 luôn có nghĩa “không còn hàng”. Cần đọc trạng thái hiện tại và phân biệt nguyên nhân khi trả kết quả API.

### 18.2. Tại sao không lưu requestId vô hạn trong array?

Ví dụ **appliedRequestIds** chỉ phù hợp khi mỗi document có số lần xử lý ít và giới hạn đã được biết. Nếu một SKU nhận hàng triệu yêu cầu, array sẽ tăng không giới hạn, gây áp lực bộ nhớ và kích thước document (MongoDB có giới hạn kích thước BSON document).

Với hệ thống lớn, thường tốt hơn là lưu mỗi reservation thành **một document riêng có unique business key** và dùng transaction cho cập nhật số lượng tồn + reservation nếu cần nguyên tử xuyên document. Ví dụ array trong một document minh họa **tính nguyên tử**, không phải thiết kế tồn kho hoàn chỉnh cho mọi workload.

### 18.3. Kiểm tra quyền và trường hợp thay đổi trạng thái

Khi một reservation bị hủy, ứng dụng phải biết cách hoàn kho đúng một lần. Nếu chỉ xóa requestId khỏi array mà không có history trạng thái, việc hủy rồi retry giữ hàng có thể trở nên mơ hồ.

Hệ thống thực tế cần mô hình riêng cho CREATE/CONFIRM/CANCEL với mã operation hoặc reservationId nhất quán và ràng buộc unique phù hợp; một field requestId không thể thay thế toàn bộ state machine.

## 19. MongoDB Java Sync Driver: insert idempotent bằng unique index

Với ứng dụng Java dùng **mongodb-driver-sync**, một cách rõ ràng là:

1. Collection orders đã có unique index **{tenantId:1, clientRequestId:1}**.
2. Thử **insertOne** document mới.
3. Nếu thành công, trả document vừa tạo.
4. Nếu gặp **duplicate key 11000**, tìm order theo đúng khóa.
5. So sánh các trường nghiệp vụ bất biến; giống thì trả order gốc, khác thì trả lỗi conflict.
6. Không lặp lại tạo đơn hoặc gọi downstream ở nhánh duplicate.

### 19.1. Ví dụ Java hoàn chỉnh

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Date;
import java.util.Objects;

public class IdempotentOrderInsert {
    static Document createOrGet(
            MongoCollection<Document> orders,
            String tenantId,
            String requestId,
            String customerId,
            long amountCents,
            String currency) {

        Bson requestKey = Filters.and(
                Filters.eq("tenantId", tenantId),
                Filters.eq("clientRequestId", requestId)
        );

        Document candidate = new Document("tenantId", tenantId)
                .append("clientRequestId", requestId)
                .append("customerId", customerId)
                .append("amountCents", amountCents)
                .append("currency", currency)
                .append("status", "CREATED")
                .append("createdAt", new Date());

        try {
            orders.insertOne(candidate);
            return candidate;
        } catch (MongoWriteException ex) {
            if (ex.getError().getCode() != 11000) {
                throw ex;
            }

            // Chỉ coi duplicate là retry khi tìm đúng khóa nghiệp vụ.
            Document existing = orders.find(requestKey).first();
            if (existing == null) {
                // Có thể duplicate đến từ constraint khác hoặc
                // chưa thể quan sát bản ghi cần tìm.
                throw ex;
            }

            boolean samePayload =
                    Objects.equals(existing.getString("customerId"), customerId)
                    && Objects.equals(
                            existing.getLong("amountCents"), amountCents)
                    && Objects.equals(existing.getString("currency"), currency);

            if (!samePayload) {
                throw new IllegalStateException(
                        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD");
            }

            return existing;
        }
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("idempotency_lab")
                    .getCollection("orders")
                    .withWriteConcern(WriteConcern.MAJORITY);

            Document first = createOrGet(
                    orders, "T-JAVA", "R-JAVA-001",
                    "C-301", 250000L, "VND");

            Document retry = createOrGet(
                    orders, "T-JAVA", "R-JAVA-001",
                    "C-301", 250000L, "VND");

            System.out.println(first.toJson());
            System.out.println(retry.toJson());
        }
    }
}
~~~

Với **unique index đã tạo thành công**, hai lời gọi cùng khóa và payload sẽ tham chiếu đến **một order**. Ví dụ lưu amountCents là **Long**; không dùng double để tính tiền nếu đơn vị tiền tệ và quy tắc làm tròn cần chính xác.

**Quan trọng:** code này minh họa luồng insert thành công và trường hợp **duplicate key**. Một ngoại lệ mạng sau insert có thể là **kết quả ghi mơ hồ** chứ không nhất thiết là MongoWriteException 11000. Ở lớp API/job thực, cần thêm chính sách retry/đọc lại theo requestId, timeout có giới hạn và write/read concern phù hợp như phần 11.

### 19.2. Vì sao so sánh payload trong nhánh duplicate?

Nếu requestId R-JAVA-001 được gửi lại với amountCents = 999999L, unique index ngăn insert mới. Nhưng chỉ trả order cũ mà không báo xung đột có thể làm caller hiểu sai rằng số tiền mới đã được chấp nhận.

Điều kiện samePayload bảo đảm caller gửi lại **cùng ý định về các trường mà ví dụ coi là bất biến**. Trong ứng dụng thật, danh sách trường phải bao phủ đầy đủ nội dung nghiệp vụ: line items, product option, customerId, currency, giá trị, địa chỉ giao hàng nếu những field đó quyết định kết quả.

### 19.3. Tạo index trong Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

public class OrderIndexes {
    public static void ensureUniqueRequestIndex(
            MongoCollection<Document> orders) {

        orders.createIndex(
                Indexes.compoundIndex(
                        Indexes.ascending("tenantId"),
                        Indexes.ascending("clientRequestId")
                ),
                new IndexOptions()
                        .unique(true)
                        .name("uq_orders_tenant_request")
        );
    }
}
~~~

Đoạn này chỉ minh họa API tạo index. Không gọi nó bên trong **mỗi request**; hãy quản lý index qua bootstrap/migration đã được duyệt. Tạo unique index trên collection có duplicate sẵn có thể thất bại và cần xử lý dữ liệu lịch sử.

### 19.4. Xử lý lỗi duplicate đúng loại

Không phải mọi **MongoException** đều là duplicate key:

- Lỗi xác thực/quyền: không thể giả định request đã tồn tại.
- Timeout/network: kết quả có thể mơ hồ, cần đối soát.
- Lỗi validation: payload hoặc schema không hợp lệ.
- Duplicate key 11000: có một unique constraint bị vi phạm; vẫn phải xác minh **khóa nào** gây trùng.

Trong thực tế có nhiều unique index, code không nên bắt mọi lỗi 11000 rồi trả kết quả cho requestId hiện tại một cách mù quáng. Việc tìm được bản ghi đúng khóa và đối chiếu payload là điều kiện cần trước khi coi đó là retry thành công.

## 20. Spring Data MongoDB: bắt DuplicateKeyException

Trong dự án Spring Boot/Spring Data MongoDB, **MongoTemplate** có thể insert document và phát sinh **DuplicateKeyException** khi unique index bị vi phạm.

### 20.1. Entity có compound index

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
@CompoundIndex(
        name = "uq_orders_tenant_request",
        def = "{'tenantId': 1, 'clientRequestId': 1}",
        unique = true
)
public class OrderRecord {
    @Id
    private String id;
    private String tenantId;
    private String clientRequestId;
    private String customerId;
    private long amountCents;
    private String currency;
    private String status;

    // Constructor, getters, setters được bổ sung theo dự án.
}
~~~

Annotation mô tả index muốn có. **MongoDB phải thực sự có index trước khi xử lý request cạnh tranh**. Việc Spring Data có tự tạo index từ annotation lúc startup hay không phụ thuộc cấu hình và phiên bản; trong production, thường cần migration quản lý rõ ràng.

### 20.2. Service xử lý insert và duplicate

Ví dụ minh họa với entity có getters/setters:

~~~java
import java.util.Objects;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderCreationService {
    private final MongoTemplate mongoTemplate;

    public OrderCreationService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public OrderRecord createOrRead(OrderRecord candidate) {
        try {
            return mongoTemplate.insert(candidate);
        } catch (DuplicateKeyException duplicate) {
            Query query = Query.query(
                    Criteria.where("tenantId")
                            .is(candidate.getTenantId())
                            .and("clientRequestId")
                            .is(candidate.getClientRequestId())
            );

            OrderRecord existing = mongoTemplate.findOne(
                    query, OrderRecord.class);

            if (existing == null) {
                throw duplicate;
            }

            boolean samePayload =
                    Objects.equals(
                            existing.getCustomerId(),
                            candidate.getCustomerId())
                    && existing.getAmountCents() == candidate.getAmountCents()
                    && Objects.equals(
                            existing.getCurrency(),
                            candidate.getCurrency());

            if (!samePayload) {
                throw new IllegalStateException(
                        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD");
            }

            return existing;
        }
    }
}
~~~

Trong HTTP controller, lỗi payload khác có thể được ánh xạ sang **409 Conflict**. Khi tìm thấy request đã hoàn tất, response cần chứa đúng resourceId/orderId hiện hữu; không tự tạo id mới để phản hồi.

Đoạn code giả định collection chỉ tạo một order document ở thao tác này. Nếu còn phải giữ hàng, ghi thanh toán và phát event, cần áp dụng transaction/outbox hoặc mô hình phù hợp thay vì coi một lệnh insert là đủ.

### 20.3. Cẩn thận với catch rộng

Một cách làm sai:

~~~java
try {
    mongoTemplate.insert(candidate);
} catch (Exception ex) {
    return mongoTemplate.findOne(
            Query.query(Criteria.where("clientRequestId")
                    .is(candidate.getClientRequestId())),
            OrderRecord.class);
}
~~~

Nó bắt cả lỗi mạng, lỗi quyền, lỗi mapping và validation rồi coi tất cả là duplicate, lại **không giới hạn tenantId**. Điều này vừa che giấu lỗi thật vừa có nguy cơ trả nhầm dữ liệu của tenant khác.

Hãy phân loại lỗi, kiểm tra khóa đầy đủ, xác thực quyền và chỉ trả lại kết quả cũ khi điều kiện idempotency đã được chứng minh.

## 21. Quản lý trạng thái HTTP/API cho retry

Idempotency là một hợp đồng giữa client và server. Một quy ước minh họa:

| Tình huống | Hành động server | HTTP có thể dùng |
|---|---|---|
| RequestId lần đầu, xử lý đồng bộ thành công | Ghi kết quả, trả orderId | 201 Created |
| Retry cùng requestId/payload, kết quả đã có | Trả lại kết quả theo hợp đồng | 200 OK hoặc response đã lưu |
| Retry khi request còn PROCESSING | Không chạy nghiệp vụ lần hai; thông báo đang xử lý | 202 Accepted kèm resource theo dõi |
| Retry cùng mã nhưng payload khác | Từ chối | 409 Conflict |
| RequestId sai định dạng/thiếu bắt buộc | Từ chối trước khi ghi | 400 Bad Request |
| Lỗi nghiệp vụ xác định, không retry được | Trả kết quả lỗi đã được ghi nhận | Mã lỗi nghiệp vụ phù hợp |
| Trạng thái thanh toán UNKNOWN | Không tự charge lại; yêu cầu đối soát | 202/409/5xx tùy hợp đồng, cùng mã tra cứu |

**MongoDB không quyết định HTTP status**. Bảng là gợi ý thiết kế API; API cần có tài liệu về TTL, xử lý key trùng, trường hợp đang chạy và cách lấy lại kết quả.

### 21.1. Ví dụ response khi đang xử lý

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Retry-After: 3

{
  "requestId": "R-300",
  "state": "PROCESSING",
  "statusUrl": "/v1/requests/R-300"
}
~~~

Nếu có URL tra cứu trạng thái, endpoint đó phải kiểm tra tenant/user đã xác thực, tránh lộ kết quả chỉ nhờ biết requestId. Header Retry-After là gợi ý thời điểm gọi lại, không phải dấu hiệu worker chắc chắn hoàn tất sau đúng ba giây.

### 21.2. Trả kết quả cũ hay trạng thái hiện tại?

Giả sử order ban đầu là CREATED, sau đó đã được giao và chuyển thành SHIPPED. Khi retry yêu cầu tạo đơn cũ:

- **Replay response ban đầu:** trả orderId và trạng thái CREATED đã lưu.
- **Trả trạng thái hiện tại:** trả orderId giống cũ nhưng trạng thái SHIPPED.

Cả hai có thể idempotent về **hiệu ứng tạo đơn**, nhưng là hai hợp đồng API khác nhau. Cần chọn và ghi rõ, đặc biệt nếu client so sánh response hoặc tự retry dựa vào trạng thái.

## 22. Quan sát và vận hành cơ chế chống trùng

Một cơ chế idempotency tốt không chỉ ngăn trùng trong điều kiện bình thường, mà còn giúp xác định **request nào đang kẹt, request nào đã có kết quả và nguyên nhân nào gây retry nhiều lần**.

Những metric hữu ích:

| Metric | Mục đích |
|---|---|
| requests_first_seen | Số mã yêu cầu mới được tiếp nhận |
| requests_replayed_completed | Số lần retry lấy lại kết quả hoàn tất |
| requests_in_progress_conflict | Số lần retry khi request đang xử lý |
| requests_payload_conflict | Số lần cùng mã nhưng payload không giống |
| duplicate_key_count | Số xung đột unique index liên quan đến request |
| requests_unknown_state | Số yêu cầu chưa xác định hiệu ứng đã xảy ra hay chưa |
| stale_processing_count | Số PROCESSING quá hạn lease hoặc SLA |
| reconciliation_duration | Thời gian đối soát một yêu cầu trạng thái mơ hồ |
| outbox_redelivery_count | Số event được gửi lại sau lỗi |
| downstream_duplicate_suppressed | Số lệnh trùng bị downstream từ chối/khử |

Những tên metric là gợi ý đặt tên trong ứng dụng, **không phải các field metrics có sẵn trong MongoDB**.

### 22.1. Tìm request PROCESSING quá lâu

Ví dụ:

~~~javascript
const threshold = new Date(Date.now() - 15 * 60 * 1000);

db.requestResults.find({
  state: "PROCESSING",
  updatedAt: { $lt: threshold }
}).sort({ updatedAt: 1 });
~~~

Đây là cách tìm **ứng viên cần điều tra**, không phải giấy phép cho mọi worker chạy lại. Có request đang chờ một đối tác ngoài, nên có thể phải đối soát trước khi thử tiếp.

Nếu tập dữ liệu lớn, có thể cân nhắc index:

~~~javascript
db.requestResults.createIndex({
  state: 1,
  updatedAt: 1
});
~~~

Index này phục vụ truy vấn trạng thái/quá hạn, **không thay** unique compound index bảo vệ requestId.

### 22.2. Ghi log theo mã yêu cầu

Ví dụ một log có cấu trúc:

~~~text
traceId=tr-501
tenantId=T-A
operation=CREATE_ORDER
requestId=R-500
idempotencyOutcome=REPLAY_COMPLETED
orderId=ORDER-500
statusCode=200
~~~

Không log số thẻ, token, toàn bộ payload hoặc dữ liệu cá nhân không cần thiết. Một trace có thể gắn với nhiều lần retry của cùng requestId, nhưng traceId không phải luôn là idempotency key: traceId thường khác ở những request HTTP độc lập.

### 22.3. Giám sát unique index và thay đổi schema

Khi một bản triển khai mới bắt đầu yêu cầu requestId, cần bảo đảm:

- Index unique đã tồn tại trước khi mở traffic.
- Validator/logic ghi không còn cho phép document thiếu key.
- Các đường ghi khác (admin script, importer, batch) cũng tuân theo ràng buộc.
- Quá trình migrate dữ liệu cũ không làm thất bại index build.
- Hệ thống theo dõi số conflict và trạng thái kẹt sau triển khai.

Unique index là **rào chắn cuối ở database**; các lớp ứng dụng vẫn phải validate và cung cấp thông báo hợp lý cho caller.

## 23. Các tình huống cạnh tranh cần phân biệt

### 23.1. Hai request cùng key, cùng payload đến đúng một lúc

~~~text
              request R-100
                 /     \
              A           B
              |           |
          insertOne    insertOne
              |           |
           SUCCESS       E11000
              |           |
          order A       read order A
              |           |
            return      return original
~~~

**Kết quả đúng:** tối đa một order được tạo. Request bị E11000 chỉ trả kết quả gốc sau khi xác minh key và payload.

### 23.2. Cùng key nhưng khác payload

~~~text
Request A: key=R-100, amount=100000
Request B: key=R-100, amount=900000
~~~

**Kết quả đúng:** một request được ghi trước hợp lệ; request còn lại phải nhận xung đột, **không thể coi cả hai cùng thành công**.

### 23.3. Khác key nhưng cùng mã đơn nghiệp vụ

~~~text
Request A: requestId=R-100, orderRef=SHOP-1
Request B: requestId=R-101, orderRef=SHOP-1
~~~

Nếu orderRef là định danh duy nhất của nghiệp vụ, cần unique index riêng trên **(tenantId, orderRef)**. Nếu không, hai requestId hợp lệ khác nhau vẫn có thể tạo hai order trùng mã nguồn.

### 23.4. Request đã ghi nhưng response bị mất

Khi client timeout, lần retry phải **tra và tái sử dụng kết quả đã ghi**, không sinh requestId mới cho cùng hành động. Một write timeout không đủ chứng minh lần đầu chưa commit.

### 23.5. Worker A mất lease, worker B tiếp quản

Để ngăn worker A ghi đè kết quả B, cập nhật cuối phải có **leaseVersion** hoặc fencing token trong điều kiện. Side effect bên ngoài vẫn cần cơ chế idempotency riêng.

### 23.6. Registry bị TTL xóa trước một replay cũ

Không còn requestResult không đồng nghĩa hệ thống chưa từng thực hiện hành động. Cần xác định retention window và unique business record/ledger hoặc downstream operationId phù hợp.

## 24. Bài thực hành: tạo hai request cạnh tranh bằng mongosh

Chuẩn bị:

~~~javascript
use idempotency_lab

db.demoRequests.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uq_demo_request" }
);
~~~

Mở **hai phiên mongosh** cùng kết nối database thử nghiệm. Trên cả hai cửa sổ, gần như đồng thời chạy:

~~~javascript
db.demoRequests.insertOne({
  tenantId: "T-DEMO",
  requestId: "R-RACE-1",
  state: "COMPLETED",
  createdAt: new Date()
});
~~~

Một insert có thể thành công, insert còn lại có thể nhận **E11000 duplicate key**, tùy thứ tự server xử lý. Nếu đã có dữ liệu từ lần thử trước, cả hai lần chạy có thể bị duplicate; muốn thử lại với một ý định mới, dùng requestId khác.

Xác nhận số document:

~~~javascript
db.demoRequests.countDocuments({
  tenantId: "T-DEMO",
  requestId: "R-RACE-1"
});
~~~

Kết quả kỳ vọng là **1** khi có ít nhất một insert đã thành công. Đây là quan sát trực tiếp ràng buộc uniqueness, không phải bằng chứng mọi side effect trong hệ thống thanh toán đều được chống trùng.

### 24.1. Thử bỏ index sẽ có gì khác?

Trên một collection thử nghiệm **khác**, nếu không có unique index theo requestId, hai insert với hai _id tự sinh khác nhau có thể cùng tồn tại dù tenantId/requestId trùng nhau. Không thử **drop index trên collection sản xuất** để kiểm chứng giả thuyết.

### 24.2. Thử upsert và xem kết quả

~~~javascript
db.demoRequests.updateOne(
  {
    tenantId: "T-DEMO",
    requestId: "R-UPSERT-1"
  },
  {
    $setOnInsert: {
      state: "COMPLETED",
      resourceId: "RESOURCE-1",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

Chạy lại đúng câu lệnh, rồi xem document:

~~~javascript
db.demoRequests.findOne({
  tenantId: "T-DEMO",
  requestId: "R-UPSERT-1"
});
~~~

Phần $setOnInsert không ghi đè resourceId cũ trong lần retry. Nếu ứng dụng thật phải trả resourceId, nó cần **đọc giá trị đã được lưu**; không được tự sinh RESOURCE-2 rồi trả về trong lần retry.

### 24.3. Tránh nhầm biến mã request và mã tài nguyên

Một requestId đại diện cho **ý định tạo**, còn orderId/resourceId đại diện cho **kết quả đã tạo**. Chúng có thể trùng trong một số thiết kế, nhưng không bắt buộc. Giữ hai khái niệm tách biệt giúp API phản hồi idempotent:

~~~text
RequestId:  R-UPSERT-1
ResourceId: RESOURCE-1
~~~

Khi cùng requestId xuất hiện lại, server trả **RESOURCE-1** — không bắt đầu một quy trình tạo resource mới.

## 25. Bài tập vận dụng

Các bài tập dưới đây tập trung vào **tư duy cạnh tranh, tính nguyên tử và định danh nghiệp vụ**, không yêu cầu hệ thống thanh toán thật. Có thể thực hành với collection thử nghiệm đã tạo hoặc mô tả kết quả dự kiến.

### Bài 1. Hai worker cùng insert

Cho collection:

~~~javascript
db.payments.createIndex(
  { merchantId: 1, paymentInstructionId: 1 },
  { unique: true }
);
~~~

Worker A và B cùng insert paymentInstructionId = "P-101" của merchant "M-1", mỗi worker dùng _id khác nhau. Hãy trả lời:

1. Có thể cùng tồn tại hai document với cặp khóa đó không?
2. Nếu một insert nhận lỗi 11000, phải làm gì?
3. Có nên tự retry insert bằng requestId khác để “khắc phục lỗi” không?

**Đáp án định hướng:** Unique index ngăn hai document cùng cặp khóa. Request bị duplicate phải đọc và kiểm tra kết quả đã có, so payload/trạng thái, rồi trả kết quả phù hợp. Sinh requestId khác để retry cùng ý định có thể phá cơ chế chống trùng.

### Bài 2. Cùng mã nhưng số tiền khác

Giả sử request đầu:

~~~json
{
  "requestId": "R-2000",
  "amountCents": 120000,
  "currency": "VND"
}
~~~

Request sau:

~~~json
{
  "requestId": "R-2000",
  "amountCents": 900000,
  "currency": "VND"
}
~~~

Chọn phản hồi hợp lý và giải thích tại sao không thể chỉ trả kết quả cũ mà bỏ qua payload khác.

**Đáp án:** Một cơ chế điển hình trả **409 Conflict** với mã lỗi key reused with different payload. Khóa trùng không chứng minh cùng ý định khi dữ liệu bất biến khác nhau.

### Bài 3. Upsert có bảo đảm duy nhất nếu không có index?

Hai worker gọi đồng thời:

~~~javascript
db.orders.updateOne(
  { tenantId: "T-1", clientRequestId: "R-3000" },
  { $setOnInsert: { status: "CREATED" } },
  { upsert: true }
);
~~~

Collection chưa có unique index theo tenantId/clientRequestId. Hãy giải thích vì sao vẫn có nguy cơ hai insert trong race.

**Định hướng:** Hai worker có thể cùng quan sát chưa có document trước khi quyết định upsert. Cần constraint được MongoDB cưỡng chế bằng unique index; chỉ dùng upsert không thay ràng buộc duy nhất.

### Bài 4. Chọn key đúng phạm vi

Hệ thống đa tenant cho phép mỗi tenant cấp mã "REQ-1". Hãy chọn giữa:

~~~javascript
{ requestId: 1 }

{ tenantId: 1, requestId: 1 }
~~~

**Đáp án:** Nếu requestId chỉ duy nhất trong mỗi tenant, dùng **compound unique index (tenantId, requestId)**. TenantId lấy từ ngữ cảnh xác thực đáng tin cậy. Nếu nghiệp vụ yêu cầu requestId toàn cục, thiết kế khóa khác có thể phù hợp.

### Bài 5. Tại sao không đưa state vào khóa unique?

Cho index:

~~~javascript
{ tenantId: 1, requestId: 1, state: 1 }
~~~

với unique = true. Có thể insert hai document cùng tenantId/requestId nhưng một là PROCESSING và một là COMPLETED không?

**Đáp án:** Có thể, vì key ba trường khác nhau. Nếu chỉ được có một document cho requestId trong mọi trạng thái, không nên để state phân biệt uniqueness.

### Bài 6. Mất phản hồi sau khi ghi

Một lệnh insert trả timeout, nhưng sau đó tìm theo requestId thấy order đã ở state CREATED. Client retry cùng mã và payload. Backend cần làm gì?

**Định hướng:** Không tạo order mới. Xác minh đúng scope, payload và quyền truy cập rồi trả lại order gốc hoặc trạng thái đã lưu theo hợp đồng. Timeout không chứng minh lần đầu thất bại.

### Bài 7. Transaction và cổng thanh toán

Trong một transaction, backend insert order, rồi gọi HTTP charge, sau đó insert requestResult và commit. Nếu commit thất bại nhưng HTTP charge đã thành công thì sao?

**Định hướng:** MongoDB không rollback được charge ở hệ thống ngoài. Hãy đề xuất outbox, operationId/idempotency key tại payment provider và cơ chế đối soát. Không đặt side effect ngoài vào callback transaction có thể retry.

### Bài 8. LeaseVersion và worker cũ

Worker A có leaseVersion = 7. Do quá hạn, B tiếp quản và tăng leaseVersion lên 8. A quay lại và muốn ghi COMPLETED.

Viết filter update để A **không thể** thành công nếu document hiện là phiên bản 8.

~~~javascript
db.requestResults.updateOne(
  {
    tenantId: "T-A",
    operationType: "CREATE_ORDER",
    requestId: "R-7000",
    state: "PROCESSING",
    ownerId: "worker-A",
    leaseVersion: 7
  },
  {
    $set: {
      state: "COMPLETED",
      updatedAt: new Date()
    }
  }
);
~~~

Khi B đã cập nhật ownerId/leaseVersion, filter của A không khớp và matchedCount bằng 0. Cơ chế này chỉ chặn cập nhật MongoDB có kiểm tra token; không tự ngăn một HTTP call ngoài thiếu fencing/idempotency.

### Bài 9. TTL và replay sau một tháng

Một payment registry xóa document chống trùng sau bảy ngày, nhưng message broker có thể giao lại event cũ sau ba mươi ngày. Điều gì có thể xảy ra?

**Định hướng:** Event được giao lại sau khi document bị TTL xóa có thể bị coi như mới. Cần retention phù hợp với replay window hoặc dấu nghiệp vụ lâu dài (paymentInstructionId/ledger) và downstream idempotency. TTL không phải bảo đảm “chỉ xử lý một lần mãi mãi”.

### Bài 10. Duplicate business reference với requestId khác nhau

Hai request:

~~~text
R-1 -> orderRef=INV-2026-100
R-2 -> orderRef=INV-2026-100
~~~

Nếu hai requestId khác nhau và hệ thống chỉ có unique index trên requestId, điều gì xảy ra? Hãy thiết kế thêm một unique business index.

**Đáp án:** Hai request khác key có thể đều được chấp nhận. Nếu orderRef phải duy nhất theo tenant, thêm unique index **{tenantId:1, orderRef:1}**, kiểm tra trạng thái và quyết định cách xử lý xung đột nghiệp vụ.

### Bài 11. Bảo vệ kho bằng cập nhật một document

Cho:

~~~javascript
{
  _id: "SKU-1",
  available: 5,
  appliedRequestIds: ["REQ-A"]
}
~~~

Hãy viết update giữ một đơn vị hàng với requestId REQ-A. Filter gồm **available >= 1** và **appliedRequestIds != REQ-A**. Dự đoán matchedCount và available.

**Đáp án:** matchedCount = 0, available vẫn bằng 5 vì request đã có trong appliedRequestIds. Nếu đổi thành REQ-B, thao tác có thể giảm available xuống 4 và thêm REQ-B, giả sử không có request khác cạnh tranh và mọi điều kiện khác hợp lệ.

### Bài 12. Thiết kế endpoint có thể retry

Một API tạo đơn cần chịu được mất mạng, hai request đồng thời, payload xung đột và gửi thông báo đến hệ thống ngoài. Hãy phác thảo:

1. Quy tắc cấp requestId và phạm vi duy nhất.
2. Unique index trên request registry hoặc order.
3. Cách kiểm tra fingerprint/payload khi mã đã tồn tại.
4. Xử lý COMPLETED/PROCESSING/FAILED/UNKNOWN.
5. Cách ghi order + outbox nhất quán.
6. OperationId để downstream chống gửi trùng.
7. Retention và kế hoạch phục hồi.

Một câu trả lời đạt mục tiêu phải phân biệt **bảo vệ dữ liệu MongoDB** và **bảo vệ side effect ngoài MongoDB**, không chỉ nói “thêm unique index là xong”.

## 26. Chọn mô hình theo độ phức tạp nghiệp vụ

| Nhu cầu | Mô hình đề xuất để xem xét | Hạn chế cần nhớ |
|---|---|---|
| Một request chỉ insert một document | Unique business key + insertOne; xử lý duplicate | Không tự bảo vệ side effect ngoài |
| Muốn “tạo nếu chưa có” | Unique index + upsert $setOnInsert | Đọc lại/so payload khi đã tồn tại, xử lý race |
| Một request thay đổi một document | Conditional atomic update với requestId/state trong filter | Phải có chỗ lưu dấu đã áp dụng và kiểm soát kích thước |
| Một request ghi nhiều collection và cần cùng commit | Multi-document transaction + unique index | Không bao gồm HTTP call ngoài |
| Cần phát event sau commit dữ liệu | Transactional outbox + downstream dedupe | Event có thể được giao lại; cần operationId ổn định |
| Job lâu, worker có thể tiếp quản | Registry + lease + leaseVersion/fencing | Không tự chặn side effect ở hệ thống ngoài |
| Chỉ giữ response idempotency trong thời hạn hữu hạn | TTL index + hợp đồng retention window | Hết TTL có thể replay nếu không có dấu nghiệp vụ dài hạn |
| Chống nhiều request khác key cùng mã đơn | Unique business reference riêng | Không coi payload giống nhau là duplicate một cách mù quáng |
| Nhiều tenant/shard | Compound key theo scope, thiết kế cùng shard key | Phải kiểm tra quy tắc unique index trên sharded collection |

### 26.1. Sơ đồ quyết định đơn giản

~~~text
Có một ý định nghiệp vụ cần chống trùng?
                    |
                    v
       Xác định requestId + scope
                    |
                    v
      Tạo unique constraint ở MongoDB
                    |
                    v
       Tác vụ chỉ ghi một document?
              /             \
            Có              Không
            |                 |
     insert/upsert       Có cần nguyên tử
     + kiểm payload      giữa nhiều document?
                         /             \
                       Có              Không
                       |                 |
                  Transaction      Workflow/state machine
                       |                 |
                       +---------+-------+
                                 |
                                 v
                     Có side effect ngoài?
                          /       \
                        Có        Không
                        |           |
                 Outbox/operationId  Hoàn tất
                 + downstream dedupe
                        |
                        v
               Retry/recovery/đối soát
~~~

Sơ đồ nhằm giúp lựa chọn hướng thiết kế, không phải thay thế việc phân tích tính nhất quán, latency, quy định dữ liệu và khả năng của từng hệ thống.

## 27. Những lỗi thiết kế cần tránh

1. **Sinh requestId mới trên mỗi retry.** Khi đó hệ thống mất khả năng nhận diện cùng ý định.
2. **Chỉ dùng findOne rồi insertOne.** Hai worker đồng thời vẫn có thể insert trùng nếu không có unique index.
3. **Dùng state làm một phần khóa unique** dù muốn mỗi requestId có đúng một record trong mọi trạng thái.
4. **Dùng $set trong upsert để ghi lại payload ở mỗi retry.** Có thể ghi đè đơn gốc bằng dữ liệu mới.
5. **Coi mọi E11000 là retry hợp lệ.** Duplicate có thể đến từ constraint khác hoặc payload xung đột.
6. **Coi timeout là chưa ghi dữ liệu.** Ghi đã thành công vẫn có thể bị mất phản hồi.
7. **Coi retryable writes của driver là chống trùng nghiệp vụ.** Hai HTTP request vẫn là hai thao tác độc lập nếu ứng dụng không truyền mã chung.
8. **Gọi cổng thanh toán trong transaction và nghĩ rollback MongoDB sẽ hoàn tiền.** Side effect ngoài không thuộc phạm vi commit/rollback MongoDB.
9. **Để request PROCESSING mãi mãi sau worker crash.** Cần cơ chế phục hồi, lease và đối soát.
10. **Cho worker cũ hoàn tất sau khi mất lease.** Phải kiểm tra owner/leaseVersion trong cập nhật cuối.
11. **TTL xóa dấu chống trùng quá sớm.** Replay cũ có thể tạo hiệu ứng mới.
12. **Không kiểm tra quyền khi lấy lại response.** Biết requestId không đồng nghĩa có quyền xem kết quả.
13. **Dùng unique requestId khi nghiệp vụ còn yêu cầu unique orderRef.** Hai requestId khác nhau vẫn có thể vi phạm bất biến đơn hàng.
14. **Không giám sát request UNKNOWN/stale PROCESSING.** Cơ chế dedupe có thể ngăn trùng nhưng làm hệ thống kẹt mà không ai phát hiện.
15. **Bỏ qua chi phí index/transaction.** Một thiết kế chống trùng đúng về logic vẫn cần cân bằng hiệu năng và khả năng vận hành.

## 28. Kết luận

**Mã yêu cầu nghiệp vụ** là cách để nối những lần truyền lặp của **cùng một ý định** thành một hành động có thể kiểm soát. MongoDB giúp thực thi ràng buộc đó nhờ **unique index** và **tính nguyên tử trên một document**. Upsert, conditional update và transaction bổ sung những mức nhất quán khác nhau khi yêu cầu phức tạp hơn.

Nhưng để chống xử lý trùng thực sự, không thể chỉ tạo một index rồi dừng:

~~~text
Same business intent
       |
       v
Stable requestId + correct scope
       |
       v
Unique index (MongoDB-enforced)
       |
       v
Same payload? ---- No ----> Conflict
       |
      Yes
       |
       v
State: new / processing / completed / unknown
       |
       v
Atomic write or transaction as needed
       |
       v
Outbox + downstream operationId when needed
       |
       v
Durable result + safe retry + reconciliation
~~~

**Năm nguyên tắc cần nhớ:**

- Một ý định nghiệp vụ phải dùng **cùng requestId qua mọi lần retry**; một ý định mới phải có mã mới.
- **Unique compound index** là hàng rào chống race quan trọng; thao tác kiểm tra trước rồi ghi sau không đủ.
- **Cùng mã nhưng khác payload là xung đột**, không phải retry hợp lệ.
- **Ghi MongoDB thành công không đồng nghĩa side effect ngoài đã an toàn**; cần outbox, idempotency ở downstream hoặc đối soát.
- **Thời gian lưu khóa và khả năng phục hồi** phải bao phủ thực tế retry/replay; không được cho rằng TTL, lease hay driver retry tự mang lại exactly-once end-to-end.

Khi áp dụng các nguyên tắc này, hệ thống MongoDB có thể tiếp nhận request trùng, thao tác đồng thời và lỗi mạng mà vẫn giữ được bất biến nghiệp vụ: **một ý định hợp lệ tạo tối đa một hiệu ứng tương ứng trong phạm vi đã định nghĩa**, còn những trường hợp chưa chắc chắn được ghi nhận và xử lý có kiểm soát thay vì âm thầm tạo thêm dữ liệu.
