# Private synonym, public synonym và rủi ro phân giải sai đối tượng trong Oracle

Trong một hệ thống Oracle, bảng và view thường nằm trong schema của một nhóm hoặc một ứng dụng. Ứng dụng khác vẫn có thể cần truy cập chúng mà không muốn ghi lặp tên schema dài trong mọi câu SQL. Synonym cung cấp một tên thay thế cho một đối tượng database. Nhờ đó, ứng dụng có thể tham chiếu một bảng qua tên ngắn hoặc một tên ổn định dù đối tượng thật nằm ở schema khác.

Oracle có hai loại synonym chính:

- **Private synonym:** được tạo trong một schema cụ thể, phục vụ cách đặt tên trong phạm vi schema đó.
- **Public synonym:** được tạo trong schema đặc biệt PUBLIC, cung cấp một tên dùng chung để các schema có thể tham chiếu.

Synonym chỉ là lớp định danh. Nó không tạo bản sao của bảng, không chuyển quyền sở hữu, không tự cấp quyền SELECT/INSERT/UPDATE/DELETE và cũng không làm thay đổi quyền trên đối tượng đích. Nếu một synonym trỏ tới sai đối tượng, một câu SQL vẫn có thể chạy thành công nhưng đọc hoặc sửa nhầm dữ liệu. Đây là rủi ro quan trọng khi hệ thống dùng nhiều schema, public synonym, CURRENT_SCHEMA hoặc tên không ghi rõ owner.

Sau bài học, bạn có thể:

- Giải thích synonym là gì và phân biệt private với public synonym.
- Tạo, thay thế, tra cứu và xóa synonym bằng SQL.
- Hiểu cách Oracle phân giải tên không ghi schema và vai trò của CURRENT_SCHEMA.
- Nhận biết khi đối tượng cục bộ che khuất public synonym.
- Phân biệt lỗi synonym không hợp lệ, target không tồn tại, thiếu quyền và synonym chain bị vòng.
- Hiểu synonym không cấp quyền, không thay thế schema qualification và không bảo đảm đối tượng đích luôn đúng.
- Dùng data dictionary để kiểm tra owner, target, database link và trạng thái tham chiếu.
- Quản lý synonym trong môi trường dev/test/prod, migration, dependency và database link.
- Giảm rủi ro truy vấn nhầm bảng bằng quy tắc đặt tên, kiểm tra quyền và schema qualification.

> Các ví dụ dùng schema giả định HR, APP và SALES. Bạn cần thay tên theo schema thực tế và có quyền tương ứng. Tên đối tượng trong ví dụ chỉ minh họa; không mặc định schema HR hoặc các bảng mẫu tồn tại trong database của bạn.

## 1. Synonym là gì?

Synonym là một tên thay thế (alias) cho một đối tượng database. Synonym lưu thông tin đối tượng mà nó trỏ tới, gồm owner, tên đối tượng và có thể có database link.

Ví dụ, bảng EMPLOYEES thuộc schema HR. Schema APP được cấp quyền đọc bảng này:

```sql
GRANT SELECT ON hr.employees TO app;
```

Người dùng APP có thể tạo private synonym:

```sql
CREATE SYNONYM employees
FOR hr.employees;
```

Sau đó truy vấn:

```sql
SELECT employee_id, first_name, last_name
FROM employees;
```

Oracle phân giải tên EMPLOYEES thành synonym trong schema APP rồi chuyển tham chiếu tới HR.EMPLOYEES. Dữ liệu vẫn nằm trong bảng HR.EMPLOYEES; synonym không chứa hàng dữ liệu.

### 1.1. Synonym không phải view

| Đặc điểm | Synonym | View |
| --- | --- | --- |
| Bản chất | Tên thay thế cho đối tượng khác | Đối tượng lưu định nghĩa truy vấn SELECT |
| Lưu dữ liệu riêng | Không | View thường không lưu dữ liệu; materialized view có lưu kết quả |
| Biến đổi cột/hàng | Không | Có thể chọn cột, join, lọc hoặc biểu diễn phép tính |
| Quyền | Không tự cấp quyền trên target | Có cơ chế quyền trên view và underlying objects theo quy tắc Oracle |
| Mục đích | Đơn giản hóa tên và che giấu vị trí/owner | Cung cấp giao diện dữ liệu qua truy vấn |

Synonym không thể thêm WHERE, đổi tên cột hoặc che một cấu trúc dữ liệu phức tạp như view. Nếu cần giới hạn hàng/cột theo chính sách truy cập, hãy xem xét view hoặc cơ chế bảo mật phù hợp; synonym không phải lớp kiểm soát dữ liệu.

### 1.2. Những loại đối tượng có thể được synonym trỏ tới

Synonym thường được dùng cho table, view, sequence, procedure, function, package, materialized view, object type và một số loại đối tượng schema khác mà Oracle cho phép tham chiếu bằng synonym. Synonym cũng có thể trỏ tới đối tượng từ xa qua database link.

Synonym không phải cách đặt alias cho một schema, tablespace hay một câu SELECT tùy ý. Đối tượng đích phải phù hợp với loại tham chiếu mà câu lệnh SQL/PLSQL đang dùng.

### 1.3. Synonym có thể được tạo trước khi target tồn tại

Oracle cho phép tạo synonym tham chiếu tới một đối tượng chưa tồn tại hoặc hiện chưa truy cập được. Việc CREATE SYNONYM thành công vì vậy không chứng minh target đã tồn tại hay người dùng có quyền trên target.

Khi sử dụng synonym, Oracle mới cần phân giải đối tượng đích và kiểm tra quyền. Nếu target thiếu hoặc tham chiếu không hợp lệ, câu SQL có thể thất bại dù synonym vẫn có trong dictionary. Luôn xác minh target sau khi tạo và trong bước triển khai.

## 2. Private synonym

Private synonym thuộc một schema cụ thể. Nó giúp schema đó dùng một tên thay thế cho target mà không phải lặp tên owner trong từng câu SQL.

### 2.1. Tạo private synonym trong schema hiện tại

Giả sử đang kết nối bằng user APP và user này có quyền SELECT trên HR.EMPLOYEES:

```sql
CREATE SYNONYM employees
FOR hr.employees;
```

Truy vấn qua synonym:

```sql
SELECT employee_id, first_name
FROM employees;
```

Tương đương về target với:

```sql
SELECT employee_id, first_name
FROM hr.employees;
```

Private synonym không làm cho người dùng APP sở hữu bảng HR.EMPLOYEES. Owner của bảng vẫn là HR.

### 2.2. Tạo private synonym trong schema khác

Một user có quyền CREATE ANY SYNONYM có thể tạo private synonym trong schema khác:

```sql
CREATE SYNONYM app.employee_directory
FOR hr.employees;
```

Quyền này có phạm vi rộng và cần được cấp có kiểm soát. Nếu chỉ tạo synonym trong schema của chính mình, quyền CREATE SYNONYM thường là đủ.

### 2.3. Private synonym có thể trỏ tới đối tượng cùng schema hoặc schema khác

Synonym không bắt buộc target phải ở schema khác:

```sql
CREATE SYNONYM active_orders
FOR app.orders;
```

Ví dụ trên tạo một tên thay thế cho APP.ORDERS. Cách này có thể hữu ích nếu muốn tên trong ứng dụng ít phụ thuộc vào tên vật lý, nhưng không nên tạo alias dư thừa nếu nó làm người đọc khó biết target thực sự là gì.

### 2.4. Quyền tạo và xóa private synonym

| Thao tác | Quyền thường cần |
| --- | --- |
| Tạo synonym trong schema của mình | CREATE SYNONYM |
| Tạo synonym trong schema khác | CREATE ANY SYNONYM |
| Xóa synonym trong schema của mình | Chủ sở hữu synonym |
| Xóa synonym trong schema khác | DROP ANY SYNONYM |

Chủ sở hữu synonym có thể xóa synonym của chính mình bằng DROP SYNONYM. Để xóa synonym trong schema khác cần quyền DROP ANY SYNONYM. Quyền quản trị mạnh như ANY privilege nên chỉ cấp khi thật sự cần.

Xóa private synonym:

```sql
DROP SYNONYM employees;
```

Nếu synonym thuộc schema khác và được phép xóa:

```sql
DROP SYNONYM app.employee_directory;
```

DROP SYNONYM chỉ xóa tên thay thế. Nó không xóa bảng, view, sequence hoặc procedure mà synonym trỏ tới.

## 3. Public synonym

Public synonym được tạo trong schema đặc biệt PUBLIC. Nó cung cấp một tên chung để nhiều schema có thể tham chiếu cùng một target mà không cần mỗi schema tự tạo private synonym.

### 3.1. Tạo public synonym

Giả sử HR.EMPLOYEES là bảng dùng chung:

```sql
CREATE PUBLIC SYNONYM employees
FOR hr.employees;
```

Sau khi tạo, các schema có thể viết:

```sql
SELECT employee_id, first_name
FROM employees;
```

Tuy nhiên, câu SELECT chỉ thành công nếu người dùng thực thi có quyền cần thiết trên HR.EMPLOYEES. Public synonym không cấp SELECT cho mọi người.

### 3.2. Quyền tạo và xóa public synonym

| Thao tác | Quyền |
| --- | --- |
| Tạo public synonym | CREATE PUBLIC SYNONYM |
| Xóa public synonym | DROP PUBLIC SYNONYM |

Đây là các quyền hệ thống có phạm vi rộng. Trong môi trường doanh nghiệp, thường chỉ DBA hoặc một tài khoản triển khai được ủy quyền mới nên quản lý public synonym.

Xóa public synonym:

```sql
DROP PUBLIC SYNONYM employees;
```

Lệnh này chỉ xóa synonym có tên EMPLOYEES trong PUBLIC; nó không xóa HR.EMPLOYEES.

### 3.3. Public synonym không có nghĩa là public data

Ba khái niệm cần tách biệt:

1. **Public synonym:** cung cấp tên có thể phân giải rộng rãi.
2. **Object privilege:** cho phép một user SELECT, INSERT, UPDATE, DELETE hoặc EXECUTE trên target.
3. **System privilege/role:** quyền thực hiện một loại hành động hoặc quản lý một phạm vi đối tượng.

Một public synonym có thể tồn tại và được nhìn thấy bởi user không có quyền đọc bảng đích. Khi user đó SELECT qua synonym, Oracle vẫn kiểm tra quyền trên target và từ chối nếu thiếu.

Ví dụ:

```sql
CREATE PUBLIC SYNONYM payroll_data
FOR hr.payroll;

-- User APP không tự nhiên có quyền đọc HR.PAYROLL.
-- DBA/owner cần cấp quyền phù hợp nếu APP được phép:
GRANT SELECT ON hr.payroll TO app;
```

Không dùng public synonym như một cơ chế chia sẻ dữ liệu hoặc thay thế GRANT.

## 4. Private synonym và public synonym khác nhau thế nào?

| Tiêu chí | Private synonym | Public synonym |
| --- | --- | --- |
| Schema sở hữu | Schema cụ thể | PUBLIC |
| Phạm vi tên | Thuộc namespace của schema đó | Tên dùng chung toàn database |
| Quyền tạo | CREATE SYNONYM; hoặc CREATE ANY SYNONYM để tạo trong schema khác | CREATE PUBLIC SYNONYM |
| Quyền xóa | Chủ sở hữu hoặc DROP ANY SYNONYM theo phạm vi | DROP PUBLIC SYNONYM |
| Tác động khi đổi target | Ảnh hưởng các câu lệnh dùng private synonym đó | Có thể ảnh hưởng nhiều schema đang dùng tên chung |
| Khả năng xung đột | Với đối tượng cùng namespace trong schema sở hữu | Có thể bị tên cục bộ che khuất khi phân giải không ghi schema |
| Quản trị | Thường do chủ schema/ứng dụng quản lý | Thường cần quản trị tập trung |

### 4.1. Khi nào dùng private synonym?

Private synonym phù hợp khi:

- Một ứng dụng cần tên ngắn cho bảng ở schema dữ liệu khác.
- Mỗi schema ứng dụng cần ánh xạ tên riêng tới một target riêng.
- Muốn triển khai dev/test/prod với tên logic giống nhau nhưng target khác nhau, có kiểm soát theo môi trường.
- Muốn tránh tạo một tên dùng chung ảnh hưởng toàn database.

