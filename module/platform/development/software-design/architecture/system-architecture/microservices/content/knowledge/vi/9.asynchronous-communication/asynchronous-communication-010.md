# Chọn thông điệp nghiệp vụ thay vì sao chép toàn bộ dữ liệu nội bộ

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Giao tiếp bất đồng bộ

## 1. Bài toán: một service cần thông báo điều gì cho service khác?

Trong hệ thống microservices, các năng lực nghiệp vụ thường sở hữu dữ liệu và quy tắc của riêng mình. Khi một trạng thái quan trọng thay đổi, các năng lực khác có thể cần phản ứng: đặt hàng thành công thì gửi thông báo, thanh toán hoàn tất thì xuất hóa đơn, sản phẩm được cập nhật thì làm mới chỉ mục tìm kiếm.

Một cách giao tiếp bất đồng bộ là phát thông điệp qua broker hoặc hệ thống event. Tuy nhiên, cách thiết kế **nội dung thông điệp** quyết định mức độ phụ thuộc giữa các service.

Ví dụ OrderService vừa xác nhận đơn hàng. Có hai cách phát thông điệp:

- **Sao chép dữ liệu nội bộ:** đưa toàn bộ đối tượng đơn hàng, mọi dòng hàng, dữ liệu khách, địa chỉ, cấu trúc database, trạng thái kỹ thuật và các quan hệ lồng nhau lên broker.
- **Diễn đạt sự kiện nghiệp vụ:** công bố rằng một đơn hàng cụ thể đã được xác nhận, kèm định danh, thời điểm, phiên bản hợp đồng và những thông tin công khai thực sự cần cho bên nhận.

Cách đầu có vẻ tiện vì consumer nhận ngay nhiều dữ liệu, nhưng dễ biến event thành **bản sao trực tiếp của mô hình lưu trữ**. Khi OrderService thay đổi entity, schema hoặc cách biểu diễn, những consumer không liên quan cũng có thể bị ảnh hưởng. Hậu quả là tăng coupling, phơi bày dữ liệu nhạy cảm, làm thông điệp nặng và mất quyền kiểm soát ranh giới nghiệp vụ.

Cách thứ hai tập trung vào câu hỏi: **điều gì có ý nghĩa với doanh nghiệp đã xảy ra?** Consumer đăng ký sự kiện đó để tự quyết định phản ứng phù hợp với năng lực mình sở hữu.

Điều quan trọng là không cực đoan theo hướng “event lúc nào cũng chỉ có một ID”. Một event quá ít thông tin có thể buộc mọi consumer gọi đồng bộ ngược lại nguồn, tạo **event-triggered API chattiness**. Thiết kế đúng cân bằng giữa ý nghĩa nghiệp vụ, tính ổn định, bảo mật, độ mới dữ liệu và nhu cầu sử dụng thực tế.

## 2. Phân biệt dữ liệu nội bộ, hợp đồng công khai và thông điệp nghiệp vụ

Ba loại cấu trúc này có thể chứa những trường gần giống nhau nhưng có trách nhiệm khác nhau.

| Thành phần | Mục đích | Ai sở hữu? | Có nên gửi nguyên vẹn qua broker? |
| --- | --- | --- | --- |
| Database schema/entity | Lưu trữ và xử lý nghiệp vụ nội bộ | Service sở hữu dữ liệu | Thường không |
| Internal DTO/view | Truyền dữ liệu giữa các lớp bên trong service | Service nội bộ | Không mặc định |
| Integration event | Thông báo sự thật nghiệp vụ cho bên ngoài | Producer sở hữu hợp đồng, consumers phụ thuộc vào hợp đồng đã công bố | Có, sau khi thiết kế riêng |
| Command message | Yêu cầu một bên thực hiện hành động | Bên gọi và bên nhận có hợp đồng rõ | Có, nếu kênh bất đồng bộ phù hợp |
| Read projection | Bản sao dữ liệu tối ưu cho nhu cầu đọc | Consumer hoặc nhóm được giao sở hữu projection | Có thể được cập nhật từ integration events |

**Entity là mô hình triển khai**, có thể chứa khóa ngoại, cờ kỹ thuật, trường tạm, trường tối ưu cache hoặc giá trị không cần công khai. **Integration event là hợp đồng giữa các hệ thống**, cần được thiết kế để phát triển độc lập.

Một thay đổi như tách bảng `orders` thành `orders` và `order_items`, đổi tên property Java hay thêm cache key không nên mặc nhiên buộc event `OrderConfirmed` thay đổi.

## 3. Domain event, integration event và command

### 3.1. Domain event: điều đã xảy ra trong một bounded context

Một domain event có tên ở thì quá khứ và diễn tả một sự thật trong ngôn ngữ nghiệp vụ, ví dụ:

- `OrderConfirmed`
- `PaymentAuthorized`
- `InventoryReservationExpired`
- `CustomerAddressVerified`

Domain event có thể được dùng **nội bộ** trong cùng bounded context để điều phối hành vi. Không phải mọi domain event nội bộ đều cần phát ra broker. Nhiều sự kiện quá nhỏ chỉ liên quan cấu trúc triển khai và không có giá trị như hợp đồng liên hệ thống.

### 3.2. Integration event: sự thật được công bố ra ngoài ranh giới

Integration event đại diện cho một sự kiện đáng quan tâm với hệ thống khác. Nó có schema, ý nghĩa, chính sách tương thích và yêu cầu vận hành riêng.

Ví dụ, OrderService có thể xử lý nhiều domain event nhỏ trong một transaction nhưng chỉ phát `OrderConfirmed` sau khi bất biến xác nhận đơn đã được bảo vệ. Consumer không cần biết OrderService đã chạy bao nhiêu bước nội bộ để đi tới trạng thái đó.

