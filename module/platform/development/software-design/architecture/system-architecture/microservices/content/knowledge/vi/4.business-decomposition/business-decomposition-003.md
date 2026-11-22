# Miền con và ranh giới ngữ cảnh (Subdomain & Bounded Context)

> Trong kiến trúc microservices, bước phân rã quan trọng nhất là **xác định trách nhiệm nghiệp vụ và giới hạn của mô hình**, trước khi quyết định sẽ có bao nhiêu ứng dụng, API, database hoặc container. **Subdomain** giúp trả lời “doanh nghiệp đang có những bài toán nào?”; **bounded context** giúp trả lời “mô hình và ngôn ngữ nghiệp vụ nào có hiệu lực trong phạm vi nào?”. Hai khái niệm có liên hệ chặt chẽ nhưng không đồng nhất.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt domain, subdomain, bounded context, ubiquitous language, aggregate và microservice.
2. Phân loại **core**, **supporting** và **generic subdomain** theo giá trị chiến lược trong một bối cảnh kinh doanh cụ thể.
3. Phân tích từ ngữ, quy tắc, dữ liệu và quy trình để tìm ranh giới ngữ cảnh thay vì chia theo controller hoặc bảng.
4. Vẽ context map, nhận diện quan hệ giữa các bounded context và chọn cách tích hợp thích hợp.
5. Thiết kế phạm vi sở hữu dữ liệu, hợp đồng trao đổi, luồng nghiệp vụ xuyên ranh giới và bước triển khai trong Spring Boot.
6. Giải thích khi nào một bounded context nên trở thành microservice và khi nào nên ở lại trong modular monolith.

## 2. Từ miền nghiệp vụ đến miền con

### 2.1. Domain là gì?

**Domain** là lĩnh vực hoạt động cùng những bài toán mà phần mềm cần hỗ trợ: chẳng hạn thương mại điện tử, bảo hiểm, ngân hàng hay quản lý bệnh viện. Domain bao gồm mục tiêu, chính sách, khái niệm, quyết định và quy trình nghiệp vụ, không chỉ gồm các entity hoặc bảng dữ liệu.

Với một nền tảng bán hàng, phát biểu “xây dựng hệ thống thương mại điện tử” vẫn quá rộng để thiết kế service. Cần đi tiếp: quản lý danh mục, định giá, khuyến mại, tồn kho, đặt hàng, thanh toán, vận chuyển, chăm sóc khách hàng và báo cáo có những trách nhiệm rất khác nhau.

### 2.2. Subdomain là gì?

**Subdomain (miền con)** là một phần của domain tập trung vào một nhóm bài toán và năng lực nghiệp vụ tương đối nhất quán. Một subdomain được khám phá từ **hoạt động kinh doanh thực tế**; nó tồn tại về mặt phân tích nghiệp vụ ngay cả trước khi quyết định phần mềm sẽ được chia thành mấy service.

Ví dụ:

| Subdomain | Câu hỏi kinh doanh tiêu biểu | Quy tắc nổi bật |
| --- | --- | --- |
| Catalog | Sản phẩm được giới thiệu và mô tả như thế nào? | Cấu trúc danh mục, thuộc tính hiển thị, xuất bản |
| Pricing | Mức giá bán nào áp dụng cho trường hợp này? | Bảng giá, hiệu lực giá, phân khúc khách hàng |
| Promotions | Ưu đãi nào có thể áp dụng và kết hợp? | Điều kiện khuyến mại, thời hạn, giới hạn ngân sách |
| Ordering | Đơn hàng được tạo và chuyển trạng thái ra sao? | Vòng đời đơn, điều kiện xác nhận/hủy |
| Inventory | Số lượng nào có thể bán hoặc giữ trước? | Stock on hand, available to promise, reservation |
| Payments | Giao dịch nào đã được ủy quyền, thu hoặc hoàn? | Quy trình xác nhận, đối soát, chống thanh toán trùng |
| Fulfillment | Hàng được lấy, đóng gói và bàn giao thế nào? | Chọn kho, picking, packing, giao nhận |
| Identity | Ai đang truy cập và có quyền gì? | Xác thực, định danh, phân quyền |

Một năng lực kinh doanh như “đặt hàng” có thể cần phối hợp nhiều subdomain. **Một quy trình đi qua nhiều miền không có nghĩa mọi miền phải nằm trong cùng một mô hình hoặc cùng một transaction.**

### 2.3. Core, supporting và generic subdomain

Trong strategic Domain-Driven Design (DDD), có thể nhìn các miền con theo mức đóng góp vào lợi thế cạnh tranh của **chính doanh nghiệp**.

**Core subdomain** là nơi quyết định lợi thế khác biệt, cần hiểu sâu và đầu tư chất lượng mô hình. Ví dụ, doanh nghiệp giao thực phẩm trong 15 phút có thể xem thuật toán phân bổ đơn, kho và tuyến giao là core. Một sàn thương mại điện tử khác lại xem khả năng ghép người mua với người bán là core.

**Supporting subdomain** là phần cần thiết, có nét riêng nhưng ít quyết định khả năng cạnh tranh. Ví dụ, quy trình hỗ trợ đổi trả hoặc quản lý nội dung nội bộ có thể là supporting, tùy chiến lược.

**Generic subdomain** xử lý nhu cầu phổ biến có giải pháp dùng lại hoặc mua ngoài tương đối tốt: xác thực đăng nhập, gửi email, lưu trữ tài liệu, thanh toán qua nhà cung cấp... Cần đánh giá trường hợp cụ thể; thanh toán có thể là generic đối với một cửa hàng nhưng lại là core đối với một công ty fintech.

| Nhóm | Câu hỏi đánh giá | Gợi ý đầu tư |
| --- | --- | --- |
| Core | Nếu làm tốt vượt trội, khách hàng có chọn doanh nghiệp vì điều đó không? | Đầu tư chuyên gia miền, mô hình sâu, vòng phản hồi nhanh |
| Supporting | Có cần tùy biến cho cách vận hành của doanh nghiệp không? | Xây vừa đủ, giữ ranh giới rõ |
| Generic | Có giải pháp chuẩn/hàng hóa sẵn với chi phí hợp lý không? | Ưu tiên dùng lại hoặc tích hợp khi phù hợp |

