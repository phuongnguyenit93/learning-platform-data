# Tạo, đổi và xóa chỉ mục

**Chỉ mục (index)** là cấu trúc dữ liệu giúp cơ sở dữ liệu tìm, lọc, sắp xếp hoặc nối các bản ghi hiệu quả hơn trong những trường hợp thích hợp. Trong Liquibase, tạo, thay đổi và xóa chỉ mục đều là **thay đổi schema cần quản lý bằng changeset**, có thứ tự triển khai, lịch sử, khả năng kiểm tra và chiến lược rollback. Một index có thể cải thiện một truy vấn nhưng lại làm tăng chi phí INSERT/UPDATE/DELETE, thời gian build và dung lượng lưu trữ; vì vậy không nên tạo index chỉ vì thấy truy vấn đang chậm.

Bài này thuộc chương **Khóa và chỉ mục** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Trong phạm vi module, người học quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trọng tâm ở đây là cách biểu diễn vòng đời của index bằng Liquibase, điều chỉnh thiết kế mà không sửa lịch sử đã triển khai, kiểm tra ảnh hưởng hiệu năng và phục hồi khi cần.

## 1. Vì sao cần quản lý index bằng migration?

Giả sử bảng orders có hàng triệu bản ghi. Ứng dụng thường tìm các đơn hàng của một khách hàng, lọc theo trạng thái và sắp xếp theo thời gian tạo:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

Nếu thiếu index phù hợp, database có thể phải đọc nhiều dòng rồi lọc/sắp xếp. Một index phù hợp có khả năng giúp tìm nhanh các dòng thỏa điều kiện và giảm công việc sắp xếp. Tuy nhiên hiệu quả phụ thuộc phân bố dữ liệu, mức độ chọn lọc, kích thước bảng, phiên bản DBMS và kế hoạch truy vấn thực tế.

Khi đưa index vào Liquibase, nhóm được lợi:

- **Có lịch sử:** biết index được tạo/xóa ở changeset nào và đã chạy trên môi trường nào.
- **Có thứ tự:** index chỉ được tạo sau khi bảng, cột hoặc dữ liệu tiền đề sẵn sàng.
- **Có kiểm chứng:** dùng precondition và câu truy vấn catalog để xác nhận trạng thái.
- **Có khả năng phục hồi:** xem trước SQL, chuẩn bị rollback hoặc forward-fix khi migration không đạt.
- **Phối hợp được nhiều môi trường:** cùng changelog nhưng kiểm thử riêng trên database trống và database đã có dữ liệu.

**Lưu ý:** Liquibase không quyết định thay bạn rằng index nào tối ưu. Tác giả migration phải dựa trên workload và phép đo; Liquibase quản lý *cách triển khai thay đổi*.

## 2. Khái niệm: index thông thường, index duy nhất và constraint

Không phải mọi index đều giống nhau.

| Loại | Công dụng | Điều cần lưu ý |
|---|---|---|
| Index thông thường | Hỗ trợ tìm kiếm, join, lọc, sắp xếp | Không tự cấm dữ liệu trùng |
| Index nhiều cột (composite) | Hỗ trợ truy vấn dựa trên nhiều cột theo thứ tự | Thứ tự cột là một quyết định thiết kế |
| Unique index | Yêu cầu giá trị khóa index không trùng theo quy tắc DBMS | Cách xử lý NULL, collation, biểu thức khác nhau theo DBMS |
| Index phục vụ PRIMARY KEY / UNIQUE constraint | Thực thi ràng buộc toàn vẹn của database | Không nên xóa/đổi độc lập mà bỏ qua constraint liên quan |
| Index đặc thù DBMS | Partial, expression, GIN, GiST, full-text, filtered... | Có thể cần SQL riêng và kiểm thử trên DBMS cụ thể |

Một **PRIMARY KEY** hoặc **UNIQUE constraint** là quy tắc toàn vẹn dữ liệu, còn index là cấu trúc phục vụ việc tra cứu/kiểm tra. Trên PostgreSQL, primary key và unique constraint thường có index hỗ trợ do database quản lý. Tạo thêm index giống hệt có thể lãng phí dung lượng và làm chậm ghi.

Trong Liquibase, nếu mục tiêu là quy tắc nghiệp vụ “email phải duy nhất”, nên cân nhắc **addUniqueConstraint** hoặc unique=true theo cơ chế tương ứng, thay vì chỉ nghĩ tới một index phục vụ hiệu năng. Nếu mục tiêu là tăng tốc truy vấn, dùng **createIndex**. Tùy DBMS, unique index và unique constraint có thể không tương đương hoàn toàn về metadata, NULL, deferred constraint hoặc khả năng được sử dụng trong quan hệ ràng buộc.

## 3. Tạo index với createIndex

Liquibase có change type **createIndex** để định nghĩa index theo cách có cấu trúc. Ví dụ YAML tạo index trên cột customer_id của bảng orders:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-001-idx-orders-customer
      author: database-team
      changes:
        - createIndex:
            indexName: idx_orders_customer_id
            tableName: orders
            columns:
              - column:
                  name: customer_id
~~~

Phần quan trọng:

- **changeSet.id** và **author** giúp nhận diện thay đổi theo lịch sử.
- **indexName** là tên index mà nhóm quản lý.
- **tableName** xác định bảng được đánh index.
- **columns** khai báo một hoặc nhiều cột và **thứ tự** của chúng.

