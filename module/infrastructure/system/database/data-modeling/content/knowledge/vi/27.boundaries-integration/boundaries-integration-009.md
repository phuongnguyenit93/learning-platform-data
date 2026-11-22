# Quyền sở hữu dữ liệu giữa dịch vụ và tránh chia sẻ bảng ngoài kiểm soát

## 1. Bài toán: nhiều dịch vụ cùng nhìn một bảng, ai chịu trách nhiệm?

Giả sử hệ thống bán hàng có bốn dịch vụ: **Catalog** quản lý sản phẩm, **Ordering** quản lý đơn, **Inventory** quản lý tồn kho và **Payment** quản lý các yêu cầu thu/hoàn tiền. Vì thuận tiện, cả bốn dịch vụ cùng dùng bảng `product` và `orders` trong một database. Catalog sửa tên sản phẩm; Ordering đọc trực tiếp bảng Catalog để hiện tên trong chi tiết đơn; Inventory cập nhật cột `stock_quantity` của `product`; Payment viết `orders.payment_status = 'PAID'` sau khi nhận callback.

Thiết kế này có thể hoạt động trong một bản thử nghiệm nhỏ, nhưng khi mở rộng sẽ phát sinh những câu hỏi rất khó trả lời:

- Khi `product` đổi schema, đội nào có quyền phê duyệt và ai phải sửa theo?
- Một bản cập nhật `stock_quantity` có phải qua logic giữ hàng và chống đặt vượt tồn không?
- `payment_status = 'PAID'` có nghĩa đã gửi yêu cầu thu hay nhà cung cấp đã xác nhận thu?
- Ai được xóa khách hàng và những bảng nào được phép tiếp tục giữ chứng từ liên quan?
- Khi báo cáo sai, nguồn nào có thẩm quyền xác nhận giá trị đúng?

Đây là vấn đề **quyền sở hữu dữ liệu (data ownership)**, không đơn thuần là vấn đề đặt bảng trong database nào.

**Nguyên tắc trọng tâm:** mỗi **sự thật nghiệp vụ có thẩm quyền** cần một chủ sở hữu rõ ràng, chịu trách nhiệm về định nghĩa, bất biến, ghi nhận và vòng đời; các dịch vụ khác truy cập qua **hợp đồng tích hợp được quản trị** thay vì tự ý ghi vào bảng của chủ sở hữu.

Quyền sở hữu không có nghĩa mọi dịch vụ chỉ được đọc một loại dữ liệu hoặc không được sao chép bất cứ dữ liệu nào. Một dịch vụ có thể giữ **read model/cache bản dẫn xuất** của thông tin do dịch vụ khác sở hữu, miễn biết nguồn, độ mới, cách đồng bộ, quyền sử dụng và cách xử lý khi nguồn sửa/xóa.

## 2. Quyền sở hữu là quyền quyết định ngữ nghĩa và bất biến, không chỉ sở hữu máy chủ

Một dịch vụ **sở hữu** dữ liệu khi có quyền và trách nhiệm:

1. Định nghĩa **thực thể, business key, ràng buộc và trạng thái nghiệp vụ**.
2. Chấp nhận hoặc từ chối các command làm thay đổi sự thật thuộc phạm vi của mình.
3. Quyết định **điểm chốt** một sự việc: `PaymentCaptured` chỉ sau xác nhận của nguồn thanh toán, `StockReserved` sau khi tồn kho chấp nhận giữ.
4. Công bố **API/event/data contract** đã version hóa cho consumer.
5. Quản trị schema, migration, phân quyền, retention và xử lý dữ liệu sai/điều chỉnh.
6. Giải thích tình trạng nhất quán và xác minh dữ liệu với nguồn có thẩm quyền.

Bốn khái niệm cần phân biệt:

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Business/domain ownership** | Ai quyết định một sự thật là hợp lệ? | Inventory quyết định có thể giữ 1 ghế/1 món hàng. |
| **Data storage ownership** | Ai quản lý bảng, document, chỉ mục và migration vật lý? | Nhóm Inventory quản lý schema `inventory`. |
| **Data contract ownership** | Ai cam kết ý nghĩa, trường và thời gian cung cấp dữ liệu? | Catalog xuất `ProductChanged.v2`. |
| **Data stewardship/governance** | Ai chịu trách nhiệm chất lượng, quyền, danh mục, chính sách toàn tổ chức? | Nhóm quản trị dữ liệu phối hợp cùng domain owner. |

Một nhóm hạ tầng vận hành cùng một PostgreSQL cluster cho nhiều dịch vụ **không có nghĩa** nhóm đó quyết định thế nào là “đơn đã thanh toán”. Ngược lại, một domain owner có thể dùng kho lưu trữ do đội platform quản lý nhưng vẫn sở hữu hợp đồng và quyết định nghiệp vụ.

### Chọn ranh giới theo năng lực nghiệp vụ

Không lấy bảng làm ranh giới trước rồi tạo “ProductService vì có bảng product”. Hãy xét năng lực và bất biến:

- **Catalog:** định danh sản phẩm, nội dung, phân loại, trạng thái công bố.
- **Inventory:** số lượng khả dụng, đặt chỗ, giải phóng và quy tắc không cấp vượt nguồn lực.
- **Ordering:** vòng đời đặt hàng, dòng hàng, trạng thái hủy/xác nhận theo quy tắc đơn.
- **Payment:** giao dịch thu/hoàn, idempotency khi gọi provider, đối soát.
- **Customer Identity:** định danh khách, thông tin liên hệ được phép sử dụng, vòng đời tài khoản.

Các năng lực có thể chung một ứng dụng khi hệ thống còn nhỏ; ranh giới ownership vẫn có giá trị ngay cả khi chưa tách thành các microservice.

## 3. Bản đồ nguồn sự thật: ai được ghi cái gì?

Hãy lập **ownership matrix** trước khi triển khai quan hệ dữ liệu hoặc tích hợp.

| Dữ kiện | Nguồn có thẩm quyền | Các dịch vụ có thể cần đọc | Không nên làm |
| --- | --- | --- | --- |
| Tên/loại sản phẩm đang công bố | Catalog | Ordering, Search, Recommendation | Ordering tự sửa `catalog.product_name`. |
| Tồn khả dụng và reservation | Inventory | Ordering, Storefront | Storefront trừ số lượng tại cache rồi tuyên bố giữ hàng thành công. |
| Đơn và dòng hàng đã chốt | Ordering | Support, Payment, Analytics | Payment sửa trực tiếp hàng đơn để đánh dấu đã thanh toán. |
| Capture/refund được provider xác nhận | Payment | Ordering, Accounting, Analytics | Ordering tự coi `RefundRequested` là tiền đã hoàn. |
| Danh tính và quyền xử lý dữ liệu khách | Customer Identity | Ordering, Support | Mỗi dịch vụ tự sửa email master khi nhận yêu cầu đổi email. |
| KPI doanh thu ròng theo ngày | Analytics/Finance có định nghĩa được phê duyệt | Dashboard, quản lý | Mỗi dashboard tự định nghĩa `revenue` theo dữ liệu khác nhau. |

**Một nguồn sự thật theo phạm vi sự thật**, không phải một “database master của toàn doanh nghiệp”. Ví dụ Catalog quản lý **giá niêm yết hiện hành**, còn Ordering sở hữu **đơn giá đã chốt trên dòng đơn**. Hai giá trị cùng nói về giá nhưng không phải hai bản sao của cùng một sự thật:

- `catalog.current_price`: sản phẩm được chào bán ở giá nào hiện giờ?
- `order_line.agreed_unit_price`: khách đã đồng ý mức giá nào khi đặt đơn?

Ordering **phải giữ giá đã chốt** của giao dịch, không đọc lại Catalog và thay giá cũ khi giá niêm yết đổi. Dữ liệu trùng phần nhìn thấy có thể hợp lệ vì **ngữ nghĩa và thời điểm có thẩm quyền khác nhau**.

### Một mẫu câu để viết ranh giới

