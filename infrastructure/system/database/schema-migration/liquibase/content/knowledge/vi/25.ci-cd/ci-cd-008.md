# Xử lý pipeline bị hủy, chạy lại hoặc lỗi một phần

## 1. Bối cảnh và mục tiêu

Một pipeline CI/CD có thể bị hủy do người dùng bấm Cancel, runner hết thời gian, pod bị thu hồi, mất kết nối mạng hoặc một bước kiểm tra thất bại. Khi pipeline đang chạy Liquibase, những sự kiện đó tạo ra một câu hỏi quan trọng: **database đã thay đổi đến đâu?**

Trạng thái job không phải là bằng chứng đầy đủ về trạng thái database. Một runner có thể báo timeout trong khi câu SQL vẫn còn chạy trên DBMS; một câu DDL có thể đã commit nhưng Liquibase chưa kịp ghi nhận changeset; hoặc changeset đã hoàn tất và được ghi vào lịch sử nhưng pipeline lỗi ở bước kiểm tra sau triển khai. Những tình huống này có cách xử lý khác nhau.

Bài thuộc chương **CI/CD** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **xử lý pipeline bị hủy, chạy lại hoặc lỗi một phần**, giúp nhóm khôi phục có kiểm soát và giữ lịch sử migration chính xác.

Sau bài học, bạn cần có thể:

1. Phân biệt pipeline bị hủy trước migration, trong khi chạy SQL và sau khi migration đã hoàn tất.
2. Hiểu vai trò của DATABASECHANGELOG và DATABASECHANGELOGLOCK khi job bị dừng bất thường.
3. Đối chiếu log, trạng thái session DBMS, lịch sử changeset, schema và dữ liệu trước khi retry.
4. Nhận diện rủi ro transaction, DDL implicit commit và changeset chạy ngoài transaction.
5. Chọn retry, rollback, cleanup hoặc forward fix theo trạng thái thực tế.
6. Thiết kế pipeline chỉ có một chủ sở hữu migration trên mỗi database.
7. Dùng precondition, hậu kiểm, artifact bất biến và runbook để giảm rủi ro triển khai lặp.
8. Kiểm thử kịch bản cancel/timeout/failure trên database có thể hủy trước khi áp dụng quy trình cho production.

## 2. Vì sao job thất bại không nói lên database đã thất bại?

Một lượt triển khai thường có nhiều bước: lấy artifact, kết nối database, kiểm tra changelog, lấy khóa, thực thi SQL, ghi lịch sử, kiểm tra sau triển khai và thông báo kết quả. Pipeline có thể dừng ở bất kỳ bước nào.

Ví dụ:

~~~text
CI/CD job
   |
   v
Tải artifact và cấu hình
   |
   v
Kết nối database
   |
   v
Liquibase lấy DATABASECHANGELOGLOCK
   |
   v
Chạy changeset / SQL
   |
   v
Ghi DATABASECHANGELOG
   |
   v
Hậu kiểm schema và ứng dụng
   |
   v
Pipeline báo thành công
~~~

Nếu pipeline bị hủy ở bước hậu kiểm, migration có thể đã hoàn tất. Nếu runner mất kết nối trong khi DBMS đang thực thi DDL, kết quả có thể chưa rõ. Nếu job bị hủy trước khi Liquibase bắt đầu, database có thể chưa bị tác động.

Vì vậy, cần tách hai trạng thái:

- **Trạng thái điều phối:** job, runner, pod, process và bước CI/CD.
- **Trạng thái database:** session DBMS, transaction, khóa, schema, dữ liệu và lịch sử Liquibase.

Chỉ khi hai nhóm thông tin được đối chiếu, người vận hành mới quyết định được có thể chạy lại hay phải phục hồi.

## 3. Các kiểu gián đoạn thường gặp

| Kiểu sự cố | Điều có thể đã xảy ra | Việc cần xác minh |
|---|---|---|
| Hủy trước bước Liquibase update | Chưa có changeset nào được thực thi | Xác nhận lệnh update chưa được gọi và không có job khác |
| Hủy khi đang chờ DATABASECHANGELOGLOCK | Liquibase có thể chưa bắt đầu changeset | Kiểm tra job đang giữ khóa và trạng thái khóa |
| Hủy khi đang chạy SQL | SQL có thể chưa chạy, đang chạy hoặc đã hoàn tất | Kiểm tra session, transaction và đối tượng bị tác động |
| Runner timeout/mất mạng | Client mất liên lạc nhưng server có thể còn xử lý | Kiểm tra DB session và trạng thái thật, không dựa vào exit code |
| Một changeset lỗi | Transaction có thể rollback hoặc thay đổi một phần tùy DBMS | Đối chiếu DATABASECHANGELOG với schema/dữ liệu |
| Một changeset thành công, changeset sau lỗi | Một phần release đã được áp dụng | Xác định changeset cuối cùng hoàn tất và phần pending |
| Migration xong, hậu kiểm thất bại | Schema có thể đã được cập nhật đầy đủ | Kiểm tra điều kiện hậu kiểm và tương thích ứng dụng |
| Job bị chạy hai lần song song | Một job giữ khóa, job khác chờ hoặc lỗi | Xác định chủ sở hữu và tránh retry song song |
| Container/pod bị kill | Connection có thể đóng hoặc server phát hiện đóng muộn | Kiểm tra session, transaction và lock table |

**Không thể suy ra database chưa thay đổi chỉ từ thông báo “Canceled”, “Timed out” hoặc exit code khác 0.**

## 4. Hai bảng Liquibase cần kiểm tra

### 4.1. DATABASECHANGELOG ghi nhận changeset

Liquibase lưu lịch sử changeset trong DATABASECHANGELOG. Các cột thường gặp gồm ID, AUTHOR, FILENAME, DATEEXECUTED, ORDEREXECUTED, EXECTYPE và MD5SUM; tên/cấu trúc chi tiết phụ thuộc phiên bản và cấu hình.