Nếu bảng nằm trong schema cụ thể, thêm **schemaName** khi change type hỗ trợ và xác minh đường dẫn schema trên database đích:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-002-idx-app-orders-status
      author: database-team
      changes:
        - createIndex:
            schemaName: app
            tableName: orders
            indexName: idx_orders_status
            columns:
              - column:
                  name: status
~~~

Ví dụ giả định schema app và bảng app.orders đã tồn tại. Cần có migration tiền đề tạo schema/bảng, hoặc quy trình bootstrap chính thức, trước khi tạo index.

### 3.1. Ví dụ tương đương bằng XML

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="20261119-003-idx-orders-created" author="database-team">
        <createIndex
            tableName="orders"
            indexName="idx_orders_created_at">
            <column name="created_at"/>
        </createIndex>
    </changeSet>
</databaseChangeLog>
~~~

Chỉ thay định dạng YAML thành XML không làm thay đổi nguyên tắc: index vẫn phải tương thích với DBMS và được tạo theo đúng thứ tự migration. SQL sinh ra có thể khác nhau theo phiên bản Liquibase, JDBC driver và database.

## 4. Thiết kế index từ truy vấn, không từ danh sách cột

Trước khi thêm index, hãy xác định **truy vấn mục tiêu** và điều kiện sử dụng.

Với ví dụ:

~~~sql
SELECT id, created_at
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

Một ứng viên có thể là composite index:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-004-idx-orders-customer-status-created
      author: database-team
      changes:
        - createIndex:
            tableName: orders
            indexName: idx_orders_customer_status_created
            columns:
              - column:
                  name: customer_id
              - column:
                  name: status
              - column:
                  name: created_at
~~~

Thứ tự này là một **ứng viên cần thử nghiệm**, không phải khuyến nghị tuyệt đối. Nó đặt các cột lọc theo phép bằng ở đầu, rồi cột thường dùng khi sắp xếp. DBMS có thể chọn index khác hoặc vẫn cần sort tùy hướng sắp xếp, phạm vi truy vấn, thống kê và tỷ lệ bản ghi thỏa điều kiện.

### 4.1. Thứ tự cột trong composite index

Nhiều index dạng B-tree có lợi từ các cột dẫn đầu. Một index (customer_id, status, created_at) thường hữu ích cho truy vấn có điều kiện customer_id và status; không nên mặc định nó tốt tương đương cho truy vấn **chỉ** lọc created_at.

Các câu hỏi cần trả lời:

1. Truy vấn lọc theo cột nào bằng dấu bằng, khoảng giá trị hoặc tiền tố?
2. Thứ tự sắp xếp và giới hạn LIMIT có quan trọng không?
3. Dữ liệu phân bố ra sao? status có quá ít giá trị nên độ chọn lọc thấp không?
4. Truy vấn có thể tận dụng một index sẵn có không?
5. Các hoạt động ghi dữ liệu tăng thêm bao nhiêu chi phí khi duy trì index?

Không tạo một index riêng cho mọi cột rồi coi đó là tối ưu. Tập hợp index dư thừa sẽ làm tăng dung lượng, I/O và chi phí ghi.

### 4.2. Index cho khóa ngoại

Trong PostgreSQL, index hỗ trợ khóa ngoại ở **phía bảng tham chiếu** không phải lúc nào cũng được tạo tự động. Ví dụ orders.customer_id tham chiếu customers.id; index trên orders.customer_id có thể hữu ích khi join hoặc khi xóa/cập nhật bản ghi customers khiến database phải kiểm tra các dòng orders liên quan.

Cần xem index hiện hữu trước khi tạo: một composite index bắt đầu bằng customer_id có thể đã phục vụ trường hợp này. Index ở phía được tham chiếu thường đã được bảo đảm qua primary/unique key, không nên tự tạo bản sao không cần thiết.

## 5. Thêm precondition và rollback khi tạo index

Để tránh áp dụng mù quáng lên database đã có lịch sử hoặc từng bị thay đổi thủ công, có thể bổ sung precondition:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-005-idx-orders-customer
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: customer_id
        - not:
            - indexExists:
                tableName: orders
                indexName: idx_orders_customer_id
      changes:
        - createIndex:
            tableName: orders
            indexName: idx_orders_customer_id
            columns:
              - column:
                  name: customer_id
      rollback:
        - dropIndex:
            tableName: orders
            indexName: idx_orders_customer_id
~~~

Ở đây:

- tableExists và columnExists xác minh đối tượng tiền đề.
- not/indexExists yêu cầu index mang tên dự kiến chưa tồn tại.
- onFail=HALT chặn thay đổi nếu trạng thái không phù hợp.
- rollback mô tả thao tác gỡ index vừa tạo.

**Nếu index đã tồn tại nhưng changeset chưa được Liquibase ghi nhận, không tự động chuyển onFail thành MARK_RAN.** Tên index giống nhau không chứng minh rằng cột, thứ tự, kiểu index, biểu thức, predicate hoặc tính duy nhất đều giống thiết kế mong đợi. Cần kiểm tra định nghĩa thực tế rồi lựa chọn quy trình đồng bộ/baseline có kiểm chứng.

