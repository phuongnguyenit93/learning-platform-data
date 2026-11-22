# Cấu trúc sự kiện và các trường định danh cần thiết

## 1. Sự kiện là một hợp đồng dữ liệu

Trong kiến trúc hướng sự kiện, producer công bố một điều đã xảy ra để các consumer có thể phản ứng độc lập. Ví dụ, sau khi đơn hàng được tạo, dịch vụ đơn hàng phát `OrderCreated`; dịch vụ kho có thể giữ hàng, dịch vụ phân tích cập nhật số liệu và dịch vụ thông báo gửi email. Các consumer có thể được triển khai bằng Java function và được kích hoạt qua queue hoặc event bus trong môi trường serverless.

Thông điệp sự kiện vì vậy là một hợp đồng giữa các thành phần. Hợp đồng cần trả lời được ít nhất bốn câu hỏi: sự kiện nào đã xảy ra, sự kiện đến từ đâu, nó liên quan đến đối tượng nghiệp vụ nào và consumer cần dữ liệu gì để xử lý. Nếu thiếu định danh hoặc ngữ cảnh, consumer khó chống xử lý trùng, truy vết quy trình và phân biệt sự kiện đến trễ. Nếu payload gắn chặt với cấu trúc cơ sở dữ liệu nội bộ, thay đổi của producer có thể phá vỡ nhiều consumer.

Một sự kiện tích hợp (integration event) tốt thường có các đặc điểm:

- Mô tả một sự thật đã xảy ra, thường dùng tên ở thì quá khứ như `OrderCreated` hoặc `PaymentAuthorized`.
- Có định danh ổn định cho chính sự kiện, không phụ thuộc vào lần giao nhận.
- Xác định được nguồn phát, loại sự kiện và đối tượng nghiệp vụ liên quan.
- Có thời điểm xảy ra và, khi cần, số phiên bản hoặc thứ tự trong phạm vi đối tượng.
- Mang đủ dữ liệu cho consumer theo hợp đồng đã thống nhất.
- Bất biến sau khi công bố; thay đổi nghiệp vụ được thể hiện bằng sự kiện mới.
- Có quy tắc phiên bản và tương thích để producer, consumer có thể triển khai độc lập.

Không nên xem mọi bản ghi trong cơ sở dữ liệu là một sự kiện tích hợp. `OrderCreated` diễn đạt một mốc nghiệp vụ; `orders_row_inserted` thường chỉ phản ánh chi tiết kỹ thuật. Consumer nên phụ thuộc vào ý nghĩa nghiệp vụ ổn định thay vì tên bảng, tên cột hoặc đối tượng ORM của producer.

## 2. Tách envelope, metadata và payload

Một cấu trúc dễ quản lý thường có ba lớp:

1. **Envelope (vỏ sự kiện):** các trường chung để nhận diện và định tuyến sự kiện, chẳng hạn ID, nguồn, loại và thời điểm.
2. **Metadata (ngữ cảnh):** các trường hỗ trợ liên kết quy trình, tenant, phiên bản aggregate hoặc truy vết.
3. **Payload (dữ liệu nghiệp vụ):** thông tin cụ thể của sự kiện, chẳng hạn mã đơn, khách hàng, mặt hàng và tổng tiền tại thời điểm đơn được tạo.

Ví dụ dạng JSON đơn giản:

```json
{
  "eventId": "01933c7e-7d8a-7a31-9a4d-2c4d9f40c101",
  "eventType": "com.example.order.created.v1",
  "source": "/commerce/orders",
  "subject": "orders/ORD-2048",
  "occurredAt": "2026-11-17T10:15:30Z",
  "schemaVersion": 1,
  "aggregate": {
    "id": "ORD-2048",
    "version": 1
  },
  "correlationId": "req-7f5a2d",
  "causationId": "cmd-4a91d0",
  "data": {
    "orderId": "ORD-2048",
    "customerId": "CUS-81",
    "currency": "VND",
    "totalAmount": 450000,
    "lines": [
      { "sku": "BOOK-01", "quantity": 2, "unitPrice": 225000 }
    ]
  }
}
```

Đây là một hợp đồng minh họa do ứng dụng định nghĩa, không phải cấu trúc bắt buộc của mọi nền tảng. Nếu các dịch vụ cần một định dạng chung, có thể sử dụng CloudEvents. Dù chọn định dạng nào, hãy giữ ý nghĩa của từng trường nhất quán và mô tả chúng trong schema hoặc tài liệu hợp đồng.

Envelope nên chứa thông tin chung cho nhiều loại sự kiện. Payload chỉ chứa dữ liệu của loại sự kiện cụ thể. Ví dụ, `eventId` thuộc envelope; `totalAmount` thuộc payload của `OrderCreated`. Không lặp lại các trường chung ở nhiều vị trí nếu không có lý do tương thích rõ ràng, vì hai giá trị có thể lệch nhau sau này.

## 3. CloudEvents: định dạng chung cho envelope

CloudEvents là đặc tả trung lập nền tảng để mô tả metadata của sự kiện. Nó giúp các dịch vụ dùng nhiều ngôn ngữ hoặc nhà cung cấp cloud trao đổi sự kiện với cùng cách hiểu về nguồn, loại và định danh. CloudEvents không quyết định nghiệp vụ nào cần phát sự kiện và cũng không thay thế schema cho payload.

Một CloudEvent phiên bản 1.0 ở dạng JSON có thể trông như sau:

