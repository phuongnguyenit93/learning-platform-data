# Phân biệt đổi tên, đổi cấu trúc và đổi ý nghĩa dữ liệu

## 1. Vì sao ba kiểu thay đổi nhìn giống nhau nhưng rủi ro rất khác nhau?

Một yêu cầu “đổi cột `customer_name` thành `display_name`” có thể là thay đổi tên thuần túy. Một yêu cầu “tách cột `phone` ra bảng liên hệ” là thay đổi cấu trúc và có thể thay đổi quan hệ từ một-một thành một-nhiều. Một yêu cầu “`PAID` từ nay chỉ có nghĩa tiền đã được nhà thanh toán xác nhận” là thay đổi **ý nghĩa nghiệp vụ**, dù tên cột và kiểu dữ liệu không đổi.

Trong mô hình dữ liệu, **không thể đánh giá độ an toàn của migration chỉ bằng cách nhìn DDL**. Hai lệnh `ALTER TABLE` giống nhau có thể có ảnh hưởng hoàn toàn khác nếu ràng buộc và hợp đồng dữ liệu khác nhau; ngược lại, một thay đổi ngữ nghĩa có thể không đụng đến lược đồ vật lý nhưng làm sai báo cáo tài chính.

Ví dụ nền tảng bán hàng có:

- `Customer`: `customer_id`, `customer_name`, `phone_e164`, `segment`.
- `Order`: `order_id`, `customer_id`, `amount_minor`, `status`.
- `Payment`: `payment_attempt_id`, kết quả xác nhận với nhà cung cấp.

Đội phát triển nhận ba yêu cầu:

1. “Đổi tên `customer_name` thành `display_name`, vẫn là tên dùng để hiển thị.”
2. “Một khách có thể có nhiều số điện thoại; đưa số điện thoại sang bảng liên hệ.”
3. “Từ nay `status = PAID` chỉ được ghi khi payment provider xác nhận capture, thay vì lúc gửi yêu cầu thu.”

Ba yêu cầu cần ba chiến lược khác nhau:

| Phân loại chính | Thứ thay đổi | Có nhất thiết thay schema vật lý? | Rủi ro chính |
| --- | --- | --- | --- |
| **Đổi tên (rename)** | Cách gọi một khái niệm giữ nguyên ý nghĩa. | Không nhất thiết: có thể chỉ đổi nhãn API/semantic layer. | Phá consumer, view, query, mapping, serialization. |
| **Đổi cấu trúc (structural change)** | Cách chia bảng/document, quan hệ, cardinality, khóa, kiểu và vị trí dữ liệu. | Thường có. | Mất hoặc nhân hàng, phá FK/unique, backfill thiếu thông tin, thay grain. |
| **Đổi ý nghĩa (semantic change)** | Điều giá trị/sự kiện/trạng thái khẳng định về nghiệp vụ. | Không nhất thiết. | Dữ liệu cũ và mới bị diễn giải như cùng nghĩa, dẫn tới quyết định/KPI sai. |

**Một thay đổi có thể thuộc nhiều nhóm.** Đổi `amount_minor` thành `net_amount_minor` có bề ngoài là rename, nhưng nếu `amount_minor` trước đây là số tiền *trước* hoàn còn `net_amount_minor` là số tiền *sau* hoàn, đó là **đổi ý nghĩa** và có thể đòi **đổi cấu trúc** để bổ sung từng giao dịch refund.

Bài này tập trung cách phân loại, thiết kế lược đồ và triển khai tiến hóa có thể kiểm chứng trong database quan hệ, đồng thời so sánh với document, graph và mô hình phân tích.

## 2. Cần phân biệt ba lớp: tên, biểu diễn và hợp đồng ngữ nghĩa

Mỗi trường dữ liệu nên được xem qua ít nhất ba lớp:

1. **Tên và ngôn ngữ:** `display_name`, `customer_name`, “Tên hiển thị” trên giao diện; gồm tên logic, tên vật lý và tên trong hợp đồng API/event.
2. **Biểu diễn:** cột `TEXT` hay thuộc tính JSON, bảng riêng hay embedded document, một hàng hay nhiều hàng, khóa/FK, đơn vị lưu.
3. **Ngữ nghĩa:** tên này thuộc chủ thể nào, còn đúng tại thời điểm nào, ai có thẩm quyền xác nhận, giá trị thiếu có nghĩa gì, ràng buộc nào phải đúng.

Ví dụ giá bán có các trường tưởng giống nhau:

| Tên | Định nghĩa có thể có | Chủ sở hữu |
| --- | --- | --- |
| `current_list_price_minor` | Giá niêm yết hiện hành của Catalog. | Catalog. |
| `agreed_unit_price_minor` | Đơn giá đã chốt tại thời điểm đặt hàng. | Ordering. |
| `captured_amount_minor` | Số tiền nhà cung cấp đã xác nhận thu. | Payment. |
| `refunded_amount_minor` | Số tiền đã được xác nhận hoàn. | Payment. |
| `net_cash_minor` | Tổng capture trừ tổng refund trong phạm vi/thời điểm định nghĩa. | Finance/Analytics dựa trên Payment. |

Cả năm có thể dùng `BIGINT` và đơn vị nhỏ nhất của tiền tệ, nhưng **không phải năm tên của một trường**. Đổi tên một trường mà kéo theo đổi chủ sở hữu, nguồn sự thật hoặc cách tính không còn là rename thuần.

Một **data contract** tốt phải gồm: định danh, grain, kiểu và đơn vị, phạm vi khóa, nullability, enum, thời gian hiệu lực, giá trị mặc định, chủ sở hữu, quy tắc cập nhật, bảo mật/retention và ý nghĩa cho consumer.

## 3. Đổi tên thuần túy: điều kiện để khẳng định “không đổi nghĩa”

Rename thuần chỉ hợp lệ khi **tất cả bất biến và ý nghĩa của dữ liệu giữ nguyên**:

- Cùng thực thể, cùng phạm vi business key và tenant.
- Cùng grain: một hàng vẫn đại diện cho cùng một sự việc/đối tượng.
- Cùng kiểu giá trị và đơn vị, không đổi cách chuẩn hóa hoặc làm tròn.
- Cùng cách diễn giải `NULL`, giá trị rỗng, enum và mặc định.
- Cùng nguồn có thẩm quyền và thời điểm xác nhận.
- Cùng vòng đời và ý nghĩa lịch sử.

Ví dụ sửa tên `customer_name` thành `display_name` nếu hai tên đều chỉ *tên hiển thị do Customer Identity sở hữu* thì có thể là rename. Nhưng nếu `customer_name` trước đây là **tên pháp lý trên hóa đơn**, còn `display_name` là **biệt danh người dùng có thể sửa tùy ý**, phép đổi này **không thuần túy**: cần tách hai khái niệm, quyền sửa và hợp đồng sử dụng.

### Tên hiển thị, tên API và tên cột có thể khác

Không bắt buộc phải đổi mọi tầng đồng thời. Một mô hình có thể dùng:

~~~text
Database column: customer_name
Domain property: displayName
REST API field: display_name
UI label: Tên hiển thị
~~~

Nếu cùng nghĩa và mapping được tài liệu hóa, khác tên không phải lỗi. Đổi tên **trong code hoặc giao diện** có thể không cần DDL. Đổi tên cột vật lý có thể giảm nợ kỹ thuật nhưng tạo rủi ro cho SQL consumers, stored procedures, exports, materialized views, CDC và ORM mapping.

### Phép đổi tên nguy hiểm dù dữ liệu không biến đổi

~~~sql
ALTER TABLE customer_account
RENAME COLUMN customer_name TO display_name;
~~~

PostgreSQL thực hiện thay đổi metadata của cột mà không cần copy toàn bộ giá trị sang cột mới, **nhưng không vì thế là không gián đoạn**. DDL cần khóa phù hợp và có thể chờ hoặc chặn các truy vấn khác; ứng dụng, SQL text và consumer phụ thuộc tên cột cũ có thể hỏng khi deploy.

Một số dependency do database quản lý có thể được cập nhật theo catalog, nhưng **SQL văn bản trong ứng dụng, query được lưu ở nơi khác và message contract không tự đổi**. Do đó với hệ có nhiều phiên bản ứng dụng chạy đồng thời, `RENAME COLUMN` trực tiếp thường không phải chiến lược tương thích an toàn nhất.

## 4. Đổi cấu trúc: thay cách dữ liệu được biểu diễn và liên kết

