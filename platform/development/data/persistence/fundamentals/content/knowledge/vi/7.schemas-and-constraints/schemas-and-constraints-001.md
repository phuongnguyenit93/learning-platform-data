# Lược đồ dữ liệu và hợp đồng giữa ứng dụng với kho lưu trữ

> **Chương:** Lược đồ và ràng buộc  
> **Module:** DATA_PERSISTENCE_FUNDAMENTALS  
> **Bối cảnh:** Thiết kế ranh giới persistence cho ứng dụng Java từ cấu trúc dữ liệu, truy vấn và chỉ mục tới giao dịch, cô lập, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng.

## 1. Vì sao schema là một hợp đồng, không chỉ là bản vẽ bảng?

Giả sử dịch vụ đặt hàng Java ghi một đơn mới xuống cơ sở dữ liệu. Lúc đầu, bảng `orders` có ba trường: `id`, `customer_id` và `total`. Một lập trình viên hiểu `total` là **số tiền VND**, người khác lại hiểu là **số xu USD**. Khi một yêu cầu gửi `total = 100000`, cả hai chương trình đều có thể ghi thành công nhưng diễn giải số tiền hoàn toàn khác nhau.

Tương tự, nếu API coi `status = "PAID"` là một trạng thái hợp lệ nhưng database cho phép mọi chuỗi, một đoạn script có thể ghi `status = "DONE"`; ứng dụng mới không biết phải xử lý nó ra sao. Đây là ví dụ **hợp đồng dữ liệu bị thiếu hoặc không đồng nhất**.

**Schema (lược đồ dữ liệu)** mô tả những thực thể, thuộc tính, kiểu dữ liệu, quan hệ và ràng buộc mà hệ thống lưu trữ chấp nhận. **Hợp đồng persistence** mở rộng ý nghĩa đó thành những cam kết giữa mã ứng dụng với kho dữ liệu: trường có nghĩa gì, cách đọc/ghi thế nào, điều kiện nào được bảo vệ, khi nào giao dịch thành công, dữ liệu cũ được đọc ra sao.

Một thiết kế đủ tốt cần giúp trả lời:

1. **Dữ liệu có dạng gì?** Bảng, document, bản ghi, trường, kiểu, khóa, quan hệ.
2. **Dữ liệu có nghĩa gì?** Tiền tệ, thời điểm, trạng thái, đơn vị đo, người sở hữu.
3. **Điều gì không được phép sai?** Bất biến, khóa duy nhất, tham chiếu hợp lệ, miền giá trị.
4. **Ai được phép đọc/ghi?** Quyền, phạm vi tenant, kiểm toán và dữ liệu nhạy cảm.
5. **Thao tác nào phải xảy ra cùng nhau?** Transaction, kiểm soát đồng thời, ranh giới nhất quán.
6. **Ứng dụng nào phụ thuộc schema?** Repository, job nền, báo cáo, CDC, tích hợp ngoài.
7. **Thay đổi theo thời gian thế nào?** Migration, phiên bản, dữ liệu lịch sử và khôi phục.

Mục tiêu bài học: sau khi học, người đọc có thể **đề xuất một hợp đồng dữ liệu cho ứng dụng Java, hiện thực một phần bằng SQL và JDBC, phân biệt trách nhiệm giữa các tầng và lên kế hoạch thay đổi schema an toàn**.

## 2. Ba góc nhìn về lược đồ

Để tránh biến chi tiết lưu trữ thành logic nghiệp vụ, nên phân biệt ba lớp thiết kế:

| Góc nhìn | Câu hỏi chính | Ví dụ với đơn hàng |
| --- | --- | --- |
| **Khái niệm (conceptual)** | Thực thể nào tồn tại và có quan hệ nghiệp vụ gì? | Khách có nhiều đơn; đơn có các dòng hàng |
| **Logic (logical)** | Dữ liệu được mô hình hóa và ràng buộc ra sao, độc lập tối đa với vendor? | `Order(id, customerId, status, total, lines)`, khóa, tính duy nhất |
| **Vật lý (physical)** | Công nghệ lưu cụ thể thực hiện thế nào? | PostgreSQL `UUID`, `BIGINT`, `CHECK`, index B-tree, partition |

Trong một hệ document, lớp logic có thể xác định đơn hàng và các dòng hàng là **một aggregate document**; lớp vật lý chọn collection, partition key, index và hạn mức kích thước document. Trong hệ quan hệ, lớp vật lý chọn bảng, ràng buộc khóa ngoại và kiểu cột.

**Không bắt buộc một lớp Java phải tương đương một bảng** và cũng không bắt buộc một JSON object phải tương đương một document lưu trữ. Domain model ưu tiên hành vi và bất biến nghiệp vụ; schema vật lý ưu tiên khả năng ghi, đọc, kiểm soát nhất quán và vận hành.

### 2.1. Ví dụ mô hình khái niệm

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : referenced_by
    ORDER {
        uuid id PK
        uuid customer_id FK
        string status
        integer total_minor
        string currency_code
        integer version
    }
    ORDER_LINE {
        uuid order_id FK
        integer line_no
        uuid product_id FK
        integer quantity
        integer unit_price_minor
    }
~~~

Đây là mô hình khái niệm giản lược. Để hỗ trợ **lưu nháp chưa có dòng hàng**, quan hệ “một hoặc nhiều dòng” chỉ bắt buộc khi đơn được nộp; nếu cần cho phép nháp rỗng, hợp đồng phải diễn đạt điều kiện phụ thuộc trạng thái, không được rập khuôn theo ký hiệu trên sơ đồ.

## 3. Hợp đồng giữa ứng dụng và kho lưu trữ gồm những phần nào?

Hợp đồng không chỉ là câu `CREATE TABLE`. Nó có thể được ghi trong tài liệu, schema, repository interface, test và quy ước vận hành:

| Thành phần hợp đồng | Nội dung cần xác định |
| --- | --- |
| **Định danh** | Khóa chính ổn định, key nghiệp vụ, cách chống trùng |
| **Trường và kiểu** | Tên, loại giá trị, độ dài, precision/scale, nullability |
| **Ngữ nghĩa** | Đơn vị tiền, múi giờ, ý nghĩa trạng thái, quy tắc canonicalization |
| **Quan hệ** | Cardinality, khóa ngoại, quy tắc xóa/cập nhật tham chiếu |
| **Bất biến** | Số lượng dương, tổng tiền không âm, trạng thái được phép |
| **Đọc** | Query/filter/sort, phân trang, mức độ mới của dữ liệu, giới hạn kết quả |
| **Ghi** | Atomicity, transaction boundary, điều kiện chuyển trạng thái, idempotency |
| **Xung đột** | Version, khóa, isolation, mã lỗi và cách retry |
| **Vòng đời** | Migration, retention, audit, backup/restore, schema version |
| **Bảo mật** | Quyền theo bảng/hàng/tenant, dữ liệu nhạy cảm, truy vết |

