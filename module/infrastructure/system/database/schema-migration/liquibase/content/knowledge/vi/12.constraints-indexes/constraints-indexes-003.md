# Thiết lập quy tắc tham chiếu khi cập nhật hoặc xóa

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **Khóa và chỉ mục** này tập trung vào một quyết định quan trọng của thiết kế **khóa ngoại (foreign key)**: khi bản ghi được tham chiếu bị **xóa** hoặc khóa được tham chiếu bị **cập nhật**, cơ sở dữ liệu phải xử lý các bản ghi liên quan ra sao?

Quy tắc đó được khai báo thông qua **ON DELETE** và **ON UPDATE** của ràng buộc khóa ngoại. Liquibase giúp version hóa chúng trong changeset, để các môi trường cùng áp dụng một thiết kế rõ ràng và có lịch sử kiểm tra được. Mục tiêu của bài là chọn đúng hành vi tham chiếu, khai báo bằng Liquibase, đánh giá tác động dữ liệu, kiểm tra trên database thật và xây dựng phương án rollback an toàn.

## 1. Khóa ngoại bảo vệ quan hệ nào?

Giả sử hệ thống bán hàng có hai bảng:

- **customer**: khách hàng, với khóa chính **id**.
- **purchase_order**: đơn hàng, với **customer_id** trỏ đến **customer.id**.

Quan hệ có thể được hình dung:

~~~text
customer (bảng cha / bảng được tham chiếu)
+--------+----------------+
| id PK  | name           |
+--------+----------------+
     ^
     | purchase_order.customer_id -> customer.id
     |
purchase_order (bảng con / bảng tham chiếu)
+--------+-----------------+-------------+
| id PK  | customer_id FK  | total       |
+--------+-----------------+-------------+
~~~

Khóa ngoại bảo đảm một giá trị **purchase_order.customer_id** khác NULL phải tham chiếu đến khách hàng hợp lệ. Nếu customer_id được phép NULL, bản ghi đơn hàng có thể không liên kết khách hàng theo quy tắc nullable thông thường.

Khi tạo khóa ngoại, ta cần xác định hai hướng tác động:

1. **ON DELETE**: điều gì xảy ra với các đơn hàng khi một **customer** được xóa?
2. **ON UPDATE**: điều gì xảy ra với các đơn hàng nếu giá trị khóa được tham chiếu **customer.id** bị thay đổi?

Điều quan trọng: **ON UPDATE không phải quy tắc khi cập nhật mọi cột của bảng cha**. Nếu chỉ sửa **customer.name** mà không sửa khóa được tham chiếu, hành vi ON UPDATE của khóa ngoại không được kích hoạt. Tương tự, xóa hoặc sửa bản ghi **con** không làm database tự xóa bản ghi **cha** theo quy tắc ON DELETE của quan hệ này.

Trong thực tế, khóa chính thường bất biến. Vì vậy, lựa chọn ON DELETE thường ảnh hưởng nghiệp vụ nhiều hơn, còn ON UPDATE cần được cân nhắc nếu khóa tự nhiên hoặc mã định danh có thể đổi.

## 2. Năm hành vi tham chiếu thường gặp

Khi thiết kế foreign key, các lựa chọn phổ biến gồm **NO ACTION**, **RESTRICT**, **CASCADE**, **SET NULL** và **SET DEFAULT**. Khả năng hỗ trợ chi tiết phụ thuộc DBMS. Ví dụ xuyên suốt dùng PostgreSQL, nơi cả ON DELETE và ON UPDATE hỗ trợ những lựa chọn này.

| Hành vi | Khi xóa hàng cha | Khi đổi giá trị khóa cha | Điều kiện/rủi ro đáng chú ý |
|---|---|---|---|
| **NO ACTION** | Không cho để lại tham chiếu không hợp lệ; kiểm tra ràng buộc theo thời điểm áp dụng | Tương tự với khóa cha bị đổi | Có thể khác RESTRICT khi ràng buộc được phép trì hoãn kiểm tra |
| **RESTRICT** | Từ chối xóa khi còn bản ghi con tham chiếu | Từ chối đổi khóa khi còn tham chiếu | Thường phù hợp dữ liệu cần giữ liên kết bắt buộc |
| **CASCADE** | Tự động xóa các bản ghi con liên quan | Tự động đổi giá trị FK ở bản ghi con theo khóa mới | Có thể ảnh hưởng số lượng lớn bản ghi, lan theo nhiều cấp |
| **SET NULL** | Đặt FK ở con thành NULL | Đặt FK ở con thành NULL | Cột FK phải chấp nhận NULL, và nghiệp vụ phải cho phép mất liên kết |
| **SET DEFAULT** | Đặt FK ở con về giá trị mặc định | Đặt FK ở con về giá trị mặc định | Default phải đáp ứng ràng buộc FK hoặc là NULL hợp lệ; hỗ trợ khác nhau theo DBMS |

