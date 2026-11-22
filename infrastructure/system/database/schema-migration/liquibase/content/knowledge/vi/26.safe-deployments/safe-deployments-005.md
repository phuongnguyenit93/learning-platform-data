# Thêm NOT NULL, khóa ngoại và chỉ mục trên bảng lớn

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở chương **Triển khai an toàn**, thêm ràng buộc NOT NULL, khóa ngoại và chỉ mục trên bảng lớn là công việc cần chuẩn bị kỹ vì một câu DDL ngắn có thể quét hàng triệu dòng, giữ lock, làm tăng replication lag hoặc khiến ứng dụng ngừng ghi.

Mục tiêu không chỉ là làm cho migration chạy thành công. Cần đạt đồng thời bốn điều kiện:

1. **Đúng dữ liệu:** dữ liệu hiện tại và dữ liệu mới đều tuân thủ ràng buộc.
2. **Ít gián đoạn:** hạn chế lock dài, table rewrite, timeout và ảnh hưởng truy vấn.
3. **Tương thích khi rollout:** phiên bản ứng dụng cũ/mới có thể cùng hoạt động trong giai đoạn chuyển tiếp.
4. **Có đường phục hồi:** biết thao tác nào rollback được, thao tác nào cần forward-fix hoặc restore.

Cách triển khai thường gồm nhiều bước nhỏ: mở rộng schema, bảo vệ ghi mới, backfill theo batch, xác minh, xác thực constraint và chỉ sau đó mới hoàn tất thay đổi. Những kỹ thuật như NOT VALID, VALIDATE CONSTRAINT hay CREATE INDEX CONCURRENTLY có ngữ nghĩa riêng theo DBMS; ví dụ PostgreSQL trong bài không thể áp dụng nguyên xi cho MySQL, SQL Server hoặc Oracle.

## 1. Vì sao bảng lớn cần chiến lược triển khai riêng?

Trên bảng nhỏ, thêm NOT NULL, foreign key hoặc index có thể hoàn tất nhanh. Trên bảng hàng chục hoặc hàng trăm triệu dòng, cùng thao tác có thể:

- Quét toàn bộ bảng để xác minh dữ liệu.
- Giữ lock khiến request ghi phải chờ.
- Tạo lượng lớn WAL/transaction log và tăng replication lag.
- Gây cạnh tranh I/O, CPU, memory và dung lượng tạm.
- Làm tăng latency của truy vấn đang chạy.
- Vượt statement timeout hoặc thời gian cho phép của deployment.
- Tạo index chưa hoàn chỉnh nếu thao tác bị ngắt.
- Làm ứng dụng cũ không tương thích với schema mới.

Một thay đổi được gọi là online hoặc concurrent không có nghĩa là hoàn toàn không khóa hay không tốn tài nguyên. Nó thường giảm một số loại chặn ghi, nhưng vẫn có giai đoạn cần lock, quét dữ liệu hoặc chờ transaction cũ kết thúc.

### 1.1. Ba loại thay đổi có đặc điểm khác nhau

| Thay đổi | Công việc chính | Rủi ro trên bảng lớn |
|---|---|---|
| NOT NULL | Xác minh không còn NULL và ngăn ghi NULL về sau | Quét bảng, lock khi validate/enforce, backfill lớn |
| FOREIGN KEY | Xác minh mỗi khóa con tham chiếu một khóa cha hợp lệ | Quét bảng con, truy vấn kiểm tra tốn kém, ảnh hưởng ghi/xóa bảng cha |
| INDEX | Đọc dữ liệu, sắp xếp và xây cấu trúc index | I/O, CPU, dung lượng, lock và ảnh hưởng write workload |

Không nên gộp cả ba vào một changeset dài. Tách các giai đoạn giúp xác định bước nào thất bại, kiểm tra trạng thái vật lý và tiếp tục có kiểm soát.

### 1.2. Thu thập thông tin trước khi thiết kế migration

Trước khi viết changelog, cần biết:

- Kích thước bảng và số dòng ước tính.
- Tốc độ INSERT/UPDATE/DELETE và thời điểm cao tải.
- Tỷ lệ NULL, duplicate và orphan hiện tại.
- Các index/constraint đã có.
- Query và transaction dài đang chạy.
- DBMS, phiên bản, storage engine và cấu hình replication.
- Khả năng DDL online/concurrent của đúng phiên bản.
- Thời gian lock tối đa và cửa sổ triển khai.
- Dung lượng trống cho index, temporary files và log.
- Consumer của cột/bảng: ứng dụng, batch, báo cáo, ETL, CDC.

Một phép COUNT(*) hoặc anti-join trên bảng rất lớn cũng có thể tiêu tốn nhiều I/O. Hãy đo trên môi trường đại diện, dùng thống kê/catalog khi phù hợp và dành thời gian cho phép kiểm tra chính xác.

## 2. Quy trình chung: expand, backfill, validate, enforce

Một cách triển khai an toàn thường có các giai đoạn:

~~~text
Hiện trạng: bảng lớn, dữ liệu và ứng dụng đang hoạt động
                  |
                  v
1. EXPAND
   Thêm cột/index/constraint ở trạng thái chưa gây breaking change
                  |
                  v
2. PROTECT NEW WRITES
   Ngăn dữ liệu mới tiếp tục vi phạm invariant
                  |
                  v
3. BACKFILL
   Sửa dữ liệu cũ theo batch, có checkpoint và giới hạn tải
                  |
                  v
4. VALIDATE
   Kiểm tra dữ liệu hiện hữu và xác thực constraint
                  |
                  v
5. ENFORCE
   Hoàn tất NOT NULL / FOREIGN KEY / UNIQUE nếu cần
                  |
                  v
6. OBSERVE
   Theo dõi lock, latency, lỗi ứng dụng, replication và dữ liệu
                  |
                  v
7. CONTRACT
   Chỉ xóa cấu trúc chuyển tiếp ở release sau khi không còn consumer
~~~

Thứ tự cụ thể phụ thuộc thay đổi. Với NOT NULL, cần bảo vệ ghi mới trước hoặc trong lúc backfill để không phát sinh NULL mới. Với foreign key, cần bảo đảm bảng cha và unique key đã tồn tại, kiểm tra orphan và tạo index phù hợp. Với index, cần xác định workload, uniqueness, cách tạo online và cách xử lý index lỗi.

### 2.1. Mỗi giai đoạn phải có hậu điều kiện

