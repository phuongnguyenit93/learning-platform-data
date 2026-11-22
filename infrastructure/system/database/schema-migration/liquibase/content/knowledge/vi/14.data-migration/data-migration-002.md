
# Thêm, cập nhật và xóa dữ liệu bằng change type trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu thông qua changelog, changeset, precondition, checksum và lịch sử triển khai. Không phải migration nào cũng là CREATE TABLE hoặc ALTER TABLE. Khi bổ sung mã danh mục, chuẩn hóa dữ liệu cũ, chuyển giá trị trạng thái hoặc loại bỏ bản ghi không còn hợp lệ, ta cần **data migration**: thay đổi dữ liệu có kiểm soát, có lịch sử và có thể kiểm chứng.

Bài thuộc chương **Chuyển đổi dữ liệu** tập trung vào ba change type phổ biến: **insert**, **update** và **delete**. Chúng giúp khai báo thao tác thêm, sửa và xóa bản ghi trong YAML, XML hoặc JSON changelog mà không phải viết SQL thủ công cho mọi trường hợp. Tuy nhiên, change type chỉ mô tả thao tác; tính an toàn phụ thuộc nhiều vào điều kiện WHERE, dữ liệu đã tồn tại, ràng buộc, transaction, rollback và cách phối hợp migration qua môi trường.

Mục tiêu sau bài học: viết được changeset insert/update/delete có phạm vi chính xác; phân biệt dữ liệu tham chiếu với dữ liệu nghiệp vụ; kiểm chứng số dòng bị ảnh hưởng và tính nhất quán sau migration; thiết kế rollback có ý thức về nguy cơ mất dữ liệu; và triển khai an toàn bằng Liquibase trong dự án Java, Spring Boot hoặc CI/CD.

## 1. Phân biệt schema migration và data migration

**Schema migration** thay đổi cấu trúc: bảng, cột, index, constraint, view và các đối tượng database. **Data migration** thay đổi nội dung bản ghi trong các bảng đó.

Ví dụ hệ thống quản lý khách hàng đang có bảng customer với các trường id, email và status. Nhóm phát triển muốn chuyển giá trị status cũ từ NULL sang ACTIVE trước khi bổ sung ràng buộc NOT NULL. Đây là hai bước khác nhau:

1. **Data migration:** UPDATE customer SET status = 'ACTIVE' WHERE status IS NULL.
2. **Schema migration:** thêm NOT NULL constraint sau khi dữ liệu được kiểm chứng.

Nếu thêm constraint trước khi xử lý dữ liệu cũ, migration có thể thất bại. Nếu cập nhật toàn bộ status mà không có điều kiện, nó có thể ghi đè cả những khách hàng đã có trạng thái SUSPENDED hoặc INACTIVE.

Một hệ thống có lịch sử dài cần kết hợp cả hai kiểu migration theo thứ tự rõ ràng. Liquibase cho phép đặt mỗi bước trong changeset riêng, gắn id/author, kiểm tra precondition, theo dõi checksum và ghi lịch sử trong **DATABASECHANGELOG**.

## 2. Ba change type cơ bản

| Change type | Mục đích | Phạm vi tác động | Nguy cơ chính |
|---|---|---|---|
| **insert** | Thêm một bản ghi có các cột/giá trị được khai báo | Thông thường một hàng cho mỗi change insert | Trùng khóa, trùng dữ liệu tham chiếu, sai giá trị mặc định |
| **update** | Sửa giá trị một hoặc nhiều cột của các hàng thỏa điều kiện | Một hoặc nhiều hàng; **toàn bảng nếu không giới hạn** | Ghi đè dữ liệu đúng, sửa quá nhiều hàng, lock kéo dài |
| **delete** | Xóa các hàng thỏa điều kiện | Một hoặc nhiều hàng; **có thể toàn bảng nếu thiếu WHERE** | Mất dữ liệu, cascade delete, mất khả năng rollback |

Trong Liquibase, một changeset có thể chứa nhiều change. Nhưng nên chia theo mục tiêu nghiệp vụ và mức độ rủi ro, nhất là khi có dữ liệu production. Để phục vụ truy vết và khôi phục, thường không nên nhồi một thao tác UPDATE hàng triệu dòng và một thao tác DELETE phá hủy vào cùng changeset.

Các change type có cấu hình chung như **tableName**, có thể có **schemaName** tùy dự án, và danh sách **columns** đối với insert/update. Nội dung được Liquibase chuyển thành SQL phù hợp trong giới hạn hỗ trợ của DBMS.

## 3. Chuẩn bị dữ liệu mẫu và các giả định

Các ví dụ dùng hai bảng:

**customer_type** — danh mục loại khách hàng:

| code | display_name | active |
|---|---|---|
| INDIVIDUAL | Khách hàng cá nhân | true |
| BUSINESS | Khách hàng tổ chức | true |

**customer** — dữ liệu nghiệp vụ:

| id | email | status |
|---|---|---|
| 101 | a@example.invalid | NULL |
| 102 | b@example.invalid | SUSPENDED |
| 103 | c@example.invalid | NULL |

Giả định:

- Bảng customer_type có cột code (khóa duy nhất), display_name (chuỗi) và active (boolean hoặc kiểu tương đương).
- Bảng customer có id (khóa chính), email, status và đã tồn tại trước data migration.
- Khả năng lưu boolean, ký tự Unicode và tên schema phụ thuộc DBMS.
- Dữ liệu trên chỉ là dữ liệu thử nghiệm; không suy luận tất cả database thật có cùng số hàng hoặc cùng trạng thái.

Nếu bảng chưa tồn tại, hãy tạo nó trong **schema changeset trước** rồi mới chạy các changeset dữ liệu. Trong bài thực hành cuối, ta sẽ xem cách tổ chức thứ tự và kiểm tra cả database trống lẫn database đã có dữ liệu.

## 4. insert: thêm một bản ghi tham chiếu

