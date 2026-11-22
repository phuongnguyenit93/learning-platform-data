# Viết rollback cho formatted SQL và sqlFile

Một migration thành công không chỉ cần mô tả **đưa database từ trạng thái A sang B**, mà còn phải trả lời: nếu cần hủy phát hành, **bước nào có thể đưa database trở về trạng thái trước đó mà không gây mất dữ liệu hoặc phá vỡ phiên bản ứng dụng đang chạy?** Với Liquibase, câu trả lời này phụ thuộc loại change, khả năng transaction của DBMS và **cách bạn khai báo rollback trong changelog**. Đặc biệt, SQL viết tay bằng *formatted SQL* hoặc nạp qua *sqlFile* không thể được coi là có rollback tự động chỉ vì Liquibase quản lý lịch sử.

Bài thuộc chương **Hoàn tác** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu toàn module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Nội dung ở đây tập trung vào **hai cách viết rollback cho SQL tùy chỉnh**: chỉ thị `--rollback` trong formatted SQL changelog, và phần tử `rollback` trỏ tới `sqlFile` tương ứng trong changelog XML/YAML. Sau khi học, người đọc có thể chọn cách triển khai phù hợp, viết ví dụ chạy được trong phòng lab và biết giới hạn vận hành của rollback.

## 1. Hiểu đúng rollback: thao tác kỹ thuật và kết quả nghiệp vụ

**Rollback** trong Liquibase là việc thực thi phần thay đổi đảo ngược tương ứng với một hoặc nhiều changeset đã được ghi nhận, theo phạm vi chọn bằng count, tag hoặc ngày (tùy lệnh và phiên bản). Liquibase dựa vào lịch sử trong **DATABASECHANGELOG** để xác định changeset nào đã thực thi, chứ không tự suy luận từ trạng thái bảng hiện có rằng cần đảo ngược SQL như thế nào.

Ví dụ:

~~~text
Trước migration
  bảng orders không có index idx_orders_created_at

Sau migration
  index idx_orders_created_at tồn tại

Rollback mong muốn
  index vừa tạo bị xóa, các bản ghi orders không đổi
~~~

Trường hợp này khá dễ đảo ngược. Nhưng giả sử migration là:

~~~sql
UPDATE orders SET status = 'CANCELLED' WHERE status = 'PENDING';
~~~

Một rollback đơn giản đổi CANCELLED thành PENDING sẽ **sai** nếu có những dòng đã là CANCELLED từ trước, hoặc trạng thái đã bị ứng dụng thay đổi sau migration. Với thay đổi dữ liệu, “viết câu SQL ngược” không đồng nghĩa “khôi phục đúng dữ liệu gốc”.

| Tình huống | Có thể rollback bằng SQL đơn giản? | Rủi ro chính |
|---|---|---|
| CREATE INDEX thường | Thường có thể DROP INDEX | Lock, truy vấn trở nên chậm, index hỗ trợ constraint |
| ADD COLUMN mới chưa có dữ liệu | Có thể DROP COLUMN về cấu trúc | Mất dữ liệu phát sinh ở cột sau deploy |
| CREATE VIEW mới | Có thể DROP VIEW | Dependency từ view khác hoặc ứng dụng |
| CREATE OR REPLACE VIEW cũ | Phải phục hồi **định nghĩa cũ**, không chỉ DROP | Mất view phục vụ phiên bản ứng dụng trước |
| INSERT dữ liệu danh mục | Có thể DELETE những khóa mới nếu an toàn | Khóa ngoại và thay đổi nghiệp vụ phát sinh |
| UPDATE/DELETE dữ liệu hàng loạt | Thường cần snapshot, bảng lịch sử hoặc forward-fix | Không khôi phục được thông tin đã ghi đè |
| DROP TABLE hoặc DROP COLUMN | Không thể phục hồi dữ liệu chỉ bằng CREATE lại | Mất dữ liệu, index, constraint và quan hệ |

**Nguyên tắc:** thiết kế rollback dựa trên trạng thái cần khôi phục và dữ liệu thực, không chỉ dựa trên cú pháp SQL đối xứng.

## 2. Formatted SQL và sqlFile là hai cơ chế khác nhau

Hai cách đều cho phép viết SQL trực tiếp, nhưng Liquibase phân tích chúng khác nhau.

| Khía cạnh | Formatted SQL changelog | sqlFile change type |
|---|---|---|
| Tệp chính | Một tệp `.sql` với header `--liquibase formatted sql` và các chỉ thị changeset | Changelog XML/YAML/JSON khai báo change type `sqlFile` |
| Ranh giới changeset | Dòng `--changeset author:id` bên trong tệp SQL | Phần tử `changeSet` của changelog cha |
| SQL tiến | Viết ngay sau chỉ thị changeset | Đọc từ đường dẫn `path` đã khai báo |
| Rollback tùy chỉnh | Chỉ thị `--rollback` ở trong chính changeset formatted SQL | Phần `rollback` bên trong changeSet, có thể chứa `sqlFile` trỏ tệp SQL đảo ngược |
| Path/encoding | Tệp formatted SQL phải được Liquibase nhận diện là changelog | Chú ý `path`, `relativeToChangelogFile`, `encoding` và packaging |
| Lỗi dễ nhầm | Viết `--rollback` như comment SQL thường, thiếu header hoặc sai vị trí | Tưởng rằng Liquibase tự suy ra SQL đảo ngược hoặc đọc `--rollback` bên trong file SQL thô |

