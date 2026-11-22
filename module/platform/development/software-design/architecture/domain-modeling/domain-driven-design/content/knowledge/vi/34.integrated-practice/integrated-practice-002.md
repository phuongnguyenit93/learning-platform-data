# Xây dựng ngôn ngữ chung và phân loại các miền con

Domain-Driven Design (DDD) bắt đầu bằng việc hiểu bài toán kinh doanh và cách tổ chức tạo ra giá trị. Trước khi chọn aggregate, repository hay framework, nhóm cần biết doanh nghiệp đang thực hiện những hoạt động nào, khái niệm nào có ý nghĩa, các quyết định được đưa ra theo quy tắc nào và phần năng lực nào tạo ra lợi thế cạnh tranh. Hai công việc chiến lược quan trọng là xây dựng **Ubiquitous Language (ngôn ngữ chung)** và **phân loại subdomain (miền con)**.

Ubiquitous Language giúp chuyên gia nghiệp vụ và đội phát triển trao đổi bằng cùng một hệ thuật ngữ trong một bounded context. Khi chuyên gia nói “giữ hàng”, “ủy quyền thanh toán” hoặc “xác nhận đơn”, code, test, tài liệu và cuộc thảo luận cần thể hiện đúng ý nghĩa của các hành động đó. Subdomain giúp chia domain lớn thành các phần bài toán có mục tiêu và mức độ chiến lược khác nhau, từ đó quyết định nơi cần đầu tư mô hình sâu, nơi có thể dùng giải pháp tiêu chuẩn và nơi nên đơn giản hóa.

Hai việc này liên kết chặt chẽ nhưng không thay thế nhau. Ngôn ngữ chung làm rõ một phần nghiệp vụ; phân loại subdomain cho biết phần đó có vai trò chiến lược ra sao. Bounded Context xác định ranh giới nơi một mô hình và ngôn ngữ nhất quán được áp dụng. Bài học này hướng dẫn một nhóm thực hiện từ khám phá domain, lập glossary, nhận diện subdomain, phân loại Core/Supporting/Generic, đến xác định bounded context và kiểm chứng kết quả bằng một case study xuyên suốt.

## 1. Mục tiêu của bài thực hành

Sau khi hoàn thành bài thực hành, nhóm cần có khả năng:

- Mô tả domain và mục tiêu kinh doanh bằng ngôn ngữ dễ hiểu.
- Thu thập thuật ngữ, hành động, sự kiện, trạng thái và quy tắc từ chuyên gia.
- Xây dựng Ubiquitous Language có định nghĩa rõ trong từng bounded context.
- Phát hiện từ đồng nghĩa, từ đồng âm khác nghĩa và thuật ngữ mơ hồ.
- Phân biệt domain, subdomain và bounded context.
- Chia domain thành các subdomain theo năng lực và vấn đề kinh doanh.
- Phân loại subdomain thành Core, Supporting và Generic dựa trên chiến lược.
- Đưa ra lý do đầu tư, tự phát triển, mua giải pháp hoặc tích hợp dịch vụ bên ngoài.
- Kết nối kết quả khám phá với context map, backlog và domain model.

Đầu ra không phải một danh sách thuật ngữ hoặc sơ đồ đẹp. Đầu ra cần giúp nhóm đưa ra quyết định thiết kế và phát triển có căn cứ.

## 2. Bắt đầu từ domain và mục tiêu kinh doanh

**Domain** là lĩnh vực vấn đề và hoạt động kinh doanh mà tổ chức đang tham gia. Domain có thể rộng, gồm nhiều năng lực và quy trình khác nhau.

Ví dụ, domain thương mại điện tử có thể bao gồm:

- Thu hút và hỗ trợ người mua.
- Quản lý danh mục sản phẩm.
- Tìm kiếm và khám phá sản phẩm.
- Định giá và khuyến mại.
- Đặt hàng và quản lý đơn.
- Quản lý tồn kho.
- Thanh toán và hoàn tiền.
- Đóng gói, vận chuyển và giao nhận.
- Chăm sóc khách hàng và xử lý khiếu nại.
- Báo cáo và đối soát.

Nếu nhóm chỉ bắt đầu bằng câu hỏi “cần tạo những bảng nào?”, họ dễ bỏ qua mục tiêu và quy tắc của các hoạt động trên. Hãy bắt đầu bằng những câu hỏi:

1. Tổ chức phục vụ ai?
2. Khách hàng cần đạt kết quả gì?
3. Tổ chức tạo ra giá trị bằng những hoạt động nào?
4. Điều gì khiến khách hàng chọn tổ chức thay vì đối thủ?
5. Năng lực nào phải được kiểm soát chặt vì ảnh hưởng trực tiếp đến doanh thu, rủi ro hoặc uy tín?
6. Những phần nào chỉ là điều kiện cần để vận hành?

### 2.1. Phân biệt mục tiêu với giải pháp

“Xây một ứng dụng bán hàng” là mô tả giải pháp. “Giúp khách hàng tìm đúng sản phẩm, mua với mức giá phù hợp và nhận hàng đúng hẹn” mô tả kết quả nghiệp vụ rõ hơn.

Mục tiêu giúp nhóm không nhầm lẫn giữa domain và hệ thống hiện tại. Một tổ chức có thể đổi website, ERP hoặc payment provider nhưng domain và mục tiêu kinh doanh vẫn tồn tại.

### 2.2. Xác định phạm vi thực hành

Không cần khám phá toàn bộ doanh nghiệp trong một buổi. Chọn một domain đủ cụ thể để có thể trao đổi sâu, ví dụ nền tảng bán lẻ trực tuyến, ngân hàng số, quản lý logistics hoặc đặt lịch khám. Ghi rõ phạm vi, nhóm khách hàng, sản phẩm và khu vực địa lý đang xét.

## 3. Phân biệt Domain, Subdomain và Bounded Context

Ba khái niệm này thường bị dùng thay thế nhau, nhưng chúng trả lời các câu hỏi khác nhau:

| Khái niệm | Thuộc góc nhìn | Câu hỏi chính | Ví dụ thương mại điện tử |
| --- | --- | --- | --- |
| Domain | Problem space | Tổ chức đang giải quyết lĩnh vực vấn đề nào? | Thương mại điện tử |
| Subdomain | Problem space | Domain lớn gồm những phần bài toán/năng lực nào? | Định giá, quản lý đơn, tồn kho |
| Bounded Context | Solution/model space | Mô hình và ngôn ngữ nào có ranh giới nhất quán? | Sales, Inventory, Billing |

### 3.1. Domain là bức tranh lớn

Domain bao gồm các mục tiêu, quy trình, quy tắc, con người và năng lực mà tổ chức cần để hoạt động. Domain không nhất thiết tương ứng với một phần mềm hoặc một database.

### 3.2. Subdomain chia nhỏ bài toán