Precondition metadata có thể tốn chi phí snapshot, nhất là trên database có nhiều đối tượng. Dùng chúng khi hữu ích và đo thời gian trên môi trường đại diện; đừng thêm hàng loạt kiểm tra trùng lặp không cần thiết.

## 6. Unique index và kiểm tra dữ liệu trước khi tạo

Nếu index phải là unique, có thể khai báo thuộc tính unique của createIndex khi phiên bản Liquibase và DBMS hỗ trợ:

~~~xml
<changeSet id="20261119-006-idx-customer-email-unique" author="database-team">
    <createIndex
        tableName="customer"
        indexName="ux_customer_email"
        unique="true">
        <column name="email"/>
    </createIndex>
    <rollback>
        <dropIndex tableName="customer" indexName="ux_customer_email"/>
    </rollback>
</changeSet>
~~~

**Điểm cần kiểm tra trước:** dữ liệu hiện có có trùng khóa hay không. Nếu tạo unique index trên email nhưng hai bản ghi cùng email, DDL có thể thất bại. Có thể dùng SQL khám phá:

~~~sql
SELECT email, COUNT(*) AS occurrences
FROM customer
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Đây là truy vấn chẩn đoán; với dữ liệu cá nhân, không đưa kết quả email thật vào log công khai. Cách xử lý dữ liệu trùng phải được xác định theo nghiệp vụ, không xóa ngẫu nhiên để migration chạy qua.

Nếu yêu cầu là ràng buộc uniqueness của dữ liệu, hãy so sánh với **addUniqueConstraint** và hành vi của DBMS trước khi quyết định. Trên PostgreSQL, UNIQUE constraint có index hỗ trợ; thêm một unique index giống hệt constraint có thể tạo cấu trúc dư thừa.

**NULL:** các DBMS có quy tắc khác nhau đối với NULL trong unique index/constraint; ngay trên PostgreSQL cũng có tùy chọn phiên bản cụ thể ảnh hưởng hành vi. Vì vậy không giả định unique index sẽ làm cột trở thành NOT NULL. Nếu email bắt buộc có giá trị, phải quản lý riêng NOT NULL hoặc thiết kế phù hợp.

## 7. “Đổi chỉ mục” có thể là ba thao tác khác nhau

Trong thực tế, yêu cầu “đổi index” có thể mang một trong ba ý nghĩa:

1. **Đổi tên** index nhưng giữ nguyên định nghĩa.
2. **Thay cấu trúc** index: đổi cột, thứ tự cột, loại index, tính unique hoặc điều kiện lọc.
3. **Xây dựng lại/khắc phục** index do bloat, hỏng hoặc cần thay đổi cấu hình vận hành.

Ba trường hợp có mức rủi ro và SQL khác nhau. **Không sửa changeset tạo index đã được triển khai để đổi định nghĩa**. Nếu changeset 001 đã ghi trong DATABASECHANGELOG, chỉnh nó có thể gây checksum mismatch, và thường cũng không tự biến đổi index hiện có. Hãy viết **changeset mới** thể hiện thao tác chuyển tiếp.

### 7.1. Đổi tên index

Tên index có thể cần thay đổi để thống nhất quy ước đặt tên. Một số DBMS cung cấp lệnh đổi tên riêng; không nên mặc định có một change type renameIndex tiêu chuẩn dùng giống nhau trên mọi phiên bản Liquibase/DBMS.

Ví dụ **PostgreSQL**, trên index thông thường độc lập với constraint:

~~~sql
ALTER INDEX public.idx_orders_customer_id
RENAME TO idx_orders_customer;
~~~

Đưa SQL riêng theo DBMS vào changeset:

~~~xml
<changeSet
    id="20261119-007-rename-orders-index"
    author="database-team"
    dbms="postgresql">
    <sql>
        ALTER INDEX public.idx_orders_customer_id
        RENAME TO idx_orders_customer;
    </sql>
    <rollback>
        <sql>
            ALTER INDEX public.idx_orders_customer
            RENAME TO idx_orders_customer_id;
        </sql>
    </rollback>
</changeSet>
~~~

Lệnh ở trên giả định index cũ có tồn tại, index mới chưa có và tài khoản có quyền phù hợp. Nên kiểm tra các điều kiện trước khi chạy thật. Đổi tên index có thể ảnh hưởng script giám sát, thao tác vận hành, tài liệu và công cụ tham chiếu theo tên; hãy cập nhật những nơi đó trong kế hoạch phát hành.

**Không xử lý index do PRIMARY KEY/UNIQUE constraint quản lý như một index độc lập.** Trên PostgreSQL, đổi tên index gắn với constraint có thể kéo theo đổi tên constraint; nếu mục tiêu là đổi tên ràng buộc, hãy nghiên cứu lệnh ALTER TABLE ... RENAME CONSTRAINT và thử trên DBMS/phiên bản cụ thể.

### 7.2. Thay cột hoặc cấu trúc index

Không thể coi một index cũ đang có khóa (customer_id) là index mới có khóa (customer_id, status) chỉ bằng việc đổi tên. Đây là thay đổi định nghĩa và thường cần tạo một index mới rồi ngừng dùng index cũ.

Một quy trình chuyển tiếp an toàn hơn là:

1. Tạo index **mới** bằng changeset mới, với tên mới và định nghĩa mong muốn.
2. Kiểm tra build hoàn tất và database thực sự có index hợp lệ.
3. Thử query plan/hiệu năng của workload cần hỗ trợ.
4. Khi xác nhận hệ thống dùng được index mới và không còn nhu cầu index cũ, dùng changeset khác để xóa index cũ.
5. Giữ rollback/forward-fix rõ ràng cho mỗi giai đoạn.

Ví dụ (changeset trong **bản phát hành tạo index mới**, chưa xóa index cũ):

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-008-create-new-orders-index
      author: database-team
      changes:
        - createIndex:
            tableName: orders
            indexName: idx_orders_customer_status
            columns:
              - column:
                  name: customer_id
              - column:
                  name: status
      rollback:
        - dropIndex:
            tableName: orders
            indexName: idx_orders_customer_status
~~~

Sau khi benchmark và phê duyệt, **một changeset trong bản phát hành sau** có thể xóa idx_orders_customer_id. Không nên tạo rồi xóa index cũ ngay trong cùng bước chỉ vì định dạng changelog cho phép: trên bảng lớn, việc đó có thể gây tải, lock hoặc ảnh hưởng truy vấn khác.

### 7.3. Rebuild không giống rename hay thay cột

Rebuild có thể được yêu cầu khi index bloat, cần thay storage parameters, hoặc có vấn đề vận hành. PostgreSQL cung cấp các dạng REINDEX; các tùy chọn có khả năng hoạt động đồng thời và giới hạn transaction riêng theo phiên bản. Đây là thao tác cần lên lịch, đánh giá quyền, dung lượng, lock và rollback thực tế; không nên coi rebuild như một change type có thể lặp lại tùy tiện trong mọi lần startup.

Nếu mục tiêu thực chất là tối ưu truy vấn, hãy bắt đầu từ EXPLAIN, thống kê và các index hiện có trước khi quyết định rebuild hay tạo mới.

## 8. Chỉ mục biểu thức, partial index và SQL đặc thù PostgreSQL

Không phải mọi loại index đều biểu diễn thuận tiện bằng createIndex chuẩn. Chẳng hạn, PostgreSQL hỗ trợ index trên biểu thức:

~~~sql
CREATE INDEX idx_customer_lower_email
ON public.customer (LOWER(email));
~~~

Nó có thể hỗ trợ truy vấn lọc theo biểu thức phù hợp:

~~~sql
SELECT id
FROM public.customer
WHERE LOWER(email) = 'support@example.test';
~~~

Một **partial index** chỉ lập chỉ mục các dòng thỏa điều kiện:

~~~sql
CREATE INDEX idx_orders_paid_created
ON public.orders (created_at)
WHERE status = 'PAID';
~~~

Đây là hai ví dụ **đặc thù PostgreSQL**. Dùng SQL trong changeset với dbms tương ứng khi change type chuẩn hoặc phiên bản Liquibase không hỗ trợ chính xác tính năng mong muốn:

~~~xml
<changeSet
    id="20261119-009-partial-paid-index"
    author="database-team"
    dbms="postgresql">
    <sql>
        CREATE INDEX idx_orders_paid_created
        ON public.orders (created_at)
        WHERE status = 'PAID';
    </sql>
    <rollback>
        <sql>DROP INDEX public.idx_orders_paid_created;</sql>
    </rollback>
</changeSet>
~~~

Các điểm cần thận trọng:

- Partial index chỉ hữu ích nếu điều kiện truy vấn giúp optimizer nhận ra phạm vi dữ liệu phù hợp; không phải mọi biểu thức tương đương về mặt logic đều được engine nhận ra như nhau.
- Index biểu thức có thể làm tăng chi phí ghi vì DBMS phải tính biểu thức khi duy trì index.
- Cú pháp, tính năng và chiến lược rollback cần được thử trên đúng PostgreSQL version.
- Các index hỗ trợ constraint không nên bị thay thế bằng partial index mà không xét lại quy tắc toàn vẹn dữ liệu.

## 9. Tạo index trên bảng lớn: CREATE INDEX CONCURRENTLY

Trên PostgreSQL, tạo index thông thường có thể gây ảnh hưởng đến thao tác ghi. Với bảng lớn và hệ thống vẫn đang nhận traffic, có thể cân nhắc **CREATE INDEX CONCURRENTLY** để giảm mức chặn ghi trong quá trình tạo.

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON public.orders (created_at);
~~~

Nhưng đây **không phải thao tác miễn phí**: nó thường tốn thời gian và I/O hơn, cần thêm các giai đoạn chờ transaction, vẫn dùng CPU, disk và có thể ảnh hưởng workload.

Một yêu cầu kỹ thuật quan trọng của PostgreSQL: CREATE INDEX CONCURRENTLY **không được chạy bên trong một transaction block**. Với Liquibase, có thể dùng SQL changeset và đặt runInTransaction=false khi runtime/DBMS phù hợp:

~~~xml
<changeSet
    id="20261119-010-idx-orders-created-concurrently"
    author="database-team"
    dbms="postgresql"
    runInTransaction="false">
    <sql>
        CREATE INDEX CONCURRENTLY idx_orders_created_at
        ON public.orders (created_at);
    </sql>
    <rollback>
        <sql>
            DROP INDEX CONCURRENTLY public.idx_orders_created_at;
        </sql>
    </rollback>
</changeSet>
~~~

**Những ràng buộc quan trọng:**

