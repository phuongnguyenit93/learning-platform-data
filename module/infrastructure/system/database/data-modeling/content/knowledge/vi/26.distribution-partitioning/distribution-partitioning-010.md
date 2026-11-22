# Thiết kế lại ranh giới khi bất biến không thể được bảo vệ hợp lý

Một hệ thống có thể đã phân vùng dữ liệu thành công về dung lượng và độ trễ, nhưng vẫn **không bảo vệ được sự thật nghiệp vụ**: hai shard cùng bán chiếc vé cuối, hai service cùng xác nhận một voucher, hoặc hai khu vực cùng chi từ một ngân sách chung. Mỗi node đều tuân thủ mọi ràng buộc cục bộ, nhưng kết quả toàn hệ thống lại không hợp lệ.

Trong trường hợp này, việc thêm khóa ngoại, transaction cục bộ, retry hay job kiểm tra cuối ngày đôi khi không đủ. Vấn đề thực sự là **dữ liệu tham gia một bất biến không nằm trong cùng ranh giới có thể được cập nhật nhất quán**. Nếu bất biến phải đúng ngay khi một lệnh được chấp nhận, kiến trúc cần xác định rõ **ai có quyền ra quyết định cuối cùng**, dựa trên trạng thái nào và được bảo vệ bằng cơ chế giao dịch nào.

Bài học thuộc chương **Phân tán và phân vùng** của module **DATABASE_DATA_MODELING**. Trọng tâm là chuyển quy tắc nghiệp vụ thành mô hình dữ liệu, khóa, phân vùng, quyền sở hữu và đường ghi hợp lý; đồng thời phân tích cách so sánh cơ sở dữ liệu quan hệ, document, đồ thị và kho phân tích khi cần mở rộng hoặc bảo toàn lịch sử.

> **Nguyên tắc:** Khi một bất biến quan trọng không thể bảo vệ với chi phí hợp lý, hãy xem xét **đổi ranh giới owner, aggregate, shard key hoặc phạm vi cam kết**, thay vì chỉ kiểm tra dữ liệu đã sai rồi sửa sau.

## 1. Bất biến và phạm vi cam kết

**Bất biến (invariant)** là một mệnh đề phải đúng tại thời điểm được định nghĩa trong quy trình nghiệp vụ.

Ví dụ:

- **Tồn kho:** với một warehouse và SKU, số lượng đã giữ không vượt tồn có thể bán.
- **Voucher:** một voucher được đổi tối đa một lần trong phạm vi đã quy định.
- **Đơn hàng:** chỉ được đánh dấu CONFIRMED nếu các dòng hàng cần thiết đã tồn tại và hợp lệ.
- **Đa tenant:** Order của tenant A không được tham chiếu Customer thuộc tenant B.
- **Ngân sách:** tổng số tiền được chấp nhận chi không vượt hạn mức được duyệt.
- **Chuyển tiền:** không được coi một khoản chuyển là hoàn tất nếu một nửa tác động bắt buộc còn thất bại.

Một phát biểu như “không bán vượt tồn kho” chưa đủ để triển khai. Cần làm rõ:

1. Tồn kho **theo SKU và warehouse**, hay tổng tồn toàn mạng lưới?
2. “Bán” tính tại thời điểm khách nhấn nút, lúc đặt chỗ thành công, lúc thanh toán hay khi giao hàng?
3. Đơn hàng chờ thanh toán có **giữ trước** hàng không, trong bao lâu?
4. Các request trùng **operation_id** có được tính lại không?
5. Ai có quyền điều chỉnh tồn kho và hủy reservation?
6. Tại thời điểm nào điều kiện bắt buộc đúng: trước ACCEPTED, tại COMMIT hay sau đối soát?

Phát biểu chính xác hơn:

> Với mỗi bộ (tenant_id, warehouse_id, sku_id), lệnh ReserveStock chỉ được trả ACCEPTED sau khi đã ghi bền vững reservation và cập nhật lượng reserved trong **cùng một ranh giới transaction**, sao cho reserved không vượt on_hand; cùng operation_id không làm phát sinh thêm lượt giữ hàng.

Bất biến như vậy cho phép thiết kế một **aggregate tồn kho** rõ ràng. Nhưng nó chưa đảm bảo điều kiện tổng tồn kho toàn công ty nếu hai warehouse cùng bán một nguồn hàng chung: đó là **bất biến khác**, với phạm vi khác.

### 1.1. Sáu câu hỏi trước khi chọn cơ chế

| Câu hỏi | Ví dụ cần xác nhận |
| --- | --- |
| **Scope** | Duy nhất theo tenant, warehouse, campaign hay toàn doanh nghiệp? |
| **Data set** | Một hàng, một Order và các Line, hay tổng across shards? |
| **Writers** | Chỉ một service, hay API, batch, admin, consumer cùng ghi? |
| **Time** | Phải đúng tại COMMIT hay chấp nhận sai lệch tối đa 5 phút? |
| **Failure** | Nếu mất một node, có được nhận lệnh mới không? |
| **Proof** | PK/FK/CHECK, atomic UPDATE, transaction, registry, escrow hay reconciliation? |

Điều quan trọng là **thời điểm công bố thành công**. Nếu trả cho khách “vé của bạn đã được giữ” trước khi hệ thống có một quyết định atomic, sau đó phát hiện oversell và gửi email xin lỗi, invariant “không hứa hai người cùng một ghế” đã bị vi phạm.

## 2. Phân biệt các ranh giới trong mô hình phân tán

| Ranh giới | Bản chất | Khả năng bảo vệ bất biến |
| --- | --- | --- |
| **Hàng** | Một bản ghi với các cột | CHECK, NOT NULL, atomic UPDATE |
| **Bảng/quan hệ** | Nhiều hàng, khóa và FK | UNIQUE, FK, transaction khi DBMS hỗ trợ |
| **Aggregate nghiệp vụ** | Dữ liệu có chung owner để kiểm tra quy tắc ghi | Được bảo vệ nếu tất cả writer tuân theo owner và transaction |
| **Partition** | Một phần vật lý của bảng theo RANGE/HASH/LIST | Không đồng nghĩa một database độc lập |
| **Shard** | Dữ liệu chia ra nhiều node/database có thể commit độc lập | Transaction cục bộ; xuyên shard cần hỗ trợ hoặc giao thức |
| **Service** | Ranh giới API, quyền sở hữu và triển khai | Không mặc định có transaction xuyên các service |
| **Region** | Vị trí địa lý của bản ghi/bản sao/owner | Có thể có replication lag, failover và split-brain |

Một bảng PostgreSQL được **PARTITION BY HASH** và các partition nằm trong **cùng một database** vẫn có thể tham gia transaction của database đó. Điều này **khác** việc tách sang nhiều database PostgreSQL độc lập: chúng không tự chia sẻ FK, SERIALIZABLE transaction hoặc UNIQUE toàn hệ thống.

**Aggregate không phải là một bảng.** Một Order gồm bảng Order và OrderLine có thể là một aggregate nếu mọi lệnh xác nhận, thêm, sửa, xóa dòng đều đi qua cùng owner. Một bảng StockBalances chứa nhiều hàng thì mỗi bộ (warehouse, SKU) có thể là một aggregate riêng.

### 2.1. Thế nào là colocate?

Hai nhóm dữ liệu được **colocate** khi hệ thống định tuyến chúng tới một nơi có khả năng kiểm tra và commit cùng bất biến.

~~~text
Trước:
  Orders      --shard by customer_id--> A
  OrderLines  --shard by product_id --> B/C/D

  Xác nhận Order phải kiểm tra qua nhiều shard.

Sau:
  Orders      --shard by order_id--> Owner(order_id)
  OrderLines  --shard by order_id--> Owner(order_id)

  Một Order và các Line nằm tại cùng owner.
~~~

