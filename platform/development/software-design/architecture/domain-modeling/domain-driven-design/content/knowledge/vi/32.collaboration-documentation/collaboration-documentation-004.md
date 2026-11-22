# Quản lý Context Map, bảng thuật ngữ và ví dụ nghiệp vụ cùng mã nguồn

Domain-Driven Design (DDD) cần sự cộng tác liên tục giữa chuyên gia nghiệp vụ, developer, tester, kiến trúc sư và những nhóm sở hữu các Bounded Context khác nhau. Mô hình miền chỉ hữu ích khi mọi người hiểu cùng một ý nghĩa, biết ranh giới trách nhiệm và có thể lần theo một quy tắc nghiệp vụ đến cách nó được thực thi trong hệ thống.

Ba loại tài liệu giúp duy trì sự hiểu biết đó là **Context Map**, **bảng thuật ngữ (glossary/Ubiquitous Language)** và **ví dụ nghiệp vụ**. Context Map cho biết các mô hình và nhóm liên hệ với nhau thế nào. Glossary làm rõ một thuật ngữ có nghĩa gì trong từng context. Ví dụ nghiệp vụ cho thấy quy tắc tạo ra kết quả nào trong tình huống cụ thể. Khi các tài liệu này được liên kết với code, API contract và test, chúng trở thành một phần có thể kiểm chứng của quá trình phát triển thay vì những ghi chú dễ bị bỏ quên.

Bài học này trình bày cách xây dựng, sử dụng và duy trì ba loại tài liệu trên trong một nhóm DDD. Ví dụ xuyên suốt dùng nền tảng thương mại điện tử với Sales, Inventory, Payments và Delivery; tên context và quy tắc minh họa cần được điều chỉnh theo ngôn ngữ thực tế của tổ chức.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò khác nhau của Context Map, glossary và business examples.
- Tổ chức workshop để khám phá context, quan hệ upstream/downstream và hợp đồng tích hợp.
- Ghi lại ý nghĩa thuật ngữ theo từng Bounded Context thay vì ép một định nghĩa toàn cục.
- Dùng ví dụ, phản ví dụ và bảng quyết định để làm rõ quy tắc nghiệp vụ.
- Liên kết thuật ngữ và ví dụ với Aggregate, package, API, event schema và test.
- Xác định người sở hữu, trạng thái, phiên bản và thời điểm review của từng tài liệu.
- Giữ tài liệu gần code bằng docs-as-code và quy trình review.
- Phát hiện tài liệu lỗi thời, mâu thuẫn hoặc không còn phản ánh hành vi hệ thống.
- Giải quyết bất đồng thuật ngữ giữa các nhóm mà vẫn giữ ranh giới mô hình.
- Tạo traceability từ câu hỏi nghiệp vụ đến quyết định và kiểm thử.

## 1. Ba loại tài liệu giải quyết ba câu hỏi khác nhau

Không nên gom mọi thứ vào một sơ đồ kiến trúc hoặc một trang wiki dài. Mỗi loại tài liệu phục vụ một câu hỏi riêng và cần liên kết với nhau.

| Artifact | Câu hỏi chính | Nội dung cần ghi | Người dùng chính |
| --- | --- | --- | --- |
| Context Map | Các Bounded Context liên hệ và phụ thuộc nhau thế nào? | Boundary, quan hệ, upstream/downstream, contract, cơ chế tích hợp, owner | Domain expert, architect, team leads, developers |
| Glossary / Ubiquitous Language | Một thuật ngữ có nghĩa gì trong context này? | Định nghĩa, ví dụ, phản ví dụ, từ đồng nghĩa, tên trong code/API | Toàn bộ nhóm và stakeholder |
| Business Examples | Quy tắc được áp dụng thế nào trong tình huống cụ thể? | Given/When/Then, decision table, dữ liệu đầu vào, kết quả, ngoại lệ | Domain expert, developer, tester, product owner |

Ba artifact này bổ sung cho nhau:

- Context Map cho biết Sales nhận kết quả giữ hàng từ Inventory qua một hợp đồng tích hợp.
- Glossary giải thích Reservation là cam kết giữ một lượng hàng trong thời hạn, còn Order là yêu cầu mua do Sales sở hữu.
- Business Example chỉ ra khi nào Order được chuyển sang PENDING_CONFIRMATION, khi nào được CONFIRMED và điều gì xảy ra nếu reservation hết hạn.

Một tài liệu không thay thế được hai tài liệu còn lại. Context Map không giải thích hết mọi quy tắc trong một use case. Glossary không mô tả toàn bộ luồng xử lý. Ví dụ nghiệp vụ không tự nói lên quyền sở hữu giữa các nhóm.

## 2. Context Map là bản đồ quan hệ giữa các mô hình

Context Map mô tả cách các Bounded Context tương tác và ảnh hưởng lẫn nhau. Nó giúp nhóm nhận biết nơi có hợp đồng tích hợp, nơi cần chuyển đổi ngôn ngữ và nơi phụ thuộc có thể gây rủi ro.

Một Context Map có thể bao gồm:

- Tên Bounded Context và năng lực nghiệp vụ mà nó sở hữu.
- Team hoặc role chịu trách nhiệm về context.
- Nguồn dữ liệu và quyết định mà context sở hữu.
- Quan hệ giữa các context.
- Upstream và downstream trong từng quan hệ.
- Integration Contract: API, command, event hoặc batch interface.
- Cách chuyển đổi ngôn ngữ/dữ liệu ở ranh giới.
- Các rủi ro, giả định và quyết định kiến trúc liên quan.

