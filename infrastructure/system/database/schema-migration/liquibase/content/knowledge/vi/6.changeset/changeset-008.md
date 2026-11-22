# Thuộc tính runInTransaction và phạm vi kiểm soát giao dịch

## 1. Mục tiêu của bài học

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Người học cần thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Bài thuộc chương **Changeset**, tập trung vào thuộc tính **runInTransaction** và câu hỏi thực tế: *Liquibase có thể hoàn tác phần việc nào khi một migration lỗi giữa chừng?* Đây là chủ đề quan trọng bởi một lệnh DDL có thể thành công ở cơ sở dữ liệu nhưng changeset vẫn lỗi trước khi lịch sử triển khai được ghi lại.

Sau bài này, bạn cần phân biệt được:

- Ranh giới giao dịch của **một changeset** với ranh giới của toàn bộ changelog hoặc một đợt phát hành.
- Ý nghĩa của **runInTransaction: true** và **runInTransaction: false**.
- Bảo đảm mà Liquibase yêu cầu so với bảo đảm giao dịch thực sự do hệ quản trị cơ sở dữ liệu cung cấp.
- Trường hợp cần thực thi SQL ngoài transaction, đặc biệt các lệnh như PostgreSQL **CREATE INDEX CONCURRENTLY**.
- Cách ứng phó khi một changeset chạy được một phần, cách kiểm tra DATABASECHANGELOG và cách thiết kế rollback, precondition, quy trình triển khai an toàn.

## 2. Hiểu đúng transaction trong Liquibase

### 2.1. Giao dịch là gì?

**Transaction** (giao dịch) là nhóm thao tác cơ sở dữ liệu có thể được xác nhận (**commit**) hoặc hoàn tác (**rollback**) theo cơ chế của hệ quản trị. Khi một nhóm thao tác thực sự nằm trong một giao dịch và database hỗ trợ rollback đối với các thao tác ấy, lỗi trước commit có thể khiến các thay đổi chưa commit được khôi phục về trạng thái ban đầu.

Ví dụ nghiệp vụ dễ hình dung là chuyển tiền giữa hai tài khoản: trừ tiền ở A và cộng tiền ở B phải cùng thành công hoặc cùng thất bại. Với migration, mong muốn tương tự là tạo hai cấu trúc liên quan mà không để lại trạng thái “mới tạo một nửa” nếu lệnh sau gặp lỗi.

Tuy nhiên, **DDL và DML không có tính giao dịch giống nhau trên mọi DBMS**:

- DML như INSERT/UPDATE/DELETE thông thường có thể rollback khi nằm trong transaction, tùy loại bảng, engine và cấu hình.
- Nhiều thao tác DDL trên PostgreSQL có thể nằm trong transaction; nhưng một số lệnh bắt buộc chạy ngoài transaction.
- Nhiều thao tác DDL trên MySQL và Oracle có thể gây implicit commit hoặc không có khả năng rollback như DML.
- SQL Server và các hệ quản trị khác có phạm vi hỗ trợ DDL trong giao dịch riêng, tùy lệnh và phiên bản.

Vì vậy, muốn đánh giá an toàn của một migration phải xem **thuộc tính changeset, SQL được sinh ra và khả năng của DBMS đích**.

### 2.2. Đơn vị giao dịch mặc định: changeset

Liquibase dùng một hoặc nhiều changelog để tổ chức các **changeset**. Trong điều kiện thông thường, Liquibase tìm các changeset chưa chạy, đánh giá precondition, thực hiện các change rồi ghi thông tin vào bảng **DATABASECHANGELOG**.

Khi **runInTransaction: true** và hệ quản trị hỗ trợ giao dịch cho các thao tác đang chạy, Liquibase cố gắng thực hiện **mỗi changeset** trong một giao dịch. Điều này không có nghĩa cả tệp changelog, cả phiên bản phát hành hay hàng chục changeset cùng nằm trong một transaction.

Ví dụ:

~~~text
Changelog phát hành
  |
  +-- Changeset A: tạo customer       -> transaction A -> commit
  |
  +-- Changeset B: thêm status         -> transaction B -> commit
  |
  +-- Changeset C: tạo index           -> transaction C -> lỗi
~~~

