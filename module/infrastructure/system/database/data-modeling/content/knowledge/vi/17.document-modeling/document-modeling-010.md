# Chuyển mô hình đơn hàng quan hệ sang mô hình tài liệu và đối chiếu đánh đổi

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định **ranh giới aggregate** của đơn hàng trước khi quyết định nhúng (*embed*) hay tham chiếu (*reference*) dữ liệu trong mô hình tài liệu.
- Chuyển một lược đồ quan hệ gồm đơn hàng, dòng hàng, sản phẩm, khách hàng và vận chuyển thành cấu trúc document phục vụ **các mẫu truy cập cụ thể**.
- Phân biệt **thông tin được chốt tại giao dịch** với thông tin hiện hành của danh mục sản phẩm hoặc khách hàng.
- Thiết kế khóa định danh, chỉ mục, phiên bản, cập nhật nguyên tử trong một document và hợp đồng nhất quán khi thao tác nhiều document/dịch vụ.
- Đánh giá chi phí đọc, ghi, tăng trưởng document, tìm kiếm đa chiều, kiểm soát tính đúng, thay đổi schema và di trú.
- Viết một bản so sánh có bằng chứng giữa mô hình quan hệ, document và phương án kết hợp, thay vì khẳng định một mô hình luôn tốt hơn.

Bài thuộc chương **Mô hình tài liệu** của **DATABASE_DATA_MODELING**. Mục tiêu của module là chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc đến khóa, chỉ mục và lược đồ vật lý; đồng thời biết đối chiếu cách tổ chức dữ liệu quan hệ, document, đồ thị và phân tích. Ví dụ dùng **PostgreSQL** làm mô hình quan hệ và cú pháp **MongoDB/mongosh** để minh họa document. Các lựa chọn cụ thể cần kiểm tra trên phiên bản hệ quản trị và workload thực tế.

## 1. Bắt đầu từ hành vi nghiệp vụ, không bắt đầu từ JSON

Giả sử một nền tảng bán hàng cần hỗ trợ:

1. Khách tạo giỏ và xác nhận một đơn có nhiều dòng sản phẩm.
2. Khi xác nhận, hệ thống **chốt tên sản phẩm, đơn giá, số lượng và địa chỉ giao hàng**.
3. Khách mở chi tiết một đơn và xem đầy đủ các dòng hàng trong **một lần gọi API**.
4. Khách xem 20 đơn gần nhất, chỉ cần ngày, trạng thái, tổng tiền.
5. Bộ phận giao vận có thể chia đơn thành nhiều kiện; trạng thái và sự kiện vận chuyển liên tục thay đổi.
6. Bộ phận thanh toán ghi nhận nhiều lần thử thanh toán, hoàn tiền và sự kiện từ nhà cung cấp.
7. Bộ phận phân tích hỏi doanh số theo sản phẩm, danh mục, ngày và trạng thái.

Nếu chỉ nhìn yêu cầu số 3, việc nhúng mọi thông tin vào document **order** có vẻ hấp dẫn. Nhưng yêu cầu số 5–7 gợi ý rằng một số tập con có vòng đời, tốc độ tăng trưởng, quyền ghi và truy vấn hoàn toàn khác.

**Câu hỏi thiết kế quan trọng nhất:** những dữ liệu nào cần được **đọc và thay đổi cùng một đơn hàng**, những dữ liệu nào là **thực thể dùng chung** và những dữ liệu nào phải được **quản lý độc lập**?

### 1.1. Bảng access pattern trước khi chọn mô hình

| Tác vụ | Điều kiện truy cập | Dữ liệu cần | Yêu cầu nhất quán |
| --- | --- | --- | --- |
| Chi tiết đơn | **order_id** | Trạng thái, địa chỉ đã chốt, các dòng, tổng tiền | Các khoản đã xác nhận phải tự nhất quán |
| Danh sách đơn của khách | **customer_id**, thời gian giảm dần | ID, thời điểm, trạng thái, tổng | Chấp nhận độ tươi theo hợp đồng của màn hình |
| Xác nhận giỏ | Giỏ/khách, sản phẩm, báo giá | Nhiều dòng, giá đã xác thực, địa chỉ | Không xác nhận đơn sai giá/tổng |
| Hủy đơn | ID và trạng thái hiện tại | Trạng thái đơn, lý do | Tránh hai luồng chuyển trạng thái mâu thuẫn |
| Cập nhật hành trình kiện | **shipment_id** | Sự kiện giao nhận | Có thể tăng lâu dài, nguồn từ giao vận |
| Xác nhận thanh toán | **payment_attempt_id**, sự kiện từ nhà cung cấp | Trạng thái/ledger thanh toán | Chống ghi trùng, không ghi nhận tiền sai |
| Báo cáo doanh số | Ngày, sản phẩm, loại tiền, trạng thái | Nhiều đơn và dòng hàng | Công thức, thời điểm và grain rõ |

Quyết định embed/reference phải dựa trên bảng này cùng **kích thước phân bố thực tế**: trung vị/p95/p99 số dòng đơn, số kiện, số sự kiện vận chuyển, số lần đọc và số lần cập nhật. Không nên chọn dựa vào một đơn hàng nhỏ minh họa rồi mặc định áp dụng được cho đơn hàng có hàng chục nghìn dòng.

## 2. Điểm xuất phát: mô hình quan hệ chuẩn hóa

Trong mô hình quan hệ, thực thể và quan hệ có thể được biểu diễn như sau:

~~~text
customers 1 ─── N orders 1 ─── N order_items N ─── 1 catalog_products
                     |
                     + ─── N payment_attempts
                     |
                     + ─── N shipments 1 ─── N shipment_events
~~~

Đường nối **order_items → catalog_products** nhận diện sản phẩm đã mua, **không** nói rằng giá hiện tại của sản phẩm là giá đã mua. Giá thực tế chốt trên dòng hàng vẫn cần được lưu theo ngữ nghĩa giao dịch.

Một lược đồ PostgreSQL thu gọn:

~~~sql
CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE catalog_products (
    product_id TEXT PRIMARY KEY,
    current_name TEXT NOT NULL,
    current_unit_price NUMERIC(18, 2) NOT NULL
        CHECK (current_unit_price >= 0),
    currency CHAR(3) NOT NULL
);

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    client_request_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('CONFIRMED', 'SHIPPED', 'CANCELLED')),
    currency CHAR(3) NOT NULL,
    ship_to_name_at_confirmation TEXT NOT NULL,
    ship_to_line1_at_confirmation TEXT NOT NULL,
    ship_to_city_at_confirmation TEXT NOT NULL,
    total_at_confirmation NUMERIC(20, 2) NOT NULL,
    UNIQUE (customer_id, client_request_id)
);

