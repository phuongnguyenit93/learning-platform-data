# Migration theo từng tenant và theo dõi trạng thái độc lập

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Nhiều cơ sở dữ liệu** này tập trung vào cách triển khai migration cho hệ thống nhiều tenant, trong đó mỗi tenant có thể dùng một database riêng, một schema riêng hoặc cùng chia sẻ các bảng nghiệp vụ. Trọng tâm là bảo đảm **mỗi tenant có lịch sử migration và trạng thái triển khai độc lập**, dù tất cả dùng chung một bộ changelog đã được version hóa.

Liquibase quản lý changeset trên một kết nối database trong mỗi lần thực thi. Nó không tự biết danh sách tenant, chính sách rollout, tenant nào đang hoạt động hay tenant nào đã nâng cấp thành công. Những quyết định đó thuộc về **bộ điều phối migration (migration orchestrator)** của nền tảng hoặc pipeline. Liquibase cung cấp cơ chế thực thi và lịch sử tại database; bộ điều phối quản lý vòng đời triển khai trên nhiều tenant.

Mục tiêu của bài là chọn kiến trúc multi-tenant phù hợp, cấu hình metadata Liquibase độc lập, tổ chức rollout theo nhóm, theo dõi trạng thái ngoài database, xử lý retry và sự cố giữa chừng, onboarding tenant mới và kiểm chứng rằng từng tenant đã đạt phiên bản schema mong muốn.

## 1. Multi-tenant ảnh hưởng đến migration như thế nào?

Một ứng dụng multi-tenant phục vụ nhiều khách hàng hoặc tổ chức trên cùng nền tảng. Dữ liệu có thể được cô lập ở các mức khác nhau:

1. **Database-per-tenant:** mỗi tenant có database riêng, có thể trên cùng server hoặc server khác nhau.
2. **Schema-per-tenant:** một database chứa nhiều schema, mỗi tenant dùng một schema riêng.
3. **Shared schema/shared tables:** nhiều tenant dùng chung các bảng, mỗi hàng được phân biệt bằng tenant_id.
4. **Mô hình kết hợp:** tenant lớn có database riêng, tenant nhỏ dùng chung database hoặc schema; một số thành phần dùng shared tables.

Cách lưu trữ quyết định cách Liquibase ghi lịch sử:

| Kiến trúc | Đơn vị áp dụng migration | Nơi theo dõi lịch sử phù hợp |
|---|---|---|
| Database-per-tenant | Từng database | DATABASECHANGELOG và DATABASECHANGELOGLOCK trong từng database |
| Schema-per-tenant | Từng schema tenant | Metadata Liquibase riêng cho từng tenant/schema hoặc một vùng metadata riêng biệt không bị dùng chung sai cách |
| Shared schema/shared tables | Một schema dùng chung | Một lịch sử Liquibase cho schema chung; không chạy cùng DDL một lần cho mỗi tenant |
| Hybrid | Theo nhóm tenant và loại lưu trữ | Metadata riêng cho từng database/schema được quản lý độc lập, kèm registry điều phối |

**Nguyên tắc quan trọng:** nếu hai tenant có thể có trạng thái schema khác nhau, chúng cần có lịch sử Liquibase độc lập. Không để hai schema tenant dùng chung một bảng DATABASECHANGELOG nếu cùng một changeset phải được áp dụng riêng cho từng schema.

Ví dụ, tenant A đã có cột invoice.status còn tenant B chưa có. Nếu cả hai cùng dùng một DATABASECHANGELOG chung, Liquibase có thể thấy changeset thêm cột đã được ghi nhận bởi tenant A và bỏ qua khi xử lý tenant B. Kết quả là lịch sử chung nói migration đã chạy trong khi schema B vẫn thiếu cột.

Ngược lại, nếu tất cả tenant dùng chung một schema và cùng một bảng invoice có tenant_id, DDL thêm cột vào bảng đó chỉ cần chạy **một lần**. Không tạo một lịch sử migration giả cho từng tenant đối với cùng một schema vật lý.

## 2. Chọn mô hình cô lập và phạm vi migration

### Database-per-tenant

Mỗi tenant có URL, database và có thể có credential riêng. Khi chạy Liquibase, bộ điều phối chọn database tương ứng rồi gọi cùng changelog đã được review.

Ưu điểm:

- Lịch sử DATABASECHANGELOG tự nhiên độc lập theo database.
- Có thể nâng cấp, phục hồi hoặc bảo trì riêng một tenant.
- Dễ đặt giới hạn tài nguyên và chính sách bảo mật theo tenant.

Thách thức:

- Số lượng kết nối và lần chạy tăng theo số tenant.
- Cần quản lý credential, backup, version DBMS và vòng đời database.
- Một release có thể thành công ở một số tenant và thất bại ở tenant khác.

### Schema-per-tenant

Một database có nhiều schema như tenant_001, tenant_002 và tenant_003. Mỗi schema có bảng nghiệp vụ tương tự nhau.

Ưu điểm là chia sẻ server/connection infrastructure nhưng vẫn có thể tách quyền và namespace. Tuy nhiên, cần cấu hình **default schema** và **Liquibase metadata schema** cho từng tenant. Nếu các tenant dùng chung DATABASECHANGELOG và DATABASECHANGELOGLOCK, lịch sử và lock sẽ không còn độc lập.

### Shared schema/shared tables

Một schema chung chứa dữ liệu của tất cả tenant, ví dụ invoice(id, tenant_id, amount). Changeset tạo hoặc sửa bảng invoice chỉ được chạy một lần cho database chung.

Các thao tác backfill theo tenant là một vấn đề riêng: chúng phải giới hạn bằng tenant_id, có tính idempotent và được theo dõi theo cách phù hợp. Không nên nhân bản cùng một changeset DDL cho từng tenant nếu mọi tenant cùng dùng một đối tượng vật lý.

### Mô hình hybrid

