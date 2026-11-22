# Quản lý quyền, tài nguyên và tính có thể kiểm thử của package

Trong PL/SQL, package thường là ranh giới mà ứng dụng dùng để gọi một nhóm thao tác liên quan. Package có thể đọc hoặc thay đổi dữ liệu của nhiều bảng, gọi package khác, giữ trạng thái trong phiên và thực hiện những thao tác tiêu tốn tài nguyên. Vì vậy, thiết kế package cần trả lời đồng thời ba câu hỏi:

- Ai được phép gọi API của package, và khi được gọi thì câu lệnh bên trong chạy bằng quyền của ai?
- Package sử dụng tài nguyên của phiên và cơ sở dữ liệu như thế nào, đặc biệt khi ứng dụng dùng connection pool?
- Có thể kiểm tra hành vi, quyền truy cập và giới hạn tài nguyên của package một cách lặp lại, độc lập với dữ liệu thật hay không?

Ba câu hỏi này liên quan trực tiếp đến nhau. Một package chạy với quyền chủ sở hữu có thể giúp ứng dụng chỉ cần quyền `EXECUTE`, nhưng nếu cấp quyền quá rộng thì package trở thành một đường truy cập dữ liệu nguy hiểm. Một package giữ nhiều biến toàn cục có thể chạy đúng trong một phiên thử nghiệm nhưng làm rò rỉ trạng thái giữa hai yêu cầu khi phiên được tái sử dụng. Một package tự `COMMIT` có thể khiến bài kiểm thử không còn khả năng hoàn tác dữ liệu sau mỗi ca chạy.

## 1. Package là ranh giới API và ranh giới bảo mật

Một package PL/SQL thường gồm hai phần:

- **Package specification (spec):** khai báo các thủ tục, hàm, kiểu dữ liệu, hằng số và biến được phép truy cập từ bên ngoài. Đây là hợp đồng công khai của package.
- **Package body:** cài đặt các thủ tục và hàm trong spec, đồng thời có thể chứa thủ tục, hàm, biến và con trỏ riêng chỉ dùng nội bộ.

Ví dụ, ứng dụng chỉ cần biết cách tạo đơn hàng. Nó không cần biết package truy vấn bảng nào, kiểm tra tồn kho ra sao hoặc ghi lịch sử vào đâu.

```sql
CREATE OR REPLACE PACKAGE app_owner.order_api
AUTHID DEFINER
AS
    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_product_id  IN NUMBER,
        p_quantity    IN NUMBER
    );
END order_api;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY app_owner.order_api
AS
    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_product_id  IN NUMBER,
        p_quantity    IN NUMBER
    )
    IS
    BEGIN
        -- Kiểm tra dữ liệu và thực hiện nghiệp vụ tại đây.
        NULL;
    END create_order;
END order_api;
/
```

Người dùng bên ngoài chỉ nhìn thấy `create_order` vì đó là thành phần công khai trong spec. Các thủ tục nội bộ trong body không thể được gọi trực tiếp từ schema khác. Thiết kế spec nhỏ và ổn định giúp giới hạn bề mặt bảo mật: chỉ công bố những thao tác mà ứng dụng thực sự cần.

Oracle cấp quyền `EXECUTE` ở cấp package. Khi một user được cấp `EXECUTE` trên package, user đó có thể gọi các subprogram công khai trong package; quyền này không mở trực tiếp các thành phần riêng trong body. Nếu hai nhóm người dùng cần hai tập thao tác khác nhau, có thể tách API thành các package nhỏ hơn, thay vì đưa mọi thao tác nhạy cảm vào một package rồi cấp `EXECUTE` cho tất cả.

## 2. Quyền gọi package và quyền thực thi câu lệnh bên trong

Khi phân tích quyền của một lời gọi package, cần tách hai lớp quyền:

1. **Quyền của caller:** user hoặc role nào được phép gọi package.
2. **Quyền của code đang chạy:** các câu lệnh SQL và lời gọi package khác bên trong được kiểm tra theo quyền của chủ sở hữu hay người gọi.

Hai lớp này không đồng nghĩa. Caller có thể được phép gọi package nhưng không có quyền `SELECT` trực tiếp trên bảng mà package sử dụng. Trường hợp đó có thể là thiết kế có chủ đích khi package là API nghiệp vụ được kiểm soát.

### 2.1. Cấp quyền EXECUTE theo nguyên tắc tối thiểu

Ví dụ có ba schema:

| Schema | Vai trò |
|---|---|
| `DATA_OWNER` | Sở hữu các bảng dữ liệu nghiệp vụ |
| `APP_OWNER` | Sở hữu package API |
| `APP_RUNTIME` | Tài khoản ứng dụng dùng khi kết nối cơ sở dữ liệu |

Chủ sở hữu package cần quyền trực tiếp trên các object thuộc schema khác mà code sử dụng. Sau đó, tài khoản chạy ứng dụng chỉ cần quyền gọi API nếu package được thiết kế theo quyền chủ sở hữu.