Sơ đồ:

~~~mermaid
flowchart LR
  A["Formatted SQL .sql"] --> B["--changeset"]
  B --> C["SQL thực thi"]
  B --> D["--rollback SQL đảo ngược"]
  E["Changelog XML/YAML"] --> F["changeSet"]
  F --> G["sqlFile: forward.sql"]
  F --> H["rollback / sqlFile: rollback.sql"]
~~~

**Điểm rất quan trọng:** một file SQL được **sqlFile** nạp như nội dung SQL thông thường **không tự trở thành formatted SQL changelog** chỉ vì có các dòng comment kiểu `--rollback`. Muốn Liquibase quản lý rollback cho sqlFile, phải khai báo nó ở cấu trúc rollback của changeset trong changelog cha.

## 3. Cú pháp tối thiểu: rollback trong formatted SQL

Tệp SQL cần mở đầu bằng header nhận diện và chỉ thị changeset:

~~~sql
--liquibase formatted sql

--changeset database-team:20261119-001-create-status-table
CREATE TABLE status_code (
    code VARCHAR(24) PRIMARY KEY,
    description VARCHAR(120) NOT NULL
);

--rollback DROP TABLE status_code;
~~~

Cách hiểu:

1. `--liquibase formatted sql` thông báo tệp được phân tích theo định dạng changelog SQL của Liquibase.
2. `--changeset database-team:20261119-001-create-status-table` bắt đầu changeset có author và id ổn định.
3. `CREATE TABLE ...` là SQL hướng tiến (*forward SQL*).
4. `--rollback DROP TABLE status_code;` là **chỉ thị metadata rollback**, không phải câu lệnh được thực thi trong lần `update` bình thường.
5. Khi yêu cầu rollback tới phạm vi chứa changeset này, Liquibase sử dụng lệnh `DROP TABLE` đã khai báo.

**Cảnh báo:** ví dụ này hợp lý cho phòng lab hoặc khi bảng chưa chứa dữ liệu thực. Nếu status_code được hệ thống sử dụng và đã có bản ghi hoặc FK tham chiếu, DROP TABLE có thể không chạy được hoặc gây mất dữ liệu. Việc có một chỉ thị rollback hợp lệ về cú pháp không có nghĩa nó an toàn trên production.

### 3.1. Các dấu hiệu để Liquibase nhận đúng rollback

- Tệp phải là **formatted SQL changelog**, không chỉ là SQL thuần.
- Chỉ thị `--rollback` phải nằm trong đúng changeset cần đảo ngược.
- Tên directive và định dạng comment phải đúng với phiên bản Liquibase được dùng.
- Nếu rollback là một câu SQL, nên biểu diễn rõ ràng và có dấu kết thúc câu theo cấu hình delimiter.
- Đừng ghi rollback như một câu SQL tiến bình thường ở dưới cùng tệp: khi đó nó có thể được chạy ngay lúc `update`, vô tình hoàn tác thay đổi vừa thực hiện.

Ví dụ **sai**:

~~~sql
--liquibase formatted sql

--changeset team:wrong-example
CREATE TABLE status_code (code VARCHAR(24) PRIMARY KEY);
DROP TABLE status_code;
~~~

Câu DROP ở đây không được đánh dấu là rollback; nó thuộc SQL hướng tiến. Tránh kiểu viết này.

## 4. Rollback nhiều câu SQL trong một changeset formatted SQL

Nếu một changeset gồm hai thao tác độc lập, rollback phải đảo theo **thứ tự ngược với phụ thuộc**. Ví dụ PostgreSQL:

~~~sql
--liquibase formatted sql

--changeset database-team:20261119-002-create-audit-objects
CREATE TABLE audit_event (
    id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL
);
CREATE INDEX idx_audit_event_created ON audit_event (created_at);

--rollback DROP INDEX idx_audit_event_created;
--rollback DROP TABLE audit_event;
~~~

Khi rollback, cần xóa index trước rồi mới xóa bảng. Nhiều dòng `--rollback` giúp khai báo các câu đảo ngược riêng, rõ ràng; hãy dùng dạng mỗi chỉ thị chứa một câu SQL hoàn chỉnh để tránh mơ hồ giữa newline và statement delimiter.

Ví dụ này vẫn có rủi ro xóa dữ liệu nếu bảng audit_event đã nhận bản ghi trong thời gian ứng dụng chạy. Trên production, nên cân nhắc **tách changeset tạo bảng và changeset tạo index**, bởi khi đó có thể rollback index mà không xóa bảng.

### 4.1. Một changeset hay nhiều changeset?

| Cách tổ chức | Ưu điểm | Bất lợi |
|---|---|---|
| Một changeset chứa nhiều SQL | Gọn, phù hợp thao tác thực sự phải là một đơn vị | Rollback khó tách, nhất là khi DBMS không rollback được toàn bộ DDL |
| Mỗi changeset một trách nhiệm | Dễ review, test, rollback chọn lọc theo thứ tự | Nhiều ID và nhiều file/khối hơn |
| Chia thành giai đoạn expand/migrate/contract | Phù hợp hệ thống có dữ liệu và deploy cuốn chiếu | Cần điều phối ứng dụng và triển khai nhiều đợt |

Thường ưu tiên changeset nhỏ và rõ. Không ép một migration dữ liệu dài cùng thao tác DROP COLUMN vào một changeset chỉ vì SQL viết dễ.

## 5. Ví dụ an toàn hơn: rollback CREATE VIEW

