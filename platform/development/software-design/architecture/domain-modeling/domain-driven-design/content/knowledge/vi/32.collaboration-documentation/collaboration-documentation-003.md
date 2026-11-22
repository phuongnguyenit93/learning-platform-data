# Ghi quyết định về ranh giới, bất biến và lựa chọn nhất quán

Trong Domain-Driven Design (DDD), đội phát triển phải đưa ra nhiều quyết định ảnh hưởng lâu dài đến cách mô hình nghiệp vụ được tổ chức và vận hành: một Bounded Context bắt đầu và kết thúc ở đâu, Aggregate bảo vệ những invariant nào, dữ liệu nào phải được cập nhật nguyên tử, phần nào có thể nhất quán trễ và các context phối hợp với nhau bằng API, event hay quy trình Saga.

Những quyết định này thường được hình thành qua workshop, trao đổi với chuyên gia nghiệp vụ, review code và thử nghiệm kỹ thuật. Nếu chỉ lưu kết quả trong đầu người tham gia hoặc trong một đoạn chat, người đến sau khó biết vì sao hệ thống được thiết kế như vậy. Khi một yêu cầu mới xuất hiện, đội ngũ có thể lặp lại cuộc tranh luận cũ hoặc vô tình phá vỡ một ràng buộc quan trọng.

**Ghi quyết định kiến trúc** là cách lưu lại bối cảnh, lựa chọn, lý do, phương án đã cân nhắc và hệ quả dự kiến để mọi người có thể hiểu, kiểm tra và xem xét lại. Trong DDD, decision record đặc biệt hữu ích cho ranh giới Bounded Context, Aggregate boundary, invariant và consistency strategy.

Mục tiêu không phải tạo tài liệu thật dài cho mọi thay đổi. Mục tiêu là để một người không tham gia cuộc thảo luận ban đầu vẫn hiểu quyết định nào đang có hiệu lực, quyết định đó bảo vệ điều gì và điều kiện nào có thể khiến đội ngũ cần xem xét lại.

## 1. Vì sao cần ghi quyết định?

### 1.1. Kết quả không giải thích được lý do sẽ nhanh chóng mất ngữ cảnh

Giả sử một nhóm thống nhất rằng Ordering và Inventory là hai Bounded Context riêng. Nếu chỉ ghi “tách Ordering khỏi Inventory”, người đọc chưa biết:

- Hai context có trách nhiệm nghiệp vụ khác nhau ở điểm nào?
- Vì sao không dùng chung một mô hình Product/Stock?
- Ai sở hữu số lượng tồn khả dụng?
- Khi đơn hàng được xác nhận, việc giữ chỗ tồn kho diễn ra đồng bộ hay bất đồng bộ?
- Nếu Inventory phản hồi thất bại, Ordering phải làm gì?
- Quyết định này dựa trên quy mô hiện tại hay là yêu cầu dài hạn?

Không có bối cảnh và lý do, người khác có thể hợp nhất hai context để giảm số module, hoặc tạo một API đồng bộ mới mà không nhận ra trade-off đã được thảo luận.

### 1.2. Quyết định có hệ quả vượt ra ngoài một class

Một quyết định về Aggregate boundary có thể ảnh hưởng đến:

- Transaction scope.
- Cách tổ chức repository.
- Concurrency control và locking.
- API và event contract.
- Cách kiểm thử invariant.
- Cách chia công việc giữa các team.

Một quyết định về eventual consistency có thể ảnh hưởng đến:

- Trải nghiệm người dùng khi dữ liệu chưa cập nhật.
- Retry và idempotency.
- Outbox/Inbox.
- Monitoring và vận hành sự cố.
- Quy trình bù trừ khi một bước thất bại.

Vì vậy, các quyết định này cần được giải thích ở cấp độ nghiệp vụ và kiến trúc, không chỉ bằng tên class hoặc sơ đồ database.

### 1.3. Tài liệu quyết định giúp tránh tranh luận lặp lại

Một decision record tốt cho phép đội ngũ nói:

- Quyết định hiện tại là gì?
- Nó được đưa ra trong bối cảnh nào?
- Những phương án nào đã được cân nhắc?
- Vì sao phương án được chọn phù hợp hơn?
- Hệ quả nào đã được chấp nhận?
- Điều gì sẽ khiến quyết định cần được xem xét lại?

Khi bối cảnh thay đổi, đội ngũ có thể mở lại quyết định dựa trên bằng chứng mới thay vì tranh luận như thể chưa từng có lịch sử.

## 2. Decision Record và Architecture Decision Record

### 2.1. Decision Record là gì?

Decision Record là một tài liệu ngắn, có cấu trúc, mô tả một quyết định quan trọng và lý do của nó. Architecture Decision Record (ADR) là cách phổ biến để ghi quyết định kiến trúc theo dạng này.

Một ADR thường tập trung vào một quyết định có phạm vi rõ, ví dụ:

- Ordering và Inventory là hai Bounded Context riêng.
- Order aggregate sở hữu OrderLine nhưng không sở hữu Payment.
- Tồn kho được giữ chỗ bằng quy trình bất đồng bộ.
- Mỗi service dùng Transactional Outbox để phát integration event.
- Billing lưu version hợp đồng đã áp dụng trong từng hóa đơn.

### 2.2. ADR khác với tài liệu thiết kế tổng thể

| Tài liệu | Câu hỏi chính | Nội dung |
|---|---|---|
| Domain glossary | Thuật ngữ có nghĩa gì? | Tên khái niệm và định nghĩa |
| Context map | Các context liên hệ ra sao? | Upstream/downstream, quan hệ tích hợp |
| Model/design document | Mô hình được tổ chức thế nào? | Entity, Value Object, Aggregate, workflow |
| ADR | Vì sao chọn phương án này? | Bối cảnh, lựa chọn, alternatives, consequences |
| Runbook | Khi vận hành cần làm gì? | Kiểm tra, xử lý lỗi, phục hồi |
| API/event contract | Hai bên trao đổi dữ liệu thế nào? | Schema, semantics, versioning |

