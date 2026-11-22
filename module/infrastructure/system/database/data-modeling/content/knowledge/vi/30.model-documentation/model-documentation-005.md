# Quy ước đặt tên nhất quán mà vẫn giữ đúng ngôn ngữ nghiệp vụ

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **tên nghiệp vụ** và **tên triển khai kỹ thuật**, hiểu vì sao tuân thủ một kiểu chữ chưa đồng nghĩa mô hình dữ liệu rõ nghĩa.
- Xây dựng **bảng thuật ngữ (*glossary*)** với định nghĩa, phạm vi, nguồn chuẩn và chủ sở hữu trong từng **ngữ cảnh giới hạn (*bounded context*)**.
- Đặt tên rõ ràng cho **thực thể, quan hệ, khóa, trạng thái, thời gian, tiền tệ, bản chụp giao dịch, fact/dimension, API và sự kiện tích hợp**.
- Phát hiện các tên chung chung như **customer, status, amount, date, value, data** có nguy cơ che mất grain và bất biến nghiệp vụ.
- Thiết kế quy ước vật lý nhất quán cho PostgreSQL, đồng thời giữ ngôn ngữ đúng nghĩa khi biểu diễn dữ liệu trong relational, document, graph và analytics.
- Đổi tên có kiểm soát qua **expand – migrate – contract**, bảo vệ API, event, cache, ETL và các consumer đang hoạt động.
- Xây dựng checklist, data dictionary và các bài kiểm thử giúp chứng minh tên trường diễn đạt đúng dữ liệu thực.

Bài thuộc chương **Tài liệu mô hình** trong **DATABASE_DATA_MODELING**. Module này rèn cách chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời so sánh quan hệ, document, graph và phân tích để chọn cấu trúc dễ tiến hóa, dễ kiểm chứng. **Quy ước đặt tên là một phần của hợp đồng mô hình**, không phải chỉ là quy định thẩm mỹ của mã nguồn.

> **Nguyên tắc:** chuẩn hóa cách viết tên, nhưng **không ép các khái niệm nghiệp vụ khác nhau dùng chung một từ** chỉ để nhìn cho đồng bộ.

## 1. Tên nhất quán về cú pháp vẫn có thể sai nghĩa

Một hệ thống bán hàng cũ có ba bảng:

~~~text
customer:
  id, status, updated_at

order:
  id, customer_id, amount, date

payment:
  id, order_id, amount, date
~~~

Cách viết đều ngắn gọn nhưng người đọc chưa biết:

- **customer** là một người, một hồ sơ CRM, một tài khoản đăng nhập, bên mua hay người nhận hàng?
- **status** là trạng thái tài khoản, kiểm tra danh tính hay điều kiện được đặt hàng?
- **order.amount** là tổng tiền hàng đã xác nhận, số tiền bao gồm phí và thuế, hay số tiền thực thu?
- **payment.amount** là tiền dự định thu, tiền capture thành công hay tiền hoàn?
- **date** là ngày tạo, xác nhận, thanh toán, nhận message hay ngày pipeline nạp?
- **id** duy nhất toàn hệ thống hay chỉ trong một tenant hoặc một hệ nguồn?

Một truy vấn chạy đúng cú pháp vẫn có thể trả **doanh thu sai** vì cộng số tiền ở sai giai đoạn hoặc sai grain. Đổi **amount** thành **order_amount** là một cải thiện nhỏ; nhưng chỉ khi có định nghĩa rằng nó thực sự là **giá trị nào tại thời điểm nào** thì người dùng mới có thể tin cậy.

Ví dụ tên có mục đích rõ ràng hơn:

~~~text
sales.orders:
  tenant_id
  order_id
  buyer_account_id
  order_state_code
  confirmed_at
  confirmed_items_amount
  currency_code

billing.payment_captures:
  tenant_id
  capture_id
  order_id
  capture_state_code
  captured_at
  captured_amount
  currency_code
~~~

Người đọc có thể thấy **đơn được xác nhận** khác **lần capture tiền**. Dù vậy, họ vẫn cần data dictionary để biết **confirmed_items_amount** có gồm thuế, vận chuyển hay giảm giá cấp đơn không.

### 1.1. Có hai lớp nhất quán khác nhau

| Lớp | Kiểm tra điều gì? | Ví dụ |
| --- | --- | --- |
| **Cú pháp** | Kiểu chữ, từ viết tắt, số ít/số nhiều, hậu tố | PostgreSQL lowercase snake_case; thời điểm kết thúc bằng _at |
| **Ngữ nghĩa** | Một tên có đúng sự thật được đo và trong đúng context? | captured_amount không phải order_value |
| **Grain và định danh** | Một hàng đại diện điều gì? ID duy nhất ở đâu? | Một capture_id nhận diện một lần capture |
| **Thời điểm và đơn vị** | Khi nào và theo thước đo nào? | price_at_confirmation, currency_code |
| **Quyền sở hữu** | Ai được quyết định giá trị và cung cấp cho consumer? | Payment quyết định capture thành công |

Quy ước naming kiểu chữ chỉ bảo vệ hàng đầu tiên. Những dòng sau cần làm rõ nghiệp vụ, ràng buộc và bài kiểm thử.

## 2. Ubiquitous language: chọn từ cùng người làm nghiệp vụ

**Ubiquitous language** là từ vựng được nghiệp vụ và kỹ thuật thống nhất sử dụng trong một phạm vi cụ thể. Phạm vi rất quan trọng: cùng một chữ trong hai bounded context có thể mang hai nghĩa hợp lệ nhưng khác nhau.

| Thuật ngữ | Context | Nghĩa có thể cần dùng | Không mặc định giống |
| --- | --- | --- | --- |
| **Customer** | CRM | Hồ sơ quan hệ khách hàng | Account đăng nhập |
| **Buyer account** | Sales | Tài khoản có quyền đặt đơn | Người nhận |
| **Payer** | Payment | Chủ thể thực hiện nghĩa vụ trả tiền | Buyer |
| **Recipient** | Fulfillment | Người nhận một shipment | Chủ tài khoản |
| **Product** | Catalog | Nhóm/mô tả sản phẩm được công bố | SKU cụ thể |
| **Product variant** | Inventory | Biến thể bán hoặc tồn riêng | Product group |
| **Order** | Sales | Một đơn đặt hàng theo vòng đời Sales | Payment/Invoice |
| **Invoice** | Billing | Chứng từ có quy tắc phát hành | Bản sao đơn hàng |
| **Shipment** | Logistics | Một kiện/đợt giao với mã và trạng thái riêng | Một đơn hàng |
| **Revenue** | Finance | Chỉ số được ghi nhận theo chính sách tài chính | Tổng đơn đã xác nhận |

Không tự tạo một bảng **customers** toàn cục rồi bắt mọi domain tham chiếu nó như một đối tượng giống hệt. Một người có thể có nhiều tài khoản; bên thanh toán có thể khác bên mua; người nhận hàng có thể là người thứ ba.

### 2.1. Từ câu nói nghiệp vụ tới thực thể và quan hệ

Người quản lý kho nói:

> “Một đơn có thể chia thành ba kiện. Mỗi kiện có mã vận đơn. Một kiện có thể được giao thử vài lần.”

Những khái niệm cần có:

- **Order**: một đơn mua.
- **Shipment**: một kiện/đợt giao, quan hệ Order 1:N Shipment.
- **DeliveryAttempt**: một lần giao thử, quan hệ Shipment 1:N DeliveryAttempt.
- **TrackingNumber**: mã vận đơn do đối tác vận chuyển cấp, có thể cần carrier để tạo định danh duy nhất.
- **DeliveredAt**: mốc giao thành công, khác **ShippedAt** và **LastAttemptedAt**.

Nếu chỉ có **orders.delivery_date**, mô hình không đủ biểu diễn các lần giao thử và nhiều kiện. **Đặt tên tốt không thay thế thiết kế quan hệ**; nó giúp phát hiện sự thiếu hụt khi biến yêu cầu thành model.

### 2.2. Làm rõ trước khi tạo metric

Người kinh doanh yêu cầu “số khách mới theo ngày”. Tên **new_customer_count** chưa đủ vì “mới” có thể là:

- Tài khoản vừa đăng ký.
- Hồ sơ CRM lần đầu xuất hiện.
- Người mua lần đầu có đơn đã xác nhận.
- Người mua lần đầu đã thanh toán thành công.
- Một khách được hợp nhất từ hai hồ sơ nguồn hôm nay.

Có thể dùng **registered_account_count** hoặc **first_confirmed_order_buyer_count**, với nguồn, trạng thái lọc và mốc thời gian được mô tả. Không để một metric cũ giữ tên trong khi nhóm BI âm thầm đổi định nghĩa.

## 3. Glossary: mỗi tên quan trọng phải tìm được định nghĩa

Một **bảng thuật ngữ theo bounded context** nên có:

| Trường tài liệu | Mục đích |
| --- | --- |
| **Tên tiếng Việt** | Tên người nghiệp vụ thực sự dùng |
| **Technical term** | Tên canonical trong code/schema |
| **Bounded context** | Sales, Billing, Inventory, Fulfillment... |
| **Định nghĩa và ngoại lệ** | Điều gì được tính và không được tính |
| **Grain** | Một hàng hoặc một giá trị đại diện sự thật nào |
| **Business/natural key** | Định danh và phạm vi duy nhất |
| **Authority/owner** | Hệ hoặc nhóm có quyền quyết định |
| **Thời gian/đơn vị** | Event time, snapshot, currency, unit |
| **Phân loại dữ liệu** | PII, nội bộ, công khai, quyền truy cập |
| **Alias/legacy name** | Tên cũ và thời hạn tương thích |
| **Version và quyết định** | Ai duyệt và khi nào đổi nghĩa |

Ví dụ một mục glossary (minh họa, không ghi vào YAML của bài):

~~~yaml
term_vi: "Tiền hàng đã xác nhận"
technical_name: confirmed_items_amount
context: Sales.Order
definition: >
  Tổng tiền ròng của các dòng đơn tại thời điểm xác nhận,
  sau khi phân bổ giảm giá xuống dòng.
grain: "Một đơn trong một tenant"
unit: "Đơn vị tiền tệ ở currency_code"
event_time: confirmed_at
source_of_truth: Sales.Order
excluded:
  - "Phí vận chuyển"
  - "Thuế chưa được mô hình trong số đo"
  - "Capture thanh toán và refund sau xác nhận"
owner: "Nhóm Sales"
~~~

Tên **confirmed_items_amount** gợi nghĩa, nhưng **công thức và phần loại trừ** mới giúp người dùng biết đây có phải chỉ số họ cần hay không.

### 3.1. Canonical term và alias

Một hệ legacy gọi bên mua bằng ba tên **client**, **customer**, **buyer**. Quy trình không phải tìm-thay toàn bộ:

1. Liệt kê mỗi tên đang dùng ở đâu và ai là consumer.
2. Kiểm tra chúng thực sự là một đối tượng hay chỉ gần giống nhau.
3. Chọn term canonical **trong context** dựa trên định nghĩa được duyệt.
4. Ghi alias cũ trong glossary, cung cấp mapping tạm thời khi di trú.
5. Ngừng tạo tên mới đồng nghĩa không cần thiết.
6. Chỉ loại bỏ alias khi không còn consumer và không mất dấu vết lịch sử.

**Alias phục vụ chuyển tiếp, không phải lý do giữ vĩnh viễn nhiều cách gọi trái nhau.**

## 4. Từ ngôn ngữ nghiệp vụ đến tên ở các lớp

~~~text
Người dùng nói: "Đơn được xác nhận"

Conceptual:
  Order / OrderConfirmation

Logical:
  Order --contains--> OrderLine
  Order --may be fulfilled by--> Shipment

Physical relational:
  sales.orders, sales.order_lines
  fulfillment.shipments

Java:
  Order, OrderLine, OrderConfirmed

API:
  orderId, confirmedAt, confirmedItemsTotal

Integration event:
  OrderConfirmed, eventId, occurredAt, schemaVersion
~~~

**Không bắt mọi lớp dùng cùng kiểu chữ**. Phải bảo đảm khi hai tên đại diện **cùng sự thật**, mapping giữ ngữ nghĩa. Khi chúng đại diện **hai sự thật khác nhau**, phải có hai tên khác nhau.

### 4.1. Một bộ quy ước minh họa

| Đối tượng | Quy ước | Ví dụ |
| --- | --- | --- |
| PostgreSQL schema | Tên domain/context, lowercase | sales, billing, fulfillment |
| Bảng quan hệ | Số nhiều, snake_case | orders, order_lines |
| Cột | lowercase snake_case | confirmed_at, buyer_account_id |
| Primary key constraint | pk_ + tên bảng | pk_orders |
| Foreign key constraint | fk_ + nguồn + đích | fk_order_lines_order |
| Unique constraint | uq_ + grain/điều kiện | uq_capture_source_id |
| Check constraint | ck_ + bất biến | ck_order_lines_quantity |
| Index | ix_ + bảng + mục tiêu | ix_orders_tenant_confirmed_at |
| Java class/record | PascalCase, số ít | Order, OrderLine |
| Java field | camelCase | confirmedAt |
| JSON field | camelCase theo hợp đồng | orderId, currencyCode |
| Integration event | Sự kiện quá khứ | OrderConfirmed |
| Analytics fact | fact_ + grain/sự kiện | fact_order_line_confirmed |
| Dimension | dim_ + đối tượng/phiên bản | dim_product_variant |
| Aggregate | agg_ + metric/grain | agg_confirmed_orders_daily |

Đây là ví dụ, **không phải tiêu chuẩn duy nhất đúng**. Dự án đã ổn định tên bảng số ít hoặc JSON snake_case có thể giữ quy ước hiện có, nếu nó đủ nhất quán và có tài liệu. Không nên tổ chức một đợt rename diện rộng chỉ vì sở thích cá nhân.

### 4.2. Tiếng Việt và tiếng Anh trong mô hình

Một lựa chọn thực dụng trong môi trường Java/PostgreSQL:

- **Thuật ngữ và giải thích nghiệp vụ bằng tiếng Việt** để người dùng dễ xác nhận nghĩa.
- **Identifier kỹ thuật bằng tiếng Anh ASCII**, ví dụ buyer_account_id, shipment_id, confirmed_at.
- **Bảng ánh xạ VI ↔ EN** trong glossary.
- Viết tắt chỉ khi đã được giải nghĩa và thống nhất như id, sku, api, utc.

Tránh đặt **ma_don**, **order_id**, **idOrder** lẫn lộn trong cùng một schema nếu không có lý do. Nhưng cũng **không gọi recipient là customer** chỉ vì muốn toàn hệ thống dùng cùng chữ.

### 4.3. Những tên cần xem lại

- **data**, **info**, **value**, **object**, **type**, **flag** đứng một mình.
- **status** khi có nhiều workflow.
- **date** khi có nhiều mốc.
- **amount** khi có nhiều loại tiền.
- **id1**, **id2**, **ref_no**, **val** không có ngữ cảnh.
- **new_orders**, **old_customer**, **tmp_v2** tồn tại lâu sau migration.
- Viết tắt không chuẩn như **cust**, **amt**, **prc**, **dt**.

Tên dài không phải tự động tốt. Một tên **on_time_delivered_shipment_count** dài vì nó phải phân biệt kiện giao đúng hạn với đơn có một số kiện giao đúng hạn. Khi quá dài cho giới hạn DB, chọn phần cốt lõi và liên kết data dictionary; không tự rút thành **cnt1**.

### 4.4. Đặc thù identifier của PostgreSQL

PostgreSQL chuyển identifier không đặt nháy kép về lowercase. Dùng quoted MixedCase sẽ khiến code phải giữ đúng case và dấu nháy ở nhiều nơi. **lowercase snake_case** thường ít ma sát hơn.

Bản dựng PostgreSQL thông dụng có giới hạn **63 byte** cho identifier, có thể cắt tên quá dài. Nên chọn tên index/constraint vừa ngắn vừa rõ, kiểm tra giới hạn theo môi trường thực tế. Tránh tên trùng từ khóa SQL dự trữ, tên dễ đụng trong cùng schema và những quy ước phụ thuộc vào ORM tự sinh.

## 5. Tên thực thể và quan hệ phải nói đúng grain

Một bảng tên **payments** không tự nói được mỗi hàng là payment intent, payment attempt, capture hay refund. Chúng có vòng đời và quan hệ khác nhau.

| Tên | Grain hợp lệ khi sử dụng | Khóa/quan hệ gợi ý |
| --- | --- | --- |
| catalog_products | Một nhóm sản phẩm | product_id |
| product_variants | Một biến thể/SKU | variant_id, product_id |
| inventory_balances | Một variant tại một warehouse ở mốc đã chốt | (warehouse_id, variant_id) |
| orders | Một đơn thuộc tenant | (tenant_id, order_id) |
| order_lines | Một dòng đơn đã xác nhận | (tenant_id, order_id, line_no) |
| payment_attempts | Một lần thử thanh toán | attempt_id |
| payment_captures | Một lần capture tiền | capture_id |
| shipments | Một kiện/đợt giao | shipment_id, order_id |
| delivery_attempts | Một lần thử giao | attempt_id, shipment_id |

Nếu **product_id** trước đây là SKU nhưng nay có nghĩa **nhóm sản phẩm**, không thể cập nhật toàn bộ dòng đơn lịch sử về ID nhóm rồi làm mất màu/size. **Tên thay đổi theo grain phải được xem là thay đổi mô hình**, không chỉ đổi chuỗi.

### 5.1. Tên của bảng nhiều-nhiều phải chọn đúng cấp