Nếu nền tảng hỗ trợ cả tenant lớn và tenant nhỏ, cần có một registry phân loại topology của từng tenant: database nào, schema nào, DBMS/version nào, changelog scope nào. Bộ điều phối dựa vào topology để chọn kết nối và cấu hình Liquibase đúng.

Không suy ra kiến trúc từ tên tenant hoặc URL tùy tiện. Mapping tenant → database/schema phải là dữ liệu quản trị được kiểm soát, có phân quyền và có lịch sử thay đổi.

## 3. Metadata Liquibase phải độc lập theo tenant

Liquibase thường dùng hai bảng metadata:

- **DATABASECHANGELOG**: lưu changeset đã được ghi nhận, checksum và thông tin thực thi.
- **DATABASECHANGELOGLOCK**: điều phối để tránh các tiến trình Liquibase cùng cập nhật một lịch sử database tại một thời điểm.

Với database-per-tenant, mỗi database có bộ metadata riêng một cách tự nhiên, miễn là chúng không bị cấu hình trỏ sang một kho metadata dùng chung bên ngoài.

Với schema-per-tenant, có thể đặt metadata trong chính schema tenant. Ví dụ:

~~~text
appdb
  |
  +-- tenant_001
  |     +-- invoice
  |     +-- customer
  |     +-- databasechangelog
  |     +-- databasechangeloglock
  |
  +-- tenant_002
  |     +-- invoice
  |     +-- customer
  |     +-- databasechangelog
  |     +-- databasechangeloglock
  |
  +-- tenant_003
        +-- invoice
        +-- customer
        +-- databasechangelog
        +-- databasechangeloglock
~~~

Trong cấu hình Liquibase, **defaultSchemaName** xác định schema mặc định cho các đối tượng nghiệp vụ không ghi schema tường minh; **liquibaseSchemaName** xác định schema chứa các bảng metadata Liquibase. Khi chạy cho tenant_001, có thể đặt cả hai là tenant_001; tenant_002 dùng tenant_002.

Ví dụ với PostgreSQL:

~~~shell
liquibase \
  --url="jdbc:postgresql://db-host:5432/appdb" \
  --username="migration_user" \
  --changelog-file="db/changelog/db.changelog-master.yaml" \
  --default-schema-name="tenant_001" \
  --liquibase-schema-name="tenant_001" \
  update
~~~

Các thông tin xác thực cần được cấp qua secret store hoặc môi trường chạy an toàn; không ghi password vào script hoặc repository. Schema tenant phải được tạo và cấp quyền trước khi Liquibase cần tạo metadata trong đó. Quy trình bootstrap schema tenant là một bước provision được quản lý riêng hoặc được thiết kế rõ ràng trong nền tảng.

Khi chạy tenant_002, bộ điều phối thay schema đích và xác nhận lại database/schema trước khi gọi update.

**Không dùng một liquibaseSchemaName chung cho tất cả tenant schema** nếu mục tiêu là có lịch sử độc lập. Một bảng metadata chung sẽ làm Liquibase xem changeset đã chạy ở tenant này như đã chạy cho tenant khác.

Tên bảng metadata cũng có thể tùy chỉnh, nhưng đổi tên bảng cho từng tenant không tự động giải quyết mọi vấn đề nếu chúng vẫn nằm trong cùng một namespace và không có cơ chế phân tách rõ ràng. Ưu tiên schema metadata độc lập, cấu hình đơn giản và có thể kiểm tra.

## 4. Changelog dùng chung, trạng thái theo tenant riêng

Một chiến lược dễ quản lý là **một bộ changelog chuẩn cho cùng một loại tenant**, còn Liquibase chạy bộ changelog đó trên từng database/schema tenant với metadata độc lập.

Ví dụ master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-invoice.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-add-invoice-status.yaml
      relativeToChangelogFile: true
~~~

Changeset tạo bảng invoice không cần biết tenant nào đang được nâng cấp:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-invoice
      author: platform-team
      changes:
        - createTable:
            tableName: invoice
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: amount
                  type: decimal(18,2)
                  constraints:
                    nullable: false
~~~

Khi Liquibase chạy cho tenant_001 với defaultSchemaName là tenant_001, bảng được tạo trong schema đó. Chạy cùng changeset cho tenant_002 với metadata riêng sẽ tạo bảng trong schema tenant_002 và ghi lịch sử ở metadata của tenant_002.

Không hard-code tenant_001 vào changeset nếu cùng changelog cần chạy cho nhiều tenant. Tránh đặt điều kiện tenant-specific trong file migration theo cách khiến các tenant có lịch sử hoặc cấu trúc khác nhau ngoài ý muốn. Nếu một nhóm tenant có yêu cầu schema khác biệt thật sự, hãy xác định **biến thể topology/feature** và quản lý bằng nhánh changelog hoặc contexts/labels được review; đừng tạo hàng trăm changeset riêng lẻ chỉ vì có nhiều tenant.

**Giữ changeset đã triển khai bất biến.** Khi cần đổi cấu trúc, thêm changeset mới; không sửa changeset cũ theo tenant vì checksum sẽ khác và lịch sử giữa các tenant khó đối chiếu.

## 5. Bộ điều phối migration theo tenant

Với hàng chục hoặc hàng nghìn tenant, không nên yêu cầu người vận hành tự chạy lệnh cho từng database bằng tay. Cần một **migration orchestrator** có thể:

1. Lấy danh sách tenant đủ điều kiện nâng cấp từ registry.
2. Xác định topology, database/schema và secret tương ứng.
3. Chọn release/changelog artifact bất biến đã được phê duyệt.
4. Tạo một execution record cho tenant và release.
5. Chạy preflight trên đúng tenant.
6. Gọi Liquibase update với cấu hình riêng tenant.
7. Chạy postflight kiểm tra lịch sử, schema và dữ liệu.
8. Ghi trạng thái thành công/thất bại vào registry điều phối.
9. Phát cảnh báo và hỗ trợ retry/reconcile nếu có lỗi.

