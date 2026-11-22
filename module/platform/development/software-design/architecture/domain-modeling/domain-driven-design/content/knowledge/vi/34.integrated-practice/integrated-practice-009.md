# Đánh giá sản phẩm bằng ví dụ nghiệp vụ, kiểm thử và quyết định kiến trúc

Một sản phẩm phần mềm có thể có nhiều tính năng, nhiều service và một bộ test lớn nhưng vẫn không giải quyết đúng vấn đề của doanh nghiệp. Ngược lại, một thay đổi nhỏ trong domain model có thể tạo ra tác động lớn nếu nó loại bỏ một điểm nghẽn quan trọng trong quy trình. Vì vậy, đánh giá sản phẩm theo Domain-Driven Design (DDD) cần kết nối ba loại bằng chứng: ví dụ nghiệp vụ cho biết hệ thống phải làm gì, kiểm thử chứng minh hành vi đó có được thực hiện ổn định hay không, và quyết định kiến trúc giải thích vì sao hệ thống được tổ chức theo cách hiện tại.

Đánh giá không dừng ở việc xác nhận một endpoint trả về HTTP 200 hoặc một use case chạy qua. Nhóm cần biết khách hàng có hoàn thành được công việc không, quy tắc nghiệp vụ có được bảo vệ trong các tình huống biên không, dữ liệu giữa các Bounded Context có nhất quán theo mức đã cam kết không, và hệ thống có thể thay đổi mà không tạo rủi ro không chấp nhận được không.

Bài viết xây dựng một phương pháp thực hành tích hợp. Ta sẽ dùng ví dụ thương mại điện tử: khách chọn sản phẩm đang có khuyến mãi, đặt hàng, hệ thống giữ tồn kho và xử lý thanh toán; sau đó khách có thể hủy đơn hoặc yêu cầu hoàn tiền. Từ cùng một câu chuyện, ta xác định outcome, ví dụ cụ thể, ngôn ngữ chung, mô hình domain, ranh giới context, test ở nhiều tầng và các quyết định kiến trúc. Cuối cùng, ta lập một hồ sơ đánh giá có thể dùng trong review sản phẩm, refinement, release readiness và cải tiến liên tục.

## 1. Đánh giá sản phẩm cần trả lời câu hỏi nào?

Một đánh giá hữu ích phải xem sản phẩm từ góc nhìn người sử dụng, nghiệp vụ và hệ thống kỹ thuật. Ba góc nhìn liên quan chặt chẽ nhưng không thể thay thế cho nhau.

### 1.1. Sản phẩm có tạo ra kết quả nghiệp vụ mong muốn không?

Hãy bắt đầu bằng kết quả, không phải danh sách màn hình hoặc API. Ví dụ:

- Khách có thể mua được sản phẩm với mức giá đã được xác nhận.
- Hệ thống không bán vượt số lượng có thể phân bổ.
- Khách biết đơn đã được tiếp nhận, xác nhận hay đang chờ thanh toán.
- Hủy đơn không làm mất dấu vết tài chính hoặc giải phóng nhầm tồn kho.
- Nhân viên hỗ trợ có thể giải thích trạng thái đơn mà không phải truy vấn nhiều hệ thống thủ công.

Các outcome này cần gắn với chỉ số có thể quan sát, chẳng hạn tỷ lệ checkout thành công, tỷ lệ giữ hàng thất bại, thời gian hoàn tiền, số lần can thiệp thủ công hoặc tỷ lệ đơn bị xử lý sai.

### 1.2. Hành vi có đúng trong cả trường hợp bình thường và ngoại lệ không?

Happy path chỉ là một phần của sản phẩm. Các tình huống có giá trị đánh giá cao thường là:

- Hai khách cùng mua sản phẩm cuối cùng.
- Giá hoặc khuyến mãi thay đổi giữa lúc thêm giỏ hàng và đặt đơn.
- Payment gateway timeout nhưng có thể đã nhận yêu cầu.
- Khách gửi lặp yêu cầu đặt đơn do mạng chậm.
- Reservation hết hạn trong khi thanh toán đang xử lý.
- Khách hủy đơn sau khi shipment đã được bàn giao.
- Một phần đơn đã giao, phần còn lại chưa giao.

Nếu sản phẩm chỉ hoạt động đúng khi mọi hệ thống phản hồi nhanh và theo đúng thứ tự, thiết kế chưa được đánh giá đầy đủ.

### 1.3. Kiến trúc có hỗ trợ thay đổi và vận hành không?

Một sản phẩm cần được đánh giá cả khả năng tiến hóa:

- Quy tắc giá mới có thể thay đổi mà không sửa nhiều context không?
- Ordering có phụ thuộc trực tiếp vào schema nội bộ của Inventory không?
- Khi message bị gửi lại, projector hoặc consumer có xử lý an toàn không?
- Khi một dịch vụ ngoài ngừng hoạt động, hệ thống có trạng thái phục hồi rõ không?
- Có thể triển khai một thay đổi trong phạm vi nhỏ và rollback không?
- Test có kiểm chứng đúng contract hay chỉ kiểm tra implementation hiện tại?

Kiến trúc tốt không phải kiến trúc có nhiều pattern nhất. Nó là kiến trúc có trade-off phù hợp với outcome, rủi ro và năng lực vận hành của sản phẩm.

## 2. Chọn một lát cắt nghiệp vụ để đánh giá

Không nên cố đánh giá toàn bộ sản phẩm trong một lần. Hãy chọn một lát cắt dọc (vertical slice) có ý nghĩa với người dùng và đi qua đủ các lớp cần thiết.

Ví dụ, lát cắt “đặt một đơn có khuyến mãi” có thể đi qua:

1. Màn hình checkout nhận thông tin giỏ hàng và địa chỉ.
2. Ordering tiếp nhận yêu cầu tạo đơn.
3. Pricing xác nhận báo giá và điều kiện khuyến mãi.
4. Inventory kiểm tra và giữ số lượng.
5. Payment thực hiện authorization hoặc capture theo chính sách.
6. Ordering ghi nhận kết quả và công bố trạng thái đơn.
7. Notification gửi thông tin cho khách.

Lát cắt này có đủ nghiệp vụ để đánh giá mô hình, nhưng vẫn có phạm vi cụ thể để kiểm thử và đo lường.

### 2.1. Xác định actor và mục tiêu

| Actor | Mục tiêu |
|---|---|
| Khách hàng | Hoàn tất mua hàng với giá và điều kiện rõ ràng |
| Ordering | Quản lý vòng đời Order |
| Pricing | Cung cấp báo giá có hiệu lực |
| Inventory | Bảo vệ số lượng có thể giữ |
| Payment | Xác nhận và hoàn tiền theo trạng thái giao dịch |
| Customer Support | Tra cứu và giải thích trạng thái đơn |

