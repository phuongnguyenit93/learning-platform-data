# IAM database authentication và quản lý người dùng

> **Chương:** Cloud SQL và AlloyDB  
> **Bài học:** IAM database authentication và quản lý người dùng  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM, VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua triển khai thực tế, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành, quan sát độ tin cậy và kiểm soát chi phí. Một phần quan trọng của bảo mật ứng dụng Java là **xác định ai được đăng nhập database, bằng danh tính nào, qua đường mạng nào và được phép thao tác dữ liệu gì**.

**IAM database authentication** cho phép Cloud SQL và AlloyDB sử dụng danh tính Google Cloud IAM cùng **OAuth 2.0 access token ngắn hạn** thay cho mật khẩu database tĩnh. Tuy nhiên, **IAM không tự cấp quyền `SELECT`, `INSERT` hoặc `DELETE` bên trong PostgreSQL/MySQL**. Một kết nối thành công phải vượt qua **các lớp độc lập**: identity/IAM, đường mạng/TLS, database account và quyền SQL.

Bài này tập trung vào **Cloud SQL for PostgreSQL/MySQL** và **AlloyDB for PostgreSQL**, đặc biệt là Java workload chạy trên Cloud Run hoặc GKE. **Cloud SQL for SQL Server không hỗ trợ kiểu IAM database authentication được mô tả ở đây**, dù Google Cloud IAM vẫn được dùng để quản trị tài nguyên instance. Các lệnh tạo users, sửa IAM, thay flags và chạy SQL dưới đây **có tác động thật**, chỉ thực hiện trong project sandbox đã được phê duyệt.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **IAM permission đăng nhập**, **connection authorization**, **database account** và **SQL privileges**.
2. So sánh **built-in password authentication**, **individual IAM authentication** và **IAM group authentication**.
3. Cấu hình IAM database authentication cho **Cloud SQL PostgreSQL/MySQL** và **AlloyDB PostgreSQL** theo các database flags riêng.
4. Cấp đúng các role `roles/cloudsql.instanceUser`, `roles/cloudsql.client`, `roles/alloydb.databaseUser` và `roles/alloydb.client` khi cần.
5. Đăng nhập qua **Cloud SQL Auth Proxy/Java Connector** hoặc **AlloyDB Auth Proxy** bằng automatic IAM authentication.
6. Tạo database users/groups, dùng `GRANT` và `REVOKE` theo nguyên tắc least privilege.
7. Kết nối Java JDBC với IAM authentication, tránh lưu service account key và mật khẩu database trong repository.
8. Quản lý lifecycle onboarding/offboarding, account naming, group propagation, audit và application connection pooling.
9. Khoanh vùng lỗi IAM 403, database `permission denied`, xác thực thất bại và lỗi mạng.
10. Hoàn thành bài tập và case study phân quyền cho Orders API, Billing Worker và nhóm phân tích.

## 2. Bốn lớp kiểm soát trước khi đọc được dữ liệu

~~~mermaid
flowchart LR
    App["Java Orders API<br/>runtime service account"]
    IAM["Google Cloud IAM<br/>login + connect"]
    Network["VPC / PSC / IP<br/>connector + TLS"]
    DBLogin["Database account<br/>IAM user hoặc group"]
    SQL["PostgreSQL / MySQL<br/>GRANT, role, schema"]
    Data["orders database<br/>tables / views"]
    App --> IAM --> Network --> DBLogin --> SQL --> Data
~~~

| Lớp | Kiểm tra điều gì? | Ví dụ |
|---|---|---|
| **Google IAM** | Principal có permission kết nối và đăng nhập instance không? | `cloudsql.instances.login`, `alloydb.users.login` |
| **Kết nối mạng** | Client có đường đi, TLS/connector và policy kết nối phù hợp không? | Cloud SQL Auth Proxy, VPC private IP, AlloyDB Auth Proxy |
| **Database user** | User/service account/group đã được đăng ký cho instance hoặc cluster chưa? | `dev@example.com`, `orders-api@PROJECT_ID.iam` |
| **SQL authorization** | Database user/role được dùng database, schema, bảng nào? | `GRANT CONNECT`, `GRANT USAGE`, `GRANT SELECT` |

Một người có `roles/cloudsql.admin` trên project **không đương nhiên** được đọc dữ liệu đơn hàng. Ngược lại, `GRANT SELECT` cho một PostgreSQL role **không tạo ra quyền IAM đăng nhập từ bên ngoài**. SQL roles và Google Cloud IAM roles là **hai hệ thống phân quyền khác nhau**, cần kiểm soát và kiểm toán đồng thời.

### 2.1. Authentication khác authorization

- **Authentication:** xác minh principal muốn đăng nhập là ai — bằng mật khẩu database hoặc IAM access token.
- **Connection authorization:** quyền dùng connector/proxy để thiết lập kết nối được Google Cloud kiểm tra.
- **Database authorization:** sau khi đăng nhập, PostgreSQL/MySQL kiểm tra `GRANT`, ownership, schema và row-level security nếu áp dụng.
- **Application authorization:** mã Java vẫn kiểm tra tenant/user, không dùng riêng SQL account để kết luận khách hàng A được đọc đơn hàng B.

**Không xem IAM database authentication là công cụ tự động bảo vệ dữ liệu theo tenant**. Nếu API Java dùng chung một runtime SA và một database account, DB vẫn không tự biết người dùng HTTP nào đang gọi; cần domain authorization/RLS context có thiết kế cẩn thận.

## 3. So sánh Cloud SQL và AlloyDB

| Chủ đề | Cloud SQL for PostgreSQL | Cloud SQL for MySQL | AlloyDB for PostgreSQL |
|---|---|---|---|
| Engine | PostgreSQL | MySQL | PostgreSQL-compatible |
| Instance flag IAM | `cloudsql.iam_authentication=on` | `cloudsql_iam_authentication=on` | `alloydb.iam_authentication=on` |
| Group IAM flag | Dùng IAM flag ở trên | Dùng IAM flag ở trên | Cần thêm `alloydb.iam_group_authentication=on` |
| IAM login role | `roles/cloudsql.instanceUser` | `roles/cloudsql.instanceUser` | `roles/alloydb.databaseUser` |
| Connector/proxy role | `roles/cloudsql.client` | `roles/cloudsql.client` | `roles/alloydb.client` |
| Khác với quyền SQL | PostgreSQL `GRANT` | MySQL `GRANT` | PostgreSQL `GRANT` |
| Proxy | Cloud SQL Auth Proxy **v2** | Cloud SQL Auth Proxy **v2** | **AlloyDB Auth Proxy** |
| IAM group | Cloud Identity group, account sinh khi member đăng nhập | Tương tự, chú ý tên MySQL | IAM group trên cluster, bật cả hai flags |
| User provisioning | Gắn với **instance** | Gắn với **instance** | Tạo IAM user ở **cluster** |
| Token | OAuth access token, thường có hiệu lực khoảng **1 giờ** | Tương tự | OAuth access token ngắn hạn |
| Built-in users | Có thể cùng tồn tại với IAM users | Có thể cùng tồn tại | Có thể cùng tồn tại |

**Tính năng IAM database authentication của Cloud SQL không áp dụng cho SQL Server**. Việc thấy `roles/cloudsql.client` hoặc `roles/cloudsql.admin` trên một SQL Server instance không biến tài khoản SQL Server thành IAM database user.

