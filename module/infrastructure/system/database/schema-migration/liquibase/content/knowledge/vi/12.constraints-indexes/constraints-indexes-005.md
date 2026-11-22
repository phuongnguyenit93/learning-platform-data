# Thêm hoặc gỡ ràng buộc NOT NULL

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Khóa và chỉ mục**, ràng buộc **NOT NULL** bảo đảm một cột không được lưu giá trị SQL **NULL**. Đây là quy tắc toàn vẹn dữ liệu quan trọng, nhưng việc bật hoặc gỡ quy tắc trên bảng đã có dữ liệu phải được thiết kế như một **migration có kiểm chứng**: kiểm tra hàng cũ, phối hợp những luồng ghi mới, xem xét khóa bảng, lựa chọn thời điểm triển khai và chuẩn bị rollback.

Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai trong **DATABASECHANGELOG**. Với cột đã tồn tại, hai change type trực tiếp là **addNotNullConstraint** và **dropNotNullConstraint**. Bài này giải thích chúng khác với thuộc tính **nullable** lúc tạo cột ra sao, khi nào dùng, các bước xử lý dữ liệu hiện có và cách áp dụng trên nhiều môi trường, kể cả khi tích hợp Spring Boot hoặc CI/CD.

Sau bài học, người học có thể: giải thích chính xác NOT NULL kiểm soát điều gì; viết changeset YAML để thêm/gỡ ràng buộc; phát hiện dữ liệu NULL trước khi thay đổi; tổ chức migration theo mô hình expand–backfill–contract; xây dựng rollback đúng trạng thái; và kiểm chứng cả schema lẫn hành vi ghi dữ liệu.

## 1. NOT NULL bảo vệ điều gì?

Giá trị **NULL** trong SQL thường thể hiện một giá trị chưa biết, chưa có hoặc không áp dụng. Nó **khác** chuỗi rỗng, số 0, false và một chuỗi mang chữ "NULL".

Ví dụ một bảng có dữ liệu:

| customer_id | contact_channel | Ý nghĩa |
|---|---|---|
| 101 | EMAIL | Kênh liên hệ đã biết |
| 102 | SMS | Kênh liên hệ đã biết |
| 103 | NULL | Chưa được xác định |
| 104 | *(chuỗi rỗng)* | Có giá trị chuỗi rỗng, không phải NULL trên đa số DBMS |

Khi đặt **contact_channel NOT NULL**, database phải từ chối thao tác ghi tạo ra giá trị SQL NULL ở cột này. Quy tắc được thực thi tại database, nên nó bảo vệ cả những luồng ghi không đi qua validation của ứng dụng, ví dụ JDBC, batch job hoặc SQL trực tiếp.

**NOT NULL không tự bảo đảm giá trị hợp lệ về nghiệp vụ**. Một cột VARCHAR có NOT NULL thường vẫn có thể chứa chuỗi rỗng hoặc chuỗi không thuộc tập giá trị cho phép. Nếu yêu cầu là chỉ chấp nhận EMAIL hoặc SMS, có thể cần thêm **CHECK constraint**, bảng tra cứu hoặc kiểm tra nghiệp vụ phù hợp. Tương tự, NOT NULL không bảo đảm giá trị **unique** và không tạo chỉ mục.

Một số DBMS có cách diễn giải đặc biệt. Ví dụ Oracle thường xem chuỗi rỗng là NULL đối với các kiểu chuỗi liên quan. Vì thế, nếu hành vi chuỗi rỗng quan trọng, phải kiểm thử trên đúng DBMS và phiên bản đang sử dụng.

## 2. Phân biệt NOT NULL, giá trị mặc định và thuộc tính nullable

Ba khái niệm thường bị nhầm lẫn:

| Khái niệm | Mục đích | Ảnh hưởng chính |
|---|---|---|
| **NOT NULL** | Cấm lưu NULL vào cột | INSERT/UPDATE vi phạm sẽ thất bại |
| **DEFAULT** | Cung cấp giá trị khi thao tác ghi không chỉ định cột theo quy tắc DBMS | Có thể tự cấp giá trị cho INSERT mới |
| **nullable: false** trong khai báo cột Liquibase | Khai báo ràng buộc NOT NULL khi tạo hoặc thêm cột | Trở thành đặc tính của schema sau khi migration được áp dụng |

Ví dụ khi **tạo bảng mới**, có thể khai báo nullable ở định nghĩa cột:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer-profile"
      author: "platform"
      changes:
        - createTable:
            tableName: customer_profile
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: contact_channel
                  type: VARCHAR(20)
                  constraints:
                    nullable: false
~~~

Đây là cách chỉ định NOT NULL ngay từ khi bảng được tạo; dữ liệu lịch sử chưa phát sinh nên bài toán backfill chưa xuất hiện.

Với **cột đã tồn tại** và đang cho phép NULL, thay đổi ràng buộc được thể hiện bằng **addNotNullConstraint**. Để cho phép NULL trở lại, dùng **dropNotNullConstraint**. Hai thao tác này thay đổi schema, chứ không tự mang nghĩa “sửa hết dữ liệu cũ”.