Actor không chỉ là con người. Một hệ thống khác hoặc một tiến trình nền cũng có thể kích hoạt hành vi.

### 2.2. Viết outcome và tiêu chí quan sát

Ví dụ outcome:

“Khách có thể đặt đơn với mức giá đã được xác nhận, và hệ thống chỉ xác nhận đơn khi các điều kiện bắt buộc về tồn kho và thanh toán đã được đáp ứng theo chính sách.”

Tiêu chí quan sát có thể gồm:

- Giá trong đơn là giá snapshot được chấp nhận tại thời điểm đặt.
- Reservation thuộc đúng Order và có thời hạn.
- Một request lặp không tạo hai đơn hoặc hai khoản thanh toán.
- Trạng thái Order phản ánh đúng kết quả của workflow.
- Có thể truy vết một yêu cầu qua các context bằng correlation ID.
- Nếu một bước thất bại, hệ thống có trạng thái chờ, retry hoặc bù rõ ràng.

Tiêu chí cần được xác nhận với chuyên gia nghiệp vụ. Không tự suy ra rằng thanh toán phải capture trước hay sau khi giữ hàng; thứ tự đó phụ thuộc chính sách thực tế.

## 3. Biến câu chuyện thành ví dụ nghiệp vụ cụ thể

Ví dụ nghiệp vụ (concrete example) mô tả dữ liệu, điều kiện, hành động và kết quả của một tình huống thật. Nó giúp chuyên gia và kỹ sư thảo luận về cùng một điều thay vì dùng các câu chung chung như “hệ thống phải xử lý khuyến mãi đúng”.

### 3.1. Ví dụ happy path

**Bối cảnh:** Khách hàng An đặt hai sản phẩm A, mỗi sản phẩm có giá niêm yết 200.000 đồng. Khuyến mãi hợp lệ giảm 10%. Phí giao hàng là 20.000 đồng. Kho có đủ số lượng và Payment chấp nhận authorization.

**Hành động:** An xác nhận checkout với báo giá còn hiệu lực.

**Kết quả mong đợi:**

- Pricing xác nhận giảm giá 40.000 đồng.
- Tổng tiền trước giao hàng là 360.000 đồng.
- Tổng thanh toán là 380.000 đồng.
- Inventory giữ hai sản phẩm cho Order.
- Payment authorization thành công.
- Ordering chuyển đơn sang trạng thái đã xác nhận theo chính sách.
- Khách nhận được mã đơn và thông tin trạng thái.

Các con số ở đây là dữ liệu minh họa để làm rõ phép tính. Quy tắc làm tròn, cách tính thuế, phí giao hàng và thời điểm chốt giá phải được lấy từ chính sách của sản phẩm.

### 3.2. Ví dụ ngoại lệ: chỉ còn một sản phẩm

**Bối cảnh:** Hai khách cùng checkout sản phẩm cuối cùng trong kho.

**Hành động:** Hai yêu cầu giữ hàng được xử lý gần như đồng thời.

**Kết quả mong đợi:** Chỉ một reservation được chấp nhận. Yêu cầu còn lại nhận kết quả hết hàng hoặc không đủ số lượng; hệ thống không tạo hai đơn đã xác nhận dựa trên cùng một đơn vị tồn kho.

Ví dụ này buộc nhóm xác định ai sở hữu số lượng có thể giữ và cơ chế concurrency nằm ở đâu. Một phép kiểm tra tồn kho bằng SELECT trước rồi INSERT sau có thể bị race condition nếu không có khóa hoặc constraint phù hợp.

### 3.3. Ví dụ ngoại lệ: payment timeout

**Bối cảnh:** Payment gateway nhận yêu cầu authorization nhưng client của hệ thống timeout trước khi nhận phản hồi.

**Hành động:** Application Service không biết chắc gateway đã xử lý hay chưa.

**Kết quả mong đợi:** Hệ thống không gửi một giao dịch mới với identity khác một cách mù quáng. Nó tra cứu hoặc retry bằng idempotency key theo contract của provider, ghi nhận trạng thái chưa xác định và chỉ chuyển Order theo kết quả được xác nhận.

Timeout không đồng nghĩa giao dịch thất bại. Đây là một điểm quan trọng cần đưa vào ví dụ, test và quyết định kiến trúc.

### 3.4. Ví dụ ngoại lệ: hủy sau khi đã bàn giao

**Bối cảnh:** Order đã được xác nhận và Shipment đã bàn giao cho hãng vận chuyển.

**Hành động:** Khách yêu cầu hủy đơn.

**Kết quả mong đợi:** Ordering đánh giá chính sách hủy; Shipping có thể từ chối lệnh dừng giao hoặc chuyển sang quy trình hoàn hàng. Payment xử lý hoàn tiền theo điều kiện thực tế. Hệ thống không giả vờ rằng mọi tác dụng phụ đã được đảo ngược tức thời.

Ví dụ này giúp phân biệt Order cancellation, shipment interception và return. Chúng có thể là những quy trình domain khác nhau.

### 3.5. Dùng bảng ví dụ để thống nhất kỳ vọng

| Mã | Tình huống | Điều kiện chính | Kết quả cần xác minh |
|---|---|---|---|
| EX-01 | Đặt đơn thành công | Báo giá còn hiệu lực, giữ hàng và payment thành công | Order được xác nhận đúng tổng tiền |
| EX-02 | Hai khách tranh sản phẩm cuối | Cùng yêu cầu giữ một đơn vị cuối | Chỉ một reservation thành công |
| EX-03 | Payment timeout | Kết quả provider chưa rõ | Không tạo giao dịch trùng; trạng thái chờ được quản lý |
| EX-04 | Khuyến mãi hết hạn | Quote hết hiệu lực trước khi xác nhận | Không áp dụng giá cũ trái chính sách |
| EX-05 | Hủy sau bàn giao | Shipment đã dispatch | Chuyển sang quy trình phù hợp, không giả lập rollback |
| EX-06 | Gửi request lặp | Cùng idempotency key | Không tạo Order hoặc payment trùng |

Một ví dụ tốt có thể trở thành tài liệu nghiệp vụ, tiêu chí acceptance và nguồn dữ liệu cho test. Khi quy tắc thay đổi, nhóm cập nhật ví dụ trước hoặc cùng lúc với code.

## 4. Dùng Ubiquitous Language để tránh đánh giá sai

Nếu các bên dùng cùng một từ nhưng hiểu khác nhau, test có thể xác nhận một kết quả mà nghiệp vụ không mong muốn.

