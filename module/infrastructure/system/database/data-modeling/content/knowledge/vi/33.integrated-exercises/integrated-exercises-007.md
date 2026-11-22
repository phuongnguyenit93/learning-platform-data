# So sánh biểu diễn đơn hàng bằng bảng quan hệ với tài liệu

## Mục tiêu và cách thực hành

Bài học thuộc chương **Thực hành tổng hợp** của module **DATABASE_DATA_MODELING**, nơi chúng ta luyện chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, bất biến, chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; sau đó so sánh cách mô hình hóa bằng **quan hệ**, **document**, đồ thị và phân tích để chọn cấu trúc dễ tiến hóa và kiểm chứng. Chủ đề của bài là cùng một nghiệp vụ **đơn hàng** được biểu diễn bằng **các bảng quan hệ** và **một tài liệu (document) chứa các dòng đơn**.

Hoàn thành bài này, bạn cần có khả năng:

1. Phát biểu đúng **grain**, danh tính, phạm vi tenant và ranh giới nhất quán của Order, OrderLine.
2. Tạo được mô hình PostgreSQL gồm header/line, khóa chính–khóa ngoại, CHECK, chỉ mục và transaction.
3. Tạo được mô hình document nhúng OrderLine trong Order bằng cấu trúc JSON/BSON, quy tắc kiểm tra và cập nhật nguyên tử.
4. Thực hiện **cùng các truy vấn** trên hai biểu diễn và đối chiếu kết quả bằng một bộ dữ liệu mẫu.
5. Nhận diện giới hạn của cả hai: transaction đa hàng, cập nhật đồng thời, document tăng kích thước, báo cáo theo SKU và tiến hóa schema.
6. Tách **mô hình miền Java** và DTO/event khỏi lựa chọn storage; không để kiểu bảng hoặc document quyết định quyền sửa nghiệp vụ.
7. Thiết kế thử nghiệm, test và lộ trình chuyển đổi có cơ sở thay vì kết luận rằng một công nghệ luôn nhanh hoặc tốt hơn.

**Cách học:** đọc yêu cầu, tự phác hai mô hình trước khi xem phần đáp án; nhập bộ dữ liệu bằng ví dụ tương ứng; chạy truy vấn nếu có môi trường; sau đó tự giải các câu hỏi ở phần cuối. Các giá trị tiền, số lượng và workload là **giả định để học**, không phải benchmark hay chuẩn ngành.

## 1. Bài toán chung: một nguồn đơn hàng, nhiều cách lưu

Nền tảng Sales nhận đơn mua hàng trực tuyến. Một Order gồm nhiều OrderLine; mỗi dòng ghi SKU, số lượng, đơn giá **đã chốt khi đặt**, giảm giá trên một đơn vị. Ứng dụng cần:

- **Tạo và chỉnh sửa đơn nháp:** thêm/bớt dòng khi trạng thái DRAFT.
- **Xác nhận:** chỉ đơn nháp không rỗng và đã kiểm tra tiền mới chuyển CONFIRMED; sau đó dòng/giá không được sửa bởi lệnh thường.
- **Đọc chi tiết:** lấy một Order với tất cả các dòng theo (tenantId, orderId).
- **Liệt kê:** tìm đơn gần đây của một khách, phân trang theo thời gian.
- **Phân tích:** tính số lượng và giá trị đơn đã xác nhận theo SKU, theo ngày.
- **Tích hợp:** công bố OrderConfirmed cho Inventory/Notification sau khi transaction nguồn thành công.
- **An toàn:** không lấy tenantId và giá bán từ input chưa được xác thực; không để một request trùng tạo hai lần xác nhận.

Quy mô làm việc **giả định**: 10.000 đơn/ngày, trung bình 8 dòng/đơn; đa số đơn có 1–30 dòng, một ít đơn bất thường lớn hơn. Truy vấn chi tiết theo orderId thường xuyên, nhưng báo cáo theo SKU cũng cần. Đây là giả định đầu vào để **đánh giá hai mô hình**, không phải lời khẳng định về tốc độ của PostgreSQL hay MongoDB.

### Ranh giới nghiệp vụ

**Sales sở hữu** Order và những snapshot giá/giảm giá đã chốt. **Catalog** sở hữu giá niêm yết hiện tại; đổi Catalog không viết lại giá quá khứ của đơn đã xác nhận. **Inventory** sở hữu tồn kho/reservation; OrderConfirmed chưa có nghĩa StockReserved. **Payment** sở hữu kết quả thu tiền; OrderConfirmed chưa mặc nhiên là PaymentCaptured. **Analytics** có thể xây fact theo dòng bán từ các sự kiện/trạng thái nguồn, nhưng không ra lệnh chuyển trạng thái đơn.

Trong bài, giả định tiền là **số nguyên đồng VND**, chưa có thuế, phí vận chuyển hoặc quy đổi ngoại tệ. Nếu nghiệp vụ có chúng, phải mở rộng Money và các công thức, không âm thầm đổi nghĩa trường total.

## 2. Chốt grain, danh tính và bất biến trước khi chọn storage

| Khái niệm | Grain và danh tính | Ai có quyền quyết định? |
| --- | --- | --- |
| Order | Một đơn trong tenant; (tenantId, orderId) | Sales/Order aggregate |
| OrderLine | Một dòng trên Order; (tenantId, orderId, lineNo) | Sales/Order aggregate |
| Customer | Một khách hàng có ID trong nguồn Customer | Customer context; Order chỉ tham chiếu ID |
| Product/SKU | Một sản phẩm trong Catalog | Catalog; Order giữ SKU và snapshot giá |
| OrderConfirmed | Một lần chuyển trạng thái hợp lệ của Order | Sales công bố sau commit |
| FactConfirmedOrderLine | Một dòng thuộc Order đã xác nhận, trong một lần ghi nhận hợp lệ | Analytical pipeline theo grain riêng |

Các mã **T1**, **O100**, **C1**, **A**, **B** bên dưới là khóa giả lập dễ đọc. Trong ứng dụng thực, có thể dùng UUID/ULID và namespace phù hợp; quan trọng là khóa không bị mơ hồ giữa tenant và các nguồn.

Định nghĩa tiền cho một dòng \(i\):

\[
g_i=q_i p_i,\qquad d_i=q_i r_i,\qquad n_i=g_i-d_i,
\]

trong đó \(q_i\) là số lượng, \(p_i\) là đơn giá đã chốt, \(r_i\) là giảm giá **trên mỗi đơn vị**. Các bất biến:

\[
q_i>0,\qquad 0\leq r_i\leq p_i,\qquad n_i\geq0.
\]

Tổng của Order:

\[
\mathrm{gross}=\sum_i g_i,\quad
\mathrm{discount}=\sum_i d_i,\quad
\mathrm{payable}=\mathrm{gross}-\mathrm{discount}.
\]

**Quy tắc trạng thái:**

- DRAFT có thể tạm chưa có dòng, có thể thêm/bớt/sửa dòng theo command được kiểm soát.
- CONFIRMED phải có **ít nhất một dòng** và toàn bộ tiền hợp lệ; không được sửa dòng theo command DRAFT.
- CANCELLED không được xác nhận lại tự do; hoàn tiền/hủy sau giao dịch đã chốt thuộc quy trình khác có sự kiện và đối soát.
- Mọi thay đổi có thể xảy ra cạnh tranh phải được **version/lock** theo cùng Order root, không chỉ tin một trạng thái đã đọc trước đó.

Ràng buộc nhiều dòng như **tổng header bằng tổng lines** và **đơn CONFIRMED không rỗng** cần được bảo vệ bằng giao thức ghi và test, không tự xuất hiện chỉ vì đã vẽ một đường quan hệ.

## 3. Bộ dữ liệu đối chiếu chung

Sử dụng đúng ba đơn trong tenant **T1**, với giá/discount đã chốt:

| Order | Khách | Trạng thái | Dòng hàng | Gross VND | Discount VND | Payable VND |
| --- | --- | --- | --- | ---: | ---: | ---: |
| O100 | C1 | CONFIRMED | A: 2 × 120.000, giảm 10.000/đv; B: 1 × 90.000, giảm 0 | 330.000 | 20.000 | 310.000 |
| O101 | C1 | DRAFT | A: 1 × 120.000, giảm 0 | 120.000 | 0 | 120.000 |
| O102 | C2 | CONFIRMED | B: 3 × 90.000, giảm 5.000/đv | 270.000 | 15.000 | 255.000 |

**Kiểm tra bằng tay:**

\[
\begin{aligned}
O100 &: 2(120000-10000)+1(90000)=310000,\\
O101 &: 1(120000-0)=120000,\\
O102 &: 3(90000-5000)=255000.
\end{aligned}
\]

Các kết quả chuẩn sẽ dùng để đối chiếu hai cách lưu:

| Câu hỏi | Đáp án đúng |
| --- | --- |
| Chi tiết O100 | Hai dòng A và B, payable 310.000 VND |
| Danh sách đơn C1 | O101 và O100 theo createdAt mới nhất trước |
| Số Order CONFIRMED | 2 (O100, O102) |
| Tổng payable của Order CONFIRMED | **565.000 VND** |
| SKU A trong Order CONFIRMED | 2 đơn vị, gross 240.000, discount 20.000, net **220.000 VND** |
| SKU B trong Order CONFIRMED | 4 đơn vị, gross 360.000, discount 15.000, net **345.000 VND** |

**Không cộng O101 vào tổng đã xác nhận.** Cũng không đếm O100 là hai Order vì nó có hai dòng. Khóa lineNo chỉ có ý nghĩa bên trong một Order; cùng SKU có thể xuất hiện ở nhiều Order với đơn giá snapshot khác nhau.

## 4. Hai biểu diễn cạnh nhau

~~~mermaid
flowchart LR
    subgraph SQL["Quan hệ: PostgreSQL"]
        H["order_header<br/>PK tenantId + orderId"]
        L["order_line<br/>PK tenantId + orderId + lineNo"]
        H -->|"1 - N, FK"| L
    end
    subgraph DOC["Document: MongoDB"]
        O["Order document<br/>_id + tenantId + orderId"]
        I["lines: [ {lineNo, skuId,<br/>quantity, unitPriceVnd, discount} ]"]
        O -->|"nhúng 1 - N"| I
    end
~~~

Hai mô hình biểu diễn **cùng một ý nghĩa Order**, nhưng khác **đơn vị ghi vật lý**:

- Quan hệ: header và line là **nhiều row**; dùng transaction để bảo đảm cập nhật Order nhất quán.
- Document: một Order và các line hữu hạn nằm **trong một document**; thay đổi cùng document có thể nguyên tử theo khả năng engine.
- Cả hai vẫn phải phân biệt **aggregate**, **transaction**, **cross-context workflow**, **DTO**, **event** và **fact**; không lấy hình dạng storage làm chuẩn toàn hệ thống.

