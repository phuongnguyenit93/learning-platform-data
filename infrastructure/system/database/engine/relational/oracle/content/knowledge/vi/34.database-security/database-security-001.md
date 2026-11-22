# Nguyên tắc quyền tối thiểu và tách tài khoản quản trị/ứng dụng

Trong Oracle Database, bảo mật tài khoản không chỉ là đặt mật khẩu mạnh. Một thiết kế an toàn cần giới hạn mỗi tài khoản ở đúng công việc nó phải thực hiện, tách quyền quản trị khỏi quyền chạy ứng dụng, kiểm soát cách cấp quyền và có khả năng truy vết hành động. Hai nguyên tắc nền tảng là **least privilege** (quyền tối thiểu) và **separation of duties** (phân tách nhiệm vụ).

Tài khoản ứng dụng thường chỉ cần kết nối và thực hiện một tập thao tác nghiệp vụ đã xác định. Tài khoản quản trị cần quyền rộng hơn để triển khai, vận hành hoặc xử lý sự cố, nhưng chỉ được sử dụng bởi người và quy trình có trách nhiệm tương ứng. Nếu ứng dụng chạy bằng tài khoản DBA hoặc dùng chung mật khẩu với tài khoản triển khai, một lỗi SQL injection, lộ secret hoặc lỗi trong code có thể biến thành quyền kiểm soát gần như toàn bộ database.

Thiết kế đúng trong Oracle cần kết hợp user/schema, role, system privilege, object privilege, quyền thực thi PL/SQL, quản lý secret, audit và quy trình vận hành.

## 1. Quyền tối thiểu là gì?

Least privilege nghĩa là một user, service hoặc tiến trình chỉ được cấp những quyền cần thiết để hoàn thành nhiệm vụ đã xác định, trong phạm vi dữ liệu và thời gian cần thiết.

Ví dụ, một ứng dụng bán hàng có thể cần:

- Đọc một số bảng danh mục.
- Gọi package tạo đơn hàng.
- Gọi procedure cập nhật trạng thái thanh toán.
- Đọc view tra cứu đơn hàng của khách hàng hiện tại.

Ứng dụng đó thường không cần:

- CREATE USER hoặc ALTER USER.
- DROP ANY TABLE hoặc ALTER ANY TABLE.
- SELECT ANY TABLE hoặc UPDATE ANY TABLE.
- Quyền DBA hoặc SYSDBA.
- Quyền đọc mọi schema trong database.
- Quyền thay đổi tham số instance hoặc cấu hình listener.

Một tài khoản có nhiều quyền hơn nhu cầu sẽ làm tăng phạm vi ảnh hưởng khi mật khẩu bị lộ, ứng dụng có lỗi hoặc một câu SQL bị khai thác.

### Nguyên tắc cần áp dụng

1. Cấp quyền theo nhiệm vụ cụ thể, không theo sự tiện lợi tạm thời.
2. Ưu tiên quyền trên object cụ thể thay vì system privilege rộng.
3. Cấp quyền qua role có tên và có chủ sở hữu rõ ràng.
4. Tách tài khoản con người, tài khoản ứng dụng, tài khoản triển khai và tài khoản vận hành.
5. Dùng tài khoản riêng theo môi trường và theo service khi có thể.
6. Thu hồi quyền không còn cần thiết và rà soát định kỳ.
7. Ghi nhận ai đã cấp quyền, quyền được dùng ở đâu và ai chịu trách nhiệm.

## 2. User và schema trong Oracle

Trong Oracle Database, user là danh tính dùng để xác thực và sở hữu các đối tượng database. Schema là tập hợp các object thuộc sở hữu của user đó. Vì vậy, khi tạo một user mới, Oracle đồng thời tạo một schema cùng tên.

Ví dụ:

~~~sql
CREATE USER app_owner
  IDENTIFIED BY "Replace-With-A-Managed-Secret";
~~~

User APP_OWNER có schema APP_OWNER và có thể sở hữu bảng, view, sequence, package hoặc các object khác. Tuy nhiên, tạo user không đồng nghĩa user có thể đăng nhập hoặc tạo object. Cần cấp quyền phù hợp.

Trong một kiến trúc ứng dụng, có thể tách:

| User/schema | Vai trò |
|---|---|
| APP_OWNER | Sở hữu bảng, sequence, view và PL/SQL nghiệp vụ |
| APP_RUNTIME | Tài khoản kết nối của ứng dụng khi chạy nghiệp vụ |
| APP_DEPLOY | Tài khoản hoặc danh tính triển khai schema trong cửa sổ release |
| APP_READONLY | Tài khoản đọc phục vụ báo cáo hoặc hỗ trợ |
| DBA_NAMED_USER | Tài khoản cá nhân của DBA |
| MONITOR_USER | Danh tính giám sát với các quyền đọc được phê duyệt |

Không nhất thiết mọi hệ thống phải có đúng các user trên. Mục tiêu là làm rõ quyền sở hữu object, danh tính chạy ứng dụng, danh tính triển khai và danh tính quản trị.

### Vì sao không nên để ứng dụng sở hữu schema?

Nếu ứng dụng kết nối bằng user sở hữu toàn bộ bảng và package, bất kỳ SQL nào chạy dưới user đó đều có thể sử dụng các quyền mà owner đang có. Nếu runtime credential bị lộ, kẻ tấn công có thể đọc hoặc thay đổi dữ liệu, tạo object, sửa package hoặc xóa object tùy quyền owner.