CREATE TABLE order_items (
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id TEXT REFERENCES catalog_products(product_id),
    product_name_at_confirmation TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_confirmation >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE INDEX idx_orders_customer_recent
    ON orders (customer_id, confirmed_at DESC, order_id DESC);
~~~

Lược đồ chưa bao gồm bảng **payment_attempts**, **shipments** và **shipment_events** để tránh che khuất bài toán chuyển đổi. Trong hệ thống thật, các bảng ấy cần khóa riêng, ràng buộc trạng thái và quy tắc chống trùng tương ứng; không thể mặc định chúng đều là thuộc tính đơn giản của đơn hàng.

**Điểm mạnh của cách tổ chức này:** khóa chính và khóa ngoại định danh quan hệ rõ ràng, dòng hàng có thể truy vấn trực tiếp và JOIN theo tập. Một phép đổi tên sản phẩm không phải cập nhật các dòng đơn đã chốt. Truy vấn phân tích có thể tận dụng các quan hệ và chỉ mục phù hợp.

**Chi phí cần đo:** màn hình chi tiết đơn có thể dùng JOIN, truy vấn theo lô hoặc nhiều lần lấy dữ liệu. Truy vấn nhiều bảng **không mặc nhiên chậm**; PostgreSQL có thể JOIN hiệu quả nếu tập kết quả nhỏ và chỉ mục thích hợp.

### 2.1. Truy vấn quan hệ dựng chi tiết đơn

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    o.confirmed_at,
    o.status,
    o.currency,
    o.ship_to_name_at_confirmation,
    o.ship_to_line1_at_confirmation,
    o.total_at_confirmation,
    i.line_no,
    i.product_id,
    i.product_name_at_confirmation,
    i.quantity,
    i.unit_price_at_confirmation
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
WHERE o.order_id = $1
ORDER BY i.line_no;
~~~

Kết quả có một hàng cho mỗi **order_item**, nghĩa là thuộc tính của **orders** bị lặp trong result set. Ứng dụng thường gom các hàng thành một DTO có mảng dòng hàng. Với một đơn có ít dòng, chi phí này có thể nhỏ; muốn đánh giá phải đo toàn bộ API, serialization và số truy vấn thực tế.

## 3. Chọn ranh giới aggregate trước khi nhúng

Trong thiết kế hướng document, **aggregate** là một tập dữ liệu có ranh giới nhất quán và thay đổi được quản lý như một đơn vị. Aggregate **Order** thường là ứng viên phù hợp vì:

- Một đơn có danh sách dòng hàng được chấp thuận khi xác nhận.
- Màn hình chi tiết thường trả **đơn + các dòng**.
- Tổng tiền và số lượng dòng phải phù hợp với nhau theo quy tắc nghiệp vụ.
- Sau xác nhận, tên/giá của từng dòng là dữ liệu lịch sử, không chạy theo danh mục hiện hành.

Tuy nhiên, các thực thể khác có thể nằm **ngoài** aggregate đơn hàng:

- **Customer**: được dùng chung bởi nhiều đơn và có vòng đời hồ sơ độc lập.
- **CatalogProduct**: dùng chung, giá/tên hiện hành thay đổi; chỉ **ID** và snapshot đã chốt được giữ trong đơn.
- **PaymentAttempt/PaymentEvent**: có định danh idempotency, thay đổi trạng thái và yêu cầu đối soát tài chính riêng.
- **Shipment/TrackingEvent**: có thể xuất hiện nhiều kiện, nhiều lần giao và một chuỗi sự kiện kéo dài.
- **InventoryReservation**: có bất biến tồn kho liên đơn, không thể coi là trường con của một đơn mà không xử lý tranh chấp nguồn.

Phép thử hữu ích:

> Nếu xóa, tạo, sửa và đọc một nhóm dữ liệu có thể được thực hiện theo vòng đời riêng mà không cần thay toàn bộ đơn hàng, nhóm ấy có thể là thực thể/document độc lập, được nối bằng ID.

### 3.1. Embed hay reference?

| Dữ liệu | Gợi ý ban đầu | Lý do | Ngoại lệ cần xem |
| --- | --- | --- | --- |
| Dòng hàng đã chốt | **Embed trong order** | Thường đọc cùng, số lượng có giới hạn theo nghiệp vụ, cần nhất quán với tổng tiền | Đơn bán buôn có lượng dòng rất lớn hoặc xử lý độc lập từng dòng |
| Địa chỉ đã chốt | **Embed snapshot** | Phải giữ địa chỉ được chấp nhận tại sự kiện xác nhận | Nhiều shipment có địa chỉ riêng, cần snapshot trên shipment |
| **customerId** | **Reference** | Khách hàng dùng chung, hồ sơ đổi theo thời gian | Có thể nhúng thêm tên người nhận đã chốt, không nhúng mọi trường hồ sơ |
| **productId** | **Reference + snapshot tên/giá** | Dùng ID để đối chiếu; dùng giá lịch sử để giữ sự thật giao dịch | Báo giá cá nhân/thuế phải lưu theo hợp đồng giá chi tiết hơn |
| Nhiều payment attempts | **Document riêng** | Idempotency và vòng đời thanh toán độc lập | Snapshot trạng thái tổng hợp có thể để trong order nếu rõ độ tươi |
| Nhiều sự kiện tracking | **Document/collection riêng** | Danh sách có thể tăng không giới hạn, truy vấn theo kiện và thời gian | Một vài mốc ngắn gọn có thể được nhúng để hiển thị |
| Ghi chú cố định của đơn | **Có thể embed** | Ít thay đổi, cần đọc cùng đơn | Ghi chú nhạy cảm hay cần phân quyền riêng nên tách |

Đây là **điểm xuất phát**, không phải quy tắc bất biến. Quyết định cuối phụ thuộc access pattern, cardinality, kích thước document, tính nguyên tử, quyền truy cập và tần suất cập nhật.

## 4. Chuyển sang document Order: một mô hình cụ thể

Ví dụ một document trong collection **orders** của MongoDB. Đoạn sau dùng **MongoDB Extended JSON** để biểu diễn số tiền Decimal128 và thời gian:

~~~json
{
  "_id": "ord-9001",
  "customerId": "cus-42",
  "clientRequestId": "checkout-42-001",
  "confirmedAt": {"$date": "2026-11-22T01:00:00Z"},
  "status": "CONFIRMED",
  "currency": "VND",
  "shippingAddressAtConfirmation": {
    "recipientName": "Nguyễn An",
    "line1": "12 Đường Hoa",
    "city": "TP. Hồ Chí Minh",
    "countryCode": "VN"
  },
  "items": [
    {
      "lineId": "line-1",
      "productId": "prod-501",
      "productNameAtConfirmation": "Sổ tay A5",
      "quantity": 2,
      "unitPriceAtConfirmation": {"$numberDecimal": "150000.00"},
      "lineSubtotal": {"$numberDecimal": "300000.00"}
    }
  ],
  "totals": {
    "itemsSubtotal": {"$numberDecimal": "300000.00"},
    "discountTotal": {"$numberDecimal": "10000.00"},
    "shippingAmount": {"$numberDecimal": "20000.00"},
    "taxTotal": {"$numberDecimal": "0.00"},
    "grandTotal": {"$numberDecimal": "310000.00"}
  },
  "version": 1,
  "createdAt": {"$date": "2026-11-22T01:00:00Z"},
  "updatedAt": {"$date": "2026-11-22T01:00:00Z"}
}
~~~

Trong ví dụ: **300.000 − 10.000 + 20.000 + 0 = 310.000 VND**. Đây là phép tính minh họa, **chưa phải mô hình thuế/giảm giá hoàn chỉnh**. Hệ thống thật phải xác định tiền thuế, cách phân bổ discount, chính sách làm tròn, tiền tệ và quan hệ với payment capture/refund.

**Extended JSON** chỉ là cách trình bày/trao đổi. Trong MongoDB, các giá trị **$numberDecimal** tương ứng BSON **Decimal128** khi được parse phù hợp. Khi dùng mongosh, có thể tạo số tiền bằng **NumberDecimal("150000.00")**. Đừng chuyển tiền qua số dấu phẩy động JavaScript thông thường rồi kỳ vọng mọi phép tính tài chính đều chính xác; một lựa chọn khác là dùng **số nguyên đơn vị nhỏ của tiền** với quy tắc tiền tệ rõ.

### 4.1. Những quyết định quan trọng trong cấu trúc này

1. **_id = orderId**: định danh đơn toàn cục; một document đại diện một đơn.
2. **customerId**: tham chiếu đến hồ sơ hiện hành, không nhúng toàn bộ khách hàng.
3. **clientRequestId**: hỗ trợ chống tạo trùng đơn khi API bị retry; cần ràng buộc duy nhất theo phạm vi đã định.
4. **items[]**: nhúng những dòng hàng cùng vòng đời xác nhận với order, có **lineId** riêng.
5. **productId + productNameAtConfirmation + unitPriceAtConfirmation**: vừa truy được sản phẩm, vừa giữ thông tin lịch sử của giao dịch.
6. **shippingAddressAtConfirmation**: snapshot đã được khách và hệ thống xác nhận; khi khách sửa địa chỉ mặc định sau đó, trường này **không tự thay đổi**.
7. **totals**: kết quả tính từ các điều khoản đã chốt; phải có công thức và bất biến để tránh không khớp **items[]**.
8. **version**: phiên bản thay đổi của document Order dùng cho optimistic concurrency.
9. **createdAt/updatedAt**: mốc kỹ thuật, không thay thế **confirmedAt** là thời điểm nghiệp vụ.

**Không nhúng lại mọi thuộc tính sản phẩm** như kho hàng hiện tại, tồn khả dụng hay mô tả dài chỉ vì chúng đang có trong Catalog. Những thông tin hiện hành này không phải là dữ liệu lịch sử cần thiết của dòng đơn và tạo nghĩa vụ đồng bộ không cần thiết.

### 4.2. Không nhầm snapshot giá với bản sao dùng để tăng tốc

Trong document Order, **unitPriceAtConfirmation** là một **sự thật tại thời điểm xác nhận**. Nếu giá danh mục tăng, các đơn cũ vẫn giữ giá đã chốt.

Ngược lại, trong **productCards.currentPriceDisplay**, giá được nhân bản để phục vụ đọc nhanh. Khi nguồn giá hiện hành thay đổi, product card phải làm mới theo mức độ nhất quán được cam kết.

Dù cả hai có thể là giá trị 150.000 tại ngày đặt hàng, chúng **không dùng chung quy tắc cập nhật**. Việc tự động đồng bộ mọi giá trong orders theo giá catalog sẽ **viết lại lịch sử**.

## 5. Ánh xạ từ quan hệ sang document một cách có kiểm soát

| Nguồn quan hệ | Đích document/hệ thống mới | Phép chuyển đổi | Tránh nhầm lẫn |
| --- | --- | --- | --- |
| **orders.order_id** | **orders._id** | Giữ ID ổn định, bảo đảm duy nhất | Không cấp ID mới ngẫu nhiên rồi mất khả năng đối soát |
| **orders.customer_id** | **orders.customerId** | Lưu ID tham chiếu | Không copy toàn bộ hồ sơ khách |
| **orders.confirmed_at** | **orders.confirmedAt** | Chuẩn hóa thời gian tuyệt đối, giữ múi giờ/ngữ nghĩa | Không lấy thời gian migration thay thế confirmed_at |
| **orders.status** | **orders.status** | Ánh xạ trạng thái hợp lệ | Không trộn trạng thái order, payment và shipment |
| **order_items** | **orders.items[]** | Gom theo order_id, sắp theo line_no | Không bỏ dòng hoặc nhân đôi khi JOIN bảng khác |
| **order_items.product_id** | **items[].productId** | Giữ tham chiếu sản phẩm | Không dùng giá hiện hành khi dựng dòng lịch sử |
| **order_items.unit_price_at_confirmation** | **items[].unitPriceAtConfirmation** | Bảo toàn decimal/đơn vị tiền | Không chuyển qua float làm tròn sai |
| **orders.ship_to_*_at_confirmation** | **shippingAddressAtConfirmation** | Gom các trường thành object snapshot | Không lấy địa chỉ hiện hành của khách |
| **orders.total_at_confirmation** | **totals.grandTotal** | Ánh xạ sau khi xác định cùng công thức | Không coi mọi trường tên “total” có cùng nghĩa |
| **payment_attempts** | **paymentAttempts** riêng | Giữ ID, trạng thái và idempotency của payment | Không nhúng vô hạn mọi callback |
| **shipment_events** | **shipmentEvents** riêng | Giữ shipmentId, thời gian, nguồn event | Không để array lớn không giới hạn trong order |

Ánh xạ **1:N** thành một array đòi bảo đảm **gom đúng grain**: một dòng trong bảng nguồn thành một phần tử item, không phải mỗi dòng JOIN với payment tạo thêm một item. Khi gom quan hệ phức tạp, hãy tạo order và items từ nguồn đã phân định, hoặc dùng grouping với khóa duy nhất chặt chẽ.

### 5.1. Nguy cơ nhân dòng khi JOIN nhiều quan hệ 1:N

Giả sử một đơn có **3 dòng hàng** và **2 payment attempts**. Nếu viết JOIN **orders → order_items → payment_attempts**, result set có thể có **6 hàng**. Nếu chuyển thẳng mỗi hàng thành item, document sẽ có 6 dòng thay vì 3, làm tổng tiền sai.

Cách an toàn hơn là:

- Truy xuất order cùng items theo **order_id**, không trộn payment nếu không cần.
- Truy xuất payment theo **payment_id/order_id** riêng và giữ cấu trúc riêng.
- Khi backfill, đối soát **COUNT số dòng** và tổng tiền ở từng order.
- Đặt khóa **(order_id, line_no)** ở nguồn và **lineId** ổn định ở đích.

## 6. Đọc từ document: một lần lấy chi tiết, nhưng không phải mọi truy vấn đều rẻ

Truy vấn một đơn theo khóa:

~~~javascript
db.orders.findOne(
  { _id: "ord-9001" },
  {
    customerId: 1,
    confirmedAt: 1,
    status: 1,
    currency: 1,
    shippingAddressAtConfirmation: 1,
    items: 1,
    totals: 1
  }
);
~~~

Vì **items[]** đã nhúng trong order, truy vấn có thể trả đầy đủ nội dung cho màn hình chi tiết mà không cần JOIN tới bảng dòng hàng. Đây là lợi ích rõ ràng khi **đa số lượt đọc cần cả đơn và dòng hàng**.

Nhưng nếu đơn có hàng nghìn dòng và trang chỉ cần tiêu đề/tổng tiền, tải cả document lớn là lãng phí. Dùng **projection** để trả đúng trường:

~~~javascript
db.orders.find(
  { customerId: "cus-42" },
  {
    _id: 1,
    confirmedAt: 1,
    status: 1,
    currency: 1,
    "totals.grandTotal": 1
  }
)
.sort({ confirmedAt: -1, _id: -1 })
.limit(20);
~~~

Chỉ mục hỗ trợ mẫu đọc theo khách và thời gian:

~~~javascript
db.orders.createIndex(
  { customerId: 1, confirmedAt: -1, _id: -1 },
  { name: "ix_customer_recent_orders" }
);
~~~

Chỉ mục compound này là ứng viên phù hợp vì truy vấn lọc **customerId** và sắp xếp theo **confirmedAt, _id**. Nên xác minh bằng **explain** và dữ liệu thực; không cần tạo tất cả chỉ mục có thể tưởng tượng. Lưu ý: nếu ứng dụng có nhiều tenant, **tenantId** có thể phải xuất hiện trong khóa phân vùng logic, lọc và chỉ mục theo chính sách truy cập.

### 6.1. Tìm đơn theo sản phẩm: được nhưng có đánh đổi

~~~javascript
db.orders.find(
  { "items.productId": "prod-501" },
  {
    _id: 1,
    confirmedAt: 1,
    customerId: 1,
    status: 1
  }
).limit(50);
~~~

Có thể xem xét chỉ mục đa khóa (*multikey index*) trên **items.productId**:

~~~javascript
db.orders.createIndex(
  { "items.productId": 1 },
  { name: "ix_orders_item_product" }
);
~~~

Đây **không phải bằng chứng** truy vấn thống kê theo sản phẩm sẽ tốt bằng một bảng dòng hàng phẳng: nhiều phần tử array tạo thêm index entries, có thể làm chỉ mục lớn, tăng chi phí ghi và bị hạn chế ở một số dạng truy vấn/sắp xếp. Trường hợp phân tích lớn thường phù hợp hơn với **fact/order_items** riêng hoặc pipeline phân tích.

MongoDB cũng có **aggregation pipeline** và phép nối **$lookup**. Mô hình document không có nghĩa “không bao giờ nối được”; lợi ích cần đo là **đường đọc thường xuyên được thiết kế để không phải ghép nhiều nguồn**, không phải một hạn chế tuyệt đối của công nghệ.

### 6.2. Phân trang danh sách và tránh tải quá nhiều

- Danh sách đơn theo khách thường chỉ cần metadata và tổng tiền; dùng projection.
- Phân trang sâu nên xem xét **keyset/cursor pagination** dựa trên cặp thứ tự ổn định, thay vì tăng **skip** quá lớn.
- Cần bảo đảm điều kiện phân trang và sort cùng hướng với chỉ mục.
- Không lấy địa chỉ, số điện thoại, ghi chú hay toàn bộ items trong API công khai nếu màn hình không cần.

Với truy vấn document, **giảm số lần nối** là một lợi ích; **trả document quá lớn hoặc tạo quá nhiều chỉ mục** là một chi phí có thể vượt lợi ích ấy.

## 7. Cập nhật và ranh giới tính nguyên tử

MongoDB bảo đảm tính nguyên tử cho **một thao tác ghi trên một document**. Đây là một lý do quan trọng để nhúng những dữ liệu phải thay đổi cùng nhau. Tuy nhiên, tính nguyên tử chỉ giúp các trường được ghi **cùng nhau**, chứ không tự biết công thức tiền có đúng hay không.

### 7.1. Cập nhật trạng thái với optimistic concurrency

Ví dụ một lệnh hủy đơn chỉ được phép khi trạng thái hiện là **CONFIRMED** và phiên bản đang là **3**:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ord-9001",
    status: "CONFIRMED",
    version: 3
  },
  {
    $set: {
      status: "CANCELLED",
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);

if (result.matchedCount !== 1) {
  // Trạng thái/phiên bản đã thay đổi, hoặc đơn không tồn tại:
  // đọc lại và quyết định trả xung đột, idempotent response, hoặc xử lý khác.
}
~~~

**status**, **version** và **updatedAt** được thay đổi nguyên tử trong document Order. Bộ lọc theo trạng thái và version tránh việc hai worker cùng dựa vào trạng thái cũ rồi ghi đè không kiểm soát.

Tuy nhiên, **hủy đơn** có thể còn yêu cầu hoàn tiền, trả tồn kho hoặc hủy vận chuyển ở các nguồn khác. Một update trên Order **không tự thực hiện nguyên tử** những thao tác ngoài document. Chúng cần quy trình nghiệp vụ với trạng thái trung gian, transaction nhiều document trong điều kiện phù hợp, hoặc saga/outbox/bù trừ tùy kiến trúc. Không được báo “đã hoàn tiền” chỉ vì đã đổi **orders.status**.

### 7.2. Sửa giỏ trước xác nhận: phải thay đổi items và totals cùng nhau

Nếu hệ thống cho chỉnh giỏ trong document trạng thái **DRAFT**, mỗi lần đổi quantity hoặc bỏ dòng cần tính lại tổng. Một thiết kế tốt có thể:

1. Đọc phiên bản document hiện tại.
2. Xác thực quyền và trạng thái vẫn là DRAFT.
3. Tính lại **items[]** và **totals** từ báo giá có thẩm quyền; không tin tổng do client gửi.
4. Ghi **cả items và totals trong một update/replace có điều kiện version**.
5. Kiểm tra **matchedCount** và retry/reject khi có xung đột.

Ví dụ phép ghi có điều kiện (ứng dụng đã tính ra các giá trị hợp lệ):

~~~javascript
db.orders.updateOne(
  { _id: "draft-42", status: "DRAFT", version: 5 },
  {
    $set: {
      items: [
        {
          lineId: "line-1",
          productId: "prod-501",
          productNameQuoted: "Sổ tay A5",
          quantity: 3,
          quotedUnitPrice: NumberDecimal("150000.00"),
          quotedLineSubtotal: NumberDecimal("450000.00")
        }
      ],
      totals: {
        itemsSubtotal: NumberDecimal("450000.00"),
        discountTotal: NumberDecimal("0.00"),
        shippingAmount: NumberDecimal("20000.00"),
        taxTotal: NumberDecimal("0.00"),
        grandTotal: NumberDecimal("470000.00")
      },
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
~~~

Đoạn này minh họa dạng ghi, **không phải cách dựng toàn bộ đơn từ dữ liệu không tin cậy**. Trường **productNameQuoted** và **quotedUnitPrice** trên DRAFT là báo giá tạm thời; khi xác nhận cần kiểm tra lại và chuyển thành **AtConfirmation** theo hợp đồng chốt đơn. Không đổi giá của các dòng **CONFIRMED** mỗi khi Catalog đổi giá.

Nếu ứng dụng dùng thao tác riêng để sửa quantity rồi sửa total sau, dù mỗi thao tác là nguyên tử, **cả chuỗi không còn nguyên tử**. Đó chính là lỗi cần tránh khi gom dữ liệu vào một document để giữ bất biến.

### 7.3. Cập nhật payment và inventory vẫn có ranh giới riêng

Ví dụ một giao dịch xác nhận đơn cùng lúc cần:

- Kiểm tra giá hiện hành hoặc báo giá hợp lệ.
- Giữ chỗ số lượng tồn kho của nhiều sản phẩm.
- Ghi order và dòng hàng.
- Tạo yêu cầu thanh toán hoặc bảo đảm idempotency với cổng thanh toán.

Những bất biến liên quan nhiều đơn, nhiều sản phẩm hoặc hệ thống ngoài **không thể được giải quyết chỉ bằng một document Order**. MongoDB hỗ trợ **giao dịch nhiều document** trong những cấu hình thích hợp, nhưng giao dịch dài, ghi đồng thời và hoạt động qua dịch vụ bên ngoài vẫn có chi phí/giới hạn. Một kiến trúc có thể cần reservation, outbox, saga và xử lý bù.

Ranh giới aggregate Order giúp đơn và dòng hàng cùng nhất quán; nó **không biến cả doanh nghiệp thành một aggregate**.

## 8. Chống tạo đơn trùng và cập nhật sai do retry

Khi client gửi request xác nhận đơn, mạng có thể timeout sau khi database đã commit. Nếu client gửi lại, không được tạo đơn thứ hai chỉ vì request được xử lý hai lần.

Giả sử mọi document Order có **customerId** và **clientRequestId** được cấp ổn định cho cùng một yêu cầu:

~~~javascript
db.orders.createIndex(
  { customerId: 1, clientRequestId: 1 },
  { unique: true, name: "ux_order_client_request" }
);
~~~

Quy tắc nghiệp vụ:

- Đảm bảo **clientRequestId** hiện diện và không rỗng khi tạo đơn trong phạm vi ràng buộc này.
- Nếu trùng, đọc đơn có cùng khóa và **so ý định nghiệp vụ**; không mặc định hai payload khác nhau là cùng yêu cầu hợp lệ.
- Trả lại kết quả đã tạo cho retry phù hợp, hoặc báo xung đột nếu thông tin không khớp.
- Nếu dùng multi-tenant, xác định phạm vi khóa riêng theo **tenantId**.

Lưu ý MongoDB có hành vi cụ thể với trường thiếu/NULL trong **unique index**; vì thế không dùng index trên một field tùy chọn rồi giả định nó cho phép vô hạn document thiếu field. Với mô hình DRAFT không có request ID, có thể cần field bắt buộc theo loại document hoặc chỉ mục **partial** phù hợp và được kiểm thử.

Để xử lý callback thanh toán lặp, cần một khóa **payment provider event ID/attempt ID** riêng tại nơi sở hữu thanh toán. Khóa chống lặp khi tạo **Order** không thay thế idempotency của luồng thu tiền.

## 9. Lược đồ tài liệu linh hoạt không đồng nghĩa không có ràng buộc

MongoDB cho phép document có cấu trúc linh hoạt hơn nhiều lược đồ quan hệ, nhưng ứng dụng vẫn cần một **schema contract**. Có thể dùng **$jsonSchema** validator để bắt lỗi thiếu field hoặc sai loại dữ liệu:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "customerId", "status", "currency",
        "items", "totals", "version"
      ],
      properties: {
        customerId: { bsonType: "string" },
        status: {
          enum: ["DRAFT", "CONFIRMED", "SHIPPED", "CANCELLED"]
        },
        currency: { bsonType: "string" },
        version: { bsonType: ["int", "long"], minimum: 1 },
        items: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: [
              "lineId", "productId", "quantity"
            ],
            properties: {
              lineId: { bsonType: "string" },
              productId: { bsonType: "string" },
              quantity: {
                bsonType: ["int", "long"],
                minimum: 1
              }
            }
          }
        },
        totals: {
          bsonType: "object",
          required: ["grandTotal"],
          properties: {
            grandTotal: { bsonType: "decimal" }
          }
        }
      }
    }
  }
});
~~~

