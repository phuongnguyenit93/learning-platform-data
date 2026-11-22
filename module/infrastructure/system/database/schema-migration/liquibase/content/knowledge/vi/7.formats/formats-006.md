# Phân biệt SQL thông thường với formatted SQL

Trong chương **Định dạng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, cần phân biệt hai cách sử dụng câu lệnh SQL: viết **SQL thông thường** để hệ quản trị cơ sở dữ liệu thực thi, và viết **Liquibase formatted SQL** để Liquibase đọc như một **changelog có cấu trúc**. Hai cách đều sử dụng SQL thực tế để thay đổi schema hoặc dữ liệu, nhưng chúng khác nhau ở cách khai báo changeset, ghi nhận lịch sử, kiểm soát phạm vi, tính checksum và tổ chức rollback.

Mục tiêu của module là quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Vì thế, lựa chọn giữa SQL thông thường và formatted SQL phải xuất phát từ **vai trò của tệp trong quy trình Liquibase**, không chỉ từ việc tệp có đuôi .sql.

## 1. SQL thông thường là gì?

SQL thông thường (plain SQL) là tập lệnh được viết theo cú pháp mà một DBMS hiểu, ví dụ PostgreSQL, MySQL, SQL Server hoặc Oracle. Một tệp có thể chứa DDL, DML hoặc câu truy vấn:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL
);

CREATE UNIQUE INDEX ux_customer_email ON customer(email);

INSERT INTO customer (id, email)
VALUES (1, 'sample@example.test');
~~~

Khi gửi các câu lệnh này trực tiếp qua công cụ SQL của database, DBMS sẽ thực thi chúng dựa trên quyền, transaction, thứ tự và trạng thái hiện tại của database. Bản thân SQL thông thường **không khai báo** id và author của Liquibase; DBMS cũng **không tự thêm dòng vào bảng DATABASECHANGELOG** chỉ vì tệp chứa một câu lệnh CREATE TABLE.

Nếu chạy lại đoạn SQL trên một database đã có bảng customer, CREATE TABLE có thể thất bại. Nếu dùng các lệnh DML không thiết kế an toàn khi chạy lại, việc thực thi nhiều lần có thể tạo dữ liệu trùng hoặc gây thay đổi không mong muốn. Người vận hành phải chủ động kiểm soát việc đã chạy hay chưa.

SQL thông thường có thể được sử dụng theo nhiều cách: chạy thủ công qua SQL client, được database driver thực thi, hoặc được **Liquibase nhúng vào một changeset** thông qua change type sql hay sqlFile. Trường hợp thứ ba vẫn có lịch sử Liquibase, nhưng định danh changeset nằm ở **changelog bao ngoài**, chứ không được suy ra từ nội dung tệp SQL thuần.

## 2. Formatted SQL là gì?

**Liquibase formatted SQL** là tệp SQL chứa những dòng chú thích đặc biệt được Liquibase nhận diện như chỉ thị của changelog. Tệp vẫn có câu lệnh SQL thông thường, nhưng các marker hướng dẫn Liquibase xác định điểm bắt đầu changeset, id, author, thuộc tính thực thi và rollback.

Ví dụ:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-001-create-customer
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL
);
--rollback DROP TABLE customer;

--changeset team-db:20261119-002-unique-email
CREATE UNIQUE INDEX ux_customer_email ON customer(email);
--rollback DROP INDEX ux_customer_email;
~~~

Cách đọc tệp này:

1. **--liquibase formatted sql** khai báo đây là một changelog ở định dạng formatted SQL.
2. **--changeset team-db:20261119-001-create-customer** bắt đầu changeset thứ nhất; phần trước dấu hai chấm là author, phần sau là id.
3. Câu lệnh CREATE TABLE là SQL mà Liquibase thực thi khi changeset được chọn.
4. **--rollback DROP TABLE customer;** mô tả SQL để rollback changeset thứ nhất.
5. Marker changeset tiếp theo mở changeset thứ hai với định danh và rollback độc lập.

Cú pháp author:id dễ bị viết ngược. Với ví dụ trên, **author là team-db**, còn **id là 20261119-001-create-customer**. Trong YAML hoặc XML, hai thuộc tính có tên riêng; trong formatted SQL, chúng được ghép trong một marker.