Sơ đồ tổng quát:

~~~text
Tenant Registry
      |
      v
Migration Orchestrator
      |
      +--> Resolve tenant_001 -> DB/schema + secret
      |         |
      |         v
      |      Preflight
      |         |
      |         v
      |      Liquibase update
      |         |
      |         v
      |      Postflight
      |         |
      |         v
      |      Record status for tenant_001
      |
      +--> Resolve tenant_002 -> DB/schema + secret
      |         |
      |         v
      |      Preflight -> Update -> Postflight
      |         |
      |         v
      |      Record status for tenant_002
      |
      +--> Resolve tenant_003 ...
~~~

Liquibase vẫn thực thi changeset cho từng kết nối. Orchestrator không thay thế DATABASECHANGELOG; nó quản lý **tenant nào cần chạy, chạy lúc nào, đang ở trạng thái nào và có được phép tiếp tục rollout hay không**.

Nên dùng một migration worker/job riêng thay vì để mọi request ứng dụng hoặc mọi replica Spring Boot tự tìm tenant rồi chạy migration. Điều đó giúp kiểm soát concurrency, credential, timeout, log và quyết định dừng rollout.

## 6. Theo dõi trạng thái độc lập: hai lớp lịch sử

Một hệ thống nhiều tenant thường cần hai lớp thông tin khác nhau:

**Lịch sử Liquibase trong từng tenant** là nguồn dữ liệu về changeset đã được Liquibase ghi nhận ở database/schema đó. Nó trả lời: changeset nào đã chạy, checksum nào được lưu, thời điểm nào, trạng thái thực thi ra sao.

**Registry điều phối trung tâm** là nơi theo dõi tiến trình rollout trên toàn nền tảng. Nó trả lời: tenant nào được chọn, release mục tiêu là gì, job đang chạy hay thất bại, lần thử thứ mấy, ai yêu cầu, khi nào cần retry và rollout có được phép chuyển wave tiếp theo không.

Không thay thế một lớp bằng lớp còn lại. DATABASECHANGELOG không phải bảng điều khiển rollout toàn hệ thống; registry trung tâm cũng không chứng minh DDL đã chạy đúng.

Ví dụ cấu trúc logic cho registry:

| Trường | Ý nghĩa |
|---|---|
| tenant_id | Định danh tenant trong nền tảng |
| topology | database-per-tenant, schema-per-tenant hoặc shared |
| target_release | Release/changelog version cần đạt |
| current_release | Phiên bản schema đã xác minh gần nhất |
| execution_id | ID của lần điều phối cụ thể |
| status | Trạng thái job của tenant |
| attempt | Số lần thử |
| started_at / finished_at | Thời điểm bắt đầu/kết thúc |
| last_success_at | Lần migration thành công gần nhất |
| error_code / error_summary | Mã và tóm tắt lỗi không chứa secret |
| changelog_commit | Commit/artifact đã dùng |
| operator_or_job | Người hoặc job khởi tạo |

Các trạng thái như **QUEUED**, **RUNNING**, **SUCCEEDED**, **FAILED**, **RECONCILIATION_REQUIRED**, **SKIPPED** là trạng thái do nền tảng định nghĩa, không phải tập giá trị EXECTYPE của Liquibase. Cần tài liệu hóa ý nghĩa và chuyển trạng thái cho chúng.

Một ví dụ state machine:

~~~text
QUEUED
  |
  v
PREFLIGHT
  | PASS
  v
RUNNING
  | update + postflight PASS
  v
SUCCEEDED

PREFLIGHT FAIL ---------> FAILED
RUNNING error ----------> RECONCILIATION_REQUIRED
RECONCILIATION_REQUIRED -> xác minh DBCL/schema -> RETRY hoặc SUCCEEDED
FAILED -----------------> retry có điều kiện hoặc BLOCKED
~~~

Registry nên có khóa duy nhất cho cặp tenant_id + release/execution scope để tránh hai worker cùng khởi tạo một lần migration cho một tenant.

## 7. Thiết kế trạng thái và cập nhật registry an toàn

Một lần migration không nên chỉ có cột boolean `done`. Cần trạng thái phân biệt để xử lý job bị ngắt:

- **QUEUED**: đã được chọn nhưng chưa chạy.
- **PREFLIGHT**: đang kiểm tra kết nối, quyền, version và trạng thái hiện tại.
- **RUNNING**: Liquibase update đang thực thi.
- **SUCCEEDED**: update và các hậu kiểm bắt buộc đều đạt.
- **FAILED**: thất bại rõ ràng trước khi có thay đổi cần reconcile, hoặc đã được phân loại có thể retry an toàn.
- **RECONCILIATION_REQUIRED**: tiến trình bị ngắt hoặc lỗi có thể đã để lại thay đổi một phần; phải kiểm tra database thật trước khi retry.
- **BLOCKED**: tenant cần can thiệp hoặc chưa đạt điều kiện nâng cấp.
- **SKIPPED**: tenant được miễn/hoãn theo quyết định có lý do và thời hạn.

Không cập nhật trạng thái SUCCEEDED ngay sau khi lệnh Liquibase trả mã 0 nếu postflight chưa chạy. Trình tự nên là:

1. Tạo execution record với release và tenant identity.
2. Đặt RUNNING trước khi bắt đầu update.
3. Chạy Liquibase với log gắn execution_id.
4. Xác minh changeset và hậu điều kiện.
5. Chỉ sau khi PASS mới ghi SUCCEEDED và current_release.
6. Nếu job mất kết nối hoặc worker bị kill trong giai đoạn không rõ kết quả, ghi RECONCILIATION_REQUIRED thay vì đoán FAILED hoặc SUCCEEDED.

