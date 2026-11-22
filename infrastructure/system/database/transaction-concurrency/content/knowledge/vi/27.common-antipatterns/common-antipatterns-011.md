# Bỏ qua khóa do chỉ mục, ràng buộc hoặc trigger tạo ra

Một lỗi thiết kế concurrency thường gặp là chỉ nhìn các câu `SELECT ... FOR UPDATE`, `UPDATE` hoặc `DELETE` do ứng dụng viết rồi kết luận transaction đang khóa những hàng nào. Database còn phải duy trì index, kiểm tra constraint, thực thi trigger, cascade quan hệ và cập nhật các cấu trúc nội bộ. Những công việc này có thể đọc hoặc khóa thêm tài nguyên mà câu SQL bên ngoài không thể hiện trực tiếp.

Vì vậy, hai transaction có thể deadlock dù mỗi transaction chỉ cập nhật một hàng theo góc nhìn của ứng dụng. Một câu `INSERT` đơn giản có thể phải chờ một khóa duy nhất; cập nhật hàng con có thể cần xác nhận hàng cha; xóa hàng cha có thể tìm và xử lý nhiều hàng con; trigger có thể cập nhật một bảng thứ ba. Nếu thiết kế thứ tự khóa chỉ dựa trên câu SQL nhìn thấy, ta có thể bỏ qua một cạnh trong đồ thị chờ và không hiểu được deadlock thực tế.

Muốn kiểm soát concurrency, hãy xem toàn bộ công việc database thực hiện cho một câu lệnh: truy cập index, kiểm tra constraint, trigger, cascade và các thao tác phụ thuộc. Phạm vi khóa thực tế được quyết định bởi execution plan, schema, dữ liệu và hệ quản trị đang dùng.

## 1. Quan niệm sai: chỉ câu SQL tường minh mới lấy khóa

Giả sử code chỉ có một câu lệnh:

```sql
UPDATE employee
SET department_id = :new_department_id
WHERE employee_id = :employee_id;
```

Nhìn vào câu lệnh, ta có thể nghĩ transaction chỉ khóa hàng `employee` được cập nhật. Nhưng database có thể còn phải:

- Tìm hàng qua primary key hoặc một index khác.
- Kiểm tra foreign key để xác nhận phòng ban mới tồn tại.
- Duy trì index trên `employee.department_id` nếu cột này được lập chỉ mục.
- Kiểm tra unique constraint nếu có khóa duy nhất liên quan.
- Chạy trigger `BEFORE` hoặc `AFTER` để ghi audit hay cập nhật bảng khác.
- Kiểm tra hoặc thực hiện các hành động cascade do constraint quy định.

Các thao tác phụ thuộc này có thể cần khóa trên hàng cha, index key, hàng audit hoặc tài nguyên khác. Một transaction khác có thể đang giữ một trong những tài nguyên đó và chờ tài nguyên mà transaction hiện tại giữ.

Điều này không có nghĩa mọi index hoặc mọi constraint đều luôn tạo thêm một khóa hàng độc lập. Cách khóa chính xác phụ thuộc DBMS, loại constraint, index, execution plan và dữ liệu. Bài học là không thể suy ra lock footprint chỉ bằng cách đếm số câu SQL hoặc số hàng xuất hiện trong `WHERE`.

## 2. Những nguồn khóa ngầm cần tính đến

| Nguồn | Công việc database thực hiện | Tài nguyên có thể liên quan |
|---|---|---|
| Primary/secondary index | Tìm hàng, thêm/xóa/cập nhật index entry. | Index key, page, tuple/record, range hoặc khóa nội bộ tùy engine. |
| Unique constraint | Kiểm tra không có khóa trùng, phối hợp với transaction đang tạo cùng giá trị. | Unique index entry/key và transaction đang giữ thay đổi cạnh tranh. |
| Foreign key | Xác nhận hàng cha tồn tại; khi xóa/đổi khóa cha, tìm và xử lý hàng con. | Khóa tham chiếu ở cha, hàng con, index phía con. |
| Check/exclusion constraint | Đánh giá điều kiện hoặc loại trừ giá trị xung đột. | Hàng đang ghi và tài nguyên phụ thuộc vào cách triển khai constraint. |
| Trigger | Chạy SQL bổ sung khi insert/update/delete. | Hàng, index và bảng mà trigger truy cập. |
| Cascade | Lan truyền delete/update đến các hàng liên quan. | Nhiều hàng và index qua một hoặc nhiều bảng. |
| ORM/cascade ở ứng dụng | Sinh thêm câu SQL hoặc flush nhiều entity. | Các hàng và bảng mà ORM thực sự cập nhật. |
| DDL/schema metadata | Thay đổi bảng, index hoặc constraint. | Khóa metadata/schema và có thể chặn truy vấn đang chạy. |