```json
{
  "specversion": "1.0",
  "id": "01933c7e-7d8a-7a31-9a4d-2c4d9f40c101",
  "source": "/commerce/orders",
  "type": "com.example.order.created.v1",
  "subject": "orders/ORD-2048",
  "time": "2026-11-17T10:15:30Z",
  "datacontenttype": "application/json",
  "dataschema": "https://schemas.example.com/order-created/v1.json",
  "correlationid": "req-7f5a2d",
  "causationid": "cmd-4a91d0",
  "aggregateid": "ORD-2048",
  "aggregateversion": 1,
  "data": {
    "orderId": "ORD-2048",
    "customerId": "CUS-81",
    "currency": "VND",
    "totalAmount": 450000,
    "lines": [
      { "sku": "BOOK-01", "quantity": 2, "unitPrice": 225000 }
    ]
  }
}
```

Trong CloudEvents, bốn thuộc tính context cốt lõi là:

| Thuộc tính | Bắt buộc | Ý nghĩa |
|---|---:|---|
| `specversion` | Có | Phiên bản đặc tả CloudEvents dùng để diễn giải envelope, ví dụ `1.0` |
| `id` | Có | Định danh sự kiện trong phạm vi nguồn phát |
| `source` | Có | URI-reference xác định ngữ cảnh hoặc nguồn phát sự kiện |
| `type` | Có | Loại sự kiện, thường là tên có namespace và có thể gắn phiên bản |
| `subject` | Không | Đối tượng mà sự kiện nói đến trong phạm vi `source` |
| `time` | Không | Thời điểm sự kiện xảy ra |
| `datacontenttype` | Không | Kiểu nội dung của dữ liệu, ví dụ `application/json` |
| `dataschema` | Không | URI tham chiếu schema diễn giải dữ liệu |
| `data` | Không bắt buộc ở mọi event | Nội dung nghiệp vụ của sự kiện |

Các thuộc tính `correlationid`, `causationid`, `aggregateid` và `aggregateversion` trong ví dụ là extension attributes do ứng dụng quy ước. Tên extension của CloudEvents phải dùng chữ thường và chữ số. Các bên tham gia phải thống nhất kiểu dữ liệu và ý nghĩa của extension; chỉ thêm một thuộc tính vào JSON không có nghĩa mọi broker hoặc SDK tự hiểu nó.

`specversion` và phiên bản schema nghiệp vụ giải quyết hai vấn đề khác nhau. `specversion: "1.0"` nói consumer cách đọc định dạng CloudEvents. `type: "com.example.order.created.v1"` hoặc `dataschema` nói consumer đang nhận phiên bản hợp đồng `OrderCreated` nào. Nâng phiên bản payload không nhất thiết yêu cầu đổi phiên bản CloudEvents.

CloudEvents có thể được truyền ở structured mode, trong đó metadata và data nằm trong cùng nội dung JSON, hoặc binary mode, trong đó context attributes nằm ở metadata của giao thức còn payload nằm ở phần thân. Adapter của Java function cần biết trigger đang cung cấp mode nào và chuyển đổi về mô hình nội bộ nhất quán.

## 4. Các trường định danh: mỗi ID trả lời một câu hỏi

Không có một ID duy nhất giải quyết mọi nhu cầu. Một hệ thống cần phân biệt định danh sự kiện, đối tượng nghiệp vụ, quy trình, nguyên nhân và yêu cầu thao tác. Dùng nhầm một ID cho nhiều ý nghĩa có thể làm hỏng idempotency hoặc khiến việc truy vết sai lệch.

| Trường | Định danh điều gì? | Phạm vi thường gặp | Dùng để làm gì? |
|---|---|---|---|
| `eventId` | Một sự kiện cụ thể | Một lần phát sự kiện, ổn định qua các lần giao lại | Chống xử lý trùng, tra cứu và kiểm toán |
| `source` | Nguồn/ngữ cảnh phát sự kiện | Một dịch vụ, ứng dụng hoặc resource | Phân biệt các producer và namespace của ID |
| `aggregateId` | Đối tượng nghiệp vụ được thay đổi | Một đơn hàng, tài khoản hoặc subscription | Gom các sự kiện cùng một đối tượng, phân vùng và kiểm tra trạng thái |
| `aggregateVersion` | Phiên bản của đối tượng sau thay đổi | Tăng theo từng aggregate | Phát hiện sự kiện cũ, thiếu hoặc sai thứ tự |
| `correlationId` | Một quy trình hoặc yêu cầu đầu-cuối | Nhiều sự kiện và lời gọi liên quan | Tìm toàn bộ luồng nghiệp vụ |
| `causationId` | Thông điệp trực tiếp gây ra sự kiện hiện tại | Một bước cha trực tiếp | Dựng quan hệ nguyên nhân-kết quả |
| `idempotencyKey` | Một yêu cầu thao tác cần tránh thực hiện lặp | Một hành động nghiệp vụ hoặc API call | Bảo vệ thao tác ghi hoặc tác động bên ngoài |
| `tenantId` | Không gian dữ liệu của khách hàng/tenant | Một tenant | Phân vùng dữ liệu và áp dụng quyền truy cập |
| `traceId` | Một distributed trace | Một trace quan sát | Liên kết span qua các tiến trình và dịch vụ |

### 4.1. `eventId`: định danh chính sự kiện

`eventId` phải được tạo khi sự kiện được hình thành và giữ nguyên trong mọi lần retry, redelivery, chuyển queue hoặc replay của chính sự kiện đó. Nếu broker giao cùng một thông điệp ba lần, cả ba lần phải mang cùng định danh. Nếu producer tạo hai sự kiện nghiệp vụ khác nhau, chúng phải có định danh khác nhau dù payload có thể giống hệt.

