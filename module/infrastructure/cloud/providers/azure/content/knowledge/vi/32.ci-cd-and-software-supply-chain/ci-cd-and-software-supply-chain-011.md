# Triển khai thay đổi database cùng phiên bản ứng dụng

Một bản phát hành Spring Boot thường không chỉ đổi Java code. Chẳng hạn ứng dụng bán hàng muốn đổi tên cột **customer_name** thành **display_name**, thêm trạng thái đơn hàng và chuyển dữ liệu cũ sang định dạng mới. Nếu đội phát triển đổi schema database và ứng dụng **cùng một thời điểm** theo cách không tương thích, người dùng có thể gặp lỗi HTTP 500 trong lúc rolling deployment, khi phiên bản cũ và mới vẫn phục vụ song song. Ngược lại, nếu phát hành code trước nhưng database chưa có cột mới, application startup có thể thất bại ngay.

Đây là bài toán **database change deployment**, thuộc chương **CI/CD và chuỗi cung ứng phần mềm** của module **CLOUD_PROVIDERS_AZURE**. Trong quá trình học Azure từ subscription, resource group và Microsoft Entra ID tới mạng ảo, compute, lưu trữ, dữ liệu, bảo mật, giám sát và chi phí, chúng ta cần xem **database schema, dữ liệu, ứng dụng, migration scripts và pipeline** là một đơn vị thay đổi có kiểm soát. Bài tập trung vào Azure SQL Database và Azure Database for PostgreSQL, Java/Spring Boot, Flyway/Liquibase, Azure App Service, Azure Container Apps, AKS, GitHub Actions và Azure Pipelines. Các nguyên tắc phần lớn áp dụng cho RDBMS khác, nhưng câu lệnh DDL, cơ chế transaction, khóa và rollback phụ thuộc database engine.

**Điểm mấu chốt:** triển khai **cùng một release** không nhất thiết nghĩa là chạy **DDL và đổi toàn bộ application instances cùng một giây**. Một release an toàn thường bao gồm nhiều bước có thứ tự, có thể tạm thời chạy **hai phiên bản ứng dụng** với **một schema đang chuyển tiếp**. Cần bảo đảm mỗi trạng thái trung gian vẫn hoạt động hoặc có cơ chế cô lập traffic có kiểm soát.

Các ví dụ dùng **dữ liệu giả**, một hệ thống đặt hàng giả định và những câu lệnh cần rà soát theo engine/version/SKU thực tế. Các endpoint, resource names, IAM roles, giới hạn dịch vụ và giá có thể thay đổi theo region/plan. Không chạy migration mẫu trên production hoặc dữ liệu khách hàng thật mà không có approval, backup/restore test và kế hoạch ứng cứu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **application version**, **schema version**, **data migration** và **deployment state**.
2. Nhận biết các thay đổi **backward-compatible**, **forward-compatible** và **breaking**.
3. Thiết kế kế hoạch **expand → migrate/backfill → switch → contract** để giảm downtime.
4. Dùng **Flyway** hoặc **Liquibase** quản lý migration scripts trong cùng version control với code.
5. Tổ chức **migration runner duy nhất** trong CI/CD, tránh nhiều replicas tranh chạy DDL.
6. Viết migration có **ràng buộc an toàn**, có version và kiểm tra schema/history.
7. Phân biệt **schema migration, data backfill và database restore**.
8. Phối hợp database changes với **App Service slots, Container Apps revisions, AKS rolling updates**.
9. Thiết kế **pre-deployment compatibility tests, staging rehearsal, approval và release gates**.
10. Quản lý **Microsoft Entra identity, data-plane permissions, private networking, Key Vault và secrets**.
11. Biết khi nào **rollback ứng dụng** an toàn, khi nào phải **roll forward** database.
12. Giám sát lock waits, replication, errors, migration duration và business invariants.
13. Lập **runbook ứng cứu và kế hoạch khôi phục** cho migration thất bại.
14. Phân tích chi phí, downtime budget và trách nhiệm vận hành trong một bản phát hành.

## 2. Một lần release gồm nhiều trạng thái

Giả sử có:

~~~text
orders-api v1  <----> database schema S1
orders-api v2  <----> database schema S2
~~~

Tưởng như chỉ cần thay **v1/S1 → v2/S2**. Nhưng trong thực tế:

~~~text
T0: tất cả replicas chạy v1, database S1
T1: migration bắt đầu; app v1 vẫn nhận requests
T2: một số instances chạy v2, một số chạy v1
T3: tất cả instances chạy v2
T4: dữ liệu cũ tiếp tục được backfill/chuẩn hóa
T5: sau thời gian an toàn mới bỏ phần schema không còn dùng
~~~

Mỗi thời điểm phải trả lời:

- **App v1 có còn đọc/ghi schema hiện tại được không?**
- **App v2 có chạy khi dữ liệu cũ chưa backfill xong không?**
- **Có request/worker cũ còn đang xử lý không?**
- **Nếu v2 bị rollback về v1, schema có còn tương thích không?**
- **Có message/cron job nào mang định dạng cũ đang chờ trong queue không?**

Nếu không, một release "đã deploy thành công" theo CI/CD vẫn có thể làm hỏng nghiệp vụ.

## 3. Bốn lớp phiên bản phải quản lý

| Lớp | Ví dụ | Câu hỏi quan trọng |
|---|---|---|
| **Ứng dụng** | orders-api v1.8.0/v1.9.0 | Code nào đang đọc/ghi thuộc tính nào? |
| **Schema** | Flyway V15, V16 | Bảng, cột, index, constraint hiện có? |
| **Dữ liệu** | 60% customers đã có display_name | Dữ liệu cũ chuyển đổi tới đâu? |
| **Contract/API/event** | REST v2, Service Bus event schema 3 | Consumer/worker cũ còn nhận format cũ không? |

### Schema version không phải số release ứng dụng

Một release ứng dụng có thể:

- Không có migration schema nào.
- Có nhiều migration SQL liên tiếp.
- Đọc schema mới nhưng chưa sử dụng.
- Chỉ chuyển feature flag hoặc backfill data.

Vì vậy **orders-api v2.0.0 không bắt buộc trùng Flyway V2**. Không hard-code quy tắc "app version = schema version" nếu release có nhiều services dùng chung database.

### Migration history

Flyway/Liquibase có bảng lịch sử riêng theo cơ chế sản phẩm; ví dụ Flyway thường dùng **flyway_schema_history**. Bảng này chứng minh migration nào đã được công cụ ghi nhận, **không chứng minh tất cả dữ liệu đã được chuyển đổi đúng** nếu backfill được thực thi ngoài migration.

## 4. Compatibility: luật quan trọng nhất

Thay đổi database có thể thuộc ba nhóm:

| Thay đổi | Thường tương thích với app cũ? | Ghi chú |
|---|---|---|
| Thêm cột **nullable** không làm đổi code cũ | Thường có | Kiểm tra triggers/ORM SELECT * /write patterns |
| Thêm bảng mới | Thường có | Quyền truy cập và data model |
| Thêm index | Thường có ở mức logic | Có thể gây locks, IO, chi phí |
| Thêm constraint NOT NULL ngay | Có thể phá | Dữ liệu cũ, writers cũ thiếu trường |
| Đổi tên cột | Thường phá | SQL/ORM ở app cũ dùng tên cũ |
| Xóa cột | Phá nếu app cũ còn dùng | Cần contract phase |
| Đổi type/precision | Có thể phá | Truncation, conversion, locking |
| Đổi semantics của enum/status | Có thể phá | App cũ không hiểu giá trị mới |
| Xóa bảng/foreign key | Có thể phá | Đánh giá reader/writer và business invariants |

**"Thường có" không phải bảo đảm tuyệt đối.** Một ứng dụng dùng native query **SELECT *** và deserialize theo vị trí cột, hoặc dùng ORM mapping nghiêm ngặt, có thể bị ảnh hưởng bởi thay đổi tưởng như chỉ thêm cột.

### Hai hướng tương thích

- **Backward compatibility:** schema mới vẫn phục vụ phiên bản ứng dụng cũ.
- **Forward compatibility:** ứng dụng mới vẫn xử lý được dữ liệu và trạng thái cũ trong giai đoạn chuyển tiếp.

Rolling update, blue-green và rollback đòi cả hai hướng ở những thời điểm khác nhau. Nếu không thiết kế rõ, **thành công trên staging chỉ có một phiên bản** không kiểm chứng được tính tương thích lúc production có hai phiên bản.

## 5. Vì sao "ALTER TABLE rồi deploy" nguy hiểm?

Ví dụ:

~~~sql
-- Schema ban đầu:
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);
~~~

App v1:

~~~sql
SELECT id, customer_name
FROM customers
WHERE id = 1001;
~~~

Nếu deploy trực tiếp:

~~~sql
ALTER TABLE customers RENAME COLUMN customer_name TO display_name;
~~~

thì **v1 vẫn chạy** trong lúc migration/rollback sẽ gặp lỗi vì **customer_name** không còn. Ngược lại, nếu v2 chỉ biết **display_name** nhưng schema chưa đổi, v2 lỗi trước migration.

### Rủi ro khác ngoài lỗi SQL

- DDL phải lấy **schema/table locks**, gây chờ truy vấn.
- Application connections đã cache prepared statements/plans.
- Connection pools chưa refresh mapping.
- Old worker message vẫn dùng field cũ.
- Deploy dừng giữa chừng và tạo **half-migrated state**.
- Feature flag bật khi backfill chưa xong.
- Backup/restore sai thời điểm làm mất dữ liệu mới ghi.

Giải pháp đáng tin là **chia bản thay đổi thành nhiều pha tương thích**, không chỉ "thực thi SQL nhanh hơn".

## 6. Mô hình Expand → Migrate → Contract

~~~mermaid
flowchart LR
    A[App v1 + schema S1] --> B[Expand: thêm schema mới tương thích]
    B --> C[App chuyển tiếp: đọc/ghi hỗ trợ 2 dạng]
    C --> D[Backfill và verify]
    D --> E[Switch reads + hoàn tất rollout]
    E --> F[Observe và chờ rollback window]
    F --> G[Contract: bỏ cột/code cũ]
~~~

### Expand

Thêm cấu trúc mới mà **không loại bỏ thứ app cũ vẫn cần**. Ví dụ thêm **display_name nullable**, index mới hoặc bảng mới. App v1 vẫn hoạt động.

### Migrate

Thay đổi code để đọc/ghi dạng mới, chuyển dữ liệu cũ theo batch, đo tiến độ, kiểm tra lệch dữ liệu. Trong khoảng thời gian này cần định nghĩa **nguồn sự thật** và cách xử lý updates đồng thời.

### Switch

Khi dữ liệu đủ hoàn chỉnh, chuyển read path/feature flag sang trường mới. Chạy test, theo dõi lỗi và có khả năng quay về code cũ khi schema vẫn tương thích.

### Contract

Chỉ sau khi chắc chắn **không còn app/worker/report/query/ETL** dùng cấu trúc cũ và đã qua rollback window, mới xóa cột/index/triggers/compatibility code. **Contract là thay đổi phá vỡ tương thích**, phải được review như một release riêng.

**Không nhất thiết bốn pha chạy trong một pipeline duy nhất.** Với dữ liệu lớn hoặc nhiều services, contract có thể diễn ra sau vài ngày/tuần. Trong một lần release đầu tiên, deploy app v2 và schema S2 theo thứ tự an toàn là đã đạt mục tiêu; không cần ép xóa cột cũ ngay.

## 7. Ví dụ xuyên suốt: đổi customer_name thành display_name

**Mục tiêu nghiệp vụ:** đổi cách gọi tên khách hàng, cho phép backend dùng field **display_name**, nhưng không gián đoạn orders-api v1 đang chạy và workers cũ vẫn nhận messages.

Schema ban đầu:

~~~sql
-- PostgreSQL minh họa:
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

### Kế hoạch sai

1. Rename cột.
2. Deploy v2.
3. Nếu deploy lỗi, rollback code về v1.

**Vấn đề:** ngay bước 1 app v1 có thể lỗi; rollback code không phục hồi tên cột. Vì vậy kế hoạch không có trạng thái an toàn trong lúc deploy.

### Kế hoạch đúng hơn

1. **Expand:** thêm display_name nullable, không rename/drop.
2. **Release chuyển tiếp:** app có thể đọc display_name nếu có, fallback customer_name; tiếp tục duy trì dữ liệu cũ.
3. **Backfill:** sao chép/biến đổi dữ liệu hiện có theo batch.
4. **Switch:** readers mới ưu tiên display_name, áp kiểm tra consistency.
5. **Contract:** sau khi app cũ/worker cũ không còn và rollback window qua, mới xóa customer_name.

