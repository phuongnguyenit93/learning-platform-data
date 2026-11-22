# Quan hệ phụ thuộc giữa đối tượng và cơ chế invalidation

Trong Oracle Database, các đối tượng của schema thường không hoạt động độc lập. Một **view** đọc bảng; một **procedure** truy vấn view; một **package** gọi function của package khác; một **trigger** được gắn vào bảng. Khi cấu trúc hoặc định nghĩa của đối tượng được tham chiếu thay đổi, Oracle phải quyết định liệu những đối tượng phụ thuộc còn sử dụng được hay cần **invalidation** (đánh dấu không còn hợp lệ) và **recompilation** (biên dịch lại).

Đây là cơ chế quan trọng khi phát triển hệ thống Oracle: một câu lệnh DDL tác động lên một bảng có thể ảnh hưởng cả API dữ liệu phía trên, mặc dù lập trình viên không sửa trực tiếp view hoặc procedure. Ngược lại, Oracle có những cơ chế theo dõi phụ thuộc chi tiết để tránh vô hiệu hóa không cần thiết khi thay đổi không ảnh hưởng tới thành phần được sử dụng.

Bài học tập trung vào bốn câu hỏi:

1. Oracle ghi nhận **ai phụ thuộc vào ai** như thế nào?
2. Những thay đổi nào có thể khiến đối tượng trở thành **INVALID**?
3. Điều gì xảy ra khi một phiên gọi đối tượng đã bị invalidation?
4. Làm sao dùng **data dictionary** để kiểm tra và quản lý tác động của thay đổi schema?

## 1. Đối tượng schema tạo thành đồ thị phụ thuộc

Giả sử có bảng khách hàng, một view chọn khách đang hoạt động và một procedure đếm số khách:

~~~text
P_DEM_KH_ACTIVE (PROCEDURE)
        |
        | truy vấn
        v
V_KH_ACTIVE (VIEW)
        |
        | đọc dữ liệu
        v
KHACH_HANG_DEP (TABLE)
~~~

Đây là đồ thị phụ thuộc theo hướng **đối tượng sử dụng → đối tượng được sử dụng**:

- **Dependent object**: đối tượng cần định nghĩa hoặc đặc điểm của đối tượng khác để hoạt động, ví dụ procedure cần view.
- **Referenced object**: đối tượng được phụ thuộc, ví dụ view được procedure truy vấn.
- **Direct dependency**: procedure trực tiếp tham chiếu view.
- **Indirect/transitive dependency**: procedure gián tiếp phụ thuộc vào bảng qua view.

Trong ví dụ, nếu đổi tên cột mà view sử dụng, view có thể bị invalidation; procedure phía trên cũng có thể bị ảnh hưởng khi Oracle cần xác định lại khả năng thực thi. Khi xét tác động của một thay đổi, cần nhìn **cả nhánh downstream**, không chỉ đối tượng bị sửa.

### 1.1. Các mối phụ thuộc thường gặp

| Đối tượng sử dụng | Đối tượng được sử dụng | Tại sao phát sinh phụ thuộc? |
| --- | --- | --- |
| View | Table/view khác | Cần cột, kiểu dữ liệu và tên đối tượng trong câu SELECT |
| Procedure/function | Table, view, package, function... | SQL tĩnh hoặc lời gọi đối tượng trong mã PL/SQL |
| Package body | Package specification, bảng/view, các program unit khác | Body hiện thực interface và sử dụng đối tượng khác |
| Procedure khác schema | Public interface của package được cấp quyền | Phụ thuộc chữ ký/thành phần được gọi và quyền thích hợp |
| Trigger | Table sở hữu trigger và đối tượng mà mã trigger tham chiếu | Kích hoạt theo sự kiện, sử dụng cột/đối tượng |
| Materialized view | Table/view nguồn và metadata liên quan | Định nghĩa dữ liệu materialized view dựa trên nguồn |
| SQL shared cursor | Table/view và metadata dùng để parse/execute SQL | Cần kiểm tra lại khi định nghĩa hoặc thông tin tối ưu hóa thay đổi |

Không phải mọi phụ thuộc đều có cùng cơ chế invalidation hoặc cùng trạng thái metadata. Đặc biệt, **cursor SQL trong library cache** và **stored object như view/procedure/package** là hai phạm vi khác nhau: một thay đổi có thể khiến cursor phải parse lại nhưng không làm stored procedure trở thành INVALID.

### 1.2. Phụ thuộc tĩnh và phụ thuộc động

Oracle có thể ghi nhận phụ thuộc từ **câu lệnh SQL tĩnh** và lời gọi đối tượng được phân tích khi tạo/biên dịch view hay PL/SQL:

~~~sql
CREATE OR REPLACE PROCEDURE p_dem_kh_active AS
    v_dem NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_dem
    FROM v_kh_active;

    DBMS_OUTPUT.PUT_LINE('So khach: ' || v_dem);
END;
/
~~~

Ở đây, mã procedure có tham chiếu tĩnh đến **V_KH_ACTIVE**, nên Oracle có thể lưu mối quan hệ trong data dictionary.

Với **dynamic SQL**:

~~~sql
EXECUTE IMMEDIATE
    'DELETE FROM bang_tam_thuc_hanh WHERE ngay_tao < :1'
    USING DATE '2024-01-01';
~~~

Tên bảng nằm trong chuỗi được phân tích **khi thực thi**, nên không nên mặc định Oracle có thể liệt kê mọi đối tượng được truy cập động trong metadata phụ thuộc biên dịch. Bảng được chọn từ cấu hình, tên đối tượng được ghép động, đối tượng ở xa qua database link hoặc logic ở dịch vụ Java càng đòi hỏi phương pháp phân tích tác động riêng.

