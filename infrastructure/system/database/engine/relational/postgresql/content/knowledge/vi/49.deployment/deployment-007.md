# Phân vùng mạng, tường lửa và quyền truy cập quản trị

PostgreSQL thường lưu dữ liệu quan trọng của ứng dụng, vì vậy đường kết nối đến máy chủ cơ sở dữ liệu cần được giới hạn rõ ràng. Chỉ những thành phần có nhu cầu hợp lệ mới được phép đi đến cổng PostgreSQL; các kết nối quản trị phải đi qua một đường riêng có xác thực mạnh, được ghi nhận và có thể thu hồi.

Bảo vệ PostgreSQL không phụ thuộc vào một cấu hình duy nhất. Phân vùng mạng giới hạn nơi có thể tiếp cận máy chủ; firewall kiểm soát luồng gói tin; cấu hình lắng nghe và pg_hba.conf giới hạn kết nối ở PostgreSQL; TLS bảo vệ dữ liệu trên đường truyền; còn role và privilege xác định người đã kết nối được phép làm gì. Các lớp này bổ trợ nhau và cần được kiểm thử như một hệ thống.

## 1. Mục tiêu và nguyên tắc thiết kế

Một thiết kế triển khai an toàn cần đạt các mục tiêu sau:

- Máy chủ PostgreSQL không có địa chỉ IP công khai nếu ứng dụng không có yêu cầu đặc biệt đã được phê duyệt.
- Chỉ subnet hoặc nhóm máy chủ ứng dụng được phép kết nối đến cổng cơ sở dữ liệu.
- Truy cập quản trị đi qua VPN, bastion host hoặc nền tảng quản trị từ xa có MFA và nhật ký.
- Kết nối giữa ứng dụng, máy chủ quản trị, replica và dịch vụ sao lưu được giới hạn theo đúng nhu cầu.
- Kết nối qua mạng sử dụng TLS và xác minh danh tính máy chủ.
- pg_hba.conf chỉ cho phép nguồn, database, role và phương thức xác thực đã định nghĩa.
- Role ứng dụng không có quyền quản trị hệ điều hành, SUPERUSER hoặc BYPASSRLS.
- Có log, cảnh báo và quy trình thu hồi quyền khi máy chủ, tài khoản hoặc nguồn kết nối thay đổi.

Không nên xem việc đổi cổng mặc định 5432 là biện pháp bảo vệ chính. Kẻ tấn công có thể dò cổng; điều quan trọng là cổng cơ sở dữ liệu chỉ có thể tiếp cận từ các nguồn được phép và PostgreSQL tiếp tục xác thực từng kết nối.

## 2. Phân vùng mạng cho PostgreSQL

Phân vùng mạng chia hạ tầng thành các vùng có mức độ tin cậy và chức năng khác nhau. Máy chủ database nên nằm trong private subnet hoặc vùng dữ liệu riêng. Máy chủ ứng dụng truy cập database qua mạng nội bộ; người quản trị đi qua vùng quản trị; replica và backup dùng các luồng được cấp riêng.

Một mô hình tham khảo:

~~~mermaid
flowchart TB
    U["Người dùng / Internet"] --> W["Load balancer / Web tier"]
    W --> A["Application subnet"]
    A -->|TCP 5432| D["Private database subnet"]
    O["Quản trị viên"] --> V["VPN / Bastion / MFA"]
    V -->|Luồng quản trị được cấp| D
    D -->|Replication| R["Replica subnet"]
    D -->|Backup có kiểm soát| B["Backup storage"]
    M["Monitoring subnet"] -->|Metrics / Logs| D
~~~

Các vùng trong sơ đồ có thể được triển khai bằng VPC/VNet subnet, VLAN, security group, firewall zone hoặc network policy của Kubernetes. Không nhất thiết phải tạo một subnet cho mọi chức năng, nhưng cần xác định rõ nguồn và đích của từng luồng.

### 2.1. Application subnet

Chứa các service backend có nhu cầu truy cập database. Firewall chỉ cho phép các workload thuộc nhóm ứng dụng đã xác định kết nối tới địa chỉ riêng của PostgreSQL trên TCP 5432.

Không nên mở cổng database cho toàn bộ mạng nội bộ chỉ vì các máy chủ cùng nằm trong một VPC. Một máy build, máy phát triển, máy chạy thử hoặc workload bị xâm nhập có thể trở thành điểm di chuyển ngang nếu mọi nguồn trong mạng đều được phép truy cập.

### 2.2. Database subnet

Chứa primary và các replica nếu kiến trúc dùng replication. Vùng này không nhận kết nối trực tiếp từ Internet. Chỉ mở những luồng cần thiết:

- Ứng dụng tới PostgreSQL: cổng TCP của PostgreSQL, thường là 5432.
- Bastion hoặc hệ thống quản trị tới PostgreSQL: chỉ từ nguồn quản trị đã xác minh.
- Primary tới replica hoặc replica tới primary: luồng replication theo topology thực tế.
- Monitoring tới exporter hoặc endpoint metrics: chỉ từ máy giám sát.
- Database tới backup endpoint: chỉ các giao thức và đích lưu trữ cần thiết.

Nếu dùng nhiều instance PostgreSQL, hãy cấp quyền mạng riêng cho từng nhóm. Không mở cả dải cổng hoặc toàn bộ subnet chỉ để tránh phải cập nhật firewall khi thêm replica.

### 2.3. Management subnet

Chứa bastion host, VPN gateway hoặc hệ thống quản trị từ xa. Người quản trị xác thực vào lớp này trước, sau đó mới truy cập máy chủ database theo quyền được cấp.

Bastion không nên trở thành máy chủ dùng chung cho mọi mục đích. Hạn chế phần mềm cài đặt, tài khoản đăng nhập, quyền sudo, truy cập Internet và khả năng chuyển tiếp sang các mạng khác. Theo dõi phiên quản trị và xóa quyền khi nhân sự không còn phụ trách hệ thống.

### 2.4. Replication và backup subnet

Replication và backup là các luồng dịch vụ riêng. Chỉ cho phép địa chỉ của primary, replica hoặc backup worker tương ứng kết nối theo đúng chiều và giao thức.

Physical streaming replication thường dùng kết nối PostgreSQL với database đặc biệt replication và role có thuộc tính REPLICATION. Logical replication kết nối vào database cụ thể và dùng quyền phù hợp với publication/subscription. Không nên cấp quyền REPLICATION hoặc quyền đọc toàn bộ dữ liệu cho role ứng dụng chỉ để tái sử dụng tài khoản.

Backup worker cần quyền đọc hoặc gọi công cụ backup đúng thiết kế. Hạn chế quyền xóa và quyền quản trị trên kho backup; bản sao lưu phải được bảo vệ khỏi việc bị xóa cùng lúc với máy chủ database.

## 3. Xác định luồng mạng trước khi mở firewall

Trước khi viết rule, lập danh sách luồng kết nối. Mỗi luồng nên ghi nhận:

| Nguồn | Đích | Giao thức/cổng | Mục đích | Quyền sở hữu |
|---|---|---|---|---|
| Application subnet | PostgreSQL primary | TCP 5432 | Truy vấn nghiệp vụ | Nhóm ứng dụng |
| Bastion / admin subnet | PostgreSQL | TCP 5432 | Quản trị database | DBA |
| Primary | Replica | TCP 5432 | Physical/logical replication theo cấu hình | DBA |
| Monitoring host | Metrics exporter | Cổng exporter được cấu hình | Thu thập chỉ số | SRE |
| Backup worker | PostgreSQL | TCP 5432 hoặc kênh backup được chọn | Sao lưu | DBA / Backup |
| PostgreSQL host | DNS, NTP, logging, backup endpoint | Theo dịch vụ được duyệt | Hạ tầng phụ trợ | Platform |

Bảng này là cơ sở để tạo security group, network ACL, host firewall và policy của nền tảng điều phối. Cần phân biệt rõ:

- **Inbound:** kết nối đi vào máy chủ database.
- **Outbound:** kết nối từ database tới DNS, NTP, logging, backup hoặc hệ thống khác.
- **East-west:** kết nối giữa các máy trong cùng môi trường nội bộ.
- **Administrative:** kết nối do con người hoặc công cụ quản trị khởi tạo.

Đừng mặc định mọi luồng outbound đều an toàn. Một máy chủ database bị xâm nhập có thể dùng quyền outbound rộng để truyền dữ liệu ra ngoài hoặc liên lạc với hạ tầng điều khiển. Chỉ cho phép các đích outbound cần thiết, đồng thời duy trì DNS, NTP, logging và backup để hệ thống vẫn vận hành đúng.

## 4. Firewall ở các lớp hạ tầng

Firewall có thể được triển khai ở nhiều vị trí. Mỗi lớp xử lý một phần của đường kết nối.

### 4.1. Firewall mạng và security group

Trong môi trường cloud, security group thường là firewall stateful gắn với network interface hoặc tài nguyên. Có thể chỉ định nguồn bằng security group của application server thay vì một dải IP rộng. Network ACL ở cấp subnet thường stateless, do đó cần xem xét cả chiều đi và chiều về, bao gồm ephemeral ports.

