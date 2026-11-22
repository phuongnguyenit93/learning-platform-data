# Phân quyền sở hữu mô hình và cách tiếp nhận thay đổi xuyên nhóm

Trong một tổ chức phát triển nhiều bounded context, domain model không chỉ là tài sản của một lập trình viên hoặc một repository. Nó là kết quả của sự hiểu biết chung giữa chuyên gia nghiệp vụ, product owner, kiến trúc sư và các nhóm phát triển. Khi nhiều nhóm cùng làm việc trên các phần liên quan của một miền, thay đổi trong một context có thể ảnh hưởng đến thuật ngữ, quy tắc, event hoặc contract mà context khác đang sử dụng.

Nếu không xác định ai chịu trách nhiệm cho mô hình và cách đề xuất thay đổi, những vấn đề thường xuất hiện: cùng một thuật ngữ bị định nghĩa khác nhau, một nhóm tự đổi event làm consumer hỏng, shared kernel trở thành nơi mọi người tùy tiện thêm class, hoặc mọi quyết định đều phải chờ một hội đồng trung tâm. DDD cần sự hợp tác chặt chẽ nhưng cũng cần quyền sở hữu rõ ràng để các nhóm có thể thay đổi độc lập trong ranh giới của mình.

**Model ownership** là việc xác định nhóm và vai trò chịu trách nhiệm duy trì tính đúng đắn, ngôn ngữ, invariant và tiến hóa của một mô hình trong bounded context. **Cross-team change** là thay đổi có ảnh hưởng đến mô hình, contract hoặc quy trình mà nhiều nhóm cùng phụ thuộc. Quy trình tiếp nhận thay đổi cần giúp nhóm hiểu vấn đề, đánh giá tác động, thương lượng phương án, ghi nhận quyết định, triển khai tương thích và theo dõi sau phát hành.

Bài học này trình bày cách phân quyền sở hữu mô hình theo bounded context, vai trò của domain expert và model steward, cách xử lý shared kernel, quy trình đề xuất thay đổi xuyên nhóm, quản lý contract/API/event, ghi quyết định bằng ADR, phối hợp rollout/deprecation, xử lý bất đồng và duy trì tài liệu có ích mà không tạo ra thủ tục nặng nề.

## 1. Vì sao cần phân quyền sở hữu mô hình?

Một bounded context có mô hình và Ubiquitous Language riêng. Nhóm sở hữu context cần chịu trách nhiệm cho các khái niệm, hành vi và dữ liệu trong ranh giới đó. Các nhóm khác có thể tiêu thụ contract hoặc thông tin được công bố, nhưng không nên tự ý thay đổi mô hình nội bộ của owner.

Ví dụ, trong hệ thống thương mại điện tử:

- Sales sở hữu Order, quy tắc xác nhận đơn, giá tại thời điểm đặt và trạng thái thương mại.
- Inventory sở hữu StockItem, Reservation, AvailableQuantity và quy tắc giữ hàng.
- Billing sở hữu PaymentAuthorization, Capture, Refund và trạng thái thanh toán.
- Shipping sở hữu Shipment, DeliveryWindow và quy tắc giao nhận.

Một thay đổi ở Sales như tách trạng thái Order thành nhiều trạng thái fulfillment có thể ảnh hưởng đến Shipping và Billing nếu các context đang tiêu thụ event hoặc query contract. Tuy nhiên, điều đó không có nghĩa Shipping có quyền sửa trực tiếp Order model. Sales vẫn là owner của mô hình Order; các consumer tham gia góp ý về tác động lên contract.

### 1.1. Ownership tạo ra trách nhiệm, không tạo ra độc quyền thông tin

Nhóm owner có trách nhiệm:

- Hiểu và duy trì ngôn ngữ của context.
- Bảo vệ invariant và semantics của mô hình.
- Quyết định thay đổi nội bộ trong phạm vi context.
- Công bố và duy trì contract cho consumer.
- Thông báo thay đổi có ảnh hưởng đến nhóm khác.
- Xử lý lỗi hoặc migration liên quan dữ liệu mà context sở hữu.

Các nhóm consumer vẫn có quyền đặt câu hỏi, phản biện và đề xuất thay đổi. Ownership không có nghĩa owner có thể bỏ qua nhu cầu tích hợp; nó có nghĩa có một nơi chịu trách nhiệm cuối cùng cho tính nhất quán của mô hình.

### 1.2. Không để ownership phụ thuộc vào một cá nhân duy nhất

Nếu chỉ một người hiểu model, người đó trở thành điểm nghẽn và rủi ro nghỉ việc. Ownership nên thuộc về một team hoặc một nhóm vai trò có người dự phòng, tài liệu, quy trình review và khả năng tiếp nhận trách nhiệm khi thành viên thay đổi.

## 2. Phân biệt Bounded Context, team và quyền sở hữu

Bounded Context là ranh giới mô hình nghiệp vụ. Team là đơn vị tổ chức chịu trách nhiệm phát triển và vận hành. Hai ranh giới này nên được liên kết có chủ đích nhưng không nhất thiết trùng nhau.

| Khái niệm | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Bounded Context | Sở hữu ngôn ngữ và model nhất quán | Sales, Billing |
| Owning team | Duy trì model, code, dữ liệu và contract | Sales team |
| Domain expert | Giải thích quy tắc và trường hợp thực tế | Chuyên gia vận hành bán hàng |
| Consumer team | Sử dụng contract và phản hồi nhu cầu | Shipping team |
| Model steward | Hỗ trợ ngôn ngữ, tài liệu và quy trình thay đổi | Người được team chỉ định |
| Architecture/community group | Đưa ra nguyên tắc chung và hỗ trợ giải quyết vấn đề liên context | DDD community |

### 2.1. Một team có thể sở hữu nhiều context

