# Mô hình dữ liệu riêng cho từng ngữ cảnh thay vì một mô hình dùng cho mọi hệ thống

## Mục tiêu học tập

Một doanh nghiệp có thể cùng sử dụng những từ như **khách hàng**, **sản phẩm**, **đơn hàng**, **giá**, **tồn kho** và **trạng thái** ở nhiều bộ phận. Tuy nhiên, các từ đó không nhất thiết có cùng nghĩa, cùng vòng đời hay cùng quy tắc ràng buộc trong mọi quy trình. Mô hình dữ liệu cố gắng phục vụ mọi hệ thống bằng **một thực thể, một bộ thuộc tính và một tập trạng thái chung** thường trở nên khó hiểu, nhiều cột tùy chọn, xung đột quy tắc và khó thay đổi độc lập.

Một hướng tiếp cận là **thiết kế mô hình dữ liệu riêng cho từng ngữ cảnh nghiệp vụ** (*bounded context*), rồi làm rõ cách các ngữ cảnh **trao đổi sự kiện, yêu cầu và định danh** qua các hợp đồng tích hợp. Mục tiêu không phải tạo càng nhiều database càng tốt, mà là giữ **nghĩa và quyền sở hữu dữ liệu rõ ràng**, đồng thời phối hợp đủ tin cậy khi một quy trình kinh doanh trải qua nhiều ngữ cảnh.

Bài thuộc chương **Ranh giới và tích hợp** của module **DATABASE_DATA_MODELING**. Theo mục tiêu module, người học luyện chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng từ thực thể, quan hệ, ràng buộc đến chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời so sánh mô hình quan hệ, document, đồ thị và phân tích để chọn cấu trúc dễ tiến hóa, dễ kiểm chứng. Bài này nhấn mạnh **ranh giới ngữ nghĩa và quyền sở hữu dữ liệu** khi tích hợp hệ thống.

Sau bài học, bạn có thể:

1. Giải thích **bounded context**, **ngôn ngữ chung trong ngữ cảnh** (*ubiquitous language*) và sự khác biệt với ranh giới bảng, package, service hoặc database vật lý.
2. Nhận ra các dấu hiệu của **mô hình toàn cục quá tham vọng**: một thực thể chung có nhiều nghĩa, một enum trạng thái cho mọi quy trình, bảng dùng chung với nhiều nhóm ghi.
3. Xây dựng mô hình riêng cho **Danh mục sản phẩm, Bán hàng, Tồn kho, Thanh toán và Giao vận**, dù các ngữ cảnh có thể tham chiếu cùng mã nghiệp vụ bên ngoài.
4. Phân biệt **khóa nội bộ**, **định danh tham chiếu liên ngữ cảnh** và **ràng buộc tồn tại trong cùng database**.
5. Thiết kế các hợp đồng tích hợp **API đồng bộ**, **sự kiện bất đồng bộ** và **lớp chống nhiễm mô hình** (*anti-corruption layer, ACL*) mà không làm lộ bảng nội bộ.
6. Xác định ranh giới giao dịch, invariant cục bộ, **eventual consistency**, **transactional outbox**, **inbox/idempotency**, sự kiện đến trễ và cơ chế bù trong quy trình nhiều ngữ cảnh.
7. Phân biệt **mô hình tác nghiệp theo từng ngữ cảnh** với **read model/tầng phân tích tích hợp** được xây dựng để phục vụ truy vấn xuyên nhiều nguồn.
8. Lập checklist và kiểm thử để đánh giá khi nào nên tách mô hình, khi nào cần chia sẻ hợp đồng và khi nào **không nên** phân chia hệ thống.

> **Giới hạn:** Các ví dụ dùng SQL PostgreSQL và Java hiện đại ở mức minh họa. Chúng giúp thấy cấu trúc, khóa, hợp đồng và nguy cơ tích hợp; chúng **không** phải một nền tảng microservice hoàn chỉnh hoặc bằng chứng đã có hệ thống message broker, giao dịch phân tán, cơ chế retry và giám sát vận hành.

## 1. Vì sao một mô hình dữ liệu toàn cục thường thất bại?

### 1.1. Cùng tên không đồng nghĩa cùng thực thể nghiệp vụ

Hãy xét một cửa hàng trực tuyến với các bộ phận sau:

| Ngữ cảnh | Từ dùng quen thuộc | Nghĩa trong ngữ cảnh ấy |
| --- | --- | --- |
| **Danh mục (Catalog)** | Sản phẩm | Định nghĩa thứ được bày bán: mô tả, SKU, phân loại, trạng thái hiển thị |
| **Bán hàng (Sales)** | Sản phẩm trong đơn | Ảnh chụp mặt hàng, giá chấp nhận, thuế/chiết khấu và số lượng **tại lúc chốt mua** |
| **Tồn kho (Inventory)** | Hàng tồn | Đơn vị hàng có thể cấp phát, vị trí kho, tồn khả dụng và phần đã giữ chỗ |
| **Thanh toán (Billing/Payments)** | Đơn, số tiền | Nghĩa vụ thu, chứng từ thanh toán, giao dịch thu tiền và hoàn tiền |
| **Giao vận (Fulfillment)** | Đơn giao | Những kiện hàng/lô hàng phải đóng gói, theo dõi, giao và xác nhận |
| **Tài khoản (Identity/Accounts)** | Người dùng | Danh tính đăng nhập, phương thức xác thực, quyền truy cập |

Một **sản phẩm** trong Catalog có thể đổi tên từ “Sổ tay A5” sang “Sổ tay bìa cứng A5”. Đơn đã mua tháng trước vẫn cần hiển thị **tên và giá tại thời điểm giao dịch**, không nhất thiết phải đổi theo danh mục hiện hành. Một sản phẩm đã ngừng bán có thể vẫn có tồn kho để xử lý hoàn trả. Một đơn hàng đã được thanh toán có thể chưa giao xong; trạng thái thanh toán và trạng thái giao vận là **hai khái niệm khác nhau**.

Nếu ép mọi thứ vào:

~~~~text
UNIVERSAL_PRODUCT(id, name, price, quantity, reserved, published,
                  warehouse, paid, shipped, status, ...)

UNIVERSAL_ORDER(id, customer_id, payment_status, picking_status,
                shipment_status, accounting_status, ...)
~~~~

ta sẽ gặp những câu hỏi khó trả lời: ai được sửa giá, price là giá niêm yết hay giá đơn đã chấp nhận, quantity là tồn toàn hệ thống hay số lượng một dòng đơn, status phải ưu tiên tiến trình nào? **Nhiều cột không tạo ra một định nghĩa thống nhất** nếu các khái niệm ban đầu khác nhau.

### 1.2. Mô hình toàn cục tạo ra kiểu ghép nối nào?

| Dấu hiệu | Hậu quả thiết kế |
| --- | --- |
| Nhiều hệ thống cùng INSERT/UPDATE một bảng | Khó xác định ai sở hữu quy tắc bất biến và chịu trách nhiệm khi dữ liệu sai |
| Một trạng thái enum phải thêm giá trị cho mọi quy trình | Mọi dịch vụ phải triển khai lại khi một bộ phận có trạng thái mới |
| Các cột chỉ áp dụng cho một số hệ thống | Nhiều NULL có nghĩa khác nhau, kiểm tra hợp lệ phức tạp |
| Một khóa ngoại từ hệ thống này trỏ sâu vào bảng nội bộ hệ thống khác | Thay đổi cấu trúc nội bộ gây tác động dây chuyền |
| Muốn đổi schema phải xin xác nhận nhiều nhóm | Tốc độ phát hành bị phụ thuộc vào một lược đồ lớn |
| Các báo cáo tự JOIN bảng tác nghiệp của mọi nhóm | Ngữ nghĩa khác nhau dễ bị gộp nhầm, khó đảm bảo thời gian và quyền dữ liệu |
| Một thư viện “domain chung” chứa mọi entity | Các nhóm bị buộc nâng cấp cùng một phiên bản khái niệm dù nhu cầu khác nhau |

Các vấn đề trên **không chứng minh mọi bảng chung đều xấu**. Một bảng dữ liệu tham chiếu ít thay đổi do một bên quản trị, như mã tiền tệ hoặc danh mục quốc gia đã được thống nhất, vẫn có thể dùng chung hợp lý. Vấn đề nằm ở việc **nhiều ngữ cảnh độc lập cùng gán nghĩa và quyền sửa** cho một mô hình không có chủ sở hữu rõ ràng.

### 1.3. Ví dụ “khách hàng” có nhiều cách nhìn

Trong Identity, một user có thể là tài khoản đăng nhập, email xác minh và quyền. Trong Sales, **buyer** là người đặt hàng; tên liên hệ và địa chỉ giao hàng có thể là dữ liệu ghi nhận cho đơn cụ thể. Trong Billing, **bill-to party** là bên có nghĩa vụ thanh toán, có thể là doanh nghiệp khác với người nhận hàng. Trong chăm sóc khách hàng, **contact** có thể là một người đại diện được ủy quyền.

Không nên mặc định tất cả đều là một bảng CUSTOMER toàn cục với một ID và mọi cột bắt buộc. Có thể có **quan hệ ánh xạ danh tính**, nhưng “cùng một người” cũng chưa chắc “cùng vai trò nghiệp vụ” hay “được phép dùng cùng dữ liệu cá nhân”.

## 2. Bounded context: ranh giới của nghĩa và quy tắc

### 2.1. Định nghĩa

**Bounded context** là một phạm vi nơi **mô hình, thuật ngữ và các quy tắc nghiệp vụ có nghĩa rõ ràng, nhất quán**. Trong ngữ cảnh ấy, các tên như Order, Customer, Stock, Paid hoặc Available có định nghĩa được nhóm phụ trách thống nhất.

Từ “Order” có thể là:

- **SalesOrder** trong Sales: cam kết mua hàng, giá đã được chấp nhận và trạng thái đặt/chốt.
- **FulfillmentRequest** trong Giao vận: yêu cầu chuẩn bị và giao những dòng hàng cụ thể.
- **Invoice** trong Billing: chứng từ hoặc nghĩa vụ thu tiền với quy định kế toán.

Các thực thể này có thể liên quan qua **order_id**, nhưng **không cần cùng thuộc tính, cùng khóa chính hay cùng vòng đời**.

**Một bounded context không mặc định bằng một microservice**, một schema SQL hay một nhóm nhân sự. Một monolith có thể có nhiều module ngữ cảnh được ngăn cách tốt; một ngữ cảnh lớn có thể cần nhiều tiến trình triển khai. Điều cần kiểm tra là **ngôn ngữ, invariant, quyền sở hữu và hợp đồng**.

### 2.2. Ngôn ngữ chung trong từng ngữ cảnh

Một nhóm Sales có thể định nghĩa:

> Đơn **được xác nhận** khi giá và điều kiện mua đã chốt, đồng thời các bước cần thiết theo chính sách của Sales đã thành công.

Nhóm Billing có thể định nghĩa:

> Khoản thu **đã quyết toán** khi cổng thanh toán hoặc sổ kế toán xác nhận giao dịch theo quy tắc của Billing.

Nhóm Fulfillment có thể định nghĩa:

> Kiện hàng **đã giao** khi có xác nhận giao nhận hợp lệ.

Ba khái niệm “được xác nhận”, “đã quyết toán”, “đã giao” không nên bị rút gọn thành một giá trị chung **status = DONE**. Khi cần hiển thị “đơn hàng hoàn tất”, một tầng tổng hợp phải **định nghĩa chính xác** điều kiện kết hợp các trạng thái, thay vì ép từng ngữ cảnh ghi chung cột status.

### 2.3. Dấu hiệu tìm ranh giới

Một số câu hỏi thực hành:

1. **Ai quyết định** bản ghi hợp lệ? Catalog hay Sales quyết định giá phải trả cho một đơn đã đặt?
2. **Điều gì thay đổi cùng nhau?** Khóa tồn và giữ chỗ kho cần được cập nhật nguyên tử; mô tả marketing không cần nằm trong cùng giao dịch.
3. **Khi nào một từ đổi nghĩa?** “Available” trong Catalog có thể nghĩa là được phép hiển thị; trong Inventory là số lượng có thể cấp phát.
4. **Có vòng đời riêng không?** Đơn Sales đã chốt nhưng Shipment vẫn đang vận chuyển.
5. **Có yêu cầu quyền truy cập khác không?** Bí mật xác thực ở Identity không nên nằm trong bản sao buyer của Sales.
6. **Có thể thay đổi độc lập không?** Nhóm kho sửa thuật toán giữ hàng mà không phải di trú tất cả bảng Sales.

Không nên đặt ranh giới chỉ vì “mỗi danh từ một microservice”. Ranh giới cần phản ánh **quy tắc và cách phối hợp thật**, không chỉ sơ đồ tổ chức.

### 2.4. Sơ đồ ngữ cảnh ví dụ

~~~~mermaid
flowchart LR
    C["Catalog\nĐịnh nghĩa sản phẩm"] -->|"Product quote / published data"| S["Sales\nĐơn và giá chốt"]
    S -->|"OrderSubmitted"| I["Inventory\nGiữ hàng và khả dụng"]
    I -->|"InventoryReserved / Rejected"| S
    S -->|"OrderConfirmed"| B["Billing\nNghĩa vụ thu"]
    S -->|"OrderConfirmed"| F["Fulfillment\nYêu cầu giao"]
    B -->|"PaymentSettled"| S
    F -->|"ShipmentDelivered"| S
    S -.->|"Sự kiện cho báo cáo"| R["Reporting / Read model"]
    B -.->|"Sự kiện cho báo cáo"| R
    F -.->|"Sự kiện cho báo cáo"| R
~~~~

