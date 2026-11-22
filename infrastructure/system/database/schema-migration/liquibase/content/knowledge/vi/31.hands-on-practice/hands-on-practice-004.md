
# Tiếp nhận cơ sở dữ liệu có sẵn và xác lập baseline

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi một hệ thống đã vận hành nhiều năm trước khi áp dụng Liquibase, database có thể chứa hàng trăm bảng, view, sequence, index, trigger và dữ liệu nghiệp vụ. Việc đưa Liquibase vào không bắt đầu bằng cách chạy một changelog tạo toàn bộ schema lên database đang có dữ liệu. Trước hết phải hiểu trạng thái thực tế, mô tả trạng thái đó bằng một baseline có thể tái tạo, rồi thiết lập lịch sử để Liquibase quản lý các thay đổi tiếp theo.

Bài thuộc chương **Thực hành** này hướng dẫn **tiếp nhận cơ sở dữ liệu có sẵn và xác lập baseline**. Quy trình đi từ xác định phạm vi sở hữu, kiểm kê database, sao lưu và đóng băng DDL, tạo changelog từ hiện trạng, rà soát khác biệt, đồng bộ lịch sử bằng `changelog-sync`, xác minh DATABASECHANGELOG và chuyển sang các changeset mới. Bài cũng phân biệt baseline schema với baseline dữ liệu, hướng dẫn chuẩn bị môi trường mới, rehearsal, cutover và xử lý drift hoặc thất bại trong quá trình tiếp nhận.

Phạm vi bài học được xác định bởi **SERVICE_NAME=DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Theo **SERVICE_NAME_DESCRIBE**, module hướng dẫn quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Baseline là gì và vì sao cần thiết?

**Baseline** là mốc mô tả trạng thái database đã tồn tại tại thời điểm một hệ thống bắt đầu được quản lý bằng Liquibase. Baseline cho biết những object nào đã có, định nghĩa của chúng ra sao và từ thời điểm nào các thay đổi tiếp theo được theo dõi bằng changeset.

Ví dụ, database production đã có:

- Bảng customer, orders, order_item và invoice.
- Primary key, foreign key, unique/check constraints.
- Index phục vụ truy vấn.
- Sequence, view, function và trigger.
- Một tập reference data như trạng thái đơn hàng và loại tiền tệ.
- Dữ liệu nghiệp vụ được tạo trong nhiều năm.

Nếu tạo changelog gồm các changeset createTable rồi chạy update trực tiếp lên production, Liquibase sẽ cố tạo lại các bảng đang tồn tại. Kết quả thường là lỗi object already exists hoặc một chuỗi thay đổi dở dang.

Quy trình baseline giải quyết vấn đề này bằng cách **mô tả hiện trạng trong changelog và ghi nhận các changeset baseline là đã được xử lý** trên database hiện có. Từ mốc đó, changeset mới mới được áp dụng như thay đổi phát sinh.

Baseline không phải backup, không phải bản sao dữ liệu và cũng không tự chứng minh database hiện tại đúng. Nó là mốc quản lý lịch sử, cần được đối chiếu với schema và dữ liệu thực tế.

## 2. Mục tiêu và điều kiện hoàn tất

Một lần tiếp nhận thành công cần đạt các kết quả có thể kiểm chứng:

1. Xác định chính xác database, schema, DBMS/version và owner.
2. Có bản sao lưu hoặc điểm phục hồi được kiểm tra.
3. Có inventory các object nằm trong phạm vi Liquibase quản lý.
4. Có changelog baseline được review và lưu trong version control.
5. Changelog phản ánh đúng trạng thái hiện tại của database.
6. DATABASECHANGELOG được thiết lập trên đúng database/schema.
7. Các changeset baseline được ghi nhận mà không chạy lại DDL trên database hiện hữu.
8. Không có changeset tương lai vô tình bị đánh dấu là đã chạy.
9. Có cách tạo database mới từ cùng baseline changelog.
10. Có quy trình rõ cho reference data, dữ liệu nghiệp vụ và thay đổi ngoài Liquibase.
11. Có release record, người chịu trách nhiệm và kế hoạch xử lý drift.
12. Các lần update tiếp theo chỉ chứa thay đổi mới đã được review.

Không coi “chạy changelog-sync thành công” là điều kiện hoàn tất duy nhất. Phải chứng minh changelog khớp database, lịch sử đúng target và môi trường mới có thể tái tạo trạng thái tương đương.

## 3. Phân biệt ba loại dữ liệu cần tiếp nhận