Bản ghi cho biết Liquibase đã ghi nhận changeset theo lịch sử như thế nào. Nó không phải snapshot đầy đủ của schema và không chứng minh mọi câu lệnh ngoài Liquibase đều được quản lý.

Ví dụ truy vấn chỉ đọc:

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
ORDER BY orderexecuted;
~~~

Điều chỉnh schema/tên bảng theo cấu hình thực tế. Nếu metadata nằm trong schema riêng, cần truy vấn đúng schema.

### 4.2. DATABASECHANGELOGLOCK điều phối các lượt chạy

DATABASECHANGELOGLOCK dùng để ngăn các tiến trình Liquibase đồng thời cập nhật cùng lịch sử một cách không phối hợp. Thông tin thường gồm ID, LOCKED, LOCKGRANTED và LOCKEDBY.

Truy vấn minh họa:

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM databasechangeloglock;
~~~

Khóa này khác khóa bảng/hàng mà DBMS dùng khi thực thi SQL. Một job có thể giữ khóa Liquibase trong khi câu DDL đang chờ khóa DBMS. Ngược lại, việc không thấy lock Liquibase không chứng minh không có SQL khác đang chặn migration.

### 4.3. Đọc hai bảng cùng nhau

| DATABASECHANGELOG | DATABASECHANGELOGLOCK | Cách diễn giải ban đầu |
|---|---|---|
| Chưa có changeset mới | LOCKED=false | Có thể job chưa bắt đầu hoặc đã dừng trước update; vẫn kiểm tra schema nếu có dấu hiệu SQL đã chạy |
| Changeset mới được ghi | LOCKED=false | Changeset đã được ghi nhận; cần hậu kiểm phần còn lại |
| Changeset mới được ghi | LOCKED=true | Có thể job còn chạy changeset tiếp theo hoặc trạng thái khóa chưa được giải phóng |
| Không có bản ghi mới | LOCKED=true | Có thể job đang chạy, đang chờ hoặc đã dừng bất thường; cần tìm holder |
| Không có bản ghi mới | LOCKED=false | Chưa đủ kết luận SQL chưa tác động; DDL không transactional có thể đã thay đổi schema |

Bảng này chỉ là hướng điều tra. Không dùng một tổ hợp trạng thái để tự động quyết định release-locks hoặc retry mà chưa xem log, session và schema thật.

## 5. Hiểu ranh giới transaction của changeset

Liquibase thường thực thi changeset trong transaction khi DBMS và loại thao tác hỗ trợ. Nếu một câu lệnh trong changeset lỗi và toàn bộ thay đổi nằm trong transaction có thể rollback, DBMS có thể hoàn tác phần thay đổi chưa commit.

Nhưng không thể giả định mọi DDL đều transactional trên mọi DBMS:

- PostgreSQL hỗ trợ transaction cho nhiều thao tác DDL, nhưng có ngoại lệ như CREATE INDEX CONCURRENTLY không được chạy trong transaction block thông thường.
- Oracle có quy tắc implicit commit đối với nhiều DDL.
- MySQL có hành vi implicit commit và atomic DDL phụ thuộc phiên bản/engine/thao tác.
- SQL Server hỗ trợ transaction cho nhiều DDL nhưng cần kiểm tra từng lệnh và tùy chọn.

Vì vậy, một changeset thất bại có thể để lại trạng thái khác nhau tùy DBMS, câu lệnh và cấu hình.

### 5.1. runInTransaction

Thuộc tính runInTransaction điều khiển việc Liquibase chạy changeset trong transaction theo khả năng hỗ trợ. Giá trị mặc định thường là true, nhưng phải kiểm tra phiên bản và hành vi DBMS.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 120-create-index-concurrently
      author: platform-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            sql: |
              CREATE INDEX CONCURRENTLY ix_orders_created_at
              ON app.orders (created_at);
~~~

PostgreSQL không cho phép CREATE INDEX CONCURRENTLY chạy bên trong transaction block thông thường, nên changeset cần được tổ chức phù hợp. Nếu lệnh thất bại, có thể còn index không hợp lệ; phải kiểm tra catalog và dọn dẹp có kiểm soát trước retry.

**runInTransaction: false không phải cách chữa lỗi transaction chung.** Nếu changeset gồm nhiều câu lệnh, một số câu có thể đã thành công trước khi câu sau lỗi. Khi đó, database có thể ở trạng thái áp dụng một phần.

### 5.2. Một changeset không transactional nên nhỏ và dễ xác minh

Nếu bắt buộc dùng thao tác ngoài transaction:

- Đặt một thao tác chính trong một changeset riêng.
- Có precondition kiểm tra điều kiện đầu vào.
- Xác định trạng thái có thể để lại khi thất bại.
- Có truy vấn hậu kiểm để biết thao tác đã hoàn thành chưa.
- Có cleanup hoặc forward fix được review.
- Không tự động retry nếu chưa kiểm tra object thực tế.

Đừng gom nhiều DDL không transactional vào một changeset dài nếu không có lý do rõ ràng.

## 6. Vì sao DATABASECHANGELOG có thể chưa phản ánh thay đổi một phần?

Liquibase ghi nhận changeset sau khi xử lý thành công theo cơ chế của công cụ và DBMS. Với changeset chạy trong transaction, việc thực thi và ghi lịch sử có thể được phối hợp trong transaction đó. Với DDL implicit commit hoặc changeset không transactional, một câu lệnh có thể đã thay đổi database trước khi một bước sau thất bại.

Ví dụ:

~~~text
Changeset X (runInTransaction=false)
   |
   +-- CREATE TABLE staging_copy  -> thành công
   |
   +-- CREATE INDEX ix_copy       -> lỗi
   |
   +-- Ghi DATABASECHANGELOG      -> chưa được ghi
~~~

Khi đó, lần update tiếp theo có thể xem changeset X là chưa hoàn tất và cố chạy lại. Nếu SQL không idempotent hoặc bảng staging_copy đã tồn tại, lần chạy lại sẽ tiếp tục lỗi.