Subdomain là một phần của domain có mục tiêu và quy tắc riêng. Ví dụ, quản lý tồn kho tập trung vào biết hàng đang ở đâu, lượng nào khả dụng và reservation nào còn hiệu lực. Định giá tập trung vào cách xác định giá và ưu đãi cho một giao dịch.

Subdomain giúp nhóm ưu tiên đầu tư và chọn chiến lược xây dựng giải pháp.

### 3.3. Bounded Context chia ranh giới mô hình

Bounded Context xác định nơi một model và Ubiquitous Language có ý nghĩa nhất quán. Nó thường được thiết kế để hỗ trợ một hoặc một số subdomain, nhưng quan hệ không bắt buộc là một-một.

Ví dụ:

- Subdomain Fulfillment có thể được triển khai qua Inventory Context và Shipping Context.
- Một Sales Context có thể chứa các năng lực liên quan đến đặt hàng và chính sách bán hàng nếu chúng chia sẻ một mô hình phù hợp.
- Một hệ thống cũ có thể có nhiều bounded context cùng xử lý một subdomain vì lịch sử tổ chức hoặc các mô hình khác nhau.

Điều quan trọng là không suy ra bounded context chỉ từ tên subdomain hoặc bảng dữ liệu. Cần xem xét ngôn ngữ, invariant, ownership và cách thay đổi mô hình.

### 3.4. Quan hệ thường gặp nhưng không phải quy luật cứng

Subdomain mô tả phần bài toán cần giải quyết; bounded context mô tả ranh giới mô hình dùng để giải quyết. Trong trường hợp đơn giản, một subdomain có thể được hỗ trợ bởi một bounded context. Khi quy trình hoặc ownership phức tạp hơn, một subdomain có thể cần nhiều context, hoặc một context có thể hỗ trợ nhiều năng lực gần nhau.

## 4. Khám phá domain cùng chuyên gia

Ubiquitous Language không thể được tạo ra chỉ bằng cách đặt tên class. Nhóm cần khám phá cách chuyên gia suy nghĩ và ra quyết định trong công việc.

Những người có thể tham gia:

- Domain expert: người hiểu quy tắc và ngoại lệ.
- Nhân viên vận hành: người thực hiện quy trình hằng ngày.
- Product owner/business owner: người xác định mục tiêu và ưu tiên.
- Developer/analyst: người chuyển hiểu biết thành mô hình và kiểm tra tính khả thi.
- Người hỗ trợ, bán hàng, tài chính hoặc đối tác: người nhìn thấy các trường hợp mà nhóm phát triển có thể bỏ sót.

### 4.1. Phỏng vấn theo tình huống

Thay vì hỏi “quy trình đặt hàng gồm những bước nào?”, hãy yêu cầu chuyên gia kể lại một đơn hàng cụ thể:

- Khách đã chọn sản phẩm nào?
- Giá được xác định ở thời điểm nào?
- Khi nào đơn được coi là đã đặt?
- Điều kiện nào khiến đơn được xác nhận?
- Hàng được giữ ở đâu và trong bao lâu?
- Khi thanh toán bị từ chối thì chuyện gì xảy ra?
- Ai được phép hủy đơn?
- Nếu khách đổi địa chỉ sau khi đóng gói thì xử lý ra sao?

Tình huống thực tế làm lộ ra từ ngữ, sự kiện, trạng thái và quy tắc chính xác hơn mô tả quy trình chung.

### 4.2. Hỏi “vì sao?” và “trường hợp nào không?”

Khi chuyên gia nói “đơn phải được kiểm tra trước khi xác nhận”, hãy hỏi:

- Kiểm tra những điều kiện nào?
- Ai hoặc hệ thống nào kiểm tra?
- Có trường hợp được bỏ qua bước không?
- Kết quả kiểm tra có hết hạn không?
- Nếu dữ liệu thay đổi sau kiểm tra thì sao?
- Có thể kiểm tra lại không?

Các câu hỏi này giúp phát hiện những khái niệm như OrderValidation, Reservation, PaymentAuthorization hoặc ApprovalPolicy.

### 4.3. Ghi nguyên văn từ chuyên gia trước khi chuẩn hóa

Đừng vội thay thuật ngữ của chuyên gia bằng từ kỹ thuật. Ghi lại từ đang được sử dụng, ví dụ “giữ hàng”, “chốt đơn”, “đối soát”, “hủy mềm”. Sau đó mới hỏi ý nghĩa và thống nhất cách dùng trong context.

Nếu nhóm tự đổi “giữ hàng” thành “trừ tồn” mà hai hành động có semantics khác nhau, mô hình sẽ sai ngay từ ngôn ngữ.

## 5. Thu thập danh từ, động từ, sự kiện và trạng thái

Một cách khám phá có cấu trúc là phân loại từ ngữ xuất hiện trong cuộc trao đổi.

| Loại | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Danh từ/khái niệm | Ai hoặc cái gì có ý nghĩa? | Buyer, Order, Product, Reservation |
| Động từ/hành vi | Người hoặc hệ thống làm gì? | Place, Confirm, Reserve, Capture |
| Sự kiện | Điều gì đã xảy ra? | OrderPlaced, StockReserved |
| Trạng thái | Đối tượng đang ở tình trạng nào? | Draft, Confirmed, AwaitingPayment |
| Quy tắc | Điều gì phải đúng? | Không xác nhận đơn rỗng |
| Chính sách | Quy tắc nào quyết định kết quả? | Miễn phí giao hàng theo phân khúc |
| Vai trò | Ai chịu trách nhiệm hoặc được phép làm gì? | Buyer, Approver, WarehouseOperator |

### 5.1. Động từ thường tiết lộ domain behavior

“Đặt hàng”, “xác nhận đơn”, “ủy quyền thanh toán”, “thu tiền”, “giữ hàng” và “bàn giao vận chuyển” là các hành vi khác nhau. Nếu code chỉ có updateStatus(), ý nghĩa của hành động có thể bị che khuất.

### 5.2. Event cần diễn đạt fact đã xảy ra

ReserveStock là command yêu cầu giữ hàng. StockReserved là event ghi nhận hàng đã được giữ. Không dùng hai tên này thay thế nhau. Phân biệt command và event giúp nhóm nói chính xác về yêu cầu và kết quả.

### 5.3. Trạng thái cần có semantics

PAID có thể được hiểu là đã authorization hoặc đã capture. Nếu chuyên gia phân biệt hai bước, model cũng cần phân biệt. Một enum chung không nên gom những fact khác nhau chỉ vì giao diện muốn hiển thị một nhãn ngắn.

## 6. Xây dựng Ubiquitous Language

**Ubiquitous Language** là hệ thuật ngữ được chuyên gia và developer cùng sử dụng trong thảo luận, tài liệu, thiết kế, code và test của một bounded context.

Ngôn ngữ chung không phải một từ điển do analyst viết xong rồi gửi cho developer. Nó hình thành qua trao đổi, ví dụ, mô hình hóa và kiểm chứng liên tục.