Đổi cấu trúc không chỉ là đổi kiểu dữ liệu; nó có thể thay **số hàng, ranh giới bảng, quan hệ và ràng buộc**.

| Thay đổi cấu trúc | Ví dụ | Câu hỏi phải trả lời |
| --- | --- | --- |
| **Tách cột thành nhiều cột** | `full_address` → `street`, `ward`, `city`. | Có thể tách chính xác toàn bộ dữ liệu cũ không? |
| **Gộp cột** | `first_name` + `last_name` → `display_name`. | Thứ tự tên, văn hóa, giá trị thiếu và dấu cách được xử lý thế nào? |
| **Tách bảng** | `customer.phone` → `customer_contact_method`. | Cardinality đổi từ một số sang nhiều số; khóa/unique mới ra sao? |
| **Gộp bảng** | `order_header` + `order_detail` → document. | Grain của hàng/document là gì, có mất khả năng query chi tiết không? |
| **Đổi kiểu** | `VARCHAR` → enum/UUID, `INT` → `BIGINT`. | Dữ liệu hiện có có chuyển đổi an toàn, đúng phạm vi không? |
| **Đổi khóa** | `customer_email` làm PK → surrogate `customer_id`. | FK, reference ngoài, duplicate và vòng đời email được xử lý thế nào? |
| **Đổi cardinality** | Một order có một coupon → nhiều coupon. | Unique cũ còn đúng? Có cần bảng liên kết nhiều-nhiều? |
| **Chuẩn hóa/phi chuẩn hóa** | `order.customer_name` tách thành dimension. | Tên đã chốt của đơn có còn cần giữ không? |
| **Đổi phân vùng/chỉ mục** | Chia `orders` theo tháng. | Unique xuyên partition, routing key và query pruning ra sao? |
| **Đổi nơi sở hữu** | `payment_status` từ Ordering sang Payment. | Đây còn là thay đổi cấu trúc, hay đổi cả nguồn và ý nghĩa? |

Đổi cấu trúc **không nhất thiết đổi nghĩa** nếu dữ liệu mới chỉ là biểu diễn tương đương và mapping là không mất mát theo yêu cầu. Nhưng thực tế nhiều migration gặp dữ liệu thiếu, khóa không ổn định, quy tắc cũ mơ hồ hoặc thay đổi cardinality khiến mapping **không thể tự động**.

### Lossless và lossy mapping

Giả sử `full_name = "Nguyễn Văn An"`. Không thể chắc chắn tách thành `first_name = An` và `last_name = Nguyễn Văn` theo mọi văn hóa và mọi dữ liệu. Nếu cần giữ tên gốc, lưu `full_name` nguyên vẹn hoặc các thành phần chỉ khi có nguồn xác nhận.

Tương tự, từ một cột `phone` không thể tự suy khách có bao nhiêu số điện thoại khác trong lịch sử. Migration sang bảng nhiều liên hệ chỉ có thể tạo **một bản liên hệ được biết từ nguồn cũ**, không tái tạo các liên hệ chưa từng lưu.

**Quy tắc:** với một structural migration, phải định nghĩa ánh xạ dữ liệu cũ → mới, ranh giới thông tin có thể khôi phục và phép kiểm tra bảo toàn trước khi xóa cấu trúc cũ.

## 5. Đổi ý nghĩa: nguy hiểm vì schema vẫn có thể hoàn toàn hợp lệ

Đổi ngữ nghĩa xảy ra khi cách hiểu giá trị **trước và sau thay đổi không còn tương đương**.

Ví dụ `order_status = 'PAID'`:

- **Quy tắc cũ:** gán `PAID` khi ứng dụng gửi lệnh thu tiền và nhận phản hồi “đã tiếp nhận”.
- **Quy tắc mới:** chỉ gán `PAID` sau khi provider xác nhận capture thành công.

Hai giá trị có **cùng chuỗi**, nhưng một giá trị mô tả *yêu cầu đã được nhận* và một giá trị mô tả *tiền đã được thu*. Nếu dashboard tính doanh thu bằng `COUNT(status = 'PAID')` trên dữ liệu nhiều thời kỳ, kết quả có thể sai dù query vẫn chạy.

Các thay đổi ngữ nghĩa khác:

| Giá trị/trường | Cách hiểu cũ | Cách hiểu mới | Vì sao không chỉ là rename? |
| --- | --- | --- | --- |
| `amount` | Số tiền trước chiết khấu. | Số tiền sau chiết khấu. | Công thức và nguồn bằng chứng khác nhau. |
| `amount_minor` | Đơn vị nhỏ nhất của VND. | Đơn vị lớn của VND. | Thay đơn vị làm phép tính sai, dù kiểu số vẫn hợp lệ. |
| `active` | Đối tượng chưa bị xóa mềm. | Đối tượng còn được phép giao dịch. | Trạng thái hiển thị khác quyền nghiệp vụ. |
| `order_date` | Lúc hệ thống tạo đơn. | Lúc khách xác nhận mua. | Nhóm báo cáo theo ngày sẽ thay đổi. |
| `customer_id` | Tài khoản đăng nhập. | Người mua pháp lý/hợp nhất danh tính. | Đối tượng và khóa tham chiếu khác. |
| `gross_revenue` | Giá trị đơn đã đặt. | Giá trị hóa đơn được ghi nhận. | Khác điểm chốt kế toán và xử lý hủy/hoàn. |
| `delivery_done` | Tài xế nhấn “đã giao”. | Người nhận xác nhận giao thành công. | Cần bằng chứng khác nhau. |
| `quantity` | Số đơn vị sản phẩm đặt. | Số đơn vị đã giao. | Không phản ánh cùng trạng thái nghiệp vụ. |

**Semantic compatibility** là một vấn đề riêng với **schema compatibility**. Hai phiên bản JSON có cùng tên và kiểu trường có thể *vẫn không tương thích* về ý nghĩa.

### Không đổi nghĩa của dữ liệu cũ bằng phép gán mặc định

Nếu bản ghi cũ thiếu bằng chứng provider capture, không được biến `PAID` cũ thành `PaymentCaptured` mới chỉ bằng:

~~~sql
-- KHÔNG làm thế nếu lịch sử PAID chỉ có nghĩa đã yêu cầu thu.
UPDATE orders
SET payment_state = 'CAPTURED'
WHERE status = 'PAID';
~~~

Một kế hoạch đúng phải xác định có thể truy hồi **provider confirmation ID**, giao dịch nào được đối soát, giao dịch nào chưa biết và cách công bố giới hạn số liệu. Nếu không có đủ chứng cứ, nên giữ trạng thái **LEGACY_REQUEST_ACCEPTED** hoặc **UNKNOWN_CAPTURE_RESULT**, tùy hợp đồng đã thống nhất, chứ không bịa ra kết quả tài chính.

## 6. Một thay đổi có thể thuộc cả ba loại

Các loại thay đổi không loại trừ nhau. Hãy phân tách từng lớp để không bỏ sót rủi ro.

Ví dụ yêu cầu “thay `order.total` bằng `payment_summary.net_cash_minor`”:

1. **Đổi tên:** `total` → `net_cash_minor`.
2. **Đổi cấu trúc:** một cột trên `orders` thành summary từ nhiều dòng `payment_movement` theo `CAPTURE`/`REFUND`.
3. **Đổi ngữ nghĩa:** “giá trị đơn hàng” trở thành “tiền đã thu ròng” tại mốc đối soát.

Ba phép biến đổi không thể triển khai an toàn bằng một `RENAME COLUMN`, vì không có quan hệ một-một giữa tổng đơn và cashflow: một order có thể bị hủy, thu nhiều lần, hoàn một phần hoặc có giao dịch chưa được provider xác nhận.

### Bảng phân loại nhanh

| Câu hỏi kiểm tra | Nếu câu trả lời là Có | Phân loại cần xem xét |
| --- | --- | --- |
| Có chỉ đổi nhãn, cùng định nghĩa và grain? | Có. | Rename. |
| Có chuyển dữ liệu giữa bảng/document hay thêm quan hệ? | Có. | Structural. |
| Có đổi khóa, cardinality, đơn vị hoặc kiểu? | Có. | Structural; **có thể cả semantic**. |
| Cùng giá trị cũ nhưng giờ khẳng định điều khác? | Có. | Semantic. |
| Có đổi “ai được quyền quyết định/ghi giá trị”? | Có. | Semantic/ownership boundary. |
| Có đổi thời điểm sự việc được coi đã xảy ra? | Có. | Semantic/temporal. |
| Báo cáo lịch sử có thể đổi mà fact gốc không thay? | Có. | Có thể là semantic restatement hoặc SCD policy. |
| Có dữ liệu cũ không ánh xạ chính xác sang đích? | Có. | Structural migration mất thông tin / semantic ambiguity. |