Một thiết kế chặt hơn là dùng APP_OWNER làm schema owner và APP_RUNTIME làm tài khoản kết nối. APP_RUNTIME chỉ nhận CREATE SESSION và quyền cần thiết để gọi các package/view được công bố.

## 3. Phân tách tài khoản quản trị và tài khoản ứng dụng

Tài khoản quản trị và tài khoản ứng dụng có mục đích khác nhau:

| Đặc điểm | Tài khoản quản trị | Tài khoản ứng dụng |
|---|---|---|
| Người hoặc tiến trình sử dụng | DBA, vận hành, release automation được phê duyệt | Application service |
| Mục tiêu | Quản lý database, schema, backup, cấu hình và sự cố | Thực hiện nghiệp vụ ứng dụng |
| Quyền | Chỉ cấp quyền quản trị cần cho nhiệm vụ và phạm vi | Quyền kết nối và quyền trên API database được công bố |
| Cách xác thực | Danh tính cá nhân, MFA ở tầng truy cập, wallet hoặc phương thức bảo mật phù hợp | Secret manager, wallet hoặc cơ chế xác thực service |
| Thời gian sử dụng | Theo phiên làm việc hoặc cửa sổ thay đổi | Theo vòng đời service |
| Audit | Phải truy vết đến cá nhân hoặc quy trình quản trị | Phải truy vết đến service/module và request khi có thể |

Không dùng tài khoản SYS, SYSTEM hoặc user có DBA role làm credential trong connection pool của ứng dụng. Những tài khoản này có phạm vi quyền rất rộng và được thiết kế cho quản trị database.

Tài khoản ứng dụng cũng không nên dùng chung với tài khoản triển khai. Việc triển khai cần thay đổi object và đôi khi cần DDL; runtime thông thường chỉ cần đọc/ghi dữ liệu qua API nghiệp vụ. Nếu dùng cùng một user, runtime sẽ phải giữ những quyền DDL không cần thiết.

## 4. System privilege và object privilege

Oracle có hai nhóm quyền quan trọng:

### System privilege

System privilege cho phép thực hiện một loại hành động trong database hoặc trên phạm vi nhiều object. Ví dụ:

- CREATE SESSION: đăng nhập database.
- CREATE TABLE: tạo bảng trong schema của chính user, khi có quota phù hợp.
- CREATE VIEW: tạo view trong schema của user.
- CREATE PROCEDURE: tạo procedure, function hoặc package trong schema của user.
- CREATE USER: tạo user.
- ALTER USER: thay đổi thuộc tính user.
- DROP ANY TABLE: xóa bảng trong schema bất kỳ.
- SELECT ANY TABLE: đọc bảng/view trong nhiều schema theo phạm vi privilege.

Một số system privilege có hậu tố ANY có phạm vi rất rộng. Không cấp các quyền này cho APP_RUNTIME chỉ để làm cho một câu SQL chạy được.

### Object privilege

Object privilege cấp quyền trên một object cụ thể:

- SELECT trên bảng hoặc view.
- INSERT, UPDATE, DELETE trên bảng hoặc view khi thao tác được hỗ trợ.
- EXECUTE trên procedure, function hoặc package.
- REFERENCES trên bảng hoặc cột phù hợp.
- READ hoặc WRITE trên một số object như DIRECTORY tùy loại object và phiên bản.

Ví dụ:

~~~sql
GRANT SELECT ON app_owner.product_catalog TO app_runtime;
GRANT EXECUTE ON app_owner.order_api TO app_runtime;
~~~

APP_RUNTIME chỉ được đọc PRODUCT_CATALOG và gọi ORDER_API. Nó không tự động có quyền SELECT trên mọi bảng của APP_OWNER.

### Ưu tiên quyền hẹp

Nếu ứng dụng chỉ cần đọc một view đã giới hạn cột hoặc hàng, hãy cân nhắc cấp SELECT trên view thay vì bảng gốc. Nếu ứng dụng chỉ cần thực hiện một thao tác nghiệp vụ, cấp EXECUTE trên package API có thể giới hạn bề mặt truy cập tốt hơn cấp trực tiếp INSERT/UPDATE/DELETE trên nhiều bảng.

## 5. Thiết kế role theo nhiệm vụ

Role là tập hợp các privilege có thể cấp cho user hoặc role khác. Dùng role giúp quản lý quyền theo chức năng thay vì cấp từng quyền riêng lẻ cho từng user.

Ví dụ tạo role cho runtime:

~~~sql
CREATE ROLE app_runtime_role;

GRANT CREATE SESSION TO app_runtime_role;
GRANT SELECT ON app_owner.product_catalog TO app_runtime_role;
GRANT EXECUTE ON app_owner.order_api TO app_runtime_role;

GRANT app_runtime_role TO app_runtime;
~~~

Tài khoản APP_RUNTIME nhận các quyền thông qua APP_RUNTIME_ROLE. Khi cần thay đổi quyền của nhóm runtime, DBA có thể sửa role thay vì quản lý từng user độc lập.

Có thể thiết kế nhiều role:

| Role | Quyền tiêu biểu |
|---|---|
| APP_RUNTIME_ROLE | CREATE SESSION, SELECT view tra cứu, EXECUTE package nghiệp vụ |
| APP_REPORT_ROLE | SELECT các view báo cáo được duyệt |
| APP_SUPPORT_READ_ROLE | Đọc một số view chẩn đoán dữ liệu ứng dụng |
| APP_DEPLOY_ROLE | Quyền DDL cần thiết trong schema ứng dụng, chỉ dùng khi triển khai |
| APP_BATCH_ROLE | Quyền cho batch job cụ thể |

Không nên tạo một role APP_ALL_ROLE chứa DBA, SELECT ANY TABLE, CREATE ANY PROCEDURE và nhiều quyền rộng rồi cấp cho mọi user. Role cần thể hiện nhiệm vụ cụ thể và được rà soát như một hợp đồng quyền.

### Quyền mặc định và role

Role có thể được cấu hình là default hoặc non-default cho user. Default role được bật khi user đăng nhập theo cấu hình. Có thể kiểm tra role của user và trạng thái role trong các view dictionary phù hợp.

Ví dụ giới hạn default role:

~~~sql
ALTER USER app_runtime
  DEFAULT ROLE app_runtime_role;
~~~

Trong một số phiên làm việc, user có thể dùng SET ROLE để bật hoặc tắt role được cấp nếu cấu hình cho phép. Tuy nhiên, không nên xem việc tắt role như một ranh giới bảo mật đủ mạnh nếu user vẫn có thể bật lại role đó.

## 6. Tài khoản runtime chỉ gọi API database

Một mẫu thiết kế hữu ích là schema owner sở hữu bảng và package; runtime user chỉ được EXECUTE package. Package định nghĩa các thao tác nghiệp vụ hợp lệ.

Ví dụ owner tạo package:

~~~sql
CREATE OR REPLACE PACKAGE app_owner.order_api AS
  PROCEDURE create_order(
    p_order_id    IN NUMBER,
    p_customer_id IN NUMBER
  );
END order_api;
/

CREATE OR REPLACE PACKAGE BODY app_owner.order_api AS
  PROCEDURE create_order(
    p_order_id    IN NUMBER,
    p_customer_id IN NUMBER
  ) IS
  BEGIN
    INSERT INTO app_owner.orders (
      order_id,
      customer_id,
      status
    )
    VALUES (
      p_order_id,
      p_customer_id,
      'NEW'
    );
  END create_order;
END order_api;
/
~~~

Sau đó cấp quyền:

~~~sql
GRANT EXECUTE ON app_owner.order_api TO app_runtime;
~~~

APP_RUNTIME có thể gọi:

~~~sql
BEGIN
  app_owner.order_api.create_order(
    p_order_id    => 10001,
    p_customer_id => 501
  );
END;
/
~~~

Nếu APP_RUNTIME không được cấp INSERT trực tiếp trên APP_OWNER.ORDERS, ứng dụng chỉ có thể tạo đơn qua API đã công bố. Điều này giúp tập trung kiểm tra quy tắc nghiệp vụ, audit và validation ở một điểm.

### Definer rights và Invoker rights

PL/SQL stored unit có thể chạy theo quyền của owner hoặc quyền của invoker:

- **Definer rights:** mặc định của procedure/function/package khi không khai báo AUTHID khác. Code chạy với quyền của schema owner; role thường bị vô hiệu hóa trong named definer-rights PL/SQL unit. Các quyền cần thiết cho static SQL trong unit phải được cấp trực tiếp cho owner theo quy tắc Oracle.
- **Invoker rights:** khai báo AUTHID CURRENT_USER. Code sử dụng ngữ cảnh quyền của invoker khi thực thi theo quy tắc invoker-rights; các role đang bật của invoker có thể được tính đến. Cách phân giải tên và quyền truy cập cũng chịu ảnh hưởng của current user/current schema.

Ví dụ invoker rights:

~~~sql
CREATE OR REPLACE PROCEDURE app_owner.show_user_objects
AUTHID CURRENT_USER
AS
BEGIN
  -- Truy vấn động sẽ chạy theo ngữ cảnh quyền của invoker.
  NULL;
END;
/
~~~

Không chọn AUTHID CURRENT_USER chỉ vì muốn tránh cấp quyền trực tiếp. Invoker-rights unit có thể mở rộng phạm vi hành động theo quyền của người gọi, nên cần thiết kế và kiểm tra kỹ. Với API nghiệp vụ có quyền truy cập bảng của owner, definer rights thường là lựa chọn có chủ đích: runtime chỉ cần EXECUTE package, còn package dùng các quyền trực tiếp của owner.

## 7. Vì sao role không thay thế direct grant trong PL/SQL definer rights?

Một khác biệt quan trọng trong Oracle là role được bật trong session không được áp dụng theo cách thông thường bên trong named definer-rights PL/SQL unit. Vì vậy, một package owner có thể chạy được câu SELECT trực tiếp trong worksheet nhờ role, nhưng khi biên dịch hoặc thực thi package lại gặp lỗi quyền.

Ví dụ:

~~~sql
-- Giả sử APP_OWNER cần đọc bảng thuộc REFERENCE_OWNER.
GRANT SELECT ON reference_owner.countries TO app_owner;
~~~