Các nguồn trên có thể kết hợp. Ví dụ, một trigger ghi audit vào bảng có unique key; thao tác ghi audit lại phải kiểm tra foreign key. Một câu lệnh ban đầu có thể tạo ra chuỗi phụ thuộc dài hơn nhiều so với phần code gọi nó.

## 3. Index không chỉ giúp đọc nhanh

Index là cấu trúc dữ liệu cần được duy trì đồng bộ với bảng. Khi insert, delete hoặc thay đổi cột được index, database phải cập nhật index entry tương ứng.

Ví dụ:

```sql
CREATE INDEX ix_employee_department
ON employee (department_id);

UPDATE employee
SET department_id = 20
WHERE employee_id = 501;
```

Nếu `department_id` thay đổi, engine phải cập nhật biểu diễn index của hàng. Tùy DBMS và loại index, điều này có thể gồm đánh dấu entry cũ, thêm entry mới, khóa page hoặc key, và kiểm tra các constraint liên quan.

Index cũng ảnh hưởng đến cách tìm hàng cần khóa. Một truy vấn dùng index seek có thể tiếp cận một phạm vi nhỏ; truy vấn quét bảng hoặc index rộng có thể đọc và khóa nhiều tài nguyên hơn. Trong InnoDB, range scan dưới một số isolation level có thể lấy next-key/gap lock. Trong SQL Server, Serializable có thể dùng key-range lock. PostgreSQL dùng cơ chế khác cho row lock và predicate tracking ở Serializable.

Do đó, thay đổi index hoặc statistics có thể thay đổi execution plan và lock footprint, ngay cả khi câu SQL không đổi. Sau khi thêm index, đổi điều kiện lọc hoặc nâng cấp DBMS, hãy kiểm tra lại kế hoạch truy vấn và hành vi chờ khóa.

### 3.1. Index duy nhất tạo phối hợp khi ghi trùng khóa

Giả sử bảng có unique constraint:

```sql
CREATE TABLE user_account (
    user_id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE
);
```

Hai transaction đồng thời cố tạo cùng email:

```sql
-- Transaction A
INSERT INTO user_account (user_id, email)
VALUES (101, 'a@example.test');
```

```sql
-- Transaction B
INSERT INTO user_account (user_id, email)
VALUES (102, 'a@example.test');
```

Database không thể chỉ kiểm tra unique bằng một lần đọc thông thường rồi cho cả hai transaction tiếp tục. Nó phải phối hợp các thay đổi cạnh tranh trên khóa duy nhất. Một transaction có thể phải chờ transaction kia commit hoặc rollback; sau đó một bên thành công, bên còn lại nhận lỗi duplicate/unique violation hoặc kết quả phù hợp với cú pháp upsert.

Đây là hành vi bảo vệ tính duy nhất, không phải lỗi khóa cần né bằng cách bỏ constraint. Ứng dụng phải xử lý duplicate theo nghiệp vụ, ví dụ đọc tài khoản đã tồn tại nếu yêu cầu là “tạo nếu chưa có”. Không retry mù một insert chắc chắn vi phạm cùng unique key.

### 3.2. Nhiều index có thể mở rộng công việc ghi

Một hàng có thể nằm trong primary key, nhiều secondary index, unique index và index phục vụ FK. Mỗi lần ghi có thể cần duy trì nhiều cấu trúc. Điều đó ảnh hưởng thời gian transaction, số page được chạm và cơ hội xung đột với transaction khác.

Không nên xóa index chỉ vì thấy nó xuất hiện trong deadlock hoặc lock wait. Index có thể cần thiết cho hiệu năng truy vấn và constraint. Trước tiên hãy xác định index nào đang được dùng, nó có làm phạm vi quét rộng hay không, và chi phí duy trì có phù hợp với workload đọc/ghi.

## 4. Foreign key tạo phụ thuộc giữa hàng con và hàng cha

Khi insert hoặc đổi khóa ngoại ở bảng con, database phải xác nhận hàng cha được tham chiếu tồn tại. Khi xóa hoặc đổi khóa được tham chiếu ở bảng cha, database phải xác nhận không còn hàng con vi phạm hoặc thực hiện hành động `ON DELETE`/`ON UPDATE` đã khai báo.

Ví dụ:

```sql
CREATE TABLE department (
    department_id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES department (department_id)
        ON DELETE RESTRICT
);
```