Lựa chọn này có thể khiến truy vấn “mọi Line của Product P” phải fan-out qua nhiều shard. Nếu đường xác nhận Order quan trọng và cần nhất quán mạnh, đó là đánh đổi hợp lý; đường báo cáo theo Product có thể dùng một read model hoặc analytics mart.

**Đặt dữ liệu gần nhau chưa đủ** nếu các writer vẫn ghi vào hai nguồn chân lý độc lập. Cần thiết kế **routing, transaction và quyền ghi** đồng thời.

## 3. Vì sao transaction cục bộ không bảo vệ bất biến toàn cục?

Giả sử campaign có ngân sách **1.000.000 VND**, đã dùng **900.000 VND**. Hai vùng cùng muốn duyệt khoản chi 80.000:

~~~text
Đã chi:       900.000
Còn lại:      100.000

Shard A đọc còn 100.000 -> chấp nhận +80.000
Shard B đọc còn 100.000 -> chấp nhận +80.000

Đã duyệt: 1.060.000 > 1.000.000
~~~

Mỗi shard có thể dùng transaction cục bộ và không phát sinh lỗi nào. Một **SELECT tổng qua replica** có thể còn tệ hơn nếu replica chậm đồng bộ.

Với bất biến:

~~~text
SUM(accepted_spend WHERE campaign_id = X) <= budget(X)
~~~

cơ chế bảo vệ phải bao phủ **mọi lệnh tăng accepted_spend của X**. Không đủ nếu chỉ có SERIALIZABLE ở từng shard và không có transaction/validation liên shard. Retry cũng không giúp khi hai shard **không phát hiện conflict**.

### 3.1. Đối soát cuối ngày có sửa được không?

Đối soát có thể phát hiện tổng vượt mức. Nhưng nếu cả hai khoản chi đã được cam kết với đối tác, việc “xóa bớt một hàng” không tự khôi phục sự thật kinh doanh.

Đối soát sau sự kiện phù hợp với những chỉ tiêu **cho phép sai lệch tạm thời** như số lượt xem dashboard, với quy trình sửa được chấp thuận. Nó không thay thế quyết định atomic đối với các bất biến không thể bù trừ hợp lệ.

### 3.2. Một read replica không phải owner

Một cache đọc còn 5 vé **không phải quyền phát hành 5 vé**. Owner vé vẫn cần thao tác giữ chỗ nguyên tử. Giao diện có thể hiển thị lượng còn “ước tính”, nhưng chỉ kết quả commit từ owner mới được gọi là **đã giữ thành công**.

## 4. Lập bản đồ invariant theo chi phí phối hợp

| Bất biến | Scope thật | Lựa chọn ranh giới |
| --- | --- | --- |
| Quantity > 0 | Một hàng | NOT NULL, CHECK |
| reserved <= on_hand | Một warehouse + SKU | Một balance owner, atomic UPDATE |
| OrderLine thuộc cùng tenant với Order | Một Order | Khóa ghép tenant/order và FK cùng DB |
| Order CONFIRMED có Line | Order + tập Line | Một aggregate owner + transaction |
| Email duy nhất trong tenant | Một tenant | Per-tenant UNIQUE và colocate |
| Email duy nhất toàn hệ thống | Mọi tenant | Global registry/owner theo email |
| Voucher dùng một lần | Một voucher code trong scope | Owner/guard theo voucher |
| Campaign spend <= budget | Toàn campaign | Budget owner hoặc escrow |
| Event không được tính hai lần | Một source event | Owner/registry dedup theo event ID |
| KPI báo cáo đã công bố phải truy vết được | Nhiều fact và phiên bản | Versioned mart + reconciliation |

Một ràng buộc UNIQUE **trên từng shard** chỉ duy nhất **trong shard**. Nếu hai email bằng nhau được route đến hai shard khác nhau, không thể gọi đó là global uniqueness. Một FK **qua API GET** cũng không giống FK được DBMS cưỡng chế trong transaction, vì đối tượng cha có thể bị xóa/chuyển tenant giữa lúc kiểm tra và lúc ghi con.

Phân loại theo **phạm vi cần nhất quán**, không theo tên bảng hoặc tên service hiện tại.

## 5. Năm chiến lược khi boundary hiện tại không đủ

### 5.1. Đổi shard key để gom dữ liệu cần bảo vệ

Nếu Order/OrderLine phải cập nhật cùng nhau, chia theo order_id/tenant_id thay cho product_id. Nếu vé cần được bán đúng một lần, chia theo **seat_id/event_id** thay cho customer_id. Đây là cách biến bất biến xuyên shard thành **bất biến cục bộ tại owner**.

Đánh đổi: đường truy vấn theo các chiều khác có thể cần scatter-gather, projection hoặc search index riêng.

### 5.2. Tạo owner quyết định tập trung theo đối tượng

Một VoucherOwner hoặc CampaignBudgetOwner quyết định chính thức việc redeem/approve. Dữ liệu phụ liên quan có thể sống ở shard khác; chỉ **quyền chấp nhận** tập trung tại nơi kiểm soát được điều kiện atomic.

Đánh đổi: hot key, tranh khóa, độ trễ từ vùng xa, bài toán failover; nhưng bất biến rõ ràng hơn.

### 5.3. Chia quyền chi (escrow/quota)

Nếu tổng quyền được cấp cho các shard không vượt ngân sách chung và mỗi shard không dùng quá phần được cấp, tổng chi không thể vượt ngân sách.

~~~text
Campaign budget: 1.000.000
Shard A được cấp:   400.000
Shard B được cấp:   350.000
Shard C được cấp:   250.000
Tổng quyền đã cấp: 1.000.000
~~~

Mỗi shard có thể kiểm tra cục bộ. Nhưng việc **tái phân bổ quota giữa shard** phải tránh cấp trùng: không thể để A và B đều tự tăng quyền nhờ đọc một bản sao cũ. Một shard hết quota có thể tạm từ chối dù shard khác còn nhiều quyền chưa dùng.

### 5.4. Biến một transaction xuyên service thành workflow có trạng thái

Một checkout có thể:

~~~text
PENDING -> STOCK_RESERVED -> PAYMENT_AUTHORIZED -> CONFIRMED
        -> CANCELLED / COMPENSATING / MANUAL_REVIEW
~~~

Mỗi bước chỉ xác nhận khi owner tương ứng đã commit. Saga cần **idempotency, timeout, retry, trạng thái trung gian và compensation hợp lệ**. Saga **không tương đương** một transaction nguyên tử xuyên tất cả các service.

### 5.5. Thu hẹp hoặc đổi nghĩa bất biến theo quyết định nghiệp vụ

Nếu yêu cầu thực sự chỉ là email duy nhất **theo tenant**, không cần global registry. Nếu dashboard được phép trễ 5 phút, không cần lock tất cả shard để cập nhật biểu đồ. Nếu một warehouse chịu trách nhiệm giữ SKU, không bắt buộc cả hệ thống cùng reserve một pool.

Đây là **thay đổi hợp đồng nghiệp vụ**, không phải tối ưu kỹ thuật tùy ý. Với tiền, an toàn, quyền và cam kết với người dùng, phải có phê duyệt rõ ràng trước khi nới scope hoặc chấp nhận sai lệch tạm thời.

## 6. Ca A: đặt chỗ tồn kho tại owner của warehouse + SKU

Giả sử kho 10 có 10 chiếc SKU 501, 8 chiếc đã giữ. Hai request cùng muốn giữ thêm 2 chiếc.

### 6.1. Lược đồ PostgreSQL

~~~sql
CREATE TABLE stock_balances (
    tenant_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    sku_id BIGINT NOT NULL,
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    PRIMARY KEY (tenant_id, warehouse_id, sku_id),
    CHECK (reserved <= on_hand)
);

CREATE TABLE stock_reservations (
    reservation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    operation_id TEXT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    sku_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status TEXT NOT NULL
        CHECK (status IN ('ACTIVE', 'CONSUMED', 'RELEASED')),
    UNIQUE (tenant_id, operation_id),
    FOREIGN KEY (tenant_id, warehouse_id, sku_id)
        REFERENCES stock_balances(tenant_id, warehouse_id, sku_id)
);