## 5. Lời giải A — mô hình quan hệ PostgreSQL

### 5.1. Thiết kế bảng và ràng buộc

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_header (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    gross_total_vnd BIGINT NOT NULL CHECK (gross_total_vnd >= 0),
    discount_total_vnd BIGINT NOT NULL CHECK (discount_total_vnd >= 0),
    payable_total_vnd BIGINT NOT NULL CHECK (payable_total_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (discount_total_vnd <= gross_total_vnd),
    CHECK (gross_total_vnd - discount_total_vnd = payable_total_vnd),
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    discount_per_unit_vnd BIGINT NOT NULL DEFAULT 0
        CHECK (discount_per_unit_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id),
    CHECK (discount_per_unit_vnd <= unit_price_vnd)
);

CREATE INDEX order_by_customer_recent
    ON sales.order_header
        (tenant_id, customer_id, created_at DESC, order_id DESC);

CREATE INDEX order_line_by_sku
    ON sales.order_line (tenant_id, sku_id, order_id);
~~~

**Ý nghĩa ràng buộc:**

- PK ghép tenantId vào danh tính Order, ngăn nhầm cùng orderId ở hai tenant; FK ghép tenantId tránh một line của T2 trỏ tới header T1.
- CHECK bảo vệ tính hợp lệ **trong từng row** và quan hệ tổng–discount ở header. Không có CHECK thông thường nào trên order_header tự tính được SUM của tất cả order_line.
- Với đơn CONFIRMED, confirmedAt bắt buộc. Nhưng DDL trên chưa chứng minh nó có ít nhất một line hay ngăn đổi CONFIRMED → DRAFT. Đó là giao thức domain/transaction cần bổ sung.
- Số tiền dùng BIGINT nguyên VND; khi tổng hợp nhiều dòng, chuyển phép nhân sang NUMERIC để tránh tràn số trong phép tổng lớn; application phải dùng Math.*Exact hoặc số chính xác tương ứng.
- **Các ID dạng TEXT chỉ là lựa chọn giúp ví dụ dễ đọc.** Hệ thống thật cần benchmark kiểu ID, index và namespace; có thể chọn UUID.

### 5.2. Nhập đúng bộ dữ liệu

~~~sql
BEGIN;

INSERT INTO sales.order_header (
    tenant_id, order_id, customer_id, status, currency_code,
    gross_total_vnd, discount_total_vnd, payable_total_vnd,
    version, created_at, confirmed_at
) VALUES
('T1','O100','C1','CONFIRMED','VND',
 330000,20000,310000,2,
 TIMESTAMPTZ '2026-11-20 08:00:00+00',
 TIMESTAMPTZ '2026-11-20 09:00:00+00'),
('T1','O101','C1','DRAFT','VND',
 120000,0,120000,1,
 TIMESTAMPTZ '2026-11-21 08:00:00+00',NULL),
('T1','O102','C2','CONFIRMED','VND',
 270000,15000,255000,3,
 TIMESTAMPTZ '2026-11-21 10:00:00+00',
 TIMESTAMPTZ '2026-11-21 11:00:00+00');

INSERT INTO sales.order_line (
    tenant_id, order_id, line_no, sku_id, quantity,
    unit_price_vnd, discount_per_unit_vnd
) VALUES
('T1','O100',1,'A',2,120000,10000),
('T1','O100',2,'B',1, 90000,    0),
('T1','O101',1,'A',1,120000,    0),
('T1','O102',1,'B',3, 90000, 5000);

COMMIT;
~~~

Ví dụ nhập dữ liệu đã được tính sẵn để so sánh, **không phải API cho phép client gán trực tiếp header total hay trạng thái**. Trong use case ghi thực, repository/domain phải tính các giá trị và bảo vệ transaction. Đây cũng không phải script idempotent; muốn chạy lại cần dùng database thử mới hoặc quy trình reset do người thực hành chủ động.

### 5.3. Truy vấn chi tiết, danh sách và báo cáo

~~~sql
-- Chi tiết O100: hai row, nhưng vẫn chỉ một Order.
SELECT h.order_id, h.status, h.payable_total_vnd,
       l.line_no, l.sku_id, l.quantity,
       l.unit_price_vnd, l.discount_per_unit_vnd
FROM sales.order_header AS h
JOIN sales.order_line AS l
  ON l.tenant_id = h.tenant_id AND l.order_id = h.order_id
WHERE h.tenant_id = 'T1' AND h.order_id = 'O100'
ORDER BY l.line_no;

-- Danh sách đơn của khách C1.
SELECT order_id, status, payable_total_vnd, created_at
FROM sales.order_header
WHERE tenant_id = 'T1' AND customer_id = 'C1'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

-- Phân tích các dòng của Order đã xác nhận theo SKU.
SELECT l.sku_id,
       SUM(l.quantity) AS units,
       SUM(l.quantity::NUMERIC * l.unit_price_vnd) AS gross_vnd,
       SUM(l.quantity::NUMERIC * l.discount_per_unit_vnd)
           AS discount_vnd,
       SUM(l.quantity::NUMERIC *
           (l.unit_price_vnd - l.discount_per_unit_vnd)) AS net_vnd
FROM sales.order_header AS h
JOIN sales.order_line AS l
  ON l.tenant_id = h.tenant_id AND l.order_id = h.order_id
WHERE h.tenant_id = 'T1' AND h.status = 'CONFIRMED'
GROUP BY l.sku_id
ORDER BY l.sku_id;
~~~

Kết quả nhóm theo SKU phải là **A: 2 đơn vị/net 220.000** và **B: 4 đơn vị/net 345.000**. Tổng hai nhóm là 565.000 VND. Nếu JOIN thêm nhiều PaymentAttempt của mỗi Order rồi SUM trực tiếp, tổng có thể **nhân theo số attempt**; hãy chọn đúng grain/source trạng thái đã xác nhận hoặc tổng hợp trước khi nối.

### 5.4. Đối soát header với dòng

~~~sql
WITH totals AS (
    SELECT tenant_id, order_id,
           SUM(quantity::NUMERIC * unit_price_vnd) AS gross,
           SUM(quantity::NUMERIC * discount_per_unit_vnd) AS discount
    FROM sales.order_line
    GROUP BY tenant_id, order_id
)
SELECT h.tenant_id, h.order_id,
       h.gross_total_vnd, h.discount_total_vnd,
       h.payable_total_vnd,
       t.gross AS computed_gross,
       t.discount AS computed_discount,
       t.gross - t.discount AS computed_payable
FROM sales.order_header AS h
LEFT JOIN totals AS t
  ON t.tenant_id = h.tenant_id AND t.order_id = h.order_id
WHERE h.tenant_id = 'T1'
  AND (
      t.order_id IS NULL
      OR h.gross_total_vnd IS DISTINCT FROM t.gross
      OR h.discount_total_vnd IS DISTINCT FROM t.discount
      OR h.payable_total_vnd IS DISTINCT FROM (t.gross - t.discount)
  );
~~~

Trên ba Order mẫu, truy vấn **không trả dòng nào**. Trong hệ thống thật, DRAFT có thể tạm rỗng nên phải phân loại riêng thay vì coi mọi Order không có line là dữ liệu hỏng. Đối soát bằng query là **phát hiện**, không thay thế việc bảo vệ các writer đang hoạt động.

## 6. Lời giải B — mô hình document nhúng OrderLine

Với cùng bài toán, có thể lưu **một Order là một document** trong collection orders. Các OrderLine là mảng nhúng vì chúng thường được đọc cùng Order và vòng đời được Sales/Order aggregate kiểm soát.

### 6.1. Hình dạng của một document

~~~json
{
  "_id": "T1:O100",
  "tenantId": "T1",
  "orderId": "O100",
  "customerId": "C1",
  "status": "CONFIRMED",
  "currency": "VND",
  "grossTotalVnd": 330000,
  "discountTotalVnd": 20000,
  "payableTotalVnd": 310000,
  "version": 2,
  "createdAt": "2026-11-20T08:00:00Z",
  "confirmedAt": "2026-11-20T09:00:00Z",
  "lines": [
    {
      "lineNo": 1,
      "skuId": "A",
      "quantity": 2,
      "unitPriceVnd": 120000,
      "discountPerUnitVnd": 10000
    },
    {
      "lineNo": 2,
      "skuId": "B",
      "quantity": 1,
      "unitPriceVnd": 90000,
      "discountPerUnitVnd": 0
    }
  ]
}
~~~

Đây là **JSON khái niệm** để đọc dễ. Khi lưu MongoDB thật, timestamp được biểu diễn bằng **BSON Date**, số tiền có thể dùng **BSON Int64/Decimal128** theo hợp đồng. JSON number nhìn giống nhau **không chứng minh** cùng kiểu số vật lý, precision hay giới hạn. Ví dụ mongosh bên dưới dùng NumberLong cho tiền để minh họa Int64. Không dùng float/double tùy tiện cho dữ liệu tiền.

**Ý nghĩa identity:** _id = "T1:O100" là khóa vật lý gộp namespace tenant/order theo quy ước của bài; tenantId và orderId là field giúp query và trao đổi nghiệp vụ. Nếu dùng _id là UUID toàn cục, vẫn phải kiểm tra tenant ở tất cả đường truy cập. Không xây một khóa gộp bằng nối chuỗi tùy ý nếu các phần có thể chứa dấu phân cách gây nhập nhằng; production nên dùng định dạng/encoding không mơ hồ hoặc một ID ổn định duy nhất.

### 6.2. Schema validation và chỉ mục của collection

MongoDB có thể dùng JSON Schema để kiểm tra một số ràng buộc **cấu trúc** khi ghi:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "orderId", "customerId", "status",
        "currency", "version", "grossTotalVnd",
        "discountTotalVnd", "payableTotalVnd", "lines", "createdAt"
      ],
      properties: {
        _id: { bsonType: "string" },
        tenantId: { bsonType: "string" },
        orderId: { bsonType: "string" },
        customerId: { bsonType: "string" },
        status: { enum: ["DRAFT", "CONFIRMED", "CANCELLED"] },
        currency: { enum: ["VND"] },
        version: { bsonType: "int", minimum: 0 },
        grossTotalVnd: { bsonType: "long", minimum: 0 },
        discountTotalVnd: { bsonType: "long", minimum: 0 },
        payableTotalVnd: { bsonType: "long", minimum: 0 },
        createdAt: { bsonType: "date" },
        confirmedAt: { bsonType: ["date", "null"] },
        lines: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: [
              "lineNo", "skuId", "quantity",
              "unitPriceVnd", "discountPerUnitVnd"
            ],
            properties: {
              lineNo: { bsonType: "int", minimum: 1 },
              skuId: { bsonType: "string" },
              quantity: { bsonType: "int", minimum: 1 },
              unitPriceVnd: { bsonType: "long", minimum: 0 },
              discountPerUnitVnd: { bsonType: "long", minimum: 0 }
            }
          }
        }
      }
    }
  },
  validationAction: "error"
});