Trong tổ chức nhỏ, một team có thể phụ trách Sales và Pricing. Điều này không có nghĩa hai context phải dùng chung model. Mỗi context vẫn cần ownership, language và contract riêng.

### 2.2. Một context có thể cần nhiều team cộng tác

Nếu một bounded context lớn được nhiều team cùng phát triển, cần chia ownership theo capability hoặc subdomain bên trong context và xác định ai chịu trách nhiệm cho phần model chung. Nếu nhiều team cùng sửa một aggregate hoặc cùng quyết định một invariant, cần có cơ chế phối hợp rõ hơn.

### 2.3. Tránh chia ownership theo file hoặc layer

Một team sở hữu controller, team khác sở hữu entity và team thứ ba sở hữu repository thường làm trách nhiệm nghiệp vụ bị chia cắt. Khi một quy tắc thay đổi, không có team nào chịu trách nhiệm trọn vẹn. Ưu tiên ownership theo capability/bounded context thay vì chia theo loại class kỹ thuật.

## 3. Xác định phạm vi model ownership

Ownership cần cụ thể để mọi người biết nhóm nào có quyền quyết định và nhóm nào cần được tham vấn.

Một context ownership map có thể ghi:

| Thành phần | Owner | Consumer/Stakeholder | Cách thay đổi |
| --- | --- | --- | --- |
| Domain terms | Owning team + domain expert | Các nhóm tích hợp | Thảo luận và cập nhật glossary |
| Aggregate và invariant | Owning team | Application/consumer teams | Review domain behavior và test |
| Domain events | Owning team | Event consumers | Contract review và versioning |
| Public API/query contract | Owning team | API consumers | Compatibility review |
| Database schema/data | Owning team | Data/reporting consumers | Migration và quyền truy cập |
| Shared Kernel | Các team đồng sở hữu | Các team tham gia | Thỏa thuận thay đổi chung |

### 3.1. Owner của model và owner của integration contract

Thông thường, team sở hữu bounded context cũng sở hữu contract mà context công bố. Tuy nhiên, một contract liên tổ chức hoặc schema được nhiều producer/consumer cùng quản trị có thể cần một nhóm stewardship riêng. Dù chọn cách nào, phải chỉ rõ ai quyết định semantics, ai duy trì implementation và ai thông báo consumer.

### 3.2. Quyền quyết định phải đi kèm trách nhiệm vận hành

Nếu một team quyết định đổi event schema nhưng không chịu trách nhiệm theo dõi consumer bị lỗi, quyền quyết định đó chưa đầy đủ. Owner cần theo dõi adoption, compatibility, deprecation và sự cố sau phát hành.

## 4. Vai trò của Domain Expert, Developer và Model Steward

Mô hình tốt cần sự hợp tác của nhiều vai trò:

| Vai trò | Đóng góp chính | Không nên bị giao phó |
| --- | --- | --- |
| Domain expert | Giải thích nghiệp vụ, ngoại lệ, ưu tiên và thuật ngữ | Tự quyết định cấu trúc code hoặc database |
| Product owner/business owner | Mục tiêu, giá trị, phạm vi và thứ tự ưu tiên | Thay thế việc xác nhận semantics chi tiết |
| Developer/domain modeler | Chuyển hiểu biết thành model, hành vi và test | Tự suy đoán quy tắc khi thiếu bằng chứng |
| Owning team lead | Điều phối quyết định và chất lượng trong context | Phê duyệt mọi thay đổi nhỏ không cần thiết |
| Model steward | Duy trì glossary, decision log và consistency | Trở thành người duy nhất được phép hiểu model |
| Consumer team | Mô tả tác động tích hợp và nhu cầu sử dụng | Áp đặt implementation nội bộ cho producer |

### 4.1. Domain expert cần tham gia vào quyết định có semantics

Một thay đổi như đổi tên class nội bộ có thể do developer quyết định. Nhưng thay đổi ý nghĩa trạng thái “đã thanh toán”, điều kiện hủy đơn hoặc thời điểm ghi nhận doanh thu cần được domain expert xác nhận.

### 4.2. Model steward hỗ trợ chứ không thay owner

Model steward có thể tổ chức glossary, ghi nhận thuật ngữ mới, điều phối workshop và nhắc nhóm cập nhật tài liệu. Quyền quyết định vẫn thuộc owner và những vai trò được tổ chức ủy quyền.

### 4.3. Có người thay thế và kênh liên hệ rõ

Mỗi context nên có primary owner và backup contact. Tài liệu cần chỉ ra team/channel hoặc hệ thống quản lý công việc đang được sử dụng. Không nên phụ thuộc vào một cuộc trò chuyện riêng mà người mới không thể tìm lại.

## 5. Ubiquitous Language là tài sản được quản trị trong context

Ubiquitous Language là ngôn ngữ chung giữa chuyên gia và đội phát triển trong một bounded context. Nó cần được duy trì khi nghiệp vụ thay đổi.

Một glossary hữu ích có thể ghi:

| Thuật ngữ | Định nghĩa trong context | Ví dụ | Thuật ngữ dễ nhầm |
| --- | --- | --- | --- |
| Order | Cam kết mua bán đã được ghi nhận trong Sales | Đơn ORD-501 | Shipment |
| Confirmed Order | Đơn đã vượt qua điều kiện xác nhận của Sales | Đơn được xác nhận | Payment Authorized |
| Reservation | Lượng hàng được Inventory giữ cho một yêu cầu | RES-81 | Available Stock |
| Payment Authorized | Giao dịch được đơn vị thanh toán chấp thuận ủy quyền | PAY-91 | Payment Captured |
| Shipment | Đơn vị vận chuyển do Shipping quản lý | SHP-31 | Order |

### 5.1. Một từ có thể có nghĩa khác trong context khác