Các tài liệu này bổ sung cho nhau. ADR có thể liên kết tới context map, model diagram, code và runbook thay vì sao chép toàn bộ nội dung.

### 2.3. Khi nào nên tạo ADR?

Nên ghi quyết định khi nó:

- Ảnh hưởng đến ranh giới Bounded Context hoặc quyền sở hữu dữ liệu.
- Định nghĩa Aggregate boundary hoặc invariant quan trọng.
- Chọn consistency model, transaction boundary hoặc cơ chế phối hợp.
- Tạo contract được nhiều module/team sử dụng.
- Có trade-off đáng kể về độ tin cậy, hiệu năng, chi phí hoặc khả năng vận hành.
- Khó đảo ngược hoặc tốn kém nếu thay đổi sau này.
- Giải quyết một tranh luận lặp lại giữa các nhóm.

Không cần ADR cho mọi đổi tên method, sửa lỗi nhỏ hoặc lựa chọn implementation cục bộ dễ đảo ngược. Có thể dùng pull request description hoặc code comment cho các thay đổi nhỏ.

### 2.4. Một ADR nên ghi một quyết định

Tránh gộp các quyết định không liên quan vào một tài liệu dài. Ví dụ, “tách Inventory thành service riêng”, “dùng Kafka” và “dùng PostgreSQL” có thể là ba quyết định có lý do và vòng đời khác nhau.

Chúng có thể liên kết với nhau, nhưng nên tách nếu mỗi quyết định có thể được xem xét hoặc thay thế độc lập.

## 3. Cấu trúc của một quyết định tốt

Một ADR có thể dùng các phần sau:

| Phần | Nội dung cần trả lời |
|---|---|
| Title/ID | Quyết định về điều gì? |
| Status | Đang đề xuất, đã chấp nhận hay đã bị thay thế? |
| Date/Owners | Khi nào và ai chịu trách nhiệm? |
| Context | Vấn đề, bối cảnh nghiệp vụ và ràng buộc là gì? |
| Decision drivers | Tiêu chí nào quan trọng nhất? |
| Decision | Đội ngũ chọn phương án nào? |
| Alternatives | Những phương án nào đã cân nhắc? |
| Rationale | Vì sao lựa chọn phù hợp với bối cảnh? |
| Consequences | Lợi ích, chi phí và rủi ro nào được chấp nhận? |
| Validation | Làm sao biết quyết định đang hoạt động đúng? |
| Revisit conditions | Điều kiện nào khiến cần xem xét lại? |
| Related records | Quyết định và tài liệu nào có liên quan? |

Không phải ADR nào cũng cần đủ mọi phần. Với quyết định nhỏ, có thể rút gọn. Với quyết định về dữ liệu tài chính hoặc consistency, phần consequences, validation và revisit conditions thường cần chi tiết hơn.

## 4. Template ADR có thể dùng trong dự án

Một template Markdown đơn giản:

~~~markdown
# ADR-NNN: <Tên quyết định>

- Status: Proposed | Accepted | Rejected | Superseded | Deprecated
- Date: YYYY-MM-DD
- Decision owners: <vai trò/team>
- Review date: <nếu có>

## Context

<Vấn đề nghiệp vụ, bối cảnh hệ thống, ràng buộc và điều gì đang thúc đẩy quyết định.>

## Decision drivers

- <Tiêu chí 1>
- <Tiêu chí 2>
- <Tiêu chí 3>

## Decision

<Lựa chọn cụ thể, phạm vi áp dụng và điều gì nằm ngoài phạm vi.>

## Alternatives considered

### Option A

- Mô tả:
- Ưu điểm:
- Hạn chế:
- Lý do không chọn:

### Option B

- Mô tả:
- Ưu điểm:
- Hạn chế:
- Lý do không chọn:

## Consequences

### Positive
- <Lợi ích>

### Negative / Trade-offs
- <Chi phí, rủi ro hoặc giới hạn đã chấp nhận>

### Operational impact
- <Monitoring, retry, recovery, ownership>

## Validation

- <Test, metric, review hoặc bằng chứng>

## Revisit when

- <Điều kiện cụ thể để mở lại quyết định>

## Related

- <ADR, context map, contract, code, issue>
~~~

Template là khung để hỗ trợ suy nghĩ, không phải biểu mẫu bắt buộc phải điền cho đủ. Nếu một mục không liên quan, có thể ghi “Không áp dụng” hoặc bỏ mục đó theo quy ước của đội.

## 5. Ghi quyết định về Bounded Context

### 5.1. Những câu hỏi cần trả lời

Khi xác định một Bounded Context, ADR nên làm rõ:

- Năng lực nghiệp vụ mà context chịu trách nhiệm.
- Ngôn ngữ và mô hình cốt lõi.
- Những khái niệm context sở hữu.
- Những khái niệm chỉ tham chiếu từ context khác.
- Upstream và downstream.
- Contract trao đổi.
- Quyền sở hữu dữ liệu và cách thay đổi.
- Điều gì nằm ngoài ranh giới.

### 5.2. Ghi ranh giới bằng trách nhiệm, không chỉ bằng tên service

Một service tên `order-service` chưa chắc là một Bounded Context. Một Bounded Context có thể được triển khai trong một module hoặc nhiều service; ngược lại, một service có thể chứa nhiều module hoặc context nếu ranh giới nội bộ được giữ rõ.

