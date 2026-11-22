# Hoàn thiện quy trình rà soát và tiêu chí nghiệm thu migration

Một changeset chạy thành công chưa đủ để kết luận một lần migration đã được nghiệm thu. Database có thể đã nhận DDL nhưng thiếu grant cho ứng dụng; backfill có thể hoàn tất về mặt kỹ thuật nhưng sai số hàng; index có thể tồn tại nhưng không hợp lệ; hoặc history đã ghi nhận changeset trong khi một consumer vẫn dùng schema cũ. Nghiệm thu migration phải xác nhận đồng thời **đúng thay đổi, đúng dữ liệu, đúng môi trường, đúng quyền, tương thích ứng dụng và có khả năng phục hồi**.

Bài học thuộc chương **Thực hành** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này xây dựng quy trình rà soát từ lúc nhận yêu cầu tới sau triển khai, thiết lập các cổng kiểm soát, viết tiêu chí nghiệm thu có thể đo lường, phân công trách nhiệm và lưu bằng chứng để có thể kiểm tra lại.

## 1. Nghiệm thu migration có nghĩa là gì?

**Rà soát migration** là hoạt động kiểm tra thiết kế, changelog, SQL, dữ liệu, tác động vận hành và phương án phục hồi trước khi cho phép triển khai.

**Nghiệm thu migration** là xác nhận bằng bằng chứng rằng thay đổi đã đạt trạng thái mong đợi sau khi thực thi, đồng thời ứng dụng và các hệ thống phụ thuộc có thể hoạt động theo hợp đồng mới.

Hai hoạt động liên quan nhưng ở hai thời điểm khác nhau:

- Review trước triển khai trả lời: thay đổi có an toàn và có thể triển khai theo kế hoạch không?
- Acceptance sau triển khai trả lời: database thực tế có đạt trạng thái đã cam kết không?

Một pipeline xanh chỉ chứng minh các bước pipeline đã kết thúc theo điều kiện của nó. Nếu pipeline chỉ chạy liquibase update và kiểm tra exit code, nó chưa chắc đã kiểm tra dữ liệu, quyền runtime, hiệu năng, consumer hay khả năng rollback.

### 1.1. Sáu chiều cần nghiệm thu

| Chiều | Câu hỏi cần trả lời | Bằng chứng điển hình |
|---|---|---|
| Nội dung schema | Object có đúng định nghĩa và nằm đúng schema không? | Metadata catalog, schema diff, truy vấn kiểm tra. |
| Dữ liệu | Backfill/seed có đủ, đúng và không trùng không? | Count, aggregate, invariant, đối soát nguồn. |
| Lịch sử Liquibase | Changeset được ghi nhận đúng và checksum nhất quán không? | DATABASECHANGELOG, status, deployment log. |
| Quyền và bảo mật | Migration role và runtime role có đúng quyền không? | Grants, current user, kiểm thử quyền. |
| Tương thích và vận hành | Ứng dụng, consumer, lock, latency và replication có ổn không? | Integration/smoke test, metrics, logs. |
| Khả năng phục hồi | Có thể xử lý khi lỗi mà không mất dữ liệu ngoài dự kiến không? | Rollback SQL, forward fix, backup/PITR và diễn tập. |

Không nên thay thế một chiều bằng chiều khác. Ví dụ schema diff sạch không chứng minh backfill đúng; DATABASECHANGELOG có hàng không chứng minh ứng dụng runtime có quyền đọc bảng mới.

## 2. Quy trình từ yêu cầu tới nghiệm thu

Một quy trình thực tế có thể chia thành tám cổng. Mỗi cổng có đầu vào, người chịu trách nhiệm và điều kiện để chuyển bước.

~~~mermaid
flowchart TD
    A[1. Tiếp nhận yêu cầu và phạm vi] --> B[2. Thiết kế schema và dữ liệu]
    B --> C[3. Review changelog và SQL]
    C --> D[4. Validate và thử trên DB đại diện]
    D --> E[5. Readiness và phê duyệt triển khai]
    E --> F[6. Thực thi có giám sát]
    F --> G[7. Kiểm tra hậu điều kiện]
    G --> H{Đạt tiêu chí nghiệm thu?}
    H -->|Có| I[8. Ghi nhận và đóng release]
    H -->|Không| J[Incident: dừng, điều tra, phục hồi]
    J --> G
~~~

### Cổng 1 — Tiếp nhận yêu cầu và phạm vi

Trước khi viết changeset, ghi rõ:

- Vấn đề nghiệp vụ hoặc kỹ thuật cần giải quyết.
- Database, catalog, schema và service bị ảnh hưởng.
- Object sẽ tạo/sửa/xóa: table, column, index, constraint, view, sequence, routine.
- Dữ liệu cần backfill, seed, chuẩn hóa hoặc loại bỏ.
- Các ứng dụng, job, báo cáo và consumer phụ thuộc.
- Môi trường và thứ tự triển khai.
- Yêu cầu downtime, lock, throughput và thời gian chạy tối đa.
- RPO/RTO và phương án phục hồi phù hợp mức độ rủi ro.

Phạm vi phải phân biệt thay đổi cần thiết với thay đổi tiện thể. Một migration không nên gom nhiều mục tiêu độc lập chỉ vì chúng cùng liên quan một bảng.

**Điều kiện qua cổng:** owner dữ liệu và owner ứng dụng hiểu cùng một trạng thái đích; đã xác định database/schema, consumer và tác động chính.

### Cổng 2 — Thiết kế schema và dữ liệu

Thiết kế changeset theo trạng thái trước và sau:

1. Mô tả schema hiện tại và schema đích.
2. Xác định thứ tự expand, migrate, validate và contract nếu có thay đổi phá vỡ tương thích.
3. Định nghĩa dữ liệu đầu vào, điều kiện lọc, mapping và hậu điều kiện.
4. Xác định transaction boundary, DDL behavior và khả năng retry.
5. Xác định quyền migration và quyền runtime.
6. Đánh giá lock, index build, replication lag và dung lượng.
7. Viết rollback hoặc mô tả lý do chọn forward recovery/restore.

Với backfill lớn, ước lượng số hàng, batch size, tốc độ xử lý và thời gian dự kiến. Đừng mặc định một câu UPDATE trên toàn bảng là an toàn chỉ vì chạy nhanh trên database nhỏ.

**Điều kiện qua cổng:** có mô tả trạng thái đích, cách kiểm tra và phương án xử lý khi từng bước thất bại.

### Cổng 3 — Review changelog và SQL

Reviewer kiểm tra:

- ID, author, filename/logical path ổn định.
- Changeset đã phát hành không bị sửa nội dung tùy tiện.
- Include order và root changelog đúng.
- Context, label, DBMS filter và precondition rõ ràng.
- Change type, schemaName/catalogName và object name chính xác.
- SQL native phù hợp DBMS và version.
- Rollback hoặc forward recovery được xem xét.
- DML có điều kiện lọc, before-image/checkpoint khi cần.
- Không có secret hoặc thông tin môi trường cố định trong changelog.

**Điều kiện qua cổng:** một reviewer khác tác giả có thể giải thích được changeset sẽ làm gì, phạm vi tác động và cách xác minh.

### Cổng 4 — Validate và thử trên database đại diện

Chạy các kiểm tra phù hợp:

- liquibase validate để kiểm tra changelog và tham chiếu.
- liquibase status --verbose để biết changeset pending theo cấu hình hiện tại.
- liquibase update-sql hoặc command SQL preview tương ứng để review SQL sẽ chạy.
- Test migration trên DBMS/version đại diện.
- Test database sạch và database đã nâng từ phiên bản cũ.
- Kiểm tra schema/data, permissions, lock và hiệu năng.
- Sinh SQL rollback preview và thử rollback nếu phương án rollback được chọn.

validate không thay thế việc thực thi trên DBMS. Nó không chứng minh mọi câu SQL native chạy thành công, dữ liệu hợp lệ hay thời gian lock nằm trong giới hạn. status cũng không phải schema drift detector toàn diện.

Tên command và option có thể khác giữa các phiên bản Liquibase. Kiểm tra liquibase --help và tài liệu của phiên bản dự án trước khi đưa vào pipeline.

**Điều kiện qua cổng:** kiểm tra tĩnh đạt, thử nghiệm DBMS đại diện đạt và có log/bằng chứng.

### Cổng 5 — Readiness và phê duyệt triển khai

Trước cửa sổ release, xác nhận:

- Đúng artifact ứng dụng và changelog đã được review.
- Đúng URL/database/schema và Liquibase version.
- Secret migration còn hiệu lực và được cấp đúng môi trường.
- Migration role có quyền cần thiết; runtime role có quyền sau migration.
- Không có migration hoặc DDL khác đang chạy cạnh tranh.
- Backup/PITR hoặc restore point phù hợp đã sẵn sàng nếu rủi ro yêu cầu.
- Có người theo dõi, người quyết định dừng và kênh liên lạc.
- Có ngưỡng dừng và phương án phục hồi cụ thể.

**Điều kiện qua cổng:** owner triển khai và owner database xác nhận readiness; không còn blocker nghiêm trọng chưa có phương án.

### Cổng 6 — Thực thi có giám sát

Khi chạy migration:

1. Ghi nhận deployment ID, commit/artifact, database identity và thời điểm bắt đầu.
2. Chạy đúng command, context, label và changelog đã được phê duyệt.
3. Theo dõi Liquibase log, DBMS session, lock, CPU, I/O và replication lag.
4. Dừng theo runbook nếu vượt ngưỡng hoặc gặp lỗi ngoài dự kiến.
5. Không chạy retry song song hoặc xóa lock khi chưa xác định process.
6. Ghi nhận changeset đã chạy, bị bỏ qua hoặc thất bại.

**Điều kiện qua cổng:** command kết thúc theo kết quả dự kiến, không còn migration process/lock bất thường và có log đủ để truy vết.

### Cổng 7 — Kiểm tra hậu điều kiện

Kiểm tra schema, dữ liệu, history, quyền và ứng dụng theo tiêu chí định trước. So sánh trạng thái thực tế với trạng thái đích, không chỉ dựa vào exit code.

**Điều kiện qua cổng:** tất cả tiêu chí bắt buộc đạt hoặc có ngoại lệ được owner chấp nhận, ghi rõ phạm vi và thời hạn xử lý.

### Cổng 8 — Ghi nhận và đóng release

Lưu artifact, log, SQL preview, kết quả hậu kiểm, quyết định và ngoại lệ. Cập nhật trạng thái release và thông báo kết quả theo quy trình tổ chức.

**Điều kiện đóng:** có bằng chứng, owner và thời điểm nghiệm thu; các việc còn lại có người nhận và deadline.

## 3. Xây dựng tiêu chí nghiệm thu đo lường được

Một tiêu chí tốt mô tả trạng thái mong đợi, phép đo, nguồn bằng chứng và ngưỡng đạt. Các từ như “đã chạy tốt”, “không có vấn đề” hoặc “schema ổn” không đủ cụ thể để nghiệm thu.

### 3.1. Mẫu tiêu chí