**USER_DEPENDENCIES không phải bản kiểm kê tuyệt đối mọi truy cập dữ liệu có thể xảy ra trong hệ thống.**

## 2. Data dictionary lưu thông tin phụ thuộc ở đâu?

Oracle cung cấp các view metadata theo phạm vi quyền truy cập:

| View | Phạm vi thông tin | Mục đích |
| --- | --- | --- |
| **USER_DEPENDENCIES** | Phụ thuộc của đối tượng do user hiện tại sở hữu | Tìm các đối tượng trong schema đang tham chiếu đối tượng khác |
| **ALL_DEPENDENCIES** | Thông tin phụ thuộc của đối tượng người dùng được phép nhìn thấy | Xem trong phạm vi truy cập được cấp |
| **DBA_DEPENDENCIES** | Phụ thuộc ở phạm vi database, cần quyền phù hợp | Phân tích toàn cục, đặc biệt khi nhiều schema phụ thuộc nhau |
| **USER_OBJECTS** | Đối tượng thuộc schema hiện tại, gồm OBJECT_TYPE và STATUS | Kiểm tra VALID/INVALID |
| **USER_ERRORS** | Lỗi biên dịch của view/PLSQL và các đối tượng tương ứng trong schema | Tìm lỗi sau khi biên dịch thất bại |
| **ALL_OBJECTS**, **DBA_OBJECTS** | Metadata đối tượng theo phạm vi truy cập | Phân tích trạng thái của đối tượng ngoài schema hiện tại |

### 2.1. Xem quan hệ trực tiếp

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type,
       dependency_type
FROM user_dependencies
WHERE name IN ('P_DEM_KH_ACTIVE', 'V_KH_ACTIVE')
ORDER BY name, referenced_owner, referenced_name;
~~~

Ý nghĩa các cột quan trọng:

- **NAME / TYPE**: tên và kiểu của đối tượng **đang phụ thuộc**.
- **REFERENCED_OWNER / REFERENCED_NAME / REFERENCED_TYPE**: schema, tên và kiểu của đối tượng **được tham chiếu**.
- **DEPENDENCY_TYPE**: thông tin về loại phụ thuộc do Oracle ghi nhận; không dùng một giá trị đơn lẻ để kết luận tác động của mọi DDL.

Procedure gọi DBMS_OUTPUT hoặc package hệ thống có thể xuất hiện thêm các quan hệ ngoài những đối tượng nghiệp vụ. Muốn tập trung vào chuỗi thực hành có thể thêm điều kiện REFERENCED_NAME tương ứng.

### 2.2. Tìm đối tượng phụ thuộc vào một bảng

~~~sql
SELECT name,
       type,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE referenced_name = 'KHACH_HANG_DEP'
ORDER BY name, type;
~~~

Kết quả này chủ yếu tìm **phụ thuộc trực tiếp**. Nếu procedure phụ thuộc view và view phụ thuộc bảng, truy vấn lọc theo tên bảng có thể chỉ thấy view, không tự đưa procedure vào kết quả.

Có thể truy vấn đồ thị phụ thuộc nhiều cấp với cú pháp phân cấp Oracle:

~~~sql
SELECT LEVEL AS muc_do,
       LPAD(' ', 2 * (LEVEL - 1)) || name AS doi_tuong_phu_thuoc,
       type,
       referenced_name AS phu_thuoc_vao,
       referenced_type
FROM user_dependencies
START WITH referenced_name = 'KHACH_HANG_DEP'
           AND referenced_type = 'TABLE'
CONNECT BY NOCYCLE
       PRIOR name = referenced_name
   AND PRIOR type = referenced_type
ORDER SIBLINGS BY name;
~~~

Với đồ thị ví dụ, tầng đầu là view tham chiếu bảng, tầng tiếp theo là procedure tham chiếu view. Một hệ thống lớn có thể có nhiều đường đến cùng một đối tượng hoặc chuỗi phụ thuộc dài; kết quả phải được đọc như **đường đi trong đồ thị**, không nhất thiết là một cây không trùng lặp. Khi có schema khác, cần sử dụng các trường OWNER/REFERENCED_OWNER và quyền view tương ứng để ghép chính xác, thay vì chỉ nối theo tên.

### 2.3. Kiểm tra trạng thái đối tượng

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_name IN (
    'KHACH_HANG_DEP',
    'V_KH_ACTIVE',
    'P_DEM_KH_ACTIVE'
)
ORDER BY object_type, object_name;
~~~

**STATUS = VALID** thường nghĩa là định nghĩa đã được Oracle xác nhận hợp lệ ở thời điểm metadata phản ánh. **STATUS = INVALID** báo đối tượng cần biên dịch/xác thực lại hoặc không thể dùng với định nghĩa hiện tại. Trạng thái này **không phải phép thử đầy đủ rằng mọi câu SQL nghiệp vụ hoặc dữ liệu runtime đều đúng**.

**LAST_DDL_TIME** cho biết thời điểm DDL liên quan đến đối tượng được ghi nhận; nó không có nghĩa lần cuối dữ liệu trong bảng thay đổi. Không dùng cột này làm timestamp của INSERT/UPDATE/DELETE.

## 3. Invalidation là gì?

**Invalidation** là cơ chế Oracle đánh dấu một đối tượng hoặc cấu trúc thực thi đang phụ thuộc vào metadata không còn được tin cậy nguyên trạng. Mục tiêu là ngăn hệ thống tiếp tục sử dụng định nghĩa, chữ ký, quyền hoặc execution plan đã lỗi thời sau thay đổi liên quan.

~~~text
Đối tượng tham chiếu đang thay đổi
                |
                v
Oracle đánh giá dependency và tác động của thay đổi
                |
       +--------+---------+
       |                  |
       v                  v
Không ảnh hưởng       Có ảnh hưởng hoặc cần xác minh lại
       |                  |
       v                  v