**Cập nhật registry và database tenant không nằm trong cùng một transaction phân tán.** Một bên có thể commit trong khi bên kia không ghi được. Ví dụ Liquibase đã hoàn thành nhưng orchestrator crash trước khi cập nhật registry. Khi worker khởi động lại, phải đọc DATABASECHANGELOG của tenant, kiểm tra schema/data và đối chiếu execution log trước khi cập nhật trạng thái.

Không được chỉ thấy registry RUNNING quá lâu rồi đổi SUCCEEDED bằng tay. Cần bằng chứng từ database tenant.

## 8. Quy trình chạy một tenant

Một worker thực hiện migration cho một tenant theo chuỗi:

### Bước 1 — Resolve tenant

Đọc tenant_id từ registry và lấy topology đã phê duyệt: DB host, database, schema, DBMS/version, credential reference, release mục tiêu. Kiểm tra tenant đang active và được phép nâng cấp.

### Bước 2 — Xác nhận target

Mở kết nối bằng secret của tenant, truy vấn danh tính database/schema/role. Nếu URL hoặc schema không trùng registry, dừng trước khi gọi Liquibase.

### Bước 3 — Preflight

- Kiểm tra DBMS và version có nằm trong ma trận hỗ trợ.
- Xác minh Liquibase/JDBC version.
- Kiểm tra DATABASECHANGELOG và DATABASECHANGELOGLOCK của tenant.
- Xem changeset pending, checksum bất thường, context/label.
- Kiểm tra backup/restore policy và các điều kiện dữ liệu.
- Đánh giá migration có thể khóa bảng hoặc cần maintenance window không.

### Bước 4 — Chạy update

Dùng cùng changelog artifact đã review nhưng cấu hình URL, schema và metadata riêng cho tenant. Không lấy changelog khác nhau theo từng tenant nếu không có lý do topology/DBMS được quản lý rõ.

### Bước 5 — Postflight

Kiểm tra changeset dự kiến đã được ghi nhận, schema/data đạt hậu điều kiện, quyền runtime và smoke test phù hợp. Nếu update chỉ tạo một cột nhưng ứng dụng vẫn không đọc được do quyền hoặc mapping, tenant chưa nên được đánh dấu thành công.

### Bước 6 — Ghi trạng thái

Cập nhật registry với release hiện tại, thời gian hoàn tất, execution_id và kết quả. Lưu log/metrics gắn tenant ID nội bộ nhưng tránh log dữ liệu nhạy cảm của tenant.

## 9. Ví dụ cấu hình database-per-tenant

Giả sử hai tenant có database PostgreSQL độc lập:

~~~text
tenant_001 -> jdbc:postgresql://db-a:5432/customer_001
tenant_002 -> jdbc:postgresql://db-b:5432/customer_002
~~~

Cả hai dùng cùng master changelog:

~~~text
db/changelog/
  db.changelog-master.yaml
  changes/
    001-create-customer.yaml
    002-create-invoice.yaml
    003-add-invoice-status.yaml
~~~

Orchestrator gọi Liquibase lần lượt với URL của từng tenant. Vì mỗi database có DATABASECHANGELOG và DATABASECHANGELOGLOCK riêng, cùng một changeset có thể được thực thi và ghi nhận độc lập trên cả hai database.

Ví dụ lệnh cho tenant_001:

~~~shell
liquibase \
  --url="jdbc:postgresql://db-a:5432/customer_001" \
  --username="tenant_001_migrator" \
  --changelog-file="db/changelog/db.changelog-master.yaml" \
  update
~~~

Tenant_002 dùng URL và secret riêng nhưng cùng changelog artifact. Không cần thay id/author hoặc sửa file theo tenant.

Nếu các database dùng DBMS khác nhau, cùng một changelog chỉ có thể được dùng nếu các changeset tương thích hoặc được giới hạn đúng bằng thuộc tính **dbms**, contexts/labels và cấu trúc include đã review. Không giả định SQL PostgreSQL chạy được trên Oracle hoặc MySQL.

## 10. Ví dụ cấu hình schema-per-tenant

Giả sử database PostgreSQL `appdb` chứa ba schema:

~~~text
appdb
  tenant_001
  tenant_002
  tenant_003
~~~

Cả ba schema có cùng cấu trúc bảng. Khi chạy tenant_001:

~~~shell
liquibase \
  --url="jdbc:postgresql://db-host:5432/appdb" \
  --username="migration_user" \
  --changelog-file="db/changelog/db.changelog-master.yaml" \
  --default-schema-name="tenant_001" \
  --liquibase-schema-name="tenant_001" \
  update
~~~

Khi chạy tenant_002, đặt cả hai schema thành tenant_002. Kết quả mong muốn:

- Các bảng nghiệp vụ được tạo/sửa trong schema của tenant đang chạy.
- DATABASECHANGELOG và DATABASECHANGELOGLOCK nằm trong schema metadata riêng của tenant đó.
- Tenant khác không bị xem là đã chạy changeset chỉ vì tenant hiện tại đã chạy.
- Các query kiểm tra postflight cũng phải giới hạn đúng schema tenant.

Nếu muốn metadata nằm ở schema quản trị riêng, có thể thiết kế một schema metadata riêng cho **mỗi tenant** hoặc dùng cấu hình tên bảng metadata độc lập đã được kiểm chứng. Không đặt mọi tenant dùng chung một bộ metadata nếu cần theo dõi changeset riêng.

### Lưu ý về tên schema tường minh trong changelog

Nếu changeset ghi cứng `schemaName: public`, cấu hình defaultSchemaName=tenant_001 không nhất thiết chuyển đối tượng sang tenant_001. Với changelog dùng chung nhiều schema, cần thống nhất cách để tên schema được giải quyết theo cấu hình kết nối hoặc dùng placeholder/property được truyền có kiểm soát. Review SQL sinh ra để chắc chắn không ghi nhầm schema.

