# Autonomous Database, wallet và ranh giới trách nhiệm vận hành

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Tính năng mở rộng  
> **Mục tiêu:** Hiểu mô hình vận hành của Oracle Autonomous Database; phân biệt trách nhiệm của Oracle Cloud và khách hàng; cấu hình kết nối bảo mật bằng TLS/mTLS và client credentials wallet; quản lý TNS alias, JDBC và connection pool; phân biệt database identity với OCI IAM; vận hành network access, wallet rotation, backup/restore, patching, monitoring, scaling và xử lý sự cố theo ranh giới trách nhiệm rõ ràng.

## 1. Autonomous Database là gì?

Oracle Autonomous Database (ADB) là dịch vụ database được quản lý trên Oracle Cloud Infrastructure (OCI). Dịch vụ tự động hóa nhiều công việc quản trị thường phải thực hiện thủ công trên database tự quản lý, chẳng hạn provisioning, một số hoạt động patching, backup, tuning và scaling theo cấu hình dịch vụ.

Từ autonomous không có nghĩa database tự quyết định mọi chính sách nghiệp vụ hoặc khách hàng không còn trách nhiệm vận hành. Oracle quản lý nền tảng dịch vụ theo mô hình cloud managed service; khách hàng vẫn chịu trách nhiệm về dữ liệu, schema, người dùng, quyền truy cập, ứng dụng, network policy phía tổ chức, client wallet, kiểm thử và quy trình nghiệp vụ.

ADB thường được sử dụng cho các workload như:

- **Autonomous Transaction Processing (ATP):** workload giao dịch, ứng dụng OLTP và xử lý đồng thời.
- **Autonomous Data Warehouse (ADW):** workload phân tích, reporting, data warehouse.
- Các cấu hình Autonomous Database chuyên biệt hoặc triển khai trên hạ tầng Exadata dedicated tùy lựa chọn dịch vụ và khu vực.

Tên dịch vụ, tùy chọn, service level và khả năng quản trị có thể thay đổi theo edition, deployment model, region và thời điểm. Khi triển khai, phải đối chiếu trang cấu hình và tài liệu của đúng dịch vụ đang sử dụng.

### 1.1. Autonomous không đồng nghĩa không cần DBA

Các công việc hạ tầng được tự động hóa giúp DBA chuyển trọng tâm sang:

- Thiết kế schema và data model.
- Kiểm soát quyền truy cập và phân loại dữ liệu.
- Thiết kế SQL, index, partition và workload.
- Quản lý kết nối, wallet và credential.
- Kiểm thử ứng dụng sau patch/maintenance.
- Theo dõi hiệu năng, SLA, chi phí và capacity.
- Thiết kế backup/restore và disaster recovery theo yêu cầu nghiệp vụ.
- Điều phối thay đổi schema, release và incident response.

DBA vẫn cần hiểu transaction, SQL execution plan, locking, resource usage, security và recovery. Managed service thay đổi nơi thực hiện một số thao tác quản trị, không loại bỏ trách nhiệm đảm bảo hệ thống đáp ứng nghiệp vụ.

## 2. Các lớp của dịch vụ và ranh giới quản lý

Một cách nhìn hữu ích là chia ADB thành ba lớp:

1. **Cloud control plane:** OCI Console, API, IAM, networking và cấu hình tài nguyên dịch vụ.
2. **Database service plane:** database instance, database users, schemas, SQL, backup/restore và workload services.
3. **Application/client plane:** ứng dụng, JDBC driver, wallet, connection pool, secret management và business transaction.

~~~text
Organization / Cloud tenancy
        |
        +---- OCI IAM, policies, compartments
        |
        +---- VCN, subnet, NSG, private endpoint
        |
        v
Autonomous Database service
        |
        +---- Managed database infrastructure
        +---- Database users, roles, schemas
        +---- Workload services
        +---- Backup / restore / monitoring
        |
        v
Application runtime
        |
        +---- JDBC driver and TNS alias
        +---- Wallet / TLS trust
        +---- Connection pool
        +---- Application authorization
~~~

OCI IAM điều khiển ai được quản lý tài nguyên cloud. Database user/role điều khiển ai được đọc hoặc sửa dữ liệu bên trong database. Wallet hỗ trợ thiết lập kết nối và xác thực theo chế độ được cấu hình. Ba lớp này phải được quản lý cùng nhau nhưng không thể thay thế nhau.

## 3. Deployment model: Serverless và Dedicated

ADB có thể được cung cấp theo các deployment model khác nhau. Hai khái niệm thường gặp là Serverless và Dedicated Infrastructure.

### 3.1. Autonomous Database Serverless

Với mô hình Serverless, Oracle quản lý hạ tầng Exadata và phần lớn hoạt động vận hành nền tảng database. Khách hàng tạo database trong OCI, chọn workload, cấu hình compute/storage, network access và các tùy chọn dịch vụ.

Đặc điểm thường gặp:

- Provision database qua OCI Console/API.
- Compute có thể được điều chỉnh theo khả năng và chính sách của dịch vụ.
- Oracle tự động hóa các hoạt động bảo trì được dịch vụ hỗ trợ.
- Backup và các tùy chọn recovery được tích hợp.
- Khách hàng tập trung vào schema, data, access policy và ứng dụng.

Serverless không có nghĩa database không có compute/storage hoặc không chịu quota/cost. Khách hàng vẫn phải chọn cấu hình phù hợp, theo dõi usage và kiểm soát scaling.

### 3.2. Autonomous Database Dedicated

Dedicated Infrastructure cung cấp hạ tầng Exadata dành riêng cho tenancy/khách hàng theo mô hình dịch vụ tương ứng. Khách hàng có thêm lựa chọn kiểm soát về hạ tầng database chuyên biệt, resource allocation và isolation tùy dịch vụ.

Một số tài nguyên có thể được tạo và quản lý theo các lớp như:

- Exadata Infrastructure.
- Autonomous Container Database.
- Autonomous Database.

Mô hình dedicated có thêm lựa chọn và trách nhiệm điều phối hạ tầng cấp cao hơn so với Serverless, nhưng vẫn là managed service. Phân định chính xác quyền thao tác và phần Oracle quản lý theo hợp đồng, service description và deployment configuration.

### 3.3. Chọn mô hình theo yêu cầu

| Tiêu chí | Serverless | Dedicated |
|---|---|---|
| Mục tiêu | Đơn giản hóa triển khai và vận hành | Isolation và kiểm soát hạ tầng chuyên biệt hơn |
| Quản lý Exadata | Oracle quản lý nền tảng | Hạ tầng dedicated theo mô hình dịch vụ |
| Cấu hình | Theo các lựa chọn service được cung cấp | Có thêm cấu hình ở tầng infrastructure/container tùy edition |
| Vận hành | Tập trung database, security và ứng dụng | Cần điều phối thêm lifecycle hạ tầng chuyên biệt |
| Phù hợp | Nhiều workload cloud managed thông thường | Yêu cầu isolation, capacity hoặc governance riêng |