| Giai đoạn | Hậu điều kiện |
|---|---|
| Expand | Cột hoặc đối tượng mới tồn tại, ứng dụng cũ vẫn hoạt động |
| Protect | Ghi mới không tạo giá trị vi phạm |
| Backfill | Số dòng chưa xử lý giảm về 0, dữ liệu được ghi đúng |
| Validate | Truy vấn invariant trả kết quả đạt; constraint đã được xác thực |
| Enforce | Metadata DBMS cho thấy NOT NULL/FK/unique đã bật |
| Observe | Không có lỗi tăng bất thường, lock kéo dài hoặc replication lag vượt ngưỡng |
| Contract | Không còn ứng dụng/job dùng cấu trúc cũ |

Không đánh dấu migration hoàn tất chỉ vì DATABASECHANGELOG có dòng changeset. Cần xác minh trạng thái schema và dữ liệu vật lý.

## 3. Chuẩn bị Liquibase và quy tắc changeset

Liquibase giúp version hóa các bước thay đổi, lưu lịch sử và điều phối thực thi. Với DDL trên bảng lớn, hãy thiết kế changeset nhỏ, có tên thể hiện mục tiêu, có precondition phù hợp và rollback được đánh giá riêng.

Ví dụ cấu trúc:

~~~text
db/changelog/
  orders/
    db.changelog-master.yaml
    040-add-delivery-status.yaml
    041-protect-delivery-status.yaml
    042-backfill-delivery-status.yaml
    043-enforce-delivery-status.yaml
    044-create-orders-customer-index.yaml
    045-add-orders-customer-fk.yaml
~~~

Đây là cách phân chia minh họa; một backfill lớn có thể được thực hiện bởi job riêng thay vì một changeset chạy toàn bộ trong một transaction. Root changelog phải include đúng thứ tự và mọi changeset đã triển khai phải được giữ bất biến.

### 3.1. Không sửa changeset đã chạy

Nếu changeset tạo cột đã được triển khai, không sửa trực tiếp để thêm NOT NULL sau này. Thêm changeset mới. Thay đổi lịch sử có thể gây checksum mismatch, trong khi database cũ và database mới có thể nhận cấu trúc khác nhau.

### 3.2. Dùng precondition để dừng khi giả định sai

Precondition có thể xác minh bảng/cột tồn tại hoặc dữ liệu đã đạt điều kiện. Tuy nhiên, precondition không tự thay thế kế hoạch backfill, lock và kiểm tra hiệu năng.

Với thay đổi bắt buộc, ưu tiên dừng rõ ràng khi invariant chưa đạt. Không dùng MARK_RAN để ghi nhận changeset đã chạy trong khi constraint thực tế chưa được tạo.

### 3.3. Cẩn thận với changeset không transactional

Một số câu lệnh online/concurrent không thể chạy trong transaction. Khi dùng runInTransaction: false, giữ changeset nhỏ, tốt nhất chỉ chứa một thao tác độc lập và có kế hoạch kiểm tra trạng thái nếu lệnh thất bại giữa chừng.

Liquibase không thể rollback một câu DDL đã commit chỉ vì ghi nhận changeset thất bại. Phải kiểm tra catalog database trước khi retry.

## 4. Thêm NOT NULL an toàn trên bảng lớn

Giả sử bảng app.orders có cột delivery_status mới được thêm ở dạng nullable. Yêu cầu là cuối cùng mọi dòng phải có giá trị và database phải từ chối ghi NULL.

Cách thêm ngay:

~~~sql
ALTER TABLE app.orders
ALTER COLUMN delivery_status SET NOT NULL;
~~~

có thể buộc DBMS quét dữ liệu và lấy lock mạnh. Trên bảng lớn, thao tác có thể làm request ghi chờ lâu. Một chiến lược nhiều bước giúp chủ động kiểm soát thời gian và tải.

### 4.1. Bước 1: thêm cột nullable

Ví dụ Liquibase YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-040-add-delivery-status
      author: database-team
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: delivery_status
                  type: VARCHAR(24)
~~~

Cột nullable giúp ứng dụng cũ tiếp tục hoạt động nếu nó chưa gửi giá trị. Không thêm NOT NULL ngay nếu dữ liệu hiện tại chưa được backfill và mọi writer chưa tương thích.

Kiểm tra tác động của ADD COLUMN theo DBMS/version. Một số engine có thể thực hiện thay đổi metadata nhanh với kiểu/default phù hợp; kiểu dữ liệu, default expression hoặc phiên bản khác có thể dẫn tới rewrite.

### 4.2. Bước 2: triển khai ứng dụng tương thích

Trước khi bắt buộc NOT NULL, bảo đảm tất cả writer có thể cung cấp delivery_status:

- API và service ghi đơn hàng.
- Batch import.
- Consumer message/event.
- Script quản trị.
- ETL hoặc integration bên ngoài.

Có thể triển khai code mới để ghi giá trị mặc định nghiệp vụ. Trong giai đoạn rolling deployment, phiên bản cũ vẫn có thể ghi NULL; vì vậy cần xác định khi nào toàn bộ writer đã được cập nhật.

### 4.3. Bước 3: bảo vệ ghi mới

Nếu DBMS hỗ trợ, có thể thêm một CHECK constraint chưa validate để kiểm soát các dòng mới và dòng được cập nhật, trong khi chưa quét toàn bộ dữ liệu cũ. Ví dụ riêng cho PostgreSQL:

~~~sql
ALTER TABLE app.orders
ADD CONSTRAINT ck_orders_delivery_status_nn
CHECK (delivery_status IS NOT NULL) NOT VALID;
~~~

NOT VALID có nghĩa constraint chưa được kiểm tra trên toàn bộ dòng hiện có tại thời điểm thêm. PostgreSQL vẫn áp dụng điều kiện cho các INSERT/UPDATE mới sau khi constraint được tạo. Dòng cũ còn NULL có thể tồn tại cho đến khi backfill và validate hoàn tất.

Một hệ quả cần tính trước: khi một dòng cũ còn NULL bị UPDATE, PostgreSQL cũng kiểm tra CHECK trên phiên bản dòng mới. Vì vậy, một câu UPDATE chỉ sửa cột khác vẫn có thể thất bại nếu delivery_status tiếp tục là NULL. Backfill cần gán delivery_status trong cùng thao tác cập nhật; đồng thời phải xác nhận ứng dụng cũ không có luồng cập nhật các dòng đó mà vẫn để NULL. Đây là lý do cần triển khai writer tương thích và kiểm tra workload trước khi bật CHECK.

