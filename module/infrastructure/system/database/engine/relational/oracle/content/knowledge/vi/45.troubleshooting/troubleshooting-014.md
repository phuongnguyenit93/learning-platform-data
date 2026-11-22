# ORA-04063, ORA-06508, ORA-04068 và đối tượng PL/SQL/trạng thái package

Oracle Database lưu procedure, function, package, trigger, view và nhiều đối tượng PL/SQL dưới dạng stored program unit. Trước khi chạy, các đối tượng này phải được biên dịch thành công và có trạng thái hợp lệ. Khi source code tham chiếu đến object không tồn tại, thiếu quyền, sai chữ ký hoặc có lỗi cú pháp, Oracle có thể đánh dấu đối tượng là INVALID. Lời gọi đến đối tượng không hợp lệ hoặc không thể nạp được có thể dẫn đến các lỗi như ORA-04063 và ORA-06508.

Một nhóm lỗi khác liên quan đến trạng thái package trong từng session. Package có thể giữ biến toàn cục, cursor và dữ liệu trạng thái trong bộ nhớ của session. Khi package bị recompile hoặc invalidated, trạng thái đã tạo trong các session có thể bị loại bỏ. Lần gọi tiếp theo từ một session từng khởi tạo package có thể nhận ORA-04068.

Ba lỗi cần phân biệt:

- **ORA-04063**: đối tượng được tham chiếu có lỗi, ví dụ package body hoặc view có lỗi biên dịch. Cần tìm lỗi gốc trong USER_ERRORS/ALL_ERRORS và dependency.
- **ORA-06508**: PL/SQL không tìm thấy program unit có thể thực thi tại thời điểm gọi. Đối tượng có thể không tồn tại, không hợp lệ, không thể nạp hoặc dependency của nó đang lỗi.
- **ORA-04068**: trạng thái hiện có của package trong session đã bị loại bỏ. Đây thường là sự kiện invalidation/recompilation của package stateful; không đồng nghĩa package hiện tại chắc chắn vẫn INVALID.

Điều tra đúng cần xem cả trạng thái object trong data dictionary, lỗi biên dịch, dependency, quyền truy cập và session nào đã khởi tạo package. Chỉ chạy COMPILE rồi kết luận xong có thể bỏ sót lỗi dependency hoặc các session trong connection pool vẫn giữ trạng thái cũ.

## 1. Package specification, package body và trạng thái object

Package là đơn vị gom các procedure, function, type, cursor, exception, constant và biến dùng chung. Package thường gồm hai phần:

- **Package specification (spec)** khai báo giao diện công khai: procedure/function nào có thể gọi, kiểu dữ liệu, constant, type và biến public.
- **Package body** chứa phần triển khai procedure/function, biến private, cursor, helper subprogram và khối initialization nếu có.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE app.order_api AS
  PROCEDURE mark_paid(
    p_order_id IN NUMBER,
    p_status   OUT VARCHAR2
  );

  FUNCTION get_total(
    p_order_id IN NUMBER
  ) RETURN NUMBER;
END order_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY app.order_api AS

  g_call_count NUMBER := 0;

  PROCEDURE mark_paid(
    p_order_id IN NUMBER,
    p_status   OUT VARCHAR2
  ) AS
  BEGIN
    UPDATE app.orders
    SET    status = 'PAID'
    WHERE  order_id = p_order_id;

    IF SQL%ROWCOUNT = 1 THEN
      p_status := 'UPDATED';
    ELSE
      p_status := 'NOT_FOUND';
    END IF;

    g_call_count := g_call_count + 1;
  END mark_paid;

  FUNCTION get_total(
    p_order_id IN NUMBER
  ) RETURN NUMBER AS
    l_total NUMBER;
  BEGIN
    SELECT total_amount
    INTO   l_total
    FROM   app.orders
    WHERE  order_id = p_order_id;

    RETURN l_total;
  END get_total;

BEGIN
  -- Khối initialization chạy khi package được khởi tạo trong session.
  g_call_count := 0;
END order_api;
/
~~~

Spec và body là hai object riêng trong data dictionary. Một package có thể có spec VALID nhưng body INVALID. Khi đó client có thể nhìn thấy khai báo public nhưng không thể thực thi procedure/function vì phần triển khai chưa hợp lệ.

Các trạng thái thường thấy:

| Object type | Ý nghĩa |
|---|---|
| PACKAGE | Package specification |
| PACKAGE BODY | Phần triển khai package |
| PROCEDURE | Stored procedure độc lập |
| FUNCTION | Stored function độc lập |
| TRIGGER | Trigger |
| VIEW | View |
| TYPE / TYPE BODY | SQL object type và phần triển khai type method |

Trạng thái phổ biến:

- **VALID**: object đã được biên dịch thành công theo dependency hiện tại.
- **INVALID**: object cần được biên dịch lại hoặc không thể biên dịch thành công.
- **N/A** hoặc trạng thái khác: phụ thuộc object type và cách Oracle quản lý.

Object INVALID không nhất thiết có nghĩa source code bị sai cú pháp. Nguyên nhân có thể là object phụ thuộc bị drop/alter, grant bị thu hồi, type thay đổi, synonym trỏ sai hoặc một object được tạo lại với chữ ký khác.

## 2. ORA-04063: package hoặc object có lỗi

ORA-04063 thường xuất hiện khi Oracle cần sử dụng một object có lỗi biên dịch. Với package, error message thường chỉ rõ package body hoặc package có lỗi. Ví dụ:

~~~text
ORA-04063: package body "APP.ORDER_API" has errors
ORA-06508: PL/SQL: could not find program unit being called: "APP.ORDER_API"
ORA-06512: at line ...
~~~

ORA-04063 là dấu hiệu object không thể được sử dụng như mong đợi. Cần tìm lỗi biên dịch cụ thể, thường là PLS-xxxx hoặc ORA-xxxx trong USER_ERRORS/ALL_ERRORS. Lỗi đầu tiên trong danh sách có thể gây ra nhiều lỗi tiếp theo; hãy đọc toàn bộ thông báo theo thứ tự line/position.