Một dòng bán chịu hai chương trình khuyến mãi. Bảng **order_line_promotions** có grain một **(tenant, order, line, promotion)**. Nếu dùng **order_promotions**, người đọc có thể lầm tưởng một promotion áp lên cả đơn.

Nếu bảng còn lưu **allocated_discount_amount**, phải có quy tắc rằng tổng phân bổ về dòng bằng phần giảm giá đúng. Không JOIN bảng bridge rồi SUM tiền dòng để “doanh thu theo promotion” khi một dòng xuất hiện hai lần, trừ khi đã có hợp đồng phân bổ/đếm rõ.

### 5.2. Không sửa cardinality bằng đổi tên cột

Ban đầu Orders có cột **shipment_id**, vì mỗi đơn một shipment. Về sau đơn có nhiều shipment, cách đúng là mô hình quan hệ **Order 1:N Shipment**, không đơn thuần đổi thành **shipment_ids** rồi nhồi danh sách vào một cột relational. Tên phải đi cùng thay đổi thực thể và constraint.

## 6. Đặt tên khóa: phân biệt ID vật lý, công khai và nguồn ngoài

| Tên | Nghĩa cụ thể |
| --- | --- |
| **order_pk** | Khóa hàng nội bộ nếu dùng một surrogate riêng |
| **order_id** | Định danh đơn trong phạm vi đã định |
| **public_order_id** | Định danh được công bố qua API/event |
| **order_number** | Mã hiển thị, có thể cấp theo tenant/năm |
| **buyer_account_id** | Tài khoản đặt đơn |
| **source_system** | Nguồn cấp định danh từ bên ngoài |
| **source_order_id** | ID ở nguồn, chỉ duy nhất trong scope nguồn đã công bố |
| **processor_capture_id** | ID capture do bộ xử lý thanh toán cấp |
| **tracking_number** | Mã vận đơn, cần xem scope carrier |

Một hệ thống có thể chọn order_id chính là public UUID, khi đó không cần thêm public_order_id. **Không tạo nhiều ID chỉ vì khuôn mẫu**; chỉ tách khi khác nguồn, phạm vi hoặc vòng đời.

**UUID không tự cấp quyền truy cập.** Người gọi biết orderId vẫn phải chứng minh có quyền xem object theo tenant và chủ sở hữu. Nếu không, một định danh công khai khó đoán vẫn có thể bị lộ qua log hoặc URL.

### 6.1. Composite keys và tenant

Một order_id có thể chỉ duy nhất trong tenant. Khi đó khóa nghiệp vụ là **(tenant_id, order_id)**; FK từ dòng đơn nên mang cả hai trường để tránh tham chiếu nhầm tenant. Tên field không tự diễn đạt hết phạm vi nên **constraint và data dictionary** phải bảo vệ.

Nếu một ID từ đối tác có thể tái sử dụng theo năm, UNIQUE(source_order_id) là sai. Cần thêm **source_system, tenant hoặc effective period** tùy hợp đồng nguồn.

## 7. Thời gian: hậu tố phải thể hiện ý nghĩa

| Tên | Giá trị biểu diễn | Kiểu gợi ý |
| --- | --- | --- |
| **created_at** | Khi record được tạo trong hệ lưu trữ | TIMESTAMPTZ |
| **confirmed_at** | Khi đơn được xác nhận | TIMESTAMPTZ |
| **captured_at** | Khi capture thành công theo Payment | TIMESTAMPTZ |
| **shipped_at** | Khi kiện bàn giao vận chuyển | TIMESTAMPTZ |
| **delivered_at** | Khi kiện giao thành công | TIMESTAMPTZ |
| **observed_at** | Khi sensor đo ở nguồn | TIMESTAMPTZ |
| **received_at** | Khi hệ thống nhận message | TIMESTAMPTZ |
| **loaded_at** | Khi ETL nạp kho | TIMESTAMPTZ |
| **business_date** | Ngày nghiệp vụ theo timezone và quy tắc | DATE |
| **effective_from / effective_to** | Khoảng hiệu lực của dimension version | TIMESTAMPTZ hoặc DATE theo hợp đồng |
| **processing_duration_ms** | Thời lượng xử lý, không phải thời điểm | BIGINT/NUMERIC |

**created_at không đồng nghĩa occurred_at.** Một đơn cũ được nhập hôm nay có **confirmed_at** của tháng trước và **loaded_at** hôm nay. Một event có **observed_at** 23:59 UTC, **received_at** 00:04 UTC ngày hôm sau; báo cáo theo ngày xảy ra không được lấy ngày nhận.

Đối với **business_date**, phải nói rõ múi giờ của nơi nào. Một thời điểm tuyệt đối có thể thuộc hai ngày khác nhau tại hai múi giờ.

### 7.1. Snapshot tại giao dịch khác giá trị hiện tại

- **current_list_price**: giá niêm yết hiện hành.
- **unit_price_at_confirmation**: giá đã chốt trên dòng khi xác nhận.
- **shipping_address_at_confirmation**: địa chỉ đã được chấp nhận lúc xác nhận.
- **current_default_address**: địa chỉ mặc định hiện tại.
- **customer_segment_at_purchase**: phân khúc theo thời điểm mua.
- **current_customer_segment**: phân khúc hiện hành.

Các trường này không nhất thiết phải “đồng bộ cho giống nhau”. Khi Catalog đổi giá, **unit_price_at_confirmation** của chứng từ cũ vẫn giữ nghĩa lịch sử. Khi khách đổi địa chỉ mặc định, không tự viết lại người nhận của kiện đã bàn giao.

### 7.2. NULL, effective interval và thời gian kết thúc

Một trường **delivered_at = NULL** có thể biểu diễn “chưa giao” theo hợp đồng, không tự đại diện cả trạng thái UNKNOWN và FAILED. Nếu cần phân biệt, dùng state và quy tắc rõ.

Với SCD Type 2, dùng khoảng nửa mở **[effective_from, effective_to)**. Một phiên bản có hiệu lực tại from nhưng không tại to; tránh BETWEEN hai cận đóng làm một event ở thời điểm giao biên khớp hai version.

## 8. Tiền, số lượng, tỷ lệ và sự cộng gộp

| Tên | Grain/ý nghĩa | Tránh nhầm |
| --- | --- | --- |
| **unit_price_at_confirmation** | Giá một đơn vị trên dòng đã chốt | current_list_price |
| **line_gross_amount** | Tổng dòng trước giảm | Tổng đơn |
| **line_discount_amount** | Giảm giá phân bổ xuống dòng | Giảm giá cấp đơn chưa phân bổ |
| **line_net_amount** | Tiền ròng của dòng sau giảm | Tiền đã thu |
| **confirmed_items_amount** | Tổng tiền hàng trên một đơn đã xác nhận | Captured amount / revenue |
| **captured_amount** | Tiền thu ở grain một capture | Payment attempt amount |
| **refunded_amount** | Tiền hoàn ở grain một refund | Giá trị đơn gốc |
| **on_hand_quantity** | Tồn kho tại thời điểm được chụp | Tổng dòng nhập/xuất |
| **distinct_buyer_count** | Số buyer khác nhau trong tập được xét | Tổng distinct của các nhóm |
| **average_unit_price** | Tổng amount chia tổng quantity | AVG các AVG nhóm |

Một cột NUMERIC(18,2) tên **amount** nhưng không gắn **currency_code** vẫn dễ bị SUM VND với USD. Với tỷ lệ như **conversion_rate**, cần lưu tử số và mẫu số hoặc trạng thái hợp nhất phù hợp; không cộng phần trăm. Với gauge hoặc tồn kho, không SUM xuyên thời gian như với lượng giao dịch.

**Revenue** chỉ nên dùng khi tổ chức đã định nghĩa rõ quy tắc ghi nhận. Không coi mọi SUM(order.amount) là doanh thu.

### 8.1. Tên count cần phù hợp với thứ COUNT đếm

Một Order có ba OrderLine:

- **order_line_count = 3**.
- **distinct_order_count = 1**.
- **sold_unit_quantity** có thể bằng tổng quantity nếu đơn vị tương thích.

COUNT(*) sau JOIN order_lines **đếm dòng**, không phải số đơn. Dù đặt alias **order_count**, số vẫn sai. Cần thay phép truy vấn hoặc phân nhóm trước, không chỉ thay tên.

### 8.2. Số đo phải thể hiện đơn vị

Các tên **distance_meters**, **duration_seconds**, **temperature_celsius**, **weight_kg**, **memory_bytes** giúp hạn chế nhầm đơn vị. Nếu hệ cho phép kg/hộp/chiếc, dùng **quantity + unit_code** hoặc đơn vị quy đổi được tài liệu hóa; đừng gọi mọi lượng là quantity_pieces.

## 9. Trạng thái và Boolean: một cột không gánh nhiều vòng đời

Một đơn có thể đồng thời:

- **order_state_code = CONFIRMED**.
- **payment_state_code = PARTIALLY_CAPTURED**.
- **fulfillment_state_code = NOT_STARTED**.
- **fraud_review_state_code = APPROVED**.

