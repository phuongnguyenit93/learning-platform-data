# Xác minh sau triển khai và lưu bằng chứng thực thi

## 1. Mục tiêu và bối cảnh

Một lệnh Liquibase kết thúc với exit code 0 là tín hiệu quan trọng, nhưng chưa đủ để kết luận release database thành công. Pipeline có thể chạy đúng changeset nhưng ứng dụng vẫn không đọc được cột mới; migration có thể tạo index nhưng index chưa ở trạng thái hợp lệ; dữ liệu backfill có thể thiếu một phần; hoặc ứng dụng đã khởi động nhưng lỗi nghiệp vụ chỉ xuất hiện khi có tải thật.

**Xác minh sau triển khai (post-deploy verification)** là tập kiểm tra có chủ đích nhằm chứng minh database đã đạt trạng thái mong đợi, ứng dụng tương thích với schema mới và các tác động vận hành nằm trong giới hạn chấp nhận được. **Bằng chứng thực thi (execution evidence)** là thông tin được lưu có cấu trúc để người khác có thể truy vết ai triển khai, artifact nào được dùng, changeset nào đã chạy, kiểm tra nào đã đạt và ngoại lệ nào còn tồn tại.

Bài thuộc chương **CI/CD** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **xác minh sau triển khai và lưu bằng chứng thực thi**, kết nối lịch sử Liquibase với trạng thái schema, dữ liệu, ứng dụng và hồ sơ release.

Sau bài học, bạn cần có thể:

1. Thiết kế các lớp kiểm tra trước, trong và sau migration.
2. Đối chiếu release artifact với changeset, checksum và DATABASECHANGELOG.
3. Xác minh DATABASECHANGELOGLOCK đã được giải phóng và không có migration cạnh tranh.
4. Kiểm tra schema, index, constraint, dữ liệu và quyền sau triển khai.
5. Chạy smoke test và quan sát metrics/logs để xác nhận ứng dụng tương thích.
6. Phân biệt bằng chứng kỹ thuật với quyết định phê duyệt release.
7. Lưu evidence bundle có nguồn gốc, thời gian, kết quả và khả năng kiểm toán.
8. Đặt release gate, xử lý kiểm tra thất bại và giữ an toàn dữ liệu nhạy cảm.

## 2. Vì sao cần xác minh sau migration?

Migration thay đổi database, nhưng mục tiêu cuối cùng là duy trì khả năng hoạt động của hệ thống. Một changeset có thể chạy thành công mà vẫn không đáp ứng yêu cầu thực tế:

- Cột mới được tạo nhưng ứng dụng đang kết nối tới database khác.
- Index tồn tại nhưng sai cột, thứ tự cột, predicate hoặc trạng thái hợp lệ.
- Constraint được tạo nhưng chưa validate hoặc không bảo vệ dữ liệu như dự kiến.
- Backfill hoàn thành về mặt câu lệnh nhưng bỏ sót một nhóm bản ghi.
- Quyền runtime chưa được cấp nên ứng dụng lỗi khi truy cập object mới.
- Migration làm tăng thời gian khóa, query latency hoặc replication lag.
- Ứng dụng phiên bản cũ không tương thích với schema mới.
- Pipeline đã migrate xong nhưng bước rollout hoặc smoke test thất bại.

Vì vậy, kết quả cần được đánh giá qua nhiều lớp:

| Lớp xác minh | Câu hỏi cần trả lời |
|---|---|
| Artifact và cấu hình | Đúng commit, changelog, Liquibase version và database đích chưa? |
| Liquibase history | Changeset dự kiến đã được ghi nhận đúng chưa? |
| Lock và điều phối | Có migration khác đang chạy hoặc giữ lock không? |
| Schema | Đối tượng và định nghĩa thực tế có đúng không? |
| Dữ liệu | Backfill, constraint và bất biến nghiệp vụ có đạt không? |
| Ứng dụng | Phiên bản được rollout có đọc/ghi đúng schema không? |
| Vận hành | Error rate, latency, lock wait và replication lag có bình thường không? |
| Evidence | Có thể chứng minh kết quả và truy vết nguồn gốc không? |

Không nên gom tất cả thành một phép kiểm tra duy nhất. Mỗi lớp phát hiện một nhóm lỗi khác nhau.

## 3. Xác định tiêu chí thành công trước khi triển khai

Một kiểm tra chỉ hữu ích khi biết trạng thái mong đợi. Trước release, chuyển yêu cầu migration thành các assertion có thể quan sát.

Ví dụ thay đổi thêm cột customer.status và backfill giá trị mặc định:

| Yêu cầu | Tiêu chí xác minh |
|---|---|
| Cột status được tạo | Cột tồn tại trong schema app, đúng kiểu và nullable/default theo thiết kế |
| Backfill hoàn tất | Không còn hàng thuộc phạm vi migration có status NULL |
| Constraint đúng | Constraint tồn tại, đúng định nghĩa và đã validate nếu DBMS hỗ trợ trạng thái đó |
| Runtime truy cập được | Runtime role có quyền cần thiết |
| Ứng dụng tương thích | Endpoint đọc/ghi customer chạy thành công |
| Migration hoàn tất | Changeset có bản ghi phù hợp trong DATABASECHANGELOG |
| Pipeline sạch | DATABASECHANGELOGLOCK không còn bị giữ sau khi job kết thúc |

