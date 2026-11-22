# Thiết lập điểm dừng và tiêu chí xác nhận hoàn tất

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Triển khai an toàn** này hướng dẫn thiết lập các **điểm dừng (stop points/gates)** và **tiêu chí xác nhận hoàn tất (completion criteria)** cho một lần phát hành database.

Một migration không nên được xem là hoàn tất chỉ vì lệnh Liquibase trả mã thoát thành công. Nhóm cần xác nhận đúng database đã được tác động, đúng changeset được ghi nhận, schema và dữ liệu đạt hậu điều kiện, ứng dụng tiếp tục hoạt động, các chỉ số vận hành nằm trong ngưỡng chấp nhận và bằng chứng triển khai đã được lưu. Ngược lại, khi một điều kiện quan trọng không đạt, pipeline cần dừng đúng chỗ để tránh lan lỗi sang tenant, môi trường hoặc bước phát hành tiếp theo.

Mục tiêu của bài là biến việc triển khai thành một chuỗi quyết định có thể kiểm tra: **điều kiện nào cho phép bắt đầu, điều gì buộc phải dừng, ai quyết định tiếp tục, trạng thái nào cần reconcile và bằng chứng nào chứng minh release đã hoàn tất**.

## 1. Vì sao cần điểm dừng và tiêu chí hoàn tất?

Một changeset có thể thành công về mặt SQL nhưng vẫn không đạt mục tiêu phát hành. Ví dụ:

- Liquibase chạy vào database staging thay vì production.
- Changeset được ghi vào DATABASECHANGELOG nhưng index sau đó bị xóa thủ công.
- ALTER TABLE thành công nhưng ứng dụng phiên bản cũ không còn ghi được dữ liệu.
- Backfill chỉ cập nhật một phần bản ghi nhưng pipeline vẫn đánh dấu release thành công.
- Migration tạo lock lâu, khiến độ trễ API vượt SLA.
- Một tenant đã nâng cấp, tenant khác chưa chạy nhưng bộ điều phối báo cả nhóm đã hoàn tất.
- Job bị kill sau khi DDL đã commit nhưng trước khi Liquibase ghi lịch sử.
- Postflight thất bại nhưng deployment job vẫn tiếp tục rollout ứng dụng.

Điểm dừng giúp nhóm **ngăn một trạng thái chưa được xác minh tiến sang bước tiếp theo**. Tiêu chí hoàn tất giúp tránh kết luận dựa trên cảm giác hoặc một tín hiệu đơn lẻ.

Một quy trình có thể dùng các gate:

~~~text
G0: Release được định danh và phê duyệt
       |
       v
G1: Preflight database và changelog PASS
       |
       v
G2: SQL dự kiến được review và chấp thuận
       |
       v
G3: Migration thực thi có giám sát
       |
       v
G4: Postflight history + schema + data PASS
       |
       v
G5: Ứng dụng và vận hành ổn định trong cửa sổ quan sát
       |
       v
G6: Bằng chứng đầy đủ, release được đóng
~~~

Mỗi gate phải có người hoặc job chịu trách nhiệm, đầu vào, điều kiện PASS, điều kiện FAIL, hành động khi dừng và bằng chứng lưu lại.

## 2. Phân biệt gate, stop, abort, rollback và completion

Các từ này không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Gate / điểm kiểm soát** | Một bước quyết định có cho phép tiếp tục không | Review SQL trước production |
| **Stop / pause** | Tạm dừng rollout hoặc bước tiếp theo để đánh giá | Dừng mở wave tenant mới |
| **Abort** | Hủy bước đang chờ hoặc dừng quy trình theo cách được DBMS hỗ trợ | Không bắt đầu DDL khi sai target |
| **Rollback** | Thực thi thao tác đảo ngược đã thiết kế | Drop index vừa tạo |
| **Forward-fix** | Tạo migration mới để sửa trạng thái hiện tại | Thêm changeset sửa constraint |
| **Restore/PITR** | Phục hồi database từ backup hoặc mốc log | Khôi phục sau khi mất dữ liệu |
| **Completion** | Tất cả điều kiện bắt buộc đã đạt và có bằng chứng | Schema, data, app và vận hành đều PASS |

Dừng rollout không nhất thiết có nghĩa là hủy statement đang chạy. Với DDL dài hoặc non-transactional, việc ngắt session có thể để lại object một phần hoặc kéo theo thời gian cleanup. Người vận hành phải xác định DBMS đang ở trạng thái nào và dùng phương án an toàn đã chuẩn bị.

Tương tự, rollback không phải phản xạ mặc định mỗi khi một gate FAIL. Có trường hợp schema đã thay đổi thành công nhưng smoke test ứng dụng lỗi do code; rollback schema có thể làm tình hình xấu hơn. Khi đó có thể dừng rollout ứng dụng, rollback code hoặc forward-fix tùy tương thích.

## 3. Xác định phạm vi và chủ sở hữu release

Trước khi đặt ngưỡng, phải biết release đang triển khai những gì:

