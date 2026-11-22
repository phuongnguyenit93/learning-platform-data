# Quản lý migration bằng phiên bản và lịch sử thực thi

Ứng dụng Java cần thay đổi theo nghiệp vụ: thêm cột, tạo chỉ mục, bổ sung ràng buộc, chuẩn hóa dữ liệu cũ hoặc đổi cấu trúc một bảng mà nhiều phiên bản ứng dụng vẫn đang sử dụng. Nếu kỹ sư sửa schema trực tiếp qua SQL console, sau vài lần triển khai sẽ xuất hiện những khác biệt khó truy vết giữa development, staging và production.

**Database migration** là phương pháp quản lý thay đổi cơ sở dữ liệu thành **các bước có phiên bản, nội dung được lưu cùng mã nguồn và lịch sử thực thi trên từng database**. Công cụ như **Flyway** hoặc **Liquibase** giúp biết migration nào đã chạy, còn bước nào chưa chạy, có tệp đã áp dụng nào bị sửa đổi và khi nào nên dừng rollout.

Bài học thuộc chương **Tiến hóa dữ liệu** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, liên hệ quản lý schema với ranh giới persistence trong Java: SQL, JDBC, giao dịch, khả năng tương thích trong rolling deployment, tính bền vững, bảo mật và hiệu năng. Ví dụ dùng PostgreSQL, Java, Spring Boot và quy ước migration thường gặp ở Flyway; tên bảng metadata, khả năng rollback và cơ chế giao dịch cần được xác minh theo phiên bản công cụ và DBMS.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **migration file**, **version**, **checksum**, **schema history** và schema thực tế.
2. Giải thích cách công cụ xác định migration đã áp dụng, còn thiếu hoặc không hợp lệ.
3. Thiết kế phiên bản và thứ tự thay đổi, giải quyết xung đột khi nhiều branch phát triển đồng thời.
4. Tạo migration **schema**, **data** và **repeatable** phù hợp.
5. Hiểu cách dùng Flyway/Liquibase với Java/Spring Boot và database đã tồn tại.
6. Xử lý failure, schema drift, DDL không hỗ trợ transaction và migration chạy trên nhiều instance.
7. Áp dụng **expand → migrate → contract**, backfill theo lô, rollback có kế hoạch và kiểm tra dữ liệu.
8. Xây dựng pipeline CI/CD, observability và quy trình khôi phục khi schema thay đổi không thành công.

## 2. Vì sao schema cần được quản lý theo lịch sử?

Giả sử bảng khách hàng ban đầu chỉ có hai cột:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);
~~~

Tháng sau cần thêm **display_name**, sau đó tạo index và chuyển các bản ghi cũ. Khi chỉ lưu một file **schema.sql** biểu diễn trạng thái cuối cùng, ta chưa biết:

- Production đã chạy đến bước nào?
- Staging có thiếu một constraint hay index không?
- Ai chạy ALTER TABLE trực tiếp trên production và khi nào?
- Có migration nào chạy dở dang sau sự cố?
- Dữ liệu cũ đã được chuyển đổi đầy đủ chưa?
- Có thể rollback phiên bản ứng dụng mà không phá tương thích với schema hiện tại không?

Migration giải quyết bài toán **tiến hóa có thể kiểm soát**, không chỉ bài toán tạo schema từ đầu. Thay vì hỏi “bảng cần trông như thế nào?”, nhóm còn trả lời “**bảng đã tiến hóa bằng những bước nào và môi trường nào đã thực hiện bước nào?**”.

### 2.1. Các loại thay đổi

| Nhóm thay đổi | Ví dụ | Rủi ro cần quản lý |
|---|---|---|
| Schema | CREATE TABLE, ADD COLUMN, DROP COLUMN | Lock, mất tương thích, schema rewrite |
| Constraint | NOT NULL, UNIQUE, FOREIGN KEY, CHECK | Dữ liệu cũ không đạt điều kiện |
| Index | CREATE INDEX, DROP INDEX | I/O, tài nguyên, thời gian chờ và tác động tới ghi |
| Data | Chuẩn hóa giá trị, backfill cột mới | Lượng bản ghi lớn, transaction dài, ghi đè cập nhật mới |
| Stored object | VIEW, FUNCTION, TRIGGER | Thứ tự phụ thuộc, cập nhật logic |
| Reference data | Mã trạng thái, loại dịch vụ | Dữ liệu trùng, môi trường khác nhau |
| Partition | Tạo partition mới, chuyển dữ liệu cũ | Routing, retention, khóa và hiệu năng |

Migration tốt có **tiền điều kiện, tác động được hiểu rõ và cơ chế xác minh**. Không nên coi migration chỉ là một tập các lệnh ALTER TABLE được chạy tự động.

## 3. Version, checksum và bảng lịch sử

Một cấu trúc migration file theo quy ước Flyway thường gặp:

~~~text
db/migration/
    V1__create_customers.sql
    V2__create_orders.sql
    V3__add_customer_display_name.sql
    V4__add_orders_status_index.sql
    R__order_summary_view.sql
~~~

Trong ví dụ:

- **V** đại diện cho **versioned migration**: một bước có version xác định, thường chỉ được ghi nhận áp dụng thành công một lần trên một DB đã được quản lý.
- Số **1, 2, 3, 4** xác định thứ tự logic.
- **__** phân cách version và phần mô tả theo quy tắc đặt tên thông dụng.
- **R** đại diện cho **repeatable migration**: một số đối tượng như view hoặc function có thể được áp dụng lại khi nội dung thay đổi theo cơ chế checksum.
- **Checksum** là dấu vết từ nội dung migration được công cụ ghi vào lịch sử và kiểm tra vào những lần chạy sau.