Nếu C thất bại, **A và B đã commit trước đó sẽ không tự động bị rollback** chỉ vì C lỗi. Trong một hệ quản trị có hỗ trợ transactional DDL, phần chưa commit của C có thể được rollback, nhưng A và B vẫn là lịch sử triển khai hợp lệ.

Đây là điểm cần nhớ khi chạy Liquibase trong CI/CD: thất bại giữa một đợt migration không đồng nghĩa toàn bộ đợt được hoàn tác về trước khi chạy.

## 3. runInTransaction là thuộc tính gì?

**runInTransaction** là thuộc tính của **changeset**, xác định Liquibase có cố gắng bao các thay đổi trong changeset bằng một transaction hay không.

| Giá trị | Ý nghĩa | Khi nào nên dùng |
|---|---|---|
| **true** | Liquibase chạy changeset trong transaction khi DBMS hỗ trợ; đây là giá trị mặc định | Phần lớn thay đổi cấu trúc hoặc dữ liệu có khả năng thực thi trong transaction |
| **false** | Liquibase không bao changeset trong một transaction do nó quản lý | Trường hợp DBMS yêu cầu câu lệnh chạy ngoài transaction hoặc có lý do kỹ thuật rõ ràng |
| Không khai báo | Giữ hành vi mặc định **true** | Lựa chọn ưu tiên với changeset thông thường |

Đặt thuộc tính ở **changeSet**, không đặt ở cấp toàn bộ databaseChangeLog và cũng không đặt bên trong một change type:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-001
      author: schema-team
      runInTransaction: true
      changes:
        - createTable:
            tableName: feature_flag
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: flag_key
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
~~~

Trong ví dụ này, **runInTransaction: true** được ghi tường minh để người đọc thấy ý định; bỏ dòng đó vẫn giữ mặc định true. Không nên đặt false chỉ vì changeset chạy lâu, gặp lock hoặc vì muốn “tăng tốc”. Tắt transaction làm thay đổi cách khôi phục sau sự cố, nhưng không tự động tối ưu hiệu năng.

## 4. runInTransaction: true hoạt động ra sao?

Giả sử một changeset bổ sung hai cột cho một bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-002
      author: schema-team
      runInTransaction: true
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: email_verified
                  type: BOOLEAN
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: verified_at
                  type: TIMESTAMP
      rollback:
        - dropColumn:
            tableName: customer
            columnName: verified_at
        - dropColumn:
            tableName: customer
            columnName: email_verified
~~~

Trong DBMS hỗ trợ rollback các thao tác DDL tương ứng, nếu lệnh thêm cột thứ hai lỗi trước commit, transaction có thể hoàn tác cả lệnh thêm cột thứ nhất. Liquibase báo lỗi và changeset chưa được đánh dấu là đã thực thi thành công.

Nhưng **runInTransaction: true không thể ép database hỗ trợ điều mà nó không hỗ trợ**. Nếu một DBMS thực hiện implicit commit cho lệnh ALTER TABLE, cột thứ nhất có thể đã tồn tại dù Liquibase báo lỗi ở cột thứ hai. Vì vậy, không được suy ra tính nguyên tử chỉ từ giá trị thuộc tính.

### Điều kiện để đạt tính nguyên tử mong muốn

1. Mọi SQL trong changeset phải hỗ trợ giao dịch theo đúng DBMS và phiên bản đang chạy.
2. Connection và transaction mode phải phù hợp; không có lệnh nào tự commit hoặc yêu cầu chạy ngoài transaction.
3. Nếu dùng change type do Liquibase sinh SQL, cần kiểm tra SQL thực tế vì một change type có thể tạo nhiều câu lệnh tùy DBMS.
4. Nếu có thay đổi ngoài database (gọi dịch vụ, ghi file, thủ tục tác động ngoại hệ thống), transaction SQL không tự rollback những tác động đó.
5. Hành vi rollback khi chạy lỗi phải được kiểm chứng trên database thử nghiệm tương thích môi trường đích.

### Giao dịch chưa đồng nghĩa rollback triển khai

**Rollback transaction** là thao tác hoàn tác các thay đổi chưa commit của một lần thực thi.

**Rollback migration** là quy trình chủ động đưa database về trạng thái trước các changeset đã commit, thường dùng rollback được Liquibase khai báo hoặc công cụ quản trị.

Hai việc này khác nhau. Một changeset đã commit thành công sẽ không bị transaction rollback khi changeset sau thất bại. Muốn hoàn tác nó cần chạy một rollback có kiểm chứng, và dữ liệu mất đi có thể không khôi phục được chỉ bằng DDL.