Đặc biệt, **DEFAULT không thay thế được NOT NULL**. Một cột có DEFAULT 'EMAIL' vẫn có thể nhận NULL nếu cột cho phép NULL và ứng dụng truyền NULL tường minh. Một cột NOT NULL nhưng không có DEFAULT lại yêu cầu bên ghi cung cấp một giá trị hợp lệ khi database không có cơ chế tạo giá trị thay thế.

## 3. Trước khi thêm NOT NULL: xác minh trạng thái dữ liệu

Giả sử bảng **customer** đã tồn tại với cột **contact_channel VARCHAR(20)** đang nullable. Nhóm muốn bảo đảm tất cả khách hàng có kênh liên hệ.

Trước hết cần kiểm tra dữ liệu NULL hiện có:

~~~sql
SELECT COUNT(*) AS null_count
FROM customer
WHERE contact_channel IS NULL;
~~~

Nếu kết quả lớn hơn 0, việc bật NOT NULL sẽ gặp rào cản dữ liệu: database không thể xác nhận mọi hàng đang tuân thủ quy tắc mới. Trong vận hành, không được chỉ thêm ràng buộc rồi kỳ vọng Liquibase tự hiểu khách hàng có NULL phải nhận giá trị nào.

Cần trả lời:

1. **NULL hiện tại có nghĩa gì?** Chưa biết, chưa thu thập hay không áp dụng?
2. **Có giá trị thay thế đúng nghiệp vụ không?** Không nên gán EMAIL mặc định cho mọi khách hàng chỉ để đủ điều kiện NOT NULL nếu đó không phản ánh dữ liệu thật.
3. **Có hệ thống nào còn ghi NULL không?** REST API, message consumer, import dữ liệu, batch job hoặc phiên bản ứng dụng cũ?
4. **Kích thước bảng và tần suất ghi ra sao?** Một UPDATE toàn bảng và ALTER COLUMN có thể tạo tải đáng kể.
5. **Nếu cần rollback, có khôi phục được dữ liệu gốc không?** Thay NULL bằng một giá trị giả có thể làm mất thông tin về trạng thái ban đầu.

Nếu nghiệp vụ cho phép lưu **UNKNOWN** để biểu diễn chưa xác định, đó là một quy tắc dữ liệu khác với SQL NULL, cần được thống nhất và tài liệu hóa. Nếu không có giá trị hợp lệ, có thể phải giữ cột nullable hoặc thay thiết kế dữ liệu thay vì cưỡng ép NOT NULL.

## 4. Thêm NOT NULL bằng addNotNullConstraint

Khi đã xác nhận cột tồn tại, dữ liệu không còn NULL và các luồng ghi đã tương thích, có thể viết changeset sau:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-customer-contact-channel-not-null"
      author: "platform"
      preConditions:
        - onFail: HALT
        - columnExists:
            tableName: customer
            columnName: contact_channel
        - sqlCheck:
            expectedResult: "0"
            sql: SELECT COUNT(*) FROM customer WHERE contact_channel IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer
            columnName: contact_channel
            columnDataType: VARCHAR(20)
      rollback:
        - dropNotNullConstraint:
            tableName: customer
            columnName: contact_channel
            columnDataType: VARCHAR(20)
~~~

**Giải thích từng phần:**

- **tableName** và **columnName** chỉ rõ cột cần ràng buộc; nếu dùng nhiều schema, cần xác định **schemaName** thích hợp.
- **columnDataType** mô tả kiểu cột hiện tại để Liquibase có đủ thông tin sinh DDL khi DBMS yêu cầu. Giá trị phải khớp schema thực tế, tránh vô tình thay đổi kiểu dữ liệu.
- **columnExists** phát hiện tình huống migration thiếu phụ thuộc hoặc trỏ nhầm database/schema.
- **sqlCheck** yêu cầu số dòng NULL bằng 0; **onFail: HALT** dừng khi dữ liệu chưa sẵn sàng.
- **rollback** gỡ NOT NULL, trở về trạng thái cột nullable trước khi migration (giả định cột ban đầu đúng là nullable).

**Precondition không thay thế ràng buộc database.** Nếu ứng dụng còn ghi liên tục, một bản ghi NULL có thể xuất hiện sau thời điểm sqlCheck đếm và trước khi ALTER thực thi. Khi đó câu lệnh ALTER phải tiếp tục tự bảo vệ tính toàn vẹn và có thể thất bại. Cần ngăn nguồn ghi NULL bằng kế hoạch triển khai ứng dụng và chọn thời điểm thay đổi phù hợp. Không thể coi phép đếm trước migration là bảo đảm an toàn tuyệt đối.

### SQL được sinh ra phụ thuộc DBMS

Trên PostgreSQL, ý định trên thường tương đương:

~~~sql
ALTER TABLE customer
ALTER COLUMN contact_channel SET NOT NULL;
~~~