```sql
-- Cấp quyền trực tiếp cho schema sở hữu package.
GRANT SELECT, INSERT, UPDATE
ON data_owner.orders
TO app_owner;

-- Tạo role đại diện cho nhóm được phép gọi API.
CREATE ROLE order_api_executor;

GRANT EXECUTE
ON app_owner.order_api
TO order_api_executor;

GRANT order_api_executor TO app_runtime;
```

Khi quyền được cấp qua role, quản trị viên có thể quản lý quyền gọi API theo nhóm. Nếu một tài khoản chỉ cần một số API, hãy cấp role tương ứng thay vì cấp `EXECUTE` trên mọi package của schema.

Không nên mặc định cấp quyền cho `PUBLIC`:

```sql
-- Cân nhắc kỹ trước khi cấp quyền cho mọi user trong database.
GRANT EXECUTE ON app_owner.order_api TO PUBLIC;
```

Quyền `PUBLIC` làm API có thể được gọi rộng rãi hơn dự kiến. Nếu một package chứa thao tác quản trị, dữ liệu cá nhân hoặc nghiệp vụ nhạy cảm, quyền này có thể biến package thành một điểm truy cập ngoài ý muốn.

Thu hồi quyền khi không còn nhu cầu:

```sql
REVOKE EXECUTE
ON app_owner.order_api
FROM order_api_executor;
```

**Synonym không thay thế quyền truy cập.** Public synonym hoặc private synonym chỉ giúp tham chiếu object bằng tên ngắn hơn. User vẫn cần quyền thích hợp trên package đích. Tương tự, việc biết tên schema, package hoặc thủ tục không tự tạo ra quyền gọi.

### 2.2. AUTHID DEFINER: chạy bằng quyền chủ sở hữu

`AUTHID DEFINER` là chế độ mặc định nếu package không khai báo `AUTHID`. Trong chế độ này, các câu lệnh trong package chạy theo quyền của schema sở hữu package, gọi là *definer*.

Ví dụ, `APP_RUNTIME` được cấp `EXECUTE` trên `APP_OWNER.ORDER_API`, còn `APP_OWNER` được cấp trực tiếp quyền thao tác trên `DATA_OWNER.ORDERS`. Khi `APP_RUNTIME` gọi `ORDER_API.CREATE_ORDER`, package thực thi câu lệnh theo quyền của `APP_OWNER`. `APP_RUNTIME` không cần được cấp quyền `INSERT` trực tiếp trên `DATA_OWNER.ORDERS` chỉ để gọi thao tác đã được package công bố.

Đây là cách xây dựng API dữ liệu thường gặp: ứng dụng không truy cập tùy ý vào bảng mà chỉ gọi các thao tác đã được package kiểm soát. Tuy nhiên, cần nhớ rằng quyền của chủ sở hữu có thể mạnh hơn quyền của caller. Mỗi thủ tục công khai phải kiểm tra dữ liệu đầu vào và các điều kiện nghiệp vụ phù hợp; không nên cho phép caller truyền tên bảng, câu SQL hoặc biểu thức tùy ý để tận dụng quyền của definer.

Một điểm dễ gây lỗi là **role không được bật bên trong đơn vị PL/SQL chạy theo quyền definer**. Vì vậy, quyền trên bảng hoặc package phụ mà code cần dùng phải được cấp trực tiếp cho schema sở hữu package. Cấp quyền đó cho một role mà chủ sở hữu đang giữ thường không đủ để biên dịch hoặc thực thi static SQL trong definer-rights unit.

Ví dụ, nếu body truy vấn `DATA_OWNER.CUSTOMERS`, hãy cấp trực tiếp:

```sql
GRANT SELECT
ON data_owner.customers
TO app_owner;
```

Sau khi thay đổi quyền, biên dịch lại package nếu cần và kiểm tra lỗi biên dịch trong `USER_ERRORS` hoặc `ALL_ERRORS`. Không nên xử lý lỗi bằng cách cấp thêm quyền rộng cho `PUBLIC`.

### 2.3. AUTHID CURRENT_USER: chạy theo quyền người gọi

Khai báo `AUTHID CURRENT_USER` để package sử dụng ngữ cảnh quyền của *invoker* tại thời điểm chạy:

```sql
CREATE OR REPLACE PACKAGE app_owner.report_api
AUTHID CURRENT_USER
AS
    PROCEDURE show_my_report;
END report_api;
/
```

Chế độ này phù hợp khi cùng một package cần hoạt động với các tập dữ liệu mà mỗi caller được phép truy cập khác nhau. Ví dụ, một tiện ích báo cáo có thể truy vấn các view mà người gọi đã được cấp quyền. Khi đó, caller phải có các quyền cần thiết đối với object mà code thực sự truy cập.

Các khác biệt quan trọng:

| Khía cạnh | `AUTHID DEFINER` | `AUTHID CURRENT_USER` |
|---|---|---|
| Ngữ cảnh quyền khi chạy | Chủ sở hữu package | Người gọi hiện tại |
| Role của session trong unit | Bị vô hiệu hóa, trừ cơ chế role được cấp cho program unit theo phiên bản hỗ trợ | Các role đang bật của invoker có thể tham gia kiểm tra quyền |
| Caller có cần quyền trên bảng nội bộ không? | Thường không, nếu definer có quyền cần thiết và API cho phép thao tác | Có, theo quyền mà câu lệnh yêu cầu |
| Trường hợp thường dùng | API nghiệp vụ kiểm soát truy cập dữ liệu | Tiện ích cần tôn trọng quyền riêng của từng caller |

`CURRENT_USER` và `CURRENT_SCHEMA` là hai khái niệm khác nhau. `CURRENT_USER` xác định ngữ cảnh user phục vụ kiểm tra quyền; `CURRENT_SCHEMA` ảnh hưởng đến việc phân giải tên object không ghi rõ schema. Đổi `CURRENT_SCHEMA` không tự cấp thêm quyền và không biến một user thành chủ sở hữu object.

Với invoker-rights unit trên các phiên bản Oracle có kiểm soát `INHERIT PRIVILEGES`, chủ sở hữu unit còn phải có quyền kế thừa quyền của invoker theo chính sách database. Quản trị viên có thể cấp quyền này có phạm vi rõ ràng, ví dụ:

```sql
-- Ví dụ minh họa: APP_OWNER được phép kế thừa quyền của APP_RUNTIME.
GRANT INHERIT PRIVILEGES
ON USER app_runtime
TO app_owner;
```

Hãy đối chiếu phiên bản Oracle và chính sách bảo mật thực tế trước khi cấp quyền kế thừa. Không nên mở rộng thành quyền kế thừa trên mọi user nếu package chỉ cần phục vụ một nhóm caller xác định.

### 2.4. Role gắn với program unit và dynamic SQL

Ở các phiên bản Oracle hỗ trợ *Code Based Access Control* (CBAC), có thể cấp một role cho program unit. Role được bật trong phạm vi thực thi của unit, giúp giới hạn quyền theo từng package thay vì cấp toàn bộ quyền cho schema sở hữu package.

Ví dụ cú pháp thường dùng trên phiên bản hỗ trợ:

```sql
GRANT order_data_reader TO PACKAGE app_owner.order_api;
```

Đây là cơ chế nâng cao. Cần kiểm tra cú pháp và điều kiện hỗ trợ của phiên bản Oracle đang vận hành, đồng thời kiểm tra quyền hiệu lực khi package chạy. Không nên đưa CBAC vào chỉ để né việc hiểu rõ `AUTHID` hoặc để thay thế thiết kế quyền tối thiểu.

Dynamic SQL cần được xem xét riêng. Với câu lệnh được tạo bằng `EXECUTE IMMEDIATE` hoặc `DBMS_SQL`, việc kiểm tra quyền xảy ra khi câu lệnh được thực thi và phụ thuộc ngữ cảnh quyền của unit. Dữ liệu đầu vào không được ghép trực tiếp vào chuỗi SQL:

```sql
-- Dùng bind variable cho giá trị dữ liệu.
EXECUTE IMMEDIATE
    'SELECT status FROM data_owner.orders WHERE order_id = :1'
    INTO l_status
    USING p_order_id;
```

Bind variable không thay thế được tên bảng, tên cột hoặc từ khóa SQL. Nếu phải tạo dynamic SQL với identifier, hãy kiểm tra identifier theo allowlist và dùng các tiện ích xác thực phù hợp như `DBMS_ASSERT` khi thích hợp. Không cho caller cung cấp một đoạn SQL tùy ý để package thực thi bằng quyền definer.

## 3. Quản lý tài nguyên trong package

Package không có một hạn mức CPU hay bộ nhớ độc lập chỉ vì nó là package. Tài nguyên được sử dụng thông qua session, SQL statement, transaction và các dịch vụ database mà package gọi. Vì thế, quản lý tài nguyên cần kết hợp thiết kế code với cấu hình session và Oracle Database Resource Manager.

### 3.1. Trạng thái package tồn tại theo session

Biến khai báo ở cấp package body hoặc spec là trạng thái của package trong session. Trạng thái này có thể còn tồn tại giữa nhiều lần gọi package trong cùng một session.

```sql
CREATE OR REPLACE PACKAGE app_owner.request_context
AS
    g_request_count PLS_INTEGER := 0;

    PROCEDURE next_request;
END request_context;
/

CREATE OR REPLACE PACKAGE BODY app_owner.request_context
AS
    PROCEDURE next_request
    IS
    BEGIN
        g_request_count := g_request_count + 1;
    END next_request;
END request_context;
/
```