Khi kết luận “rename thuần”, hãy viết ra **bằng chứng không đổi nghĩa**, không chỉ nói “team bảo giống nhau”.

## 7. Grain, business key và bất biến quyết định khả năng tiến hóa

**Grain** trả lời một hàng đại diện cho điều gì. **Business key** trả lời làm sao nhận diện thực thể/sự việc đó trong phạm vi nghiệp vụ. **Invariant** trả lời điều gì phải luôn đúng.

Ba yếu tố này quan trọng hơn tên bảng.

### Đổi tên khóa hay đổi danh tính?

Giả sử trước đây `user_id` là ID tài khoản, còn yêu cầu mới dùng `customer_id`. Nếu một khách có nhiều tài khoản thì `user_id` và `customer_id` không tương đương. Rename khóa sẽ gộp sai thực thể hoặc làm sai quan hệ:

~~~text
UserAccount U-101 ----+
                      +---- Customer C-42
UserAccount U-202 ----+
~~~

Có thể cần bảng mapping `customer_account_membership` với thời gian hiệu lực, nguồn chứng minh và unique constraints. Không thể đổi cột `user_id` thành `customer_id` rồi giữ nguyên mọi giá trị như thể mỗi tài khoản là một khách.

### Đổi cardinality là đổi cấu trúc và có thể đổi luật

Một khách có nhiều số điện thoại. Trước đây:

~~~text
customer_account(customer_id, phone_e164)
~~~

Sau đó:

~~~text
customer_account(customer_id)
customer_contact_method(contact_id, customer_id, contact_type, value, ...)
~~~

Các câu hỏi cần làm rõ: tối đa bao nhiêu số? Có một số **primary** hay nhiều primary theo mục đích? Một số có thể được dùng cho hai khách? Số đã xác minh khác số do khách nhập? Được phép xóa/khôi phục theo chính sách nào?

Nếu không xác định bất biến, dữ liệu mới có thể hợp lệ về FK nhưng gây sai luồng gửi mã xác thực hoặc lộ thông tin liên hệ.

### Không phá grain của fact

Bảng `fact_order_line` có grain “một dòng hàng của một đơn”; bảng `fact_payment_movement` có grain “một giao dịch thu/hoàn đã được xác nhận”. Gộp hai bảng trực tiếp theo `order_id` có thể nhân hàng khi một đơn có ba dòng và hai lần thanh toán. Migration cấu trúc sang một bảng “đơn hàng tổng hợp” phải định nghĩa grain mới và phép tổng hợp, không tự JOIN rồi SUM.

## 8. Ví dụ xuyên suốt: cùng một Customer, ba loại thay đổi

Giả sử schema v1 (rút gọn) của một module Customer Identity:

~~~sql
CREATE TABLE customer_account (
    tenant_id       UUID NOT NULL,
    customer_id     UUID NOT NULL,
    customer_name   TEXT NOT NULL,
    phone_e164      TEXT,
    account_status  VARCHAR(20) NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, customer_id)
);
~~~

Ba yêu cầu:

**R1 — Đổi tên:** `customer_name` → `display_name`, giữ nguyên “tên hiển thị của tài khoản”, không phải tên trên chứng từ. Có thể dùng kỹ thuật tương thích expand–contract.

**R2 — Đổi cấu trúc:** `phone_e164` → bảng `customer_contact_method` để có nhiều số. Bản số cũ tạo được tối đa một contact đã biết. Không mặc định nó đã được xác minh.

**R3 — Đổi ý nghĩa:** nghiệp vụ muốn `account_status = 'ACTIVE'` chỉ khi **đã xác minh danh tính và được phép giao dịch**, trong khi dữ liệu cũ dùng `ACTIVE` nghĩa “chưa đóng tài khoản”. Trạng thái mới phải dựa trên bằng chứng xác minh, không chỉ đổi enum.

Ba yêu cầu có thể đi cùng một release ở cấp sản phẩm, nhưng **nên có kế hoạch migration và kiểm chứng riêng**. Nếu gộp mọi thứ vào một script, lỗi backfill số điện thoại có thể che lấp lỗi thay nghĩa trạng thái.

## 9. Quy trình Expand–Migrate–Contract cho rename tương thích

**Expand–Migrate–Contract** (còn gọi expand/contract) là lộ trình giúp hai phiên bản ứng dụng có thể cùng hoạt động trong giai đoạn chuyển đổi.

~~~mermaid
flowchart LR
    A["v1: customer_name"] --> B["EXPAND: thêm display_name, reader hỗ trợ 2 tên"]
    B --> C["MIGRATE: backfill, một đường ghi có thẩm quyền cập nhật cả hai"]
    C --> D["CUTOVER: reader dùng display_name, kiểm chứng"]
    D --> E["CONTRACT: gỡ code cũ, bỏ customer_name sau khi hết phụ thuộc"]
~~~

### Pha A — Expand: thêm trường mới, chưa bỏ trường cũ

~~~sql
ALTER TABLE customer_account
ADD COLUMN display_name TEXT;
~~~

Ở pha đầu, `display_name` **nullable** để hàng cũ không bị giả định đã có dữ liệu mới. Chỉ tạo cột không chứng minh ứng dụng đã chuyển đổi; cần thay code/mapper, API và kiểm thử tương thích.

### Pha B — Migrating reads/writes

Trong giai đoạn tồn tại hai cột, ứng dụng mới có thể đọc:

~~~sql
SELECT tenant_id, customer_id,
       COALESCE(display_name, customer_name) AS display_name
FROM customer_account
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;
~~~

`COALESCE` chỉ hợp lệ ở đây vì **hai trường đã được xác nhận cùng nghĩa** và chuỗi NULL biểu diễn “chưa được chuyển”. Nếu giá trị rỗng có nghĩa nghiệp vụ riêng, phải có chính sách xử lý, không tự coi rỗng bằng NULL.

Một **đường ghi có thẩm quyền** tạm thời cập nhật hai cột trong **cùng transaction/hàng**:

~~~sql
UPDATE customer_account
SET customer_name = :new_display_name,
    display_name  = :new_display_name,
    updated_at    = now()
WHERE tenant_id   = :tenant_id
  AND customer_id = :customer_id;
~~~

Đây là **dual-column write trong cùng transaction**, khác với **dual-write hai cơ sở dữ liệu độc lập**. Phải kiểm tra mọi write path cũ: nếu service v1 tiếp tục chỉ ghi `customer_name` trong khi v2 chỉ ghi `display_name`, hai cột có thể lệch. Các lựa chọn gồm giữ một writer/migration facade, tương thích cả phiên bản cũ hoặc cơ chế đồng bộ chuyển tiếp có kiểm thử.

### Pha C — Backfill dữ liệu hiện có

~~~sql
-- Minh họa logic cập nhật; với bảng lớn cần chia lô/giới hạn lock.
UPDATE customer_account
SET display_name = customer_name
WHERE display_name IS NULL;
~~~

Trong môi trường đang có ghi đồng thời, phải định nghĩa thứ tự triển khai và cơ chế chống một job dùng snapshot cũ để ghi đè thay đổi mới. Nên bật dual-column write **trước** backfill hoặc dùng change capture/cutover có bảo đảm. Với hàng triệu hàng, chạy UPDATE một lần có thể tạo WAL, bloat, lock wait và replica lag lớn; cần batch với checkpoint và giới hạn tải.

### Pha D — Kiểm chứng, tăng ràng buộc

Kiểm tra các hàng còn thiếu/sai:

~~~sql
SELECT COUNT(*) AS mismatched_rows
FROM customer_account
WHERE display_name IS DISTINCT FROM customer_name;
~~~

Trong giai đoạn cả hai phải đồng nhất, kết quả mong đợi là 0 ở **cùng một snapshot nhất quán**. Nếu thấy khác nhau, cần phân loại write path lỗi, dữ liệu không đạt hợp đồng hoặc backfill chưa hoàn tất.

Sau khi dữ liệu đã đầy đủ và mọi writer đảm bảo cột mới không NULL, có thể tăng constraint:

~~~sql
ALTER TABLE customer_account
ADD CONSTRAINT customer_display_name_present
CHECK (display_name IS NOT NULL) NOT VALID;

ALTER TABLE customer_account
VALIDATE CONSTRAINT customer_display_name_present;
~~~

