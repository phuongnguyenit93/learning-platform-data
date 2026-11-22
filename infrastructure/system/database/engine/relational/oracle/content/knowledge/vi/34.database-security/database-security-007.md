# Ranh giới quyền qua synonym, view, package và database link

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Bảo mật  
> **Mục tiêu:** Hiểu cách Oracle phân biệt phân giải tên và kiểm tra quyền; thiết kế ranh giới truy cập bằng synonym, view và PL/SQL package; lựa chọn AUTHID DEFINER hoặc AUTHID CURRENT_USER; hiểu quyền trực tiếp, role và INHERIT PRIVILEGES; kiểm soát danh tính local/remote, quyền sử dụng và quyền dữ liệu qua database link; chẩn đoán lỗi privilege và xây dựng mô hình least privilege.

## 1. Bốn đối tượng, bốn vai trò khác nhau

Synonym, view, package và database link thường xuất hiện cùng nhau trong một kiến trúc nhiều schema. Tuy nhiên, chúng giải quyết những vấn đề khác nhau:

| Thành phần | Vai trò chính | Có tự cấp quyền truy cập dữ liệu không? |
|---|---|---|
| Synonym | Bí danh để phân giải tên object | Không |
| View | Công bố một tập cột/hàng hoặc biểu thức từ nguồn dữ liệu | Người dùng cần quyền trên view; quyền trên bảng gốc được kiểm tra theo quy tắc view |
| PL/SQL package | Đóng gói thao tác và cung cấp API có kiểm soát | Người gọi cần EXECUTE; quyền trong code phụ thuộc AUTHID và quyền của owner/invoker |
| Database link | Kết nối từ database local tới database remote bằng một danh tính | Không tự cấp quyền trên object remote; remote identity phải có quyền phù hợp |

Điểm cần nhớ là một câu SQL có thể đi qua nhiều lớp tên và nhiều schema, nhưng Oracle vẫn phải xác định:

1. Tên đang trỏ tới object nào?
2. Ai là user đang thực thi?
3. Code đang chạy theo quyền của definer hay invoker?
4. Object privilege hoặc system privilege nào được yêu cầu?
5. Nếu có database link, remote session đăng nhập bằng danh tính nào?
6. Remote identity có quyền trên object đích hay không?

Một synonym có thể làm tên truy cập ngắn hơn nhưng không làm người dùng có thêm quyền. Một view có thể giới hạn cột và hàng được công bố, nhưng sẽ mất ý nghĩa nếu người dùng cũng được cấp quyền trực tiếp trên bảng gốc. Một package có thể tạo API thay cho cấp DML trực tiếp, nhưng cần kiểm soát definer rights và dynamic SQL. Một database link tạo thêm ranh giới xác thực và phân quyền ở database từ xa.

## 2. Mô hình schema tách dữ liệu và API

Một cách tổ chức phổ biến là tách schema sở hữu dữ liệu, schema công bố API và schema người dùng ứng dụng.

~~~text
                 Database local
+------------------------------------------------+
|                                                |
|  DATA_OWNER                                    |
|  +----------------------+                      |
|  | ORDERS               |  bảng dữ liệu gốc    |
|  | CUSTOMERS            |                      |
|  +----------------------+                      |
|       ^                  ^                     |
|       | direct grants    |                     |
|       |                  |                     |
|  API_OWNER                                     |
|  +----------------------+                      |
|  | ORDER_API package    |  AUTHID DEFINER      |
|  | V_OPEN_ORDERS view   |  hoặc view owner     |
|  +----------------------+                      |
|       ^                  ^                     |
|       | EXECUTE          | SELECT on view      |
|       |                  |                     |
|  APP_USER                                      |
|  +----------------------+                      |
|  | private synonyms     |  tên tiện dụng      |
|  +----------------------+                      |
|                                                |
+------------------------------------------------+
                 |
                 | database link
                 v
          Remote database
+------------------------------------------------+
| REMOTE_REPORT_READER                            |
|   quyền SELECT tối thiểu trên dữ liệu cần đọc  |
+------------------------------------------------+
~~~

Một cấu trúc triển khai có thể dùng:

- DATA_OWNER sở hữu bảng và dữ liệu.
- API_OWNER sở hữu package thực hiện các thao tác được cho phép.
- APP_USER là schema kết nối của ứng dụng.
- APP_READ và APP_WRITE là các role nhóm quyền của ứng dụng.
- Một remote account riêng chỉ đọc dữ liệu cần thiết ở database từ xa.

Không nhất thiết phải có đủ các schema/role này trong mọi hệ thống. Mục tiêu là xác định rõ ai sở hữu dữ liệu, ai quản lý API, ai gọi API và danh tính nào được dùng ở remote database.

### 2.1. Nguyên tắc least privilege

Mỗi principal chỉ nên có quyền cần thiết cho nhiệm vụ:

- Ứng dụng đọc báo cáo chỉ cần SELECT trên view hoặc package đọc.
- Ứng dụng tạo đơn chỉ cần EXECUTE package tạo đơn.
- API_OWNER chỉ có SELECT/INSERT/UPDATE cần thiết trên bảng liên quan.
- Remote account chỉ có SELECT trên các bảng/view cần truy vấn.
- Không cấp DBA, ANY TABLE hoặc quyền schema-wide nếu chỉ cần một vài object.

Tách quyền đọc và ghi khi nghiệp vụ yêu cầu khác nhau. Không cấp SELECT ANY TABLE cho ứng dụng chỉ để xử lý lỗi thiếu quyền trên một bảng.

## 3. Synonym: phân giải tên, không phải lớp bảo mật

Synonym là tên thay thế cho một schema object. Nó giúp client không phải viết đầy đủ owner.object hoặc tên object remote.

### 3.1. Private synonym

Ví dụ APP_USER tạo synonym trỏ tới view:

~~~sql
CREATE SYNONYM open_orders
FOR api_owner.v_open_orders;
~~~

Sau đó có thể truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM open_orders;
~~~

Synonym chỉ rút gọn tên. APP_USER vẫn phải có quyền SELECT trên API_OWNER.V_OPEN_ORDERS.

Cấp quyền:

~~~sql
GRANT SELECT ON api_owner.v_open_orders TO app_user;
~~~

Nếu chưa có quyền trên view, truy vấn qua synonym vẫn bị từ chối. Việc synonym tồn tại không chứng minh người dùng có thể truy cập target.

### 3.2. Public synonym

Public synonym được tạo trong namespace dùng chung:

~~~sql
CREATE PUBLIC SYNONYM open_orders
FOR api_owner.v_open_orders;
~~~

Tên OPEN_ORDERS có thể được các schema phân giải mà không cần tạo private synonym riêng. Tuy nhiên, public synonym không cấp SELECT, INSERT, UPDATE, DELETE hoặc EXECUTE trên object đích.