**Phân loại mang tính chiến lược và thay đổi theo thời gian.** Nó không mặc định rằng core phải tách thành microservice, generic phải mua ngoài hoặc mỗi nhóm chỉ có một service. Mục đích là tập trung năng lực thiết kế vào bài toán có giá trị nhất.

## 3. Bounded context là gì?

**Bounded context (ranh giới ngữ cảnh)** là giới hạn rõ ràng trong đó một **mô hình nghiệp vụ** và ngôn ngữ của mô hình đó được hiểu nhất quán. Trong phạm vi ấy, các khái niệm như “đơn”, “khách hàng”, “giá”, “sản phẩm”, “trạng thái đã hoàn tất” có định nghĩa, thuộc tính và quy tắc cụ thể.

Bên ngoài ranh giới, cùng từ có thể mang nghĩa khác. Không cần ép toàn doanh nghiệp dùng chung một entity hoặc một bộ trạng thái nếu các nhóm nghiệp vụ thực sự có cách nhìn khác nhau.

**Ví dụ về từ “đơn hàng”:**

- Trong **Ordering Context**, đơn hàng là cam kết mua gồm dòng hàng, số tiền chốt tại thời điểm đặt và trạng thái xác nhận/hủy.
- Trong **Fulfillment Context**, đơn hàng có thể được nhìn như yêu cầu chuẩn bị và giao hàng, cần kiện hàng, vị trí kho và lần giao.
- Trong **Billing Context**, thông tin cần thiết là số tiền phải thu, chứng từ, thuế và đối soát.
- Trong **Customer Support Context**, nhân viên quan tâm lịch sử khiếu nại, hoàn tiền và lý do xử lý.

Bốn mô hình trên có thể tham chiếu cùng một mã đơn nhưng **không cần dùng chung class Order**, không cần có cùng mọi trường và không có quyền thay đổi trực tiếp trạng thái của nhau.

### 3.1. Ubiquitous language: ngôn ngữ chung trong ngữ cảnh

**Ubiquitous language** là ngôn ngữ mà chuyên gia nghiệp vụ và người phát triển cùng sử dụng trong một bounded context. Tên class, API, rule, sự kiện và tài liệu nên phản ánh từ vựng có nghĩa đối với người dùng nghiệp vụ ở ranh giới đó.

Ví dụ trong Inventory:

- “On hand”: lượng tồn vật lý trong kho.
- “Reserved”: lượng đã giữ cho đơn cụ thể.
- “Available to promise”: lượng có thể cam kết bán theo chính sách.
- “Release reservation”: nhả một phần giữ hàng.

Trong Catalog, từ “available” có thể chỉ nghĩa “sản phẩm đang được hiển thị để bán”. Nếu đặt hai khái niệm này chung một biến boolean isAvailable, hệ thống dễ trộn lẫn điều kiện hiển thị với điều kiện đủ tồn kho. Tách ngữ cảnh cho phép Catalog trả lời “có được đăng bán?” và Inventory trả lời “có thể cam kết bao nhiêu chiếc?”.

### 3.2. Ranh giới áp dụng cho mô hình, không chỉ code

Một bounded context quy định:

- Những quy tắc, thuật ngữ và bất biến nào thuộc phạm vi mô hình.
- Ai có quyền quyết định trạng thái nghiệp vụ và thay đổi ý nghĩa của chúng.
- Dữ liệu nào là nguồn sự thật (source of truth) cho các quy tắc đó.
- Bên ngoài được tương tác qua hợp đồng nào.
- Thay đổi nào có thể thực hiện độc lập và thay đổi nào đòi hỏi phối hợp.

Ranh giới có thể thể hiện qua một module trong modular monolith, một tập package với cổng giao tiếp rõ hoặc một hay nhiều dịch vụ triển khai riêng. **Bounded context không đồng nghĩa với tiến trình, API endpoint, repository, team hay database.**

## 4. Phân biệt subdomain và bounded context

Đây là khác biệt thường bị bỏ qua khi phân rã microservices:

| Góc nhìn | Subdomain | Bounded context |
| --- | --- | --- |
| Bản chất | Một **lĩnh vực bài toán** của doanh nghiệp | Một **phạm vi mà mô hình và ngôn ngữ có hiệu lực** |
| Câu hỏi | Doanh nghiệp cần giải quyết vấn đề nào? | Trong phạm vi này, các khái niệm có nghĩa và luật gì? |
| Nguồn khám phá | Hoạt động, năng lực, mục tiêu, chính sách kinh doanh | Quy tắc, thuật ngữ, mô hình, trách nhiệm và ranh giới giao tiếp |
| Chiến lược | Core, supporting, generic | Chủ sở hữu mô hình, quan hệ với context khác |
| Khi thay đổi | Chiến lược hoặc năng lực nghiệp vụ thay đổi | Mô hình, luật, trách nhiệm hoặc cách phối hợp thay đổi |
| Sản phẩm thiết kế | Bản đồ các miền con | Context map và kiến trúc ranh giới mô hình |

Một subdomain có thể được phục vụ bởi **nhiều bounded context** nếu có nhiều mô hình hợp lệ nhưng khác nhau. Chẳng hạn “Logistics” có mô hình quản lý kho vận nội bộ và mô hình theo dõi giao hàng của bên vận chuyển. Ngược lại, ở giai đoạn đầu, một bounded context nhỏ có thể giải quyết phần việc liên quan của nhiều subdomain khi tách riêng chưa mang lại lợi ích rõ.

**Không ép ánh xạ một-một** chỉ để các sơ đồ đẹp. Điều cần giữ là các quy tắc nghiệp vụ bên trong mỗi context nhất quán, còn sự tích hợp xuyên ranh giới được công bố và quản lý.

### 4.1. Aggregate không phải bounded context