## 5. Khi nào cần runInTransaction: false?

Một số câu lệnh database **không được phép chạy trong transaction block**. Chẳng hạn PostgreSQL yêu cầu **CREATE INDEX CONCURRENTLY** được thực thi ngoài transaction block. Đây là ví dụ điển hình để đặt **runInTransaction: false**.

Mục đích dùng CONCURRENTLY là giảm mức độ chặn ghi lên bảng so với cách xây dựng index thông thường trong một số tình huống; việc xây dựng index vẫn tiêu tốn tài nguyên và có thể chạy lâu. Cần cân nhắc tải hệ thống và đặc điểm bảng trước khi áp dụng.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-003
      author: schema-team
      dbms: postgresql
      runInTransaction: false
      comment: Tạo index orders.created_at ngoài transaction
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: orders
        - not:
            - indexExists:
                tableName: orders
                indexName: idx_orders_created_at
      changes:
        - sql:
            sql: CREATE INDEX CONCURRENTLY idx_orders_created_at ON orders (created_at)
      rollback:
        - sql:
            sql: DROP INDEX CONCURRENTLY IF EXISTS idx_orders_created_at
~~~

**Giải thích ví dụ:**

- **dbms: postgresql** giới hạn changeset cho PostgreSQL.
- **runInTransaction: false** cho phép câu CREATE INDEX CONCURRENTLY chạy ngoài transaction do Liquibase quản lý.
- **preConditions** yêu cầu bảng đã tồn tại và index cùng tên chưa tồn tại, giúp phát hiện trạng thái không mong đợi.
- Changeset chứa **một thao tác chính** để giới hạn tác hại nếu quá trình bị ngắt.
- **rollback** nêu rõ thao tác xóa index, và chính lệnh DROP INDEX CONCURRENTLY cũng cần điều kiện thực thi phù hợp ngoài transaction.

**Cần kiểm tra trên đúng phiên bản Liquibase và PostgreSQL mà dự án sử dụng.** Công cụ quản trị, phiên bản driver và cách thực hiện rollback đều có thể ảnh hưởng đến hành vi triển khai thực tế.

### Cạm bẫy riêng của CREATE INDEX CONCURRENTLY

Nếu PostgreSQL gặp lỗi trong quá trình xây dựng index concurrently, một **index không hợp lệ** có thể còn tồn tại trong catalog. Khi ấy:

- SQL tạo index có thể không hoàn thành công việc dự kiến.
- Precondition kiểm tra tên index có thể thấy index tồn tại, dù index không sử dụng được như mong muốn.
- Một lần chạy lại có thể báo trùng tên hoặc thất bại nếu chưa dọn trạng thái còn sót.

Vì vậy sau lỗi, cần kiểm tra catalog PostgreSQL, trạng thái index hợp lệ và log triển khai. Chỉ thực hiện dọn dẹp hoặc tái tạo index sau khi biết chính xác trạng thái database. Dùng tùy chọn **IF NOT EXISTS** một cách máy móc có thể khiến một index đã tồn tại nhưng không hợp lệ bị bỏ qua.

## 6. Rủi ro khi runInTransaction: false và có nhiều lệnh

Xét changeset sau:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-004
      author: schema-team
      runInTransaction: false
      changes:
        - sql:
            sql: UPDATE customer SET status = 'ACTIVE' WHERE status IS NULL
        - sql:
            sql: INSERT INTO audit_log(event_type) VALUES ('CUSTOMER_STATUS_BACKFILL')
~~~

Giả sử UPDATE thành công, nhưng INSERT thất bại vì bảng audit_log không tồn tại. Khi runInTransaction=false:

1. UPDATE có thể đã được commit hoặc tác động đã tồn tại, tùy database và cách câu lệnh được thực thi.
2. INSERT báo lỗi; Liquibase dừng changeset và không thể mặc định hoàn tác UPDATE đã thành công.
3. Trạng thái lịch sử DATABASECHANGELOG có thể chưa ghi nhận changeset là đã hoàn tất, dù database đã bị thay đổi một phần.
4. Lần update tiếp theo có thể thử thực thi lại changeset, tạo thay đổi lặp hoặc lỗi dữ liệu.