### Ví dụ Context Map cho thương mại điện tử

Giả sử hệ thống có các context sau:

| Bounded Context | Trách nhiệm chính | Dữ liệu/quyết định sở hữu |
| --- | --- | --- |
| Catalog | Thông tin và cách trình bày sản phẩm | Product description, category, searchable attributes |
| Sales | Tiếp nhận mua hàng và vòng đời Order | Order, OrderLine, giá đã chấp nhận trong đơn |
| Inventory | Tồn kho có thể phân bổ và giữ hàng | Stock allocation, Reservation, expiry |
| Payments | Ủy quyền, thu và hoàn tiền | Payment, Authorization, Capture, Refund |
| Delivery | Tạo và theo dõi shipment | Shipment, carrier booking, delivery status |

Một quan hệ có thể được ghi như sau:

| Upstream | Downstream | Quan hệ | Hợp đồng |
| --- | --- | --- | --- |
| Catalog | Sales | Published Language / Open Host Service | Product query/API và ProductChanged event |
| Inventory | Sales | Customer-Supplier | ReserveStock command, InventoryReserved/ReservationRejected |
| Payments | Sales | Customer-Supplier | AuthorizePayment command, PaymentAuthorized/PaymentDeclined |
| Sales | Delivery | Customer-Supplier | CreateShipment command, ShipmentCreated |
| Delivery | Sales | Published Language | Shipment status events |

Bảng này là ví dụ. Upstream/downstream cần được xác định theo quyền quyết định và khả năng thay đổi hợp đồng trong tổ chức cụ thể; không suy ra chỉ từ hướng mũi tên trong sơ đồ.

### Sơ đồ Context Map

~~~mermaid
flowchart LR
    Catalog["Catalog Context"] -->|"Product API / events"| Sales["Sales Context"]
    Sales -->|"ReserveStock command"| Inventory["Inventory Context"]
    Inventory -->|"Reservation result"| Sales
    Sales -->|"AuthorizePayment command"| Payments["Payments Context"]
    Payments -->|"Payment result"| Sales
    Sales -->|"CreateShipment command"| Delivery["Delivery Context"]
    Delivery -->|"Shipment events"| Sales
~~~

Sơ đồ chỉ là lớp nhìn tổng quát. Bên cạnh mỗi quan hệ, tài liệu cần ghi ai sở hữu hợp đồng, cách versioning, cơ chế retry, timeout và cách xử lý khi consumer không thể tiếp tục.

### Ghi rõ relationship pattern

Context Map có thể sử dụng các pattern quan hệ để mô tả cách hai nhóm phối hợp:

| Pattern | Ý nghĩa khi cộng tác | Cần ghi trong tài liệu |
| --- | --- | --- |
| Partnership | Hai nhóm phối hợp và cùng thành công/thất bại theo mục tiêu chung | Mục tiêu chung, cách phối hợp thay đổi, người ra quyết định |
| Shared Kernel | Hai nhóm cùng sở hữu một phần mô hình được chia sẻ có kiểm soát | Phạm vi shared model, quyền review, quy trình thay đổi |
| Customer-Supplier | Upstream cung cấp năng lực/hợp đồng, downstream tiêu thụ | Nhu cầu downstream, cam kết upstream, ưu tiên và SLA |
| Conformist | Downstream chấp nhận mô hình upstream mà không kiểm soát được nó | Rủi ro phụ thuộc, giới hạn thay đổi, kế hoạch giảm coupling |
| Anti-Corruption Layer (ACL) | Downstream chuyển đổi mô hình bên ngoài sang ngôn ngữ nội bộ | Mapping, nơi đặt adapter, quy tắc không cho mô hình ngoài lan vào |
| Open Host Service (OHS) | Upstream cung cấp giao diện ổn định cho nhiều consumer | API/event contract, version, compatibility |
| Published Language | Các bên dùng một ngôn ngữ trao đổi được công bố | Schema, semantics, version và ví dụ payload |
| Separate Ways | Hai context không cần tích hợp trực tiếp | Dữ liệu không chia sẻ, lý do độc lập, giới hạn trách nhiệm |

Không cần gắn pattern cho mọi đường nối. Chỉ ghi khi pattern giúp giải thích quyền lực, trách nhiệm hoặc rủi ro của quan hệ.

### Phân biệt hướng dữ liệu với hướng phụ thuộc

Một event có thể đi từ Inventory sang Sales, trong khi Sales gửi command đến Inventory. Hai chiều message không làm mất quan hệ ownership: Inventory vẫn quyết định Reservation có được tạo hay không; Sales vẫn quyết định trạng thái Order. Hãy ghi rõ ai là owner của quyết định và ai là consumer của kết quả, thay vì chỉ vẽ mũi tên.

## 3. Tổ chức workshop để tạo và cập nhật Context Map

Context Map không nên được vẽ riêng bởi một người chỉ nhìn vào service diagram. Cần có người hiểu nghiệp vụ, người chịu trách nhiệm mô hình, người biết tích hợp và đại diện các team liên quan.

### Trước workshop

Chuẩn bị:

- Một workflow nghiệp vụ quan trọng, chẳng hạn Place Order.
- Danh sách thuật ngữ đang gây hiểu nhầm.
- Các sự kiện đã xảy ra và command thường được gửi.
- Những API hoặc event contract hiện có.
- Các điểm phải phối hợp release, incident hoặc sửa schema.
- Đại diện từ upstream và downstream.