ADR cần mô tả trách nhiệm và ngôn ngữ của context. Tên triển khai là chi tiết có thể thay đổi.

### 5.3. Context map là bằng chứng trực quan bổ trợ

Context map có thể thể hiện:

- Ordering là upstream của Inventory đối với OrderSubmitted.
- Inventory công bố StockReserved hoặc StockReservationRejected.
- Billing tiêu thụ sự kiện đã chốt để tạo nghĩa vụ thanh toán.
- ACL chuyển đổi contract của nhà vận chuyển bên ngoài thành mô hình Fulfillment.

ADR nên liên kết tới sơ đồ context map và giải thích vì sao các quan hệ đó được chọn.

~~~mermaid
flowchart LR
    O["Ordering Context"] -->|"OrderSubmitted"| I["Inventory Context"]
    I -->|"StockReserved / Rejected"| O
    O -->|"OrderConfirmed"| B["Billing Context"]
    X["External Carrier"] -->|"Carrier Status"| A["Fulfillment ACL"]
    A --> F["Fulfillment Context"]
~~~

Sơ đồ chỉ minh họa quan hệ trao đổi. Nó không thay thế việc định nghĩa event schema, semantics, retry hoặc ownership.

### 5.4. Ví dụ ADR: tách Ordering và Inventory

~~~markdown
# ADR-014: Ordering và Inventory là hai Bounded Context riêng

- Status: Accepted
- Date: 2026-11-18
- Decision owners: Ordering Team, Inventory Team

## Context

Ordering quản lý ý định mua, giá đã chốt và vòng đời đơn hàng.
Inventory quản lý số lượng vật lý, lượng có thể bán, giữ chỗ và giải phóng
giữ chỗ. Hai nhóm dùng từ "số lượng" nhưng có ý nghĩa khác nhau.

Ordering cần biết sản phẩm có thể được đáp ứng hay không, nhưng không
được tự quyết định số lượng tồn kho. Inventory phải xử lý nhiều nguồn
nhu cầu và các lần giữ chỗ đồng thời.

## Decision drivers

- Mỗi nhóm phải sở hữu invariant và dữ liệu của mình.
- Nhiều đơn có thể tranh chấp cùng một lượng tồn.
- Ordering cần phản hồi rõ khi giữ chỗ thất bại.
- Hai mô hình có thể thay đổi theo nhịp khác nhau.

## Decision

Ordering và Inventory là hai Bounded Context riêng.
Ordering phát OrderSubmitted sau khi đơn đạt điều kiện.
Inventory quyết định giữ chỗ và phát kết quả.
Ordering lưu trạng thái quy trình tương ứng.

## Alternatives considered

1. Một mô hình Order/Stock chung:
   - Ít tích hợp ban đầu.
   - Trộn ý nghĩa available quantity và ordered quantity.
   - Hai nhóm cùng thay đổi một mô hình.
2. Ordering gọi đồng bộ Inventory:
   - Có kết quả ngay trong request.
   - Tăng coupling và phụ thuộc availability của Inventory.
   - Cần xử lý timeout khi không biết giữ chỗ đã thành công chưa.

## Consequences

- Hai context có mô hình và persistence riêng.
- Quy trình submit có thể hoàn tất trước khi giữ chỗ xong.
- Cần trạng thái chờ, timeout, retry và xử lý kết quả thất bại.
- Consumer phải idempotent.

## Validation

- Architecture test cấm import Inventory internal model từ Ordering.
- Contract test cho OrderSubmitted và StockReservationResult.
- Metric theo dõi tuổi yêu cầu giữ chỗ chưa hoàn tất.

## Revisit when

- Quy trình cần xác nhận tồn kho đồng bộ theo yêu cầu nghiệp vụ mới.
- Hai context thực tế có cùng ownership và invariant sau khi domain discovery.
~~~

Ví dụ này cho thấy ADR ghi cả lý do và chi phí của quyết định. Nếu chỉ ghi “tách thành hai service” thì người đọc không biết đâu là lý do nghiệp vụ và đâu là chi tiết triển khai.

## 6. Ghi quyết định về Aggregate boundary và invariant

### 6.1. Invariant phải được viết thành câu có thể kiểm chứng

Một câu như “Order phải hợp lệ” quá mơ hồ. Nên diễn đạt cụ thể:

- Order chỉ được Submit khi có ít nhất một OrderLine.
- Mỗi OrderLine có Quantity lớn hơn 0.
- Sau khi Submit, giá và số lượng của dòng hàng không được thay đổi qua hành vi chỉnh sửa thông thường.
- Order không được chuyển từ Cancelled sang Confirmed.
- Tổng tiền phải dùng cùng currency trong toàn bộ phép cộng.

Một invariant tốt có phạm vi, điều kiện và thời điểm áp dụng rõ ràng.

### 6.2. Ghi ai sở hữu invariant

Ví dụ:

| Invariant | Chủ sở hữu |
|---|---|
| Order phải có dòng hàng trước khi Submit | Ordering / Order Aggregate |
| Số lượng giữ chỗ không vượt khả năng khả dụng | Inventory / Stock Aggregate |
| Payment capture không vượt số tiền được authorize | Payment / Payment Aggregate |
| Invoice tham chiếu đúng nghĩa vụ đã phát sinh | Billing / Invoice Aggregate |

Nếu một invariant cần nhiều aggregate hoặc nhiều context cùng bảo vệ, cần làm rõ nó là invariant cục bộ hay quy trình phối hợp. Đừng mô tả một quy tắc xuyên context như thể một aggregate có thể bảo đảm nó nguyên tử.

### 6.3. Ghi quyết định chọn Aggregate boundary

ADR nên nêu:

- Aggregate Root.
- Entity/Value Object thuộc bên trong.
- ID của aggregate khác được tham chiếu.
- Những hành vi được phép thay đổi trạng thái.
- Invariant cần bảo vệ.
- Transaction boundary dự kiến.
- Cách xử lý concurrency.

Ví dụ, Order sở hữu OrderLine và bảo vệ việc submit. Payment có identity và lifecycle riêng nên là aggregate khác. Order lưu PaymentId hoặc nhận trạng thái thanh toán qua integration result; nó không giữ toàn bộ Payment object để thay đổi trực tiếp.

### 6.4. Ví dụ ADR: Order sở hữu OrderLine, không sở hữu Payment

~~~markdown
# ADR-015: Order và Payment có Aggregate boundary riêng

- Status: Accepted
- Decision owners: Ordering Team, Payment Team

## Context

OrderLine chỉ có ý nghĩa trong đơn hàng và các thay đổi dòng hàng
phải tuân theo trạng thái của Order. Payment có transaction reference,
provider response, retry attempt, authorization và capture lifecycle.

Một Order có thể có nhiều payment attempt. Payment cần được đối soát
độc lập với vòng đời chỉnh sửa Order.

## Decision

Order aggregate sở hữu OrderLine.
Payment là aggregate riêng, tham chiếu OrderId.
Ordering không sửa trạng thái Payment trực tiếp.
Payment công bố kết quả qua integration event/contract.

## Alternatives considered

- Đưa Payment vào Order aggregate: đơn giản khi đọc, nhưng làm Order
  lớn và kéo payment retry/settlement vào transaction của đơn.
- Chỉ lưu PaymentStatus trên Order: dễ hiển thị, nhưng không đủ
  biểu diễn nhiều lần thử và đối soát.

## Consequences

- Có hai repository và lifecycle riêng.
- Cần idempotency cho payment command và event.
- Order có thể hiển thị trạng thái thanh toán qua projection.
- Cần định nghĩa trạng thái khi payment thành công nhưng event đến trễ.

## Validation

- Unit test invariant Order và Payment độc lập.
- Integration test cho payment result handling.
- Architecture test cấm Ordering truy cập Payment internal entity.
~~~

### 6.5. Không ghi Aggregate boundary như một quy tắc bất biến vĩnh viễn

Ranh giới có thể thay đổi khi domain discovery cho thấy invariant khác, khi quy trình mới xuất hiện hoặc khi hệ thống cần thay đổi consistency guarantee.

ADR ghi lại quyết định tại thời điểm đưa ra, không tuyên bố mô hình không bao giờ được thay đổi. Nếu quyết định cũ bị thay thế, giữ lại lịch sử và liên kết ADR mới.

## 7. Ghi quyết định về consistency và transaction

### 7.1. Phân biệt consistency trong aggregate và giữa context

Trong một aggregate, invariant thường cần được bảo vệ ngay khi command hoàn tất. Ví dụ, Order không thể Submit nếu thiếu dòng hàng.

Giữa các Bounded Context, dữ liệu có thể được đồng bộ qua event và cập nhật sau. Ví dụ, Ordering đã submit nhưng Inventory chưa xử lý giữ chỗ.

ADR cần chỉ ra:

- Dữ liệu nào phải nhất quán ngay lập tức?
- Dữ liệu nào có thể nhất quán trễ?
- Người dùng nhìn thấy trạng thái trung gian nào?
- Bao lâu là chậm có thể chấp nhận?
- Khi quá thời hạn, hệ thống xử lý thế nào?

### 7.2. Không dùng “eventual consistency” như một câu trả lời đầy đủ

Nói “hệ thống dùng eventual consistency” chưa giải thích được:

- Sự kiện nào kích hoạt cập nhật?
- Consumer nào sở hữu thay đổi?
- Message có thể bị gửi trùng không?
- Thứ tự event có quan trọng không?
- Khi consumer lỗi thì retry trong bao lâu?
- Người dùng thấy trạng thái Pending hay một trạng thái cũ?
- Khi quy trình không hoàn tất, ai can thiệp?

ADR phải mô tả contract và hành vi vận hành cần thiết.

### 7.3. Ma trận consistency

| Dữ liệu/quy tắc | Consistency cần thiết | Cơ chế gợi ý |
|---|---|---|
| Order status và OrderLine trong cùng Order | Đồng bộ trong aggregate | Một local transaction |
| Stock reservation và available quantity | Đồng bộ trong Inventory | Transaction + concurrency control |
| Ordering nhận kết quả giữ chỗ | Có thể trễ | Integration Event |
| Search index cập nhật theo Order | Có thể trễ | Projection/consumer |
| Báo cáo tổng hợp doanh thu | Có thể trễ theo SLA | Batch/stream projection |
| Ghi Order và ý định phát event | Phải nguyên tử tại service nguồn | Transactional Outbox |

Mức nhất quán nên xuất phát từ hậu quả nghiệp vụ nếu dữ liệu tạm thời chưa đồng bộ. Không nên chọn đồng bộ chỉ vì dễ hiểu hoặc chọn bất đồng bộ chỉ vì muốn giảm coupling.

### 7.4. Ghi rõ transaction boundary

ADR về transaction cần nêu:

- Những thay đổi nào nằm trong cùng local transaction?
- Database/resource nào tham gia?
- Điều gì được commit trước khi gọi hệ thống ngoài?
- Khi một bước thất bại, dữ liệu nào rollback?
- Có cần Outbox hoặc Inbox không?
- Retry có thể tạo duplicate hay không?

Không nên ghi “toàn bộ use case nằm trong transaction” nếu nó thực tế gọi broker hoặc HTTP service mà không tham gia cùng distributed transaction.

### 7.5. Ghi rõ concurrency control

