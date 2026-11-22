# Cloud SQL cho PostgreSQL, MySQL và SQL Server

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Cloud SQL** là dịch vụ cơ sở dữ liệu quan hệ được quản lý, phân biệt instance, database, user, HA standby, read replica và bản backup.
2. So sánh **Cloud SQL for PostgreSQL**, **MySQL** và **SQL Server** về hệ sinh thái, version, authentication, licensing, khả năng mở rộng và các giới hạn quản trị.
3. Chọn **Enterprise/Enterprise Plus**, region, machine size, storage, availability và phương án kết nối **public IP/private IP/Cloud SQL connectors**.
4. Tạo và cấu hình instance bằng **gcloud**, kết nối an toàn từ Java/Spring Boot trên Cloud Run, GKE hoặc máy lập trình.
5. Tách quyền **Google Cloud IAM**, **database users/roles** và **service identity**; áp dụng Secret Manager, IAM database authentication khi được hỗ trợ.
6. Thiết kế backup, **point-in-time recovery (PITR)**, high availability, read replicas, migration, giám sát, rollback và kiểm soát chi phí; thực hiện các bài tập có đáp án.

## 1. Cloud SQL giải quyết việc gì?

**Cloud SQL** là dịch vụ quản lý máy chủ cơ sở dữ liệu quan hệ trên Google Cloud. Thay vì tự vận hành PostgreSQL, MySQL hoặc Microsoft SQL Server trên Compute Engine, bạn giao cho Google Cloud các công việc cơ sở hạ tầng như provisioning, bản vá, sao lưu, giám sát khả năng sẵn sàng và một phần replication. **Ứng dụng vẫn chịu trách nhiệm** về schema, chỉ mục, truy vấn, users, dữ liệu, kết nối, chi phí và quy trình phục hồi.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, đây là mắt xích nối tổ chức project/IAM/VPC với Java chạy trên **Compute Engine, GKE, Cloud Run**, cũng như chiến lược bảo mật, tự động phát hành, theo dõi độ tin cậy và ngân sách.

### Ví dụ xuyên suốt

Công ty bán lẻ triển khai:

- **orders-api** (Spring Boot/Java) trên Cloud Run, cần giao dịch đơn hàng.
- **payment-adapter** trên GKE, cần đọc trạng thái thanh toán.
- **reporting-job** tổng hợp dữ liệu vào cuối ngày.
- Database production đặt tại **asia-southeast1**, dữ liệu backup được giữ theo chính sách phục hồi.

~~~mermaid
flowchart LR
    U["Người dùng"] --> LB["Cloud Run orders-api<br/>Java + HikariCP"]
    LB --> CONN["Cloud SQL Java Connector<br/>hoặc Auth Proxy"]
    CONN --> DB["Cloud SQL primary<br/>orders-db"]
    DB --> HA["HA standby<br/>khác zone, cùng region"]
    DB -. "replication bất đồng bộ" .-> RR["Read replica<br/>reporting"]
    DB --> BK["Backups + transaction logs<br/>PITR"]
    GKE["GKE payment worker"] --> CONN
    IAM["IAM + Secret Manager"] -. "Quản lý danh tính/credentials" .-> CONN
~~~

**Giới hạn của sơ đồ:** HA standby không phải read replica cho reporting; backup/PITR không phải bản sao đang phục vụ truy vấn; và **replication không thay thế backup**.

## 2. Phân cấp tài nguyên và các khái niệm

~~~text
Google Cloud project: shop-dev-001
└── Cloud SQL instance: orders-pg
    ├── Engine: PostgreSQL 18
    ├── Region: asia-southeast1
    ├── Databases: ordersdb, app_test
    ├── Users/roles: app_user, readonly_user
    ├── HA standby (nếu chọn regional availability)
    ├── Read replica (tài nguyên instance riêng, nếu tạo)
    └── Backups / transaction logs (nếu cấu hình)
~~~

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Instance** | Server DB managed với engine/version, vCPU/RAM/storage/network | orders-pg |
| **Database** | Cơ sở dữ liệu logic nằm trong instance | ordersdb |
| **Database user/role** | Danh tính và quyền SQL, khác Cloud IAM | app_user chỉ được CRUD một schema |
| **Instance connection name** | Định danh dùng cho Cloud SQL Auth Proxy/Language Connectors | shop-dev-001:asia-southeast1:orders-pg |
| **Primary** | Instance xử lý writes và phần lớn giao dịch | orders-pg |
| **HA standby** | Bản standby quản lý nội bộ ở zone khác, phục vụ failover | Không để ứng dụng truy vấn trực tiếp |
| **Read replica** | Instance nhận dữ liệu bất đồng bộ từ primary để scale reads | orders-pg-replica |
| **Backup / PITR** | Khôi phục dữ liệu theo thời điểm/cửa sổ | Phục hồi trước thao tác DELETE nhầm |

**Cloud SQL không phải database server tự quản trị**: bạn không có root trên VM chạy engine và không tùy ý cài mọi extension, plugin hoặc tính năng OS. Hãy kiểm tra **engine-specific feature compatibility** trước khi di chuyển ứng dụng cũ.

## 3. Chọn PostgreSQL, MySQL hay SQL Server?

| Tiêu chí | PostgreSQL | MySQL | Microsoft SQL Server |
|---|---|---|---|
| Hệ sinh thái | SQL chuẩn, extension được Cloud SQL hỗ trợ, kiểu JSON/JSONB, GIS với PostGIS | Ứng dụng web/LAMP và nhiều ORM, MySQL ecosystem | Ứng dụng .NET/Windows/SQL Server, T-SQL, hệ sinh thái Microsoft |
| Cú pháp đặc thù | PL/pgSQL, JSONB, PostgreSQL functions | MySQL dialect, InnoDB, collations | T-SQL, stored procedures, SQL Server data types |
| JDBC driver phổ biến | **org.postgresql:postgresql** | **com.mysql:mysql-connector-j** | **com.microsoft.sqlserver:mssql-jdbc** |
| Cổng TCP mặc định | **5432** | **3306** | **1433** |
| Database authentication | Built-in user/password; **IAM database authentication** | Built-in user/password; **IAM database authentication** | SQL logins/password, Active Directory/Entra ID theo cấu hình; **không hỗ trợ IAM database authentication** |
| Licensing | Cấu phần PostgreSQL mã nguồn mở trong giá dịch vụ | Cấu phần MySQL trong giá dịch vụ | Có chi phí giấy phép SQL Server theo edition |
| Lưu ý | Extensions/superuser bị giới hạn | Flags, charset/collation, binary logs cần xem | SQL Server Agent/AD/linked server/features có giới hạn dịch vụ |

**Không chọn chỉ vì tên engine:** hãy dựa trên khả năng tương thích với schema/query hiện có, đội ngũ, yêu cầu HA/DR, hiệu năng thực nghiệm, licensing và chi phí vận hành.

### 3.1. Database versions không phải mặc định bất biến

Theo tài liệu cập nhật năm 2026, Cloud SQL hỗ trợ các bản hiện đại như:

- **PostgreSQL 18**; còn nhiều major versions cũ được hỗ trợ theo lịch **regular/extended support**.
- **MySQL 8.4** và các bản được liệt kê trong bảng version hỗ trợ; các bản cũ có thể phát sinh **extended support charges**.
- **SQL Server 2022/2025** với các editions đủ điều kiện; một số versions 2017/2019 có vòng đời hỗ trợ riêng của Microsoft.

Không dựa vào phiên bản mặc định của console/gcloud; **chỉ định database-version rõ ràng** và kiểm tra **support/EOL**, khả năng đổi major version và tương thích JDBC trước khi tạo. Một phiên bản trong danh sách “supported” có thể đang ở **extended support với phí bổ sung**, không có nghĩa nên chọn cho dự án mới.

## 4. Edition, cấu hình máy và availability

Cloud SQL cung cấp hai dòng edition cho cả ba engines:

| Edition | Đặc điểm | Khi chọn |
|---|---|---|
| **Enterprise** | Khả năng managed DB cốt lõi, machine series và mức HA/observability cơ bản | Ứng dụng nhỏ–vừa, dev/staging, ngân sách/tiêu chí latency vừa phải |
| **Enterprise Plus** | Các lựa chọn hiệu năng, data protection, availability/maintenance/observability nâng cao | Workload production cần SLA/latency/throughput và các tính năng nâng cao được hỗ trợ |