Một domain event có thể được ánh xạ thành integration event; không nên tự động serialize mọi domain event nội bộ thành hợp đồng công khai.

### 3.3. Command: yêu cầu một năng lực làm việc gì đó

Ví dụ `GenerateInvoiceForOrder` là một yêu cầu thực thi, không phải thông báo “hóa đơn đã được tạo”. Một command có thể được chuyển qua queue khi muốn xử lý nền, nhưng cần rõ **người nhận chịu trách nhiệm**, cách ghi nhận tiếp nhận và cách trả trạng thái.

So sánh:

| Câu | Kiểu thông điệp | Ai quyết định hành động? |
| --- | --- | --- |
| “Đơn 8042 đã được xác nhận” | Event `OrderConfirmed` | Mỗi consumer quyết định phản ứng |
| “Hãy phát hành hóa đơn cho đơn 8042” | Command `IssueInvoice` | InvoiceService chịu trách nhiệm xử lý |
| “Hóa đơn INV-33 đã phát hành” | Event `InvoiceIssued` | Các consumer quan tâm được thông báo |
| “Hãy trả trạng thái hóa đơn 8042” | Query | Bên nắm dữ liệu trả kết quả |

Đặt tên message là “event” không tự biến command thành event. Nếu producer phải biết chính xác từng consumer và chỉ đạo họ làm gì, mô hình đó có thể vẫn mang coupling command.

## 4. Ví dụ: không công bố nguyên đối tượng OrderEntity

Giả sử OrderService có cấu trúc lưu trữ bao gồm thông tin đặt hàng, trạng thái thanh toán, địa chỉ, lịch sử xử lý, khóa liên kết, thời gian cập nhật và các trường kỹ thuật.

### 4.1. Thông điệp có nguy cơ phơi bày mô hình nội bộ

Ví dụ minh họa **không nên dùng như một integration contract ổn định**:

```json
{
  "type": "OrderEntityUpdated",
  "order": {
    "databaseId": 8042,
    "entityVersion": 13,
    "internalStatusCode": 7,
    "customer": {
      "customerId": 921,
      "email": "customer@example.test",
      "phone": "0000000000",
      "internalRiskScore": 0.81
    },
    "payment": {
      "providerMetadata": {"rawResponse": "..."},
      "internalRetryCounter": 3
    },
    "items": [
      {
        "productId": "SKU-17",
        "dbRowId": 1928,
        "warehouseJoinKey": 823,
        "costBasis": 18.4
      }
    ],
    "hibernateMetadata": "...",
    "lastModifiedByJob": "worker-7"
  }
}
```

Ví dụ trên trộn lẫn thông tin nghiệp vụ, dữ liệu nhạy cảm và chi tiết triển khai. Consumer phải đoán `internalStatusCode=7` có nghĩa gì, có thể phụ thuộc vào `dbRowId`, hoặc vô tình lưu lại `internalRiskScore` mà không có nhu cầu. Đổi ORM, thêm trường, tách bảng hay đổi enum có thể gây lỗi dây chuyền.

Những trường như điểm rủi ro, metadata đối tác và địa chỉ có thể còn tạo rủi ro truy cập vượt quyền. Không nên phát tán chúng tới mọi consumer chỉ vì có sẵn trong entity.

### 4.2. Thông điệp nói rõ sự thật nghiệp vụ

Một integration event công khai có thể có dạng:

```json
{
  "eventId": "e7d7b8bf-cc55-4cb4-bfad-6b0c8a6978ef",
  "eventType": "order.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T09:15:00Z",
  "producer": "ordering",
  "correlationId": "checkout-8042",
  "aggregateId": "order-8042",
  "aggregateVersion": 13,
  "data": {
    "orderId": "order-8042",
    "confirmedAt": "2026-11-11T09:15:00Z",
    "salesChannel": "WEB"
  }
}
```

Các giá trị chỉ là dữ liệu minh họa. Ý nghĩa của trường cần được công bố trong tài liệu hợp đồng. `aggregateVersion` có thể giúp phát hiện sự kiện lỗi thời hoặc đảo thứ tự theo từng aggregate, nhưng chỉ dùng khi producer có phiên bản đơn điệu được xác định rõ.

Điểm khác biệt:

- `eventType` nêu một **sự thật nghiệp vụ đã xảy ra**, thay vì chỉ nói “entity changed”.
- `orderId` là định danh **nghiệp vụ ổn định**, không phụ thuộc khóa kết nối bảng nội bộ.
- `confirmedAt` mô tả thời điểm sự kiện có hiệu lực theo quy ước.
- `schemaVersion` cho phép quản lý sự phát triển hợp đồng.
- `eventId` cung cấp định danh xử lý trùng ở consumer.
- `correlationId` hỗ trợ liên hệ event với một hành trình mà không đưa dữ liệu nhạy cảm vào log.

Event này không đủ cho mọi use case. Nếu consumer cần biết tiền tệ hoặc tổng tiền **tại thời điểm xác nhận**, việc thêm một giá trị đã được công bố là hợp đồng nghiệp vụ có thể hợp lý. Không có lý do bắt tất cả consumer phải gọi API chỉ để lấy một thuộc tính nhỏ, ổn định và an toàn.

## 5. Thiết kế payload: tối thiểu có ý nghĩa, không tối thiểu tuyệt đối

Quy tắc hữu ích là:

> Chỉ công bố những thông tin bên ngoài thực sự cần hiểu sự kiện hoặc phản ứng với nó, ở mức ổn định mà producer sẵn sàng duy trì như một hợp đồng.

Một phương pháp chọn trường:

1. **Bắt đầu từ tên sự kiện:** Điều gì đã xảy ra, khi nào, với thực thể nghiệp vụ nào?
2. **Liệt kê consumer dự kiến:** Notification, Analytics, Shipping, Loyalty... và phản ứng mỗi bên cần thực hiện.
3. **Đánh dấu thông tin bắt buộc:** định danh, mốc thời gian, giá trị nghiệp vụ có ý nghĩa, thông tin để phân biệt cùng một sự kiện.
4. **Phân loại trường nhạy cảm:** có chứa PII, dữ liệu thanh toán, bí mật, dữ liệu chỉ dành cho một quyền truy cập riêng không?
5. **Đánh giá tính ổn định:** trường có phụ thuộc cấu trúc database, thứ tự enum nội bộ hoặc thuật toán triển khai không?
6. **Đánh giá độ mới:** consumer cần snapshot tại thời điểm event hay dữ liệu mới nhất khi xử lý?
7. **Định nghĩa cách phát triển:** thêm trường tùy chọn có tương thích không; xóa/đổi nghĩa trường ảnh hưởng ai?
8. **Chốt chính sách lỗi và xử lý trùng:** consumer nào có thể nhận lại event, nhận trễ, hoặc xử lý lại lịch sử?

### 5.1. Nhóm trường thường hữu ích

| Nhóm | Ví dụ | Vì sao có thể cần |
| --- | --- | --- |
| Danh tính message | `eventId`, `eventType` | Định tuyến, nhận diện, chống lặp |
| Phiên bản hợp đồng | `schemaVersion` | Giải mã và tiến hóa schema |
| Thời điểm | `occurredAt` | Hiểu thời điểm sự kiện diễn ra |
| Định danh nghiệp vụ | `orderId`, `paymentId` | Liên hệ đúng đối tượng |
| Quan hệ nhân quả | `correlationId`, `causationId` | Truy vết hành trình xử lý |
| Thứ tự theo đối tượng | `aggregateVersion`, sequence | Phát hiện event cũ/đảo thứ tự khi có cơ sở |
| Dữ liệu nghiệp vụ được công bố | `currency`, `confirmedTotal` | Consumer cần snapshot hợp lệ |
| Nguồn phát | `producer` | Hỗ trợ quan sát, ownership, hợp đồng |

Không phải event nào cũng bắt buộc mọi trường. Một hệ thống có thể đặt metadata trong header của broker thay vì body. Điều quan trọng là ý nghĩa và cách truy cập được thống nhất giữa producer với consumer.

### 5.2. Những trường thường không nên phát công khai

- Khóa chính phụ, khóa join, tên bảng, ORM proxy và navigation properties.
- Stack trace, retry counter, cờ bảo trì, giá trị cache và thông tin theo dõi debug nội bộ.
- Token, secret, thông tin định danh nhạy cảm, dữ liệu thẻ hoặc thông tin rủi ro mà consumer không có quyền biết.
- Object graph lồng nhau lớn chỉ vì thao tác serialize entity quá dễ.
- Các enum dạng số mà chỉ mã nguồn producer mới biết ý nghĩa.

Một trường có tên giống dữ liệu nội bộ **không nhất thiết** là sai. Vấn đề là nó có ý nghĩa nghiệp vụ ổn định và được phê duyệt thành hợp đồng hay chỉ vô tình bị lộ từ cấu trúc triển khai.

## 6. Event notification và event-carried state transfer

Có hai cách phổ biến để phân phối thông tin qua event. Cả hai có thể hợp lệ nếu chọn dựa trên yêu cầu.

### 6.1. Event notification: báo có sự thay đổi

Ví dụ:

```json
{
  "eventType": "product.price-changed",
  "data": {
    "productId": "sku-17",
    "priceVersion": 41
  }
}
```

Consumer biết giá đã đổi, sau đó tự quyết định có tải dữ liệu mới từ nguồn sở hữu hay không.

**Ưu điểm:** payload nhỏ, không phải mang nhiều dữ liệu; producer không cần dự đoán tất cả nhu cầu đọc. **Đánh đổi:** consumer có thể cần gọi API; nếu hàng nghìn event cùng đến hoặc API nguồn unavailable, hệ thống dễ phát sinh N+1, thundering herd và coupling runtime.

### 6.2. Event-carried state transfer: mang một phần trạng thái đã công bố

Ví dụ:

```json
{
  "eventType": "product.price-changed",
  "data": {
    "productId": "sku-17",
    "priceVersion": 41,
    "newPrice": {
      "amount": "249000",
      "currency": "VND"
    },
    "effectiveAt": "2026-11-11T09:00:00Z"
  }
}
```

Consumer có thể cập nhật read model mà không phải gọi lại producer cho mỗi event. Tuy nhiên, các trường giá và thời điểm hiệu lực trở thành **hợp đồng ổn định**; producer cần biết ai được phép sử dụng, giá áp dụng cho vùng/khách hàng nào, xử lý giá có hiệu lực trong tương lai và cách phân biệt tiền tệ.

**Không đồng nhất state transfer với việc serialize toàn bộ entity.** State transfer được thiết kế có chủ đích cho nhu cầu phân phối trạng thái, với schema công khai và phạm vi rõ.

### 6.3. Chọn mô hình theo nhu cầu

| Câu hỏi | Notification thường phù hợp | State transfer có chọn lọc thường phù hợp |
| --- | --- | --- |
| Consumer cần ít thông tin và ít event? | Có | Chưa chắc cần |
| Consumer cần tự duy trì projection đọc? | Có thể, nhưng phải gọi lại nguồn | Thường thuận tiện hơn |
| Nguồn có thể phục vụ truy vấn theo tải từ event? | Cần đánh giá | Có thể giảm tải đọc lại |
| Dữ liệu nhạy cảm và nhiều quyền truy cập? | Payload nhỏ có lợi | Phải kiểm soát phạm vi phân phối rất chặt |
| Consumer cần snapshot đúng thời điểm event? | Query dữ liệu hiện tại có thể không đủ | Snapshot có phiên bản có thể phù hợp |
| Producer muốn giảm hợp đồng dữ liệu công khai? | Thường ít trường hơn | Nhiều trường hơn phải duy trì ổn định |

