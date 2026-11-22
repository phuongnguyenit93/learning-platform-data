# Phân biệt DELETE, TRUNCATE, DROP và PURGE trong Oracle Database

Khi cần dọn dữ liệu Oracle, bốn từ khóa **`DELETE`, `TRUNCATE`, `DROP` và `PURGE`** thường được nhắc cùng nhau vì đều có khả năng làm dữ liệu biến mất khỏi các truy vấn thường ngày. Tuy nhiên, chúng tác động đến **những cấp độ khác nhau**: dòng dữ liệu, nội dung toàn bảng, định nghĩa đối tượng và thùng rác của database. Chọn nhầm lệnh có thể khiến mất dữ liệu không thể `ROLLBACK`, vô tình commit một giao dịch khác, làm hỏng đối tượng phụ thuộc hoặc xóa luôn cơ hội khôi phục từ recycle bin.

Trong bối cảnh chương **Bảng và ràng buộc** của Oracle, điều cần học không chỉ là cú pháp mà còn là **transaction**, **constraint**, **trigger**, **redo/undo**, **tablespace và storage**, cùng khả năng khôi phục sau thao tác. Bài này trình bày từng lệnh, so sánh chúng bằng tình huống và thực hành an toàn trên bảng có tiền tố `LAB_`.

> **Cảnh báo phạm vi:** Những câu lệnh `TRUNCATE`, `DROP` và `PURGE` trong bài chỉ nên thử trên **bảng lab do bạn kiểm soát**. Chúng có thể có hậu quả không thể khôi phục bằng `ROLLBACK`. Không chạy với bảng chứa dữ liệu quan trọng hoặc môi trường production chỉ để quan sát kết quả.

## 1. Nhìn nhanh: bốn lệnh làm gì?

| Lệnh | Cấp độ tác động | Phân loại | Có `WHERE`? | `ROLLBACK` thông thường? | Bảng còn tồn tại? |
|---|---|---|---|---|---|
| **`DELETE`** | Các **dòng** thỏa điều kiện, hoặc toàn bộ dòng nếu không có điều kiện | **DML** | **Có** | **Có, nếu transaction chưa commit** | **Có** |
| **`TRUNCATE TABLE`** | **Tất cả dòng** của một bảng (hoặc thao tác tương ứng với phân vùng theo cú pháp riêng) | **DDL** | **Không** | **Không** | **Có**, cấu trúc còn |
| **`DROP TABLE`** | **Đối tượng bảng** và các thành phần thuộc phạm vi drop | **DDL** | **Không** | **Không** | **Không** trong namespace sử dụng bình thường |
| **`PURGE`** | **Đối tượng đã bị DROP trong recycle bin**, hoặc bỏ qua recycle bin khi kết hợp `DROP ... PURGE` | Lệnh quản lý recycle bin/DDL | **Không** | **Không** | Đối tượng đã drop không còn khả năng `FLASHBACK ... TO BEFORE DROP` qua recycle bin |

Ví dụ ngắn:

~~~sql
DELETE FROM lab_orders
WHERE order_status = 'CANCELLED';

TRUNCATE TABLE lab_orders;

DROP TABLE lab_orders;

DROP TABLE lab_orders PURGE;
~~~

Đây là **các lựa chọn độc lập**, không phải bốn câu nên chạy liên tiếp trên một bảng. Sau `DROP TABLE`, tên bảng đó không còn truy vấn như trước; sau `DROP ... PURGE`, đối tượng không được đưa vào recycle bin để phục hồi bằng `FLASHBACK TABLE ... TO BEFORE DROP`.

Một cách ghi nhớ:

~~~text
DELETE   ── xóa DÒNG có lựa chọn (hoặc tất cả dòng)
                │   giữ table/schema object
                │   có transaction và ROLLBACK khi chưa COMMIT
                ▼
TRUNCATE ── làm TRỐNG toàn bảng
                │   giữ định nghĩa table
                │   DDL, implicit COMMIT, không ROLLBACK
                ▼
DROP     ── loại bỏ ĐỐI TƯỢNG bảng khỏi schema đang dùng
                │   có thể đưa object vào recycle bin
                ▼
PURGE    ── xóa khả năng phục hồi object từ RECYCLE BIN
                    không phải lệnh xóa từng dòng còn sống
~~~

## 2. Phân biệt DML và DDL trước khi thao tác

**DML (Data Manipulation Language)** thao tác với dữ liệu trong bảng: `INSERT`, `UPDATE`, `DELETE`, `MERGE`. Một thay đổi DML diễn ra trong **transaction**; người dùng có thể `COMMIT` để xác nhận hoặc `ROLLBACK` để hủy các thay đổi chưa commit.

**DDL (Data Definition Language)** thay đổi định nghĩa/cấu trúc đối tượng và cách database quản lý chúng: `CREATE`, `ALTER`, `TRUNCATE`, `DROP`, v.v. Trong Oracle, DDL thông thường thực hiện **implicit commit** trước khi thực thi, và commit kết quả DDL nếu thành công. Vì vậy không thể coi `TRUNCATE` hay `DROP` là một bước của transaction DML có thể rollback.

Một tình huống dễ gây mất dữ liệu ngoài ý muốn:

~~~sql
UPDATE lab_customer
SET display_name = 'Ten moi'
WHERE customer_id = 10;

-- Chưa COMMIT bằng tay.
TRUNCATE TABLE lab_temp_data;

ROLLBACK;
~~~

Người mới có thể nghĩ `ROLLBACK` sẽ trả `LAB_CUSTOMER` về tên cũ và khôi phục dữ liệu `LAB_TEMP_DATA`. **Không đúng**: `TRUNCATE` là DDL, Oracle implicit commit giao dịch đang chờ **trước** khi chạy DDL. Vì vậy thay đổi `LAB_CUSTOMER` có thể đã được commit; dữ liệu bị truncate cũng không trở lại qua rollback. Thậm chí khi DDL sau đó thất bại, giao dịch DML trước đó vẫn có thể đã bị commit bởi bước implicit commit ban đầu.

**Thói quen an toàn:** Hoàn tất hoặc rollback các transaction DML quan trọng **trước khi** thực hiện DDL. Dùng connection quản trị chuyên biệt cho thao tác schema khi thích hợp; không gộp DDL “dọn dẹp” vào luồng transaction nghiệp vụ Java rồi kỳ vọng rollback bảo vệ được mọi thứ.

## 3. DELETE: xóa dòng có điều kiện và vẫn thuộc transaction

`DELETE` là lựa chọn khi cần xóa **một phần dữ liệu** hoặc khi logic xóa phải tuân theo các ràng buộc/giao dịch thông thường.

### 3.1. Xóa theo điều kiện

~~~sql
DELETE FROM lab_orders
WHERE order_status = 'CANCELLED'
  AND created_at < DATE '2025-01-01';
~~~

Oracle xóa các dòng thỏa predicate. Nếu không có `WHERE`:

~~~sql
DELETE FROM lab_orders;
~~~

Lệnh này cố gắng xóa **mọi dòng**, nhưng vẫn là DML: Oracle vẫn cần thực thi theo ngữ nghĩa xóa dòng, phát sinh undo/redo phù hợp và kiểm tra constraint/trigger theo quy tắc. Nó **không giống** `TRUNCATE TABLE` dù sau khi thành công, truy vấn `COUNT(*)` có thể đều cho kết quả 0.

### 3.2. DELETE có thể rollback

~~~sql
DELETE FROM lab_orders
WHERE order_id = 101;

-- Kiểm tra số dòng trước khi quyết định.
SELECT COUNT(*)
FROM lab_orders
WHERE order_id = 101;

ROLLBACK;
~~~

Nếu lệnh `DELETE` và `ROLLBACK` cùng nằm trong một transaction chưa commit, dòng đã xóa có thể trở lại. Nhưng cần nhớ:

- Nếu đã `COMMIT` hoặc client được cấu hình **auto-commit**, `ROLLBACK` sau đó không khôi phục thay đổi đã xác nhận.
- Nếu có một lệnh DDL xen giữa, implicit commit có thể kết thúc transaction trước khi bạn gọi `ROLLBACK`.
- Nếu bạn thực hiện nhiều DML trong cùng transaction, `ROLLBACK` toàn bộ sẽ hủy **tất cả thay đổi chưa commit** từ đầu transaction (trừ trường hợp dùng savepoint phù hợp), không chỉ riêng lần xóa gần nhất.

Với câu lệnh cần thao tác an toàn theo từng bước, có thể đặt savepoint:

~~~sql
SAVEPOINT before_cleanup;

DELETE FROM lab_orders
WHERE order_status = 'CANCELLED';

-- Nếu kiểm tra thấy chưa đúng:
ROLLBACK TO before_cleanup;
~~~

Savepoint áp dụng cho transaction DML; **không thể đặt savepoint rồi dùng để khôi phục TRUNCATE/DROP**.

### 3.3. DELETE có trigger và ràng buộc

Oracle hỗ trợ DML trigger theo sự kiện `DELETE`, ví dụ:

- **Statement-level trigger** cho một câu lệnh DELETE.
- **Row-level trigger** với `FOR EACH ROW`, chạy theo các dòng chịu tác động.

Ví dụ ý tưởng:

~~~sql
CREATE TABLE lab_delete_audit (
  audit_id    NUMBER GENERATED ALWAYS AS IDENTITY,
  deleted_id  NUMBER NOT NULL,
  deleted_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT pk_lab_delete_audit PRIMARY KEY (audit_id)
);

CREATE OR REPLACE TRIGGER trg_lab_orders_delete
AFTER DELETE ON lab_orders
FOR EACH ROW
BEGIN
  INSERT INTO lab_delete_audit(deleted_id)
  VALUES (:OLD.order_id);
END;
/
~~~

Đây là trigger minh họa; bảng `LAB_ORDERS` và cột `ORDER_ID` phải tồn tại, quyền tạo trigger phải phù hợp. Nếu transaction bị `ROLLBACK`, các bản ghi audit DML thông thường do trigger ghi **trong cùng transaction** cũng được rollback (trừ khi triển khai cơ chế autonomous transaction riêng, vốn có ngữ nghĩa khác). Trigger này **không được gọi bởi `TRUNCATE TABLE`** vì truncate không phải xóa từng dòng bằng DML.

Một statement-level trigger `DELETE` có thể chạy ngay cả khi câu DELETE không tác động dòng nào; còn row-level trigger chỉ chạy cho các dòng thực sự bị ảnh hưởng. Không xây dựng logic nghiệp vụ giả định mọi lệnh làm trống bảng đều kích hoạt trigger DELETE.

### 3.4. DELETE và foreign key

Giả sử:

~~~text
LAB_PARENT
   ID (PK)
      |
      | 1
      | N
      v
LAB_CHILD
   PARENT_ID (FK)
~~~

Khi xóa một parent vẫn được child tham chiếu, Oracle thường ngăn xóa nếu FK đang áp dụng và không có hành vi xóa phụ thuộc phù hợp:

~~~sql
DELETE FROM lab_parent
WHERE parent_id = 1;
-- Có thể gặp ORA-02292 khi child vẫn tham chiếu parent.
~~~

Tùy DDL, foreign key có thể dùng `ON DELETE CASCADE` để xóa child khi parent bị xóa, hoặc `ON DELETE SET NULL` khi cột child nullable và nghiệp vụ cho phép. Đừng bật cascade chỉ để thuận tiện dọn dữ liệu nếu bảng con giữ lịch sử cần bảo toàn.

## 4. TRUNCATE: làm trống bảng, giữ định nghĩa, không thể rollback

`TRUNCATE TABLE` loại bỏ toàn bộ dòng của bảng mà **không sử dụng đường đi xóa từng dòng giống DELETE**. Trong Oracle, đây là **DDL**.

~~~sql
TRUNCATE TABLE lab_orders;
~~~

Điều vẫn còn sau khi truncate (ở bảng bình thường):

- **Table object và định nghĩa các cột** vẫn còn.
- **Constraints, triggers, privileges và indexes** vẫn là các đối tượng/cấu trúc tương ứng với bảng theo quy tắc Oracle; nội dung index được xử lý để phù hợp bảng trống.
- Có thể `INSERT` dữ liệu mới vào cùng bảng sau đó.

Điều không còn là **các dòng dữ liệu của bảng tại thời điểm truncate**. Không có `WHERE` để chỉ truncate đơn đã hủy hay đơn trước một ngày; muốn xóa có lựa chọn phải dùng `DELETE` hoặc thiết kế partition/maintenance phù hợp.

### 4.1. Vì sao TRUNCATE thường nhanh hơn DELETE toàn bảng?

`DELETE FROM table` xử lý tác động tới các dòng và cần đủ undo để rollback, ghi redo và duy trì cơ chế ràng buộc/trigger theo DML. Với bảng rất lớn, công việc này có thể đắt đỏ.

`TRUNCATE` chủ yếu làm thay đổi metadata/segment và xử lý việc loại bỏ dữ liệu ở mức cấu trúc; nó thường dùng **ít undo hơn cho việc xóa dữ liệu** và có thể nhanh hơn nhiều khi muốn làm trống toàn bảng. Tuy nhiên:

- Không có nghĩa “không ghi redo/undo nào cả”; thao tác quản lý metadata và cấu trúc vẫn có chi phí.
- Truncate có thể phải đợi các lock/transaction khác và phải đáp ứng điều kiện constraint.
- Truncate không chạy row-level DELETE triggers.
- Truncate không hỗ trợ rollback như DELETE.

Không nên chọn TRUNCATE chỉ dựa trên tốc độ khi yêu cầu nghiệp vụ còn cần lịch sử, audit trigger hoặc khả năng hủy thao tác.

### 4.2. High Water Mark (HWM) và storage

**High Water Mark** mô tả vùng segment đã từng được sử dụng/cấp phát theo cơ chế Oracle. `DELETE` xóa dòng nhưng thường **không tự hạ HWM** của bảng; các block đã cấp phát vẫn thuộc segment và có thể tái sử dụng cho dữ liệu mới.

`TRUNCATE` thường **reset HWM** và có thể giải phóng extents tùy tùy chọn storage:

~~~sql
TRUNCATE TABLE lab_orders DROP STORAGE;

TRUNCATE TABLE lab_orders REUSE STORAGE;
~~~

| Tùy chọn | Ý nghĩa thực hành |
|---|---|
| **`DROP STORAGE`** | Oracle có thể giải phóng các extents có thể trả lại theo quy tắc quản lý segment; đây là lựa chọn mặc định thông thường cho truncate bảng |
| **`REUSE STORAGE`** | Giữ phần storage được cấp phát để lần nạp dữ liệu sau có thể tái sử dụng, hữu ích cho bảng staging thường xuyên được làm mới |

“Giải phóng extents” **không đồng nghĩa** file datafile của tablespace tự co nhỏ ở cấp hệ điều hành; kích thước datafile và cách thu hồi dung lượng vật lý là câu chuyện quản trị khác. Cũng không thể suy ra hiệu năng một câu `SELECT` chỉ bằng việc nhìn `COUNT(*)` sau truncate; còn có execution plan và tình trạng storage.

### 4.3. TRUNCATE và foreign key: đừng nhầm với DELETE CASCADE

Với một parent đang được **enabled foreign key** ở bảng khác tham chiếu, Oracle thường **không cho truncate parent** khi các điều kiện tham chiếu không được đáp ứng, kể cả trong trường hợp bạn tin rằng bảng con hiện trống. Quy tắc và ngoại lệ cụ thể phụ thuộc đối tượng và phiên bản, nhưng điều cần ghi nhớ là **TRUNCATE không thay thế DELETE và không đi qua cơ chế kiểm tra/xóa từng dòng như DELETE**.