Đừng bắt đầu bằng danh sách microservice hiện tại. Hãy bắt đầu từ hoạt động và quyết định nghiệp vụ để không nhầm ranh giới triển khai hiện hữu với ranh giới mô hình đúng.

### Trong workshop

Một luồng làm việc hữu ích:

1. Liệt kê business capability và kết quả mỗi capability chịu trách nhiệm.
2. Gom các hành vi, thuật ngữ và quy tắc thành các Bounded Context có mô hình nhất quán.
3. Xác định owner của dữ liệu và quyết định ở mỗi context.
4. Vẽ các quan hệ và ghi upstream/downstream.
5. Chọn relationship pattern nếu nó giải thích được cách cộng tác.
6. Ghi API, command, event hoặc batch contract đang dùng.
7. Đánh dấu điểm dịch ngôn ngữ, ACL, shared kernel và dữ liệu snapshot.
8. Liệt kê câu hỏi chưa được giải quyết và người chịu trách nhiệm trả lời.

### Sau workshop

- Đưa sơ đồ vào nơi nhóm có thể review và sửa.
- Gắn mã định danh cho context và relationship nếu cần traceability.
- Liên kết đến glossary, contract, ADR và ví dụ liên quan.
- Ghi ngày cập nhật, owner và trạng thái xác nhận.
- Chuyển câu hỏi chưa rõ thành việc cần xác minh, không biến giả định thành sự thật.

### Context Map cần mô tả quan hệ có thể thay đổi

Một relationship record có thể có các trường:

| Trường | Ví dụ |
| --- | --- |
| Relationship ID | REL-SALES-INVENTORY |
| Upstream | Inventory |
| Downstream | Sales |
| Pattern | Customer-Supplier |
| Contract | ReserveStock v1, InventoryReserved v1 |
| Transport | HTTP command + broker event |
| Translation | Sales Reservation Result Adapter |
| Owner | Inventory integration owner |
| Failure behavior | Timeout, retry cùng idempotency key, trạng thái PENDING |
| Review trigger | Đổi reservation lifecycle hoặc contract schema |

Các trường này làm rõ điều cần biết khi một nhóm định thay đổi contract. Không nhất thiết tất cả phải nằm trên sơ đồ; có thể để trong bảng chi tiết và liên kết từ sơ đồ.

## 4. Glossary và Ubiquitous Language phải gắn với context

Ubiquitous Language là ngôn ngữ chung được sử dụng trong hội thoại, tài liệu và code của một Bounded Context. Glossary ghi lại thuật ngữ để người mới, nhóm khác và stakeholder hiểu đúng cách dùng.

Điểm quan trọng là **một từ có thể có nghĩa khác nhau ở các context khác nhau**. Không nên tạo một từ điển toàn hệ thống rồi ép mọi nhóm dùng chung một định nghĩa nếu mô hình của họ khác nhau.

### Ví dụ cùng từ, khác mô hình

| Thuật ngữ | Catalog Context | Sales Context | Inventory Context |
| --- | --- | --- | --- |
| Product | Sản phẩm được mô tả và tìm kiếm | Thông tin sản phẩm được chụp vào OrderLine tại thời điểm mua | SKU/stock item có thể được phân bổ |
| Available | Có thể hiển thị hoặc mua theo catalog rule | Có thể tiếp tục checkout theo thông tin đã nhận | Số lượng có thể giữ tại thời điểm kiểm tra |
| Price | Giá hiển thị hoặc giá niêm yết | Giá được chấp nhận và lưu trong đơn | Có thể không có ý nghĩa trong mô hình tồn kho |
| Reservation | Có thể không tồn tại trong context | Kết quả giữ hàng được tham chiếu trong workflow | Cam kết giữ lượng stock đến thời hạn |
| Customer | Hồ sơ khách hàng và phân khúc | Bên đặt Order và chịu điều khoản bán | Có thể chỉ là tham chiếu phục vụ chính sách phân bổ |

Glossary không nhằm thống nhất tất cả các từ thành một mô hình duy nhất. Nó giúp nhận ra nơi ngôn ngữ giống nhau nhưng ý nghĩa khác nhau và ghi lại cách chuyển đổi khi đi qua ranh giới.

### Mẫu một mục glossary

Một thuật ngữ nên có đủ thông tin để người đọc sử dụng đúng:

| Trường | Nội dung |
| --- | --- |
| Term ID | SALES-TERM-ORDER |
| Term | Order |
| Context | Sales |
| Definition | Yêu cầu mua đã được Sales tiếp nhận và quản lý vòng đời |
| Examples | Order ở DRAFT, PENDING_CONFIRMATION, CONFIRMED |
| Counterexamples | Cart chưa được gửi không phải Order |
| Related terms | OrderLine, Confirmation, Cancellation |
| Code mapping | sales.order.Order, OrderStatus |
| API/event mapping | OrderPlaced, OrderConfirmed |
| Owner | Sales domain owner |
| Status | Proposed / Confirmed / Deprecated |
| Last reviewed | Ngày review gần nhất |

Mẫu này có thể giản lược cho dự án nhỏ. Các trường quan trọng nhất là term, context, definition, example/counterexample và owner.

### Định nghĩa bằng ví dụ và phản ví dụ