### 3.1. Individual IAM vs IAM group vs password

| Cách quản lý | Ưu điểm | Đánh đổi |
|---|---|---|
| **Built-in username/password** | Tương thích công cụ cũ, không cần IAM token | Cần lưu/rotation/revocation password; dễ dùng chung account |
| **IAM từng user/service account** | Tên rõ ràng, login bằng token ngắn hạn, IAM revoke tập trung | Phải tạo từng DB account và gán SQL privileges |
| **IAM group** | Quản lý quyền theo nhóm, onboarding/offboarding dễ hơn | Group membership propagation; cần migration nếu user tồn tại dạng cá nhân |
| **Workforce Identity Federation** (nếu được hỗ trợ) | Không phải cấp tài khoản Google riêng cho mọi người dùng ngoài | Có giới hạn/cấu hình khác với IAM group; phải kiểm tra engine và connector |

Với ứng dụng production Java, **ưu tiên service identity riêng** cho mỗi workload. Với con người truy cập phân tích/khắc phục sự cố, **IAM group** thường giảm số thay đổi thủ công và giúp thu hồi tập trung.

## 4. Automatic IAM authentication và manual authentication

~~~mermaid
sequenceDiagram
    participant Java as Java / psql
    participant Proxy as Cloud SQL / AlloyDB connector
    participant IAM as Google IAM
    participant DB as Database
    Java->>Proxy: Kết nối với IAM DB username
    Proxy->>IAM: Lấy/refresh short-lived access token
    IAM-->>Proxy: Token gắn với runtime principal
    Proxy->>DB: Thiết lập kết nối được xác thực và mã hóa
    DB->>DB: Kiểm tra IAM user + SQL privileges
    DB-->>Java: Query result / permission denied
~~~

### 4.1. Automatic IAM database authentication

- **Cloud SQL:** hỗ trợ Cloud SQL Auth Proxy v2 `--auto-iam-authn` hoặc Cloud SQL Language Connectors (Java/Go/Python).
- **AlloyDB:** hỗ trợ AlloyDB Auth Proxy `--auto-iam-authn` hoặc AlloyDB Language Connectors.
- Connector **tự lấy và làm mới access token** khi cần kết nối mới; hữu ích cho Java service có connection pool.
- Principal dùng để **chạy connector phải trùng với principal được đăng ký làm IAM DB user**, trừ khi đã thiết kế service account impersonation hợp lệ.
- Kết nối client tới local proxy thường là loopback; **proxy mã hóa đường kết nối đến database**, nhưng phải bảo vệ local listener khỏi người dùng không đáng tin.

**Đây là phương án khuyến nghị** cho các ứng dụng chạy lâu. Nó tránh lưu token một giờ vào `application.properties` hoặc yêu cầu người vận hành rotate mật khẩu thủ công.

### 4.2. Manual IAM database authentication

Quy trình là **lấy OAuth access token**, dùng token làm password của IAM DB user trong `psql`/`mysql`; thường dành cho thử nghiệm hoặc tình huống đặc biệt.

~~~bash
# Minh họa Cloud SQL PostgreSQL trên bash/Cloud Shell.
# Không in token, không bật shell tracing; cần kết nối SSL.
PGPASSWORD="$(gcloud sql generate-login-token)" \
  psql "hostaddr=DATABASE_IP dbname=orders user=dev@example.com sslmode=require" \
  --no-password
~~~

**Cảnh báo:**

- Token có hạn khoảng **một giờ**; connection mới sau khi hết hạn có thể fail, nên không dùng cách này làm cấu hình cố định cho pool Java.
- `psql` có giới hạn độ dài khi nhập password tương tác; truyền token qua biến môi trường theo hướng dẫn, **không dán token vào console/log/ticket**.
- Truy cập trực tiếp cần đường mạng tới IP instance và chứng thực TLS theo thiết kế. `sslmode=require` mã hóa, nhưng đánh giá verify certificate/hostname theo chính sách bảo mật production.
- Không dùng `gcloud auth print-access-token` một cách tùy tiện thay `gcloud sql generate-login-token` nếu cần token có scope login phù hợp.
- Nếu dùng **Context-Aware Access**, Cloud SQL/AlloyDB connectors với IAM DB auth có những hạn chế riêng; cần kiểm tra hướng kết nối trực tiếp được hỗ trợ.

### 4.3. Vì sao ADC có thể gây nhầm lẫn?

`gcloud auth login` cấu hình credential của **gcloud CLI**; `gcloud auth application-default login` tạo **Application Default Credentials** cho ứng dụng/connector local. Đây không nhất thiết là cùng identity.

Nếu bạn thêm DB user `dev@example.com`, nhưng local proxy chạy bằng ADC của `ops@example.com`, **automatic IAM authentication không thể đăng nhập tùy ý bằng `dev@example.com`**. Khi chạy trên Cloud Run/GKE, kiểm tra **runtime service account** hoặc Workload Identity Federation for GKE, không suy từ người đã deploy.

## 5. IAM roles theo nhiệm vụ: ít quyền nhất

### 5.1. Cloud SQL

| Identity | IAM role | Phạm vi/ý nghĩa |
|---|---|---|
| IAM DB user hoặc service account | `roles/cloudsql.instanceUser` | Quyền `cloudsql.instances.login` để đăng nhập IAM |
| Identity chạy Cloud SQL Auth Proxy/Java Connector | `roles/cloudsql.client` | Quyền `cloudsql.instances.connect` và hỗ trợ kết nối |
| Database operator | Quyền quản trị DB/instance cần thiết | Chỉ dành cho người vận hành, **không cấp cho Java runtime** |
| Reader SQL data | **PostgreSQL/MySQL GRANT**, không phải Cloud IAM role | Chỉ bảng/schema mà workload cần |

Nếu Java connector chạy dưới **cùng** runtime service account, account đó thường cần **cả Instance User và Cloud SQL Client**. Các IAM bindings được cấp theo scope thực tế mà sản phẩm hỗ trợ; Cloud SQL login IAM có thể được quản lý ở cấp project qua IAM policy, cần hạn chế project/resources theo kiến trúc và org policy.

### 5.2. AlloyDB

| Identity | IAM role | Ý nghĩa |
|---|---|---|
| IAM DB user/group | `roles/alloydb.databaseUser` | Cho phép database IAM login |
| Principal dùng AlloyDB Auth Proxy/Language Connector | `roles/alloydb.client` | Cho phép thiết lập kết nối qua connector |
| Principal tương tác API để xác minh quyền | `roles/serviceusage.serviceUsageConsumer` | Role cần theo hướng dẫn IAM/connector |
| Data reader/writer | PostgreSQL `GRANT` | Phân quyền SQL thực, không phải `roles/alloydb.admin` |

Trong một Java workload dùng AlloyDB Auth Proxy và automatic IAM auth, runtime identity thường cần **Database User + AlloyDB Client + Service Usage Consumer**, rồi được tạo **database account trên cluster** và cấp quyền SQL.

**Không cấp `roles/owner`, `roles/editor`, `roles/cloudsql.admin` hoặc `roles/alloydb.admin` cho Java app chỉ để vượt 403.** Quyền quản trị hạ tầng không thay thế phân quyền SQL.

## 6. Chuẩn bị lab Cloud SQL PostgreSQL

Lab sử dụng **Cloud SQL PostgreSQL instance đã tồn tại** và database `orders`. Không tạo instance mới vì việc này dễ phát sinh chi phí lớn hơn nhu cầu bài học.