> “Dịch vụ **X** là nguồn có thẩm quyền cho **dữ kiện Y** trong phạm vi **Z**. Mọi cập nhật Y phải qua **command/hợp đồng** của X; dịch vụ khác được giữ **bản dẫn xuất D** phục vụ **truy vấn Q**, với **độ trễ/retention** đã xác định.”

Câu này buộc nhóm thiết kế phải nói rõ các phần thường bị bỏ qua: scope, chính sách phiên bản và dữ liệu dẫn xuất.

## 4. Shared-table anti-pattern: chia sẻ bảng làm xói mòn hợp đồng

Một **shared database** không nhất thiết sai, nhưng **nhiều dịch vụ cùng truy cập và thay đổi bảng nghiệp vụ của nhau không có hợp đồng** là rủi ro lớn.

### Mẫu lỗi phổ biến

~~~text
Catalog API -------- INSERT / UPDATE -----+
                                          |
Ordering API ------- SELECT / UPDATE -----+--> product (bảng dùng chung)
                                          |
Inventory worker ---- UPDATE stock -------+
                                          |
Reports ----------- SELECT / JOIN --------+
~~~

Giả sử Catalog đổi `product.status` từ `ACTIVE` sang hai giá trị `PUBLISHED` và `SUSPENDED`. Ordering có query `WHERE status = 'ACTIVE'`; Inventory lại xem `status != 'DELETED'` là bán được. Mỗi consumer đã gắn **ngữ nghĩa riêng** vào một cột vật lý nên migration đơn giản trở thành thay đổi phối hợp nhiều đội.

### Những kiểu phụ thuộc nguy hiểm

| Dạng phụ thuộc | Hậu quả |
| --- | --- |
| Service A `UPDATE` bảng của B | Bị bỏ qua logic kiểm tra quyền, bất biến và side effect của B. |
| Service A tạo FK/JOIN trực tiếp vào bảng B | Schema migration của B thành thay đổi bắt buộc cho A. |
| Nhiều service cùng deploy migration trên một bảng | Tranh quyền owner, thứ tự migration và rollback không rõ. |
| Service dùng trigger của bảng chung để phát sự kiện | Consumer lệ thuộc tác động ngầm, khó kiểm soát khi quy tắc nghiệp vụ đổi. |
| Dashboard đọc OLTP tables bằng tài khoản toàn quyền | Tăng tải, lộ dữ liệu nội bộ và làm khó triển khai versioned contract. |
| Một team sửa bảng “vì chỉ thêm cột” | Có thể phá consumer không chấp nhận trường/enum mới hoặc hiểu sai default. |
| Nhiều hệ dùng trạng thái riêng rồi ghi đè lẫn nhau | Không còn một nguồn sự thật, dễ lost update và dữ liệu không thể đối soát. |

**Cảnh báo đặc biệt:** chỉ cấp quyền `SELECT` trực tiếp không làm dependency biến mất. Consumer vẫn có thể phụ thuộc cột nội bộ, loại mã, cách JOIN và vòng đời hàng mà owner chưa cam kết. Quyền đọc chỉ giảm khả năng phá dữ liệu do ghi, **không tạo ra hợp đồng ngữ nghĩa ổn định**.

### Khi nào shared database có thể chấp nhận?

- **Modular monolith:** các module ở cùng đơn vị triển khai/transaction, có phân quyền logic và owner của schema rõ, migration được phối hợp.
- **Giai đoạn chuyển đổi:** tạm cho một consumer đọc bảng cũ, có danh sách phụ thuộc, phạm vi quyền, hạn chót và kế hoạch thay bằng contract.
- **Một bộ dữ liệu tham chiếu được công bố:** dùng view hoặc schema phục vụ đọc do owner quản lý, có contract/version/giám sát; không tự mở quyền trên bảng lõi.

Nói rõ mức đánh đổi. Không ép phải triển khai database-per-service ngay khi chưa có lý do, nhưng cũng không xem chia sẻ bảng là giao diện tích hợp lâu dài mà không có ownership.

## 5. Các mức cô lập: từ schema riêng đến database riêng

Quyền sở hữu là ranh giới **logic**; cô lập vật lý và quyền truy cập giúp thực thi ranh giới ấy.

| Phương án | Lợi ích | Giới hạn và công việc |
| --- | --- | --- |
| Cùng database, bảng/schema thuộc module rõ | Dễ giao dịch cục bộ, chi phí vận hành thấp. | Phải quản trị vai trò, migration và tránh query xuyên module tùy ý. |
| Database riêng trong cùng server/cluster | Tách credential và một số quyền quản trị, backup logic. | Vẫn có rủi ro cạnh tranh tài nguyên; tính năng cross-database không đồng nhất. |
| Database/cluster riêng mỗi service | Cô lập schema, quy trình triển khai và nhiều loại tài nguyên. | Tăng chi phí hạ tầng; query JOIN hoặc transaction xuyên nguồn khó hơn. |
| Một service sở hữu kho và công bố read model/data product | Consumer đọc cấu trúc ổn định, tách OLTP khỏi workload BI. | Đồng bộ dữ liệu, freshness, quyền và version contract phải được quản trị. |

**Database-per-service là một cách thực thi ownership, không phải định nghĩa của ownership.** Nếu hai dịch vụ chia cluster nhưng tuân thủ nguyên tắc chỉ owner ghi, giao tiếp qua contract và migration có người chịu trách nhiệm, ranh giới vẫn có thể rõ. Ngược lại, hai database tách vật lý nhưng ứng dụng của A đăng nhập trực tiếp vào B và UPDATE bảng B vẫn vi phạm nguyên tắc.

### Ranh giới schema trong PostgreSQL

Một cơ chế triển khai là định nghĩa owner role cho từng schema. Ví dụ dưới đây minh họa cách giới hạn *quyền tạo/sửa bảng* và *truy cập dữ liệu* khi cùng dùng PostgreSQL:

~~~sql
-- Chạy bởi tài khoản quản trị/deployment có quyền phù hợp.
CREATE ROLE catalog_owner NOLOGIN;
CREATE ROLE ordering_owner NOLOGIN;

CREATE SCHEMA catalog AUTHORIZATION catalog_owner;
CREATE SCHEMA ordering AUTHORIZATION ordering_owner;

REVOKE ALL ON SCHEMA catalog FROM PUBLIC;
REVOKE ALL ON SCHEMA ordering FROM PUBLIC;

-- Role runtime của ứng dụng được tạo/quản lý bằng cơ chế cấp quyền
-- và secrets của tổ chức, không hard-code mật khẩu trong script này.
-- Ví dụ catalog_runtime và ordering_runtime đã tồn tại.
GRANT USAGE ON SCHEMA catalog TO catalog_runtime;
GRANT USAGE ON SCHEMA ordering TO ordering_runtime;
~~~

**Lưu ý:** quyền trên **schema** và quyền trên **table/sequence/function** là hai lớp khác nhau. `GRANT USAGE ON SCHEMA` **không tự cho phép SELECT/INSERT/UPDATE bảng**. Chủ sở hữu chỉ cấp quyền phù hợp cho runtime của mình, ví dụ trên bảng Catalog:

~~~sql
-- Do catalog_owner hoặc deployment role được ủy quyền thực hiện.
GRANT SELECT, INSERT, UPDATE, DELETE
ON catalog.product TO catalog_runtime;

-- Không GRANT UPDATE/DELETE trên catalog.product cho ordering_runtime.
-- Ordering nhận bản dẫn xuất qua API/event.
~~~

Các câu trên giả định bảng `catalog.product` và hai role runtime đã được tạo; đây là ví dụ quyền, không phải migration chạy độc lập từ đầu đến cuối. Với cột identity/sequence hoặc function, cần cấp đúng quyền phụ thuộc theo cấu trúc thật. Tài khoản runtime không nên là owner của tất cả bảng và không nên có quyền DDL tùy ý.

Một nguyên tắc đơn giản để kiểm tra: **service runtime phải bị database từ chối khi cố sửa bảng do service khác sở hữu**, kể cả lập trình viên viết nhầm một câu SQL.

## 6. Kết nối giữa dịch vụ: đồng bộ, bất đồng bộ hay bản sao đọc?

Không phải mọi consumer đều cần cùng một phương thức truy cập.