Một changeset YAML thêm loại khách hàng mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-01-insert-vip-customer-type
      author: customer-team
      comment: Thêm loại VIP phục vụ chính sách chăm sóc khách hàng.
      changes:
        - insert:
            tableName: customer_type
            columns:
              - column:
                  name: code
                  value: VIP
              - column:
                  name: display_name
                  value: Khách hàng ưu tiên
              - column:
                  name: active
                  valueBoolean: true
      rollback:
        - delete:
            tableName: customer_type
            where: "code = 'VIP'"
~~~

Ý nghĩa các phần:

- **id + author + đường dẫn changelog** là định danh changeset. Chỉ chạy khi được Liquibase xác định đang pending theo lịch sử và điều kiện thực thi.
- **insert** chỉ định bảng và giá trị từng cột. Những cột không khai báo dùng default của database hoặc NULL nếu schema cho phép; không tự sinh giá trị ngoài khả năng DBMS/driver.
- **value** biểu diễn giá trị chuỗi; **valueBoolean** giúp thể hiện ý định dùng giá trị boolean.
- **rollback** được khai báo riêng để xóa hàng tham chiếu nếu cần quay lui. Đây không phải bảo đảm rollback an toàn.

**Rủi ro quan trọng:** nếu ứng dụng đã tạo dữ liệu tham chiếu khóa ngoại tới code VIP, việc xóa VIP khi rollback có thể bị constraint chặn hoặc làm mất dữ liệu liên quan nếu bật cascade. Không dùng rollback delete một cách tự động mà không phân tích dependency.

Với mã danh mục, nên có unique constraint ở cột code. Unique constraint ngăn tạo hai bản ghi có cùng mã, nhưng nó không tự làm insert trở thành idempotent: lần insert trùng có thể bị lỗi, đúng với cơ chế bảo vệ dữ liệu.

## 5. Cách khai báo kiểu giá trị trong column

Một column của Liquibase có nhiều thuộc tính để chỉ rõ dữ liệu. Không phải lúc nào cũng nên đặt mọi giá trị vào value dưới dạng text.

| Thuộc tính thường gặp | Ví dụ | Mục đích |
|---|---|---|
| **value** | ACTIVE | Chuỗi ký tự |
| **valueNumeric** | 42 | Giá trị số |
| **valueBoolean** | true | Giá trị boolean theo cách DBMS hỗ trợ |
| **valueDate** | "2026-11-19 09:30:00" | Giá trị ngày/giờ cần được Liquibase chuyển đổi |
| **valueComputed** | CURRENT_TIMESTAMP | Biểu thức SQL được tính ở database, không phải chuỗi hằng |
| Bỏ qua column | Không khai báo created_at | Để database áp dụng default, nếu có |

Ví dụ minh họa nhiều kiểu giá trị:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-02-insert-event-code
      author: platform-team
      changes:
        - insert:
            tableName: event_catalog
            columns:
              - column:
                  name: code
                  value: CUSTOMER_REGISTERED
              - column:
                  name: priority
                  valueNumeric: 10
              - column:
                  name: enabled
                  valueBoolean: true
              - column:
                  name: created_at
                  valueComputed: CURRENT_TIMESTAMP
~~~

Đây là ví dụ chỉ chạy khi bảng event_catalog cùng các cột đã tồn tại, và SQL sinh ra tương thích DBMS. **valueComputed** có nghĩa Liquibase đưa biểu thức cho database tính, khác với **value: CURRENT_TIMESTAMP** (giá trị chuỗi literal theo ngữ cảnh). Không đưa nội dung không đáng tin cậy từ người dùng vào valueComputed.

Giá trị ngày/giờ có thể bị ảnh hưởng bởi timezone, kiểu DATE/TIMESTAMP và driver. Với dữ liệu nghiệp vụ cần mốc thời gian tuyệt đối, xác định rõ quy tắc UTC, timezone và cách biểu diễn. Không dùng một timestamp mặc định tự phát nếu mục tiêu là tái tạo cùng dữ liệu qua nhiều môi trường.

## 6. Thêm nhiều hàng: nhiều insert hay loadData?

Một insert change thường thêm một hàng, do đó với vài giá trị tham chiếu ổn định có thể viết nhiều insert trong một changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-03-insert-customer-categories
      author: customer-team
      comment: Khởi tạo các nhóm khách hàng chuẩn.
      changes:
        - insert:
            tableName: customer_type
            columns:
              - column:
                  name: code
                  value: INDIVIDUAL
              - column:
                  name: display_name
                  value: Khách hàng cá nhân
              - column:
                  name: active
                  valueBoolean: true
        - insert:
            tableName: customer_type
            columns:
              - column:
                  name: code
                  value: BUSINESS
              - column:
                  name: display_name
                  value: Khách hàng tổ chức
              - column:
                  name: active
                  valueBoolean: true
~~~

Để rollback đoạn này cần **xây dựng rollback có chủ đích**, không chỉ dựa vào việc thấy hai change insert. Những code tham chiếu có thể đã được sử dụng sau khi triển khai; rollback xóa danh mục không phải lúc nào cũng phù hợp.

Khi có vài chục hoặc hàng nghìn hàng từ CSV, viết thủ công hàng loạt insert khiến changelog dài, khó review và dễ sai. Liquibase có **loadData** và **loadUpdateData** phục vụ dữ liệu từ file, với semantics và yêu cầu khác. Đó là lựa chọn nên cân nhắc cho dữ liệu tham chiếu lớn hoặc có chiến lược đồng bộ rõ ràng, nhưng cũng phải kiểm tra khóa duy nhất, encoding, quoting, kiểu dữ liệu, tính tái tạo và rollback.

**Không dùng một changeset insert hàng triệu bản ghi nghiệp vụ theo cách máy móc.** Với dữ liệu lớn, cần chiến lược ETL/batch/migration job chuyên dụng, có checkpoint, quan sát và kiểm soát lock.

## 7. update: thay đổi có điều kiện