Đây là lý do phải kiểm tra **schema và dữ liệu thật** song song với DATABASECHANGELOG. Lịch sử là nguồn bằng chứng quan trọng nhưng không phải bằng chứng duy nhất cho các thay đổi có thể commit một phần.

## 7. Trạng thái không chắc chắn sau khi cancel hoặc timeout

Có ba nhóm cần phân biệt:

### 7.1. Kết quả đã biết

Có log xác nhận Liquibase chưa gọi update, hoặc DBMS xác nhận transaction đã rollback và không còn thay đổi. Có thể tiếp tục theo quy trình bình thường sau khi kiểm tra job khác.

### 7.2. Kết quả đã hoàn tất

DATABASECHANGELOG có bản ghi cho changeset, schema/dữ liệu đúng và hậu kiểm xác nhận kết quả. Nếu pipeline chỉ lỗi ở bước thông báo hoặc artifact hậu kiểm, có thể chạy lại phần pipeline còn thiếu hoặc thực hiện hậu kiểm riêng. Không cần chạy lại migration chỉ để biến trạng thái CI thành xanh.

### 7.3. Kết quả chưa rõ

Client mất kết nối, job bị kill, log bị cắt hoặc session DBMS còn chạy. Đây là trường hợp nguy hiểm nhất. Dừng retry, xác minh process/session, lock, history và schema. Chỉ tiếp tục sau khi có kết luận về trạng thái thực tế.

Một nguyên tắc vận hành hữu ích: **khi không biết SQL đã commit hay chưa, hãy coi kết quả là chưa xác định và điều tra trước khi phát lệnh thay đổi tiếp theo.**

## 8. Quy trình điều tra sau khi pipeline bị hủy

### Bước 1. Ghi nhận sự kiện và artifact

Lưu lại:

- ID pipeline/job/run và commit được triển khai.
- Artifact changelog và checksum hoặc version.
- Phiên bản Liquibase, Java và JDBC driver.
- Môi trường, database, schema và tài khoản migration.
- Thời điểm bắt đầu, thời điểm hủy và bước cuối cùng trong log.
- Lý do hủy: người dùng, timeout, runner, mạng, lỗi SQL hay lỗi hậu kiểm.

Không thay artifact hoặc commit khi đang điều tra. Cần biết chính xác nội dung changelog mà job đã sử dụng.

### Bước 2. Xác nhận process và session cũ

Kiểm tra runner, container, pod và process Liquibase. Sau đó kiểm tra session DBMS để xác định:

- Connection migration còn hoạt động không?
- Có câu SQL đang chạy hoặc chờ khóa không?
- Transaction còn mở không?
- Session thuộc job nào và user nào?
- Có một job khác đang thực thi migration không?

Nếu client đã mất kết nối, DBMS có thể cần thời gian mới phát hiện connection đóng, tùy driver, network và server. Không khởi chạy job mới song song khi session cũ còn khả năng thực thi.

### Bước 3. Kiểm tra DATABASECHANGELOGLOCK

Xem LOCKED, LOCKGRANTED và LOCKEDBY, sau đó đối chiếu với process/session. LOCKED=true có thể là job đang chạy hợp lệ hoặc trạng thái còn lại sau sự cố. Không chỉ dựa vào tuổi của LOCKGRANTED để kết luận stale lock.

### Bước 4. Kiểm tra DATABASECHANGELOG

Xác định changeset cuối cùng đã được ghi nhận. So sánh ID, AUTHOR, FILENAME, EXECTYPE và checksum với artifact đã triển khai.

Nếu changeset mới chưa có bản ghi, không kết luận ngay rằng SQL chưa chạy. Kiểm tra loại DDL, transaction boundary và schema thực tế.

### Bước 5. Kiểm tra schema và dữ liệu

Với từng changeset đang nghi ngờ, kiểm tra:

- Bảng/cột/index/constraint/view/function có tồn tại không?
- Định nghĩa có đúng với changelog không?
- Dữ liệu đã được insert/update/delete đến đâu?
- Sequence/identity có ở trạng thái phù hợp không?
- Quyền/owner có bị thay đổi không?
- Có object dở dang hoặc không hợp lệ không?
- Có tác động phụ nào lên ứng dụng/replication không?

Chọn truy vấn metadata phù hợp DBMS. Tránh sửa ngay object để “cho giống” trước khi lưu bằng chứng.

### Bước 6. Chọn hướng xử lý và ghi quyết định

Ghi rõ: migration chưa bắt đầu, đã hoàn tất, đã rollback, áp dụng một phần hay chưa xác định. Chỉ sau khi xác nhận mới chọn retry, cleanup, rollback hoặc forward fix.

## 9. Quyết định có thể chạy lại hay không

| Tình trạng đã xác minh | Có nên retry ngay? | Hướng xử lý |
|---|---|---|
| Job dừng trước Liquibase update, không có session khác | Có thể tiếp tục sau preflight | Chạy lại từ bước migration |
| Chỉ lỗi khi chờ khóa changelog, job giữ khóa vẫn hoạt động | Không | Chờ holder hoàn tất hoặc điều phối job |
| Changeset đã ghi trong DATABASECHANGELOG, hậu kiểm đạt | Không cần chạy lại migration | Chạy lại hậu kiểm/notification hoặc bước CI còn thiếu |
| Changeset đã ghi nhưng hậu kiểm không đạt | Không | Điều tra schema/data, tạo kế hoạch forward fix hoặc rollback |
| Changeset không có bản ghi, transaction đã rollback và không còn thay đổi | Có thể retry sau khi xác nhận | Chạy lại cùng artifact sau preflight |
| Changeset không có bản ghi nhưng một phần DDL đã tồn tại | Không | Reconcile trạng thái, cleanup an toàn hoặc forward fix |
| Session DBMS cũ còn chạy | Không | Theo dõi và kết thúc session theo runbook |
| DATABASECHANGELOGLOCK=true nhưng không xác định được holder | Không | Điều tra trước; chỉ release khi chứng minh stale |
| Không biết câu SQL đã commit chưa | Không | Giữ pipeline dừng, xác minh DBMS và object |