Một người dùng không có quyền trên API_OWNER.V_OPEN_ORDERS vẫn không thể đọc view chỉ vì public synonym tồn tại.

Public synonym cũng có thể gây rủi ro phân giải tên nếu tên chung xung đột với object/private synonym trong schema khác. Dùng tên rõ nghĩa, quản trị ownership và tránh tạo public synonym tùy tiện.

### 3.3. Synonym không sở hữu target

Xóa synonym chỉ xóa bí danh:

~~~sql
DROP SYNONYM open_orders;
~~~

Lệnh này không xóa view hoặc bảng đích. Tương tự, đổi synonym không thay đổi quyền trên target.

Không nhầm DROP SYNONYM với DROP TABLE hoặc DROP VIEW.

### 3.4. Synonym trỏ tới package

Có thể tạo synonym cho package:

~~~sql
CREATE SYNONYM order_api
FOR api_owner.order_api;
~~~

Gọi procedure:

~~~sql
BEGIN
    order_api.set_order_status(
        p_order_id => 1001,
        p_status   => 'SHIPPED'
    );
END;
/
~~~

APP_USER vẫn cần EXECUTE trên API_OWNER.ORDER_API. Synonym không thay thế GRANT EXECUTE.

### 3.5. Synonym trỏ qua database link

Một synonym có thể trỏ tới object remote:

~~~sql
CREATE SYNONYM remote_orders
FOR sales.orders@reporting_link;
~~~

Sau đó:

~~~sql
SELECT order_id, created_at
FROM remote_orders;
~~~

Để truy vấn thành công, cần thỏa các điều kiện độc lập:

- Synonym phân giải được target.
- Session có thể sử dụng database link theo loại link và owner.
- Remote connection được xác thực thành công.
- Remote identity có quyền SELECT trên SALES.ORDERS.
- Network/service name và remote database sẵn sàng.

Synonym không chuyển quyền local thành quyền remote.

## 4. View: công bố cột và hàng có kiểm soát

View là một query được đặt tên. View có thể chỉ công bố một số cột, lọc hàng, tính toán dữ liệu hoặc kết hợp nhiều bảng.

Ví dụ bảng gốc:

~~~sql
CREATE TABLE data_owner.orders (
    order_id      NUMBER PRIMARY KEY,
    customer_id   NUMBER NOT NULL,
    status        VARCHAR2(20) NOT NULL,
    created_at    TIMESTAMP(6) NOT NULL,
    total_amount  NUMBER(12,2) NOT NULL,
    internal_note VARCHAR2(1000)
);
~~~

Tạo view chỉ công bố các cột ứng dụng được phép đọc:

~~~sql
CREATE OR REPLACE VIEW data_owner.v_open_orders AS
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM data_owner.orders
WHERE status = 'OPEN'
WITH READ ONLY;
~~~

Cấp SELECT trên view:

~~~sql
GRANT SELECT ON data_owner.v_open_orders TO app_read;
GRANT app_read TO app_user;
~~~

Người dùng có role APP_READ có thể truy vấn view khi role được enable trong session:

~~~sql
SELECT order_id, customer_id, total_amount
FROM data_owner.v_open_orders;
~~~

Họ không cần được cấp SELECT trên DATA_OWNER.ORDERS nếu không có đường truy cập trực tiếp nào khác.

### 4.1. Giới hạn cột

View không đưa INTERNAL_NOTE ra projection, nên người đọc view không thể lấy cột này qua chính view.

Điều này giúp tách dữ liệu nội bộ khỏi interface ứng dụng. Nhưng nếu APP_USER có SELECT trực tiếp trên bảng gốc, họ có thể bỏ qua view. Vì vậy, muốn view trở thành ranh giới cột, không cấp quyền bảng gốc cho consumer.

### 4.2. Giới hạn hàng

WHERE trong view giới hạn các hàng được view trả về:

~~~sql
CREATE OR REPLACE VIEW data_owner.v_open_orders AS
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM data_owner.orders
WHERE status = 'OPEN'
WITH READ ONLY;
~~~

View này chỉ hiển thị đơn OPEN. Tuy nhiên, đây là chính sách cố định cho mọi người có quyền trên view. Nếu mỗi tenant/user chỉ được xem các hàng khác nhau, cần cơ chế row-level security phù hợp như Virtual Private Database (VPD) hoặc chính sách kiểm soát dựa trên application context đã được bảo vệ.

Không dùng một predicate cố định trong view như thể nó tự tạo chính sách phân quyền theo từng người dùng.

### 4.3. WITH CHECK OPTION

Nếu view cho phép DML, WITH CHECK OPTION buộc hàng được INSERT/UPDATE qua view vẫn phải thỏa predicate của view.

Ví dụ:

~~~sql
CREATE OR REPLACE VIEW data_owner.v_open_orders_edit AS
SELECT order_id,
       customer_id,
       status,
       created_at,
       total_amount
FROM data_owner.orders
WHERE status = 'OPEN'
WITH CHECK OPTION CONSTRAINT v_open_orders_ck;
~~~

Nếu người dùng cập nhật STATUS thành CLOSED qua view này, thao tác có thể bị từ chối vì hàng không còn thỏa điều kiện view.

WITH CHECK OPTION không thay thế các constraint nghiệp vụ hoặc row-level security. Nó kiểm soát việc DML qua view duy trì predicate của view.

### 4.4. WITH READ ONLY

Nếu consumer chỉ cần đọc, WITH READ ONLY làm view không cho DML qua view:

~~~sql
CREATE OR REPLACE VIEW data_owner.v_order_summary AS
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM data_owner.orders
GROUP BY customer_id
WITH READ ONLY;
~~~

View có thể là một interface báo cáo. Người dùng được SELECT nhưng không thể cập nhật dữ liệu qua view.

### 4.5. View không tự động là security barrier hoàn chỉnh

View chỉ giới hạn đường truy cập mà nó cung cấp. Kiểm tra các đường khác:

- User có quyền trực tiếp trên bảng gốc không?
- Có synonym khác trỏ tới bảng gốc không?
- Có package khác trả ra dữ liệu nhạy cảm không?
- Có database link hoặc schema khác cho phép truy cập không?
- Có quyền ANY TABLE hoặc quyền hệ thống quá rộng không?
- Có view khác join lại cột đã bị ẩn không?

Một view an toàn phải đi cùng ma trận quyền tổng thể. Chỉ tạo view rồi grant SELECT mà không thu hồi quyền dư thừa không tạo được ranh giới mong muốn.

### 4.6. Quyền của view owner và quyền của người đọc

Để tạo view, owner cần quyền trực tiếp phù hợp trên các object cơ sở; quyền chỉ có thông qua role thường không đủ cho dependency/compile của stored object.

