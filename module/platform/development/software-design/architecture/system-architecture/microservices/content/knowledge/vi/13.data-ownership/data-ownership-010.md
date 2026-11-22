# Những bước giảm dần cơ sở dữ liệu dùng chung trong hệ thống cũ

## 1. Bài toán: vì sao một database dùng chung cản trở microservices?

Nhiều hệ thống khởi đầu dưới dạng monolith hoặc một nhóm ứng dụng cùng truy cập cơ sở dữ liệu quan hệ. Theo thời gian, các nhóm tạo thêm service mới nhưng vẫn sử dụng cùng bảng, cùng schema hoặc cùng tài khoản database. Về mặt mạng, các ứng dụng đã tách tiến trình; về mặt dữ liệu và thay đổi, chúng vẫn phụ thuộc chặt chẽ.

Ví dụ:

~~~text
                    LEGACY DATABASE
                 +----------------------+
                 | customers            |
                 | orders               |
                 | order_items          |
                 | inventory            |
                 | payments             |
                 +----------------------+
                   ^         ^       ^
                   |         |       |
              Checkout   Inventory  Billing
              Service    Service    Service
                 \_________ | ______/
                        SQL trực tiếp
~~~

Khi cả Checkout, Inventory và Billing tự đọc/ghi các bảng trên, một thay đổi schema hoặc quy tắc nghiệp vụ có thể khiến nhiều service phải triển khai cùng lúc. Một service có thể cập nhật bảng của service khác mà không thông qua logic kiểm tra bất biến. Sự cố khóa bảng, connection pool hoặc migration cũng lan rộng hơn dự kiến.

**Mục tiêu không phải ngay lập tức tạo một database instance cho mỗi service.** Mục tiêu trước tiên là hình thành **quyền sở hữu dữ liệu và quyền ghi rõ ràng**:

> Mỗi dữ liệu nghiệp vụ quan trọng phải có một thành phần chịu trách nhiệm cho cách thay đổi nó. Những thành phần khác truy cập qua hợp đồng được quản lý thay vì tự sửa bảng của chủ dữ liệu.

Trong nhiều môi trường, giai đoạn đầu vẫn có thể dùng cùng database server nhưng tách schema, tài khoản, quyền và contract. Sau khi giảm phụ thuộc logic, mới có thể tách storage vật lý khi có đủ lợi ích về triển khai, mở rộng hoặc isolation.

Bài này hướng dẫn một lộ trình **tăng dần, có kiểm chứng và có thể dừng ở từng mốc**, phù hợp hệ thống cũ cần tiếp tục phục vụ người dùng trong suốt chuyển đổi.

## 2. Học xong bài này bạn cần làm được gì?

- Nhận diện các kiểu phụ thuộc dữ liệu trong legacy system và chọn thứ tự tháo gỡ.
- Lập bản đồ bảng, cột, truy vấn, job, stored procedure, report và các ứng dụng đang sử dụng.
- Phân biệt **database per service** về quyền sở hữu với yêu cầu “mỗi service một máy chủ database”.
- Thiết kế lộ trình từ shared database sang **single writer**, đọc qua API/event hoặc read model riêng.
- Chuyển đổi theo kỹ thuật **expand–migrate–contract**, backfill, CDC, transactional outbox và reconciliation.
- Xử lý thay đổi schema tương thích, giao dịch xuyên service, out-of-order event và dữ liệu tạm thời chưa đồng bộ.
- Thực hiện cutover, rollback và quan sát mà không mặc định dual write là an toàn.
- Chuyển cross-service SQL joins, report và batch jobs sang kiến trúc dữ liệu phù hợp.
- Đề xuất tiêu chí hoàn thành theo bằng chứng thay vì chỉ đếm số database tách ra.

## 3. Hiểu đúng shared database và quyền sở hữu dữ liệu

### 3.1. Một số trạng thái thường gặp

| Trạng thái | Đặc điểm | Rủi ro nổi bật |
|---|---|---|
| **Shared database, shared tables** | Nhiều ứng dụng đọc/ghi cùng bảng | Bất biến bị vượt qua, migration ảnh hưởng rộng |
| **Shared database, separate schemas** | Mỗi service có schema nhưng có thể còn query chéo | Coupling qua SQL và transaction |
| **Single writer, shared readers** | Một chủ ghi; nhiều bên đọc trực tiếp | Các reader vẫn phụ thuộc schema nội bộ |
| **Single owner, contract-based access** | Bên ngoài gọi API/event, không query bảng của chủ | Cần quản trị hợp đồng, availability và consistency |
| **Independent persistence** | Chủ dữ liệu có storage, backup, migration và cấp quyền riêng | Cần đầu tư vận hành và tích hợp dữ liệu |

Đây không phải năm bước bắt buộc phải đi tuần tự với mọi bảng. Một bảng chỉ dùng bởi một module có thể tách trực tiếp. Một bảng có nhiều consumer hoặc giao dịch phức tạp cần nhiều pha hơn.

### 3.2. Database per service là nguyên tắc ownership

Trong kiến trúc microservices, database per service thường diễn đạt rằng **service sở hữu và kiểm soát dữ liệu của nó; không service khác được tự do truy cập storage nội bộ**.

Điều này **không nhất thiết** có nghĩa:

- Một server vật lý hoặc cluster database riêng cho mỗi service.
- Mỗi entity JPA bắt buộc là một service.
- Không được dùng cùng công nghệ database.
- Cấm hoàn toàn replication hoặc dữ liệu dẫn xuất ở consumer.
- Bỏ mọi SQL join trong phạm vi một service.

Có thể bắt đầu bằng schema riêng, role riêng và quyền truy cập được thực thi, miễn các đường truy cập ngoài ownership được quản lý. Tách vật lý là lựa chọn vận hành tiếp theo, không phải điều kiện tiên quyết để cải thiện ranh giới nghiệp vụ.

### 3.3. Những phụ thuộc khó nhìn thấy

Đừng chỉ nhìn repository chính. Một database dùng chung còn có thể bị truy cập bởi:

- Ứng dụng web cũ, batch worker, command-line tools.
- Stored procedure, trigger và scheduled database job.
- BI/reporting, ETL, dashboard, data export.
- Admin scripts, data-fix, cron hoặc migration thủ công.
- Third-party integration, CRM, ERP, ứng dụng nội bộ.
- Process đồng bộ cache, Elasticsearch và search indexing.
- Tài khoản database dùng chung bởi nhiều deployment.
- Test fixtures và công cụ seed dữ liệu.

Nếu bỏ sót, việc thay quyền có thể khiến một job chạy hằng tháng hỏng dù các request online đều ổn.

## 4. Bắt đầu bằng bản đồ dữ liệu và các luồng truy cập

### 4.1. Lập inventory cho bảng và consumer

Ví dụ bảng khảo sát:

| Bảng | Đơn vị nghiệp vụ | Đang ghi bởi | Đang đọc bởi | Invariant quan trọng | Chủ đề xuất |
|---|---|---|---|---|---|
| customers | Customer | Legacy app, CRM sync | Checkout, Billing, Support | Trạng thái và định danh khách hợp lệ | Customer |
| orders | Order | Checkout, batch import | Billing, Fulfillment, BI | Vòng đời đơn hàng hợp lệ | Checkout |
| order_items | Order | Checkout | Catalog, BI | Tổng đơn khớp các dòng hàng | Checkout |
| stock_balances | Inventory | Inventory, legacy batch | Checkout, ERP | Không giữ/bán vượt số lượng có thể cấp | Inventory |
| payments | Payment | Payment, reconciliation job | Checkout, Billing, BI | Không thu một giao dịch hai lần | Payment |

Mọi giá trị ở bảng là **tình huống minh họa**. Quyền sở hữu phải được xác minh với domain expert và hệ thống đang chạy.

Nên thêm vào bảng inventory:

- Tên database/schema/table/column, dữ liệu nhạy cảm và độ lớn.
- Consumer/service, **loại thao tác** (SELECT, INSERT, UPDATE, DELETE, DDL).
- Query mẫu, tần suất, peak throughput, latency và transaction boundary.
- Bảng được join cùng; foreign key, trigger, view, stored procedure phụ thuộc.
- Quy trình deploy/backup/restore và người chịu trách nhiệm.
- Dữ liệu gốc hay dữ liệu dẫn xuất; cách tái dựng nếu bị mất.
- Mức ưu tiên nghiệp vụ và mức độ rủi ro khi thay đổi.