### 2.1. Package spec hợp lệ nhưng body lỗi

Ví dụ spec khai báo một procedure:

~~~sql
CREATE OR REPLACE PACKAGE app.inventory_api AS
  PROCEDURE reserve_stock(
    p_product_id IN NUMBER,
    p_quantity   IN NUMBER
  );
END inventory_api;
/
~~~

Nhưng body tham chiếu đến bảng hoặc cột không tồn tại:

~~~sql
CREATE OR REPLACE PACKAGE BODY app.inventory_api AS
  PROCEDURE reserve_stock(
    p_product_id IN NUMBER,
    p_quantity   IN NUMBER
  ) AS
  BEGIN
    UPDATE app.product_stock
    SET    reserved_qty = reserved_qty + p_quantity
    WHERE  product_id = p_product_id;
  END reserve_stock;
END inventory_api;
/
~~~

Nếu bảng PRODUCT_STOCK không tồn tại, cột RESERVED_QTY không tồn tại hoặc schema APP không có quyền cần thiết, body có thể INVALID. Spec vẫn có thể VALID vì phần khai báo không phụ thuộc vào chi tiết triển khai đó.

Khi ứng dụng gọi APP.INVENTORY_API.RESERVE_STOCK, Oracle cần nạp package body. Nếu body có lỗi, lời gọi có thể thất bại với ORA-04063 và/hoặc ORA-06508 trong stack.

### 2.2. Nguyên nhân thường gặp

- Lỗi cú pháp PL/SQL trong package spec hoặc body.
- Procedure/function body không khớp khai báo trong spec: sai tên, số lượng tham số, mode IN/OUT, kiểu hoặc kiểu trả về.
- Bảng, view, sequence, synonym hoặc type được tham chiếu đã bị drop/rename.
- Cột hoặc kiểu dữ liệu của object phụ thuộc đã thay đổi.
- Package khác hoặc function được gọi đang INVALID.
- User sở hữu package thiếu quyền object được tham chiếu.
- Quyền chỉ được cấp qua role, trong khi stored PL/SQL definer-rights cần quyền trực tiếp để biên dịch/hoạt động theo ngữ cảnh.
- Synonym trỏ đến object sai owner hoặc object không tồn tại.
- SQL object type thay đổi làm package phụ thuộc cần biên dịch lại.
- Một migration chạy dở, tạo object chưa đầy đủ hoặc theo sai thứ tự.

Đừng sửa package trước khi xác nhận dependency. Nếu nguyên nhân là một table thiếu cột hoặc grant bị thu hồi, việc biên dịch lại package không tự sửa được dependency.

## 3. ORA-06508: không tìm thấy program unit được gọi

ORA-06508 là lỗi tại thời điểm thực thi: PL/SQL không thể tìm hoặc nạp program unit cần gọi. Program unit có thể là package procedure, function, procedure độc lập hoặc một đơn vị PL/SQL khác.

Ví dụ một package A gọi package B:

~~~sql
CREATE OR REPLACE PACKAGE app.order_api AS
  PROCEDURE create_order(p_order_id OUT NUMBER);
END order_api;
/

CREATE OR REPLACE PACKAGE BODY app.order_api AS
  PROCEDURE create_order(p_order_id OUT NUMBER) AS
  BEGIN
    app.sequence_api.next_order_id(p_order_id);
  END create_order;
END order_api;
/
~~~

Nếu SEQUENCE_API bị drop, invalid hoặc không thể truy cập, lời gọi CREATE_ORDER có thể thất bại khi Oracle cần thực thi dependency.

### 3.1. Phân biệt lỗi biên dịch và lỗi thực thi

| Tình huống | Dấu hiệu thường gặp | Việc cần làm |
|---|---|---|
| Package body có lỗi biên dịch | ORA-04063, PLS-xxxx trong USER_ERRORS | Đọc lỗi compile và sửa source/dependency |
| Caller tham chiếu program unit không nạp được | ORA-06508 | Kiểm tra object tồn tại, status, dependency, edition và quyền |
| Package state bị invalidated | ORA-04068, có thể đi cùng ORA-04061/04065 | Hiểu session state và xử lý lần gọi bị gián đoạn |
| Không có quyền execute | ORA-01031 hoặc lỗi PL/SQL/SQL tương ứng | Kiểm tra grant, owner và quyền trực tiếp |
| Object không tồn tại hoặc tên sai | ORA-06550/PLS-00201 hoặc lỗi resolution | Kiểm tra schema, synonym và tên gọi |

Một object INVALID có thể được Oracle thử biên dịch lại tự động khi được gọi. Nếu compile thành công, lời gọi có thể tiếp tục. Nếu compile thất bại hoặc object không thể nạp, lỗi được trả về. Không nên dựa vào auto-recompile để thay thế quy trình triển khai có kiểm soát, vì lần gọi ứng dụng đầu tiên có thể phải trả chi phí compile hoặc gặp lỗi.

### 3.2. Kiểm tra chữ ký procedure/function

Nếu spec đã thay đổi nhưng caller hoặc synonym vẫn dùng cách gọi cũ, kiểm tra định nghĩa public:

~~~sql
SELECT owner,
       package_name,
       object_name,
       argument_name,
       position,
       sequence,
       data_type,
       in_out,
       overload
FROM all_arguments
WHERE owner = 'APP'
  AND package_name = 'ORDER_API'
ORDER BY object_name, overload, sequence;
~~~

Với procedure/function độc lập, PACKAGE_NAME có thể NULL. ALL_ARGUMENTS cho biết chữ ký mà dictionary công bố; kiểm tra source package spec khi cần xem type, default parameter và khai báo đầy đủ.

### 3.3. Kiểm tra object có tồn tại và đúng edition

~~~sql
SELECT owner,
       object_name,
       object_type,
       status,
       edition_name
FROM all_objects
WHERE owner = 'APP'
  AND object_name IN ('ORDER_API', 'SEQUENCE_API')
ORDER BY object_name, object_type;
~~~