Một số phần do **database** bảo vệ; một số do **domain/service** bảo vệ; một số cần phối hợp cả hai. Ví dụ “quantity phải dương” có thể đặt `CHECK (quantity > 0)` ở DB, trong khi “đơn đã giao không được đổi địa chỉ” là điều kiện chuyển trạng thái phức tạp hơn.

### 3.1. Nguồn sự thật và bản sao dẫn xuất

Nếu dữ liệu đơn được lưu chính thức ở database giao dịch, còn search index hay cache giữ bản sao, hợp đồng phải nói rõ **nơi nào là nguồn sự thật**. Việc search index chậm cập nhật không nên khiến hệ thống xác nhận thanh toán dựa trên trạng thái cũ.

Với nhiều dịch vụ sử dụng chung database, cần xác định **ai được quyền thay đổi schema** và cách các consumer nhận biết thay đổi. Kể cả khi mỗi dịch vụ có database riêng, contract vẫn tồn tại tại API/event schema và qua quy tắc đồng bộ dữ liệu.

## 4. Thiết kế kiểu dữ liệu có ý nghĩa, không chỉ “chứa vừa số”

Mỗi cột phải được lựa chọn theo **miền giá trị** và **cách sử dụng**:

| Dữ liệu nghiệp vụ | Ví dụ kiểu PostgreSQL | Lưu ý |
| --- | --- | --- |
| Định danh đơn | `UUID` | Không dùng vị trí dòng hoặc địa chỉ object Java |
| Số lượng món | `INTEGER` với `CHECK > 0` | Nếu đo theo kg thì cần decimal/unit thay vì giả định nguyên |
| Tiền theo minor units | `BIGINT` và `currency_code` | Quy định minor unit theo currency; kiểm tra overflow |
| Tiền tính toán thập phân | `NUMERIC(p,s)` | Quy định scale, rounding; không dùng `double` cho tiền cần chính xác |
| Thời điểm sự kiện | `TIMESTAMPTZ` | Lưu instant; timezone hiển thị thuộc nhu cầu khác |
| Trạng thái | `TEXT` + `CHECK` hoặc type phù hợp | Có quy tắc chuyển và phiên bản thay đổi |
| Nội dung mô tả | `TEXT` | Charset/collation, bảo mật, index tìm kiếm khi cần |
| Cờ được/không | `BOOLEAN` | Tránh dùng ba trạng thái ngầm nếu NULL chưa được định nghĩa |
| Version kiểm soát ghi | `BIGINT` | Tăng nguyên tử mỗi lần thay đổi aggregate |

### 4.1. Quyết định precision và scale dựa trên yêu cầu

`NUMERIC(18, 2)` cho phép tối đa 18 chữ số, trong đó 2 chữ số sau dấu thập phân. Nó **không tự nói rõ currency** hoặc lúc nào cần làm tròn. Một thay đổi từ `NUMERIC(12,2)` sang `NUMERIC(18,4)` còn có thể tác động API, đối soát và dữ liệu cũ.

Nếu dùng số tiền nguyên theo minor units, `long` của Java thường ánh xạ tốt với `BIGINT` của PostgreSQL; nhưng phải xác định **minor unit của từng loại tiền**, tránh mặc định mọi loại tiền có hai chữ số thập phân.

### 4.2. Tên cột phải tránh gây hiểu lầm

Cột `temperature` không nêu đơn vị; `temperature_celsius` hoặc cặp `temperature_value`, `temperature_unit` rõ nghĩa hơn. Cột `created_at` phải được định nghĩa là **thời điểm tạo trong hệ thống** hay **thời điểm khách thực hiện sự kiện**.

Tên trường tốt làm giảm rủi ro, nhưng **không thay thế constraint hoặc hợp đồng**. Chẳng hạn, cột `quantity_positive` vẫn có thể bị ghi số âm nếu không kiểm tra.

## 5. Ví dụ schema quan hệ cho đơn hàng

Ví dụ sau dùng PostgreSQL, tập trung vào các quy tắc dữ liệu lõi. Đây là một **mẫu học tập**, chưa phải toàn bộ schema cho hệ thống thương mại điện tử.

~~~sql
CREATE TABLE customers (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customers_email UNIQUE (email)
);

CREATE TABLE products (
    id UUID PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    available_qty INTEGER NOT NULL CHECK (available_qty >= 0)
);

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL
        REFERENCES customers(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    total_minor BIGINT NOT NULL DEFAULT 0,
    currency_code VARCHAR(3) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMPTZ,
    CONSTRAINT chk_order_status
        CHECK (status IN ('DRAFT', 'SUBMITTED', 'PAID',
                         'SHIPPED', 'CANCELLED')),
    CONSTRAINT chk_order_total
        CHECK (total_minor >= 0),
    CONSTRAINT chk_order_currency
        CHECK (currency_code ~ '^[A-Z]{3}$'),
    CONSTRAINT chk_order_version
        CHECK (version >= 0),
    CONSTRAINT chk_submitted_at
        CHECK (status = 'DRAFT' OR submitted_at IS NOT NULL)
);