Gộp tất cả thành **status = PROCESSING** làm mất thông tin và dễ tạo trạng thái không hợp lệ. Đặt status theo owner của vòng đời, không theo tên thuận tiện của một response.

Boolean **is_active** cũng thường mơ hồ: tài khoản đã xác minh email, không bị khóa, có đơn trong 90 ngày hay còn hợp đồng? Có thể dùng **email_verification_state**, **account_access_state** và **last_order_at** nếu đó thực sự là các sự thật độc lập.

Một tên như **is_delivered** được dẫn xuất từ **delivered_at** hoặc một event có thẩm quyền không nên trở thành nguồn chuẩn thứ hai được cập nhật độc lập. Nếu cần read projection, ghi rõ đây là thuộc tính dẫn xuất, có owner và độ tươi.

## 10. Ví dụ PostgreSQL: mô hình Order có tên và constraint nhất quán

Giả định:

- Một hàng **sales.orders** là một đơn đã xác nhận trong một tenant; sau đó trạng thái hiện hành có thể chuyển thành CANCELLED.
- Một hàng **sales.order_lines** là một dòng của đơn, định danh bằng **(tenant_id, order_id, line_no)**.
- **confirmed_items_amount** là tổng **line_net_amount** của các dòng, sau giảm giá phân bổ; ví dụ chưa tính thuế và phí vận chuyển.
- Mỗi Order có **currency_code** thống nhất cho các dòng. Buyer account không đồng nghĩa người nhận.

~~~sql
CREATE SCHEMA sales;

CREATE TABLE sales.orders (
    tenant_id BIGINT NOT NULL,
    order_id UUID NOT NULL,
    buyer_account_id UUID NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    order_state_code TEXT NOT NULL,
    confirmed_items_amount NUMERIC(18, 2) NOT NULL,
    currency_code CHAR(3) NOT NULL,

    CONSTRAINT pk_orders
        PRIMARY KEY (tenant_id, order_id),
    CONSTRAINT ck_orders_state
        CHECK (order_state_code IN ('CONFIRMED', 'CANCELLED')),
    CONSTRAINT ck_orders_items_nonnegative
        CHECK (confirmed_items_amount >= 0)
);

CREATE TABLE sales.order_lines (
    tenant_id BIGINT NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    product_variant_id UUID NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL,
    line_discount_amount NUMERIC(18, 2) NOT NULL,
    line_gross_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price_at_confirmation
        ) STORED,
    line_net_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price_at_confirmation
            - line_discount_amount
        ) STORED,

    CONSTRAINT pk_order_lines
        PRIMARY KEY (tenant_id, order_id, line_no),
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.orders(tenant_id, order_id),
    CONSTRAINT ck_order_lines_line_no CHECK (line_no > 0),
    CONSTRAINT ck_order_lines_quantity CHECK (quantity > 0),
    CONSTRAINT ck_order_lines_price
        CHECK (unit_price_at_confirmation >= 0),
    CONSTRAINT ck_order_lines_discount_range
        CHECK (
            line_discount_amount >= 0
            AND line_discount_amount
              <= quantity * unit_price_at_confirmation
        )
);

CREATE INDEX ix_orders_tenant_confirmed_at
    ON sales.orders (tenant_id, confirmed_at DESC);

CREATE INDEX ix_order_lines_product_variant
    ON sales.order_lines (tenant_id, product_variant_id);
~~~

Ý nghĩa trong thiết kế:

- **sales** là context sở hữu Order, không phải schema chung kiểu tables_v2.
- **orders** và **order_lines** phân biệt grain.
- FK gồm **tenant_id** bảo vệ liên kết đúng tenant ở database.
- **buyer_account_id** không bị hiểu thành recipient.
- **unit_price_at_confirmation** là snapshot, không lấy giá Catalog hiện hành.
- **line_gross_amount** và **line_net_amount** là giá trị dẫn xuất của **một dòng**, không phải tổng đơn.
- **confirmed_items_amount** ở header có grain một đơn; phép đối chiếu với tổng dòng là invariant liên hàng, không tự bảo đảm bằng CHECK trên Orders.
- Tên constraint mang thông tin về nguyên nhân lỗi; tên index cho biết truy vấn dự kiến.

**Giới hạn:** ví dụ chưa tạo bảng buyer_accounts và product_variants, nên các UUID ấy cần được xác minh bằng nguồn/hợp đồng riêng hoặc FK bổ sung trong hệ thực. Không khẳng định FK có đủ khi một bảng khác context chưa được định nghĩa. PostgreSQL hỗ trợ generated stored column trong các phiên bản phù hợp; nếu sử dụng bản cũ hoặc engine khác phải kiểm tra khả năng hỗ trợ.

### 10.1. Data dictionary ngắn bên cạnh SQL

| Field | Định nghĩa | Chủ sở hữu và quy tắc |
| --- | --- | --- |
| **tenant_id** | Phạm vi doanh nghiệp/tenant | Scope của PK/FK |
| **order_id** | ID ổn định của đơn trong tenant | Sales.Order |
| **buyer_account_id** | Tài khoản đặt đơn | Không là recipient |
| **confirmed_at** | Thời điểm xác nhận | Không dùng loaded_at thay thế |
| **order_state_code** | Trạng thái hiện tại của Order | Có tập enum được phê duyệt |
| **confirmed_items_amount** | Tổng tiền hàng đã xác nhận | Currency theo currency_code, không phải tiền đã thu |
| **product_variant_id** | Biến thể hàng được mua | Theo định danh Catalog |
| **unit_price_at_confirmation** | Giá lịch sử đã chốt | Không đồng bộ theo giá hiện hành |
| **line_discount_amount** | Giảm giá phân bổ cho dòng | Không vượt line_gross_amount |
| **line_net_amount** | Gross trừ discount tại dòng | Không tự gồm thuế/phí |

Có thể dùng **COMMENT ON** trong PostgreSQL để giữ mô tả gần schema:

~~~sql
COMMENT ON COLUMN sales.orders.confirmed_items_amount IS
    'Tong tien hang tai xac nhan, sau giam gia dong; chua gom thue va phi van chuyen.';

COMMENT ON COLUMN sales.orders.buyer_account_id IS
    'Tai khoan dat don; khong dong nghia nguoi nhan.';

COMMENT ON COLUMN sales.order_lines.unit_price_at_confirmation IS
    'Don gia da chot luc xac nhan; khong cap nhat theo Catalog hien hanh.';
~~~

Ví dụ viết comment không dấu để tương thích một số pipeline cũ; môi trường PostgreSQL UTF-8 có thể lưu tiếng Việt có dấu bình thường. COMMENT không thay glossary có owner, lịch sử thay đổi và công thức.

### 10.2. Kiểm chứng tên và grain bằng truy vấn

Truy vấn ở **grain một đơn**:

~~~sql
SELECT
    tenant_id,
    currency_code,
    COUNT(*) AS currently_confirmed_order_count,
    SUM(confirmed_items_amount) AS confirmed_items_amount
FROM sales.orders
WHERE order_state_code = 'CONFIRMED'
  AND confirmed_at >= $1::TIMESTAMPTZ
  AND confirmed_at <  $2::TIMESTAMPTZ
GROUP BY tenant_id, currency_code;
~~~

Tên **currently_confirmed_order_count** nhắc rõ điều kiện: đơn đã từng được xác nhận nhưng **hiện đang CANCELLED** không nằm trong nhóm. Nếu cần đếm **mọi đơn được xác nhận trong kỳ bất kể trạng thái hiện hành**, phải bỏ lọc trạng thái hoặc dùng fact sự kiện và đặt tên metric phù hợp.

Truy vấn ở **grain dòng đơn**:

~~~sql
SELECT
    o.tenant_id,
    o.currency_code,
    COUNT(*) AS order_line_count,
    SUM(l.line_net_amount) AS confirmed_lines_net_amount
FROM sales.orders AS o
JOIN sales.order_lines AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
WHERE o.confirmed_at >= $1::TIMESTAMPTZ
  AND o.confirmed_at <  $2::TIMESTAMPTZ
GROUP BY o.tenant_id, o.currency_code;
~~~

**Không SUM(o.confirmed_items_amount) sau JOIN dòng**, vì header amount bị lặp theo số dòng. Quy tắc này không được sửa chỉ bằng đổi alias COUNT(*) thành order_count.

### 10.3. Đối soát ngữ nghĩa của header và dòng

~~~sql
WITH lines_by_order AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS line_count,
        SUM(line_net_amount) AS lines_net_amount
    FROM sales.order_lines
    GROUP BY tenant_id, order_id
)
SELECT
    o.tenant_id,
    o.order_id,
    o.confirmed_items_amount,
    l.line_count,
    l.lines_net_amount
FROM sales.orders AS o
LEFT JOIN lines_by_order AS l
    ON l.tenant_id = o.tenant_id
   AND l.order_id = o.order_id