Cột EDITION_NAME chỉ có trong các cấu hình/phiên bản hỗ trợ Edition-Based Redefinition; nếu view của phiên bản không có cột này, bỏ cột khỏi truy vấn. Với database dùng edition, cần kiểm tra edition hiện tại của session và object edition mà ứng dụng nhìn thấy.

## 4. ORA-04068: trạng thái package trong session bị loại bỏ

Package PL/SQL có thể chứa biến toàn cục, constant, cursor và trạng thái khác tồn tại trong bộ nhớ của mỗi session. Khi một session gọi package lần đầu, Oracle khởi tạo package state cho session đó. Các lần gọi tiếp theo trong cùng session có thể sử dụng lại trạng thái này.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE app.session_counter AS
  PROCEDURE increment;
  FUNCTION current_value RETURN NUMBER;
END session_counter;
/

CREATE OR REPLACE PACKAGE BODY app.session_counter AS
  g_counter NUMBER := 0;

  PROCEDURE increment AS
  BEGIN
    g_counter := g_counter + 1;
  END increment;

  FUNCTION current_value RETURN NUMBER AS
  BEGIN
    RETURN g_counter;
  END current_value;
END session_counter;
/
~~~

Trong mỗi database session riêng, g_counter bắt đầu từ 0 khi package được khởi tạo. Nếu session A gọi increment ba lần, session A thấy 3; session B có state riêng và không tự thấy giá trị 3 của session A.

Package có state như vậy thường được gọi là **stateful package**.

### 4.1. Điều gì làm package state bị invalidated?

Package state có thể bị loại bỏ khi package bị recompile hoặc invalidated, ví dụ:

- DBA chạy ALTER PACKAGE ... COMPILE hoặc CREATE OR REPLACE PACKAGE BODY.
- Package specification được thay đổi.
- Object phụ thuộc làm package invalid.
- Type hoặc dependency liên quan thay đổi.
- Một số hoạt động triển khai, upgrade hoặc thay đổi edition làm session cần nạp lại object.

Khi một package stateful bị invalidated, các session đã khởi tạo package đó có thể không còn giữ state cũ. Khi session tiếp tục gọi package, Oracle có thể báo:

~~~text
ORA-04068: existing state of packages has been discarded
ORA-04061: existing state of package body "APP.SESSION_COUNTER" has been invalidated
ORA-04065: not executed, altered or dropped package body "APP.SESSION_COUNTER"
ORA-06508: PL/SQL: could not find program unit being called: "APP.SESSION_COUNTER"
~~~

Các lỗi đi kèm và thứ tự trong stack có thể khác tùy tình huống/phiên bản. ORA-04068 là thông báo quan trọng rằng package state của session đã bị loại bỏ.

### 4.2. ORA-04068 không nhất thiết có nghĩa package vẫn INVALID

Đây là điểm cần hiểu rõ khi điều tra production.

Ví dụ DBA đã recompile package body thành công. Trong data dictionary, PACKAGE BODY có thể đang VALID. Nhưng một session connection pool đã khởi tạo package trước khi recompile vẫn có state cũ. Khi session đó gọi package lần tiếp theo, Oracle phát hiện state đã invalidated và trả ORA-04068.

Vì vậy:

- Package hiện tại có thể VALID.
- Session cũ vẫn có thể nhận ORA-04068 ở lần gọi tiếp theo.
- Sau khi state bị loại, lần gọi sau có thể khởi tạo package state mới và hoạt động bình thường nếu package/dependency hợp lệ.
- Các session khác nhau có thể nhìn thấy lỗi vào những thời điểm khác nhau, tùy session nào đã khởi tạo package và khi nào nó được gọi lại.

Nếu chỉ kiểm tra DBA_OBJECTS sau sự cố, có thể thấy package VALID và tưởng rằng không có vấn đề. Cần kết hợp thời điểm deployment, session pool và log lỗi của client.

### 4.3. Package initialization chạy lại như thế nào?

Khi package được khởi tạo lần đầu trong session, Oracle thực hiện phần khai báo biến và khối initialization ở cuối package body. Sau khi state bị loại bỏ, lần khởi tạo tiếp theo có thể chạy lại initialization và đưa biến package về giá trị ban đầu.

Điều này có nghĩa:

- Bộ đếm hoặc cache trong package có thể mất giá trị.
- Cursor package đang mở có thể bị đóng/loại.
- Biến package không còn giữ dữ liệu tạm từ các lần gọi trước.
- Logic initialization có thể chạy lại.
- Nếu initialization có side effect, cần thiết kế cẩn thận vì nó có thể được thực hiện nhiều lần trong vòng đời session.

Không dùng biến package làm nơi lưu trạng thái nghiệp vụ lâu dài hoặc dữ liệu cần tồn tại qua deployment. Lưu dữ liệu quan trọng trong bảng có transaction và khóa phù hợp.

## 5. Stateful và stateless package

### Stateful package

Package có biến hoặc cursor thay đổi trong session thường giữ package state. Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE app.request_context AS
  PROCEDURE set_user(p_user_id NUMBER);
  FUNCTION get_user RETURN NUMBER;
END request_context;
/

CREATE OR REPLACE PACKAGE BODY app.request_context AS
  g_user_id NUMBER;

  PROCEDURE set_user(p_user_id NUMBER) AS
  BEGIN
    g_user_id := p_user_id;
  END set_user;

  FUNCTION get_user RETURN NUMBER AS
  BEGIN
    RETURN g_user_id;
  END get_user;
END request_context;
/
~~~

State này có thể hữu ích cho một số thao tác trong cùng session, nhưng tạo ra yêu cầu quản lý session chặt chẽ. Nếu connection pool tái sử dụng physical session cho request khác, biến package có thể giữ giá trị từ request trước nếu ứng dụng không reset đúng cách.

### Stateless package

Package không phụ thuộc vào state thay đổi giữa các lần gọi thường dễ vận hành hơn. Thay vì lưu user ID trong biến toàn cục, truyền user ID như tham số:

~~~sql
CREATE OR REPLACE PACKAGE app.request_api AS
  PROCEDURE get_orders(
    p_user_id IN NUMBER,
    p_result  OUT SYS_REFCURSOR
  );
END request_api;
/
~~~

Mỗi lời gọi nhận đầy đủ input, giảm phụ thuộc vào lịch sử session và giảm nguy cơ dữ liệu request này rò sang request khác trong connection pool.

Package vẫn có thể chứa constant hoặc biến chỉ dùng nội bộ; điều quan trọng là logic không dựa vào state thay đổi giữa các lần gọi.

### SERIALLY_REUSABLE package

Oracle hỗ trợ pragma SERIALLY_REUSABLE cho package trong các trường hợp phù hợp. Package serially reusable chỉ giữ state trong thời gian server call thay vì suốt session; state được thu hồi khi call kết thúc và khởi tạo lại cho call tiếp theo.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE app.temp_work AS
  PRAGMA SERIALLY_REUSABLE;

  PROCEDURE process_one(p_id NUMBER);
END temp_work;
/

CREATE OR REPLACE PACKAGE BODY app.temp_work AS
  PRAGMA SERIALLY_REUSABLE;

  g_counter PLS_INTEGER := 0;

  PROCEDURE process_one(p_id NUMBER) AS
  BEGIN
    g_counter := g_counter + 1;
    -- Xử lý một call.
  END process_one;
END temp_work;
/
~~~

Pragma phải được khai báo trong cả package specification và body theo quy tắc Oracle. Không phải package nào cũng phù hợp; package state không thể được giả định tồn tại giữa các server call. Có giới hạn khi gọi từ SQL hoặc khi kết hợp với các loại package khác; kiểm tra tài liệu phiên bản trước khi dùng.

SERIALLY_REUSABLE không phải cách sửa ORA-04068 cho mọi ứng dụng. Nó thay đổi semantics vòng đời state và cần kiểm tra các caller hiện tại.

## 6. Chẩn đoán trạng thái object bằng data dictionary

Bắt đầu bằng việc kiểm tra object status.

### 6.1. Kiểm tra PACKAGE và PACKAGE BODY

Với schema hiện tại:

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY object_name, object_type;
~~~

Với owner APP:

~~~sql
SELECT owner,
       object_name,
       object_type,
       status,
       last_ddl_time
FROM all_objects
WHERE owner = 'APP'
  AND object_type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY object_name, object_type;
~~~

DBA có thể dùng DBA_OBJECTS để xem phạm vi rộng hơn. LAST_DDL_TIME giúp đối chiếu thời điểm object thay đổi với thời điểm deployment hoặc sự cố. Đây không phải lúc nào cũng là thời điểm chính xác của mọi thao tác runtime; cần kết hợp log audit và deployment log.

### 6.2. Đọc lỗi biên dịch trong USER_ERRORS/ALL_ERRORS

Schema hiện tại:

~~~sql
SELECT name,
       type,
       line,
       position,
       attribute,
       message_number,
       text
FROM user_errors
WHERE name = 'ORDER_API'
ORDER BY type, sequence;
~~~

Owner khác:

~~~sql
SELECT owner,
       name,
       type,
       line,
       position,
       attribute,
       message_number,
       text
FROM all_errors
WHERE owner = 'APP'
  AND name = 'ORDER_API'
ORDER BY type, sequence;
~~~

Các cột quan trọng:

- NAME: tên object.
- TYPE: PACKAGE, PACKAGE BODY, PROCEDURE, FUNCTION...
- LINE/POSITION: vị trí lỗi trong source.
- ATTRIBUTE: ERROR hoặc WARNING.
- TEXT: nội dung compiler message.
- SEQUENCE: thứ tự message trong object.

Nếu không có dòng trong USER_ERRORS/ALL_ERRORS nhưng object vẫn INVALID, kiểm tra đúng owner, đúng edition, quyền xem dictionary và loại object. DBA_ERRORS có thể dùng với quyền thích hợp.

### 6.3. Kiểm tra dependency

Package có thể phụ thuộc vào table, view, sequence, type, synonym hoặc package khác. Xem dependency:

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type,
       dependency_type
FROM all_dependencies
WHERE owner = 'APP'
  AND name = 'ORDER_API'
ORDER BY referenced_owner, referenced_name;
~~~

Kiểm tra chiều ngược lại — object nào phụ thuộc package:

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM all_dependencies
WHERE referenced_owner = 'APP'
  AND referenced_name = 'ORDER_API'
ORDER BY owner, type, name;
~~~

ALL_DEPENDENCIES cho thấy dependency được Oracle ghi nhận. SQL động, tên object được ghép bằng chuỗi và một số phụ thuộc runtime có thể không được biểu diễn đầy đủ trong dictionary. Vì vậy, khi package dùng EXECUTE IMMEDIATE, cần đọc source và kiểm tra các object name mà code tạo động.

### 6.4. Kiểm tra source code

Dùng USER_SOURCE hoặc ALL_SOURCE:

~~~sql
SELECT line,
       text
FROM all_source
WHERE owner = 'APP'
  AND name = 'ORDER_API'
  AND type = 'PACKAGE BODY'
ORDER BY line;
~~~

Đọc cả PACKAGE spec và PACKAGE BODY để xác định khai báo public, biến global, initialization block và lời gọi dependency. Nếu object dùng wrapped source, source có thể không đọc được đầy đủ; cần artifact gốc trong source control.

## 7. Tìm lỗi gốc và thứ tự biên dịch lại

Khi nhiều object INVALID, không nên compile ngẫu nhiên từng package. Cần xác định dependency và sửa từ object gốc.

Ví dụ chuỗi dependency:

~~~text
APP.ORDER_API
      |
      +----> APP.CUSTOMER_API
      |             |
      |             +----> APP.CUSTOMERS (table/view)
      |
      +----> APP.ORDER_TYPES (SQL type)
      |
      +----> APP.PRICING_API
~~~

Nếu CUSTOMER_API lỗi do thiếu cột trong CUSTOMERS, hãy sửa schema hoặc migration trước. Sau đó compile CUSTOMER_API, rồi ORDER_API nếu nó còn INVALID.