`NOT VALID` với CHECK cho phép thêm ràng buộc mà chưa quét toàn bộ hàng hiện có, nhưng **các ghi mới/vừa cập nhật vẫn phải thỏa ràng buộc**. Cần deploy writer tương thích trước, rồi kiểm chứng ràng buộc và cân nhắc `SET NOT NULL` theo khả năng phiên bản PostgreSQL, lock và kế hoạch migration.

### Pha E — Contract: bỏ trường cũ khi không còn consumer

Chỉ sau khi mọi reader/writer, job, query, export, API và CDC consumer không còn phụ thuộc, mới cân nhắc:

~~~sql
ALTER TABLE customer_account
DROP COLUMN customer_name;
~~~

Việc bỏ cột là **khó đảo ngược** nếu chưa có backup/dữ liệu nguồn để khôi phục, kể cả dữ liệu từng nằm trong hai cột. Cần điểm cutover, kiểm chứng, kế hoạch rollback và thời gian quan sát trước khi dọn sạch.

**Không cần giữ hai cột vĩnh viễn:** giai đoạn tương thích là một bước có thời hạn rõ. Giữ lâu mà không xác định cột chuẩn sẽ tạo hai nguồn dữ liệu có khả năng diverge.

## 10. Ví dụ đổi cấu trúc: từ số điện thoại trên Customer sang bảng Contact

Yêu cầu mới là mỗi khách có thể dùng **nhiều phương thức liên hệ**. Đây là thay đổi cardinality và ràng buộc; không thể giải quyết bằng rename `phone_e164` → `contact_value`.

### Lược đồ đích

~~~sql
CREATE TABLE customer_contact_method (
    contact_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    customer_id      UUID NOT NULL,
    contact_type     VARCHAR(20) NOT NULL,
    contact_value    TEXT NOT NULL,
    is_primary       BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at      TIMESTAMPTZ,
    revoked_at       TIMESTAMPTZ,
    origin           VARCHAR(30) NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customer_account (tenant_id, customer_id),
    CHECK (contact_type IN ('PHONE', 'EMAIL')),
    CHECK (btrim(contact_value) <> ''),
    UNIQUE (tenant_id, customer_id, contact_type, contact_value)
);

-- Tối đa một số điện thoại primary còn hiệu lực cho mỗi khách.
CREATE UNIQUE INDEX ux_one_live_primary_phone
ON customer_contact_method (tenant_id, customer_id)
WHERE contact_type = 'PHONE'
  AND is_primary = TRUE
  AND revoked_at IS NULL;
~~~

**Giới hạn của lược đồ minh họa:**

- `contact_value` trong bảng nhiều loại cần validator/chuẩn hóa riêng cho PHONE và EMAIL. Chỉ `CHECK(btrim(...) <> '')` không chứng minh số điện thoại đúng định dạng hoặc email có thể nhận được.
- `verified_at` chỉ được điền khi có bằng chứng xác minh. Dữ liệu nhập từ cột cũ không được tự đánh dấu là đã xác minh.
- `is_primary` và `revoked_at` được dùng để ràng buộc **tối đa một** số chính còn hoạt động. Không có ràng buộc nào ở ví dụ bắt buộc **phải có ít nhất một** số chính; nếu nghiệp vụ yêu cầu, cần logic transaction/constraint phù hợp.
- Khóa duy nhất trên `(tenant_id, customer_id, contact_type, contact_value)` không cho phép hai record cùng value cho một khách dù một record đã revoked; đây là một **lựa chọn vòng đời**. Nếu muốn tái đăng ký cùng số và lưu nhiều lần xác minh, cần thiết kế history/grain khác.
- Một số điện thoại có thể thuộc nhiều khách hay không là quyết định nghiệp vụ; schema này không áp đặt unique toàn hệ thống.

### Backfill từ dữ liệu cũ

Giả sử `phone_e164` ở source đã được xác minh định dạng hoặc đã qua bước làm sạch. Không có chứng cứ xác minh quyền sở hữu số điện thoại, vì vậy `verified_at` phải là NULL.

~~~sql
INSERT INTO customer_contact_method (
    tenant_id, customer_id, contact_type, contact_value,
    is_primary, verified_at, origin
)
SELECT tenant_id, customer_id, 'PHONE', phone_e164,
       TRUE, NULL, 'LEGACY_IMPORT'
FROM customer_account
WHERE phone_e164 IS NOT NULL
  AND btrim(phone_e164) <> ''
ON CONFLICT (tenant_id, customer_id, contact_type, contact_value)
DO NOTHING;
~~~

Đoạn backfill **giả định** dữ liệu nguồn có thể dùng làm số liên hệ tạm và chỉ có một writer chuyển đổi. Nếu đã có một primary PHONE khác được tạo trước, unique index có điều kiện có thể làm transaction lỗi; **không** nên tự bỏ ràng buộc. Cần điều phối thứ tự, khóa theo Customer hoặc đưa conflict vào luồng đối soát.

Nếu số nguồn không đạt E.164, phải **cách ly/giữ giá trị gốc có giới hạn quyền** và chuẩn hóa theo dữ kiện đáng tin, không tự tạo số hợp lệ giả. Nếu nguồn chỉ có một số, không thể dựng ra lịch sử nhiều số điện thoại của cùng khách.

### So sánh cardinality và kiểm chứng

- Trước migration: `customer_account` có 0 hoặc 1 `phone_e164` trên mỗi khách.
- Sau migration: `customer_contact_method` có 0..N phương thức liên hệ trên mỗi khách.
- Trong thời gian chuyển: một bản legacy phone có thể sinh ra **tối đa một** contact PHONE nguồn legacy theo business key.
- Một truy vấn JOIN Customer → Contacts nay có thể trả nhiều hàng cho cùng Customer; báo cáo `COUNT(customers)` hoặc JOIN Order có thể bị nhân số dòng.

~~~sql
-- Đếm số khách có điện thoại legacy nhưng chưa tìm được contact tương ứng.
SELECT COUNT(*) AS missing_legacy_contacts
FROM customer_account c
WHERE c.phone_e164 IS NOT NULL
  AND btrim(c.phone_e164) <> ''
  AND NOT EXISTS (
      SELECT 1
      FROM customer_contact_method m
      WHERE m.tenant_id = c.tenant_id
        AND m.customer_id = c.customer_id
        AND m.contact_type = 'PHONE'
        AND m.contact_value = c.phone_e164
  );
~~~

Kết quả cần về 0 **sau khi backfill hoàn tất và tại cùng mốc dữ liệu**. Điều này không chứng minh số đã được xác minh hoặc mọi contact hiện hành có thể đồng bộ ngược thành một cột; đó là giới hạn mới của quan hệ 1:N.

### Chiến lược chuyển đường ghi

Khi bảng Contact thành nguồn sự thật cho nhiều số, không nên tiếp tục cho các ứng dụng tùy ý sửa `customer_account.phone_e164`. Trong giai đoạn tương thích, nếu phải cung cấp “số chính” cho consumer cũ, hãy xem đó là **projection** tính từ Contact với một chính sách duy nhất; không coi cả hai bảng là master độc lập.

Với mô hình contact mới, xóa mềm hoặc thu hồi một số phải có ý nghĩa nghiệp vụ, quyền hạn, thời gian và thông báo downstream. Chỉ cập nhật bảng cũ bằng số nhận cuối cùng không đủ để quản lý nhiều số và trạng thái xác minh.

## 11. Đổi ý nghĩa trạng thái: viết lại mô hình miền trước khi sửa cột

Quay lại yêu cầu `account_status = ACTIVE`. Quy tắc cũ “chưa đóng” không đồng nghĩa quy tắc mới “đã xác minh và được phép giao dịch”.

Một thiết kế rõ hơn có thể tách hai chiều:

| Trường | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| `lifecycle_status` | `OPEN`, `CLOSED` | Tài khoản còn trong vòng đời hoạt động hay đã đóng. |
| `verification_status` | `UNVERIFIED`, `VERIFIED`, `REJECTED` | Bằng chứng xác minh theo quy trình được phê duyệt. |
| `access_status` | `ENABLED`, `SUSPENDED` | Hiện được phép sử dụng chức năng theo chính sách hay bị khóa. |
| `eligible_for_purchase` (dẫn xuất) | true/false | Quy tắc tổng hợp từ lifecycle, verification, access và điều kiện khác. |

Mô hình mới có thể cần nhiều cột/bảng (structural) vì **một enum cũ đã gộp nhiều chiều nghĩa**. Nhưng quan trọng nhất là **ngữ nghĩa của từng giá trị và điểm quyết định**.