Nếu chỉ cấp quyền thông qua role cho APP_OWNER, static SQL trong definer-rights package có thể không có privilege cần thiết. Hãy cấp trực tiếp object privilege cho owner đối với các object mà code definer-rights cần truy cập.

Đây là lý do cần tách hai tầng:

- Role dùng để quản lý quyền của user/session.
- Direct grant cho schema owner dùng để bảo đảm stored PL/SQL definer-rights có các quyền cần thiết khi compile/runtime.

Không giải quyết lỗi bằng cách cấp DBA hoặc SELECT ANY TABLE cho owner. Hãy xác định object cụ thể và cấp đúng quyền.

## 8. Mẫu cấp quyền theo từng giai đoạn

Một quy trình cấp quyền có thể chia thành:

### Giai đoạn 1: tạo owner và runtime user

~~~sql
CREATE USER app_owner
  IDENTIFIED BY "Use-A-Secret-Manager";

CREATE USER app_runtime
  IDENTIFIED BY "Use-A-Different-Secret";
~~~

Trong hệ thống thực tế, mật khẩu cần được tạo, lưu và truyền qua secret manager hoặc quy trình bảo mật. Không lưu mật khẩu thật trong source code, file SQL được commit, ticket hoặc log CI/CD.

### Giai đoạn 2: cấp quyền tạo object cho owner

Chỉ cấp các quyền DDL cần thiết trong thời gian hoặc phạm vi triển khai:

~~~sql
GRANT CREATE SESSION TO app_owner;
GRANT CREATE TABLE TO app_owner;
GRANT CREATE VIEW TO app_owner;
GRANT CREATE SEQUENCE TO app_owner;
GRANT CREATE PROCEDURE TO app_owner;
~~~

APP_OWNER cần quota trên tablespace để tạo segment:

~~~sql
ALTER USER app_owner
  QUOTA 500M ON app_data;
~~~

Ví dụ quota 500M chỉ là giá trị minh họa; cần tính theo dung lượng, growth, tablespace policy và môi trường. Không cấp UNLIMITED TABLESPACE nếu không có lý do đã được phê duyệt.

Nếu owner không cần tự đăng nhập sau triển khai, có thể khóa account theo quy trình vận hành. Việc khóa user sở hữu schema không đồng nghĩa xóa schema hoặc các object thuộc sở hữu của user.

### Giai đoạn 3: tạo object và role runtime

Schema owner triển khai bảng, sequence, view và package. Sau đó tạo role runtime:

~~~sql
CREATE ROLE app_runtime_role;

GRANT CREATE SESSION TO app_runtime_role;
GRANT SELECT ON app_owner.product_catalog TO app_runtime_role;
GRANT SELECT ON app_owner.order_status_v TO app_runtime_role;
GRANT EXECUTE ON app_owner.order_api TO app_runtime_role;

GRANT app_runtime_role TO app_runtime;
~~~

Nếu ứng dụng không cần đọc trực tiếp bảng, không cấp SELECT trên bảng đó. Nếu API package đã thực hiện việc đọc/ghi dữ liệu, chỉ cấp EXECUTE trên package.

### Giai đoạn 4: thu hồi quyền triển khai không cần ở runtime

APP_RUNTIME không được nhận CREATE TABLE, CREATE PROCEDURE, ALTER ANY TABLE, DROP ANY TABLE hoặc quyền DBA. Các quyền DDL thuộc về quy trình triển khai riêng.

## 9. Tách tài khoản triển khai và tài khoản chạy ứng dụng

Một lỗi thiết kế thường gặp là cấp quyền DDL cho runtime vì ứng dụng tự động tạo hoặc cập nhật bảng khi khởi động. Cách này khiến mọi instance ứng dụng đều có quyền thay đổi schema.

Một pipeline triển khai nên dùng danh tính riêng:

1. Release automation xác thực bằng credential được quản lý.
2. Tài khoản triển khai chạy migration đã review.
3. Migration tạo hoặc thay đổi object trong schema owner.
4. Pipeline cấp hoặc xác nhận quyền runtime cần thiết.
5. Ứng dụng khởi động bằng APP_RUNTIME và chỉ thực hiện DML/API đã được cấp.
6. Sau cửa sổ triển khai, credential triển khai được khóa hoặc chỉ cho phép dùng theo quy trình kiểm soát.

Không nên để ứng dụng tự chạy CREATE TABLE, ALTER TABLE hoặc CREATE OR REPLACE PACKAGE bằng tài khoản runtime. Schema migration cần có phiên bản, log, khả năng kiểm tra và quy trình rollback phù hợp.

## 10. Tách tài khoản theo service và môi trường

Không dùng một database user duy nhất cho tất cả microservice hoặc môi trường nếu các service có nhu cầu quyền khác nhau.

Ví dụ:

| Tài khoản | Phạm vi |
|---|---|
| ORDER_RUNTIME | Gọi API đơn hàng và đọc danh mục cần thiết |
| BILLING_RUNTIME | Gọi API hóa đơn và đọc dữ liệu thanh toán được phép |
| REPORT_RUNTIME | Đọc view báo cáo |
| ORDER_DEPLOY | Thực hiện migration schema đơn hàng |
| ORDER_DEV_RUNTIME | Kết nối môi trường development |
| ORDER_TEST_RUNTIME | Kết nối môi trường test |
| ORDER_PROD_RUNTIME | Kết nối môi trường production |

