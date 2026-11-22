# Rollback thất bại và quy trình chọn phương án phục hồi

Một release gặp lỗi sau khi Liquibase đã cập nhật database. Nhóm vận hành quyết định rollback, nhưng chính rollback cũng thất bại: câu lệnh DROP bị từ chối do thiếu quyền, object đã thay đổi, constraint không thể khôi phục, dữ liệu mới đang tham chiếu tới bảng, hoặc kết nối bị ngắt giữa lúc database thực thi SQL. Khi đó database có thể ở trạng thái chỉ một phần changeset được đảo ngược, trong khi ứng dụng, dữ liệu và lịch sử Liquibase không còn cùng một mốc.

Đây là tình huống cần ra quyết định theo bằng chứng. **Rollback thất bại không đồng nghĩa database tự quay lại trạng thái trước rollback.** Một số statement có thể đã commit; một số changeset trước đó có thể đã rollback thành công; changeset gây lỗi có thể vẫn còn trong history hoặc có side effect chưa được ghi nhận. Chạy lại rollback, sửa tiến bằng changeset mới hay khôi phục từ backup/PITR đều có thể đúng trong một số hoàn cảnh, nhưng phải dựa trên trạng thái thực tế.

Bài học thuộc chương **Xử lý sự cố** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng tới quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào cách điều tra rollback thất bại, xác định phạm vi đã đảo ngược, lựa chọn phương án phục hồi, giữ nhất quán giữa schema và DATABASECHANGELOG, và chuẩn bị runbook để giảm thời gian gián đoạn.

## 1. Rollback thất bại có thể để lại trạng thái nào?

Liquibase thường rollback các changeset theo thứ tự ngược với thứ tự triển khai. Với mỗi changeset, Liquibase thực thi rollback SQL hoặc rollback change được khai báo, sau đó cập nhật lịch sử tương ứng. Nhưng transaction boundary và hành vi DDL phụ thuộc DBMS, loại statement, cấu hình changeset và phiên bản Liquibase.

Vì vậy, sau lỗi có thể gặp nhiều trạng thái:

| Trạng thái | Điều có thể đã xảy ra | Câu hỏi cần trả lời |
|---|---|---|
| Không có thay đổi rollback nào được commit | Lỗi xảy ra trước statement đầu tiên hoặc transaction đã rollback toàn bộ. | Database có thực sự còn nguyên trạng trước rollback không? |
| Một số changeset đã rollback thành công | Các changeset gần nhất đã được đảo; một changeset tiếp theo thất bại. | Những changeset nào đã bị gỡ khỏi history và còn những thay đổi nào? |
| Một changeset rollback dở dang | Một vài statement trong rollback đã commit trước khi statement sau lỗi. | Object/data nào đã bị thay đổi một phần? |
| SQL rollback đã commit nhưng client mất kết nối | Database có thể đã đảo xong, nhưng Liquibase không nhận được kết quả cuối hoặc chưa cập nhật history. | Cần đối chiếu schema thực tế với hàng history. |
| Rollback không có SQL để chạy | Changeset không có rollback tự động hoặc rollback tùy chỉnh. | Có thể thiết kế rollback mới, forward fix hay phải phục hồi dữ liệu? |
| History đã thay đổi nhưng schema không đúng | Có thao tác thủ công, restore không đồng bộ hoặc behavior ngoài dự kiến. | Ai/thao tác nào làm lệch history và schema? |

Không giả định tất cả changeset của một lệnh rollback được bao trong một transaction lớn. Cũng không giả định một lỗi sẽ giữ nguyên mọi thay đổi trước đó. Phải đọc history và kiểm tra từng object/dữ liệu.

### 1.1. Ví dụ rollback qua nhiều changeset

Giả sử một release đã áp dụng ba changeset:

1. Tạo cột mới trên bảng khách hàng.
2. Backfill dữ liệu vào cột đó.
3. Thêm constraint kiểm tra dữ liệu.

Rollback thường đi theo thứ tự ngược:

1. Gỡ constraint.
2. Đảo dữ liệu backfill nếu rollback được định nghĩa.
3. Xóa cột.

Nếu bước 1 thành công nhưng bước 2 thất bại, database có thể đã bỏ constraint nhưng vẫn còn cột và dữ liệu. Nếu lệnh tiếp tục bị dừng, history có thể đã phản ánh changeset đầu tiên được rollback, trong khi changeset backfill và tạo cột vẫn còn. Tuy nhiên, nếu DDL/DML không transaction hoặc kết nối đứt đúng thời điểm commit, trạng thái có thể phức tạp hơn.

### 1.2. Bốn trạng thái phải đối chiếu

Khi điều tra, không chỉ xem một bảng history. Hãy so sánh:

- **Changelog:** rollback definition thực tế của từng changeset.
- **DATABASECHANGELOG:** changeset nào đang được ghi nhận, execution type và checksum.
- **Schema/data:** object, constraint, index và dữ liệu hiện có.
- **Ứng dụng/consumer:** phiên bản nào đang chạy và đang phụ thuộc vào schema nào.

Mục tiêu là tìm được trạng thái thật và xác định trạng thái đích an toàn.

## 2. Vì sao rollback có thể thất bại?

### 2.1. Thiếu quyền hoặc sai owner

Rollback thường cần quyền đối nghịch với migration: DROP object, ALTER table, xóa dữ liệu, khôi phục constraint hoặc cập nhật bảng metadata. Tài khoản có thể đã được cấp quyền CREATE/ALTER nhưng không có quyền DROP hoặc không sở hữu object.

Ví dụ:

- PostgreSQL báo không phải owner của table/index.
- MySQL từ chối DROP hoặc ALTER do thiếu quyền.
- SQL Server login có thể truy cập database nhưng không có quyền trên schema/object.
- Oracle user không có quyền ALTER/DROP object thuộc schema khác.

Kiểm tra user thực tế mà Liquibase sử dụng, object owner và quyền trên đúng database/schema. Không cấp DBA/superuser toàn hệ thống chỉ để vượt qua một lỗi rollback.