Hai lựa chọn không loại trừ nhau. Có thể phát sự kiện nghiệp vụ có vài thuộc tính cần thiết và cung cấp API query cho nhu cầu đặc biệt hoặc dữ liệu bị hạn chế quyền truy cập.

## 7. Consumer có quyền biết gì, và ai sở hữu sự thật?

Giả sử các năng lực có ranh giới:

    Ordering    : xác nhận đơn, vòng đời đơn
    Payment     : giao dịch, trạng thái thanh toán
    Inventory   : tồn kho, giữ hàng
    Notification: gửi thông báo
    Analytics   : chỉ số và báo cáo

Ordering không nên gửi toàn bộ `PaymentEntity` chỉ vì trong cơ sở dữ liệu của Ordering có bản ghi snapshot liên quan tới thanh toán. Payment mới là nguồn chịu trách nhiệm về trạng thái thanh toán. Nếu Ordering phát `OrderConfirmed`, nó chỉ cam kết nghĩa của “đơn đã xác nhận” trong bounded context của mình.

Ví dụ một consumer Analytics nhận `OrderConfirmed` không được tự kết luận “đã thu tiền thành công” nếu hợp đồng OrderConfirmed không đảm bảo điều đó. Nếu doanh thu chỉ được ghi nhận sau thanh toán, Analytics có thể cần `PaymentCaptured` hoặc một business event khác mô tả đúng thời điểm ghi nhận doanh thu.

**Ngôn ngữ nghiệp vụ quan trọng hơn cấu trúc field.** Hai service có thể cùng dùng từ “status” nhưng định nghĩa khác nhau. Một contract tốt phải ghi rõ điều kiện làm phát sinh event và những điều event không đảm bảo.

### 7.1. Tránh chia sẻ enum nội bộ

Một service có thể dùng:

    enum InternalOrderState {
        CREATED, WAITING_FOR_PAYMENT, RESERVED, CONFIRMED, ARCHIVED
    }

Nếu message phát nguyên ordinal của enum (0, 1, 2...), việc đổi thứ tự enum có thể phá consumer. Thay vì thế, dùng một event được định nghĩa rõ như `OrderConfirmed`, hoặc một chuỗi trạng thái công khai khi consumer thật sự cần nó, có tài liệu giải thích ý nghĩa và chính sách tương thích.

### 7.2. Không dùng event để lách quyền sở hữu dữ liệu

Nếu consumer nhận event rồi coi bản sao của mình là nguồn sự thật để ra quyết định **yêu cầu nhất quán mạnh**, nó có thể quyết định sai khi event đến trễ. Ví dụ Inventory không được xác nhận khả năng giữ hàng dựa trên snapshot tồn kho trễ của Analytics.

Projection là dữ liệu dẫn xuất, có mức độ mới và trách nhiệm khác với dữ liệu authoritative. Với quyết định quan trọng, cần quy định rõ có được sử dụng projection hay phải giao quyền xác nhận cho service sở hữu bất biến.

## 8. Dùng một ví dụ xuyên suốt: xác nhận đơn và thông báo

Xét quy trình khách hoàn tất đặt hàng:

1. Ordering kiểm tra điều kiện tạo đơn và lưu trạng thái phù hợp.
2. Khi đơn thực sự được xác nhận, Ordering tạo integration event `OrderConfirmed`.
3. Notification đọc event và gửi thông báo.
4. Analytics đọc event để ghi nhận lượt đơn xác nhận.
5. Loyalty có thể xử lý tích điểm theo quy tắc riêng; nếu điều kiện là thanh toán thành công thì Loyalty cần event phù hợp từ Payment hoặc một business workflow được mô hình hóa rõ.

### 8.1. Payload công khai đủ dùng

```json
{
  "eventId": "7fd05b23-881b-4193-9882-3a10ae3f8723",
  "eventType": "order.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-11T10:05:00Z",
  "producer": "ordering",
  "aggregateId": "ord-1205",
  "data": {
    "orderId": "ord-1205",
    "customerRef": "cust-381",
    "confirmedAt": "2026-11-11T10:05:00Z",
    "salesChannel": "WEB",
    "currency": "VND",
    "confirmedTotal": "385000"
  }
}
```

Trong ví dụ này, `confirmedTotal` là số tiền tại thời điểm xác nhận theo định nghĩa của Ordering. Tên trường và quy ước số tiền phải được công bố rõ: đơn vị là đồng, đồng xu, hay một decimal biểu diễn bằng chuỗi; có bao gồm thuế/vận chuyển hay không; trường này có phải số tiền đã thu thành công hay chưa.

Nếu Notification cần email, có thể dùng `customerRef` để gọi một dịch vụ được quyền cung cấp thông tin liên hệ, hoặc có một kênh riêng chuyển dữ liệu đã được cho phép. Việc cho mọi consumer nhận trực tiếp email và số điện thoại không phải lựa chọn mặc định.

### 8.2. Phản ứng độc lập

    Ordering
       |
       | OrderConfirmed
       v
    Message broker
       |----------------> Notification
       |----------------> Analytics
       '----------------> Reporting projection