Khi tiếp nhận database cũ, hãy chia nội dung thành ba nhóm:

| Nhóm | Ví dụ | Cách quản lý |
|---|---|---|
| Schema/object | Table, column, PK, FK, index, view, sequence, routine | Baseline changelog và các changeset schema |
| Reference/configuration data | Currency, status code, country, loại nghiệp vụ | Seed changeset hoặc quy trình nạp dữ liệu có kiểm chứng |
| Business/transaction data | Customer, order, invoice, payment | Backup/restore, replication hoặc quy trình data migration riêng |

Một lệnh generate-changelog thường tập trung mô tả schema/object mà Liquibase hỗ trợ. Nó không tự tạo bản sao đầy đủ của dữ liệu nghiệp vụ. Vì vậy, không được suy ra rằng baseline changelog có thể dựng lại toàn bộ database từ số 0 với dữ liệu production.

Nếu cần tạo môi trường mới, phải xác định rõ dữ liệu nào là reference data bắt buộc, dữ liệu nào được seed, dữ liệu nào được nạp từ fixture hoặc backup, và dữ liệu nào chỉ tồn tại trong production.

## 4. Xác định phạm vi sở hữu trước khi chạm database

Database cũ có thể được nhiều nhóm quản lý. Một số bảng do ứng dụng sở hữu, một số bảng do DBA hoặc công cụ tích hợp tạo, một số object thuộc hệ thống báo cáo.

Trước khi baseline, lập danh sách:

- Database/catalog và schema thuộc phạm vi.
- Object do service/domain nào sở hữu.
- Object dùng chung và người phê duyệt thay đổi.
- Object do extension, replication, CDC hoặc nền tảng tạo.
- Object do vendor/package quản lý.
- Object tạm thời hoặc không còn được sử dụng.
- Những object sẽ không được Liquibase quản lý trong đợt đầu.

Không đưa toàn bộ object trên server vào baseline một cách máy móc. Nếu database chứa nhiều schema độc lập, có thể cần master changelog riêng hoặc phạm vi include riêng cho từng owner.

Phải thống nhất ai có quyền thay đổi DDL sau khi tiếp nhận. Nếu DBA vẫn có thể sửa schema thủ công, cần quy trình ghi nhận và chuyển thay đổi đó thành changeset được review.

## 5. Thu thập thông tin kết nối và định danh target

Trước tiên, xác nhận target bằng connection profile có kiểm soát:

- Environment và target ID.
- Host/endpoint, port và database/catalog.
- DBMS và phiên bản.
- User/session hiện tại.
- Default schema và schema chứa object ứng dụng.
- Schema/catalog dự kiến chứa DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Encoding, collation, timezone và các thiết lập liên quan.
- Liquibase version, JDBC driver và artifact sẽ dùng.

Ví dụ truy vấn tham khảo cho PostgreSQL:

~~~sql
SELECT current_database(), current_schema(), current_user;
~~~

MySQL:

~~~sql
SELECT DATABASE(), CURRENT_USER(), VERSION();
~~~

SQL Server:

~~~sql
SELECT DB_NAME() AS database_name, SCHEMA_NAME() AS default_schema;
~~~

Cú pháp và quyền quan sát khác nhau theo DBMS. Ghi lại target ID và thông tin không nhạy cảm trong biên bản; không đưa password hoặc full secret URI vào changelog hay log.

Nếu job trỏ nhầm database hoặc default schema, baseline có thể ghi lịch sử vào nơi khác và khiến database thật xuất hiện hàng loạt changeset pending ở lần update sau.

## 6. Kiểm kê schema hiện trạng

Inventory cần mô tả cả cấu trúc và phụ thuộc:

| Nhóm object | Thông tin cần thu thập |
|---|---|
| Tables | Schema, tên, cột, kiểu, nullability, default, partition |
| Constraints | PK, FK, unique, check, trạng thái enabled/validated |
| Indexes | Cột, thứ tự, unique, predicate, method, trạng thái |
| Sequences/identity | Start, increment, cache, ownership |
| Views/materialized views | Định nghĩa, dependency, refresh strategy |
| Procedures/functions | Source, language, security mode, dependency |
| Triggers | Event, timing, body, thứ tự thực thi |
| Synonyms/extensions/types | Phạm vi DBMS và owner |
| Grants/roles | Quyền runtime, migration, DBA |
| Database settings | Encoding, collation, timezone, extension và compatibility |

Không phải mọi object đều được generate-changelog hỗ trợ hoặc biểu diễn đầy đủ. Cần dùng catalog/DDL export của DBMS và review thủ công các object quan trọng.