Retry chỉ an toàn khi hiểu điều gì đã xảy ra. Câu lệnh “update có thể chạy lại” không có nghĩa mọi changeset đều idempotent.

## 10. Liquibase update có idempotent không?

Liquibase dùng định danh changeset và DATABASECHANGELOG để tránh thực thi lại changeset đã được ghi nhận là hoàn tất. Điều đó tạo ra khả năng tiếp tục một release sau khi các changeset trước đã chạy thành công.

Nhưng idempotency của **lịch sử điều phối** khác idempotency của **SQL**:

- Nếu changeset đã được ghi nhận, update thường không chạy lại changeset đó.
- Nếu changeset chưa được ghi nhận nhưng SQL đã tác động một phần, update có thể thử lại.
- Nếu SQL có CREATE TABLE không có kiểm tra trạng thái, lần retry có thể báo object đã tồn tại.
- Nếu DML cộng dồn hoặc không có khóa ổn định, retry có thể tạo dữ liệu trùng hoặc cập nhật sai.
- Nếu thao tác chạy ngoài transaction, trạng thái dở dang cần được xử lý trước.

Không nên thêm IF NOT EXISTS vào mọi câu lệnh chỉ để tránh lỗi retry. Một object cùng tên nhưng sai định nghĩa không phải là trạng thái thành công. Cần precondition và hậu kiểm xác minh **định nghĩa**, không chỉ sự tồn tại.

## 11. Thiết kế changeset để phục hồi dễ hơn

### 11.1. Giữ changeset nhỏ và có một mục tiêu rõ

Một changeset nên mô tả một thay đổi logic có thể kiểm tra. Tránh kết hợp tạo bảng, backfill hàng triệu dòng, tạo index online, đổi quyền và drop cột cũ vào cùng một đơn vị không thể phân tích khi lỗi.

Chia nhỏ giúp xác định chính xác bước nào đã hoàn tất và giảm phạm vi điều tra.

### 11.2. Preconditions có chủ đích

Precondition có thể xác minh DBMS, bảng/cột tồn tại, hoặc dữ liệu đáp ứng điều kiện trước khi thực thi. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 205-add-customer-status
      author: platform-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: app
            tableName: customer
        - not:
            - columnExists:
                schemaName: app
                tableName: customer
                columnName: status
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: status
                  type: VARCHAR(30)
~~~

Ví dụ này yêu cầu bảng tồn tại và cột status chưa có. Nếu cột đã tồn tại sau một lần DDL dở dang, precondition sẽ dừng để người vận hành điều tra. Đây là lựa chọn có chủ đích: dừng rõ ràng an toàn hơn tự coi object có tên đúng là object đã được tạo đúng.

Không dùng MARK_RAN để che một trạng thái chưa rõ. Chỉ dùng chính sách MARK_RAN khi việc bỏ qua changeset đã được chứng minh là đúng và được ghi nhận.

### 11.3. DML có khóa ổn định

Khi thêm dữ liệu tham chiếu, dùng khóa tự nhiên hoặc khóa nghiệp vụ ổn định và kiểm tra trước/sau. Tránh insert lặp không kiểm soát.

Với backfill lớn, chia batch theo khóa ổn định, có checkpoint và tiêu chí hoàn tất. Liquibase không tự biến một UPDATE lớn thành nhiều transaction nhỏ; có thể cần job backfill riêng hoặc thiết kế migration nhiều giai đoạn.

### 11.4. Không sửa changeset lịch sử để phục hồi

Khi một changeset đã triển khai cần sửa, tạo changeset mới để điều chỉnh trạng thái. Sửa nội dung cũ có thể gây checksum mismatch và làm lịch sử giữa các môi trường không còn nhất quán.

## 12. Xử lý DATABASECHANGELOGLOCK sau khi job bị kill

Liquibase thường giải phóng khóa changelog khi lượt chạy kết thúc bình thường. Nếu process bị kill hoặc kết nối bị gián đoạn bất thường, trạng thái khóa có thể còn lại và các lượt chạy tiếp theo bị chặn.

Trình tự an toàn:

1. Xác nhận process/runner/pod cũ đã kết thúc.
2. Kiểm tra không còn session DBMS đang chạy SQL từ job đó.
3. Xác nhận không có pipeline khác đang sở hữu migration.
4. Đọc LOCKEDBY/LOCKGRANTED và đối chiếu log.
5. Kiểm tra DATABASECHANGELOG cùng schema/dữ liệu để biết migration đã tiến tới đâu.
6. Chỉ khi đã xác nhận khóa thực sự stale, dùng lệnh quản trị Liquibase phù hợp.
7. Sau giải phóng, chạy status/validate và hậu kiểm trước khi update.

Lệnh CLI thường dùng để giải phóng stale changelog lock:

~~~bash
liquibase --defaults-file=liquibase.properties release-locks
~~~

Cú pháp tùy phiên bản. **release-locks chỉ giải phóng khóa điều phối Liquibase**; nó không rollback SQL, không hủy session DBMS đang chạy và không sửa object dở dang.

Không tự động gắn release-locks vào nhánh finally/cleanup của pipeline. Nếu job A còn chạy, job B hoặc bước cleanup có thể giải phóng khóa của A và cho phép một lượt migration khác chen vào. Cũng không cập nhật LOCKED trực tiếp bằng SQL trừ quy trình khẩn cấp được DBA phê duyệt và có kiểm chứng.

## 13. Chọn rollback hay forward fix?

### 13.1. Rollback

Rollback phù hợp khi:

- Thay đổi đã hoàn tất và có rollback được review.
- Dữ liệu có thể phục hồi hoặc chưa phát sinh dữ liệu mới cần giữ.
- DBMS hỗ trợ cách rollback tương ứng.
- Ứng dụng tương thích với trạng thái schema sau rollback.
- Có backup và quy trình kiểm tra kết quả.

Liquibase có thể rollback theo tag/count/date hoặc phạm vi được hỗ trợ. Tuy nhiên, rollback chỉ biết những changeset được ghi nhận trong lịch sử và có logic rollback tương ứng. Một DDL đã commit một phần nhưng changeset chưa được ghi nhận có thể không được rollback command tự động xử lý.

### 13.2. Forward fix

Forward fix thường phù hợp khi:

- Migration đã hoàn tất và ứng dụng có thể đã ghi dữ liệu vào cấu trúc mới.
- Rollback làm mất dữ liệu hoặc gây gián đoạn lớn.
- Có thể tạo changeset mới để đưa schema/data về trạng thái mong muốn.
- Một thao tác ngoài transaction để lại object dở dang cần được hòa giải.

Ví dụ, nếu một cột mới đã tồn tại và có dữ liệu hợp lệ nhưng changeset chưa được ghi nhận, không drop cột ngay. Kiểm tra định nghĩa, nullable/default, dữ liệu và phụ thuộc; sau đó chọn cách hòa giải lịch sử hoặc tạo migration sửa lỗi theo quy trình được phê duyệt.

### 13.3. So sánh

| Tiêu chí | Rollback | Forward fix |
|---|---|---|
| Mục tiêu | Quay về trạng thái trước | Tiến tới trạng thái đúng tiếp theo |
| Dữ liệu mới phát sinh | Có thể mất nếu rollback phá hủy | Có thể giữ và chuyển đổi |
| Phụ thuộc | Rollback logic, DBMS và trạng thái history | Changeset sửa lỗi mới, hậu kiểm |
| Phù hợp | Thay đổi mới, chưa có consumer/data quan trọng | Release đã lan rộng hoặc rollback rủi ro |
| Rủi ro | Rollback không hoàn chỉnh hoặc không tương thích | Cần thiết kế migration sửa lỗi chính xác |

Không có quy tắc rằng forward fix luôn tốt hơn rollback. Quyết định dựa trên dữ liệu, khả năng khôi phục và mức ảnh hưởng ứng dụng.

## 14. Những lệnh không nên dùng như nút sửa lỗi chung

| Lệnh/cơ chế | Mục đích đúng | Vì sao không thay thế quy trình phục hồi |
|---|---|---|
| update | Áp dụng changeset pending | Có thể chạy lại SQL khi trạng thái trước chưa rõ |
| rollback | Hoàn tác changeset có rollback | Không nhất thiết xử lý DDL một phần chưa ghi history |
| release-locks | Giải phóng stale changelog lock | Không rollback hoặc hủy SQL DBMS |
| clear-checksums | Xóa checksum đã lưu để tính lại | Không sửa schema và không hòa giải changeset dở dang |
| changelogSync | Ghi nhận changeset như đã chạy mà không thực thi SQL | Có thể tạo history sai nếu schema chưa tương ứng |
| markNextChangeSetRan | Đánh dấu changeset kế tiếp là đã chạy theo cơ chế lệnh | Không thực thi SQL để hoàn tất thay đổi |
| validCheckSum | Cho phép checksum cụ thể được chấp nhận | Không sửa trạng thái schema/data |
| runOnChange | Chạy lại changeset khi checksum thay đổi theo quy tắc | Không phải cơ chế retry một migration bị dở dang |
| runAlways | Chạy changeset ở mỗi lượt update phù hợp | Không tự làm DML/DDL an toàn khi chạy lặp |

Không chọn một lệnh chỉ vì tên của nó có vẻ giải quyết triệu chứng. Trước hết xác định database đang ở trạng thái nào.

## 15. Quy trình retry an toàn

Một lần retry có kiểm soát nên thực hiện theo trình tự:

1. **Đóng băng lượt chạy cũ:** xác nhận job cũ không còn khả năng thực thi.
2. **Giữ nguyên artifact:** dùng đúng commit/changelog đã chạy, không thay bằng bản mới trong lúc điều tra.
3. **Xác minh đích:** host, database, schema, user và môi trường.
4. **Kiểm tra lock:** xác định DATABASECHANGELOGLOCK và holder.
5. **Kiểm tra history:** changeset cuối cùng đã ghi nhận, checksum và EXECTYPE.
6. **Kiểm tra schema/data:** so sánh với postcondition mong đợi của từng changeset nghi ngờ.
7. **Hòa giải trạng thái dở dang:** cleanup hoặc forward fix được review nếu cần.
8. **Xác nhận không có blocker:** không có session cũ hoặc job khác chạy migration.
9. **Chạy validate/status:** xem changeset pending trước khi update.
10. **Review SQL dự kiến:** dùng update-sql khi phù hợp.
11. **Retry có giới hạn:** chạy một job sở hữu migration, có timeout và log đầy đủ.
12. **Hậu kiểm:** xác minh schema, dữ liệu, history và chức năng ứng dụng.

Retry phải có số lần giới hạn và điều kiện dừng. Không lặp vô hạn sau lock timeout, deadlock, checksum mismatch hoặc lỗi precondition. Những lỗi đó thường cần điều tra nguyên nhân thay vì thử lại cùng một lệnh.

## 16. Ví dụ tình huống: runner bị kill khi tạo index

Giả sử pipeline chạy changeset PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 310-create-orders-index
      author: platform-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            sql: |
              CREATE INDEX CONCURRENTLY ix_orders_created_at
              ON app.orders (created_at);
~~~

Runner bị kill sau khi gửi câu SQL nhưng trước khi ghi được kết quả cuối cùng vào log.

### 16.1. Không retry ngay

Lệnh có thể:

- Chưa được server nhận.
- Đang chạy.
- Đã tạo index thành công.
- Thất bại và để lại index không hợp lệ.