Assertion cần phản ánh ý nghĩa nghiệp vụ. Ví dụ kiểm tra COUNT(*) WHERE status IS NULL = 0 có thể đúng với dữ liệu hiện tại nhưng chưa chứng minh ứng dụng sẽ tiếp tục ghi status hợp lệ. Cần kiểm tra cả code path ghi mới hoặc constraint bảo vệ bất biến.

### 3.1. Phân loại assertion

- **Existence:** object có tồn tại không?
- **Definition:** object có đúng kiểu, cột, predicate, constraint và option không?
- **Data:** dữ liệu có đáp ứng điều kiện không?
- **Permission:** principal runtime có thể thực hiện thao tác cần thiết không?
- **Behavior:** ứng dụng có thực hiện luồng nghiệp vụ không?
- **Performance:** thay đổi có làm vượt ngưỡng latency, lock hoặc tài nguyên không?

Đừng dùng assertion existence thay cho definition hoặc behavior. Một index cùng tên nhưng định nghĩa sai vẫn là migration chưa đạt.

## 4. Chụp trạng thái trước triển khai để có điểm so sánh

Xác minh sau triển khai có giá trị hơn khi đã lưu baseline trước migration. Trước khi chạy update, pipeline nên thu thập:

- Database identifier không nhạy cảm, DBMS và version.
- Artifact/commit/changelog version.
- Liquibase version và JDBC driver.
- status --verbose hoặc trạng thái changeset pending.
- Kết quả validate.
- Danh sách contexts/labels/parameters được chọn.
- Trạng thái DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Các metric nền như connection count, lock wait, latency và replication lag.
- Assertion baseline cho dữ liệu quan trọng nếu migration có backfill/chuyển đổi.

Baseline giúp phân biệt thay đổi do release với trạng thái đã tồn tại từ trước. Không lưu mật khẩu, token hoặc dữ liệu nhạy cảm trong evidence.

### 4.1. Dùng đúng artifact đã được phê duyệt

Artifact cần bất biến từ lúc validate tới lúc update. Nếu pipeline build lại giữa hai bước, file changelog hoặc SQL được đóng gói có thể khác nội dung đã review.

Lưu tối thiểu:

- Git commit hoặc release tag.
- Artifact name/version và checksum.
- Liquibase version.
- JDBC driver version.
- Master changelog path.
- Contexts, labels và parameters không nhạy cảm.
- Database/environment identifier.
- Pipeline run ID.

Nếu có SQL file ngoài YAML/XML, phải đưa chúng vào artifact manifest hoặc kiểm tra chúng nằm trong bundle đã xác minh. Chỉ lưu đường dẫn master không chứng minh file con giống bản đã review.

## 5. Xác minh kết quả Liquibase

### 5.1. validate

validate kiểm tra cấu trúc changelog, tham chiếu resource và các điều kiện kiểm tra mà Liquibase hỗ trợ. Nó hữu ích trước và sau khi đóng gói artifact, nhưng không phải phép so sánh đầy đủ schema thực tế với yêu cầu nghiệp vụ.

Ví dụ:

~~~bash
liquibase --defaults-file=liquibase.properties validate
~~~

Chạy với đúng artifact và cấu hình của môi trường mục tiêu. Nếu validate ở một cấu hình nhưng update ở cấu hình khác về DBMS, contexts hoặc parameters, kết quả validate không còn đại diện đầy đủ.

### 5.2. status --verbose

status --verbose giúp xem changeset còn pending theo database và bộ lọc đang dùng:

~~~bash
liquibase --defaults-file=liquibase.properties status --verbose
~~~

Trước update, danh sách pending cần khớp release plan. Sau update, không nên còn changeset bắt buộc của release ở trạng thái pending. Nếu vẫn còn, xác định đó là changeset bị filter, nhánh DBMS không áp dụng hay migration chưa hoàn tất.

Không kết luận mọi pending đều là lỗi: changeset có thể dành cho DBMS khác hoặc context/label chưa được chọn theo thiết kế. Evidence cần ghi bộ lọc được dùng để giải thích kết quả.

### 5.3. history và DATABASECHANGELOG

Tùy phiên bản Liquibase, lệnh history có thể cung cấp lịch sử triển khai. Bảng DATABASECHANGELOG vẫn là nguồn metadata trực tiếp để đối chiếu changeset.

Các trường thường quan tâm:

- ID và AUTHOR: định danh changeset.
- FILENAME: đường dẫn được ghi nhận.
- DATEEXECUTED và ORDEREXECUTED: thứ tự/thời điểm thực thi.
- EXECTYPE: kiểu kết quả thực thi theo Liquibase.
- MD5SUM: checksum mà Liquibase lưu cho changeset.

Truy vấn minh họa:

~~~sql
SELECT
    id,
    author,
    filename,
    dateexecuted,
    orderexecuted,
    exectype,
    md5sum