Trong nhiều mô hình lab, cần truncate **bảng con trước bảng cha**:

~~~sql
TRUNCATE TABLE lab_child;
TRUNCATE TABLE lab_parent;
~~~

Tuy nhiên, việc bảng child đã trống **không tự loại bỏ enabled foreign key** tham chiếu parent; vì vậy câu thứ hai vẫn có thể bị Oracle từ chối. Với môi trường có FK, cần chọn giải pháp phù hợp:

- Dùng `DELETE` theo thứ tự child → parent nếu cần transaction/audit.
- Xem xét khả năng `TRUNCATE ... CASCADE` **khi phiên bản và định nghĩa foreign key cho phép**; không giả định mọi FK đều được phép cascade.
- Trong một quy trình DBA được phê duyệt, có thể có thao tác quản lý constraint/partition riêng, kèm kiểm soát và kế hoạch khôi phục. Không tự động disable toàn bộ FK trong production.

Với quan hệ đơn hàng/sản phẩm, việc truncate parent có thể gây lỗi ngay cả khi mục tiêu chỉ là “reset dữ liệu test”. Tốt nhất dùng các bảng staging/lab độc lập nếu thường xuyên cần truncate.

### 4.4. TRUNCATE CASCADE không giống DROP CASCADE CONSTRAINTS

Ở các phiên bản Oracle có hỗ trợ `TRUNCATE TABLE ... CASCADE` và điều kiện tham chiếu phù hợp (đặc biệt các quan hệ được cấu hình `ON DELETE CASCADE`), cú pháp này có thể hỗ trợ truncate dữ liệu của các bảng liên quan. Không nên áp dụng mù quáng: phạm vi tác động có thể vượt một bảng và cần xác nhận trên phiên bản/configuration đang dùng.

~~~sql
-- Chỉ là ví dụ cú pháp cho thiết kế FK và phiên bản hỗ trợ;
-- không chạy trên dữ liệu cần giữ.
TRUNCATE TABLE lab_parent CASCADE;
~~~

Ngược lại, `DROP TABLE ... CASCADE CONSTRAINTS` sẽ **xóa các referential constraints cần thiết** để bỏ bảng cha, chứ **không có nghĩa xóa toàn bộ các bảng con**. Hai loại cascade khác bản chất và phải được xem riêng ở phần DROP.

## 5. DROP: loại bỏ định nghĩa bảng khỏi schema

Khi chạy:

~~~sql
DROP TABLE lab_orders;
~~~

Oracle loại bỏ bảng khỏi namespace sử dụng thông thường. Điều này khác `TRUNCATE`:

- `TRUNCATE` giữ object bảng và schema của cột.
- `DROP` làm tên bảng không còn truy vấn như trước; `SELECT * FROM lab_orders` có thể báo `ORA-00942`.
- Đối tượng phụ thuộc (view, procedure, materialized view, trigger, constraint, index...) có thể bị xóa, invalidated hoặc ảnh hưởng theo loại đối tượng và quy tắc Oracle.
- `DROP` là **DDL**: không thể dùng `ROLLBACK` để đảo ngược như DELETE.

### 5.1. DROP và recycle bin

Khi **recycle bin** được bật và đối tượng phù hợp, `DROP TABLE` có thể đưa bảng và những thành phần liên quan vào recycle bin thay vì xóa vật lý ngay. Tên bên trong recycle bin thường là tên hệ thống dạng `BIN$...`, cho phép Oracle phân biệt nhiều lần drop cùng một tên bảng.

~~~text
Trước DROP
  LAB_ORDERS  ── table dùng bình thường
       |
       | DROP TABLE LAB_ORDERS
       v
Sau DROP khi recycle bin áp dụng
  Tên LAB_ORDERS không còn để truy vấn bình thường
       |
       v
  Recycle bin: BIN$...   ── object có khả năng flashback before drop
       |
       | PURGE / DROP ... PURGE
       v
  Không còn đường phục hồi object qua recycle bin
~~~

Việc object có được đưa vào recycle bin hay không phụ thuộc cấu hình `RECYCLEBIN`, loại đối tượng, tablespace, quyền và những trường hợp ngoại lệ. Không phải mọi `DROP` đều phục hồi được bằng recycle bin. Đặc biệt, `DROP TABLE ... PURGE` **bỏ qua recycle bin** ngay từ đầu.

### 5.2. DROP TABLE ... PURGE

~~~sql
DROP TABLE lab_orders PURGE;
~~~

Lệnh này **drop bảng và purge ngay**, không đặt bảng vào recycle bin. Đây là thao tác mạnh hơn một `DROP TABLE` thông thường trong môi trường recycle bin đang bật. Khi đó, `FLASHBACK TABLE lab_orders TO BEFORE DROP` không thể dùng dữ liệu recycle bin của lần drop này để khôi phục.

Không nên đồng nhất “không có trong recycle bin” với “không thể phục hồi bằng bất kỳ công nghệ nào”: DBA có thể còn backup RMAN, snapshot storage hoặc khả năng phục hồi khác theo cấu hình. Tuy nhiên việc đó cần quy trình riêng, quyền và điều kiện phù hợp, không phải `ROLLBACK` hay `FLASHBACK ... TO BEFORE DROP` đơn giản.

### 5.3. DROP với foreign key ở bảng khác

Nếu bảng con có FK tới bảng cha, lệnh:

~~~sql
DROP TABLE lab_parent;
~~~

có thể bị Oracle từ chối vì đang có referential constraint tham chiếu đến khóa của bảng cha. Khi chủ động **loại bỏ bảng cha**, có tùy chọn:

~~~sql
DROP TABLE lab_parent CASCADE CONSTRAINTS;
~~~

`CASCADE CONSTRAINTS` cho phép Oracle **drop các foreign key constraints** phụ thuộc cần thiết ở bảng khác. Nó **không đồng nghĩa `DROP TABLE lab_child`**, và không tự xóa dữ liệu bảng child. Sau thao tác đó, bảng child có thể vẫn tồn tại nhưng đã mất ràng buộc tham chiếu tới parent; cần hiểu rõ hậu quả về integrity.

Nếu không muốn mất quan hệ, hãy **không** dùng cascade theo thói quen. Xem lại mục tiêu: đang muốn xóa dữ liệu thử nghiệm, làm trống bảng, hay thật sự bỏ một entity/schema khỏi mô hình?

### 5.4. DROP và các đối tượng phụ thuộc khác

Một bảng là đầu vào của nhiều thành phần:

~~~text
TABLE
 ├── PRIMARY KEY / UNIQUE / CHECK / FOREIGN KEY trong bảng
 ├── INDEXES / TRIGGERS
 ├── VIEWS và PL/SQL có tham chiếu
 ├── SYNONYMS
 └── Ứng dụng JDBC / JPA / báo cáo / ETL
~~~

Khi drop bảng, một số cấu trúc gắn trực tiếp với bảng cũng bị drop/đưa vào recycle bin tùy loại; một số view, PL/SQL hoặc consumer **không tự bị xóa** nhưng có thể không còn hợp lệ và sẽ lỗi khi chạy. Một synonym tham chiếu tên bảng không phải hợp đồng bảo đảm bảng đó tồn tại. Sau `DROP`, muốn tạo lại schema cần DDL, constraints, grants, indexes, comments, dữ liệu và các phụ thuộc theo quy trình phù hợp; không chỉ chạy `CREATE TABLE` qua loa.

## 6. PURGE: dọn recycle bin, không phải DELETE hàng

**PURGE** liên quan đến **những object đã bị drop** và đang ở recycle bin, hoặc chế độ drop bỏ qua thùng rác. Nó không phải lệnh “purge những dòng có status CANCELLED” trong một bảng còn sống.

Các dạng thường gặp:

~~~sql
-- Drop và bỏ qua recycle bin cùng lúc:
DROP TABLE lab_old_data PURGE;

-- Xem các đối tượng trong recycle bin của user hiện tại:
SELECT object_name, original_name, type, droptime
FROM user_recyclebin
ORDER BY droptime DESC;