- Giữ changeset không transaction này tập trung vào thao tác cần thiết, tránh gộp các SQL không liên quan. Khi thất bại giữa chừng, thay đổi có thể không tự được rollback như một transaction nguyên tử.
- Với PostgreSQL, index build CONCURRENTLY thất bại có thể để lại index **INVALID**, vẫn chiếm dung lượng và có thể phát sinh chi phí duy trì. Cần kiểm tra và xử lý index invalid trước khi chạy lại.
- DROP INDEX CONCURRENTLY cũng có ràng buộc riêng, chẳng hạn không chạy trong transaction block và không thích hợp cho mọi loại index; rollback phải được thử trên môi trường riêng.
- Một số DBMS khác có cơ chế online index creation khác về cú pháp, lock và quyền; không sao chép nguyên cú pháp PostgreSQL sang MySQL/Oracle/SQL Server.
- Không mặc định createIndex cấu trúc của Liquibase sẽ tự chuyển thành CREATE INDEX CONCURRENTLY chỉ vì đang kết nối PostgreSQL.

### 9.1. Kiểm tra index INVALID trên PostgreSQL

Trong lab, có thể truy vấn metadata để nhận diện trạng thái index:

~~~sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisvalid AS is_valid,
    x.indisready AS is_ready
FROM pg_catalog.pg_index x
JOIN pg_catalog.pg_class i ON i.oid = x.indexrelid
JOIN pg_catalog.pg_class t ON t.oid = x.indrelid
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public'
  AND t.relname = 'orders'
ORDER BY i.relname;
~~~

Nếu index invalid, đừng giả định tên index đang tồn tại đồng nghĩa với migration thành công. Hãy kiểm tra log build, các transaction đang chạy, dung lượng đĩa và quy trình DROP/REINDEX phù hợp. Những hành động khắc phục phải được quản lý như một thay đổi có kiểm soát, không tự sửa bảng DATABASECHANGELOG.

## 10. Xóa index bằng dropIndex

Trong Liquibase, **dropIndex** dùng để xóa một index khi nó không còn cần thiết, đã được thay thế hoặc gây chi phí duy trì quá lớn.

Ví dụ XML:

~~~xml
<changeSet id="20261119-011-drop-old-index" author="database-team">
    <dropIndex
        tableName="orders"
        indexName="idx_orders_customer_id"/>
    <rollback>
        <createIndex
            tableName="orders"
            indexName="idx_orders_customer_id">
            <column name="customer_id"/>
        </createIndex>
    </rollback>
</changeSet>
~~~

Ví dụ YAML tương đương:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-011-drop-old-index
      author: database-team
      changes:
        - dropIndex:
            tableName: orders
            indexName: idx_orders_customer_id
      rollback:
        - createIndex:
            tableName: orders
            indexName: idx_orders_customer_id
            columns:
              - column:
                  name: customer_id
~~~

Đây là ví dụ giả định index cũ đúng là index thông thường trên customer_id, không phụ thuộc một constraint. Nếu index thực sự có nhiều cột, predicate hoặc thuộc tính đặc biệt, rollback tạo lại một index đơn cột **không tương đương**. Trước khi viết rollback, phải ghi nhận định nghĩa thực tế và tái tạo đầy đủ.

**Không trông chờ dropIndex có rollback tự động hoàn chỉnh.** Xóa index làm mất thông tin định nghĩa nếu không được lưu trong changelog và hệ thống version control. Với SQL index đặc thù, rollback thường phải dùng SQL đối ứng.

### 10.1. Không xóa index hỗ trợ constraint bằng thao tác tùy tiện

Nếu index do PRIMARY KEY hoặc UNIQUE constraint tạo ra/điều phối, thao tác dropIndex có thể bị DBMS từ chối hoặc làm mất tính toàn vẹn nếu xử lý sai. Khi mục tiêu là bỏ UNIQUE hoặc PRIMARY KEY, hãy dùng các change type **dropUniqueConstraint** hoặc **dropPrimaryKey** thích hợp, kiểm tra dependency và quy tắc dữ liệu thay vì coi đó chỉ là tối ưu hiệu năng.

Trước khi xóa, cần kiểm tra index có được dùng cho:

- Constraint bắt buộc hay không.
- Query quan trọng, JOIN hoặc ORDER BY nào.
- Khóa ngoại ở phía tham chiếu, thao tác DELETE/UPDATE của bảng cha.
- Tác vụ báo cáo, batch, job hoặc quy trình vận hành ít chạy nhưng quan trọng.

Index không xuất hiện trong thống kê sử dụng gần đây chưa chắc là index vô dụng: thống kê có thể bị reset, workload hiếm chưa chạy, hoặc optimizer chỉ dùng nó khi lượng dữ liệu/điều kiện thay đổi.

## 11. Precondition khi xóa index và rủi ro MARK_RAN

Có thể xác minh index tồn tại trước khi drop:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-012-drop-orders-old-index
      author: database-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - indexExists:
            tableName: orders
            indexName: idx_orders_customer_id
      changes:
        - dropIndex:
            tableName: orders
            indexName: idx_orders_customer_id
      rollback:
        - createIndex:
            tableName: orders
            indexName: idx_orders_customer_id
            columns:
              - column:
                  name: customer_id
~~~