- Release ID, artifact/build và commit changelog.
- Database, schema, tenant hoặc nhóm database trong phạm vi.
- DBMS/version, Liquibase/JDBC version.
- Master changelog, contexts, labels và các changeset dự kiến.
- Phiên bản ứng dụng trước/sau migration.
- Người phê duyệt, migration owner và người quyết định khi cần dừng.
- Cửa sổ triển khai, SLA và ngưỡng vận hành liên quan.
- Kế hoạch rollback, forward-fix hoặc restore.

Mỗi database hoặc schema có thể có trạng thái khác nhau. Với database-per-tenant hoặc schema-per-tenant, completion phải được xác định theo từng đơn vị migration; một tenant thành công không chứng minh tất cả tenant đã hoàn tất.

Nên chỉ định **một migration owner** cho một database/schema trong một thời điểm. Owner chịu trách nhiệm xác nhận target, chạy Liquibase, theo dõi tiến trình, thực hiện postflight và ghi nhận kết quả. DBA, SRE, ứng dụng và người phê duyệt có thể tham gia các gate tương ứng, nhưng không nên có hai pipeline độc lập cùng quyết định cập nhật một target.

## 4. Thiết kế gate G0: release có thể bắt đầu hay chưa?

Gate G0 xác nhận release có danh tính rõ và đủ điều kiện tổ chức triển khai.

**PASS khi:**

- Artifact ứng dụng và changelog đã được build từ commit đã review.
- Release ID và phạm vi database/tenant đã xác định.
- Changeset mới có ID/author/path ổn định; changeset đã triển khai không bị sửa tùy tiện.
- Kế hoạch triển khai và người chịu trách nhiệm đã rõ.
- Rủi ro chính, thời gian dự kiến và phương án phục hồi đã được review.
- Approval cần thiết đã được ghi nhận.

**FAIL khi:**

- Không xác định được release/commit sẽ chạy.
- Changelog bị thay đổi sau review hoặc artifact không bất biến.
- Chưa biết database/tenant nào nằm trong phạm vi.
- Có changeset phá hủy dữ liệu nhưng chưa có phương án phục hồi.
- Không có migration owner hoặc người có quyền quyết định khi sự cố.
- Có một release khác đang sở hữu cùng target.

Nếu G0 FAIL, không chạy preflight trên production bằng credential ghi và không bắt đầu migration. Có thể tiếp tục chuẩn bị độc lập như review changelog hoặc dựng database test, nhưng target chưa được mở cho update.

## 5. Thiết kế gate G1: preflight database và Liquibase

G1 xác nhận môi trường thật khớp với mục tiêu và trạng thái hiện tại đáp ứng giả định của changeset.

### 5.1. Xác nhận target identity

Ví dụ PostgreSQL:

~~~sql
SELECT
    current_database() AS database_name,
    current_schema() AS current_schema,
    current_user AS connected_role,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    current_setting('server_version') AS server_version;
~~~

So sánh kết quả với môi trường được phê duyệt. Tên connection hoặc biến môi trường như production không đủ làm bằng chứng; cần xác minh database/schema/role thực tế.

**PASS:** đúng target, schema, role và DBMS/version thuộc ma trận hỗ trợ.

**FAIL:** sai target, không xác định được database hoặc thiếu quyền đọc metadata cần thiết. Dừng trước update.

### 5.2. Xác nhận lịch sử và changelog

Các lệnh CLI thường dùng:

~~~shell
liquibase --version
liquibase validate
liquibase status --verbose
~~~

Cần xác minh:

- Liquibase/JDBC version đúng phiên bản đã pin.
- Changelog parse và validate được.
- Các changeset pending đúng với release dự kiến.
- Không có checksum mismatch chưa được giải quyết.
- Context/label filter đúng.
- DATABASECHANGELOG và DATABASECHANGELOGLOCK thuộc đúng target.
- Không có migration job khác đang chạy hoặc giữ lock.

Validate thành công không chứng minh SQL sẽ chạy được trên dữ liệu thật. Status không thay thế việc đọc DATABASECHANGELOG và kiểm tra schema thực tế khi có dấu hiệu drift.

### 5.3. Xác nhận giả định dữ liệu

Ví dụ trước khi thêm NOT NULL:

~~~sql
SELECT COUNT(*) AS null_status_count
FROM public.invoice
WHERE status IS NULL;
~~~

Nếu hậu điều kiện yêu cầu không còn NULL, expected result là 0. Cần kiểm tra cả ứng dụng đang chạy có tiếp tục ghi NULL trong thời gian triển khai hay không.

**PASS:** các truy vấn preflight trả đúng kết quả mong đợi và không có writer nào làm vô hiệu giả định trước khi DDL chạy.

**FAIL:** dữ liệu vi phạm, truy vấn không thể thực thi, hoặc có thay đổi đồng thời chưa được kiểm soát. Dừng để backfill/điều phối writer hoặc sửa kế hoạch.

## 6. Thiết kế gate G2: review SQL và kế hoạch thay đổi

Trước production, cần xem SQL mà Liquibase dự kiến thực thi:

~~~shell
liquibase update-sql
~~~

Tên lệnh/options cụ thể cần xác minh theo phiên bản CLI. Dùng cùng changelog, target, contexts và labels với lệnh update thật.

Review tập trung vào:

- Có đúng changeset trong phạm vi không?
- Có DROP, TRUNCATE, DELETE hoặc thu hẹp kiểu dữ liệu không?
- Có thao tác rebuild/copy bảng hoặc tạo index lớn không?
- Có DDL cần chạy ngoài transaction không?
- Có lock, metadata lock hoặc replication lag đáng kể không?
- Có precondition và hậu điều kiện đủ rõ không?
- Rollback có thể phục hồi dữ liệu hay chỉ đảo cấu trúc?
- Ứng dụng cũ và mới có tương thích trong từng giai đoạn không?
- SQL có đúng schema và object ownership không?

**PASS:** SQL được review, phạm vi và rủi ro được chấp thuận, kế hoạch phục hồi sẵn sàng.

**FAIL:** SQL khác với kế hoạch, có thao tác phá hủy chưa phê duyệt, thiếu rollback/forward-fix hoặc không có thời gian/tài nguyên phù hợp. Không chạy update.

Một bản preview không phải hợp đồng tuyệt đối về runtime. Precondition, dữ liệu cạnh tranh, lock và trạng thái DB có thể làm kết quả khác. Nếu artifact, filter hoặc target thay đổi sau review, phải chạy lại gate G2.

## 7. Thiết kế gate G3: thực thi có giám sát

Sau khi G0–G2 PASS, migration owner mới chạy:

~~~shell
liquibase update
~~~

Trong lúc chạy, theo dõi:

- Log và changeset đang thực thi.
- DATABASECHANGELOGLOCK.
- Thời gian thực hiện và statement timeout.
- Lock wait, transaction dài và deadlock.
- CPU, I/O, dung lượng đĩa và transaction log/WAL/redo.
- Replication lag/CDC.
- Request latency, timeout và error rate của ứng dụng.
- Tiến độ backfill hoặc index build nếu có.

Đặt ngưỡng trước khi chạy. Ví dụ, nhóm có thể quy định dừng mở wave tiếp theo nếu replication lag vượt ngưỡng SLA trong một khoảng thời gian, hoặc nếu request error rate vượt baseline đã thống nhất. Các giá trị cụ thể phải dựa trên SLO, workload và khả năng phục hồi của hệ thống; không dùng một con số chung cho mọi database.

### Khi nào phải dừng?

- Target hoặc role thực tế không còn đúng.
- Statement báo lỗi hoặc changeset có dấu hiệu thực thi một phần.
- Lock wait vượt giới hạn đã phê duyệt.
- Replication lag, disk usage hoặc error rate vượt ngưỡng dừng.
- Có dấu hiệu ảnh hưởng dữ liệu ngoài phạm vi.
- Người vận hành mất khả năng quan sát trạng thái.
- Có một migration khác tác động cùng target.

**Dừng rollout** nghĩa là không khởi chạy changeset/tenant/wave kế tiếp. Với statement đang chạy, xác minh trạng thái và hậu quả của việc cancel trên DBMS trước khi can thiệp. Không tự ý kill session hoặc xóa DATABASECHANGELOGLOCK chỉ vì job lâu.

## 8. Thiết kế gate G4: postflight lịch sử Liquibase

Sau khi update kết thúc, kiểm tra DATABASECHANGELOG. Ví dụ trên PostgreSQL khi metadata nằm trong schema public:

~~~sql
SELECT
    id,
    author,
    filename,
    exectype,
    md5sum,
    dateexecuted,
    orderexecuted
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Với changeset cụ thể:

~~~sql
SELECT id, author, filename, exectype, md5sum
FROM public.databasechangelog
WHERE id = '060-invoice-status-not-null'
  AND author = 'billing-team';
~~~

Xác nhận:

- Changeset bắt buộc có bản ghi với đúng ID, author và filename/logical path.
- Checksum khớp chính sách release.
- EXECTYPE phù hợp với cách thực thi dự kiến; không nhầm MARK_RAN với DDL đã chạy.
- Không có changeset ngoài phạm vi bất ngờ được ghi nhận.
- Các changeset cần chạy tiếp vẫn pending đúng như thiết kế.

**PASS:** lịch sử khớp release và không có dấu hiệu checksum hoặc execution bất thường.

**FAIL:** thiếu changeset, checksum mismatch, trạng thái MARK_RAN ngoài dự kiến hoặc lịch sử không thể giải thích. Dừng rollout và reconcile trước khi retry.

Không sửa trực tiếp DATABASECHANGELOG hoặc MD5SUM để làm cho gate xanh. Hãy xác định nguyên nhân và xử lý bằng quy trình Liquibase được review.

## 9. Thiết kế gate G4: postflight schema và dữ liệu

Lịch sử đúng chưa đủ. Kiểm tra object thực tế bằng metadata DBMS và truy vấn hậu điều kiện.

Ví dụ kiểm tra cột:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'invoice'
  AND column_name = 'status';
~~~

Nếu mục tiêu là NOT NULL, kỳ vọng cột có is_nullable = NO. Tiếp theo kiểm tra dữ liệu:

~~~sql
SELECT COUNT(*) AS null_status_count
FROM public.invoice
WHERE status IS NULL;
~~~

Kỳ vọng bằng 0. Với index PostgreSQL, kiểm tra thêm trạng thái valid/ready; với FK, kiểm tra constraint và validation; với sequence, kiểm tra thuộc tính và cách ứng dụng cấp ID.