Có thể quản lý bước này bằng changeset Liquibase:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-041-protect-delivery-status
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              ADD CONSTRAINT ck_orders_delivery_status_nn
              CHECK (delivery_status IS NOT NULL) NOT VALID;
      rollback:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              DROP CONSTRAINT ck_orders_delivery_status_nn;
~~~

Cú pháp NOT VALID trong ví dụ là đặc thù PostgreSQL. Không dùng nguyên văn trên DBMS khác. Constraint name cần được kiểm soát để tránh trùng với đối tượng có sẵn.

### 4.4. Bước 4: backfill theo batch

Không nên cập nhật hàng triệu dòng trong một transaction lớn nếu có thể tránh. Chia dữ liệu thành các batch có giới hạn, checkpoint và khả năng tiếp tục.

Ví dụ SQL minh họa cho một batch theo khóa tăng dần:

~~~sql
UPDATE app.orders
SET delivery_status = 'PENDING'
WHERE id > :lower_id
  AND id <= :upper_id
  AND delivery_status IS NULL;
~~~

:lower_id và :upper_id là tham số do job backfill điều khiển, không phải cú pháp placeholder được gửi nguyên văn cho Liquibase. Job cần:

1. Chọn khoảng khóa có giới hạn.
2. Chỉ cập nhật các dòng còn NULL.
3. Commit batch.
4. Ghi checkpoint.
5. Đo thời gian, số dòng và replication lag.
6. Tạm dừng khi tải hoặc lag vượt ngưỡng.
7. Tiếp tục từ checkpoint sau khi phục hồi.

Giá trị PENDING chỉ là ví dụ. Phải xác nhận quy tắc nghiệp vụ; không gán một giá trị mặc định tùy tiện chỉ để làm cho constraint đạt.

Với bảng không có khóa tăng dần, có thể dùng khóa chính phù hợp, bảng công việc hoặc cơ chế phân trang ổn định. Tránh OFFSET lớn trên bảng rất lớn vì chi phí có thể tăng theo vị trí.

### 4.5. Bước 5: xác minh không còn NULL

Ví dụ:

~~~sql
SELECT COUNT(*) AS null_count
FROM app.orders
WHERE delivery_status IS NULL;
~~~

Kết quả mong đợi là 0. Trên bảng lớn, truy vấn chính xác có thể quét nhiều dữ liệu. Có thể dùng thống kê để theo dõi tiến độ nhưng trước khi enforce phải có kiểm tra chính xác hoặc cơ chế validate constraint do DBMS cung cấp.

Cần kiểm tra cả writer đang hoạt động: nếu ứng dụng cũ vẫn tạo NULL trong lúc backfill, số dòng có thể không về 0 hoặc lại tăng sau khi kiểm tra.

### 4.6. Bước 6: validate CHECK rồi đặt NOT NULL

PostgreSQL cho phép xác thực constraint đã thêm bằng:

~~~sql
ALTER TABLE app.orders
VALIDATE CONSTRAINT ck_orders_delivery_status_nn;
~~~

Sau khi constraint đã validated, có thể đặt NOT NULL:

~~~sql
ALTER TABLE app.orders
ALTER COLUMN delivery_status SET NOT NULL;
~~~

Ở các phiên bản PostgreSQL hỗ trợ tối ưu tương ứng, CHECK constraint đã được validate chứng minh không có NULL có thể giúp tránh quét lại toàn bảng khi đặt NOT NULL. Dù vậy, SET NOT NULL vẫn cần lock thích hợp; phải kiểm tra phiên bản và đo trên môi trường tương đương.

Sau khi NOT NULL đã được áp dụng, constraint CHECK tạm có thể được gỡ:

~~~sql
ALTER TABLE app.orders
DROP CONSTRAINT ck_orders_delivery_status_nn;
~~~

Nên tách validate, enforce và cleanup thành các changeset hoặc bước vận hành riêng để có thể dừng giữa các giai đoạn, kiểm tra trạng thái và tiếp tục an toàn.

### 4.7. Mẫu changeset cho validate và enforce

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-043-validate-delivery-status
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              VALIDATE CONSTRAINT ck_orders_delivery_status_nn;

  - changeSet:
      id: orders-044-enforce-delivery-status
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              ALTER COLUMN delivery_status SET NOT NULL;
~~~

Đây là minh họa PostgreSQL. Trước khi dùng, kiểm tra trạng thái constraint và cột trong catalog, phiên bản engine, lock timeout và quy tắc retry. Nếu changeset validate thành công nhưng enforce thất bại, constraint CHECK vẫn tồn tại và có thể tiếp tục bảo vệ ghi mới.

## 5. Thêm khóa ngoại trên bảng lớn

Một foreign key bảo đảm mỗi giá trị ở bảng con tham chiếu một hàng hợp lệ ở bảng cha. Ví dụ orders.customer_id tham chiếu customers.id.

Trước khi thêm FK, cần xác nhận:

- Bảng cha và bảng con tồn tại trong đúng schema.
- Cột hai bên có kiểu dữ liệu tương thích.
- Cột tham chiếu ở bảng cha có PRIMARY KEY hoặc UNIQUE phù hợp.
- Dữ liệu con hiện tại không có orphan rows.
- Các writer mới không tiếp tục tạo orphan.
- Có index phù hợp trên khóa ngoại ở bảng con cho workload cập nhật/xóa bảng cha.
- Tác động lock và validate đã được kiểm tra trên DBMS đích.

### 5.1. Tìm orphan rows trước khi thêm FK

Truy vấn minh họa:

~~~sql
SELECT COUNT(*) AS orphan_count
FROM app.orders o
LEFT JOIN app.customers c
  ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Nếu kết quả lớn hơn 0, cần xác định nguyên nhân và cách xử lý theo nghiệp vụ. Không tự xóa đơn hàng, gán customer giả hoặc bỏ qua dòng lỗi chỉ để thêm constraint.

Với bảng rất lớn, anti-join có thể tốn I/O. Đảm bảo bảng cha có index/primary key trên cột tham chiếu; cân nhắc index trên orders.customer_id và chạy trong cửa sổ phù hợp. Có thể chia kiểm tra theo khoảng khóa để điều tra, nhưng trước khi validate toàn constraint vẫn cần bằng chứng rằng toàn bộ dữ liệu hợp lệ.