Trong cùng một session, `g_request_count` tiếp tục tăng sau mỗi lần gọi. Session khác có trạng thái package riêng. Điều này có một hệ quả quan trọng với ứng dụng dùng connection pool: một kết nối vật lý có thể lần lượt phục vụ nhiều yêu cầu logic của nhiều người dùng. Nếu package giữ `customer_id`, quyền tạm thời, bộ lọc hoặc dữ liệu request trong biến toàn cục, yêu cầu sau có thể nhìn thấy trạng thái còn sót lại từ yêu cầu trước.

Các cách xử lý an toàn:

- Ưu tiên truyền dữ liệu cần thiết qua tham số của thủ tục và hàm.
- Chỉ giữ trạng thái package khi có lý do rõ ràng và vòng đời của trạng thái đã được định nghĩa.
- Nếu bắt buộc giữ trạng thái theo session, cung cấp thao tác khởi tạo hoặc reset rõ ràng và gọi nó tại ranh giới vòng đời connection phù hợp.
- Khi pool tái sử dụng session, thiết lập lại context, role, package state và các thuộc tính session theo quy trình quản lý connection của ứng dụng.
- Không xem package variable như bộ nhớ dùng chung an toàn giữa nhiều session; mỗi session có trạng thái riêng.

`DBMS_SESSION.RESET_PACKAGE` có thể được dùng để reset trạng thái package trong session trong các trường hợp phù hợp. Đây là thao tác ảnh hưởng đến trạng thái package của session, nên cần phối hợp với connection pool và kiểm tra chi phí trước khi gọi thường xuyên. Một lựa chọn khác là thiết kế package không giữ trạng thái request qua nhiều lần gọi.

Oracle cũng hỗ trợ `PRAGMA SERIALLY_REUSABLE` cho một số package cần trạng thái tạm trong phạm vi một server call. Cơ chế này thay đổi vòng đời trạng thái package và không phù hợp nếu logic cần giữ biến qua nhiều lần gọi ở các server call khác nhau. Chỉ sử dụng sau khi đã hiểu vòng đời session/server call và các giới hạn của pragma trên phiên bản đang dùng.

Khi package hoặc dependency bị invalidation/recompile, trạng thái package hiện có có thể bị loại bỏ. Ứng dụng có thể gặp các lỗi như `ORA-04068` hoặc `ORA-04061` khi đang dùng package có state. Vì vậy, không nên dựa vào package state để lưu dữ liệu nghiệp vụ quan trọng hoặc trạng thái cần tồn tại bền vững. Với lỗi phát sinh trong lúc gọi, chỉ retry khi thao tác có tính idempotent hoặc đã xác định được transaction trước đó không hoàn tất; retry mù có thể tạo bản ghi trùng hoặc thực hiện nghiệp vụ hai lần.

### 3.2. Đóng cursor và giải phóng tài nguyên tạm

Các tài nguyên thường cần được quản lý trong package gồm:

- Explicit cursor và `REF CURSOR`.
- Cursor được mở qua `DBMS_SQL`.
- Collection lớn được nạp bằng `BULK COLLECT`.
- Temporary LOB.
- Lock và transaction được giữ trong thời gian dài.

Cursor mở thủ công phải được đóng cả ở đường chạy thành công lẫn đường xử lý exception. Nếu dùng cursor `FOR` loop, Oracle tự quản lý việc mở và đóng cursor cho vòng lặp đó; với explicit cursor hoặc `REF CURSOR`, cần xác định rõ thành phần nào sở hữu trách nhiệm đóng.

Ví dụ quản lý explicit cursor:

```sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM data_owner.orders
        WHERE status = 'PENDING';

    l_order_id data_owner.orders.order_id%TYPE;
BEGIN
    OPEN c_orders;

    LOOP
        FETCH c_orders INTO l_order_id;
        EXIT WHEN c_orders%NOTFOUND;

        -- Xử lý một đơn hàng.
        NULL;
    END LOOP;

    CLOSE c_orders;
EXCEPTION
    WHEN OTHERS THEN
        IF c_orders%ISOPEN THEN
            CLOSE c_orders;
        END IF;
        RAISE;
END;
/
```

Với `DBMS_SQL`, hãy gọi `DBMS_SQL.CLOSE_CURSOR` khi hoàn tất và cả khi xảy ra lỗi. Với temporary LOB do code tạo ra, giải phóng bằng `DBMS_LOB.FREETEMPORARY` khi không còn sử dụng và khi code sở hữu vòng đời của LOB. Không giải phóng một LOB mà caller hoặc thành phần khác vẫn đang sở hữu.

Tránh nạp một tập dữ liệu rất lớn vào collection chỉ để xử lý từng dòng. Có thể dùng `BULK COLLECT ... LIMIT` để giới hạn số dòng trong mỗi batch, kết hợp `FORALL` khi cần DML hàng loạt. `LIMIT` cần được chọn theo kích thước bản ghi và giới hạn bộ nhớ của môi trường, không phải một con số cố định áp dụng cho mọi hệ thống.