| Thành phần | Giá trị giả định |
|---|---|
| Project | `PROJECT_ID` |
| Region | `asia-southeast1` |
| Cloud SQL instance | `orders-pg` |
| Instance connection name | `PROJECT_ID:asia-southeast1:orders-pg` |
| PostgreSQL database | `orders` |
| IAM human account | `dev@example.com` |
| IAM app SA | `orders-api@PROJECT_ID.iam.gserviceaccount.com` |
| PostgreSQL app username | `orders-api@PROJECT_ID.iam` |
| SQL application role | `orders_reader` |
| Schema/table | `public.orders` |

**Không dùng địa chỉ `dev@example.com` hoặc `PROJECT_ID` theo nghĩa literal**; thay chúng bằng giá trị sandbox thật. Nếu chưa có database/table, DBA tạo theo migration được kiểm soát; ví dụ `GRANT` chỉ chạy khi đối tượng đã có.

### 6.1. Kiểm tra không thay đổi tài nguyên

~~~bash
gcloud auth list
gcloud config get-value project

gcloud sql instances describe orders-pg \
  --project=PROJECT_ID \
  --format="yaml(name,region,connectionName,settings.databaseFlags)"

gcloud sql users list \
  --project=PROJECT_ID \
  --instance=orders-pg

gcloud projects get-iam-policy PROJECT_ID \
  --format="yaml(bindings)"
~~~

Hãy xem trước instance flag **`cloudsql.iam_authentication`**, network/IP, backups và vai trò hiện hữu. Cần Cloud SQL Admin API đã bật và IAM đủ cho thao tác đọc/ghi.

### 6.2. Bật flag IAM: chú ý mất cấu hình khác

Đối với Cloud SQL PostgreSQL, bật:

~~~text
cloudsql.iam_authentication=on
~~~

Trên **instance đang chạy**, có thể dùng Google Cloud Console → Cloud SQL → instance → Edit → Flags; hoặc `gcloud sql instances patch`. **Cảnh báo quan trọng:** lệnh `--database-flags` có thể **thay thế toàn bộ danh sách flags đang đặt**. Nếu chỉ ghi IAM flag, các flags khác bị reset về mặc định.

~~~bash
# CHỈ MINH HỌA cú pháp; không chạy nguyên lệnh trên production.
# Phải đọc tất cả existing flags và liệt kê lại trong cùng patch.
gcloud sql instances patch orders-pg \
  --project=PROJECT_ID \
  --database-flags=cloudsql.iam_authentication=on
~~~

Lệnh mẫu trên **không an toàn nếu instance đã có flags khác**. Trước khi thực hiện thật, lưu toàn bộ flags, sao lưu/chốt change window, giữ các flag khác trong patch và kiểm tra khả năng restart/ảnh hưởng kết nối. Trên Cloud SQL MySQL, tên flag khác: **`cloudsql_iam_authentication`** (dấu gạch dưới).

## 7. Thực hành A — Cấp IAM login cho Cloud SQL

### 7.1. Bước 1: Cấp quyền IAM cho người học

**Các lệnh sau sửa IAM project** và chỉ dành cho sandbox có quản trị được ủy quyền:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/cloudsql.instanceUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/cloudsql.client"
~~~

`roles/cloudsql.instanceUser` cho phép **IAM DB login**; `roles/cloudsql.client` phục vụ **Cloud SQL Auth Proxy/connector**. Hai role này **không** tạo database user và **không** cấp `SELECT` trên bảng `orders`.

### 7.2. Bước 2: Tạo IAM user ở Cloud SQL instance

~~~bash
gcloud sql users create dev@example.com \
  --project=PROJECT_ID \
  --instance=orders-pg \
  --type=cloud_iam_user

gcloud sql users list \
  --project=PROJECT_ID \
  --instance=orders-pg
~~~

User là **`CLOUD_IAM_USER`** thuộc instance `orders-pg`. Nếu database có quyền sẵn của `PUBLIC`, user có thể kế thừa chúng; vì vậy không nói “không có quyền gì tuyệt đối” — cần audit quyền `PUBLIC` cùng với explicit grants.

### 7.3. Bước 3: Cấp SQL privileges riêng

Kết nối **bằng DBA role được phê duyệt** để chạy SQL dưới đây, không dùng quyền của learner để tự cấp cho mình:

~~~sql
-- PostgreSQL trong database orders:
CREATE ROLE orders_reader NOLOGIN;

GRANT CONNECT ON DATABASE orders TO orders_reader;
GRANT USAGE ON SCHEMA public TO orders_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO orders_reader;

-- Vì IAM username chứa @ và dấu chấm, phải dùng quoted identifier.
GRANT orders_reader TO "dev@example.com";
~~~

**Quyền SELECT trên tất cả bảng** là ví dụ nhóm phân tích; với Orders API, nên chọn bảng/view cụ thể để giảm dữ liệu được truy cập. PostgreSQL `GRANT SELECT ON ALL TABLES` **chỉ áp cho những bảng hiện có**, không tự cấp quyền trên các bảng tạo sau. Nếu cần, DBA cấu hình default privileges theo **đúng role tạo bảng**:

~~~sql
-- Chỉ là ví dụ: chạy bởi DBA/role có quyền để quản lý
-- các bảng được tạo về sau bởi role app_owner.
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT SELECT ON TABLES TO orders_reader;
~~~

Kiểm tra trước khi áp dụng: role `app_owner` tồn tại và thực sự tạo bảng. Default privileges **không áp ngược** lên bảng đã tồn tại và **không tự bao phủ bảng do owner khác tạo**.

### 7.4. Bước 4: Kết nối qua Cloud SQL Auth Proxy v2

Trên máy dev/Cloud Shell được phép, **ADC phải thuộc đúng `dev@example.com`**:

~~~bash
gcloud auth application-default login

# Chạy riêng một terminal, cần binary cloud-sql-proxy v2 đã cài.
cloud-sql-proxy --auto-iam-authn \
  PROJECT_ID:asia-southeast1:orders-pg
~~~

Terminal khác:

~~~bash
psql -h 127.0.0.1 -p 5432 \
  -U "dev@example.com" \
  --dbname=orders

# Bên trong psql:
# SELECT current_user, current_database();
# SELECT COUNT(*) FROM public.orders;
~~~

Cloud SQL Auth Proxy mặc định lắng nghe loopback, không cần phát sinh database password. **Kết nối từ client tới local proxy là kết nối cục bộ**, còn proxy cung cấp bảo mật/TLS khi đi tới Cloud SQL. Trên VM/bastion dùng chung, hạn chế người khác truy cập port/socket của proxy vì connector đang chạy dưới IAM principal được cấp quyền.

**Hạ tầng mạng vẫn phải đúng:** Cloud SQL connector cần egress tới Cloud APIs qua TCP 443 và tới instance qua cổng 3307, và không tự tạo đường VPC nếu đang chọn **private IP**. Nếu thiết lập `--private-ip`, máy chạy proxy phải có network path tới Cloud SQL instance.

### 7.5. Kiểm tra cả “cho phép” và “từ chối”

~~~sql
-- Thành công khi có CONNECT, USAGE và SELECT:
SELECT COUNT(*) FROM public.orders;