Mỗi thay đổi cần có **postcondition định lượng hoặc định tính rõ ràng**:

| Loại thay đổi | Ví dụ tiêu chí hoàn tất |
|---|---|
| Thêm bảng | Bảng tồn tại đúng schema, cột/PK/FK/default đúng |
| Thêm cột | Kiểu, nullability, default đúng; ứng dụng đọc/ghi được |
| Thêm index | Index tồn tại, đúng cột/thuộc tính và hợp lệ |
| Thêm UNIQUE | Constraint/index hợp lệ và không có dữ liệu trùng |
| Thêm FK | FK đúng cột/action, dữ liệu không mồ côi, validation đạt |
| Backfill | Số hàng mục tiêu, số hàng cập nhật và giá trị hậu kiểm đạt |
| Đổi kiểu | Kiểu mới đúng, dữ liệu không bị cắt/tràn ngoài dự kiến |
| Xóa object | Dependency và consumer đã được loại bỏ, hậu điều kiện được xác nhận |

**PASS:** tất cả postcondition bắt buộc đạt trên đúng database/schema.

**FAIL:** object thiếu/sai, dữ liệu không đạt, index invalid hoặc có drift ngoài kế hoạch. Không đánh dấu release thành công.

## 10. Thiết kế gate G5: ứng dụng và vận hành ổn định

Migration có thể đúng nhưng ứng dụng không tương thích. Gate G5 kiểm tra hệ thống sau khi database thay đổi.

Các kiểm tra thường cần:

1. Ứng dụng khởi động và kết nối datasource thành công.
2. ORM/schema validation không báo thiếu hoặc sai mapping.
3. Role runtime có quyền cần thiết.
4. Smoke test các luồng đọc/ghi quan trọng đạt.
5. Các thao tác không hợp lệ bị constraint từ chối đúng cách.
6. Tỷ lệ lỗi, latency và timeout không vượt ngưỡng.
7. Replication/CDC/downstream consumer đã bắt kịp theo tiêu chí.
8. Phiên bản ứng dụng cũ và mới tương thích nếu rollout theo kiểu rolling.
9. Job nền, báo cáo và tích hợp không bị lỗi do schema mới.

Một smoke test đơn lẻ không chứng minh mọi nghiệp vụ hoạt động. Chọn test theo tác động của changeset và mức độ quan trọng của luồng nghiệp vụ.

### Cửa sổ quan sát

Với migration rủi ro cao, nên có khoảng thời gian quan sát sau deploy trước khi mở rộng rollout. Cửa sổ này có thể dựa trên:

- Một chu kỳ traffic cao/thấp.
- Thời gian hoàn thành job nền quan trọng.
- Thời gian replication bắt kịp.
- Một số lượng request hoặc giao dịch đại diện.
- Ngưỡng error rate/latency trong khoảng liên tục.

Không kết luận ổn định chỉ vì vài phút đầu không có lỗi nếu workload thực tế chỉ xuất hiện theo giờ hoặc theo batch.

## 11. Đặt tiêu chí PASS/FAIL có thể đo được

Mỗi gate nên mô tả điều kiện theo dạng có thể kiểm tra, tránh câu chung như “database hoạt động bình thường”.

Ví dụ bảng tiêu chí:

| Gate | PASS | FAIL |
|---|---|---|
| Target identity | DB/schema/role trùng release manifest | Bất kỳ thành phần nào không khớp |
| Changelog validation | Validate thành công, không có checksum conflict | Parse/validation/checksum lỗi |
| Pending changesets | Đúng tập changeset đã review | Có changeset ngoài phạm vi hoặc thiếu changeset bắt buộc |
| Data precondition | Tất cả assertion đạt expected result | Có dữ liệu vi phạm hoặc không thể kiểm tra |
| SQL review | Preview khớp kế hoạch và được phê duyệt | Có DDL phá hủy/chưa review |
| Runtime execution | Update kết thúc theo trạng thái dự kiến | Lỗi, timeout hoặc partial failure chưa reconcile |
| History | DATABASECHANGELOG khớp identity/checksum | Thiếu, sai hoặc có trạng thái bất thường |
| Schema | Metadata đúng hậu điều kiện | Object thiếu/sai/invalid |
| Data | Assertion đạt | Dữ liệu sai hoặc chưa đủ |
| Application | Smoke test và SLO đạt | Lỗi chức năng hoặc vượt ngưỡng |
| Evidence | Log, release, approval và kết quả được lưu | Thiếu bằng chứng bắt buộc |

Ngưỡng số cần được cấu hình theo hệ thống. Ví dụ, nếu SLO quy định p95 latency không tăng quá mức đã phê duyệt trong cửa sổ quan sát, pipeline cần đo p95 trước/sau và dùng đúng ngưỡng đó. Không tự chọn một con số tùy tiện trong changeset.

### Phân biệt FAIL và UNKNOWN

- **PASS:** có bằng chứng và đạt tiêu chí.
- **FAIL:** có bằng chứng vi phạm tiêu chí.
- **UNKNOWN:** không đủ dữ liệu hoặc không thể kiểm tra.

Với gate bắt buộc, UNKNOWN không được tự động coi là PASS. Ví dụ, không đọc được metadata index vì thiếu quyền thì trạng thái là UNKNOWN, cần sửa quyền hoặc dùng truy vấn kiểm tra được phê duyệt.