**Lưu ý:** nếu cả hai trường được phép update, chỉ backfill một lần là không đủ. Phải có cơ chế **dual-write có kiểm soát, database trigger được review, hoặc một nguồn dữ liệu chuẩn** và đồng bộ cập nhật trong giai đoạn chuyển tiếp.

## 8. Migration expand: thêm cột nullable

Với PostgreSQL:

~~~sql
-- Ví dụ Flyway V2026112001__add_display_name.sql
ALTER TABLE customers
    ADD COLUMN display_name VARCHAR(200);
~~~

### Vì sao nullable?

Nếu app v1 vẫn tạo customer mà không gửi **display_name**, cột **NOT NULL không có default** sẽ khiến INSERT v1 thất bại. Cột nullable cho phép cả hai phiên bản chạy khi chuyển đổi.

### Không có nghĩa DDL không khóa

PostgreSQL **ALTER TABLE** cần lock phù hợp, kể cả thay đổi metadata đơn giản. Nó có thể phải chờ các transaction cũ và chặn statements khác trong thời gian giữ lock. Trong hệ thống bận, đặt chính sách **lock_timeout**, chạy rehearsal, đo lock waits và có cơ chế retry/approval.

### Không hứa "IF NOT EXISTS" luôn tốt

~~~sql
-- Chỉ minh họa cú pháp engine hỗ trợ:
ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(200);
~~~

Cú pháp này có thể giúp tránh lỗi khi chạy thủ công lặp lại, nhưng **không thay thế migration history/version checks**. Nó có thể che drift: cột đã tồn tại nhưng type/constraints không đúng. Với Flyway versioned migrations, ưu tiên scripts có trạng thái được quản trị và kiểm tra schema.

## 9. Ứng dụng chuyển tiếp: đọc dữ liệu an toàn

Đọc ưu tiên field mới, fallback field cũ:

~~~sql
SELECT
    id,
    COALESCE(display_name, customer_name) AS effective_display_name
FROM customers
WHERE id = :id;
~~~

Khi dùng Spring Data JPA, phải có **entity mapping** tương thích schema đã expand:

~~~java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class CustomerEntity {
    @Id
    private Long id;

    @Column(name = "customer_name", nullable = false)
    private String legacyName;

    @Column(name = "display_name")
    private String displayName;

    public String effectiveDisplayName() {
        return displayName != null ? displayName : legacyName;
    }

    // Constructors/getters/setters do dự án tự bổ sung.
}
~~~

Ví dụ là **entity skeleton**, chưa có repository, validation, auditing, tenant checks hay getters/setters. Quan trọng nhất là **app v2 chuyển tiếp chỉ chạy sau khi cột display_name tồn tại**, nhưng vẫn có thể đọc data cũ chưa backfill.

### Nếu không thể deploy migration trước app?

Có thể chọn một bản ứng dụng trung gian không truy cập field mới, deploy trước rồi chạy migration sau. Tuy nhiên phải thiết kế hẳn compatibility matrix. Không mặc định JPA/Hibernate sẽ khởi động nếu entity đã mapping cột chưa tồn tại.

## 10. Ghi dữ liệu khi hai phiên bản cùng tồn tại

Trong giai đoạn chuyển tiếp, **app v1** vẫn ghi customer_name. App v2 có thể ghi cả hai:

~~~text
v1 writer -> customer_name only
v2 writer -> customer_name + display_name
v2 reader -> display_name if present, else customer_name
~~~

### Một nguyên tắc đơn giản

Trong giai đoạn v1/v2 cùng chạy, chọn **customer_name làm canonical write source** và duy trì display_name là mirror/copy với consistency rule rõ. Nếu v2 cho phép sửa display_name nhưng v1 vẫn sửa customer_name, hai bản cập nhật có thể ghi đè nhau theo thời gian.

### Mẫu cập nhật trong một database transaction

~~~sql
UPDATE customers
SET customer_name = :new_name,
    display_name = :new_name,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :customer_id;
~~~

**Việc ghi hai cột trong một UPDATE** cho cùng row có tính nguyên tử ở database transaction, nhưng **không bảo đảm v1 ghi theo cơ chế cũ cũng update display_name**. Muốn đồng bộ trong lúc writers v1 tồn tại, phải:

1. Tạm bảo đảm mỗi customer chỉ được sửa qua writer đã nâng cấp, **hoặc**
2. Thêm **trigger/compatibility layer** được review và test, **hoặc**
3. Chấp nhận field mới có thể stale, tiếp tục đọc canonical legacy field cho tới khi tất cả writers cũ được nâng cấp và chạy reconciliation.

Trong nhiều hệ thống, cách an toàn là **deploy code có dual-write logic (vẫn đọc legacy field) tới tất cả replicas trước**, rồi backfill và chuyển reads.

## 11. Migration backfill: không khóa cả bảng lớn

Với bảng rất lớn, một UPDATE toàn bộ có thể tạo lock contention, WAL/transaction log phình to, replica lag và chi phí.

~~~sql
-- Chỉ minh họa cho bảng nhỏ / test data:
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL;
~~~

Đối với production lớn, cần một **backfill job có checkpoint**, các batch nhỏ và giới hạn tải.

### Mô hình backfill theo khóa tăng dần

~~~text
Start cursor = 0
  |
  +-- Select next N IDs > cursor
  +-- Update only corresponding rows when safe
  +-- Commit one batch
  +-- Persist cursor and counts
  +-- Sleep/throttle on DB pressure
  +-- Repeat until no eligible rows
~~~

**Không xây backfill theo OFFSET lớn** cho bảng liên tục thay đổi mà giả định các rows sẽ được duyệt chính xác một lần. Keyset pagination/cursor bền vững thường dễ kiểm soát hơn, nhưng vẫn phải xử lý inserts, updates và retries.

### Reconciliation

Sau mỗi lượt, kiểm tra:

~~~sql
SELECT COUNT(*) AS missing_new_name
FROM customers
WHERE display_name IS NULL;

SELECT COUNT(*) AS inconsistent_name
FROM customers
WHERE display_name IS NOT NULL
  AND display_name <> customer_name;
~~~

Hai truy vấn chỉ đúng với **business rule** hai cột phải bằng nhau. Nếu **display_name** cho phép nickname khác customer_name, không được coi mọi khác biệt là lỗi. Khi yêu cầu nghiệp vụ thay đổi, cần định nghĩa mapping/normalization riêng.

## 12. Switch và contract khi nào?

### Điều kiện chuyển read path

- Tất cả writers đã được nâng cấp hoặc có cơ chế đồng bộ.
- Backfill đã xong theo quy tắc chấp nhận.
- Có số liệu về missing/mismatch ổn định.
- v2 đọc display_name chính xác với dữ liệu mới và cũ.
- API/event consumers hiểu field mới khi được bật.
- Có feature flag/rollback plan hợp lệ.

### Contract sau rollback window

~~~sql
-- Chỉ chạy ở release contract đã được phê duyệt;
-- không chạy ngay sau expand:
ALTER TABLE customers
    DROP COLUMN customer_name;
~~~

**Về logic, đây là thay đổi phá vỡ tương thích**. Trước khi chạy phải tìm mọi SQL query, JPA mapping, reporting job, ETL pipeline, backup restore scripts, old container revisions, slots và workers còn đọc cột cũ.

### Một release timeline an toàn

~~~text
R1: Expand schema + app tương thích với 2 cột
R2: Hoàn tất rollout writers + backfill + verify
R3: Switch reads sang cột mới + monitor
R4: Contract bỏ cột legacy sau rollback window
~~~

Không cần ấn định chính xác một tuần giữa mỗi release; quyết định bằng **dữ liệu quan sát, inventory clients và mức rủi ro**, không chỉ bằng lịch.

## 13. Flyway: versioned migrations theo source control

**Flyway** là công cụ quản lý database migrations theo các file có version, tên và checksum. Trong dự án Spring Boot, các migration SQL thường đặt ở:

~~~text
src/main/resources/db/migration/
  V1__create_customers.sql
  V2__create_orders.sql
  V3__add_display_name.sql
  V4__add_order_status.sql
~~~

### Cơ chế cơ bản

1. Công cụ kết nối database bằng identity/credential được cấp.
2. Kiểm tra bảng schema history (nếu được quản lý bởi Flyway).
3. Đọc version và checksum các migrations.
4. Áp dụng migrations chưa chạy, theo thứ tự được hỗ trợ.
5. Ghi trạng thái migration và lỗi vào lịch sử.
6. Không tùy ý chạy lại một versioned migration đã thành công.

### Quy tắc đặt tên

Ví dụ:

~~~text
V2026112001__add_customers_display_name.sql
V2026112002__create_order_outbox.sql
V2026112003__add_order_status_index.sql
~~~

Phân tách version và description bằng hai dấu gạch dưới theo convention Flyway. Chọn version scheme nhất quán cho đội; **không sửa nội dung một migration đã apply vào production**, vì checksum và audit history có thể không khớp. Nếu cần thay đổi tiếp, tạo migration version mới, trừ quy trình repair/rebaseline đặc biệt đã được phê duyệt.

### Điểm cần lưu ý

- Flyway không tự chứng minh tính **backward compatibility**.
- Migration history không thay thế backup và kiểm tra dữ liệu.
- DDL có thể gây lock mặc dù SQL hợp lệ.
- Engine-specific SQL có thể không chạy được trên database loại khác.
- Tùy version Flyway, support database/driver có thể đòi module riêng; kiểm tra dependencies chính thức.
- Không chạy **clean** trên database production chỉ vì tests dùng clean.

## 14. Flyway với Spring Boot: cấu hình cơ bản

Ví dụ dependencies Maven dùng Spring Boot dependency management:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
  </dependency>
  <dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
  </dependency>
</dependencies>
~~~

Trong một số version Flyway, PostgreSQL support được đóng module riêng, ví dụ **flyway-database-postgresql**. Nếu project thực dùng version đó, thêm module tương thích với Flyway BOM đang dùng:

~~~xml
<dependency>
  <groupId>org.flywaydb</groupId>
  <artifactId>flyway-database-postgresql</artifactId>
</dependency>
~~~

**Không sao chép các dependency mà không kiểm tra Spring Boot–Flyway–JDBC driver compatibility matrix**, tính năng license/edition và Maven dependency management thực tế.

### Spring profile local

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_lab
    username: orders_lab
    password: PLACEHOLDER_FROM_SECRET_PROVIDER
  flyway:
    enabled: true
    locations: classpath:db/migration
    validate-on-migrate: true
~~~

Trong production, **không commit password thật**; sử dụng secret provider/environment injection an toàn và tách config local. Một pipeline riêng có thể quản migration và Spring Boot app đặt **spring.flyway.enabled=false** để tránh nhiều replicas tự migrate. Tùy thiết kế, một migration runner dùng cùng Flyway scripts nhưng được cấp credential/schema privileges riêng.

### Không để Hibernate tự sửa schema production

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Nếu dùng JPA/Hibernate, **validate** giúp phát hiện mapping/schema mismatch ở mức Hibernate kiểm tra; **không bảo đảm database hoàn toàn tương thích** với mọi native query, trigger hoặc business invariant. Tránh **ddl-auto=update/create/create-drop** trên production để schema migration có lịch sử, review và deployment ordering rõ.

## 15. Liquibase: changeSet, checksum và rollback

**Liquibase** quản lý thay đổi qua **changeSets**, có thể viết XML/YAML/JSON/SQL theo version/capability. Một changelog YAML minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: add-customer-display-name
      author: orders-team
      changes:
        - addColumn:
            tableName: customers
            columns:
              - column:
                  name: display_name
                  type: varchar(200)
      rollback:
        - dropColumn:
            tableName: customers
            columnName: display_name
~~~

**Đây chỉ là ví dụ lab về cơ chế rollback clause**, không phải khuyến nghị tự động chạy dropColumn khi production rollback. Nếu cột đã chứa dữ liệu, rollback này **xóa dữ liệu**, không có gì bảo đảm có thể khôi phục. Trong production, destructive changes phải có kế hoạch riêng, backup/restore và duyệt mức độ ảnh hưởng.

### Những khái niệm

- **DATABASECHANGELOG** lưu lịch sử changeSets.
- **DATABASECHANGELOGLOCK** hỗ trợ coordination/locking của Liquibase.
- **Preconditions** kiểm tra điều kiện trước changeSet.
- **Checksum** phát hiện thay đổi nội dung changeSet đã áp dụng.
- **Rollback definitions** có thể giúp với một số thay đổi, nhưng không biến mọi migration thành đảo ngược an toàn.

### Flyway hay Liquibase?