-- Nếu orders_reader không được cấp DELETE, câu lệnh dưới đây
-- KHÔNG được chạy trên dữ liệu thật; chỉ test trên bảng thử.
-- DELETE FROM public.orders WHERE id = 1;
~~~

**Không dùng dữ liệu production để thử negative permissions**. Hãy tạo bảng thử riêng, hoặc dùng `has_table_privilege` để kiểm tra mà không thực thi tác động:

~~~sql
SELECT current_user;
SELECT has_table_privilege(current_user, 'public.orders', 'SELECT') AS can_read;
SELECT has_table_privilege(current_user, 'public.orders', 'DELETE') AS can_delete;
~~~

Kỳ vọng `can_read=true` và `can_delete=false` khi role chỉ có SELECT và không có grant bổ sung qua PUBLIC/roles khác. Nếu không như mong muốn, kiểm tra role membership, table ownership và các grants khác.

## 8. Thực hành B — IAM service account cho Java Orders API

Ứng dụng Java trên Cloud Run hoặc GKE không nên dùng tài khoản người phát triển. Tạo identity riêng:

~~~bash
gcloud iam service-accounts create orders-api \
  --project=PROJECT_ID \
  --display-name="Orders API database identity"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:orders-api@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.instanceUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:orders-api@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
~~~

Đăng ký **tên rút gọn** làm PostgreSQL IAM database user:

~~~bash
gcloud sql users create "orders-api@PROJECT_ID.iam" \
  --project=PROJECT_ID \
  --instance=orders-pg \
  --type=cloud_iam_service_account
~~~

**Quy tắc tên PostgreSQL IAM:** `orders-api@PROJECT_ID.iam.gserviceaccount.com` → **`orders-api@PROJECT_ID.iam`**. Tên sau khi rút gọn phải không quá **63 ký tự**. User account con người vẫn dùng full email như `dev@example.com`.

Cấp SQL quyền tối thiểu, ví dụ Orders API **chỉ đọc** các order đã được tạo:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_reader;
GRANT USAGE ON SCHEMA public TO orders_reader;
GRANT SELECT ON public.orders TO orders_reader;
GRANT orders_reader TO "orders-api@PROJECT_ID.iam";
~~~

Đối với một Orders API thực sự ghi dữ liệu, cần role riêng như `orders_writer` với quyền `INSERT/UPDATE` đúng bảng, không cấp toàn quyền vì tiện. **Runtime service account phải được gắn vào Cloud Run revision hoặc KSA/GSA mapping của GKE** theo mô hình quản lý của tổ chức; tạo account trong IAM **không tự gắn** vào workload.

### 8.1. Java JDBC dùng Cloud SQL Java Connector và ADC

Trong Maven project, thêm dependencies phiên bản **được khóa và tương thích** cho:

- `com.google.cloud.sql:postgres-socket-factory` (Cloud SQL Java Connector).
- `org.postgresql:postgresql` (PostgreSQL JDBC).
- `com.zaxxer:HikariCP` nếu dùng connection pooling.

Ví dụ Java 17 đơn giản kiểm tra IAM login bằng JDBC; các biến môi trường là **configuration, không chứa token hay password**:

~~~java
package com.example.orders;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Properties;

public final class DatabaseCheck {
    public static void main(String[] args) throws SQLException {
        String instance = System.getenv("INSTANCE_CONNECTION_NAME");
        String database = System.getenv("DB_NAME");
        String iamUser = System.getenv("DB_IAM_USER");
        if (instance == null || database == null || iamUser == null) {
            throw new IllegalArgumentException("Missing database configuration");
        }

        Properties p = new Properties();
        p.setProperty("socketFactory",
                "com.google.cloud.sql.postgres.SocketFactory");
        p.setProperty("cloudSqlInstance", instance);
        p.setProperty("enableIamAuth", "true");
        p.setProperty("user", iamUser);
        p.setProperty("password", "ignored-by-IAM-connector");
        p.setProperty("sslmode", "disable");
        p.setProperty("ipTypes", "PRIVATE");
        p.setProperty("cloudSqlRefreshStrategy", "lazy");

        try (Connection c = DriverManager.getConnection(
                     "jdbc:postgresql:///" + database, p);
             Statement stmt = c.createStatement();
             ResultSet rows = stmt.executeQuery(
                     "SELECT current_user, current_database()")) {
            if (rows.next()) {
                System.out.println("Database user=" + rows.getString(1)
                        + ", database=" + rows.getString(2));
            }
        }
    }
}
~~~

Giải thích các trường dễ nhầm:

- `enableIamAuth=true`: Java connector tự lấy IAM login token qua **ADC** của runtime identity.
- `user`: **database IAM username rút gọn**, ở ví dụ là `orders-api@PROJECT_ID.iam`.
- `password`: **giá trị giả không có hiệu lực** khi automatic IAM auth, chỉ để PostgreSQL JDBC driver vượt kiểm tra nonempty password; **không phải secret thật**.
- `sslmode=disable` áp cho **PostgreSQL JDBC driver**, vì **Cloud SQL Java Connector tự quản lý encrypted connection tới instance**. Không sao chép cấu hình này sang **direct IP connection** không dùng connector.
- `ipTypes=PRIVATE`: chỉ dùng nếu workload có đường VPC/private IP đến Cloud SQL. Connector **không tự dựng đường mạng**.
- `cloudSqlRefreshStrategy=lazy` thích hợp một số serverless workloads nhằm giảm background refresh.

Để dùng thật, thêm **HikariCP** với giới hạn connection pool, statement timeouts, secrets quản lý đúng chính sách và monitoring. **Không mở một database connection mới cho mỗi HTTP request**; IAM login có quota theo instance và việc tạo connection liên tục làm tăng độ trễ/áp lực DB.

### 8.2. Cloud SQL connector khác Cloud Run “connection attachment”

Cloud Run có cách tích hợp Cloud SQL qua cấu hình service/instance connection. Nếu dùng **Java JDBC Socket Factory**, ứng dụng tự thực hiện connector flow; nếu dùng **Cloud SQL Auth Proxy**, một local proxy làm phần transport/auth. Đừng chạy **nhiều lớp connector chồng nhau** khi không cần thiết; chọn một topology, kiểm tra IAM và network theo cách đó.

## 9. Thực hành C — IAM database authentication trên AlloyDB

AlloyDB for PostgreSQL là dịch vụ riêng: **user thêm ở cluster, flags cấu hình theo instance**, role IAM và Auth Proxy khác Cloud SQL.

| Giá trị lab | Ví dụ |
|---|---|
| Region | `asia-southeast1` |
| AlloyDB cluster | `orders-alloy-cluster` |
| Primary instance | `orders-primary` |
| Database | `orders` |
| IAM principal | `dev@example.com` hoặc dedicated runtime SA |
| Cluster user type | `IAM_BASED` hoặc `IAM_GROUP` |
| Auth Proxy binary | `alloydb-auth-proxy` |

### 9.1. Kiểm tra flags trước khi bật

~~~bash
gcloud alloydb clusters describe orders-alloy-cluster \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud alloydb instances describe orders-primary \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1

gcloud alloydb users list \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1
~~~

Bật flag `alloydb.iam_authentication=on` cho **instance**. Nếu dùng IAM groups, bật **cả hai**:

~~~text
alloydb.iam_authentication=on
alloydb.iam_group_authentication=on
~~~