**Giá, machine series và tính năng khác nhau theo engine, database version và region.** SQL Server Enterprise Plus không dành cho mọi SQL Server edition: tài liệu hiện hành liệt kê các tổ hợp **SQL Server Enterprise 2019/2022/2025** đủ điều kiện. PostgreSQL 16+ và MySQL 8.4+ có những quy tắc **default edition** khác các phiên bản cũ khi tạo qua gcloud/API. Vì vậy luôn khai báo **--edition** để không bất ngờ về chi phí.

### 4.1. Cần quyết định gì trước khi tạo instance?

1. **Engine/version/edition**: ảnh hưởng tương thích SQL, extensions, chi phí và lifecycle.
2. **Region**: đặt gần ứng dụng và data dependencies; đánh giá residency và egress.
3. **CPU/RAM/storage**: chọn theo workload đo được; Cloud SQL không tự co CPU/RAM theo mỗi HTTP request như Cloud Run.
4. **Availability**: **Zonal** hay **Regional HA**; production quan trọng nên cân nhắc HA.
5. **Connection path**: private IP, public IP + connector, hoặc Private Service Connect theo topology.
6. **Data protection**: backup option, retention, PITR, encryption/CMEK, failover runbook.
7. **Network/IAM**: ai quản lý instance, ai kết nối, ai được SQL GRANT.
8. **Maintenance**: maintenance window, lịch nâng cấp, retry/reconnect của ứng dụng.

### 4.2. HA không phải DR

**Regional HA** giữ primary và standby trong **hai zones của cùng region**. Dữ liệu được sao chép đồng bộ cho HA; khi zone/instance lỗi, Cloud SQL có thể **fail over** sang standby bằng endpoint/IP theo cơ chế được quản lý. Trong tài liệu PostgreSQL, failover thường gây gián đoạn **khoảng một phút** nhưng có thể khác theo cấu hình và sự cố. **Connections đang mở phải reconnect/retry**.

**Zonal/standalone** ít tài nguyên hơn nhưng không tự động phục hồi từ cả một zone outage như HA. **HA không khắc phục** DELETE nhầm, ứng dụng ghi dữ liệu sai, lỗi logic kéo dài hoặc mất toàn region. Những rủi ro này cần **PITR, backups và cross-region DR** được kiểm thử.

### 4.3. Read replicas không thay thế standby

Read replica nhận thay đổi **bất đồng bộ**, phục vụ SELECT/analytics/reporting để giảm tải primary; **replication lag** khiến nó có thể đọc dữ liệu chưa cập nhật. Truy vấn cần **read-after-write consistency** (kiểm tra thanh toán vừa ghi) nên đọc từ primary hoặc có cơ chế bảo đảm nhất quán.

Read replica có **connection endpoint, instance cost và monitoring riêng**. Với SQL Server, Cloud SQL hiện cũng có read replicas, nhưng giới hạn/điều kiện theo edition và version cần được kiểm tra. Failover sang replica hoặc cross-region DR là **quy trình khác HA standby tự động**.

## 5. Thực hành A — Tạo instance PostgreSQL cho lab

Đặt giả định:

| Thuộc tính | Giá trị ví dụ |
|---|---|
| Project | **shop-dev-001** |
| Region | **asia-southeast1** |
| Instance | **orders-pg** |
| Engine | **PostgreSQL 16**, Enterprise |
| Database | **ordersdb** |
| App runtime | **orders-api** service account |

**Đây là ví dụ thao tác**, không phải lệnh đã chạy. Tạo Cloud SQL instance sẽ phát sinh phí vCPU/RAM, storage và backup. Chỉ chạy trong project lab được phép; trước khi tạo production cần review sizing, IAM và network.

### 5.1. Preflight

~~~bash
gcloud config get-value project
gcloud auth list
gcloud sql instances list --project=shop-dev-001

# Chỉ chạy nếu có quyền bật API cho project lab.
gcloud services enable sqladmin.googleapis.com \
  --project=shop-dev-001
~~~

### 5.2. Tạo instance zonal để học (không thay thế mẫu production HA)

~~~bash
gcloud sql instances create orders-pg \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --cpu=2 \
  --memory=7680MB \
  --storage-size=20GB \
  --availability-type=ZONAL \
  --backup-start-time=02:00
~~~

**Chọn rõ edition**: phiên bản PostgreSQL 16 có thể mặc định Enterprise Plus nếu không chỉ định edition. Kích thước 2 vCPU/7.5 GiB và 20 GB chỉ để lab, không phải cấu hình khuyên dùng cho mọi ứng dụng.

Lệnh tạo trên là **mô hình mạng public IP mặc định nếu không chỉ định private IP**, tùy cấu hình hiện hành/organization policy. **Đừng mở authorized networks 0.0.0.0/0** để thử kết nối. Với production, nên thiết kế private connectivity ngay từ đầu.

### 5.3. Tạo database và kiểm tra thông tin

~~~bash
gcloud sql databases create ordersdb \
  --instance=orders-pg \
  --project=shop-dev-001

gcloud sql instances describe orders-pg \
  --project=shop-dev-001 \
  --format="yaml(name,connectionName,databaseVersion,region,settings,ipAddresses)"

gcloud sql databases list \
  --instance=orders-pg \
  --project=shop-dev-001
~~~

**Instance** không đồng nghĩa **database**: một instance có thể chứa nhiều databases. Lệnh **databases create** không tự cấp SQL permissions cho Java runtime.

### 5.4. Khi chọn HA production

Mô hình tham khảo (không chạy tiếp lên lab nếu không cần):

~~~bash
gcloud sql instances patch orders-pg \
  --project=shop-dev-001 \
  --availability-type=REGIONAL

gcloud sql instances describe orders-pg \
  --project=shop-dev-001 \
  --format="yaml(settings.availabilityType,gceZone,secondaryGceZone)"
~~~

**Thay đổi availability** có thể gây restart/failover hoặc thời gian provision đáng kể và làm tăng chi phí. Production cần chọn **REGIONAL từ khi tạo** nếu có nhu cầu cao, review backup/PITR và test reconnect.

## 6. MySQL và SQL Server: thao tác tương tự nhưng không đồng nhất

### 6.1. Tạo MySQL Enterprise instance

~~~bash
gcloud sql instances create orders-mysql \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --database-version=MYSQL_8_0 \
  --edition=ENTERPRISE \
  --cpu=2 \
  --memory=7680MB \
  --storage-size=20GB \
  --backup-start-time=02:00
~~~

**MySQL 8.0** là ví dụ để minh họa cú pháp ổn định; với ứng dụng mới nên đánh giá **MySQL 8.4** và các version hiện được hỗ trợ, đồng thời xem edition/region/machine series tương ứng. MySQL có nhu cầu cấu hình **binary logging** đối với một số replication/PITR workflows; kiểm tra tùy chọn đúng theo version và backup settings.

### 6.2. Tạo SQL Server: khác ở edition và SQL credentials

Một mẫu gcloud **có placeholder, không chạy nguyên văn**:

~~~bash
gcloud sql instances create orders-sqlserver \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --database-version=SQLSERVER_2022_STANDARD \
  --edition=ENTERPRISE \
  --cpu=2 \
  --memory=7680MB \
  --root-password=REPLACE_WITH_TEST_PASSWORD
~~~

SQL Server dùng **login sa/password hoặc các phương án AD/Entra ID được hỗ trợ**, không dùng IAM database authentication. Lệnh **--root-password** trên command line có nguy cơ lộ ở shell history/process list/CI logs. Với dữ liệu thật, **đặt password qua kênh quản trị an toàn được phê duyệt** (ví dụ console hoặc workflow secrets chuyên dụng), không hardcode trong script hoặc đẩy vào Git.

**SQL Server editions** (Standard/Enterprise/Express/Web) và **Cloud SQL editions** (Enterprise/Enterprise Plus) là **hai phân loại khác nhau**. Ví dụ SQLSERVER_2022_STANDARD có thể là **Cloud SQL Enterprise edition**, không phải SQL Server Enterprise license. Chi phí SQL Server bao gồm các thành phần license riêng.