### 2.2. Object hoặc dữ liệu đã thay đổi sau migration

Rollback được viết theo giả định rằng database còn ở trạng thái ngay sau changeset. Nhưng ứng dụng, DBA hoặc job khác có thể đã:

- Tạo thêm index, constraint hoặc trigger.
- Rename/drop object.
- Ghi dữ liệu mới vào cột vừa được thêm.
- Thay đổi dữ liệu mà rollback dự định ghi đè.
- Tạo khóa ngoại hoặc view tham chiếu tới object cần drop.

Rollback có thể thất bại do dependency, hoặc chạy thành công nhưng làm mất dữ liệu hợp lệ. Cần kiểm tra consumer và dữ liệu phát sinh sau release.

### 2.3. Rollback definition không đúng

Các lỗi thường gặp:

- Rollback SQL dùng tên bảng/cột cũ trong khi changeset đã rename.
- Rollback xóa nhầm hàng do điều kiện WHERE quá rộng.
- Rollback insert/delete không xác định đúng khóa.
- Rollback custom dùng cú pháp chỉ hợp lệ trên DBMS khác.
- Rollback của changeset không khôi phục được giá trị trước đó vì không lưu before-image.
- Rollback có dependency sai thứ tự giữa foreign key, table, view và routine.

SQL rollback cần được review và thử trên database đại diện giống như SQL migration.

### 2.4. DDL không transactional hoặc implicit commit

Một số DDL tự commit hoặc không thể chạy trong transaction. Ví dụ MySQL có nhiều DDL implicit commit; PostgreSQL có ngoại lệ như CREATE INDEX CONCURRENTLY không thể chạy trong transaction block. Nếu rollback gồm nhiều statement, một số statement có thể đã có hiệu lực trước khi statement sau lỗi.

Đừng suy ra từ lỗi cuối rằng mọi câu lệnh rollback trước đó đều đã được đảo ngược.

### 2.5. Constraint hoặc dữ liệu ngăn việc đảo ngược

Rollback có thể muốn drop một cột hoặc bảng nhưng object đó đang được tham chiếu. Hoặc rollback muốn khôi phục một giá trị cũ nhưng dữ liệu hiện tại đã vi phạm unique/check/foreign key.

Ví dụ: sau khi thêm cột customer_code, một service mới đã ghi giá trị và một bảng khác tạo foreign key tới cột đó. Rollback drop column sẽ không thể thực hiện nếu dependency còn tồn tại; ép xóa constraint trước có thể làm hỏng dữ liệu của service khác.

### 2.6. Timeout, mất kết nối hoặc lock

Rollback có thể thất bại vì:

- Database quá tải hoặc statement chạy quá lâu.
- Lock bị giữ bởi truy vấn/transaction khác.
- Pool không cấp được connection.
- Kết nối bị reset sau khi server commit.
- Liquibase lock còn được giữ bởi tiến trình khác.
- Một migration khác chạy đồng thời trên cùng database.

Phải phân biệt Liquibase lock với DBMS lock. Hai loại lock giải quyết vấn đề khác nhau và cần điều tra ở hai lớp.

## 3. Việc cần làm ngay sau khi rollback thất bại

### 3.1. Dừng retry tự động

Tạm dừng pipeline rollback/redeploy tự động cho database bị ảnh hưởng. Không để job khác tiếp tục chạy update hoặc rollback trong khi trạng thái hiện tại chưa rõ. Nếu ứng dụng đang ghi dữ liệu sai, cân nhắc tạm hạn chế luồng ghi liên quan theo runbook incident.

Không dừng toàn bộ database theo phản xạ. Giữ hệ thống ở trạng thái có thể quan sát và bảo toàn log.

### 3.2. Ghi nhận bằng chứng

Thu thập:

- Thời điểm bắt đầu/kết thúc rollback và lệnh đã chạy.
- Liquibase version, DBMS/version, JDBC driver.
- Changelog artifact/commit và changeset ID, author, filename.
- Tag/count/date hoặc phạm vi rollback được chọn.
- SQL rollback được sinh hoặc SQL thực thi.
- Exception chain, SQLState, vendor error code.
- DATABASECHANGELOG trước/sau nếu có snapshot/log.
- DATABASECHANGELOGLOCK và session DBMS.
- Schema/data thực tế và phiên bản ứng dụng đang chạy.
- Backup/PITR gần nhất và RPO/RTO.

Không ghi password, token hoặc JDBC URL có chứa secret vào ticket/log.

### 3.3. Xác định rollback dừng ở đâu

Đọc log theo thứ tự statement và changeset:

1. Changeset nào được rollback hoàn tất?
2. Changeset nào đang được rollback khi lỗi xảy ra?
3. Statement đầu tiên thất bại là statement nào?
4. Statement trước đó có thể đã commit không?
5. Liquibase có cập nhật history cho changeset nào?
6. Database lock/session có còn hoạt động không?

Nếu log không đủ, đối chiếu system catalog, dữ liệu và DBMS audit. Không chạy lại rollback chỉ để xem nó sẽ lỗi ở đâu.

## 4. Quy trình phân loại trạng thái trước khi chọn phương án

| Nhóm trạng thái | Dấu hiệu | Hướng xử lý ban đầu |
|---|---|---|
| **Rollback chưa tạo side effect** | Không có statement nào thành công hoặc transaction rollback hoàn toàn. | Sửa nguyên nhân, preview lại và retry có kiểm soát. |
| **Một số changeset đã rollback hoàn tất** | Một phần history đã được cập nhật; các object tương ứng đã đảo. | Xác định mốc hiện tại rồi tiếp tục xử lý từ changeset còn lại. |
| **Rollback dở dang trong một changeset** | Object/data chỉ thay đổi một phần; history không thể mô tả chi tiết. | Điều tra từng statement và chọn đưa database về pre-state hoặc post-state. |
| **Rollback đã commit nhưng history chưa cập nhật** | Schema phản ánh rollback, history vẫn ghi changeset đã áp dụng. | Reconcile history bằng quy trình được kiểm soát sau khi chứng minh trạng thái. |
| **Rollback không khả thi về mặt dữ liệu** | Thiếu before-image, dữ liệu mới phụ thuộc object hoặc thao tác phá hủy không thể đảo. | Ưu tiên forward fix hoặc restore/selective recovery. |
| **Database và history lệch từ trước** | Có drift hoặc thao tác thủ công ngoài Liquibase. | Điều tra nguồn drift và lập remediation riêng. |