Ví dụ, APP_DEV.ORDERS và APP_TEST.ORDERS có thể là private synonym trỏ tới các schema dữ liệu khác nhau. Cần đảm bảo cấu hình môi trường không bị nhầm khi deploy.

### 4.2. Khi nào dùng public synonym?

Public synonym phù hợp khi một đối tượng thực sự cần tên chung cho nhiều schema, và DBA có quy trình quản trị tập trung:

- Một package hoặc view tiện ích dùng chung.
- Một đối tượng có tên ổn định, được nhiều ứng dụng tham chiếu.
- Tương thích với ứng dụng cũ phụ thuộc tên không ghi schema.

Không tạo public synonym cho mọi bảng chỉ để giảm số ký tự SQL. Mỗi public synonym làm tăng bề mặt tên toàn database, có thể che khuất lỗi thiếu schema qualification và làm việc chuyển đổi target khó kiểm soát.

## 5. Oracle phân giải tên synonym như thế nào?

Rủi ro lớn nhất của synonym thường không nằm ở câu lệnh CREATE mà ở câu SQL không ghi rõ schema. Khi gặp tên không qualified, Oracle phải xác định tên đó đại diện cho object nào trong ngữ cảnh session hiện tại.

### 5.1. Tên không ghi schema

Với tham chiếu như:

```sql
SELECT *
FROM employees;
```

Oracle tìm tên trong schema hiện tại (CURRENT_SCHEMA), bao gồm đối tượng cục bộ hoặc private synonym phù hợp. Nếu không tìm thấy tên cục bộ, Oracle có thể tìm public synonym cùng tên. Khi synonym được tìm thấy, Oracle tiếp tục phân giải target mà synonym chỉ tới và kiểm tra quyền truy cập target.

Có thể ghi nhớ luồng khái niệm:

```text
Tên không ghi schema: EMPLOYEES
             |
             v
      CURRENT_SCHEMA
             |
       Có tên phù hợp?
          /       \
        Có         Không
        |            |
        v            v
  Dùng object/   Tìm PUBLIC synonym
  private synonym      |
                       v
                Có synonym phù hợp?
                  /          \
                Có            Không
                |               |
                v               v
          Phân giải target   Tên không được
          và kiểm tra quyền  phân giải
```

Đây là mô hình khái niệm cho tên object không qualified; cú pháp cụ thể và ngữ cảnh PL/SQL có thể có quy tắc phân giải riêng. Khi cần chắc chắn target, ghi rõ owner và object name.

### 5.2. Object cục bộ che khuất public synonym

Giả sử DBA tạo:

```sql
CREATE PUBLIC SYNONYM employees
FOR hr.employees;
```

APP có thể truy vấn tên EMPLOYEES qua public synonym nếu được cấp SELECT trên HR.EMPLOYEES. Sau này, nếu một bảng hoặc view tên EMPLOYEES được tạo trong schema APP, câu:

```sql
SELECT *
FROM employees;
```

trong APP sẽ tham chiếu đối tượng cục bộ đó. Public synonym không còn là đối tượng được chọn cho tên không qualified này.

Đây là một dạng shadowing (che khuất tên). Ứng dụng có thể vẫn chạy nhưng đọc bảng APP.EMPLOYEES thay vì HR.EMPLOYEES. Nếu hai bảng có cấu trúc tương tự, lỗi có thể không lộ ra ngay mà chỉ làm kết quả nghiệp vụ sai.

### 5.3. Private synonym và object trong schema

Private synonym nằm trong namespace của schema sở hữu. Các object cùng namespace không thể được tạo trùng tên trong cùng schema. Vì vậy, nếu APP đã có private synonym EMPLOYEES, APP không thể đồng thời tạo một table/view cùng tên trong namespace đó; ngược lại, nếu table EMPLOYEES đã tồn tại, không thể tạo private synonym trùng tên.

Public synonym nằm ở namespace PUBLIC nên có thể trùng tên với object trong một schema. Object cục bộ được ưu tiên khi tên không ghi schema được phân giải trong schema đó.

### 5.4. Dùng schema qualification để chỉ rõ target

So sánh:

```sql
-- Phụ thuộc vào CURRENT_SCHEMA và synonym resolution:
SELECT employee_id FROM employees;

-- Chỉ rõ owner và object:
SELECT employee_id FROM hr.employees;
```

Tên HR.EMPLOYEES bỏ qua một synonym cùng tên trong schema APP hoặc public synonym EMPLOYEES. Nếu HR.EMPLOYEES bản thân là synonym thì Oracle tiếp tục phân giải synonym đó; qualification làm rõ schema chứa tên được tra cứu, không nhất thiết bảo đảm đối tượng cuối cùng là table vật lý.

Với câu lệnh quan trọng về tài chính, payroll, quyền truy cập hoặc migration, nên ghi rõ schema trong SQL để tránh phụ thuộc vào public synonym hay cấu hình session.

## 6. CURRENT_SCHEMA và SESSION_USER

Oracle có nhiều khái niệm schema/user gần nhau nhưng không đồng nghĩa:

- SESSION_USER: user đã xác thực và mở session.
- CURRENT_SCHEMA: schema mặc định được dùng khi phân giải tên không ghi owner.
- CURRENT_USER: danh tính hiện hành trong một số ngữ cảnh bảo mật/PLSQL; có thể khác SESSION_USER khi chạy code với quyền definer.

### 6.1. Kiểm tra ngữ cảnh session

```sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

Ví dụ APP có thể đặt schema mặc định:

```sql
ALTER SESSION SET CURRENT_SCHEMA = hr;
```

Sau đó tên không ghi schema như EMPLOYEES được tìm trong HR trước. SESSION_USER vẫn là APP. Thay CURRENT_SCHEMA không đăng nhập thành HR, không chuyển quyền sở hữu và không cấp thêm quyền trên HR. APP vẫn chỉ được làm những việc mà quyền của APP cho phép.

### 6.2. Vì sao CURRENT_SCHEMA có thể gây bất ngờ?

Một connection pool có thể tái sử dụng session. Nếu request trước chạy:

```sql
ALTER SESSION SET CURRENT_SCHEMA = reporting;
```

nhưng không khôi phục schema mặc định, request tiếp theo có thể phân giải cùng một câu SQL sang schema REPORTING thay vì APP. Đây là lỗi cấu hình session có thể gây đọc/ghi nhầm dữ liệu.

Nếu ứng dụng thay CURRENT_SCHEMA theo tenant hoặc schema ứng dụng:

- Đặt schema trong một điểm khởi tạo session rõ ràng.
- Khôi phục schema trước khi trả connection về pool.
- Không giả định mỗi request nhận một session mới.
- Kiểm tra CURRENT_SCHEMA trong log chẩn đoán khi kết quả khác nhau giữa các connection.
- Dùng schema qualification cho câu SQL nhạy cảm.

### 6.3. CURRENT_SCHEMA không phải cơ chế bảo mật

Đổi CURRENT_SCHEMA chỉ đổi nơi Oracle bắt đầu tìm tên không qualified. Nó không cho phép user đọc dữ liệu schema đó nếu chưa được cấp quyền. Không dùng ALTER SESSION SET CURRENT_SCHEMA để thay cho GRANT, role, VPD hoặc các cơ chế phân quyền.

## 7. Synonym chain và lỗi phân giải

Synonym có thể trỏ tới một synonym khác. Khi đó Oracle phải đi qua nhiều bước để tìm target cuối cùng. Cách này đôi khi xuất hiện trong hệ thống legacy, nhưng làm tăng độ phức tạp khi kiểm tra.

### 7.1. Chuỗi synonym hợp lệ

Ví dụ:

```sql
CREATE SYNONYM app.employee_alias
FOR hr.employee_directory;

CREATE SYNONYM hr.employee_directory
FOR hr.employees;
```

Về mặt tên, APP.EMPLOYEE_ALIAS dẫn tới HR.EMPLOYEE_DIRECTORY rồi tới HR.EMPLOYEES. Mỗi tầng có thể được thay đổi độc lập, nên khi debug cần lần theo toàn bộ chuỗi chứ không dừng ở synonym đầu tiên.

Trong ví dụ này cần có quyền tạo synonym ở các schema tương ứng; câu lệnh thứ hai chạy trong HR hoặc bởi tài khoản có CREATE ANY SYNONYM.

### 7.2. Synonym target không tồn tại hoặc không còn hợp lệ

Synonym có thể vẫn tồn tại sau khi target bị DROP hoặc đổi tên. Khi câu SQL dùng synonym, Oracle không thể hoàn tất việc phân giải target. Một lỗi thường gặp là:

```text
ORA-00980: synonym translation is no longer valid
```

Kiểm tra:

1. Synonym còn tồn tại không?
2. TABLE_OWNER và TABLE_NAME có đúng không?
3. Target có tồn tại trong schema được chỉ định không?
4. Target có bị đổi tên hoặc drop trong deployment gần đây không?
5. Nếu có DB_LINK, database link và đối tượng remote còn hoạt động không?

ORA-00942 (table or view does not exist) cũng có thể xuất hiện khi target không tồn tại hoặc user không có quyền truy cập. Không kết luận ngay rằng bảng đã bị xóa chỉ từ thông báo này; cần kiểm tra owner, object và privilege.

### 7.3. Synonym chain bị vòng

Ví dụ:

```sql
CREATE SYNONYM app.a FOR app.b;
CREATE SYNONYM app.b FOR app.a;
```

Hai synonym tham chiếu vòng lại nhau. Khi Oracle lần theo chuỗi, nó không tìm được target cuối cùng. Lỗi điển hình:

```text
ORA-01775: looping chain of synonyms
```

Không tạo synonym chain nhiều tầng nếu không có lý do rõ ràng. Một private synonym trỏ thẳng tới object cuối thường dễ kiểm soát hơn.

### 7.4. Synonym không tự cập nhật khi target đổi

Synonym lưu tên target. Nếu bảng HR.EMPLOYEES được đổi tên, synonym không tự đoán bảng mới để trỏ tới. Cần migration có kiểm soát:

1. Xác định synonym và code đang phụ thuộc.
2. Tạo target mới hoặc đổi tên theo kế hoạch.
3. Cập nhật/recreate synonym.
4. Kiểm tra quyền trên target mới.
5. Compile/validate object phụ thuộc nếu cần.
6. Chạy smoke test từ schema ứng dụng.

Không dùng CREATE OR REPLACE synonym như một thay đổi vô hại: đổi target có thể làm cùng một câu SQL truy cập một tập dữ liệu khác.

## 8. Tạo, thay thế và xóa synonym

### 8.1. CREATE SYNONYM

Private synonym trong schema hiện tại:

```sql
CREATE SYNONYM order_header
FOR sales.orders;
```

Private synonym trong schema được chỉ định (cần CREATE ANY SYNONYM nếu không phải owner):

```sql
CREATE SYNONYM app.order_header
FOR sales.orders;
```

Public synonym:

```sql
CREATE PUBLIC SYNONYM order_header
FOR sales.orders;
```

### 8.2. CREATE OR REPLACE SYNONYM

Khi synonym đã tồn tại và cần đổi target, có thể dùng OR REPLACE:

```sql
CREATE OR REPLACE SYNONYM order_header
FOR sales.orders_v2;
```

Với public synonym:

```sql
CREATE OR REPLACE PUBLIC SYNONYM order_header
FOR sales.orders_v2;
```

OR REPLACE thay định nghĩa synonym cùng tên. Nó không đổi tên bảng đích, không di chuyển dữ liệu và không cấp quyền trên target mới. Sau khi thay target, kiểm tra lại privilege, cột mà ứng dụng mong đợi và các dependent object. Một thay đổi synonym có thể làm cùng câu SQL truy cập một đối tượng khác.

### 8.3. DROP SYNONYM và DROP PUBLIC SYNONYM

Xóa private synonym:

```sql
DROP SYNONYM order_header;
```

Xóa public synonym:

```sql
DROP PUBLIC SYNONYM order_header;
```

Các lệnh DROP chỉ xóa alias. Chúng không xóa target. Nếu ứng dụng phụ thuộc synonym bị xóa, câu SQL không qualified có thể không còn phân giải được hoặc chuyển sang một tên khác (ví dụ public synonym cùng tên).

### 8.4. Không có ALTER SYNONYM để sửa target

Để đổi target, dùng CREATE OR REPLACE SYNONYM hoặc DROP rồi CREATE lại. Chọn cách thay thế có kiểm soát trong migration. CREATE OR REPLACE thường giúp tránh khoảng thời gian tên synonym hoàn toàn không tồn tại, nhưng vẫn cần xác minh dependent code và target sau thay đổi.

## 9. Synonym trỏ tới đối tượng qua database link

Synonym có thể trỏ tới object trong database từ xa thông qua database link:

```sql
CREATE SYNONYM remote_customers
FOR crm.customers@crm_link;
```

Ứng dụng có thể tham chiếu:

```sql
SELECT customer_id, customer_name
FROM remote_customers;
```

Oracle dùng database link CRM_LINK để kết nối database từ xa và truy cập CRM.CUSTOMERS. Synonym chỉ lưu tên tham chiếu; nó không tạo database link, không kiểm tra mạng và không cấp quyền ở database remote.

### 9.1. Điều kiện để truy vấn thành công

- Database link tồn tại và hợp lệ trong ngữ cảnh user đang chạy.
- Tên service/host và thông tin kết nối remote đúng.
- Database từ xa sẵn sàng.
- Tài khoản remote có quyền trên object CRM.CUSTOMERS.
- Object remote còn tồn tại và schema/column phù hợp.
- Network ACL, wallet hoặc cấu hình kết nối (nếu áp dụng) cho phép truy cập.

Nếu synonym có DB_LINK nhưng link bị drop hoặc remote database không sẵn sàng, câu SQL sẽ lỗi dù synonym local vẫn tồn tại.

### 9.2. Private và public database link

Database link cũng có phạm vi riêng:

- Private database link thuộc schema tạo nó.
- Public database link có thể được dùng rộng hơn theo quyền và cấu hình database.

Đừng nhầm public synonym với public database link. Một public synonym có thể tham chiếu database link, nhưng điều đó không tự biến database link private thành public và cũng không chia sẻ thông tin đăng nhập remote cho mọi user.

### 9.3. Rủi ro khi public synonym trỏ tới remote system

Public synonym tới database link có thể khiến nhiều ứng dụng phụ thuộc vào một remote service. Khi remote đổi endpoint, credential hoặc cấu trúc bảng, nhiều schema cùng bị ảnh hưởng.

Nên:

- Dùng tên synonym có ý nghĩa và thể hiện nguồn dữ liệu.
- Quản lý quyền tạo/xóa database link tập trung.
- Theo dõi trạng thái remote dependency.
- Có smoke test kết nối và truy vấn sau mỗi lần triển khai.
- Không đặt thông tin nhạy cảm vào script/log hoặc chia sẻ database link ngoài phạm vi được phép.

## 10. Tra cứu synonym trong data dictionary

Oracle cung cấp các view dictionary để tra cứu synonym. Tên bảng trong dictionary thường được lưu dạng chữ hoa nếu không tạo bằng quoted identifier.

### 10.1. USER_SYNONYMS

Liệt kê synonym thuộc schema hiện tại:

```sql
SELECT
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM user_synonyms
ORDER BY synonym_name;
```

Các cột quan trọng:

| Cột | Ý nghĩa |
| --- | --- |
| SYNONYM_NAME | Tên alias |
| TABLE_OWNER | Owner của object được trỏ tới (nếu được chỉ định) |
| TABLE_NAME | Tên object target |
| DB_LINK | Database link nếu target nằm ở database từ xa |

USER_SYNONYMS tập trung vào synonym do schema hiện tại sở hữu; public synonym không thuộc schema user nên cần xem view phù hợp khác.

### 10.2. ALL_SYNONYMS

Liệt kê synonym mà user có thể thấy theo phạm vi view:

```sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM all_synonyms
WHERE synonym_name = 'EMPLOYEES'
ORDER BY owner;
```

Public synonym thường có OWNER là PUBLIC. Kết quả cũng có thể có private synonym thuộc schema khác mà user được thấy theo metadata visibility. Hãy xem cả OWNER và target, không chỉ nhìn tên synonym.

### 10.3. DBA_SYNONYMS

DBA_SYNONYMS cho phép quản trị viên xem toàn bộ synonym trong database:

```sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM dba_synonyms
ORDER BY owner, synonym_name;
```

View DBA_ thường yêu cầu quyền từ điển phù hợp. Nếu user ứng dụng không truy cập được, có thể dùng ALL_SYNONYMS hoặc nhờ DBA cung cấp thông tin theo quy trình.

### 10.4. Tìm synonym cùng tên trên nhiều owner

Khi câu SQL phân giải bất ngờ, truy vấn tất cả synonym có cùng tên:

```sql
SELECT
    owner,
    synonym_name,
    table_owner,
    table_name,
    db_link