Giả sử bảng customer đã tồn tại và ta tạo **một view mới** để ứng dụng đọc danh sách khách hàng đang hoạt động:

~~~sql
--liquibase formatted sql

--changeset database-team:20261119-003-create-active-customers-view dbms:postgresql
CREATE VIEW active_customers AS
SELECT id, email
FROM customer
WHERE active = TRUE;

--rollback DROP VIEW active_customers;
~~~

Trường hợp này thường dễ rollback hơn việc DROP TABLE, miễn là không có view hoặc chức năng khác đã phụ thuộc active_customers. Chỉ thị `dbms:postgresql` trong header changeset thể hiện tập DBMS dự kiến; cần kiểm tra cú pháp thuộc tính theo phiên bản Liquibase và SQL trên DBMS thực tế.

### 5.1. Đổi định nghĩa view cũ phải phục hồi định nghĩa cũ

Nếu view đã tồn tại rồi ta viết:

~~~sql
CREATE OR REPLACE VIEW active_customers AS
SELECT id, email, status
FROM customer
WHERE active = TRUE;
~~~

Rollback bằng `DROP VIEW active_customers` thường **không đúng**: trước migration view đã tồn tại. Muốn khôi phục schema trước đó, rollback phải tạo lại đúng định nghĩa view cũ, đồng thời xét dependency và phiên bản PostgreSQL. Nếu SQL `CREATE OR REPLACE VIEW` không được DBMS cho phép khi thay đổi danh sách cột theo cách đó, phải thiết kế migration khác.

Trước khi viết rollback dạng `CREATE OR REPLACE VIEW`, ghi lại **định nghĩa đã được quản lý trong source control** ở phiên bản trước. Không giả định có thể đọc định nghĩa cũ sau khi migration đã thay thế mà không có bản lưu.

## 6. sqlFile: tách SQL tiến ra khỏi changelog

Khi SQL dài hoặc cần tận dụng cú pháp đặc thù DBMS, có thể dùng **sqlFile** bên trong một changeset XML/YAML, trong khi SQL thật nằm ở một tệp khác.

Ví dụ cấu trúc tài nguyên (chỉ minh họa, không yêu cầu tạo các tệp này trong bài hiện tại):

~~~text
src/main/resources/db/changelog/
├── master.yaml
├── changes/
│   └── 20261119-order-index.yaml
└── sql/
    ├── 20261119-create-order-index.sql
    └── 20261119-drop-order-index.sql
~~~

Tệp SQL hướng tiến:

~~~sql
-- 20261119-create-order-index.sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
~~~

Tệp SQL đảo ngược:

~~~sql
-- 20261119-drop-order-index.sql
DROP INDEX idx_orders_customer_created;
~~~

Đối với PostgreSQL, hai câu trên minh họa một index độc lập, không phải index được DBMS sử dụng để duy trì constraint. Việc DROP INDEX vẫn có thể tác động hiệu năng; cần kiểm tra các truy vấn mục tiêu trước khi rollback.

**Không cần đặt header `--liquibase formatted sql` trong các file được nạp qua sqlFile như ví dụ này.** Chúng là nội dung SQL cho change type, còn ID/author/rollback nằm trong changelog cha.

## 7. Khai báo sqlFile và rollback bằng YAML

Tệp `changes/20261119-order-index.yaml` có thể chứa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-004-create-order-index
      author: database-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - columnExists:
            tableName: orders
            columnName: customer_id
        - columnExists:
            tableName: orders
            columnName: created_at
      changes:
        - sqlFile:
            path: ../sql/20261119-create-order-index.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
            endDelimiter: ";"
            stripComments: false
      rollback:
        - sqlFile:
            path: ../sql/20261119-drop-order-index.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
            endDelimiter: ";"
            stripComments: false
~~~

**Giải thích:**

- `changes` chứa SQL tiến; `rollback` chứa SQL đảo ngược.
- Cả hai cùng nằm trong **một changeSet** nên lịch sử rollback gắn với changeset đã triển khai.
- `path` trỏ đúng file SQL; vì changelog nằm trong thư mục changes, `../sql/...` đi lên một cấp rồi vào sql.
- `relativeToChangelogFile: true` khiến đường dẫn được giải tương đối so với **changelog chứa sqlFile**, không phải theo thư mục terminal đang chạy.
- `encoding: UTF-8` yêu cầu tệp SQL được lưu theo đúng mã hóa đã chọn.
- `splitStatements` và `endDelimiter` điều khiển cách chia nội dung thành các câu SQL; trong ví dụ mỗi file chỉ có một câu kết thúc bằng dấu chấm phẩy.
- `stripComments` quyết định việc loại bỏ comment SQL trong những trường hợp được hỗ trợ; không nên sử dụng các comment chứa directive rollback như thể chúng là changelog metadata.

**Lưu ý phiên bản:** các thuộc tính và chi tiết hành vi parser cần được kiểm tra với Liquibase runtime cụ thể. `sqlFile` không hứa hẹn biến mọi SQL phức tạp thành các câu lệnh có thể tách bằng dấu chấm phẩy một cách an toàn.

### 7.1. Changelog gốc include changeset

Một master YAML có thể tham chiếu changelog con:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/20261119-order-index.yaml
      relativeToChangelogFile: true
~~~

Cần đảm bảo bảng orders và các cột được tạo bởi changeset tiền đề trước khi changeset index được xử lý. Liquibase thực hiện các changeset theo thứ tự changelog; nó không tự suy luận dependency từ tên tệp SQL.