Điều kiện này giúp báo lỗi rõ hơn khi migration kỳ vọng index hiện hữu nhưng database không có. Tuy nhiên chỉ kiểm tra tên index không bảo đảm nó đúng định nghĩa. Một index khác cùng tên hoặc khác schema có thể làm thay đổi ý nghĩa kiểm tra. Trên hệ thống nhiều schema, nên cung cấp schemaName và đối chiếu catalog thật.

**Không dùng onFail=MARK_RAN theo thói quen** để xử lý index vắng mặt trong production. Cần xác định nguyên nhân: index đã bị xóa thủ công, thay đổi trên một nhánh khác, deployment trước lỗi, hay database được baseline khác. Hành vi tiếp tục hay đồng bộ lịch sử phải được cân nhắc có chủ đích.

## 12. Thứ tự phụ thuộc: bảng, index, constraint và dữ liệu

Một trình tự triển khai điển hình:

~~~mermaid
flowchart TD
  A["Tạo bảng và cột"] --> B["Làm sạch/backfill dữ liệu"]
  B --> C["Tạo index phù hợp"]
  C --> D["Kiểm tra query plan và trạng thái index"]
  D --> E["Đưa thay đổi ứng dụng vào sử dụng"]
  E --> F["Đánh giá/xóa index cũ"]
~~~

Thứ tự này chỉ minh họa một chiến lược chuyển tiếp. Không phải migration nào cũng cần backfill trước tạo index hoặc đợi phát hành ứng dụng trước khi xóa index. Cần thiết kế theo dependency thực sự:

- Index phụ thuộc bảng và các cột đã tồn tại.
- Unique index phụ thuộc dữ liệu không vi phạm quy tắc uniqueness.
- Expression index phụ thuộc biểu thức/hàm/extension có sẵn và phù hợp.
- Ràng buộc khóa chính/unique và index hỗ trợ có thể ràng buộc nhau theo cách DBMS triển khai.
- Xóa index có thể ảnh hưởng performance của phiên bản ứng dụng chưa được nâng cấp.
- Với nhiều replica hoặc deployment cuốn chiếu, phiên bản ứng dụng cũ và mới có thể chạy đồng thời.

**Đừng thay đổi định nghĩa của một changeset đã chạy chỉ để “chèn thêm” index mới vào quá khứ.** Hãy thêm changeset tiếp nối lịch sử. Cả fresh install lẫn upgrade từ phiên bản trước đều phải cho schema cuối cùng đúng như thiết kế.

## 13. Đánh giá hiệu quả index bằng EXPLAIN và thống kê

Quyết định tạo/xóa index phải có bằng chứng từ truy vấn mục tiêu. Trên PostgreSQL, có thể xem kế hoạch truy vấn mà không thực thi nó bằng EXPLAIN:

~~~sql
EXPLAIN
SELECT id, status, created_at
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
~~~

Các tín hiệu quan sát:

1. DBMS có chọn Index Scan, Index Only Scan, Bitmap Index Scan hay Seq Scan không?
2. Ước lượng số hàng, chi phí và độ chọn lọc có phù hợp với dữ liệu không?
3. Có bước Sort lớn hay đọc nhiều row từ heap không?
4. Thời gian chạy thực tế có giảm trên tập dữ liệu đại diện không?
5. Khi index tồn tại, chi phí ghi, dung lượng đĩa và độ trễ replication thay đổi thế nào?

EXPLAIN **ANALYZE** thực sự chạy truy vấn trên PostgreSQL và cho thông tin thời gian thực tế, vì vậy phải cân nhắc tác động. Chỉ chạy với truy vấn/phạm vi được phép trên môi trường thử nghiệm hoặc trong kế hoạch quan sát được phê duyệt; không thực hiện bừa bãi trên production.

### 13.1. Kiểm tra catalog index trên PostgreSQL

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'orders'
ORDER BY indexname;
~~~

Truy vấn giúp so sánh tên, cột và định nghĩa SQL thực tế của index. Dùng nó để kiểm chứng sau tạo, đổi tên, thay cấu trúc hoặc xóa index.

Có thể quan sát kích thước index bằng một truy vấn tương ứng:

~~~sql
SELECT pg_size_pretty(
    pg_relation_size('public.idx_orders_customer_status'::regclass)
) AS index_size;
~~~

Truy vấn trên yêu cầu index có tên đó tồn tại. Kích thước index là một thước đo chi phí lưu trữ, không chứng minh index tốt hay xấu.

### 13.2. Thống kê sử dụng index

PostgreSQL có các view thống kê như pg_stat_user_indexes với trường idx_scan. Tuy nhiên, chỉ số có thể bị reset và không thể hiện đầy đủ các truy vấn hiếm, khác biệt thời gian hoặc lý do optimizer chọn index. Không quyết định dropIndex chỉ dựa vào “idx_scan bằng 0” trong một khoảng ngắn.

Dữ liệu benchmark cần gần với production về phân bố giá trị, dung lượng và truy vấn thật. Một index có lợi trên bảng hàng triệu dòng có thể bị optimizer bỏ qua trên bảng lab chỉ có vài chục dòng.

## 14. Mức độ rủi ro khi tạo, đổi hoặc xóa index