## 12. Quy tắc dừng theo từng giai đoạn

| Giai đoạn | Điều kiện dừng | Hành động an toàn tiếp theo |
|---|---|---|
| Trước update | Sai target, validate lỗi, checksum bất thường, precondition FAIL | Không chạy; điều tra cấu hình/changelog/dữ liệu |
| Sau SQL preview | Có DROP/ALTER ngoài kế hoạch, thiếu approval | Sửa kế hoạch, review lại preview |
| Đang thực thi | Lock/resource/error vượt ngưỡng | Dừng mở bước tiếp theo; đánh giá statement đang chạy |
| Update lỗi | Không rõ DDL đã commit tới đâu | Chuyển RECONCILIATION_REQUIRED; kiểm tra object và lịch sử |
| Postflight lỗi | Schema/data không đạt | Chặn ứng dụng/wave phụ thuộc; chọn forward-fix/rollback/restore |
| Smoke test lỗi | DB đúng nhưng ứng dụng không tương thích | Dừng rollout ứng dụng; đánh giá rollback code hoặc forward-fix |
| Observation lỗi | SLO vượt ngưỡng | Dừng promotion/wave; điều tra và giảm tải |
| Evidence thiếu | Không chứng minh được trạng thái | Chưa đóng release; bổ sung bằng chứng |

Một lệnh update trả lỗi không cho biết chắc mọi thay đổi đã được hoàn tác. Với DDL implicit commit hoặc changeset runInTransaction=false, có thể có một phần tác động đã tồn tại. Luôn xác minh trước khi retry.

## 13. Phân loại trạng thái khi job thất bại hoặc bị ngắt

Đối với CI/CD hoặc orchestrator, nên dùng trạng thái rõ ràng:

- **QUEUED:** đã được chọn, chưa bắt đầu.
- **PREFLIGHT:** đang xác minh target và điều kiện.
- **RUNNING:** Liquibase đang thực thi.
- **SUCCEEDED:** update và mọi postflight bắt buộc đã đạt.
- **FAILED:** thất bại đã được phân loại, trạng thái database được hiểu rõ.
- **RECONCILIATION_REQUIRED:** job bị ngắt hoặc partial failure chưa rõ trạng thái.
- **BLOCKED:** cần quyết định hoặc can thiệp của người có trách nhiệm.
- **SKIPPED:** được hoãn/bỏ qua theo ngoại lệ đã phê duyệt.

Ví dụ:

~~~text
QUEUED
  |
  v
PREFLIGHT ---- FAIL ----> BLOCKED
  |
 PASS
  v
RUNNING ------ ERROR ---> RECONCILIATION_REQUIRED
  |
  v
POSTFLIGHT --- FAIL ----> BLOCKED
  |
 PASS
  v
OBSERVING ---- SLO FAIL -> BLOCKED
  |
 PASS
  v
SUCCEEDED
~~~

Trạng thái này thuộc pipeline/orchestrator; nó không phải EXECTYPE của Liquibase. DATABASECHANGELOG vẫn là nguồn lịch sử changeset ở database. Registry trung tâm là nguồn trạng thái điều phối.

Nếu worker crash sau khi Liquibase hoàn tất nhưng trước khi ghi SUCCEEDED, không đánh dấu FAILED rồi chạy lại mù. Đọc DATABASECHANGELOG, kiểm tra schema/data, xác nhận release ID và chỉ sau đó reconcile registry.

## 14. Xử lý partial failure và quyết định phục hồi

Khi lỗi xảy ra, thực hiện theo thứ tự:

1. **Ngừng rollout mới:** không triển khai tenant/wave hoặc ứng dụng phụ thuộc tiếp theo.
2. **Giữ bằng chứng:** log, job ID, statement cuối, thời gian, DBMS session và lỗi.
3. **Xác nhận tiến trình:** Liquibase còn chạy không, session nào giữ lock, có DDL đang cleanup không.
4. **Đối chiếu lịch sử:** changeset nào đã được ghi nhận, checksum và EXECTYPE.
5. **Đối chiếu schema thật:** object nào đã tạo/sửa/xóa, index có valid không, constraint có validate không.
6. **Đối chiếu dữ liệu:** có hàng nào đã backfill/xóa/chuyển đổi một phần?
7. **Chọn phương án:** tiếp tục, retry sau reconcile, rollback, forward-fix hoặc restore.
8. **Chạy lại gate:** preflight, review, postflight và observation theo phạm vi bị ảnh hưởng.

### Khi nào retry?

Retry chỉ phù hợp khi nguyên nhân transient đã được xử lý và trạng thái database chứng minh thao tác có thể chạy lại an toàn. Ví dụ, lỗi kết nối xảy ra trước khi statement bắt đầu có thể retry sau khi xác nhận không có tác động.

### Khi nào không retry?

- Index invalid hoặc object một phần còn sót.
- DDL có thể đã commit nhưng history chưa ghi.
- Backfill đã cập nhật một phần mà không có checkpoint/idempotency.
- Checksum mismatch hoặc schema drift chưa giải thích.
- Constraint fail vì dữ liệu không hợp lệ.
- Không xác định được statement cuối đã hoàn tất hay chưa.