| Thành phần | Nội dung |
|---|---|
| Điều kiện | Trạng thái hoặc hành vi phải đạt. |
| Phép kiểm tra | SQL, command, test hoặc metric dùng để xác minh. |
| Ngưỡng đạt | Giá trị cụ thể hoặc kết quả mong đợi. |
| Bằng chứng | Log, query result, report hoặc artifact lưu lại. |
| Owner | Người xác nhận kết quả. |
| Thời điểm | Trước, trong hay sau migration. |

Ví dụ:

| Tiêu chí | Phép kiểm tra | Ngưỡng đạt |
|---|---|---|
| Cột mới có đúng kiểu và nullability | Đọc system catalog hoặc schema diff | Kiểu VARCHAR(80), nullable theo thiết kế, đúng schema. |
| Backfill đủ dữ liệu | Đếm hàng đủ điều kiện còn thiếu giá trị | missing_rows = 0 tại snapshot/điều kiện đã định. |
| Không tạo duplicate | Group by business key | Số nhóm duplicate mới bằng 0. |
| Changeset được ghi nhận | Đọc DATABASECHANGELOG | Đúng ID/author/path, execution type dự kiến. |
| Runtime có quyền | Chạy smoke query bằng runtime role | SELECT/DML cần thiết thành công; DDL bị từ chối nếu policy yêu cầu. |
| Không gây suy giảm ngoài ngưỡng | Theo dõi latency/lock/replication | Trong SLO/ngưỡng đã thống nhất. |
| Phục hồi đã sẵn sàng | Kiểm tra backup/restore drill | Restore point hợp lệ và runbook có owner. |

Ngưỡng cụ thể phải do hệ thống và owner xác định. Không áp dụng con số latency hoặc thời gian downtime chung cho mọi database.

### 3.2. Tiêu chí schema

Tối thiểu xác minh:

- Table/column tồn tại trong đúng catalog/schema.
- Data type, precision/scale, length, nullability và default đúng.
- Primary key, unique, foreign key, check constraint đúng.
- Index tồn tại, definition đúng và trạng thái hợp lệ.
- View, trigger, function/procedure có definition đúng.
- Sequence/identity và ownership đúng.
- Grants và owner đúng.
- Không tạo object thừa hoặc object trùng tên ngoài dự kiến.

Với index PostgreSQL tạo concurrently, chỉ thấy tên index trong catalog chưa đủ. Kiểm tra trạng thái hợp lệ, ví dụ pg_index.indisvalid và indisready.

### 3.3. Tiêu chí dữ liệu

Đối với backfill hoặc data migration, cần định nghĩa:

- Tập hàng đủ điều kiện.
- Tập hàng đã xử lý.
- Tập hàng còn thiếu.
- Số hàng bị bỏ qua và lý do.
- NULL/duplicate/orphan/giá trị ngoài miền cho phép.
- Mapping từ dữ liệu cũ sang dữ liệu mới.
- Bất biến nghiệp vụ phải giữ.
- Cách kiểm tra khi có ghi đồng thời.

Ví dụ PostgreSQL:

~~~sql
-- Tổng số hàng cần được backfill
SELECT COUNT(*) AS eligible_rows
FROM customer_profile
WHERE preferred_language IS NULL
  AND migration_source = 'legacy';

-- Số hàng còn thiếu sau backfill
SELECT COUNT(*) AS missing_rows
FROM customer_profile
WHERE migration_source = 'legacy'
  AND preferred_language IS NULL;

-- Phát hiện khóa nghiệp vụ bị trùng
SELECT customer_id, COUNT(*) AS row_count
FROM customer_profile
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Các truy vấn là ví dụ và phải điều chỉnh theo quy tắc nghiệp vụ. Nếu dữ liệu thay đổi liên tục, count trước/sau có thể không so sánh được nếu không dùng snapshot, transaction phù hợp hoặc kiểm soát luồng ghi.

Không chỉ kiểm tra tổng số hàng. Hai tập dữ liệu có cùng count vẫn có thể khác nội dung. Với migration quan trọng, dùng đối soát theo khóa, checksum/aggregate có phân vùng, hoặc so sánh từng nhóm dữ liệu theo quy tắc nghiệp vụ.

## 4. Review changeset trước khi nghiệm thu

### 4.1. Danh tính và tính bất biến

Changeset đã chạy ở môi trường chia sẻ phải được xem như lịch sử bất biến. Kiểm tra:

- ID không trùng trong phạm vi định danh.
- Author rõ ràng.
- Filename/logical path ổn định.
- Nội dung không bị sửa sau khi đã triển khai.
- Checksum mismatch đã được điều tra, không chỉ xóa checksum để làm pipeline xanh.
- Thay đổi mới được biểu diễn bằng changeset mới khi cần sửa lịch sử.

### 4.2. Precondition

Precondition phải kiểm tra giả định mà changeset thực sự phụ thuộc. tableExists chỉ chứng minh bảng tồn tại; nó không chứng minh cột đúng kiểu, index hợp lệ hay dữ liệu đã sạch.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 080-add-preferred-language
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: customer
            tableName: customer_profile
        - not:
            - columnExists:
                schemaName: customer
                tableName: customer_profile
                columnName: preferred_language
      changes:
        - addColumn:
            schemaName: customer
            tableName: customer_profile
            columns:
              - column:
                  name: preferred_language
                  type: VARCHAR(80)
~~~

Ví dụ minh họa precondition trên bảng/cột. Trước khi áp dụng, kiểm tra cú pháp YAML và behavior trên phiên bản Liquibase cụ thể. Nếu cột đã tồn tại, HALT giúp yêu cầu điều tra drift thay vì tự bỏ qua một trạng thái không rõ.