Tách credential theo service giúp:

- Thu hồi một service mà không làm gián đoạn service khác.
- Audit được nguồn truy cập.
- Giới hạn tác động nếu một secret bị lộ.
- Cấu hình quota, profile, role và chính sách riêng.
- Tránh dùng dữ liệu production bằng credential của môi trường phát triển.

Trong Oracle, có thể dùng MODULE/ACTION qua DBMS_APPLICATION_INFO hoặc driver để gắn thông tin ứng dụng vào session. Đây là metadata giúp quan sát và audit, không thay thế xác thực danh tính database.

## 11. Quản lý mật khẩu và secret

Mật khẩu của database user không nên được hard-code trong:

- Source code.
- File cấu hình được commit.
- Docker image hoặc container layer.
- Script triển khai lưu lâu dài.
- Log ứng dụng, log pipeline hoặc exception.
- Tài liệu hướng dẫn có thể chia sẻ rộng.

Thay vào đó:

- Lưu credential trong secret manager hoặc Oracle wallet/secure external password store phù hợp.
- Giới hạn ai có thể đọc secret và service nào được phép lấy.
- Dùng secret riêng theo môi trường và service.
- Xoay vòng credential theo chính sách và khả năng của ứng dụng.
- Không gửi mật khẩu qua command line hoặc biến môi trường nếu cách đó làm lộ trong process list/log.
- Có quy trình revoke/rotate ngay khi phát hiện secret bị lộ.

Nếu dùng connection pool, cần hiểu việc thay đổi mật khẩu ảnh hưởng đến các connection hiện hữu và cách pool tạo connection mới. Thử nghiệm quy trình rotation trước khi áp dụng production để tránh outage.

### Profile và chính sách mật khẩu

Oracle profile có thể kiểm soát một số giới hạn tài nguyên và chính sách password như thời hạn, số lần đăng nhập sai, thời gian khóa account hoặc password reuse theo cấu hình.

Ví dụ minh họa:

~~~sql
CREATE PROFILE app_user_profile LIMIT
  FAILED_LOGIN_ATTEMPTS 5
  PASSWORD_LOCK_TIME 1
  PASSWORD_LIFE_TIME 90;

ALTER USER app_runtime
  PROFILE app_user_profile;
~~~

Các giá trị trên chỉ là ví dụ, không phải khuyến nghị cố định cho mọi hệ thống. Chính sách hết hạn mật khẩu có thể không phù hợp với service credential nếu quy trình rotation tự động được thiết kế theo cách khác. Hãy thống nhất với chính sách bảo mật tổ chức và phiên bản Oracle.

Profile không thay thế MFA ở tầng quản trị, secret manager hoặc kiểm soát mạng. Với tài khoản service, cần thiết kế rotation để ứng dụng có thể đổi credential mà không phải lưu mật khẩu lâu dài trong code.

## 12. Tài khoản quản trị cá nhân và quyền đặc biệt

DBA nên sử dụng tài khoản cá nhân để các hành động quản trị có thể truy vết đến người thực hiện. Không dùng chung một user DBA cho cả nhóm nếu có thể tránh.

Các quyền như SYSDBA, SYSOPER hoặc quyền quản trị tương đương có phạm vi đặc biệt. Chúng có thể được xác thực thông qua password file, OS authentication hoặc cơ chế quản trị khác tùy cấu hình.

Nguyên tắc:

- Không dùng SYS/SYSTEM làm tài khoản ứng dụng.
- Không cấp SYSDBA cho developer hoặc service runtime.
- Dùng named DBA account cho hoạt động thường ngày.
- Chỉ sử dụng quyền đặc biệt khi nhiệm vụ yêu cầu.
- Dùng quy trình phê duyệt và audit cho các thao tác nhạy cảm.
- Bảo vệ password file, OS group và quyền truy cập máy chủ database.
- Xem xét tài khoản break-glass riêng, lưu secret có kiểm soát và chỉ dùng khi có sự cố.

Một DBA account cá nhân vẫn có thể được cấp quyền rộng, nhưng trách nhiệm và hoạt động phải được gắn với danh tính cụ thể. Tách tài khoản không có ý nghĩa nếu mọi người cùng biết mật khẩu của một user.

## 13. Kiểm tra quyền đã cấp

Oracle cung cấp các data dictionary view để xem user, role và privilege. Quyền đọc view phụ thuộc tài khoản và phạm vi quản trị.

### Xem system privilege của user

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 WHERE grantee IN ('APP_OWNER', 'APP_RUNTIME')
 ORDER BY grantee, privilege;
~~~

### Xem role được cấp

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
  FROM dba_role_privs
 WHERE grantee IN ('APP_OWNER', 'APP_RUNTIME')
 ORDER BY grantee, granted_role;
~~~

### Xem object privilege

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
  FROM dba_tab_privs
 WHERE grantee IN ('APP_OWNER', 'APP_RUNTIME')
 ORDER BY grantee, owner, table_name, privilege;
~~~

### Xem quyền trên cột

Một số object privilege có thể được cấp ở mức cột, ví dụ UPDATE hoặc REFERENCES khi cú pháp và object hỗ trợ:

~~~sql
SELECT grantee,
       owner,
       table_name,
       column_name,
       privilege
  FROM dba_col_privs
 WHERE grantee IN ('APP_OWNER', 'APP_RUNTIME')
 ORDER BY grantee, owner, table_name, column_name;
~~~

### Xem role và system privilege đang bật trong session

~~~sql
SELECT * FROM session_roles;

SELECT * FROM session_privs;
~~~

Các view SESSION_* chỉ cho biết quyền/role đang có hiệu lực trong session hiện tại. Chúng không thay thế việc kiểm tra toàn bộ grant trực tiếp, grant qua role, quyền kế thừa và quyền đặc biệt.

Nếu không có quyền DBA_*, có thể dùng một số view USER_* hoặc ALL_* trong phạm vi tài khoản được phép xem.

## 14. Thu hồi quyền và xử lý quyền dư

Khi một service không còn cần quyền, cần thu hồi:

~~~sql
REVOKE SELECT ON app_owner.product_catalog FROM app_runtime_role;
REVOKE app_runtime_role FROM app_runtime;
~~~

Nếu quyền được cấp trực tiếp cho user, thu hồi trực tiếp. Nếu quyền đến qua role, kiểm tra cả role được cấp lồng nhau và default role. Một privilege có thể được cấp từ nhiều nguồn, nên thu hồi một grant chưa chắc loại bỏ toàn bộ quyền hiệu lực.

Trước khi revoke trên production:

1. Xác định object và user/role nhận quyền.
2. Kiểm tra dependency của package, view, job và ứng dụng.
3. Xác định grant trực tiếp, grant qua role và grant qua role lồng nhau.
4. Thử trong môi trường test hoặc staging.
5. Revoke trong cửa sổ thay đổi phù hợp.
6. Kiểm tra login, API và job sau thay đổi.
7. Ghi nhận kết quả và cập nhật tài liệu quyền.

Không giữ quyền dư chỉ vì sợ thay đổi. Hãy lập kế hoạch kiểm chứng và thu hồi có kiểm soát.

## 15. Quyền ANY và quyền DBA cần được kiểm soát đặc biệt

Các system privilege có phạm vi rộng như SELECT ANY TABLE, INSERT ANY TABLE, UPDATE ANY TABLE, DELETE ANY TABLE, EXECUTE ANY PROCEDURE, CREATE ANY PROCEDURE, ALTER ANY TABLE và DROP ANY TABLE cần được xem xét nghiêm ngặt.

Một số quyền có thể được yêu cầu cho công cụ quản trị hoặc deployment automation, nhưng cần giới hạn:

- Danh tính được cấp.
- Thời gian được cấp.
- Môi trường được phép dùng.
- Schema hoặc đối tượng liên quan nếu có cách giới hạn hẹp hơn.
- Người phê duyệt và người chịu trách nhiệm.
- Cách audit và thu hồi.

DBA role thường chứa nhiều system privilege. Không cấp DBA cho APP_RUNTIME chỉ để khắc phục lỗi ORA-01031. Hãy đọc thông báo lỗi, xác định operation cần thực hiện và cấp đúng quyền hẹp nhất.

## 16. Tách quyền trong Oracle Multitenant

Trong kiến trúc multitenant, cần phân biệt CDB root và pluggable database (PDB). Một số user/role là common user/role ở phạm vi container; một số là local user/role chỉ tồn tại trong một PDB.

Với ứng dụng nghiệp vụ, thông thường nên tạo local user trong PDB chứa schema ứng dụng và kết nối service name của PDB đó. Tránh cấp common privilege hoặc tạo common user rộng nếu ứng dụng chỉ cần truy cập một PDB.

Ví dụ tạo local user trong PDB:

~~~sql
-- Kết nối đúng PDB trước khi chạy:
CREATE USER app_runtime
  IDENTIFIED BY "Managed-Secret-For-This-PDB";

GRANT CREATE SESSION TO app_runtime;
~~~

Tên user, quy tắc common/local và quyền tạo user phụ thuộc container hiện tại và cấu hình. DBA cần xác nhận đang ở đúng PDB trước khi chạy DDL.

Một ứng dụng chỉ dùng một PDB không nên có quyền truy cập nhiều PDB hoặc CDB root. Tách local user theo PDB giúp thu hẹp phạm vi và giảm nguy cơ truy cập nhầm container.

## 17. Tách quyền ở tầng ứng dụng và database

Database privilege chỉ là một phần của bảo mật. Ứng dụng vẫn cần kiểm soát người dùng cuối và tenant:

- Database user APP_RUNTIME xác định service kết nối database.
- Người dùng cuối được xác thực ở application identity provider hoặc cơ chế đăng nhập ứng dụng.
- Ứng dụng kiểm tra người dùng có quyền thực hiện nghiệp vụ nào.
- Query phải giới hạn dữ liệu theo tenant hoặc người dùng.
- Database API có thể nhận tenant/user context đã được xác minh và kiểm tra lại theo thiết kế.

Không nên coi mọi request đi qua cùng APP_RUNTIME là cùng một người dùng. Nếu tất cả request dùng một connection pool, database mặc định nhìn thấy cùng một database user. Cần truyền context an toàn và có cách audit request, module, action hoặc client identifier.

### SQL injection và bind variables