Nếu hai request có thể thay đổi cùng dữ liệu, ADR cần xác định:

- Optimistic locking hay pessimistic locking?
- Unique/exclusion constraint nào bảo vệ invariant?
- Có thể retry khi conflict không?
- Khi conflict, caller nhận lỗi nào?
- Có thứ tự cần bảo đảm theo aggregate không?

Ví dụ, Inventory có thể dùng optimistic version để phát hiện hai lần giữ chỗ đồng thời. Nếu một lần cập nhật thất bại do version conflict, use case tải lại trạng thái và đánh giá lại số lượng khả dụng.

## 8. Ví dụ ADR: chọn Transactional Outbox

~~~markdown
# ADR-016: Dùng Transactional Outbox cho integration event

- Status: Accepted
- Date: 2026-11-18
- Decision owners: Platform Team, Ordering Team

## Context

Khi Order được submit, Ordering cần lưu trạng thái và phát OrderSubmitted.
Nếu commit database thành công nhưng publish thất bại, Inventory không nhận
được yêu cầu giữ chỗ. Nếu publish trước rồi database rollback, Inventory
có thể xử lý một đơn chưa được submit.

## Decision drivers

- Không làm mất ý định phát event sau khi Order commit.
- Không yêu cầu broker tham gia database transaction.
- Có thể retry sau process restart.
- Consumer có thể xử lý duplicate an toàn.

## Decision

Ordering ghi Order và Outbox record trong cùng database transaction.
Relay publish các record đã commit. Consumer dùng eventId làm idempotency key.

## Alternatives considered

1. Publish trực tiếp trong application transaction:
   - Dễ triển khai.
   - Có dual-write failure window.
2. Publish sau commit bằng callback trong memory:
   - Không publish khi transaction rollback.
   - Process có thể dừng sau commit trước khi callback gửi.
3. Distributed transaction:
   - Có thể phối hợp resource nếu hỗ trợ.
   - Tăng coupling và độ phức tạp vận hành.

## Consequences

- Cần relay, retry, monitoring và retention cho Outbox.
- Message có thể được gửi nhiều lần.
- Consumer phải idempotent và ack sau khi local transaction commit.
- Event schema cần versioning.

## Validation

- Test rollback khi Outbox insert thất bại.
- Test relay retry sau broker failure.
- Test consumer nhận cùng eventId nhiều lần.
- Alert theo tuổi của Outbox event chưa publish.

## Revisit when

- Nền tảng hỗ trợ một cơ chế atomic publication khác với chi phí vận hành thấp hơn.
- Throughput hoặc latency khiến polling relay không còn phù hợp và cần CDC.
~~~

Ví dụ này ghi rõ cả guarantee và giới hạn. Outbox bảo đảm thay đổi nghiệp vụ và ý định phát event được lưu cùng transaction; nó không tự bảo đảm exactly-once delivery end-to-end.

## 9. So sánh alternatives một cách có trách nhiệm

### 9.1. Không mô tả phương án không chọn như một phương án tồi

Một ADR hữu ích ghi cả lợi thế của phương án bị loại. Điều đó giúp người đọc hiểu trade-off và nhận ra khi bối cảnh đã thay đổi thì phương án cũ có thể trở nên phù hợp.

Ví dụ, synchronous call giữa hai context có thể phù hợp khi:

- Caller cần câu trả lời ngay để tiếp tục.
- Dependency availability được chấp nhận.
- Timeout và failure semantics được định nghĩa.
- Quy trình cần một quyết định tức thời.

Asynchronous event có thể phù hợp khi:

- Không cần phản hồi ngay.
- Consumer có thể xử lý trễ.
- Cần giảm coupling thời gian chạy.
- Có thể thiết kế trạng thái trung gian và retry.

Không có một lựa chọn đúng cho mọi tình huống.

### 9.2. Ghi tiêu chí trước khi chọn

Các tiêu chí có thể gồm:

- Tính đúng nghiệp vụ.
- Latency.
- Availability.
- Khả năng retry/recovery.
- Độ phức tạp vận hành.
- Khả năng quan sát.
- Chi phí hạ tầng.
- Khả năng thay đổi và migration.
- Mức phụ thuộc giữa team.

Nên xác định tiêu chí quan trọng trước khi đánh giá phương án để tránh chọn theo sở thích công nghệ.

### 9.3. Bảng trade-off

| Tiêu chí | Synchronous API | Asynchronous Event |
|---|---|---|
| Phản hồi ngay | Có thể | Thường không |
| Coupling thời gian chạy | Cao hơn | Thấp hơn |
| Xử lý consumer chậm | Caller có thể chờ/timeout | Consumer xử lý sau |
| Retry | Caller và server cần phối hợp | Broker/consumer có thể retry |
| Duplicate | Có thể do retry request | Có thể do redelivery |
| Trạng thái trung gian | Thường ít hơn | Cần mô hình hóa rõ |
| Quan sát | Request trace | Correlation/event trace và backlog |

ADR nên giải thích tiêu chí nào quan trọng hơn trong bối cảnh cụ thể, không chỉ đưa ra một bảng chung.

## 10. Ghi consequences, rủi ro và giả định

### 10.1. Positive consequences

Ghi những lợi ích thực tế dự kiến:

- Ordering và Inventory có thể thay đổi mô hình độc lập.
- Invariant của từng context có chủ sở hữu rõ.
- Có thể triển khai consumer mới mà không sửa domain model producer.
- Có thể kiểm tra dependency bằng architecture test.

### 10.2. Negative consequences và trade-off

Ghi những chi phí phải chấp nhận:

- Dữ liệu trên màn hình có thể cập nhật trễ.
- Cần xử lý duplicate và event ordering.
- Cần thêm dashboard và alert.
- Khó debug hơn một call đồng bộ đơn giản.
- Phải duy trì event contract và schema compatibility.