### 4.2. Tìm bằng chứng bằng nhiều nguồn

Có thể kết hợp:

1. **Source code/static search:** tìm table name, ORM mapping, raw SQL, repository và stored procedure.
2. **Database audit/query logs:** biết tài khoản nào truy cập bảng nào, khi nào và thao tác gì.
3. **Application traces:** kết nối query với HTTP request, job và business flow.
4. **DB permissions:** xác định tài khoản có quyền quá rộng dù ít sử dụng.
5. **CI/CD và migration history:** biết ai sửa schema và những thay đổi bắt buộc deploy phối hợp.
6. **Trao đổi người vận hành/nghiệp vụ:** tìm report, script hoặc batch job không nằm trong repository chính.

Không nên chỉ dựa vào log một ngày rồi kết luận “không ai sử dụng bảng này”. Cần xem chu kỳ cuối tháng/quý, xử lý thủ công, mùa cao điểm và các jobs chạy không thường xuyên.

### 4.3. Sơ đồ đường phụ thuộc

~~~text
             +-------------------+
             | customers table   |
             +-------------------+
                  ^  ^   ^  ^
                  |  |   |  |
              CRM  |   |  Billing
                   |   |
                Checkout  Support UI

             +-------------------+
             | stock_balances    |
             +-------------------+
                  ^         ^
                  |         |
              Inventory   Legacy job

             +-------------------+
             | orders            |
             +-------------------+
                 ^         ^
                 |         |
              Checkout   Fulfillment
~~~

Những đường **ghi** cần được phân biệt với đường **đọc**. Một table có nhiều writer thường cần được ưu tiên giải quyết sớm vì nguy cơ phá bất biến cao hơn. Tuy nhiên, một đường đọc trực tiếp có traffic lớn cũng có thể là trở ngại lớn cho thay schema về sau.

## 5. Xác định ranh giới nghiệp vụ, không tách theo tên bảng

Một bảng không nhất thiết tương ứng một service; nhiều bảng có thể cùng nằm trong một aggregate hoặc bounded context.

Ví dụ:

- **Order** và **OrderLine** có thể thuộc cùng bounded context Checkout.
- **PaymentAttempt** và **Refund** có thể thuộc Payment.
- **StockBalance** và **InventoryReservation** có thể phải cùng tham gia bảo vệ invariant Inventory.
- **CustomerProfile** có thể khác **BillingAccount** dù cùng chứa một customerId.

Khi quyết định ownership, hỏi:

1. Ai chịu trách nhiệm nghiệp vụ cho dữ liệu này?
2. Ai có quyền quyết định trạng thái hợp lệ và transition?
3. Invariant nào phải được giữ atomic?
4. Những thay đổi nào thường xảy ra cùng nhau?
5. Ai có thể triển khai, kiểm thử, giám sát và khôi phục độc lập?
6. Dữ liệu được phép lặp lại tại consumer dưới dạng read model không?
7. Ai chịu trách nhiệm xác định nguồn sự thật khi các bản sao khác nhau?

**Cùng database không chứng minh phải cùng bounded context.** Ngược lại, tách vật lý hai bảng cần cùng local transaction mà chưa có lý do nghiệp vụ rõ có thể gây phức tạp phân tán không đáng có.

## 6. Ưu tiên giải quyết multi-writer trước

Một bảng do nhiều ứng dụng trực tiếp ghi tạo ra những câu hỏi khó:

- Các ứng dụng có cùng thực thi validation và invariant không?
- Có ai bỏ qua optimistic locking, trạng thái nghiệp vụ hay audit không?
- Có trigger làm side effect ẩn?
- Một writer có thể ghi đè dữ liệu mới bằng snapshot cũ?
- Ai chịu trách nhiệm khi hai writer cập nhật cạnh tranh?

**Single writer** nghĩa là một service hoặc một module được ủy quyền duy nhất kiểm soát **các thay đổi nghiệp vụ** của dữ liệu. Nó không loại trừ replica, backup, job vận hành được kiểm soát hoặc database internal processes.

Lộ trình chuyển:

~~~text
Trước:
  Checkout ---- UPDATE stock_balances ----+
  Legacy Job -- UPDATE stock_balances ----+--> Shared DB
  Inventory --- UPDATE stock_balances ----+

Sau giai đoạn single writer:
  Checkout ---- ReserveInventory command --+
  Legacy Job -- ReconcileStock command ----+--> Inventory Service
  Inventory -------------------------------+--> stock_balances
~~~

Điểm quan trọng là tất cả đường ghi đều đi qua cùng quy tắc domain, không phải chỉ đổi tên user database. Nếu legacy job thực sự làm inventory adjustment, cần operation riêng có audit, idempotency và phân quyền chứ không cho nó gọi API reserve giả mạo nghiệp vụ.

### 6.1. Quy trình giảm writer

1. Liệt kê mọi writer đang tồn tại, gồm batch/admin.
2. Xác định invariant và bộ điều khiển trạng thái.
3. Tạo API/command chính thức tại chủ dữ liệu.
4. Chuyển từng writer cũ sang interface mới bằng feature flag hoặc adapter.
5. Quan sát kết quả, lỗi và hiệu năng.
6. Cắt quyền UPDATE/INSERT/DELETE không còn hợp lệ.
7. Duy trì audit cho các thao tác sửa dữ liệu đặc biệt.
8. Khi tất cả writer ngoài owner đã ngừng, xác minh không còn đường bypass.

Quyền database là **lớp thực thi ranh giới**. Nếu service khác vẫn có quyền UPDATE toàn bộ schema, một lần refactor trong tương lai có thể làm sống lại shared database coupling.

## 7. Lộ trình tổng thể nhiều pha, không cần “big bang”

Một kế hoạch khả thi:

| Pha | Mục tiêu | Thay đổi chính | Điều kiện để sang bước tiếp |
|---|---|---|---|
| **0. Đo hiện trạng** | Biết ai đọc/ghi gì | Inventory query, quyền, transaction, schema | Đủ bản đồ consumer và bất biến quan trọng |
| **1. Chặn coupling mới** | Không mở rộng shared DB | Quy tắc kiến trúc, review, cảnh báo truy cập chéo | Không có writer/read mới không đăng ký |
| **2. Single writer** | Chỉ owner ghi dữ liệu | Command/API nội bộ, adapter legacy, revoke write | Invariant và luồng ghi hoạt động ổn định |
| **3. Tách đường đọc** | Consumer không phụ thuộc schema nội bộ | Query API, event, read model, reporting pipeline | Có phương án giữ độ mới và đối soát |
| **4. Tách storage logic** | Schema/role/migration do owner kiểm soát | Schema riêng, grants, migration ownership | Không còn cross-schema SQL bắt buộc |
| **5. Di chuyển storage khi cần** | Independence vật lý | Backfill, CDC/outbox, shadow read/write cutover | Đối soát khớp và rollback có kế hoạch |
| **6. Dọn legacy** | Loại bỏ bảng và quyền cũ | Contract, drop sau retention và evidence | Không còn consumer hợp lệ bị ảnh hưởng |

Các pha có thể xen kẽ theo từng domain. Hệ thống lớn nên chọn **một vertical slice nghiệp vụ** trước, tránh migrate mọi bảng đồng thời.

### Vì sao nên tách từng lát?

- Phạm vi blast radius nhỏ.
- Có thể so sánh trước/sau trên một luồng thật.
- Mỗi pha tạo một trạng thái trung gian hợp lệ.
- Có cơ hội điều chỉnh contract trước khi nhiều consumer phụ thuộc.
- Giữ khả năng rollback ở các mốc quan trọng.
- Nhóm vận hành có thời gian học các failure mode mới.

## 8. Pha 0: đo baseline trước khi sửa

Trước khi chuyển quyền sở hữu, ghi lại số liệu hiện tại:

- API latency p50/p95/p99 của các luồng quan trọng.
- Tỷ lệ lỗi, timeout, deadlock và transaction conflict.
- Tần suất migration schema và số lần phải deploy nhiều ứng dụng cùng nhau.
- Query load và connection pool theo consumer.
- Thời gian khôi phục sau lỗi DB, backup/restore và RPO/RTO nếu có.
- Số thao tác ghi bảng quan trọng theo từng writer.
- Số bảng bị đọc/ghi chéo và số report phụ thuộc join trực tiếp.
- Số bất biến có nguy cơ bị vi phạm do đường ghi không kiểm soát.

Mục tiêu không phải tối ưu một metric duy nhất. Tách dữ liệu có thể làm tăng network hop nhưng giảm change coupling, rủi ro schema và blast radius. Cần nêu guardrails để tránh hy sinh tính đúng đắn hoặc SLO.

**Ví dụ mục tiêu minh họa:** “Sau ba chu kỳ phát hành, không còn writer trực tiếp vào inventory ngoài Inventory Service; mọi event đồng bộ tồn kho đều có idempotency; p95 checkout không vượt SLO.” Không nên lấy các ngưỡng minh họa làm chuẩn chung.

## 9. Pha 1: ngăn tạo thêm phụ thuộc shared DB

Nếu nhóm đang chuyển đổi mà service mới tiếp tục SELECT/UPDATE trực tiếp bảng chung, khoản nợ kiến trúc tăng nhanh hơn tốc độ giảm.

Các biện pháp:

1. Công bố **data ownership catalog**: bảng/schema nào do domain nào sở hữu.
2. Quy định service mới không được dùng cùng broad-privilege DB user.
3. Thêm kiểm tra review cho SQL chéo context.
4. Đặt role riêng, giới hạn quyền theo nhu cầu thực tế.
5. Quản lý migration bằng pipeline có owner, không cho service khác tùy ý đổi schema của owner.
6. Giới hạn các ngoại lệ có thời hạn, người phê duyệt và kế hoạch loại bỏ.
7. Theo dõi các query trực tiếp còn tồn tại như một **compatibility backlog**.

Có thể giữ **legacy compatibility view** để giảm tác động, nhưng view không phải ranh giới service hoàn chỉnh nếu consumer vẫn phụ thuộc tên cột và semantics nội bộ. Hãy ghi rõ thời gian sống và người sở hữu view.

### 9.1. Quy tắc dependency qua database

~~~text
ĐƯỢC:
  Checkout -> Orders data thuộc Checkout
  Billing  -> API OrderSummary của Checkout
  Analytics <- event hoặc read model được thiết kế

CHỈ TẠM THỜI:
  Billing -> read-only compatibility view của Orders,
             có owner, tài liệu và thời hạn loại bỏ

KHÔNG ĐƯỢC VỀ LÂU DÀI:
  Billing -> UPDATE orders.status
  Checkout -> trực tiếp UPDATE inventory.quantity
~~~

Không phải mọi SELECT chéo bảng đều nguy hiểm như multi-writer, nhưng chúng vẫn làm contract rò rỉ qua schema.

## 10. Pha 2: đưa đường ghi về chủ dữ liệu

Ví dụ hệ thống cũ dùng cùng bảng inventory.

### 10.1. Trạng thái ban đầu

