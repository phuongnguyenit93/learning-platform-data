# Phản ứng trong cùng ngữ cảnh và ranh giới của các tác dụng phụ

Khi một đơn hàng được đặt thành công, nhiều việc có thể cần diễn ra tiếp theo: cập nhật hạn mức mua chịu của khách, làm mới lịch sử mua hàng, gửi email xác nhận, yêu cầu kho giữ hàng hoặc thông báo cho hệ thống vận chuyển. Những phản ứng này đều bắt đầu từ một sự việc có ý nghĩa trong domain, nhưng chúng không nhất thiết có cùng yêu cầu nhất quán, cùng thời điểm thực hiện hoặc cùng cơ chế phục hồi.

Trong Domain-Driven Design (DDD), **Domain Event** ghi nhận một sự việc nghiệp vụ đã xảy ra. Một thành phần khác có thể lắng nghe sự kiện và thực hiện phản ứng phù hợp. Tuy nhiên, việc một phản ứng được kích hoạt bởi event không có nghĩa mọi công việc nên chạy trong cùng transaction, hoặc mọi tác dụng phụ đều thuộc cùng Bounded Context.

Để thiết kế đúng, cần phân biệt ba ranh giới:

- **Ranh giới mô hình:** Bounded Context nào sở hữu khái niệm và quy tắc đang được thực hiện?
- **Ranh giới nhất quán:** Những thay đổi nào phải cùng được commit hoặc rollback để bảo vệ invariant?
- **Ranh giới tác dụng phụ:** Công việc nào thay đổi dữ liệu nội bộ, cập nhật mô hình đọc hoặc tác động đến hệ thống bên ngoài?

Một Domain Event có thể dẫn đến nhiều phản ứng. Có phản ứng cần hoàn tất trong transaction hiện tại; có phản ứng có thể chạy sau commit; có phản ứng phải được gửi bền vững sang context khác. Chọn đúng ranh giới giúp hệ thống giữ được sự thật nghiệp vụ khi xảy ra lỗi, retry hoặc cập nhật đồng thời.

Sau bài học này, bạn có thể:

- Giải thích cách Domain Event kích hoạt phản ứng trong cùng Bounded Context.
- Phân biệt xử lý đồng bộ trước commit, xử lý sau commit và xử lý bất đồng bộ.
- Xác định phản ứng nào cần nằm trong cùng transaction để bảo vệ invariant.
- Nhận diện tác dụng phụ ngoài transaction như email, HTTP call và message broker.
- Dùng Transactional Outbox khi cần bảo đảm ý định công bố được lưu cùng thay đổi domain.
- Thiết kế handler có khả năng xử lý duplicate, retry, thứ tự và lỗi.
- Phân biệt Domain Event với Integration Event và Process Manager.

## 1. Domain Event và event handler

Domain Event mô tả một sự việc đã xảy ra trong domain, chẳng hạn `OrderPlaced`, `PaymentCaptured`, `StockReserved` hoặc `SubscriptionCancelled`. Event handler là thành phần phản ứng khi sự kiện đó xuất hiện.

Ví dụ trong Sales Context:

```text
Order được đặt thành công
        |
        v
     OrderPlaced
        |
        +--> Cập nhật khoản mua chịu của Buyer
        |
        +--> Cập nhật Customer Order History
        |
        +--> Tạo yêu cầu gửi email xác nhận
        |
        +--> Công bố thông tin để Fulfillment xử lý
```

Các handler có thể phục vụ mục tiêu khác nhau. Cập nhật khoản mua chịu có thể ảnh hưởng trực tiếp đến quyết định cho phép đặt đơn tiếp theo. Customer Order History có thể chỉ là dữ liệu tổng hợp để tra cứu. Email là tác dụng phụ bên ngoài. Fulfillment có thể thuộc một Bounded Context khác.

Event handler không nhất thiết là một message consumer chạy trên broker. Nó có thể là một hàm được gọi trong cùng process, một listener của framework, một worker bất đồng bộ hoặc một consumer ở service khác. Cơ chế thực thi phải phù hợp với yêu cầu nhất quán và độ tin cậy của phản ứng.

### Event không phải lệnh điều khiển handler

Event nói điều gì đã xảy ra. Nó không nên mang ý nghĩa “hãy chạy handler X”. Một event có thể có nhiều consumer độc lập, và mỗi consumer quyết định phản ứng theo trách nhiệm của mình.

Ví dụ, `OrderPlaced` có thể được quan tâm bởi Sales, Customer Insights và Notification. Event không cần biết có bao nhiêu handler, handler nằm ở class nào hoặc công nghệ nào đang thực thi chúng.

## 2. Phân biệt ba loại ranh giới

Ba khái niệm thường bị nhầm lẫn khi thiết kế event-driven behavior.

| Ranh giới | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Bounded Context | Ai sở hữu mô hình và quy tắc? | Sales sở hữu Order; Inventory sở hữu Stock |
| Transaction boundary | Những thay đổi nào phải cùng commit/rollback? | Order và Buyer Exposure cùng cập nhật trong một transaction nếu invariant yêu cầu |
| Side-effect boundary | Tác động nào xảy ra ngoài thay đổi dữ liệu cục bộ? | Gửi email, publish message, gọi cổng thanh toán |

Hai Aggregate cùng Bounded Context không tự động phải nằm trong một transaction. Ngược lại, một use case có thể dùng một transaction cho nhiều Aggregate nếu chúng ở cùng transactional resource và nghiệp vụ yêu cầu atomicity. Bounded Context xác định ranh giới mô hình và quyền sở hữu; transaction boundary xác định ranh giới commit.

Tương tự, một event được xử lý trong cùng process không có nghĩa tác dụng phụ của handler cũng nằm trong transaction database. Gọi API gửi email từ một handler đồng bộ không thể được rollback cùng database nếu request email đã được nhà cung cấp chấp nhận.