Tiếp tục dùng        Dependent object/cursor bị invalidation
                          |
                          v
               Khi biên dịch/thực thi lại
                  +-------+--------+
                  |                |
                  v                v
            Biên dịch được     Biên dịch thất bại
                  |                |
                  v                v
             VALID, chạy       INVALID hoặc lỗi
~~~

Không phải mọi DDL đều khiến toàn bộ những đối tượng trong đồ thị trở thành INVALID. Oracle có cơ chế **fine-grained dependency tracking** ở những trường hợp/phiên bản được hỗ trợ: hệ thống theo dõi chi tiết thành phần được sử dụng, ví dụ cột hoặc thành phần public của package, để giảm invalidation khi thay đổi không liên quan.

### 3.1. Những thay đổi có khả năng ảnh hưởng

| Thay đổi | Đối tượng có thể bị ảnh hưởng | Điểm cần hiểu |
| --- | --- | --- |
| Đổi tên hoặc xóa cột được view/procedure sử dụng | View, PL/SQL program unit và downstream dependents | Mã tham chiếu tên cột cũ không còn biên dịch được |
| DROP/RECREATE bảng hoặc view | Các đối tượng tham chiếu | Đối tượng nguồn biến mất hoặc định nghĩa mới khác đi |
| CREATE OR REPLACE VIEW | Các object sử dụng cột của view | Oracle đánh giá thay đổi định nghĩa giao diện của view |
| Thay đổi package specification | Các program unit gọi thành phần public có liên quan | Signature/interface thay đổi có thể yêu cầu biên dịch lại |
| Thay đổi package body | Bản thân body và phiên đang dùng package | Thường khác tác động của đổi spec; stateful package cần chú ý |
| REVOKE quyền trực tiếp cần để biên dịch/thực thi | Object của schema được cấp quyền | Sau thay đổi quyền, object có thể không biên dịch/chạy lại được |
| Đổi đối tượng đích của synonym | Mã hoặc truy vấn qua synonym | Việc phân giải tên và đối tượng đích có thể thay đổi |
| DDL thay index hoặc optimizer statistics | SQL cursor và kế hoạch thực thi | Cursor có thể invalidation/reparse; stored procedure không nhất thiết INVALID |

**UPDATE/INSERT/DELETE trên dữ liệu thông thường không phải là DDL thay đổi định nghĩa object**, nên không mặc nhiên làm view hoặc procedure trở thành INVALID. Chúng có thể ảnh hưởng kết quả truy vấn và đặc tính dữ liệu, nhưng cần tách điều này khỏi metadata dependency.

### 3.2. Fine-grained dependency: thay đổi nào thực sự liên quan?

Giả sử một procedure chỉ đọc cột **MA_KHACH_HANG** của bảng. Khi bảng được thêm cột mới không dùng tới, Oracle có thể tránh invalidating procedure nếu giao diện nó sử dụng không bị ảnh hưởng. Ngược lại, đổi tên hoặc xóa chính cột MA_KHACH_HANG là thay đổi trực tiếp liên quan.

Các trường hợp này không phải một luật tuyệt đối chỉ dựa trên loại ALTER TABLE. Tác động còn phụ thuộc hình thức tham chiếu (ví dụ SELECT * hay tham chiếu cột cụ thể), kiểu object, phiên bản Oracle và chi tiết thay đổi. Khi bảo trì, hãy dùng metadata và kiểm tra thực tế thay vì giả định mọi lệnh ADD COLUMN là an toàn cho tất cả dependent objects.

### 3.3. Cursor invalidation khác object INVALID

Một câu SELECT đã parse có thể có shared cursor trong library cache. Thay đổi cấu trúc bảng hoặc thống kê optimizer theo một số chính sách invalidation có thể khiến cursor đó cần **hard parse hoặc tối ưu lại**.

Đây là hiện tượng ở cấp cấu trúc thực thi SQL. Một stored procedure vẫn có thể là **VALID**, nhưng SQL bên trong cần cursor mới khi chạy tiếp. Ngược lại, một procedure có STATUS = INVALID có thể không biên dịch được vì thiếu cột hoặc quyền, dù một câu SELECT độc lập khác vẫn chạy bình thường.

Không lấy số hard parse làm số lượng stored object INVALID; cũng không lấy USER_OBJECTS.STATUS để suy ra mọi shared cursor của SQL vẫn còn được sử dụng.

## 4. Vòng đời VALID → INVALID → VALID

Đối tượng lưu trong Oracle như view hoặc PL/SQL unit có thể trải qua vòng đời:

1. **Tạo hoặc biên dịch thành công:** Oracle xác nhận định nghĩa, lưu phụ thuộc và đánh dấu trạng thái thích hợp là VALID.
2. **Đối tượng nguồn thay đổi:** Oracle xác định dependent nào không còn an toàn để dùng nguyên trạng và có thể invalidation.
3. **Được gọi lần tiếp theo:** Với nhiều PL/SQL unit, Oracle có thể cố **recompile tự động** trước khi thực thi.
4. **Biên dịch lại thành công:** Định nghĩa vẫn tương thích, object trở lại trạng thái VALID và được thực thi.
5. **Biên dịch lại thất bại:** Object tiếp tục INVALID hoặc người gọi nhận lỗi tương ứng; phải sửa định nghĩa, quyền hoặc đối tượng nguồn.

**INVALID không luôn có nghĩa mã nguồn đã bị xóa hay dữ liệu bảng bị hỏng.** Nó có thể là trạng thái tạm thời cần biên dịch lại sau DDL. Nhưng cũng không nên xem mọi INVALID là vô hại: nếu một cột đã bị xóa, tự recompile không thể khôi phục cú pháp không còn hợp lệ.

### 4.1. Các lỗi thường gặp

