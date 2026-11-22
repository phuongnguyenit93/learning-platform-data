# Từ điển dữ liệu cho bảng, trường, kiểu, đơn vị và miền giá trị

## 1. Từ điển dữ liệu giải quyết vấn đề gì?

Khi nhìn vào một bảng `orders`, người phát triển có thể đoán `total_amount` là tổng tiền, `status` là trạng thái và `created_at` là thời điểm tạo. Nhưng chỉ nhìn tên cột không thể xác định:

- `total_amount` là giá trị đơn trước hay sau giảm giá, đã gồm thuế/vận chuyển chưa, tính theo đơn vị tiền nào?
- `status = 'PAID'` nghĩa là đã gửi yêu cầu thanh toán hay nhà cung cấp đã xác nhận thu tiền?
- `created_at` là giờ khách đặt đơn, giờ server nhận yêu cầu hay giờ hàng được ghi vào database?
- `customer_id` là khóa khách trong một tenant, trong một hệ nguồn hay toàn hệ thống?
- `NULL` ở `delivered_at` nghĩa là chưa giao, không áp dụng, chưa nhận dữ liệu hay đã xóa?
- Một đơn có nhiều dòng hàng; JOIN thêm thanh toán có làm nhân doanh thu không?

**Từ điển dữ liệu (data dictionary)** là tài liệu có cấu trúc định nghĩa **đối tượng dữ liệu và từng thuộc tính**: tên, ý nghĩa nghiệp vụ, vị trí lưu trữ, kiểu, đơn vị, miền giá trị, khóa, quan hệ, quy tắc thiếu dữ liệu, nguồn có thẩm quyền, thời gian và các kiểm tra cần thiết.

Mục tiêu không phải chỉ liệt kê kiểu `VARCHAR` hay `BIGINT`. Mục tiêu là giúp một người **chưa viết lược đồ** hiểu dữ liệu đủ chính xác để:

1. Thiết kế bảng, khóa, ràng buộc và chỉ mục mà không tự đoán yêu cầu.
2. Viết API, query, báo cáo và pipeline tích hợp có cùng ngữ nghĩa.
3. Kiểm tra một giá trị hợp lệ về **cả kỹ thuật lẫn nghiệp vụ**.
4. Biết điều gì phải giữ nguyên khi đổi schema hoặc nguồn dữ liệu.
5. Phân biệt giá trị hiện hành, giá trị lịch sử, dữ liệu dẫn xuất và sự kiện đã xác nhận.
6. Truy nguyên dữ liệu sai đến người sở hữu, nguồn và quy tắc biến đổi.

Ví dụ xuyên suốt là nền tảng bán hàng nhiều tenant. Chúng ta sẽ lập từ điển cho `sales_order`, `sales_order_line` và `payment_movement`, từ yêu cầu nghiệp vụ đến mô hình logic, PostgreSQL và quy tắc kiểm chứng.

## 2. Phân biệt từ điển dữ liệu với ERD, business glossary, catalog và DDL

Các tài liệu bổ sung cho nhau, nhưng không thay thế hoàn toàn nhau.

| Công cụ/tài liệu | Câu hỏi nó trả lời tốt | Điều nó thường không tự trả lời |
| --- | --- | --- |
| **Business glossary** | “Đơn đã đặt”, “doanh thu”, “khách đang hoạt động” nghĩa là gì? | Cột vật lý nào chứa dữ liệu, kiểu DB và FK cụ thể. |
| **ERD / mô hình quan hệ** | Thực thể nào có quan hệ 1:N, N:N? Khóa chính và khóa ngoại nằm ở đâu? | Đơn vị tiền, điều kiện chốt sự việc, nghĩa NULL và nguồn có thẩm quyền. |
| **Data dictionary** | Mỗi bảng/trường có grain, kiểu, nghĩa, miền giá trị, đơn vị, quy tắc gì? | Không nhất thiết tự kiểm tra được mọi quy tắc nếu chưa nối với code/DB. |
| **DDL/schema** | Database đang khai báo cột, kiểu, PK/FK/CHECK/INDEX thế nào? | Vì sao có cột đó, giá trị nào là bằng chứng nghiệp vụ và quy tắc đổi lịch sử. |
| **Metadata catalog** | Dataset nằm ở đâu, ai dùng, được cập nhật khi nào, có lineage và phân quyền gì? | Không bảo đảm mọi trường có định nghĩa nghiệp vụ đúng nếu metadata thiếu quản trị. |
| **Data contract** | Producer cam kết gì với consumer về schema, nghĩa, chất lượng và thay đổi? | Có thể chỉ mô tả một giao diện công bố, không bao phủ toàn bộ mô hình nội bộ. |

**Mối quan hệ đúng:** glossary định nghĩa thuật ngữ; ERD thể hiện quan hệ; từ điển gắn nghĩa với thực thể/trường; DDL thực thi một phần ràng buộc; catalog giúp tìm và quản trị; contract xác định cam kết giữa bên cung cấp và bên dùng.

Một từ điển được xuất tự động từ `information_schema.columns` mới chỉ biết tên, kiểu, `nullable` và một vài thuộc tính vật lý. Nó **chưa biết** `total_minor` là “giá trị đã đặt” chứ không phải “tiền thực thu”. Cần bổ sung metadata có người chịu trách nhiệm xác nhận.

## 3. Bắt đầu từ grain và nguồn sự thật, không bắt đầu từ danh sách cột

**Grain** là phát biểu chính xác “một hàng đại diện cho cái gì”. Nếu không có grain, từ điển dễ thành danh sách cột rời rạc.

Với hệ thống ví dụ:

| Dataset | Grain: một hàng đại diện cho… | Nguồn có thẩm quyền |
| --- | --- | --- |
| `sales_order` | Một đơn hàng đã được tiếp nhận theo `(tenant_id, order_id)`. | Ordering. |
| `sales_order_line` | Một dòng hàng thứ `line_no` của một đơn cụ thể. | Ordering. |
| `payment_movement` | Một giao dịch capture hoặc refund được Payment ghi nhận **đã có xác nhận** từ nguồn thanh toán. | Payment. |
| `catalog_product` | Một sản phẩm đang được Catalog công bố trong một tenant. | Catalog. |
| `daily_sales_mart` | Một ngày, một tenant, một tiền tệ, một kênh theo định nghĩa chỉ số được duyệt. | Analytics; dữ liệu dẫn xuất từ các owner. |

Từ grain, mới xác định:

- **Business key:** định danh nghiệp vụ như `order_id` trong phạm vi tenant.
- **Primary key:** khóa DB thực thi uniqueness của một hàng.
- **Foreign key / external reference:** cách liên kết đến hàng hoặc thực thể khác.
- **Các thuộc tính mô tả** và **các số đo** của đúng grain.
- **Miền giá trị, đơn vị và thời gian** liên quan đến mỗi thuộc tính.
- **Các trường hợp phải có hoặc được phép thiếu**.

Ví dụ, `payment_movement` có thể có **nhiều hàng cho một order** vì đơn được thu nhiều lần hoặc hoàn một phần. Nếu từ điển chỉ viết “thông tin thanh toán đơn” mà không chỉ rõ một hàng là *một chuyển động tiền*, người làm báo cáo dễ JOIN hai bảng `order_line` và `payment_movement` theo order rồi nhân tổng tiền.

### Chủ sở hữu không đồng nghĩa nơi lưu dữ liệu

`customer_id` có thể xuất hiện trong Ordering để biết ai đặt đơn, nhưng Customer Identity có thể là owner của hồ sơ khách. Ordering được phép giữ **external reference** và dữ liệu đã chốt của đơn; không vì có cột `customer_id` mà được phép tự sửa email của khách.

Từ điển nên ghi rõ mỗi dữ kiện là **authoritative**, **snapshot đã chốt** hay **projection dẫn xuất**.

## 4. Cấu trúc từ điển dữ liệu: cấp hệ, bảng và cột

Một bộ từ điển dùng được cần ít nhất ba cấp.

### Cấp mô hình/dataset

| Metadata | Cách điền |
| --- | --- |
| Mã mô hình/dataset | `SALES_ORDER_V1`; mã bền vững, khác tên hiển thị. |
| Mục đích | Phục vụ ghi nhận đơn đã đặt và phân tích giá trị đơn. |
| Bounded context/owner | Ordering, người phê duyệt định nghĩa. |
| Hệ lưu và môi trường | PostgreSQL, schema `ordering`; tránh ghi secrets. |
| Phạm vi tenant/khu vực | Khóa tenant, chính sách truy cập và lưu trú dữ liệu. |
| Nguồn dữ liệu | Command đặt hàng được chấp nhận, không phải status ở cache. |
| Refresh/latency | Trực tiếp trong OLTP hoặc độ trễ ETL có SLO. |
| Phiên bản hợp đồng | `v1`, thời điểm có hiệu lực và liên kết ADR/migration. |
| Chính sách dữ liệu | Phân loại, quyền, retention, xóa/ẩn danh, backup. |

### Cấp bảng/collection

Một entry cho mỗi bảng nên ghi:

- Tên logic và tên vật lý, mô tả nghiệp vụ.
- **Grain** và tập thực thể nằm trong phạm vi.
- PK, các candidate/business keys, unique constraints.
- Quan hệ, cardinality và quy tắc orphan/cascade.
- Chủ sở hữu ghi, nguồn có thẩm quyền, kiểu nguồn/dẫn xuất.
- Quy tắc INSERT/UPDATE/DELETE, trạng thái bất biến hay mutable.
- Khóa phân vùng, pattern đọc/ghi, chỉ mục phục vụ workload.
- Phân loại nhạy cảm, thời hạn lưu và đường đồng bộ downstream.

### Cấp cột/trường

Một entry cần có những thông tin tối thiểu:

| Thuộc tính metadata | Diễn giải và ví dụ |
| --- | --- |
| `column_name` | `order_total_minor`, tên vật lý ổn định trong phiên bản schema. |
| `business_term` | “Giá trị đơn đã chấp nhận”; có liên kết đến glossary. |
| `definition` | Sau giảm giá trên dòng hàng; chưa trừ hoàn tiền thực tế. |
| `data_type` | PostgreSQL `BIGINT`. |
| `nullable` và `null_meaning` | `NOT NULL` hoặc phân loại vì sao được phép NULL. |
| `unit` và `scale` | Đơn vị nhỏ nhất của `currency_code` tương ứng. |
| `domain` | Số nguyên từ 0 trở lên; miền có version khi thay đổi. |
| `default` | Có hay không, chỉ dùng khi giá trị mặc định là đúng về nghiệp vụ. |
| `key_role` | PK/FK/business key/không phải khóa. |
| `source_authority` | Ordering tại thời điểm chấp nhận đơn. |
| `derivation` | Nếu tính từ nguồn khác, công thức, làm tròn và phiên bản quy tắc. |
| `temporal_meaning` | Giá trị có hiệu lực/chốt lúc nào, có được correction không. |
| `classification` | Public/internal/PII/financial và quyền cần thiết. |
| `quality_rules` | CHECK, test SQL, kiểm tra đối soát và SLO. |
| `change_policy` | Rename, deprecation, khả năng tương thích, người phê duyệt. |

Không phải mỗi ô đều cần một đoạn văn dài, nhưng **những ô quyết định tính đúng** như grain, unit, domain, NULL và source authority phải có nghĩa rõ. Đánh dấu “chưa xác định” và người chịu trách nhiệm giải quyết còn tốt hơn tự bịa thông tin.

## 5. Ví dụ mô hình nghiệp vụ: đơn hàng và giao dịch thu/hoàn

Yêu cầu nghiệp vụ:

1. Một tenant có nhiều đơn; một đơn có ít nhất một dòng hàng khi được chấp nhận.
2. Mỗi dòng hàng lưu số lượng và giá **đã chốt** tại lúc đặt.
3. Giá trị đơn tính theo định nghĩa đặt hàng; nó **khác** số tiền provider đã thu.
4. Một đơn có thể có nhiều lần capture/refund, chỉ tính giao dịch được xác nhận.
5. Không cộng tiền khác loại tiền tệ, không gộp nhiều chuyển động tiền thành một dòng order.
6. Báo cáo cần cả trạng thái đơn hiện tại và lịch sử payment movements.