Không chọn Dedicated chỉ vì tên gọi có vẻ an toàn hơn. Đánh giá workload, compliance, isolation, capacity, region availability, operational model và tổng chi phí.

## 4. ATP và ADW: chọn workload service phù hợp

Autonomous Transaction Processing và Autonomous Data Warehouse được tối ưu cho workload khác nhau.

### 4.1. ATP

ATP phù hợp với:

- Transaction ngắn và thường xuyên.
- Nhiều session đồng thời.
- Insert/update/delete.
- Ứng dụng nghiệp vụ.
- API backend và transaction processing.

Ứng dụng nên thiết kế connection pool, transaction duration, index và SQL theo pattern OLTP.

### 4.2. ADW

ADW phù hợp với:

- Query scan/aggregate dữ liệu lớn.
- Reporting và analytics.
- Data warehouse workloads.
- Batch transformation và analytical SQL.

Workload phân tích có thể dùng parallel execution và tiêu thụ compute lớn hơn. Cần kiểm soát concurrency, service class, query duration và chi phí.

### 4.3. Không dùng một database/service cho mọi workload theo mặc định

Một ứng dụng OLTP và một báo cáo quét dữ liệu lớn có thể cạnh tranh tài nguyên. Cân nhắc workload service riêng, read replica/standby hoặc tách analytical workload theo kiến trúc được hỗ trợ.

Không chuyển workload sang ADW chỉ vì query chậm; trước tiên phải đo execution plan, data model và access pattern.

## 5. Wallet trong Autonomous Database

Wallet là tập hợp file bảo mật được client sử dụng trong một số phương thức kết nối tới ADB. Wallet có thể chứa thông tin certificate, private key và cấu hình kết nối. Với kết nối mTLS, wallet cung cấp client identity để database xác thực client qua TLS.

Wallet không phải:

- Database schema.
- Database user password.
- OCI IAM policy.
- Một bản backup database.
- Tệp chứa dữ liệu bảng.
- Cơ chế cấp quyền SELECT/INSERT/UPDATE.

Wallet giúp thiết lập kết nối bảo mật; sau khi kết nối, database vẫn xác định database user và kiểm tra privilege của user đó theo cơ chế xác thực được sử dụng.

### 5.1. TLS và mTLS

**TLS một chiều (server-authenticated TLS):**

- Client xác minh certificate của server.
- Server không yêu cầu client certificate để xác thực kết nối ở tầng TLS.
- Ứng dụng vẫn cần database credential hoặc phương thức database authentication khác.

**Mutual TLS (mTLS):**

- Client xác minh server certificate.
- Server cũng yêu cầu client certificate.
- Client trình certificate và chứng minh quyền sở hữu private key tương ứng.
- ADB có thể dùng client credentials wallet cho phương thức này.

mTLS xác thực client ở tầng kết nối. Nó không tự cấp quyền truy cập mọi schema. Database user/role vẫn quyết định quyền dữ liệu.

### 5.2. Wallet client credentials

Wallet được tải từ OCI Console hoặc cơ chế quản trị được hỗ trợ cho Autonomous Database. File ZIP thường chứa các thành phần như:

- cwallet.sso: auto-login wallet trong các cấu hình wallet tương ứng.
- ewallet.p12: wallet được bảo vệ bằng password.
- tnsnames.ora: các network alias kết nối.
- sqlnet.ora: cấu hình Oracle Net/wallet.
- README hoặc file hướng dẫn.

Thành phần chính xác có thể thay đổi theo loại wallet và dịch vụ. Kiểm tra nội dung file ZIP và tài liệu của ADB đang dùng; không giả định mọi wallet có cấu trúc hoàn toàn giống nhau.

### 5.3. Wallet password

Password wallet bảo vệ wallet file như ewallet.p12. Nó không nhất thiết là password của database user.

Cần phân biệt:

| Bí mật | Mục đích |
|---|---|
| Wallet password | Mở hoặc quản lý wallet được bảo vệ bằng password |
| Database user password | Xác thực database user khi dùng username/password |
| Client private key | Chứng minh client identity trong mTLS |
| OCI API key/private key | Xác thực principal với OCI API theo cơ chế tương ứng |
| OAuth/token/secret | Xác thực ứng dụng với một dịch vụ khác |

Không dùng một password cho mọi loại credential và không lưu wallet password trong source code.

### 5.4. Auto-login wallet

Auto-login wallet giúp Oracle client sử dụng wallet mà không cần nhập password wallet ở mỗi lần kết nối, tùy cấu hình và nền tảng.

Điều này tiện cho ứng dụng server nhưng làm quyền truy cập filesystem trở nên quan trọng: process đọc được auto-login wallet có thể sử dụng nội dung wallet theo khả năng của client/tool.

Bảo vệ wallet directory:

- Chỉ service account cần thiết được đọc.
- Không đặt trong web root hoặc thư mục public.
- Không commit ZIP hoặc file wallet vào Git.
- Không đính kèm wallet vào ticket/chat.
- Không đưa wallet vào image/container layer dùng chung.
- Không để wallet trong thư mục tạm có cleanup hoặc backup không kiểm soát.
- Mã hóa và hạn chế quyền đối với backup wallet.

## 6. Tải và cài đặt wallet an toàn

Quy trình tổng quát:

1. Xác định đúng Autonomous Database và môi trường.
2. Chọn loại wallet/phương thức kết nối được tổ chức phê duyệt.
3. Tải wallet qua OCI Console hoặc API được ủy quyền.
4. Đặt password wallet theo policy khi thao tác tải yêu cầu.
5. Giải nén vào thư mục riêng trên host ứng dụng.
6. Cấp quyền filesystem tối thiểu cho service account.
7. Cấu hình Oracle client/JDBC trỏ tới wallet directory.
8. Kết nối bằng alias phù hợp.
9. Xác nhận database user, service, TLS mode và workload service.
10. Ghi nhận owner, ngày tải, phiên bản/rotation event và nơi lưu trữ an toàn.

Không tải wallet từ nguồn không xác minh hoặc dùng wallet của môi trường production trong máy phát triển không được quản lý.

### 6.1. Ví dụ cấu trúc thư mục

Ví dụ trên Linux:

~~~text
/opt/app/
  config/
    oracle/
      adb-prod/
        cwallet.sso
        ewallet.p12
        tnsnames.ora
        sqlnet.ora
~~~

Thư mục trên là ví dụ phía application host. Wallet không nằm trong database server filesystem theo cách DIRECTORY object hoạt động; đây là credential/configuration được Oracle client đọc.

### 6.2. Quyền filesystem

Ví dụ kiểm tra:

~~~bash
ls -ld /opt/app/config/oracle/adb-prod
ls -l /opt/app/config/oracle/adb-prod
namei -l /opt/app/config/oracle/adb-prod
~~~

Chỉ cấp quyền đọc cho account chạy ứng dụng và nhóm vận hành được phê duyệt. Không dùng chmod 777. Với Windows, kiểm tra NTFS ACL của service account; với container, kiểm tra mount/secret volume và UID/GID thực tế.

### 6.3. Không nhầm wallet client với DIRECTORY object

