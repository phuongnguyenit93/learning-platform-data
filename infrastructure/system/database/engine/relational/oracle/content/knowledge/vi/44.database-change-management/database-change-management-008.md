# Edition-Based Redefinition, editioning view và cross-edition trigger

Oracle Edition-Based Redefinition (EBR) là cơ chế giúp nâng cấp ứng dụng và cấu trúc truy cập dữ liệu trong khi database vẫn phục vụ các phiên làm việc đang chạy. EBR cho phép nhiều phiên bản của một số schema object cùng tồn tại trong các **edition** khác nhau. Session cũ tiếp tục dùng phiên bản object cũ; session mới được chuyển sang edition mới. Trong giai đoạn hai phiên bản cùng hoạt động, **editioning view** tạo lớp giao diện trên table và **cross-edition trigger** đồng bộ DML giữa cấu trúc cũ và mới.

EBR hữu ích khi một bản phát hành cần thay đổi PL/SQL, view hoặc cách biểu diễn dữ liệu nhưng không thể dừng toàn bộ ứng dụng để nâng cấp. Cơ chế này hỗ trợ triển khai theo từng bước, kiểm thử phiên bản mới và chuyển traffic có kiểm soát.

Bài học dùng Oracle Database 19c làm mốc, tập trung vào:
- Mô hình edition, edition hierarchy và editioned object.
- Bật edition cho schema, tạo edition và chọn edition cho session/service.
- Editioning view và cách tách giao diện ứng dụng khỏi base table.
- Forward và reverse cross-edition trigger.
- Quy trình nâng cấp online có backfill, kiểm tra, cutover và cleanup.
- Quản lý session cũ/mới, rollback và khả năng tương thích.
- Data dictionary, quyền, giới hạn và troubleshooting.
- Ví dụ SQL/PLSQL, kịch bản migration, lab và checklist vận hành.

EBR không tạo một bản sao vật lý của table cho mỗi edition. Table là cấu trúc dữ liệu dùng chung; các editioned object như PL/SQL unit và view có thể có phiên bản khác nhau theo edition. Vì vậy cần thiết kế kỹ cách đồng bộ dữ liệu khi hai phiên bản ứng dụng cùng ghi.

## 1. Bài toán nâng cấp ứng dụng không downtime

Giả sử ứng dụng phiên bản 1 dùng table EMPLOYEES với cột SALARY. Phiên bản 2 cần đổi tên logic cột thành BASE_SALARY, đồng thời thay đổi package xử lý lương.

Nếu sửa table và package trực tiếp trong một đợt triển khai duy nhất, có thể xảy ra:
- Session phiên bản 1 đang chạy nhưng object vừa bị thay đổi.
- Code cũ truy cập cột đã đổi tên hoặc bị drop.
- Session mới triển khai chưa đồng thời với toàn bộ connection pool.
- DML từ phiên bản cũ không cập nhật cột mới.
- Rollback application không thể chạy vì schema đã chuyển hoàn toàn sang dạng mới.

EBR giải quyết vấn đề bằng cách duy trì hai edition:

~~~text
                    ORA$BASE
                       |
                 APP_EDITION_V1
                       |
                 APP_EDITION_V2
                    /       \
             Old sessions  New sessions
             old package   new package
             old view      new view
                    \       /
                  Shared base table
             salary | base_salary
                       |
                Cross-edition triggers
                  synchronize DML
~~~

Trong giai đoạn chuyển tiếp:
- Session cũ phân giải package/view theo edition cũ.
- Session mới phân giải package/view theo edition mới.
- Base table dùng chung có thể chứa cả cột cũ và cột mới.
- Cross-edition trigger giữ hai cách biểu diễn đồng bộ.
- Sau khi session cũ đã thoát, có thể ngừng tương thích ngược và dọn cấu trúc cũ ở một release sau.

## 2. Edition và edition hierarchy

### 2.1. Edition là gì?

Edition là một namespace phiên bản trong database. Khi session chạy trong một edition, Oracle phân giải editioned object theo edition hiện tại và cây kế thừa của nó.

Một edition mới thường được tạo làm con của edition đang phát hành. Nó kế thừa các editioned object chưa được thay thế trong edition con. Khi tạo phiên bản mới của object trong edition con, session ở edition con thấy phiên bản mới; session ở edition cha tiếp tục thấy phiên bản cũ.

Edition không phải:
- Một schema/user mới.
- Một database mới.
- Một bản sao datafile.
- Một bản sao độc lập của table.
- Một transaction hoặc snapshot dữ liệu.

Nhiều edition có thể cùng tham chiếu một base table vật lý. Chúng khác nhau ở phiên bản object được phân giải và giao diện dữ liệu mà ứng dụng sử dụng.

### 2.2. Edition hierarchy

Edition được tổ chức thành cây cha/con. Database thường có edition gốc ORA$BASE. Một release mới có thể tạo child edition:

~~~sql
CREATE EDITION app_v2 AS CHILD OF ora$base;
~~~

Trong quy trình có nhiều lần nâng cấp, có thể tạo edition con từ edition đang phát hành:

~~~sql
CREATE EDITION app_v3 AS CHILD OF app_v2;
~~~

Child edition kế thừa object từ parent cho tới khi có version riêng trong child. Việc tạo edition không sao chép mọi object; nó tạo điểm phân nhánh trong cơ chế quản lý phiên bản.

Không nên tạo nhiều nhánh edition không có quy hoạch. Đặt tên theo release, ghi nhận parent edition và giữ một lộ trình cleanup rõ ràng.

### 2.3. Edition hiện tại của session

Kiểm tra edition mà session đang sử dụng:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME') AS current_edition
FROM dual;
~~~

Chuyển edition của session:

~~~sql
ALTER SESSION SET EDITION = app_v2;
~~~

Lệnh chỉ ảnh hưởng session hiện tại. Các session khác, kể cả session trong cùng connection pool, vẫn có thể đang ở edition cũ.

Ứng dụng nên xác định edition khi tạo session hoặc định tuyến qua database service được cấu hình edition. Không giả định đổi default edition sẽ tự chuyển những session đang tồn tại.

## 3. Bật edition cho schema và tạo edition

### 3.1. Điều kiện

Để sử dụng EBR:
- Database release hỗ trợ EBR.
- Schema sở hữu editioned objects được enable editions.
- User quản trị có quyền tạo edition và quản lý object.
- Ứng dụng kết nối vào đúng schema và edition.
- Các thay đổi table được thiết kế tương thích trong giai đoạn nhiều phiên bản cùng hoạt động.

Bật edition cho schema ứng dụng:

~~~sql
ALTER USER app_owner ENABLE EDITIONS;
~~~

Thực hiện bằng tài khoản có quyền quản trị phù hợp. Đây là thay đổi cấu hình schema; lập kế hoạch trước khi triển khai và kiểm tra object hiện có theo tài liệu release.

### 3.2. Tạo edition

Ví dụ tạo edition mới từ edition hiện hành:

~~~sql
CREATE EDITION app_v2 AS CHILD OF ora$base;
~~~

Quyền tạo edition thường cần quyền hệ thống phù hợp như CREATE ANY EDITION. Quản trị edition phải theo quy trình DBA và change management.

### 3.3. Cấp quyền sử dụng edition

Cấp quyền USE trên edition cho user cần kết nối:

~~~sql
GRANT USE ON EDITION app_v2 TO app_owner;
~~~

Quyền này cho phép user sử dụng edition được chỉ định. Nó không thay thế quyền object như SELECT/INSERT/UPDATE hoặc quyền thực thi package.

### 3.4. Chọn edition cho session

Sau khi được cấp quyền:

~~~sql
ALTER SESSION SET EDITION = app_v2;
~~~

Xác minh:

~~~sql
SELECT
    USER AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME') AS current_edition
FROM dual;
~~~

### 3.5. Default edition

Database có default edition cho session không được định tuyến tới edition khác. DBA có thể quản lý default edition theo quy trình phát hành, ví dụ:

~~~sql
ALTER DATABASE DEFAULT EDITION = app_v2;
~~~

Thay default edition chỉ ảnh hưởng session mới theo cơ chế mặc định; session đã kết nối vẫn giữ edition hiện tại. Trước khi thay đổi, kiểm tra user/service nào có edition riêng và chuẩn bị rollback.

## 4. Editioned object và noneditioned object

### 4.1. Object có phiên bản

Một số loại schema object có thể được version theo edition, thường bao gồm:
- PL/SQL procedures và functions.
- Packages và package bodies.
- Triggers.
- Views, bao gồm editioning views.
- Synonyms.
- Types và một số object type khác theo release.

Khi tạo phiên bản mới trong child edition, Oracle giữ phiên bản ở parent cho session thuộc parent.

### 4.2. Object không có phiên bản

Table là noneditioned object. Base table vật lý được dùng chung giữa các edition. Một số object type khác cũng không editionable; danh sách cụ thể phụ thuộc Oracle release.

Điều này có hệ quả quan trọng: nếu đổi cấu trúc base table, thay đổi đó có thể tác động tới mọi edition. EBR không tự tạo hai phiên bản table.

Ví dụ:
- Thêm cột mới thường có thể tương thích với code cũ nếu không đổi/xóa cột cũ.
- Drop hoặc rename cột cũ ngay khi session cũ còn chạy có thể làm code cũ lỗi.
- Thay đổi constraint hoặc datatype cần xem tác động lên tất cả phiên bản ứng dụng.

### 4.3. Kế thừa object

Khi session ở edition con yêu cầu một object chưa có phiên bản trong child, Oracle có thể phân giải tới phiên bản được kế thừa từ edition cha. Khi object được tạo hoặc thay đổi trong child, phiên bản riêng của child được sử dụng ở đó.

Điều này giúp tránh phải compile/copy toàn bộ schema khi tạo release mới. Tuy nhiên, cần theo dõi object invalid và dependency sau mỗi thay đổi.

### 4.4. Editionability của object

Có thể xem metadata object:

~~~sql
SELECT
    owner,
    object_name,
    object_type,
    status,
    editionable
FROM user_objects
ORDER BY object_type, object_name;
~~~

Đối với các phiên bản trên nhiều edition, dùng view có hậu tố _AE như DBA_OBJECTS_AE hoặc ALL_OBJECTS_AE để xem thông tin across editions nếu có quyền.

Không cố tạo phiên bản editioned của object type không được hỗ trợ. Đọc SQL Language Reference và EBR guide đúng release trước khi chọn object cho thiết kế.

## 5. Editioning view

### 5.1. Mục đích

Editioning view (EV) là lớp view đặc biệt giúp mỗi edition nhìn base table theo một giao diện cột phù hợp với phiên bản ứng dụng.

Ứng dụng nên truy cập editioning view thay vì truy cập trực tiếp base table. Khi cấu trúc vật lý thay đổi, DBA có thể tạo phiên bản EV khác trong edition mới trong khi phiên bản cũ vẫn giữ giao diện cũ.

Ví dụ:
- Base table có SALARY và BASE_SALARY.
- Edition cũ có EV chỉ hiển thị SALARY.
- Edition mới có EV chỉ hiển thị BASE_SALARY.
- Cùng tên view được version theo edition, còn table vật lý vẫn là một.

### 5.2. Tạo editioning view

Ví dụ table:

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    salary NUMBER(12,2) NOT NULL,
    department_id NUMBER
);
~~~