| Thông báo/mã lỗi | Gợi ý phân tích |
| --- | --- |
| **ORA-04063: view ... has errors** | View đang có lỗi biên dịch hoặc định nghĩa không còn hợp lệ |
| **ORA-06508: PL/SQL: could not find program unit being called** | Program unit cần gọi không sẵn sàng, có thể do invalidation/recompile thất bại |
| **ORA-04068: existing state of packages has been discarded** | Trạng thái của stateful package trong phiên bị hủy sau thay đổi/invalidation |
| **ORA-04061 / ORA-04065** | Lỗi liên quan trạng thái hoặc thay đổi của program unit/package |
| **ORA-00904: invalid identifier** | Tham chiếu tên cột hoặc biểu thức không hợp lệ, có thể sau rename/drop column |
| **ORA-00942: table or view does not exist** | Thiếu đối tượng hoặc quyền nhìn thấy đối tượng cần truy cập |
| **PLS-00302 / PLS-00306** | Thành phần package hoặc chữ ký lời gọi PL/SQL không phù hợp |

Mã lỗi thực tế có thể đi kèm nhau theo chuỗi, tùy thời điểm phát hiện, phiên bản Oracle và công cụ gọi. Một lỗi biên dịch sau DDL cần được đối chiếu **USER_ERRORS**, metadata object và thay đổi schema gần đây.

## 5. Bài thực hành: tạo đồ thị phụ thuộc có thể quan sát

Ví dụ dưới đây dùng **một schema sandbox còn trống**, nơi tài khoản có quyền **CREATE TABLE, CREATE VIEW, CREATE PROCEDURE**. Chạy theo thứ tự trên Oracle Database qua SQLcl, SQL*Plus hoặc một công cụ SQL hỗ trợ thực thi PL/SQL block. Không dùng tên những đối tượng đã có dữ liệu nghiệp vụ thực.

### 5.1. Tạo bảng, view và procedure

~~~sql
-- Bảng gốc.
CREATE TABLE khach_hang_dep (
    ma_khach_hang NUMBER(6) CONSTRAINT pk_khach_hang_dep PRIMARY KEY,
    ho_ten        VARCHAR2(100 CHAR) NOT NULL,
    trang_thai    VARCHAR2(10 CHAR) NOT NULL,
    CONSTRAINT ck_khach_hang_dep_tt
        CHECK (trang_thai IN ('ACTIVE', 'INACTIVE'))
);

INSERT INTO khach_hang_dep
    (ma_khach_hang, ho_ten, trang_thai)
VALUES (1, 'Nguyen An', 'ACTIVE');

INSERT INTO khach_hang_dep
    (ma_khach_hang, ho_ten, trang_thai)
VALUES (2, 'Tran Binh', 'INACTIVE');

INSERT INTO khach_hang_dep
    (ma_khach_hang, ho_ten, trang_thai)
VALUES (3, 'Le Chi', 'ACTIVE');

COMMIT;

-- View phụ thuộc trực tiếp vào bảng và cột TRANG_THAI.
CREATE OR REPLACE VIEW v_kh_active AS
SELECT ma_khach_hang, ho_ten
FROM khach_hang_dep
WHERE trang_thai = 'ACTIVE';

-- Procedure phụ thuộc trực tiếp vào view.
CREATE OR REPLACE PROCEDURE p_dem_kh_active AS
    v_dem NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_dem
    FROM v_kh_active;

    DBMS_OUTPUT.PUT_LINE('Khach active: ' || v_dem);
END;
/
~~~

Trong SQLcl/SQL*Plus, có thể bật phần hiển thị DBMS_OUTPUT:

~~~sql
SET SERVEROUTPUT ON

EXEC p_dem_kh_active;
~~~