DIRECTORY object ánh xạ tên trong Oracle Database tới path mà database server process truy cập. Wallet client nằm trên host/container chạy ứng dụng và được JDBC/Oracle Net client đọc.

Nếu JDBC app chạy trong Kubernetes, wallet thường được mount vào pod qua secret/volume hoặc cơ chế secret delivery. Nếu app chạy trên VM, wallet được đặt trong filesystem được bảo vệ của VM. Cách phân phối khác nhau nhưng nguyên tắc là không đưa private key ra ngoài phạm vi client cần sử dụng.

## 7. TNS alias và workload service

Trong wallet ZIP thường có tnsnames.ora với nhiều alias kết nối. Mỗi alias có connect descriptor và service name phù hợp với workload service.

Ví dụ khái niệm:

~~~text
myadb_high =
  (description =
    (retry_count = 20)
    (retry_delay = 3)
    (address =
      (protocol = tcps)
      (port = 1522)
      (host = adb.example.oraclecloud.com)
    )
    (connect_data =
      (service_name = example_high.adb.oraclecloud.com)
    )
    (security =
      (ssl_server_dn_match = yes)
    )
  )
~~~

Đây là ví dụ minh họa rút gọn; dùng alias và descriptor được cung cấp trong wallet tải từ đúng database, không tự dựng hostname/service name production theo mẫu.

### 7.1. Các workload service alias

Tùy loại ADB và cấu hình, wallet có thể cung cấp các alias với suffix như:

- high
- medium
- low
- tp
- tpurgent

Không phải mọi database đều có cùng danh sách alias. Xem tnsnames.ora và thông tin service trong tài liệu của database cụ thể.

Các service khác nhau có thể áp dụng consumer group, concurrency, parallelism hoặc resource management policy khác nhau. Chọn service phù hợp workload thay vì luôn dùng HIGH.

### 7.2. Ví dụ chọn service

| Workload | Service cần đánh giá |
|---|---|
| Giao dịch ngắn, latency-sensitive | Service OLTP phù hợp, ví dụ TP theo cấu hình có |
| Transaction cần ưu tiên cao | TPURGENT nếu dịch vụ cung cấp và có entitlement |
| Query phân tích/report | HIGH/MEDIUM/LOW theo workload và policy |
| Batch dài, concurrency thấp | Service phù hợp với batch/resource policy |
| Ứng dụng thông thường | MEDIUM hoặc service được kiến trúc quy định |

Tên service không phải mức ưu tiên nghiệp vụ tùy ý. Mỗi service có semantics và giới hạn riêng do ADB cung cấp. Kiểm tra cấu hình thực tế và đo trước khi đổi.

## 8. Cấu hình JDBC Thin với wallet

Oracle JDBC Thin driver có thể dùng Oracle Net configuration và wallet. Cách phổ biến là chỉ định TNS_ADMIN trỏ tới thư mục chứa tnsnames.ora/sqlnet.ora/wallet, sau đó kết nối bằng alias.

### 8.1. JDBC URL theo TNS alias

Ví dụ:

~~~text
jdbc:oracle:thin:@myadb_medium?TNS_ADMIN=/opt/app/config/oracle/adb-prod
~~~

Đây là mẫu minh họa. Alias phải tồn tại trong tnsnames.ora của wallet đúng database; cú pháp property hỗ trợ phụ thuộc Oracle JDBC driver version.

Một cách khác là cấu hình TNS_ADMIN qua JVM/system property hoặc OracleDataSource property theo tài liệu driver:

~~~text
-Doracle.net.tns_admin=/opt/app/config/oracle/adb-prod
~~~

Không cấu hình đồng thời nhiều wallet path không nhất quán. Khi dùng connection pool, mọi connection trong pool phải dùng cùng cấu hình target/service và wallet lifecycle.

### 8.2. Spring Boot datasource

Ví dụ cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@myadb_medium?TNS_ADMIN=/opt/app/config/oracle/adb-prod
    username: APP_USER
    password: DB_PASSWORD_FROM_SECRET_STORE
    driver-class-name: oracle.jdbc.OracleDriver
~~~

DB_PASSWORD_FROM_SECRET_STORE là placeholder minh họa cho secret được inject từ secret manager hoặc cơ chế cấu hình bảo mật của nền tảng. Không lưu password rõ trong application.yml đã commit.

Nếu kết nối sử dụng database authentication khác hoặc mTLS-only flow theo cấu hình được hỗ trợ, phần username/password có thể khác. Đối chiếu phương thức authentication của ADB và Oracle JDBC driver.

### 8.3. Kiểm tra connection

Sau khi kết nối, xác nhận database/service/user:

~~~sql
SELECT
    sys_context('USERENV', 'DB_NAME') AS db_name,
    sys_context('USERENV', 'SERVICE_NAME') AS service_name,
    sys_context('USERENV', 'SESSION_USER') AS session_user,
    sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

Không chỉ kiểm tra SELECT 1. Một kết nối có thể thành công nhưng trỏ tới nhầm database, PDB, schema hoặc workload service.

### 8.4. Driver compatibility

Chọn Oracle JDBC driver tương thích với JDK, Spring Boot/Hibernate và database deployment. TNS alias, wallet handling, TLS protocol và authentication option có thể thay đổi theo driver release.

Pin driver version, test kết nối trên đúng runtime và kiểm tra release notes trước khi nâng cấp.

## 9. Connection pool và wallet lifecycle

Ứng dụng thường dùng HikariCP, UCP hoặc pool do application server quản lý. Pool giữ physical database sessions và tái sử dụng chúng qua nhiều request.

Cần xác định:

- Pool kết nối tới service alias nào.
- Số connection tối đa và tối thiểu.
- Connection timeout.
- Idle/max lifetime.
- Validation/health check.
- Retry khi database failover/maintenance.
- Hành vi khi wallet thay đổi.
- Cách recycle physical connections sau credential rotation.

### 9.1. Đổi wallet không tự cập nhật mọi connection đang tồn tại

Một pool có thể giữ physical connections đã mở bằng wallet cũ. Thay file wallet trên filesystem không bảo đảm mọi connection đang hoạt động lập tức sử dụng credential mới.

Quy trình rotation cần phối hợp:

1. Phát hành/tải wallet mới theo quy trình ADB.
2. Cập nhật secret/volume hoặc file location.
3. Kiểm tra ứng dụng có thể tạo connection mới bằng wallet mới.
4. Recycle pool hoặc rolling restart theo kế hoạch.
5. Xác nhận connection mới hoạt động.
6. Theo dõi connection cũ và lỗi xác thực.
7. Thu hồi/rotate credential cũ theo policy và xác nhận trạng thái thực tế.

Không xóa wallet cũ trước khi biết mọi workload đã chuyển và có phương án rollback. Đồng thời không giữ wallet cũ lâu hơn chính sách bảo mật cho phép.

### 9.2. Connection pool sau maintenance/failover

Sau maintenance, restart hoặc role transition, connection cũ có thể bị ngắt. Pool cần loại bỏ connection lỗi và tạo connection mới. Ứng dụng phải xử lý retry có giới hạn và transaction outcome không xác định.