Định nghĩa “Reservation là việc giữ hàng” vẫn quá mơ hồ. Có thể làm rõ:

- Ví dụ: Inventory giữ 3 đơn vị SKU A cho Order 123 đến 10:30 UTC.
- Phản ví dụ: Sales đọc availability = 3 nhưng chưa gửi command giữ hàng; đó chưa phải Reservation.
- Trạng thái: REQUESTED, RESERVED, RELEASED, EXPIRED.
- Chủ sở hữu: Inventory Context.
- Điều kiện: chỉ Reservation ở trạng thái RESERVED và chưa hết hạn mới có thể được xác nhận theo policy.

Ví dụ và phản ví dụ giúp phân biệt khái niệm với từ gần nghĩa.

### Tránh synonym gây mơ hồ

Nếu nhóm dùng “đơn”, “order”, “purchase” và “booking” thay thế cho nhau, hãy xác định từ nào là tên chính trong context và từ nào là alias hoặc khái niệm khác. Không nên tự động coi các từ gần nghĩa là cùng một thuật ngữ.

Một glossary tốt cũng ghi rõ các thuật ngữ không được dùng trong một context nếu chúng gây nhầm lẫn. Ví dụ, trong Inventory, dùng StockItem hoặc SKU thay vì Product nếu mô hình không quản lý mô tả thương mại của Catalog.

## 5. Ví dụ nghiệp vụ biến thuật ngữ thành quy tắc có thể kiểm chứng

Glossary giải thích khái niệm; business example giải thích khái niệm vận hành trong tình huống cụ thể. Ví dụ cần đủ chi tiết để domain expert xác nhận và developer/tester chuyển thành hành vi có thể kiểm thử.

Một ví dụ tốt thường có:

- Bối cảnh và trạng thái ban đầu.
- Điều kiện hoặc sự kiện kích hoạt.
- Hành động được yêu cầu.
- Kết quả mong đợi.
- Side effect hoặc event được phát.
- Trường hợp từ chối và lý do.
- Thời điểm, số lượng, tiền tệ hoặc version nếu chúng ảnh hưởng quyết định.

### Example Mapping

Example Mapping là kỹ thuật cộng tác để làm rõ một user story bằng các nhóm:

- **Story:** hành vi đang được thảo luận.
- **Rules:** quy tắc nghiệp vụ chi phối hành vi.
- **Examples:** tình huống minh họa cho từng quy tắc.
- **Questions:** điều chưa rõ cần chuyên gia xác nhận.

Ví dụ story: “Xác nhận đơn khi hàng đã được giữ và thanh toán được ủy quyền”.

| Nhóm | Nội dung |
| --- | --- |
| Story | Sales xác nhận Order sau khi các điều kiện fulfillment đạt |
| Rule 1 | Order chỉ được xác nhận khi Inventory có Reservation hợp lệ |
| Rule 2 | Reservation phải còn hiệu lực tại thời điểm Sales xử lý kết quả |
| Rule 3 | Payment phải có trạng thái AUTHORIZED theo hợp đồng Payments |
| Example | Reservation R-10 còn hạn và Payment P-20 đã AUTHORIZED → Order có thể CONFIRMED |
| Example | Reservation đã EXPIRED → Order không được CONFIRMED |
| Question | Nếu Payment đã AUTHORIZED nhưng reservation hết hạn trước khi xác nhận thì xử lý bù trừ thế nào? |

Câu hỏi chưa rõ phải được ghi lại với người chịu trách nhiệm và thời hạn xác minh. Không được tự điền một giả định kỹ thuật rồi coi đó là chính sách nghiệp vụ.

### Given/When/Then

Khi quy tắc đã rõ, có thể biểu diễn bằng ví dụ có cấu trúc:

~~~gherkin
Feature: Confirm an order

  Rule: An order requires a valid inventory reservation
    Scenario: Confirm when reservation and payment are valid
      Given order "ORD-123" is pending confirmation
      And reservation "RES-10" is reserved until "10:30Z"
      And payment "PAY-20" is authorized
      When Sales processes the fulfillment result at "10:15Z"
      Then order "ORD-123" becomes confirmed
      And an OrderConfirmed event is recorded

    Scenario: Reject confirmation after reservation expiry
      Given order "ORD-123" is pending confirmation
      And reservation "RES-10" expired at "10:00Z"
      And payment "PAY-20" is authorized
      When Sales processes the fulfillment result at "10:15Z"
      Then order "ORD-123" is not confirmed
      And the reason is "RESERVATION_EXPIRED"
~~~

Gherkin là cách diễn đạt ví dụ, không tự động bảo đảm test đã chạy. Step definitions cần gọi application use case hoặc test adapter thực sự, không chỉ kiểm tra chuỗi văn bản.

### Bảng quyết định cho thời điểm giữ hàng

| Reservation status | Còn hạn? | Payment status | Kết quả Sales |
| --- | --- | --- | --- |
| RESERVED | Có | AUTHORIZED | Có thể xác nhận nếu Order vẫn hợp lệ |
| RESERVED | Không | AUTHORIZED | Không xác nhận; xử lý authorization theo workflow |
| RELEASED | Không | AUTHORIZED | Không xác nhận |
| RESERVED | Có | DECLINED | Không xác nhận; yêu cầu release reservation |
| EXPIRED | Không | PENDING | Chờ hoặc kết thúc theo deadline |