## 8. Tương đương bằng XML: rollback chứa sqlFile

Nếu hệ thống chuẩn hóa changelog theo XML, có thể khai báo như sau:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      http://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet
        id="20261119-004-create-order-index"
        author="database-team"
        dbms="postgresql">

        <sqlFile
            path="../sql/20261119-create-order-index.sql"
            relativeToChangelogFile="true"
            encoding="UTF-8"
            splitStatements="true"
            endDelimiter=";"
            stripComments="false"/>

        <rollback>
            <sqlFile
                path="../sql/20261119-drop-order-index.sql"
                relativeToChangelogFile="true"
                encoding="UTF-8"
                splitStatements="true"
                endDelimiter=";"
                stripComments="false"/>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

Trong XML, `<rollback>` bao thay đổi đảo ngược; `<sqlFile>` bên trong nó đọc file SQL tương ứng khi rollback. Phần SQL đảo ngược được chọn theo changeset, **không phải** vì tên file chứa chữ “drop” hoặc “rollback”.

So sánh hai định dạng:

| Hạng mục | Formatted SQL | sqlFile trong XML/YAML |
|---|---|---|
| Nơi đặt rollback | Các dòng `--rollback` | `rollback:` hoặc `<rollback>` |
| SQL tiến | Trong chính formatted changelog | Trong file được `sqlFile.path` trỏ đến |
| SQL đảo ngược | Trong chính formatted changelog | Có thể là một sqlFile riêng |
| Review | Một tệp cho tiến và lùi | Cần review cả changelog, file tiến và file rollback |
| Sai sót dễ gặp | Thiếu directive/đặt sai changeset | Sai đường dẫn hoặc không đóng gói rollback SQL |

Với SQL rất dài, tách thành hai file giúp dễ xem diff và dùng công cụ SQL chuyên biệt. Nhưng số file nhiều hơn đồng nghĩa phải kiểm tra kỹ việc đóng gói và bất biến của từng tài nguyên.

## 9. Không trộn cơ chế formatted SQL và sqlFile một cách tùy tiện

Một nhầm lẫn phổ biến là tạo file `create.sql` như sau:

~~~sql
--liquibase formatted sql

--changeset team:001
CREATE TABLE example_table (id BIGINT PRIMARY KEY);

--rollback DROP TABLE example_table;
~~~

sau đó nạp file ấy qua `sqlFile` của một changeset YAML khác và cho rằng chỉ thị `--rollback` bên trong sẽ được hiểu như metadata của changeset cha.

Đây là cách thiết kế **không nên dùng**. Chỉ thị formatted SQL có ý nghĩa khi file được xử lý như **formatted SQL changelog**. Nếu file được dùng như SQL thô qua `sqlFile`, phải khai báo rollback ở changeset cha; các dòng comment trong file SQL không thay thế phần rollback chính thức.

Chọn **một trong hai hướng**:

1. Dùng `--liquibase formatted sql` và `--changeset` trực tiếp trong một changelog SQL, kèm chỉ thị `--rollback`.
2. Dùng changelog XML/YAML chứa `sqlFile` cho SQL tiến và phần `rollback` trỏ SQL đảo ngược.

Nếu một dự án có cả hai kiểu, vẫn nên dùng quy ước nhất quán và thử parser đúng phiên bản Liquibase; không đổi cơ chế cho một changeset đã deploy.

## 10. endDelimiter, splitStatements và SQL thủ tục phức tạp

Một tệp SQL có nhiều câu thường được tách bằng dấu `;`. Tuy nhiên, SQL có thủ tục, trigger, DO block hoặc PL/SQL có thể **chứa dấu chấm phẩy bên trong thân lệnh**. Tách mọi dấu chấm phẩy thành ranh giới câu lệnh sẽ làm SQL sai.

Ví dụ PostgreSQL:

~~~sql
DO $$
BEGIN
    RAISE NOTICE 'Start';
    RAISE NOTICE 'Done';
END
$$;
~~~

Nếu dùng một `sqlFile` chứa khối đó, cần cấu hình cách chia câu lệnh tương thích với SQL/DBMS và phiên bản Liquibase. Đối với file chỉ chứa một đơn vị SQL phức tạp, `splitStatements: false` có thể phù hợp hơn so với tách dấu chấm phẩy. Trường hợp có nhiều block, phải xây dựng quy tắc delimiter riêng và kiểm thử.

Các hệ quản trị cũng có cơ chế khác nhau:

- PostgreSQL có dollar-quoted body và các lệnh như `CREATE INDEX CONCURRENTLY` với hạn chế transaction.
- Oracle có PL/SQL block và quy ước kết thúc trong các công cụ SQL riêng.
- SQL Server thường dùng `GO` trong script, nhưng đây là batch separator của công cụ, không phải câu lệnh T-SQL thông thường.

Không mặc định cùng một `endDelimiter` và `splitStatements` chạy đúng trên mọi DBMS. Rollback file cũng cần được thử với cấu hình parser **của chính nó**.

### 10.1. Comment và encoding

Nếu giữ comment trong SQL, hãy xác định chúng có ảnh hưởng đến parser/delimiter hoặc SQL native hay không. SQL file có ký tự tiếng Việt nên dùng UTF-8 nhất quán; không thay encoding mà không kiểm tra.