**NO ACTION không có nghĩa database “không làm gì rồi bỏ qua kiểm tra”.** Database vẫn duy trì toàn vẹn tham chiếu. Trong PostgreSQL, ràng buộc **NO ACTION** có thể được khai báo **DEFERRABLE**, và việc kiểm tra có thể trì hoãn đến cuối transaction khi cấu hình và transaction yêu cầu. **RESTRICT** không cho trì hoãn kiểm tra hành động tham chiếu theo cùng cách đó. Với các ràng buộc kiểm tra ngay, hai lựa chọn thường trông giống nhau.

Không nên mặc định mọi DBMS hỗ trợ cả năm lựa chọn cho cả ON DELETE và ON UPDATE. Ví dụ, MySQL/InnoDB không hỗ trợ **SET DEFAULT** như một hành động foreign key khả dụng; Oracle có khác biệt và không có cú pháp ON UPDATE tương đương PostgreSQL cho mọi hành động; SQL Server dùng tập lựa chọn riêng và **RESTRICT** không phải từ khóa hành động như trong PostgreSQL. Luôn đối chiếu chính xác dialect/version của database đích.

## 3. Chọn ON DELETE dựa trên vòng đời dữ liệu

### RESTRICT hoặc NO ACTION: giữ bản ghi cha khi còn phụ thuộc

Nếu mỗi đơn hàng bắt buộc gắn với một khách hàng hợp lệ để phục vụ kiểm toán, việc xóa customer khi còn đơn hàng nên bị từ chối. Có thể dùng:

~~~sql
FOREIGN KEY (customer_id)
REFERENCES customer(id)
ON DELETE RESTRICT
~~~

Khi ứng dụng cố xóa khách hàng còn đơn hàng, database trả lỗi vi phạm khóa ngoại. Ứng dụng cần chuyển khách hàng sang trạng thái vô hiệu hóa, ẩn danh thông tin cá nhân theo quy trình phù hợp, hoặc xử lý dữ liệu phụ thuộc trước khi xóa vật lý.

Đây thường là lựa chọn an toàn cho dữ liệu giao dịch có giá trị lịch sử. Nó cũng buộc các luồng nghiệp vụ xem xét quan hệ thay vì để một lệnh DELETE vô tình xóa nhiều bảng.

### CASCADE: xóa đối tượng sở hữu cùng vòng đời

Ví dụ **purchase_order** có bảng **purchase_order_item**, trong đó mỗi dòng chi tiết chỉ có ý nghĩa khi đơn hàng còn tồn tại. Có thể chọn **ON DELETE CASCADE** từ order_item đến purchase_order:

~~~sql
FOREIGN KEY (order_id)
REFERENCES purchase_order(id)
ON DELETE CASCADE
~~~

Xóa một purchase_order sẽ làm database xóa các dòng order_item phụ thuộc. Nhưng đừng suy ra rằng xóa customer cũng xóa đơn hàng nếu khóa ngoại từ purchase_order đến customer đang dùng RESTRICT. Mỗi quan hệ có quy tắc độc lập.

CASCADE hợp lý khi bản ghi con thực sự thuộc quyền sở hữu và vòng đời của bản ghi cha. Với dữ liệu quan trọng, hãy kiểm tra chuỗi cascading qua nhiều cấp, tác động tới các trigger, chi phí khóa và thời gian giao dịch. Một DELETE cha duy nhất có thể ảnh hưởng hàng trăm nghìn hàng con.

### SET NULL: ngắt liên kết khi mối quan hệ là tùy chọn

Một bản ghi **support_ticket** có thể gắn với nhân viên xử lý **assignee_id**. Khi tài khoản nhân viên bị xóa, ticket vẫn cần được giữ để phân công lại. Lựa chọn:

~~~sql
FOREIGN KEY (assignee_id)
REFERENCES employee(id)
ON DELETE SET NULL
~~~

Điều kiện bắt buộc là **support_ticket.assignee_id** phải nullable, đồng thời ứng dụng phải xử lý được ticket chưa có người phụ trách. Nếu cột khai báo NOT NULL, cơ chế SET NULL sẽ xung đột khi cần thực hiện; chỉ khai báo hành động trên FK không tự làm cột nullable.