“Customer” trong Sales có thể là người mua; trong Billing có thể là bên chịu trách nhiệm thanh toán; trong Identity có thể là tài khoản người dùng. Không nên ép các context dùng một định nghĩa chung nếu semantics khác nhau.

### 5.2. Ghi cả từ không nên dùng

Glossary có thể ghi các cặp dễ nhầm như Order/Shipment, Authorized/Captured, Available/Reserved. Điều này giúp người viết API và event tránh dùng một từ chung chung gây hiểu nhầm.

### 5.3. Glossary cần được cập nhật cùng code và contract

Khi một thuật ngữ thay đổi ý nghĩa, cần xem xét domain model, test, API/event schema, dashboard và tài liệu vận hành. Chỉ sửa glossary mà không cập nhật contract hoặc code sẽ tạo ra hai nguồn thông tin mâu thuẫn.

## 6. Phân loại thay đổi trước khi yêu cầu phối hợp

Không phải mọi thay đổi đều cần quy trình liên nhóm. Phân loại đúng giúp tránh tạo thủ tục cho thay đổi nội bộ và tránh bỏ sót thay đổi có tác động rộng.

| Loại thay đổi | Ví dụ | Ai cần tham gia |
| --- | --- | --- |
| Internal implementation | Đổi class, package hoặc query plan không đổi semantics | Owning team |
| Local domain behavior | Thêm invariant nội bộ không ảnh hưởng contract | Owning team + domain expert |
| Published contract additive | Thêm field optional hoặc event mới | Owner + consumer bị ảnh hưởng |
| Contract breaking | Xóa field, đổi kiểu hoặc semantics | Owner + tất cả consumer liên quan |
| Shared Kernel | Đổi value object hoặc policy dùng chung | Các team đồng sở hữu |
| Cross-context workflow | Đổi thứ tự giữ hàng, thanh toán và giao hàng | Các owner tham gia + domain experts |
| Data ownership/schema | Chuyển bảng hoặc quyền ghi | Owner, consumer, data/operations |

### 6.1. Thay đổi nội bộ có thể không cần RFC

Nếu thay đổi không ảnh hưởng hành vi công khai, contract, dữ liệu lịch sử hoặc consumer, owning team có thể tự quyết định theo quy trình code review thông thường. Không nên yêu cầu họp liên nhóm cho một refactor nội bộ.

### 6.2. Thay đổi semantics cần được coi trọng dù schema không đổi

Nếu event OrderConfirmed vẫn có cùng tên và field nhưng đổi nghĩa từ “Sales xác nhận đơn” sang “đơn đã sẵn sàng giao”, đó là thay đổi contract. Consumer có thể hành động sai dù JSON không thay đổi.

## 7. Quy trình tiếp nhận thay đổi xuyên nhóm

Một quy trình thực tế có thể gồm các bước:

~~~mermaid
flowchart TD
    A[Đề xuất thay đổi] --> B[Owning team phân loại phạm vi]
    B --> C{Có ảnh hưởng contract/context khác?}
    C -->|Không| D[Owner xử lý nội bộ]
    C -->|Có| E[Impact assessment]
    E --> F[Trao đổi với domain experts và consumer owners]
    F --> G[Đề xuất phương án và trade-off]
    G --> H[Review và quyết định]
    H --> I[Decision record + migration plan]
    I --> J[Implement + contract tests]
    J --> K[Rollout và theo dõi]
    K --> L[Deprecate phần cũ nếu cần]
~~~

### 7.1. Bước 1: Ghi rõ vấn đề nghiệp vụ

Đề xuất nên mô tả:

- Tình huống hiện tại và điều gì đang gây khó khăn.
- Ai bị ảnh hưởng và ảnh hưởng như thế nào.
- Ví dụ cụ thể hoặc dữ liệu minh chứng.
- Kết quả nghiệp vụ mong muốn.
- Deadline hoặc lý do cần thay đổi.

Tránh mở đầu bằng “cần đổi field X” nếu chưa giải thích vì sao. Giải pháp kỹ thuật có thể chưa phải cách tốt nhất để giải quyết vấn đề.

### 7.2. Bước 2: Xác định owner và consumer

Owning team xác nhận context nào sở hữu khái niệm. Liệt kê các consumer của API/event/schema và những quy trình bị ảnh hưởng. Nếu chưa biết consumer, dùng contract registry, telemetry, repository search và hỏi các nhóm liên quan.

### 7.3. Bước 3: Phân tích tác động

Đánh giá tác động đến:

- Ubiquitous Language và định nghĩa khái niệm.
- Aggregate, invariant, policy và domain event.
- API/query/event contract.
- Database schema và dữ liệu lịch sử.
- Workflow/process manager và compensation.
- Consumer code, dashboard, báo cáo và job.
- Security, audit, observability và vận hành.

### 7.4. Bước 4: Đề xuất phương án

Nên nêu ít nhất phương án ưu tiên và lý do. Với thay đổi lớn, có thể so sánh một số lựa chọn theo compatibility, chi phí, rủi ro, độ phức tạp và thời gian. Không cần tạo nhiều phương án giả tạo cho thay đổi đơn giản.

### 7.5. Bước 5: Tham vấn đúng người

Mời domain expert xác nhận semantics, consumer owner đánh giá ảnh hưởng và owning team quyết định cách triển khai. Không cần mời toàn bộ tổ chức vào mọi thay đổi.

### 7.6. Bước 6: Ghi quyết định và kế hoạch

Ghi lại quyết định, lý do, phạm vi, contract mới, migration, người chịu trách nhiệm và điều kiện hoàn tất. Nếu thay đổi lớn, dùng Architecture Decision Record (ADR) hoặc RFC theo quy ước nhóm.

### 7.7. Bước 7: Triển khai, kiểm thử và theo dõi

Thực hiện theo lộ trình tương thích. Kiểm tra provider/consumer contract, integration test, metrics và adoption. Chỉ loại bỏ contract cũ khi các điều kiện deprecation đã đạt.