Trong edition cũ, tạo editioning view:

~~~sql
CREATE EDITIONING VIEW employees_ev AS
SELECT
    employee_id,
    salary,
    department_id
FROM employees;
~~~

Code cũ dùng EMPLOYEES_EV và tiếp tục thấy cột SALARY.

### 5.3. Giới hạn của editioning view

Editioning view có các giới hạn nghiêm ngặt để Oracle có thể ánh xạ DML trực tiếp tới một base table. Mô hình thông thường:
- View dựa trên đúng một base table.
- Các cột được chọn là tham chiếu trực tiếp tới cột base table.
- Có thể đổi tên cột trong giao diện view.
- Không dùng join, group by, aggregate hoặc biểu thức tính toán như view thông thường.
- Không dùng predicate lọc row trong định nghĩa editioning view.
- Không dùng view này để tổng hợp nhiều table.

Nếu cần join, filter hoặc tính toán, có thể đặt một ordinary view phía trên editioning view hoặc dùng API/query layer phù hợp. Kiểm tra chính xác các restriction trong SQL Language Reference của release.

### 5.4. DML qua editioning view

Editioning view được thiết kế để cho phép DML đơn giản đi tới base table. Ví dụ:

~~~sql
INSERT INTO employees_ev (employee_id, salary, department_id)
VALUES (1001, 5000, 10);

UPDATE employees_ev
SET salary = 5200
WHERE employee_id = 1001;
~~~

DML được ánh xạ tới các cột tương ứng trong base table. Cross-edition trigger trên base table có thể đồng bộ cột cũ/mới trong thời gian chuyển tiếp.

### 5.5. Quyền truy cập

Một thiết kế tốt thường:
- Cấp SELECT/INSERT/UPDATE/DELETE trên editioning view cho application user.
- Hạn chế hoặc không cấp DML trực tiếp trên base table cho application user.
- Giữ quyền thay đổi base table cho schema owner/DBA.
- Không để code ứng dụng phụ thuộc vào cột vật lý mà editioning view không công bố.

Lớp view chỉ có ý nghĩa khi ứng dụng thực sự sử dụng nó. Nếu ứng dụng vẫn DML trực tiếp vào base table, một phần lợi ích cô lập schema của EBR bị mất.

## 6. Thay đổi cấu trúc table theo kiểu tương thích

Vì table không được version theo edition, nâng cấp cấu trúc thường dùng chiến lược expand-and-contract:

1. **Expand:** thêm cột hoặc cấu trúc mới mà code cũ vẫn dùng được.
2. **Bridge:** tạo cross-edition trigger để đồng bộ thay đổi giữa cột cũ và mới.
3. **Backfill:** chuyển dữ liệu hiện có sang biểu diễn mới.
4. **Switch:** tạo code/view mới và chuyển session sang edition mới.
5. **Contract:** sau khi không còn session cũ, loại bỏ trigger/cột cũ trong một release sau.

Không đổi tên hoặc drop cột cũ ngay trong bước đầu. Mục tiêu là giữ tương thích trong thời gian phiên bản cũ và mới cùng chạy.

### 6.1. Ví dụ đổi tên logic

Giả sử cần thay SALARY bằng BASE_SALARY.

Thêm cột mới vào base table:

~~~sql
ALTER TABLE employees ADD (base_salary NUMBER(12,2));
~~~

Đây là thay đổi trên noneditioned table nên cả edition cũ và mới đều thấy cột vật lý mới. Tuy nhiên editioning view cũ vẫn chỉ công bố SALARY.

### 6.2. Tạo edition mới và phiên bản view mới

~~~sql
CREATE EDITION app_v2 AS CHILD OF app_v1;
ALTER SESSION SET EDITION = app_v2;
~~~

Trong edition mới, thay phiên bản editioning view:

~~~sql
CREATE OR REPLACE EDITIONING VIEW employees_ev AS
SELECT
    employee_id,
    base_salary,
    department_id
FROM employees;
~~~

Trong edition mới, ứng dụng nhìn thấy BASE_SALARY. Session thuộc edition cũ vẫn nhìn thấy phiên bản EV cũ với SALARY.

Việc CREATE OR REPLACE trong child edition tạo/thay version ở edition đang dùng; không chạy nhầm trong edition cha.

## 7. Cross-edition trigger

### 7.1. Vì sao cần trigger?

Trong thời gian chuyển tiếp, session cũ và session mới có thể cùng ghi vào một base table nhưng dùng các cột khác nhau.

Nếu chỉ thêm cột và backfill một lần:
- Session cũ có thể tiếp tục cập nhật cột cũ sau khi backfill.
- Cột mới sẽ bị stale.
- Session mới có thể ghi cột mới trong khi code cũ vẫn đọc cột cũ.
- Dữ liệu hai cách biểu diễn có thể lệch nhau.

Cross-edition trigger đồng bộ DML giữa phiên bản dữ liệu cũ và mới trong giai đoạn hai edition cùng hoạt động.

### 7.2. Forward crossedition trigger

Forward trigger chuyển thay đổi từ code/edition cũ sang cấu trúc mới. Ví dụ khi session cũ cập nhật SALARY, trigger ghi giá trị tương ứng vào BASE_SALARY.

~~~sql
CREATE OR REPLACE TRIGGER employees_forward_ct
BEFORE INSERT OR UPDATE ON employees
FORWARD CROSSEDITION
DISABLE
FOR EACH ROW
BEGIN
    :NEW.base_salary := :NEW.salary;
END;
/
~~~

Đây là ví dụ minh họa cho trường hợp ánh xạ một cột sang một cột. Cần kiểm tra cú pháp, edition sở hữu trigger và quy tắc kích hoạt theo đúng Oracle release. Cross-edition trigger có hướng FORWARD được Oracle phân biệt với trigger DML thông thường.