Nếu package trả về `REF CURSOR`, hợp đồng API cần nói rõ caller phải fetch và đóng cursor. Package mở cursor rồi trả cho caller thì thường không nên tự đóng cursor ngay trước khi trả về. Ngược lại, nếu package tự fetch toàn bộ dữ liệu, package phải tự đóng cursor trong mọi nhánh thực thi.

### 3.3. Transaction và lock

Một package nghiệp vụ thường nên để caller hoặc tầng điều phối transaction quyết định thời điểm `COMMIT` và `ROLLBACK`. Nếu một thủ tục thư viện tự `COMMIT`, caller có thể không còn khả năng hoàn tác toàn bộ một quy trình gồm nhiều package.

Ví dụ, ứng dụng thực hiện tạo đơn hàng, trừ tồn kho và ghi thanh toán trong một transaction. Nếu `ORDER_API.CREATE_ORDER` tự commit ngay sau khi thêm đơn hàng, lỗi ở bước trừ tồn kho sẽ để lại dữ liệu dở dang.

Chỉ dùng `PRAGMA AUTONOMOUS_TRANSACTION` khi thao tác thực sự độc lập với transaction chính, chẳng hạn ghi một bản ghi audit cần tồn tại ngay cả khi transaction nghiệp vụ rollback. Cần hiểu rõ việc autonomous transaction có thể commit riêng và nhìn thấy dữ liệu theo quy tắc transaction riêng. Không dùng nó như cách né lỗi transaction hoặc để làm cho test dễ chạy hơn.

Lock nên được giữ trong thời gian ngắn nhất có thể. Không gọi dịch vụ mạng chậm hoặc chờ người dùng trong khi transaction đang giữ row lock. Khi cần xử lý dài, cân nhắc chia công việc thành các bước có trạng thái và transaction ngắn, tùy yêu cầu nhất quán của nghiệp vụ.

### 3.4. Định danh và điều tiết workload

Oracle Database Resource Manager điều tiết workload ở cấp session/consumer group theo resource plan. Tùy cấu hình và phiên bản, resource plan có thể phân bổ CPU, giới hạn mức sử dụng tài nguyên, điều khiển số session hoạt động đồng thời hoặc đặt quy tắc chuyển nhóm khi session vượt ngưỡng.

Package không tự tạo một consumer group riêng. Muốn điều tiết một loại công việc do package thực hiện, ứng dụng cần giúp database nhận diện session hoặc thao tác. `DBMS_APPLICATION_INFO` có thể gắn module và action vào session:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'CREATE_ORDER'
    );
END;
/
```

Ở những điểm chuyển nghiệp vụ, có thể cập nhật action để phân biệt các hoạt động như `CREATE_ORDER`, `REBUILD_REPORT` hoặc `BATCH_CLOSE`. Quản trị viên có thể dùng thông tin module/action trong giám sát và xây dựng mapping rule của Resource Manager theo cấu hình phù hợp.

Nên thống nhất nơi chịu trách nhiệm đặt và khôi phục module/action. Nếu tầng ứng dụng đã đặt module cho request, package con không nên tùy tiện ghi đè module rồi xóa thông tin của tầng gọi. Có thể để tầng ứng dụng đặt module, còn package cập nhật action trong phạm vi được quy ước; khi kết thúc request, tầng sở hữu context khôi phục giá trị ban đầu.

Profile và quota cũng có vai trò riêng:

| Cơ chế | Phạm vi chính |
|---|---|
| Database Resource Manager | Điều tiết workload và tài nguyên của session/consumer group |
| Database profile | Một số giới hạn tài nguyên và chính sách ở cấp user/session; việc thực thi các giới hạn tài nguyên phụ thuộc cấu hình database như `RESOURCE_LIMIT` |
| Tablespace quota | Giới hạn dung lượng mà schema/user được phép sử dụng trong tablespace |
| Giới hạn trong code | Kích thước batch, số dòng xử lý, timeout nghiệp vụ, số lần retry và phạm vi dữ liệu |

Không nên nhầm quota tablespace với giới hạn bộ nhớ PL/SQL, hoặc nhầm profile của user với một hạn mức riêng cho từng package. Nếu nhiều package chạy trong cùng session, Resource Manager thường nhìn workload theo session/consumer group chứ không tự hiểu từng package nếu ứng dụng không gắn thông tin nhận diện.

## 4. Thiết kế package để dễ kiểm thử

Package dễ kiểm thử khi đầu vào, đầu ra, tác dụng phụ và quyền cần thiết đều có thể nhận biết. Mục tiêu là mỗi ca kiểm thử có thể thiết lập điều kiện, gọi một API và xác nhận kết quả mà không phụ thuộc vào trạng thái còn sót lại từ lần chạy trước.

### 4.1. Giữ spec nhỏ và tách nghiệp vụ khỏi truy cập dữ liệu

Không nên để một package vừa tính toán quy tắc nghiệp vụ, vừa truy vấn nhiều bảng, gửi thông báo, ghi file và điều khiển transaction. Khi các trách nhiệm bị trộn lẫn, một test nhỏ cũng cần dựng gần như toàn bộ môi trường.

Có thể chia thành các nhóm trách nhiệm:

| Nhóm package | Trách nhiệm |
|---|---|
| `ORDER_RULES` | Tính toán và kiểm tra quy tắc nghiệp vụ; ưu tiên hàm thuần |
| `ORDER_REPOSITORY` | Đọc và ghi dữ liệu đơn hàng |
| `ORDER_NOTIFICATION` | Gửi hoặc ghi nhận yêu cầu thông báo |
| `ORDER_API` | Điều phối các bước và cung cấp API cho ứng dụng |

Đây là cách phân chia theo trách nhiệm, không phải quy tắc bắt buộc mỗi bảng phải có một package. Hãy giữ số package vừa đủ để ranh giới có ý nghĩa và spec không bị phình to.

Hàm thuần nhận dữ liệu qua tham số và trả kết quả mà không phụ thuộc trạng thái session, bảng dữ liệu, thời gian hệ thống hoặc dịch vụ bên ngoài. Hàm như vậy thường dễ kiểm thử nhất.

```sql
CREATE OR REPLACE PACKAGE app_owner.order_rules
AS
    FUNCTION net_amount(
        p_gross         IN NUMBER,
        p_discount_pct  IN NUMBER
    ) RETURN NUMBER;