### 4.3. Transaction và DDL

Reviewer phải nhận diện:

- Changeset có chạy trong transaction không?
- DBMS có transactional DDL cho statement đó không?
- Có statement như concurrent index build cần chạy ngoài transaction không?
- Nếu statement giữa chừng thất bại, side effect nào có thể còn?
- Retry có tạo duplicate hoặc ghi đè dữ liệu không?

Một changeset chứa nhiều DDL không transactional có thể để lại trạng thái dở dang. Chia theo ranh giới phục hồi và viết hậu kiểm cho từng bước.

### 4.4. Rollback và forward recovery

Không phải thay đổi nào cũng có thể rollback an toàn. Review cần phân loại:

| Thay đổi | Câu hỏi cần review |
|---|---|
| Add column | Nếu drop column, dữ liệu mới có mất không? |
| Rename/drop column | Binary cũ/mới và consumer có tương thích không? |
| Modify data type | Có truncation, overflow hoặc mất precision không? |
| Update/delete | Có before-image hoặc nguồn phục hồi không? |
| Create/drop index | Lock, validity và ảnh hưởng query plan thế nào? |
| Constraint | Dữ liệu hiện tại có đáp ứng và ứng dụng có bị từ chối ghi không? |
| SQL native | Có rollback rõ và đúng DBMS không? |

Nếu rollback không an toàn, ghi rõ phương án forward fix hoặc restore/PITR. Không có rollback không nhất thiết chặn mọi migration, nhưng phải có chiến lược phục hồi phù hợp rủi ro.

## 5. Kiểm tra SQL preview và schema diff

### 5.1. SQL preview

Trước khi thực thi, sinh SQL từ đúng root changelog, URL, context, label và schema sẽ dùng. Reviewer cần đọc:

- SQL có đúng object và schema không?
- Có DROP/DELETE/TRUNCATE ngoài dự kiến không?
- Có default hoặc constraint gây table rewrite/lock không?
- Có tạo index theo cách phù hợp quy mô bảng không?
- Có DML thiếu WHERE hoặc điều kiện quá rộng không?
- Có statement phụ thuộc thứ tự không?
- Có câu lệnh chỉ hợp lệ trên một DBMS khác không?

SQL preview cần được lưu cùng artifact/commit để biết chính xác nội dung đã review.

### 5.2. Schema diff

Schema diff có thể giúp tìm drift giữa database và changelog/model tham chiếu. Tuy nhiên:

- Diff không thay thế review SQL.
- Diff không kiểm tra dữ liệu nghiệp vụ.
- Diff có thể hiển thị khác biệt do DBMS normalize metadata.
- Một schema hiện tại đúng không chứng minh migration đã được chạy đúng lịch sử.
- Một diff rỗng không chứng minh grants, performance hay consumer đều đúng.

Khi dùng diff, xác định rõ source/target, schema filter và object được so sánh. Không tự động biến mọi diff thành changeset để triển khai mà không review.

### 5.3. Phân biệt validate, status, update-sql và update

| Lệnh | Mục đích | Không chứng minh |
|---|---|---|
| validate | Kiểm tra cấu trúc/tham chiếu changelog theo Liquibase. | SQL chắc chắn chạy, dữ liệu đúng, hiệu năng đạt. |
| status --verbose | Liệt kê changeset Liquibase coi là pending. | Schema drift đã được phát hiện toàn diện. |
| update-sql | Sinh SQL dự kiến sẽ chạy. | SQL đã chạy hoặc database sẽ chấp nhận mọi statement. |
| update | Thực thi changeset pending. | Nghiệm thu dữ liệu, quyền runtime và ứng dụng. |
| rollback-sql | Sinh SQL rollback dự kiến. | Rollback an toàn trên dữ liệu hiện tại. |
| diff | So sánh schema theo source/target được cấu hình. | History và dữ liệu nghiệp vụ đúng. |

Nghiệm thu cần kết hợp nhiều loại bằng chứng.

## 6. Kiểm thử trên các trạng thái database khác nhau

Một migration có thể chạy trên database mới nhưng thất bại trên database đã tồn tại lâu năm. Review và test cần bao phủ các trạng thái thực tế.

### 6.1. Ma trận môi trường kiểm thử

| Trạng thái | Mục tiêu kiểm tra |
|---|---|
| Database sạch | Root changelog tạo được schema cuối đúng. |
| Database nâng từ release gần nhất | Changeset mới chạy đúng và không phá dữ liệu cũ. |
| Database có dữ liệu gần production | Backfill, constraint, unique và hiệu năng đạt. |
| Database đã có drift được mô phỏng | Precondition phát hiện trạng thái bất thường đúng cách. |
| Database đã chạy một phần migration trong lab | Retry/recovery có thể đưa về trạng thái nhất quán. |
| Database với runtime role hạn chế | Ứng dụng dùng được object mới mà không cần DDL. |
| Database có nhiều instance/app version | Rolling deploy và tương thích schema đạt. |

### 6.2. Kiểm thử DBMS tương đương production

H2 hoặc mock có thể hữu ích cho logic đơn giản nhưng không thay thế DBMS production khi migration dùng:

- DDL native.
- Sequence, identity, trigger hoặc stored procedure.
- Index concurrent/online.
- Lock, transaction isolation hoặc implicit commit.
- Kiểu dữ liệu, collation và JSON implementation riêng.
- Authentication, TLS và permission model.