~~~mermaid
erDiagram
    SALES_ORDER ||--|{ SALES_ORDER_LINE : contains
    SALES_ORDER ||--o{ PAYMENT_MOVEMENT : related_to
    SALES_ORDER {
        uuid tenant_id PK
        uuid order_id PK
        uuid customer_id
        timestamptz placed_at
        varchar order_status
        bigint booked_total_minor
        char currency_code
    }
    SALES_ORDER_LINE {
        uuid tenant_id PK
        uuid order_id PK
        integer line_no PK
        uuid product_id
        numeric quantity
        bigint agreed_unit_price_minor
        bigint line_net_minor
    }
    PAYMENT_MOVEMENT {
        uuid tenant_id PK
        uuid movement_id PK
        uuid order_id FK
        varchar movement_type
        bigint amount_minor
        char currency_code
        timestamptz confirmed_at
    }
~~~

Sơ đồ thể hiện **quan hệ logic**; `customer_id` và `product_id` có thể là tham chiếu đến owner khác, không nhất thiết có FK xuyên database. Một dòng order có thể xuất hiện trong các điều chỉnh hoặc hủy sau khi đặt; nếu nghiệp vụ yêu cầu lịch sử thay đổi dòng, phải có event/audit/history bổ sung.

### Quy tắc thời gian

- `placed_at`: mốc Ordering chấp nhận đơn theo định nghĩa chốt, không phải mốc ghi vào warehouse.
- `confirmed_at` trên movement: mốc Payment công nhận capture/refund được nhà cung cấp xác nhận.
- `recorded_at`: khi Payment ghi bản movement; có thể muộn hơn `confirmed_at`.
- `created_at` trong OLTP: mốc hệ quản trị tạo hàng; không mặc nhiên dùng thay `placed_at`.

Bản tin callback có thể đến muộn hoặc lặp; từ điển phải quy định cách giữ một giao dịch duy nhất, chứ không lấy “số lần callback” làm số lần thu.

## 6. Ví dụ lược đồ PostgreSQL để đối chiếu từ điển

Đây là **lược đồ minh họa**, không phải mô hình kế toán đầy đủ. Nó tập trung vào các cột mà từ điển phải giải thích.

~~~sql
CREATE SCHEMA IF NOT EXISTS ordering;

CREATE TABLE ordering.sales_order (
    tenant_id           UUID NOT NULL,
    order_id            UUID NOT NULL,
    customer_id         UUID NOT NULL,
    placed_at           TIMESTAMPTZ NOT NULL,
    order_status        VARCHAR(20) NOT NULL
                        CHECK (order_status IN
                          ('PLACED', 'CANCELLED', 'FULFILLED')),
    booked_total_minor  BIGINT NOT NULL
                        CHECK (booked_total_minor >= 0),
    currency_code       CHAR(3) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE INDEX ix_order_tenant_placed
    ON ordering.sales_order (tenant_id, placed_at DESC);

CREATE TABLE ordering.sales_order_line (
    tenant_id              UUID NOT NULL,
    order_id               UUID NOT NULL,
    line_no                INTEGER NOT NULL CHECK (line_no > 0),
    product_id             UUID NOT NULL,
    quantity               NUMERIC(18, 3) NOT NULL
                           CHECK (quantity > 0),
    agreed_unit_price_minor BIGINT NOT NULL
                           CHECK (agreed_unit_price_minor >= 0),
    line_net_minor         BIGINT NOT NULL
                           CHECK (line_net_minor >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.sales_order (tenant_id, order_id)
);

CREATE TABLE ordering.payment_movement (
    tenant_id           UUID NOT NULL,
    movement_id         UUID NOT NULL,
    order_id            UUID NOT NULL,
    provider_name       VARCHAR(50) NOT NULL,
    provider_reference  VARCHAR(120) NOT NULL,
    movement_type       VARCHAR(10) NOT NULL
                        CHECK (movement_type IN ('CAPTURE', 'REFUND')),
    amount_minor        BIGINT NOT NULL CHECK (amount_minor > 0),
    currency_code       CHAR(3) NOT NULL,
    confirmed_at        TIMESTAMPTZ NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, movement_id),
    UNIQUE (tenant_id, provider_name, provider_reference),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.sales_order (tenant_id, order_id)
);

CREATE INDEX ix_payment_order_confirmed
    ON ordering.payment_movement
       (tenant_id, order_id, confirmed_at DESC);
~~~

**Điều kiện để đọc DDL đúng:**

- `order_status` mô tả vòng đời **đơn**, không thay thế `payment_movement`. Danh sách CHECK không tự chặn chuyển tiếp `FULFILLED -> PLACED`; transaction/domain state machine phải bảo vệ.
- `booked_total_minor` là giá trị đơn đã chốt theo quy tắc của Ordering; giả sử **đã trừ giảm giá trên đơn**, **chưa trừ refund**, xử lý thuế/vận chuyển phải có chính sách riêng. Trong ví dụ, công thức tổng chưa được thể hiện thành CHECK vì có thể gồm nhiều khoản độc lập.
- `agreed_unit_price_minor` là giá **trên một đơn vị số lượng chuẩn**; `quantity` cho phép phần thập phân, nên cần quy tắc làm tròn trước khi ra `line_net_minor` nguyên. Không dùng phép nhân rồi ép kiểu tùy tiện.
- `currency_code` là mã tiền tệ của giá trị tương ứng, nhưng `CHAR(3)` **không tự chứng minh** mã hợp lệ hoặc hai bảng đang dùng cùng loại tiền. Cần kiểm tra danh mục tiền tệ/chính sách chuyển đổi.
- `UNIQUE (tenant_id, provider_name, provider_reference)` chỉ đúng nếu provider cam kết tham chiếu duy nhất theo phạm vi đó cho từng movement. Nếu reference chỉ duy nhất trong merchant account hoặc theo operation type, phải đưa đúng namespace vào key.
- `customer_id` và `product_id` là external references nếu Customer/Catalog do database khác sở hữu; không tạo FK giả xuyên dịch vụ.
- Foreign key giữa ba bảng cùng owner được DBMS bảo vệ theo tenant; không tự áp `ON DELETE CASCADE` vì chứng từ giao dịch có retention độc lập.

Từ điển là nơi giải thích **vì sao** mỗi quyết định đó tồn tại và cách kiểm chứng nó, trong khi DDL chỉ bảo vệ một phần.

## 7. Mẫu từ điển cấp bảng có thể đưa vào dự án

Ví dụ một entry bảng cho `ordering.sales_order`:

| Mục | Nội dung từ điển |
| --- | --- |
| **Dataset ID** | `ordering.sales_order.v1`. |
| **Tên nghiệp vụ** | Đơn hàng đã được chấp nhận. |
| **Mô tả** | Thực thể đơn đã chốt; giữ trạng thái đơn và giá trị đặt, không phải dòng tiền provider. |
| **Grain** | Một hàng/`(tenant_id, order_id)`. |
| **Owner và writer** | Ordering; chỉ workflow Order được phép cập nhật trạng thái đơn. |
| **PK / business key** | PK `(tenant_id, order_id)`; `order_id` ổn định trong tenant. |
| **Quan hệ** | 1:N với `sales_order_line`; 1:N với `payment_movement`. |
| **Temporal contract** | `placed_at` là thời điểm chấp nhận đơn; `created_at` là lúc ghi hàng. |
| **Trạng thái** | `PLACED`, `CANCELLED`, `FULFILLED`; chuyển tiếp theo state machine riêng. |
| **Update policy** | Trạng thái có thể thay; ID và thời điểm chấp nhận không đổi tùy tiện. |
| **Delete policy** | Không xóa vật lý chỉ vì đơn bị hủy; retention theo chính sách chứng từ. |
| **Phân loại** | Internal/financial; `customer_id` là định danh có thể liên kết tới chủ thể. |
| **Truy vấn điển hình** | Tra đơn bằng PK; danh sách theo tenant và `placed_at`. |
| **Quality checks** | PK không trùng; không thiếu currency; tổng không âm; đối soát dòng hàng theo cùng mốc. |

Một từ điển bảng nên có **một grain duy nhất**. Nếu đội ngũ không thống nhất một hàng ở đây đại diện cho gì, chưa nên bắt đầu thiết kế các cột số tiền dẫn xuất.

### Từ điển cấp quan hệ

Nên bổ sung bảng quan hệ thay vì chỉ nêu tên FK:

| Quan hệ | Cardinality | Tính bắt buộc | Quy tắc vòng đời |
| --- | --- | --- | --- |
| Order → OrderLine | Một Order có 1..N dòng khi đã chốt. | Ít nhất một dòng là **invariant nghiệp vụ**, không tự được FK một chiều đảm bảo. | Không xóa dòng cũ khi Catalog xóa sản phẩm. |
| Order → PaymentMovement | Một Order có 0..N movement. | Có thể không có payment đã xác nhận. | Movement có retention và audit riêng. |
| Order → CustomerIdentity | Order tham chiếu một customer theo contract. | Khóa không rỗng tại lúc chốt. | Khách ngừng hoạt động không làm đơn lịch sử biến mất. |
| OrderLine → CatalogProduct | Dòng chứa product ID và giá đã chốt. | ID phải được xác minh theo contract tại thời điểm đặt. | Giá hiện hành của Catalog không được ghi đè giá đã chốt. |

## 8. Mẫu từ điển cấp cột: một ví dụ hoàn chỉnh

Bảng sau dùng cho `ordering.sales_order`. Các hàng chỉ là **bản tóm tắt**; hệ thống thực tế nên lưu thêm owner, source và quality rule có thể liên kết.

| Cột | Kiểu vật lý | NULL | Đơn vị/miền | Định nghĩa và ràng buộc |
| --- | --- | --- | --- | --- |
| `tenant_id` | `UUID` | Không | ID tenant có namespace. | Thành phần PK; mọi truy vấn/đối soát phải trong đúng tenant. |
| `order_id` | `UUID` | Không | ID đơn ổn định trong tenant. | Thành phần PK; không tái sử dụng cho đơn khác. |
| `customer_id` | `UUID` | Không | External customer reference. | ID CustomerIdentity tại lúc đặt; không phải email hoặc tên khách. |
| `placed_at` | `TIMESTAMPTZ` | Không | Thời điểm tuyệt đối. | Mốc Ordering chấp nhận đặt; dùng nhóm đơn theo event-time khi phù hợp. |
| `order_status` | `VARCHAR(20)` | Không | `PLACED/CANCELLED/FULFILLED`. | Vòng đời đơn; không đồng nghĩa đã capture hoặc đã hoàn tiền. |
| `booked_total_minor` | `BIGINT` | Không | Đơn vị nhỏ nhất của `currency_code`; ≥ 0. | Tổng giá trị đơn đã chốt theo quy tắc, chưa trừ refund. |
| `currency_code` | `CHAR(3)` | Không | Mã tiền tệ được phê duyệt. | Mọi phép cộng tiền phải nhóm/chuyển đổi theo tiền tệ. |
| `created_at` | `TIMESTAMPTZ` | Không | Thời điểm lưu hàng. | Metadata kỹ thuật; không mặc định là thời điểm khách đặt. |

Mỗi định nghĩa phải giải thích cả **trường hợp không được dùng cột đó**. Ví dụ `booked_total_minor` có thể được dùng cho “booked sales” theo chính sách, nhưng **không** được dùng làm “net cash received” nếu chưa đối chiếu các movements.

### Bảng dòng hàng

| Cột | Miền và đơn vị | Ý nghĩa |
| --- | --- | --- |
| `line_no` | Số nguyên dương, duy nhất trong order. | Số thứ tự dòng; ổn định sau khi đơn đã chốt. |
| `product_id` | Product reference theo tenant. | Sản phẩm được đặt tại thời điểm chốt, khác tên Catalog hiện hành. |
| `quantity` | `NUMERIC(18,3)`; đơn vị hàng hóa từ contract. | Số đơn vị đã đặt; `1.500` có thể là 1,5 kg, không phải 1,5 chiếc. |
| `agreed_unit_price_minor` | Tiền nhỏ nhất **trên một đơn vị quantity chuẩn**. | Đơn giá thỏa thuận, không tự cập nhật theo Catalog. |
| `line_net_minor` | Tiền nhỏ nhất của currency trong Order. | Số tiền dòng sau chính sách chiết khấu/làm tròn được chốt. |

Nếu mặt hàng có cả `kg` và `piece`, phải có quy tắc đơn vị theo sản phẩm hoặc lưu `unit_code` ở dòng hàng. Một cột `quantity` không có unit/scale contract sẽ làm số liệu thống kê vô nghĩa ngay cả khi kiểu DB hợp lệ.

## 9. Chọn kiểu dữ liệu: vật lý đúng chưa đủ, phải đúng miền nghiệp vụ

| Nhóm | Kiểu thường dùng | Quy tắc từ điển cần ghi |
| --- | --- | --- |
| Định danh | `UUID`, `BIGINT`, `VARCHAR` | Namespace, độ ổn định, cách phát ID, có cho phép tái sử dụng không. |
| Số nguyên đếm | `INTEGER`/`BIGINT` | Có âm không? Giới hạn trên? Counter có reset không? |
| Số thập phân | `NUMERIC(p,s)` / `DECIMAL` | Precision, scale, làm tròn, đơn vị vật lý, có thể âm không. |
| Tiền | `BIGINT` minor units hoặc `NUMERIC` | Currency, minor-unit convention, tỷ giá và rounding. |
| Văn bản | `TEXT`/`VARCHAR(n)` | Định nghĩa, chuẩn Unicode, độ dài thực tế, tính nhạy cảm. |
| Boolean | `BOOLEAN` | Hai trạng thái có đủ không? NULL có nghĩa gì nếu được cho phép? |
| Enum/code | `VARCHAR` + CHECK hoặc bảng tham chiếu | Danh sách code, nghĩa, trạng thái ngừng dùng, version. |
| Thời điểm | `TIMESTAMPTZ` | Mốc nghiệp vụ, timezone hiển thị, precision và nguồn đồng hồ. |
| Ngày địa phương | `DATE` | Timezone/lịch nghiệp vụ để xác định “ngày”. |
| JSON/document | `JSONB` hoặc document riêng | Schema version, các field cần/không cần, cách truy vấn/index và kiểm soát dữ liệu tự do. |
| Nhị phân | `BYTEA` / object reference | MIME/type, kích thước, checksum, quyền và retention. |

### Không lưu mọi thứ bằng chuỗi

Số tiền `"120000"`, timestamp `"22/11/2026"`, trạng thái `"1"` đều có thể nhét vào `VARCHAR`, nhưng mất kiểm tra hình thức và dễ sinh ngữ nghĩa khác nhau giữa consumer. Chỉ dùng chuỗi cho mã định danh hoặc dữ liệu có hình thức thực sự là văn bản; giá trị nghiệp vụ nên có kiểu đủ chặt ở lớp lưu trữ và hợp đồng.

### Precision khác độ chính xác của thực tế

`NUMERIC(18,6)` có thể lưu sáu chữ số thập phân nhưng không khiến cân đo hoặc cảm biến chính xác đến sáu chữ số. Từ điển phải phân biệt:

- **Độ phân giải lưu trữ**: số chữ số/cỡ bước có thể biểu diễn.
- **Độ chính xác phép đo**: sai số thiết bị/nguồn.
- **Quy tắc làm tròn**: cách biến giá trị tính toán thành số tiền hoặc đơn vị lưu.

Đối với FLOAT/DOUBLE, còn cần chính sách sai số khi so sánh. Không dùng phép so bằng tuyệt đối cho các phép tính thực mà nghiệp vụ yêu cầu khoảng dung sai.

## 10. Đơn vị đo: phần bắt buộc của nghĩa trường

`temperature = 30` không có nghĩa đầy đủ nếu chưa biết °C hay °F. `amount = 20000` cũng không đủ nếu chưa biết loại tiền, minor units hoặc định nghĩa số đo.

Một cột đo lường cần ít nhất:

1. **Đại lượng**: nhiệt độ, khối lượng, thời lượng, khoảng cách, số tiền, tỷ lệ…
2. **Đơn vị chuẩn**: °C, kg, millisecond, minor units, %, fraction…
3. **Hệ đo/quy đổi**: nguồn nào, chuyển đổi ra sao, có version không.
4. **Precision/scale/rounding**: giữ mấy chữ số, khi nào làm tròn.
5. **Giới hạn hợp lệ**: phạm vi vật lý và phạm vi nghiệp vụ có thể khác nhau.
6. **Tính cộng được**: có được SUM theo thời gian/khách/sản phẩm không?
7. **Thời gian tham chiếu**: đo lúc nào, theo kỳ nào, tỷ giá tại thời điểm nào.

Ví dụ:

| Trường | Định nghĩa an toàn | Không được làm |
| --- | --- | --- |
| `quantity` | Số lượng với `unit_code` hoặc đơn vị chuẩn của sản phẩm. | Cộng 3 kg với 2 chiếc như thể cùng đơn vị. |
| `amount_minor` | Số nguyên trong đơn vị nhỏ nhất của currency đi kèm. | Cộng trực tiếp VND và USD. |
| `discount_rate` | Tỷ lệ dạng số thực 0..1; `0.15` là 15%. | Nhầm `0.15` là 0,15% hoặc `15` là 15%. |
| `temperature_c` | Nhiệt độ Celsius, scale theo thiết bị. | So với ngưỡng Fahrenheit nếu chưa chuyển. |
| `latency_ms` | Khoảng thời gian millisecond không âm. | Nhầm timestamp tuyệt đối với độ dài thời gian. |
| `inventory_balance` | Số dư tại một thời điểm. | Cộng số dư từng ngày như dòng nhập/xuất. |

### Quy tắc cộng tiền phải ghi rõ

Ví dụ `amount_minor = 150000` và `currency_code = 'VND'` được hiểu theo minor unit của VND đã thống nhất trong hợp đồng; nếu một loại tiền dùng số chữ số thập phân khác thì converter phải dựa trên currency, không cố định “chia 100” cho mọi tiền tệ.

~~~sql
-- Ví dụ tổng capture và refund theo tiền tệ, không đổi currency.
SELECT tenant_id, currency_code,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE 0 END) AS captured_minor,
       SUM(CASE WHEN movement_type = 'REFUND'
                THEN amount_minor ELSE 0 END) AS refunded_minor,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE -amount_minor END) AS net_cash_minor
FROM ordering.payment_movement
WHERE tenant_id = :tenant_id
GROUP BY tenant_id, currency_code;
~~~

Kết quả là **dòng tiền ròng đã xác nhận** trong phạm vi dữ liệu nguồn; không tự đồng nghĩa doanh thu kế toán. Nếu dùng tỷ giá, từ điển/contract phải chỉ rõ tỷ giá nguồn nào, ngày hiệu lực, rounding, currency đích và cách restatement khi tỷ giá được điều chỉnh.

## 11. Miền giá trị: lớn hơn một danh sách enum

**Miền giá trị (value domain)** là tập các giá trị có thể xuất hiện **và ý nghĩa/điều kiện hợp lệ của chúng**. Miền không chỉ gồm enum; nó có thể là khoảng số, định dạng, quan hệ với cột khác, danh mục tham chiếu hoặc quy tắc phụ thuộc trạng thái.

Ví dụ:

| Trường | Miền giá trị | Quy tắc ngoài kiểu |
| --- | --- | --- |
| `line_no` | Số nguyên dương. | Unique trong từng order. |
| `quantity` | Số thập phân dương, tối đa 3 chữ số thập phân. | Đơn vị phù hợp loại sản phẩm; số lượng nguyên nếu bán theo chiếc. |
| `booked_total_minor` | Số nguyên không âm. | Công thức tổng theo pricing rule đã chốt. |
| `order_status` | `PLACED/CANCELLED/FULFILLED`. | Chuyển tiếp hợp lệ, quyền actor và điều kiện hủy. |
| `currency_code` | Mã tiền tệ được hệ thống hỗ trợ. | Danh mục mã có thời điểm hiệu lực, không chỉ độ dài = 3. |
| `confirmed_at` | Thời điểm tuyệt đối có nguồn xác nhận. | Không được tự lấy `received_at` nếu callback không xác nhận mốc. |
| `provider_reference` | Chuỗi theo namespace provider. | Unique đúng phạm vi merchant/tenant/provider theo contract. |

### Các loại domain nên nhận diện

- **Enumerated:** tập mã trạng thái, loại movement, loại hợp đồng.
- **Range:** `0 ≤ discount_rate ≤ 1`, `quantity > 0`.
- **Format:** mã quốc gia, email, số điện thoại, business ID.
- **Referential:** mã phải tồn tại trong bảng/cấu hình danh mục có owner.
- **Cross-field:** `end_at > start_at`, `net_amount = gross - discount` theo policy.
- **Conditional:** nếu `movement_type = REFUND` thì phải có tham chiếu khoản capture đủ điều kiện nếu nghiệp vụ đòi.
- **Temporal:** giá trị chỉ hợp lệ trong khoảng hiệu lực.
- **Uniqueness:** một `provider_reference` cho mỗi giao dịch theo phạm vi nguồn.

Một enum `status` có thể hợp lệ trong SQL nhưng chuyển trạng thái nghiệp vụ vẫn sai. Ví dụ `FULFILLED -> PLACED` có thể không được phép dù cả hai value nằm trong `CHECK`. Từ điển nên liên kết đến **state machine** và điều kiện chuyển tiếp.

### Miền giá trị có thể thay đổi theo thời gian

Thêm trạng thái `PARTIALLY_FULFILLED` là thay đổi contract; consumer cũ có thể không parse được enum mới. Từ điển cần lưu:

- Tên và code của trạng thái, mô tả, ngày bắt đầu áp dụng.
- Hành vi của writer/reader khi gặp mã chưa biết.
- Quy tắc ngừng dùng mã cũ và xử lý lịch sử.
- Chỗ nào dùng enum cứng; chỗ nào dùng reference table có version.

Không gán lại **ý nghĩa mới cho code cũ** rồi coi mọi bản ghi lịch sử đều được hiểu theo nghĩa mới.

## 12. Giá trị NULL, vắng mặt và giá trị mặc định

`NULL` trong database có nghĩa **không có giá trị ở cột tại trạng thái hiện tại**, nhưng **nguyên nhân nghiệp vụ** có thể khác nhau. Từ điển phải định nghĩa:

| Trường hợp | Ví dụ | Cách biểu diễn cần cân nhắc |
| --- | --- | --- |
| **Chưa xảy ra** | Đơn chưa được giao, `delivered_at` chưa có. | Nullable timestamp + state rõ. |
| **Không áp dụng** | Khoản thu không cần mã vận đơn. | Null hoặc loại nghiệp vụ riêng; định nghĩa vì sao. |
| **Chưa được cung cấp** | Khách chưa nhập số liên hệ phụ. | Null, không tự điền số giả. |
| **Đang chờ xác minh** | Kết quả hoàn tiền chưa được provider xác nhận. | Trạng thái PENDING; không coi NULL là đã hoàn. |
| **Không biết từ nguồn cũ** | Bản ghi legacy thiếu thời điểm capture. | `UNKNOWN_LEGACY`/status có căn cứ, không tự gán `now()`. |
| **Đã bị xóa/ẩn** | Thuộc tính cá nhân được xử lý theo policy. | Metadata lifecycle thích hợp, không lẫn với “chưa biết”. |

Một cột nullable không nên đồng thời mang năm nghĩa khác nhau nếu chúng dẫn đến quyết định khác nhau. Có thể cần **status hoặc reason_code** đi kèm.

### Không nhầm NULL với 0 và chuỗi rỗng

- `NULL`: chưa có hoặc không áp dụng theo contract.
- `0`: giá trị số bằng không, **đã biết**.
- `''`: chuỗi rỗng, có thể là không hợp lệ hoặc giá trị thật tùy field.
- `"UNKNOWN"`: mã phân loại rõ ràng, không phải giá trị mặc định cho mọi lỗi thiếu dữ liệu.
- Trường **vắng mặt trong JSON patch**: không đề cập thay đổi trường, khác với gửi trường `null` để xóa giá trị.

Ví dụ refund chưa xảy ra: không nên ghi `refunded_amount_minor = 0` trong bảng payment movement để tạo một “giao dịch hoàn tiền 0”; số liệu tổng hợp ròng có thể trả 0 từ việc **không có dòng refund**, còn mỗi movement phải có số tiền dương.

### Default trong DB và default nghiệp vụ

~~~sql
-- Hợp lý khi metadata thật sự do DB quyết định.
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
~~~

Điều đó không đồng nghĩa mọi `confirmed_at` có thể mặc định `now()`. `confirmed_at` phải lấy từ nguồn có thẩm quyền hoặc theo điểm chốt đã định nghĩa. Một default thuận tiện về kỹ thuật có thể **bịa dữ kiện nghiệp vụ** nếu áp sai field.

## 13. Khóa, quan hệ và tính duy nhất phải có phạm vi

Một từ điển đúng cần nói rõ “duy nhất **ở đâu**?”.

| Loại | Ví dụ | Điều cần ghi |
| --- | --- | --- |
| **PK** | `(tenant_id, order_id)`. | Danh tính hàng, không tái sử dụng. |
| **Composite FK** | `(tenant_id, order_id)` ở OrderLine. | Bảo vệ không nối nhầm hàng của tenant khác. |
| **Business key** | `provider_name + provider_reference` trong namespace đã xác minh. | Provider có bảo đảm unique ở phạm vi merchant/time không? |
| **Candidate key** | `tenant_id + external_order_no` khi nguồn cam kết. | Được phép thiếu/trùng hoặc sửa mã không? |
| **Surrogate key** | `customer_sk` ở data warehouse. | SK nội bộ, không thay thế mã nghiệp vụ khi trao đổi nguồn. |
| **External reference** | `product_id` của Catalog trong Ordering. | Owner, cách xác minh, lifecycle/tombstone, không giả định FK xuyên service. |

**Foreign key bảo vệ sự tồn tại của hàng cha trong cùng phạm vi DBMS**, nhưng không tự bảo vệ mọi bất biến miền. Ví dụ FK OrderLine → Order không tự bảo đảm Order đã chốt có ít nhất một dòng hàng trong lúc commit; ứng dụng/transaction cần kiểm tra điều kiện đó.

Tương tự, `UNIQUE (tenant_id, order_id)` ngăn hai hàng dùng cùng ID trong một bảng; nó không tự bảo vệ idempotency của **business request** nếu request có thể được phát lại với ID đơn mới. Cần một khóa yêu cầu ổn định và chính sách xử lý lặp.

### Quan hệ 1:N, N:N và optionality

Ngoài cardinality, từ điển quan hệ cần mô tả:

- Một phía có **bắt buộc** phải có hàng liên quan không?
- Quy tắc xóa: RESTRICT, SET NULL, CASCADE, soft delete hay giữ lịch sử?
- Quan hệ có **hiệu lực theo thời gian** hay không?
- Có phải tham chiếu xuyên bounded context không?
- Quan hệ nhiều-nhiều có thuộc tính riêng (vai trò, tỷ lệ phân bổ, thời gian) không?

Nếu một product có nhiều category, JOIN để tính doanh thu theo category có thể nhân số tiền. Cần quy tắc phân bổ/bridge grain thay vì coi N:N là phép nối vô hại.

## 14. Định nghĩa thời gian và vòng đời giá trị

Trong một từ điển, các trường thời gian cần **định nghĩa mốc** chứ không chỉ khai báo `TIMESTAMP`.

| Trường | Mốc có nghĩa | Thường dùng cho |
| --- | --- | --- |
| `occurred_at` | Khi sự việc được nguồn có thẩm quyền xác nhận xảy ra. | Event timeline, phân tích theo sự việc. |
| `placed_at` | Khi Ordering chấp nhận đơn. | Khoảng đặt hàng/kỳ bán. |
| `confirmed_at` | Khi Payment công nhận capture/refund được provider xác nhận. | Dòng tiền theo thời điểm giao dịch. |
| `recorded_at` | Khi hệ thống ghi bản ghi. | Audit ingest, thời gian hệ thống biết. |
| `effective_from/to` | Khoảng dữ kiện có hiệu lực theo nghiệp vụ. | Giá, chính sách, hợp đồng as-of. |
| `deleted_at` | Lúc bị xóa mềm khỏi luồng thông thường. | Lọc dữ liệu hiện hành; **không** thay purge. |
| `retention_until` | Mốc đánh giá/đủ điều kiện xử lý theo policy. | Lưu trữ, purge/ẩn danh có kiểm soát. |

Thời gian nghiệp vụ có thể khác thời gian ghi nhận. Một callback đến trễ lúc 15:00 có thể xác nhận capture xảy ra lúc 14:30. Nếu báo cáo yêu cầu theo thời điểm provider xác nhận thì dùng `confirmed_at`, không dùng `recorded_at`.

**Khi dữ liệu được sửa hồi tố**, có thể cần cả **valid time** và **recorded/system time** (bitemporal). Ví dụ giá hợp lệ từ 01/04 nhưng quyết định correction được ghi ngày 10/04. Từ điển phải cho biết dataset có thể trả lời “giá có hiệu lực ngày 05/04” và “ngày 05/04 hệ thống đang biết giá nào” hay không.

### Khoảng thời gian và timezone

Quy ước `[start_at, end_at)` — bao gồm bắt đầu, loại trừ kết thúc — tránh chồng tại mốc ranh giới. Từ điển cần ghi:

- Thời điểm tuyệt đối dùng UTC/`TIMESTAMPTZ` khi phù hợp.
- Ngày kinh doanh dùng timezone địa phương nào.
- Độ chính xác thời gian: giây, mili giây, micro giây.
- Điều kiện `end_at IS NULL` có nghĩa không xác định điểm kết thúc hay chưa kết thúc.
- Quy tắc kỳ tháng/tuần, múi giờ và ngày chuyển giờ mùa hè nếu áp dụng.

Không tự lấy ngày theo server timezone cho mọi tenant. Cùng một thời điểm UTC có thể thuộc hai ngày kinh doanh khác nhau ở hai khu vực.

## 15. Trường dẫn xuất và chỉ số KPI: ghi công thức cùng ngữ nghĩa

Từ điển không chỉ mô tả cột lưu trực tiếp. Với cột **dẫn xuất**, cần ghi:

1. Nguồn có thẩm quyền và độ mới.
2. Công thức **có đơn vị** và grain đầu ra.
3. Bộ lọc: status nào được tính, thời gian và phạm vi tenant.
4. Xử lý missing/late/retry/correction.
5. Cách làm tròn, tỷ giá, phân loại và tính cộng được.
6. Phiên bản định nghĩa, từ khi nào áp dụng, có restate dữ liệu cũ không.

Ví dụ một mart có hai chỉ số cần tách:

| Metric | Công thức gợi ý | Vì sao khác |
| --- | --- | --- |
| **Booked sales** | Tổng `booked_total_minor` của đơn hợp lệ theo chính sách tại `placed_at`. | Giá trị đặt, không chứng minh đã thu. |
| **Gross captured** | Tổng CAPTURE đã được provider xác nhận. | Dòng tiền thu gộp; có thể nhiều giao dịch trên đơn. |
| **Refunded cash** | Tổng REFUND đã được provider xác nhận. | Không tính `RefundRequested` chưa hoàn. |
| **Net cash** | `gross_captured - refunded_cash` theo currency/kỳ đã thống nhất. | Dòng tiền ròng; không tự là doanh thu kế toán. |
| **Refund rate** | Tử số refund / mẫu số capture theo định nghĩa. | Không lấy AVG các tỷ lệ nhóm nếu trọng số khác nhau. |

Trong data dictionary, **metric definition** cần phân biệt cột raw và KPI dẫn xuất. Một field tên `revenue` trong bảng vật lý không tự chứng minh nó tương đương “doanh thu được công nhận” của Finance.

### Grain dẫn xuất

Nếu `daily_sales_mart` có grain `(tenant_id, business_date, currency_code, channel_id)`, một dòng phải chỉ chứa số liệu cho đúng bốn khóa. Không JOIN bảng movement (grain giao dịch) trực tiếp với bảng order_line (grain dòng hàng) rồi SUM nếu quan hệ một-nhiều ở cả hai phía; phải tổng hợp riêng về grain chung đã xác định.

## 16. Từ điển phải liên kết với ràng buộc kỹ thuật và kiểm thử

Một định nghĩa có giá trị khi có **cách kiểm chứng**.

| Điều được tài liệu hóa | Ràng buộc/kiểm thử phù hợp | Giới hạn |
| --- | --- | --- |
| `quantity > 0` | `CHECK (quantity > 0)`. | Không kiểm tra đơn vị hàng hóa đúng hay không. |
| `order_status` thuộc ba mã | `CHECK ... IN (...)`. | Không kiểm tra chuyển trạng thái hợp lệ. |
| Mỗi OrderLine thuộc một Order | Composite FK theo tenant/order. | Không đảm bảo mỗi Order có ít nhất một dòng tại commit. |
| `provider_reference` duy nhất | UNIQUE theo namespace đã xác minh. | Không tự đảm bảo provider không gửi hai ID cho cùng một business attempt. |
| Một đồng tiền mỗi phép tính | `GROUP BY currency_code` / conversion rule. | Không tự định nghĩa tỷ giá hợp lệ. |
| `confirmed_at` có căn cứ | Đối soát provider confirmation và pipeline receipt. | Kiểu `TIMESTAMPTZ` không chứng minh mốc đúng. |
| Không có PII trong event công bố | Schema contract + kiểm thử payload/quyền. | DDL nguồn không kiểm soát hết consumer. |

### SQL kiểm tra chất lượng dữ liệu

~~~sql
-- 1. Trường không hợp lệ về miền tại source/staging
--    (với bảng đích có CHECK, các hàng như vậy sẽ bị chặn khi ghi).
SELECT tenant_id, order_id, line_no
FROM ordering.sales_order_line
WHERE quantity <= 0
   OR line_net_minor < 0;

-- 2. Kiểm tra orphan ở nguồn đích
--    (FK tại cùng DB thông thường đã bảo vệ).
SELECT l.tenant_id, l.order_id, l.line_no
FROM ordering.sales_order_line l
LEFT JOIN ordering.sales_order o
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
WHERE o.order_id IS NULL;

-- 3. Phân bố giá trị enum (hữu ích khi đối soát nguồn khác).
SELECT order_status, COUNT(*) AS n
FROM ordering.sales_order
GROUP BY order_status;

-- 4. Hai movement cùng provider ref (đã bị UNIQUE bảo vệ trong ví dụ).
SELECT tenant_id, provider_name, provider_reference, COUNT(*) AS n
FROM ordering.payment_movement
GROUP BY tenant_id, provider_name, provider_reference
HAVING COUNT(*) > 1;
~~~

Kiểm thử kiểu “trả 0 hàng” phù hợp với lỗi uniqueness/orphan; các phép kiểm tra chất lượng khác cần **ngưỡng SLO**, ví dụ độ trễ giữa `confirmed_at` và `recorded_at` hoặc tỷ lệ đơn chưa đối soát.

### Những bất biến không nằm gọn trong một CHECK

“Không hoàn vượt số tiền đã thu” có thể cần tổng từ nhiều movement và transaction/ledger owner. “Không bán một ghế hai lần” cần unique/lock ở owner ghế, không chỉ CHECK trên Booking. Trong từ điển ghi **owner, quy tắc và nơi thực thi**, thay vì giả rằng tất cả rule đều phải nằm ở một constraint SQL.

## 17. Có thể sinh phần metadata nào tự động từ PostgreSQL?

DBMS biết tên, kiểu, nullability, default, key, index, một số constraint và comment. Có thể truy xuất các dữ kiện này để so với từ điển.

~~~sql
SELECT
    c.table_schema,
    c.table_name,
    c.ordinal_position,
    c.column_name,
    c.data_type,
    c.character_maximum_length,
    c.numeric_precision,
    c.numeric_scale,
    c.is_nullable,
    c.column_default
FROM information_schema.columns AS c
WHERE c.table_schema = 'ordering'
ORDER BY c.table_name, c.ordinal_position;
~~~

Một query khác liệt kê PK/UNIQUE/FK qua `information_schema.table_constraints`, `key_column_usage` và `constraint_column_usage`, hoặc qua catalog PostgreSQL khi cần chi tiết đặc thù. Cần phân biệt **metadata đang được DB thực thi** với **hợp đồng mong muốn**.

### COMMENT giúp gắn ngữ nghĩa gần schema, nhưng không đủ

~~~sql
COMMENT ON COLUMN ordering.sales_order.booked_total_minor IS
'Giá trị đơn đã chốt, minor units theo currency_code; chưa trừ refund.';
~~~

Ưu điểm: người quản trị SQL có thể thấy giải thích gần cột. Giới hạn:

- Comment không bắt buộc có cấu trúc thống nhất.
- Không thể hiện đầy đủ grain, owner, privacy, quality tests và version.
- Không tự đồng bộ với API/event hay glossary.
- Có thể trở nên stale sau migration.

**Thực hành tốt:** chọn một nguồn tài liệu có quản trị (metadata-as-code hoặc catalog), **đối chiếu tự động với DDL**, và quyết định metadata nào được đồng bộ về `COMMENT`. Không mặc định có hai bản từ điển được sửa độc lập mà không có đường kiểm tra.

## 18. Từ điển dạng máy đọc được và kiểm soát phiên bản

Một nhóm có thể lưu metadata trong YAML/JSON/schema registry và sinh bảng Markdown để người học, người phân tích hoặc developer đọc. Ví dụ **định dạng minh họa**, không phải chuẩn bắt buộc của công cụ nào:

~~~yaml
dataset_id: ordering.sales_order
contract_version: 1
owner: Ordering
grain: "Một đơn đã chốt theo (tenant_id, order_id)"
primary_key:
  - tenant_id
  - order_id
columns:
  - name: order_id
    type: uuid
    nullable: false
    definition: "Định danh bất biến của đơn trong tenant"
  - name: booked_total_minor
    type: bigint
    nullable: false
    unit: "minor units of currency_code"
    domain: "integer >= 0"
    definition: "Giá trị đơn đã chốt, chưa trừ refund"
  - name: currency_code
    type: char(3)
    nullable: false
    domain_ref: "supported_currency_codes"
    definition: "Mã tiền tệ gắn với booked_total_minor"
quality_checks:
  - "PK unique theo (tenant_id, order_id)"
  - "booked_total_minor >= 0"
change_policy: "Đổi nghĩa cần contract mới và đối soát lịch sử"
~~~

Trong dự án thực tế nên có schema validation cho file metadata, quy tắc đặt tên và cách liên kết đến DDL/CI. Bản YAML trên mô tả **contract**, không tự tạo CHECK, FK hay ràng buộc DB.

### Mã định danh khác tên hiển thị

Nếu “Đơn đặt hàng” được đổi nhãn thành “Đơn giao dịch” mà nghĩa giữ nguyên, có thể đổi label. Nếu nghĩa đổi từ đơn đặt sang đơn được thanh toán, cần **term ID/version hoặc thuật ngữ riêng**, không âm thầm sửa định nghĩa của cùng mã rồi diễn giải toàn bộ dữ liệu cũ theo nghĩa mới.

Định nghĩa từ điển cũng có vòng đời: draft, reviewed, approved, deprecated. Một trường bị deprecate vẫn có thể cần tài liệu để giải mã sự kiện/báo cáo lịch sử cho đến khi hết cam kết hỗ trợ.

## 19. Quản trị thay đổi: từ yêu cầu đến DDL, contract và read model

Quy trình bảo trì từ điển nên đi cùng **schema evolution**, không phải viết tài liệu sau khi deploy.

~~~mermaid
flowchart TD
    REQ["Yêu cầu nghiệp vụ"] --> DEF["Định nghĩa grain, cột, đơn vị, miền, owner"]
    DEF --> REV["Review nghiệp vụ + kỹ thuật + data governance"]
    REV --> MODEL["Mô hình logic / ERD / data dictionary version"]
    MODEL --> DDL["Migration SQL, constraints, API/event contract"]
    DDL --> TEST["Test schema, data quality, compatibility"]
    TEST --> DEPLOY["Expand / migrate / cutover / contract"]
    DEPLOY --> OBS["Lineage, lag, drift, KPI, ngoại lệ"]
    OBS --> DEF
~~~

### Khi đổi tên

`customer_name` → `display_name` chỉ là rename nếu **cùng khái niệm và nghĩa**. Cập nhật tên vật lý/API và alias theo kế hoạch tương thích, đồng thời giữ ổn định term ID. Kiểm kê SQL, ORM, CDC, exports và consumer. Nếu có hai cột trong giai đoạn chuyển, ghi rõ cột nào là authoritative và điều kiện đối soát chúng.

### Khi đổi cấu trúc

`customer.phone` → bảng 0..N contact methods: cập nhật grain, quan hệ, khóa, cardinality, quy tắc primary/verified và backfill. Không tự điền `verified_at` nếu nguồn cũ không có bằng chứng. Một bảng từ điển cũ chỉ nói `phone VARCHAR` không đủ bảo vệ trường hợp này.

### Khi đổi ý nghĩa

Nếu `order_status='PAID'` trước đây nghĩa “gửi yêu cầu thu”, còn nay nghĩa “provider xác nhận capture”, phải tạo định nghĩa/hợp đồng mới, có phân biệt dữ liệu legacy, backfill đối soát và consumer migration. Đổi description trong từ điển **không làm dữ liệu quá khứ tự đúng**.

### Điều kiện hoàn thành một thay đổi

- Từ điển logic và vật lý cập nhật đúng contract.
- DDL/schema migration có rollback/cutover phù hợp.
- API/event/CDC consumers được kiểm tra.
- Data quality và số liệu trước/sau được đối soát.
- Owner xác nhận ngữ nghĩa, phương án xử lý lịch sử và retention.
- Có cảnh báo khi metadata được ghi trong từ điển lệch metadata được DB thực thi.

## 20. Dữ liệu đến từ nhiều nguồn: namespace, chuẩn hóa và lineage

Một data dictionary dùng cho tích hợp phải nói rõ nguồn nào cung cấp trường nào.

Ví dụ hai hệ thống có tên `customer_id`:

- CRM: `crm.customer_id = 42`, duy nhất trong CRM.
- E-commerce: `account_id = 42`, duy nhất trong tenant và nền tảng.
- Master data: `canonical_customer_id = CUS-920` sau khi đối chiếu bằng chứng.

Ba giá trị **không tự cùng một khách** vì cùng số 42. Từ điển cần mô tả:

| Metadata | Ví dụ |
| --- | --- |
| Source system | `crm`, `ecommerce`. |
| Source field | `crm.customer_id`, `ecommerce.account_id`. |
| Source namespace/scope | Theo CRM và tenant. |
| Canonical ID mapping | Cơ chế và bằng chứng xác nhận cùng khách. |
| Source-of-truth per attribute | CRM sở hữu phân khúc, Customer Identity sở hữu danh tính đăng nhập. |
| Update/precedence | Có mốc hiệu lực, quy tắc chọn nguồn và cách xử lý conflict. |
| Lineage | Dataset/record nguồn, cursor/batch, rule version, transform. |
| Temporal contract | Giờ cập nhật nguồn, giờ nhận, giờ có hiệu lực. |

Không chọn “bản ghi mới nhất” từ hai nguồn nếu chỉ so timestamp mà chưa chứng minh đồng hồ, nghiệp vụ và nguồn ưu tiên đáng tin. `last_updated_at` của CRM có thể nói khi **CRM lưu**, chứ không nói phân khúc được công nhận có hiệu lực từ khi nào.

### Có thể có nhiều bản dẫn xuất hợp lệ

Một `dim_customer` SCD2 giữ phân khúc tại thời điểm bán; một `customer_current` chỉ giữ phân khúc hiện tại. Cả hai xuất phát từ master nhưng có **grain và thời gian khác nhau**. Dictionary cần ghi mỗi dataset được phép trả lời câu hỏi nào; không áp một tên `segment` với nghĩa mơ hồ cho mọi mart.

## 21. Riêng tư, phân quyền và chính sách giữ dữ liệu là metadata bắt buộc

Từ điển cũng là cơ sở để xác định **dữ liệu nào được phép sử dụng**.

Đối với các cột có thể nhận diện người, vị trí hoặc dữ liệu thanh toán, ghi:

- **Phân loại:** public/internal/confidential/PII/financial hoặc scheme tổ chức đã duyệt.
- **Mục đích xử lý:** vì sao trường cần tồn tại trong dataset này.
- **Owner và data steward:** ai xác nhận quyền đọc/ghi và xử lý yêu cầu.
- **Retention trigger:** tính thời hạn từ khi nào, có ngoại lệ legal hold không.
- **Erasure/anonymization:** trường nào được xóa, bút danh hóa, tổng hợp hoặc phải giữ theo nghĩa vụ khác.
- **Đường dẫn xuất:** API, event, cache, search, report, archive và backup còn chứa trường không.
- **Quyền theo tenant/vai trò:** ai có thể thấy bản chi tiết; dữ liệu đã xóa mềm có được tra cứu không.
- **Đối tác nhận dữ liệu:** contract và giới hạn chia sẻ, không mặc định mọi consumer cần toàn bộ payload.

Ví dụ `customer_id` là UUID nhưng vẫn có thể được liên kết về một con người. Đổi email sang UUID hoặc hash business key **không tự làm dữ liệu vô danh**. Nếu `customer_name` bị xóa khỏi bảng nguồn, các phiên bản trước trong audit, event, CDC, backup hoặc warehouse vẫn cần xử lý theo chính sách.

Không điền một thời hạn pháp lý tùy ý vào từ điển chỉ vì ví dụ có “giữ 7 năm”. Thời hạn thực tế và căn cứ phải được người có thẩm quyền phê duyệt theo loại dữ liệu, khu vực và mục đích.

## 22. Lựa chọn cách mô tả cho document, graph, time-series và warehouse

Từ điển dữ liệu không chỉ dành cho bảng SQL.

| Mô hình | Đơn vị cần tài liệu hóa | Metadata đặc biệt |
| --- | --- | --- |
| **Quan hệ** | Bảng, cột, PK/FK/unique, quan hệ. | Cardinality, check, constraint, index, partition. |
| **Document** | Collection, document type, đường dẫn JSON, array. | Schema version, required/optional/missing, embedded vs reference, array cardinality. |
| **Graph** | Node label, edge type, thuộc tính node/edge. | Hướng cạnh, multiplicity, thời gian hiệu lực, owner quan hệ. |
| **Time-series** | Measurement type, sensor, sample ID, timestamp, value. | Unit, event time vs ingest time, chất lượng, revision, dedup, retention. |
| **Analytical** | Fact, dimension, metric, snapshot, mart. | Grain, additive/semi-additive, SCD, business-time, rule version. |
| **Event store** | Event type, aggregate ID, stream version, payload. | Ý nghĩa sự việc, schema version, idempotency, replay/correction. |

### Document: thiếu key khác key = null

Một JSON document có thể thiếu `middle_name`, có `"middle_name": null`, hoặc có `"middle_name": ""`. Từ điển phải quy định ba dạng này được xử lý giống hay khác; đặc biệt với **JSON Merge Patch/partial update**, thiếu trường có thể nghĩa “giữ nguyên”, còn null có thể nghĩa “xóa”.

### Graph: mô tả cạnh như một dữ kiện nghiệp vụ

Cạnh `Customer-[:OWNS]->Account` cần biết ownership có nghĩa pháp lý hay chỉ quan hệ sử dụng, có hiệu lực từ lúc nào, có thể có nhiều owner không. Chỉ document node/edge label không đủ để tránh traversal suy luận sai.

### Time-series: timestamp không phải danh tính phép đo

Hai mẫu nhiệt độ hợp lệ có thể trùng `measured_at`. Từ điển phải định nghĩa `measurement_id`, `sensor_id`, unit, revision và chính sách correction; nếu dùng `(sensor_id, measured_at)` làm unique theo mặc định, có thể mất dữ liệu thật.

### Warehouse: tỷ lệ không tự cộng được

`inventory_balance` của mỗi ngày là số dư, không SUM qua nhiều ngày như doanh số. `conversion_rate` phải có tử số/mẫu số và grain rõ; trung bình các tỷ lệ từng cửa hàng không luôn bằng tỷ lệ toàn doanh nghiệp. Các điều này là **một phần từ điển measure**, không chỉ logic dashboard.

## 23. Cách tổ chức quy trình review để từ điển không lỗi thời

Một quy trình khả thi:

1. **Người phân tích nghiệp vụ** viết định nghĩa, grain và quy tắc kết quả mong muốn bằng ví dụ phản chứng.
2. **Domain owner** xác nhận điểm chốt, nguồn sự thật, quyền cập nhật, điều kiện chuyển trạng thái.
3. **Data modeler/DB engineer** xác nhận kiểu, PK/FK, cardinality, tính toàn vẹn, index và chiến lược migration.
4. **Data engineer/analytics owner** xác nhận lineage, transform, metric grain, late data và khả năng tái tính.
5. **Security/privacy owner** rà soát phân loại, quyền, retention và dữ liệu dẫn xuất.
6. **Consumer đại diện** kiểm tra tên, enum, nullability và compatibility; không chỉ nhìn compile pass.
7. **CI/CD** kiểm tra metadata schema, drift với database, test dữ liệu, contract và tài liệu phiên bản.
8. **Sau deploy** theo dõi chất lượng, exception, số lượng consumer, field đã deprecate và deadline bỏ hỗ trợ.

Không phải nhóm nhỏ nào cũng có đủ các vai trò thành nhiều người. Có thể một người kiêm nhiệm, nhưng **trách nhiệm phê duyệt** vẫn phải được chỉ rõ.

### Đặt mức ưu tiên tài liệu

Không cần viết hàng chục trang cho một cột kỹ thuật ít dùng. Ưu tiên những trường làm thay đổi kết quả hoặc rủi ro:

- Khóa và foreign/external references.
- Amount, quantity, rate, balance, currency.
- Status/enum quyết định hành vi.
- Timestamp và khoảng thời gian.
- PII và dữ liệu nhạy cảm.
- KPI fact/dimension grain và công thức.
- Các cột có nhiều nguồn hoặc có lịch sử correction.

Tài liệu ngắn nhưng **đủ chính xác, có owner và test** hữu ích hơn một bảng metadata dài được copy từ DDL rồi bỏ quên.

## 24. Sai lầm phổ biến khi xây dựng từ điển dữ liệu

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ ghi tên cột và kiểu DB | Consumer tự đoán nghĩa, đơn vị, NULL. | Thêm definition, grain, unit, domain và owner. |
| Gọi mọi amount là “doanh thu” | Nhầm booked sales với capture/refund/revenue recognized. | Phân biệt điểm chốt và công thức có source. |
| Đặt `VARCHAR(20)` rồi coi status domain đã được kiểm soát | Có mã lạ hoặc chuyển trạng thái sai. | CHECK/reference table + state machine có version. |
| Ghi “timestamp là UTC” nhưng không nói mốc gì | Group theo ngày/cửa sổ sai. | Định nghĩa event/record/effective time và timezone nghiệp vụ. |
| Dùng một giá trị NULL cho mọi nguyên nhân | Không phân biệt chưa xảy ra, không biết, không áp dụng. | Null semantics và trạng thái/reason code cần thiết. |
| Đặt `quantity` không có unit | Cộng kg với chiếc hoặc hiểu sai decimal. | Unit code, scale, chuẩn hóa và quality checks. |
| Chỉ mô tả PK, bỏ business key và namespace | Trùng ID giữa tenant/nguồn, sai mapping. | Scope rõ và mapping có bằng chứng. |
| Ghi bảng Order có 1:N Payment nhưng vẫn SUM sau JOIN nhiều-nhiều | Nhân doanh số. | Định nghĩa grain trước và aggregate theo grain. |
| Coi COMMENT/DDL tự sinh là từ điển hoàn chỉnh | Không có ngữ nghĩa, owner và lineage. | Metadata quản trị + đối chiếu tự động với schema. |
| Đổi nghĩa cột mà không version | Dữ liệu cũ bị hiểu theo định nghĩa mới. | Semantic version, migration và restatement minh bạch. |
| Đổi enum không kiểm tra consumer | Reader cũ lỗi hoặc rơi vào default sai. | Contract test, rollout và deprecation. |
| Có dictionary nhưng không có test | Tài liệu nói một đằng, dữ liệu một nẻo. | Gắn định nghĩa với CHECK/quality SQL/CI. |
| Coi UUID/hash là dữ liệu đã ẩn danh | Vẫn liên kết và tái định danh được. | Classification và retention theo policy. |
| Bảng metadata bị chỉnh bởi nhiều nhóm không owner | Định nghĩa cạnh tranh, không biết ai chốt. | RACI/owner, review và phiên bản được phê duyệt. |
| Đổi schema vật lý mà không cập nhật từ điển | Tài liệu stale và downstream lỗi. | Quy định dictionary diff là phần bắt buộc của migration. |

## 25. Bài tập thực hành: lập từ điển cho hệ thống thuê thiết bị

**Bối cảnh:** nền tảng thuê thiết bị có khách hàng, thiết bị, hợp đồng thuê, các dòng thiết bị, đặt cọc và hoàn cọc. Một hợp đồng có thể gia hạn nhiều lần; khách có thể đổi số liên hệ; payment provider gửi callback muộn hoặc lặp. Đội phân tích cần báo cáo doanh thu thuê, tiền cọc đang giữ và tỷ lệ trả trễ.

Một bản mô hình thô được cung cấp:

~~~text
rental_contract(
    tenant_id, rental_id, customer_id,
    start_time, end_time, status, total_amount
)

rental_item(
    tenant_id, rental_id, line_no, equipment_id,
    quantity, price
)

payment_record(
    tenant_id, payment_id, rental_id,
    type, amount, time, provider_ref
)

equipment(
    tenant_id, equipment_id, code, name, availability
)
~~~

**Nhiệm vụ:**

1. **Định nghĩa grain** chính xác cho bốn bảng. `payment_record` là một attempt, một request hay một movement provider-confirmed? Chọn và giải thích.
2. **Xác định owner/source of truth** cho hợp đồng, số lượng khả dụng, tiền cọc và hồ sơ khách. Dữ liệu nào là external reference?
3. **Lập từ điển cấp bảng** cho `rental_contract`: PK, business key, quan hệ, temporal contract, update policy, retention, index đọc.
4. **Lập từ điển cấp cột** ít nhất 12 trường ở bốn bảng: tên, định nghĩa, kiểu, NULL, unit, domain, source, quality rule.
5. **Làm rõ `start_time/end_time`:** đó là thời hạn hợp đồng, giờ bàn giao/nhận thực tế hay giờ server ghi? Nếu cần cả ba, đề xuất tên trường mới.
6. **Tách `status` thành miền giá trị**: trạng thái hợp đồng khác trạng thái thanh toán và trạng thái thiết bị. Vẽ chuyển tiếp tối thiểu.
7. **Thiết kế tiền và đơn vị:** chọn `amount_minor`, `currency_code`, số lượng và unit; phân biệt giá thuê đã chốt với giá niêm yết hiện hành.
8. **Làm rõ NULL:** `actual_returned_at = NULL` có ý nghĩa gì? `refund_confirmed_at = NULL` có đủ chứng minh chưa hoàn tiền không?
9. **Định nghĩa key/unique:** khóa tổng hợp theo tenant; business key provider reference có namespace ra sao? Nếu hai hợp đồng cùng yêu cầu giữ một thiết bị tại cùng thời gian, kiểm soát bất biến ở đâu?
10. **Tạo DDL PostgreSQL** cho một bảng với PK, FK, CHECK và index theo truy vấn đã xác định; giải thích quy tắc nào không thể chỉ dùng CHECK.
11. **Viết phép kiểm chứng** cho các ca: dòng thuê thiếu hợp đồng, quantity không hợp lệ, movement bị lặp, số tiền hoàn vượt khoản đã thu, thời điểm trả không hợp lệ.
12. **Định nghĩa KPI:** doanh thu thuê, tiền cọc còn giữ, tỷ lệ trả trễ; nêu grain, tử/mẫu, kỳ thời gian, currency và xử lý correction.
13. **Tiến hóa schema:** đổi `code` → `equipment_code` chỉ đổi tên hay đổi nghĩa? Chuyển `phone` của khách từ một số sang nhiều số là đổi cấu trúc gì?
14. **Bảo mật và lịch sử:** khách yêu cầu xóa số điện thoại nhưng hợp đồng/cọc còn nghĩa vụ giữ; từ điển phải ghi các trường và bản dẫn xuất bị ảnh hưởng thế nào?
15. **Metadata-as-code:** viết một đoạn YAML/JSON mô tả bảng `rental_contract` và ba trường có domain/unit; đề xuất test CI phát hiện lệch với DDL.
16. **Architecture Decision Record:** ghi giả định, lựa chọn nguồn sự thật, chính sách versioning, phương pháp review và điều kiện coi từ điển đã hoàn thành.

### Bảng kiểm tự đánh giá

| Tiêu chí | Kết quả đạt |
| --- | --- |
| **Grain và identity** | Mỗi bảng có một định nghĩa hàng, business key/PK và phạm vi tenant rõ. |
| **Ngữ nghĩa** | Không nhầm trạng thái hợp đồng, payment, tồn kho và sự kiện nghiệp vụ. |
| **Kiểu và đơn vị** | Tiền, tỷ lệ, thời lượng, số lượng có unit/precision/rounding phù hợp. |
| **Miền giá trị** | Có domain, chuyển tiếp và điều kiện xuyên trường khi cần. |
| **NULL** | Phân biệt chưa xảy ra, không biết và không áp dụng. |
| **Thời gian** | Biết event-time, effective-time, recorded-time và timezone nghiệp vụ. |
| **Quan hệ** | FK/external reference, cardinality, xóa/retention được giải thích. |
| **Tính đúng** | Có CHECK/constraint và kiểm thử dữ liệu lẫn invariant liên bảng. |
| **Tích hợp** | Có owner, source, lineage, consumer compatibility và rule version. |
| **Quản trị** | Dữ liệu nhạy cảm, quyền và chính sách lưu được ghi có trách nhiệm. |

**Kết luận:** từ điển dữ liệu là **hợp đồng giải thích mô hình**, nối yêu cầu nghiệp vụ với thực thể, quan hệ, kiểu, đơn vị, miền giá trị và quy tắc kiểm chứng. Một bảng có DDL hợp lệ chưa chắc đã có dữ liệu **đúng nghĩa**. Khi mỗi dataset có grain và owner rõ, mỗi trường có định nghĩa/đơn vị/NULL/domain, và các ràng buộc được gắn với test cùng quy trình thay đổi, mô hình mới dễ sử dụng, dễ tích hợp, dễ tiến hóa và có thể kiểm chứng qua thời gian.