### 7.1. Compile package spec và body

Compile cả package:

~~~sql
ALTER PACKAGE app.order_api COMPILE;
~~~

Compile riêng spec:

~~~sql
ALTER PACKAGE app.order_api COMPILE SPECIFICATION;
~~~

Compile riêng body:

~~~sql
ALTER PACKAGE app.order_api COMPILE BODY;
~~~

Dùng COMPILE SPECIFICATION khi khai báo public cần biên dịch lại; dùng COMPILE BODY khi chỉ phần triển khai cần compile và spec không thay đổi. Nếu không chắc, đọc trạng thái và source trước khi chọn. Việc compile spec có thể ảnh hưởng dependency của caller rộng hơn so với compile body.

Sau compile, kiểm tra lại:

~~~sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_name = 'ORDER_API'
ORDER BY object_type;
~~~

Và:

~~~sql
SELECT type,
       line,
       position,
       text
FROM user_errors
WHERE name = 'ORDER_API'
ORDER BY type, sequence;
~~~

### 7.2. SQL*Plus SHOW ERRORS

Trong SQL*Plus hoặc SQLcl:

~~~sql
ALTER PACKAGE app.order_api COMPILE BODY;
SHOW ERRORS PACKAGE BODY app.order_api;
~~~

Có thể dùng:

~~~sql
SHOW ERRORS PACKAGE app.order_api;
~~~

SHOW ERRORS là lệnh client, không phải SQL statement gửi từ JDBC. Trong SQL Developer, xem tab Errors hoặc truy vấn USER_ERRORS/ALL_ERRORS.

### 7.3. Compile toàn schema

Khi có nhiều object INVALID sau migration/upgrade, có thể dùng DBMS_UTILITY.COMPILE_SCHEMA:

~~~sql
BEGIN
  DBMS_UTILITY.COMPILE_SCHEMA(
    schema      => 'APP',
    compile_all => FALSE,
    reuse_settings => TRUE
  );
END;
/
~~~

COMPILE_SCHEMA yêu cầu quyền phù hợp. Nó cố gắng biên dịch các object cần biên dịch trong schema. Nếu dependency gốc vẫn lỗi, một số object sẽ tiếp tục INVALID. Sau khi chạy, phải truy vấn lại USER_OBJECTS/DBA_OBJECTS và *_ERRORS; không chỉ dựa vào việc procedure kết thúc không ném exception.

### 7.4. Recompile sau upgrade hoặc patch

Oracle cung cấp script utlrp.sql để biên dịch lại các object INVALID sau một số hoạt động upgrade/patch. Script thường nằm trong thư mục admin của Oracle Home và được chạy theo hướng dẫn của Oracle, với quyền SYSDBA trong môi trường phù hợp.

Không chạy utlrp.sql tùy tiện trong production chỉ vì một package có lỗi. Đây là công cụ thường dùng trong quy trình post-upgrade/patch; cần theo đúng hướng dẫn phiên bản, trạng thái database và maintenance window.

## 8. Quyền và synonym gây lỗi compile

Một lỗi khó nhận ra là user sở hữu package có quyền thông qua role nhưng thiếu grant trực tiếp trên object được tham chiếu.

Stored PL/SQL chạy theo quyền của definer hoặc invoker tùy AUTHID. Với definer-rights program unit (mặc định), role thường bị vô hiệu hóa khi thực thi; quyền cần thiết trên object tham chiếu phải được cấp trực tiếp cho owner theo quy tắc Oracle.

Ví dụ:

~~~sql
GRANT SELECT ON data_owner.customers TO app;
GRANT EXECUTE ON common_owner.customer_types TO app;
~~~

Nếu APP.ORDER_API truy cập DATA_OWNER.CUSTOMERS, cần kiểm tra grant trực tiếp cho APP, không chỉ kiểm tra role của user đăng nhập.

Kiểm tra quyền object được cấp:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM all_tab_privs
WHERE grantee = 'APP'
ORDER BY owner, table_name, privilege;
~~~

Với quyền EXECUTE trên package/type, kiểm tra ALL_TAB_PRIVS hoặc DBA_TAB_PRIVS tùy object và quyền xem.

### Synonym

Synonym chỉ là tên thay thế cho object, không tạo ra quyền truy cập và không bảo đảm target tồn tại.

Kiểm tra synonym:

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM all_synonyms
WHERE synonym_name IN ('CUSTOMERS', 'ORDER_API')
ORDER BY owner;
~~~

Nếu synonym trỏ đến owner/object sai, sửa synonym hoặc tham chiếu đầy đủ schema. Với package quan trọng, dùng tên owner rõ ràng trong source giúp giảm phụ thuộc vào CURRENT_SCHEMA và synonym resolution.

## 9. Package state và connection pool

Ứng dụng Java thường dùng connection pool như HikariCP, UCP hoặc pool của application server. Connection lấy ra trong mỗi request có thể là physical database session đã được sử dụng bởi request trước.

Nếu package giữ global state, request có thể nhìn thấy state còn lại từ request trước khi connection được trả về pool. Điều này tạo hai vấn đề:

1. Dữ liệu stateful có thể bị dùng nhầm giữa request/người dùng nếu không reset.
2. Khi package bị recompile, nhiều connection pool session có thể lần lượt gặp ORA-04068 vào lần gọi tiếp theo.

### 9.1. Vì sao lỗi xuất hiện rải rác sau deployment?

Giả sử pool có 20 physical sessions. Chỉ 12 session đã gọi ORDER_API trước khi DBA recompile body. Sau deployment:

- Session đã khởi tạo package có state cũ có thể nhận ORA-04068 ở lần gọi tiếp theo.
- Session chưa từng khởi tạo package có thể khởi tạo phiên bản mới mà không gặp lỗi state cũ.
- Một session có thể chỉ phát sinh lỗi khi một request sau đó gọi đúng package.
- Lỗi có thể xuất hiện dần trong vài phút hoặc lâu hơn, tùy traffic và cách pool phân phối connection.

