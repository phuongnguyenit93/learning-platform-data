# Thứ tự hoàn tác và phụ thuộc giữa các đối tượng

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chương **Hoàn tác**, vấn đề quan trọng khi rollback không chỉ là biết lệnh nào đảo ngược một thay đổi. **Các đối tượng database phụ thuộc lẫn nhau**: view tham chiếu bảng, khóa ngoại nối bảng con với bảng cha, chỉ mục phục vụ truy vấn hoặc constraint, trigger tham chiếu cột, còn dữ liệu được ứng dụng sử dụng qua nhiều phiên bản. Hoàn tác đúng thao tác nhưng **sai thứ tự** vẫn có thể thất bại hoặc làm mất dữ liệu.

Liquibase quản lý quá trình thay đổi schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và bảng lịch sử **DATABASECHANGELOG**. Những khả năng đó hỗ trợ triển khai, kiểm chứng và rollback có kiểm soát trên nhiều môi trường hoặc qua Spring Boot/CI/CD. Tuy nhiên, Liquibase không thể tự suy ra đầy đủ mọi phụ thuộc nghiệp vụ và mọi cách phục hồi dữ liệu. Người thiết kế migration phải xác định trạng thái trước–sau, quan hệ phụ thuộc và thứ tự hoàn tác an toàn.

Bài học tập trung vào **thứ tự hoàn tác và phụ thuộc giữa các đối tượng**: cách suy ra thứ tự từ changelog và lịch sử, cách đảo chuỗi thay đổi có khóa ngoại, chỉ mục, view, cột và dữ liệu; những trường hợp phải viết rollback tường minh; và quy trình thực hành kiểm chứng trên database đại diện.

## 1. Rollback là gì, và không phải là gì?

**Rollback** của Liquibase là quá trình đảo một tập changeset đã được triển khai theo mốc hoặc giới hạn do lệnh rollback xác định. Từng changeset phải có cơ chế đảo phù hợp, do Liquibase tự sinh khi change type hỗ trợ hoặc do tác giả khai báo tường minh.

Ba việc thường bị nhầm:

| Khái niệm | Ý nghĩa | Giới hạn |
|---|---|---|
| **Rollback changeset** | Đảo tác động của một changeset đã triển khai | Cần SQL đảo hợp lệ, đủ điều kiện dữ liệu và phụ thuộc |
| **Rollback release** | Đảo tập changeset thuộc phạm vi release, xét ngược thứ tự | Không bảo đảm đảo được mọi tác động bên ngoài DB |
| **Khôi phục database từ backup** | Phục hồi dữ liệu/trạng thái từ bản sao đã lưu | Có thể làm mất các giao dịch mới hơn mốc sao lưu; cần kế hoạch phục hồi riêng |

**Rollback không đồng nghĩa với “database sẽ trở lại y hệt trước khi deploy”.** Ví dụ:

- Xóa cột có thể làm mất dữ liệu; tạo lại cột không khôi phục được giá trị đã mất.
- Đảo lệnh đổi default không tự sửa dữ liệu mà ứng dụng đã ghi trong thời gian dùng default mới.
- Thả NOT NULL rồi để ứng dụng ghi NULL; khi thêm NOT NULL trở lại, câu ALTER có thể thất bại vì dữ liệu mới.
- Ứng dụng có thể đã gửi email hoặc sự kiện ra hệ thống khác; database rollback không thu hồi được những side effect đó.
- DDL có thể tự commit hoặc không hoàn tác theo transaction như DML, tùy DBMS.

Vì vậy, khi nói một rollback là *an toàn*, cần xét **thứ tự**, **khả năng đảo của từng bước**, **trạng thái dữ liệu hiện hành**, **hành vi DBMS** và **tương thích ứng dụng**.

## 2. Nguyên tắc cốt lõi: hoàn tác theo thứ tự ngược

Một chuỗi migration phụ thuộc nhau thường có logic triển khai:

~~~text
Bước A: Tạo bảng cha
   |
   v
Bước B: Tạo bảng con
   |
   v
Bước C: Tạo chỉ mục của bảng con
   |
   v
Bước D: Thêm khóa ngoại bảng con -> bảng cha
   |
   v
Bước E: Tạo view tham chiếu bảng cha và con
~~~

Nếu các bước này đã thực thi thành công, rollback hợp lý theo chuỗi **E → D → C → B → A**:

~~~text
Đầu tiên: Gỡ view
     |
     v
Gỡ khóa ngoại
     |
     v
Gỡ chỉ mục đã tạo ở bước C
     |
     v
Gỡ bảng con
     |
     v
Gỡ bảng cha
~~~

Cách hiểu quan trọng:

> **Phải gỡ những đối tượng đang phụ thuộc vào một đối tượng trước khi xóa đối tượng được phụ thuộc vào.**

Ví dụ, không nên thả bảng **customer** khi **sales_order** còn khóa ngoại tham chiếu tới nó hoặc view còn phụ thuộc vào customer. Một số DBMS sẽ chặn thao tác; một số cú pháp như **CASCADE** có thể xóa lan truyền những đối tượng phụ thuộc, nhưng điều này phải được kiểm soát rõ, không được mặc định dùng như đường tắt.

Liquibase thông thường xử lý rollback các **changeset được chọn** theo **thứ tự ngược với thứ tự đã triển khai**. Nhờ đó, nếu changelog được xây dựng theo thứ tự phụ thuộc hợp lý và rollback của từng changeset đúng, chuỗi hoàn tác thường tự nhiên phù hợp với quan hệ phụ thuộc. Tuy nhiên, **Liquibase không bảo đảm tự lập một đồ thị phụ thuộc toàn bộ database và chọn lại thứ tự tùy ý**: thứ tự triển khai, cấu trúc changeset, rollback do tác giả cung cấp và hiện trạng schema vẫn quyết định khả năng thành công.

## 3. Ba loại thứ tự cần phân biệt

Để tránh nhầm “theo thứ tự ngược” một cách máy móc, hãy xác định ba lớp:

1. **Thứ tự khai báo changelog**: các changeset xuất hiện qua file gốc, file include và includeAll. Đây là đường đi dự kiến khi thực hiện update.
2. **Thứ tự thực tế đã chạy**: **DATABASECHANGELOG** ghi nhận những changeset đã thực thi và metadata như ORDEREXECUTED/DATEEXECUTED. Context, label, dbms, precondition và lịch sử có thể làm tập changeset thực tế khác danh sách trong file.
3. **Thứ tự SQL đảo của mỗi changeset**: khi một changeset có nhiều change hoặc rollback SQL tự viết, cần kiểm tra thứ tự các câu SQL rollback mà Liquibase thật sự sinh. Không nên đoán dựa trên việc các câu lệnh được trình bày ra sao trong một block YAML.

**Quy tắc thiết kế tốt:** nếu các bước cần được kiểm soát độc lập hoặc phải đảo ngược rõ ràng, nên đặt vào **các changeset có mục đích đơn nhất** thay vì nhét nhiều thay đổi phụ thuộc vào một changeset lớn. Khi rollback một changeset chứa nhiều change, hãy xem **rollback SQL** được sinh trên đúng runtime/DBMS, không mặc định toàn bộ cấu trúc phức tạp được đảo an toàn.

Một chú ý nữa: nếu một changeset được đánh dấu **MARK_RAN** vì precondition, lịch sử có thể ghi nhận changeset dù phần DDL/DML không được chạy. Vì vậy, kiểm tra ORDEREXECUTED là cần nhưng **chưa đủ để xác nhận trạng thái schema thực tế**.

## 4. Phụ thuộc giữa những loại đối tượng phổ biến

Các phụ thuộc thường thấy trong migration:

| Đối tượng cần hoàn tác | Những thứ có thể đang phụ thuộc | Nguyên tắc xử lý |
|---|---|---|
| **Bảng cha** | Bảng con có foreign key, view, procedure, trigger, ứng dụng | Gỡ phụ thuộc trước khi drop bảng cha |
| **Bảng con** | View, trigger, index, khóa ngoại của bảng khác | Gỡ view/trigger/ràng buộc liên quan trước |
| **Cột** | Foreign key, unique/check constraint, index, view, generated column, trigger | Gỡ hoặc điều chỉnh phụ thuộc trước drop/rename |
| **Primary key/unique constraint** | Foreign key tham chiếu, index tự động hoặc ứng dụng | Gỡ foreign key phụ thuộc trước; xem ownership index |
| **Foreign key** | Có thể cần một index hỗ trợ trên bảng con tùy DBMS | Gỡ FK trước khi drop index được FK yêu cầu |
| **Index** | Constraint có thể sở hữu hoặc sử dụng index; câu truy vấn phụ thuộc hiệu năng | Xác định index độc lập hay do constraint quản lý |
| **View/materialized view** | Bảng, cột, view khác | Drop view phụ thuộc theo thứ tự ngược; xem tính năng DBMS |
| **Sequence/identity** | Default expression, bảng/cột hoặc trigger dùng sequence | Bỏ tham chiếu trước khi xóa sequence nếu cần |
| **Trigger/function/procedure** | Bảng, cột, kiểu dữ liệu, function khác | Gỡ/đổi object tham chiếu trước khi drop nền tảng |
| **Dữ liệu đã chuyển đổi** | Ràng buộc mới, ứng dụng mới, dữ liệu lịch sử | Xác định phép đảo có bảo toàn thông tin hay không |

Không phải mọi DBMS quản lý các quan hệ giống nhau. Ví dụ, một unique constraint có thể có index được database tự tạo; nếu tác giả viết thêm **dropIndex** cho một index tự quản lý bởi constraint, rollback có thể thất bại hoặc làm sai schema. Cần biết **ai tạo ra và sở hữu object**.

Một sơ đồ phụ thuộc có thể đọc theo chiều “A cần B tồn tại”:

~~~text
v_customer_order_count ----> customer
          |
          +----------------> sales_order
                                  |
                                  +--> fk_sales_order_customer --> customer(id)
                                  |
                                  +--> ix_sales_order_customer_id
~~~

Khi hoàn tác, nên gỡ object ở đầu nhánh phụ thuộc trước rồi mới gỡ object nền. Các liên kết trong sơ đồ là quan hệ logic, không thay thế catalog của DBMS.

## 5. Ví dụ YAML hoàn chỉnh: hai bảng, index, khóa ngoại, view

Giả sử hệ thống cần bảng **customer** và **sales_order**; bảng sales_order có khóa ngoại tham chiếu customer. Một index được tạo để hỗ trợ tra cứu theo customer_id, và view tổng hợp số đơn hàng phụ thuộc cả hai bảng.

Để minh họa thứ tự rollback, chia thành **năm changeset**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-customer"
      author: "platform"
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: full_name
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: customer

  - changeSet:
      id: "20261119-002-create-sales-order"
      author: "platform"
      changes:
        - createTable:
            tableName: sales_order
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: amount
                  type: DECIMAL(14,2)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: sales_order

  - changeSet:
      id: "20261119-003-index-sales-order-customer"
      author: "platform"
      changes:
        - createIndex:
            tableName: sales_order
            indexName: ix_sales_order_customer_id
            columns:
              - column:
                  name: customer_id
      rollback:
        - dropIndex:
            tableName: sales_order
            indexName: ix_sales_order_customer_id

  - changeSet:
      id: "20261119-004-fk-sales-order-customer"
      author: "platform"
      changes:
        - addForeignKeyConstraint:
            baseTableName: sales_order
            baseColumnNames: customer_id
            referencedTableName: customer
            referencedColumnNames: id
            constraintName: fk_sales_order_customer
      rollback:
        - dropForeignKeyConstraint:
            baseTableName: sales_order
            constraintName: fk_sales_order_customer

  - changeSet:
      id: "20261119-005-view-customer-order-count"
      author: "platform"
      changes:
        - createView:
            viewName: v_customer_order_count
            selectQuery: |
              SELECT c.id AS customer_id, COUNT(o.id) AS order_count
              FROM customer c
              LEFT JOIN sales_order o ON o.customer_id = c.id
              GROUP BY c.id
      rollback:
        - dropView:
            viewName: v_customer_order_count
~~~