Testcontainers hoặc database staging cùng engine/version giúp kiểm tra gần thực tế hơn. Dữ liệu test cần đại diện cho cardinality, phân bố và edge case, nhưng phải dùng dữ liệu giả lập hoặc đã được xử lý theo policy.

## 7. Đánh giá tác động vận hành

Migration đúng về schema vẫn có thể gây sự cố vận hành. Review cần xem xét thời gian chạy và ảnh hưởng tới traffic.

### 7.1. Lock và downtime

Với mỗi DDL, xác định:

- Loại lock mà DBMS cần.
- Thời gian giữ lock dự kiến.
- Có chặn SELECT/INSERT/UPDATE/DELETE không?
- Có cần timeout hoặc lock timeout không?
- Có thể chạy online/concurrently không?
- Có cần chia nhỏ hoặc thực hiện ngoài giờ cao điểm không?

Không dùng một ngưỡng lock chung cho mọi DBMS. Dựa vào thử nghiệm trên quy mô gần production và SLO của dịch vụ.

### 7.2. Index và query plan

Sau khi tạo index:

- Xác minh index tồn tại và hợp lệ.
- Kiểm tra query plan cho truy vấn mục tiêu.
- So sánh latency/rows scanned trước và sau.
- Theo dõi write amplification, disk usage và maintenance nếu liên quan.
- Đánh giá index có trùng hoặc không được sử dụng không.

Việc optimizer chưa dùng index ngay không tự động có nghĩa migration lỗi; cần xem statistics, query shape và workload.

### 7.3. Dung lượng và replication

Đối với backfill lớn hoặc tạo index:

- Ước lượng dung lượng tạm và dung lượng cuối.
- Theo dõi WAL/binlog và replication lag.
- Theo dõi disk free, IOPS, CPU và memory.
- Đặt batch size và pause/resume nếu có.
- Xác định ngưỡng dừng trước khi ảnh hưởng SLO.

### 7.4. Quan sát sau deploy

Chọn metric theo thay đổi:

- Error rate của API liên quan.
- Query latency và timeout.
- DB connection pool usage.
- Lock wait/deadlock.
- Replication lag.
- Queue lag hoặc job backlog.
- Số hàng pending trong backfill.
- Tỷ lệ dữ liệu vi phạm invariant.

Theo dõi trong một khoảng thời gian đủ đại diện cho workload; owner dịch vụ xác định khoảng thời gian và ngưỡng cụ thể.

## 8. Kiểm tra quyền và bảo mật

### 8.1. Migration role

Migration role cần quyền cho các change type trong changelog và quyền đọc/ghi bảng metadata Liquibase. Không mặc định cấp superuser hoặc db_owner.

Kiểm tra:

- Database CONNECT/access.
- Schema USAGE/CREATE hoặc quyền tương đương.
- Quyền ALTER/DROP trên object hiện có.
- Quyền sequence, routine, view, trigger nếu cần.
- Quyền đọc/ghi DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Owner/role membership theo DBMS.

### 8.2. Runtime role

Runtime role chỉ cần quyền nghiệp vụ:

- SELECT/INSERT/UPDATE/DELETE trên object được phép.
- Sequence usage hoặc execute routine cần thiết.
- Không có DDL rộng nếu không cần.
- Không cần quyền chỉnh sửa history Liquibase trong vận hành thông thường.

Sau migration, test bằng runtime credential thật hoặc role tương đương. Migration thành công không bảo đảm runtime được cấp quyền trên object mới.

### 8.3. Secret và cấu hình

- Không commit password, token hoặc certificate private key.
- Không log secret đã resolve.
- Xác minh đúng profile, URL và database identity.
- Secret migration được cấp đúng thời điểm và đúng môi trường.
- Không để staging credential trỏ nhầm production.
- Xác định quy trình xoay vòng và thu hồi credential.

## 9. Kiểm tra lịch sử Liquibase sau migration

Sau khi chạy update, kiểm tra DATABASECHANGELOG:

- ID, author và filename đúng.
- Checksum phù hợp với artifact đã triển khai.
- Execution type phù hợp với hành vi mong đợi.
- Thời điểm và deployment ID (nếu có) khớp lần release.
- Không có changeset pending ngoài dự kiến.

Kiểm tra DATABASECHANGELOGLOCK không còn lock bất thường. Nếu lock còn tồn tại, xác định process/session trước khi giải phóng.

Không chỉnh sửa trực tiếp history để làm cho báo cáo nghiệm thu đẹp hơn. Nếu history và schema lệch, tạo incident/reconciliation có bằng chứng và owner.

## 10. Tiêu chí nghiệm thu theo loại migration

### 10.1. Thêm bảng/cột

- Object nằm đúng schema.
- Kiểu dữ liệu, nullability, default và constraint đúng.
- Grant runtime đúng.
- Ứng dụng cũ/mới xử lý object mới theo thiết kế.
- Không có lock/downtime vượt ngưỡng.
- Rollback/forward recovery đã được review.

### 10.2. Thay đổi kiểu dữ liệu

- Kiểm tra dữ liệu biên, overflow, precision và truncation.
- Kiểm tra cast/conversion cho toàn bộ tập dữ liệu.
- Kiểm tra index/constraint phụ thuộc.
- Test truy vấn và serialization ở ứng dụng.
- Có cách phục hồi nếu conversion thất bại hoặc mất thông tin.

### 10.3. Backfill

- Tổng số hàng đủ điều kiện được định nghĩa.
- Số hàng đã xử lý và còn thiếu được đo.
- Duplicate/orphan/invalid value trong ngưỡng.
- Retry/resume không nhân đôi hoặc ghi đè dữ liệu mới.
- Batch/lock/replication lag nằm trong ngưỡng.
- Có audit hoặc nguồn phục hồi khi thay đổi không thể đảo.