| Tiêu chí | Flyway | Liquibase |
|---|---|---|
| Cách làm quen thuộc | Versioned SQL scripts | Changelog/changeSets, SQL hoặc DSL |
| Database-specific SQL | Rõ ràng, dễ review | Có thể dùng SQL/change types |
| Schema history | Schema history | Changelog tables |
| Rollback | Forward migrations thường là mặc định an toàn | Có hỗ trợ rollback mechanisms tùy loại change |
| Coordination | Migration locking theo engine/version | Changelog lock |
| Yêu cầu vận hành | Đều cần credential, pipeline và test | Đều cần credential, pipeline và test |

Chọn **một công cụ canonical cho một database/schema boundary** trừ khi có migration plan đặc biệt; chạy Flyway và Liquibase độc lập trên cùng schema mà không có ownership rõ có thể gây drift và race.

## 16. Ai được quyền chạy migrations?

Một anti-pattern rất phổ biến: **mọi Spring Boot replica tự chạy Flyway lúc startup**, đồng thời trong rolling update.

~~~text
Old replicas: v1 v1 v1
                 |
Deploy v2:       +-- v2 Pod A -> Flyway migrate
                     v2 Pod B -> Flyway migrate
                     v2 Pod C -> Flyway migrate
~~~

Migration tools có cơ chế lock/tracking, nhưng **không nên dùng chúng thay cho chiến lược phối hợp release**. Một pod có thể block startup chờ lock, HPA khởi động thêm pods, health checks timeout, và quyền DDL phải được phân phối cho mọi app instances.

### Mô hình khuyến nghị: một migration runner

~~~mermaid
flowchart TD
    A[CI build + test] --> B[Migration artifact / scripts immutable]
    B --> C[Staging migrate + integration tests]
    C --> D[Production approval]
    D --> E[One-shot migration runner]
    E --> F{History + invariants PASS?}
    F -- No --> G[Stop app rollout + incident]
    F -- Yes --> H[Roll out app version]
    H --> I[Smoke + monitor]
~~~

**Một migration runner** có thể là CI/CD deployment job có private network access, AKS Kubernetes Job, ACA Job hoặc một approved automation host, không nhất thiết là application pod. Runner có schema privileges trong thời gian cần thiết; runtime app dùng **least-privileged DML identity**.

### Trường hợp chạy Flyway trong Spring startup

Được chấp nhận trong **lab/một instance có quản trị** hoặc hệ thống nhỏ với rủi ro thấp, nhưng production nhiều replicas cần kiểm tra startup contention và least privilege. Khi release có backward-incompatible migrations, việc agent tự migrate ở startup còn nguy hiểm hơn vì timing không được kiểm soát.

## 17. Exactly-once migration có thật không?

Migration framework thường bảo đảm trạng thái và locking ở mức của nó, nhưng không thể bảo đảm **mọi SQL/data backfill bên trong** thực thi exactly-once qua mọi engine và mọi lỗi.

Ví dụ:

~~~text
Job starts
  -> ALTER TABLE succeeds
  -> Backfill writes 70% rows
  -> Process crashes
  -> Job retries
~~~

Nếu migration DDL không transactional hoặc backfill được chạy bên ngoài migration transaction, trạng thái có thể đã thay đổi một phần.

### Vì sao cần idempotency?

- Migration phải biết những thay đổi nào đã apply.
- Backfill chạy lại không được nhân đôi dữ liệu.
- Unique constraints ngăn trùng khi retry.
- Checkpoint/sentinel cần phản ánh commit bền.
- Khi partial failure, phải có **reconciliation** và runbook.

**Không dùng cùng một phiên migration version để chạy lại một phép UPDATE không bền vững** mà không hiểu trạng thái tool. Dữ liệu lớn nên có một backfill job riêng, với **job version, cursor, batch transaction và monitoring**.

## 18. Transactional DDL: PostgreSQL và Azure SQL khác nhau

**Azure Database for PostgreSQL – Flexible Server** tuân theo cơ chế PostgreSQL tương ứng; nhiều thao tác DDL có thể thực hiện trong transaction, nhưng **không phải mọi lệnh**. **Azure SQL Database** dùng SQL Server/T-SQL với quy tắc transaction/DDL, locking và online operations khác.

| Thao tác | PostgreSQL | Azure SQL Database |
|---|---|---|
| Thêm cột | ALTER TABLE ... ADD COLUMN | ALTER TABLE ... ADD ... |
| Index không khóa ghi lâu | CREATE INDEX CONCURRENTLY khi hỗ trợ và phù hợp | Online/resumable index operations theo edition/service tier/option |
| Transactional behavior | Nhiều DDL transactional, có exceptions | Phụ thuộc statement/engine restrictions |
| Locking | Table/relation locks, MVCC, wait | Schema modification locks, transaction/log/lock waits |
| Monitoring | pg_stat_activity, pg_locks, metrics | sys.dm_* views, Query Store/metrics |
| Migration strategy | Batches, lock_timeout, transaction control | Batches, lock timeout/config, index options |

**Không copy PostgreSQL SQL rồi chạy trên Azure SQL**, hoặc sao chép SQL Server **WITH (ONLINE = ON)** mà không kiểm tra SKU/tính năng hiện hành. Migration scripts nên được test với đúng engine/version và cấu hình gần production.

### DDL có thể chặn ứng dụng

Một câu lệnh **ALTER TABLE** nhanh trên 100 rows ở local có thể chờ nhiều phút ở production vì có long-running transactions hoặc lock queue. Cần test **transaction duration, lock acquisition, WAL/transaction log, CPU/IO, replica lag** trong điều kiện tương đương.

## 19. PostgreSQL: index concurrently

Giả sử thêm index cho orders:

~~~sql
-- PostgreSQL:
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON orders (customer_id, created_at);
~~~

### Vì sao dùng concurrently?

Nó giúp giảm một số loại chặn đọc/ghi so với xây index thông thường, nhưng có thể **tốn thời gian, IO** và có những restriction.

**Quan trọng:**

- PostgreSQL **CREATE INDEX CONCURRENTLY không được chạy trong một transaction block**.
- Flyway migration bình thường có thể dùng transaction theo cấu hình/version; cần tạo migration non-transactional theo capability và settings chính xác.
- Nếu lệnh concurrent index bị lỗi, có thể để lại **invalid index**, cần kiểm tra catalog và cleanup theo runbook.
- **Không hứa zero locks**: vẫn có giai đoạn chờ transactions và các tác động performance.

### Kiểm tra index sau release

~~~sql
-- PostgreSQL minh họa: kiểm tra trạng thái index trong pg_index
SELECT
    c.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index i
JOIN pg_class c ON c.oid = i.indexrelid
WHERE c.relname = 'idx_orders_customer_created';
~~~

Đây là cách kiểm tra catalog theo PostgreSQL; table/index names và quyền truy vấn cần đúng. Một index tồn tại trên catalog **không tự chứng minh query planner đang chọn nó**; cần dùng EXPLAIN (ANALYZE) trong môi trường an toàn và theo dõi query latency.

## 20. Azure SQL Database: thêm cột, index và Query Store

T-SQL minh họa:

~~~sql
-- Azure SQL Database: cú pháp SQL Server, không phải PostgreSQL.
ALTER TABLE dbo.Customers
ADD DisplayName NVARCHAR(200) NULL;
~~~

Sau đó, nếu cần index:

~~~sql
CREATE INDEX IX_Customers_DisplayName
ON dbo.Customers (DisplayName);
~~~

**Không chạy ngay trên bảng lớn mà chưa đánh giá locks/IO/plan**. Với Azure SQL, xem **Query Store**, wait statistics, DTU/vCore/resource utilization và khả năng online/resumable index theo tier/SKU để chọn cách triển khai.

### Không dùng "WITH (ONLINE = ON)" như công thức chung

Các tùy chọn ONLINE/RESUMABLE và giới hạn loại index/operation phụ thuộc engine/tier và yêu cầu thiết kế. Một lệnh hỗ trợ ở môi trường này có thể thất bại ở môi trường khác. Rà kỹ **current Azure SQL documentation + actual SKU** trước khi áp dụng.

### Schema ownership

Nếu Spring Boot dùng **dbo.Customers**, migration runner cần quyền đủ để ALTER schema, nhưng **application runtime user** không nhất thiết được ALTER TABLE. Tách các credentials/roles giúp giảm tác động nếu API bị compromise.

## 21. Data backfill và thay đổi semantics

Thay đổi **display_name** chỉ là một ví dụ đơn giản. Data migrations thực có thể:

- Chuyển **money** từ floating point sang **DECIMAL/NUMERIC**.
- Chuẩn hóa timezone từ local time sang UTC.
- Tách **address** thành các trường cấu trúc.
- Đổi enum trạng thái, hợp nhất status cũ.
- Bổ sung **tenant_id** để phân vùng/multi-tenant.
- Migrate dữ liệu qua hai database/storage services.

### Không chỉ cần SQL chạy được

Với tiền tệ:

~~~text
Old: total_amount_float = 19.999999
New: total_amount_minor_units = 2000
~~~

Cần định nghĩa **rounding mode, currency exponent, legal/accounting rule**, reconcile và các ngoại lệ. Một migration **CAST(...)** không đủ để chứng minh số tiền đúng.

### Dữ liệu mới trong lúc backfill

Giả sử backfill 1 triệu rows trong 30 phút, ứng dụng vẫn tạo records. Phải có cách biết:

- Rows mới có được ghi vào schema mới?
- Rows đã migrate bị writer cũ sửa lại không?
- Cursor có bỏ sót rows insert khi job đang chạy không?
- Trigger/dual-write có gây loops/conflicts không?
- Backfill có đủ retry/monitoring?

**Không xem trạng thái "backfill job completed" là xong nếu không có reconciliation business invariants.**

## 22. Thiết kế backfill job có checkpoint

Một job lý tưởng có:

~~~text
backfill_version = customer-display-name-v1
cursor           = last_committed_customer_id
batch_size       = 1000 (giả định, cần benchmark)
status           = RUNNING / PAUSED / FAILED / DONE
rows_processed   = monotonic counter
rows_updated     = count of successful writes
error_count      = monitored
~~~

### Pseudocode

~~~text
repeat:
  if DB overloaded / maintenance window exceeded:
      pause safely

  begin transaction
      rows = fetch next batch by stable key > cursor
      update rows needing transformation, preserving concurrent writes
      persist committed cursor / counts
  commit

  emit metrics/logs with no sensitive payload
until no more eligible rows

re-run reconciliation over full eligible population
~~~

**Lưu cursor và update dữ liệu trong cùng transaction** khi cùng database và thiết kế cho phép, tránh trường hợp cursor đi trước write. Nếu chạy qua nhiều services, phải áp idempotency/saga/checkpoints riêng.

### Batch lớn hay nhỏ?

Batch lớn giảm overhead nhưng tăng lock time, WAL/log pressure và khả năng rollback tốn thời gian. Batch nhỏ giảm contention nhưng tốn nhiều round-trips; chọn theo **lock waits, replication lag, CPU/IO, latency SLO** trong staging/load rehearsal.

## 23. Constraints NOT NULL, UNIQUE và foreign keys

Thêm constraint ngay khi triển khai có thể làm dữ liệu cũ hoặc ứng dụng cũ thất bại.

### Phased NOT NULL

1. Expand: thêm nullable column.
2. Writers mới bắt đầu ghi trường.
3. Backfill dữ liệu cũ.
4. Verify count missing=0 và application logic.
5. Ngăn writers cũ và xác minh rollback window.
6. Thêm constraint NOT NULL theo cách hỗ trợ/ít lock nhất của engine.

### Phased UNIQUE

Nếu thêm unique index mới, phải kiểm tra duplicates trước:

~~~sql
-- PostgreSQL minh họa:
SELECT lower(email) AS normalized_email, COUNT(*) AS n
FROM customers
GROUP BY lower(email)
HAVING COUNT(*) > 1;
~~~

Cần quyết định **normalization/collation/case sensitivity** theo nghiệp vụ trước khi tạo unique constraint/index. Đừng âm thầm xóa một trong hai customers chỉ để migration đi qua.

### Foreign keys và referential integrity

Nếu constraint mới yêu cầu mọi row tham chiếu đều tồn tại, phải xác minh data. Các engine có cơ chế constraint validation/deferral khác nhau. Thêm foreign key không đơn giản là một câu lệnh vô hại trên bảng hàng trăm triệu rows.

## 24. Migration script và chuỗi cung ứng phần mềm

Migration SQL có **quyền thay đổi dữ liệu production**, nên phải quản trị như một release artifact có rủi ro cao.

~~~text
Git commit
  |
  +-- Spring Boot application source
  +-- Migration SQL / changelog
  +-- Contract tests / verification queries
  +-- Deployment manifests / IaC
  |
  v
CI: tests + code review + policy checks
  |
  v
Immutable release artifact(s)
  |
  v
