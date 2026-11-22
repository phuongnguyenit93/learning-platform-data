# Xây dựng dự án Spring Boot với changelog đầu tiên

## 1. Mục tiêu thực hành

Trong bài thực hành này, bạn sẽ xây dựng một ứng dụng Spring Boot nhỏ kết nối PostgreSQL và dùng Liquibase để tạo schema ngay từ changelog đầu tiên. Khi ứng dụng khởi động, Spring Boot nạp cấu hình datasource, khởi tạo Liquibase, đọc changelog, tạo các bảng cần thiết và ghi lại changeset đã chạy. Khi khởi động lần sau, Liquibase đọc lịch sử để chỉ thực hiện những thay đổi còn pending.

Bài tập sử dụng một miền nghiệp vụ đơn giản gồm khách hàng và đơn hàng. Changelog đầu tiên tạo bảng <code>customer</code>; changelog tiếp theo tạo bảng <code>orders</code> và khóa ngoại tới khách hàng. Qua đó, bạn sẽ thực hành thứ tự phụ thuộc, kiểu dữ liệu, khóa chính, khóa ngoại, rollback và cách xác minh trạng thái database.

Bài học thuộc chương **Thực hành** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module giúp nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Sau bài học, bạn có thể:

1. Chuẩn bị project Spring Boot có dependency Liquibase và JDBC driver.
2. Cấu hình datasource và đường dẫn master changelog.
3. Viết changelog YAML với các changeset tạo bảng có quan hệ.
4. Khởi động ứng dụng và xác nhận Liquibase đã chạy migration.
5. Đọc DATABASECHANGELOG, DATABASECHANGELOGLOCK và hiểu checksum.
6. Thêm changeset mới đúng cách, kiểm tra SQL dự kiến và thử rollback trong môi trường lab.
7. Phân biệt vai trò của Liquibase với Hibernate schema generation.

## 2. Kiến trúc và luồng thực thi

Trong bài lab, ứng dụng kết nối tới một PostgreSQL database. Liquibase là thành phần quản lý thay đổi schema; Spring Boot tự động chạy Liquibase trong quá trình khởi tạo application context khi dependency và cấu hình phù hợp được bật.

~~~text
Spring Boot application
        |
        v
    DataSource  -----------------> PostgreSQL database
        |                                  |
        v                                  |
   SpringLiquibase                         |
        |                                  |
        +---- đọc master changelog         |
        |                                  |
        +---- đọc DATABASECHANGELOG <------+
        |
        +---- lấy DATABASECHANGELOGLOCK
        |
        +---- chạy changeset pending
        |
        +---- ghi lịch sử / giải phóng lock
        |
        v
Application context hoàn tất
~~~

Liquibase quản lý schema thông qua các file changelog được version control. Mỗi changeset mô tả một thay đổi có định danh, thường gồm <code>id</code>, <code>author</code> và đường dẫn changelog. Khi thực thi, Liquibase lưu thông tin changeset vào <code>DATABASECHANGELOG</code>, bao gồm checksum để phát hiện nội dung changeset lịch sử bị sửa.

<code>DATABASECHANGELOGLOCK</code> phối hợp các tiến trình Liquibase dùng cùng lock table. Nó giúp tránh hai tiến trình cùng áp dụng migration trên một history scope tại cùng thời điểm. Lock này không thay thế khóa DDL của DBMS và không điều phối thay đổi thủ công từ DBA hoặc công cụ khác.

## 3. Chuẩn bị môi trường

Bạn cần:

- JDK tương thích với phiên bản Spring Boot của project.
- Maven và Maven Wrapper (hoặc hệ thống build mà project đã chọn).
- PostgreSQL đang chạy và có một database dành riêng cho bài lab.
- IDE hoặc editor có hỗ trợ Java, YAML và Maven.
- Quyền kết nối database và quyền tạo bảng trong schema lab.

Ví dụ dưới đây dùng Maven và PostgreSQL. Có thể chuyển sang Gradle nếu project đã chuẩn hóa Gradle; các file changelog và nguyên tắc Liquibase không phụ thuộc Maven.