db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);

db.orders.createIndex(
  { tenantId: 1, customerId: 1, createdAt: -1, orderId: -1 }
);

// Index đa khóa ứng viên cho truy vấn theo SKU, cân nhắc chi phí.
db.orders.createIndex(
  { tenantId: 1, "lines.skuId": 1, status: 1 }
);
~~~

**Những gì validator trên KHÔNG tự chứng minh:**

- discountPerUnitVnd ≤ unitPriceVnd cần so **hai field cùng phần tử mảng**; cấu trúc minh họa ở trên chỉ kiểm tra từng field không âm.
- Tổng các dòng bằng gross/discount/payable header cũng **chưa được validator bảo vệ**.
- DRAFT/CONFIRMED có trạng thái và số dòng đúng quy tắc hay không là bất biến miền.
- Không có hai lineNo giống nhau trong cùng document chưa được kiểm tra bởi mảng schema trên.
- Một người gọi có được phép đổi trạng thái/tenant hay không thuộc **authorization và command processing**, không thuộc JSON Schema.

Có thể bổ sung validator phức tạp bằng biểu thức và/hoặc ràng buộc ở tầng ứng dụng tùy phiên bản/sản phẩm, nhưng không tự giả định JSON Schema đã thay toàn bộ aggregate invariants. **Mọi đường ghi** cần tuân theo cùng quy tắc và kiểm thử.

### 6.3. Nhập bộ dữ liệu mẫu trong mongosh

~~~javascript
db.orders.insertMany([
  {
    _id: "T1:O100",
    tenantId: "T1", orderId: "O100", customerId: "C1",
    status: "CONFIRMED", currency: "VND", version: NumberInt(2),
    grossTotalVnd: NumberLong("330000"),
    discountTotalVnd: NumberLong("20000"),
    payableTotalVnd: NumberLong("310000"),
    createdAt: ISODate("2026-11-20T08:00:00Z"),
    confirmedAt: ISODate("2026-11-20T09:00:00Z"),
    lines: [
      {
        lineNo: NumberInt(1), skuId: "A", quantity: NumberInt(2),
        unitPriceVnd: NumberLong("120000"),
        discountPerUnitVnd: NumberLong("10000")
      },
      {
        lineNo: NumberInt(2), skuId: "B", quantity: NumberInt(1),
        unitPriceVnd: NumberLong("90000"),
        discountPerUnitVnd: NumberLong("0")
      }
    ]
  },
  {
    _id: "T1:O101",
    tenantId: "T1", orderId: "O101", customerId: "C1",
    status: "DRAFT", currency: "VND", version: NumberInt(1),
    grossTotalVnd: NumberLong("120000"),
    discountTotalVnd: NumberLong("0"),
    payableTotalVnd: NumberLong("120000"),
    createdAt: ISODate("2026-11-21T08:00:00Z"),
    confirmedAt: null,
    lines: [
      {
        lineNo: NumberInt(1), skuId: "A", quantity: NumberInt(1),
        unitPriceVnd: NumberLong("120000"),
        discountPerUnitVnd: NumberLong("0")
      }
    ]
  },
  {
    _id: "T1:O102",
    tenantId: "T1", orderId: "O102", customerId: "C2",
    status: "CONFIRMED", currency: "VND", version: NumberInt(3),
    grossTotalVnd: NumberLong("270000"),
    discountTotalVnd: NumberLong("15000"),
    payableTotalVnd: NumberLong("255000"),
    createdAt: ISODate("2026-11-21T10:00:00Z"),
    confirmedAt: ISODate("2026-11-21T11:00:00Z"),
    lines: [
      {
        lineNo: NumberInt(1), skuId: "B", quantity: NumberInt(3),
        unitPriceVnd: NumberLong("90000"),
        discountPerUnitVnd: NumberLong("5000")
      }
    ]
  }
]);
~~~

Mẫu này có cùng ba Order, bốn OrderLine và số tiền với PostgreSQL. Lệnh **không idempotent** vì _id đã tồn tại khi chạy lại. Sử dụng database thử riêng; không chạy chung với dữ liệu thật. Trường timestamp BSON Date mang Instant, không phải chỉ là một chuỗi tùy ý.

### 6.4. Truy vấn chi tiết và danh sách theo khách

~~~javascript
// Lấy chi tiết: một document chứa mọi line.
db.orders.findOne(
  { tenantId: "T1", orderId: "O100" },
  {
    _id: 0, orderId: 1, status: 1, payableTotalVnd: 1,
    currency: 1, lines: 1
  }
);

// Lấy các đơn của C1, mới nhất trước.
db.orders.find(
  { tenantId: "T1", customerId: "C1" },
  { _id: 0, orderId: 1, status: 1, payableTotalVnd: 1, createdAt: 1 }
).sort({ createdAt: -1, orderId: -1 }).limit(20);
~~~

**Lưu ý projection:** chỉ lấy những field cần cho use case; không trả nguyên document chỉ vì query dễ. Nếu document sau này có địa chỉ/điện thoại/cờ nội bộ, API vẫn phải áp **allowlist và quyền**.

### 6.5. Tính lại báo cáo theo SKU bằng aggregation

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T1", status: "CONFIRMED" } },
  { $unwind: "$lines" },
  {
    $group: {
      _id: "$lines.skuId",
      units: { $sum: "$lines.quantity" },
      grossVnd: {
        $sum: { $multiply: [
          "$lines.quantity", "$lines.unitPriceVnd"
        ] }
      },
      discountVnd: {
        $sum: { $multiply: [
          "$lines.quantity", "$lines.discountPerUnitVnd"
        ] }
      }
    }
  },
  {
    $project: {
      _id: 0,
      skuId: "$_id",
      units: 1,
      grossVnd: 1,
      discountVnd: 1,
      netVnd: { $subtract: ["$grossVnd", "$discountVnd"] }
    }
  },
  { $sort: { skuId: 1 } }
]);
~~~

Kết quả **phải giống SQL**: A có 2 đơn vị/net 220.000, B có 4 đơn vị/net 345.000. **$unwind tạo một hàng logic cho mỗi line trong pipeline**; nếu sau đó SUM payableTotalVnd của header, O100 sẽ bị tính hai lần. Muốn tổng theo Order, tính **trước khi unwind** hoặc dùng measure ở đúng grain.

### 6.6. Đối soát tổng tiền bên trong document

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "T1" } },
  {
    $project: {
      orderId: 1,
      storedGross: "$grossTotalVnd",
      storedDiscount: "$discountTotalVnd",
      storedPayable: "$payableTotalVnd",
      computedGross: {
        $sum: {
          $map: {
            input: "$lines", as: "l",
            in: { $multiply: ["$$l.quantity", "$$l.unitPriceVnd"] }
          }
        }
      },
      computedDiscount: {
        $sum: {
          $map: {
            input: "$lines", as: "l",
            in: { $multiply: [
              "$$l.quantity", "$$l.discountPerUnitVnd"
            ] }
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: {
        $or: [
          { $ne: ["$storedGross", "$computedGross"] },
          { $ne: ["$storedDiscount", "$computedDiscount"] },
          {
            $ne: [
              "$storedPayable",
              { $subtract: ["$computedGross", "$computedDiscount"] }
            ]
          }
        ]
      }
    }
  }
]);
~~~

Trên bộ dữ liệu sạch, pipeline đối soát cũng **không trả document nào**. Đây là cách phát hiện một document có header totals khác các dòng nhúng. Tương tự SQL, kiểm tra sau khi ghi không thay cho quy tắc ghi nguyên tử. Với lượng dữ liệu lớn cần giới hạn phạm vi kiểm tra/batch theo tenant hoặc thời gian, tránh dùng full scan không kiểm soát trên hệ thống nóng.

## 7. Cập nhật Order: cùng aggregate, khác giao thức lưu vật lý

### 7.1. Trên bảng quan hệ: lock root và ghi nhiều row cùng transaction

Giả sử client thêm một dòng cho Order DRAFT, repository phải **lấy lock hoặc kiểm tra version root** trước mọi thao tác dòng. Pseudocode transaction:

~~~sql
BEGIN;

-- Tất cả writer sửa line / confirm phải khóa cùng root trước.
SELECT status, version
FROM sales.order_header
WHERE tenant_id = :tenant_id AND order_id = :order_id
FOR UPDATE;

-- Ứng dụng xác minh status='DRAFT', version=:expected_version
-- và giá mới đã được xác thực; nếu không ROLLBACK.

INSERT INTO sales.order_line (
    tenant_id, order_id, line_no, sku_id, quantity,
    unit_price_vnd, discount_per_unit_vnd
) VALUES (
    :tenant_id, :order_id, :line_no, :sku_id, :quantity,
    :unit_price_vnd, :discount_per_unit_vnd
);

UPDATE sales.order_header
SET gross_total_vnd = gross_total_vnd + :gross_delta,
    discount_total_vnd = discount_total_vnd + :discount_delta,
    payable_total_vnd = payable_total_vnd + :payable_delta,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version
RETURNING version;

-- Chỉ COMMIT nếu INSERT hợp lệ, UPDATE đúng 1 row,
-- delta được tính chính xác và các bất biến đều PASS.
COMMIT;
~~~

**Giả định bắt buộc:** mọi đường ghi OrderLine, kể cả batch/admin, phải dùng cùng giao thức khóa root, không chỉ INSERT trực tiếp line khi header đang CONFIRMED. Dùng delta có thể hiệu quả nhưng cần đồng bộ chống trùng, kiểm tra overflow, sửa/xóa dòng và đối soát; các lệnh nguy hiểm có thể tính lại tổng từ dòng dưới lock.

Đối với lệnh confirm, ứng dụng kiểm tra root đang DRAFT, **đọc và tính tiền của tập dòng đã được bảo vệ**, cập nhật header bằng expectedVersion và ghi outbox trong cùng transaction. SQL engine không tự biết "đơn xác nhận phải có ít nhất một dòng" nếu không có constraint/trigger/procedure hay command protocol thực thi điều đó.

### 7.2. Trong document: thay cùng document nguyên tử

Với document chứa lines và totals, một lệnh updateOne có điều kiện version có thể sửa mảng và totals **trong một thao tác atomic đối với document đó**:

~~~javascript
// Ví dụ thêm một line cho O101 DRAFT version=1.
// Dòng mới: SKU B, số lượng 1, đơn giá 90000, discount 5000.
// Chỉ chạy SAU các truy vấn baseline: nó làm O101 thay đổi!
db.orders.updateOne(
  {
    tenantId: "T1", orderId: "O101",
    status: "DRAFT", version: NumberInt(1),
    "lines.lineNo": { $ne: NumberInt(2) }
  },
  {
    $push: {
      lines: {
        lineNo: NumberInt(2),
        skuId: "B", quantity: NumberInt(1),
        unitPriceVnd: NumberLong("90000"),
        discountPerUnitVnd: NumberLong("5000")
      }
    },
    $inc: {
      grossTotalVnd: NumberLong("90000"),
      discountTotalVnd: NumberLong("5000"),
      payableTotalVnd: NumberLong("85000"),
      version: NumberInt(1)
    }
  }
);
~~~

Vì version=1 và status=DRAFT nằm trong filter, hai update cạnh tranh dựa trên cùng version **không thể cùng thành công** nếu mọi writer đều tăng version. Kết quả phải kiểm tra **matchedCount=1, modifiedCount=1**; nếu không, trả conflict/đã xử lý theo command. Các delta do server/domain tính và xác minh từ một dòng hợp lệ; **không lấy trực tiếp từ request client**.

Tính nguyên tử trong **một document** không giải quyết:

- Trùng request sau timeout: cần **idempotency key/command ledger**; version conflict chỉ phát hiện cạnh tranh, không luôn trả được kết quả của retry.
- Lệnh ghi đồng thời vào **document tồn kho** hoặc **document thanh toán** khác: cần transaction nhiều document nếu engine/triển khai hỗ trợ, hoặc workflow bất đồng bộ có nguồn quyết định và bù.
- Ghi **outbox event ở collection khác**: yêu cầu transaction nhiều document hoặc một cơ chế thông báo bền vững có semantics được thiết kế rõ; atomic update Order đơn lẻ không làm outbox riêng cùng commit.
- Ràng buộc cross-document như "tổng giữ hàng không vượt tồn": vẫn phải có điểm phân xử bất biến ở Inventory, không suy ra từ việc Order chứa mảng lines.

### 7.3. Hai con đường đều có thể làm sai nếu writer bỏ giao thức

Trong PostgreSQL, một script INSERT trực tiếp order_line sau CONFIRMED có thể phá bất biến. Trong MongoDB, một script **replace toàn document** đã đọc từ nhiều giây trước có thể ghi đè version/giá/lines mới nếu không dùng conditional update. Công nghệ không tự thay thế **quyền ghi, command và quy tắc nhất quán**.

## 8. Đồng bộ API, Java, event: storage không được định nghĩa hợp đồng

Dù chọn quan hệ hay document, **miền nghiệp vụ Order** vẫn cần hành vi có kiểm soát:

~~~java
import java.util.*;

record OrderLine(int lineNo, String skuId, int quantity,
                 long unitPriceVnd, long discountPerUnitVnd) {
    OrderLine {
        Objects.requireNonNull(skuId);
        if (lineNo <= 0 || quantity <= 0 || unitPriceVnd < 0
                || discountPerUnitVnd < 0
                || discountPerUnitVnd > unitPriceVnd) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }

    long gross() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }
    long discount() {
        return Math.multiplyExact((long) quantity, discountPerUnitVnd);
    }
}