### Chọn rollback, forward-fix hay restore

Rollback phù hợp khi change có logic đảo ngược đã thử và không làm mất dữ liệu mới. Forward-fix phù hợp khi schema mới đã được ứng dụng sử dụng hoặc rollback làm tăng rủi ro. Restore/PITR dành cho tình huống cần phục hồi dữ liệu hoặc cấu trúc mà migration không thể đảo an toàn, với RPO/RTO và ảnh hưởng giao dịch sau mốc đã được đánh giá.

## 15. Đặt stop threshold cho tài nguyên và SLO

Ngưỡng dừng cần gắn với rủi ro cụ thể:

| Chỉ số | Ngưỡng ví dụ cần xác định trước | Hành động nếu vượt |
|---|---|---|
| Lock wait | Thời gian chờ tối đa theo SLA | Không mở bước tiếp theo; xác minh transaction blocker |
| Statement duration | Giới hạn theo operation/maintenance window | Đánh giá tiến độ và tác động trước khi cancel |
| Replication lag | Mức lag tối đa chấp nhận | Tạm dừng wave, theo dõi khả năng bắt kịp |
| Disk free | Dung lượng tối thiểu để hoàn thành index/table copy | Dừng trước khi cạn đĩa; giải phóng/tăng dung lượng có kiểm soát |
| CPU/I/O | Ngưỡng giữ được latency hệ thống | Giảm concurrency hoặc dừng wave |
| API error rate | Ngưỡng error budget/SLO | Dừng promotion, điều tra tương thích |
| p95/p99 latency | Mức tăng tối đa so với baseline | Dừng rollout hoặc giảm tải |
| Deadlock/timeout | Tần suất vượt ngưỡng | Kiểm tra lock order và workload |
| Backfill progress | Không đạt throughput hoặc checkpoint | Pause job dữ liệu và điều tra |

Đây là các loại ngưỡng, không phải giá trị mặc định. Đội vận hành cần lấy baseline từ hệ thống thật, định nghĩa cửa sổ đo và phân biệt cảnh báo với ngưỡng bắt buộc dừng.

Không nên dừng một migration đang trong giai đoạn cleanup mà không hiểu hậu quả. Ngưỡng có thể buộc dừng **promotion** ngay lập tức trong khi owner xử lý statement đang chạy theo runbook DBMS.

## 16. Tiêu chí hoàn tất cho từng changeset

Mỗi changeset nên có tiêu chí hoàn tất tương ứng với tác động của nó. Có thể ghi trong review/PR/runbook:

~~~text
CHANGESET:
  id: 060-invoice-status-not-null
  author: billing-team
  target: customer_db / public
  expected_schema:
    - invoice.status exists
    - data_type = varchar(30)
    - is_nullable = NO
  expected_data:
    - count(status IS NULL) = 0
  liquibase_history:
    - id/author/path matches
    - checksum matches approved artifact
    - execution type is expected
  application:
    - runtime role can insert/update/read
    - invalid NULL write is rejected as designed
  operations:
    - error rate and latency within release SLO
    - replication lag within agreed limit
  decision: PASS / FAIL / UNKNOWN
~~~

Mẫu này giúp reviewer thấy rõ thay đổi được coi là hoàn tất khi nào. Nếu một changeset chỉ tạo index, tiêu chí cần xác minh index đúng định nghĩa và trạng thái hợp lệ; không cần kiểm tra cột không liên quan. Nếu backfill dữ liệu, phải có expected row count hoặc assertion nghiệp vụ.

Không nên viết tiêu chí chung như “Liquibase update thành công”. Cần nêu object, dữ liệu, ứng dụng và ngưỡng vận hành liên quan.

## 17. Completion criteria cho toàn bộ release

Release chỉ được đóng khi tất cả điều kiện bắt buộc sau đạt:

### Kỹ thuật

- Update kết thúc theo trạng thái dự kiến.
- Changeset bắt buộc được ghi nhận đúng trong DATABASECHANGELOG.
- Không có checksum conflict chưa giải quyết.
- Schema/object đạt hậu điều kiện.
- Data assertions đạt.
- Không có partial failure chưa reconcile.
- Ứng dụng và role runtime hoạt động đúng.

### Vận hành

- Error rate, latency, lock và replication lag nằm trong ngưỡng.
- Các tenant/database bắt buộc trong scope đã hoàn thành hoặc ngoại lệ đã được phê duyệt.
- Không có migration job khác đang giữ quyền sở hữu target.
- Monitoring và cảnh báo trở về trạng thái chấp nhận được.
- Cửa sổ quan sát sau release đã hoàn thành nếu policy yêu cầu.

### Quản trị và bằng chứng

- Release ID, commit, artifact và Liquibase version được ghi lại.
- SQL preview, approval và execution log được lưu.
- Kết quả preflight/postflight và người xác nhận được lưu.
- Snapshot/schema evidence hoặc truy vấn kiểm tra được lưu khi policy yêu cầu.
- Sự cố/ngoại lệ có owner và thời hạn xử lý.
- Runbook và trạng thái release được cập nhật.

Nếu còn một tenant bị BLOCKED nhưng được phép tạm hoãn, release tổng thể phải được mô tả là **partial rollout** hoặc **completed with approved exceptions**, không báo “all tenants succeeded”. Ngôn ngữ trạng thái phải phản ánh đúng phạm vi.