Trên những DBMS khác, thao tác có thể dùng **MODIFY COLUMN**, **ALTER COLUMN** kèm kiểu dữ liệu hoặc câu lệnh DDL riêng. Vì thế, YAML Liquibase giúp mô tả mục tiêu một cách thống nhất, nhưng **không bảo đảm mọi hệ quản trị sẽ sinh hoặc thực thi cùng một lệnh SQL**.

## 5. Gỡ NOT NULL bằng dropNotNullConstraint

Giả sử từ một phiên bản mới, **contact_channel** trở thành thông tin tùy chọn. Nhóm muốn chấp nhận khách hàng chưa khai báo kênh liên hệ.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-011-customer-contact-channel-nullable"
      author: "platform"
      changes:
        - dropNotNullConstraint:
            tableName: customer
            columnName: contact_channel
            columnDataType: VARCHAR(20)
      rollback:
        - addNotNullConstraint:
            tableName: customer
            columnName: contact_channel
            columnDataType: VARCHAR(20)
~~~

Sau khi áp dụng:

- Database có thể nhận NULL cho cột theo quy tắc của DBMS, nếu không còn constraint khác ngăn cản.
- Những giá trị không NULL đã lưu **không tự bị xóa**.
- Không có thay đổi mặc định cho cột trừ khi một migration khác xử lý DEFAULT.
- Ứng dụng và hợp đồng API cần chấp nhận khả năng nhận giá trị null khi đọc dữ liệu, nếu luồng ghi mới bắt đầu lưu NULL.

Ví dụ SQL tương đương trên PostgreSQL:

~~~sql
ALTER TABLE customer
ALTER COLUMN contact_channel DROP NOT NULL;
~~~

**Điểm nguy hiểm ở rollback:** Khi đã gỡ NOT NULL, các bản ghi mới có thể được lưu với contact_channel NULL. Nếu rollback changeset bằng cách thêm NOT NULL trở lại, lệnh rollback sẽ **thất bại** chừng nào còn bản ghi NULL. Do đó rollback được khai báo trong YAML không đồng nghĩa với khả năng hoàn tác luôn bảo đảm thành công: trước khi rollback phải kiểm tra và xử lý dữ liệu phát sinh trong thời gian cột nullable.

Với ứng dụng đang chạy, cần xem lại sự tương thích ngược trước khi gỡ constraint. Một code path cũ có thể giả định field không bao giờ null và gây lỗi xử lý nếu dữ liệu mới chứa NULL. Thứ tự phát hành ứng dụng/schema nên dựa trên hợp đồng dữ liệu thực tế.

## 6. Kịch bản thêm NOT NULL theo từng giai đoạn

Với bảng đã có dữ liệu, phương pháp an toàn thường là **expand → cập nhật luồng ghi → backfill → contract**. Một mục tiêu nghiệp vụ như “mọi customer phải có contact_channel” có thể được chia thành nhiều changeset hoặc nhiều đợt triển khai có kiểm chứng.

### Giai đoạn A — Expand: thêm cột nullable

Nếu cột chưa tồn tại, bắt đầu bằng thay đổi tương thích với ứng dụng cũ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-020-customer-channel-expand"
      author: "platform"
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: contact_channel
                  type: VARCHAR(20)
~~~

Cột mới cho phép NULL trong giai đoạn chuyển tiếp. Sau khi chạy, cần kiểm tra schema thật sự có cột và loại dữ liệu phù hợp. Nếu cột vốn đã tồn tại, **không thêm lại** mà bắt đầu từ bước rà soát dữ liệu.

### Giai đoạn B — Cập nhật mọi luồng ghi

Phiên bản ứng dụng mới cần ghi contact_channel hợp lệ khi tạo hoặc cập nhật customer. Các nguồn ghi ngoài ứng dụng cũng cần được xem xét:

- API hoặc batch import có gửi contact_channel không?
- Consumer xử lý message cũ có ghi NULL không?
- ORM có tự điền giá trị hợp lệ hay vẫn tạo INSERT với NULL tường minh?
- Những phiên bản ứng dụng cũ còn đang hoạt động trong rolling deployment không?
- Giá trị fallback có đúng nghiệp vụ, hay cần chặn thao tác tạo mới nếu thiếu thông tin?

Trong quá trình rollout, thường phải giữ cột nullable cho đến khi **mọi nguồn ghi** không còn tạo giá trị NULL, hoặc có một chiến lược tương thích khác được kiểm chứng. Chỉ kiểm tra một instance Spring Boot mới không đủ nếu vẫn còn instance cũ chạy song song.

### Giai đoạn C — Backfill các bản ghi cũ

Nếu nghiệp vụ cho phép chuyển giá trị NULL sang một giá trị rõ nghĩa như **UNKNOWN**, có thể dùng changeset dữ liệu:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-021-customer-channel-backfill"
      author: "platform"
      changes:
        - update:
            tableName: customer
            columns:
              - column:
                  name: contact_channel
                  value: UNKNOWN
            where: contact_channel IS NULL