~~~sql
-- Ví dụ minh họa, KHÔNG phải schema production đầy đủ.
CREATE TABLE stock_balances (
    sku TEXT PRIMARY KEY,
    available_quantity INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
~~~

Checkout kiểm tra rồi tự trừ:

~~~sql
SELECT available_quantity
FROM stock_balances
WHERE sku = 'SKU-42';

-- Sau nhiều bước xử lý khác...
UPDATE stock_balances
SET available_quantity = available_quantity - 2
WHERE sku = 'SKU-42';
~~~

Nếu hai request đồng thời đọc cùng quantity hoặc một ứng dụng bỏ qua invariant, có thể ghi thiếu an toàn. Thêm API không tự sửa race condition; **owner phải triển khai atomic invariant**.

### 10.2. Thiết kế command cho Inventory

Hợp đồng tối thiểu:

~~~http
POST /internal/v1/reservations
Authorization: Bearer <service-token>
Idempotency-Key: ord-947-line-1
Content-Type: application/json

{
  "orderId": "ord-947",
  "sku": "SKU-42",
  "quantity": 2
}
~~~

Inventory chịu trách nhiệm:

- Xác thực caller và quyền thao tác.
- Kiểm tra SKU và quy tắc số lượng.
- Bảo vệ invariant tồn kho.
- Tạo reservation bền vững với định danh ổn định.
- Lưu idempotency key để tránh reserve lặp khi retry.
- Trả mã lỗi nghiệp vụ như STOCK_NOT_AVAILABLE.
- Công bố trạng thái, expiry/confirm/release theo contract.

Checkout **không** cập nhật bảng stock_balances nữa, dù vẫn có thể lưu orderId và bản sao thông tin cần hiển thị.

### 10.3. Atomic update trong database owner

Ví dụ PostgreSQL minh họa:

~~~sql
UPDATE stock_balances
SET available_quantity = available_quantity - :quantity,
    updated_at = NOW()
WHERE sku = :sku
  AND available_quantity >= :quantity;
~~~

Chỉ khi số hàng được cập nhật bằng 1 mới được tiếp tục tạo reservation trong transaction thích hợp. Phải thiết kế **tổng lượng còn có thể bán, reservation đã giữ, release và expiration** thành một mô hình nhất quán; câu UPDATE trên chỉ minh họa một phần invariant.

Nếu reservation được tạo cùng thao tác giảm tồn kho, ghi reservation và cập nhật balance trong **cùng local transaction** để tránh giảm tồn nhưng không có reservation hoặc ngược lại. Idempotency record cũng phải nằm trong ranh giới transaction phù hợp.

### 10.4. Không biến API thành SQL từ xa

Một API như:

~~~http
POST /inventory/sql
{
  "query": "UPDATE stock_balances SET ..."
}
~~~

không phải tách ownership. Nó chỉ chuyển quyền sửa bảng qua mạng. API cần thể hiện **hành vi nghiệp vụ** (Reserve, Release, Adjust, Reconcile), không phải các thao tác CRUD tùy ý trên schema nội bộ.

## 11. Pha 3: thay đường đọc trực tiếp bằng hợp đồng

Một số consumer không cần tất cả cột của bảng owner. Có ba phương án phổ biến.

### 11.1. Đồng bộ qua Query API

~~~text
Billing ---> Checkout API: GET /orders/{id}/summary
~~~

Phù hợp khi consumer cần dữ liệu mới, lưu lượng vừa phải và phụ thuộc availability/latency được chấp nhận.

Cần công bố:

- Input, output, pagination/filter.
- Authentication và authorization theo tenant.
- Rate limit, timeout, caching, retry.
- Độ mới của dữ liệu và error semantics.
- Phiên bản contract và backward compatibility.

**Tránh “chatty API”:** thay một SQL JOIN bằng 300 request nhỏ để lấy từng item có thể gây latency cao và quá tải. Thiết kế operation theo **use case** hoặc batch query thay vì chỉ mô phỏng SELECT row-by-row.

### 11.2. Dữ liệu dẫn xuất qua event

~~~text
Checkout DB
     |
Transactional Outbox / Event Publisher
     |
     v
OrderCreated / OrderUpdated
     |
     +----> Billing Read Model
     +----> Fulfillment Read Model
     +----> Analytics
~~~

Consumer tự giữ bản sao dữ liệu **cần dùng**, do đó giảm gọi API đồng bộ. Đổi lại, cần thiết kế:

- Event identity/version và schema.
- Delivery ít nhất một lần, duplicate và ordering.
- Backfill/snapshot ban đầu.
- Lag và consistency window.
- Cách xử lý xóa dữ liệu, sửa sai và replay.
- Cách tránh chia sẻ dữ liệu nhạy cảm không cần thiết.

**Bản sao do consumer sở hữu không trở thành source of truth.** Nếu Payment hiển thị order amount được sao chép, Checkout vẫn sở hữu định nghĩa amount theo quy tắc Order; Payment chỉ dùng snapshot hợp lệ theo hợp đồng đã thỏa thuận.

### 11.3. Read model / CQRS / reporting store

Những truy vấn tổng hợp nhiều context thường phù hợp với:

- Read model xây riêng cho màn hình hoặc workflow.
- Search index/analytics warehouse.
- Materialized projection được cập nhật từ event.
- Data pipeline CDC/ETL có contract được quản lý.

Nếu cần report join trên Customer, Order, Payment, có thể tạo **data product/reporting mart** thay vì cho BI chạy join trực tiếp trên các database giao dịch của service. Với dữ liệu tài chính, báo cáo cần quy tắc đối soát và mốc chốt dữ liệu rõ ràng.

### 11.4. Chọn phương án đọc

| Nhu cầu | Phương án thường phù hợp | Đánh đổi |
|---|---|---|
| Kiểm tra trạng thái có thẩm quyền trước quyết định nghiệp vụ | Query API owner | Dependency đồng bộ, latency |
| Màn hình đọc nhiều, chấp nhận trễ vài giây | Local read model | Eventual consistency, backfill |
| Tìm kiếm phức tạp | Search projection | Đồng bộ index, lag/rebuild |
| Báo cáo lịch sử và join nhiều miền | Warehouse/data mart | Độ trễ pipeline, quản trị dữ liệu |
| Truy vấn kỹ thuật cũ đang cần thay gấp | Compatibility view tạm | Chưa loại được schema coupling |

## 12. Pha 4: tách schema và quyền database

Một giai đoạn trung gian tốt có thể là **cùng PostgreSQL cluster, schema khác nhau**:

~~~text
PostgreSQL instance
  |
  +-- checkout_schema
  |     orders
  |     order_items
  |
  +-- inventory_schema
  |     stock_balances
  |     reservations
  |
  +-- payment_schema
        payment_attempts
        refunds
~~~

Mỗi service:

- Có database role riêng.
- Có quyền SELECT/INSERT/UPDATE/DELETE trong schema được sở hữu theo nhu cầu.
- Không có quyền DML trên schema service khác, trừ ngoại lệ tạm thời được ghi nhận.
- Có migration pipeline/owner duy nhất cho schema của mình.
- Có quản lý secret và audit riêng.
- Có backup/restore phù hợp với yêu cầu dữ liệu.

Ví dụ SQL minh họa tư duy phân quyền PostgreSQL:

~~~sql
CREATE ROLE checkout_app LOGIN PASSWORD '<managed-secret>';
CREATE ROLE inventory_app LOGIN PASSWORD '<managed-secret>';

CREATE SCHEMA IF NOT EXISTS checkout_schema;
CREATE SCHEMA IF NOT EXISTS inventory_schema;

REVOKE ALL ON SCHEMA inventory_schema FROM PUBLIC;
GRANT USAGE ON SCHEMA inventory_schema TO inventory_app;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA inventory_schema
TO inventory_app;

-- Khi đã chuyển hết consumer:
REVOKE ALL ON ALL TABLES IN SCHEMA inventory_schema
FROM checkout_app;
~~~

Lưu ý:

- Đây không phải script đầy đủ để triển khai production: còn quyền CONNECT, schema owner, sequence, default privileges, extension, kế thừa role, trigger/function và migration credentials.
- Không nên hardcode password thật; dùng secret manager phù hợp.
- Quyền của role có thể đến từ membership hoặc quyền database khác, cần rà soát trước khi tuyên bố isolation.
- Không thu hồi một quyền bất ngờ trước khi biết tất cả đường truy cập. Dùng quan sát và kế hoạch cutover.
- Nếu service chạy chung database server, lỗi server hoặc resource contention vẫn có blast radius chung.

## 13. Pha 5: chuyển dữ liệu sang storage riêng khi thật sự cần

Sau khi single ownership và contract đã ổn định, chuyển một bounded context sang database riêng dễ hơn vì không còn nhiều writer ngoài chủ dữ liệu.

Ví dụ:

~~~text
Trước migration:
  Inventory Service ---> shared_db.inventory_schema

Sau migration:
  Inventory Service ---> inventory_db

Consumer khác ---> Inventory API / events
~~~

### 13.1. Quy trình expand – migrate – contract

**Expand:** thêm schema mới, endpoint/adapter, event format và khả năng đồng bộ mà không phá đường cũ.

**Migrate:** backfill dữ liệu, tiếp nhận thay đổi phát sinh sau snapshot, đối chiếu, chuyển dần đọc/ghi.

**Contract:** bỏ code, quyền và bảng cũ khi không còn consumer và rollback không phụ thuộc vào chúng.

~~~text
Expand
  +-- tạo database/table mới
  +-- bổ sung cách xuất thay đổi
  +-- giữ đường cũ hoạt động

Migrate
  +-- snapshot + backfill
  +-- CDC/outbox đồng bộ delta
  +-- shadow compare
  +-- chuyển read/write có kiểm soát

Contract
  +-- gỡ truy cập direct SQL cũ
  +-- ngừng sync dư thừa
  +-- xóa schema/bảng cũ theo lịch và chính sách
~~~

Không xóa source quá sớm. Sau cutover vẫn cần khoảng thời gian xác minh, khả năng phục hồi và chính sách lưu trữ hợp lệ.

### 13.2. Khái niệm snapshot và delta

Một phương án phổ biến:

1. Chọn mốc nhất quán từ source database.
2. Copy snapshot dữ liệu thuộc owner sang target.
3. Theo dõi các thay đổi phát sinh sau mốc bằng CDC hoặc outbox/change log phù hợp.
4. Áp các delta theo thứ tự và idempotency cần thiết.
5. Xác minh số record, key, version, checksum và invariant.
6. Chỉ chuyển traffic khi lag đủ thấp và target đáp ứng điều kiện consistency đã đặt.

**Khó khăn lớn:** không được có “khoảng trống” giữa mốc snapshot và lúc bắt đầu nhận delta. Phải xác định rõ transaction/LSN/offset hoặc cơ chế watermark nhất quán theo công nghệ đang dùng. Lấy snapshot thường rồi bật CDC sau vài phút có thể bỏ sót dữ liệu.

### 13.3. Backfill theo lô

Nếu bảng lớn, nên đọc theo **khóa ổn định** hoặc chiến lược phân trang bền vững:

~~~sql
-- Ví dụ keyset pagination trên ID được index.
SELECT id, sku, available_quantity, version
FROM inventory_schema.stock_balances
WHERE id > :last_id
ORDER BY id
LIMIT :batch_size;
~~~

Ghi target bằng upsert có version guard:

~~~sql
INSERT INTO stock_balances (id, sku, available_quantity, version)
VALUES (:id, :sku, :quantity, :version)
ON CONFLICT (id)
DO UPDATE SET
  sku = EXCLUDED.sku,
  available_quantity = EXCLUDED.available_quantity,
  version = EXCLUDED.version
WHERE stock_balances.version < EXCLUDED.version;
~~~

Mã SQL là **minh họa**, cần điều chỉnh để tránh ghi đè trạng thái mới hơn bằng snapshot cũ và xử lý delete/tombstone đúng. Với bảng liên tục có insert/update/delete, chỉ dùng keyset backfill không đủ để bắt mọi thay đổi; phải kết hợp change capture và kiểm tra mốc.

### 13.4. Xử lý xóa

Một lỗi thường gặp là chỉ đồng bộ INSERT và UPDATE, rồi target còn record đã bị xóa trong source. Cần chiến lược rõ:

- Hard delete với change event/tombstone.
- Soft delete có trạng thái và thời điểm hiệu lực.
- Chống hồi sinh dữ liệu khi replay event cũ.
- Cân nhắc nghĩa vụ xóa dữ liệu cá nhân cả ở archive, backup, read model và search index.

Không thể tuyên bố hai database tương đương nếu chỉ so tổng số hàng mà bỏ qua bản ghi đã xóa hoặc trạng thái có hiệu lực.

## 14. Vì sao dual write trực tiếp nguy hiểm?

Một cách làm dễ nghĩ đến:

~~~text
Inventory Service
      |
      +--> UPDATE shared_db.stock_balances
      |
      +--> UPDATE inventory_db.stock_balances
~~~

Hai thao tác thường **không nằm trong một local transaction**. Nếu ghi source thành công nhưng ghi target timeout, dữ liệu phân kỳ. Nếu retry cả hai, source có thể bị tác động lần nữa. Nếu một transaction rollback nhưng message/event đã phát, consumer có thể nhận trạng thái không bao giờ commit.

Tránh giả định “gọi hai database lần lượt là đồng bộ an toàn”. Những lựa chọn tốt hơn, tùy yêu cầu:

1. **Single writer + CDC:** nguồn cũ vẫn là chủ trong giai đoạn chuyển, hệ thống mới đồng bộ từ changelog.
2. **Transactional outbox:** ghi trạng thái và outbox event trong một transaction, relay event đến hệ thống khác; consumer idempotent.
3. **Migration adapter có reconciliation:** nếu không thể tránh ghi hai nơi tạm thời, cần định nghĩa nguồn sự thật, conflict resolution, retry và audit rõ.
4. **Cutover một chiều:** khi target trở thành authoritative, ngừng writer vào source thay vì duy trì song song vô hạn.

Cần phân biệt **dual read để so sánh** (không tác động) với **dual write để cập nhật** (có nguy cơ phân kỳ). Một thời kỳ shadow read thường an toàn hơn nhưng vẫn phải bảo vệ PII và tải database.

### 14.1. Transactional outbox

~~~text
Legacy/Owner Database transaction:
  UPDATE business_table
  INSERT outbox_event
  COMMIT
           |
           v
Outbox publisher
           |
          Broker
           |
        Consumer
           |
       Upsert target
~~~

Outbox giảm rủi ro “data commit rồi event không được ghi nhận”, nhưng publisher vẫn có thể phát trùng. Consumer phải dùng eventId, aggregateId/version hoặc business key để đảm bảo hiệu ứng idempotent. Outbox không tự đảm bảo eventual-consistency lag luôn dưới một ngưỡng nếu broker/publisher chậm.

### 14.2. Change Data Capture (CDC)

CDC có thể lấy thay đổi từ database log để cấp dữ liệu cho pipeline migration hoặc read model. Ưu điểm: không cần sửa từng writer cũ ngay để phát event. Đánh đổi:

- Schema vật lý vẫn có thể rò rỉ ra consumer nếu phát raw table changes trực tiếp.
- Không phải row change nào cũng thể hiện đúng ý nghĩa nghiệp vụ.
- Phải xử lý snapshot, ordering, delete, schema evolution và lag.
- Cần bảo vệ connector/replication slot/log retention và khả năng recovery.
- Có thể tạo thêm tải và quyền truy cập dữ liệu nhạy cảm.

CDC rất hữu ích làm **cầu chuyển đổi**, nhưng không nhất thiết là hợp đồng event nghiệp vụ lâu dài. Có thể bổ sung layer biến đổi sang event có ngữ nghĩa ổn định.

## 15. Tách đọc trước hay tách ghi trước?

Không có một thứ tự đúng cho mọi domain.

### 15.1. Thường ưu tiên single writer

Nếu nhiều hệ thống cùng UPDATE một bảng quan trọng, hãy ưu tiên gom quyền ghi và bất biến về một chủ. Điều này giảm rủi ro dữ liệu và tạo nền tảng để tách storage sau.

### 15.2. Đôi khi tách đọc trước dễ hơn

Ví dụ, báo cáo chạy SELECT rất nặng trên transaction database. Di chuyển reporting sang read replica/warehouse có thể giảm tải nhanh, ít đụng tới luồng giao dịch. Nhưng phải ghi nhận rằng **schema coupling có thể còn** nếu báo cáo vẫn trực tiếp hiểu bảng nội bộ.

### 15.3. Chọn theo ma trận

| Tình huống | Bước đầu nên cân nhắc | Lý do |
|---|---|---|
| Nhiều writer cùng bảng tiền/tồn kho | Chuyển sang single writer | Bảo vệ invariant |
| Reporting gây chậm database giao dịch | Tách read/reporting pipeline | Giảm contention |
| Một bounded context đã độc lập, bảng ít liên kết | Tách schema và role | Chi phí thấp, ích lợi rõ |
| Consumer query chéo nhiều bảng | Tạo API/read model theo use case | Giảm phụ thuộc schema |
| Hệ thống có nhiều stored procedure xuyên miền | Xác định trách nhiệm và transaction trước | Không thể tách cơ học theo tên bảng |
| Cần scale/restore dữ liệu riêng | Tách storage sau khi contract ổn định | Tránh migration nhiều writer |
| Legacy không thể sửa ngay | Compatibility adapter/view tạm | Chuyển đổi từng bước |

**Ưu tiên theo rủi ro và khả năng kiểm chứng**, không theo số lượng bảng dễ tách để báo cáo tiến độ đẹp.

## 16. Giao dịch xuyên service sau khi tách dữ liệu

Shared database trước đây có thể dùng một SQL transaction để cập nhật Order, Inventory và Payment. Khi mỗi domain có database riêng, một transaction ACID duy nhất không còn là giả định an toàn.

Ví dụ:

~~~text
Trước:
BEGIN;
  INSERT orders;
  UPDATE inventory;
  INSERT payment_record;
COMMIT;

Sau:
  Checkout -> tạo Order = PENDING
  Checkout -> gửi command giữ tồn
  Inventory -> tạo Reservation
  Checkout -> yêu cầu PaymentAuthorization
  Payment -> ghi kết quả
  Checkout -> xác nhận Order hoặc bù trừ
~~~

Phải thiết kế **workflow và consistency**, không chỉ thay connection string.

### 16.1. Saga và trạng thái trung gian

Một phương án minh họa:

~~~text
Order(PENDING)
   |
ReserveInventory
   +-- fail ------> Order(REJECTED)
   |
   v
PaymentAuthorize
   +-- fail ------> ReleaseReservation -> Order(REJECTED)
   |
   v
ConfirmOrder
   |
   v
Order(CONFIRMED)
~~~

Các bước có thể đồng bộ hoặc bất đồng bộ tùy yêu cầu. Cần định nghĩa:

- Ai là **orchestrator** hoặc có cơ chế choreography?
- Idempotency key cho từng command và callback?
- Làm gì nếu request timeout nhưng operation thực tế đã thành công?
- Compensation nào hợp lệ và compensation nào không đảo ngược được?
- Khi nào Order ở PENDING quá lâu cần đối soát?
- Event có thể đến trùng/out-of-order thì xử lý ra sao?
- Có deadline tổng thể nhưng workflow tiếp tục nền sau khi API trả 202 không?

**Saga không thay thế transaction nội bộ.** Mỗi service vẫn phải bảo vệ invariant local trong một transaction phù hợp. Không gọi bù trừ một cách máy móc khi không biết kết quả bước trước.

### 16.2. Không “join giao dịch” bằng distributed lock tùy tiện

Phân tán database có thể khiến nhóm muốn tạo một distributed lock toàn cục để mô phỏng một transaction cũ. Điều này thường thêm latency, điểm lỗi và câu hỏi về lock lease/fencing. Trước tiên xác định invariant nào thực sự cần đồng bộ và ai phải sở hữu chúng; chỉ dùng cơ chế khóa phân tán khi có lý do và thiết kế chịu lỗi rõ.

## 17. Foreign key, constraint và join xuyên database

Khi tách database, foreign key xuyên hai storage độc lập thường không còn là phương án dựa vào cùng một RDBMS transaction.

Ví dụ:

~~~text
checkout_db.orders.customer_id
         |
         | chỉ lưu ID tham chiếu có ý nghĩa
         v
customer_db.customers.id
~~~

Các lựa chọn:

- Checkout lưu **customerId** như một tham chiếu nghiệp vụ và xác minh tính hợp lệ qua API hoặc snapshot theo contract.
- Customer công bố event lifecycle; Checkout xây read model tối thiểu để kiểm tra/hiển thị khi nghiệp vụ chấp nhận độ trễ.
- Dữ liệu được snapshot vào Order theo yêu cầu pháp lý/nghiệp vụ, ví dụ tên nhận hàng tại thời điểm đặt đơn; snapshot này không phải bản sao profile luôn cập nhật.
- Khi Customer bị xóa/vô hiệu, các service liên quan cần chính sách rõ cho historical orders và yêu cầu quyền riêng tư.

Không nên kỳ vọng “eventual consistency tự sửa mọi tham chiếu mồ côi”. Nếu có invariant bắt buộc mạnh, hãy đặt nó trong một owner hoặc thiết kế giao thức xác nhận tương ứng.

### 17.1. Truy vấn join phục vụ UI

Thay vì Billing trực tiếp join 5 bảng của Checkout/Customer, có thể:

1. API composition ở BFF/gateway chuyên dụng (cẩn thận N+1).
2. Query API của owner trả dữ liệu được phép, có batch/pagination.
3. Read model kết hợp nhiều nguồn qua event.
4. Warehouse cho báo cáo lịch sử không cần tức thời.

Mỗi phương án cần contract về **độ mới**, **độ tin cậy**, **quyền dữ liệu** và **latency**. Không chuyển một SQL join 20 ms thành 100 RPC mà không đo hiệu năng và failure modes.

## 18. Anti-corruption layer cho hệ thống cũ

Một module legacy có thể biết bảng theo cách rất khác domain mới. **Anti-corruption layer (ACL)** chuyển đổi giữa mô hình cũ và ngôn ngữ nghiệp vụ mới mà không để những tên cột/phụ thuộc cũ rò rỉ khắp hệ thống.

~~~text
New Checkout Domain
       |
       v
Order Repository Port
       |
       +-- LegacyOrderAdapter -----> shared_db.orders
       |
       +-- NewOrderAdapter --------> checkout_db.orders
~~~

Dùng branch-by-abstraction và feature flag có thể chuyển từng use case sang adapter mới. Nhưng **không** để hai adapter cùng ghi hai nguồn độc lập vô điều kiện. Quy định chính xác khi nào adapter nào là authoritative, cách shadow compare và cutover.

### 18.1. Mẫu interface Java

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}