Ví dụ cập nhật tên hiển thị của một mã danh mục:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-04-rename-vip-label
      author: customer-team
      comment: Thống nhất tên hiển thị VIP theo bộ nhận diện mới.
      changes:
        - update:
            tableName: customer_type
            columns:
              - column:
                  name: display_name
                  value: Khách hàng đặc biệt
            where: "code = 'VIP'"
~~~

Liquibase tạo thao tác UPDATE phù hợp với database. Điều kiện **where** quyết định những hàng nào bị sửa.

Có thể cập nhật nhiều cột trong cùng change:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-05-change-vip-status
      author: customer-team
      changes:
        - update:
            tableName: customer_type
            columns:
              - column:
                  name: display_name
                  value: Khách hàng ưu tiên
              - column:
                  name: active
                  valueBoolean: true
            where: "code = 'VIP'"
~~~

Nếu code là unique key, phạm vi tối đa là một hàng khi dữ liệu và constraint hợp lệ. Nếu không có unique constraint hoặc where sử dụng một cột không duy nhất, số hàng thực tế bị ảnh hưởng có thể lớn hơn dự tính.

**Không có where** đồng nghĩa lệnh UPDATE có thể tác động đến toàn bộ hàng trong bảng. Trước khi review migration, người phát triển phải trả lời: “Những hàng nào được phép bị sửa, và vì sao điều kiện này chọn đúng tập đó?”

## 8. Backfill: cập nhật dữ liệu cũ trước khi siết constraint

Một kịch bản data migration phổ biến là backfill giá trị còn thiếu. Giả sử cột customer.status mới được bổ sung nhưng chưa NOT NULL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-06-backfill-customer-status
      author: customer-team
      comment: Bổ sung ACTIVE cho khách hàng chưa có trạng thái.
      changes:
        - update:
            tableName: customer
            columns:
              - column:
                  name: status
                  value: ACTIVE
            where: "status IS NULL"
~~~

Với dữ liệu ví dụ ở phần 3:

| id | status trước | status sau |
|---|---|---|
| 101 | NULL | ACTIVE |
| 102 | SUSPENDED | SUSPENDED |
| 103 | NULL | ACTIVE |

Tính quan trọng nằm ở **where: "status IS NULL"**. Nếu bỏ where, giá trị SUSPENDED của khách hàng 102 sẽ bị ghi đè thành ACTIVE, có thể thay đổi quyền hoặc trạng thái nghiệp vụ.

Một trình tự phát hành thường an toàn hơn:

1. Thêm cột status ở trạng thái tương thích với ứng dụng cũ.
2. Triển khai code mới biết đọc/ghi status, nếu cần hỗ trợ chạy song song.
3. Backfill có điều kiện cho các bản ghi cũ.
4. Kiểm tra không còn bản ghi vi phạm.
5. Chỉ sau đó thêm NOT NULL hoặc constraint khác ở changeset mới.
6. Kiểm tra ứng dụng và rollback/forward fix trước khi đóng giai đoạn chuyển đổi.

Nếu tập dữ liệu rất lớn, backfill bằng một UPDATE duy nhất có thể giữ lock lâu, sinh WAL/binlog/redo lớn, vượt timeout hoặc làm replication lag. Khi đó cần thiết kế batch có checkpoint, theo dõi và giới hạn tốc độ thay vì mặc nhiên dùng một update change.

## 9. WHERE cần chính xác đến mức nào?

**where** là một chuỗi điều kiện SQL được đưa vào lệnh UPDATE/DELETE. Nó không phải biểu thức lọc dựa trên Java Stream. Cú pháp phải được DBMS đích hiểu và đúng với schema thật.

Một số mẫu điều kiện có thể xem xét:

| Mục tiêu | Ví dụ where | Điều cần kiểm tra |
|---|---|---|
| Sửa một mã danh mục | "code = 'VIP'" | code có unique constraint không? |
| Backfill giá trị thiếu | "status IS NULL" | Có giá trị rỗng '' hoặc sentinel khác NULL không? |
| Sửa theo mốc cố định | "id BETWEEN 1000 AND 1999" | Đây có phải tập bản ghi đúng cho mọi môi trường? |
| Xử lý trạng thái cũ | "status = 'PENDING_OLD'" | Có ngoại lệ nghiệp vụ hay dữ liệu khác spelling không? |
| Xóa dữ liệu test | "source = 'TEST_FIXTURE' AND is_test = 1" | Điều kiện có chắc phân biệt được dữ liệu test với dữ liệu thật? |

Các điều kiện này chỉ là ví dụ; tên cột và giá trị boolean sẽ khác nhau theo DBMS. **Không tạo where bằng cách ghép trực tiếp dữ liệu người dùng vào changelog**. Changelog được review là cấu hình triển khai; nếu phải tham số hóa thì kiểm soát chặt nguồn giá trị và khả năng SQL injection, vì text substitution không tự động tương đương prepared statement.

Trước mỗi UPDATE/DELETE có nguy cơ ảnh hưởng rộng, hãy chạy một truy vấn SELECT tương ứng trên bản sao dữ liệu:

~~~sql
SELECT COUNT(*)
FROM customer
WHERE status IS NULL;
~~~

Sau khi xác định số lượng, kiểm tra mẫu dữ liệu và ràng buộc nghiệp vụ, mới quyết định liệu thao tác có phù hợp. Truy vấn COUNT(*) có thể tốn tài nguyên trên bảng lớn; với production phải cân nhắc kế hoạch query và công cụ thống kê thích hợp.

## 10. delete: xóa bản ghi theo điều kiện

Một changeset xóa bản ghi danh mục thử nghiệm đã được xác nhận không còn sử dụng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-07-delete-obsolete-code
      author: customer-team
      comment: Loại bỏ mã danh mục không còn sử dụng sau khi đã xác minh phụ thuộc.
      changes:
        - delete:
            tableName: customer_type
            where: "code = 'LEGACY_UNUSED'"
~~~

**delete** loại bỏ các hàng khớp điều kiện. Nó không xóa bảng hoặc cột; đây là thao tác DML. Tuy nhiên, phạm vi xóa có thể lan tới bảng khác nếu database có cấu hình foreign key **ON DELETE CASCADE**, hoặc bị chặn nếu có khóa ngoại RESTRICT/NO ACTION.