~~~

**UNKNOWN phải là giá trị được nghiệp vụ chấp nhận**, không chỉ là cách vượt qua validation của database. Với bảng lớn, câu UPDATE trên toàn bộ các dòng NULL có thể tạo transaction dài, chiếm khóa, tăng WAL/redo log, gây áp lực replication và ảnh hưởng hiệu năng. Có thể cần chia thành lô theo khóa chính hoặc chạy job backfill riêng với cơ chế checkpoint, giám sát và kiểm chứng số dòng còn thiếu.

Nếu backfill do một job bên ngoài Liquibase thực hiện, pipeline phải có bằng chứng job đã hoàn tất trước khi triển khai ràng buộc. **Sự tồn tại của changeset backfill không tự chứng minh dữ liệu đã hợp lệ** nếu backfill cần xử lý bất đồng bộ, có lỗi một phần hoặc vẫn còn nguồn ghi NULL.

### Giai đoạn D — Contract: thêm NOT NULL

Sau khi tất cả nguồn ghi đã tuân thủ và dữ liệu cũ được giải quyết, chạy changeset **addNotNullConstraint** như mục 4, với precondition COUNT(*) = 0. Một số hệ thống còn cần quan sát một khoảng thời gian để xác nhận số dòng NULL không tăng trở lại.

Lưu ý: **tách thành nhiều changeset trong một changelog không tự tạo khoảng thời gian giữa các giai đoạn**. Nếu tất cả nằm trong một artifact và cùng được phép chạy bởi lệnh update, Liquibase có thể thực thi liên tiếp. Cần thiết kế điểm dừng bằng chiến lược release, labels/contexts, phạm vi changelog hoặc migration job có kiểm soát, tránh chạy contract trước khi application rollout và backfill đã thực sự hoàn thành.

## 7. addNotNullConstraint với defaultNullValue: dùng khi nào?

Liquibase cung cấp thuộc tính **defaultNullValue** cho **addNotNullConstraint** ở những phiên bản và DBMS có hỗ trợ. Thuộc tính này có ý nghĩa **chuyển các giá trị NULL đang tồn tại sang một giá trị xác định trước khi áp NOT NULL**; nó **khác** việc cấu hình DEFAULT của cột cho INSERT trong tương lai.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-030-task-priority-not-null"
      author: "platform"
      changes:
        - addNotNullConstraint:
            tableName: task
            columnName: priority
            columnDataType: INTEGER
            defaultNullValue: "0"
      rollback:
        - dropNotNullConstraint:
            tableName: task
            columnName: priority
            columnDataType: INTEGER
~~~

Trên một cột priority kiểu INTEGER, ví dụ này có ý định gán **0** cho những dòng đang NULL trước khi thiết lập NOT NULL. Cần xác minh **0** là giá trị hợp lệ theo nghiệp vụ và kiểm tra SQL thực tế mà phiên bản Liquibase/DBMS tạo ra.

**Không đánh đồng defaultNullValue với defaultValue hoặc addDefaultValue:**

| Cơ chế | Dữ liệu NULL cũ | INSERT mới bỏ qua cột |
|---|---|---|
| **defaultNullValue** khi addNotNullConstraint | Có thể được cập nhật thành giá trị chỉ định trong migration | Không tự thiết lập DEFAULT lâu dài của cột |
| **addDefaultValue** | Thông thường không thay đổi dữ liệu đã lưu | Có thể nhận default khi INSERT phù hợp |
| **addNotNullConstraint** không có defaultNullValue | Không tự sửa NULL cũ; sẽ không áp dụng được nếu dữ liệu vi phạm | Cấm lưu NULL, nhưng không tự sinh giá trị thay thế |

Với tập dữ liệu lớn hoặc yêu cầu lưu vết nguồn gốc giá trị, nên cân nhắc tách backfill khỏi thay đổi constraint để dễ kiểm soát thời gian chạy và rollback. Thuộc tính defaultNullValue giúp biểu đạt một số kịch bản nhỏ/gọn nhưng không tự giải quyết bài toán hiệu năng, nghiệp vụ hay phục hồi dữ liệu ban đầu.

Nếu backfill đã thay NULL bằng 0, rollback chỉ **gỡ NOT NULL** không khôi phục các NULL cũ; muốn hoàn tác dữ liệu chính xác cần nguồn dữ liệu gốc hoặc cách xác định đúng các hàng đã đổi. Việc sửa mọi giá trị 0 thành NULL sẽ sai nếu trước đó đã có các bản ghi priority=0 hợp lệ.

## 8. Kiểm tra lỗi và điều kiện trước khi áp constraint

Một thay đổi NOT NULL có thể không thành công dù YAML đúng cú pháp. Cần phân biệt các nguyên nhân:

| Hiện tượng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Precondition COUNT(*) khác 0 | Dữ liệu cũ còn NULL | Kiểm tra số dòng, nghiệp vụ backfill và luồng ghi |
| columnExists thất bại | Changelog thiếu phụ thuộc, sai schema/bảng/cột | Xác nhận thứ tự migration, schemaName và kết nối |
| ALTER COLUMN thất bại với lỗi NULL | Có NULL phát sinh giữa kiểm tra và ALTER hoặc kiểm tra sai phạm vi | Dừng luồng ghi vi phạm, truy vấn lại dữ liệu và kiểm tra transaction |
| DDL không được DBMS hỗ trợ theo cách mong đợi | Khác biệt phiên bản DBMS/Liquibase | Xem update-sql và ma trận hỗ trợ |
| SQL báo sai kiểu cột | columnDataType không khớp hoặc DBMS cần định nghĩa đầy đủ | So sánh catalog và SQL sinh ra |
| ALTER bị chặn quá lâu | Khóa bảng, transaction đang mở hoặc validation tốn tài nguyên | Theo dõi lock, truy vấn đang chạy, kế hoạch thời gian |
| Gỡ NOT NULL nhưng INSERT vẫn bị từ chối | Còn CHECK constraint, trigger, quyền/validation khác hoặc ứng dụng chặn | Xem schema, trigger, log và SQL thực tế |
| Rollback của drop NOT NULL thất bại | Trong thời gian nullable đã phát sinh dòng NULL | Kiểm tra và sửa dữ liệu theo phương án đã phê duyệt |

**Precondition nên phản ánh điều kiện thực tế**, thay vì trở thành mẹo bỏ qua một migration đang lỗi. Ví dụ, sử dụng **onFail: MARK_RAN** khi còn dữ liệu NULL có thể ghi nhận changeset như đã xử lý mà constraint thực tế chưa tồn tại. Nếu kết quả bắt buộc là có NOT NULL, **onFail: HALT** thường phù hợp hơn để tránh lịch sử sai khác schema.

Nếu database đã có NOT NULL từ trước, cần phân tích nguyên nhân và thống nhất cách đồng bộ lịch sử. Không sửa dòng **DATABASECHANGELOG** trực tiếp để đánh lừa Liquibase.

## 9. Rollback: gỡ ràng buộc và khôi phục ràng buộc là hai rủi ro khác nhau

Rollback của thao tác **thêm NOT NULL** thường là **dropNotNullConstraint**. Việc gỡ một ràng buộc để trở về nullable tương đối rõ về mặt schema, nhưng ứng dụng có thể đã thay đổi để dựa vào thuộc tính NOT NULL; phải xem lại sự tương thích ở tầng ứng dụng.

Rollback của thao tác **gỡ NOT NULL** thường là **addNotNullConstraint**, nhưng có rủi ro lớn hơn: sau khi cột được cho phép NULL, dữ liệu mới có thể đã chứa NULL. Một câu lệnh rollback có khai báo hợp lệ vẫn có thể không chạy được vì dữ liệu không đáp ứng điều kiện.

Bảng định hướng:

| Migration xuôi | Trạng thái trước | Rollback có ý nghĩa | Điều cần kiểm chứng |
|---|---|---|---|
| Thêm NOT NULL | Cột nullable, dữ liệu không NULL | Gỡ NOT NULL | Ứng dụng sau rollback có chấp nhận NULL không |
| Gỡ NOT NULL | Cột NOT NULL | Thêm NOT NULL trở lại | Có NULL mới xuất hiện trong khoảng thời gian nullable không |
| Backfill NULL → UNKNOWN | Có hàng NULL cũ | Phục hồi dữ liệu gốc từ nguồn tin cậy | Không thể đảo mọi UNKNOWN thành NULL một cách mù quáng |
| Thêm cột nullable rồi siết NOT NULL | Cột chưa tồn tại | Tùy giai đoạn: bỏ constraint, xử lý dữ liệu, có thể xóa cột | Xóa cột có thể làm mất dữ liệu phát sinh |

**Rollback một changeset không đồng nghĩa toàn bộ release được đảo về trạng thái trước đó.** Nếu hệ thống đã triển khai nhiều changeset kế tiếp, database có thể tiếp tục chịu các ràng buộc hoặc dữ liệu phát sinh do những bước sau. Kế hoạch phục hồi cần tính đến thứ tự ngược, phụ thuộc, phiên bản ứng dụng và thời điểm có thể chấp nhận gián đoạn.

Tốt nhất nên kiểm thử rollback trên một database đại diện đã có dữ liệu được tạo cả trước và sau migration. Không chạy rollback thử trên production chỉ để chứng minh syntax.

## 10. DBMS khác nhau sẽ triển khai NOT NULL khác nhau

Liquibase cố gắng sinh SQL phù hợp với database, nhưng khác biệt DDL, lock và giới hạn version vẫn là trách nhiệm thiết kế migration.