FROM all_synonyms
WHERE synonym_name = UPPER(:name_to_find)
ORDER BY
    CASE WHEN owner = SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')
         THEN 1
         WHEN owner = 'PUBLIC'
         THEN 2
         ELSE 3
    END,
    owner;
```

Thứ tự ở đây chỉ giúp người đọc ưu tiên xem synonym thuộc CURRENT_SCHEMA và PUBLIC. Nó không phải một bản sao đầy đủ của thuật toán name resolution cho mọi loại câu lệnh.

### 10.5. Kiểm tra target có tồn tại trong schema local

Với target local:

```sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE owner = UPPER(:target_owner)
  AND object_name = UPPER(:target_name)
ORDER BY object_type;
```

ALL_OBJECTS có thể cho biết object tồn tại và trạng thái INVALID/VALID khi loại object có trạng thái đó. Với target remote, cần truy vấn metadata ở database từ xa qua link nếu có quyền, hoặc kiểm tra trực tiếp tại hệ thống remote.

## 11. Dependency và tác động khi đổi synonym

Synonym tạo một lớp tên trung gian. Các view, procedure, function, package hoặc câu SQL ứng dụng có thể dựa vào tên đó. Thay target có thể ảnh hưởng cấu trúc cột, quyền và hành vi của code phụ thuộc.

### 11.1. Tìm object phụ thuộc

Các view dependency trong schema có thể giúp điều tra:

```sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE referenced_name = UPPER(:synonym_or_target_name)
ORDER BY type, name;
```

Nếu cần phạm vi toàn database và có quyền, DBA có thể dùng DBA_DEPENDENCIES. Kết quả cần được diễn giải theo object name và referenced owner/type; synonym chain hoặc code dynamic SQL có thể khiến việc tìm dependency không đơn giản.

### 11.2. Static SQL và dynamic SQL

- Static SQL trong PL/SQL được phân tích khi compile và có metadata dependency phù hợp.
- Dynamic SQL (EXECUTE IMMEDIATE) được phân giải khi chạy; dependency có thể không được thể hiện đầy đủ như static SQL.
- Ứng dụng Java/JDBC gửi SQL text khi chạy cũng cần được tìm trong code/config/log, không chỉ dựa vào data dictionary.

Vì vậy, kiểm tra USER_DEPENDENCIES là một nguồn thông tin hữu ích nhưng không phải danh sách đầy đủ mọi nơi dùng synonym.

### 11.3. Quy trình đổi target an toàn

Trước khi chạy CREATE OR REPLACE SYNONYM:

1. Tra cứu synonym hiện tại và ghi lại target cũ.
2. Tìm object phụ thuộc và các câu SQL ứng dụng dùng tên alias.
3. Xác nhận target mới có đúng cấu trúc, dữ liệu và owner.
4. Xác nhận quyền trực tiếp cần thiết trên target mới.
5. Thử synonym mới trong schema dev/test.
6. Lên lịch thay đổi, cập nhật synonym và validate dependent code.
7. Chạy smoke test bằng đúng user/role/session context của ứng dụng.
8. Theo dõi lỗi ORA-00942, ORA-00980, ORA-01775 và lỗi quyền sau deploy.
9. Giữ phương án rollback về target cũ nếu kiểm tra sau triển khai không đạt.

Không thay synonym production trỏ sang bảng khác chỉ vì hai bảng có cùng tên cột. Cần xác nhận semantics, dữ liệu, trigger, constraint, transaction behavior và quyền.

## 12. Synonym và quyền truy cập

Synonym chỉ giải quyết việc đặt tên. Quyền vẫn được kiểm tra trên object đích.

### 12.1. Cấp quyền trên target

Ví dụ HR sở hữu bảng EMPLOYEES và APP cần đọc:

```sql
GRANT SELECT ON hr.employees TO app;
```

APP tạo private synonym:

```sql
CREATE SYNONYM employees FOR hr.employees;
```

APP có thể viết:

```sql
SELECT employee_id, first_name
FROM employees;
```

Nếu bỏ GRANT nhưng vẫn tạo được synonym, câu SELECT không tự thành công. Lỗi có thể hiển thị như object không tồn tại/không có quyền tùy ngữ cảnh; cần kiểm tra privilege trên target.

### 12.2. Synonym không phải lớp che giấu object

Tên alias ngắn không làm target trở nên bí mật. Metadata có thể cho biết owner và target; người dùng có quyền trên target vẫn truy cập theo tên schema-qualified nếu biết tên.

Không dùng synonym để:

- Che giấu schema nhạy cảm.
- Thay thế GRANT/REVOKE.
- Tạo ranh giới tenant.
- Giới hạn hàng hoặc cột.
- Cấp quyền cho người dùng chỉ vì họ nhìn thấy public synonym.

Nếu cần kiểm soát hàng/cột, xem xét view, VPD/FGAC, Database Vault hoặc cơ chế bảo mật phù hợp với kiến trúc và phiên bản Oracle.

### 12.3. Quyền trực tiếp trong definer-rights PL/SQL

Một package/procedure chạy với quyền DEFINER có quy tắc privilege khác với SQL chạy trực tiếp trong session. Khi compile và chạy static SQL trong definer-rights PL/SQL, owner của program unit cần được cấp trực tiếp các object privilege cần thiết; quyền chỉ nhận thông qua role thường không đủ cho việc compile/execute code definer-rights.

Tạo synonym trong schema của package owner không thay thế GRANT trực tiếp trên target. Khi gặp lỗi quyền chỉ trong PL/SQL dù SELECT tương tự chạy được ở SQL worksheet, hãy kiểm tra AUTHID, owner của program unit và direct grants.

### 12.4. Public synonym có thể mở rộng bề mặt sử dụng

Public synonym làm tên target dễ được tham chiếu từ nhiều schema. Nếu target nhạy cảm, hãy cân nhắc private synonym hoặc schema qualification và chỉ cấp quyền cho user cần thiết. Không tạo public synonym cho object chỉ vì một ứng dụng cụ thể muốn tên ngắn.

## 13. Rủi ro phân giải sai đối tượng và cách giảm thiểu

### 13.1. Cùng câu SQL, target khác nhau theo session

Một câu SQL:

```sql
SELECT COUNT(*) FROM orders;
```

có thể trỏ tới APP.ORDERS trong session có CURRENT_SCHEMA là APP, nhưng trỏ tới REPORTING.ORDERS trong session có CURRENT_SCHEMA là REPORTING. Nếu các schema có object cùng tên, code không qualified có thể cho kết quả khác nhau mà không phát sinh lỗi cú pháp.

### 13.2. Public synonym bị che bởi object cục bộ

DBA tạo public synonym ORDERS trỏ tới SALES.ORDERS. Ứng dụng đang dùng public synonym. Một migration sau đó tạo bảng APP.ORDERS để lưu dữ liệu tạm. Câu SQL không ghi schema trong APP bắt đầu đọc APP.ORDERS. Đây là một thay đổi hành vi dù không sửa câu SELECT ban đầu.

Trước khi tạo object mới, kiểm tra tên public synonym cùng tên:

```sql
SELECT owner, synonym_name, table_owner, table_name
FROM all_synonyms
WHERE synonym_name = UPPER(:new_object_name);
```

Đồng thời kiểm tra object local:

```sql
SELECT object_name, object_type
FROM user_objects
WHERE object_name = UPPER(:new_object_name);
```

### 13.3. Synonym bị thay target trong lúc ứng dụng đang chạy

Nếu public synonym hoặc private synonym được CREATE OR REPLACE, các session tiếp theo dùng tên đó có thể phân giải sang target mới. Một ứng dụng có thể gặp:

- Cột không còn tồn tại.
- Kiểu dữ liệu khác.
- Dữ liệu thuộc tenant hoặc môi trường khác.
- Quyền thiếu trên target mới.
- Trigger/constraint hoặc semantics khác.
- Kế hoạch thực thi khác do object mới có index/statistics khác.

Hãy coi việc đổi target là một thay đổi API/schema contract và triển khai như một migration có kiểm thử.

### 13.4. Tên gần giống và quoted identifier

Oracle thường chuyển tên không đặt trong dấu nháy kép sang chữ hoa. Tên tạo bằng quoted identifier có thể phân biệt hoa/thường:

```sql
CREATE SYNONYM "EmployeeAlias"
FOR hr.employees;
```

Khi đó cách tham chiếu phải giữ đúng cách viết có quote:

```sql
SELECT * FROM "EmployeeAlias";
```

Tên quoted có thể gây khó khăn cho code generator, ORM, migration và thao tác dictionary. Thực hành phổ biến là dùng tên không quote, nhất quán với quy ước chữ hoa/chữ thường của Oracle.

### 13.5. Môi trường dev/test/prod

Một lỗi triển khai nguy hiểm là synonym trong TEST vô tình trỏ tới PROD, hoặc synonym trong PROD trỏ về schema test. Cần kiểm tra mapping theo môi trường:

| Môi trường | Schema ứng dụng | Target mong muốn |
| --- | --- | --- |
| DEV | APP_DEV | DATA_DEV |
| TEST | APP_TEST | DATA_TEST |
| PROD | APP | DATA |

Không hard-code endpoint production vào script dùng chung nếu script được chạy ở nhiều môi trường. Dùng biến triển khai/configuration có kiểm soát, nhưng log ra target thực tế để người vận hành xác nhận.

### 13.6. Nguyên tắc giảm rủi ro

- Ghi rõ owner trong SQL nhạy cảm.
- Dùng private synonym khi chỉ một ứng dụng cần alias.
- Hạn chế public synonym và quyền CREATE/DROP PUBLIC SYNONYM.
- Không tạo synonym chain dài hoặc vòng.
- Không thay target ngoài migration có kiểm soát.
- Kiểm tra CURRENT_SCHEMA trong connection pool.
- Kiểm tra dictionary sau deploy.
- Kiểm thử bằng đúng user, role, schema context và database link của ứng dụng.
- Ghi log target và phiên bản cấu hình khi điều tra sự cố.

## 14. Bài thực hành: quan sát private/public synonym và shadowing

Các bước sau cần quyền tạo schema object và synonym. Dùng schema thử nghiệm; không tạo object tên phổ biến trong schema dùng chung.

### 14.1. Tạo bảng target

Chạy bằng user DATA_OWNER (hoặc schema thử nghiệm tương đương):

```sql
CREATE TABLE lab_departments (
    department_id NUMBER(4) PRIMARY KEY,
    department_name VARCHAR2(80) NOT NULL
);