**Không sửa bằng cách thay toàn bộ flags đang có:** `gcloud alloydb instances update --database-flags=...` có thể **reset mọi flag không liệt kê**. Hãy sao lưu flags, giữ nguyên những cấu hình khác, cân nhắc maintenance/restart và không dùng `--update-mode=FORCE_APPLY` trên production nếu không có lý do kiểm soát. IAM authentication của AlloyDB mặc định **tắt** trên instances theo tài liệu hiện hành.

### 9.2. Cấp AlloyDB IAM roles và tạo database user

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/alloydb.databaseUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/alloydb.client"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="user:dev@example.com" \
  --role="roles/serviceusage.serviceUsageConsumer"

gcloud alloydb users create dev@example.com \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1 \
  --type=IAM_BASED
~~~

Những lệnh này tạo **login permission**, chưa cấp quyền SQL đọc bảng. DBA cần chạy PostgreSQL `GRANT` trong database `orders`, tương tự mục 7:

~~~sql
GRANT CONNECT ON DATABASE orders TO orders_reader;
GRANT USAGE ON SCHEMA public TO orders_reader;
GRANT SELECT ON public.orders TO orders_reader;
GRANT orders_reader TO "dev@example.com";
~~~

### 9.3. Automatic IAM auth qua AlloyDB Auth Proxy

~~~bash
# Cần kết nối mạng/VPC/PSC phù hợp và binary alloydb-auth-proxy.
alloydb-auth-proxy --auto-iam-authn \
  projects/PROJECT_ID/locations/asia-southeast1/clusters/orders-alloy-cluster/instances/orders-primary

# Terminal khác, khi ADC đang là chính dev@example.com:
psql -h 127.0.0.1 -p 5432 -U "dev@example.com" --dbname=orders
~~~

AlloyDB Auth Proxy dùng **instance URI** khác với Cloud SQL connection name. Truy cập network/private IP/PSC phải được thiết kế đúng. Với cách thao tác nhanh từ gcloud CLI:

~~~bash
# CLI beta/Preview: dùng để thử thủ công, kiểm tra trạng thái hiện hành.
gcloud beta alloydb connect orders-primary \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1 \
  --auto-iam-authn
~~~

Lệnh này cần `psql` và connectivity tương ứng. Nó **không** tạo cluster hoặc VPC tunnel vô điều kiện; principal gcloud đang dùng phải trùng IAM database user hoặc dùng impersonation được ủy quyền.

### 9.4. Khác biệt nếu là Java workload

- Dùng **AlloyDB Auth Proxy** hoặc **AlloyDB Language Connector** hỗ trợ automatic IAM auth, **không dùng Cloud SQL Socket Factory** trỏ sang AlloyDB.
- Runtime service account cần `roles/alloydb.databaseUser`, `roles/alloydb.client` và `roles/serviceusage.serviceUsageConsumer` theo phương án kết nối.
- Tạo database user ở **cluster** với tên rút gọn: `orders-api@PROJECT_ID.iam` nếu là SA.
- PostgreSQL `GRANT` phải thực thi trong database đích.
- Chú ý **quota login theo phút** của AlloyDB instance và pool sizing; tránh scale serverless gây bão kết nối.

## 10. IAM group authentication: cấp quyền theo đội

### 10.1. Cloud SQL IAM group

Nếu nhóm `db-analysts@example.com` dùng Cloud SQL PostgreSQL:

~~~bash
# Nhóm Cloud Identity phải tồn tại trước.
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/cloudsql.instanceUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/cloudsql.client"

gcloud sql users create db-analysts@example.com \
  --project=PROJECT_ID \
  --instance=orders-pg \
  --type=cloud_iam_group
~~~

DBA cấp quyền SQL cho **group database role**:

~~~sql
GRANT CONNECT ON DATABASE orders TO "db-analysts@example.com";
GRANT USAGE ON SCHEMA public TO "db-analysts@example.com";
GRANT SELECT ON public.orders TO "db-analysts@example.com";
~~~

Thành viên đăng nhập với **IAM identity cá nhân**, không dùng mật khẩu chung của group. Cloud SQL tạo database account tương ứng sau lần đăng nhập đầu tiên. Khi thay đổi Cloud Identity group membership, thời gian propagation có thể khoảng **15 phút hoặc hơn**, chưa tính IAM propagation.

**Migration trap:** một người đã tồn tại dạng `CLOUD_IAM_USER` hoặc `CLOUD_IAM_SERVICE_ACCOUNT` **không tự kế thừa SQL grants từ group**. Muốn chuyển sang IAM group, phải lên kế hoạch **thu hồi/xóa individual DB account và tạo lại qua group**, đặc biệt nếu account sở hữu objects/privileges đang hoạt động; không xóa trong production khi chưa chuyển ownership.

### 10.2. AlloyDB IAM group

Ngoài bật cả hai database flags, gán roles cho **group**, rồi tạo group user ở cluster:

~~~bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/alloydb.databaseUser"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/serviceusage.serviceUsageConsumer"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:db-analysts@example.com" \
  --role="roles/alloydb.client"

gcloud alloydb users create db-analysts@example.com \
  --project=PROJECT_ID \
  --cluster=orders-alloy-cluster \
  --region=asia-southeast1 \
  --type=IAM_GROUP
~~~

Tiếp tục `GRANT` SQL cho `"db-analysts@example.com"`. Group members vẫn đăng nhập bằng account riêng.

**Lưu ý giới hạn hiện hành:** AlloyDB hỗ trợ tối đa **200 IAM groups mỗi cluster** và usernames PostgreSQL tối đa 63 ký tự. **AlloyDB IAM group authentication không tương thích với managed connection pooling/PgBouncer** theo tài liệu hiện hành; đừng áp cấu hình pooling group users mà chưa kiểm tra hỗ trợ. Group members được thêm/xóa có thể cần thời gian đồng bộ.

### 10.3. Group authentication có thay database roles không?

**Không.** IAM/Cloud Identity group là cách quản lý **ai có thể đăng nhập**, còn PostgreSQL SQL GRANT quyết định **được làm gì**. Việc nhóm được cấp `roles/alloydb.databaseUser` hoặc `roles/cloudsql.instanceUser` **không cho tất cả members quyền đọc bảng** nếu chưa GRANT phù hợp.

## 11. Quy tắc tên database user và engine differences

| Principal | Cloud SQL PostgreSQL / AlloyDB PostgreSQL | Cloud SQL MySQL |
|---|---|---|
| User `dev@example.com` | `dev@example.com` | Username nội bộ `dev` (bỏ `@example.com`) |
| SA `orders-api@PROJECT_ID.iam.gserviceaccount.com` | `orders-api@PROJECT_ID.iam` | Username nội bộ `orders-api` |
| Tên user tối đa | **63 ký tự** trong PostgreSQL identifier | **32 ký tự** trong MySQL username |
| Đăng nhập | Email đầy đủ với human; SA rút `.gserviceaccount.com` | Dùng tên rút gọn theo engine/cloud connector |
| Database grants | `GRANT ... TO "name@domain"` | `GRANT ... TO 'name'@'host'` theo user/host thực |

**MySQL giới hạn quan trọng:** hai human emails `dev@company-a.com` và `dev@company-b.com` có thể cùng bị rút thành username `dev`, nên không thể dùng cả hai trên một instance theo cách IAM MySQL này. DBA phải thiết kế namespace account có tránh xung đột. **Không sao chép nguyên PostgreSQL GRANT sang MySQL** — các cú pháp role, grants và host semantics khác nhau.

