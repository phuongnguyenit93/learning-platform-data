# Chuyển khóa chính, tách thực thể và hợp nhất thực thể

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **định danh nghiệp vụ**, **khóa chính vật lý**, **khóa thay thế**, **khóa công khai** và **khóa tham chiếu** khi một mô hình dữ liệu tiến hóa.
- Lập kế hoạch đổi khóa theo các giai đoạn **mở rộng – điền dữ liệu – đồng bộ chuyển tiếp – kiểm chứng – chuyển luồng đọc/ghi – thu hẹp**, không làm mất quan hệ hoặc đổi ý nghĩa ID.
- Tách một thực thể thành nhiều thực thể mới theo **grain, cardinality, ownership, vòng đời và bất biến**, thay vì chỉ chuyển cột sang bảng khác.
- Hợp nhất những thực thể có cùng ngữ nghĩa bằng **quy tắc nhận diện, mã canonical, bảng alias và chính sách giải quyết xung đột**, mà vẫn bảo toàn sự kiện và chứng từ lịch sử.
- Dùng các truy vấn PostgreSQL để thêm khóa, nạp lại khóa ngoại, kiểm tra bản ghi thiếu/sai liên kết và đối soát số đo nghiệp vụ.
- Thiết kế tương thích API, event, cache, read model và hệ phân tích trong quá trình thay đổi, kể cả khi có nhiều phiên bản ứng dụng chạy đồng thời.
- Đánh giá khả năng rollback, dữ liệu đến muộn, khóa bị tái sử dụng, quyền đa tenant, tác động tới bảo mật và chi phí vận hành trước khi xóa cấu trúc cũ.

Bài thuộc chương **Tiến hóa mô hình** trong **DATABASE_DATA_MODELING**. Mục tiêu của module là chuyển yêu cầu nghiệp vụ thành các mô hình có thực thể, quan hệ, ràng buộc, khóa, chỉ mục và lược đồ vật lý rõ ràng, so sánh relational, document, graph và analytics để lựa chọn cấu trúc dễ tiến hóa, dễ kiểm chứng. Bài này xem việc đổi khóa, tách hoặc hợp nhất thực thể là **thay đổi ngữ nghĩa và hợp đồng dữ liệu có kiểm soát**, không phải chỉ là một lệnh ALTER TABLE.

> Nguyên tắc xuyên suốt: trước khi đổi cấu trúc, phải chứng minh **một hàng, một ID và một quan hệ đang có ý nghĩa gì**; sau thay đổi, phải chứng minh ý nghĩa ấy được giữ nguyên hoặc được thay đổi theo một quyết định nghiệp vụ được chấp thuận.

## 1. Ba kiểu thay đổi trông giống nhau nhưng tác động khác nhau

Giả sử hệ thống bán hàng ban đầu có bảng khách hàng và đơn hàng. Sau một thời gian xuất hiện ba yêu cầu:

1. Khóa khách **customer_id TEXT** được tạo bởi hệ thống cũ, có nguy cơ thay đổi hoặc trùng khi nhập dữ liệu; nhóm muốn dùng **customer_sk BIGINT** cho quan hệ trong database.
2. Bảng **orders** đang chứa cả thông tin thương mại và thông tin người nhận; nhóm muốn tách phần dữ liệu giao hàng để giảm phạm vi truy cập và có vòng đời độc lập.
3. Sau nhập dữ liệu từ hai hệ thống, khách **C-101** và **C-202** được xác minh là cùng một tài khoản nghiệp vụ; nhóm muốn hợp nhất để không tính khách hai lần.

Dù cả ba có thể yêu cầu sửa nhiều bảng, chúng có bản chất khác nhau:

| Thay đổi | Câu hỏi chính | Đối tượng cần bảo toàn |
| --- | --- | --- |
| **Chuyển khóa chính** | Một thực thể cũ được định danh bằng khóa mới như thế nào? | Tính duy nhất, mọi FK, ID public, lịch sử |
| **Tách thực thể** | Những thuộc tính nào thực sự thuộc cùng một grain và vòng đời? | Cardinality, bất biến, transaction, quyền |
| **Hợp nhất thực thể** | Hai bản ghi có đại diện cùng một thực thể nghiệp vụ không? | Quy tắc nhận diện, quan hệ, chứng từ, quyền, lịch sử |

**Đổi khóa không nhất thiết đổi thực thể.** **Tách thực thể không nhất thiết đổi ID công khai.** **Hợp nhất bản ghi không nhất thiết phải viết lại mọi khóa trong lịch sử.**

Nói rõ loại thay đổi giúp nhóm không biến việc tối ưu index thành dự án thay đổi danh tính khách hàng, hoặc dùng một script UPDATE FK để giải quyết bài toán xác minh hai khách có thật sự là một.

## 2. Chuẩn bị: mô tả định danh, grain và phạm vi trước khi migration

### 2.1. Một thực thể có thể mang nhiều loại khóa

| Loại khóa | Ví dụ | Ai sở hữu? | Có nên công bố? |
| --- | --- | --- | --- |
| **Natural/business key** | Mã khách trong hệ legacy | Miền nghiệp vụ hoặc nguồn tích hợp | Chỉ nếu hợp đồng cho phép |
| **Surrogate key** | customer_sk = 912348 | Database hoặc dịch vụ sở hữu | Thường không cần |
| **Public identifier** | customerRef dạng UUID | Hợp đồng API/integration | Có thể, nhưng vẫn phải kiểm tra quyền |
| **Composite scope key** | (tenant_id, customer_id) | Hợp đồng phân vùng tenant | Có thể dùng nội bộ để bảo vệ đúng tenant |
| **Foreign key** | orders.customer_sk | Bảng con tham chiếu phiên bản ID phù hợp | Thường là chi tiết triển khai |
| **Idempotency key** | client_request_id của yêu cầu tạo đơn | Tác vụ nghiệp vụ | Không phải định danh thực thể |
| **Historical reference** | customer_id_at_purchase trong chứng từ | Nguồn lịch sử giao dịch | Chỉ sửa theo quy trình chứng từ |

Một **UUID không tự cấp quyền** và một **BIGINT không tự xấu**. Tiêu chí quan trọng là tính ổn định, phạm vi duy nhất, quy tắc cấp lại, quyền sở hữu và khả năng thay đổi mà không phá hợp đồng bên ngoài.

### 2.2. Đặt câu hỏi theo grain

Trước khi thay đổi bảng **customers**, cần định nghĩa:

> Một hàng của customers đại diện **một tài khoản khách trong một tenant**, không nhất thiết tương đương một người tự nhiên duy nhất.

Trước khi đổi **orders**, cần định nghĩa:

> Một hàng của orders đại diện **một đơn đã được cấp order_id** trong tenant; nhiều đơn có thể cùng khách, và mỗi đơn có thể có nhiều dòng hàng.

Với một bản chụp giao hàng:

> Một hàng của order_delivery_snapshots đại diện **địa chỉ/người nhận được chốt cho một lần giao hoặc một đơn**, tùy nghiệp vụ đã chọn.

Nếu gọi hai tài khoản là “cùng khách” nhưng một tài khoản thuộc doanh nghiệp và một thuộc cá nhân, hoặc thuộc hai tenant không có quyền hợp nhất, thuật toán merge có thể phá phân quyền. **Grain và phạm vi định danh phải được xác minh trước khi chọn khóa.**

### 2.3. Bản đồ phụ thuộc tối thiểu

~~~text
customers (customer_id)
      |
      +---- orders.customer_id
      |         |
      |         +---- order_lines
      |         +---- payments / refunds
      |         +---- shipments
      |
      +---- loyalty_accounts
      +---- support_tickets
      +---- API / events / caches / search
      +---- dimension_customer / analytics facts
~~~

Đừng chỉ tra các FK được khai báo trong PostgreSQL. Còn có tham chiếu **ngoài database**: khóa trong message, URL, CSV xuất cho đối tác, cache key, dữ liệu phân tích, CDC, dashboard và công cụ vận hành. Nếu một hệ lưu ID dưới dạng string trong JSON, database không thấy đó là FK.

## 3. Khung migration an toàn: expand – migrate – contract

Một thay đổi khóa hoặc cấu trúc có thể chia thành các pha:

| Pha | Mục tiêu | Điều kiện để qua pha |
| --- | --- | --- |
| **0. Khảo sát và chốt hợp đồng** | Hiểu định danh, dependency, invariants, workload | Có chủ sở hữu, sơ đồ nguồn và phương án phục hồi |
| **1. Expand** | Thêm cột/bảng/khóa/chỉ mục mới mà chưa bỏ cái cũ | Ứng dụng cũ vẫn chạy được |
| **2. Backfill** | Điền dữ liệu đã có vào cấu trúc mới | Có checkpoint, đối soát, không ghi lùi |
| **3. Chuyển tiếp** | Mọi ghi mới bảo toàn cả cách đọc cũ và mới | Không có write gap; kiểm soát retry và lỗi |
| **4. Validate** | Kiểm tra dữ liệu và toàn bộ tham chiếu | Không còn null sai, orphan, mismatch, quyền sai |
| **5. Cutover** | Chuyển từng reader/writer sang hợp đồng mới | Có telemetry, rollback hoặc phương án sửa sự cố |
| **6. Contract** | Gỡ cấu trúc cũ khi không còn phụ thuộc | Không còn consumer hoặc retention cần tới nó |