Approved migration runner + application rollout
~~~

### Điều cần kiểm soát

- PR review bởi app owner và database owner cho destructive DDL.
- Không sửa migration file đã apply; tạo version mới.
- **Checksums/manifest** giúp xác minh scripts đúng commit.
- SAST/secret scan; không chứa connection strings/password.
- Artifact provenance và identity của pipeline.
- **Migration history** được backup/audit, không sửa tùy tiện.
- Không cho mọi developer tự chạy **db owner** trên production.

### Một kiểm soát quan trọng

CI đã build app commit **ABC** nhưng migration job lại checkout nhánh **main** tại thời điểm sau đó: có thể chạy script của commit **DEF**. Kết quả là **schema và app lệch phiên bản dù pipeline đều xanh**. Cần **pin chung commit SHA/release manifest** cho migration artifact và application artifact.

## 25. Release manifest: kết nối code, schema và dữ liệu

Một **release manifest** có thể lưu:

~~~yaml
# Minh họa mô tả release; không phải schema deploy trực tiếp.
release: orders-2026-11-20-r3
gitCommit: abcdef0123456789
app:
  image: myregistry.azurecr.io/orders-api
  digest: sha256:REPLACE_WITH_VERIFIED_DIGEST
database:
  engine: postgresql
  migrationTool: flyway
  expandThrough: V2026112001
  backfillJob: customer-display-name-v1
  contractDeferred: true
compatibility:
  oldApp: orders-api-1.8
  newApp: orders-api-1.9
environment: staging
approvedBy: RELEASE_APPROVER_PLACEHOLDER
~~~

Các giá trị chỉ minh họa. **Digest phải là digest thật đã build/scanned**, không phải placeholder khi production. Manifest cần phân quyền sửa và version control, lưu link artifacts/CI run/approval để truy ngược.

### Một artifact, nhiều môi trường

~~~text
Commit ABC
  |
  +-- orders-api image digest D1
  +-- migration package checksum M1
          |
          +--> dev deploy D1/M1
          +--> staging deploy D1/M1
          +--> production deploy D1/M1 sau approval
~~~

Tách **configuration/identities/database endpoints** theo môi trường, nhưng không rebuild source ở mỗi environment nếu muốn dùng cùng binary đã được test.

### Configuration drift

Staging có cột đã được admin tạo thủ công, production chưa có. Flyway history và schema có thể không giống nhau dù dùng cùng manifest. Trước deploy cần **migration validate, schema drift detection và inventory**; không dựa chỉ vào tên environment.

## 26. Pipeline deployment theo thứ tự an toàn

Một pipeline chất lượng cần có các gates:

~~~mermaid
flowchart TD
    A[PR reviewed + commit pinned] --> B[Build, unit, integration tests]
    B --> C[Package app + migrations + SBOM]
    C --> D[Migration lint + compatibility tests]
    D --> E[Apply expand to staging clone/test DB]
    E --> F[Deploy both old/new apps, run mixed-version tests]
    F --> G[Load test + lock/latency assessment]
    G --> H{Security/DB owner approval}
    H -- Rejected --> STOP[Do not touch production]
    H -- Approved --> I[Preflight production/backup readiness]
    I --> J[One-shot expand migration]
    J --> K{Schema history and invariants PASS?}
    K -- No --> FIX[Stop app rollout + investigate]
    K -- Yes --> L[Canary new app]
    L --> M{SLO and business metrics PASS?}
    M -- No --> RB[Roll back app if schema remains compatible]
    M -- Yes --> N[Complete rollout + observe]
    N --> O[Backfill / reconcile / later contract]
~~~

### Thứ tự không phải bất biến

Một số release cần deploy **bridge application** trước migration, ví dụ trước tiên loại code sử dụng cột legacy rồi mới contract. Vì thế pipeline phải chọn **thứ tự dựa compatibility matrix**, không dùng "migrate always first" với mọi loại thay đổi.

### Approval thật sự cho phép gì?

Approval cần xác nhận **SQL diff, estimate lock/IO, target database/resource IDs, backup restore readiness, change window, owner và rollback/roll-forward plan**. Nút approve không làm một migration destructive trở nên an toàn nếu thiếu dữ liệu.

## 27. GitHub Actions: cấu trúc jobs và environments

GitHub Actions có thể tách:

~~~text
build-and-test
       |
       v
staging-migration-rehearsal
       |
       v
production-migration (environment approval)
       |
       v
deploy-application-canary
       |
       v
post-deploy-verify
~~~

Ví dụ **khung workflow mang tính giáo dục**, chưa là pipeline chạy được nguyên trạng:

~~~yaml
name: orders-release
on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and test
        run: ./mvnw -B clean verify
      # Build/push immutable image and migration artifact:
      # cần action/script được review, scan và digest.

  migrate-production:
    needs: build
    environment: production-database
    runs-on: [self-hosted, linux, db-migration-runner]
    steps:
      - uses: actions/checkout@v4
      - name: Authenticate Azure via federated identity
        uses: azure/login@v2
        with:
          client-id: PLACEHOLDER_CLIENT_ID
          tenant-id: PLACEHOLDER_TENANT_ID
          subscription-id: PLACEHOLDER_SUBSCRIPTION_ID
      - name: Verify approved migration artifact and run migration
        run: |
          echo "REPLACE WITH REVIEWED RUNNER COMMAND"
          exit 1

  deploy-application:
    needs: migrate-production
    runs-on: ubuntu-latest
    steps:
      - name: Deploy verified image to canary
        run: |
          echo "REPLACE WITH APPROVED DEPLOY SCRIPT"
          exit 1
~~~

**Workflow cố ý fail** ở các placeholder để không bị nhầm là release production sẵn dùng. Cần pin actions version/SHA theo chính sách, kiểm soát GitHub environments approvals, concurrency/release lock, artifact promotion/digest, Azure RBAC, log redaction, private networking và scripts. Self-hosted runner label chỉ là ví dụ; phải có runner được đội platform quản lý.

### OIDC không tự cấp quyền SQL

GitHub Actions đăng nhập Azure qua **federated credential/OIDC** có thể dùng Microsoft Entra identity để thao tác control plane phù hợp. Nhưng **đăng nhập az login không tự biến JDBC connection thành database principal có ALTER TABLE**.

Để migrate DB, phải cấu hình một đường **data-plane authentication** được engine/driver/tool hỗ trợ (Entra token auth cho Azure SQL/PostgreSQL nếu có, hoặc credential ngắn hạn/secret từ Key Vault), rồi cấp **schema permissions tối thiểu**. Không ghi database password trực tiếp vào workflow YAML, environment output hoặc logs.

## 28. Azure Pipelines: stages và service connections

Trong **Azure DevOps Pipelines**, ý tưởng tương tự:

~~~text
Stage 1: Build
  -> tests, SBOM, artifact + image digest

Stage 2: Deploy to Staging
  -> run migrations on test/clone database
  -> deploy mixed-version apps + verify

Stage 3: Production DB Change
  -> environment approvals/checks
  -> run migration once, collect history/invariants

Stage 4: Production App Rollout
  -> canary/slot/revision/rolling update
  -> post-deployment gates, monitor
~~~

### Những cấu phần

- **Service connection** có workload identity/federation nếu được hỗ trợ.
- **Approvals and checks** cho environment production.
- **Variable groups/Key Vault integration** để lấy cấu hình không đưa secrets vào YAML.
- **Secure agents** có network tới private database.
- **Artifacts** với checksums từ cùng commit/release run.
- **Stage conditions** để chặn app deploy khi migration fail.
- **Audit records** cho người phê duyệt và thời điểm thay đổi.

Không coi **service connection có quyền Contributor** là đủ để chạy migration. Quyền Azure control-plane và quyền **database schema/data plane** là hai cơ chế khác nhau.

### Kiểm soát đồng thời

Cho dù pipeline có approvals, hai người có thể bấm deploy hai releases cùng lúc. Dùng **deployment concurrency control** ở environment/resource và migration tool lock. Nếu R3 và R4 cùng chạy, thứ tự scripts và app versions có thể xen kẽ nguy hiểm.

## 29. Migration runner ở private network

Nhiều Azure Database for PostgreSQL/Azure SQL instances được cấu hình với **private access/private endpoints**. Một runner trên GitHub-hosted public agent có thể **không kết nối được**, ngay cả khi pipeline đã đăng nhập Azure thành công.

~~~text
GitHub / Azure DevOps control plane
            |
            v
Secure self-hosted runner / approved Azure job
  trong VNet hoặc network có đường đi hợp lệ
            |
            +-- Private DNS resolution
            +-- TLS to database endpoint
            +-- Entra/DB auth with schema permission
            |
            v
     Azure PostgreSQL / Azure SQL
~~~

### Các phép kiểm tra

1. DNS từ **runner host thực**, không chỉ laptop operator.
2. Route/firewall/NSG/private endpoint/port tới database.
3. TLS hostname validation và CA chain.
4. Principal được phép **CONNECT, ALTER** phạm vi schema cần thiết.
5. Secrets/token chưa hết hạn khi migration chạy dài.
6. Database có capacity và không vào maintenance/failover.
7. Runner egress tới Azure control-plane/registry/telemetry khi cần.

**Không mở database public access 0.0.0.0/0 để sửa lỗi kết nối của pipeline.** Thay bằng network placement/identity đúng và phê duyệt security.

## 30. Phân tách quyền migration và runtime

Trong production nên có ít nhất hai identity:

| Principal | Nhiệm vụ | Quyền |
|---|---|---|
| **Migration runner** | Apply schema changes | DDL quyền phù hợp trên schema/table được phép |
| **Runtime Spring Boot** | Đọc/ghi nghiệp vụ | SELECT/INSERT/UPDATE/DELETE hoặc stored procedure permissions cần thiết |
| **Backfill job** khi tách riêng | Cập nhật dữ liệu lịch sử | Chỉ các bảng/operations cần cho backfill |
| **CI build job** | Build/test/scan artifacts | Không cần quyền database production |
| **Operator/reviewer** | Review/approve, audit | Không mặc định quyền data write/DDL |

### Vì sao không cấp dbo/owner cho runtime?

Nếu REST API bị khai thác, principal có quyền DDL có thể **DROP TABLE/ALTER SCHEMA**. Least privilege giảm blast radius. Tuy nhiên migrations cần quản lý ownership và grants của objects mới, tránh runner tạo bảng mà runtime không truy cập được.

### Entra ID và database authentication

Azure SQL Database và Azure Database for PostgreSQL – Flexible Server có các khả năng Microsoft Entra authentication phù hợp cấu hình; cách kết nối/JDBC/token và role mapping khác nhau. **Không coi managed identity tự động là database user**. Cần:

- Cấu hình database Entra administrator/authentication feature theo policy.
- Tạo/mapping database principal hoặc role đúng.
- Chỉ cấp quyền DDL/DML cần thiết.
- Kiểm tra lifetime/refresh của access token.
- Xác minh thư viện JDBC/Flyway/Liquibase hỗ trợ cách token được đưa vào connection.

Nếu phải dùng database password cho một runner, lưu trong secret store, truy cập có kiểm soát, rotate và không in vào CI logs.

## 31. Preflight trước khi production migration

Một lệnh SQL đúng về mặt cú pháp vẫn có thể hỏng do environment sai. Preflight cần xác nhận:

~~~text
Release ID / Git SHA / artifact checksum
Target subscription + resource group + server + database
Engine/version/service tier
Migration history + checksum + expected prior version
Database size / target table row count
Long-running transactions / lock wait risk
Backup/PITR/restore capability
Replication/HA state and maintenance events
Expected peak traffic and quiet window
Owner/approver + change ticket
Stop conditions / rollback or roll-forward runbook
~~~

**Không in database password hoặc token vào preflight report.** Xác định target bằng resource ID/server/database identity rõ ràng; không chỉ nhìn một hostname alias dễ trỏ nhầm staging/prod.

### Schema history fail = stop

Nếu Flyway validate báo checksum mismatch, missing migration hoặc database đã apply version mới hơn artifact, dừng và điều tra **drift/version mismatch**. Không chạy **repair** tự động chỉ để tiếp tục deployment; repair có thể hợp thức hóa trạng thái sai nếu chưa đánh giá.

### Capacity gate

Nếu Azure SQL/PostgreSQL đang có CPU/IO bão hòa, long transactions hoặc replication lag cao, migration nặng có thể vượt downtime budget. Có thể hoãn release hoặc tách thao tác theo pha thay vì ép qua do đã có approval.

## 32. Backup, PITR và thử restore

Các dịch vụ Azure SQL/PostgreSQL managed có cơ chế backup/PITR theo policy/service tier, nhưng **thời hạn retention, khả năng restore, RPO/RTO và thao tác restore thực tế khác nhau**.