Trên một số DBMS, có thể chỉ định tập cột áp dụng SET NULL trong ràng buộc nhiều cột. Không giả định cú pháp bổ sung đó được Liquibase và mọi DBMS hỗ trợ như nhau.

### SET DEFAULT: chuyển tham chiếu về đối tượng dự phòng

SET DEFAULT có thể dùng khi muốn chuyển bản ghi con về một giá trị đã quy định, chẳng hạn **assignee_id** về tài khoản hệ thống. Tuy nhiên, default khác NULL vẫn phải trỏ đến một bản ghi cha đang tồn tại; nếu không, ràng buộc vẫn có thể thất bại.

Cần kiểm soát vòng đời bản ghi dự phòng và giải thích rõ ý nghĩa nghiệp vụ của nó. Không dùng một ID giả chỉ để né lỗi toàn vẹn tham chiếu.

## 4. Chọn ON UPDATE khi khóa được tham chiếu thay đổi

Nếu bảng **department** có khóa tự nhiên **code**, ví dụ **SALES**, và bảng **employee** lưu **department_code**, khi đổi mã **SALES** thành **COMMERCIAL** có thể dùng:

- **ON UPDATE CASCADE:** tự đổi employee.department_code tương ứng, giữ liên kết.
- **ON UPDATE RESTRICT/NO ACTION:** từ chối đổi code khi còn nhân viên tham chiếu, buộc ứng dụng thực hiện quy trình chuyển đổi.
- **ON UPDATE SET NULL:** xóa liên kết phòng ban ở nhân viên, chỉ phù hợp khi quan hệ tùy chọn.
- **ON UPDATE SET DEFAULT:** chuyển nhân viên sang mã phòng ban mặc định hợp lệ nếu database hỗ trợ.

Nhiều hệ thống dùng khóa chính bất biến như BIGINT hoặc UUID và đặt mã nghiệp vụ ở cột riêng có thể thay đổi. Khi đó, việc đổi mã doanh nghiệp không chạm khóa chính; ON UPDATE của FK trỏ vào ID sẽ ít khi được kích hoạt.

**ON UPDATE CASCADE không phải phép thay thế tự động cho mọi loại chuyển đổi định danh.** Nếu mã mới va chạm unique constraint, dữ liệu không còn hợp lệ hoặc cột có trigger phức tạp, update vẫn có thể thất bại. Phải thử trên dữ liệu thực tế đủ đại diện.

## 5. Khai báo foreign key với Liquibase

Liquibase hỗ trợ change type **addForeignKeyConstraint**. Dưới đây là một changeset YAML có thể đưa vào changelog, giả sử hai bảng **customer(id)** và **purchase_order(id, customer_id)** đã tồn tại, cột liên kết có kiểu tương thích và khóa cha là PRIMARY KEY hoặc UNIQUE phù hợp:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-order-customer-fk
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
        - tableExists:
            tableName: purchase_order
        - columnExists:
            tableName: purchase_order
            columnName: customer_id
        - not:
            - foreignKeyConstraintExists:
                foreignKeyName: fk_order_customer
                foreignKeyTableName: purchase_order
      changes:
        - addForeignKeyConstraint:
            constraintName: fk_order_customer
            baseTableName: purchase_order
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            onDelete: RESTRICT
            onUpdate: CASCADE
      rollback:
        - dropForeignKeyConstraint:
            baseTableName: purchase_order
            constraintName: fk_order_customer
~~~

Ở đây:

- **baseTableName / baseColumnNames** xác định bảng và cột **con** chứa FK.
- **referencedTableName / referencedColumnNames** xác định bảng và khóa **cha**.
- **constraintName** đặt tên ràng buộc ổn định để truy vết, thay đổi hoặc xóa về sau.
- **onDelete: RESTRICT** ngăn xóa khách hàng khi còn đơn hàng.
- **onUpdate: CASCADE** truyền thay đổi khóa khách hàng sang giá trị FK của đơn hàng.
- **preConditions** chặn chạy khi đối tượng nền tảng thiếu hoặc tên FK đã tồn tại. Chúng không chứng minh dữ liệu không có bản ghi mồ côi hay FK cùng tên đã đúng định nghĩa.
- **rollback** xóa ràng buộc được tạo; việc này không khôi phục những cập nhật/xóa dữ liệu đã xảy ra do hành vi tham chiếu sau khi migration chạy.

Các thuộc tính và hành vi của **onDelete**, **onUpdate**, **deferrable** và **initiallyDeferred** phụ thuộc DBMS; không lấy một YAML dùng PostgreSQL áp dụng nguyên vẹn cho tất cả database.

