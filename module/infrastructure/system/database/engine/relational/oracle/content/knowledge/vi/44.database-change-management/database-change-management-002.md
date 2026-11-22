# Flyway/Liquibase với Oracle và thứ tự thực hiện migration

Migration quản lý những thay đổi có phiên bản đối với schema và dữ liệu của database. Khi ứng dụng Oracle phát triển, các thay đổi như tạo bảng, thêm cột, đổi constraint, tạo sequence, cập nhật dữ liệu tham chiếu hoặc thay package PL/SQL cần được thực hiện theo một thứ tự xác định và có thể truy vết. Flyway và Liquibase giúp đưa các thay đổi đó vào source control, tự động áp dụng theo môi trường và lưu lại lịch sử đã chạy.

Oracle có một đặc điểm quan trọng ảnh hưởng trực tiếp đến migration: nhiều câu lệnh DDL tự commit. Vì vậy, không thể giả định toàn bộ một file migration sẽ được rollback như một giao dịch DML thông thường. Cần thiết kế thứ tự phụ thuộc, chia nhỏ thay đổi, chuẩn bị cách phục hồi và kiểm tra trạng thái schema sau mỗi lần chạy.

## 1. Migration giải quyết vấn đề gì?

Không dùng công cụ migration, nhóm vận hành thường nhận các file SQL rời rạc qua email hoặc ticket. Người thực hiện phải tự xác định file nào chạy trước, môi trường nào đã chạy, có chạy lặp lại hay chưa và có cần bỏ qua thay đổi nào không. Cách làm này dễ dẫn đến schema khác nhau giữa development, test và production.

Một quy trình migration có kiểm soát cần trả lời được:

- Thay đổi nào thuộc phiên bản ứng dụng nào?
- Thay đổi nào đã được áp dụng trên database hiện tại?
- Thứ tự tạo bảng, khóa ngoại, index, dữ liệu và PL/SQL là gì?
- Nếu migration lỗi giữa chừng, database đang ở trạng thái nào?
- Làm sao xác nhận một schema đã đúng với mã nguồn migration?
- Làm sao triển khai cùng một thay đổi lên nhiều môi trường mà không chạy nhầm hoặc chạy lặp?

Flyway và Liquibase đều lưu lịch sử migration trong database. Mỗi công cụ có mô hình khai báo riêng, nhưng cả hai đều cần một nguyên tắc: migration đã áp dụng phải được xem là lịch sử bất biến. Khi cần sửa kết quả, tạo migration mới có phiên bản cao hơn thay vì sửa file cũ rồi chạy lại trên các môi trường.

## 2. Chọn Flyway hay Liquibase

| Tiêu chí | Flyway | Liquibase |
|---|---|---|
| Cách mô tả thay đổi | Chủ yếu là script SQL có phiên bản hoặc repeatable | Changelog XML, YAML, JSON hoặc SQL có định dạng Liquibase |
| Thứ tự | Phiên bản migration; repeatable chạy sau versioned | Thứ tự changeset trong changelog và cách include changelog |
| Lịch sử | Bảng schema history, mặc định thường là `flyway_schema_history` | `DATABASECHANGELOG` |
| Khóa cập nhật | Cơ chế khóa migration của Flyway | Bảng `DATABASECHANGELOGLOCK` |
| Kiểm tra trước khi chạy | `validate`, `info` và thử trên database riêng | `validate`, `updateSQL` và thử trên database riêng |
| Thay đổi có thể chạy lại | Repeatable migration, thường dùng cho view hoặc PL/SQL | `runOnChange`, `runAlways` và precondition |
| Cách quản lý rollback | Thường ưu tiên migration sửa tiến; tính năng undo phụ thuộc edition/cấu hình | Có thể khai báo rollback cho changeset, nhưng vẫn chịu giới hạn DDL của Oracle |

Flyway phù hợp khi nhóm muốn quản lý schema bằng các file SQL rõ ràng và thứ tự phiên bản đơn giản. Liquibase phù hợp khi cần changelog có cấu trúc, nhiều loại định dạng, precondition, context, label hoặc rollback được khai báo cùng thay đổi.

Không có công cụ nào tự làm cho migration Oracle trở nên nguyên tử. Chọn công cụ theo cách nhóm quản lý mã nguồn, kỹ năng SQL, nhu cầu kiểm soát triển khai và khả năng vận hành. Với một schema, nên có một công cụ làm nguồn sự thật duy nhất. Nếu Flyway và Liquibase cùng quản lý một schema mà không có ranh giới rõ ràng, mỗi công cụ chỉ nhìn thấy lịch sử riêng của nó và có thể áp dụng thay đổi trùng hoặc sai thứ tự.

## 3. Những đặc điểm Oracle phải hiểu trước khi viết migration

### 3.1. DDL tự commit

Oracle thực hiện implicit commit trước và sau nhiều câu lệnh DDL, ví dụ `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`, `CREATE SEQUENCE`, `CREATE OR REPLACE VIEW` và `CREATE OR REPLACE PACKAGE`. Vì vậy, một migration gồm nhiều câu lệnh DDL có thể đã tạo được một số object trước khi câu lệnh sau thất bại.

Ví dụ:

```sql
CREATE TABLE customer (
  customer_id NUMBER PRIMARY KEY,
  customer_name VARCHAR2(200 CHAR)
);

ALTER TABLE customer ADD status VARCHAR2(20 CHAR);

CREATE INDEX ix_customer_status ON customer(status);
```