Trong tactical DDD, **aggregate** là cụm đối tượng có một aggregate root giữ các bất biến cần nhất quán khi thay đổi trạng thái. Một bounded context có thể có nhiều aggregate như Order, ReturnRequest và CancellationPolicy. Aggregate thường có phạm vi nhỏ hơn context và giúp quyết định transaction nội bộ. Một service có thể sở hữu nhiều aggregate, còn nhiều service không nên cùng ghi trực tiếp vào một aggregate.

Đừng lấy “mỗi aggregate một microservice” làm quy tắc cứng; cũng đừng dùng số bảng hoặc số entity để suy ra số context.

## 5. Ví dụ xuyên suốt: bán hàng đa kênh

Giả sử một nền tảng bán hàng cần cho phép khách tìm sản phẩm, áp dụng khuyến mại, đặt đơn, giữ tồn kho, thanh toán và nhận hàng.

### 5.1. Phân rã ở mức nghiệp vụ

~~~text
Commerce Domain
|
+-- Product discovery / Catalog
+-- Pricing
+-- Promotions
+-- Ordering
+-- Inventory
+-- Payments
+-- Fulfillment
+-- Identity / Customer accounts
~~~

Đây là **bản đồ subdomain sơ bộ**, chưa phải kiến trúc microservices. Để tìm bounded context, cần phân tích cách các nhóm sử dụng thuật ngữ và dữ liệu.

### 5.2. Các mô hình hợp lệ của cùng một “sản phẩm”

| Context | “Product” hoặc khái niệm tương ứng | Điều context sở hữu |
| --- | --- | --- |
| Catalog | Thông tin để khách tìm, so sánh và xem | Tên hiển thị, mô tả, hình ảnh, taxonomy, trạng thái xuất bản |
| Pricing | Đối tượng chịu chính sách giá | Giá theo khu vực, phân khúc, hiệu lực, currency |
| Inventory | SKU và lượng tồn tại vị trí kho | Reservation, stock movement, available quantity |
| Ordering | Dòng hàng đã được khách chấp thuận mua | Snapshot tên, SKU, đơn giá/giảm giá tại thời điểm đặt |
| Fulfillment | Đơn vị cần lấy và đóng kiện | Kích thước, khối lượng, vị trí picking, package item |

Catalog có thể đổi tên sản phẩm ngày mai. **Tên và đơn giá trong đơn đã xác nhận không nên âm thầm thay theo Catalog hôm nay.** Order lưu snapshot cần thiết cho hợp đồng bán hàng. Inventory không cần biết mô tả marketing mới để xác định khả năng giữ hàng.

Cùng một productId/SKU có thể đi qua nhiều context để liên kết tham chiếu. **Dùng cùng định danh không đồng nghĩa dùng chung mô hình hoặc quyền sở hữu dữ liệu.**

### 5.3. Mỗi context quyết định bất biến của mình

- Ordering quyết định khi nào Order có thể chuyển PENDING sang CONFIRMED hay CANCELLED.
- Inventory quyết định một reservation có hợp lệ hay vượt mức hàng có thể bán.
- Pricing quyết định chính sách giá tại thời điểm báo giá.
- Payments quyết định một payment attempt đã authorized, captured, failed hoặc refunded.
- Fulfillment quyết định một package đã picked, packed, dispatched hay delivered.

Khi Order cần biết “giữ hàng có thành công không?”, nó **gửi yêu cầu qua hợp đồng Inventory**. Nó không trực tiếp sửa bảng inventory_reservation của Inventory. Khi Billing cần biết đơn được xác nhận, nó tiêu thụ dữ liệu được công bố theo contract, không JOIN trực tiếp các bảng của Order.

### 5.4. Context map sơ bộ

~~~text
[Catalog Context] ----- ProductPublished ------> [Search Context]
       |
       +------ ProductSummary ------------------> [Ordering Context]
                                                 |       |
[Pricing Context] ---- PriceQuote ---------------+       |
                                                         |
[Inventory Context] <--- Reserve/Release ---------------+
       |                                                 |
       +------ ReservationResult ------------------------>+
                                                         |
[Payments Context] <--- ChargeRequest -------------------+
       |                                                 |
       +------ PaymentStatus ---------------------------->+
                                                         |
[Fulfillment Context] <--- OrderReadyForFulfillment -----+
       |
       +------ ShipmentStatus --------------------------> [Customer Support]
~~~

Mũi tên chỉ **quan hệ và hướng trao đổi thông tin**, chưa bắt buộc lựa chọn HTTP, gRPC hay message broker. Một sơ đồ đầy đủ còn cần ghi rõ **ai sở hữu hợp đồng, ai phụ thuộc ai, cơ chế giao tiếp, mức nhất quán và cách xử lý lỗi**.

## 6. Context map: các ranh giới hợp tác như thế nào?

**Context map** là tài liệu về những bounded context có mặt trong hệ thống và cách mô hình của chúng kết nối với nhau. Nó chứa cả quan hệ tổ chức và quan hệ kỹ thuật: đâu là hệ thống upstream tạo dữ liệu, đâu là downstream tiêu thụ, bên nào có quyền thay đổi hợp đồng và bên nào chịu chi phí thích nghi.

Những pattern thường gặp trong strategic DDD:

### 6.1. Partnership

Hai nhóm/context có nhu cầu phối hợp chặt, cùng lập kế hoạch thay đổi và chia sẻ trách nhiệm tương tác. Ví dụ Ordering và Fulfillment đang cùng thiết kế một năng lực giao nhiều chặng mới. Partnership có chi phí phối hợp, vì vậy không thể áp dụng cho mọi tích hợp.

### 6.2. Customer–Supplier

Một context **upstream (supplier)** cung cấp dữ liệu/dịch vụ; context **downstream (customer)** có nhu cầu được cân nhắc khi supplier thiết kế và tiến hóa API. Ví dụ Inventory cung cấp hợp đồng giữ hàng cho Ordering, còn Ordering tham gia xác định yêu cầu chức năng của hợp đồng. Quan hệ này có ích khi hai nhóm chủ động phối hợp thay đổi.