### 10.4. Index/constraint

- Index/constraint tồn tại với definition đúng.
- Index ở trạng thái hợp lệ.
- Constraint được validate hoặc có trạng thái validation đúng theo kế hoạch.
- Query plan và write overhead được đánh giá.
- Dữ liệu hiện tại đáp ứng constraint.
- Rollback không làm mất dữ liệu hợp lệ.

### 10.5. Rename/drop/contract

- Không còn consumer sử dụng tên/object cũ.
- Tất cả ứng dụng/job đã chuyển đổi.
- Có quan sát đủ lâu để chứng minh không còn dependency.
- Dữ liệu cần giữ đã được chuyển và đối soát.
- Binary rollback có tương thích với schema sau contract không?
- Backup/restore hoặc forward recovery đã được đánh giá.

## 11. Ví dụ: bộ tiêu chí nghiệm thu cho một migration backfill

**Yêu cầu:** thêm preferred_language vào bảng customer_profile, điền giá trị từ nguồn cũ và sau đó ứng dụng sử dụng cột mới.

### 11.1. Thiết kế changelog minh họa

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 090-add-preferred-language
      author: customer-team
      changes:
        - addColumn:
            schemaName: customer
            tableName: customer_profile
            columns:
              - column:
                  name: preferred_language
                  type: VARCHAR(80)

  - changeSet:
      id: 091-backfill-preferred-language
      author: customer-team
      changes:
        - sql:
            sql: >
              UPDATE customer.customer_profile
              SET preferred_language = legacy_language
              WHERE preferred_language IS NULL
                AND legacy_language IS NOT NULL;
~~~

Ví dụ này chỉ minh họa cấu trúc. Với bảng lớn, nên cân nhắc backfill theo batch/job riêng, checkpoint, transaction và giới hạn lock. Nếu legacy_language không phải nguồn chuẩn hoặc có giá trị ngoài miền hợp lệ, cần mapping và precondition/validation bổ sung.

### 11.2. Tiêu chí trước triển khai

- customer.customer_profile tồn tại.
- preferred_language chưa tồn tại.
- Đã xác định mapping và tập hàng cần backfill.
- Đã đo cardinality, NULL, giá trị ngoài miền và duplicate.
- Đã test trên DBMS/version tương đương.
- SQL preview đã được review.
- Runtime role sẽ có quyền cần thiết.
- Có phương án nếu backfill thất bại giữa chừng.

### 11.3. Tiêu chí sau triển khai

Ví dụ truy vấn:

~~~sql
SELECT COUNT(*) AS missing_language
FROM customer.customer_profile
WHERE legacy_language IS NOT NULL
  AND preferred_language IS NULL;

SELECT COUNT(*) AS mismatched_language
FROM customer.customer_profile
WHERE legacy_language IS NOT NULL
  AND preferred_language <> legacy_language;
~~~

Nếu có mapping chuẩn hóa, truy vấn so sánh phải dùng cùng mapping thay vì so sánh trực tiếp. Cần xử lý riêng trường hợp NULL vì phép so sánh SQL với NULL không trả TRUE/FALSE như giá trị thông thường.

Tiêu chí đạt có thể là:

- missing_language = 0 cho tập hàng đủ điều kiện tại snapshot kiểm tra.
- mismatched_language = 0 sau khi áp dụng mapping.
- Không phát sinh duplicate business key.
- DATABASECHANGELOG có cả changeset schema và backfill với định danh/checksum mong đợi.
- Runtime role đọc/ghi được cột.
- API smoke test và consumer test đạt.
- Lock/latency/replication nằm trong ngưỡng đã phê duyệt.

### 11.4. Khi dữ liệu tiếp tục thay đổi

Nếu ứng dụng vẫn ghi vào legacy_language trong lúc backfill, một truy vấn count đơn lẻ có thể trở nên stale ngay sau khi chạy. Cần chọn một chiến lược:

- Dual-write có kiểm soát trong giai đoạn chuyển đổi.
- CDC hoặc job đồng bộ liên tục.
- Tạm hạn chế ghi trong cửa sổ ngắn.
- Backfill theo batch rồi chạy reconciliation cuối.

Nghiệm thu phải xác định thời điểm snapshot và cách xử lý các hàng thay đổi sau snapshot.

## 12. Checklist review trước triển khai

### Phạm vi và thiết kế

- [ ] Yêu cầu và trạng thái schema/data đích đã rõ.
- [ ] Đã liệt kê service, job, report và consumer phụ thuộc.
- [ ] Đã chọn chiến lược expand–migrate–contract nếu cần.
- [ ] Đã ước lượng số hàng, thời gian, dung lượng và lock.
- [ ] Đã xác định transaction/DDL behavior của DBMS.

### Changelog và SQL

- [ ] ID/author/path ổn định; changeset lịch sử không bị sửa sai quy trình.
- [ ] Include, context, label và DBMS filter đúng.
- [ ] Precondition kiểm tra đủ giả định.
- [ ] SQL preview đúng database/schema và đã được review.
- [ ] DML có WHERE, mapping và kiểm tra số hàng.
- [ ] Rollback/forward recovery được thiết kế và review.
- [ ] Không có secret hoặc giá trị môi trường hard-code.

### Kiểm thử

- [ ] Validate và status đã chạy.
- [ ] Test database sạch và database nâng cấp đã đạt.
- [ ] Test trên DBMS/version tương đương production.
- [ ] Test quyền migration và runtime.
- [ ] Test dữ liệu biên, duplicate, NULL và orphan.
- [ ] Test failure/retry/recovery trong lab khi cần.
- [ ] Rollback SQL preview và rollback drill đã được thực hiện nếu áp dụng.