Một thuật ngữ tốt cần:

- Có định nghĩa rõ trong context.
- Có ví dụ và trường hợp biên.
- Phân biệt với các thuật ngữ gần nghĩa.
- Được sử dụng nhất quán trong code và trao đổi.
- Có owner hoặc người duy trì khi semantics thay đổi.

### 6.1. Ví dụ glossary cho Sales Context

| Thuật ngữ | Định nghĩa | Không đồng nghĩa với |
| --- | --- | --- |
| Buyer | Chủ thể thực hiện giao dịch mua trong Sales | Payer hoặc UserAccount |
| Cart | Tập lựa chọn chưa trở thành đơn đã đặt | Order |
| Order | Cam kết mua bán được Sales ghi nhận | Shipment |
| Place Order | Ghi nhận yêu cầu mua thành Order | Confirm Order |
| Confirm Order | Chấp nhận đơn sau khi thỏa điều kiện Sales | Payment Authorized |
| Order Total | Tổng tiền được xác định theo chính sách giá của đơn | Số tiền đã capture |
| Cancel Order | Kết thúc đơn theo chính sách hủy | Refund Payment |

Định nghĩa cần được xác nhận với chuyên gia. Bảng chỉ là ví dụ để minh họa cách ghi glossary.

### 6.2. Từ đồng nghĩa

Nếu các nhóm dùng “đơn”, “đơn mua”, “order” để chỉ cùng một khái niệm, cần chọn thuật ngữ chuẩn trong context. Các từ còn lại có thể được ghi như alias hoặc từ nên tránh.

Việc chuẩn hóa giúp code không có các class PurchaseOrder, SalesOrder và Order cùng biểu diễn một khái niệm mà không có khác biệt semantics.

### 6.3. Từ đồng âm khác nghĩa

Một từ có thể mang nghĩa khác trong các context:

| Từ | Sales | Billing | Shipping |
| --- | --- | --- | --- |
| Customer | Người mua trong giao dịch | Bên chịu trách nhiệm thanh toán | Người nhận hàng có thể được tham chiếu |
| Order | Cam kết mua bán | Tham chiếu giao dịch cần thu tiền | Yêu cầu giao hàng được tạo từ đơn |
| Completed | Quy trình bán hàng hoàn tất theo định nghĩa Sales | Nghĩa vụ thanh toán đã hoàn tất | Giao hàng đã hoàn tất |

Không ép các context dùng một định nghĩa toàn cục nếu thực tế khác nhau. Có thể dùng cùng một từ trong giao tiếp đời thường, nhưng trong model và contract phải nêu rõ context và semantics.

### 6.4. Từ mơ hồ cần được làm rõ

Các từ như “xử lý”, “hoàn tất”, “hợp lệ”, “đã thanh toán”, “khả dụng” hoặc “đã duyệt” thường quá rộng. Hãy hỏi chính xác điều gì đã xảy ra, ai xác nhận và điều kiện nào được đáp ứng.

## 7. Đưa ngôn ngữ chung vào code và test

Ngôn ngữ chung chỉ có giá trị khi được dùng trong mô hình và các hành vi thực tế.

Ví dụ, tên method:

~~~java
order.place();
order.confirm();
order.cancel(reason);
~~~

diễn đạt rõ hơn:

~~~java
order.updateStatus("DONE");
order.setFlag(true);
~~~

Tên event:

~~~java
OrderPlaced
OrderConfirmed
OrderCancelled
~~~

Tên test:

~~~java
shouldNotConfirmAnOrderWithoutLines
shouldRejectCancellationAfterShipmentHandoff
~~~

Tên tốt giúp người đọc hiểu hành vi mà không cần đọc implementation trước.

### 7.1. Tránh đưa chi tiết kỹ thuật vào tên miền

Tên như OrderJpaEntity, OrderKafkaMessage hoặc OrderDto có thể phù hợp ở adapter/infrastructure. Trong domain model, ưu tiên tên khái niệm nghiệp vụ như Order, Reservation hoặc PaymentAuthorization. Không để công nghệ lưu trữ định nghĩa ngôn ngữ của domain.

### 7.2. Không phải mọi thuật ngữ đều cần class

Glossary có thể chứa vai trò, quy trình, trạng thái hoặc khái niệm không cần class riêng. Chỉ tạo type khi nó có identity, value semantics, hành vi, quy tắc hoặc lợi ích rõ trong mô hình.

## 8. Phân rã Domain thành Subdomain

Sau khi hiểu bức tranh domain, nhóm xác định các phần bài toán có mục tiêu riêng. Có thể bắt đầu từ business capability hoặc hoạt động tạo giá trị rồi kiểm tra xem chúng có quy tắc và chuyên môn riêng không.

Với thương mại điện tử, một bản phân rã ban đầu có thể gồm:

- Product Discovery: giúp người mua tìm và đánh giá sản phẩm.
- Merchandising: tổ chức cách sản phẩm được trưng bày.
- Pricing and Promotion: xác định giá và ưu đãi cho một giao dịch.
- Order Management: ghi nhận và quản lý cam kết mua bán.
- Inventory Management: quản lý tồn và giữ hàng.
- Payment Management: ủy quyền, thu tiền, hoàn tiền.
- Fulfillment and Delivery: chuẩn bị và giao hàng.
- Customer Support: xử lý câu hỏi và khiếu nại.
- Reporting and Reconciliation: tổng hợp và đối soát.

### 8.1. Subdomain nên phản ánh năng lực và quy tắc

Một nhóm bảng như orders, order_lines, order_status_history chưa đủ để chứng minh đó là subdomain. Hãy mô tả năng lực: tổ chức tiếp nhận cam kết mua, xác định trạng thái thương mại, kiểm tra điều kiện xác nhận và xử lý hủy.

### 8.2. Chia theo mục tiêu, không chia theo màn hình

Một màn hình có thể hiển thị dữ liệu từ nhiều subdomain. Ngược lại, một subdomain có thể hỗ trợ nhiều màn hình và quy trình. UI navigation không phải tiêu chí chính để phân rã domain.

### 8.3. Chia quá nhỏ cũng là vấn đề

Nếu mỗi bước của một quy trình đều bị đặt tên thành một subdomain riêng, nhóm có thể tạo ra quá nhiều ranh giới không có ownership hoặc mục tiêu riêng. Chỉ tách khi có khác biệt đáng kể về năng lực, quy tắc, chuyên môn hoặc lý do thay đổi.

## 9. Phân loại Core, Supporting và Generic Subdomain

Sau khi có danh sách subdomain, nhóm đánh giá vai trò chiến lược của từng phần.

### 9.1. Core Subdomain

Core Subdomain là phần tạo ra lợi thế cạnh tranh hoặc giá trị khác biệt quan trọng của tổ chức. Đây thường là nơi tổ chức cần đầu tư chuyên gia, mô hình hóa sâu và năng lực phát triển riêng.