### 3.1. Tạo database lab

Tạo database rỗng tên <code>liquibase_lab</code> bằng công cụ quản trị PostgreSQL hoặc Docker. Ví dụ lệnh chạy PostgreSQL container chỉ dành cho môi trường local:

~~~bash
docker run --name liquibase-lab-db \
  -e POSTGRES_DB=liquibase_lab \
  -e POSTGRES_USER=lab_user \
  -e POSTGRES_PASSWORD=local-only-password \
  -p 5432:5432 \
  -d postgres
~~~

Mật khẩu trong ví dụ chỉ là giá trị minh họa cho máy local. Không tái sử dụng nó trong staging/production, không commit secret vào repository và không dùng tài khoản có quyền quản trị rộng cho ứng dụng thật.

Xác minh database có thể kết nối:

~~~sql
SELECT current_database(), current_user;
~~~

Kết quả cần cho biết bạn đang kết nối đúng database lab và đúng user dự kiến. Database phải tồn tại trước khi Spring Boot kết nối; Liquibase thường quản lý schema/object bên trong database chứ không mặc định tạo database PostgreSQL thay bạn.

### 3.2. Tạo project Spring Boot

Tạo một project Spring Boot với Java và Maven. Có thể dùng Spring Initializr hoặc cấu trúc project nội bộ. Chọn các thành phần:

- Spring Boot.
- Spring JDBC (hoặc Spring Data JPA nếu bài tập cần ORM).
- PostgreSQL Driver.
- Liquibase.

Một cấu trúc thư mục tối thiểu:

~~~text
orders-service/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/orders/
        │       └── OrdersApplication.java
        └── resources/
            ├── application.yaml
            └── db/
                └── changelog/
                    ├── db.changelog-master.yaml
                    └── changes/
                        ├── 001-create-customer.yaml
                        └── 002-create-orders.yaml
~~~

Đường dẫn changelog là tài nguyên trong classpath, không phải đường dẫn file tùy ý trên máy developer. Giữ tên file và cấu trúc ổn định để các môi trường dùng cùng artifact.

## 4. Thêm dependency

Nếu project dùng Spring Boot dependency management, phiên bản tương thích của các dependency thường được quản lý qua Spring Boot parent hoặc BOM. Ví dụ các dependency cần có trong Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.liquibase</groupId>
        <artifactId>liquibase-core</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Nếu ứng dụng dùng JPA, có thể thay hoặc bổ sung starter phù hợp. Không thêm đồng thời nhiều cách quản lý schema như Liquibase, Hibernate <code>create</code> và script tự chạy mà không xác định rõ owner của DDL. Hãy dùng một nguồn quản lý schema nhất quán.

### 4.1. Kiểm tra dependency thực tế

Trước khi chạy, xác nhận:

- Có đúng một phiên bản Liquibase được resolve trong runtime classpath.
- JDBC driver khớp với DBMS.
- Spring Boot version và Liquibase version tương thích.
- Dependency không bị loại khỏi gói chạy.
- Nếu dùng JPA, Hibernate không được cấu hình tự tạo hoặc tự cập nhật schema song song.

Không cần tự đặt version cho từng dependency nếu BOM đã quản lý. Nếu project không dùng BOM, hãy chọn phiên bản tương thích theo ma trận hỗ trợ của Spring Boot, Liquibase và driver.

## 5. Cấu hình datasource và Liquibase

Tạo <code>src/main/resources/application.yaml</code>:

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/liquibase_lab}
    username: ${DB_USERNAME:lab_user}
    password: ${DB_PASSWORD}
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: public
    drop-first: false

logging:
  level:
    liquibase: INFO
~~~

Các placeholder trên biểu diễn giá trị cấu hình được cung cấp từ môi trường. Ví dụ local có thể dùng URL <code>jdbc:postgresql://localhost:5432/liquibase_lab</code>, username của database lab và secret được cấp an toàn. Không ghi password thật vào Git.

Giải thích:

| Thuộc tính | Ý nghĩa |
|---|---|
| <code>spring.datasource.url</code> | JDBC URL của database |
| <code>spring.datasource.username</code> | User kết nối |
| <code>spring.datasource.password</code> | Credential do môi trường cấp |
| <code>spring.liquibase.enabled</code> | Bật auto-run Liquibase |
| <code>spring.liquibase.change-log</code> | Master changelog |
| <code>spring.liquibase.default-schema</code> | Schema mặc định cho object khi change không chỉ rõ schema |
| <code>spring.liquibase.drop-first</code> | Có xóa object trước khi chạy hay không; phải giữ false cho bài lab thông thường |

Với PostgreSQL, schema <code>public</code> thường tồn tại sẵn, nhưng project thực tế có thể dùng schema riêng. Nếu dùng schema riêng, phải tạo/provision schema và cấp quyền phù hợp trước khi Liquibase tạo object.

### 5.1. Nếu dùng Spring Data JPA

Trong môi trường do Liquibase quản lý schema, cấu hình Hibernate theo hướng chỉ kiểm tra hoặc không can thiệp DDL. Ví dụ:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

<code>validate</code> yêu cầu Hibernate kiểm tra mapping so với schema hiện có; nó không thay Liquibase tạo bảng. Tùy ứng dụng, <code>none</code> cũng có thể được dùng. Tránh <code>update</code>, <code>create</code> hoặc <code>create-drop</code> trong môi trường mà Liquibase là nguồn quản lý schema chính.

## 6. Tạo master changelog

Tạo file <code>src/main/resources/db/changelog/db.changelog-master.yaml</code>:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true

  - include:
      file: changes/002-create-orders.yaml
      relativeToChangelogFile: true
~~~

Master changelog là điểm vào của Liquibase. Các file được include theo thứ tự. Ở ví dụ này, bảng customer được tạo trước bảng orders vì orders có khóa ngoại tham chiếu customer.

Lưu ý:

- Đường dẫn include phải tồn tại trong classpath.
- Giữ thứ tự theo dependency.
- Không include cùng một changelog nhiều lần nếu không có chủ đích.
- Không đổi đường dẫn hoặc logical file path của changeset đã triển khai tùy tiện vì filename là một phần định danh lịch sử.
- Khi thêm migration mới, ưu tiên thêm file/changelog mới và include ở vị trí phù hợp.

## 7. Viết changeset đầu tiên: tạo bảng customer

Tạo file <code>changes/001-create-customer.yaml</code>:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: orders-team
      comment: Create customer table for the first orders-service schema
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_customer
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(254)
                  constraints:
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(160)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  defaultValueComputed: CURRENT_TIMESTAMP
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer
~~~

Changeset có ba thành phần định danh quan trọng:

- <code>id</code>: mã duy nhất trong phạm vi tác giả và changelog.
- <code>author</code>: người/nhóm chịu trách nhiệm.
- Filename/logical file path: vị trí changelog chứa changeset.

Liquibase dùng định danh này để xác định changeset đã chạy hay chưa. Không tái sử dụng cùng bộ định danh cho một thay đổi khác.

### 7.1. Ý nghĩa các cột

| Cột | Thiết kế | Lý do |
|---|---|---|
| id | BIGINT, auto increment, primary key | Khóa định danh khách hàng |
| email | VARCHAR(254), NOT NULL | Ví dụ dữ liệu liên hệ; uniqueness cần quyết định theo nghiệp vụ |
| display_name | VARCHAR(160), NOT NULL | Tên hiển thị |
| created_at | TIMESTAMP, default current timestamp | Thời điểm tạo theo database |

Không phải mọi hệ thống đều nên dùng email làm khóa duy nhất. Nếu yêu cầu nghiệp vụ cần unique, hãy thêm constraint/index trong changeset riêng sau khi kiểm tra dữ liệu hiện hữu. Kiểu thời gian và semantics timezone cần được thống nhất với ứng dụng.

### 7.2. Rollback của changeset đầu

Block rollback minh họa thao tác xóa bảng vừa tạo. Đây là thao tác phá hủy dữ liệu nếu bảng đã được sử dụng. Chỉ thử rollback trên database lab hoặc môi trường được phép; không xem rollback dropTable là cách phục hồi dữ liệu production.