### Ví dụ dùng SET NULL

Giả sử bảng **support_ticket** có cột **assignee_id** nullable, bảng **employee** có khóa chính id:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-ticket-assignee-fk
      author: database-team
      changes:
        - addForeignKeyConstraint:
            constraintName: fk_ticket_assignee
            baseTableName: support_ticket
            baseColumnNames: assignee_id
            referencedTableName: employee
            referencedColumnNames: id
            onDelete: SET NULL
            onUpdate: CASCADE
      rollback:
        - dropForeignKeyConstraint:
            baseTableName: support_ticket
            constraintName: fk_ticket_assignee
~~~

Khi xóa employee, ticket còn lại nhưng assignee_id trở thành NULL. Trước khi áp dụng, kiểm tra ứng dụng không mặc định trường này luôn có giá trị; query JOIN INNER có thể làm mất ticket khỏi kết quả, còn code có thể gây lỗi khi giải tham chiếu assignee.

## 6. Các yêu cầu bắt buộc trước khi thêm ràng buộc

Cấu hình action đúng chưa đủ để migration thành công. Cần xem xét đồng thời schema, dữ liệu và chi phí vận hành.

### Khóa được tham chiếu và kiểu cột

Cột cha được tham chiếu phải có tính duy nhất phù hợp (thường PRIMARY KEY hoặc UNIQUE constraint/index được DBMS chấp nhận). Kiểu dữ liệu giữa cột con và cột cha phải tương thích theo quy tắc DBMS. Với khóa nhiều cột, danh sách **baseColumnNames** và **referencedColumnNames** phải khớp số lượng và thứ tự:

~~~yaml
- addForeignKeyConstraint:
    constraintName: fk_order_line_tenant_order
    baseTableName: order_line
    baseColumnNames: tenant_id,order_id
    referencedTableName: tenant_order
    referencedColumnNames: tenant_id,id
    onDelete: CASCADE
~~~

Ví dụ composite key này đòi hỏi bảng **tenant_order** có khóa UNIQUE/PRIMARY KEY phù hợp cho cặp **(tenant_id, id)**. Với các cột nullable trong foreign key tổng hợp, cách kiểm tra giá trị NULL phụ thuộc quy tắc MATCH và DBMS; không nên giả định chúng có cùng hành vi với FK đơn cột.

### Kiểm tra bản ghi con mồ côi

Trước khi thêm FK, cần biết có bản ghi con trỏ đến khóa cha không tồn tại hay không. Ví dụ PostgreSQL:

~~~sql
SELECT po.id, po.customer_id
FROM purchase_order AS po
LEFT JOIN customer AS c ON c.id = po.customer_id
WHERE po.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Nếu có kết quả, thêm FK thường thất bại khi database xác thực dữ liệu hiện tại. Phải xử lý từng trường hợp theo nghiệp vụ: tạo lại bản ghi cha hợp lệ, sửa tham chiếu, chuyển liên kết thành NULL nếu được phép, hoặc làm sạch bản ghi mồ côi theo kế hoạch được phê duyệt. Không tự ý xóa dữ liệu chỉ để migration “qua được”.

Nếu chuẩn bị dùng SET NULL, kiểm tra cột con có ràng buộc NOT NULL không. Nếu chuẩn bị dùng SET DEFAULT, kiểm tra default có thực sự tham chiếu bản ghi hợp lệ. Nếu chọn CASCADE, ước lượng tổng số bản ghi sẽ bị xóa hoặc cập nhật trên các bảng con khi một thao tác cha diễn ra.

### Index và hiệu năng

FK là ràng buộc dữ liệu; index phục vụ hiệu năng truy vấn và kiểm tra liên kết. PostgreSQL không mặc định tạo index trên **cột con** chỉ vì bạn thêm FK. Với **purchase_order.customer_id**, thường nên xem xét index riêng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 005-order-customer-index
      author: database-team
      changes:
        - createIndex:
            tableName: purchase_order
            indexName: idx_purchase_order_customer_id
            columns:
              - column:
                  name: customer_id
      rollback:
        - dropIndex:
            tableName: purchase_order
            indexName: idx_purchase_order_customer_id
~~~

Index giúp database tìm nhanh bản ghi con khi xóa/đổi khóa cha và trong truy vấn JOIN. Nhưng index làm tăng chi phí ghi và chiếm dung lượng; với bảng rất lớn cần đánh giá chiến lược tạo index trực tuyến hoặc concurrently theo DBMS, thay vì mặc định chạy DDL khóa bảng kéo dài.