### Trước một destructive migration

1. Xác nhận backup policy/retention còn hiệu lực.
2. Ghi mốc thời gian/snapshot/restore point theo cơ chế dịch vụ hỗ trợ.
3. **Thử restore vào môi trường cô lập** và đo thời gian.
4. Kiểm tra restored database có schema/data/permissions cần thiết.
5. Xác định ứng dụng sẽ trỏ vào restored database bằng cách nào.
6. Tính dữ liệu **mới ghi sau restore point** sẽ bị xử lý ra sao.

### Vì sao PITR không phải rollback schema đơn giản?

Nếu migration bắt đầu 10:00 và ứng dụng nhận 500 đơn hàng lúc 10:01–10:15, phục hồi database về 09:59 có thể **mất những đơn hàng mới** trừ khi có cách replay/reconciliation an toàn.

~~~text
09:59  Restore point
10:00  DDL migration
10:01  New order #A created
10:15  Migration incident

PITR to 09:59:
  -> schema cũ có thể trở lại
  -> order #A không tự xuất hiện trong DB restored
~~~

Vì thế, lựa chọn **roll forward** hoặc rollback app trên schema vẫn tương thích thường an toàn hơn **PITR toàn database** khi vẫn có traffic ghi, tùy loại lỗi. PITR là công cụ **disaster recovery**, không phải nút undo release miễn phí.

## 33. Rollback code, rollback schema và roll forward

| Phương án | Có thể dùng khi | Rủi ro |
|---|---|---|
| **Rollback application** | Schema đã expand còn tương thích với app cũ | App cũ có hiểu dữ liệu/status mới không? |
| **Roll forward database** | Có thể sửa lỗi bằng migration tiếp theo | Cần test và biết partial state |
| **Rollback migration script** | Có inverse an toàn, ít/nil data loss và đã test | Không bảo đảm mọi DDL đảo ngược |
| **PITR/restore** | Mất dữ liệu/corruption nghiêm trọng, cần DR | Mất ghi mới, thời gian downtime/replay |
| **Pause feature flag** | Tính năng mới là nguồn lỗi nhưng schema vẫn tương thích | Feature flag có chặn write path thật không? |

### Nguyên tắc

- **Không tự động DROP COLUMN** chỉ vì app rollback về version cũ.
- Nếu expand thêm cột nullable và v2 lỗi, thường có thể rollback **chỉ app** về v1, giữ schema expand.
- Nếu migration đã xóa cột cũ, rollback app v1 thường **không an toàn**.
- Nếu dữ liệu đã đổi semantics, phải tính **forward/backward data transformations**, không chỉ DDL.

### Roll-forward fix

Ví dụ migration tạo index sai nhưng chưa thay app behavior, có thể tạo version mới sửa index theo safe procedure. Không tự sửa Flyway version đã apply và rerun trên production vì có thể gây checksum mismatch/drift.

## 34. Feature flags và canary ứng dụng

**Feature flag** tách hành động deploy code khỏi hành động bắt đầu sử dụng schema mới:

~~~text
Database: S1 + display_name nullable
orders-api v1.9: code biết cả customer_name/display_name
Feature flag use_display_name_reads = false
          |
          v
Backfill + reconciliation
          |
          v
Flag enabled for 1% / internal tenants
          |
          v
Observe errors/data consistency
          |
          v
Gradually enable for all
~~~

### Điều kiện flag an toàn

- Có default fail-safe.
- Flag changes được audit và có owner.
- Old/new app paths xử lý cả trạng thái data chưa backfill.
- Không để toggle đọc field mới khi writer chưa đồng bộ.
- Có kill switch thực sự ngăn **risky writes**, không chỉ che UI.
- Không dùng client-side flag thay server-side authorization.

### Đừng contract chỉ vì flag bật 100%

Rollback window, delayed queues, offline workers, scheduled reports và BI/ETL consumers vẫn có thể dùng schema cũ. Cần inventory code/database access trước destructive migration.

## 35. Post-deployment verification

Một release không hoàn thành khi CI job trả **exit 0**. Sau migration và rollout:

1. Kiểm tra **Flyway/Liquibase schema history** và checksums mong đợi.
2. Kiểm tra cột/bảng/index/constraints đúng engine schema.
3. Xác minh app instances **Ready/healthy**, đúng image digest/release.
4. Smoke test một **read** và một **write** với synthetic/test tenant có quyền.
5. Kiểm tra **data invariants**: missing/mismatch/duplicate counts.
6. Theo dõi DB **CPU, IO, storage, locks, connections, replication lag**.
7. Theo dõi app **5xx, p95/p99, SQL exceptions, retry count, queue age**.
8. Xem logs/alerts trong cửa sổ sau deploy để phát hiện regression.
9. Xác nhận business owners chấp nhận kết quả.
10. Ghi release evidence và điều kiện chuyển pha contract.

### Nếu chỉ có read smoke test

App có thể **SELECT** schema mới thành công nhưng **INSERT** từ worker cũ thất bại vì NOT NULL constraint hoặc default sai. Test phải có cả **old and new writers/readers**, kể cả background jobs và endpoints ít traffic.

### Post-deploy gates

Đặt thresholds theo baseline/SLO thực, không tự suy ra "không lỗi" từ 1 phút chưa có traffic. Với hệ thống ít requests, dùng synthetic transactions có kiểm soát để tăng độ tin cậy.

## 36. App Service: deployment slots và schema dùng chung

**Azure App Service deployment slots** có thể hỗ trợ kiểm thử rồi swap app version, nhưng **slot swap không tạo bản database tương ứng**.

~~~text
Before:
  Slot production: orders-api v1 ─┐
                                  ├── Azure Database S1
  Slot staging:    orders-api v2 ──┘

After expand S2 (backward-compatible):
  Slot production: orders-api v1 ─┐
                                  ├── Azure Database S2
  Slot staging:    orders-api v2 ──┘

Swap:
  Production traffic -> orders-api v2
  Database vẫn là S2, không bị swap
~~~

### Điều kiện an toàn

- Nếu staging slot trỏ **chung production DB**, chỉ cho app mới chạy khi S2 đã expand tương thích; tránh test tạo dữ liệu nghiệp vụ không được phép.
- Nếu staging có **database staging riêng**, smoke test không hoàn toàn chứng minh app v2 hoạt động với production shared DB; vẫn cần xác nhận schema/version.
- Slot-specific settings và Key Vault references phải được đánh dấu đúng theo chính sách của App Service.
- **Swap warm-up/Health Check** không thay thế database migration gate.
- Nếu cần rollback slot sau lỗi v2, S2 vẫn phải tương thích với v1.

### Anti-pattern

~~~text
Slot swap v2 to production
  -> v2 starts
  -> Flyway auto-runs DROP COLUMN
  -> v1 staging slot cannot query old field
  -> Rollback slot fails
~~~

Vì vậy, dùng **expand migration trước canary/swap**, giữ destructive contract riêng và tránh migration DDL tự chạy vô kiểm soát ở mỗi Web App instance.

## 37. Azure Container Apps: revisions cùng đọc một database

**Azure Container Apps (ACA)** có **revisions** và traffic splitting theo chế độ/tính năng. Nhưng nhiều revisions vẫn có thể trỏ cùng Azure PostgreSQL/Azure SQL.

~~~text
Ingress
  |
  +-- 90% -> revision v1 -> DB S2
  |
  +-- 10% -> revision v2 -> DB S2
~~~

### Bốn câu hỏi trước canary

1. S2 có phục vụ v1 và v2?
2. v2 có ghi dữ liệu mà v1 không hiểu không?
3. Background workers chạy từ **revision v1** còn active không?
4. Backfill/contract có chạy ngoài lifecycle replicas không?

### ACA Job cho migration

Nếu tổ chức chọn **Container Apps Job** làm runner, cấu hình một job hữu hạn với image chứa migration scripts/CLI, quyền DB phù hợp và network environment truy cập được DB.

~~~text
CI/CD:
  1. Trigger one-shot migration job
  2. Wait for completed state AND verify schema history
  3. Deploy revision v2
  4. Canary + monitor
  5. Complete rollout or rollback traffic
~~~

**Một job tự động scale hoặc retry không bảo đảm script idempotent**; cần Flyway/Liquibase history và stop conditions. Giới hạn executions/concurrency của job, chỉ chạy khi release approver xác nhận.

### Không sử dụng scale-to-zero như migration locking

ACA API có thể scale replicas về 0 và bật lên khi request tới. Điều đó không liên quan đến tính đúng đắn của schema migration. **Một instance mới không được phép tự chạy ALTER TABLE chỉ vì nó vừa cold start**, nếu migration ownership thuộc CI/CD runner.

## 38. AKS: một migration Job và Deployment riêng

**AKS** có Kubernetes **Job** cho tác vụ hữu hạn và **Deployment** cho Spring Boot API dài hạn.

~~~mermaid
flowchart TD
    CI[Approved release pipeline] --> J[Kubernetes Job: migrate-schema]
    J --> D[(Azure PostgreSQL S2)]
    J --> V{History and invariants validated?}
    V -- No --> S[Stop rollout]
    V -- Yes --> DEP[Deployment: orders-api v2]
    DEP --> C[Canary / readiness checks]
    C --> M[Monitor / promote or roll back app]
~~~

Ví dụ **Kubernetes Job skeleton**:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-schema-expand-r3
  namespace: orders-production
  labels:
    release: r3
spec:
  parallelism: 1
  completions: 1
  backoffLimit: 0
  activeDeadlineSeconds: 900
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: orders-db-migrator
      containers:
        - name: migrate
          image: myregistry.azurecr.io/orders-migration@sha256:REPLACE
          args: ["migrate"]
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "1024Mi"
~~~

**Chưa phải manifest production deployable.** Phải thay digest thật và xác nhận image entrypoint/args, workload identity/secret mounting, database connectivity, namespace permissions, job security context, resource sizing, timeout và observability. Ví dụ cố ý để **backoffLimit: 0** nhằm yêu cầu operator đánh giá partial state trước retry; không phải tất cả migrations đều nên zero retries.

### Đừng dựa chỉ vào Job Succeeded

Job có thể exit 0 sau khi chạy shell script không kiểm tra SQL error code. Kiểm chứng **schema history, số records đổi, constraints/index status và smoke test** bằng bước CI riêng. Khi migration fail, pipeline **không được tiếp tục rollout**.

### Helm hooks có rủi ro

Helm pre-upgrade hooks có thể khởi chạy Job migration, nhưng hook ordering/rollback/job cleanup có những semantics riêng. Nếu Helm release rollback, **database schema không tự đảo ngược**. Khi có migration nặng và nhiều teams, orchestration bằng pipeline riêng thường minh bạch hơn.

## 39. Azure Functions và background workers

Một Spring Boot API có thể đồng tồn tại với **Azure Functions Java**, Service Bus workers hoặc AKS CronJobs.

~~~text
orders-api v1/v2 -> Azure PostgreSQL S2
        |
        +-- Service Bus queue with old/new messages
                 |
                 +-- invoice-worker v1
                 +-- invoice-worker v2
                 +-- Azure Function consumer
~~~

### Rủi ro ít ai để ý

Khi API v2 đã triển khai xong, **workers v1** có thể còn xử lý messages đã enqueue hàng giờ hoặc vài ngày trước. Nếu migration contract xóa cột mà worker v1 dùng, worker có thể thất bại dù tất cả HTTP requests mới đều thành công.

### Checklist consumers

- Có inventory **all readers/writers** dùng database không?
- Mỗi worker version còn deploy ở đâu?
- Queue retention/dead-letter/replay có mang event schema cũ?
- Có scheduled reports/ETL jobs tuần/tháng?
- Function triggers có retries và delayed execution?
- Có BI dashboards, ad hoc queries hoặc integration partners không?

**"Tất cả API pods đều v2" chưa đủ để contract cột.** Cần chứng cứ các consumers cũ đã bị ngừng hoặc chuyển sang path mới.

## 40. Nhiều microservices dùng chung schema

Nếu **orders-api**, **billing-api** và **reporting-worker** cùng truy cập bảng customers, một migration của orders-api có thể làm billing-api lỗi.

~~~text
orders-api v2 ---------+
billing-api v1 --------+-- shared customers table
reporting-worker v1 ---+
~~~

### Rủi ro ownership

- Hai teams có thể tạo migrations thay đổi cùng table.
- Flyway histories riêng nhưng ownership của schema không rõ.
- Một service tạo constraint khiến inserts của service khác fail.
- Không biết service nào được phép chạy destructive DDL.

### Thiết kế giảm rủi ro