### 6.3. Conformist

Downstream chấp nhận mô hình/hợp đồng do upstream áp đặt, không có nhiều quyền tác động. Ví dụ ứng dụng nhỏ bắt buộc tích hợp API của một nhà cung cấp SaaS không thể đàm phán schema. Đây là lựa chọn thực dụng nếu khác biệt mô hình nhỏ; nếu khác biệt lớn, áp dụng trực tiếp mô hình bên ngoài sẽ lan nhiễm khắp code.

### 6.4. Anti-Corruption Layer (ACL)

Một lớp chuyển đổi giúp **bảo vệ mô hình nội bộ khỏi từ vựng và quy tắc của mô hình khác**, đặc biệt khi tích hợp hệ thống legacy hoặc nhà cung cấp bên ngoài.

Ví dụ, hệ thống giao hàng bên ngoài trả orderStatus = "COMPLETED" để nói “bàn giao thành công cho hãng vận chuyển”, trong khi trong Ordering “COMPLETED” nghĩa “khách đã nhận hàng”. ACL không chuyển một cách máy móc hai giá trị thành cùng một enum; nó ánh xạ trạng thái theo ý nghĩa nghiệp vụ:

~~~text
Partner status: COMPLETED
      |
      v
[Shipping Partner ACL]
      |
      v
Fulfillment status: HANDED_OVER_TO_CARRIER

Không đồng nhất với:
Ordering status: DELIVERED_TO_CUSTOMER
~~~

ACL có thể gồm adapter, translator, facade, validator, chính sách chuyển trạng thái và cơ chế ghi nhận dữ liệu thiếu. Nó không chỉ là lớp đổi tên field.

### 6.5. Shared Kernel

Hai context chia sẻ **một phần mô hình rất nhỏ** do cùng chịu trách nhiệm duy trì, ví dụ một value object được quản trị chung. Có thể giảm lặp code nhưng làm tăng coupling khi thay đổi. Tránh dùng shared-kernel để nhét toàn bộ entity, DTO, enum và database model của doanh nghiệp vào một package dùng chung.

### 6.6. Open Host Service và Published Language

Một context có thể cung cấp hợp đồng công khai ổn định cho nhiều consumer (**Open Host Service**) và một ngôn ngữ trao đổi được mô tả rõ, có phiên bản và quy tắc tiến hóa (**Published Language**), chẳng hạn API contract hoặc event schema. Các consumer không cần biết cấu trúc database/domain entity bên trong provider.

Ví dụ, thay vì public nguyên JPA OrderEntity, Ordering công bố hợp đồng OrderConfirmed với orderId, confirmedAt, các dòng hàng cần thiết và schema version. Fulfillment và Support xử lý theo nhu cầu riêng của từng context.

**Chọn quan hệ theo thực tế quyền lực và mức hợp tác.** Trên một context map, các cặp context khác nhau có thể dùng những pattern khác nhau. Một doanh nghiệp không nhất thiết chỉ có một pattern.

## 7. Tìm ranh giới thực tế từ quy trình và ngôn ngữ

Ranh giới tốt thường xuất hiện ở nơi thay đổi **ý nghĩa, quyền quyết định, luật nghiệp vụ, nguồn dữ liệu hoặc yêu cầu nhất quán**.

### Bước 1 — Chọn một luồng nghiệp vụ có giá trị

Ví dụ: “Khách đặt mua 2 sản phẩm, thanh toán thành công và được giao trong ngày”. Hãy mời chuyên gia từ bán hàng, kho, tài chính, hỗ trợ và vận hành mô tả những gì thực sự xảy ra, kể cả ngoại lệ.

### Bước 2 — Phác họa các domain event theo dòng thời gian

Các event có thể được mô tả ở thì quá khứ:

~~~text
CartCheckedOut
  -> OrderPlaced
  -> StockReserved
  -> PaymentAuthorized
  -> OrderConfirmed
  -> PackagePacked
  -> PackageDispatched
  -> PackageDelivered
~~~

Tên event ở đây **là gợi ý để khám phá**, không phải yêu cầu mọi event phải được phát qua message broker. Nghiệp vụ thực tế có thể thanh toán trước rồi mới giữ tồn, hoặc chỉ thu tiền sau khi giao. Hãy khám phá thứ tự, ngoại lệ và bất biến thực tế trước khi chốt kiến trúc.

### Bước 3 — Hỏi “ai quyết định?” ở mỗi bước

- Ai quyết định mức giá cuối cùng? Pricing hay Ordering?
- Ai được quyền xác nhận còn đủ hàng? Inventory.
- Ai chịu trách nhiệm chống trừ tiền hai lần? Payments.
- Ai có thẩm quyền hủy đơn đã đóng gói? Ordering phối hợp Fulfillment theo chính sách nào?
- Ai công bố sự kiện có ý nghĩa “đơn hoàn tất”? Ordering, Fulfillment hay cả hai với ngữ nghĩa khác nhau?

Những chỗ câu trả lời “cả hai cùng sửa một trạng thái” thường cần phân tích thêm để tách **quyền quyết định** và **quyền theo dõi**.

### Bước 4 — Tìm từ đồng âm khác nghĩa

Ghi nhận khi chuyên gia dùng cùng từ nhưng định nghĩa khác:

- “Hoàn tất” với Payments nghĩa là tiền đã được captured; với Fulfillment là gói hàng đã delivered.
- “Khách hàng” với Identity là account đăng nhập; với Billing là pháp nhân hoặc thông tin người nhận hóa đơn.
- “Giá” với Catalog có thể là giá gợi ý hiển thị; với Ordering là số tiền khách đã đồng ý ở thời điểm mua.
- “Hàng còn” với Catalog có thể chỉ trạng thái listing; với Inventory là available-to-promise.

Đây là tín hiệu cần ranh giới ngôn ngữ. **Không nhất thiết cứ có một từ khác nghĩa là phải tạo microservice mới.**