Ví dụ chính sách logic:

| Tài nguyên đích | Nguồn được phép | Cổng đích | Chính sách |
|---|---|---:|---|
| PostgreSQL primary | Application security group | TCP 5432 | Allow |
| PostgreSQL primary | Admin/bastion security group | TCP 5432 | Allow |
| PostgreSQL primary | Replica security group | TCP 5432 | Allow theo topology |
| PostgreSQL primary | Internet / mọi nguồn khác | TCP 5432 | Deny |
| PostgreSQL primary | Toàn bộ mạng nội bộ không liên quan | TCP 5432 | Deny |

Tên nhóm và cách tham chiếu phụ thuộc nhà cung cấp cloud. Cần kiểm tra rule thực tế gắn vào network interface, route table và subnet; một security group đúng nhưng route hoặc firewall khác vẫn có thể làm đường truy cập mở ngoài dự kiến.

### 4.2. Host firewall

Host firewall là lớp kiểm soát ngay trên hệ điều hành chạy PostgreSQL. Nó hữu ích để giới hạn nguồn ngay cả khi rule mạng bên ngoài bị cấu hình nhầm.

Ví dụ với UFW trên Linux, giả sử máy database chỉ nhận kết nối ứng dụng từ 10.20.10.0/24 và quản trị từ 10.20.30.0/24:

~~~bash
sudo ufw default deny incoming
sudo ufw default allow outgoing

sudo ufw allow from 10.20.10.0/24 to any port 5432 proto tcp
sudo ufw allow from 10.20.30.0/24 to any port 5432 proto tcp

sudo ufw status numbered
~~~

Các địa chỉ trong ví dụ là mạng minh họa; phải thay bằng CIDR thực tế đã được xác minh. Trước khi bật firewall trên máy chủ từ xa, bảo đảm đã có rule cho kênh quản trị hệ điều hành hiện tại, ví dụ SSH từ bastion. Nếu khóa nhầm đường quản trị, DBA có thể mất quyền khôi phục cấu hình.

Không nên chạy nhiều công cụ cùng lúc để quản lý cùng một bộ rule nếu chưa hiểu thứ tự và cách chúng tương tác. Chọn một nguồn cấu hình chuẩn, quản lý bằng IaC hoặc hệ thống cấu hình, ghi lại thay đổi và kiểm tra trạng thái sau khi áp dụng.

### 4.3. Firewall trong Kubernetes

Nếu PostgreSQL chạy ngoài Kubernetes, NetworkPolicy có thể giới hạn pod nào được phép kết nối tới database. Nếu PostgreSQL chạy trong cluster, policy cần kiểm soát cả traffic tới pod database và các luồng quản trị/replication.

Ví dụ NetworkPolicy cho phép pod có label app: orders-api trong namespace production kết nối tới pod database trên TCP 5432:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-orders-to-postgres
  namespace: database
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: production
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 5432
~~~

Policy này chỉ có hiệu lực nếu CNI plugin của cluster hỗ trợ NetworkPolicy. Cần xác minh label namespace và pod đúng với thực tế; label sai có thể khiến luồng hợp lệ bị chặn hoặc policy không khớp workload mong muốn. NetworkPolicy cũng không thay thế pg_hba.conf hay quyền database.

## 5. Giới hạn địa chỉ mà PostgreSQL lắng nghe

Firewall quyết định gói tin nào có thể đến máy chủ; PostgreSQL còn quyết định tiến trình database có lắng nghe trên interface nào.

Xem cấu hình hiện hành:

~~~sql
SHOW listen_addresses;
SHOW port;
SHOW config_file;
SHOW hba_file;
~~~

listen_addresses mặc định thường là localhost. Trong môi trường production, có thể cấu hình địa chỉ private interface cụ thể:

~~~conf
listen_addresses = '127.0.0.1,10.20.0.15'
port = 5432
~~~

Địa chỉ 10.20.0.15 ở đây là IP private minh họa của database server. Chỉ khai báo địa chỉ thực sự được gắn trên máy chủ. Nếu cần lắng nghe trên nhiều interface, hãy xác định rõ lý do và bảo đảm firewall giới hạn từng đường truy cập.

Giá trị '*' khiến PostgreSQL lắng nghe trên tất cả interface khả dụng. Chỉ dùng khi kiến trúc cần điều đó và các lớp firewall, routing, pg_hba.conf đã được giới hạn chặt chẽ. Việc lắng nghe trên mọi interface không tự động làm cổng database truy cập được từ Internet, nhưng làm tăng phạm vi ảnh hưởng nếu firewall hoặc route bị cấu hình sai.