1. Chỉ định **schema owner/data contract owner**.
2. Có migration repository hoặc release gate chung khi chia schema.
3. Public API/events thay shared table access khi khả thi.
4. Contract tests cho mọi consumers.
5. Không để hai pipelines độc lập cùng chạy DDL mà không coordination.
6. Nếu cần tách database, thiết kế data replication/outbox và consistency policy.

**Microservices không tự động đồng nghĩa mỗi service có database riêng**, nhưng chia sẻ schema làm deployment independence kém hơn, cần kiểm soát rõ.

## 41. Test matrix cho hai app versions và hai schema states

Trước release v2, tối thiểu phải kiểm tra:

| Application | Schema S1 | Schema S2 expand | Schema S3 contract |
|---|---|---|---|
| **v1** | PASS cần có | **PASS bắt buộc** khi rolling/rollback | FAIL có thể chấp nhận chỉ sau khi v1 retired |
| **v2 chuyển tiếp** | Có thể FAIL nếu yêu cầu cột mới | **PASS bắt buộc** | PASS nếu code không còn dùng legacy field |
| **v3 chỉ dùng mới** | FAIL | PASS | **PASS bắt buộc** |
| **Worker v1** | PASS | **PASS bắt buộc** nếu worker còn chạy | FAIL chỉ khi worker đã retired |

Đây là **matrix thiết kế mẫu**; kết quả cụ thể phụ thuộc code. Quan trọng là ghi rõ điều kiện **bắt buộc PASS** tại từng bước.

### Kiểm tra cả read và write

Không chỉ test **GET /customers**. Cần test:

- Tạo customer từ writer v1 và đọc bằng reader v2.
- Tạo customer từ writer v2 và đọc bằng reader v1.
- Update cùng row từ hai versions trong phạm vi business cho phép.
- Transaction rollback/idempotency khi code bị restart giữa chừng.
- Report/ETL query dùng legacy field.
- Null/default/constraint behavior cho data chưa backfill.

### Data migration phải có canary data

Sử dụng test rows đại diện: Unicode/Vietnamese names, NULLs, long strings, duplicate normalized values, large transactions, timezone/currency edge cases. Không dùng bản sao production chứa PII nếu chưa được phép và xử lý bảo vệ dữ liệu đúng quy định.

## 42. Integration tests và rehearsal bằng database thật

**H2 in-memory database** có thể tiện cho unit tests nhưng khác PostgreSQL/Azure SQL về SQL grammar, constraints, transactions, collations và locking.

### Mức test

| Mức | Mục đích | Môi trường |
|---|---|---|
| Unit tests | Business functions, DTO mappings | JVM/mock |
| Migration syntax tests | Chạy scripts theo thứ tự | Test DB cùng engine |
| Schema compatibility tests | v1/v2 read/write trên S2 | Integration environment |
| Data backfill tests | Checkpoint/restart/reconcile | Synthetic representative data |
| Load/locking tests | DDL và backfill ảnh hưởng tới requests | Staging gần production |
| Restore rehearsal | Đo RTO và data recovery | DB clone/isolated restore |
| Canary production | Xác minh SLO trên traffic ít | Approved production rollout |

### Testcontainers

Với Spring Boot/JUnit, **Testcontainers PostgreSQL** có thể giúp chạy PostgreSQL container trong CI thay H2, cung cấp engine behavior thực hơn cho SQL migrations. Tuy nhiên nó **không sao chép** Azure network, service tier, HA, table size hoặc concurrent production load; vẫn phải có staging rehearsal.

### Mẫu câu hỏi test

- Migration **fresh install** chạy từ 0 tới latest có pass?
- Migration **upgrade** từ schema trước đó lên latest có pass?
- App v1 có chạy trên S2?
- App v2 có đọc dữ liệu S1 còn sót sau expand?
- Backfill chạy lại sau kill có đếm/ghi trùng?
- Có thể rollback app v2 về v1 mà không mất dữ liệu?
- DDL có chặn requests quá downtime SLO?

## 43. Locking, query latency và quá tải database

Một migration thành công nhưng làm p95 API tăng từ 100 ms lên 12 giây vẫn là **sự cố chất lượng dịch vụ**.

### Các nguyên nhân

- DDL chờ/giữ lock, chặn transactions.
- Index rebuild/creation gây CPU/IO pressure.
- Data backfill sinh lượng lớn WAL/transaction log.
- Autovacuum/maintenance/index statistics thay đổi.
- Connection pool chờ vì database hết connections.
- Read replicas bị replication lag.
- Query plan thay đổi sau khi có index/constraint/schema.

### PostgreSQL query điều tra lock (chạy theo quyền phù hợp)

~~~sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_start,
    LEFT(a.query, 120) AS query_sample
FROM pg_stat_activity a
WHERE a.datname = current_database()
ORDER BY a.query_start NULLS LAST;
~~~

**Không chia sẻ raw query_sample nếu chứa dữ liệu nhạy cảm**. SQL được phép đọc từ pg_stat_activity tùy role; không tự ý terminate các backend khác khi chưa có incident owner cho phép.

### Thước đo stop condition

Ví dụ thiết kế:

~~~text
If p95 latency > approved SLO for sustained window
 OR lock wait exceeds approved threshold
 OR database CPU/IO saturation persists
 OR replica lag exceeds permitted budget:
    pause backfill / stop new migration stages
    escalate to DB/application owner
~~~

Threshold phải dựa trên workload thật, không tự mặc định một con số cho tất cả deployments. **Không thể ngắt tùy tiện một DDL đang chạy** mà chưa hiểu rollback/partial state của engine.

## 44. Cấu trúc versioning giữa schema và event contracts

Ứng dụng mới có thể ghi dữ liệu trong database S2 rồi phát event **order.v2**, trong khi worker cũ chỉ hiểu **order.v1**.

~~~text
orders-api v1 + DB S1 -> event order.v1 -> worker v1

Expand DB S2
orders-api v2 -> event order.v1 + optional v2 fields
             -> worker v1/v2 cùng đọc trong giai đoạn chuyển tiếp

Sau consumer migration:
orders-api v3 -> event order.v2 -> worker v2
~~~

### Không phát event incompatible ngay trong cùng migration

Database schema và event schema thuộc **hai contract khác nhau**. Khi API v2 dùng display_name mới, event consumer v1 có thể không hiểu trường bắt buộc mới hoặc ý nghĩa status mới. Giải pháp:

- Thêm trường **optional** trước và giữ trường legacy khi cần.
- Version event schema rõ ràng, cho consumer chấp nhận unknown fields khi thích hợp.
- Dùng **schema compatibility tests** và delayed-message replay test.
- Không xóa code đọc event cũ trước khi queue/DLQ/backup retention hết hoặc có chuyển đổi.
- Dùng outbox để liên kết database commit với event publish khi nghiệp vụ cần.

**Flyway migration thành công không chứng minh Service Bus worker tương thích.** Cần phối hợp release across DB, API, messages và consumers.

## 45. Flyway runner: migration, validate và info

Khi sử dụng Flyway CLI hoặc Maven plugin được cấu hình, quy trình thường có:

~~~text
validate -> info -> approved migrate -> info -> verify invariants
~~~

Ví dụ **các lệnh minh họa trong sandbox** với Flyway CLI đã cài và config qua môi trường:

~~~bash
# Chỉ chạy trên DB sandbox; các biến nên được inject an toàn.
flyway -locations=filesystem:./db/migration validate
flyway -locations=filesystem:./db/migration info
flyway -locations=filesystem:./db/migration migrate
flyway -locations=filesystem:./db/migration info
~~~

**Lệnh chỉ chạy được nếu Flyway CLI được cài, đã nhận đúng JDBC URL, driver, user/auth và config**, đồng thời đường dẫn db/migration tồn tại. Dữ liệu trong ví dụ lesson không có quyền tự động triển khai. Trong production, migration runner phải lấy package **đã build từ commit/digest được duyệt**, không checkout nhánh không cố định; có secret injection, private DNS và gate.

### Những điều cần tránh

- Không in password/JDBC URL kèm tokens trong CI logs.
- Không dùng **flyway clean** trên production.
- Không chạy **repair** tự động sau checksum mismatch khi chưa điều tra.
- Không nhầm **validate successful** với **schema/data compatibility verified**.
- Không chạy **migrate** khi đang có migration job khác hoạt động mà không biết tool lock.

### Khi cần dùng Maven Flyway plugin

Có thể dùng **mvn flyway:validate/info/migrate** khi plugin được cấu hình đúng; đừng cho rằng vì project đã có **flyway-core** thì Maven plugin goal chắc chắn sẵn sàng. Cần pin plugin và xác định configuration/driver/credentials, test trên sandbox.

## 46. Tình huống A: app mới chạy khi migration chưa hoàn tất

**Bối cảnh:** CI/CD deploy Spring Boot v2 trước; v2 dùng **display_name** qua JPA mapping nhưng database vẫn S1.

### Triệu chứng

- Spring Boot startup báo validation/missing column.
- HTTP requests trả SQL undefined column.
- Các pod mới không Ready/CrashLoopBackOff; old pods vẫn đang chạy.
- Auto-scaler tạo thêm v2 pods, tăng log noise.

### Nguyên nhân

Pipeline thiếu dependency **successful expand migration → deploy v2**, hoặc migration job kết thúc nhưng không xác minh schema thật.

### Hướng xử lý

1. **Dừng rollout v2** nếu chưa làm hỏng data.
2. Kiểm tra DB target identity và migration history.
3. Xem script expand có được apply vào **đúng server/database/schema** không.
4. Nếu v1 vẫn tương thích, tiếp tục phục vụ trên v1.
5. Review/apply expand với approval/lock assessment.
6. Validate schema S2 và chạy mixed-version integration test.
7. Thực hiện canary v2 lại.

### Bài học

**Kubernetes/App Service readiness không tự chạy database migration**. Orchestration phải đảm bảo điều kiện tiên quyết và bước verify, không chỉ sắp xếp hai deployment commands sát nhau.

## 47. Tình huống B: Flyway báo checksum mismatch

**Bối cảnh:** Migration **V16__add_customer_name.sql** đã chạy trên staging/prod. Một developer chỉnh nội dung file đó sau merge và deploy commit mới. Flyway validate báo mismatch.

### Nguyên nhân

Lịch sử production giữ checksum của script đã apply, nhưng artifact mới có nội dung khác.

### Không nên làm

~~~text
Flyway validation failed
  -> Automatically run flyway repair
  -> Retry migrate without reviewing changes
~~~

Repair có thể cập nhật metadata history mà không áp đúng SQL như developer dự định, tạo cảm giác đã đồng bộ trong khi schema không giống source.

### Cách xử lý an toàn

1. Xác minh script đã apply thật từ release artifact/history.
2. So sánh schema/database object hiện có và Git history.
3. Nếu muốn thêm/sửa behavior mới, tạo **migration version tiếp theo**.
4. Nếu checksum mismatch do normalization/rules đã được chấp thuận, theo quy trình đặc biệt có review và audit.
5. Không sửa trực tiếp schema history table để né migration tool.
6. Thêm CI check ngăn chỉnh sửa migrations đã release.

**Migration history là audit record**; thao tác repair cần được ghi rõ trong change ticket.

## 48. Tình huống C: ALTER TABLE bị block bởi transaction lâu

**Bối cảnh:** Migration **ADD COLUMN** trên Azure Database for PostgreSQL không xong sau 2 phút. Trong thời gian đó, một số request chờ lock và p95 API tăng.

### Nguyên nhân có thể

- Có transaction lâu giữ lock không tương thích.
- DDL vào lock queue, khiến các queries khác bị chặn gián tiếp.
- DB thiếu capacity hoặc đang failover/maintenance.
- Migration đang chứa thêm UPDATE/INDEX chứ không chỉ ADD COLUMN.

### Runbook

1. Xác định migration statement hiện tại, start time, lock wait.
2. Xem **pg_stat_activity/pg_locks** và Azure PostgreSQL metrics trong quyền được cấp.
3. Đánh giá application latency, DB CPU/IO và replication lag.
4. Xác định có thể **cancel statement** an toàn theo PostgreSQL transaction semantics không.
5. Nếu cancel, kiểm tra migration history và schema state trước retry.
6. Lên lịch lại khi workload giảm hoặc tách migration thành thao tác nhỏ.
7. Cấu hình lock timeout thích hợp sau benchmark, không tăng timeout tùy tiện.

### Bài học

**DDL metadata nhanh vẫn có thể chặn traffic vì lock acquisition.** Không đo migration chỉ bằng execution time trên database 100 rows ở laptop.

## 49. Tình huống D: backfill 99% nhưng dữ liệu vẫn thiếu

**Bối cảnh:** Backfill hiển thị 99% rows processed, nhưng sau khi bật flag đọc display_name, một số customers hiển thị rỗng.

### Giả thuyết