Đây là validator **minh họa cho một collection mới**, chưa phải schema hoàn chỉnh cho mọi trạng thái. Trong ví dụ, DRAFT được phép có **items rỗng**; khi chuyển sang CONFIRMED, tầng nghiệp vụ phải kiểm tra ít nhất một dòng, đủ trường snapshot và các quy tắc tiền. Để tránh nhầm với collection có sẵn, không chạy **createCollection** nếu collection đã tồn tại; triển khai validation cho collection hiện hữu cần quy trình migration riêng.

Validator không tự chứng minh:

- **lineSubtotal = quantity × unitPriceAtConfirmation**.
- **grandTotal = subtotal − discount + shipping + tax** với đúng cách làm tròn.
- **lineId** là duy nhất **giữa các phần tử trong cùng items[]**.
- Mọi **productId/customerId** trỏ tới một thực thể hợp lệ ở collection khác.
- Trạng thái **CONFIRMED** chỉ được tạo sau khi giá và tồn kho được xác nhận.

Những bất biến này cần thiết kế ở tầng domain và kiểm thử, hoặc cơ chế dữ liệu phù hợp. Đặc biệt, **unique multikey index** không nên được hiểu là tự cấm hai phần tử trong **cùng một document** có cùng lineId; quy tắc duy nhất nội bộ mảng phải được kiểm soát rõ.