### Readiness

- [ ] Artifact/commit đã được khóa cho release.
- [ ] URL, schema, profile và Liquibase version đúng.
- [ ] Secret và quyền đã được xác minh.
- [ ] Backup/restore point và runbook sẵn sàng theo mức rủi ro.
- [ ] Người theo dõi, người quyết định dừng và ngưỡng dừng đã rõ.

## 13. Checklist nghiệm thu sau triển khai

- [ ] Liquibase command kết thúc theo kết quả mong đợi.
- [ ] Không còn process/lock migration bất thường.
- [ ] DATABASECHANGELOG có đúng changeset, path, checksum và execution type.
- [ ] Không có changeset pending ngoài dự kiến.
- [ ] Schema object/column/type/default/constraint/index đúng.
- [ ] Index và constraint ở trạng thái hợp lệ.
- [ ] Dữ liệu backfill đạt count, mapping và invariant.
- [ ] Không có duplicate/orphan/NULL ngoài ngưỡng.
- [ ] Runtime role có đủ quyền nghiệp vụ và không có DDL rộng ngoài policy.
- [ ] Ứng dụng và consumer đọc/ghi đúng schema.
- [ ] API/job smoke test đạt.
- [ ] Latency, lock, error rate, replication lag và resource usage trong ngưỡng.
- [ ] Backup/PITR/forward recovery sẵn sàng nếu cần.
- [ ] Bằng chứng và ngoại lệ đã được lưu, owner đã xác nhận.

## 14. Mẫu biên bản nghiệm thu

Có thể dùng mẫu sau trong pull request, release record hoặc ticket triển khai:

~~~text
MIGRATION ACCEPTANCE RECORD

Service:
Environment:
Database / Catalog:
Schema:
Liquibase version:
Application version:
Changelog artifact / commit:
Deployment ID:
Execution time:

Scope:
- Changeset IDs:
- Objects changed:
- Data migration:
- Consumers affected:

Pre-deployment review:
- Changelog review:
- SQL preview:
- Validate / status:
- DBMS integration test:
- Permission review:
- Recovery plan:

Post-deployment evidence:
- DATABASECHANGELOG:
- Schema verification:
- Data verification:
- Runtime permission test:
- Application smoke test:
- Performance / lock / replication:
- Backup / recovery readiness:

Acceptance:
- Required criteria passed:
- Exceptions:
- Exception owner and due date:
- Decision: ACCEPT / REJECT / ACCEPT WITH EXCEPTIONS

Approvers:
- Migration owner:
- Database owner:
- Application owner:
- Release/incident owner:

Evidence links:
~~~

Không điền thông tin bí mật vào biên bản. Link bằng chứng phải trỏ tới hệ thống lưu trữ có quyền truy cập phù hợp.

## 15. Vai trò và trách nhiệm

| Vai trò | Trách nhiệm chính |
|---|---|
| Tác giả migration | Viết changelog, SQL preview, precondition, rollback/recovery và tiêu chí dữ liệu. |
| Reviewer database | Kiểm tra DDL/DML, transaction, lock, quyền và tác động DBMS. |
| Application owner | Xác nhận tương thích binary, repository, API và consumer. |
| Data owner | Xác nhận mapping, invariant, số liệu và kết quả đối soát. |
| Release owner | Điều phối cửa sổ, readiness, ngưỡng dừng và quyết định tiếp tục. |
| DBA/SRE | Giám sát DBMS, backup, lock, replication và hỗ trợ phục hồi. |

Một người có thể đảm nhiệm nhiều vai trò ở nhóm nhỏ, nhưng với thay đổi rủi ro cao nên có reviewer độc lập và người có quyền quyết định dừng triển khai.

## 16. Phân loại kết quả nghiệm thu

| Kết quả | Ý nghĩa | Hành động |
|---|---|---|
| ACCEPT | Tất cả tiêu chí bắt buộc đạt và bằng chứng đầy đủ. | Đóng migration/release theo quy trình. |
| ACCEPT WITH EXCEPTIONS | Tiêu chí bắt buộc đạt; còn ngoại lệ nhỏ đã có owner, deadline và biện pháp giảm rủi ro. | Theo dõi ngoại lệ tới khi đóng. |
| REJECT | Một hoặc nhiều tiêu chí bắt buộc không đạt hoặc không đủ bằng chứng. | Không mở rộng rollout; xử lý theo incident/recovery plan. |
| INCOMPLETE | Chưa thể kết luận vì thiếu dữ liệu kiểm tra hoặc môi trường chưa ổn định. | Giữ trạng thái theo dõi, bổ sung bằng chứng rồi quyết định. |

Không dùng ACCEPT WITH EXCEPTIONS cho mất dữ liệu, schema không tương thích, lỗi bảo mật nghiêm trọng hoặc không xác định được trạng thái database. Những vấn đề này cần được xử lý theo quy trình incident và quyết định rõ ràng.

## 17. Những lỗi phổ biến khi nghiệm thu

