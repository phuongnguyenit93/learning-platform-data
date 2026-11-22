# Xóa lan truyền làm mất lịch sử cần giữ

## 1. Một lệnh xóa Customer có thể xóa cả hợp đồng và chứng từ

Giả sử hệ thống cho thuê thiết bị có `Customer`, `RentalContract`, `RentalItem` và `PaymentMovement`. Khách yêu cầu đóng tài khoản, ứng dụng gọi:

~~~sql
DELETE FROM customer
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;
~~~

Nếu khóa ngoại từ hợp đồng đến khách, dòng thuê đến hợp đồng và thanh toán đến hợp đồng đều cấu hình `ON DELETE CASCADE`, một lệnh tưởng chỉ tác động đến hồ sơ khách có thể **xóa toàn bộ lịch sử thuê, dòng thiết bị và giao dịch đã xác nhận**.

Hậu quả:

- Không biết ai đã thuê thiết bị nào, điều khoản nào và thời điểm giao/nhận.
- Không đối soát được khoản thu và hoàn tiền với nguồn thanh toán.
- Báo cáo lịch sử thay đổi sau khi tài khoản bị đóng; tổng tiền có thể bị giảm giả tạo.
- Mất bằng chứng giải thích hủy hợp đồng, tranh chấp hoặc thiết bị thất lạc.
- Các bản sao ở warehouse, cache, backup có thể còn dữ liệu, khiến nguồn và dữ liệu dẫn xuất bất đồng.
- Khôi phục backup có thể làm mất giao dịch mới phát sinh sau mốc backup hoặc tái sinh dữ liệu cá nhân đã được xử lý xóa.

**Nguyên nhân gốc:** nhầm **quan hệ tham chiếu** (“hợp đồng có khách”) với **quan hệ phụ thuộc vòng đời** (“hợp đồng không được tồn tại khi khách không còn tài khoản”).

Một ràng buộc khóa ngoại có thể hợp lệ về kỹ thuật nhưng sai về nghĩa nghiệp vụ. Xóa dữ liệu phải dựa trên **grain, điểm chốt sự việc, quyền sở hữu dữ liệu, retention và mục đích xử lý**, không dựa vào việc bảng có quan hệ 1:N.

### Tình huống xuyên suốt

Khách `CUS-42` có 3 hợp đồng thuê đã chốt, 7 dòng thuê, 5 giao dịch thu/hoàn đã xác nhận, một giỏ nháp 2 dòng và một hồ sơ chứa email/số điện thoại. Mục tiêu là **đóng tài khoản và xử lý dữ liệu liên hệ theo chính sách**, không mặc nhiên là xóa 3 hợp đồng và 5 giao dịch.

## 2. Định nghĩa chính xác ba loại thao tác: đóng, hủy và xóa

| Thao tác | Ý nghĩa nghiệp vụ | Không được suy ra |
| --- | --- | --- |
| `CloseCustomerAccount` | Ngừng quyền đăng nhập hoặc hoạt động tài khoản. | Mọi hợp đồng và payment đã xảy ra phải biến mất. |
| `CancelRentalContract` | Chuyển hợp đồng sang trạng thái hủy, có điều kiện và bằng chứng. | Có thể xóa các giao dịch đã xác nhận khỏi lịch sử. |
| `EraseCustomerPrivateProfile` | Xử lý thông tin cá nhân trong **phạm vi yêu cầu đã xác minh**. | Một SQL DELETE trên profile nghĩa là mọi bản sao đã bị xóa. |
| `PurgeExpiredDraftCart` | Xóa dữ liệu nháp hết hạn theo policy. | Có thể áp dụng tương tự cho hợp đồng đã ký. |
| `PurgeRetainedHistory` | Xóa lịch sử sau khi đã đáp ứng điều kiện retention và không còn ngoại lệ. | Mọi dữ liệu có cùng thời gian tạo đều có cùng thời hạn lưu. |

**Hủy một sự việc không tương đương xóa việc nó từng xảy ra.** Một hợp đồng bị hủy vẫn có thể cần hiển thị giá đã chốt, lý do hủy và thông tin refund. Một giao dịch `RefundRequested` không thể thay thế `RefundConfirmed` nếu provider chưa xác nhận đã hoàn tiền.

Không có thời hạn lưu trữ phổ quát áp dụng cho mọi hợp đồng hoặc mọi khu vực. Thời hạn, căn cứ giữ/xóa, legal hold và ngoại lệ phải do người có thẩm quyền xác định cho từng loại dữ liệu.

## 3. Mỗi quan hệ cần một chính sách vòng đời độc lập

| Quan hệ | Ý nghĩa tham chiếu | Chính sách xóa cần cân nhắc |
| --- | --- | --- |
| Customer → RentalContract | Hợp đồng gắn với khách. | Hợp đồng có thể cần tồn tại khi tài khoản đóng. |
| RentalContract → RentalItem | Dòng hàng mô tả thiết bị đã thỏa thuận. | Dòng đã chốt thường cần giữ cùng hợp đồng. |
| RentalContract → PaymentMovement | Giao dịch tiền gắn với hợp đồng. | Không xóa giao dịch đã xác nhận vì UI hủy hợp đồng. |
| DraftCart → DraftCartLine | Dòng chỉ là một phần giỏ nháp. | Có thể cascade khi xóa giỏ hết hạn, nếu policy cho phép. |
| Session → SessionToken | Token dùng cho phiên truy cập. | Có thể thu hồi/xóa, tách audit bảo mật cần giữ. |
| Customer → SearchProjection | Bản dẫn xuất để đọc/tìm kiếm. | Có thể purge/rebuild, không phải nguồn sự thật. |
| Transaction → AuditRecord | Ghi nhận thao tác và nguồn đã chốt. | Có retention/quyền riêng, không mặc định xóa theo parent. |

Một `OrderLine` đã được ký xác nhận có thể là thành phần không độc lập về nghiệp vụ nhưng vẫn phải **giữ lịch sử cùng Order**, không phải cascade vì Order bị ẩn khỏi màn hình. Điều kiện tiên quyết để dùng cascade là cha **được phép xóa vật lý** và mọi con bị xóa đều cùng vòng đời thật sự.

## 4. ON DELETE trong PostgreSQL hoạt động thế nào?