END order_rules;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY app_owner.order_rules
AS
    FUNCTION net_amount(
        p_gross         IN NUMBER,
        p_discount_pct  IN NUMBER
    ) RETURN NUMBER
    IS
    BEGIN
        IF p_gross IS NULL OR p_gross < 0 THEN
            RAISE_APPLICATION_ERROR(-20001, 'Gross amount must be non-negative');
        END IF;

        IF p_discount_pct IS NULL
           OR p_discount_pct < 0
           OR p_discount_pct > 100
        THEN
            RAISE_APPLICATION_ERROR(-20002, 'Discount must be between 0 and 100');
        END IF;

        RETURN ROUND(p_gross * (1 - p_discount_pct / 100), 2);
    END net_amount;
END order_rules;
/
```

Hàm không đọc bảng, không gọi `SYSDATE`, không dùng package variable và không commit. Vì vậy, kết quả chỉ phụ thuộc hai tham số. Có thể kiểm tra trực tiếp:

```sql
DECLARE
    l_actual NUMBER;
BEGIN
    l_actual := app_owner.order_rules.net_amount(100, 10);

    IF l_actual <> 90 THEN
        RAISE_APPLICATION_ERROR(-20990, 'Expected net amount 90');
    END IF;
END;
/
```

Ngoài trường hợp thông thường, cần kiểm tra biên như giảm giá bằng `0`, giảm giá bằng `100`, số tiền bằng `0`, giá trị âm và tham số `NULL`. Nếu nghiệp vụ quy định cách xử lý `NULL` khác, hãy thể hiện rõ trong hợp đồng API và test theo hợp đồng đó.

### 4.2. Làm rõ dependency và thời gian

Các dependency ẩn làm test khó lặp lại gồm:

- `SYSDATE` hoặc `SYSTIMESTAMP` được gọi ở nhiều nơi.
- `SYS_CONTEXT` dùng để đọc user, tenant hoặc request context.
- `DBMS_RANDOM` hoặc thứ tự sinh sequence được giả định là cố định.
- Package variable giữ cấu hình hoặc dữ liệu từ lần gọi trước.
- Truy vấn trực tiếp bảng thật hoặc gọi dịch vụ bên ngoài ngay trong hàm tính toán.

Khi logic phụ thuộc thời gian, có thể truyền thời điểm vào API nghiệp vụ hoặc gom việc lấy thời gian vào một adapter riêng. Khi cần giá trị ngẫu nhiên, hãy tách phần tạo giá trị khỏi phần quyết định nghiệp vụ. Với sequence, test nên xác nhận rằng mã được sinh và liên kết đúng, thay vì giả định sequence luôn bắt đầu từ một số cố định.

PL/SQL không có cơ chế interface/mock object giống một số ngôn ngữ hướng đối tượng. Có thể tạo điểm thay thế dependency bằng cách tách package truy cập dữ liệu và package nghiệp vụ, truyền dữ liệu cần tính toán qua tham số, hoặc biên dịch adapter tương ứng trong schema test độc lập. Tránh thay synonym hoặc sửa package dùng chung ngay trong một test chạy song song, vì cách đó tạo trạng thái toàn cục và có thể ảnh hưởng test khác.

### 4.3. Để caller kiểm soát transaction

Nếu package nghiệp vụ không tự commit, test có thể chuẩn bị dữ liệu, gọi API, kiểm tra kết quả rồi rollback:

```sql
SAVEPOINT before_order_test;