Không retry mù một transaction ghi khi client không biết COMMIT đã thành công hay chưa. Dùng idempotency key hoặc kiểm tra trạng thái nghiệp vụ.

## 10. Database identity và OCI IAM là hai lớp khác nhau

OCI IAM quản lý danh tính và quyền trên tài nguyên cloud. Database authentication/authorization quản lý session và quyền truy cập dữ liệu.

### 10.1. OCI IAM

OCI IAM có thể quản lý:

- User/group.
- Dynamic group.
- Policy.
- Compartment.
- Quyền tạo/đọc/cập nhật Autonomous Database resource.
- Quyền tải wallet hoặc thao tác quản trị tùy policy.
- Quyền truy cập Vault, Object Storage và các dịch vụ cloud khác.

Ví dụ policy khái niệm:

~~~text
Allow group DatabaseOperators to read autonomous-databases in compartment Production
~~~

Cú pháp và phạm vi policy phải theo OCI IAM policy language, compartment và resource type thực tế. Ví dụ trên chỉ minh họa ý nghĩa, không phải policy hoàn chỉnh cho mọi API.

### 10.2. Database user và role

Database user có thể được cấp quyền:

- CREATE SESSION.
- SELECT/INSERT/UPDATE/DELETE trên object.
- EXECUTE trên package.
- Role ứng dụng.
- Quota và quyền schema theo nhu cầu.

Ví dụ:

~~~sql
CREATE USER app_user IDENTIFIED BY "<secret-managed-password>";
GRANT CREATE SESSION TO app_user;
GRANT SELECT, INSERT, UPDATE ON app_owner.orders TO app_user;
~~~

Đây là ví dụ lab. Trong production, tạo/rotate password qua quy trình secret management, giới hạn quyền và dùng role/object grants phù hợp.

### 10.3. OCI IAM không tự cấp SELECT trên bảng

Một user có quyền quản lý Autonomous Database resource trong OCI Console không mặc nhiên có quyền SELECT dữ liệu trong database.

Ngược lại, một database user có SELECT trên bảng không mặc nhiên có quyền stop, scale hoặc thay đổi cấu hình Autonomous Database trong OCI.

Cần review riêng hai ma trận quyền:

| Hành động | Lớp quyền |
|---|---|
| Tạo/scale/stop ADB resource | OCI IAM policy |
| Tải hoặc rotate wallet | OCI IAM/ADB administrative permission |
| Mở kết nối database | Network policy + TLS/mTLS + authentication |
| Login schema | Database authentication |
| SELECT/UPDATE bảng | Database grants/roles |
| Gọi package | Database EXECUTE privilege |
| Đọc secret trong OCI Vault | OCI IAM policy và secret authorization |
| Đọc dữ liệu Object Storage từ database | Cơ chế credential/resource principal và policy tương ứng |

## 11. Resource principal và truy cập OCI service từ database

Một số tính năng ADB cho phép database workload truy cập OCI services mà không cần lưu API key dài hạn trong database code, thông qua resource principal hoặc credential mechanism được hỗ trợ.

Ví dụ workload có thể cần:

- Đọc/ghi Object Storage.
- Truy cập một số OCI resource.
- Dùng DBMS_CLOUD hoặc tích hợp cloud service.
- Thực hiện operation bằng identity của Autonomous Database resource.

Cần phân biệt:

- **Client wallet:** giúp ứng dụng kết nối vào database.
- **Database credential:** xác thực database user.
- **Resource principal:** danh tính của database resource khi gọi dịch vụ OCI được hỗ trợ.
- **OCI IAM policy:** cho phép resource principal thực hiện hành động cloud.
- **Database package privilege:** cho phép schema gọi package/feature tương ứng.

Resource principal không phải quyền mặc định truy cập mọi bucket hoặc mọi secret. Cần thiết lập dynamic group/resource principal policy đúng compartment/resource và chỉ cấp quyền cần thiết.

Không hardcode OCI user API key trong PL/SQL nếu dịch vụ hỗ trợ identity-based access phù hợp.

## 12. Network access: public endpoint và private endpoint

ADB có thể được cấu hình với các lựa chọn network access khác nhau tùy deployment model và tính năng:

- Public endpoint với access control/ACL theo cấu hình.
- Private endpoint trong VCN.
- Network Security Group và subnet/security policy.
- Private DNS/routing.
- Kết nối qua VPN/FastConnect hoặc network path của tổ chức.

### 12.1. Public endpoint

Public endpoint không đồng nghĩa mở database cho toàn Internet nếu access control được cấu hình đúng. Cần:

- Chỉ allow nguồn IP/network cần thiết.
- Tránh CIDR quá rộng.
- Quản lý egress/ingress policy.
- Kiểm soát DNS và TLS.
- Theo dõi thay đổi access list.
- Review quyền OCI IAM sửa network access.

### 12.2. Private endpoint

Private endpoint giúp truy cập database qua private network trong phạm vi cấu hình hỗ trợ. Nó không tự giải quyết mọi vấn đề bảo mật:

- Client vẫn cần authentication.
- Database user vẫn cần privilege phù hợp.
- Route, subnet, NSG và DNS phải đúng.
- On-premises client cần VPN/FastConnect hoặc network path phù hợp.
- Wallet/TLS configuration vẫn phải hợp lệ nếu phương thức kết nối yêu cầu.

Private endpoint giảm exposure public nhưng không thay thế least privilege, audit và credential protection.

### 12.3. Network ACL ở database và OCI network policy

Cần phân biệt:

- OCI VCN/subnet/NSG/security list: kiểm soát network path ở cloud networking.
- ADB access control list/private endpoint configuration: kiểm soát nguồn được phép kết nối theo dịch vụ.
- Oracle database network ACL: kiểm soát outbound network call từ PL/SQL như UTL_HTTP.
- Host firewall/egress proxy: kiểm soát traffic ở host/application network.

Một inbound JDBC connection vào ADB và một outbound UTL_HTTP call từ database là hai luồng khác nhau. Cấu hình network access cho một luồng không tự cho phép luồng còn lại.

## 13. TLS, mTLS và xác thực database

Khi client kết nối tới ADB, cần tách ba bước:

1. **Network reachability:** DNS, route, endpoint, firewall, private/public access.
2. **TLS handshake:** xác minh server certificate; mTLS có thể yêu cầu client certificate.
3. **Database authentication/authorization:** xác định user/schema và quyền.

Một lỗi có thể xảy ra ở từng tầng:

| Tầng | Ví dụ lỗi | Hướng kiểm tra |
|---|---|---|
| Network | Timeout, connection refused | DNS, route, NSG, access control |
| TLS | Certificate validation/handshake failure | Wallet, trust chain, clock, driver |
| Authentication | Invalid username/password hoặc client identity | Credential, wallet, auth mode |
| Authorization | Insufficient privileges | Database grants/roles |
| Workload | Query timeout/resource error | Service alias, SQL, concurrency |