Một số change type Liquibase có thể sinh rollback tự động, nhưng khai báo rollback tường minh giúp người đọc thấy rõ ý định. Với thay đổi dữ liệu hoặc thao tác không đảo ngược, phải thiết kế phương án backup/forward fix riêng.

## 8. Viết changeset thứ hai: tạo bảng orders

Tạo file <code>changes/002-create-orders.yaml</code>:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-create-orders
      author: orders-team
      comment: Create orders table and reference customer
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_orders
                    nullable: false
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: order_number
                  type: VARCHAR(40)
                  constraints:
                    nullable: false
              - column:
                  name: total_amount
                  type: DECIMAL(14,2)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  defaultValueComputed: CURRENT_TIMESTAMP
                  constraints:
                    nullable: false

        - addForeignKeyConstraint:
            baseTableName: orders
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_orders_customer

        - createIndex:
            tableName: orders
            indexName: idx_orders_customer_id
            columns:
              - column:
                  name: customer_id
      rollback:
        - dropTable:
            tableName: orders
~~~

Vì <code>customer</code> được tạo trong changeset trước, khóa ngoại có thể tham chiếu tới khóa chính. Changelog master phải include file 001 trước file 002. Nếu đảo thứ tự, migration có thể thất bại do bảng tham chiếu chưa tồn tại.

### 8.1. Vì sao có index trên customer_id?

Index giúp các truy vấn lọc đơn hàng theo khách hàng và có thể hỗ trợ một số thao tác kiểm tra khóa ngoại tùy DBMS. Tuy nhiên, index làm tăng chi phí ghi và dung lượng. Thiết kế index phải dựa trên truy vấn thực tế; bài lab chỉ dùng một index minh họa.

### 8.2. Constraint và dữ liệu

Foreign key bảo đảm mỗi <code>customer_id</code> trong orders tham chiếu tới một customer tồn tại. NOT NULL bảo đảm đơn hàng luôn gắn khách hàng. Khi triển khai trên bảng đã có dữ liệu, cần kiểm tra orphan records trước khi thêm FK. Trong bài lab database còn rỗng nên không có dữ liệu cũ cần chuyển đổi.

## 9. Chạy ứng dụng lần đầu

Từ thư mục project, chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Khi khởi động:

1. Spring Boot nạp application.yaml.
2. DataSource kết nối PostgreSQL.
3. Liquibase đọc master changelog.
4. Liquibase kiểm tra bảng lịch sử và lock.
5. Liquibase chạy changeset 001, sau đó changeset 002.
6. Liquibase ghi kết quả vào DATABASECHANGELOG.
7. Application context hoàn tất nếu không có lỗi khác.

Nếu database không truy cập được hoặc changelog sai, ứng dụng có thể không khởi động thành công. Đây là hành vi fail-fast thường mong muốn khi ứng dụng không thể làm việc với schema bắt buộc.

### 9.1. Đọc log khởi động

Log thường cho biết Liquibase đã khởi tạo, kiểm tra lock, thực hiện changeset và hoàn tất update. Cấu trúc thông điệp thay đổi theo phiên bản. Không phụ thuộc chính xác vào một dòng log; hãy xác minh bằng trạng thái database.

Không bật DEBUG/TRACE vô thời hạn để xem migration. Log production cần tránh credential, URL nhạy cảm và dữ liệu nghiệp vụ.

## 10. Xác minh schema sau lần chạy đầu

Kết nối database lab và kiểm tra bảng:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('customer', 'orders')
ORDER BY table_name;
~~~

Kiểm tra cột:

~~~sql
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('customer', 'orders')
ORDER BY table_name, ordinal_position;
~~~

Kiểm tra constraint:

~~~sql
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type
FROM information_schema.table_constraints AS tc
WHERE tc.table_schema = 'public'
  AND tc.table_name IN ('customer', 'orders')
ORDER BY tc.table_name, tc.constraint_type;
~~~

Kiểm tra index:

~~~sql
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('customer', 'orders')
ORDER BY tablename, indexname;
~~~

Các truy vấn cuối dùng catalog PostgreSQL. Nếu dùng DBMS khác, thay bằng catalog view tương ứng. Kết quả mong đợi có hai bảng, khóa chính cho từng bảng, foreign key orders.customer_id tham chiếu customer.id và index customer_id.

## 11. Đọc DATABASECHANGELOG và DATABASECHANGELOGLOCK

Liquibase thường tạo hai bảng metadata trong schema được cấu hình hoặc schema mặc định theo DBMS/tích hợp.

### 11.1. Xem changeset đã chạy

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

Bạn sẽ thấy các changeset như <code>001-create-customer</code> và <code>002-create-orders</code> nếu cả hai đã chạy thành công. Tên cột có thể khác cách viết hoa/thường tùy DBMS và cấu hình.

Các trường có ý nghĩa:

- <code>ID</code>, <code>AUTHOR</code>, <code>FILENAME</code>: định danh changeset.
- <code>DATEEXECUTED</code>: thời điểm Liquibase ghi nhận thực thi.
- <code>ORDEREXECUTED</code>: thứ tự áp dụng trong lịch sử.
- <code>EXECTYPE</code>: trạng thái thực thi, ví dụ EXECUTED hoặc các trạng thái khác theo trường hợp.
- <code>MD5SUM</code>: checksum nội dung changeset theo cơ chế Liquibase.

### 11.2. Xem lock

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM databasechangeloglock;
~~~

Sau khi migration hoàn tất bình thường, lock thường được giải phóng. Nếu thấy lock còn giữ, hãy xác định process và tình trạng migration trước khi can thiệp. Không tự xóa bảng lock hoặc cập nhật <code>locked=false</code> chỉ vì ứng dụng đang báo lỗi; thao tác sai có thể cho phép hai tiến trình cùng sửa schema.

### 11.3. History không thay thế kiểm tra object

DATABASECHANGELOG nói rằng Liquibase đã ghi nhận changeset. Nó không chứng minh object chưa bị DBA xóa hoặc sửa sau đó. Khi điều tra drift, cần đối chiếu history với catalog/DDL thực tế.

## 12. Khởi động lại ứng dụng và kiểm tra tính lặp an toàn

Dừng ứng dụng rồi khởi động lại:

~~~bash
./mvnw spring-boot:run
~~~

Liquibase đọc DATABASECHANGELOG, nhận ra hai changeset đã chạy và không tạo lại bảng. Đây là một trong những lợi ích quan trọng của migration có lịch sử: cùng một artifact có thể khởi động ở nhiều môi trường mà không chạy lặp changeset đã áp dụng.

Xác minh:

- Hai bảng vẫn tồn tại.
- Số bản ghi tương ứng của hai changeset trong DATABASECHANGELOG không tăng do restart.
- Không có lỗi “table already exists” từ changeset cũ.
- Lock được giải phóng sau khi Liquibase hoàn tất.

## 13. Thêm thay đổi mới đúng cách

Giả sử nghiệp vụ cần thêm cột <code>phone</code> vào customer. Không sửa changeset 001 đã chạy. Hãy tạo changeset mới, ví dụ file <code>003-add-customer-phone.yaml</code>:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-add-customer-phone
      author: orders-team
      comment: Add optional phone number to customer
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(32)
                  constraints:
                    nullable: true
~~~

Thêm file vào master changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-orders.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-add-customer-phone.yaml
      relativeToChangelogFile: true
~~~

Chạy lại ứng dụng. Liquibase bỏ qua hai changeset cũ và chỉ chạy changeset mới.

### 13.1. Quy tắc quan trọng

- Mỗi thay đổi mới có changeset mới.
- Không sửa changeset đã triển khai ở bất kỳ môi trường dùng chung nào.
- Không tái sử dụng id/author cho thay đổi khác trong cùng file identity.
- Giữ thứ tự dependency trong master changelog.
- Dùng precondition khi cần bảo vệ giả định về trạng thái database.
- Review SQL và tác động trước khi chạy production.