## 18. Ví dụ: release thêm NOT NULL cho invoice.status

Giả sử mục tiêu là thêm ràng buộc NOT NULL cho cột invoice.status.

**G0 — Release:** chốt changelog commit, code tương thích, tenant/database scope và người chịu trách nhiệm.

**G1 — Preflight:**

- Xác nhận database/schema/role.
- Validate changelog, xem status và checksum.
- Đếm số hàng status NULL.
- Kiểm tra ứng dụng đang chạy không tiếp tục ghi NULL.
- Xác nhận backup/forward-fix và cửa sổ triển khai.

Nếu còn NULL, G1 FAIL. Chạy backfill có checkpoint hoặc sửa dữ liệu trước khi thử lại.

**G2 — SQL review:**

- Xác nhận changeset chỉ thêm constraint dự kiến.
- Đánh giá lock của ALTER TABLE trên DBMS/version.
- Kiểm tra precondition và rollback.
- Review thời gian dự kiến, tác động đến writer và ứng dụng.

**G3 — Execution:** chạy Liquibase update với một owner, theo dõi lock, statement duration và error rate.

**G4 — Postflight:**

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'invoice'
  AND column_name = 'status';

SELECT COUNT(*) AS null_count
FROM public.invoice
WHERE status IS NULL;
~~~

Kỳ vọng đúng một cột status với nullability NO và null_count bằng 0. Đối chiếu DATABASECHANGELOG để xác nhận changeset.

**G5 — Application:** chạy smoke test tạo invoice với status hợp lệ, thử tình huống thiếu status trên database test và xác nhận ứng dụng xử lý lỗi theo thiết kế; theo dõi error rate và latency.

**G6 — Completion:** lưu log, query results, release ID, commit, approval và kết quả observation. Chỉ đóng release khi mọi gate bắt buộc PASS.

Ví dụ này cũng cho thấy nếu G4 PASS nhưng G5 FAIL, không được đánh dấu release hoàn tất. Có thể schema đúng nhưng ứng dụng chưa tương thích.

## 19. Nhiều database hoặc tenant: hoàn tất theo từng đơn vị

Với database-per-tenant hoặc schema-per-tenant, mỗi tenant cần một kết quả độc lập:

| Tenant | Liquibase update | Postflight | Trạng thái |
|---|---|---|---|
| tenant_001 | PASS | PASS | SUCCEEDED |
| tenant_002 | PASS | FAIL | BLOCKED |
| tenant_003 | Chưa chạy | Chưa chạy | QUEUED |

Không dùng một bản ghi DATABASECHANGELOG chung để suy ra mọi tenant đã chạy. Mỗi database/schema có lịch sử riêng; registry điều phối theo dõi execution state của từng tenant.

Bộ điều phối có thể rollout theo canary và wave. Nếu tenant_002 postflight FAIL, dừng wave tiếp theo theo policy, reconcile tenant_002 và đánh giá liệu tenant_003 có được phép tiếp tục độc lập không. Quyết định này cần dựa trên blast radius, tính tương thích ứng dụng và chính sách release.

**All tenants complete** chỉ khi toàn bộ tenant trong scope bắt buộc đạt completion criteria. Nếu có tenant được miễn hoặc hoãn, ghi rõ danh sách, lý do, người phê duyệt và thời hạn; không gộp trạng thái ngoại lệ thành thành công.

## 20. Tích hợp gate vào CI/CD

Pipeline nên biểu diễn mỗi gate thành một job/step có exit status rõ ràng:

~~~text
Build immutable release
        |
        v
G0: Approval + scope
        |
        v
G1: Target / validate / history / data preflight
        |
        v
G2: update-sql + review
        |
        v
G3: Liquibase update + monitoring
        |
        v
G4: DATABASECHANGELOG + schema + data assertions
        |
        v
G5: application smoke + SLO observation
        |
        v
G6: evidence + release completion
~~~

Một job không nên chỉ in “PASS” trong log mà trả mã 0 khi assertion thất bại. Ví dụ, query COUNT(*) chạy thành công nhưng trả 12 trong khi expected là 0 phải khiến gate FAIL.

Các nguyên tắc:

- Pin Liquibase, JDBC driver và changelog artifact.
- Truyền target identity rõ ràng, không lấy từ biến không kiểm soát.
- Secret lấy từ secret manager, không ghi vào log.
- Mỗi gate lưu output và release/execution ID.
- Approval production gắn với artifact và SQL đã review.
- Không cho bước deploy ứng dụng tiếp tục khi postflight bắt buộc FAIL.
- Retry chỉ sau reconcile nếu trạng thái database chưa rõ.
- Dừng wave mới khi ngưỡng vận hành vượt giới hạn.

Với Spring Boot, cần chọn rõ ai sở hữu migration: ứng dụng khi khởi động hay job riêng của CI/CD. Nếu job riêng chạy Liquibase, profile runtime thường cần tránh tự động chạy cùng changelog ngoài kế hoạch. DATABASECHANGELOGLOCK hỗ trợ điều phối Liquibase, nhưng không thay thế deployment lock và các gate pipeline.