Không xử lý lỗi TLS bằng cách cấp thêm database privilege. Không xử lý ORA-01017 bằng cách mở rộng network ACL.

## 14. Wallet rotation và thu hồi credential

Wallet chứa thông tin nhạy cảm và cần được quản lý như một credential có vòng đời.

### 14.1. Khi nào cần rotation?

- Theo lịch security policy.
- Khi nghi ngờ wallet bị lộ.
- Khi nhân sự/nhà cung cấp không còn quyền truy cập.
- Khi thay đổi client certificate.
- Khi thay đổi authentication mode.
- Khi có yêu cầu compliance hoặc incident response.

### 14.2. Quy trình rotation tổng quát

1. Xác định mọi consumer của wallet: VM, container, CI/CD, developer workstation, batch và DR site.
2. Xác nhận người thực hiện có OCI IAM permission phù hợp.
3. Tạo/tải wallet mới theo cơ chế ADB hỗ trợ.
4. Lưu wallet mới trong secret manager hoặc secure volume.
5. Triển khai tới một client canary.
6. Kiểm tra TLS/mTLS, database authentication và service alias.
7. Recycle pool hoặc rolling restart theo kế hoạch.
8. Xác nhận toàn bộ workload dùng wallet mới.
9. Thu hồi wallet/certificate cũ theo policy và semantics của dịch vụ.
10. Xóa bản sao cũ theo retention/security procedure.
11. Ghi audit trail và cập nhật inventory.

### 14.3. Xử lý wallet bị lộ

Nếu wallet hoặc private key bị lộ:

- Kích hoạt incident/security response.
- Xác định loại wallet, database, service và client bị ảnh hưởng.
- Hạn chế hoặc thu hồi credential theo khả năng ADB cung cấp.
- Phát hành wallet/certificate mới.
- Recycle connection pool và client runtime.
- Kiểm tra access logs/audit và dấu hiệu truy cập bất thường.
- Kiểm tra secret replication, backups, container images và developer copies.
- Xác nhận mọi client cũ không còn truy cập được theo yêu cầu incident.
- Ghi nhận timeline và root cause.

Chỉ xóa file khỏi một máy không đồng nghĩa credential đã bị thu hồi. Wallet có thể đã được copy sang nhiều host hoặc backup.

## 15. Backup, restore và trách nhiệm dữ liệu

ADB tự động hóa backup theo cấu hình dịch vụ và cung cấp các khả năng restore/recovery được hỗ trợ. Tuy vậy, khách hàng phải hiểu mục tiêu recovery và xác minh quy trình có đáp ứng nghiệp vụ.

### 15.1. Các câu hỏi cần trả lời

- Backup retention hiện tại là bao lâu?
- Có point-in-time recovery tới mốc cần thiết không?
- RPO/RTO nghiệp vụ là gì?
- Có backup thủ công hoặc export bổ sung cần thiết không?
- Dữ liệu cần giữ theo legal/compliance policy nào?
- Ai được phép restore/clone database?
- Restore có cần approval hai người không?
- Ứng dụng có thể kết nối tới bản restored database không?
- Wallet, service alias, secret và network access có cần cập nhật sau restore không?

Không giả định backup do Oracle quản lý đồng nghĩa khách hàng không cần kiểm thử restore.

### 15.2. Backup không thay thế logical recovery

Backup bảo vệ khả năng khôi phục database. Nhưng khi người dùng xóa nhầm một số hàng, có thể cần Flashback, point-in-time clone/restore, export/import hoặc logical recovery để lấy đúng dữ liệu.

Một restore toàn database có thể ảnh hưởng các giao dịch mới hơn. Cần chọn cách phục hồi theo phạm vi lỗi và business impact.

### 15.3. Kiểm thử restore

Thực hiện theo quy trình được hỗ trợ:

1. Xác định target time/SCN hoặc recovery objective.
2. Chọn restore/clone destination phù hợp.
3. Xác nhận quyền OCI IAM và network isolation.
4. Thực hiện restore/clone qua OCI Console/API.
5. Kiểm tra database open mode, schema và dữ liệu.
6. Chạy application smoke test.
7. Kiểm tra user/role, wallet, connection alias và secret.
8. Đo thời gian thực tế.
9. Ghi lại RPO/RTO và bằng chứng.

Tên menu, retention và khả năng restore phụ thuộc dịch vụ/region/configuration. Dùng giao diện và tài liệu của đúng ADB instance.

## 16. Patching, maintenance và change management

Oracle quản lý nhiều hoạt động patching/maintenance cho ADB. Khách hàng vẫn cần quản lý tác động ở application layer.

### 16.1. Trách nhiệm khách hàng trước maintenance

- Theo dõi thông báo maintenance và cửa sổ dự kiến.
- Xác định ứng dụng, batch và integration bị ảnh hưởng.
- Kiểm tra connection pool, retry, timeout và reconnect.
- Xác nhận backup/recovery posture.
- Kiểm tra driver/client compatibility nếu có thay đổi.
- Chuẩn bị smoke test và business validation.
- Thông báo stakeholder theo change policy.

### 16.2. Trong và sau maintenance

- Theo dõi trạng thái ADB trên OCI.
- Kiểm tra connection errors và pool recovery.
- Xác nhận service name, database user và schema.
- Chạy read/write smoke test được phê duyệt.
- Kiểm tra latency, throughput và error rate.
- Xác nhận scheduled jobs, replication và integration.
- Ghi incident/change evidence nếu có tác động.

Không giả định maintenance hoàn tất nghĩa là mọi connection pool đã tự hồi phục. Connection cũ có thể cần được recycle.

### 16.3. Database version và client compatibility

ADB có thể được patch/nâng cấp theo lifecycle dịch vụ. Khách hàng phải duy trì driver, framework, SQL và stored code tương thích với phiên bản dịch vụ được hỗ trợ.

Không dùng driver quá cũ hoặc phụ thuộc vào undocumented behavior. Pin dependency và có regression suite chạy trên môi trường ADB test.

## 17. Scaling và workload management

ADB có các khả năng điều chỉnh compute/storage theo service model và cấu hình. Scaling có thể ảnh hưởng chi phí và performance.

### 17.1. Scale compute

Trước khi tăng compute:

- Xác định bottleneck CPU, I/O, memory, concurrency hay SQL plan.
- Kiểm tra thời điểm tải cao và workload mix.
- Đánh giá parallelism và service class.
- Đo latency/throughput trước/sau.
- Kiểm tra chi phí theo đơn vị billing của dịch vụ.

Scale compute có thể giúp workload CPU-bound, nhưng không tự sửa query kém, lock contention hoặc network latency.

### 17.2. Auto scaling

Nếu dịch vụ hỗ trợ auto scaling, xác định:

- Điều kiện và giới hạn scaling.
- Hành vi khi peak workload.
- Cost impact.
- Quota/compartment budget.
- Monitoring và alert.
- Hệ quả với connection pool và concurrency.

Không để auto scaling thay thế capacity governance. Đặt budget, alert và policy để tránh tăng compute ngoài dự kiến.

### 17.3. Storage scaling