BEGIN
    app_owner.order_api.create_order(
        p_customer_id => 1001,
        p_product_id  => 501,
        p_quantity    => 2
    );

    -- Truy vấn và xác nhận dữ liệu do test tạo.
    -- Các assertion cụ thể tùy framework kiểm thử.
END;
/

ROLLBACK TO before_order_test;
```

Đoạn trên minh họa vòng đời transaction; nó chỉ rollback được các thay đổi thuộc transaction hiện tại. Autonomous transaction, DDL và tác dụng phụ bên ngoài không tự được hoàn tác theo cách này. Test cần có bước dọn dẹp riêng cho những tác dụng phụ đó.

### 4.4. Dùng framework kiểm thử và assertion rõ ràng

Có thể dùng `utPLSQL` để tổ chức suite, test case và assertion cho PL/SQL. Framework giúp chuẩn hóa cách chạy và báo cáo, nhưng không thay thế việc thiết kế package có đầu vào rõ ràng và tác dụng phụ được kiểm soát.

Một test case nên thể hiện ba phần:

1. **Arrange:** chuẩn bị dữ liệu và trạng thái cần thiết.
2. **Act:** gọi đúng API cần kiểm tra.
3. **Assert:** xác nhận kết quả, dữ liệu thay đổi và lỗi được phát ra khi đầu vào không hợp lệ.

Không nên chỉ kiểm tra rằng thủ tục chạy mà không phát sinh exception. Cần xác nhận kết quả nghiệp vụ cụ thể, chẳng hạn tổng tiền, trạng thái đơn hàng, số dòng được cập nhật hoặc mã lỗi theo hợp đồng.

### 4.5. Kiểm thử quyền như một phần của hành vi

Một package có thể chạy đúng khi đăng nhập bằng schema owner nhưng thất bại khi chạy bằng user ứng dụng. Vì vậy, test quyền phải dùng đúng các schema và role giống mô hình triển khai.

Với API definer-rights, có thể kiểm tra các điều kiện:

- `APP_OWNER` có quyền trực tiếp cần thiết trên bảng hoặc package phụ.
- `APP_RUNTIME` có `EXECUTE` trên API.
- `APP_RUNTIME` không có quyền trực tiếp trên bảng nội bộ nếu thiết kế không yêu cầu.
- Caller được phép gọi thao tác công khai và không thể gọi thành phần private trong body.
- Caller không được gọi package sau khi quyền `EXECUTE` bị thu hồi.

Với API invoker-rights, cần kiểm tra thêm caller có quyền trên các object mà unit truy cập hay không. Hãy thử cả trường hợp có quyền và thiếu quyền. Nếu ứng dụng dựa vào role, kiểm tra role đang bật ở thời điểm gọi; nếu code chạy trong definer-rights unit, kiểm tra riêng quy tắc role bị vô hiệu hóa hoặc role được cấp trực tiếp cho program unit theo cơ chế CBAC.

Không chạy toàn bộ test bảo mật chỉ bằng tài khoản DBA. Tài khoản DBA thường có quyền vượt xa tài khoản ứng dụng nên có thể che giấu lỗi cấu hình quyền.

## 5. Ma trận kiểm thử nên có

Một package quan trọng nên được kiểm tra ở nhiều lớp. Không phải mọi dự án đều cần cùng số lượng test, nhưng các nhóm dưới đây giúp tránh bỏ sót hành vi liên quan đến quyền và tài nguyên.

| Nhóm | Tình huống | Điều cần xác nhận |
|---|---|---|
| API | Gọi với dữ liệu hợp lệ | Kết quả đúng theo hợp đồng |
| Biên dữ liệu | `NULL`, âm, bằng 0, giá trị tối đa | Quy tắc biên và lỗi rõ ràng |
| Quyền gọi | Caller có `EXECUTE` | Gọi được API công khai |
| Quyền gọi | Caller không có `EXECUTE` | Bị từ chối |
| Definer rights | Owner có direct grant, caller không có quyền bảng | API hoạt động đúng phạm vi đã thiết kế |
| Invoker rights | Caller có hoặc thiếu quyền object | Kết quả phản ánh quyền của caller |
| Role | Quyền chỉ được cấp qua role | Xác nhận hành vi theo `AUTHID` và CBAC |
| Trạng thái | Gọi liên tiếp trong cùng session | Không rò rỉ dữ liệu giữa hai request |
| Connection pool | Tái sử dụng session cho caller/request khác | Context và package state được reset đúng |
| Cursor/LOB | Chạy thành công và phát sinh exception | Tài nguyên được đóng hoặc giải phóng |
| Dữ liệu lớn | Xử lý nhiều dòng | Bộ nhớ và thời gian nằm trong giới hạn chấp nhận |
| Transaction | Bước sau thất bại | Không commit dở dang ngoài hợp đồng |
| Đồng thời | Nhiều session gọi cùng API | Không có lỗi do giả định state dùng chung |
| Invalidation | Package/dependency được biên dịch lại | Ứng dụng xử lý trạng thái package bị loại bỏ an toàn |

Test tài nguyên cần chạy trong môi trường đủ gần production để quan sát hành vi session, cursor và Resource Manager. Một test unit chạy vài dòng dữ liệu không thể chứng minh package xử lý tốt hàng triệu dòng hoặc nhiều session đồng thời.

## 6. Theo dõi lỗi và chẩn đoán

Một số lỗi thường gặp khi triển khai package có liên quan đến quyền hoặc trạng thái:

| Lỗi | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `PLS-00201: identifier must be declared` | Tên object sai, object không nhìn thấy hoặc thiếu quyền cần thiết khi biên dịch | Kiểm tra schema, synonym, object tồn tại và direct grant cho owner |
| `ORA-01031: insufficient privileges` | Caller hoặc code đang chạy thiếu quyền tại thời điểm thực thi | Xác định `AUTHID`, user thực thi, role đang bật và quyền trên object |
| `ORA-04068: existing state of packages has been discarded` | Trạng thái package trong session bị loại bỏ, thường sau invalidation/recompile | Kiểm tra package state và dependency; bảo đảm caller không dựa vào state cũ |
| `ORA-04061: existing state of package has been invalidated` | Package có state bị invalidation | Kiểm tra lần biên dịch, dependency và cách ứng dụng xử lý session |
| `ORA-06508: PL/SQL: could not find program unit being called` | Program unit không khả dụng hoặc dependency chưa hợp lệ | Kiểm tra trạng thái `VALID/INVALID`, lỗi biên dịch và thứ tự triển khai |

Khi kiểm tra trạng thái object, có thể dùng các view phù hợp với quyền của tài khoản:

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'ORDER_API';
```