Nếu cần sửa một thay đổi đã triển khai, hãy tạo changeset khắc phục mới. Không xóa dòng history hoặc sửa checksum thủ công để che giấu khác biệt.

## 14. Hiểu checksum qua một tình huống thực hành

Checksum giúp Liquibase phát hiện nội dung changeset đã thay đổi sau khi được ghi nhận. Trong môi trường lab, có thể quan sát cơ chế bằng cách:

1. Chạy changeset 003 thành công.
2. Lưu lại trạng thái history.
3. Thay đổi một thuộc tính trong chính changeset 003 đã chạy, chẳng hạn độ dài cột.
4. Khởi động lại ứng dụng và quan sát cảnh báo/lỗi checksum validation.
5. Khôi phục file về nội dung đã triển khai hoặc tạo changeset mới cho yêu cầu thay đổi.

Đây là thử nghiệm trên project và database lab. Không thực hiện chỉnh sửa changeset lịch sử trên nhánh đã phát hành hoặc database dùng chung.

Checksum không phải checksum của toàn bộ schema vật lý. Nó giúp bảo vệ tính ổn định của định nghĩa changeset theo cơ chế Liquibase; nó không phát hiện mọi thay đổi thủ công ngoài Liquibase và không chứng minh dữ liệu đúng.

## 15. Thêm precondition cho một thay đổi có giả định

Precondition cho phép kiểm tra điều kiện trước khi changeset chạy. Ví dụ, chỉ thêm cột phone khi bảng customer tồn tại và cột đó chưa có:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-add-customer-phone-guarded
      author: orders-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: customer
        - not:
            - columnExists:
                tableName: customer
                columnName: phone
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: phone
                  type: VARCHAR(32)
                  constraints:
                    nullable: true
~~~

Ví dụ này minh họa cú pháp và cách đặt điều kiện. Không thêm changeset 004 trong bài lab nếu changeset 003 đã tạo cùng cột phone; hai changeset sẽ xung đột. Khi thực hành, chọn một trong hai thiết kế và dùng một changeset duy nhất cho thay đổi đó.

<code>HALT</code> làm migration dừng nếu điều kiện không đạt. Đây thường là lựa chọn an toàn khi trạng thái database không đúng giả định. Không dùng <code>MARK_RAN</code> chỉ để bỏ qua lỗi khi chưa hiểu vì sao object đã tồn tại hoặc thiếu.

## 16. Xem SQL dự kiến trước khi cập nhật

Với Liquibase CLI được cấu hình cùng changelog và datasource, có thể sinh SQL dự kiến bằng lệnh phù hợp phiên bản, thường là <code>update-sql</code> hoặc <code>updateSQL</code>.

~~~bash
liquibase --defaults-file=./liquibase-lab.properties validate
liquibase --defaults-file=./liquibase-lab.properties status --verbose
liquibase --defaults-file=./liquibase-lab.properties update-sql
~~~

Đây là ví dụ CLI; tên lệnh và cách cấu hình phụ thuộc phiên bản. Nếu dùng Spring Boot auto-run, việc sinh preview bằng CLI vẫn cần cùng changelog, parameters, context/label, DBMS và trạng thái database như lúc chạy thật.

Khi review SQL:

- Xác nhận schema và bảng đích.
- Kiểm tra lệnh CREATE/ALTER/DROP.
- Xem thứ tự tạo bảng và constraint.
- Kiểm tra default, nullability, precision và index.
- Tìm thao tác có thể xóa hoặc biến đổi dữ liệu.
- Xác định DDL có thể giữ lock lâu hay không.

Không đưa password vào command line, changelog hoặc file preview. SQL preview có thể chứa literal từ changeset nên cần được bảo vệ theo quyền truy cập và retention phù hợp.

## 17. Thử rollback trong database lab

Với changeset tạo bảng đơn giản, có thể thử rollback bằng lệnh Liquibase phù hợp phiên bản, ví dụ rollback theo tag hoặc số changeset. Trước khi rollback, hãy đọc SQL dự kiến và xác nhận database chỉ chứa dữ liệu lab.