### Không bịa verification status cho lịch sử

Nếu khách cũ chỉ có `account_status = 'ACTIVE'`, không thể chuyển tất cả sang `verification_status = 'VERIFIED'`. Cần:

1. Kiểm kê nguồn xác minh trước đây (hồ sơ, provider, audit có thẩm quyền), nếu có.
2. Phân loại khách có thể chứng minh `VERIFIED`, `UNVERIFIED`, `REJECTED`.
3. Nếu không có bằng chứng, dùng `UNKNOWN_LEGACY` hoặc trạng thái chưa xác định theo chính sách, không tự điền “đã xác minh”.
4. Quy định rõ hành vi với tài khoản chưa biết: cho xem dữ liệu? yêu cầu xác minh lại trước khi mua? chặn tác vụ nhạy cảm?
5. Ghi lại migration rule version và mốc có hiệu lực; người dùng cần hiểu sự khác nhau giữa **đã được xác minh** và **đã tồn tại từ thời cũ**.

### State transition mới không được tự sửa lịch sử

Đối với order, `PAID` chỉ khi capture được provider xác nhận là một quy tắc state transition mới. Dữ liệu lịch sử từ hệ cũ cần đối soát hoặc giữ phân loại legacy. Nếu nguồn xác nhận capture đến trễ, cần xử lý timestamp và lịch sử trạng thái phù hợp; không đổi `created_at` của đơn thành giờ callback.

Đổi nghĩa một field có thể đòi **domain event mới**, migration dữ liệu và version của read model, chứ không chỉ chỉnh validation enum.

## 12. Dữ liệu lịch sử: “đã biết lúc đó” khác “hiện công nhận đúng từ lúc đó”

Thay đổi mô hình đặc biệt phức tạp khi dữ liệu có **valid time** và **recorded time**.

Ví dụ chính sách giá giao hàng:

- Ngày 01/03: hệ thống biết phí áp dụng là 20.000 VND.
- Ngày 10/03: doanh nghiệp phát hiện phí phải là 18.000 VND kể từ 01/03.
- Ngày 10/03: ghi nhận quyết định sửa hồi tố.

Một báo cáo cần trả lời hai câu hỏi:

1. **Vào ngày 05/03, hệ thống đang biết mức phí nào?** 20.000 VND.
2. **Theo quyết định mới, phí có hiệu lực cho ngày 05/03 là bao nhiêu?** 18.000 VND.

Nếu chỉ ghi đè một cột Type 1, có thể mất câu trả lời thứ nhất. Nếu chỉ giữ `valid_from/to` mà không lưu lúc hệ thống ghi nhận correction, cũng khó trả lời câu hỏi “lúc đó biết gì”.

| Cơ chế | Khi phù hợp | Giới hạn |
| --- | --- | --- |
| **SCD Type 1** | Sửa giá trị hiển thị và chủ ý phân nhóm lại toàn bộ lịch sử. | Không giữ giá trị cũ ngay trong dimension. |
| **SCD Type 2 / valid-time** | Cần biết thuộc tính đã có hiệu lực theo từng khoảng. | Một trục thời gian không tự ghi đầy đủ lịch sử hệ thống biết. |
| **Bitemporal** | Cần cả thời gian hiệu lực nghiệp vụ và thời gian ghi nhận. | Chi phí schema, update, truy vấn và constraint cao hơn. |
| **Event/correction history** | Cần biết sự việc và quyết định chỉnh sửa có chứng cứ. | Reader phải hiểu phiên bản/sự kiện; replay không tự bảo đảm đủ dữ liệu. |
| **Audit/CDC** | Cần truy vết thao tác lưu trữ, thay đổi before/after. | Không mặc định ghi được ý nghĩa nghiệp vụ của sự kiện. |

**Đừng coi `updated_at` là “đã có lịch sử”.** Nó chỉ cho biết lần sửa gần nhất nếu không có thông tin phiên bản khác.

### Fact lịch sử phải giữ đúng điểm chốt

Catalog có thể đổi `list_price` hiện hành, nhưng `order_line.agreed_unit_price` của đơn đã chốt cần giữ theo chứng từ giao dịch. Nếu migration đổi một tên cột giá thành tên chung `price` rồi dùng query sang Catalog để tính đơn cũ, dữ liệu có thể mất đúng nghĩa lịch sử dù schema hợp lệ.

## 13. Compatibility là ma trận giữa writer, reader và nguồn dữ liệu cũ

Khi deploy thay đổi mô hình, luôn có giai đoạn writer và reader **không cùng phiên bản**.

| Writer / Reader | Reader cũ | Reader mới |
| --- | --- | --- |
| **Writer cũ** | Thường chạy theo hợp đồng v1. | Reader mới cần đọc v1 hoặc có adapter. |
| **Writer mới** | Cần backward compatibility của writer với reader cũ, hoặc phiên bản v1 song song. | Cần đọc v2 và validate mới. |

Để tránh nhập nhằng thuật ngữ:

- **Reader mới đọc dữ liệu writer cũ:** thường gọi **backward compatibility** theo cách định nghĩa reader/writer.
- **Reader cũ đọc dữ liệu writer mới:** thường gọi **forward compatibility**.
- **Full compatibility:** hai chiều theo các ràng buộc đã quy định.

Một số schema registry/framework có cách định nghĩa và quy tắc riêng; phải kiểm tra công cụ đang dùng, không tự suy rằng mọi việc thêm field đều an toàn.

### Rename trong REST/GraphQL/JSON

Ví dụ JSON v1:

~~~json
{
  "customer_id": "CUS-42",
  "customer_name": "Nguyễn Vân"
}
~~~

JSON v2:

~~~json
{
  "customer_id": "CUS-42",
  "display_name": "Nguyễn Vân"
}
~~~

Nếu consumer cũ **yêu cầu** `customer_name`, bỏ field này là breaking change. Một cách chuyển tiếp có kiểm soát là phát cả hai trường cùng nghĩa trong một thời gian, tài liệu hóa deprecation và cấm consumer mới tiếp tục dùng trường cũ. Nhưng phải đảm bảo **hai trường luôn đồng nhất**, không trở thành hai giá trị khác nhau.

### Rename hoặc change của event schema

Event bất biến được ghi theo `event_type + schema_version` phải còn đọc được sau nhiều năm. Upcaster có thể đổi biểu diễn `customer_name` v1 thành `display_name` chuẩn nếu nghĩa không đổi.

~~~text
decode_v1(event):
  return CanonicalCustomerRenamed(
    display_name = event.payload.customer_name,
    original_event_id = event.event_id
  )
~~~

Đây là **mã giả**, và chỉ hợp lệ khi sự kiện v1 thật sự mô tả cùng dữ kiện. Upcaster không thể biến `PaymentRequested` thành `PaymentCaptured` chỉ bằng rename nếu không có xác nhận giao dịch.

### CDC là hợp đồng dễ bị phụ thuộc ngầm

Một consumer đọc trực tiếp CDC của bảng có thể thấy tên cột/kiểu thay đổi dù API nghiệp vụ không đổi. Nếu CDC được dùng lâu dài cho tích hợp, cần schema contract, cursor/checkpoint, quyền và deprecation như một giao diện chính thức; tốt hơn trong nhiều trường hợp là **transactional outbox** công bố integration event có ngữ nghĩa ổn định.

## 14. Thay đổi bảng và contract: không có “một script SQL là xong”

Một thay đổi liên quan nhiều tầng:

~~~mermaid
flowchart TD
    REQ["Yêu cầu nghiệp vụ và định nghĩa dữ liệu"] --> MODEL["Mô hình logic: thực thể, grain, khóa, bất biến"]
    MODEL --> DB["Lược đồ vật lý: bảng, cột, index, FK"]
    DB --> WRITE["Writer / validation / transaction"]
    WRITE --> API["API, event, CDC contract"]
    API --> CONS["Consumer, cache, read model, report"]
    CONS --> QA["Đối soát và giám sát"]
    QA -. "Phát hiện drift/điều chỉnh" .-> MODEL
~~~

Một kế hoạch migration hoàn chỉnh phải nhận diện **mọi bên phụ thuộc**:

- ORM mapping, raw SQL, stored procedure/trigger, views/materialized views.
- Migration scripts đang chạy, dữ liệu import và batch jobs.
- REST/GraphQL/gRPC, JSON/Avro/Protobuf events, Kafka topics, CDC.
- Cache, search index, analytical fact/dimension, exports.
- Mobile/offline clients chưa nâng cấp, tích hợp đối tác.
- Audit, backup, retention và công cụ vận hành/debug.