**Nếu bỏ where, lệnh DELETE có thể xóa toàn bộ dữ liệu bảng.** Một changeset như vậy chỉ phù hợp trong trường hợp chủ đích rõ ràng, ví dụ dọn một bảng staging disposable có xác nhận môi trường và không chứa dữ liệu cần giữ. Trong migration production thông thường, đây là tín hiệu cần chặn review.

Trước khi xóa:

1. Xác định tập bản ghi bằng SELECT và kiểm tra số lượng.
2. Kiểm tra foreign key và các bảng phụ thuộc.
3. Kiểm tra trigger DELETE, audit trail, soft-delete policy và retention.
4. Xác định ảnh hưởng tới phiên bản ứng dụng đang chạy.
5. Có backup hoặc snapshot khi dữ liệu cần khôi phục.
6. Thử migration trên dữ liệu đại diện và xác nhận số hàng thực sự thay đổi.
7. Chọn thời điểm phát hành nếu việc xóa tạo lock hoặc ảnh hưởng truy vấn.

## 11. Xóa cứng, xóa mềm và lưu trữ trước khi xóa

Không phải mọi yêu cầu “xóa dữ liệu” đều nên dùng delete change.

**Hard delete:** xóa hàng khỏi bảng. Phù hợp cho dữ liệu tham chiếu không còn được dùng hoặc dữ liệu thật sự được phép loại bỏ. Khôi phục cần bản sao dữ liệu hoặc câu lệnh insert đủ thông tin.

**Soft delete:** UPDATE một cột như archived_at hoặc active=false. Dữ liệu vẫn tồn tại, ứng dụng chủ động lọc khỏi truy vấn chính. Hữu ích khi cần audit, rollback trạng thái hoặc tuân thủ retention.

**Archive/move:** chuyển bản ghi sang bảng lưu trữ hoặc kho dữ liệu khác sau khi đối chiếu, rồi mới xóa. Cần kiểm tra tính toàn vẹn và khả năng khôi phục; không xem việc INSERT vào bảng archive là đủ nếu thao tác không đảm bảo transactional trên DBMS.

Ví dụ soft delete bằng update:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-08-disable-old-customer-type
      author: customer-team
      comment: Ngừng sử dụng mã LEGACY_UNUSED mà không xóa dữ liệu lịch sử.
      changes:
        - update:
            tableName: customer_type
            columns:
              - column:
                  name: active
                  valueBoolean: false
            where: "code = 'LEGACY_UNUSED'"
~~~

Soft delete cũng có rủi ro: nếu ứng dụng cũ không lọc active=false, dữ liệu vẫn có thể xuất hiện. Phải phối hợp thay đổi code, query, index và logic nghiệp vụ.

## 12. Rollback dữ liệu khó hơn rollback cấu trúc

Một thao tác tạo bảng có thể được rollback bằng dropTable, nhưng rollback dữ liệu không đơn giản là đảo ngược tên change type. Muốn khôi phục UPDATE hoặc DELETE cần biết **giá trị trước khi thay đổi**.

| Thao tác tiến | Rollback có thể cân nhắc | Vì sao không thể làm máy móc? |
|---|---|---|
| insert một mã tham chiếu mới | delete theo khóa duy nhất | Bản ghi có thể đã được sử dụng hoặc bị chỉnh sửa sau đó |
| update tên hiển thị cố định | update trở về giá trị cũ đã biết | Giá trị cũ có thể khác nhau giữa môi trường |
| backfill status cho hàng NULL | Phục hồi snapshot các hàng bị sửa | Không thể biết từ dữ liệu hiện tại hàng nào vốn NULL nếu không lưu trạng thái trước |
| delete hàng tham chiếu | insert lại bản ghi đã lưu | Cần đủ cột, khóa, quan hệ và dữ liệu gốc |
| delete nhiều bản ghi nghiệp vụ | Khôi phục backup/snapshot | Không thể tái tạo chính xác toàn bộ bản ghi chỉ từ điều kiện where |

Ví dụ rollback tương đối kiểm soát được khi nhóm **biết chắc** một mã được tạo mới bởi chính changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-09-insert-new-channel
      author: platform-team
      changes:
        - insert:
            tableName: sales_channel
            columns:
              - column:
                  name: code
                  value: PARTNER
              - column:
                  name: description
                  value: Kênh đối tác
      rollback:
        - delete:
            tableName: sales_channel
            where: "code = 'PARTNER'"
~~~

Điều kiện tiên quyết để rollback an toàn là bản ghi PARTNER chưa có trước migration và không có dữ liệu phát sinh phụ thuộc vào nó sau đó. Nếu channel đã được đặt hàng sử dụng, xóa có thể gây lỗi hoặc mất dữ liệu.

Với UPDATE có điều kiện, **rollback không nên đơn giản gán tất cả hàng về NULL** trừ khi có bằng chứng chính xác rằng mọi hàng bị sửa ban đầu đều NULL và không có ghi mới hợp lệ vào nhóm hàng ấy. Nếu không, cách làm đó có thể xóa dữ liệu được ứng dụng tạo sau migration.

## 13. Precondition giúp kiểm tra trạng thái trước insert/update/delete

Precondition dùng để bảo đảm một số tiền đề trước khi Liquibase thực thi changeset. Ví dụ muốn insert mã VIP nhưng từ chối nếu mã đã có:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-10-insert-vip-strict
      author: customer-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer_type
        - sqlCheck:
            expectedResult: "0"
            sql: >-
              SELECT COUNT(*)
              FROM customer_type
              WHERE code = 'VIP'
      changes:
        - insert:
            tableName: customer_type
            columns:
              - column:
                  name: code
                  value: VIP
              - column:
                  name: display_name
                  value: Khách hàng ưu tiên
~~~

Ở đây nhóm chủ động chọn **HALT** thay vì âm thầm bỏ qua. Nếu một bản ghi VIP đã tồn tại nhưng mô tả khác, pipeline phải dừng để điều tra, tránh che drift dữ liệu.