Theo dõi storage usage, growth, retention và backup footprint. Kiểm tra giới hạn/tùy chọn tăng storage của service model. Không đợi tới khi storage gần đầy mới lập kế hoạch.

## 18. Monitoring và observability

Vận hành ADB cần quan sát cả database metrics và cloud resource metrics.

### 18.1. Database-level metrics

Theo dõi:

- CPU/database time.
- Active sessions.
- SQL execution time.
- Buffer gets và physical reads.
- Wait events.
- Connection errors.
- Tablespace/storage usage.
- Transaction rate.
- Failed login và privilege errors.
- Long-running SQL và blocking sessions.
- Workload service usage.

Dùng các view/tool được ADB cho phép. Một số quyền DBA truyền thống có thể bị giới hạn trong managed service; không giả định user ứng dụng có quyền truy cập mọi V$ view.

### 18.2. OCI monitoring

Có thể theo dõi các metric và event được dịch vụ công bố qua OCI Monitoring/Events/Logging tùy cấu hình:

- CPU utilization.
- Storage utilization.
- Availability/lifecycle state.
- Maintenance events.
- Connection/network metrics nếu dịch vụ cung cấp.
- Alarm và notification.

Tên metric và namespace phải lấy từ ADB resource cụ thể và tài liệu OCI hiện hành.

### 18.3. Alert và ownership

Mỗi alert nên có:

- Severity.
- Resource OCID hoặc database identity.
- Metric/query.
- Threshold và duration.
- Business impact.
- Owner/on-call.
- Runbook.
- Escalation path.

Một alert CPU cao cần dẫn tới phân tích SQL/workload; một alert wallet expiry cần dẫn tới rotation owner; một alert OCI resource lifecycle cần dẫn tới cloud operations.

## 19. High availability và disaster recovery

ADB cung cấp các khả năng availability/recovery tùy service model và cấu hình. Khách hàng cần chọn topology theo RTO/RPO.

Các lựa chọn có thể bao gồm:

- Managed redundancy trong nền tảng.
- Autonomous Data Guard/standby capabilities nếu được cung cấp và bật.
- Cross-region disaster recovery theo cấu hình/edition hỗ trợ.
- Backup và point-in-time restore.
- Application retry/reconnect.
- Data export/replication cho yêu cầu riêng.

### 19.1. HA không giống backup

HA giúp dịch vụ tiếp tục hoạt động khi một số thành phần lỗi. Backup/restore giúp khôi phục dữ liệu sau lỗi logic, xóa nhầm hoặc sự cố lớn.

Standby có thể replicate thao tác xóa nhầm hoặc thay đổi dữ liệu sai. Vì vậy, standby không thay thế backup.

### 19.2. Kiểm thử failover

- Xác định primary/standby role.
- Kiểm tra lag/protection state nếu được expose.
- Thực hiện switchover/failover theo ADB runbook.
- Kiểm tra service alias và application reconnect.
- Xác nhận transaction outcome.
- Đo RTO/RPO thực tế.
- Kiểm tra backup sau role transition.
- Ghi lại mọi manual action và follow-up.

Không chạy lệnh Data Guard thủ công dành cho database tự quản lý nếu ADB service không cho phép hoặc không hỗ trợ. Sử dụng thao tác/automation được dịch vụ cung cấp.

## 20. Bảng phân định trách nhiệm vận hành

Ranh giới chính xác phụ thuộc service model, hợp đồng, edition và cấu hình. Bảng dưới đây là khung shared-responsibility để lập RACI, không thay thế Oracle service description.

| Hạng mục | Oracle/service provider | Khách hàng/tổ chức |
|---|---|---|
| Data center, phần cứng và nền tảng Exadata | Quản lý theo dịch vụ | Chọn region/service model và yêu cầu |
| Provisioning database service | Cung cấp automation/control plane | Chọn cấu hình, compartment, workload |
| Database infrastructure patching | Thực hiện theo lifecycle dịch vụ | Theo dõi maintenance, test ứng dụng |
| Backup automation | Cung cấp và vận hành theo service policy | Chọn yêu cầu, retention option nếu có, kiểm thử restore |
| Database schema và data model | Nền tảng lưu trữ | Thiết kế, thay đổi và quản lý |
| Database users/roles/grants | Cung cấp database engine | Tạo, review, revoke và audit |
| Application SQL/JDBC/ORM | Không sở hữu application logic | Phát triển, tuning và compatibility |
| Wallet/client certificate | Cung cấp cơ chế tạo/tải/rotate theo dịch vụ | Bảo vệ, phân phối, rotate và thu hồi trong client estate |
| OCI IAM policy | Cung cấp IAM platform | Thiết kế least privilege và quản trị group/policy |
| VCN/NSG/private connectivity | Cung cấp network platform | Thiết kế route, subnet, access policy theo ownership |
| Data classification/privacy | Cung cấp control nền tảng theo dịch vụ | Phân loại, retention, lawful use và access |
| Encryption at rest | Dịch vụ cung cấp encryption nền tảng theo cấu hình | Quản lý lựa chọn customer-managed key nếu dùng |
| Monitoring nền tảng | Công bố metrics/events theo dịch vụ | Thiết lập alert, owner và response |
| Business continuity | Cung cấp capability được hỗ trợ | Chọn RTO/RPO, topology và diễn tập |
| Application recovery | Không đảm bảo business behavior của app | Kiểm thử, reconnect, reconcile và xác nhận nghiệp vụ |
| Cost governance | Cung cấp usage/billing data | Budget, tagging, alert và tối ưu workload |

### 20.1. Ranh giới không phải lúc nào cũng cố định

Ví dụ backup: Oracle có thể tự động thực hiện backup và quản lý hạ tầng backup, nhưng khách hàng vẫn cần hiểu retention, restore options, quyền restore và kiểm thử dữ liệu sau phục hồi.

Ví dụ patching: Oracle có thể patch database service, nhưng khách hàng phải kiểm tra ứng dụng, JDBC driver, SQL plan, stored procedure và integration sau maintenance.

Ví dụ wallet: OCI cung cấp cơ chế tạo/tải wallet, nhưng khách hàng phải bảo vệ file trên mọi host, container, CI/CD và workstation đã nhận wallet.

## 21. Security baseline

### 21.1. Least privilege

- OCI IAM policy chỉ cấp quyền resource cần thiết.
- Tách cloud operator và database developer.
- Database application user chỉ có quyền trên object cần thiết.
- Không dùng ADMIN account trong ứng dụng runtime.
- Tách schema owner và runtime schema nếu phù hợp.
- Review EXECUTE grants trên package.
- Thu hồi quyền khi workload hoặc nhân sự kết thúc.

### 21.2. Secret management

- Lưu database password và wallet password trong secret manager được phê duyệt.
- Không commit wallet ZIP, private key hoặc credential.
- Không đưa wallet vào Docker image layer.
- Dùng secret volume hoặc secret injection phù hợp.
- Hạn chế quyền đọc và audit truy cập.
- Có lịch rotation và incident revocation.
- Không log connection string có secret.