Thay đổi listen_addresses hoặc port cần restart PostgreSQL để có hiệu lực. Sau khi restart, xác minh tiến trình đang lắng nghe đúng địa chỉ và cổng, đồng thời thử kết nối từ một nguồn được phép và một nguồn không được phép.

## 6. Dùng pg_hba.conf để giới hạn kết nối

pg_hba.conf (host-based authentication) là lớp kiểm soát kết nối ở PostgreSQL. Mỗi dòng quy định loại kết nối, database, role, địa chỉ client và phương thức xác thực.

Cấu trúc tổng quát:

~~~conf
# TYPE  DATABASE  USER  ADDRESS  METHOD  [OPTIONS]
~~~

Các loại dòng thường gặp:

- local: kết nối qua Unix-domain socket trên máy chủ.
- host: kết nối TCP, có thể dùng SSL hoặc không.
- hostssl: chỉ kết nối TCP có TLS.
- hostnossl: chỉ kết nối TCP không dùng TLS.

Ví dụ chỉ cho phép ứng dụng và DBA kết nối bằng TLS từ hai subnet riêng:

~~~conf
# Ứng dụng: chỉ database appdb và role app_runtime
hostssl  appdb  app_runtime  10.20.10.0/24  scram-sha-256

# Quản trị: chỉ database cần quản lý và role db_admin
hostssl  all    db_admin    10.20.30.0/24  scram-sha-256

# Physical replication: chỉ replica có địa chỉ được xác định
hostssl  replication  repl_user  10.20.40.10/32  scram-sha-256
~~~

Ví dụ trên giả định đã tạo role tương ứng, cấp quyền database và cấu hình TLS. Với logical replication, trường DATABASE trong pg_hba.conf thường là tên database cụ thể thay vì từ khóa đặc biệt replication dành cho kết nối physical replication.

### 6.1. Thứ tự rule rất quan trọng

PostgreSQL xét các dòng từ trên xuống và dùng dòng đầu tiên khớp loại kết nối, địa chỉ, database và user. Nếu xác thực trên dòng khớp đó thất bại, PostgreSQL không tiếp tục thử dòng sau. Vì vậy, rule rộng đặt phía trên có thể làm mất tác dụng của rule cụ thể bên dưới.

Không thêm các rule như sau vào production:

~~~conf
# Không an toàn: cho phép mọi địa chỉ truy cập database
host  all  all  0.0.0.0/0  trust
~~~

trust bỏ qua xác thực mật khẩu cho kết nối khớp rule. Dải 0.0.0.0/0 bao phủ mọi IPv4; IPv6 có dải tương ứng ::/0. Không dùng trust cho kết nối TCP từ mạng không đáng tin cậy. Nếu có cấu hình host rộng, nó có thể cho phép cả kết nối không TLS; ưu tiên hostssl cho các đường mạng cần mã hóa.

### 6.2. Phương thức xác thực

SCRAM-SHA-256 là phương thức xác thực mật khẩu nên dùng cho triển khai PostgreSQL hiện đại. Nó an toàn hơn cơ chế mật khẩu cũ md5. Cần kiểm tra phiên bản server và client trước khi chuyển đổi; client cũ có thể không hỗ trợ SCRAM.

Có thể đặt cách mã hóa mật khẩu mới:

~~~conf
password_encryption = 'scram-sha-256'
~~~

Thay đổi cấu hình này ảnh hưởng cách lưu mật khẩu khi đặt hoặc đổi mật khẩu. Để chuyển role hiện có sang SCRAM, cần đặt lại mật khẩu cho các role liên quan sau khi đã xác minh client tương thích.

Có thể kiểm tra cấu hình HBA đã đọc được hay chưa bằng view pg_hba_file_rules:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

Tìm dòng lỗi:

~~~sql
SELECT line_number, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
~~~

Sau khi sửa file, yêu cầu PostgreSQL nạp lại cấu hình:

~~~sql
SELECT pg_reload_conf();
~~~

pg_reload_conf() trả về true cho biết yêu cầu reload đã được gửi thành công; vẫn cần đọc log máy chủ và kiểm tra lại cấu hình. Sửa pg_hba.conf thường chỉ cần reload, không cần restart toàn bộ PostgreSQL. Nếu file có lỗi cú pháp, log và view kiểm tra sẽ giúp xác định dòng cần sửa.

## 7. Mã hóa và xác minh kết nối bằng TLS

TLS bảo vệ dữ liệu truyền giữa client và server, bao gồm thông tin đăng nhập và dữ liệu truy vấn. Chỉ bật SSL ở server chưa đủ; client cần xác minh chứng chỉ server để tránh kết nối nhầm máy chủ.

Cấu hình server tham khảo:

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