Một số lựa chọn khi precondition thất bại:

- **HALT:** dừng; hợp lý khi việc thay đổi dữ liệu không đủ an toàn.
- **WARN:** cảnh báo nhưng không thay thế kiểm chứng; phải hiểu liệu changeset tiếp tục chạy hay không theo phiên bản.
- **CONTINUE:** bỏ qua changeset ở lần này, có thể xét lại vào lần sau.
- **MARK_RAN:** đánh dấu changeset như đã xử lý dù phần changes không thực thi. Chỉ dùng khi đã xác minh trạng thái mong đợi thực sự tồn tại.

MARK_RAN không phải “INSERT IF NOT EXISTS” một cách an toàn. Nếu row trùng khóa nhưng có nội dung sai, điều kiện chỉ kiểm tra sự tồn tại có thể khiến dữ liệu không bao giờ được sửa và DATABASECHANGELOG lại cho biết changeset không còn pending.

Đối với UPDATE/DELETE phá hủy, precondition nên bảo vệ **phạm vi và tiền đề**. Có thể dùng sqlCheck để chặn nếu số hàng vượt ngưỡng hoặc nếu còn khóa ngoại liên quan. Nhưng việc thêm precondition không thay thế kiểm tra transaction và dữ liệu thật.

## 14. Kiểm tra số hàng dự kiến và số hàng thực tế

Trước một migration dữ liệu, nên định nghĩa **kết quả có thể kiểm chứng**:

- Có đúng một mã VIP mới với display_name mong đợi.
- Không còn hàng customer có status NULL.
- Không còn mã LEGACY_UNUSED, đồng thời không có hàng phụ thuộc bị mất.
- Không có thay đổi ngoài tập bản ghi dự kiến.

Ví dụ kiểm tra sau backfill:

~~~sql
SELECT COUNT(*) AS missing_status
FROM customer
WHERE status IS NULL;

SELECT status, COUNT(*) AS amount
FROM customer
GROUP BY status;
~~~

Ví dụ kiểm tra sau insert danh mục:

~~~sql
SELECT code, display_name, active
FROM customer_type
WHERE code = 'VIP';
~~~

Ví dụ kiểm tra trước delete:

~~~sql
SELECT COUNT(*) AS candidates
FROM customer_type
WHERE code = 'LEGACY_UNUSED';
~~~

Liquibase không tự đảm bảo “đúng N hàng bị tác động” chỉ vì câu lệnh được thực thi thành công. Nhiều UPDATE có thể trả về số hàng bằng 0 và vẫn thành công về mặt SQL; điều đó có thể là mong đợi (dữ liệu đã ở trạng thái đúng) hoặc dấu hiệu where sai.

Trong một hệ thống cần bằng chứng số hàng chính xác, phải thu thập row count hoặc đối chiếu tập khóa trước/sau theo công cụ DBMS, log migration hay test tự động. Tránh ghi dữ liệu nhạy cảm hoặc danh sách identifier cá nhân vào log CI/CD.

## 15. Idempotency và tính tái lập khác nhau thế nào?

**Idempotency** là tính chất thao tác có thể chạy lặp lại mà không tạo thêm hiệu ứng ngoài ý định. **Tính tái lập** là khả năng dựng cùng trạng thái mong đợi khi dùng cùng revision changelog, cấu hình và trạng thái đầu vào đã xác định.

Ví dụ:

- UPDATE customer SET status='ACTIVE' WHERE status IS NULL có tính gần idempotent đối với trạng thái đó: chạy lại thường không sửa các hàng đã được đặt ACTIVE.
- INSERT customer_type (code='VIP') không idempotent nếu chạy lại lần nữa gây lỗi unique key, trừ khi có cơ chế bảo đảm tương ứng.
- DELETE ... WHERE code='LEGACY_UNUSED' có thể không còn hàng để xóa ở lần sau, nhưng việc thiếu dữ liệu ban đầu và ảnh hưởng phụ thuộc vẫn phải được xét.

Liquibase **thông thường không chạy lại changeset đã được ghi nhận** trong DATABASECHANGELOG. Vì vậy, không nên nhầm “chỉ chạy một lần nhờ lịch sử” với “SQL an toàn khi bị gọi nhiều lần”. Một changeset vẫn cần được thiết kế chống sai phạm trong trường hợp chạy lại do thao tác vận hành, các thuộc tính đặc biệt hoặc môi trường bị mất lịch sử.

Một môi trường A có mã VIP trước migration còn B chưa có sẽ hành xử khác nếu cả hai chạy cùng insert. Muốn tái lập, cần quy định rõ trạng thái đầu vào, lựa chọn HALT/tiếp tục và chính sách reconcile dữ liệu. Không sửa changeset sau khi đã triển khai chỉ để thích nghi từng môi trường.

## 16. Thứ tự changeset trong data migration

Dữ liệu cần cấu trúc để lưu trữ; schema cần dữ liệu phù hợp trước khi đặt constraint. Một pipeline Liquibase thường có thứ tự:

~~~text
001 — Tạo bảng/cột (schema)
      |
      v
002 — Thêm mã danh mục chuẩn (insert)
      |
      v
003 — Backfill dữ liệu cũ (update)
      |
      v
004 — Kiểm tra dữ liệu đầy đủ, không còn giá trị vi phạm
      |
      v
005 — Thêm NOT NULL, CHECK, FOREIGN KEY (schema)
      |
      v
006 — Dọn dữ liệu cũ sau giai đoạn chuyển tiếp (update/delete)
~~~

Những con số trong tên file hay id **không tự khiến Liquibase sắp xếp lại changeset**: thứ tự do master changelog, include/includeAll và cấu trúc changeset quyết định.

Đối với triển khai rolling hoặc blue-green, phải tính đến ứng dụng cũ và mới chạy đồng thời. Ví dụ nếu phiên bản cũ còn ghi status=NULL sau khi đã backfill, một lần UPDATE duy nhất trước deploy có thể không đủ. Có thể cần thêm default tạm, logic ứng dụng tương thích, batch bổ sung và chỉ siết constraint khi luồng ghi cũ không còn tồn tại.