Những dòng bắt đầu bằng dấu -- là comment theo cú pháp SQL của nhiều DBMS. Khi Liquibase phân tích tệp ở chế độ formatted SQL, một số comment đó trở thành chỉ thị triển khai. Nếu đưa tệp vào một SQL client thông thường để chạy trực tiếp, các marker thường chỉ bị xem là comment, còn lệnh CREATE TABLE và CREATE INDEX vẫn được gửi đến database. Khi đó các thay đổi **không được ghi nhận bằng changeset trong DATABASECHANGELOG** theo quy trình Liquibase.

## 3. So sánh theo vai trò của tệp

| Tiêu chí | SQL thông thường chạy trực tiếp | Liquibase formatted SQL |
|---|---|---|
| Người đọc cú pháp | DBMS/SQL client | Liquibase phân tích marker, sau đó gửi SQL đến DBMS |
| Marker bắt buộc của Liquibase | Không có | Header formatted SQL và marker changeset |
| id, author | Không có mặc định | Khai báo trong --changeset author:id |
| Định danh lịch sử | Do quy trình ngoài Liquibase quản lý nếu có | Liquibase dùng ID + AUTHOR + FILENAME |
| Chạy lại | Tùy người gọi hoặc logic SQL | Liquibase đối chiếu lịch sử và thuộc tính changeset |
| Checksum Liquibase | Không có khi chạy thuần bằng SQL client | Được quản lý theo changeset đã ghi nhận |
| Rollback Liquibase | Phải tự xây dựng quy trình | Có thể khai báo bằng --rollback |
| Context, label, dbms | Không có ý nghĩa với DBMS thuần | Có thể khai báo bằng thuộc tính changeset |
| Tích hợp changelog | Cần đưa vào một change hoặc cơ chế riêng | Có thể được Liquibase nạp như changelog |
| Khả năng dùng SQL đặc thù DBMS | Có | Có; vẫn phải quan tâm đến DBMS đích |

Có một trường hợp thứ ba rất quan trọng: **SQL thuần được Liquibase gọi qua sqlFile**. Khi đó Liquibase vẫn ghi lịch sử và kiểm tra checksum **cho changeset bao ngoài**, dù tệp SQL không có header formatted SQL. Vì vậy, kết luận “SQL thuần không được Liquibase quản lý” chỉ đúng khi tệp được chạy **ngoài** một changeset Liquibase.

## 4. Ba cách dùng SQL trong Liquibase

### Cách A: Viết change type sql ngay trong changelog YAML

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "team-db"
      changes:
        - sql:
            sql: |
              CREATE TABLE customer (
                  id BIGINT PRIMARY KEY,
                  email VARCHAR(320) NOT NULL
              );
      rollback:
        - sql:
            sql: DROP TABLE customer;
~~~

**id và author nằm ở YAML**. Nội dung SQL trong khối sql là thao tác được quản lý bởi changeset đó. Cách này phù hợp một đoạn SQL tương đối ngắn, khi nhóm muốn đặt metadata và rollback cạnh nhau trong changelog có cấu trúc.

### Cách B: Viết SQL thuần trong tệp bên ngoài và gọi bằng sqlFile

Tệp SQL thuần, ví dụ sql/create_customer.sql:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL
);
~~~

Changelog YAML tham chiếu đến tệp đó:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "team-db"
      changes:
        - sqlFile:
            path: sql/create_customer.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
      rollback:
        - sqlFile:
            path: sql/drop_customer.sql
            relativeToChangelogFile: true
~~~

Tệp sql/drop_customer.sql được chuẩn bị riêng với SQL rollback tương ứng:

~~~sql
DROP TABLE customer;
~~~

Đây là một changeset, dù nội dung changes được đặt trong tệp khác. **Không cần** thêm --liquibase formatted sql hay --changeset vào sql/create_customer.sql. Liquibase nạp nó như **nội dung của sqlFile change**, còn khóa lịch sử của changeset lấy từ id, author và filename của changelog YAML.

Trong ví dụ, relativeToChangelogFile: true giúp giải quyết đường dẫn tương đối dựa trên nơi chứa changelog khai báo sqlFile. Không nên suy ra đường dẫn từ thư mục bạn đang mở trong editor; hãy đối chiếu đường dẫn được Liquibase giải quyết trong môi trường chạy.