Đường dẫn chứng chỉ phụ thuộc cấu trúc cài đặt. Private key phải được bảo vệ bằng quyền truy cập hệ điều hành phù hợp; trên Linux, thông thường chỉ tài khoản dịch vụ PostgreSQL được đọc key. Không đưa private key vào source control hoặc image công khai.

Client libpq nên dùng sslmode=verify-full và CA tin cậy:

~~~bash
psql "host=db.internal.example port=5432 dbname=appdb user=app_runtime sslmode=verify-full sslrootcert=/etc/ssl/certs/company-db-ca.crt"
~~~

Với verify-full, client kiểm tra chuỗi chứng chỉ và tên máy chủ khớp với hostname kết nối. Chứng chỉ server cần có Subject Alternative Name phù hợp. Nếu dùng IP thay hostname, chứng chỉ phải có IP SAN tương ứng; nên dùng DNS nội bộ ổn định cho primary, replica và endpoint failover.

Các chế độ require, verify-ca và verify-full có mức kiểm tra khác nhau. require mã hóa kết nối nhưng không xác minh đầy đủ danh tính server; verify-ca xác minh CA nhưng không kiểm tra hostname; verify-full kiểm tra cả chuỗi chứng chỉ và hostname. Với kết nối production, ưu tiên verify-full.

Nếu sử dụng chứng chỉ client, cần thiết kế vòng đời cấp phát, phân phối, gia hạn và thu hồi chứng chỉ. Chứng chỉ client không thay thế role database: PostgreSQL vẫn cần ánh xạ danh tính kết nối sang role và cấp privilege phù hợp.

## 8. Thiết kế quyền truy cập quản trị

Quyền truy cập mạng chỉ xác định ai có thể tiếp cận cổng PostgreSQL. Sau khi kết nối thành công, PostgreSQL tiếp tục kiểm tra role và quyền trên database. Hai lớp này phải được thiết kế độc lập.

### 8.1. Tách tài khoản ứng dụng và quản trị

Không dùng một tài khoản postgres hoặc SUPERUSER cho ứng dụng, migration, backup và người quản trị. Mỗi mục đích cần một role riêng:

| Role | Mục đích | Quyền nên có |
|---|---|---|
| app_runtime | Backend xử lý nghiệp vụ | Chỉ quyền đọc/ghi cần thiết trên schema và bảng |
| db_migrator | Triển khai thay đổi schema | Quyền DDL cần thiết trong thời gian migration |
| db_monitor | Thu thập chỉ số | Quyền giám sát tối thiểu, không đọc dữ liệu nghiệp vụ nếu không cần |
| repl_user | Replication | LOGIN và REPLICATION theo yêu cầu |
| db_admin | Công việc DBA thông thường | Quyền quản trị được phân công, có audit |
| Break-glass role | Khôi phục khẩn cấp | SUPERUSER chỉ khi thật sự cần, lưu giữ và sử dụng theo quy trình riêng |

Các role nhóm có thể được tạo dưới dạng NOLOGIN rồi cấp membership cho các login role được phê duyệt. Tài khoản cá nhân nên có danh tính riêng để log truy vết được người thực hiện thao tác. Tránh chia sẻ một mật khẩu DBA cho cả nhóm.

### 8.2. Đường truy cập của DBA

Một luồng quản trị thường có dạng:

1. Quản trị viên xác thực vào VPN hoặc hệ thống truy cập từ xa có MFA.
2. Hệ thống xác minh thiết bị, danh tính và quyền truy cập.
3. Quản trị viên mở phiên tới bastion hoặc công cụ quản trị được phê duyệt.
4. Firewall chỉ cho phép bastion kết nối đến PostgreSQL trên cổng cần thiết.
5. PostgreSQL xác thực role DBA qua pg_hba.conf và phương thức xác thực mạnh.
6. Thao tác quản trị được ghi log, gắn với người thực hiện và ticket/change tương ứng khi cần.

Không nên mở cổng 5432 ra Internet để DBA có thể dùng laptop từ bất cứ đâu. Nếu phải hỗ trợ vận hành từ xa, dùng VPN, bastion hoặc giải pháp zero-trust có danh tính, MFA và nhật ký phiên.

### 8.3. Quản lý đặc quyền cao

SUPERUSER có thể bỏ qua phần lớn kiểm soát trong PostgreSQL, bao gồm RLS. Vì vậy:

- Không cấp SUPERUSER cho tài khoản ứng dụng, migration thông thường hoặc monitoring.
- Chỉ dùng tài khoản đặc quyền cao cho thao tác thực sự cần thiết.
- Lưu thông tin xác thực trong secret manager hoặc hệ thống quản lý mật khẩu được kiểm soát.
- Ưu tiên cấp quyền tạm thời và thu hồi sau khi hoàn thành công việc.
- Bảo vệ tài khoản break-glass bằng MFA, kiểm soát truy cập và quy trình ghi nhận.
- Kiểm tra định kỳ membership, thuộc tính SUPERUSER, CREATEROLE, CREATEDB, REPLICATION và BYPASSRLS.

Kiểm tra thuộc tính role:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls
FROM pg_roles
ORDER BY rolname;
~~~

Danh sách role và membership là một phần của cấu hình bảo mật. Khi nhân sự rời nhóm hoặc workload bị thay thế, cần thu hồi membership, credential, certificate và rule mạng liên quan.

## 9. Kiểm soát kết nối quản trị qua bastion hoặc tunnel

Bastion là điểm trung gian cho phép người quản trị truy cập mạng riêng. Nó không làm cho database tự an toàn; cần bảo vệ cả bastion, kênh xác thực và đường chuyển tiếp.

Một số nguyên tắc:

- Bastion chỉ nhận kết nối quản trị từ VPN hoặc danh tính/thiết bị được cho phép.
- Không lưu mật khẩu database trong script hoặc file cấu hình không được bảo vệ trên bastion.
- Dùng SSH key hoặc cơ chế xác thực được quản lý; tắt tài khoản mặc định và mật khẩu yếu.
- Giới hạn người được phép tạo tunnel và các đích mà tunnel có thể đi tới.
- Ghi log phiên, thời điểm, danh tính và đích truy cập.
- Cập nhật hệ điều hành, giới hạn package và loại bỏ dịch vụ không cần thiết.

SSH local port forwarding có thể dùng để tạo tunnel tạm thời:

~~~bash
ssh -N -L 15432:db.internal.example:5432 admin@bastion.internal.example
~~~

Sau khi tunnel hoạt động, client kết nối vào cổng local 15432, lưu ý phải giữ xác minh hostname chứng chỉ TLS. Với libpq, có thể dùng host là hostname có trong chứng chỉ và hostaddr là địa chỉ loopback của tunnel, đồng thời đặt port local tương ứng. Cấu hình cụ thể cần được kiểm tra với DNS và thư viện client đang dùng; không tắt verify-full chỉ để tunnel hoạt động.

Với nền tảng cloud, dịch vụ session manager có thể thay bastion SSH truyền thống. Dù dùng phương án nào, nguyên tắc vẫn là cấp quyền theo danh tính, giới hạn đích truy cập, MFA, thời hạn và audit.

## 10. Kiểm thử đường truy cập hợp lệ và bị từ chối

Không nên chỉ kiểm tra từ máy chủ database. Cần thử từ các vùng mạng khác nhau để xác nhận firewall và PostgreSQL cùng hoạt động đúng.

### 10.1. Kiểm tra từ client được phép

Từ application subnet, kiểm tra DNS và TCP:

~~~bash
getent hosts db.internal.example
nc -vz db.internal.example 5432
~~~

Sau đó kết nối bằng TLS và truy vấn ngữ cảnh:

~~~bash
psql "host=db.internal.example port=5432 dbname=appdb user=app_runtime sslmode=verify-full sslrootcert=/path/company-ca.crt"
~~~

Trong phiên SQL:

~~~sql
SELECT
    current_database(),
    session_user,
    current_user,
    inet_server_addr(),
    inet_server_port(),
    inet_client_addr();
~~~

Thông tin này giúp xác nhận database, role, địa chỉ server và client mà PostgreSQL đang thấy. Nếu ứng dụng đi qua NAT hoặc proxy, inet_client_addr() có thể là địa chỉ của lớp trung gian; cần đối chiếu với log và topology thực tế.

### 10.2. Kiểm tra từ nguồn không được phép

Từ một máy trong subnet không được cấp quyền, thử kiểm tra TCP 5432. Kết nối nên bị chặn ở lớp firewall hoặc không có route tới vùng database. Không cần gửi mật khẩu hoặc thử đăng nhập nhiều lần.

Khi firewall cho phép gói tin đến PostgreSQL nhưng pg_hba.conf không có rule phù hợp, client thường nhận thông báo dạng no pg_hba.conf entry. Đây là dấu hiệu kết nối đã tới PostgreSQL nhưng bị từ chối ở lớp HBA. Nếu firewall chặn trước, thường sẽ gặp timeout hoặc lỗi kết nối mạng tùy thiết bị.

Phân biệt hai kết quả này giúp xác định lớp cần kiểm tra. Một test âm tính nên ghi nhận nguồn thử, đích, thời điểm, lớp từ chối và log liên quan.