**Expand–migrate–contract** là chiến lược hữu ích: mở rộng schema không phá tương thích, chuyển dữ liệu và code, sau đó mới thu hẹp ràng buộc/loại bỏ trường cũ.

## 17. Data migration và đặc tính transaction của DBMS

Change type insert/update/delete thường được thực thi bằng các câu DML do Liquibase sinh ra. Với DBMS hỗ trợ transaction cho các thao tác đó và changeset cho phép transaction, Liquibase thường cố gắng áp dụng chúng trong transaction.

Tuy nhiên:

- DDL và DML trong cùng changeset có thể có hành vi commit khác nhau giữa DBMS.
- Trigger, stored procedure, foreign key cascade và side effect có thể làm số bản ghi thực sự bị ảnh hưởng lớn hơn tập SQL trực tiếp.
- Một UPDATE trên bảng lớn có thể giữ lock kéo dài, gây deadlock hoặc làm ứng dụng chậm.
- Transaction dài có thể tạo nhiều WAL/redo/undo, ảnh hưởng log storage, replication và backup.
- runInTransaction: false có thể khiến changeset dở dang nếu một câu thành công nhưng câu sau thất bại.

Không tự động đặt runInTransaction: false chỉ để né timeout. Phải hiểu nguồn gốc vấn đề và xây dựng batch migration chuyên dụng nếu dữ liệu lớn. Với dữ liệu quan trọng, hãy kiểm chứng tính nguyên tử và khả năng rollback trên **cùng DBMS/phiên bản** với production.

## 18. Dữ liệu lớn: không nên dùng UPDATE/DELETE toàn bảng thiếu kế hoạch

Ví dụ có hàng chục triệu khách hàng cần chuẩn hóa trạng thái. Một changeset update toàn bảng có thể làm tăng thời gian triển khai và tác động ứng dụng. Những câu hỏi cần trả lời:

1. Có index phù hợp với điều kiện where không?
2. Số hàng ước tính cần sửa là bao nhiêu?
3. Thao tác có vượt ngưỡng thời gian triển khai không?
4. Có kích hoạt trigger, audit hay replication bổ sung không?
5. Có thể chia thành các lô dựa trên khóa ổn định không?
6. Làm sao biết lô nào đã hoàn thành nếu job bị gián đoạn?
7. Làm sao bảo đảm code đang chạy không viết lại dữ liệu cũ?
8. Có yêu cầu nghiệp vụ về thứ tự cập nhật hoặc dữ liệu được phép thay đổi không?

Với bài toán lớn, lựa chọn có thể là tách nhiều changeset theo phạm vi đã được kiểm chứng hoặc sử dụng job batch/ETL có checkpoint và giám sát. Liquibase vẫn có thể quản lý thay đổi schema và mốc chuyển đổi, nhưng không phải mọi data migration đều nên được đóng gói thành một UPDATE khổng lồ.

Tránh chia lô bằng các khoảng id giả định nếu những khoảng đó không ổn định hoặc dễ bỏ sót. Nếu cần dùng watermark/checkpoint, phải định nghĩa rõ idempotency, snapshot tập cần xử lý và cách phát hiện thay đổi đồng thời.

## 19. Khác biệt giữa các môi trường và dữ liệu tham chiếu

Dữ liệu danh mục như customer_type thường nên nhất quán giữa development, test, staging và production. Dữ liệu nghiệp vụ trong bảng customer thì **không nhất thiết** phải giống nhau.

| Loại dữ liệu | Ví dụ | Cách quản lý thường phù hợp |
|---|---|---|
| Reference/master data | Mã loại khách hàng, trạng thái chuẩn | Changeset được review, khóa ổn định, kiểm tra sự hiện diện |
| Configuration data | Feature flag hoặc ngưỡng nghiệp vụ | Tách giá trị đặc thù môi trường, có chủ sở hữu rõ ràng |
| Test fixture | Người dùng giả, đơn hàng giả | Chỉ chạy trên môi trường kiểm thử có bộ lọc và guard phù hợp |
| Transactional data | Giao dịch, khách hàng thật, thanh toán | Migration có kiểm soát riêng, bảo mật, giới hạn phạm vi |
| Derived data | Bảng tổng hợp, cache | Đánh giá khả năng rebuild thay vì luôn cập nhật từng hàng |

Không đưa dữ liệu cá nhân production vào changelog hoặc fixture. Không dựa vào việc ghi context: test đơn thuần để đảm bảo dữ liệu test không chạy ở production: tùy semantics Liquibase, **changeset có context có thể vẫn được xét nếu không truyền filter**. Nếu sử dụng context bắt buộc, label hay dbms, phải kiểm chứng đúng cấu hình triển khai.

Một mã danh mục chung cần được giữ ổn định qua các môi trường. Tránh dùng sequence hoặc id auto-generated làm khóa tham chiếu giữa hệ thống khi các môi trường có thể cấp số khác nhau; mã business key duy nhất và bất biến thường giúp migration tái lập tốt hơn.

## 20. Những thay đổi nhạy cảm: dữ liệu, audit và bảo mật

Data migration có thể đọc hoặc ghi dữ liệu nhạy cảm, kể cả khi changelog chỉ chứa câu lệnh trừu tượng.

Các nguyên tắc:

- Dùng tài khoản migration có quyền vừa đủ; không cần cấp quyền quản trị database cho mọi lần update.
- Không hardcode credential, token, số định danh cá nhân hoặc bản dump dữ liệu thật vào YAML/SQL.
- Không ghi đầy đủ các hàng chứa PII vào CI logs để chứng minh migration thành công.
- Kiểm tra retention và quy định xóa/lưu trữ trước khi thực thi delete.
- Xác định thao tác có ảnh hưởng audit log, CDC, trigger, báo cáo hay hệ thống downstream không.
- Đảm bảo những bản ghi xóa được phép khôi phục hoặc có căn cứ pháp lý để xóa vĩnh viễn.
- Giữ dấu vết approval, commit, artifact, execution log và kết quả kiểm chứng.