Bảng cần bao gồm những kết hợp có ý nghĩa nghiệp vụ, không cần liệt kê mọi tổ hợp dữ liệu vô ích. Domain expert xác nhận kết quả; developer xác định cách thực thi; tester bảo đảm các nhánh được kiểm thử.

## 6. Liên kết Context Map, glossary, ví dụ và code

Tài liệu trở nên hữu ích khi người đọc có thể đi từ khái niệm đến hành vi triển khai và ngược lại.

Một đường truy vết có thể là:

1. Context Map xác định Sales phụ thuộc Inventory qua Reservation contract.
2. Glossary định nghĩa Reservation, Reserved, Expired và Order.
3. Example Mapping ghi quy tắc Order cần Reservation hợp lệ.
4. API/event contract định nghĩa Reservation ID, status, expiresAt và version.
5. Application code xử lý kết quả.
6. Test chứng minh từng ví dụ và phản ví dụ.

### Ví dụ mapping từ thuật ngữ đến code

| Business concept | Context | Code artifact | Contract/test |
| --- | --- | --- | --- |
| Order | Sales | `sales.order.Order` | `OrderAggregateTest` |
| Reservation | Inventory | `inventory.reservation.Reservation` | `ReservationExpiryTest` |
| Reservation result | Sales integration adapter | `ReservationGateway` | `ReservationContractTest` |
| Order confirmation rule | Sales | `ConfirmOrder` | `ConfirmOrderAcceptanceTest` |
| Order confirmed | Sales | `OrderConfirmed` | `OrderEventMappingTest` |

Tên class không phải định nghĩa nghiệp vụ. Glossary là nơi giải thích ý nghĩa; code là cách thực thi. Nếu code và glossary không còn khớp, cần xác định artifact nào sai và sửa cùng một change.

### Ví dụ Java ở ranh giới Sales

Sales không đọc bảng Inventory. Nó dùng một port diễn đạt nhu cầu nghiệp vụ:

~~~java
public interface ReservationGateway {
    ReservationEvidence findReservation(ReservationId reservationId);
}

// Value Object owned by the Sales context.
public record ReservationEvidence(
    ReservationId reservationId,
    boolean reserved,
    Instant expiresAt
) {
    public boolean isValidAt(Instant now) {
        return reserved && now.isBefore(expiresAt);
    }
}

public record PaymentAuthorizationEvidence(boolean authorized) {}
~~~

Integration adapter chuyển status bên ngoài thành ngôn ngữ của Sales. Ví dụ, adapter có thể đổi response `InventoryReservationStatus.RESERVED` thành `ReservationEvidence(reservationId, true, expiresAt)`. Enum của Inventory chỉ xuất hiện ở adapter; Aggregate Sales không phụ thuộc kiểu miền nội bộ của Inventory.

Application service điều phối use case:

~~~java
public final class ConfirmOrder {
    private final OrderRepository orders;
    private final ReservationGateway reservations;
    private final PaymentGateway payments;

    public ConfirmOrder(
        OrderRepository orders,
        ReservationGateway reservations,
        PaymentGateway payments
    ) {
        this.orders = orders;
        this.reservations = reservations;
        this.payments = payments;
    }

    public void handle(ConfirmOrderCommand command) {
        Order order = orders.get(command.orderId());

        ReservationEvidence reservation =
            reservations.findReservation(order.reservationId());

        PaymentAuthorizationEvidence payment =
            payments.findPayment(order.paymentId());

        order.confirm(
            reservation,
            payment,
            command.processedAt()
        );

        orders.save(order);
    }
}
~~~

Aggregate bảo vệ quyết định cục bộ dựa trên dữ liệu hợp đồng đã nhận:

~~~java
public void confirm(
    ReservationEvidence reservation,
    PaymentAuthorizationEvidence payment,
    Instant now
) {
    if (status != OrderStatus.PENDING_CONFIRMATION) {
        throw new OrderCannotBeConfirmed(id, status);
    }
    if (!reservation.isValidAt(now)) {
        throw new ReservationNotValid(id);
    }
    if (!payment.authorized()) {
        throw new PaymentNotAuthorized(id);
    }

    status = OrderStatus.CONFIRMED;
    domainEvents.add(new OrderConfirmed(id, now));
}
~~~

Ví dụ được giản lược để thể hiện mapping. Trong hệ thống bất đồng bộ, Sales thường nhận kết quả từ Integration Event và lưu trạng thái workflow; không nên gọi nhiều API đồng bộ trong Aggregate hoặc giữ transaction database mở khi chờ network. Application layer cần xử lý timeout, version, idempotency và kết quả có thể đến muộn. Việc xác nhận phải dùng dữ liệu đủ mới theo hợp đồng đã thống nhất.

### Liên kết bằng ID ổn định

Có thể dùng các ID như:

- Context: `CTX-SALES`, `CTX-INVENTORY`.
- Relationship: `REL-SALES-INVENTORY`.
- Term: `TERM-INVENTORY-RESERVATION`.
- Rule: `RULE-SALES-CONFIRM-ORDER-01`.
- Example: `EX-SALES-CONFIRM-ORDER-VALID-01`.
- Contract: `CONTRACT-INVENTORY-RESERVATION-V1`.
- Decision: `ADR-024-RESERVATION-OWNERSHIP`.

ID ổn định giúp liên kết từ tài liệu đến PR, test, ADR và contract ngay cả khi tiêu đề hoặc đường dẫn thay đổi. Không cần tạo ID cho mọi câu; chỉ dùng khi có giá trị truy vết qua nhiều artifact.