### 9.1. Schema version và dữ liệu cũ

Trong quá trình tiến hóa, document Order cũ có thể thiếu **shippingAddressAtConfirmation.countryCode** hoặc dùng tên field **subtotal** thay cho **itemsSubtotal**.

Hai chiến lược phổ biến:

- **Đọc tương thích:** ứng dụng đọc nhiều phiên bản schema và chuyển đổi về một DTO thống nhất.
- **Migration có kiểm soát:** thêm field mới, backfill từ nguồn đáng tin, theo dõi version và ngừng đọc schema cũ khi hoàn tất.

Nếu có trường **schemaVersion**, nó là phiên bản **cấu trúc**, khác với **version** dùng cho optimistic concurrency. Không nên dùng một số phiên bản cho cả hai mục đích rồi suy rằng thay đổi schema và cập nhật đơn có cùng thứ tự.

Đối với đơn lịch sử thiếu giá/địa chỉ đã chốt, **không lấy giá hoặc địa chỉ hôm nay để lấp vào như sự thật giao dịch** nếu không có chứng cứ. Đánh dấu chưa xác minh và tìm hóa đơn, báo giá, log thanh toán hoặc dữ liệu lịch sử đáng tin khi backfill.

## 10. Đối chiếu chi phí đọc, ghi và kích thước document