| Cơ chế | Phù hợp với | Đánh đổi |
| --- | --- | --- |
| **API/command đồng bộ** | Cần quyết định tức thời của owner: giữ tồn, kiểm tra hạn mức, lấy thông tin phải mới. | Độ trễ mạng, timeout, cascading failure; cần SLO và fallback đúng nghĩa. |
| **Query API theo hợp đồng** | Truy xuất một đối tượng hoặc danh sách có filter được owner cam kết. | Query liên dịch vụ có thể N+1 calls; cần pagination/cache và giới hạn tải. |
| **Integration event + local read model** | Consumer cần thông tin phục vụ truy vấn riêng, có thể chấp nhận độ trễ. | Idempotency, ordering, schema evolution, lag và xử lý correction/delete. |
| **Transactional outbox + broker** | Owner phải phát tin cậy một sự việc đã commit. | Relay/consumer vẫn có thể retry và nhận message lặp; cần dedup. |
| **CDC từ DB của owner** | ETL/analytics, migration, legacy integration có kiểm soát. | CDC mô tả thay đổi lưu trữ, không tự là domain event hoặc API ổn định. |
| **Read-only published view/data product** | Báo cáo, truy vấn được quản trị, cần hợp đồng SQL rõ. | Owner phải quản lý version, quyền, tải truy vấn và thời điểm ngừng hỗ trợ. |

**Chọn theo ý nghĩa nghiệp vụ, không theo sự tiện của giao thức.** Gọi Inventory qua API để yêu cầu giữ hàng là hành động có thẩm quyền. Lấy tên sản phẩm cho màn hình danh sách có thể dùng local projection; không cần gọi Catalog cho mỗi dòng nếu chấp nhận độ trễ. Còn báo cáo tài chính cuối kỳ có thể dùng pipeline riêng và đối soát thay vì nối trực tiếp ba OLTP databases.

### Quy tắc cho API đồng bộ

- Cung cấp operation đúng ngữ nghĩa như `ReserveStock`, không chỉ một API `PATCH /stock_quantity` tùy ý.
- Owner kiểm tra quyền, idempotency và bất biến; consumer không tự quyết định thay owner.
- Có timeout/circuit breaker và phân biệt **thất bại đã biết** với **kết quả chưa biết vì timeout**.
- Không kéo dài một transaction DB trong khi đợi mạng nếu có cách phân ranh giới tốt hơn.
- Khi một request cần gọi nhiều dịch vụ, thiết kế rõ độ sẵn sàng và fallback: stale catalog label có thể được chấp nhận, nhưng stale inventory availability **không** được dùng để xác nhận giữ hàng thành công.

## 7. Dữ liệu dẫn xuất có thể sao chép, nhưng không được trở thành nguồn sự thật thứ hai

Ordering thường cần hiển thị tên sản phẩm, ảnh và nhóm hàng trong trang đơn. Nếu mỗi request đều JOIN trực tiếp `catalog.product` hoặc gọi API cho mọi dòng, hệ thống dễ tăng coupling và độ trễ.

Giải pháp: Ordering giữ `catalog_product_projection` (read model), nhận dữ liệu từ Catalog qua integration event hoặc cơ chế đồng bộ theo hợp đồng.

~~~text
Catalog (authoritative):
  product_id = P-108
  display_name = "Tai nghe không dây"
  catalog_version = 12
  sellable = true

Ordering local projection (derived):
  product_id = P-108
  display_name = "Tai nghe không dây"
  catalog_version = 12
  sellable = true
  applied_at = 2026-11-22T01:00:00Z
~~~

Trên trang quản trị, giá trị trong projection có thể trễ so với Catalog. Điều đó phải được xem là **đặc tính nhất quán**, không phải một lỗi bất ngờ.

Nhưng khi người dùng đặt mua, **giá và chính sách bán phải được chốt theo quy trình có thẩm quyền**, còn lượng hàng thực có thể giữ do Inventory quyết định. Không nên dựa vào `sellable = true` trong projection đã trễ để khẳng định Inventory đã giữ hàng.

### Phân biệt “bản sao” và “sự thật riêng”

| Trường trong Ordering | Ai chịu trách nhiệm? | Cách cập nhật đúng |
| --- | --- | --- |
| `product_display_name_current` | Catalog; Ordering chỉ giữ projection. | Nhận ProductChanged/refresh từ Catalog. |
| `agreed_product_name_at_order` | Ordering giữ thông tin đã trình bày/chốt trong đơn. | Ghi một lần theo snapshot giao dịch và chính sách sửa sai. |
| `agreed_unit_price_minor` | Ordering theo báo giá/điều kiện được chấp nhận. | Không tự ghi đè khi giá Catalog đổi. |
| `stock_reserved` | Inventory xác nhận reservation, Ordering phản ánh kết quả. | Dựa trên reservation ID và trạng thái owner công bố. |
| `payment_confirmed` | Payment xác nhận từ nguồn thanh toán. | Chỉ phản ánh sự kiện xác nhận đã được chấp nhận. |

**Một giá trị có thể trông giống nhau mà thuộc những sự thật khác nhau.** Tên hiện hành là projection; tên đã chốt là bằng chứng của giao dịch. Nhận diện này tránh sai lầm cập nhật dữ liệu lịch sử khi dữ liệu master thay đổi.

## 8. Tham chiếu xuyên dịch vụ: ID bền vững thay cho FK xuyên DB

Trong một database quan hệ, FK đảm bảo khóa cha tồn tại và hỗ trợ xử lý ràng buộc. Nhưng hai database/shard thuộc hai dịch vụ độc lập thường **không có một FK giao dịch được DBMS bảo vệ xuyên biên**.

Thiết kế tham chiếu phải chuyển từ “có FK sang bảng bên kia” thành **hợp đồng định danh + kiểm tra tại điểm ra quyết định + đồng bộ trạng thái vòng đời**.

### Định danh và namespace

Một `product_id` phải đủ ổn định trong phạm vi được công bố. Nếu ID chỉ duy nhất trong tenant, reference cần chứa `tenant_id + product_id`. Nếu ID chỉ duy nhất trong hệ nguồn, cần thêm namespace. Không dùng tên sản phẩm hoặc email làm FK nghiệp vụ nếu chúng có thể đổi.

Ví dụ bảng Ordering:

~~~sql
CREATE TABLE ordering.customer_order (
    tenant_id        UUID NOT NULL,
    order_id         UUID NOT NULL,
    customer_id      UUID NOT NULL,
    placed_at        TIMESTAMPTZ NOT NULL,
    status           VARCHAR(24) NOT NULL,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE ordering.order_line (
    tenant_id         UUID NOT NULL,
    order_id          UUID NOT NULL,
    line_no           INTEGER NOT NULL CHECK (line_no > 0),
    product_id        UUID NOT NULL,
    agreed_unit_minor BIGINT NOT NULL CHECK (agreed_unit_minor >= 0),
    currency          CHAR(3) NOT NULL,
    quantity          NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    product_name_at_order TEXT NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.customer_order(tenant_id, order_id)
);
~~~

- FK **nội bộ Ordering** giữa `order_line` và `customer_order` phù hợp vì cùng owner và cùng DB transaction.
- `product_id` là **external business reference** đến Catalog, không có FK trực tiếp sang `catalog.product`. Việc tham chiếu hợp lệ phải được kiểm tra theo hợp đồng và quy tắc chốt đơn.
- `product_name_at_order` và `agreed_unit_minor` là **thuộc tính đã chốt** của dòng đơn. Chúng không phải projection cần giữ đồng bộ từng lần thay tên/giá Catalog.

Nếu Catalog ngừng công bố sản phẩm, Ordering thường **không được xóa các dòng đơn lịch sử**. Chủ sở hữu cần event/status/tombstone để Ordering biết không tiếp nhận đơn mới với mã đó, trong khi vẫn có thể trình bày chứng từ cũ theo policy.

### Khi cần nhất quán mạnh

Nếu business invariant là “mỗi ghế chỉ bán một lần”, **không đủ** để Ordering đọc một snapshot ghế còn trống rồi tự chèn hàng. Reservation phải được owner ghế chấp nhận atomically với khóa/unique/concurrency control tại nơi sở hữu tập ghế.

Nếu cần uniqueness email toàn hệ thống, phải có một owner của danh tính/registry. Hai dịch vụ cùng kiểm tra `SELECT NOT EXISTS` ở hai database rồi tạo email độc lập có thể cùng thành công.

## 9. Ví dụ luồng ghi: Booking không tự cập nhật tồn kho hoặc Payment

~~~mermaid
sequenceDiagram
    participant U as Client
    participant O as Ordering
    participant I as Inventory
    participant P as Payment
    U->>O: PlaceOrder(request_id, lines)
    O->>O: Ghi Order PENDING với idempotency
    O->>I: ReserveStock(reservation_key, items)
    I->>I: Kiểm tra tồn và giữ tại owner
    I-->>O: ReservationConfirmed(reservation_id)
    O->>P: RequestCapture(payment_key, amount)
    P-->>O: PENDING / request accepted
    Note over O,P: Timeout không chứng minh capture thất bại
    P-->>O: PaymentCaptured(ref, amount) khi đã xác nhận
    O->>O: Chuyển Order CONFIRMED theo hợp đồng
~~~

Mỗi dịch vụ ghi dữ liệu mà mình sở hữu:

- Ordering ghi trạng thái của Order và receipt của `request_id`.
- Inventory ghi reservation và tồn khả dụng với `reservation_key` idempotent.
- Payment ghi ý định thu, kết quả từ provider và lịch sử đối soát với `payment_key`.

Nếu giữ hàng thất bại, Order có thể chuyển `REJECTED`. Nếu Payment thất bại, Ordering có thể yêu cầu giải phóng reservation. Nếu Payment **timeout**, cần đối soát trạng thái với provider trước khi quyết định có nên retry/compensate; không gửi một lệnh capture mới thiếu idempotency key và giả định lần trước chắc chắn thất bại.

**Điểm quan trọng:** các bước này không cùng một ACID transaction. Nếu yêu cầu nghiệp vụ không chấp nhận trạng thái trung gian, phải xem lại ranh giới nguồn sự thật, giao thức giao dịch phân tán hoặc cách quản lý reservation. Không gắn nhãn “Saga” rồi coi mọi bất biến đã được đảm bảo.

## 10. Phát integration event: hợp đồng nghiệp vụ khác bản ghi CDC

Một domain owner có thể công bố những sự kiện có ý nghĩa rõ cho consumer.

Ví dụ Catalog đổi thông tin một sản phẩm:

~~~json
{
  "event_id": "ff6c6a7a-7726-4dca-9a04-4ea32c28d219",
  "event_type": "CatalogProductChanged",
  "schema_version": 2,
  "tenant_id": "00000000-0000-4000-8000-000000000001",
  "product_id": "d3b37c4f-0e7c-4407-bdf8-6bc9c108c65a",
  "aggregate_version": 17,
  "occurred_at": "2026-11-20T10:05:00Z",
  "recorded_at": "2026-11-20T10:05:02Z",
  "payload": {
    "display_name": "Tai nghe không dây",
    "category_code": "AUDIO",
    "sellable": true
  }
}
~~~

**Hợp đồng ví dụ:** event là **full-state cập nhật các trường Catalog đã công bố** ở aggregate version 17. `aggregate_version` tăng theo một product stream, không phải số version của schema hay thứ tự toàn hệ thống. Nếu event chỉ chứa **delta** so với version trước, consumer phải xử lý khác: không được bỏ qua version 16 rồi áp patch 17.

Một event dành cho integration cần tài liệu hóa:

| Thành phần | Quy tắc |
| --- | --- |
| **Điểm chốt** | Khi Catalog commit thay đổi đã được chấp nhận. |
| **Identity** | `tenant_id + product_id` xác định thực thể; `event_id` xác định sự kiện. |
| **Version** | `schema_version` của thông điệp, `aggregate_version` của product. |
| **Dữ liệu** | Chỉ trường consumer được phép nhận; không lộ cột nội bộ hoặc thông tin bí mật. |
| **Thời gian** | `occurred_at` và `recorded_at` có ý nghĩa rõ. |
| **Lặp/đến trễ** | Consumer idempotent, có chính sách out-of-order. |
| **Xóa/ngừng công bố** | Event hoặc trạng thái tombstone, không chỉ ngừng phát thông tin. |
| **Tương thích** | Reader cũ/mới được hỗ trợ theo policy; có thử nghiệm contract. |

### Domain event, integration event và CDC không đồng nhất

- **Domain event:** sự việc có ý nghĩa trong miền Catalog, được phát theo quy tắc nghiệp vụ nguồn.
- **Integration event:** thông điệp Catalog chủ động công bố cho các consumer; có thể gom/tách/ẩn trường và version riêng.
- **CDC:** bản thay đổi lưu trữ như UPDATE một hàng Catalog; thường chứa cấu trúc bảng/cột và log position, không tự giải thích lý do nghiệp vụ.

Có thể dùng CDC làm cơ chế vận chuyển outbox hoặc pipeline phân tích, nhưng **không biến mọi thay đổi một cột thành hợp đồng nghiệp vụ công khai**. Nếu owner đổi schema vật lý, consumer integration không nên bị buộc đổi logic chỉ vì một cột nội bộ đã bị tách đôi.

## 11. Transactional outbox: giữ nhất quán giữa dữ liệu owner và ý định công bố

Một lỗi phổ biến:

~~~text
1. UPDATE catalog.product
2. COMMIT
3. publish CatalogProductChanged
~~~

Nếu ứng dụng chết giữa bước 2 và 3, Catalog đã đổi nhưng consumer không biết. Nếu phát trước commit và transaction bị rollback, consumer lại tin một thay đổi chưa được chấp nhận.

**Transactional outbox** giải quyết khoảng trống này bằng cách ghi dữ liệu nghiệp vụ và **bản ghi ý định công bố** trong cùng local transaction.

~~~sql
CREATE TABLE catalog.outbox_event (
    event_id           UUID PRIMARY KEY,
    tenant_id          UUID NOT NULL,
    aggregate_id       UUID NOT NULL,
    aggregate_version  BIGINT NOT NULL CHECK (aggregate_version > 0),
    event_type         VARCHAR(120) NOT NULL,
    schema_version     SMALLINT NOT NULL CHECK (schema_version > 0),
    payload            JSONB NOT NULL
                       CHECK (jsonb_typeof(payload) = 'object'),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at       TIMESTAMPTZ,
    UNIQUE (tenant_id, aggregate_id, aggregate_version, event_type)
);

CREATE INDEX ix_catalog_outbox_pending
    ON catalog.outbox_event (created_at, event_id)
    WHERE published_at IS NULL;
~~~

Ví dụ thao tác logic:

~~~text
BEGIN TRANSACTION TẠI CATALOG
  - kiểm tra quyền, product_version và bất biến
  - UPDATE catalog.product với expected_version
  - INSERT catalog.outbox_event cùng aggregate_version đã commit
COMMIT

RELAY / CDC OUTBOX
  - đọc event đã commit
  - gửi message đến broker, có thể gửi lại sau lỗi
  - ghi nhận tình trạng publish theo giao thức đã chọn
~~~

Outbox giúp bảo đảm **ý định công bố không bị mất giữa commit và publish** với giả định cơ chế lưu/relay được vận hành đúng. Nó **không bảo đảm exactly-once end-to-end**: relay có thể gửi xong nhưng chết trước khi cập nhật `published_at`, khiến message được gửi lại.

Consumer phải chống lặp; nếu consumer thực hiện một tác động khác như gọi API thanh toán, cần thêm idempotency ở **chính thao tác đó**. Không lấy một dòng outbox đã commit làm bằng chứng dịch vụ đích đã áp dụng thành công.

## 12. Consumer đọc bản dẫn xuất: chống lặp, phiên bản và consistency

Ví dụ Ordering duy trì một projection Catalog để hiển thị nhanh.

~~~sql
CREATE TABLE ordering.catalog_product_projection (
    tenant_id          UUID NOT NULL,
    product_id         UUID NOT NULL,
    display_name       TEXT NOT NULL,
    category_code      VARCHAR(64) NOT NULL,
    sellable           BOOLEAN NOT NULL,
    catalog_version    BIGINT NOT NULL
                       CHECK (catalog_version > 0),
    projected_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, product_id)
);