FROM databasechangelog
ORDER BY orderexecuted DESC;
~~~

Tên bảng/schema và cách viết identifier phụ thuộc DBMS/cấu hình. Chỉ truy vấn đọc; không sửa hoặc xóa bản ghi để làm cho pipeline báo thành công.

### 5.4. Kiểm tra changeset cụ thể

Đối chiếu danh sách changeset kỳ vọng với DATABASECHANGELOG:

| Trường | Cần xác minh |
|---|---|
| ID | Đúng changeset trong release |
| AUTHOR | Đúng định danh tác giả |
| FILENAME | Đúng logical/path identity đã được quản lý |
| MD5SUM | Phù hợp artifact và phiên bản Liquibase |
| EXECTYPE | Phù hợp kết quả mong đợi |
| DATEEXECUTED/ORDEREXECUTED | Nằm trong cửa sổ release và thứ tự hợp lý |

Không chỉ đếm số dòng mới trong DATABASECHANGELOG. Một changeset có thể bị MARK_RAN hoặc có EXECTYPE khác với EXECUTED; cần hiểu vì sao và có phê duyệt cho hành vi đó.

## 6. Checksum và tính toàn vẹn artifact

Liquibase lưu checksum changeset trong DATABASECHANGELOG để phát hiện nội dung changeset đã thay đổi theo quy tắc checksum của phiên bản. Đây là cơ chế quan trọng để giữ lịch sử migration bất biến.

Khi xác minh:

1. Lấy commit/artifact đã triển khai.
2. Kiểm tra changeset ID/author/path.
3. Chạy validate bằng đúng phiên bản Liquibase.
4. Đối chiếu lỗi checksum nếu có.
5. Xem xét các thay đổi có chủ đích như runOnChange/runAlways hoặc validCheckSum.
6. Lưu kết quả và quyết định xử lý.

Không dùng clear-checksums như bước hậu kiểm thông thường. Lệnh này làm Liquibase tính lại checksum trong lần chạy sau; nó không chứng minh schema đúng và có thể che giấu việc changeset lịch sử bị chỉnh sửa.

Không so sánh chuỗi checksum bằng một quy tắc tự viết mà bỏ qua version prefix/cách chuẩn hóa của Liquibase. Dùng chính phiên bản công cụ và validate để diễn giải checksum.

### 6.1. Checksum không chứng minh database đúng

Checksum xác nhận quan hệ giữa nội dung changeset và lịch sử được ghi nhận. Nó không chứng minh:

- DBA không thay đổi schema thủ công sau migration.
- SQL đã tạo object đúng như yêu cầu.
- Dữ liệu backfill đầy đủ.
- Ứng dụng có quyền truy cập.
- Index có hiệu năng mong muốn.
- Migration không gây tác động ngoài database.

Do đó, phải kiểm tra catalog/schema/data và behavior riêng.

## 7. Xác minh DATABASECHANGELOGLOCK

Liquibase sử dụng DATABASECHANGELOGLOCK để điều phối migration. Sau một lượt update bình thường, lock thường được giải phóng.

Truy vấn minh họa:

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM databasechangeloglock;
~~~

Tiêu chí sau triển khai thường là:

- Không còn lock do job đã kết thúc giữ lại.
- Không có migration job khác đang chạy ngoài kế hoạch.
- Không có session DBMS cũ tiếp tục thực thi SQL.
- Nếu LOCKED=true, đã xác định được holder và trạng thái thực tế.

Lock=false không chứng minh migration thành công; changeset có thể đã lỗi trước đó. Lock=true cũng không tự động chứng minh stale lock; có thể một migration hợp lệ vẫn đang chạy.

Không gọi release-locks trong post-deploy cleanup một cách mù quáng. Trước hết xác minh process/session cũ và chủ sở hữu lock. Release lock chỉ xử lý khóa điều phối, không rollback SQL hay dừng câu lệnh DBMS.

## 8. Xác minh schema thực tế

Kiểm tra schema phải đối chiếu **định nghĩa**, không chỉ sự tồn tại.

Với mỗi object do release thay đổi, xác minh:

- Đúng database và schema.
- Đúng tên, kiểu dữ liệu, độ dài/precision/scale.
- Nullable, default và generated/identity behavior.
- Primary key, foreign key, unique và check constraints.
- Index columns, thứ tự, predicate, method và trạng thái valid.
- View/function/procedure definition.
- Owner, grants và dependency.
- Trạng thái validate/disabled nếu DBMS hỗ trợ.

Ví dụ kiểm tra cột trên PostgreSQL:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'customer'
  AND column_name = 'status';
~~~

Cùng một truy vấn không nhất thiết hoạt động giống nhau trên mọi DBMS; cần dùng catalog tương ứng và hiểu mapping kiểu dữ liệu. information_schema có thể không thể hiện mọi thuộc tính vendor-specific.

### 8.1. Kiểm tra index

Một index có tên đúng nhưng sai cột hoặc sai predicate không đáp ứng migration. Trên PostgreSQL, có thể xem định nghĩa và trạng thái:

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND tablename = 'customer';
~~~