### 5.2. Chuẩn bị index trên cột khóa ngoại

Nhiều DBMS không tự tạo index trên cột tham chiếu ở bảng con khi thêm foreign key. PostgreSQL không tự tạo index này. Index giúp truy vấn join và có thể giảm chi phí khi xóa/cập nhật khóa ở bảng cha vì engine phải tìm các dòng con liên quan.

Ví dụ index:

~~~sql
CREATE INDEX idx_orders_customer_id
ON app.orders (customer_id);
~~~

Trên bảng lớn, tạo index thường cần chiến lược online/concurrent nếu DBMS hỗ trợ. Không tạo index một cách máy móc nếu đã có index bắt đầu bằng cùng cột và đáp ứng workload; kiểm tra thứ tự cột, predicate, selectivity và kế hoạch truy vấn.

### 5.3. PostgreSQL: ADD FOREIGN KEY NOT VALID

PostgreSQL cho phép thêm FK với NOT VALID:

~~~sql
ALTER TABLE app.orders
ADD CONSTRAINT fk_orders_customers
FOREIGN KEY (customer_id)
REFERENCES app.customers (id)
NOT VALID;
~~~

Cách này tránh kiểm tra toàn bộ dữ liệu cũ ngay tại thời điểm thêm constraint. Constraint vẫn được áp dụng cho các thay đổi mới sau khi được tạo. Sau khi dữ liệu cũ được xác minh, chạy:

~~~sql
ALTER TABLE app.orders
VALIDATE CONSTRAINT fk_orders_customers;
~~~

Validation kiểm tra các dòng hiện hữu. Trong PostgreSQL, thao tác này dùng mức lock được thiết kế để giảm cản trở hoạt động ghi so với một số cách thêm constraint trực tiếp; vẫn có thể tiêu tốn I/O và cần chờ/đụng các lock khác. Kiểm tra đúng phiên bản và workload trước khi chạy.

Ví dụ Liquibase:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-050-add-customer-fk-not-valid
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              ADD CONSTRAINT fk_orders_customers
              FOREIGN KEY (customer_id)
              REFERENCES app.customers (id)
              NOT VALID;
      rollback:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              DROP CONSTRAINT fk_orders_customers;

  - changeSet:
      id: orders-051-validate-customer-fk
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              VALIDATE CONSTRAINT fk_orders_customers;
~~~

NOT VALID không có nghĩa FK bị vô hiệu hóa hoàn toàn. Nó bỏ qua xác minh dữ liệu cũ tại lúc thêm; các thao tác ghi mới vẫn phải tuân thủ constraint. Đây là điểm quan trọng để backfill/repair dữ liệu cũ mà không tạo thêm orphan.

### 5.4. Khi validate FK thất bại

Nếu có orphan rows, validation thất bại và constraint vẫn tồn tại ở trạng thái chưa validated. Không xóa lịch sử Liquibase hoặc tự đánh dấu changeset thành công. Hãy:

1. Đọc lỗi và xác định khóa gây vi phạm.
2. Kiểm tra nguồn phát sinh orphan.
3. Sửa dữ liệu theo quy tắc nghiệp vụ.
4. Xác nhận writer mới không tạo thêm orphan.
5. Chạy lại validate có kiểm soát.
6. Kiểm tra metadata constraint đã validated.

Nếu constraint đã được tạo nhưng changeset ghi nhận không hoàn tất do lỗi ngoài dự kiến, kiểm tra catalog trước khi retry. Không chạy lại lệnh ADD CONSTRAINT khi đối tượng đã tồn tại.

## 6. Tạo chỉ mục trên bảng lớn

Index cải thiện một số truy vấn đọc nhưng có chi phí tạo và duy trì. Mỗi index bổ sung có thể làm tăng dung lượng, thời gian INSERT/UPDATE/DELETE, vacuum/maintenance và chi phí backup.

Trước khi tạo index:

- Xác định truy vấn hoặc constraint cần index.
- Kiểm tra index hiện có và thứ tự cột.
- Xem query plan và selectivity.
- Đo kích thước bảng và index dự kiến.
- Đánh giá dung lượng trống và I/O.
- Chọn chế độ tạo index phù hợp DBMS.
- Xác định cách xử lý khi lệnh bị ngắt.
- Chuẩn bị hậu kiểm index hợp lệ và được optimizer sử dụng.

### 6.1. PostgreSQL: CREATE INDEX CONCURRENTLY

PostgreSQL hỗ trợ CREATE INDEX CONCURRENTLY, cho phép các thao tác ghi tiếp tục trong phần lớn quá trình xây index, nhưng lệnh có thể chạy lâu và phải chờ một số transaction/snapshot. Nó không hoàn toàn không khóa.

Ví dụ:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON app.orders (customer_id, created_at);
~~~

Lệnh này không được chạy bên trong transaction block. Với Liquibase, changeset cần runInTransaction: false:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-060-create-customer-created-index
      author: database-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_orders_customer_created
              ON app.orders (customer_id, created_at);
      rollback:
        - sql:
            splitStatements: false
            sql: |
              DROP INDEX CONCURRENTLY app.idx_orders_customer_created;
~~~

Một changeset không transactional nên chỉ chứa một thao tác chính. Nếu tạo index thất bại, PostgreSQL có thể để lại index invalid. Trước khi retry, kiểm tra catalog và xử lý index invalid theo quy trình phù hợp. Không thêm IF NOT EXISTS một cách máy móc: tên index đã tồn tại nhưng invalid có thể khiến câu lệnh bỏ qua thay vì tạo index hợp lệ.

### 6.2. Kiểm tra tiến độ và trạng thái index PostgreSQL

Có thể quan sát tiến độ qua view hệ thống phù hợp, ví dụ pg_stat_progress_create_index, và kiểm tra trạng thái trong pg_index:

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_index i
WHERE i.indexrelid = 'app.idx_orders_customer_created'::regclass;
~~~

Kết quả indisvalid = true là một phần bằng chứng index hợp lệ; cần kiểm tra thêm định nghĩa, bảng đích và query plan. Không chỉ dựa vào việc tên index xuất hiện trong catalog.

### 6.3. Index duy nhất trên bảng lớn

Nếu cần UNIQUE, trước hết tìm duplicate theo đúng quy tắc collation/normalization/NULL của DBMS. Với PostgreSQL, có thể tạo unique index concurrently rồi gắn constraint bằng index đó:

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY ux_customers_external_code
ON app.customers (external_code);