## 8. Mẫu đề xuất thay đổi xuyên nhóm

Một đề xuất ngắn nhưng đủ thông tin có thể theo cấu trúc:

~~~markdown
# Change proposal: [Tên thay đổi]

## Problem
Mô tả vấn đề nghiệp vụ và tình huống hiện tại.

## Desired outcome
Kết quả cần đạt và cách nhận biết thành công.

## Owning context
Context và team chịu trách nhiệm cho model/contract.

## Affected contexts and consumers
Các nhóm, API, event, schema và workflow bị ảnh hưởng.

## Domain meaning
Thuật ngữ, invariant, policy hoặc state transition thay đổi.

## Options
Các phương án và trade-off chính.

## Proposed approach
Phương án đề xuất và lý do.

## Compatibility and migration
Version, rollout, deprecation, backfill hoặc data migration.

## Tests and observability
Contract test, integration test, metrics và cảnh báo.

## Owners and timeline
Người chịu trách nhiệm, mốc phối hợp và điều kiện hoàn tất.
~~~

Không cần điền mọi mục với độ dài như nhau. Nếu thay đổi chỉ thêm một event mới, phần migration có thể ngắn. Nếu thay đổi semantics của trạng thái thanh toán, phần impact và compatibility cần chi tiết hơn.

## 9. Đánh giá tác động xuyên context

Một thay đổi có thể lan truyền qua nhiều tầng. Ví dụ, Sales muốn thay event OrderConfirmed bằng OrderReadyForFulfillment.

Nhóm cần hỏi:

1. Event cũ đang diễn đạt fact gì?
2. Fact mới có thực sự khác về semantics hay chỉ đổi tên?
3. Billing đang dùng event để bắt đầu thu tiền hay chỉ ghi nhận đơn?
4. Shipping đang dùng event để tạo shipment hay chờ reservation?
5. Reporting có tính doanh thu theo event này không?
6. Consumer nào đang chạy phiên bản cũ?
7. Có dữ liệu lịch sử hoặc replay cần giữ event cũ không?
8. Có cần một event mới song song trong giai đoạn chuyển tiếp?

### 9.1. Impact map

Có thể ghi dependency như sau:

| Thành phần | Tác động | Owner cần xác nhận |
| --- | --- | --- |
| Sales Order aggregate | Thay đổi thời điểm phát fact | Sales |
| Sales integration event | Thêm/đổi contract | Sales |
| Billing consumer | Có thể thu tiền sớm/muộn | Billing |
| Shipping consumer | Có thể tạo shipment theo điều kiện mới | Shipping |
| Reporting projection | Thay đổi mốc tính chỉ số | Data/Reporting |
| Customer notification | Thay đổi nội dung thông báo | Customer Experience |

### 9.2. Phân biệt dependency trực tiếp và dependency ngữ nghĩa

Consumer có thể không import class của producer nhưng vẫn phụ thuộc ý nghĩa event. Tìm dependency bằng code search là chưa đủ; cần hỏi consumer owner cách họ diễn giải event và quyết định nghiệp vụ.

## 10. Quyền quyết định và ma trận trách nhiệm

Không phải mọi bên tham gia đều có quyền phê duyệt mọi nội dung. Có thể dùng ma trận trách nhiệm để tránh cả hai thái cực: owner tự ý thay đổi contract và mọi nhóm đều có quyền phủ quyết mọi việc.

| Quyết định | Accountable | Consulted | Informed |
| --- | --- | --- | --- |
| Thay đổi implementation nội bộ | Owning team | Thành viên liên quan | Không cần thông báo rộng |
| Thay đổi invariant/semantics nội bộ | Owning team + business owner theo chính sách tổ chức | Domain expert | Consumer nếu có ảnh hưởng |
| Thay đổi public contract | Contract owner | Consumer owners, domain expert | Các nhóm liên quan |
| Thay đổi Shared Kernel | Nhóm đồng sở hữu theo thỏa thuận | Các consumer | Các nhóm sử dụng |
| Thay đổi workflow liên context | Owner của process/workflow được chỉ định | Các participant owners | Stakeholders |
| Thay đổi dữ liệu hoặc cutover | Data owner/technical owner | Consumer, operations, security | Các bên bị ảnh hưởng |

### 10.1. Một người chịu trách nhiệm quyết định cuối cùng

Với mỗi thay đổi, cần biết ai là người có trách nhiệm đưa ra quyết định cuối cùng trong phạm vi được giao. Có thể là owning team lead, product/domain owner hoặc contract owner. Nếu không có người chịu trách nhiệm, thảo luận dễ kéo dài mà không đi đến kết luận.

### 10.2. Consumer có quyền nêu rủi ro, không sở hữu model của producer

Consumer có thể nói contract mới làm họ không thể triển khai trong thời hạn hiện tại, hoặc semantics mới phá quy trình của họ. Producer cần xem xét và có thể điều chỉnh rollout. Nhưng consumer không nên yêu cầu producer dùng entity hoặc cấu trúc database nội bộ cụ thể.

## 11. Thay đổi API và Event Contract

Contract công khai là điểm phối hợp quan trọng giữa các nhóm. Mỗi contract cần owner, consumer list, versioning policy, compatibility rule và cách deprecate.

### 11.1. Thay đổi thường tương thích

Một số thay đổi có thể tương thích nếu consumer và tooling hỗ trợ:

- Thêm endpoint mới.
- Thêm response field optional mà consumer bỏ qua unknown field.
- Thêm event mới mà không thay đổi event cũ.
- Thêm metadata không bắt buộc.
- Tăng khả năng quan sát mà không đổi semantics.

Không nên mặc định mọi field mới đều an toàn. Consumer có thể dùng schema strict hoặc generated code từ chối field chưa biết.