## 3. Khi nào phản ứng nên nằm ngay trong Aggregate?

Không phải mọi thay đổi nội bộ đều cần Domain Event. Nếu một hành vi chỉ cập nhật trạng thái hoặc bảo vệ invariant bên trong cùng Aggregate, hãy thực hiện trực tiếp trong hành vi của Aggregate Root.

Ví dụ:

- `Order.place()` kiểm tra Order có dòng hàng hợp lệ rồi chuyển trạng thái sang `Placed`.
- `Order.cancel()` kiểm tra điều kiện hủy và chuyển trạng thái.
- `Subscription.renew()` cập nhật thời hạn thuê bao theo policy của chính Subscription.

Nếu `Order.place()` chỉ cần cập nhật `status` và `placedAt` của chính Order, không cần phát `OrderPlaced` rồi tạo handler chỉ để đặt lại chính những field đó. Event hữu ích khi sự việc cần được quan sát bởi một phần khác của domain, một projection hoặc một hệ thống tích hợp.

Một quy tắc đơn giản:

- Thay đổi thuộc nội bộ Aggregate và cần bảo vệ invariant của nó: đặt trong Aggregate.
- Sự việc cần được phần khác phản ứng: ghi nhận Domain Event.
- Quy tắc phối hợp nhiều đối tượng nhưng không có owner tự nhiên: cân nhắc Domain Service hoặc handler domain phù hợp.

## 4. Phản ứng trong cùng Bounded Context

Trong cùng một Bounded Context, handler có thể thực hiện các phản ứng thuộc cùng mô hình domain. Ví dụ, khi Order được đặt, Sales có thể cần ghi nhận phần hạn mức mua chịu đã sử dụng của Buyer Account.

Giả sử Sales có hai Aggregate:

- `Order` sở hữu các dòng hàng, giá đã chốt và trạng thái đơn.
- `BuyerAccount` sở hữu hạn mức mua chịu và khoản nghĩa vụ chưa thanh toán.

Khi đặt đơn, quy tắc có thể yêu cầu Buyer Account còn đủ hạn mức và khoản phơi nhiễm tín dụng phải được cập nhật cùng với Order. Handler của `OrderPlaced` có thể tải `BuyerAccount` và gọi hành vi domain `recordOrderExposure()`.

```text
Sales Application Service
       |
       v
Order.place()
       |
       v
Domain Event: OrderPlaced
       |
       v
Handler: RecordBuyerExposureOnOrderPlaced
       |
       v
BuyerAccount.recordOrderExposure(amount)
       |
       v
Commit cùng transaction (nếu policy yêu cầu atomicity)
```

Nếu hạn mức phải luôn chính xác ngay sau khi Order được chấp nhận, phản ứng này có thể cần chạy đồng bộ trong cùng transaction. Nếu handler thất bại vì Buyer Account không còn đủ hạn mức hoặc version conflict, toàn bộ use case phải rollback theo policy. Không được để Order đã được đặt nhưng khoản exposure bắt buộc lại không được ghi nhận.

Tuy nhiên, hãy cân nhắc liệu kiểm tra và cập nhật Buyer Account có nên được thực hiện trực tiếp bởi Domain Service trước khi Order chuyển trạng thái hay không. Nếu hành vi “đặt đơn trong hạn mức” là một quyết định liên đối tượng cốt lõi, một Domain Service có thể diễn đạt rõ hơn việc phối hợp; Domain Event sau đó ghi nhận sự thật `OrderPlaced`. Không nên dùng event handler để che giấu một quyết định cần hoàn tất trước khi event được phát.

### Phản ứng nội bộ không nhất thiết phải đồng bộ

Customer Order History có thể được xây dựng từ các event đã phát. Nếu đây chỉ là projection phục vụ tra cứu và có thể trễ vài giây, handler có thể chạy bất đồng bộ sau commit. Khi đó Sales vẫn có thể chấp nhận Order dù projection chưa cập nhật xong.

Điểm quyết định là hậu quả nếu phản ứng chưa hoàn thành:

- Nếu invariant hoặc cam kết nghiệp vụ bị vi phạm, phản ứng cần được bảo vệ đồng bộ hoặc bằng một cơ chế tương đương.
- Nếu chỉ có dữ liệu đọc tạm thời chưa mới, eventual consistency có thể chấp nhận.

## 5. Dispatch event trước commit

Một cách triển khai là thu thập Domain Event từ Aggregate, sau đó dispatch các event trong khi transaction hiện tại vẫn mở. Handler chạy đồng bộ và có thể tải/cập nhật Aggregate khác thông qua repository trong cùng transaction.

Luồng:

```text
BEGIN TRANSACTION
  Load Order
  Order.place()
  Collect OrderPlaced
  Dispatch Domain Event
    -> Load BuyerAccount
    -> BuyerAccount.recordOrderExposure()
  Save/flush các Aggregate thay đổi
COMMIT
```

Nếu handler ném lỗi và lỗi được truyền ra transaction boundary, transaction có thể rollback cả Order và BuyerAccount. Đây là lựa chọn phù hợp khi các thay đổi phải cùng được ghi nhận và cùng database transaction có thể bảo đảm điều đó.

### Ưu điểm

- Phản ứng hoàn thành trước khi use case báo thành công.
- Có thể dùng cùng transaction để rollback tất cả thay đổi nội bộ.
- Lỗi domain trong handler có thể ngăn commit một trạng thái không hợp lệ.
- Dễ hiểu khi quy tắc phối hợp cần consistency ngay lập tức.

### Chi phí và giới hạn

- Transaction dài hơn vì phải chạy thêm handler.
- Có thể tăng số Aggregate được tải và cập nhật trong một transaction.
- Tăng contention và nguy cơ optimistic locking conflict.
- Handler có thể tạo chuỗi phản ứng khó theo dõi.
- Một handler chậm làm use case chính chậm theo.
- Không rollback được tác dụng phụ đã xảy ra ở hệ thống bên ngoài.