### 6.3. Khác nhau trong SQL dialect

~~~sql
-- PostgreSQL
CREATE TABLE orders (
  order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  amount NUMERIC(12, 2) NOT NULL
);

-- MySQL
CREATE TABLE orders (
  order_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  amount DECIMAL(12, 2) NOT NULL
);

-- SQL Server
CREATE TABLE orders (
  order_id BIGINT IDENTITY(1,1) PRIMARY KEY,
  amount DECIMAL(12, 2) NOT NULL
);
~~~

Ba đoạn là **các lựa chọn thay thế**, không được chạy tuần tự vào cùng một database. Khi migrate, cần review **data types, sequences/identity, transaction isolation, collation, timestamp/time zone, JSON, stored procedures và indexes**, chứ không chỉ đổi JDBC URL.

## 7. Kết nối Cloud SQL: public IP, private IP hay connector?

**Có đường mạng** và **có quyền truy cập database** là hai điều kiện khác nhau. Chọn đường đi trước, sau đó thiết lập IAM, TLS và SQL credentials.

| Kiểu kết nối | Dùng khi | Điều kiện và rủi ro |
|---|---|---|
| **Private IP + direct TCP** | Cloud Run/GKE/VM có VPC connectivity đến Cloud SQL | Private services access hoặc kiến trúc private IP phù hợp; kiểm soát VPC/firewall/TLS |
| **Public IP + direct TCP** | Client cố định IP, có lý do mở public endpoint | Authorized networks + TLS/certificate; không mở 0.0.0.0/0 |
| **Cloud SQL Auth Proxy** | Developer, GKE sidecar hoặc các workloads cần connector | ADC/IAM + Cloud SQL Admin API, phiên bản Proxy phù hợp; không cần public authorized networks |
| **Cloud SQL Java/Python/Go connector** | Ứng dụng quản lý kết nối trong ngôn ngữ | Cài thư viện, ADC, kiểm soát pool, lựa chọn IP |
| **Private Service Connect (PSC)** | Kiến trúc service networking nhiều VPC/project theo điều kiện | DNS, service attachment/endpoint, quota và giới hạn cụ thể |

**Khuyến nghị:** với workloads trong Google Cloud, ưu tiên **private IP** trừ khi có ràng buộc khác; dùng **Cloud SQL connectors** khi cần xác thực/tạo TLS tự động. Một **connector không tự tạo tuyến VPC tới private IP**: nếu chọn private IP, Cloud Run/GKE/VM vẫn phải có network path hợp lệ.

### 7.1. Quy tắc cho public IP

- Khi **kết nối trực tiếp qua public IP**, cấu hình **authorized networks** với CIDR hẹp và TLS.
- Khi dùng **Cloud SQL Auth Proxy/Language Connector qua public IP**, không cần khai báo client IP trong authorized networks vì connector xác thực theo cơ chế Cloud SQL.
- Không dùng **gcloud sql instances patch --authorized-networks=...** trên production khi chưa đọc list hiện có: lệnh có thể **thay thế toàn bộ danh sách** và chặn các clients khác.
- Đường public không có nghĩa DB authentication được bỏ qua; account SQL vẫn phải đăng nhập đúng.

### 7.2. Quy tắc cho private IP

Với mô hình private IP dùng **Private Services Access**, tạo allocated IP range và service networking connection trên VPC trước khi gán private IP cho instance. Chọn CIDR/organization policy đủ capacity cho các dịch vụ; đây là cấu hình mạng có thể ảnh hưởng tài nguyên khác nên cần platform team review.

Với **Cloud Run**, dùng **Direct VPC egress** hoặc **Serverless VPC Access connector** đến VPC nhìn thấy private IP Cloud SQL. Với **GKE**, cluster/network và routing phải đi đến database; không coi việc hai tài nguyên ở cùng project là bằng chứng có network connectivity.

**Cổng mặc định:** PostgreSQL **5432**, MySQL **3306**, SQL Server **1433**. Client Java dùng đúng driver, cổng và SQL dialect. Với Cloud SQL Auth Proxy, ứng dụng kết nối **localhost/Unix socket** theo cổng do Proxy lắng nghe, không nhất thiết cùng port DB engine.

### 7.3. Instance connection name

~~~bash
gcloud sql instances describe orders-pg \
  --project=shop-dev-001 \
  --format="value(connectionName)"

# Ví dụ kết quả:
# shop-dev-001:asia-southeast1:orders-pg
~~~

**Connection name** dùng cho Cloud SQL connectors, không phải host DNS/database name. Không nhầm với **ordersdb** hay địa chỉ IP của instance.

## 8. Thực hành B — Cloud SQL Auth Proxy và Java

### 8.1. Tài khoản và quyền IAM

Cloud SQL Auth Proxy/Java connector sử dụng **Google Cloud credentials** để xác nhận principal được phép kết nối instance; thông thường cần:

- **roles/cloudsql.client**, hoặc custom role có **cloudsql.instances.connect**, được cấp ở đúng phạm vi.
- **Cloud SQL Admin API** đã bật tại project chứa instance (và các dự án liên quan khi kết nối cross-project).
- **ADC** hợp lệ: service account Cloud Run/GKE/Compute Engine hoặc user đã đăng nhập ADC trong môi trường lab.
- **Database user/password** riêng, trừ khi cấu hình **IAM database authentication** trên engine hỗ trợ.

**Quan trọng:** **roles/cloudsql.client không cấp SELECT/INSERT** trên schema SQL. Nó cho phép đi qua lớp Cloud SQL connector. Ứng dụng vẫn cần một database login và quyền **GRANT** tương ứng.

### 8.2. Chạy Proxy trên máy phát triển được kiểm soát

Sau khi cài **Cloud SQL Auth Proxy v2** theo hướng dẫn Google Cloud, chạy:

~~~bash
# Lệnh này sử dụng ADC hiện có; KHÔNG cần tải JSON key.
cloud-sql-proxy \
  --port=5432 \
  shop-dev-001:asia-southeast1:orders-pg
~~~

Mở terminal khác để kết nối:

~~~bash
# Chỉ ví dụ cho PostgreSQL; nhập mật khẩu theo prompt an toàn.
psql -h 127.0.0.1 -p 5432 -U app_user -d ordersdb
~~~

Proxy mặc định lắng nghe **127.0.0.1**. **Không bind 0.0.0.0** để chia sẻ Proxy cho người khác; một người có quyền vào socket có thể dùng đường kết nối do Proxy mở. Nếu instance chỉ có **private IP** hoặc muốn chọn đường private, Proxy cần **--private-ip** và máy chạy Proxy phải có VPC route hợp lệ (VPN/VM/VPC).

**Đây là thực hành cục bộ:** không chạy cloud-sql-proxy trên cùng cổng với PostgreSQL server khác đang lắng nghe; dùng cổng local khác nếu xung đột.

### 8.3. Java JDBC không nhúng mật khẩu

Ví dụ Java 21 với **PostgreSQL JDBC driver**. Mã nguồn kết nối Proxy trên localhost; **DB_USER/DB_PASSWORD** phải được cấu hình qua secrets injection được phê duyệt:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class CloudSqlCheck {
    private CloudSqlCheck() {}

    public static void main(String[] args) throws SQLException {
        String url = "jdbc:postgresql://127.0.0.1:5432/ordersdb";
        String username = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        if (username == null || password == null) {
            throw new IllegalStateException("Missing DB credentials");
        }

        try (Connection conn = DriverManager.getConnection(url, username, password);
             PreparedStatement stmt = conn.prepareStatement("SELECT 1");
             ResultSet rs = stmt.executeQuery()) {
            if (rs.next()) {
                System.out.println("Database connection OK"); // Không in secret.
            }
        }
    }
}
~~~

**Đối với ứng dụng thực tế**, không tạo kết nối mới cho từng HTTP request; dùng **HikariCP**, cấu hình **max pool size**, connection timeout, idle timeout, retry/jitter. JDBC PostgreSQL driver chỉ là ví dụ cho engine này. Khi chuyển sang MySQL/SQL Server phải thay **JDBC driver, URL, cổng, SQL syntax, DB authentication**.