Nếu câu lệnh tạo index lỗi, bảng và cột đã được tạo có thể vẫn tồn tại. Rollback giao dịch ở tầng ứng dụng không tự xóa những object đó. Công cụ migration cũng không thể biến DDL Oracle thành một giao dịch có thể rollback đầy đủ.

Hệ quả khi thiết kế:

- Chia migration theo thay đổi nhỏ và có ý nghĩa; tránh gom hàng chục thay đổi không liên quan vào một file.
- Kiểm tra trước điều kiện về object, quyền, dung lượng và phụ thuộc.
- Chuẩn bị hướng xử lý nếu một phần DDL đã commit nhưng công cụ chưa ghi nhận migration thành công.
- Dùng migration tiến để sửa trạng thái sau sự cố, hoặc khôi phục từ backup/clone theo kế hoạch đã được kiểm chứng.
- Không dựa vào nút rollback của công cụ như một cơ chế hoàn tác toàn bộ DDL.

### 3.2. DML và DDL có đặc tính giao dịch khác nhau

Các thao tác DML như `INSERT`, `UPDATE` và `DELETE` có thể tham gia giao dịch Oracle. Tuy nhiên, khi trộn DML với DDL trong cùng migration, DDL có thể commit phần DML đang chờ trước đó. Vì vậy, không viết một file với giả định mọi câu lệnh sẽ cùng rollback khi có lỗi.

Không đặt `COMMIT` tùy tiện trong migration. Với migration DML thông thường, hãy để công cụ quản lý transaction theo cấu hình của nó. Với backfill lớn cần commit theo lô, nên thiết kế thành tiến trình dữ liệu riêng có checkpoint và khả năng tiếp tục, thay vì một thay đổi schema dài không thể quan sát.

### 3.3. PL/SQL có dấu chấm phẩy bên trong

Package, procedure, function, trigger và anonymous PL/SQL block chứa nhiều dấu chấm phẩy bên trong thân chương trình. Dấu `/` trên một dòng riêng là lệnh phân cách của SQL*Plus/SQLcl, không phải một phần của câu lệnh SQL được gửi trực tiếp qua JDBC.

Với migration chạy qua JDBC, phải dùng parser và delimiter phù hợp với phiên bản Flyway/Liquibase. Với Liquibase, có thể cấu hình `splitStatements: false` cho một changeset chỉ chứa một đơn vị PL/SQL để công cụ gửi nguyên khối cho Oracle. Với Flyway, dùng parser Oracle của phiên bản đang cài và kiểm tra cách parser nhận biết PL/SQL; không trộn quy ước SQL*Plus với quy ước JDBC một cách tùy tiện. Luôn thử script package/procedure trên đúng phiên bản công cụ trước khi triển khai.

Ví dụ một package specification:

```sql
CREATE OR REPLACE PACKAGE customer_api AS
  PROCEDURE set_status(
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2
  );
END customer_api;
```

Và package body:

```sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
  PROCEDURE set_status(
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2
  ) IS
  BEGIN
    UPDATE customer
       SET status = p_status
     WHERE customer_id = p_customer_id;
  END set_status;
END customer_api;
```

Khi dùng JDBC, các khối trên là từng câu lệnh riêng. Không thêm lệnh SQL*Plus `/` vào giữa nội dung PL/SQL trừ khi cấu hình parser của công cụ yêu cầu delimiter đó.

### 3.4. Schema trong Oracle gắn với user

Trong Oracle, schema là tập object thuộc một database user. Ví dụ, user `APP_OWNER` sở hữu bảng `CUSTOMER`, package `CUSTOMER_API` và sequence `CUSTOMER_SEQ`. Vì vậy, cần xác định migration chạy bằng user sở hữu schema hay một deployment user riêng có quyền thích hợp.

Tham số `CURRENT_SCHEMA` chỉ thay đổi cách Oracle phân giải tên object chưa ghi rõ owner; nó không cấp quyền và không chuyển quyền sở hữu object. Nếu chạy migration bằng tài khoản riêng, hãy cấp quyền cần thiết trực tiếp và xác định rõ schema đích, schema lưu bảng lịch sử, quyền tạo object và quota tablespace.

Đối với package chạy với quyền definer's rights, các quyền cần thiết trên object ở schema khác thường phải được cấp trực tiếp cho owner của package. Không giả định role của tài khoản đăng nhập sẽ tự cung cấp các quyền compile/runtime cần thiết cho stored PL/SQL.

## 4. Xác định thứ tự migration theo phụ thuộc

Thứ tự migration phải phản ánh quan hệ phụ thuộc giữa các object. Một thứ tự tham khảo cho schema ứng dụng mới:

1. Kiểm tra kết nối, user/schema, tablespace quota, quyền và cấu hình môi trường.
2. Tạo các kiểu dữ liệu dùng chung, sequence hoặc các object nền tảng cần thiết.
3. Tạo bảng gốc, cột và khóa chính.
4. Tạo bảng phụ thuộc, khóa ngoại, unique constraint và check constraint.
5. Tạo index phục vụ truy vấn và constraint.
6. Nạp dữ liệu tham chiếu tối thiểu mà object hoặc ứng dụng cần.
7. Tạo view, synonym và các object phụ thuộc vào bảng.
8. Cấp quyền cross-schema cần thiết trước khi compile package phụ thuộc.
9. Tạo package specification, procedure/function và package body theo thứ tự phụ thuộc.
10. Tạo trigger, job hoặc object vận hành sau khi các object mà chúng gọi đã tồn tại.
11. Backfill dữ liệu, kiểm tra constraint và xác nhận trạng thái object.