INSERT INTO stock_balances
    (tenant_id, warehouse_id, sku_id, on_hand, reserved)
VALUES (1, 10, 501, 10, 8);

-- Tám chiếc đã giữ trước đó có bản ghi reservation tương ứng.
-- Giữ dữ liệu mẫu nhất quán với phép đối soát ở phần 14.
INSERT INTO stock_reservations
    (tenant_id, operation_id, warehouse_id, sku_id, quantity, status)
VALUES (1, 'existing-reservation', 10, 501, 8, 'ACTIVE');
~~~

**Grain** của StockBalances là một hàng cho một **tenant × warehouse × SKU**. FK giúp reservation trỏ tới hàng balance tồn tại. CHECK bảo vệ số lượng trên một hàng; nhưng invariant **reserved bằng tổng reservation ACTIVE** là quy tắc xuyên nhiều hàng, không tự được CHECK bảo vệ.

### 6.2. UPDATE có điều kiện và reservation cùng transaction

Một lệnh reserve có thể thực hiện **trong cùng một PostgreSQL database/owner**:

~~~sql
BEGIN;

INSERT INTO stock_reservations
    (tenant_id, operation_id, warehouse_id, sku_id, quantity, status)
VALUES (1, 'order901-line1', 10, 501, 2, 'ACTIVE')
ON CONFLICT (tenant_id, operation_id) DO NOTHING
RETURNING reservation_id;

-- CHỈ NẾU INSERT ở trên trả đúng 1 hàng:
UPDATE stock_balances
SET reserved = reserved + 2
WHERE tenant_id = 1
  AND warehouse_id = 10
  AND sku_id = 501
  AND on_hand - reserved >= 2
RETURNING on_hand, reserved;

-- Nếu UPDATE không trả đúng 1 hàng: ROLLBACK.
-- Nếu cả hai thành công: COMMIT.
COMMIT;
~~~

**Không chạy script trên một cách mù quáng:** ứng dụng hoặc stored procedure phải rẽ nhánh sau mỗi RETURNING. Nếu INSERT trả **0 hàng** vì operation_id đã tồn tại, **không chạy UPDATE**; đọc reservation cũ, kiểm tra payload (SKU/warehouse/quantity) để trả kết quả idempotent hoặc báo xung đột. Nếu INSERT có một hàng nhưng UPDATE có 0 hàng, **ROLLBACK**, không để reservation mồ côi.

UPDATE dùng biểu thức trên hàng hiện tại và điều kiện **on_hand - reserved >= 2** để quyết định atomic trên cùng hàng. Với PostgreSQL, những lệnh cùng sửa hàng balance phải phối hợp khóa hàng. Chỉ khi transaction commit mới trả ACCEPTED.

### 6.3. Release cũng phải chỉ xảy ra một lần

~~~sql
BEGIN;

UPDATE stock_reservations
SET status = 'RELEASED'
WHERE tenant_id = 1
  AND operation_id = 'order901-line1'
  AND status = 'ACTIVE'
RETURNING warehouse_id, sku_id, quantity;

-- CHỈ NẾU trả đúng 1 hàng, giảm reserved ở balance
-- theo chính quantity/warehouse/sku vừa RETURNING.
UPDATE stock_balances
SET reserved = reserved - 2
WHERE tenant_id = 1
  AND warehouse_id = 10
  AND sku_id = 501
  AND reserved >= 2;

-- Nếu UPDATE balance có 0 hàng: ROLLBACK.
-- Nếu cả hai thành công: COMMIT.
COMMIT;
~~~

Thủ tục thật phải dùng **quantity từ hàng được chuyển trạng thái**, không tin tham số release do caller tự gửi. Retry release sau khi reservation đã RELEASED không được giảm reserved lần thứ hai.

Khi hàng thực xuất kho, trạng thái CONSUMED có thể cần giảm **cả on_hand và reserved** trong một transaction, theo chính sách kho. Không dùng release thay cho consume vì hai nghiệp vụ khác nhau.

### 6.4. Giới hạn của ví dụ

- CHECK không chứng minh reserved = SUM(quantity của reservation ACTIVE).
- Hai API được quyền sửa stock_balances và stock_reservations độc lập vẫn có thể tạo chênh lệch.
- Đây chỉ là bất biến **theo một warehouse/SKU**. Nếu hai warehouse cùng lấy từ một tồn pool vật lý, owner phải được đặt lại theo pool hoặc quyền phân bổ.
- Nếu Stock DB và Reservation DB là hai hệ độc lập, ví dụ **không còn một transaction chung** và phải thiết kế giao thức bổ sung.

## 7. Ca B: giới hạn ngân sách bằng một budget owner

Ngân sách toàn campaign có invariant:

~~~text
accepted_spend(campaign) <= approved_budget(campaign)
~~~

Nếu việc chấp nhận chi diễn ra trên nhiều shard độc lập, mỗi shard có thể “đúng cục bộ” nhưng chi vượt tổng.

### 7.1. Dùng một hàng quyết định

~~~sql
CREATE TABLE campaign_budgets (
    campaign_id BIGINT PRIMARY KEY,
    budget_vnd BIGINT NOT NULL CHECK (budget_vnd >= 0),
    spent_vnd BIGINT NOT NULL DEFAULT 0 CHECK (spent_vnd >= 0),
    CHECK (spent_vnd <= budget_vnd)
);

CREATE TABLE campaign_spend_events (
    campaign_id BIGINT NOT NULL
        REFERENCES campaign_budgets(campaign_id),
    operation_id TEXT NOT NULL,
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (campaign_id, operation_id)
);

INSERT INTO campaign_budgets(campaign_id, budget_vnd, spent_vnd)
VALUES (42, 1000000, 900000);

-- Khoản 900.000 đã chi từ trước có sự kiện tương ứng.
INSERT INTO campaign_spend_events
    (campaign_id, operation_id, amount_vnd)
VALUES (42, 'existing-approved-spend', 900000);
~~~

Chấp nhận một khoản chi 80.000 theo **trình tự có nhánh điều kiện**:

~~~sql
BEGIN;

INSERT INTO campaign_spend_events
    (campaign_id, operation_id, amount_vnd)
VALUES (42, 'req-abc', 80000)
ON CONFLICT (campaign_id, operation_id) DO NOTHING
RETURNING operation_id;

-- CHỈ NẾU INSERT tạo đúng một hàng:
UPDATE campaign_budgets
SET spent_vnd = spent_vnd + 80000
WHERE campaign_id = 42
  AND budget_vnd - spent_vnd >= 80000
RETURNING budget_vnd, spent_vnd;

-- Nếu INSERT trùng: không tăng spent, kiểm tra payload.
-- Nếu UPDATE 0 hàng: ROLLBACK.
-- Chỉ COMMIT nếu hai bước mới đều thành công.
COMMIT;
~~~

Khi còn 100.000, hai giao dịch cùng tăng 80.000 trên **một hàng owner** sẽ không thể cùng thành công nếu transaction/điều kiện được thực thi như quy định.

Đánh đổi: campaign nóng có thể tạo điểm tranh khóa. Có thể chuyển sang **escrow allocation**, nhưng mọi lần cấp, thu hồi, điều chuyển quyền chi phải có cơ chế không cấp trùng. Không được tự chia quota dựa trên tổng đọc từ replica trễ.

### 7.2. Tái phân bổ quota

Giả sử shard A hết quota, B còn 50.000. Nếu A cần 20.000, một giao thức điều chuyển phải:

1. Xác nhận B có **ít nhất 20.000 quyền chưa sử dụng**.
2. Khóa hoặc tước quyền đó ở B theo cơ chế chịu được lỗi mạng/retry.
3. Cấp 20.000 quyền cho A **đúng một lần**.
4. Lưu lịch sử transfer và xử lý trạng thái không xác định nếu một bước thất bại.