### 10.3. Kiểm tra riêng đường quản trị

Xác nhận rằng:

- Người không có quyền VPN/bastion không thể tới subnet quản trị.
- Người có quyền vào bastion nhưng không có quyền DBA không thể đăng nhập role quản trị.
- DBA có thể kết nối từ nguồn được cấp và bị từ chối khi dùng nguồn khác.
- Role DBA không được dùng thay cho role ứng dụng trong cấu hình backend.
- Khi thu hồi quyền VPN, SSH, membership hoặc chứng chỉ, đường truy cập tương ứng không còn hoạt động.

### 10.4. Kiểm tra sau failover

Nếu dùng primary/replica hoặc dịch vụ HA, kiểm thử cả endpoint sau failover. Firewall và pg_hba.conf phải cho phép client đến đúng node hoặc endpoint mới. Không mở toàn bộ subnet để tránh phải cập nhật rule khi chuyển primary; thay vào đó, quản lý danh tính nhóm database hoặc cập nhật rule tự động theo cơ chế failover.

Cũng cần xác minh chứng chỉ TLS của endpoint, DNS, route, role và quyền replication sau khi chuyển đổi. Một endpoint kết nối được nhưng dùng chứng chỉ không khớp hostname vẫn phải bị client verify-full từ chối.

## 11. Theo dõi và audit truy cập

Cấu hình mạng có thể thay đổi theo thời gian. Cần ghi nhận kết nối thành công, kết nối thất bại, thay đổi cấu hình và thao tác đặc quyền.

Một số cấu hình log cơ bản:

~~~conf
log_connections = on
log_disconnections = on
log_line_prefix = '%m [%p] user=%u db=%d client=%h '
~~~

Các tùy chọn và cách ghi log chi tiết có thể khác theo phiên bản PostgreSQL và hệ thống log. Cần kiểm tra log thực tế sau khi thay đổi cấu hình. Tránh ghi toàn bộ câu SQL hoặc dữ liệu nhạy cảm một cách không cần thiết; log phải có chính sách lưu trữ, phân quyền đọc và thời hạn xóa.

Có thể xem kết nối hiện tại:

~~~sql
SELECT
    pid,
    usename,
    datname,
    client_addr,
    application_name,
    state,
    backend_start
FROM pg_stat_activity
ORDER BY backend_start DESC;
~~~

Theo dõi tối thiểu các tín hiệu:

- Kết nối từ địa chỉ client ngoài danh sách cho phép.
- Lỗi xác thực tăng đột biến hoặc lặp lại.
- Role có đặc quyền cao được sử dụng ngoài khung thời gian dự kiến.
- Thay đổi pg_hba.conf, listen_addresses, firewall hoặc security group.
- Chứng chỉ TLS sắp hết hạn hoặc không còn được tin cậy.
- Replication bị gián đoạn và backup không hoàn thành.
- Kết nối từ subnet phát triển hoặc máy cá nhân vào database production.

Có thể dùng PostgreSQL logging, hệ thống audit như pgAudit khi yêu cầu kiểm toán cần chi tiết hơn, cùng log từ firewall, cloud control plane, bastion và hệ điều hành. Đồng bộ thời gian bằng NTP để các sự kiện từ nhiều hệ thống có thể đối chiếu được.

## 12. Quy trình triển khai thay đổi mạng và quyền

Thay đổi firewall hoặc pg_hba.conf có thể làm gián đoạn ứng dụng hoặc khóa đường quản trị. Nên triển khai theo từng bước có thể xác minh và rollback.

1. **Lập inventory:** ghi nhận primary, replica, app subnet, admin subnet, backup, monitoring, DNS và các endpoint phụ thuộc.
2. **Đối chiếu luồng:** xác nhận nguồn, đích, cổng, giao thức, owner và lý do tồn tại.
3. **Thiết kế rule:** tạo rule cụ thể theo nguồn và đích; chuẩn bị cả chiều phản hồi nếu dùng firewall stateless.
4. **Chuẩn bị đường khôi phục:** xác nhận console hoặc kênh quản trị độc lập vẫn dùng được; lưu bản cấu hình hiện tại.
5. **Cập nhật firewall:** thêm rule allow cần thiết trước, kiểm tra luồng hợp lệ, sau đó loại bỏ rule rộng đã hết nhu cầu.
6. **Cập nhật PostgreSQL:** giới hạn listen_addresses, TLS và pg_hba.conf; kiểm tra cú pháp và reload/restart theo loại thay đổi.
7. **Kiểm tra kết nối:** thử từ nguồn được phép và nguồn bị từ chối; xác minh TLS, role và database.
8. **Theo dõi:** xem log ứng dụng, PostgreSQL, firewall và bastion trong thời gian sau triển khai.
9. **Hoàn tất thay đổi:** lưu cấu hình chuẩn, người phê duyệt, kết quả kiểm tra và phương án rollback.