Không đưa passwords, token, thông tin khách hàng thật hoặc JDBC URL có credentials vào SQL script/rollback file. Changelog và artifact thường được phát hành cho nhiều môi trường và nằm trong hệ thống log/build.

## 11. runInTransaction và rollback khi DBMS không cho giao dịch

Theo cấu hình thông thường, Liquibase cố chạy changeset trong transaction khi DBMS hỗ trợ. Nhưng không phải mọi DDL đều rollback được, và một số thao tác **bị cấm trong transaction block**.

Ví dụ PostgreSQL: `CREATE INDEX CONCURRENTLY` không được thực thi trong transaction block. Một changeset SQL riêng theo DBMS có thể dùng `runInTransaction:false`.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-005-create-index-concurrently
      author: database-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sqlFile:
            path: ../sql/create-index-concurrently.sql
            relativeToChangelogFile: true
            splitStatements: false
      rollback:
        - sqlFile:
            path: ../sql/drop-index-concurrently.sql
            relativeToChangelogFile: true
            splitStatements: false
~~~

Ví dụ SQL tiến:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_at
ON orders (created_at);
~~~

Ví dụ rollback:

~~~sql
DROP INDEX CONCURRENTLY idx_orders_created_at;
~~~

**Các điều kiện bắt buộc xem xét:**

- Trong PostgreSQL, `CREATE INDEX CONCURRENTLY` và `DROP INDEX CONCURRENTLY` có ràng buộc transaction, dependency và loại index; không coi ví dụ là áp dụng cho mọi index.
- Nếu index concurrently thất bại, PostgreSQL có thể để lại index **INVALID**. Việc index có tên đúng không chứng minh nó đã build thành công.
- `runInTransaction:false` làm giảm khả năng Liquibase bảo đảm thay đổi và lịch sử được ghi nhận như một đơn vị nguyên tử. Nếu process chết sau khi DDL thực hiện nhưng trước khi ghi nhận changeset, lần chạy lại có thể gặp index đã tồn tại.
- Rollback nên là một thao tác có thể giám sát, kiểm thử trên database giống production về dữ liệu và tải; không chỉ dựa vào cú pháp DROP đối xứng.

Không gộp hàng chục câu SQL không liên quan vào changeset `runInTransaction:false`, nhất là khi giữa chúng có thể xảy ra lỗi để lại trạng thái nửa hoàn tất.

## 12. Rollback dữ liệu: phân biệt xóa dữ liệu do migration với khôi phục trạng thái cũ

Rollback phần dữ liệu thường khó hơn schema. Giả sử migration thêm các mã trạng thái tham chiếu:

~~~sql
INSERT INTO status_code (code, description)
VALUES ('APPROVED', 'Approved'), ('REJECTED', 'Rejected');
~~~

Một rollback có thể được thiết kế:

~~~sql
DELETE FROM status_code
WHERE code IN ('APPROVED', 'REJECTED');
~~~

Nhưng chỉ an toàn khi hai mã này **thực sự do migration tạo**, không có tham chiếu nghiệp vụ hoặc dữ liệu phát sinh cần giữ. Nếu bảng order_state đã tham chiếu các mã đó, DELETE có thể bị foreign key từ chối hoặc gây mất dữ liệu khi có cascade.

Với dữ liệu UPDATE, muốn phục hồi đúng cần biết **giá trị trước migration của từng hàng**. Có vài cách:

- Lưu dữ liệu trước thay đổi vào bảng backup/staging riêng theo quy trình được phê duyệt.
- Sử dụng data migration có bước forward-fix thay vì rollback trực tiếp.
- Thực hiện restore từ backup/snapshot khi nghiệp vụ và thời gian khôi phục cho phép.
- Áp dụng expand–migrate–contract để tránh biến đổi không thể đảo ngược trong một lần deploy.

### 12.1. Phép đảo ngược toán học không đủ

Ví dụ SQL hướng tiến:

~~~sql
UPDATE product
SET price = ROUND(price * 1.1, 2)
WHERE category = 'A';
~~~

Không thể đảm bảo rollback bằng `price / 1.1` vì làm tròn đã mất thông tin, và giá có thể được cập nhật bởi ứng dụng sau triển khai. Với DELETE dữ liệu, nếu không giữ bản sao thông tin đã xóa thì một câu INSERT với giá trị đoán trước không khôi phục được bản ghi thật.

**Rollback có thể là “không thể hoàn tác an toàn”**. Đó là thông tin quan trọng phải được ghi trong phương án release; không nên bịa một câu rollback chỉ để đánh dấu có hỗ trợ.

## 13. Precondition có vai trò gì khi rollback?

Precondition thường bảo vệ **chiều update** của changeset, ví dụ yêu cầu index chưa tồn tại trước khi CREATE INDEX. Nhưng ở chiều rollback, điều kiện mong muốn có thể ngược lại: index **phải đang tồn tại** trước khi DROP INDEX.

Không nên mặc định precondition ở chiều tiến sẽ kiểm tra đầy đủ an toàn cho chiều ngược. Khi rollback có rủi ro, kiểm tra riêng trạng thái DB ở preflight ngoài changeset (SQL chỉ đọc hoặc bước CI có kiểm soát), đối chiếu dependency và bản ghi lịch sử.

Ví dụ trước khi rollback một changeset index, kiểm tra PostgreSQL catalog:

~~~sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname = 'idx_orders_customer_created';
~~~

Kết quả giúp xác minh index tồn tại, nhưng còn cần biết nó có gắn constraint hoặc được query quan trọng sử dụng không. Đừng giải phóng Liquibase lock hay xóa DATABASECHANGELOG để ép rollback.