### 7.3. Reverse crossedition trigger

Reverse trigger chuyển thay đổi từ phiên bản mới về dạng mà code cũ vẫn hiểu. Khi session mới cập nhật BASE_SALARY, trigger cập nhật SALARY:

~~~sql
CREATE OR REPLACE TRIGGER employees_reverse_ct
BEFORE INSERT OR UPDATE ON employees
REVERSE CROSSEDITION
DISABLE
FOR EACH ROW
BEGIN
    :NEW.salary := :NEW.base_salary;
END;
/
~~~

Reverse trigger hữu ích khi old edition vẫn còn session đang hoạt động trong lúc new edition bắt đầu ghi. Khi toàn bộ old sessions đã được drain, nhu cầu đồng bộ ngược có thể kết thúc.

### 7.4. Enable và disable trigger

Cross-edition trigger có thể được tạo ở trạng thái DISABLE để chuẩn bị trước khi cutover. Bật khi đã kiểm tra:

~~~sql
ALTER TRIGGER employees_forward_ct ENABLE;
ALTER TRIGGER employees_reverse_ct ENABLE;
~~~

Tình trạng trigger cần được quản lý như một phần của release runbook. Không enable trigger trước khi xác nhận cột đích, mapping và dữ liệu đã sẵn sàng.

### 7.5. Trigger phải idempotent và có kiểm soát

Trong migration phức tạp:
- Xác định rõ nguồn dữ liệu có thẩm quyền ở từng edition.
- Không để forward và reverse ghi đè lẫn nhau ngoài dự kiến.
- Tránh gọi DML đệ quy trên cùng table từ trigger.
- Giữ logic trigger ngắn, xác định và dễ audit.
- Xử lý NULL, default, datatype conversion và lỗi validation.
- Kiểm tra trigger firing order với trigger hiện có.
- Đo redo/latency phát sinh khi trigger chạy.

Cross-edition trigger không thay thế backfill. Nó duy trì đồng bộ cho DML phát sinh trong giai đoạn hai phiên bản cùng tồn tại.

## 8. Quy trình EBR end-to-end

Một đợt nâng cấp online nên có các giai đoạn tách biệt.

### 8.1. Giai đoạn chuẩn bị

- Xác định object cần version và object không editionable.
- Bật editions cho schema từ trước.
- Ghi nhận edition hiện tại và object dependency.
- Thiết kế base table thay đổi theo kiểu expand-and-contract.
- Tạo kế hoạch backfill và đối soát.
- Chuẩn bị quyền, service, connection pool và rollback.
- Xác định thời gian tối đa cho coexistence.

### 8.2. Expand base table

Thêm cột hoặc cấu trúc mới mà phiên bản cũ vẫn hoạt động:

~~~sql
ALTER TABLE employees ADD (base_salary NUMBER(12,2));
~~~

Không drop SALARY trong giai đoạn này.

### 8.3. Tạo child edition

~~~sql
CREATE EDITION app_v2 AS CHILD OF app_v1;
GRANT USE ON EDITION app_v2 TO app_owner;
~~~

Sau đó chuyển session triển khai sang edition mới:

~~~sql
ALTER SESSION SET EDITION = app_v2;
~~~

### 8.4. Tạo version mới của editioning view và PL/SQL

Trong edition mới:
- Thay EV để công bố BASE_SALARY.
- Tạo package/procedure/function tương thích schema mới.
- Compile và kiểm tra dependency.
- Không chuyển traffic production trước khi smoke test.

### 8.5. Tạo và enable forward trigger

Tạo forward trigger để DML từ old edition tiếp tục cập nhật cột mới. Bật trigger theo change plan trước hoặc cùng thời điểm mở giai đoạn backfill, sao cho không có khoảng thời gian old DML bị bỏ sót.

### 8.6. Backfill dữ liệu cũ

Chuyển giá trị hiện có:

~~~sql
UPDATE employees
SET base_salary = salary
WHERE base_salary IS NULL;

COMMIT;
~~~

Ví dụ giả định SALARY luôn có giá trị và BASE_SALARY IS NULL chỉ ra row chưa backfill. Nếu NULL là giá trị hợp lệ, cần thêm migration marker hoặc logic phân biệt rõ.

Với table lớn:
- Chạy theo primary-key range hoặc batch.
- Commit theo batch có kiểm soát.
- Theo dõi undo, redo, locks và elapsed time.
- Cho phép resume.
- Không chạy một transaction khổng lồ nếu gây áp lực undo.
- Đối soát row chưa backfill sau mỗi batch.

### 8.7. Tạo reverse trigger

Trước khi mở new edition cho ghi dữ liệu, tạo/enable reverse trigger nếu old sessions còn cần đọc cột cũ. Điều này giữ hai biểu diễn đồng bộ khi new application cập nhật BASE_SALARY.

### 8.8. Kiểm tra trước cutover

- So sánh số row.
- Kiểm tra SALARY và BASE_SALARY theo từng row.
- Kiểm tra NULL và giá trị ngoài miền.
- Xác nhận trigger ENABLED.
- Xác nhận package/view mới VALID.
- Chạy integration test trong edition mới.
- Kiểm tra session đang dùng edition nào.
- Xác nhận rollback path và service routing.

### 8.9. Cutover

Định tuyến session mới sang edition mới. Có thể dùng service được cấu hình edition hoặc thiết lập edition cho session khi kết nối.

Session cũ đã tồn tại không tự chuyển edition. Giữ chúng chạy trong thời gian ngắn có kiểm soát rồi drain/close theo kế hoạch.

### 8.10. Drain old edition