Ví dụ trong một nền tảng bán lẻ cạnh tranh bằng khả năng cá nhân hóa và tối ưu chuyển đổi:

- Recommendation và Product Discovery có thể là Core.
- Dynamic Pricing hoặc Promotion Optimization có thể là Core.
- Năng lực dự báo nhu cầu độc đáo có thể là Core.

Core không được xác định bằng số lượng code hoặc độ khó kỹ thuật. Một thuật toán phức tạp nhưng không tạo khác biệt chiến lược chưa chắc là Core.

### 9.2. Supporting Subdomain

Supporting Subdomain cần thiết để tổ chức vận hành hoặc hỗ trợ Core Domain, nhưng bản thân nó không tạo ra lợi thế cạnh tranh chính.

Ví dụ:

- Quy trình xử lý đơn theo chính sách riêng của doanh nghiệp.
- Quản lý danh mục sản phẩm nội bộ.
- Điều phối chăm sóc khách hàng.
- Quy trình onboarding nhà cung cấp.

Supporting có thể cần phát triển riêng vì quy trình đặc thù, nhưng thường không cần đầu tư mô hình sâu như Core. Có thể đơn giản hóa, dùng nền tảng sẵn có hoặc thích ứng giải pháp có sẵn.

### 9.3. Generic Subdomain

Generic Subdomain là năng lực phổ biến, không tạo khác biệt đáng kể và thường có giải pháp tiêu chuẩn trên thị trường.

Ví dụ có thể gồm:

- Xác thực danh tính phổ biến.
- Gửi email/SMS thông báo cơ bản.
- Lưu trữ file.
- Thanh toán qua cổng tiêu chuẩn.
- Quản lý quyền truy cập phổ biến.

Các ví dụ này phụ thuộc chiến lược tổ chức. Với một công ty thanh toán, Payment Processing có thể là Core. Với một nhà bán lẻ dùng cổng thanh toán bên ngoài, tích hợp thanh toán có thể là Generic.

### 9.4. Bảng so sánh

| Tiêu chí | Core | Supporting | Generic |
| --- | --- | --- | --- |
| Giá trị chiến lược | Tạo khác biệt quan trọng | Hỗ trợ năng lực chính | Hàng hóa/dịch vụ phổ biến |
| Cần đầu tư domain expertise | Cao | Vừa phải theo nhu cầu | Thường thấp hơn |
| Cách triển khai | Ưu tiên năng lực riêng và mô hình sâu | Tùy biến vừa đủ | Mua, thuê hoặc tích hợp giải pháp có sẵn |
| Rủi ro khi làm kém | Mất lợi thế cạnh tranh | Giảm hiệu quả vận hành | Tăng chi phí hoặc giảm chất lượng dịch vụ |
| Ví dụ minh họa | Recommendation độc đáo | Quy trình onboarding đặc thù | Email delivery tiêu chuẩn |

## 10. Cách đánh giá subdomain có thực sự là Core?

Không nên phân loại chỉ dựa trên cảm giác “phần này quan trọng”. Hãy đánh giá theo một số câu hỏi:

1. Khách hàng có chọn chúng ta vì năng lực này không?
2. Năng lực này có khác biệt đáng kể so với đối thủ không?
3. Nó có đóng góp trực tiếp vào doanh thu, biên lợi nhuận, giữ chân khách hàng hoặc giảm rủi ro chiến lược không?
4. Tổ chức có bí quyết, dữ liệu hoặc quy trình riêng khó sao chép không?
5. Nếu mua một sản phẩm tiêu chuẩn, tổ chức có mất lợi thế hoặc phải thay đổi cách kinh doanh quan trọng không?
6. Có đội ngũ và chuyên gia đủ khả năng duy trì năng lực này không?
7. Mức đầu tư có tương xứng với giá trị tạo ra không?

### 10.1. Dùng ma trận đánh giá để hỗ trợ thảo luận

Có thể chấm điểm định tính hoặc thang điểm 1–5 cho các chiều:

| Chiều đánh giá | Câu hỏi |
| --- | --- |
| Differentiation | Năng lực có khác biệt với thị trường không? |
| Strategic impact | Nó ảnh hưởng đến mục tiêu dài hạn đến mức nào? |
| Customer value | Khách hàng có nhận ra và đánh giá cao không? |
| Proprietary knowledge | Tổ chức có kiến thức/dữ liệu/quy trình riêng không? |
| Market availability | Có giải pháp tiêu chuẩn phù hợp không? |
| Change frequency | Quy tắc có cần thay đổi thường xuyên để cạnh tranh không? |

Điểm số chỉ giúp so sánh và làm rõ giả định. Không nên cộng điểm máy móc rồi kết luận Core mà không có lập luận chiến lược.

### 10.2. Complexity không đồng nghĩa với Core

Một hệ thống legacy rất phức tạp có thể chỉ là Supporting hoặc Generic. Độ phức tạp có thể đến từ nợ kỹ thuật, quy trình lỗi thời hoặc tích hợp khó. Core là câu hỏi về lợi thế và chiến lược, không phải về số dòng code.

### 10.3. Phân loại có thể thay đổi theo thời gian

Khi thị trường, chiến lược hoặc mô hình kinh doanh thay đổi, subdomain có thể chuyển loại. Một năng lực từng là Generic có thể trở thành Core khi tổ chức đầu tư tạo ra khác biệt. Một năng lực từng quan trọng có thể trở thành hàng hóa phổ biến khi thị trường chuẩn hóa.

Vì vậy, cần ghi ngày đánh giá, giả định và người xác nhận, rồi xem lại khi chiến lược thay đổi.

## 11. Case study: nền tảng thương mại điện tử

Giả sử một doanh nghiệp bán lẻ trực tuyến muốn tăng tỷ lệ chuyển đổi và giữ chân khách hàng. Họ cạnh tranh bằng khả năng đề xuất đúng sản phẩm, giá/ưu đãi phù hợp và giao hàng đáng tin cậy.

### 11.1. Xác định mục tiêu

- Giúp khách tìm sản phẩm phù hợp nhanh hơn.
- Tăng tỷ lệ mua hàng và giá trị đơn.
- Giữ trải nghiệm giá minh bạch.
- Giảm đơn bị hủy do thiếu hàng.
- Giao hàng đúng cam kết.
- Giải quyết khiếu nại và hoàn tiền rõ ràng.

### 11.2. Phân rã thành subdomain