record OrderTotals(long gross, long discount, long payable) {}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }

final class Order {
    private final String id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;
    private long version;

    Order(String id) { this.id = Objects.requireNonNull(id); }

    void addLine(OrderLine line) {
        if (status != OrderStatus.DRAFT)
            throw new IllegalStateException("Order immutable");
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(x -> x.lineNo() == line.lineNo()))
            throw new IllegalArgumentException("Duplicate line number");
        // Kiểm tra overflow trước khi sửa state:
        var now = totals();
        Math.addExact(now.gross(), line.gross());
        Math.addExact(now.discount(), line.discount());
        lines.add(line);
        version++;
    }

    OrderTotals totals() {
        long gross = 0, discount = 0;
        for (OrderLine l : lines) {
            gross = Math.addExact(gross, l.gross());
            discount = Math.addExact(discount, l.discount());
        }
        return new OrderTotals(
            gross, discount, Math.subtractExact(gross, discount));
    }

    void confirm() {
        if (status != OrderStatus.DRAFT || lines.isEmpty())
            throw new IllegalStateException("Cannot confirm");
        totals();
        status = OrderStatus.CONFIRMED;
        version++;
    }

    List<OrderLine> lines() { return List.copyOf(lines); }
    OrderStatus status() { return status; }
    long version() { return version; }
    String id() { return id; }
}
~~~

Đây là Java 17 **rút gọn** minh họa bất biến. Repository cần đường **restore từ dữ liệu đã lưu** để đặt status/version và lines chính xác mà không gọi lại command làm tăng version; ví dụ không triển khai đường restore. Giá do Sales chốt theo một nguồn có thẩm quyền. Để tránh tràn số khi cộng nhiều dòng và kiểm soát điều kiện không âm, domain thực tế có thể dùng Money/NUMERIC có chính sách cụ thể.

API không nên nhận một Order đầy đủ từ client rồi save nguyên object. Thay vào đó:

~~~json
{
  "skuId": "B",
  "quantity": 1,
  "expectedVersion": 1,
  "idempotencyKey": "req-add-line-123"
}
~~~

Đây là một **AddOrderLine command DTO**; đơn giá chốt phải do application/domain xác minh và không được client tự đặt total hoặc status. Response OrderView có thể chỉ công bố ID, dòng và số tiền, không đưa version nội bộ hay dữ liệu nhạy cảm ra ngoài trừ khi use case yêu cầu.

Integration event sau confirm có thể có:

~~~json
{
  "eventId": "evt-O100-confirmed-v2",
  "eventType": "sales.order-confirmed",
  "schemaVersion": 1,
  "tenantId": "T1",
  "aggregateId": "O100",
  "aggregateVersion": 2,
  "occurredAt": "2026-11-20T09:00:00Z",
  "payload": {
    "orderId": "O100",
    "payableTotalVnd": "310000",
    "currency": "VND"
  }
}
~~~

Event là **sự thật đã commit** theo hợp đồng, không phải ảnh chụp toàn bộ row hay document. EventId giữ ổn định khi relay phát lại; aggregateVersion khác schemaVersion. Nếu Sales lưu document Order và event vào hai collection, **không** được tuyên bố cập nhật cùng document đã tự bảo đảm ghi event; phải có giải pháp outbox/transaction đúng.

## 9. Ma trận so sánh theo thao tác nghiệp vụ

| Yêu cầu | Quan hệ header + line | Document Order nhúng lines | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| Đọc **một Order đầy đủ** | JOIN hoặc đọc header rồi lines, tối ưu theo truy vấn | Một document nếu số lines và kích thước hợp lý | p95 latency, byte đọc, cache, index |
| Liệt kê **Order summary** | Query header, không phải nạp lines | Projection chỉ lấy trường cần thiết | Phân trang, sort ổn định |
| Thêm một line DRAFT | INSERT line và UPDATE header trong transaction | Atomic update mảng, totals và version trong một document | Conflict, idempotency, validation |
| Confirm một Order | Lock/version root, kiểm tra tập lines rồi ghi header | Conditional update root document | Tính đúng và outbox cùng commit |
| Báo cáo theo SKU | JOIN header/line, GROUP BY, index | Aggregation với $unwind, $group | Grain, chi phí quét lines |
| Sửa một line | Ghi row tương ứng và root/version | Positional/array update với version | Không sửa sau CONFIRMED |
| Hủy/xóa Order | Transaction, FK, retention | Xử lý document và bản sao liên quan | Hủy nghiệp vụ khác xóa vật lý |
| Order có hàng nghìn lines | Row con có thể tăng độc lập | Document tăng kích thước và tranh chấp | P99, giới hạn document |
| Đổi schema | Migration DDL, backfill | Schema/document version, đọc dữ liệu cũ | Old writer có làm mất field mới? |
| Báo cáo lịch sử dài hạn | ETL sang fact/dimension | Xuất sang fact/dimension | Lineage, late data, retention |

**Không được suy ra rằng một document luôn tương đương một lần I/O, hay một JOIN luôn chậm.** Index, cache, nén, network round-trip, query plan và chiến lược read/write quyết định kết quả. Một truy vấn SQL chỉ lấy header có thể ít byte hơn đọc một document lớn; ngược lại đọc toàn bộ Order với lines nhúng có thể tránh nhiều đường truy xuất. Cần đo với dữ liệu đại diện.

### Nguyên tắc so sánh công bằng

Hai phương án phải có cùng tập Order và số lượng lines, cùng xác suất truy vấn và write, cùng ràng buộc nghiệp vụ, chính sách quyền/tenant, yêu cầu độ bền, read consistency và độ tươi báo cáo. Phải cấu hình index hợp lý ở **cả hai**, đo trên hạ tầng phù hợp và xem p50/p95/p99 thay vì chỉ một con số trung bình.

Nếu MongoDB không kiểm soát total/version/outbox còn PostgreSQL thực hiện đủ transaction, kết quả benchmark **không so cùng một yêu cầu**. Nếu PostgreSQL bị buộc đọc toàn bộ line cho trang danh sách còn MongoDB chỉ chiếu summary, bài đo cũng bị lệch.

## 10. Chỉ mục, truy vấn và cách kiểm tra hiệu năng

### 10.1. Lấy chi tiết theo khóa

**PostgreSQL:** PK(tenant_id, order_id) tra header; PK của order_line đã có tiền tố (tenant_id, order_id), thuận tiện nạp lines. Repository có thể JOIN hoặc đọc hai truy vấn trong một giao thức nhất quán phù hợp.

**MongoDB:** có thể tìm bằng khóa vật lý _id duy nhất, hoặc dùng index duy nhất (tenantId, orderId). Nếu _id đã mã hóa định danh Order toàn cục và mọi truy vấn dùng nó, index compound thứ hai cần được đánh giá về lợi ích và chi phí.

### 10.2. Liệt kê gần đây theo khách

Quan hệ dùng index trên (tenant_id, customer_id, created_at DESC, order_id), document dùng (tenantId, customerId, createdAt DESC, orderId DESC). Với hàng triệu bản ghi, **keyset pagination** theo (createdAt, orderId) có thể phù hợp hơn OFFSET sâu. Mọi truy vấn phải giữ tenant filter; nếu dùng phân quyền ở DB thì kiểm tra cả chính sách truy cập.

### 10.3. Báo cáo theo SKU

Quan hệ có row line riêng, thuận tiện JOIN/GROUP BY khi cần. Document nhúng dùng $unwind để xử lý mỗi phần tử mảng; ở workload báo cáo lớn có thể xây **projection phân tích riêng** và giữ Order OLTP tập trung vào command. Không nên lấy một truy vấn BI hiếm gặp làm lý do duy nhất để phủ nhận hoặc chọn nhúng document.

### 10.4. Phân tích execution plan

~~~sql
-- Chỉ chạy trên môi trường thử hoặc môi trường có kiểm soát tải.
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, payable_total_vnd
FROM sales.order_header
WHERE tenant_id = 'T1' AND customer_id = 'C1'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