DATABASECHANGELOG có thể chưa có bản ghi changeset nếu Liquibase chưa hoàn tất ghi lịch sử. Vì thế, kiểm tra history một mình chưa đủ.

### 16.2. Kiểm tra PostgreSQL

Xác nhận session từ runner cũ còn chạy không bằng pg_stat_activity. Kiểm tra index trong catalog, ví dụ:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'app'
  AND idx.relname = 'ix_orders_created_at';
~~~

Truy vấn này giúp xác định index có tồn tại và trạng thái valid/ready. Cần kiểm tra thêm định nghĩa index và các tùy chọn dự kiến; chỉ cùng tên chưa chứng minh cấu trúc đúng.

### 16.3. Chọn hướng tiếp tục

- Nếu không có index và không còn session cũ: xác nhận nguyên nhân, kiểm tra lock rồi retry theo kế hoạch.
- Nếu index hợp lệ, định nghĩa đúng và changeset chưa ghi history: cần hòa giải lịch sử bằng quy trình được review; không chạy lại CREATE INDEX một cách mù quáng.
- Nếu index không hợp lệ: xác định nguyên nhân và dùng lệnh cleanup phù hợp sau khi chắc chắn không có build index đang chạy; sau đó mới retry.
- Nếu index tồn tại nhưng sai cột/điều kiện: không coi là thành công; lập kế hoạch thay thế hoặc forward fix.

Ví dụ này cho thấy cùng một exit code có thể dẫn tới nhiều trạng thái database khác nhau.

## 17. Ví dụ tình huống: migration hoàn tất nhưng pipeline timeout

Pipeline chạy update thành công, DATABASECHANGELOG đã ghi các changeset. Sau đó bước smoke test chờ ứng dụng khởi động quá lâu và job timeout.

Không chạy lại migration chỉ để sửa trạng thái job. Thay vào đó:

1. Xác nhận changeset đã ghi đầy đủ.
2. Kiểm tra schema và dữ liệu.
3. Xác minh ứng dụng đang trỏ đúng database.
4. Điều tra smoke test: startup, kết nối, quyền, cache hoặc lỗi nghiệp vụ.
5. Chạy lại bước kiểm tra sau triển khai nếu an toàn.
6. Ghi nhận migration thành công và bước hậu kiểm thất bại riêng biệt.

Nếu ứng dụng không tương thích schema mới, cần chọn rollback hoặc forward fix theo khả năng phục hồi và chiến lược tương thích.

## 18. Ví dụ tình huống: một changeset gồm nhiều câu lệnh

Một changeset có ba câu lệnh SQL và runInTransaction=false:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 320-create-reporting-objects
      author: platform-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            sql: CREATE TABLE app.report_stage (id BIGINT PRIMARY KEY);
        - sql:
            sql: CREATE INDEX CONCURRENTLY ix_report_stage_id ON app.report_stage (id);
        - sql:
            sql: GRANT SELECT ON app.report_stage TO report_reader;
~~~

Nếu câu đầu thành công, câu thứ hai thất bại, câu thứ ba chưa chạy, database có thể có bảng nhưng không có index/quyền mong muốn và changeset có thể chưa được ghi nhận hoàn tất.

Một lần retry có thể lỗi ngay ở CREATE TABLE vì bảng đã tồn tại. Cách thiết kế tốt hơn là chia thành changeset nhỏ, có precondition và hậu kiểm rõ ràng. Với thao tác không transactional, mỗi đơn vị nên có một trạng thái thành công/thất bại dễ xác minh.

Ví dụ trên chỉ minh họa rủi ro; nếu index trùng với khóa chính hoặc index đã có, hãy xem xét liệu có cần tạo index riêng hay không trước khi triển khai.

## 19. Thiết kế pipeline có một chủ sở hữu migration

Một database chỉ nên có một luồng điều phối migration cho một thời điểm. Có thể đạt điều này bằng:

- Concurrency group/lock ở hệ thống CI/CD.
- Một job migration riêng trước khi rollout ứng dụng.
- Quy tắc chỉ một release pipeline có quyền chạy Liquibase trên database.
- Tách tài khoản migration khỏi runtime.
- Không để mọi replica Spring Boot và job CI cùng chủ động update production mà thiếu điều phối.

DATABASECHANGELOGLOCK là lớp bảo vệ của Liquibase, nhưng không thay thế hoàn toàn điều phối pipeline. Một job khác có thể chờ khóa, chiếm runner hoặc timeout, và những công cụ chạy SQL trực tiếp không bị khóa changelog ngăn lại.

### 19.1. Ví dụ pipeline theo giai đoạn

~~~text
Build
  |
  v
Đóng gói artifact bất biến
  |
  v
Validate changelog + kiểm tra artifact
  |
  v
Review update-sql + phê duyệt môi trường
  |
  v
Migration job (một chủ sở hữu)
  |
  v
Kiểm tra history + schema + dữ liệu
  |
  v
Deploy/rollout ứng dụng
  |
  v
Smoke test + quan sát
  |
  v
Ghi nhận kết quả release
~~~

Tùy kiến trúc, ứng dụng có thể được rollout trước hoặc sau migration nếu schema thay đổi theo chiến lược expand-contract. Nhưng phải xác định rõ tương thích giữa phiên bản ứng dụng đang chạy và schema trong từng giai đoạn.

### 19.2. Artifact phải bất biến

Không build lại changelog từ branch đang thay đổi giữa các lần retry. Giữ cùng:

- Commit/tag release.
- JAR hoặc migration bundle.
- Phiên bản Liquibase.
- JDBC driver.
- Cấu hình đã được review.
- Danh sách contexts/labels.
- Thông tin database đích.

Nếu cần sửa migration sau sự cố, tạo artifact/release mới với changeset sửa lỗi mới. Không thay nội dung changeset đã chạy trong artifact cũ.

## 20. Timeout, cancel và cơ chế dừng