**Rollback là hành động chọn lịch sử changeset**, không phải câu lệnh tự ý “đưa về bản trước” dựa trên một kiểm tra metadata duy nhất.

## 14. Chọn phạm vi rollback và xem trước SQL

Liquibase cung cấp các lệnh rollback theo **số changeset**, **tag** hoặc **thời điểm**, với cú pháp CLI phụ thuộc phiên bản. Để luyện tập an toàn, có thể dùng phạm vi số changeset trên database lab.

Ví dụ khi đã cấu hình changelog, JDBC driver, URL và user:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update
liquibase rollback-count-sql --count=1
~~~

Sau khi đọc kỹ SQL đảo ngược, chỉ trên **database lab đã được xác nhận đích**, thực hiện:

~~~bash
liquibase rollback-count --count=1
~~~

Ý nghĩa:

1. `validate` phát hiện một số lỗi changelog và cấu hình; không chứng minh SQL đảo ngược hoạt động trên dữ liệu thật.
2. `status --verbose` cho thấy các changeset chờ chạy, không phải bản thay thế lịch sử rollback.
3. `update` áp migration thực tế.
4. `rollback-count-sql` hiển thị SQL dự kiến để rollback một changeset gần nhất trong phạm vi lệnh.
5. `rollback-count` thực thi rollback trên database đã cấu hình.

Cách viết các tham số có thể khác giữa các phiên bản Liquibase CLI; cần kiểm tra `help` của runtime đang chạy. Với production, thông thường nên gắn **tag phát hành đã có chủ đích** và chọn phạm vi rollback dựa trên lịch sử thật, không mặc định “count=1” luôn là đúng changeset cần hủy.

### 14.1. Cảnh báo: thứ tự chạy rollback

Liquibase rollback các changeset đã chọn theo **thứ tự ngược với thứ tự áp dụng**. Nếu chuỗi:

~~~text
001: CREATE TABLE customer
002: CREATE INDEX idx_customer_email
003: CREATE VIEW active_customers
~~~

đã chạy đầy đủ, khi rollback cả ba, thứ tự hợp lý là:

~~~text
003: DROP VIEW active_customers
002: DROP INDEX idx_customer_email
001: DROP TABLE customer
~~~

Tuy vậy, trong **một changeset** chứa nhiều câu SQL, bạn vẫn phải viết rollback có thứ tự đúng; đừng giả định Liquibase tự suy diễn phụ thuộc giữa từng dòng SQL viết tay.

## 15. Cần kiểm tra gì trước khi rollback thật?

| Câu hỏi | Vì sao quan trọng |
|---|---|
| Database đích, schema và account đúng chưa? | Tránh rollback nhầm staging/production |
| Changelog artifact và đường dẫn đúng phiên bản? | Tránh chọn nhầm changeset hoặc logic khác lịch sử |
| Phạm vi tag/count/date đã được đối chiếu? | Tránh xóa nhiều thay đổi hơn dự định |
| SQL rollback có thể được parse bởi runtime thật? | Delimiter, PL/SQL/DO block, encoding có thể khác |
| Có dữ liệu mới sau migration? | DROP/DELETE có thể gây mất dữ liệu |
| Có bảng/constraint/index/view phụ thuộc? | DROP có thể thất bại hoặc phá vỡ ứng dụng |
| Phiên bản ứng dụng cũ và mới đang chạy? | Schema trước rollback có thể không hỗ trợ phiên bản mới |
| DBMS có transactional DDL phù hợp? | Có thể để lại trạng thái nửa hoàn tất khi lỗi |
| Có backup/restore hoặc forward-fix khả thi? | Phòng trường hợp rollback không thể phục hồi đúng |
| Liquibase lock có đang do job khác giữ? | Tránh hai tiến trình migration tranh chấp |
| Đã review rollback SQL trên bản sao dữ liệu đại diện? | Cú pháp hợp lệ chưa đủ để khẳng định an toàn |

Đặc biệt, **rollback không thay thế backup**. Một rollback xóa cột không thể tự khôi phục dữ liệu đã nhập vào cột kể từ lần deploy, kể cả khi database đã thực thi rollback thành công về mặt kỹ thuật.

## 16. Changelog đã phát hành và checksum: giữ bất biến

Liquibase ghi lịch sử changeset trong **DATABASECHANGELOG**, thường nhận diện changeset bằng ID, author và đường dẫn changelog (hoặc logicalFilePath nếu cấu hình). Một khi changeset đã triển khai trên môi trường dùng chung, không nên sửa SQL tiến hoặc rollback như một cách “chữa nóng” mà không có quy trình thay đổi được kiểm soát.

Những rủi ro:

- Đổi `id` hoặc `author` có thể khiến Liquibase xem đây là changeset khác.
- Đổi đường dẫn changelog có thể ảnh hưởng danh tính changeset.
- Thay đổi nội dung forward SQL có thể gây checksum mismatch tùy phần nội dung được tính theo cơ chế của phiên bản Liquibase.
- Sửa file SQL được `sqlFile` tham chiếu sau deploy có thể gây khác biệt giữa artifact và dữ liệu thực; tác động checksum/hành vi cần xác minh theo change type và runtime, không suy đoán.
- Một số phần khai báo rollback có quy tắc checksum riêng; dù thay đổi được chấp nhận về mặt checksum cũng không có nghĩa có thể sửa tùy ý mà không review.