Do đó, lỗi không nhất thiết xuất hiện ngay lúc migration hoàn tất và không nhất thiết xảy ra trên mọi request.

### 9.2. Quản lý package state trong pool

Các nguyên tắc:

- Ưu tiên package stateless: truyền dữ liệu qua tham số thay vì giữ state nghiệp vụ trong global variable.
- Nếu package stateful là cần thiết, xác định rõ lifecycle và reset state ở ranh giới request/transaction.
- Không giả định close connection sẽ xóa package state; với pool, close thường chỉ trả physical session về pool.
- Sau deployment làm thay đổi package state, cân nhắc drain/recycle pool theo quy trình vận hành để tránh lỗi rải rác.
- Nếu cần reset package trong session hiện tại, DBMS_SESSION.RESET_PACKAGE có thể giải phóng package state của session; nó không sửa object INVALID và cần được dùng đúng ranh giới session.
- Không xóa session hoặc restart toàn bộ database chỉ để xử lý ORA-04068 nếu có thể xử lý theo pool/session scope.

Ví dụ reset package state trong session hiện tại:

~~~sql
BEGIN
  DBMS_SESSION.RESET_PACKAGE;
END;
/
~~~

Lệnh này tác động đến package state của session hiện tại, không phải mọi session trong database. Nó không biên dịch package và không sửa dependency lỗi.

### 9.3. Drain và recycle pool

Khi release thay đổi package spec/body có stateful behavior, có thể chủ động drain traffic, chờ request hoàn tất rồi recycle application pool để tạo session mới. Cách làm phụ thuộc nền tảng triển khai:

- Với HikariCP, quản lý lifecycle DataSource/pool theo cơ chế ứng dụng.
- Với UCP, dùng API quản trị pool phù hợp để drain/refresh connection.
- Với application server, dùng quy trình redeploy hoặc connection pool reset được nền tảng hỗ trợ.

Không tự ý kill mọi database session đang dùng package trong giờ cao điểm. Session có transaction đang chạy có thể bị rollback hoặc làm request thất bại. Cần phối hợp cửa sổ triển khai và kiểm tra transaction active.

## 10. Xử lý ORA-04068 ở ứng dụng

ORA-04068 báo rằng package state cũ đã bị loại bỏ. Lời gọi hiện tại thất bại; sau đó session có thể khởi tạo lại package state mới ở lần gọi tiếp theo nếu object hợp lệ.

Ứng dụng cần quyết định có retry hay không dựa trên tính idempotent và transaction semantics.

### 10.1. Không retry mù quáng

Ví dụ procedure vừa trừ số dư vừa ghi giao dịch:

~~~sql
PROCEDURE debit_account(
  p_account_id IN NUMBER,
  p_amount     IN NUMBER
) AS
BEGIN
  UPDATE accounts
  SET    balance = balance - p_amount
  WHERE  account_id = p_account_id;

  INSERT INTO account_transactions(
    account_id, amount, transaction_type
  )
  VALUES (
    p_account_id, p_amount, 'DEBIT'
  );
END;
~~~

Nếu ứng dụng tự retry không kiểm soát sau lỗi, cần hiểu transaction đã rollback đến đâu và có side effect ngoài database nào đã xảy ra hay chưa. Với transaction Oracle thông thường, lỗi statement thường dẫn đến rollback statement, nhưng transaction trước đó của caller có thể vẫn còn mở; autonomous transaction hoặc external side effect có thể đã tồn tại.

Không commit ngay chỉ để “xóa lỗi”. Caller sở hữu transaction phải quyết định rollback hoặc tiếp tục theo hợp đồng nghiệp vụ.

### 10.2. Chiến lược retry an toàn

- Xác định vendor error code 4068 và nhận diện lỗi state discard.
- Đảm bảo lần gọi lỗi đã kết thúc và xử lý transaction theo quy tắc của ứng dụng.
- Nếu unit of work có thể retry an toàn, gọi lại trên cùng session sau khi package được khởi tạo lại hoặc lấy session mới theo pool policy.
- Dùng idempotency key/unique business key để tránh ghi nhận nghiệp vụ hai lần.
- Giới hạn số lần retry; không lặp vô hạn.
- Ghi log correlation ID, package name, database/session context và release version.
- Nếu lần gọi tiếp theo trả ORA-04063/06508, dừng retry và xử lý package/dependency; lỗi không còn chỉ là stale package state.

Ví dụ Java minh họa bắt lỗi Oracle vendor code:

~~~java
try {
    callOrderPackage(connection, orderId);
} catch (SQLException e) {
    if (e.getErrorCode() == 4068) {
        // Xử lý transaction theo unit-of-work.
        // Chỉ retry nếu thao tác idempotent và được phép.
        throw e;
    }
    throw e;
}
~~~

Đoạn code trên chỉ nhận diện lỗi, không phải retry implementation hoàn chỉnh. Với Spring transaction, exception có thể đánh dấu transaction rollback-only; không nên gọi lại trong cùng transaction đã bị đánh dấu rollback-only. Retry nên diễn ra ở tầng điều phối ngoài transaction cũ, tạo transaction mới theo policy.

### 10.3. Transaction boundary trong Spring

Một cách tiếp cận là đặt retry bên ngoài method transactional để mỗi lần thử có transaction riêng. Cần dùng bean/proxy riêng hoặc retry framework với transaction advice được sắp xếp đúng thứ tự; self-invocation trong cùng bean có thể không tạo transaction mới.

Không bọc một lời gọi có side effect ngoài database bằng retry tự động nếu chưa có idempotency. Với thao tác thanh toán, gửi email hoặc gọi REST API, cần cơ chế idempotency/outbox phù hợp.

## 11. Sửa package invalid và xác minh sau compile

Một quy trình xử lý package lỗi nên theo thứ tự:

1. Lấy đầy đủ error stack từ client và Oracle.
2. Xác định object name, owner, type và edition.
3. Kiểm tra USER_OBJECTS/ALL_OBJECTS/DBA_OBJECTS.
4. Đọc USER_ERRORS/ALL_ERRORS/DBA_ERRORS theo sequence.
5. Kiểm tra source spec/body và các dependency.
6. Kiểm tra object được tham chiếu, synonym, grant và chữ ký.
7. Sửa nguyên nhân gốc trong source/migration/permission.
8. Compile object phụ thuộc theo thứ tự.
9. Kiểm tra lại status và error list.
10. Thử gọi package trong session mới.
11. Đánh giá các session cũ và connection pool nếu package có state.
12. Theo dõi ORA-04068/04063/06508 sau deployment.

Ví dụ compile và xác minh:

~~~sql
ALTER PACKAGE app.order_api COMPILE BODY;

SELECT object_name,
       object_type,
       status
FROM all_objects
WHERE owner = 'APP'
  AND object_name = 'ORDER_API'
ORDER BY object_type;

SELECT owner,
       name,
       type,
       line,
       position,
       text
FROM all_errors
WHERE owner = 'APP'
  AND name = 'ORDER_API'
ORDER BY type, sequence;
~~~

Chỉ khi PACKAGE và PACKAGE BODY cần thiết đều VALID, không còn compile error và lời gọi kiểm thử thành công mới có thể xem phần sửa package đã hoàn tất. Nếu object vẫn INVALID, không che lỗi bằng cách grant rộng hoặc tạo synonym tạm mà chưa hiểu dependency.

## 12. Kiểm tra runtime session và package state

Khi lỗi chỉ xảy ra trên một số connection, cần xác định session nào đang dùng package. DBA có thể xem session:

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       machine,
       program,
       module,
       action,
       logon_time
FROM v$session
WHERE username = 'APP'
ORDER BY logon_time;
~~~

Trong RAC, dùng GV$SESSION để xem nhiều instance:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       machine,
       program,
       module,
       action,
       logon_time
FROM gv$session
WHERE username = 'APP'
ORDER BY inst_id, logon_time;
~~~

Có thể xem SQL hiện tại, wait event và transaction theo quyền DBA. Không phải mọi session đều đang gọi package tại thời điểm query; session có thể giữ state trong UGA/PGA sau khi call kết thúc.

Oracle cung cấp một số view về package và session state tùy phiên bản/cấu hình. Khi cần điều tra sâu, tham khảo dynamic performance views và tài liệu phiên bản cụ thể; tránh phụ thuộc vào các cột nội bộ không được hỗ trợ.

Đối với connection pool, ghi nhận connection/session identifier trong log ứng dụng khi có thể. Điều này giúp đối chiếu ORA-04068 với SID/SERIAL#, service, module, instance và thời điểm recompile.

## 13. Thay đổi package spec so với body

Thay đổi package body và spec có phạm vi ảnh hưởng khác nhau.

### Thay đổi package body

Nếu chỉ sửa logic nội bộ và không đổi public spec, các caller phụ thuộc vào spec thường ít bị ảnh hưởng hơn về compile dependency. Tuy nhiên, session đã khởi tạo package state vẫn có thể bị invalidated và gặp ORA-04068. Body cũng có thể phụ thuộc vào object khác nên cần compile và kiểm tra lại.

### Thay đổi package specification

Spec là giao diện công khai. Thay đổi spec như thêm/xóa procedure, đổi kiểu tham số, thay đổi public type/constant có thể làm invalid các object phụ thuộc như package, procedure, function, trigger hoặc view có sử dụng khai báo đó.

Sau thay đổi spec, cần xác định dependency graph và biên dịch lại theo thứ tự. Caller đã compile với chữ ký cũ có thể cần sửa source và compile lại.

### Tương thích ngược khi triển khai

Với ứng dụng có nhiều instance đang chạy, tránh thay đổi public signature làm code cũ không thể gọi package trong thời gian rolling deployment. Có thể:

- Thêm overload mới thay vì thay chữ ký cũ ngay.
- Giữ procedure cũ trong một release chuyển tiếp.
- Deploy ứng dụng hỗ trợ cả giao diện cũ và mới.
- Chuyển traffic sang code mới.
- Xóa API cũ trong migration/release sau khi không còn caller.

Overload cần được thiết kế rõ để tránh lời gọi mơ hồ, đặc biệt khi có default parameter hoặc kiểu có thể chuyển đổi ngầm.

## 14. Dùng Edition-Based Redefinition khi cần triển khai ít gián đoạn

Oracle Edition-Based Redefinition (EBR) cho phép duy trì nhiều edition của một số loại database object, hỗ trợ triển khai thay đổi code database trong khi ứng dụng cũ vẫn dùng edition cũ và ứng dụng mới dùng edition mới.

EBR thường liên quan:

- Edition-enabled schema.
- Editioned PL/SQL package, procedure, function và view theo khả năng hỗ trợ.
- Editioning view để che giấu thay đổi cấu trúc bảng.
- Service/session được cấu hình chạy trong edition phù hợp.
- Quy trình cutover và cleanup edition cũ.

EBR có thể giảm tác động của thay đổi package spec/body lên session đang dùng edition cũ, nhưng cần thiết kế từ trước và kiểm thử dependency. Nó không tự sửa compile error, không thay thế migration history và không giải quyết mọi loại DDL/schema change.

Nếu hệ thống không dùng EBR, không nên thêm EBR vào một hotfix đơn giản chỉ để xử lý ORA-04068. Với phần lớn ứng dụng, quản lý migration, deploy tương thích và recycle pool theo kế hoạch là đủ.

## 15. Các lỗi thường gặp khi khắc phục

### Compile thành công nhưng ứng dụng vẫn nhận ORA-04068

Package có thể VALID nhưng session cũ đã mất package state. Kiểm tra thời điểm recompile, session pool và lỗi ở lần gọi tiếp theo. Cân nhắc drain/recycle pool hoặc retry an toàn theo unit-of-work.

### Compile lại vẫn INVALID

Đọc toàn bộ USER_ERRORS/ALL_ERRORS, tìm lỗi gốc đầu tiên và kiểm tra dependency, direct grants, synonym, type và object được tham chiếu. Compile lại liên tục không sửa được object thiếu hoặc quyền thiếu.