| Hoạt động | Rủi ro chính | Chiến lược giảm rủi ro |
|---|---|---|
| Tạo index thông thường | Build lâu, lock, I/O và thiếu dung lượng | Đo kích thước, chạy thử trên bảng lớn, chọn cửa sổ phù hợp |
| Tạo unique index | Dữ liệu trùng làm build thất bại | Kiểm tra và dọn dữ liệu trùng theo nghiệp vụ |
| Tạo index đồng thời | Build lâu hơn, có thể để lại INVALID index khi lỗi | runInTransaction=false khi cần, kiểm tra trạng thái catalog |
| Đổi tên index | Phụ thuộc theo tên, constraint liên quan | Xác minh loại index, cập nhật job/tool và chuẩn bị rollback |
| Thay định nghĩa index | Tăng tạm thời số index, rủi ro regression query plan | Tạo mới trước, đo đạc, xóa cũ ở bước sau |
| Xóa index | Query chậm, lock hoặc constraint bị ảnh hưởng | Kiểm tra workload, dependency và có cách tạo lại |
| Rollback tạo/xóa index | Không tái tạo đúng định nghĩa hoặc cần build lớn | Lưu DDL đầy đủ, thử rollback trên dữ liệu đại diện |

Lưu ý thêm dung lượng đĩa: trong giai đoạn chuyển tiếp giữa hai index, cả index cũ và index mới có thể cùng tồn tại. Cần dự trù storage, I/O, thời gian build và ảnh hưởng backup/replication, không chỉ tính dung lượng sau khi hoàn tất.

## 15. Spring Boot, nhiều môi trường và CI/CD

Liquibase thường được tích hợp cùng Spring Boot bằng dependency và cấu hình changelog, ví dụ:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.xml
~~~

Nếu changelog gốc dùng YAML thì đường dẫn phải trỏ tới tệp YAML tương ứng. Tệp master phải include các changeset index đúng thứ tự và được đóng gói vào artifact thực tế.

Trong hệ thống có nhiều replica hoặc nhiều pipeline, cần quyết định rõ **ai chạy migration**: một job riêng trước deployment hay ứng dụng chạy lúc startup. Bảng DATABASECHANGELOGLOCK giúp điều phối các tiến trình Liquibase, nhưng không giải quyết thay những rủi ro workload do build index. Đối với index lớn, tránh khởi chạy không dự kiến cùng thời điểm cao tải.

Pipeline CI/CD nên kiểm chứng:

1. Changelog hợp lệ và có đầy đủ dependency bảng/cột.
2. Danh sách changeset mới đúng với phiên bản phát hành.
3. SQL dự kiến phù hợp DBMS đích, nhất là SQL riêng như CONCURRENTLY.
4. Migration thành công trên database mới.
5. Upgrade thành công từ database đã có lịch sử và dữ liệu đại diện.
6. Catalog có index đúng tên, cột, thứ tự, tính unique và trạng thái hợp lệ.
7. Query plan/performance không suy giảm bất thường đối với workload mục tiêu.
8. Rollback hoặc forward-fix đã được thử trên database riêng.
9. Không có index thừa hoặc trạng thái INVALID còn sót sau lỗi.

### 15.1. Các lệnh Liquibase thường dùng

Với kết nối JDBC, driver và changelog đã được cấu hình:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
~~~

- **validate:** phát hiện những lỗi changelog mà runtime có thể kiểm tra.
- **status --verbose:** xem những changeset chưa được áp dụng.
- **update-sql:** xem trước SQL dự kiến để review.
- **update:** thực thi migration trên database đích; chỉ chạy khi đã xác minh đích.

Tên tùy chọn, cách chạy và hành vi kiểm chứng khác nhau theo phiên bản Liquibase. Việc preview SQL không thay thế phép thử build index trên dữ liệu gần production. Đặc biệt, SQL có CONCURRENTLY và runInTransaction=false phải được thử thực tế trên PostgreSQL với cấu hình giống pipeline.

## 16. Các lỗi thường gặp và cách điều tra

| Triệu chứng | Khả năng gây ra | Hướng xử lý |
|---|---|---|
| index already exists | Migration lặp, index tạo thủ công hoặc thay đổi path định danh | Kiểm tra pg_indexes và DATABASECHANGELOG, không tự MARK_RAN |
| column does not exist | Index chạy trước changeset tạo cột, hoặc sai schema | Kiểm tra dependency và tên schema/cột |
| Unique index build failed | Dữ liệu trùng theo khóa hoặc biểu thức | Truy vấn phát hiện trùng, xử lý dữ liệu theo nghiệp vụ |
| CREATE INDEX CONCURRENTLY cannot run inside a transaction block | Changeset đang chạy trong transaction | Xác minh runInTransaction=false và cách runtime thực thi |
| Index mang tên dự kiến nhưng không được planner dùng | Query không phù hợp cột/biểu thức, thống kê hoặc tính chọn lọc | EXPLAIN, thử workload, kiểm tra index definition và validity |
| Index vẫn tồn tại nhưng không hợp lệ | Concurrent build thất bại hoặc thao tác chưa hoàn tất | Kiểm tra pg_index, xử lý index INVALID theo quy trình |
| DROP INDEX thất bại do dependency | Index hỗ trợ constraint hoặc đối tượng phụ thuộc | Xác minh constraint, dùng change type/lệnh phù hợp |
| Rollback không tạo lại đúng index | Rollback thiếu cột, predicate hoặc unique flag | Lưu đầy đủ định nghĩa trước khi xóa |
| Prod chậm sau khi xóa index | Workload thực tế khác lab hoặc index phục vụ truy vấn ít chạy | Dùng query telemetry và kế hoạch khôi phục index |
| Checksum mismatch | Changeset đã triển khai bị sửa | Không sửa lịch sử tùy tiện; thêm changeset mới |
| Build index làm chậm ứng dụng | I/O, lock, CPU, dung lượng hoặc transaction dài | Thử chiến lược online và lên lịch triển khai phù hợp |