~~~javascript
db.orders.find(
  { tenantId: "T1", customerId: "C1" },
  { _id: 0, orderId: 1, payableTotalVnd: 1, createdAt: 1 }
).sort({ createdAt: -1, orderId: -1 }).limit(20)
  .explain("executionStats");
~~~

Những chỉ số cần xem: số row/doc/index key đã quét so với trả về; thời gian p95/p99; số round-trip; lượng dữ liệu và bộ nhớ; chi phí index khi ghi; tỷ lệ write conflict; thời gian phục hồi khi một Order tăng số line bất thường. Một chỉ mục tốt cho truy vấn A có thể làm write chậm hơn và không hỗ trợ truy vấn B. Đừng thêm index chỉ vì tên một field xuất hiện trong JSON.

## 11. Kích thước dữ liệu, aggregate và quyết định nhúng

Với giả định **10.000 Order/ngày, 8 dòng/Order**:

\[
N_{\text{Order/năm}}=10.000\times365=3.650.000,\qquad
N_{\text{Line/năm}}=3.650.000\times8=29.200.000.
\]

Trong một năm, quan hệ có khoảng **3,65 triệu header row** và **29,2 triệu line row**. Document có khoảng **3,65 triệu Order document**, mỗi document chứa trung bình tám phần tử lines. Đây là **số đơn vị logic**, không phải byte, giá thành hay tốc độ. Một document lớn chứa cả lines; row quan hệ có overhead, index và cơ chế nén khác.

### Khi nào nên nhúng?

- OrderLine phụ thuộc vòng đời Order; thường được đọc/cập nhật cùng root.
- Số lines có giới hạn thực tế và không tăng vô hạn.
- Một lệnh cần nguyên tử trên trạng thái Order và các dòng của **chính Order đó**.
- Không có các bounded context khác đòi quyền sửa độc lập từng line.
- Truy vấn toàn hệ theo SKU được phục vụ ở mức chịu được hoặc có read projection phù hợp.

### Khi nào không nên nhúng toàn bộ?

- Order có thể có hàng nghìn/hàng triệu lines, cập nhật tăng mãi.
- Nhiều worker sửa các line khác nhau của cùng Order liên tục, gây điểm nóng document.
- Mỗi line có vòng đời, retention hoặc chính sách quyền riêng khác với Order.
- Phần lớn truy vấn không cần lines, trong khi mảng thường rất lớn.
- Cần cập nhật phần tử độc lập mà vẫn bảo vệ bất biến tổng thể; phải đánh giá lại aggregate boundary và protocol.

MongoDB có **giới hạn kích thước document** và chi phí cập nhật mảng dài. Kiểm tra giới hạn thực tế của engine/phiên bản đang dùng, không thiết kế một document tăng vô hạn. Nếu tách OrderLine thành collection riêng, bài toán transaction nhiều document và ràng buộc danh tính quay lại; không thể vừa tách vật lý vừa mặc định giữ nguyên đảm bảo một-document atomic.

### Snapshot khác sao chép tùy tiện

Đơn giá và giảm giá được **chốt tại thời điểm tạo Order** là snapshot có mục đích: đổi giá Catalog sau này không được thay tiền của Order CONFIRMED. Nhưng đưa toàn bộ mô tả sản phẩm, ảnh, mọi danh mục và dữ liệu nhạy cảm của khách vào mỗi Order có thể tạo dư thừa khó cập nhật/retention. Chỉ snapshot dữ liệu thiết yếu cho **cam kết giao dịch và truy vết lịch sử**; phần còn lại giữ reference/read projection thích hợp.

## 12. Transaction, outbox và ranh giới giữa các context

Quy tắc cốt lõi giống nhau ở hai storage: **một Order chỉ được confirm sau khi miền bảo vệ bất biến; sự kiện tích hợp chỉ công bố khi thay đổi đã commit**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Sales Application
    participant D as Sales Storage
    participant R as Outbox Relay
    participant B as Broker
    participant I as Inventory

    C->>S: ConfirmOrder(orderId, expectedVersion, key)
    S->>S: Xác thực tenant, idempotency, domain rules
    S->>D: Transaction: Order CONFIRMED + outbox event
    D-->>S: Commit thành công
    S-->>C: Order CONFIRMED
    R->>D: Đọc outbox chưa phát
    R->>B: Publish với eventId E1
    B->>I: Deliver E1
    I->>I: Dedup và quyết định ReserveStock riêng
    B->>I: Có thể redeliver E1
    I->>I: Không áp dụng tác động hai lần
~~~

**Quan hệ:** cập nhật header, nếu cần sửa lines, và INSERT outbox row trong **cùng transaction PostgreSQL**. Transaction thành công không có nghĩa relay đã publish hay consumer đã xử lý.

**Document:** nếu dùng MongoDB và outbox ở collection khác, cần **multi-document transaction** được cấu hình phù hợp hoặc cơ chế thông báo bền vững có semantics tương đương. Atomic update Order document **chỉ bảo vệ những field trong document đó**. Có thể giữ pending events trong chính document, nhưng phải kiểm soát kích thước, xóa sau phát, thứ tự, relay crash và retention; không coi cách đó tự tạo exactly-once end-to-end.

**Inventory:** nguồn tồn kho có bất biến riêng. Nó nhận yêu cầu/sự kiện theo hợp đồng rồi xử lý đặt giữ dưới quyền Inventory. Sales không tự sửa tồn kho ở DB khác mà gọi đó là transaction của Order.

### Ba lỗi tích hợp dễ gặp

1. **Phát event trước commit:** Sales rollback nhưng Inventory đã hành động trên một Order chưa confirm.
2. **Gửi lại eventId mới:** relay retry bị xem là một sự thật khác, consumer có thể giữ tồn hoặc gửi email hai lần.
3. **Nhầm atomicity cục bộ với ACID toàn hệ:** Order đã confirm và Payment bị từ chối, nhưng không có trạng thái quy trình hoặc bù.

Command idempotency key và eventId là **hai danh tính khác nhau**. Retry cùng command sau commit phải tìm lại kết quả đã xử lý. Publish lại cùng occurrence phải giữ eventId cũ. Consumer cần cơ chế dedup và commit tác động cục bộ cùng bản ghi đã xử lý; các HTTP call ngoài transaction còn cần idempotency riêng.

## 13. Bảo mật, lưu trữ và truy vết

Trong cả hai mô hình, cần thiết kế:

- **Tenant isolation:** khóa, index và query có tenant; actor được xác thực. TenantId trong JSON không tự chứng minh caller có quyền.
- **Địa chỉ và dữ liệu cá nhân:** nếu cần giữ snapshot địa chỉ giao khi đặt, phải có hợp đồng về ai được đọc, thời hạn lưu, che/ẩn danh và quyền xuất; không gửi toàn bộ trong event chung.
- **Audit:** ai xác nhận đơn, version trước/sau, khi nào, lý do correction; createdAt và updatedAt đơn thuần không đủ cho mọi yêu cầu điều tra.
- **Xóa/retention:** xóa Order ở storage chính không tự xóa outbox, archive, backup và fact phân tích. Cần quy trình theo nghĩa vụ và mục đích áp dụng.
- **Snapshot giá:** Catalog đổi giá sau mua không được làm thay payable của Order đã confirm.
- **Truy vết báo cáo:** fact có nguồn, transformVersion và business-date policy; không hứa replay từng line nếu dữ liệu nguồn đã hết hạn và bị xóa.

**Nhúng document không miễn yêu cầu kiểm soát field-level exposure.** Nếu document chứa địa chỉ và thông tin kiểm soát nội bộ, controller phải trả DTO cho đúng use case, không serialize toàn document cho mọi người dùng. Nếu các nhóm field có vòng đời hoặc phân quyền khác hẳn nhau, cân nhắc lưu tách ngay cả khi chúng thường được đọc chung.

## 14. Mô hình phân tích riêng tránh làm méo storage giao dịch

Mô hình OLTP tốt cho **đọc, sửa và xác nhận Order** không nhất thiết là dạng tốt cho **tổng hợp hàng chục triệu dòng theo SKU/ngày**. Có thể tạo fact với grain:

> Một FactConfirmedOrderLine = một OrderLine của một Order đã xác nhận hợp lệ trong tenant, có snapshot tiền và confirmedAt.

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.fact_confirmed_order_line (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    sku_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    business_date DATE NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_vnd BIGINT NOT NULL CHECK (gross_vnd >= 0),
    discount_vnd BIGINT NOT NULL CHECK (discount_vnd >= 0),
    net_vnd BIGINT NOT NULL CHECK (net_vnd >= 0),
    source_order_version BIGINT NOT NULL,
    transform_version INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    CHECK (discount_vnd <= gross_vnd),
    CHECK (gross_vnd - discount_vnd = net_vnd)
);
~~~

Fact này có thể được nạp từ **PostgreSQL order_header + order_line** hoặc từ **MongoDB orders[].lines**. Hình dạng storage nguồn khác nhau, nhưng fact đích **có thể giống nhau nếu hợp đồng nghiệp vụ và metric giống nhau**.

**Giới hạn grain:** ví dụ phù hợp khi một OrderLine được ghi nhận ở trạng thái confirmed đúng một lần. Nếu có xác nhận từng phần, nhiều lần phân bổ, hủy/hoàn hoặc thay đổi sau khi chốt, cần fact theo **occurrence hoặc adjustment** với khóa riêng. Không ghi đè lịch sử giao dịch có ý nghĩa chỉ để duy trì khóa (Order, lineNo). Và OrderConfirmed **không tự đồng nghĩa** đã thu tiền; Payment sở hữu kết quả capture.

Khi xây fact:

1. Giữ khóa grain ổn định (tenant, order, lineNo) nếu đúng nghiệp vụ; replay không INSERT bản sao.
2. Chỉ lấy snapshot line ở đúng Order/version đã chốt, không lấy giá Catalog hiện hành.
3. Tính business_date từ confirmedAt và timezone/cutoff đã công bố, không dùng ngày ETL nhận.
4. Có correction/restatement hoặc adjustment versioned khi sửa lịch sử.
5. Lưu source reference, schema/transform version và watermark để đối soát.

Vì vậy, chọn quan hệ hay document cho **giao dịch** nên dựa trên truy vấn và bất biến của Order; chọn star schema, fact/dimension hay column store cho **phân tích** là một quyết định có thể tách riêng.

## 15. Bài thực hành nâng cao: chuyển đổi giữa hai biểu diễn

Một nhóm có thể bắt đầu với PostgreSQL rồi cần một read model document cho API. Nhóm khác có thể lưu document Order nhưng sau này muốn tách OrderLine ra bảng do báo cáo/khối lượng tăng. **Đổi storage không được làm mất ý nghĩa nghiệp vụ hoặc sửa ngầm lịch sử**.