Với CloudEvents, cặp `source` và `id` tạo định danh duy nhất cho một sự kiện trong ngữ cảnh nguồn. Nên tạo ID đủ duy nhất trên phạm vi hệ thống cần trao đổi; UUID ngẫu nhiên hoặc UUID có thứ tự thời gian là lựa chọn thường gặp. ID tăng dần từ cơ sở dữ liệu có thể tiết lộ lưu lượng và dễ va chạm khi nhiều producer cùng phát. Không dùng số lần thử, thời điểm nhận hoặc ID invocation làm `eventId` mới khi giao lại một sự kiện cũ.

Ví dụ sai: consumer timeout, producer tạo `eventId` mới cho lần gửi lại. Consumer không thể nhận ra hai thông điệp là cùng một sự kiện và có thể trừ tồn kho hoặc thu tiền hai lần. Ví dụ đúng: producer lưu ID cùng bản ghi outbox; relay gửi lại đúng bản ghi đó với cùng ID.

### 4.2. `aggregateId`: định danh đối tượng nghiệp vụ

Aggregate là ranh giới nhất quán trong mô hình miền. `aggregateId` xác định đối tượng mà sự kiện mô tả, chẳng hạn `ORD-2048`. Một đơn hàng có thể phát nhiều sự kiện: `OrderCreated`, `OrderAddressChanged`, `OrderConfirmed` và `OrderShipped`. Mỗi sự kiện có `eventId` riêng nhưng dùng chung `aggregateId`.

Không dùng `aggregateId` thay cho `eventId`: nhiều sự kiện của cùng đơn hàng không phải là một sự kiện. Cũng không nên đặt email hoặc số điện thoại khách hàng làm aggregate ID; ID nên ổn định, không chứa thông tin cá nhân và không thay đổi khi dữ liệu hiển thị thay đổi.

Trong một số mô hình, sự kiện liên quan đến nhiều đối tượng. Hãy xác định aggregate sở hữu thay đổi chính, sau đó đưa các ID liên quan cần thiết vào payload với tên rõ nghĩa như `customerId`, `paymentId` hoặc `shipmentId`. Đừng dùng một trường `id` mơ hồ cho nhiều thực thể.

### 4.3. `aggregateVersion`: thứ tự thay đổi trong phạm vi aggregate

`aggregateVersion` là số phiên bản tăng dần của aggregate sau mỗi thay đổi có ý nghĩa. Ví dụ một đơn hàng phát `OrderCreated` ở version 1, `OrderAddressChanged` ở version 2 và `OrderConfirmed` ở version 3. Consumer có thể dùng version để phát hiện thông điệp cũ, thiếu hoặc đến sai thứ tự.

Version không thay thế `eventId`. Hai aggregate khác nhau có thể cùng version 2; hai sự kiện khác nhau cũng có thể cùng thời điểm. Nếu một thao tác phát nhiều sự kiện cho cùng một lần commit, cần quy ước rõ version áp dụng cho trạng thái aggregate hay sequence riêng cho từng event. Có thể dùng `aggregateVersion` cộng `eventIndex`, hoặc một `eventSequence` tăng đơn điệu nếu consumer cần thứ tự duy nhất từng sự kiện.

Không lấy timestamp làm version. Đồng hồ giữa các máy có thể lệch, độ phân giải thời gian có thể không đủ và hai sự kiện có thể có cùng timestamp. Số phiên bản được cấp tại nơi sở hữu aggregate là cơ sở đáng tin cậy hơn cho kiểm tra thứ tự.

### 4.4. `correlationId` và `causationId`

`correlationId` liên kết nhiều thông điệp thuộc cùng một quy trình. Ví dụ yêu cầu tạo đơn có thể dẫn đến giữ hàng, thanh toán, xác nhận và gửi thông báo. Tất cả các bước có thể mang cùng `correlationId` để tìm toàn bộ hành trình của đơn.

`causationId` chỉ ra thông điệp trực tiếp đã gây ra sự kiện hiện tại. Khi `OrderCreated` dẫn đến `InventoryReserved`, trường `causationId` của `InventoryReserved` có thể bằng `eventId` của `OrderCreated`. Nếu sự kiện được phát do một command, giá trị có thể là ID của command đó. Quan hệ này tạo thành chuỗi nguyên nhân-kết quả.

Hai trường không thể thay thế nhau. Một quy trình có thể chứa hàng chục sự kiện cùng `correlationId`, nhưng mỗi sự kiện có `causationId` khác nhau. Khi consumer phát sự kiện mới, giữ `correlationId` của quy trình và đặt `causationId` thành ID của thông điệp đầu vào trực tiếp.

### 4.5. `idempotencyKey`: định danh yêu cầu thao tác

`idempotencyKey` không nhất thiết là ID của sự kiện. Nó xác định một ý định hoặc thao tác cần có hiệu lực tối đa một lần, chẳng hạn yêu cầu thu tiền cho đơn `ORD-2048`. Một thao tác có thể tạo ra nhiều sự kiện theo tiến trình, và một sự kiện có thể được phát bởi relay nhiều lần. Khóa idempotency thường được lưu cùng kết quả thao tác hoặc gửi đến API bên ngoài nếu nhà cung cấp hỗ trợ.

Ví dụ, khi gọi cổng thanh toán, dùng khóa ổn định như `authorize:ORD-2048:v1` cho mọi lần retry cùng yêu cầu. Nếu người dùng chủ động thử thanh toán lại sau khi đổi phương thức, đó có thể là một thao tác mới với khóa khác. Không tạo khóa mới ngẫu nhiên cho mỗi lần retry, vì như vậy mất tác dụng chống trùng.

### 4.6. `tenantId`: định danh ranh giới khách hàng

Trong hệ thống đa tenant, `tenantId` xác định không gian dữ liệu và chính sách của khách hàng tổ chức. Consumer cần kiểm tra tenant trước khi đọc hoặc cập nhật tài nguyên. Không tin mù quáng `tenantId` do payload bên ngoài tự khai báo; producer phải lấy tenant từ ngữ cảnh đã xác thực và consumer phải áp dụng quyền truy cập tương ứng.