Nếu thay đổi chỉ là rename trong database nhưng một đối tác đọc file CSV có header `customer_name`, đó vẫn là thay đổi hợp đồng cần quản trị. Một column rename có thể không cần thay giá trị, nhưng có thể cần hàng loạt sửa reader.

### Cần xác định một nguồn sự thật trong thời gian chuyển

Trong giai đoạn hai biểu diễn tồn tại, phải quy định:

- Trường/bảng nào là **authoritative** ở pha hiện tại?
- Writer nào được phép sửa, có một đường ghi hay nhiều đường ghi?
- Cơ chế đồng bộ phần dẫn xuất là gì?
- Điều kiện nào chứng minh có thể chuyển quyền đọc?
- Có thể rollback tới đâu nếu đã xuất hiện dữ liệu mới không còn biểu diễn được theo mô hình cũ?

Đặc biệt với thay đổi 1:1 → 1:N, hệ thống cũ không thể biểu diễn nhiều số điện thoại. Một khi consumer bắt đầu ghi **hai contact cùng loại**, rollback về một cột `phone_e164` cũ **không còn lossless**. Cần xác định **rollback boundary** trước khi cho phép tính năng mới.

## 15. Migration online: dữ liệu lớn, concurrent writes và ràng buộc

Với database lớn, một phép backfill không chỉ là biến đổi logic mà là **thao tác vật lý** ảnh hưởng WAL, CPU, index, replication và lock.

### Thứ tự triển khai tương thích

1. Kiểm kê dữ liệu và các record không hợp lệ: NULL, ký tự lạ, duplicate keys, orphan references.
2. **Expand**: thêm cấu trúc mới mà không làm writer cũ lỗi.
3. Nâng cấp reader và writer theo compatibility matrix; nếu cần, triển khai một đường ghi cập nhật cả biểu diễn cũ/mới atomically.
4. **Backfill theo batch** có checkpoint, retry, giới hạn tải và tiêu chí idempotency.
5. Đối soát grain, số hàng, tiền tệ, dữ liệu khác nhau và tác động báo cáo.
6. Tạo/kiểm chứng constraint và index phù hợp. Một số hệ hỗ trợ validate riêng hoặc online DDL, nhưng khả năng cụ thể phải kiểm tra phiên bản DB.
7. Chuyển đường đọc (canary → mở rộng), theo dõi lag/drift và lỗi contract.
8. Sau cửa sổ tương thích, **contract**: thu hồi cột/bảng cũ, code cũ và quyền truy cập không cần thiết.

### Bẫy index và constraint trong PostgreSQL

Với PostgreSQL, `CREATE INDEX CONCURRENTLY` có thể giảm chặn ghi trong quá trình tạo index, nhưng **không được chạy bên trong một transaction block thông thường**; nó cũng có chi phí, có thể thất bại và để lại index không hợp lệ cần xử lý theo hướng dẫn phiên bản. Đừng nhét lệnh này vào cùng `BEGIN ... COMMIT` của backfill chỉ vì muốn “mọi thứ atomic”.

`ALTER TABLE ... ADD CONSTRAINT ... NOT VALID` rồi `VALIDATE CONSTRAINT` hữu ích với một số ràng buộc như CHECK/FK trong trường hợp hỗ trợ; **không phải mọi loại constraint đều có cùng cơ chế**. Việc thêm UNIQUE/PK trên bảng lớn phải có kế hoạch index và lock tương ứng. Khi constraint chưa được validate, không tự công bố toàn bộ dữ liệu lịch sử đã đạt chuẩn.

### Foreign key và thay đổi khóa

Nếu chuyển từ `email` sang `customer_id` làm khóa:

- Tạo ID bền vững và unique, kiểm tra email trùng/case-sensitivity/tenant scope.
- Bổ sung cột tham chiếu mới ở child tables, backfill bằng mapping có căn cứ.
- Kiểm tra hàng thiếu parent, ID tái sử dụng và các trường hợp hợp nhất khách.
- Tạo FK phù hợp và validate ở một mốc dữ liệu nhất quán.
- Chuyển writer/reader rồi mới bỏ phụ thuộc khóa cũ.

Không xóa FK trước rồi mặc định dữ liệu sẽ tự toàn vẹn; cũng không nâng cấp khóa bằng cách đánh đổi ràng buộc mà không có phương án thay thế.

## 16. SQL kiểm chứng: chứng minh dữ liệu và ngữ nghĩa không bị sai

Một migration phải có **phép chứng minh cụ thể**, không chỉ “script chạy không báo lỗi”.

### Kiểm tra tên trong pha dual-column

~~~sql
SELECT COUNT(*) AS rows_with_mismatched_name
FROM customer_account
WHERE display_name IS DISTINCT FROM customer_name;
~~~

Kỳ vọng 0 **trong thời gian hai cột được quy định cùng nghĩa và phải đồng bộ**. Sau khi contract, không còn dùng phép so với cột cũ.

### Kiểm tra khóa và grain

~~~sql
SELECT tenant_id, customer_id, COUNT(*) AS n
FROM customer_account
GROUP BY tenant_id, customer_id
HAVING COUNT(*) > 1;
~~~

PK thực thi thông thường đã chặn trùng, nhưng truy vấn hữu ích khi kiểm tra staging/copy ở hệ thống chưa áp constraint.

### Kiểm tra quan hệ sau khi tách bảng

~~~sql
SELECT m.tenant_id, m.customer_id
FROM customer_contact_method m
LEFT JOIN customer_account c
  ON c.tenant_id = m.tenant_id
 AND c.customer_id = m.customer_id
WHERE c.customer_id IS NULL;
~~~

Kỳ vọng 0 nếu các bảng cùng DB và ràng buộc được thực thi đầy đủ. Nếu dữ liệu được nạp qua pipeline/không cùng DB, kiểm tra orphan càng quan trọng.

### Kiểm tra giá trị lịch sử khi thay nghĩa

Không có một câu SQL đơn giản nào chứng minh “mọi `PAID` lịch sử là đã capture” khi nguồn cũ không lưu provider confirmation. Cần bảng đối soát với nguồn giao dịch có thẩm quyền:

~~~text
order_id | legacy_status | provider_capture_ref | evidence_status
ORD-1    | PAID          | CAP-101              | VERIFIED
ORD-2    | PAID          | NULL                 | UNKNOWN
ORD-3    | PENDING       | CAP-105              | REQUIRES_REVIEW
~~~

Ở hàng `ORD-2`, giá trị `UNKNOWN` là thông tin thật về giới hạn chứng cứ. Ở hàng `ORD-3`, không tự đổi `PENDING` thành `CAPTURED` nếu chưa giải thích mốc nghiệp vụ và quy tắc đối soát.

### Đối soát theo hạt và đơn vị

Nếu migration biến order amount thành nhiều payment movements, phải so:

- Số order theo tenant và thời kỳ.
- Số transaction duy nhất theo provider reference/idempotency key.
- Tổng `CAPTURE` và `REFUND` **riêng theo currency**.
- Số bản ghi chưa đối soát, không có nguồn hoặc mâu thuẫn.
- Phiên bản công thức KPI trước/sau và phạm vi restatement.

**Không cộng số tiền của các loại tiền tệ khác nhau.** Không so tổng giá trị đơn với tổng đã capture rồi kết luận phải bằng nhau nếu nghiệp vụ cho phép giao hàng chưa thu, thanh toán nhiều lần hoặc hoàn một phần.

## 17. Tiến hóa dữ liệu trong document, graph và analytics

Nguyên tắc rename/structural/semantic áp dụng cho nhiều mô hình lưu trữ, nhưng tác động vật lý khác nhau.

| Kiểu lưu trữ | Đổi tên | Đổi cấu trúc | Đổi ý nghĩa |
| --- | --- | --- | --- |
| **Quan hệ** | Đổi cột/view/mapper; xét SQL/ORM/CDC. | Split/merge bảng, PK/FK, unique, index, partition. | Thường cần rule/constraint/source mới và đối soát lịch sử. |
| **Document** | Đổi key JSON, reader hỗ trợ schema cũ và mới. | Chuyển embedded object ↔ references/collections; đổi aggregate boundary. | Cần version tài liệu và quy tắc đọc legacy; parse JSON không đủ. |
| **Graph** | Đổi label/property/relation name có ánh xạ cùng nghĩa. | Tách node, thêm edge và cardinality; đổi hướng quan hệ/traversal. | Đổi nghĩa `FRIEND` từ “theo dõi” sang “đã chấp nhận kết bạn” cần sự kiện/bằng chứng. |
| **Analytics** | Đổi nhãn fact/dimension/metric trong semantic layer. | Đổi grain, SCD, star schema/data mart, backfill. | Đổi công thức/doanh thu và lịch công bố phải version/restatement. |
| **Event store** | Upcast cách biểu diễn của event cũ nếu cùng nghĩa. | Đổi envelope/payload, tách event type, lưu version. | Không sửa sự kiện đã xảy ra để giả tạo sự thật mới; cần correction/confirmation. |