## 7. Thay đổi ON DELETE/ON UPDATE cho một FK đã tồn tại

Trong nhiều DBMS, không thể “sửa trực tiếp” hành vi ON DELETE/ON UPDATE của một ràng buộc FK đã tạo bằng một thao tác phổ quát. Cách thông dụng là **drop FK cũ rồi tạo FK mới** với cùng tập cột và quy tắc mới. Hãy đưa cả hai bước vào **changeset mới**, có định danh mới và rollback khôi phục chính sách cũ nếu việc đó khả thi.

Giả sử FK **fk_ticket_assignee** trước đây dùng **ON DELETE RESTRICT**, nay muốn chuyển sang **SET NULL**. Điều kiện tiên quyết: **support_ticket.assignee_id** đang nullable, dữ liệu và ứng dụng xử lý được ticket không có assignee.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 006-ticket-assignee-set-null
      author: database-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - foreignKeyConstraintExists:
            foreignKeyName: fk_ticket_assignee
            foreignKeyTableName: support_ticket
      changes:
        - dropForeignKeyConstraint:
            baseTableName: support_ticket
            constraintName: fk_ticket_assignee
        - addForeignKeyConstraint:
            constraintName: fk_ticket_assignee
            baseTableName: support_ticket
            baseColumnNames: assignee_id
            referencedTableName: employee
            referencedColumnNames: id
            onDelete: SET NULL
            onUpdate: CASCADE
      rollback:
        - dropForeignKeyConstraint:
            baseTableName: support_ticket
            constraintName: fk_ticket_assignee
        - addForeignKeyConstraint:
            constraintName: fk_ticket_assignee
            baseTableName: support_ticket
            baseColumnNames: assignee_id
            referencedTableName: employee
            referencedColumnNames: id
            onDelete: RESTRICT
            onUpdate: CASCADE
~~~

Ví dụ giả định quy tắc cũ thật sự là **RESTRICT** cho DELETE và **CASCADE** cho UPDATE. Precondition kiểm tra FK tồn tại, **không** xác minh hành vi hiện hành của FK. Trước khi chạy production, phải kiểm tra định nghĩa thực tế và bảo đảm rollback khôi phục đúng quy tắc trước đó.

PostgreSQL hỗ trợ DDL transactional cho các thao tác này trong trường hợp thông thường, nhưng lệnh thêm ràng buộc và xác thực dữ liệu có thể khóa bảng. Không mặc định mọi DBMS sẽ rollback nguyên tử nếu bước tạo FK mới thất bại: nhiều hệ quản trị có DDL tự commit. Với bảng lớn hoặc hệ thống có SLA cao, cần nghiên cứu thời gian khóa, cách tạo ràng buộc chưa validate nếu DBMS hỗ trợ, rồi validate sau bằng quy trình riêng; đây là quyết định theo DBMS cụ thể.

**Không sửa changeset cũ** chỉ để đổi ON DELETE. Changeset đã chạy có checksum và lịch sử riêng trong DATABASECHANGELOG; chỉnh nội dung cũ gây sai lệch giữa các môi trường và có thể làm Liquibase từ chối vì checksum thay đổi.

## 8. Kiểm tra hành vi bằng SQL trên môi trường thử nghiệm

Sau khi Liquibase áp dụng FK, cần kiểm tra không chỉ ràng buộc có tồn tại mà còn hành vi thực tế.

### Xem quy tắc đang lưu trong database

Với PostgreSQL, có thể truy vấn metadata chuẩn:

~~~sql
SELECT
    rc.constraint_name,
    rc.update_rule,
    rc.delete_rule
FROM information_schema.referential_constraints AS rc
WHERE rc.constraint_name = 'fk_order_customer';
~~~

Kết quả dự kiến cho ví dụ đầu tiên là **update_rule = CASCADE** và **delete_rule = RESTRICT**. Nếu có nhiều schema, bổ sung điều kiện **constraint_schema** để xác định đúng ràng buộc.

### Thử DELETE và UPDATE có kiểm soát

Trên **database test có dữ liệu mẫu**, tạo customer và purchase_order tương ứng. Sau đó kiểm tra:

1. **ON DELETE RESTRICT:** xóa customer còn purchase_order phải bị từ chối; đơn hàng vẫn tồn tại.
2. **ON UPDATE CASCADE:** đổi customer.id theo quy trình thử nghiệm; purchase_order.customer_id phải cập nhật theo.
3. **ON DELETE SET NULL:** trong quan hệ support_ticket–employee, xóa employee và xác nhận ticket còn tồn tại nhưng assignee_id = NULL.
4. **ON DELETE CASCADE:** trong quan hệ purchase_order_item–purchase_order, xóa order và xác nhận các item phụ thuộc đã bị xóa, đồng thời kiểm tra không có bảng khác bị ảnh hưởng ngoài dự định.

Để tránh thay đổi dữ liệu kiểm thử ngoài ý muốn, dùng dữ liệu cô lập và transaction có thể rollback nếu DBMS hỗ trợ cho các lệnh kiểm tra. Khi lệnh DELETE cố ý gây lỗi, PostgreSQL sẽ đưa transaction hiện tại vào trạng thái aborted; cần ROLLBACK transaction đó hoặc dùng SAVEPOINT và ROLLBACK TO SAVEPOINT trước khi thực hiện thử nghiệm tiếp theo.

Tránh thử hành vi CASCADE bằng cách xóa hàng thật trên production. Không nên chỉ căn cứ vào việc một câu lệnh chạy thành công; cần xác minh **số bản ghi ảnh hưởng**, quan hệ còn lại, các đối tượng phụ thuộc và hiệu năng.

## 9. Precondition, checksum và lịch sử triển khai

Liquibase cho phép dùng **preConditions** để kiểm tra bảng/cột/FK có tồn tại hay không và **sqlCheck** để đánh giá điều kiện dữ liệu cụ thể. Với bước thêm FK, cần nhớ:

- **onFail: HALT** phù hợp khi điều kiện bắt buộc chưa đạt, chẳng hạn bảng cha thiếu hoặc dữ liệu có bản ghi mồ côi.
- **onError: HALT** phù hợp khi không thể truy vấn metadata hoặc điều kiện dữ liệu; không được coi lỗi kiểm tra là lý do tự động bỏ qua.
- **MARK_RAN** chỉ nên dùng nếu đã chứng minh database đang ở trạng thái tương đương với changeset được đánh dấu; tên FK tồn tại chưa đủ để kết luận hành vi ON DELETE/ON UPDATE là đúng.
- **sqlCheck** thường dùng cho phép đếm dữ liệu; câu SQL, phạm vi schema và chi phí truy vấn cần phù hợp database thực tế.

Ví dụ kiểm tra không có bản ghi mồ côi trong precondition PostgreSQL:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - sqlCheck:
      expectedResult: "0"
      sql: |
        SELECT COUNT(*)
        FROM purchase_order po
        LEFT JOIN customer c ON c.id = po.customer_id
        WHERE po.customer_id IS NOT NULL
          AND c.id IS NULL
~~~

Đoạn YAML là **phần preConditions cần đặt trong một changeset**, không phải changelog độc lập hoàn chỉnh. Trên bảng lớn, phép đếm có thể tốn chi phí; cần ước lượng và thử trên môi trường tương đương. Ngoài ra, kiểm tra trước không loại bỏ khả năng có thao tác dữ liệu đồng thời giữa bước kiểm tra và bước áp dụng ràng buộc; DDL vẫn có thể thất bại, nên cần kế hoạch xử lý.

Khi update thành công, Liquibase ghi changeset vào **DATABASECHANGELOG**, với định danh và checksum để tránh chạy trùng một migration cấu trúc. Nếu thay đổi hành vi FK ở tương lai, tạo changeset mới, giữ các changeset cũ bất biến. **DATABASECHANGELOGLOCK** giúp tránh nhiều tiến trình Liquibase cùng cập nhật schema tại một thời điểm, nhưng không thay thế kiểm thử tác động của CASCADE đến dữ liệu ứng dụng.

## 10. Phối hợp với Spring Boot/JPA

Trong ứng dụng Java, ORM/JPA quản lý quan hệ đối tượng và có thể cấu hình hành vi xóa entity. Tuy nhiên, cần tách rõ:

| Cơ chế | Ai thực hiện? | Ý nghĩa |
|---|---|---|
| FK **ON DELETE CASCADE** | Database | Xóa các hàng con khi hàng cha bị xóa theo ràng buộc |
| FK **ON UPDATE CASCADE** | Database | Cập nhật giá trị FK ở hàng con khi khóa cha đổi |
| JPA **CascadeType.REMOVE** | ORM/persistence context | Lan thao tác remove đến entity liên quan theo mapping |
| JPA **orphanRemoval=true** | ORM | Xóa entity con khi bị loại khỏi quan hệ được ORM quản lý |
| Hibernate **@OnDelete** (nếu dùng) | Khai báo ORM có thể ảnh hưởng DDL do Hibernate sinh | Không tự sửa changelog Liquibase đã tồn tại |