Một document chứa nhiều dòng có thể tiết kiệm một số bước ghép dữ liệu, nhưng tăng lượng dữ liệu được lưu và cập nhật cùng một đơn. Cần đo dưới tải đại diện.

| Tiêu chí | Quan hệ với order_items riêng | Order document nhúng items | Kết hợp: Order document + payment/shipment riêng |
| --- | --- | --- | --- |
| Chi tiết một đơn | JOIN/batch, thường hiệu quả với chỉ mục | Một lần lấy document | Một lần lấy phần order, truy vấn thêm khi cần shipment/payment |
| Danh sách 20 đơn | Truy vấn bảng orders và projection cột | Truy vấn projection field của orders | Tương tự document |
| Đổi quantity trước xác nhận | Có thể sửa dòng và tính tổng trong transaction | Một update document có thể sửa items + totals | Tương tự document |
| Giá/tên đã chốt | Lưu trên từng order_item | Lưu trong phần tử items[] | Lưu trong Order |
| Thanh toán và vận chuyển | Bảng riêng, khóa/transaction rõ | Nếu nhúng không giới hạn có thể phình to | Giữ vòng đời riêng, liên kết bằng ID |
| Truy vấn theo sản phẩm/ngày | Dòng hàng phẳng thuận tiện | Cần multikey/aggregation/unwind | Có thể phát fact/read model riêng |
| Nhiều bộ phận ghi đồng thời | Có thể cập nhật các hàng riêng, vẫn có transaction/lock | Nhiều update cùng document có thể tranh chấp | Giảm tranh chấp do tách thực thể |
| Thay đổi lược đồ | Migration schema rõ | Dữ liệu cũ có nhiều hình dạng, phải có version/validation | Quản lý contract từng collection |
| Bảo đảm tham chiếu | PK/FK/UNIQUE/CHECK rõ ràng | Phụ thuộc validation và logic ứng dụng; join vẫn có | Tương tự nhưng có ranh giới trách nhiệm |
| Giới hạn kích thước | Hàng con nằm riêng | Có giới hạn kích thước BSON document | Hạn chế mảng không giới hạn |