Mỗi consumer có thể triển khai riêng. Nếu Notification ngừng trong một khoảng thời gian, các event đã được lưu bền theo cấu hình broker có thể được xử lý khi consumer phục hồi. Tuy nhiên điều này chỉ đúng trong phạm vi retention, delivery semantics và hệ thống đã xác định rõ; không mặc định broker sẽ lưu mãi mãi.

### 8.3. Tách dữ liệu nghiệp vụ khỏi dữ liệu điều phối

Event có thể có `eventId`, `correlationId`, `occurredAt` và metadata schema để phục vụ vận hành. Nhưng không cần nhét thread ID, tên class producer, stack trace, connection string hay số lần thử của job vào payload công khai.

Với tracing, correlation ID có thể nằm trong message headers, cùng trace context theo chuẩn được hệ thống chọn. Consumer cần tạo span xử lý và truyền trace phù hợp khi tạo tác vụ tiếp theo; đồng thời tránh đưa dữ liệu bí mật vào metadata quan sát.

## 9. Thiết kế event schema như một API dài hạn

Thông điệp qua broker là **API bất đồng bộ**. Consumer có thể đang chạy phiên bản cũ khi producer bắt đầu phát phiên bản mới; event có thể được lưu để replay sau nhiều ngày hoặc nhiều tháng.

Vì vậy schema event cần được quản lý như hợp đồng được công bố.

### 9.1. Phát triển tương thích

Thay đổi thường dễ tương thích hơn khi:

- Thêm trường tùy chọn với giá trị mặc định và ý nghĩa rõ.
- Giữ nguyên tên và nghĩa của các trường đang được sử dụng.
- Không đổi kiểu dữ liệu một cách bất ngờ.
- Không xóa giá trị enum công khai khi consumer cũ còn phụ thuộc.
- Giữ khả năng đọc phiên bản trước trong giai đoạn chuyển tiếp.
- Viết schema và contract tests để phát hiện thay đổi phá vỡ consumer.

Những thay đổi như đổi `orderId` từ chuỗi sang đối tượng mới, dùng lại `OrderConfirmed` nhưng đổi nghĩa thành “đơn mới tạo”, hoặc xóa trường bắt buộc đều có thể là breaking changes.

### 9.2. Quản lý phiên bản có chủ đích

Có thể dùng version trong envelope, subject của schema registry, hoặc tên event mới theo chiến lược của nền tảng. Ví dụ `order.confirmed` phiên bản 1 và 2. Quyết định phải trả lời:

- Producer phát một hay nhiều phiên bản trong giai đoạn chuyển đổi?
- Consumer nào được phép nâng cấp độc lập?
- Dữ liệu đã lưu trước đó được replay như thế nào?
- Khi event mới chứa thuộc tính cũ bị loại bỏ, consumer cũ có còn chạy được không?
- Khi nào có thể ngừng phát phiên bản cũ?

Không phải thay đổi cấu trúc nào cũng cần đặt tên `OrderConfirmedV2`; nhưng thay đổi ý nghĩa nghiệp vụ có thể cần **một event mới**, thay vì âm thầm thay contract của event cũ.

### 9.3. Schema registry không thay thế semantic contract

Avro, Protobuf, JSON Schema hoặc schema registry có thể giúp kiểm tra kiểu và tương thích cấu trúc. Chúng không tự trả lời “Confirmed có nghĩa là thanh toán đã thành công chưa?” hoặc “Total bao gồm hoàn tiền hay không?”. Các quy tắc nghiệp vụ này phải được tài liệu hóa riêng và kiểm chứng bằng các ví dụ.

## 10. Đảm bảo event thật sự tương ứng với một thay đổi đã commit

Một lỗi nguy hiểm:

    1. Ordering cập nhật đơn hàng trong DB.
    2. Commit DB thành công.
    3. Gửi OrderConfirmed lên broker bị lỗi.

Khi đó consumer không nhận được event dù đơn đã xác nhận.

Lỗi ngược lại:

    1. Phát OrderConfirmed lên broker thành công.
    2. Giao dịch DB thất bại/rollback.

Lúc đó consumer có thể xử lý một sự thật chưa từng được ghi nhận chính thức.

**Transactional outbox** là một giải pháp phổ biến khi DB và broker không cùng giao dịch phân tán:

    Transaction DB:
      UPDATE orders SET status = 'CONFIRMED' WHERE ...
      INSERT INTO outbox(event_id, event_type, payload, created_at)
      COMMIT

    Outbox publisher:
      read unpublished outbox rows
      publish to broker
      record publish progress
      retry safely when necessary

Việc cập nhật trạng thái và ghi bản ghi outbox diễn ra trong **cùng một transaction của DB**. Publisher tách riêng chuyển event sang broker. Cần hiểu rằng outbox thường đạt **at-least-once delivery** trong thực tế: nếu publish thành công nhưng chưa ghi nhận tiến độ thì event có thể được phát lại. Consumer vì vậy phải xử lý lặp an toàn.

Có thể dùng CDC để chuyển các bản ghi outbox ra broker. **CDC trên bảng nghiệp vụ thô không tự trở thành domain event**: thay đổi cột và hàng không nhất thiết mang đúng ý nghĩa nghiệp vụ. Mẫu outbox vẫn có giá trị vì producer chủ động ghi integration event đã được định nghĩa.

## 11. Xử lý message trùng, đến trễ và sai thứ tự

Giao tiếp bất đồng bộ có thể gặp redelivery, consumer restart, network partition và thay đổi phân vùng.

### 11.1. Idempotent consumer

Consumer nên dùng `eventId` hoặc business idempotency key để tránh thực thi tác dụng phụ trùng. Một cách đơn giản:

    BEGIN TRANSACTION
      IF eventId đã có trong processed_messages:
          COMMIT; ACK
          return

      áp dụng thay đổi dữ liệu của consumer
      INSERT processed_messages(eventId)
    COMMIT
    ACK