Các cơ chế có thể tạo hiệu ứng dữ liệu tương tự nhưng khác điểm kích hoạt và cách quan sát. Ví dụ, xóa customer bằng SQL trực tiếp sẽ kích hoạt cascade ở database nếu FK có ON DELETE CASCADE, nhưng **không** chạy logic cascade entity của JPA. Ngược lại, ORM có thể phát nhiều câu DELETE theo cascade cấu hình trong mapping ngay cả khi FK dùng RESTRICT.

Nếu Liquibase chịu trách nhiệm schema, cấu hình Hibernate nên tránh tự ý đổi DDL, ví dụ dùng **spring.jpa.hibernate.ddl-auto=validate** hoặc **none** tùy quy trình. Khi đổi quy tắc FK, cần xem lại mapping JPA, vòng đời transaction và các event/entity callback; các callback ORM không nhất thiết được gọi đối với bản ghi bị database xóa theo cascade.

Một cấu hình Spring Boot minh họa đường dẫn changelog:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Nếu migration được chạy trong job CI/CD riêng, quyết định rõ bên nào thực thi Liquibase. Tránh cấu hình pipeline và nhiều replica ứng dụng cùng sở hữu migration mà không có điều phối.

## 11. CI/CD, rollback và triển khai qua nhiều môi trường

Thay đổi quy tắc tham chiếu cần được xem như thay đổi hành vi nghiệp vụ: cùng một DELETE có thể bị từ chối trước đây, nhưng sau migration lại tự động xóa hoặc ngắt liên kết của nhiều bản ghi. Vì vậy, quy trình phát hành phải kiểm chứng trước khi áp dụng.

Một luồng triển khai đề xuất:

1. **Mô tả nghiệp vụ:** bản ghi con có cùng vòng đời với cha không, có yêu cầu giữ lịch sử không, có thể cho FK thành NULL không?
2. **Kiểm tra schema/dữ liệu:** khóa cha UNIQUE, kiểu cột tương thích, dữ liệu không mồ côi, default/nullable phù hợp; thống kê lượng dữ liệu có thể bị cascade.
3. **Soạn changeset mới:** đặt tên constraint rõ ràng, khai báo ON DELETE/ON UPDATE, thêm precondition và rollback thích hợp.
4. **Kiểm tra trên môi trường test:** chạy **liquibase validate**, xem SQL bằng **liquibase update-sql**, thực thi **update** trên database đại diện và kiểm thử INSERT/UPDATE/DELETE thực tế.
5. **Đánh giá hiệu năng và khóa:** đo thời gian thay đổi constraint, kiểm tra index ở cột con, thử kịch bản xóa/đổi khóa có nhiều bản ghi liên quan.
6. **Promote cùng changelog qua staging/production:** dùng cùng changeset đã review, không sửa migration đã chạy; đặt lịch phù hợp khi cần khóa bảng dài.
7. **Theo dõi và xác minh:** kiểm tra DATABASECHANGELOG, metadata FK, log ứng dụng, lỗi foreign key, số bản ghi phụ thuộc và tác động truy vấn.

Có thể xem xét **rollback** bằng cách xóa FK mới và tạo lại FK cũ, nhưng rollback **quy tắc ràng buộc** không hồi sinh các bản ghi đã bị CASCADE xóa hoặc phục hồi liên kết đã SET NULL. Muốn khôi phục dữ liệu phải có backup, nhật ký hoặc quy trình nghiệp vụ riêng. Trong nhiều trường hợp, một changeset sửa tiến về phía trước an toàn hơn cố gắng quay lại trạng thái cũ.

Hãy cân nhắc tương thích phiên bản ứng dụng khi triển khai cuốn chiếu: ứng dụng cũ có thể giả định xóa customer bị từ chối, còn ứng dụng mới cho phép xóa và trông chờ cascade. Việc đổi FK trước/sau ứng dụng cần được lên kế hoạch để hai phiên bản cùng vận hành an toàn trong thời gian chuyển tiếp.

## 12. Các sai lầm phổ biến

**Dùng CASCADE vì muốn tránh lỗi foreign key.** Đây là quyết định có thể xóa dữ liệu hàng loạt. Phải chứng minh bản ghi con được phép biến mất cùng cha; nếu không hãy dùng RESTRICT hoặc cơ chế nghiệp vụ phù hợp.