Phương án an toàn là phát hành **changeset bổ sung** cho việc sửa schema/dữ liệu, lưu các file SQL đi kèm trong source control, và giữ artifact đã deploy có thể truy xuất lại. Nếu phát hiện rollback chưa đúng sau khi changeset đã chạy, phải đánh giá cách sửa trong quy trình phát hành có version control và thử trên bản sao database đã có lịch sử.

Không xóa hàng trong DATABASECHANGELOG hoặc dùng `clear-checksums` chỉ để làm mất cảnh báo sau khi chỉnh file.

## 17. Kết hợp với Spring Boot và CI/CD

Với Spring Boot, cấu hình changelog ví dụ:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/master.yaml
~~~

Ứng dụng cần dependency Liquibase, JDBC driver và datasource hoặc cấu hình Liquibase riêng. Khi changelog dùng `sqlFile`, **cả SQL tiến và SQL rollback phải được đóng gói trong JAR/image**. Một thay đổi chạy được từ IDE nhưng thiếu file rollback trong artifact là rủi ro lớn: lúc update có thể chưa cần đọc rollback SQL theo cùng đường đi, đến sự cố mới phát hiện tài nguyên không có.

### 17.1. Quy trình CI/CD đề xuất

1. **Static review:** kiểm tra changeset ID/author, đường dẫn `sqlFile`, có rollback không, và có chứa SQL nhạy cảm không.
2. **Kiểm tra parser:** validate changelog, xác minh formatted SQL được nhận diện đúng hoặc XML/YAML khớp phiên bản runtime.
3. **Đóng gói:** đảm bảo tệp tiến và tệp rollback đều nằm trong artifact đã phát hành.
4. **Fresh install:** dựng database mới từ đầu để kiểm tra các changeset chạy đúng.
5. **Upgrade:** chạy từ một database có lịch sử phiên bản trước và dữ liệu đại diện.
6. **Rollback preview:** kiểm tra SQL đảo ngược dự kiến theo phạm vi changeset thật.
7. **Rollback thực tế trên lab:** chạy rollback, xác minh schema, dữ liệu và lịch sử.
8. **Reapply:** khi có ý nghĩa, thử áp dụng lại migration sau rollback và kiểm tra tính nhất quán.
9. **Khả năng tương thích ứng dụng:** đảm bảo phiên bản đang chạy có thể hoạt động với schema trước/sau migration trong kế hoạch release.
10. **Production gate:** chỉ cho phép chạy rollback theo thẩm quyền đã định, có backup, log, người chịu trách nhiệm và phương án forward-fix.

Một số thao tác có thể không hỗ trợ việc rollback và reapply nhiều lần với dữ liệu thật. Khi đó, pipeline cần có **đánh giá rủi ro và đường khôi phục thay thế**, không đánh đồng “bỏ test” với “đã hỗ trợ rollback”.

### 17.2. Nhiều replica và rollback

DATABASECHANGELOGLOCK điều phối các tiến trình Liquibase cùng phạm vi khóa, nhưng không tự bảo vệ người dùng khỏi schema bị rollback trong lúc phiên bản ứng dụng mới vẫn phục vụ traffic. Với deployment nhiều replica, cần điều phối **ứng dụng và migration**: kiểm soát readiness, tạm dừng rollout, xác nhận phiên bản ứng dụng tương thích và chạy rollback bằng một job được quản lý.

Không tự giải phóng Liquibase lock vì rollback cần chạy gấp mà chưa biết holder còn hoạt động hay không.

## 18. Những sai lầm thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Formatted SQL không có rollback | Thiếu `--rollback` hoặc chỉ viết SQL tiến | Khai báo rollback trong đúng changeset và thử trên lab |
| Rollback SQL bị chạy lúc update | Viết câu DROP/UPDATE như SQL tiến, không có directive | Dùng đúng `--rollback` trong formatted SQL |
| sqlFile rollback không được nhận | Ghi `--rollback` trong file SQL thô nhưng changelog cha không khai báo rollback | Thêm `rollback` chứa `sqlFile` vào changeSet |
| Chạy từ IDE được nhưng khi rollback không tìm thấy file | Sai `relativeToChangelogFile` hoặc thiếu file trong JAR | Xác minh đường dẫn theo changelog con và nội dung artifact |
| SQL thủ tục bị tách sai | `splitStatements` và `endDelimiter` không phù hợp | Điều chỉnh theo SQL/DBMS, thử parser và rollback riêng |
| ROLLBACK mất dữ liệu sau DROP COLUMN | Không có bản lưu dữ liệu bị xóa | Dùng backup/forward-fix; không coi CREATE lại là phục hồi đủ |
| DDL rollback lỗi do dependency | View, FK, index hoặc ứng dụng còn phụ thuộc đối tượng | Đảo thứ tự theo dependency, đánh giá tương thích |
| CREATE INDEX CONCURRENTLY lỗi trong transaction | Chưa cấu hình `runInTransaction:false` | Kiểm chứng trên PostgreSQL, tách changeset |
| Retry gặp object already exists | DDL đã commit một phần nhưng lịch sử chưa ghi nhận | Đối chiếu schema và DATABASECHANGELOG trước khi thử lại |
| Checksum mismatch | Changeset hoặc file SQL đã deploy bị chỉnh | Điều tra lịch sử, tạo changeset sửa chữa |
| Rollback count quá nhiều | Chọn sai phạm vi | Preview SQL, đối chiếu tag/lịch sử, có phê duyệt |
| Rollback thành công nhưng ứng dụng lỗi | Schema trước rollback không phù hợp app mới | Điều phối phiên bản ứng dụng và migration |