Đây là thứ tự định hướng, không phải một chuỗi cứng cho mọi ứng dụng. Ví dụ, view có thể cần tồn tại trước package sử dụng view; grant phải có trước khi compile package tham chiếu object ở schema khác; synonym phải có trước khi compile code dùng synonym. Hãy lập đồ thị phụ thuộc thực tế từ object và mã nguồn của dự án.

### 4.1. Tách thay đổi schema khỏi thay đổi dữ liệu lớn

Tạo cột, constraint và index là thay đổi schema. Cập nhật hàng triệu bản ghi là thay đổi dữ liệu. Hai loại thay đổi có thời gian chạy, khóa và phương án phục hồi khác nhau.

Với dữ liệu lớn, nên chia thành các giai đoạn:

- Thêm cấu trúc mới ở trạng thái tương thích với ứng dụng đang chạy, chẳng hạn thêm cột nullable.
- Triển khai ứng dụng có thể ghi hoặc đọc cả cấu trúc cũ và mới.
- Chạy backfill theo lô, ghi checkpoint và theo dõi số dòng đã xử lý.
- Kiểm tra dữ liệu sau backfill.
- Chuyển ứng dụng sang cấu trúc mới.
- Chỉ xóa cấu trúc cũ trong một migration phát hành sau khi không còn phiên bản ứng dụng nào phụ thuộc nó.

Mô hình này thường được gọi là expand-migrate-contract. Nó giúp giảm rủi ro khi ứng dụng có nhiều instance hoặc không thể dừng lâu để thay đổi schema.

### 4.2. Khóa ngoại và constraint trên bảng lớn

Khi thêm foreign key, unique constraint hoặc check constraint vào bảng đã có dữ liệu, cần xác định dữ liệu cũ có thỏa điều kiện hay không. Với bảng lớn, việc xác thực constraint có thể tốn thời gian và ảnh hưởng đến tải.

Oracle hỗ trợ các trạng thái constraint như `ENABLE NOVALIDATE` trong những tình huống phù hợp: dữ liệu cũ chưa được xác thực nhưng DML mới vẫn bị kiểm tra theo constraint. Sau khi làm sạch dữ liệu, có thể xác thực constraint bằng `ENABLE VALIDATE`. Phải hiểu rõ trạng thái constraint trước khi coi migration là hoàn tất; `NOVALIDATE` không chứng minh toàn bộ dữ liệu cũ hợp lệ.

## 5. Tổ chức migration bằng Flyway

### 5.1. Cấu trúc file và quy tắc phiên bản

Flyway thường dùng hai loại migration:

- **Versioned migration:** tên bắt đầu bằng `V`, có phiên bản duy nhất và được chạy theo thứ tự phiên bản tăng dần.
- **Repeatable migration:** tên bắt đầu bằng `R__`, được chạy lại khi nội dung thay đổi; thường dùng cho view, package hoặc procedure được quản lý từ source.

Ví dụ cấu trúc:

```text
db/
  migration/
    oracle/
      V001__create_customer_table.sql
      V002__add_customer_status.sql
      V003__create_customer_sequence.sql
      V004__insert_customer_status_reference.sql
      R__customer_summary_view.sql
      R__customer_api_package.sql
```

Ví dụ migration tạo bảng:

```sql
-- V001__create_customer_table.sql
CREATE TABLE customer (
  customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
  customer_name VARCHAR2(200 CHAR) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT pk_customer PRIMARY KEY (customer_id)
);
```

Identity column cần release Oracle hỗ trợ tính năng này. Nếu ứng dụng phải tương thích với release cũ hơn, dùng sequence và cách cấp khóa phù hợp với kiến trúc ứng dụng thay vì giả định mọi phiên bản đều hỗ trợ cú pháp identity.

Migration tiếp theo có thể thêm cột:

```sql
-- V002__add_customer_status.sql
ALTER TABLE customer
  ADD status VARCHAR2(20 CHAR);

UPDATE customer
   SET status = 'ACTIVE'
 WHERE status IS NULL;

ALTER TABLE customer
  MODIFY status DEFAULT 'ACTIVE';
```

Ví dụ này minh họa thứ tự thêm cột, backfill và đặt default. Trên bảng lớn, không nên mặc định chạy một lệnh UPDATE toàn bảng trong migration triển khai đồng bộ; hãy đánh giá thời gian khóa, redo/undo, dung lượng và tách backfill thành job theo lô nếu cần. Nếu cần ràng buộc NOT NULL, chỉ thêm sau khi đã xác nhận dữ liệu hợp lệ và kế hoạch khóa phù hợp.

Tên phiên bản có thể dùng số thứ tự như `V001`, `V002` hoặc quy ước phiên bản của nhóm như `V2026.11.14.1`. Điều quan trọng là phiên bản duy nhất, tăng đơn điệu và không phụ thuộc thứ tự chữ cái của tên file. Không sửa hoặc đổi tên một versioned migration đã được áp dụng trên bất kỳ môi trường dùng chung nào.

### 5.2. Repeatable migration cho object có thể thay thế

View và package thường được tạo bằng `CREATE OR REPLACE`. Nếu source của object thay đổi, một repeatable migration có thể cập nhật định nghĩa đó:

```sql
-- R__customer_summary_view.sql
CREATE OR REPLACE VIEW customer_summary AS
SELECT status, COUNT(*) AS customer_count
FROM customer
GROUP BY status;
```

Repeatable migration chạy sau các versioned migration đang chờ áp dụng. Vì vậy, bảng và cột mà view cần phải được tạo trong versioned migration trước. Với package có nhiều phụ thuộc, cần bảo đảm specification, body và object liên quan được triển khai đúng thứ tự; không dựa vào thứ tự ngẫu nhiên giữa các repeatable file.

Không dùng repeatable migration cho dữ liệu nghiệp vụ cần áp dụng đúng một lần như tạo tài khoản, nạp giao dịch hoặc cộng dồn số dư. Những thay đổi đó cần versioned migration hoặc quy trình dữ liệu có kiểm soát.

### 5.3. Cấu hình kết nối Oracle

Ví dụ cấu hình cơ bản trong file cấu hình Flyway:

```properties
flyway.url=jdbc:oracle:thin:@//dbhost:1521/appsvc
flyway.user=APP_OWNER
flyway.schemas=APP_OWNER
flyway.defaultSchema=APP_OWNER
flyway.locations=filesystem:db/migration/oracle
flyway.table=flyway_schema_history
```

URL dùng service name của Oracle theo dạng `jdbc:oracle:thin:@//host:port/service_name`. Nếu môi trường dùng SID hoặc cấu hình TNS, URL sẽ khác và cần theo chuẩn kết nối của hệ thống.

Không lưu mật khẩu production trong file cấu hình được commit vào Git. Truyền bí mật bằng secret store, biến môi trường hoặc cơ chế bảo mật của pipeline. Giới hạn user migration vào đúng schema và quyền cần thiết.

Tùy phiên bản và cách phân phối Flyway, Oracle database support có thể cần module Oracle riêng bên cạnh core; driver JDBC Oracle cũng phải tương thích với JDK, database và phiên bản công cụ. Khóa version các thành phần này trong build để môi trường local và CI sử dụng cùng parser và driver.

### 5.4. Các lệnh vận hành thường dùng

Các lệnh Flyway phổ biến:

```text
flyway info
flyway validate
flyway migrate
flyway repair
```

- `info` hiển thị migration đã chạy, đang chờ hoặc trạng thái lịch sử.
- `validate` đối chiếu migration nguồn với lịch sử đã lưu, bao gồm checksum của versioned migration.
- `migrate` áp dụng migration đang chờ theo thứ tự.
- `repair` điều chỉnh metadata lịch sử trong các tình huống được hỗ trợ, ví dụ đồng bộ checksum hoặc xử lý một số bản ghi lịch sử.

`repair` không xóa bảng/cột đã được DDL tạo ra và không khôi phục dữ liệu. Trước khi chạy repair sau lỗi Oracle, phải xác định object nào đã được tạo, câu lệnh nào đã commit và lịch sử đang ghi nhận điều gì. Chỉ sửa metadata sau khi schema thực tế đã được đối soát.

Khi đưa Flyway vào một database đã có schema, có thể dùng baseline để đánh dấu một phiên bản mốc mà không chạy lại toàn bộ migration lịch sử. Chỉ baseline sau khi kiểm tra schema hiện tại thực sự tương ứng với phiên bản mốc. Không bật tự động baseline cho mọi database production mà không có điều kiện kiểm tra.

## 6. Tổ chức migration bằng Liquibase

### 6.1. Changelog và changeset

Liquibase quản lý thay đổi trong changelog. Mỗi changeset có định danh dựa trên `id`, `author` và đường dẫn changelog. Khi chạy, Liquibase ghi nhận changeset đã áp dụng trong `DATABASECHANGELOG`; việc khóa cập nhật được điều phối qua `DATABASECHANGELOGLOCK`.

Changelog có thể viết bằng XML, YAML, JSON hoặc formatted SQL. Với Oracle, formatted SQL hữu ích khi nhóm muốn dùng cú pháp SQL và PL/SQL gốc, còn XML/YAML hữu ích khi muốn biểu diễn thay đổi bằng các change type có cấu trúc.

Ví dụ formatted SQL:

```sql
--liquibase formatted sql

--changeset app:001 dbms:oracle
CREATE TABLE customer (
  customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
  customer_name VARCHAR2(200 CHAR) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT pk_customer PRIMARY KEY (customer_id)
);

--changeset app:002 dbms:oracle
ALTER TABLE customer ADD status VARCHAR2(20 CHAR);
```

Mỗi changeset nên chứa một thay đổi có ý nghĩa và có thể xác định rõ trạng thái sau khi chạy. Tránh gộp nhiều object không liên quan vào một changeset chỉ để giảm số dòng changelog.

### 6.2. Khai báo PL/SQL và delimiter

Với package, procedure hoặc trigger, cần ngăn Liquibase tách câu lệnh tại các dấu chấm phẩy bên trong thân PL/SQL. Một changeset chỉ chứa một package specification có thể được khai báo như sau:

```sql
--liquibase formatted sql
--changeset app:010 dbms:oracle splitStatements:false
CREATE OR REPLACE PACKAGE customer_api AS
  PROCEDURE set_status(
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2
  );
END customer_api;
```

Package body nên ở changeset riêng:

```sql
--liquibase formatted sql
--changeset app:011 dbms:oracle splitStatements:false
CREATE OR REPLACE PACKAGE BODY customer_api AS
  PROCEDURE set_status(
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2
  ) IS
  BEGIN
    UPDATE customer
       SET status = p_status
     WHERE customer_id = p_customer_id;
  END set_status;
END customer_api;
```

Ở ví dụ này, mỗi changeset gửi một đơn vị PL/SQL như một statement. Nếu dùng XML/YAML hoặc `sqlFile`, cấu hình tương ứng `splitStatements` và `endDelimiter` theo tài liệu của phiên bản Liquibase đang chạy. Không đưa lệnh SQL*Plus `/` vào nội dung JDBC nếu parser đang gửi nguyên statement.

### 6.3. runOnChange, runAlways và precondition

Một số thuộc tính giúp điều khiển cách changeset được xử lý:

- `runOnChange: true` chạy lại changeset khi checksum thay đổi. Có thể dùng cho view hoặc package được quản lý như source có thể thay thế.
- `runAlways: true` chạy changeset ở mỗi lần update. Chỉ dùng khi việc lặp lại đã được thiết kế rõ ràng và an toàn.
- `preConditions` kiểm tra điều kiện trước khi áp dụng, chẳng hạn database là Oracle, bảng đã tồn tại hoặc cột chưa tồn tại.
- `context` và `labels` chọn nhóm changeset theo môi trường hoặc mục đích triển khai.

Ví dụ:

```xml
<changeSet id="020-add-customer-status" author="app">
    <preConditions onFail="HALT">
        <dbms type="oracle"/>
        <not>
            <columnExists tableName="CUSTOMER" columnName="STATUS"/>
        </not>
    </preConditions>
    <addColumn tableName="CUSTOMER">
        <column name="STATUS" type="VARCHAR2(20 CHAR)"/>
    </addColumn>
</changeSet>
```

Precondition giúp phát hiện schema không đúng trạng thái mong đợi. Không dùng `onFail="MARK_RAN"` như cách bỏ qua mọi lỗi: nếu object thiếu hoặc sai trạng thái, đánh dấu changeset đã chạy có thể làm lịch sử nói rằng schema đã cập nhật trong khi thực tế chưa đúng.

### 6.4. Rollback và metadata

Liquibase cho phép khai báo rollback cho changeset. Với thay đổi DML hoặc một số thay đổi schema có thể đảo ngược rõ ràng, rollback có thể hữu ích. Tuy nhiên, rollback SQL vẫn phải thực thi được trên Oracle và không xóa dữ liệu hợp lệ được tạo sau migration.

Vì DDL Oracle có implicit commit, khai báo rollback không biến DDL thành transaction có thể hoàn tác tự động. Cần viết rollback tường minh, thử trên bản sao dữ liệu và xác định điều kiện trước khi chạy. Với thay đổi phá hủy như drop column hoặc chuyển đổi dữ liệu mất thông tin, phương án an toàn thường là backup/restore hoặc migration tiến có bước chuyển đổi ngược riêng.

Các lệnh thường dùng:

```text
liquibase validate
liquibase updateSQL
liquibase update
liquibase status
liquibase release-locks
liquibase clear-checksums
```

- `validate` kiểm tra changelog và cấu trúc changeset.
- `updateSQL` tạo SQL dự kiến để xem xét trước khi áp dụng.
- `update` thực thi changeset đang chờ.
- `status` hiển thị changeset chưa được triển khai.
- `release-locks` giải phóng khóa metadata khi đã xác nhận không còn tiến trình update đang chạy.
- `clear-checksums` xóa checksum đã lưu để Liquibase tính lại ở lần chạy sau; đây không phải cách sửa schema drift.

Nếu update bị gián đoạn và lock còn giữ, trước tiên kiểm tra tiến trình migration và trạng thái database. Chỉ release lock sau khi chắc chắn không có một tiến trình hợp lệ đang chạy. Không xóa bảng `DATABASECHANGELOG` hoặc `DATABASECHANGELOGLOCK` để giải quyết lỗi thông thường.

### 6.5. Đặt schema lưu lịch sử

Liquibase có thể dùng schema riêng cho bảng theo dõi. Phân biệt schema đích của object với schema chứa metadata Liquibase. Các cấu hình như `defaultSchemaName` và `liquibaseSchemaName` cần được khai báo nhất quán trong pipeline. User chạy migration phải có quyền đọc/ghi bảng lịch sử và quyền tạo/sửa object ở schema đích.

Không đổi đường dẫn hoặc định danh changelog tùy tiện sau khi changeset đã chạy, vì Liquibase dùng định danh và vị trí changelog để đối chiếu lịch sử. Khi đổi cấu trúc thư mục, dùng cơ chế logical path hoặc quy trình chuyển đổi phù hợp để giữ định danh ổn định.

## 7. Cấu trúc thứ tự migration thực tế cho Oracle

Một cấu trúc thư mục dễ theo dõi:

```text
database/
  oracle/
    001-foundation/
      V001__create_reference_types.sql
      V002__create_customer.sql
      V003__create_order.sql
    002-constraints/
      V004__add_customer_order_fk.sql
      V005__add_order_indexes.sql
    003-reference-data/
      V006__insert_customer_statuses.sql
    004-program-units/
      V007__create_customer_api.sql
      V008__create_order_api.sql
    repeatable/
      R__customer_summary_view.sql
      R__customer_api_package.sql
    data-jobs/
      backfill_customer_status.sql
```