Inventory cũng nên ghi object nào được quản lý trong baseline, object nào sẽ bổ sung ở đợt sau và lý do loại trừ.

## 7. Đóng băng DDL và tạo điểm phục hồi

Trong thời gian chụp hiện trạng và tạo baseline, tránh để schema tiếp tục thay đổi ngoài quy trình.

Có thể thực hiện theo một trong các cách:

- Đặt maintenance window và tạm dừng DDL.
- Dùng quy trình change freeze cho các nhóm liên quan.
- Chụp schema snapshot nhất quán và ghi thời điểm.
- Ghi nhận các thay đổi khẩn cấp nếu không thể đóng băng hoàn toàn.

Trước khi thao tác:

1. Xác minh backup hoặc snapshot có thể phục hồi.
2. Kiểm tra thời điểm backup và retention.
3. Xác nhận quy trình restore đã từng được thử hoặc rehearsal.
4. Lưu trạng thái replication/CDC nếu có.
5. Ghi nhận migration window và người trực.
6. Thống nhất cách xử lý nếu phát hiện drift trong lúc baseline.

Backup chỉ có giá trị vận hành khi biết cách phục hồi. Không thực hiện thử nghiệm generate-changelog, changelog-sync hoặc DDL trực tiếp trên production nếu chưa có kế hoạch phục hồi phù hợp.

## 8. Chọn cách tạo baseline changelog

Có hai cách phổ biến:

**Cách A — Generate từ database hiện có**

Dùng Liquibase `generate-changelog` để tạo changelog từ schema mà Liquibase có thể đọc và serialize. Đây là điểm khởi đầu nhanh khi database có nhiều object.

~~~text
liquibase generate-changelog
~~~

Cần cung cấp connection profile, schema/catalog và output path phù hợp với CLI/version. Kết quả phải được review; không mặc định file sinh ra đã đầy đủ hoặc đúng thứ tự cho mọi DBMS.

**Cách B — Viết baseline có chủ đích**

Nhóm tự viết changelog cho object trong phạm vi quản lý. Cách này cho phép kiểm soát tên, thứ tự, chia changeset, comment và khả năng tái tạo, nhưng tốn công và cần đối chiếu kỹ với database thật.

Hai cách có thể kết hợp: generate để lấy inventory/DDL ban đầu, sau đó chỉnh thành baseline có cấu trúc rõ và bổ sung object không được tự động sinh.

## 9. Giới hạn của generate-changelog

Generate-changelog là công cụ hỗ trợ, không phải bản sao hoàn hảo của database.

Cần review các vấn đề:

- Object hoặc thuộc tính DBMS chưa được Liquibase hỗ trợ đầy đủ.
- Trigger, procedure, function, package và view phức tạp.
- Partitioning, extension, generated column và custom type.
- Collation, tablespace, storage parameters và grants.
- Object thuộc schema khác hoặc ngoài phạm vi.
- Thứ tự phụ thuộc giữa sequence, table, view và routine.
- SQL cụ thể phụ thuộc DBMS.
- Khác biệt giữa phiên bản DBMS nguồn và target dựng mới.

Một file generate-changelog có thể chạy được trên database nguồn nhưng không tái tạo đúng database mới trên DBMS/version khác. Hãy thử tạo một database rỗng trên cùng DBMS/version và so sánh kết quả.

Không dùng generate-changelog lặp lại trên production rồi ghi đè baseline đã được review. Khi schema thay đổi sau baseline, hãy tạo changeset mới hoặc dùng diff-changelog để điều tra khác biệt.

## 10. Changelog baseline nên có cấu trúc rõ ràng

Một dự án có thể tổ chức:

~~~text
db/changelog/
  db.changelog-master.yaml
  baseline/
    000-baseline-schema.yaml
    tables/
    views/
    routines/
  reference-data/
    100-seed-status.yaml
    110-seed-currency.yaml
  changes/
    200-add-customer-contact.yaml
    210-add-order-index.yaml
~~~

Master changelog ban đầu chỉ include baseline root:

~~~yaml
databaseChangeLog:
  - include:
      file: baseline/000-baseline-schema.yaml
      relativeToChangelogFile: true
~~~

Baseline root có thể include các file con theo thứ tự dependency. Sau khi đồng bộ baseline trên database cũ, mới bổ sung các changeset tương lai vào master.