Không ghi “không có nhược điểm”. Mọi quyết định kiến trúc đều có phạm vi và chi phí.

### 10.3. Assumptions

Assumption là giả định chưa được chứng minh nhưng ảnh hưởng đến quyết định.

Ví dụ:

- Inventory có thể phản hồi giữ chỗ trong vòng vài giây ở tải thông thường.
- Một Order chỉ cần một kết quả giữ chỗ cuối cùng cho mỗi phiên bản yêu cầu.
- Broker có thể giữ message đủ lâu để phục hồi consumer.
- Các team có khả năng trực vận hành relay và consumer.

Giả định cần có cách kiểm chứng hoặc thời điểm xem xét lại. Nếu giả định sai, quyết định có thể cần thay đổi.

### 10.4. Risks và mitigations

| Rủi ro | Biện pháp |
|---|---|
| Event backlog tăng | Alert theo oldest event age và throughput |
| Consumer nhận duplicate | Inbox/idempotency key |
| Event đến sai thứ tự | Aggregate sequence/partition key |
| Schema không tương thích | Versioning và contract test |
| Context phụ thuộc internal model | Architecture test và public contract |
| Một team không rõ ownership | Ghi owner và escalation path |

ADR không thay thế risk register hoặc runbook, nhưng cần liên kết đến chúng khi rủi ro đáng kể.

## 11. Status và vòng đời của ADR

Một decision record cần cho người đọc biết nó đang ở trạng thái nào.

Các trạng thái phổ biến:

- Proposed: đang được thảo luận, chưa phải quyết định có hiệu lực.
- Accepted: đã được chấp nhận và có thể triển khai.
- Rejected: đã xem xét nhưng không chọn.
- Superseded: đã được một ADR mới thay thế.
- Deprecated: không còn được khuyến nghị, nhưng có thể vẫn tồn tại trong hệ thống.

Tên status có thể khác giữa các tổ chức. Điều quan trọng là định nghĩa rõ semantics và tránh để một đề xuất bị hiểu nhầm là quyết định đã chấp nhận.

### 11.1. Không sửa lịch sử quyết định đã chấp nhận để làm như nó chưa từng tồn tại

Nếu ADR Accepted không còn phù hợp:

1. Tạo ADR mới mô tả bối cảnh và lựa chọn hiện tại.
2. Liên kết ADR mới với ADR cũ.
3. Đánh dấu ADR cũ là Superseded.
4. Ghi migration hoặc transition plan nếu cần.

Giữ lịch sử giúp đội ngũ hiểu hệ thống đã tiến hóa vì sao.

### 11.2. Một ADR có thể được cập nhật trước khi Accepted

Khi còn Proposed, có thể sửa trực tiếp nội dung để phản ánh thảo luận mới. Nên ghi người cập nhật và ngày review theo quy ước của đội.

Sau khi Accepted, thay đổi nội dung quyết định nên được ghi thành ADR mới hoặc amendment có lịch sử rõ.

### 11.3. Review date không phải ngày hết hạn tự động

Một quyết định có thể được review sau sáu tháng để xác minh giả định. Review không có nghĩa tự động hết hiệu lực.

Kết quả review có thể là:

- Giữ nguyên vì bối cảnh vẫn đúng.
- Bổ sung bằng chứng hoặc vận hành.
- Đề xuất ADR mới.
- Đánh dấu Superseded khi đã có quyết định thay thế.

## 12. Quyền sở hữu và cách cộng tác

### 12.1. Ai viết ADR?

Người đề xuất quyết định hoặc nhóm chịu trách nhiệm về phần kiến trúc thường soạn bản nháp. Người viết không nhất thiết là người có quyền phê duyệt cuối cùng.

Với quyết định liên quan nhiều context, cần có đại diện các nhóm sở hữu:

- Domain/business owner.
- Team sở hữu Bounded Context.
- Platform/architecture khi có ảnh hưởng nền tảng.
- Security, compliance hoặc operations khi quyết định tác động tới trách nhiệm của họ.

Không cần mời mọi người vào mọi ADR. Chỉ mời các vai trò chịu ảnh hưởng thực tế.

### 12.2. Chuyên gia nghiệp vụ cần tham gia phần nào?

Chuyên gia nghiệp vụ giúp xác nhận:

- Thuật ngữ và định nghĩa.
- Invariant và ngoại lệ.
- Quy trình khi một bước thất bại.
- Mức trễ dữ liệu có thể chấp nhận.
- Hậu quả của việc từ chối, hủy hoặc bù trừ.
- Các quy tắc pháp lý/hợp đồng liên quan.

Đội kỹ thuật chịu trách nhiệm chuyển các cam kết đó thành mô hình, consistency strategy và cơ chế triển khai.

### 12.3. Tách câu hỏi nghiệp vụ khỏi câu hỏi kỹ thuật

Ví dụ:

| Câu hỏi | Người cần xác nhận |
|---|---|
| Đơn có được xác nhận khi chưa giữ chỗ tồn kho không? | Chuyên gia Ordering/Operations |
| Bao lâu được xem là giữ chỗ bị timeout? | Nghiệp vụ và Operations |
| Dùng Outbox polling hay CDC? | Kiến trúc/Platform |
| Consumer duplicate được xử lý ra sao? | Team sở hữu consumer |
| Khi hết hàng thì hủy hay cho phép backorder? | Chủ sở hữu chính sách bán hàng |

Không nên để lựa chọn công nghệ quyết định ngược lại quy tắc nghiệp vụ.

### 12.4. Quy trình review ngắn và có trọng tâm

Một buổi review ADR có thể theo thứ tự:

1. Người đề xuất trình bày vấn đề và bối cảnh.
2. Chuyên gia nghiệp vụ xác nhận thuật ngữ và invariant.
3. Team nêu các decision drivers.
4. So sánh alternatives và trade-offs.
5. Xác định consequences và rủi ro vận hành.
6. Chọn người quyết định hoặc cơ chế đồng thuận.
7. Ghi status và owner.
8. Liên kết tài liệu và ticket triển khai.

Review không nên biến thành buổi tranh luận về sở thích công nghệ trước khi vấn đề nghiệp vụ được làm rõ.

## 13. Tổ chức thư mục và liên kết tài liệu

### 13.1. Lưu ADR gần code hoặc trong kho tài liệu có version control

Một cấu trúc có thể là:

~~~text
docs/
  architecture/
    decisions/
      README.md
      ADR-001-context-boundaries.md
      ADR-002-order-aggregate.md
      ADR-003-outbox.md
    diagrams/
      context-map.md
      aggregate-model.md
    contracts/
      ordering/
      inventory/
~~~

Nếu tổ chức dùng hệ thống tài liệu tập trung, cần có version history, quyền truy cập và link ổn định. Vị trí lưu trữ không quan trọng bằng việc người làm việc có thể tìm thấy và hiểu trạng thái mới nhất.

### 13.2. Dùng ID ổn định

ID ADR không nên phụ thuộc vào tên file có thể đổi. Một mã như `ADR-016` có thể được tham chiếu từ:

- Pull request.
- Issue.
- Code comment khi thật sự cần.
- Context map.
- Runbook.
- Decision index.

### 13.3. Decision index

Một file index giúp tìm quyết định theo chủ đề:

| ID | Quyết định | Status | Owner |
|---|---|---|---|
| ADR-014 | Ordering và Inventory là hai context | Accepted | Ordering/Inventory |
| ADR-015 | Order và Payment có aggregate riêng | Accepted | Ordering/Payment |
| ADR-016 | Transactional Outbox cho integration event | Accepted | Platform |

Index chỉ là danh mục. Nội dung chính thức vẫn nằm trong từng ADR để tránh một file tổng hợp dài và khó cập nhật.

### 13.4. Liên kết ADR với code và test

Một ADR nên dẫn tới:

- Module/package thực thi quyết định.
- Architecture test bảo vệ ranh giới.
- Contract schema liên quan.
- Dashboard hoặc runbook nếu có ảnh hưởng vận hành.
- Pull request hoặc issue triển khai.

Ngược lại, test có thể ghi tên ADR trong mô tả để người sửa hiểu vì sao rule tồn tại.

Không cần thêm comment ADR vào mọi class. Chỉ liên kết ở nơi quyết định có thể không rõ từ code.

## 14. Từ quyết định đến kiểm chứng

### 14.1. Quyết định cần có bằng chứng

ADR không kết thúc ở câu “đã thống nhất”. Hãy xác định cách kiểm chứng:

- Unit test cho invariant.
- Integration test cho transaction boundary.
- Architecture test cho dependency direction.
- Contract test cho integration event.
- Load test cho throughput/latency.
- Dashboard cho backlog và failure rate.
- Review định kỳ cho assumption.

### 14.2. Ví dụ mapping decision với verification

| Quyết định | Bằng chứng kiểm chứng |
|---|---|
| Domain không phụ thuộc Spring/JPA | ArchUnit rule |
| Order sở hữu OrderLine | Unit test và repository mapping test |
| Payment là aggregate riêng | Dependency test và integration test |
| Ordering không import Inventory internal | Architecture test |
| Outbox ghi cùng Order | Rollback integration test |
| Consumer idempotent | Duplicate delivery test |
| Inventory giữ chỗ không âm | Concurrency test + database constraint |

### 14.3. Metric xác minh trade-off sau triển khai

Nếu quyết định chọn eventual consistency, có thể theo dõi:

- Event publication latency.
- Consumer processing latency.
- Oldest unprocessed event age.
- Retry count.
- Duplicate count.
- Tỷ lệ quy trình chuyển sang trạng thái cần can thiệp.

Nếu SLA thực tế không đáp ứng decision driver, cần xem lại cơ chế hoặc giả định ban đầu.

### 14.4. Ghi kết quả khác với dự kiến

Nếu quyết định đúng về mặt lý thuyết nhưng vận hành cho thấy chi phí quá cao, hãy cập nhật bằng chứng và tạo quyết định mới nếu cần. Không nên giữ ADR như một tài liệu quảng bá lựa chọn đã qua.

## 15. Khi nào cần xem xét lại quyết định?

Một ADR có thể định nghĩa điều kiện mở lại:

- Số lượng giao dịch tăng vượt ngưỡng thiết kế.
- SLA hoặc latency không còn đáp ứng.
- Một Bounded Context nhận thêm trách nhiệm nghiệp vụ mới.
- Invariant thay đổi do chính sách hoặc quy định mới.
- Hai team có ownership thay đổi.
- Một integration contract có quá nhiều consumer khó nâng cấp.
- Chi phí vận hành vượt lợi ích.
- Công nghệ hoặc nền tảng hiện tại không còn được hỗ trợ.

Điều kiện nên có thể quan sát hoặc kiểm chứng. “Khi cần” không đủ rõ để giúp người vận hành biết lúc nào nên review.

## 16. Những sai lầm thường gặp

**Chỉ ghi kết quả, không ghi bối cảnh.** Người đọc không hiểu quyết định giải quyết vấn đề nào. Hãy mô tả tình huống nghiệp vụ và ràng buộc.

**Ghi quyết định nhưng không ghi alternatives.** Không thấy trade-off và lý do loại phương án khác. Ghi ít nhất những lựa chọn thực sự đã cân nhắc.