### 4.1. Phân biệt các trạng thái dễ bị gộp

Trong ví dụ thương mại điện tử:

- Order được tiếp nhận không đồng nghĩa đã được xác nhận.
- Payment được authorize không đồng nghĩa đã capture.
- Inventory có số lượng vật lý không đồng nghĩa có số lượng khả dụng để bán.
- Reservation được tạo không đồng nghĩa hàng đã được đóng gói.
- Shipment được dispatch không đồng nghĩa khách đã nhận hàng.
- Order bị hủy không đồng nghĩa refund đã hoàn tất.

Những phân biệt này cần xuất hiện trong glossary, model, event, API và test.

### 4.2. Tạo glossary theo context

| Thuật ngữ | Ordering | Inventory | Payment | Shipping |
|---|---|---|---|---|
| Confirmed | Đơn thỏa điều kiện xác nhận | Không nhất thiết có nghĩa tương ứng | Không phải trạng thái payment | Không phải trạng thái shipment |
| Reserved | Tham chiếu kết quả giữ hàng | Số lượng được giữ cho một mục đích | Không áp dụng | Có thể là dữ liệu cần giao |
| Authorized | Trạng thái thanh toán được tham chiếu | Không áp dụng | Provider đã chấp thuận hạn mức/ủy quyền | Không áp dụng |
| Dispatched | Có thể là mốc liên quan đến đơn | Không phải trạng thái tồn kho | Không áp dụng | Shipment đã được bàn giao/đưa đi theo định nghĩa |

Cùng một từ có thể có nghĩa khác nhau giữa context. Không nên ép mọi context dùng một enum Status chung chỉ để thuận tiện mapping.

### 4.3. Dùng ví dụ để phát hiện ngôn ngữ mơ hồ

Nếu chuyên gia nói “đơn đã thanh toán”, hãy hỏi:

- Gateway đã authorize hay capture?
- Tiền đã được quyết toán chưa?
- Có thể hoàn tiền không?
- Đơn có thể bị hủy không?
- Payment có thể thất bại sau khi Order đã được xác nhận không?

Câu trả lời quyết định model và test cần có những trạng thái nào.

## 5. Từ ví dụ nghiệp vụ đến mô hình domain

Sau khi thống nhất ví dụ và thuật ngữ, nhóm xác định trách nhiệm, Entity, Value Object, Aggregate và Domain Event.

### 5.1. Phân chia trách nhiệm theo Bounded Context

Một mô hình ban đầu có thể gồm:

- **Pricing Context:** ProductOffer, PriceQuote, Promotion và quy tắc áp dụng giá.
- **Ordering Context:** Order, OrderLine, OrderStatus và quy tắc vòng đời đơn.
- **Inventory Context:** StockItem, Reservation và quy tắc phân bổ số lượng.
- **Payment Context:** Payment, Authorization, Capture, Refund và trạng thái giao dịch.
- **Shipping Context:** Shipment, Tracking và quy trình giao nhận.

Đây là giả thuyết ranh giới, cần được xác nhận theo ownership và ngôn ngữ thực tế. Không phải cứ có một context là bắt buộc có một microservice hoặc database riêng.

### 5.2. Chọn Aggregate theo invariant

Ví dụ, Order Aggregate có thể bảo vệ:

- Chỉ đơn ở trạng thái cho phép mới được đặt.
- Không thêm hoặc sửa dòng hàng sau khi đơn đã được xác nhận, trừ các hành động được chính sách cho phép.
- Tổng tiền trong Order khớp với các dòng và snapshot giá theo quy tắc.
- Mỗi OrderLine thuộc đúng Order.
- Hành vi hủy ghi nhận lý do và trạng thái hợp lệ.

Inventory có thể có Aggregate riêng bảo vệ số lượng khả dụng và Reservation. Không nên để Ordering tự sửa số lượng kho trong database của Inventory.

### 5.3. Dùng Value Object cho giá trị có ý nghĩa

Các kiểu có thể gồm:

~~~java
public record OrderId(UUID value) {}
public record ProductId(UUID value) {}
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
    }
}
public record Money(BigDecimal amount, Currency currency) {}
~~~

Trong code thực tế, Money cần quy tắc precision, rounding và phép toán giữa các currency. Ví dụ ngắn chỉ minh họa rằng kiểu domain giúp biểu đạt ý nghĩa và ngăn một số lỗi truyền nhầm dữ liệu.

### 5.4. Domain Event ghi nhận sự việc đã xảy ra

Một số event trong luồng:

- PriceQuoteAccepted.
- StockReserved.
- OrderPlaced.
- PaymentAuthorized.
- OrderConfirmed.
- OrderCancelled.
- RefundCompleted.
- ShipmentDispatched.

Không phải mọi event đều cần tồn tại. Chỉ tạo event khi nó diễn đạt một sự kiện có ý nghĩa cho domain hoặc integration. Event phải có semantics rõ về thời điểm xảy ra, identity và version/schema nếu được công bố ra ngoài context.

## 6. Xác định Context Map và hợp đồng tích hợp

Context Map mô tả quan hệ giữa các Bounded Context: bên nào cung cấp thông tin, bên nào tiêu thụ, contract được quản lý ra sao và mức phụ thuộc nào được chấp nhận.

### 6.1. Sơ đồ quan hệ sơ bộ

~~~mermaid
flowchart LR
    P["Pricing"] -->|"Price Quote"| O["Ordering"]
    O -->|"Reserve Stock command"| I["Inventory"]
    I -->|"StockReserved event"| O
    O -->|"Authorize Payment command"| Y["Payment"]
    Y -->|"PaymentAuthorized event"| O
    O -->|"Fulfillment request"| S["Shipping"]
    S -->|"Shipment status event"| O
~~~

Sơ đồ này không khẳng định mọi tương tác phải bất đồng bộ. Một quote có thể được lấy đồng bộ; reservation và payment có thể cần command/event tùy yêu cầu về thời gian phản hồi và consistency.

### 6.2. Đánh giá contract thay vì chỉ đánh giá endpoint

Với mỗi ranh giới, cần hỏi:

- Ai sở hữu dữ liệu và quy tắc?
- Consumer có phụ thuộc vào class nội bộ của provider không?
- Schema có version và chính sách tương thích không?
- Có correlation ID và idempotency key không?
- Timeout hoặc message trùng được xử lý thế nào?
- Có thể thay đổi provider mà không buộc consumer sửa domain model không?

Một contract rõ ràng giúp đánh giá được cả hành vi lẫn khả năng tiến hóa.