Với index tạo concurrent, kiểm tra trạng thái hợp lệ trong catalog nếu migration có khả năng thất bại một phần. DBMS khác cần truy vấn metadata riêng.

### 8.2. Kiểm tra constraint

Xác minh constraint tồn tại, đúng cột và được bật/validate. Ví dụ một foreign key có thể được tạo ở trạng thái chưa validate tùy DBMS và cách triển khai. Nếu yêu cầu là dữ liệu hiện có cũng phải thỏa constraint, chỉ thấy object trong catalog chưa đủ.

## 9. Xác minh dữ liệu sau migration

Với DML/backfill, cần assertion dữ liệu cụ thể và có giới hạn tải.

Ví dụ kiểm tra cột status không còn NULL:

~~~sql
SELECT COUNT(*) AS rows_missing_status
FROM app.customer
WHERE status IS NULL;
~~~

Kết quả kỳ vọng có thể là 0, nhưng chỉ phù hợp nếu yêu cầu nghiệp vụ thực sự quy định mọi hàng phải có status.

Các kiểm tra khác:

- Tổng số hàng trước/sau theo quy tắc dự kiến.
- Số hàng được backfill trong phạm vi.
- Không có duplicate key.
- Không có foreign key orphan.
- Tổng tiền hoặc số lượng đối soát với nguồn đáng tin cậy.
- Dữ liệu mới có format/range hợp lệ.
- Sequence/identity tiếp tục sinh giá trị không trùng.
- DML có thể chạy lặp theo thiết kế mà không tạo duplicate.

Không chạy COUNT(*) toàn bảng rất lớn trên production nếu truy vấn gây tải không cần thiết. Có thể dùng index, partition, batch counter hoặc số liệu đã được tính trong quá trình migration. Ghi rõ giới hạn của phép kiểm tra.

### 9.1. Kiểm tra dữ liệu theo mẫu và theo tổng hợp

Kiểm tra sample giúp tìm lỗi định dạng hoặc mapping. Kiểm tra aggregate giúp phát hiện sai lệch số lượng/tổng. Với dữ liệu tài chính hoặc audit, cần đối chiếu với nguồn độc lập và tiêu chí nghiệp vụ, không chỉ query cùng database vừa migrate.

## 10. Xác minh quyền và principal

Migration có thể tạo object nhưng quên cấp quyền runtime. Khi đó DATABASECHANGELOG ghi changeset thành công nhưng ứng dụng gặp permission denied.

Hậu kiểm cần xác nhận:

- Runtime principal đúng.
- Quyền SELECT/INSERT/UPDATE/DELETE/EXECUTE cần thiết đã có.
- Runtime không có quyền DDL hoặc quyền quản trị ngoài phạm vi.
- Owner của object mới phù hợp mô hình.
- Default privileges áp dụng cho object tạo mới nếu thiết kế dựa vào chúng.
- Schema metadata Liquibase không bị runtime truy cập ngoài nhu cầu.
- Secret/credential được dùng đúng môi trường.

Nên chạy một số truy vấn hoặc test bằng đúng runtime role, không dùng owner/migrator để giả lập ứng dụng.

## 11. Kiểm thử ứng dụng sau migration

### 11.1. Smoke test

Smoke test xác nhận các đường đi quan trọng hoạt động sau rollout. Ví dụ:

- Ứng dụng khởi động và readiness đạt.
- Kết nối database thành công.
- Đọc một bản ghi qua repository/DAO.
- Tạo và cập nhật một bản ghi test có thể dọn dẹp.
- Endpoint nghiệp vụ quan trọng trả kết quả đúng.
- Job nền hoặc consumer có thể đọc schema mới.
- Runtime role không gặp lỗi quyền.

Smoke test phải có dữ liệu và môi trường phù hợp. Không thực hiện thanh toán thật, gửi email thật hoặc tạo tác động bên ngoài trong test nếu không có sandbox/idempotency.

### 11.2. Compatibility giữa ứng dụng và schema

Trong rolling deployment, phiên bản cũ và mới có thể cùng chạy một lúc. Migration nên tuân theo chiến lược expand-contract khi cần:

1. Expand: thêm cột/bảng mới theo cách tương thích với phiên bản cũ.
2. Deploy ứng dụng mới có thể đọc/ghi cấu trúc mới.
3. Backfill và xác minh dữ liệu.
4. Chuyển traffic/code path sang cấu trúc mới.
5. Chỉ contract: xóa cột hoặc object cũ sau khi mọi consumer đã ngừng dùng.

Post-deploy verification phải kiểm tra consumer cũ còn hoạt động trong giai đoạn chuyển tiếp. Không drop cột ngay sau khi code mới được deploy nếu các replica cũ, job nền hoặc báo cáo vẫn phụ thuộc.

### 11.3. Kiểm tra các consumer ngoài ứng dụng chính

Schema có thể được sử dụng bởi:

- Batch job.
- ETL/ELT pipeline.
- BI/reporting.
- CDC/replication.
- Stored procedure hoặc trigger.
- Dịch vụ khác truy cập trực tiếp database.