Trong MongoDB, có giới hạn kích thước một BSON document (thông thường **16 MiB**); nhưng cần thiết kế dựa vào **phân bố số dòng và kích thước thực tế**, không chỉ dừng ở kiểm tra có vượt giới hạn cứng hay không. Một document chưa chạm giới hạn vẫn có thể tốn băng thông, bộ nhớ, contention và chi phí lập chỉ mục đáng kể.

### 10.1. Nhúng không đồng nghĩa mọi thao tác sẽ ghi lại toàn bộ document

MongoDB hỗ trợ **$set**, **$inc** và cập nhật trường con/array. Vì vậy, không nên khẳng định bất kỳ thay đổi nhỏ nào cũng bắt buộc ứng dụng tải về và thay lại toàn bộ document.

Tuy nhiên, **một document vẫn là ranh giới tranh chấp và cập nhật nguyên tử**, nên các dòng hàng được thay đổi rất thường xuyên bởi nhiều tác nhân có thể tạo contention. Việc thêm phần tử mảng, tăng kích thước document và duy trì multikey index cũng có chi phí thực tế. Cần đo thay vì suy đoán từ mô hình lưu.

### 10.2. Về khóa ngoại, JOIN và giao dịch

- PostgreSQL có **FK** giúp bảo vệ quan hệ giữa order_items và orders; MongoDB không tự tạo cùng loại FK xuyên collection chỉ vì có **productId**.
- MongoDB hỗ trợ **$lookup** trong aggregation; chuyển sang document không có nghĩa loại bỏ hoàn toàn mọi phép nối.
- MongoDB hỗ trợ **multi-document transactions** trong cấu hình phù hợp; tuy nhiên transaction có chi phí, điều kiện vận hành và không tự bao trùm hệ thống thanh toán ngoài DB.
- Một thao tác ghi document là nguyên tử, nhưng **dữ liệu có đúng nghiệp vụ không** còn phụ thuộc vào giá, totals, trạng thái, quyền và các ràng buộc ứng dụng.

Vì vậy, không nên dùng khẩu hiệu “document luôn đọc nhanh hơn relational” hoặc “relational luôn đáng tin hơn”. Cần đo **workload đúng** và đánh giá độ rõ ràng của bất biến, không chỉ số lần JOIN.

## 11. Phân tích và báo cáo: document Order chưa chắc là mô hình tốt nhất

Giả sử bộ phận phân tích muốn doanh số theo **productId** và tháng bán. Trong document Order, items nằm trong mảng. MongoDB có thể dùng **aggregation pipeline**:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: { $in: ["CONFIRMED", "SHIPPED"] }
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: {
        productId: "$items.productId",
        currency: "$currency"
      },
      soldQuantity: { $sum: "$items.quantity" },
      itemGrossAmount: { $sum: "$items.lineSubtotal" }
    }
  }
]);
~~~

Pipeline này chỉ minh họa phép tổng hợp **các dòng hàng theo productId và currency** trong tập trạng thái được chọn. Nó **không phải doanh thu ròng**: không trừ refund, chưa phân bổ discount/thuế/phí, chưa nhóm theo tháng và chưa xử lý những trường hợp hủy/điều chỉnh theo chính sách. Phải xác định công thức và thời điểm nghiệp vụ trước khi dùng số liệu trong báo cáo.

Nếu chạy phân tích toàn bộ lịch sử rất lớn nhiều lần, việc **$unwind** mọi dòng có thể đắt. Một hướng là phát **order_line_fact** hoặc bảng tổng hợp vào hệ phân tích, với grain **một dòng hàng đã chốt** và lineage về order. Khi đó mô hình giao dịch phục vụ API còn mô hình phân tích phục vụ quét/nhóm, mỗi bên có mục đích rõ.

**Không cộng trực tiếp số tiền từ nhiều currency.** Nếu đơn hàng có cả VND và USD trong hệ thống, phải nhóm theo tiền tệ hoặc quy đổi với tỷ giá, thời điểm và quy tắc làm tròn đã xác định.

### 11.1. Document và graph giải quyết bài toán khác nhau

Đơn hàng có cấu trúc aggregate tương đối rõ, thường hợp document cho đường đọc theo orderId. Truy vấn “khách nào mua chung những sản phẩm nào”, “mạng lưới giới thiệu nhiều cấp” hoặc “đường liên kết người–sản phẩm–nhà cung cấp” có thể phù hợp với mô hình graph/analytics tùy workload.

Không nên biến mọi truy vấn thành một document khổng lồ hay một đồ thị chỉ vì công nghệ hỗ trợ. Chọn mô hình dựa trên **đối tượng được đọc/ghi cùng nhau và các quan hệ cần duyệt**.

## 12. Đảm bảo dữ liệu sau khi chuyển: bất biến và đối soát

Chuyển dữ liệu không được làm mất một dòng hàng, đổi giá lịch sử hoặc tính sai tổng tiền.

### 12.1. Bất biến tối thiểu theo đơn

Với mỗi order đã xác nhận:

1. **Số dòng:** số phần tử **items[]** bằng số dòng nguồn của order.
2. **Định danh:** mỗi lineId tương ứng một **(order_id, line_no)** nguồn; không trùng trong document.
3. **Số lượng:** quantity > 0, productId/name/price mang đúng giá trị đã chốt.
4. **Tiền tệ:** các đơn giá được tính trong currency hợp lệ hoặc có quy tắc nhiều tiền rõ.
5. **Thành tiền dòng:** mỗi lineSubtotal khớp quantity × unitPriceAtConfirmation theo quy tắc làm tròn.
6. **Tổng đơn:** grandTotal khớp công thức đã chốt; phân biệt subtotal, discount, shipping, tax và refund.
7. **Địa chỉ:** shippingAddressAtConfirmation được lấy từ snapshot giao dịch, **không** lấy hồ sơ hiện hành.
8. **Tính duy nhất:** một orderId tương ứng một document, và idempotency key không sinh đơn trùng.
9. **Trạng thái:** ánh xạ đúng status và không ghi đè điều chỉnh phát sinh sau khi migration snapshot được tạo.
10. **Quyền dữ liệu:** thông tin nhạy cảm được sao chép, bảo vệ và lưu giữ theo chính sách.

Không thể dùng phép kiểm tra **document có JSON hợp lệ** thay cho các bất biến này.

### 12.2. Ví dụ đối soát số dòng ở nguồn

~~~sql
SELECT
    o.order_id,
    COUNT(i.line_no)::BIGINT AS source_line_count,
    SUM(i.quantity * i.unit_price_at_confirmation)
        AS source_items_subtotal
FROM orders AS o
LEFT JOIN order_items AS i ON i.order_id = o.order_id
GROUP BY o.order_id;
~~~

Vì LEFT JOIN trả một hàng với **i.line_no = NULL** cho đơn không có items, dùng **COUNT(i.line_no)** thay vì COUNT(*) để phân biệt 0 dòng. **SUM** trả NULL với không có dòng; nên quy định trước cách diễn giải trường hợp này thay vì âm thầm gán một con số tùy ý.

Trong MongoDB, đối soát một document cụ thể có thể xem số item và các số tiền đã lưu:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-9001" } },
  {
    $project: {
      orderId: "$_id",
      documentLineCount: { $size: "$items" },
      storedItemsSubtotal: "$totals.itemsSubtotal",
      recomputedItemsSubtotal: { $sum: "$items.lineSubtotal" },
      storedGrandTotal: "$totals.grandTotal"
    }
  }
]);
~~~