~~~text
PostgreSQL : jdbc:postgresql://127.0.0.1:5432/ordersdb
MySQL      : jdbc:mysql://127.0.0.1:3306/ordersdb
SQL Server : jdbc:sqlserver://127.0.0.1:1433;databaseName=ordersdb;encrypt=true
~~~

Đối với SQL Server, xác thực TLS với driver và Proxy phải được kiểm tra cùng nhau; **encrypt=true** một mình không chứng minh endpoint được xác thực chính xác nếu cấu hình trust server certificate bỏ kiểm tra chứng chỉ. Dùng cấu hình driver/connector được Google hỗ trợ, không bật **trustServerCertificate=true** như một cách sửa lỗi nhanh.

### 8.4. Gắn Cloud SQL vào Cloud Run

Nếu **orders-api** đã được triển khai trên Cloud Run và dùng đường kết nối tích hợp:

~~~bash
gcloud run services update orders-api \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --add-cloudsql-instances=shop-dev-001:asia-southeast1:orders-pg
~~~

Cấu hình Cloud Run tạo **revision mới**; service identity cần **Cloud SQL Client**, và app vẫn phải dùng **database login/credentials**. Với lựa chọn **private IP/direct TCP**, Cloud Run cần cấu hình VPC egress riêng; không mặc định **--add-cloudsql-instances** giải quyết mọi bài toán private networking.

### 8.5. GKE và kết nối qua sidecar

Trên GKE, mô hình phổ biến là **Pod Java + Cloud SQL Auth Proxy sidecar**, với quyền **Cloud SQL Client** cấp cho KSA qua **Workload Identity Federation for GKE**. Hai containers trong cùng Pod dùng chung namespace mạng, nên Java có thể kết nối tới **127.0.0.1** trên cổng Proxy. Dùng image Proxy được pin version/digest, hạn chế CPU/memory, health checks và secret exposure.

**Không đặt JSON service account key trong Pod** trừ khi có yêu cầu ngoại lệ được phê duyệt. WIF + IAM giúp cấp credential ngắn hạn để Proxy gọi Cloud SQL APIs, không thay database username/password hoặc IAM database login.

## 9. Phân quyền: Google IAM không đồng nghĩa SQL GRANT

### 9.1. Hai cửa phải qua

~~~mermaid
flowchart LR
    APP["Java app / service account"] --> NET{"VPC/Public IP/Proxy"}
    NET --> IAM{"Cloud SQL IAM<br/>nếu qua connector"}
    IAM --> LOGIN{"Database login<br/>password hoặc IAM DB auth"}
    LOGIN --> GRANT{"SQL privileges<br/>GRANT/roles"}
    GRANT --> QUERY["SELECT/INSERT/UPDATE"]
~~~

| Quyền | Tác dụng | Không thay thế |
|---|---|---|
| **roles/cloudsql.client** | Cho Cloud SQL connector/Proxy kết nối | DB login và SQL GRANT |
| **roles/cloudsql.instanceUser** | Quyền **cloudsql.instances.login** cho IAM database authentication | Cloud SQL Client nếu dùng connector, SQL GRANT |
| **Cloud SQL Admin** | Quản trị instances/operations theo IAM | DBA toàn quyền bên trong mọi database |
| **Database user / SQL roles** | Đọc/ghi schema, tables, stored procedures | Project IAM để quản lý instance |

**PostgreSQL và MySQL** hỗ trợ đăng nhập database bằng **IAM database authentication** khi cấu hình instance và tạo IAM DB user/group đúng quy trình. **SQL Server không hỗ trợ IAM database authentication**: dùng SQL logins/password, Active Directory hoặc Microsoft Entra ID theo tính năng hiện có. Không gọi tất cả ba engine “đều đăng nhập bằng IAM”.

### 9.2. Với PostgreSQL và MySQL: IAM database authentication

Để đăng nhập bằng IAM theo mô hình tự động:

1. Bật **IAM database authentication** cho Cloud SQL instance (thao tác thay đổi DB flags, có thể cần restart).
2. Thêm IAM user/service account hoặc nhóm đúng dạng được Cloud SQL hỗ trợ.
3. Cấp **roles/cloudsql.instanceUser** cho IAM principal; nếu dùng Proxy/Language Connector, cấp thêm **roles/cloudsql.client**.
4. Dùng **Cloud SQL Auth Proxy/Java Connector** với chế độ **automatic IAM database authentication**.
5. Trong database vẫn cần **GRANT SELECT/INSERT/EXECUTE** theo nghiệp vụ; IAM login không tự cho quyền CRUD.

**Access token có thời hạn ngắn**, vì thế tự động refresh qua connector phù hợp hơn tự quản lý token trong connection pool. Khi runtime chạy ở Cloud Run, principal ADC phải trùng danh tính được cấu hình cho IAM DB auth và SQL user tương ứng.

### 9.3. Với SQL Server: SQL login và Directory

Cloud SQL for SQL Server có các cách xác thực database như **built-in SQL authentication**, **managed/customer-managed Active Directory** và **Microsoft Entra ID** theo điều kiện. **IAM chỉ kiểm soát instance/backup operations, không login SQL query**. Với app Java:

- Dùng **Microsoft JDBC driver** tương thích server version.
- Cấp SQL login tối thiểu, lưu password ở **Secret Manager** nếu dùng SQL auth.
- Quản lý rotation và connection pool; không ghi sa password trong app.yaml, Dockerfile, GitHub Actions logs.
- Không dùng login **sa** để chạy ứng dụng hằng ngày; tạo user/roles chỉ được thao tác trên database cần thiết.

### 9.4. Least privilege trong database

Ví dụ PostgreSQL sau khi đã đăng nhập bằng **DBA được ủy quyền**:

~~~sql
-- Chỉ minh họa, user app_user đã được tạo bằng quy trình bảo mật.
GRANT CONNECT ON DATABASE ordersdb TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE ON TABLE public.orders TO app_user;
-- Nếu dùng identity/sequence hoặc objects khác, phải kiểm tra GRANT tương ứng.
~~~

Không dùng **GRANT ALL PRIVILEGES ON DATABASE** như mặc định cho runtime. MySQL dùng **GRANT SELECT, INSERT, UPDATE ON ordersdb.orders ...**; SQL Server dùng **GRANT ... ON OBJECT::dbo.orders TO app_user**. Cú pháp và mô hình schema/roles giữa ba engines **khác nhau**.

## 10. Bảo mật mạng, dữ liệu và bí mật

### 10.1. Checklist security

| Lớp | Biện pháp |
|---|---|
| **Resource IAM** | Tách deployer, DB operator, runtime SA; role nhỏ nhất |
| **Network** | Private IP/PSC khi phù hợp; public authorized networks rất hẹp; VPC firewall/TLS |
| **DB authentication** | IAM DB auth khi engine hỗ trợ, SQL users tối thiểu, AD/Entra khi phù hợp |
| **Secrets** | Secret Manager, không log password; rotate với kế hoạch hỗ trợ 2 credentials nếu có |
| **At-rest encryption** | Google-managed encryption mặc định; cân nhắc **CMEK** theo yêu cầu compliance |
| **Backup** | Encryption, retention, vị trí lưu, kiểm thử restore; không giả định bản sao trong cùng region là DR |
| **Audit** | Cloud Audit Logs cho control-plane, database audit/logs engine theo nhu cầu |
| **App** | Prepared statements, query timeouts, connection pool, migration review và chống SQL injection |

### 10.2. CMEK không phải SQL permission

Cloud SQL mã hóa data at rest mặc định. Nếu chọn **customer-managed encryption key (CMEK)**, phải tạo Cloud KMS key tại location được hỗ trợ và cấp quyền cần thiết cho **Cloud SQL service agent** tương ứng; thiết kế rotation/availability của key trước khi tạo instance. **Không cấp KMS CryptoKey Decrypter cho mọi SQL application user** — dịch vụ Cloud SQL thực hiện việc mã hóa lưu trữ.

Nếu khóa bị disable hoặc quyền service agent bị thu hồi, instance/backup/restart có thể bị ảnh hưởng. Không thử disable key production để kiểm tra; dùng project lab với runbook và kiểm tra hậu quả tới DR.

### 10.3. Mã hóa đường truyền