Không dùng trạng thái “changeset pending” hay “rollback command failed” làm bằng chứng duy nhất. Cần xác định side effect đã tồn tại ở database.

## 5. Cây quyết định chọn phương án phục hồi

~~~mermaid
flowchart TD
    A[Rollback Liquibase thất bại] --> B[Dừng retry, giữ log và xác định phạm vi]
    B --> C[Đối chiếu history, schema, dữ liệu và ứng dụng]
    C --> D{Database đã ở đúng trạng thái đích?}
    D -->|Có| E[Reconcile history có kiểm soát]
    D -->|Không| F{Rollback còn an toàn và khả thi?}
    F -->|Có| G{Lỗi chỉ do điều kiện có thể sửa?}
    G -->|Có| H[Sửa quyền, lock, cấu hình hoặc dependency]
    H --> I[Preview và retry rollback]
    G -->|Không| J[Thiết kế rollback thủ công có kiểm chứng]
    F -->|Không| K{Có thể sửa tiến mà bảo toàn dữ liệu?}
    K -->|Có| L[Forward fix bằng changeset mới]
    K -->|Không| M{Có backup/PITR đáng tin?}
    M -->|Có| N[Restore thử và lập kế hoạch reconciliation]
    M -->|Không| O[Giữ bằng chứng, tìm nguồn dữ liệu thay thế]
    I --> P[Kiểm tra hậu điều kiện]
    J --> P
    L --> P
    E --> P
    N --> P
    O --> P
    P --> Q[Smoke test, mở lại traffic và giám sát]
~~~

Sơ đồ giúp định hướng; incident commander, DBA và owner dữ liệu phải quyết định phương án cuối cùng theo mức độ ảnh hưởng, khả năng mất dữ liệu và mục tiêu khôi phục.

## 6. Phương án A: sửa nguyên nhân và chạy lại rollback

Đây là lựa chọn phù hợp khi rollback SQL vẫn đúng, database chưa bị thay đổi ngoài dự kiến và lỗi đến từ điều kiện có thể sửa như quyền, lock, kết nối hoặc cấu hình.

### 6.1. Điều kiện để retry

- Xác định được changeset và statement rollback đã thất bại.
- Xác minh statement trước đó đã rollback hoặc đã commit đúng như dự kiến.
- Database hiện tại vẫn thỏa precondition của rollback.
- Không có dữ liệu/consumer mới khiến rollback phá hủy dữ liệu hợp lệ.
- Đã xử lý nguyên nhân lỗi.
- SQL preview đã được xem lại và thử trên bản sao đại diện.
- Không có tiến trình Liquibase/DBMS khác đang thao tác cùng object.

### 6.2. Ví dụ thiếu quyền DROP

Một rollback cần drop index nhưng migration role chỉ có quyền tạo index. Cách xử lý:

1. Xác định index, table, schema và owner.
2. Xác minh rollback chỉ drop đúng index do changeset tạo.
3. Kiểm tra có query hoặc consumer phụ thuộc vào index đặc biệt không.
4. DBA cấp quyền tối thiểu cần thiết trên đúng object/role theo DBMS.
5. Sinh lại rollback SQL và review.
6. Thử trên bản sao đại diện.
7. Chạy rollback trong cửa sổ được kiểm soát.
8. Kiểm tra index đã được xử lý, history và query plan.

Không cấp superuser hoặc db_owner chỉ vì một lệnh DROP bị từ chối.

### 6.3. Ví dụ lock timeout

Nếu rollback không thể drop/alter object do DBMS lock:

1. Xác định session đang giữ lock và câu truy vấn/transaction liên quan.
2. Xác định owner của session và tác động nếu kết thúc session.
3. Chờ transaction hợp lệ hoàn tất hoặc điều phối dừng workload theo runbook.
4. Kiểm tra Liquibase lock và process migration.
5. Khi đã chắc chắn không còn tiến trình cạnh tranh, preview và retry.

Không kill session hoặc giải phóng DATABASECHANGELOGLOCK chỉ vì thời gian chờ đã lâu. Một transaction hợp lệ có thể vẫn đang chạy và nếu bị ngắt có thể để lại thêm trạng thái cần phục hồi.

## 7. Phương án B: hoàn tất rollback thủ công có kiểm soát

Đôi khi rollback Liquibase thất bại do một rollback statement không phù hợp với trạng thái hiện tại, nhưng nhóm vẫn muốn đưa database về trạng thái trước release. Khi đó có thể cần thao tác thủ công hoặc một script phục hồi riêng.

### 7.1. Khi nào cân nhắc?

- Rollback definition cũ sai hoặc thiếu.
- Một phần rollback đã commit và command không thể tiếp tục an toàn.
- Object đã được chỉnh sửa sau release nhưng có thể xác định trạng thái đích.
- Có thể đảo ngược thay đổi mà không làm mất dữ liệu hợp lệ.
- DBA và application owner đã thống nhất trạng thái cuối.

### 7.2. Lập bảng đối chiếu từng changeset

Trước khi chạy SQL, lập bảng:

| Changeset | Trạng thái trước release | Trạng thái hiện tại | Trạng thái đích | Hành động |
|---|---|---|---|---|
| add-customer-column | Không có cột | Cột còn tồn tại | Không có cột hoặc giữ tạm | Drop nếu không có dữ liệu cần giữ; nếu có thì chọn phương án khác. |
| backfill-customer | Giá trị cũ | Một phần giá trị mới | Giá trị cũ hoặc trạng thái đã chuyển đổi đúng | Dùng before-image hoặc nguồn đáng tin. |
| add-customer-check | Không có constraint | Constraint đã drop | Không có constraint | Không cần thao tác thêm. |