ALTER TABLE app.customers
ADD CONSTRAINT uq_customers_external_code
UNIQUE USING INDEX ux_customers_external_code;
~~~

Hai lệnh cần được chia theo transaction/changeset phù hợp: CREATE INDEX CONCURRENTLY phải chạy ngoài transaction block; việc gắn constraint là thao tác riêng. Nếu unique index build thất bại vì duplicate, xử lý dữ liệu trước khi retry. Không xóa duplicate tùy tiện.

Unique index partial hoặc expression có thể không phù hợp để gắn thành UNIQUE constraint theo cách trên. Hãy xác định liệu yêu cầu là constraint nghiệp vụ hay index phục vụ query.

## 7. Chiến lược theo DBMS

Không có một cú pháp online DDL chung cho mọi database. Phải kiểm tra đúng phiên bản engine, edition, storage engine và loại thao tác.

| DBMS | Cơ chế thường gặp | Điểm cần xác minh |
|---|---|---|
| PostgreSQL | NOT VALID, VALIDATE CONSTRAINT, CREATE INDEX CONCURRENTLY | Lock mode, phiên bản, transaction block, index invalid |
| MySQL/InnoDB | Online DDL với ALGORITHM và LOCK tùy thao tác/version | Engine, version, loại ALTER, metadata lock, FK và fallback |
| SQL Server | ONLINE = ON cho một số thao tác index/version/edition; resumable index build ở cấu hình hỗ trợ | Edition, version, loại index, lock ngắn ở đầu/cuối |
| Oracle | Một số thao tác online/parallel và cơ chế constraint enable/validate | Version, option/licensing, khóa và giới hạn DDL |

### 7.1. MySQL/InnoDB

Một số thao tác ALTER TABLE hỗ trợ ALGORITHM=INPLACE hoặc ALGORITHM=INSTANT, và có thể dùng LOCK=NONE khi engine/version hỗ trợ. Nhưng không phải mọi thay đổi NOT NULL, FK hoặc index đều được thực hiện online.

Ví dụ dạng lệnh cần đánh giá theo phiên bản:

~~~sql
ALTER TABLE orders
ADD INDEX idx_orders_customer_created (customer_id, created_at),
ALGORITHM=INPLACE,
LOCK=NONE;
~~~

Nếu yêu cầu LOCK=NONE không được hỗ trợ, hãy để câu lệnh thất bại rõ ràng thay vì bỏ tùy chọn và vô tình cho phép thao tác khóa mạnh. Đọc kế hoạch/metadata của đúng phiên bản MySQL, thử trên bản sao có kích thước gần production và quan sát metadata lock.

Với thay đổi cần rebuild bảng hoặc không đáp ứng SLA, có thể cân nhắc công cụ online schema change như gh-ost hoặc pt-online-schema-change. Các công cụ này có trigger/replication/cutover và giới hạn riêng; cần review FK, trigger, unique key, replication và khả năng rollback.

### 7.2. SQL Server

SQL Server hỗ trợ một số tùy chọn online cho index tùy phiên bản, edition và loại thao tác. Ví dụ minh họa:

~~~sql
CREATE INDEX IX_Orders_Customer_Created
ON dbo.Orders (CustomerId, CreatedAt)
WITH (ONLINE = ON);
~~~

Không giả định mọi edition hoặc mọi loại index đều hỗ trợ ONLINE = ON. Một số thao tác vẫn cần lock ở các giai đoạn bắt đầu/kết thúc và có thể cần thêm dung lượng. Kiểm tra tài liệu đúng version/edition, thử trên dữ liệu đại diện và theo dõi blocking.

### 7.3. Oracle

Oracle có các tùy chọn online cho một số thao tác index/constraint và có thể hỗ trợ enable/validate constraint theo giai đoạn. Cú pháp, khả năng và điều kiện phụ thuộc version, loại đối tượng và cấu hình. Không copy câu lệnh PostgreSQL NOT VALID hoặc CREATE INDEX CONCURRENTLY sang Oracle.

### 7.4. H2 không thay thế DBMS production

H2 hữu ích cho test nhanh, nhưng không mô phỏng đầy đủ lock, DDL transaction, online index, optimizer, constraint validation hoặc SQL dialect của PostgreSQL/MySQL/SQL Server/Oracle. Với migration bảng lớn, cần integration test trên engine và version đại diện.

## 8. Thời gian lock, timeout và hoạt động hệ thống

Một thao tác online vẫn có thể cần lock metadata hoặc lock ngắn nhưng mạnh tại thời điểm bắt đầu/kết thúc. Nếu có transaction dài đang giữ lock, DDL có thể chờ; khi DDL đứng đầu hàng đợi, các request sau cũng có thể bị ảnh hưởng.

Trước khi chạy:

- Xác định transaction dài và query đang giữ lock.
- Chọn lock_timeout/timeout phù hợp theo DBMS.
- Đặt statement timeout hoặc job timeout có giới hạn.
- Chạy ở thời điểm tải phù hợp.
- Theo dõi active sessions, lock waits và deadlocks.
- Theo dõi CPU, I/O, disk free, WAL/binlog/transaction log.
- Theo dõi replication lag và consumer lag.
- Chuẩn bị điều kiện dừng khi latency hoặc lỗi vượt ngưỡng.

Không đặt timeout quá lớn chỉ để DDL cuối cùng chạy được. Một lệnh chờ lock kéo dài có thể gây sự cố dây chuyền.

### 8.1. Quan sát trong lúc triển khai

Các chỉ số hữu ích:

| Nhóm | Chỉ số |
|---|---|
| Database sessions | Active sessions, long transactions, lock wait, deadlock |
| DDL/index | Tiến độ build, thời gian chạy, index validity |
| Tài nguyên | CPU, IOPS, disk free, temp space, WAL/binlog |
| Replication | Lag, apply rate, replica health |
| Ứng dụng | p95/p99 latency, timeout, error rate, pool saturation |
| Dữ liệu | NULL còn lại, orphan, duplicate, batch progress |

Ghi nhận baseline trước migration để phân biệt tải bình thường và ảnh hưởng do DDL. Khi vượt ngưỡng, dừng bước tiếp theo và xử lý trạng thái hiện tại; không khởi chạy thêm một bản DDL song song.

## 9. Backfill quy mô lớn