Theo dõi số session cũ, request đang chạy, transaction dài và connection pool. Chỉ kết thúc giai đoạn tương thích khi không còn session/worker cần old edition và dữ liệu đã được xác minh.

### 8.11. Contract và cleanup

Sau khi không còn consumer cũ:
- Disable/drop cross-edition trigger không còn cần.
- Cập nhật view/package cuối cùng.
- Xóa cột cũ trong một change riêng nếu không còn dependency.
- Dọn edition cũ khi không còn session hoặc dependency.
- Backup trước cleanup và ghi nhận release cuối.

Không drop old edition ngay sau khi đổi service. Edition cũ là một phần rollback window cho tới khi xác nhận không còn cần quay lại.

## 9. Ví dụ minh họa đầy đủ: SALARY sang BASE_SALARY

### 9.1. Schema ban đầu

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    salary NUMBER(12,2) NOT NULL,
    department_id NUMBER
);

CREATE EDITIONING VIEW employees_ev AS
SELECT employee_id, salary, department_id
FROM employees;
~~~

Phiên bản cũ đọc và ghi EMPLOYEES_EV.SALARY.

### 9.2. Expand

~~~sql
ALTER TABLE employees ADD (base_salary NUMBER(12,2));
~~~

Giữ nguyên cột SALARY.

### 9.3. Tạo edition mới

~~~sql
CREATE EDITION app_v2 AS CHILD OF app_v1;
GRANT USE ON EDITION app_v2 TO app_owner;
ALTER SESSION SET EDITION = app_v2;
~~~

### 9.4. Thay editioning view trong app_v2

~~~sql
CREATE OR REPLACE EDITIONING VIEW employees_ev AS
SELECT employee_id, base_salary, department_id
FROM employees;
~~~

Phiên bản mới dùng BASE_SALARY. Phiên bản EV trong APP_V1 vẫn giữ SALARY.

### 9.5. Đồng bộ DML từ old edition

Trong edition phù hợp với quy trình EBR:

~~~sql
CREATE OR REPLACE TRIGGER employees_forward_ct
BEFORE INSERT OR UPDATE ON employees
FORWARD CROSSEDITION
DISABLE
FOR EACH ROW
BEGIN
    :NEW.base_salary := :NEW.salary;
END;
/
~~~

Enable khi chuẩn bị bắt đầu coexistence:

~~~sql
ALTER TRIGGER employees_forward_ct ENABLE;
~~~

### 9.6. Backfill row hiện có

~~~sql
UPDATE employees
SET base_salary = salary
WHERE base_salary IS NULL;

COMMIT;
~~~

Nếu table rất lớn, chia batch và kiểm tra row count còn thiếu:

~~~sql
SELECT COUNT(*) AS rows_not_backfilled
FROM employees
WHERE base_salary IS NULL;
~~~

### 9.7. Đồng bộ DML từ new edition

~~~sql
CREATE OR REPLACE TRIGGER employees_reverse_ct
BEFORE INSERT OR UPDATE ON employees
REVERSE CROSSEDITION
DISABLE
FOR EACH ROW
BEGIN
    :NEW.salary := :NEW.base_salary;
END;
/
~~~

Enable trước khi new edition bắt đầu ghi nếu old edition vẫn còn hoạt động:

~~~sql
ALTER TRIGGER employees_reverse_ct ENABLE;
~~~

### 9.8. Kiểm tra đồng nhất hai cột

~~~sql
SELECT COUNT(*) AS mismatched_rows
FROM employees
WHERE salary <> base_salary
   OR salary IS NULL AND base_salary IS NOT NULL
   OR salary IS NOT NULL AND base_salary IS NULL;
~~~

Trong ví dụ SALARY là NOT NULL. Với dữ liệu thực tế, dùng điều kiện NULL-safe phù hợp và kiểm tra datatype/rounding.

### 9.9. Ứng dụng mới

Code trong APP_V2 truy cập:

~~~sql
SELECT employee_id, base_salary, department_id
FROM employees_ev
WHERE employee_id = :employee_id;
~~~

Old code vẫn truy cập SALARY qua phiên bản view cũ. Cross-edition triggers duy trì hai cột trong giai đoạn coexistence.

### 9.10. Sau cutover

Khi old sessions đã drain:
- Ngừng reverse synchronization nếu không còn old consumer.
- Xác nhận không có dependency trên SALARY.
- Lên lịch contract change riêng để drop cột cũ.
- Dọn cross-edition trigger và edition cũ theo dependency.
- Tạo backup và chạy regression test sau cleanup.

Ví dụ này chỉ minh họa ánh xạ một cột sang một cột. Chuyển đổi dữ liệu thực tế có thể cần function chuẩn hóa, xử lý NULL, rounding, timezone hoặc dữ liệu lịch sử; phải thiết kế mapping riêng và kiểm thử.

## 10. Backfill dữ liệu lớn và tránh race condition

### 10.1. Vì sao backfill cần trigger?

Giả sử backfill bắt đầu lúc 10:00 và hoàn tất lúc 10:30. Trong 30 phút đó, old application vẫn có thể cập nhật SALARY. Nếu không có forward trigger, một số row đã backfill có thể trở nên stale và row chưa backfill có thể nhận giá trị cũ.

Forward trigger giúp mỗi DML từ old edition tiếp tục ghi giá trị sang cột mới.

### 10.2. Backfill theo batch

Ví dụ xử lý theo employee_id range:

~~~sql
UPDATE employees
SET base_salary = salary
WHERE employee_id >= :low_id
  AND employee_id < :high_id
  AND base_salary IS NULL;

COMMIT;
~~~

Lặp theo range nhỏ, lưu checkpoint tiến độ. Range size cần dựa trên kích thước table, redo/undo capacity và thời gian lock.