Một lệnh insert employee có thể phải bảo vệ khóa cha trong lúc kiểm tra FK. Một lệnh delete department phải tìm các employee đang tham chiếu. Hai thao tác có thể xung đột dù câu SQL của ứng dụng chỉ ghi một bảng.

### 4.1. Ví dụ transaction con trước, cha sau

```text
T1: INSERT employee(department_id = 10)
    Database kiểm tra/bảo vệ department 10
    T1 tiếp tục ghi employee

T2: DELETE department WHERE department_id = 10
    Database cần kiểm tra hàng employee tham chiếu
```

Tùy thứ tự khóa và thời điểm commit, T2 có thể phải chờ T1. Nếu T1 commit, T2 có thể bị từ chối bởi `RESTRICT`/`NO ACTION`; nếu T1 rollback, T2 có thể tiếp tục. Engine phải giữ FK hợp lệ dù hai thao tác chạy đồng thời.

### 4.2. Index phía con ảnh hưởng đến kiểm tra FK

Khi xóa hoặc đổi khóa cha, database cần tìm hàng con có giá trị FK tương ứng. Index trên cột FK thường giúp tìm nhanh:

```sql
CREATE INDEX ix_employee_department_id
ON employee (department_id);
```

Nếu thiếu index, engine có thể phải quét nhiều hàng con. Việc quét kéo dài có thể làm transaction giữ khóa lâu hơn hoặc chạm nhiều tài nguyên hơn. Tuy nhiên, index con không tự thay đổi ngữ nghĩa FK và không phải DBMS nào cũng tự tạo index cho cột FK.

### 4.3. Cascade mở rộng phạm vi khóa

Với `ON DELETE CASCADE`, một câu `DELETE` trên hàng cha có thể xóa nhiều hàng con, rồi tiếp tục cascade qua quan hệ khác. Câu SQL bên ngoài chỉ có một hàng cha trong predicate nhưng transaction có thể sửa hàng trăm hoặc hàng nghìn hàng con.

Cascade cần được xem như một phần của transaction và lock footprint. Hãy ước lượng số hàng con, index cần duy trì, trigger có thể kích hoạt và thời gian giữ khóa. Nếu thao tác cascade lớn, cân nhắc batch hoặc quy trình xóa có kiểm soát theo đúng yêu cầu toàn vẹn.

## 5. Unique, check và exclusion constraint

Các constraint có vai trò khác nhau:

- **PRIMARY KEY/UNIQUE:** bảo đảm không có hai hàng cùng khóa. Thường dựa trên index duy nhất và cần phối hợp với insert/update cạnh tranh.
- **FOREIGN KEY:** bảo đảm tham chiếu hợp lệ giữa bảng con và bảng cha.
- **CHECK:** đánh giá biểu thức trên hàng đang ghi. Constraint `CHECK` thông thường không phải công cụ khóa các hàng khác để bảo vệ invariant nhiều hàng.
- **EXCLUSION:** trên PostgreSQL, có thể ngăn các hàng có giá trị/range xung đột theo toán tử được chỉ định; việc kiểm tra cạnh tranh có thể cần chờ hoặc từ chối transaction khác.

Ví dụ check constraint:

```sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_nonnegative
CHECK (available_quantity >= 0);
```

Constraint này bảo vệ điều kiện trên chính hàng inventory. Nó không tự bảo vệ một quy tắc tổng hợp như “tổng số reservation đang hoạt động không vượt sức chứa của nhiều hàng”. Với invariant nhiều hàng, cần mô hình dữ liệu, constraint hoặc giao thức transaction phù hợp.

Đừng giả định mọi biểu thức constraint đều có thể truy vấn bảng khác an toàn. Một số hệ quản trị giới hạn biểu thức, và việc nhúng truy vấn phụ thuộc vào dữ liệu khác trong CHECK thường không phải cách đáng tin cậy để bảo vệ invariant xuyên hàng. Hãy dùng FK, unique/exclusion constraint, trigger được thiết kế cẩn thận hoặc transaction protocol có khóa rõ ràng.

## 6. Trigger có thể truy cập thêm bảng và lấy thêm khóa

Trigger chạy tự động khi một sự kiện insert/update/delete xảy ra. Vì vậy, câu SQL gọi trigger có thể kéo theo các câu SQL khác mà caller không nhìn thấy.

Ví dụ trigger ghi audit:

```sql
CREATE TABLE employee_audit (
    audit_id BIGINT PRIMARY KEY,
    employee_id BIGINT NOT NULL,
    old_department_id BIGINT,
    new_department_id BIGINT,
    changed_at TIMESTAMP NOT NULL
);
```

Một trigger `AFTER UPDATE` trên `employee` có thể insert vào `employee_audit`. Nếu audit table có unique key, FK hoặc trigger riêng, thao tác update ban đầu có thể lấy thêm khóa và phát sinh thêm xung đột.