Không cho A tự tăng quyền rồi “hy vọng” B tự giảm sau, bởi cả hai có thể chi từ cùng một khoản quyền trong khoảng trễ.

## 8. Ca C: colocate theo tenant với khóa và FK ghép

Hệ SaaS có Customer, Order và OrderLine. Nghiệp vụ yêu cầu: mỗi OrderLine thuộc Order cùng tenant; mỗi Order trỏ tới Customer cùng tenant. Nếu ID customer/order chỉ duy nhất trong tenant, mọi FK phải bao gồm tenant_id.

Ví dụ **partitioning trong một PostgreSQL database**, không phải database-sharding qua nhiều server:

~~~sql
CREATE TABLE tenant_customers (
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    email_normalized TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, email_normalized)
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_customers_p0
PARTITION OF tenant_customers
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE tenant_customers_p1
PARTITION OF tenant_customers
FOR VALUES WITH (MODULUS 2, REMAINDER 1);

CREATE TABLE tenant_orders (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')
    ),
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES tenant_customers(tenant_id, customer_id)
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_orders_p0
PARTITION OF tenant_orders
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE tenant_orders_p1
PARTITION OF tenant_orders
FOR VALUES WITH (MODULUS 2, REMAINDER 1);

CREATE TABLE tenant_order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES tenant_orders(tenant_id, order_id)
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_order_lines_p0
PARTITION OF tenant_order_lines
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE tenant_order_lines_p1
PARTITION OF tenant_order_lines
FOR VALUES WITH (MODULUS 2, REMAINDER 1);
~~~

Các khóa PK/UNIQUE trên bảng partitioned bao gồm **tenant_id** (partition key) theo yêu cầu của PostgreSQL. FK ghép ngăn một dòng Order tenant A trỏ tới Order/Customer chỉ tồn tại ở tenant B. Cả ba bảng được định tuyến theo tenant, thuận lợi cho việc colocate nếu **thiết kế sharding độc lập về sau** cũng dùng cùng routing.

**Cần tách bạch:** PostgreSQL partition trong ví dụ vẫn là **một database có transaction xuyên partition**; FK được DBMS bảo vệ. Nếu chuyển mỗi partition sang server/database độc lập, không được suy ra FK/transaction xuyên server tự tồn tại.

### 8.1. Kiểm tra với dữ liệu hai tenant

~~~sql
INSERT INTO tenant_customers
    (tenant_id, customer_id, email_normalized)
VALUES
    (1, 101, 'a@example.test'),
    (2, 101, 'a@example.test');

INSERT INTO tenant_orders
    (tenant_id, order_id, customer_id, status)
VALUES (1, 5001, 101, 'DRAFT');

INSERT INTO tenant_order_lines
    (tenant_id, order_id, line_no, sku_id, quantity)
VALUES (1, 5001, 1, 9001, 2);

-- Tenant 2 không có Order 5001: lệnh sau bị từ chối bằng FK.
INSERT INTO tenant_order_lines
    (tenant_id, order_id, line_no, sku_id, quantity)
VALUES (2, 5001, 1, 9001, 2);
~~~

Hai tenant dùng cùng email_normalized được phép trong ví dụ: UNIQUE ở đây bảo vệ **per-tenant**, không bảo vệ email toàn hệ. Giá trị email đã chuẩn hóa được giả định theo chính sách ứng dụng; hàm lower() đơn giản không phải một chuẩn email toàn cục đáng tin cậy cho mọi trường hợp.

### 8.2. Xác nhận Order phải có ít nhất một Line

FK từ Line lên Order bảo vệ con có cha, nhưng không bảo vệ cha luôn có con.

~~~sql
SELECT o.tenant_id, o.order_id
FROM tenant_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM tenant_order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
~~~

Truy vấn này **phát hiện**, không tự ngăn lỗi. Muốn bảo vệ invariant khi ghi, owner của Order phải:

1. Khóa Order và kiểm tra trạng thái trong một transaction.
2. Kiểm tra có ít nhất một Line hợp lệ.
3. Chuyển DRAFT -> CONFIRMED khi điều kiện đúng.
4. Mọi lệnh xóa/sửa Line phải dùng **cùng quy ước khóa và kiểm tra trạng thái**; không cho xóa dòng cuối của Order CONFIRMED.
5. Commit hoặc rollback toàn bộ.

Nếu API xác nhận có kiểm tra, nhưng job nền vẫn xóa Line không qua owner, bất biến vẫn có thể bị phá. **Ranh giới write ownership** phải bao gồm mọi đường ghi liên quan.

## 9. Global uniqueness: đổi phạm vi, shard theo key hay registry

Yêu cầu “email duy nhất toàn hệ thống” khác rất xa “email duy nhất trong một tenant”.

- **Per-tenant:** UNIQUE(tenant_id, email_normalized) là đủ nếu các hàng cùng tenant nằm tại nơi hỗ trợ uniqueness phù hợp.
- **Global:** nếu Customer chia theo tenant, cần cơ chế kiểm tra toàn bộ email ở mọi tenant.
- **Shard theo email:** đưa những giá trị email giống nhau tới cùng owner; đổi email có thể kéo theo thay shard hoặc lookup riêng.
- **Global registry:** một owner giữ quyền đăng ký email; các Customer shard chỉ dùng email đã được registry phê duyệt.

Ví dụ bảng đăng ký toàn cục:

~~~sql
CREATE TABLE global_email_registry (
    email_normalized TEXT PRIMARY KEY,
    identity_id BIGINT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (
        status IN ('RESERVED', 'ACTIVE', 'RELEASE_PENDING')
    )
);
~~~

Registry có thể quyết định atomic việc chiếm email. Nhưng **registry thành công, Customer shard thất bại** vẫn là bài toán hai hệ thống. Cần workflow có trạng thái, idempotency, timeout, expiry/reconciliation và quy tắc khi nào tài khoản được công bố ACTIVE.

Cần hỏi thêm: email là **username**, kênh liên hệ hay thuộc tính hồ sơ? Một email tổng đài có thể dùng chung cho nhiều người? Email cũ có còn bị giữ khi account xóa mềm? Việc đặt invariant toàn cục khi nghiệp vụ chỉ cần per-tenant có thể tạo điểm nghẽn không cần thiết.

## 10. Partition theo thời gian và giới hạn UNIQUE toàn cục

Bảng sự kiện lớn có thể được partition theo ngày/tháng để phục vụ lưu trữ và query pruning. Nhưng bất biến “một source_event_id chỉ được chấp nhận một lần” **không có ngày tháng trong phạm vi duy nhất**.

Giả sử source event E-100 xảy ra ngày 10/10, rồi được phát lại cùng ID với timestamp bị sửa thành 10/11. Nếu mỗi partition có UNIQUE(source_event_id), E-100 vẫn có thể xuất hiện một lần **trong mỗi partition**.

### 10.1. Ví dụ PostgreSQL RANGE partition

~~~sql
CREATE TABLE meter_events (
    tenant_id BIGINT NOT NULL,
    source_event_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    device_id BIGINT NOT NULL,
    value_num NUMERIC(18, 5) NOT NULL,
    PRIMARY KEY (occurred_at, tenant_id, source_event_id)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE meter_events_oct
PARTITION OF meter_events
FOR VALUES FROM ('2026-10-01 00:00:00+00')
           TO ('2026-11-01 00:00:00+00');

CREATE TABLE meter_events_nov
PARTITION OF meter_events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
           TO ('2026-12-01 00:00:00+00');
~~~

PK bảo vệ **(occurred_at, tenant_id, source_event_id)**, không bảo vệ **(tenant_id, source_event_id)** trên mọi timestamp. Cùng ID nhưng occurred_at khác có thể đi vào hai partition mà không vi phạm PK.

Trong PostgreSQL, ràng buộc UNIQUE/PRIMARY KEY của bảng partitioned phải bao gồm **các cột partition key** theo các giới hạn hiện hành. Vì vậy không nên mặc định có thể đặt một UNIQUE(source_event_id) toàn bảng partition theo occurred_at mà DBMS sẽ tự giải quyết uniqueness xuyên mọi partition.

### 10.2. Tạo một ingestion registry độc lập với thời gian

~~~sql
CREATE TABLE accepted_source_events (
    tenant_id BIGINT NOT NULL,
    source_system TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    first_accepted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, source_system, source_event_id)
);
~~~