## 7. Ghi lại quan hệ và quyết định, không chỉ ghi kết quả cuối

Context Map và glossary trả lời “hiện tại chúng ta hiểu mô hình thế nào”. Architecture Decision Record (ADR) hoặc decision log trả lời “vì sao đã chọn cách này và những phương án nào đã được cân nhắc”.

Một quyết định có thể ghi:

- Context và relationship liên quan.
- Vấn đề cần giải quyết.
- Các phương án đã xem xét.
- Quyết định và lý do.
- Hệ quả, rủi ro và điều kiện để xem xét lại.
- Người tham gia và ngày quyết định.

Ví dụ, nhóm chọn để Inventory sở hữu Reservation vì Inventory có quyền kiểm soát số lượng và expiry. Sales chỉ lưu reservation reference và kết quả. Một phương án khác là Sales tự quản lý số lượng tồn; phương án đó bị loại vì Sales không sở hữu dữ liệu phân bổ và có thể gây race condition.

ADR không phải nơi lặp lại toàn bộ glossary hoặc code. Nó ghi lý do của quyết định và liên kết đến các artifact chi tiết.

### Khi nào cần ADR?

- Chọn hoặc thay đổi Bounded Context boundary.
- Chuyển quan hệ từ Conformist sang ACL.
- Tạo hoặc loại bỏ Shared Kernel.
- Đổi synchronous API sang event-driven integration.
- Thay nguồn sự thật hoặc quyền sở hữu dữ liệu.
- Thay contract có ảnh hưởng đến nhiều consumer.
- Chấp nhận consistency lag hoặc một failure mode mới.

Không cần ADR cho mọi rename nhỏ. Dùng nó khi quyết định có hệ quả dài hạn hoặc cần giữ lại bối cảnh để người sau hiểu.

## 8. Tổ chức tài liệu gần mã nguồn

Tài liệu cần dễ tìm, dễ review và được cập nhật cùng thay đổi liên quan. Một cách là lưu Markdown, Mermaid, OpenAPI, AsyncAPI và ADR trong repository của context hoặc một repository tài liệu có ownership rõ.

Ví dụ cấu trúc:

~~~text
docs/
  domain/
    context-map/
      overview.md
      relationships/
        sales-inventory.md
        sales-payments.md
    glossary/
      sales.md
      inventory.md
      payments.md
    examples/
      sales/
        confirm-order.md
      inventory/
        reserve-stock.md
    decisions/
      ADR-024-reservation-ownership.md
  contracts/
    inventory/
      reserve-stock.yaml
      inventory-reserved.schema.json
~~~

Đây là gợi ý tổ chức, không phải cấu trúc bắt buộc. Có thể đặt tài liệu trong từng repo nếu mỗi context có owner độc lập. Nếu Context Map cần cái nhìn toàn hệ thống, một bản tổng hợp có link đến nguồn chi tiết của từng context sẽ hữu ích.

### Docs-as-code

Lưu tài liệu dạng text trong Git đem lại:

- Pull request và review như code.
- Lịch sử thay đổi và tác giả.
- Diff rõ ràng cho glossary, sơ đồ và ví dụ.
- Link đến commit, test và contract.
- Có thể kiểm tra format, link và schema trong CI.
- Dễ tạo bản xem trước theo branch.

Nhưng docs-as-code không có nghĩa mọi domain expert phải sửa Markdown trực tiếp. Họ có thể review nội dung qua PR, workshop hoặc công cụ cộng tác; developer hoặc technical writer hỗ trợ chuyển kết quả thành artifact có version.

### Tự động kiểm tra điều gì?

CI có thể kiểm tra:

- Markdown có lỗi format hoặc link nội bộ bị hỏng.
- Mermaid có thể parse.
- OpenAPI/AsyncAPI/schema hợp lệ.
- Example files có ID duy nhất.
- Glossary entries có context và owner bắt buộc.
- Contract examples khớp schema.
- Test có liên kết tới rule/example ID nếu nhóm dùng traceability.

CI không thể tự xác nhận một định nghĩa có đúng với ý nghĩa nghiệp vụ hay không. Review của domain expert vẫn cần thiết.

## 9. Quy trình cộng tác từ khám phá đến thay đổi code

Một vòng làm việc có thể tổ chức theo các bước sau:

### Trước khi viết code

1. Product owner hoặc domain expert mô tả tình huống và kết quả mong muốn.
2. Nhóm làm rõ thuật ngữ và ghi vào glossary nếu đây là khái niệm mới hoặc đang mơ hồ.
3. Cập nhật Context Map nếu thay đổi ảnh hưởng boundary hoặc quan hệ giữa context.
4. Dùng Example Mapping để tìm rule, example, counterexample và câu hỏi.
5. Ghi quyết định kiến trúc nếu có trade-off dài hạn.

### Trong khi triển khai

1. Chọn tên class, method, event và package theo Ubiquitous Language của context.
2. Giữ Aggregate bảo vệ invariant được mô tả trong rule.
3. Định nghĩa contract và mapping tại integration boundary.
4. Viết test từ business examples đã xác nhận.
5. Khi phát hiện trường hợp mới, quay lại domain expert để xác minh.

### Khi review và phát hành