| Lựa chọn FK | Tác động khi xóa cha | Điều kiện phù hợp |
| --- | --- | --- |
| `ON DELETE CASCADE` | Tự xóa những hàng con tham chiếu. | Dữ liệu con không còn ý nghĩa/lý do giữ khi cha bị xóa. |
| `ON DELETE RESTRICT` | Chặn xóa cha nếu có hàng con. | Cần bảo vệ chứng từ/hàng lịch sử còn tham chiếu. |
| `ON DELETE NO ACTION` | Yêu cầu FK hợp lệ khi kiểm tra; mặc định kiểm tra cuối statement. | Có thể dùng constraint `DEFERRABLE` khi cần trì hoãn kiểm tra; phải kiểm chứng logic. |
| `ON DELETE SET NULL` | Gán cột tham chiếu ở con thành NULL. | Con có thể tồn tại không có cha và không mất bằng chứng cần giữ. |
| `ON DELETE SET DEFAULT` | Gán tham chiếu mặc định. | Default là một tham chiếu hợp lệ và có ý nghĩa nghiệp vụ thực. |

**RESTRICT và NO ACTION không hoàn toàn giống nhau:** với cơ chế PostgreSQL hỗ trợ, kiểm tra của NO ACTION có thể hoãn khi constraint được khai báo deferrable; hành động RESTRICT không được trì hoãn theo cách đó. Dù dùng cơ chế nào, một FK chỉ bảo vệ quan hệ, không thay thế chính sách quyền riêng tư hay retention.

Với FK tổ hợp gồm `tenant_id` và `customer_id`, `SET NULL` có thể xung đột `NOT NULL` hoặc làm mất tenant scope nếu gán sai cột. Cần thiết kế chính xác nullable field và phạm vi identity; không copy máy móc một ví dụ FK đơn cột vào hệ đa tenant.

## 5. Anti-pattern: chuỗi cascade hợp lệ về SQL, sai về dữ liệu

Đoạn DDL cố tình sai cho chứng từ cần giữ; **chỉ xem hoặc thử trong database cô lập**, không dùng nguyên mẫu trong production:

~~~sql
CREATE SCHEMA IF NOT EXISTS demo_bad;