Trigger có thể:

- Đọc hoặc cập nhật bảng khác.
- Ghi audit hoặc outbox.
- Kiểm tra trạng thái tổng hợp.
- Kích hoạt trigger khác theo chuỗi.
- Cập nhật hàng cha hoặc hàng con.
- Gây đệ quy nếu cấu hình và logic cho phép.

Đặc biệt, hai trigger trên hai bảng khác nhau có thể truy cập chéo theo thứ tự ngược nhau. Transaction A cập nhật bảng X rồi trigger ghi Y; transaction B cập nhật Y rồi trigger ghi X. Dù code ứng dụng không có câu SQL trực tiếp cập nhật bảng thứ hai, deadlock vẫn có thể xuất hiện.

### 6.1. Ví dụ vòng chờ do trigger

```text
T1: UPDATE account SET ... WHERE id = 1
    Trigger: UPDATE account_summary WHERE account_id = 1

T2: UPDATE account_summary SET ... WHERE account_id = 1
    Trigger: UPDATE account WHERE id = 1
```

Nếu T1 giữ khóa `account(1)` rồi chờ `account_summary(1)`, trong khi T2 giữ khóa `account_summary(1)` rồi chờ `account(1)`, vòng chờ được tạo ra qua trigger. Chỉ đọc hai câu SQL ở tầng repository sẽ không giải thích đủ deadlock graph.

### 6.2. Trigger statement-level và row-level

Một số DBMS hỗ trợ trigger theo từng hàng và trigger theo từng câu lệnh. Trigger row-level có thể chạy nhiều lần cho một câu lệnh cập nhật nhiều hàng; trigger statement-level chạy một lần cho cả câu lệnh hoặc có cơ chế transition table tùy sản phẩm.

Điều này ảnh hưởng số lần truy cập bảng phụ và thứ tự khóa. Một câu `UPDATE` 10.000 hàng có thể kích hoạt trigger row-level 10.000 lần. Nếu trigger thực hiện truy vấn phụ cho mỗi hàng, chi phí và lock footprint có thể tăng đáng kể.

Hãy đọc định nghĩa trigger, kiểm tra loại trigger và số lần kích hoạt thực tế. Không giả định một trigger chỉ chạy một lần cho mỗi câu SQL.

## 7. ORM và stored procedure cũng che giấu thao tác phụ

ORM có thể tự flush nhiều entity, cập nhật bảng join, cascade quan hệ hoặc thực hiện optimistic version check. Một lời gọi repository tưởng như cập nhật một object có thể sinh nhiều câu SQL.

Ví dụ một thao tác xóa `Order` có thể:

1. Xóa các dòng `OrderLine` theo cascade của ORM.
2. Cập nhật bảng inventory để giải phóng reservation.
3. Ghi audit entity.
4. Xóa hoặc cập nhật bản ghi join.
5. Flush theo thứ tự do ORM quyết định.

Stored procedure cũng có thể chạy nhiều câu lệnh và gọi procedure khác. Nếu chỉ quan sát câu gọi procedure từ ứng dụng, bạn sẽ bỏ qua các bảng thực sự được truy cập bên trong.

Khi điều tra, hãy thu thập SQL đã phát ra ở mức phù hợp, execution plan và call stack/trace ứng dụng. Bật SQL logging trong thời gian giới hạn và che dữ liệu nhạy cảm; logging quá chi tiết có thể làm thay đổi hiệu năng benchmark.

## 8. Deadlock có thể hình thành qua khóa ngầm

Một deadlock cần vòng chờ, không cần hai câu SQL bên ngoài trực tiếp khóa cùng hai hàng. Các cạnh chờ có thể phát sinh từ FK, index, trigger, cascade hoặc khóa metadata.

Ví dụ tổng quát:

```text
Transaction A                         Transaction B
----------------                       ----------------
UPDATE parent                         UPDATE child
  giữ khóa parent                       giữ khóa child
  trigger/cascade cần child             FK/trigger cần parent
  chờ child                             chờ parent

             A chờ B  <---->  B chờ A
```

Khi deadlock graph hiển thị một câu `INSERT` đang chờ unique index hoặc một câu `DELETE` đang chờ transaction ID, đừng chỉ tìm câu `SELECT ... FOR UPDATE` trong code. Hãy lần theo tài nguyên và constraint liên quan.

### 8.1. Một ví dụ thứ tự cha-con không nhất quán

Giả sử ứng dụng có hai quy trình:

- Quy trình A cập nhật hàng cha trước, sau đó cập nhật hàng con.
- Quy trình B cập nhật hàng con trước; việc kiểm tra FK hoặc trigger cần truy cập hàng cha.

Nếu hai quy trình chạy đồng thời và giữ khóa ở hai phía, chúng có thể tạo vòng chờ. Cách khắc phục là thiết kế thứ tự truy cập nhất quán cho toàn bộ quan hệ, bao gồm các thao tác phụ do FK và trigger tạo ra.

Không có một thứ tự “cha trước” hoặc “con trước” đúng cho mọi hệ thống. Thứ tự phải dựa trên lock behavior của DBMS, trigger và cascade cụ thể. Điều quan trọng là mọi đường code liên quan phải tuân theo cùng quy ước.

## 9. DDL và metadata lock cũng có thể chặn giao dịch

Không chỉ DML mới tạo chờ khóa. Các thao tác thay đổi schema như `ALTER TABLE`, tạo/xóa index, thay constraint hoặc đổi cấu trúc có thể yêu cầu khóa metadata/schema mạnh hơn.

Ví dụ, một migration thêm constraint hoặc thay index có thể phải chờ transaction đang sử dụng bảng. Ngược lại, DDL có thể làm các request mới chờ metadata lock. Trên MySQL, metadata lock là nguyên nhân thường gặp khi một DDL bị chặn bởi transaction chưa commit. SQL Server có schema stability/schema modification locks; PostgreSQL và Oracle cũng có khóa relation/DDL riêng.

Khi một request chờ lâu mà không thấy row lock rõ ràng, hãy kiểm tra:

- Có migration hoặc DDL đang chạy không?
- Session có đang chờ metadata/schema lock không?
- Transaction cũ có giữ metadata lock do đã truy cập bảng nhưng chưa kết thúc không?
- DDL có đang chờ một transaction idle in transaction không?

Không xử lý mọi lock wait như row lock. Xác định loại tài nguyên trước khi quyết định hủy session hoặc thay đổi timeout.

## 10. Lock footprint phụ thuộc execution plan và dữ liệu

Một câu truy vấn có thể có lock footprint khác nhau sau khi statistics thay đổi hoặc index được thêm/xóa. Ví dụ:

```sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE customer_id = :customer_id
  AND created_at < :cutoff;
```

Nếu có index phù hợp trên `(customer_id, created_at)`, engine có thể tìm một phạm vi nhỏ. Nếu không có, engine có thể quét nhiều hàng hơn. Ở các engine dùng range/gap locking, phạm vi khóa còn phụ thuộc isolation level và index access path.

Các yếu tố cần ghi nhận:

- Execution plan và index được chọn.
- Rows estimated so với rows actual.
- Số hàng đọc, số hàng cập nhật và số hàng bị lọc bỏ.
- Predicate và phạm vi khóa trong isolation level đang dùng.
- Lock escalation hoặc lock coarsening nếu DBMS hỗ trợ.
- Trigger và constraint được kích hoạt bởi số hàng thực tế.

Một thay đổi statistics có thể khiến optimizer đổi từ index seek sang scan. Khi đó, câu SQL không đổi nhưng số tài nguyên truy cập và thời gian giữ khóa có thể thay đổi. Sau deploy schema hoặc thay đổi dữ liệu lớn, hãy quan sát lại lock wait và deadlock.

## 11. Khác biệt giữa các hệ quản trị

Không thể suy ra cùng một loại khóa vật lý cho PostgreSQL, MySQL InnoDB, SQL Server và Oracle:

| DBMS | Những điểm cần chú ý |
|---|---|
| PostgreSQL | Row locks được ghi nhận theo tuple/transaction; FK kiểm tra tham chiếu có thể lấy khóa trên hàng cha. SSI dùng `SIReadLock` để theo dõi predicate; đây không phải khóa chặn thông thường. Trigger có thể chạy SQL trong cùng transaction. |
| MySQL InnoDB | Khóa record, gap và next-key phụ thuộc index access path và isolation level. Unique/FK checks và cascade có thể tạo thêm khóa. Metadata lock có thể giữ đến cuối transaction. |
| SQL Server | Key, page, row và range locks có thể xuất hiện; lock escalation có thể thay đổi phạm vi. FK, trigger và index maintenance tham gia cùng transaction. Schema locks ảnh hưởng DDL. |
| Oracle | Row-level TX locks và TM table locks phối hợp thao tác DML/constraint; index maintenance và trigger có thể mở rộng công việc. Deadlock graph/trace giúp lần theo tài nguyên phụ thuộc. |

Đây là mô tả định hướng, không phải bảng ánh xạ một-một. Hãy dùng tài liệu và công cụ chẩn đoán của đúng phiên bản. Cùng một constraint hoặc truy vấn có thể tạo lock footprint khác khi index, isolation level hoặc execution plan thay đổi.