| Subdomain | Mục tiêu | Quy tắc/chuyên môn chính |
| --- | --- | --- |
| Product Discovery | Giúp khách tìm sản phẩm phù hợp | Search relevance, ranking, personalization |
| Merchandising | Tổ chức danh mục và trưng bày | Campaign, placement, assortment |
| Pricing & Promotion | Xác định giá và ưu đãi | Price rules, eligibility, stacking |
| Order Management | Quản lý cam kết mua bán | Place, confirm, amend, cancel |
| Inventory Management | Quản lý lượng hàng khả dụng | Reservation, allocation, release |
| Payment Management | Quản lý nghĩa vụ thanh toán | Authorize, capture, void, refund |
| Fulfillment & Delivery | Chuẩn bị và giao hàng | Pick, pack, handoff, delivery |
| Customer Support | Hỗ trợ và giải quyết vấn đề | Case, complaint, return coordination |
| Reporting & Reconciliation | Theo dõi và đối soát | Revenue, settlement, operational metrics |

### 11.3. Phân loại chiến lược

Giả định doanh nghiệp cạnh tranh chủ yếu bằng cá nhân hóa, tối ưu khuyến mại và trải nghiệm khám phá sản phẩm:

| Subdomain | Phân loại giả định | Lý do |
| --- | --- | --- |
| Product Discovery | Core | Năng lực đề xuất và xếp hạng tạo khác biệt |
| Pricing & Promotion | Core | Chính sách giá linh hoạt hỗ trợ chuyển đổi và biên lợi nhuận |
| Merchandising | Supporting | Cần thiết cho vận hành danh mục và chiến dịch |
| Order Management | Supporting | Cần thiết để thực hiện giao dịch nhưng có thể theo quy trình phổ biến |
| Inventory Management | Supporting | Quan trọng để tránh oversell; chưa phải lợi thế chính trong giả định này |
| Payment Management | Generic | Dùng provider tiêu chuẩn, tích hợp qua contract |
| Fulfillment & Delivery | Supporting | Có quy trình riêng nhưng có thể dựa vào đối tác logistics |
| Customer Support | Supporting | Hỗ trợ trải nghiệm và giữ chân khách |
| Reporting & Reconciliation | Supporting/Generic | Phụ thuộc mức độ khác biệt của analytics và quy định tài chính |

Phân loại này không phải kết luận chung cho mọi doanh nghiệp thương mại điện tử. Nếu doanh nghiệp sở hữu mạng lưới logistics vượt trội, Fulfillment có thể là Core. Nếu doanh nghiệp cung cấp dịch vụ thanh toán, Payment Management có thể là Core. Nhóm phải dựa trên chiến lược thật.

## 12. Từ Subdomain đến Bounded Context

Sau khi phân loại subdomain, nhóm xác định ranh giới model phù hợp. Bounded Context không phải cách đặt tên khác cho subdomain; nó là quyết định thiết kế về nơi một model có hiệu lực.

Một mapping minh họa:

| Subdomain | Bounded Context đề xuất | Ghi chú |
| --- | --- | --- |
| Product Discovery | Discovery Context | Có model ranking và recommendation riêng |
| Merchandising | Catalog/Merchandising Context | Có thể tách Catalog nếu ownership khác |
| Pricing & Promotion | Pricing Context | Sở hữu price quote và promotion eligibility |
| Order Management | Sales Context | Sở hữu Order aggregate và trạng thái thương mại |
| Inventory Management | Inventory Context | Sở hữu Stock và Reservation |
| Payment Management | Billing Context | Sở hữu payment lifecycle |
| Fulfillment & Delivery | Shipping Context | Sở hữu Shipment và Delivery |
| Customer Support | Support Context | Tham chiếu các ID và snapshot từ context khác |
| Reporting & Reconciliation | Reporting Context hoặc data platform | Tiêu thụ event/projection từ các owner |

### 12.1. Một subdomain có thể cần nhiều context

Fulfillment & Delivery có thể được chia thành Inventory Context và Shipping Context vì quản lý tồn kho và điều phối giao nhận có invariant, dữ liệu và nhịp thay đổi khác nhau.

### 12.2. Một context có thể hỗ trợ nhiều capability gần nhau

Sales Context có thể sở hữu cả đặt hàng và một số quy tắc thương mại gắn chặt với Order. Nếu Pricing có mô hình và chính sách thay đổi độc lập, tách Pricing Context có thể hợp lý hơn.

### 12.3. Bounded Context cần được xác nhận bằng ranh giới mô hình

Hãy kiểm tra:

- Thuật ngữ trong context có nhất quán không?
- Aggregate có bảo vệ invariant rõ không?
- Context có owner và lifecycle dữ liệu riêng không?
- Thay đổi nội bộ có thể diễn ra mà ít ảnh hưởng context khác không?
- Contract giữa context có đủ nhỏ và rõ không?
- Có nhiều định nghĩa khác nhau đang bị ép dùng chung không?

## 13. Xây dựng Context Map từ các quan hệ thực tế

Sau khi xác định các context, nhóm mô tả cách chúng hợp tác. Context Map không chỉ là sơ đồ hộp nối bằng mũi tên; nó ghi nhận quan hệ, hướng phụ thuộc và cách bảo vệ model.

~~~mermaid
flowchart LR
    DISC[Discovery Context] -->|Product information contract| CAT[Catalog Context]
    SALES[Sales Context] -->|ReserveStock command| INV[Inventory Context]
    SALES -->|AuthorizePayment command| BILL[Billing Context]
    INV -->|StockReserved / Rejected| SALES
    BILL -->|PaymentAuthorized / Declined| SALES
    SALES -->|OrderPlaced event| SHIP[Shipping Context]
    INV -->|Reservation result| SHIP
    BILL -->|Payment status event| REPORT[Reporting Context]
    SALES -->|Order events| REPORT
    SHIP -->|Shipment events| REPORT
    SUPPORT[Support Context] -->|Query contracts / projections| SALES
    SUPPORT -->|Query contracts / projections| SHIP
~~~

Đây là sơ đồ minh họa. Trong triển khai thực tế, cần xác định chính xác ai phát command, ai phát event, event nào là fact và luồng nào được điều phối bằng Process Manager.

### 13.1. Upstream và downstream

Upstream là context cung cấp mô hình hoặc thông tin cho context khác. Downstream là context tiêu thụ thông tin đó. Quan hệ này giúp xác định bên nào chịu trách nhiệm công bố contract và bên nào cần bảo vệ model nội bộ.

### 13.2. Anti-Corruption Layer

Nếu consumer phải tiếp nhận mô hình bên ngoài có semantics khác, ACL chuyển đổi dữ liệu sang ngôn ngữ nội bộ. Ví dụ, Billing nhận OrderPlaced từ Sales nhưng chỉ lưu InvoiceRequest với các trường cần cho hóa đơn, không dùng Sales Order aggregate làm model của mình.

### 13.3. Published Language

Published Language là ngôn ngữ/contract được công bố để context khác tích hợp, ví dụ event schema hoặc API contract. Nó có thể dựa trên Ubiquitous Language của producer nhưng cần được thiết kế cho giao tiếp ổn định, có version và semantics rõ.

## 14. Kết nối Subdomain với chiến lược phát triển phần mềm