Thay đổi listen_addresses cần restart PostgreSQL, vì vậy nên lên lịch và chuẩn bị phương án HA nếu hệ thống yêu cầu sẵn sàng cao. Thay đổi pg_hba.conf thường chỉ cần reload. Thay đổi firewall có thể áp dụng tức thời; nên có rule rollback hoặc phiên console đang mở để tránh tự khóa đường quản trị.

Không nên xóa rule cũ ngay khi chưa xác minh mọi ứng dụng, job, migration, backup và monitoring đã chuyển sang luồng mới. Các kết nối ít thường xuyên có thể chỉ xuất hiện vào thời điểm backup hoặc bảo trì.

## 13. Các lỗi triển khai thường gặp

- **Đưa PostgreSQL ra public subnet:** làm tăng bề mặt tấn công và phụ thuộc quá nhiều vào cấu hình firewall.
- **Mở TCP 5432 cho 0.0.0.0/0 hoặc ::/0:** cho phép mọi nguồn thử tiếp cận database.
- **Chỉ dựa vào firewall:** nếu rule mạng bị mở rộng, PostgreSQL vẫn cần HBA, TLS và quyền role để bảo vệ dữ liệu.
- **Chỉ dựa vào pg_hba.conf:** tiến trình vẫn có thể lắng nghe trên interface ngoài dự kiến; HBA không thay thế firewall.
- **Dùng trust hoặc mật khẩu yếu:** làm giảm khả năng xác minh danh tính.
- **Dùng sslmode=require như thể đã xác minh server:** kết nối được mã hóa nhưng danh tính server chưa được kiểm tra đầy đủ như verify-full.
- **Dùng chung tài khoản DBA:** khó truy vết và khó thu hồi quyền theo cá nhân.
- **Cấp SUPERUSER cho ứng dụng:** khiến ứng dụng vượt qua nhiều lớp kiểm soát database, bao gồm RLS.
- **Quên IPv6:** firewall IPv4 chặt không đảm bảo IPv6 cũng bị giới hạn.
- **Quên replication và backup:** ứng dụng hoạt động nhưng replica hoặc backup worker bị chặn sau khi siết rule.
- **Quên connection pool hoặc failover:** endpoint mới không có rule, DNS hoặc chứng chỉ tương thích.
- **Không theo dõi thay đổi:** rule tạm thời có thể tồn tại lâu dài và trở thành đường truy cập ngoài kiểm soát.

## 14. Checklist vận hành

Trước khi đưa PostgreSQL vào production hoặc thay đổi đường truy cập, hãy xác nhận:

- [ ] Database nằm trong vùng mạng riêng và không có public IP ngoài thiết kế.
- [ ] Chỉ nguồn ứng dụng, quản trị, replication, backup và monitoring đã xác định được phép truy cập.
- [ ] Security group, network ACL và host firewall đã được kiểm tra theo cả chiều đi và về.
- [ ] IPv4 và IPv6 đều có chính sách rõ ràng.
- [ ] listen_addresses chỉ bao gồm interface cần thiết.
- [ ] pg_hba.conf không có rule rộng hoặc trust ngoài phạm vi an toàn.
- [ ] Kết nối production dùng TLS và client xác minh hostname bằng sslmode=verify-full.
- [ ] Ứng dụng, migration, replication, monitoring và DBA dùng role riêng.
- [ ] Không cấp SUPERUSER hoặc BYPASSRLS cho role ứng dụng.
- [ ] Đường quản trị có MFA, thời hạn quyền, audit và quy trình break-glass.
- [ ] Kết nối hợp lệ thành công và kết nối từ nguồn không được phép bị từ chối.
- [ ] Log PostgreSQL, firewall và bastion được lưu trữ, giám sát và bảo vệ.
- [ ] Có phương án rollback và kênh khôi phục khi thay đổi làm mất kết nối.

Phân vùng mạng, firewall và quyền quản trị cần được xem như một hợp đồng giữa các nhóm ứng dụng, DBA và platform. Mỗi kết nối phải có nguồn, đích, mục đích và người chịu trách nhiệm. Khi một luồng không còn cần thiết, hãy thu hồi rule mạng, credential và quyền database tương ứng. Cách làm này giúp PostgreSQL chỉ phục vụ đúng workload được phê duyệt, đồng thời giữ cho hoạt động quản trị có thể truy vết và kiểm soát.