Nếu dữ liệu cần ẩn danh hoặc băm lại, cần phân biệt migration bảo mật với thao tác thay chuỗi thông thường. Kỹ thuật mã hóa/hash có ràng buộc về thuật toán, salt, rotation và khả năng xác minh; không nên tự viết một update change đơn giản mà chưa có thiết kế riêng.

## 21. Các lỗi thường gặp với insert/update/delete

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| insert lỗi duplicate key | Mã đã tồn tại hoặc unique constraint vi phạm | Đối chiếu khóa, nội dung hiện tại và chính sách reconcile; không xóa dữ liệu cũ tùy tiện |
| insert lỗi NOT NULL | Thiếu cột bắt buộc hoặc không có default | Kiểm tra schema thật và danh sách columns |
| Giá trị boolean/date bị sai | Dùng value thay vì valueBoolean/valueDate, hoặc khác biệt DBMS | Khai báo kiểu rõ ràng, thử trên DBMS đích |
| update ảnh hưởng quá nhiều hàng | Thiếu where hoặc điều kiện rộng | Dừng và xác minh phạm vi, số lượng, dữ liệu |
| update không ảnh hưởng hàng nào | Không có hàng phù hợp, where sai hoặc dữ liệu đã ở trạng thái mới | Kiểm tra bằng SELECT và kỳ vọng nghiệp vụ |
| delete xóa cả bảng | Thiếu where | Kiểm soát review, điều kiện bắt buộc và bản backup |
| delete lỗi foreign key | Hàng vẫn được bảng khác tham chiếu | Điều tra phụ thuộc, chọn soft delete hoặc chiến lược chuyển tiếp |
| delete làm mất thêm dữ liệu | Cascade hoặc trigger | Kiểm tra DDL và thử trên bản sao có dữ liệu |
| rollback update không khôi phục đúng | Không lưu giá trị cũ | Thiết kế snapshot hoặc forward fix; không gán ngược hàng loạt |
| Staging thành công nhưng production thất bại | Dữ liệu đầu vào khác, quy mô khác, quyền hoặc constraint khác | Test trên bản dữ liệu đại diện và kiểm chứng tiền đề |
| Migration chạy xong nhưng schema vẫn lệch | DDL thiếu, thứ tự changeset sai, dữ liệu vi phạm constraint | Kiểm tra master, DATABASECHANGELOG và schema thực tế |
| Changeset cũ báo checksum mismatch | Nội dung migration đã được sửa sau triển khai | So sánh revision cũ và tạo changeset mới cho thay đổi tiếp theo |
| Chạy từ Spring Boot khởi động lâu | Lock/transaction của data migration lớn | Tách migration job và batch có giám sát, đánh giá cách deploy |
| Không tìm thấy bảng | Sai schemaName/defaultSchema hoặc migration chưa tạo bảng | Kiểm tra database, schema và thứ tự include |

Không giải quyết lỗi bằng cách sửa trực tiếp DATABASECHANGELOG, xóa row lịch sử hoặc đổi EXECTYPE để ép migration chạy lại. Trước tiên phải xác định id/author/FILENAME, schema thực, transaction và dữ liệu đã bị tác động.

## 22. Tích hợp Spring Boot và CI/CD

Với Spring Boot, Liquibase có thể đọc changelog từ classpath khi ứng dụng khởi động:

~~~yaml
spring:
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Cấu hình datasource phải được cấp riêng và an toàn. Các change type insert/update/delete được xử lý cùng changelog với schema changeset.

Có hai mô hình:

**Ứng dụng tự chạy migration:** phù hợp với một số ứng dụng nhỏ hoặc môi trường có điều phối chặt. Rủi ro là một update dữ liệu lớn có thể kéo dài thời gian startup và làm rollout nhiều replica phức tạp.

**Pipeline chạy migration riêng:** job Liquibase CLI/Maven/Gradle chạy validate, status, updateSQL và update trước hoặc trong một giai đoạn phát hành có kiểm soát. Sau khi hoàn tất và xác nhận schema/data, mới triển khai ứng dụng tương thích. Cần tắt tự chạy trong Spring Boot nếu pipeline được chọn là chủ thể migration chính cho môi trường đó.

Một quy trình CI/CD tốt:

1. Ghim phiên bản Liquibase, JDBC driver và revision changelog.
2. Kiểm tra database đích, schema, quyền, loại DBMS và cấu hình secret.
3. Review từng insert/update/delete, nhất là WHERE và rollback.
4. Chạy validate; xem status trên đúng database.
5. Sinh SQL dự kiến bằng updateSQL hoặc lệnh tương ứng với công cụ.
6. Thử trên database mới và bản sao có dữ liệu của release trước.
7. Kiểm chứng tập bản ghi, constraint và tác động ứng dụng.
8. Chạy update khi được phê duyệt.
9. Đối chiếu DATABASECHANGELOG, dữ liệu thật và log.
10. Lưu release record, thông tin rollback/forward fix và kết quả hậu kiểm.

Validate thành công không đảm bảo WHERE chọn đúng hàng trên production. UpdateSQL giúp review SQL được sinh nhưng không thực thi, nên không thay thế kiểm chứng dữ liệu thực tế.

## 23. Bài thực hành: insert, update và delete có kiểm chứng

Mục tiêu: thao tác trên ba thay đổi dữ liệu độc lập với database thử nghiệm. **Không dùng database production.**

### Bước 1 — Chuẩn bị schema và dữ liệu

Tạo hai bảng customer_type và customer với các cột đã mô tả ở phần 3. Thêm ít nhất ba khách hàng: hai hàng status NULL, một hàng SUSPENDED. Nếu triển khai bằng Liquibase, tạo bảng trong schema changeset trước rồi mới thêm dữ liệu.