- **Cloud SQL Auth Proxy/Connectors** tạo kênh bảo mật tới Cloud SQL và xác thực theo principal, giảm việc quản lý server/client certificates trực tiếp.
- Với **direct TCP**, cấu hình **SSL/TLS** đúng yêu cầu và xác minh chứng chỉ server; private IP **không tự đồng nghĩa encrypted traffic**.
- Đường từ Java tới Proxy local TCP trên cùng máy/Pod là trusted boundary; **không expose cổng Proxy ra public interface**.

## 11. Quản lý connection pools khi Cloud Run/GKE scale

**Cloud SQL instances có giới hạn connections và resources**. Cloud Run có thể tăng hàng chục instances khi traffic cao; nếu mỗi instance mở pool quá lớn, DB bị quá tải dù CPU app vẫn khỏe.

Giả sử **40 Cloud Run instances**, mỗi instance pool tối đa **10 connections**:

\[
\text{Số kết nối tối đa từ ứng dụng} \approx 40 \times 10 = 400.
\]

Đây là cận trên theo cấu hình (chưa tính migrations, reporting, DBA, background jobs). Với DB có max connections thấp hơn, errors như **too many connections**, latency tăng hoặc timeout có thể xuất hiện sau scale-out.

### 11.1. Thiết kế pool

1. Tính **concurrent requests × tỷ lệ requests thực sự cần DB**, không đặt pool size bằng số requests nếu nhiều requests không cần DB.
2. Giới hạn **HikariCP maximumPoolSize**, có connectionTimeout và maxLifetime thấp hơn lifetime kết nối bị hạ tầng đóng; test dưới peak thực.
3. Giới hạn Cloud Run **max instances/concurrency** phù hợp năng lực DB; ở GKE, kiểm tra HPA replica cap.
4. Dùng **retry cho lỗi transient/failover** với exponential backoff/jitter; hạn chế retry trong cùng transaction nếu có nguy cơ tạo đơn hàng trùng.
5. Cân nhắc **read replica** cho báo cáo dài, cache ứng dụng và query optimization trước khi tăng vCPU.
6. Đo **active/idle connections**, queue wait, SQL latency và error rate từ cả app lẫn Cloud SQL.

### 11.2. Idempotency sau failover

Khi DB ngắt giữa lúc ghi giao dịch và lúc client nhận response, ứng dụng có thể **không biết transaction đã commit chưa**. Không retry lệnh **CREATE ORDER** một cách mù quáng; dùng **idempotency key** hoặc unique business constraint để tránh đơn hàng bị nhân đôi.

**HA giúp hệ thống phục hồi nhanh hơn, không làm JDBC connections bất tử**. Java/Spring Boot vẫn cần reconnect, timeout và health checks.

## 12. Backups, PITR và khôi phục sau sự cố

### 12.1. Ba thứ khác nhau: HA, backup và PITR

| Cơ chế | Bảo vệ khỏi | Không bảo vệ khỏi |
|---|---|---|
| **Regional HA** | Hỏng một zone/instance, giúp failover nhanh | DELETE nhầm, ransomware/logic xấu, mất cả region |
| **Read replica** | Tải đọc lớn và một số tình huống DR có thể promote | Không bảo đảm không mất dữ liệu; không thay backup |
| **Automated/on-demand backup** | Mất dữ liệu hoặc cần khôi phục trạng thái trước đó | Không phải endpoint phục vụ traffic; cần thời gian restore |
| **PITR** | Khôi phục gần thời điểm trước một giao dịch lỗi | Chỉ hoạt động trong **cửa sổ log được giữ**, phải bật từ trước |
| **Cross-region backup/replica** | Hỗ trợ DR ngoài region | Không tự chuyển DNS/app/database credentials và traffic |

### 12.2. Standard backups và Enhanced backups

Cloud SQL hiện có hai **backup options**:

- **Standard backups:** cấu hình trực tiếp trên instance, do Cloud SQL lưu và quản lý cùng project. Lịch tự động thường **hằng ngày**; retention của automated backups tùy cấu hình và edition. On-demand backups có quy tắc retention riêng.
- **Enhanced backups:** tích hợp **Backup and DR Service**, dùng **backup vault/backup plans**, có thể quản lý tập trung ở project khác, lịch **hourly/daily/weekly/monthly/yearly**, retention dài hơn và cơ chế bảo vệ như retention lock.

Hai options **không cùng hoạt động đồng thời trên một instance**. Theo tài liệu, Standard automated backups có thể giữ tối đa khoảng **1 năm**, Enhanced có thể lên tới **10 năm**, nhưng giới hạn và tính năng cụ thể phụ thuộc engine, edition, backup plan và lựa chọn giữ backup sau khi xóa instance.

**Cảnh báo:** backup storage location có thể khác region của DB. Thay nơi lưu backup **không tự di chuyển backups cũ**. Cần kiểm tra data residency, Cloud KMS key location, phí lưu trữ và băng thông trước khi chọn.

### 12.3. Thực hành C — Tạo backup và xem danh sách

~~~bash
# Tạo một on-demand backup trên lab instance; phát sinh chi phí lưu trữ.
gcloud sql backups create \
  --instance=orders-pg \
  --project=shop-dev-001 \
  --description="Pre-migration lab backup"

gcloud sql backups list \
  --instance=orders-pg \
  --project=shop-dev-001

gcloud sql instances describe orders-pg \
  --project=shop-dev-001 \
  --format="yaml(settings.backupConfiguration)"
~~~

Để **backup thực sự phục hồi được**, cần kiểm thử **restore vào một instance tách biệt**, chạy SQL integrity checks, xác nhận ứng dụng có thể đọc và ghi. Một dòng **SUCCESS** ở công đoạn backup không đủ chứng minh RTO/RPO đã đáp ứng.

### 12.4. Point-in-time recovery

**PITR** kết hợp backup với **transaction logs**: PostgreSQL sử dụng WAL, MySQL sử dụng binary logs và SQL Server sử dụng log backups theo khả năng/edition. PITR yêu cầu các cấu hình hỗ trợ được bật, transaction logs trong cửa sổ retention và timestamp hợp lệ.

**PITR tạo ra một instance mới**, không phải thao tác UNDO ngay trên primary. Ví dụ lệnh cho **standard backup** sau khi đã xác nhận PITR được bật:

~~~bash
# THAY timestamp bằng thời điểm UTC thật, NẰM TRONG PITR window.
# Không chạy nguyên văn placeholder.
gcloud sql instances clone orders-pg orders-pg-restore-test \
  --project=shop-dev-001 \
  --point-in-time="YYYY-MM-DDTHH:MM:SSZ"
~~~

Nếu instance dùng **Enhanced backups**, quy trình restore từ **backup vault/data source** có thể dùng lệnh **gcloud sql instances point-in-time-restore** và tham số khác. **Đừng sao chép lệnh standard clone sang vault rồi giả định thành công**. Hãy xác nhận backup option hiện có trước khi chọn workflow.

**Bài thực hành phục hồi an toàn:**

1. Tạo dữ liệu test và ghi một mốc thời gian UTC.
2. Chụp backup on-demand, đảm bảo PITR đã hoạt động.
3. Giả lập một thao tác DELETE nhầm trên **database lab**, sau đó chọn mốc phục hồi trước DELETE.
4. Khôi phục ra **instance mới**, kiểm tra row counts, constraints và khả năng ứng dụng kết nối.
5. Đo **RTO** (thời gian phục hồi) và **RPO** (mức dữ liệu có thể mất), so với mục tiêu đã đề ra.
6. Dọn instance clone sau khi hoàn thành test và hết nhu cầu forensic/rollback, tránh chi phí tiếp tục.

**Không giả định** backup/PITR sẽ cứu mọi trường hợp mất vùng; chọn vị trí transaction logs, backup locality và khả năng cross-region restore theo tài liệu của engine/backup option.

### 12.5. Vòng đời backup, key và quyền xóa

Backups là tài nguyên nhạy cảm vì có dữ liệu sản xuất. Hạn chế IAM người được restore/export/xóa; dùng Cloud KMS khi phù hợp, đặt retention rõ ràng, theo dõi audits. Với **CMEK**, không disable/destroy phiên bản khóa còn cần để giải mã backup. Nếu instance bị xóa, backup có được giữ hay không còn phụ thuộc backup option và **retained/final backup configuration**.