## 21. Thiết kế báo cáo gate và bằng chứng

Một báo cáo release nên chứa đủ thông tin để người khác có thể đánh giá quyết định:

~~~text
RELEASE_ID: billing-2.4.1
CHANGELOG_COMMIT: <reviewed-commit>
LIQUIBASE_VERSION: <pinned-version>
TARGET:
  database: customer_db
  schema: public
  dbms: PostgreSQL
  version: <server-version>

GATES:
  G0_scope_and_approval: PASS
  G1_preflight: PASS
  G2_sql_review: PASS
  G3_execution: PASS
  G4_history_schema_data: PASS
  G5_application_observation: PASS
  G6_evidence: PASS

EXCEPTIONS: NONE
DECISION: COMPLETED
EVIDENCE:
  pipeline_job: <job-id>
  sql_review: <approval-id>
  preflight_results: <artifact-id>
  postflight_results: <artifact-id>
  logs: <artifact-id>
~~~

Đây là mẫu nội dung minh họa. Không đưa password, token, dữ liệu cá nhân hoặc URL có credentials vào báo cáo. Artifact có thể chứa tên schema/object nhạy cảm nên cần phân quyền truy cập.

Nếu gate không áp dụng, ghi **NOT_APPLICABLE** và lý do. Nếu chưa kiểm tra được, ghi **UNKNOWN**. Nếu một ngoại lệ được chấp thuận, ghi owner, phạm vi, thời hạn và điều kiện đóng ngoại lệ.

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ dựa vào exit code của update | Bỏ sót schema/data/app failure | Có postflight assertions |
| Không xác minh target | Thay đổi nhầm database | Gate identity trước update |
| Xem UNKNOWN như PASS | Tiếp tục khi thiếu bằng chứng | UNKNOWN chặn gate bắt buộc |
| Dừng pipeline nhưng bỏ mặc statement đang chạy | Có thể để lại partial DDL | Xác minh session và DBMS semantics |
| Retry ngay sau timeout | Thực thi trùng hoặc gặp object một phần | Reconcile history và schema trước |
| Rollback mọi lỗi | Có thể làm mất dữ liệu hoặc phá tương thích | Chọn rollback/forward-fix/restore theo trạng thái |
| Chỉ kiểm tra DATABASECHANGELOG | Bỏ qua drift sau migration | Kiểm tra metadata object thực tế |
| Đánh dấu tenant thành công trước postflight | Registry sai trạng thái | Chỉ ghi SUCCEEDED sau tất cả gate |
| Không có cửa sổ quan sát | Phát hiện lỗi muộn sau khi đã mở rộng rollout | Đặt observation criteria |
| Đóng release khi còn ngoại lệ không ghi nhận | Báo cáo sai mức hoàn tất | Ghi partial rollout/approved exceptions |

## 23. Checklist thiết lập điểm dừng và xác nhận hoàn tất

**Trước khi chạy**

- [ ] Release ID, commit, artifact và changelog đã cố định.
- [ ] Target database/schema/tenant được xác nhận.
- [ ] Migration owner và người phê duyệt đã xác định.
- [ ] Liquibase/JDBC/DBMS version đúng ma trận hỗ trợ.
- [ ] Validate, status, checksum và precondition đạt.
- [ ] Dữ liệu đáp ứng các điều kiện trước migration.
- [ ] SQL preview được review và phê duyệt.
- [ ] Rollback/forward-fix/restore plan đã được đánh giá.
- [ ] Ngưỡng lock, thời gian, tài nguyên và SLO đã đặt.

**Trong khi chạy**

- [ ] Một owner thực hiện update trên target.
- [ ] Log, DATABASECHANGELOGLOCK và session được theo dõi.
- [ ] Lock wait, resource, replication và application metrics trong ngưỡng.
- [ ] Không mở wave tiếp theo khi gate hiện tại chưa đạt.
- [ ] Khi lỗi, dừng rollout và xác minh partial failure trước retry.

**Sau khi chạy**

- [ ] DATABASECHANGELOG đúng changeset identity/checksum/EXECTYPE.
- [ ] Schema và object đạt postcondition.
- [ ] Data assertions đạt.
- [ ] Role runtime và smoke test ứng dụng đạt.
- [ ] SLO và cửa sổ quan sát đạt.
- [ ] Từng tenant/database trong scope có trạng thái riêng.
- [ ] Evidence, approval, log và release record đã lưu.
- [ ] Ngoại lệ có owner, lý do và thời hạn.
- [ ] Release chỉ được đóng khi toàn bộ điều kiện bắt buộc đạt.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, triển khai an toàn cần có điểm dừng rõ ràng từ lúc xác định release đến khi đóng release. Mỗi gate phải nêu bằng chứng và điều kiện PASS/FAIL; khi trạng thái chưa rõ, dừng rollout và reconcile database thực tế trước khi retry. Chỉ xác nhận hoàn tất khi lịch sử Liquibase, schema, dữ liệu, ứng dụng, chỉ số vận hành và bằng chứng release đều đạt tiêu chí đã thống nhất. Cách làm này giúp nhóm phát hiện sai lệch sớm, giới hạn blast radius và đưa ra quyết định phục hồi có căn cứ thay vì dựa vào một thông báo update thành công.