Một cách tổ chức thực tế là tạo tag sau một mốc triển khai, rồi thử rollback về tag trong database có thể xóa và tạo lại. Cú pháp tag/rollback phụ thuộc phiên bản Liquibase và cách nhóm quản lý release.

Các nguyên tắc:

- Rollback chỉ đảo được những thao tác có logic đảo ngược phù hợp.
- Drop table/column có thể làm mất dữ liệu.
- Rollback DDL không tự khôi phục backup.
- Một số DDL có hành vi transaction riêng theo DBMS.
- Với thay đổi dữ liệu không thể đảo, cần forward fix hoặc restore.

Không thử rollback destructive trên database chia sẻ hoặc production khi chưa có kế hoạch phục hồi được phê duyệt.

## 18. Lỗi thường gặp trong bài thực hành

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Spring Boot không kết nối database | URL, port, database hoặc credential sai | Kiểm tra connection bằng client và cấu hình runtime |
| Không tìm thấy master changelog | Sai classpath hoặc tên file | Kiểm tra vị trí trong src/main/resources và change-log property |
| YAML parse error | Thụt lề hoặc kiểu dữ liệu sai | Kiểm tra indentation và cấu trúc YAML |
| Bảng orders không tạo được | Changeset chạy trước customer hoặc FK sai | Kiểm tra include order và referenced key |
| Table already exists | Object được tạo ngoài Liquibase hoặc history không phản ánh object | Kiểm tra catalog và DATABASECHANGELOG trước khi sửa |
| Checksum validation failed | Changeset đã chạy bị sửa | Khôi phục nội dung lịch sử hoặc tạo changeset mới |
| Liquibase chờ lock | Một tiến trình khác đang giữ DATABASECHANGELOGLOCK | Xác định process và trạng thái migration |
| Hibernate báo schema mismatch | Mapping không khớp schema hoặc ddl-auto cấu hình sai | Kiểm tra changelog và Hibernate validation |
| Ứng dụng không startup dù migration thành công | Lỗi ở bean hoặc dependency khác | Đọc nguyên nhân gốc sau log Liquibase |
| Chạy lại không thấy thay đổi mới | Chưa include file mới hoặc changeset đã có trong history | Kiểm tra master changelog và status |

Không xóa DATABASECHANGELOG, DATABASECHANGELOGLOCK hoặc bản ghi changeset để “làm sạch” lỗi. Trước tiên xác định trạng thái vật lý và lịch sử; sửa nguyên nhân bằng changeset có kiểm soát.

## 19. Tích hợp vào quy trình phát triển nhóm

Khi bài lab chuyển thành dự án thật:

1. Changelog nằm trong source control cùng ứng dụng hoặc repository migration có owner rõ.
2. Mỗi thay đổi schema được thêm bằng changeset mới.
3. Pull request review cả changelog, SQL preview và tác động dữ liệu.
4. CI chạy validate và các kiểm tra phù hợp.
5. Staging chạy migration trên DBMS/version tương ứng.
6. Production dùng migration job hoặc startup strategy đã được quyết định rõ.
7. Sau triển khai, xác minh schema, dữ liệu và DATABASECHANGELOG.

### 19.1. Phân biệt môi trường local và production

Local có thể dùng startup auto-run để tạo schema nhanh. Production có thể cần migration job riêng nhằm tách quyền DDL, approval và thời gian triển khai khỏi vòng đời từng replica.

Dù chọn cách nào, cần bảo đảm:

- Chỉ có chủ thể được chỉ định chạy migration.
- Artifact chứa changelog giống artifact đã review.
- Datasource và schema target chính xác.
- Secret được cấp qua cơ chế bảo mật.
- Log/SQL preview không tiết lộ thông tin nhạy cảm.
- Có phương án xử lý khi migration chạy một phần.

### 19.2. Không để Hibernate và Liquibase cùng sở hữu DDL