public final class LegacyOrderRepository implements OrderRepository {
    // Ánh xạ từ legacy schema sang domain model.
    // Trong giai đoạn này legacy DB có thể vẫn authoritative.
}

public final class NewOrderRepository implements OrderRepository {
    // Lưu theo schema do Checkout sở hữu.
}
~~~

Interface trên chỉ minh họa boundary; implementation phải xử lý transaction, concurrency, security và error mapping phù hợp.

Một **strangler pattern** có thể dần chuyển từng tuyến nghiệp vụ từ legacy sang service mới. Chuyển traffic đúng còn phải đi kèm chuyển ownership dữ liệu; chỉ route HTTP sang service mới nhưng vẫn để mọi service UPDATE shared DB chưa giải quyết cốt lõi.

## 19. Ví dụ migration thực tế: tách Inventory khỏi shared DB

Giả sử hiện trạng:

~~~text
Legacy App ---- UPDATE stock_balances ----+
Checkout ------ UPDATE stock_balances ----+--> Shared DB
Inventory ----- UPDATE stock_balances ----+
ERP Job ------- UPDATE stock_balances ----+
~~~

### Giai đoạn A: xác minh và chuẩn hóa invariant

- Kiểm kê mọi writer/reader, stored procedure và ERP batch.
- Xác định thế nào là **available**, **reserved**, **committed**, **released**.
- Thiết kế invariant không bán vượt và mô hình xử lý adjustment.
- Thống nhất ai có quyền làm StockAdjustment, Reserve, Release, Reconcile.
- Định nghĩa lỗi, idempotency, audit và quyền truy cập.