### 15.1. Chuyển từ bảng quan hệ sang document

Một cách dựng biểu diễn JSON từ nguồn quan hệ (chạy theo lô có cutoff và quyền đọc thích hợp):

~~~sql
SELECT h.tenant_id, h.order_id, h.customer_id,
       h.status, h.currency_code, h.version,
       h.gross_total_vnd, h.discount_total_vnd,
       h.payable_total_vnd, h.created_at, h.confirmed_at,
       COALESCE(children.lines, '[]'::jsonb) AS lines
FROM sales.order_header AS h
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
        jsonb_build_object(
            'lineNo', l.line_no,
            'skuId', l.sku_id,
            'quantity', l.quantity,
            'unitPriceVnd', l.unit_price_vnd,
            'discountPerUnitVnd', l.discount_per_unit_vnd
        ) ORDER BY l.line_no
    ) AS lines
    FROM sales.order_line AS l
    WHERE l.tenant_id = h.tenant_id
      AND l.order_id = h.order_id
) AS children ON TRUE
WHERE h.tenant_id = :tenant_id
  AND h.order_id > :last_order_id
ORDER BY h.order_id
LIMIT :batch_size;
~~~

**Giới hạn của truy vấn minh họa:**

- Nó tạo bản JSON trung gian, **chưa phải** các document MongoDB đã được chuyển đúng BSON types, compound IDs, validator, timestamps và quyền. Chương trình ETL còn phải ánh xạ/tạo _id, NumberLong/Date và schema version.
- Nếu source thay đổi trong lúc quét nhiều lô, có thể đọc header và line ở các thời điểm khác nhau. Cần snapshot/cutoff, transaction isolation thích hợp hoặc cơ chế chụp + CDC để bảo đảm đối chiếu.
- Filter phân trang theo orderId chỉ là ví dụ **keyset trong một tenant**; khi có nhiều tenant, phải sắp xếp/đánh dấu checkpoint theo khóa đầy đủ và xử lý thay đổi đồng thời.
- Khi không có dòng, JSON thành mảng rỗng; đó là hợp lệ cho DRAFT nhưng không phù hợp cho CONFIRMED theo quy tắc đã nêu.

### 15.2. Lộ trình migrate an toàn