### 11.2. Thay đổi thường phá vỡ

- Xóa hoặc đổi tên field đang được dùng.
- Đổi kiểu, đơn vị hoặc format.
- Thêm request field bắt buộc.
- Đổi ý nghĩa event hoặc status.
- Thay thứ tự/semantics của workflow.
- Thay đổi error code hoặc validation theo cách client không xử lý được.
- Xóa endpoint hoặc ngừng publish event.

### 11.3. Semantics là một phần của contract

Một event OrderPaid có thể có nghĩa tiền đã được capture, hoặc chỉ được authorization. Hai trạng thái này khác nhau về nghiệp vụ. Nếu producer đổi cách dùng event mà schema không đổi, consumer có thể thực hiện hành động sai.

### 11.4. Contract test và consumer-driven contract

Provider contract test xác nhận implementation đáp ứng schema/contract công bố. Consumer-driven contract test ghi lại những tương tác mà consumer thực sự cần. Cả hai giúp phát hiện breaking change trước khi phát hành.

Contract test không thay thế thảo luận nghiệp vụ. Nó xác nhận hình dạng và tương tác; domain expert vẫn cần xác nhận ý nghĩa.

## 12. Deprecation và migration cho consumer

Khi cần loại bỏ contract cũ, cần một giai đoạn chuyển tiếp:

1. Công bố contract mới và lý do thay đổi.
2. Thêm contract mới song song nếu cần.
3. Cung cấp mapping và ví dụ migration.
4. Thông báo consumer owner và mốc deprecation.
5. Theo dõi traffic/version của từng consumer.
6. Hỗ trợ consumer chuyển đổi và chạy contract test.
7. Xác nhận không còn consumer hợp lệ trên contract cũ.
8. Ngừng contract cũ và dọn code sau thời hạn đã công bố.

### 12.1. Deprecation phải có thời hạn và người chịu trách nhiệm

Một thông báo “deprecated” không có thời hạn hoặc owner sẽ dễ bị bỏ quên. Cần ghi ngày dự kiến sunset, điều kiện gia hạn, consumer chưa chuyển và người quyết định đóng.

### 12.2. Consumer không phản hồi không có nghĩa là không sử dụng

Một job cuối tháng hoặc đối tác bên ngoài có thể không xuất hiện trong traffic hằng ngày. Trước khi xóa contract, kiểm tra đủ chu kỳ nghiệp vụ và danh sách tích hợp.

### 12.3. Không ép consumer nâng cấp đồng loạt nếu không cần

Giữ hai version trong một khoảng thời gian thường giúp các nhóm release độc lập. Nhưng duy trì quá nhiều version cũng có chi phí. Thời hạn hỗ trợ cần cân bằng giữa autonomy của consumer và khả năng vận hành của producer.

## 13. Shared Kernel cần quy tắc đồng sở hữu riêng

Shared Kernel là phần model được nhiều bounded context cùng thống nhất chia sẻ. Nó có thể chứa value object hoặc contract thật sự có cùng semantics. Vì có nhiều owner, thay đổi Shared Kernel cần quy trình rõ hơn một thư viện tiện ích thông thường.

### 13.1. Chỉ chia sẻ khi semantics thực sự giống nhau

Hai context có thể cùng dùng Money nếu định nghĩa currency, precision và phép toán giống nhau. Nhưng hai context cùng có class Customer không có nghĩa họ cần chia sẻ Customer model.

### 13.2. Xác định ai được đề xuất và ai quyết định

Các team tham gia cần thống nhất:

- Phạm vi Shared Kernel.
- Owner/steward và nhóm đồng sở hữu.
- Quy tắc review.
- Versioning và compatibility.
- Release cadence.
- Cách xử lý khi các context có nhu cầu khác nhau.

### 13.3. Giữ Shared Kernel nhỏ

Nếu Shared Kernel liên tục nhận thêm model chỉ vì “nhiều nơi dùng”, nó có thể trở thành coupling point. Khi semantics bắt đầu khác nhau, tách model và mapping thường là lựa chọn lành mạnh hơn.

## 14. Architecture Decision Record và Decision Log

Một quyết định xuyên nhóm cần lưu lý do để người đến sau hiểu tại sao nhóm chọn phương án đó.

**Architecture Decision Record (ADR)** thường ghi:

- Bối cảnh và vấn đề.
- Quyết định đã chọn.
- Các phương án đã cân nhắc.
- Lý do và trade-off.
- Hệ quả tích cực/tiêu cực.
- Trạng thái quyết định.
- Người chịu trách nhiệm và ngày quyết định.

Ví dụ cấu trúc:

~~~markdown
# ADR-024: Sales công bố OrderPlaced cho Inventory

## Status
Accepted

## Context
Inventory cần biết đơn đã được ghi nhận để bắt đầu quy trình giữ hàng.

## Decision
Sales công bố integration event OrderPlaced sau khi transaction đơn hàng commit.
Inventory tiêu thụ event và tự tạo reservation qua mô hình của mình.

## Alternatives
- Inventory truy vấn trực tiếp bảng orders.
- Sales gọi đồng bộ Inventory trong transaction đặt hàng.

## Consequences
- Hai context không còn chia sẻ quyền ghi.
- Inventory xử lý bất đồng bộ và cần idempotency.
- Quy trình cần theo dõi event lag và reservation rejection.
~~~

### 14.1. ADR ghi quyết định, không phải biên bản mọi cuộc họp

Không cần ghi lại từng câu nói. Hãy giữ bối cảnh, lý do, quyết định và hệ quả đủ để người đọc hiểu lựa chọn. Link đến proposal, issue hoặc contract nếu cần thêm chi tiết.

### 14.2. Quyết định có thể được thay thế

Khi điều kiện thay đổi, ADR cũ không nên bị xóa hoặc viết lại như thể quyết định chưa từng tồn tại. Tạo ADR mới tham chiếu quyết định trước và đánh dấu superseded/replaced.