## 12. Cách tìm nguồn khóa ẩn khi điều tra

Khi gặp deadlock hoặc lock wait, thực hiện theo trình tự:

1. Thu thập deadlock graph hoặc wait graph đầy đủ, gồm session, câu lệnh, resource, mode và owner/waiter.
2. Xác định bảng/index/key/page/transaction/metadata resource mà session đang giữ hoặc chờ.
3. Đối chiếu SQL thực thi, không chỉ method repository hoặc câu SQL đầu tiên.
4. Kiểm tra index và constraint trên các bảng liên quan.
5. Đọc định nghĩa trigger, cascade, stored procedure và ORM-generated SQL.
6. Xem execution plan để hiểu đường truy cập và số hàng thực tế.
7. Dựng lại thứ tự tài nguyên mà mỗi transaction lấy, bao gồm khóa ngầm.
8. Tìm vòng chờ và xác định một thứ tự toàn cục có thể áp dụng.
9. Kiểm thử lại bằng hai hoặc nhiều session trên DBMS thực tế.

### 12.1. PostgreSQL

Kết hợp `pg_stat_activity`, `pg_blocking_pids()` và `pg_locks`:

```sql
SELECT a.pid,
       a.application_name,
       a.state,
       a.wait_event_type,
       a.wait_event,
       pg_blocking_pids(a.pid) AS blockers,
       a.xact_start,
       left(a.query, 1000) AS query_text
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.pid <> pg_backend_pid();
```

```sql
SELECT locktype,
       relation::regclass AS relation,
       page,
       tuple,
       transactionid,
       classid,
       objid,
       mode,
       granted,
       pid
FROM pg_locks
ORDER BY granted, pid;
```

Row lock thường được lưu trong tuple; session chờ row lock có thể chờ transaction ID của session giữ hàng. Advisory lock và relation lock cũng xuất hiện trong `pg_locks`. Deadlock details được ghi trong server log nếu logging được cấu hình phù hợp.

### 12.2. MySQL InnoDB

Trên MySQL 8, `performance_schema.data_locks` và `data_lock_waits` giúp xem record/index lock và quan hệ chờ. `SHOW ENGINE INNODB STATUS` cung cấp deadlock gần nhất, gồm transaction, index và record liên quan. `performance_schema.metadata_locks` giúp điều tra metadata lock.

Khi đọc deadlock report, chú ý tên index, lock mode và record/key được mô tả. Một câu lệnh insert/update có thể đang chờ một unique index hoặc foreign key check, dù code không có câu `SELECT FOR UPDATE`.

### 12.3. SQL Server

Dùng Extended Events với `xml_deadlock_report` để thu deadlock graph. Kết hợp `sys.dm_tran_locks`, `sys.dm_os_waiting_tasks`, `sys.dm_exec_requests` và execution plan để xác định key/page/object và câu lệnh liên quan. Trigger và constraint cần được kiểm tra trong schema, không chỉ trong query text.

### 12.4. Oracle

Đọc deadlock trace trong ADR để xem graph và tài nguyên liên quan. `V$LOCK`, `V$SESSION`, `DBA_BLOCKERS` và `DBA_WAITERS` hỗ trợ xác định session và loại khóa. Nếu tài nguyên là index hoặc bảng phụ, truy ngược trigger/constraint để tìm câu SQL đã chạm đến nó.

## 13. Thiết kế thứ tự khóa có tính đến thao tác ngầm

Một quy tắc lock ordering chỉ hữu ích khi bao gồm cả các tài nguyên mà database truy cập tự động. Ví dụ, quy trình cập nhật một đơn hàng có thể cần:

```text
1. Hàng account/customer
2. Hàng order
3. Hàng inventory theo product_id tăng dần
4. Hàng reservation
5. Hàng audit/outbox
```

Nếu trigger hoặc cascade ghi audit trước khi code cập nhật inventory, thứ tự thực tế có thể khác. Cần hiểu đúng thứ tự câu lệnh được thực thi và tài nguyên engine yêu cầu.

Các nguyên tắc:

- Lập sơ đồ bảng và constraint mà mỗi transaction chạm đến.
- Liệt kê trigger và thủ tục phụ được kích hoạt.
- Xác định các index/unique key có thể bị tranh chấp.
- Chọn thứ tự truy cập ổn định giữa mọi đường nghiệp vụ liên quan.
- Với nhiều hàng cùng loại, sắp xếp theo khóa định danh ổn định trước khi cập nhật.
- Không giả định `ORDER BY` luôn là cam kết thứ tự khóa vật lý trên mọi DBMS.
- Kiểm tra lại bằng deadlock graph sau khi thay đổi.