### 21.3. Encryption

ADB thường cung cấp encryption-at-rest và TLS capability theo dịch vụ. Khách hàng cần chọn chế độ kết nối, bảo vệ client wallet và quản lý key theo mô hình đã chọn.

Nếu dùng customer-managed keys qua OCI Vault, xác định owner key, rotation, availability, policy và quy trình phục hồi. Mất quyền truy cập key có thể ảnh hưởng khả năng sử dụng dữ liệu được bảo vệ.

### 21.4. Audit

Bật và cấu hình audit theo yêu cầu. Theo dõi:

- Failed/successful login.
- Privilege changes.
- User/role changes.
- DDL/schema changes.
- Sensitive table access.
- Administrative operations.
- Wallet download/rotation theo OCI audit trail nếu có.
- Network access configuration changes.

Giữ log trong thời hạn phù hợp và hạn chế người có thể sửa/xóa log.

## 22. Runbook: onboarding một ứng dụng mới

### Bước 1 — Phân loại workload

Xác định ATP/ADW, service alias, concurrency, latency, data classification, RTO/RPO và network location.

### Bước 2 — Tạo cloud access

Tạo compartment/group/policy phù hợp cho operator. Không cấp quyền quản trị toàn tenancy nếu chỉ cần quản lý một database resource.

### Bước 3 — Tạo database identity

Tạo schema/user, role và object grants tối thiểu. Không dùng ADMIN cho connection runtime.

### Bước 4 — Thiết lập network

Chọn public access với ACL hoặc private endpoint theo security design. Xác nhận DNS, route, NSG, firewall và source network.

### Bước 5 — Phát hành wallet

Tải wallet theo mTLS/TLS mode được chọn, lưu vào secret/secure filesystem, thiết lập owner/mode và inventory.

### Bước 6 — Cấu hình JDBC

Dùng đúng TNS alias/workload service, TNS_ADMIN và Oracle JDBC driver tương thích. Inject database credential từ secret store nếu phương thức auth yêu cầu.

### Bước 7 — Kiểm tra

- TLS handshake.
- Database login.
- SERVICE_NAME.
- SESSION_USER/CURRENT_SCHEMA.
- Read/write permission.
- Connection pool behavior.
- Failover/reconnect.
- Query latency và workload service.

### Bước 8 — Đưa vào vận hành

Đăng ký owner/on-call, monitoring, backup/restore expectations, wallet rotation, maintenance notifications và runbook.

## 23. Runbook: wallet rotation

1. Mở inventory mọi client đang dùng wallet.
2. Xác định wallet hiện tại, database, môi trường, authentication mode và ngày phát hành.
3. Xác nhận rotation action và hiệu lực thu hồi theo ADB documentation.
4. Tải wallet mới bằng OCI principal được phê duyệt.
5. Lưu vào secret manager/versioned secure path.
6. Deploy wallet mới tới canary client.
7. Tạo connection mới và xác minh database/service/user.
8. Rolling update các app instance còn lại.
9. Recycle pool để loại connection cũ.
10. Theo dõi login/handshake failure và workload errors.
11. Thu hồi credential cũ theo policy.
12. Xác nhận wallet cũ không còn được dùng và dọn bản sao theo retention.
13. Ghi audit evidence và cập nhật inventory.

Nếu rotation thất bại, dùng quy trình rollback được phê duyệt và xác minh trạng thái credential cũ còn hiệu lực trước khi quay lại. Không giả định wallet cũ luôn còn hoạt động sau rotation.

## 24. Runbook: ứng dụng không kết nối được ADB

### Bước 1 — Kiểm tra service state

Xác nhận ADB resource state và maintenance event trong OCI Console/API.

### Bước 2 — Kiểm tra network

- DNS resolve đúng.
- Route và firewall.
- Public access ACL hoặc private endpoint.
- Subnet/NSG/security list.
- VPN/FastConnect nếu on-premises.
- Proxy nếu môi trường yêu cầu.

### Bước 3 — Kiểm tra wallet và TNS

- Wallet đúng database và đúng môi trường.
- File đầy đủ, không corrupt.
- TNS_ADMIN trỏ đúng thư mục.
- Alias tồn tại trong tnsnames.ora.
- sqlnet.ora và wallet path hợp lệ.
- Service alias đúng workload.

### Bước 4 — Kiểm tra driver và authentication

- Oracle JDBC version tương thích.
- TLS/mTLS mode đúng.
- Database username/password hoặc identity mechanism đúng.
- Wallet password chỉ dùng cho mục đích wallet.
- Certificate còn hiệu lực và chain hợp lệ.

### Bước 5 — Kiểm tra database authorization

Kết nối thành công nhưng ORA-01031 hoặc query bị từ chối là vấn đề database privilege. Kiểm tra grants/roles/schema, không sửa network policy.

### Bước 6 — Kiểm tra pool

Nếu kết nối mới thành công nhưng request vẫn lỗi, kiểm tra pool đang giữ connection cũ, validation, timeout và pool recycle.

Ghi full error chain, timestamp, service alias, driver version và client environment; che password/token/wallet contents trước khi gửi log.

## 25. Runbook: sau maintenance hoặc restore

- Xác nhận ADB resource state.
- Kiểm tra database service và role nếu có standby.
- Kiểm tra connection pool có tạo physical connection mới.
- Xác nhận TNS alias, wallet và authentication.
- Chạy read/write smoke test.
- Xác minh schema version và invalid objects nếu có thay đổi liên quan.
- Kiểm tra scheduled jobs, integration và data pipeline.
- Đối soát dữ liệu nghiệp vụ.
- Đo latency, throughput và error rate.
- Xác nhận backup/recovery configuration sau restore.
- Cập nhật incident/change record và owner.

Restore database có thể tạo resource/endpoint/service identity khác tùy cách thực hiện. Không giả định ứng dụng dùng nguyên connection string cũ; kiểm tra lại wallet, alias, IAM/network access và secrets.

## 26. Bài thực hành

Thực hiện trong tenancy/lab được phê duyệt.

### Bài 1 — Nhận diện service model

Mở một ADB lab và ghi deployment model, workload type, region, compute/storage configuration và network mode.

### Bài 2 — Phân biệt IAM và database user

Tạo một OCI group có quyền đọc metadata resource theo policy giới hạn và một database user chỉ có CREATE SESSION/SELECT trên bảng test. Chứng minh hai lớp quyền độc lập.

### Bài 3 — Tải và kiểm tra wallet

Tải wallet từ database lab, liệt kê file, đặt quyền filesystem tối thiểu và ghi nhận alias trong tnsnames.ora. Không đưa file wallet vào Git.

### Bài 4 — Kết nối TLS/mTLS

Kết nối bằng client được hỗ trợ. Xác nhận TLS mode, database user và service name. So sánh lỗi network, TLS và authentication.

### Bài 5 — JDBC TNS_ADMIN

Cấu hình Oracle JDBC Thin bằng TNS alias và TNS_ADMIN. Kiểm tra connection pool tạo connection mới và query session identity.

### Bài 6 — Workload service