Chỉ dispatch trước commit cho phản ứng thực sự cần thuộc cùng đơn vị công việc. Không nên gọi email, HTTP API hoặc message broker trực tiếp trong handler này nếu không có cơ chế bảo vệ phù hợp.

## 6. Dispatch event sau commit

Một lựa chọn khác là chỉ chạy handler sau khi transaction chứa thay đổi domain đã commit thành công.

Luồng:

```text
BEGIN TRANSACTION
  Load Order
  Order.place()
  Save Order
COMMIT
       |
       v
Dispatch after commit
  -> Update read projection
  -> Prepare notification
```

Nếu transaction rollback, handler sau commit không được chạy. Đây là cách phù hợp cho những phản ứng chỉ nên xảy ra khi sự kiện đã được ghi nhận thành công.

Tuy nhiên, dispatch sau commit trong bộ nhớ có một khoảng trống độ tin cậy:

1. Database commit thành công.
2. Process dừng trước khi handler chạy.
3. Order đã được đặt nhưng phản ứng bị mất.

Nếu phản ứng có thể được tạo lại hoặc không quan trọng, đây có thể là một giới hạn chấp nhận được. Nếu phải bảo đảm phản ứng sẽ được gửi, cần một cơ chế lưu ý định xử lý bền vững như Transactional Outbox.

### So sánh trước commit và sau commit

| Tiêu chí | Trước commit | Sau commit |
|---|---|---|
| Thời điểm handler | Trong transaction hiện tại | Sau khi transaction thành công |
| Rollback cùng dữ liệu gốc | Có thể, nếu cùng transaction/resource | Không; dữ liệu gốc đã commit |
| Phù hợp | Quy tắc cần atomicity | Projection, notification, phản ứng có thể trễ |
| Lỗi handler | Có thể làm use case rollback | Cần retry hoặc xử lý lỗi riêng |
| Độ dài transaction | Có thể tăng | Transaction gốc ngắn hơn |
| Rủi ro mất phản ứng | Nếu lỗi làm rollback, không có event được commit | Có thể mất nếu process dừng sau commit trước dispatch |

Không có lựa chọn đúng cho mọi handler. Hãy phân loại theo yêu cầu domain và độ tin cậy cần có.

## 7. Cùng Bounded Context không đồng nghĩa cùng transaction

Một Bounded Context có thể có nhiều Aggregate với vòng đời và invariant độc lập. Dù cùng dùng một database, không phải mọi phản ứng đều cần cùng transaction.

Ví dụ trong Sales:

- `Order` được đặt.
- `BuyerAccount` cập nhật hạn mức đang sử dụng.
- `CustomerOrderHistory` cập nhật projection.
- `SalesDashboard` cập nhật số liệu tổng hợp.

Nếu hạn mức là invariant quyết định có thể đặt đơn tiếp theo hay không, cập nhật BuyerAccount có thể cần đồng bộ. Lịch sử mua hàng và dashboard có thể cập nhật bất đồng bộ.

Việc đưa tất cả vào một transaction chỉ để “đỡ phức tạp” có thể làm use case chậm, tăng contention và khiến dashboard không sẵn sàng cũng làm khách không đặt được hàng. Ngược lại, tách một cập nhật quan trọng sang eventual consistency có thể khiến hệ thống chấp nhận vượt hạn mức.

Hãy đặt câu hỏi cho từng phản ứng:

- Nếu phản ứng thất bại, command gốc có được phép thành công không?
- Có thể chấp nhận trạng thái trung gian trong bao lâu?
- Có thể tính lại hoặc dựng lại phản ứng từ event không?
- Có cần bảo đảm thứ tự so với event khác không?
- Phản ứng có tác động đến invariant của Aggregate nào?
- Có cần retry bền vững và quan sát được không?

## 8. Phân loại phản ứng theo tác dụng

Một cách hữu ích là chia các phản ứng thành bốn nhóm.

### 8.1. Thay đổi domain state trong cùng context

Handler thực hiện một hành vi nghiệp vụ trên Aggregate khác trong cùng Bounded Context. Ví dụ, `OrderPlaced` làm tăng khoản exposure của Buyer Account.

Nếu hai Aggregate phải cùng thay đổi để giữ invariant, handler có thể chạy đồng bộ trong cùng transaction hoặc use case có thể dùng Domain Service để phối hợp trước khi phát event. Cần concurrency control cho từng Aggregate và rollback toàn bộ nếu yêu cầu atomicity.

### 8.2. Cập nhật read model hoặc projection

Handler tạo dữ liệu phục vụ đọc, tìm kiếm, báo cáo hoặc dashboard. Ví dụ, `OrderPlaced` làm tăng số đơn của khách trong Customer Order History.

Projection thường có thể được cập nhật sau commit và chấp nhận eventual consistency. Nếu handler lỗi, hệ thống có thể retry hoặc rebuild từ event/log nguồn, tùy kiến trúc.

### 8.3. Tác dụng phụ hạ tầng hoặc bên ngoài

Ví dụ:

- Gửi email hoặc SMS.
- Gọi API của cổng thanh toán.
- Yêu cầu nhà vận chuyển tạo shipment.
- Publish message lên broker.
- Gửi webhook cho đối tác.

Những thao tác này không thể rollback cùng database transaction. Cần idempotency, retry, outbox, trạng thái tiến trình hoặc đối soát tùy mức độ quan trọng.

### 8.4. Điều phối quy trình dài

Nếu phản ứng cần chờ nhiều event, theo dõi trạng thái qua thời gian hoặc phát command đến nhiều context, đó có thể là trách nhiệm của Process Manager/Saga. Handler chỉ nhận event và cập nhật tiến trình; Process Manager quyết định bước tiếp theo theo trạng thái hiện tại.

## 9. Domain Event và Integration Event