-- Purge một bảng đã drop theo tên BIN$ chính xác từ dictionary:
PURGE TABLE "BIN$...$...";

-- Purge tất cả object thuộc recycle bin của user hiện tại:
PURGE RECYCLEBIN;
~~~

Chuỗi `"BIN$...$..."` ở trên chỉ là **placeholder minh họa**, không chạy nguyên văn. Tên object trong recycle bin có thể chứa ký tự đặc biệt, nên thường cần dấu nháy kép khi dùng câu `PURGE TABLE` với tên `BIN$...`. Hãy truy vấn `USER_RECYCLEBIN`, lấy **đúng `OBJECT_NAME`**, rồi chỉ purge đối tượng đã xác nhận không cần.

### 6.1. Sự khác biệt giữa PURGE TABLE và PURGE RECYCLEBIN

| Câu lệnh | Phạm vi |
|---|---|
| `PURGE TABLE "BIN$..."` | Nhắm tới một đối tượng bảng trong recycle bin theo tên phù hợp |
| `PURGE RECYCLEBIN` | Xóa các đối tượng thuộc recycle bin của **user hiện tại** trong phạm vi theo quy tắc Oracle |
| `PURGE DBA_RECYCLEBIN` | Thao tác quản trị phạm vi rộng hơn, cần quyền tương ứng |
| `DROP TABLE x PURGE` | Drop bảng `x` và không đưa object vào recycle bin |

**Rủi ro:** `PURGE RECYCLEBIN` có thể ảnh hưởng **nhiều bảng đã drop khác**, không chỉ bảng bạn vừa thử. Đừng dùng nó để “dọn sạch cho nhanh” trên schema dùng chung. Trong lab, hãy thử purge **một bảng BIN$ cụ thể** sau khi đọc danh sách và nhận diện chính xác.

### 6.2. PURGE có làm co datafile không?

Purge có thể giải phóng không gian của segment từng thuộc recycle bin để Oracle quản lý/tái sử dụng trong tablespace. Tuy nhiên, **điều đó không có nghĩa datafile ở filesystem tự giảm kích thước**. Datafile/tablespace growth, HWM, reclaim storage và backup retention là các lớp quản lý khác.

### 6.3. PURGE và khả năng khôi phục

Sau khi object đã bị purge khỏi recycle bin, không thể chỉ dùng `FLASHBACK TABLE ... TO BEFORE DROP` để đưa object đó trở lại. Khôi phục có thể còn phụ thuộc backup và công nghệ phục hồi khác, nhưng đó là quy trình khôi phục đầy đủ cần DBA, không phải nút Undo tức thì.

## 7. Phục hồi dữ liệu: DELETE khác DROP thế nào?

Một số công cụ phục hồi được thiết kế cho **các sự cố khác nhau**:

| Trường hợp | Cách xử lý khả dĩ | Điều kiện quan trọng |
|---|---|---|
| `DELETE` vừa chạy, chưa commit | `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` | Phải còn trong transaction chưa commit |
| `DELETE` đã commit | Flashback Query/Table hoặc restore từ backup tùy cấu hình, đôi khi dùng `INSERT ... SELECT AS OF` | Phụ thuộc undo còn đủ, quyền, row movement/quy trình, thời điểm cần phục hồi |
| `TRUNCATE` đã chạy | Khôi phục từ backup/restore theo quy trình Oracle | Không thể `ROLLBACK` thông thường; recycle bin không giữ các dòng đã truncate |
| `DROP TABLE` khi recycle bin áp dụng | `FLASHBACK TABLE ... TO BEFORE DROP` | Object còn trong recycle bin và điều kiện phục hồi được đáp ứng |
| `DROP TABLE ... PURGE` hoặc đã `PURGE` object | Backup/RMAN/khả năng khôi phục khác nếu có | Không còn đường `TO BEFORE DROP` từ recycle bin |

### 7.1. FLASHBACK TABLE ... TO BEFORE DROP

Nếu bảng đã được đưa vào recycle bin và chưa bị purge, có thể thử:

~~~sql
FLASHBACK TABLE lab_orders TO BEFORE DROP;
~~~

Nếu tên `LAB_ORDERS` đã được tái sử dụng bởi một bảng mới, thao tác phục hồi cần xử lý xung đột tên; Oracle hỗ trợ cú pháp `RENAME TO` khi flashback trước drop trong các điều kiện phù hợp:

~~~sql
FLASHBACK TABLE lab_orders
  TO BEFORE DROP RENAME TO lab_orders_restored;
~~~

**Flashback before drop không phải undo toàn bộ môi trường**. Những object liên quan như foreign key từ bảng khác, một số quyền, dependencies hoặc tên đối tượng có thể không trở lại đúng như trước và cần kiểm tra sau phục hồi. Phải xem trạng thái catalog và đối chiếu với DDL/migration.

### 7.2. Flashback Query sau DELETE

Khi một `DELETE` đã commit, Oracle có thể cho phép truy vấn trạng thái dữ liệu trước một thời điểm bằng **Flashback Query**, nếu dữ liệu undo cần thiết vẫn còn và user có quyền:

~~~sql
-- Minh họa: truy vấn phiên bản bảng ở thời điểm trước,
-- với điều kiện timestamp còn trong khả năng Flashback Query.
SELECT *
FROM lab_orders AS OF TIMESTAMP
  (SYSTIMESTAMP - INTERVAL '10' MINUTE);
~~~

Mục đích đầu tiên thường là **điều tra** phiên bản dữ liệu trước khi quyết định khôi phục. Đây không phải cam kết Oracle luôn giữ đủ undo 10 phút hoặc lâu hơn trong mọi workload. Nếu cần khôi phục một tập dòng, phải thiết kế thao tác insert/merge có kiểm soát khóa chính, FK, transaction, và thay đổi phát sinh sau đó. **Không** sử dụng Flashback Query như một phương pháp thay thế backup dài hạn.

### 7.3. TRUNCATE không đưa dữ liệu vào recycle bin

Một điểm đặc biệt dễ nhầm: **recycle bin lưu object đã bị drop**, không phải các phiên bản dòng do truncate xóa. Do đó, sau `TRUNCATE TABLE`, `FLASHBACK TABLE ... TO BEFORE DROP` không áp dụng vì bảng **không hề bị drop**. Khôi phục trạng thái trước truncate đòi hỏi công cụ/phương án phục hồi khác đã được chuẩn bị, thường dựa vào backup.

## 8. Bảng so sánh chi tiết theo hành vi Oracle

| Câu hỏi | DELETE | TRUNCATE | DROP | PURGE |
|---|---|---|---|---|
| Mục tiêu | Dòng dữ liệu | Toàn bộ nội dung bảng | Object bảng | Object trong recycle bin |
| Là DML hay DDL? | DML | DDL | DDL | Quản lý recycle bin/DDL |
| Có điều kiện `WHERE`? | Có | Không | Không | Không |
| Có thể xóa một vài dòng? | Có | Không | Không | Không |
| Có thể rollback thường? | Có, trước commit | Không | Không | Không |
| Implicit commit? | Không do chính DELETE | Có | Có | Có theo ngữ nghĩa thao tác DDL |
| DELETE row trigger? | Có cho các dòng tác động | Không | Không | Không |
| Kiểm tra FK theo ngữ nghĩa xóa dòng? | Có | Bị hạn chế bởi FK, không phải row delete | Bị hạn chế/ảnh hưởng constraints phụ thuộc | Object đã drop |
| Index/table structure còn? | Còn | Còn | Không dùng bình thường sau drop | Không phục hồi từ recycle bin sau purge |
| HWM table reset? | Thường không | Thường có | Object bị drop | Xử lý không gian object đã drop |
| Có thể thay đổi số file/dung lượng filesystem ngay? | Không tự động | Có thể trả extents nhưng không nhất thiết co file | Phụ thuộc recycle bin/storage | Có thể giải phóng extents, không nhất thiết co file |
| Recycle bin liên quan? | Không | Không | Có thể | Chính là đối tượng của thao tác |
| Khi nào phù hợp? | Xóa có chọn lọc/audit/transaction | Làm trống bảng tạm hoặc staging được phép | Bỏ bảng khỏi mô hình | Dọn bảng đã drop khi chắc chắn không cần flashback |