Least privilege giảm tác động của SQL injection nhưng không thay thế việc chống injection. Không nối trực tiếp dữ liệu người dùng vào SQL:

~~~sql
-- Không xây SQL bằng cách nối chuỗi từ input.
-- l_sql := 'SELECT ... WHERE customer_id = ' || p_customer_id;
~~~

Dùng bind variable:

~~~sql
SELECT order_id,
       status
  FROM app_owner.orders
 WHERE customer_id = :customer_id;
~~~

Nếu dùng dynamic SQL trong PL/SQL, hãy bind dữ liệu bằng USING và chỉ cho phép tên object/column từ danh sách allowlist đã kiểm soát. Bind variable không thể thay thế tên bảng hoặc tên cột động; các identifier động phải được xác thực và giới hạn riêng.

Ngay cả khi APP_RUNTIME chỉ có quyền SELECT trên một view, SQL injection vẫn có thể đọc toàn bộ dữ liệu mà view cho phép. Vì vậy cần kết hợp least privilege, bind variables, authorization ở application layer và kiểm soát tenant.

## 18. Audit và khả năng truy vết

Một hệ thống quyền tối thiểu cần biết:

- Ai đã đăng nhập.
- Tài khoản nào thực hiện thao tác.
- Thao tác nào được thực hiện trên object nào.
- Thời điểm, client, module và kết quả.
- Ai đã cấp hoặc thu hồi quyền.

Oracle Unified Auditing có thể hỗ trợ ghi nhận các hành động đăng nhập, thay đổi quyền và truy cập object theo policy được cấu hình. Phạm vi audit nên được thiết kế theo rủi ro và yêu cầu lưu trữ; audit quá rộng có thể tạo nhiều dữ liệu và overhead.

Ví dụ minh họa tạo policy audit cho một số thao tác trên bảng:

~~~sql
CREATE AUDIT POLICY app_orders_read_pol
  ACTIONS SELECT ON app_owner.orders;

AUDIT POLICY app_orders_read_pol;
~~~

Cú pháp và khả năng của audit policy phụ thuộc phiên bản Oracle và chế độ auditing đang dùng. DBA cần thử trong môi trường tương ứng, xác định view audit đầu ra và retention trước khi triển khai.

Đối với tài khoản quản trị, audit các hành động nhạy cảm như tạo user, cấp quyền, thay đổi role và thay đổi cấu hình. Đối với runtime account, cân nhắc audit theo module/action hoặc policy cụ thể để hỗ trợ điều tra mà không ghi nhận dư thừa.

Không lưu password, token hoặc dữ liệu nhạy cảm không cần thiết vào MODULE, ACTION, CLIENT_IDENTIFIER hoặc log.

## 19. Proxy authentication và danh tính ứng dụng

Oracle hỗ trợ proxy authentication trong một số kiến trúc, cho phép một user kết nối thay mặt user khác theo cấu hình được cấp. Cơ chế này có thể hữu ích khi một middle tier cần quản lý kết nối nhưng vẫn muốn database nhận diện người dùng cuối hoặc schema đại diện.

Proxy authentication không nên được bật đại trà. Cần xác định:

- User nào được phép proxy cho user nào.
- Proxy user có được cấp quyền session hay quyền khác hay không.
- Audit hiển thị proxy identity và client identity như thế nào.
- Ứng dụng có thể bảo vệ danh tính người dùng cuối khỏi bị giả mạo không.
- Connection pool có reset context đúng cách khi tái sử dụng connection không.

Nếu không có nhu cầu truy vết database theo user cuối, một runtime account riêng cho mỗi service kết hợp MODULE/ACTION và audit request có thể đã đáp ứng yêu cầu. Chọn proxy authentication khi mô hình danh tính và vận hành thực sự cần nó.

## 20. Ví dụ kiến trúc quyền tối thiểu

Một ứng dụng đơn hàng có thể triển khai theo sơ đồ:

~~~text
             DBA cá nhân
                 |
       quyền quản trị được duyệt
                 |
                 v
           Oracle Database
                 |
        +--------+---------+
        |                  |
        v                  v
     APP_OWNER          APP_RUNTIME
  sở hữu bảng/package   CREATE SESSION
        |                  |
        |                  v
        |             APP_RUNTIME_ROLE
        |                  |
        |           EXECUTE ORDER_API
        |           SELECT catalog view
        |                  |
        +------ package API
                   |
                   v
             Bảng nghiệp vụ
~~~

Trong mô hình này:

- APP_OWNER sở hữu object và có direct privilege cần cho package.
- APP_RUNTIME chỉ kết nối và gọi API được công bố.
- APP_RUNTIME_ROLE nhóm các quyền runtime.
- DBA cá nhân thực hiện quản trị theo danh tính riêng.
- APP_DEPLOY là danh tính riêng cho migration, không dùng trong connection pool runtime.
- Secret được quản lý ngoài source code và có quy trình rotation.

Đây là một mẫu tham khảo. Tùy kiến trúc, có thể thêm user đọc báo cáo, batch, integration hoặc schema riêng cho từng service.

## 21. Rà soát quyền định kỳ

Quyền tối thiểu cần được duy trì trong suốt vòng đời ứng dụng. Một lần cấp quyền đúng lúc triển khai không bảo đảm quyền vẫn đúng sau nhiều tháng thay đổi.