```sql
SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'ORDER_API'
ORDER BY sequence;
```

Nếu package thuộc schema khác và tài khoản có quyền xem metadata, có thể dùng `ALL_OBJECTS`, `ALL_ERRORS` hoặc các view DBA tương ứng. Khi chẩn đoán, hãy ghi nhận cả user đang kết nối, `CURRENT_USER`, `CURRENT_SCHEMA`, role đang bật và module/action của session. Chỉ nhìn vào mã nguồn package thường chưa đủ để giải thích một lỗi quyền xảy ra ở runtime.

Không nên dùng `WHEN OTHERS THEN NULL` để che lỗi. Nếu cần bổ sung xử lý, hãy ghi nhận ngữ cảnh cần thiết rồi phát sinh lại lỗi bằng `RAISE`, trừ khi hợp đồng API quy định rõ một cách chuyển đổi lỗi khác. Việc nuốt exception làm test khó phát hiện lỗi và khiến ứng dụng không biết thao tác đã thất bại.

## 7. Quy trình thiết kế và triển khai

Khi tạo hoặc chỉnh sửa package, có thể đi theo trình tự sau:

1. **Xác định API:** liệt kê đúng thủ tục, hàm và kiểu dữ liệu cần công khai; giữ implementation trong body.
2. **Chọn AUTHID:** quyết định thao tác cần chạy bằng quyền owner hay invoker; ghi rõ lý do trong thiết kế.
3. **Lập ma trận quyền:** xác định caller nào được `EXECUTE`, owner cần direct grant nào và có cần CBAC hay không.
4. **Rà soát dynamic SQL:** dùng bind variable cho giá trị, xác thực identifier và không cho caller đưa SQL tùy ý vào definer-rights API.
5. **Rà soát vòng đời tài nguyên:** xác định ai đóng cursor, ai giải phóng LOB, batch size, transaction boundary và vòng đời package state.
6. **Rà soát session pooling:** bảo đảm request mới không kế thừa context hoặc biến package của request trước.
7. **Thiết kế test:** tách logic thuần, chuẩn bị fixture, xác nhận kết quả và các nhánh lỗi.
8. **Test bằng đúng user ứng dụng:** xác nhận cả quyền được phép và quyền bị từ chối.
9. **Quan sát workload:** gắn module/action, đo thời gian và tài nguyên trên dữ liệu có kích thước thực tế.
10. **Triển khai có kiểm soát:** biên dịch package, kiểm tra `USER_ERRORS`/`ALL_ERRORS`, kiểm tra trạng thái dependency và xác nhận lại quyền sau khi triển khai.

Một package tốt có spec rõ ràng, quyền được cấp theo nhu cầu, trạng thái session có vòng đời xác định, tài nguyên được giải phóng đúng lúc và các hành vi quan trọng có thể được kiểm tra bằng test lặp lại. Khi những điều kiện này được thiết kế ngay từ đầu, package sẽ dễ vận hành và ít phụ thuộc vào quyền quá rộng hoặc trạng thái ngầm của database.