WHERE l.order_id IS NULL
   OR o.confirmed_items_amount
        IS DISTINCT FROM l.lines_net_amount;
~~~

Ví dụ giả định mọi đơn có ít nhất một dòng và tổng header bằng tổng net dòng. Nếu hệ thực có giảm giá cấp đơn chưa phân bổ hoặc thuế/phí tại header, phải **điều chỉnh hợp đồng và phép đối soát**, không dùng một tên hấp dẫn để che công thức khác.

Một tên đáng tin cần có **nghĩa được duyệt + grain đúng + ràng buộc/đối soát + kiểm thử**, không chỉ có khả năng đọc trôi chảy.

## 11. Tên trong API và event: giữ nghĩa, không lộ cấu trúc vật lý

Một API đọc đơn có thể công bố:

~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "CONFIRMED",
  "confirmedAt": "2026-11-22T01:30:00Z",
  "confirmedItemsTotal": {
    "amount": "310000.00",
    "currency": "VND"
  }
}
~~~

Ở đây **confirmedItemsTotal** tương ứng với **confirmed_items_amount + currency_code** trong nguồn. JSON dùng camelCase trong khi PostgreSQL dùng snake_case; **hình thức khác nhưng ngữ nghĩa phải giống**.

Một số quy tắc:

- **orderId** là định danh công khai theo hợp đồng; không cần phát **order_pk** hoặc khóa FK vật lý nếu consumer không dùng.
- **status** trong API có thể là trạng thái công khai đã ánh xạ; không phát mọi enum nội bộ như PICKING, WAREHOUSE_RECHECK chỉ vì cột source chứa chúng.
- **amount** là chuỗi decimal trong ví dụ để giữ chữ số thập phân; quy tắc precision, scale và làm tròn phải được công bố.
- **confirmedAt** có timezone rõ; không lấy updated_at thay thế.
- Không thêm **buyerAccountId, email, phone hoặc risk_score** chỉ vì những cột ấy tồn tại ở nguồn; phải xác định quyền và nhu cầu của consumer.

API là **hợp đồng có vòng đời dài hơn tên cột SQL**. Khi đổi cách lưu sang document store, client không nhất thiết biết thay đổi nếu tên public và nghĩa được giữ.

### 11.1. Tên sự kiện theo hành vi đã xảy ra

~~~json
{
  "eventId": "c3b26b87-594e-4a98-9ad2-52b8d2ddf04f",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "aggregateVersion": 4,
  "occurredAt": "2026-11-22T01:30:00Z"
}
~~~

Tên **OrderConfirmed** nói rằng Order đã đạt mốc xác nhận nghiệp vụ; nó khác **OrderUpdated** vốn thường chỉ báo một row bị cập nhật. Phải phân biệt:

| Field | Định nghĩa |
| --- | --- |
| **eventId** | ID duy nhất của sự kiện/message để chống xử lý trùng |
| **eventType** | Tên hành vi nghiệp vụ đã xảy ra |
| **schemaVersion** | Version cấu trúc/hợp đồng event |
| **aggregateVersion** | Version trạng thái đối tượng nguồn |
| **occurredAt** | Thời điểm hành vi nghiệp vụ xảy ra |
| **publishedAt/receivedAt** | Thời điểm truyền/nhận trên hạ tầng, nếu cần |

**OrderConfirmed** không có nghĩa Payment đã capture thành công. Event **PaymentCaptured** thuộc miền Payment khi capture thực sự thành công. Một đơn có thể thanh toán nhiều lần; đừng phát một event có tên **OrderPaid** chỉ vì nhận một capture bất kỳ nếu tổng tiền chưa được thanh toán đủ.

Tên event theo quá khứ phải đi cùng cơ chế ghi đáng tin: không gửi sự kiện xác nhận trước khi transaction thực sự commit rồi sau đó rollback. Có thể dùng transactional outbox và consumer idempotent khi tích hợp bất đồng bộ.

### 11.2. Mapping giữa bounded contexts phải được ghi rõ

~~~text
Sales.Order.buyerAccountId
    -> Billing.PaymentIntent.payerRef
    -> Fulfillment.Shipment.recipientRef
~~~

Đây là **các ID có thể có quan hệ qua quy trình**, không phải bằng chứng rằng chúng bằng nhau. Bên trả tiền có thể khác người đặt; người nhận có thể là bên thứ ba.

Một **anti-corruption layer** giúp chuyển các khái niệm và kiểm tra điều kiện nghiệp vụ. Nếu Payment đổi **SETTLED** thành các trạng thái chi tiết hơn, Sales không nên tự sao chép enum Payment vào order_state_code mà không duyệt ý nghĩa.

## 12. Đặt tên trong document, graph, time-series và analytics

Một hệ thống có thể dùng nhiều mô hình lưu trữ. **Quy ước ký tự có thể khác**, nhưng nghĩa và phạm vi của thực thể phải nhất quán hoặc có mapping được ghi rõ.

### 12.1. Document model: tên nhúng phải giữ grain

Một document Order:

~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "confirmedAt": "2026-11-22T01:30:00Z",
  "currencyCode": "VND",
  "items": [
    {
      "lineNo": 1,
      "productVariantId": "d0b8cb27-84c2-4ca4-985d-33f1705bd6d3",
      "quantity": 2,
      "unitPriceAtConfirmation": "150000.00",
      "lineDiscountAmount": "10000.00"
    }
  ]
}
~~~

Document có grain **một Order**, nhưng mỗi phần tử **items[]** có grain **một dòng đơn**. Nếu thêm **paymentAttempts[]** và **shipments[]**, không được mặc nhiên coi mọi phần tử thuộc cùng một loại sự kiện hoặc cùng quyền truy cập.

Tên **unitPriceAtConfirmation** vẫn là snapshot dù document được lưu chung với thông tin hiện hành khác. Nếu database dùng trường kỹ thuật **_id**, API không nhất thiết phải lộ _id cho client.

### 12.2. Graph: động từ trên cạnh phải mô tả quan hệ thật

~~~text
(:BuyerAccount)-[:PLACED]->(:Order)
(:Order)-[:CONTAINS_LINE]->(:OrderLine)
(:Order)-[:FULFILLED_BY]->(:Shipment)
(:Shipment)-[:HAS_ATTEMPT]->(:DeliveryAttempt)
~~~

Nhãn cạnh **RELATED_TO** không nói được hướng, chủ thể, thời điểm và nghĩa. Nếu muốn phân tích **một sự kiện mua**, không thể giả định một cạnh BuyerAccount–PURCHASED–Product chứa đầy đủ số lần mua khi nhiều lần mua cùng một sản phẩm. Có thể cần node **OrderLine** hoặc **PurchaseEvent** với ID/time và số đo phù hợp.

Tên cạnh theo graph cũng phải có tài liệu về cardinality, chiều duyệt, khoảng hiệu lực và quyền; đổi nhãn cạnh có thể tác động traversal của consumer.

### 12.3. Analytics: tên fact/dimension phải kèm grain

| Bảng | Grain | Điểm cần ghi rõ |
| --- | --- | --- |
| **fact_order_line_confirmed** | Một dòng đơn đã chốt | line_net_amount có currency; Order có thể nhiều dòng |
| **fact_payment_capture** | Một capture | captured_amount không phải confirmed_items_amount |
| **dim_product_variant** | Một biến thể hoặc một version lịch sử | variant_key có thể là surrogate dimension |
| **dim_customer_version** | Một phiên bản thuộc tính khách trong khoảng hiệu lực | effective_from/effective_to |
| **fact_inventory_eod** | Một variant × warehouse × business_date | on_hand_quantity không SUM xuyên ngày |
| **agg_confirmed_orders_daily** | Ngày × currency × tập chiều đã chọn | metric, lọc trạng thái, watermark |

Tiền tố **fact_**, **dim_**, **agg_** hữu ích cho warehouse. Không phải mọi bảng OLTP đều cần tiền tố này.

Với SCD Type 2, **customer_key** có thể định danh **một version dimension**, khác **customer_id** định danh một customer nghiệp vụ. Nếu gọi cả hai là customer_id, phép JOIN có thể lặp nhiều phiên bản và làm doanh thu tăng giả. Glossary phải ghi rõ hai lớp khóa.

### 12.4. Time-series: tên thống kê phải nói rõ loại trung bình

Trong telemetry:

- **observed_at**: thời điểm thiết bị đo.
- **received_at**: thời điểm server nhận.
- **bucket_start**: cận trái bucket, với quy tắc [start,end).
- **sample_count**: số mẫu đủ điều kiện.
- **temperature_sum_celsius**: tổng nhiệt độ của các mẫu theo đơn vị đã chọn.
- **sample_mean_temperature_celsius**: trung bình theo số mẫu.
- **time_weighted_mean_temperature_celsius**: chỉ dùng khi phép tính thời gian được thiết kế đúng.
- **max_temperature_celsius**: cực trị trong khoảng, không phải thời lượng vượt ngưỡng.