### Bước 5 — Tìm bất biến cần giữ nguyên tử

Ví dụ: “Không có hai reservation cùng tiêu thụ vượt quá lượng available của cùng SKU tại cùng kho”. Quy tắc này nên được thực thi bởi Inventory. Một transaction cục bộ của Inventory có thể bảo vệ nó. Bất biến “đơn CONFIRMED phải có kết quả giữ hàng hợp lệ” nằm trong quy trình phối hợp với Ordering; có thể cần trạng thái trung gian, idempotency và bù trừ thay vì cố mở một transaction SQL xuyên nhiều context.

Bất biến thuộc cùng một mô hình và thường thay đổi cùng nhau là tín hiệu nên đặt gần nhau. Tuy nhiên, không nên gom toàn bộ chuỗi nghiệp vụ vào một context chỉ vì các bước có liên hệ.

### Bước 6 — Kiểm tra nhịp thay đổi và quyền sở hữu

Nhóm Pricing có thường đổi chính sách giá mà không muốn thay đổi code của Ordering? Nhóm vận hành kho có cần tự điều chỉnh chính sách reservation? Việc mở rộng riêng Inventory có mang lại lợi ích vận hành không? Những sự khác biệt thực tế hỗ trợ quyết định ranh giới service, sau khi đã hiểu mô hình.

### Bước 7 — Vẽ context map và xác nhận với chuyên gia

Vẽ các context, tên người chịu trách nhiệm, dữ liệu nguồn, event/API nhận và phát, hướng upstream/downstream, chính sách versioning và tình huống lỗi. Đọc lại sơ đồ cùng người làm nghiệp vụ để tránh ranh giới chỉ đúng trong tưởng tượng của kỹ sư.

## 8. Từ bounded context sang microservice: không phải phép đổi tên

Một phương án thường hữu ích là **một microservice sở hữu một bounded context có tính kết dính cao**. Nhưng đây là một heuristic thiết kế, không phải định luật.

### 8.1. Ba mức triển khai có thể gặp

~~~text
A. Modular monolith
   [Commerce Application]
       |- Catalog Context (module)
       |- Ordering Context (module)
       |- Inventory Context (module)
   -> One runtime/deployment, explicit internal boundaries

B. Multiple microservices
   [Catalog Service]   [Ordering Service]   [Inventory Service]
     own model/data      own model/data       own model/data
   -> Separate deployable units, explicit API/event contracts

C. Hybrid
   [Commerce Core]
      |- Ordering Context
      |- Promotions Context
   [Inventory Service]  [Payments Service]
   -> Extract only boundaries with clear independent benefits
~~~

Trong A, các context vẫn có thể có interface và mô hình riêng, chỉ chưa cần chi phí phân tán. Trong B, sự độc lập khi triển khai tạo lợi ích nhưng cũng đòi hỏi xử lý mạng, contract và nhất quán dữ liệu. Trong C, doanh nghiệp có thể tiến hóa theo nhu cầu mà không phải tách toàn bộ hệ thống một lần.

### 8.2. Những tiêu chí quyết định tách service

- **Cohesion:** chức năng của context có tập trung vào một trách nhiệm nghiệp vụ rõ ràng không?
- **Coupling:** thay đổi trong context có thường buộc context khác sửa theo không?
- **Autonomous change:** có thể build, kiểm thử và phát hành riêng khi giữ contract tương thích không?
- **Data ownership:** có thể xác định nơi quản lý nguồn sự thật và bỏ quyền ghi xuyên boundary không?
- **Consistency:** nghiệp vụ có chịu được độ trễ và trạng thái trung gian không?
- **Operational fit:** nhóm có đủ khả năng CI/CD, tracing, alert, bảo mật và xử lý sự cố mạng không?
- **Business value:** việc tách có giải quyết điểm nghẽn phát hành, scale hoặc tổ chức thật sự không?

Nếu không có lợi ích rõ, một bounded context được triển khai tốt trong modular monolith vẫn là kết quả đúng. Ngược lại, chia thành 20 container mà mọi thay đổi phải phát hành cùng nhau là dấu hiệu **distributed monolith**, bất kể tên service nghe giống miền nghiệp vụ.

## 9. Quyền sở hữu dữ liệu và tích hợp xuyên context

### 9.1. Sở hữu mô hình quan trọng hơn sở hữu máy chủ database

Ordering có thể sở hữu dữ liệu về Order; Inventory sở hữu Stock và Reservation; Payments sở hữu PaymentAttempt và Refund. Mỗi context cần kiểm soát các bất biến và cách thay đổi schema của mình.

Trong microservices, thực hành phổ biến là **database-per-service theo quyền sở hữu**. Không bắt buộc mỗi service có server vật lý riêng, nhưng hạn chế chặt quyền đọc/ghi xuyên schema và tránh các JOIN hoặc transaction SQL phụ thuộc nội bộ của service khác.

Ví dụ không nên làm:

~~~sql
-- Trong Ordering Service: cập nhật trực tiếp bảng do Inventory sở hữu
UPDATE inventory.stock
SET reserved_quantity = reserved_quantity + 2
WHERE sku = 'SKU-123';
~~~

Ordering nên gọi một contract như ReserveStock(commandId, orderId, sku, quantity) và để Inventory quyết định chấp nhận hay từ chối.

### 9.2. Trao đổi dữ liệu: request/response và sự kiện

**Request/response** (REST, gRPC) phù hợp khi cần hỏi hoặc yêu cầu một tác vụ và nhận kết quả trực tiếp, ví dụ báo giá hay giữ hàng. Nó cần deadline, timeout và chính sách retry an toàn.

**Domain event** mô tả một sự kiện đã xảy ra bên trong context theo ngôn ngữ của context, chẳng hạn StockReserved, OrderConfirmed hoặc PaymentCaptured. Downstream có thể cập nhật read model của riêng mình mà không can thiệp database nguồn. Event phải có hợp đồng rõ và khả năng tiến hóa phiên bản.