### Document: schema-on-read không loại bỏ schema

Một document v1 có `"phone": "..."`, document v2 có `"contacts": [...]`. Nếu reader mới chỉ hiểu `contacts`, tài liệu cũ vẫn phải được backfill hoặc đọc qua adapter. Một số hệ chỉ cập nhật document khi nó được ghi lại, khiến trong cùng collection có nhiều shape tồn tại lâu. Hãy version tài liệu và quy định khi nào decoder hỗ trợ từng dạng.

### Graph: sửa quan hệ thường là đổi nghĩa

Đổi edge `WORKS_AT` sang `EMPLOYED_BY` có thể là rename nếu cùng điều kiện và cùng thời gian hiệu lực. Nhưng nếu `WORKS_AT` trước đây bao gồm cộng tác viên còn `EMPLOYED_BY` chỉ gồm nhân viên ký hợp đồng, đó là đổi ngữ nghĩa, cần nguồn kiểm chứng. Chỉ thay label sẽ tạo cạnh sai.

### Analytics: đổi metric cần version

Tên `net_revenue` nghe rõ, nhưng có thể đang được tính từ đơn hàng sau giảm giá, còn định nghĩa mới đòi invoice recognized revenue sau điều chỉnh. Hãy tạo metric/version rõ (hoặc công bố lần restatement), ghi nguồn và khoảng thời gian áp dụng. Không đổi công thức rồi để người xem tin số từ hai kỳ có cùng nghĩa.

## 18. Quản trị schema, hợp đồng và quyền dữ liệu

Một thay đổi kỹ thuật có thể trở thành vi phạm an toàn khi làm lộ dữ liệu hoặc thay đổi owner.

### Chủ sở hữu và quyền ghi

- Ai sở hữu dữ kiện và có quyền quyết định sửa?
- Dữ liệu nằm trong service/schema nào; service khác có đang `UPDATE` trực tiếp bảng không?
- Thay đổi cấu trúc có tạo bản sao mới không; nó có được phân quyền cùng mức với bản nguồn?
- API/event mới có vô tình công bố email, địa chỉ hoặc thuộc tính nhạy cảm hơn trước không?
- Data warehouse có coi một fact/dimension dẫn xuất như nguồn có thẩm quyền và ghi ngược về OLTP không?

Một ranh giới tốt cho phép owner đổi bảng nội bộ mà không buộc mọi consumer đổi theo. Consumer sử dụng **published contract**, không coi tên cột vật lý là API ổn định.

### Retention, erasure và lịch sử

Khi tách `customer.phone` sang `customer_contact_method`, thông tin cũ còn tồn tại trong backfill log, audit, CDC stream, read models, backups và exports. Xóa cột cũ **không tự xóa mọi bản sao dữ liệu cá nhân**.

Nếu có yêu cầu xóa/ẩn danh hợp lệ, phải xét nguồn, bản dẫn xuất, retention, legal hold theo chính sách thực tế. Không coi việc hash ID hoặc bỏ tên hiển thị là ẩn danh tuyệt đối nếu dữ liệu vẫn có thể liên kết trở lại người dùng.

### Một hợp đồng migration cần giữ những gì?

| Thuộc tính | Ví dụ |
| --- | --- |
| `change_id` và owner | `CUST-MODEL-2026-01`, đội Customer Identity. |
| Loại thay đổi | Rename + structural split + semantic change riêng biệt. |
| Nguồn → đích | `customer_name → display_name`. |
| Grain và khóa | `(tenant_id, customer_id)` không đổi; contacts 0..N. |
| Quy tắc mapping | Chỉ tạo contact từ `phone_e164` có dữ liệu hợp lệ. |
| Quy tắc ngữ nghĩa | `ACTIVE` mới cần verification evidence. |
| Backward/forward policy | Reader v1/v2 được hỗ trợ đến mốc nào. |
| Data quality và exceptions | Missing, duplicate, ambiguous, conflict. |
| Security/retention | Đường chứa PII và chính sách xử lý. |
| Cutover/rollback | Khi nào chuyển owner, điều kiện có thể phục hồi. |
| Success criteria | Row count, FK, KPI, consumer contract và SLO. |

## 19. Tình huống lỗi và rollback cần diễn tập trước khi xóa cột

| Sự cố | Hệ quả | Cách phòng ngừa/khôi phục |
| --- | --- | --- |
| Ứng dụng v1 còn ghi `customer_name` sau cutover | `display_name` bị stale hoặc lệch. | Kiểm kê writer, tương thích pha chuyển, chặn writer cũ sau mốc chốt. |
| Batch backfill chạy lại | Tạo contact trùng hoặc ghi đè dữ liệu mới. | Business key/unique, idempotent backfill và kiểm tra phiên bản. |
| Hai writer cùng tạo primary phone | Vi phạm unique hoặc tranh quyết định primary. | Transaction/locking theo Customer và chính sách xung đột. |
| Rename cột khi query SQL cũ còn chạy | API/report lỗi ngay khi deploy. | Expand–contract, inventory dependencies, canary. |
| Data v1 không parse được vào schema v2 | Reader mới lỗi hoặc “sửa” bằng giá trị đoán. | Adapter versioned, quarantine, golden fixtures. |
| `PAID` cũ bị đọc như provider-confirmed | Doanh thu và quy trình hoàn tiền sai. | Legacy semantic version, đối soát, phân loại unknown. |
| Xóa bảng cũ rồi cần rollback | Mất dữ liệu không có trong đích. | Backup/rollback window, giữ dữ liệu cũ đủ lâu; xác định điểm không thể đảo. |
| Hai mô hình 1:N và 1:1 cùng nhận ghi | Không có mapping ngược lossless. | Chọn một owner ghi; giới hạn tính năng mới đến sau mốc cutover. |
| Aggregate cũ chưa được rebuild | Báo cáo vẫn phản ánh grouping/meaning cũ. | Shadow mart, đối soát grain và metric version. |
| DDL lớn làm lock lâu hoặc replica lag | Ảnh hưởng SLO production. | Batch/online DDL phù hợp, thử nghiệm và giới hạn tài nguyên. |
| Backup restore trước migration | Hệ phục hồi không hiểu contract/schema hiện tại. | Runbook restore + replay migrations + kiểm tra compatibility. |
| Đổi khóa mà bỏ qua tenant scope | FK trỏ sai khách/đơn của tenant khác. | Composite keys, test tenant isolation, quyền và mapping. |

### Phân biệt rollback code, rollback schema và rollback dữ liệu

Ba việc này **khác nhau**:

- **Rollback code:** chạy lại phiên bản ứng dụng cũ; chỉ an toàn nếu nó hiểu dữ liệu/contract hiện đang tồn tại.
- **Rollback schema:** trả lại cột/bảng cũ; có thể không khôi phục được dữ liệu đã bị loại hoặc phân tách.
- **Rollback dữ liệu:** khôi phục trạng thái tại một mốc bằng backup, log hay phép migration ngược đã được chứng minh; cần tránh mất dữ liệu mới đã commit hợp lệ.

Một thay đổi semantic không thể rollback chỉ bằng đổi tên cột. Khi quyền giao dịch đã được cấp theo quy tắc mới hoặc provider đã capture tiền, việc quay lại code không đảo được tác động nghiệp vụ; cần workflow và correction rõ ràng.

## 20. Quy trình ra quyết định: phân loại trước, triển khai sau

Có thể dùng checklist theo thứ tự:

**Bước 1 — Viết hợp đồng nguồn và đích.** Với mỗi field/entity, định nghĩa grain, ID, kiểu, đơn vị, nullability, thời gian, chủ sở hữu, điều kiện chốt, constraint, người dùng dữ liệu.

**Bước 2 — Chứng minh mức thay đổi.**