### 11.1. Cloud SQL MySQL chỉ cần nắm các khác biệt thực hành

- IAM flag là `cloudsql_iam_authentication=on` (không phải `cloudsql.iam_authentication`).
- Đăng nhập IAM vẫn cần `roles/cloudsql.instanceUser`; dùng proxy/connector cần thêm `roles/cloudsql.client`.
- Thêm IAM user/service account/group ở instance; cấp quyền bằng MySQL `GRANT`.
- IAM accounts dùng username lowercase; giới hạn MySQL username **32 ký tự**, không cho phép hai IAM emails tạo cùng tên nội bộ.
- MySQL 5.6 **không hỗ trợ IAM database authentication**; kiểm tra engine/version thực tế.

## 12. Security, auditing và vòng đời người dùng

### 12.1. Onboarding

1. Xác định principal: developer, BI analyst, Java runtime hoặc CI migration.
2. Chọn **human individual, IAM group hoặc user-managed service account**; không dùng mặc định Editor.
3. Cấp đúng **IAM database login + connector role** ở project/resources.
4. Tạo IAM DB account trên **Cloud SQL instance** hoặc **AlloyDB cluster**.
5. Cấp **database role** và `GRANT` tối thiểu vào database/schema/tables cần thiết.
6. Kiểm tra connection path (private IP/PSC, proxy/TLS) và login bằng đúng principal.
7. Chạy positive/negative SQL privilege tests trên dữ liệu thử.
8. Ghi owner, purpose, review date và audit evidence.

### 12.2. Offboarding

**Thu hồi IAM login** giúp ngăn sign-in mới sau khi quyền có hiệu lực, nhưng **không xem đó là cơ chế lập tức hủy mọi kết nối hiện có**. Đối với sự cố bảo mật:

1. Thu hồi IAM role hoặc group membership.
2. Kiểm tra sessions đang tồn tại, chấm dứt sessions theo change/incident plan nếu cần.
3. Thu hồi SQL grants/role membership và xử lý ownership phụ thuộc.
4. Xóa DB account/group object nếu đúng kế hoạch, **không xóa dữ liệu/role owner bất cẩn**.
5. Thu hồi runtime SA hoặc redeploy workload mới nếu identity bị compromise.
6. Audit truy cập và xác minh user không thể login/query lại.

**IAM group propagation có độ trễ**. Với tình huống thu hồi khẩn cấp, không chỉ chờ group sync rồi kết luận đã an toàn; cần lớp chặn network/revoke/terminate DB sessions phù hợp.

### 12.3. Audit

- Google Cloud Audit Logs ghi nhận hoạt động quản trị/IAM; **Data Access logs** cần cấu hình theo sản phẩm để có thông tin đăng nhập/truy cập, lưu ý nhiều loại bị tắt mặc định.
- PostgreSQL/MySQL engine logs và database audit extensions có thể cung cấp chi tiết đăng nhập/query theo cấu hình.
- Không giả định IAM audit logs tự chứa **mọi SQL statement và dữ liệu hàng**.
- Không log OAuth tokens, credentials, full query chứa PII, database dumps hoặc secrets vào application logs.
- Theo dõi IAM policy changes, DB account creation/deletion, role grants, failed logins, session spikes và query permission-denied.

### 12.4. Kết nối, HA và chi phí

- Không dùng mỗi HTTP request tạo một kết nối database mới: dùng HikariCP/connection pool phù hợp concurrency Cloud Run/GKE.
- Token IAM có hạn khoảng 1 giờ, connector tự refresh cho **kết nối mới**; một connection hiện tại không nên bị đóng đơn giản chỉ vì token lúc tạo đã hết hạn.
- IAM database login có quota theo instance; connection storms có thể dẫn đến xác thực thất bại ngay cả khi SQL server còn CPU.
- Failover/read replica có thể có cấu hình authentication riêng; **Cloud SQL read replicas không tự kế thừa bật IAM auth từ primary trong mọi trường hợp** — kiểm tra flag trên replica.
- Proxy/connector không miễn phí về mặt mạng/CPU vận hành của client; database instance/AlloyDB storage, egress, Cloud Logging/Monitoring vẫn có phí theo sử dụng.
- Khi dùng **Workload Identity Federation for GKE**, phân biệt Kubernetes ServiceAccount mapping và database IAM username; không copy email của KSA thành PostgreSQL user trừ khi nó được xác định là principal đăng nhập.

## 13. Chẩn đoán: lỗi IAM, lỗi SQL hay lỗi network?

| Lỗi / dấu hiệu | Khả năng nguyên nhân | Kiểm tra |
|---|---|---|
| Proxy lỗi `403 PERMISSION_DENIED` | Thiếu `roles/cloudsql.client` hoặc `roles/alloydb.client`; sai identity | ADC/runtime SA, project/instance IAM |
| Database báo login/authentication failed | IAM flag tắt, user chưa tạo, thiếu InstanceUser/DatabaseUser | Flags, IAM role và DB users |
| Cloud SQL login IAM thành công nhưng `permission denied for table` | Thiếu SQL `GRANT`/schema USAGE | PostgreSQL `\dp`, role membership/ownership |
| AlloyDB login 403 | Thiếu DatabaseUser, ServiceUsageConsumer, Client | IAM/connector logs, cluster user |
| `psql` không kết nối được, timeout | Không có VPC route/private IP/PSC, proxy không chạy | Local listener, firewall, 443/3307/5433, network path |
| Java app báo user/password mismatch | Connector dùng ADC khác DB username | Runtime SA, `DB_IAM_USER` |
| Token hết hạn khi pool tạo connection mới | Manual IAM token tĩnh | Chuyển sang automatic IAM auth/refresh |
| IAM group member không có grants | Individual DB account tồn tại hoặc membership chưa sync | User type, group/DB grants, propagation |
| PostgreSQL role name bị cắt | IAM SA rút gọn vẫn vượt 63 ký tự | Tên ngắn hơn hoặc impersonation phù hợp |
| Cloud SQL MySQL user trùng | Bỏ domain khiến hai email có cùng local username | Thiết kế lại IAM principals/naming |
| Người đã offboard vẫn có session | Revoke chỉ ảnh hưởng login mới, connection hiện tại còn | DB sessions, thu hồi SQL/network, terminate hợp lệ |
| Java mở quá nhiều connections | Hikari pool quá lớn, Cloud Run scale cao | DB connection count, instance max, auth quota |
| Cloud SQL IAM auth lỗi trên read replica | Replica flag chưa bật | Describe replica flags |
| AlloyDB group qua managed pool không hoạt động | Unsupported group + managed pooling theo docs | Dùng kết nối hỗ trợ hoặc phương án cá nhân |
| Context-Aware Access làm connector auth fail | Cơ chế connector không tương thích IAM DB auth theo policy | Kiểm tra policy và direct connection được hỗ trợ |

### 13.1. Quy trình 6 bước tránh cấp quyền quá rộng

1. **Xác nhận principal**: `gcloud auth list` chưa đủ, phải kiểm tra **ADC/runtime identity**.
2. **Xác nhận tài nguyên**: đúng project, Cloud SQL connection name hoặc AlloyDB instance URI, region, database.
3. **Xác nhận mạng**: VPC/private IP/PSC, proxy listener, TLS và egress.
4. **Xác nhận Google IAM**: quyền **login** và quyền **connect** khác nhau, group propagation/role bindings.
5. **Xác nhận DB account/SQL grants**: user tồn tại, tên rút gọn đúng, `GRANT` vào schema/table chính xác.
6. **Thử lại bằng read-only query** và kiểm tra audit/metrics; không dùng `Owner` để thử.