### 14.3. Ghi cả quyết định không thay đổi

Đôi khi nhóm đánh giá và quyết định giữ contract hiện tại. Ghi lý do có thể giúp tránh việc cùng một đề xuất được thảo luận lại mà không có dữ kiện mới.

## 15. RFC, ADR, glossary và contract documentation khác nhau

Các loại tài liệu phục vụ mục đích khác nhau:

| Tài liệu | Mục đích | Thời điểm |
| --- | --- | --- |
| Change proposal/RFC | Mời đánh giá một vấn đề và phương án | Trước quyết định |
| ADR | Ghi quyết định và trade-off | Sau khi quyết định |
| Ubiquitous Language glossary | Định nghĩa thuật ngữ trong context | Duy trì liên tục |
| API/event contract | Mô tả tương tác công khai | Cùng code và release |
| Runbook/migration guide | Hướng dẫn vận hành/chuyển đổi | Trước rollout |
| Decision log | Tra cứu các quyết định theo thời gian | Liên tục |

Không nên dùng một tài liệu dài để thay thế tất cả. Mỗi tài liệu cần có owner, nơi lưu và liên kết đến các nguồn liên quan.

## 16. Tổ chức workshop và trao đổi xuyên nhóm

Khi thay đổi liên quan nhiều context, workshop ngắn có thể giúp các bên thống nhất semantics và luồng nghiệp vụ trước khi tranh luận implementation.

Một buổi làm việc có thể:

1. Nêu tình huống và mục tiêu nghiệp vụ.
2. Xác định context owner và participant.
3. Làm rõ thuật ngữ và fact/event.
4. Vẽ luồng hiện tại và luồng mong muốn.
5. Xác định invariant và điểm chịu trách nhiệm.
6. Ghi các câu hỏi chưa được xác nhận.
7. So sánh phương án và trade-off.
8. Chốt owner, quyết định tiếp theo và thời hạn.

### 16.1. Dùng event storming khi cần hiểu luồng

Event storming hữu ích khi thay đổi ảnh hưởng chuỗi event, command, policy và actor. Nó giúp phát hiện bước nào thuộc context nào và nơi nào cần Process Manager. Kết quả workshop cần được chuyển thành contract, decision record và test; không để sticky note trở thành tài liệu duy nhất.

### 16.2. Chuẩn bị ví dụ thay vì chỉ dùng thuật ngữ trừu tượng

Một cuộc trao đổi về “trạng thái đơn” dễ kéo dài vì mỗi nhóm hiểu khác nhau. Dùng ví dụ cụ thể như “đã authorization nhưng chưa capture” hoặc “đã giữ hàng nhưng chưa tạo shipment” giúp lộ ra khác biệt semantics.

### 16.3. Ghi nhận câu hỏi chưa có câu trả lời

Không nên ép nhóm đưa ra quyết định khi thiếu dữ liệu. Ghi câu hỏi, người cần xác minh và thời hạn. Một quyết định tạm thời có thể được dùng nếu rủi ro và điều kiện xem xét lại đã rõ.

## 17. Xử lý bất đồng giữa các nhóm

Bất đồng thường xuất phát từ:

- Mỗi context tối ưu cho mục tiêu khác nhau.
- Một từ có nghĩa khác trong các mô hình.
- Consumer muốn dữ liệu mới ngay trong khi producer chỉ có thể công bố bất đồng bộ.
- Thay đổi làm tăng chi phí vận hành của một nhóm.
- Không rõ ai chịu trách nhiệm cho một quy trình xuyên context.
- Các bên dựa trên giả định hoặc dữ liệu khác nhau.

Một cách giải quyết có hệ thống:

1. Tách vấn đề nghiệp vụ khỏi giải pháp kỹ thuật đang đề xuất.
2. Thống nhất định nghĩa thuật ngữ và ví dụ.
3. Làm rõ invariant và trách nhiệm owner.
4. Đưa ra các lựa chọn cùng trade-off.
5. Đánh giá theo mục tiêu người dùng, rủi ro và chi phí toàn hệ thống.
6. Chỉ định người có quyền quyết định trong phạm vi đã thống nhất.
7. Ghi quyết định và điều kiện xem xét lại.

### 17.1. Không dùng shared model để né bất đồng

Nếu Sales và Billing bất đồng về nghĩa của Customer, tạo một Customer class chung không giải quyết được vấn đề. Nó chỉ giấu hai semantics khác nhau trong cùng cấu trúc. Hãy giữ model riêng và xác định contract cần trao đổi.

### 17.2. Escalation khi không thể thống nhất

Nếu bất đồng ảnh hưởng đến nhiều context hoặc rủi ro tổ chức, có thể chuyển đến domain owner, product leadership hoặc architecture group. Escalation cần mang theo vấn đề, các phương án, trade-off và tác động, không chỉ yêu cầu “hãy quyết định giúp”.

### 17.3. Có thể dùng quyết định tạm thời

Khi cần tiến độ, nhóm có thể chọn một phương án reversible, ghi rõ thời hạn và điều kiện xem xét lại. Không nên biến quyết định tạm thời thành chuẩn vĩnh viễn chỉ vì chưa ai quay lại tài liệu.

## 18. Phối hợp triển khai thay đổi

Sau khi quyết định, cần chuyển nó thành kế hoạch có thể thực hiện:

- Work item theo từng owning team.
- Thứ tự deploy và dependency.
- Contract test hoặc test fixture dùng chung.
- Feature flag hoặc compatibility window nếu cần.
- Data migration/backfill nếu semantics hoặc schema thay đổi.
- Dashboard/alert để theo dõi.
- Người trực xử lý khi rollout gặp lỗi.
- Điều kiện hoàn tất và deprecation.