Nếu registry và meter_events nằm trong **cùng một database transaction**, đường ingest có thể:

1. INSERT accepted_source_events theo ID nguồn.
2. Nếu trùng ID, so sánh payload; retry đúng không tạo event mới, payload khác phải được phân loại.
3. Nếu registry insert thành công, INSERT meter_events.
4. Commit cả hai, hoặc rollback cả hai.

Nếu registry nằm ở **database độc lập** với meter_events, trình tự trên không còn tự nguyên tử. Cần một owner ingest, transaction phân tán thực sự được hỗ trợ hoặc workflow có trạng thái/pending và phát hành nhất quán.

**Đừng nhầm partition pruning với invariant.** Phân vùng theo thời gian có thể làm báo cáo nhanh hơn, nhưng không tự chống event trùng, event late, backfill hoặc correction đổi partition.

## 11. Khi bất biến nằm giữa nhiều service hoặc shard

Một đơn hàng có thể cần giữ hàng ở hai kho và xác nhận thanh toán:

~~~mermaid
flowchart LR
    O["Order Owner"] --> WA["Stock Owner A"]
    O --> WB["Stock Owner B"]
    O --> P["Payment Owner"]
~~~

Yêu cầu:

> Order chỉ được CONFIRMED khi cả hai kho đã giữ đủ hàng và payment đã được xác thực theo chính sách.

**Một transaction trong Order DB** không có khả năng tự rollback các bước đã commit ở hai Stock DB hay một payment gateway độc lập.

### 11.1. Ba lựa chọn kiến trúc chính

**Colocate dữ liệu vào cùng ranh giới transaction:** nếu các đối tượng thực sự phải commit cùng nhau và có thể chấp nhận tập trung, chuyển shard/aggregate ownership để các thao tác nằm trong một transaction của một DBMS phù hợp. Đánh đổi là hot key, write latency và độ khó phân bố địa lý.

**Distributed transaction/2PC:** một số hệ DB phân tán hỗ trợ transaction xuyên shard hoặc giao thức two-phase commit. Phải xem chính xác hệ tham gia, recovery khi coordinator lỗi, thời gian giữ khóa, timeout và tính sẵn sàng. Mở hai kết nối, chạy BEGIN ở cả hai rồi COMMIT lần lượt **không phải** 2PC. Dịch vụ thanh toán bên ngoài cũng không mặc nhiên tham gia 2PC của database.

**Saga/workflow:** nếu các bước có thể bù trừ theo nghĩa nghiệp vụ, giữ state machine và các lệnh idempotent:

~~~text
PENDING
  -> RESERVED_AT_A
  -> RESERVED_AT_A_AND_B
  -> PAYMENT_AUTHORIZED
  -> CONFIRMED

Khi một bước thất bại:
  -> COMPENSATING
  -> RELEASE các reservation đã commit
  -> VOID payment authorization khi được phép
  -> CANCELLED hoặc MANUAL_REVIEW
~~~

### 11.2. Những bảo đảm bắt buộc với saga

- Mỗi service owner **bảo vệ invariant cục bộ**: kho không over-reserve, payment không capture hai lần.
- Mỗi command có **operation_id** ổn định; retry không tạo tác động mới.
- Order owner là nơi duy nhất chuyển sang CONFIRMED sau khi đã nhận đủ bằng chứng.
- Trạng thái PENDING và COMPENSATING là trạng thái nghiệp vụ **thật**, không được trình bày như giao dịch đã kết thúc.
- Timeout có thể để lại **unknown outcome**; cần truy vấn trạng thái theo idempotency key, không đoán rằng call thất bại nghĩa là thao tác phía xa chưa commit.
- Compensation có thể thất bại, cần retry và escalation; không được gọi là rollback nguyên tử.
- Nếu một bước không đảo ngược được (đã giao hàng, đã chuyển tiền không thể hủy), phải dùng **nghiệp vụ sửa sai riêng** hoặc buộc quyết định mạnh hơn trước khi cam kết.

Saga không đảm bảo all-or-nothing tại mọi thời điểm. Nó bảo vệ sự nhất quán **của quy trình trạng thái cuối** với những giai đoạn trung gian được công nhận. Nếu nghiệp vụ tuyệt đối không cho phép trạng thái trung gian lộ ra, cần cân nhắc transaction/phối hợp mạnh hoặc thiết kế lại cam kết.

### 11.3. Outbox và retry không thay atomcity xuyên service

Transactional outbox giúp ghi “đã commit thay đổi cục bộ” và sự kiện cần phát đi **trong cùng database transaction**. Consumer ở nơi khác xử lý event và dedup theo event_id.

Điều đó giải quyết một phần bài toán **không mất sự kiện sau commit cục bộ**, nhưng không tự đảm bảo consumer đã xử lý hoặc hai service đã commit cùng một transaction. API trả CONFIRMED phải dựa trên hợp đồng workflow, không chỉ dựa vào việc “đã gửi sự kiện”.

## 12. Single writer, read model và ranh giới của CQRS

Một nguồn quyết định có thể phục vụ nhiều bản sao đọc:

~~~mermaid
flowchart TB
    CMD["Commands"] --> OWN["Aggregate Owner + Transaction"]
    OWN --> LOG["Outbox / CDC"]
    LOG --> RD["Read Model"]
    LOG --> AN["Analytics Mart"]
    RD --> API["API read"]
    AN --> BI["Dashboard"]
~~~

- **Owner:** có quyền chấp nhận hoặc từ chối thay đổi theo invariant.
- **Read model:** tối ưu tìm kiếm, lọc và độ trễ đọc; có thể trễ.
- **Analytics mart:** tổng hợp nhiều nguồn, phục vụ phân tích với thời gian làm mới rõ ràng.
- **Outbox/CDC:** đồng bộ những thay đổi đã commit; cần replay, dedup và đối soát.

Nếu API ghi thẳng vào Read Model rồi tin nó là sự thật, boundary owner lại bị phá. Cần ghi rõ **source of truth**, những writer được phép sửa authoritative data và ai có trách nhiệm khôi phục sau lỗi.

Một phép đọc read replica trả **available_stock = 5** không cho phép API cấp quyền giữ 5 chiếc mà không gọi Stock Owner. Replica có thể dùng để hiển thị “còn khoảng 5 chiếc”, còn **ReserveStock** phải kiểm tra tại nơi có quyền ra quyết định.

### 12.1. Mọi đường ghi đều phải theo quy ước

Một invariant có thể bị phá bởi:

- API thông thường đã kiểm tra nhưng job nhập dữ liệu bỏ qua.
- Admin script trực tiếp sửa budget/spent hoặc reserved.
- Consumer replay một event hai lần mà không có dedup.
- Luồng xóa Line cuối của Order CONFIRMED không khóa Order.
- Migration dual-write làm hai owner cùng chấp nhận lệnh.
- Một service cũ vẫn giữ credential ghi sau khi chuyển owner.

**Đổi ranh giới phải bao gồm quyền DB, routing, code path, batch job và runbook**, không chỉ đổi tên microservice hay thêm một lớp API.

## 13. Di chuyển shard key: điều nguy hiểm nhất là hai owner cùng ghi

Giả sử tenant 1 được chuyển từ shard A sang B:

~~~text
Old route: tenant 1 -> shard A
New route: tenant 1 -> shard B

Client X vẫn ghi vào A theo routing cũ.
Client Y ghi vào B theo routing mới.

Mỗi nơi đều cho rằng mình là owner.
~~~