**Giả định của ví dụ:** bảng chưa tồn tại trước khi chạy; hệ quản trị hỗ trợ change types và cú pháp SELECT được chọn; index ix_sales_order_customer_id được chính changeset 003 tạo; không có object bên ngoài changelog tham chiếu các bảng. Trong hệ thống thực tế cần thêm schemaName/catalogName khi phù hợp và kiểm tra SQL với đúng DBMS. **Các lệnh dropTable trong rollback sẽ làm mất dữ liệu trong bảng**; ví dụ này không được dùng để rollback dữ liệu nghiệp vụ thật mà chưa có kế hoạch phục hồi.

### Vì sao tạo index trước khóa ngoại?

Một số DBMS có yêu cầu index liên quan đến foreign key và có cách quản lý index khác nhau. Tạo index độc lập ở bước 003 trước khi thêm khóa ngoại ở bước 004 giúp làm rõ ownership của index trong ví dụ. Khi rollback, **gỡ foreign key ở bước 004 trước rồi mới gỡ index ở bước 003**; nhờ vậy tránh thao tác xóa index khi constraint vẫn có thể cần nó.

Dù vậy, không phải DBMS nào cũng cần cùng một loại index hay có cùng quy tắc sở hữu index. Nếu DBMS tự tạo index cho foreign key hoặc quản lý index qua constraint, cần xác định xem có cần createIndex riêng hay không để tránh trùng lặp.

### Vì sao tạo view cuối cùng?

View tham chiếu cả customer và sales_order; nếu tạo nó sau khi hai bảng sẵn sàng, rollback theo thứ tự ngược sẽ **dropView trước**. Nếu thả bảng khi view vẫn tồn tại, database có thể từ chối hoặc khiến view bị invalid, tùy DBMS và câu SQL được tạo.

## 6. Bảng diễn tiến rollback của ví dụ

Giả sử cả năm changeset đã được chạy thành công, không có đối tượng ngoài changelog tham chiếu chúng. Trình tự hoàn tác dự kiến:

| Thứ tự rollback | Changeset | Tác vụ đảo | Vì sao phải ở vị trí này? |
|---:|---|---|---|
| 1 | 005 | **dropView** v_customer_order_count | View phụ thuộc hai bảng |
| 2 | 004 | **dropForeignKeyConstraint** fk_sales_order_customer | Bỏ liên kết giữa bảng con và cha |
| 3 | 003 | **dropIndex** ix_sales_order_customer_id | Gỡ index khi FK không còn cần nó |
| 4 | 002 | **dropTable** sales_order | Xóa bảng con trước bảng cha |
| 5 | 001 | **dropTable** customer | Xóa bảng cha sau khi các phụ thuộc đã gỡ |

Mỗi changeset được đánh dấu đã rollback theo cơ chế quản lý lịch sử của Liquibase sau khi thao tác thành công. Nếu rollback thất bại giữa chừng, những changeset đã hoàn tác trước đó có thể vẫn đã được commit và xóa khỏi lịch sử đang chạy, tùy tính giao dịch của DBMS. Không giả định toàn bộ chuỗi rollback là một transaction nguyên tử.

**Điều tối quan trọng:** trên môi trường đã có đơn hàng thật, rollback tới mức thả hai bảng là **thao tác phá hủy dữ liệu**. Thứ tự kỹ thuật hợp lệ **không đồng nghĩa nghiệp vụ cho phép**. Kế hoạch release phải xác định lúc nào dùng rollback schema, lúc nào dừng ở rollback ứng dụng, và lúc nào cần backup hoặc sửa tiến bằng migration mới.

## 7. Chỉ rollback một phần: xác định mốc và ranh giới phụ thuộc

Giả sử hệ thống vừa thêm view ở bước 005 nhưng view chứa công thức tổng hợp sai; bốn changeset trước vẫn hợp lệ. Thay vì rollback toàn bộ cấu trúc, có thể chọn hoàn tác **duy nhất changeset 005** theo lệnh và điều kiện phù hợp.

Ví dụ minh họa cách rollback một changeset gần nhất bằng số lượng (nếu phiên bản CLI hỗ trợ tên lệnh/tùy chọn tương ứng):

~~~bash
liquibase --changelog-file=db.changelog.yaml rollback-count --count=1
~~~

Điều này nhằm gỡ view mà **giữ lại hai bảng, index và foreign key**. Tuy nhiên, rollback-count chọn các changeset đã thực thi theo phạm vi lịch sử, **không chọn theo tên object**. Nếu lịch sử đã có các changeset mới khác hoặc runAlways/runOnChange, “1 changeset gần nhất” có thể không còn là bước tạo view. Phải kiểm tra **DATABASECHANGELOG** và kế hoạch rollback trước.

Nếu chọn rollback theo **tag** hoặc theo **thời điểm**, cũng cần xác định chính xác phạm vi changeset sẽ bị đảo. Không dùng mốc dựa vào trí nhớ hoặc một tag chưa xác minh vì nó có thể đảo nhiều bước hơn dự kiến.

### Tình huống ngược: muốn giữ view nhưng drop bảng

Điều này không nhất quán về phụ thuộc nếu view thật sự tham chiếu bảng cần xóa. Trước khi hoàn tác bước tạo bảng, cần có kế hoạch thay thế hoặc gỡ view. Nếu có một hệ thống khác tạo view sau khi migration chạy, Liquibase **không tự biết và không tự sở hữu** đối tượng đó; rollback có thể thất bại. Không dùng **CASCADE** chỉ để vượt lỗi nếu chưa liệt kê tất cả object sẽ bị xóa lan truyền.

## 8. Không chỉ bảng: phụ thuộc ở mức cột và constraint

Một thay đổi tưởng nhỏ như xóa cột **customer.email** có thể bị ràng buộc bởi:

~~~text
customer.email
    ^
    |-- ix_customer_email
    |-- uq_customer_email
    |-- view v_customer_contact
    |-- trigger trg_customer_normalize
    |-- procedure search_customer
    |-- ứng dụng/API/ETL đọc email
~~~

Nếu muốn rollback một thay đổi **addColumn email**, hành động đảo đơn giản là **dropColumn email**. Nhưng trong thời gian cột tồn tại, một changeset sau có thể đã tạo unique constraint và view tham chiếu email. Muốn dropColumn an toàn, phải hoàn tác những bước tạo phụ thuộc đó trước.

Ví dụ chuỗi triển khai tốt:

~~~text
A. addColumn(customer.email)
B. backfill customer.email
C. createIndex(customer.email)
D. addUniqueConstraint(customer.email)
E. createView(v_customer_contact)
~~~

Nếu rollback cả chuỗi, hướng logic là **E → D → C → B → A**. Nhưng có hai cảnh báo:

1. **Index do unique constraint sở hữu** có thể được DBMS tự tạo. Trong ví dụ mang tính khái niệm, C là một index độc lập; nếu D tự quản lý index, không viết dropIndex cho một index mà C không hề tạo.
2. **B — backfill dữ liệu** thường không có phép đảo an toàn. Nếu người dùng đã cập nhật email sau backfill, một câu UPDATE đặt email=NULL theo toàn bảng có thể xóa dữ liệu mới. Rollback logic của schema không tự khôi phục dữ liệu gốc.

Với **renameColumn** hoặc **modifyDataType**, ngoài constraint, cần kiểm tra view/procedure/trigger SQL và ứng dụng còn tham chiếu tên/kiểu cũ. Đổi tên cột ngược lại chưa chắc khôi phục toàn bộ hành vi nếu trong quá trình chuyển tiếp đã có dữ liệu bị ép kiểu hoặc làm tròn.

## 9. Phụ thuộc có chu trình: tách việc tạo bảng khỏi việc thêm khóa

Một số mô hình dữ liệu có quan hệ vòng, ví dụ:

- Bảng **employee** tham chiếu phòng ban qua **department_id**.
- Bảng **department** tham chiếu trưởng phòng qua **manager_employee_id**.

Nếu mỗi bảng đòi bảng kia tồn tại ngay từ câu CREATE TABLE có foreign key, quá trình triển khai có thể rơi vào bài toán thứ tự khó giải. Cách thiết kế rõ ràng:

1. Tạo **employee** và **department** với các cột cần thiết, chưa thêm foreign key vòng.
2. Tạo constraint/index nền theo yêu cầu DBMS.
3. Thêm foreign key employee → department.
4. Thêm foreign key department → employee.

Khi rollback toàn bộ, **gỡ hai foreign key trước**, sau đó mới thả bảng. Nếu constraint được tạo trong changeset tách biệt, logic đảo theo thứ tự thường dễ kiểm chứng hơn.

Không nên dùng lệnh drop bảng với CASCADE như giải pháp mặc định cho một thiết kế phụ thuộc vòng. CASCADE có thể xóa rộng hơn ý định và làm khó phục hồi những object khác.

## 10. Phụ thuộc dữ liệu và thứ tự rollback DML

Các quan hệ dữ liệu còn ảnh hưởng rollback ngay cả khi không drop schema.

Giả sử migration lần lượt:

~~~text
001. Tạo customer
002. Tạo sales_order, FK -> customer
003. Insert bản ghi customer có id=10
004. Insert sales_order có customer_id=10
~~~

Nếu rollback dữ liệu, cần **xóa sales_order trước khi xóa customer** để tránh vi phạm foreign key. Đó cũng là thứ tự ngược với tiến trình insert.

Một changeset chèn dữ liệu nên có rollback rõ ràng và **định danh chính xác các hàng do nó tạo**, ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-101-insert-seed-customer"
      author: "platform"
      changes:
        - insert:
            tableName: customer
            columns:
              - column:
                  name: id
                  valueNumeric: 10
              - column:
                  name: full_name
                  value: "Migration Seed"
      rollback:
        - delete:
            tableName: customer
            where: "id = 10"
~~~

**Đây chỉ là ví dụ một changeset độc lập**, giả định bản ghi id=10 do migration tạo và không có dữ liệu nghiệp vụ nào phụ thuộc. Nếu sau đó ứng dụng tạo đơn hàng tham chiếu khách hàng 10, rollback delete có thể bị foreign key chặn; hoặc nếu dùng ON DELETE CASCADE thì xóa lan truyền dữ liệu không mong muốn. Trong hệ thống thật phải xác định tính sở hữu của hàng dữ liệu và cách xử lý các bản ghi phát sinh sau release.

### Backfill không có phép đảo tự nhiên

Giả sử migration chuyển:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Một rollback kiểu:

~~~sql
UPDATE customer
SET status = NULL
WHERE status = 'ACTIVE';
~~~

**không an toàn**. Nó không biết dòng nào vốn là ACTIVE trước migration, dòng nào được ứng dụng ghi ACTIVE sau đó. Muốn khôi phục chính xác phải có snapshot, cột audit, bảng đối chiếu hoặc nguồn dữ liệu gốc. Nếu không thể phục hồi dữ liệu chính xác, nên cân nhắc **roll-forward** bằng migration sửa chữa thay vì rollback dữ liệu mù quáng.

### Transaction không thay thế việc xác định thứ tự

Database có thể kiểm tra foreign key ngay trong mỗi statement, cuối transaction hoặc theo cơ chế deferrable constraint (nếu hỗ trợ). Không được mặc định rằng đưa các lệnh DELETE vào chung một transaction sẽ bỏ qua thứ tự phụ thuộc. Hãy chọn thứ tự đúng và chỉ dùng cơ chế trì hoãn constraint khi đã phân tích kỹ DBMS và nhu cầu nghiệp vụ.

## 11. Default, NOT NULL và tính hợp lệ khi rollback

Một ví dụ khác về phụ thuộc trạng thái:

~~~text
R1: Cột contact_channel nullable
R2: Đặt DEFAULT 'EMAIL'
R3: Backfill các hàng còn NULL
R4: Thêm NOT NULL
R5: Ứng dụng mới dựa vào contact_channel luôn có giá trị
~~~

Rollback R4 về nullable thường có thể thực hiện bằng **dropNotNullConstraint**, nhưng:

- Đảo R3 không thể chỉ đặt mọi EMAIL thành NULL, vì có thể làm mất dữ liệu hợp lệ.
- Đảo R2 cần khôi phục default trước đó (nếu có), không nhất thiết là dropDefaultValue.
- Rollback ứng dụng về bản trước phải xem bản cũ có hiểu dữ liệu và schema hiện tại không.
- Nếu R4 chưa chạy mà ứng dụng mới đã dựa vào NOT NULL, hệ thống có khoảng thời gian không nhất quán về ràng buộc.