Ở mô hình này, bản ghi chống trùng và tác động trên database **cùng một transaction**. Với tác dụng phụ ở hệ thống ngoài, chẳng hạn gửi email hoặc thu tiền, transaction DB này không thể bao trùm mọi thứ. Cần idempotency ở cổng ngoài, trạng thái xử lý hoặc quy trình đối soát tương ứng.

Consumer phải định nghĩa liệu xử lý event là tạo một lần, cập nhật theo phiên bản hay ghi nhận một sự kiện có thể tái diễn. `eventId` chỉ nhận diện một lần công bố, còn business key giúp nhận diện thao tác có ý nghĩa nghiệp vụ.

### 11.2. Event đến trễ hoặc đảo thứ tự

Ví dụ `OrderConfirmed` và `OrderCancelled` có thể đến consumer theo thứ tự khác với thứ tự nghiệp vụ do nhiều partition, retry hoặc replay. Để xử lý, có thể:

- Dùng partition key theo `orderId` khi broker bảo đảm thứ tự trong phạm vi partition.
- Gắn `aggregateVersion` có nghĩa và tăng đơn điệu để consumer phát hiện cập nhật cũ.
- Thiết kế projection xử lý lại/đối soát với nguồn khi phát hiện khoảng trống phiên bản.
- Dùng state machine và điều kiện chuyển trạng thái hợp lệ, thay vì chỉ lấy “event đến sau cùng” làm sự thật.

Không nên mặc định có thứ tự toàn cục trên mọi topic hoặc giữa nhiều producer. Cũng không nên hiểu timestamp lớn hơn luôn có nghĩa là trạng thái mới hơn trong mọi bối cảnh.

### 11.3. Poison message và schema không tương thích

Nếu consumer không giải mã được payload hoặc business validation thất bại, retry vô hạn có thể chặn partition/hàng đợi. Cần phân biệt lỗi tạm thời với lỗi vĩnh viễn, có chính sách dead-letter/quarantine, cảnh báo và khả năng xử lý lại có kiểm soát. Những thay đổi schema phá vỡ consumer phải được phát hiện trước khi rollout.

## 12. Bảo mật và quyền riêng tư trong thông điệp

Broker có thể có nhiều consumer, tài khoản dịch vụ và cơ chế retention/replay. Một trường dữ liệu nhạy cảm khi đã phát vào topic dùng chung có thể bị sao chép vào log, DLQ, projection, backup và môi trường phân tích.

Trước khi thêm trường:

1. Consumer nào thực sự cần trường đó cho hành vi đã được phép?
2. Topic/queue có cơ chế phân quyền đọc và ghi riêng không?
3. Thông điệp có chứa thông tin định danh cá nhân, token, bí mật hoặc dữ liệu thanh toán không?
4. Dữ liệu phải được giữ bao lâu, có thể được replay tới ai, và quy định xóa dữ liệu có áp dụng không?
5. Có thể thay bằng business ID, pseudonymous ID hoặc tham chiếu được kiểm soát quyền truy cập không?
6. Có cần tách event công khai với message dành riêng cho một consumer có quyền cao hơn không?

**Ví dụ:** Notification cần địa chỉ email để gửi thư, nhưng Analytics không cần biết email để đếm số đơn. Thay vì đưa email trong `OrderConfirmed` topic chung, có thể để Notification tải liên hệ qua API được cấp quyền hoặc nhận một message riêng tuân theo chính sách dữ liệu. Việc lấy email tại thời điểm xử lý có thể khiến địa chỉ khác thời điểm đặt hàng; cần chọn theo đúng quy tắc nghiệp vụ và quyền riêng tư.

Không ghi raw payload chứa PII vào log/traces chỉ để debug. Log có thể ghi `eventId`, `eventType`, `orderId` đã được cho phép, trạng thái xử lý và mã lỗi; các trường nhạy cảm cần được ẩn hoặc hạn chế.

## 13. Khi nào bản sao dữ liệu có chọn lọc là chủ đích đúng?

Có những nhu cầu **cần** lan truyền dữ liệu chứ không chỉ báo một ID:

- SearchIndex cần tên, mô tả, thuộc tính có thể tìm kiếm.
- Reporting cần snapshot một số giá trị tại thời điểm giao dịch.
- Read model cho màn hình tổng hợp cần vài trường từ nhiều bounded context.
- Một vùng mạng tách biệt cần hoạt động khi nguồn tạm thời không thể truy vấn.

Trong các trường hợp này, có thể thiết kế integration event mang trạng thái được công bố hoặc một data product riêng. Điều kiện:

- Chỉ rõ **producer authoritative** và định nghĩa trường công khai.
- Chọn tập trường cho nhu cầu đã biết, tránh vô tình phát toàn bộ entity.
- Có version và quy tắc tương thích.
- Có định danh, thứ tự và phương pháp dựng lại projection.
- Có chiến lược xử lý sự kiện bị mất, trễ, trùng hoặc replay.
- Có giới hạn quyền truy cập và thời gian lưu trữ dữ liệu.
- Công bố tính nhất quán: projection cập nhật trễ bao lâu, có điều kiện nào không được dùng để quyết định nghiệp vụ.

**Đánh đổi:** payload đầy đủ giúp giảm số query trực tiếp nhưng tăng phạm vi hợp đồng và dữ liệu sao chép. Payload nhỏ giảm bề mặt phụ thuộc schema nhưng có thể làm tăng runtime coupling nếu consumer luôn phải hỏi lại producer. Chọn mức dữ liệu công bố dựa trên nghiệp vụ và số liệu thực tế.

## 14. Các anti-pattern đáng chú ý

### 14.1. Serialize toàn bộ entity làm event