Cần đưa các consumer quan trọng vào checklist hoặc có hợp đồng schema rõ ràng. Smoke test chỉ gọi một endpoint không chứng minh toàn bộ hệ sinh thái đã tương thích.

## 12. Quan sát metrics và logs sau deploy

Sau khi migration xong, theo dõi trong một khoảng thời gian phù hợp với workload:

| Tín hiệu | Điều cần quan sát |
|---|---|
| Application error rate | Tăng lỗi SQL, mapping, constraint hoặc permission |
| Latency p95/p99 | Query chậm do plan/index hoặc lock |
| Database CPU/I/O | Migration hoặc query mới tạo tải bất thường |
| Lock wait/deadlock | Migration còn block hoặc workload bị ảnh hưởng |
| Connection pool | Pool cạn, timeout hoặc rò rỉ connection |
| Replication lag | Thay đổi lớn tạo WAL/binlog backlog |
| Disk/temporary space | Index build, sort hoặc backfill dùng nhiều tài nguyên |
| Background jobs | Consumer/batch lỗi sau schema change |
| Business metrics | Tỷ lệ giao dịch, số đơn, tổng tiền hoặc quy trình chính |

Đặt ngưỡng dựa trên baseline và SLO. Không coi mọi biến động ngắn hạn là lỗi, nhưng cần có tiêu chí rõ để tiếp tục, dừng rollout hoặc kích hoạt incident.

### 12.1. Quan sát trong lúc migration

Một số metric cần thu thập ngay khi chạy:

- Thời gian chờ DATABASECHANGELOGLOCK.
- Thời gian từng changeset.
- Statement duration và lock wait.
- Số hàng xử lý trong backfill nếu có.
- Replication lag và WAL/binlog generation.
- Dung lượng còn lại.
- Số connection và session đang hoạt động.

Không log toàn bộ dữ liệu hàng hoặc giá trị secret để có thêm chi tiết. Correlation ID và changeset identity thường đủ để nối log pipeline với log DBMS.

## 13. Phân biệt migration thành công và release thành công

Một release database thường gồm nhiều trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| Artifact validated | Changelog hợp lệ theo kiểm tra Liquibase |
| Migration started | Job đã kết nối và bắt đầu điều phối |
| Changesets applied | Liquibase ghi nhận changeset đã chạy |
| Schema/data verified | Các assertion database đạt |
| Application deployed | Phiên bản ứng dụng đã rollout |
| Smoke tests passed | Luồng chức năng trọng yếu hoạt động |
| Observation window passed | Metrics/logs không vượt ngưỡng |
| Release accepted | Người/quy trình có thẩm quyền chấp nhận release |

Không gộp migration success thành release success nếu các bước ứng dụng, dữ liệu hoặc quan sát còn pending.

Nếu migration thành công nhưng smoke test thất bại, ghi nhận hai kết quả riêng. Không chạy lại migration để chữa lỗi ứng dụng. Điều tra tương thích, quyền, cấu hình và quyết định rollback/forward fix theo runbook.

## 14. Thiết kế pipeline với các gate rõ ràng

Một pipeline tham khảo:

~~~text
Build changelog artifact
        |
        v
Validate + kiểm tra resource
        |
        v
Review update-sql / approval
        |
        v
Capture pre-deploy baseline
        |
        v
Liquibase update (single owner)
        |
        v
Verify DATABASECHANGELOG + LOCK
        |
        v
Verify schema + data + grants
        |
        v
Deploy / rollout application
        |
        v
Smoke tests + consumer checks
        |
        v
Observe metrics and logs
        |
        v
Store evidence bundle
        |
        v
Release gate / approval
~~~

Có thể rollout ứng dụng trước migration trong chiến lược expand-contract, hoặc chạy migration trước rồi rollout. Điều quan trọng là dependency và compatibility được định nghĩa rõ, không áp dụng một thứ tự cứng cho mọi thay đổi.

### 14.1. Gate nên có kết quả có cấu trúc

Mỗi bước trả về một trạng thái như PASS, FAIL, WARN hoặc NOT_APPLICABLE, kèm timestamp, nguồn dữ liệu và lý do. Không chỉ tìm chuỗi SUCCESS trong log.

Ví dụ:

| Check | Result | Evidence |
|---|---|---|
| Liquibase validate | PASS | validate log + artifact digest |
| Expected changesets | PASS | DATABASECHANGELOG query |
| Lock released | PASS | DATABASECHANGELOGLOCK query |
| Schema assertions | PASS | catalog query output |
| Backfill completeness | PASS | aggregate query |
| Application smoke | PASS | test run ID |
| Error-rate window | WARN | monitoring snapshot |
| Release approval | PENDING | approval record |

WARN không tự động đồng nghĩa FAIL; policy phải định nghĩa ngưỡng nào được tiếp tục và ai có quyền chấp thuận ngoại lệ.

## 15. Lưu bằng chứng thực thi (evidence bundle)

Evidence bundle là tập artifact nhỏ, có cấu trúc, đủ để người khác tái dựng quyết định release. Có thể gồm:

1. Release ID, pipeline run ID và environment.
2. Git commit/tag và artifact digest.
3. Master changelog path và danh sách file SQL tham chiếu.
4. Liquibase/JDBC/DBMS version.
5. Contexts, labels và parameter names đã dùng (không lưu secret values).
6. Kết quả validate, status và update.
7. Danh sách changeset cùng EXECTYPE/checksum được ghi nhận.
8. Trạng thái DATABASECHANGELOGLOCK sau migration.
9. Kết quả schema/data/grant assertions.
10. Smoke test và consumer test run IDs.
11. Metrics/logs trong observation window.
12. Approval, ngoại lệ và người chịu trách nhiệm.

Không cần sao chép toàn bộ log database vào một file duy nhất. Lưu tham chiếu tới hệ thống log/monitoring có quyền truy cập được kiểm soát, cùng truy vấn hoặc dashboard và khoảng thời gian cụ thể.

### 15.1. Ví dụ manifest bằng JSON

~~~json
{
  "releaseId": "orders-2026.11.19.3",
  "pipelineRunId": "run-18427",
  "environment": "staging",
  "database": {
    "identifier": "orders-staging",
    "dbms": "PostgreSQL",
    "version": "16"
  },
  "artifact": {
    "gitCommit": "a1b2c3d4",
    "digest": "sha256:...",
    "masterChangelog": "db/changelog/db.changelog-master.yaml"
  },
  "liquibase": {
    "version": "4.x",
    "contexts": ["staging"],
    "labels": ["release"]
  },
  "checks": {
    "validate": "PASS",
    "expectedChangesets": "PASS",
    "lockReleased": "PASS",
    "schemaAssertions": "PASS",
    "dataAssertions": "PASS",
    "applicationSmoke": "PASS",
    "observationWindow": "PASS"
  },
  "result": "ACCEPTED"
}
~~~

Đây là ví dụ định dạng, không phải schema bắt buộc. Digest, version và kết quả phải lấy từ công cụ thật. Không dùng giá trị minh họa làm bằng chứng của một release thực tế.

### 15.2. Bằng chứng phải có nguồn gốc

Mỗi record nên chỉ ra:

- Ai hoặc job nào tạo ra?
- Thời điểm nào và theo timezone nào?
- Database/environment nào?
- Artifact/commit nào?
- Lệnh hoặc assertion nào được thực hiện?
- Kết quả và exit code?
- Có bị chỉnh sửa sau khi tạo không?

Có thể lưu manifest cùng checksum/signature trong artifact store hoặc hệ thống evidence. Chỉ lưu file JSON có nội dung tự khai không đủ bảo đảm tính xác thực; cần phân quyền và audit nơi lưu.

## 16. Bảo mật evidence và log

Evidence có thể chứa database name, schema, query, object name, lỗi SQL hoặc dữ liệu nghiệp vụ. Cần:

- Không lưu password, token, private key hoặc secret đã resolve.
- Mask thông tin định danh nhạy cảm theo chính sách.
- Không đưa sample data chứa dữ liệu cá nhân vào log không kiểm soát.
- Giới hạn quyền đọc evidence theo vai trò.
- Mã hóa khi lưu/truyền nếu hệ thống yêu cầu.
- Giữ retention theo chính sách audit.
- Ghi nhận người tải/xóa/sửa evidence.
- Dùng link tham chiếu tới log có kiểm soát thay vì nhân bản dữ liệu rộng rãi.

Không ghi nguyên JDBC URL nếu URL chứa username/password hoặc tham số nhạy cảm. Dùng database identifier đã chuẩn hóa.

### 16.1. Lưu truy vấn và kết quả, không lưu dữ liệu thừa

Với assertion dữ liệu, thường chỉ cần câu truy vấn đã chuẩn hóa, số lượng kết quả, ngưỡng kỳ vọng và trạng thái PASS/FAIL. Không cần dump toàn bộ hàng thỏa điều kiện vào evidence.

## 17. Xử lý khi một bước hậu kiểm thất bại

Khi một assertion FAIL, pipeline cần dừng theo chính sách và phân loại:

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Sai artifact/target | Digest không đúng hoặc database identifier sai | Dừng ngay, không tiếp tục rollout |
| History không đúng | Changeset bắt buộc pending hoặc checksum mismatch | Đối chiếu artifact, contexts/labels và DATABASECHANGELOG |
| Lock bất thường | Lock còn giữ sau khi job đã kết thúc | Xác minh holder/session trước khi xử lý |
| Schema mismatch | Cột/index/constraint sai định nghĩa | Điều tra SQL, DBMS và thay đổi ngoài Liquibase |
| Data assertion fail | Backfill thiếu hoặc dữ liệu vi phạm bất biến | Dừng rollout, đánh giá resume/forward fix/restore |
| Permission fail | Runtime role không truy cập object mới | Sửa quyền qua migration/quy trình được review |
| Smoke test fail | Endpoint lỗi hoặc mapping sai | Giữ rollout, xác định tương thích schema/app |
| Metric vượt ngưỡng | Latency/lock/replication lag tăng mạnh | Dừng rollout hoặc kích hoạt incident theo SLO |
| Evidence không đầy đủ | Thiếu log hoặc không truy ra artifact | Không đánh dấu release accepted |