### Bước 2 — insert mã tham chiếu

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-insert-vip
      author: lab-team
      comment: Thêm mã VIP dùng trong kịch bản kiểm thử.
      changes:
        - insert:
            tableName: customer_type
            columns:
              - column:
                  name: code
                  value: VIP
              - column:
                  name: display_name
                  value: Khách hàng ưu tiên
              - column:
                  name: active
                  valueBoolean: true
      rollback:
        - delete:
            tableName: customer_type
            where: "code = 'VIP'"
~~~

Kiểm tra có đúng một row VIP, giá trị hiển thị chính xác, không có mã trùng. Trên database thử nghiệm chưa có row VIP thì lần thực thi đầu phải thêm được bản ghi.

### Bước 3 — update khách hàng chưa có status

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-002-backfill-status
      author: lab-team
      comment: Chỉ backfill status của các hàng còn NULL.
      changes:
        - update:
            tableName: customer
            columns:
              - column:
                  name: status
                  value: ACTIVE
            where: "status IS NULL"
~~~

Kiểm tra id 101 và 103 trở thành ACTIVE, còn id 102 vẫn SUSPENDED. Ghi lại rằng rollback chính xác của bước này đòi hỏi snapshot/tập khóa bị tác động, không thể tự động đặt mọi status ACTIVE về NULL vì có thể làm hỏng dữ liệu hợp lệ.

### Bước 4 — soft delete trước khi hard delete

Giả sử còn một mã test LEGACY_UNUSED không có bản ghi phụ thuộc. Trước hết cập nhật active=false bằng update và kiểm tra ứng dụng/quan hệ. Chỉ khi có xác nhận mã không còn được dùng, áp dụng changeset delete:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-003-remove-obsolete-code
      author: lab-team
      comment: Xóa dữ liệu thử nghiệm đã được xác nhận không còn phụ thuộc.
      changes:
        - delete:
            tableName: customer_type
            where: "code = 'LEGACY_UNUSED'"
~~~

Nếu bản ghi đó không tồn tại, DELETE có thể không xóa hàng nào và câu lệnh vẫn thành công. Đánh giá đó có phải kết quả được chấp nhận hay không bằng tiêu chí kiểm chứng đã định nghĩa trước.

### Bước 5 — Thử chạy và đối chiếu lịch sử

Dùng Liquibase trên một database thử nghiệm với changelog chứa ba changeset theo đúng thứ tự:

~~~text
validate
status
updateSQL / update-sql
update
status
~~~

Tên lệnh có thể khác theo CLI hoặc Maven/Gradle plugin và phiên bản Liquibase. Sau update, truy vấn DATABASECHANGELOG để xem id, author, filename, checksum, thời gian và EXECTYPE. Đối chiếu bằng SELECT các dữ liệu VIP, status của customer và mã LEGACY_UNUSED.

### Bước 6 — Kiểm thử trạng thái đầu vào khác nhau

Thử trên một database thứ hai đã có mã VIP với mô tả khác. Quan sát insert có thể bị unique constraint chặn. Đây là **bài học về tiền đề**, không phải lỗi cần giấu bằng MARK_RAN hoặc xóa dữ liệu cũ. So sánh với một changeset dùng precondition HALT rõ ràng và quyết định cách xử lý drift.

Thử một bản database có ít dữ liệu hơn và một bản có nhiều hàng NULL hơn để đánh giá tác động UPDATE. Sau đó đưa vào kế hoạch kiểm thử nâng cấp trước khi phát hành trên hệ thống thật.

## 24. Checklist khi phát hành data migration

- [ ] Thao tác là insert, update hay delete; mục đích nghiệp vụ đã rõ.
- [ ] Đối tượng bảng/cột tồn tại và đúng schema đích.
- [ ] Các giá trị dùng kiểu thích hợp (value, valueNumeric, valueBoolean, valueDate, valueComputed).
- [ ] insert có business key hoặc constraint chống trùng phù hợp.
- [ ] update/delete có điều kiện where được review; không tác động toàn bảng ngoài chủ đích.
- [ ] Đã kiểm tra số hàng dự kiến và mẫu dữ liệu bằng truy vấn chỉ đọc.
- [ ] Đã đánh giá foreign key, trigger, cascade, audit và downstream.
- [ ] Đã cân nhắc soft delete/archive trước hard delete.
- [ ] Rollback có đủ thông tin dữ liệu gốc và không gây mất dữ liệu mới.
- [ ] Nếu rollback không an toàn, có backup và forward-fix/runbook rõ ràng.
- [ ] Precondition không che giấu drift bằng MARK_RAN thiếu chứng cứ.
- [ ] Backfill có thứ tự đúng trước khi siết NOT NULL hoặc constraint.
- [ ] Đã tính tới ứng dụng cũ và mới chạy đồng thời khi rolling deployment.
- [ ] Migration lớn có kế hoạch batch/lock/timeout/replication.
- [ ] Changelog giữ cùng revision qua các môi trường, còn config/secrets tách riêng.
- [ ] Không chèn dữ liệu nhạy cảm hoặc fixture production vào changelog.
- [ ] Đã validate, kiểm tra status và review SQL dự kiến.
- [ ] Đã chạy trên DBMS thật ở môi trường thử nghiệm có dữ liệu đại diện.
- [ ] Đã đối chiếu DATABASECHANGELOG và kết quả dữ liệu sau update.
- [ ] Không sửa changeset đã triển khai; thay đổi mới được tạo ở changeset mới.

**Ghi nhớ:** **insert** thêm bản ghi, **update** sửa bản ghi, **delete** xóa bản ghi. Chúng giúp quản lý data migration có lịch sử bằng Liquibase, nhưng không tự bảo đảm điều kiện WHERE đúng, rollback giữ được dữ liệu cũ hoặc mọi môi trường đều có cùng trạng thái đầu vào. Một migration đáng tin cậy phải được thiết kế theo tiền đề rõ ràng, có kiểm chứng số hàng và bất biến nghiệp vụ, gắn với changelog bất biến và được triển khai có kiểm soát cùng Spring Boot hoặc CI/CD.