CREATE TABLE order_lines (
    order_id UUID NOT NULL
        REFERENCES orders(id) ON DELETE RESTRICT,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_minor BIGINT NOT NULL
        CHECK (unit_price_minor >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

### 5.1. Những gì schema trên bảo vệ

- Không có hai dòng `orders` cùng `id`.
- Một đơn phải tham chiếu khách đang tồn tại.
- Giá trị trạng thái phải nằm trong một tập hữu hạn.
- Tổng tiền, version, số lượng và đơn giá không âm theo quy tắc hiện tại.
- Các dòng thuộc đơn được định danh bằng cặp `(order_id, line_no)`.
- Nếu trạng thái khác nháp, phải có `submitted_at`.

### 5.2. Những gì schema trên **chưa** bảo vệ

- Cột `currency_code` mới được kiểm tra **định dạng ba chữ cái**, chưa kiểm tra mã tiền có được hỗ trợ trong nghiệp vụ hay không.
- Ràng buộc `UNIQUE(email)` so sánh theo hành vi của kiểu/collation đang áp dụng. Nếu đăng nhập không phân biệt hoa/thường, cần thiết kế canonical key hoặc cách so sánh tương ứng; không mặc nhiên coi `A@example.com` bằng `a@example.com`.
- Không có constraint đơn giản đảm bảo `orders.total_minor` luôn bằng tổng `quantity × unit_price_minor` của tất cả dòng hàng, vì phép tính trải qua nhiều dòng/bảng.
- Không biết người gửi lệnh đã có quyền hay chưa.
- Không ngăn một lệnh trực tiếp chuyển `DRAFT → PAID` nếu ứng dụng bỏ qua state machine.
- Không thay thế giao dịch khi vừa tạo đơn vừa trừ tồn kho.

**Bài học:** constraint ở DB bảo vệ một tập bất biến được biểu diễn cụ thể; domain/service phải bảo vệ phần còn lại, và những bất biến xuyên nhiều bản ghi cần ranh giới transaction/khóa thích hợp.

## 6. Primary key, unique key và định danh nghiệp vụ

**Primary key** định danh duy nhất một bản ghi. Một **business key** có thể là mã SKU, mã đơn công khai hoặc mã yêu cầu thanh toán.

| Loại khóa | Ví dụ | Lưu ý |
| --- | --- | --- |
| Primary key | `orders.id` (UUID) | Dùng để liên kết ổn định, không nên thay vì đổi tên hiển thị |
| Unique business key | `products.sku` | Cần xác định phạm vi duy nhất và quy tắc chuẩn hóa |
| Composite key | `(order_id, line_no)` | Một số bản ghi được định danh trong ngữ cảnh bản ghi cha |
| Idempotency key | `(tenant_id, request_key)` | Chống tạo tác động lặp khi client retry |
| Foreign key | `order_lines.order_id` | Bảo vệ tham chiếu giữa các bảng |

Một mã hiển thị như `ORD-2026-00123` có thể đổi quy tắc sinh theo năm hoặc kênh bán; dùng một ID nội bộ ổn định giúp tránh nối dữ liệu vào định dạng hiển thị.

### 6.1. Unique constraint và nhiều request đồng thời

Hai request có thể cùng kiểm tra “email chưa tồn tại” rồi cùng tạo tài khoản. Kiểm tra trước ở ứng dụng là hữu ích cho thông báo lỗi, nhưng **không chống được cuộc đua** nếu không có ràng buộc duy nhất hoặc thao tác ghi nguyên tử.

Một unique constraint tại DB là chốt kiểm soát cuối cùng cho phạm vi duy nhất mà nó mô tả. Ứng dụng phải xử lý lỗi vi phạm, nhưng không được coi mọi lỗi unique là “email đã tồn tại”: cần biết **constraint nào** bị vi phạm.

### 6.2. UNIQUE và NULL

Hành vi nhiều giá trị `NULL` dưới ràng buộc `UNIQUE` phụ thuộc sản phẩm và cấu hình. Trong PostgreSQL theo mặc định, nhiều hàng với `NULL` ở cột unique có thể cùng tồn tại vì `NULL` không được xem là bằng nhau theo cơ chế đó.

Vì vậy, nếu một trường **bắt buộc có giá trị và duy nhất**, thường cần cả `NOT NULL` và `UNIQUE`. Nếu nghiệp vụ chỉ yêu cầu duy nhất khi trường có giá trị, cần diễn giải và thử đúng hành vi mong đợi.

## 7. NULL là “chưa biết”, “không áp dụng” hay “chưa nhập”?

Trong SQL, `NULL` biểu thị **không có một giá trị xác định**, chứ không phải số 0, chuỗi rỗng hay `false`. Ứng dụng phải có quy ước nghiệp vụ cụ thể.

Ví dụ:

| Trường | `NULL` có thể mang nghĩa gì? | Thiết kế phù hợp |
| --- | --- | --- |
| `submitted_at` | Đơn chưa nộp | Nullable khi `status = DRAFT` |
| `delivered_at` | Chưa giao hoặc chưa biết thời điểm | Có thể cần status riêng để phân biệt |
| `weight_grams` | Chưa cân | Không dùng 0 thay thế nếu 0 là một phép đo có nghĩa |
| `discount_minor` | Chưa áp dụng quy tắc chiết khấu | Có thể cần 0 hoặc NULL tùy hợp đồng |

### 7.1. Logic ba giá trị và CHECK

Trong SQL, điều kiện có thể là `TRUE`, `FALSE` hoặc `UNKNOWN`. So sánh `column = NULL` không phải cách tìm giá trị NULL; phải dùng `IS NULL`.

~~~sql
SELECT id
FROM orders
WHERE submitted_at IS NULL;
~~~

Đặc biệt, một `CHECK (price > 0)` trong PostgreSQL **không từ chối NULL** chỉ vì biểu thức thành UNKNOWN; muốn cấm NULL phải đặt thêm `NOT NULL`. Hiểu đúng điều này giúp tránh lược đồ nhìn có vẻ bảo vệ miền giá trị nhưng vẫn chấp nhận “thiếu dữ liệu”.

### 7.2. Có nên đặt default?

`DEFAULT 0` phù hợp khi 0 thực sự là giá trị khởi tạo đúng, ví dụ tổng tiền của một đơn nháp trống theo quy tắc đã chọn. Nó không phù hợp nếu 0 sẽ khiến một phép đo chưa có trở thành kết quả đo được.

Không nên gán mặc định `status = 'PAID'` hoặc thời điểm thanh toán chỉ để tránh NULL. **Giá trị mặc định cũng là quy tắc nghiệp vụ** và phải được kiểm tra.

## 8. CHECK, foreign key và ranh giới của constraint

Cơ sở dữ liệu có thể bảo vệ nhiều bất biến trực tiếp:

~~~sql
-- PostgreSQL: minh họa constraint theo hàng.
ALTER TABLE products
ADD CONSTRAINT chk_product_stock
CHECK (available_qty >= 0);
~~~

Trong ví dụ schema ở mục 5, `products.available_qty` đã có `CHECK (available_qty >= 0)`; câu lệnh trên **chỉ minh họa cú pháp ALTER TABLE**, không được chạy nối tiếp trên schema mẫu với cùng quy tắc mà không xem xét constraint trùng.

### 8.1. Quy tắc có liên quan nhiều hàng

“Một đơn đã nộp phải có ít nhất một dòng hàng” là ràng buộc trải qua bảng `orders` và `order_lines`. `CHECK` thông thường của PostgreSQL không được thiết kế để kiểm tra truy vấn tổng hợp qua các hàng/bảng khác.

Một quy trình an toàn có thể:

1. Bắt đầu transaction.
2. Khóa hoặc kiểm soát version của hàng `orders` đang được nộp.
3. Đọc và xác minh danh sách dòng hàng, giá, số lượng.
4. Chỉ chuyển trạng thái khi tập dòng hàng hợp lệ.
5. Commit tất cả thay đổi liên quan; rollback khi điều kiện thất bại.

Nếu luồng khác có thể sửa `order_lines` mà không tuân theo quy tắc khóa/kiểm soát cùng aggregate, bước 3 vẫn có rủi ro race. **Phải yêu cầu tất cả đường ghi dùng cùng quy ước đồng thời**.

### 8.2. ON DELETE: đừng chọn CASCADE theo thói quen

Các lựa chọn như `RESTRICT`, `NO ACTION`, `CASCADE` hoặc `SET NULL` có ảnh hưởng lớn:

- Xóa một khách có nên xóa lịch sử đơn hàng của họ không?
- Xóa một sản phẩm có làm mất dòng hàng đã mua không?
- Khi một record bị soft delete, khóa ngoại có cần giữ nguyên không?

Với dữ liệu giao dịch và kiểm toán, nhiều trường hợp **không nên xóa dây chuyền lịch sử**. Bảo vệ quyền riêng tư và chính sách lưu giữ có thể cần các cơ chế ẩn danh hóa/xóa theo quy trình được xác định riêng.

## 9. Mã hóa và làm rõ trạng thái nghiệp vụ

Một schema có cột `status TEXT` và `CHECK status IN (...)` giúp không nhận giá trị ngoài tập, nhưng chưa diễn đạt đầy đủ **đồ thị chuyển trạng thái**.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED: SubmitOrder
    DRAFT --> CANCELLED: CancelDraft
    SUBMITTED --> PAID: ConfirmPayment
    SUBMITTED --> CANCELLED: CancelUnpaid
    PAID --> SHIPPED: Ship
    SHIPPED --> [*]
    CANCELLED --> [*]
~~~

Trong mô hình minh họa này, `DRAFT → PAID` bị cấm dù `PAID` là một giá trị status hợp lệ. Domain/service phải kiểm tra nguồn, lệnh và guard. Tầng persistence cần chống trường hợp **kiểm tra trạng thái cũ trước, dữ liệu đã thay đổi ngay trước lúc ghi**.

Một câu `UPDATE` có điều kiện minh họa:

~~~sql
UPDATE orders
SET status = 'SUBMITTED',
    submitted_at = :submittedAt,
    version = version + 1
WHERE id = :orderId
  AND customer_id = :customerId
  AND status = 'DRAFT'
  AND version = :expectedVersion;
~~~

Các tham số dạng `:orderId` là ký hiệu ở tầng repository/framework, không phải cú pháp trực tiếp của mọi SQL console. Nếu câu lệnh cập nhật **0 hàng**, có thể do không có bản ghi, không có quyền, trạng thái khác hoặc version đã thay đổi. Nếu **1 hàng**, cập nhật đã áp dụng ở mức statement; nếu vẫn đang trong transaction thì chưa thể coi là thành công cho tới khi commit theo hợp đồng.

**Version** có thể dùng để thực hiện *optimistic locking*. Nó không thay thế transaction cho những bất biến liên quan nhiều bảng nếu các đường ghi khác bỏ qua version hoặc không khóa cùng aggregate.

## 10. Index là một phần của thiết kế truy vấn, không thay thế constraint

Schema logic phải hỗ trợ các **mẫu đọc và ghi thực tế**. Giả sử API thường lấy 20 đơn mới nhất của một khách:

~~~sql
SELECT id, status, total_minor, currency_code, created_at
FROM orders
WHERE customer_id = :customerId
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Với PostgreSQL, một index ghép có thể là:

~~~sql
CREATE INDEX idx_orders_customer_recent
ON orders (customer_id, created_at DESC, id DESC);
~~~

Index này phục vụ bộ lọc khách hàng và thứ tự thời gian; cần đo với `EXPLAIN` và dữ liệu đại diện trước khi kết luận hiệu quả. Mỗi index làm tăng chi phí bảo trì khi ghi và dùng thêm dung lượng.

### 10.1. Constraint và index có quan hệ nhưng không đồng nghĩa

- `PRIMARY KEY` và `UNIQUE` trên PostgreSQL thường có index được tạo để hỗ trợ thực thi ràng buộc.
- Khóa ngoại bảo đảm tính tham chiếu nhưng **PostgreSQL không tự động tạo index trên mọi cột phía tham chiếu**; nhiều workload cần tự tạo index cho cột FK.
- Index không unique giúp tăng tốc truy vấn nhưng **không bảo đảm tính duy nhất**.
- Một partial/functional index có thể hữu ích cho query hoặc ràng buộc chuyên biệt, nhưng cần biết sản phẩm hỗ trợ gì và triển khai migration ra sao.

Chọn index dựa trên **câu truy vấn**, độ chọn lọc, dữ liệu, kế hoạch thực thi và tỷ lệ đọc/ghi; không nên tạo index cho mọi cột vì “đó là cột quan trọng”.

## 11. Ranh giới Java: domain model, DTO và persistence model

Ba mô hình thường có mục đích khác nhau:

| Mô hình | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| **API DTO** | Nhận/trả dữ liệu qua HTTP hoặc event | `CreateOrderRequest`, `OrderResponse` |
| **Domain model** | Biểu diễn hành vi, bất biến và trạng thái | `Order.submit()`, `Money`, `OrderLine` |
| **Persistence model** | Ánh xạ dữ liệu với bảng/document và metadata lưu trữ | `OrderRow`, JPA entity, JDBC mapping |

Trong ứng dụng nhỏ, các mô hình này có thể trùng một phần. Tuy nhiên, việc đưa trực tiếp JPA entity ra API thường tăng nguy cơ:

- Client tự ghi các trường không được phép (*mass assignment*), ví dụ `status`, `version` hay `customer_id`.
- Làm lộ dữ liệu nội bộ hoặc thông tin nhạy cảm.
- Serialization vô tình kích hoạt lazy loading, N+1 query hoặc vòng lặp quan hệ.
- Một migration schema buộc thay đổi hợp đồng API dù ý nghĩa nghiệp vụ không đổi.

**Ranh giới persistence** nên cho phép service phát biểu ý định nghiệp vụ mà không cần tự xử lý tên cột hoặc kết nối.

### 11.1. Repository port: thể hiện hành vi, không chỉ CRUD

~~~java
import java.util.Optional;
import java.util.UUID;

record OrderSnapshot(
        UUID id,
        UUID customerId,
        String status,
        long totalMinor,
        String currencyCode,
        long version) {}

interface OrderRepository {
    Optional<OrderSnapshot> findVisibleOrder(
            UUID orderId, UUID customerId);

    boolean submitIfDraft(
            UUID orderId,
            UUID customerId,
            long expectedVersion);
}
~~~

`submitIfDraft` nói rõ đây là **chuyển trạng thái có điều kiện**, tránh hiểu nhầm rằng service có thể gọi `save(Order)` để ghi đè toàn bộ bản ghi tùy ý. Interface vẫn cần tài liệu về transaction: phương thức trả về `true` lúc nào, có thể ném lỗi gì, có retry nội bộ không, và caller xử lý kết quả không rõ như thế nào.

## 12. JDBC: đọc/ghi đúng kiểu, đúng scope và đúng hợp đồng

Ví dụ Java 17+ dưới đây ánh xạ dữ liệu đọc từ PostgreSQL thành một record bất biến và cập nhật trạng thái có điều kiện. Đây là **ví dụ một repository đơn giản**, không thay thế framework giao dịch, kiểm soát quyền toàn ứng dụng hoặc thiết kế domain đầy đủ.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import javax.sql.DataSource;

final class JdbcOrderRepository implements OrderRepository {
    private final DataSource dataSource;

    JdbcOrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public Optional<OrderSnapshot> findVisibleOrder(
            UUID orderId, UUID customerId) {
        String sql = """
                SELECT id, customer_id, status, total_minor,
                       currency_code, version
                FROM orders
                WHERE id = ? AND customer_id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, orderId);
            statement.setObject(2, customerId);
            try (ResultSet rows = statement.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }
                return Optional.of(new OrderSnapshot(
                        rows.getObject("id", UUID.class),
                        rows.getObject("customer_id", UUID.class),
                        rows.getString("status"),
                        rows.getLong("total_minor"),
                        rows.getString("currency_code"),
                        rows.getLong("version")));
            }
        } catch (SQLException error) {
            throw new IllegalStateException("Khong the doc don", error);
        }
    }

    @Override
    public boolean submitIfDraft(
            UUID orderId, UUID customerId, long expectedVersion) {
        String sql = """
                UPDATE orders
                   SET status = 'SUBMITTED',
                       submitted_at = CURRENT_TIMESTAMP,
                       version = version + 1
                 WHERE id = ?
                   AND customer_id = ?
                   AND status = 'DRAFT'
                   AND version = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, orderId);
            statement.setObject(2, customerId);
            statement.setLong(3, expectedVersion);
            return statement.executeUpdate() == 1;
        } catch (SQLException error) {
            throw new IllegalStateException("Khong the nop don", error);
        }
    }
}
~~~