Nếu hệ thống chỉ phục vụ một tenant, không cần thêm trường chỉ để cho đủ mẫu. Nếu có tenant, hãy xác định tenant là CloudEvents extension, thuộc payload hay được truyền ở metadata giao thức, và giữ cùng một quy ước ở mọi producer/consumer. Không dùng `tenantId` thay cho `customerId`: một tenant có thể chứa nhiều khách hàng hoặc người dùng.

### 4.7. `traceId` và `traceparent`

Distributed tracing giúp nối các span qua API gateway, function, queue và dịch vụ bên ngoài. `traceparent` theo W3C Trace Context mang ngữ cảnh trace và parent span; đây là metadata phục vụ quan sát. `correlationId` thường mang ý nghĩa nghiệp vụ và có thể tồn tại lâu hơn trace kỹ thuật.

Một quy trình nghiệp vụ dài có thể vượt thời hạn của một trace hoặc được tiếp tục sau nhiều giờ. Vì vậy, không dựa duy nhất vào `traceId` để định danh quy trình nghiệp vụ. Có thể truyền cả correlation ID và trace context, đồng thời tuân theo cách nền tảng nối trace qua thông điệp bất đồng bộ.

## 5. Trường thời gian: xảy ra, phát đi, nhận và xử lý

Một thông điệp có thể đi qua nhiều hàng đợi trước khi consumer xử lý. Chỉ có một trường `timestamp` sẽ khiến mọi người khó biết nó biểu thị mốc nào. Hãy đặt tên rõ ràng:

| Trường | Ý nghĩa | Ai thường ghi? |
|---|---|---|
| `occurredAt` hoặc CloudEvents `time` | Thời điểm thay đổi nghiệp vụ thực sự xảy ra | Producer nghiệp vụ |
| `publishedAt` | Thời điểm sự kiện được đưa lên broker hoặc công bố ra ngoài | Outbox relay hoặc publisher |
| `receivedAt` | Thời điểm consumer hoặc adapter nhận thông điệp | Hệ thống nhận |
| `processedAt` | Thời điểm consumer hoàn tất xử lý | Consumer |

Các mốc này giúp đo độ trễ: `publishedAt - occurredAt` phản ánh thời gian chờ phát; `processedAt - publishedAt` phản ánh độ trễ giao nhận và xử lý, nếu các đồng hồ được đồng bộ đủ tốt. Không đưa `receivedAt`, `processedAt` vào payload bất biến do producer phát; đó là metadata riêng của từng lần giao nhận hoặc xử lý.

Nên dùng thời gian UTC theo ISO 8601, ví dụ `2026-11-17T10:15:30Z`, và kiểu thời gian có timezone trong Java như `Instant`. Không lưu chuỗi giờ địa phương không kèm múi giờ. Thời gian giúp phân tích và hiển thị nhưng không nên là căn cứ duy nhất để sắp xếp sự kiện. Khi thứ tự nghiệp vụ quan trọng, dùng version hoặc sequence do aggregate sở hữu.

## 6. Payload nên chứa những gì?

Payload cần đủ để consumer thực hiện trách nhiệm của mình mà không tạo phụ thuộc không cần thiết. Có hai cách thiết kế phổ biến:

- **Event mang dữ liệu tại thời điểm xảy ra:** payload chứa snapshot các thuộc tính consumer cần. Ví dụ `OrderCreated` chứa mã đơn, loại tiền, tổng tiền và các dòng hàng tại thời điểm tạo. Consumer có thể xử lý ngay cả khi đơn hàng đã thay đổi sau đó.
- **Event mang tham chiếu:** payload chứa ID và consumer gọi API của dịch vụ sở hữu dữ liệu để lấy trạng thái hiện tại. Cách này giảm kích thước thông điệp nhưng tạo phụ thuộc vào API, quyền truy cập và thời điểm đọc.

Chọn dựa trên ngữ nghĩa. Nếu consumer cần xử lý chính xác sự thật ở thời điểm phát, hãy đưa snapshot cần thiết hoặc tham chiếu bất biến có phiên bản. Nếu consumer chỉ cần trạng thái mới nhất, đọc API có thể hợp lý. Không phát một ID rồi kỳ vọng consumer có thể truy cập trực tiếp cơ sở dữ liệu của producer.

Các nguyên tắc thiết kế payload:

- Dùng tên trường có nghĩa và nhất quán, ví dụ `totalAmount` thay vì `value`.
- Quy định kiểu dữ liệu, đơn vị đo, quy tắc làm tròn và giá trị null.
- Với tiền, truyền cả `currency` và số tiền theo đơn vị nhỏ nhất hoặc kiểu decimal có quy ước rõ; không để consumer tự đoán đơn vị.
- Với số lượng, quy định đơn vị như `piece`, `kg` hoặc `liter` nếu nghiệp vụ có nhiều loại đo.
- Dùng mảng khi thứ tự có ý nghĩa; nếu thứ tự không quan trọng, consumer không nên phụ thuộc vào vị trí phần tử.
- Tránh nhúng toàn bộ đối tượng lớn hoặc lồng nhiều cấp không cần thiết.
- Không chứa mật khẩu, access token, dữ liệu thẻ thanh toán hoặc thông tin cá nhân mà consumer không cần.
- Không thêm trạng thái giao nhận như `retryCount` vào sự kiện nghiệp vụ bất biến; số lần thử thuộc metadata vận chuyển hoặc log của consumer.

Không dùng payload để gửi một đối tượng ORM hoặc bản sao nguyên trạng của bảng. Hãy tạo DTO sự kiện riêng. Điều này giúp producer giữ quyền thay đổi mô hình lưu trữ mà không làm thay đổi hợp đồng tích hợp.