### Cách C: Dùng chính tệp formatted SQL làm changelog

Tệp changelog, ví dụ db/changelog/changes/20261119-customer.sql:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-001-create-customer
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL
);
--rollback DROP TABLE customer;
~~~

Liquibase có thể nạp tệp formatted SQL như changelog đầu vào, hoặc nạp từ changelog gốc thông qua cơ chế include phù hợp với phiên bản Liquibase đang dùng.

Ví dụ chạy trực tiếp làm changelog gốc:

~~~bash
liquibase --changelog-file=db/changelog/changes/20261119-customer.sql validate
liquibase --changelog-file=db/changelog/changes/20261119-customer.sql status --verbose
liquibase --changelog-file=db/changelog/changes/20261119-customer.sql update-sql
~~~

Ở cách này, Liquibase đọc các marker để tạo changeset. Không đặt một tệp formatted SQL vào sqlFile rồi mặc định mong Liquibase phân tích các marker như một changelog: sqlFile dùng để thực thi **nội dung SQL** của changeset bao ngoài.

## 5. Thứ tự marker và phạm vi của một changeset

Trong formatted SQL, marker changeset tách các đoạn SQL thành những đơn vị quản lý lịch sử độc lập:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-001-create-department
CREATE TABLE department (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
--rollback DROP TABLE department;

--changeset team-db:20261119-002-add-department-code
ALTER TABLE department ADD COLUMN code VARCHAR(20);
--rollback ALTER TABLE department DROP COLUMN code;
~~~

Changeset thứ nhất và thứ hai có hai dòng lịch sử riêng khi được thực thi/ghi nhận. Nếu changeset thứ nhất đã chạy và thứ hai chưa chạy, Liquibase có thể chỉ chọn changeset thứ hai ở lần update tiếp theo.

Những lỗi thường gặp khi bố trí marker:

- Thiếu header đầu tệp: Liquibase có thể không nhận diện tệp là formatted SQL changelog.
- Thiếu marker --changeset: SQL không được gắn vào changeset hợp lệ theo định dạng dự kiến.
- Viết --changeset id:author thay vì author:id: lịch sử được nhận diện sai.
- Đặt SQL thuộc changeset A sau marker của B: câu lệnh được chuyển sang changeset B.
- Đặt rollback của A sau marker của B: rollback có thể bị hiểu thành rollback của B.
- Lặp lại id và author trong cùng tệp: tạo xung đột định danh.

Một changeset có thể chứa nhiều câu lệnh SQL, nhưng việc gom hay tách cần dựa vào tính độc lập, khả năng rollback và giao dịch của DBMS. Đừng đặt mọi câu lệnh migration của cả phiên bản vào một changeset khổng lồ chỉ vì định dạng cho phép.

## 6. Cách Liquibase nhận diện changeset của formatted SQL

Liquibase dùng bộ ba **ID + AUTHOR + FILENAME** để phân biệt changeset đã ghi nhận với changeset đang chờ. Trong formatted SQL, ID và AUTHOR đến từ marker --changeset; FILENAME là đường dẫn changelog được Liquibase ghi nhận, có thể chịu ảnh hưởng của logicalFilePath nếu được cấu hình và hỗ trợ trong phạm vi phù hợp.

Ví dụ hai tệp có cùng marker:

~~~text
db/changelog/customer.sql  -> author=team-db, id=001
db/changelog/order.sql     -> author=team-db, id=001
~~~

Đây có thể là hai định danh khác nhau do FILENAME khác nhau. Tuy nhiên, việc dùng id có ý nghĩa và ít trùng trên toàn module sẽ làm log dễ đọc và giảm sai sót khi tái cấu trúc.

**Không đổi id, author hay đường dẫn định danh của changeset đã triển khai** nếu chưa có quy trình chuyển đổi được kiểm chứng. Đổi tên hoặc di chuyển tệp formatted SQL có thể khiến Liquibase xem changeset cũ là mới, dẫn đến chạy lại CREATE TABLE/ALTER TABLE ngoài ý muốn.

DATABASECHANGELOG lưu lịch sử đã chạy/được ghi nhận; nó không được SQL client cập nhật tự động khi chạy SQL bên ngoài Liquibase. Kiểm tra lịch sử bằng:

~~~sql
SELECT ID, AUTHOR, FILENAME, DATEEXECUTED, EXECTYPE, MD5SUM
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

MD5SUM giúp phát hiện nội dung changeset thay đổi. Nếu sửa SQL của changeset đã được triển khai, Liquibase có thể báo lỗi checksum. Thực hành mặc định là **giữ changeset cũ bất biến và tạo changeset mới** để điều chỉnh; không xóa lịch sử hoặc bỏ qua checksum chỉ để lệnh update chạy qua.

## 7. Thuộc tính bổ sung trong marker changeset

Formatted SQL cho phép khai báo nhiều thuộc tính ngay trên marker changeset. Ví dụ:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-003-add-customer-note contextFilter:dev labels:demo dbms:postgresql
ALTER TABLE customer ADD COLUMN note VARCHAR(200);
--rollback ALTER TABLE customer DROP COLUMN note;
~~~

Ý nghĩa:

- **contextFilter:dev** chọn changeset khi bộ lọc context phù hợp.
- **labels:demo** cho phép chọn theo label của lệnh triển khai.
- **dbms:postgresql** chỉ ra SQL dành cho PostgreSQL.
- **--rollback** cung cấp SQL để khôi phục khi thực hiện rollback có kiểm soát.

Các thuộc tính bổ sung thuộc về **changeset**, không phải nội dung lệnh SQL mà DBMS tự hiểu. Bộ lọc context hoặc label không thay thế quyền database; người có quyền chạy job vẫn cần bị giới hạn bằng thông tin xác thực và quyền triển khai thích hợp.

Các thuộc tính đáng chú ý khác là runInTransaction, runOnChange, runAlways, splitStatements, endDelimiter và stripComments. Không phải thuộc tính nào cũng phù hợp mọi câu lệnh. Hãy kiểm tra tài liệu của phiên bản Liquibase và DBMS đang dùng khi áp dụng.

## 8. Phân tách câu lệnh, dấu kết thúc và SQL phức tạp

Một tệp SQL thuần có thể chứa nhiều câu lệnh ngăn cách bằng dấu chấm phẩy. Nhưng thủ tục, function, trigger hoặc khối PL/SQL có thể chứa dấu chấm phẩy **bên trong một câu lệnh logic**. Nếu Liquibase chia sai, DBMS sẽ nhận những mảnh SQL chưa hoàn chỉnh.

Đối với sqlFile hoặc formatted SQL, cần hiểu ba tùy chọn:

| Tùy chọn | Ý nghĩa | Khi cần quan tâm |
|---|---|---|
| splitStatements | Có chia nội dung thành nhiều câu lệnh trước khi gửi hay không | Tệp chứa nhiều câu lệnh, hoặc khối SQL đặc biệt không được phép chia tùy tiện |
| endDelimiter | Dấu phân cách/kết thúc được Liquibase sử dụng khi tách câu lệnh | DBMS dùng thủ tục, trigger hoặc delimiter đặc biệt |
| stripComments | Có loại bỏ comment SQL trước khi thực thi hay không | Tệp có comment quan trọng với DBMS hoặc được yêu cầu giữ nguyên |

Ví dụ minh họa marker tùy biến:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-004-multi-statement splitStatements:true endDelimiter:;
UPDATE customer SET note = 'verified' WHERE id = 1;
UPDATE customer SET note = 'reviewed' WHERE id = 2;
--rollback UPDATE customer SET note = NULL WHERE id IN (1, 2);
~~~

Đây là ví dụ đơn giản sử dụng dấu chấm phẩy. Với stored procedure hoặc SQL có cú pháp delimiter đặc thù, cần kiểm tra cách Liquibase và bộ thực thi JDBC/driver xử lý khối lệnh; đừng sao chép endDelimiter hoặc splitStatements từ một DBMS sang DBMS khác.

Tùy cách dùng, Liquibase có thể dựa vào dấu chấm phẩy hoặc ký hiệu như GO để chia câu lệnh, và các tùy chọn ở cấp change hoặc changeset sẽ điều chỉnh hành vi. Một số bộ thực thi SQL native có quy tắc tách câu lệnh riêng. Việc SQL chạy được trong một SQL client **không tự bảo đảm** rằng Liquibase sẽ chia câu lệnh giống hệt.

Khi dùng sqlFile, đặt splitStatements và các tùy chọn liên quan ở **change sqlFile** trong changelog để hành vi rõ ràng; khi dùng formatted SQL, đặt các thuộc tính hỗ trợ tại marker changeset theo cú pháp định dạng và phiên bản được chọn.

## 9. Rollback: khác biệt giữa SQL thuần và formatted SQL

DBMS không có khái niệm marker rollback của Liquibase. Khi một người vận hành chạy SQL thuần trực tiếp, muốn đảo ngược thay đổi phải tự thực hiện SQL ngược, khôi phục từ backup hoặc áp dụng kế hoạch sửa tiến.

Trong formatted SQL, có thể khai báo rollback cạnh changeset:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-005-add-status
ALTER TABLE customer ADD COLUMN status VARCHAR(20);
--rollback ALTER TABLE customer DROP COLUMN status;
~~~

Dòng --rollback là chỉ thị cho Liquibase. Khi update thông thường, SQL rollback không được chạy; nó được dùng khi thực hiện một lệnh rollback phù hợp.

Với SQL thường được gọi qua sqlFile, rollback được định nghĩa ở changeset bao ngoài, chẳng hạn bằng một sqlFile khác như ví dụ ở phần 4. Nếu thiếu rollback có thể phải xây dựng thủ công; không nên mặc định Liquibase tự tạo được rollback cho mọi change SQL tùy ý.

**Rollback kỹ thuật không đồng nghĩa khôi phục dữ liệu an toàn.** DROP TABLE, DROP COLUMN hoặc DELETE có thể xóa dữ liệu đã phát sinh sau lúc migration chạy. Cần kiểm thử rollback trên dữ liệu đại diện, xem xét phụ thuộc khóa ngoại, tính tương thích ứng dụng và phương án khôi phục bản sao lưu. Với thay đổi dữ liệu phức tạp, sửa tiến (forward fix) có thể thực tế hơn rollback tự động.

Khi thiết kế một changeset chứa nhiều câu lệnh, hãy đánh giá giao dịch thực tế của DBMS. Mặc dù runInTransaction mặc định thường được dùng, không phải mọi loại DDL đều hỗ trợ transaction như nhau; một lỗi giữa chừng có thể để lại thay đổi từng phần tùy nền tảng.

## 10. Preconditions: bảo vệ việc thực thi

Formatted SQL hỗ trợ một số precondition qua comment directive; phạm vi loại precondition hỗ trợ và cú pháp cần đối chiếu với phiên bản Liquibase. Một ví dụ SQL check thường gặp:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-006-add-note
--preconditions onFail:HALT
--precondition-sql-check expectedResult:1 SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'customer';
ALTER TABLE customer ADD COLUMN note VARCHAR(200);
--rollback ALTER TABLE customer DROP COLUMN note;
~~~

Ví dụ dùng truy vấn vào information_schema để kiểm tra điều kiện; cú pháp SQL, schema và phân biệt chữ hoa/thường phụ thuộc DBMS. Trong môi trường thật cần đặt điều kiện chính xác với schema đang triển khai.

Với onFail:HALT, nếu điều kiện không đạt, Liquibase dừng thay vì mạo hiểm chạy ALTER TABLE. Các lựa chọn khác như WARN, CONTINUE hoặc MARK_RAN có hành vi khác nhau và cần được cân nhắc; đặc biệt MARK_RAN có thể ghi nhận changeset là đã chạy mà không thực thi SQL.

Không dựa hoàn toàn vào precondition để biến mọi migration thành idempotent. Phải xem xét tình trạng schema, dữ liệu, bộ lọc, lịch sử và thứ tự changeset. Khi cần precondition phức tạp hoặc không được formatted SQL ở phiên bản cụ thể hỗ trợ, có thể chuyển metadata sang YAML/XML changelog và tham chiếu SQL qua sqlFile.

## 11. Tích hợp vào changelog gốc và cấu trúc thư mục

Một dự án có thể tổ chức như sau:

~~~text
db/
  changelog/
    db.changelog-master.yaml
    changes/
      20261119-customer.sql       # formatted SQL changelog
      20261120-order.sql          # formatted SQL changelog
  sql/
    create-legacy-index.sql       # plain SQL cho sqlFile change
~~~

Changelog gốc có thể bao gồm các changelog con:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/20261119-customer.sql
      relativeToChangelogFile: true
  - include:
      file: changes/20261120-order.sql
      relativeToChangelogFile: true
~~~

Tệp formatted SQL được nạp như **changelog con**; tệp plain SQL cần được dùng trong **sqlFile change** thích hợp. Với cấu trúc include và định dạng SQL, mức hỗ trợ cụ thể phụ thuộc phiên bản Liquibase; cần xác nhận bằng validate trong bản CLI hoặc ứng dụng đang dùng.

Khi dùng includeAll, phải hiểu quy tắc nạp và sắp xếp tệp trước khi triển khai. Thứ tự chạy do cấu trúc changelog xác định, **không phải** do giá trị id mang ý nghĩa thời gian mà bạn tự đặt. Cần tránh thay đổi thứ tự hoặc đường dẫn của những changelog đã triển khai mà không đánh giá tác động lịch sử.

## 12. Tích hợp Spring Boot và CI/CD

Với Spring Boot, có thể cấu hình changelog gốc như sau:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Khi ứng dụng khởi động, Liquibase đọc changelog gốc, nạp các tệp được include và đối chiếu changeset trong DATABASECHANGELOG của database đích. Liquibase có thể xử lý formatted SQL khi tệp đã được nạp đúng vai trò changelog. Nếu dùng sqlFile, id và author vẫn nằm ở changelog YAML/XML bao ngoài.

Với Liquibase CLI hoặc CI/CD, quy trình kiểm tra cơ bản:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Sau khi review SQL dự kiến, kiểm tra thông tin kết nối, schema đích và phạm vi changeset, pipeline mới chạy:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

Sau update, kiểm tra history, DATABASECHANGELOG và trạng thái schema thực tế. Cùng tệp formatted SQL có thể đã chạy ở development nhưng đang chờ ở staging/production vì mỗi database có lịch sử riêng. Đừng sửa marker id/author để “đánh dấu môi trường”; quản lý khác biệt môi trường qua cấu hình kết nối, context, label và lựa chọn changeset được review.

Trong pipeline, nên dùng một bản artifact/changelog đã được validate để promote qua các môi trường; tránh chỉnh SQL cũ giữa staging và production. SQL thông thường chạy ngoài Liquibase sẽ không tự được hệ thống lịch sử ghi nhận, có thể dẫn đến drift giữa schema và DATABASECHANGELOG.

## 13. Các tình huống chọn định dạng

### Tình huống A: Một SQL migration đã có sẵn trong kho mã

Bạn được bàn giao tệp legacy_update.sql chứa nhiều câu SQL phức tạp. Nếu muốn dùng Liquibase mà giữ nội dung SQL thuần để SQL client hoặc công cụ khác vẫn đọc được, hãy cân nhắc **sqlFile change trong YAML/XML**. Định danh, precondition, rollback và các thuộc tính khác được quản lý ở changelog bao ngoài.

### Tình huống B: Nhóm chủ yếu viết SQL nhưng muốn quản lý lịch sử qua Liquibase

Nếu nhóm quen review SQL và mỗi thay đổi cần marker rõ ràng, **formatted SQL** là lựa chọn tự nhiên. Cùng một tệp có thể có nhiều changeset, mỗi changeset có id, author, rollback và metadata. Cần review cẩn thận marker và quy tắc phân tách câu lệnh.

### Tình huống C: Migration cần nhiều change type trừu tượng hoặc metadata phức tạp

Khi muốn dùng createTable, addColumn, loadData, precondition nhiều loại hoặc khả năng hỗ trợ nhiều DBMS, changelog **YAML/XML/JSON** thường dễ biểu đạt và được IDE hoặc tooling hỗ trợ tốt hơn. Có thể kết hợp change sql hoặc sqlFile cho các đoạn SQL đặc thù khi cần.

### Tình huống D: Script chỉ chạy một lần bằng DBA tool, ngoài Liquibase

Một script SQL thuần được chạy thủ công có thể phù hợp cho tác vụ vận hành đơn lẻ theo quy trình riêng. Nhưng nếu thay đổi schema thuộc vòng đời ứng dụng, cần lập kế hoạch đưa nó vào lịch sử migration để những môi trường khác có thể triển khai thống nhất và kiểm chứng được. Không tự thêm dòng vào DATABASECHANGELOG nếu chưa đối chiếu schema thật và thiết kế baseline đúng cách.

Không có định dạng nào tự động giải quyết an toàn dữ liệu. Định dạng giúp diễn đạt thay đổi và kiểm soát lịch sử; việc review SQL, thử nghiệm trên dữ liệu đại diện, quản lý giao dịch và quyền truy cập vẫn bắt buộc.

## 14. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Liquibase không nhận tệp SQL là changelog | Thiếu hoặc sai header formatted SQL; tệp đang được gọi như sqlFile | Kiểm tra vai trò tệp và marker đầu tệp |
| Chỉ thấy một changeset dù tệp chứa nhiều lệnh | SQL được gọi qua một sqlFile change hoặc thiếu marker --changeset | Phân biệt sqlFile với formatted SQL; tách changeset khi cần |
| Changeset có author/id sai | Viết nhầm thứ tự author:id | Sửa trước khi phát hành; nếu đã chạy phải xử lý lịch sử có kiểm chứng |
| Một changeset cũ bị chọn lại | Đổi id, author hoặc FILENAME | Đối chiếu DATABASECHANGELOG và đường dẫn logic |
| Lỗi checksum sau khi sửa script | Nội dung changeset đã chạy bị thay đổi | Giữ nguyên lịch sử; tạo changeset mới để điều chỉnh |
| SQL chạy được trong SQL client nhưng Liquibase lỗi cú pháp | Liquibase chia câu lệnh sai hoặc thiếu delimiter phù hợp | Xem splitStatements, endDelimiter, DBMS/driver, bản SQL được tạo |
| Rollback không hoạt động | Thiếu khai báo rollback hoặc SQL rollback không hợp lệ | Viết và thử rollback trong môi trường kiểm thử |
| Một changeset không chạy ở production | Context, label, dbms, precondition hoặc lịch sử đã ghi nhận | Kiểm tra filter và DATABASECHANGELOG ở đúng database |
| Chạy SQL trực tiếp xong Liquibase vẫn xem là pending | SQL client không ghi lịch sử Liquibase | So sánh schema với changelog; sử dụng quy trình đồng bộ/baseline có kiểm chứng |

Khi lỗi xảy ra, cần phân biệt lỗi **parse changelog**, lỗi **định danh và trạng thái**, lỗi **chia câu lệnh SQL**, lỗi **quyền hoặc DBMS**, và lỗi **dữ liệu đã tồn tại**. Không giải quyết toàn bộ bằng việc xóa checksum hay sửa DATABASECHANGELOG thủ công.

## 15. Bài thực hành có kiểm chứng

**Bối cảnh:** thêm cột loyalty_level vào bảng customer trên database thử nghiệm. Mục tiêu là thử hai cách biểu diễn cùng thay đổi, hiểu id/author nằm ở đâu và chứng minh khác biệt về lịch sử.

### Phần A: SQL thuần + sqlFile

Tệp sql/add_loyalty_level.sql:

~~~sql
ALTER TABLE customer ADD COLUMN loyalty_level VARCHAR(20);
~~~

Changelog YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-101-add-loyalty-level"
      author: "team-db"
      changes:
        - sqlFile:
            path: sql/add_loyalty_level.sql
            relativeToChangelogFile: true
      rollback:
        - sql:
            sql: ALTER TABLE customer DROP COLUMN loyalty_level;
~~~

Quan sát: SQL trong tệp không có marker; id và author được cấp từ YAML.

### Phần B: Formatted SQL

Trong một database thử nghiệm **độc lập** hoặc sau khi đưa schema về trạng thái trước thay đổi, dùng changelog sau:

~~~sql
--liquibase formatted sql

--changeset team-db:20261119-101-add-loyalty-level
ALTER TABLE customer ADD COLUMN loyalty_level VARCHAR(20);
--rollback ALTER TABLE customer DROP COLUMN loyalty_level;
~~~

Quan sát: id và author được cấp trực tiếp trong tệp SQL ở marker changeset. Không dùng cùng database đã chạy phần A rồi chạy lại phần B mà chưa xử lý trạng thái; cả hai ví dụ đều cố tạo cùng một cột.

### Các bước xác minh

1. Chuẩn bị hai database thử nghiệm có schema ban đầu giống nhau, bảng customer đã tồn tại và chưa có cột loyalty_level.
2. Kiểm tra đường dẫn và chọn changelog cho từng bài thực hành.
3. Chạy validate và status --verbose; xác nhận changeset đang chờ trên từng database.
4. Chạy update-sql, so sánh lệnh ALTER TABLE được sinh ra.
5. Chạy update trên từng database riêng, xác nhận cột đã tồn tại.
6. Truy vấn DATABASECHANGELOG. Ở phần A, FILENAME thuộc changelog YAML; ở phần B, FILENAME thuộc formatted SQL changelog. ID và AUTHOR được ghi theo nơi khai báo tương ứng.
7. Chạy lại status để xác nhận changeset thông thường không còn pending.
8. Kiểm tra rollback-sql hoặc thực hành rollback trên database thử nghiệm theo cơ chế phù hợp với phiên bản Liquibase; đánh giá tác động xóa cột.
9. Thử chỉnh nội dung một changeset đã chạy **chỉ trong môi trường học tập**, chạy validate/status theo khả năng kiểm tra checksum của phiên bản để quan sát lỗi, rồi hoàn nguyên. Không thử thay đổi lịch sử trên database dùng chung.

### Câu hỏi tự kiểm tra

- Nếu tệp SQL chỉ có CREATE TABLE và không có marker, có thể dùng nó trong Liquibase không? **Có**, thông qua sqlFile hoặc sql change của một changeset có định danh trong changelog bao ngoài.
- Nếu tệp chứa --liquibase formatted sql nhưng được chạy bằng psql hoặc SQL client thông thường, Liquibase có cập nhật DATABASECHANGELOG không? **Không**, vì các marker chỉ là comment đối với SQL client; việc thực thi đó bỏ qua Liquibase.
- Có thể dùng hai marker --changeset trong một formatted SQL không? **Có**, đây là hai changeset với id/author riêng, được Liquibase quản lý độc lập.
- Nếu sửa đường dẫn tệp formatted SQL đã triển khai, nguy cơ là gì? **Khóa ID + AUTHOR + FILENAME thay đổi**, làm Liquibase có thể nhận diện changeset cũ thành changeset mới.
- Dùng --rollback có bảo đảm không mất dữ liệu không? **Không**; rollback SQL phải được thiết kế và thử nghiệm dựa trên schema và dữ liệu thực tế.

## 16. Checklist trước khi chọn và chạy định dạng

- [ ] Đã xác định tệp SQL đóng vai trò **plain SQL trong sqlFile** hay **formatted SQL changelog**.
- [ ] Nếu là formatted SQL, header và marker --changeset author:id đúng cú pháp.
- [ ] id, author, FILENAME ổn định và không xung đột với lịch sử đã triển khai.
- [ ] Nếu dùng sqlFile, path và relativeToChangelogFile được kiểm tra chính xác.
- [ ] Đã xác định cách chia câu lệnh, delimiter và comment cho DBMS đích.
- [ ] Đã xem xét context, labels, dbms, precondition và thuộc tính chạy lại khi cần.
- [ ] Đã có kế hoạch rollback hoặc forward fix và đã đánh giá mất dữ liệu.
- [ ] Không sửa nội dung changeset đã chạy chỉ để làm đẹp hoặc đổi định dạng.
- [ ] Đã chạy validate, status --verbose và review update-sql.
- [ ] Đã xác nhận database/schema và quyền của tài khoản migration.
- [ ] Sau update, đã kiểm tra DATABASECHANGELOG cùng cấu trúc/dữ liệu thực tế.
- [ ] Đã dùng cùng artifact/changelog qua các môi trường, quản lý khác biệt bằng cấu hình.

Sự khác biệt cốt lõi nằm ở **ai quản lý ranh giới changeset và lịch sử**. SQL thông thường là lệnh cho DBMS; formatted SQL là một changelog mà Liquibase phân tích để quản lý những lệnh đó theo từng changeset. SQL thuần vẫn có thể tham gia đầy đủ vào quy trình migration khi được khai báo trong sqlFile change của Liquibase. Hiểu rõ ba cách dùng giúp nhóm phát triển chọn định dạng dễ bảo trì, quản lý checksum và rollback đúng nơi, đồng thời triển khai có thể kiểm chứng qua Spring Boot, CI/CD và nhiều database đích.