## 13. Migration, nâng cấp và thay đổi schema

### 13.1. Đưa dữ liệu từ môi trường cũ lên Cloud SQL

| Nguồn | Đường di chuyển điển hình | Điều cần kiểm tra |
|---|---|---|
| PostgreSQL tự quản trị | **Database Migration Service (DMS)** hoặc dump/restore | Versions/extensions, roles, large objects, replication permissions |
| MySQL tự quản trị | DMS hoặc logical dump/import | Binary logs, GTID, collations, stored procedures |
| SQL Server tại chỗ/VM | DMS theo tính năng được hỗ trợ hoặc native **.bak** export/import | T-SQL, logins, jobs, Active Directory, SQL Server edition/features |
| Giữa Cloud SQL instances | Engine-specific replication, backup/restore, export/import hoặc migration tool | Engine/version, region, downtime, RPO, compatibility |

**Không có công cụ “đổi engine bằng một nút”** để biến T-SQL thành PL/pgSQL. Migrate từ SQL Server sang PostgreSQL/MySQL cần chuyển schema, data types, stored procedures, query behavior, integration và test nghiệp vụ. Migrate major version cùng engine cũng có thể gây downtime hoặc yêu cầu quy trình đặc biệt.

### 13.2. Quy trình migration an toàn

1. **Inventory:** database size, extension/flags, connections, users, collations, SQL dialect, transaction peak.
2. **Prepare:** tạo target instance đúng engine/version/edition, networking/IAM/backups và monitoring.
3. **Transfer:** dump/restore hoặc DMS/replication theo khả năng của engine; đo lag và throughput.
4. **Validate:** checksums/counts, database constraints, query compatibility, timezone và encoding.
5. **Cutover:** dừng/tạm giới hạn writes theo runbook, đồng bộ lần cuối, đổi connection routing/secrets, smoke test.
6. **Rollback:** xác định điểm quay lại và cách đồng bộ dữ liệu mới; tránh tình huống hai databases cùng nhận writes không được phối hợp.
7. **Observe:** theo dõi slow queries, errors, connection counts, storage và chi phí; chỉ xóa nguồn sau khi hết retention/rollback window.

### 13.3. Schema migration với Java

Với Spring Boot, dùng **Flyway** hoặc **Liquibase** theo quy trình CI/CD để version hóa schema. Khi rolling release có nhiều phiên bản Java đang chạy, ưu tiên **expand/contract**:

~~~text
1. Expand : thêm cột/bảng/index tương thích code cũ
2. Deploy : Java v2 bắt đầu dùng schema mới
3. Migrate: backfill dữ liệu, đo performance và lỗi
4. Contract: gỡ cột/constraint cũ khi không còn code phụ thuộc
~~~

Không deploy thay đổi phá tương thích schema trước khi chắc rằng **Java v1 rollback** sẽ còn hoạt động. Một số DDL gây lock/table rewrite lớn; thử với dataset tương đương production và đo tác động đến SLO.

## 14. Giám sát, Query Insights và tối ưu chi phí

### 14.1. Mỗi triệu chứng cần nhìn cả hai phía

| Triệu chứng | Cloud SQL metrics | Java/app metrics |
|---|---|---|
| API p99 latency tăng | CPU/IO utilization, DB query latency, locks | Hikari pool wait, JDBC calls, request traces |
| Connection errors khi traffic tăng | Connections, max connections, CPU/memory | Cloud Run instance count, max pool size |
| Queries chậm sau release | Slow query/Query Insights, index usage | Version deploy, SQL statement shape |
| Storage tăng nhanh | Disk utilization, storage growth, transaction log retention | Batch jobs, message retry, large blobs |
| Read replica báo kết quả cũ | Replication lag, replica health | Client routing, read-after-write behavior |
| Failover/maintenance | Cloud SQL operations/events, availability | Reconnect errors, retry rate, readiness |
| Restore không đạt RTO | Backup size, operation duration | Traffic cutover/recovery workflow |

Sử dụng **Cloud SQL System Insights**, **Cloud Monitoring**, **Cloud Logging** và **Query Insights** khi tính năng hỗ trợ engine/version. Với PostgreSQL, có thể phân tích **pg_stat_statements** hoặc slow query/locks theo cấu hình; MySQL có slow query/performance_schema; SQL Server có **DMVs/Query Store** theo hỗ trợ của dịch vụ.

### 14.2. Alert minh họa

| Alert | Ngưỡng giả định | Gợi ý phản ứng |
|---|---|---|
| CPU utilization | Trên **85%** trong **15 phút** | Tìm queries nóng, index thiếu, kiểm tra capacity |
| Disk utilization | Trên **80%**, tăng nhanh | Đánh giá storage autosize, retention, growth |
| Connections | Trên **80%** mức giới hạn | Xem pool × số app instances, connection leaks |
| Replica lag | Trên **30 giây** trong **10 phút** | Tìm long transactions, I/O, SQL workload |
| Backup failure | Bất kỳ job quan trọng thất bại | Page owner, kiểm tra backup window/quotas |
| API DB errors | Tăng đột biến sau failover | Reconnect, IAM/network, DB login và pool |

**Các số là giả định**, không phải SLO mặc định của Cloud SQL. Một workload database OLTP có thể chịu lag thấp hơn nhiều; chọn ngưỡng qua baseline, error budget và tầm quan trọng dữ liệu.

### 14.3. Thành phần chi phí

| Thành phần | Yếu tố chính |
|---|---|
| **CPU/RAM** | Edition, machine series, số instances, thời gian hoạt động |
| **Storage/IO** | SSD/HDD theo edition, provisioned storage, autosize, throughput |
| **HA** | Primary + standby resources, vùng, chi phí hạ tầng |
| **Replicas** | Compute/storage của replicas, network replication |
| **Backups/PITR** | Backup option, size, retention, transaction logs, restore |
| **SQL Server** | License/engine edition + Cloud SQL compute/storage |
| **Network** | Inter-region transfer, VPC/PSC/egress, clients ngoài region |
| **Monitoring/logs** | Cloud Logging ingestion/retention, Monitoring, Query Insights khi tính phí |

**Budget alerts không tự ngắt instance**. Bật HA, một replica và backup retention dài trên một DB production có thể tạo nhiều dòng phí riêng. Ước lượng bằng **Google Cloud Pricing Calculator**, kiểm tra bảng giá theo **engine/edition/region** và theo dõi Billing report sau deployment.

### 14.4. Những tối ưu đầu tiên nên thử

1. **Tìm query chậm và index**, thay vì nâng machine ngay khi p95 tăng.
2. Sửa **N+1 queries** từ ORM và giảm số round trips JDBC.
3. Dùng **connection pool có giới hạn** và đặt Cloud Run/GKE autoscaling phù hợp.
4. Dùng **read replica** chỉ khi đọc là nút thắt thực, có yêu cầu độ mới dữ liệu chấp nhận lag.
5. Chọn storage growth/backup retention có căn cứ; không giảm backup vì muốn tiết kiệm khi RPO/RTO quan trọng.
6. Xóa tài nguyên lab và backup artifacts theo kế hoạch, nhưng không xóa version/instance còn cần cho rollback hoặc kiểm toán.