Lịch rà soát nên gồm:

1. Liệt kê user, role và system privilege được cấp.
2. Liệt kê object privilege trực tiếp và qua role.
3. Tìm quyền ANY, DBA, SYSDBA và quyền quản trị nhạy cảm.
4. Xác định user không còn sử dụng, account hết nhiệm vụ hoặc role không còn owner.
5. Đối chiếu quyền thực tế với danh sách API và nhiệm vụ service.
6. Kiểm tra tài khoản dùng chung, secret cũ và credential trong pipeline.
7. Xác nhận tài khoản runtime không có quyền DDL hoặc quản trị.
8. Thu hồi quyền dư theo quy trình thay đổi.
9. Lưu bằng chứng review, phê duyệt và kết quả.

Nên rà soát thêm sau các sự kiện: release lớn, chia tách service, thay đổi nhân sự DBA, di chuyển database, thay đổi môi trường cloud hoặc sự cố lộ credential.

## 22. Những lỗi thiết kế thường gặp

**Ứng dụng dùng user DBA:** runtime có thể đọc, sửa hoặc xóa dữ liệu ngoài phạm vi nghiệp vụ. Tạo runtime user riêng và cấp quyền hẹp.

**Dùng một user cho nhiều service:** khó xác định nguồn truy cập và thu hồi riêng. Tách service account khi quyền hoặc vòng đời khác nhau.

**Cấp SELECT ANY TABLE để sửa lỗi truy cập:** quyền rộng hơn nhiều so với một object bị thiếu. Cấp SELECT trên bảng/view cụ thể.

**Cấp CREATE ANY hoặc DROP ANY cho pipeline:** pipeline có thể tác động schema ngoài dự kiến. Giới hạn schema owner và quyền DDL cần thiết.

**Dùng role nhưng package definer-rights không chạy:** static SQL trong named definer-rights unit cần privilege trực tiếp cho owner theo quy tắc Oracle. Kiểm tra grant cụ thể thay vì cấp DBA.

**Không tách owner và runtime:** ứng dụng có quyền sửa object hoặc dữ liệu cấu trúc mà nó không cần thay đổi khi chạy.

**Hard-code mật khẩu:** secret có thể bị lộ qua Git, log, image hoặc artifact. Dùng secret manager/wallet và rotation.

**Không khóa hoặc vô hiệu hóa account cũ:** credential không còn nhiệm vụ vẫn có thể bị sử dụng. Có quy trình offboarding và revoke.

**Chỉ audit login:** hành động cấp quyền, DDL hoặc truy cập dữ liệu nhạy cảm có thể không được ghi nhận đủ. Thiết kế audit theo rủi ro.

**Coi database user là người dùng cuối:** một connection pool có thể đại diện cho hàng nghìn người dùng. Truyền context an toàn và kiểm tra authorization ở application layer.

## 23. Trình tự triển khai an toàn

Khi triển khai quyền cho ứng dụng mới, có thể thực hiện theo thứ tự:

1. Liệt kê chức năng ứng dụng và các thao tác SQL thực tế.
2. Phân loại object cần đọc, ghi hoặc gọi.
3. Xác định schema owner và tài khoản runtime.
4. Xác định tài khoản deployment và danh tính quản trị.
5. Tạo role theo nhiệm vụ, tránh role tổng hợp quá rộng.
6. Cấp quyền tạo object cho owner trong phạm vi cần thiết.
7. Triển khai bảng, view và package.
8. Cấp direct grant cho owner đối với object ngoài schema mà definer-rights code cần truy cập.
9. Cấp object privilege hoặc EXECUTE qua runtime role.
10. Kiểm tra runtime không có quyền DDL/ANY/DBA ngoài nhu cầu đã phê duyệt.
11. Kiểm thử kết nối, API, transaction, lỗi quyền và audit.
12. Đưa credential vào secret manager/wallet và thử rotation.
13. Ghi lại quyền, owner, approver và lịch review.

Khi gặp ORA-01031 (insufficient privileges), đừng cấp thêm quyền rộng ngay lập tức. Hãy xác định câu lệnh hoặc stored unit nào thất bại, user thực thi thực tế là ai, privilege cần là system hay object privilege, quyền đến từ role hay direct grant và phạm vi object nhỏ nhất có thể.

## 24. Kết luận

Nguyên tắc quyền tối thiểu yêu cầu mỗi tài khoản chỉ có quyền cần cho nhiệm vụ cụ thể. Tách tài khoản quản trị, schema owner, deployment và runtime giúp giới hạn phạm vi ảnh hưởng khi có lỗi hoặc lộ credential, đồng thời làm rõ trách nhiệm và audit.

Trong Oracle Database, hãy dùng role để quản lý quyền theo nhiệm vụ, object privilege để giới hạn truy cập vào từng bảng/view/package, direct grant cho schema owner khi definer-rights PL/SQL cần quyền truy cập, và hạn chế system privilege rộng như ANY hoặc DBA. Quản lý secret riêng, tách user theo service/môi trường, kiểm soát quyền trong PDB và rà soát định kỳ. Ứng dụng nên chạy bằng runtime user chỉ có CREATE SESSION và quyền gọi các API database được công bố; các thao tác DDL và quản trị phải đi qua danh tính triển khai hoặc quản trị riêng có kiểm soát.