Nếu cả hai cùng chấp nhận voucher redemption hoặc stock reservation, dữ liệu hợp lệ **trong từng shard** nhưng sai **toàn tenant**. Việc copy thành công số lượng hàng không ngăn split-brain này.

### 13.1. Quy trình migration có thể kiểm chứng

1. **Lập danh sách bất biến:** những điều nào phải đúng trước, trong và sau cutover?
2. **Định nghĩa scope chuyển quyền:** tenant, aggregate_id, key-range hay voucher_code?
3. **Định nghĩa owner/routing map:** một khóa nghiệp vụ chỉ có một owner có quyền nhận commit.
4. **Backfill snapshot:** copy dữ liệu và khóa nghiệp vụ, giữ mapping ID ổn định.
5. **Đồng bộ delta:** dùng CDC/outbox/replay idempotent, đo lag.
6. **Kiểm tra đồng nhất:** PK/FK/unique, số hàng theo business key, balance, event offsets và tổng trạng thái.
7. **Chặn hai writer:** dùng dừng ghi có kiểm soát hoặc fencing/owner-epoch có tính cưỡng chế trước cutover.
8. **Đổi route:** lệnh theo route cũ phải bị từ chối/chuyển tiếp, không tiếp tục commit độc lập.
9. **Giám sát hậu chuyển:** lag, số operation treo, mismatch, timeout và retry.
10. **Rollback có điều kiện:** không chuyển đơn giản về A nếu A đã không còn cập nhật đầy đủ sau cutover.

Dual-write kiểu “ghi cả A và B” không mặc định an toàn: ghi A xong B lỗi có thể khiến hai bên lệch, và cả hai cùng chấp nhận command có thể nhân hiệu ứng nghiệp vụ.

### 13.2. Fencing và owner epoch

Một cách quản lý quyền chuyển là dùng epoch tăng dần:

~~~text
tenant 1, owner = A, epoch = 7
sau cutover:
tenant 1, owner = B, epoch = 8
~~~

Writer gửi epoch tương ứng và nơi chấp nhận command từ chối epoch cũ. Tuy nhiên, **chỉ lưu epoch ở một bảng metadata được replicate bất đồng bộ chưa đủ** nếu A vẫn có thể commit dựa trên epoch 7 trong lúc B đã chấp nhận epoch 8.

Fencing phải gắn với **khả năng ghi authoritative** hoặc cơ chế đồng thuận/lease/lock đủ mạnh để owner cũ thực sự không còn quyền ghi sau chuyển giao. Cần kiểm thử với mạng chia cắt, timeout và leader failover.

## 14. Kiểm chứng invariant sau đổi ranh giới

Kiểm thử migration không chỉ so COUNT(*) hay SUM tổng. Hai lỗi trái chiều có thể triệt tiêu nhau, hoặc cùng tổng reservation nhưng gán sai warehouse.

### 14.1. Tồn kho không âm và không vượt capacity

~~~sql
SELECT tenant_id, warehouse_id, sku_id, on_hand, reserved
FROM stock_balances
WHERE on_hand < 0
   OR reserved < 0
   OR reserved > on_hand;
-- Kỳ vọng: không hàng nào.
~~~

Đối chiếu reserved materialized với reservation ACTIVE:

~~~sql
SELECT b.tenant_id, b.warehouse_id, b.sku_id,
       b.reserved,
       COALESCE(r.active_qty, 0) AS active_qty
FROM stock_balances AS b
LEFT JOIN (
    SELECT tenant_id, warehouse_id, sku_id,
           SUM(quantity) AS active_qty
    FROM stock_reservations
    WHERE status = 'ACTIVE'
    GROUP BY tenant_id, warehouse_id, sku_id
) AS r
  ON r.tenant_id = b.tenant_id
 AND r.warehouse_id = b.warehouse_id
 AND r.sku_id = b.sku_id
WHERE b.reserved <> COALESCE(r.active_qty, 0);
~~~

Truy vấn giả định tất cả lượng reserved đều được ghi ở trạng thái ACTIVE trong bảng này, không có luồng reservation khác. Nếu có trạng thái trung gian hoặc inventory reconciliation, phải điều chỉnh công thức theo **business contract**, không coi mọi sai lệch là bug trong dữ liệu.

### 14.2. Ngân sách materialized đối chiếu với spend events

~~~sql
SELECT b.campaign_id, b.budget_vnd, b.spent_vnd
FROM campaign_budgets AS b
WHERE b.spent_vnd < 0
   OR b.spent_vnd > b.budget_vnd;

SELECT b.campaign_id, b.spent_vnd,
       COALESCE(e.event_amount_vnd, 0) AS event_amount_vnd
FROM campaign_budgets AS b
LEFT JOIN (
    SELECT campaign_id, SUM(amount_vnd) AS event_amount_vnd
    FROM campaign_spend_events
    GROUP BY campaign_id
) AS e ON e.campaign_id = b.campaign_id
WHERE b.spent_vnd <> COALESCE(e.event_amount_vnd, 0);
~~~

Với mẫu này, events chỉ tăng accepted spend. Khi có refund/reversal, phải đối soát theo **net effects** hoặc delta hợp lệ, không so tổng positive event một cách máy móc.

### 14.3. Order CONFIRMED không có Line

~~~sql
SELECT o.tenant_id, o.order_id
FROM tenant_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM tenant_order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
~~~

Nếu query trả hàng, cần truy ngược các writer có quyền sửa status/line. Đây là lỗi của **đường ghi hoặc chính sách transition**, không phải bằng chứng rằng chỉ cần thêm một index.

### 14.4. Đối chiếu ở nhiều cấp

Một bộ kiểm chứng trước/sau migration nên gồm:

| Cấp | Cần so sánh |
| --- | --- |
| **Business ID** | Có bản ghi thiếu, trùng hoặc bị đổi owner không hợp lệ không? |
| **Tenant/Shard** | Mỗi đối tượng xuất hiện ở đúng một owner authoritative? |
| **Quan hệ** | FK/parent-child, tenant scope, status transition |
| **Tổng theo scope** | Budget/campaign, reserved/warehouse/SKU |
| **Event** | Operation ID/source ID đã được xử lý đúng một lần? |
| **Thời gian** | Event đến muộn, backfill, epoch và thời điểm cutover |
| **Trạng thái lỗi** | PENDING/COMPENSATING cần retry hoặc can thiệp thủ công |
| **Hiệu năng** | Hot key, p95/p99 commit, lag CDC, độ trễ đọc |

Một tổng toàn hệ khớp không chứng minh các **nhóm nhỏ** hoặc các **business key** đã đúng.

## 15. Ma trận chọn ranh giới theo tình huống

| Tình huống | Lựa chọn đáng xem xét | Rủi ro/đánh đổi |
| --- | --- | --- |
| Order + Line cần transaction chung | Colocate theo order/tenant | Truy vấn theo Product có thể fan-out |
| Stock theo một warehouse/SKU | Owner và conditional UPDATE trên balance | Hot SKU tranh khóa |
| Stock chung phân bổ nhiều kho | Owner chung hoặc escrow quota | Điều chuyển quota cần protocol |
| Voucher chỉ đổi một lần | Owner/registry theo voucher | Hot key và failover |
| Email duy nhất per-tenant | UNIQUE(tenant_id,email) | Cho phép trùng giữa tenant |
| Email duy nhất toàn hệ | Global registry hoặc shard theo email | Workflow xuyên Customer shard |
| Campaign spend không vượt budget | Single owner hoặc quyền chi phân bổ | Tranh khóa/underutilization |
| Thanh toán và kho khác service | Saga hoặc distributed transaction thật sự | Trạng thái trung gian/chi phí 2PC |
| Event partition theo thời gian, ID phải global | Registry dedup ngoài time partition | Registry phải tham gia đường ingest an toàn |
| Dashboard cần dữ liệu liên shard | Read model/mart có freshness SLA | Không dùng để duyệt nghiệp vụ |
| Di chuyển tenant sang shard mới | Backfill + fencing + cutover | Split-brain, replay, rollback khó |
| Invariant toàn cục quá đắt | Đàm phán đổi scope/commit semantics | Phải có phê duyệt nghiệp vụ |