| DBMS | Dạng SQL hoặc đặc điểm thường gặp | Rủi ro cần xem xét |
|---|---|---|
| **PostgreSQL** | ALTER TABLE ... ALTER COLUMN ... SET NOT NULL / DROP NOT NULL | Có thể cần kiểm tra bảng, lấy khóa DDL; thời gian và cơ chế phụ thuộc phiên bản/cấu trúc |
| **MySQL/MariaDB** | Thường dùng MODIFY/CHANGE COLUMN với định nghĩa kiểu và nullability | Có thể rebuild bảng hoặc dùng thuật toán DDL khác nhau theo version/engine |
| **Microsoft SQL Server** | ALTER TABLE ... ALTER COLUMN <kiểu> NOT NULL/NULL | Cần mô tả đủ kiểu; có thể gặp phụ thuộc, khóa schema và giới hạn hiện hành |
| **Oracle** | MODIFY cột theo cú pháp NULL/NOT NULL, có cơ chế validate/novalidate trong một số bối cảnh | DDL/transaction và validation không giống PostgreSQL; kiểm tra exact behavior |
| **SQLite hoặc DBMS đặc thù** | Có thể không hỗ trợ đổi nullability trực tiếp bằng ALTER đơn giản | Có thể cần tạo lại bảng hoặc giải pháp Liquibase/DBMS riêng |

Ví dụ trong bảng là **định hướng kỹ thuật**, không phải cam kết cú pháp áp dụng cho mọi phiên bản. Một câu SQL được sinh thành công bằng **update-sql** chưa bảo đảm sẽ thực thi nhanh hoặc không gây khóa.

Đặc biệt với bảng lớn:

- Việc xác minh mọi hàng khác NULL có thể cần quét bảng hoặc sử dụng cơ chế tối ưu riêng của DBMS.
- Lệnh ALTER có thể lấy lock ảnh hưởng SELECT/INSERT/UPDATE tùy loại lock và DBMS.
- Transaction dài ở ứng dụng có thể làm thời gian chờ DDL tăng đáng kể.
- Khi DBMS không hỗ trợ rollback DDL theo transaction, thay đổi một phần hoặc lỗi khi ALTER cần được điều tra và phục hồi cụ thể.
- Có thể cần maintenance window hoặc một quy trình online schema change chuyên dụng nếu bảng rất lớn và yêu cầu sẵn sàng cao.

Không nên thêm tùy chọn DDL đặc thù DBMS vào changelog theo suy đoán. Nếu cần thao tác riêng bằng SQL hoặc extension, hãy ghi rõ phiên bản hỗ trợ, dbms, yêu cầu transaction và phương án rollback tương ứng.

## 11. Quan sát thực tế: schema đúng và dữ liệu đúng

Sau khi bật NOT NULL, cần có ít nhất **hai bằng chứng độc lập**: metadata schema xác nhận cột là non-nullable, và luồng ghi thực sự không tạo được dữ liệu NULL.

### Truy vấn dữ liệu

~~~sql
SELECT COUNT(*) AS null_count
FROM customer
WHERE contact_channel IS NULL;
~~~

Kỳ vọng **0**. Truy vấn này chỉ cho biết dữ liệu ở thời điểm đọc; nếu chưa có NOT NULL, NULL vẫn có thể xuất hiện sau đó do các writer chạy đồng thời.

### Truy vấn metadata ví dụ cho PostgreSQL

~~~sql
SELECT column_name, is_nullable, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customer'
  AND column_name = 'contact_channel';
~~~

Khi NOT NULL được áp dụng, **is_nullable** thường cho biết cột không cho phép NULL. SQL và cách hiển thị metadata trên DBMS khác có thể khác; nên dùng catalog đúng của database đích.

### Thử hành vi INSERT hoặc UPDATE

Trong **database thử nghiệm**, tạo tình huống ghi NULL vào cột:

~~~sql
INSERT INTO customer (id, contact_channel)
VALUES (900001, NULL);
~~~

Nếu các cột bắt buộc khác đã được cung cấp và NOT NULL của contact_channel đang có hiệu lực, database phải từ chối thao tác. Nếu thử trên bảng có trigger, default, constraint khác hoặc nhiều cột bắt buộc, hãy thiết kế fixture hợp lệ để biết chính xác constraint nào gây lỗi.

Trong môi trường có traffic thật, không chèn dữ liệu thử trực tiếp vào production để kiểm chứng. Ưu tiên database đại diện, kết quả DDL và monitoring.

## 12. Kiểm chứng bằng Liquibase CLI

Các lệnh cơ bản có thể dùng khi chuẩn bị migration:

~~~bash
liquibase --version
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

- **--version** xác nhận binary Liquibase thực sự chạy.
- **validate** kiểm tra cấu trúc changelog và các quy tắc validation mà engine hỗ trợ.
- **status --verbose** giúp xem changeset còn chờ triển khai.
- **update-sql** cho thấy SQL dự kiến sinh cho DBMS đang kết nối, bao gồm dạng ALTER và thông tin kiểu cột.

Sau khi review và thử trên database đại diện, có thể chạy:

~~~bash
liquibase update
~~~