CREATE TABLE demo_bad.customer (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    full_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE demo_bad.rental_contract (
    tenant_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    status_code TEXT NOT NULL,
    PRIMARY KEY (tenant_id, rental_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_bad.customer (tenant_id, customer_id)
        ON DELETE CASCADE
);

CREATE TABLE demo_bad.rental_item (
    tenant_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    item_code TEXT NOT NULL,
    PRIMARY KEY (tenant_id, rental_id, line_no),
    FOREIGN KEY (tenant_id, rental_id)
        REFERENCES demo_bad.rental_contract (tenant_id, rental_id)
        ON DELETE CASCADE
);

CREATE TABLE demo_bad.payment_movement (
    tenant_id UUID NOT NULL,
    movement_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency_code CHAR(3) NOT NULL,
    PRIMARY KEY (tenant_id, movement_id),
    FOREIGN KEY (tenant_id, rental_id)
        REFERENCES demo_bad.rental_contract (tenant_id, rental_id)
        ON DELETE CASCADE
);
~~~

~~~mermaid
flowchart TD
    C["DELETE customer"] --> R["CASCADE rental_contract"]
    R --> L["CASCADE rental_item"]
    R --> P["CASCADE payment_movement"]
    L --> HIST["Mất nội dung hợp đồng đã chốt"]
    P --> CASH["Mất bằng chứng thu/hoàn để đối soát"]
~~~

Database chỉ đang thi hành đúng ràng buộc đã khai báo. **Đây là lỗi thiết kế vòng đời, không phải bug của PostgreSQL.**

Nếu xóa một `customer` có 3 hợp đồng, 7 dòng và 5 movement, có thể biến mất đồng thời cả bốn cấp dữ liệu. Không kết luận một thao tác an toàn vì ứng dụng chỉ gọi một lệnh DELETE và nhận kết quả “1 row affected” ở bảng đầu vào.

## 6. Dò toàn bộ chuỗi cascade thay vì chỉ kiểm tra một FK

Khi rà soát một thao tác xóa, phải tìm các FK trỏ vào bảng cha và tiếp tục đi theo từng bảng con bị xóa.

PostgreSQL lưu thông tin foreign key trong `pg_constraint`:

~~~sql
SELECT con.conrelid::regclass AS child_table,
       con.confrelid::regclass AS parent_table,
       con.conname AS fk_name,
       CASE con.confdeltype
          WHEN 'a' THEN 'NO ACTION'
          WHEN 'r' THEN 'RESTRICT'
          WHEN 'c' THEN 'CASCADE'
          WHEN 'n' THEN 'SET NULL'
          WHEN 'd' THEN 'SET DEFAULT'
       END AS on_delete_action,
       pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint con
WHERE con.contype = 'f'
  AND con.connamespace = 'demo_bad'::regnamespace
ORDER BY parent_table, child_table, fk_name;
~~~

Kiểm tra:

1. Bảng được xóa → tất cả FK tham chiếu bảng đó.
2. Với mỗi FK `CASCADE`, tiếp tục tìm FK tham chiếu bảng con bị xóa.
3. Nhận diện nhiều đường cascade dẫn đến cùng bảng, khóa vòng, lượng hàng và tính nhất quán transaction.
4. Tìm trigger, stored procedure, job cleanup, ORM/JPA cascade và outbox/event handler.
5. Kiểm tra quyền thực thi, các query thiếu `tenant_id`, lịch xóa tự động và partition maintenance.
6. Mở rộng sang search, cache, warehouse, event store, backup/replica và dịch vụ liên quan.

Truy vấn `pg_constraint` **chỉ cho biết FK trong database đang xét**. Nó không cho biết xóa qua API service khác hoặc các side effect trong ứng dụng.

### Ba cơ chế tên giống nhưng tác động khác nhau

| Cơ chế | Tác động |
| --- | --- |
| `DELETE FROM parent ...` với FK `ON DELETE CASCADE` | Xóa các **hàng con có FK** tới hàng cha bị xóa, rồi có thể lan tiếp. |
| `TRUNCATE parent CASCADE` | Có thể truncate **toàn bộ các bảng tham chiếu** theo hành vi TRUNCATE, không chỉ hàng liên quan tới một khách. |
| `DROP TABLE parent CASCADE` | Xóa đối tượng schema và phụ thuộc tương ứng; không phải DELETE có điều kiện trên hàng. |

`TRUNCATE ... CASCADE` rất nguy hiểm khi bị hiểu nhầm là cách xóa “nhanh hơn” vài hàng của khách. Luôn review độc lập tác động toàn bảng.

## 7. Phân loại dữ liệu: chứng từ, dữ liệu tạm, PII và bản dẫn xuất

Một bảng có thể chứa nhiều loại dữ kiện với yêu cầu vòng đời khác nhau. Nên phân tích theo **ý nghĩa** thay vì chỉ theo tên bảng.

| Loại | Ví dụ | Nguyên tắc đánh giá |
| --- | --- | --- |
| **Business record đã chốt** | Hợp đồng, invoice, ticket đã phát hành. | Giữ trong phạm vi có căn cứ; chỉnh sai bằng correction/adjustment phù hợp. |
| **Confirmed financial movement** | Capture/refund được provider xác nhận. | Không xóa cùng tài khoản; cần đối soát bằng reference/ID. |
| **Đang xử lý** | Payment pending, refund chưa biết kết quả. | Không tự coi timeout là thất bại; giữ trạng thái đủ để recovery. |
| **Bản nháp/tạm** | Cart, draft line, temporary search. | Có thể cascade khi hết hạn và không còn yêu cầu giữ. |
| **Dữ liệu cá nhân hiện hành** | Email, điện thoại, display name. | Mục đích xử lý/retention/erasure riêng, phân quyền. |
| **Bản dẫn xuất** | Cache, search projection, dashboard mart. | Đồng bộ lifecycle và đối soát với nguồn có thẩm quyền. |
| **Audit/event history** | Sự kiện hủy hợp đồng, thay đổi quyền. | Có thể cần lịch sử độc lập, nhưng hạn chế PII và có retention riêng. |

**Không lấy retention của tài khoản làm retention cho mọi sự việc có customer_id.** Retention của hợp đồng có thể tính từ ngày hoàn tất hợp đồng, tranh chấp hoặc mốc nghiệp vụ được duyệt; dòng nháp có thể có lịch ngắn hơn.

Phải ghi chính xác **ai có quyền quyết định** một sự thật được chấp nhận và tồn tại bao lâu: Customer Identity sở hữu profile, Rental sở hữu hợp đồng, Payment sở hữu confirmed movements, Analytics sở hữu phép tính dẫn xuất.

## 8. Tách PII khỏi lịch sử giao dịch để giảm phụ thuộc vòng đời

Một cách mô hình hóa là tách:

- `CustomerSubject`: tham chiếu định danh tối thiểu và trạng thái tài khoản, có căn cứ lưu phù hợp.
- `CustomerPrivateProfile`: thông tin liên hệ được phép dùng ở hiện tại, xử lý quyền riêng tư riêng.
- `RentalContract`: chứng từ đã ký và các giá trị đã chốt.
- `RentalItem`: nội dung chứng từ, không phụ thuộc giá niêm yết hiện hành.
- `PaymentMovement`: sự việc thu/hoàn đã xác nhận với provider.
- `Projection`: bản sao phục vụ đọc, xóa/rebuild theo owner.

~~~mermaid
flowchart LR
    S[("CustomerSubject")] --> C[("RentalContract")]
    C --> I[("RentalItem")]
    C --> M[("PaymentMovement")]
    S --> P[("CustomerPrivateProfile: PII")]
    C -. "Sự việc có thẩm quyền" .-> H[("History / Audit")]
    P -. "Xử lý lifecycle theo policy" .-> E["Erasure workflow"]
~~~

Giữ `customer_id` hoặc surrogate ID không tự đồng nghĩa dữ liệu đã ẩn danh. Một mã có thể liên kết ngược với chủ thể qua hệ khác. **Pseudonymization không bằng anonymization**; retention, quyền và bản đồ các nguồn liên kết vẫn cần quản trị.

### Khi hợp đồng cần tên/địa chỉ đã ký

Nếu chứng từ thực sự phải lưu một giá trị tên/địa chỉ tại thời điểm ký theo nghĩa vụ hợp lệ, định nghĩa **snapshot chứng từ** và retention cho chính trường đó, không chỉ JOIN Profile hiện hành. Nhưng cũng không copy toàn bộ hồ sơ cá nhân vào mọi dòng hoặc sự kiện chỉ để tiện query.

## 9. Ví dụ PostgreSQL an toàn hơn: bảo vệ chứng từ bằng RESTRICT

Mô hình dưới đây tách hồ sơ riêng tư ra khỏi dòng giao dịch; đây là **một lựa chọn khi có căn cứ giữ lịch sử**. Nó không tự đáp ứng mọi trường hợp bắt buộc phải xóa hoàn toàn định danh.

~~~sql
CREATE SCHEMA IF NOT EXISTS demo_safe;

CREATE TABLE demo_safe.customer_subject (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    state_code VARCHAR(20) NOT NULL
        CHECK (state_code IN ('ACTIVE', 'CLOSED', 'ERASED_PROFILE')),
    closed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE demo_safe.customer_private_profile (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    email TEXT,
    phone_e164 TEXT,
    display_name TEXT,
    PRIMARY KEY (tenant_id, customer_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_safe.customer_subject (tenant_id, customer_id)
        ON DELETE RESTRICT
);

CREATE TABLE demo_safe.rental_contract (
    tenant_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    agreed_total_minor BIGINT NOT NULL CHECK (agreed_total_minor >= 0),
    currency_code CHAR(3) NOT NULL,
    signed_at TIMESTAMPTZ NOT NULL,
    status_code VARCHAR(20) NOT NULL
       CHECK (status_code IN
         ('SIGNED', 'ACTIVE', 'COMPLETED', 'CANCELLED')),
    PRIMARY KEY (tenant_id, rental_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_safe.customer_subject (tenant_id, customer_id)
        ON DELETE RESTRICT
);

CREATE TABLE demo_safe.rental_item (
    tenant_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    item_code TEXT NOT NULL,
    qty NUMERIC(18,3) NOT NULL CHECK (qty > 0),
    PRIMARY KEY (tenant_id, rental_id, line_no),
    FOREIGN KEY (tenant_id, rental_id)
        REFERENCES demo_safe.rental_contract (tenant_id, rental_id)
        ON DELETE RESTRICT
);

CREATE TABLE demo_safe.payment_movement (
    tenant_id UUID NOT NULL,
    movement_id UUID NOT NULL,
    rental_id UUID NOT NULL,
    provider_name VARCHAR(60) NOT NULL,
    provider_reference VARCHAR(120) NOT NULL,
    movement_type VARCHAR(12) NOT NULL
       CHECK (movement_type IN ('CAPTURE', 'REFUND')),
    amount_minor BIGINT NOT NULL CHECK (amount_minor > 0),
    currency_code CHAR(3) NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, movement_id),
    UNIQUE (tenant_id, provider_name, provider_reference),
    FOREIGN KEY (tenant_id, rental_id)
        REFERENCES demo_safe.rental_contract (tenant_id, rental_id)
        ON DELETE RESTRICT
);
~~~

Tác dụng và giới hạn:

1. `CustomerPrivateProfile` có thể được xử lý trong phạm vi PII **mà không xóa RentalContract và PaymentMovement**.
2. `customer_subject` giữ ID tối thiểu phục vụ quan hệ; nó **vẫn có thể là dữ liệu cá nhân** và cần căn cứ giữ, phân quyền, xử lý khi hết retention.
3. `ON DELETE RESTRICT` ngăn xóa cha khi các hàng đã chốt còn tham chiếu. Bản thân nó không định nghĩa ai được phép purge khi nghĩa vụ lưu đã hết.
4. FK tổ hợp gồm `tenant_id` giúp bảo vệ liên kết cùng tenant trong DB.
5. `provider_reference` phải thực sự unique theo phạm vi nguồn; nếu nhà cung cấp chỉ bảo đảm theo merchant account hoặc loại operation, cần chỉnh khóa phù hợp.
6. `currency_code` và `amount_minor` chỉ biểu diễn số tiền, không tự chứng minh doanh thu; confirmed movement phải lấy từ nguồn Payment được chấp thuận.
7. Nếu cần **xóa hoàn toàn customer_subject** trong lúc hợp đồng vẫn phải giữ, mô hình này phải được thiết kế lại về liên kết (hoặc dùng tham chiếu nullable phù hợp, tách định danh và chứng từ) theo chính sách. **Không** thả FK bừa để tạo orphan hoặc che dấu khả năng liên kết còn tồn tại.

## 10. Đặt đúng chính sách cho SET NULL và bản ghi tham chiếu

`SET NULL` phù hợp khi một quan hệ **thật sự tùy chọn** sau xóa cha.

Ví dụ ticket hỗ trợ vẫn có giá trị dù nhân viên được gán xử lý đã nghỉ:

~~~sql
CREATE TABLE demo_safe.support_operator (
    operator_id UUID PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE demo_safe.support_ticket (
    ticket_id UUID PRIMARY KEY,
    assigned_operator_id UUID
        REFERENCES demo_safe.support_operator (operator_id)
        ON DELETE SET NULL,
    subject_text TEXT NOT NULL
);
~~~

Trường này chỉ có ý nghĩa “người được gán hiện hành”; nếu cần biết **ai từng xử lý** thì phải lưu assignment history riêng. Nếu dùng SET NULL trên `rental_contract.customer_id`, phải có chính sách rõ làm sao đối soát chứng từ với khách/nguồn và quyền giữ dữ liệu, không tự biến toàn bộ lịch sử thành “không biết”.

`SET DEFAULT` còn dễ nguy hiểm: gán một ID khách mặc định giả để chạy FK có thể khiến nhiều chứng từ của người khác nhau bị quy về một khách “UNKNOWN”. Nó chỉ hợp lệ nếu default có nghĩa nghiệp vụ, tham chiếu tồn tại, phạm vi tenant đúng và nguồn giải thích còn đủ.

## 11. Soft delete không tương đương xóa dữ liệu cá nhân

**Soft delete** đánh dấu row thay vì DELETE vật lý:

~~~sql
ALTER TABLE demo_safe.customer_subject
ADD COLUMN deleted_at TIMESTAMPTZ;

UPDATE demo_safe.customer_subject
SET state_code = 'CLOSED',
    closed_at = COALESCE(closed_at, now()),
    deleted_at = now()
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id
  AND state_code = 'ACTIVE';
~~~

Nó có thể giúp giữ tham chiếu và tránh cascade, nhưng không chứng minh hoàn tất erasure:

- PII có thể vẫn ở profile, row mềm xóa, index, WAL, backup, cache và export.
- Query thiếu `deleted_at IS NULL` vẫn thấy row; query lịch sử JOIN nhầm với trạng thái hiện hành có thể bỏ fact.
- Unique email/phone có thể cản đăng ký mới hoặc gây ID reuse nếu bỏ constraint thiếu suy nghĩ.
- ORM delete/orphanRemoval vẫn có thể xóa vật lý các con dù cha chuyển state.
- `deleted_at` không cho biết trạng thái công tác xử lý ở tất cả downstream systems.

Nếu mục đích là **đóng tài khoản**, hãy gọi và đặt tên đúng command. Nếu là **xóa PII**, cần workflow kiểm chứng riêng. Nếu là **hủy hợp đồng**, dùng state/event thay vì xóa chứng từ.

## 12. Hủy nghiệp vụ và hoàn tiền là các sự việc mới, không phải xóa quá khứ

Một RentalContract từng có `SIGNED` có thể trở thành `CANCELLED`. Điều đó không làm biến mất `RentalContractSigned` hay thay nội dung thỏa thuận cũ.

Ví dụ state update tối thiểu:

~~~sql
UPDATE demo_safe.rental_contract
SET status_code = 'CANCELLED'
WHERE tenant_id = :tenant_id
  AND rental_id = :rental_id
  AND status_code IN ('SIGNED', 'ACTIVE')
RETURNING tenant_id, rental_id, status_code;
~~~

Đoạn này chỉ minh họa update; production cần quyền, reason, actor, version/concurrency, thời điểm, ràng buộc nghiệp vụ và outbox/audit phù hợp.

Tương tự, với `CAPTURE 500.000 VND` và `REFUND 100.000 VND` đã được xác nhận:

- Giữ movement CAPTURE 500.000 VND.
- Giữ movement REFUND 100.000 VND.
- Chỉ số net cash theo công thức đã duyệt là 400.000 VND, **không** biến CAPTURE gốc thành 400.000 hoặc xóa REFUND.
- Nếu refund mới ở trạng thái `REQUESTED`, chưa được tính như đã hoàn.

Đây là lý do payment history thường phải có **grain một movement đã xác nhận**, không phụ thuộc lifecycle của tài khoản.

## 13. CASCADE ở ORM cũng có thể phá chứng từ

Trong JPA/Hibernate:

~~~java
@Entity
class RentalContract {
    @OneToMany(
        mappedBy = "rentalContract",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<RentalItem> items;
}
~~~

Ở đây `CascadeType.ALL` bao gồm `REMOVE`; khi xóa entity cha, ORM có thể xóa các item. `orphanRemoval = true` có thể xóa một item khi bị gỡ khỏi collection lúc flush, ngay cả khi người viết code nghĩ chỉ đang sửa danh sách.

**Không nhầm:**

- `ON DELETE CASCADE` là hành vi do **DB foreign key** thực thi với lệnh DELETE bất kể client nào thực hiện.
- `CascadeType.REMOVE` và `orphanRemoval` là chính sách ORM.
- Trigger, job cleanup, stored procedure và handler nhận sự kiện có thể có tác động xóa khác.
- Một hệ có cả DB cascade và ORM cascade; cần điều tra cả hai.

Với giỏ nháp các phần tử chỉ sống theo giỏ, cascade có thể đúng. Với dòng hợp đồng đã chốt, phương thức `removeItem` có thể phải tạo một **correction/version** thay vì xóa dấu vết.

## 14. CASCADE vẫn hữu ích khi con thật sự không có vòng đời riêng

Mục tiêu không phải cấm tuyệt đối cascade mà là chỉ dùng khi **toàn bộ con được phép mất cùng cha**.

~~~sql
CREATE TABLE demo_safe.draft_cart (
    tenant_id UUID NOT NULL,
    cart_id UUID NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, cart_id)
);

CREATE TABLE demo_safe.draft_cart_line (
    tenant_id UUID NOT NULL,
    cart_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, cart_id, line_no),
    FOREIGN KEY (tenant_id, cart_id)
        REFERENCES demo_safe.draft_cart (tenant_id, cart_id)
        ON DELETE CASCADE
);
~~~

Điều kiện:

1. Giỏ chỉ là **draft**, không phải chứng từ đơn đã chốt.
2. Dòng giỏ không có nghĩa vụ lưu hoặc audit độc lập.
3. Xóa giỏ sau mốc hết hạn là việc được phép theo policy.
4. Nếu đã chốt thành đơn, dữ liệu phải được ghi thành Order/OrderLine ở nguồn có thẩm quyền **trước khi** xóa giỏ.
5. Có job cleanup với phạm vi tenant, batch, quan sát và khả năng xử lý retry.

Chính sách giống nhau về cardinality (1:N) có thể **khác nhau về xóa**, vì vòng đời và bằng chứng nghiệp vụ khác nhau.

## 15. Xóa private profile trong khi giữ lịch sử có căn cứ

Một giao dịch cục bộ minh họa **phạm vi Customer Profile**:

~~~sql
BEGIN;

DELETE FROM demo_safe.customer_private_profile
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;

UPDATE demo_safe.customer_subject
SET state_code = 'ERASED_PROFILE',
    closed_at = COALESCE(closed_at, now())
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;

COMMIT;
~~~

Đây **không phải** quy trình xóa dữ liệu cá nhân end-to-end. Nó chỉ xử lý bảng `customer_private_profile` của một database. Vẫn cần xét:

- Search, cache, analytics, export, audit, log và message broker.
- Backup/restore, replica, retention và giới hạn khả năng xóa tức thì.
- Có ID hay dữ kiện chứng từ còn liên kết ngược đến cá nhân không?
- Có ngoại lệ lưu giữ hợp lệ, nhiệm vụ đối soát hoặc tranh chấp nào không?
- Có dữ liệu bị ghi lại vào projection do event/snapshot cũ đến muộn không?

Trạng thái `ERASED_PROFILE` nên được hiểu là **profile ở nguồn này đã xử lý trong phạm vi xác định**, không phải “toàn tổ chức đã xóa mọi dữ liệu”.

## 16. Phân tích tác động trước một thao tác DELETE

Đừng coi việc một API nhận `customer_id` là đủ điều kiện xóa. Hãy đếm những chứng từ có nguy cơ bị tác động.

~~~sql
SELECT
    (SELECT COUNT(*)
     FROM demo_safe.rental_contract c
     WHERE c.tenant_id = :tenant_id
       AND c.customer_id = :customer_id) AS contracts_count,
    (SELECT COUNT(*)
     FROM demo_safe.rental_item i
     JOIN demo_safe.rental_contract c
       ON c.tenant_id = i.tenant_id
      AND c.rental_id = i.rental_id
     WHERE c.tenant_id = :tenant_id
       AND c.customer_id = :customer_id) AS items_count,
    (SELECT COUNT(*)
     FROM demo_safe.payment_movement p
     JOIN demo_safe.rental_contract c
       ON c.tenant_id = p.tenant_id
      AND c.rental_id = p.rental_id
     WHERE c.tenant_id = :tenant_id
       AND c.customer_id = :customer_id) AS movements_count;
~~~

**Đếm ở thời điểm T không bảo đảm số bị xóa ở T+1** nếu dữ liệu còn được cập nhật đồng thời. Khi cần precondition vững chắc, dùng isolation/locking hoặc workflow owner thích hợp. Với operation có thể xóa rất nhiều hàng, nên có giới hạn, phê duyệt và kiểm tra mọi nguồn trong phạm vi.

Checklist trước xóa:

- FK/ORM/trigger/job nào có thể xóa lan?
- Có hợp đồng đang hiệu lực, tranh chấp, legal hold hoặc refund pending không?
- Nguồn có cho phép xóa hay chỉ cho close/disable?
- Có thể giữ lịch sử cần thiết nhưng giảm dữ liệu nhận dạng không?
- Có đường purge theo tenant và ngày đúng retention không?
- Có snapshot/backup và runbook phục hồi đã được thử không?

Không chạy một DELETE nguy hiểm trên production chỉ để “thử rollback”. Database transaction có thể rollback row changes, nhưng side effects ngoài DB và các hành vi khác không nhất thiết đảo được theo kỳ vọng.

## 17. Thay CASCADE thành RESTRICT cần cả migration và thay đổi ứng dụng

Nếu đã phát hiện FK sai, chỉ sửa annotation ORM là không đủ; phải thay constraint ở database và mọi đường xóa cha.

Ví dụ trên schema thử nghiệm, **tên FK phải được xác minh thực tế** bằng `pg_constraint` trước khi dùng:

~~~sql
BEGIN;

ALTER TABLE demo_bad.rental_contract
DROP CONSTRAINT rental_contract_tenant_id_customer_id_fkey;

ALTER TABLE demo_bad.rental_contract
ADD CONSTRAINT rental_contract_customer_fk
FOREIGN KEY (tenant_id, customer_id)
REFERENCES demo_bad.customer (tenant_id, customer_id)
ON DELETE RESTRICT;

COMMIT;
~~~

Các lưu ý:

- Tên constraint tự sinh có thể khác; đoạn lệnh chỉ minh họa.
- DDL có lock và chi phí; benchmark trên môi trường gần production, chuẩn bị rollback/timeout.
- Nếu muốn dùng `NOT VALID` + `VALIDATE CONSTRAINT` cho bảng lớn, cần hiểu constraint nào hỗ trợ, khả năng enforcement cho dữ liệu mới và thứ tự cutover.
- **Không thêm RESTRICT mới rồi mặc định CASCADE cũ đã vô hiệu hóa.** Khi constraint CASCADE cũ còn tồn tại, vẫn có đường xóa; phải phối hợp migration/đường ghi để không có cửa sổ nguy hiểm.
- Trước khi thay FK, rà soát ứng dụng còn gọi `DELETE customer` và chuyển đúng command đóng tài khoản/xử lý PII.
- Nếu dữ liệu đã bị xóa nhầm, thay FK **không khôi phục** những row mất; cần quy trình phục hồi từ nguồn thích hợp và đối chiếu dữ liệu mới phát sinh.

## 18. Xóa xuyên dịch vụ: cần workflow, idempotency và đối soát

Xử lý hồ sơ khách thường liên quan nhiều owner: Customer Identity, Rental, Payment, Search, Analytics, Backup.

Một workflow có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `REQUESTED` | Nhận yêu cầu từ actor, chưa kết luận phạm vi. |
| `VERIFIED` | Quyền yêu cầu đã được xác minh. |
| `SCOPED` | Dữ liệu cần xóa/giảm thiểu và phần được giữ có căn cứ đã được phân loại. |
| `IN_PROGRESS` | Các owner xử lý từng phần. |
| `WAITING_DEPENDENCY` | Một nguồn hoặc bản sao chưa xác nhận, hoặc đang đợi điều kiện giữ. |
| `NEEDS_REVIEW` | Mâu thuẫn giữa quyền dữ liệu và nghĩa vụ lưu, hoặc dữ liệu chưa đủ chứng cứ. |
| `COMPLETED` | Mọi bước **trong phạm vi đã xác nhận** được kiểm chứng hoặc có ngoại lệ hợp lệ. |

~~~mermaid
flowchart TD
    A["Close / Erasure request"] --> B["Xác minh quyền, chính sách và phạm vi"]
    B --> C{"Có chứng từ cần giữ hợp lệ?"}
    C -->|Có| D["Giữ lịch sử tối thiểu, giảm PII"]
    C -->|Không| E["Purge theo policy"]
    D --> F["Gửi lệnh từng data owner"]
    E --> F
    F --> G["Customer Identity"]
    F --> H["Search / Analytics / Cache"]
    F --> I["Backup / Archive policy"]
    G --> J["Đối soát, ghi outcome"]
    H --> J
    I --> J
    J --> K{"Đã kiểm chứng đủ phạm vi?"}
    K -->|Chưa| L["Retry / Needs review"]
    K -->|Có| M["Complete có phạm vi rõ"]
~~~

Không đánh dấu `COMPLETED` chỉ vì câu DELETE ở primary trả 1 row. Cần biết các bản sao có dữ liệu cần xử lý, điều kiện retention của backup và cách ngăn phục hồi dữ liệu đã xử lý xóa.

### Outbox/inbox và tombstone

Owner có thể ghi thay đổi hồ sơ cùng `outbox` trong một local transaction rồi phát event có ID, aggregate version và scope, tránh đưa PII gốc vào payload:

~~~json
{
  "event_id": "2d918b53-930b-49fa-b5e5-8f37db2f9261",
  "event_type": "CustomerPrivateProfileErased",
  "schema_version": 1,
  "tenant_id": "00000000-0000-4000-8000-000000000001",
  "customer_id": "11111111-1111-4111-8111-111111111111",
  "aggregate_version": 24,
  "payload": {
    "scope": "PRIVATE_PROFILE",
    "contact_fields_erased": true
  }
}
~~~

Consumer nên chống lặp theo `event_id`, so phiên bản để sự kiện v23 đến muộn **không hồi sinh email** đã xóa ở v24, và ghi nhận outcome có thể kiểm chứng. Khi rebuild projection hoặc replay, phải áp tombstone/erasure policy. Outbox không đảm bảo exactly-once end-to-end; consumer vẫn cần idempotency.

## 19. Warehouse, SCD2 và báo cáo có thể “mất lịch sử” dù fact chưa bị xóa

Trong phân tích, có thể vẫn còn `fact_order` nhưng truy vấn sai lại loại nó:

~~~sql
-- Anti-pattern: thống kê lịch sử chỉ tính khách đang active hiện tại.
SELECT f.month_key, SUM(f.booked_minor)
FROM analytics_fact_order f
JOIN analytics_dim_customer d
  ON d.customer_sk = f.customer_sk
WHERE d.is_active = TRUE
GROUP BY f.month_key;
~~~

Nếu khách đóng tài khoản, fact của họ sẽ **biến khỏi kết quả** dù vẫn có trong kho dữ liệu. Truy vấn này chỉ phù hợp khi câu hỏi thật sự là “doanh số lịch sử của nhóm khách hiện active”, không phù hợp cho “tổng doanh số đã đặt trong kỳ”.

Với SCD Type 2, nhiều hàng phiên bản Customer có thể chứa PII. Xử lý PII ở bản hiện hành **không đồng nghĩa** đã xử lý các phiên bản lịch sử. Các cách bảo vệ gồm:

- Giữ fact ở grain transaction trong phạm vi retention được phép.
- Định nghĩa dimension `ERASED/UNKNOWN` hoặc nullable reference với semantic contract rõ; không gộp hai khách khác nhau thành một khách thật.
- Giảm/loại trường PII khỏi các phiên bản và read model theo policy.
- Tránh `ON DELETE CASCADE` từ dim sang fact chứa chứng từ hợp lệ.
- Đối soát kết quả tổng hợp trước/sau theo currency, tenant, business time và cùng định nghĩa KPI.

Một surrogate key hoặc hash định danh vẫn có thể liên kết tới cá nhân; phải quản trị nó đúng mức.

## 20. Document, graph, event và time-series cũng gặp lỗi xóa lan

| Mô hình | Lỗi điển hình | Điều chỉnh thiết kế |
| --- | --- | --- |
| **Quan hệ** | FK `CASCADE` xóa Order/Payment khi xóa Customer. | Phân biệt ownership/lifecycle; RESTRICT/tách PII. |
| **Document** | Nhúng hóa đơn đã chốt trong Customer document rồi xóa toàn document. | Tách aggregate và bằng chứng có retention riêng. |
| **Graph** | Xóa Customer node kéo theo edge chứng minh giao dịch/quan hệ. | Đặt owner cho node/edge, lưu lịch sử có thời gian hiệu lực. |
| **Event store** | Xóa toàn event stream để “đóng tài khoản”, mất khả năng replay. | Tách PII, retention cho sự kiện và correction/redaction theo policy. |
| **Time-series** | Xóa Sensor metadata kéo theo measurements cần điều tra sự cố. | Tách metadata hiện tại khỏi sự kiện đo/lịch sử. |
| **Warehouse** | Xóa dimension hoặc INNER JOIN active làm mất fact cũ. | Giữ history fact hợp lệ, xử lý key/PII riêng. |
| **Cache/search** | Không áp sự kiện xóa nên PII vẫn hiện. | Tombstone/version, idempotency, đối soát. |

Ở graph, thao tác như `DETACH DELETE` có thể xóa các cạnh gắn với node, nhưng nhiều cạnh thể hiện **sự việc có ý nghĩa lịch sử**. Ở document, nhúng `cart_items` trong `draft_cart` có thể phù hợp vì cùng vòng đời; nhúng toàn bộ hóa đơn đã thanh toán dưới `customer_profile` thường tạo phụ thuộc xóa không mong muốn.

## 21. Purge theo partition, retention và backup không được áp máy móc

Xóa theo thời gian có thể dùng batch hoặc drop partition, nhưng không được suy rằng mọi dữ liệu tạo cùng ngày có cùng điều kiện xóa.

| Công cụ | Lợi ích | Rủi ro |
| --- | --- | --- |
| DELETE theo tenant/ID | Phạm vi rõ khi filter đúng. | Cascade, lock, WAL và cạnh tranh ghi. |
| Purge theo mốc retention | Tự động hóa vòng đời. | Mốc bắt đầu retention sai, legal hold chưa xử lý. |
| Drop partition cũ | Hiệu quả khi dữ liệu cùng policy. | Xóa nhầm record còn tranh chấp/đến trễ/cần điều chỉnh. |
| Xóa archive/backup | Giảm dữ liệu còn giữ. | Mất khả năng recovery hoặc không đáp ứng chính sách backup. |
| Xóa projection | Giảm dữ liệu dẫn xuất. | Replay nguồn cũ có thể sinh lại trường bị xóa. |

Phải đo số hàng, dung lượng, lock, WAL, replica lag và thời gian phục hồi. Một job purge không có tenant scope hay checkpoint có thể gây lỗi diện rộng.

**Backup bất biến:** có thể không hỗ trợ xóa một row ngay; cần policy thời hạn lưu, giới hạn truy cập, runbook restore và cơ chế **không phát lại dữ liệu đã xử lý xóa vào hệ sống**. Không báo “mọi bản sao đã được xóa” nếu khả năng kiểm chứng chưa có.

## 22. Kiểm thử trước/sau: bản ghi cần giữ không được biến mất

Tạo golden fixture cho `CUS-42`: 3 hợp đồng đã ký, 7 dòng thuê, 5 payment movements confirmed và một giỏ nháp 2 dòng.

| Thời điểm | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Trước | Đếm FK cascade, ORM remove, trigger và cleanup job. | Không có đường xóa chứng từ ngoài policy. |
| Trước | Chụp tập rental IDs, movement IDs, tổng theo currency. | Có baseline có thể đối chiếu. |
| Trong | Thực hiện close/erase profile theo quyền đã xác minh. | Không gọi DELETE RentalContract/PaymentMovement. |
| Trong | Retry cùng request và tiếp nhận event cũ. | Không xóa thêm/hồi sinh PII. |
| Sau | Đếm hợp đồng, dòng thuê và movement cần giữ. | Cùng số và business keys. |
| Sau | Kiểm tra nguồn profile và downstream. | PII được xử lý theo scope; chưa xong thì báo trạng thái rõ. |
| Sau | So tổng CAPTURE/REFUND theo currency/provider reference. | Không thay đổi do đóng tài khoản. |
| Sau | So dashboard lịch sử trên cùng grain. | Không giảm số liệu vì JOIN/active filter sai. |
| Sau | Kiểm tra restore/replay policy. | Không phục hồi trái phép dữ liệu đã xử lý. |

Ví dụ đối soát:

~~~sql
-- Số hợp đồng còn được phép giữ sau khi xử lý profile.
SELECT COUNT(*) AS contracts_count
FROM demo_safe.rental_contract
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;

-- Tổng movement đã xác nhận theo currency và loại.
SELECT p.currency_code, p.movement_type,
       COUNT(*) AS movements_count,
       SUM(p.amount_minor) AS amount_minor
FROM demo_safe.payment_movement p
JOIN demo_safe.rental_contract c
  ON c.tenant_id = p.tenant_id
 AND c.rental_id = p.rental_id
WHERE c.tenant_id = :tenant_id
  AND c.customer_id = :customer_id
GROUP BY p.currency_code, p.movement_type;

-- Chỉ kiểm chứng bảng private profile trong database này.
SELECT COUNT(*) AS private_profiles_remaining
FROM demo_safe.customer_private_profile
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;
~~~

`private_profiles_remaining = 0` **không** chứng minh đã xử lý toàn bộ bản sao. Kết quả xóa phải đối soát với scope đã phê duyệt và owner liên quan.

### Một lỗi FK có thể là kết quả đúng

Trong môi trường test có RentalContract còn tham chiếu, lệnh:

~~~sql
DELETE FROM demo_safe.customer_subject
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id;
~~~

**phải bị từ chối** bởi `RESTRICT` nếu phạm vi dữ liệu như giả định. Đó là **thành công của guardrail**: API cần hướng người vận hành tới thao tác đóng tài khoản/xóa profile đúng policy, không “sửa lỗi” bằng cách đổi FK về CASCADE.

## 23. Khi thực sự phải xóa vật lý: không biến giữ lịch sử thành giữ vô hạn

Các trường hợp có thể cần physical delete:

1. Dữ liệu nháp hết hạn không có nghĩa vụ độc lập.
2. Dữ liệu cá nhân không còn mục đích xử lý hoặc phải xóa theo chính sách đã phê duyệt.
3. Dữ liệu dẫn xuất đã trở nên không cần thiết.
4. Dữ liệu giao dịch/chứng từ hết retention và không có legal hold.
5. Bản ghi sai được xác minh không phải sự kiện nghiệp vụ thật, với quy trình xử lý và audit phù hợp.

Vẫn phải phân biệt:

- **Correction** của dữ kiện đã xảy ra và việc xóa một record chưa từng là sự thật.
- **Hủy giao dịch** với xóa hợp đồng/receipt khỏi lịch sử.
- Xóa hồ sơ gốc với **xóa bản sao** hay kết thúc khả năng tái định danh.
- Phục hồi dữ liệu bị xóa nhầm với **tái xuất hiện dữ liệu đã được xóa hợp lệ**.

Không dùng `RESTRICT` làm lý do từ chối mọi yêu cầu xóa cá nhân. Nếu retention không cho phép giữ, mô hình phải có cách xử lý dữ liệu phù hợp, kể cả việc tách liên kết/giảm dữ liệu hoặc purge khi đủ điều kiện.

## 24. Bài tập thực hành: đóng tài khoản khách mua vé nhưng giữ chứng từ

**Bối cảnh:** nền tảng bán vé có `Customer`, `Booking`, `BookingLine`, `PaymentMovement` và `DraftCart`. Một khách có hai booking đã xác nhận, bốn dòng vé, ba movement provider-confirmed và một giỏ nháp hết hạn. FK từ Customer → Booking → BookingLine/PaymentMovement hiện dùng `ON DELETE CASCADE`. Customer Identity nhận yêu cầu xóa email/số điện thoại và đóng tài khoản. Finance cần tiếp tục đối soát movement trong phạm vi retention đã phê duyệt.

### Nhiệm vụ

1. Vẽ toàn bộ đồ thị FK, chỉ rõ các cạnh cascade dẫn tới mất chứng từ và số bản ghi có nguy cơ mất.
2. Định nghĩa grain, business key, owner và vòng đời cho Booking, BookingLine, PaymentMovement và DraftCart.
3. Phân biệt `CloseCustomerAccount`, `CancelBooking`, `EraseCustomerPrivateProfile` và `PurgeExpiredCart`.
4. Viết DDL phản ví dụ với `CASCADE` sai; viết DDL đích bảo vệ chứng từ bằng `RESTRICT` hoặc giải pháp thích hợp.
5. Giải thích khi nào có thể dùng `SET NULL`, khi nào phải giữ chủ thể/định danh tối thiểu và vì sao vẫn có rủi ro PII.
6. Xác định mọi đường xóa từ DB FK, Hibernate `CascadeType.ALL`/`orphanRemoval`, trigger và cleanup job.
7. Lập migration plan đổi FK và API trong cùng cửa sổ kiểm soát; tránh thời điểm CASCADE cũ còn tác dụng.
8. Viết SQL đếm Booking, BookingLine, PaymentMovement trước/sau; xác nhận không giảm lịch sử hợp lệ.
9. Với capture 500.000 VND và refund 100.000 VND, giải thích hai movement được giữ và công thức net cash.
10. Thiết kế workflow xóa PII đa dịch vụ với outbox, tombstone, idempotency, trạng thái chờ và đối soát.
11. Giải thích vì sao warehouse INNER JOIN Booking → Customer active có thể làm doanh số quá khứ biến mất.
12. Lập retention matrix cho booking có tranh chấp, booking hết thời hạn giữ, giỏ nháp và backup immutable.
13. Diễn tập thất bại: dịch vụ Customer xóa profile thành công nhưng Search không nhận event; xử lý retry thế nào?
14. Viết ADR nêu quyết định, phương án bị loại, bất biến, giới hạn quyền dữ liệu, kiểm thử và tiêu chí đánh giá lại.

### Tự kiểm chứng

| Tiêu chí | Kết quả đạt |
| --- | --- |
| **Phân loại lifecycle** | FK tham chiếu không bị hiểu thành quyền xóa lan truyền. |
| **Bảo vệ lịch sử** | Booking/Movement được giữ khi còn căn cứ; không xóa do tài khoản đóng. |
| **Thanh toán đúng** | Không xóa capture/refund hoặc biến request thành confirmed. |
| **PII đúng scope** | Nêu rõ dữ liệu cá nhân nào được xử lý, ở đâu, theo policy nào. |
| **Ràng buộc** | PK/FK giữ tenant scope và chặn thao tác xóa sai. |
| **Vận hành** | Kiểm tra ORM, trigger, job, replication, backup, outbox/replay. |
| **Đối soát** | Business keys, count, currency total và số liệu dashboard không bị nhân/mất. |
| **Khôi phục** | Có runbook cho xóa nhầm và chống tái sinh dữ liệu xóa hợp lệ. |

**Kết luận:** `ON DELETE CASCADE` không sai tự thân; nó sai khi bị áp cho **chứng từ hoặc sự kiện có vòng đời độc lập với tài khoản cha**. Thiết kế đúng phải xuất phát từ grain, nguồn có thẩm quyền, ý nghĩa nghiệp vụ, lịch sử cần lưu và chính sách dữ liệu cá nhân. Có thể cascade những bản nháp thật sự cùng vòng đời; bảo vệ hợp đồng/movement đã xác nhận bằng ràng buộc và command đúng nghĩa; xử lý PII riêng theo phạm vi có kiểm chứng. Khi đã có đồ thị xóa, golden fixtures và đối soát nhiều nguồn, hệ thống mới tránh được việc “xóa một khách” nhưng vô tình xóa luôn sự thật đã xảy ra.