Mũi tên biểu diễn **ý định trao đổi thông tin**, không phải khẳng định một quy trình cụ thể đã được triển khai hay OrderConfirmed phải luôn có đúng thứ tự như hình. Thứ tự reservation, thu tiền, xác nhận và giao hàng phải được **chốt theo chính sách nghiệp vụ** của từng hệ thống.

## 3. Mô hình dữ liệu riêng cho năm ngữ cảnh

### 3.1. Catalog: sự thật về mặt hàng được chào bán

Một mô hình Catalog có thể gồm:

~~~~text
CATALOG_PRODUCT(
  product_id,
  sku,
  display_name,
  category_id,
  publication_status,
  current_list_price,
  currency_code,
  catalog_version
)
~~~~

Catalog sở hữu các quy tắc như SKU duy nhất theo thị trường, tên hiển thị, ngành hàng và sản phẩm nào có thể xuất hiện trong danh mục. **current_list_price** là giá niêm yết hiện hành, không mặc nhiên là giá cuối cùng mà khách đã chấp nhận ở một giao dịch cũ.

### 3.2. Sales: sự thật về đơn đã đặt

Một mô hình Sales có thể gồm:

~~~~text
SALES_ORDER(
  order_id,
  buyer_ref,
  order_status,
  submitted_at,
  order_currency
)

SALES_ORDER_LINE(
  order_line_id,
  order_id,
  catalog_product_ref,
  product_name_snapshot,
  quantity,
  accepted_unit_price,
  discount_snapshot,
  line_currency
)
~~~~

**catalog_product_ref** là mã tham chiếu tới khái niệm sản phẩm trong Catalog. Nhưng tên, giá và chiết khấu đã chốt thuộc **dữ liệu đơn hàng của Sales**; khi Catalog thay tên hoặc thay giá niêm yết, dòng đơn đã chấp nhận không nhất thiết bị viết lại.

Sales cần bảo đảm mỗi order_line thuộc một order cục bộ, giá trị số lượng hợp lệ, tổng tiền theo chính sách và trạng thái chuyển đổi được phép. Những invariant đó khác với việc Catalog có cho sản phẩm xuất hiện trên trang tìm kiếm hay không.

### 3.3. Inventory: sự thật về số lượng và giữ chỗ

Một mô hình Inventory có thể gồm:

~~~~text
STOCK(
  warehouse_id,
  stock_product_ref,
  on_hand_qty,
  reserved_qty
)

STOCK_RESERVATION(
  reservation_id,
  external_order_line_ref,
  warehouse_id,
  stock_product_ref,
  reserved_qty,
  reservation_status,
  expires_at
)
~~~~

Với phạm vi đơn vị đo và chính sách tồn đã thống nhất:

\[
\text{available}=\text{on\_hand\_qty}-\text{reserved\_qty}.
\]

Inventory sở hữu invariant **không giữ chỗ vượt khả năng cấp phát** theo quy tắc của kho. Sales không nên tự UPDATE reserved_qty bằng cách truy cập bảng Inventory; Sales gửi **yêu cầu giữ hàng** và nhận kết quả thành công/thất bại.

### 3.4. Billing: sự thật về chứng từ và tiền

Một mô hình Billing có thể gồm:

~~~~text
INVOICE(
  invoice_id,
  external_order_ref,
  bill_to_party_id,
  invoice_amount,
  currency_code,
  invoice_status,
  issued_at
)

PAYMENT(
  payment_id,
  invoice_id,
  gateway_transaction_ref,
  settled_amount,
  settled_at,
  payment_status
)
~~~~

Một đơn có thể có **nhiều lần thanh toán**, hoàn tiền hoặc chia chứng từ theo nghiệp vụ. Không giả định quan hệ Order–Invoice luôn 1:1 nếu chưa xác minh. Billing định nghĩa khi nào là **đã thu tiền**, theo loại sự kiện cổng thanh toán hoặc sổ kế toán có thẩm quyền; Sales chỉ sử dụng kết quả phù hợp với quy trình đặt hàng.

### 3.5. Fulfillment: sự thật về kiện hàng và giao nhận

Một mô hình Fulfillment có thể gồm:

~~~~text
SHIPMENT(
  shipment_id,
  external_order_ref,
  shipping_address_snapshot,
  shipment_status,
  dispatched_at,
  delivered_at
)

SHIPMENT_LINE(
  shipment_line_id,
  shipment_id,
  external_order_line_ref,
  packed_qty
)
~~~~

Một SalesOrder có thể phát sinh nhiều Shipment do tách kho hoặc giao nhiều đợt. Ngược lại, một Shipment có thể gộp các dòng theo quy tắc vận hành. Vì vậy không nên gắn thẳng **shipment_status** và **tracking_number** vào một bảng SalesOrder rồi giả định một đơn có một kiện.

### 3.6. Tóm tắt điểm khác biệt

| Ngữ cảnh | Câu hỏi cốt lõi | Bất biến ví dụ | Dữ liệu từ ngữ cảnh khác |
| --- | --- | --- | --- |
| Catalog | Mặt hàng nào có thể được chào bán? | SKU/phiên bản danh mục hợp lệ | Chính sách giá hoặc taxonomy được đồng bộ nếu cần |
| Sales | Khách đã đồng ý mua gì, với giá nào? | Dòng đơn thuộc đúng đơn; giá chốt không đổi tùy tiện | product_ref, quote, buyer_ref |
| Inventory | Còn đủ hàng để cấp phát không? | Số giữ chỗ không vượt khả dụng theo quy tắc kho | product_ref, order_line_ref |
| Billing | Đã lập và thu khoản nào? | Không ghi nhận một giao dịch cổng hai lần | order_ref và khoản phải thu theo hợp đồng |
| Fulfillment | Hàng nào cần đóng/giao? | Kiện giao có dòng và số lượng hợp lệ | order_ref, line_ref, địa chỉ giao chốt |

**Các khóa tham chiếu chung liên kết đối tượng ở mức nghiệp vụ; chúng không biến các mô hình con thành một thực thể SQL toàn cục.**

## 4. Quyền sở hữu dữ liệu và ranh giới giao dịch

### 4.1. Ai là nguồn sự thật?

Một nguyên tắc thiết kế thường hữu ích:

> **Mỗi trạng thái nghiệp vụ quan trọng cần có một bên chịu trách nhiệm quyết định và bảo vệ invariant của nó.** Bên khác có thể dùng hoặc lưu bản sao có nguồn gốc rõ ràng, nhưng không tự ý sửa trạng thái được sở hữu.

Ví dụ:

- Catalog là nguồn tin cậy cho **tên và giá niêm yết hiện tại**.
- Sales là nguồn tin cậy cho **giá mà đơn đã chấp nhận**.
- Inventory là nguồn tin cậy cho **khả năng cấp phát và phần hàng đã giữ chỗ**.
- Billing là nguồn tin cậy cho **giao dịch thanh toán đã quyết toán**.
- Fulfillment là nguồn tin cậy cho **trạng thái giao kiện**.

Đây là các phạm vi **không mâu thuẫn**. Sales giữ bản sao tên sản phẩm tại lúc mua không phải “sao chép dữ liệu sai chuẩn hóa” nếu đây là **snapshot có ý nghĩa lịch sử riêng**. Ngược lại, Sales tự sửa tồn kho rồi coi bản sao của mình là tồn kho thật sẽ gây tranh chấp quyền sở hữu.

### 4.2. Ranh giới logic không buộc mỗi context có một database riêng

Có những phương án triển khai:

| Phương án | Ví dụ | Điểm cần kiểm soát |
| --- | --- | --- |
| **Monolith theo module** | Cùng tiến trình, package Sales và Inventory khác nhau | API module rõ ràng, không để lớp tùy ý đọc/sửa bảng của nhau |
| **Cùng DB, tách schema/role** | sales.orders và inventory.stock trong PostgreSQL | Chủ sở hữu schema, quyền GRANT, migration độc lập, tránh FK hoặc JOIN xuyên schema tùy tiện |
| **Database riêng theo context** | Sales DB và Inventory DB | Tham chiếu ID bên ngoài, hợp đồng API/event, xử lý đồng bộ cuối cùng |
| **Một context gồm nhiều ứng dụng** | API và worker cùng thao tác một mô hình Inventory | Phối hợp quyền ghi và invariant trong cùng ranh giới sở hữu |

Không nên quyết định “mỗi context một database” trước khi hiểu **ngữ nghĩa và invariant**. Tách vật lý có thể tăng độc lập triển khai, nhưng cũng tăng chi phí tích hợp, quan sát và độ nhất quán; dùng chung vật lý vẫn có thể bảo vệ ranh giới logic nếu được quản trị và kiểm soát quyền nghiêm túc.

**Chú ý:** PostgreSQL schema không tự ngăn một application role truy cập schema khác. Nếu hai module dùng cùng tài khoản toàn quyền và cùng sửa bảng của nhau, đặt tên schema khác nhau **không phải** bảo đảm quyền sở hữu.

### 4.3. Invariant cục bộ và invariant xuyên nhiều context

Một **invariant cục bộ** có thể được kiểm tra trong một giao dịch của context sở hữu, chẳng hạn:

- Trong Sales: mỗi order_line thuộc một sales_order hợp lệ; quantity > 0.
- Trong Inventory: on_hand_qty ≥ 0, reserved_qty ≥ 0 và reserved_qty ≤ on_hand_qty.
- Trong Billing: mã giao dịch từ cổng thanh toán không được ghi nhận hai lần theo đúng phạm vi định danh.

Một yêu cầu như “**không xác nhận đơn trừ khi đã giữ đủ hàng và thanh toán hợp lệ**” liên quan **nhiều context**. Không thể chỉ thêm một CHECK SQL vào bảng Sales để đảm bảo các trạng thái Inventory/Billing ở database khác luôn đồng bộ tức thời.

Ta cần định nghĩa:

1. **Ai điều phối** quy trình hoặc ai đưa ra quyết định chốt.
2. **Thông điệp/chứng nhận nào** được coi là kết quả giữ hàng và thanh toán có giá trị.
3. Trạng thái **đang chờ**, **thất bại**, **hết hạn** hoặc **hủy** của quy trình.
4. Cách xử lý **gửi trùng, đến trễ, timeout và bù giao dịch**.
5. Những gì cuối cùng nhất quán (*eventually consistent*) và những gì bắt buộc phải kiểm tra ngay trong context sở hữu.

Không cần làm toàn bộ hệ thống phân tán mới có thể mô hình hóa đúng invariant; nhưng phải biết **invariant nào không thể giao phó cho một FK hoặc một enum ở bảng toàn cục**.

## 5. Khóa cục bộ và tham chiếu liên ngữ cảnh

### 5.1. Hai loại định danh cần phân biệt

**Khóa cục bộ** định danh một hàng bên trong mô hình của context, ví dụ sales.order_line_id là PK của dòng đơn Sales.

**Định danh tham chiếu ngoài** là mã để một context nhận ra đối tượng có chủ sở hữu ở context khác, ví dụ:

~~~~text
Sales.order_line.catalog_product_ref = Catalog.product_id
Inventory.stock.stock_product_ref    = Catalog.product_id
Billing.invoice.external_order_ref   = Sales.order_id
~~~~

Ba trường tham chiếu có thể dùng cùng giá trị UUID trong wire contract, nhưng mỗi bên dùng nó cho **một mục đích khác nhau**. Nó **không** khiến SalesOrderLine, CatalogProduct và StockItem trở thành một đối tượng duy nhất.

Một UUID đúng định dạng **không chứng minh** sản phẩm vẫn đang được bán, giá đã được xác nhận, hay hàng còn trong kho. Những câu hỏi ấy phải được trả lời qua **quy tắc và hợp đồng của bên sở hữu**.

### 5.2. Không mặc định có FK xuyên context

Ở **cùng một database**, về mặt kỹ thuật có thể tạo FK giữa schema Sales và Catalog. Nhưng FK đó tạo **ghép nối vòng đời schema và dữ liệu**: Catalog khó đổi/xóa một bản ghi mà không ảnh hưởng Sales, dù Sales cần giữ lịch sử đơn đã mua và Catalog có thể ngừng bán sản phẩm.

Với **database riêng**, FK SQL thông thường không thể trực tiếp bảo vệ hàng ở database khác. Khi đó:

- Sales lưu **catalog_product_ref** và **snapshot** của dữ liệu đã chấp nhận.
- Sales kiểm tra điều kiện mua thích hợp qua **API/quote** hoặc dữ liệu Catalog đã đồng bộ theo hợp đồng.
- Sales giữ một **tham chiếu nguồn** để truy vết, không coi nó là FK nội bộ.
- Các cơ chế kiểm tra và đối soát phát hiện tham chiếu không còn giải quyết được, tùy chính sách lưu lịch sử.

Không có nghĩa “FK luôn xấu”. **FK nội bộ cùng context là công cụ mạnh** để bảo vệ quan hệ cục bộ. Đối với một modular monolith đã cố định quyền sở hữu, đôi khi FK vật lý xuyên module vẫn là đánh đổi có chủ ý. Điều quan trọng là **đánh giá chi phí thay đổi và quyền sửa**, không coi một FK có sẵn là bằng chứng hai khái niệm phải cùng bounded context.

### 5.3. Trường hợp định danh có phạm vi

Nếu SKU chỉ duy nhất **theo tenant** hoặc **theo thị trường**, một tham chiếu chỉ chứa sku sẽ mơ hồ. Hợp đồng có thể cần:

~~~~text
ProductReference(
  tenant_id,
  catalog_id,
  product_id
)
~~~~

Trường nào thực sự cần phụ thuộc vào ngữ nghĩa định danh đã chốt. Không thêm trường vô hạn; nhưng **không được làm rơi phạm vi** chỉ vì mọi mã đều có dạng String.

### 5.4. Mapping định danh khi các context có ID riêng

Có hệ thống Billing tự cấp customer_account_id, trong khi Identity cấp identity_user_id. Không nên giả định hai UUID phải giống nhau. Một quan hệ ánh xạ có thể có:

~~~~text
BILLING_ACCOUNT_LINK(
  billing_account_id,
  source_system,
  external_party_ref,
  verified_at
)
~~~~

Quy tắc **một–một, một–nhiều hay nhiều–nhiều** phải xuất phát từ nghiệp vụ: một doanh nghiệp có nhiều tài khoản đăng nhập; một người có thể đại diện nhiều công ty. Ánh xạ danh tính có thể là **thực thể nghiệp vụ cần quản trị**, không phải một JOIN ngầm theo email.

## 6. PostgreSQL: một database minh họa nhưng mô hình vẫn tách ngữ cảnh

Đoạn SQL này chỉ là **lược đồ minh họa trong một database PostgreSQL mới**, không phải yêu cầu mọi hệ thống dùng chung database. Những bảng đặt ở bốn schema để **làm lộ ranh giới sở hữu**. Phần quan trọng là: **FK cục bộ bên trong schema**, còn những tham chiếu tới context khác được diễn đạt bằng mã tham chiếu và hợp đồng tích hợp.

### 6.1. Lược đồ Catalog và Sales

~~~~sql
CREATE SCHEMA catalog;
CREATE SCHEMA sales;
CREATE SCHEMA inventory;
CREATE SCHEMA billing;

CREATE TABLE catalog.product (
    product_id UUID PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    current_list_price NUMERIC(18, 2) NOT NULL
        CHECK (current_list_price >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    publication_status VARCHAR(20) NOT NULL
        CHECK (publication_status IN ('DRAFT', 'ACTIVE', 'ARCHIVED'))
);

CREATE TABLE sales.sales_order (
    order_id UUID PRIMARY KEY,
    buyer_external_ref UUID NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL,
    order_status VARCHAR(20) NOT NULL
        CHECK (order_status IN (
            'DRAFT', 'SUBMITTED', 'CONFIRMED', 'CANCELLED'
        ))
);

CREATE TABLE sales.order_line (
    order_line_id UUID PRIMARY KEY,
    order_id UUID NOT NULL
        REFERENCES sales.sales_order(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    catalog_product_ref UUID NOT NULL,
    product_name_at_purchase VARCHAR(160) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    accepted_unit_price NUMERIC(18, 2) NOT NULL
        CHECK (accepted_unit_price >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    UNIQUE (order_id, line_no)
);
~~~~

**Những điều được bảo vệ:**

- sales.order_line.order_id là FK tới **sales.sales_order**: cả hai thuộc **Sales**.
- sale line có line_no duy nhất trong cùng đơn, quantity > 0 và accepted_unit_price không âm.
- catalog_product_ref là **tham chiếu sang Catalog**, không có FK SQL từ Sales sang catalog.product.
- product_name_at_purchase và accepted_unit_price là **dữ liệu Sales đã chốt**, không bị định nghĩa bởi giá/tên hiện tại của Catalog.

**Những điều chưa được DDL bảo vệ:** Sale có thật sự được Catalog cho phép bán ở thời điểm chốt không, quote đã hết hiệu lực chưa, người mua có được phép đặt không, số lượng được Inventory chấp nhận hay chưa. Các bất biến đó cần quy tắc và hợp đồng tương ứng.

### 6.2. Lược đồ Inventory và Billing

~~~~sql
CREATE TABLE inventory.stock (
    warehouse_code VARCHAR(40) NOT NULL,
    catalog_product_ref UUID NOT NULL,
    on_hand_qty INTEGER NOT NULL CHECK (on_hand_qty >= 0),
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty >= 0),
    PRIMARY KEY (warehouse_code, catalog_product_ref),
    CONSTRAINT ck_inventory_not_over_reserved
        CHECK (reserved_qty <= on_hand_qty)
);

CREATE TABLE inventory.stock_reservation (
    reservation_id UUID PRIMARY KEY,
    source_request_id UUID NOT NULL UNIQUE,
    warehouse_code VARCHAR(40) NOT NULL,
    catalog_product_ref UUID NOT NULL,
    external_order_line_ref UUID NOT NULL,
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty > 0),
    reservation_status VARCHAR(20) NOT NULL
        CHECK (reservation_status IN (
            'HELD', 'COMMITTED', 'RELEASED', 'EXPIRED'
        )),
    FOREIGN KEY (warehouse_code, catalog_product_ref)
        REFERENCES inventory.stock(warehouse_code, catalog_product_ref)
);

CREATE TABLE billing.invoice (
    invoice_id UUID PRIMARY KEY,
    external_order_ref UUID NOT NULL,
    invoice_amount NUMERIC(18, 2) NOT NULL
        CHECK (invoice_amount >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    invoice_status VARCHAR(20) NOT NULL
        CHECK (invoice_status IN (
            'ISSUED', 'PARTIALLY_PAID', 'PAID', 'VOID'
        ))
);

CREATE TABLE billing.payment (
    payment_id UUID PRIMARY KEY,
    invoice_id UUID NOT NULL
        REFERENCES billing.invoice(invoice_id),
    gateway_transaction_ref VARCHAR(100) NOT NULL UNIQUE,
    settled_amount NUMERIC(18, 2) NOT NULL
        CHECK (settled_amount >= 0),
    settled_at TIMESTAMPTZ,
    payment_status VARCHAR(20) NOT NULL
        CHECK (payment_status IN (
            'PENDING', 'SETTLED', 'FAILED'
        ))
);
~~~~

Ở Inventory, một STOCK có khóa **(warehouse_code, catalog_product_ref)**: một sản phẩm có tồn ở nhiều kho. external_order_line_ref tham chiếu Sales ở mức **hợp đồng tích hợp**, không tạo FK tới sales.order_line.

Ở Billing, invoice tham chiếu order ngoài bằng external_order_ref; **không đặt UNIQUE(external_order_ref)** vì bài chưa giả định một đơn chỉ có một hóa đơn. payment.invoice_id là FK **cục bộ** đến billing.invoice. gateway_transaction_ref duy nhất theo phạm vi giả định của ví dụ; hệ thống thật phải kiểm tra liệu mã gateway có duy nhất **theo nhà cung cấp/tenant** hay không.

### 6.3. Minh họa: cập nhật Catalog không được sửa ảnh chụp đơn

~~~~sql
INSERT INTO catalog.product
    (product_id, sku, display_name, current_list_price, publication_status)
VALUES
    ('00000000-0000-0000-0000-000000000101',
     'NOTE-A5', 'Sổ tay A5', 100000, 'ACTIVE');

INSERT INTO sales.sales_order
    (order_id, buyer_external_ref, submitted_at, order_status)
VALUES
    ('00000000-0000-0000-0000-000000000201',
     '00000000-0000-0000-0000-000000000301',
     TIMESTAMPTZ '2026-10-01 09:00:00+07',
     'SUBMITTED');

INSERT INTO sales.order_line
    (order_line_id, order_id, line_no, catalog_product_ref,
     product_name_at_purchase, quantity, accepted_unit_price)
VALUES
    ('00000000-0000-0000-0000-000000000202',
     '00000000-0000-0000-0000-000000000201',
     1,
     '00000000-0000-0000-0000-000000000101',
     'Sổ tay A5', 2, 90000);

-- Sau đó Catalog cập nhật thông tin mặt hàng đang bán.
UPDATE catalog.product
SET display_name = 'Sổ tay bìa cứng A5',
    current_list_price = 120000
WHERE sku = 'NOTE-A5';

SELECT
    c.display_name AS current_catalog_name,
    c.current_list_price,
    l.product_name_at_purchase,
    l.accepted_unit_price
FROM sales.order_line AS l
JOIN catalog.product AS c
    ON c.product_id = l.catalog_product_ref
WHERE l.line_no = 1;
~~~~

Kết quả minh họa:

| current_catalog_name | current_list_price | product_name_at_purchase | accepted_unit_price |
| --- | ---: | --- | ---: |
| Sổ tay bìa cứng A5 | 120000 | Sổ tay A5 | 90000 |

Câu SELECT **JOIN xuyên schema chỉ để minh họa và đối chiếu trong một database thử nghiệm**; nó không phải hợp đồng mà Sales được phép phụ thuộc khi chạy độc lập. Trong sản phẩm có database riêng, hai bên sẽ cần một API/projection hoặc quy trình đọc dữ liệu được phê duyệt.

**Đừng hiểu 90000 là tự động hợp lệ:** đây là **giá chấp nhận của đơn mẫu**, có thể do khuyến mại, báo giá hoặc chính sách riêng. Hệ thống thật phải kiểm tra điều kiện chấp nhận giá. Điều quan trọng là **Catalog.current_list_price không nên viết đè Sales.accepted_unit_price**.

### 6.4. Inventory phải thực thi invariant tại nơi sở hữu

Khi một yêu cầu giữ hàng tới Inventory, không nên để Sales đọc tồn hiện tại rồi tự giảm số lượng vì dữ liệu có thể thay đổi đồng thời.

Một cập nhật có điều kiện tại Inventory:

~~~~sql
-- Thực hiện trong giao dịch của Inventory.
-- Các giá trị ví dụ ở phần dưới minh họa một yêu cầu giữ 2 đơn vị.
INSERT INTO inventory.stock
    (warehouse_code, catalog_product_ref, on_hand_qty, reserved_qty)
VALUES
    ('WH-HN',
     '00000000-0000-0000-0000-000000000101',
     10, 0);

UPDATE inventory.stock
SET reserved_qty = reserved_qty + 2
WHERE warehouse_code = 'WH-HN'
  AND catalog_product_ref =
      '00000000-0000-0000-0000-000000000101'
  AND on_hand_qty - reserved_qty >= 2
RETURNING warehouse_code, catalog_product_ref,
          on_hand_qty, reserved_qty;
-- Nếu còn đủ hàng: một dòng trả về, reserved_qty = 2.
-- Nếu không đủ: không có dòng trả về.
~~~~

Một UPDATE có điều kiện như trên bảo vệ phần kiểm tra **khả dụng và cộng lượng giữ chỗ** tại bản ghi kho bị khóa/cập nhật trong transaction. Nhưng đây **chưa phải quy trình reservation hoàn chỉnh**:

- Phải đồng bộ việc tạo/cập nhật STOCK_RESERVATION **trong cùng giao dịch**.
- Phải có idempotency theo source_request_id để xử lý bản tin gửi lại.
- Phải xác định giới hạn số lần giữ, thời hạn, giải phóng/commit tồn và tác động khi nhập/xuất kho.
- Phải phân biệt **giữ chỗ** với **xuất kho thực tế** và tránh đếm tồn hai lần.

Đó là invariant thuộc Inventory; nó không cần một bảng UNIVERSAL_ORDER dùng chung để được bảo vệ.

## 7. Tích hợp theo hợp đồng, không theo bảng nội bộ

Hai context có thể cần trao đổi dữ liệu, nhưng không nhất thiết chia sẻ một **kiểu entity hoặc một schema SQL**. Các hợp đồng có thể là:

1. **API đồng bộ:** một bên hỏi/ra lệnh và nhận kết quả ngay, ví dụ Sales yêu cầu Catalog tính báo giá hoặc Inventory giữ chỗ.
2. **Sự kiện bất đồng bộ:** một context thông báo **điều đã xảy ra**, ví dụ OrderSubmitted hoặc PaymentSettled.
3. **Bản đọc/projection:** một context lưu dữ liệu được đồng bộ từ nơi khác chỉ để phục vụ truy vấn hoặc ra quyết định trong phạm vi đã thỏa thuận.
4. **Tệp hoặc lô trao đổi:** phù hợp với một số tích hợp đối tác hoặc quy trình báo cáo, vẫn cần contract rõ.

Chọn hình thức theo **mục đích, mức nhất quán cần có, độ trễ cho phép và khả năng xử lý lỗi**, không phải vì công nghệ đang phổ biến.

### 7.1. API đồng bộ: request/response là hợp đồng, không phải chia sẻ database

Giả sử Sales cần báo giá có hiệu lực của sản phẩm. Hợp đồng logic có thể là:

~~~~text
GET QUOTE
Input:
  buyer_ref
  product_ref
  quantity
  requested_at

Output:
  quote_id
  accepted_eligible_product_ref
  quantity
  unit_price
  currency_code
  quote_version
  valid_until
  availability_or_eligibility_status
~~~~

**Báo giá** là một **hợp đồng nghiệp vụ**, không nhất thiết là ảnh chụp trực tiếp của Catalog.current_list_price. Giá thực tế có thể phụ thuộc khách hàng, số lượng, thị trường và thời gian.

Sales dùng kết quả này theo chính sách:

- Kiểm tra quote đúng **người mua, sản phẩm, số lượng và tiền tệ**.
- Chốt accepted_unit_price khi đơn đủ điều kiện.
- Tôn trọng valid_until hoặc quy tắc khóa giá rõ ràng.
- Xử lý trường hợp API không phản hồi, trả lỗi hoặc quote thay đổi.

Nếu Sales phải đọc trực tiếp bảng Catalog rồi biết cấu trúc cột và các JOIN nội bộ để tự tính quote, ranh giới bắt đầu bị rò rỉ. Một API có chủ sở hữu giúp bên cung cấp thay đổi cách lưu dữ liệu mà vẫn giữ **hợp đồng có phiên bản**.

### 7.2. Sự kiện: sự thật đã xảy ra, không phải mệnh lệnh mơ hồ

Một **integration event** nên diễn đạt rõ sự kiện ở phạm vi ngữ cảnh sở hữu:

- **OrderSubmitted:** đơn đã được Sales ghi nhận gửi đi. Không tự có nghĩa đã thanh toán.
- **InventoryReserved:** Inventory đã giữ số lượng theo các quy tắc kho.
- **PaymentSettled:** Billing đã xác nhận khoản thanh toán theo quy tắc thu tiền.
- **ShipmentDelivered:** Fulfillment xác nhận việc giao theo quy tắc giao nhận.

Không nên gọi tất cả là **EntityUpdated** và bắt bên nhận đoán nghiệp vụ từ bản dump các cột entity. Đặc biệt, sự kiện **OrderSubmitted** không đồng nghĩa **OrderConfirmed**; hai thời điểm có thể cách nhau bởi giữ hàng và thanh toán.

Một hợp đồng sự kiện minh họa:

~~~~json
{
  "eventId": "00000000-0000-0000-0000-000000000401",
  "eventType": "sales.order-submitted",
  "schemaVersion": 1,
  "aggregateId": "00000000-0000-0000-0000-000000000201",
  "occurredAt": "2026-10-01T02:00:00Z",
  "sourceContext": "sales",
  "payload": {
    "orderId": "00000000-0000-0000-0000-000000000201",
    "lines": [
      {
        "orderLineId": "00000000-0000-0000-0000-000000000202",
        "productRef": "00000000-0000-0000-0000-000000000101",
        "quantity": 2,
        "acceptedUnitPrice": {
          "amount": "90000.00",
          "currency": "VND"
        }
      }
    ]
  }
}
~~~~

**Những điều cần thiết kế trước khi phát hành:**

- **eventId** định danh duy nhất từng thông điệp để bên nhận có thể dedup.
- **aggregateId** cho biết đối tượng sự kiện thuộc về; không bảo đảm broker phát đúng thứ tự nếu không có chính sách partition/ordering.
- **occurredAt** là thời điểm nghiệp vụ của sự kiện; thời điểm broker nhận có thể khác.
- **schemaVersion** giúp quản lý thay đổi hợp đồng.
- **amount + currency** tránh một số số tiền không rõ đơn vị; dùng chuỗi thập phân khi truyền qua JSON có thể tránh mất độ chính xác do kiểu số thực của một số consumer.
- **payload** chỉ mang dữ liệu cần thiết cho contract, không nhất thiết sao chép toàn bộ bảng nội bộ hay thông tin cá nhân nhạy cảm.

Một consumer Inventory có thể chỉ cần orderLineId, productRef, quantity và tham số kho; việc chép acceptedUnitPrice vào payload **không mặc định** cho Inventory quyền sửa giá hoặc coi giá là nguồn sự thật của mình. Nếu không cần đến giá, một hợp đồng sự kiện dành cho mục đích giữ hàng có thể lược bỏ nó.

### 7.3. Event khác command

**Command** thường diễn đạt một **yêu cầu hành động**:

~~~~text
ReserveStock(
  request_id,
  order_line_ref,
  product_ref,
  warehouse_ref,
  quantity
)
~~~~

**Event** diễn đạt một **sự thật đã được context sở hữu ghi nhận**:

~~~~text
StockReserved(
  reservation_id,
  request_id,
  order_line_ref,
  quantity,
  reserved_at
)
~~~~

Tên event ở thì quá khứ không đủ chứng minh nghiệp vụ đúng; phải có trạng thái đã được commit theo quy tắc Inventory. Không xuất event StockReserved **trước khi giao dịch giữ chỗ thành công** rồi mong bên nhận coi như tồn đã được bảo đảm.

### 7.4. Đồng bộ hay bất đồng bộ?

| Tiêu chí | API đồng bộ | Event/message bất đồng bộ |
| --- | --- | --- |
| Tương tác | Bên gọi chờ kết quả trong một yêu cầu | Bên phát không cần chờ mọi consumer xử lý |
| Phù hợp | Cần quyết định trực tiếp tại thời điểm thao tác | Phát tán sự kiện, cập nhật projection, quy trình dài |
| Phụ thuộc sẵn sàng | Bên được gọi thường phải có mặt đúng lúc | Có thể giảm phụ thuộc thời điểm nếu broker và lưu trữ được thiết kế phù hợp |
| Kiểu lỗi | Timeout, retry, circuit breaker, phản hồi thất bại | Trễ, gửi lại, đảo thứ tự, dead-letter, xử lý không thành công |
| Mức nhất quán | Có thể thấy kết quả của thao tác được gọi, nhưng không tự có giao dịch phân tán | Thường nhất quán cuối cùng giữa các context |
| Cần bảo vệ | Hạn mức, timeout, idempotent request, hợp đồng | Event ID, replay, ordering, idempotent handler, outbox/inbox |

Không có lựa chọn duy nhất cho mọi nghiệp vụ. Có thể dùng API đồng bộ để kiểm tra quote trước khi chốt, và event bất đồng bộ để báo Billing/Fulfillment sau khi Sales ghi nhận một trạng thái hợp lệ.

### 7.5. Anti-corruption layer (ACL): chuyển nghĩa khi tích hợp

**Anti-corruption layer** là một lớp dịch giữa **hợp đồng bên ngoài** và **mô hình nội bộ** nhằm tránh mô hình của nhà cung cấp hoặc context khác thâm nhập trực tiếp vào mã nghiệp vụ cục bộ.

Ví dụ bên bán hàng nhận một phản hồi từ nhà cung cấp Catalog:

~~~~json
{
  "item_code": "NOTE-A5",
  "title": "Sổ tay A5",
  "list_price_minor": 100000,
  "sellable": true
}
~~~~

Giả sử **list_price_minor** trong hợp đồng này là **số đơn vị nhỏ nhất của VND**, và chính sách giá xác nhận VND không có phần lẻ ở kênh đang xét. Sales cần chuyển nội dung đó thành **ProductQuote** của mình:

~~~~text
External catalog.item_code
    → Sales.CatalogProductRef (mapping được quản lý)

External sellable
    → Tín hiệu đầu vào cho việc được phép chào bán
      (chưa chắc đủ điều kiện chốt một đơn)

External list_price_minor
    → Giá niêm yết tham khảo theo hợp đồng đơn vị tiền
      (chưa phải accepted_unit_price)
~~~~

ACL phải xử lý **ngữ nghĩa, đơn vị, null, phiên bản, miền giá trị và lỗi**, không chỉ đổi tên trường JSON. Nếu một bên dùng “customer” cho **tài khoản thanh toán** còn bên kia dùng cho **người mua**, copy thẳng cả object không tạo ra cùng nghĩa.

### 7.6. Java: kiểu miền riêng giữa hai context

Hai context có thể tự định nghĩa kiểu ID cùng dựa trên UUID nhưng khác tên miền:

~~~~java
// Mã minh họa, mỗi phần được đặt trong package của context tương ứng.
package catalog.domain;

import java.util.UUID;

public record ProductId(UUID value) {
    public ProductId {
        java.util.Objects.requireNonNull(value);
    }
}
~~~~

~~~~java
package sales.domain;

import java.util.UUID;

public record CatalogProductRef(UUID value) {
    public CatalogProductRef {
        java.util.Objects.requireNonNull(value);
    }
}

public record OrderId(UUID value) {
    public OrderId {
        java.util.Objects.requireNonNull(value);
    }
}
~~~~

**Lưu ý Java:** Hai khai báo public record bên trong phần thứ hai là minh họa **hai tệp nguồn riêng trong cùng package**, không phải cú pháp để ghép vào một tệp .java duy nhất. Mục tiêu là cho thấy Sales dùng **CatalogProductRef**, không nhất thiết phải import toàn bộ **CatalogProduct entity**.

Thay vì cho Sales phụ thuộc trực tiếp vào một **CatalogProductJpaEntity** có những field và annotation nội bộ, đặt hợp đồng:

~~~~java
// Package sales.application.port
import java.math.BigDecimal;
import java.time.Instant;

record PriceQuote(
    CatalogProductRef productRef,
    BigDecimal unitPrice,
    String currencyCode,
    String quoteId,
    Instant validUntil
) {}

interface PricingPort {
    PriceQuote quoteFor(
        CatalogProductRef productRef,
        int quantity
    );
}
~~~~

**Sales** sở hữu PricingPort theo nhu cầu của mình; adapter tích hợp thực hiện lời gọi Catalog và mapping sang PriceQuote. Nếu Catalog đổi công nghệ lưu dữ liệu hoặc đổi field nội bộ mà hợp đồng vẫn tương thích, Sales không phải sửa toàn bộ domain.

Trong triển khai thực, phải kiểm tra **quote validity, currency, version, buyer context, điều kiện cạnh tranh về giá**, và giới hạn quyền truy cập. Dùng type an toàn giúp giảm lỗi trộn định danh nhưng không thay thế điều kiện kinh doanh tại lúc giao dịch.

## 8. Giao dịch nội bộ và nhất quán cuối cùng xuyên ngữ cảnh

### 8.1. Vì sao một giao dịch SQL không phủ toàn bộ mọi context?

Nếu Sales, Inventory và Billing sử dụng database riêng, một giao dịch BEGIN/COMMIT trong Sales **không** đồng thời commit giữ chỗ và thanh toán ở database khác.

Ví dụ:

1. Sales ghi order ở trạng thái SUBMITTED.
2. Inventory giữ hàng thành công.
3. Billing thu tiền thất bại.

Nếu chỉ cập nhật Sales sang CONFIRMED ngay bước 1, người dùng có thể nhìn thấy một đơn “đã xác nhận” nhưng chưa đủ điều kiện nghiệp vụ. Thiết kế phải có **trạng thái trung gian** và quy tắc chuyển trạng thái dựa trên sự kiện tin cậy.

Một bản đồ tiến trình minh họa:

~~~~mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> STOCK_HELD: StockReserved
    SUBMITTED --> CANCELLED: StockRejected / timeout policy
    STOCK_HELD --> CONFIRMED: PaymentSettled
    STOCK_HELD --> CANCELLING: PaymentFailed / timeout policy
    CANCELLING --> CANCELLED: StockReleased / resolution
    CONFIRMED --> [*]
    CANCELLED --> [*]
~~~~

Đây là **một chính sách giả định**. Nếu doanh nghiệp chỉ thu tiền sau giao hàng hoặc cho phép backorder, máy trạng thái khác. Quan trọng là **mỗi sự kiện và điều kiện chuyển có nghĩa rõ**, không dùng một cột status chung do nhiều service tùy ý ghi.

### 8.2. Saga và thao tác bù

Một **saga** là cách phối hợp nhiều giao dịch cục bộ thành một quy trình dài với **bước tiếp theo** và **hành động bù** phù hợp nếu xảy ra thất bại. Trong ví dụ:

~~~~text
Sales.SubmitOrder
    → Inventory.ReserveStock
    → Billing.CollectPayment
    → Sales.ConfirmOrder

Nếu Billing thất bại sau khi đã giữ hàng:
    → Inventory.ReleaseReservation
    → Sales.CancelOrder
~~~~

**Bù giao dịch không nhất thiết là rollback SQL chính xác về trạng thái cũ.** Có những hành động thực tế không hoàn tác được: một bưu kiện đã được giao, một khoản tiền đã quyết toán, một chứng từ đã phát hành. Chúng cần **sự kiện hoặc quy trình bù có ý nghĩa nghiệp vụ** (hoàn tiền, xuất chứng từ điều chỉnh, thu hồi hàng), không phải xóa dòng ở mọi database.

### 8.3. Eventual consistency không có nghĩa bất biến cục bộ được phép sai

Trong thời gian giữa các sự kiện, Sales có thể chưa biết Inventory đã hoàn tất giữ chỗ. Trạng thái projection ở Sales có thể **đến trễ** và phải thể hiện độ mới hoặc trạng thái đang chờ.

Nhưng invariant **reserved_qty ≤ on_hand_qty** phải được Inventory bảo vệ ngay tại giao dịch giữ hàng của mình. **Nhất quán cuối cùng giữa context** không phải giấy phép để **ghi tồn kho âm trong Inventory** rồi hy vọng một job sau sửa lại.

### 8.4. Truy vấn xuyên nhiều context có cần nhất quán tức thời không?

Một dashboard hiển thị:

~~~~text
Order status: Submitted
Stock status: Reserved
Payment status: Pending
Shipment status: Not created
~~~~

có thể hoàn toàn hợp lệ ở một thời điểm giữa các bước. Nếu người dùng đòi “mọi cột phải đổi cùng lúc”, cần xác định đó là:

- **Một invariant giao dịch thật sự** đòi hỏi thiết kế trong một ranh giới ghi phù hợp, hay
- **Yêu cầu hiển thị nhất quán** có thể đạt bằng một projection có trạng thái tiến trình, phiên bản và độ trễ được chấp nhận.

Đừng tự thêm distributed transaction chỉ vì nhiều nhãn giao diện cùng nằm trên một trang.

## 9. Transactional outbox và inbox: giữ hợp đồng đáng tin qua hai hệ thống

Sự kiện bất đồng bộ dẫn đến câu hỏi: **Nếu cập nhật database thành công nhưng gửi sự kiện thất bại thì sao?** Hoặc ngược lại, nếu publish thành công nhưng tiến trình lỗi trước khi đánh dấu đã gửi, sự kiện có thể xuất hiện lần nữa.

### 9.1. Bài toán ghi dữ liệu và phát thông điệp

Cách dễ sai:

~~~~text
1. COMMIT Sales.order_status = CONFIRMED.
2. Publish OrderConfirmed lên broker.

Nếu tiến trình hỏng giữa 1 và 2:
    Order đã CONFIRMED trong Sales
    nhưng Billing/Fulfillment không biết sự kiện này.
~~~~

Đảo thứ tự gửi event trước COMMIT cũng có vấn đề: bên nhận có thể xử lý một sự kiện mà trạng thái tương ứng **sau đó không được commit**. Không có bảo đảm giao dịch nguyên tử mặc định giữa PostgreSQL và một message broker độc lập.

### 9.2. Transactional outbox

**Transactional outbox** lưu một bản ghi sự kiện dự định phát **trong cùng giao dịch database** với thay đổi trạng thái nghiệp vụ. Một tiến trình phát riêng sẽ đọc outbox và giao sự kiện đến broker.

~~~~mermaid
sequenceDiagram
    participant S as Sales
    participant D as Sales DB
    participant R as Outbox Relay
    participant M as Message Broker
    participant I as Inventory Consumer
    S->>D: BEGIN
    S->>D: UPDATE SalesOrder + INSERT OutboxEvent
    S->>D: COMMIT
    R->>D: Đọc outbox chưa phát
    R->>M: Publish event
    M-->>R: Ack (theo broker)
    R->>D: Ghi trạng thái đã publish
    M->>I: Deliver event
    I->>I: Kiểm tra eventId / xử lý idempotent
~~~~

**Bảo đảm cốt lõi ở phía Sales:** Thay đổi trạng thái và bản ghi outbox commit/rollback cùng nhau. Nhưng điều đó **không tự bảo đảm giao event exactly-once xuyên mọi hệ thống**. Nếu relay gửi thành công rồi chết trước khi đánh dấu published, nó có thể phát lại sự kiện.

### 9.3. DDL PostgreSQL cho outbox của Sales

Tiếp tục lược đồ trong mục 6:

~~~~sql
CREATE TABLE sales.outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_ref UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE INDEX ix_sales_outbox_pending
    ON sales.outbox_event (occurred_at, event_id)
    WHERE published_at IS NULL;
~~~~

Ví dụ **một chuyển trạng thái đã được quy trình Sales xác nhận đủ điều kiện** đi kèm outbox trong cùng transaction:

~~~~sql
BEGIN;

WITH changed AS (
    UPDATE sales.sales_order
    SET order_status = 'CONFIRMED'
    WHERE order_id =
        '00000000-0000-0000-0000-000000000201'
      AND order_status = 'SUBMITTED'
    RETURNING order_id
)
INSERT INTO sales.outbox_event
    (event_id, aggregate_ref, event_type,
     schema_version, occurred_at, payload)
SELECT
    '00000000-0000-0000-0000-000000000402',
    order_id,
    'sales.order-confirmed',
    1,
    CURRENT_TIMESTAMP,
    jsonb_build_object('orderId', order_id::TEXT)
FROM changed;

COMMIT;
~~~~

Nếu UPDATE không thay đổi hàng nào, CTE changed rỗng và INSERT outbox **không tạo sự kiện**. Nếu INSERT outbox gây lỗi, transaction rollback cả UPDATE và INSERT. Đây là minh họa tính nguyên tử **trong Sales DB**.

**Giới hạn bắt buộc ghi rõ:** SQL này chỉ kiểm tra order_status = SUBMITTED; nó **không tự xác minh** đã nhận StockReserved và PaymentSettled. Trong triển khai thật, logic xác thực các điều kiện nghiệp vụ phải được tích hợp trước khi chuyển CONFIRMED, có cách chống ghi đua và xử lý thông điệp đến trễ. **Không gọi thử đoạn SQL này là quy trình chốt đơn hoàn chỉnh.**

### 9.4. Inbox và tính idempotent ở consumer

Một consumer có thể nhận **cùng eventId nhiều lần** vì retry hoặc broker giao lại. Nếu mỗi lần nhận đều tăng reserved_qty, tồn kho có thể bị giữ chỗ hai lần.

Một **inbox** lưu dấu thông điệp đã xử lý trong database của bên nhận:

~~~~sql
CREATE TABLE inventory.inbox_message (
    consumer_name VARCHAR(80) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~~

Luồng xử lý mẫu **trong một transaction Inventory**:

~~~~text
BEGIN;

1. Thử INSERT (consumer_name, event_id) vào inventory.inbox_message.
2. Nếu bản ghi đã tồn tại:
     kiểm tra đây là replay của thông điệp đã xử lý;
     không tăng reserved_qty một lần nữa.
3. Nếu mới:
     xác thực payload và trạng thái dự kiến;
     cập nhật tồn kho với điều kiện còn đủ;
     tạo reservation gắn request_id duy nhất;
     ghi kết quả và outbox của Inventory nếu cần.
4. COMMIT toàn bộ hoặc ROLLBACK toàn bộ nếu gặp lỗi.
~~~~

Thao tác kiểm tra eventId và cập nhật trạng thái **phải nằm trong cùng một ranh giới giao dịch hợp lệ**. Nếu ghi inbox và COMMIT trước rồi mới giữ hàng, một lỗi sau đó sẽ để lại dấu “đã xử lý” dù chưa xử lý xong. Không nên coi inbox chỉ là bảng nhật ký được ghi tùy thời điểm.

**Idempotency theo eventId** bảo vệ xử lý lặp một thông điệp. Nhưng nếu upstream gửi **hai eventId khác nhau cho cùng một yêu cầu nghiệp vụ**, consumer vẫn cần **business idempotency key** như source_request_id. Cần xác định tính duy nhất của request_id theo tenant/nguồn nếu không phải toàn cục.

### 9.5. Thứ tự, phiên bản và phát lại

Một context có thể phát:

~~~~text
OrderSubmitted(version=1)
OrderCancelled(version=2)
~~~~

Nếu consumer nhận bản hủy trước bản gửi vì đảo thứ tự, hoặc nhận lại bản gửi rất lâu sau khi hủy, nó không được vô điều kiện biến trạng thái trở lại SUBMITTED.

Những thông tin/hợp đồng có thể cần:

- **Aggregate version** hoặc một cách xác định phiên bản trạng thái.
- Quy tắc sự kiện **đến cũ, đến trùng, đến thiếu**.
- Quy định **partition/ordering** theo aggregate khi broker hỗ trợ và cần.
- Quy tắc **replay** để dựng projection mà không tạo tác dụng phụ mới.
- Cơ chế phản hồi, điều tra hoặc đối soát nếu gặp chuỗi sự kiện không hợp lệ.

Không tuyên bố “broker bảo đảm đúng thứ tự” nếu chưa xác định rõ **phạm vi thứ tự**, khóa partition và loại delivery. Các điều kiện này là phần hợp đồng và triển khai tích hợp, không thuộc về một bảng universal.

### 9.6. Outbox/inbox giải quyết được gì, không giải quyết được gì?

| Khả năng | Outbox/inbox hỗ trợ | Không tự bảo đảm |
| --- | --- | --- |
| DB update + lưu ý định phát event | Cùng transaction phía producer | Broker đã giao cho mọi consumer ngay lập tức |
| Retry relay | Có thể phát lại sau sự cố | Chỉ có đúng một lần publish |
| Consumer chống trùng eventId | Dùng PK inbox + transaction đúng | Hai eventId khác nhau có cùng nghĩa nghiệp vụ |
| Truy vết trạng thái xử lý | Event ID, aggregate ID, timestamp, log | Kết quả nghiệp vụ luôn đúng nếu handler có bug |
| Tách mô hình Sales/Inventory | Contract và tham chiếu ID | Invariant xuyên context trở thành một transaction ACID |

**Kết luận phần này:** Thiết kế theo context cần chấp nhận **giao thức tích hợp thực tế**. Tách bảng mà không thiết kế độ tin cậy của thông điệp chỉ chuyển lỗi từ “schema coupling” sang “integration failure”.

## 10. Hợp đồng phiên bản và thay đổi độc lập

Một lý do chính để tách mô hình theo context là cho phép thay đổi **nội bộ** mà không buộc mọi bên sửa cùng lúc. Điều đó chỉ thực hiện được nếu hợp đồng tích hợp cũng được quản lý có trách nhiệm.

### 10.1. Phân biệt phiên bản bảng nội bộ và phiên bản hợp đồng

Catalog có thể tách bảng PRODUCT thành PRODUCT, PRODUCT_TRANSLATION và PRICE_POLICY. Nếu API quote hoặc event PublishedProduct vẫn giữ được nội dung hợp đồng, Sales không cần biết nội bộ Catalog vừa thay đổi lược đồ.

Ngược lại, nếu Sales import trực tiếp **CatalogProductEntity** hoặc đọc các cột nội bộ, Catalog chỉ cần đổi tên một cột đã gây ảnh hưởng Sales. **Ghép nối do chia sẻ model** khiến việc tách bounded context không đạt mục tiêu.

### 10.2. Những thay đổi hợp đồng cần phân loại

| Thay đổi | Rủi ro |
| --- | --- |
| Thêm trường tùy chọn, consumer có thể bỏ qua | Thường có thể tương thích, nhưng phải kiểm tra consumer thật |
| Đổi tên hoặc xóa trường đang bắt buộc | Có thể phá consumer |
| Đổi ý nghĩa của amount từ VND sang đơn vị nhỏ nhất | **Breaking về ngữ nghĩa** dù tên/trường và kiểu số không đổi |
| Đổi OrderConfirmed từ “đã giữ hàng” thành “đã giao” | Breaking về nghiệp vụ, cần tên sự kiện và hợp đồng rõ |
| Đổi customer_id từ phạm vi toàn cục sang tenant-scoped | Có thể gây gán sai danh tính hoặc dedup sai |
| Thêm trạng thái enum mới | Consumer switch không có nhánh dự phòng có thể lỗi hoặc xử lý sai |
| Cho phép NULL ở trường vốn luôn có | Có thể phá code consumer giả định non-null |
| Đổi múi giờ hoặc nguồn thời điểm occurredAt | Có thể làm sai báo cáo hoặc xử lý timeout |

Không chỉ xem thay đổi schema JSON/Avro/Protobuf có “backward-compatible” theo công cụ hay không; **tương thích ngữ nghĩa** mới là điều người dùng và nghiệp vụ cần.

### 10.3. Expand–migrate–contract ở hợp đồng

Khi cần đổi productRef sang ProductReference gồm tenantId và productId, một kế hoạch giảm rủi ro:

1. **Expand:** Cung cấp cấu trúc mới song song cấu trúc cũ, hoặc phát phiên bản hợp đồng mới. Nêu rõ trường cũ còn hiệu lực tới khi nào.
2. **Migrate:** Producer và consumer lần lượt triển khai adapter có thể đọc hai phiên bản hoặc chuyển đổi có kiểm chứng; đối soát ID theo tenant.
3. **Contract:** Chỉ loại bỏ trường/phiên bản cũ khi các consumer liên quan đã chuyển và kế hoạch replay/backfill có thể xử lý lịch sử.

Đừng sửa âm thầm payload cũ tại cùng một eventType/schemaVersion rồi mong mọi consumer tự hiểu.

### 10.4. Contract test và ownership

Một hợp đồng có thể được kiểm tra bằng:

- **Producer contract tests:** dữ liệu phát đáp ứng lược đồ và ràng buộc đã công bố.
- **Consumer-driven tests:** consumer xác nhận những phần nó thật sự dùng còn được hỗ trợ.
- **Mapping/ACL tests:** trường nguồn chuyển sang ý nghĩa nội bộ đúng đơn vị, phạm vi và lịch sử.
- **Compatibility tests:** consumer của phiên bản cũ xử lý được thông điệp tương thích mới theo kế hoạch.
- **Negative tests:** thiếu trường, giá trị enum mới, currency sai, ID không cùng tenant, event đến trễ, event trùng.

Đầu ra không nhất thiết là một thư viện Java DTO chung duy nhất. Có thể dùng **schema contract độc lập với ngôn ngữ**, tài liệu API, ví dụ payload và bộ contract tests; mỗi context ánh xạ về **mô hình nội bộ của mình**.

## 11. Dữ liệu cá nhân, phân quyền và bản sao xuyên context

Tách mô hình không chỉ để giảm phụ thuộc kỹ thuật mà còn giúp thực thi nguyên tắc **chỉ lấy những gì cần thiết**:

- Identity có thể cần thông tin xác thực hoặc thông tin hồ sơ.
- Sales có thể cần buyer_ref và **ảnh chụp địa chỉ giao** cho đơn cụ thể.
- Fulfillment có thể cần tên/người nhận/địa chỉ để giao kiện, nhưng không cần dữ liệu đăng nhập.
- Billing có thể cần thông tin lập chứng từ; không nên tự động nhận toàn bộ hồ sơ và lịch sử duyệt web.

Khi phát event, cân nhắc **data minimization**: chỉ chứa những trường cần cho hợp đồng. Không biến một sự kiện “OrderSubmitted” thành một bản sao mọi cột khách hàng, địa chỉ, phương thức thanh toán và thông tin nhạy cảm, vì như vậy dữ liệu lan tới tất cả consumer.

### 11.1. Bản sao không tự có quyền sở hữu

Sales có thể duy trì một bản đọc của tên khách hàng để hiển thị; nó phải nêu:

- **Nguồn nào có thẩm quyền** cho tên hiện tại.
- Dữ liệu được cập nhật bằng event hay API và **trễ bao lâu** được chấp nhận.
- Khi nào cần **snapshot bất biến** cho giao dịch, khác với bản sao cập nhật thường xuyên.
- Quy trình sửa/xóa dữ liệu theo chính sách quyền riêng tư, lưu trữ bắt buộc và yêu cầu pháp lý áp dụng.

Không thể suy ra mọi bản sao phải bị xóa ngay lập tức hoặc giữ mãi mãi: chính sách phụ thuộc pháp luật, hợp đồng và mục đích lưu dữ liệu của doanh nghiệp. **Ranh giới sở hữu và lineage** làm các quyết định đó rõ ràng hơn.

### 11.2. Bảo mật không dừng ở tách database

Ngay cả khi mỗi context có DB riêng, một token service có quyền gọi mọi API hoặc một topic event phát toàn bộ PII vẫn tạo rủi ro. Cần quản lý:

- Quyền truy cập API/command/event theo vai trò và mục đích.
- Quyền đọc/ghi database cục bộ, tài khoản triển khai migration.
- Danh mục dữ liệu nhạy cảm, mã hóa và nhật ký truy cập phù hợp.
- Bên nào được tạo bản sao, thời hạn lưu giữ và quyền yêu cầu chỉnh sửa/xóa theo chính sách.

Các quyết định này là một phần của **thiết kế tích hợp và quản trị dữ liệu**, không thể giải quyết chỉ bằng đổi tên bảng.

## 12. Mô hình tích hợp để đọc và phân tích khác mô hình ghi dùng chung

Một tổ chức vẫn cần các báo cáo như:

- Danh sách đơn đã mua, khoản thanh toán, trạng thái giao hàng và số hàng còn lại.
- Doanh thu theo sản phẩm và phân khúc khách hàng.
- Tỷ lệ giao trễ và tỷ lệ hoàn trả theo ngành hàng.
- Số tiền đã thanh toán nhưng hàng chưa xuất kho.

Không nên suy ra rằng các báo cáo đó bắt buộc phải dùng **một schema tác nghiệp toàn cục có thể ghi từ mọi context**.

### 12.1. Read model/projection có mục đích rõ

Một mô hình đọc phục vụ trang quản lý đơn có thể là:

~~~~text
ORDER_OVERVIEW_READ_MODEL(
  sales_order_ref,
  submitted_at,
  sales_status,
  payment_summary_status,
  inventory_reservation_status,
  fulfillment_summary_status,
  last_synced_at,
  source_versions
)
~~~~

Nó được xây dựng từ những thông tin đã công bố/cho phép:

~~~~mermaid
flowchart LR
    S["Sales events"] --> P["Order Overview Projection"]
    B["Billing events"] --> P
    I["Inventory events"] --> P
    F["Fulfillment events"] --> P
    P --> UI["Trang theo dõi đơn"]
~~~~

Mô hình này **không là nguồn sự thật cho thanh toán hoặc tồn kho**. Nó là **bản đọc có thể trễ**, với thông tin nguồn, phiên bản và thời điểm cập nhật để người dùng hiểu độ tin cậy.

Khi một event PaymentSettled đến muộn, projection có thể chưa hiển thị khoản thanh toán vừa hoàn tất; nếu một event được phát lại, handler phải idempotent để không cộng tiền hai lần. Đây là tính chất của read model tích hợp, không phải lý do để chuyển quyền sửa payment sang bảng tổng hợp.

### 12.2. CQRS không đồng nghĩa microservice

**Command Query Responsibility Segregation (CQRS)** là cách tách nhu cầu **ghi để duy trì invariant** và **đọc theo góc nhìn truy vấn**. Không nhất thiết phải có hai database vật lý hay event sourcing.

Trong ví dụ:

- **Write model** Sales bảo vệ order và giá chốt.
- **Write model** Inventory bảo vệ stock/reservation.
- **Read model** Order Overview kết hợp các trạng thái để giao diện đọc nhanh.

Một hệ thống monolith vẫn có thể thiết kế **mô hình ghi rõ ranh giới** và **projection đọc tổng hợp**. Không buộc tạo dịch vụ độc lập chỉ vì dùng thuật ngữ CQRS.

### 12.3. Conformed dimension cho phân tích xuyên ngữ cảnh

Đối với báo cáo phân tích, có thể xây một **lớp dimension dùng chung** để đồng nhất:

- Product ID, phân loại ngành hàng và lịch sử taxonomy.
- Ngày theo múi giờ hoặc lịch tài chính đã chọn.
- Định danh khách đã được cấp phép phục vụ phân tích.
- Đơn vị tiền và quy tắc đổi tiền.

Rồi tạo các fact riêng:

~~~~text
FACT_SALES_LINE
FACT_PAYMENT
FACT_SHIPMENT
FACT_RETURN_LINE

DIM_DATE
DIM_PRODUCT
DIM_CUSTOMER_ANALYTICS
~~~~

Mô hình **conformed dimension** phục vụ **so sánh và truy vấn**; nó không phủ định việc Sales, Billing, Fulfillment có mô hình ghi riêng. Các fact cũng có thể có **grain khác nhau**, nên phải tổng hợp từng fact đến cấp phân tích chung trước khi JOIN, tránh fanout.

Một dimension dùng chung trong phân tích có thể là kết quả của **data mapping có quản trị**, chứ không phải bằng chứng mọi context phải dùng chung CatalogProduct entity ở tầng nghiệp vụ.

### 12.4. Mô hình đọc tích hợp không tự bảo đảm nhất quán ngay lập tức

Một bảng báo cáo có thể ghi PaymentSettled trước khi nhận OrderConfirmed do độ trễ khác nhau. Vì thế cần:

1. Chỉ rõ **source event và trường có thẩm quyền**.
2. Theo dõi **version, occurredAt/processedAt hoặc offset** khi cần.
3. Quy định mức **freshness** và trạng thái dữ liệu chưa đủ.
4. Có cơ chế **rebuild/replay** projection hoặc đối soát lại nguồn.
5. Kiểm soát quyền truy cập và dữ liệu nhạy cảm của những bản sao tổng hợp.

Không dùng projection làm nguồn cập nhật ngược Inventory hoặc Billing trừ khi đã thiết kế một quy trình command hợp lệ riêng.

## 13. Context mapping: các quan hệ hợp tác có thể khác nhau

Không phải mọi context trao đổi theo một kiểu quan hệ duy nhất. Một bản đồ tích hợp có thể làm rõ **ai định nghĩa hợp đồng và ai phải thích nghi**.

### 13.1. Upstream và downstream

Một context **upstream** công bố dữ liệu hoặc năng lực được context **downstream** sử dụng. Ví dụ Catalog có thể là upstream cho một số thông tin sản phẩm; Sales là downstream của API quote. Nhưng quan hệ này **có thể đổi chiều theo từng luồng tích hợp**: Sales công bố OrderConfirmed để Billing tiêu thụ.

Không nên gọi một dịch vụ “luôn là upstream” trong toàn bộ doanh nghiệp; phải xét **hợp đồng cụ thể**.

### 13.2. Những kiểu quan hệ thường gặp

| Kiểu quan hệ | Ý tưởng | Khi nào cân nhắc |
| --- | --- | --- |
| **Partnership** | Hai nhóm phối hợp thiết kế/triển khai một tích hợp có mục tiêu chung | Hai context phụ thuộc lịch phát hành hoặc quy trình chung |
| **Customer–Supplier** | Bên cung cấp xem xét nhu cầu của bên dùng hợp đồng | Một upstream có downstream được xác định rõ |
| **Conformist** | Downstream chấp nhận mô hình bên cung cấp khi không có quyền ảnh hưởng | Tích hợp với hệ thống bên thứ ba ít khả năng thay đổi |
| **Anti-Corruption Layer** | Downstream dịch mô hình ngoài sang ngôn ngữ nội bộ | Hai ngữ cảnh có thuật ngữ/đơn vị và invariant khác |
| **Open Host Service / Published Language** | Upstream công bố API/giao thức ổn định, có tài liệu và phiên bản | Nhiều consumer cần tích hợp nhất quán |
| **Shared Kernel** | Hai nhóm chủ ý chia sẻ **một phần nhỏ** mô hình/hợp đồng có chủ sở hữu chung | Khái niệm thật sự cùng nghĩa, ít thay đổi, có cơ chế phối hợp |
| **Separate Ways** | Không tích hợp trực tiếp vì chi phí vượt lợi ích | Dữ liệu không cần đồng bộ hoặc có giải pháp độc lập phù hợp |

Đây là **công cụ để ra quyết định**, không phải danh sách pattern phải triển khai đủ. **Shared Kernel** không có nghĩa tạo một thư viện domain khổng lồ chứa toàn bộ Catalog, Sales và Inventory. Nếu dùng, phạm vi cần **hẹp, thật sự nhất quán, có quy trình phối hợp thay đổi**.

### 13.3. Khi nào nên dùng anti-corruption layer?

Giả sử đối tác thanh toán gọi trạng thái **APPROVED**, nhưng trong Billing của doanh nghiệp “đã quyết toán” chỉ được công nhận ở trạng thái **SETTLED**. Nếu mapping thẳng APPROVED → Paid, doanh nghiệp có thể xác nhận đã thu tiền khi mới được phê duyệt, chưa thực sự quyết toán.

ACL phải phân biệt:

~~~~text
Provider.APPROVED → Billing.PaymentAuthorized
Provider.SETTLED  → Billing.PaymentSettled
Provider.DECLINED → Billing.PaymentFailed
~~~~

Tên trạng thái của provider thay đổi có thể được xử lý trong adapter, thay vì bắt toàn bộ Sales và Fulfillment hiểu ngôn ngữ của nhà cung cấp thanh toán. **Ngăn nhiễm ngữ nghĩa** quan trọng hơn đổi tên JSON cho đẹp.

## 14. Khi nào nên tách, khi nào không?

Tách mô hình theo ngữ cảnh có lợi nhưng cũng có **chi phí giao tiếp và nhất quán**. Không được dùng “DDD” như lý do tự động tạo hàng chục database và message topic cho một bài toán nhỏ.

### 14.1. Dấu hiệu nên tách mô hình

| Dấu hiệu | Lý do |
| --- | --- |
| Cùng danh từ có nghĩa/khóa/vòng đời khác nhau | Một entity chung dễ gây xung đột bất biến |
| Nhiều nhóm cần thay đổi độc lập | Một schema chung trở thành nút cổ chai migration |
| Quyền sở hữu dữ liệu khác nhau | Cần chỉ rõ bên nào được ghi, bên nào chỉ đọc |
| Giao dịch nghiệp vụ có pha và trạng thái riêng | Không nên ép mọi tiến trình vào một status |
| Cần snapshot lịch sử | Không muốn cập nhật hiện tại của một context viết đè dữ liệu quá khứ của context khác |
| Có nguồn/đối tác bên ngoài với ngữ nghĩa khác | ACL ngăn mô hình ngoài đi sâu vào domain nội bộ |
| Độ tin cậy, quyền riêng tư và chính sách lưu trữ khác nhau | Dữ liệu cần ranh giới truy cập/retention khác |

### 14.2. Dấu hiệu nên cân nhắc giữ một ranh giới chung

Nếu hai khái niệm:

- Luôn được tạo/sửa trong **cùng một giao dịch nguyên tử bắt buộc**.
- Có cùng chủ sở hữu, cùng ngôn ngữ và cùng chu kỳ thay đổi.
- Không có lợi ích độc lập rõ ràng khi tách.
- Tách ra sẽ làm mọi thao tác cốt lõi phải gọi mạng và bù giao dịch không cần thiết.

thì có thể chúng thuộc **cùng một bounded context hoặc cùng một aggregate**. Ví dụ SalesOrder và SalesOrderLine thường cùng một mô hình Sales; nếu một dòng đơn **không thể tồn tại độc lập**, việc chia chúng thành hai dịch vụ khác database sẽ gây chi phí vô ích.

### 14.3. Ranh giới sai theo hai cực đoan

**Quá ít ranh giới:** Một UniversalCustomer có 80 cột, nhóm Identity, Marketing, Billing, Sales đều ghi vào; một migration nhỏ phải chờ mọi nhóm.

**Quá nhiều ranh giới:** Một ứng dụng nhỏ tách riêng dịch vụ tính tổng dòng đơn, dịch vụ kiểm tra quantity, dịch vụ lưu từng thuộc tính rồi phải phối hợp nhiều cuộc gọi mạng để tạo một đơn hàng.

Thiết kế hợp lý là **tập trung những bất biến cần nhất quán mạnh**, tách những mô hình có nghĩa và quyền sở hữu khác, rồi tích hợp theo hợp đồng phù hợp. Không đo chất lượng thiết kế bằng **số lượng microservice**.

### 14.4. Bảng quyết định ngắn

| Câu hỏi | Nếu câu trả lời là “Có” | Hướng suy nghĩ |
| --- | --- | --- |
| Hai nhóm có định nghĩa khác nhau cho cùng tên? | Có | Tách domain type/context, tạo mapping |
| Hai bảng cần luôn cập nhật atomically? | Có | Cân nhắc cùng ranh giới giao dịch |
| Bên khác chỉ cần một số thuộc tính để đọc? | Có | Published API/event hoặc projection, tránh chia sẻ entity |
| Một bước cần kết quả ngay trước khi chốt? | Có | API đồng bộ/command với timeout và xử lý lỗi rõ |
| Kết quả có thể đến muộn nhưng cần phát tán? | Có | Event + outbox/inbox/idempotency |
| Dữ liệu dùng để báo cáo xuyên nguồn? | Có | Read model/analytics layer theo grain và conformed dimensions |
| Có nhiều consumer phụ thuộc payload? | Có | Quản trị hợp đồng, phiên bản và compatibility tests |
| Định danh chỉ duy nhất theo tenant? | Có | Mang phạm vi vào business key và contract |

## 15. Lộ trình chuyển từ mô hình dùng chung sang từng context

Một hệ thống đang chạy có thể có bảng UNIVERSAL_ORDER mà nhiều ứng dụng trực tiếp sử dụng. Không nhất thiết phải **tách hết một lần**; có thể di chuyển dần để giảm rủi ro dữ liệu.

### Bước 1 — Khám phá ngữ nghĩa và quyền ghi

- Liệt kê những nhóm/API/job đang đọc và ghi bảng chung.
- Ghi từng cột có **ý nghĩa gì với từng nhóm**.
- Xác định invariant, bên có quyền chốt giá, tồn, thanh toán, giao hàng.
- Tìm những trường đang bị nhiều nhóm viết chồng hoặc dùng sai trạng thái.

### Bước 2 — Vẽ context map và xác định hợp đồng đầu tiên

- Phân định Catalog, Sales, Inventory, Billing, Fulfillment hoặc ranh giới thực tế phù hợp.
- Chọn **một luồng ít rủi ro, giá trị cao** để tách trước, ví dụ Sales chỉ đọc Catalog qua quote API thay vì đọc trực tiếp bảng sản phẩm.
- Ghi contract, mã định danh, đơn vị, trạng thái, phiên bản và error handling.

### Bước 3 — Bảo vệ mô hình mới bằng adapter

- Đặt API hoặc ACL giữa consumer và mô hình chung cũ.
- Không cho các module mới tự ý ghi vào bảng chung.
- Viết kiểm thử với dữ liệu hiện tại và ví dụ phản chứng.
- Dùng telemetry để xác định những đường đọc/ghi nào đã được chuyển.

### Bước 4 — Tách quyền sở hữu dữ liệu theo từng phần

- Chuyển dần các cột/quan hệ sang schema hoặc database thuộc context tương ứng.
- Thiết kế business ID và local ID, mapping, giữ lịch sử cần thiết.
- Nếu cần đồng bộ dữ liệu trong giai đoạn chuyển, định nghĩa **nguồn sự thật duy nhất cho mỗi thuộc tính**. Không để cả hai bảng mới/cũ tùy ý ghi hai chiều mà không có quy tắc xung đột.
- Chọn sự kiện/CDC/projection có thể kiểm chứng khi cần bản đọc từ context khác.

### Bước 5 — Chạy song song, đối soát và chuyển lưu lượng

Ví dụ Sales mới và Sales cũ cùng tạo ra một **projection doanh thu thử nghiệm**. So sánh:

- Số đơn/dòng đơn, giá chốt, tiền tệ và tổng tiền theo kỳ.
- Những giao dịch đến muộn, hủy, sửa, hoàn trả.
- Trường hợp một sản phẩm đã ngừng bán nhưng vẫn có đơn lịch sử.
- Mã sai tenant và tham chiếu không tìm được ở nguồn.

**Đối soát không chỉ so COUNT:** Hai tập dữ liệu có cùng số hàng nhưng khác giá chốt hoặc trạng thái vẫn là sai.

### Bước 6 — Thu hồi hợp đồng/bảng cũ theo kế hoạch

- Chỉ bỏ đường ghi cũ sau khi producer và consumer đã chuyển.
- Theo dõi event replay, dữ liệu tồn đọng và backfill.
- Công bố thời điểm dừng API/schema cũ, cách xử lý báo cáo lịch sử và quyền truy cập.
- Không xóa dữ liệu được yêu cầu lưu giữ chỉ vì schema cũ không còn là nguồn ghi chính.

### Các rủi ro cần ghi trong kế hoạch

| Rủi ro | Cách giảm thiểu |
| --- | --- |
| Dual write không nguyên tử | Outbox/luồng đồng bộ có kiểm chứng, không tự cam kết hai commit cùng lúc |
| Mã nguồn không ổn định | Business ID/mapping có phiên bản và quy tắc phạm vi |
| Không thể dựng lịch sử | Chỉ rõ giới hạn nguồn và chính sách snapshot |
| Hai bên đều sửa cùng dữ liệu | Xác định một bên sở hữu, lệnh sửa có hợp đồng |
| Consumer chưa chuyển mà producer đổi payload | Expand–migrate–contract, contract tests |
| Event gửi lại và đến lệch | Idempotency, version/ordering, đối soát |
| Quyền dữ liệu bị mở rộng | ACL, tối thiểu hóa payload, quyền truy cập và kiểm tra lineage |

Đây là **một lộ trình gợi ý**. Tùy rủi ro, doanh nghiệp có thể bắt đầu bằng modular monolith và tách deploy sau, không bắt buộc chuyển thẳng sang microservice hoặc event-driven toàn diện.

## 16. Checklist kiểm chứng thiết kế ranh giới dữ liệu

Trước khi một nhóm công bố rằng đã tách mô hình theo bounded context, hãy kiểm tra:

1. **Ngôn ngữ và phạm vi:** Mỗi context có câu mô tả nhiệm vụ, thuật ngữ và quy tắc không mâu thuẫn trong chính context ấy.
2. **Ownership:** Mỗi trạng thái nghiệp vụ quan trọng có một nguồn sự thật và bên chịu trách nhiệm ghi/sửa.
3. **Không trộn entity:** Các kiểu Order, Product, Customer khác nghĩa không bị ép thành một class/bảng toàn cục chỉ vì tên giống.
4. **Invariant và transaction:** Những quy tắc phải đúng tức thời nằm trong ranh giới giao dịch có thể bảo vệ; quy tắc xuyên context có protocol nhất quán và trạng thái trung gian.
5. **Khóa:** Phân biệt PK cục bộ, business ID, external reference và phạm vi tenant/source. Không dùng nhãn hay email làm khóa liên kết mặc định.
6. **FK:** Các FK nội bộ bảo vệ dữ liệu cục bộ; FK xuyên context nếu có phải là quyết định có đánh giá coupling, không là đường đọc/ghi tùy tiện.
7. **Snapshot:** Giá, địa chỉ, tên hoặc trạng thái cần giữ tại thời điểm nghiệp vụ được lưu đúng ngữ nghĩa; không bị cập nhật theo nguồn hiện tại nếu phải giữ lịch sử.
8. **API:** Hợp đồng đồng bộ trả lời đúng câu hỏi của consumer, có cách xử lý timeout, lỗi và điều kiện hợp lệ.
9. **Event/command:** Tên và payload thể hiện đúng sự kiện đã xảy ra hoặc yêu cầu cần thực thi; không đồng nhất “đã gửi đơn” với “đã thu tiền”.
10. **Versioning:** Contract có phiên bản và kế hoạch tiến hóa; không đổi âm thầm đơn vị tiền hoặc ý nghĩa enum.
11. **ACL:** Mô hình của bên ngoài được dịch sang loại dữ liệu và ngữ nghĩa cục bộ; domain code không phụ thuộc trực tiếp vào bảng hoặc ORM entity của context khác.
12. **Delivery reliability:** Giao dịch + outbox ở phía phát; idempotency/inbox ở phía nhận nếu cần; có xử lý gửi lại, đến trễ và đảo thứ tự.
13. **Business idempotency:** Cùng yêu cầu nghiệp vụ từ hai eventId khác nhau không tạo hai lần tác dụng phụ ngoài mong muốn.
14. **Saga:** Có quy tắc chuyển trạng thái, timeout, tác vụ bù và cách xử lý trường hợp đã xảy ra tác dụng không thể rollback đơn thuần.
15. **Read model:** Báo cáo và projection xuyên nguồn có chủ sở hữu, định nghĩa mức trễ, nguồn dữ liệu và cách đối soát; không biến bản đọc thành nguồn ghi cạnh tranh.
16. **Quyền và riêng tư:** Chỉ trao đổi dữ liệu cần thiết, quản lý quyền và thời hạn lưu giữ theo chính sách.
17. **Kiểm thử:** Có test cho từng invariant, contract producer/consumer, các trường hợp trùng/lỗi/mất thông điệp và đối soát giữa các context.
18. **Thay đổi độc lập:** Một context có thể đổi schema nội bộ mà consumer không cần đổi, miễn hợp đồng đã công bố vẫn được giữ.
19. **Giới hạn vận hành:** Độ trễ, khả năng phục hồi và chi phí tích hợp được đánh giá; không tách vật lý chỉ vì sơ đồ đẹp.
20. **Lộ trình chuyển đổi:** Các đường đọc/ghi cũ được thu hồi theo từng bước, không có hai bên cùng sửa một thuộc tính mà không có quy tắc.

### Ma trận “đầu ra nào để chứng minh ranh giới?”

| Đầu ra | Câu hỏi được kiểm chứng |
| --- | --- |
| **Context map** | Các phạm vi nào có ý nghĩa riêng và trao đổi với ai? |
| **Mô hình từng context** | Mỗi context sở hữu entity, khóa, invariant và vòng đời nào? |
| **Data ownership matrix** | Trường/trạng thái nào có nguồn sự thật ở đâu? |
| **Integration contracts** | API, command, event có tên, phiên bản, schema, đơn vị và ý nghĩa nào? |
| **ACL/mapping specification** | Giá trị bên ngoài đổi thành mô hình nội bộ bằng quy tắc nào? |
| **Consistency workflow** | Trạng thái chờ, lỗi, timeout, bù và thứ tự sự kiện ra sao? |
| **Reliability tests** | Retry, dedup, replay, outbox/inbox và xử lý xung đột có đúng không? |
| **Read-model contract** | Projection được cập nhật từ đâu, độ trễ và lineage được hiểu thế nào? |
| **Migration plan** | Có chuyển dần từ shared schema sang quyền sở hữu độc lập một cách an toàn không? |

## 17. Bài tập thực hành có đáp án

### Bài 1 — Một từ “khách hàng” có phải một bảng toàn cục?

Identity lưu tài khoản đăng nhập, Sales lưu buyer và địa chỉ giao của đơn, Billing lưu doanh nghiệp chịu trách nhiệm thanh toán. Một kiến trúc sư đề xuất bảng CUSTOMER chung chứa email đăng nhập, địa chỉ giao, mã số thuế, lịch sử thanh toán và trạng thái marketing.

**Câu hỏi:** Đề xuất ấy có vấn đề gì? Cần làm rõ trước khi gộp?

**Đáp án:** Những dữ liệu đó có **ý nghĩa, quyền sở hữu, quy tắc lịch sử và quyền truy cập khác nhau**. Cần xác định **identity user, buyer, recipient, bill-to party** có phải cùng một đối tượng nghiệp vụ hay chỉ có quan hệ ánh xạ. Có thể dùng định danh/contract chung cho những chỗ thật sự cần liên kết, nhưng không nên ép toàn bộ trường và quyền ghi vào một CUSTOMER nếu các ngữ cảnh độc lập.

### Bài 2 — Giá hiện hành và giá chốt đơn

Catalog có giá hiện hành của P01 là 120.000 VND. Đơn O100 đã mua P01 tuần trước với giá chấp nhận 90.000 VND. Một job đồng bộ tên/giá Catalog dự định UPDATE tất cả dòng SalesOrderLine của P01 thành 120.000.

**Câu hỏi:** Nên làm không?

**Đáp án:** Không nếu accepted_unit_price là **giá của giao dịch đã chốt**. Sales phải giữ giá chấp nhận theo quy tắc của mình; thay đổi giá hiện hành trong Catalog không phải sự kiện sửa đơn cũ. Có thể dùng current_list_price cho hiển thị hiện hành và accepted_unit_price cho lịch sử, với quyền sở hữu rõ ràng.

### Bài 3 — Inventory có nên cho Sales trực tiếp UPDATE?

Sales muốn giảm reserved_qty trong Inventory sau khi khách bấm mua. Nhóm Sales đề nghị tài khoản DB của mình có quyền UPDATE inventory.stock để giảm một chuyến gọi API.

**Câu hỏi:** Rủi ro và phương án thay thế?

**Đáp án:** Sales sẽ vượt quyền sở hữu, có thể phá invariant giữ chỗ, không phối hợp được nhiều kho, retry hoặc hết hạn reservation. Nên gửi **ReserveStock command/API** với request_id ổn định; Inventory kiểm tra khả dụng và cập nhật stock/reservation trong giao dịch cục bộ, trả kết quả theo hợp đồng. Nếu cùng monolith, lệnh vẫn có thể là **gọi module nội bộ** chứ không bắt buộc qua mạng.

### Bài 4 — FK nội bộ hay FK xuyên ngữ cảnh?

Sales có SalesOrder và SalesOrderLine. SalesOrderLine.order_id trỏ SalesOrder.order_id. SalesOrderLine.catalog_product_ref trỏ mã sản phẩm bên Catalog.

**Câu hỏi:** FK nào nên được DB Sales bảo vệ trực tiếp? Có phải mọi external reference đều phải là FK SQL?

**Đáp án:** FK từ **OrderLine đến Order** nằm trong Sales, nên DB Sales có thể bảo vệ trực tiếp. catalog_product_ref là **tham chiếu liên ngữ cảnh**; nếu Catalog có DB riêng, không thể dùng FK SQL thông thường đến đó. Tính hợp lệ của việc chào bán cần kiểm tra qua contract/API hoặc cơ chế đồng bộ được thiết kế; snapshot giúp giữ lịch sử.

### Bài 5 — Bounded context có đồng nghĩa microservice?

Một ứng dụng Java monolith có package Catalog, Sales và Inventory với interface module rõ ràng, mỗi module quản lý bảng thuộc schema riêng và không đọc/sửa dữ liệu nhau ngoài API nội bộ.

**Câu hỏi:** Có thể xem đây là các bounded context dù chỉ một tiến trình?

**Đáp án:** **Có thể**, nếu mỗi phạm vi có ngôn ngữ, invariant, mô hình và quyền sở hữu rõ ràng. Bounded context là ranh giới **ngữ nghĩa và mô hình**, không nhất thiết là ranh giới tiến trình. Tách deploy chỉ là một lựa chọn triển khai tiếp theo.

### Bài 6 — Không nên tạo một enum trạng thái chung

Hệ thống đề xuất enum UniversalOrderStatus = NEW, PAID, PACKING, DELIVERED, RETURNED để cả Sales, Billing và Fulfillment cùng ghi vào một trường.

**Câu hỏi:** Sai ở đâu?

**Đáp án:** Một đơn có thể **đã thanh toán nhưng đang đóng gói**, hoặc **đã giao nhưng được hoàn tiền một phần**. Một enum không thể mô tả đồng thời các tiến trình độc lập mà không mất thông tin hoặc tạo hàng trăm tổ hợp. Nên giữ **SalesStatus, PaymentStatus, ShipmentStatus** trong context sở hữu; projection hiển thị tổng quan dựa trên quy tắc có tên rõ ràng.

### Bài 7 — Phân biệt sự kiện và lệnh

Đội Inventory nhận thông điệp có tên InventoryReserved nhưng payload thực ra chỉ chứa yêu cầu “hãy giữ 2 sản phẩm”.

**Câu hỏi:** Tên có phù hợp không? Đổi thế nào?

**Đáp án:** Không. **InventoryReserved** nghe như một sự thật đã giữ thành công. Yêu cầu nên là **ReserveStock** với request_id; khi Inventory commit giữ chỗ thành công mới phát **StockReserved**. Nếu không giữ được, có kết quả **StockReservationRejected** hoặc phản hồi thất bại với ngữ nghĩa rõ.

### Bài 8 — API đồng bộ và sự kiện bất đồng bộ

Sales cần biết quote có còn hiệu lực **trước khi chốt giao dịch**, còn trang tổng quan chỉ cần cập nhật trạng thái giao hàng vài giây sau khi có event.

**Câu hỏi:** Nên cân nhắc hình thức tích hợp nào cho từng nhu cầu?

**Đáp án:** Quyết định quote có thể phù hợp với **API/command đồng bộ** có timeout, xử lý lỗi và kiểm tra hiệu lực; trạng thái giao vận cho trang tổng quan có thể dùng **event bất đồng bộ và projection** nếu độ trễ được chấp nhận. Cả hai vẫn cần hợp đồng và cách xử lý retry/idempotency thích hợp.

### Bài 9 — Event gửi thành công nhưng chưa đánh dấu published

Relay đọc outbox, publish OrderConfirmed thành công rồi bị lỗi trước khi UPDATE published_at. Sau khi khởi động lại, relay phát lại cùng event.

**Câu hỏi:** Đó có phải bằng chứng outbox sai không? Consumer nên làm gì?

**Đáp án:** Đây là **tình huống gửi lại có thể xảy ra** trong thiết kế outbox, không phải lý do bỏ outbox. Consumer dùng **eventId/inbox** và xử lý idempotent để không áp dụng tác dụng phụ hai lần. Ngoài ra cần business idempotency key nếu cùng một yêu cầu được phát dưới hai eventId khác nhau.

### Bài 10 — Ghi inbox trước rồi xử lý sau

Consumer nhận event và INSERT inbox, COMMIT; sau đó mới tăng reserved_qty. Tiến trình sập ở giữa.

**Câu hỏi:** Điều gì sai và sửa thế nào?

**Đáp án:** Inbox đã ghi “đã xử lý” dù tồn kho chưa được cập nhật; lần giao lại có thể bị bỏ qua. Phải ghi dấu inbox và thay đổi trạng thái cục bộ **trong cùng một transaction**, COMMIT cùng nhau sau khi xử lý thành công; lỗi phải ROLLBACK cả hai.

### Bài 11 — Invariant và eventual consistency

Sales hiển thị “đang chờ giữ hàng” trong 3 giây sau OrderSubmitted, trong khi Inventory chưa xác nhận StockReserved.

**Câu hỏi:** Có phải dữ liệu đã sai không? Invariant nào phải đúng ngay?

**Đáp án:** Đây có thể là trạng thái **đang chờ hợp lệ** nếu hợp đồng cho phép nhất quán cuối cùng. Nhưng tại Inventory, invariant **không giữ vượt tồn khả dụng** vẫn phải được bảo vệ ngay khi xử lý reservation. Sales không được tự chuyển CONFIRMED nếu điều kiện nghiệp vụ yêu cầu stock đã reserved mà chưa có kết quả hợp lệ.

### Bài 12 — Bù giao dịch sau thanh toán thất bại

Inventory giữ hàng thành công, Billing trả PaymentFailed. Sales cần hủy đơn.

**Câu hỏi:** Chỉ ROLLBACK transaction của Sales có giải phóng được tồn đã giữ không?

**Đáp án:** Không. Inventory đã COMMIT giao dịch riêng. Quy trình saga phải yêu cầu Inventory **ReleaseReservation** và xử lý phản hồi, timeout hoặc retry; sau đó Sales ghi trạng thái phù hợp. Bù là **hành động nghiệp vụ**, không phải rollback SQL xuyên nhiều database.

### Bài 13 — Consumer hiểu sai trạng thái thanh toán

Một cổng thanh toán phát APPROVED khi thẻ được phê duyệt, SETTLED khi tiền được quyết toán. Billing dùng từ PAID cho trạng thái SETTLED. Một mapper lại chuyển APPROVED thành PAID.

**Câu hỏi:** Đây là lỗi nào và nên đặt kiểm tra ở đâu?

**Đáp án:** Đây là **lỗi ngữ nghĩa hợp đồng**. ACL ở Billing phải chuyển APPROVED thành PaymentAuthorized, SETTLED thành PaymentSettled theo quy tắc đã xác nhận. Contract test với trạng thái provider giúp ngăn một thay đổi vendor lan thành hành vi thanh toán sai.

### Bài 14 — Thay đổi payload mà giữ tên/version

Producer trước đây phát amount = "90000.00" với đơn vị VND. Sau nâng cấp, producer giữ eventType/schemaVersion như cũ nhưng đổi amount thành **90000 tiểu đơn vị của tiền tệ khác**, không thêm currency.

**Câu hỏi:** Có tương thích không?

**Đáp án:** Không. Cùng kiểu JSON string/number không có nghĩa cùng ngữ nghĩa. Thay đổi **đơn vị tiền** là breaking; phải công bố hợp đồng mới hoặc áp quy trình chuyển đổi rõ ràng, giữ amount + currency và kiểm tra consumer, không đổi âm thầm.

### Bài 15 — Dùng read model làm nguồn ghi

OrderOverviewProjection có cột payment_status được cập nhật từ event Billing. Một nhóm muốn sửa cột này trực tiếp để “xác nhận đã thu tiền”, rồi coi Billing sẽ tự hiểu.

**Câu hỏi:** Có nên không?

**Đáp án:** Không. Projection là **bản đọc suy ra** và có thể trễ; Billing mới sở hữu nghiệp vụ quyết toán. Muốn thực hiện thao tác thu tiền phải gửi **command đến Billing** theo quyền và quy tắc phù hợp. Sửa trực tiếp projection làm dữ liệu hiển thị khác nguồn sự thật.

### Bài 16 — Cùng dữ liệu cho báo cáo không có nghĩa một bảng ghi chung

Báo cáo cần doanh thu, số tiền đã thu và tỷ lệ giao thành công theo ngày–sản phẩm. Nhóm BI đề xuất buộc Sales, Billing và Fulfillment dùng một bảng FACT_GLOBAL duy nhất và cùng UPDATE.

**Câu hỏi:** Có cần mô hình ghi chung không?

**Đáp án:** Không. Có thể giữ **fact/sự kiện ghi riêng** theo Sales, Billing, Fulfillment rồi xây **mô hình phân tích tích hợp** với dimension có định nghĩa thống nhất. Phải xác định grain, ngày sự kiện, tiền tệ và cách tổng hợp từng fact trước khi so sánh, tránh fanout và không biến FACT_GLOBAL thành nguồn ghi cạnh tranh.

### Bài 17 — Khóa có phạm vi tenant

Hai tenant có product_code = NOTE-A5 nhưng là hai sản phẩm khác nhau. Sales chỉ phát productCode = NOTE-A5 cho Inventory.

**Câu hỏi:** Nguy cơ gì và cần chỉnh hợp đồng?

**Đáp án:** Inventory có thể tra nhầm tồn kho của tenant khác. Hợp đồng phải mang **tenantId và productId/productCode với phạm vi định danh rõ**, hoặc một ID toàn hệ thống thực sự duy nhất. Không nên dùng nhãn hiển thị hoặc SKU địa phương làm định danh liên ngữ cảnh nếu không kèm phạm vi.

### Bài 18 — Khi nào không nên tách thêm context?

SalesOrder và SalesOrderLine luôn được cập nhật atomically. Mỗi dòng đơn không có vòng đời độc lập; khi xóa một đơn nháp, dòng nháp phải mất theo. Một nhóm đề xuất hai microservice riêng, mỗi dòng đơn nạp qua message broker.

**Câu hỏi:** Có nên tách không?

**Đáp án:** Chưa có lý do thuyết phục. Đây nhiều khả năng là **các thực thể trong cùng context/aggregate Sales**; tách làm tăng chi phí mạng, đồng bộ và xử lý lỗi cho một invariant cần transaction chung. Nên ưu tiên mô hình cục bộ có PK/FK và giao dịch nguyên tử, chỉ tách khi có lý do nghiệp vụ và vận hành cụ thể.

### Bài 19 — Shared Kernel có nghĩa chia sẻ mọi entity?

Hai nhóm dùng chung một lớp CountryCode bất biến, nhưng còn muốn đưa Order, Payment, Stock và User vào cùng package domain-common.

**Câu hỏi:** Nên chấp nhận phần nào và cần điều kiện gì?

**Đáp án:** Một value object hoặc thuật ngữ **thật sự giống nghĩa**, ít đổi và có quy trình phối hợp có thể là shared kernel nhỏ. Không nên biến domain-common thành **mô hình tất cả nghiệp vụ**. Nếu Order/Payment/Stock có invariant và vòng đời riêng, hãy giữ tại context sở hữu và tích hợp bằng contract.

### Bài 20 — Lập kế hoạch chuyển dần khỏi bảng chung

Ba ứng dụng cùng sửa UNIVERSAL_PRODUCT. Nhóm muốn đổi thành Catalog sở hữu thông tin sản phẩm, Sales giữ snapshot và Inventory giữ stock, nhưng không được làm ngừng hoạt động hệ thống.

**Câu hỏi:** Nêu các bước ưu tiên và bằng chứng nghiệm thu.

**Đáp án tham khảo:**

1. Kiểm kê **đường đọc/ghi**, ý nghĩa mỗi cột và quy tắc chủ sở hữu.
2. Công bố context map, ID, API/event và ACL cho consumer.
3. Chặn đường ghi mới xuyên context; chuyển từng nhóm sang **một nguồn ghi có thẩm quyền**.
4. Xây snapshot Sales và stock Inventory trong phạm vi riêng, có kế hoạch đồng bộ/migration.
5. Đối soát **số lượng, giá chốt, tồn, sự kiện trễ và trường hợp lỗi**, không chỉ so COUNT.
6. Chuyển lưu lượng từng phần, bảo vệ contract cũ trong giai đoạn tương thích.
7. Thu hồi bảng/quyền truy cập cũ **sau khi** consumer đã chuyển và dữ liệu lịch sử được xử lý đúng chính sách.

Không có yêu cầu phải tạo ngay năm microservice; có thể bắt đầu bằng **modular monolith**, dùng contract và quyền sở hữu rõ trước khi tách vật lý.

## 18. Tổng kết

| Khái niệm | Ghi nhớ |
| --- | --- |
| **Bounded context** | Ranh giới mà mô hình, thuật ngữ và invariant có nghĩa nhất quán |
| **Một từ, nhiều nghĩa** | Product/Order/Customer có thể là những mô hình khác nhau ở từng context |
| **Data ownership** | Một bên chịu trách nhiệm cho trạng thái nghiệp vụ; bên khác dùng hợp đồng hoặc bản đọc |
| **Local PK/FK** | Bảo vệ thực thể và quan hệ **trong** context sở hữu |
| **External reference** | Liên kết định danh theo contract, không mặc nhiên là FK xuyên hệ thống |
| **Snapshot** | Giữ dữ liệu theo thời điểm giao dịch, không tự cập nhật theo trạng thái hiện tại |
| **API đồng bộ** | Hỏi/ra lệnh để có kết quả trực tiếp; cần xử lý timeout và lỗi |
| **Integration event** | Thông báo điều đã xảy ra, có eventId, version, thời điểm và payload có nghĩa |
| **Command** | Yêu cầu thực hiện một hành động; không giả định hành động đã thành công |
| **ACL** | Dịch mô hình ngoài sang ngôn ngữ/kiểu miền nội bộ, tránh lan nhiễm khái niệm |
| **Eventual consistency** | Bản đọc giữa các context có thể chậm; invariant cục bộ vẫn phải đúng |
| **Saga** | Phối hợp giao dịch cục bộ với bước tiếp và bù theo nghiệp vụ |
| **Transactional outbox** | Lưu state và ý định phát event trong cùng transaction cục bộ |
| **Inbox/idempotency** | Xử lý sự kiện phát lại mà không lặp tác dụng phụ |
| **Contract versioning** | Quản lý cả tương thích schema lẫn **tương thích ngữ nghĩa** |
| **Read model/CQRS** | Phục vụ truy vấn kết hợp, không trở thành nguồn ghi cạnh tranh |
| **Conformed dimension** | Thống nhất chiều phân tích ở lớp đọc, không ép mọi context dùng một write model |
| **Shared Kernel** | Chỉ chia sẻ phần thật sự cùng nghĩa, nhỏ và có quyền quản trị chung |
| **Migration** | Chuyển quyền sở hữu từng bước, đối soát và thu hồi hợp đồng cũ có kiểm soát |

**Kết luận:** Thiết kế mô hình dữ liệu theo từng ngữ cảnh không phải là từ bỏ tích hợp; đó là **làm cho tích hợp có nghĩa và có hợp đồng rõ ràng**. Catalog định nghĩa sản phẩm đang chào bán, Sales giữ đơn và giá chốt, Inventory bảo vệ tồn và giữ hàng, Billing bảo vệ chứng từ và tiền, Fulfillment bảo vệ quá trình giao. Mỗi context cần khóa, invariant và quyền sửa độc lập đúng phạm vi. Những mối liên hệ được biểu diễn bằng **ID, API, command, event, ACL, mô hình đọc và quy trình nhất quán** phù hợp, thay vì ép toàn bộ hệ thống chia sẻ một entity hoặc một bảng tác nghiệp khổng lồ. Khi các ranh giới này được chứng minh bằng kiểm thử, đối soát và quản trị hợp đồng, hệ thống có thể **thay đổi từng phần mà vẫn giữ dữ liệu và quy tắc nghiệp vụ kiểm chứng được**.