CREATE TABLE ordering.processed_integration_event (
    consumer_name  VARCHAR(120) NOT NULL,
    event_id       UUID NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Một consumer xử lý `CatalogProductChanged` theo hợp đồng full-state:

1. Bắt đầu transaction **trong database Ordering**.
2. Thử INSERT `(consumer_name, event_id)` vào bảng receipt. Nếu event đã được nhận trong một transaction đã commit, không áp dụng lại.
3. Đọc phiên bản `catalog_version` hiện tại. Nếu bản tin có version cao hơn, upsert các trường đã công bố; nếu thấp hơn, bỏ qua bản cũ.
4. Nếu version **bằng nhau nhưng payload khác**, ghi nhận conflict/điều tra; không “last message wins”.
5. Commit receipt và projection **cùng transaction**. Chỉ sau đó xác nhận đã xử lý message phù hợp với broker.

SQL cập nhật state (chỉ chạy khi bước receipt chứng minh đây là lần xử lý mới và payload đã được kiểm tra):

~~~sql
INSERT INTO ordering.catalog_product_projection (
    tenant_id, product_id, display_name,
    category_code, sellable, catalog_version
)
VALUES (
    :tenant_id, :product_id, :display_name,
    :category_code, :sellable, :catalog_version
)
ON CONFLICT (tenant_id, product_id)
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    category_code = EXCLUDED.category_code,
    sellable = EXCLUDED.sellable,
    catalog_version = EXCLUDED.catalog_version,
    projected_at = now()
WHERE ordering.catalog_product_projection.catalog_version
      < EXCLUDED.catalog_version;
~~~

**Điều kiện quan trọng:** ví dụ này chỉ phù hợp khi bản tin chứa **đủ full-state** cho các trường projection. Nếu Catalog phát **patch**, consumer phải xử lý version liền nhau hoặc lấy snapshot nguồn để bù phần thiếu. Gặp message version 19 trước 18 mà chỉ có `{"category_code":"AUDIO"}` không thể tự suy các trường còn lại.

### Độ mới của bản dẫn xuất

Projection có thể trễ vài giây hoặc vài phút. Hãy xác định:

- SLA/SLO `projection_lag` theo use case.
- Cách làm mới/bắt kịp khi consumer dừng lâu hoặc message không còn ở broker.
- Cách nhận biết dữ liệu chưa đủ khi chưa từng nhận event tạo sản phẩm.
- Tại các quyết định mạnh như reservation/khóa tài khoản, **không** coi cache hiện hành là bằng chứng bất biến tại owner đã được đảm bảo.
- Khi có yêu cầu “đọc kết quả vừa ghi”, có thể dùng response từ command owner, session/version token hoặc chờ projection đến đúng `aggregate_version` với timeout.

### Không phục hồi dữ liệu đã bị xóa bằng message cũ

Nếu Catalog phát `ProductRetired` ở version 20, projection nên giữ **tombstone/`sellable=false` và version 20** theo policy, để một bản `CatalogProductChanged` version 19 đến muộn không làm sản phẩm lại bán được.

Điều này không đồng nghĩa giữ mọi thông tin cá nhân vô thời hạn: tombstone có thể chỉ giữ ID/phiên bản tối thiểu, cần tuân thủ chính sách retention và quyền truy cập.

## 13. Ràng buộc xuyên dịch vụ và transaction: giữ quyết định ở đúng owner

Khi nghiệp vụ cần tác động đến nhiều nguồn sự thật, câu hỏi không còn là “JOIN hai bảng thế nào” mà là “bất biến nào phải đúng ngay, ở đâu?”.

| Bất biến/quyết định | Owner | Biện pháp cốt lõi |
| --- | --- | --- |
| Ghế không bán hai lần | SeatInventory | Unique/lock/reservation theo `(show_id, seat_id)` trong một điểm nhất quán. |
| Không cấp vượt số lượng tồn | Inventory | Atomic reservation/update với kiểm tra số lượng còn khả dụng. |
| Một request đặt hàng không tạo hai đơn | Ordering | Unique/idempotency key và transaction tạo Order. |
| Không capture hai lần cho cùng yêu cầu | Payment + provider | Idempotency key ổn định, lưu receipt/đối soát kết quả. |
| Đơn chỉ `CONFIRMED` khi đã đủ điều kiện | Ordering | State machine dựa trên xác nhận Inventory và Payment có ID tham chiếu. |
| Khách không được mở tài khoản trùng định danh toàn cục | Customer Identity | Registry/unique ở chủ sở hữu danh tính, không kiểm tra rời rạc. |

Một `FOREIGN KEY` xuyên hai database **không phải cơ chế điều phối phổ quát**. Nếu có yêu cầu nhất quán mạnh xuyên nhiều nguồn, cân nhắc:

- **Đặt dữ liệu cần atomic cùng một owner/transaction** nếu ranh giới hiện tại bị chia sai.
- **Reservation/escrow** để một owner xác nhận quyền sử dụng tài nguyên trước khi consumer tiến tiếp.
- **Distributed transaction/2PC** khi các participant hỗ trợ và atomic commit thực sự cần thiết; phải xử lý coordinator crash/lock treo và isolation.
- **Saga** khi quy trình có thể dùng các local transaction với trạng thái trung gian, retry và compensation.
- **Outbox/inbox** để chuyển các sự việc đã commit tới dịch vụ khác một cách có thể khôi phục.

### Saga không phải phép rollback đồng thời

~~~mermaid
flowchart TD
    A["Order PENDING"] --> B["Inventory.reserve"]
    B --> C{"Đã giữ hàng?"}
    C -->|"Không"| X["Order REJECTED"]
    C -->|"Có"| D["Payment.requestCapture"]
    D --> E{"Kết quả có thẩm quyền?"}
    E -->|"Captured"| F["Order CONFIRMED"]
    E -->|"Failed"| G["Inventory.release đúng reservation"]
    G --> H["Order FAILED"]
    E -->|"Timeout / unknown"| I["Order PENDING_RECONCILIATION"]
    I --> J["Đối soát provider và reservation"]
    J --> E
~~~

Một capture đã thành công **không thể rollback bằng `ROLLBACK` ở Ordering**. Nếu nghiệp vụ phải hoàn tiền, đó là một thao tác bù trừ mới có thể thất bại, đến muộn hoặc cần xác minh. Cần mô hình rõ các trạng thái đang chờ, đã xác nhận và cần can thiệp thủ công.

Trong data modeling, điều này dẫn đến các bảng/state riêng cho `reservation_id`, `payment_attempt_id`, `saga_id`, `idempotency_key` và lịch sử từng bước. Không dùng mỗi `orders.status` một chuỗi để thay toàn bộ bằng chứng liên dịch vụ.

## 14. Thay đổi schema và hợp đồng mà không bắt tất cả service cùng deploy

Một ranh giới tốt cho phép owner thay cấu trúc lưu trữ trong phạm vi của mình mà **không phá consumer**.

### Ba thay đổi cần phân biệt

1. **Internal schema change:** Catalog tách `product.description` thành nhiều bảng nội bộ. Consumer không cần biết nếu API/event vẫn giữ hợp đồng cũ.
2. **Contract schema change:** Catalog thêm trường `category_code` vào `CatalogProductChanged.v2`. Cần kiểm tra reader cũ có cho phép trường mới không, reader mới xử lý event v1 thiếu trường thế nào.
3. **Semantic change:** trước đây `available` là “có trong catalog”, nay đổi thành “Inventory xác nhận còn hàng”. Đây là đổi **nguồn có thẩm quyền và nghĩa nghiệp vụ**, không chỉ rename field; cần thiết kế contract và owner mới cho thông tin tồn.

### Quy trình versioning an toàn

- **Kiểm kê consumer** và hợp đồng họ đang dùng; đừng dựa vào việc các team “có lẽ không dùng cột này”.
- Xác định `event_type`, `schema_version`, field required/optional, enum, unit, timestamp và semantic description.
- Triển khai **reader hiểu cả version cũ và mới** hoặc adapter/upcaster hợp lệ trước khi writer đổi, khi kiến trúc cho phép.
- Với thay đổi breaking, có thể công bố **contract v2 song song** trong thời gian chuyển và đảm bảo consumer không xử lý hai biểu diễn của cùng sự việc như hai sự kiện nghiệp vụ khác nhau.
- Kiểm thử **consumer-driven contracts** và replay dữ liệu lịch sử. Không tự điền giá trị cũ không tồn tại bằng default làm sai ý nghĩa.
- Công bố lịch deprecation và cơ chế theo dõi consumer còn dùng v1; không xóa decoder v1 nếu event lịch sử còn cần replay.

**Không coi API version và database schema version là cùng một con số.** API v2 có thể chạy trên schema lưu trữ mới mà không thay đổi event đã phát. Ngược lại, thay đổi định nghĩa KPI báo cáo có thể cần metric/projection version riêng dù API JSON không đổi.

## 15. Tách bảng dùng chung theo từng bước thay vì “big bang”

Giả sử nhiều service đang dùng chung `public.product` và đội ngũ muốn đưa Catalog về quyền sở hữu chính thức.

### Giai đoạn A — Kiểm kê phụ thuộc

1. Tìm các đường **SELECT/INSERT/UPDATE/DELETE** vào bảng; bao gồm job nền, báo cáo, stored procedure, trigger, export, test và công cụ hỗ trợ.
2. Xác định **chủ sở hữu sự thật** của từng nhóm cột. `product_name` có thể thuộc Catalog, còn `stock_quantity` nên thuộc Inventory; một bảng chung đôi khi đang trộn **hai miền khác nhau**.
3. Lập bản đồ khóa và FK, truy vấn JOIN xuyên miền, mức nhất quán cần giữ, quyền tài khoản DB và tần suất cập nhật.
4. Đánh dấu các trường được dùng để chốt giao dịch; không thay thế chúng ngay bằng cache bất đồng bộ nếu điều đó phá bất biến.

### Giai đoạn B — Thiết kế đích và hợp đồng

1. Tạo schema/bảng đích cho từng owner với business key ổn định.
2. Catalog công bố API cho các câu hỏi và event cho các thay đổi đã commit; Inventory công bố reservation command/result.
3. Thiết kế projection cho consumer cần đọc nhanh; giữ lineage/`source_version` và tombstone.
4. Định nghĩa cách tiếp nhận thay đổi cũ, dedup và xử lý các bản ghi xung đột khi backfill.

### Giai đoạn C — Chuyển từng luồng ghi

- **Chọn một owner ghi tại một thời điểm**, giảm tình trạng một cột bị ghi song song từ hai nguồn.
- Có thể dùng facade/adapter hoặc chuyển request tới owner mới trong giai đoạn chuyển.
- Nếu cần đồng bộ từ bảng legacy, dùng outbox/CDC có checkpoint và **cursor theo commit** được bảo đảm. Không dùng ID sequence cấp trước commit làm watermark chắc chắn.
- Đảm bảo việc copy lần đầu và theo dõi thay đổi diễn ra không bỏ sót các transaction commit trong khoảng chuyển.

### Giai đoạn D — Chuyển đường đọc

- Xây projection/read API mới song song với đường đọc legacy.
- Kiểm chứng số business key, trạng thái bản ghi, số phiên bản, các case soft delete, quyền truy cập, dữ liệu giữa tenant và độ trễ.
- Chuyển từng consumer sang contract mới, theo dõi lỗi/latency/drift và chuẩn bị rollback rõ ràng.
- Chỉ sau khi không còn consumer hợp lệ cần bảng legacy mới **thu hồi quyền DB** và hoàn tất trách nhiệm migration.

~~~mermaid
flowchart LR
    LEG[("Bảng product legacy dùng chung")] --> COPY["Backfill + CDC theo commit"]
    COPY --> CAT[("Catalog schema: owner mới")]
    CAT --> EVT["API / Outbox / Integration event"]
    EVT --> PROJ[("Ordering local projection")]
    PROJ --> CUT["Cutover đường đọc Ordering"]
    LEG -. "Theo dõi drift đến khi kết thúc" .-> CUT
~~~

**Tránh dual write thiếu kiểm soát.** Nếu ứng dụng gửi hai lệnh ghi độc lập tới Legacy và Catalog rồi coi cả hai là thành công khi chỉ một nơi commit, sẽ có hai nguồn sự thật bất đồng. Nếu buộc phải dual-write, cần protocol cụ thể về owner, idempotency, failure recovery và điều kiện chốt; giải pháp an toàn hơn thường là **một đường ghi có thẩm quyền** và một đường đồng bộ dẫn xuất.

### Bẫy migration: mixed ownership theo cột

Có lúc `public.product.stock_quantity` chỉ là bản sao từ Inventory, trong khi Catalog vẫn sở hữu các cột tên/nhóm hàng. Chuyển toàn bộ bảng sang Catalog và cho Catalog tự quyết định tồn kho sẽ làm bất biến của Inventory biến mất. Nên tách **sự thật và owner theo ý nghĩa**, kể cả khi việc tách khiến bảng vật lý phải thay đổi lớn.

## 16. Quan sát tính đúng đắn: không chỉ đo độ trễ API

Một mô hình ranh giới có thể chạy nhanh nhưng dữ liệu sai vì consumer bỏ sự kiện hoặc hai service cùng ghi.

| Metric/kiểm chứng | Câu hỏi | Hành động khi sai |
| --- | --- | --- |
| **Unauthorized cross-schema writes** | Runtime nào đang thử ghi bảng không sở hữu? | Chặn bằng quyền và điều tra đường gọi. |
| **Catalog projection lag** | Consumer trễ bao lâu và đến product version nào? | Retry, backfill, so nguồn và giới hạn hiển thị nếu cần. |
| **Event dedup rate** | Bao nhiêu message bị phát/nhận lặp? | Bảo đảm idempotency, theo dõi relay. |
| **Out-of-order/gap count** | Có nhận version 18 trước 17 hoặc patch bị thiếu không? | Tạm giữ/refresh snapshot; không áp patch sai. |
| **Source-projection drift** | Các trường Catalog đã công bố có khớp projection tại cùng mốc? | Reconcile và rebuild phần ảnh hưởng. |
| **Orphan external references** | OrderLine trỏ product không còn biết đến hay không? | Điều tra missing/deleted/backfill; giữ chứng từ cũ. |
| **Saga pending age** | Có đơn chờ đối soát, giải phóng, hoàn tiền quá lâu? | Workflow recovery và cảnh báo. |
| **Idempotency conflict** | Cùng business request ID nhưng payload khác nhau? | Từ chối/điều tra, không âm thầm chọn last write. |
| **Schema contract breakage** | Reader cũ có xử lý được message mới theo policy? | Contract test, canary, rollback/dual publish. |
| **Data access audit** | Ai truy vấn dữ liệu nhạy cảm ngoài phạm vi? | Rà soát quyền, thu hồi và xử lý sự cố. |
| **Cross-service synchronous dependency** | Một API request gọi dây chuyền bao nhiêu owner? | Batching/caching đúng ngữ nghĩa, giảm fan-out. |
| **Consumer freshness SLO** | Có đáp ứng kỳ vọng của màn hình/báo cáo? | Công bố độ trễ, điều chỉnh architecture hoặc SLO. |

### Tình huống lỗi phải diễn tập

- Catalog commit thay tên rồi relay chết trước khi publish: sự kiện outbox có được gửi lại và consumer có thể rebuild không?
- Ordering nhận `CatalogProductChanged v19` trước v18: full-state có cho phép bỏ qua v18 không? Nếu patch thì làm sao bù?
- API Inventory timeout nhưng reservation thực ra đã thành công: retry với key nào và xác nhận bằng nguồn nào?
- Customer bị xóa mềm nhưng CRM projection vẫn hiển thị tên: quy trình xử lý dữ liệu dẫn xuất hoạt động thế nào?
- Hai worker đồng thời xử lý cùng `event_id`: receipt và projection có cùng transaction không?
- Team deploy migration thay enum Catalog: consumer version cũ có lỗi parse hay hiểu sai trạng thái không?

**Không đủ chỉ đo success rate của HTTP 200**. Một hệ thống có thể luôn trả 200 nhưng phản ánh dữ liệu đã cũ, cộng doanh thu hai lần hoặc vi phạm bất biến tồn kho.

## 17. Phân quyền, tenant isolation và vòng đời dữ liệu xuyên ranh giới

Quyền sở hữu đi kèm trách nhiệm bảo vệ dữ liệu:

1. **Least privilege:** runtime chỉ có quyền trên dữ liệu của nó và hợp đồng đọc được cấp. Tài khoản quản trị/migration tách khỏi runtime.
2. **Tenant scope:** ID, query, event và projection phải mang khóa tenant khi nghiệp vụ phân vùng theo tenant; kiểm tra cả tầng API và tầng DB. Shared schema không phải lý do bỏ kiểm tra chéo tenant.
3. **PII minimization:** không công bố email, địa chỉ, số giấy tờ trong mọi integration event chỉ để consumer “có sẵn”. Chỉ trường hợp cần mới truyền dữ liệu có phân quyền.
4. **Retention/erasure:** owner chịu trách nhiệm quy trình nguồn, còn consumer phải có cơ chế xóa/ẩn danh dữ liệu dẫn xuất theo hợp đồng. Một event `CustomerErasureRequested` không phải `ErasureCompleted` nếu downstream chưa hoàn tất.
5. **Bản sao ẩn:** read model, search index, cache, export, analytics, backup và message archive có thể giữ dữ liệu sau khi master đã đổi hoặc bị xóa.
6. **Data lineage:** biết trường nào lấy từ owner nào, theo event/schema version nào, và làm sao xác minh tính đúng khi có tranh chấp.
7. **Residency và audit:** nếu dữ liệu bị giới hạn lưu trú theo khu vực, kiểm tra cả nơi consumer, broker và backups; quyền truy vấn/debug cũng là quyền truy cập dữ liệu.

### Không dùng sự kiện bất biến như kho PII không giới hạn

Nếu một event được giữ dài hạn để có thể replay, hãy cân nhắc **opaque ID**, tham chiếu tới kho danh tính được quản trị, mã hóa theo chính sách và giới hạn payload nhạy cảm. Việc giữ lịch sử không miễn trừ chính sách xóa/ẩn danh hợp lệ; một số cơ chế giảm dữ liệu nhạy cảm có thể giới hạn khả năng replay và cần được công bố.

**Sự thật nghiệp vụ không nhất thiết bằng dữ liệu định danh chi tiết.** Ordering có thể giữ `customer_id` và thông tin giao hàng đã chốt theo nghĩa vụ hợp đồng, nhưng không cần sao chép toàn bộ hồ sơ Customer Identity vào mỗi event.

## 18. So sánh hướng tiếp cận quan hệ, document, graph và analytics

Tách ownership khỏi hình thức lưu trữ; cùng một ranh giới nghiệp vụ có thể dùng nhiều công nghệ.

| Mô hình/hệ lưu | Cách thực thi ownership | Cạm bẫy khi tích hợp |
| --- | --- | --- |
| **Quan hệ** | Schema/DB riêng theo owner; FK, unique, transaction nội bộ; published view/API. | JOIN/FK trực tiếp xuyên domain biến schema thành contract ngầm. |
| **Document** | Service sở hữu collection/document aggregate; consumer giữ projection phù hợp. | Nhúng document của owner khác rồi sửa cục bộ khiến hai bản diverge; query thiếu shard key gây fan-out. |
| **Graph** | Service sở hữu nodes/edges trong một miền; global graph được dẫn xuất theo hợp đồng. | Traversal xuyên owner, ID không ổn định, cạnh cũ sau xóa/đổi quan hệ. |
| **Event store** | Owner append các sự việc miền, công bố integration events có version. | Consumer nhầm event nội bộ với contract bên ngoài hoặc replay gây side effect. |
| **Analytics/warehouse** | Data product được công bố với grain, metric, lineage và owner; ingestion có hợp đồng. | CDC được hiểu sai là domain event, join nhiều fact sai grain, số liệu không cùng watermark. |

Data warehouse có thể đọc dữ liệu từ nhiều owner vì mục đích phân tích, **nhưng không nên trở thành nơi âm thầm chỉnh sửa giá trị nguồn rồi đẩy ngược về OLTP** nếu chưa có command/approval của owner. Một bảng dimension `dim_customer` có thể phục vụ phân tích mà không được nhận quyền sửa hồ sơ khách trong Customer Identity.

Một **global graph** dùng để tìm quan hệ gian lận có thể tạo từ các node/edge của nhiều dịch vụ. Khi đó chủ sở hữu graph chịu trách nhiệm phép suy luận và freshness, còn quyền xác nhận giao dịch và thay đổi khách vẫn thuộc các source owners.

## 19. Ma trận quyết định và Architecture Decision Record

Khi có yêu cầu mới, chọn cách tích hợp bằng các câu hỏi cụ thể:

| Câu hỏi | Nếu câu trả lời là… | Phương án xem xét |
| --- | --- | --- |
| Cần owner quyết định ngay để giữ invariant? | Có, như giữ ghế hoặc duyệt hạn mức. | Command/API tới owner với concurrency và idempotency. |
| Cần dữ liệu phục vụ màn hình, trễ có giới hạn? | Có, như tên/nhóm sản phẩm. | Integration event + local projection/cache. |
| Cần báo cáo xuyên miền và lịch sử nhiều năm? | Có, và không yêu cầu OLTP realtime. | Analytical pipeline/data product, hợp đồng grain và đối soát. |
| Consumer có thực sự cần cột vật lý của owner? | Không, chỉ cần nghiệp vụ. | Published API/event contract, không mở table access. |
| Bắt buộc đọc trực tiếp trong giai đoạn chuyển? | Có, có thời hạn và owner kiểm soát. | Published view read-only, quyền tối thiểu, lịch loại bỏ. |
| Cần thay đổi nhiều nguồn cùng một nghiệp vụ? | Có, không thể co-locate. | Saga/2PC theo yêu cầu atomicity, kiểm tra khả năng bù trừ. |
| Nguồn có thể bị xóa/ngừng hiệu lực? | Có. | Lifecycle events/tombstone và erasure propagation. |

### ADR mẫu rút gọn

**Bối cảnh:** Ordering đang JOIN trực tiếp bảng `catalog.product` để hiển thị tên sản phẩm. Đội Catalog cần đổi schema và chuyển hệ quản trị; đường đọc Ordering có P95 cao khi Catalog chịu tải.

**Quyết định:** Catalog sở hữu tên/phân loại/trạng thái công bố; Ordering nhận `CatalogProductChanged` full-state có `aggregate_version` và lưu read projection. Ordering giữ riêng tên/giá **đã chốt theo dòng đơn**. Đường đặt hàng vẫn kiểm tra điều kiện giao dịch ở owner thích hợp, không coi projection là quyết định giữ tồn kho.

**Đánh đổi:** chấp nhận độ trễ projection có SLO và cơ chế backfill; đổi lại giảm JOIN trực tiếp, giảm coupling migration. Triển khai outbox, inbox dedup, kiểm tra latest version, tombstone và đối soát.

**Phương án không chọn:** trao quyền SELECT vĩnh viễn trên bảng Catalog; sao chép bảng Catalog bằng job không có version/lineage; cho Ordering cập nhật `product.status` để “phản ánh bán được”.

**Điều kiện đánh giá lại:** projection lag vượt mức chấp nhận, lượng event quá lớn, hoặc màn hình thực sự cần dữ liệu mới đến từng mili-giây mà không thể chấp nhận stale. Đánh giá từ workload và SLO, không từ sở thích công nghệ.

## 20. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nhiều service cùng UPDATE một bảng | Bỏ qua bất biến, nguồn sự thật mơ hồ. | Một owner ghi, consumer dùng command/hợp đồng. |
| Chia schema nhưng vẫn cấp tài khoản superuser chung | Ranh giới chỉ tồn tại trên sơ đồ. | Credential và quyền runtime riêng, chặn cross-schema writes. |
| Có quyền SELECT thì coi bảng là API ổn định | Consumer phụ thuộc schema và giá trị nội bộ. | Published query/event contract, kiểm thử và deprecation. |
| Dùng cache để xác nhận giữ hàng | Tồn kho có thể đã đổi. | Quyết định tại Inventory owner với atomic reservation. |
| Update tên/giá trong đơn cũ theo Catalog hiện hành | Thay đổi chứng từ đã chốt. | Phân biệt snapshot giao dịch và projection master hiện hành. |
| Dùng cùng tên `payment_status` ở nhiều service, mỗi nơi tự sửa | Không biết bên nào xác nhận tiền thực. | Payment có thẩm quyền, Ordering phản ánh kết quả có ID nguồn. |
| Coi CDC UPDATE là sự kiện nghiệp vụ đầy đủ | Mất lý do, actor, điểm chốt, ràng buộc. | Contract integration event với ngữ nghĩa rõ. |
| Cập nhật projection rồi mới ghi receipt ở transaction khác | Retry làm áp dụng lặp. | Inbox/dedup và projection cùng transaction. |
| Nhận event cũ rồi “last message wins” | State bị lùi về version cũ. | Version check, gap policy, conflict detection. |
| Phát outbox trước khi commit hoặc không có outbox | Phát sự kiện sai hoặc mất thông báo. | Ghi outbox cùng commit nguồn, relay sau commit. |
| Xóa customer master rồi cascade xóa order/payments | Mất chứng từ và quan hệ đối soát. | Data lifecycle theo chủ sở hữu, retention riêng, pseudonymization có kiểm soát. |
| Dual write sang legacy và new DB rồi bỏ qua lỗi một bên | Hai nguồn sự thật diverge. | Một đường ghi chuẩn, CDC/outbox và migration có mốc chốt. |
| Tách microservice chỉ vì tách bảng | Distributed transaction và latency tăng không cần thiết. | Bounded context/ownership trước, physical split sau. |
| Một dashboard tự JOIN các database production | Coupling, tải OLTP, snapshot không nhất quán. | Data product/analytical mart với lineage và watermark. |
| Nghĩ “eventual consistency” nghĩa là không cần kiểm chứng | Projection mất event mà không ai phát hiện. | Lag, reconciliation, replay, alert và owner rõ. |

## 21. Bài tập thực hành: tách bảng dùng chung trong nền tảng bán vé

**Bối cảnh:** một nền tảng bán vé có bảng dùng chung `public.show_booking` lưu cả tên sự kiện, danh sách ghế, trạng thái đơn, trạng thái thanh toán, email khách và tổng tiền. Các ứng dụng Catalog, Booking, SeatInventory, Payment, Customer Support và Analytics đều truy cập trực tiếp. Khi concert mở bán, hai booking có thể tranh cùng ghế; Payment trả callback chậm/lặp; ban tổ chức sửa tên show; khách yêu cầu thay đổi email hoặc xóa hồ sơ theo chính sách.

### Yêu cầu thiết kế

1. **Lập ownership matrix:** xác định owner cho show name/status, seat availability, booking line, confirmed capture/refund, customer identity và KPI tài chính.
2. **Phân biệt sự thật với bản sao:** show name hiện hành thuộc ai? Tên show đã chốt trên vé thuộc ai? Email hiện hành và email liên hệ của giao dịch có chính sách nào?
3. **Thiết kế khóa:** nêu `tenant_id`, `show_id`, `seat_id`, `booking_id`, `payment_attempt_id`; phạm vi uniqueness và khả năng tái sử dụng ID.
4. **Bất biến ghế:** thiết kế điểm giữ ghế atomically ở SeatInventory, với unique/lock hoặc reservation; chỉ rõ vì sao hai bảng Booking ở hai shard không tự bảo vệ được một ghế.
5. **Quan hệ xuyên dịch vụ:** Booking giữ `show_id` và `seat_reservation_id` như external references; dữ liệu nào cần FK nội bộ và dữ liệu nào cần contract/lifecycle event?
6. **Đọc màn hình:** chọn API đồng bộ hay local projection cho tên show, danh mục chỗ ngồi và trạng thái payment. Với dữ liệu cũ, làm sao biết đã stale?
7. **Write flow:** mô tả Booking PENDING → SeatReserved → PaymentCaptured → CONFIRMED; cách xử lý timeout/unknown outcome và compensation khi giữ ghế hoặc capture thất bại.
8. **Event contract:** viết một `ShowDetailsChanged.v1` có `event_id`, `schema_version`, `aggregate_version`, `occurred_at`, payload; chỉ ra dữ liệu không nên công bố.
9. **Outbox/inbox:** đề xuất bảng/khóa và transaction để cập nhật show rồi phát event; consumer chống lặp và out-of-order thế nào?
10. **Tách shared table:** lập kế hoạch backfill, bắt CDC tail, một owner ghi, shadow read, đối soát, cutover và thu hồi quyền; giải thích vì sao hai write path độc lập nguy hiểm.
11. **Quyền:** thiết kế database roles để runtime Booking không `UPDATE catalog.show` hoặc `payment.capture` được; quyền debug và migration có gì khác?
12. **Retention:** khách bị xóa hồ sơ nhưng Booking và Payment còn nghĩa vụ giữ chứng từ; làm sao phân tách PII và các bản dẫn xuất, xử lý event/cache/backup?
13. **SQL kiểm chứng:** truy vấn xác nhận grain không trùng, đếm orphan external references trong read model, và tìm projection có version nhỏ hơn nguồn tại mốc đối soát.
14. **SLO/giám sát:** nêu ít nhất tám chỉ số về projection lag, retries, conflicts, unauthorized access, saga pending, data drift, lỗi contract và latency.
15. **ADR:** viết một quyết định ngắn nêu owner, contract, mô hình lưu, tính nhất quán, phương án không chọn, lộ trình chuyển và điều kiện đánh giá lại.

### Bảng kiểm tự đánh giá

| Tiêu chí | Thiết kế đạt khi |
| --- | --- |
| **Owner rõ** | Mỗi sự thật nghiệp vụ có nguồn có thẩm quyền và điểm chốt được định nghĩa. |
| **Quyền ghi** | Runtime không thể tự ghi dữ liệu của owner khác. |
| **Khóa/quan hệ** | PK/FK nội bộ và external references có phạm vi/namespace rõ. |
| **Bất biến** | Không bán trùng ghế, không coi yêu cầu thanh toán là đã capture. |
| **Đường tích hợp** | API/event/outbox/read model phù hợp mức nhất quán, có retry và dedup. |
| **Lịch sử** | Chứng từ đã chốt không bị ghi đè theo master hiện hành; xử lý lifecycle rõ. |
| **Migration** | Backfill + catch-up + cutover có đối soát, không hai nguồn ghi độc lập. |
| **Vận hành** | Giám sát drift/lag/contract và có phương án phục hồi khi thông tin thiếu. |
| **Riêng tư** | PII, retention, deletion/tombstone, backup và quyền theo tenant được kiểm soát. |

**Kết luận:** quyền sở hữu dữ liệu là quyết định **ai có quyền xác nhận sự thật và bảo vệ bất biến của nó**, chứ không chỉ là tên schema hay vị trí database. Các dịch vụ không nên coi bảng vật lý của nhau là giao diện công khai không giới hạn. Hãy xác định business key, owner, mốc chốt và hợp đồng; chỉ cho owner sửa dữ liệu chuẩn; dùng API cho quyết định cần thẩm quyền, event/outbox cho truyền sự việc đã commit, projection cho nhu cầu đọc, và quy trình đối soát để quản lý độ trễ hoặc thay đổi. Từ ranh giới ấy, mô hình quan hệ, document, đồ thị và phân tích mới có thể tiến hóa độc lập mà vẫn giải thích được nguồn gốc và tính đúng đắn của dữ liệu.