**Quy tắc quan trọng:** khi V2 đã chạy trên production, không mở V2 sửa thêm SQL như thể đó là version mới. Hãy tạo **V5__...sql**; nếu sửa nội dung đã áp dụng, công cụ có thể phát hiện checksum mismatch và yêu cầu điều tra.

### 3.1. Bảng history chứa gì?

Flyway thường dùng bảng mặc định **flyway_schema_history**, còn Liquibase thường dùng **DATABASECHANGELOG** và **DATABASECHANGELOGLOCK**. Chúng có cơ chế metadata khác nhau, không nên trộn lẫn.

Một bản ghi lịch sử có thể chứa:

| Thông tin | Ý nghĩa |
|---|---|
| Thứ tự thực thi | Migration nào đã được ghi nhận trước/sau |
| Version hoặc changeset identity | Danh tính duy nhất của thay đổi |
| Description, script/file | Đường nguồn migration |
| Checksum | Dấu vết nội dung tại thời điểm áp dụng |
| Người chạy hoặc chủ thể chạy | Tài khoản/CI job có liên quan |
| Thời điểm, thời lượng | Giúp kiểm tra và phát hiện migration bất thường |
| Trạng thái thành công/thất bại | Dùng để xác định trạng thái của lần triển khai |

**Bảng lịch sử không phải bản sao lưu dữ liệu.** Nó không chứa dữ liệu bị xóa bởi DROP TABLE và không tự sửa được schema drift do các thay đổi thủ công ngoài công cụ.

### 3.2. Version schema không phải version Java artifact

Ứng dụng Java release **2.7.1** không nhất thiết dùng migration **V2.7.1**. Release có thể yêu cầu schema tối thiểu ở V13, trong khi một hotfix Java không cần migration nào. Tính tương thích phải được xác định theo **schema mà binary đọc/ghi được**, nhất là khi rolling deployment còn các instance cũ.

## 4. Công cụ biết migration nào cần chạy như thế nào?

Một vòng chạy khái quát:

~~~mermaid
flowchart TD
    A["Nạp tập migration có trong artifact"] --> B["Kết nối DB và lấy quyền điều phối"]
    B --> C["Đọc lịch sử migration"]
    C --> D{"Version/checksum/thứ tự hợp lệ?"}
    D -->|Không| E["Dừng, yêu cầu điều tra"]
    D -->|Có| F["Xác định migration chưa áp dụng"]
    F --> G{"Còn bước mới?"}
    G -->|Có| H["Thực thi SQL hoặc changeset"]
    H --> I{"Thành công?"}
    I -->|Có| J["Ghi metadata lịch sử"]
    I -->|Không| K["Rollback hoặc ghi nhận lỗi theo DB/tool"]
    J --> G
    K --> E
    G -->|Không| L["Hoàn tất, giải phóng quyền điều phối"]
~~~

Mô hình này chỉ thể hiện các giai đoạn logic. Các công cụ thường điều phối để hai executor không áp dụng cùng một migration lên một database cùng lúc, nhưng cách khóa và ghi lịch sử thay đổi theo DB/tool. Không phải mọi câu DDL có thể thực thi trong một transaction.

Ở lần triển khai tiếp theo, công cụ dựa vào history và tập migration hiện tại để xác định bước còn thiếu. **Không cần chạy lại toàn bộ V1..Vn mỗi lần deploy.** Đối với repeatable migration, cơ chế chạy lại dựa trên thay đổi nội dung và chính sách công cụ.

### 4.1. IF NOT EXISTS có thay thế history không?

Không. Ví dụ **ADD COLUMN IF NOT EXISTS** có thể tránh lỗi nếu cột đã tồn tại, nhưng không cho biết:

- Kiểu cột hoặc default có đúng không?
- Ràng buộc đã được thêm đủ chưa?
- Cột được tạo từ migration nào?
- Một người đã sửa metadata hoặc schema ngoài pipeline hay chưa?
- Có dữ liệu cũ còn cần backfill không?

Idempotency SQL có ích trong một số tình huống nhưng **không thay thế version, checksum, lịch sử và kiểm thử schema**.

## 5. Thực hành versioned migration trên PostgreSQL

Giả sử ứng dụng quản lý khách hàng và đơn hàng.

### 5.1. V1 — tạo customers

Nội dung file **V1__create_customers.sql**:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 5.2. V2 — tạo orders

Nội dung file **V2__create_orders.sql**:

~~~sql
CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    status VARCHAR(24) NOT NULL DEFAULT 'CREATED',
    total_amount NUMERIC(14, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

V2 phụ thuộc V1 vì khóa ngoại tham chiếu bảng customers. Thứ tự version là một phần của tính đúng; tên file hợp lệ nhưng thứ tự dependency sai vẫn gây lỗi.

### 5.3. V3 — thêm display_name theo kiểu mở rộng

Nội dung **V3__add_customer_display_name.sql**:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(200);
~~~

Cột mới **cho phép NULL** để bản ứng dụng cũ vẫn có thể tạo khách hàng với full_name mà không bị chặn. Đây là thay đổi **expand**, chưa phải công đoạn chuyển toàn bộ dữ liệu hoặc xóa cột cũ.

### 5.4. V4 — index cho truy vấn đơn hàng

Nội dung ví dụ **V4__add_orders_status_index.sql**:

~~~sql
CREATE INDEX orders_status_created_idx
    ON orders (status, created_at);
~~~

Câu này có thể chặn ghi trên bảng lớn trong quá trình tạo index; trước khi dùng production cần xem lựa chọn tạo index đồng thời và mức khóa phù hợp với PostgreSQL/phiên bản công cụ. Việc có migration không làm câu SQL tự hết tốn tài nguyên.

### 5.5. Repeatable — view có thể tái định nghĩa

Nội dung **R__order_summary_view.sql**:

~~~sql
CREATE OR REPLACE VIEW order_summary AS
SELECT
    o.id AS order_id,
    o.customer_id,
    c.full_name,
    o.status,
    o.total_amount
FROM orders o
JOIN customers c ON c.id = o.customer_id;
~~~

Repeatable migration có thể được thực thi lại khi checksum thay đổi. Thích hợp với một số view/function, nhưng **không dùng như lệnh backfill hàng loạt có side effect mỗi lần chạy lại**. Nếu về sau xóa full_name, phải đổi view và kiểm tra dependency theo thứ tự triển khai trước.

## 6. Quản lý lịch sử giữa các môi trường

~~~text
Repository:     V1 -> V2 -> V3 -> V4 -> V5
Development:    V1 -> V2 -> V3 -> V4 -> V5
Staging:        V1 -> V2 -> V3 -> V4
Production:     V1 -> V2 -> V3
~~~

Production chưa có V4/V5 dù build artifact chứa chúng. Công cụ chỉ dựa trên **lịch sử của chính database đang kết nối** để xác định bước nào pending. Đây là lý do cần bảo đảm URL/database được chọn chính xác.

### 6.1. Version conflict khi nhiều nhánh phát triển

Branch A tạo **V8__add_index.sql**, branch B tạo **V8__add_column.sql**. Nếu merge mà cả hai vẫn là V8, lịch sử không thể có hai thay đổi với cùng version theo chính sách thông dụng.

Giải quyết **trước khi phát hành**, thống nhất lại version và thứ tự. Nếu V8 đã chạy ở môi trường dùng chung, không tự ý đổi tên hoặc sửa nội dung lịch sử; cần đánh giá trạng thái đã áp dụng và tạo thay đổi tiếp theo thích hợp.

Timestamp version giảm một số xung đột nhưng không đảm bảo thứ tự dependency đúng. Một migration tạo foreign key vẫn phải đến sau migration tạo bảng được tham chiếu.

### 6.2. Không được tự sửa file đã áp dụng

Một hành động phổ biến nhưng sai:

1. V2 tạo bảng orders đã chạy production.
2. Developer sửa chính V2 để thêm một index.
3. Tool phát hiện checksum mismatch.
4. Developer sửa trực tiếp checksum ở history để cho deploy chạy.

Bước 4 che dấu khác biệt giữa mã nguồn và database. Cách đúng thông thường là **khôi phục file V2 nguyên gốc**, tạo migration mới để thêm index, và xác minh history của mọi môi trường.

## 7. Checksum, validate, repair và schema drift

**Checksum** giúp nhận ra nội dung migration đã áp dụng bị sửa trong source. Nó **không chứng minh toàn bộ schema thực tế giống thiết kế mong muốn**.

**Schema drift** xảy ra khi đối tượng trong DB khác với trạng thái mà migration quản lý, ví dụ:

- Kỹ sư tạo index thủ công ở production.
- Một cột bị đổi kiểu trực tiếp trên SQL console.
- Một bản restore lấy từ mốc khác artifact.
- Một tool ngoài pipeline xóa trigger hoặc constraint.
- Một migration được chạy bằng tay nhưng history chưa ghi.

Khi phát hiện drift hoặc checksum mismatch:

1. Dừng bước rollout có thể phá dữ liệu.
2. Đọc history và xác minh schema thực tế (cột/index/constraint).
3. Xác định ai thực hiện thay đổi, từ nguồn nào và đã tác động tới dữ liệu nào.
4. Tạo **migration mới hoặc kế hoạch phục hồi** có review, thay vì sửa history tùy ý.
5. Chỉ dùng tính năng **repair metadata** sau khi hiểu rõ trường hợp được hỗ trợ của công cụ.
6. Kiểm tra lại staging, validation và integration test trước khi tiếp tục.

**Repair không tự khôi phục cột bị DROP hoặc dữ liệu bị xóa**. Nó là một thao tác lên metadata lịch sử trong những tình huống công cụ hỗ trợ, không phải lệnh thần kỳ khiến database tự trở về đúng schema.

### 7.1. Kiểm tra schema thực tế trong PostgreSQL

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customers'
ORDER BY ordinal_position;
~~~

Kiểm tra index:

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'orders';
~~~

Đây chỉ là các truy vấn hỗ trợ chẩn đoán; một schema diff toàn diện còn phải đối chiếu nhiều đối tượng khác và cấu hình liên quan.

## 8. Flyway và Liquibase khác nhau thế nào?

| Nội dung | Flyway | Liquibase |
|---|---|---|
| Đơn vị công việc phổ biến | Versioned/repeatable migrations | Changelog với changeset |
| Định danh | Version, filename và metadata theo tool | Thường gồm **id + author + file path** |
| Lịch sử | Thường là **flyway_schema_history** | Thường là **DATABASECHANGELOG** |
| Khóa điều phối | Cơ chế riêng theo DB/tool | Thường là **DATABASECHANGELOGLOCK** |
| Nội dung migration | SQL và các kiểu migration được hỗ trợ | Changelog XML/YAML/JSON/SQL cùng changes |
| Kiểm tra nội dung | Checksum và validate theo policy | Checksum và policy từng changeset |
| Rollback | Phụ thuộc edition, DBMS và chiến lược | Một số change có rollback khai báo, không phải mọi bước đều đảo ngược an toàn |

Một changeset Liquibase minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: add-customer-display-name
      author: platform-team
      changes:
        - addColumn:
            tableName: customers
            columns:
              - column:
                  name: display_name
                  type: varchar(200)
~~~

Đây là ví dụ cú pháp, không phải file cấu hình đang được sửa trong tác vụ. Cần kiểm tra bản Liquibase, changelog cha, schema và kết nối thực tế.

Không dùng cùng lúc Flyway và Liquibase để tùy ý điều khiển **cùng một schema** mà thiếu ranh giới rõ: hai bảng lịch sử riêng có thể không biết các bước do công cụ kia thực hiện.

## 9. Tích hợp Flyway vào Java/Spring Boot

Một dự án Spring Boot sử dụng JDBC có thể để migration trong **classpath:db/migration**.

Ví dụ dependency Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.flywaydb:flyway-database-postgresql")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

Đây là ví dụ, các module cần tương thích với phiên bản Spring Boot và Flyway của dự án. Một số bản Flyway mới có module riêng hỗ trợ PostgreSQL; cần xác minh cách quản lý phiên bản dependency.

Ví dụ Spring application YAML:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/training
    username: REPLACE_WITH_DB_USER_SECRET
    password: REPLACE_WITH_DB_PASSWORD_SECRET
  flyway:
    enabled: true
    locations: classpath:db/migration
    validate-on-migrate: true
~~~

Những chuỗi **REPLACE_WITH_...** là placeholder minh họa, **không dùng nguyên văn ở production**. Dữ liệu đăng nhập phải lấy từ cấu hình/secret store phù hợp và không log mật khẩu. Tài khoản migration có thể cần quyền CREATE/ALTER khác với tài khoản runtime chỉ thực thi DML.

### 9.1. Migration khi startup hay job riêng?

**Startup migration:** cấu hình đơn giản, thường phù hợp dự án nhỏ. Nhưng khi nhiều instance khởi động cùng lúc, chúng có thể tranh chấp lock và timeout nếu migration chậm.

**Job migration riêng:** một bước CI/CD hoặc deploy job được điều phối chạy trước khi bật tính năng đòi schema mới. Ưu điểm là phân tách quyền DDL, log/approval, thời gian chạy và kiểm soát lỗi. Đổi lại cần phối hợp chính xác với lịch deploy ứng dụng.

Hai mô hình đều phải bảo đảm không cho code mới dùng cột chưa tồn tại, và migration phá tương thích không chạy trước khi các binary cũ đã được gỡ khỏi traffic.

## 10. Expand → migrate → contract trong rolling deployment

Một deployment thường có **App v1** và **App v2** chạy cùng lúc trên cùng DB. Nếu App v1 còn đọc **customers.full_name**, lệnh DROP COLUMN full_name sẽ khiến App v1 lỗi ngay.

~~~text
T0: App v1 đọc/ghi full_name
T1: Migration EXPAND thêm display_name nullable
T2: App v1 và v2 chạy đồng thời
T3: Điều phối đường ghi, backfill dữ liệu cũ
T4: Đảm bảo mọi app/job/report đã dùng display_name
T5: Migration CONTRACT thêm ràng buộc, bỏ full_name
~~~

### 10.1. Expand: thêm mà chưa phá bỏ

~~~sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(200);
~~~

Cột mới nullable để writer cũ chưa bị lỗi. App mới có thể tạm thời đọc:

~~~sql
SELECT id, COALESCE(display_name, full_name) AS shown_name
FROM customers
WHERE id = ?;
~~~

**Cẩn thận:** nếu v1 vẫn cập nhật full_name trong khi display_name đã tồn tại, coalesce có thể đọc giá trị display_name cũ. Cần một chiến lược chuyển đổi writer, dual-write, trigger hoặc đồng bộ hợp lệ theo nghiệp vụ. Không chỉ thêm coalesce rồi tuyên bố đã tương thích mọi tình huống.

### 10.2. Migrate: backfill dữ liệu và đổi đường ghi

Khi đã có cơ chế bảo đảm các thay đổi mới không bị ghi đè, backfill từng dải ID:

~~~sql
UPDATE customers
SET display_name = full_name
WHERE id BETWEEN ? AND ?
  AND display_name IS NULL;
~~~

Hai dấu **?** dùng làm placeholder của PreparedStatement; để chạy trực tiếp trong SQL console phải có giá trị cụ thể. Điều kiện **IS NULL** giúp lần chạy sau không ghi đè các hàng đã có display_name.

Cần theo dõi số hàng chưa được chuyển:

~~~sql
SELECT COUNT(*) AS remaining
FROM customers
WHERE display_name IS NULL;
~~~

Kết quả 0 tại một thời điểm **chưa đủ** nếu các writer cũ vẫn có thể tạo hoặc sửa hàng theo cấu trúc cũ. Chỉ sau khi đã kiểm soát đầy đủ đường ghi, xác minh dữ liệu và kế hoạch lock, mới tạo migration thêm ràng buộc:

~~~sql
ALTER TABLE customers
ALTER COLUMN display_name SET NOT NULL;
~~~

Với bảng lớn, cần kiểm tra chi phí scan và lock. Một số chiến lược xác thực constraint theo giai đoạn có thể giảm tác động tùy phiên bản PostgreSQL.

### 10.3. Contract: gỡ cấu trúc legacy muộn

Chỉ khi mọi bản ứng dụng và downstream consumer đã ngừng dùng full_name, mới thực hiện:

~~~sql
ALTER TABLE customers
DROP COLUMN full_name;
~~~

Đây là **thay đổi phá tương thích**. Một binary cũ được rollback sau thời điểm này có thể không khởi động hoặc truy vấn thành công. Cần gắn quyết định contract với kế hoạch rollback và danh sách consumers thật.

**ALTER TABLE ... RENAME COLUMN** có thể nhanh về mặt DDL, nhưng cũng phá khả năng đọc cột cũ của App v1. Trong triển khai nhiều instance không downtime, expand-migrate-contract thường dễ kiểm soát hơn rename trực tiếp.

## 11. Backfill lớn cần tiến độ riêng và retry an toàn

Một migration **ADD COLUMN** chạy thành công không có nghĩa **hàng chục triệu bản ghi cũ đã được chuyển xong**. Với bảng lớn, một câu UPDATE tất cả dữ liệu trong một transaction có thể:

- Giữ lock/transaction lâu, làm tăng độ trễ truy vấn online.
- Sinh nhiều WAL và tăng replication lag.
- Gây áp lực I/O hoặc làm vùng WAL đầy.
- Khó tiếp tục từ điểm đã hoàn thành nếu tiến trình bị dừng.
- Dễ đè lên cập nhật nghiệp vụ xảy ra đồng thời nếu điều kiện UPDATE không chặt.

Nên tách **schema migration nhanh, có version** khỏi **backfill job theo batch có giới hạn và checkpoint tiến độ riêng** khi quy mô yêu cầu. Chỉ bật NOT NULL hoặc bỏ cột cũ sau khi kiểm chứng được trạng thái dữ liệu và các writer.

### 11.1. Ví dụ Java JDBC backfill một dải ID

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class CustomerBackfill {
    private final DataSource dataSource;

    public CustomerBackfill(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int fillRange(long fromInclusive, long toInclusive)
            throws SQLException {
        if (fromInclusive <= 0 || toInclusive < fromInclusive) {
            throw new IllegalArgumentException("Dải ID không hợp lệ");
        }

        String sql = """
                UPDATE customers
                SET display_name = full_name
                WHERE id BETWEEN ? AND ?
                  AND display_name IS NULL
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement stmt = connection.prepareStatement(sql)) {
            stmt.setLong(1, fromInclusive);
            stmt.setLong(2, toInclusive);
            stmt.setQueryTimeout(10);
            return stmt.executeUpdate();
        }
    }
}
~~~

Ví dụ dựa trên connection auto-commit thông thường. Production cần bảo đảm batch được commit trước khi cập nhật checkpoint tiến độ; nếu vừa cập nhật dữ liệu vừa cập nhật checkpoint trong DB, nên đặt chúng trong một transaction nhất quán khi có thể.

Batch size cần chọn theo thời gian/row, độ trễ API, WAL, lag replica và sức chứa DB. Không retry vô hạn khi DB đang quá tải. Tác dụng bên ngoài như gửi email không được chạy lặp trong mỗi batch nếu chưa có idempotency.

## 12. DDL transactional và DDL không thể rollback giống nhau

Đừng giả định mọi thay đổi schema được bọc trong một transaction chung rồi lỗi là có thể rollback nguyên vẹn.

### 12.1. PostgreSQL hỗ trợ transaction cho nhiều DDL

Ví dụ:

~~~sql
BEGIN;

ALTER TABLE customers
ADD COLUMN preferred_language VARCHAR(10);

ROLLBACK;
~~~

Vì lệnh ALTER TABLE nằm trong transaction chưa commit, rollback có thể hoàn tác thay đổi tương ứng. Nhiều lệnh CREATE TABLE/ALTER TABLE của PostgreSQL hỗ trợ cách làm này.

Tuy vậy, **không phải mọi lệnh PostgreSQL đều được phép chạy trong transaction block**, và không phải DBMS nào cũng hỗ trợ transactional DDL tương đương.

### 12.2. CREATE INDEX CONCURRENTLY cần xử lý đặc biệt

~~~sql
CREATE INDEX CONCURRENTLY orders_status_created_idx
    ON orders (status, created_at);
~~~

PostgreSQL không cho **CREATE INDEX CONCURRENTLY** chạy bên trong một transaction block. Nếu công cụ migration mặc định thực thi file trong transaction, bước này cần được khai báo/cấu hình là **non-transactional migration** theo tài liệu đúng phiên bản công cụ.

Tạo index đồng thời giúp giảm một số mức chặn ghi so với CREATE INDEX thông thường nhưng không miễn phí: vẫn dùng I/O/CPU, có thể chờ các transaction khác và có thể thất bại. Một lần thực thi lỗi có thể để lại **index invalid** cần kiểm tra/dọn có kiểm soát trước khi thử lại.

Kiểm tra index:

~~~sql
SELECT indexrelid::regclass AS index_name,
       indisvalid, indisready
FROM pg_index
WHERE indrelid = 'orders'::regclass;
~~~

Không chỉ dựa vào tên lệnh đã chạy rồi suy ra index chắc chắn dùng được.

### 12.3. DBMS khác có implicit commit

Một số lệnh DDL ở MySQL có quy tắc **implicit commit** hoặc không rollback như DDL PostgreSQL trong transaction. Nếu migration chứa ba thao tác và lỗi ở thao tác thứ ba, hai thao tác trước có thể đã lưu bền vững.

Vì vậy, khi migration thất bại, hãy hỏi:

1. Những statement nào thực sự đã chạy và commit?
2. Tool có ghi failed state, hay transaction rollback đã loại cả history record liên quan?
3. Có đối tượng tạm, constraint/index invalid hoặc dữ liệu chỉ chuyển một phần không?
4. Có thể sửa bằng migration tiếp theo, hay cần đối soát/khôi phục trước?

Không dùng một quy trình retry chung cho mọi DBMS.

## 13. Nhiều instance cùng khởi động: ai chạy migration?

Trong môi trường có 20 pod Spring Boot, tất cả có thể cùng chứa V5 và cùng phát hiện database chưa có V5. Công cụ migration thường dùng cơ chế locking/coordination để ngăn **hai executor áp dụng cùng thay đổi trên một database**. Nhưng điều đó không bảo đảm mọi pod sẽ khởi động nhanh: nếu V5 giữ khóa hoặc mất nhiều phút, các pod còn lại có thể chờ hoặc timeout.

Một phương án điều phối phù hợp cho hệ thống lớn:

~~~text
CI build và test migration
             |
             v
  Áp dụng trên staging
             |
      Review kết quả
             |
             v
 Production migration job
      (một executor có điều phối)
             |
       Success + validate?
          /       \
        Không      Có
          |         |
    Dừng rollout   Deploy application
                    |
                Health check
~~~

**Mấu chốt:** migration job chỉ được chạy bước **tương thích với các ứng dụng cũ vẫn hoạt động**. Với migration **DROP full_name**, cần đợi tất cả phiên bản ứng dụng cũ và các consumer phụ thuộc biến mất khỏi traffic.

### 13.1. Migration lock khác DDL lock

- **Migration coordination lock** bảo vệ việc nhiều executor cùng chạy một bước.
- **DDL lock** bảo vệ cấu trúc bảng khi ALTER/CREATE/DROP, có thể chặn truy vấn và transaction của ứng dụng.
- **Transaction/row lock** bảo vệ các thay đổi dữ liệu trong workload thông thường.

Có migration lock **không đồng nghĩa** câu ALTER TABLE không làm chậm production. Một DDL tưởng rất nhanh vẫn có thể phải đợi transaction đang giữ lock, rồi chặn các truy vấn đến sau trong hàng chờ khóa.

### 13.2. Spring Boot startup và quyền DDL

Có hai lựa chọn phổ biến:

- **Migration lúc khởi động ứng dụng:** đơn giản cho hệ thống ít replica; phải quản lý timeout và cùng quyền migration/runtime.
- **Migration job riêng:** pipeline cấp credential DDL cho job, runtime app dùng role DML tối thiểu. Phức tạp hơn nhưng giúp kiểm soát approval, rollback và tác động vận hành.

Không cấp quyền superuser cho mọi API pod chỉ để chúng có thể ALTER TABLE lúc startup. Credential migration cần được bảo vệ như các secret quan trọng khác.

## 14. Baseline trên database đã tồn tại

Một hệ thống mới có thể tạo database trống rồi chạy V1 → V2 → V3. Nhưng một ứng dụng đã chạy nhiều năm có thể có hàng trăm bảng, dữ liệu lớn và chưa từng dùng migration tool.

**Baseline** giúp khai báo mốc bắt đầu quản lý cho schema đã tồn tại. Nó không đồng nghĩa công cụ đã kiểm tra và tạo lại mọi bảng giống một tệp V1.

Quy trình an toàn:

1. **Backup và kiểm thử khả năng restore** trước khi thay đổi quy trình quản lý.
2. Kiểm kê tables/indexes/constraints và dữ liệu mẫu của database hiện tại.
3. Xác định trạng thái baseline đã được review và version biểu diễn trạng thái đó.
4. Ghi metadata baseline theo đúng cơ chế công cụ, không tự sửa history trực tiếp.
5. Chỉ áp dụng migration có version sau baseline vào database đã được xác nhận.
6. Kiểm thử riêng quy trình bootstrap từ database trống và nâng cấp từ database hiện tại.
7. Phân biệt rõ môi trường tạo mới và môi trường đã baseline.

**Không bật baseline tự động một cách mù quáng cho mọi database có schema không rỗng.** Nếu URL trỏ sai database hoặc schema có drift, bạn có thể đánh dấu một trạng thái sai là “đã đạt baseline” mà không hề tạo những đối tượng còn thiếu.

## 15. Migration lỗi: điều tra trước khi retry hoặc repair

Một migration lỗi có thể để lại những trạng thái khác nhau:

| Loại thất bại | Rủi ro | Cách điều tra |
|---|---|---|
| SQL syntax error | Script không thể thực thi | Xác định DDL có được rollback sạch không |
| Lock timeout | Câu lệnh chưa chạy hoặc đang chờ lock | Xem transaction blocker và trạng thái object |
| Constraint validation | Dữ liệu cũ vi phạm UNIQUE/NOT NULL | Đếm/sửa bản ghi không hợp lệ |
| DDL nontransactional bị lỗi | Schema thay đổi một phần | Kiểm kê index/constraint/table thực tế |
| Hết dung lượng/WAL | Transaction/recovery bị ảnh hưởng | Kiểm tra storage, WAL và sức khỏe DB |
| Mất kết nối quanh DDL | Không rõ server đã commit hay chưa | So history cùng schema thực tế |
| Checksum mismatch | Nội dung tệp đã áp dụng bị sửa hoặc lịch sử khác | Khôi phục version gốc, tạo migration mới khi cần |
| App mới chạy trước schema mới | Repository lỗi thiếu column/table | Dừng rollout và điều chỉnh thứ tự triển khai |

Nếu công cụ có lệnh **repair**, hiểu chính xác nó sửa **metadata** gì. Repair không xây lại bảng bị xóa, không phục hồi dữ liệu và không tự hợp thức hóa một schema sai.

Một kế hoạch sự cố cơ bản:

~~~text
Migration thất bại
       |
       v
Dừng rollout / không deploy code phụ thuộc
       |
       v
Xác minh DBMS, transaction semantics, metadata
       |
       v
Kiểm tra schema + dữ liệu thật
       |
       +--> Có thể forward-fix an toàn? -> Migration mới
       |
       +--> Cần rollback app? -> Kiểm tra schema còn tương thích
       |
       +--> Cần restore? -> Backup/PITR + đối soát
       |
       v
Validate lại + integration test + giám sát
~~~

**Không sửa trực tiếp hàng trong flyway_schema_history hoặc DATABASECHANGELOG** chỉ để đẩy pipeline qua lỗi. Hành động đó có thể tách trạng thái metadata khỏi trạng thái vật lý của database.

## 16. Rollback, forward fix và khôi phục dữ liệu

Một file migration có thể chứa:

~~~sql
ALTER TABLE customers DROP COLUMN full_name;
~~~

Sau khi cột bị xóa và thay đổi được commit, việc thêm lại cột cùng tên không khôi phục dữ liệu cũ. “Migration rollback” không tương đương “dữ liệu đã quay về đúng mốc”.

Ba hướng xử lý thường gặp:

1. **Forward fix:** tạo migration mới sửa schema/dữ liệu theo trạng thái hiện tại. Đây thường là lựa chọn thích hợp khi đã có transaction mới trên production và cần tránh mất dữ liệu.
2. **Rollback ứng dụng:** quay về binary cũ khi schema vẫn **tương thích** với binary đó. Không được dựa vào rollback app nếu cột/tên bảng cũ đã bị drop.
3. **Restore/PITR:** khôi phục từ backup và WAL tới thời điểm thích hợp nếu lỗi gây mất dữ liệu không khôi phục bằng forward fix. Phải tính đến những giao dịch hợp lệ phát sinh sau mốc restore và các side effect ngoài DB.

Một số công cụ hỗ trợ cấu hình rollback/undo cho một số loại migration, nhưng **không phải mọi thao tác đều tự động đảo ngược được**. Các bước DELETE, chuyển kiểu làm mất độ chính xác hoặc cập nhật dữ liệu sai cần chiến lược phục hồi riêng.

### 16.1. Trước khi áp dụng migration rủi ro cao

- Có backup hoặc snapshot phù hợp, xác minh được restore.
- Có mốc RPO/RTO được nghiệp vụ chấp nhận.
- Có bản sao/schema staging tương đương để thử.
- Đo lock time, rewrite time, WAL và replication lag.
- Xác định app nào cần schema cũ và đường rollback của chúng.
- Có bước dừng và điều kiện abort rõ ràng.
- Với dữ liệu nhạy cảm, log/backup và tài khoản triển khai phải được bảo vệ.

## 17. CI/CD và code review cho migration

Migration là một thay đổi production có thể ảnh hưởng dữ liệu bền vững, nên review không kém phần quan trọng so với code Java.

### 17.1. Checklist trong pull request

- Version duy nhất và đúng thứ tự dependency.
- File migration đã chạy trên môi trường chung **không bị sửa**.
- SQL dùng đúng dialect của DBMS.
- ADD COLUMN, index, constraint có tiền điều kiện về dữ liệu.
- Không phá tương thích với app cũ còn chạy.
- Tạo index/ALTER TABLE có mức lock và thời gian dự kiến phù hợp.
- Backfill lớn có batch/checkpoint/idempotency, không chiếm transaction quá lâu.
- Permission, role, schema name, secret và đường kết nối được kiểm soát.
- Có cách kiểm tra kết quả và kế hoạch recovery/rollback.
- Có integration test từ **schema production hiện tại**, không chỉ từ database trống.

### 17.2. Kiểm thử trên database trống và database nâng cấp

Hai tình huống cần test riêng:

**Bootstrap test:** tạo database mới, áp dụng đầy đủ tập migration V1..Vn và chạy integration test. Bài test này phát hiện thiếu migration hoặc dependency sai.

**Upgrade test:** restore một database ở version đang chạy production (có dữ liệu cũ đại diện), áp dụng chỉ những bước còn thiếu. Bài test phát hiện vấn đề **giá trị NULL, trùng dữ liệu, lock, độ dài index hoặc chuyển kiểu không hợp lệ** mà database trống không bộc lộ.

Một pipeline có thể chạy qua những điểm nâng cấp được hỗ trợ khác nhau nếu ứng dụng có nhiều nhánh vận hành.

### 17.3. Tránh phát hành lệnh DDL không được review

Không nên để ứng dụng tự sửa schema bằng những câu ALTER TABLE tùy tiện trong request HTTP. Nếu Hibernate hoặc ORM có tính năng tự điều chỉnh schema ở môi trường phát triển, production nên dùng quy trình migration đã quản lý và kiểm tra cấu trúc theo cấu hình phù hợp.

**Thay đổi schema phải có một nguồn điều phối rõ ràng** để tránh ORM startup, Flyway và script thủ công cùng tranh nhau ghi cấu trúc.

## 18. Nhiều shard, tenant và database

Trong kiến trúc nhiều tenant hoặc sharding, mỗi database/shard có thể giữ **history riêng**.

~~~text
Release yêu cầu V12
    |
    +-- Shard A: V12 SUCCESS
    +-- Shard B: V12 SUCCESS
    +-- Shard C: V11, chưa áp dụng
    +-- Shard D: V12 FAILED
~~~

Một số shard đang ở V12 không có nghĩa toàn hệ thống đã ở V12. Nếu Java mới chỉ tương thích từ V12, khi route request đến Shard C có thể lỗi.

Cần:

- Theo dõi version và success theo **mỗi database/shard**.
- Điều phối migration với giới hạn đồng thời, tránh tất cả shard tạo tải DDL cùng lúc.
- Có compatibility window cho app cũ/mới khi rollout chưa hoàn tất.
- Dừng bật tính năng đòi schema mới trên những shard chưa đạt version.
- Lập kế hoạch backup/recovery cho từng shard, kể cả khi một shard migration thất bại.
- Tránh coi một câu **Connection.commit()** cục bộ là giao dịch nguyên tử trên nhiều shard.

Nếu một migration chỉ áp dụng một phần shards, quy trình retry phải dựa trên lịch sử và trạng thái của từng shard; không chạy lại V12 cho toàn bộ mà không phân loại.

## 19. Quan sát và kiểm toán quá trình tiến hóa dữ liệu

Những metric/tín hiệu nên có:

| Tín hiệu | Ý nghĩa |
|---|---|
| **schema_version** theo environment/database | Database đã đạt version nào |
| **pending_migration_count** | Số bước chưa áp dụng |
| **migration_duration_seconds** | Bước nào chạy bất thường lâu |
| **migration_failure_total** | Số lần lỗi và nguyên nhân |
| **checksum_validation_error** | Nội dung file đã áp dụng không khớp |
| **migration_lock_wait** | Tác nhân nào đang chờ quyền migration |
| **DDL blocked queries** | Migration tác động lên traffic ra sao |
| **backfill_rows_processed/remaining** | Tiến độ data backfill |
| **WAL rate / replication lag** | Backfill/DDL có làm chậm replica không |
| **schema_compatibility_gate** | Binary nào đang đòi schema version nào |

Các tên metric là ví dụ thiết kế instrument, không phải mặc định của mọi công cụ. Log nên có **deployment ID, Git commit, database/shard, version, tên migration, thời lượng và kết quả**, tránh password, access token hoặc payload người dùng.

### 19.1. Truy vấn history Flyway

Nếu dùng tên bảng Flyway mặc định của một phiên bản tương ứng và tài khoản được cấp quyền đọc:

~~~sql
SELECT installed_rank, version, description, script,
       installed_on, execution_time, success
FROM flyway_schema_history
ORDER BY installed_rank;
~~~

Cấu trúc bảng metadata thay đổi theo công cụ/phiên bản và có thể được cấu hình tên khác. Không dùng câu truy vấn này cho Liquibase nếu không có bảng tương ứng.

### 19.2. Xem transaction đang chờ trong PostgreSQL

~~~sql
SELECT pid, state,
       now() - xact_start AS transaction_age,
       wait_event_type, wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Thông tin chỉ là ảnh chụp tại một thời điểm; mức chi tiết phụ thuộc quyền. Cần kết hợp log migration, khóa và metric DB để tìm tại sao DDL chậm.

## 20. Bài tập tình huống

### Bài 1 — File V2 bị sửa sau khi chạy

Production đã áp dụng V2. Một developer mở V2 thêm index, khiến công cụ báo checksum mismatch. Cần xử lý thế nào?

**Gợi ý:** không sửa history cho qua. Khôi phục nội dung V2 gốc, thêm migration version mới cho index và validate lại.

### Bài 2 — History báo đúng nhưng schema sai

Bảng history báo V5 success, nhưng một người đã DROP index ngoài pipeline. Có thể kết luận schema hoàn toàn hợp lệ không?

**Gợi ý:** không. Checksum chỉ kiểm tra lịch sử nội dung migration, không tự phát hiện mọi drift; cần introspection và diff.

### Bài 3 — Rolling deployment rename cột

App v1 đọc full_name, App v2 đọc display_name. Có nên rename full_name thành display_name ở một lần deploy trong lúc hai phiên bản cùng chạy?

**Gợi ý:** không an toàn nếu app v1 còn dùng tên cũ. Dùng expand-migrate-contract hoặc một downtime có kiểm soát.

### Bài 4 — Backfill dữ liệu lớn

Một migration UPDATE 100 triệu hàng trong một transaction dài giữa giờ cao điểm. Rủi ro là gì?

**Gợi ý:** lock, WAL, replica lag, timeout và khó resume. Dùng batch, checkpoint, idempotency và giám sát.

### Bài 5 — Index đồng thời

Một migration chứa CREATE INDEX CONCURRENTLY nhưng công cụ đặt lệnh trong transaction block, dẫn tới lỗi. Vì sao?

**Gợi ý:** PostgreSQL không cho lệnh này trong transaction block. Cần nontransactional migration theo tool và kiểm tra index invalid nếu đã chạy một phần.

### Bài 6 — DDL thất bại

Một DBMS implicit commit DDL. Migration ba bước thất bại ở bước thứ ba. Có thể mặc định mọi DDL đều rollback không?

**Gợi ý:** không. Phải kiểm tra đối tượng đã thay đổi và lịch sử trước khi sửa/retry.

### Bài 7 — Baseline nhầm môi trường

Nhóm bật auto-baseline trên một database chưa được kiểm kê, rồi công cụ coi đây là schema đang quản lý. Rủi ro?

**Gợi ý:** schema có thể sai hoặc thiếu đối tượng, metadata baseline không chứng minh cấu trúc đúng.

### Bài 8 — Version khác nhau theo shard

Shard A/B đã lên V12, shard C còn V11. App mới chỉ đọc cột được thêm ở V12. Cần làm gì?

**Gợi ý:** compatibility gate và điều phối migration C trước hoặc duy trì code hỗ trợ V11 cho tới khi rollout hoàn tất.

### Bài 9 — Rollback app sau khi DROP COLUMN

Migration đã DROP full_name, sau đó ứng dụng v2 lỗi và nhóm định rollback binary v1 đọc full_name. Có an toàn?

**Gợi ý:** không, schema đã phá tương thích. Cần kế hoạch sửa tiến lên hoặc phục hồi có kiểm soát.

### Bài 10 — Hai branch cùng V8

Hai PR tạo V8 khác nội dung, một đã chạy staging. Nên xử lý thế nào?

**Gợi ý:** phải đối soát lịch sử staging; chọn version mới và quy trình thích hợp thay vì đổi tên bừa tệp đã áp dụng.

## 21. Tổng kết

**Quản lý migration bằng phiên bản và lịch sử thực thi** biến thay đổi database thành quy trình có thể theo dõi và kiểm thử. **Version** xác định thứ tự, **migration script/changeset** mô tả thay đổi, **checksum** cảnh báo nội dung bị sửa, còn **history** ghi database đã áp dụng các bước nào. History không phải backup và không đảm bảo schema thực tế không bị drift.

Trong Java, tiến hóa an toàn cần kết hợp **Flyway hoặc Liquibase, ranh giới transaction, JDBC/DataSource, CI/CD, code review và kiểm soát đồng thời**. Với hệ thống có rolling deployment, ưu tiên **expand → migrate → contract**; với dữ liệu lớn, backfill theo lô, idempotent và có checkpoint riêng; với DDL rủi ro cao, cần đo khóa, có backup/restore và kế hoạch dừng rollout.

Một hệ thống trưởng thành không chỉ trả lời “đã ở migration V mấy?”, mà còn trả lời **“database nào đã chạy, trạng thái dữ liệu thực tế ra sao, bản ứng dụng nào còn phụ thuộc schema cũ, và sẽ khôi phục thế nào nếu thay đổi không thành công?”**.