Ngược lại, sau khi **dropNotNullConstraint** để cho phép NULL, nếu ứng dụng bắt đầu ghi NULL, rollback thay đổi ấy bằng **addNotNullConstraint** sẽ thất bại chừng nào dữ liệu vi phạm chưa được xử lý.

Vì vậy, rollback không chỉ xét **đảo đúng DDL** mà còn phải xét **tiền điều kiện dữ liệu để DDL đảo thành công**.

## 12. Tham chiếu bên ngoài changelog: điều Liquibase không tự biết

Các phụ thuộc tồn tại bên ngoài tập changeset cần rollback gồm:

- DBA tạo index, trigger, view hoặc procedure thủ công.
- Hệ thống BI/ETL chạy SQL tham chiếu một bảng/cột dự kiến bị xóa.
- Job chạy theo lịch ghi dữ liệu vào bảng đang hoàn tác.
- Một service khác dùng cùng database hoặc gọi stored procedure.
- Application mới đã được deploy và còn kết nối khi rollback schema.
- Extension DBMS tạo object phụ trợ theo quy tắc riêng.
- Cơ chế replication, CDC hoặc materialized view tham chiếu bảng.

Các đối tượng ngoài Liquibase có thể **không xuất hiện trong DATABASECHANGELOG**. Do đó, lịch sử changeset là nguồn quan trọng nhưng không phải inventory đầy đủ của database. Trước khi drop object nền, nên tra catalog database, công cụ quản lý schema và phụ thuộc ở tầng ứng dụng; xác định rõ **tập object dự kiến chịu tác động**.

Nếu rollback bị chặn vì phụ thuộc lạ, không nên xóa object đó theo phỏng đoán. Cần điều tra chủ sở hữu và quyết định phạm vi tác động. Với production, phương án **dừng rollback và roll-forward sửa lỗi** thường an toàn hơn việc drop cascade không kiểm soát.

## 13. Những lệnh rollback thường dùng và phạm vi của chúng

Liquibase có các phương thức xác định phạm vi hoàn tác theo **tag**, **số changeset** hoặc **thời điểm**, tùy phiên bản và tính năng hiện có.

Ví dụ CLI minh họa:

~~~bash
# Xác nhận runtime và cấu trúc changelog
liquibase --version
liquibase --changelog-file=db.changelog.yaml validate
liquibase --changelog-file=db.changelog.yaml history

# Xem SQL của rollback theo số changeset nếu runtime hỗ trợ
liquibase --changelog-file=db.changelog.yaml rollback-count-sql --count=2

# Trên database thử nghiệm, thực thi rollback đúng hai changeset
liquibase --changelog-file=db.changelog.yaml rollback-count --count=2
~~~

Phải xác nhận **cú pháp option và tính sẵn có của lệnh** bằng đúng phiên bản/edition Liquibase đang sử dụng. Không dùng lệnh minh họa để chạy trực tiếp trên production khi chưa có phê duyệt và kế hoạch khôi phục.

Với tag, một số phiên bản dùng dạng lệnh:

~~~bash
liquibase --changelog-file=db.changelog.yaml \
  rollback-sql --tag=release-2026.11.1

liquibase --changelog-file=db.changelog.yaml \
  rollback --tag=release-2026.11.1
~~~

Tên tag phải được xác minh trong **lịch sử database đích**; đừng giả định một chuỗi trông giống release sẽ luôn có ý nghĩa đúng với rollback. Lệnh rollback theo tag và lệnh update-to-tag là **hai thao tác khác nhau**; update-to-tag không đảo changeset đã chạy sau mốc.

### Rollback-count đếm changeset, không đếm câu SQL

Một changeset có thể chứa nhiều câu SQL. Vì vậy, **--count=2** không có nghĩa “chạy hai câu lệnh đảo” mà là chọn phạm vi theo hai changeset được tính theo cơ chế của Liquibase. Phải xem trước lịch sử và rollback SQL thật.

### Rollback-to-date phụ thuộc mốc thời gian

Lệnh rollback theo thời điểm cần đối chiếu **DATEEXECUTED**, timezone, giá trị thời gian và lịch sử thực tế. Nếu nhiều changeset chạy sát nhau, chọn nhầm timestamp có thể đảo sai phạm vi. Với release có mốc quản trị rõ, dùng tag được kiểm chứng thường dễ review hơn so với suy đoán thời gian bằng mắt.

## 14. Xem trước rollback SQL trước khi thực thi

**Rollback SQL preview** là bước thiết yếu để kiểm tra thứ tự và phạm vi, nhất là khi có FK, view và dữ liệu. Lệnh preview tương ứng có thể khác theo loại rollback:

~~~bash
liquibase --changelog-file=db.changelog.yaml rollback-count-sql --count=5
~~~

Với ví dụ năm changeset, SQL sinh ra về mặt logic nên được kiểm tra để bảo đảm:

1. View bị gỡ trước khi bảng nguồn bị xóa.
2. Foreign key được gỡ trước khi thả bảng cha và trước khi xóa index nếu index còn cần cho constraint.
3. Index độc lập được gỡ đúng tên và đúng schema.
4. Bảng con bị xóa trước bảng cha.
5. Không có thao tác CASCADE ngoài ý định hoặc DROP object không thuộc phạm vi.
6. DDL phù hợp với DBMS, bao gồm schema/catalog, quoting và transaction semantics.

**Preview không phải bảo đảm rollback thành công.** SQL có thể đúng cú pháp nhưng thất bại khi chạy vì dữ liệu hiện tại, lock, phụ thuộc mới, permissions hoặc SQL do DBA/app tạo sau lần deploy. Cần tiếp tục kiểm chứng trên database đại diện.

Nên lưu **rollback SQL, commit changelog, phiên bản Liquibase, DBMS/version, mốc lịch sử và danh sách object tác động** cùng hồ sơ thay đổi. Việc này giúp reviewer phát hiện lỗi thứ tự trước khi chạm tới production.

## 15. Kiểm tra lịch sử DATABASECHANGELOG

Bảng **DATABASECHANGELOG** ghi thông tin về các changeset được Liquibase quản lý. Truy vấn minh họa:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    ORDEREXECUTED,
    DATEEXECUTED,
    EXECTYPE,
    TAG,
    MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED;
~~~

Các trường cần hiểu:

- **ID, AUTHOR, FILENAME**: giúp nhận diện changeset; đường dẫn có thể chịu ảnh hưởng của logicalFilePath.
- **ORDEREXECUTED/DATEEXECUTED**: hỗ trợ quan sát trình tự thực thi thực tế. Khi so sánh nhiều lần deploy hoặc DBMS khác nhau, cần đọc cùng metadata lịch sử và log, không suy duy nhất từ một con số.
- **EXECTYPE**: có thể cho biết một changeset được thực thi theo cách nào; phân biệt với trạng thái schema thực tế.
- **TAG**: hỗ trợ đối chiếu các mốc được gắn.
- **MD5SUM**: checksum của định nghĩa changeset đã được ghi nhận.

Khi rollback thành công một changeset thông thường, Liquibase cập nhật lịch sử theo cơ chế rollback, nên danh sách “changeset đã chạy” về sau khác trước rollback. Tuy nhiên, không được **tự xóa/sửa DATABASECHANGELOG** để mô phỏng rollback: lịch sử không thể thay thế thao tác DDL/DML đảo thật.

Sau khi rollback, cần kiểm tra đồng thời:

1. Changeset nào còn trong lịch sử.
2. Đối tượng schema nào còn thực tế.
3. Dữ liệu có đúng trạng thái mong muốn không.
4. Ứng dụng còn hoạt động với schema hiện hành không.

Nếu có người đã ALTER/DROP trực tiếp ngoài Liquibase, dữ liệu lịch sử và schema có thể lệch nhau. Khi đó cần điều tra trước khi gọi rollback tiếp.

## 16. Auto rollback và rollback tường minh

Một số change type của Liquibase có thể sinh rollback tự động, nhưng **không phải tất cả**. Ví dụ:

| Change type xuôi | Rollback thường mong đợi | Cần cân nhắc |
|---|---|---|
| **createTable** | **dropTable** | Xóa dữ liệu trong bảng, có thể phá phụ thuộc mới |
| **createIndex** | **dropIndex** | Index có thuộc constraint hoặc FK không |
| **addForeignKeyConstraint** | **dropForeignKeyConstraint** | Đúng tên constraint và bảng |
| **createView** | **dropView** | Các view hoặc object khác có tham chiếu view này không |
| **addColumn** | **dropColumn** | Dữ liệu mới trong cột sẽ mất |
| **addNotNullConstraint** | **dropNotNullConstraint** | Ứng dụng và dữ liệu đang kỳ vọng NOT NULL |
| **insert / update / delete dữ liệu** | Tùy thao tác, có thể cần SQL đảo hoặc snapshot | Không thể suy ra dữ liệu gốc cho mọi trường hợp |
| **sql / sqlFile tự viết** | Thường cần rollback tự định nghĩa | Không nên trông đợi suy diễn SQL tùy ý |

Đây là định hướng tư duy, **không phải cam kết mọi phiên bản/DBMS đều tự sinh rollback cho tất cả mục trong bảng**. Để biết thực tế, xem tài liệu change type/phiên bản và thử các lệnh preview rollback. Dù Liquibase tự sinh SQL, kỹ sư vẫn phải kiểm tra mất dữ liệu và quan hệ phụ thuộc.

Một quy tắc thực hành hữu ích là **viết rollback tường minh cho các thay đổi quan trọng**, đặc biệt khi trạng thái trước đó không thể suy ra, phụ thuộc nhiều object hoặc cần dữ liệu phục hồi.

### Không viết rollback “đẹp mắt” nhưng sai nghiệp vụ

Ví dụ forward thay **DEFAULT PENDING → QUEUED**. Rollback đúng thường là **khôi phục DEFAULT PENDING**, không phải gỡ default hoàn toàn. Tương tự, khi đổi type có thể mất độ chính xác hoặc cắt chuỗi, đổi type ngược lại không tự hồi sinh giá trị bị mất.

## 17. Tác động của transaction và DDL ở các DBMS

Khả năng transaction của DDL khác nhau giữa PostgreSQL, MySQL/MariaDB, SQL Server, Oracle và các hệ khác. Những khác biệt này làm thay đổi rủi ro khi rollback nhiều changeset:

| Khía cạnh | Điều cần xem xét |
|---|---|
| **DDL transactional** | Một số DBMS hỗ trợ rollback transaction cho nhiều DDL; số khác có implicit commit hoặc hạn chế |
| **Locks** | DROP/ALTER có thể lấy khóa mạnh, chặn query/transaction khác |
| **Foreign key/index** | Quy tắc index và constraint ownership khác nhau |
| **CASCADE** | Phạm vi object bị xóa lan truyền khác nhau theo loại object/DBMS |
| **Views và stored objects** | Phụ thuộc được database kiểm tra khác nhau; một số object có thể invalid |
| **Data migration** | DML có thể tạo WAL/log lớn; hoàn tác và kiểm chứng mất thời gian |
| **Permissions** | Quyền tạo/drop object có thể khác quyền dùng object |

Với SQL Server, default constraint/unique constraint có thể sở hữu những object phụ trợ cần xử lý đúng tên. Với PostgreSQL, **DROP ... CASCADE** có thể tự xóa các object phụ thuộc, vì vậy chỉ sử dụng sau khi hiểu đầy đủ tác động. Với MySQL/MariaDB, việc thay đổi cột hoặc khóa có thể cần rebuild bảng hoặc bị giới hạn bởi engine/phiên bản. Các ví dụ SQL của một DBMS **không được xem là hướng dẫn copy-paste cho DBMS khác**.

Khi production có dữ liệu lớn và SLA nghiêm ngặt, một rollback kỹ thuật hợp lệ nhưng cần khóa nhiều phút vẫn có thể không đáp ứng yêu cầu vận hành. Phải thử trên database có kích thước/chỉ mục/dữ liệu đại diện và có kế hoạch maintenance hoặc phương án thay thế.

## 18. Rollback trong hệ thống đang có nhiều phiên bản ứng dụng

Schema không tồn tại độc lập với code. Ví dụ:

~~~text
Release R1:
    app-v1 đọc bảng customer

Release R2:
    thêm cột preferred_name nullable
    triển khai app-v2 bắt đầu ghi preferred_name