Nếu Liquibase là nguồn chuẩn, Hibernate nên validate hoặc không tự tạo schema. Hai công cụ cùng thay đổi DDL có thể làm kết quả phụ thuộc thứ tự startup và khiến lịch sử không đầy đủ.

## 20. Bài tập mở rộng

Sau khi hoàn thành hai bảng đầu tiên, thực hiện các nhiệm vụ sau trong database lab:

### Bài 1 — Thêm email unique

Thống kê dữ liệu trước, sau đó thêm unique constraint hoặc unique index cho customer.email bằng changeset mới. Giải thích vì sao cần kiểm tra duplicate trước khi enforce.

### Bài 2 — Thêm cột trạng thái đơn hàng

Thêm cột <code>status</code> nullable, xác định giá trị mặc định có đúng nghiệp vụ không và mô tả cách backfill nếu bảng đã có dữ liệu.

### Bài 3 — Tạo view báo cáo

Thêm view kết hợp orders với customer. Xác định dependency và cách thay đổi view trong một changeset mới.

### Bài 4 — Mô phỏng checksum mismatch

Chạy changeset trong lab, sửa nội dung sau đó quan sát lỗi, rồi khôi phục file. Viết giải thích vì sao phải thêm changeset mới cho thay đổi tiếp theo.

### Bài 5 — Mô phỏng môi trường thứ hai

Tạo database lab thứ hai, chạy cùng artifact và xác nhận cùng changelog tạo cùng cấu trúc. So sánh DATABASECHANGELOG giữa hai database.

### Bài 6 — Chuẩn bị migration job

Tắt auto-run trong profile ứng dụng thử nghiệm và cấu hình một job Liquibase riêng. Xác định pipeline cần validate, status, SQL preview, update và verify theo thứ tự nào.

## 21. Checklist hoàn thành bài lab

- [ ] Project Spring Boot có Liquibase và PostgreSQL driver.
- [ ] Database lab đã tồn tại và user có quyền phù hợp.
- [ ] Datasource URL, username và password được cấu hình an toàn.
- [ ] <code>spring.liquibase.enabled</code> và master changelog đúng.
- [ ] Master changelog include đúng thứ tự file.
- [ ] Changeset customer tạo đúng bảng và khóa chính.
- [ ] Changeset orders tạo đúng bảng, khóa ngoại và index.
- [ ] Lần startup đầu chạy đủ changeset.
- [ ] DATABASECHANGELOG có bản ghi tương ứng.
- [ ] DATABASECHANGELOGLOCK được giải phóng sau khi chạy.
- [ ] Restart không chạy lại changeset cũ.
- [ ] Thay đổi schema mới được thêm bằng changeset mới.
- [ ] Đã hiểu checksum và không sửa changeset đã triển khai.
- [ ] Đã review SQL preview và thử rollback chỉ trên database lab.
- [ ] Hibernate không tự thay đổi schema song song nếu Liquibase là owner.
- [ ] Đã xác định chiến lược startup hoặc migration job cho môi trường triển khai.

## 22. Kết luận

Một project Spring Boot tích hợp Liquibase bắt đầu từ ba thành phần: datasource kết nối đúng database, master changelog xác định thứ tự và các changeset mô tả thay đổi có định danh. Khi ứng dụng khởi động, Liquibase so sánh changelog với DATABASECHANGELOG, lấy lock, chạy changeset pending và ghi lịch sử. Nhờ đó, restart không tạo lại object và mỗi môi trường có thể tiến tới cùng một phiên bản schema từ cùng artifact.

Hãy giữ changeset đã triển khai bất biến, thêm thay đổi bằng changeset mới, review SQL trước khi áp dụng và kiểm tra catalog cùng lịch sử sau khi chạy. Preconditions bảo vệ giả định, checksum giúp phát hiện sửa đổi lịch sử, rollback cần được đánh giá theo khả năng phục hồi dữ liệu và DBMS. Khi chuyển từ lab sang production, cần chọn rõ startup migration hay job riêng, quản lý credential, quyền DDL, log và xử lý partial failure. Đó là nền tảng để dùng Liquibase có kiểm chứng trong ứng dụng Spring Boot và quy trình CI/CD.