AVG của những AVG bucket 5 phút có thể sai nếu mỗi bucket có số mẫu khác nhau. Tên phải đi kèm phép hợp nhất: lưu **sum + count** nếu cần average theo mẫu ở cấp giờ.

## 13. Đổi tên là một thay đổi hợp đồng, không chỉ tìm và thay chuỗi

Một hệ Sales cũ có **customer_id**, nhưng thực chất đây là ID **buyer account**, không phải ID người thật hoặc người nhận. Nhóm muốn đổi thành **buyer_account_id**.

### 13.1. Các câu hỏi trước migration

- Hai khái niệm có đúng là một-một trong dữ liệu lịch sử không?
- Source cũ có **customer_id** duy nhất trong tenant hay trên toàn hệ?
- API, event, CSV xuất cho đối tác, cache và data warehouse đang dùng tên nào?
- ORM, stored procedure, trigger và hệ thống báo cáo có phụ thuộc tên cũ không?
- Cần giữ legacy alias bao lâu?
- Có consumer chỉ đọc customer_id nhưng kỳ thực đang dùng ID **person**, không phải account không?

**Nếu customer_id cũ là một person còn buyer_account_id mới là một account, đây không phải rename tương đương.** Phải thiết kế quan hệ person–account và mapping có thể xác minh trước.

### 13.2. Quy trình expand – migrate – contract

1. **Chốt glossary và ADR** cho tên cũ/mới, scope và source of truth.
2. **Expand**: thêm trường mới hoặc view/DTO tương thích, chưa bỏ tên cũ.
3. **Backfill**: ánh xạ trên dữ liệu cũ bằng nguồn có thẩm quyền, lưu checkpoint và mismatch.
4. **Chuyển đường ghi**: tạo dữ liệu mới theo một mapping canonical, tránh hai cột được cập nhật độc lập.
5. **Shadow read**: so kết quả từ cách đọc cũ và mới; kiểm tra tenant/authorization.
6. **Cutover**: chuyển consumer theo nhóm, theo dõi fallback và lỗi.
7. **Contract**: chỉ loại tên cũ sau khi không còn consumer/đường ghi và có phương án rollback/forward-fix.

Giả định bảng **legacy_orders** có customer_id UUID thực sự mang nghĩa account ID:

~~~sql
ALTER TABLE legacy_orders
ADD COLUMN buyer_account_id UUID;

-- Chỉ hợp lệ nếu đã xác minh ý nghĩa và mapping 1:1.
UPDATE legacy_orders
SET buyer_account_id = customer_id
WHERE buyer_account_id IS NULL;

-- Đối chiếu cột mới/cũ trong giai đoạn tương thích.
SELECT order_id, customer_id, buyer_account_id
FROM legacy_orders
WHERE buyer_account_id IS DISTINCT FROM customer_id;
~~~

Đây là **ví dụ cho một bảng legacy giả định**, không thuộc DDL sales.orders ở phần 10. Chạy thực tế cần batch, checkpoint, quản lý ghi đồng thời và kiểm tra kiểu dữ liệu/mapping. Một lần backfill không tự bảo đảm bản ghi mới từ ứng dụng cũ tiếp tục có buyer_account_id.

Nếu có hai đường ghi, chỉ nên có **một nguồn quyết định giá trị**; cột còn lại được dẫn xuất/đối soát trong thời gian chuyển tiếp. Trigger ghi hai chiều không có quy tắc có thể tạo vòng hoặc che xung đột.

### 13.3. Rename API có thể breaking dù giá trị không đổi

JSON v1 trả **customerId**, đổi thành **buyerAccountId** có thể làm client không deserialize được. Tương tự, đổi enum public **PROCESSING** thành **PICKING** là thay đổi nghĩa và cấu trúc.

Có thể dùng API v2, mapping có version và thời hạn hỗ trợ v1; thực hiện contract test với consumer thực. Đừng mặc định thêm một field luôn tương thích: client dùng validator hoặc deserializer nghiêm ngặt có thể từ chối trường lạ.

Không nên đổi public ID chỉ vì database chuyển từ VARCHAR sang BIGINT hoặc UUID. **Định danh công khai ổn định** có thể tách khỏi khóa vật lý.

## 14. Những tên liên quan bảo vệ dữ liệu cần đặc biệt rõ

Một cột **user_info** có thể chứa email, phone, địa chỉ, ghi chú hoặc thông tin nhạy cảm, làm khó phân quyền và retention. Nên tách theo **ý nghĩa nghiệp vụ**, ví dụ:

| Tên | Ngữ nghĩa | Ranh giới |
| --- | --- | --- |
| **buyer_account_id** | Định danh account đặt đơn | Không tự là thông tin liên hệ |
| **recipient_phone_at_handover** | Điện thoại người nhận ở mốc bàn giao | Chỉ bên giao được ủy quyền |
| **current_customer_email** | Email hiện hành theo Customer | Có thể thay đổi, cần quyền tra |
| **shipping_address_at_confirmation** | Địa chỉ chốt của giao dịch | Snapshot có chính sách lưu giữ riêng |
| **fraud_review_score** | Điểm phân loại rủi ro nội bộ | Không công bố mặc định |
| **public_order_id** | ID được phép trao đổi trong hợp đồng | Không thay authorization |
| **subject_ref** | Mã liên kết giả danh | Vẫn có nguy cơ tái định danh |

Một tên chứa **_hash** không chứng minh dữ liệu đã ẩn danh. Hash email không khóa có thể bị dò từ danh sách email; token hoặc UUID ổn định vẫn có thể liên kết hành vi qua nhiều hệ. **Tên bảo vệ phải phản ánh đúng cơ chế và phạm vi**, đi kèm quyền, mã hóa, audit và retention.

### 14.1. Tránh xuất nguyên entity

Một serializer trực tiếp trả mọi cột SQL có thể lộ trường mới như risk_score hoặc agent_note. Public API phải dùng DTO/mapper allowlist theo nhu cầu.

Naming review nên hỏi: **consumer có thật sự cần trường này, tại thời điểm nào, với quyền nào?** Việc trường có tên đẹp không làm nó đủ điều kiện công bố.

## 15. Quy trình review tên và chất lượng tài liệu

### 15.1. Lint cú pháp có thể tự động hóa

Ví dụ một pattern cho identifier PostgreSQL:

~~~text
^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$

Tên hợp khuôn:
  order_id
  confirmed_at
  line_net_amount
  source_order_id

Cần xem lại:
  OrderID
  order--id
  order__id
  123status
  value1
~~~

Regex chỉ kiểm tra **hình thức**, không biết **amount** là tiền gì, một hàng đếm gì, hay customer và recipient có khác nhau. Đừng đồng nhất “lint pass” với “semantic pass”.

### 15.2. Checklist review theo trường mới

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Từ này do người nghiệp vụ dùng ở context nào? | Bảng glossary và owner |
| Một hàng đại diện điều gì? | Tuyên bố grain |
| Tên có đè lên term khác không? | So với glossary hiện có |
| ID duy nhất ở scope nào? | PK/UK, quy tắc tenant/source |
| Ai quyết định giá trị? | Source of truth |
| Trường đúng ở thời điểm nào? | Current, confirmed_at, effective time |
| Đơn vị và cách làm tròn? | currency, scale, unit |
| Null có nghĩa gì? | Required/unknown/not-yet/withheld |
| Field có nhạy cảm không? | Phân loại PII, quyền và retention |
| API/event/analytics có dùng tên này? | Inventory consumer/version |
| Có kiểm thử xác minh nghĩa? | Constraint, reconciliation, contract test |

Nên có người sở hữu glossary trong từng bounded context. Một hội đồng tên gọi không nên ép ngôn ngữ toàn cục mà không hiểu quy trình nghiệp vụ. Khi hai nhóm khác nhau thực sự sở hữu hai nghĩa, cần **mapping**, không phải đồng nhất cưỡng ép.

### 15.3. Contract test và data quality test

Các test hữu ích:

- **Schema test:** tên field/API đúng version; không phát cột ngoài allowlist.
- **Enum test:** mọi trạng thái nội bộ có mapping public hợp lệ, không lộ enum chưa duyệt.
- **Time test:** confirmed_at, captured_at, received_at không bị hoán đổi; timezone được giữ.
- **Money test:** currency và scale nhất quán, không mất độ chính xác khi serialize.
- **Grain test:** UNIQUE ngăn trùng dòng/đơn; các JOIN không nhân số đo.
- **Snapshot test:** đổi giá Catalog không sửa unit_price_at_confirmation.
- **Metric test:** cách lọc/trạng thái phù hợp với tên count/amount.
- **Security test:** ID công khai không bỏ qua object authorization; PII không xuất nhầm.
- **Migration test:** alias/tên mới đối chiếu đúng trong thời gian chuyển tiếp.
- **Rebuild test:** read projection hoặc bảng dẫn xuất được tính lại từ nguồn đúng mà không đổi nghĩa.