Với Flyway, các file versioned thực tế thường được đặt cùng location và được sắp theo version. Thư mục con ở ví dụ thể hiện cách nhóm thiết kế; cần cấu hình locations phù hợp hoặc dùng một location duy nhất theo quy ước của dự án. Với Liquibase, các file có thể được include từ changelog gốc theo đúng thứ tự mong muốn.

Ví dụ changelog gốc Liquibase:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-order.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-customer-order-fk.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/004-customer-api.yaml
      relativeToChangelogFile: true
```

Thứ tự include là một phần của thiết kế. Nếu package API tham chiếu bảng `CUSTOMER`, bảng và các quyền cần thiết phải tồn tại trước changeset package. Nếu view phụ thuộc một cột mới, migration tạo cột phải đứng trước lần cập nhật view.

### 7.1. Tạo bảng, sequence và khóa ngoại

Nếu không dùng identity column, có thể tạo sequence riêng:

```sql
CREATE TABLE customer (
  customer_id NUMBER NOT NULL,
  customer_name VARCHAR2(200 CHAR) NOT NULL,
  CONSTRAINT pk_customer PRIMARY KEY (customer_id)
);

CREATE SEQUENCE customer_seq
  START WITH 1
  INCREMENT BY 1
  CACHE 100;
```

Ứng dụng có thể lấy khóa bằng `customer_seq.NEXTVAL`. Sequence là object độc lập và giá trị sequence không tham gia rollback như một cột dữ liệu thông thường; việc có khoảng trống trong dãy số là bình thường. Không dùng sequence để chứng minh số bản ghi liên tục.

Tạo bảng phụ thuộc sau bảng cha:

```sql
CREATE TABLE customer_order (
  order_id NUMBER NOT NULL,
  customer_id NUMBER NOT NULL,
  order_total NUMBER(14,2) NOT NULL,
  CONSTRAINT pk_customer_order PRIMARY KEY (order_id)
);

ALTER TABLE customer_order
  ADD CONSTRAINT fk_order_customer
  FOREIGN KEY (customer_id)
  REFERENCES customer(customer_id);

CREATE INDEX ix_order_customer
  ON customer_order(customer_id);
```

Index trên cột khóa ngoại có thể giúp một số truy vấn và thao tác parent-row tránh quét bảng con, nhưng cần quyết định dựa trên workload và thiết kế index tổng thể. Không tạo index trùng với index đã được constraint tạo ra.

### 7.2. Nạp dữ liệu tham chiếu

Các giá trị danh mục như trạng thái đơn hàng hoặc loại khách hàng có thể được nạp bằng versioned migration:

```sql
INSERT INTO customer_status (status_code, status_name)
VALUES ('ACTIVE', 'Active');

INSERT INTO customer_status (status_code, status_name)
VALUES ('INACTIVE', 'Inactive');
```

Versioned migration chỉ chạy một lần theo lịch sử công cụ, nên phù hợp với dữ liệu khởi tạo có phiên bản. Nếu một script có thể được chạy thủ công hoặc chạy lại trong quy trình phục hồi, cần bảo đảm tính idempotent bằng khóa duy nhất và điều kiện kiểm tra phù hợp. Tránh dùng `WHEN OTHERS THEN NULL` để nuốt mọi lỗi trùng dữ liệu; cách đó có thể che giấu lỗi quyền, kiểu dữ liệu hoặc constraint.

Nếu cần cập nhật nội dung danh mục ở lần phát hành sau, tạo migration mới có điều kiện xác định rõ bản ghi cần sửa. Không sửa file seed đã áp dụng trên production.

### 7.3. Cấp quyền và synonym

Nếu schema ứng dụng gọi package ở schema khác, grant phải được thực hiện trước khi compile code phụ thuộc:

```sql
GRANT SELECT ON reference_data.customer_status
  TO app_owner;

GRANT EXECUTE ON reference_data.customer_rules
  TO app_owner;

-- Chạy câu lệnh CREATE SYNONYM bằng APP_OWNER.
CREATE SYNONYM customer_status
  FOR reference_data.customer_status;