Người dùng được GRANT SELECT trên view có thể đọc qua view mà không cần SELECT trực tiếp trên bảng gốc.

Nếu view owner không sở hữu object cơ sở và muốn grant quyền trên view cho người khác, cần kiểm tra yêu cầu grant option trên các object nền. Thiếu grant option có thể dẫn tới ORA-01720. Một cách đơn giản để quản lý là để schema sở hữu bảng tạo view công bố, hoặc thiết kế grant chain có chủ đích thay vì cấp WITH GRANT OPTION rộng rãi.

## 5. PL/SQL package: API thao tác dữ liệu

Package có thể đóng gói logic đọc/ghi và chỉ công bố những thao tác nghiệp vụ được cho phép. Consumer được cấp EXECUTE trên package thay vì DML trực tiếp trên bảng.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE api_owner.order_api
AUTHID DEFINER
AS
    PROCEDURE set_order_status(
        p_order_id IN data_owner.orders.order_id%TYPE,
        p_status   IN data_owner.orders.status%TYPE
    );

    PROCEDURE create_order(
        p_order_id     IN data_owner.orders.order_id%TYPE,
        p_customer_id  IN data_owner.orders.customer_id%TYPE,
        p_total_amount IN data_owner.orders.total_amount%TYPE
    );
END order_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY api_owner.order_api
AS
    PROCEDURE set_order_status(
        p_order_id IN data_owner.orders.order_id%TYPE,
        p_status   IN data_owner.orders.status%TYPE
    )
    IS
    BEGIN
        IF p_status NOT IN ('OPEN', 'PAID', 'SHIPPED', 'CANCELLED') THEN
            RAISE_APPLICATION_ERROR(-20001, 'Invalid order status');
        END IF;

        UPDATE data_owner.orders
        SET status = p_status
        WHERE order_id = p_order_id;

        IF SQL%ROWCOUNT = 0 THEN
            RAISE_APPLICATION_ERROR(-20002, 'Order not found');
        END IF;
    END set_order_status;
END order_api;
/
~~~

Ví dụ minh họa cần các cột và quyền tương ứng tồn tại. API production cần thêm validation, transaction contract, audit và xử lý lỗi theo nghiệp vụ.

Cấp quyền:

~~~sql
GRANT UPDATE ON data_owner.orders TO api_owner;
GRANT EXECUTE ON api_owner.order_api TO app_writer;
GRANT app_writer TO app_user;
~~~

APP_USER gọi API nhưng không được cấp UPDATE trực tiếp trên DATA_OWNER.ORDERS.

### 5.1. Package specification và body

- Specification công bố procedure, function, type, constant và cursor được phép dùng.
- Body chứa implementation và chi tiết nội bộ.
- Consumer chỉ cần biết contract trong specification.
- Thay implementation trong body có thể không yêu cầu consumer thay đổi nếu public contract giữ nguyên.

Không công bố procedure nội bộ trong package specification nếu ứng dụng không cần gọi. Mọi public member đều mở rộng API và cần được quản lý tương thích.

### 5.2. Package không tự làm code an toàn

Một package definer-rights có thể thực hiện thao tác với quyền rộng hơn người gọi. Nếu API nhận input tùy ý và xây dynamic SQL không an toàn, attacker có thể lợi dụng quyền của package owner.

Các nguyên tắc:

- Chỉ công bố thao tác nghiệp vụ cần thiết.
- Validate trạng thái, khóa và phạm vi tenant ở server.
- Bind dữ liệu thay vì nối chuỗi SQL.
- Whitelist tên bảng/cột/sort direction nếu buộc phải dynamic.
- Dùng DBMS_ASSERT để xác thực identifier trong trường hợp phù hợp; hàm này không thay thế authorization.
- Không trả lỗi nội bộ, SQL text hoặc dữ liệu nhạy cảm cho client.
- Không cấp quyền package cho PUBLIC nếu không có lý do.
- Owner package chỉ giữ quyền trên object thực sự cần.

## 6. AUTHID DEFINER: thực thi theo quyền của owner

PL/SQL stored procedure, function và package mặc định sử dụng definer rights nếu không khai báo AUTHID khác.

~~~sql
CREATE OR REPLACE PACKAGE api_owner.order_api
AUTHID DEFINER
AS
    PROCEDURE close_order(p_order_id NUMBER);
END;
/
~~~

Khi APP_USER gọi package, code chạy với quyền của API_OWNER cho các thao tác được thực hiện trong definer-rights unit.

Điều này cho phép API_OWNER giữ quyền UPDATE trên bảng nhưng APP_USER chỉ có EXECUTE trên package.

### 6.1. Role không thay thế direct grant trong definer-rights code

Trong definer-rights PL/SQL, các role của session caller không được dùng để cấp quyền cho câu SQL chạy bên trong unit; quyền cần thiết phải được cấp trực tiếp cho owner theo quy tắc stored object.

Ví dụ:

~~~sql
-- Không đủ để compile static SQL trong definer-rights package:
GRANT update_role TO api_owner;

-- Cấp object privilege trực tiếp cho package owner:
GRANT UPDATE ON data_owner.orders TO api_owner;
~~~

Nếu API_OWNER chỉ có UPDATE qua UPDATE_ROLE, static SQL trong package có thể không compile hoặc không thực thi theo mong đợi. Hãy cấp đúng object privilege trực tiếp.

Đây là một khác biệt quan trọng giữa câu SQL chạy trực tiếp trong session và SQL nằm trong stored definer-rights program unit.

### 6.2. Vì sao definer rights hữu ích?

- Consumer không cần biết bảng vật lý.
- Có thể kiểm soát thao tác qua procedure.
- Validation và audit tập trung.
- Có thể thay đổi schema nội bộ mà không đổi contract ứng dụng.
- Hạn chế quyền DML trực tiếp trên bảng.

### 6.3. Rủi ro của definer rights

- Package owner có thể có quyền rộng hơn caller.
- Một lỗi authorization trong package có thể trở thành privilege escalation.
- Dynamic SQL có thể mở rộng bề mặt SQL injection.
- Package được grant EXECUTE cho quá nhiều user có thể trở thành cổng truy cập dữ liệu không phù hợp.
- Direct grants của owner có thể vô tình quá rộng.

Dùng một schema owner chuyên biệt, không dùng SYS/SYSTEM làm owner ứng dụng và không cấp ANY TABLE chỉ để code chạy được.

## 7. AUTHID CURRENT_USER: thực thi theo quyền invoker

Khai báo AUTHID CURRENT_USER tạo invoker-rights unit:

~~~sql
CREATE OR REPLACE PACKAGE util_owner.report_tools
AUTHID CURRENT_USER
AS
    PROCEDURE read_report;
END;
/
~~~