**Đúng tên nhưng sai dữ liệu vẫn là lỗi**, và một test chỉ xác minh JSON có field amount không thể chứng minh amount thực sự đến từ capture thành công thay vì payment attempt.

## 16. Ví dụ từ đầu đến cuối: “số kiện giao đúng hạn”

Yêu cầu:

> “Báo cáo số đơn giao đúng hạn mỗi ngày theo đơn vị vận chuyển.”

Trước khi đặt tên metric, phải làm rõ:

- Đếm **Order** hay **Shipment**? Một Order có thể có nhiều kiện.
- “Đã giao” là giao thành công, có chứng cứ hay chỉ đã bàn giao carrier?
- “Đúng hạn” tính theo **promised_delivery_at** hay hết ngày giao dự kiến?
- Nhóm theo ngày giao hay ngày hẹn? Timezone nào?
- Một shipment có nhiều delivery attempt thì đếm thế nào?
- Nếu carrier thay đổi giữa chừng, bên nào chịu trách nhiệm trong báo cáo?

Giả định người dùng muốn **số shipment đã giao thành công không muộn hơn promised_delivery_at**, theo ngày giao ở múi giờ Việt Nam.

### 16.1. Grain và tên

~~~text
fulfillment.shipments:
  tenant_id
  shipment_id
  order_id
  carrier_id
  promised_delivery_at
  delivered_at
  delivery_state_code

Metric:
  on_time_delivered_shipment_count

Grouping:
  delivered_business_date
  carrier_id
~~~

**Không gọi metric này là on_time_order_count**, vì hai shipment của một đơn đều đúng hạn sẽ đóng góp hai lần. Nếu muốn đếm **đơn được giao đủ mọi shipment đúng hạn**, phải thiết kế metric khác có điều kiện coverage.

### 16.2. DDL và ràng buộc

~~~sql
CREATE SCHEMA fulfillment;

CREATE TABLE fulfillment.shipments (
    tenant_id BIGINT NOT NULL,
    shipment_id UUID NOT NULL,
    order_id UUID NOT NULL,
    carrier_id UUID NOT NULL,
    promised_delivery_at TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ,
    delivery_state_code TEXT NOT NULL,
    CONSTRAINT pk_shipments
        PRIMARY KEY (tenant_id, shipment_id),
    CONSTRAINT fk_shipments_order
        FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.orders(tenant_id, order_id),
    CONSTRAINT ck_shipments_state
        CHECK (delivery_state_code IN (
            'CREATED', 'IN_TRANSIT', 'DELIVERED', 'FAILED'
        ))
);

CREATE INDEX ix_shipments_delivered_carrier
    ON fulfillment.shipments(tenant_id, delivered_at, carrier_id);
~~~

Nếu hệ có trạng thái **RETURNED** sau khi từng DELIVERED, cần lưu **lịch sử sự kiện giao** thay vì giả định state hiện hành luôn phản ánh đầy đủ mốc đã giao. **delivered_at** có thể cần giữ sau khi hoàn hàng; đừng tạo CHECK ép mọi state khác DELIVERED phải NULL mà không hiểu vòng đời.

### 16.3. Truy vấn và các phép kiểm chứng