### 6.3. Dùng Anti-Corruption Layer khi semantics khác nhau

Ordering có thể dùng trạng thái Payment nội bộ như AwaitingAuthorization, Authorized và RefundPending. Payment provider có thể trả mã như PENDING, APPROVED, DECLINED hoặc UNKNOWN. Adapter chuyển đổi các mã ngoài thành khái niệm Payment của context tương ứng.

Không nên để mã enum của nhà cung cấp lan vào Aggregate Order hoặc các context khác.

## 7. Chuyển ví dụ thành Acceptance Criteria

Acceptance Criteria mô tả điều kiện để một capability được chấp nhận từ góc nhìn người dùng và nghiệp vụ. Chúng cần cụ thể, có thể quan sát và không mô tả chi tiết implementation khi không cần thiết.

### 7.1. Dùng Given–When–Then

Ví dụ đặt đơn:

~~~gherkin
Feature: Đặt đơn có khuyến mãi

  Scenario: Đặt đơn khi báo giá và tồn kho còn hiệu lực
    Given khách hàng có báo giá hợp lệ cho 2 sản phẩm
    And báo giá đã bao gồm khuyến mãi được chấp nhận
    And Inventory có thể giữ đủ số lượng
    When khách hàng xác nhận đặt đơn
    Then hệ thống tạo một Order
    And Order lưu snapshot giá đã được chấp nhận
    And Reservation được liên kết với Order
    And khách hàng nhận được mã đơn và trạng thái phù hợp
~~~

Ví dụ payment timeout:

~~~gherkin
Scenario: Payment timeout sau khi provider nhận yêu cầu
  Given Order đang chờ kết quả thanh toán
  And provider có thể đã nhận authorization request
  When hệ thống không nhận được phản hồi trước timeout
  Then Payment được ghi nhận ở trạng thái chưa xác định hoặc đang xử lý
  And hệ thống không tạo một giao dịch mới với identity khác
  And tiến trình tra cứu hoặc retry theo idempotency contract
~~~

Acceptance Criteria cần tránh các từ mơ hồ như “nhanh”, “đúng”, “thân thiện” nếu không có tiêu chí quan sát đi kèm.

### 7.2. Thêm ví dụ biên và quy tắc từ chối

Mỗi capability quan trọng cần ít nhất một số ví dụ từ chối:

- Quote hết hạn.
- Số lượng không hợp lệ.
- Khách không có quyền thao tác.
- Order đã giao nên không thể hủy theo chính sách.
- Reservation không còn hiệu lực.
- Payment bị từ chối.
- Idempotency key được dùng lại với payload khác.

Ví dụ từ chối giúp xác định lỗi là domain rejection, authorization failure, validation failure hay lỗi kỹ thuật.

### 7.3. Acceptance Criteria không thay thế đặc tả chi tiết mọi quy tắc

Một số quy tắc phức tạp cần decision table, state transition table hoặc policy specification. Ví dụ tính khuyến mãi có thể phụ thuộc nhóm khách, thời gian, kênh bán và số lượng. Hãy dùng hình thức diễn đạt phù hợp với độ phức tạp, nhưng giữ nguồn thuật ngữ và quyết định nhất quán.

## 8. Xây dựng chiến lược kiểm thử từ ví dụ

Không có một loại test nào đủ để đánh giá toàn bộ sản phẩm. Hãy ánh xạ mỗi ví dụ vào tầng test phù hợp, nơi có thể kiểm chứng hành vi với chi phí hợp lý.

### 8.1. Unit Test cho Value Object và Aggregate

Kiểm tra quy tắc thuần domain:

~~~java
@Test
void cannotCancelDeliveredOrder() {
    Order order = TestOrders.delivered();

    assertThrows(
        OrderCannotBeCancelledException.class,
        () -> order.cancel(CancellationReason.customerRequest())
    );
}
~~~

Unit Test cần nhanh, độc lập với database, HTTP và broker. Nó phù hợp với invariant, phép tính và chuyển trạng thái.

### 8.2. Application Test cho điều phối

Dùng fake Repository và fake ports để kiểm tra use case:

- Tải đúng Order.
- Gọi hành vi domain.
- Lưu Aggregate khi thành công.
- Không phát lệnh tích hợp khi domain từ chối.
- Ghi command/event theo contract.
- Xử lý quyền truy cập ở boundary.

Test này không cần chứng minh SQL đúng; Repository Integration Test sẽ làm điều đó.

### 8.3. Repository Integration Test cho persistence

Dùng database engine phù hợp để kiểm tra:

- Lưu và nạp lại Aggregate.
- Identity và Value Object được bảo toàn.
- Entity con và quan hệ được tái tạo.
- Constraint và transaction hoạt động.
- Optimistic locking phát hiện ghi đồng thời.
- Query, sorting và pagination đúng.

Với ORM, cần flush và clear persistence context trước khi xác minh rehydration để tránh đọc lại object trong bộ nhớ.

### 8.4. Contract Test cho ranh giới context

Kiểm tra consumer và provider hiểu cùng một contract:

- Field bắt buộc và tùy chọn.
- Enum và schema version.
- Semantics của trạng thái.
- Idempotency và correlation.
- Quy tắc tương thích khi thêm hoặc thay đổi field.

Contract Test đặc biệt hữu ích khi hai context được triển khai độc lập.

### 8.5. End-to-End Test cho luồng quan trọng

E2E kiểm tra đường đi qua hệ thống gần với người dùng thật: từ API/UI, application, database và tích hợp cần thiết đến kết quả cuối.

Không cần viết E2E cho mọi nhánh nhỏ. Chọn một số luồng có giá trị cao như đặt đơn thành công, payment bị từ chối, hủy đơn và hoàn tiền. Các trường hợp chi tiết nên được kiểm tra ở unit, application và integration test để E2E không trở thành bộ test chậm và chập chờn.

### 8.6. Test theo rủi ro và ví dụ

| Ví dụ | Unit | Application | Integration | Contract/E2E |
|---|---|---|---|---|
| Tính tổng tiền | Money/Price policy | Use case chọn quote | Mapping snapshot | Checkout E2E |
| Giữ sản phẩm cuối | Invariant trong Inventory | Reservation workflow | Lock/constraint | Luồng mua cạnh tranh |
| Payment timeout | State transition | Retry/lookup policy | Provider adapter | Payment scenario |
| Hủy sau dispatch | Cancellation policy | Saga orchestration | Outbox/inbox | Luồng hủy và hoàn hàng |
| Request lặp | Idempotency domain rule nếu có | Command deduplication | Unique key/store | API retry scenario |