Backfill thường là phần tốn thời gian nhất khi chuẩn bị NOT NULL hoặc FK. Không nên gộp một UPDATE hàng triệu dòng vào changeset mặc định nếu nó tạo transaction lớn, giữ lock lâu hoặc tạo lượng log vượt khả năng hệ thống.

### 9.1. Chia batch và checkpoint

Một job backfill nên có:

- Khóa phân trang ổn định.
- Kích thước batch được cấu hình và đo.
- Điều kiện idempotent để có thể chạy lại.
- Checkpoint sau mỗi batch.
- Giới hạn tốc độ hoặc thời gian nghỉ.
- Metric số dòng đọc/cập nhật/lỗi.
- Cơ chế pause/resume.
- Quy tắc xử lý dòng không thể chuyển đổi.
- Hậu kiểm sau khi hoàn tất.

Ví dụ logic:

~~~text
last_processed_id = checkpoint

while còn dòng cần xử lý:
    lấy một khoảng khóa tiếp theo
    cập nhật các dòng trong khoảng còn thiếu giá trị
    commit batch
    xác minh số dòng đã xử lý
    lưu checkpoint
    nếu tải/replication lag vượt ngưỡng:
        tạm dừng
~~~

Job có thể chạy ngoài Liquibase nhưng phải được quản lý cùng release: version, code, tham số, log và trạng thái. Liquibase changeset nên thể hiện điểm bắt đầu/kết thúc hoặc trạng thái schema; không để một script cá nhân không được version hóa trở thành bước bắt buộc trong production.

### 9.2. Tránh ghi đè dữ liệu mới

Điều kiện backfill phải chỉ cập nhật dòng còn thiếu, ví dụ WHERE delivery_status IS NULL. Không ghi đè giá trị mà ứng dụng đã cập nhật trong lúc job chạy.

Nếu cần chuyển đổi phức tạp, dùng bảng staging hoặc mapping có version để có thể xác định dòng nào đã được xử lý. Kiểm tra concurrency giữa backfill và ứng dụng ghi dữ liệu.

### 9.3. Tính đúng của giá trị backfill

Không phải mọi NULL đều có thể gán cùng một default. Ví dụ customer_id không thể gán một khách hàng giả cho các đơn hàng mồ côi. Có thể cần đối chiếu nguồn dữ liệu chuẩn, sửa mapping hoặc đưa dòng lỗi vào quy trình xử lý thủ công.

Nếu không xác định được giá trị đúng, dừng enforce constraint và xử lý dữ liệu nghiệp vụ trước.

## 10. Precondition và hậu điều kiện trong Liquibase

Precondition giúp kiểm tra giả định trước khi changeset chạy. Ví dụ trước khi validate NOT NULL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-042-check-delivery-status-ready
      author: database-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.orders
              WHERE delivery_status IS NULL
      changes:
        - sql:
            sql: |
              ALTER TABLE app.orders
              VALIDATE CONSTRAINT ck_orders_delivery_status_nn;
~~~

Đây là minh họa; SQL check có thể tốn kém trên bảng lớn và validate constraint đã thực hiện kiểm tra chính xác. Có thể ưu tiên native validation của DBMS làm nguồn xác nhận cuối cùng thay vì quét thủ công nhiều lần.

Hậu điều kiện sau changeset:

- Cột có NOT NULL trong metadata.
- Constraint FK tồn tại và đã validated.
- Index tồn tại, đúng định nghĩa và trạng thái valid/usable.
- Không còn NULL, orphan hoặc duplicate theo invariant.
- Ứng dụng và truy vấn quan trọng hoạt động bình thường.

Không coi status EXECUTED trong DATABASECHANGELOG là bằng chứng duy nhất. Changeset có thể được ghi nhận theo các trạng thái khác nhau; phải xem EXECTYPE và catalog.

## 11. Tổ chức changeset theo giai đoạn

Một cách tổ chức minh họa cho PostgreSQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-040-add-delivery-status
      author: database-team
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: delivery_status
                  type: VARCHAR(24)

  - changeSet:
      id: orders-041-protect-delivery-status
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              ADD CONSTRAINT ck_orders_delivery_status_nn
              CHECK (delivery_status IS NOT NULL) NOT VALID;

  - changeSet:
      id: orders-043-validate-delivery-status
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              VALIDATE CONSTRAINT ck_orders_delivery_status_nn;

  - changeSet:
      id: orders-044-enforce-delivery-status
      author: database-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              ALTER TABLE app.orders
              ALTER COLUMN delivery_status SET NOT NULL;
~~~

Backfill có thể nằm giữa các changeset 041 và 043, được chạy bởi job theo batch. Khi làm vậy, release orchestration phải chờ backfill hoàn tất trước khi chạy validate. Không để root changelog tự chạy validate ngay sau protect nếu backfill là một bước bất đồng bộ chưa hoàn thành.

### 11.1. Không dùng một changeset dài cho toàn bộ quy trình

Nếu một changeset vừa thêm cột, backfill hàng triệu dòng, thêm FK, tạo index và enforce NOT NULL, khó kiểm soát transaction, timeout và partial failure. Tách ra giúp:

- Deploy ứng dụng tương thích trước.
- Chạy backfill trong khoảng thời gian riêng.
- Validate khi dữ liệu sẵn sàng.
- Theo dõi tiến độ từng bước.
- Dừng hoặc tiếp tục mà không lặp lại thao tác đã hoàn tất.

## 12. Rollback và phục hồi

Không phải mọi bước đều có mức rollback giống nhau.

| Bước | Khả năng đảo ngược | Điều cần lưu ý |
|---|---|---|
| Thêm cột nullable | Có thể drop cột | Nếu ứng dụng đã ghi dữ liệu, drop sẽ mất dữ liệu |
| Thêm CHECK/FK | Có thể drop constraint | Sau khi drop, database không còn bảo vệ invariant |
| Backfill | Không tự đảo ngược | Cần lưu giá trị cũ hoặc quy tắc phục hồi |
| Tạo index | Có thể drop index | Tốn thời gian/tài nguyên nếu phải tạo lại |
| Enforce NOT NULL | Có thể drop NOT NULL | Không khôi phục các NULL ban đầu đã backfill |
| Validate constraint | Không thay đổi dữ liệu | Trạng thái constraint có thể vẫn giữ sau lỗi bước sau |

### 12.1. Rollback của index concurrent