Khi điều tra, đi theo thứ tự: **đúng database và changelog → lịch sử changeset → khai báo rollback → SQL dự kiến → trạng thái schema/dữ liệu → khả năng tương thích ứng dụng**. Không khắc phục bằng cách sửa bảng lịch sử trực tiếp.

## 19. Bài thực hành: rollback formatted SQL và sqlFile

Chuẩn bị một PostgreSQL lab riêng và nguồn changelog lưu trong version control. Những ví dụ file dưới đây chỉ để người học tự tạo trong môi trường lab; không sử dụng dữ liệu production.

**Bài A — Formatted SQL cơ bản**

1. Viết formatted SQL tạo bảng `status_code`, kèm `--rollback DROP TABLE status_code;`.
2. Chạy validate, update và xác minh bảng xuất hiện.
3. Dùng rollback preview theo count=1, kiểm tra chỉ có câu DROP mong đợi.
4. Trên database lab không có dữ liệu quan trọng, thực thi rollback count=1 và xác nhận bảng bị xóa.
5. Chạy update lại để kiểm tra changeset có thể được áp dụng lại trong điều kiện lab.

**Bài B — Nhiều câu rollback và thứ tự**

1. Viết changeset tạo bảng và index.
2. Thêm hai chỉ thị `--rollback` theo thứ tự xóa index rồi xóa bảng.
3. Kiểm tra preview và làm rõ điều gì xảy ra nếu bảng có dữ liệu hoặc bị tham chiếu.
4. Tách thành hai changeset riêng và so sánh khả năng rollback chọn lọc.

**Bài C — sqlFile với XML/YAML**

1. Tạo changelog YAML hoặc XML khai báo `sqlFile` chạy một câu CREATE INDEX.
2. Khai báo `rollback` tham chiếu `sqlFile` chứa DROP INDEX.
3. Xác nhận `relativeToChangelogFile` đúng khi chạy từ thư mục làm việc khác.
4. Đóng gói artifact thử nghiệm và xác nhận file rollback nằm trong resources.
5. Chạy update/rollback trên lab, so sánh catalog index trước và sau.

**Bài D — Trường hợp dữ liệu không đảo ngược đơn giản**

1. Tạo dữ liệu thử với một số dòng status=PENDING và một số dòng status=CANCELLED.
2. Mô phỏng migration cập nhật PENDING thành CANCELLED.
3. Giải thích vì sao câu rollback đổi tất cả CANCELLED về PENDING là sai.
4. Đề xuất thiết kế backup/staging hoặc forward-fix và cách kiểm tra những dòng thực sự cần phục hồi.

**Bài E — SQL đặc thù transaction**

1. Trên PostgreSQL lab, thử một changeset `CREATE INDEX CONCURRENTLY` với `runInTransaction:false`.
2. Viết rollback `DROP INDEX CONCURRENTLY` trong file riêng.
3. Quan sát catalog, transaction constraints, khả năng lỗi và tình huống index INVALID.
4. Không thử nghiệm trên production.

## 20. Checklist trước khi merge migration có rollback SQL

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Tệp SQL là formatted changelog hay sqlFile? | Chọn đúng cách khai báo rollback |
| Formatted SQL có header, changeset và `--rollback` hợp lệ? | Parser/preview nhận đúng thay đổi |
| Changelog có rollback cho sqlFile rõ ràng? | `rollback` chứa `sqlFile`, đúng đường dẫn |
| Các file tiến/lùi có được đóng gói đầy đủ? | Kiểm tra JAR/image hoặc deployment bundle |
| Thứ tự rollback đảo đúng dependency? | SQL preview và thử trên database lab |
| Đã kiểm tra NULL, FK, index, view và ràng buộc dữ liệu? | Trạng thái schema/dữ liệu trước và sau thử nghiệm |
| SQL parser có đúng delimiter/encoding? | Test các script thực tế trên DBMS mục tiêu |
| Thay đổi có tính nguyên tử/transaction phù hợp? | Kiểm thử trạng thái lỗi và rollback |
| Rollback có thể làm mất dữ liệu mới phát sinh không? | Đánh giá dữ liệu thật, backup/forward-fix |
| Changeset ID/author/path và SQL đã deploy ổn định? | Review lịch sử và checksum |
| Phạm vi count/tag/date đã được duyệt? | Preview rollback SQL, chọn đúng DB đích |
| App cũ/mới có tương thích với schema sau rollback? | Kế hoạch release nhiều phiên bản |
| Đã thử rollback và reapply khi phù hợp? | Bằng chứng CI/CD trên database mới và đã có lịch sử |

**Nguyên tắc cuối cùng:** với formatted SQL, viết rollback bằng chỉ thị `--rollback` trong đúng changeset; với SQL được nạp bằng `sqlFile`, khai báo rollback tường minh trong changelog cha và trỏ đến SQL đảo ngược. Dù cú pháp hợp lệ, rollback chỉ an toàn nếu đã kiểm chứng **phạm vi changeset, trạng thái dữ liệu, dependency, transaction và phiên bản ứng dụng**. Hãy luôn xem trước SQL, thử trên database có dữ liệu đại diện và chuẩn bị backup hoặc forward-fix cho những thay đổi không thể đảo ngược chính xác.