### 13.2. Các truy vấn đọc role/privileges

~~~sql
-- PostgreSQL, chạy bởi principal có quyền kiểm tra catalog:
SELECT current_user, session_user;

SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
FROM pg_roles
WHERE rolname LIKE '%orders%' OR rolname LIKE '%example.com%';

SELECT has_database_privilege(current_user, 'orders', 'CONNECT') AS can_connect;
SELECT has_schema_privilege(current_user, 'public', 'USAGE') AS can_use_schema;
SELECT has_table_privilege(current_user, 'public.orders', 'SELECT') AS can_select;
~~~

Đừng dùng câu lệnh test `DELETE` trên bảng production để xác nhận “không được xóa”. Các query `has_*_privilege` giúp kiểm tra mà không sửa dữ liệu.

## 14. Case study: bán lẻ với Orders API và Analytics

**Bối cảnh giả định:** doanh nghiệp có `orders-api` chạy trên Cloud Run, `billing-worker` chạy GKE và nhóm phân tích đọc báo cáo. Orders và Billing truy cập Cloud SQL PostgreSQL; nhóm phân tích sau đó chuyển một số workloads sang AlloyDB để tăng throughput.

### 14.1. Phân tách danh tính

| Thành phần | IAM principal | Database role |
|---|---|---|
| Orders API Cloud Run | `orders-api@PROJECT_ID.iam.gserviceaccount.com` | `orders_writer` trên đúng bảng Orders |
| Billing Worker GKE | `billing-worker@PROJECT_ID.iam.gserviceaccount.com` | `billing_reader`, `billing_writer` theo nghiệp vụ |
| Nhóm phân tích | Cloud Identity `db-analysts@example.com` | `orders_reader` hoặc read-only views |
| DBA/migration CI | Identity riêng có quyền nâng cấp/schema có kiểm soát | DDL role, không dùng trong HTTP runtime |
| Monitoring | Identity chuyên đọc metric/logs | Không cần login DB nếu chỉ xem Cloud Monitoring |

### 14.2. Đường xử lý an toàn

~~~mermaid
flowchart LR
    HTTP["Client HTTP"] --> Run["Cloud Run Orders API"]
    SA1["Orders runtime SA"] -. "IAM login + connect" .-> Run
    Run --> Connector["Cloud SQL Java Connector"]
    Connector --> DB["Cloud SQL PostgreSQL"]
    DB --> SQLRole["orders_writer<br/>only required GRANT"]
    Group["Analyst Cloud Identity group"] --> Proxy["Cloud SQL / AlloyDB Proxy"]
    Proxy --> Read["read-only views"]
~~~

Quy tắc triển khai:

1. Mỗi workload có **service account riêng**, không dùng account của developer hoặc Editor mặc định.
2. Gắn runtime identity vào Cloud Run/GKE, cấp IAM login/connect, tạo DB user và SQL role tương ứng.
3. Java dùng **automatic IAM auth + connection pool**, không lưu password/token tĩnh.
4. Người phân tích vào **IAM group**, SQL grants chỉ trên views/schema báo cáo.
5. Không dùng chung credential ghi dữ liệu giữa Java runtime và BI.
6. Offboarding group membership và runtime SA theo change control; kiểm tra kết nối đang mở.
7. Thu thập audit IAM + DB logs, định kỳ rà soát grants, login failures và chi phí.

### 14.3. Sự cố “có IAM mà vẫn không đọc được bảng”

Sau khi cấp `roles/cloudsql.instanceUser` và `roles/cloudsql.client` cho `orders-api`, Cloud Run kết nối được nhưng SQL query trả `permission denied for table orders`.

**Chẩn đoán:** IAM đã mở cổng đăng nhập/kết nối; database account chưa được cấp `USAGE` trên schema hoặc `SELECT` trên bảng qua SQL role. Sửa bằng `GRANT` đúng bảng, **không** cấp `roles/cloudsql.admin` hoặc dùng account `postgres` cho HTTP application.

### 14.4. Bằng chứng vận hành

| Câu hỏi | Bằng chứng |
|---|---|
| Java chạy bằng identity nào? | Cloud Run revision/GKE workload SA |
| IAM principal được login/connect? | Project IAM bindings/role permissions |
| User/group đã được đăng ký DB? | Cloud SQL users list / AlloyDB users list |
| Được SELECT/INSERT trên đối tượng nào? | `pg_roles`, `\dp`, `has_table_privilege` |
| Token có được tự refresh? | Connector config, auth failures, pool metrics |
| Analyst nghỉ việc còn đăng nhập được? | Group membership, sessions và login test |
| DB cost phù hợp? | Connection count, CPU, storage, billing, logs |

## 15. Bài tập và tự đánh giá

### Bài 1 — Hai lớp IAM và SQL

Java SA có `roles/cloudsql.instanceUser` và `roles/cloudsql.client`, được thêm vào PostgreSQL instance nhưng query `SELECT * FROM orders` trả `permission denied`.

**Hỏi:** thêm `roles/cloudsql.admin` có giải quyết đúng nguyên nhân không? Cần thay đổi gì?

**Gợi ý:** không; cấp SQL `CONNECT/USAGE/SELECT` trên đúng database/schema/table hoặc role.

### Bài 2 — Automatic vs manual

Một Java service giữ access token trong biến môi trường và không refresh trong 24 giờ. Sau hơn một giờ, pool tạo connection mới bị authentication failure.

**Hỏi:** vì sao? Đề xuất chuyển đổi sang cơ chế nào?

**Gợi ý:** token IAM ngắn hạn; dùng Cloud SQL/AlloyDB connector với automatic IAM auth.

### Bài 3 — Tên service account PostgreSQL

Service account là `orders-api@retail-prod.iam.gserviceaccount.com`. **Tên IAM database user trong PostgreSQL nên là gì?** Giới hạn độ dài nào áp dụng?

**Gợi ý:** `orders-api@retail-prod.iam`; tối đa 63 ký tự.

### Bài 4 — MySQL khác PostgreSQL

Cloud SQL MySQL có hai IAM users `dev@team-a.example` và `dev@team-b.example`.

**Hỏi:** việc MySQL bỏ domain tạo vấn đề gì? Flag MySQL IAM có viết giống PostgreSQL không?

**Gợi ý:** trùng local username `dev`; flag MySQL dùng gạch dưới `cloudsql_iam_authentication`.

### Bài 5 — AlloyDB roles

Một người được cấp `roles/alloydb.databaseUser` nhưng kết nối AlloyDB Auth Proxy bị 403.

**Hỏi:** cần kiểm tra thêm IAM roles nào, database user/flag nào và thành phần mạng nào?

**Gợi ý:** `roles/alloydb.client`, `serviceusage.serviceUsageConsumer`, instance flags, user ở cluster, VPC/PSC.

### Bài 6 — Group không kế thừa grants

`dev@example.com` đã là individual IAM DB user; DBA thêm `db-analysts@example.com` group và GRANT SELECT cho group. Developer vẫn không hưởng quyền.

**Hỏi:** tại sao? Thiết kế migration an toàn ra sao?