Nếu PostgreSQL tạo index concurrent thất bại, có thể cần xử lý index invalid. Trước khi drop, xác minh tên và định nghĩa đúng. DROP INDEX CONCURRENTLY cũng không chạy trong transaction block; changeset rollback cần runInTransaction: false nếu thực thi theo cách đó.

### 12.2. Rollback dữ liệu backfill

Nếu backfill đã thay NULL bằng PENDING, rollback bằng cách đổi tất cả PENDING về NULL có thể làm hỏng những dòng mà người dùng đã thay đổi trạng thái sau migration. Muốn đảo chính xác, phải lưu tập dòng đã được job sửa và giá trị trước đó, hoặc dùng một cơ chế audit/mapping có kiểm soát.

Nếu không có dữ liệu gốc, forward-fix thường an toàn hơn rollback giả định.

### 12.3. Không drop cấu trúc chuyển tiếp quá sớm

Một CHECK tạm hoặc cột cũ chỉ nên được cleanup khi constraint cuối đã bật, mọi ứng dụng tương thích và hậu điều kiện đạt. Giữ lại cấu trúc chuyển tiếp thêm một release có thể giúp rollback ứng dụng an toàn hơn.

## 13. Kiểm thử trên dữ liệu và DBMS đại diện

Một migration có thể chạy nhanh trên database test 1.000 dòng nhưng mất hàng giờ trên production. Cần test với quy mô, phân bố dữ liệu và tải gần thực tế.

Các trường hợp kiểm thử:

- Bảng có hàng triệu dòng và tỷ lệ NULL thực tế.
- Có transaction dài và writer liên tục.
- Có duplicate/orphan để xác nhận validation dừng đúng.
- Có index trùng hoặc index invalid từ lần thử trước.
- Có replica/CDC để quan sát lag.
- Có phiên bản ứng dụng cũ và mới chạy song song.
- Có DDL thất bại giữa chừng và quy trình retry.
- Có rollback/forward-fix trên bản sao.

### 13.1. Test fresh install và upgrade path

Fresh install xác nhận root changelog tạo được schema cuối cùng. Upgrade path xác nhận migration mới hoạt động trên database đã có lịch sử và dữ liệu. Với NOT NULL/FK/index trên bảng lớn, upgrade path là bài test quan trọng vì chỉ ở đó mới có dữ liệu và workload đại diện.

### 13.2. Đo chứ không đoán

Ghi lại:

- Thời gian lock chờ và lock giữ.
- Thời gian backfill/validation/index build.
- CPU, I/O, WAL/log và dung lượng.
- Replication lag.
- p95/p99 latency và error rate.
- Số dòng cập nhật, NULL/orphan còn lại.
- Trạng thái constraint/index sau khi chạy.

Dùng số liệu để chọn batch size, cửa sổ triển khai và ngưỡng dừng.

## 14. Triển khai theo DBMS và phiên bản

Một thay đổi được hỗ trợ online ở một DBMS có thể gây lock dài ở DBMS khác. Hãy ghi rõ matrix hỗ trợ:

| Thành phần | Thông tin cần cố định |
|---|---|
| DBMS | PostgreSQL/MySQL/SQL Server/Oracle |
| Version | Phiên bản major/minor được hỗ trợ |
| Storage engine | Ví dụ InnoDB với MySQL |
| Liquibase | Version CLI hoặc dependency Spring Boot |
| JDBC driver | Version tương thích |
| DDL mode | Concurrent/online/in-place/transactional |
| Timeout | Lock/statement/job timeout |
| Replication | Kiểu replication và lag threshold |

Không dùng H2 làm bằng chứng duy nhất cho một thay đổi online DDL. SQL sinh ra từ Liquibase có thể khác theo DBMS; cần xem update-sql và test trên engine thật.

## 15. CI/CD và điều phối deployment

Một pipeline có thể chia migration thành các cổng:

~~~text
Pull request
    |
    v
Review DDL + dữ liệu + DBMS compatibility
    |
    v
validate + status + update-sql
    |
    v
Test trên database có dữ liệu đại diện
    |
    v
Expand schema
    |
    v
Deploy ứng dụng tương thích
    |
    v
Backfill job theo batch
    |
    v
Kiểm tra NULL / orphan / duplicate
    |
    v
Validate constraint + enforce
    |
    v
Hậu kiểm index / lock / latency / replication
    |
    v
Cho phép release tiếp theo
~~~

Các điểm kiểm soát:

- Mỗi bước có artifact và version rõ ràng.
- Không sửa changeset đã chạy.
- Backfill job có checkpoint và idempotency.
- Có thể pause/resume mà không ghi đè dữ liệu mới.
- SQL preview và update dùng cùng artifact/config.
- Migration bắt buộc thất bại phải trả exit code non-zero.
- Không rollout ứng dụng phụ thuộc constraint khi bước enforce chưa hoàn tất.
- Ghi trạng thái từng database nếu triển khai nhiều target.
- Lưu log và kết quả hậu kiểm đã loại bỏ secret/PII.

### 15.1. Giới hạn concurrency

Không chạy đồng thời nhiều backfill hoặc index build nặng trên cùng database nếu chưa đo tài nguyên. Một job có thể làm tăng I/O và kéo dài job khác; nhiều DDL cùng chờ lock có thể tạo hàng đợi request.

Orchestrator nên giới hạn số migration job theo database/target, có cancellation policy và chỉ cho retry khi trạng thái trước đã được xác minh.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| SET NOT NULL bị timeout | Scan bảng hoặc lock chờ lâu | Xác minh CHECK đã validate, transaction dài và lock |
| Backfill không về 0 NULL | Writer cũ vẫn ghi NULL hoặc batch bỏ sót | Kiểm tra mọi producer và checkpoint |
| FK validation thất bại | Orphan rows tồn tại | Tìm khóa vi phạm, sửa dữ liệu theo nghiệp vụ |
| ADD FK bị chặn | Lock/dependency hoặc DDL không phù hợp | Xem DBMS lock mode và trạng thái transaction |
| CREATE INDEX CONCURRENTLY thất bại | Duplicate, deadlock, cancel hoặc resource | Kiểm tra catalog, index invalid, log |
| Index có tên nhưng query không dùng | Định nghĩa/order/predicate không phù hợp hoặc optimizer chọn khác | Xem query plan và statistics |
| Retry báo index đã tồn tại | Lần trước để lại index invalid hoặc valid | Kiểm tra catalog trước khi chạy lại |
| Replication lag tăng | Backfill hoặc index build tạo tải/log lớn | Giảm batch/concurrency, pause theo ngưỡng |
| Ứng dụng lỗi sau thêm NOT NULL | Writer cũ không gửi giá trị | Kiểm tra rollout và mọi producer |
| DDL giữ lock lâu | Transaction dài hoặc DDL scan/rewrite | Xác định blocker, timeout và chiến lược online |
| Liquibase báo changeset lỗi nhưng DDL đã tồn tại | Non-transactional/partial execution | Kiểm tra catalog trước retry; không xóa history tùy tiện |
| Rollback làm mất dữ liệu mới | Rollback drop cột hoặc đảo DML quá rộng | Dừng rollback, đánh giá forward-fix/restore |