Mỗi hàng phải có bằng chứng từ catalog, dữ liệu và history. Không suy ra trạng thái từ thứ tự changeset một cách máy móc.

### 7.3. Dùng script có checkpoint

Một script thủ công nên:

- Có điều kiện xác định object và dữ liệu mục tiêu.
- Dùng transaction nếu DBMS và statement hỗ trợ.
- Ghi nhận số hàng trước/sau.
- Có kiểm tra hậu điều kiện sau mỗi bước.
- Có checkpoint để biết bước nào đã hoàn tất.
- Được review và thử trên bản sao production-like.
- Ghi log người thực hiện, thời điểm và phiên bản script.

Ví dụ kiểm tra trước khi xóa index PostgreSQL:

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'customer'
  AND indexname = 'idx_customer_email';
~~~

Sau khi xác minh đúng index và dependency, DBA mới chọn thao tác tương ứng. Ví dụ này chỉ đọc metadata, không phải lệnh xóa index.

### 7.4. Đồng bộ lại history sau thao tác thủ công

Nếu SQL thủ công đã đưa database về trạng thái trước changeset, history cần phản ánh đúng changeset nào vẫn được xem là đã áp dụng. Có thể cần chạy tiếp rollback qua Liquibase nếu trạng thái và command còn phù hợp, hoặc dùng một quy trình reconciliation được phê duyệt.

Không tự xóa hàng trong DATABASECHANGELOG để “làm cho Liquibase chạy lại”. Trước khi sửa history, phải chứng minh schema/data tương ứng với trạng thái mà history mới sẽ mô tả, và xác định chính xác các changeset phụ thuộc.

## 8. Phương án C: forward fix bằng changeset mới

Forward fix thường phù hợp khi rollback sẽ mất dữ liệu, rollback definition không còn đúng, hoặc database đã được ứng dụng sử dụng theo schema mới.

Thay vì cố quay về schema cũ, nhóm tạo changeset mới để đưa trạng thái hiện tại tới trạng thái ổn định, tương thích với phiên bản ứng dụng cần chạy.

### 8.1. Tình huống nên ưu tiên forward fix

- Cột mới đã nhận dữ liệu nghiệp vụ hợp lệ.
- Bảng mới đã được service khác tham chiếu.
- Rollback cần drop object nhưng object có consumer mới.
- Rollback DML không thể khôi phục giá trị trước đó.
- Một phần rollback đã làm mất constraint/index nhưng việc tái tạo schema cũ không cần thiết.
- Cần giữ cả binary cũ và mới hoạt động trong giai đoạn rolling deployment.

### 8.2. Ví dụ: rollback drop column thất bại vì dữ liệu mới

Giả sử changeset thêm cột preferred_language và ứng dụng mới đã ghi dữ liệu vào cột. Rollback dropColumn thất bại do dependency hoặc bị nhóm vận hành dừng vì nhận thấy dữ liệu mới cần giữ.

Một phương án forward fix:

1. Giữ cột mới.
2. Rollback binary ứng dụng về phiên bản có thể bỏ qua cột mới, hoặc phát hành hotfix tương thích.
3. Sửa dependency gây lỗi mà không xóa cột.
4. Giữ schema mở rộng trong thời gian chuyển đổi.
5. Chỉ contract/drop cột trong release sau khi xác nhận dữ liệu và consumer không còn cần.

Điều này có thể giảm downtime và bảo toàn dữ liệu, nhưng phải kiểm tra binary cũ có thực sự tương thích với schema mở rộng hay không.

### 8.3. Changeset mới phải phản ánh trạng thái hiện tại

Forward fix không phải sửa changeset cũ hoặc đổi checksum để bỏ qua lỗi. Hãy:

- Tạo ID mới, author và file path ổn định.
- Dùng precondition đủ mạnh để nhận diện trạng thái đầu vào.
- Xác định rõ hành vi khi object đã tồn tại một phần.
- Không dùng MARK_RAN nếu chưa chứng minh toàn bộ trạng thái đích.
- Có rollback definition nếu khả thi và an toàn.
- Kiểm tra trên database đã nhận rollback một phần và database chưa từng rollback.

Ví dụ precondition:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 061-preserve-customer-language
      author: db-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: customer
            tableName: customer_profile
        - columnExists:
            schemaName: customer
            tableName: customer_profile
            columnName: preferred_language
      changes:
        - sql:
            sql: COMMENT ON COLUMN customer.customer_profile.preferred_language IS 'Retained during compatibility recovery';
~~~

Ví dụ chỉ minh họa một changeset kiểm tra/ghi nhận cột còn tồn tại trên PostgreSQL; COMMENT không sửa dữ liệu và không thay thế phương án forward fix thực tế. Một precondition table/column exists không đủ chứng minh dữ liệu hợp lệ hoặc dependency đã được giải quyết.

## 9. Phương án D: khôi phục từ backup hoặc PITR

Restore/PITR phù hợp khi dữ liệu đã bị mất hoặc hỏng đến mức không thể tái tạo an toàn bằng rollback/forward fix. Đây thường là lựa chọn có phạm vi tác động lớn nhất.

### 9.1. Khi nào nên restore?

- Rollback DML đã ghi đè/xóa dữ liệu và không có before-image.
- Rollback thủ công làm hỏng dữ liệu trên nhiều bảng.
- Schema/data bị hỏng nghiêm trọng và không xác định được trạng thái đúng.
- Cần đưa database về một mốc nhất quán đã biết.
- Các thao tác phục hồi chọn lọc không thể đảm bảo toàn vẹn quan hệ.

Nếu chỉ một index bị thiếu, restore toàn database thường quá rộng. Nếu một tập dữ liệu quan trọng đã bị xóa và không có nguồn tái tạo, restore hoặc selective recovery có thể cần thiết.

### 9.2. Restore toàn database

Restore toàn database về một backup hoặc thời điểm PITR có thể đưa schema, dữ liệu và DATABASECHANGELOG về cùng một snapshot. Tuy nhiên, mọi giao dịch hợp lệ sau mốc đó cũng có thể biến mất.

Trước khi restore, xác định:

- Mốc cuối cùng được xác nhận tốt.
- Backup chain và WAL/binlog/archive log có đầy đủ không.
- RPO/RTO mục tiêu.
- Giao dịch phát sinh sau mốc cần replay hoặc đối soát.
- Ứng dụng, queue, cache, search index và hệ thống ngoài DB có thể đồng bộ lại thế nào.
- Cách cutover và quay lại nếu restore test không đạt.

### 9.3. Restore sang database mới trước

Nếu có thể, restore vào một instance/database cô lập:

1. Kiểm tra database mở được.
2. Kiểm tra schema, constraints, indexes và sequences.
3. Đọc DATABASECHANGELOG và xác định changeset đã tồn tại ở mốc đó.
4. So sánh dữ liệu bị ảnh hưởng với dữ liệu hiện tại.
5. Xác định phần dữ liệu sau mốc cần giữ.
6. Chạy smoke test bằng phiên bản ứng dụng dự kiến.

Chỉ sau khi kết quả được xác minh mới lập kế hoạch cutover production.

### 9.4. Selective recovery

Nếu chỉ một nhóm bảng/hàng bị hỏng, có thể trích dữ liệu từ bản restore riêng rồi merge vào database hiện tại. Cần xem:

- Foreign key và thứ tự insert.
- Unique key và xung đột với dữ liệu mới.
- Sequence/identity value.
- Trigger, generated column và default.
- Audit/history và quan hệ với hệ thống ngoài DB.
- Tính nhất quán giữa các bảng liên quan.

Selective recovery giảm mất dữ liệu mới nhưng khó hơn full restore. Không copy một bảng đơn lẻ nếu dữ liệu của nó phụ thuộc vào bảng khác đã thay đổi.

### 9.5. RPO, RTO và reconciliation

- **RPO:** khoảng dữ liệu tối đa tổ chức chấp nhận mất.
- **RTO:** thời gian mục tiêu để khôi phục dịch vụ.
- **Reconciliation:** đối soát/replay các giao dịch hoặc trạng thái phát sinh sau mốc restore.

Backup job thành công không chứng minh restore đạt RPO/RTO. Cần diễn tập phục hồi và đo thời gian thực tế.

## 10. Phương án E: sửa history khi database đã ở trạng thái đúng

Một trường hợp đặc biệt là rollback SQL đã commit nhưng kết nối đứt trước khi Liquibase cập nhật history. Schema có thể đã ở trạng thái rollback hoàn tất, nhưng DATABASECHANGELOG vẫn ghi changeset là đã áp dụng.

Trường hợp ngược lại cũng có thể xảy ra do thao tác thủ công hoặc restore: history cho biết changeset đã rollback nhưng schema vẫn còn object.

### 10.1. Điều kiện trước khi reconciliation

Phải chứng minh:

1. Mọi statement rollback của changeset đã hoàn tất.
2. Không còn object/data side effect nào cần đảo.
3. Constraint, index, view, trigger, sequence và grant đúng trạng thái.
4. Changeset phụ thuộc không bị bỏ sót.
5. Database đang ở đúng pre-state hoặc post-state đã chọn.
6. Không có tiến trình Liquibase khác đang chạy.
7. Phạm vi history cần cập nhật được xác định chính xác.

### 10.2. Không sửa DATABASECHANGELOG tùy tiện

Không xóa hàng history trực tiếp chỉ để Liquibase chạy lại. Không dùng changelogSync như một lệnh reset; command này có thể đánh dấu các changeset pending theo filter hiện tại là đã chạy mà không thực thi chúng. Không dùng clearCheckSums để sửa trạng thái schema.

Nếu cần baseline/reconciliation, dùng quy trình phù hợp phiên bản Liquibase và phạm vi được phê duyệt. Preview changeset nào bị ảnh hưởng, thử trên bản sao, sao lưu metadata và xác minh kết quả sau thao tác.

## 11. Đọc history và lock sau rollback lỗi

### 11.1. DATABASECHANGELOG

Các cột phổ biến:

- ID, AUTHOR, FILENAME: định danh changeset.
- DATEEXECUTED và ORDEREXECUTED: thời điểm/thứ tự được ghi nhận.
- EXECTYPE: trạng thái thực thi được ghi.
- MD5SUM: checksum theo cơ chế Liquibase.
- DEPLOYMENT_ID: định danh triển khai nếu phiên bản hỗ trợ.

Schema bảng thay đổi theo version. Kiểm tra cấu trúc thật trước khi viết truy vấn.

Ví dụ PostgreSQL:

~~~sql
SELECT id, author, filename, dateexecuted, orderexecuted, exectype, md5sum
FROM databasechangelog
ORDER BY orderexecuted DESC;
~~~

Đối chiếu changeset theo đủ ID, author và filename. Chỉ nhìn ID có thể nhầm changeset cùng tên ở file khác.

### 11.2. DATABASECHANGELOGLOCK

Lock còn được giữ có thể do migration vẫn chạy, session bị treo hoặc process chết trước khi giải phóng. Trước khi release lock:

1. Kiểm tra pipeline/job.
2. Kiểm tra session và statement phía DBMS.
3. Xác định process owner và thời điểm lock.
4. Xác nhận không có migration hợp lệ đang hoạt động.
5. Dùng command release lock Liquibase đúng phiên bản nếu thực sự cần.

Không xóa hàng lock bằng SQL nếu chưa xác định session. Việc giải phóng lock khi process cũ còn hoạt động có thể tạo hai tiến trình cùng thay đổi database.

### 11.3. Status sau rollback lỗi

Lệnh status cho biết changeset nào Liquibase coi là pending theo cấu hình hiện tại. Nó không kiểm tra đầy đủ schema drift hoặc side effect chưa ghi history. Sau rollback lỗi, dùng status như một tín hiệu rồi đối chiếu với catalog và dữ liệu thực tế.

## 12. Kiểm tra rollback SQL trước khi chạy lại

Liquibase có thể sinh SQL rollback để review trước khi thực thi. Command cụ thể thay đổi theo phiên bản; ví dụ dạng CLI thường gặp:

~~~bash
liquibase --changelog-file=db/changelog/master.yaml rollback-sql --tag=release-before-incident
~~~

Một số phiên bản dùng command/option khác hoặc hỗ trợ phạm vi rollback theo count/date. Kiểm tra liquibase --help và tài liệu đúng phiên bản trước khi dùng production.

Khi review SQL:

- Xác nhận đúng URL/database/schema.
- Xác nhận changeset sẽ rollback và thứ tự ngược.
- Tìm DROP TABLE, DROP COLUMN, DELETE, TRUNCATE và thao tác ghi đè.
- Xem điều kiện WHERE có giới hạn đúng dữ liệu không.
- Kiểm tra dependency giữa constraint, index, view và table.
- Xem DDL có transaction/implicit commit không.
- Kiểm tra rollback custom có dùng đúng cú pháp DBMS không.
- Xác định dữ liệu mới có bị xóa không.

SQL preview chỉ cho biết câu lệnh được sinh. Nó không chứng minh câu lệnh an toàn trên trạng thái database hiện tại hoặc không bị lock.

## 13. Khôi phục theo từng tình huống

### Tình huống A — Rollback thất bại do thiếu quyền DROP

**Triệu chứng:** rollback dừng ở DROP INDEX hoặc DROP TABLE với lỗi permission.

**Điều tra:** xác minh user Liquibase, owner object, schema và quyền cụ thể; kiểm tra các changeset rollback trước đó đã thành công chưa.

**Phương án:** nếu rollback SQL vẫn đúng và không có dependency mới, cấp quyền tối thiểu cho migration role, preview lại và retry. Nếu object thuộc owner khác hoặc có consumer mới, điều phối DBA/owner để chọn thao tác phù hợp.

### Tình huống B — Rollback drop column bị từ chối do foreign key

**Triệu chứng:** database báo column/table đang được constraint hoặc object khác tham chiếu.

**Điều tra:** liệt kê foreign key, view, trigger, routine và service phụ thuộc; xác định ai tạo dependency và khi nào.

**Phương án:** nếu dependency không hợp lệ và có thể gỡ, lên kế hoạch gỡ theo thứ tự rồi retry. Nếu dependency đại diện cho dữ liệu/consumer hợp lệ, giữ schema mở rộng và forward fix.

### Tình huống C — Rollback DML không thể khôi phục dữ liệu cũ

**Triệu chứng:** rollback update không có before-image hoặc điều kiện đảo ngược không còn đúng.

**Điều tra:** tìm audit, CDC, event log, backup, replica hoặc nguồn dữ liệu nghiệp vụ đáng tin.

**Phương án:** dùng forward correction từ nguồn chuẩn hoặc selective recovery. Không suy đoán giá trị cũ từ trạng thái hiện tại.

### Tình huống D — Rollback đã commit nhưng client timeout

**Triệu chứng:** pipeline báo lỗi nhưng object đã biến mất; history vẫn ghi changeset đã áp dụng.

**Điều tra:** DBMS log, schema catalog, history và session; xác định commit đã xảy ra.

**Phương án:** nếu toàn bộ rollback thực sự hoàn tất, reconciliation history có thể cần thiết. Chứng minh cả object lẫn dữ liệu, sau đó xử lý history theo quy trình được phê duyệt.

### Tình huống E — Một số changeset đã rollback, changeset kế tiếp lỗi

**Triệu chứng:** một phần release đã bị đảo; phần còn lại chưa.

**Điều tra:** đọc history, log và schema từng changeset. Xác định release đang ở trạng thái trung gian nào.

**Phương án:** không chạy lại lệnh rollback rộng mà không xem phạm vi còn lại. Có thể tiếp tục rollback từ trạng thái hiện tại nếu SQL còn phù hợp, hoặc chuyển sang forward fix để đưa hệ thống tới trạng thái ổn định.

### Tình huống F — Restore cần thiết nhưng có giao dịch mới

**Triệu chứng:** rollback không thể phục hồi dữ liệu bị xóa; backup tốt nhất ở thời điểm trước release.

**Điều tra:** xác định giao dịch sau mốc, hệ thống ngoài DB và khả năng replay.

**Phương án:** restore sang instance riêng, trích dữ liệu hoặc lập cutover có reconciliation. Không ghi đè production trước khi biết giao dịch nào sẽ mất.

## 14. Thiết kế rollback để có thể phục hồi

### 14.1. Viết rollback ngay trong changeset

Với change type không có rollback tự động phù hợp, khai báo rollback tường minh. Nhưng rollback phải có khả năng khôi phục đúng dữ liệu và trạng thái, không chỉ chạy câu SQL ngược.

Ví dụ insert dữ liệu tham chiếu có khóa xác định:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 070-add-default-language
      author: db-team
      changes:
        - insert:
            tableName: supported_language
            columns:
              - column:
                  name: code
                  value: vi
              - column:
                  name: display_name
                  value: Vietnamese
      rollback:
        - delete:
            tableName: supported_language
            where: code = 'vi'
~~~

Ví dụ chỉ an toàn nếu hàng code=vi do chính changeset tạo, không tồn tại trước và không được tham chiếu/được chỉnh sửa theo cách cần giữ. Nếu dữ liệu đã được sử dụng, rollback delete có thể phá tham chiếu hoặc xóa thay đổi hợp lệ.

### 14.2. Lưu before-image cho DML khó đảo

Nếu changeset update dữ liệu nghiệp vụ, cân nhắc lưu giá trị cũ với định danh release và khóa hàng trước khi thay đổi. Bảng before-image cần:

- Khóa duy nhất cho release và row identity.
- Thời điểm và nguồn dữ liệu.
- Giá trị cũ đủ để khôi phục.
- Quy tắc lưu giữ và bảo vệ truy cập.
- Kiểm tra số hàng snapshot khớp tập hàng update.

Rollback phải so sánh version/giá trị hiện tại trước khi ghi lại, để không xóa các cập nhật hợp lệ phát sinh sau migration.

### 14.3. Chia changeset theo ranh giới phục hồi

Tách các thay đổi có failure mode độc lập:

1. Expand schema.
2. Tạo index/constraint riêng nếu cần DDL không transaction.
3. Backfill theo batch/checkpoint.
4. Validate dữ liệu.
5. Chuyển consumer.
6. Contract sau.

Một changeset nhỏ giúp xác định phạm vi lỗi và rollback dễ hơn. Nhưng không nên chia quá vụn khiến các bước phụ thuộc không thể điều phối; mỗi changeset vẫn cần một mục tiêu và hậu điều kiện rõ ràng.

### 14.4. Thử rollback như một phần của release

Trong môi trường staging hoặc database clone:

- Chạy update từ schema ban đầu.
- Kiểm tra ứng dụng và dữ liệu sau update.
- Sinh rollback SQL.
- Chạy rollback trên bản sao.
- Kiểm tra schema/data trở lại trạng thái mong muốn.
- Thử cả trường hợp rollback lỗi giữa chừng nếu migration có DDL không transaction.

Rollback test phải dùng DBMS/version tương đương production. H2 không thay thế kiểm thử DDL và lock trên PostgreSQL, MySQL, Oracle hoặc SQL Server.

## 15. Phòng ngừa bằng expand–migrate–contract

Nhiều sự cố rollback xảy ra vì schema mới đã được ứng dụng sử dụng trước khi nhóm biết release có ổn định hay không. Expand–migrate–contract giảm nhu cầu rollback phá hủy.

Ví dụ đổi cột old_email thành normalized_email:

1. **Expand:** thêm normalized_email, giữ old_email.
2. **Deploy tương thích:** ứng dụng đọc/ghi theo cách hỗ trợ cả hai cột.
3. **Migrate:** backfill normalized_email và kiểm tra dữ liệu.
4. **Switch:** chuyển tất cả consumer sang cột mới.
5. **Observe:** theo dõi truy vấn và job còn dùng cột cũ.
6. **Contract:** xóa old_email trong release sau khi xác nhận không còn dependency.

Nếu release mới có lỗi ở giai đoạn 2, có thể rollback binary trong khi vẫn giữ schema mở rộng. Nếu đã contract và xóa cột cũ, rollback binary cũ có thể không còn khả thi nếu không phục hồi dữ liệu.

~~~mermaid
flowchart LR
    A[Schema cũ] --> B[Expand schema mới]
    B --> C[Deploy tương thích]
    C --> D[Backfill và xác minh]
    D --> E[Chuyển consumer]
    E --> F[Quan sát dependency cũ]
    F --> G[Contract ở release sau]
~~~

## 16. Quản lý ứng dụng trong lúc phục hồi

Database không hoạt động độc lập. Khi rollback thất bại, cần xác định binary nào có thể chạy với trạng thái schema hiện tại.

### 16.1. Ma trận tương thích

| Phiên bản ứng dụng | Schema cũ | Schema mở rộng | Schema đã contract |
|---|---|---|---|
| App cũ | Thường tương thích. | Chỉ tương thích nếu không bị ảnh hưởng bởi object mới. | Có thể lỗi nếu object cũ đã bị xóa/đổi. |
| App mới | Có thể lỗi nếu cần cột mới. | Thường là mục tiêu trong giai đoạn chuyển đổi. | Tương thích nếu đã chuyển hoàn toàn. |
| App hotfix | Phải xác định rõ contract hỗ trợ. | Thường được thiết kế để xử lý trạng thái trung gian. | Cần kiểm thử trước cutover. |

Không rollback binary trước khi xác minh schema mà binary đó cần. Nếu cần giữ service hoạt động, có thể dùng compatibility release hoặc tạm hạn chế endpoint ghi phụ thuộc vào phần schema lỗi.

### 16.2. Kiểm soát dữ liệu trong thời gian phục hồi

Nếu rollback hoặc restore có thể làm mất dữ liệu mới:

- Tạm dừng ghi vào phần bị ảnh hưởng nếu phù hợp.
- Ghi nhận giao dịch đang chờ hoặc message chưa xử lý.
- Bảo toàn event/audit/CDC để có thể replay.
- Tránh dual-write kéo dài mà không có cơ chế đối soát.
- Xác định rõ thời điểm mở lại traffic và kiểm tra dữ liệu.

## 17. Runbook mẫu cho rollback thất bại

Runbook dưới đây là khung để điều chỉnh theo tổ chức và DBMS:

### Pha A — Ổn định

1. Mở incident và xác định người điều phối.
2. Tạm dừng pipeline migration/rollback tự động.
3. Hạn chế luồng ghi có thể làm tăng hỏng dữ liệu.
4. Giữ log và thông tin triển khai.

### Pha B — Chẩn đoán

1. Xác định database/schema và user kết nối.
2. Đọc changeset, rollback definition và SQL preview.
3. Đọc DATABASECHANGELOG và DATABASECHANGELOGLOCK.
4. Kiểm tra session/lock phía DBMS.
5. Kiểm tra object, constraint, index và dữ liệu.
6. Xác định changeset nào đã rollback thành công và changeset nào đang lệch.

### Pha C — Quyết định

1. Có thể retry rollback an toàn sau khi sửa nguyên nhân không?
2. Có thể hoàn tất rollback thủ công mà bảo toàn dữ liệu không?
3. Có thể forward fix để giữ schema/data mới không?
4. Có cần restore/PITR hoặc selective recovery không?
5. Giao dịch sau mốc phục hồi được replay/reconcile thế nào?

### Pha D — Thực hiện

1. Thử trên bản sao đại diện.
2. Review SQL và phạm vi tác động.
3. Chuẩn bị backup/restore point nếu thao tác có rủi ro.
4. Thực hiện một bước tại một thời điểm, có checkpoint.
5. Không cho pipeline khác chạy đồng thời.

### Pha E — Xác minh và kết thúc

1. Kiểm tra schema/data theo hậu điều kiện.
2. Đối chiếu history và lock.
3. Kiểm thử binary ứng dụng và consumer.
4. Chạy smoke test, đối soát giao dịch và theo dõi lỗi.
5. Lưu quyết định, SQL, kết quả và bài học sự cố.

