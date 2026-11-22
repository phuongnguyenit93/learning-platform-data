# Chọn dữ liệu cần công bố và tránh lộ cấu trúc lưu trữ nội bộ

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt **mô hình lưu trữ**, **mô hình miền nghiệp vụ**, **mô hình đọc** và **hợp đồng tích hợp**; không coi tên cột hoặc cấu trúc document nội bộ là API công khai.
- Xác định **consumer nào cần dữ liệu nào, để làm gì, được phép xem ở mức nào và cần dữ liệu mới đến đâu** trước khi tạo endpoint, event hoặc bảng chia sẻ.
- Thiết kế **DTO/API response**, **integration event** và **read projection** có trường, kiểu, đơn vị, ngữ nghĩa, định danh và quyền truy cập rõ ràng.
- Dùng **allowlist trường, ánh xạ tường minh, kiểm tra quyền trên đối tượng** và ID công khai để giảm lộ dữ liệu hoặc phụ thuộc vào khóa nội bộ.
- Chọn cách phát thay đổi bằng **transactional outbox** và phân biệt nó với việc mở bảng, chia sẻ database hoặc chuyển nguyên CDC row cho consumer.
- Xây dựng kế hoạch tiến hóa schema với **tương thích ngược, versioning, contract test, observability, đối soát và ngừng hợp đồng cũ**.
- So sánh cách giữ ranh giới khi dữ liệu nằm trong relational database, document database, graph database hoặc hệ phân tích.

Bài thuộc chương **Ranh giới và tích hợp** của **DATABASE_DATA_MODELING**. Khi chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu, ta cần biết thực thể, quan hệ, ràng buộc, khóa, chỉ mục và lược đồ vật lý; nhưng lúc công bố dữ liệu sang API hoặc dịch vụ khác, **mô hình bên trong không nên trở thành lời hứa lâu dài với mọi consumer**. Mục tiêu là để thay đổi cấu trúc bên trong mà vẫn bảo toàn hợp đồng nghiệp vụ và quyền truy cập của bên ngoài.

## 1. Tình huống: một bảng đơn hàng bị dùng như API

Một ứng dụng bán hàng có các bảng nội bộ:

~~~text
orders_internal
  order_pk                 -- BIGINT, khóa thay thế của database
  tenant_id                -- phạm vi doanh nghiệp/tenant
  public_order_id          -- UUID cho khách hàng và hệ ngoài
  customer_pk              -- khóa nội bộ của hồ sơ khách
  workflow_state           -- trạng thái chi tiết của xử lý nội bộ
  total_amount             -- tiền đã chốt trên đơn
  currency
  confirmed_at
  risk_score               -- chỉ số chống gian lận
  agent_note               -- ghi chú nhân viên
  row_version
  updated_at

order_lines_internal
  order_pk, line_no
  product_pk               -- FK nội bộ
  product_name_at_order    -- snapshot tên đã chốt
  quantity
  unit_price_at_order      -- snapshot giá đã chốt

payment_attempts
  payment_attempt_pk
  provider_reference
  internal_error_detail
  ...
~~~

Một lập trình viên viết endpoint đơn giản:

~~~text
GET /orders/901
    -> SELECT * FROM orders_internal WHERE order_pk = 901
    -> serialize nguyên hàng database ra JSON
~~~

Cách này có vẻ nhanh để phát triển, nhưng tạo nhiều vấn đề:

1. **Rò thông tin không cần thiết:** risk_score, agent_note và khóa nội bộ xuất hiện trong response.
2. **Lộ mô hình lưu trữ:** consumer phải biết order_pk, workflow_state, các tên cột SQL và quan hệ FK.
3. **Phụ thuộc khi refactor:** đổi tên cột, tách bảng hay chuyển sang document store dễ làm hỏng tất cả client.
4. **Sai ranh giới quyền:** biết order_pk không chứng minh người gọi được phép đọc đơn; endpoint cần kiểm tra tenant và chủ sở hữu.
5. **Sai ngữ nghĩa:** giá đang lưu trong dòng đơn khác giá niêm yết hiện hành; trạng thái nội bộ chưa chắc là trạng thái nên công bố.
6. **Khó versioning:** mọi thay đổi cơ sở dữ liệu vô tình thành thay đổi hợp đồng bên ngoài.

Một thiết kế tốt đặt **lớp công bố có chủ đích** giữa hệ thống lưu trữ và người dùng dữ liệu:

~~~text
           BÊN TRONG MIỀN ORDER
   +----------------------------------+
   | orders_internal / order_lines    |
   | payment / fulfillment state      |
   | domain rules, transactions       |
   +----------------+-----------------+
                    |
              mapping + policy
                    |
   +----------------+-----------------+
   | Public API DTO                    |
   | Integration events                |
   | Purpose-built read projections    |
   +--------+------------+-------------+
            |            |
         Customer     Logistics / Analytics
         API client   (hợp đồng riêng)
~~~

**Bên ngoài chỉ được dựa vào hợp đồng đã công bố**, không được tùy tiện truy cập bảng, cột hoặc khóa nội bộ. Tách ranh giới này giúp mô hình lưu trữ còn khả năng tiến hóa.

## 2. Bốn mô hình không nên nhập làm một

| Lớp | Trả lời câu hỏi | Ví dụ | Ai có quyền thay đổi? |
| --- | --- | --- | --- |
| **Storage model** | Dữ liệu được lưu, khóa và index thế nào? | orders_internal, order_pk, các bảng FK | Nhóm sở hữu database |
| **Domain model** | Bất biến và chuyển trạng thái nghiệp vụ là gì? | Xác nhận đơn, hủy đơn, chốt giá, hoàn tiền | Nhóm nghiệp vụ và dịch vụ sở hữu |
| **Integration/public contract** | Consumer được biết điều gì với ý nghĩa gì? | OrderView, OrderShippingStarted v1 | Chủ sở hữu hợp đồng phối hợp consumer |
| **Consumer read model** | Consumer cần truy vấn nhanh cấu trúc nào? | Danh sách đơn, dashboard, search document | Nhóm consumer hoặc nhóm projection |

Có thể giữ một **bảng quan hệ chuẩn hóa** làm nguồn dữ liệu chuẩn, một **DTO** cho khách, một **event** tối thiểu cho dịch vụ vận chuyển và một **fact** cho báo cáo. Những cấu trúc đó không phải bản sao “đồng bộ cho giống nhau”; mỗi cấu trúc có **ngữ nghĩa, độ tươi, phạm vi và chủ sở hữu khác nhau**.

### 2.1. Nguồn chuẩn không có nghĩa phải xuất toàn bộ nguồn

**Authoritative source** xác định giá trị đúng của một sự thật nghiệp vụ. Nó không đồng nghĩa mọi trường tại nguồn đều được phép công bố.

Ví dụ:

- Dịch vụ Order là nguồn chuẩn cho **trạng thái đơn** và **giá đã xác nhận**.
- Dịch vụ Customer là nguồn chuẩn cho **địa chỉ mặc định hiện tại**.
- Dịch vụ Payment là nguồn chuẩn cho **capture/refund**.
- Bảng **order_detail_view** có thể là bản sao phục vụ đọc; nó không có quyền tạo ra một giá giao dịch mới.

Ngay cả khi Order có địa chỉ giao hàng đã chốt, dịch vụ Analytics không tự động được quyền nhận toàn bộ địa chỉ đó. **Quyền quyết định giá trị và quyền chia sẻ giá trị là hai quyết định khác nhau.**

### 2.2. Hợp đồng công bố là sản phẩm có vòng đời

Một hợp đồng tốt được xem như một giao diện có người sử dụng:

- Có **tên, phiên bản, mô tả trường và ví dụ**.
- Có **quyền truy cập**, phạm vi tenant và mục đích sử dụng.
- Có **quy tắc đổi schema**, trạng thái lỗi, dữ liệu thiếu, ngữ nghĩa thời gian và tiền.
- Có **SLO** về khả dụng, độ trễ và độ tươi khi dữ liệu được đồng bộ.
- Có **chủ sở hữu**, kiểm thử và quy trình thông báo thay đổi.

Chỉ thêm một JSON serializer không tạo ra các bảo đảm ấy.

## 3. Kiểm kê consumer trước khi quyết định công bố gì

Cùng một đơn hàng có nhiều consumer:

| Consumer | Cần biết | Không nên nhận mặc định | Độ tươi và quyền |
| --- | --- | --- | --- |
| **Khách sở hữu đơn** | Mã đơn, trạng thái dễ hiểu, giá đã chốt, dòng hàng | Điểm rủi ro, ghi chú nhân viên, khóa database | Đọc sau xác thực và kiểm tra sở hữu |
| **Ứng dụng hỗ trợ khách hàng** | Trạng thái, lý do xử lý được phép xem, dữ liệu liên hệ cần thiết | Toàn bộ log Payment, thông tin nhạy cảm không liên quan | Phân quyền theo vai trò và mục đích |
| **Dịch vụ giao vận** | Mã đơn, chỉ dẫn giao, người nhận và địa chỉ **đúng phạm vi thực hiện giao** | Giá vốn, risk_score, chi tiết thanh toán | Cần thông tin đúng thời điểm tạo kiện và quyền hạn hẹp |
| **Dịch vụ thanh toán** | Payment intent, số tiền và currency có thẩm quyền, mã yêu cầu | Ghi chú logistics, danh sách mọi khách hàng | Idempotency và chứng cứ giao dịch rõ |
| **Dashboard vận hành** | Số lượng/trạng thái đơn theo khoảng, độ trễ xử lý | Địa chỉ và số điện thoại từng khách nếu không cần | Có thể dùng dữ liệu tổng hợp cập nhật chậm |
| **Kho phân tích** | Event/fact có grain và định nghĩa số đo, dimension cần thiết | Bản dump nguyên hệ OLTP | Có lineage, chính sách PII/retention và watermark |

Công bố dữ liệu nên dựa trên ba bộ câu hỏi:

1. **Cần để hoàn thành hành động nào?** Nếu không dùng trường, tại sao lại đưa vào hợp đồng?
2. **Consumer có quyền và mục đích hợp lệ không?** Xác thực người gọi, quyền theo đối tượng và chính sách dữ liệu nhạy cảm khác nhau.
3. **Consumer cần sự thật ở thời điểm nào?** Hiện hành, đã xác nhận trong quá khứ, hay trạng thái dẫn xuất có độ trễ?

Không nên lập một kiểu **UniversalOrder** chứa mọi trường rồi chia sẻ cho tất cả bên bằng cách “ẩn những gì không render trên UI”. Dữ liệu đã trả trong response vẫn có thể bị ghi log, cache, đồng bộ sang ứng dụng khác hoặc xem qua công cụ mạng.

### 3.1. Lập bảng quyết định theo trường, không theo bảng

| Trường nội bộ | Public Order API | Logistics contract | Analytics contract | Lý do |
| --- | --- | --- | --- | --- |
| **public_order_id** | Có | Có | Có, theo chính sách định danh | Định danh công khai ổn định |
| **order_pk** | Không | Không | Không mặc định | Khóa lưu trữ nội bộ |
| **customer_pk** | Không | Không | Có thể dùng ID giả danh đã kiểm soát | Không phát tán khóa nội bộ |
| **workflow_state** | Ánh xạ sang trạng thái public | Chuyển thành sự kiện/tiến độ liên quan | Có thể xuất trạng thái có định nghĩa | Trạng thái nội bộ có thể refactor |
| **total_amount, currency** | Có, dưới dạng tiền rõ nghĩa | Thường không | Có khi phục vụ chỉ số hợp lệ | Phải phân biệt đã đặt với đã thu |
| **product_name_at_order** | Có | Có thể cần tên hàng | Có thể cần product ID và thuộc tính theo thời điểm | Snapshot không đồng bộ theo tên hiện tại |
| **risk_score** | Không | Không | Chỉ nếu có nhu cầu được duyệt, có kiểm soát | Thông tin nhạy cảm nghiệp vụ |
| **agent_note** | Không | Không | Không mặc định | Văn bản có thể chứa PII hoặc nhận xét nội bộ |
| **shipping_address_at_confirmation** | Có khi chính chủ cần xem | Chỉ bên giao vận được ủy quyền | Không mặc định | PII và mục đích khác nhau |
| **provider_secret / token** | Không | Không | Không | Bí mật không được phát tán |

**Nguyên tắc allowlist:** bắt đầu từ tập trường **không có gì được công bố**, chỉ thêm trường khi có yêu cầu và phê duyệt phù hợp. Cách này khác blacklist kiểu “serialize mọi cột trừ risk_score”, vì cột nhạy cảm mới thêm vào bảng có thể tự xuất hiện nếu người viết quên cập nhật danh sách cấm.

## 4. Thiết kế ID công khai và giữ ngữ nghĩa ổn định

### 4.1. Khóa nội bộ và định danh công khai khác vai trò

Một bảng có thể dùng **order_pk BIGINT** làm khóa chính để JOIN và index. API lại dùng **public_order_id UUID** để trao đổi giữa các hệ.

Lợi ích:

- Tách hợp đồng bên ngoài khỏi lựa chọn kiểu khóa và chiến lược phân vùng nội bộ.
- Tránh việc API phụ thuộc vào sequence hoặc khóa FK cụ thể.
- Giữ ID công khai ổn định nếu di trú database hoặc tái tạo bảng.
- Giảm một số cách suy đoán quy mô từ ID tuần tự, nhưng **không thay thế bảo mật**.

**UUID không phải cơ chế phân quyền.** Người dùng biết hoặc đoán được một UUID vẫn không có quyền đọc đơn người khác. Đường đọc phải xác minh **tenant và chủ sở hữu/role** theo thông tin đáng tin từ phiên đăng nhập hoặc token đã xác thực.

Nếu hệ thống có **order_number** dễ đọc và có thể lặp theo tenant/năm, cần ghi rõ phạm vi duy nhất. Không được nhập nhằng giữa **order_pk**, **public_order_id** và **order_number** rồi dùng chúng như cùng một khóa.

### 4.2. Trạng thái công khai là ngữ nghĩa, không phải mã enum của database

Trạng thái nội bộ có thể gồm:

~~~text
CONFIRMED -> PICKING -> PACKED -> IN_TRANSIT -> DELIVERED
                   -> WAITING_WAREHOUSE_RECHECK
                         -> PICKING
CONFIRMED -> CANCELLED
~~~

Khách hàng có thể chỉ cần:

~~~text
CONFIRMED, PROCESSING, SHIPPING, DELIVERED, CANCELLED
~~~

Nếu API công bố thẳng **PICKING**, **PACKED**, **WAITING_WAREHOUSE_RECHECK**, mọi thay đổi workflow có thể bắt khách cập nhật ứng dụng. Một **mapping có chủ đích** cho phép thay đổi bước nội bộ mà giữ lời hứa public, nếu vẫn cùng ý nghĩa:

| Nội bộ | Công khai |
| --- | --- |
| CONFIRMED | CONFIRMED |
| PICKING, PACKED, WAITING_WAREHOUSE_RECHECK | PROCESSING |
| IN_TRANSIT | SHIPPING |
| DELIVERED | DELIVERED |
| CANCELLED | CANCELLED |

Mapping không phải phép đổi tên tùy ý. Các trạng thái thực sự khác nhau về quyền hủy, nghĩa vụ giao và thời gian chờ phải được xem xét trong domain. Nếu thêm một trạng thái mới mà không rõ cách công bố, hệ thống nên **phát hiện thiếu mapping** thay vì tự trả nguyên giá trị nội bộ.

## 5. Hợp đồng API: một OrderView nhỏ, rõ nghĩa và đủ dùng

Ví dụ endpoint cho khách đã đăng nhập:

~~~text
GET /v1/orders/{publicOrderId}
Authorization: Bearer <access-token>

200 OK          -- Đơn thuộc phạm vi người gọi và có quyền xem
404 Not Found   -- Không tồn tại hoặc chính sách không tiết lộ sự tồn tại
401/403         -- Theo chính sách xác thực, phân quyền và chống lộ dữ liệu
~~~

Response minh họa:

~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PROCESSING",
  "confirmedAt": "2026-11-22T01:00:00Z",
  "total": {
    "amount": "310000.00",
    "currency": "VND"
  },
  "items": [
    {
      "lineId": "1",
      "productNameAtOrder": "Sổ tay A5",
      "quantity": 2,
      "unitPriceAtOrder": {
        "amount": "150000.00",
        "currency": "VND"
      }
    }
  ],
  "delivery": {
    "city": "TP. Hồ Chí Minh",
    "countryCode": "VN"
  }
}
~~~

Đây là **mẫu hợp đồng giả định**, không phải schema đầy đủ của thanh toán/thuế/giảm giá. Đơn có hai dòng hoặc các điều khoản giảm giá khác sẽ có cấu trúc tương ứng theo thiết kế được công bố.

Quyết định quan trọng:

- **orderId** là ID công khai, không phải khóa chính database.
- **status** có tập giá trị public được tài liệu hóa.
- **confirmedAt** là timestamp ISO 8601 kèm timezone, biểu diễn thời điểm nghiệp vụ; không lấy **updated_at** thay thế.
- **amount** là chuỗi decimal tránh phụ thuộc vào cách JavaScript JSON number biểu diễn số tiền; phải mô tả quy tắc precision, scale và làm tròn. Có thể chọn số nguyên đơn vị nhỏ thay thế nếu hợp đồng thống nhất.
- **items[]** là snapshot dòng hàng đã xác nhận. Đây là sự thật lịch sử, **không** đồng bộ giá/tên theo Catalog hiện hành.
- **delivery.city/countryCode** là thông tin vừa đủ cho màn hình này. Địa chỉ đầy đủ, nếu cần, nên được công bố tại endpoint/trường có chính sách truy cập và retention thích hợp.
- Không có **risk_score**, **agent_note**, **order_pk**, **customer_pk** hoặc **provider_secret**.
- **lineId** chỉ là định danh dòng được thiết kế cho API; nó không buộc client phải biết khóa phức hợp nội bộ.

Cần làm rõ **trường nào luôn có**, trường nào có thể **null**, trường nào **không xuất hiện** tùy quyền hoặc trạng thái. “Không có thông tin giao hàng” có thể là chưa được thu thập, không được phép xem hoặc chưa tạo kiện; đừng tùy tiện trả chuỗi rỗng cho cả ba ý nghĩa.

### 5.1. Không nhầm phép chiếu dữ liệu với quyền truy cập

Câu SQL chỉ chọn bảy cột thay vì toàn bộ bảng giúp **giảm lượng dữ liệu có thể lộ**, nhưng **không đủ** làm authorization. Kiểm tra quyền phải áp dụng **trước hoặc cùng lúc** truy vấn dữ liệu dựa trên identity đã xác thực, không nhận tùy tiện customerId/tenantId do client gửi.

Cụ thể:

- Phải bảo vệ **BOLA/IDOR**: người gọi không được đọc object của người khác chỉ bằng thay orderId trong URL.
- Phải bảo vệ **mass assignment**: endpoint ghi không tự bind mọi field request vào entity nội bộ; client không được tự đặt **risk_score**, **row_version** hoặc trạng thái nhạy cảm.
- Không giả định API gateway đã lọc quyền đến từng object nếu dịch vụ chưa có hợp đồng về việc đó.
- Kiểm tra hành vi **404/403** để tránh tạo kênh dò dữ liệu qua phản hồi khác nhau, tùy chính sách hệ thống.

## 6. Ví dụ PostgreSQL: bảng nội bộ khác truy vấn công bố

Đặt lược đồ nội bộ đủ cho ví dụ:

~~~sql
CREATE TABLE orders_internal (
    order_pk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    public_order_id UUID NOT NULL UNIQUE,
    customer_pk BIGINT NOT NULL,
    workflow_state TEXT NOT NULL
        CHECK (workflow_state IN (
            'CONFIRMED', 'PICKING', 'PACKED',
            'WAITING_WAREHOUSE_RECHECK',
            'IN_TRANSIT', 'DELIVERED', 'CANCELLED'
        )),
    total_amount NUMERIC(18, 2) NOT NULL
        CHECK (total_amount >= 0),
    currency CHAR(3) NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    delivery_city TEXT,
    delivery_country_code CHAR(2),
    risk_score NUMERIC(5, 4),
    agent_note TEXT,
    row_version BIGINT NOT NULL DEFAULT 1
        CHECK (row_version >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_lines_internal (
    order_pk BIGINT NOT NULL
        REFERENCES orders_internal(order_pk),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_pk BIGINT NOT NULL,
    product_name_at_order TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_order NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    PRIMARY KEY (order_pk, line_no)
);

CREATE INDEX ix_orders_tenant_customer
    ON orders_internal
       (tenant_id, customer_pk, public_order_id);
~~~

Đây là DDL **thu gọn cho bài học**, chưa có đầy đủ bảng Customer, Payment, Shipment hoặc chính sách chống trùng thao tác tạo đơn. Trong môi trường đa tenant, cần xác định quyền và tính duy nhất của **public_order_id**, phạm vi **customer_pk** và các ràng buộc ở nguồn nghiệp vụ.

**Phân quyền database** cũng cần phù hợp: tài khoản phục vụ API không nên tùy ý cập nhật cột nhạy cảm. Một lớp truy cập dữ liệu có thể tách quyền đọc projection với quyền xử lý nghiệp vụ, nhưng **view/role** không thay thế kiểm tra quyền theo từng người dùng.

### 6.1. Query allowlist và phạm vi quyền

Giả sử ứng dụng đã có:

- **$1**: tenant ID từ phiên đã xác thực, không lấy trực tiếp từ input thiếu tin cậy.
- **$2**: customer PK đã xác minh từ principal hoặc quan hệ sở hữu có thẩm quyền.
- **$3**: public order UUID do client yêu cầu.

SQL lấy header:

~~~sql
SELECT
    o.order_pk,        -- chỉ dùng ở service để lấy items
    o.public_order_id,
    o.workflow_state,
    o.confirmed_at,
    o.total_amount,
    o.currency,
    o.delivery_city,
    o.delivery_country_code
FROM orders_internal AS o
WHERE o.tenant_id = $1
  AND o.customer_pk = $2
  AND o.public_order_id = $3::UUID;
~~~

Kết quả **order_pk không được đưa vào API**; nó chỉ là khóa nối bên trong service. Nếu không trả hàng, service không thể tự động kết luận “không có đơn”, vì có thể là không thuộc quyền; response được quyết định theo chính sách không tiết lộ sự tồn tại.

Lấy các dòng **sau khi header đã được kiểm tra quyền**:

~~~sql
SELECT
    line_no,
    product_name_at_order,
    quantity,
    unit_price_at_order
FROM order_lines_internal
WHERE order_pk = $1
ORDER BY line_no;
~~~

Nếu yêu cầu phải trả một **snapshot nhất quán** khi order và items được cập nhật đồng thời, hai câu SELECT chạy ở hai snapshot **READ COMMITTED** có thể nhìn các phiên bản khác nhau. Có thể dùng một câu SELECT JOIN rồi gom DTO, hoặc dùng transaction với isolation/snapshot phù hợp; điều đó tùy bất biến và vòng đời ghi thực tế. **Tách DTO khỏi storage không được trở thành lý do bỏ qua consistency.**

### 6.2. Ánh xạ Java bằng record và mapper tường minh

Ví dụ Java với kiểu dành cho miền công bố:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

record MoneyView(String amount, String currency) {}

record OrderLineView(
    String lineId,
    String productNameAtOrder,
    int quantity,
    MoneyView unitPriceAtOrder
) {}

record DeliveryAreaView(
    String city,
    String countryCode
) {}

record OrderView(
    UUID orderId,
    String status,
    Instant confirmedAt,
    MoneyView total,
    List<OrderLineView> items,
    DeliveryAreaView delivery
) {}

final class OrderPublicMapper {
    private OrderPublicMapper() {}

    static String publicStatus(String internalState) {
        return switch (internalState) {
            case "CONFIRMED" -> "CONFIRMED";
            case "PICKING", "PACKED", "WAITING_WAREHOUSE_RECHECK"
                -> "PROCESSING";
            case "IN_TRANSIT" -> "SHIPPING";
            case "DELIVERED" -> "DELIVERED";
            case "CANCELLED" -> "CANCELLED";
            default -> throw new IllegalArgumentException(
                "Unmapped internal order state"
            );
        };
    }

    static MoneyView money(BigDecimal amount, String currency) {
        return new MoneyView(
            amount.toPlainString(),
            currency.trim()
        );
    }
}
~~~

Đây là ví dụ **kiểu dữ liệu và mapper cốt lõi**, không phải một REST controller chạy độc lập. Service phải xây **OrderView** từ các bản ghi đã kiểm tra quyền và các phép tính được xác minh, sau đó serializer chỉ phát các trường trong DTO.

**Không trả entity ORM trực tiếp** rồi trông chờ annotation ẩn vài field. Từ entity có thể phát sinh quan hệ lazy-loaded, object graph vòng lặp, trường mới và thông tin nội bộ mà nhóm API chưa review. Một mapper tường minh làm sai khác storage/public contract có thể kiểm tra được qua code review và test.

**Không chuyển BigDecimal thành double** để tiện serialize tiền. Nếu public contract chọn chuỗi decimal như ví dụ, cần giữ quy tắc scale/rounding và xử lý khi dữ liệu nội bộ thiếu hoặc không hợp lệ.

### 6.3. Request ghi cũng cần kiểu riêng

Tương tự response, endpoint thay đổi trạng thái đơn không nên nhận nguyên **OrderEntity** từ client. Một lệnh nghiệp vụ chỉ cần dữ liệu có thể thay đổi theo chính sách:

~~~json
{
  "reasonCode": "CUSTOMER_REQUEST",
  "idempotencyKey": "cancel-req-991"
}
~~~

**Order ID** thường nằm trên đường dẫn; trạng thái đích và điều kiện chuyển tiếp phải do server quyết định. Client không được tự gửi **tenant_id**, **risk_score**, **total_amount** hoặc **workflow_state = DELIVERED** rồi hy vọng server “chỉ lưu các field hợp lệ”. Cần validation và authorization tại ranh giới lệnh.

## 7. Chọn hợp đồng event: chia sẻ sự kiện nghiệp vụ, không phát toàn bộ bảng

Dịch vụ Logistics cần biết đơn bắt đầu giao; hệ Analytics cần fact để tính thời gian từ xác nhận đến giao; Customer App cần trạng thái hiển thị. Một lỗi phổ biến là phát event chứa nguyên hàng **orders_internal**:

~~~json
{
  "eventType": "OrderUpdated",
  "table": "orders_internal",
  "row": {
    "order_pk": 901,
    "tenant_id": 17,
    "workflow_state": "IN_TRANSIT",
    "risk_score": "0.4200",
    "agent_note": "Call customer after review",
    "updated_at": "2026-11-22T03:00:00Z"
  }
}
~~~

Kiểu event này khiến consumer phụ thuộc cột database, có thể lộ dữ liệu và không biết điều gì **thực sự xảy ra theo nghiệp vụ**: đơn vừa được tạo, được chuyển sang giao, hay chỉ sửa ghi chú?

Hợp đồng event có chủ đích hơn:

~~~json
{
  "eventId": "d6cf7c19-19a1-4fbc-a88b-67e6300a9b11",
  "eventType": "OrderShippingStarted",
  "schemaVersion": 1,
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "orderVersion": 8,
  "occurredAt": "2026-11-22T03:00:00Z"
}
~~~

Đặc điểm:

- **OrderShippingStarted** nói rõ sự kiện domain, không phải thao tác UPDATE một bảng.
- **eventId** giúp consumer nhận biết cùng một message được gửi lại.
- **schemaVersion** phiên bản **cấu trúc/hợp đồng**; khác **orderVersion** là phiên bản **trạng thái nghiệp vụ**.
- **orderId** là ID công khai ổn định; không phát FK nội bộ.
- **occurredAt** là thời điểm chuyển trạng thái có thẩm quyền, không được tự đồng nhất với lúc broker nhận.
- Event **không có địa chỉ giao** nếu consumer chỉ cần biết trạng thái. Dịch vụ giao vận có thể nhận **hợp đồng chi tiết bảo mật riêng** khi thật sự cần thực hiện giao hàng.

**Event không nhất thiết là snapshot hoàn chỉnh.** Một event báo thay đổi trạng thái có ngữ nghĩa riêng; nếu consumer cần xây projection đầy đủ, thiết kế event hoặc API lấy snapshot phải thể hiện rõ cách lấy dữ liệu nhất quán và các phiên bản liên quan.

### 7.1. CDC và integration event giải quyết các nhu cầu khác nhau

**Change Data Capture (CDC)** ghi nhận sự thay đổi ở mức log/hàng/cột database. Nó rất hữu ích để đồng bộ dữ liệu kỹ thuật, xây projection hoặc chuyển dữ liệu vào warehouse, nhưng nếu chuyển nguyên payload CDC tới mọi consumer, tên bảng/cột, quyền ghi và cấu trúc lưu trữ dễ trở thành hợp đồng thực tế.

**Integration event** là hợp đồng **nghiệp vụ/quan sát** do bên sở hữu công bố. Nó cần mapping từ thay đổi bên trong sang ngữ nghĩa bên ngoài, quyết định field và policy. Có thể **dùng CDC làm cơ chế vận chuyển** dữ liệu tới lớp mapping, nhưng **không nên đồng nhất bản ghi CDC thô với event công khai**.

| Khía cạnh | CDC kỹ thuật | Integration event có chủ đích |
| --- | --- | --- |
| Đơn vị thay đổi | Row/document/operation tại storage | Sự kiện nghiệp vụ được đặt tên |
| Tên và field | Thường theo schema lưu trữ | Theo hợp đồng consumer |
| Refactor database | Có thể làm đổi payload | Có thể được che bởi mapper khi nghĩa không đổi |
| Quyền truy cập | Phải kiểm soát dữ liệu raw và kênh truy xuất | Công bố allowlist theo audience |
| Khả năng dựng projection | Có thể phù hợp nếu có snapshot/checkpoint | Phụ thuộc độ đầy đủ và semantics của event |
| Điểm yếu | Lộ schema, khó suy nghiệp vụ khi nhiều ghi liên quan | Phải duy trì mapping, version, testing và delivery |

Dù dùng cơ chế nào, **consumer không tự có quyền đọc mọi dữ liệu chỉ vì cùng mạng nội bộ**.

## 8. Transactional outbox: giữ tính nguyên tử mà không lộ schema

Một thay đổi trạng thái ở Order phải có event tương ứng. Nếu ứng dụng:

1. COMMIT **workflow_state = IN_TRANSIT**;
2. Sau đó gửi message tới broker;

thì có thể xảy ra lỗi sau bước 1 khiến event **không bao giờ gửi**. Ngược lại, nếu gửi trước commit, broker có thể nhận event của một giao dịch bị rollback.

**Transactional outbox** ghi sự kiện cần phát cùng transaction với thay đổi nguồn.

### 8.1. Bảng outbox minh họa

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL
        CHECK (schema_version >= 1),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    CONSTRAINT uq_outbox_order_version
        UNIQUE (aggregate_id, aggregate_version)
);
~~~

Ví dụ này giả định **mỗi lần chuyển phiên bản đơn cần phát tối đa một integration event**. Nếu một phiên bản có thể phát nhiều event độc lập, unique constraint và cách đánh số thứ tự phải thay đổi; không áp ràng buộc sai khiến mất event.

Bảng outbox là **cấu trúc nội bộ để phát hợp đồng**, không phải bảng mà bên ngoài được phép truy cập trực tiếp. Publisher chịu trách nhiệm gửi các message chưa phát, thử lại và cập nhật trạng thái phát.

### 8.2. Thay đổi trạng thái và ghi event trong một SQL statement

Ứng dụng chuyển trạng thái từ **PACKED** sang **IN_TRANSIT**, cấp một UUID sự kiện và kiểm tra có đúng một hàng được thay đổi:

~~~sql
BEGIN;

WITH changed AS (
    UPDATE orders_internal
    SET workflow_state = 'IN_TRANSIT',
        row_version = row_version + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE order_pk = $1
      AND workflow_state = 'PACKED'
    RETURNING public_order_id, row_version, updated_at
)
INSERT INTO integration_outbox (
    event_id,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    payload
)
SELECT
    $2::UUID,
    public_order_id,
    row_version,
    'OrderShippingStarted',
    1,
    jsonb_build_object(
        'eventId', $2::UUID,
        'eventType', 'OrderShippingStarted',
        'schemaVersion', 1,
        'orderId', public_order_id,
        'orderVersion', row_version,
        'occurredAt', to_char(
            updated_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'
        )
    )
FROM changed;

-- Chỉ COMMIT khi INSERT trả đúng một hàng.
-- Nếu không: ROLLBACK, trả lỗi chuyển trạng thái/xung đột hợp lệ.
COMMIT;
~~~

Đây là **ví dụ giao thức ứng dụng**, không phải script SQL tự ra quyết định COMMIT khi **INSERT** trả 0 hàng. Service phải kiểm tra kết quả, áp dụng quy tắc chuyển trạng thái và lựa chọn COMMIT/ROLLBACK. Những thông tin nghiệp vụ khác như shipment ID có thể phải được quản lý bởi dịch vụ giao vận và event tương ứng, không tự bịa để lấp payload.

Tính chất cốt lõi: **UPDATE nguồn và INSERT outbox** cùng commit hoặc rollback. Sau commit, publisher có thể gửi event qua broker.

**Outbox không tự bảo đảm chính xác một lần từ đầu tới cuối.** Publisher có thể đã gửi thành công rồi chết trước khi đánh dấu **published_at**, khiến event được gửi lại. Consumer cần idempotency theo **eventId** và/hoặc version, cùng quy tắc xử lý message đến sai thứ tự. Trạng thái chuyển lệnh ở nguồn cũng cần idempotency nếu retry cùng một yêu cầu có thể tạo thêm nghiệp vụ.

### 8.3. Bản sao đọc nhanh vẫn cần hợp đồng

Một consumer tạo **order_cards** có thể lưu:

~~~text
order_cards (projection)
  public_order_id
  customer_public_id
  public_status
  confirmed_at
  total_amount
  currency
  source_order_version
  projected_at
~~~

Đó là mô hình đọc theo access pattern, **không** là nơi tự quyết định trạng thái đơn. Nếu nhận event v8 rồi v7, không được ghi lùi về v7. Với event chỉ chứa trạng thái, cần chắc chắn consumer có đủ thông tin/phiên bản để cập nhật một phần an toàn; với event tạo mới, có thể cần snapshot hoặc API có thẩm quyền.

Không được dùng eventual projection để duyệt thanh toán, hoàn tiền hoặc quyết định bán hàng khi nghiệp vụ đòi trạng thái đã xác minh ở nguồn.

## 9. Hợp đồng không được vô tình phụ thuộc vào cách lưu vật lý

Những thiết kế dễ lộ storage:

- API công bố **order_pk BIGINT** rồi mọi consumer lưu làm FK.
- DTO có tên **order_row**, **deleted_flag**, **join_table_ids** đúng như bảng SQL nội bộ.
- GraphQL schema tự tạo từ tất cả entity ORM, cho phép query xuyên mọi relation không xét phân quyền.
- Search API trả nguyên **MongoDB document** gồm **_id**, metadata kỹ thuật và trường mới chưa review.
- Event broker phát mọi **UPDATE** trong bảng cùng toàn bộ before/after row.
- Consumer query trực tiếp database Order bằng SELECT từ các bảng nội bộ thay vì hợp đồng có version.
- Dashboard lấy thẳng cột **workflow_state** rồi tự ánh xạ sang trạng thái public theo từng đội.

Có thể dùng mô hình lưu trữ để **triển khai** một hợp đồng, nhưng không nên coi nó là hợp đồng.

### 9.1. Anti-corruption layer và mapping theo miền

Khi một dịch vụ tham gia vào kiến trúc nhiều miền, **anti-corruption layer (ACL)** chuyển khái niệm của hệ khác sang khái niệm của miền mình, tránh nhập nguyên tên, trạng thái và bất biến bên ngoài.

Ví dụ Order gọi dịch vụ Payment:

~~~text
Payment response: capture_status = "SETTLED"
             |
             v
Adapter có kiểm chứng: tiền đã capture thành công
             |
             v
Order business state: paymentRequirementSatisfied = true
~~~

Không nên viết trực tiếp **orders_internal.workflow_state = payment.capture_status** vì hai trạng thái thuộc hai miền và có vòng đời khác nhau. Nếu Payment thêm **PARTIALLY_SETTLED**, adapter phải xử lý theo luật nghiệp vụ Order, không âm thầm map một enum mới.

Tương tự, hợp đồng Order công bố cho Logistics phải tôn trọng ngôn ngữ giao vận và quyền dữ liệu của phía nhận, thay vì ép Logistics biết tên bảng **order_lines_internal**.

### 9.2. Database view có thể giúp nhưng không phải toàn bộ lớp công bố

Một **SQL VIEW** có allowlist cột có thể tiện cho job nội bộ hoặc read-only integration trong một boundary đáng tin:

~~~sql
CREATE VIEW order_public_projection AS
SELECT
    public_order_id,
    confirmed_at,
    total_amount,
    currency,
    CASE
        WHEN workflow_state = 'CONFIRMED' THEN 'CONFIRMED'
        WHEN workflow_state IN (
            'PICKING', 'PACKED', 'WAITING_WAREHOUSE_RECHECK'
        ) THEN 'PROCESSING'
        WHEN workflow_state = 'IN_TRANSIT' THEN 'SHIPPING'
        WHEN workflow_state = 'DELIVERED' THEN 'DELIVERED'
        WHEN workflow_state = 'CANCELLED' THEN 'CANCELLED'
    END AS public_status
FROM orders_internal;
~~~

**Cảnh báo:** view này **không chứa điều kiện người dùng/tenant** và **không nên được cấp SELECT công khai cho mọi client**. Muốn dùng an toàn cần cơ chế permission/RLS hoặc service có authorization theo object. View giúp giảm phụ thuộc cột nội bộ, nhưng khi **consumer có quyền query tự do và chia sẻ database**, coupling vào khả năng truy vấn, thời điểm dữ liệu và quyền vận hành vẫn tồn tại.

Có thể dùng view cho chuyển đổi dữ liệu trong nội bộ một nhóm, rồi **API/service boundary** để kiểm tra quyền theo người gọi và công bố hợp đồng. Không xem view là giải pháp thay thế mọi API.

## 10. Versioning: thay storage mà không bắt consumer đổi cùng lúc

Giả sử phiên bản đầu của API có:

~~~json
{
  "orderId": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PROCESSING",
  "total": {
    "amount": "310000.00",
    "currency": "VND"
  }
}
~~~

Nhóm Order muốn đổi database nội bộ từ nhiều bảng quan hệ sang một document store. Nếu giữ được **orderId, status, total** với cùng semantics, client **không phải biết** thay đổi đó.

Ngược lại, đổi tên **status** thành **workflowState**, đổi giá từ **amount chuỗi decimal** sang **float**, hoặc tự thay **PROCESSING** thành **PICKING** là thay đổi hợp đồng có thể làm hỏng consumer dù database không đổi.

### 10.1. Phân biệt thay đổi tương thích và phá vỡ hợp đồng

| Thay đổi | Tác động thường gặp | Cần làm |
| --- | --- | --- |
| Đổi tên bảng, index hoặc partition nội bộ | Không nên ảnh hưởng API | Giữ mapper và contract test |
| Thêm trường tùy chọn đã có semantics rõ | Có thể tương thích với client bỏ qua trường lạ | Kiểm thử consumer thực tế, tài liệu hóa |
| Thêm giá trị enum công khai | Có thể phá vỡ client dùng enum exhaustive | Thiết kế unknown/fallback hoặc version và thông báo |
| Bỏ/đổi tên field bắt buộc | Thường breaking | Hợp đồng mới, giai đoạn chuyển tiếp |
| Đổi decimal string thành JSON number | Có thể breaking và mất chính xác | Contract mới, thử số tiền lớn và rounding |
| Đổi ý nghĩa của **total** từ giá trị đơn sang tiền đã thu | Breaking về ngữ nghĩa dù type không đổi | Tạo field/metric có tên mới, migration |
| Chuyển timestamp UTC sang local không có offset | Breaking/khó giải thích | Giữ timezone và chuẩn hóa |
| Chia một event lớn thành nhiều event khác | Tác động ordering, dedupe và flow | Version, replay/compatibility, hợp đồng consumer |
| Thêm cột nhạy cảm vào database | **Không được** tự xuất hiện ngoài API | Allowlist mapping và test chống lộ |

Đừng đánh đồng **thêm field** với an toàn tuyệt đối: với schema validator nghiêm ngặt, client tự deserialize không chấp nhận unknown field, hoặc sự kiện có chữ ký/canonical form, thêm field vẫn có thể làm hỏng consumer. Hợp đồng cần quy định hướng tương thích và mức linh hoạt của consumer.

### 10.2. Chiến lược expand–migrate–contract

Ví dụ đổi hợp đồng public từ **grandTotal** cũ sang object **total(amount,currency)**:

1. **Expand:** bổ sung hợp đồng mới hoặc version v2 song song, chưa xóa v1.
2. **Migrate:** chuyển consumer và test; theo dõi ai còn gọi v1.
3. **Contract:** ngừng v1 sau thông báo, thời hạn và điều kiện sử dụng thực tế đã đáp ứng.
4. **Cleanup:** sau khi không còn consumer, mới bỏ mapper/field/storage hỗ trợ v1.

Nếu cần hỗ trợ hai version dài hạn, mapping và test phải xác nhận **cùng một sự thật nghiệp vụ** được công bố đúng theo từng format. Tránh giữ cả hai đường ghi độc lập tạo thành hai nguồn chuẩn.

### 10.3. Version của event khác version của aggregate

- **schemaVersion = 1**: consumer diễn giải payload theo cấu trúc hợp đồng v1.
- **orderVersion = 8**: lần thay đổi trạng thái dữ liệu Order theo quy tắc ở nguồn.
- **sourceCheckpoint/watermark**: luồng/projection đã xử lý đến mốc nào.
- **effectiveAt**: một trạng thái có hiệu lực nghiệp vụ từ lúc nào, nếu khác thời điểm phát sự kiện.

Không thay thế các mốc này bằng **updated_at** của bảng theo cách ngầm định. Một message có thể gửi lại, đến muộn hoặc được tái dựng trong migration.

## 11. Cách chia sẻ dữ liệu an toàn giữa các boundary

### 11.1. API request/response

Phù hợp khi consumer cần truy vấn **theo yêu cầu** và chủ nguồn có thể kiểm tra quyền tại thời điểm gọi.

Cần quy định endpoint, rate limits, pagination, lỗi, trường và policy. Với danh sách đơn, nên hỗ trợ **pagination theo khóa công khai/thời điểm có thứ tự ổn định**, không cho phép SELECT tùy ý từ mọi cột nội bộ.

### 11.2. Integration event

Phù hợp khi consumer cần phản ứng với **sự kiện đã xảy ra**, duy trì projection hoặc kích hoạt workflow. Event phải có ngữ nghĩa, ID, version, retry và retention; consumer phải chấp nhận at-least-once delivery nếu đó là cơ chế thực tế.

**Event không phải quyền vô hạn để consumer lưu dữ liệu vĩnh viễn.** Các trường có PII, chính sách xóa và thời hạn giữ cũng áp dụng cho broker, dead-letter và read models.

### 11.3. Shared database / SQL view

Có thể là giải pháp chuyển tiếp ở hệ thống nhỏ, batch hoặc cùng một miền quản trị. Nhưng consumer SELECT từ bảng nguồn có thể:

- Phụ thuộc tên cột và cách JOIN.
- Đọc trạng thái chưa có ngữ nghĩa nghiệp vụ đầy đủ.
- Tạo tải trực tiếp lên OLTP.
- Khó phân quyền theo trường và từng đối tượng.
- Gây khó khăn khi thay đổi schema hoặc di trú.

Nếu cần chia sẻ SQL, ưu tiên **schema/view được công bố riêng, quyền read-only tối thiểu, version và ownership**, đồng thời có kế hoạch ngừng phụ thuộc trước khi thay đổi lớn. Không tự giả định shared database luôn bị cấm, nhưng cần ghi nhận chi phí coupling và kiểm soát quyền.

### 11.4. Analytics export

Phù hợp báo cáo dài hạn, phân tích theo sản phẩm/ngày/kênh. Cần khai báo **grain của fact**, định nghĩa số đo, thời điểm ghi nhận và dimension dùng để phân loại.

Ví dụ bảng **fact_order_line_confirmed** có thể công bố cho kho dữ liệu ở grain **một dòng đơn đã xác nhận**, với quantity, tiền ròng đã phân bổ, currency, confirmedAt và ID sản phẩm. Đây **không phải** dump nguyên hàng Orders + Payments + Shipments: JOIN nhiều quan hệ 1:N có thể nhân dòng và làm doanh thu sai.

Nếu consumer chỉ cần báo cáo doanh thu theo ngày, nên cân nhắc **bảng tổng hợp theo ngày × currency** thay vì phát danh tính và địa chỉ mọi khách.

## 12. Đối chiếu dữ liệu quan hệ, document, graph và analytics

| Mô hình nguồn | Điều dễ bị lộ khi publish trực tiếp | Hợp đồng nên công bố |
| --- | --- | --- |
| **Relational** | PK/FK, join table, cột kiểm soát workflow, cấu trúc chuẩn hóa | DTO hoặc resource/event theo nghĩa nghiệp vụ |
| **Document** | **_id**, mảng nội bộ, metadata kỹ thuật, cấu trúc nhúng thay đổi | Schema theo use case, projection allowlist, ID public |
| **Graph** | Node/edge ID vật lý, nhãn quan hệ nội bộ, traversal không giới hạn | Truy vấn theo quyền và câu hỏi nghiệp vụ, không trả toàn graph |
| **Time-series** | ID thiết bị nhạy cảm, raw samples, tag nội bộ, retention | Các series đã được duyệt, bucket/đơn vị/độ tươi rõ |
| **Dimensional/analytics** | Khóa surrogate dimension, dữ liệu khách chi tiết, trạng thái ETL | Fact/aggregate có grain, metric, quyền dữ liệu, watermark |

**Mô hình document:** nếu document Order chứa toàn bộ thanh toán, log giao vận và địa chỉ, API không được trả nguyên document chỉ vì nó đã nằm trong một aggregate. **Cấu trúc lưu cùng nhau không chứng minh được quyền đọc cùng nhau.**

**Mô hình graph:** một API “lấy tất cả neighbor” có thể lộ quan hệ cá nhân hoặc nội bộ. Mỗi cạnh, node và đường duyệt cần kiểm tra quyền và giới hạn mục đích. Không gửi ID nội bộ của đồ thị như hợp đồng định danh dài hạn.

**Hệ analytics:** giảm nguy cơ lộ bằng cách công bố số liệu tổng hợp khi đủ dùng, nhưng **aggregate không tự đảm bảo ẩn danh**; nhóm quá nhỏ, phép lọc chồng nhau hoặc dữ liệu liên kết ngoài vẫn có thể cho phép suy ra cá nhân. Cần kiểm soát dimension, cardinality, chính sách truy vấn và người được phép truy cập.

## 13. Security và privacy: không chỉ lọc một vài cột

### 13.1. Phân loại dữ liệu và data minimization

Trước khi công bố, phân loại ít nhất:

- **Dữ liệu công khai theo nghiệp vụ:** trạng thái đơn của chủ đơn, tên sản phẩm công khai.
- **Dữ liệu định danh/cá nhân:** địa chỉ, số điện thoại, email, ID khách và metadata có thể liên kết.
- **Dữ liệu nhạy cảm nội bộ:** fraud score, ghi chú hỗ trợ, quy tắc giá, thông tin vận hành.
- **Bí mật/credentials:** token thanh toán, khóa API, password hash, secret và thông tin truy cập.
- **Dữ liệu phân tích:** metric đã được định nghĩa, có thể cần tổng hợp hoặc giả danh hóa.

Không chỉ xem tên trường. **Một tập dữ liệu được cho là vô hại có thể trở thành nhạy cảm khi ghép với dữ liệu khác.** Chính sách công bố cần bao gồm mục đích, đối tượng nhận, thời hạn giữ, khả năng chuyển tiếp và xóa.

### 13.2. Trường hợp cần xem địa chỉ đầy đủ

Nếu customer phải xem địa chỉ đã chọn khi xác nhận đơn, API có thể công bố **shippingAddressAtConfirmation** cho đúng chủ đơn theo quyền. Nhưng sự kiện **OrderShippingStarted** chung cho nhiều consumer không nên mang địa chỉ nếu đa số chỉ cần ID đơn và trạng thái.

Dịch vụ Logistics được ủy quyền có thể dùng một **kênh/hợp đồng riêng** để lấy đúng dữ liệu người nhận, với xác thực dịch vụ, kiểm tra mục đích, audit và retention. **Một thông điệp broadcast nhiều người nhận không phải nơi tốt để đặt PII chỉ vì một consumer cần.**

### 13.3. Đầu ra, log, cache và lỗi đều là nơi có thể rò dữ liệu

Cần kiểm tra:

- **API response và error body:** không lộ SQL query, tên bảng, stack trace, token hoặc trạng thái nội bộ.
- **Access log/APM/tracing:** không ghi tràn body chứa địa chỉ, giá nhạy cảm hoặc headers xác thực.
- **Cache và CDN:** cache key có tenant/user phù hợp, chính sách riêng tư, thời hạn và vô hiệu hóa.
- **Dead-letter queue / broker:** payload, retention, phân quyền, replay và xóa.
- **Export CSV/report:** lọc cột/đối tượng, kiểm soát tải xuống, watermark và audit.
- **Backup:** có thời hạn lưu và cơ chế quản lý dữ liệu phù hợp với chính sách.
- **Môi trường kiểm thử:** tránh copy dữ liệu thật sang nơi quyền yếu nếu không có quy trình bảo vệ.

Lược bớt dữ liệu ở DTO là cần thiết, nhưng không phải toàn bộ security design. **Authorization, audit, phân vùng dữ liệu và vận hành** vẫn bắt buộc theo rủi ro.

## 14. Contract test và đối soát: ngăn rò cấu trúc từ lần refactor sau

Một API có thể tình cờ lộ field mới khi developer đổi serializer hoặc entity. Cần kiểm thử ở **ranh giới**, không chỉ kiểm thử repository.

### 14.1. Các nhóm kiểm thử API

| Nhóm | Ca cần có |
| --- | --- |
| **Schema allowlist** | JSON chỉ có field hợp đồng; không có order_pk, customer_pk, risk_score, agent_note |
| **Authorization** | Người khác tenant/chủ đơn không xem được; token vô hiệu không được đọc |
| **Output mapping** | Internal PICKING/PACKED đều công bố PROCESSING đúng nghĩa |
| **Unknown internal state** | Phát hiện trạng thái chưa có mapping, không rò giá trị nội bộ |
| **Money/time** | Decimal string giữ chính xác; timestamp có timezone; giá tại xác nhận không chạy theo Catalog |
| **Null/optional** | Delivery chưa có dữ liệu và dữ liệu bị hạn chế được xử lý theo contract |
| **Pagination** | Thứ tự ổn định, scope theo tenant, không lặp hoặc bỏ hàng |
| **Error shape** | Không lộ SQL, stack trace, nội dung nhạy cảm |
| **Version compatibility** | v1 còn dùng được khi storage đổi; v2 có semantics được tài liệu hóa |

Có thể so **tập tên key JSON** với allowlist của version; kiểm tra những field nhạy cảm vắng mặt cả khi underlying entity có giá trị. Các test nên tạo dữ liệu cố ý chứa **agent_note** và **risk_score** để chứng minh mapper không lỡ xuất chúng.

### 14.2. Kiểm thử event và consumer

- **Schema:** đúng eventType, schemaVersion, ID public, timestamp, không có field từ DB ngoài allowlist.
- **Ngữ nghĩa:** event chỉ phát khi chuyển trạng thái nghiệp vụ thực sự xảy ra.
- **Delivery:** gửi lặp cùng event ID không tạo hành động trùng; consumer xử lý event cũ hơn theo version/sequence.
- **Khôi phục:** publisher dừng sau commit vẫn có thể gửi event từ outbox; restart có thể replay.
- **Backfill:** rebuild projection từ nguồn đã xác minh không làm ghi lùi hoặc lộ trường ngoài hợp đồng.
- **Privacy:** khi cần thu hồi quyền/xóa dữ liệu, các projection, log và topic có kế hoạch xử lý.

**Đạt schema test không có nghĩa dữ liệu đúng nghiệp vụ.** Ví dụ event có trường amount kiểu decimal đúng nhưng chứa **giá niêm yết hôm nay** thay vì **giá đã chốt** vẫn là lỗi nghiêm trọng. Cần test kiểm chứng **ngữ nghĩa và nguồn chuẩn**.

### 14.3. Data lineage và metric vận hành

Một hợp đồng cần truy được:

~~~text
Public OrderView.status
  <- mapPublicStatus(orders_internal.workflow_state)
  <- Domain Order state transition

OrderShippingStarted.orderVersion
  <- orders_internal.row_version
  <- UPDATE + transactional outbox (cùng commit)

Analytics fact_order_line.net_amount
  <- order_lines_internal (snapshot đã chốt)
  <- quy tắc giảm giá phân bổ theo dòng
~~~

Với API/event/projection bất đồng bộ, nên đo:

- **Độ trễ end-to-end**, không chỉ thời gian consumer xử lý message.
- **Tỷ lệ lỗi map schema**, trạng thái enum chưa được xử lý.
- **Outbox oldest pending age**, backlog, retry và dead-letter.
- **Mismatch** giữa source và projection tại cùng version/watermark.
- **Consumer usage** theo contract/version để biết khi nào có thể ngừng v1.
- **Truy cập bị từ chối**, rò dữ liệu phát hiện qua test hoặc audit, và độ trễ thu hồi quyền.

Một event có thể được gửi đúng nhưng consumer đã dùng một phiên bản hợp đồng không còn được hỗ trợ. Vì vậy **chủ hợp đồng** và **consumer** phải phối hợp khi phát hành, không chỉ khi có lỗi.

## 15. Di trú khỏi API lộ database: làm từng bước có thể quay lại

Giả sử API cũ trả gần như nguyên hàng SQL và các client đã phụ thuộc vào **order_pk** và **workflow_state**. Không nên xóa hai trường ấy ngay trong một bản cập nhật gây hỏng hàng loạt client.

Quy trình tham khảo:

1. **Kiểm kê consumer thực tế** bằng tài liệu, code, access log có kiểm soát và trao đổi với các nhóm. Tìm những client còn dùng ID/field nội bộ.
2. **Phân loại rủi ro:** field nhạy cảm cần xử lý ưu tiên; field không nhạy cảm nhưng là coupling cần lộ trình deprecation.
3. **Định nghĩa hợp đồng mới v2:** public ID, status nghiệp vụ, money/time, quyền, lỗi, pagination và độ tươi.
4. **Tạo mapper/projection riêng**, không thay nguồn chuẩn khi chưa cần.
5. **Contract test cả v1 và v2**, test quyền, dữ liệu lịch sử và trạng thái ít gặp.
6. **Công bố v2**, chuyển client theo từng nhóm; có mapping ID cũ → public ID ở server nếu cần giai đoạn chuyển tiếp.
7. **Quan sát mức dùng v1** và sai lệch; liên hệ consumer trước khi đặt mốc ngừng.
8. **Đóng v1 theo chính sách deprecation**, loại quyền truy cập vào cấu trúc nội bộ và xóa mapping không còn cần.
9. **Refactor storage sau khi ranh giới ổn định** hoặc chạy song song phù hợp; dùng shadow read/đối soát để bảo toàn lời hứa của hợp đồng.

Nếu API cũ đã **làm lộ bí mật hoặc PII không được phép**, xử lý an ninh có thể cần nhanh hơn lịch deprecation thông thường: chặn truy cập, thu hồi token, giảm phạm vi dữ liệu và phản ứng theo quy trình sự cố. “Giữ tương thích” không phải lý do tiếp tục công bố dữ liệu trái quyền.

### 15.1. Đừng dùng dual-write làm nguồn chuẩn kép

Nếu chuyển từ PostgreSQL sang document store, có thể duy trì một **read projection** tại document store, cập nhật bằng outbox/CDC. **PostgreSQL vẫn là nguồn chuẩn** trong giai đoạn được xác định; read model không tự quyết định giá/trạng thái.

Nếu cho phép cả hai kho tự ghi và tự đồng bộ mà không có quy tắc giải quyết xung đột, sự khác biệt giá/trạng thái sẽ trở thành khó phân xử. Cần quyết định **hệ nào sở hữu lệnh ghi, hệ nào là projection**, cơ chế cutover và rollback rõ.

## 16. Chọn phạm vi hợp đồng bằng bằng chứng chứ không bằng độ tiện của SELECT *

Giả sử có ba cách phục vụ trang chi tiết đơn, số liệu **hoàn toàn giả định**:

| Thiết kế | API p95 | Dữ liệu công bố | Rủi ro/chi phí |
| --- | ---: | --- | --- |
| Trả trực tiếp row/entity nội bộ | 68 ms | Nhiều cột không cần, có risk_score và agent_note | Rò dữ liệu, phụ thuộc schema, khó refactor |
| Mapper DTO từ truy vấn có index | 75 ms | Trường được duyệt theo API | Thêm chi phí mapping/test, bảo vệ boundary |
| Read projection riêng cho OrderView | 48 ms | Trường được duyệt, có source version | Nhanh hơn nhưng có pipeline, lag, đối soát, rebuild |

**Không thể chọn phương án đầu chỉ vì p95 = 68 ms.** Nó có lỗi ranh giới và bảo mật; một số rủi ro là tiêu chí phải đáp ứng trước khi cân nhắc tối ưu hiệu năng.

Phương án projection có thể hữu ích nếu API thực sự gặp nút thắt hoặc dữ liệu nằm ở kho riêng; nhưng nếu truy vấn DTO đã đạt SLO và workload vừa phải, **không cần tạo thêm bản sao** chỉ để giảm vài mili giây.

Các phép đo cần có gồm **p95/p99 đọc, số query/request, độ trễ ghi, tỷ lệ lỗi mapping, độ tươi projection, tải nguồn, fan-out cập nhật, khả năng phục hồi và tần suất thay đổi hợp đồng**. Thiết kế tốt tối ưu tổng thể, không riêng một SELECT.

## 17. Checklist review trước khi công bố trường hoặc event mới

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Consumer và hành động là gì? | Use case, chủ sở hữu, mục đích sử dụng |
| Nguồn chuẩn của từng field? | Field-level authority và thời điểm |
| Có cần trường này thật không? | Allowlist theo consumer, tránh toàn bộ entity |
| Dữ liệu có nhạy cảm không? | Phân loại, quyền, retention, phạm vi chia sẻ |
| ID công khai là gì? | Định danh ổn định, không phụ thuộc PK vật lý |
| Có kiểm tra quyền theo object không? | Tenant, principal, role, BOLA/IDOR cases |
| Trường có nghĩa gì? | Status, tiền, currency, timezone, snapshot vs current |
| Có dữ liệu thiếu/NULL không? | Required/optional, trạng thái không có dữ liệu |
| Hợp đồng thay đổi thế nào? | Schema version, compatibility, consumer tests |
| Dữ liệu được phát bằng cách nào? | API, outbox/event, CDC, view, export |
| Khi sự kiện trùng/sai thứ tự? | Event ID, aggregate version, idempotency |
| Khi nguồn và bản sao lệch? | Freshness SLO, watermark và reconciliation |
| Khi refactor nội bộ? | Mapper và test bảo vệ public contract |
| Có thể thu hồi dữ liệu không? | API/cache/broker/DLQ/warehouse/log/backup |
| Khi không còn consumer? | Deprecation, usage metrics, gỡ quyền và storage phụ |

## 18. Bài tập tình huống

### Bài 1 — JSON của entity nội bộ

Một endpoint dùng thư viện ORM trả toàn bộ **OrderEntity**. Hôm sau nhóm Fraud thêm thuộc tính **riskScore** vào entity; JSON của endpoint xuất hiện trường đó dù không ai sửa controller.

**Câu hỏi:** Ranh giới nào bị thiếu? Đề xuất một cách sửa ngay và một biện pháp ngăn tái diễn.

### Bài 2 — UUID có thay thế quyền truy cập không?

API dùng **UUID** thay cho ID số tuần tự. Một khách sao chép UUID đơn của khách khác và GET endpoint vẫn trả nội dung vì service chỉ tìm theo UUID.

**Câu hỏi:** Hệ thống đã cải thiện điều gì, nhưng thiếu bảo vệ gì? Viết điều kiện truy vấn nghiệp vụ cần có.

### Bài 3 — Vận chuyển chỉ cần biết đã sẵn sàng giao

Logistics nhận toàn bộ **orders_internal**, bao gồm giá, risk score, ghi chú và ID khách. Thực tế nó chỉ cần ID đơn, mốc bàn giao và mã kiện; địa chỉ được lấy qua một dịch vụ giao riêng khi cần.

**Câu hỏi:** Chọn các trường event nào? Có nên phát địa chỉ trong event chung cho mọi subscriber không?

### Bài 4 — Đổi mô hình lưu trữ

Nhóm Order chuyển từ PostgreSQL gồm **orders + order_lines** sang MongoDB document có array **items**. Client trước đây dùng DTO chỉ có **orderId, status, total, items** với ngữ nghĩa ổn định.

**Câu hỏi:** Có nhất thiết thay API version không? Những test nào cần chạy trước khi chuyển đọc?

### Bài 5 — Thêm trạng thái workflow mới

Nội bộ có **PICKING** và **PACKED**, đều map thành **PROCESSING**. Nhóm kho thêm trạng thái **WAITING_WAREHOUSE_RECHECK**. Một client public không hỗ trợ enum mới.

**Câu hỏi:** Nên xử lý thế nào để không lộ trạng thái nội bộ và vẫn đúng nghiệp vụ?

### Bài 6 — CDC row đưa thẳng lên broker

Một consumer phân tích subscribe CDC của **orders_internal** và dùng các trường **order_pk**, **workflow_state** và **updated_at** làm hợp đồng. Nhóm Order đổi khóa, tách trạng thái và thêm partition.

**Câu hỏi:** Vì sao consumer bị ảnh hưởng dù “chỉ là refactor DB”? Nên thay bằng hợp đồng hoặc tầng mapping nào?

### Bài 7 — Event bị phát lại sau crash

Transaction đổi đơn sang **IN_TRANSIT** và ghi outbox đã commit. Publisher gửi message thành công, nhưng chết trước khi cập nhật **published_at**, nên gửi lại cùng event sau khởi động.

**Câu hỏi:** Đây có phải lỗi chứng minh outbox vô dụng? Consumer phải có đặc tính gì?

### Bài 8 — Giá trị đơn hay tiền đã thu?

API công bố **total** là **giá trị đơn tại xác nhận**. Đội Analytics lấy **total** này làm tiền thực thu, trong khi một số đơn thanh toán nhiều đợt hoặc đã refund.

**Câu hỏi:** Lỗi là do kiểu dữ liệu hay ngữ nghĩa? Thiết kế hợp đồng số liệu nào rõ hơn?

### Bài 9 — Sửa API cũ không thể cắt ngay

API v1 đang lộ **order_pk**, và một số đối tác ngoài còn sử dụng nó. Nhóm muốn bỏ field trong một ngày. Không có log thể hiện phiên bản client.

**Câu hỏi:** Hãy đề xuất các bước an toàn để giảm rò schema mà vẫn quản lý việc chuyển đổi.

### Gợi ý lời giải

1. Thiếu **API DTO và allowlist mapping** độc lập với ORM entity. Cần ngừng serialize entity thẳng, công bố response có trường được duyệt, thêm contract test kiểm tra field nhạy cảm không xuất hiện; xem lại quyền endpoint và log.
2. UUID tách định danh công khai khỏi khóa database và khó đoán hơn ID tuần tự, nhưng **không phải authorization**. Truy vấn phải giới hạn **tenant và chủ sở hữu/quan hệ quyền** từ principal xác thực, ví dụ WHERE public_order_id = ? AND tenant_id = ? AND customer_pk = ?.
3. Event tối thiểu gồm **eventId, eventType, schemaVersion, orderId, orderVersion, occurredAt, shipmentId** nếu nguồn đã có ID đúng. Địa chỉ đầy đủ chỉ nên trao qua hợp đồng/kênh dành cho bên giao được ủy quyền; không broadcast PII không cần thiết.
4. **Không nhất thiết** nếu hợp đồng public giữ nguyên về field và semantics. Cần test schema/serializer, tiền/timestamp, quyền, trạng thái, tính đúng items/snapshot, thứ tự dòng, p95, lỗi và so kết quả shadow read.
5. Bổ sung mapping ở boundary sang **PROCESSING** nếu đúng nghĩa; kiểm thử nghiệp vụ và unknown state. Client vẫn chỉ thấy các public status được cam kết. Nếu trạng thái mới cần khách biết một hành động khác, hãy thiết kế hợp đồng public có version/compatibility rõ.
6. Consumer phụ thuộc **schema vật lý**, không phải hợp đồng nghiệp vụ. Tạo adapter biến CDC thành sự kiện/thực thể công bố ổn định, có public ID và ngữ nghĩa thay đổi; hoặc dùng API/event domain được duy trì bởi chủ nguồn.
7. **Không**. Outbox bảo đảm ý định phát không bị tách khỏi commit, thường vận chuyển **at least once**. Consumer phải **idempotent** theo event ID, xử lý version/order và retry; hành động không được thực hiện hai lần chỉ vì nhận lại message.
8. Sai ở **ngữ nghĩa nguồn và định nghĩa metric**. **OrderConfirmedAmount** khác **PaymentCapturedAmount** và **RefundAmount**. Nên có fact/event từ Payment cho capture/refund với grain, currency, business time và công thức net revenue rõ.
9. Kiểm kê consumer, thiết lập telemetry/usage per version, công bố v2 với public ID, tạo adapter chuyển ID cũ trong giai đoạn chuyển tiếp, contract test, thông báo deprecation, chuyển từng đối tác, theo dõi và sau đó bỏ v1. Nếu dữ liệu nhạy cảm đang lộ, ưu tiên xử lý an ninh ngay, không chờ toàn bộ lịch tương thích.

## 19. Ghi nhớ

**Dữ liệu được lưu ở đâu và được phép công bố cho ai là hai quyết định khác nhau.** Bảng, document, graph node hay fact trong kho phân tích được tối ưu cho lưu trữ và xử lý; API và integration event phải được tối ưu cho **ngữ nghĩa nghiệp vụ, quyền truy cập và độ ổn định hợp đồng**.

**Công bố ít nhưng đủ:** chọn field theo use case và audience, tách ID công khai khỏi khóa vật lý, map trạng thái/tiền/thời gian rõ nghĩa, không phát toàn bộ entity hoặc CDC row như hợp đồng. Khi dữ liệu nhạy cảm cần được chia sẻ, dùng đúng phạm vi và kiểm soát quyền, không phát tán mặc định.

Trước khi đưa một field mới ra ngoài boundary, hãy trả lời: **“Consumer cần biết điều gì để làm việc gì, dữ liệu có nghĩa ở thời điểm nào, ai được phép đọc, và khi chúng ta đổi bảng hoặc database thì lời hứa này có còn đúng không?”**. Một hợp đồng có thể kiểm chứng sẽ giúp mô hình dữ liệu tiến hóa mà không kéo theo toàn bộ hệ thống tích hợp.