## 15. Troubleshooting: xử lý theo từng lớp

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra đầu tiên |
|---|---|---|
| **gcloud sql instances create** lỗi | API chưa bật, thiếu IAM, quota/region/edition/version không hợp lệ | Cloud SQL Admin API, organization policy, create operation |
| **PERMISSION_DENIED** từ Auth Proxy/connector | Principal ADC sai hoặc thiếu Cloud SQL Client | Service identity, IAM effective policy, instance connection name |
| **Connection refused / timeout** | Không có VPC route, sai IP/port, firewall, Proxy chưa chạy | Network path, 127.0.0.1:port, private IP/PSC DNS |
| **no pg_hba.conf entry / access denied** | DB login/TLS/user/host không được chấp nhận | Authentication mode, SQL user, log engine |
| **Invalid password / Login failed for user** | Sai username/password hoặc SQL Server AD config | Secret version, DB user status, rotation, grants |
| **IAM DB authentication không hoạt động trên SQL Server** | Không phải tính năng được hỗ trợ | Dùng SQL auth/AD/Entra; IAM chỉ quản lý instance/backup |
| **IAM DB login nhận 403 trên PostgreSQL/MySQL** | Thiếu instanceUser, client hoặc chưa thêm IAM DB user | IAM grants, instance flag, user mapping, automatic refresh |
| **Cloud Run v2 không kết nối private IP** | Chưa cấu hình Direct VPC egress/connector hoặc sai network | VPC egress, network/subnet, route |
| **Public IP connect trực tiếp lỗi** | Client IP không ở authorized networks hoặc TLS sai | CIDR allowlist, SSL settings |
| **Cloud SQL Proxy chạy nhưng Java không vào được** | JDBC URL/cổng sai hoặc DB credentials thiếu | Local listener, socket, dbname, JDBC exception |
| **Too many connections** | Hikari pool quá lớn × quá nhiều app instances | Cloud SQL connections, autoscale limit, pool leak |
| **p99 SQL latency cao** | Query/index/lock, GC/app timeout, I/O/CPU | Query Insights, slow query/locks, Cloud Monitoring |
| **Read replica thấy dữ liệu cũ** | Replication bất đồng bộ, lag tăng | Replica lag, ứng dụng có gửi reads đúng replica? |
| **Ứng dụng lỗi lúc failover** | JDBC connection cũ bị ngắt, không reconnect | Connection timeout, retry, health probes |
| **PITR không tìm được thời điểm** | Chưa bật PITR từ trước, mốc ngoài retention, log thiếu | Backup option, transaction-log retention, recovery window |
| **Restore đã xong nhưng Java không vào đúng dữ liệu** | App vẫn trỏ primary cũ, DB users/secret/config khác | Instance connection name, endpoints, schema, validation |
| **Chi phí tăng mạnh sau bật HA** | Standby/edition/storage và backup phụ phí | Billing breakdown, edition, machine, replicas |

### 15.1. Lệnh kiểm tra không làm thay đổi dữ liệu

~~~bash
gcloud sql instances list --project=shop-dev-001
gcloud sql instances describe orders-pg --project=shop-dev-001
gcloud sql databases list --instance=orders-pg --project=shop-dev-001
gcloud sql users list --instance=orders-pg --project=shop-dev-001
gcloud sql backups list --instance=orders-pg --project=shop-dev-001
gcloud sql operations list --instance=orders-pg --project=shop-dev-001
~~~

Kết hợp với **Cloud SQL System Insights, Query Insights, Cloud Monitoring, Cloud Logging** và logs của Java/GKE/Cloud Run. Không in mật khẩu, SQL result chứa dữ liệu khách hàng hoặc toàn bộ JDBC connection string có secret vào ticket/log.

### 15.2. Một quy trình điều tra hiệu quả

1. **Xác định tài nguyên:** project/instance/database/region, engine, edition, trạng thái maintenance.
2. **Xác định lớp lỗi:** resource provisioning, network, connector IAM, DB login, SQL privileges, query/connection pool, data recovery.
3. **Chỉ sửa đúng lớp:** 403 không có nghĩa phải cấp Cloud SQL Admin; SQL GRANT không sửa lỗi VPC route.
4. **Giảm rủi ro production:** kiểm tra thay đổi mới nhất; nếu đang canary và app mới lỗi, rollback app traffic sau khi kiểm tra schema compatibility.
5. **Đo lại:** connection success, request 5xx, p95/p99, DB locks/connections, replica lag, transaction correctness.

## 16. Tình huống tổng hợp: đơn hàng Java, báo cáo và phân vùng dữ liệu

Công ty **Minh Phúc** dự định chuyển PostgreSQL tự quản trị trên Compute Engine sang Cloud SQL. Có yêu cầu:

- Java **orders-api** trên Cloud Run phải ghi đơn hàng an toàn, không lộ password.
- GKE reporting worker có thể đọc dữ liệu tổng hợp và chịu lag vài giây, nhưng không ghi đơn hàng.
- Dịch vụ cần phục hồi khi hỏng một zone; lỗi xóa dữ liệu nhầm cần khôi phục trong cửa sổ 7 ngày.
- Production ở **asia-southeast1**, có kế hoạch DR ngoài vùng và theo dõi chi phí.

### 16.1. Phương án ban đầu

| Quyết định | Lựa chọn | Vì sao |
|---|---|---|
| Engine | **Cloud SQL for PostgreSQL** cùng major version đã kiểm thử | Giảm khác biệt SQL khi migration |
| Edition | Enterprise hoặc Enterprise Plus theo SLO/baseline | Không chỉ chọn edition theo tên |
| Availability | **REGIONAL HA** | Bảo vệ khỏi một số zone/instance failures |
| Networking | Private IP + Cloud Run VPC egress; GKE cùng VPC/route | Hạn chế truy cập public DB |
| App authentication | Runtime service accounts riêng; IAM DB auth hoặc SQL user tối thiểu | Tách kết nối cloud khỏi SQL grants |
| Java | HikariCP pool có giới hạn, prepared statements, idempotency key | Tránh connection storm và duplicate orders |
| Reporting | Read replica nếu tải đo được cần | Giảm load primary, chấp nhận lag |
| Backup | Standard/Enhanced theo retention và compliance + PITR đã bật | Khôi phục DELETE nhầm |
| Observability | System Insights, SQL metrics, Cloud Run/GKE logs, alerts | Phát hiện sớm và đo RTO/RPO |

### 16.2. Dòng phát hành và DR

~~~mermaid
flowchart TD
    OLD["PostgreSQL tự quản trị"] --> MIG["Migration rehearsal + DMS/dump"]
    MIG --> TEST["Validate data, IAM, latency, backup/restore"]
    TEST --> CUT["Cutover Java connection"]
    CUT --> PROD["Cloud SQL primary HA"]
    PROD --> RR["Read replica nếu cần"]
    PROD --> BAK["Backups + PITR"]
    PROD --> MON["Cloud Monitoring + alerts"]
    MON --> FAIL{"Sự cố?"}
    FAIL -->|"Zone failure"| HA["HA automatic failover + app reconnect"]
    FAIL -->|"DELETE nhầm"| PITR["PITR ra instance mới + validation"]
    FAIL -->|"Region outage"| DR["DR runbook: restore/promote, app routing"]
~~~

### 16.3. Test chấp nhận trước production

| Kịch bản | Kết quả mong muốn |
|---|---|
| Deploy Java với DB user chỉ đọc | INSERT bị từ chối nhưng SELECT được nếu đã cấp |
| Runtime service account không có Cloud SQL Client | Auth Proxy không được phép kết nối |
| Java dùng SQL Server nhưng chỉ bật IAM DB auth | Tài liệu/runbook phát hiện không hỗ trợ, chọn cách đúng |
| Cloud Run scale từ 2 lên 40 instances | DB connection count vẫn trong giới hạn pool |
| Read replica chậm 15 giây | Orders API đọc primary khi cần consistency |
| Thử ngắt DB kết nối trên môi trường lab | App reconnect, retry idempotent; không nhân đôi đơn hàng |
| Backup/PITR test | Restore sang instance mới, kiểm tra row counts và RTO |
| SQL migration có thay schema | Bản Java cũ vẫn hoạt động trong cửa sổ rollback |
| Thử đổi credential | Secret version/connection pool được cập nhật không downtime quá SLO |
| Kết thúc thử nghiệm | Dọn instances, replicas, backups và các tài nguyên tính phí theo policy |

## 17. Bài tập thực hành có đáp án

### Bài tập A — Chọn engine

Ứng dụng hiện tại phụ thuộc **T-SQL stored procedures** và SQL Server Agent jobs. Nhóm muốn migrate nhanh sang PostgreSQL để giảm phí.

**Đáp án:** Không giả định đổi engine là lift-and-shift. Có thể cân nhắc **Cloud SQL for SQL Server** để giữ compatibility trước, hoặc thực hiện **migration project riêng** chuyển stored procedures, schema và integration nếu lợi ích dài hạn xứng đáng. Kiểm tra tính năng SQL Server trong Cloud SQL được hỗ trợ đến mức nào.

### Bài tập B — IAM hay SQL GRANT?