Hệ quả là **database thực tế và lịch sử changeset có thể không khớp**. Chính Liquibase cũng cảnh báo về rủi ro không nhất quán với DATABASECHANGELOG nếu một changeset chạy ngoài transaction thất bại giữa chừng.

**Nguyên tắc mạnh:** mỗi changeset với runInTransaction=false nên có phạm vi nhỏ, lý tưởng là một câu lệnh không thể chạy trong transaction. Nếu cần nhiều thao tác độc lập, hãy xem xét tách chúng thành các changeset riêng và thiết kế khả năng chạy lại, kiểm tra trạng thái cùng quy trình khôi phục rõ ràng.

### Không dùng false chỉ để giải quyết lỗi ngẫu nhiên

Khi một changeset chạy thất bại ở chế độ true, cần tìm nguyên nhân trước: cú pháp SQL, quyền truy cập, phụ thuộc schema, deadlock, timeout, transactional DDL của DBMS hay lệnh thật sự bị cấm trong transaction. Chỉ đổi false sau khi xác định đó là yêu cầu hợp lệ của cơ sở dữ liệu. Nếu lỗi do cột chưa tồn tại hay dữ liệu không hợp lệ, tắt transaction không giải quyết được nguyên nhân và thường làm tình huống phục hồi khó hơn.

## 7. Ma trận hành vi: thuộc tính không quyết định mọi thứ

| runInTransaction | Đặc điểm SQL/DBMS | Nếu lệnh sau lỗi | Đánh giá |
|---|---|---|---|
| **true** | Mọi thao tác được database hỗ trợ trong transaction | Có thể rollback phần chưa commit của cùng changeset | Trường hợp mặc định mong muốn |
| **true** | Một DDL gây implicit commit | Có thể để lại thao tác đã áp dụng | Không có bảo đảm nguyên tử chỉ nhờ thuộc tính |
| **false** | Một câu lệnh bắt buộc chạy ngoài transaction | Nếu lệnh lỗi, kiểm tra xem có trạng thái còn sót không | Có thể cần thiết, nhưng cần kế hoạch khôi phục |
| **false** | Nhiều câu lệnh độc lập | Các câu đầu có thể đã có hiệu lực khi câu sau thất bại | Rủi ro cao, nên tách hoặc thiết kế lại |
| **true/false** | Nhiều changeset trong một changelog | Changeset đã commit trước đó không tự hoàn tác do changeset sau lỗi | Cần chiến lược rollback ở mức triển khai |

Không đánh đồng **bật transaction** với **an toàn tuyệt đối** hoặc **tắt transaction** với **nhanh hơn**. Tính an toàn phụ thuộc vào SQL thực tế, engine database và quy trình vận hành.

## 8. Ảnh hưởng của transaction đến checksum và lịch sử triển khai

Liquibase nhận diện changeset qua **id, author và đường dẫn changelog** (hoặc logicalFilePath khi cấu hình). Nó ghi nhận những changeset đã thực hiện trong **DATABASECHANGELOG** và lưu checksum để phát hiện nội dung đã chạy bị sửa.

**runInTransaction không phải công cụ “bỏ qua lịch sử”.** Sau khi một changeset đã triển khai ở môi trường dùng chung:

- Giữ nguyên id, author, đường dẫn logic và nội dung changeset đã chạy.
- Không đổi runInTransaction từ true sang false ngay trong một changeset lịch sử chỉ để thử xử lý sự cố.
- Không sửa SQL và thực hiện clear-checksums để che giấu việc đã thay đổi lịch sử.
- Nếu cần điều chỉnh schema, tạo changeset mới; nếu phải phục hồi một lỗi triển khai, kiểm tra trạng thái database và bản ghi DATABASECHANGELOG trước khi quyết định.

Có thể có chênh lệch giữa thay đổi thực tế và lịch sử do lỗi ở changeset chạy ngoài transaction. Việc xử lý đòi hỏi đối chiếu dữ liệu/schema, log và thông tin changeset; không tự chèn một dòng DATABASECHANGELOG hoặc đánh dấu MARK_RAN chỉ vì muốn pipeline đi tiếp.

### DATABASECHANGELOGLOCK có vai trò gì?