Không phải mọi thay đổi field đều đáng phát event. Event nghiệp vụ nên gắn với điều đã xảy ra và có ý nghĩa cho consumer. Nếu cần snapshot đọc, consumer có thể giữ projection riêng, ghi rõ độ trễ cho phép và cách tái đồng bộ.

### 9.3. Không giả định một transaction xuyên nhiều context

Nếu Order cần giữ hàng và thu tiền, thất bại có thể xuất hiện giữa các bước. Không nên coi các lời gọi HTTP liên tiếp là một transaction nguyên tử. Có thể cần:

- Trạng thái nghiệp vụ như PENDING, AWAITING_PAYMENT và CONFIRMED.
- Saga/orchestration hoặc choreography phù hợp để quản lý quy trình dài.
- Compensating action như release reservation hoặc refund theo chính sách.
- Transactional outbox để gắn việc ghi dữ liệu nội bộ với việc công bố thông điệp.
- Idempotency key để xử lý lệnh và thông điệp trùng lặp khi retry.
- Reconciliation để phát hiện và xử lý trạng thái lệch kéo dài.

Ví dụ: Payment đã captured nhưng response bị timeout. Ordering **không được tự suy đoán là chưa thu tiền rồi gọi lại bằng một paymentId mới**. Nó cần truy vấn trạng thái theo idempotency key hoặc nhận kết quả bền vững theo contract.

### 9.4. Hợp đồng không nên rò rỉ entity nội bộ

Nếu Payment expose nguyên JPA PaymentEntity gồm tên bảng, enum storage và quan hệ ORM, consumer sẽ gắn chặt vào chi tiết triển khai. Thay vào đó, công bố một DTO hoặc event được thiết kế theo nhu cầu tích hợp, với ngữ nghĩa, version và chính sách tương thích được mô tả.

Hợp đồng có thể ổn định ngay cả khi entity, storage engine hoặc thuật toán bên trong thay đổi.

## 10. Ví dụ Java/Spring Boot: chống rò rỉ mô hình bằng Anti-Corruption Layer

Giả sử Ordering gọi một hệ thống kho cũ. Phía kho dùng khái niệm “allocation”, trong khi Ordering chỉ cần câu trả lời “đã giữ được hàng cho đơn chưa?”. Ordering không nên mang enum trạng thái của kho vào toàn bộ domain model.

### 10.1. Cổng nghiệp vụ ở phía Ordering

~~~java
package com.example.ordering.domain;

import java.util.UUID;

// Ngôn ngữ của Ordering Context
public interface StockReservationPort {
    ReservationDecision reserve(
            UUID orderId,
            String sku,
            int quantity,
            String requestId
    );
}

public record ReservationDecision(boolean accepted, String reservationId) {
    public static ReservationDecision rejected() {
        return new ReservationDecision(false, null);
    }

    public static ReservationDecision accepted(String id) {
        return new ReservationDecision(true, id);
    }
}
~~~

Port dùng từ ngữ phù hợp với Ordering, không phơi bày tên field hay status của hệ thống kho. Để ví dụ ngắn, mã minh họa không trình bày đầy đủ validation, exception hierarchy, transaction và telemetry.

### 10.2. Adapter chuyển từ mô hình bên ngoài sang nội bộ

~~~java
package com.example.ordering.infrastructure.inventory;

import com.example.ordering.domain.ReservationDecision;
import com.example.ordering.domain.StockReservationPort;
import org.springframework.stereotype.Component;
import java.util.UUID;

@Component
final class LegacyInventoryAdapter implements StockReservationPort {
    private final LegacyInventoryClient client;

    LegacyInventoryAdapter(LegacyInventoryClient client) {
        this.client = client;
    }

    @Override
    public ReservationDecision reserve(
            UUID orderId, String sku, int quantity, String requestId) {
        var response = client.allocate(new AllocationRequest(
                orderId.toString(), sku, quantity, requestId));

        return switch (response.status()) {
            case "ALLOCATED" ->
                    ReservationDecision.accepted(response.allocationId());
            case "OUT_OF_STOCK" ->
                    ReservationDecision.rejected();
            default ->
                    throw new IllegalStateException(
                            "Unknown allocation status: " + response.status());
        };
    }
}

// Chỉ tồn tại trong adapter/infrastructure của Ordering.
// Client thực có thể dùng RestClient, WebClient, gRPC hoặc SDK của nhà cung cấp.
interface LegacyInventoryClient {
    AllocationResponse allocate(AllocationRequest request);
}

record AllocationRequest(
        String externalOrderRef, String itemCode, int units, String key) {}

record AllocationResponse(String status, String allocationId) {}
~~~

Trong ví dụ, method reserve là interface do Ordering sở hữu; phần infrastructure hiểu status “ALLOCATED” và “OUT_OF_STOCK”. Nếu hệ thống kho đổi tên trạng thái hoặc API, nơi thích nghi chủ yếu là adapter. Domain của Ordering vẫn nói “reservation accepted/rejected”.

Lưu ý: timeout và kết quả **không xác định** không nên bị ánh xạ thành “rejected”. Trong production, cần trạng thái UNKNOWN/PENDING, truy vấn lại theo requestId hoặc cơ chế reconciliation; nếu không, retry có thể tạo nhiều allocation. Bản minh họa chủ yếu làm rõ **ngôn ngữ và boundary**.

### 10.3. Vì sao tên package và controller chưa đủ?

Cấu trúc:

~~~text
com.example.commerce
  |- catalog/
  |- ordering/
  |- inventory/
  |- payment/
~~~

chỉ là bước đầu. Nếu package ordering import trực tiếp InventoryJpaEntity hoặc cập nhật inventory repository, ranh giới vẫn bị xuyên thủng. Nếu muốn giữ các context trong một monolith, có thể tổ chức thành các module, quy định API công khai cho module, giữ implementation package private khi phù hợp và dùng kiểm tra dependency để phát hiện import trái phép.