- Cursor bỏ qua rows được insert/update trong lúc job chạy.
- Worker cũ vẫn ghi customer_name nhưng không ghi display_name.
- Batch thất bại một phần, checkpoint tiến trước commit.
- Logic transform bỏ qua NULL/Unicode/trailing spaces.
- Một số tenant được archive/partition và không nằm trong query.

### Khắc phục

1. **Tắt feature flag read-new** hoặc fallback về legacy trong phạm vi an toàn.
2. Chạy reconciliation theo business invariant, không chỉ xem progress bar.
3. Thống kê missing/mismatched rows theo partition/tenant khi được phép.
4. Kiểm tra writers cũ và concurrent updates.
5. Chạy lại batch idempotent hoặc sửa transform theo version mới.
6. Xác minh **zero/acceptable discrepancies** theo định nghĩa.
7. Mới bật reads theo canary.

### Không dùng COUNT(*) không có scope

Nếu job chỉ áp cho active customers, COUNT(*) toàn bảng có thể báo sai; ngược lại nếu dữ liệu archived vẫn được business report đọc, chỉ check active customers có thể bỏ sót lỗi. Scope của reconciliation phải trùng với scope nghiệp vụ.

## 50. Tình huống E: rollback image nhưng old app vẫn lỗi

**Bối cảnh:** Sau v2 release, đội phát hiện lỗi và rollback ACA revision/AKS Deployment về v1. Nhưng v1 liên tục lỗi **column customer_name does not exist**.

### Nguyên nhân

Pipeline đã chạy migration contract **DROP COLUMN customer_name** ngay cùng lúc v2, làm schema không còn tương thích.

### Phản ứng

- Không tiếp tục lặp rollback image vô nghĩa.
- Dừng risky traffic/write path nếu dữ liệu có nguy cơ sai.
- Xác định schema hiện tại, trạng thái các migrations và dữ liệu bị ảnh hưởng.
- Xem có thể **roll forward v2** với fix cấp tốc/feature flag hay không.
- Nếu phải phục hồi cột, cần kế hoạch rebuild/backfill đúng data semantics; **ADD COLUMN** không tự khôi phục dữ liệu đã drop.
- Chỉ dùng PITR/restore sau phân tích RPO/RTO và dữ liệu mới ghi.
- Sau incident, chuyển policy: **không contract trong cùng release đầu tiên** khi còn rollback về v1.

### Bài học

**Rollback app không rollback DB.** Chính compatibility matrix và contract timing quyết định liệu rollback code còn là phương án hợp lệ.

## 51. Tình huống F: migration ở đúng release nhưng sai database

**Bối cảnh:** Pipeline production sử dụng environment variable từ staging. Migration chạy thành công, nhưng production Spring Boot tiếp tục lỗi thiếu schema, còn staging DB đã có thêm cột.

### Nguyên nhân

Target database được suy ra từ một alias/secret không được xác thực, hoặc release job có quyền rộng trên nhiều DB.

### Cách tránh

1. Gắn environment/database resource IDs vào release manifest.
2. Trước migration, query **current_database/current_schema/server identity** theo engine với quyền phù hợp.
3. Xác minh identity của runner chỉ có quyền ở DB intended.
4. Có environment approvals và log target identity không chứa secrets.
5. Dùng secret scope và network riêng cho staging/prod.
6. Sau migration, so sánh schema history ở target đã khai báo.

**Một migration job exit 0 là bằng chứng đã thực thi trên đâu đó**, không chứng minh đã thay đúng production DB nếu không kiểm chứng target và permissions.

## 52. Bài thực hành end-to-end: migration cùng ứng dụng Spring Boot

### Mục tiêu bài lab

Xây **Orders Lab** bằng **Spring Boot + PostgreSQL** với hai phiên bản:

- **v1:** đọc/ghi **customers.customer_name**.
- **v2 chuyển tiếp:** nhận biết **display_name**, nhưng vẫn phục vụ dữ liệu cũ.
- **Schema S1:** chỉ có customer_name.
- **Schema S2:** có cả customer_name và display_name.
- **Backfill:** chuyển data cũ và xác minh consistency.
- **Pipeline mô phỏng:** build → expand → verify → canary v2 → rollback app → later contract.

Bạn có thể chạy **PostgreSQL container local/Testcontainers** và trình bày deployment manifests Azure. Nếu không có quyền/budget subscription, **không cần tạo Azure SQL/PostgreSQL production**; vẫn đạt mục tiêu bằng mô phỏng release và ADR. Nếu có sandbox Azure, thực hành trên tài nguyên tách biệt, không dùng dữ liệu khách hàng thật.

### Phần A — Tạo schema S1 trong test database

SQL **PostgreSQL**:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO customers (customer_name)
VALUES
  ('Nguyễn An'),
  ('Trần Bình'),
  ('Lê Chi');

SELECT id, customer_name FROM customers ORDER BY id;
~~~

**Dùng test database mới hoặc schema lab trống.** Không chạy CREATE/INSERT trên database đã có customers thật. Khi dùng Flyway, đặt các lệnh vào V1 migration, đừng vừa chạy thủ công vừa cho Flyway tự chạy cùng CREATE TABLE lên một schema chưa quản trị history.

### Phần B — Xây app v1

Spring Boot v1 nên có:

~~~text
GET /customers/{id}
  -> return customer_name

POST /customers
  -> INSERT customer_name

Health endpoint
  -> /actuator/health
~~~

Ví dụ SQL của repository:

~~~sql
SELECT id, customer_name
FROM customers
WHERE id = :id;

INSERT INTO customers (customer_name)
VALUES (:customer_name);
~~~

Sử dụng **prepared statements/JDBC bind parameters** hoặc JPA theo dự án, không nối user input vào SQL. Test v1 đọc cả ba rows và tạo một row test mới.

### Phần C — Tạo migration expand V2

File migration riêng, ví dụ:

~~~text
src/main/resources/db/migration/
  V1__create_customers.sql
  V2__add_display_name.sql
~~~

Nội dung V2:

~~~sql
ALTER TABLE customers
    ADD COLUMN display_name VARCHAR(200);
~~~

Ở pipeline thật, cần bảo đảm **migration artifact từ cùng release**; trong lab có thể để Flyway chạy một lần vào PostgreSQL test.

### Phần D — Chạy Flyway và kiểm tra

Nếu project đã cấu hình Flyway và test DB đúng, trong lab có thể chạy ứng dụng migration runner hoặc Flyway CLI:

~~~bash
# Flyway CLI phải cài và nhận cấu hình JDBC an toàn.
flyway -locations=filesystem:./db/migration validate
flyway -locations=filesystem:./db/migration migrate
flyway -locations=filesystem:./db/migration info
~~~

Sau đó truy vấn:

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'customers'
ORDER BY ordinal_position;

SELECT COUNT(*) AS missing_display_name
FROM customers
WHERE display_name IS NULL;
~~~

**Kỳ vọng:** cột mới tồn tại và ban đầu còn NULL cho rows cũ. **Đây không phải lỗi migration**; schema expand cho phép backfill ở bước sau.

### Phần E — Test app v1 trên S2

Giữ **v1 đang chạy** hoặc chạy lại bộ test v1 trỏ tới S2:

1. GET customer cũ phải thành công.
2. POST customer mới phải thành công dù không gửi display_name.
3. Không có lỗi missing column/NOT NULL từ S2.
4. Kiểm tra schema history vẫn đúng.

Nếu v1 bị lỗi trên S2, **dừng release**: expand chưa tương thích. Không đi tiếp v2 hoặc backfill trước khi sửa nguyên nhân.

### Phần F — Xây app v2 chuyển tiếp

Lựa chọn logic:

~~~java
public String effectiveDisplayName(
        String customerName,
        String displayName) {
    return displayName != null ? displayName : customerName;
}
~~~

Trong app thật, service layer sẽ đọc hai fields từ JPA/JDBC entity. Với writes mới, để duy trì compatibility:

~~~sql
UPDATE customers
SET customer_name = :new_name,
    display_name = :new_name,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id;
~~~

**Đây là SQL minh họa cho cùng một row**. Trong môi trường chạy lẫn v1/v2, có thể tiếp tục để v2 đọc canonical customer_name trước khi v1 writers được retire. Nếu dùng display_name làm read-first sớm, kiểm tra writer v1 có thể làm stale display_name; thiết kế compatibility bridge/trigger hoặc đợi rollout writers v2 hoàn tất.

### Phần G — Backfill và reconciliation

Trên dữ liệu nhỏ của lab:

~~~sql
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL;

SELECT COUNT(*) AS remaining_nulls
FROM customers
WHERE display_name IS NULL;

SELECT COUNT(*) AS mismatches
FROM customers
WHERE display_name <> customer_name;
~~~

**Kỳ vọng trong mô hình tên đồng nhất:** remaining_nulls = 0, mismatches = 0. Với data thật lớn, thay một UPDATE bằng **backfill batches có checkpoint**, kiểm tra concurrent writes và dashboard progress.

### Phần H — Canary và rollback app

Giả lập rollout:

~~~text
Time T0: schema S1, app v1 all replicas
Time T1: schema S2 expand, app v1 all replicas
Time T2: app v1 90%, app v2 10%
Time T3: app v1 50%, app v2 50%
Time T4: app v2 100%
Time T5: simulate app v2 bug -> roll back app to v1 on S2
~~~

Trong từng thời điểm:

- Gửi GET và POST test requests.
- Kiểm tra mọi version còn đọc/ghi đúng.
- Đọc logs SQL exceptions, request 5xx và DB connection errors.
- Kiểm tra rows vừa tạo bởi v1 và v2.
- Quan sát feature flag read path và data consistency.

**Mục tiêu then chốt:** sau bước T5 **v1 vẫn chạy được trên schema S2**, vì migration expand không xóa customer_name.

### Phần I — Kiểm thử failure có kiểm soát

Chỉ trong sandbox:

1. **Kill backfill job** giữa batch, khởi chạy lại, kiểm tra checkpoint/idempotency.
2. **Chạy v2 trước S2** để thấy missing-column behavior và tại sao cần gate.
3. **Sửa một Flyway migration đã apply trong lab** để quan sát checksum mismatch (không sửa production history).
4. **Tạo long transaction trong test DB**, thử DDL có lock timeout phù hợp và quan sát wait.
5. **Chạy deployment song song giả lập** để thấy nhu cầu release concurrency lock.
6. **Dùng wrong test DB target có chủ đích** với principal bị hạn chế, kiểm tra preflight chặn.

Không thực hiện các test lỗi này trên DB dùng chung hoặc production. Nếu fault injection không được cấp quyền, mô tả tabletop runbook với expected outcomes.

### Phần J — Contract muộn

Khi **v1/worker v1** đã retired, rollback window đã qua, các bài kiểm tra no legacy readers/writers đạt, một migration contract *có thể*:

~~~sql
-- PostgreSQL, chỉ dùng test DB/contract release riêng:
ALTER TABLE customers
    DROP COLUMN customer_name;
~~~

Trước DROP, chuyển v2 thành **v3 chỉ dùng display_name**, đảm bảo dữ liệu bắt buộc đã backfill và constraint theo lộ trình riêng. Nếu vẫn cần old field cho reports/BI/rollbacks, **không chạy contract**.

### Phần K — Bằng chứng cần nộp

~~~text
Release ID / commit / app version:
Database engine/version:
Schema S1 -> S2 migration ID/checksum:
Migration runner và quyền:
Schema history before/after:
Old app v1 on S2 result:
New app v2 on S2 result:
Read/write matrix outcomes:
Backfill processed/missing/mismatch counts:
Rollback app v2 -> v1 outcome:
Locks, p95 latency và DB load measurements:
Data backup/restore test summary:
Security: secret exposure NONE:
Cost/cleanup:
Remaining contract preconditions:
~~~

**Không tự bịa các kết quả đo**. Nếu lab chỉ thực hiện local mà chưa triển khai Azure, ghi **local-only / not measured** ở phần platform metrics/production SLO.

### Phần L — Cleanup

- Chỉ xóa **lab database/container/resource group** do mình sở hữu và được phép.
- Không xóa Azure SQL/PostgreSQL dùng chung, backups hoặc migration history production.
- Thu hồi/rotate test credentials nếu phát hiện bị lộ.
- Kiểm tra tài nguyên sandbox còn tính phí: database compute/storage, runner/AKS/ACA job, Log Analytics.
- Giữ lại migration scripts/ADR/CI evidence đã redaction theo chính sách đội.

## 53. Runbook production release và ứng cứu

### Trước change window