Phân loại subdomain giúp quyết định nên đầu tư loại năng lực nào:

| Loại subdomain | Hướng đầu tư thường gặp | Câu hỏi kiến trúc |
| --- | --- | --- |
| Core | Đầu tư domain expert, modeler, kỹ sư; mô hình hóa sâu và kiểm thử kỹ | Làm thế nào tạo và bảo vệ khác biệt? |
| Supporting | Xây vừa đủ theo quy trình riêng; cân nhắc cấu hình hoặc giải pháp sẵn có | Phần nào thực sự cần tùy biến? |
| Generic | Mua, thuê, dùng dịch vụ hoặc package chuẩn | Tích hợp và quản lý rủi ro phụ thuộc ra sao? |

### 14.1. Core không có nghĩa phải tự xây mọi thứ

Một subdomain Core có thể sử dụng thư viện, cloud service hoặc hạ tầng tiêu chuẩn. Điều cần sở hữu là logic và năng lực tạo khác biệt. Ví dụ, doanh nghiệp có thể dùng database và message broker phổ biến nhưng tự phát triển thuật toán ranking.

### 14.2. Generic không có nghĩa là không quan trọng

Xác thực hoặc thanh toán có thể không tạo khác biệt nhưng lỗi ở đó vẫn gây hậu quả lớn. Generic thường cần độ tin cậy, bảo mật và kiểm soát tích hợp tốt; chỉ là tổ chức không nhất thiết tự phát minh lại năng lực phổ biến.

### 14.3. Supporting không có nghĩa làm qua loa

Supporting có thể chứa quy trình rất đặc thù. Nhóm cần đầu tư đủ để đáp ứng vận hành và bảo vệ rủi ro, nhưng không nên tiêu tốn nguồn lực Core vào việc xây một nền tảng tùy biến quá mức cho năng lực không tạo lợi thế.

## 15. Quy trình workshop xây dựng Ubiquitous Language

Một workshop ban đầu có thể kéo dài từ 90 phút đến nửa ngày tùy phạm vi. Cần mời ít nhất một domain expert có kinh nghiệm thực tế, một người điều phối và các developer/analyst sẽ xây model.

### Chuẩn bị

- Chọn một quy trình hoặc capability cụ thể.
- Chuẩn bị ví dụ thực tế và các tình huống lỗi.
- Mời đúng người có quyền giải thích quy tắc.
- Chuẩn bị bảng/board để ghi thuật ngữ, event, command, state và câu hỏi.
- Thống nhất rằng glossary ban đầu là giả thuyết cần xác nhận.

### Phần 1: Kể lại quy trình

Để chuyên gia mô tả một trường hợp thành công và một trường hợp thất bại. Người điều phối ghi các sự kiện đã xảy ra, hành động và trạng thái.

### Phần 2: Thu thập thuật ngữ

Ghi lại danh từ, động từ, vai trò, trạng thái và quy tắc. Chưa vội tranh luận tên class.

### Phần 3: Làm rõ nghĩa

Với từng thuật ngữ, hỏi định nghĩa, ví dụ, điều kiện và từ dễ nhầm. Đánh dấu thuật ngữ chưa thống nhất.

### Phần 4: Chuẩn hóa ngôn ngữ

Chọn thuật ngữ chuẩn trong phạm vi context. Ghi alias và thuật ngữ không nên dùng.

### Phần 5: Kiểm tra bằng tình huống

Đưa các case biên để xem định nghĩa có đủ rõ không. Nếu hai người hiểu khác nhau, cần bổ sung semantics hoặc chia khái niệm.

### Phần 6: Chuyển vào model và test

Chọn một vài hành vi có giá trị để mô hình hóa. Viết test thể hiện quy tắc đã thống nhất và liên kết đến glossary.

### Đầu ra workshop

- Glossary theo context.
- Danh sách câu hỏi còn mở.
- Ví dụ và quy tắc được xác nhận.
- Các domain event/command quan trọng.
- Danh sách khái niệm cần model hóa.
- Người chịu trách nhiệm cập nhật.

## 16. Quy trình workshop phân loại Subdomain

Workshop này tập trung vào bài toán và chiến lược, không bắt đầu từ class hoặc database.

### Bước 1: Ghi mục tiêu kinh doanh

Viết các kết quả tổ chức cần đạt, chẳng hạn tăng chuyển đổi, giảm thời gian giao hàng hoặc giảm rủi ro gian lận.

### Bước 2: Liệt kê business capability

Nhóm liệt kê các năng lực cần có để đạt mục tiêu. Có thể dùng value stream hoặc quy trình end-to-end để tránh bỏ sót capability hỗ trợ.

### Bước 3: Gom thành subdomain

Nhóm các capability có mục tiêu, quy tắc và chuyên môn liên quan. Đặt tên theo ngôn ngữ nghiệp vụ.

### Bước 4: Xác định sự khác biệt chiến lược

Với mỗi subdomain, hỏi nó có tạo lợi thế, có bí quyết riêng, có tác động đến khách hàng và có giải pháp tiêu chuẩn phù hợp không.

### Bước 5: Phân loại Core/Supporting/Generic

Ghi loại, lý do, giả định và độ tin cậy. Nếu chưa đủ thông tin, đánh dấu “chưa xác định” thay vì ép phân loại.

### Bước 6: Xác định hướng đầu tư

Quyết định phần nào cần đội chuyên môn và mô hình sâu; phần nào dùng giải pháp tiêu chuẩn; phần nào cần quy trình riêng nhưng giữ đơn giản.

### Bước 7: Xác định owner và bounded context sơ bộ

Chỉ định nhóm chịu trách nhiệm và đề xuất ranh giới model. Kiểm tra lại bằng ngôn ngữ, invariant, data ownership và quan hệ tích hợp.

### Bước 8: Review theo chiến lược

Domain owner/product leadership xác nhận rằng phân loại phản ánh chiến lược thật, không phải sở thích kỹ thuật.

## 17. Bộ tài liệu đầu ra tích hợp

Sau hai workshop, nhóm nên có một bộ tài liệu ngắn, liên kết với nhau:

| Artifact | Nội dung | Owner gợi ý |
| --- | --- | --- |
| Domain overview | Mục tiêu, khách hàng, phạm vi | Product/domain owner |
| Subdomain map | Các phần bài toán và quan hệ | Domain analyst + experts |
| Subdomain classification | Core/Supporting/Generic và lý do | Business/domain leadership |
| Context map | Bounded Context và quan hệ tích hợp | Architecture/domain teams |
| Ubiquitous Language glossary | Thuật ngữ và định nghĩa theo context | Owning team + domain expert |
| Open questions | Giả định chưa được xác nhận | Người điều phối/owner |
| Decision log/ADR | Quyết định và trade-off | Người có quyền quyết định |
| Example/test catalog | Tình huống minh họa và quy tắc | Developer + domain expert |