Các mục trong bảng là **hành vi chung đối với bảng Oracle thông thường**. Một số trường hợp như temporary table, bảng partitioned, table có domain index, cluster, materialized view hoặc các tính năng chuyên biệt có ràng buộc và cú pháp riêng. Không suy diễn rằng tất cả biến thể đều có cùng hiệu ứng chỉ từ bảng so sánh này.

## 9. Thực hành có kiểm soát trên một bảng độc lập

Các bước dưới đây dùng **bảng mới `LAB_CLEANUP_DEMO`**, không có FK để tránh đụng bảng nghiệp vụ. Hãy dùng một schema riêng trong PDB thực hành, có quyền `CREATE TABLE` và đủ quota tablespace. Nếu đã tồn tại bảng cùng tên trong schema hiện tại, **không chạy ghi đè hoặc drop nó**; hãy đổi tên bảng lab của bạn.

### Bước 1 — Tạo bảng và dữ liệu gốc

~~~sql
CREATE TABLE lab_cleanup_demo (
  record_id NUMBER NOT NULL,
  description VARCHAR2(100 CHAR) NOT NULL,
  created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT pk_lab_cleanup_demo PRIMARY KEY (record_id)
);

INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (1, 'Dong du lieu A');
INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (2, 'Dong du lieu B');
INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (3, 'Dong du lieu C');

COMMIT;

SELECT record_id, description
FROM lab_cleanup_demo
ORDER BY record_id;
~~~

Kết quả ban đầu có ba dòng với `RECORD_ID` là `1, 2, 3`.

### Bước 2 — DELETE rồi ROLLBACK

~~~sql
DELETE FROM lab_cleanup_demo
WHERE record_id = 2;

SELECT COUNT(*) AS remaining_rows
FROM lab_cleanup_demo;
-- Trong session này: 2 dòng.

ROLLBACK;

SELECT COUNT(*) AS remaining_rows
FROM lab_cleanup_demo;
-- Sau rollback: 3 dòng.
~~~

Ở session khác, hành vi quan sát các thay đổi chưa commit phụ thuộc isolation và snapshot. Trong chế độ phổ biến `READ COMMITTED`, session khác không nhìn thấy kết quả DELETE **chưa commit** của bạn như một thay đổi đã xác nhận. Khi commit, thay đổi mới trở thành dữ liệu đã xác nhận.

### Bước 3 — DELETE rồi COMMIT

~~~sql
DELETE FROM lab_cleanup_demo
WHERE record_id = 2;

COMMIT;

SELECT COUNT(*) AS remaining_rows
FROM lab_cleanup_demo;
-- 2 dòng.

ROLLBACK;

SELECT COUNT(*) AS remaining_rows
FROM lab_cleanup_demo;
-- Vẫn 2 dòng: commit đã kết thúc transaction.
~~~

Trong tình huống thực tế, điều này là lý do phải kiểm tra điều kiện DELETE và số dòng tác động trước khi commit. Không nên mặc định có thể undo sau khi đã gửi lệnh qua một framework bật auto-commit.

### Bước 4 — Chuẩn bị lại dữ liệu để thử TRUNCATE

~~~sql
INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (2, 'Dong du lieu B duoc tao lai');

COMMIT;

SELECT COUNT(*) AS total_rows
FROM lab_cleanup_demo;
-- Trở lại 3 dòng.
~~~

### Bước 5 — TRUNCATE rồi thử ROLLBACK

~~~sql
TRUNCATE TABLE lab_cleanup_demo REUSE STORAGE;

SELECT COUNT(*) AS total_rows
FROM lab_cleanup_demo;
-- 0 dòng.

ROLLBACK;

SELECT COUNT(*) AS total_rows
FROM lab_cleanup_demo;
-- Vẫn 0 dòng.
~~~

`REUSE STORAGE` cho phép giữ các extents đã cấp để dùng lại cho những lần insert tiếp theo; nó không làm phép truncate có thể rollback.

### Bước 6 — Tạo lại dữ liệu, DROP và quan sát recycle bin

~~~sql
INSERT INTO lab_cleanup_demo (record_id, description)
VALUES (10, 'Du lieu truoc DROP');
COMMIT;

-- Quan sát cấu hình recycle bin của session:
SHOW PARAMETER recyclebin

-- Khi được phép và phù hợp môi trường lab, dùng:
-- ALTER SESSION SET recyclebin = ON;

DROP TABLE lab_cleanup_demo;

SELECT object_name, original_name, type, droptime
FROM user_recyclebin
WHERE original_name = 'LAB_CLEANUP_DEMO'
ORDER BY droptime DESC;
~~~

`SHOW PARAMETER` là lệnh SQL*Plus/SQLcl, không phải SQL chuẩn. Nếu recycle bin bật và bảng đủ điều kiện, kết quả có một object tên `BIN$...`; nếu không xuất hiện, cần kiểm tra cấu hình/ngoại lệ, không giả định database đã làm mất dữ liệu do câu query.

Nếu lab có thể flashback, sau `DROP` hãy thử:

~~~sql
FLASHBACK TABLE lab_cleanup_demo TO BEFORE DROP;

SELECT COUNT(*)
FROM lab_cleanup_demo;
-- Có thể thấy lại dòng đã INSERT trước DROP.
~~~

Việc có khôi phục được hay không phụ thuộc recycle bin, quyền và tình trạng object. Trong trường hợp thành công, bảng được phục hồi từ recycle bin; thao tác này **không minh họa `ROLLBACK`**.

### Bước 7 — Thử DROP ... PURGE trên bảng lab được phép xóa

Nếu đã flashback thành công và chắc chắn không cần dữ liệu:

~~~sql
DROP TABLE lab_cleanup_demo PURGE;
~~~

Sau lệnh này, bảng không còn để dùng `FLASHBACK ... TO BEFORE DROP` với lần drop vừa thực hiện. Nếu không thể flashback ở bước 6, **không** tự tạo thêm lệnh xóa tên bảng hiện có mà chưa kiểm tra object/owner; có thể bỏ qua bước này.

### Bước 8 — PURGE đối tượng đã drop cụ thể

Để luyện câu `PURGE TABLE`, hãy tạo một bảng lab **khác tên**, rồi drop bình thường trong môi trường recycle bin đang bật:

~~~sql
CREATE TABLE lab_purge_demo (id NUMBER);
INSERT INTO lab_purge_demo VALUES (1);
COMMIT;

DROP TABLE lab_purge_demo;

SELECT object_name, original_name, type
FROM user_recyclebin
WHERE original_name = 'LAB_PURGE_DEMO';
~~~

Nếu query trả một hàng có `OBJECT_NAME` dạng `BIN$...`, sao chép **đúng tên đó** rồi chạy:

~~~sql
-- Thay toàn bộ placeholder bằng tên OBJECT_NAME thật trong kết quả:
PURGE TABLE "BIN$...ten_thuc_te...";
~~~

Quan sát lại `USER_RECYCLEBIN`, object đã purge không còn sẵn sàng cho flashback before drop. Không dùng `PURGE RECYCLEBIN` trên schema có nhiều object của người khác để chỉ xóa bài lab này.

## 10. Thực hành với FK: vì sao DELETE và TRUNCATE có quy tắc khác?

Tạo hai bảng lab độc lập với FK **không có ON DELETE CASCADE**:

~~~sql
CREATE TABLE lab_parent (
  parent_id NUMBER PRIMARY KEY,
  title VARCHAR2(60 CHAR) NOT NULL
);