Nếu không thể kiểm soát thứ tự khóa do trigger phức tạp, cân nhắc gom logic vào một procedure/repository có thứ tự thống nhất, đơn giản hóa trigger hoặc thay đổi mô hình dữ liệu. Đừng thêm khóa tường minh ở mọi nơi mà chưa xác định tài nguyên nào thực sự cần bảo vệ.

## 14. Giảm rủi ro từ trigger và cascade

Trigger và cascade có thể cần thiết để bảo vệ audit hoặc quan hệ dữ liệu, nhưng nên được giữ đơn giản và có phạm vi rõ:

- Tránh trigger thực hiện truy vấn N+1 cho từng hàng nếu có thể dùng xử lý theo tập.
- Tránh trigger cập nhật ngược bảng nguồn hoặc tạo chuỗi trigger khó theo dõi.
- Giữ thứ tự truy cập bảng nhất quán giữa trigger của các bảng khác nhau.
- Không gọi dịch vụ mạng hoặc chờ tác vụ bên ngoài trong trigger.
- Đánh giá số hàng cascade và thời gian giữ khóa khi xóa/cập nhật hàng cha.
- Tạo index phía con để tìm hàng tham chiếu hiệu quả khi phù hợp.
- Ghi nhận lỗi trigger/constraint riêng để phân biệt với lỗi ở câu SQL gọi nó.

Nếu audit cần phát sự kiện ra hệ thống khác, cân nhắc transactional outbox: trigger hoặc transaction ghi bản ghi outbox trong cùng database transaction, worker gửi sự kiện sau commit. Không giữ transaction và khóa database trong lúc chờ HTTP hoặc message broker.

## 15. Không tắt constraint để né contention

Khi FK hoặc unique constraint làm một insert phải chờ, tắt constraint có thể khiến benchmark nhanh hơn nhưng phá tính toàn vẹn dữ liệu. Tương tự, xóa trigger audit để giảm lock wait có thể làm mất lịch sử cần thiết.

Trước khi thay đổi constraint/trigger, hãy xác định:

- Constraint đang bảo vệ invariant nào?
- Có thể thay bằng một cơ chế tương đương được database thực thi không?
- Nếu tạm hoãn kiểm tra, có bảo đảm dữ liệu hợp lệ trước commit không?
- Có thể tối ưu index hoặc thứ tự transaction thay vì bỏ constraint không?
- Trigger có thể được chuyển sang xử lý set-based hoặc outbox mà vẫn giữ semantics không?

Chỉ thay đổi constraint/trigger khi thiết kế mới bảo đảm cùng yêu cầu dữ liệu và đã có kiểm thử. Không xem việc bỏ khóa ngầm là một tối ưu hiệu năng nếu nó làm thay đổi tính đúng đắn.

## 16. Kiểm thử lock footprint thực tế

Một bài kiểm thử tốt cần chạy trên DBMS và schema thật, với nhiều connection. Ví dụ kiểm tra FK/trigger:

1. Tạo hàng cha và hàng con, bật đầy đủ FK, index và trigger như production.
2. Session A bắt đầu transaction, cập nhật hàng con và giữ transaction mở.
3. Session B xóa hoặc đổi khóa hàng cha, quan sát chờ khóa và kết quả constraint.
4. Thu lock wait/deadlock graph và xác định tài nguyên phụ.
5. Lặp lại với trigger audit bật/tắt trong database thử nghiệm để hiểu phần lock footprint do trigger tạo; không dùng kết quả khi tắt trigger làm chuẩn correctness.
6. Lặp lại với index phía con có/không có trong môi trường thử nghiệm để đo tác động scan và thời gian giữ khóa.
7. Rollback hoặc reset dữ liệu giữa các lượt, rồi xác nhận FK và invariant vẫn hợp lệ.

Một bài kiểm thử unique race:

1. Hai session cùng insert một unique key.
2. Giữ transaction đầu chưa commit.
3. Cho session thứ hai insert cùng key.
4. Quan sát session thứ hai chờ hoặc nhận lỗi sau khi transaction đầu commit/rollback.
5. Xác nhận chỉ có tối đa một hàng cho key đó.

Một bài kiểm thử trigger deadlock:

1. Tạo hai bảng X và Y với trigger cập nhật chéo.
2. Transaction A cập nhật X; transaction B cập nhật Y.
3. Điều phối để A cần Y và B cần X.
4. Thu deadlock graph và kiểm tra câu SQL bên trong trigger.
5. Thay đổi thứ tự truy cập hoặc thiết kế trigger rồi chạy lại.