Không tự động rollback mọi khi smoke test thất bại. Rollback có thể làm mất dữ liệu mới hoặc không tương thích với ứng dụng đang chạy. Chọn rollback, forward fix hoặc phục hồi theo runbook và trạng thái database thực tế.

### 17.1. Retry hậu kiểm có điều kiện

Một số kiểm tra eventual consistency có thể cần chờ ngắn rồi chạy lại, ví dụ replication lag giảm hoặc service vừa rollout. Retry chỉ phù hợp khi:

- Assertion có tính đọc, không gây side effect.
- Có deadline và số lần thử giới hạn.
- Kết quả trước/sau được lưu.
- Không che giấu lỗi cấu trúc hoặc dữ liệu.
- Không chạy lại migration chỉ vì một smoke test tạm thời chưa sẵn sàng.

## 18. Ví dụ truy vấn hậu kiểm theo yêu cầu

Giả sử changeset thêm cột status, tạo index và backfill trạng thái cho customer.

### 18.1. Kiểm tra cột và kiểu

Dùng catalog DBMS để xác minh cột app.customer.status có kiểu và nullability theo thiết kế. Truy vấn information_schema.columns ở phần trước chỉ là ví dụ cho các thuộc tính chuẩn; với kiểu đặc thù cần catalog vendor-specific.

### 18.2. Kiểm tra dữ liệu

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(status) AS rows_with_status,
    COUNT(*) FILTER (WHERE status IS NULL) AS rows_missing_status
FROM app.customer;
~~~

Cú pháp FILTER là ví dụ PostgreSQL. Trên DBMS khác, dùng CASE WHEN hoặc cú pháp tương ứng. So sánh với expected result đã xác định trước, không chỉ ghi số liệu mà không có ngưỡng.

### 18.3. Kiểm tra dữ liệu không hợp lệ

~~~sql
SELECT COUNT(*) AS invalid_status_rows
FROM app.customer
WHERE status NOT IN ('ACTIVE', 'INACTIVE', 'PENDING')
   OR status IS NULL;
~~~

Nếu status cho phép giá trị khác, assertion phải phản ánh domain thật. Trường hợp cột nullable theo thiết kế thì không thể dùng điều kiện này như tiêu chí chung.

### 18.4. Kiểm tra index được sử dụng

Tồn tại index chưa có nghĩa query planner sử dụng index. Với truy vấn quan trọng, dùng EXPLAIN hoặc công cụ query plan trên dữ liệu đại diện. Không chạy EXPLAIN ANALYZE trên truy vấn có side effect hoặc workload production mà chưa đánh giá chi phí.

Kết hợp query plan với metrics sau rollout để xác minh index có cải thiện mục tiêu và không gây write amplification quá lớn.

## 19. Xác minh theo nhiều DBMS

Một pipeline đa DBMS phải chạy assertion phù hợp từng hệ quản trị. Không giả định truy vấn catalog PostgreSQL có thể dùng trên MySQL/Oracle/SQL Server.

| Hạng mục | PostgreSQL | MySQL/MariaDB | SQL Server | Oracle |
|---|---|---|---|---|
| Cột/kiểu | information_schema + pg_catalog | information_schema + metadata | sys.columns/sys.types | USER_TAB_COLUMNS/ALL_TAB_COLUMNS |
| Index | pg_indexes/pg_index | information_schema.statistics | sys.indexes/sys.index_columns | USER_INDEXES/USER_IND_COLUMNS |
| Constraint | information_schema/pg_catalog | table_constraints/key_column_usage | sys.check_constraints/sys.foreign_keys | USER_CONSTRAINTS |
| Routine | pg_proc/pg_get_functiondef | information_schema.routines | sys.objects/sys.sql_modules | USER_OBJECTS/USER_SOURCE |
| Session/lock | pg_stat_activity/pg_locks | processlist/performance_schema | DMVs | dynamic performance views |

Quyền đọc catalog có thể khác theo DBMS và principal. Chỉ cấp quyền metadata cần thiết; không nâng migration/runtime lên quyền quản trị chỉ để chạy một dashboard.

## 20. Lưu bằng chứng theo changeset

Với release lớn, evidence nên gắn kết quả ở cấp changeset thay vì chỉ một trạng thái tổng.

Ví dụ bảng nội bộ hoặc manifest có thể chứa:

| Trường | Ví dụ |
|---|---|
| Release ID | orders-2026.11.19.3 |
| Changeset identity | 520-add-customer-status / platform-team |
| Changelog path | db/changelog/changes/520-add-customer-status.yaml |
| Checksum | Giá trị đọc từ DATABASECHANGELOG |
| Execution type | EXECUTED |
| Start/end | Timestamp UTC |
| DBMS | PostgreSQL 16 |
| Postcondition | status column exists; null rows = 0 |
| Application check | customer-read-write-smoke PASS |
| Evidence reference | URI/log query ID trong hệ thống lưu trữ |