Cần cấu hình đúng URL, credential, schema, changelog, context và label. Không đưa mật khẩu vào nội dung changelog hoặc log phát hành. Sau update, kiểm tra **DATABASECHANGELOG**, metadata cột và dữ liệu/null_count.

Lưu ý:

- Validate thành công không chứng minh dữ liệu hiện có thỏa NOT NULL.
- update-sql hiển thị kế hoạch SQL, không đảm bảo thời gian lock khi thực thi trên bảng thật.
- Nếu precondition không đạt, update có thể dừng trước khi DDL chạy; đây là cơ chế bảo vệ cần theo dõi trong log.
- Cần thử cả database **mới hoàn toàn** lẫn database **nâng cấp từ phiên bản cũ**. Đường xây mới có thể không có hàng NULL, trong khi production có lịch sử dữ liệu vi phạm.
- Nếu cần kiểm chứng rollback, hãy dùng lệnh rollback/rollback-sql phù hợp phiên bản và **database thử nghiệm**, đồng thời kiểm tra trạng thái sau hoàn tác.

## 13. Tích hợp Spring Boot và CI/CD

Spring Boot có thể khởi chạy Liquibase khi ứng dụng bắt đầu, ví dụ:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Nếu changeset **addNotNullConstraint** thất bại vì còn hàng NULL hoặc DBMS không cho phép ALTER ở trạng thái hiện tại, quá trình cập nhật schema có thể lỗi và khiến ứng dụng không khởi động như mong đợi. Bởi vậy, migration NOT NULL cần được điều phối như một phần của release ứng dụng, không chỉ là một file YAML được merge.

Một trình tự triển khai an toàn:

1. **Xác nhận schema và dữ liệu hiện hành**: loại cột, số hàng NULL, tổng số hàng, tốc độ ghi và database/version.
2. **Thống nhất quy tắc nghiệp vụ**: giá trị nào thực sự bắt buộc; có chấp nhận fallback UNKNOWN không.
3. **Cập nhật ứng dụng và các writer** để ngừng tạo NULL, kể cả trong thời gian rolling deployment.
4. **Backfill dữ liệu cũ** theo cách phù hợp quy mô; lưu kết quả và điều kiện hoàn thành.
5. **Chạy validate và update-sql** bằng đúng phiên bản Liquibase/DBMS của môi trường phát hành.
6. **Áp NOT NULL** bằng changeset đã kiểm tra với precondition, theo thứ tự phát hành được kiểm soát.
7. **Xác minh metadata và dữ liệu sau update**, đồng thời theo dõi lỗi ghi, lock, latency và replication.
8. **Ghi nhận artifact, commit, Liquibase version và kết quả** để có thể truy nguyên khi cần rollback hoặc sửa chữa.

Với hệ thống nhiều instance, cơ chế khóa migration của Liquibase có thể giúp điều phối các tiến trình cùng cập nhật, nhưng **không tự làm thay đổi mới tương thích với các instance ứng dụng cũ**. Đặc biệt trong rolling deployment, một instance cũ vẫn ghi NULL có thể gặp lỗi sau khi NOT NULL được bật. Có thể dùng migration job riêng trong CI/CD để tạo một điểm kiểm soát trước khi triển khai ứng dụng, miễn là kế hoạch release giữ đúng thứ tự tương thích.

Context/label trong Liquibase có thể dùng để chọn changeset theo giai đoạn triển khai, nhưng phải xác nhận filter được truyền thực tế. Thiếu filter trong một số cấu hình có thể làm phạm vi changeset chạy rộng hơn dự kiến; không nên coi labels là rào chắn duy nhất để tránh contract chạy quá sớm.

## 14. Bất biến của changeset và lịch sử triển khai

Sau khi một changeset được thực thi thành công, Liquibase ghi nhận thông tin trong **DATABASECHANGELOG**, bao gồm định danh changeset và checksum. Nếu sau đó sửa nội dung changeset cũ, môi trường đã chạy bản trước có thể gặp **checksum validation error**.

Ví dụ, nếu changeset ban đầu chỉ thêm cột nullable nhưng bản sau bị sửa thành nullable:false trong chính ID cũ, các môi trường đã triển khai có lịch sử không tương đồng với định nghĩa mới. Cách làm đúng trong chuỗi phát hành thông thường là:

- Giữ nguyên changeset đã được triển khai.
- Thêm changeset mới dùng **addNotNullConstraint** khi dữ liệu đã sẵn sàng.
- Nếu cần cho phép NULL trở lại, tạo changeset mới dùng **dropNotNullConstraint**.
- Giữ ID, author và đường dẫn changelog ổn định; tránh đổi định danh ngoài ý muốn.
- Chỉ dùng các cơ chế xử lý checksum có kiểm soát sau khi đã xác định nguyên nhân; không chạy **clear-checksums** để bỏ qua một thay đổi lịch sử chưa được điều tra.