INSERT INTO lab_departments VALUES (10, 'Engineering');
INSERT INTO lab_departments VALUES (20, 'Finance');
COMMIT;
```

Cấp quyền đọc cho user ứng dụng APP:

```sql
GRANT SELECT ON data_owner.lab_departments TO app;
```

### 14.2. Tạo private synonym trong APP

Kết nối bằng APP:

```sql
CREATE SYNONYM departments
FOR data_owner.lab_departments;

SELECT department_id, department_name
FROM departments
ORDER BY department_id;
```

Kết quả phải có Engineering và Finance. Kiểm tra synonym:

```sql
SELECT synonym_name, table_owner, table_name
FROM user_synonyms
WHERE synonym_name = 'DEPARTMENTS';
```

### 14.3. Tạo public synonym cùng tên

DBA hoặc user có quyền CREATE PUBLIC SYNONYM:

```sql
CREATE PUBLIC SYNONYM departments
FOR data_owner.lab_departments;
```

Nếu APP đã có private synonym cùng tên, APP tiếp tục dùng private synonym của mình. Public synonym là fallback khi không có tên phù hợp trong schema hiện tại.

### 14.4. Quan sát shadowing bằng object cục bộ

Trong schema APP, private synonym DEPARTMENTS đang chiếm tên trong namespace đó nên không thể tạo table trùng tên. Để quan sát public synonym bị che, hãy dùng một tên khác chỉ có public synonym:

DBA:

```sql
CREATE PUBLIC SYNONYM shared_departments
FOR data_owner.lab_departments;
```

APP:

```sql
SELECT department_id, department_name
FROM shared_departments;
```

Sau đó tạo bảng APP.SHARED_DEPARTMENTS trong schema test:

```sql
CREATE TABLE shared_departments (
    department_id NUMBER(4),
    department_name VARCHAR2(80)
);