Khi một context được tách thành service riêng, interface và hợp đồng tích hợp vẫn được giữ ở mức ý nghĩa nghiệp vụ; phần adapter chỉ đổi từ lời gọi in-process sang giao tiếp mạng, kèm thêm khả năng chống lỗi phân tán.

## 11. Các dấu hiệu phân chia sai ranh giới

**Chia theo lớp kỹ thuật:** UserControllerService, UserBusinessService, UserRepositoryService chạy ở ba process. Một thao tác CRUD đi qua nhiều mạng nhưng không có năng lực nghiệp vụ nào tự chủ. Đây thường là “distributed layers”, không phải bounded context tốt.

**Chia theo bảng:** Mỗi bảng orders, order_items, addresses, order_statuses có một service chỉ vì tên bảng khác nhau. Bất biến Order buộc phải phân tán qua nhiều lời gọi và transaction phức tạp. Nên phân tích aggregate và context trước khi quyết định.

**Dùng chung toàn bộ domain entity:** Các service import cùng một “common-domain.jar” chứa Entity, JPA mapping và mọi enum, nên mỗi thay đổi nhỏ kéo theo nâng version hàng loạt. Shared Kernel chỉ nên bao gồm phần thực sự có lý do quản trị chung, với quy trình thay đổi rõ.

**Cùng từ nhưng khác nghĩa bị ép dùng chung:** “Completed” của Payment và Fulfillment dùng chung OrderStatus.COMPLETED, làm mất ngữ nghĩa. Dùng ngôn ngữ theo context và mapping ở biên tích hợp.

**Nhiều service cùng ghi một bảng:** Ownership mơ hồ; một nhóm thay schema làm nhóm khác lỗi. Cần tìm một nơi duy nhất quản lý quy tắc và cung cấp hợp đồng để người khác yêu cầu thay đổi.

**Một thay đổi luôn buộc phát hành đồng loạt:** Dù có API Gateway và Kubernetes, coupling phát hành vẫn cao. Nên kiểm tra hướng phụ thuộc, contract versioning, migration và khả năng tương thích.

**Event có tên mơ hồ:** Các sự kiện như EntityUpdated hoặc StatusChanged làm consumer phải hiểu sâu cấu trúc nguồn. Nên mô tả rõ điều đã xảy ra, ai phát và người nhận được phép hiểu điều gì từ nó.

**Ranh giới chỉ theo sơ đồ tổ chức:** Team A và Team B được giao hai service nhưng công việc và bất biến luôn đan chéo. Cần đối chiếu với nhiệm vụ kinh doanh và nhịp thay đổi thực tế.

**Mỗi subdomain bắt buộc một microservice:** Subdomain là phạm vi vấn đề; việc tách deploy là quyết định triển khai. Những context quá nhỏ hoặc biến động mạnh có thể nên cùng một ứng dụng module hóa.

## 12. Quy trình thiết kế ranh giới có thể áp dụng ngay

### Giai đoạn 1 — Khám phá

1. Chọn một giá trị kinh doanh hoặc một customer journey có nhiều thay đổi.
2. Ghi subdomain, người phụ trách, chính sách và thuật ngữ thực tế.
3. Làm workshop/event storming để hiện luồng bình thường và ngoại lệ.
4. Tìm từ có nhiều nghĩa, dữ liệu bị tranh quyền sửa và bất biến cần bảo vệ.
5. Đề xuất các bounded context và đặt tên theo **trách nhiệm**, không theo công nghệ.

### Giai đoạn 2 — Vẽ ranh giới

1. Mỗi context có bảng từ vựng và danh sách quy tắc nó quyết định.
2. Ghi những aggregate hoặc entity quan trọng và nguồn dữ liệu chuẩn.
3. Vẽ context map: ai upstream, downstream, partnership, ACL hoặc shared kernel.
4. Xác định hợp đồng API/event và dữ liệu tối thiểu cần gửi qua ranh giới.
5. Liệt kê các hành trình nghiệp vụ qua nhiều context cùng chính sách consistency/failure.

### Giai đoạn 3 — Ra quyết định triển khai

1. Chọn modular monolith, microservice hay mô hình kết hợp theo nhu cầu hiện tại.
2. Đánh giá chi phí network, migration, security, CI/CD, observability và quản trị contract.
3. Với service cần tách, xây đường giao tiếp công khai trước và ngừng direct write vào dữ liệu của nhau.
4. Tách dữ liệu theo ownership, kiểm soát migration, áp dụng compatibility và quan sát lỗi.
5. Đo kết quả: tần suất phát hành độc lập, số lần thay đổi chéo, incident ảnh hưởng dây chuyền và thời gian khôi phục.

Một tài liệu thiết kế ranh giới hữu ích có thể ghi theo mẫu:

~~~text
Context: Inventory
Purpose: Quản lý lượng tồn và reservation có thể cam kết
Language: SKU, StockOnHand, Reservation, AvailableToPromise
Owns: stock ledger, reservation lifecycle, stock availability rules
Inputs: ReserveStock, ReleaseStock, ReceiveStock
Outputs: StockReserved, ReservationRejected, StockReleased
Invariants: Không cam kết quá ngưỡng tồn được phép
Upstream/Downstream: Tương tác với Ordering và Fulfillment qua contract
Consistency: Local transaction cho stock/reservation; eventual ở read model ngoài context
Failure policy: timeout, idempotency key, retry, reconciliation
Deployment decision: tách khi cần scale/phát hành độc lập có giá trị
~~~

Mẫu chỉ mang tính minh họa. Tài liệu thực tế cần phản ánh đặc thù ngành và chính sách nghiệp vụ được phê duyệt.

## 13. Bài tập phân tích và gợi ý lời giải

### Bài tập 1 — “Customer” có phải một mô hình chung?

Một công ty có hệ thống đăng nhập, hệ thống thanh toán doanh nghiệp và hệ thống chăm sóc khách hàng. Cả ba đều dùng tên Customer. Hãy quyết định có nên tạo common.CustomerEntity để mọi ứng dụng cùng đọc/ghi không.