## 7. Ví dụ một chuỗi sự kiện cho đơn hàng

Giả sử đơn hàng `ORD-2048` được tạo, giữ hàng và xác nhận. Ba sự kiện có thể dùng chung aggregate ID nhưng có event ID và version riêng:

| Trường | `OrderCreated` | `InventoryReserved` | `OrderConfirmed` |
|---|---|---|---|
| `eventId` | `evt-a1` | `evt-b2` | `evt-c3` |
| `type` | `order.created.v1` | `inventory.reserved.v1` | `order.confirmed.v1` |
| `aggregateId` | `ORD-2048` (Order) | `RES-9901` (Reservation) | `ORD-2048` (Order) |
| `aggregateVersion` | 1 (Order) | 1 (Reservation) | 2 (Order) |
| `correlationId` | `flow-77` | `flow-77` | `flow-77` |
| `causationId` | `cmd-91` | `evt-a1` | `evt-b2` |

Trong ví dụ này, `InventoryReserved` do dịch vụ kho phát và thuộc aggregate `Reservation` riêng. Payload của nó có thể chứa `orderId: ORD-2048` để liên kết với đơn hàng. `aggregateId` và `aggregateVersion` vẫn mô tả dữ liệu do dịch vụ kho sở hữu. Không gán version của Reservation vào aggregate Order chỉ vì hai sự kiện cùng nằm trong một quy trình.

Một cách rõ ràng hơn khi sự kiện của dịch vụ khác tác động đến đơn hàng là giữ `reservationId` trong payload, `orderId` là đối tượng liên quan, còn `aggregateId` xác định aggregate mà producer sở hữu. Tên trường phải phản ánh đúng ranh giới dữ liệu, không chỉ phản ánh quy trình tổng thể.

## 8. Ánh xạ cấu trúc sự kiện sang Java

Trong Java, có thể biểu diễn metadata và payload bằng `record` bất biến. Ví dụ dưới đây là mô hình ứng dụng độc lập với adapter cụ thể của AWS Lambda, Azure Functions hoặc một nền tảng FaaS khác:

```java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public record EventMetadata(
        String eventId,
        String source,
        String type,
        String subject,
        Instant occurredAt,
        String correlationId,
        String causationId,
        String aggregateId,
        long aggregateVersion,
        String tenantId) {

    public EventMetadata {
        Objects.requireNonNull(eventId, "eventId is required");
        Objects.requireNonNull(source, "source is required");
        Objects.requireNonNull(type, "type is required");
        Objects.requireNonNull(occurredAt, "occurredAt is required");
        if (aggregateVersion < 0) {
            throw new IllegalArgumentException("aggregateVersion must be non-negative");
        }
    }
}

public record OrderLine(
        String sku,
        int quantity,
        long unitPriceMinor) {}

public record OrderCreatedData(
        String orderId,
        String customerId,
        String currency,
        long totalAmountMinor,
        List<OrderLine> lines) {

    public OrderCreatedData {
        Objects.requireNonNull(orderId, "orderId is required");
        Objects.requireNonNull(currency, "currency is required");
        lines = List.copyOf(lines);
    }
}

public record IntegrationEvent<T>(EventMetadata metadata, T data) {
    public IntegrationEvent {
        Objects.requireNonNull(metadata, "metadata is required");
        Objects.requireNonNull(data, "data is required");
    }
}
```

Ở ví dụ này, `totalAmountMinor` và `unitPriceMinor` biểu diễn số tiền theo đơn vị nhỏ nhất của tiền tệ; hợp đồng phải ghi rõ quy ước này. Trong hệ thống cần hỗ trợ số thập phân hoặc tiền tệ có số chữ số lẻ khác nhau, có thể dùng `BigDecimal` cùng quy tắc scale và rounding được công bố. `List.copyOf` giúp danh sách không bị sửa qua tham chiếu sau khi tạo event.

Adapter nhận thông điệp từ nền tảng cần giải mã envelope, xác thực nguồn và chuyển thành `IntegrationEvent<OrderCreatedData>`. Lớp nghiệp vụ không nên phụ thuộc vào class event của nhà cung cấp nếu không cần thiết. Khi publish, producer tạo metadata và payload từ cùng một thay đổi nghiệp vụ đã commit; khi consume, function xác thực schema trước khi gọi service ứng dụng.

Trong dự án Java, mỗi kiểu `public` ở ví dụ được đặt trong file riêng theo quy tắc biên dịch của Java. Các record chỉ là mô hình ứng dụng; adapter chịu trách nhiệm ánh xạ tên trường JSON hoặc CloudEvents sang các kiểu này.

Không nên dùng constructor validation để thay thế schema validation đầy đủ. Cần kiểm tra kích thước, kiểu, trường bắt buộc, giới hạn số lượng phần tử và các invariant nghiệp vụ. Dữ liệu không hợp lệ nên được phân loại để đưa vào DLQ hoặc quy trình xử lý dữ liệu, tránh retry vô hạn.

## 9. Sinh ID và bảo đảm tính duy nhất

Định danh cần phù hợp với phạm vi hệ thống, khả năng phát song song và yêu cầu riêng tư. Một số lựa chọn thường gặp:

| Cách tạo ID | Ưu điểm | Lưu ý |
|---|---|---|
| UUID v4 | Ngẫu nhiên, không cần bộ cấp phát trung tâm | Không có thứ tự thời gian; cần unique constraint để bảo vệ ở tầng lưu trữ |
| UUID v7 | Có thành phần thời gian giúp sắp xếp gần theo thời điểm tạo | Không thay thế sequence nghiệp vụ; không dùng để suy ra thứ tự chính xác |
| ULID | Biểu diễn gọn, có thể sắp xếp theo thời gian | Vẫn cần quy tắc uniqueness và không phải thứ tự aggregate |
| ID do cơ sở dữ liệu cấp | Dễ dùng trong một database | Có thể tạo phụ thuộc vào database, tiết lộ quy mô và khó phối hợp nhiều producer |

