# Phân biệt quản lý Autonomous Database và kết nối JDBC đến cơ sở dữ liệu

Oracle Autonomous Database (tài liệu OCI hiện hiển thị tên Autonomous AI Database ở nhiều trang quản trị mới) là dịch vụ cơ sở dữ liệu managed. Oracle vận hành nhiều thành phần hạ tầng, tự động hóa backup, patching và một phần tối ưu hóa; đội ứng dụng vẫn phải quản lý quyền OCI, database user, schema, kết nối, transaction và pool connection.

Hai nhóm công việc này dùng hai mặt phẳng khác nhau:

- **Quản lý dịch vụ trên OCI control plane:** provision, chọn workload, compartment/region, cấu hình mạng, scale compute/storage, bật auto scaling, start/stop, backup/restore, clone, encryption key và lifecycle.
- **Kết nối database trên data plane:** ứng dụng dùng Oracle JDBC Thin Driver, TNS service name, TLS hoặc mTLS wallet, database username/password hoặc cơ chế xác thực database được cấu hình, rồi thực thi SQL qua DataSource/connection pool.

OCI IAM policy cho phép một operator quản lý tài nguyên Autonomous Database. Nó không tự cấp quyền SELECT/INSERT cho ứng dụng trong database. Ngược lại, database user có quyền đọc bảng không mặc nhiên được quyền scale, stop, restore hay terminate Autonomous Database trên OCI.

Bài học dùng document-service làm ví dụ. Nhóm Platform provision Autonomous Database và cấu hình network/backup; DBA tạo schema và user; Spring Boot kết nối qua JDBC, quản lý DataSource, transaction và pool. Ứng dụng chỉ nhận credential cần thiết cho schema của nó, không dùng tài khoản ADMIN để chạy nghiệp vụ.

## 1. Mục tiêu học tập và kiến trúc

Sau bài học, bạn có thể:

1. Phân biệt OCI control plane với database SQL/data plane.
2. Xác định việc nào cần OCI IAM policy và việc nào cần database user/role/grant.
3. Mô tả vòng đời Autonomous Database: provision, scale, auto scaling, stop/start, backup, restore, clone và terminate.
4. Cấu hình network access bằng public endpoint, ACL hoặc private endpoint.
5. Chọn đúng workload type và predefined database service name.
6. Phân biệt JDBC Thin, TLS và mTLS; biết khi nào cần wallet.
7. Tải, phân phối, bảo vệ và rotate instance wallet.
8. Cấu hình Oracle JDBC URL, TNS alias và TNS_ADMIN.
9. Cấu hình Spring Boot DataSource với HikariCP hoặc Oracle UCP.
10. Thiết kế connection pool phù hợp với số replica, session budget và service concurrency.
11. Quản lý database user, password, secret, schema migration và transaction.
12. Kiểm thử kết nối, quyền, TLS, pool exhaustion, failover và lỗi thường gặp.

~~~mermaid
flowchart TD
    subgraph CP["OCI Control Plane"]
        A["OCI Console / API / Terraform"]
        B["OCI IAM policy"]
        C["Autonomous Database lifecycle"]
        D["Network, ECPU, storage, backup, key"]
        A --> B
        B --> C
        C --> D
    end

    subgraph DP["Database Data Plane"]
        E["Spring Boot application"]
        F["Oracle JDBC Thin Driver"]
        G["TLS / mTLS + TNS service"]
        H["Autonomous Database"]
        I["DB user / role / schema / SQL grants"]
        E --> F --> G --> H
        I --> H
    end

    D -. "Provisioned endpoint and connection details" .-> G
    B -. "Does not grant SQL table privileges" .-> I
~~~

**OCI IAM quyết định ai được quản lý dịch vụ. Database grants quyết định user kết nối được làm gì trong database. JDBC là đường kết nối của ứng dụng tới database, không phải API quản trị dịch vụ OCI.**

## 2. Hai mặt phẳng quản lý cần tách biệt

### 2.1. OCI control plane

Control plane quản lý tài nguyên Autonomous Database trong tenancy/compartment. Các thao tác thường gặp:

- Provision hoặc terminate một database.
- Đổi display name, workload type hoặc compartment.
- Scale ECPU và storage.
- Bật/tắt compute auto scaling hoặc storage auto scaling.
- Start, stop, restart và lên lịch start/stop.
- Cấu hình network access, ACL, private endpoint và NSG.
- Cấu hình customer-managed encryption key.
- Xem backup, restore tới thời điểm phù hợp và clone database.
- Cấu hình disaster recovery/Autonomous Data Guard.
- Xem maintenance, lifecycle event và metric dịch vụ.

Các thao tác này được thực hiện qua OCI Console, OCI REST API, OCI SDK, OCI CLI hoặc Terraform. Operator cần IAM policy cho Autonomous Database và backup resource tương ứng.

### 2.2. Database data plane

Data plane là những thao tác bên trong database sau khi một client kết nối thành công:

- Đăng nhập bằng database user hoặc cơ chế xác thực database đã cấu hình.
- Tạo schema, table, index, sequence, view và procedure.
- Cấp role và object privilege.
- Chạy SELECT/INSERT/UPDATE/DELETE.
- Quản lý transaction, isolation và locking.
- Thực hiện migration bằng Flyway/Liquibase.
- Theo dõi session, SQL, execution plan và database wait.
- Quản lý application connection pool.

Những thao tác này cần database credential và SQL privilege. Một user có quyền kết nối JDBC có thể không có quyền tạo user, đổi cấu hình dịch vụ hay restore database.

### 2.3. So sánh quyền

| Công việc | Mặt phẳng | Quyền cần thiết |
| --- | --- | --- |
| Xem Autonomous Database trong Console | OCI control plane | OCI IAM inspect |
| Scale ECPU/storage | OCI control plane | OCI IAM use theo policy |
| Stop/start database | OCI control plane | OCI IAM use theo policy |
| Restore từ backup | OCI control plane | OCI IAM use Autonomous Database và read backup |
| Terminate database | OCI control plane | OCI IAM manage Autonomous Database |
| Tạo schema/user | Database data plane | Database account có SQL privilege tương ứng |
| SELECT bảng hợp đồng | Database data plane | Database user có SELECT object privilege |
| Chạy Flyway migration | Database data plane | Migration account có DDL privilege cần thiết |
| Mở JDBC connection | Database data plane | Network reachability, TLS/mTLS và database authentication |
| Thay đổi IAM policy | OCI control plane | OCI IAM policy administration |

OCI IAM policy tham khảo cho operator:

~~~text
Allow group DBOperators to inspect autonomous-databases in compartment Production
Allow group DBOperators to use autonomous-databases in compartment Production
Allow group DBOperators to read autonomous-backups in compartment Production
~~~