## 18. Bài thực hành có kiểm chứng

**Bối cảnh:** một ứng dụng quản lý khách hàng triển khai changeset thêm cột preferred_language, backfill dữ liệu và tạo constraint. Sau khi ứng dụng mới bắt đầu ghi dữ liệu, rollback gặp lỗi khi xóa cột do dependency mới.

### Giai đoạn A — Chuẩn bị trạng thái

1. Tạo database lab với bảng customer_profile và dữ liệu giả lập.
2. Viết changeset thêm cột, backfill và constraint thành các bước có thể quan sát.
3. Chạy update và ghi nhận history, schema, số hàng.
4. Tạo dependency giả lập từ một object/service khác.
5. Sinh rollback SQL và review các thao tác DROP/DELETE.

### Giai đoạn B — Tạo rollback failure

1. Thực hiện rollback trong lab để gặp lỗi dependency hoặc permission.
2. Lưu log và xác định changeset/statement thất bại.
3. Kiểm tra changeset nào đã được rollback và history đã thay đổi ra sao.
4. Kiểm tra cột, dữ liệu, constraint và dependency còn tồn tại.
5. Xác minh Liquibase lock và DBMS session.

### Giai đoạn C — So sánh phương án

1. Sửa điều kiện gây lỗi và thử retry rollback trên một bản sao.
2. Trên bản sao khác, thiết kế forward fix giữ cột và tương thích app cũ.
3. Tạo backup và thử restore sang database mới.
4. So sánh dữ liệu còn lại, history, thời gian và phạm vi ảnh hưởng.
5. Chọn phương án theo yêu cầu bảo toàn dữ liệu và RPO/RTO.

### Giai đoạn D — Reconciliation

1. Xác minh schema/data đạt trạng thái đích.
2. Đọc history và xác định changeset còn được ghi nhận.
3. Nếu cần reconciliation, lập phạm vi cụ thể và thử trên bản sao.
4. Kiểm tra status, validate và SQL preview.
5. Chạy smoke test bằng phiên bản ứng dụng dự kiến.

**Tiêu chí đạt:** phân biệt được rollback failure do permission, dependency, transaction hay dữ liệu; xác định changeset nào đã được đảo; lựa chọn được retry, manual recovery, forward fix hoặc restore; giữ history nhất quán với database và chứng minh ứng dụng hoạt động sau phục hồi.

## 19. Checklist chọn phương án phục hồi

- [ ] Đã dừng retry/pipeline và xác định process/session còn hoạt động.
- [ ] Đã lưu log, SQL rollback, changeset, version và phạm vi command.
- [ ] Đã đọc DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- [ ] Đã kiểm tra schema/data thực tế, không suy luận chỉ từ history.
- [ ] Đã xác định changeset nào rollback thành công và changeset nào thất bại.
- [ ] Đã xác minh DDL transaction/implicit commit của DBMS.
- [ ] Đã kiểm tra quyền, owner, dependency, constraint và consumer.
- [ ] Đã định lượng dữ liệu mới có thể mất nếu rollback tiếp.
- [ ] Đã quyết định retry, manual rollback, forward fix hay restore/PITR.
- [ ] Đã thử phương án trên database clone/staging tương đương.
- [ ] Đã xác định RPO/RTO và giao dịch cần replay/reconcile nếu restore.
- [ ] Đã kiểm tra ma trận tương thích ứng dụng/schema.
- [ ] Không sửa/xóa history hoặc release lock bằng SQL tùy tiện.
- [ ] Reconcile history chỉ sau khi chứng minh trạng thái database.
- [ ] Đã chạy validate, status, SQL preview và hậu kiểm schema/data.
- [ ] Đã smoke test, mở traffic có kiểm soát và giám sát sau phục hồi.
- [ ] Đã ghi lại quyết định, người thực hiện, thời điểm và kết quả.

## 20. Câu hỏi tự kiểm tra

1. Vì sao rollback command thất bại không chứng minh database còn nguyên trạng?
2. Một lệnh rollback qua nhiều changeset có thể để lại những trạng thái trung gian nào?
3. Vì sao DDL implicit commit làm rollback không còn atomic?
4. Cần phân biệt Liquibase lock và DBMS lock như thế nào?
5. Khi nào có thể sửa quyền rồi retry rollback?
6. Vì sao object dependency mới có thể khiến rollback drop column thất bại?
7. Khi nào nên dùng manual recovery và cần checkpoint gì?
8. Forward fix phù hợp trong trường hợp dữ liệu mới đã được ứng dụng sử dụng như thế nào?
9. Khi nào restore/PITR tốt hơn rollback hoặc forward fix?
10. Full restore và selective recovery khác nhau về tính nhất quán và phạm vi mất dữ liệu ra sao?
11. Vì sao phải restore thử sang database riêng trước khi cutover?
12. Reconciliation history cần chứng minh những điều gì?
13. Vì sao không được xóa DATABASECHANGELOG để ép Liquibase chạy lại?
14. Expand–migrate–contract giảm rủi ro rollback phá hủy như thế nào?
15. Sau khi phục hồi, cần kiểm tra những gì ngoài schema và history?

## Kết luận

Khi rollback thất bại, **đừng giả định database đã quay về hoặc vẫn nguyên trạng**. Hãy dừng retry, giữ log, xác định changeset và statement đã hoàn tất, rồi đối chiếu DATABASECHANGELOG, lock, schema, dữ liệu và phiên bản ứng dụng. Nếu lỗi chỉ do điều kiện có thể sửa và rollback còn an toàn, preview rồi retry; nếu rollback không còn phù hợp, chọn manual recovery hoặc forward fix bằng changeset mới; nếu dữ liệu đã mất/hỏng và không thể tái tạo, đánh giá restore/PITR cùng kế hoạch replay/reconciliation. Chỉ đồng bộ history sau khi chứng minh database đạt trạng thái tương ứng. Thiết kế rollback, backup, compatibility và diễn tập phục hồi từ trước giúp **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** giảm thời gian gián đoạn và bảo toàn dữ liệu khi triển khai gặp sự cố.