Khi điều tra, đi theo thứ tự: **tình trạng DATABASECHANGELOG → định nghĩa index thực tế → quyền/DBMS → câu SQL migration → query plan và tải hệ thống**. Không xử lý lỗi bằng cách xóa bảng lịch sử, đặt lại checksum hoặc sửa dữ liệu production khi chưa xác định nguyên nhân.

## 17. Bài thực hành: vòng đời index có kiểm chứng

Chuẩn bị PostgreSQL lab có bảng orders với các cột id, customer_id, status và created_at, đồng thời có dữ liệu thử đủ để quan sát query plan.

**Phần A — Tạo index:** Viết changeset Liquibase tạo idx_orders_customer_id. Thêm precondition kiểm tra bảng/cột có và index chưa tồn tại. Chạy validate, status, update-sql rồi update trên lab. Xác minh tên và định nghĩa trong pg_indexes.

**Phần B — Composite index:** Viết một changeset mới tạo idx_orders_customer_status với thứ tự (customer_id, status). So sánh EXPLAIN trước/sau cho ít nhất hai truy vấn khác nhau. Giải thích tại sao composite index không tự động tối ưu cho mọi điều kiện WHERE.

**Phần C — Đổi tên:** Trên bản sao lab, thử đổi tên một index thông thường bằng ALTER INDEX ... RENAME TO trong changeset PostgreSQL. Viết rollback đổi tên về giá trị ban đầu. Kiểm tra rằng thao tác không làm thay đổi cột/index definition và xác minh các đối tượng bên ngoài tham chiếu tên cũ.

**Phần D — Thay cấu trúc:** Tạo index mới trước khi xóa index cũ, ghi lại kích thước và kế hoạch truy vấn. Không sửa changeset tạo index cũ. Tách bước xóa cũ thành một thay đổi tiếp theo sau khi kết quả đã được xác nhận.

**Phần E — Concurrent index:** Trên bảng đủ lớn trong lab, thử tạo index bằng CREATE INDEX CONCURRENTLY với runInTransaction=false. Quan sát thời gian, trạng thái valid/invalid và hành vi khi lỗi. Không thử tạo index đồng thời trên production chỉ để học.

**Phần F — Xóa và rollback:** Xóa một index thường không liên quan constraint bằng dropIndex, kiểm tra pg_indexes; rollback trong lab để tạo lại index với **đúng định nghĩa ban đầu**. Không xóa index gắn với PRIMARY KEY/UNIQUE constraint trong bài thử này.

**Phần G — Nâng cấp:** Thử cùng bộ changelog trên database mới và database đã chạy bản trước. Xác nhận những changeset cũ không bị nhận diện lại do đổi tên tệp và schema đích cuối cùng phù hợp thiết kế.

## 18. Checklist trước khi merge migration index

| Câu hỏi kiểm tra | Bằng chứng cần có |
|---|---|
| Index giải quyết truy vấn nào? | Query thực tế và EXPLAIN/benchmark |
| Index có bị trùng với index/constraint hiện có? | Danh sách index, primary/unique constraints |
| Tên, schema và thứ tự cột đúng không? | Định nghĩa createIndex hoặc SQL đã review |
| Unique index có dữ liệu vi phạm không? | Kiểm tra trùng trước khi build |
| Changeset có ID/author/path ổn định? | Không sửa lịch sử đã deploy |
| Precondition xác nhận đúng trạng thái tiền đề? | Kiểm thử trường hợp đạt, không đạt và lỗi |
| Build có ảnh hưởng đến lock, disk, I/O, traffic không? | Kết quả thử trên dữ liệu đại diện |
| SQL đặc thù có đúng DBMS/transaction không? | Kiểm thử CONCURRENTLY/runInTransaction nếu dùng |
| Thay đổi cấu trúc có cần giai đoạn chuyển tiếp? | Kế hoạch tạo mới, xác minh rồi xóa cũ |
| Index đang gắn constraint hoặc dependency không? | Kiểm tra catalog và schema thực tế |
| Rollback/forward-fix tái tạo đúng index không? | Định nghĩa đầy đủ và bài thử phục hồi |
| Fresh install và upgrade đều đúng? | Kết quả CI/CD ở hai trạng thái database |
| Sau chạy đã kiểm tra validity và query plan? | pg_indexes, pg_index và kiểm tra hiệu năng |

**Nguyên tắc cuối cùng:** tạo index vì có bằng chứng về lợi ích, thay đổi index bằng changeset mới thay vì sửa lịch sử cũ, và chỉ xóa index sau khi kiểm chứng dependency cùng ảnh hưởng truy vấn. Liquibase giúp tổ chức và truy vết những thao tác đó, nhưng độ an toàn vận hành đến từ việc hiểu DBMS, đo hiệu năng, quản lý rollback và kiểm thử trên database mới lẫn database đã có dữ liệu.