Một changeset được ghi nhận đã chạy không có nghĩa schema sẽ luôn đúng trong tương lai nếu có người can thiệp DDL thủ công. Cần phối hợp lịch sử Liquibase với quyền database, kiểm tra schema và quy trình quản lý thay đổi.

## 15. Bài thực hành có kiểm chứng

**Bài toán:** Bảng customer có cột contact_channel VARCHAR(20) nullable. Một số hàng cũ có NULL. Từ phiên bản mới, mọi customer phải có contact_channel hợp lệ.

**Bước 1 — Đánh giá trạng thái**

- Truy vấn COUNT(*) WHERE contact_channel IS NULL và ghi lại kết quả.
- Xác định liệu UNKNOWN có phải giá trị nghiệp vụ chấp nhận được hay cần thu thập lại dữ liệu thật.
- Kiểm tra ứng dụng hiện tại, batch/import, consumer và những nguồn ghi có thể truyền NULL.

**Bước 2 — Chuẩn bị thay đổi**

- Viết changeset backfill riêng nếu có dữ liệu cần sửa.
- Viết changeset addNotNullConstraint với precondition để dừng khi còn NULL.
- Viết rollback dropNotNullConstraint và mô tả giới hạn của việc rollback dữ liệu đã backfill.
- Nếu bảng đang rất lớn, mô tả phương án batching và thời gian chạy dự kiến dựa trên thử nghiệm thực tế.

**Bước 3 — Thử trên database nâng cấp**

- Khởi tạo database thử nghiệm từ dữ liệu có NULL tương tự môi trường đang chạy.
- Chạy validate, xem update-sql và thử backfill.
- Xác nhận null_count về 0; thử một luồng ghi chuẩn của ứng dụng.
- Áp NOT NULL, kiểm tra metadata is_nullable và thử INSERT NULL trong fixture hợp lệ; database phải từ chối.

**Bước 4 — Thử gỡ constraint**

- Chạy changeset dropNotNullConstraint trên một database thử nghiệm tương ứng.
- Kiểm tra metadata trở thành nullable và thử ghi NULL trong tình huống hợp lệ.
- Trước khi rollback dropNotNullConstraint, thử thêm một hàng NULL mới; quan sát rằng bước addNotNullConstraint để rollback sẽ không thể thành công nếu chưa xử lý hàng vi phạm.

**Bước 5 — Tổng kết bằng chứng**

Ghi lại ID changeset, thời gian migration, SQL thực tế, số lượng bản ghi NULL trước/sau, trạng thái metadata và kết quả rollback. Người học cần giải thích được vì sao dữ liệu không hợp lệ phải được xử lý trước khi áp constraint, và vì sao rollback schema không tự động phục hồi dữ liệu ban đầu.

## 16. Checklist review trước khi merge

Trước khi chấp nhận migration thêm hoặc gỡ NOT NULL, reviewer nên xác nhận:

- Đã xác định đúng bảng, schema, cột và **columnDataType** hiện tại.
- Biết rõ trạng thái ban đầu của cột: nullable hay NOT NULL.
- Mục đích nghiệp vụ đã được mô tả rõ; không dùng NOT NULL để che dữ liệu chưa được làm sạch.
- Đã kiểm tra số hàng NULL và tính đúng đắn của chiến lược backfill.
- Đã xác nhận mọi luồng ghi mới không tiếp tục tạo NULL trước khi bật constraint.
- Nếu dùng **defaultNullValue**, đã phân biệt nó với DEFAULT lâu dài và kiểm tra tải cập nhật.
- Precondition dùng **HALT** khi dữ liệu không đạt, tránh đánh dấu đã chạy khi schema chưa đúng.
- Đã xem SQL ALTER của đúng DBMS/Liquibase version, đánh giá lock và transaction.
- Đã thử migration trên database có lịch sử và dữ liệu đại diện, không chỉ trên database trống.
- Rollback có khôi phục đúng trạng thái schema ban đầu; nếu rollback từ nullable về NOT NULL, đã xử lý dữ liệu NULL mới.
- Đã kiểm tra tương thích ứng dụng trước/sau thay đổi, đặc biệt với rolling deployment.
- Những changeset cũ đã được giữ nguyên, không sửa nội dung làm sai lệch checksum.
- CI/CD ghi nhận được lịch sử thực thi và có bước xác minh metadata cùng dữ liệu.

**Kết luận:** **addNotNullConstraint** giúp chuyển một cột đã tồn tại thành bắt buộc có giá trị; **dropNotNullConstraint** cho phép cột nhận NULL trở lại. Giá trị của hai thao tác không nằm ở việc ALTER TABLE có ngắn hay không, mà ở việc chúng được áp dụng đúng **thời điểm dữ liệu và ứng dụng đã sẵn sàng**. Khi thiết kế backfill, precondition, kiểm chứng theo DBMS và rollback theo trạng thái thực tế, nhóm sẽ quản lý ràng buộc NOT NULL trong Liquibase một cách có kiểm soát, dễ truy nguyên và an toàn qua nhiều môi trường.