~~~sql
SELECT
    s.tenant_id,
    s.carrier_id,
    (s.delivered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS delivered_business_date,
    COUNT(*) AS on_time_delivered_shipment_count
FROM fulfillment.shipments AS s
WHERE s.delivery_state_code = 'DELIVERED'
  AND s.delivered_at IS NOT NULL
  AND s.delivered_at <= s.promised_delivery_at
  AND s.delivered_at >= $1::TIMESTAMPTZ
  AND s.delivered_at <  $2::TIMESTAMPTZ
GROUP BY
    s.tenant_id,
    s.carrier_id,
    (s.delivered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE;
~~~

Ca kiểm thử:

1. Một shipment có ba lần giao thử, một lần thành công: đếm **một shipment**.
2. Một Order có hai shipment giao đúng hạn: đếm **hai shipments**.
3. delivered_at đúng bằng promised_delivery_at: đúng hạn nếu hợp đồng dùng cận **<=**.
4. Giao trễ một giây: không đúng hạn theo quy tắc timestamp.
5. Một shipment chưa giao, delivered_at NULL: không đếm.
6. Event giao thành công đến muộn: báo cáo phải có cơ chế cập nhật/đối soát theo event time.
7. Carrier thực hiện giao khác carrier đặt ban đầu: cần quy tắc phân loại rõ.
8. Nếu đổi yêu cầu thành “đúng hạn theo ngày”, phải đổi công thức và test, không giữ tên cũ với nghĩa tự phát.

**Tên đúng là kết quả của việc chốt grain và quy tắc**, không phải bước dán nhãn ở cuối.

## 17. Decision log và vòng đời của glossary

Một glossary dễ lỗi thời nếu schema và nghiệp vụ đổi mà không cập nhật. Bộ tài liệu tối thiểu có thể bao gồm:

- **Context map** cho ownership giữa các miền.
- **Conceptual diagram** và thuật ngữ chính.
- **Logical model** với grain, cardinality, khóa nghiệp vụ và bất biến.
- **Physical schema** với table/column/index/constraint.
- **Data dictionary** với nghĩa, thời gian, đơn vị, NULL và phân loại dữ liệu.
- **Metric catalog** với công thức, tập lọc, cách aggregate và owner.
- **API/event contracts** với version và định danh public.
- **Decision log/ADR** về lựa chọn tên, alias và lý do thay đổi.
- **Data quality checks** gắn với những lời hứa quan trọng.

Không cần chín ứng dụng tài liệu riêng biệt. Có thể lưu bên cạnh code/migration, sinh phần cấu trúc từ schema, nhưng **định nghĩa nghiệp vụ phải được người có thẩm quyền xác nhận**.

Ví dụ ADR ngắn:

~~~text
ADR-024: Chọn buyer_account_id thay customer_id trong Sales.Order

Context:
  customer_id trong Order cũ định danh tài khoản đặt đơn.
  Nó không phải CRM person, cũng không phải recipient.

Decision:
  Canonical: buyer_account_id
  Legacy alias: customer_id trong schema và API v1
  Public v2: buyerAccountId, chỉ với consumer cần biết

Consequences:
  - Cần mapping/backfill và chuyển reader/writer có kiểm chứng.
  - Không tự cấp quyền cho recipient hoặc payer.
  - Không phát ID này trong API không có nhu cầu.

Validation:
  - FK đúng tenant.
  - Mapping từ mã cũ sang mới được xác minh.
  - Chỉ bỏ alias khi consumer v1 đã ngừng.

Owner:
  Sales.Order và nhóm dữ liệu.
~~~

### 17.1. Đừng để tên tạm trở thành nguồn chuẩn thứ hai

**orders_new** và **orders_old** tồn tại song song trong một migration cần có:

- Nguồn nào có quyền ghi?
- Bảng nào là projection?
- Mapping tên/trường nào tương đương?
- Khi nào dừng writer cũ?
- Đối soát theo order ID và metric nào?
- Khi nào có thể drop bảng/alias?
- Có đường rollback hoặc forward-fix không?

Nếu hai bảng được ghi độc lập quá lâu, việc đổi tên không thể chữa xung đột. Cần chốt ownership và quy trình tiến hóa.

## 18. Anti-pattern và cách sửa

| Anti-pattern | Nguy cơ | Cách sửa |
| --- | --- | --- |
| Mọi bảng đều có **status** | Mất nghĩa workflow | order_state_code, capture_state_code... |
| **created_at** được dùng cho event time | Sai ngày báo cáo | confirmed_at/occurred_at và loaded_at riêng |
| **amount** ở mọi nơi | Nhầm tiền đã chốt, capture, refund | Tên gắn sự kiện và currency |
| **customer_id** cho buyer, payer, recipient | Sai quan hệ và quyền | Các term theo bounded context |
| **is_active** không có định nghĩa | Không phân biệt xác minh, khóa và hoạt động | State model rõ |
| **payment_count** từ attempts | Đếm cả thất bại | attempted_payment_count hoặc capture_count đúng source |
| **avg_of_avgs** nhưng tên average | Tổng hợp sai | Sum/count và định nghĩa trọng số |
| **fact_orders** chứa dòng hàng | COUNT(*) bị hiểu là số đơn | fact_order_line và grain contract |
| **current_price** ghi trên hóa đơn cũ | Xóa lịch sử giao dịch | unit_price_at_confirmation |
| **orderId** thực chất là PK nội bộ | Coupling và lộ schema | Public ID ổn định/mapper |
| **UserData JSON** chứa PII mọi nơi | Khó phân quyền, xóa dữ liệu | Schema/DTO tối thiểu theo purpose |
| Tự động rename API từ tên DB mới | Breaking change | Contract versioning, compatibility |
| **_new / _old / _tmp** tồn tại vĩnh viễn | Không rõ authoritative source | Owner, expiry, migration gate |

Nếu thấy một tên không đủ rõ, trước tiên xác định **có phải mô hình sai grain hay sai ownership không**. Việc thêm hậu tố dài chỉ có ý nghĩa khi cấu trúc đang biểu diễn đúng sự thật.

## 19. Bài tập vận dụng

### Bài 1 — Customer khác recipient

CRM có Customer, Order có tài khoản đặt, Logistics có người nhận. Người nhận có thể là người khác. Nhóm muốn đặt mọi ID là **customer_id** để thống nhất.

**Câu hỏi:** Thiết kế này có vấn đề gì? Hãy đề xuất tên và mapping.

### Bài 2 — Amount không rõ nghĩa

Một đơn 500.000 VND có hai PaymentAttempt, chỉ attempt thứ hai capture thành công 500.000 VND. Báo cáo SUM amount ở cả bảng orders và payment_attempts.

**Câu hỏi:** Tên nào nên sửa và dữ liệu nào đại diện tiền đã thu?

### Bài 3 — Date nhập nhằng

Sensor đo lúc 23:58 UTC, server nhận lúc 00:03 UTC ngày sau. Bảng chỉ có cột **date**.

**Câu hỏi:** Cần các tên/mốc nào để báo cáo ngày đo và ngày nhận riêng?

### Bài 4 — Product và SKU

Catalog có một Product “Áo thun” với ba size; inventory giữ tồn theo size. Sales chỉ lưu product_id trên OrderLine.

**Câu hỏi:** Nên có entity và FK nào? Mất gì nếu chỉ dùng Product cấp nhóm?

### Bài 5 — is_active thiếu nghĩa

Một account đã đăng ký, chưa xác minh email, không bị khóa và không mua trong 90 ngày, nhưng is_active = true.

**Câu hỏi:** Có thể suy điều gì? Chọn mô hình tên/state khác.

### Bài 6 — SUM sau JOIN

Một đơn có ba dòng, confirmed_items_amount trên header = 310.000 VND. Sau JOIN lines, SUM(header amount) = 930.000.

**Câu hỏi:** Nguyên nhân là tên hay grain? Sửa thế nào?

### Bài 7 — Fact inventory

Có 20 sản phẩm cuối thứ Hai, 25 sản phẩm cuối thứ Ba. Báo cáo SUM(on_hand_quantity) = 45 rồi gọi là tồn cuối kỳ.

**Câu hỏi:** Sai ở đâu và metric đúng là gì?

### Bài 8 — Giá hiện tại và giá đã chốt

Catalog tăng giá hiện hành từ 120.000 lên 130.000, một job cập nhật tất cả OrderLine cũ để giá “đồng nhất”.

**Câu hỏi:** Tên nào giúp phát hiện lỗi và owner nào quyết định giá?

### Bài 9 — Rename API

JSON v1 trả customerId, nhóm Sales muốn buyerAccountId và các giá trị đã xác minh là cùng ID account.

**Câu hỏi:** Có thể thay tên đột ngột không? Đề xuất kế hoạch tương thích.

### Bài 10 — Trạng thái đa chiều

Order xác nhận, Payment capture 50%, Fulfillment chưa xử lý. Hệ lưu status = PROCESSING.

**Câu hỏi:** Vì sao không đủ và trạng thái nào cần tách?

### Bài 11 — Event tên quá chung

Producer gửi OrderUpdated mỗi khi sửa ghi chú, xác nhận đơn hoặc đổi trạng thái giao, kèm nguyên row SQL. Logistics không biết lúc nào tạo Shipment.

**Câu hỏi:** Đặt tên event và giới hạn payload ra sao?

### Bài 12 — Hai kiện giao

Một Order có hai Shipment: kiện A đúng hạn, kiện B trễ. Báo cáo tên **on_time_order_count** dùng COUNT(*) trên shipment đúng hạn.

**Câu hỏi:** Tên và metric đúng cần phân biệt thế nào?

### Bài 13 — Nghĩa metric bị đổi ngầm

Tuần trước new_customer_count = tài khoản đăng ký mới; tuần này = tài khoản mua lần đầu. Nhóm giữ tên và sửa định nghĩa cũ trong glossary.

**Câu hỏi:** Điều gì sai? Nên xử lý version/metric thế nào?

### Bài 14 — Tên bảng tạm tồn tại quá lâu

Hai bảng orders_old và orders_new đều có writer, có các báo cáo đọc xen kẽ. Nhóm dự định chỉ rename để “hết old/new”.

**Câu hỏi:** Thiếu quyết định gì trước khi đổi tên?

### Gợi ý lời giải

1. Không gộp term toàn cục. Dùng **crm_customer_id**, **buyer_account_id** và **recipient_ref** theo context; chỉ nối qua mapping có quyền và nghĩa rõ.
2. Cần **confirmed_items_amount**, **attempt_amount**, **captured_amount**, trạng thái attempt/capture và currency. Tiền đã thu theo **capture thành công** ở nguồn Payment, không cộng attempts thất bại hoặc lặp tổng order.
3. Dùng **observed_at** và **received_at** tách biệt; nhóm theo timestamp tương ứng, với timezone báo cáo được ghi rõ.
4. Dùng Product, ProductVariant và tồn kho variant × warehouse; OrderLine cần **product_variant_id**/snapshot SKU tại giao dịch. Chỉ product group sẽ mất size cụ thể.
5. **is_active** quá mơ hồ. Tách **email_verification_state**, **account_access_state**, **last_order_at** hoặc các điều kiện đã được duyệt; không tự suy ba nghĩa từ một Boolean.
6. Số đo header ở grain Order bị nhân bởi Join dòng. Tổng trên **orders** hoặc SUM **line_net_amount** ở grain OrderLine; không dùng SUM(DISTINCT amount) làm cách sửa chung.
7. **on_hand_quantity** là trạng thái cuối kỳ, không cộng qua hai ngày. Tồn cuối thứ Ba là **25**; bình quân hai ngày chỉ khi yêu cầu và phép đo cho phép.
8. **unit_price_at_confirmation** là snapshot Sales.Order; **current_list_price** thuộc Catalog. Không đồng bộ giá hiện tại vào chứng từ cũ.
9. Field public là contract; cần v2 hoặc cơ chế chuyển tiếp được kiểm thử, mapping rõ, theo dõi consumer và ngừng v1 khi đủ điều kiện.
10. Cần **order_state_code**, **payment_state_code**, **fulfillment_state_code** theo owner; public status có thể là ánh xạ riêng với semantics rõ.
11. Dùng event domain như **OrderConfirmed**, **ShipmentRequested**, **PaymentCaptured** khi phù hợp, có eventId/occurredAt/version; không broadcast PII, PK nội bộ hoặc toàn bộ CDC row.
12. **on_time_delivered_shipment_count** đếm một shipment đúng hạn; **on_time_fulfilled_order_count** phải kiểm tra toàn bộ shipment của mỗi order được giao đúng hạn theo coverage và deadline nghiệp vụ.
13. Hai nghĩa khác nhau cần hai metric như **registered_account_count** và **first_purchase_buyer_count**, có version, owner và ngày hiệu lực; không ghi đè định nghĩa lịch sử.
14. Phải chốt **source of truth, ownership, đường ghi, backfill/đối soát, consumer, rollback và cleanup gate**. Rename không giải quyết dual-write xung đột.

## 20. Ghi nhớ

**Quy ước đặt tên tốt có hai lớp:** một **cú pháp dự đoán được** (schema, snake_case, suffix, constraint) và một **ngôn ngữ nghiệp vụ có định nghĩa, grain, context, owner, thời điểm và đơn vị rõ ràng**. Thiếu lớp ngữ nghĩa, schema trông đẹp vẫn có thể dẫn tới JOIN sai, doanh thu sai hoặc lộ dữ liệu.

**Không ép những sự thật khác nhau cùng một tên.** Buyer không mặc định là Recipient, OrderConfirmed không đồng nghĩa PaymentCaptured, snapshot tại xác nhận không phải giá trị hiện hành, và Shipment không phải Order. Khi hai context có từ vựng khác nhau, hãy viết mapping thay vì đồng nhất cưỡng ép.

**Tên là một phần của hợp đồng có vòng đời.** Khi nghiệp vụ đổi, cần cập nhật glossary, model, API/event, metric và test; chuyển đổi bằng kế hoạch tương thích và đối soát, không chỉ tìm-thay chuỗi.

Trước khi duyệt một tên, hãy hỏi: **“Người nghiệp vụ có dùng thuật ngữ này không? Một hàng hoặc giá trị biểu diễn điều gì, ở thời điểm nào và trong đơn vị gì? Ai có quyền quyết định? Tên này còn giữ đúng nghĩa khi JOIN, tổng hợp hoặc công bố sang hệ khác không?”**. Câu trả lời có thể kiểm chứng giúp mô hình dữ liệu dễ hiểu, dễ bảo trì và tiến hóa an toàn.