CREATE TABLE lab_child (
  child_id NUMBER PRIMARY KEY,
  parent_id NUMBER NOT NULL,
  note_text VARCHAR2(60 CHAR),
  CONSTRAINT fk_lab_child_parent
    FOREIGN KEY (parent_id)
    REFERENCES lab_parent (parent_id)
);

INSERT INTO lab_parent VALUES (1, 'Parent A');
INSERT INTO lab_child VALUES (101, 1, 'Child A');
COMMIT;
~~~

### 10.1. DELETE parent khi child vẫn tồn tại

~~~sql
DELETE FROM lab_parent
WHERE parent_id = 1;
-- Thường ORA-02292: child record found.
~~~

Oracle ngăn xóa parent vì vẫn tồn tại child tham chiếu. Nếu nghiệp vụ cho phép xóa cả hai, một transaction có thể thực hiện:

~~~sql
DELETE FROM lab_child
WHERE parent_id = 1;

DELETE FROM lab_parent
WHERE parent_id = 1;

ROLLBACK;
-- Cả hai bảng về trạng thái trước transaction.
~~~

Nếu không dùng `ROLLBACK` mà `COMMIT`, kết quả xóa mới được xác nhận. Cách viết theo thứ tự child rồi parent là biểu hiện của việc hiểu quan hệ.

### 10.2. TRUNCATE bảng cha

~~~sql
-- Thử trên lab: thường không được phép khi FK khác bảng còn enabled.
TRUNCATE TABLE lab_parent;
~~~

Oracle thường báo một lỗi kiểu **`ORA-02266`** (unique/primary keys in table referenced by enabled foreign keys). Ngay cả khi truncate child trước, **FK vẫn enabled**; vì vậy bản thân việc child trống không tự bảo đảm câu truncate parent thành công.

~~~sql
TRUNCATE TABLE lab_child;
-- Có thể thành công trên bảng con.

TRUNCATE TABLE lab_parent;
-- Vẫn có thể bị từ chối do FK metadata còn enabled.
~~~

Nếu hệ thống được thiết kế cho `TRUNCATE CASCADE`, phải kiểm tra phiên bản và quy tắc FK phù hợp. Trong các bảng nghiệp vụ có FK phức tạp, `DELETE` có transaction hoặc quy trình maintenance được DBA thiết kế thường phù hợp hơn tự động disable các ràng buộc.

### 10.3. DROP parent với CASCADE CONSTRAINTS

~~~sql
-- Chỉ khi thực sự muốn bỏ bảng lab_parent và FK phụ thuộc.
DROP TABLE lab_parent CASCADE CONSTRAINTS;
~~~

Sau đó `LAB_CHILD` vẫn có thể tồn tại; constraint `FK_LAB_CHILD_PARENT` không còn vì bảng đích đã bị drop. Đừng nhầm `CASCADE CONSTRAINTS` với “xóa bảng con”. Cần kiểm tra `USER_CONSTRAINTS` và các đối tượng còn lại, không tiếp tục nạp dữ liệu con giả định FK vẫn bảo vệ như trước.

## 11. Oracle data dictionary: kiểm tra sau mỗi thao tác

Muốn biết bảng còn tồn tại, constraint còn không hay recycle bin có object, hãy dùng metadata thay vì đoán.

### 11.1. Đang ở PDB và schema nào?

~~~sql
SELECT
  SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name,
  SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
  SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
  SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Trong một CDB có nhiều PDB, hai bảng cùng tên trong các PDB khác nhau **không phải cùng một object**. Trước mọi `TRUNCATE`, `DROP` hay `PURGE`, xác nhận **PDB/service, user/schema và tên bảng đủ rõ ràng**.

### 11.2. Xem bảng còn trong schema

~~~sql
SELECT table_name, tablespace_name, status
FROM user_tables
WHERE table_name IN (
  'LAB_CLEANUP_DEMO', 'LAB_PARENT', 'LAB_CHILD'
)
ORDER BY table_name;
~~~

Sau `DELETE` hoặc `TRUNCATE`, tên bảng vẫn xuất hiện. Sau `DROP TABLE`, tên bảng gốc không còn như một bảng hoạt động thông thường. Nếu đang đăng nhập user khác, dùng các view `ALL_*` với điều kiện `OWNER` khi có quyền.

### 11.3. Xem recycle bin

~~~sql
SELECT
  object_name,
  original_name,
  type,
  droptime,
  can_undrop,
  can_purge
FROM user_recyclebin
WHERE original_name LIKE 'LAB_%'
ORDER BY droptime DESC;
~~~

`ORIGINAL_NAME` cho biết tên trước khi drop; `OBJECT_NAME` là tên hệ thống trong recycle bin. `CAN_UNDROP` và `CAN_PURGE` thể hiện thông tin mà Oracle ghi nhận về khả năng thao tác trên object đó. Recycle bin có thể có nhiều phiên bản với cùng `ORIGINAL_NAME` nếu bảng đã được drop nhiều lần.

### 11.4. Xem foreign key trước khi xóa

~~~sql
SELECT
  child.table_name AS child_table,
  child.constraint_name AS fk_name,
  parent.table_name AS parent_table,
  child.status,
  child.delete_rule
FROM user_constraints child
JOIN user_constraints parent
  ON parent.constraint_name = child.r_constraint_name
 AND parent.owner = child.r_owner
WHERE child.constraint_type = 'R'
  AND parent.table_name = 'LAB_PARENT'
ORDER BY child.table_name, child.constraint_name;
~~~

`DELETE_RULE` giúp nhận biết hành vi xóa liên quan FK, như `NO ACTION`, `CASCADE`, `SET NULL` theo constraint. `STATUS` cho biết FK có đang enabled hay không. Với schema khác, quyền/catalog và tên owner cần được xét; không kết luận “không có FK” chỉ vì user không nhìn thấy một bảng ngoài quyền.

## 12. Các tình huống lựa chọn lệnh

### Tình huống A — Xóa đơn hàng bị hủy theo kỳ lưu trữ

Yêu cầu: “Chỉ xóa đơn đã hủy và đã hết hạn lưu trữ, ghi audit, có thể rollback nếu tổng số dòng sai.”

**Chọn `DELETE ... WHERE`** trong transaction quản lý chặt chẽ, có kiểm tra FK, audit và điều kiện lưu trữ. `TRUNCATE` không phù hợp vì xóa toàn bộ bảng. Với dữ liệu nghiệp vụ quan trọng, cần có bản backup và thực hiện theo quy trình được duyệt.

### Tình huống B — Mỗi đêm tải lại bảng staging không có dữ liệu cần giữ

Yêu cầu: “Bảng staging độc lập, dữ liệu ngày hôm qua không cần giữ; chuẩn bị bảng trống để nạp mới nhiều triệu dòng.”

**Cân nhắc `TRUNCATE TABLE ... REUSE STORAGE`** nếu không vướng FK/đối tượng hạn chế, ứng dụng đã ngừng dùng bảng và chấp nhận DDL implicit commit. Nếu staging nằm trong một chuỗi công việc cần rollback toàn bộ, có thể phải chọn cách khác hoặc thiết kế quy trình nạp theo batch/partition riêng.

### Tình huống C — Bỏ hẳn bảng trung gian đã ngừng sử dụng

Yêu cầu: “Bảng không còn thuộc schema phiên bản mới; toàn bộ ứng dụng phụ thuộc đã được cập nhật.”

**Chọn `DROP TABLE`** trong migration được review. Kiểm tra constraint, view, synonym, code Java, grants và backup trước khi drop. Nếu chính sách cho phép recycle bin, tránh `PURGE` ngay để còn khả năng khôi phục hạn chế; nếu chính sách yêu cầu hủy object triệt để, việc purge phải là quyết định có chủ đích.

### Tình huống D — Dọn những bảng đã DROP, lấy lại chỗ trong tablespace

Yêu cầu: “Recycle bin của schema chứa nhiều bản thử nghiệm đã drop.”