| Cách làm chưa đủ | Vì sao chưa đủ | Bổ sung cần thiết |
|---|---|---|
| Chỉ nhìn exit code 0 | Chỉ phản ánh command kết thúc thành công. | Kiểm tra schema, data, history và app. |
| Chỉ chạy validate | Không thực thi SQL trên DBMS. | Test DBMS thực tế và SQL preview. |
| Chỉ kiểm tra table exists | Bảng có thể thiếu cột/constraint hoặc sai kiểu. | Kiểm tra definition đầy đủ. |
| Chỉ đếm tổng số hàng | Count bằng nhau không chứng minh nội dung đúng. | Đối soát theo khóa và invariant. |
| Chỉ kiểm tra DATABASECHANGELOG | History có thể lệch schema thực tế. | Đọc catalog và kiểm tra dữ liệu. |
| Chỉ test bằng tài khoản migration | Runtime role có thể thiếu quyền. | Smoke test bằng runtime credential. |
| Chỉ test H2 | Khác behavior DDL, lock và kiểu dữ liệu. | Test trên DBMS tương đương production. |
| Không preview rollback | Có thể xóa dữ liệu mới hoặc không thể đảo. | Review rollback SQL và recovery alternative. |
| Không lưu bằng chứng | Không thể tái hiện hoặc audit quyết định. | Lưu log, report, query result và approver. |
| Đóng release ngay sau update | Chưa quan sát lỗi runtime hoặc workload thực. | Theo dõi post-deploy theo khoảng thời gian đã định. |

## 18. Bài thực hành hoàn chỉnh

**Bối cảnh:** hệ thống quản lý khách hàng cần thêm preferred_language, backfill từ legacy_language, tạo index cho truy vấn mới và chuyển ứng dụng sang cột mới.

### Giai đoạn A — Xác định phạm vi

1. Viết yêu cầu và trạng thái schema/data đích.
2. Liệt kê API, batch job và báo cáo đang dùng cột cũ.
3. Xác định số hàng, phân bố NULL và giá trị ngôn ngữ hiện tại.
4. Chọn expand–migrate–contract và thứ tự release.
5. Đặt tiêu chí lock, latency và thời gian chạy theo SLO.

### Giai đoạn B — Viết và review changelog

1. Tạo changeset thêm cột nullable.
2. Tạo bước backfill riêng hoặc job có checkpoint.
3. Tạo index theo phương án phù hợp DBMS.
4. Bổ sung precondition và rollback/recovery.
5. Review ID/author/path, context/label, schema và quyền.
6. Sinh SQL preview và review mọi statement.

### Giai đoạn C — Kiểm thử

1. Chạy validate/status.
2. Test database sạch và database có dữ liệu cũ.
3. Test trên DBMS/version tương đương production.
4. Test dữ liệu biên, duplicate, NULL và mapping.
5. Mô phỏng lỗi giữa backfill và index.
6. Kiểm tra retry/resume và rollback/forward fix.
7. Test runtime role và application compatibility.

### Giai đoạn D — Triển khai thử và nghiệm thu

1. Chạy migration trên staging có dữ liệu đại diện.
2. Kiểm tra history, schema và count.
3. Chạy smoke test bằng runtime credential.
4. Theo dõi lock, latency, replication lag và error rate.
5. Đối soát dữ liệu theo khóa/invariant.
6. Ghi biên bản ACCEPT/REJECT và bằng chứng.

### Giai đoạn E — Production

1. Xác nhận readiness và backup/recovery.
2. Chạy đúng artifact đã review trong cửa sổ release.
3. Theo dõi quá trình thực thi và ngưỡng dừng.
4. Chạy lại toàn bộ hậu kiểm bắt buộc.
5. Chuyển consumer sang cột mới theo rollout.
6. Chỉ contract cột cũ khi có bằng chứng không còn dependency.
7. Đóng release và lưu biên bản.

**Tiêu chí hoàn thành bài thực hành:** có thể đưa ra checklist review, tiêu chí schema/data/history/permission/performance/recovery đo lường được, thực hiện test trên DBMS đại diện, và tạo biên bản nghiệm thu có bằng chứng, owner và quyết định rõ.

## 19. Câu hỏi tự kiểm tra

1. Review migration khác nghiệm thu migration ở thời điểm và mục tiêu nào?
2. Vì sao exit code thành công chưa đủ để đóng release?
3. validate, status, update-sql và update chứng minh những điều gì?
4. Một tiêu chí nghiệm thu đo lường được cần có những thành phần nào?
5. Vì sao schema diff không chứng minh dữ liệu backfill đúng?
6. Cần kiểm tra những metadata nào của column, constraint và index?
7. Vì sao tổng số hàng bằng nhau chưa chứng minh dữ liệu giống nhau?
8. Làm sao nghiệm thu backfill khi ứng dụng vẫn ghi dữ liệu đồng thời?
9. Vì sao cần test cả database sạch và database nâng cấp từ release cũ?
10. Vì sao runtime role cần được kiểm thử riêng?
11. Khi nào rollback SQL preview là bắt buộc trong review?
12. Những metric nào cần theo dõi với migration DDL/backfill lớn?
13. Khi nào có thể chấp nhận ngoại lệ và khi nào phải reject?
14. Biên bản nghiệm thu cần lưu những bằng chứng nào?
15. Vì sao chỉ contract schema sau khi xác nhận không còn consumer cũ?

## Kết luận

Hoàn thiện quy trình rà soát và nghiệm thu migration đòi hỏi kiểm tra **changelog, SQL, schema, dữ liệu, history, quyền, tương thích ứng dụng, hiệu năng và khả năng phục hồi** theo từng cổng có bằng chứng. validate, status và exit code là những tín hiệu hữu ích nhưng không thay thế hậu kiểm trên database và ứng dụng thực tế. Khi mỗi tiêu chí có phép đo, ngưỡng đạt, bằng chứng và owner rõ ràng, **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** có thể triển khai nhất quán qua local, staging, production và CI/CD, đồng thời truy vết được quyết định nghiệm thu khi cần audit hoặc xử lý sự cố.