Kết quả này chỉ đối soát **số dòng và subtotal trong document**; các giá trị dòng hàng cũng có thể cùng sai. Để kiểm tra migration, phải so **lineId, quantity, đơn giá đã chốt và quy tắc tổng** với nguồn quan hệ/ chứng từ tại cùng mốc, không chỉ so hai tổng.

### 12.3. Xử lý sai lệch và dữ liệu đến muộn

Nếu dữ liệu nguồn còn thay đổi trong lúc migration, một document đã nạp có thể cũ hơn các thao tác mới. Cần có **version/checkpoint** hoặc quy tắc snapshot + bắt kịp thay đổi; không để job backfill cũ ghi đè document mới.

Khi đã phát hiện lỗi:

- Tìm sự kiện/khóa nguồn thực sự bị thiếu hoặc nhân đôi.
- Phân biệt sai do **mapping**, **công thức tính tiền**, **trùng dữ liệu từ JOIN** hay **sự kiện chưa kịp đồng bộ**.
- Tính lại từ nguồn chuẩn với mốc phù hợp; không sửa một tổng bằng tay mà không kiểm tra dòng hàng.
- Ghi nhận số bản ghi lệch, nguyên nhân, lần sửa và cách ngăn tái diễn.

## 13. Kế hoạch di trú an toàn từ quan hệ sang document

Một kế hoạch tham khảo cho hệ thống đang vận hành:

1. **Kiểm kê use case và nguồn chuẩn:** đơn/dòng đã chốt, giá, khách, payment, shipment; xác định phần nào sẽ nằm trong Order aggregate.
2. **Chốt schema contract:** trường bắt buộc, type tiền, timezone, trạng thái, version, snapshot lịch sử, giới hạn mảng.
3. **Tạo dữ liệu mẫu và bộ kiểm thử bất biến:** đơn không có dòng (nếu trạng thái cho phép), đơn nhiều dòng, tiền giảm giá, khách đổi địa chỉ, sản phẩm đổi tên, thanh toán nhiều lần.
4. **Xây pipeline backfill:** đọc các bảng nguồn có kiểm soát và gom theo **order_id**, tránh nhân dòng qua JOIN nhiều quan hệ 1:N.
5. **Chọn snapshot/checkpoint thay đổi:** có cách thu/áp dụng những thay đổi phát sinh trong lúc nạp; nếu dùng CDC/outbox thì bảo đảm nối tiếp giữa snapshot và stream.
6. **Giữ một nguồn có thẩm quyền trong giai đoạn chuyển đổi:** nếu đang dual-write, chỉ một bên quyết định sự thật; ghi lặp/trễ được đối soát, không coi cả hai là master.
7. **Đối soát tự động:** số order, số dòng, giá đã chốt, tổng tiền, status, địa chỉ, ID bị thiếu/trùng và dữ liệu mồ côi.
8. **Chạy shadow read:** đọc cả hệ cũ và mới cho một mẫu requests, so DTO theo cùng định nghĩa; không công khai kết quả sai khác khi chưa điều tra.
9. **Chuyển đọc có kiểm soát:** theo tỷ lệ traffic hoặc nhóm khách, giám sát p95/p99, số lỗi và độ tươi dữ liệu.
10. **Chuyển ghi khi đã có phương án rollback:** bảo đảm xử lý transaction xuyên nguồn liên quan, event, payment và trạng thái; có đường quay lại hoặc kế hoạch đồng bộ ngược rõ ràng.
11. **Theo dõi và gỡ thành phần cũ:** chỉ sau khi xác minh mọi API, báo cáo, batch và quy định lưu trữ không còn phụ thuộc.

Không nên chuyển cả đọc, ghi, payment, fulfillment và báo cáo sang document **trong một bước không có mốc khôi phục**. Cũng không được coi **dual-write hai database** tự động là transaction nguyên tử; thất bại một phía phải được phát hiện và xử lý.

### 13.1. Có thể chọn phương án lai thay vì chuyển hoàn toàn

Nếu **đọc chi tiết đơn** đang chậm nhưng phần thanh toán và báo cáo quan hệ hoạt động tốt, nhóm có thể:

- Giữ **PostgreSQL Orders + OrderItems** là nguồn chuẩn.
- Tạo **order_detail_documents** làm projection đọc theo orderId.
- Duy trì qua outbox/CDC, có version/lag/đối soát.
- Giữ payment, inventory và báo cáo trên nguồn/bộ mô hình phù hợp.

Phương án này làm giảm rủi ro di trú nguồn ghi nhưng tăng trách nhiệm đồng bộ projection. Chỉ chọn nếu lợi ích đọc đủ lớn và SLO độ tươi cho phép. Nếu JOIN quan hệ đã đạt SLO, không thêm projection chỉ vì document trông gọn hơn.

## 14. Thí nghiệm hiệu năng: so cùng workload, cả đọc lẫn ghi

Giả sử mục tiêu là **p95 API chi tiết đơn ≤ 120 ms**, **p95 cập nhật trạng thái ≤ 100 ms**, và thời gian tải 20 đơn gần nhất ≤ 150 ms. Các con số sau **hoàn toàn giả định để luyện phân tích**, không phải benchmark thực.

| Chỉ số giả định | Quan hệ có index và JOIN tối ưu | Document nhúng items |
| --- | ---: | ---: |
| Chi tiết đơn p95, đơn 5 dòng | 92 ms | 58 ms |
| Danh sách 20 đơn p95 | 76 ms | 71 ms |
| Đổi trạng thái order p95 | 24 ms | 31 ms |
| Đơn 1.500 dòng: thời gian đọc đầy đủ p95 | 420 ms | 540 ms |
| Số truy vấn để lấy chi tiết | Một JOIN hoặc batch | Một document |
| Rủi ro cần đo | JOIN, N+1, số lần round-trip | Kích thước document, contention, truyền tải |
| Thế mạnh phân tích theo dòng | Bảng order_items trực tiếp | Phải unwind hoặc tạo read/fact model |
| Chi phí migration và vận hành | Giữ nguồn đang có | Dữ liệu kép, mapping, kiểm thử, thay đường ghi |

Kết luận có điều kiện:

- **Document** có thể là lựa chọn tốt cho đơn nhỏ/vừa nếu đường đọc chi tiết rất thường xuyên, schema/order aggregate rõ và chiến lược vận hành phù hợp.
- **Quan hệ** đã đạt SLO của một số use case trong ví dụ; không có căn cứ chuyển mọi hệ thống chỉ để giảm số JOIN.
- Với **đơn rất lớn**, tài liệu quá to và nhiều cập nhật riêng từng dòng, thiết kế nhúng có thể kém hơn; cần đo cardinality đuôi dài.
- Với payment, inventory và analytics, phải so sánh **toàn bộ luồng nghiệp vụ**, không chỉ p95 API chi tiết đơn.

Một benchmark đúng cần cùng dữ liệu, phân bố số dòng, tỷ lệ đọc/ghi, đồng thời, chính sách cache, chỉ mục, cấu hình phần cứng và điều kiện mạng. Đo cả p50/p95/p99, throughput, I/O, CPU, lock/write conflicts, dung lượng/index, thời gian build lại và độ sai khác sau khi đồng bộ.