1. Reviewer kiểm tra code có diễn đạt đúng thuật ngữ không.
2. Domain expert xác nhận rule và ví dụ có còn đúng không.
3. Team owner review Context Map/contract nếu quan hệ thay đổi.
4. Cập nhật glossary, example, ADR và schema trong cùng change khi cần.
5. Sau triển khai, quan sát hành vi thực tế và ghi lại khoảng cách với giả định ban đầu.

Không phải mọi PR đều cần sửa cả ba artifact. Chỉ cập nhật tài liệu bị ảnh hưởng, nhưng phải kiểm tra tác động đến các artifact liên quan.

## 10. Quản lý thay đổi và vòng đời thuật ngữ

Thuật ngữ và quan hệ giữa context có thể thay đổi khi tổ chức hiểu nghiệp vụ sâu hơn. Glossary cần trạng thái để phân biệt điều đã thống nhất với giả thuyết đang khám phá.

Một vòng đời đơn giản:

| Trạng thái | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| Proposed | Thuật ngữ hoặc định nghĩa đang được đề xuất | Dùng trong thảo luận, chưa coi là chuẩn |
| Confirmed | Domain expert và team đã thống nhất | Dùng trong code, contract và tài liệu |
| Deprecated | Không còn khuyến nghị dùng | Chỉ giữ để giải thích tài liệu cũ và migration |
| Retired | Không còn được dùng trong hệ thống hiện tại | Lưu lịch sử nếu cần audit |

Khi đổi thuật ngữ:

- Xác định đây là đổi tên hay thay đổi ý nghĩa.
- Nếu chỉ đổi tên, giữ alias và mapping trong thời gian chuyển đổi.
- Nếu đổi nghĩa, tạo định nghĩa mới hoặc phân biệt theo context/version.
- Tìm code, API, event, test và tài liệu đang dùng thuật ngữ cũ.
- Lập kế hoạch migration cho consumer.
- Đánh dấu thuật ngữ cũ Deprecated và ghi ngày review lại.

### Review trigger cho Context Map

Không cần review theo lịch một cách máy móc nếu không có thay đổi. Nên review khi:

- Thêm hoặc loại bỏ Bounded Context.
- Thay đổi upstream/downstream hoặc team owner.
- Thay API/event contract.
- Có incident do hiểu sai semantics.
- Chuyển quyền sở hữu dữ liệu.
- Tách hoặc gộp module/service.
- Một context bắt đầu phụ thuộc trực tiếp vào schema nội bộ của context khác.

### Review trigger cho glossary và examples

- Domain expert thay đổi chính sách.
- Xuất hiện ngoại lệ mới.
- Một từ được dùng với hai nghĩa khác nhau.
- Test liên tục cần workaround vì ví dụ không phản ánh rule.
- Support/operations thường xuyên giải thích kết quả khác tài liệu.
- Code và tài liệu dùng tên khác nhau mà không có mapping.

## 11. Xử lý bất đồng giữa các nhóm

Bất đồng thuật ngữ không nhất thiết là vấn đề giao tiếp. Nó có thể chỉ ra rằng các nhóm đang mô hình hóa những khía cạnh khác nhau của cùng một thực thể.

Ví dụ, Catalog gọi Product là mặt hàng có mô tả, hình ảnh và category. Inventory dùng SKU để quản lý đơn vị có thể lưu kho. Sales dùng Product Snapshot để giữ tên và giá tại thời điểm đặt. Cố tạo một Product class chung cho cả ba context có thể làm mô hình phình to và khiến mỗi nhóm phụ thuộc vào thay đổi của nhóm khác.

Cách xử lý:

1. Hỏi mỗi nhóm đang giải quyết quyết định nghiệp vụ nào.
2. Ghi định nghĩa của thuật ngữ trong từng context.
3. Ghi rõ phần thông tin được chuyển qua integration contract.
4. Xác định ai chuyển đổi mô hình và ở boundary nào.
5. Chỉ dùng Shared Kernel khi hai nhóm thật sự cùng sở hữu một phần mô hình nhỏ và có quy trình thay đổi chung.
6. Nếu không có nhu cầu tích hợp, cân nhắc Separate Ways.

### Dùng ACL để bảo vệ ngôn ngữ nội bộ

Khi upstream có mô hình không phù hợp, downstream có thể dùng Anti-Corruption Layer để dịch.

Ví dụ, provider vận chuyển trả về trạng thái `IN_TRANSIT_3` hoặc `DELIVERY_EXCEPTION_X`. Delivery Context chuyển chúng thành các trạng thái miền như `IN_TRANSIT` hoặc `DELIVERY_ATTEMPT_FAILED`. Sales chỉ nhận hợp đồng mà nó cần, không phải hiểu toàn bộ mã nội bộ của provider.

Glossary nên ghi cả thuật ngữ ngoài, thuật ngữ nội bộ và mapping để nhóm biết nơi dịch. Không để tên field từ hệ thống đối tác lan khắp Aggregate.

## 12. Phân biệt tài liệu sống với bản ghi lịch sử

Context Map và glossary hiện hành cần phản ánh cách hệ thống đang vận hành. ADR, biên bản workshop và quyết định cũ là lịch sử giúp hiểu vì sao mô hình đã thay đổi.

Không nên sửa tài liệu lịch sử để giả vờ quyết định cũ chưa từng tồn tại. Hãy tạo quyết định mới supersede quyết định trước và cập nhật bản đồ hiện hành.

Một cách tổ chức:

- **Current model:** Context Map và glossary đang có hiệu lực.
- **Examples/specifications:** quy tắc và tình huống hiện hành được kiểm thử.
- **Decision history:** ADR và quyết định đã thay thế.
- **Migration notes:** mapping từ thuật ngữ/contract cũ sang mới.

Điều này giúp người mới không nhầm một quyết định lịch sử với chính sách hiện tại.

## 13. Những sai lầm thường gặp

- **Chỉ vẽ Context Map mà không ghi owner/contract:** sơ đồ không giúp biết ai chịu trách nhiệm khi thay đổi.
- **Dùng một glossary toàn cục:** che mất khác biệt ngôn ngữ giữa các Bounded Context.
- **Định nghĩa thuật ngữ bằng tên class:** code có thể đổi nhưng ý nghĩa nghiệp vụ cần được giải thích độc lập.
- **Chỉ ghi happy path:** ngoại lệ và ranh giới thời gian vẫn phải được suy đoán.
- **Ghi meeting notes thay cho business examples:** biên bản không phải specification có thể kiểm chứng.
- **Tạo tài liệu rồi không gắn với PR/review:** tài liệu nhanh chóng lệch khỏi code.
- **Để developer tự quyết định nghĩa nghiệp vụ:** domain expert không xác nhận thì giả định dễ trở thành quy tắc sai.
- **Dùng Shared Kernel quá rộng:** mọi nhóm bị buộc đồng bộ thay đổi.
- **Coi mọi event là Published Language:** event nội bộ và integration contract có mục đích khác nhau.
- **Để contract lộ mô hình nội bộ:** consumer phụ thuộc vào chi tiết mà upstream cần tự do thay đổi.
- **Không quản lý deprecated term:** từ cũ tiếp tục xuất hiện trong code, dashboard và hội thoại.
- **Tự động hóa kiểm tra nội dung mà không có review chuyên môn:** CI có thể kiểm tra format nhưng không xác nhận semantics.
- **Lưu nhiều bản copy của cùng một định nghĩa:** không biết đâu là nguồn có thẩm quyền.

## 14. Quy trình thiết lập hệ thống tài liệu DDD

Có thể bắt đầu nhỏ với một workflow quan trọng và mở rộng dần:

1. **Chọn workflow.** Chọn một hành trình có nhiều quyết định hoặc nhiều context tham gia.
2. **Xác định context.** Ghi năng lực, owner và source of truth.
3. **Vẽ quan hệ.** Xác định upstream/downstream, relationship pattern và contract.
4. **Lập glossary theo context.** Ghi định nghĩa, ví dụ, phản ví dụ và mapping code/API.
5. **Làm Example Mapping.** Tách story, rules, examples và questions.
6. **Chuyển ví dụ thành test.** Dùng Given/When/Then, decision table và boundary tests.
7. **Liên kết artifact.** Gắn term/rule/example ID với ADR, contract, package và test.
8. **Lưu nơi có ownership.** Chọn repository hoặc workspace mà các nhóm có thể review.
9. **Thiết lập review.** Xác định domain expert, context owner và reviewer kỹ thuật.
10. **Tích hợp kiểm tra tự động.** Validate Markdown, diagram, schema, link và ID.
11. **Theo dõi drift.** Khi code, contract hoặc nghiệp vụ đổi, xác định tài liệu cần cập nhật.
12. **Review theo trigger.** Cập nhật Context Map, glossary và examples khi boundary hoặc rule thay đổi.

Checklist review:

- [ ] Context Map nêu rõ Bounded Context, năng lực và owner?
- [ ] Quan hệ có upstream/downstream và contract cụ thể?
- [ ] Relationship pattern được dùng khi nó giải thích được cách cộng tác?
- [ ] Glossary ghi nghĩa theo từng context?
- [ ] Thuật ngữ có ví dụ, phản ví dụ và từ liên quan?
- [ ] Tên trong code/API có mapping về thuật ngữ miền?
- [ ] Business examples bao gồm happy path, rejection và boundary case?
- [ ] Rules và examples được domain expert xác nhận?
- [ ] Có thể lần từ example đến Aggregate, contract và test?
- [ ] ADR ghi lý do cho các quyết định có hệ quả dài hạn?
- [ ] Mỗi artifact có owner, trạng thái và review trigger?
- [ ] PR/CI giúp phát hiện link, schema hoặc tài liệu bị lệch?
- [ ] Tài liệu hiện hành được phân biệt với quyết định lịch sử?
- [ ] Các context giữ được ngôn ngữ riêng và có mapping rõ ở integration boundary?

## Kết luận

Context Map, glossary và business examples tạo thành một hệ thống cộng tác bổ trợ nhau. Context Map làm rõ ranh giới và quan hệ giữa các mô hình. Glossary giữ Ubiquitous Language chính xác theo từng Bounded Context. Ví dụ nghiệp vụ biến quy tắc và ngoại lệ thành tình huống mà domain expert có thể xác nhận và tester có thể kiểm chứng.

Hãy liên kết những artifact đó với Aggregate, package, API/event contract, ADR và test bằng các tham chiếu ổn định. Đặt tài liệu gần quy trình review và thay đổi code, có owner và trạng thái rõ ràng, đồng thời review khi nghiệp vụ hoặc quan hệ tích hợp thay đổi. Mục tiêu không phải tạo thật nhiều tài liệu; mục tiêu là giúp mọi người hiểu cùng một quyết định, biết ai sở hữu nó và có thể lần theo quyết định đó đến hành vi đang chạy trong hệ thống.