Domain Event diễn đạt sự việc trong mô hình của một Bounded Context. Integration Event là hợp đồng được công bố để context hoặc hệ thống khác phản ứng.

Không nhất thiết phải gửi nguyên Domain Event nội bộ ra broker. Event nội bộ có thể chứa dữ liệu phục vụ logic riêng của context hoặc thay đổi theo mô hình nội bộ. Khi công bố ra ngoài, context nên ánh xạ sang contract có chủ đích.

Ví dụ:

```text
Domain Event nội bộ của Sales:
  OrderPlaced
    - orderId
    - buyerId
    - acceptedPriceBreakdown
    - internalSalesPolicyId

Integration Event công bố:
  SalesOrderAccepted
    - orderReference
    - acceptedAt
    - fulfillmentLines (sku, quantity)
    - deliveryAddressSnapshot
```

Fulfillment cần mã hàng, số lượng và địa chỉ giao đã chốt. Nó không cần biết policy nội bộ hoặc cấu trúc chi tiết của Sales Aggregate.

| Tiêu chí | Domain Event | Integration Event |
|---|---|---|
| Phạm vi | Nội bộ Bounded Context | Qua ranh giới context/hệ thống |
| Ngôn ngữ | Mô hình domain phát sinh | Contract dành cho consumer |
| Payload | Dữ liệu cần cho phản ứng nội bộ | Dữ liệu tối thiểu đã công bố |
| Thay đổi | Theo tiến hóa mô hình nội bộ | Cần quản lý tương thích và versioning |
| Phân phối | In-process hoặc cơ chế nội bộ | Broker, API, webhook hoặc message transport |

Một Domain Event có thể dẫn đến Integration Event, nhưng việc chuyển đổi cần được thực hiện có chủ đích. Không công bố mọi event nội bộ chỉ vì đã có event dispatcher.

## 10. Transactional Outbox bảo vệ ý định công bố

Giả sử Sales cần lưu Order và gửi `SalesOrderAccepted` sang Fulfillment. Có hai cách ngây thơ đều có thể tạo lỗi.

**Commit trước rồi publish:** database commit thành công, nhưng process dừng trước khi publish. Fulfillment không nhận được thông tin.

**Publish trước rồi commit:** message được gửi, nhưng transaction database rollback. Fulfillment xử lý một Order chưa thực sự được chấp nhận.

Transactional Outbox ghi thay đổi domain và thông điệp cần công bố trong cùng database transaction:

```text
BEGIN TRANSACTION
  Save Order
  Insert OutboxMessage(SalesOrderAccepted)
COMMIT

Outbox Publisher
  Read pending message
  Publish to broker
  Mark as published
```

Nếu transaction rollback, cả Order và outbox record đều không được commit. Nếu commit thành công, outbox record tồn tại để publisher gửi lại kể cả sau khi process khởi động lại.

### Outbox không bảo đảm exactly-once delivery

Publisher có thể gửi message thành công nhưng process dừng trước khi đánh dấu record đã gửi. Khi khởi động lại, publisher có thể gửi lại cùng message. Vì vậy, outbox thường cung cấp khả năng giao ít nhất một lần (*at-least-once delivery*) khi được triển khai đúng; consumer phải xử lý duplicate.

Một outbox record thường cần:

- `messageId` hoặc `eventId` duy nhất.
- Loại event và schema version.
- Payload đã serialize.
- Thời điểm tạo và thời điểm gửi.
- Trạng thái hoặc checkpoint gửi.
- Correlation/causation reference nếu cần theo dõi flow.

Không nên giữ outbox record vô thời hạn mà không có chính sách archive/cleanup. Cần metric cho message tồn đọng, số lần retry và thời gian chờ lâu nhất.

## 11. Idempotency của event handler

Khi handler có thể được gọi nhiều lần cho cùng một event, nó cần có khả năng xử lý lặp an toàn (*idempotent*) hoặc có cơ chế deduplication.

Ví dụ, `OrderPlaced` làm tăng `BuyerAccount.outstandingExposure` thêm 500.000 VND. Nếu cùng event được xử lý hai lần, số exposure có thể tăng thành 1.000.000 VND. Đây là lỗi nghiệp vụ.

Một chiến lược phổ biến là lưu event ID đã xử lý trong cùng transaction với thay đổi mà handler thực hiện:

```text
BEGIN TRANSACTION
  Try insert ProcessedMessage(eventId)
  If duplicate:
      do nothing and return
  Else:
      Load BuyerAccount
      BuyerAccount.recordOrderExposure(amount)
      Save BuyerAccount
COMMIT
```

Ràng buộc unique trên `eventId` giúp hai consumer cạnh tranh không cùng xử lý thành công một message. Việc ghi dấu đã xử lý và thay đổi domain cần cùng transaction; nếu ghi dấu trước rồi thay đổi thất bại nhưng transaction không rollback cả hai, event có thể bị đánh dấu xong dù chưa áp dụng.

### Idempotency key và business reference

Không phải lúc nào cũng cần một bảng inbox riêng. Một số domain có thể dùng reference duy nhất như `orderId` trong bảng exposure hoặc reservation để ngăn tạo trùng. Chọn cách phù hợp với invariant và cách truy vấn.

Ví dụ, Buyer Account có thể lưu các khoản exposure theo `orderId` và áp dụng unique constraint cho mỗi Order. Khi event được gửi lại, thao tác ghi nhận cùng `orderId` không tạo khoản exposure thứ hai.

Idempotency không có nghĩa mọi lần gọi lặp đều trả cùng response một cách tự động. Nó có nghĩa lặp lại cùng ý định không làm phát sinh tác động nghiệp vụ ngoài dự kiến.

## 12. Thứ tự event và xử lý message đến muộn

Một handler có thể nhận event trễ hoặc không theo đúng thứ tự phát sinh, nhất là khi có nhiều worker, retry hoặc broker partition.

Ví dụ:

```text
SubscriptionRenewed (version 8)
SubscriptionSuspended (version 9)
```

Nếu consumer nhận `SubscriptionSuspended` trước rồi mới nhận `SubscriptionRenewed`, một projection ngây thơ có thể hiển thị thuê bao đã hoạt động trở lại dù event mới hơn thực tế là suspended.

Một số cách xử lý:

- Dùng aggregate version hoặc sequence để phát hiện event cũ.
- Duy trì thứ tự theo aggregate key nếu broker hỗ trợ partition/order key.
- Consumer kiểm tra version trước khi áp dụng event vào projection.
- Khi phát hiện gap hoặc thiếu event, tải snapshot hoặc thực hiện reconciliation theo policy.
- Không giả định có một thứ tự toàn cục giữa mọi aggregate.

Timestamp hữu ích để quan sát nhưng không luôn là thứ tự đáng tin cậy vì đồng hồ có thể lệch hoặc message đến muộn. Nếu thứ tự nghiệp vụ quan trọng, hãy dùng sequence/version do nguồn sở hữu.

## 13. Tránh vòng lặp event và phản ứng dây chuyền khó kiểm soát

Một handler có thể phát ra event khác khi thực hiện hành vi domain. Điều này bình thường nếu chuỗi phản ứng có ý nghĩa nghiệp vụ rõ ràng. Nhưng nếu các handler liên tục kích hoạt lẫn nhau, hệ thống có thể tạo vòng lặp.

Ví dụ không tốt:

```text
CustomerUpdated
    -> Handler A cập nhật Customer
    -> phát CustomerUpdated
    -> Handler A chạy lại
    -> ...
```

Nguyên nhân có thể là handler phát lại event chỉ vì lưu object, hoặc hai handler thay đổi qua lại cùng một trạng thái.

Để hạn chế:

- Chỉ phát Domain Event khi có một sự việc nghiệp vụ mới thực sự xảy ra.
- Không phát event chỉ vì ORM gọi `save()` hoặc một field kỹ thuật được cập nhật.
- Đặt tên event theo kết quả cụ thể, tránh một event chung như `EntityUpdated` cho mọi thay đổi.
- Dùng `correlationId` và `causationId` để theo dõi chuỗi phản ứng.
- Thiết kế handler idempotent và giới hạn retry.
- Kiểm tra xem hai handler có đang sở hữu cùng một quy tắc hay không.
- Nếu chuỗi bước có trạng thái và tiến trình riêng, mô hình hóa Process Manager/Saga thay vì tạo nhiều listener ẩn.

## 14. Handler nên nhỏ và có trách nhiệm rõ

Một event có thể có nhiều handler, nhưng mỗi handler nên thực hiện một phản ứng có tên và mục đích cụ thể.

Ví dụ:

- `RecordBuyerExposureOnOrderPlaced`.
- `UpdateCustomerOrderSummaryOnOrderPlaced`.
- `ScheduleOrderConfirmationEmail`.
- `StartFulfillmentProcessOnSalesOrderAccepted`.

Tránh một handler lớn như `OrderPlacedHandler` vừa cập nhật tín dụng, vừa gửi email, gọi Inventory, cập nhật dashboard và ghi log. Khi một bước thất bại, rất khó xác định phần nào đã hoàn thành và phần nào cần retry.

Một handler nên:

- Nhận một event cụ thể.
- Kiểm tra event có thuộc trách nhiệm của nó không.
- Tải Aggregate cần thiết qua repository của context sở hữu.
- Gọi hành vi domain hoặc query/projection logic phù hợp.
- Ghi kết quả trong transaction phù hợp.
- Xử lý duplicate, lỗi và retry theo contract.

Handler không nên trực tiếp sửa field nội bộ của Aggregate hoặc dùng repository của context khác để thay đổi dữ liệu ngoài quyền sở hữu.

## 15. Event handler và Application Service

Event handler thường là một entry point cho phản ứng, nhưng nó không thay thế Application Service hoặc Domain Service.

| Thành phần | Trách nhiệm |
|---|---|
| Aggregate | Thay đổi state và bảo vệ invariant cục bộ |
| Domain Event | Ghi nhận sự việc đã xảy ra |
| Event Handler | Tiếp nhận event và kích hoạt phản ứng cụ thể |
| Domain Service | Thực hiện quy tắc domain phối hợp nhiều đối tượng |
| Application Service | Điều phối use case, repository và transaction |
| Process Manager/Saga | Theo dõi quy trình dài, trạng thái chờ và compensation |
| Infrastructure adapter | Gửi email, gọi HTTP, publish message, truy cập broker |

Một handler có thể gọi Application Service hoặc một use case chuyên biệt, nhưng hãy tránh tạo chuỗi handler -> service -> handler khó theo dõi. Nếu phản ứng chỉ là một hành vi domain nhỏ, handler có thể tải Aggregate rồi gọi hành vi đó trực tiếp. Nếu nó là một quy trình có nhiều bước, một Application Service hoặc Process Manager có tên rõ ràng sẽ phù hợp hơn.

## 16. Tác dụng phụ bên ngoài phải có ranh giới riêng

Một database transaction chỉ có thể rollback những thay đổi thuộc transactional resource mà nó quản lý. Nó không thể thu hồi email đã gửi, HTTP request đã được đối tác xử lý hoặc message đã được consumer nhận.

Ví dụ:

```text
BEGIN TRANSACTION
  Order.place()
  SendEmail("Order confirmed")
  Save Order
ROLLBACK
```

Nếu email đã được gửi trước khi rollback, khách nhận xác nhận cho một Order chưa được ghi nhận. Database không thể “hoàn tác” email.

Các tác dụng phụ bên ngoài thường nên được lên lịch sau commit bằng outbox hoặc cơ chế bền vững tương đương. Consumer/publisher xử lý retry và idempotency.

### Gửi email