Không phải mọi ô đều cần một test riêng. Bảng giúp chỉ ra bằng chứng cần có và tránh bỏ sót rủi ro ở ranh giới.

## 9. Đánh giá chất lượng của bộ kiểm thử

Một bộ test lớn chưa chắc có giá trị nếu nó chỉ kiểm tra cấu trúc code hoặc không bao phủ các quyết định nghiệp vụ quan trọng.

### 9.1. Đánh giá theo ví dụ và rủi ro

Với mỗi ví dụ quan trọng, ghi:

- Có acceptance example chưa?
- Quy tắc domain nào bảo vệ kết quả?
- Có unit test cho invariant chưa?
- Có integration test cho persistence hoặc transaction chưa?
- Có contract test cho ranh giới không?
- Có E2E cho hành trình quan trọng không?
- Có metric/log để phát hiện lỗi sau release không?

Khoảng trống trong ma trận cho biết nơi cần bổ sung bằng chứng.

### 9.2. Tránh test implementation detail

Test không nên thất bại chỉ vì đổi tên private method hoặc thay cấu trúc class mà hành vi vẫn giữ nguyên. Ưu tiên quan sát qua public contract: kết quả, trạng thái, event, dữ liệu lưu và phản hồi của API.

Một test kiểm tra chính xác thứ tự gọi mock có thể hữu ích khi thứ tự là contract. Nếu thứ tự chỉ là chi tiết nội bộ, assertion đó làm test mong manh.

### 9.3. Dùng mutation testing có chọn lọc

Mutation testing thay đổi nhỏ code để xem test có phát hiện sai lệch hay không. Nếu bỏ một điều kiện quan trọng mà toàn bộ test vẫn xanh, có thể bộ test chưa bảo vệ quy tắc đó.

Không cần đặt mục tiêu mutation score tuyệt đối cho toàn bộ codebase. Dùng kỹ thuật này ở domain policy, tính tiền, trạng thái và các quy tắc có hậu quả lớn.

### 9.4. Kiểm tra dữ liệu và test fixture

Fixture cần có dữ liệu phân biệt đủ để kiểm tra filter, boundary và thứ tự. Không dùng một Order duy nhất cho mọi test query. Cố định Clock và dữ liệu thời gian khi quy tắc phụ thuộc thời điểm. Tạo Aggregate qua factory/domain API để fixture không bỏ qua invariant.

### 9.5. Test phải có khả năng chạy lặp lại

Kiểm tra tính ổn định:

- Không phụ thuộc thứ tự test.
- Không dùng dữ liệu dùng chung có thể bị test khác sửa.
- Không chờ bằng sleep tùy tiện.
- Có timeout hợp lý.
- Có thể chạy trong CI.
- Container và dependency được quản lý rõ.
- Lỗi test có thông tin đủ để chẩn đoán.

## 10. Đưa ra quyết định kiến trúc từ bằng chứng

Quyết định kiến trúc nên trả lời một vấn đề cụ thể, nêu lựa chọn đã cân nhắc, trade-off và lý do. Không nên chọn pattern chỉ vì nó phổ biến.

### 10.1. Mẫu ghi Architecture Decision Record

Một ADR tối thiểu có thể gồm:

- **Context:** Vấn đề và bối cảnh nghiệp vụ/kỹ thuật.
- **Decision:** Lựa chọn được chấp nhận.
- **Alternatives:** Các phương án đã xem xét.
- **Consequences:** Lợi ích, chi phí, rủi ro và điều phải vận hành.
- **Evidence:** Ví dụ, test, metric hoặc giả định hỗ trợ.
- **Review trigger:** Điều kiện khiến quyết định cần được xem xét lại.

ADR là bản ghi quyết định, không phải tài liệu thiết kế dài thay cho code và test.

### 10.2. Ví dụ ADR: Modular Monolith trước Microservices

**Context:** Ordering, Pricing và Inventory hiện nằm trong một ứng dụng lớn. Các nhóm muốn thay đổi độc lập nhưng ranh giới domain và ownership dữ liệu chưa được kiểm chứng.

**Decision:** Tổ chức các Bounded Context thành module có contract rõ trong modular monolith trước; chưa tách deployment.

**Alternatives:** Giữ cấu trúc package hiện tại; tách ngay thành microservices; dùng modular monolith và đánh giá lại sau pilot.

**Consequences:**

- Có thể thiết lập ownership và kiểm thử ranh giới mà chưa thêm chi phí vận hành phân tán.
- Các module vẫn dùng chung process và có thể dùng transaction nội bộ khi phù hợp.
- Cần ngăn truy cập trực tiếp database hoặc class nội bộ xuyên module.
- Việc tách service sau này vẫn cần thiết kế contract, data ownership và consistency.

**Evidence:** Nhiều thay đổi hiện tại chạm cùng bảng và class; chưa có nhu cầu scale hoặc deploy độc lập đủ mạnh; test hiện tại chưa bảo vệ context boundary.

Quyết định này có thể được xem xét lại khi một context có nhu cầu triển khai, mở rộng hoặc ownership độc lập rõ ràng.

### 10.3. Ví dụ ADR: Outbox cho tích hợp bất đồng bộ

**Context:** Ordering cần công bố OrderPlaced. Nếu database commit nhưng publish message thất bại, consumer không nhận được sự kiện; nếu publish trước commit, consumer có thể xử lý một Order chưa tồn tại.

**Decision:** Ghi Order và Outbox trong cùng database transaction; publisher gửi message sau commit.

**Alternatives:** Publish trực tiếp trong transaction; dùng distributed transaction; dùng CDC; ghi Outbox và worker polling.

**Consequences:**

- Tránh khoảng hở giữa database commit và ý định publish.
- Message có thể được gửi nhiều lần nên consumer phải idempotent.
- Cần theo dõi backlog, retry và dead-letter.
- Có thêm bảng, worker và vận hành publisher.

**Evidence:** Test rollback chứng minh Order và Outbox cùng commit; test redelivery chứng minh consumer xử lý trùng an toàn.

### 10.4. Ví dụ ADR: Tính nhất quán của tồn kho

**Context:** Hai yêu cầu có thể cùng mua đơn vị tồn kho cuối cùng. Một projection đọc chậm không đủ để quyết định reservation.

**Decision:** Inventory là nguồn có thẩm quyền cho reservation; thao tác giữ hàng dùng transaction/locking hoặc cơ chế atomic phù hợp trong Inventory.

**Alternatives:** Ordering tự đọc bảng kho; dùng cache; cập nhật số lượng bất đồng bộ mà không có reservation; gọi Inventory qua command.

**Consequences:**