| Bước | Bằng chứng | Owner |
|---|---|---|
| Freeze release manifest | Commit/digest/checksum đã duyệt | Release engineer |
| DB preflight | Engine/target, schema history, data size, locks | DBA/DB owner |
| Security approval | Migration principal, network, secret handling | Security/platform |
| Restore rehearsal | RTO, PITR validity, data recovery plan | DB/SRE |
| Compatibility tests | App v1/v2 + S1/S2 matrix | App team |
| Load rehearsal | Lock/IO/latency impact estimate | DBA/SRE |
| Rollback decision tree | App rollback hay roll forward | Incident commander |
| Stakeholder comms | Change ticket, user-impact window | Release owner |

### Trong khi migration

1. Kiểm tra lại **đúng target database, release checksum và principal**.
2. Chặn pipeline phát hành cạnh tranh.
3. Chụp baseline latency, CPU/IO/locks, DB connections và replication lag.
4. Chạy **expand migration một lần** bằng runner được phê duyệt.
5. Thu status/error, kiểm tra **Flyway/Liquibase history** và schema object.
6. Nếu fail: **dừng app rollout ngay**, xác định partial state, không retry mù.
7. Nếu pass: thực hiện canary application rollout.
8. Theo dõi business invariants, old/new version read/write và database health.
9. Tiến hành backfill có giới hạn nếu kế hoạch cho phép.
10. Promote hoặc rollback app theo decision tree; giữ schema expand nếu tương thích.

### Sau release

- Xác nhận observed schema version, app image digest và service versions.
- Chạy synthetic read/write với test tenant được phép.
- Kiểm tra backlog workers/events và delayed messages.
- Ghi dữ liệu backfill/reconciliation, incidents, change duration và SLO.
- Đặt action item và **gate để contract** khi data/consumers đã sạch.
- Theo dõi DB log/WAL/storage growth và chi phí vài chu kỳ sau release.

### Quy trình khi migration bị kẹt

~~~mermaid
flowchart TD
    A[Migration exceeds threshold] --> B[Freeze app rollout]
    B --> C[Check DB locks/CPU/IO and current SQL]
    C --> D{Safe to cancel?}
    D -- Unknown --> E[DB owner decides, preserve evidence]
    D -- Yes --> F[Cancel according to engine behavior]
    D -- No --> G[Coordinate risk mitigation / incident]
    F --> H[Inspect schema/history/partial data]
    G --> H
    H --> I{Database and app compatible?}
    I -- Yes --> J[Keep old app, plan roll-forward]
    I -- No --> K[Invoke tested recovery plan]
~~~

**Không ngắt DB session hoặc kill job đang chạy chỉ vì CI timeout**. Cần biết DDL có transactional không, batch đã commit chưa, DB lock state và tính toàn vẹn dữ liệu.

## 54. Checklist release database cùng ứng dụng

- [ ] Một migration owner/schema owner được xác định rõ.
- [ ] Đã vẽ sơ đồ các ứng dụng/worker/report/ETL dùng schema.
- [ ] Có mục tiêu SLO/downtime budget, RTO/RPO và change window.
- [ ] Đã phân loại DDL **expand/migrate/contract**; destructive operations tách riêng.
- [ ] Có compatibility matrix cho app cũ/mới và schema trước/sau.
- [ ] Schema expand không làm app cũ đang phục vụ thất bại.
- [ ] App chuyển tiếp đọc data cũ và ghi data mới theo quy tắc nhất quán.
- [ ] Có reconciliation cho dual-write/backfill và concurrent updates.
- [ ] Cột NOT NULL/UNIQUE/FK được thêm theo pha với data checks.
- [ ] Các index operations đã được kiểm tra lock/IO và engine options.
- [ ] Migration scripts được version/checksum và review qua Git.
- [ ] Không sửa migration đã apply; thay đổi mới dùng version mới.
- [ ] Flyway/Liquibase/driver versions tương thích engine/Spring Boot.
- [ ] Runtime app không tự ALTER TABLE khi migration runner là canonical owner.
- [ ] Runner one-shot có concurrency lock và partial-failure runbook.
- [ ] Migration artifact và app artifact chung release manifest/commit/digest.
- [ ] CI test fresh install, upgrade và old/new read-write trên expanded schema.
- [ ] Có load/locking test trên database cùng engine và data đại diện.
- [ ] Database target server/schema/region được xác nhận từ runner thật.
- [ ] Runner private DNS/VNet/TLS kết nối đúng DB, không mở public DB vô cớ.
- [ ] CI identity/managed identity/database principal được phân quyền tối thiểu.
- [ ] Không có passwords, tokens hoặc raw PII trong repo, SQL scripts, logs.
- [ ] Backup/PITR policy được xác nhận và restore rehearsal đã thực hiện.
- [ ] Có kế hoạch giữ dữ liệu mới nếu cần disaster restore.
- [ ] Preflight schema history/engine/version/capacity/locks PASS.
- [ ] Pipeline dừng nếu migration, schema verification hoặc compatibility gate fail.
- [ ] Migration không chạy đồng thời với release khác trên cùng schema.
- [ ] App rollout qua slot/revision/rolling update được kiểm soát.
- [ ] App cũ chạy được trên schema expand trong suốt rollback window.
- [ ] Các worker cũ, queue messages và reports được kiểm tra trước contract.
- [ ] Feature flags có rollback/kill switch và audit logs.
- [ ] Synthetic read/write tests, business invariants và SLO monitoring PASS.
- [ ] Database metrics bao gồm CPU/IO, waits, connections, storage, replica lag.
- [ ] Migration audit record có owner, start/end, result, SQL checksum.
- [ ] Có decision tree **rollback app vs roll forward DB vs PITR**.
- [ ] Chưa có destructive contract trước khi hết rollback window.
- [ ] Có runbook và người trực cho migration/incident.
- [ ] Chi phí của staging clones, runner, index/backfill và log retention được dự toán.
- [ ] Đã dọn lab resources được sở hữu và lưu evidence theo chính sách.

## 55. Câu hỏi tự kiểm tra

1. Vì sao đổi application version và database schema cùng một giây thường nguy hiểm?
2. Một release có thể có bao nhiêu trạng thái trung gian giữa v1/S1 và v2/S2?
3. Backward compatibility và forward compatibility khác nhau thế nào?
4. Thêm nullable column thường an toàn hơn rename trực tiếp vì sao?
5. Expand–migrate–contract gồm những bước nào?
6. Vì sao cần một version bridge cho writers/readers cũ?
7. Trong migration đổi customer_name, tại sao chỉ backfill một lần chưa đủ?
8. Nếu app v1 vẫn update customer_name, display_name có thể stale như thế nào?
9. Khi nào nên bật feature flag đọc cột mới?
10. Vì sao app rollback về v1 cần schema S2 vẫn tương thích?
11. Flyway schema history lưu gì và không chứng minh điều gì?
12. Vì sao không nên sửa script Flyway đã apply vào production?
13. Liquibase changeSet và checksum có vai trò gì?
14. Liquibase rollback dropColumn có thể phá dữ liệu thế nào?
15. Vì sao không nên để mọi Spring Boot pods chạy migration DDL lúc startup?
16. Migration runner một lần cần quyền gì khác với runtime app?
17. OIDC đăng nhập Azure có tự cấp quyền ALTER TABLE trong PostgreSQL không?
18. Vì sao GitHub-hosted runner có thể không truy cập private database?
19. Flyway clean và repair có nguy cơ gì trong production?
20. PostgreSQL transactional DDL có exceptions nào cần chú ý?
21. Vì sao CREATE INDEX CONCURRENTLY không chạy trong transaction block?
22. Một concurrently built index có thể để lại trạng thái invalid khi lỗi không?
23. Azure SQL Query Store giúp gì sau index migration?
24. Vì sao không sao chép lệnh DDL PostgreSQL nguyên xi sang T-SQL?
25. Data backfill theo batch cần cursor/checkpoint như thế nào?
26. Vì sao cursor phải được commit phù hợp với writes?
27. Tại sao một UPDATE cả bảng có thể gây downtime trên dataset lớn?
28. Khi thêm NOT NULL hoặc UNIQUE constraint cần kiểm tra những dữ liệu nào?
29. Schema version có bắt buộc bằng application semantic version không?
30. Tại sao release manifest cần git commit và image/migration digest?
31. Flyway migrate exit 0 có đủ làm post-deploy gate không?
32. Vì sao stage approval không thay data recovery plan?
33. Slot swap của App Service có tự rollback database schema không?
34. ACA revisions dùng chung một database tạo rủi ro gì?
35. AKS Kubernetes Job backoff/retry cần cân nhắc partial migrations thế nào?
36. Vì sao Helm rollback không tự rollback database?
37. Queue consumer version cũ còn có thể đọc field bị drop khi nào?
38. Làm thế nào test cả writer v1 và reader v2 trên expanded schema?
39. Vì sao H2 không thay thế PostgreSQL/Azure SQL integration tests?
40. Long-running database transactions ảnh hưởng DDL như thế nào?
41. PITR về trước migration có nguy cơ làm mất dữ liệu mới ghi ra sao?
42. Khi nào nên roll forward thay vì rollback schema?
43. Nếu migration chạy nhầm staging DB, preflight nào sẽ phát hiện?
44. Một feature flag tắt read path có chắc chặn risky writes không?
45. Sau một release, những metrics nào cần xem để kết luận thành công?
46. Điều kiện nào cần đáp ứng trước khi chạy contract DROP COLUMN?
47. Sự khác nhau giữa migration schema và event schema qua Service Bus là gì?
48. Một release gồm API, worker và database dùng chung có thể được quản lý quyền sở hữu thế nào?
49. Trong bài lab, vì sao v1 phải PASS trên S2 trước khi deploy v2?
50. Một báo cáo release tốt phải chứa những bằng chứng nào?

## 56. Tài liệu tham khảo

- [Azure Database for PostgreSQL – Flexible Server documentation](https://learn.microsoft.com/azure/postgresql/flexible-server/) — kiến trúc managed PostgreSQL, HA, network, monitoring và backup.
- [Azure SQL Database documentation](https://learn.microsoft.com/azure/azure-sql/database/) — T-SQL, scale, backup/restore và performance.
- [Azure SQL Query Store](https://learn.microsoft.com/azure/azure-sql/database/query-store-overview) — phân tích truy vấn/regression.
- [Azure Database for PostgreSQL monitoring](https://learn.microsoft.com/azure/postgresql/flexible-server/concepts-monitoring) — metrics và vận hành PostgreSQL.
- [Spring Boot Flyway integration](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html#howto.data-initialization.migration-tool.flyway) — Spring Boot schema initialization/migrations.
- [Flyway documentation](https://documentation.red-gate.com/fd/) — versioned migrations, validation, CLI, history và engine support.
- [Liquibase documentation](https://docs.liquibase.com/) — changelogs, changeSets, preconditions và rollback.
- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — DDL semantics/locks.
- [PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — concurrently, restrictions và invalid indexes.
- [PostgreSQL monitoring database activity](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity và wait events.
- [GitHub Actions environments](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment) — approvals và environment protection.
- [Azure Login for GitHub Actions](https://github.com/Azure/login) — Entra/OIDC authentication của workflows.
- [Azure Pipelines environments](https://learn.microsoft.com/azure/devops/pipelines/process/environments) — deployment governance.
- [Azure Container Apps jobs](https://learn.microsoft.com/azure/container-apps/jobs) — one-shot/cron/event jobs.
- [Azure Container Apps revisions](https://learn.microsoft.com/azure/container-apps/revisions) — staged app rollout.
- [Azure App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — slot warm-up, swapping và settings.
- [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) — completion, retries và timeouts.
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — rolling updates.
- [Microsoft Entra managed identities](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview) — workload identities.
- [Azure Key Vault](https://learn.microsoft.com/azure/key-vault/general/overview) — secrets và keys.
- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview) — metrics, logs, alerts và release observation.
- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — reliability, operational excellence, security và cost.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — database, compute, network và logs.

**Kết luận:** Triển khai thay đổi database cùng phiên bản ứng dụng trên Azure là **bài toán tương thích nhiều trạng thái và điều phối release**, không chỉ chạy một file SQL. Hãy quản lý migration trong version control, gắn chúng với **cùng commit/release manifest** của ứng dụng, kiểm thử cả **old/new app versions** trên schema expand, dùng **runner một lần với quyền tối thiểu** và xác minh history/data invariants trước canary. Với thay đổi phá vỡ tương thích, dùng **expand → migrate/backfill → switch → contract** thay vì rename/drop trực tiếp. Đừng coi **slot swap, ACA revision rollback, Helm rollback hoặc PITR** là phép undo schema tự động. Một release đáng tin là release có thể chứng minh **đúng database, đúng migration, đúng code, dữ liệu không mất/không trùng, ứng dụng cũ vẫn tương thích trong rollback window và có kế hoạch khôi phục đã diễn tập khi sự cố xảy ra**.