Thay vì gọi email provider trực tiếp trong handler đồng bộ trước commit, có thể ghi `OrderConfirmationRequested` vào outbox. Worker đọc message, gửi email và lưu trạng thái gửi. Nếu worker dừng giữa chừng, nó có thể retry theo idempotency key hoặc kiểm tra trạng thái provider nếu được hỗ trợ.

### Gọi cổng thanh toán

Không nên gọi `capturePayment()` rồi kỳ vọng rollback database sẽ hoàn lại giao dịch nếu commit thất bại. Thanh toán có trạng thái và quy trình riêng. Dùng idempotency key, lưu payment intent/reference, xử lý kết quả không xác định và đối soát với provider.

### Gọi Inventory hoặc Fulfillment

Nếu Inventory là Bounded Context riêng, Sales nên công bố Integration Event hoặc gửi command theo contract. Process Manager theo dõi `StockReserved`, `StockUnavailable` và các kết quả liên quan để cập nhật tiến trình Order.

## 17. Ví dụ Java: thu thập Domain Event từ Aggregate

Một Aggregate có thể ghi nhận event trong quá trình thực hiện hành vi. Event được lấy ra ở application boundary để dispatch hoặc chuyển thành outbox message.

```java
import java.time.Instant;
import java.util.UUID;

public interface DomainEvent {
    UUID eventId();
    Instant occurredAt();
}

public record OrderPlaced(
        UUID eventId,
        OrderId orderId,
        BuyerId buyerId,
        Money total,
        Instant occurredAt
) implements DomainEvent {}
```

Aggregate minh họa:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class Order {
    private final OrderId id;
    private final BuyerId buyerId;
    private final List<OrderLine> lines;
    private final List<DomainEvent> pendingEvents = new ArrayList<>();
    private OrderStatus status;

    public void place(Instant now) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only a draft order can be placed");
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException("Order must contain a line");
        }

        status = OrderStatus.PLACED;
        pendingEvents.add(new OrderPlaced(
            UUID.randomUUID(), id, buyerId, total(), now
        ));
    }

    public List<DomainEvent> pullDomainEvents() {
        List<DomainEvent> events = List.copyOf(pendingEvents);
        pendingEvents.clear();
        return events;
    }
}
```

Đoạn code là minh họa. Trong triển khai thực tế, cần cân nhắc serialization, cách khôi phục pending event sau khi nạp Aggregate, event ID, thứ tự event và cách event được lưu cùng transaction. `pullDomainEvents()` nên được gọi ở application/persistence boundary, không để code bên ngoài sửa collection event của Aggregate.

`eventId` được tạo một lần khi sự kiện được ghi nhận và phải được giữ nguyên khi đưa vào outbox hoặc retry. Không tạo ID mới cho mỗi lần publisher gửi lại, vì consumer cần nhận diện các lần giao lặp là cùng một sự kiện.

## 18. Ví dụ dispatch đồng bộ trong cùng transaction

Nếu `OrderPlaced` phải cập nhật Buyer Account ngay trong cùng transaction, application service có thể dispatch event trước commit:

```java
import java.util.List;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void placeOrder(OrderId orderId) {
    Order order = orders.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    order.place(clock.instant());
    orders.save(order);

    List<DomainEvent> events = order.pullDomainEvents();
    eventDispatcher.dispatch(events);
}
```

Handler:

```java
public interface DomainEventHandler<E extends DomainEvent> {
    void handle(E event);
}