### 10.3. Tránh ghi đè dữ liệu mới

Điều kiện BASE_SALARY IS NULL trong ví dụ giúp tránh ghi đè row đã được trigger hoặc ứng dụng mới cập nhật, với giả định NULL chỉ có nghĩa chưa backfill.

Nếu NULL là giá trị nghiệp vụ hợp lệ, dùng migration marker hoặc trạng thái riêng để phân biệt. Không dùng điều kiện đơn giản mà không hiểu semantics dữ liệu.

### 10.4. Đối soát sau backfill

Đếm:
- Tổng row.
- Row chưa chuyển đổi.
- Row mismatch.
- Row có giá trị NULL bất thường.
- Row được cập nhật trong thời gian backfill.

Đối với phép chuyển đổi phức tạp, so sánh bằng function migration giống nhau ở backfill và trigger để tránh hai nơi áp dụng logic khác nhau.

## 11. Quản lý service và connection pool

### 11.1. Session edition không tự thay đổi

Một connection pool có thể giữ connection từ trước cutover. Dù service mặc định đã chuyển edition, session cũ vẫn giữ edition hiện tại cho tới khi disconnect hoặc được xử lý theo cơ chế hỗ trợ.

Cần có kế hoạch:
- Drain connection pool cũ.
- Ngăn connection cũ tái sử dụng sau thời điểm cutover.
- Tạo pool/service mới gắn edition mới.
- Theo dõi session còn ở edition cũ.
- Xử lý transaction dài và job nền.

### 11.2. Edition gắn với database service

Oracle service có thể được cấu hình để session mới kết nối qua service đó dùng edition chỉ định. Có thể quản lý edition thuộc service qua DBMS_SERVICE trong quy trình DBA phù hợp.

Ví dụ minh họa:

~~~sql
BEGIN
    DBMS_SERVICE.MODIFY_SERVICE(
        service_name => 'app_v2_service',
        edition      => 'APP_V2'
    );
END;
/
~~~

Tên service, quyền và tham số hỗ trợ phải kiểm tra theo release và cách quản lý service (DBMS_SERVICE, srvctl hoặc cloud service). Không dùng lệnh minh họa trên production nếu chưa xác nhận service hiện hữu và cấu hình HA.

### 11.3. Kiểm tra session

Có thể quan sát edition hiện tại từ chính session:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME')
FROM dual;
~~~

DBA có thể dùng các dynamic performance view và data dictionary để giám sát session, service, edition và connection pool. Thu thập bằng chứng trước và sau cutover.

## 12. PL/SQL dependency và invalid object

### 12.1. Dependency theo edition

Package/procedure/function có thể phụ thuộc editioning view và các editioned object khác. Khi thay view hoặc package trong edition mới, cần compile/test các dependency trong edition đó.

### 12.2. Compile và kiểm tra

~~~sql
SELECT
    object_name,
    object_type,
    status
FROM user_objects
WHERE status <> 'VALID'
ORDER BY object_type, object_name;
~~~

Xem lỗi compile:

~~~sql
SELECT
    name,
    type,
    line,
    position,
    text
FROM user_errors
ORDER BY name, sequence;
~~~

Các view trên phản ánh schema/session context. Khi kiểm tra nhiều edition, dùng các data dictionary view across editions nếu có quyền.

### 12.3. Không compile nhầm edition

Trước khi chạy DDL/compile script, xác nhận:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CURRENT_EDITION_NAME')
FROM dual;
~~~

Một script tạo package trong edition cha có thể thay đổi phiên bản mà session cũ đang dùng. Mọi migration script nên log edition đầu vào và fail fast nếu không đúng edition dự kiến.

## 13. Data dictionary phục vụ EBR

### 13.1. Danh sách edition

~~~sql
SELECT
    edition_name,
    parent_edition_name
FROM dba_editions
ORDER BY edition_name;
~~~

### 13.2. Object qua các edition

~~~sql
SELECT
    owner,
    object_name,
    object_type,
    edition_name,
    status
FROM dba_objects_ae
WHERE owner = 'APP_OWNER'
ORDER BY object_name, edition_name;
~~~

DBA_OBJECTS_AE giúp quan sát object version theo edition. Quyền đọc dictionary view tùy DBA grants.

### 13.3. Editioning view

~~~sql
SELECT
    owner,
    view_name,
    table_name
FROM dba_editioning_views
WHERE owner = 'APP_OWNER'
ORDER BY view_name;
~~~

### 13.4. Schema được enable editions

Kiểm tra metadata user/schema theo dictionary view phù hợp release, ví dụ:

~~~sql
SELECT username, editions_enabled
FROM dba_users
WHERE username = 'APP_OWNER';
~~~

### 13.5. Trigger metadata

~~~sql
SELECT
    owner,
    trigger_name,
    table_name,
    status,
    triggering_event
FROM dba_triggers
WHERE owner = 'APP_OWNER'
ORDER BY trigger_name;
~~~

Dùng view cross-edition trigger chuyên biệt nếu release cung cấp và quyền cho phép; kết hợp trigger metadata với source code/DDL deployment log để xác nhận hướng FORWARD/REVERSE và edition sở hữu trigger.

## 14. EBR và DBMS_REDEFINITION

EBR và DBMS_REDEFINITION có thể cùng xuất hiện trong một dự án nâng cấp, nhưng chúng giải quyết hai vấn đề khác nhau.