Kết quả mong đợi là **Khach active: 2**. Dấu **/** cuối phần tạo procedure là lệnh của công cụ để gửi PL/SQL đi thực thi, không phải một phần của ngữ pháp PL/SQL. Khi dùng JDBC/Spring JDBC, công cụ gọi procedure và cách hiển thị output sẽ khác.

### 5.2. Xem dependency graph đã tạo

~~~sql
SELECT name, type, referenced_name, referenced_type
FROM user_dependencies
WHERE name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
  AND referenced_name IN ('KHACH_HANG_DEP', 'V_KH_ACTIVE')
ORDER BY name;
~~~

Quan hệ kỳ vọng:

| NAME | TYPE | REFERENCED_NAME | REFERENCED_TYPE |
| --- | --- | --- | --- |
| P_DEM_KH_ACTIVE | PROCEDURE | V_KH_ACTIVE | VIEW |
| V_KH_ACTIVE | VIEW | KHACH_HANG_DEP | TABLE |

Procedure còn có thể có dependency đến package hệ thống **DBMS_OUTPUT**; truy vấn đã lọc riêng hai quan hệ nghiệp vụ cho dễ quan sát.

Kiểm tra trạng thái:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'KHACH_HANG_DEP', 'V_KH_ACTIVE', 'P_DEM_KH_ACTIVE'
)
ORDER BY object_type, object_name;
~~~

Ở trạng thái ban đầu, các đối tượng được tạo thành công thường có STATUS **VALID**.

### 5.3. Thực hiện thay đổi phá vỡ một phụ thuộc

Để thấy invalidation một cách rõ ràng, đổi tên cột được dùng trong WHERE của view:

~~~sql
ALTER TABLE khach_hang_dep
    RENAME COLUMN trang_thai TO tinh_trang;
~~~

Dữ liệu của cột không bị xóa, nhưng view vẫn chứa điều kiện **WHERE TRANG_THAI = 'ACTIVE'**, trong khi cột này không còn tên đó. Oracle sẽ phải đánh giá lại định nghĩa view, và những object phụ thuộc có thể bị invalidation. Quan sát:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
ORDER BY object_name;
~~~

Với thay đổi trực tiếp làm mất tên cột được tham chiếu, view không còn biên dịch hợp lệ cho đến khi định nghĩa được sửa hoặc tên cột được khôi phục. Trạng thái của các dependent phía trên có thể phụ thuộc thời điểm Oracle lan truyền invalidation và thử biên dịch lại.

Thử truy vấn view hoặc gọi procedure:

~~~sql
SELECT COUNT(*) FROM v_kh_active;

EXEC p_dem_kh_active;
~~~

Các lệnh này **được dự kiến phát sinh lỗi**, không thuộc phần tạo dữ liệu chuẩn. Tùy điểm thất bại, Oracle có thể báo lỗi view invalid, invalid identifier hoặc lỗi program unit. Không lấy một mã lỗi cụ thể làm điều kiện duy nhất để kết luận.

Để xem lỗi biên dịch chi tiết, sau khi thử biên dịch view hoặc procedure:

~~~sql
ALTER VIEW v_kh_active COMPILE;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
ORDER BY name, sequence;
~~~

Lệnh ALTER VIEW COMPILE có thể báo warning/lỗi vì cột được tham chiếu đã không còn. Bảng USER_ERRORS giúp tìm vấn đề thực sự; không chỉ dựa vào thông báo SQL client.

### 5.4. Phục hồi nguồn rồi biên dịch lại

Trong schema sandbox này, đặt lại tên cột:

~~~sql
ALTER TABLE khach_hang_dep
    RENAME COLUMN tinh_trang TO trang_thai;

ALTER VIEW v_kh_active COMPILE;
ALTER PROCEDURE p_dem_kh_active COMPILE;
~~~

Sau đó:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
ORDER BY object_name;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('V_KH_ACTIVE', 'P_DEM_KH_ACTIVE')
ORDER BY name, sequence;

SELECT COUNT(*) AS so_khach_active
FROM v_kh_active;
~~~

Khi định nghĩa và quyền đã hợp lệ, **view/procedure có thể trở lại VALID**, và truy vấn view tiếp tục trả về **2**. Một số object có thể đã được Oracle tự biên dịch hợp lệ ở lần tham chiếu sau khi nguồn được sửa; các lệnh COMPILE tường minh ở đây giúp trình bày rõ thao tác bảo trì.

**ALTER TABLE là DDL có quy tắc implicit commit.** Không thực hiện các bước thay đổi cột như một phần của giao dịch ứng dụng chưa hoàn tất và kỳ vọng ROLLBACK hoàn tác toàn bộ DDL.

### 5.5. Dọn dữ liệu thực hành

Sau khi kết thúc và chắc chắn chỉ còn đối tượng sandbox do bài tập tạo:

~~~sql
DROP PROCEDURE p_dem_kh_active;
DROP VIEW v_kh_active;
DROP TABLE khach_hang_dep PURGE;
~~~

Xóa từ dependent xuống referenced object giúp quan sát thứ tự phụ thuộc rõ ràng. **PURGE** bỏ qua cơ chế lưu giữ thông thường của recycle bin; chỉ thực hiện khi dữ liệu thử nghiệm được phép xóa vĩnh viễn.

## 6. Package specification và package body: phụ thuộc giao diện

Đối với package PL/SQL, cần phân biệt:

- **Package specification (spec)**: phần công khai mô tả procedure/function, kiểu, hằng hoặc biến được client có thể tham chiếu.
- **Package body**: phần cài đặt các thành phần trong spec và thành phần private.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE pkg_quy_tac_dep AS
    FUNCTION nhan_doi(p_gia_tri IN NUMBER) RETURN NUMBER;
END pkg_quy_tac_dep;
/

CREATE OR REPLACE PACKAGE BODY pkg_quy_tac_dep AS
    FUNCTION nhan_doi(p_gia_tri IN NUMBER)
        RETURN NUMBER
    AS
    BEGIN
        RETURN p_gia_tri * 2;
    END nhan_doi;
END pkg_quy_tac_dep;
/

CREATE OR REPLACE PROCEDURE p_dung_quy_tac_dep AS
    v_ket_qua NUMBER;
BEGIN
    v_ket_qua := pkg_quy_tac_dep.nhan_doi(10);
    DBMS_OUTPUT.PUT_LINE('Ket qua: ' || v_ket_qua);
END p_dung_quy_tac_dep;
/
~~~

Procedure **P_DUNG_QUY_TAC_DEP** sử dụng public function của package. Nếu chỉ sửa phép tính bên trong **body**, giao diện của function vẫn như cũ và caller thường không cần thay mã nguồn. Nhưng package body mới vẫn phải hợp lệ và việc thay thế body có thể ảnh hưởng đến **trạng thái package** của các session đang dùng.

Nếu sửa **spec** theo cách đổi tên, xóa function hoặc thay chữ ký bắt buộc của function mà caller đang dùng, caller có thể bị invalidation và không biên dịch lại được cho tới khi được sửa. Cơ chế phụ thuộc chi tiết có thể tránh lan truyền invalidation từ những thay đổi public interface không liên quan; vì vậy không kết luận “mọi sửa spec đều invalid toàn bộ caller”.

Kiểm tra riêng metadata:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'PKG_QUY_TAC_DEP',
    'P_DUNG_QUY_TAC_DEP'
)
ORDER BY object_type;
~~~

Có thể thấy hai dòng **PACKAGE** và **PACKAGE BODY** cho cùng tên package. Khi lỗi ở body, kiểm tra đúng loại lỗi/đối tượng:

~~~sql
SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'PKG_QUY_TAC_DEP'
ORDER BY type, sequence;
~~~

Biên dịch thủ công theo phạm vi cần thiết:

~~~sql
ALTER PACKAGE pkg_quy_tac_dep COMPILE SPECIFICATION;
ALTER PACKAGE pkg_quy_tac_dep COMPILE BODY;
ALTER PROCEDURE p_dung_quy_tac_dep COMPILE;
~~~

Các lệnh trên chỉ phù hợp khi các đối tượng đã tồn tại; không dùng việc recompile hàng loạt để che lỗi giao diện chưa được xử lý. Sau thực hành, có thể xóa procedure rồi package khi chắc chắn không còn cần sử dụng.

### 6.1. Stateful package và ORA-04068

Package có biến hoặc trạng thái tồn tại qua nhiều lời gọi trong một session có thể trở thành **stateful package**. Nếu package đang được session sử dụng mà bị thay thế/invalidation, Oracle có thể phải hủy trạng thái cũ; khi gọi tiếp, ứng dụng có thể gặp chuỗi lỗi liên quan, nổi bật là **ORA-04068**.

Trường hợp này đặc biệt quan trọng với **Java connection pool**, vì nhiều JDBC connection vật lý giữ session Oracle lâu hơn một HTTP request. Một session đã có trạng thái package trước deployment có thể nhận lỗi ở lần gọi sau, dù session mới không gặp lỗi.

Giải pháp không phải là “bắt lỗi rồi bỏ qua mọi trường hợp”. Cần xác định có phụ thuộc package state hay không, thiết kế khả năng khởi tạo lại phù hợp, điều phối thời điểm deployment/connection pool và quyết định retry theo tính an toàn của tác vụ. Những giao dịch ghi có kết quả chưa rõ cần được kiểm tra trước khi thử lại.

## 7. Quyền truy cập và đối tượng khác schema

Phụ thuộc giữa hai schema còn đi kèm **privilege dependency**. Giả sử schema APP_OWNER sở hữu bảng, còn schema REPORT_APP tạo view hoặc procedure đọc bảng đó.

Một DBA hoặc chủ sở hữu đối tượng có thể cấp quyền trực tiếp:

~~~sql
-- Ví dụ minh họa, chỉ chạy khi schema/tài khoản tồn tại
-- và người chạy có quyền cấp tương ứng.
GRANT SELECT ON app_owner.don_hang TO report_app;
~~~

Khi REPORT_APP tạo stored PL/SQL unit tham chiếu đối tượng schema khác, **quyền cần cho SQL tĩnh trong definer-rights PL/SQL phải được cấp trực tiếp phù hợp**, không thể mặc định dựa vào role đang bật trong phiên tương tác. Trường hợp invoker-rights với AUTHID CURRENT_USER có thêm quy tắc về quyền khi biên dịch/chạy; cần kiểm tra quyền của owner và invoker theo đúng thiết kế.

Nếu quyền trực tiếp cần thiết bị **REVOKE**, đối tượng đã biên dịch có thể bị invalidation hoặc không còn chạy/biên dịch lại được. Khi chẩn đoán, phân biệt:

1. Đối tượng nguồn vẫn tồn tại nhưng caller **không đủ quyền**.
2. Đối tượng nguồn đã đổi tên hoặc bị xóa.
3. Synonym vẫn tồn tại nhưng đối tượng đích hoặc quyền trên đích không còn phù hợp.
4. SQL động có thể thất bại runtime dù metadata dependency không báo đường tham chiếu trực tiếp.

Một synonym là **bí danh cho đối tượng**; nó không tạo bản sao độc lập của bảng/procedure và không tự cấp quyền truy cập. Thay đổi hoặc xóa synonym có thể ảnh hưởng mã sử dụng tên đó, tùy kiểu tham chiếu và cách Oracle phân giải đối tượng.

### 7.1. Cách tra cứu đa schema

Trong phạm vi có quyền thích hợp, có thể truy vấn:

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM all_dependencies
WHERE referenced_owner = 'APP_OWNER'
  AND referenced_name = 'DON_HANG'
ORDER BY owner, name;
~~~

**ALL_DEPENDENCIES** chỉ cho thấy những đối tượng người gọi được phép thấy; nó không đảm bảo đầy đủ toàn bộ database. Khi cần đánh giá tác động đầy đủ giữa mọi schema, DBA có thể dùng **DBA_DEPENDENCIES**, metadata quyền và mã của các ứng dụng liên quan.

## 8. Dependency tracking không bao phủ tất cả ảnh hưởng

Một ứng dụng có thể phụ thuộc vào Oracle ngoài những mối quan hệ được data dictionary của stored object ghi nhận.

| Loại phụ thuộc | Có thể được dictionary ghi nhận trực tiếp? | Phương pháp bổ sung |
| --- | --- | --- |
| View SELECT trực tiếp bảng | Thường có | USER_DEPENDENCIES / ALL_DEPENDENCIES |
| Procedure gọi package tĩnh | Thường có | Dependency view, package spec và errors |
| Procedure dùng EXECUTE IMMEDIATE với tên bảng biến đổi | Không thể mặc định liệt kê đầy đủ từ compile-time dependencies | Phân tích code, cấu hình và SQL thực thi |
| Java JDBC gửi SELECT tới bảng | Không là một stored object dependency của schema | Tìm trong source code, repository, query logs/observability |
| Báo cáo bên ngoài dùng cùng một view | Không phải luôn là dependent stored object ở Oracle | Catalog của công cụ báo cáo, contract/API, kiểm thử tích hợp |
| Materialized view | Có quan hệ nguồn, đồng thời có trạng thái refresh/staleness riêng | Xem metadata mview và cơ chế refresh |
| Database link đến đối tượng từ xa | Có cơ chế phân giải/dependency riêng | Kiểm tra quyền và metadata cả hai database |

Một **materialized view** có thể có trạng thái dữ liệu **STALE** vì chưa refresh, trong khi tình trạng này không đồng nghĩa trực tiếp với STATUS = INVALID của view thường. Tương tự, stored procedure VALID không chứng minh mọi SQL động trong procedure đều thực thi được với mọi đầu vào.

Khi thay đổi schema, phải kết hợp **dependency metadata**, **phân tích SQL tĩnh/động** và **kiểm thử caller bên ngoài**, nhất là ứng dụng Java/Spring Boot.

## 9. Recompilation thủ công và tự động

Oracle có thể tự động thử biên dịch lại stored object invalid khi cần dùng. Tuy nhiên, tự động recompile có thể tăng độ trễ request đầu tiên sau triển khai, và nếu định nghĩa không còn hợp lệ thì request vẫn thất bại.

Với đối tượng cụ thể:

~~~sql
ALTER VIEW v_kh_active COMPILE;
ALTER PROCEDURE p_dem_kh_active COMPILE;
ALTER PACKAGE pkg_quy_tac_dep COMPILE BODY;
~~~

Sau đó kiểm tra STATUS và USER_ERRORS. Không nên chỉ nhìn thông báo “Statement processed” hoặc coi một lệnh COMPILE đã chạy xong là toàn bộ đồ thị phụ thuộc hợp lệ.

Trong những hệ thống có nhiều object INVALID, Oracle có các tiện ích phục vụ recompilation theo schema/database mà DBA có thể sử dụng khi thích hợp. Việc chạy recompile hàng loạt có thể tốn CPU và tạo tranh chấp; phải phân tích nguyên nhân trước. Nếu object INVALID vì đã xóa cột được tham chiếu, biên dịch lại bao nhiêu lần cũng không thay thế việc cập nhật mã.

### 9.1. Thứ tự xử lý theo đồ thị

Với chuỗi:

~~~text
TABLE -> VIEW -> PROCEDURE -> APPLICATION
~~~

Khi sửa một lỗi phụ thuộc, thứ tự hợp lý là:

1. Sửa hoặc khôi phục **đối tượng gốc** (bảng/cột/quyền).
2. Biên dịch hoặc kiểm tra **view**.
3. Biên dịch hoặc kiểm tra **procedure/package**.
4. Thử **caller** trong ứng dụng và quan sát kết quả nghiệp vụ.

Đây là thứ tự tư duy để sửa nguyên nhân, không có nghĩa phải bắt buộc gọi COMPILE thủ công cho từng object sau mọi DDL. Oracle có thể tự revalidate một số object khi được sử dụng.

## 10. Quy trình đánh giá thay đổi schema trước deployment

Một thay đổi ALTER TABLE nhỏ trong migration có thể tác động nhiều service. Để tránh phát hiện vấn đề sau khi traffic đã chuyển sang bản mới, cần quản lý việc đổi schema như một thay đổi **contract** giữa các đối tượng.

**Bước 1 — Xác định đối tượng và giao diện thay đổi.** Tên bảng/view/package nào đổi? Đụng đúng cột, kiểu dữ liệu, constraint, public function hay chỉ thêm một thành phần mới?

**Bước 2 — Truy xuất dependent trực tiếp và gián tiếp.** Dùng USER_DEPENDENCIES, ALL_DEPENDENCIES hoặc DBA_DEPENDENCIES tùy quyền. Ghi nhận cả schema chủ sở hữu và referenced owner.

**Bước 3 — Xem các phụ thuộc bên ngoài database.** Tìm SQL trong Java repository, ORM mapping, batch job, report, migration và dynamic SQL. Những phụ thuộc này có thể không xuất hiện trong USER_DEPENDENCIES.

**Bước 4 — Phân loại tác động.** Đổi tên/xóa cột dùng trực tiếp có nguy cơ cao. Thêm cột mới không dùng tới thường ít ảnh hưởng hơn nhưng vẫn cần xét SELECT *, view, trigger và khả năng phụ thuộc đặc biệt.

**Bước 5 — Chuẩn bị khả năng chuyển đổi tương thích.** Có thể chọn hướng *expand–migrate–contract*: thêm cấu trúc mới, triển khai code đọc/ghi tương thích, chuyển dữ liệu, rồi chỉ xóa tên/cột cũ khi caller đã chuyển hết. Khi phù hợp, cân nhắc các cơ chế editioning của Oracle nhưng chỉ sau khi đánh giá giới hạn đối tượng và vận hành của phiên bản đang dùng.

**Bước 6 — Thực hiện migration và biên dịch.** Chạy DDL có kiểm soát, xử lý trực tiếp lỗi định nghĩa, kiểm tra USER_OBJECTS và USER_ERRORS. Với package có state, cân nhắc session cũ và connection pool.

**Bước 7 — Kiểm thử contract.** Chạy SQL của view/procedure, API Java, batch và trường hợp giao dịch quan trọng. Một object VALID chỉ chứng minh biên dịch hợp lệ ở phạm vi nhất định; nó không bảo đảm nghiệp vụ vẫn đúng.

**Bước 8 — Quan sát sau triển khai.** Xem số object INVALID, lỗi ORA-04063/06508/04068, số lần parse và latency request đầu tiên. Chuẩn bị rollback/roll-forward theo khả năng của DDL và migration, không dựa vào ROLLBACK giao dịch SQL thông thường.

## 11. Chẩn đoán một sự cố invalidation

Giả sử sau deployment, API Java nhận lỗi khi gọi procedure P_DEM_KH_ACTIVE. Có thể làm theo thứ tự:

### 11.1. Xác định đối tượng đang INVALID

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

Không nhất thiết mọi object INVALID đều liên quan tới API. Lọc đúng schema và dependency chain trước khi sửa.

### 11.2. Lấy lỗi biên dịch

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
ORDER BY name, sequence;
~~~

Nếu procedure báo lỗi gọi view, hãy kiểm tra chính view và đối tượng nguồn. Một lỗi downstream có thể là hậu quả, không phải nguyên nhân gốc.

### 11.3. Truy tìm đối tượng nguồn

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE name = 'P_DEM_KH_ACTIVE'
ORDER BY referenced_owner, referenced_name;
~~~

Tiếp tục kiểm tra referenced view và bảng. Nếu mã lỗi là thiếu quyền, kiểm tra quyền được cấp trực tiếp và thay đổi GRANT/REVOKE. Nếu lỗi do không có cột, so sánh định nghĩa hiện tại của bảng/view với phiên bản migration trước.

### 11.4. Sửa rồi xác nhận đến tầng ứng dụng

Khôi phục tên đối tượng/kiểu dữ liệu/quyền hoặc cập nhật mã dependent, biên dịch lại khi cần, rồi chạy chính lời gọi mà ứng dụng Java sử dụng. Nếu dùng connection pool với stateful package, kiểm soát phiên đã tồn tại trước deployment. Nếu có giao dịch ghi bị lỗi ở giữa luồng xử lý, xác minh trạng thái commit trước khi tự động retry.

## 12. Các nhầm lẫn dễ gặp

**“Bất kỳ thay đổi DDL nào trên bảng đều làm INVALID mọi procedure dùng bảng.”** Không đúng. Fine-grained dependency tracking có thể tránh invalidation khi thay đổi không liên quan đến thành phần đã sử dụng.

**“Object INVALID đồng nghĩa dữ liệu bên trong bảng bị hỏng.”** Không đúng. INVALID là trạng thái metadata/biên dịch hoặc khả năng sử dụng một đối tượng, không phải kết luận về tính toàn vẹn dữ liệu.

**“Compile thành công có nghĩa toàn bộ nghiệp vụ đúng.”** Không đúng. Biên dịch kiểm tra định nghĩa và phụ thuộc mà Oracle có thể xác định; SQL động, dữ liệu runtime và caller Java vẫn cần kiểm thử.

**“USER_DEPENDENCIES liệt kê mọi truy vấn từ ứng dụng Java.”** Không đúng. Java JDBC gửi SQL từ bên ngoài database; không trở thành một stored schema object dependency chỉ vì đã chạy SELECT.

**“Thay package body luôn buộc mọi caller recompile.”** Không thể khẳng định. Phụ thuộc vào spec/interface khác với phần cài đặt body; nhưng thay package body có thể ảnh hưởng package state ở session đã sử dụng.

**“Đổi tên cột chỉ ảnh hưởng một bảng.”** Không đúng. View, procedure, SQL động, ORM mapping và các integration phía trên có thể dùng tên cũ.

**“Procedure VALID thì shared SQL cursor chắc chắn không reparse.”** Không đúng. SQL cursor có lifecycle và điều kiện invalidation riêng, không đồng nhất với STATUS của stored procedure.

**“Mọi lỗi ORA-04068 có thể retry ngay.”** Không an toàn khi lời gọi tác động dữ liệu có thể đã tạo thay đổi hoặc trạng thái giao dịch chưa rõ. Cần hiểu package state và tính idempotent.

**“Chỉ cần cấp quyền qua role để PL/SQL definer-rights compile.”** Không đúng với SQL tĩnh yêu cầu quyền trực tiếp trong các stored definer-rights units. Phân quyền theo đúng chủ sở hữu và loại program unit.

## 13. Bài tập tự luyện

1. Vẽ đồ thị gồm TABLE KHACH_HANG, VIEW V_KH_ACTIVE, PROCEDURE P_DEM_KH_ACTIVE. Xác định direct và indirect dependency của procedure.
2. Thực hiện phần 5 và ghi nhận kết quả USER_DEPENDENCIES trước khi đổi tên cột, sau khi đổi tên và sau khi khôi phục tên. Những view nào thể hiện trạng thái và lỗi biên dịch?
3. Một view chỉ đọc cột MA_KHACH_HANG. Bảng được thêm cột MO_TA. Có thể kết luận chắc chắn view sẽ INVALID không? Vì sao cần xét fine-grained dependencies?
4. Một procedure sử dụng EXECUTE IMMEDIATE với tên bảng từ biến. Vì sao phân tích USER_DEPENDENCIES có thể bỏ sót tác động của đổi tên bảng?
5. Một package có function công khai tinh_thue(p NUMBER). Thay đổi công thức bên trong body và đổi tên function trong spec khác nhau ở điểm nào?
6. Thay package body trong production khiến một số connection JDBC gặp ORA-04068. Vì sao chỉ các session có state từ trước có thể bị ảnh hưởng khác với session mới?
7. Một object INVALID do mất quyền SELECT trên bảng của schema khác. Chạy COMPILE nhiều lần có sửa được không? Cần khôi phục điều kiện nào?
8. Vì sao SQL cursor phải hard parse lại sau thay đổi cấu trúc không đồng nghĩa stored procedure chứa SQL ấy đã INVALID?
9. Khi đổi tên cột được ứng dụng Java tham chiếu, vì sao USER_DEPENDENCIES không đủ để cho phép xóa cột cũ ngay?
10. Soạn kế hoạch triển khai an toàn cho việc đổi cột TRANG_THAI thành TINH_TRANG khi có view, package và nhiều phiên bản service Java đang hoạt động song song.

Mối quan hệ phụ thuộc giúp Oracle bảo vệ tính nhất quán giữa **định nghĩa đối tượng được tham chiếu** và **đối tượng đang sử dụng chúng**. Invalidation là tín hiệu phải kiểm tra hoặc biên dịch lại sau thay đổi có liên quan; automatic recompilation chỉ thành công khi nguồn và quyền vẫn tương thích. Sử dụng data dictionary kết hợp phân tích ứng dụng và kiểm thử sau migration sẽ giúp thay đổi schema mà không vô tình làm đứt chuỗi phụ thuộc của hệ thống.