Không tạo một hệ thống audit thứ hai trùng lặp với DATABASECHANGELOG nếu không có yêu cầu. Evidence bundle bổ sung ngữ cảnh release và kết quả kiểm chứng; DATABASECHANGELOG vẫn là lịch sử changeset của Liquibase.

## 21. Quan hệ giữa bằng chứng và rollback/forward fix

Bằng chứng sau triển khai giúp đưa ra quyết định khi có sự cố:

- Nếu changeset đã chạy, schema/data đạt và smoke test đạt, release có thể tiếp tục qua observation window.
- Nếu changeset đã chạy nhưng data assertion fail, cần xác định phạm vi dữ liệu sai và chọn forward fix/restore.
- Nếu history ghi changeset nhưng schema không đúng, điều tra thay đổi ngoài Liquibase, sai target hoặc lỗi DBMS.
- Nếu schema đã thay đổi nhưng history chưa ghi nhận, xem xét transaction boundary và trạng thái thực thi trước khi retry.
- Nếu ứng dụng lỗi nhưng database đạt, kiểm tra compatibility, config và quyền trước khi rollback.

Không dùng evidence để hợp thức hóa một trạng thái sai. Nếu có ngoại lệ, ghi rõ ai chấp thuận, lý do, thời hạn và hành động tiếp theo.

## 22. Tiêu chí đóng release

Một release có thể được đánh dấu accepted khi các điều kiện bắt buộc đều đạt:

1. Artifact và database target đúng.
2. Liquibase validate/status/history phù hợp release plan.
3. Changeset bắt buộc có kết quả thực thi được chấp nhận.
4. DATABASECHANGELOGLOCK không còn trạng thái bất thường.
5. Schema/data/grants assertions đạt.
6. Ứng dụng và consumer quan trọng vượt qua smoke test.
7. Metrics/logs nằm trong ngưỡng trong observation window.
8. Evidence bundle đã lưu và có thể truy cập bởi người được phép.
9. Ngoại lệ có owner và approval.
10. Có phương án phục hồi/runbook nếu sự cố xảy ra tiếp.

Không nhất thiết mọi release đều cần cùng số lượng assertion. Thay đổi thêm một index có thể tập trung vào định nghĩa index, lock/performance và query plan; thay đổi backfill dữ liệu tài chính cần đối soát nghiệp vụ sâu hơn.

## 23. Checklist trước và sau triển khai

### Trước triển khai

- [ ] Tiêu chí schema/data/app được viết thành assertion.
- [ ] Baseline và database target đã được ghi nhận.
- [ ] Commit, artifact digest và Liquibase/JDBC version đã cố định.
- [ ] Validate và status chạy với đúng contexts/labels.
- [ ] SQL preview được review khi cần.
- [ ] Có release owner và điều phối single-writer.
- [ ] Có ngưỡng metrics, observation window và kế hoạch phục hồi.
- [ ] Evidence storage có quyền và retention phù hợp.

### Sau migration

- [ ] DATABASECHANGELOG ghi nhận đúng changeset, path, checksum và EXECTYPE.
- [ ] Không còn changeset bắt buộc pending ngoài kế hoạch.
- [ ] DATABASECHANGELOGLOCK đã được giải phóng; không có session cũ còn chạy.
- [ ] Schema object đúng định nghĩa, owner và trạng thái.
- [ ] Dữ liệu/backfill/constraint đạt assertion.
- [ ] Runtime role thực hiện được thao tác cần thiết và không có quyền thừa.
- [ ] Ứng dụng, batch và consumer quan trọng vượt qua smoke test.
- [ ] Error rate, latency, lock wait, replication lag và tài nguyên đạt ngưỡng.
- [ ] Evidence bundle có đủ nguồn gốc, timestamp, artifact và kết quả.
- [ ] Ngoại lệ/approval được ghi rõ trước khi accepted.

## 24. Kết luận

Xác minh sau triển khai cần chứng minh ba điều: **Liquibase đã ghi nhận đúng thay đổi, database thực sự đạt schema/data mong đợi và ứng dụng hoạt động tương thích**. DATABASECHANGELOG, checksum và DATABASECHANGELOGLOCK cung cấp bằng chứng về lịch sử và điều phối; catalog, truy vấn dữ liệu, quyền runtime, smoke test và metrics cung cấp bằng chứng về trạng thái thực tế.

Evidence bundle nối các kết quả đó với commit, artifact, phiên bản công cụ, database đích, pipeline run và người phê duyệt. Bằng chứng phải có nguồn gốc, timestamp, quyền truy cập và retention rõ ràng; không chứa secret hoặc dữ liệu thừa. Release gate dựa trên các assertion đã định nghĩa trước, và mọi ngoại lệ cần có owner cùng quyết định được lưu.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, cách làm này giúp migration có thể kiểm chứng qua dev, test, staging và production; hỗ trợ điều tra khi có lỗi, quyết định rollback hay forward fix và duy trì lịch sử triển khai đáng tin cậy.