Release R3:
    backfill preferred_name
    thêm NOT NULL
    app-v3 chỉ đọc preferred_name
~~~

Nếu rollback schema từ R3 về R1 nhưng app-v3 vẫn đang chạy, các truy vấn app-v3 có thể lỗi vì cột đã bị xóa. Ngược lại, nếu rollback app về v1 nhưng giữ schema mới, có thể vẫn hoạt động nếu thay đổi tương thích ngược.

Một thứ tự phối hợp thường cần:

1. **Chặn hoặc điều tiết các luồng ghi không tương thích** trước khi rollback schema.
2. **Chọn phiên bản ứng dụng tương thích** với trạng thái database sau rollback.
3. **Đánh giá dữ liệu mới** có còn được ứng dụng cũ hiểu hay không.
4. **Thực thi rollback có kiểm soát** theo đúng phạm vi changeset/objects.
5. **Kiểm tra smoke test và dữ liệu**, rồi cho phép traffic trở lại.

Không có một quy trình cố định áp dụng cho mọi hệ thống; đôi khi cần **rollback ứng dụng nhưng giữ nguyên schema** để bảo toàn dữ liệu, rồi viết migration sửa lỗi tiến lên. Sự an toàn được xác định bằng tương thích giữa ứng dụng và dữ liệu, không chỉ bằng trạng thái changelog.

## 19. Vai trò của precondition và kiểm tra trước rollback

**Precondition** trong changelog thường phục vụ việc kiểm tra điều kiện của quá trình triển khai; không được giả định rằng mọi precondition đặt cho **forward update** sẽ tự bảo vệ logic rollback phức tạp. Trước rollback cần **kiểm tra độc lập** các điều kiện an toàn:

- Những object nào đang tham chiếu bảng/cột/index dự kiến gỡ?
- Có dữ liệu mới nào sẽ mất nếu drop bảng hoặc cột?
- Có hàng nào vi phạm constraint định thêm lại?
- Các writer/consumer/ETL có bị ảnh hưởng sau khi thay đổi schema không?
- Đã có backup hoặc nguồn khôi phục dữ liệu phù hợp chưa?
- Có đủ quyền DROP/ALTER và có maintenance window nếu cần không?

Ví dụ khi rollback **dropNotNullConstraint** bằng cách thêm NOT NULL trở lại, cần kiểm tra:

~~~sql
SELECT COUNT(*) AS null_count
FROM customer
WHERE contact_channel IS NULL;
~~~

Nếu số lượng khác 0, không thể tùy tiện thêm NOT NULL mà không xử lý dữ liệu. Với rollback **createTable** bằng dropTable, kiểm tra số dòng và phụ thuộc hiện có trước khi cho phép dữ liệu bị xóa.

Nếu rollback được điều phối bằng CI/CD, các kiểm tra này có thể thành **approval gate** hoặc bước preflight; không dùng **MARK_RAN** hoặc chỉnh tay DATABASECHANGELOG để qua lỗi mà không sửa trạng thái thực tế.

## 20. Quy trình rollback an toàn theo từng giai đoạn

Một quy trình thực tế nên có năm giai đoạn.

### Giai đoạn A — Xác định mục tiêu

- Lỗi thuộc ứng dụng, schema hay dữ liệu?
- Thực sự cần rollback database hay có thể roll-forward bằng changeset sửa lỗi?
- Mốc đích là tag, timestamp hay một số changeset cụ thể?
- Các object nào được phép thay đổi, object nào phải giữ nguyên?
- Có mất dữ liệu hoặc hành vi ứng dụng không tương thích không?

### Giai đoạn B — Vẽ đồ thị phụ thuộc

Liệt kê:

~~~text
Bảng, cột, PK/unique, FK, index, view, trigger,
function/procedure, sequence, dữ liệu, ứng dụng và job.
~~~

Vẽ mũi tên từ object phụ thuộc tới object nó cần. Tìm những object được tạo ngoài changelog. Chọn **thứ tự gỡ object phụ thuộc trước**; nếu phát hiện chu trình, tách các constraint/tham chiếu trước khi xóa object nền.

### Giai đoạn C — Xem lịch sử và SQL dự kiến

- Kiểm tra DATABASECHANGELOG và tag trên **đúng database**.
- Kiểm tra trạng thái thực của schema qua catalog DBMS.
- Chạy lệnh preview rollback phù hợp phiên bản/edition.
- Review từng câu SQL, thứ tự, tên constraint/index và tác động dữ liệu.
- Đối chiếu phạm vi với release manifest và kế hoạch triển khai ứng dụng.

### Giai đoạn D — Thử trên môi trường đại diện

- Tạo môi trường thử có schema và dữ liệu giống trạng thái thực tế đủ mức cần thiết.
- Áp đúng changelog/changeset đã triển khai.
- Tạo dữ liệu mới tương tự sau release để bộc lộ vấn đề rollback.
- Thực thi rollback trong thử nghiệm; đo thời gian, lock và tính đúng đắn.
- Thử khởi động phiên bản ứng dụng sẽ chạy sau rollback.

### Giai đoạn E — Thực thi và xác minh

- Tạm dừng/điều tiết writer nếu cần.
- Chạy rollback có giám sát, dùng đúng artifact và thông số đã duyệt.
- Đọc lại lịch sử changeset và catalog database.
- Kiểm tra dữ liệu, constraint, view, truy vấn ứng dụng và smoke test.
- Ghi lại kết quả, lỗi, thay đổi phát sinh và quyết định tiếp theo.

**Không tuyên bố hoàn tất chỉ vì CLI trả exit code 0.** Trạng thái schema, dữ liệu và hoạt động ứng dụng là bằng chứng bắt buộc cho rollback có ý nghĩa.