**Tín hiệu nên dừng và thiết kế lại:** mỗi request ghi phải gọi nhiều service chỉ để kiểm tra một điều kiện bắt buộc; mọi FK “được kiểm tra qua GET API”; cùng key có thể được chấp nhận trên nhiều shard; hệ thống dựa vào job cuối ngày để sửa cam kết đã xác nhận; hoặc migration có hai owner cùng quyền ghi.

## 16. Đánh đổi hiệu năng, sẵn sàng và tính đúng

Bảo vệ invariant tốt hơn có thể tăng chi phí:

- **Write p95/p99:** thêm phối hợp và khóa có thể tăng độ trễ command.
- **Throughput:** hot budget/stock row có thể giới hạn số lệnh/s.
- **Availability:** khi owner không truy cập được, lệnh có thể phải từ chối/chờ thay vì nhận thiếu kiểm soát.
- **Read amplification:** phân vùng theo owner nghiệp vụ có thể làm query theo chiều khác phải fan-out.
- **Data movement:** đổi shard key có backfill/CDC, kiểm soát cutover và nguy cơ split-brain.
- **Operational burden:** reconciliation, deadlock/serialization retry, Saga recovery, alerting.

Cần đo với dữ liệu hot/cold, tải đọc–ghi thật, số shard và khoảng cách vùng địa lý. Không dựa vào một số ms đo trên bảng nhỏ để tuyên bố giải pháp sẽ mở rộng tuyến tính.

Nếu FK/unique/row lock làm ghi chậm, trước hết hãy hỏi có thể **thu nhỏ scope owner**, **phân rã quyền qua escrow**, **tối ưu index/transaction**, hoặc **tách read model** hay không. Tắt constraint rồi chờ job sửa hậu kỳ là thay đổi mức bảo đảm, không chỉ là tối ưu.

### 16.1. Bảo vệ đúng nhưng không quá chặt

Không phải mọi query phân tích cần một transaction xuyên shard. Ví dụ doanh thu theo Product có thể được tổng hợp từ event đã commit và chịu trễ 1 phút, với quy tắc backfill và đối soát. Cũng không cần cho mọi Customer cùng tenant tranh một khóa lớn nếu invariant chỉ liên quan **mỗi Order**.

Mục tiêu là **phối hợp đúng nơi cần**, không phải tập trung toàn bộ hệ thống vào một transaction duy nhất.

## 17. So sánh mô hình quan hệ, document, graph và warehouse

| Công nghệ | Boundary thường hữu ích | Điều không được suy diễn |
| --- | --- | --- |
| **Quan hệ** | PK/FK/UNIQUE và transaction theo aggregate/shard | FK trong một DB không tự trở thành FK xuyên server |
| **Document** | Document/aggregate được cập nhật nguyên tử nếu DB hỗ trợ | Nhiều document liên quan không mặc nhiên atomic |
| **Graph** | Owner/transaction cho các node/cạnh cần kiểm tra | Duyệt replica cũ không chứng minh quyền/chu trình hiện tại |
| **Warehouse** | Fact/dimension, mart có phiên bản, đối soát | Tổng hợp cuối ngày không ngăn oversell lúc checkout |

### 17.1. Document: nhúng dữ liệu cùng vòng đời

Một Order document:

~~~json
{
  "tenantId": 1,
  "orderId": 5001,
  "status": "DRAFT",
  "lines": [
    {"lineNo": 1, "skuId": 9001, "quantity": 2}
  ]
}
~~~

có thể giúp kiểm tra status và lines trong cùng thao tác cập nhật document **nếu** hệ thống hỗ trợ atomic document update và mọi writer tuân thủ. Nhưng Inventory và Payment ở hai document/service khác vẫn cần phối hợp; nhúng Line không tự tạo transaction toàn bộ checkout.

### 17.2. Graph: invariant theo cạnh và đường đi

Graph tổ chức/phân quyền có thể cần “mỗi tài nguyên chỉ có một owner trực tiếp” hoặc “cây quản lý không chứa chu trình”. Một cập nhật cạnh có thể phải kiểm tra cả một subgraph; nếu các cạnh nằm trên nhiều partition, kiểm tra cục bộ không chứng minh đồ thị toàn cục không có chu trình.

Có thể chọn owner cho subgraph, một đường command được tuần tự hóa, hoặc protocol consistency mạnh. Chỉ chấp nhận kiểm tra hậu kỳ khi chu trình tạm thời không ảnh hưởng quyền hay an toàn.

### 17.3. Warehouse: đối soát thay vì ra quyết định bán

Một mart tồn kho tổng hợp theo giờ phù hợp phân tích xu hướng, không phù hợp để quyết định giữ hai chiếc cuối cùng khi đồng thời có nhiều request. Command phải tới **Stock Owner**. Ngược lại, không bắt toàn bộ dashboard phải đọc owner với khóa mạnh nếu có thể dùng projection với SLA rõ.

## 18. Quy trình thiết kế lại và di trú

1. **Viết invariant** dưới dạng công thức, scope và thời điểm phải đúng.
2. **Liệt kê mọi dữ liệu tham gia** và các owner/shard hiện tại.
3. **Liệt kê mọi writer**, kể cả batch/import/admin và consumer.
4. **Dựng một lịch đua tranh** cho thấy hai request có thể phá invariant ra sao.
5. **Xác nhận khả năng transaction thực tế** ở mỗi node và xuyên node.
6. **Ưu tiên colocate** dữ liệu và quyền ghi cần cập nhật cùng nhau.
7. **Nếu hot owner**, đo escrow/quota hoặc chia quyền có proof an toàn.
8. **Nếu khác service**, định nghĩa state machine, idempotency, unknown outcomes và compensation.
9. **Nếu phải đổi scope invariant**, xin phê duyệt business và sửa hợp đồng API/báo cáo.
10. **Thiết kế PK/FK/UNIQUE** theo scope mới, không bỏ quên partition key hoặc tenant.
11. **Lập kế hoạch migration** có backfill, CDC, fencing, cutover và rollback phù hợp.
12. **Thử concurrency/failover** trước và sau cutover.
13. **Đối soát theo business key** cùng các invariant, không chỉ SUM/COUNT.
14. **Đo vận hành** trên hot key, write latency, lock, replication lag và throughput.
15. **Lưu quyết định thiết kế** để các writer sau này không phá boundary.

### 18.1. Mẫu ghi nhận quyết định

~~~text
Invariant:
  Voucher được dùng tối đa một lần trong một tenant.

Scope:
  (tenant_id, voucher_code)

Old routing:
  Redemption sharded by customer_id.
  Hai customer có thể chấp nhận cùng voucher ở hai shard.

New owner:
  VoucherOwner sharded by (tenant_id, voucher_code).

Write protocol:
  AVAILABLE -> REDEEMED bằng atomic transition tại owner.
  operation_id được lưu để retry an toàn.

Cross-service lifecycle:
  Order chỉ được CONFIRMED theo quy tắc workflow.
  Compensation/release chỉ khi voucher policy cho phép.

Read model:
  Event đã commit được replicate để báo cáo.
  Projection không có quyền duyệt redemption.

Migration:
  Backfill, ngăn writer cũ, fence, cutover, reconcile.

Validation:
  Không voucher nào có hơn một redemption hợp lệ.
  Retry/concurrent requests không tăng số lượt.
  Không có hai owner cùng được quyền commit.
~~~

Đây là bản ghi thiết kế minh họa, không phải lời khẳng định mọi voucher khi hủy Order đều được phép sử dụng lại. Vòng đời voucher phải theo chính sách nghiệp vụ.

## 19. Bài tập tình huống có hướng dẫn giải

### Bài 1. Chọn lại shard key

**Đề bài:** Order chia theo customer_id, OrderLine chia theo product_id. CONFIRMED yêu cầu Order có Line cùng tenant. Điều gì khó bảo vệ?