- Cùng nghĩa, cùng grain và chỉ khác tên? Rename.
- Đổi biểu diễn/cardinality/keys? Structural.
- Đổi nguồn có thẩm quyền, điều kiện xác nhận, cách tính, hiệu lực hay định nghĩa KPI? Semantic.
- Nhiều câu trả lời Có? Ghi thành một **migration có nhiều loại rủi ro**, không gán nhãn duy nhất để giảm độ khó.

**Bước 3 — Phân loại dữ liệu cũ.** Dữ liệu nào ánh xạ chắc chắn, dữ liệu nào thiếu thông tin, dữ liệu nào phải đưa vào review/unknown?

**Bước 4 — Chọn compatibility strategy.** Direct rename chỉ khi hệ khép kín có downtime/điều phối; expand–contract khi cần rolling deployment; versioned adapter/upcaster cho historical events; shadow projection khi đổi nghĩa KPI.

**Bước 5 — Thiết kế và kiểm chứng bất biến.** PK/FK/unique/check, grain không đổi bất ngờ, currency/unit đúng, không mồ côi tham chiếu, không ghi đè nguồn sự thật.

**Bước 6 — Lập rollout/cutover/rollback.** Ai ghi, ai đọc, khi nào bắt đầu dùng trường mới, khi nào bỏ cũ, khi nào hết khả năng rollback lossless?

**Bước 7 — Đo và đối soát.** Row count, duplicate/orphan, mismatch, exception count, version/schema errors, query P95/P99, outbox/projection lag, metrics trước/sau.

### Một cây quyết định ngắn

~~~mermaid
flowchart TD
    A["Đề xuất thay đổi dữ liệu"] --> B{"Ý nghĩa, thời điểm, owner có đổi?"}
    B -->|"Có"| S["Đổi ngữ nghĩa: định nghĩa mới + bằng chứng lịch sử"]
    B -->|"Không"| C{"Grain, khóa, quan hệ, kiểu/đơn vị có đổi?"}
    C -->|"Có"| T["Đổi cấu trúc: mapping + constraints + backfill"]
    C -->|"Không"| D{"Chỉ đổi tên hoặc nhãn?"}
    D -->|"Có"| N["Rename: contract compatibility + rollout"]
    D -->|"Không"| R["Làm rõ đề bài và quyền sở hữu"]
    S --> M["Đánh giá thêm thay đổi cấu trúc/rename đi kèm"]
    T --> M
    N --> M
    M --> V["Kiểm chứng, cutover, quan sát và dọn phụ thuộc"]
~~~

Cây được dùng để **phát hiện nhóm rủi ro đầu tiên**, không để cho rằng một nhánh loại trừ các nhánh khác. Dự án có semantic change vẫn có thể cần structural migration và rename.

## 21. Bài tập thực hành: tiến hóa mô hình đơn hàng mà không làm sai lịch sử

**Bối cảnh:** một nền tảng đặt dịch vụ dùng PostgreSQL và gửi event cho Finance/CRM. Lược đồ cũ:

~~~text
customer(
  tenant_id, customer_id, customer_name, phone, active
)

booking(
  tenant_id, booking_id, customer_id, total_amount, status, created_at
)

status = NEW | PAID | CANCELLED
~~~

Thông tin thêm được kiểm chứng từ các nhóm:

- `customer_name` là tên hiển thị, không phải tên pháp lý.
- `phone` hiện chỉ giữ một số; khách có thể muốn nhiều số và thông tin xác minh.
- `active` cũ có nghĩa “chưa đóng tài khoản”, không phải “đã xác minh”.
- `total_amount` cũ là giá trị đã báo cho khách **trước khi hoàn tiền**, nhưng lịch sử không luôn ghi rõ giảm giá và tiền tệ.
- `PAID` cũ được ghi khi hệ thống gửi yêu cầu thanh toán; provider callback thành công không phải lúc nào cũng được lưu.
- Các booking lịch sử cần giữ để hỗ trợ tranh chấp; một số khách yêu cầu xóa thông tin liên hệ theo chính sách.
- CRM dùng JSON `customer_name`; Finance đọc CDC bảng booking; một bản ứng dụng di động cũ còn hoạt động.

### Nhiệm vụ

1. **Phân loại sáu yêu cầu:** đổi `customer_name` thành `display_name`, tách `phone`, đổi `active`, đổi `total_amount` thành `net_cash`, sửa `PAID`, bổ sung nhiều bản booking history. Nêu mỗi yêu cầu là rename, structural, semantic hay kết hợp.
2. **Định nghĩa hợp đồng:** với `customer_id`, `phone`, `booking.total_amount` và `PAID`, ghi rõ grain, đơn vị, thời điểm, owner, nullability và bằng chứng.
3. **Thiết kế khóa:** bảng Contact 0..N, primary phone, verification, tenant isolation; vì sao không dùng email/phone làm PK của Customer?
4. **Lập migration rename:** viết `ADD COLUMN display_name`, query tương thích, backfill, kiểm tra mismatch và kế hoạch bỏ cột cũ sau khi CRM/mobile nâng cấp.
5. **Migrate phone:** tạo bảng Contact với FK; nêu phương pháp chống record trùng, xử lý số không hợp lệ và lý do không đánh dấu legacy phone đã xác minh.
6. **Xử lý semantic trạng thái:** tách account lifecycle, verification và quyền giao dịch; đề xuất giá trị UNKNOWN cho lịch sử không có bằng chứng.
7. **Tách amount:** phân biệt booked amount với captured/refunded cash; thiết kế `payment_movement` có grain một giao dịch provider-confirmed, `currency` và idempotency.
8. **Đối soát `PAID`:** lập danh mục `VERIFIED_CAPTURE`, `PENDING_RECONCILIATION`, `UNKNOWN_LEGACY`; giải thích vì sao không thể backfill toàn bộ thành CAPTURED.
9. **Thời gian:** phân biệt booking `created_at`, provider `captured_at` và `recorded_at` của callback; xử lý callback đến muộn.
10. **Consumer:** định nghĩa API/event v2, compatibility matrix và reader lịch sử; phân biệt CDC với integration event có nghĩa nghiệp vụ.
11. **Triển khai production:** thứ tự expand, dual-column write, backfill, validate, cutover, contract; các bước nào cần một writer và các bước nào không đảo ngược được?
12. **Bảo mật:** nêu đường dữ liệu cá nhân còn tồn tại ở staging, event, read model, backup và cách xử lý retention/erasure theo policy.
13. **Kiểm thử:** viết query/test cho mismatch, duplicate BK, orphan FK, fact-grain, net cash theo tiền tệ, provider outcome unknown và reader API v1/v2.
14. **ADR:** ghi hai phương án đã loại bỏ, lý do chọn, SLO, owner, kịch bản rollback và điều kiện hoàn thành.

### Bảng kiểm tự đánh giá

| Tiêu chí | Dấu hiệu đạt |
| --- | --- |
| **Phân loại đúng** | Rename chỉ khi cùng nghĩa; cấu trúc và ngữ nghĩa được nhận diện độc lập. |
| **Không bịa dữ kiện** | Không tự tạo verification, refund hoặc capture từ trạng thái thiếu bằng chứng. |
| **Khóa/grain đúng** | Tách Contact 0..N, giữ business IDs và FK/unique theo tenant. |
| **Tương thích** | Reader cũ/mới và dữ liệu lịch sử có đường chuyển đổi rõ. |
| **Triển khai an toàn** | Expand–migrate–contract có một nguồn ghi, backfill/checkpoint, cutover và kiểm chứng. |
| **Tính đúng của KPI** | Booked amount khác net cash; không gộp sai currency/đếm trùng movement. |
| **Lịch sử** | Chứng từ và thời điểm được bảo tồn theo nghĩa nghiệp vụ và retention. |
| **Vận hành** | Theo dõi mismatch, unknown, lag, load, error và kế hoạch rollback thực tế. |

**Kết luận:** đổi tên chỉ đổi **cách gọi** một sự thật, đổi cấu trúc đổi **cách biểu diễn và quan hệ**, còn đổi ý nghĩa thay **điều giá trị khẳng định về nghiệp vụ**. Một migration có thể bao gồm cả ba. Muốn hệ thống dễ tiến hóa mà vẫn kiểm chứng được, hãy xác định grain, business key, ràng buộc, chủ sở hữu, thời gian và hợp đồng của dữ liệu nguồn/đích; chỉ chuyển thông tin đã biết một cách có căn cứ, tách dữ liệu legacy mơ hồ, triển khai tương thích theo giai đoạn và đối soát trước khi bỏ cấu trúc cũ.