```

Thay owner và object bằng tên thực tế của hệ thống. Việc tạo synonym không cấp quyền; user vẫn cần privilege tương ứng trên object gốc. Với code PL/SQL chạy theo quyền chủ sở hữu, cấp quyền trực tiếp cho owner của chương trình khi cần.

## 8. Triển khai theo pipeline CI/CD

Một pipeline migration có thể chia thành các giai đoạn:

1. **Build:** đóng gói changelog hoặc SQL migration cùng phiên bản ứng dụng.
2. **Static validation:** kiểm tra tên file, version duy nhất, định dạng changelog, parser và các quy tắc nội bộ.
3. **Provision:** tạo database Oracle tạm hoặc PDB cô lập với release, edition, RU và cấu hình đã khóa.
4. **Preview:** dùng `liquibase updateSQL` hoặc công cụ xem kế hoạch phù hợp; với Flyway, dùng `info`, `validate` và thử migrate trên database dùng một lần.
5. **Apply:** chạy migration bằng một deployment job duy nhất với tài khoản và secret được cấp đúng quyền.
6. **Verify:** kiểm tra lịch sử migration, object invalid, dữ liệu, constraint và smoke test.
7. **Deploy application:** triển khai phiên bản ứng dụng tương thích với schema vừa cập nhật.
8. **Observe:** theo dõi lỗi SQL, thời gian phản hồi, lock, session và các chỉ số database sau phát hành.

Không nên để tất cả instance ứng dụng tự chạy migration khi khởi động nếu có thể tổ chức một job triển khai riêng. Nhiều pod khởi động đồng thời có thể tạo cuộc đua, làm khó quan sát lỗi và khiến thời gian khởi động ứng dụng phụ thuộc vào thay đổi schema. Dù công cụ có khóa, một migration job riêng vẫn giúp kiểm soát thứ tự giữa database và application release.

Trong production, thực hiện preflight về backup, dung lượng, quyền, thời gian khóa, tải hiện tại và cửa sổ triển khai. Với thay đổi có nguy cơ khóa bảng lớn, cần thử trên bản sao có dữ liệu gần thực tế và thống nhất phương án dừng/tiếp tục.

## 9. Đồng bộ database đã tồn tại với lịch sử migration

Nhiều hệ thống Oracle đã có schema trước khi đưa Flyway hoặc Liquibase vào. Không thể mặc định chạy toàn bộ migration lịch sử lên schema đó vì object có thể đã tồn tại.

Với Flyway, baseline ghi nhận một phiên bản mốc cho schema hiện có. Với Liquibase, `changelogSync` có thể đánh dấu các changeset phù hợp là đã thực thi mà không chạy nội dung SQL của chúng. Cả hai thao tác đều chỉ an toàn khi đã đối chiếu schema hiện tại với trạng thái mà mốc đó mô tả.

Quy trình tiếp nhận schema cũ:

1. Backup hoặc clone database để có thể đối chiếu và phục hồi.
2. Xuất inventory object, DDL, constraint, index, sequence, package, grant và synonym.
3. Xác định phiên bản logic của schema hiện tại.
4. Đối chiếu schema thực tế với trạng thái sau migration dự kiến.
5. Chọn baseline version hoặc danh sách changeset được đồng bộ.
6. Chạy validate/status và thử migration tiếp theo trên clone.
7. Chỉ sau khi xác nhận kết quả mới áp dụng metadata baseline vào môi trường thật.

Không dùng `baselineOnMigrate` hoặc `changelogSync` để bỏ qua một schema không rõ nguồn gốc. Việc đánh dấu migration đã chạy chỉ cập nhật lịch sử, không tạo object còn thiếu và không sửa object sai định nghĩa.

## 10. Xử lý migration lỗi trên Oracle

Khi một migration thất bại, không chạy lại ngay và cũng không xóa bảng lịch sử. Trước tiên xác định:

- Công cụ ghi migration là thành công, thất bại hay chưa có bản ghi?
- Câu lệnh nào đã chạy trước khi lỗi?
- Các DDL đã commit object nào?
- DML nào đã commit và DML nào còn rollback được?
- Object hiện tại có đúng định nghĩa mong muốn không?
- Có phiên migration khác đang giữ lock không?

Có thể kiểm tra object invalid:

```sql
SELECT owner,
       object_type,
       object_name,
       status
FROM all_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
```

Với object invalid, xem lỗi compile:

```sql
SELECT owner,
       name,
       type,
       line,
       position,
       text