Không nhúng email, số điện thoại, tên khách hàng hoặc dữ liệu bí mật vào ID. ID thường xuất hiện trong log, URL, metric và công cụ hỗ trợ; dùng dữ liệu cá nhân làm ID có thể làm lộ thông tin ngoài dự kiến. ID cũng không nên mang ý nghĩa có thể thay đổi như trạng thái đơn hoặc tên sản phẩm.

Đặt unique constraint cho khóa định danh trong kho dữ liệu consumer. Xác suất va chạm rất thấp không phải lý do để bỏ kiểm tra tính duy nhất. Khi nhận trùng `eventId`, consumer cần xác minh đó là cùng một nội dung sự kiện đã xử lý hay một xung đột ID bất thường; không âm thầm coi mọi payload cùng ID là hợp lệ nếu nội dung khác nhau.

## 10. Schema, phiên bản và khả năng tương thích

Định danh sự kiện giúp biết đang nhận loại sự kiện nào; schema giúp biết dữ liệu bên trong có cấu trúc gì. Hai phần này phải được quản lý cùng nhau. Có thể lưu schema trong repository, công bố qua `dataschema`, hoặc dùng schema registry. Dù chọn cách nào, producer và consumer cần kiểm tra hợp đồng tự động trong quy trình build và triển khai.

Một số quy tắc tiến hóa schema:

- Ưu tiên thêm trường tùy chọn, có quy tắc mặc định rõ ràng.
- Giữ nguyên kiểu, tên và ý nghĩa của trường đã công bố.
- Không tái sử dụng tên trường cũ cho một ý nghĩa khác.
- Không xóa hoặc đổi kiểu trường nếu consumer cũ vẫn có thể nhận sự kiện.
- Xác định cách consumer xử lý trường chưa biết và trường vắng mặt.
- Khi thay đổi phá vỡ tương thích, công bố phiên bản mới và có lộ trình chuyển consumer.

Ví dụ `order.created.v1` có thể được bổ sung trường tùy chọn `salesChannel` mà không làm hỏng consumer biết bỏ qua trường mới. Nếu `totalAmount` đổi từ số nguyên theo đơn vị nhỏ nhất sang chuỗi decimal với ý nghĩa khác, đây là thay đổi cần phiên bản hợp đồng mới hoặc một quy tắc chuyển đổi rõ ràng.

Không nhầm phiên bản schema với `aggregateVersion`. Schema version mô tả hình dạng và ý nghĩa payload. Aggregate version mô tả trạng thái của một đối tượng nghiệp vụ qua các thay đổi. Một schema v1 có thể được dùng cho hàng triệu sự kiện với aggregate version khác nhau.

## 11. Định tuyến và thứ tự: partition key không phải event ID

Nền tảng truyền sự kiện có thể hỗ trợ partition key, message group ID hoặc ordering key. Các khóa này quyết định cách thông điệp được phân vùng hoặc tuần tự hóa. Nếu cần xử lý các sự kiện của cùng đơn hàng theo thứ tự, `aggregateId` thường là lựa chọn phù hợp làm partition key. Điều đó không có nghĩa `aggregateId` thay thế `eventId`; hai trường giải quyết hai nhu cầu khác nhau.

Không phải event bus nào cũng bảo đảm thứ tự toàn cục. Có nền tảng chỉ bảo đảm trong một partition hoặc message group; có nền tảng không bảo đảm thứ tự khi nhiều consumer chạy song song. Consumer vẫn nên kiểm tra `aggregateVersion`, trạng thái hiện tại và tính hợp lệ của chuyển trạng thái. Nếu nhận version 5 trong khi đang ở version 3, consumer có thể chờ version 4, đọc lại trạng thái chuẩn hoặc đưa vào luồng đối soát theo quy tắc hệ thống.

Partition key cần có phân bố đủ tốt. Nếu mọi thông điệp đều dùng cùng một key, một partition có thể trở thành nút thắt. Nếu nghiệp vụ cần tuần tự theo aggregate, phân vùng theo `aggregateId` thường cân bằng giữa thứ tự trong từng aggregate và xử lý song song giữa các aggregate.

## 12. Metadata vận chuyển và metadata nghiệp vụ

Một thông điệp có thể có metadata do broker hoặc adapter thêm vào, ví dụ delivery count, receipt handle, queue name, visibility timeout hoặc thời điểm nhận. Đây là thông tin phục vụ vận chuyển và vận hành, không phải sự thật nghiệp vụ. Chúng có thể thay đổi giữa các lần giao lại.

Ngược lại, `eventId`, `source`, `type`, `occurredAt` và payload là phần mô tả sự kiện đã được công bố. Các giá trị này cần giữ ổn định khi cùng sự kiện được giao lại. `correlationId` và `causationId` là ngữ cảnh quy trình cần được truyền xuyên qua các bước theo quy ước chung.

Không ghi `deliveryAttempt = 3` vào event payload rồi phát lại như một sự kiện mới. Nếu consumer cần biết lần giao thứ mấy, hãy lấy từ metadata trigger hoặc ghi vào log riêng. Khi chuyển event qua broker khác, adapter có thể ánh xạ metadata vận chuyển nhưng phải giữ nguyên danh tính và ý nghĩa nghiệp vụ của event.

## 13. Bảo mật và quyền riêng tư của trường định danh