### 17.1. Liên kết thay vì sao chép

Glossary, context map và ADR có thể nằm ở những tài liệu khác nhau, nhưng nên liên kết đến nhau. Tránh copy cùng một định nghĩa vào nhiều nơi rồi để chúng lệch nhau.

### 17.2. Tài liệu phải phản ánh model hiện tại

Khi một thuật ngữ hoặc ranh giới thay đổi, cần cập nhật code, test, glossary và contract liên quan. Tài liệu không nên chỉ là kết quả workshop cũ.

## 18. Ví dụ chuyển từ ngôn ngữ mơ hồ sang ngôn ngữ chính xác

Các câu dưới đây thường xuất hiện trong trao đổi nhưng chưa đủ chính xác:

| Câu mơ hồ | Câu hỏi cần làm rõ | Cách diễn đạt có thể chính xác hơn |
| --- | --- | --- |
| Đơn đã thanh toán | Đã authorization hay capture? | PaymentAuthorized hoặc PaymentCaptured |
| Hàng đã trừ | Đã reserve, pick hay ship? | StockReserved, ItemsPicked hoặc ShipmentDispatched |
| Đơn đã xong | Sales hoàn tất, thanh toán hoàn tất hay giao hàng hoàn tất? | OrderConfirmed, PaymentCaptured, DeliveryCompleted |
| Khách hợp lệ | Hợp lệ để đăng nhập, mua chịu hay nhận khuyến mại? | AccountVerified, EligibleForCredit, PromotionEligible |
| Đơn bị hủy | Hủy trước hay sau khi thu tiền/giao hàng? | OrderCancelled, PaymentRefundRequested, ReturnInitiated |
| Giá cuối cùng | Giá niêm yết, giá sau khuyến mại hay số tiền đã thu? | ListPrice, QuotedPrice, OrderTotal, CapturedAmount |

Không nhất thiết dùng tên tiếng Anh trong mọi tổ chức. Điều quan trọng là thuật ngữ được chọn có nghĩa rõ và được dùng nhất quán trong context. Tên code có thể dùng tiếng Anh theo convention dự án, nhưng glossary nên giải thích chính xác bằng ngôn ngữ mà domain expert hiểu.

## 19. Kiểm chứng ngôn ngữ và phân loại bằng tình huống

Một glossary chỉ có định nghĩa chưa chắc đủ. Hãy kiểm tra bằng ví dụ:

### Tình huống A: Thanh toán được authorization nhưng chưa capture

Hỏi:

- Sales có coi đơn đã thanh toán không?
- Billing đang ở trạng thái nào?
- Shipping có được tạo shipment không?
- Khi đơn bị hủy, cần void hay refund?

Nếu các nhóm trả lời khác nhau, cần làm rõ semantics và contract.

### Tình huống B: Hàng đã được reserve nhưng khách hủy đơn

Hỏi:

- Ai phát lệnh release reservation?
- Reservation có thể hết hạn tự động không?
- Inventory ghi nhận event nào?
- Sales đổi trạng thái Order khi nào?

Tình huống giúp kiểm tra ranh giới giữa Order và Reservation.

### Tình huống C: Doanh nghiệp thay đổi chiến lược

Nếu tổ chức chuyển từ bán lẻ thông thường sang cạnh tranh bằng giao hàng siêu nhanh, Inventory allocation hoặc Delivery optimization có thể trở thành Core. Nhóm cần xem lại classification thay vì giữ nhãn cũ theo thói quen.

## 20. Đánh giá chất lượng Ubiquitous Language

Ngôn ngữ chung có chất lượng khi:

- Domain expert và developer hiểu cùng một nghĩa khi dùng thuật ngữ.
- Một thuật ngữ có định nghĩa và ví dụ trong đúng context.
- Các từ gần nghĩa được phân biệt.
- Tên hành vi thể hiện ý định nghiệp vụ.
- Event diễn đạt fact đã xảy ra.
- State có ý nghĩa và transition rõ.
- Code, test, API và tài liệu không mâu thuẫn.
- Thuật ngữ có thể được thay đổi khi hiểu biết mới xuất hiện.

Có thể dùng một số câu hỏi kiểm tra:

1. Khi đọc tên method, domain expert có hiểu hành động không?
2. Khi đọc event, consumer có biết fact nào đã xảy ra không?
3. Có field/status nào mà hai team diễn giải khác nhau không?
4. Có từ nào được dùng cho nhiều khái niệm không?
5. Một người mới có thể tìm định nghĩa và owner ở đâu?

## 21. Đánh giá chất lượng Subdomain Classification

Phân loại subdomain có chất lượng khi:

- Các subdomain mô tả bài toán/năng lực có ý nghĩa.
- Mỗi subdomain có mục tiêu và phạm vi tương đối rõ.
- Core được chứng minh bằng lợi thế chiến lược, không chỉ độ khó kỹ thuật.
- Supporting và Generic không bị xem nhẹ về độ tin cậy/rủi ro.
- Lý do phân loại được ghi lại.
- Có owner và hướng đầu tư.
- Các giả định chưa chắc chắn được đánh dấu.
- Có thời điểm review khi chiến lược thay đổi.

Nếu tất cả subdomain đều được đánh dấu Core, nhóm chưa thực sự ưu tiên. Nếu Generic được chọn chỉ vì có vendor, cần xem giải pháp có đáp ứng quy định, tích hợp và rủi ro không.

## 22. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Dùng một glossary toàn cục cho mọi context | Ép các khái niệm khác nghĩa thành một định nghĩa | Duy trì Ubiquitous Language theo bounded context |
| Để developer tự đặt tên mà không xác nhận với chuyên gia | Code dùng thuật ngữ không đúng nghiệp vụ | Workshop và kiểm chứng bằng ví dụ |
| Chỉ thu thập danh từ | Bỏ sót hành vi, event và quy tắc | Ghi cả động từ, trạng thái, event và policy |
| Dùng command và event thay thế nhau | Không phân biệt yêu cầu với fact đã xảy ra | Dùng tên command ở dạng ý định, event ở dạng fact |
| Coi Domain, Subdomain và Bounded Context là một | Chia sai ranh giới problem/solution space | Xác định riêng domain, phần bài toán và ranh giới model |
| Chia subdomain theo màn hình hoặc bảng | Phân rã theo UI/storage thay vì năng lực | Bắt đầu từ business capability và quy tắc |
| Phân loại Core theo độ phức tạp code | Đầu tư sai chỗ | Đánh giá lợi thế, giá trị khách hàng và chiến lược |
| Gọi mọi thứ quan trọng là Core | Không còn khả năng ưu tiên | So sánh differentiation và market availability |
| Coi Generic là không quan trọng | Bỏ qua security, reliability và compliance | Dùng giải pháp chuẩn nhưng quản lý rủi ro nghiêm túc |
| Ép quan hệ subdomain–context là một-một | Bỏ qua ownership và mô hình thực tế | Xác nhận bằng language, invariant và integration |
| Không ghi giả định và độ tin cậy | Phân loại tạm thời bị xem là sự thật | Ghi lý do, owner và ngày review |
| Tạo glossary rồi không cập nhật | Code và tài liệu dần lệch nhau | Gắn cập nhật language với thay đổi model/contract |
| Dùng tên trạng thái chung như DONE/PAID | Consumer hiểu sai fact nghiệp vụ | Đặt tên theo semantics cụ thể |