Schema tenant phải tồn tại và tài khoản migration phải có quyền tạo metadata/object ở đó. Đừng để một lần chạy migration tạo metadata vào public do thiếu cấu hình rồi lần tiếp theo lại chạy ở tenant_001.

## 11. Shared schema/shared tables: chỉ chạy DDL một lần

Với mô hình shared tables, một database/schema vật lý phục vụ tất cả tenant. Ví dụ:

~~~sql
CREATE TABLE invoice (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    amount NUMERIC(18,2) NOT NULL
);
~~~

Thêm cột hoặc index cho bảng invoice là thay đổi schema **một lần cho toàn bộ tenant**, không phải một lần cho mỗi tenant. Một DATABASECHANGELOG chung cho schema đó là đúng vì nó đại diện cho cùng một schema vật lý.

Tuy nhiên, nếu cần backfill dữ liệu cho tenant cụ thể, phải giới hạn thao tác bằng tenant_id và theo dõi tiến độ dữ liệu riêng. Ví dụ:

~~~sql
UPDATE invoice
SET status = 'OPEN'
WHERE tenant_id = 'tenant_001'
  AND status IS NULL;
~~~

Không nên tạo một changeset giống nhau cho tenant_001, tenant_002, tenant_003 trong cùng DATABASECHANGELOG nếu mỗi lần chỉ chạy trên cùng một bảng vật lý; changeset đầu có thể được ghi nhận rồi những lần sau bị bỏ qua.

Với backfill hàng triệu hàng theo tenant, cân nhắc job dữ liệu riêng có batch, checkpoint và retry idempotent thay vì nhồi toàn bộ logic vào một changeset chạy một lần. Nếu dùng Liquibase để quản lý bước dữ liệu, cần thiết kế rõ phạm vi, thứ tự, khả năng chạy lại và cách ghi nhận hoàn thành từng tenant.

## 12. Rollout theo wave và canary tenant

Không nhất thiết nâng cấp tất cả tenant cùng lúc. Một chiến lược rollout an toàn chia tenant thành các wave:

~~~text
Release được phê duyệt
       |
       v
Canary: 1-2 tenant đại diện
       |
       +-- FAIL --> Dừng wave, điều tra/forward-fix
       |
       v PASS
Wave 1: nhóm nhỏ
       |
       v PASS + quan sát
Wave 2: nhóm trung bình
       |
       v PASS + quan sát
Wave 3: phần tenant còn lại
       |
       v
Đối chiếu toàn bộ registry và báo cáo release
~~~

Canary nên đại diện cho các biến thể thực tế: tenant có nhiều dữ liệu, tenant có workload cao, tenant dùng phiên bản DBMS khác trong ma trận hỗ trợ hoặc tenant có cấu hình đặc biệt. Không chỉ chọn tenant nhỏ nhất và coi đó là đại diện cho tất cả.

Một số cách chia wave:

- Theo nhóm tenant nội bộ, khu vực hoặc múi giờ để chọn cửa sổ ít tải.
- Theo kích thước dữ liệu và thời gian migration dự kiến.
- Theo DBMS/version hoặc topology database/schema.
- Theo mức độ quan trọng của khách hàng và khả năng bảo trì.
- Theo giới hạn kết nối, IOPS, lock và năng lực đội vận hành.

Sau mỗi wave, kiểm tra tỷ lệ thành công, thời gian, lỗi ứng dụng, replication lag, lock waits và trạng thái registry. Nếu vượt ngưỡng dừng đã định, tạm dừng wave tiếp theo.

## 13. Kiểm soát concurrency và lock

Chạy migration cho nhiều tenant song song giúp rút ngắn thời gian, nhưng có thể gây quá tải database/server, connection pool hoặc storage.

Cần đặt giới hạn:

- **Global concurrency:** tổng số tenant được migrate đồng thời.
- **Per database/server concurrency:** số job cùng tác động một DB instance.
- **Per tenant concurrency:** tối đa một migration owner cho tenant/release tại một thời điểm.
- **Wave size:** số tenant được mở đồng thời trong mỗi đợt.
- **Rate limit:** khoảng cách giữa các lần bắt đầu nếu DB có tải nền lớn.

Liquibase dùng DATABASECHANGELOGLOCK để điều phối tiến trình cùng cập nhật một metadata database. Với metadata độc lập từng tenant, lock cũng độc lập theo tenant. Tuy nhiên, lock đó không bảo vệ registry trung tâm khỏi hai worker cùng nhận một tenant; orchestrator vẫn cần distributed lock/lease hoặc cơ chế claim job nguyên tử.

Đừng nhầm lock Liquibase với khóa traffic ứng dụng. DDL vẫn có thể khóa bảng, ảnh hưởng writer và reader theo DBMS. Nếu nhiều schema tenant cùng nằm trên một database vật lý, migration song song có thể tranh chấp tài nguyên hoặc khóa catalog chung; cần giới hạn theo server chứ không chỉ theo tenant.

Nếu một job chờ lock quá lâu, xác minh tiến trình giữ lock và database session trước khi giải phóng. Không xóa DATABASECHANGELOGLOCK tùy tiện; có thể tạo ra hai tiến trình update đồng thời.

## 14. Retry, idempotency và reconcile sau sự cố

Trong hệ thống phân tán, worker có thể bị dừng do mất kết nối, restart hoặc hết thời gian chạy. Không thể giả định trạng thái registry và database tenant luôn được cập nhật đồng thời.

Ví dụ:

1. Worker đặt tenant_001 thành RUNNING.
2. Liquibase chạy hết changeset và ghi DATABASECHANGELOG.
3. Worker bị kill trước khi ghi registry SUCCEEDED.
4. Registry vẫn hiển thị RUNNING hoặc timeout.
5. Worker mới nhận lại job.

Cách xử lý đúng:

- Kiểm tra database/schema/tenant identity.
- Đọc DATABASECHANGELOG của đúng tenant.
- Xác định changeset đã ghi nhận và checksum có khớp artifact không.
- Kiểm tra hậu điều kiện schema/data.
- Kiểm tra các changeset non-transactional có thể đã để lại thay đổi một phần.
- Chỉ sau khi có bằng chứng mới cập nhật registry SUCCEEDED hoặc quyết định retry/forward-fix.

Liquibase thường không chạy lại changeset đã ghi nhận thành công theo định danh lịch sử. Điều này giúp update có tính lặp lại ở cấp changeset, nhưng không bảo đảm mọi thay đổi ngoài transaction hoặc SQL tự do đều an toàn để retry sau partial failure.

**Không retry mù** chỉ vì trạng thái registry là FAILED. Nếu changeset có runInTransaction=false, DBMS implicit commit hoặc thao tác external side effect, cần kiểm tra trạng thái thực tế trước.

Một retry policy tốt có:

- Phân loại lỗi transient (mất kết nối, deadlock, timeout) và lỗi cấu trúc (checksum, SQL sai, thiếu quyền, dữ liệu vi phạm).
- Backoff và giới hạn số lần retry.
- Reconciliation gate trước retry khi kết quả trước không rõ.
- Dead-letter/blocked state cho tenant cần xử lý thủ công.
- Ghi lại attempt, error code và người phê duyệt nếu cần bỏ qua tenant.

## 15. Onboarding tenant mới

Tenant mới cần được đưa đến **schema version hiện hành** trước khi phục vụ traffic. Quy trình provision thường gồm:

1. Tạo database hoặc schema theo topology của tenant.
2. Cấp role/credential migration và runtime với quyền tối thiểu.
3. Xác minh DBMS/version được hỗ trợ.
4. Tạo metadata Liquibase riêng cho tenant.
5. Chạy cùng master changelog đến release hiện hành.
6. Chạy postflight schema/data/permission checks.
7. Ghi current_release và trạng thái SUCCEEDED trong registry.
8. Chỉ sau đó mới bật tenant hoặc cho phép ứng dụng nhận traffic.

Không cần tạo một bộ changelog khác chỉ vì tenant mới. Dùng cùng lịch sử migration chuẩn giúp giảm schema drift.

Nếu onboarding từ một database đã có dữ liệu/import, phải xác minh baseline trước khi dùng changelog-sync. Không đồng bộ toàn bộ changeset chỉ để tránh tạo lại bảng nếu schema chưa tương đương.

Tenant mới cũng cần kiểm tra các dữ liệu khởi tạo, extension, reference data và quyền. Schema đạt version nhưng thiếu dữ liệu danh mục bắt buộc vẫn chưa sẵn sàng.

## 16. Offboarding tenant và lưu lịch sử

Khi tenant ngừng sử dụng, không nên xóa ngay database/schema và metadata Liquibase mà không qua quy trình quản trị.

Một quy trình offboarding có thể:

- Ngừng nhận request và dừng job nền của tenant.
- Đảm bảo không có migration hoặc writer đang hoạt động.
- Chụp backup/export theo chính sách lưu trữ và quyền riêng tư.
- Ghi nhận release/schema version cuối cùng.
- Thu hồi credential runtime/migration.
- Đánh dấu tenant inactive/archived trong registry.
- Chỉ xóa tài nguyên vật lý sau thời hạn lưu trữ và phê duyệt cần thiết.

DATABASECHANGELOG là bằng chứng lịch sử thay đổi schema, có thể cần giữ để kiểm toán và điều tra. Không xóa riêng bảng metadata rồi giữ schema như thể tenant chưa từng được Liquibase quản lý; việc đó làm mất khả năng truy vết và có thể khiến các lần tiếp quản sau xử lý sai.

## 17. Tenant có phiên bản schema khác nhau trong thời gian rollout

Trong rollout nhiều wave, một khoảng thời gian tenant A đã lên release mới trong khi tenant B vẫn ở release cũ là điều bình thường. Ứng dụng phải được thiết kế để chịu được trạng thái này.

Một chiến lược phổ biến là **expand–migrate–contract**:

1. **Expand:** thêm cột/bảng/constraint theo cách tương thích ngược; không xóa cấu trúc ứng dụng cũ đang dùng.
2. **Deploy application:** phát hành code có thể đọc/ghi cả trạng thái cũ và mới hoặc dùng feature flag.
3. **Migrate:** backfill dữ liệu theo tenant hoặc theo wave, theo dõi tiến độ độc lập.
4. **Verify:** xác nhận tất cả tenant đủ điều kiện đã hoàn thành và dữ liệu đạt hậu điều kiện.
5. **Contract:** xóa cột/đường dẫn cũ sau khi không còn tenant hoặc phiên bản ứng dụng phụ thuộc.

Không triển khai một ứng dụng duy nhất giả định mọi tenant đã cùng schema version nếu rollout chưa hoàn tất. Cần có cơ chế tương thích theo version, route tenant tới pool/phiên bản phù hợp hoặc giới hạn tính năng cho tenant chưa nâng cấp.

Registry có thể lưu current_release để ứng dụng/feature rollout biết tenant đã đạt version nào. Tuy nhiên, dữ liệu này phải được cập nhật sau postflight, không phải ngay khi job bắt đầu.

## 18. Tenant-specific customization và nguy cơ schema drift

Một số khách hàng yêu cầu cột, index hoặc đối tượng riêng. Nếu mỗi tenant có schema khác nhau lâu dài, chi phí vận hành sẽ tăng:

- Changelog có nhiều nhánh điều kiện.
- Test matrix tăng theo biến thể.
- Rollback và hỗ trợ khó dự đoán.
- Một số tenant không thể nâng cấp qua cùng một release.
- Diff giữa tenant có nhiều khác biệt có chủ ý.

Nên ưu tiên **configuration/data customization** thay vì schema customization nếu nghiệp vụ cho phép. Khi cần schema riêng, hãy phân loại rõ:

- **Feature flag/data configuration:** không thay đổi cấu trúc schema, thường dễ quản lý hơn.
- **Optional object theo feature:** có changelog/label/contexts và policy rõ.
- **DBMS-specific object:** tách theo DBMS/version, không theo tenant ID đơn lẻ.
- **Customer-specific schema fork:** ngoại lệ có owner, version matrix, kiểm thử và kế hoạch hội tụ/loại bỏ.

Không hard-code tenant ID trong changeset dùng chung nếu có thể truyền dữ liệu hoặc cấu hình ở tầng ứng dụng. Nếu một tenant cần một migration riêng, ghi rõ tại sao, ai sở hữu và cách bảo đảm các tenant khác không bị chọn nhầm changeset.

## 19. Kiểm chứng sau migration cho từng tenant

Mỗi tenant cần một postflight riêng. Không dùng kết quả thành công của tenant_001 để kết luận tenant_002 đã đạt.

Các kiểm tra tối thiểu:

| Kiểm tra | Bằng chứng cần có |
|---|---|
| Đúng target | Tenant ID, database, schema, DBMS/version đã xác nhận |
| Liquibase history | Changeset dự kiến có trong DATABASECHANGELOG của tenant |
| Checksum | Không có checksum conflict ngoài chính sách |
| Schema | Bảng/cột/constraint/index/view cần thiết tồn tại đúng định nghĩa |
| Data | Truy vấn hậu điều kiện đạt expected result |
| Permissions | Role runtime có quyền đọc/ghi/sequence/function cần thiết |
| Application | Smoke test tenant-scoped thành công |
| Registry | current_release/status chỉ cập nhật sau khi tất cả gate bắt buộc PASS |

Ví dụ truy vấn kiểm tra metadata cho schema tenant trong PostgreSQL (điều chỉnh schema và tên bảng metadata theo cấu hình thực tế):

~~~sql
SELECT id, author, filename, exectype, md5sum, dateexecuted
FROM tenant_001.databasechangelog
ORDER BY orderexecuted;
~~~

Ví dụ kiểm tra bảng nghiệp vụ tồn tại trong đúng schema:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'tenant_001'
  AND table_name = 'invoice';
~~~

Kiểm tra dữ liệu cũng phải giới hạn tenant/schema đúng. Nếu shared tables, thêm điều kiện tenant_id và không coi một query không có filter là kiểm tra tenant riêng.

## 20. Quan sát và báo cáo trạng thái toàn hệ thống

Một dashboard rollout nên cho biết:

- Tổng tenant trong scope.
- Số tenant QUEUED, RUNNING, SUCCEEDED, FAILED, BLOCKED và RECONCILIATION_REQUIRED.
- Tỷ lệ hoàn thành theo release/wave/topology/DBMS.
- Thời gian migration p50/p95 và tenant chạy lâu nhất.
- Changeset cuối cùng thành công ở từng tenant.
- Lỗi theo nhóm: connection, permission, checksum, precondition, SQL, lock, timeout, postflight.
- Số tenant đang ở schema version cũ và thời gian tồn tại trạng thái đó.
- Tenant bị skip và lý do/expiry.

Tránh đưa dữ liệu nhạy cảm của tenant vào log tập trung. Dùng tenant ID nội bộ hoặc mã đã chuẩn hóa; không log row data, password, token hay chuỗi kết nối đầy đủ. Quyền xem dashboard cũng cần phù hợp vì nó có thể tiết lộ topology và tình trạng database của khách hàng.

Một báo cáo release nên gắn với changelog commit, Liquibase version, DBMS matrix, danh sách tenant trong scope, execution IDs, kết quả postflight và quyết định tiếp tục/dừng rollout.

## 21. Tích hợp Spring Boot và CI/CD

Spring Boot có thể chạy Liquibase khi ứng dụng khởi động, nhưng với hàng trăm tenant, để mọi replica và mọi request tự kích hoạt migration thường khó kiểm soát. Một **migration job chuyên biệt** thường phù hợp hơn:

~~~text
CI build changelog artifact
        |
        v
Validate + integration test
        |
        v
Approve release
        |
        v
Migration orchestrator
        |
        +--> tenant canary
        +--> wave 1
        +--> wave 2
        +--> wave N
        |
        v
Per-tenant postflight + registry
        |
        v
Deploy/enable application capability
~~~

Nếu Spring Boot tự chạy Liquibase, cần xác định rõ tenant nào được migrate lúc startup và metadata nào được dùng. Không cấu hình một Liquibase bean chung trỏ vào metadata table dùng chung cho tất cả schema tenant khi các schema cần lịch sử độc lập.

Nếu CI/CD chạy migration riêng, profile runtime có thể tắt Liquibase auto-run để tránh ứng dụng và pipeline cùng sở hữu update. Ứng dụng cần biết tenant nào đã đạt schema version yêu cầu trước khi bật tính năng phụ thuộc vào migration đó.

Pipeline nên:

- Cố định changelog artifact và Liquibase/JDBC version.
- Resolve tenant topology từ registry đã được kiểm soát.
- Cấp secret ngắn hạn/đúng tenant khi có thể.
- Chạy canary và rollout theo wave với giới hạn concurrency.
- Thu thập log, metrics và trạng thái per-tenant.
- Dừng wave mới khi vượt ngưỡng lỗi.
- Reconcile trạng thái sau crash trước khi retry.
- Chỉ hoàn tất release khi tập tenant bắt buộc đạt hậu điều kiện hoặc ngoại lệ được phê duyệt.