**Gợi ý lời giải:** Chưa đủ cơ sở dùng một entity chung. Identity có thể quan tâm tài khoản, phiên và quyền truy cập; Billing cần pháp nhân, địa chỉ hóa đơn, mã số thuế; Support cần ticket, người liên hệ và lịch sử tương tác. Đây có thể là ba bounded context khác nhau với các tham chiếu định danh và hợp đồng chuyển đổi. Nếu có dữ liệu dùng chung, cần xác định một chủ sở hữu và cách đồng bộ.

### Bài tập 2 — Product ở Catalog và Order

Catalog đổi tên sản phẩm từ “Áo basic” sang “Áo cotton basic”. Đơn của khách đã đặt từ tuần trước có nên cập nhật tên và đơn giá theo Catalog không?

**Gợi ý lời giải:** Không nên cập nhật vô điều kiện. Ordering thường phải lưu snapshot các thông tin đã chốt khi khách đặt đơn để phản ánh cam kết bán hàng và phục vụ đối soát. Catalog sở hữu mô tả hiện tại; Ordering sở hữu dòng hàng của giao dịch lịch sử.

### Bài tập 3 — Chia thành microservice theo subdomain

Một nhóm 4 người có hệ thống đặt hàng nhỏ, thay đổi nghiệp vụ hàng ngày, chưa có distributed tracing và chỉ triển khai 1–2 lần/tuần. Họ phát hiện Ordering, Pricing và Inventory là những phạm vi nghiệp vụ khác nhau. Có nên lập tức tách thành ba service không?

**Gợi ý lời giải:** Chưa bắt buộc. Có thể bắt đầu bằng modular monolith với ranh giới domain, API nội bộ và ownership rõ ràng. Tách service khi lợi ích phát hành, scale hoặc tổ chức lớn hơn chi phí vận hành phân tán.

### Bài tập 4 — Trạng thái “COMPLETED”

Đối tác vận chuyển gửi status “COMPLETED”, nghĩa là đã nhận kiện từ kho. Bên chăm sóc khách hàng lại diễn giải “COMPLETED” là khách đã nhận kiện. Cần xử lý thế nào?

**Gợi ý lời giải:** Nhận diện khác biệt ngữ nghĩa giữa các context, đặt tên trạng thái rõ và áp dụng ACL ở phía tích hợp. Chuyển “COMPLETED” của đối tác thành HandedOverToCarrier (hoặc khái niệm tương đương), không chuyển thành DeliveredToCustomer nếu chưa có bằng chứng giao thành công.

### Bài tập 5 — Luồng đặt hàng xuyên boundary

Ordering tạo Order, Inventory giữ hàng, Payments thu tiền. Payment thành công nhưng kết quả trả về bị timeout. Ordering có thể tự ghi payment_status = FAILED để khách đặt lại không?

**Gợi ý lời giải:** Không được suy luận kết quả chỉ từ timeout. Payment là chủ sở hữu giao dịch; cần dùng idempotency key, truy vấn trạng thái hoặc nhận sự kiện bền vững. Quy trình điều phối giữ trạng thái chưa xác định và xử lý reconciliation/bù trừ theo chính sách đã định.

### Bài tập 6 — Tìm boundary sai

Một hệ thống có bốn ứng dụng: API App, Validation App, Business App và Database App. Mỗi request bắt buộc qua cả bốn; mọi deploy đều cùng phiên bản. Hệ thống có bốn bounded context không?

**Gợi ý lời giải:** Không có bằng chứng về bốn mô hình nghiệp vụ độc lập. Cách chia hiện tại chủ yếu theo lớp kỹ thuật và có coupling triển khai cao. Hãy phân rã theo trách nhiệm nghiệp vụ, thuật ngữ và bất biến trước khi xác định bounded context hoặc microservice.

## 14. Các câu hỏi nên hỏi trong một buổi review thiết kế

- Tên context mô tả một **năng lực nghiệp vụ** hay chỉ một lớp kỹ thuật?
- Những từ nào có nghĩa khác nhau ở hai context và đang được dịch ở đâu?
- Khi một quy tắc đổi, nhóm nào có quyền quyết định và nơi nào phải sửa?
- Ai là chủ sở hữu duy nhất của bất biến và dữ liệu nghiệp vụ?
- Có service khác ghi trực tiếp vào database hoặc lấy entity nội bộ để dùng chung không?
- Hợp đồng tích hợp có ngữ nghĩa, version, error behavior và tính tương thích không?
- Một timeout, event trùng hoặc thất bại giữa chừng sẽ tạo ra trạng thái gì?
- Các context có thể phát hành độc lập khi giữ contract tương thích không?
- Tại sao lựa chọn hiện tại là microservice thay vì module trong monolith?
- Ranh giới có được chuyên gia nghiệp vụ xác nhận và có thể thay đổi khi hiểu biết mới xuất hiện không?

## 15. Ghi nhớ

1. **Domain là lĩnh vực kinh doanh; subdomain là nhóm bài toán; bounded context là ranh giới áp dụng của một mô hình và ngôn ngữ nghiệp vụ.**
2. **Core/supporting/generic** giúp ưu tiên đầu tư mô hình theo lợi thế cạnh tranh; không trực tiếp quyết định số microservice.
3. **Một khái niệm có thể có nhiều mô hình hợp lệ**: Product của Catalog khác Product/SKU của Inventory và khác OrderLine trong Ordering.
4. **Context map** giúp nhìn quan hệ hợp tác, upstream/downstream và cách chuyển đổi mô hình giữa các context.
5. **Quyền sở hữu dữ liệu, bất biến, contract và xử lý lỗi xuyên context** quyết định mức tự chủ thực tế; tên service, số endpoint hoặc số container không đủ.
6. **Bounded context có thể tồn tại trong modular monolith.** Chỉ tách thành microservice khi chi phí phân tán được bù bởi giá trị kinh doanh và vận hành.
7. **Ranh giới là giả thuyết thiết kế có thể cải tiến**, được kiểm chứng bằng sự nhất quán của mô hình, tần suất thay đổi chéo và khả năng tiến hóa an toàn.