**Chọn `PURGE TABLE "BIN$..."`** với đối tượng đã xác minh hoặc `PURGE RECYCLEBIN` chỉ khi có quyền và được phép dọn toàn bộ recycle bin của user. Không thể dùng `DELETE FROM` hay `TRUNCATE` đối với một bảng đã rời namespace hoạt động để làm cùng nhiệm vụ này.

### Tình huống E — Muốn làm trống bảng parent có nhiều foreign key

Yêu cầu: “Dọn một tập bảng liên quan trong môi trường tích hợp.”

Không thể chọn `TRUNCATE` chỉ vì nhanh. Cần lập **bản đồ dependencies**, hiểu FK enabled/disable, ON DELETE rule, audit, partition và mục tiêu rollback. Nếu muốn xóa có điều kiện hoặc cần ràng buộc theo từng dòng, dùng `DELETE` theo thứ tự thích hợp hoặc quy trình được thiết kế. Nếu cố ý truncate toàn hệ thống test, chỉ làm theo kịch bản maintenance và backup riêng.

### Tình huống F — Muốn xóa dữ liệu cá nhân theo yêu cầu quyền riêng tư

Yêu cầu: “Xóa một cá nhân và dữ liệu liên quan mà không làm mất chứng từ phải lưu.”

Không có một lệnh duy nhất giải quyết được bài toán. Cần phân loại dữ liệu, khóa ngoại, retention, lịch sử giao dịch, bản sao, backup và chính sách pháp lý áp dụng. `PURGE` recycle bin không tự xóa các dòng cá nhân trong bảng đang dùng; `TRUNCATE` làm mất toàn bộ dữ liệu không liên quan. Phải dùng thiết kế quy trình xóa/ẩn danh phù hợp và được kiểm chứng.

## 13. Lỗi thường gặp và cách chẩn đoán

| Lỗi/hiện tượng | Tình huống thường gặp | Giải thích/cách xử lý |
|---|---|---|
| `ORA-02292` | `DELETE` parent còn child | Xem FK, xử lý child theo nghiệp vụ hoặc chọn hành vi xóa quan hệ phù hợp |
| `ORA-02266` | `TRUNCATE` parent có enabled FK tham chiếu | Đây là giới hạn cấu trúc, không phải chỉ do bảng con có dữ liệu |
| `ORA-00942` sau `DROP` | Truy vấn tên bảng đã drop hoặc sai schema/quyền | Xác nhận `USER_TABLES`, `USER_RECYCLEBIN`, schema/PDB |
| `ORA-00054` | DDL không lấy được lock cần thiết | Xác định session đang giữ lock/giao dịch; xử lý theo quy trình vận hành |
| `ROLLBACK` không khôi phục sau TRUNCATE | TRUNCATE là DDL | Cần backup/restore nếu muốn lấy lại dữ liệu trước truncate |
| Không tìm thấy bảng trong recycle bin | `DROP ... PURGE`, recycle bin OFF, object không đủ điều kiện hoặc đã bị purge | Đọc cấu hình và lịch sử thao tác; không mặc định flashback được |
| `FLASHBACK TABLE ... TO BEFORE DROP` lỗi | Object không có, tên xung đột, hoặc điều kiện không thỏa | Xem `USER_RECYCLEBIN`; cân nhắc `RENAME TO` và phương án DBA |
| PURGE rồi file datafile không nhỏ lại | Recycle bin giải phóng segment không đồng nghĩa co datafile | Phân biệt free space trong tablespace và kích thước datafile |
| DELETE toàn bảng chậm | Xóa nhiều dòng, undo/redo, triggers, FK, lock | Đánh giá workload; cân nhắc bảo trì/partition/TRUNCATE nếu chấp nhận hậu quả |
| Chạy DROP bị lỗi FK | Bảng cha bị ràng buộc referential từ bảng khác | Đánh giá dependency, không tùy tiện dùng `CASCADE CONSTRAINTS` |
| JDBC DELETE xong không rollback được | Connection auto-commit hoặc transaction đã commit | Cấu hình quản lý transaction, xem transaction boundary trước khi xóa |

Không nên chỉ nhớ mã lỗi mà bỏ qua **ngữ cảnh schema, PDB, constraint và transaction**. Cùng mã có thể có nhiều nguyên nhân chi tiết; một truy vấn vào data dictionary thường cho biết thực tế cấu trúc tốt hơn suy đoán.

## 14. DELETE trong Java JDBC và transaction

Ứng dụng Java thường có nhu cầu xóa một tập dòng theo điều kiện và kiểm tra số dòng bị tác động. JDBC dùng `executeUpdate()` cho DELETE; giá trị trả về là **số dòng bị tác động** theo ngữ nghĩa statement.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.time.LocalDate;

// Giả sử connection thuộc một transaction do ứng dụng quản lý.
connection.setAutoCommit(false);

String sql = """
    DELETE FROM lab_orders
    WHERE order_status = ?
      AND created_at < ?
    """;

try {
    int deleted;
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setString(1, "CANCELLED");
        ps.setDate(2, java.sql.Date.valueOf(LocalDate.of(2025, 1, 1)));
        deleted = ps.executeUpdate();
    }

    // Ví dụ chính sách lab: không chấp nhận xóa quá 1000 dòng.
    if (deleted > 1000) {
        throw new IllegalStateException(
            "Unexpected delete count: " + deleted);
    }

    connection.commit();
} catch (Exception ex) {
    connection.rollback();
    throw ex;
}
~~~

Ví dụ giả định `CREATED_AT` có kiểu phù hợp với việc so sánh ngày và business rule đã xét rõ timezone. Trong ứng dụng thực tế, nếu `CREATED_AT` là `TIMESTAMP WITH TIME ZONE` hoặc dữ liệu được lưu ở UTC, phải bind đúng kiểu và mốc thời gian theo hợp đồng; không tùy tiện thay bằng `java.sql.Date` khiến ranh giới ngày bị hiểu sai.

Một lưu ý quan trọng khác: **số dòng trả về không chứng minh toàn bộ logic xóa đã đúng**. Nó chỉ cung cấp một chỉ số để xác nhận. Với nghiệp vụ quan trọng còn cần audit, kiểm tra quyền, quan hệ FK, thử trên môi trường staging, đo tác động và chuẩn bị phục hồi.

**Không** trộn `TRUNCATE TABLE` hoặc `DROP TABLE` vào cùng transaction JDBC với kỳ vọng `connection.rollback()` hủy toàn bộ quy trình. Những lệnh đó là DDL và Oracle có implicit commit riêng.

## 15. Xử lý khối lượng dữ liệu lớn và bảo toàn hoạt động

Khi một bảng có hàng chục/hàng trăm triệu dòng, lựa chọn lệnh có thêm ảnh hưởng tới khả năng phục vụ ứng dụng:

### 15.1. DELETE theo lô

Nếu chỉ cần dọn các dòng quá hạn:

- Có thể xác định predicate rõ ràng và xóa theo **lô được kiểm soát** để giới hạn thời gian giữ lock và lượng undo.
- Sau mỗi batch, ghi nhận số dòng và thông tin tiến độ trong một bảng/job log phù hợp.
- Tránh một transaction xóa quá lớn khiến undo, redo, locking và replication/standby apply chịu áp lực.
- **Không** dựa vào `ROWNUM <= n` như một cơ chế thứ tự nghiệp vụ ổn định khi không có chiến lược chọn batch/key phù hợp.

Ví dụ cú pháp xóa một lô nhỏ theo điều kiện:

~~~sql
DELETE FROM lab_orders
WHERE order_status = 'CANCELLED'
  AND created_at < DATE '2025-01-01'
  AND ROWNUM <= 500;

COMMIT;
~~~

Câu trên chỉ minh họa **giới hạn số dòng trong một lần DELETE**. Nó không bảo đảm xóa theo `ORDER BY` hoặc thứ tự cố định, và mỗi lần cần đánh giá lại điều kiện. Khi muốn xóa theo thứ tự dự đoán được hoặc để resume chính xác, dùng khóa/điều kiện chọn batch phù hợp; các batch khác nhau có thể nhìn snapshot dữ liệu khác nhau khi có ghi đồng thời.