## 15. Checklist thiết kế trước khi chuyển mô hình

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Mẫu truy cập nào cần thay đổi? | Query, số request, latency và SLO hiện tại |
| Ranh giới Order aggregate? | Những field thay đổi/đọc cùng nhau và các bất biến |
| Nhúng dữ liệu nào? | Cardinality, kích thước, vòng đời, quyền ghi |
| Tham chiếu dữ liệu nào? | Customer/Product/Payment/Shipment độc lập |
| Giá và địa chỉ mang nghĩa nào? | Giá trị đã chốt tại sự kiện, không phải nguồn hiện hành |
| Tiền tệ, thuế, giảm giá? | Kiểu decimal/đơn vị nhỏ, công thức và làm tròn |
| Trạng thái/phiên bản? | Allowed transitions, optimistic concurrency, idempotency |
| Chỉ mục theo use case? | Explain, query shape, selectivity và chi phí index |
| Tăng trưởng document? | Phân bố items/shipment events, giới hạn kích thước |
| Truy vấn phân tích? | Grain, pipeline, fact model và currency |
| Dữ liệu đã được xác minh? | Đếm order/line, kiểm tra mapping và totals |
| Cập nhật nhiều nguồn? | Transaction/outbox/saga, rollback và phục hồi |
| Bảo vệ PII? | Phân quyền địa chỉ, thời hạn lưu, xóa/ẩn và audit |
| Có thể quay lại không? | Shadow read, chuyển traffic dần, nguồn chuẩn và kế hoạch rollback |

## 16. Bài tập vận dụng

### Bài 1 — Nhúng hay tham chiếu?

Một đơn bán lẻ có trung vị **4 dòng**, p99 **18 dòng**. Mỗi khi khách mở chi tiết, API cần đọc toàn bộ dòng và tổng tiền. Sản phẩm trong Catalog thường đổi tên và giá.

**Câu hỏi:** Có nên nhúng items[] vào document Order không? Trong mỗi item nên lưu ID hay giá/tên hiện hành?

### Bài 2 — Lịch sử thanh toán rất dài

Một đơn có thể nhận hàng nghìn webhook từ nhà cung cấp thanh toán do retry, trạng thái và nhiều payment attempts. Nhóm muốn nhúng toàn bộ webhook vào **orders.paymentEvents[]**.

**Câu hỏi:** Nguy cơ chính là gì? Nên tách hay nhúng dữ liệu nào?

### Bài 3 — JOIN tạo nhân dòng

Đơn X có 4 dòng hàng, 3 lần thử thanh toán. Pipeline migration JOIN đồng thời **order_items** và **payment_attempts**, sau đó push một phần tử items cho mỗi hàng JOIN.

**Câu hỏi:** Document có thể sinh bao nhiêu item sai? Cách phòng tránh?

### Bài 4 — Cập nhật đơn nguyên tử nhưng hoàn tiền bị bỏ sót

Một worker dùng **updateOne** chuyển Order sang **CANCELLED**. Ghi thành công, nhưng dịch vụ thanh toán lỗi và khoản tiền đã thu chưa hoàn.

**Câu hỏi:** Vì sao một thao tác ghi document nguyên tử vẫn không đủ? Cần quy trình gì?

### Bài 5 — Danh sách đơn và chỉ mục

API thường xuyên lấy 20 đơn mới nhất của một khách, chỉ cần status, confirmedAt và grandTotal; mỗi document Order có items[] lớn.

**Câu hỏi:** Query cần projection gì và chỉ mục nào là ứng viên ban đầu?

### Bài 6 — Phân tích doanh thu theo sản phẩm

Báo cáo muốn doanh thu **sau hoàn tiền**, theo tháng và currency. Một pipeline chỉ **$unwind: "$items"** rồi SUM lineSubtotal cho tất cả đơn CONFIRMED.

**Câu hỏi:** Vì sao kết quả chưa phải doanh thu ròng? Cần làm rõ nguồn và grain nào?

### Bài 7 — Schema mới thiếu lịch sử

Khi migration, nhiều dòng đơn cũ thiếu **unit_price_at_confirmation**. Nhóm định điền từ **catalog_products.current_unit_price** để mọi document thỏa validator.

**Câu hỏi:** Vì sao cách làm này rủi ro? Nếu không có chứng từ cũ thì nên làm gì?

### Gợi ý lời giải

1. **Có thể nhúng** vì dòng hàng có số lượng giới hạn và thường đọc cùng Order. Giữ **productId** để tham chiếu, đồng thời lưu **tên/giá tại xác nhận** làm sự thật lịch sử; không đồng bộ đơn cũ theo Catalog.
2. Danh sách event không giới hạn làm document phình to, tăng cập nhật/tranh chấp và trộn trách nhiệm payment với Order. Giữ **paymentAttempts/paymentEvents** riêng với ID chống trùng; trong Order có thể lưu trạng thái tóm tắt nếu có nguồn chuẩn và độ tươi rõ.
3. **4 × 3 = 12** phần tử nếu push mỗi hàng JOIN; đúng chỉ có **4** dòng. Gom theo **(order_id, line_no)**, tránh JOIN hai nhánh 1:N khi xây items, và đối soát số dòng/tổng.
4. updateOne chỉ nguyên tử **trong Order document**, không bao trùm cổng thanh toán. Cần trạng thái/chuyển tiếp có kiểm soát, idempotency cho refund, outbox/saga hoặc giao thức phù hợp, retry và đối soát thanh toán trước khi báo hoàn tất.
5. Projection chỉ lấy **_id, confirmedAt, status, totals.grandTotal**; lọc customerId, sort confirmedAt DESC + _id DESC và thử chỉ mục **{customerId:1, confirmedAt:-1, _id:-1}**. Không tải items khi không cần.
6. SUM lineSubtotal là **doanh số gộp của dòng**, chưa xét discount, refund, phí, thuế, trạng thái hủy và cách phân bổ theo kỳ. Cần payment/refund ledger hoặc các sự kiện nghiệp vụ được định nghĩa; grain theo **tháng × product × currency**, quyết định ngày ghi nhận và công thức ròng.
7. Giá hiện hành **không chứng minh giá lịch sử**. Tìm giá từ hóa đơn, chứng từ thanh toán, báo giá/lịch sử giá có hiệu lực. Nếu không thể xác minh, đánh dấu thiếu dữ liệu theo quy trình migration, tách dữ liệu cũ khỏi điều kiện bắt buộc của đơn mới thay vì bịa số tiền.

## 17. Ghi nhớ

**Chuyển mô hình đơn hàng quan hệ sang document là thiết kế lại ranh giới dữ liệu theo cách đọc và thay đổi, không phải đổi cú pháp từ hàng/cột sang JSON.** Dòng hàng và địa chỉ đã chốt có thể phù hợp để nhúng cùng Order, trong khi khách hàng hiện hành, Catalog, thanh toán, giao vận và phân tích thường có vòng đời hoặc bất biến riêng.

**Lợi ích chính** của document là đọc một aggregate đã đóng gói và cập nhật nhiều trường của cùng document nguyên tử. **Đánh đổi** gồm document tăng kích thước, cập nhật mảng/tranh chấp, thiếu bảo vệ FK xuyên collection, chi phí truy vấn theo dòng, migration và trách nhiệm xử lý nhất quán nhiều thực thể.

Trước khi chốt schema, hãy trả lời bằng số liệu và hợp đồng: **“API nào thật sự cần đọc cùng nhau, dữ liệu nào phải chốt cùng nhau, nhóm nào có thể tăng không giới hạn, và khi cần kiểm chứng hoặc phục hồi thì nguồn chuẩn ở đâu?”**. Nếu câu trả lời rõ ràng, mô hình quan hệ, document hoặc kết hợp đều có thể được chọn trên cơ sở kiểm chứng.