Đừng thêm changeset mới vào master trước khi chạy changelog-sync trên database hiện hữu nếu bạn định dùng lệnh đó để đánh dấu baseline. Lệnh sync xử lý các changeset được chọn trong changelog hiện tại; nếu master đã chứa thay đổi tương lai, chúng cũng có thể bị đánh dấu là đã chạy.

## 11. Identity changeset phải ổn định ngay từ baseline

Liquibase nhận diện changeset thông thường bằng tổ hợp **id + author + filename logic**. Baseline cần đặt quy ước ổn định cho cả ba thành phần.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: baseline-001-create-customer
      author: database-platform
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
~~~

Đây là ví dụ minh họa, không phải schema có thể áp dụng nguyên trạng cho mọi hệ thống. Baseline thực tế phải phản ánh đúng định nghĩa hiện có, gồm kiểu dữ liệu, default, constraint và schema.

Không đổi id/author hoặc di chuyển file sau khi baseline đã được ghi vào DATABASECHANGELOG nếu chưa có kế hoạch giữ filename logic. Thay đổi identity có thể khiến Liquibase xem baseline changeset là mới và cố chạy lại DDL.

## 12. Baseline trên database hiện có: changelog-sync

Sau khi baseline changelog được review và xác nhận tương ứng với hiện trạng, dùng **changelog-sync** để ghi nhận các changeset đã chọn là đã được xử lý mà không thực thi nội dung changes.

Lệnh xem SQL dự kiến:

~~~text
liquibase changelog-sync-sql
~~~

Sau khi review đúng target và danh sách changeset, mới thực hiện:

~~~text
liquibase changelog-sync
~~~

Tên lệnh, option và cách truyền filter có thể khác theo phiên bản Liquibase/CLI/plugin. Kiểm tra tài liệu của phiên bản dự án trước khi chạy.

Điểm cốt lõi: **changelog-sync không tạo bảng, cột, index hoặc nạp dữ liệu baseline**. Nó ghi nhận lịch sử trong DATABASECHANGELOG để Liquibase không thực thi lại các changeset đã được chọn.

Nếu baseline changelog không khớp database thật, sync có thể tạo lịch sử sai và che giấu drift. Vì vậy, phải đối chiếu trước và kiểm tra sau.

## 13. Nguy cơ lớn nhất: sync nhầm changeset tương lai

Giả sử master changelog có:

1. Baseline tạo bảng customer.
2. Baseline tạo bảng orders.
3. Changeset mới thêm cột customer.phone.
4. Changeset mới tạo index orders.created_at.

Nếu chạy changelog-sync trên toàn bộ master, Liquibase có thể đánh dấu cả bốn changeset là đã xử lý mà không thực hiện hai thay đổi mới. Sau đó update sẽ bỏ qua chúng, khiến schema thiếu cột/index nhưng history lại cho rằng đã chạy.

Cách an toàn:

- Tạo một baseline-only root/master riêng trong giai đoạn tiếp nhận.
- Chỉ include các changeset mô tả trạng thái đã tồn tại.
- Chạy changelog-sync-sql và review danh sách.
- Chạy changelog-sync trên đúng target.
- Xác minh history.
- Sau đó mới mở rộng master chính để include changeset tương lai.
- Chạy status/updateSQL để xác nhận chỉ các thay đổi mới xuất hiện pending.

Có thể dùng context/label để giới hạn, nhưng phải hiểu chính xác filter semantics và truyền cùng filter vào lệnh preview/sync. Baseline-only root thường dễ audit hơn.

## 14. DATABASECHANGELOG sau khi sync

Sau changelog-sync, kiểm tra bảng DATABASECHANGELOG trong đúng database/schema history.

Truy vấn tham khảo:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    MD5SUM,
    EXECTYPE,
    DATEEXECUTED,
    ORDEREXECUTED,
    DESCRIPTION
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Đối chiếu:

- Số changeset baseline dự kiến.
- ID, AUTHOR và FILENAME logic.
- EXECTYPE của changeset được sync.
- Changelog revision đã dùng.
- Target/database/schema thực tế.
- Không có changeset tương lai bị đánh dấu nhầm.

Changelog-sync thường ghi nhận changeset theo trạng thái MARK_RAN trong history; xác minh giá trị EXECTYPE thực tế theo Liquibase version. Đây là dấu hiệu chúng được ghi nhận mà không chạy nội dung changes, không phải bằng chứng DDL vừa được tạo.

Không sửa tay row history để làm cho số lượng khớp. Nếu sync sai phạm vi, dừng và lập recovery plan dựa trên schema/history thực tế.

## 15. Xác minh DATABASECHANGELOGLOCK