- Không để Ordering tự sửa số lượng kho.
- Có thể phát sinh thời gian chờ khi gọi Inventory.
- Cần idempotency cho yêu cầu giữ hàng và xử lý timeout.
- Read model có thể trễ nhưng không được dùng thay nguồn có thẩm quyền cho quyết định giữ hàng.

**Evidence:** Test concurrency xác minh chỉ một reservation thành công cho đơn vị cuối; contract test kiểm tra kết quả giữ hàng.

## 11. Đánh giá các lựa chọn kiến trúc theo trade-off

Mỗi lựa chọn cần được đánh giá theo outcome và rủi ro, không theo sở thích công nghệ.

### 11.1. Modular Monolith hay Microservices?

| Tiêu chí | Modular Monolith | Microservices |
|---|---|---|
| Ranh giới domain | Có thể tách logic trong cùng ứng dụng | Cần contract qua network |
| Transaction | Dễ dùng transaction trong một database | Thường cần consistency phân tán |
| Triển khai | Một đơn vị hoặc một số đơn vị lớn | Có thể triển khai độc lập |
| Vận hành | Ít thành phần phân tán hơn | Cần observability, retry, service discovery, security |
| Phù hợp khi | Ranh giới đang được xác lập, đội nhỏ/vừa | Ownership và nhu cầu độc lập đã rõ |

Microservices không tự làm domain model tốt hơn. Nếu ranh giới sai, hệ thống chỉ chuyển coupling từ code thành network call.

### 11.2. Synchronous hay Asynchronous?

| Tiêu chí | Đồng bộ | Bất đồng bộ |
|---|---|---|
| Phản hồi | Có kết quả ngay trong request nếu thành công | Thường trả accepted/pending |
| Coupling thời gian | Caller phụ thuộc availability của callee | Producer và consumer tách thời gian |
| Consistency | Có thể đọc kết quả tức thời theo contract | Thường có eventual consistency |
| Lỗi | Timeout và lỗi lan truyền qua call chain | Retry, duplicate, ordering, DLQ |
| Phù hợp | Tra cứu/ra quyết định cần kết quả tức thời | Workflow kéo dài hoặc xử lý nền |

Đừng dùng asynchronous chỉ để tránh một API chậm. Cần xác định trạng thái pending, idempotency và cách người dùng quan sát kết quả.

### 11.3. Một mô hình ghi hay tách CQRS?

CQRS hữu ích khi nhu cầu ghi và đọc có cấu trúc, tải hoặc consistency khác nhau đáng kể. Nếu sản phẩm nhỏ, một Repository và vài query đơn giản có thể đủ. Tách read model tạo thêm projector, lag, replay và vận hành; chỉ nên làm khi lợi ích đọc bù được chi phí đó.

### 11.4. Database dùng chung hay database riêng?

Database riêng theo context có thể tăng ownership và giảm coupling, nhưng migration, reporting, data replication và vận hành phức tạp hơn. Database dùng chung vẫn có thể có module boundary nếu quyền truy cập bảng được kiểm soát. Đừng coi database-per-service là mục tiêu bắt buộc khi domain boundary chưa rõ.

### 11.5. Chọn theo bằng chứng

Với mỗi quyết định, hãy chỉ ra:

- Outcome nào được cải thiện?
- Ví dụ nghiệp vụ nào chứng minh nhu cầu?
- Test nào bảo vệ lựa chọn?
- Metric nào cho thấy hệ thống đang hoạt động?
- Chi phí vận hành mới là gì?
- Điều kiện nào khiến quyết định cần xem xét lại?

Nếu không thể trả lời các câu hỏi này, quyết định có thể đang dựa quá nhiều vào xu hướng hoặc giả định.

## 12. Kiểm tra các quality attribute và khả năng vận hành

Đánh giá sản phẩm không chỉ kiểm tra chức năng. Các thuộc tính chất lượng cần gắn với tình huống sử dụng và mức chấp nhận cụ thể.

### 12.1. Reliability

Ví dụ: khi Payment provider timeout, hệ thống có tránh tạo giao dịch trùng và có thể tiếp tục tra cứu trạng thái không?

Bằng chứng:

- Test timeout và retry.
- Idempotency key.
- Outbox/inbox.
- Metric retry và pending payment.
- Runbook xử lý giao dịch chưa xác định.

### 12.2. Performance

Ví dụ: trang lịch sử đơn với 20 dòng trên một trang có phản hồi trong giới hạn sản phẩm chấp nhận không?

Bằng chứng:

- Load test với dữ liệu đại diện.
- Query plan và index.
- Projection hoặc pagination nếu cần.
- p95/p99 latency.
- Số query và payload size.

Không dùng một con số latency chung cho mọi endpoint. Xác định SLO theo hành trình và mức độ ảnh hưởng.

### 12.3. Security và privacy

Ví dụ: khách A không thể đọc hoặc hủy Order của khách B chỉ bằng cách đổi Order ID.

Bằng chứng:

- Authorization test theo đối tượng.
- Audit trail cho thao tác nhạy cảm.
- DTO allowlist.
- Kiểm tra dữ liệu cá nhân trong log và event.
- Chính sách lưu trữ/xóa dữ liệu.

### 12.4. Observability

Ví dụ: từ một yêu cầu checkout, đội vận hành có thể truy vết Order, Reservation và Payment liên quan không?

Bằng chứng:

- Correlation ID xuyên context.
- Structured logs.
- Trace các lời gọi quan trọng.
- Metric về trạng thái workflow.
- Dashboard và alert theo SLO.

### 12.5. Evolvability

Ví dụ: Pricing thay đổi cách tính khuyến mãi mà Ordering không cần biết cấu trúc nội bộ mới.

Bằng chứng:

- Contract test.
- Module dependency rule.
- ADR và migration plan.
- Test bảo vệ semantics.
- Số module/caller bị ảnh hưởng trong thay đổi thực tế.

## 13. Dùng Architecture Fitness Functions để bảo vệ quyết định

Một quyết định kiến trúc sẽ mất tác dụng nếu code mới liên tục phá vỡ ranh giới. Fitness Function là kiểm tra tự động để phát hiện vi phạm các thuộc tính kiến trúc đã chọn.

Ví dụ:

- Ordering không được import package persistence nội bộ của Inventory.
- Domain module không được phụ thuộc Spring Web hoặc SDK của Payment provider.
- Mọi message integration cần có event ID và schema version.
- Consumer phải có cơ chế deduplication.
- API công khai không được trả trực tiếp JPA Entity.
- Các module chỉ truy cập dữ liệu qua contract đã công bố.

Một kiểm tra dependency có thể dùng ArchUnit:

~~~java
@AnalyzeClasses(packages = "com.example")
class DomainArchitectureTest {

    @ArchTest
    static final ArchRule domainMustNotDependOnSpring =
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat()
            .resideInAnyPackage("org.springframework..");
}
~~~

Rule này là ví dụ; package và chính sách thật cần điều chỉnh. Không nên cấm dependency chỉ vì muốn có một kiến trúc “sạch” trên giấy. Mỗi rule cần bảo vệ một ranh giới có ý nghĩa và có owner chịu trách nhiệm.

## 14. Hồ sơ đánh giá sản phẩm và quyết định release

Một phiên đánh giá nên tạo hồ sơ ngắn gọn nhưng có thể truy vết. Hồ sơ có thể dùng trong refinement, architecture review hoặc release readiness.

### 14.1. Mẫu Product Evaluation Record

| Mục | Nội dung cần ghi |
|---|---|
| Capability | Khả năng nghiệp vụ được đánh giá |
| Outcome | Kết quả mong muốn cho người dùng/doanh nghiệp |
| Actors | Người hoặc hệ thống tham gia |
| Examples | Happy path, edge case, failure case |
| Domain model | Entity, Value Object, Aggregate, Event liên quan |
| Context boundary | Context sở hữu quy tắc và dữ liệu |
| Tests | Unit, application, integration, contract, E2E |
| Architecture decisions | ADR và lựa chọn được chấp nhận |
| Quality attributes | Performance, reliability, security, observability |
| Evidence | Test result, metric, trace, demo, dữ liệu |
| Risks | Rủi ro còn lại và cách giảm thiểu |
| Decision | Accept, accept with conditions, defer hoặc reject |
| Owner | Người chịu trách nhiệm và thời điểm xem xét lại |

### 14.2. Không dùng một điểm tổng để che giấu rủi ro nghiêm trọng

Có thể dùng thang điểm để so sánh, nhưng một lỗi bảo mật nghiêm trọng hoặc nguy cơ mất dữ liệu không thể được bù bằng điểm UX cao. Hãy tách:

- Điều kiện bắt buộc (release gate).
- Chất lượng có thể cải thiện sau release.
- Rủi ro đã chấp nhận.
- Vấn đề cần hoãn phát hành.

### 14.3. Các dạng quyết định

- **Accept:** ví dụ quan trọng đã được xác minh và không còn rủi ro chặn.
- **Accept with conditions:** có thể phát hành khi kèm guardrail, monitoring hoặc giới hạn rõ.
- **Defer:** cần thêm bằng chứng, test hoặc quyết định nghiệp vụ.
- **Reject:** giải pháp không đáp ứng outcome hoặc tạo rủi ro không chấp nhận được.

Ghi rõ người có thẩm quyền chấp nhận rủi ro. Đội kỹ thuật có thể cung cấp phân tích, nhưng không tự quyết định thay nghĩa vụ kinh doanh hoặc pháp lý.

## 15. Quy trình thực hành đánh giá từ đầu đến cuối

Một quy trình có thể lặp lại cho mỗi capability:

1. **Chọn outcome.** Mô tả kết quả người dùng hoặc doanh nghiệp cần đạt.
2. **Chọn lát cắt nghiệp vụ.** Giới hạn actor, trigger, dữ liệu và hệ thống liên quan.
3. **Viết concrete examples.** Có happy path, trường hợp biên, lỗi và hành động lặp.
4. **Thống nhất Ubiquitous Language.** Làm rõ từ mơ hồ và trạng thái gần giống nhau.
5. **Mô hình hóa domain.** Xác định Entity, Value Object, Aggregate, invariant và Domain Event.
6. **Xác định Bounded Context.** Ghi ownership, contract và Context Map.
7. **Viết Acceptance Criteria.** Dùng Given–When–Then hoặc decision table phù hợp.
8. **Ánh xạ ví dụ sang test.** Chọn unit, application, integration, contract và E2E theo rủi ro.
9. **Đưa ra ADR.** Ghi context, decision, alternatives, consequences và evidence.
10. **Đánh giá quality attributes.** Reliability, performance, security, observability và evolvability.
11. **Chạy test và thu thập bằng chứng.** Gắn kết quả test, metric và trace với từng ví dụ.
12. **Đánh giá rủi ro còn lại.** Phân biệt blocker, risk accepted và follow-up.
13. **Ra quyết định.** Accept, accept with conditions, defer hoặc reject.
14. **Theo dõi sau release.** So sánh outcome với baseline và xem lại ADR khi trigger xuất hiện.

## 16. Ví dụ tổng hợp: đánh giá capability checkout

Giả sử sản phẩm chuẩn bị phát hành checkout mới có khuyến mãi và thanh toán bất đồng bộ.

### 16.1. Outcome và ví dụ

Outcome: khách đặt được đơn với giá minh bạch, không bán vượt tồn kho và có thể biết trạng thái thanh toán.

Ví dụ cần kiểm tra:

- Quote hợp lệ và reservation thành công.
- Quote hết hạn trước khi xác nhận.
- Hai khách cùng giữ sản phẩm cuối.
- Payment timeout nhưng provider đã nhận request.
- Client retry cùng idempotency key.
- Order bị hủy khi reservation đã tạo.
- Payment được capture nhưng thông báo về Ordering đến chậm.

### 16.2. Domain và context

- Pricing sở hữu quote và policy khuyến mãi.
- Inventory sở hữu reservation.
- Payment sở hữu trạng thái giao dịch.
- Ordering sở hữu vòng đời đơn.
- Checkout Application Use Case điều phối các bước theo chính sách đã thống nhất.

Mỗi context có model và contract riêng. Ordering không sửa trực tiếp bảng Inventory hoặc Payment.

### 16.3. Bằng chứng test

| Rủi ro | Test cần có | Kết quả cần chứng minh |
|---|---|---|
| Tính sai giá | Unit test Price Policy | Tổng tiền và rounding đúng |
| Bán vượt tồn | Inventory concurrency integration test | Chỉ reservation hợp lệ được tạo |
| Tạo đơn trùng | Application/integration idempotency test | Cùng key không tạo giao dịch mới |
| Payment không rõ kết quả | Adapter contract test | Retry/lookup tuân thủ provider contract |
| Message gửi lại | Consumer integration test | Xử lý duplicate an toàn |
| Hủy giữa workflow | Saga test | Trạng thái và hành động bù đúng |
| Khách xem đơn quá sớm | E2E/UX test | Trạng thái pending được diễn đạt rõ |

### 16.4. Quyết định kiến trúc

ADR có thể chọn:

- Modular boundary giữa các context trước khi tách deployment.
- Inventory giữ reservation bằng thao tác atomic.
- Outbox cho event từ Ordering.
- Payment adapter sử dụng idempotency key và trạng thái UNKNOWN/PENDING.
- Saga theo dõi các bước bất đồng bộ.
- Query model có thể trễ nhưng checkout response trả kết quả command rõ ràng.

Các lựa chọn này cần được kiểm chứng qua test và vận hành. Nếu volume hoặc yêu cầu triển khai độc lập thay đổi, ADR có thể được xem xét lại.

### 16.5. Quyết định phát hành

Không chỉ nhìn toàn bộ test đều xanh. Release review cần xem:

- Những ví dụ rủi ro cao có test phù hợp chưa?
- Contract giữa các context có tương thích không?
- Metric về reservation, payment pending và duplicate request có sẵn chưa?
- Có runbook xử lý payment chưa xác định không?
- Có rollback hoặc feature flag cho checkout mới không?
- Support team có hiểu các trạng thái mới không?

Nếu payment timeout chưa có cách tra cứu trạng thái và có thể tạo giao dịch trùng, đó là blocker cần xử lý trước khi mở rộng traffic, dù happy path đang chạy tốt.

## 17. Những sai lầm thường gặp

**Đánh giá theo số lượng tính năng.** Nhiều tính năng không chứng minh sản phẩm tạo ra outcome. Đánh giá theo công việc người dùng hoàn thành và kết quả đo được.

**Chỉ viết happy path.** Các lỗi concurrency, timeout, duplicate và trạng thái trung gian thường gây hậu quả lớn. Bổ sung ví dụ biên theo rủi ro.

**Viết test sau khi code xong mà không có ví dụ nghiệp vụ.** Test dễ xác nhận implementation hiện tại thay vì yêu cầu thật. Dùng concrete example làm nguồn cho acceptance và test.

**Dùng một enum Status cho nhiều context.** Trạng thái có semantics và vòng đời khác nhau. Định nghĩa model riêng và mapping qua contract.

**Dùng E2E để kiểm tra mọi thứ.** E2E chậm và khó chẩn đoán. Phân bổ kiểm thử theo ranh giới và rủi ro.

**Mock mọi dependency trong Integration Test.** Test không còn xác minh persistence hoặc contract thật. Dùng database, broker hoặc provider simulator phù hợp ở các test cần thiết.

**Chọn microservices chỉ vì muốn scale.** Tách service khi ownership, contract và nhu cầu độc lập đủ rõ; nếu chưa, modular monolith có thể là bước hợp lý.

**Dùng event cho mọi tương tác.** Eventual consistency và vận hành message có chi phí. Chọn đồng bộ hay bất đồng bộ theo yêu cầu nghiệp vụ.

**Ghi ADR mà không ghi trade-off.** Một quyết định không có hậu quả và điều kiện xem xét lại sẽ nhanh chóng mất ý nghĩa. Ghi alternatives và review trigger.

**Đồng nhất test xanh với release an toàn.** Test không thể bao phủ mọi rủi ro. Kết hợp test với metric, monitoring, runbook và đánh giá rủi ro còn lại.

**Không đo outcome sau release.** Nếu không so sánh baseline, nhóm không biết quyết định kiến trúc có cải thiện sản phẩm hay không. Theo dõi chỉ số đã thống nhất.

## 18. Checklist đánh giá tích hợp

**Outcome và ví dụ**

- Outcome có mô tả giá trị cho người dùng/doanh nghiệp không?
- Actor và trigger đã rõ chưa?
- Có happy path, edge case, failure case và duplicate request chưa?
- Kết quả có thể quan sát và đo được không?
- Chuyên gia nghiệp vụ đã xác nhận semantics chưa?

**Domain và context**

- Ubiquitous Language đã được thống nhất theo context chưa?
- Entity, Value Object và Aggregate có invariant rõ không?
- Domain Event mô tả sự việc đã xảy ra chưa?
- Mỗi context có ownership dữ liệu và quy tắc không?
- Context Map có thể hiện contract và phụ thuộc quan trọng không?

**Kiểm thử**

- Invariant có Unit Test không?
- Use case có Application Test không?
- Persistence và transaction có Integration Test không?
- Context boundary có Contract Test không?
- Luồng quan trọng có E2E không?
- Test có kiểm tra duplicate, concurrency và timeout khi phù hợp không?
- Test có ổn định và chạy được trong CI không?

**Quyết định kiến trúc**

- Vấn đề và bối cảnh đã được mô tả chưa?
- Alternatives và trade-off đã được cân nhắc chưa?
- Decision có bằng chứng từ ví dụ/test/metric không?
- Có xác định consistency, transaction và failure handling không?
- Có review trigger và owner không?
- Có fitness function bảo vệ ranh giới quan trọng không?

**Release và vận hành**

- Release gate và rủi ro chấp nhận đã được phân biệt chưa?
- Có baseline và metric theo dõi outcome không?
- Có log, trace, correlation ID và alert phù hợp không?
- Có runbook, retry, rollback hoặc feature flag khi cần không?
- Nhóm hỗ trợ và người dùng hiểu trạng thái mới không?
- Có lịch đánh giá lại sau release không?

## 19. Kết luận

Đánh giá sản phẩm bằng DDD cần kết nối ví dụ nghiệp vụ, kiểm thử và quyết định kiến trúc thành một chuỗi bằng chứng. Ví dụ cụ thể giúp làm rõ người dùng cần gì và quy tắc nào phải được bảo vệ. Ubiquitous Language và Bounded Context giúp xác định mô hình cùng ownership. Test ở nhiều tầng chứng minh hành vi và contract được thực hiện đúng. ADR giải thích trade-off và lý do chọn cách tổ chức hệ thống.

Không có một kiến trúc hay bộ test phù hợp cho mọi sản phẩm. Modular monolith, microservices, synchronous call, event-driven workflow, CQRS hoặc một Repository đơn giản đều có thể đúng nếu chúng giải quyết vấn đề đã được xác nhận với chi phí chấp nhận được. Điều quan trọng là mỗi lựa chọn phải gắn với outcome, ví dụ rủi ro, bằng chứng kiểm thử và khả năng vận hành.

Một buổi đánh giá tốt kết thúc bằng quyết định rõ: điều gì đã được chứng minh, điều gì còn là giả thuyết, rủi ro nào được chấp nhận, ai chịu trách nhiệm và khi nào cần xem xét lại. Nhờ vậy, DDD không chỉ là cách tổ chức class mà trở thành phương pháp giúp đội ngũ hiểu sản phẩm, bảo vệ quy tắc và đưa ra quyết định kiến trúc có cơ sở.