Chú ý:

1. `PreparedStatement` truyền tham số đúng cách, tránh nối chuỗi SQL bằng input người dùng.
2. Query có thêm `customer_id = ?` để giới hạn phạm vi dữ liệu ở repository; **thẩm quyền caller vẫn cần được xác minh từ nguồn đáng tin cậy**, không nhận tùy ý `customerId` từ client.
3. Phương thức cập nhật dùng một statement và connection mặc định autocommit. Nếu cần ghi cả `order_lines` và trừ tồn kho, hãy chuyển transaction boundary lên lớp điều phối phù hợp thay vì mở một connection riêng cho mỗi thao tác.
4. `SQLException` đang được bọc để ngắn gọn. Trong production cần phân loại lỗi database/timeout có thể retry, lỗi constraint và lỗi hạ tầng thay vì đánh đồng mọi trường hợp.
5. Chuyển thành `SUBMITTED` chưa xác minh “đơn có dòng hàng” trong câu `UPDATE`. Guard nghiệp vụ đó phải được bảo vệ trong cùng transaction/điều kiện cập nhật phù hợp.

### 12.1. Tại sao không tự gán giá trị default?

Nếu schema định nghĩa `created_at DEFAULT CURRENT_TIMESTAMP`, thao tác `INSERT` có thể bỏ trường đó để database tạo. Nhưng nếu service cần ghi **thời điểm nghiệp vụ do hệ thống quyết định** khác thời điểm ghi, phải có trường riêng; không dùng một cột cho nhiều nghĩa thời gian.