Liquibase dùng DATABASECHANGELOGLOCK để điều phối tiến trình migration cùng sử dụng bảng khóa. Sau khi sync kết thúc bình thường, xác nhận không còn lock bất thường.

Lệnh quan sát:

~~~text
liquibase list-locks
~~~

Nếu lock còn được ghi nhận, kiểm tra pipeline/process/session trước khi xử lý. Không tự đặt LOCKED=false bằng SQL và không chạy thêm job trong khi owner cũ còn hoạt động.

Baseline sync cũng là một thao tác Liquibase có lock. Không để DBA hoặc công cụ migration khác sửa schema đồng thời trong lúc đang đồng bộ history.

## 16. Kiểm tra schema sau baseline

Sau khi history được ghi nhận, cần chứng minh database không bị thay đổi ngoài dự kiến và changelog phản ánh đúng hiện trạng.

Kiểm tra theo nhóm:

- Tables/columns và data types.
- Nullability, default, generated/identity behavior.
- PK/FK/unique/check constraints.
- Index definition và trạng thái valid/usable.
- Sequences và giá trị hiện tại.
- Views/materialized views.
- Functions/procedures/triggers.
- Grants và quyền của runtime/migration user.
- Schema/catalog và object ownership.

Có thể dùng DBMS catalog hoặc DDL export. Với PostgreSQL, ví dụ truy vấn constraint:

~~~sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.customer'::regclass
ORDER BY conname;
~~~

Với DBMS khác, dùng catalog tương ứng. Không áp dụng một truy vấn catalog chung cho mọi hệ quản trị.

## 17. Dùng diff và diff-changelog để phát hiện drift

Liquibase có thể so sánh reference database với target database:

~~~text
liquibase diff
~~~

Lệnh này báo các khác biệt trong phạm vi object được hỗ trợ và cấu hình so sánh.

Có thể sinh changelog mô tả thay đổi cần áp dụng để target tiến gần reference:

~~~text
liquibase diff-changelog
~~~

Cần xác định rõ reference và target. Trong cách dùng thông thường, changelog được sinh ra nhằm đưa target về gần trạng thái reference; đảo nhầm vai trò có thể tạo DDL theo hướng ngược.

Sau baseline, có thể dùng một database clone/reference được kiểm soát để phát hiện drift. Tuy nhiên, diff không phải phép chứng minh toàn diện: object unsupported, dữ liệu, quyền hoặc thuộc tính DBMS đặc thù có thể không được so sánh như mong muốn.

Review diff output, phân loại khác biệt có chủ đích và ngoài dự kiến. Không chạy diff-changelog sinh ra thẳng lên production.

## 18. Xử lý object không được generate đầy đủ

Một số object cần bổ sung bằng SQL hoặc change type phù hợp:

- Trigger và stored procedure.
- Function/package.
- Materialized view.
- Extension hoặc custom type.
- Partitioning và storage option.
- Grant/role hoặc object security.
- DBMS-specific index và constraint.
- Job/event/scheduler nằm ngoài schema.

Có thể dùng change type Liquibase nếu hỗ trợ, hoặc `sql`/`sqlFile` với SQL riêng DBMS. Mỗi object cần xác định owner, dependency, rollback và cách hậu kiểm.

Ví dụ include SQL file:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: baseline-090-create-customer-trigger
      author: database-platform
      changes:
        - sqlFile:
            path: sql/customer-trigger.sql
            relativeToChangelogFile: true
            splitStatements: false
~~~

Các thuộc tính sqlFile cần kiểm tra theo DBMS và phiên bản. Nội dung file phải có trong artifact. Với routine có delimiter đặc thù, xem xét splitStatements/endDelimiter theo hướng dẫn công cụ; không dùng cấu hình mặc định nếu nó làm tách sai câu lệnh.

## 19. Baseline reference data

Reference data thường gồm các mã ít thay đổi và có ý nghĩa ổn định như currency, country, order status hoặc loại nghiệp vụ.

Có thể quản lý bằng changeset insert/loadData hoặc SQL có kiểm soát. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 100-seed-order-status
      author: order-team
      changes:
        - insert:
            tableName: order_status
            columns:
              - column:
                  name: code
                  value: NEW
              - column:
                  name: display_name
                  value: Mới
~~~

Trên database hiện có, nếu các row này đã tồn tại, baseline cần xác minh key và nội dung trước khi đánh dấu changeset là đã chạy. Trên database mới, cùng changeset có thể tạo seed data.