**Khai báo SET NULL khi cột đang NOT NULL.** Khi xóa cha, database không thể ghi NULL vào cột bắt buộc. Cần thiết kế nullable và sửa logic ứng dụng trước khi bật quy tắc.

**Cho rằng SET DEFAULT tự tạo bản ghi cha dự phòng.** Default không tạo parent; giá trị mặc định phải thỏa FK hoặc là NULL hợp lệ.

**Cho rằng NO ACTION bỏ qua toàn vẹn tham chiếu.** Database vẫn kiểm tra; khác biệt với RESTRICT liên quan thời điểm kiểm tra và khả năng trì hoãn, tùy DBMS.

**Nhầm ON UPDATE với UPDATE dữ liệu thông thường.** ON UPDATE chỉ liên quan thay đổi giá trị khóa được tham chiếu. Đổi email hoặc tên khách hàng không kích hoạt quy tắc nếu FK trỏ vào id.

**Quên index ở cột con.** Khi xóa/đổi khóa cha, database phải tìm các hàng con liên quan; thiếu index có thể làm thao tác chậm, tăng thời gian giữ khóa.

**Thêm FK trên dữ liệu bẩn.** Có bản ghi mồ côi làm validate constraint thất bại; không sửa bằng cách bỏ kiểm tra tùy tiện.

**Sửa changeset đã triển khai.** Checksum khác hoặc môi trường dùng định nghĩa không đồng nhất. Tạo changeset mới và ghi rõ chuyển tiếp.

**Coi rollback FK là rollback dữ liệu.** Đổi ràng buộc không đảo ngược bản ghi đã xóa hay giá trị đã cập nhật trước đó.

## 13. Bài tập tự kiểm tra

Xét ba quan hệ sau:

1. **purchase_order → customer:** đơn hàng cần lưu lâu dài để kiểm toán ngay cả khi khách hàng ngừng hoạt động.
2. **purchase_order_item → purchase_order:** mỗi dòng chi tiết chỉ tồn tại cùng đơn hàng, và nghiệp vụ thật sự cho phép xóa đơn hàng vật lý trong môi trường này.
3. **support_ticket → employee:** ticket vẫn phải lưu khi nhân viên phụ trách rời tổ chức và có thể để trống người phụ trách.

Hãy đề xuất **ON DELETE** cho từng quan hệ và xác định một kiểm tra trước migration.

Đáp án tham khảo:

- **purchase_order → customer:** **RESTRICT** hoặc **NO ACTION** với kiểm tra ngay; kiểm tra có bao nhiêu đơn hàng đang phụ thuộc để thiết kế luồng vô hiệu hóa thay cho xóa customer.
- **purchase_order_item → purchase_order:** **CASCADE** khi vòng đời con thật sự phụ thuộc; kiểm tra số dòng item có thể bị xóa cùng một order và chuỗi cascade cấp tiếp theo.
- **support_ticket → employee:** **SET NULL** nếu assignee_id nullable; kiểm tra schema và ứng dụng có xử lý ticket không có người phụ trách.

Với **ON UPDATE**, nếu khóa chính id là bất biến, lựa chọn **RESTRICT** hoặc **NO ACTION** và không cho ứng dụng sửa ID thường dễ hiểu hơn; nếu business key là khóa được tham chiếu và có thể đổi, cân nhắc **CASCADE** cùng kiểm thử dữ liệu phụ thuộc.

## 14. Nguyên tắc ghi nhớ

**ON DELETE** bảo vệ hoặc biến đổi dữ liệu con khi **xóa bản ghi cha**; **ON UPDATE** xử lý khi **giá trị khóa cha được tham chiếu đổi**. **RESTRICT/NO ACTION** giữ tính toàn vẹn bằng cách chặn thao tác không hợp lệ, **CASCADE** lan tác động, **SET NULL** bỏ liên kết và **SET DEFAULT** chuyển về giá trị mặc định hợp lệ nếu DBMS hỗ trợ. Một foreign key chỉ hoạt động đúng khi dữ liệu, nullable/default, khóa unique, index và logic ứng dụng cùng phù hợp.

Trong **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, quy tắc này cần được khai báo tường minh trong **addForeignKeyConstraint** và quản lý bằng changeset mới khi thay đổi. Kết hợp precondition, kiểm tra dữ liệu mồ côi, review update-sql, kiểm thử UPDATE/DELETE, checksum, DATABASECHANGELOG, rollback hoặc forward-fix và pipeline CI/CD sẽ giúp giữ hành vi tham chiếu nhất quán giữa các môi trường và tránh mất dữ liệu ngoài ý muốn.