Ví dụ `objectMapper.writeValueAsString(orderJpaEntity)` rồi phát đi. Điều này ràng buộc consumer với ORM, quan hệ lazy/eager, cấu trúc database và các trường có thể thay đổi mà không qua review hợp đồng.

**Hướng cải thiện:** ánh xạ entity/domain state sang một integration-event DTO độc lập, có schema, tài liệu và kiểm thử hợp đồng.

### 14.2. Phát `EntityUpdated` cho mọi thay đổi

Một sự kiện quá chung như `OrderUpdated` với `oldValue/newValue` không nói được một hành động nghiệp vụ có ý nghĩa nào đã xảy ra. Consumer có thể phải tự suy đoán bằng cách so sánh trạng thái trước/sau, khiến logic domain bị rò rỉ ra nhiều nơi.

**Hướng cải thiện:** phát các sự thật có nghĩa như `OrderConfirmed`, `OrderCancelled` khi sự kiện đó thực sự tồn tại trong domain. Với nhu cầu đồng bộ kỹ thuật như CDC/search, có thể dùng feed thay đổi dữ liệu riêng với contract và phạm vi rõ.

### 14.3. Event được thiết kế theo một consumer duy nhất

Ví dụ `OrderEmailPayloadReady` mang toàn bộ HTML và dữ liệu để Notification gửi thư, trong khi producer là Ordering. Ordering đã biết quá nhiều về cách Notification hiển thị. Nếu đó là một **command rõ chủ sở hữu** thì cần định nghĩa như command; nếu là event nghiệp vụ thì mô tả điều đã xảy ra và để consumer sở hữu cách phản ứng.

### 14.4. Bắt mọi consumer tự đi tìm tất cả dữ liệu

Event chỉ có `orderId`, nhưng mọi consumer lập tức gọi Ordering để tải 50 trường và truy vấn bổ sung. Hệ thống từ coupling schema chuyển sang phụ thuộc runtime, gây fan-out và làm mất một phần lợi ích bất đồng bộ.

**Hướng cải thiện:** xác định một tập trường ổn định, an toàn, đủ cho nhiều phản ứng chính, hoặc thiết kế read model/feed riêng để đồng bộ thông tin cần thiết.

### 14.5. Dùng tên event mang nghĩa sai

`PaymentSucceeded` chỉ hợp lý khi điều kiện “succeeded” được định nghĩa rõ. Nếu thực tế mới chỉ gửi yêu cầu tới đối tác, nên dùng tên như `PaymentRequested` hoặc `PaymentAuthorizationStarted` theo domain. Consumer không nên dựa vào sự kiện mơ hồ để giao hàng hoặc ghi doanh thu.

### 14.6. Dùng JSON không version vì “broker đã lưu message”

Broker lưu byte, không bảo đảm consumer mới hiểu event cũ. Schema phải có chiến lược thay đổi và replay. Ngay cả khi dùng schema registry, quy tắc semantic vẫn cần được quản lý riêng.

## 15. Quy trình thiết kế một integration event

Một phiên thiết kế có thể diễn ra theo các bước sau.

**Bước 1 — Mô tả business fact.** Viết một câu ngắn bằng ngôn ngữ domain: “Đơn hàng được xác nhận sau khi đã thỏa điều kiện X”. Nêu rõ trigger và bất biến.

**Bước 2 — Xác định producer authoritative.** Service nào sở hữu sự thật đó và có quyền công bố? Tránh để service trung gian phát đi trạng thái mà nó chỉ suy đoán.

**Bước 3 — Liệt kê consumers và hành vi dự kiến.** Notification muốn gửi email, Analytics muốn ghi chỉ số, Loyalty muốn tính điểm. Đừng thêm dữ liệu chỉ vì “có thể ai đó sẽ cần”.

**Bước 4 — Chọn semantics và payload.** Tên event thì quá khứ, business ID ổn định, thời gian và những giá trị cần cho phản ứng. Phân biệt snapshot với dữ liệu hiện tại.

**Bước 5 — Định nghĩa event envelope.** Event ID, type, schema version, producer, correlation/causation ID và cách xử lý thứ tự khi cần.

**Bước 6 — Phân loại dữ liệu.** Xóa thông tin triển khai, secrets và PII không cần thiết. Nếu dữ liệu hạn chế là bắt buộc, xác định topic/quyền truy cập hoặc kênh truyền riêng.

**Bước 7 — Chốt hợp đồng lỗi.** Message có thể lặp, đến trễ, bị xử lý không thành công; producer/consumer cần outbox, idempotency, retry, DLQ và đối soát ở mức tương ứng.

**Bước 8 — Lập kế hoạch thay đổi schema.** Nêu cách add optional field, deprecate field, chuyển đổi v1/v2 và xử lý replay.

**Bước 9 — Đo hoạt động thật.** Quan sát publish lag, consumer lag, DLQ, duplicate, tỉ lệ event không hiểu, số API gọi lại nguồn, tải trên broker và độ trễ hội tụ của projection.

**Bước 10 — Xem lại sau khi domain thay đổi.** Nếu consumer mới luôn cần một bộ dữ liệu rất khác, có thể cần event mới, projection riêng hoặc một query API, thay vì nhồi mọi trường vào event cũ.

## 16. Checklist kiểm tra hợp đồng thông điệp