Các statement trên minh họa quyền xem, vận hành và đọc backup. Việc restore cần quyền use Autonomous Database cùng read Autonomous Backups theo permission mapping. Terminate database là thao tác phá hủy và cần manage autonomous-databases; không cấp quyền này cho nhóm ứng dụng.

### 2.4. Database ADMIN không phải OCI administrator

ADMIN là database user có quyền quản trị database theo mô hình Autonomous Database. ADMIN không tự động là OCI tenancy administrator và không thay thế OCI IAM user/group.

Tương tự, OCI administrator không nhất thiết có thể đăng nhập SQL nếu không có database credential hoặc cơ chế database authentication phù hợp.

Không dùng ADMIN làm user runtime của Spring Boot. Tạo schema owner và application user riêng, sau đó cấp đúng quyền cho từng vai trò.

## 3. Provision và quản lý vòng đời Autonomous Database

### 3.1. Provisioning

Khi tạo Autonomous Database, operator cần xác định:

- Compartment và region.
- Database display name và database name.
- Workload type, ví dụ Transaction Processing hoặc Data Warehouse.
- Compute model và số ECPU.
- Storage capacity.
- Compute auto scaling và storage auto scaling.
- Network access option.
- Encryption key option.
- Backup/retention option.
- License model và các tùy chọn dịch vụ.

Tên giao diện và một số tùy chọn có thể thay đổi theo workload, region và compute model. Dùng thông tin trong trang provision hiện hành và tài liệu của loại database đang triển khai.

### 3.2. ECPU và OCPU

Tài liệu Autonomous AI Database hiện dùng ECPU làm compute model hiện hành; OCPU là mô hình legacy có thể còn xuất hiện ở tài nguyên cũ. Không copy số liệu ECPU sang OCPU vì đơn vị, concurrency và cách tính có thể khác.

Khi scale:

- Xem ECPU hiện tại và giới hạn tenancy.
- Đánh giá workload CPU, I/O, concurrency và latency.
- Kiểm tra connection service đang dùng.
- Kiểm tra pool connection và tổng số replica.
- Thực hiện thay đổi trong maintenance/change window phù hợp.
- Theo dõi metric trước/sau để xác nhận lợi ích.

### 3.3. Compute auto scaling

Compute auto scaling cho phép database dùng thêm CPU/I/O khi workload cần, trong giới hạn dịch vụ. Tài liệu hiện hành mô tả compute auto scaling có thể dùng tối đa khoảng ba lần mức CPU cơ sở trong điều kiện được hỗ trợ.

Auto scaling không thay thế capacity planning. Nó có thể làm tăng mức tiêu thụ và chi phí khi tải tăng. Theo dõi ECPU allocated, utilization, latency và concurrency để hiểu mức scale thực tế.

### 3.4. Storage auto scaling

Storage auto scaling cho phép database mở rộng dung lượng sử dụng trong giới hạn cấu hình. Tài liệu hiện hành mô tả có thể mở rộng đến ba lần reserved base storage khi tính năng được bật.

Cần theo dõi dung lượng và tốc độ tăng dữ liệu. Auto scaling không phải retention policy: ứng dụng vẫn phải xóa/archival dữ liệu theo vòng đời nghiệp vụ.

### 3.5. Stop, start và restart

Stop/start là lifecycle operation của dịch vụ, không phải JDBC command.

Trước khi stop:

1. Ngừng nhận request mới cần database.
2. Drain background worker và transaction đang chạy.
3. Chờ transaction hoàn tất hoặc rollback theo kế hoạch.
4. Đóng pool connection hoặc đưa ứng dụng vào maintenance mode.
5. Thực hiện stop trên OCI.
6. Xác minh trạng thái dịch vụ và thông báo ứng dụng.

Khi start:

1. Chờ trạng thái Autonomous Database về Available.
2. Kiểm tra network endpoint và service name.
3. Xác minh database user và wallet/certificate còn hiệu lực.
4. Cho application instance khởi động hoặc refill pool.
5. Chạy health check có truy vấn nhẹ.
6. Theo dõi connection errors và request latency.

Ứng dụng không nên retry connection vô hạn trong lúc database đang stop. Dùng backoff có giới hạn và readiness state phù hợp.

### 3.6. Backup, restore và clone

Autonomous Database có automatic backup và tùy chọn long-term backup theo dịch vụ/workload. Backup do Oracle quản lý có tính immutable theo tài liệu hiện hành.

Các khái niệm:

- **Automatic backup:** hỗ trợ phục hồi theo cửa sổ retention cấu hình.
- **Point-in-time recovery:** khôi phục database về thời điểm nằm trong phạm vi backup/recovery được hỗ trợ.
- **Long-term backup:** giữ bản backup theo lịch và retention được chọn.
- **Clone:** tạo database mới từ nguồn hiện tại hoặc backup theo lựa chọn.
- **Restore:** phục hồi database về trạng thái thời điểm được chọn.

Restore có thể làm thay đổi trạng thái dữ liệu hiện tại. Trước khi chạy, xác minh target database, thời điểm, business impact, backup availability, KMS key và kế hoạch kiểm tra dữ liệu. Dùng clone để diễn tập/điều tra khi cần giữ database hiện tại.

Backup database không nhất thiết bao gồm file nằm ngoài database trong Object Storage, ví dụ external table file. Nếu hệ thống dùng external data, phải backup/restore các file đó theo quy trình riêng.

### 3.7. Lifecycle event

OCI có lifecycle event cho start, stop, restart, backup, restore, auto scaling, update, wallet rotation và terminate. Có thể dùng Events/Notifications để gửi cảnh báo tới vận hành.

Không coi một API request thành công là database đã sẵn sàng. Theo dõi trạng thái operation/event và kiểm tra connection thật trước khi đưa traffic trở lại.

## 4. Network access cho Autonomous Database

### 4.1. Ba kiểu truy cập phổ biến

| Kiểu network | Đặc điểm | Trường hợp dùng |
| --- | --- | --- |
| Secure access from everywhere | Public endpoint, có thể không giới hạn IP nếu không cấu hình ACL | Dev/demo có kiểm soát; cần cân nhắc rủi ro |
| Secure access from allowed IPs and VCNs only | Public endpoint nhưng giới hạn nguồn qua ACL | Workload có egress IP/VCN xác định |
| Private endpoint access only | Private IP/hostname trong VCN, không nhận kết nối từ public internet | Production private network |

Mọi kiểu đều dùng kết nối bảo mật TLS/certificate. Network access control quyết định client nào có thể tới endpoint; nó không cấp quyền SQL.

### 4.2. ACL