ID thường được xem là dữ liệu kỹ thuật, nhưng vẫn có thể tiết lộ thông tin. Mã đơn tăng tuần tự có thể cho biết gần đúng lượng giao dịch; ID chứa email làm lộ danh tính; tenant ID có thể cho biết khách hàng tổ chức. Hãy chọn ID không chứa thông tin cá nhân và chỉ công bố những trường consumer thực sự cần.

Consumer không được xem ID là bằng chứng xác thực hoặc quyền truy cập. Biết `orderId` không có nghĩa được phép đọc đơn hàng. Quyền phải được kiểm tra bằng danh tính workload, policy và ngữ cảnh tenant đã được xác thực. Với event đến từ nguồn bên ngoài, xác minh nguồn, chữ ký hoặc cơ chế xác thực của nền tảng trước khi tin payload.

Không đưa access token, API key hoặc secret vào extension attributes. Tránh ghi toàn bộ payload vào log; ưu tiên log ID, loại sự kiện và kết quả xử lý. Nếu payload có dữ liệu cá nhân, cần có chính sách lưu giữ, mã hóa, kiểm soát quyền truy cập và xử lý yêu cầu xóa theo quy định áp dụng. Event bất biến không có nghĩa dữ liệu cá nhân phải được giữ vô thời hạn; cần thiết kế token hóa, tham chiếu hoặc chiến lược lưu trữ phù hợp.

## 14. Kiểm tra hợp đồng trước khi publish và khi consume

Producer nên kiểm tra dữ liệu trước khi phát để không biến lỗi nội bộ thành lỗi lan truyền qua nhiều consumer. Consumer vẫn cần xác thực lại vì thông điệp có thể đến từ phiên bản producer khác, bị cấu hình sai hoặc được replay từ kho lưu trữ cũ.

Các kiểm tra thường cần có:

- Envelope có đủ các trường bắt buộc; `eventId`, `source` và `type` không rỗng.
- ID có định dạng và phạm vi được quy định; `source + id` không bị tái sử dụng cho sự kiện khác.
- Thời gian hợp lệ, có timezone và tuân theo quy ước UTC.
- `aggregateVersion` có kiểu số và phạm vi hợp lệ nếu loại sự kiện yêu cầu.
- `correlationId`, `causationId` và `tenantId` tuân theo quy tắc của hệ thống.
- Payload đúng schema, giới hạn kích thước và quy tắc nghiệp vụ cơ bản.
- `currency`, đơn vị đo, số tiền và số lượng có ý nghĩa nhất quán.
- Không chứa trường nhạy cảm hoặc dữ liệu không cần thiết.

Khi dữ liệu không hợp lệ, cần phân biệt lỗi tạm thời với lỗi hợp đồng. Retry không thể sửa một payload thiếu `orderId`; thông điệp loại này nên được đưa vào DLQ hoặc quy trình cách ly để điều tra. Nếu schema hợp lệ nhưng kết quả nghiệp vụ từ chối, hãy phát kết quả nghiệp vụ tương ứng thay vì coi đó là lỗi parse.

## 15. Ví dụ xử lý định danh trong Java consumer

Consumer thường lưu dấu sự kiện đã xử lý theo `source` và `eventId` (hoặc một khóa tương đương được hệ thống quy định). Dấu xử lý và thay đổi nghiệp vụ cần nằm trong cùng giao dịch nếu chúng cùng một cơ sở dữ liệu:

```java
public interface ProcessedEventRepository {
    /** Trả true nếu lần đầu ghi nhận, false nếu khóa đã tồn tại. */
    boolean insertIfAbsent(String source, String eventId);
}

public interface OrderProjectionRepository {
    void applyCreated(OrderCreatedData data, long aggregateVersion);
}

public interface TransactionRunner {
    void inTransaction(Runnable work);
}

public final class OrderCreatedConsumer {
    private final ProcessedEventRepository processedEvents;
    private final OrderProjectionRepository projection;
    private final TransactionRunner transactions;

    public OrderCreatedConsumer(
            ProcessedEventRepository processedEvents,
            OrderProjectionRepository projection,
            TransactionRunner transactions) {
        this.processedEvents = processedEvents;
        this.projection = projection;
        this.transactions = transactions;
    }

    public void handle(IntegrationEvent<OrderCreatedData> event) {
        transactions.inTransaction(() -> {
            EventMetadata metadata = event.metadata();
            boolean firstDelivery = processedEvents.insertIfAbsent(
                    metadata.source(), metadata.eventId());

            if (!firstDelivery) {
                return; // Sự kiện này đã được áp dụng thành công trước đó.
            }

            projection.applyCreated(event.data(), metadata.aggregateVersion());
        });
    }
}
```

`insertIfAbsent` cần được thực thi bằng thao tác nguyên tử như `INSERT ... ON CONFLICT DO NOTHING` cùng unique constraint ở database, không chỉ bằng thao tác đọc rồi ghi trong Java. Nếu hai instance serverless xử lý cùng một thông điệp đồng thời, cả hai có thể cùng đọc thấy chưa tồn tại. Unique constraint đảm bảo chỉ một giao dịch ghi được khóa. Nếu cập nhật projection thất bại, giao dịch phải rollback cả dấu đã xử lý để lần retry có thể thử lại.

Đây là minh họa cho trường hợp dấu xử lý và projection nằm trong cùng database. Nếu consumer gọi một dịch vụ ngoài, không thể giả định transaction cục bộ bao trùm lời gọi mạng. Hãy dùng idempotency key do API bên ngoài hỗ trợ, lưu trạng thái tiến trình và có cơ chế đối soát. Cũng cần lưu ý consumer chỉ được acknowledgement sau khi kết quả đã được lưu bền vững.