## 23. Quy trình thực hành tổng hợp

Một nhóm có thể thực hiện theo trình tự sau để đi từ domain overview đến ngôn ngữ chung và phân loại subdomain.

### Bước 1: Chọn domain và mục tiêu

Viết ngắn gọn tổ chức phục vụ ai, tạo giá trị gì và phạm vi nào đang được xem xét.

### Bước 2: Mời domain expert và người vận hành

Chọn người hiểu cả quy tắc thường ngày lẫn ngoại lệ. Xác định người điều phối và người ghi nhận kết quả.

### Bước 3: Kể lại một số quy trình thực tế

Chọn trường hợp thành công, thất bại và ngoại lệ. Ghi event, command, state, actor và decision.

### Bước 4: Thu thập và làm rõ thuật ngữ

Ghi danh từ, động từ, trạng thái, policy và rule. Tìm synonyms, homonyms và từ mơ hồ.

### Bước 5: Tạo glossary theo context sơ bộ

Định nghĩa thuật ngữ, ví dụ, từ dễ nhầm và owner. Đánh dấu các điểm chưa thống nhất.

### Bước 6: Liệt kê business capabilities

Xác định các năng lực cần thiết để tạo giá trị cho khách hàng và vận hành tổ chức.

### Bước 7: Gom thành subdomain

Nhóm capability có mục tiêu và chuyên môn liên quan. Kiểm tra ranh giới bằng quy tắc và quy trình thực tế.

### Bước 8: Phân loại Core/Supporting/Generic

Đánh giá lợi thế cạnh tranh, giá trị khách hàng, bí quyết riêng, market availability và mức đầu tư.

### Bước 9: Xác định bounded context và owner

Đề xuất model boundary, nhóm chịu trách nhiệm, public contract và các context liên quan.

### Bước 10: Vẽ Context Map

Ghi upstream/downstream, Published Language, ACL và quan hệ điều phối/choreography nếu cần.

### Bước 11: Kiểm chứng bằng tình huống và test

Dùng ví dụ thực tế để kiểm tra glossary, policy, state transition và event semantics. Chuyển các quy tắc quan trọng thành test.

### Bước 12: Ghi quyết định và kế hoạch đầu tư

Lưu lý do phân loại, giả định, owner, hướng build/buy/integrate và thời điểm review.

### Bước 13: Duy trì và xem xét lại

Khi chiến lược, thị trường hoặc quy trình thay đổi, cập nhật subdomain map, glossary, context map và model.

## 24. Nguyên tắc thực hành

Khi xây dựng ngôn ngữ chung và phân loại các miền con, nhóm nên nhớ:

- **Bắt đầu từ mục tiêu kinh doanh.** Domain được hiểu qua vấn đề và giá trị tổ chức tạo ra.
- **Khám phá bằng tình huống thật.** Ngoại lệ và quyết định làm lộ ra quy tắc ẩn.
- **Duy trì Ubiquitous Language theo context.** Không ép một từ có cùng nghĩa ở mọi nơi.
- **Ghi cả danh từ, động từ, event và state.** Mô hình cần diễn đạt hành vi chứ không chỉ dữ liệu.
- **Phân biệt command với event.** Một bên yêu cầu hành động, bên kia ghi nhận fact.
- **Phân biệt domain, subdomain và bounded context.** Problem space và model boundary là hai góc nhìn khác nhau.
- **Phân rã theo năng lực và quy tắc.** Không chia chỉ theo màn hình, bảng hoặc team.
- **Phân loại Core theo lợi thế chiến lược.** Complexity kỹ thuật không đủ để kết luận.
- **Đầu tư phù hợp cho Supporting và Generic.** Không cần tự xây mọi thứ nhưng vẫn phải quản lý rủi ro.
- **Không ép mapping một-một.** Xác định context dựa trên language, invariant, ownership và cách thay đổi.
- **Ghi lý do và giả định.** Phân loại cần có căn cứ và thời điểm xem xét lại.
- **Đưa ngôn ngữ vào code, test và contract.** Glossary không thể thay thế mô hình thực thi.
- **Liên kết artifact.** Subdomain map, context map, glossary, ADR và test phải hỗ trợ lẫn nhau.
- **Cập nhật khi hiểu biết thay đổi.** DDD là quá trình học hỏi liên tục.

Ubiquitous Language giúp các thành viên nói cùng một nghĩa trong từng bounded context; subdomain classification giúp tổ chức biết phần năng lực nào tạo khác biệt và cần đầu tư sâu. Khi nhóm khám phá cả hai cùng domain expert, phân biệt rõ problem space với model boundary và kiểm chứng bằng ví dụ thực tế, kết quả không chỉ là tài liệu. Nó trở thành cơ sở để thiết kế context, phân quyền ownership, chọn giải pháp build/buy và tập trung nguồn lực vào những năng lực có giá trị chiến lược.

## 25. Câu hỏi tự kiểm tra

1. Ubiquitous Language là gì và vì sao nó cần được duy trì trong một bounded context?
2. Phân biệt Domain, Subdomain và Bounded Context bằng một ví dụ bạn biết.
3. Vì sao một từ như Customer hoặc Order có thể có nghĩa khác giữa các context?
4. Những kỹ thuật nào giúp khám phá thuật ngữ, hành vi, event và invariant từ domain expert?
5. Phân biệt command, event và state bằng ví dụ đặt hàng.
6. Core, Supporting và Generic Subdomain khác nhau ở vai trò chiến lược nào?
7. Vì sao độ phức tạp kỹ thuật không đủ để kết luận một subdomain là Core?
8. Một subdomain có thể được triển khai qua nhiều bounded context trong trường hợp nào?
9. Làm thế nào để xác định một subdomain có thể dùng giải pháp tiêu chuẩn thay vì tự phát triển?
10. Published Language và Anti-Corruption Layer hỗ trợ quan hệ giữa các context ra sao?
11. Những artifact nào nên được tạo sau workshop ngôn ngữ chung và phân loại subdomain?
12. Làm thế nào để kiểm chứng glossary bằng tình huống và test?
13. Khi chiến lược kinh doanh thay đổi, việc phân loại subdomain cần được xem xét lại như thế nào?
14. Hãy chọn một domain thực tế, xây glossary cho ít nhất một context, phân rã domain thành subdomain, phân loại Core/Supporting/Generic và đề xuất bounded context cùng context map.