Chạy cùng một query workload qua các service alias được cấp. So sánh concurrency, latency, execution behavior và service policy.

### Bài 7 — Wallet rotation

Tạo quy trình canary/rolling rotation trong lab. Xác nhận connection mới dùng wallet mới và pool cũ được recycle.

### Bài 8 — Private endpoint

Nếu lab hỗ trợ, cấu hình private access, DNS và route. Xác nhận client ngoài network không được phép truy cập.

### Bài 9 — Backup/restore

Thực hiện clone/restore theo khả năng của service lab. Đo thời gian và kiểm tra database identity, user, schema và application reconnect.

### Bài 10 — Maintenance rehearsal

Theo dõi maintenance event, chuẩn bị smoke test, recycle pool và ghi nhận recovery time.

### Bài 11 — Monitoring

Tạo alarm cho metric được dịch vụ công bố, chỉ định owner, severity và runbook.

### Bài 12 — Responsibility matrix

Lập RACI giữa cloud operations, DBA, application team, security và business owner cho wallet, IAM, database privilege, patching, backup, restore và incident response.

## 27. Checklist production readiness

### Service và workload

- [ ] Chọn đúng ATP/ADW và deployment model.
- [ ] Compute/storage được sizing theo workload.
- [ ] Workload service alias được chọn có chủ đích.
- [ ] Có capacity/budget/auto-scaling policy.
- [ ] Đã xác định region, availability và DR requirements.

### Identity và access

- [ ] OCI IAM policy theo least privilege.
- [ ] Database users/roles riêng cho ứng dụng.
- [ ] Không dùng ADMIN account trong runtime.
- [ ] Quyền tải/rotate wallet có owner.
- [ ] Database grants và OCI IAM được review riêng.
- [ ] Secret và wallet có inventory/owner/expiry.

### Network và wallet

- [ ] Public ACL hoặc private endpoint đúng design.
- [ ] DNS, route, NSG/firewall được kiểm tra.
- [ ] TLS/mTLS mode được xác định.
- [ ] Wallet đúng database/environment.
- [ ] Wallet directory có filesystem permission tối thiểu.
- [ ] TNS_ADMIN và alias đúng workload service.
- [ ] JDBC driver tương thích.
- [ ] Wallet rotation và revocation đã được diễn tập.

### Operations và recovery

- [ ] Maintenance notification có owner.
- [ ] Application reconnect/retry được kiểm thử.
- [ ] Backup retention và restore capability được xác nhận.
- [ ] RTO/RPO được business owner chấp thuận.
- [ ] Restore/clone test có bằng chứng.
- [ ] Monitoring, alarm và escalation hoạt động.
- [ ] Cost budget và usage alert được thiết lập.
- [ ] Audit và log retention được cấu hình.
- [ ] RACI và runbook có owner rõ ràng.

## 28. Ghi nhớ cốt lõi

- Autonomous Database là managed service tự động hóa nhiều tác vụ hạ tầng/database; khách hàng vẫn chịu trách nhiệm về dữ liệu, schema, quyền, ứng dụng và business recovery.
- Serverless và Dedicated có deployment/operational model khác nhau; chọn theo isolation, governance, capacity và chi phí.
- ATP hướng tới transaction processing; ADW hướng tới analytical workload; chọn workload service phù hợp.
- Wallet hỗ trợ client connection security và mTLS; nó không phải database user, password, IAM policy hay backup.
- TLS xác minh server; mTLS xác minh cả client ở tầng certificate; database authentication/authorization vẫn là lớp riêng.
- Wallet ZIP thường chứa wallet files và Oracle Net configuration như tnsnames.ora/sqlnet.ora; xác nhận nội dung thực tế theo loại wallet.
- Wallet password khác database password và OCI API credential.
- Bảo vệ auto-login wallet bằng filesystem/secret management; không commit wallet hoặc private key vào source control/image.
- TNS_ADMIN trỏ tới thư mục client chứa Oracle Net config/wallet; TNS alias xác định service kết nối.
- Các suffix HIGH/MEDIUM/LOW/TP/TPURGENT chỉ là ví dụ service name thường gặp; dùng alias thật được cung cấp cho database cụ thể.
- JDBC driver, TNS alias và wallet phải tương thích; kiểm tra SERVICE_NAME/SESSION_USER sau kết nối.
- OCI IAM quản lý cloud resource; database roles/grants quản lý dữ liệu. Có quyền quản lý ADB không đồng nghĩa có quyền SELECT bảng.
- Resource principal và OCI IAM policy cho phép database resource gọi dịch vụ cloud theo quyền được cấp; không phải quyền mặc định.
- Public access ACL, private endpoint, VCN/NSG, database network ACL và host firewall kiểm soát các luồng network khác nhau.
- Thay wallet file không tự cập nhật connection đang tồn tại trong pool; cần canary, recycle pool và thu hồi credential theo quy trình.
- Oracle quản lý các hoạt động hạ tầng theo service contract; khách hàng vẫn phải theo dõi maintenance, kiểm thử ứng dụng và xác nhận nghiệp vụ.
- Backup automation không thay thế restore rehearsal; standby/HA không thay thế backup chống lỗi logic.
- Scaling có thể tăng capacity và cost; cần đo bottleneck, service class và budget.
- Monitoring cần bao gồm cloud resource, database workload, connection pool, wallet lifecycle và business service.
- Ranh giới trách nhiệm cần được ghi thành RACI/runbook giữa cloud operations, DBA, security, application và business owner.

### Tài liệu Oracle nên đối chiếu

- [Oracle Autonomous Database Documentation](https://docs.oracle.com/en/cloud/paas/autonomous-database/) — Service concepts, provisioning, connectivity, operations and lifecycle.
- [Oracle Autonomous Database Serverless Documentation](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/) — Serverless deployment, workload types and administration.
- [Oracle Autonomous Database Dedicated Documentation](https://docs.oracle.com/en/cloud/paas/autonomous-database/dedicated/) — Dedicated infrastructure and Autonomous Container Database concepts.
- [Oracle Autonomous Database Security Guide](https://docs.oracle.com/en/cloud/paas/autonomous-database/security/) — TLS/mTLS, client credentials wallets, network access and security controls.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC Thin connectivity, Oracle Net configuration and driver behavior.
- [Oracle Cloud Infrastructure IAM Documentation](https://docs.oracle.com/en-us/iaas/Content/Identity/home.htm) — Users, groups, dynamic groups and policies.
- [Oracle Cloud Infrastructure Networking Documentation](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm) — VCN, subnet, NSG and private connectivity.
- [Oracle Cloud Infrastructure Monitoring Documentation](https://docs.oracle.com/en-us/iaas/Content/Monitoring/home.htm) — Metrics, alarms and monitoring concepts.

Service capabilities, wallet rotation semantics, service aliases, backup retention, patch windows, authentication modes and customer/provider responsibilities vary by ADB model, region, edition and contract. Confirm the exact database's OCI Console configuration, current service documentation and support terms; test wallet rotation, connection pool recovery, restore and application behavior in a representative non-production environment before production rollout.