Trong Java, ánh xạ `TIMESTAMPTZ` qua `OffsetDateTime` hoặc `Instant` theo driver/ORM hỗ trợ và kiểm thử round trip. Không coi `LocalDateTime` không có zone là timestamp tuyệt đối nếu nghiệp vụ yêu cầu xác định một thời điểm trên trục thời gian.

## 13. Đúng schema vẫn cần transaction và isolation

Các câu lệnh riêng lẻ có thể đều hợp lệ nhưng **tổng thể nghiệp vụ vẫn sai** nếu một phần thành công còn phần kia thất bại.

Ví dụ quy trình tạo đơn:

~~~mermaid
flowchart TD
    A["Nhận CreateOrder command"] --> B["Kiểm tra quyền, sản phẩm, giá"]
    B --> C["Bắt đầu transaction"]
    C --> D["Giảm tồn kho có điều kiện"]
    D --> E{"Đủ tồn và không xung đột?"}
    E -- Không --> R["Rollback + phản hồi phù hợp"]
    E -- Có --> F["Insert orders + order_lines"]
    F --> G["Ghi outbox nếu cần"]
    G --> H{"Commit thành công?"}
    H -- Có --> I["Trả kết quả đơn đã tạo"]
    H -- Không rõ --> J["Tra cứu theo idempotency key"]
    H -- Thất bại rõ --> R
~~~

Ghi nhận doanh thu, số lượng tồn và sự kiện gửi ra hệ thống khác cần **ranh giới nhất quán** được thiết kế rõ. Nếu gửi message qua mạng ngay giữa transaction, database có thể rollback sau khi message đã đến bên nhận. Một cách xử lý là **transactional outbox**: ghi outbox cùng transaction với thay đổi nghiệp vụ, worker phát message sau đó và consumer xử lý lặp an toàn.

### 13.1. Trừ tồn kho bằng cập nhật có điều kiện

~~~sql
UPDATE products
SET available_qty = available_qty - :quantity
WHERE id = :productId
  AND available_qty >= :quantity;
~~~

Ứng dụng kiểm tra số hàng cập nhật, yêu cầu `quantity > 0` đã được xác thực, và bảo vệ thao tác trừ kho cùng thao tác tạo đơn trong transaction phù hợp. Nếu 0 hàng, có thể do không có sản phẩm hoặc không đủ tồn — không mặc nhiên thông báo thành công.

### 13.2. Isolation không phải một lựa chọn mặc định bất biến

`READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` có hành vi khác nhau tùy database. Trước khi chọn isolation, cần xác định bất thường nào phải ngăn: lost update, write skew, đọc không nhất quán, các quyết định dựa trên tổng hợp hay danh sách nhiều hàng.

Không được suy rằng **có transaction tức là mọi concurrent request đều xử lý đúng**. Phải kiểm thử cạnh tranh trên dữ liệu thật, và tuân thủ quy tắc lock/conditional update trên **mọi đường ghi**.

## 14. Khác biệt giữa lỗi dữ liệu và lỗi hạ tầng

Hợp đồng repository cần nói rõ điều gì xảy ra khi ghi thất bại:

| Loại lỗi | Nguyên nhân điển hình | Cách phản hồi |
| --- | --- | --- |
| Vi phạm NOT NULL/CHECK | Input hoặc trạng thái nghiệp vụ không hợp lệ | Không retry mù quáng; sửa input/logic |
| Vi phạm UNIQUE | Mã nghiệp vụ trùng, request lặp | Xác minh khóa/constraint; xử lý idempotency nếu phù hợp |
| Vi phạm FK | Tham chiếu không tồn tại hoặc cạnh tranh xóa | Kiểm tra dữ liệu liên quan, ranh giới transaction |
| Optimistic lock thất bại | Version thay đổi | Đọc lại trạng thái; trả xung đột hoặc retry an toàn |
| Deadlock/serialization failure | Giao dịch đồng thời tranh chấp | Rollback và thử lại toàn transaction có giới hạn |
| Connection timeout | Network/pool/database quá tải | Phân loại trạng thái; chỉ retry khi an toàn |
| Kết quả commit không rõ | Mất kết nối sát thời điểm xác nhận | Tra cứu bằng khóa ổn định trước khi gửi lại |

Với PostgreSQL, driver có thể trả SQLSTATE giúp phân loại, chẳng hạn `23505` cho unique violation, `23503` cho foreign-key violation, `23514` cho check violation. **Đây là mã đặc thù của PostgreSQL**, không nên mã hóa cứng chúng thành hợp đồng domain chung cho mọi vendor.

### 14.1. Không retry thao tác không idempotent bằng cách tạo ID mới

Một client gửi `CreateOrder` rồi nhận timeout. Nếu server có thể đã commit, gửi lại bằng ID mới có thể tạo **hai đơn**. Nên thiết kế mã yêu cầu (*idempotency key*) lưu bền cùng kết quả nghiệp vụ hoặc dùng khóa duy nhất do client/server thống nhất từ đầu.

**Schema hỗ trợ sự an toàn này**, ví dụ:

~~~sql
CREATE TABLE processed_requests (
    request_key TEXT PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Việc ghi `processed_requests` và tạo đơn phải có **cùng transaction boundary**; chỉ tạo bảng thôi chưa đủ đảm bảo chống lặp. Cũng cần xác thực rằng một request key không được tái sử dụng với payload mang nội dung khác.

## 15. Schema migration: hợp đồng phải tiến hóa qua nhiều phiên bản

Database lưu dữ liệu lâu hơn một bản phát hành ứng dụng. Một bản deploy mới có thể chạy đồng thời với các instance cũ. Vì thế, đổi schema là **thay đổi hợp đồng với nhiều consumer**.

### 15.1. Kỹ thuật expand → migrate → contract

Giả sử cần thêm `shipping_method`, bắt buộc khi đơn chuyển sang `SHIPPED`.

**Giai đoạn Expand**

~~~sql
ALTER TABLE orders
ADD COLUMN shipping_method TEXT;
~~~

Cột ban đầu cho phép `NULL`, để ứng dụng cũ vẫn có thể ghi. Reader mới phải chịu được NULL, writer mới ghi trường khi có thông tin. Chưa nên siết `NOT NULL` nếu dữ liệu lịch sử/ứng dụng cũ chưa đáp ứng.

**Giai đoạn Migrate**

1. Phát hành ứng dụng có thể **đọc cả record cũ và mới**.
2. Chuyển các writer sang quy tắc mới, có đo lường lỗi.
3. Backfill dữ liệu cũ **chỉ khi có nguồn thông tin đáng tin cậy**, không tự điền phương thức vận chuyển giả.
4. Kiểm tra các consumer ngoài API: report, batch, export, CDC và read replica.
5. Nếu cần, bổ sung constraint phù hợp với trạng thái, ví dụ yêu cầu phương thức vận chuyển khi status là `SHIPPED`.

**Giai đoạn Contract**

Khi tất cả writer/reader đã tương thích và dữ liệu đáp ứng, siết constraint, bỏ đường ghi cũ và sau đó bỏ cột cũ không dùng. Với bảng lớn, chọn chiến lược triển khai/validation có kiểm soát nhằm tránh khóa dài hoặc giảm sẵn sàng.

### 15.2. Không phải mọi thay đổi đều tương thích

| Thay đổi | Rủi ro | Hướng giảm rủi ro |
| --- | --- | --- |
| Thêm cột nullable | Reader cũ thường bỏ qua, writer cũ vẫn chạy | Kiểm tra ORM, serializer và code dùng `SELECT *` |
| Thêm cột NOT NULL không có giá trị cho dữ liệu cũ | Writer cũ lỗi, migration khó | Expand trước rồi backfill và siết sau |
| Đổi tên/xóa cột | Consumer cũ lỗi ngay | Triển khai cột mới, chuyển consumer, bỏ cột cũ cuối cùng |
| Đổi nghĩa dữ liệu | Dữ liệu lịch sử bị diễn giải sai | Phiên bản quy tắc, backfill có nguồn, đối soát |
| Đổi type/scale/currency | Có thể mất chính xác hoặc tràn kiểu | Đo phạm vi thực, thử migration, kiểm tra round trip |
| Thêm UNIQUE | Dữ liệu cũ có thể đã trùng | Tìm và xử lý collision trước khi siết |
| Thay collation | Kết quả sort/equality/index có thể đổi | Kiểm thử khóa và query, lên kế hoạch index |

Các công cụ như Flyway/Liquibase có thể quản lý phiên bản migration, nhưng **không tự quyết định chiến lược tương thích dữ liệu và hành vi nghiệp vụ**.

### 15.3. Không thay schema trực tiếp từ startup của mọi instance

Nếu nhiều instance Java đồng thời chạy schema migration khi boot, có thể gây tranh chấp hoặc sự cố khi rollback triển khai. Cần một quy trình triển khai migration có chủ sở hữu, kiểm tra phiên bản, backup/rollback plan và trạng thái sẵn sàng theo hợp đồng.

Không nên mặc định để ORM tự “update schema” của production mà thiếu review và kiểm soát thay đổi.

## 16. Schema ở hệ document và NoSQL vẫn là hợp đồng

Một kho document có thể chấp nhận document khác cấu trúc, nhưng **schema dữ liệu vẫn tồn tại ở mức logic**:

~~~json
{
  "schemaVersion": 2,
  "orderId": "ORDER-1001",
  "customerId": "C-42",
  "status": "SUBMITTED",
  "total": {
    "amountMinor": 130000,
    "currency": "VND"
  },
  "lines": [
    {"productId": "P-1", "quantity": 2, "unitPriceMinor": 50000},
    {"productId": "P-2", "quantity": 1, "unitPriceMinor": 30000}
  ]
}
~~~

Document trên lưu một đơn và các dòng hàng cùng nhau. Tính đúng đắn vẫn cần:

- `orderId` duy nhất trong phạm vi đúng.
- `quantity > 0`, tiền và currency có ngữ nghĩa nhất quán.
- `total.amountMinor` khớp cách tính từ các dòng hàng theo chính sách được định nghĩa.
- Chuyển trạng thái có guard, quyền và kiểm soát đồng thời.
- Reader biết xử lý `schemaVersion = 1` và `2` trong thời gian migration.

Nếu một hệ cung cấp schema validation/conditional write/transaction, có thể tận dụng. Nếu không, phần lớn trách nhiệm đặt ở ứng dụng và quy trình ghi. **“Schema-less” không có nghĩa “không cần hợp đồng”**; điều đó chỉ có thể làm hợp đồng khó được thực thi tập trung hơn.

## 17. Bảo mật dữ liệu là một phần của hợp đồng

Một schema có thể đúng về kiểu và FK nhưng vẫn tạo lỗ hổng nếu ứng dụng trả về đơn của người khác.

### 17.1. Quyền theo tenant và chủ sở hữu

Trong schema minh họa, mỗi đơn gắn với một khách qua `customer_id`. Một câu đọc theo quyền sở hữu có thể giới hạn bản ghi ở ngay điều kiện truy vấn:

~~~sql
SELECT id, status, total_minor, currency_code
FROM orders
WHERE id = :orderId
  AND customer_id = :authorizedCustomerId;
~~~

Giá trị `:authorizedCustomerId` phải được suy ra từ thông tin định danh đã xác thực, không lấy tùy ý từ client. Nếu cần cách ly theo **tenant** thật sự, phải thiết kế `tenant_id`, khóa/unique key theo phạm vi tenant và điều kiện truy cập tương ứng; không giả định `customer_id` chính là tenant. Truy vấn đúng điều kiện là một lớp bảo vệ, không thay thế phân quyền ở tầng service hoặc chính sách của database.

Các lớp bảo vệ:

- Xác thực danh tính và quyền trong service.
- Ràng buộc query bằng customer/tenant ID tin cậy.
- Phân quyền database, tài khoản ứng dụng tối thiểu quyền.
- Row-level security nếu công nghệ hỗ trợ và đã kiểm chứng phạm vi áp dụng.
- Kiểm toán thao tác nhạy cảm, đặc biệt đổi trạng thái hoặc thay tiền.

### 17.2. Dữ liệu nhạy cảm và lưu giữ

Email, địa chỉ, token, số điện thoại và hồ sơ khách có thể được sao chép vào log, backup, search index hoặc analytics. Cần có quy định về mã hóa lúc truyền/lưu, quyền truy cập, retention, ẩn danh hóa/xóa và các bản sao dẫn xuất.

Không log nguyên văn toàn bộ payload hoặc thông tin bí mật chỉ để gỡ lỗi constraint. Các lỗi có thể ghi mã request, tên constraint và loại trường nếu không làm lộ dữ liệu người dùng.

## 18. Backup và restore cần phục hồi cả dữ liệu lẫn schema

Backup tạo từ một schema chỉ có giá trị khi có thể **khôi phục đúng phiên bản và ngữ nghĩa dữ liệu**.

Kiểm tra:

1. Các bản sao lưu có giữ được cấu trúc bảng, ràng buộc, index và dữ liệu cần thiết?
2. Restore ở môi trường mới có đúng encoding, timezone/locale, extension và phiên bản database tương thích?
3. Các migration sẽ chạy lại thế nào nếu bản backup thuộc phiên bản schema cũ?
4. Sau restore, các khóa ngoại, unique constraint, tổng tiền và dòng hàng có còn nhất quán?
5. RPO/RTO thực tế đo được khi diễn tập là bao nhiêu?

**Replication không thay thế backup**: một thao tác xóa nhầm hoặc migration phá dữ liệu có thể được đồng bộ sang replica. Một bản dump thành công cũng chưa chứng minh hệ thống có thể restore và chạy ứng dụng với dữ liệu đã khôi phục.

## 19. Contract tests: kiểm tra hợp đồng thay vì chỉ test mapper giả

Unit test Java có thể kiểm tra quy tắc domain, nhưng **không đủ** để chứng minh schema và driver thực sự hoạt động như mong đợi.

### 19.1. Những lớp kiểm thử cần có

| Loại kiểm thử | Ví dụ |
| --- | --- |
| **Domain unit test** | Không cho số lượng âm, không cho chuyển `DRAFT → PAID` |
| **Mapper test** | Đọc/ghi UUID, tiền, thời điểm, NULL đúng quy ước |
| **Repository integration test** | Insert rồi đọc lại trên DB thật; kiểm tra query và index |
| **Constraint test** | Chèn số lượng âm/FK sai/trùng unique và xác minh bị từ chối |
| **Concurrency test** | Hai request cùng version: chỉ một cập nhật thành công |
| **Transaction test** | Lỗi ghi dòng hàng khiến toàn transaction rollback |
| **Migration test** | Data từ schema cũ được reader mới xử lý; rollback kế hoạch hoạt động |
| **Failure/recovery test** | Timeout, restart, mất kết nối sau commit, restore bản backup |
| **Security test** | Một customer/tenant không thể đọc hoặc sửa dữ liệu của người khác |

### 19.2. Tập dữ liệu thử nghiệm cần có trường hợp biên

Không chỉ dùng một đơn hợp lệ. Hãy đưa vào:

- Đơn nháp rỗng; đơn nộp có nhiều dòng hàng.
- Dòng hàng có số lượng 0, âm hoặc vượt giới hạn.
- Hai đơn khác ID nhưng cùng mã yêu cầu chống trùng.
- Giá trị tiền rất lớn và mã currency ngoài danh sách hỗ trợ.
- Khách bị xóa/không tồn tại, dữ liệu bị soft delete.
- Tên tiếng Việt, Unicode dạng tổ hợp và timezone khác nhau.
- Nhiều request cùng cập nhật tồn kho/đơn hàng.
- Record phiên bản cũ khi đang migrate.

Khi so sánh, cần phân biệt **độ đúng nghiệp vụ** và **cách triển khai cụ thể**. Một test chỉ “có đúng 5 cột trong bảng” chưa chứng minh ứng dụng bảo vệ được bất biến chuyển trạng thái.

## 20. Dấu hiệu hợp đồng ứng dụng–kho lưu trữ đang yếu

| Dấu hiệu | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Tên trường chung chung như `value`, `data`, `amount` | Dễ diễn giải sai | Ghi rõ đơn vị, ngữ cảnh và kiểu domain |
| Không có FK/unique/check khi nghiệp vụ yêu cầu | Dữ liệu bẩn tích lũy qua nhiều đường ghi | Thiết kế constraint và backfill trước khi siết |
| API nhận nguyên entity ORM | Lộ trường nội bộ, mass assignment, N+1 | Tách DTO/domain/persistence model |
| Service kiểm tra tồn kho rồi ghi ở hai transaction khác nhau | Oversell hoặc lost update | Cập nhật có điều kiện và transaction |
| Script vận hành ghi trạng thái tùy ý | Bỏ qua domain invariant | Quy định đường ghi được phép, ràng buộc/kiểm toán |
| Không xử lý NULL hoặc timezone nhất quán | Sai báo cáo, exception khi đọc | Quy ước nullable và time semantics |
| Deploy bản mới xóa cột ngay | Instance cũ ngừng hoạt động | Expand–migrate–contract |
| Test chỉ mock repository | Không phát hiện sai lệch JDBC/schema | Integration và migration tests trên DB thật |
| Retry sau timeout không có khóa ổn định | Ghi trùng đơn/thanh toán | Idempotency và điều tra kết quả commit |
| Restore chưa từng diễn tập | Không biết khả năng phục hồi thực tế | Kiểm thử backup/restore định kỳ |

## 21. Bài tập vận dụng

### Bài tập 1: Viết hợp đồng dữ liệu cho một đơn hàng

Đề bài: Một đơn gồm ID, người mua, trạng thái, tổng tiền và nhiều dòng hàng. Người học hãy:

1. Phân biệt những trường có thể NULL với những trường bắt buộc.
2. Đề xuất khóa chính, khóa ngoại, ràng buộc unique và check.
3. Định nghĩa ngữ nghĩa tiền và thời điểm.
4. Cho biết bất biến nào không thể chỉ bảo vệ bằng `CHECK` đơn giản.

**Gợi ý:** `order_id` duy nhất; `customer_id` tham chiếu khách tồn tại; `quantity > 0`; tổng tiền và currency có hợp đồng rõ; một đơn đã nộp phải có dòng hàng và các quy tắc trạng thái cần transaction/domain logic.

### Bài tập 2: Phát hiện vấn đề NULL

Một bảng có:

~~~sql
CREATE TABLE packages (
    id UUID PRIMARY KEY,
    weight_grams INTEGER CHECK (weight_grams >= 0)
);
~~~

Câu hỏi: Có thể lưu `NULL` vào `weight_grams` không? Nếu yêu cầu “mọi kiện đã cân phải có trọng lượng không âm, kiện chưa cân được phép thiếu giá trị”, bạn sẽ mô hình hóa thế nào?

**Gợi ý:** `CHECK` không loại bỏ `NULL` theo mặc định ở PostgreSQL. Có thể giữ nullable và thêm trạng thái đo; đảm bảo trạng thái `MEASURED` có trọng lượng không NULL bằng quy tắc thích hợp.

### Bài tập 3: Hai request cùng chuyển trạng thái

Hai request đọc đơn `DRAFT` với `version = 7`. Cả hai thử chuyển thành `SUBMITTED`. Vì sao cần điều kiện `WHERE status = 'DRAFT' AND version = 7` trong câu cập nhật?

**Gợi ý:** Khi request thứ nhất cập nhật version lên 8, request thứ hai tác động 0 hàng. Điều này giúp phát hiện xung đột thay vì ghi đè trạng thái âm thầm.

### Bài tập 4: Migration không làm gián đoạn hệ thống

Phiên bản mới thêm `shipping_method` bắt buộc khi đơn đã gửi. Hãy vạch ra thứ tự:

- Thêm trường, giữ tương thích ứng dụng cũ.
- Triển khai reader/writer mới.
- Backfill dữ liệu nếu có nguồn đáng tin cậy.
- Siết ràng buộc.
- Loại đường cũ.

**Gợi ý:** Không thêm `NOT NULL` cứng ngay khi dữ liệu cũ chưa có giá trị; thay đổi theo giai đoạn và thử trên dữ liệu đại diện.

### Bài tập 5: Kiểm chứng hợp đồng repository

Viết kế hoạch kiểm thử cho `submitIfDraft(orderId, customerId, expectedVersion)`:

1. Đơn hợp lệ ở `DRAFT` và version đúng.
2. Version không khớp.
3. Khách khác gửi yêu cầu.
4. Đơn ở `PAID`.
5. Mất kết nối gần thời điểm commit.

**Gợi ý:** Kiểm tra số hàng cập nhật, tính bất biến trạng thái, không tiết lộ đơn của khách khác, và cách xử lý kết quả ghi không rõ.

## 22. Checklist thiết kế schema và hợp đồng persistence

- [ ] Đã phân biệt domain model, API DTO và persistence model ở mức cần thiết.
- [ ] Các trường có kiểu, đơn vị, múi giờ, scale/precision và ý nghĩa được ghi rõ.
- [ ] Có primary key, business key, FK, UNIQUE, NOT NULL và CHECK thích hợp.
- [ ] Hiểu rõ ngữ nghĩa NULL, mặc định và phạm vi dữ liệu thiếu.
- [ ] Đã xác định bất biến nào bảo vệ ở DB, domain/service và transaction.
- [ ] Đã mô tả trạng thái nghiệp vụ, điều kiện chuyển và kiểm soát concurrent update.
- [ ] Repository contract nói rõ lúc nào ghi được coi là thành công và lỗi được phân loại thế nào.
- [ ] Query/index đáp ứng các mẫu đọc thật, không tạo index tùy tiện.
- [ ] Phạm vi truy cập tenant/customer được bảo vệ và kiểm chứng.
- [ ] Đã thiết kế idempotency, retry và xử lý commit không rõ kết quả.
- [ ] Có chiến lược schema migration tương thích với phiên bản ứng dụng cũ.
- [ ] Backup và restore được thử cùng schema, dữ liệu tham chiếu và quyền truy cập.
- [ ] Integration/contract tests chạy trên kho dữ liệu đại diện, gồm cả lỗi, cạnh tranh và migration.

## 23. Ghi nhớ

**Lược đồ dữ liệu là một phần của hợp đồng giữa ứng dụng và kho lưu trữ**, không chỉ là danh sách tên bảng hay cấu trúc JSON. Hợp đồng cần bảo vệ **ý nghĩa**, **tính hợp lệ**, **quan hệ**, **cách truy cập**, **điểm xác nhận ghi** và **khả năng tiến hóa** của dữ liệu.

Trong ứng dụng Java, domain quyết định những thay đổi nào hợp lệ, repository ánh xạ yêu cầu thành thao tác lưu trữ, còn database bảo vệ những ràng buộc có thể và nên được thực thi tại nguồn sự thật. Giao dịch, kiểm soát đồng thời và kiểm thử thực tế nối các lớp này thành một hệ thống đáng tin cậy. **Schema tốt là schema mà những bản phát hành tương lai vẫn có thể hiểu, mở rộng và khôi phục dữ liệu đã ghi hôm nay mà không phá vỡ các bất biến nghiệp vụ.**