## 16. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `orderId` làm `eventId` | Mọi sự kiện của một đơn có cùng ID, consumer có thể bỏ qua sự kiện hợp lệ | Tạo event ID riêng cho từng sự kiện; giữ order ID ở aggregate/payload |
| Tạo event ID mới mỗi lần retry | Không nhận diện được giao trùng | Lưu ID cùng outbox và giữ nguyên khi gửi lại |
| Dùng timestamp làm thứ tự duy nhất | Lệch đồng hồ và sự kiện cùng thời điểm gây sai thứ tự | Dùng aggregate version hoặc sequence |
| Dùng `correlationId` thay `causationId` | Không dựng được quan hệ trực tiếp giữa các bước | Giữ correlation ID chung và causation ID theo thông điệp cha |
| Đưa delivery count vào payload bất biến | Replay tạo nội dung event thay đổi, khó kiểm toán | Lấy delivery count từ metadata broker hoặc log |
| Đưa toàn bộ entity database vào payload | Consumer phụ thuộc vào cấu trúc lưu trữ nội bộ | Tạo DTO và schema sự kiện độc lập |
| Đặt email/số điện thoại trong ID | Rò rỉ dữ liệu cá nhân qua log và URL | Dùng ID opaque, không mang ý nghĩa cá nhân |
| Không có schema version | Producer đổi payload có thể làm consumer cũ lỗi | Quản lý version và kiểm tra tương thích |
| Coi biết ID là có quyền truy cập | Có thể truy cập chéo tenant hoặc tài nguyên | Kiểm tra quyền bằng identity, policy và tenant context |

## 17. Quy trình thiết kế hợp đồng sự kiện

Khi định nghĩa một loại sự kiện mới, có thể làm theo trình tự sau:

1. **Viết ý nghĩa nghiệp vụ:** mô tả sự thật nào đã xảy ra và điều kiện nào làm sự kiện được phát.
2. **Xác định producer và quyền sở hữu:** dịch vụ nào có thẩm quyền phát sự kiện; aggregate nào sở hữu thay đổi.
3. **Chọn tên và type:** dùng tên ổn định, có namespace, phân biệt rõ loại sự kiện và phiên bản hợp đồng.
4. **Định nghĩa envelope:** thống nhất event ID, source, subject, occurred time và các trường CloudEvents nếu sử dụng.
5. **Định nghĩa các ID liên kết:** xác định aggregate ID/version, correlation ID, causation ID, tenant ID và idempotency key nào thực sự cần.
6. **Thiết kế payload:** chỉ đưa dữ liệu consumer cần, xác định kiểu, đơn vị, nullability, giới hạn kích thước và dữ liệu nhạy cảm.
7. **Viết schema và ví dụ:** công bố JSON Schema, Avro, Protobuf hoặc định dạng phù hợp; có ví dụ hợp lệ và không hợp lệ.
8. **Đặt quy tắc tương thích:** xác định cách thêm trường, đổi kiểu và phát hành phiên bản mới.
9. **Kiểm thử consumer:** thử sự kiện thiếu trường, trường lạ, giao trùng, sai thứ tự, replay và tenant không hợp lệ.
10. **Theo dõi sau triển khai:** log ID có cấu trúc, đo độ trễ, theo dõi DLQ và thống kê phiên bản event đang được tiêu thụ.

## 18. Checklist rà soát một event contract

- [ ] Tên sự kiện mô tả một sự thật nghiệp vụ đã xảy ra.
- [ ] `eventId` định danh riêng sự kiện và giữ nguyên qua retry/replay.
- [ ] `source` xác định producer; với CloudEvents, cặp `source + id` là duy nhất cho từng sự kiện.
- [ ] `type` ổn định, có namespace và quy ước phiên bản.
- [ ] `subject` hoặc `aggregateId` chỉ rõ đối tượng liên quan.
- [ ] `aggregateVersion` hoặc sequence có ý nghĩa rõ ràng nếu cần kiểm tra thứ tự.
- [ ] `correlationId` và `causationId` được dùng đúng mục đích.
- [ ] `occurredAt` dùng UTC và được phân biệt với thời điểm publish/receive/process.
- [ ] Schema định nghĩa kiểu dữ liệu, đơn vị, nullability và giới hạn payload.
- [ ] Payload không phụ thuộc trực tiếp vào entity hoặc bảng database nội bộ.
- [ ] `tenantId` và quyền truy cập được xác thực nếu hệ thống đa tenant.
- [ ] Không đưa secret hoặc dữ liệu cá nhân không cần thiết vào event.
- [ ] Có kiểm tra schema, quy tắc tương thích và quy trình phát hành phiên bản.
- [ ] Consumer có thể chống xử lý trùng bằng khóa và unique constraint bền vững.
- [ ] Metadata vận chuyển được tách khỏi dữ liệu nghiệp vụ bất biến.

## Kết luận

Một event contract đáng tin cậy cần tách envelope khỏi payload và định nghĩa rõ ý nghĩa của từng trường. `eventId` nhận diện sự kiện; `source` nhận diện nguồn; `aggregateId` và version mô tả đối tượng cùng thứ tự thay đổi; `correlationId` và `causationId` liên kết quy trình; `idempotencyKey` bảo vệ thao tác khỏi hiệu ứng lặp; còn trace context hỗ trợ quan sát kỹ thuật. Khi các trường này được dùng đúng mục đích, Java function có thể xử lý sự kiện an toàn hơn trước giao trùng, giao trễ và mở rộng song song. Hợp đồng cần được quản lý phiên bản, kiểm tra schema, giới hạn dữ liệu và bảo vệ quyền riêng tư để các dịch vụ serverless có thể phát triển độc lập mà vẫn hiểu đúng cùng một sự kiện.