Khi được gọi, unit sử dụng quyền của invoker theo quy tắc invoker rights. Đây là lựa chọn hữu ích cho utility dùng chung cần hoạt động trên object mà caller có quyền truy cập.

Khác biệt tổng quát:

| Đặc điểm | AUTHID DEFINER | AUTHID CURRENT_USER |
|---|---|---|
| Quyền runtime chính | Owner của unit | Invoker |
| Mục tiêu | API nghiệp vụ có kiểm soát | Utility chạy theo quyền caller |
| Role của caller | Không cấp quyền cho definer-rights SQL | Quyền invoker và role được enable có liên quan |
| Rủi ro chính | Code có thể dùng quyền owner quá rộng | Hành vi phụ thuộc quyền và schema context caller |
| Phù hợp | API đọc/ghi đã đóng gói | Framework/utility dùng chung, thao tác theo caller |

Không chọn invoker rights chỉ vì muốn tránh direct grant cho owner. Nó thay đổi ngữ nghĩa authorization và có thể làm cùng một procedure chạy thành công với user này nhưng thất bại với user khác.

### 7.1. INHERIT PRIVILEGES

Từ Oracle 12c, cơ chế INHERIT PRIVILEGES kiểm soát việc một invoker-rights program unit có được phép kế thừa quyền của invoker hay không.

Ví dụ minh họa:

~~~sql
GRANT INHERIT PRIVILEGES ON USER app_user TO util_owner;
~~~

Lệnh này cho phép UTIL_OWNER kế thừa quyền của APP_USER trong ngữ cảnh invoker-rights theo quy tắc Oracle.

Nếu thiếu quyền phù hợp, việc gọi invoker-rights unit có thể gặp ORA-06598. Có system privilege INHERIT ANY PRIVILEGES, nhưng đây là quyền rất rộng; không cấp cho owner ứng dụng nếu chỉ cần kế thừa quyền từ một số user xác định.

Kiểm tra grant INHERIT PRIVILEGES và quyền hệ thống theo chính sách DBA. Đừng giải quyết ORA-06598 bằng cách cấp INHERIT ANY PRIVILEGES cho mọi schema.

### 7.2. CURRENT_USER và CURRENT_SCHEMA không giống nhau

- CURRENT_USER là danh tính bảo mật được dùng theo ngữ cảnh thực thi.
- CURRENT_SCHEMA ảnh hưởng schema mặc định khi phân giải tên object không ghi owner.
- Đổi CURRENT_SCHEMA không cấp thêm quyền và không biến session thành user khác.

Ví dụ:

~~~sql
ALTER SESSION SET CURRENT_SCHEMA = reporting;
~~~

Lệnh này có thể thay đổi cách Oracle phân giải tên không ghi schema, nhưng quyền vẫn thuộc user đã đăng nhập/current security context. Không dùng CURRENT_SCHEMA như cơ chế phân quyền.

### 7.3. Chọn AUTHID theo contract

Trước khi tạo package, trả lời:

- Ai chịu trách nhiệm cấp quyền trên bảng?
- Procedure có được phép thao tác vượt quyền caller không?
- Caller cần truy cập object của chính họ hay object do owner quản lý?
- Có dynamic SQL hoặc schema-qualified object không?
- Role của caller có ảnh hưởng kết quả mong muốn không?
- Có cần INHERIT PRIVILEGES không?
- Có thể giới hạn API bằng definer rights và object grants nhỏ hơn không?

Ghi AUTHID rõ ràng trong DDL thay vì dựa vào default để người review nhìn thấy chủ đích.

## 8. Quyền trực tiếp, role và quyền của stored object

Oracle có nhiều lớp privilege:

- System privilege: cho phép thực hiện thao tác ở mức hệ thống, ví dụ CREATE SESSION hoặc CREATE VIEW.
- Object privilege: quyền trên object cụ thể, ví dụ SELECT trên bảng, EXECUTE trên package.
- Role: nhóm privilege được grant cho user hoặc role khác.
- Program-unit privilege behavior: quyền cần cho stored code phụ thuộc AUTHID và quy tắc compile/runtime.

### 8.1. Cấp quyền qua role cho user ứng dụng

~~~sql
CREATE ROLE app_read;

GRANT SELECT ON data_owner.v_order_summary TO app_read;
GRANT app_read TO app_user;
~~~

Khi role APP_READ được enable, APP_USER có thể SELECT view.

Kiểm tra role hiện đang enable:

~~~sql
SELECT role
FROM session_roles
ORDER BY role;
~~~

Role được grant cho user không nhất thiết đang enable trong mọi session; secure application role hoặc SET ROLE có thể thay đổi trạng thái.

### 8.2. Direct grant cho package owner

~~~sql
GRANT SELECT, UPDATE
ON data_owner.orders
TO api_owner;
~~~

Đây là quyền trực tiếp trên object. Package AUTHID DEFINER của API_OWNER có thể dùng quyền này theo contract của package.

Tránh grant quyền dư thừa. Nếu package chỉ UPDATE STATUS, cân nhắc thiết kế object/column privilege và API sao cho owner không cần quyền đọc/ghi mọi cột.

### 8.3. PUBLIC privilege

PUBLIC là role đặc biệt mà mọi database user có thể nhận privilege được grant cho PUBLIC. Grant object privilege hoặc EXECUTE package cho PUBLIC có thể mở rộng bề mặt truy cập toàn database.

Tránh:

~~~sql
GRANT EXECUTE ON api_owner.admin_api TO PUBLIC;
~~~

trừ khi API thực sự được thiết kế công khai cho toàn bộ database users và đã đánh giá rủi ro.

### 8.4. GRANT OPTION và ADMIN OPTION

- WITH GRANT OPTION trên object privilege cho phép grantee cấp tiếp object privilege đó trong phạm vi quy định.
- WITH ADMIN OPTION trên role/system privilege cho phép grantee quản lý hoặc cấp tiếp quyền tương ứng theo quy tắc Oracle.

Không cấp GRANT OPTION hoặc ADMIN OPTION theo thói quen. Chúng mở rộng quyền quản trị của grantee, không chỉ quyền sử dụng object.

## 9. Database link: ranh giới xác thực sang database khác

Database link là object trong database local chứa thông tin để kết nối tới database remote. SQL có thể truy cập remote object bằng cú pháp:

~~~sql
SELECT order_id, total_amount
FROM sales.orders@reporting_link;
~~~

Database link không phải synonym và không phải một proxy tự động mang nguyên quyền local sang remote. Remote database xác thực một danh tính và kiểm tra quyền của danh tính đó trên object remote.

### 9.1. Private database link

Private link thuộc schema tạo ra:

~~~sql
CREATE DATABASE LINK reporting_link
CONNECT TO report_reader IDENTIFIED BY "replace_with_managed_secret"
USING 'REPORTING_DB';
~~~