FROM all_errors
ORDER BY owner, name, type, sequence;
```

Tùy quyền, có thể cần view `DBA_OBJECTS` và `DBA_ERRORS` để kiểm tra toàn database. Không coi việc migration tool ghi trạng thái thành công là bằng chứng duy nhất; object có thể invalid hoặc dữ liệu chưa đạt điều kiện nghiệp vụ.

Một trình tự khôi phục có kiểm soát:

1. Dừng các lần triển khai tiếp theo để tránh migration chồng lấn.
2. Chụp lại log, trạng thái metadata và inventory object hiện tại.
3. So sánh schema với trạng thái trước migration và trạng thái mong muốn.
4. Quyết định sửa tiếp bằng forward migration, chạy một script phục hồi có kiểm soát hoặc restore từ backup.
5. Chỉ cập nhật metadata Flyway/Liquibase sau khi schema thực tế đã được đối soát.
6. Chạy lại validate/status, kiểm tra object invalid, constraint và test ứng dụng.

Flyway `repair` và Liquibase `clear-checksums` tác động đến lịch sử/checksum, không phải công cụ rollback DDL. Liquibase `release-locks` chỉ dùng sau khi xác nhận không còn tiến trình migration đang hoạt động. Không xóa thủ công các bảng lịch sử để ép công cụ chạy lại.

## 11. Kiểm soát thay đổi và an toàn khi triển khai

### 11.1. Migration đã áp dụng là bất biến

Khi một versioned migration hoặc changeset đã được áp dụng trên môi trường dùng chung:

- Không sửa nội dung cũ để thay đổi kết quả mong muốn.
- Tạo migration mới có thứ tự sau để sửa schema hoặc dữ liệu.
- Giữ mã nguồn migration trong cùng repository và cùng quy trình review với ứng dụng.
- Kiểm tra checksum trước khi phát hành.
- Ghi nhận ai chạy, lúc nào, trên database nào và bằng phiên bản artifact nào.

Repeatable migration và changeset `runOnChange` là ngoại lệ có chủ đích cho object được thay thế từ source. Dù vậy, phải kiểm soát thay đổi nội dung, phụ thuộc và tác động của việc chạy lại.

### 11.2. Không dùng migration để thực hiện mọi tác vụ vận hành

Không phải mọi thao tác database đều nên là migration schema. Rebuild index, gather statistics, purge dữ liệu cũ, backfill hàng triệu dòng hoặc thay đổi tham số instance có thể cần quy trình vận hành riêng. Đưa chúng vào migration đồng bộ có thể làm thời gian deploy không dự đoán được hoặc tạo khóa kéo dài.

Nếu bắt buộc tự động hóa, tách bước vận hành khỏi bước schema, có timeout, log, checkpoint, giám sát và khả năng tiếp tục. Không để một lần chạy migration giữ transaction hoặc session lâu hơn cần thiết.

### 11.3. Bảo mật tài khoản migration

Tài khoản migration cần đủ quyền tạo/sửa object mà ứng dụng yêu cầu, nhưng không nên dùng `SYS` hoặc `SYSTEM` cho thay đổi schema ứng dụng. Tách quyền quản trị user/tablespace khỏi quyền triển khai schema khi kiến trúc cho phép. Không cấp quyền rộng cho `PUBLIC`; lưu secret trong hệ thống quản lý bí mật và luân chuyển theo chính sách.

Tài khoản runtime của ứng dụng thường chỉ cần quyền DML và execute cần thiết. Không dùng tài khoản migration có quyền DDL rộng làm tài khoản kết nối thường xuyên của ứng dụng.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Sửa versioned migration đã chạy | Checksum khác nhau giữa môi trường | Tạo migration mới để sửa |
| Coi DDL Oracle là transaction rollback được | Schema có thể còn object tạo dở | Kiểm tra từng DDL và chuẩn bị forward fix/restore |
| Tạo package trước bảng hoặc grant cần thiết | Package invalid hoặc compile thất bại | Sắp xếp theo đồ thị phụ thuộc |
| Dùng `/` như câu lệnh SQL JDBC | Parser hoặc driver có thể từ chối script | Cấu hình delimiter theo tool và gửi PL/SQL đúng dạng |
| Backfill toàn bảng trong lúc deploy | Thời gian khóa, redo/undo và tải tăng | Tách job theo lô có checkpoint |
| Chạy migration từ mọi instance ứng dụng | Khó kiểm soát concurrency và lỗi khởi động | Dùng một migration job riêng |
| Dùng `repair` để sửa schema đã tạo dở | Metadata thay đổi nhưng object vẫn sai | Đối soát schema trước, sau đó mới sửa lịch sử |
| Đánh dấu baseline cho schema chưa kiểm kê | Bỏ qua object hoặc constraint còn thiếu | So sánh DDL thực tế trước khi baseline |
| Dùng hai công cụ quản lý cùng schema | Hai lịch sử độc lập có thể xung đột | Chọn một nguồn sự thật cho schema |
| Dùng `MARK_RAN` hoặc nuốt lỗi rộng rãi | Lịch sử báo thành công dù schema chưa đúng | Dừng triển khai và xử lý điều kiện sai rõ ràng |

## 13. Checklist trước và sau một lần migration

**Trước khi chạy**

- [ ] Đã xác nhận đúng database, service, PDB, schema và release đích.
- [ ] Đã khóa phiên bản Flyway/Liquibase, Oracle JDBC driver và cấu hình parser.
- [ ] Đã kiểm tra migration version, checksum, changelog order và các file mới.
- [ ] Đã xác nhận quyền DDL, quota, tablespace và quyền metadata.
- [ ] Đã kiểm tra phụ thuộc bảng, sequence, constraint, grant, synonym và PL/SQL.
- [ ] Đã thử migration trên database clone có cấu hình gần production.
- [ ] Đã xem SQL dự kiến hoặc log thực thi và đánh giá thời gian khóa.
- [ ] Đã có backup/restore hoặc phương án forward fix phù hợp với thay đổi.
- [ ] Đã xác nhận chỉ có một migration job đang thực hiện trên schema.

**Sau khi chạy**

- [ ] Công cụ ghi nhận đúng version/changeset đã áp dụng.
- [ ] Không còn migration pending ngoài dự kiến.
- [ ] Object cần thiết tồn tại và object PL/SQL ở trạng thái hợp lệ.
- [ ] Constraint và index có trạng thái mong muốn.
- [ ] Dữ liệu backfill và dữ liệu tham chiếu đã được đối chiếu.
- [ ] Smoke test và kiểm thử tích hợp ứng dụng đã thành công.
- [ ] Không còn lock migration bị treo hoặc session triển khai bất thường.
- [ ] Log và artifact migration được lưu cùng release ứng dụng.

## 14. Quy tắc lựa chọn và vận hành

Flyway là lựa chọn tự nhiên khi nhóm muốn quản lý migration bằng SQL có phiên bản, lịch sử rõ và quy trình đơn giản. Liquibase phù hợp khi cần changelog có cấu trúc, precondition, context/label và rollback được khai báo. Dù chọn công cụ nào, hãy duy trì một nguồn sự thật cho mỗi schema, giữ migration đã áp dụng bất biến và thử mọi thay đổi trên database Oracle có cấu hình gần môi trường đích.

Với Oracle, thứ tự migration phải phản ánh phụ thuộc object và đặc tính implicit commit của DDL. Tạo cấu trúc nền trước, sau đó constraint, dữ liệu tham chiếu, grant, view và PL/SQL theo quan hệ phụ thuộc; tách backfill lớn khỏi bước deploy schema; cuối cùng kiểm tra metadata, object invalid, dữ liệu và ứng dụng. Một migration được ghi là thành công chỉ là một phần bằng chứng: schema thực tế vẫn cần được xác nhận trước khi phát hành tiếp.