| Câu hỏi | Kỳ vọng |
| --- | --- |
| Tên có nêu sự thật nghiệp vụ hoặc command rõ ràng? | Không phụ thuộc thuật ngữ ORM/DB |
| Producer có sở hữu sự thật được công bố? | Ranh giới bounded context rõ |
| Consumer biết khi nào event được phát? | Trigger và bất biến được tài liệu hóa |
| Payload có field chỉ phục vụ triển khai nội bộ không? | Đã bỏ hoặc tách khỏi contract công khai |
| Có phát PII, secrets hoặc dữ liệu không cần thiết? | Phạm vi tối thiểu theo quyền truy cập |
| Có định danh và thời điểm có nghĩa? | `eventId`, business ID, `occurredAt` theo quy ước |
| Có cơ chế tương thích schema? | Versioning, contract tests, giai đoạn chuyển tiếp |
| Có chống xử lý trùng? | Idempotency ở phạm vi tác dụng phụ |
| Có đường xử lý lỗi và trễ? | Retry, DLQ, replay, reconciliation |
| Có thể xây projection đúng không? | Hiểu snapshot, thứ tự, version, staleness |
| Có observability? | Tracing/correlation, lag, error metrics |
| Có tránh API chattiness sau event? | Payload/projection/query được cân bằng phù hợp |

Checklist này hướng dẫn **thiết kế và vận hành**, không biến mọi trường thành bắt buộc cho mọi event. Một `PriceChanged` có payload khác `OrderConfirmed`, và một command chạy một lần cũng có contract khác một event dùng cho replay nhiều năm.

## 17. Bài tập tình huống

Một hệ thống có OrderService, PaymentService, ShippingService và NotificationService. Hiện tại mỗi khi đơn hàng đổi trạng thái, OrderService phát `OrderEntityUpdated` chứa toàn bộ object graph: trạng thái đơn, địa chỉ giao hàng, email, thông tin thanh toán, từng dòng sản phẩm, trạng thái retry, audit log và liên kết database.

Các nhóm báo cáo: mỗi lần đổi entity phải sửa consumer; event payload lớn; Notification đôi khi gửi hai email do redelivery; Shipping lấy `paymentStatus` từ bản copy của OrderService và có lúc đọc giá trị chậm.

Hãy trả lời:

1. Trong event hiện tại, trường nào là implementation detail, trường nào là PII, trường nào thực sự có ý nghĩa nghiệp vụ?
2. Nên có những business events nào thay cho `OrderEntityUpdated`? Điều kiện phát của từng event là gì?
3. Ordering có quyền cam kết trạng thái thanh toán không? Nếu không, event nào từ PaymentService cần được dùng?
4. Notification có thể lấy thông tin liên hệ qua cơ chế nào mà không phát công khai email trên mọi topic?
5. Nếu cần hiển thị lịch sử đơn, nên dùng snapshot tại thời điểm đặt hàng, read projection hay truy vấn dữ liệu hiện tại?
6. `eventId` nên được dùng như thế nào để chống gửi email lặp? Nếu provider gửi email không hỗ trợ idempotency, còn giới hạn nào?
7. Nếu Shipment đã được tạo nhưng `OrderConfirmed` đến sau một event khác, projection cần xử lý thứ tự ra sao?
8. Cách nào để OrderService không commit đơn đã xác nhận mà lại mất hoàn toàn event cần phát?
9. Khi consumer cũ và producer mới cùng chạy, kế hoạch tiến hóa schema nào có thể tránh lỗi trong giai đoạn chuyển tiếp?
10. Bạn sẽ đo metrics nào để biết thiết kế mới giảm coupling và không tạo quá nhiều API calls ngược về producer?

### Gợi ý thiết kế

Một sơ đồ quan hệ có thể là:

    Ordering
      |-- OrderConfirmed -----------------> Notification
      |                                  -> Analytics
      |
    Payment
      '-- PaymentCaptured ---------------> Accounting/Reporting
      |
    Shipping
      '-- ShipmentDispatched ------------> Tracking/Notification

Cần xác định trước hợp đồng nghiệp vụ của từng event, cách correlate cùng `orderId` và quyền truy cập data. Mọi sơ đồ trên chỉ minh họa ranh giới trách nhiệm; quy trình thực tế còn phụ thuộc mô hình đặt hàng và thanh toán được doanh nghiệp chấp nhận.

## 18. Những điều cần ghi nhớ

1. **Thông điệp nghiệp vụ mô tả điều xảy ra hoặc điều được yêu cầu**, không chỉ là bản serialize của bảng hoặc class nội bộ.
2. **Integration event là hợp đồng công khai**, có ownership, semantic, schema evolution, versioning và điều kiện phát rõ ràng.
3. **Payload nên đủ dùng và có chủ đích.** Quá nhiều trường gây rò rỉ mô hình và dữ liệu; quá ít trường có thể tạo phụ thuộc API và tải không cần thiết.
4. **Domain event, integration event, command và data-change feed không đồng nhất.** Chọn theo vai trò tương tác.
5. **Bản sao dữ liệu có chọn lọc là hợp lệ** cho projection, analytics hoặc cache khi quyền sở hữu, nhất quán và bảo mật đã được xác định.
6. **Broker không giải quyết tính đúng đắn ở mức nghiệp vụ.** Outbox, idempotency, thứ tự có phạm vi, retry, DLQ và reconciliation vẫn cần khi phù hợp.
7. **Bảo vệ ranh giới service:** service phát sự kiện về điều nó thực sự sở hữu; consumer không suy diễn sự thật của một domain khác từ các field tình cờ có mặt.
8. **Đo cả coupling thiết kế lẫn vận hành:** thay đổi một entity có còn phá consumer không, sự kiện có dễ replay không, consumer có phụ thuộc quá nhiều vào API nguồn không?

Trong microservices, lựa chọn tốt không nằm ở việc phát một object thật lớn hay thật nhỏ. Nó nằm ở việc **công bố đúng sự thật nghiệp vụ, với dữ liệu cần thiết, bằng một hợp đồng ổn định và an toàn** để các năng lực có thể phát triển độc lập.