## 21. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Không drop được bảng cha | Vẫn có FK từ bảng con hoặc object phụ thuộc | Gỡ FK/view phụ thuộc trước, kiểm tra catalog |
| Không drop được index | Index đang được constraint yêu cầu hoặc không thuộc changeset đó | Phân biệt index độc lập với index do DBMS quản lý |
| Drop column lỗi vì view | View/procedure/trigger vẫn tham chiếu cột | Rollback dependent object trước |
| Rollback-count đảo nhầm thay đổi | Đếm số changeset theo lịch sử nhưng không kiểm tra thực tế | Xem DATABASECHANGELOG và rollback SQL trước |
| Rollback một changeset thành công nhưng release vẫn lỗi | Ứng dụng/schema phụ thuộc các changeset khác | Xem phạm vi release và tương thích ứng dụng |
| Rollback DML xóa nhầm dữ liệu mới | Dùng điều kiện WHERE quá rộng, thiếu snapshot | Thiết kế rollback theo ownership và nguồn dữ liệu |
| Rollback thêm NOT NULL thất bại | Dữ liệu mới chứa NULL | Dừng writer và xử lý dữ liệu vi phạm theo nghiệp vụ |
| DDL rollback chạy khác dev | DBMS/driver/transaction/locks khác | Thử trên DBMS tương ứng và đo lock |
| Rollback xong nhưng có object lạ còn tồn tại | Object do DBA/hệ khác tạo | Kiểm tra catalog và chủ sở hữu |
| CHECKSUM không khớp | Changeset đã chạy bị chỉnh sửa hoặc đổi đường dẫn | Phục hồi lịch sử, thêm changeset mới, không che lỗi |
| Thử rollback cần xóa cả bảng dữ liệu | Rollback auto của createTable là dropTable | Thay chiến lược bằng sửa tiến/backup hoặc kế hoạch chuyển dữ liệu |
| Dùng DROP CASCADE làm mất object ngoài ý định | Phụ thuộc không được liệt kê | Không dùng cascade mù; review impact trước |

## 22. Bài thực hành: dự đoán thứ tự hoàn tác

Sử dụng changelog năm changeset ở mục 5 trên **database thử nghiệm riêng**.

**Bước 1 — Trước khi chạy:**

- Vẽ đồ thị phụ thuộc giữa customer, sales_order, index, foreign key và view.
- Dự đoán thứ tự rollback của cả năm changeset.
- Giải thích vì sao FK phải gỡ trước index trong ví dụ.
- Giải thích vì sao không thể drop customer đầu tiên.

**Bước 2 — Triển khai:**

- Chạy validate và update trên database thử nghiệm.
- Kiểm tra các bảng/index/FK/view tồn tại đúng.
- Đọc DATABASECHANGELOG và ghi thứ tự các changeset đã chạy.

**Bước 3 — Xem SQL rollback:**

- Chạy rollback-count-sql với count tương ứng trên bản Liquibase hỗ trợ.
- Xác nhận SQL gỡ view → FK → index → sales_order → customer.
- Kiểm tra có SQL drop object ngoài dự kiến không.

**Bước 4 — Thử rollback một phần:**

- Chỉ rollback changeset tạo view.
- Kiểm tra view không còn, hai bảng, index và FK vẫn tồn tại.
- Chạy lại changelog nếu muốn khôi phục view; xác minh lịch sử được cập nhật phù hợp.

**Bước 5 — Thử rollback toàn bộ trên database có dữ liệu:**

- Tạo dữ liệu customer và sales_order trong môi trường thử.
- Trước rollback, giải thích và ghi nhận rằng dropTable sẽ xóa dữ liệu.
- Thực thi rollback khi đã chấp nhận tác động trong môi trường thử.
- Xác minh các object đã được gỡ đúng thứ tự và dữ liệu không thể tự hồi phục.

**Bước 6 — Tình huống lỗi:**

- Tạo một view bổ sung ngoài changelog tham chiếu sales_order.
- Quan sát trên DBMS đích liệu rollback bị chặn hay có tác động ngoài dự kiến.
- Đề xuất cách phối hợp với người quản trị object ngoài Liquibase trước khi chạy lại.
- Không bật CASCADE nếu chưa biết rõ phụ thuộc bị ảnh hưởng.

## 23. Checklist review rollback theo phụ thuộc

Trước khi phê duyệt rollback, kiểm tra:

- Đã xác định đúng **mốc rollback** và tập changeset sẽ bị đảo chưa?
- Đã đối chiếu thứ tự changeset thực tế trong DATABASECHANGELOG chưa?
- Có object được tạo bởi DBA/ứng dụng khác mà changelog không quản lý không?
- Đã lập danh sách bảng, cột, index, PK/unique, FK, view, trigger, function và sequence liên quan?
- Mọi đối tượng phụ thuộc đã được xử lý **trước** khi gỡ object nền chưa?
- Có trường hợp index thuộc về constraint hoặc được DBMS tự tạo không?
- Có quan hệ FK vòng cần gỡ constraint trước khi drop table không?
- Đã phân biệt rollback DDL với khả năng khôi phục dữ liệu cũ chưa?
- Có những dữ liệu được ứng dụng tạo sau migration có thể bị xóa hoặc khiến constraint thất bại không?
- Đã kiểm tra trường hợp NOT NULL/default/kiểu dữ liệu thay đổi và trạng thái hiện tại chưa?
- Đã xem rollback SQL bằng **đúng version/edition/DBMS** sẽ thực thi chưa?
- Đã kiểm chứng transaction, lock, quyền và khả năng rollback DDL của DBMS đích chưa?
- Đã thử trên database đại diện và với phiên bản ứng dụng dự kiến sau rollback chưa?
- Đã có backup, phương án roll-forward hoặc quy trình khôi phục khi rollback thất bại giữa chừng chưa?
- Đã giữ nguyên changeset đã phát hành, không chỉnh lịch sử/checksum để lách lỗi chưa?
- Đã chuẩn bị bước xác minh schema, dữ liệu, log và ứng dụng sau khi rollback chưa?

**Kết luận:** Trong Liquibase, **thứ tự rollback được chọn theo lịch sử changeset** và thường đảo ngược trình tự triển khai. Nhưng **thứ tự an toàn** còn phải tôn trọng đồ thị phụ thuộc giữa view, khóa ngoại, chỉ mục, bảng, cột và dữ liệu. Hãy thiết kế changeset theo mục đích rõ ràng, gỡ đối tượng phụ thuộc trước đối tượng nền, viết hoặc kiểm tra rollback SQL tường minh khi cần, đánh giá dữ liệu phát sinh sau release và thử trên DBMS thực tế. Một rollback thành công không chỉ là lệnh hoàn tất, mà là trạng thái schema, dữ liệu và ứng dụng **được chứng minh còn nhất quán** sau khi hoàn tác.