### 18.1. Producer và consumer có thể triển khai theo thứ tự

Với thay đổi additive, thường triển khai producer hỗ trợ contract mới trước, sau đó consumer bắt đầu sử dụng. Với breaking change, có thể cần thêm field/endpoint mới song song, chuyển consumer, rồi mới loại bỏ phần cũ.

### 18.2. Kiểm tra tương thích trong CI

Provider contract test xác nhận producer vẫn đáp ứng contract. Consumer-driven contract test xác nhận producer không phá những nhu cầu consumer đã đăng ký. Schema compatibility check có thể được tự động hóa trong pipeline.

### 18.3. Không phụ thuộc vào thông báo miệng

Một cuộc họp hoặc tin nhắn có thể thông báo thay đổi, nhưng contract và migration plan cần nằm ở nơi có thể tra cứu. Người vắng mặt hoặc team mới cần có khả năng tìm lại.

## 19. Quản lý tài liệu như một phần của model lifecycle

Tài liệu hữu ích cần được cập nhật khi model thay đổi, nhưng không nên tạo ra nhiều bản sao không đồng bộ.

Có thể xác định nguồn chuẩn:

- Glossary là nơi định nghĩa thuật ngữ.
- Code và domain tests là nơi thực thi hành vi/invariant.
- OpenAPI hoặc schema registry là nơi công bố contract máy đọc được.
- ADR là nơi ghi quyết định và trade-off.
- Runbook là nơi hướng dẫn vận hành.
- Context map là nơi mô tả quan hệ giữa bounded context.

### 19.1. Mỗi tài liệu có owner và thời điểm review

Tài liệu cần biết ai chịu trách nhiệm và khi nào cần xem lại. Với contract, có thể review khi schema thay đổi hoặc consumer mới đăng ký. Với glossary, review khi thuật ngữ thay đổi hoặc phát hiện nghĩa không thống nhất.

### 19.2. Tránh tài liệu chỉ mô tả implementation hiện tại

Tài liệu nên giải thích semantics và quyết định, không chỉ liệt kê class. Nếu code đổi tên class nhưng nghiệp vụ không đổi, glossary không cần thay. Nếu event semantics thay đổi dù class không đổi, contract documentation phải được cập nhật.

### 19.3. Liên kết thay vì sao chép

Một ADR có thể liên kết đến OpenAPI schema và glossary. Không nên copy nguyên nội dung schema vào nhiều wiki khác nhau rồi phải cập nhật thủ công.

## 20. Chỉ số để đánh giá collaboration và model ownership

Không nên đo chất lượng collaboration bằng số cuộc họp hoặc số trang tài liệu. Có thể theo dõi những dấu hiệu gắn với kết quả:

- Số cross-context breaking changes được phát hiện trước release.
- Thời gian từ đề xuất đến quyết định đối với thay đổi có phạm vi rõ.
- Số consumer bị ảnh hưởng nhưng không được thông báo.
- Số incident do hiểu sai event/status semantics.
- Tỷ lệ contract có owner và consumer list.
- Tỷ lệ migration/deprecation hoàn thành đúng kế hoạch.
- Thời gian onboarding để một developer hiểu model của context.
- Số dependency chéo ngoài contract được phát hiện trong CI.

Các metrics cần được dùng để cải thiện quy trình, không để tạo áp lực khiến nhóm tránh báo cáo vấn đề hoặc giảm số lượng đề xuất.

## 21. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Không chỉ định model owner | Không ai chịu trách nhiệm cho semantics và contract | Gắn owner với từng bounded context |
| Một cá nhân giữ toàn bộ kiến thức | Bottleneck và rủi ro bus factor | Ownership theo team, có steward và backup |
| Team được chia theo layer nhưng model theo context | Trách nhiệm nghiệp vụ bị phân tán | Tổ chức ownership theo capability/context |
| Owner tự đổi contract mà không tìm consumer | Consumer hỏng sau release | Impact assessment và thông báo consumer |
| Mọi thay đổi đều cần hội đồng phê duyệt | Chậm và tạo bottleneck | Phân loại local, additive và breaking change |
| Consumer quyết định implementation nội bộ producer | Phá quyền sở hữu model | Trao đổi qua contract và semantics |
| Dùng shared model để thống nhất mọi thuật ngữ | Các semantics khác nhau bị trộn | Giữ model riêng và mapping qua ACL |
| Shared Kernel không có đồng sở hữu rõ | Một team thay đổi làm team khác bất ngờ | Quy định steward, review và versioning |
| Chỉ ghi biên bản họp | Không lưu quyết định và lý do | Dùng proposal, ADR, glossary và contract |
| ADR bị xem là tài liệu hình thức | Không ai cập nhật hoặc tra cứu | Ghi ngắn, tập trung bối cảnh, quyết định và hệ quả |
| Không ghi quyết định tạm thời | Giải pháp tạm trở thành mặc định | Ghi expiry và điều kiện review |
| Deprecate nhưng không đo usage | Xóa contract khi consumer vẫn dùng | Theo dõi traffic và kiểm tra chu kỳ định kỳ |
| Dựa vào thông báo miệng | Nhóm vắng mặt không biết thay đổi | Tài liệu chuẩn và changelog |
| Không có owner sau release | Sự cố tích hợp không được xử lý nhanh | Chỉ định owner vận hành contract |
| Đo collaboration bằng số cuộc họp | Tạo hoạt động nhưng không tạo kết quả | Đo compatibility, incident và thời gian ra quyết định |

## 22. Quy trình tiếp nhận thay đổi xuyên nhóm

Khi một team đề xuất thay đổi có thể ảnh hưởng đến context khác, có thể dùng checklist sau:

### Bước 1: Xác định vấn đề và giá trị nghiệp vụ

Viết tình huống, người bị ảnh hưởng, kết quả mong muốn và ví dụ thực tế. Không mặc định giải pháp ban đầu là phương án duy nhất.