~~~mermaid
flowchart TB
    A["1. Định nghĩa contract<br/>grain, key, tiền, trạng thái"]
    B["2. Tạo storage mới<br/>schema, index, validator"]
    C["3. Snapshot/backfill có cutoff<br/>giữ sourceVersion"]
    D["4. CDC/replay thay đổi sau cutoff<br/>dedup, thứ tự"]
    E["5. Đối soát hai bên<br/>count, tiền, line, status"]
    F["6. Shadow read / canary<br/>đo latency và đúng"]
    G["7. Cutover quyền ghi<br/>một nguồn có thẩm quyền"]
    H["8. Theo dõi và dọn cũ<br/>sau cửa sổ an toàn"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

Ở mỗi giai đoạn:

1. **Nguồn có thẩm quyền:** quyết định rõ PostgreSQL hay MongoDB là nơi được phép xử lý command Order. Nếu có hai nơi cùng cho sửa cùng Order mà không có protocol chung, sẽ có hai sự thật cạnh tranh.
2. **Snapshot:** giữ tenant, orderId, version, status, lines, totals, timestamps. Một row/header được chuyển thành đúng một document; không phân chia nhầm Order.
3. **Catch-up:** áp dụng những thay đổi mới hơn snapshot bằng log/CDC/outbox có thứ tự và idempotency, **không coi mọi row UPDATE là một OrderConfirmed**.
4. **Đối soát:** kiểm tra số Order, tổng lines, hash/giá trị của từng Order, tổng tiền theo cùng tenant/cutoff và các trường hợp null/invalid.
5. **Shadow read:** cùng một request đọc từ cả hai hệ thống nhưng chỉ trả một nguồn cho người dùng; so sánh kết quả sau mapper, không so byte JSON vô nghĩa vì thứ tự/kiểu vật lý có thể khác.
6. **Canary:** chuyển dần nhóm request/tenant sau khi kiểm tra đồng thời, read consistency, quyền và hiệu năng.
7. **Cutover:** chuyển quyền ghi ở một thời điểm có kiểm soát; lưu bản rollback và xác định cách xử lý những command đã ghi thành công sau cutover.
8. **Cleanup:** chỉ bỏ storage/adapter cũ sau khi consumer, backup, audit, retention và khả năng restore đã được giải quyết.

### 15.3. Rủi ro dual write

Ví dụ application ghi **PostgreSQL thành công**, nhưng ghi **MongoDB timeout**. Nếu client retry bằng một command mới không cùng idempotency key, một nơi có thể có hai lines, nơi khác chỉ một. **Hai lệnh ghi trực tiếp từ client tới hai DB không phải một distributed transaction**.

Thường dễ kiểm soát hơn khi có **một nguồn được ghi**, rồi phát committed change qua outbox/CDC để xây bản sao, cùng checkpoint và reconciliation. Khi thật sự cần dual write trong giai đoạn chuyển tiếp, phải có người sở hữu và protocol phân xử chênh lệch, không gọi nó là đồng bộ tự động.

### 15.4. Chiều ngược lại: document → bảng

Nếu document Order phát triển quá lớn, có thể chuyển lines ra bảng/collection riêng. Cần:

- Giữ đúng orderId và lineNo trong namespace tenant; chống trùng khi replay.
- Tạo FK hoặc liên kết được kiểm soát, kiểm chứng line thuộc Order hợp lệ.
- Đối chiếu totals trước/sau chuyển và xử lý document không hợp lệ.
- Đảm bảo lệnh addLine/confirm không bắt đầu cập nhật theo hai giao thức khác nhau trong giai đoạn mixed-version.
- Không để old writer **replace toàn document** xóa trường/mảng mà new writer đã chuyển sang schema mới.
- Xác định cách đọc các Order cũ chưa backfill và những document có version khác nhau.

**Rollback không chỉ là quay lại binary cũ.** Sau khi có Order được ghi bằng schema mới, old binary có thể không hiểu field hoặc không giữ được version/tổng. Trong tình huống đó, chọn roll-forward hoặc chặn đường ghi nguy hiểm thay vì tự động rollback gây mất dữ liệu.

## 16. Bộ kiểm thử tương đương: cùng sự thật phải cho cùng kết quả

### 16.1. Bảng kỳ vọng chức năng

| Kiểm thử | Quan hệ | Document | Tiêu chí chung |
| --- | --- | --- | --- |
| Nạp O100 | Header + 2 lines | Một doc chứa 2 lines | Total 310.000, status CONFIRMED |
| Nạp O101 | Header + 1 line | Một doc chứa 1 line | DRAFT, total 120.000 |
| Nạp O102 | Header + 1 line | Một doc chứa 1 line | CONFIRMED, total 255.000 |
| Liệt kê C1 | Query index header | Query compound index | O101 trước O100 |
| Báo cáo SKU A | Join/filter/group | Match/unwind/group | 2 đơn vị, net 220.000 |
| Báo cáo SKU B | Join/filter/group | Match/unwind/group | 4 đơn vị, net 345.000 |
| Đối soát header/lines | Aggregate SQL | Map/reduce biểu thức | Không có bản sai tổng |
| Thêm line cho O101 v1 | Root lock + transaction | Conditional atomic document update | New version=2, total=205.000 |
| Confirm Order trống | Domain/protocol từ chối | Domain/protocol từ chối | Không có event hợp lệ |
| Sửa line sau CONFIRMED | Chặn trước ghi | Filter status và domain check | Không đổi dữ liệu |
| Hai request cùng version | Một thành công, một conflict | Một matched update, một thất bại | Không lost update |
| Cùng command retry | Idempotency ledger | Idempotency ledger | Một business effect |
| Lỗi ghi outbox | Transaction rollback | Transaction/outbox protocol rollback | Không có confirm nhưng thiếu event |
| Event redelivery | Consumer dedup | Consumer dedup | Không nhân hành động/metric |
| Tenant T2 cùng orderId O100 | PK ghép tenant | Namespace _id/compound unique | Không nhầm sang T1 |
| Giá Catalog đổi | Giữ snapshot OrderLine | Giữ snapshot embedded line | Giá Order đã confirm không đổi |
| Order có 5.000 lines | Đo index/IO/lock | Đo doc size/update contention | Không tự kết luận thắng |

### 16.2. Test sai dữ liệu có chủ ý

Tạo một bản thử có lỗi:

- quantity=0 hoặc giá âm;
- discountPerUnitVnd lớn hơn unitPriceVnd;
- hai lineNo=1 trong một Order;
- header payable sai 1 VND so với tổng lines;
- Order CONFIRMED nhưng không có line;
- caller tenant T2 thử xem Order T1;
- cùng eventId xử lý hai lần;
- dữ liệu có expectedVersion cũ.

Với quan hệ, một số lỗi bị PK/CHECK/FK chặn ngay; những lỗi nhiều hàng cần domain/transaction hoặc trigger/đối soát. Với document, JSON Schema minh họa chặn một phần sai kiểu/giới hạn nhưng **không tự chặn trùng lineNo, tổng sai hay chuyển trạng thái sai**. Cùng yêu cầu thì hai hệ thống phải có **cách ngăn hoặc phát hiện tương đương**, dù cơ chế khác nhau.

### 16.3. Test đồng thời và crash

Một test tích hợp đáng giá:

~~~text
Ban đầu: O101 là DRAFT, version=1, payable=120000.
T1 và T2 cùng đọc version 1.
T1 thêm line B, dự kiến payable mới=205000, version=2.
T2 cũng thêm line C dựa version 1.

PASS:
- Chỉ một lệnh version=1 commit;
- Lệnh còn lại nhận conflict/retry theo protocol;
- Không có header total sai hoặc document lines thiếu/cộng trùng;
- Command retry cùng idempotency key không tạo line mới;
- Không có event OrderConfirmed nếu chưa thực hiện confirm.
~~~

Với PostgreSQL, test phải dùng transaction/isolation/lock trên DB thật. Với MongoDB, test phải thực hiện updateOne có version và kiểm tra matchedCount; nếu có multi-document transaction thì cần thử cả lỗi transaction/outbox. Một mock chạy tuần tự không chứng minh được xung đột thực.

### 16.4. Property-based kiểm tra tiền và mapping

Có thể sinh nhiều dòng hợp lệ và so:

\[
\forall\ \text{Order hợp lệ}:\quad
\mathrm{gross}\ge\mathrm{discount}\ge0,\quad
\mathrm{payable}=\mathrm{gross}-\mathrm{discount}\ge0.
\]

Với mỗi Order, ánh xạ **PostgreSQL rows → canonical Order** và **MongoDB document → canonical Order**, rồi so danh tính, trạng thái, version, list lines theo lineNo, currency, amounts và thời điểm. **Không so JSON raw bằng chuỗi** vì thứ tự field hoặc cách biểu diễn BSON/SQL khác nhau mà ý nghĩa vẫn đúng.

Ngoài tiền, phải so các trường hợp **NULL/absent**, timezone, giá trị lớn vượt giới hạn số nguyên an toàn của JavaScript và các Order có nhiều line. Chọn kiểu VND nguyên chính xác ở tất cả điểm chuyển đổi, không tự động cast sang số dấu phẩy động rồi khẳng định không sai lệch.

## 17. Đề bài tự làm: so sánh trong những điều kiện thay đổi

Hãy trả lời bằng **sơ đồ/tài liệu ngắn, câu lệnh truy vấn minh họa và lập luận có kiểm chứng**. Không có yêu cầu chọn một công nghệ "tốt nhất" trong mọi bối cảnh.

### Phần A — dữ liệu và phép tính

1. **Grain và khóa:** nêu grain của order_header, order_line và Order document. Vì sao OrderLine chỉ có lineNo=1 không đủ làm khóa duy nhất toàn hệ thống? Tại sao tenant phải xuất hiện trong đường đọc và liên kết?
2. **Tính tiền:** tính gross, discount, payable cho O100, O101 và O102; tổng payable của hai Order CONFIRMED; số lượng và net theo SKU A/B. Giải thích tại sao O101 không có mặt trong báo cáo đã xác nhận.
3. **Đọc chi tiết:** viết một truy vấn SQL và một truy vấn mongosh lấy chi tiết O100; giải thích số đơn vị vật lý được đọc và số Order mà API trả.
4. **Thêm dòng và xác nhận:** O101 được thêm một dòng B, quantity=1, unitPriceVnd=90.000, discountPerUnitVnd=5.000, rồi được confirm. Hãy tính totals/version theo từng bước và các tổng báo cáo sau đó.
5. **Dữ liệu không hợp lệ:** nếu discountPerUnitVnd=130.000 nhưng unitPriceVnd=120.000, hai mô hình sẽ từ chối ở đâu? Có đủ chỉ dựa vào SQL CHECK hoặc MongoDB JSON Schema hiện tại không?

### Phần B — nhất quán và tích hợp

6. **Concurrency:** hai request cùng đọc O101 version=1 rồi cùng addLine. Mô tả giao thức khiến chỉ một request ghi thành công ở PostgreSQL và MongoDB.
7. **Nguồn có thẩm quyền:** OrderConfirmed được phát; Inventory chưa trả kết quả. Có được khẳng định hàng đã giữ thành công? Nếu Payment từ chối sau đó thì sao?
8. **Ghi outbox:** một ứng dụng lưu Order thành công nhưng crash trước publish event. Hãy phân biệt cách ghi outbox atomically trong hai mô hình.
9. **Bảo mật:** client tenant T2 biết orderId O100 thuộc T1. Nếu document dùng _id chỉ là O100, những kiểm tra nào vẫn bắt buộc? Tương tự khi SQL dùng PK orderId toàn cục?

### Phần C — kiến trúc và tiến hóa

10. **Tăng kích thước:** sản phẩm mở thêm tính năng hàng tùy biến, một Order có 20.000 dòng và nhiều worker cập nhật từng dòng. Chọn một hướng lưu có căn cứ; nếu đổi từ embed sang reference, điều gì thay đổi về transaction?
11. **Báo cáo:** nhà quản lý muốn xem số đơn đã thanh toán theo tháng và doanh thu theo SKU. Vì sao chỉ nhìn OrderConfirmed chưa đủ? Hãy đề xuất grain fact và nguồn Payment cần dùng.
12. **Migration:** hiện dùng PostgreSQL, muốn bổ sung MongoDB làm read projection cho API. Lập kế hoạch backfill, catch-up, shadow read, cutover và rollback an toàn. Có cần đổi domain Java và REST response chỉ vì storage đọc thay đổi không?
13. **Thay schema:** thêm discount theo từng đơn vị vào dữ liệu cũ chưa có discount. Khi nào có thể gán 0 cho lịch sử? Old writer thay thế document mới sẽ gây lỗi gì?
14. **Chọn kỹ thuật:** đưa ra hai hồ sơ workload: (A) đơn vài dòng, phần lớn đọc cả Order; (B) nhiều cập nhật line độc lập và báo cáo xuyên Order liên tục. Với mỗi hồ sơ, đề xuất phương án ưu tiên thử nghiệm và **ba số đo** cần có trước khi chốt.

## 18. Hướng giải chi tiết và các điểm tự kiểm

### 18.1. Grain và kết quả số học

**Câu 1:** order_header đại diện một Order theo (tenantId, orderId); order_line đại diện một dòng theo (tenantId, orderId, lineNo). Document chứa **cả aggregate Order** với mảng lines, dùng một _id ổn định cho một Order. lineNo=1 có thể tồn tại trên hàng triệu Order; tenantId phải xuất hiện trong filter/khóa để vừa nhận diện đúng vừa ngăn truy cập chéo quyền.

**Câu 2:** đáp án đối chiếu:

| Phạm vi | Gross | Discount | Payable |
| --- | ---: | ---: | ---: |
| O100 | 330.000 | 20.000 | 310.000 |
| O101 (DRAFT) | 120.000 | 0 | 120.000 |
| O102 | 270.000 | 15.000 | 255.000 |
| **CONFIRMED O100 + O102** | **600.000** | **35.000** | **565.000** |
| SKU A thuộc CONFIRMED | 240.000 | 20.000 | 220.000 |
| SKU B thuộc CONFIRMED | 360.000 | 15.000 | 345.000 |

SKU A có hai đơn vị, SKU B có bốn. O101 chưa được confirm nên không thuộc cohort xác nhận; việc nó có một line và payable tạm tính không thay trạng thái.

**Câu 3:** SQL JOIN trên cùng tenant/order trả **hai row** line của O100, nhưng mapper dựng **một OrderView** có lines gồm hai phần tử. Document query trả một Order document nếu nhúng lines; API cũng trả **một OrderView**. Một lần query hay hai row không phải là con số latency tự nhiên; còn phụ thuộc index, bytes và cách dựng response.

### 18.2. Thêm dòng vào O101 và kiểm tra thay đổi cohort

**Câu 4:** trước lệnh, O101 có version=1 và total:

~~~text
Gross=120000, Discount=0, Payable=120000, Status=DRAFT.

Thêm B: q=1, price=90000, discountPerUnit=5000.
DeltaGross=90000, DeltaDiscount=5000, DeltaPayable=85000.

Sau addLine:
Gross=210000, Discount=5000, Payable=205000,
Status=DRAFT, Version=2.

Sau confirm (theo quy tắc mỗi lệnh tăng version một lần):
Gross=210000, Discount=5000, Payable=205000,
Status=CONFIRMED, Version=3.
~~~

Sau confirm, cohort CONFIRMED có ba Order:

| Chỉ tiêu | Kết quả |
| --- | ---: |
| Số Order CONFIRMED | 3 |
| Tổng gross | 810.000 VND |
| Tổng discount | 40.000 VND |
| Tổng payable | **770.000 VND** |
| SKU A | 3 đơn vị, gross 360.000, discount 20.000, net **340.000 VND** |
| SKU B | 5 đơn vị, gross 450.000, discount 20.000, net **430.000 VND** |

Điều này cho thấy phép đếm theo Order và theo OrderLine phải được **tách đúng grain**. Nếu chạy lệnh updateOne trong mục 7.2 trước khi chạy truy vấn baseline, kết quả đã thay đổi: hãy dùng môi trường sạch hoặc ghi rõ mốc trạng thái khi so sánh.

**Câu 5:** PostgreSQL CHECK ngăn discountPerUnitVnd lớn hơn unitPriceVnd trong một line. MongoDB validator **minh họa** mới chặn discount không âm và unitPrice không âm; chưa so sánh hai field cùng line. Do đó MongoDB cần thêm kiểm tra ở command/domain và có thể bổ sung validator phù hợp. Cả hai vẫn cần kiểm tra **tổng header bằng tổng lines**, trạng thái CONFIRMED và quyền ghi; CHECK trên một row/JSON Schema đơn giản chưa đủ.

### 18.3. Concurrency và ranh giới nghiệp vụ

**Câu 6:** PostgreSQL: cả hai command đều phải khóa root theo thứ tự thống nhất, kiểm tra DRAFT và expectedVersion khi lock được giữ; lệnh thắng ghi line + header/version trong transaction, lệnh còn lại thấy version mới và conflict. Không cho SQL batch bỏ qua root. MongoDB: updateOne có filter DRAFT, expectedVersion=1 và tăng version trong cùng atomic update; sau commit của lệnh đầu, filter lệnh hai không còn khớp. Cả hai cần idempotency riêng cho retry cùng command.

**Câu 7:** không. OrderConfirmed là quyết định của Sales. Inventory tự quyết định StockReserved/Rejected bằng nguồn tồn có thẩm quyền; nếu Payment từ chối, quy trình phải có trạng thái chờ/thất bại, giải phóng reservation hoặc bù theo nghiệp vụ. Không coi việc đổi Order thành CONFIRMED là đã thực hiện transaction ACID cùng Inventory và Payment.

**Câu 8:** quan hệ ghi header + outbox trong cùng transaction PostgreSQL. Document cần transaction cho Order + outbox collection hoặc một thiết kế bền vững khác có bảo đảm tương ứng; một updateOne Order không tự insert outbox. Relay sau commit có thể publish lặp cùng eventId, consumer phải dedup.

**Câu 9:** dù ID toàn cục duy nhất, ứng dụng vẫn phải xác thực actor, kiểm tra caller thuộc T1 hoặc có quyền được cấp và lọc tenant ở mọi đường đọc/ghi. Một _id duy nhất không phải token ủy quyền. SQL PK toàn cục cũng không tự ngăn query đoán ID truy cập dữ liệu tenant khác. Nếu lộ dữ liệu PII, cần thêm quyền theo field/use case.

### 18.4. Scale, analytics, migration và chọn giải pháp

**Câu 10:** với 20.000 dòng và nhiều worker cập nhật độc lập, nên **đánh giá mô hình tham chiếu/tách line**, có thể là row quan hệ hoặc collection line theo identity riêng, vì document có giới hạn kích thước và điểm nóng cập nhật. Nhưng không tự cấp mỗi line quyền cập nhật trạng thái Order: cần root/version/lock hoặc thiết kế aggregate boundary lại theo bất biến thật. Nếu chuyển từ một document sang nhiều document, thao tác trước kia atomic trên một document có thể đòi transaction nhiều document hoặc giao thức phối hợp.

**Câu 11:** OrderConfirmed chưa chứng minh PaymentCaptured; cần Payment facts với captureId/amount/occurredAt và chính sách đối soát order–capture. Để báo cáo doanh số theo SKU, dùng fact theo OrderLine đã đủ điều kiện hoặc capture allocation theo SKU khi thanh toán từng phần. Cần tránh JOIN PaymentAttempt đa hàng làm nhân giá trị và tránh cộng các loại tiền khác nhau khi chưa quy đổi.

**Câu 12:** giữ PostgreSQL làm nguồn ghi, tạo document **read projection** từ snapshot/backfill và CDC/outbox, dedup/version, đối soát theo tenant/order/line/tổng và thử shadow read, sau đó chuyển traffic đọc dần. Nếu cần rollback, có thể trả về reader PostgreSQL trong khi vẫn giữ nguồn ghi duy nhất. **Domain Java, API response và integration event có thể không đổi** nếu hợp đồng/ngữ nghĩa vẫn giữ. Nếu muốn chuyển cả quyền ghi sang MongoDB, phải có một kế hoạch cutover transaction và rollback/roll-forward phức tạp hơn.

**Câu 13:** default discount=0 cho lịch sử chỉ đúng nếu hợp đồng cũ **thực sự chưa có giảm giá** và không có chương trình voucher/giảm giá ngoài hệ thống bị bỏ sót. Nếu giá trị lịch sử không đủ, đánh dấu unknown/quarantine hoặc lấy nguồn khác; đừng bịa số 0. Old writer đọc document v2 có discount rồi replace bằng v1 có thể làm mất field discount và cập nhật total theo logic cũ, gây sai tiền. Cần schema version, conditional update và chặn old writer nguy hiểm trước khi bật tính năng mới.

**Câu 14:** 

- **Workload A:** document nhúng lines là một ứng viên đáng thử vì phần lớn query đọc một Order nhỏ, một root được cập nhật nguyên tử. Quan hệ vẫn có thể phù hợp nếu ứng dụng đã có DB và query/index tốt.
- **Workload B:** bảng line riêng hoặc mô hình reference là ứng viên đáng thử vì xử lý dòng độc lập/báo cáo nhiều; phải bảo vệ bất biến Order và không tự chia transaction tùy tiện. Document vẫn có thể dùng aggregation/read projection nếu benchmark cho thấy phù hợp.
- **Ba số đo tối thiểu cho mỗi hồ sơ:** p95 latency của use case chủ đạo, throughput/lock-or-conflict rate khi ghi đồng thời, và tổng bytes/index/storage hoặc thời gian/chí phí của truy vấn báo cáo quan trọng. Cần thêm p99 khi có Order lớn và chi phí backup/restore để đánh giá vận hành.

**Không có câu trả lời "MongoDB luôn nhanh hơn cho Order" hoặc "PostgreSQL luôn đúng hơn".** Cả hai có thể bảo vệ cùng bất biến nếu ứng dụng chọn đúng giao thức và hiểu giới hạn transaction. Quyết định phải bám **workload, tính đúng, vận hành và khả năng tiến hóa**.

## 19. Kịch bản phòng lab, báo cáo kết quả và thang đánh giá

### 19.1. Các bước thực hành có thể lặp lại

1. Chuẩn bị **môi trường thử tách biệt** cho PostgreSQL và MongoDB. Không nạp dữ liệu mẫu vào production.
2. Chạy DDL PostgreSQL trong phần 5, rồi nhập ba Order và bốn OrderLine. Xác nhận số bản ghi và các tổng đã tính bằng tay.
3. Tạo collection, validator và index MongoDB trong phần 6, rồi nhập **cùng dữ liệu** bằng mongosh. Không chạy insertMany hai lần nếu chưa xóa dataset thử.
4. Chạy hai nhóm truy vấn: chi tiết O100 và danh sách C1; báo cáo confirmed theo SKU. Ghi output **dưới dạng canonical value** và so với bảng chuẩn, không so text representation thuần túy.
5. Chạy câu đối soát tổng tiền ở mỗi engine; mong đợi **không có hàng/document sai**.
6. Trên bản sao dataset hoặc sau khi đã chụp kết quả baseline, thực hiện thao tác thêm dòng B cho O101; kiểm tra version=2 và payable=205.000.
7. Thực hiện confirm qua **đường command có kiểm tra trạng thái/version** trong ứng dụng thử, không tự set status rồi gọi đó là test miền. Kiểm tra version=3, cohort confirmed và số liệu SKU.
8. Thử request sai, request trùng và request đồng thời. Ghi rõ lỗi nào bị chặn ở **validator/schema**, lỗi nào do **domain/transaction** và lỗi nào chỉ được phát hiện nhờ reconciliation.
9. Dùng execution plan và bộ dữ liệu đại diện lớn hơn để đo p95/p99, conflict, index size và latency báo cáo; nêu cấu hình và giả định.
10. Viết **báo cáo quyết định**: workload, ràng buộc, ứng viên, phép đo, lựa chọn, rủi ro còn mở và điều kiện cần thử trước production.

Các thao tác trên được mô tả để người học thực hành, **không có nghĩa đã được chạy hoặc benchmark trong bài viết**. Các đoạn dùng tham số như :tenant_id là SQL minh họa cho prepared statements của ứng dụng; cần bind giá trị đúng, không dán nguyên dấu hai chấm vào psql mà kỳ vọng hoạt động nếu chưa cấu hình biến/binding.

### 19.2. Mẫu báo cáo so sánh

| Nội dung cần ghi | Kết quả của người học |
| --- | --- |
| Workload (số Order, lines/order, tỷ lệ đọc/ghi) | ... |
| Business invariants và bounded context | ... |
| Relational PK/FK/CHECK, index, transaction | ... |
| Document shape, _id, validator, index, atomic update | ... |
| SQL và mongosh query cùng đáp án | ... |
| p95 chi tiết Order và danh sách theo khách | ... |
| p95, số documents/rows quét khi nhóm theo SKU | ... |
| Version conflict/idempotency test | ... |
| Outbox và transaction boundary | ... |
| Backup/restore, retention, PII và tenant | ... |
| Rủi ro khi data growth/migration | ... |
| Quyết định và điều kiện xem lại | ... |

Không cần điền số benchmark nếu chưa có môi trường đo; **ghi "chưa đo" và chỉ ra phép thử cần làm**, thay vì dựng ra latency hay tỷ lệ nén không có bằng chứng.

### 19.3. Rubric tham khảo — 100 điểm

| Tiêu chí | Điểm tối đa | Dấu hiệu đạt |
| --- | ---: | --- |
| Phát biểu grain, ID, bất biến và owner | 15 | Order/Line rõ, tenant scope đúng, total/transition có nghĩa |
| Mô hình quan hệ | 20 | DDL/key/FK/CHECK/index, transaction và truy vấn đúng |
| Mô hình document | 20 | Embed có lý do, BSON/validator/index, atomic update/version |
| Đối chiếu số liệu | 15 | O100/O101/O102, SKU A/B và tình huống O101 cập nhật khớp |
| An toàn đồng thời và tích hợp | 15 | Idempotency, version, outbox, không nhầm Inventory/Payment |
| Đánh đổi, benchmark và migration | 10 | Workload-based decision, không tự khẳng định hiệu năng |
| Trình bày và truy vết | 5 | Giải thích rành mạch, có giả định, test và kết luận |
| **Tổng** | **100** | |

Điểm cao không dựa trên việc chọn PostgreSQL hay MongoDB. Một bài chọn document và giải thích rõ hạn chế dữ liệu lớn, transaction ngoài document, kiểm thử và monitoring có thể tốt hơn bài chọn quan hệ chỉ vì "có FK".

## 20. Checklist thiết kế và kết luận

Trước khi chốt biểu diễn Order, hãy kiểm tra:

- **Grain:** Order là một aggregate; OrderLine có định danh trong phạm vi Order; fact theo dòng là mô hình khác.
- **ID và tenant:** khóa, join/reference, index, API và event dùng cùng namespace, không lộ dữ liệu chéo tenant.
- **Giá snapshot:** unitPrice và discount được chốt, không đọc lại giá hiện tại để tính đơn quá khứ.
- **Tiền:** gross, discount, payable được tính chính xác; không dùng float và không nhận total tùy ý từ client.
- **Trạng thái:** DRAFT cho phép thay đổi; CONFIRMED không bị sửa dòng qua đường thường; có command và test trạng thái rỗng/cancel.
- **Quan hệ:** header/line có PK/FK/CHECK, transaction bảo vệ nhiều row, writer trực tiếp không được vượt root.
- **Document:** mảng lines có giới hạn; schema validation, version và atomic update đủ cho root; không giả định validator bảo vệ mọi bất biến.
- **Outbox:** sự thật được công bố sau commit; eventId và command idempotency không bị đánh tráo.
- **Cross-context:** Sales không tự chuyển tồn kho hay thanh toán; có trạng thái trung gian/đối soát khi hệ thống khác chậm hoặc thất bại.
- **Truy vấn:** chi tiết và list Order, phân tích theo SKU đều có query và index được kiểm tra.
- **Analytics:** không COUNT dòng thành Order; không SUM header total sau unwind; không xem OrderConfirmed là PaymentCaptured.
- **Hiệu năng:** dữ liệu và yêu cầu đo công bằng, có p95/p99, bytes quét, contention, index/storage và nhu cầu phục hồi.
- **Tiến hóa:** thêm field, document version, mixed-version writers và backfill có kế hoạch; không dual write tự do.
- **Bảo mật:** DTO không công bố PII/field nội bộ theo cấu trúc storage; quyền tenant không phụ thuộc ID đoán được.
- **Kiểm chứng:** cả hai biểu diễn phải cho ra **565.000 VND** ở baseline CONFIRMED và **770.000 VND** khi O101 thêm dòng rồi được confirm, theo đúng mốc so sánh.

**Kết luận:** Cùng một nghiệp vụ **Order–OrderLine** có thể biểu diễn thành **hai bảng quan hệ có khóa ngoại** hoặc **một document chứa mảng lines**. Quan hệ đem lại cách thể hiện khóa/ràng buộc liên bảng và cập nhật qua transaction nhiều row; document phù hợp khi một aggregate có kích thước giới hạn và thường được đọc/ghi cùng nhau, với cập nhật nguyên tử ở cấp document. Không có cách nào tự giải quyết hết **bất biến tổng tiền, đổi trạng thái, quyền tenant, idempotency, event hay báo cáo đúng grain**. Cần bắt đầu từ **yêu cầu và mô hình miền**, chọn vật lý theo workload, viết truy vấn trên cùng dữ liệu, kiểm thử tình huống sai và đo hiệu năng thực, rồi mới quyết định. Đó là cách biến so sánh quan hệ–document từ tranh luận công nghệ thành **một quyết định mô hình hóa dữ liệu có thể giải thích, kiểm chứng và tiến hóa**.