Không đưa toàn bộ dữ liệu nghiệp vụ vào baseline changelog. Với dữ liệu lớn hoặc nhạy cảm, dùng quy trình export/import, masking, replication hoặc backup/restore riêng.

## 20. Baseline dữ liệu nghiệp vụ và sequence

Nếu cần chuyển dữ liệu từ nguồn cũ sang database mới, phải có data migration plan riêng:

- Xác định source of truth và thời điểm snapshot.
- Chọn full load, incremental load hoặc CDC.
- Giữ mapping khóa và quan hệ.
- Xử lý dữ liệu trùng, orphan và lỗi định dạng.
- Đối chiếu row count và aggregate.
- Ghi watermark/checkpoint để resume.
- Đồng bộ các thay đổi phát sinh sau snapshot.
- Đồng bộ sequence/identity để ID mới không va chạm.
- Xác nhận cutover và khả năng quay lại nguồn cũ.

Liquibase có thể điều phối một số thay đổi dữ liệu nhỏ hoặc seed/reference data. Nó không thay thế công cụ ETL/CDC hoặc quy trình backup/restore cho khối lượng dữ liệu lớn.

Với PostgreSQL sequence hoặc DBMS identity, kiểm tra giá trị sinh tiếp theo sau import. Không giả định giá trị sequence tự nhảy theo MAX(id) khi dữ liệu được nạp bằng thao tác ngoài cơ chế sinh ID.

## 21. Database mới phải dựng được từ baseline

Một baseline tốt phải phục vụ cả hai tình huống:

**Database hiện có:** schema đã tồn tại, chạy changelog-sync để ghi nhận baseline mà không tạo lại object.

**Database mới/rỗng:** chạy update để Liquibase thực thi baseline changesets và tạo schema.

Hai tình huống phải được thử độc lập. Nếu baseline chỉ có thể sync trên production nhưng không thể tạo database mới, changelog chưa phải mô tả tái tạo đáng tin cậy.

Ngược lại, nếu baseline chạy được trên database rỗng nhưng không phản ánh đúng production, sync có thể đánh dấu một cấu trúc chưa tồn tại là đã có. Cần so sánh catalog trước khi sync.

Một rehearsal hữu ích là tạo database rỗng cùng DBMS/version, chạy update từ baseline, rồi diff với database hiện có đã được baseline-sync. Những khác biệt còn lại phải được giải thích.

## 22. Tổ chức changelog cho các môi trường

Mọi môi trường nên dùng cùng một revision changelog đã review. Connection, credential và một số filter có thể khác theo môi trường, nhưng nội dung baseline không được sửa tùy tiện giữa dev, staging và production.

Ví dụ:

| Môi trường | Cách thiết lập |
|---|---|
| Production hiện có | Đối chiếu schema rồi changelog-sync baseline |
| Staging hiện có | Đối chiếu riêng, sync cùng baseline nếu thực sự tương đương |
| Dev database mới | Liquibase update để tạo schema từ baseline |
| CI disposable database | Dựng từ baseline, seed fixture và chạy integration test |
| Disaster recovery | Restore backup/PITR rồi xác minh history và drift |

Không dùng DATABASECHANGELOG của production để suy ra staging đã cùng trạng thái. Mỗi database có history riêng. Nếu staging có drift, xử lý trước khi đồng bộ hoặc ghi nhận ngoại lệ có chủ đích.

## 23. Phân quyền sau khi tiếp nhận

Tách trách nhiệm:

- **Migration account:** quyền tạo/sửa object và ghi history trong phạm vi được quản lý.
- **Runtime account:** quyền DML cần thiết cho ứng dụng, thường không cần DDL.
- **Read-only audit account:** đọc metadata, history và các kiểm tra hậu kiểm.
- **DBA/admin:** quyền đặc biệt cho extension, role, grant hoặc recovery.

Không để ứng dụng runtime tiếp tục chạy bằng tài khoản DBA cũ chỉ vì trước đây schema được quản lý thủ công.

Sau baseline, thống nhất mọi thay đổi DDL phải đi qua changeset hoặc quy trình emergency change có ghi nhận và hậu kiểm. Nếu DBA thực hiện hotfix, cần chuyển nó thành changelog/recovery record trước lần update kế tiếp để tránh drift.

## 24. Thử nghiệm baseline trên clone

Trước khi sync production, tạo clone có schema và dữ liệu đại diện.

Thực hiện:

1. Chạy generate-changelog hoặc áp dụng baseline changelog đã viết.
2. Review object và dependency.
3. Dựng một database rỗng bằng baseline update.
4. Clone database hiện có và chạy changelog-sync trên clone.
5. Kiểm tra DATABASECHANGELOG và DATABASECHANGELOGLOCK.
6. So sánh schema giữa database dựng mới và clone đã sync.
7. Kiểm tra reference data và sequence.
8. Chạy smoke test ứng dụng.
9. Thử một changeset mới sau baseline.
10. Diễn tập lỗi và phục hồi.

Rehearsal phải dùng cùng DBMS major version, extension, collation và cấu hình quan trọng như môi trường đích. Một bản clone thiếu dữ liệu hoặc khác DBMS version có thể bỏ sót lock, constraint và performance issue.

## 25. Kế hoạch cutover tiếp nhận production

Một lần cutover có thể chia thành các pha:

| Pha | Công việc | Điều kiện qua bước |
|---|---|---|
| Prepare | Freeze DDL, backup, inventory, baseline review | Có bằng chứng và approval |
| Rehearsal | Thử trên clone và database rỗng | Diff và smoke test đạt |
| Pre-sync | Xác minh target, history location, changelog-sync-sql | Danh sách changeset đúng baseline-only |
| Sync | Chạy changelog-sync | Job hoàn tất và history được ghi |
| Verify | Kiểm tra DATABASECHANGELOG, lock, schema/data | Không có mismatch chưa giải thích |
| Handover | Khóa quyền DDL thủ công theo policy, công bố owner | Mọi thay đổi mới có quy trình |
| First change | Triển khai changeset mới nhỏ, có kiểm chứng | Update và hậu kiểm đạt |

Không chạy first change ngay trong cùng lần tiếp nhận nếu baseline còn chưa được xác minh. Giữ release baseline và release migration đầu tiên thành hai mốc audit rõ ràng.

## 26. Thêm changeset đầu tiên sau baseline

Sau khi baseline đã sync và được xác minh, thêm changeset mới có identity riêng.

Ví dụ thêm cột phone:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 200-add-customer-phone
      author: customer-team
      comment: Thêm số điện thoại liên hệ tùy chọn.
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: varchar(32)
                  constraints:
                    nullable: true
~~~

Trước update:

1. Xác nhận baseline changesets không còn pending.
2. Chạy validate và status.
3. Kiểm tra target/schema.
4. Sinh updateSQL và review.
5. Xác nhận chỉ changeset mới xuất hiện pending.
6. Chạy update trên clone/staging.
7. Hậu kiểm cột và application compatibility.
8. Promote cùng revision sang production theo release policy.

Không sửa baseline changeset để thêm cột phone. Thay đổi mới phải có changeset mới để giữ lịch sử bất biến.

## 27. Các lỗi thường gặp khi xác lập baseline

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Update báo table already exists | Chạy baseline create changesets thay vì sync trên DB hiện có | Dừng, xác minh schema/history; rehearsal changelog-sync |
| Hàng loạt changeset pending | Sai database/schema history hoặc filename logic khác | Kiểm tra target, FILENAME và history location |
| Sync đánh dấu cả changeset mới | Master chứa thay đổi tương lai khi chạy changelog-sync | Dùng baseline-only root và review changelog-sync-sql |
| Database mới thiếu trigger/view | Generate-changelog không biểu diễn đầy đủ object | Bổ sung SQL/change type và test recreate |
| Production sync thành công nhưng schema drift | Baseline không khớp hiện trạng | So sánh catalog, sửa baseline trước khi tiếp tục |
| Staging và production có history khác | Một môi trường có hotfix/restore hoặc artifact khác | Đối chiếu từng target, không copy history thủ công |
| Sequence sinh ID bị trùng | Data import không đồng bộ sequence | Kiểm tra và điều chỉnh theo DBMS |
| Reference data duplicate | Seed changeset không idempotent hoặc dữ liệu đã có | Xác minh business key và seed strategy |
| Diff báo nhiều khác biệt không rõ | Khác DBMS/version/filter hoặc object unsupported | Chuẩn hóa môi trường và review từng nhóm object |
| Lock còn sau job bị dừng | Process/session bất thường | Đối chiếu owner, DBMS session và list-locks trước khi xử lý |

Không giải quyết bằng cách xóa DATABASECHANGELOG, đặt MARK_RAN hàng loạt hoặc chạy changelog-sync lại mà không xác minh.

## 28. Runbook thực hành: tiếp nhận một database có sẵn

Thực hiện trên database disposable hoặc clone trước production.

### Bước 1 — Khảo sát

Ghi DBMS/version, target, schema, owner, object count, constraints, indexes, routines, grants và reference data. Xác định object nằm ngoài phạm vi.