Liquibase sử dụng **DATABASECHANGELOGLOCK** để phối hợp các tiến trình migration và hạn chế việc nhiều tiến trình cùng cập nhật một database. Lock này **không** làm biến những thay đổi ngoài transaction thành một giao dịch nguyên tử. Nếu tiến trình bị ngắt, phải xác minh không còn migration đang chạy trước khi xử lý khóa mắc kẹt.

## 9. Precondition và lựa chọn onFail trong changeset ngoài transaction

Precondition giúp kiểm tra trạng thái trước khi thực thi. Ví dụ trước CREATE INDEX CONCURRENTLY cần chắc chắn bảng đã tồn tại và tên index chưa xuất hiện.

Các giá trị onFail hay gặp:

| onFail | Hành vi chính | Khi dùng với migration nhạy cảm |
|---|---|---|
| **HALT** | Dừng khi điều kiện không đạt | Thường là lựa chọn an toàn khi trạng thái database cần điều tra |
| **WARN** | Cảnh báo, tiếp tục chạy changeset | Chỉ dùng nếu vi phạm điều kiện không ảnh hưởng tính đúng |
| **CONTINUE** | Bỏ qua changeset ở lần này; không coi là đã thực thi | Hữu ích trong tình huống được thiết kế rõ, tránh lạm dụng |
| **MARK_RAN** | Ghi nhận changeset như đã chạy mà không thực thi change | Chỉ khi đã xác minh database tương đương trạng thái mong muốn |

Với CREATE INDEX CONCURRENTLY, precondition chỉ kiểm tra **indexExists** chưa đủ để chứng minh index hiện có là hợp lệ, có cấu trúc đúng, hay đã xây dựng xong. Nếu lệnh tạo index lỗi, phải điều tra catalog và trạng thái thực tế trước khi cân nhắc MARK_RAN hoặc retry.

Lưu ý: precondition chạy trước changeset **không loại bỏ hoàn toàn race condition**; giữa thời điểm kiểm tra và thời điểm SQL thực thi, hệ thống khác vẫn có thể thay đổi schema. Cần phối hợp quyền triển khai, cấu hình khóa và kế hoạch migration.

## 10. runInTransaction và rollback: hai khái niệm liên quan nhưng khác nhau

Trong Liquibase, phần **rollback** của một changeset mô tả cách **hoàn tác thay đổi đã triển khai**. Nó không bảo đảm tự động chạy bất cứ khi nào changeset lỗi nửa chừng.

Ví dụ SQL ngoài transaction:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-005
      author: schema-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            sql: CREATE INDEX CONCURRENTLY idx_orders_status ON orders (status)
      rollback:
        - sql:
            sql: DROP INDEX CONCURRENTLY IF EXISTS idx_orders_status
~~~

Nếu changeset chạy thành công và được ghi vào lịch sử, có thể dùng cơ chế rollback của Liquibase để gọi phần rollback đã khai báo, sau khi kiểm tra SQL và điều kiện database. Nếu CREATE INDEX CONCURRENTLY thất bại trước khi changeset hoàn tất, không nên mặc định rằng rollback của Liquibase sẽ tự chạy để xóa index dở dang.

Một rollback tốt cần trả lời:

1. Thao tác ngược có hợp lệ khi chạy ngoài transaction hay không?
2. Nếu một phần dữ liệu/DDL đã áp dụng, cần kiểm tra trạng thái nào trước rollback?
3. Rollback có gây mất dữ liệu hoặc ảnh hưởng khóa, index, truy vấn đang chạy không?
4. Nếu rollback không an toàn, có nên dùng changeset mới để sửa tiến về phía trước (**forward fix**) không?
5. Đã kiểm tra quy trình trên bản sao database có dữ liệu và phiên bản DBMS tương đương chưa?

Ví dụ rollback DROP COLUMN sẽ làm mất dữ liệu của cột đó, dù lệnh DROP được phép chạy trong transaction. Khả năng rollback kỹ thuật không đồng nghĩa dữ liệu kinh doanh sẽ tự phục hồi.

## 11. Thiết kế changeset theo mục tiêu giao dịch

Giả sử cần thêm cột, backfill dữ liệu và tạo index trên bảng orders rất lớn. Thay vì gộp tất cả vào một changeset, có thể chia thành các bước với mục tiêu rõ ràng.

### Bước A: thêm cột với giao dịch mặc định

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-006
      author: order-team
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: processing_state
                  type: VARCHAR(30)
      rollback:
        - dropColumn:
            tableName: orders
            columnName: processing_state