Không dùng `sleep()` làm bằng chứng transaction đã lấy khóa. Dùng barrier/latch trong test harness và chỉ mở bước tiếp theo sau khi câu SQL lấy khóa đầu tiên hoàn tất.

## 17. Checklist khi review một transaction

- [ ] Đã xem execution plan và index được dùng, không chỉ đọc câu SQL.
- [ ] Đã liệt kê primary key, secondary index và unique constraint bị ảnh hưởng.
- [ ] Đã xác định FK được kiểm tra khi insert/update con và delete/update cha.
- [ ] Đã kiểm tra index phía con và hành động cascade.
- [ ] Đã đọc trigger, stored procedure và các câu SQL phụ.
- [ ] Đã kiểm tra ORM flush/cascade và SQL thực tế được sinh ra.
- [ ] Đã xem xét metadata/schema lock nếu có DDL.
- [ ] Đã dựng thứ tự lấy khóa bao gồm tài nguyên ngầm.
- [ ] Đã kiểm tra lock wait/deadlock graph trên DBMS thực tế.
- [ ] Đã phân biệt lock wait, deadlock, serialization failure và constraint violation.
- [ ] Đã giữ constraint và trigger cần thiết để bảo vệ invariant.
- [ ] Đã kiểm thử concurrency với dữ liệu và số lượng hàng đại diện.
- [ ] Đã thiết kế retry toàn transaction khi lỗi cạnh tranh có thể retry.

## 18. Cách đọc một deadlock graph khi có khóa ngầm

Khi xem graph, đừng dừng ở tên câu SQL. Hãy đọc theo từng cạnh:

1. Process nào là owner của resource?
2. Process nào đang chờ resource đó?
3. Resource là row/key/page/table/transaction ID/metadata hay application lock?
4. Index hoặc constraint nào liên quan đến resource?
5. Câu lệnh nào đã tạo ra thao tác kiểm tra hoặc cập nhật phụ?
6. Trigger, cascade hoặc procedure nào được kích hoạt?
7. Transaction đã giữ tài nguyên nào trước đó?
8. Có thể chuẩn hóa thứ tự lấy toàn bộ tài nguyên hay giảm số bước giữ khóa không?

Một deadlock graph có thể cho thấy transaction A đang chờ khóa trên index unique trong khi transaction B chờ một hàng cha. Đây là dấu hiệu cần xem xét luồng insert/update và FK/trigger, không chỉ thêm `FOR UPDATE` vào câu SQL đang chờ. Thêm khóa mạnh hơn mà không hiểu graph có thể làm phạm vi chờ lớn hơn.

## 19. Quy trình điều tra và sửa lỗi

1. Tái hiện lỗi với workload có kiểm soát trên database thử nghiệm.
2. Thu deadlock graph, lock wait, SQL text và transaction age.
3. Đối chiếu tài nguyên trong graph với index, FK, unique constraint, trigger và cascade.
4. Mở execution plan và schema để hiểu đường truy cập.
5. Vẽ thứ tự tài nguyên mỗi transaction đã lấy và đang chờ.
6. Chọn thay đổi nhỏ nhất có thể: index phù hợp, thứ tự truy cập ổn định, trigger set-based, batch hợp lý hoặc cập nhật nguyên tử.
7. Giữ nguyên constraint bảo vệ invariant; nếu thay đổi semantics, phải thiết kế bảo đảm tương đương.
8. Chạy lại test concurrency với nhiều session và xác nhận cả hiệu năng lẫn dữ liệu.
9. Triển khai quan sát deadlock/lock wait sau thay đổi để kiểm tra nguyên nhân đã được xử lý.

## 20. Kết luận thực hành

Index, constraint, trigger, cascade, ORM và DDL đều có thể làm database truy cập thêm tài nguyên ngoài những hàng xuất hiện trong câu SQL ở tầng ứng dụng. Chúng có thể tạo khóa ngầm, kéo dài transaction hoặc thêm cạnh chờ vào deadlock graph. Vì vậy, review concurrency phải dựa trên SQL thực tế, schema, execution plan và hành vi của DBMS.

Khi điều tra, hãy lần theo resource trong lock graph đến index, constraint hoặc trigger đã tạo ra nó. Khi thiết kế, đưa các thao tác phụ thuộc vào cùng quy tắc thứ tự khóa, giữ transaction ngắn, tối ưu đường truy cập và giữ nguyên các constraint bảo vệ dữ liệu. Đừng coi một câu SQL ngắn là một transaction chỉ chạm vào một hàng; hãy tính cả công việc database thực hiện để bảo đảm tính toàn vẹn.