## 17. Bài thực hành: thêm NOT NULL, FK và index trên bảng orders

**Mục tiêu:** cấu hình migration an toàn cho bảng lớn trên PostgreSQL lab. Bài thực hành chỉ dùng database thử nghiệm có dữ liệu synthetic và có thể tạo lại; không chạy trên production.

### Bước 1. Tạo dữ liệu lab

Tạo bảng customers và orders có số lượng dòng đủ để quan sát thời gian. Tạo một số dòng NULL và orphan có chủ đích trong một bản test riêng để kiểm tra validation.

~~~sql
CREATE TABLE app.customers (
    id BIGINT PRIMARY KEY,
    customer_code VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE app.orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT,
    delivery_status VARCHAR(24)
);
~~~

Không dùng dữ liệu cá nhân thật. Ghi lại số dòng, tỷ lệ NULL và orphan ban đầu.

### Bước 2. Tạo index trên khóa ngoại

Chạy CREATE INDEX CONCURRENTLY trên orders.customer_id bằng changeset runInTransaction: false. Quan sát tiến độ và trạng thái index. Xác nhận định nghĩa đúng và indisvalid là true.

### Bước 3. Bảo vệ ghi mới và sửa dữ liệu cũ

Thêm CHECK NOT VALID cho delivery_status. Backfill các dòng NULL theo batch với quy tắc nghiệp vụ đã xác nhận. Kiểm tra số dòng còn NULL bằng 0.

### Bước 4. Validate và enforce NOT NULL

Chạy VALIDATE CONSTRAINT, sau đó ALTER COLUMN ... SET NOT NULL. Xác nhận cột đã có thuộc tính NOT NULL trong catalog. Gỡ CHECK tạm nếu quy trình thiết kế yêu cầu.

### Bước 5. Thêm FK chưa validate

Kiểm tra orphan rows. Khi đã bảo đảm writer mới không tạo orphan, thêm FK NOT VALID, rồi chạy VALIDATE CONSTRAINT. Nếu validation thất bại, giữ nguyên bằng chứng và sửa dữ liệu trước khi retry.

### Bước 6. Kiểm tra hậu điều kiện

- Không còn delivery_status NULL.
- Không còn orders.customer_id tham chiếu customer không tồn tại.
- FK đã validated.
- Index hợp lệ và đúng cột/thứ tự.
- Query plan có thể sử dụng index trong truy vấn đại diện.
- Ứng dụng insert/update hoạt động.
- Không có replication lag hoặc latency vượt ngưỡng lab.
- DATABASECHANGELOG ghi nhận đúng các changeset.

### Bước 7. Thử lỗi và phục hồi

Trong database lab có thể tạo lại, thử hủy một index build hoặc để validation thất bại do orphan. Quan sát trạng thái vật lý sau lỗi. Không giả định Liquibase đã rollback mọi thao tác. Xác định cách drop index invalid, sửa dữ liệu và chạy lại từng bước an toàn.

## 18. Checklist trước khi enforce trên production

- [ ] Đã biết kích thước bảng, tốc độ ghi và transaction dài.
- [ ] Đã xác định DBMS/version và khả năng online/concurrent của đúng thao tác.
- [ ] Đã kiểm tra NULL, duplicate, orphan và kiểu dữ liệu hiện tại.
- [ ] Mọi writer đã tương thích hoặc có biện pháp bảo vệ ghi mới.
- [ ] Backfill chia batch, idempotent, có checkpoint và pause/resume.
- [ ] Giá trị backfill có quy tắc nghiệp vụ được phê duyệt.
- [ ] Index hiện có đã được xem xét để tránh tạo trùng.
- [ ] Index build có kế hoạch dung lượng, I/O, lock và retry.
- [ ] FK có parent key hợp lệ và index phía child phù hợp workload.
- [ ] NOT NULL/FK được validate trước khi enforce/hoàn tất.
- [ ] Changeset mới, không sửa lịch sử đã triển khai.
- [ ] runInTransaction: false chỉ dùng khi cần và changeset đủ nhỏ.
- [ ] Có precondition/hậu điều kiện phù hợp.
- [ ] SQL preview đã được review trên đúng DBMS.
- [ ] Có timeout, ngưỡng dừng và người theo dõi lock/replication.
- [ ] Fresh-install và upgrade-path test đều đạt.
- [ ] Rollback dữ liệu được đánh giá thực tế; có forward-fix/backup nếu cần.
- [ ] CI/CD lưu artifact, exit code và kết quả từng giai đoạn.
- [ ] Ứng dụng cũ/mới tương thích trong toàn bộ cửa sổ rollout.
- [ ] Hậu kiểm schema, data, index, latency và replication đạt trước khi contract.

## 19. Kết luận

Thêm NOT NULL, khóa ngoại và chỉ mục trên bảng lớn cần được xem là **một quy trình triển khai nhiều giai đoạn**, không phải một câu DDL đơn lẻ. Hãy thu thập hiện trạng, xác định invariant, bảo vệ ghi mới, backfill theo batch, validate dữ liệu rồi mới enforce constraint. Tạo index theo cơ chế online/concurrent phù hợp DBMS, theo dõi lock, I/O và replication trong suốt quá trình.

Liquibase giúp version hóa từng bước và ghi lịch sử, nhưng không tự làm cho DDL trở nên không khóa, không mất dữ liệu hay có thể rollback. Dùng changeset nhỏ, NOT VALID/VALIDATE CONSTRAINT khi DBMS hỗ trợ, runInTransaction: false đúng chỗ cho thao tác concurrent, cùng hậu kiểm catalog và ứng dụng. Kết hợp rollout tương thích, CI/CD có checkpoint và phương án forward-fix sẽ giúp hoàn tất ràng buộc trên bảng lớn với rủi ro được kiểm soát.