~~~

Đây là một thay đổi schema độc lập. Cần xác minh DBMS hỗ trợ transaction cho ALTER TABLE nếu muốn kỳ vọng atomic rollback ở cấp changeset.

### Bước B: backfill có kế hoạch

Backfill dữ liệu lớn có thể gây lock, tăng WAL/redo log hoặc kéo dài transaction. Tùy kích thước và nhu cầu nghiệp vụ, nhóm có thể dùng một changeset DML có transaction, nhiều đợt cập nhật nhỏ theo cơ chế đã kiểm soát, hoặc một job dữ liệu riêng có khả năng chạy lại và kiểm tra tiến độ. Không nên đặt runInTransaction=false cho một UPDATE hàng triệu dòng chỉ vì ngại transaction dài; cần thiết kế phạm vi cập nhật, batching và khả năng phục hồi trước.

Nếu chuyển backfill sang job ngoài Liquibase, phải ghi rõ ranh giới trách nhiệm: job nào cập nhật, điều kiện hoàn tất là gì và khi nào các changeset tiếp theo được phép chạy.

### Bước C: tạo index ngoài transaction khi DBMS yêu cầu

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 2026-11-19-007
      author: order-team
      dbms: postgresql
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - columnExists:
            tableName: orders
            columnName: processing_state
      changes:
        - sql:
            sql: CREATE INDEX CONCURRENTLY idx_orders_processing_state ON orders (processing_state)
      rollback:
        - sql:
            sql: DROP INDEX CONCURRENTLY IF EXISTS idx_orders_processing_state
~~~

Bước này là ví dụ chính đáng cho false. Tách riêng giúp tránh gộp tác động của DDL tạo index với backfill dữ liệu trong cùng một changeset không có tính nguyên tử.

### Phối hợp với ứng dụng đang chạy

Nếu ứng dụng còn sử dụng schema cũ, cần chú ý **expand-contract**: tạo cấu trúc mới theo hướng tương thích, triển khai ứng dụng đọc/ghi phù hợp, chuyển dữ liệu nếu cần, sau đó mới xóa cấu trúc cũ khi đã bảo đảm không còn phụ thuộc. runInTransaction không thay thế quy trình tương thích giữa phiên bản ứng dụng và schema.

## 12. Lỗi thực thi: nên điều tra theo trình tự nào?

Khi Liquibase báo lỗi ở changeset có **runInTransaction=false**, xử lý theo một trình tự có kiểm chứng:

1. **Dừng retry tự động:** tránh lặp lại DDL hoặc DML khi chưa hiểu tác động đang tồn tại.
2. **Ghi nhận changeset và môi trường:** id, author, đường dẫn, DBMS/phiên bản, thời điểm chạy, câu SQL và log lỗi.
3. **Kiểm tra tiến trình còn chạy:** đặc biệt với CREATE INDEX CONCURRENTLY có thể mất thời gian.
4. **Kiểm tra trạng thái thực tế:** bảng, cột, index, constraint, dữ liệu; với PostgreSQL có thể kiểm tra tính hợp lệ của index trong catalog.
5. **Đối chiếu DATABASECHANGELOG:** changeset đã có bản ghi EXECUTED/RERAN/MARK_RAN chưa, hay vẫn pending?
6. **Kiểm tra DATABASECHANGELOGLOCK:** chỉ xử lý khóa khi đã chắc không có migration nào đang chạy.
7. **Chọn chiến lược phục hồi:** làm sạch phần chưa hoàn chỉnh, sửa một cách tiến về phía trước, hoặc rollback có kiểm chứng; xác định rõ ảnh hưởng dữ liệu.
8. **Kiểm tra lại:** validate, status, SQL dự kiến và trạng thái database; chỉ tiếp tục pipeline khi kết quả nhất quán.

Trên PostgreSQL, một câu lệnh kiểm tra index không hợp lệ có thể dựa vào catalog như sau:

~~~sql
SELECT n.nspname AS schema_name,
       c.relname AS index_name,
       i.indisvalid,
       i.indisready
FROM pg_class AS c
JOIN pg_index AS i ON i.indexrelid = c.oid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relname = 'idx_orders_created_at';
~~~