Ví dụ dùng fixed user: remote connection đăng nhập bằng REPORT_READER. Trong production, không đưa mật khẩu thật vào source control, log hoặc tài liệu triển khai. Dùng quy trình quản lý credential được tổ chức phê duyệt và xoay vòng theo chính sách.

Private link được schema owner sử dụng theo quy tắc của database link. User khác không thể mặc nhiên dùng private link chỉ vì biết tên link.

### 9.2. Public database link

Public link có thể được các database user sử dụng:

~~~sql
CREATE PUBLIC DATABASE LINK reporting_public
CONNECT TO report_reader IDENTIFIED BY "managed_secret"
USING 'REPORTING_DB';
~~~

Public link có thể thuận tiện cho nhiều schema, nhưng nếu nó đăng nhập bằng một remote account có quyền rộng, nhiều local user có thể dùng chung remote identity đó.

Tránh public link tới remote account có quyền ghi hoặc quyền truy cập dữ liệu nhạy cảm nếu không có yêu cầu rõ ràng và kiểm soát bù phù hợp. Ưu tiên private link với remote account giới hạn.

### 9.3. Fixed-user database link

Fixed-user link chỉ định username/password remote trong link definition:

~~~sql
CREATE DATABASE LINK reporting_link
CONNECT TO report_reader IDENTIFIED BY "managed_secret"
USING 'REPORTING_DB';
~~~

Mọi câu SQL qua link dùng remote identity REPORT_READER. Quyền remote không tự thay đổi theo local APP_USER.

Vì vậy, nếu nhiều local user có thể sử dụng cùng link, họ có thể thực hiện các thao tác mà REPORT_READER được phép làm. Giới hạn remote account ở mức tối thiểu và kiểm soát ai được dùng link.

### 9.4. Connected-user và current-user link

Oracle hỗ trợ các kiểu link dùng danh tính người dùng thay vì một fixed remote account, tùy cơ chế xác thực và cấu hình:

- Connected-user link dùng danh tính/credential tương ứng của user kết nối local theo cấu hình link.
- Current-user link dùng global user identity trong môi trường enterprise authentication được hỗ trợ.

Ví dụ cú pháp current-user link:

~~~sql
CREATE DATABASE LINK enterprise_reporting
CONNECT TO CURRENT_USER
USING 'ENTERPRISE_REPORTING';
~~~

Current-user link yêu cầu điều kiện xác thực global user phù hợp. Không thể coi nó như fixed-user link chỉ bỏ password. Kiểm tra Oracle Net, enterprise user, directory/authentication setup và release cụ thể trước khi triển khai.

### 9.5. Local privilege và remote privilege là hai lớp riêng

Để truy vấn SALES.ORDERS@REPORTING_LINK, cần xem:

1. Local user/schema có thể sử dụng link theo loại link và ownership không?
2. Link có kết nối được tới remote service không?
3. Remote authentication thành công không?
4. Remote identity có SELECT trên SALES.ORDERS không?
5. Remote object có tồn tại và tên được phân giải đúng không?
6. Network, listener và service name có sẵn sàng không?

Cấp SELECT trên một bảng local không cấp SELECT trên bảng remote. Ngược lại, remote account có SELECT cũng không làm một local user tự động có quyền sử dụng private link của schema khác.

## 10. Remote identity và quyền trên object remote

Ví dụ remote DBA tạo account chỉ đọc:

~~~sql
CREATE USER report_reader IDENTIFIED BY "managed_secret";
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON sales.orders TO report_reader;
~~~

Ở local database, schema có link fixed-user tới REPORT_READER. Khi chạy:

~~~sql
SELECT order_id, total_amount
FROM sales.orders@reporting_link;
~~~

remote database kiểm tra quyền của REPORT_READER trên SALES.ORDERS.

Không cấp SELECT ANY TABLE cho REPORT_READER nếu chỉ cần một bảng. Nếu cần nhiều bảng, grant từng object hoặc tạo remote view chỉ công bố cột/hàng phù hợp rồi grant SELECT trên view.

### 10.1. Dùng remote view để giới hạn dữ liệu

Ở remote database:

~~~sql
CREATE OR REPLACE VIEW sales.v_order_export AS
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM sales.orders
WHERE status IN ('PAID', 'SHIPPED')
WITH READ ONLY;

GRANT SELECT ON sales.v_order_export TO report_reader;
~~~

Remote account chỉ được grant SELECT trên view nếu quyền và ownership chain phù hợp. Sau đó local query qua link:

~~~sql
SELECT order_id, customer_id, total_amount
FROM sales.v_order_export@reporting_link;
~~~

Remote view tạo interface ổn định và tránh cấp quyền đọc bảng gốc cho remote account. Nếu view owner không sở hữu bảng gốc, kiểm tra grant option requirement khi cấp quyền trên view.

### 10.2. Synonym remote không thay quyền remote

~~~sql
CREATE SYNONYM remote_order_export
FOR sales.v_order_export@reporting_link;
~~~

Synonym làm tên ngắn hơn. Remote identity vẫn phải có SELECT trên SALES.V_ORDER_EXPORT và local session vẫn phải sử dụng được REPORTING_LINK.

### 10.3. Package ở remote database

Có thể gọi package remote nếu remote identity có EXECUTE phù hợp và database link hỗ trợ truy cập:

~~~sql
BEGIN
    sales.reporting_api.refresh_summary@reporting_link;
END;
/
~~~

Khi code remote chạy, quyền và AUTHID của remote stored unit được áp dụng tại remote database. Cần kiểm tra cả local link identity lẫn remote package privilege chain.

## 11. Database link và stored code

Khi database link được dùng bên trong view hoặc PL/SQL package, cần xác định schema nào sở hữu link và code chạy theo AUTHID nào.

Các câu hỏi cần kiểm tra:

- Link là private hay public?
- Link thuộc schema nào?
- Package là AUTHID DEFINER hay CURRENT_USER?
- Runtime user có thể truy cập link theo ngữ cảnh đó không?
- Remote login user là fixed user hay current user?
- Remote object privilege có đủ không?
- Dynamic SQL có dùng đúng schema/link và bind values không?

Đừng giả định package definer-rights tự động dùng được mọi private link của caller. Hãy triển khai test bằng user ứng dụng thật, package owner thật và link thật trong môi trường kiểm thử.

### 11.1. Remote link trong package API

Một package API có thể đọc dữ liệu remote rồi trả kết quả đã kiểm soát. Package owner cần quyền và private link phù hợp; caller chỉ được EXECUTE package nếu thiết kế definer-rights.

Điều này giúp tránh grant quyền sử dụng database link trực tiếp cho mọi user. Nhưng nó cũng khiến package trở thành điểm tập trung quyền remote, nên cần:

- Giới hạn procedure được công bố.
- Validate input và tenant scope.
- Giới hạn remote account.
- Audit thao tác và lỗi.
- Timeout/retry có giới hạn.
- Kiểm soát dữ liệu trả về.
- Không cho caller truyền SQL fragment tùy ý.

### 11.2. Transaction phân tán

DML qua database link có thể tham gia distributed transaction. Khi một transaction cập nhật cả local và remote database, Oracle có thể dùng two-phase commit để điều phối commit.

Điều này tạo thêm rủi ro vận hành:

- Network failure trong quá trình commit.
- In-doubt transaction.
- Lock và latency kéo dài.
- Remote database unavailable.
- Khó retry nếu không có idempotency.

Không mở transaction phân tán dài nếu có thể tách thành message/outbox hoặc batch đồng bộ có checkpoint. Nếu cần atomic commit across databases, hiểu rõ distributed transaction, recovery và DBA procedures.

## 12. Thiết kế an toàn cho dynamic SQL

Dynamic SQL là vùng rủi ro cao khi package chạy bằng definer rights.

Ví dụ không an toàn:

~~~sql
l_sql := 'SELECT * FROM data_owner.orders WHERE status = '''
         || p_status || '''';
EXECUTE IMMEDIATE l_sql;
~~~

Nếu input chứa dấu nháy hoặc đoạn SQL độc hại, câu lệnh có thể bị thay đổi.

Dùng bind variable:

~~~sql
l_sql := 'SELECT order_id FROM data_owner.orders WHERE status = :b1';

EXECUTE IMMEDIATE l_sql
BULK COLLECT INTO l_order_ids
USING p_status;
~~~

Với tên bảng/cột, bind variable không áp dụng cho identifier. Dùng whitelist:

~~~sql
CASE p_sort_key
    WHEN 'CREATED_AT' THEN
        l_order_by := 'created_at';
    WHEN 'TOTAL_AMOUNT' THEN
        l_order_by := 'total_amount';
    ELSE
        RAISE_APPLICATION_ERROR(-20010, 'Unsupported sort key');
END CASE;
~~~

DBMS_ASSERT có thể giúp xác thực identifier/literal theo mục tiêu cụ thể:

~~~sql
l_safe_name := DBMS_ASSERT.SIMPLE_SQL_NAME(p_column_name);
~~~

Nhưng DBMS_ASSERT không chứng minh người gọi được phép truy cập object đó. Authorization vẫn cần whitelist và privilege checks.

Trong definer-rights code, SQL injection có thể khai thác quyền owner. Hạn chế dynamic SQL và không nối input không tin cậy vào statement.

## 13. Bảng tổng hợp quyền theo từng lớp

| Đường truy cập | Quyền người gọi cần | Quyền chủ thể thực thi cần |
|---|---|---|
| SELECT trực tiếp bảng | SELECT trên bảng hoặc role đang enable | Chính session user |
| SELECT qua private synonym | SELECT trên target object | Chính session user |
| SELECT qua public synonym | SELECT trên target object | Chính session user |
| SELECT qua view | SELECT trên view | View owner cần quyền nền phù hợp |
| Gọi definer-rights package | EXECUTE trên package | Package owner cần direct grants cho SQL nội bộ |
| Gọi invoker-rights package | EXECUTE trên package | Invoker cần quyền theo ngữ cảnh và INHERIT PRIVILEGES phù hợp |
| SELECT qua fixed-user DB link | Quyền sử dụng link theo owner/link type | Fixed remote account cần quyền remote object |
| SELECT qua current-user DB link | Link/authentication setup phù hợp | Current global user cần quyền remote object |
| Gọi remote package qua link | Sử dụng link và quyền remote EXECUTE | Remote package áp dụng AUTHID và quyền tại remote DB |

Bảng này là mô hình tổng quát. Các chi tiết compile-time, runtime, role, remote authentication và object resolution phụ thuộc object type và Oracle release. Khi triển khai, test bằng đúng principal thực tế.

## 14. Data dictionary để kiểm tra quyền và tên

### 14.1. Object privileges

Xem quyền object trong schema hiện tại:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM user_tab_privs
ORDER BY table_name, grantee, privilege;
~~~

Xem quyền mà user hiện tại có thể thấy:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM all_tab_privs
WHERE grantee IN ('APP_USER', 'APP_READ', 'APP_WRITE')
ORDER BY owner, table_name, grantee, privilege;
~~~

DBA có thể dùng DBA_TAB_PRIVS để xem toàn database nếu có quyền.

### 14.2. System privileges và roles

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

~~~sql
SELECT role
FROM session_roles
ORDER BY role;
~~~

Để kiểm tra role được grant cho user, xem USER_ROLE_PRIVS hoặc DBA_ROLE_PRIVS theo phạm vi quyền.

Session_roles cho biết role đang enable trong session hiện tại; user_role_privs không đồng nghĩa mọi role đều đang enable.

### 14.3. Synonym metadata

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM all_synonyms
WHERE synonym_name IN ('OPEN_ORDERS', 'ORDER_API')
ORDER BY owner, synonym_name;
~~~

DB_LINK khác NULL cho biết synonym trỏ tới object qua database link. Metadata này chỉ cho biết target mapping, không chứng minh người dùng có quyền truy cập target.

### 14.4. View và package dependencies

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM all_dependencies
WHERE owner IN ('DATA_OWNER', 'API_OWNER')
ORDER BY owner, name, referenced_owner, referenced_name;
~~~

Dependencies giúp tìm object được view/package tham chiếu. Dynamic SQL có thể không được ghi đầy đủ trong dependency metadata vì tên object chỉ xuất hiện lúc runtime.

### 14.5. Database link metadata

~~~sql
SELECT owner,
       db_link,
       username,
       host,
       created
FROM all_db_links
ORDER BY owner, db_link;
~~~

USER_DB_LINKS/ALL_DB_LINKS/DBA_DB_LINKS cung cấp metadata theo phạm vi quyền. Không coi metadata link là nơi để lấy password dạng rõ; không đưa credential vào log hoặc báo cáo.

### 14.6. Kiểm tra package AUTHID

Có thể xem source hoặc metadata của package để xác định AUTHID:

~~~sql
SELECT owner,
       name,
       type,
       line,
       text
FROM all_source
WHERE owner = 'API_OWNER'
  AND name = 'ORDER_API'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY type, line;
~~~

Khi review, xác nhận package spec có AUTHID DEFINER hay CURRENT_USER. Nếu không ghi, cần hiểu default definer rights.

## 15. Các lỗi privilege thường gặp

| Lỗi | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| ORA-00942 | Object không tồn tại hoặc user không có quyền; synonym target sai | Kiểm tra owner/object, synonym và grant |
| ORA-01031 | Thiếu system/object privilege | Xác định thao tác và principal thực thi |
| ORA-01720 | Thiếu grant option trên object nền khi grant quyền qua view | Kiểm tra view owner và grant chain |
| ORA-06598 | Invoker-rights unit thiếu INHERIT PRIVILEGES phù hợp | Kiểm tra AUTHID và grant inherit |
| ORA-04063 | View/package có lỗi hoặc dependency invalid | Xem USER_ERRORS/ALL_ERRORS và compile |
| ORA-04068 | Package state bị discard sau thay đổi/recompile trong một số tình huống | Kiểm tra package state và retry contract |
| ORA-02019 | Không tìm thấy remote connection description/database link phù hợp | Kiểm tra link name và Oracle Net |
| ORA-02085 | Global name của database link không khớp theo cấu hình | Kiểm tra GLOBAL_NAMES và remote global name |
| ORA-02019/ORA-12154 | Link/service name không phân giải được | Kiểm tra USING connect identifier, tnsnames/LDAP |
| ORA-01017 | Remote username/password không hợp lệ | Xác minh remote identity và credential rotation |
| ORA-02063 | Lỗi được trả về từ remote database | Đọc thông báo remote đứng trước dòng ORA-02063 |
| ORA-02049 | Distributed transaction timeout khi chờ lock | Kiểm tra remote blocking và transaction duration |

Một mã lỗi có thể có nhiều nguyên nhân. Luôn đọc toàn bộ error stack và xác định local hay remote database phát sinh lỗi.

## 16. Kiểm thử ranh giới quyền bằng user thật

Không chỉ kiểm thử bằng SYS hoặc schema owner. Dùng account đại diện cho ứng dụng.

Ví dụ ma trận:

| Principal | SELECT bảng gốc | SELECT view | EXECUTE package | Dùng DB link |
|---|---:|---:|---:|---:|
| DATA_OWNER | Có | Có | Theo grant | Theo cấu hình |
| API_OWNER | Chỉ direct grant cần thiết | Theo thiết kế | Owner | Private link nếu cần |
| APP_READ | Không | Có | Không | Không |
| APP_WRITE | Không | Có thể không | Có | Không trực tiếp |
| APP_USER | Theo role được grant | Theo role | Theo role | Chỉ nếu được thiết kế |

Các bài test quan trọng:

1. APP_READ SELECT view thành công.
2. APP_READ SELECT bảng gốc bị từ chối.
3. APP_WRITE gọi package thành công.
4. APP_WRITE UPDATE trực tiếp bảng gốc bị từ chối.
5. User không có EXECUTE không gọi được package.
6. Synonym tồn tại nhưng thiếu quyền target thì truy vấn vẫn bị từ chối.
7. User không phải owner không dùng được private database link của schema khác.
8. Remote account chỉ đọc không thể UPDATE bảng remote.
9. Khi remote password hết hạn/đổi, link cần được cập nhật theo runbook.
10. Invoker-rights package được test với user có và không có INHERIT PRIVILEGES.
11. Dynamic SQL không thể đổi object hoặc predicate ngoài whitelist.
12. View không để lộ cột nhạy cảm hoặc hàng tenant khác qua đường truy cập phụ.

### 16.1. Kiểm thử negative case

Security test phải chứng minh cả thao tác được phép lẫn thao tác bị từ chối. Một test chỉ xác nhận SELECT thành công không chứng minh bảng gốc đã được bảo vệ.

Dùng session mới hoặc reset role/session context phù hợp. Ghi rõ user đăng nhập, current_user, current_schema, role đang enable và database link identity.

## 17. Audit và vận hành

Một ranh giới quyền cần có khả năng kiểm tra sau khi triển khai.

Theo chính sách database, có thể audit:

- EXECUTE trên package nhạy cảm.
- SELECT/UPDATE/DELETE trên object quan trọng.
- Thay đổi role và object grants.
- Tạo/xóa synonym public.
- Tạo/sửa database link.
- Remote account login và hoạt động tại remote database.

Unified Auditing và các audit policy có thể hỗ trợ theo dõi tùy phiên bản/cấu hình. Không bật audit quá rộng mà không có kế hoạch dung lượng, retention và phân tích.

Với package API, nên ghi application module/action, user context và mã giao dịch nghiệp vụ. Không ghi password, token hoặc dữ liệu cá nhân nhạy cảm vào audit payload.

Với database link:

- Theo dõi remote availability và latency.
- Dùng account riêng cho từng integration quan trọng.
- Xoay vòng credential.
- Kiểm tra quyền remote theo định kỳ.
- Hạn chế public link.
- Dùng Oracle Net encryption/TCPS theo yêu cầu bảo mật.
- Kiểm soát transaction phân tán và retry.
- Không để remote account có quyền DBA hoặc quyền toàn schema nếu không cần.

## 18. Quy trình thiết kế access path

Khi thiết kế một luồng truy cập mới:

1. Xác định dữ liệu gốc và owner.
2. Liệt kê cột/hàng mà consumer được phép thấy.
3. Quyết định dùng view cho read interface hay package cho business operation.
4. Chọn AUTHID DEFINER hoặc CURRENT_USER theo quyền runtime mong muốn.
5. Cấp direct grants tối thiểu cho view/package owner.
6. Cấp SELECT/EXECUTE cho role hoặc user consumer.
7. Tạo private synonym nếu cần tên truy cập thuận tiện.
8. Nếu truy cập remote, chọn database link type và remote identity.
9. Cấp remote object privilege tối thiểu.
10. Kiểm tra data dictionary và dependency.
11. Chạy positive và negative security tests bằng user ứng dụng.
12. Thiết lập audit, credential rotation và runbook revoke/rollback.

### 18.1. Revoke và thu hồi quyền

Ví dụ thu hồi quyền đọc view:

~~~sql
REVOKE SELECT ON data_owner.v_open_orders FROM app_read;
~~~

Thu hồi EXECUTE package:

~~~sql
REVOKE EXECUTE ON api_owner.order_api FROM app_writer;
~~~

Thu hồi quyền trên bảng khỏi package owner:

~~~sql
REVOKE UPDATE ON data_owner.orders FROM api_owner;
~~~

Nếu quyền đến từ role, thu hồi role grant hoặc privilege được cấp cho role theo phạm vi. Khi revoke, kiểm tra các ứng dụng phụ thuộc để tránh gián đoạn ngoài dự kiến.

Xóa private link:

~~~sql
DROP DATABASE LINK reporting_link;
~~~

Lệnh phải chạy trong schema sở hữu private link. Public link cần thao tác tương ứng với quyền quản trị và phạm vi public. Trước khi xóa, kiểm tra view/package/synonym/job phụ thuộc.

## 19. Các sai lầm thiết kế thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ synonym cấp quyền | User vẫn bị ORA-00942/ORA-01031 | Grant privilege trên target object |
| Dùng public synonym như public data access | Tưởng mọi user có thể SELECT | Phân biệt namespace với object privilege |
| Grant SELECT bảng gốc cùng lúc grant view | User bỏ qua view filter/projection | Thu hồi quyền base table không cần thiết |
| Cấp EXECUTE package cho PUBLIC | Mở API cho toàn database | Grant role/user cụ thể |
| Package definer owner có quyền DBA | Lỗi package có thể tạo privilege escalation | Owner chuyên biệt và least privilege |
| Chỉ cấp privilege qua role cho definer package | Stored code thiếu direct grant | Grant object privilege trực tiếp cho owner |
| Chọn AUTHID CURRENT_USER theo cảm tính | Kết quả phụ thuộc quyền caller và có thể ORA-06598 | Chốt contract và kiểm tra INHERIT PRIVILEGES |
| Dùng CURRENT_SCHEMA như quyền user | Phân giải tên đổi nhưng privilege không đổi | Dùng grant/role đúng mục tiêu |
| Nối input vào dynamic SQL trong definer package | SQL injection dùng quyền owner | Bind values, whitelist identifier |
| Dùng fixed-user link quyền rộng cho nhiều schema | Nhiều local user dùng chung remote identity mạnh | Remote account riêng, quyền tối thiểu, private link |
| Public DB link tới remote admin account | Mở rộng quyền remote tới nhiều local user | Tránh public link hoặc giới hạn remote identity |
| Nghĩ remote SELECT grant là local link privilege | Thiếu một lớp quyền | Kiểm tra link owner/type và remote object privilege |
| Synonym remote được xem là security control | Không thay đổi remote identity | Kiểm tra remote grant và link identity |
| Không kiểm thử bằng app user | Bỏ sót role/direct-grant/definer-rights behavior | Test bằng principal thật |
| Không có audit/credential rotation | Khó điều tra và thu hồi | Runbook và audit policy |

## 20. Checklist bảo mật trước production

### Synonym và view

- [ ] Xác định rõ target owner/object của từng synonym.
- [ ] Không coi private/public synonym là privilege.
- [ ] Cấp quyền trên target object/view/package.
- [ ] View chỉ công bố cột và hàng cần thiết.
- [ ] Không cấp trực tiếp bảng gốc cho consumer nếu view là boundary.
- [ ] Kiểm tra WITH CHECK OPTION/READ ONLY theo nhu cầu.
- [ ] Kiểm tra grant option khi grant quyền trên view được tạo từ object owner khác.
- [ ] Kiểm tra đường truy cập phụ qua synonym/view/package khác.

### Package và AUTHID

- [ ] AUTHID được khai báo rõ và phù hợp contract.
- [ ] Definer-rights owner là schema chuyên biệt.
- [ ] Owner chỉ có direct grants cần thiết.
- [ ] Consumer chỉ có EXECUTE trên package cần dùng.
- [ ] Không cấp EXECUTE cho PUBLIC nếu không cần.
- [ ] Dynamic SQL dùng bind values và whitelist identifier.
- [ ] Kiểm tra INHERIT PRIVILEGES với invoker-rights code.
- [ ] Validation và authorization được thực hiện trong API.
- [ ] Positive/negative tests chạy bằng application user.

### Database link

- [ ] Chọn private/public và fixed/connected/current-user link có chủ đích.
- [ ] Remote identity được xác định và ghi trong thiết kế.
- [ ] Remote account chỉ có quyền object cần thiết.
- [ ] Tránh remote account có DBA/ANY privileges.
- [ ] Không đưa password vào source, log hoặc tài liệu.
- [ ] Có quy trình xoay vòng credential.
- [ ] Kiểm soát remote network encryption và service resolution.
- [ ] Kiểm tra synonym/package/view phụ thuộc link.
- [ ] Đánh giá distributed transaction và retry behavior.
- [ ] Theo dõi remote access bằng audit và monitoring.

## 21. Ghi nhớ cốt lõi

- Synonym chỉ là bí danh phân giải tên; quyền được kiểm tra trên object đích.
- Public synonym làm tên có thể được phân giải rộng hơn nhưng không làm object trở thành public-access.
- View có thể giới hạn cột/hàng; consumer cần quyền trên view và không nên có quyền bảng gốc nếu view là ranh giới bảo mật.
- WITH CHECK OPTION giữ hàng DML qua view thỏa predicate; WITH READ ONLY cấm DML qua view.
- View owner cần quyền nền phù hợp; grant trên view có thể cần grant option trên object nền nếu owner không sở hữu object.
- Package cung cấp API nghiệp vụ; EXECUTE trên package không đồng nghĩa consumer có DML trực tiếp trên bảng.
- AUTHID DEFINER chạy theo quyền owner; role của caller không cấp quyền cho definer-rights SQL, nên owner cần direct grants phù hợp.
- AUTHID CURRENT_USER chạy theo quyền invoker; cần xem role, schema context và INHERIT PRIVILEGES.
- CURRENT_SCHEMA thay đổi cách phân giải tên, không thay đổi danh tính bảo mật hoặc cấp thêm privilege.
- Definer-rights package có thể là privilege boundary mạnh nhưng dynamic SQL không an toàn có thể biến nó thành privilege escalation.
- Database link tạo remote session bằng fixed, connected hoặc current-user identity theo cấu hình; remote database kiểm tra quyền của remote identity.
- Private link thuộc schema owner; public link mở khả năng sử dụng link rộng hơn và cần thận trọng.
- Remote SELECT grant và quyền sử dụng local database link là hai điều kiện khác nhau.
- Synonym trỏ qua database link vẫn không cấp quyền remote.
- Least privilege cần áp dụng ở cả local owner, application user, package owner và remote account.
- Kiểm thử cả thao tác được phép lẫn thao tác phải bị từ chối bằng đúng user ứng dụng.
- Dùng data dictionary, audit và runbook để duy trì quyền, link, credential và dependency sau triển khai.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — Users, roles, object privileges, definer/invoker rights, database links and security policies.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/) — AUTHID, invoker rights, definer rights, stored program units and dynamic SQL.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — CREATE VIEW, CREATE SYNONYM, GRANT and REVOKE.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Database links, users, privileges and distributed database administration.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — USER/ALL/DBA_TAB_PRIVS, SESSION_ROLES, ALL_SYNONYMS, ALL_DB_LINKS and dependency views.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html) — Validation of SQL identifiers and literals in dynamic SQL.

Privilege checks, database-link authentication, invoker-rights behavior and dictionary metadata can vary by Oracle release and deployment configuration. Verify the exact release documentation, test with real application principals, and review both local and remote grants before exposing an access path in production.