### 15.2. Partition maintenance

Khi dữ liệu phân chia theo kỳ (ví dụ theo tháng), quản lý partition có thể cho phép loại bỏ dữ liệu cũ bằng thao tác trên **partition** thay vì DELETE từng dòng:

~~~sql
-- Ví dụ hình thức; yêu cầu bảng đã được partition đúng thiết kế.
ALTER TABLE lab_orders
  TRUNCATE PARTITION p_2024_01;
~~~

Đây là DDL, không phải DELETE có thể rollback. Tùy loại partitioned table, global indexes, referential constraints và cấu hình, cần thêm tùy chọn/index maintenance hoặc có giới hạn khác. Không áp dụng cho bảng không partitioned, và không tự chạy trên production khi chưa có kế hoạch về index/backup.

### 15.3. Lịch bảo trì và connection pool

`TRUNCATE`/`DROP` thay đổi cấu trúc hoặc dữ liệu ở phạm vi lớn, có thể yêu cầu DDL lock và ảnh hưởng các session đang truy cập. Ứng dụng có connection pool có thể giữ statement đã parse hoặc transaction đang chạy; sau thay đổi DDL, các cursor/plan có thể bị invalidated và request có thể nhận lỗi cho tới khi ứng dụng tái tạo statement/kết nối phù hợp.

Khi bảo trì, cần xác định:

1. Có thể tạm dừng đường ghi của ứng dụng và xử lý các transaction đang mở không?
2. DDL ảnh hưởng bao nhiêu đối tượng, FK, index, view, stored procedure và job?
3. Các lệnh có cần áp dụng theo thứ tự, cùng khoảng bảo trì hoặc theo migration không?
4. Đã có backup và **đã thử restore** trong môi trường tương thích chưa?
5. Sau thao tác sẽ xác minh count, schema, quyền, query và kết nối ứng dụng bằng cách nào?

## 16. Câu hỏi kiểm tra và bài tập vận dụng

### Bài 1 — DELETE chưa commit

Bạn chạy:

~~~sql
DELETE FROM lab_cleanup_demo WHERE record_id = 1;
ROLLBACK;
~~~

**Câu hỏi:** Nếu không có commit hay DDL xen giữa, dòng 1 còn không?

**Định hướng:** Có. `DELETE` là DML và rollback hủy những thay đổi chưa commit của transaction.

### Bài 2 — DDL làm commit giao dịch khác

Bạn chạy:

~~~sql
UPDATE lab_customer SET display_name = 'X' WHERE customer_id = 10;
TRUNCATE TABLE lab_staging;
ROLLBACK;
~~~

**Câu hỏi:** `ROLLBACK` có khôi phục cả tên khách hàng lẫn dữ liệu staging không?

**Định hướng:** Không. `TRUNCATE` là DDL và có implicit commit trước khi thực hiện; không được dùng như một bước có thể rollback của transaction DML.

### Bài 3 — Hai bảng trống nhưng không giống nhau

`DELETE FROM lab_cleanup_demo; COMMIT;` và `TRUNCATE TABLE lab_cleanup_demo;` đều có thể làm `COUNT(*) = 0`. Hãy nêu **ít nhất bốn khác biệt** không thể hiện qua `COUNT(*)`.

**Định hướng:** DML/DDL, rollback trước commit, trigger DELETE, lượng undo/redo và kiểu thao tác segment/HWM, implicit commit.

### Bài 4 — Foreign key vẫn còn

Đã truncate `LAB_CHILD`. `LAB_PARENT` vẫn có enabled FK từ `LAB_CHILD` tham chiếu tới. Vì sao `TRUNCATE LAB_PARENT` vẫn có thể lỗi?

**Định hướng:** Giới hạn truncate dựa vào **cấu trúc FK enabled** chứ không đơn giản phụ thuộc bảng child có bao nhiêu dòng.

### Bài 5 — DROP và PURGE

Bạn chạy:

~~~sql
DROP TABLE lab_cleanup_demo;
~~~

**Câu hỏi:** Bảng có thể phục hồi bằng `FLASHBACK TABLE ... TO BEFORE DROP` không? Câu trả lời có khác nếu là `DROP TABLE lab_cleanup_demo PURGE` không?

**Định hướng:** Drop bình thường **có thể** phục hồi khi recycle bin áp dụng và object còn; drop purge bỏ qua recycle bin, nên không có đường before-drop đó.

### Bài 6 — Sự khác nhau của hai loại CASCADE

Vì sao `DROP TABLE lab_parent CASCADE CONSTRAINTS` không có cùng ý nghĩa với `TRUNCATE TABLE lab_parent CASCADE`?

**Định hướng:** DROP CASCADE CONSTRAINTS loại bỏ **referential constraints** cần thiết để xóa parent object, không tự xóa tất cả child tables; TRUNCATE CASCADE là cơ chế làm trống dữ liệu liên quan trong điều kiện hỗ trợ.

### Bài 7 — Chọn lệnh trong ba yêu cầu

Đề xuất giải pháp cho:

1. Xóa 200 đơn bị hủy sau khi kiểm tra, cần audit và rollback khi có sai sót.
2. Làm trống một bảng staging độc lập trước khi nạp dữ liệu mới.
3. Dọn object đã drop khỏi recycle bin sau thời gian lưu giữ được phê duyệt.

**Định hướng:** (1) `DELETE ... WHERE` trong transaction; (2) có thể `TRUNCATE TABLE` nếu phù hợp; (3) `PURGE TABLE` nhắm đúng object hoặc lệnh purge có phạm vi đã được phê duyệt.

### Bài 8 — Mất bảng nhưng file vẫn chiếm đĩa

Sau `DROP TABLE`, `USER_RECYCLEBIN` có dòng `BIN$...` và tablespace vẫn gần đầy. Điều đó có hợp lý không?

**Định hướng:** Có. Object có thể còn được giữ trong recycle bin để hỗ trợ flashback before drop; purge giải phóng vùng lưu trữ theo cơ chế Oracle nhưng không nhất thiết làm file datafile của hệ điều hành co nhỏ.

## 17. Kết luận: chọn theo mục tiêu và khả năng khôi phục

~~~text
Bạn muốn làm gì?
   |
   +── Xóa một tập dòng theo điều kiện?
   |       └── DELETE ... WHERE
   |           DML; quản lý COMMIT/ROLLBACK; xét FK và trigger
   |
   +── Làm trống toàn bảng nhưng giữ schema?
   |       └── TRUNCATE TABLE
   |           DDL; implicit commit; không ROLLBACK
   |           xét FK, storage, maintenance
   |
   +── Bỏ hẳn bảng khỏi mô hình database?
   |       └── DROP TABLE
   |           DDL; có thể đưa vào recycle bin
   |           xét FK, object phụ thuộc và migration
   |
   └── Xóa object đã drop khỏi recycle bin?
           └── PURGE TABLE / PURGE RECYCLEBIN
               không phải xóa từng dòng đang hoạt động
               mất đường FLASHBACK TO BEFORE DROP qua recycle bin
~~~

**Điểm cốt lõi:** `DELETE` là thao tác **dữ liệu và transaction**; `TRUNCATE` là thao tác **làm trống bảng theo DDL**; `DROP` loại bỏ **bảng như một đối tượng**; còn `PURGE` xử lý **đối tượng đã drop trong recycle bin hoặc loại bỏ ngay khi drop**. Khi đứng trước yêu cầu “xóa”, hãy làm rõ cần xóa **dòng hay bảng**, có cần **WHERE, audit và rollback** không, có **foreign key** nào liên quan, dữ liệu có thể lấy lại từ **backup/recycle bin** không, và toàn bộ hệ thống có đang dùng đối tượng đó hay không. Lựa chọn đúng bắt đầu từ các câu hỏi ấy, không phải từ lệnh chạy nhanh nhất.