### Giai đoạn B: tạo Inventory command API

- Inventory triển khai Reserve/Release/Adjust.
- Checkout chuyển UPDATE trực tiếp sang Reserve command.
- Legacy và ERP job được chuyển dần qua adapter phù hợp.
- Đo kết quả nghiệp vụ, latency và lệnh bị duplicate.
- Các luồng chưa chuyển được ghi nhận như ngoại lệ có deadline.

### Giai đoạn C: single writer tại shared DB

- Chỉ Inventory Service còn ghi inventory schema.
- Revoke quyền ghi của các ứng dụng khác sau khi xác minh.
- Các reader tiếp tục hoạt động tạm thời nhưng có kế hoạch thay thế.
- Trigger và job cũ được kiểm tra để không tạo writer ẩn.

### Giai đoạn D: tách reader

- Checkout dùng trả lời Reserve/Query API thay vì SELECT balance trực tiếp khi cần authoritative.
- UI xem tồn kho dùng event-driven projection với độ mới được công bố.
- BI/ERP nhận dữ liệu qua export/event/feed có contract.
- Giảm dần quyền SELECT trực tiếp vào inventory.

### Giai đoạn E: di chuyển storage

- Tạo inventory_db với schema phù hợp.
- Snapshot + CDC/outbox đồng bộ thay đổi từ nguồn authoritative.
- Shadow compare bản ghi, version, tổng available/reserved và các bất biến.
- Chuyển đường ghi Inventory sang database mới theo runbook có kiểm soát.
- Sau đó chuyển đường đọc authoritative của Inventory sang database mới.
- Chỉ khi đủ bằng chứng mới khóa/xóa đường ghi ở source cũ.

### Giai đoạn F: contract và dọn dẹp

- Gỡ compatibility views/permissions không còn dùng.
- Dừng connector/CDC migration dư thừa.
- Archive hoặc xóa bảng cũ theo retention và nghĩa vụ dữ liệu.
- Chuyển trách nhiệm migration, backup và runbook cho Inventory owner.
- Đo lại tần suất deploy phối hợp và chất lượng dịch vụ.

**Điểm mấu chốt:** quá trình này có thể kéo dài nhiều đợt phát hành, nhưng mỗi giai đoạn đều mang lại giảm rủi ro hoặc giảm coupling có thể quan sát.

## 20. Cutover đọc, cutover ghi và rollback phải khác nhau

### 20.1. Shadow read

Service đọc nguồn authoritative rồi **đọc thêm** target để so sánh, nhưng response vẫn lấy từ nguồn thật. Có thể đo:

- Record tồn tại ở cả hai nơi.
- Giá trị được normalize đúng.
- Version và updatedAt.
- Chênh lệch độ trễ.
- Các bất biến/tổng nghiệp vụ.
- Chênh lệch do replication lag đã được giải thích.

Với dữ liệu nhạy cảm, giới hạn quyền và log so sánh. Không log nguyên payload tài chính hoặc PII chỉ để debug.

### 20.2. Read cutover

Chuyển một tỷ lệ nhỏ hoặc một cohort sang target read sau khi đối soát đạt guardrail. Nếu bất kỳ read nào được dùng ra quyết định ghi nghiệp vụ, phải biết rõ nó có thể stale hay không.

### 20.3. Write cutover

Write cutover là mốc khó hơn vì **nguồn sự thật có thể đổi**. Cần:

1. Ngăn writer cũ tiếp tục ghi trong vùng chuyển.
2. Chốt mốc delta/cutoff có thể đối soát.
3. Bảo đảm target đã nhận đủ thay đổi tới cutoff.
4. Chuyển quyền ghi qua adapter/feature flag.
5. Dùng fence, lease hoặc kiểm soát truy cập phù hợp để tránh hai writer cùng authoritative.
6. Theo dõi business invariant và failed/unknown operations.
7. Có kế hoạch xử lý dữ liệu mới sau cutover nếu cần rollback.

### 20.4. Rollback không chỉ là đổi connection string

Nếu target đã tiếp nhận các write mới, quay ứng dụng về source cũ có thể **mất các thay đổi đã ghi trên target**. Runbook cần xác định:

- Có thể đảo hướng replication/reconciliation không?
- Source có đọc được schema/giá trị do target tạo không?
- Trạng thái nào đã vượt điểm không thể rollback?
- Có cần dừng ghi tạm thời, export delta ngược, hoặc forward-fix thay vì rollback?
- Ai có quyền quyết định và công bố thời gian gián đoạn?

**Không hứa “rollback một nút”** nếu không chứng minh được consistency hai chiều. Với nghiệp vụ thanh toán hoặc tồn kho, một kế hoạch forward-fix có kiểm soát đôi khi an toàn hơn khôi phục kết nối cũ.

## 21. Đối soát dữ liệu: đếm hàng không đủ

Bảng đối chiếu nên gồm nhiều cấp.