public final class RecordBuyerExposureOnOrderPlaced
        implements DomainEventHandler<OrderPlaced> {

    private final BuyerAccountRepository buyers;

    @Override
    public void handle(OrderPlaced event) {
        BuyerAccount buyer = buyers.findById(event.buyerId())
            .orElseThrow(BuyerAccountNotFoundException::new);

        buyer.recordOrderExposure(event.orderId(), event.total());
        buyers.save(buyer);
    }
}
```

Trong ví dụ này, handler chạy đồng bộ trên transaction hiện tại nếu framework và repository được cấu hình tham gia cùng transaction. Nếu handler ném lỗi, exception phải được truyền ra ngoài để transaction rollback khi phản ứng là bắt buộc. Nếu handler bắt lỗi rồi bỏ qua, Order có thể được commit mà không cập nhật Buyer Account.

Với Spring, mặc định transaction rollback cho unchecked exception (`RuntimeException` và `Error`); checked exception cần cấu hình `rollbackFor` nếu cũng phải làm rollback. Ví dụ này giả định lỗi domain là unchecked exception hoặc transaction được cấu hình rollback tương ứng.

Việc dispatch trước commit không có nghĩa mọi handler được phép gọi hệ thống ngoài. Handler này chỉ thay đổi dữ liệu nội bộ trong cùng transactional resource. Cũng cần optimistic locking hoặc cơ chế concurrency phù hợp cho Buyer Account.

## 19. Ví dụ ghi Outbox cùng thay đổi domain

Với phản ứng cần chạy sau commit hoặc được gửi sang hệ thống khác, application service có thể chuyển event thành outbox message trong transaction:

```java
import java.util.List;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void placeOrder(OrderId orderId) {
    Order order = orders.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    order.place(clock.instant());
    orders.save(order);

    for (DomainEvent event : order.pullDomainEvents()) {
        outbox.add(OutboxMessage.from(event));
    }
}
```

Sau commit, publisher đọc outbox và gửi message. Với Integration Event, adapter nên ánh xạ Domain Event sang contract công bố:

```java
public IntegrationMessage toIntegrationMessage(OrderPlaced event) {
    return new SalesOrderAccepted(
        event.eventId(),
        1, // schemaVersion
        event.orderId().value(),
        event.total().amount(),
        event.total().currency().getCurrencyCode(),
        event.occurredAt()
    );
}
```

Đây là ví dụ giản lược; contract thật cần dữ liệu consumer cần, schema version, event ID và các reference phù hợp. Không nên công bố object domain trực tiếp nếu điều đó làm consumer phụ thuộc vào cấu trúc nội bộ.

## 20. Lỗi handler và chính sách phục hồi

Không nên xử lý mọi lỗi handler theo một cách. Hãy xác định loại phản ứng và hậu quả khi thất bại.

| Phản ứng | Nếu thất bại | Chiến lược phù hợp |
|---|---|---|
| Cập nhật Aggregate để bảo vệ invariant bắt buộc | Không thể chấp nhận trạng thái thiếu cập nhật | Rollback transaction hoặc phối hợp bằng cơ chế nhất quán tương đương |
| Cập nhật projection | Có thể chấp nhận trễ | Retry, rebuild hoặc replay nguồn dữ liệu |
| Gửi email xác nhận | Order vẫn có thể đã được đặt | Outbox, retry, trạng thái gửi và dead-letter khi cần |
| Gửi Integration Event | Consumer có thể không biết sự việc | Outbox, retry, monitoring và idempotency |
| Gọi payment provider | Kết quả có thể không xác định | Idempotency key, tra cứu trạng thái và reconciliation |
| Chạy bước Saga | Quy trình có thể ở trạng thái trung gian | Process Manager, retry và compensation |

Một handler bất đồng bộ cần chính sách retry có giới hạn, backoff, dead-letter hoặc cơ chế xử lý ngoại lệ. Retry vô hạn có thể làm một message lỗi chặn hàng đợi hoặc gây tải quá mức. Với phản ứng quan trọng, cần metric và cảnh báo để người vận hành biết message đang tồn đọng.

## 21. Quan sát và truy vết chuỗi phản ứng

Khi một event kích hoạt nhiều handler, cần có khả năng trả lời:

- Event nào đã phát sinh từ command nào?
- Handler nào đã xử lý event?
- Handler hoàn thành hay thất bại?
- Có retry bao nhiêu lần?
- Event có bị xử lý trùng không?
- Phản ứng nào đang chờ hoặc bị đưa vào dead-letter?

Các metadata hữu ích gồm:

| Metadata | Mục đích |
|---|---|
| `eventId` | Nhận diện một event duy nhất |
| `aggregateId` | Xác định Aggregate phát sinh event |
| `aggregateVersion` | Theo dõi thứ tự thay đổi của Aggregate |
| `occurredAt` | Thời điểm sự việc xảy ra theo nguồn domain |
| `recordedAt` | Thời điểm event được lưu nhận |
| `correlationId` | Nhóm các bước thuộc cùng một flow |
| `causationId` | Truy ngược command/event gây ra event hiện tại |
| `handlerName` | Nhận diện consumer đã xử lý |
| `attempt` | Theo dõi số lần thử xử lý |

Không nên đưa dữ liệu cá nhân hoặc toàn bộ Aggregate vào log chỉ để dễ debug. Chỉ ghi metadata cần thiết và áp dụng chính sách bảo vệ dữ liệu của hệ thống.

## 22. Những sai lầm thường gặp

**Phát event cho mọi thay đổi kỹ thuật.** Event nên diễn đạt sự việc có ý nghĩa domain, không phải mọi lần ORM flush hoặc mọi field được cập nhật.

**Dùng event handler thay cho hành vi trong Aggregate.** Nếu thay đổi chỉ thuộc nội bộ Aggregate, hãy thực hiện trực tiếp trong hành vi của nó.

**Cho rằng cùng Bounded Context thì luôn cùng transaction.** Cùng context chỉ nói về phạm vi mô hình và ngôn ngữ; transaction phải dựa trên invariant và consistency requirement.

**Dispatch trước commit rồi gọi email hoặc HTTP.** Tác dụng phụ có thể xảy ra dù database rollback. Hãy dùng outbox hoặc cơ chế bền vững sau commit.

**Dispatch sau commit trong bộ nhớ và cho rằng không mất event.** Process có thể dừng sau commit trước khi handler chạy. Nếu cần bảo đảm, hãy lưu ý định xử lý trong outbox cùng transaction.

**Một handler làm quá nhiều việc.** Nhiều phản ứng không liên quan bị gộp khiến lỗi và retry khó kiểm soát. Tách handler theo trách nhiệm.

**Không xử lý duplicate.** Broker và publisher có thể giao lại message. Handler phải idempotent hoặc deduplicate.

**Giả định event luôn đến đúng thứ tự.** Retry và phân phối song song có thể làm event đến muộn hoặc đảo thứ tự. Dùng sequence/version khi thứ tự quan trọng.

**Để handler sửa dữ liệu context khác.** Mỗi context phải sở hữu Aggregate và invariant của mình. Hãy dùng Integration Event hoặc contract.

**Tạo vòng lặp handler.** Một handler phát lại event cũ hoặc hai handler kích hoạt lẫn nhau có thể tạo chuỗi vô hạn. Chỉ phát event cho sự việc nghiệp vụ mới và theo dõi causation.

**Không mô hình hóa trạng thái tiến trình.** Quy trình dài cần trạng thái chờ, thất bại, retry và compensation; một chuỗi listener không thay thế Process Manager.

## 23. Quy trình thiết kế phản ứng từ một Domain Event

Khi có một event mới, hãy thực hiện các bước sau:

**Bước 1: Xác nhận sự việc.** Event mô tả điều gì đã xảy ra, do Aggregate nào phát sinh và khi nào được xem là sự thật?

**Bước 2: Liệt kê consumer.** Phần nào trong cùng context cần phản ứng? Có context hoặc hệ thống ngoài nào cần thông tin không?

**Bước 3: Phân loại từng phản ứng.** Thay đổi domain state, cập nhật projection, tác dụng phụ bên ngoài hay điều phối quy trình dài?

**Bước 4: Xác định invariant.** Nếu phản ứng thất bại, command gốc có được phép thành công không? Những thay đổi nào phải cùng commit?

**Bước 5: Chọn thời điểm dispatch.** Trước commit cho phản ứng nội bộ cần atomicity; sau commit cho phản ứng độc lập; outbox cho phản ứng cần giao bền vững.

**Bước 6: Xác định contract.** Event nội bộ có đủ dữ liệu không? Consumer ngoài cần Integration Event nào? Có cần snapshot hay chỉ reference?

**Bước 7: Thiết kế idempotency và ordering.** Event ID, unique constraint, aggregate version, correlation/causation và thứ tự theo key.

**Bước 8: Thiết kế failure path.** Retry, backoff, dead-letter, reconciliation, compensation hoặc thông báo cho người dùng.

**Bước 9: Kiểm tra ranh giới context.** Không để handler truy cập trực tiếp mô hình hoặc database nội bộ của context khác.

**Bước 10: Kiểm thử toàn flow.** Bao gồm rollback, crash sau commit, duplicate delivery, event đến muộn và handler thất bại.

## 24. Checklist cho Domain Event handler

- [ ] Event diễn đạt một sự việc nghiệp vụ đã xảy ra.
- [ ] Aggregate phát event sau khi hành vi domain hợp lệ.
- [ ] Handler có tên và trách nhiệm rõ ràng.
- [ ] Hành vi thuộc nội bộ Aggregate vẫn nằm trên Aggregate Root.
- [ ] Phản ứng được phân loại theo domain state, projection, side effect hoặc process.
- [ ] Transaction boundary dựa trên invariant, không dựa riêng vào Bounded Context.
- [ ] Handler chạy trước commit chỉ thực hiện việc có thể tham gia cùng transaction.
- [ ] Side effect bên ngoài không được giả định là rollback cùng database.
- [ ] Phản ứng cần giao bền vững được ghi qua Outbox hoặc cơ chế tương đương.
- [ ] Consumer có idempotency hoặc deduplication.
- [ ] Thứ tự event được xử lý bằng version/sequence khi cần.
- [ ] Có correlation/causation để truy vết chuỗi phản ứng.
- [ ] Retry có giới hạn và có xử lý dead-letter/reconciliation phù hợp.
- [ ] Handler không sửa trực tiếp Aggregate thuộc Bounded Context khác.
- [ ] Có test cho rollback, duplicate, retry và lỗi ngoài hệ thống.

## 25. Bài tập tự kiểm tra

Một hệ thống thương mại điện tử phát sinh `OrderPlaced` sau khi Sales chấp nhận đơn. Các phản ứng được yêu cầu:

1. Ghi nhận khoản mua chịu của Buyer Account trong Sales.
2. Cập nhật lịch sử mua hàng để màn hình khách hàng hiển thị số đơn mới.
3. Gửi email xác nhận đơn.
4. Yêu cầu Inventory giữ hàng.
5. Cập nhật dashboard doanh thu trong ngày.

Hãy phân loại từng phản ứng và trả lời:

- Phản ứng nào có thể cần nằm trong cùng transaction với việc đặt Order?
- Phản ứng nào có thể chạy sau commit và chấp nhận eventual consistency?
- Phản ứng nào nên dùng Outbox?
- Inventory cần nhận Domain Event nội bộ hay Integration Event?
- Nếu email gửi thành công nhưng worker dừng trước khi ghi nhận kết quả, cần làm gì để tránh gửi trùng ngoài ý muốn?
- Nếu `OrderPlaced` được giao hai lần, làm sao tránh tăng khoản mua chịu hai lần?
- Nếu dashboard chưa cập nhật, Order có nên bị rollback không?

Gợi ý:

| Phản ứng | Phân loại | Cách xử lý có thể phù hợp |
|---|---|---|
| Ghi nhận Buyer Exposure | Domain state trong Sales | Cùng transaction nếu hạn mức là invariant cần cập nhật tức thời; có thể phối hợp bằng Domain Service trước khi phát event |
| Cập nhật lịch sử mua hàng | Read projection | Sau commit, retry/rebuild nếu lỗi |
| Gửi email | Tác dụng phụ bên ngoài | Outbox và worker; idempotency/provider reference nếu hỗ trợ |
| Yêu cầu Inventory giữ hàng | Tích hợp Bounded Context | Integration Event/command qua contract, Outbox và Process Manager nếu flow cần theo dõi |
| Cập nhật dashboard | Projection/reporting | Bất đồng bộ, có thể trễ và có khả năng rebuild |

Nếu dashboard chưa cập nhật, thường không cần rollback Order vì đây là dữ liệu đọc tổng hợp. Nếu Inventory chưa giữ được hàng, kết quả phụ thuộc policy: Order có thể ở trạng thái `PendingStock`, chuyển sang `Rejected` hoặc chạy quy trình bù trừ. Không nên giả định mọi phản ứng đều phải thành công trong cùng một transaction.

## Kết luận

Domain Event cho phép các phần khác trong mô hình phản ứng với một sự việc nghiệp vụ đã xảy ra. Nhưng event không quyết định sẵn phản ứng phải đồng bộ, bất đồng bộ hay nằm trong cùng transaction. Hãy phân loại phản ứng theo trách nhiệm domain, invariant và tác dụng phụ thực tế.

Phản ứng nội bộ cần bảo vệ invariant có thể phải chạy trước commit trong cùng transaction, hoặc được phối hợp bằng một use case/Domain Service rõ ràng. Projection và thông báo có thể chạy sau commit nếu chấp nhận eventual consistency. Tác dụng phụ bên ngoài cần cơ chế bền vững như Transactional Outbox, idempotency và retry. Khi quy trình đi qua Bounded Context hoặc kéo dài nhiều bước, Integration Event và Process Manager/Saga giúp giữ quyền sở hữu mô hình và quản lý trạng thái trung gian. Thiết kế handler nhỏ, có thể truy vết và có chính sách lỗi rõ ràng giúp event-driven behavior đáng tin cậy hơn.