Trong hệ thống phục vụ liên tục, **không đồng nghĩa phải dừng mọi ghi**. Nhưng “zero downtime” chỉ khả thi khi ứng dụng, database và pipeline tương thích trong khoảng chuyển tiếp, có khả năng khóa/đồng bộ và tài nguyên đáp ứng. Một migration lớn vẫn có thể cần khoảng bảo trì được công bố.

Đặc biệt, **rollback phần code** có thể dễ nhưng **rollback dữ liệu** sau khi đã xóa khóa cũ hoặc gộp hai người không rõ căn cứ có thể không khả thi. Do đó kế hoạch phục hồi phải được thiết kế trước khi thực hiện bước không đảo ngược.

## 4. Ví dụ 1 — Chuyển khóa khách từ TEXT sang surrogate BIGINT

Giả sử hệ thống PostgreSQL hiện có:

~~~sql
CREATE TABLE customers (
    tenant_id BIGINT NOT NULL,
    customer_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT customers_pkey
        PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE orders (
    tenant_id BIGINT NOT NULL,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    confirmed_amount NUMERIC(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    CONSTRAINT orders_pkey
        PRIMARY KEY (tenant_id, order_id),
    CONSTRAINT fk_orders_customer_old
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, customer_id)
);

CREATE INDEX ix_orders_customer_old
    ON orders (tenant_id, customer_id, confirmed_at DESC);
~~~

**Mục tiêu kỹ thuật:** thêm **customer_sk BIGINT** và cuối cùng cho **orders** tham chiếu **(tenant_id, customer_sk)**, nhưng **customer_id** vẫn tồn tại như mã nghiệp vụ trong giai đoạn cần tương thích.

**Không đổi nghĩa của order_id**, không tự cấp mã customer_id mới, không đổi giá đã xác nhận và không chuyển đơn từ tenant này sang tenant khác.

### 4.1. Pha expand ở bảng cha

~~~sql
CREATE SEQUENCE customer_sk_seq AS BIGINT;

ALTER TABLE customers
ADD COLUMN customer_sk BIGINT;

ALTER TABLE customers
ALTER COLUMN customer_sk
SET DEFAULT nextval('customer_sk_seq'::regclass);

ALTER SEQUENCE customer_sk_seq
OWNED BY customers.customer_sk;
~~~

Điều này **chưa đổi primary key**. Các bản ghi mới dùng default sẽ có customer_sk; các bản ghi cũ hiện NULL và cần được điền. Sequence là cơ chế cấp mã kỹ thuật; nếu ứng dụng được phép chèn giá trị thủ công, phải có quy tắc kiểm soát trùng. Trong hệ nhiều tenant, mã surrogate ở đây được sinh bằng một sequence chung, nhưng **FK ghép với tenant_id** để bảo vệ ranh giới tenant.

Ở bảng lớn, tránh một UPDATE khổng lồ giữ transaction lâu, tạo lượng WAL lớn và gây tải. Có thể nạp theo lô có checkpoint:

~~~sql
-- Chạy nhiều đợt trong job có giới hạn kích thước và retry.
WITH batch AS (
    SELECT ctid
    FROM customers
    WHERE customer_sk IS NULL
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE customers AS c
SET customer_sk = nextval('customer_sk_seq'::regclass)
FROM batch AS b
WHERE c.ctid = b.ctid
RETURNING c.tenant_id, c.customer_id, c.customer_sk;
~~~

**ctid** chỉ được dùng ở **đây** để chọn batch hàng hiện tại trong PostgreSQL; nó không phải khóa nghiệp vụ, không lưu qua các lượt chạy như một ID bền vững và có thể thay đổi khi row được cập nhật. Job thực tế cần checkpoint theo khóa ổn định, theo dõi số hàng còn NULL và khởi động lại an toàn. **SKIP LOCKED** giúp các worker không đợi cùng hàng, nhưng không tự bảo đảm quá trình cuối cùng đã xử lý toàn bộ hàng.

Sau khi điền và đảm bảo người ghi mới luôn tạo customer_sk, thêm một unique index:

~~~sql
-- Chạy ngoài transaction block rõ ràng.
CREATE UNIQUE INDEX CONCURRENTLY ux_customers_tenant_sk
    ON customers (tenant_id, customer_sk);
~~~

**CREATE INDEX CONCURRENTLY không chạy bên trong một transaction block** và có thể kéo dài; cần kiểm soát lock, lỗi tạo index không hợp lệ, dung lượng và tác động tải. Unique index trên cột nullable cho phép nhiều NULL theo cách xử lý NULL của PostgreSQL thông thường, nên **chưa chứng minh dữ liệu đã đầy đủ**.

### 4.2. Pha expand ở bảng con

~~~sql
ALTER TABLE orders
ADD COLUMN customer_sk BIGINT;

-- Chỉ mục mới phục vụ JOIN/tra cứu sau cutover.
CREATE INDEX CONCURRENTLY ix_orders_tenant_customer_sk
    ON orders (tenant_id, customer_sk, confirmed_at DESC);
~~~

Sau đó cập nhật ứng dụng ghi mới: khi tạo đơn, tìm **customer_sk** từ nguồn customers theo đúng **(tenant_id, customer_id)**, rồi ghi **cả customer_id và customer_sk** từ **cùng một mapping đã xác minh**.

Không cho hai đường nhập tạo ra hai giá trị khác nhau của cùng khách. Việc viết hai cột trong một transaction chưa đủ nếu dữ liệu nguồn để tính chúng khác nhau hoặc một nhánh được cập nhật bằng event cũ. Có thể dùng trigger/logic database để dẫn xuất khóa mới từ khóa cũ trong giai đoạn chuyển tiếp, nhưng khi đó phải xử lý quyền ghi, lỗi không tìm thấy khách và hiệu năng truy vấn trong trigger; không tự coi hai cột là hai nguồn chuẩn độc lập.

### 4.3. Backfill khóa ngoại mới ở orders

~~~sql
-- Mỗi lần nạp có thể giới hạn theo tenant/order_id trong job thật.
UPDATE orders AS o
SET customer_sk = c.customer_sk
FROM customers AS c
WHERE o.tenant_id = c.tenant_id
  AND o.customer_id = c.customer_id
  AND o.customer_sk IS NULL
  AND c.customer_sk IS NOT NULL;
~~~

Đây là **mẫu phép biến đổi**, không phải lời khuyên chạy một UPDATE không giới hạn trên bảng hàng tỷ dòng. Có thể dùng batch theo **(tenant_id, order_id)** và checkpoint riêng; nguồn vẫn có thể nhận ghi song song. Sau backfill, tiếp tục nạp các bản ghi phát sinh muộn và kiểm tra lại trước cutover.

**Chỉ cập nhật khi customer_sk IS NULL**: nếu một hàng đã có customer_sk nhưng sai so với customer_id, đừng âm thầm sửa mà không điều tra. Mismatch có thể báo sai quyền tenant, lỗi app ghi kép, sự kiện cũ hoặc thay đổi định danh nghiệp vụ không được công bố.

### 4.4. Bổ sung FK và ràng buộc đầy đủ sau khi đường ghi sẵn sàng

Vì **ux_customers_tenant_sk** đã là unique index không partial, có thể dùng nó làm đích FK:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer_new
FOREIGN KEY (tenant_id, customer_sk)
REFERENCES customers (tenant_id, customer_sk)
NOT VALID;
~~~

**NOT VALID** cho phép hoãn quét xác minh toàn bộ dữ liệu cũ đối với foreign key trong PostgreSQL, nhưng **những ghi mới phù hợp phải tuân ràng buộc** ngay từ khi thêm. Với khóa mới còn NULL, FK không tự bác bỏ hàng có customer_sk NULL. Cần một bước ràng buộc NOT NULL riêng **sau khi** ứng dụng ghi mới đã chuyển và backfill hoàn thành.

~~~sql
ALTER TABLE orders
VALIDATE CONSTRAINT fk_orders_customer_new;

-- Chỉ thêm khi không còn writer mới nào bỏ customer_sk.
ALTER TABLE orders
ADD CONSTRAINT ck_orders_customer_sk_present
CHECK (customer_sk IS NOT NULL)
NOT VALID;

ALTER TABLE orders
VALIDATE CONSTRAINT ck_orders_customer_sk_present;

ALTER TABLE orders
ALTER COLUMN customer_sk SET NOT NULL;
~~~

Quá trình **VALIDATE CONSTRAINT** vẫn tốn I/O/lock ở một mức độ nhất định; **SET NOT NULL** có hành vi quét/lock khác nhau theo phiên bản và cách PostgreSQL chứng minh ràng buộc đã được xác minh. Cần thử trên staging có phân bố gần sản xuất, chọn thời điểm và quan sát lock thực tế.

Tương tự, để thật sự dùng customer_sk như một phần khóa chính của customers, phải xác nhận **customers.customer_sk IS NOT NULL**, bằng kiểm tra hoặc ràng buộc được xác minh. Không biến index unique trên cột nullable thành bằng chứng sai rằng tất cả hàng đã có ID mới.

### 4.5. Đối soát hai cách định danh

Một truy vấn phát hiện order thiếu ánh xạ, trỏ sai khách hoặc sai tenant:

~~~sql
SELECT
    o.tenant_id,
    o.order_id,
    o.customer_id AS old_customer_id,
    o.customer_sk AS new_customer_sk,
    c_old.customer_sk AS expected_customer_sk,
    c_new.customer_id AS referenced_customer_id,
    CASE
        WHEN c_old.customer_id IS NULL
            THEN 'OLD_REFERENCE_MISSING'
        WHEN o.customer_sk IS NULL
            THEN 'NEW_REFERENCE_MISSING'
        WHEN c_new.customer_sk IS NULL
            THEN 'NEW_REFERENCE_INVALID'
        WHEN o.customer_sk IS DISTINCT FROM c_old.customer_sk
            THEN 'IDENTITY_MISMATCH'
        ELSE 'MATCH'
    END AS mapping_state
FROM orders AS o
LEFT JOIN customers AS c_old
    ON c_old.tenant_id = o.tenant_id
   AND c_old.customer_id = o.customer_id
LEFT JOIN customers AS c_new
    ON c_new.tenant_id = o.tenant_id
   AND c_new.customer_sk = o.customer_sk;
~~~

Phải đánh giá trên **cùng snapshot nhất quán** khi có cập nhật đồng thời; mismatch tạm thời do một pipeline chưa bắt kịp cần được phân biệt với dữ liệu sai vĩnh viễn. Trong mô hình demo có FK cũ, hàng thiếu customer cũ đáng ra bị chặn, nhưng truy vấn vẫn có giá trị khi kiểm tra staging, migration sang kho khác hoặc kiểm tra hệ không thực thi FK.

Đối soát cần kiểm tra nhiều hơn “không có NULL”:

- **COUNT số khách, số đơn** trước/sau, phân theo tenant và trạng thái.
- **COUNT DISTINCT (tenant_id, customer_id)** ở nguồn và số mapping duy nhất.
- **Không có hai customer_sk** cho cùng một khách trong một trạng thái được công bố.
- **Không có đơn bị chuyển tenant**, không mất hoặc nhân đơn khi đổi JOIN.
- **Tổng confirmed_amount theo currency** không đổi do migration khóa.
- **API của khách A không trả đơn của khách B** sau khi áp dụng cách tra cứu mới.
- Những consumer dựa vào ID cũ vẫn hoạt động hoặc đã chuyển theo hợp đồng.

### 4.6. Chuyển PRIMARY KEY thực sự: không phải lúc nào cũng cần

Khi customers có **customer_sk UNIQUE NOT NULL** và orders đã tham chiếu FK mới, hệ thống có thể **đạt yêu cầu kỹ thuật mà không cần đổi ngay constraint PRIMARY KEY**. Khóa chính cũ vẫn dùng cho một số đường nghiệp vụ, còn surrogate key dùng cho các quan hệ đọc/ghi mới.

Nếu chủ đích thật sự là chuyển **PRIMARY KEY (tenant_id, customer_id)** thành **PRIMARY KEY (tenant_id, customer_sk)**, phải kiểm tra:

1. Tất cả FK đang tham chiếu **ràng buộc PK cũ**, kể cả những bảng ngoài sơ đồ.
2. Mọi truy vấn, ORM mapping, trigger, job import, replication, CDC và consumer có phụ thuộc vào PK cũ không.
3. **UNIQUE (tenant_id, customer_id)** vẫn được duy trì nếu business key phải tiếp tục duy nhất.
4. Toàn bộ hàng customers đã có customer_sk, các bảng con đã chuyển FK.
5. Có kế hoạch lock, thời gian DDL và rollback nếu swap constraint thất bại.

Lệnh kiểu **DROP CONSTRAINT customers_pkey** có thể **bị chặn do FK còn phụ thuộc**; không dùng **CASCADE** bừa để buộc xóa các ràng buộc bảo vệ dữ liệu. Việc hoán đổi constraint và index nên được thực hiện bằng kế hoạch migration được thử trên bản sao dữ liệu đại diện.

**Bài học:** đổi khóa chính trong catalog hệ quản trị chỉ là bước cuối. **Điều có giá trị là tính nhất quán của danh tính và các quan hệ qua mọi đường truy cập.**

## 5. Kiểm soát các trường hợp đổi khóa khó hơn ví dụ

### 5.1. Khóa tự nhiên bị sửa hoặc được tái sử dụng

Nếu nguồn đổi **customer_id = C-101** thành **C-202**, phải phân biệt:

- **Đổi mã của cùng một khách**: duy trì thực thể và surrogate ID, thêm alias cho mã cũ trong thời hạn cần thiết.
- **Hai khách khác nhau bị trùng mã**: cần xử lý xung đột, không gộp dữ liệu.
- **Mã cũ được cấp lại cho người khác**: phải có namespace, khoảng hiệu lực hoặc ID nguồn có lịch sử; nếu không, việc JOIN đơn quá khứ bằng mã có thể trỏ nhầm người.

Một bảng alias có thể cần **source_system**, **tenant_id**, **external_id**, **effective_from** và **effective_to** khi nguồn tái sử dụng ID. Không chỉ đặt UNIQUE(external_id) nếu thực tế ID chỉ duy nhất trong từng hệ hoặc thời kỳ.

### 5.2. ID public không nên thay chỉ vì khóa vật lý đổi

Nếu API đã hứa **publicCustomerId** ổn định, đừng trả customer_sk vừa tạo thay cho nó. Client có thể lưu ID trong liên kết, bookmark, email, export hoặc hệ ngoài.

Có thể giữ:

~~~text
customer_sk             -- khóa kỹ thuật mới
customer_id             -- mã legacy vẫn truy vết được
public_customer_id      -- ID API/integration ổn định
~~~

Mỗi loại khóa có hợp đồng và vòng đời riêng. Nếu thực sự phải thay public ID, cần **bảng ánh xạ/redirect, chính sách tương thích, theo dõi consumer và mốc ngừng alias**.

### 5.3. Multi-tenant và phạm vi quan hệ

FK chỉ trên **customer_sk** có thể đủ để định danh kỹ thuật nếu surrogate unique toàn cục, nhưng vẫn phải bảo vệ **authorization theo tenant**. FK ghép **(tenant_id, customer_sk)** như ví dụ còn giúp chặn hàng đơn chứa tenant A nhưng tham chiếu customer của tenant B khi mapping đúng.

Dù FK chính xác, **người dùng biết ID cũng không có quyền đọc** dữ liệu khách khác. Quyền truy cập phải kiểm tra tenant/principal tại API hoặc cơ chế dữ liệu đáng tin; không dùng tính khó đoán của khóa như biện pháp an ninh duy nhất.

## 6. Ví dụ 2 — Tách thực thể: từ đơn hàng thành đơn + thông tin giao

Vấn đề khác hoàn toàn với chuyển khóa: bảng **orders** đang chứa cả **sự thật thương mại** lẫn **người nhận/địa chỉ đã chốt**:

~~~text
orders
  tenant_id, order_id, customer_id
  confirmed_at, confirmed_amount, currency, status
  recipient_name, recipient_phone, address_line1, city
~~~

Báo cáo doanh số chỉ cần trường thương mại. Dịch vụ giao vận cần thông tin người nhận **của những đơn được giao**. Khi đọc mọi đơn, việc giữ tất cả thông tin ở một bảng làm mở rộng phạm vi tiếp cận PII.

### 6.1. Phải xác định đúng grain của thực thể mới

Có ít nhất ba lựa chọn khác nhau:

| Mô hình | Grain | Khi phù hợp |
| --- | --- | --- |
| **order_delivery_snapshots** | Một bản chụp địa chỉ cho **một đơn** | Mỗi đơn có đúng một địa chỉ chốt và không tách kiện |
| **order_shipments** | Một kiện/đợt giao của **một đơn** | Một đơn có nhiều kiện, trạng thái giao độc lập |
| **shipment_delivery_revisions** | Một lần hiệu chỉnh thông tin giao cho **một shipment** | Cho phép đổi địa chỉ sau xác nhận và phải giữ audit |

Nếu đơn có thể chia làm hai kiện gửi hai địa chỉ, chọn PK **(tenant_id, order_id)** cho mọi thông tin giao là **quá thô**. Nếu nghiệp vụ luôn một địa chỉ/đơn, tạo bảng revisions nhiều cấp có thể làm thiết kế phức tạp không cần thiết.

Trong ví dụ tiếp theo, giả định **một đơn vật lý có một snapshot giao lúc xác nhận**; đổi địa chỉ sau đó là một nghiệp vụ riêng có audit.

### 6.2. Expand: thêm bảng độc lập nhưng bảo toàn quan hệ

Giả sử bảng orders hiện có khóa **(tenant_id, order_id)**. Có thể tạo:

~~~sql
CREATE TABLE order_delivery_snapshots (
    tenant_id BIGINT NOT NULL,
    order_id TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    recipient_phone TEXT,
    address_line1 TEXT NOT NULL,
    city TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders(tenant_id, order_id)
);
~~~

Bảng này **không phải contact hiện hành của khách hàng**. Nếu khách đổi địa chỉ mặc định, địa chỉ đã dùng để chấp nhận đơn cũ không được tự đồng bộ theo hồ sơ mới.

Đặt snapshot ở bảng riêng cũng **chưa bảo vệ PII** nếu mọi role vẫn SELECT được bảng đó. Cần quyền riêng, API chuyên biệt, chính sách retention và xử lý log/backup.

### 6.3. Backfill dữ liệu lịch sử có chứng cứ

Ví dụ legacy orders có các cột **recipient_name**, **recipient_phone**, **address_line1**, **city** tại thời điểm xác nhận. Sau khi xác minh đây thật sự là snapshot đã chốt, nạp:

~~~sql
INSERT INTO order_delivery_snapshots (
    tenant_id,
    order_id,
    recipient_name,
    recipient_phone,
    address_line1,
    city,
    captured_at
)
SELECT
    tenant_id,
    order_id,
    recipient_name,
    recipient_phone,
    address_line1,
    city,
    confirmed_at
FROM orders
WHERE recipient_name IS NOT NULL
  AND address_line1 IS NOT NULL
  AND city IS NOT NULL
ON CONFLICT (tenant_id, order_id) DO NOTHING;
~~~

**ON CONFLICT DO NOTHING** chống tạo trùng khóa khi chạy lại nhưng **không chứng minh nội dung trùng là giống nhau**. Nếu snapshot cũ và nguồn khác nhau, phải phân loại: đã có chỉnh sửa hợp lệ, lỗi nạp, dữ liệu cũ được sửa, hay cập nhật đến muộn.

Nếu legacy chỉ có **địa chỉ hiện hành được đồng bộ từ hồ sơ khách**, nó **không phải chứng cứ địa chỉ khi xác nhận**. Không được đổi tên cột rồi khẳng định lịch sử đã được bảo toàn. Cần nguồn lịch sử, log chấp nhận, chứng từ giao vận hoặc đánh dấu **không xác minh được**.

### 6.4. Chuyển luồng ghi mà không tạo hai chủ sở hữu

Trong giai đoạn chuyển tiếp, hai cấu trúc có thể cùng tồn tại. Cần quy định:

- **Lệnh xác nhận đơn** là nơi có thẩm quyền quyết định địa chỉ được chốt.
- Trong cùng PostgreSQL, có thể INSERT order và snapshot **trong một transaction** nếu cả hai phải cùng tồn tại trước khi xác nhận thành công.
- Nếu snapshot nằm ở dịch vụ/database riêng, phải có **workflow trạng thái trung gian, idempotency, event đáng tin và cách xử lý lỗi**; không tuyên bố hai bước ghi là nguyên tử xuyên dịch vụ.
- Các phiên bản ứng dụng cũ chưa biết bảng mới cần được nâng cấp hoặc hỗ trợ bởi cơ chế tương thích được kiểm chứng trước khi chặn cột cũ.
- Consumer đọc mới chỉ chuyển sau khi đối soát độ đầy đủ; consumer đọc cũ chỉ ngừng sau khi không còn dùng.

Một lộ trình thường là **dual-read với so sánh kết quả** hoặc **shadow-read**, rồi chuyển từng consumer sang bảng mới. Không cho nhân viên sửa cột địa chỉ cũ trong khi service mới sửa snapshot độc lập mà không có quy tắc conflict.

### 6.5. Khi nào được bỏ cột cũ?

Chỉ sau khi:

1. Tất cả writer dùng đường mới.
2. Các ứng dụng, báo cáo, export, job, CDC và cache không còn đọc cột cũ.
3. Dữ liệu đã được kiểm tra theo **từng đơn cần giao**.
4. Bản chụp cũ có retention và quyền phù hợp.
5. Các đường rollback còn khả thi hoặc đã hết hạn cần hỗ trợ.
6. Nhóm sở hữu chấp thuận thay đổi mang tính không đảo ngược.

**Một bảng ít cột hơn không tự là mô hình tốt hơn.** Giá trị nằm ở ranh giới ownership, grain và quyền truy cập rõ hơn.

## 7. Tách thực thể không chỉ là chuẩn hóa cột

### 7.1. Tách 1:1 vì vòng đời hoặc quyền

Ví dụ **order_delivery_snapshots** có grain một snapshot/đơn, có thể tách 1:1 vì nhiều consumer đơn hàng **không cần đọc địa chỉ**, và snapshot có quyền/retention riêng.

Nhưng nếu dữ liệu luôn được đọc/ghi cùng, cùng quyền, không lớn và không có lifecycle khác, tách bảng có thể tăng JOIN/chi phí ghi mà không cải thiện mô hình. **Không có quy tắc “mọi nhóm cột phải thành thực thể riêng”.**

### 7.2. Tách 1:N vì thực thể thực sự có nhiều phiên bản hoặc phần tử

Một bảng **products(product_id, sku, name, color, size, stock)** có thể không diễn đạt được sản phẩm có nhiều SKU. Một cách tách có thể là:

~~~text
catalog_products
  product_id               -- grain: một nhóm sản phẩm
  product_name

product_variants
  variant_id               -- grain: một SKU/biến thể
  product_id               -- FK tới catalog_products
  sku
  color, size

inventory_balances
  variant_id, warehouse_id -- grain: một SKU tại một kho
  on_hand_quantity
~~~

Nếu trước đây **product_id** đồng nghĩa với SKU nhưng nay product_id đồng nghĩa với nhóm sản phẩm, đây là **thay đổi ngữ nghĩa ID**, không chỉ chuyển cột. Các dòng đơn lịch sử cần biết **SKU thực sự đã mua**, không được tham chiếu tùy ý sang một nhóm sản phẩm chung rồi làm mất màu/size.

Một mapping **legacy_product_id → variant_id** có thể phải được lưu và đối soát. Không chọn mặc định biến thể đầu tiên khi source có nhiều biến thể hợp lệ.

### 7.3. Tách theo ownership giữa các dịch vụ

Nếu Payment và Order có vòng đời riêng, tách bảng trong cùng database có thể là bước đầu; tách sang database riêng còn thêm ranh giới giao dịch và vận hành. Khi chuyển:

- Xác định **ai được ghi mỗi sự thật**.
- Không cho hai dịch vụ cùng quyết định **payment_status** bằng các UPDATE độc lập.
- Dùng contract/event có version để chuyển trạng thái dẫn xuất khi cần.
- Giữ sự kiện capture/refund ở nguồn có thẩm quyền, không suy số tiền đã thu chỉ từ order.status.
- Có cơ chế chặn ghi trùng, xử lý retry và bù trừ khi tác vụ xuyên dịch vụ lỗi.

**Sự chia tách code/service không làm biến mất bất biến nghiệp vụ**; nó làm bất biến ấy cần một giao thức được diễn đạt rõ hơn.

## 8. Ví dụ 3 — Hợp nhất thực thể: hai bản ghi cùng một khách?

Giả sử nhập CRM tạo **C-101** và **C-202** trong cùng tenant. Có người đề xuất:

~~~sql
-- KHÔNG chạy như cách merge tổng quát.
UPDATE orders
SET customer_id = 'C-101'
WHERE customer_id = 'C-202';

DELETE FROM customers
WHERE customer_id = 'C-202';
~~~

Ngay cả khi thêm điều kiện tenant, script này vẫn thiếu:

- Hai tài khoản đã được **xác minh thật sự thuộc cùng chủ thể** chưa?
- Có **đơn/chứng từ phải giữ ID khách tại thời điểm giao dịch** không?
- Hai tài khoản có **quyền truy cập**, mật khẩu, MFA, consent và hồ sơ thanh toán khác nhau không?
- Cùng một đơn có thể được truy cập từ cả hai tài khoản sau merge không?
- Các bảng loyalty, reward, coupon, return, support, search và analytics có xử lý cùng quy tắc không?
- Có cần khả năng **tách lại** nếu hóa ra merge nhầm không?
- ID **C-202** có còn tồn tại trong hợp đồng API hoặc sự kiện cũ không?

Một người có nhiều tài khoản **không mặc nhiên có quyền truy cập chéo toàn bộ đơn**. Merge hồ sơ hoặc quyền truy cập là một **quyết định nghiệp vụ và an ninh** cần phê duyệt, không chỉ thao tác FK.

### 8.1. Phân biệt ba khái niệm dễ bị gộp

| Tình huống | Có nên hợp nhất? | Thao tác có thể cần |
| --- | --- | --- |
| Hai bản ghi là duplicate của **cùng một thực thể** do import lỗi | Có thể, sau xác minh | Chọn canonical, alias, chuyển quan hệ theo chính sách |
| Một người sở hữu **hai tài khoản hợp lệ** | Không nhất thiết | Có thể tạo quan hệ owner / account link có quyền riêng |
| Hai pháp nhân/đơn vị được **sáp nhập** | Không phải merge ID đơn giản | Lịch sử pháp lý, hiệu lực thời gian, quyền và nghĩa vụ |
| Một sản phẩm bị đổi mã SKU | Thường là alias/đổi mã, không phải gộp sản phẩm | Giữ lịch sử SKU và tham chiếu biến thể |
| Hai địa chỉ có cùng chuỗi văn bản | Không đủ chứng minh cùng người/địa điểm nghiệp vụ | Chuẩn hóa địa chỉ, có thể dùng địa chỉ dùng chung nếu phù hợp |

**Tiêu chí hợp nhất nằm ở nhận diện thực thể và bất biến**, không nằm ở việc hai hàng có cùng email, cùng tên hoặc cùng số điện thoại. Những thuộc tính ấy có thể thay đổi, dùng chung hoặc nhập sai.

## 9. Thiết kế canonical ID và bảng alias thay vì xóa ngay lịch sử

Với sơ đồ customers đã có **(tenant_id, customer_id)**, có thể thêm bảng ánh xạ:

~~~sql
CREATE TABLE customer_merge_aliases (
    tenant_id BIGINT NOT NULL,
    alias_customer_id TEXT NOT NULL,
    canonical_customer_id TEXT NOT NULL,
    decision_ref TEXT NOT NULL,
    merged_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, alias_customer_id),
    FOREIGN KEY (tenant_id, alias_customer_id)
        REFERENCES customers (tenant_id, customer_id),
    FOREIGN KEY (tenant_id, canonical_customer_id)
        REFERENCES customers (tenant_id, customer_id),
    CHECK (alias_customer_id <> canonical_customer_id)
);
~~~

Trong ví dụ:

~~~text
tenant 17:
  C-202 -> C-101    (verified merge decision M-987)
  C-101 -> C-101    (ngầm hiểu canonical, không cần lưu alias)
~~~

Một hàm truy vấn có thể giải ID alias thành canonical theo mapping hiện tại **được quản lý**. Nhưng thiết kế này mới bảo vệ được:

- Alias chỉ có **một đích** tại một thời điểm (PRIMARY KEY).
- Alias và canonical thuộc cùng tenant có hàng khách tương ứng (FK).
- Alias không tự trỏ chính nó (CHECK).

Nó **chưa ngăn chuỗi C-202 → C-101 → C-500** hoặc vòng **C-101 → C-202 → C-101**, cũng chưa đảm bảo canonical không bị xóa/khóa sau đó. Phải có thuật toán và giao dịch **chỉ cho alias trỏ tới ID canonical cuối cùng**, không cho canonical trở thành alias khi còn phụ thuộc hoặc phải cập nhật chuỗi có kiểm soát. Có thể dùng kiểm tra graph/recursive traversal và khóa các tài khoản tham gia theo thứ tự nhất quán; không suy rằng FK tự ngăn cycle.

### 9.1. Bảng alias không phải chứng cứ rằng đã được phép chia sẻ quyền

Sau khi xác minh duplicate, có thể quyết định:

- API tra mã cũ trả **canonical public ID** theo chính sách.
- Đơn lịch sử vẫn giữ **customer_id** gốc để giải thích chứng từ.
- Màn hình hiện hành gộp đơn qua alias **chỉ khi quyền truy cập đã được thiết lập rõ**.
- Hệ thống khách hàng tách **account login**, **customer profile** và **legal party** nếu nghiệp vụ cần.

Không nên cho phép mọi người đăng nhập vào một tài khoản trong nhóm tự đọc toàn bộ tài khoản khác chỉ vì có alias. **Authorization, consent và quyền truy cập dữ liệu** phải được xem xét độc lập với quyết định canonical hóa.

### 9.2. Các bước merge có kiểm soát

1. **Xác minh cùng thực thể** bằng nguồn/tiêu chí tin cậy và phê duyệt.
2. **Đóng băng quyết định/các ghi xung đột** trong phạm vi cần thiết, khóa định danh tham gia khi cập nhật mapping.
3. **Chọn canonical ID** theo một chính sách: có thể là tài khoản có lịch sử hợp lệ nhất, không nhất thiết ID nhỏ nhất.
4. **Ghi decision_ref, người/phương pháp phê duyệt, thời điểm** và khả năng xem lại.
5. **Tạo alias** và bảo đảm không có cycle/chains ngoài quy tắc.
6. **Giải quyết thuộc tính xung đột theo field**: email đã xác minh, phone, địa chỉ, consent, loyalty, fraud flag không cùng một quy tắc.
7. **Quyết định quan hệ nào được chuyển**: read profile, quyền đăng nhập, đơn lịch sử, tài khoản thanh toán, support tickets.
8. **Tính lại projection/analytics** nếu phép đếm khách duy nhất thay đổi, có ghi nhận thời gian hiệu lực.
9. **Kiểm tra bảo mật**: không làm lộ đơn, địa chỉ, payment của chủ thể không được phép.
10. **Duy trì legacy alias** đến khi mọi consumer chuyển và quy định retention cho phép.

Một quyết định merge cần tính được **tác động và rollback**. Nếu sau này phát hiện nhầm, việc vẫn giữ ID cũ trong order và một mapping có audit thường dễ sửa hơn cách đã ghi đè mọi dấu vết nguồn.

## 10. Hợp nhất thuộc tính: conflict resolution phải theo field

Giả sử hồ sơ canonical và alias có:

| Thuộc tính | C-101 | C-202 | Quy tắc cần có |
| --- | --- | --- | --- |
| Tên hiển thị | An Nguyễn | Nguyễn Văn An | Ưu tiên nguồn đã xác minh hoặc giữ lịch sử, không lấy chuỗi dài hơn |
| Email | an@example.test (verified) | old@example.test | Quy tắc email active, trạng thái xác minh, consent |
| Số điện thoại | Có từ năm trước | Mới xác minh | Theo thời điểm xác minh và quyền sử dụng |
| Địa chỉ mặc định | Hà Nội | Đà Nẵng | Không tự gộp với **địa chỉ đơn đã chốt** |
| Điểm thưởng | 100 | 50 | Theo sổ giao dịch điểm, chống cộng trùng |
| Refund/chargeback | Có | Không | Không xóa cờ rủi ro khi gộp |
| Consent marketing | Có | Không | Không mặc định chọn “Có” vì một bên đã đồng ý |

Các giá trị trên chỉ là ví dụ; **không có luật phổ quát lấy giá trị mới nhất cho mọi field**. “Mới” có thể là mốc nhập vào hệ nhập liệu, không phải thời điểm nghiệp vụ có hiệu lực. Consent và quyền truy cập có chính sách riêng; không tự mở rộng quyền bằng merge.

### 10.1. Không được SUM hai số dư nếu có sự kiện trùng

Hai bản ghi loyalty có thể chứa cùng một event thưởng nhập từ hệ thống thứ ba. Nếu cộng **balance 100 + balance 50 = 150** mà không đối chiếu ledger gốc, hệ thống có thể tạo điểm ảo.

Nên xác định **grain của fact điểm thưởng** là một sự kiện cấp/trừ với ID nguồn, đối soát các sự kiện trùng và tính lại balance theo canonical khi được phép. Tương tự, báo cáo **COUNT(DISTINCT customer_id)** trước merge có thể là 2, sau merge là 1; số đơn/tổng tiền phải không bị nhân hoặc mất do JOIN alias.

### 10.2. Hợp nhất tại thời điểm nào?

Nếu hai tài khoản được nhập chung vào tháng 11 nhưng doanh nghiệp muốn báo cáo khách duy nhất của tháng 1:

- **Báo cáo theo danh tính hiện nay:** có thể canonical hóa mọi giao dịch về một customer hiện tại, nếu quy tắc nghiệp vụ cho phép.
- **Báo cáo theo danh tính được biết tại thời điểm tháng 1:** có thể cần giữ hai identity khác nhau vì quyết định merge chưa tồn tại khi ấy.
- **Báo cáo kiểm toán:** phải biết lúc nào quyết định hợp nhất được ghi nhận và khi nào nó được xem là có hiệu lực.

Một mapping alias không có version/time chỉ trả lời **quan hệ canonical hiện tại**, không đủ tái tạo mọi trạng thái đã biết trong quá khứ. Nếu cần truy vấn lịch sử quyết định, hãy lưu **effective time** và **recorded time** hoặc event audit phù hợp, thay vì UPDATE một hàng alias rồi xóa dấu vết cũ.

## 11. Các lỗi migration phổ biến

| Lỗi | Vì sao nguy hiểm | Cách phòng tránh |
| --- | --- | --- |
| Đổi tên cột rồi coi là chuyển khóa | FK, consumer và tính duy nhất vẫn theo cấu trúc cũ | Thêm khóa mới, đối soát, chuyển tham chiếu có kiểm soát |
| Dùng **CASCADE** để drop PK đang có FK | Có thể xóa hàng rào ràng buộc cần thiết | Khảo sát dependency, chuyển FK trước |
| Backfill chạy một lần, bỏ qua ghi đồng thời | Tạo hàng mới thiếu khóa, mapping lệch | Giao thức writer chuyển tiếp + checkpoint + đối soát cuối |
| Sinh ID mới cho mỗi retry | Một thực thể có nhiều ID sau reprocessing | Idempotency, unique business key, mapping bền |
| Cho hai cột cũ/mới cùng được sửa độc lập | Hai nguồn chuẩn xung đột | Một chiều dẫn xuất, so mismatch |
| Gộp theo email/phone giống nhau | Một contact có thể dùng chung, thay đổi hoặc nhập sai | Quyết định identity có bằng chứng và phê duyệt |
| Ghi đè order.customer_id trong mọi lịch sử | Mất khả năng biết giao dịch ban đầu thuộc tài khoản nào | Giữ reference gốc, alias/canonical view |
| Đưa toàn bộ PII theo khi tách bảng | Tăng số bản sao và nơi truy cập | Data minimization, quyền theo mục đích |
| Chuyển read path trước khi có FK/data đầy đủ | API trả sai/thiếu đơn | Shadow read, monitor mismatch, cutover theo nhóm |
| Bỏ nguồn cũ ngay sau deploy | Không rollback, consumer cũ lỗi | Expand–migrate–contract với tiêu chí ngừng |
| Chỉ so COUNT(*) | Mất một hàng và nhân một hàng có thể bù nhau | So khóa, quan hệ, payload và tổng số đo |
| Tính tiền từ bản sao chưa hội tụ | Ra quyết định trên dữ liệu eventual stale | Dùng nguồn authoritative cho bất biến cần tức thời |

Đặc biệt, **“schema chạy được” không đồng nghĩa “dữ liệu còn đúng”**. Một FK trỏ tới hàng tồn tại có thể vẫn trỏ sai **khách, tenant, phiên bản thời gian hoặc quyền sở hữu**.

## 12. Giao dịch, online migration và khóa vận hành

### 12.1. Không phải mọi thay đổi DDL đều an toàn ở giờ cao điểm

Một số thao tác như **ADD COLUMN không default tốn kém**, **CREATE INDEX CONCURRENTLY**, **VALIDATE CONSTRAINT** có thể được dùng để giảm tác động, nhưng khả năng online phụ thuộc phiên bản PostgreSQL, kích thước bảng, lock, workload và truy vấn dài đang chạy.

Trước khi chạy:

- Đo số hàng, tốc độ ghi, kích thước bảng/index và tính phân bố tenant.
- Xác định thao tác cần **ACCESS EXCLUSIVE** hay lock khác, thời gian chờ lock và khả năng block.
- Thiết lập **lock_timeout**, **statement_timeout** và batching theo chính sách hệ thống.
- Thử trên bản dữ liệu lớn và có ghi đồng thời; không chỉ test một bảng 20 hàng.
- Quan sát WAL, replication lag, disk headroom, autovacuum và số transaction dài.
- Chuẩn bị dừng/tiếp tục khi job backfill lỗi mà không tạo dữ liệu trùng.

**Không chạy một danh sách ALTER TABLE lớn như thể nó là một transaction miễn phí.** Nếu mục tiêu yêu cầu độ sẵn sàng cao, tách thao tác thành các pha tương thích như phần 3.

### 12.2. Các phiên bản ứng dụng cùng tồn tại

Trong rolling deployment, một số instance có thể còn code cũ. Cần bảng tương thích:

| Phiên bản ứng dụng | Đọc customer_id | Ghi customer_id | Đọc customer_sk | Ghi customer_sk |
| --- | --- | --- | --- | --- |
| Legacy v1 | Có | Có | Không | Không |
| Transition v2 | Có | Có | Có với fallback rõ | Có từ mapping |
| New v3 | Chỉ phục vụ tương thích | Khi còn required | Có | Có |
| Sau contract | Theo yêu cầu legacy còn lại | Theo chính sách | Có | Có |

Nếu v1 còn ghi mà không điền customer_sk, **không thêm ràng buộc NOT NULL mới** trước khi có bridge hợp lệ. Có thể trì hoãn constraint, nâng toàn bộ writer hoặc tạo cơ chế database đồng bộ an toàn trong giai đoạn chuyển tiếp.

**Fallback đọc không được che lỗi mãi mãi.** Mỗi lần fallback từ customer_sk sang customer_id nên có telemetry và hạn chấm dứt; nếu không, migration có thể sống ở trạng thái nửa chừng hàng năm.

## 13. API, event, cache và hệ phân tích cũng phải tiến hóa

### 13.1. API: hợp đồng ngoài ổn định

Giả sử API trả:

~~~json
{
  "orderId": "O-9001",
  "customerRef": "c32b27d1-6737-4d63-ae83-7f8c0cb1c912",
  "status": "CONFIRMED",
  "total": {
    "amount": "450000.00",
    "currency": "VND"
  }
}
~~~

API **không buộc công bố customer_sk** khi database chuyển sang BIGINT. Mapper đổi cách tra khóa bên trong, nhưng hợp đồng customerRef có thể giữ ổn định. Nếu schema public thật sự phải đổi, dùng version/compatibility contract theo consumer, không tự đổi trường vì tên cột mới.

### 13.2. Event và CDC: đừng phát sự thay đổi vật lý như nghiệp vụ mới

Một event:

~~~json
{
  "eventId": "5f7cbd41-38c6-41eb-8205-8be22a57fe41",
  "eventType": "OrderConfirmed",
  "schemaVersion": 1,
  "orderId": "O-9001",
  "customerRef": "c32b27d1-6737-4d63-ae83-7f8c0cb1c912",
  "occurredAt": "2026-11-22T03:00:00Z"
}
~~~

...không nên đổi thành phát **customer_sk** chỉ vì database vừa thêm cột. **CDC** ở mức bảng/cột có thể thay đổi khi rename/split/merge; consumer trực tiếp phụ thuộc CDC row sẽ bị ảnh hưởng. Một lớp mapping integration event với field nghiệp vụ ổn định có thể che refactor storage.

Khi một event cũ dùng legacy customer_id, consumer có thể cần **versioned alias resolution**. Phải hỗ trợ retry, out-of-order event và idempotency; không phát hai sự kiện **OrderConfirmed** cho một đơn chỉ vì đang nạp lại khóa.

### 13.3. Cache và search index

Cache key kiểu **customer:C-101:orders** có thể không còn phù hợp khi canonical là C-202, nhưng xóa cache và tái tạo phải tôn trọng quyền. Nếu hai identity từng có quyền xem khác nhau, **gộp cache** có thể gây lộ dữ liệu.

Các projection/search index cần có:

- Source/canonical version hoặc checkpoint.
- Cơ chế rebuild từ nguồn đã xác minh.
- Xử lý alias/redirect, xóa cache theo cả ID cũ và mới khi phù hợp.
- Không lộ PII hoặc tài khoản chéo chỉ vì hai mã được merge.
- Kiểm tra dữ liệu mới sau đổi FK không bị ghi lùi bởi event cũ.

### 13.4. Warehouse và SCD Type 2

Trong kho phân tích, **customer_key** có thể là surrogate key của một **phiên bản dimension** tại thời điểm giao dịch, khác **customer_sk** của OLTP. Không dùng lại con số ở hai hệ như một khóa có cùng ngữ nghĩa nếu chưa có hợp đồng.

Khi merge khách:

- **COUNT DISTINCT customer** có thể thay đổi theo định nghĩa canonical hiện hành.
- **Doanh thu, số đơn, số lượng dòng** không được tự thay đổi vì phép đổi ID.
- Phải biết báo cáo phân loại **theo customer lúc mua** hay **canonical hiện hành**.
- Nếu cập nhật dimension history hoặc fact FK hồi tố, cần restatement/đối soát các aggregate đã công bố.

**Không dùng việc đổi khóa khách làm cớ viết lại giá, địa chỉ, trạng thái đơn hoặc thời gian của sự kiện đã chốt.**

## 14. Đối soát sau tách và hợp nhất: so cả grain và ý nghĩa

### 14.1. Sau tách order_delivery_snapshots

Giả sử business rule là **đơn vật lý đã xác nhận phải có một bản snapshot giao**. Có thể kiểm tra đơn còn thiếu snapshot khi có cột phân loại đơn rõ:

~~~sql
SELECT o.tenant_id, o.order_id
FROM orders AS o
LEFT JOIN order_delivery_snapshots AS d
  ON d.tenant_id = o.tenant_id
 AND d.order_id = o.order_id
WHERE o.order_type = 'PHYSICAL'
  AND o.order_status = 'CONFIRMED'
  AND d.order_id IS NULL;
~~~

Đây là **truy vấn minh họa sau khi schema đã được mở rộng thêm order_type/order_status**; hai cột đó chưa nằm trong DDL rút gọn của phần 4. Không áp query nguyên xi vào schema demo nếu chưa có trường tương ứng. Nếu đơn có nhiều kiện hoặc chính sách lưu snapshot khác, bất biến cũng phải thay đổi.

Cần kiểm tra **nội dung** ở những hàng có cả dữ liệu cũ và mới, không chỉ số lượng; và nếu địa chỉ đã được chỉnh hợp lệ, phải biết bản nào là bản hiện hành theo revision.

### 14.2. Sau merge, giữ sự thật giao dịch không đổi

Một đối soát số đo đơn hàng trước và sau merge:

~~~sql
-- Chạy cùng kỳ, cùng nguồn orders và cùng currency.
SELECT
    tenant_id,
    currency,
    COUNT(*) AS order_count,
    SUM(confirmed_amount) AS confirmed_order_value
FROM orders
GROUP BY tenant_id, currency;
~~~

Phải so hai snapshot đồng nhất của **nguồn authoritative**, phân theo tenant/currency và mốc thời gian. Khi chỉ canonical hóa danh tính, **order_count và confirmed_order_value không nên đổi**. Nếu đổi, rất có thể có đơn bị thiếu/nhân hoặc truy vấn JOIN alias đã tạo fan-out.

Với **distinct customer count**, kết quả có thể đổi **có chủ đích** sau merge. Do đó phải có hai metric rõ:

- **distinct_source_accounts**: đếm các tài khoản nguồn theo ID gốc.
- **distinct_canonical_customers**: đếm khách theo mapping canonical được phê duyệt, theo thời điểm hợp đồng đã định.

Đừng tuyên bố tất cả dashboard giữ nguyên sau merge, và cũng đừng chấp nhận mọi thay đổi dashboard là hợp lệ. **Phải biết metric nào được phép đổi.**

### 14.3. Các kiểm tra bảo mật bắt buộc

- Không có FK mới trỏ customer của **tenant khác**.
- Không có request chỉ nhờ alias mà tự động được đọc đơn của một tài khoản khác không thuộc quyền.
- Các ID legacy đã ngừng sử dụng không bị cấp lại sai thời kỳ.
- Token, contact và consent không bị gộp bằng quy tắc ngầm.
- Bản sao ngoài API/event/search/export không lộ customer_sk hay thông tin nhạy cảm mới.
- Người dùng bị hạn chế/xóa dữ liệu theo chính sách không bị **tái tạo** từ backfill hoặc replay cũ.

**Data integrity và privacy là hai bộ kiểm thử song song.** Một migration có FK hợp lệ nhưng tăng quyền truy cập ngoài phạm vi vẫn là migration không đạt yêu cầu.

## 15. Rollback và forward-fix cho thay đổi khó đảo ngược

| Tình huống | Phục hồi có thể chọn | Điều cần chuẩn bị |
| --- | --- | --- |
| Chỉ thêm customer_sk, chưa cutover | Dừng writer mới, quay đọc về khóa cũ | Khóa cũ/FK còn nguyên, đồng bộ đã kiểm tra |
| Đã chuyển reader nhưng vẫn ghi khóa cũ + mới | Chuyển đọc về v1 | Telemetry, mapping và không có sai nghĩa ID |
| Đã drop khóa cũ và ngừng lưu legacy ID | Khó rollback code/dữ liệu | Backup, mapping bền, kế hoạch forward-fix |
| Tách snapshot nhưng bản mới sai | Quay về nguồn cũ nếu còn đúng và đủ | Shadow compare, version và dual-read |
| Đã xóa cột PII cũ theo chính sách | Không nên phục hồi bừa từ backup | Quy trình khôi phục tôn trọng quyền/retention |
| Merge nhầm hai khách nhưng giữ alias/audit | Hủy/đảo quyết định và sửa quyền/read model | Nhật ký merge, quan hệ gốc và test bảo mật |
| Merge nhầm rồi rewrite mọi chứng từ, xóa nguồn | Có thể không tách lại đầy đủ | Quyết định tránh bước không đảo ngược, audit/backup |

**Rollback không nên xâm phạm yêu cầu xóa/hạn chế dữ liệu.** Khôi phục backup cũ để quay schema có thể tái sinh contact hoặc quyền đã được thu hồi. Kế hoạch restore phải áp dụng lại các quyết định bảo vệ dữ liệu hợp lệ trước khi công bố.

Một số tình huống tốt hơn bằng **forward-fix**: giữ schema mới, sửa mapping hoặc restate dữ liệu sai, sau đó đối soát. Việc chọn rollback hay forward-fix phụ thuộc phần nào có thể đảo ngược mà không phá bất biến.

## 16. So sánh tác động trong relational, document, graph và analytics

| Mô hình | Đổi khóa | Tách thực thể | Hợp nhất thực thể |
| --- | --- | --- | --- |
| **Relational** | PK/UK/FK, index, transaction, constraint validation | 1:1, 1:N, FK, quyền, giao dịch | Canonical ID, alias, FK lịch sử, uniqueness |
| **Document** | **_id** thường gắn sâu vào read/writes và references | Tách embedded subdocument thành collection hoặc ngược lại | Các document tham chiếu ID cũ và snapshot nhúng |
| **Graph** | Node/edge identity và traversal references | Tách node loại mới, thêm edge có ngữ nghĩa | Merge node dễ nhân/mất edge, quan hệ và thời gian |
| **Time-series** | Sensor/device ID qua hàng tỷ event | Tách device metadata khỏi raw samples | Không tự gộp chuỗi của hai sensor nếu là hai nguồn đo khác |
| **Analytics** | Fact/dimension surrogate keys, lineage | Fact grain/dimension history có thể đổi | Distinct count, SCD và các báo cáo hồi tố |

### 16.1. Document model

Nếu Order được lưu như document với **_id** công khai và **items[]** nhúng, việc đổi từ số thứ tự sang UUID không phải một lệnh đổi PK đơn giản: phải xét các document khác tham chiếu ID cũ, event, index, cache và các client dùng _id.

Một cách an toàn có thể là **giữ ID cũ như alias** và thêm trường public ID ổn định, xây read projection mới, chuyển reader từng đợt. Tách **shippingAddress** khỏi document Order đòi quyết định snapshot, tính nguyên tử và quyền tra cứu; không phải cứ tách collection là bảo mật tốt.

### 16.2. Graph model

Hợp nhất hai node **Customer** có thể làm nhiều cạnh **PLACED_ORDER**, **OWNS_ACCOUNT** và **BELONGS_TO** dồn về một node. Nếu hệ graph dùng một cạnh để biểu diễn “đã từng mua”, merge có thể làm mất số lần sự kiện, mốc thời gian và thuộc tính cạnh. Cần bảo toàn **event identity**, không dùng “hai cạnh có đầu/cuối giống nhau thì xóa một” khi nghiệp vụ đếm hai giao dịch.

Nếu dùng graph để tra quyền, việc merge node còn có thể **mở rộng đường traversal được phép**, tạo lỗi an ninh nếu chưa kiểm tra lại access policy.

### 16.3. Analytics và SCD

Khi sản phẩm được tách thành product/variant, fact dòng bán phải trỏ **variant tại thời điểm bán** nếu muốn phân tích màu/size. Hợp nhất hai nhóm sản phẩm hiện hành không được làm mất **sự phân biệt SKU trên hóa đơn**.

Với dimension Type 2, đổi natural key không nhất thiết đổi surrogate key của mỗi historical version. Một merge canonical có thể cần bảng mapping thêm thay vì ghi đè toàn bộ fact key. Mọi thay đổi metric cần công bố **grain, effective time và recomputation policy**.

## 17. Thiết kế một kế hoạch chuyển đổi có thể thực thi

Mẫu quyết định trước khi triển khai:

| Hạng mục | Ví dụ cần ghi |
| --- | --- |
| **Lý do thay đổi** | Legacy ID có thể tái sử dụng; cần ranh giới giao hàng; duplicate CRM |
| **Đối tượng có thẩm quyền** | Customer Domain, Order Domain, Identity team |
| **Grain trước/sau** | Một tài khoản/tenant; một snapshot/đơn; một alias→canonical |
| **Khóa và scope** | (tenant, customer_id), customer_sk, public_customer_id |
| **Cấu trúc tương thích** | Cột cũ, cột mới, alias, view v1/v2 |
| **Các writer** | Bản app nào ghi ở mỗi pha, ai bảo đảm mapping |
| **Các reader/consumer** | API, batch, broker, CDC, warehouse, cache, partners |
| **Quy tắc lịch sử** | Đơn/giá/chứng từ giữ ID gốc hay canonical theo thời gian? |
| **Backfill** | Batch size, checkpoint, retry, xử lý dữ liệu không ánh xạ |
| **Ràng buộc** | Unique, FK, NOT NULL, tenant, chống cycle, quyền |
| **Acceptance metrics** | NULL=0, orphan=0, mismatch=0, p95 đọc/ghi và lag |
| **Cutover** | Theo tenant/canary, shadow read, feature flag |
| **Rollback/forward-fix** | Điểm còn đảo được, nguồn giữ để phục hồi |
| **Contract cleanup** | Mốc ngừng ID/field cũ, bằng chứng không còn consumer |

Một thay đổi mô hình đáng tin có **chỉ số có thể kiểm chứng**. “Deploy thành công” hoặc “script không báo lỗi” chưa đủ.

### 17.1. Gate trước khi đổi writer/read path

- Ghi mới sinh khóa mới đầy đủ, không tạo FK sai tenant.
- Backfill đạt ngưỡng đã duyệt cho mọi tenant; các trường hợp không ánh xạ được đã được xử lý rõ.
- FK/unique/constraint cần thiết đã được kiểm chứng phù hợp với mô hình mới.
- Shadow read trả cùng **ID public, trạng thái, giá và quyền** theo hợp đồng.
- Dịch vụ ngoài dùng event/API có version được kiểm thử, không tự dựa vào PK vật lý.
- Đường rollback hoặc forward-fix được mô phỏng và đo.
- Quyền PII, cache/analytics và retention được kiểm tra.
- Kế hoạch giám sát có người trực và tiêu chí dừng cutover.

### 17.2. Gate trước khi gỡ cấu trúc cũ

- Không còn reader và writer dùng khóa/trường cũ, hoặc có adapter được duyệt.
- Không còn event/queue/backfill cũ có thể ghi lùi.
- Không còn FK, view, trigger, index, job và báo cáo phụ thuộc.
- Dữ liệu đã đối soát toàn phần hoặc theo phương án được chấp thuận với bằng chứng phù hợp.
- Không còn mục đích chính đáng phải giữ legacy ID, ngoại trừ metadata/audit được bảo vệ.
- Việc drop đã được thử với backup, restore, lock và khả năng phục hồi.
- Owner và các consumer xác nhận kết thúc hợp đồng chuyển tiếp.

## 18. Bài tập vận dụng

### Bài 1 — Surrogate key và business key

Bảng khách có **PRIMARY KEY (tenant_id, customer_code)**. Nhóm muốn thay bằng **customer_sk BIGINT**, nhưng vài đối tác ngoài vẫn gửi customer_code.

**Câu hỏi:** Có cần đổi luôn ID API không? Hãy nêu các bước chuyển FK orders mà vẫn hỗ trợ đối tác.

### Bài 2 — UNIQUE chưa ngăn NULL

Nhóm đã tạo unique index cho **(tenant_id, customer_sk)** và tuyên bố “tất cả khách có surrogate key”. Một số hàng cũ vẫn có customer_sk NULL.

**Câu hỏi:** Điều gì sai trong kết luận? Cần những kiểm chứng/ràng buộc nào trước khi chuyển hoàn toàn?

### Bài 3 — Dual write sinh sai ánh xạ

Đơn O-9 có customer_id = C-1 nhưng customer_sk trỏ C-2 cùng tenant. Cả hai khách đều tồn tại nên FK mới hợp lệ.

**Câu hỏi:** Vì sao FK không phát hiện được lỗi ngữ nghĩa này? Viết nguyên tắc đối soát hai khóa.

### Bài 4 — Tách địa chỉ khi một đơn có nhiều kiện

Hệ thống cũ có một trường shipping_address trên orders, nhưng nay mỗi đơn có thể giao ba kiện tới ba địa chỉ khác nhau.

**Câu hỏi:** Grain **(tenant_id, order_id)** cho delivery snapshot có còn đủ không? Nên có thực thể/khóa nào?

### Bài 5 — Một sản phẩm có nhiều SKU

Bảng products trước đây có một SKU/row. Khi thêm màu và kích cỡ, nhóm chuyển product_id thành mã nhóm sản phẩm rồi cập nhật mọi dòng đơn cũ về nhóm.

**Câu hỏi:** Mất sự thật gì? Cách giữ quan hệ order item với biến thể đúng là gì?

### Bài 6 — Merge theo email

C-101 và C-202 có cùng email gia đình nhưng là hai người khác nhau. Job tự merge rồi cho tài khoản C-101 xem toàn bộ đơn của C-202.

**Câu hỏi:** Lỗi nhận diện và bảo mật là gì? Cần gate nào trước merge?

### Bài 7 — Alias có vòng

Một bảng mapping chứa A→B, B→C rồi một job chèn C→A. Cả A, B, C đều tồn tại và có FK hợp lệ.

**Câu hỏi:** Vì sao cấu trúc không hợp lệ? Làm thế nào để phòng tránh mà không dựa vào mỗi FK?

### Bài 8 — Số dư loyalty sau merge

Hai tài khoản được xác minh trùng, bảng balance ghi 100 và 50 điểm; nhưng có một event thưởng 20 điểm đã xuất hiện ở cả hai nguồn.

**Câu hỏi:** Có thể cộng 100+50 không? Mô hình fact nào cần đối soát?

### Bài 9 — Một số báo cáo thay đổi sau merge

Sau merge hai tài khoản, **COUNT DISTINCT customer** giảm từ 2 xuống 1, còn **SUM confirmed_amount** cũng giảm 20%.

**Câu hỏi:** Sự thay đổi nào có thể hợp lệ và sự thay đổi nào cần điều tra?

### Bài 10 — Rollback sau khi drop khóa cũ

Nhóm đã drop customer_id khỏi orders, nhưng phát hiện một consumer lâu năm vẫn cần nó và không có bảng ánh xạ đầy đủ.

**Câu hỏi:** Vì sao không thể đảm bảo rollback đơn giản? Lẽ ra cần gate nào trước contract?

### Bài 11 — Migrate trong khi nhiều phiên bản ứng dụng chạy

Một phần API v1 vẫn chỉ ghi customer_id, API v2 ghi cả hai khóa. Nhóm thêm NOT NULL(customer_sk) ngay sau khi deploy v2.

**Câu hỏi:** Rủi ro gì và có những phương án chuyển tiếp nào?

### Bài 12 — Hợp nhất pháp nhân có hiệu lực theo thời gian

Hai công ty sáp nhập từ 01/07 nhưng hóa đơn tháng 6 vẫn thuộc pháp nhân cũ. Nhóm sửa mọi foreign key lịch sử sang mã công ty mới.

**Câu hỏi:** Đó có phải merge duplicate đơn thuần không? Nên mô hình thời gian/quan hệ thế nào?

### Gợi ý lời giải

1. Không nhất thiết đổi ID public/đối tác. Thêm customer_sk, backfill và UNIQUE, thêm orders.customer_sk, ghi chuyển tiếp theo một mapping, đối soát, thêm FK/NOT NULL khi writer sẵn sàng, chuyển read path dần; giữ customer_code/alias đến khi hết consumer.
2. Unique index nullable có thể cho phép nhiều NULL. Phải đếm khách chưa có sk, bảo đảm người ghi mới không sinh NULL, thêm/validate ràng buộc NOT NULL và kiểm tra uniqueness, tenant mapping.
3. FK chỉ chứng minh customer_sk trỏ hàng tồn tại, không chứng minh nó là cùng khách với customer_id. JOIN orders với customers theo cả khóa cũ và khóa mới để so **expected_customer_sk = orders.customer_sk**, trên cùng tenant và snapshot.
4. Không. Cần grain **một shipment/kiện** hoặc một delivery revision phù hợp, ví dụ **(tenant_id, shipment_id)** tham chiếu order, với recipient/address riêng theo kiện.
5. Mất SKU, màu/size, giá trị đã chốt theo biến thể. Giữ **variant_id** hoặc snapshot SKU tại giao dịch, mapping legacy product ID sang biến thể có chứng cứ; product group và variant là hai thực thể khác nhau.
6. Email dùng chung không chứng minh cùng người; merge đã mở quyền truy cập trái phép. Cần nguồn xác minh identity, phê duyệt, kiểm tra tenant/account/legal party và authorization trước khi cho canonical truy cập đơn.
7. Cycle làm canonical resolution không có điểm dừng và có thể mở đường truy cập không rõ. Cần áp dụng mapping đến canonical cuối cùng, kiểm tra graph/cycle trong transaction có khóa phù hợp, bảo vệ cạnh mới trước khi commit.
8. Không cộng balance trực tiếp nếu có event trùng. Dùng **loyalty ledger** ở grain một sự kiện cấp/trừ điểm có ID nguồn, dedupe và tính lại balance theo quy tắc.
9. Distinct canonical customer giảm có thể đúng theo metric mới; tổng đơn/tiền giảm là dấu hiệu nghiêm trọng của mất hàng, JOIN sai hoặc lọc bỏ alias. Phải đối soát theo source order ID, tenant, currency và kỳ dữ liệu.
10. Khóa cũ đã bị xóa, mapping thiếu và contract ngoài chưa ngừng; rollback code không tái tạo được định danh mất. Lẽ ra phải inventory consumer, giữ alias, thử khôi phục và qua gate contract trước drop.
11. App v1 bị từ chối ghi, gây lỗi sản xuất. Chỉ thêm NOT NULL khi tất cả writer đã chuyển, hoặc có trigger/bridge đáng tin cấp khóa mới từ old key; cần monitor và chặn dual-write mismatch.
12. Không. Đây là **biến đổi pháp lý có hiệu lực thời gian**, không phải duplicate cùng identity. Giữ pháp nhân lịch sử, quan hệ predecessor/successor với effective time, hóa đơn tháng 6 tiếp tục trỏ pháp nhân gốc; báo cáo hiện hành có thể tổng hợp theo nhóm mới theo quy tắc riêng.

## 19. Ghi nhớ

**Chuyển khóa chính** là bảo toàn ánh xạ giữa định danh cũ và mới, cùng mọi quan hệ, trong khi các writer/reader được chuyển từng bước. **Tách thực thể** là xác định lại grain và ranh giới vòng đời, không chỉ cắt cột. **Hợp nhất thực thể** là quyết định nghiệp vụ về hai bản ghi có cùng danh tính hay không, cùng quy tắc quyền và lịch sử; không được giải quyết chỉ bằng UPDATE foreign key.

Trong mọi trường hợp, **đổi schema không được tự viết lại sự thật giao dịch**: giá đã chốt, địa chỉ giao của một lần giao, capture thanh toán và thời điểm sự kiện vẫn phải có nghĩa chính xác. Dữ liệu dẫn xuất có thể tái dựng; chứng từ lịch sử cần được bảo vệ theo quy trình riêng.

Trước khi chạy migration, hãy hỏi: **“Một ID mới đại diện cho điều gì, những tham chiếu nào phải chuyển, trường hợp nào cần giữ ID cũ để giải thích lịch sử, ai được quyền xem dữ liệu sau merge, và bằng chứng nào chứng minh không mất hoặc nhân sự thật?”**. Nếu trả lời bằng hợp đồng, ràng buộc, đối soát và kế hoạch phục hồi, mô hình có thể tiến hóa mà vẫn đáng tin.