Đây là câu truy vấn **chỉ đọc** hỗ trợ chẩn đoán. Không nên sử dụng kết quả một cột đơn lẻ để kết luận đầy đủ về tính an toàn của index; cần kết hợp tình trạng lệnh tạo index, log và truy vấn nghiệp vụ.

### Vì sao không sửa lịch sử cho “khớp”?

Một dòng DATABASECHANGELOG không chứng minh mọi thao tác ngoài transaction đã hoàn tất nếu môi trường từng gặp lỗi. Ngược lại, không có dòng lịch sử cũng không chứng minh chưa có SQL nào tác động database. Việc chèn/xóa sửa tay dữ liệu lịch sử có thể làm Liquibase bỏ qua một thay đổi cần thiết hoặc chạy trùng một thay đổi đã có hiệu lực. Muốn đồng bộ lại lịch sử phải có đánh giá và quy trình quản trị rõ ràng.

## 13. Kiểm chứng trước khi triển khai

Một quy trình kiểm chứng phù hợp cho changeset nhạy cảm:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
liquibase history
~~~

Các lệnh trên giả định thông tin kết nối và changelog đã được cấu hình. **validate** giúp kiểm tra cấu trúc changelog và những vấn đề được hỗ trợ phát hiện; **status** xác định changeset đang chờ; **update-sql** hiển thị SQL dự kiến; **update** áp dụng migration; **history** giúp xem lịch sử triển khai.

Các bước cần lưu ý:

- Đối với SQL yêu cầu chạy ngoài transaction, kiểm tra **runInTransaction: false** ngay trong changeset và review SQL sinh ra trên đúng DBMS.
- Dùng database thử nghiệm có lịch sử tương tự production để xác định SQL thực tế, độ dài chạy, lock và khả năng phục hồi.
- Tách các câu lệnh ngoài transaction thành changeset nhỏ, có chủ đích và có cách kiểm tra sau thực thi.
- Kiểm tra precondition, dbms, context, label, rollback và kế hoạch xử lý thay đổi dở dang.
- Đừng cho rằng update-sql tự chứng minh tính an toàn thời gian chạy: nó không mô phỏng lock, khối lượng dữ liệu hoặc mọi tác động khi câu lệnh thất bại.
- Duy trì một luồng triển khai migration có kiểm soát, tránh nhiều instance hoặc pipeline tự ý chạy chồng lên nhau.

## 14. Tích hợp Spring Boot và CI/CD

Spring Boot có thể tích hợp Liquibase khi ứng dụng khởi động. Ví dụ cấu hình cơ bản:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

**runInTransaction** được khai báo **trong changeset**, không phải một cờ tùy chọn ở cấu hình Spring Boot để tắt transaction cho toàn bộ changelog.

Với sản phẩm có nhiều instance hoặc nhiều môi trường, nhóm cần quyết định ai chịu trách nhiệm thực thi migration:

- **Ứng dụng khởi động chạy Liquibase:** cấu hình Liquibase nhất quán và bảo đảm triển khai có kiểm soát.
- **Pipeline CI/CD chạy Liquibase:** đưa validate và SQL review vào pipeline; chỉ một bước triển khai được quyền chạy update trên database đích tại một thời điểm.
- **Tách job migration riêng:** có thể phù hợp khi DDL nhạy cảm cần giám sát hoặc thời gian chạy dài; phải quản lý credential, theo dõi tiến trình và quy trình phục hồi.

Trong mọi phương án, việc đặt runInTransaction=false cho một changeset không thay thế khả năng điều phối nhiều instance. DATABASECHANGELOGLOCK hỗ trợ khóa triển khai của Liquibase, còn quy trình vận hành vẫn phải quản lý version ứng dụng và các thay đổi có rủi ro.

### Checklist review một changeset có runInTransaction=false

| Câu hỏi review | Lý do |
|---|---|
| DBMS có thực sự cấm câu lệnh này chạy trong transaction không? | Tránh tắt transaction khi không cần |
| Changeset có đúng một thao tác chính không? | Giảm phạm vi thay đổi dở dang |
| SQL có tạo trạng thái trung gian hoặc đối tượng không hợp lệ không? | Chuẩn bị cách chẩn đoán và khôi phục |
| Có precondition đủ chặt và dbms phù hợp không? | Tránh chạy trên schema hoặc DBMS sai |
| Đã xem SQL dự kiến và thử trên DBMS/phiên bản mục tiêu chưa? | Giảm khác biệt môi trường |
| Có rollback hoặc forward fix đã được kiểm chứng không? | Chủ động xử lý sự cố |
| Đã kiểm tra tải, lock và cửa sổ triển khai chưa? | Hạn chế ảnh hưởng ứng dụng |
| Có kế hoạch đối chiếu DATABASECHANGELOG nếu lệnh lỗi không? | Bảo đảm lịch sử phù hợp trạng thái thực |