### Bước 2 — Backup và freeze

Tạo điểm phục hồi được kiểm tra. Đóng băng DDL hoặc ghi nhận mọi thay đổi phát sinh trong cửa sổ baseline.

### Bước 3 — Tạo baseline changelog

Chạy generate-changelog trên target clone hoặc viết baseline có chủ đích. Review DDL và bổ sung object không được sinh đầy đủ. Giữ identity và logical path ổn định.

### Bước 4 — Tạo baseline-only root

Master tạm thời chỉ include changesets mô tả trạng thái đã tồn tại. Chưa include changeset mới của release tương lai.

### Bước 5 — Rehearsal trên hai database

- Database clone có schema sẵn: chạy changelog-sync-sql, review, changelog-sync.
- Database rỗng: chạy update để tạo schema từ cùng baseline.

So sánh schema, object và reference data sau hai nhánh.

### Bước 6 — Kiểm tra history và diff

Truy vấn DATABASECHANGELOG, xác nhận changeset identity/EXECTYPE. Chạy list-locks và kiểm tra không còn lock bất thường. Dùng diff để phân loại khác biệt còn lại.

### Bước 7 — Tiếp nhận production

Trong maintenance/change window đã duyệt, xác minh target và backup, chạy changelog-sync-sql rồi changelog-sync. Hậu kiểm history/schema/data và lưu release record.

### Bước 8 — Chuyển sang thay đổi mới

Bổ sung changeset mới vào master chính, chạy validate/status/updateSQL. Xác nhận baseline không xuất hiện pending và chỉ thay đổi mới được đề xuất.

## 29. Checklist nghiệm thu baseline

- [ ] Đã xác định target, DBMS/version, database/catalog và schema.
- [ ] Đã xác định owner và phạm vi object được Liquibase quản lý.
- [ ] Đã kiểm tra backup/restore hoặc snapshot có thể phục hồi.
- [ ] Đã freeze DDL hoặc có cơ chế ghi nhận thay đổi đồng thời.
- [ ] Đã inventory tables, columns, constraints, indexes, sequences và routines.
- [ ] Đã xác định object không được generate-changelog hỗ trợ đầy đủ.
- [ ] Baseline changelog được review và lưu trong version control.
- [ ] id, author, filename/logicalFilePath có quy ước ổn định.
- [ ] Master baseline-only không chứa changeset tương lai.
- [ ] Đã review changelog-sync-sql trên đúng target.
- [ ] Đã chạy changelog-sync chỉ sau khi schema được chứng minh tương đương.
- [ ] DATABASECHANGELOG ghi đúng baseline changesets và EXECTYPE.
- [ ] DATABASECHANGELOGLOCK không còn lock bất thường.
- [ ] Không có changeset tương lai bị đánh dấu nhầm.
- [ ] Schema catalog khớp baseline, bao gồm constraints và indexes.
- [ ] Trigger/view/procedure/extension/grants được kiểm tra riêng.
- [ ] Reference data có seed/verification strategy rõ.
- [ ] Business data có kế hoạch backup/import/CDC riêng.
- [ ] Sequence/identity được kiểm tra sau data load.
- [ ] Database rỗng dựng được từ baseline changelog.
- [ ] Database clone hiện có có thể sync mà không chạy lại DDL baseline.
- [ ] Diff giữa hai nhánh được giải thích.
- [ ] Changeset đầu tiên sau baseline được tách riêng và hậu kiểm.
- [ ] Quyền migration/runtime/DBA được phân tách phù hợp.
- [ ] Có runbook xử lý drift, partial failure và restore.
- [ ] Release record có revision, target, operator, thời gian và bằng chứng.

**Ghi nhớ:** Tiếp nhận database cũ bằng Liquibase là quá trình **đối chiếu hiện trạng, mô tả baseline và đồng bộ lịch sử**. Trên database đã có schema, changelog-sync chỉ ghi nhận các changeset baseline được chọn là đã xử lý; nó không tạo object hoặc nạp dữ liệu. Vì vậy, chỉ sync sau khi changelog khớp hiện trạng, dùng baseline-only root để tránh đánh dấu nhầm thay đổi tương lai, và kiểm tra DATABASECHANGELOG cùng schema/data sau đó. Cùng baseline phải dựng được database mới bằng update và tiếp nhận được database cũ bằng sync. Khi hai nhánh đã được rehearsal và đối chiếu, Liquibase mới có thể quản lý an toàn các thay đổi tiếp theo qua nhiều môi trường.