### Bước 2: Xác định owner của khái niệm

Tìm bounded context sở hữu model, invariant, dữ liệu và contract liên quan. Nếu ownership chưa rõ, giải quyết câu hỏi đó trước khi sửa implementation.

### Bước 3: Phân loại phạm vi thay đổi

Xác định thay đổi nội bộ, local domain behavior, public contract, shared kernel, workflow liên context hay data ownership. Chọn quy trình tương ứng.

### Bước 4: Liệt kê consumer và stakeholder

Tìm các team, API, event, report, job và đối tác sử dụng thông tin. Xác minh bằng cả code search lẫn telemetry.

### Bước 5: Đánh giá impact và compatibility

Phân tích semantics, schema, data, workflow, version và khả năng triển khai đồng thời. Xác định breaking change và migration cần thiết.

### Bước 6: Thảo luận phương án với đúng người

Domain expert xác nhận nghiệp vụ; owner quyết định model; consumer owner xác nhận tác động; operations/security tham gia khi có ảnh hưởng tương ứng.

### Bước 7: Ghi quyết định

Tạo ADR hoặc decision log với bối cảnh, lựa chọn, lý do, trade-off, owner và điều kiện review.

### Bước 8: Chia kế hoạch theo team

Ghi rõ producer, consumer, contract test, thứ tự deploy, feature flag, data migration và người xử lý sự cố.

### Bước 9: Triển khai và theo dõi

Chạy test, rollout theo giai đoạn, theo dõi consumer adoption, lỗi contract và các chỉ số vận hành.

### Bước 10: Đóng thay đổi và cập nhật tài liệu

Xác nhận mục tiêu đạt được, deprecate phần cũ khi đủ điều kiện, cập nhật glossary/contract/ADR và ghi bài học nếu có sự cố.

## 23. Nguyên tắc thực hành

Khi phân quyền sở hữu mô hình và tiếp nhận thay đổi xuyên nhóm, nhóm nên nhớ:

- **Ownership theo bounded context.** Một team chịu trách nhiệm cho model, invariant, data và contract trong ranh giới.
- **Tách owner khỏi consumer.** Consumer góp ý và kiểm tra compatibility nhưng không điều khiển implementation nội bộ.
- **Domain expert xác nhận semantics.** Không suy đoán ý nghĩa nghiệp vụ từ tên field hoặc code cũ.
- **Phân loại thay đổi trước khi phối hợp.** Internal change không cần quy trình nặng; breaking contract cần impact review.
- **Công khai consumer và contract owner.** Biết ai đang dùng gì trước khi thay đổi.
- **Đánh giá cả cấu trúc lẫn semantics.** Schema không đổi vẫn có thể là breaking change nếu ý nghĩa đổi.
- **Ghi quyết định có lý do.** RFC đề xuất, ADR ghi quyết định, glossary giữ thuật ngữ, contract mô tả tương tác.
- **Quản lý Shared Kernel như tài sản đồng sở hữu.** Giữ nhỏ và có quy tắc thay đổi.
- **Triển khai tương thích theo giai đoạn.** Producer hỗ trợ trước, consumer chuyển đổi, rồi deprecate.
- **Có owner sau phát hành.** Theo dõi adoption, lag, lỗi và incident.
- **Giải quyết bất đồng bằng semantics và trade-off.** Không dùng shared model để che giấu khác biệt.
- **Giữ tài liệu gần với vòng đời code.** Cập nhật contract, tests, glossary và ADR cùng thay đổi.
- **Đo kết quả collaboration.** Ưu tiên ít breaking incident, quyết định rõ và onboarding tốt hơn số cuộc họp.

Phân quyền sở hữu mô hình giúp mỗi bounded context có một nhóm chịu trách nhiệm rõ ràng, trong khi thay đổi xuyên nhóm vẫn được thảo luận dựa trên ngôn ngữ, contract và tác động thực tế. Một quy trình tốt không biến mọi thay đổi thành thủ tục phê duyệt; nó giúp nhận diện đúng những thay đổi cần phối hợp, mời đúng người, ghi lại quyết định và triển khai theo cách consumer có thể thích nghi. Khi ownership, contract và tài liệu cùng được duy trì, các nhóm có thể tiến hóa mô hình riêng mà vẫn giữ được sự nhất quán của toàn hệ thống.

## 24. Câu hỏi tự kiểm tra

1. Vì sao mỗi bounded context cần có model owner và trách nhiệm ownership gồm những gì?
2. Phân biệt bounded context, owning team, domain expert, consumer team và model steward.
3. Vì sao team boundary không nhất thiết trùng với bounded context?
4. Những thay đổi nào có thể do owning team tự quyết và thay đổi nào cần tham vấn consumer?
5. Vì sao một thay đổi semantics có thể phá contract dù schema không đổi?
6. Quy trình tiếp nhận thay đổi xuyên nhóm nên gồm những bước nào?
7. Impact assessment cần kiểm tra những thành phần nào ngoài code của producer?
8. Consumer có quyền gì trong quá trình thay đổi contract và giới hạn quyền đó ở đâu?
9. Shared Kernel cần cơ chế đồng sở hữu và versioning như thế nào?
10. RFC, ADR, glossary, API/event contract và runbook khác nhau ở mục đích nào?
11. Deprecation cần những thông tin và điều kiện nào trước khi xóa contract cũ?
12. Làm thế nào để xử lý bất đồng khi hai context dùng cùng thuật ngữ nhưng khác semantics?
13. Những chỉ số nào phản ánh chất lượng collaboration tốt hơn số lượng cuộc họp?
14. Hãy chọn một thay đổi event hoặc API có ảnh hưởng đến ít nhất hai nhóm, lập proposal, impact map, decision record và kế hoạch rollout/deprecation.