## 22. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Tenant A đã chạy nhưng tenant B bị bỏ qua | Cùng dùng DATABASECHANGELOG | Tách metadata theo database/schema tenant |
| Bảng được tạo vào public thay vì tenant schema | defaultSchemaName sai hoặc changelog ghi schema tường minh | Review SQL, schema mapping và kết nối |
| Registry báo SUCCEEDED nhưng tenant lỗi | Ghi trạng thái trước postflight hoặc không reconcile crash | Chỉ cập nhật sau DBCL + schema/data checks |
| Hai worker cùng migrate một tenant | Không có claim/lease ở orchestrator | Thêm lock nguyên tử theo tenant/release |
| Một wave làm DB quá tải | Concurrency không giới hạn theo server | Giới hạn global/per-server, chia wave |
| Retry tạo object trùng | Non-transactional changeset hoặc partial failure | Kiểm tra metadata/object thực tế trước retry |
| Một số tenant khác schema version lâu dài | Tenant-specific customization hoặc rollout bị chặn | Quản lý version matrix, owner và kế hoạch hội tụ |
| Tenant mới có lịch sử nhưng thiếu object | Changelog-sync/baseline sai | Đối chiếu schema, không chỉ nhìn DATABASECHANGELOG |
| Spring Boot khởi động chờ migration lâu | Mọi replica cùng kích hoạt migration | Dùng job riêng hoặc thiết kế startup migration có điều phối |
| Tenant bị migrate nhầm | Registry mapping hoặc credential sai | Xác minh target identity trước mọi update |

Không sửa trực tiếp DATABASECHANGELOG để làm tenant “bằng version” với nhóm còn lại. Nếu lịch sử và schema lệch, hãy xác minh và reconcile từng tenant.

## 23. Quy trình thực hành tổng hợp

Giả sử nền tảng có tenant_001, tenant_002 và tenant_003 dùng schema-per-tenant trong PostgreSQL. Mỗi schema có bảng invoice và bộ metadata Liquibase riêng.

**Bước 1 — Kiểm kê:** lấy tenant registry, xác nhận schema tồn tại, DBMS/version, credential và current_release từng tenant.

**Bước 2 — Kiểm tra metadata:** kết nối riêng tenant_001/002/003; xác nhận DATABASECHANGELOG và DATABASECHANGELOGLOCK nằm đúng schema tương ứng, không có lịch sử dùng chung ngoài ý muốn.

**Bước 3 — Chuẩn bị artifact:** cố định master changelog, commit và phiên bản Liquibase; chạy validate và thử update trên database/schema test mới.

**Bước 4 — Canary:** chọn một tenant đại diện, chạy preflight, update và postflight. Kiểm tra bảng, constraint, dữ liệu, quyền và smoke test.

**Bước 5 — Wave:** nâng cấp tenant_002 rồi tenant_003 theo concurrency đã đặt. Sau mỗi tenant, cập nhật registry chỉ khi hậu kiểm PASS.

**Bước 6 — Mô phỏng crash trên môi trường test:** dừng worker sau khi Liquibase hoàn tất nhưng trước khi registry cập nhật. Khi worker chạy lại, đối chiếu DATABASECHANGELOG và schema để reconcile, không chạy mù.

**Bước 7 — Xử lý tenant lỗi:** nếu một tenant thất bại do thiếu quyền, đánh dấu BLOCKED/FAILED kèm error code; không làm dừng các tenant độc lập nếu chính sách cho phép tiếp tục. Nếu lỗi xuất phát từ changelog chung, dừng wave tiếp theo để tránh lan lỗi.

**Bước 8 — Báo cáo release:** thống kê tenant đã thành công, thất bại, pending, skipped và cần reconcile; chỉ kết luận rollout hoàn tất khi tất cả tenant bắt buộc đạt trạng thái yêu cầu.

## 24. Checklist thiết kế và vận hành

- [ ] Xác định topology từng tenant: database, schema hay shared tables.
- [ ] Quyết định đơn vị migration và đơn vị theo dõi version.
- [ ] Mỗi database/schema có thể có lịch sử DATABASECHANGELOG độc lập khi trạng thái có thể khác nhau.
- [ ] DATABASECHANGELOGLOCK được phân vùng phù hợp; orchestrator có lock/lease riêng theo tenant.
- [ ] Changelog dùng chung, bất biến và được cố định theo release artifact.
- [ ] Không hard-code tenant ID vào changeset dùng chung nếu không thật sự cần.
- [ ] defaultSchemaName/liquibaseSchemaName được resolve theo tenant và kiểm tra bằng target identity.
- [ ] Registry theo dõi trạng thái orchestration, không thay thế lịch sử Liquibase.
- [ ] Chỉ đánh dấu SUCCEEDED sau update và postflight.
- [ ] Có RECONCILIATION_REQUIRED cho job crash hoặc partial failure.
- [ ] Retry có phân loại lỗi, backoff và kiểm tra trạng thái database trước.
- [ ] Rollout theo canary/wave, giới hạn concurrency theo tenant và DB server.
- [ ] Có quy trình onboarding, offboarding và baseline.
- [ ] Ứng dụng tương thích khi tenant ở các schema version khác nhau trong rollout.
- [ ] Có dashboard, log, metrics và báo cáo theo tenant/release.
- [ ] Có kế hoạch backup/restore/forward-fix phù hợp với từng loại migration.
- [ ] Không cập nhật chéo schema hoặc database của tenant khác.
- [ ] Không sửa trực tiếp DATABASECHANGELOG để ép trạng thái.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, migration multi-tenant đáng tin cậy cần kết hợp một changelog chuẩn với **metadata và trạng thái thực thi độc lập cho từng đơn vị có thể nâng cấp riêng**. Liquibase ghi nhận changeset tại từng database/schema; orchestrator quản lý danh sách tenant, rollout, concurrency, trạng thái job và reconcile; postflight xác minh schema, dữ liệu và ứng dụng trước khi đánh dấu tenant thành công. Khi giữ rõ ranh giới này, nền tảng có thể nâng cấp hàng trăm tenant theo từng wave, xử lý tenant lỗi độc lập và truy vết chính xác phiên bản schema trên toàn hệ thống.