**Gợi ý:** Kiểm tra và commit phải đi qua nhiều shard. Cân nhắc colocate theo **(tenant_id, order_id)**, có một aggregate owner; dùng FK ghép khi cùng DB và transaction/đường ghi thống nhất cho mọi thay đổi OrderLine.

### Bài 2. Voucher dùng một lần

**Đề bài:** Hai khách khác nhau dùng cùng voucher và đến hai shard theo customer_id. Local UNIQUE có đủ không?

**Gợi ý:** Không nếu uniqueness theo voucher. Chọn owner/registry theo **voucher code trong scope** và atomic transition; operation_id chống retry.

### Bài 3. SERIALIZABLE cục bộ

**Đề bài:** Campaign còn 100.000. Hai shard cùng chi 80.000, mỗi shard dùng SERIALIZABLE. Vì sao vẫn có thể overspend?

**Gợi ý:** Nếu database không có điều phối xuyên shard thì hai transaction không thấy conflict chung. Cần budget owner hoặc escrow quyền chi với tổng allocation được bảo vệ.

### Bài 4. Hai request reserve stock

**Đề bài:** on_hand = 10, reserved = 8, hai request mỗi bên xin 2. Vì sao SELECT rồi UPDATE không đủ?

**Gợi ý:** Cùng đọc số còn 2 có thể dẫn tới hai lời hứa. Atomic UPDATE có điều kiện ở StockOwner, cùng transaction với reservation/idempotency, chỉ trả ACCEPTED sau commit.

### Bài 5. Payment lỗi sau reserve

**Đề bài:** Stock DB đã commit reservation; Payment Service từ chối. ROLLBACK Order DB có trả hàng lại không?

**Gợi ý:** Không. Cần ReleaseReservation idempotent hoặc giao thức transaction thật sự hỗ trợ; Saga ghi trạng thái bù trừ và retry. Compensation không phải rollback nguyên tử.

### Bài 6. Email per-tenant hay global

**Đề bài:** UNIQUE(tenant_id,email_normalized) trên bảng chia tenant có đảm bảo một email chỉ dùng một lần toàn SaaS không?

**Gợi ý:** Không. Đó là per-tenant uniqueness. Global cần registry/owner theo email hoặc route tương ứng, cùng quy trình lifecycle giữa registry và Customer.

### Bài 7. Event ID xuyên time partition

**Đề bài:** Cùng event E100 được ghi tháng 10 và tháng 11 với occurred_at khác nhau. PK(occurred_at,event_id) có ngăn không?

**Gợi ý:** Không vì hai khóa ghép khác nhau. Cần dedup theo source event ID trong scope và protocol giữ uniqueness xuyên partition; PostgreSQL partitioned UNIQUE chịu giới hạn partition key.

### Bài 8. Dual write trong migration

**Đề bài:** Tenant được chuyển A -> B và hệ thống cho ghi hai bên trong một giờ để tránh downtime. Có chắc an toàn không?

**Gợi ý:** Không; có thể split-brain. Chỉ một owner được chấp nhận command tại mỗi thời điểm, với fencing/epoch hoặc dừng ghi kiểm soát; copy delta idempotent và đối soát sau cutover.

### Bài 9. Chỉ đối soát tổng reservation

**Đề bài:** Trước và sau migration tổng reserved đều 500 nhưng một số reservation gán sai warehouse. Có thể tuyên bố dữ liệu đúng không?

**Gợi ý:** Không. Đối chiếu theo **tenant, warehouse, SKU, operation_id, trạng thái, số lượng** và những FK/bất biến cụ thể.

### Bài 10. Escrow hết quota một shard

**Đề bài:** Shard A hết quota, B còn 50.000 quyền. A tự tăng quota 20.000 rồi yêu cầu B giảm sau có đúng không?

**Gợi ý:** Không vì hai nơi có thể cùng chi quyền đó. Cần protocol chuyển quyền không cấp trùng; trong lúc chưa chuyển an toàn, A phải chờ hoặc từ chối dù toàn hệ còn quota.

### Bài 11. Replica báo còn vé

**Đề bài:** Replica báo còn ba vé. API tự đánh dấu bán thành công mà không gọi owner vé. Có an toàn không?

**Gợi ý:** Không. Replica có thể chậm; command cần reserve ở owner atomic trước khi hứa đã bán.

### Bài 12. Nới invariant để tăng tốc

**Đề bài:** Nhóm muốn bỏ global email registry, chạy job xóa trùng hằng đêm nhưng vẫn công bố “email duy nhất toàn hệ thống”.

**Gợi ý:** Không. Đó là thay đổi mức bảo đảm chưa được phê duyệt. Có thể tối ưu registry, đổi route, hoặc chính thức đổi hợp đồng sang per-tenant nếu business chấp thuận.

## 20. Checklist nghiệm thu

- [ ] Invariant có **phạm vi và thời điểm bắt buộc đúng** được ghi rõ.
- [ ] Owner quyết định chấp nhận command là duy nhất tại thời điểm commit.
- [ ] Dữ liệu cần cập nhật cùng nhau được colocate hoặc có coordination phù hợp.
- [ ] PK/FK/UNIQUE đúng tenant, shard và business key; global uniqueness không bị nhầm với local uniqueness.
- [ ] Mọi API, job, import và admin script tuân thủ owner/đường ghi.
- [ ] Retry/idempotency không tạo hai hiệu ứng khi dùng cùng operation_id.
- [ ] Quá trình Saga có trạng thái trung gian, compensation và lối xử lý unknown outcomes.
- [ ] Quota/escrow không cấp quyền chi trùng khi điều chuyển.
- [ ] Mỗi bản sao đọc có freshness SLA và không được dùng thay owner cho quyết định mạnh.
- [ ] Migration có backfill, CDC, fencing, cutover, đối soát và rollback được đánh giá.
- [ ] Kiểm thử concurrency, failover, split-brain, duplicate và điều chỉnh muộn.
- [ ] Kiểm chứng dữ liệu theo business ID, tenant, trạng thái và invariant, không chỉ COUNT.
- [ ] Chi phí latency, contention, throughput, khả năng khôi phục và phân vùng được đo.
- [ ] Có bản ghi quyết định ownership và những giả định còn cần theo dõi.

## 21. Ghi nhớ

- **Bất biến quyết định ranh giới**, không phải ngược lại: nếu một invariant quan trọng cần nhiều shard để kiểm tra mỗi lần ghi, nên xem lại shard key/aggregate/owner.
- **Partition trong một database khác với nhiều database shard độc lập**. Transaction, FK và UNIQUE phải được xác định đúng theo DBMS và cách triển khai.
- **Colocate hoặc định tuyến theo business key** giúp chuyển nhiều bất biến xuyên node về kiểm tra cục bộ.
- **Global uniqueness, campaign budget và voucher một lần** cần một owner hoặc giao thức phân bổ quyền an toàn; các transaction cục bộ không tự tạo bảo đảm toàn cục.
- **Saga quản lý quy trình và bù trừ** nhưng không tạo một transaction nguyên tử toàn hệ; compensation cũng có thể thất bại.
- **Outbox, CDC, projection và read replica** cải thiện đồng bộ/đọc, không thay quyền chấp nhận của owner.
- **Đổi shard key là đổi quyền sở hữu**, không chỉ copy hàng; cutover phải chống hai owner cùng ghi.
- **Đối soát theo invariant và business key** quan trọng hơn chỉ so row count hoặc tổng số, vì sai lệch chi tiết có thể triệt tiêu nhau.

Một thiết kế phân tán đáng tin không phải thiết kế hoàn toàn tránh phối hợp. Đó là thiết kế **biết bất biến nào cần phối hợp, đặt quyền quyết định ở đúng ranh giới, thu nhỏ phạm vi phải phối hợp đến mức hợp lý và có bằng chứng rằng các trạng thái đã công bố tuân thủ hợp đồng nghiệp vụ**.