Pipeline nên đặt timeout cho từng tầng: lấy connection, chờ khóa Liquibase, chờ khóa DBMS, thực thi statement và toàn job. Timeout tổng thể không tự đảm bảo DBMS đã dừng câu SQL.

Khi cancel:

- Gửi tín hiệu dừng có kiểm soát nếu runner hỗ trợ.
- Cho process cơ hội đóng connection và ghi log kết thúc.
- Nếu phải force kill, đánh dấu kết quả database là chưa xác định cho tới khi kiểm tra.
- Không chạy cleanup tự động giải phóng lock mà không biết holder.
- Thu thập log, session và trạng thái database trước khi xóa runner/pod nếu có thể.

Nếu mất mạng, server có thể phát hiện connection đóng muộn. Cần dùng timeout/keepalive và giám sát session phù hợp, nhưng không coi chúng là bảo đảm tuyệt đối rằng mọi câu SQL dừng ngay khi client biến mất.

## 21. Retry policy cho từng loại lỗi

| Lỗi | Retry tự động? | Chính sách phù hợp |
|---|---|---|
| DNS/connect tạm thời trước khi gửi SQL | Có thể, số lần giới hạn | Backoff, xác minh database identity khi kết nối lại |
| Database đang bảo trì | Chỉ khi có cửa sổ retry rõ | Chờ theo lịch, không lặp vô hạn |
| DATABASECHANGELOGLOCK đang được job khác giữ | Không chạy song song | Chờ holder hoàn tất hoặc fail rõ ràng |
| Lock timeout DBMS | Không mặc định | Tìm blocker, đánh giá maintenance window |
| Deadlock | Có thể retry nghiệp vụ trong một số trường hợp; migration cần điều tra | Kiểm tra transaction và tác động trước retry |
| Checksum mismatch | Không | Đối chiếu changelog/Git/version, không clear-checksums tự động |
| Precondition HALT | Không | Sửa điều kiện hoặc dữ liệu sau review |
| SQL syntax/permission error | Không | Sửa SQL/quyền và phát hành changeset mới nếu cần |
| Statement timeout | Không mặc định | Xác định SQL đã commit hay chưa, đánh giá tài nguyên |
| Runner bị kill/mất mạng trong SQL | Không | Trạng thái chưa xác định; reconcile DB trước |
| Hậu kiểm thất bại sau update | Không chạy lại migration ngay | Điều tra ứng dụng và schema; quyết định rollback/forward fix |

Retry có backoff chỉ phù hợp với lỗi tạm thời mà ta biết chưa có thay đổi database hoặc đã xác minh an toàn. Không để một cơ chế retry chung bao phủ mọi loại lỗi Liquibase.

## 22. Hậu kiểm sau khi chạy lại hoặc phục hồi

Sau khi retry, rollback hoặc forward fix, cần kiểm tra:

### 22.1. Lịch sử Liquibase

- Changeset dự kiến có bản ghi chưa?
- ID, AUTHOR, FILENAME có đúng không?
- EXECTYPE có phản ánh kiểu thực thi mong muốn không?
- Checksum có khớp artifact được phát hành không?
- Không có changeset pending ngoài kế hoạch?
- DATABASECHANGELOGLOCK đã được giải phóng đúng cách?

### 22.2. Schema và dữ liệu

- Bảng, cột, index, constraint, view và function đúng định nghĩa?
- Dữ liệu backfill có đủ, không trùng, không thiếu?
- Sequence/identity và foreign key đúng?
- Quyền owner/runtime/migration có phù hợp?
- Không còn object dở dang hoặc index không hợp lệ?
- Có ảnh hưởng tới replication, backup hoặc query performance không?

### 22.3. Ứng dụng và release

- Ứng dụng kết nối đúng database.
- Readiness/liveness đạt theo tiêu chí.
- Các luồng đọc/ghi quan trọng hoạt động.
- Log không còn lỗi tương thích schema.
- Smoke test và giám sát sau deploy đạt.
- Release record ghi rõ migration, hậu kiểm và mọi ngoại lệ.

Chỉ đánh dấu release hoàn tất khi các điều kiện được định nghĩa trong runbook đạt, không chỉ vì lệnh Liquibase trả exit code 0.

## 23. Kiểm thử kịch bản gián đoạn trong môi trường có thể hủy

Đừng đợi production mới học cách xử lý pipeline bị kill. Có thể xây dựng các bài diễn tập trên database disposable hoặc bản sao đã ẩn danh.

| Bài diễn tập | Cách tạo tình huống | Điều cần quan sát |
|---|---|---|
| Hủy trước update | Dừng job sau validate | Không có changeset mới, không còn session/lock |
| Hủy khi chờ lock | Giữ lock bằng một job test khác | Job thứ hai chờ và kết thúc theo timeout |
| Hủy trong DDL transactional | Chạy thay đổi có thể rollback rồi cancel | Transaction rollback và history phù hợp |
| Hủy sau DDL non-transactional | Dừng sau câu lệnh đầu của changeset nhiều bước | Nhận diện object dở dang và cleanup |
| Mất kết nối client | Ngắt kết nối khi SQL đang chạy | Xác minh session server và trạng thái commit |
| Hủy sau update trước smoke test | Dừng pipeline ở bước hậu kiểm | Không chạy lại migration nếu history/schema đã đạt |
| Chạy hai job cùng lúc | Khởi chạy hai migration job có chủ ý | Chỉ một job lấy lock; job còn lại được điều phối |
| Retry sau lỗi | Chạy lại cùng artifact sau reconcile | Không tạo object/dữ liệu trùng |

Ghi lại thời điểm, log, trạng thái lock, DATABASECHANGELOG, catalog/schema và quyết định phục hồi. Bài diễn tập có giá trị khi người vận hành có thể giải thích vì sao một trạng thái được xem là an toàn để retry.

## 24. Runbook xử lý sự cố ngắn

Khi nhận thông báo pipeline bị hủy, timeout hoặc lỗi một phần:

**Dừng thay đổi tiếp theo**
- Tạm ngưng các pipeline migration khác trên cùng database.
- Không tự động retry, rollback, clear-checksums, changelogSync hoặc release-locks.
- Giữ nguyên artifact và log của job cũ.

**Xác minh**
- Job/process/runner cũ còn chạy không?
- DBMS còn session hoặc transaction của job cũ không?
- DATABASECHANGELOGLOCK có holder nào?
- Changeset cuối cùng được ghi trong DATABASECHANGELOG là gì?
- Schema và dữ liệu thật đã thay đổi đến đâu?
- Có DDL implicit commit hoặc runInTransaction=false không?

**Phân loại**
- Chưa bắt đầu.
- Đã hoàn tất.
- Đã rollback.
- Áp dụng một phần.
- Chưa xác định.

**Khôi phục**
- Retry nếu trạng thái đã sạch và an toàn.
- Cleanup object dở dang theo DBMS/runbook.
- Rollback nếu rollback logic và dữ liệu phù hợp.
- Forward fix nếu thay đổi đã được dùng hoặc rollback rủi ro.
- Release stale lock chỉ sau khi xác nhận không còn holder.

**Hậu kiểm**
- Kiểm tra history, schema, dữ liệu, quyền và ứng dụng.
- Ghi nhận quyết định, người thực hiện, artifact và kết quả.
- Chỉ mở lại pipeline khi một chủ sở hữu migration được xác định.

## 25. Những sai lầm cần tránh

| Sai lầm | Hệ quả | Cách làm đúng |
|---|---|---|
| Retry ngay khi job báo timeout | SQL trước có thể vẫn đang chạy hoặc đã commit | Reconcile session, history và schema trước |
| Tin DATABASECHANGELOG là bằng chứng duy nhất | DDL một phần có thể chưa được ghi history | Kiểm tra catalog và dữ liệu thật |
| Gọi release-locks trong cleanup luôn luôn | Có thể giải phóng khóa của job vẫn hoạt động | Chỉ release khi chứng minh stale |
| Coi mọi DDL đều rollback được | Một số DBMS implicit commit hoặc lệnh không transactional | Kiểm tra hành vi từng DBMS/lệnh |
| Dùng runInTransaction=false cho changeset lớn | Dễ để lại trạng thái áp dụng một phần | Tách changeset và có recovery plan |
| Tự động clear-checksums sau checksum error | Che dấu changeset lịch sử bị sửa | Đối chiếu Git/artifact và xử lý nguyên nhân |
| Dùng changelogSync để bỏ qua migration lỗi | History có thể nói đã chạy trong khi schema thiếu | Chỉ sync khi đã chứng minh schema tương ứng |
| Coi object cùng tên là object đúng | Định nghĩa/cột/index có thể khác | So sánh định nghĩa và thuộc tính |
| Chạy song song app startup và CI migration | Cạnh tranh lock và khó điều phối | Một chủ sở hữu migration |
| Build lại artifact khi retry | Nội dung changelog có thể khác lần chạy đầu | Giữ artifact bất biến |
| Tăng timeout vô hạn | Kéo dài blocking và che vấn đề | Chẩn đoán blocker, đặt budget theo tầng |
| Rollback không xem dữ liệu mới | Có thể xóa dữ liệu nghiệp vụ đã phát sinh | Đánh giá dữ liệu và tương thích trước rollback |

## 26. Checklist trước khi cho phép retry

- [ ] Job cũ và runner/container cũ đã dừng hoặc không còn khả năng gửi lệnh.
- [ ] Không còn session DBMS từ job cũ đang thực thi hoặc chờ.
- [ ] Không có job khác đang sở hữu migration trên database.
- [ ] Đã xác minh đúng host, database, schema và user.
- [ ] Đã đọc DATABASECHANGELOGLOCK và xác định holder.
- [ ] Đã xác định changeset cuối cùng được ghi trong DATABASECHANGELOG.
- [ ] Đã kiểm tra các changeset chưa ghi history nhưng có thể đã tác động DBMS.
- [ ] Đã kiểm tra schema, dữ liệu, index, constraint và quyền thật.
- [ ] Đã hiểu transaction/implicit commit/runInTransaction của từng thao tác.
- [ ] Đã xác định trạng thái: chưa bắt đầu, hoàn tất, rollback, một phần hoặc chưa rõ.
- [ ] Đã chọn retry, cleanup, rollback hoặc forward fix và ghi lý do.
- [ ] Dùng đúng artifact, commit, phiên bản Liquibase và cấu hình đã review.
- [ ] Có giới hạn retry, timeout, log và hậu kiểm.
- [ ] Có người chịu trách nhiệm theo dõi migration tới khi kết thúc.

## 27. Kết luận

Pipeline bị hủy, chạy lại hoặc lỗi một phần là tình huống cần xử lý theo **trạng thái thật của database**, không theo trạng thái hiển thị của job. DATABASECHANGELOG cho biết những changeset Liquibase đã ghi nhận; DATABASECHANGELOGLOCK điều phối các lượt chạy; còn schema, dữ liệu và session DBMS cho biết những thay đổi nào thực sự đã xảy ra. Ba nhóm bằng chứng này phải được đối chiếu, đặc biệt khi DDL không transactional hoặc changeset dùng runInTransaction=false.

Quy trình an toàn là dừng các lượt migration cạnh tranh, giữ nguyên artifact, xác minh process/session và lock, đọc lịch sử, kiểm tra schema/dữ liệu, phân loại trạng thái rồi mới quyết định retry, cleanup, rollback hoặc forward fix. Pipeline nên có một chủ sở hữu migration, artifact bất biến, retry giới hạn, precondition và hậu kiểm rõ ràng.

Cách vận hành này phục vụ mục tiêu của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**: quản lý changeset, checksum và lịch sử triển khai có thể kiểm chứng; phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD mà vẫn giữ được tính nhất quán, khả năng phục hồi và dấu vết kiểm toán.