### Chỉ PACKAGE BODY INVALID

Kiểm tra source body, table/view/type/package được tham chiếu và grant. Spec có thể VALID nhưng procedure không chạy được do body lỗi.

### ORA-06508 sau khi drop/create package

Kiểm tra object mới có cùng owner/name, đúng edition và spec/body đều tồn tại, VALID. Kiểm tra caller có tham chiếu đến package đúng schema và quyền EXECUTE.

### Lỗi chỉ xuất hiện trên một số request

Khả năng cao các physical session trong pool có lịch sử package state khác nhau. Ghi nhận session identifier và thời điểm deployment. Kiểm tra package stateful và các lần recompile/invalidation.

### Lỗi quay lại sau migration

Kiểm tra thứ tự migration, script tạo package, compile dependency, grant và synonym. Nếu pipeline chạy song song hoặc ứng dụng tự động compile object trong startup, điều phối lại deployment và xác nhận không có DDL cạnh tranh.

### DBA sửa package trực tiếp nhưng source control không đổi

Schema thực tế có thể khác artifact triển khai. Đưa thay đổi đã được phê duyệt về source control bằng migration/script chính thức, sau đó kiểm tra drift. Không dựa vào object production như nguồn duy nhất để dựng lại môi trường khác.

## 16. Quy trình triển khai package an toàn

Một quy trình triển khai package có thể thực hiện như sau:

1. **Review source**: xác nhận package spec/body và dependency được lưu trong source control.
2. **Kiểm tra compile trên môi trường test**: biên dịch với grant, synonym, type và object tương đương production.
3. **Đánh giá phạm vi invalidation**: xác định thay đổi body hay spec, package stateful và object phụ thuộc.
4. **Lập kế hoạch thứ tự**: triển khai DDL/type/table trước, sau đó package phụ thuộc, rồi caller.
5. **Điều phối migration**: chỉ một runner thay đổi schema trong phạm vi và ghi history.
6. **Compile và kiểm tra lỗi**: dùng ALL_OBJECTS/ALL_ERRORS hoặc công cụ triển khai.
7. **Smoke test**: gọi procedure/function đại diện bằng session mới và kiểm tra transaction.
8. **Quản lý session cũ**: drain/recycle pool nếu thay đổi có thể làm mất package state hoặc không tương thích code cũ.
9. **Theo dõi sau release**: quan sát ORA-04063, ORA-06508, ORA-04068, invalid object và lỗi ứng dụng.
10. **Lưu audit**: giữ commit, migration version, log compile và kết quả smoke test.

Không compile toàn bộ schema giữa giờ cao điểm nếu chưa đánh giá tác động. Recompile có thể tạo tải CPU, invalidate state và làm tăng lỗi tạm thời trên các session đang chạy.

## 17. Checklist điều tra theo mã lỗi

| Lỗi | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| ORA-04063 | Object status và USER_ERRORS/ALL_ERRORS | Sửa compile error/dependency rồi compile |
| ORA-06508 | Object tồn tại, status, owner, edition, dependency | Khôi phục/compile program unit và caller |
| ORA-04068 | Thời điểm recompile, package state, session/pool | Xử lý state discard, transaction và retry an toàn |
| ORA-04061 | Package state hiện tại đã bị invalidated | Kiểm tra invalidation/recompile và session cũ |
| ORA-04065 | Object đã bị alter/drop hoặc không thực thi được | Kiểm tra deployment và object version |
| PLS-00302 | Thành phần được tham chiếu không tồn tại trong package/type | Kiểm tra spec, version và chữ ký |
| PLS-00306 | Sai số lượng hoặc kiểu tham số | So sánh ALL_ARGUMENTS và caller |
| PLS-00201 | Identifier chưa khai báo/không phân giải được | Kiểm tra owner, synonym, direct grant và tên object |

Các mã lỗi có thể xuất hiện cùng nhau trong một stack. Luôn đọc lỗi gốc và toàn bộ stack thay vì chỉ bắt mã ngoài cùng.

## 18. Nguyên tắc vận hành quan trọng

- Kiểm tra PACKAGE và PACKAGE BODY riêng biệt; một phần VALID không chứng minh phần còn lại hợp lệ.
- Dùng USER_ERRORS/ALL_ERRORS/DBA_ERRORS để tìm line, position và compiler message.
- Kiểm tra dependency, synonym, object type và quyền trực tiếp trước khi compile lại.
- Sửa lỗi gốc trước, rồi biên dịch theo thứ tự dependency.
- Phân biệt ORA-04063/06508 (object không thể thực thi) với ORA-04068 (package state của session bị loại).
- Package global state thuộc từng session; không dùng nó làm nơi lưu dữ liệu nghiệp vụ lâu dài.
- Connection pool có thể giữ physical session cũ sau deployment; close connection thường chỉ trả session về pool.
- Khi thay đổi package stateful, lên kế hoạch xử lý session cũ, drain/recycle pool hoặc retry có kiểm soát.
- Không retry mù quáng thao tác có side effect; đặt retry ngoài transaction cũ và dùng idempotency khi cần.
- Không xóa session hoặc release lock khi chưa xác nhận transaction và trạng thái runner.
- Sau compile, kiểm tra object status, error list và gọi thử bằng session mới.
- Khi thay đổi spec, đánh giá dependency và tương thích ngược của caller.
- Với Oracle DDL, lưu ý implicit commit và trạng thái migration có thể chạy dở.
- Lưu source package, migration, log compile và deployment identity trong source control/audit.

ORA-04063, ORA-06508 và ORA-04068 đều có thể xuất hiện quanh thời điểm thay đổi PL/SQL, nhưng chúng chỉ ra các lớp vấn đề khác nhau: object không biên dịch được, program unit không thể nạp để thực thi, hoặc package state của một session đã bị loại bỏ. Kết hợp kiểm tra dictionary, compile errors, dependency graph và session lifecycle sẽ giúp xác định đúng nguyên nhân, khôi phục package an toàn và giảm lỗi phát sinh sau deployment.