## 15. Tình huống thực hành

### Tình huống A: CREATE INDEX CONCURRENTLY trên PostgreSQL

Một bảng orders có nhiều giao dịch ghi. Nhóm cần tạo index trên cột created_at mà hạn chế khóa ghi. Hãy tạo changeset PostgreSQL với một câu CREATE INDEX CONCURRENTLY, runInTransaction=false, precondition kiểm tra bảng và tên index, rollback DROP INDEX CONCURRENTLY. Trước triển khai production, hãy kiểm tra SQL, thử trên cơ sở dữ liệu có dữ liệu đáng kể và mô phỏng lỗi để xác định cách nhận diện index không hợp lệ.

**Điểm cốt lõi:** false có lý do kỹ thuật rõ ràng; tách riêng thao tác; có quy trình khôi phục ngoài transaction.

### Tình huống B: thêm hai cột trên PostgreSQL

Một changeset dùng hai addColumn liên tiếp. Database hỗ trợ transactional DDL cho các lệnh tương ứng. Có nên đổi runInTransaction=false để “giảm nguy cơ lock” không?

**Gợi ý:** không. Đặt true hoặc dùng mặc định giúp rollback phần chưa commit khi lỗi. Nếu lock quá dài, cần phân tích SQL và chiến lược triển khai, không mặc định tắt transaction. Việc tạo hai cột trong cùng changeset hay tách thành hai changeset là quyết định phụ thuộc cách kiểm chứng và mức độ liên quan của chúng.

### Tình huống C: DDL MySQL lỗi sau khi câu đầu thành công

Một changeset có runInTransaction=true thực hiện hai ALTER TABLE, nhưng ALTER thứ hai lỗi. Có được khẳng định ALTER thứ nhất đã rollback không?

**Gợi ý:** không. Phải kiểm tra hành vi implicit commit của phiên bản MySQL và loại ALTER, sau đó xác minh schema thực tế và DATABASECHANGELOG. Giá trị true chỉ mô tả cách Liquibase cố gắng tổ chức transaction.

### Tình huống D: changeset ngoài transaction đã sửa dữ liệu nhưng không có lịch sử

Một changeset runInTransaction=false có UPDATE rồi INSERT. UPDATE đã có hiệu lực, INSERT lỗi. Nhóm tính sửa status thành MARK_RAN cho qua bước triển khai.

**Gợi ý:** đây là hành động có rủi ro che giấu dữ liệu chưa hoàn chỉnh. Cần xác định trạng thái sau UPDATE, các điều kiện chưa thỏa, tác động nếu chạy lại và phương án sửa/hoàn tác. Chỉ đưa lịch sử về trạng thái phù hợp sau khi xác minh đầy đủ và có quyết định quản trị.

## 16. Tổng kết

**runInTransaction: true** là mặc định và phù hợp với phần lớn changeset; nó yêu cầu Liquibase quản lý transaction ở cấp changeset khi database hỗ trợ. **runInTransaction: false** chỉ nên dùng khi có yêu cầu kỹ thuật hoặc lý do vận hành rõ, điển hình là một số SQL như PostgreSQL CREATE INDEX CONCURRENTLY cần chạy ngoài transaction.

Không có thuộc tính nào bảo đảm atomicity vượt quá khả năng của DBMS. Không có transaction bao trọn toàn bộ changelog chỉ nhờ thiết lập ở từng changeset. Khi một thay đổi chạy ngoài transaction lỗi, có thể tồn tại trạng thái schema hoặc dữ liệu đã áp dụng một phần và không khớp với DATABASECHANGELOG.

Bài học quan trọng trong quản lý migration bằng Liquibase là **kiểm soát ranh giới thay đổi**: viết changeset nhỏ, chọn transaction theo khả năng SQL và DBMS, kiểm chứng SQL, thiết kế rollback hoặc forward fix, quản lý lịch sử triển khai và theo dõi thực tế trên mỗi môi trường.