| Cấp | Kiểm tra | Vì sao cần |
|---|---|---|
| Kết nối/độ phủ | Earliest/latest offset, tiến độ snapshot | Biết có bỏ sót khoảng thay đổi không |
| Bản ghi | Key, version, checksum trường chuẩn hóa | Phát hiện sai khác từng row |
| Tham chiếu | OrderId, customerId, stock reservation reference | Phát hiện orphan hoặc mapping sai |
| Tổng hợp | Tổng quantity, tổng tiền, số Order theo trạng thái | Bắt sai lệch có ý nghĩa nghiệp vụ |
| Bất biến | Không âm tồn kho theo policy, không double charge | Bảo vệ tính đúng đắn |
| Thời gian | Lag, dữ liệu cập nhật muộn, delete/tombstone | Phát hiện stale hoặc mất event |
| Hiệu năng | p95 query, CPU/IO/connection pool | Kiểm soát tác động production |
| Bảo mật | Query chéo, role/grant, tenant isolation | Chứng minh boundary được thực thi |

Ví dụ tính **mismatch rate**:

~~~text
mismatch_rate =
  số bản ghi hoặc business key có sai lệch chưa giải thích
  / số bản ghi hoặc business key được đối chiếu
~~~

Đặt ngưỡng theo mức quan trọng của dữ liệu. Một sai khác 0,01% có thể không chấp nhận được với số dư tài chính, trong khi một số trường read model không trọng yếu có thể tạm chấp nhận lag có giới hạn.

### 21.1. Dữ liệu sửa đổi liên tục gây kết quả so sánh sai

Nếu đọc source lúc 10:00:00 và target lúc 10:00:01, chênh lệch có thể do thay đổi hợp lệ trong khoảng giữa hai lần đọc. Đừng sửa dữ liệu ngay chỉ vì phát hiện mismatch thô. Dùng version, event offset, snapshot cutoff hoặc cùng mốc nghiệp vụ để phân biệt **replication lag** với **mất dữ liệu**.

## 22. Những chỉ số đánh giá tiến độ giảm shared DB

Không dùng duy nhất số database đã tách.

| Chỉ số | Hướng cải thiện mong muốn |
|---|---|
| Số **writer ngoài owner** trên dữ liệu trọng yếu | Giảm tới 0 |
| Số **direct-read consumers** vào schema của service khác | Giảm dần có kế hoạch |
| Số thay đổi schema buộc sửa/triển khai nhiều service | Giảm |
| Tỷ lệ thay đổi cần deploy phối hợp | Giảm |
| Số cross-domain SQL joins trong giao dịch quan trọng | Giảm hoặc được thay bằng hợp đồng thích hợp |
| Consumer lag và reconciliation mismatches | Trong giới hạn đã cam kết |
| Số giao dịch UNKNOWN cần đối soát | Có giám sát và cơ chế phục hồi |
| p95/p99 latency các luồng nghiệp vụ | Không vượt guardrail |
| Error rate, deadlock, connection saturation | Không xấu đi ngoài giới hạn |
| Số role còn quyền write quá phạm vi | Giảm tới phạm vi tối thiểu |
| MTTR và blast radius DB incident | Cải thiện khi tách isolation |
| Chi phí hạ tầng/quan sát và vận hành | Có trade-off chấp nhận được |

Một **sơ đồ ownership** có giá trị hơn số lượng schema vì nó chỉ rõ ai có thể thay đổi dữ liệu và giao diện nào được consumer phụ thuộc.

## 23. Bảo mật, compliance và lifecycle dữ liệu

Tách database không tự giải quyết quyền riêng tư. Cần xem toàn bộ vòng đời:

- Dữ liệu cá nhân đang được sao chép ở consumer nào?
- API/event có phát thông tin nhiều hơn nhu cầu sử dụng không?
- Database mới ở vùng địa lý nào, có đúng data residency không?
- Secret, role và encryption key được quản lý thế nào?
- Backup, archive, CDC log, DLQ và shadow environment có chứa PII không?
- Khi khách yêu cầu xóa/sửa, các bản sao và read model cập nhật thế nào?
- Hệ thống mới có audit trail cho thao tác nhạy cảm không?
- Data retention được áp dụng cả trên bảng cũ sau cutover hay không?

Đặc biệt, **backfill lại từ archive cũ** có thể hồi sinh dữ liệu đã được xóa ở target. Phải đưa tombstone/deletion registry vào pipeline và test phục hồi dữ liệu sau khi xóa.

Không nên dùng read replica hoặc CDC feed chứa toàn bộ customer table cho một service chỉ cần customerId và trạng thái hoạt động. Thu hẹp dữ liệu theo use case là một bước quan trọng trong ownership.

## 24. Những thất bại thường gặp và cách tránh

### 24.1. Tách database instance nhưng vẫn join xuyên service

Có thể xuất hiện federated queries, database links hoặc cùng một service giữ credential của tất cả database. Việc di chuyển vật lý khi ấy chưa tách coupling.

**Cách cải thiện:** xác định contract API/event, giới hạn quyền, tạo read model khi cần; dùng federated query có kiểm soát cho báo cáo đặc thù thay vì làm giao diện giao dịch mặc định.

### 24.2. Big-bang migration cuối tuần

Chuyển toàn bộ bảng và ứng dụng cùng lúc khiến rollback khó, không biết nguồn sai khác và dễ bỏ sót batch jobs.

**Cách cải thiện:** tách theo business capability/vertical slice, có snapshot + delta, shadow compare, guardrails và mốc rollback.

### 24.3. Hai writer được coi là “tạm an toàn” vô hạn

Dual write kéo dài khiến nguồn sự thật mơ hồ và conflict không được xử lý.

**Cách cải thiện:** định nghĩa mốc single writer, fencing, nguồn authoritative, reconciliation và thời hạn kết thúc bridge.

### 24.4. API chỉ là proxy của bảng

Consumer tiếp tục điều khiển UPDATE từng cột qua HTTP, làm domain invariant vẫn bị phân tán.

**Cách cải thiện:** API theo nghiệp vụ, có validation, idempotency, state transition và audit.

### 24.5. Event chứa toàn bộ entity nội bộ

Mỗi migration schema gây breaking change cho consumer, dữ liệu nhạy cảm bị phát không cần thiết.

**Cách cải thiện:** event có ngữ nghĩa nghiệp vụ, versioning, payload tối thiểu, contract tests và chính sách tương thích.

### 24.6. Dùng event nhưng bỏ qua duplicate và ordering

Consumer ghi đè trạng thái mới bằng event cũ hoặc tạo side effect hai lần.

**Cách cải thiện:** eventId, aggregateVersion, idempotent upsert/inbox, partition key và xử lý gap/out-of-order phù hợp.

### 24.7. Tách bảng đang có invariant atomic

Hai domain mới không thể giữ quy tắc cũ nếu chỉ trao đổi event bất đồng bộ.

**Cách cải thiện:** giữ invariant trong một owner hoặc thiết kế workflow/consistency được kiểm chứng; không chia cơ học.

### 24.8. Consumer mới không có backfill

Event chỉ bắt đầu từ ngày triển khai, nên trạng thái lịch sử bị thiếu.

**Cách cải thiện:** snapshot + delta có cutoff, replay đủ retention, archive hoặc đối soát từ source of truth.

### 24.9. Đánh giá thành công bằng “không có exception”

Code chạy nhưng số dư sai hoặc dữ liệu đọc có độ trễ quá lớn.

**Cách cải thiện:** metric nghiệp vụ, reconciliation, invariant tests, chaos/failure tests và quan sát lag.

### 24.10. Thu hồi quyền quá sớm

Job chạy cuối tháng hoặc script data-fix hỏng khi role bị revoke.

**Cách cải thiện:** inventory đủ chu kỳ, quan sát truy cập, owner của ngoại lệ và kế hoạch truyền thông/cutover.

### 24.11. Không dọn compatibility layer

Sau nhiều năm, bảng cũ, view và sync hai chiều vẫn tồn tại; không ai biết nguồn sự thật.

**Cách cải thiện:** mỗi bridge có owner, ngày kết thúc, metric usage và điều kiện xóa; coi cleanup là một phần deliverable.

## 25. Runbook mẫu cho migration một bounded context

~~~markdown
# Runbook: Migrate <domain> off shared database

## A. Bối cảnh
- Business owner, kỹ thuật owner, on-call:
- Source schema/database:
- Target schema/database:
- Những bảng và invariant:
- Danh sách reader/writer, job và report:
- Mục tiêu, SLO, RPO/RTO:
- Lý do cần tách vật lý:

## B. Điều kiện trước migration
- Đã nhận diện mọi đường ghi và nguồn authoritative:
- Có API/command hoặc adapter thay direct write:
- Có snapshot nhất quán + delta/change capture:
- Có hợp đồng schema, data validation và authorization:
- Có dashboard/alert và đường đối soát:
- Có hướng rollback hoặc forward-fix:

## C. Expand
- Tạo schema và tài khoản target:
- Triển khai code tương thích cả đường cũ/mới:
- Chuẩn bị outbox/CDC và retention:
- Chuẩn bị shadow read, không shadow write ngoài ý muốn:

## D. Backfill
- Snapshot cutoff / transaction ID / offset:
- Chunk key/batch size/throttle:
- Retry/idempotency/checkpoint:
- Xử lý row bị xóa hoặc sửa trong lúc copy:
- Tiến độ và thời điểm bắt kịp:

## E. Verification
- Record counts/checksums theo cùng cutoff:
- Business aggregate totals:
- Invariant, orphan reference, tombstone:
- Dữ liệu nhạy cảm và đúng tenant:
- p95/p99/DB load/replication lag:
- Chênh lệch chấp nhận được và cách giải thích:

## F. Cutover
- Ai phê duyệt:
- Thời điểm và phiên bản policy:
- Cách fence writer cũ:
- Thứ tự chuyển read/write:
- Cách theo dõi UNKNOWN business operations:
- Sự kiện buộc tạm dừng hoặc rollback:

## G. Rollback / forward-fix
- Dữ liệu phát sinh mới sau cutover:
- Có thể chuyển ngược an toàn không:
- Delta/reconciliation ngược nếu cần:
- Đường phục hồi và trách nhiệm:
- Trạng thái nào không thể đảo ngược:

## H. Contract
- Thu hồi direct write/read permissions:
- Ngừng sync migration:
- Xóa view/bảng cũ sau retention:
- Cập nhật ownership catalog, docs, audit:
- Ngày kiểm chứng sau cutover:
~~~

Runbook cần đi cùng danh sách kiểm tra có người chịu trách nhiệm thật. Không chỉ ghi “rollback bằng feature flag” nếu còn dữ liệu đã ghi theo mô hình mới.

## 26. Bài tập thực hành: tách Order khỏi một database chung

**Tình huống:** một công ty đang dùng PostgreSQL shared_db với các bảng:

- customers: CustomerApp ghi; Checkout và Billing đọc trực tiếp.
- orders: Checkout ghi; Billing, Fulfillment và BI đọc trực tiếp.
- order_items: Checkout ghi; BI join với orders.
- stock_balances: Checkout và Inventory cùng ghi.
- payments: Payment Service và reconciliation batch cùng ghi.
- Một stored procedure legacy dùng transaction cập nhật orders, stock_balances và payments.

Công ty muốn tiến tới microservices mà vẫn phục vụ khách bình thường. Nhóm đề nghị “cuối tuần này tách mỗi bảng ra một database, rồi sửa connection string”.

Hãy thực hiện:

1. Xác định **hai nguy cơ cao nhất** của đề xuất tách theo bảng.
2. Chọn bounded context/owner cho từng nhóm dữ liệu, giải thích vì sao order và order_items có thể nằm cùng owner.
3. Với stock_balances, thiết kế lộ trình **single writer** trước khi chuyển database vật lý.
4. Tìm những phần đang phụ thuộc vào transaction xuyên domain và đề xuất workflow phù hợp; nêu điểm cần idempotency.
5. Với BI, chọn cách thay truy vấn join trực tiếp từ shared DB, nêu độ mới dữ liệu chấp nhận.
6. Viết kế hoạch backfill + delta cho orders, chỉ rõ cách không bỏ sót UPDATE/DELETE khi copy.
7. Đặt ba chỉ số reconciliation và ba guardrail để xác nhận cutover.
8. Nêu điều kiện nào cho phép thu hồi quyền SELECT/UPDATE của Billing, Checkout và ERP job.
9. Nếu target đã nhận 1.000 Order mới sau cutover, vì sao đổi lại connection string về source cũ không phải rollback an toàn?
10. Thiết kế cách phát hiện không còn consumer “ẩn” của một compatibility view trước khi xóa.

### Gợi ý một phương án

- **Ưu tiên Inventory single writer** để chấm dứt nhiều ứng dụng trừ tồn cùng lúc.
- **Checkout sở hữu Orders và OrderLines**, công bố API/events cho Fulfillment và Billing.
- **Payment chịu trách nhiệm state của giao dịch**, reconciliation job qua interface/batch API có audit.
- **BI dùng pipeline/read model được quản lý**, tránh join trực tiếp trên schema giao dịch.
- **Stored procedure xuyên miền** cần được thay bằng workflow với các bất biến và trạng thái trung gian rõ.
- **Backfill dùng snapshot + delta**, đối soát cùng cutoff rồi mới chuyển traffic.
- **Contract** chỉ được thực hiện khi đã chứng minh không còn quyền truy cập hợp lệ phụ thuộc schema cũ.

Đây là bài tập thiết kế: câu trả lời hợp lý có thể khác nhau theo RPO/RTO, nghiệp vụ, khả năng sửa legacy và hệ thống dữ liệu hiện có.

## 27. Checklist trước mỗi đợt tách dữ liệu

- [ ] Đã xác định bounded context, owner và invariant quan trọng.
- [ ] Biết mọi đường đọc/ghi, kể cả batch, stored procedure, report và script.
- [ ] Có baseline SLO, transaction, coupling và quy trình khôi phục.
- [ ] Không tạo thêm direct SQL dependency mới không kiểm soát.
- [ ] Có **single writer** hoặc quy tắc authoritative write rõ.
- [ ] Các đường ghi đã chuyển sang API/command có quyền, validation và idempotency.
- [ ] Các consumer đọc có API/read model/event và hợp đồng độ mới phù hợp.
- [ ] Có chiến lược snapshot + delta, xử lý UPDATE, DELETE và late changes.
- [ ] Backfill/upsert idempotent, có version guard và checkpoint.
- [ ] Biết hệ quả của transaction xuyên domain và mô hình saga/consistency.
- [ ] Đã thử crash, redelivery, retry, timeout sau commit và concurrent writes.
- [ ] Có schema/role riêng và kế hoạch thu hồi quyền DML/SELECT chéo.
- [ ] Có test compatibility cho event/API và migration schema.
- [ ] Có reconciliation theo record, aggregate, invariant và cùng cutoff.
- [ ] Shadow read không tạo side effect và không lộ dữ liệu nhạy cảm.
- [ ] Có cutover, guardrail, đường dừng và rollback/forward-fix dựa trên dữ liệu thật.
- [ ] Reporting, search, cache và downstream jobs được kiểm tra.
- [ ] Có tài liệu trách nhiệm backup, restore, RPO/RTO và on-call.
- [ ] Sau cutover có kế hoạch xóa compatibility layer, bảng cũ và quyền dư thừa.
- [ ] Không lấy “số database mới” làm thước đo duy nhất của thành công.

## 28. Tổng kết

**Giảm dần cơ sở dữ liệu dùng chung là hành trình tách quyền sở hữu và phụ thuộc dữ liệu, không phải một thao tác chuyển bảng sang server khác.** Lộ trình an toàn thường bắt đầu bằng việc nhìn rõ mọi reader/writer, xác định bounded context và invariant, ngăn phụ thuộc mới, đưa mọi đường ghi về **single writer**, thay direct read bằng API/event/read model, rồi mới tính đến tách schema hoặc storage vật lý.

Trong migration, những rủi ro quan trọng nhất là **mất cập nhật giữa snapshot và delta, hai writer cùng authoritative, dual write phân kỳ, giao dịch xuyên domain, duplicate event và rollback làm mất dữ liệu mới**. Mỗi bước cần có hợp đồng, quan sát, đối soát, guardrails và người chịu trách nhiệm. Một bước chuyển đổi được xem là có giá trị khi nó giúp service thay đổi độc lập hơn **mà vẫn giữ đúng dữ liệu, bảo mật và trải nghiệm nghiệp vụ**.