Cloud Run runtime có **roles/cloudsql.client**, Proxy đã connect, nhưng JDBC báo **permission denied for table orders**.

**Đáp án:** Cloud IAM connector đã đủ; thiếu SQL privileges. DBA cần cấp **GRANT SELECT/INSERT...** đúng schema/table cho DB user, không cấp Cloud SQL Admin để sửa lỗi này.

### Bài tập C — Xác thực giữa ba engines

**Hỏi:** IAM database authentication có dùng giống nhau cho PostgreSQL, MySQL và SQL Server không?

**Đáp án:** Không. PostgreSQL/MySQL hỗ trợ IAM DB auth sau khi cấu hình instance, IAM role và DB users. SQL Server không hỗ trợ IAM DB auth cho queries; dùng SQL auth, Active Directory/Entra ID theo chức năng.

### Bài tập D — Public hay private IP?

Cloud Run orders-api cần kết nối private IP Cloud SQL. Nhóm đã cấp SQL Client nhưng connect timeout.

**Đáp án:** IAM role không tạo network route. Kiểm tra **Direct VPC egress hoặc Serverless VPC Access**, subnet/VPC, private services access/PSC và firewall. Đồng thời xác nhận app không dùng sai IP/port.

### Bài tập E — Giới hạn connections

Cloud Run có thể scale lên **60 instances**, mỗi instance HikariCP pool tối đa **8 connections**. Không tính các nguồn khác, tối đa có bao nhiêu DB connections?

**Đáp án:** **480 connections**. Chưa tính DBAs/reporting/jobs; cần đối chiếu với Cloud SQL max connections và đặt pool/max instances hợp lý.

### Bài tập F — HA hay backup?

Do lỗi script, ứng dụng xóa 100.000 rows lúc 10:15. Instance đã bật regional HA, nhưng chưa bật PITR.

**Đáp án:** HA sẽ **sao chép cả DELETE** sang standby, không có tác dụng undo. Phải restore từ **backup khả dụng**, chấp nhận RPO tùy thời điểm và có thể mất writes gần đây. Bật PITR trước khi sự cố mới có thể phục hồi theo thời điểm.

### Bài tập G — Read replica và nhất quán

Người dùng vừa thanh toán, sau 100 ms API gọi read replica để hiển thị trạng thái thanh toán và nhận trạng thái cũ.

**Đáp án:** Replica bất đồng bộ có **replication lag**. Giao dịch cần read-after-write nên đọc **primary**, hoặc dùng ứng dụng đồng bộ/cơ chế chờ phù hợp khi cần.

### Bài tập H — PITR và backup options

Một Cloud SQL instance dùng **Enhanced backups** và cần khôi phục về một thời điểm hôm qua.

**Đáp án:** Xác định **backup vault/data source**, PITR window và chọn **point-in-time-restore** theo hướng dẫn Enhanced backups. Khôi phục ra **instance mới**; không coi đây là lệnh sửa trực tiếp instance chính và không dùng bừa workflow clone dành cho Standard backup.

### Bài tập I — Edition và SQL Server license

Một người nói: **Cloud SQL Enterprise Plus** nghĩa là đã chọn **SQL Server Enterprise** cho mọi database.

**Đáp án:** Sai. Cloud SQL edition là **gói dịch vụ**, còn SQL Server edition là **license/feature của engine**. Với SQL Server, các tổ hợp version/edition được hỗ trợ khác nhau; chọn đúng cả hai và tính license costs.

### Bài tập J — Bảo mật và chi phí

Java service lưu SQL password trong Dockerfile ENV, Cloud SQL có public IP cho **0.0.0.0/0**; backup retention là 1 ngày dù chính sách cần 30 ngày.

**Đáp án:** Chuyển password vào Secret Manager hoặc IAM DB auth khi hỗ trợ, rotate credential đã lộ; xóa công khai rộng, ưu tiên private IP/connector; cấu hình backup option/retention **đủ 30 ngày**, kiểm thử restore; review IAM, logs, CMEK và ngân sách. **Không tin việc chỉ xóa ENV trong image mới là đã thu hồi password** — cần revoke tại DB.

## 18. Checklist vận hành và tổng kết

### Trước khi triển khai

1. Xác nhận **engine/version/edition/region** và support lifecycle.
2. Chọn vCPU/RAM/storage và **REGIONAL HA** theo RTO/SLO; có kế hoạch cross-region DR.
3. Chốt public/private/PSC và connector, TLS, service identity, DB user/roles, secrets.
4. Bật backups và PITR đúng backup option, đo restore rehearsal, kiểm tra key/location.
5. Test query latency, connection pools và khả năng scale của Java backend.
6. Đặt dashboards, error alerts, backup alerts, billing budgets và người trực xử lý.

### Khi có sự cố

1. Phân loại network/IAM/DB login/SQL GRANT/query/HA/backup thay vì sửa tất cả cùng lúc.
2. Với lỗi triển khai Java, rollback traffic/schema theo hướng dẫn tương thích.
3. Với lỗi dữ liệu, **dừng writes gây hại**, bảo toàn logs và phục hồi ra instance mới để so sánh.
4. Với failover, cho connections reconnect có kiểm soát; xác minh các giao dịch **idempotent**.
5. Ghi lại RTO/RPO, chi phí và hành động sau sự cố.

**Ghi nhớ:** Cloud SQL giúp vận hành PostgreSQL, MySQL và SQL Server dễ hơn, nhưng **không loại bỏ DBA discipline**. Chọn engine và edition phù hợp, giới hạn IAM và SQL privileges, thiết kế kết nối an toàn, kiểm soát JDBC pools, bật backup/PITR và kiểm thử khôi phục là nền tảng để ứng dụng Java bền vững.

## 19. Tài liệu Google Cloud chính thức

1. [Cloud SQL FAQ](https://docs.cloud.google.com/sql/faq) — tổng quan ba engines và các giới hạn.
2. [Database versions and version policies](https://docs.cloud.google.com/sql/docs/db-versions) — hỗ trợ version/EOL và extended support.
3. [Cloud SQL PostgreSQL editions](https://docs.cloud.google.com/sql/docs/postgres/editions-intro) — Enterprise/Enterprise Plus.
4. [Cloud SQL MySQL editions](https://docs.cloud.google.com/sql/docs/mysql/editions-intro) — cấu hình/khả năng theo edition.
5. [Cloud SQL SQL Server editions](https://docs.cloud.google.com/sql/docs/sqlserver/editions-intro) — Cloud SQL editions và SQL Server licensing/versions.
6. [Create PostgreSQL instances](https://docs.cloud.google.com/sql/docs/postgres/create-instance) — gcloud flags, edition, CPU/RAM.
7. [Create MySQL instances](https://docs.cloud.google.com/sql/docs/mysql/create-instance) — versions và máy.
8. [Create SQL Server instances](https://docs.cloud.google.com/sql/docs/sqlserver/create-instance) — password và license options.
9. [Choose connection options](https://docs.cloud.google.com/sql/docs/postgres/connection-options) — private/public IP, connector.
10. [Cloud SQL Auth Proxy](https://docs.cloud.google.com/sql/docs/postgres/connect-auth-proxy) — ADC, TLS và sidecar.
11. [Connect Cloud Run to Cloud SQL](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — network/Cloud Run integration.
12. [PostgreSQL IAM database authentication](https://docs.cloud.google.com/sql/docs/postgres/iam-logins) — instanceUser, Client và SQL GRANT.
13. [MySQL IAM database authentication](https://docs.cloud.google.com/sql/docs/mysql/iam-logins) — IAM DB user/group.
14. [SQL Server IAM authentication limitations](https://docs.cloud.google.com/sql/docs/sqlserver/iam-authentication) — không hỗ trợ IAM DB login.
15. [Cloud SQL high availability](https://docs.cloud.google.com/sql/docs/postgres/high-availability) — regional HA và failover.
16. [SQL Server replication](https://docs.cloud.google.com/sql/docs/sqlserver/replication) — read replicas.
17. [Choose backup options](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backup-options) — Standard và Enhanced.
18. [Point-in-time recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/pitr) — Standard/Enhanced recovery workflows.
19. [Monitor instances](https://docs.cloud.google.com/sql/docs/postgres/monitor-instance) — System Insights và Monitoring.