INSERT INTO shared_departments
VALUES (99, 'Local test object');
COMMIT;
```

Chạy lại:

```sql
SELECT department_id, department_name
FROM shared_departments;
```

Kết quả giờ là hàng Local test object trong APP.SHARED_DEPARTMENTS. Câu SQL không đổi nhưng object cục bộ được ưu tiên hơn public synonym.

So sánh với truy vấn ghi rõ schema:

```sql
SELECT department_id, department_name
FROM data_owner.lab_departments;
```

Truy vấn này vẫn đọc hai hàng từ DATA_OWNER.LAB_DEPARTMENTS.

### 14.5. Khôi phục môi trường test

Xóa object cục bộ trước:

```sql
DROP TABLE shared_departments;
```

Nếu không cần public synonym nữa, DBA xóa:

```sql
DROP PUBLIC SYNONYM shared_departments;
DROP PUBLIC SYNONYM departments;
```

APP có thể xóa private synonym:

```sql
DROP SYNONYM departments;
```

Không xóa DATA_OWNER.LAB_DEPARTMENTS trong khi còn bài thực hành khác cần dùng.

## 15. Bảng tra cứu lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| ORA-00942 | Target không tồn tại hoặc user không có quyền | Kiểm tra owner, object, GRANT và database link |
| ORA-00980 | Synonym translation không còn hợp lệ | Kiểm tra target name, owner, object đã đổi tên/drop và DB link |
| ORA-01775 | Synonym chain bị vòng | Lần theo TABLE_OWNER/TABLE_NAME và sửa chuỗi |
| ORA-01031 | Thiếu quyền thực hiện thao tác hoặc truy cập target | Kiểm tra CREATE/DROP SYNONYM privilege và object privilege |
| CREATE SYNONYM báo object name đã dùng | Private synonym/table/view cùng namespace đã tồn tại | Tra USER_OBJECTS và USER_SYNONYMS |
| SELECT trả dữ liệu schema khác | Public synonym bị che, CURRENT_SCHEMA thay đổi hoặc target sai | Kiểm tra CURRENT_SCHEMA, local object và ALL_SYNONYMS |
| Synonym tồn tại nhưng SELECT thất bại | Synonym không cấp quyền trên target | Kiểm tra GRANT trực tiếp và quyền remote |
| PL/SQL lỗi quyền nhưng SQL worksheet chạy | Definer-rights code thiếu direct grant hoặc owner khác | Kiểm tra AUTHID và privilege trực tiếp cho owner |
| Synonym remote không chạy | DB link, network, credential hoặc remote object lỗi | Kiểm tra DB link và truy vấn trực tiếp từ database remote |
| Sau deploy code chạy sai bảng | CREATE OR REPLACE đổi target hoặc synonym mapping sai môi trường | So sánh target trước/sau, kiểm tra smoke test |

## 16. Nguyên tắc thực hành tốt

1. **Xem synonym là alias tên.** Nó không phải bảng, view bảo mật hay cơ chế cấp quyền.
2. **Định nghĩa rõ target.** Dùng owner.object trong các câu SQL nhạy cảm và trong tài liệu triển khai.
3. **Ưu tiên private synonym cho nhu cầu cục bộ.** Chỉ tạo public synonym khi thật sự cần tên chung toàn database.
4. **Giữ quyền quản trị public synonym ở phạm vi nhỏ.** CREATE/DROP PUBLIC SYNONYM có thể ảnh hưởng nhiều ứng dụng.
5. **Kiểm tra local object trước khi dựa vào public synonym.** Object cục bộ có thể che khuất public synonym cùng tên.
6. **Kiểm tra CURRENT_SCHEMA trong connection pool.** Đặt và khôi phục session context có quy tắc.
7. **Không dùng synonym để thay GRANT.** Người dùng cần quyền trên object đích.
8. **Tránh synonym chain và circular reference.** Trỏ thẳng tới target cuối nếu có thể.
9. **Kiểm tra target sau khi CREATE/OR REPLACE.** CREATE thành công không chứng minh target tồn tại hoặc truy cập được.
10. **Quản lý synonym như một phần của migration.** Ghi nhận target cũ/mới, dependent code và kế hoạch rollback.
11. **Đối chiếu đúng môi trường.** DEV/TEST/PROD phải trỏ đúng schema và database link.
12. **Kiểm tra bằng đúng user ứng dụng.** Quyền DBA có thể làm một truy vấn thành công dù user thật không có quyền.
13. **Dùng dictionary để điều tra.** Xem USER_SYNONYMS, ALL_SYNONYMS, DBA_SYNONYMS và dependency phù hợp.
14. **Không lạm dụng quoted identifier.** Quy ước tên nhất quán giúp giảm lỗi phân giải và migration.

## 17. Câu hỏi tự kiểm tra

1. Synonym là gì và nó có lưu dữ liệu của target không?
2. Private synonym khác public synonym ở schema sở hữu và phạm vi tên như thế nào?
3. Vì sao public synonym không tự cấp quyền SELECT cho mọi user?
4. Quyền nào cần để tạo private synonym trong schema hiện tại?
5. Quyền nào cần để tạo synonym trong schema khác?
6. Quyền nào cần để tạo và xóa public synonym?
7. Nếu APP có table EMPLOYEES và PUBLIC có synonym EMPLOYEES, câu SELECT không ghi schema trong APP đọc object nào?
8. CURRENT_SCHEMA khác SESSION_USER như thế nào?
9. Vì sao connection pool cần quản lý CURRENT_SCHEMA cẩn thận?
10. Schema qualification HR.EMPLOYEES giải quyết được loại mơ hồ nào?
11. Vì sao CREATE SYNONYM có thể thành công dù target chưa tồn tại?
12. ORA-00980 khác ORA-00942 như thế nào?
13. ORA-01775 thường chỉ ra vấn đề gì?
14. Synonym chain có thể làm việc debug khó hơn như thế nào?
15. USER_SYNONYMS, ALL_SYNONYMS và DBA_SYNONYMS khác nhau về phạm vi ra sao?
16. DB_LINK trong USER_SYNONYMS cho biết điều gì?
17. Vì sao synonym không thay thế direct grant cho definer-rights PL/SQL?
18. Vì sao CREATE OR REPLACE SYNONYM cần được xem như migration có tác động?
19. Một public synonym trỏ tới remote object có phụ thuộc những thành phần nào?
20. Những bước nào giúp xác nhận ứng dụng đang truy cập đúng target sau deploy?

## 18. Mô hình ghi nhớ

```text
                 SYNONYM
                    |
          Tên thay thế cho object
                    |
          +---------+----------+
          |                    |
          v                    v
    PRIVATE SYNONYM       PUBLIC SYNONYM
    Một schema             Schema PUBLIC
    Phạm vi cục bộ         Tên dùng chung
          |                    |
          +---------+----------+
                    |
                    v
             NAME RESOLUTION
                    |
          CURRENT_SCHEMA trước
          PUBLIC synonym sau
                    |
                    v
             TARGET OBJECT
                    |
          Kiểm tra object privilege
          và database link nếu có
                    |
                    v
               SQL THỰC THI

RỦI RO
  - Local object che public synonym
  - CURRENT_SCHEMA khác dự kiến
  - Target bị drop/rename
  - Synonym chain bị vòng
  - Thiếu quyền trên target
  - Mapping DEV/TEST/PROD sai

GIẢM RỦI RO
  - Schema qualification
  - Private synonym theo nhu cầu
  - Quản lý public synonym tập trung
  - Kiểm tra dictionary và dependency
  - Smoke test bằng user ứng dụng
```

**Điểm cần nhớ:** private synonym và public synonym chỉ cung cấp tên thay thế. Oracle phân giải tên không qualified dựa trên schema hiện tại trước khi xét public synonym; object cục bộ có thể che khuất tên public. Synonym không cấp quyền và không bảo đảm target còn đúng. Hãy kiểm tra CURRENT_SCHEMA, owner/target trong dictionary, quyền trên object đích và mọi dependency trước khi triển khai hoặc thay synonym.