ACL giới hạn IP hoặc VCN được phép kết nối tới database public endpoint. Nếu ứng dụng chạy trong private subnet sau NAT Gateway, nguồn mà database nhìn thấy có thể là public IP của NAT Gateway; phải cấu hình đúng source CIDR.

Sau khi thay ACL, kiểm tra:

- Public egress IP của workload.
- CIDR của VCN/subnet.
- NAT Gateway hoặc Service Gateway path.
- NSG/security list và route table.
- DNS resolution và TCP connectivity tới port trong connection descriptor.

Không mở 0.0.0.0/0 chỉ để chữa lỗi kết nối production.

### 4.3. Private endpoint

Private endpoint đặt database trong một VCN được chỉ định. Ứng dụng phải có đường mạng tới private endpoint thông qua subnet/peering/on-prem connectivity đã cấu hình.

Cần kiểm tra:

- VCN và subnet đúng.
- DNS hostname resolve tới private IP.
- NSG ingress/egress cho database listener.
- Security list và route table.
- VCN peering hoặc DRG nếu app nằm ở VCN khác.
- Firewall/Network Security Appliance.
- Port trong connection string.

Private endpoint không thay thế TLS hoặc database authentication.

### 4.4. Connectivity test

Trước khi debug JDBC, kiểm tra tầng mạng:

1. DNS lookup hostname từ đúng container/pod/VM.
2. Kiểm tra TCP connect tới port trong descriptor.
3. Xác minh route và firewall.
4. Kiểm tra ACL hoặc private endpoint rules.
5. Kiểm tra client không đi qua proxy sai cấu hình.
6. Sau khi network thông, mới kiểm tra TLS, wallet và database login.

Ping không chứng minh Oracle listener có thể truy cập. Dùng TCP test trên đúng host/port.

## 5. JDBC Thin Driver và connection string

### 5.1. JDBC Thin

Oracle JDBC Thin Driver là driver Java thuần, dùng Oracle Net qua TCP/TLS và không cần Oracle Client native libraries cho kết nối thông thường. Đây là lựa chọn phổ biến cho Spring Boot.

Dependency Maven:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc17</artifactId>
    <version>ORACLE_JDBC_VERSION_COMPATIBLE_WITH_JDK</version>
</dependency>
~~~

Thay version minh họa bằng bản JDBC driver được chứng nhận với JDK, Spring Boot và Oracle Database đang sử dụng. Oracle hiện có các artifact như ojdbc8, ojdbc11 và ojdbc17; chọn artifact theo JDK/JDBC API tương thích. Không dùng driver quá cũ chỉ vì một sample trên Internet vẫn chạy.

Nếu dùng Oracle UCP, thêm dependency UCP cùng release family/version tương thích:

~~~xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ucp</artifactId>
    <version>ORACLE_JDBC_VERSION_COMPATIBLE_WITH_JDK</version>
</dependency>
~~~

Quản lý version bằng dependency management/version catalog. Không trộn tùy tiện ojdbc, ucp và companion security jars ở các release khác nhau.

### 5.2. Service name và TNS alias

Mỗi Autonomous Database cung cấp các predefined database service names. TNS alias và connect descriptor được hiển thị trong OCI Console hoặc file tnsnames.ora trong wallet.

Ví dụ alias thường có hậu tố:

~~~text
database_tpurgent
database_tp
database_high
database_medium
database_low
~~~

Tên thật phụ thuộc database. Không tự ghép alias chỉ từ display name; hãy dùng connection string được tạo cho instance.

### 5.3. Chọn database service theo workload

| Service | Mục đích tổng quát | Đặc điểm |
| --- | --- | --- |
| TPURGENT | Transaction cực kỳ nhạy thời gian | Ưu tiên cao nhất; hỗ trợ manual parallelism |
| TP | OLTP điển hình | Không chạy parallelism mặc định cho câu lệnh |
| HIGH | Reporting/analytics ít concurrency | Parallel execution, số statement đồng thời thấp hơn |
| MEDIUM | Analytics/batch | Parallel execution và concurrency theo cấu hình |
| LOW | Reporting/batch ưu tiên thấp | Không chạy parallelism mặc định |

Với API nghiệp vụ Spring Boot có transaction ngắn, thường bắt đầu thử service TP. TPURGENT chỉ dành cho luồng thực sự cần ưu tiên cao và đã được đánh giá tài nguyên. MEDIUM phù hợp batch/analytics hơn; HIGH cho workload phân tích ít người dùng; LOW cho tác vụ nền ưu tiên thấp.

Concurrency limit và degree of parallelism phụ thuộc ECPU/OCPU, auto scaling, workload và cấu hình hiện hành. Đừng sao chép một con số cố định từ môi trường khác. Theo dõi database service metrics và kiểm tra tài liệu service names cho compute model của instance.

Không chỉ đổi consumer group trên một connection rồi cho rằng nó tương đương kết nối bằng service khác. Service name có thể cấu hình thêm các thuộc tính session/resource manager. Dùng service alias đúng hoặc API CS_SESSION.SWITCH_SERVICE khi use case và quyền cho phép.

### 5.4. JDBC URL với TNS alias

Với wallet-based connection và JDBC Thin Driver hỗ trợ TNS_ADMIN trong URL:

~~~text
jdbc:oracle:thin:@database_tp?TNS_ADMIN=/run/secrets/adb-wallet
~~~

Trong đó:

- database_tp là TNS alias thực tế có trong tnsnames.ora.
- TNS_ADMIN trỏ tới thư mục chứa tnsnames.ora, sqlnet.ora, ojdbc.properties và wallet files.
- Path phải tồn tại và process Spring Boot có quyền đọc.
- Alias phải khớp service được chọn trong database connection page.

JDBC driver 18.3 trở lên hỗ trợ đưa TNS_ADMIN vào URL. Với driver cũ hơn, có thể phải cấu hình system property hoặc connection property theo tài liệu driver; nên ưu tiên driver được hỗ trợ hiện hành.

### 5.5. JDBC URL trực tiếp

Với walletless TLS, OCI Console cung cấp connect descriptor có protocol TCPS, host, port, service_name và server DN matching. Có thể đặt descriptor đó sau tiền tố:

~~~text
jdbc:oracle:thin:@(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1521)(host=adb.example.oraclecloud.com))(connect_data=(service_name=database_tp.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
~~~

Đây là ví dụ cấu trúc. Host, port và service_name phải lấy từ connection string TLS của chính database. TLS có thể dùng port 1521 hoặc 1522 tùy descriptor được cấp; mTLS thường dùng port 1522. Không tự thay port trong connect descriptor.

## 6. TLS, mTLS và wallet

### 6.1. TLS

TLS mã hóa kết nối và xác minh danh tính server qua certificate chain. Với walletless TLS:

- Database phải cho phép TLS authentication.
- JDBC Thin Driver/JDK phải đáp ứng yêu cầu TLS của dịch vụ.
- Ứng dụng dùng database username/password hoặc database authentication mechanism được cấu hình.
- Client xác minh server certificate/hostname.
- Không cần tải Oracle wallet cho JDBC Thin trong cấu hình TLS được hỗ trợ.

TLS không có nghĩa kết nối là public hoặc bỏ qua ACL/private endpoint. Network access vẫn phải được cho phép.

### 6.2. Mutual TLS (mTLS)

mTLS xác thực hai chiều: client xác thực server và database xác thực client certificate. Với Autonomous Database, wallet hoặc JKS client credentials được dùng cho mTLS.

mTLS cần:

- Wallet/client credential được tải cho database.
- TNS alias/connect descriptor.
- JDBC driver và security configuration tương thích.
- Database username/password hoặc database auth mechanism phù hợp.
- Network path tới TCPS endpoint.

Nếu database yêu cầu mTLS, walletless TLS sẽ không kết nối được. Nếu database được cấu hình cho phép TLS và mTLS, ứng dụng có thể chọn một trong hai theo connection descriptor.

### 6.3. Khi nào cần wallet?

| Cấu hình database | JDBC Thin wallet |
| --- | --- |
| mTLS Required | Bắt buộc |
| TLS được phép, JDBC Thin/JDK đáp ứng điều kiện | Có thể kết nối walletless |
| mTLS và TLS cùng được phép | Có thể chọn wallet/mTLS hoặc walletless/TLS |
| Driver/JDK cũ hoặc client mode có yêu cầu riêng | Kiểm tra tài liệu tương ứng |

Không kết luận mọi Autonomous Database đều bắt buộc wallet hoặc mọi TLS đều walletless. Trạng thái mTLS, network configuration, JDBC driver và JDK quyết định phương án.

### 6.4. Nội dung wallet

Instance wallet download thường có các file:

| File | Vai trò |
| --- | --- |
| cwallet.sso | Auto-login wallet |
| ewallet.p12 | PKCS12 wallet được bảo vệ bằng wallet password |
| tnsnames.ora | TNS aliases và connect descriptors |
| sqlnet.ora | SQL*Net client configuration |
| ojdbc.properties | JDBC wallet connection properties |
| keystore.jks | Java keystore |
| truststore.jks | Java truststore |
| README | Thông tin wallet/expiration và hướng dẫn |

Wallet không phải file cấu hình công khai. Người có wallet và quyền database phù hợp có thể sử dụng client certificate để kết nối. Bảo vệ toàn bộ thư mục wallet như credential:

- Lưu trong secret manager hoặc secret volume.
- Chỉ mount read-only cho application container.
- Giới hạn file permission, ví dụ 600 trên Linux cho file nhạy cảm.
- Không commit vào Git, build artifact, Docker image hoặc log.
- Không gửi qua email/chat không bảo vệ.
- Phân phối wallet password qua kênh riêng nếu cần.
- Dùng instance wallet cho một database; regional wallet có phạm vi nhiều database trong region và chỉ nên dành cho mục đích quản trị phù hợp.

### 6.5. Wallet rotation

Wallet rotation thay client certificate keys, không phải database user password.

OCI hỗ trợ:
- Immediate rotation: khóa client certificate cũ bị vô hiệu ngay; các kết nối/session hiện tại của database có thể bị chấm dứt. Ứng dụng phải tải wallet mới và cập nhật trước khi reconnect.
- Grace-period rotation: trong khoảng 1 đến 72 giờ, wallet cũ và mới cùng hợp lệ; hết thời gian, wallet cũ bị vô hiệu. Đây là cách hỗ trợ cutover có kế hoạch. Một số Always Free database chỉ hỗ trợ immediate rotation.

Quy trình đề xuất:

1. Xác định tất cả application, batch job và tool đang dùng instance wallet.
2. Tạo rotation window và thông báo owner.
3. Tải wallet mới vào secret store/volume version mới.
4. Deploy canary dùng wallet mới.
5. Xác minh JDBC connection và truy vấn nghiệp vụ.
6. Chuyển toàn bộ instance/pod sang wallet mới.
7. Reload/restart pool để không giữ session cũ.
8. Kết thúc grace period hoặc thực hiện immediate rotation theo incident plan.
9. Xác minh wallet cũ không còn kết nối được.
10. Ghi audit và xóa bản phân phối cũ theo policy.

Nếu wallet bị compromise, ưu tiên containment. Không kéo dài grace period chỉ để tiện triển khai khi attacker có thể dùng certificate cũ.

### 6.6. Wallet rotation khác password rotation

Có hai bí mật khác nhau:

- Wallet/client certificate: xác thực client trong mTLS.
- Database user password: xác thực database user theo username/password.

Rotate wallet không tự đổi password database user. Đổi password database user cũng không tự rotate client certificate. Lập lịch và quy trình riêng cho từng loại.

## 7. Database user, role và schema

### 7.1. Tạo application user

Dùng ADMIN để tạo schema owner/application user ban đầu theo quy trình DBA, sau đó cấp quyền tối thiểu. Ví dụ minh họa:

~~~sql
CREATE USER DOC_APP IDENTIFIED BY "REPLACE_WITH_SECRET_FROM_APPROVED_CHANNEL";

GRANT CREATE SESSION TO DOC_APP;

GRANT SELECT, INSERT, UPDATE, DELETE
ON DOC_OWNER.DOCUMENTS TO DOC_APP;

GRANT SELECT, INSERT, UPDATE, DELETE
ON DOC_OWNER.DOCUMENT_AUDIT TO DOC_APP;
~~~

Cú pháp và quyền DDL cụ thể phụ thuộc schema ownership và ứng dụng. Không đưa password thật vào migration đã commit. Trong production, dùng password được sinh và phân phối qua secret manager hoặc cơ chế xác thực database được tổ chức phê duyệt.

### 7.2. Schema owner và runtime user

Mô hình tốt:

- DOC_OWNER sở hữu bảng, index, sequence và migration object.
- DOC_APP có quyền chạy nghiệp vụ trên object được cấp.
- DOC_MIGRATION là tài khoản riêng dùng trong pipeline migration nếu cần DDL.
- ADMIN chỉ dùng cho tác vụ quản trị có kiểm soát.

Tách migration user và runtime user giúp giảm tác động nếu ứng dụng bị compromise.

### 7.3. OCI IAM và database user không tự liên kết

Một OCI dynamic group hoặc instance principal không tự trở thành database user. JDBC mặc định vẫn xác thực database user. Nếu muốn dùng database IAM token authentication hoặc một cơ chế external identity khác, phải cấu hình riêng theo tài liệu Oracle và database policy; không giả định OCI IAM policy cấp quyền SQL trực tiếp.

## 8. Cấu hình Spring Boot DataSource

### 8.1. Dependency

Với Spring Boot JDBC/JPA, thêm starter phù hợp:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc17</artifactId>
    <version>ORACLE_JDBC_VERSION_COMPATIBLE_WITH_JDK</version>
</dependency>
~~~

Nếu dùng Spring Data JPA, thay hoặc bổ sung starter data-jpa theo kiến trúc dự án. Spring Boot tự cấu hình DataSource khi tìm thấy JDBC driver và URL phù hợp.

Spring Boot ưu tiên HikariCP nếu có trên classpath; starter JDBC và JPA thường kéo HikariCP vào. Hãy kiểm tra version Spring Boot/JDK và driver tương thích trước khi pin dependency.

### 8.2. Cấu hình application.yml cho mTLS wallet

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@database_tp?TNS_ADMIN=/run/secrets/adb-wallet
    username: DOC_APP
    password: INJECT_FROM_SECRET_MANAGER
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      pool-name: document-db-pool
      minimum-idle: 2
      maximum-pool-size: 12
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1500000
      keepalive-time: 300000
~~~

Các giá trị pool chỉ là điểm bắt đầu để đo tải, không phải sizing mặc định cho mọi hệ thống. Username/password phải được inject từ secret manager hoặc external configuration. Không lưu credential thật trong file application.yml.

Path wallet phải được mount vào runtime container/VM. Đảm bảo process có quyền đọc file và TNS_ADMIN trỏ đúng thư mục có tnsnames.ora.

### 8.3. Cấu hình walletless TLS

Nếu database cho phép TLS và client/JDK đáp ứng yêu cầu, có thể dùng connection string TLS lấy từ OCI Console:

~~~yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1521)(host=adb.example.oraclecloud.com))(connect_data=(service_name=database_tp.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
    username: DOC_APP
    password: INJECT_FROM_SECRET_MANAGER
    driver-class-name: oracle.jdbc.OracleDriver
~~~

Đây là ví dụ; dùng nguyên host/port/service/descriptor mà OCI Console cấp. Không tắt server DN matching để chữa lỗi certificate. Hãy sửa hostname, trust chain, JDK hoặc connection descriptor.

### 8.4. Driver class và URL

Spring Boot thường suy ra driver từ JDBC URL. Với Oracle JDBC Thin:

- URL bắt đầu bằng jdbc:oracle:thin:@
- Driver class là oracle.jdbc.OracleDriver.
- Service name/TNS alias phải đúng.
- Với wallet, TNS_ADMIN phải chỉ đúng directory.
- Với TLS direct descriptor, host, port và service name phải đúng.

Không dùng URL jdbc:oracle:oci nếu không chủ ý dùng OCI native driver và đã cài Oracle Client libraries.

### 8.5. Externalized configuration

Cấu hình production nên tách:

- JDBC URL/service alias.
- Database username.
- Database password hoặc token.
- Wallet directory/secret volume.
- Pool settings.
- Connection/read timeout.
- Profile theo môi trường.

Có thể inject bằng environment variables, Kubernetes Secret/CSI secret volume hoặc OCI Vault integration. Không log DataSourceProperties, JDBC URL nếu URL có token/secret, wallet path có thông tin nhạy cảm hoặc password.

## 9. HikariCP và Oracle UCP

### 9.1. Connection pool làm gì?

Mở một kết nối TCP/TLS và database session cho mỗi request rất tốn chi phí. Connection pool giữ sẵn một nhóm connection để ứng dụng mượn/trả theo thời gian.

Luồng:

~~~mermaid
sequenceDiagram
    participant API as Spring request
    participant Pool as HikariCP / UCP
    participant DB as Autonomous Database
    API->>Pool: getConnection()
    Pool-->>API: borrow connection
    API->>DB: execute SQL / transaction
    DB-->>API: result
    API->>Pool: close() returns connection
    Note over Pool: Connection được giữ lại để tái sử dụng
~~~

Trong ứng dụng dùng Spring JDBC/JPA, không tự giữ connection toàn cục hoặc chia sẻ một Connection giữa nhiều request. Transaction manager và pool quản lý vòng đời connection.

### 9.2. HikariCP

HikariCP là lựa chọn mặc định hợp lý cho nhiều Spring Boot application:

- Pool nhẹ và hiệu năng tốt.
- Cấu hình đơn giản.
- Spring Boot auto-configuration hỗ trợ trực tiếp.
- Có metric về active, idle, pending và timeout.
- Phù hợp khi cần JDBC DataSource thông thường.

Ví dụ:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: document-db-pool
      minimum-idle: 2
      maximum-pool-size: 12
      connection-timeout: 30000
      validation-timeout: 5000
      idle-timeout: 600000
      max-lifetime: 1500000
~~~

Không sao chép con số 12 sang mọi deployment. Tính tổng connection trên tất cả pod/replica và job. Nếu 10 pod, mỗi pod max 12, ứng dụng có thể mở tới 120 connection chưa kể migration/admin/monitoring.

### 9.3. Oracle UCP

Universal Connection Pool (UCP) là connection pool của Oracle, có các tích hợp Oracle-specific như connection labeling, Fast Connection Failover/ONS, runtime load balancing và các tính năng HA khi database/service/network hỗ trợ.

Chọn UCP khi cần các tính năng Oracle-specific và đội vận hành hiểu cấu hình/monitoring của UCP. UCP không tự làm ứng dụng có quyền database hay chữa sai JDBC URL.

Ví dụ cấu hình programmatic minh họa:

~~~java
import oracle.ucp.jdbc.PoolDataSource;
import oracle.ucp.jdbc.PoolDataSourceFactory;

public PoolDataSource createPool(
        String jdbcUrl,
        String username,
        String password) throws Exception {

    PoolDataSource pool =
            PoolDataSourceFactory.getPoolDataSource();

    pool.setConnectionFactoryClassName(
            "oracle.jdbc.pool.OracleDataSource");
    pool.setURL(jdbcUrl);
    pool.setUser(username);
    pool.setPassword(password);

    pool.setInitialPoolSize(2);
    pool.setMinPoolSize(2);
    pool.setMaxPoolSize(12);
    pool.setValidateConnectionOnBorrow(true);
    pool.setConnectionValidationTimeout(5);

    return pool;
}
~~~

Đây là ví dụ API UCP. Khi tích hợp với Spring, đăng ký PoolDataSource làm DataSource bean và cấu hình lifecycle/close rõ ràng. Không đồng thời tạo Hikari pool bọc quanh UCP nếu không có chủ đích, vì hai tầng pool làm khó sizing và diagnosis.

### 9.4. Hikari hay UCP?

| Tiêu chí | HikariCP | Oracle UCP |
| --- | --- | --- |
| Spring Boot default | Có, khi có trên classpath | Có thể cấu hình rõ |
| Mục tiêu | General-purpose JDBC pool | Oracle-specific pool |
| Cấu hình | Đơn giản | Nhiều tính năng Oracle |
| HA integration | Phụ thuộc driver/network/pool | Hỗ trợ tính năng Oracle như FCF/RLB khi môi trường đáp ứng |
| Khi chọn | Hầu hết service CRUD/OLTP | Cần Oracle HA/labeling hoặc tính năng UCP cụ thể |
| Lưu ý | Phải tự sizing/monitor | Phải hiểu UCP timeout/validation/ONS/driver compatibility |

### 9.5. Sizing pool và database service concurrency

Pool max size là số connection tối đa của một process. Nó không đồng nghĩa số SQL statement database có thể chạy đồng thời.

Autonomous Database service name có resource share, concurrency và parallelism riêng. Ví dụ HIGH/MEDIUM có thể queue statement khi đạt concurrency; thêm connection trong Hikari không nhất thiết tăng throughput.

Tính pool theo:

- Số replica tối đa khi autoscaling.
- Số connection mỗi replica.
- Background worker, scheduled jobs và migration.
- Database session limit.
- Service concurrency và workload.
- Số connection dành cho DBA/monitoring.
- Thời gian giữ connection trong transaction.

Công thức kiểm tra sơ bộ:

~~~text
Total application connections
  = max replicas x max pool size per replica
    + background workers
    + migration/admin clients
~~~

Giữ tổng dưới giới hạn database đã xác nhận và theo dõi pool pending/connection timeout. Tránh transaction dài hoặc gọi HTTP trong khi đang giữ JDBC connection.

## 10. Transaction, JPA và migration

### 10.1. Spring transaction

Dùng Spring transaction manager để đảm bảo commit/rollback:

~~~java
@Service
public class DocumentRepositoryService {

    private final JdbcTemplate jdbcTemplate;

    public DocumentRepositoryService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void registerDocument(
            String documentId,
            String objectKey) {

        jdbcTemplate.update(
                "insert into DOC_OWNER.DOCUMENTS (DOCUMENT_ID, OBJECT_KEY) values (?, ?)",
                documentId,
                objectKey);
    }
}
~~~

Dùng bind parameter thay vì nối chuỗi SQL. Không giữ connection thủ công qua nhiều request. Với transaction dài, pool có thể cạn dù số request không quá cao.

### 10.2. Isolation và locking

Oracle Database hỗ trợ transaction semantics riêng. Xác định isolation phù hợp use case; không nâng isolation toàn hệ thống nếu chỉ một số luồng cần locking mạnh.

- Dùng optimistic locking/version column khi cập nhật đồng thời.
- Dùng SELECT FOR UPDATE có phạm vi/thời gian ngắn khi cần serialize.
- Thiết kế idempotency cho request retry.
- Không giữ transaction mở trong lúc gọi dịch vụ cloud khác.
- Dùng outbox/saga nếu cần phối hợp DB với Object Storage hoặc messaging.

### 10.3. Flyway/Liquibase

Schema migration là thao tác database data plane, không phải OCI resource update. Dùng migration user riêng có DDL privilege phù hợp.

Khuyến nghị:

- Migration chạy trong pipeline/release step.
- Runtime user không có quyền CREATE USER/CREATE TABLE nếu không cần.
- Version migration được commit cùng source code.
- Backup/clone trước thay đổi rủi ro cao.
- Test migration trên clone hoặc staging.
- Không chạy DDL tùy tiện khi mỗi application replica khởi động nếu không kiểm soát lock/concurrency.

## 11. Quản lý credential và secret

### 11.1. Database password

Không hard-code database password trong source, Dockerfile, image, Helm chart hoặc log. Lưu trong OCI Vault hoặc secret store phù hợp; inject vào ứng dụng lúc runtime.

Database password rotation cần phối hợp:

1. Tạo secret version mới.
2. Thay password database user bằng quy trình DBA/secret-based credential đã cấu hình.
3. Cập nhật secret version được application sử dụng.
4. Refresh/restart connection pool để tạo connection mới.
5. Xác minh login bằng password mới.
6. Thu hồi password cũ sau overlap/rollover nếu được cấu hình.
7. Theo dõi authentication failures.

Chỉ tạo version mới trong Vault không tự động đổi password của database user. Database user password phải được thay đổi trong database theo cơ chế phù hợp.

### 11.2. Wallet và password database

Wallet client credential và database user password là hai lớp riêng. Khi wallet mTLS rotate, client certificate cũ bị invalidated theo policy; database password không tự đổi. Khi password database user rotate, wallet certificate không tự đổi.

Tạo inventory cho:
- Instance wallet version.
- Database username.
- Secret version/password expiry.
- JDBC service alias.
- Owner/consumer.
- Pool refresh/deploy procedure.
- Revoke/rotation date.

### 11.3. Least privilege database

- Không dùng ADMIN cho ứng dụng.
- Tách schema owner và runtime user.
- Cấp quyền trên object cần dùng, không cấp DBA role.
- Giới hạn quyền migration cho pipeline.
- Tách user read-only cho reporting.
- Xoay password và wallet theo chính sách.
- Thu hồi user/role khi service ngừng hoạt động.

## 12. Observability và vận hành kết nối

### 12.1. Ứng dụng cần theo dõi

Theo dõi pool:

- Active connections.
- Idle connections.
- Pending threads.
- Connection acquisition latency.
- Connection timeout.
- Connection creation/validation failures.
- Usage duration và transaction duration.

Theo dõi database:

- CPU/ECPU utilization.
- Session count.
- SQL latency.
- Wait events.
- Service concurrency/queue.
- Storage utilization.
- Backup/restore lifecycle.
- Network errors.

Không ghi username/password, wallet contents, connect descriptor có thông tin bí mật hoặc SQL bind values nhạy cảm.

### 12.2. Health check

Liveness chỉ nên xác định process có sống hay không; không nên restart toàn bộ pod chỉ vì database tạm thời unavailable.

Readiness có thể thử một truy vấn nhẹ như:

~~~sql
SELECT 1 FROM DUAL
~~~

Health check phải có timeout ngắn, không mở connection mới liên tục nếu pool đã quá tải. Tách readiness dependency khỏi liveness để tránh restart storm.

### 12.3. OCI lifecycle event và application alert

Theo dõi event start/stop/restart/restore/backup/wallet rotation/maintenance. Khi database chuyển Updating hoặc Stopping, ứng dụng có thể nhận connection failure. Dùng alert và runbook để drain traffic hoặc giảm retry.

### 12.4. Connection pool sau maintenance/failover

Sau restart, wallet rotation hoặc network change:

- Xác minh endpoint vẫn đúng.
- Pool loại bỏ connection chết.
- Cấu hình validation/retry phù hợp.
- Không tạo quá nhiều connection cùng lúc (connection storm).
- Tăng traffic dần sau health check.
- Theo dõi session count và connection acquisition latency.

## 13. Troubleshooting lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-12154 | Không resolve được TNS alias | Kiểm tra TNS_ADMIN, tnsnames.ora và alias |
| ORA-12514 | Listener không nhận service name | Dùng đúng service từ OCI Console/tnsnames.ora |
| ORA-01017 | Username/password sai hoặc secret chưa refresh | Xác minh DB user, password và secret version |
| ORA-28000 | Database account bị khóa | DBA kiểm tra account status và chính sách khóa |
| ORA-29024 | Certificate validation thất bại | Kiểm tra wallet/truststore, hostname, certificate chain và thời gian hệ thống |
| Network Adapter / connect timeout | DNS, ACL, NSG, route, port hoặc private endpoint | Kiểm tra network từ đúng pod/VM tới endpoint |
| 403 khi stop/scale/restore | OCI IAM policy thiếu quyền | Kiểm tra control-plane policy và compartment |
| SQL permission denied | Database user thiếu object/system privilege | DBA cấp đúng SQL grant |
| Hikari pool timeout | Pool cạn, query/transaction lâu hoặc database không nhận connection | Kiểm tra active/pending, SQL latency, pool size và session limit |
| ORA-03113/ORA-03135 | Connection bị ngắt hoặc database/network lifecycle | Kiểm tra event, network, pool stale connection và server alert |
| Kết nối được nhưng query chậm | Chọn sai service hoặc query plan/index | Kiểm tra TP/HIGH/MEDIUM/LOW, SQL monitor và execution plan |
| Wallet cũ không kết nối sau rotate | Certificate cũ đã bị invalidated | Tải wallet mới, cập nhật volume và recycle pool |
| JDBC URL TLS bị lỗi hostname | Host/service descriptor không khớp hoặc DN match sai | Dùng nguyên descriptor từ Console; không tắt DN matching |
| Pool tăng connection quá mức | Mỗi pod có pool riêng, autoscaling tăng replica | Tính tổng max pool theo replica và database budget |

### 13.1. Chẩn đoán theo thứ tự

1. **Control plane:** database có Available không, operation lifecycle nào đang chạy?
2. **Network:** DNS, route, ACL/private endpoint, NSG và TCP port.
3. **TLS:** mTLS/TLS mode, wallet, certificate chain, hostname matching.
4. **JDBC:** driver version, URL, TNS alias, TNS_ADMIN và service name.
5. **Authentication:** database username/password hoặc token.
6. **Authorization:** SQL role/grant.
7. **Pool:** max size, timeout, stale connection, pending thread.
8. **SQL:** query plan, lock, wait và service concurrency.

Đừng cấp quyền ADMIN hoặc mở public endpoint chỉ để thử chữa lỗi. Xác định đúng tầng lỗi rồi sửa scope nhỏ nhất.

## 14. Kiểm thử tích hợp

### 14.1. Kiểm tra cấu hình JDBC

- URL có đúng alias/descriptor không?
- Driver có tương thích JDK không?
- TNS_ADMIN có đúng thư mục wallet không?
- Wallet files có đủ và process có quyền đọc không?
- TLS/mTLS mode có khớp database configuration không?
- Service name có đúng workload không?
- Username/password có được inject đúng không?

### 14.2. Smoke test

Sau khi kết nối, kiểm tra database và service:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS DB_NAME,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS SERVICE_NAME,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS SESSION_USER
FROM DUAL
~~~

Xác minh session dùng đúng database, service name và database user. Không in thông tin nhạy cảm vào log production.

### 14.3. Integration test

Dùng Autonomous Database test/staging hoặc clone được quản lý riêng:

1. Khởi tạo DataSource.
2. Lấy connection từ pool.
3. Chạy SELECT 1 FROM DUAL.
4. Insert/update/select/rollback trong transaction.
5. Xác minh runtime user không thể truy cập schema ngoài scope.
6. Xác minh migration user chạy migration được nhưng runtime user không có DDL thừa.
7. Kiểm tra pool close/reconnect.
8. Kiểm tra TLS hoặc mTLS.
9. Kiểm tra database restart/maintenance recovery.
10. Kiểm tra pool sizing dưới concurrency.

### 14.4. Negative tests

- Dùng sai password phải thất bại xác thực.
- Dùng wallet cũ sau immediate rotation phải bị từ chối.
- Dùng user không có SELECT grant phải bị từ chối truy vấn bảng.
- Dùng app network ngoài ACL/private endpoint phải không kết nối được.
- Dùng OCI user không có IAM policy phải không scale/stop database.
- Dùng service name không tồn tại phải thất bại với lỗi rõ.
- Tạo tải vượt pool max phải chờ/timeout có kiểm soát thay vì mở connection vô hạn.

### 14.5. Kiểm thử restore và DR

- Tạo backup theo policy.
- Restore/clone vào môi trường test.
- Xác minh database user, schema, data và connection service.
- Kiểm tra wallet/endpoint/network config theo database mới.
- Kiểm tra KMS key còn truy cập được.
- Xác minh application có thể kết nối bằng DataSource.
- Kiểm tra dữ liệu external table/object storage nếu hệ thống sử dụng.

Không thực hiện restore phá hủy trên production chỉ để kiểm tra runbook.

## 15. Bài tập thực hành tổng hợp

Bạn được giao triển khai document-service trên OCI. Database Autonomous Database nằm trong compartment AppData, ứng dụng chạy trên Compute/OKE trong AppRuntime. Nhóm DBA quản lý schema, nhóm Platform quản lý lifecycle, còn Spring Boot chỉ đọc/ghi các bảng nghiệp vụ.

**Nhiệm vụ:**

1. Provision Autonomous Database trong compartment/region được phê duyệt.
2. Chọn Transaction Processing workload và ECPU phù hợp.
3. Cấu hình private endpoint hoặc ACL theo network architecture.
4. Bật backup/retention và xác định quy trình restore/clone.
5. Tạo OCI IAM policy riêng cho nhóm DBOperators.
6. Tạo database schema owner và runtime user, cấp quyền tối thiểu.
7. Chọn TP service cho luồng OLTP và xác minh alias từ connection details.
8. Tải instance wallet nếu database yêu cầu mTLS; bảo vệ wallet bằng secret volume.
9. Cấu hình JDBC Thin Driver và Spring Boot DataSource.
10. Cấu hình HikariCP và tính tổng connection trên tất cả replica.
11. Viết health check và SQL smoke test.
12. Thiết kế password rotation và wallet rotation độc lập.
13. Kiểm thử 401/403 control plane, lỗi SQL grant, network, TLS và pool exhaustion.
14. Diễn tập stop/start hoặc clone/restore trong môi trường test.
15. Viết runbook cho DBA, Platform và application owner.

**Câu hỏi tự đánh giá:**

- OCI control plane và database data plane khác nhau như thế nào?
- Vì sao OCI IAM policy không tự cấp SELECT trên bảng?
- Vì sao database ADMIN không nên là application user?
- Stop Autonomous Database khác đóng JDBC connection như thế nào?
- ECPU auto scaling có đồng nghĩa Hikari pool tự scale không?
- Backup/restore và clone khác nhau như thế nào?
- Vì sao external files trên Object Storage cần backup riêng?
- Khi nào dùng public endpoint ACL và khi nào dùng private endpoint?
- JDBC Thin wallet-based mTLS khác walletless TLS ra sao?
- Vì sao wallet và database password là hai credential riêng?
- Service TP, TPURGENT, HIGH, MEDIUM và LOW phù hợp workload nào?
- Vì sao tăng maximumPoolSize không nhất thiết tăng throughput?
- HikariCP và UCP khác nhau ở điểm nào?
- Vì sao tổng pool size phải tính theo số replica?
- TNS_ADMIN trỏ tới thư mục nào?
- Wallet rotation khác password rotation như thế nào?
- Vì sao tạo secret version mới trong Vault chưa chắc đã đổi database password?
- Làm thế nào phân biệt ORA-12514 với ORA-01017?
- Vì sao health check database không nên làm liveness restart storm?
- Vì sao cần test negative IAM policy và SQL privilege?

**Đáp án định hướng:** OCI control plane quản lý resource còn JDBC data plane chạy SQL; IAM policy cấp quyền quản lý Autonomous Database, database grants cấp quyền SQL; ADMIN dành cho DBA; stop là lifecycle operation còn close connection chỉ trả/đóng session; compute auto scaling không tự cấu hình pool ứng dụng; restore khôi phục database còn clone tạo database mới; external object files không mặc định nằm trong backup DB; private endpoint giới hạn traffic trong VCN; mTLS cần client wallet còn TLS có thể walletless khi được bật; wallet certificate khác DB password; TP cho OLTP, TPURGENT ưu tiên giao dịch gấp, HIGH/MEDIUM/LOW cho reporting/analytics theo concurrency; connection count khác statement concurrency; Hikari general-purpose còn UCP có Oracle-specific HA features; tổng pool = replica x pool mỗi replica cộng worker/admin; TNS_ADMIN trỏ tới wallet/TNS directory; wallet rotation đổi client certificate còn password rotation đổi DB user; Vault secret update không tự đổi DB password; ORA-12514 thường liên quan service, ORA-01017 liên quan credential; readiness và liveness cần tách; negative tests xác nhận least privilege.

## 16. Tài liệu tham khảo chính thức

### OCI Autonomous Database management

- [Manage the Autonomous AI Database Service](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/manage-service.html): lifecycle, scale, auto scaling, clone và move compartment.
- [IAM Policies for Autonomous AI Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-database-iam-policies.html): quyền inspect/use/manage, stop/start, scale và restore.
- [Use Auto Scaling](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-auto-scale.html): compute và storage auto scaling.
- [Backup and Restore](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/backup-intro.html): automatic backup, immutability và recovery.
- [Backup and Restore Notes](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/backup-restore-notes.html): giới hạn backup external Object Storage files và restore.
- [Network Access Options](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/network-access-options.html): public endpoint, ACL và private endpoint.
- [Configure Private Endpoints](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/private-endpoints-autonomous.html): private endpoint trong VCN.
- [Configure Access Control Lists](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/access-control-rules-autonomous.html): giới hạn kết nối theo IP/VCN.
- [Autonomous AI Database Lifecycle Events](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-database-events.html): start/stop/backup/restore/wallet rotation events.

### JDBC, wallet và service names

- [Connect to Autonomous AI Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-autonomous-database.html): các phương thức kết nối và connection options.
- [JDBC Thin Connections with a Wallet (mTLS)](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/connect-jdbc-thin-wallet.html): wallet, TNS alias và TNS_ADMIN.
- [JDBC Thin Connections Without a Wallet (TLS)](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-jdbc-thin-tls.html): walletless TLS và connection descriptor.
- [Download Database Connection Information](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-download-wallet.html): instance/regional wallet, file contents và bảo vệ wallet.
- [Rotate Wallets](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/wallet-rotate.html): immediate rotation và grace period.
- [Database Service Names](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/predefined-database-services-names.html): TPURGENT, TP, HIGH, MEDIUM, LOW và workload.
- [Service Concurrency](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/manage-service-concurrency.html): concurrency theo ECPU/OCPU và auto scaling.
- [Create and Manage Users](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/manage-users-create.html): database user, role và password management.

### Spring Boot và Oracle JDBC/UCP

- [Spring Boot SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource auto-configuration, HikariCP và UCP.
- [Spring Boot Data Access](https://docs.spring.io/spring-boot/how-to/data-access.html): cấu hình custom DataSource và pool properties.
- [Oracle JDBC Getting Started](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/JDBC-getting-started.html): driver/JDK compatibility.
- [Oracle JDBC Maven Artifacts](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/introducing-JDBC.html): ojdbc, UCP và companion artifacts.
- [Universal Connection Pool Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjucp/universal-connection-pool-developers-guide.pdf): pool sizing, validation và connection management.
- [UCP PoolDataSource API](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjuar/oracle/ucp/jdbc/PoolDataSource.html): max/min pool size, validation timeout và connection wait.

**Ghi nhớ:** OCI IAM quản lý dịch vụ Autonomous Database; database user/role/grant quản lý dữ liệu bên trong; JDBC Thin kết nối ứng dụng qua TLS hoặc mTLS; wallet là client credential cho mTLS và không đồng nghĩa database password. Trong Spring Boot, dùng DataSource/pool được sizing theo tổng replica và service concurrency, bảo vệ wallet/secret, tách user runtime khỏi ADMIN và kiểm thử cả đường kết nối lẫn quyền ở hai mặt phẳng.