| Tiêu chí | Edition-Based Redefinition | DBMS_REDEFINITION |
| --- | --- | --- |
| Mục tiêu | Version code/schema interface theo edition | Thay đổi cấu trúc table online |
| Đối tượng chính | Editioned objects, editioning views, crossedition triggers | Table và các dependent objects |
| Hai phiên bản code cùng chạy | Có | Không phải mục tiêu chính |
| Đồng bộ dữ liệu | Cross-edition trigger và migration logic | Internal synchronization trong redefinition |
| Table vật lý | Dùng chung giữa editions | Có thể xây dựng interim table rồi đồng bộ/swap |
| Trường hợp phù hợp | Release application cần coexistence | Thay đổi cấu trúc table lớn theo phương thức online |

Nếu chỉ thay đổi định nghĩa table hoặc chuyển storage/partition, DBMS_REDEFINITION có thể phù hợp hơn. Nếu cần hai phiên bản PL/SQL/view cùng hoạt động, EBR giải quyết trực tiếp hơn. Có thể kết hợp hai kỹ thuật theo kiến trúc và release plan.

## 15. Giới hạn và điều kiện cần cân nhắc

- Không phải mọi schema object đều editionable.
- Base table không có phiên bản riêng cho từng edition.
- Thay đổi table có thể ảnh hưởng tất cả edition.
- Editioning view có giới hạn định nghĩa chặt hơn ordinary view.
- Cross-edition trigger tăng logic DML và có thể tăng redo/latency.
- Coexistence dài làm tăng độ phức tạp kiểm thử và vận hành.
- Object dependency có thể tạo invalid object khi thay API.
- Một số tính năng, loại object hoặc integration cần xử lý riêng theo release.
- EBR không thay thế backup, restore drill hoặc rollback database.
- EBR không tự rollback dữ liệu nghiệp vụ đã ghi theo format mới.

Không phải mọi migration đều cần EBR. Với thay đổi đơn giản, backward-compatible và downtime ngắn được chấp nhận, rolling deployment đơn giản có thể ít phức tạp hơn. Chọn EBR khi lợi ích coexistence/online upgrade xứng đáng với chi phí thiết kế, trigger và kiểm thử.

## 16. Troubleshooting thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-38802 | User chưa được enable editions hoặc điều kiện edition không hợp lệ | Kiểm tra schema edition-enabled và thao tác DDL |
| ORA-38803 | Edition không tồn tại hoặc không hợp lệ | Kiểm tra DBA_EDITIONS và edition hierarchy |
| ORA-38804 | Không thể drop edition do dependency/child edition | Xác định dependency, child edition và cleanup order |
| ORA-38805 | Object không thể thao tác trong edition context hiện tại | Kiểm tra editionability và session edition |
| ORA-38818 | Reference tới object ở edition khác không được phép | Kiểm tra dependency và edition visibility |
| ORA-04063 | Package/view có lỗi | Đọc USER_ERRORS/DBA_ERRORS và compile đúng edition |
| ORA-04098 | Trigger invalid khi kích hoạt | Kiểm tra trigger source, dependency và compile errors |
| Cột mới NULL sau backfill | Forward trigger chưa enable hoặc backfill chưa hoàn tất | Kiểm tra trigger, batch progress và mismatch query |
| Hai cột không đồng bộ | Thiếu một hướng trigger hoặc mapping sai | Kiểm tra forward/reverse trigger và DML path |
| New session vào edition cũ | Service/pool chưa được chuyển | Kiểm tra service edition và tạo/drain connection pool |
| Old session lỗi sau deploy | Cột/view cũ bị drop hoặc thay đổi không tương thích | Khôi phục tương thích và drain old sessions trước contract |
| Cutover không thể rollback | Dữ liệu mới không còn biểu diễn được ở format cũ | Giữ reverse mapping và kiểm tra downgrade feasibility |
| Trigger làm DML chậm | Trigger phức tạp hoặc chạy cho mọi row | Rút gọn mapping, đo contention và batch backfill |
| Package VALID nhưng ứng dụng lỗi | Runtime behavior/API khác giữa edition | Integration test theo service/edition thực tế |

Thông báo lỗi đầu tiên trong alert log hoặc client thường quan trọng hơn lỗi tổng hợp cuối. Ghi lại current edition, object owner, object type và deployment step tại thời điểm lỗi.

## 17. Runbook triển khai EBR

### Trước khi phát hành
- Ghi nhận current/default edition và edition hierarchy.
- Xác nhận schema được enable editions.
- Liệt kê editioned và noneditioned objects.
- Xác định base table changes và compatibility window.
- Thiết kế editioning view mới.
- Thiết kế forward/reverse trigger.
- Ước lượng backfill, redo, undo và storage.
- Xác nhận service/connection pool routing.
- Có RMAN backup và rollback plan.

### Khi triển khai
- Expand table bằng thay đổi tương thích.
- Tạo child edition.
- Tạo view/package version mới trong child.
- Tạo và kiểm tra cross-edition trigger.
- Enable forward trigger đúng thời điểm.
- Backfill theo batch.
- Đối soát dữ liệu cũ/mới.
- Enable reverse trigger nếu old sessions còn hoạt động.
- Chạy smoke/integration test trong new edition.
- Chuyển session/service mới sang edition mới.

### Sau cutover
- Theo dõi session cũ và mới.
- Theo dõi trigger errors, invalid objects và DML latency.
- Đối soát hai cách biểu diễn dữ liệu.
- Drain old pool/session.
- Giữ old edition trong rollback window.
- Sau khi ổn định, cleanup trigger và cột cũ theo release riêng.
- Backup và cập nhật runbook/edition inventory.

## 18. Lab: tạo hai edition và editioning view

Thực hiện trong Oracle lab riêng với user có quyền phù hợp. Không chạy các lệnh DDL này trên schema production.

### 18.1. Enable editions và tạo table

~~~sql
ALTER USER lab_app ENABLE EDITIONS;
~~~

Kết nối bằng LAB_APP hoặc DBA thực hiện DDL trong schema:

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    salary NUMBER(12,2) NOT NULL
);