**Gợi ý:** individual IAM account không tự dùng group grants; lập kế hoạch thay DB account type và ownership, không xóa bừa production.

### Bài 7 — Database flags

Một kỹ sư chạy `gcloud sql instances patch ... --database-flags=cloudsql.iam_authentication=on` trên instance đã có nhiều flags.

**Hỏi:** rủi ro là gì? Cần làm gì trước khi chạy?

**Gợi ý:** có thể reset flags không liệt kê; lấy trạng thái hiện tại, giữ danh sách flags và review change impact.

### Bài 8 — Cloud Run dùng sai ADC

Developer có thể `psql` bằng `dev@example.com` trên laptop, nhưng Cloud Run runtime gắn SA `orders-api`. Java connection config đặt `DB_IAM_USER=dev@example.com` và nhận authentication failed.

**Hỏi:** sửa config theo principal nào? Cần tạo DB user/SQL role nào?

**Gợi ý:** IAM DB user của runtime SA, không phải người deploy; grants tương ứng.

### Bài 9 — Offboarding

Một nhân viên bị xóa khỏi IAM group nhưng vẫn có kết nối PostgreSQL đang mở.

**Hỏi:** vì sao chỉ xóa group membership chưa chắc chặn ngay mọi truy cập? Nêu các bước ứng cứu.

**Gợi ý:** group propagation và DB sessions hiện tại; kiểm tra IAM, revoke SQL, terminate sessions theo quy trình.

### Bài 10 — Thiết kế bảo mật hệ thống

Thiết kế IAM database authentication cho Java Orders API, Billing Worker và nhóm BI, với **Cloud SQL PostgreSQL** và tùy chọn chuyển sang **AlloyDB**. Đề xuất:

- IAM roles và loại principal;
- user/group tạo ở instance hay cluster;
- SQL GRANT theo domain;
- connector/network/TLS;
- pooling, token refresh, group propagation;
- logging/audit, runbook thu hồi và chi phí.

**Gợi ý:** tách Cloud IAM resource access khỏi PostgreSQL SQL privileges; không dùng một admin identity cho mọi workload.

## 16. Checklist đưa vào production

- [ ] Xác định engine: Cloud SQL PostgreSQL/MySQL hay AlloyDB PostgreSQL; không gán IAM DB auth cho Cloud SQL SQL Server.
- [ ] Đã phân biệt IAM login/connect, network, DB account và SQL privileges.
- [ ] Đã bật đúng IAM database flag của **từng engine/instance**, giữ nguyên flags khác.
- [ ] IAM users/service accounts/group được đăng ký ở **Cloud SQL instance** hoặc **AlloyDB cluster**.
- [ ] Cloud SQL identity có `roles/cloudsql.instanceUser`, connector có `roles/cloudsql.client`.
- [ ] AlloyDB identity có `roles/alloydb.databaseUser`, connector có `roles/alloydb.client` và Service Usage Consumer khi cần.
- [ ] SQL roles được tạo rõ, chỉ GRANT database/schema/table cần thiết; kiểm tra PUBLIC grants.
- [ ] Java runtime SA riêng cho từng workload, không dùng Developer/Owner/Editor mặc định.
- [ ] Automatic IAM authentication qua connector/proxy; không lưu access token/password hoặc JSON key trong source.
- [ ] Đã kiểm tra **principal chạy connector** trùng database IAM user, kể cả impersonation nếu dùng.
- [ ] Đường mạng private IP/PSC, firewall, TLS và connector egress phù hợp.
- [ ] PostgreSQL SA username rút gọn đúng và dài không quá 63 ký tự; MySQL tránh trùng username sau bỏ domain.
- [ ] IAM group được chọn phù hợp, xử lý migration individual account và propagation.
- [ ] Không bật AlloyDB IAM group auth cùng managed pool không hỗ trợ.
- [ ] HikariCP/connection pooling được sizing theo Cloud Run/GKE concurrency và quota database sign-ins.
- [ ] Offboarding thu hồi IAM/SQL và quản lý **sessions còn sống**, không chỉ xóa group membership.
- [ ] Có audit IAM, database logs, cảnh báo login fail, quota/connection storm và thay đổi grants.
- [ ] Backup/HA/replicas, rollback IAM flags và chi phí được đánh giá trước khi thay config.
- [ ] Đã diễn tập positive/negative permissions trong sandbox, không chạy DELETE test trên dữ liệu thật.

## 17. Tài liệu chính thức

Các giới hạn, flags, connector versions và nhóm IAM có thể thay đổi. Đối chiếu tài liệu trước khi thực hiện:

- [Cloud SQL PostgreSQL — IAM authentication](https://docs.cloud.google.com/sql/docs/postgres/iam-authentication)
- [Cloud SQL PostgreSQL — Configure IAM-enabled instances](https://docs.cloud.google.com/sql/docs/postgres/create-edit-iam-instances)
- [Cloud SQL PostgreSQL — Add/manage IAM users and groups](https://docs.cloud.google.com/sql/docs/postgres/add-manage-iam-users)
- [Cloud SQL PostgreSQL — IAM login and automatic auth](https://docs.cloud.google.com/sql/docs/postgres/iam-logins)
- [Cloud SQL PostgreSQL — Cloud SQL Language Connectors](https://docs.cloud.google.com/sql/docs/postgres/connect-connectors)
- [Cloud SQL MySQL — IAM database authentication](https://docs.cloud.google.com/sql/docs/mysql/iam-authentication)
- [Cloud SQL MySQL — Manage IAM users](https://docs.cloud.google.com/sql/docs/mysql/add-manage-iam-users)
- [AlloyDB — IAM database authentication overview](https://docs.cloud.google.com/alloydb/docs/database-users/iam-authentication)
- [AlloyDB — Manage IAM authentication](https://docs.cloud.google.com/alloydb/docs/database-users/manage-iam-auth)
- [AlloyDB — Connect using IAM](https://docs.cloud.google.com/alloydb/docs/connect-iam)
- [AlloyDB — Auth Proxy](https://docs.cloud.google.com/alloydb/docs/auth-proxy/connect)
- [AlloyDB — IAM roles and permissions](https://docs.cloud.google.com/alloydb/docs/reference/iam-roles-permissions)
- [AlloyDB — Database flags](https://docs.cloud.google.com/alloydb/docs/instance-configure-database-flags)
- [AlloyDB — Connect using gcloud CLI (Preview)](https://docs.cloud.google.com/alloydb/docs/connect-gcloud)
- [Cloud SQL JDBC Socket Factory — IAM auth](https://github.com/GoogleCloudPlatform/cloud-sql-jdbc-socket-factory/blob/main/docs/jdbc.md)
- [PostgreSQL — GRANT](https://www.postgresql.org/docs/current/sql-grant.html)
- [PostgreSQL — Default privileges](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)

**Điểm cần nhớ:** **IAM database authentication xác thực danh tính để đăng nhập database; `GRANT`/`REVOKE` trong PostgreSQL/MySQL mới quyết định được đọc hay ghi dữ liệu nào.** Cloud SQL và AlloyDB khác nhau ở flags, roles và phạm vi tạo users; **automatic IAM auth qua connector** giúp Java dùng token ngắn hạn mà không giữ secrets cố định. Thiết kế an toàn kết hợp **runtime service identity riêng, least-privilege SQL roles, VPC/TLS, connection pooling, IAM groups có quản trị lifecycle và audit end-to-end**.