**Gộp nhiều quyết định độc lập vào một ADR.** Khi một phần thay đổi, toàn bộ tài liệu trở nên mơ hồ. Tách theo quyết định có thể xem xét độc lập.

**Viết ADR như tài liệu quảng bá công nghệ.** ADR phải giải thích vấn đề và hệ quả, không chỉ liệt kê ưu điểm của framework hoặc broker.

**Dùng “eventual consistency” mà không có trạng thái trung gian.** Người dùng và support không biết quy trình đang ở đâu. Định nghĩa Pending, timeout, retry và failure outcome.

**Ghi invariant không có chủ sở hữu.** Khi xảy ra vi phạm, không biết aggregate hoặc context nào chịu trách nhiệm. Gắn từng invariant với owner.

**Nhầm Bounded Context với microservice.** Context là ranh giới mô hình và ngôn ngữ. Cách triển khai có thể thay đổi mà không nhất thiết thay đổi context.

**Sửa ADR Accepted mà không lưu lịch sử.** Người đọc mất khả năng biết hệ thống từng quyết định gì. Tạo ADR mới và đánh dấu tài liệu cũ là Superseded.

**Tài liệu tách rời code.** ADR nói một hướng nhưng code đã thay đổi. Liên kết ADR với test, module và contract; review khi implementation đổi.

**Không có owner hoặc revisit condition.** Quyết định không ai chịu trách nhiệm theo dõi và không có tín hiệu xem xét lại. Ghi owner và điều kiện review.

**Ghi quá nhiều chi tiết implementation.** ADR nhanh lỗi thời khi tên class hoặc thư viện thay đổi. Ghi quyết định ở mức kiến trúc; để chi tiết code ở tài liệu kỹ thuật hoặc code.

## 17. Quy trình ghi một quyết định DDD

1. Xác định vấn đề nghiệp vụ hoặc kiến trúc đang cần giải quyết.
2. Thu thập thuật ngữ, ví dụ và ngoại lệ từ chuyên gia.
3. Xác định Bounded Context, Aggregate, invariant hoặc consistency boundary liên quan.
4. Viết decision drivers và ràng buộc trước khi chọn giải pháp.
5. Liệt kê các alternatives có thể thực hiện.
6. So sánh lợi ích, chi phí, rủi ro và khả năng đảo ngược.
7. Chọn phương án và ghi rõ phạm vi áp dụng.
8. Xác định owner, status và người cần review.
9. Ghi consequences, assumption, validation và revisit conditions.
10. Liên kết ADR với context map, model, contract, code và test.
11. Triển khai theo lát cắt có thể kiểm chứng.
12. Theo dõi bằng chứng sau triển khai và mở lại ADR khi điều kiện thay đổi.

~~~mermaid
flowchart TD
    A["Vấn đề / thay đổi nghiệp vụ"] --> B["Khám phá domain và invariant"]
    B --> C["Xác định ranh giới và decision drivers"]
    C --> D["So sánh alternatives"]
    D --> E["Ghi ADR: decision + rationale + consequences"]
    E --> F{"Được chấp nhận?"}
    F -->|Chưa| G["Bổ sung bằng chứng / thảo luận"]
    G --> D
    F -->|Có| H["Triển khai và liên kết code/test"]
    H --> I["Theo dõi metric và assumption"]
    I --> J{"Bối cảnh còn đúng?"}
    J -->|Có| K["Giữ quyết định"]
    J -->|Không| L["Tạo ADR mới và supersede"]
~~~

## 18. Checklist review ADR

**Bối cảnh**

- Vấn đề nghiệp vụ được mô tả cụ thể chưa?
- Thuật ngữ đã được chuyên gia xác nhận chưa?
- Ràng buộc và giả định có được nêu rõ không?
- Phạm vi và phần không thuộc phạm vi có rõ không?

**Ranh giới và invariant**

- Bounded Context nào sở hữu khái niệm?
- Aggregate Root và invariant nào liên quan?
- Quyền sở hữu dữ liệu có rõ không?
- Quy tắc nào cần transaction cục bộ, quy tắc nào là workflow liên context?

**Consistency**

- Dữ liệu nào phải nhất quán ngay?
- Dữ liệu nào có thể cập nhật trễ?
- Trạng thái trung gian và SLA có rõ không?
- Retry, duplicate, ordering, timeout và compensation đã được xem xét chưa?
- Transaction boundary và resource tham gia có chính xác không?

**Lựa chọn**

- Alternatives thực sự đã được cân nhắc có được ghi không?
- Tiêu chí chọn có gắn với nhu cầu nghiệp vụ không?
- Trade-off và negative consequences có được thừa nhận không?
- Có giải thích vì sao lựa chọn phù hợp trong bối cảnh hiện tại không?

**Quản trị và kiểm chứng**

- Status, date và owner có rõ không?
- Có test, metric hoặc bằng chứng để xác minh không?
- Có điều kiện cụ thể để xem xét lại không?
- ADR liên kết tới context map, contract, code và runbook liên quan chưa?
- ADR cũ có được liên kết khi bị thay thế không?

Ghi quyết định về ranh giới, invariant và consistency giúp đội ngũ duy trì cùng một cách hiểu khi nhiều người cùng phát triển hệ thống. Bounded Context cho biết ai sở hữu mô hình; Aggregate cho biết invariant được bảo vệ ở đâu; consistency decision cho biết các phần phối hợp và cập nhật với nhau như thế nào. Khi bối cảnh, lựa chọn, trade-off và bằng chứng được lưu rõ ràng, quyết định có thể được thực thi, kiểm chứng và thay đổi có trách nhiệm theo sự tiến hóa của nghiệp vụ.