CREATE EDITIONING VIEW employees_ev AS
SELECT employee_id, salary
FROM employees;
~~~

### 18.2. Tạo edition mới

~~~sql
CREATE EDITION lab_v2 AS CHILD OF ora$base;
GRANT USE ON EDITION lab_v2 TO lab_app;
~~~

### 18.3. Thêm cột và thay view trong edition mới

~~~sql
ALTER TABLE employees ADD (base_salary NUMBER(12,2));
ALTER SESSION SET EDITION = lab_v2;

CREATE OR REPLACE EDITIONING VIEW employees_ev AS
SELECT employee_id, base_salary
FROM employees;
~~~

Mở session khác ở edition cha để xác nhận view cũ vẫn công bố SALARY; session ở LAB_V2 thấy BASE_SALARY.

### 18.4. Cross-edition trigger

Tạo forward trigger và reverse trigger theo ví dụ ở mục 7, kiểm tra trigger source và trạng thái trước khi enable.

### 18.5. Backfill và kiểm tra

~~~sql
UPDATE employees
SET base_salary = salary
WHERE base_salary IS NULL;

COMMIT;

SELECT COUNT(*)
FROM employees
WHERE salary <> base_salary
   OR salary IS NULL AND base_salary IS NOT NULL
   OR salary IS NOT NULL AND base_salary IS NULL;
~~~

### 18.6. Thử coexistence

- Session A đặt edition cũ và update qua EV cũ.
- Session B đặt edition LAB_V2 và update qua EV mới.
- Xác nhận trigger đồng bộ giá trị theo đúng hướng.
- Commit/rollback riêng từng session.
- Quan sát edition context và dữ liệu base table.

### 18.7. Dọn lab

Chỉ cleanup sau khi không còn session sử dụng edition thử nghiệm. Xóa trigger, view, table và edition theo dependency order; không dùng lệnh DROP EDITION CASCADE khi chưa hiểu object nào sẽ bị xóa.

## 19. Bài tập thực hành

1. Giải thích vì sao tạo child edition không tạo bản sao của table.
2. Tạo hai edition và xác minh cùng tên package có thể có nội dung khác nhau.
3. Tạo editioning view trong parent và thay version của nó trong child.
4. Chứng minh session hiện tại không tự đổi edition khi default edition thay đổi.
5. Thêm cột mới vào base table mà không làm mất giao diện view cũ.
6. Viết forward trigger đồng bộ old column sang new column.
7. Viết reverse trigger và kiểm tra DML từ new edition.
8. Backfill một table lớn theo primary-key range và lưu checkpoint tiến độ.
9. Đối soát hai cột và xác định row mismatch.
10. Thiết kế cutover service/pool và quy trình drain old sessions.
11. Phân tích trường hợp không thể rollback vì dữ liệu mới không có mapping ngược.
12. So sánh EBR với DBMS_REDEFINITION cho một migration thực tế.

## 20. Dọn dẹp và bảo vệ sau lab

- Xác nhận session đang dùng đúng edition.
- Kiểm tra object status và dependency.
- Kiểm tra trigger ENABLED/DISABLED theo trạng thái dự kiến.
- Không drop base table hoặc cột dùng chung khi còn edition khác phụ thuộc.
- Không drop edition còn child edition hoặc session/dependency.
- Lưu DDL, edition map và migration log.
- Tạo backup trước khi cleanup cấu trúc cũ.
- Giữ rollback window theo change plan.
- Thu hồi quyền USE trên edition lab khi không còn cần.
- Không để cross-edition trigger thử nghiệm hoạt động ngoài thời gian lab.

## Tổng kết

Edition-Based Redefinition cho phép nhiều phiên bản editioned object cùng tồn tại trong một database. Session cũ và mới có thể dùng package/view khác nhau trong khi cùng truy cập base table. Editioning view cung cấp giao diện cột theo từng edition; cross-edition trigger đồng bộ DML giữa cấu trúc cũ và mới trong giai đoạn coexistence.

Một đợt EBR thường đi theo expand, bridge, backfill, switch, drain và contract. Thêm cột mới mà vẫn giữ cột cũ, tạo child edition, thay editioning view và PL/SQL trong child, đồng bộ dữ liệu bằng forward/reverse trigger, rồi chuyển session/service sang edition mới. Chỉ loại bỏ cột và edition cũ sau khi không còn session hoặc dependency cần chúng.

EBR là công cụ triển khai nâng cấp online, không phải cơ chế version hóa table vật lý hay thay thế backup/recovery. Thành công phụ thuộc vào thiết kế tương thích, backfill có thể tiếp tục, đối soát dữ liệu, service routing, quản lý connection pool và rollback plan có kiểm chứng.

## Tài liệu Oracle tham khảo

- [Oracle Database Development Guide — Edition-Based Redefinition (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/editions.html) — edition, editioned objects, editioning views và cross-edition triggers.
- [Oracle Database SQL Language Reference — CREATE EDITION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-EDITION.html) — tạo edition và quan hệ parent/child.
- [Oracle Database SQL Language Reference — CREATE VIEW (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-VIEW.html) — view và editioning view syntax.
- [Oracle Database SQL Language Reference — CREATE TRIGGER (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html) — trigger syntax, crossedition clauses và trigger behavior.
- [Oracle Database PL/SQL Packages and Types Reference (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/) — DBMS_SERVICE và các package quản lý service.
- [Oracle Database Administrator's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — user, service, session và database administration.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_REDEFINITION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_REDEFINITION.html) — online table redefinition.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu EBR guide và SQL Language Reference đúng phiên bản, đặc biệt editionability, cross-edition trigger syntax, editioning view restrictions, service edition routing, object dependency và cleanup behavior.
