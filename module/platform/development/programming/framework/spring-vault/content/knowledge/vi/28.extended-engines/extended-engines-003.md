# Phân biệt database role động với thông tin tài khoản tĩnh trong HashiCorp Vault

> **Chương:** Engine mở rộng  
> **Bài học:** Phân biệt database role động với thông tin tài khoản tĩnh  
> **Bối cảnh:** `SPRING_VAULT` dùng Spring Vault và `VaultTemplate` để ứng dụng Java truy cập HashiCorp Vault bằng danh tính workload, Vault ACL policy và quy trình quản lý vòng đời token/lease. Bài này tập trung vào **Database Secrets Engine**: hai cách cấp thông tin đăng nhập database là **dynamic role** và **static role**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích quan hệ giữa Vault database connection, **Vault role**, **database user/role** và **Vault workload token**.
2. Phân biệt dynamic credentials (tài khoản tạo theo yêu cầu, có **lease**) với static credentials (tài khoản có sẵn, giữ nguyên tên, Vault **xoay vòng mật khẩu**).
3. Chọn đúng API và quyền tối thiểu cho từng loại: `database/creds/<role>` và `database/static-creds/<role>`.
4. Tạo ví dụ PostgreSQL, quan sát lease/TTL, thực hiện renew/revoke hoặc rotate và xác minh tác động lên database.
5. Tích hợp bằng Java `VaultTemplate`, đánh giá cách kết nối JDBC/DataSource ứng xử khi credential thay đổi.
6. Thiết kế kiểm thử tích hợp, giám sát lỗi và quy trình đổi mật khẩu không làm ứng dụng mất kết nối ngoài dự kiến.

## 2. Bức tranh tổng thể: Vault role không đồng nghĩa database user

HashiCorp Vault Database Secrets Engine (mount thường là `database/`) kết nối tới database bằng một tài khoản quản lý được cấp quyền phù hợp. Vault có **role cấu hình** quy định cách tạo/tái sử dụng danh tính database và chính sách thời gian sống của credential.

```mermaid
flowchart TB
    APP["Java workload<br/>Vault token + ACL"] --> VAULT["Vault Database Secrets Engine"]
    VAULT --> CFG["database/config/orders-pg<br/>PostgreSQL connection"]
    CFG --> PG[("PostgreSQL")]
    VAULT --> DROLE["Dynamic Vault role<br/>database/roles/orders-readonly"]
    VAULT --> SROLE["Static Vault role<br/>database/static-roles/orders-app"]
    DROLE --> DCREDS["database/creds/orders-readonly<br/>Mỗi request tạo một DB user"]
    SROLE --> SCREDS["database/static-creds/orders-app<br/>Đọc password hiện hành của DB user cố định"]
    DCREDS --> PG
    SCREDS --> PG
```

Có **bốn khái niệm dễ bị gọi chung là “role”**:

| Khái niệm | Được quản lý ở đâu? | Chức năng |
| --- | --- | --- |
| **Vault token / workload identity** | Auth method của Vault (Kubernetes Auth, AppRole, v.v.) | Quyết định ứng dụng có quyền gọi API lấy credential hay không |
| **Vault dynamic role** | `database/roles/<name>` | Mẫu tạo user database mới, TTL và SQL cấp quyền khi tạo |
| **Vault static role** | `database/static-roles/<name>` | Gắn một Vault role với **một database username có sẵn** để Vault quản lý/rotate mật khẩu |
| **Database role/user** | PostgreSQL/MySQL/... | Danh tính đăng nhập trực tiếp database, với quyền SQL thực tế |

Vault ACL `read` trên một endpoint cấp credential **không tự tạo** quyền truy vấn SQL. Quyền SQL được định nghĩa bởi SQL grant/role của database. Ngược lại, database account đã được cấp `SELECT` cũng không có khả năng đọc một Vault secret nếu workload token thiếu ACL.

Trong bài dùng:
- Database connection: `orders-pg`.
- Dynamic Vault role: `orders-readonly` → mỗi lần lấy credential tạo một DB user riêng có quyền đọc.
- Static Vault role: `orders-app` → Vault quản lý password của DB user PostgreSQL tên `orders_app`.

## 3. So sánh dynamic role và static role

| Tiêu chí | Dynamic role | Static role |
| --- | --- | --- |
| Bản chất | Mẫu sinh **credential mới theo yêu cầu** | Gắn **một Vault role** với **một DB account cố định** |
| DB username | Thường được Vault tạo mới mỗi lần request | Giữ nguyên, ví dụ `orders_app` |
| DB password | Mới cho từng credential được cấp | Một password hiện hành; đổi khi rotation |
| Điều kiện trước khi dùng | Vault cần quyền tạo/cấp và thu hồi DB user | DB account phải **tồn tại trước**, Vault cần quyền đổi password của account |
| Vault endpoint lấy credential | `GET database/creds/<role>` | `GET database/static-creds/<role>` |
| Thông tin vòng đời trả về | `lease_id`, `lease_duration`, `renewable` trong metadata Vault response | `ttl`, `rotation_period`/`rotation_schedule`, `last_vault_rotation` trong data; **không cấp dynamic lease riêng cho mỗi lần đọc** |
| Hết hạn / thu hồi | Lease expire/revoke → Vault cố thu hồi hoặc vô hiệu DB account tương ứng | Đến lịch → Vault đổi mật khẩu **cùng DB account** |
| Tác động của nhiều client | Mỗi lần cấp có thể là user riêng → dễ quy về instance/lease | Các client đọc cùng static role chia sẻ một database username |
| Xoay vòng | Cấp credential mới, quản lý lease cũ và chuyển kết nối | Rotate password qua `rotation_period`, `rotation_schedule`, hoặc `rotate-role` |
| Mức cô lập khi lộ credential | Có thể giới hạn theo instance/lease TTL | Mọi client cùng dùng DB account có thể bị ảnh hưởng |
| Chi phí vận hành | Tăng số user/role DB, cần plugin thực hiện create/revoke ổn định | Ít DB accounts hơn, nhưng password rotation ảnh hưởng mọi nơi dùng account |
| Phù hợp | Ứng dụng cloud-native, job tạm thời, cần danh tính riêng | Hệ thống legacy cần username ổn định, giới hạn tạo DB users, tích hợp cũ |

**Điểm quan trọng nhất:** `ttl` trả về ở `static-creds` là **thời gian còn lại đến lần xoay vòng mật khẩu dự kiến**, không phải TTL của một dynamic lease. Đừng đem giá trị `ttl` này đi gọi `vault lease renew` hoặc `vault lease revoke`. Với dynamic credentials, phải lưu `lease_id` thực sự nếu muốn chủ động renew/revoke.

### 3.1. Hai lần gọi cùng một path sẽ như thế nào?

Giả sử gọi ngay trước khi rotate và không có thay đổi cấu hình:

```text
GET database/creds/orders-readonly
  → user v-orders-abc, password P1, lease L1

GET database/creds/orders-readonly
  → user v-orders-def, password P2, lease L2

GET database/static-creds/orders-app
  → user orders_app, password PS, ttl ~ còn 20h

GET database/static-creds/orders-app
  → user orders_app, password PS, ttl ~ còn 19h59m

[Vault rotate static role orders-app]
GET database/static-creds/orders-app
  → user orders_app, password PS2, ttl ~ 24h
```

Đây là **minh họa**; tên dynamic user/password/lease là giá trị sinh tại runtime, không phải các chuỗi được bảo đảm. Hai lần đọc dynamic path tạo ra **hai credential** và **hai lease** riêng. Hai lần đọc static path trả lại cùng credential hiện hành cho đến khi password được rotate.

## 4. Vòng đời: lease của dynamic và lịch password của static

### 4.1. Dynamic role: credential mang lease

```mermaid
sequenceDiagram
    participant App as Java workload
    participant Vault as Vault
    participant DB as PostgreSQL
    App->>Vault: GET database/creds/orders-readonly
    Vault->>DB: CREATE ROLE + GRANT
    Vault-->>App: DB username, password, lease_id, TTL
    App->>DB: Kết nối bằng credential mới
    opt Được renew và chưa chạm max TTL
        App->>Vault: Renew lease
        Vault-->>App: TTL mới (theo policy)
    end
    App->>Vault: Revoke lease / lease hết hạn
    Vault->>DB: Thu hồi hoặc vô hiệu user
    Note over App,DB: Phải chuyển datasource trước khi credential cũ mất hiệu lực
```

- Lease có `lease_id`, `lease_duration` và cờ `renewable` (có thể khác nhau tùy plugin/config). `default_ttl` và `max_ttl` của Vault dynamic role cùng giới hạn mount/system xác định thời gian tối đa; token phát hành lease hết hạn/revoke cũng có thể dẫn đến thu hồi lease.
- Renew **không có nghĩa credential sống vô hạn**. Khi đến max TTL, cần xin credential mới và chuyển kết nối.
- Revoke lease yêu cầu Vault gọi plugin/SQL để thu hồi quyền của DB user; nếu Vault mất kết nối DB, thu hồi có thể thất bại và cần giám sát đối soát. Không giả định toàn bộ DB user sẽ bị xóa tức thì khi có sự cố kết nối.
- Việc đọc `database/creds/…` liên tục như polling là **không phù hợp**: mỗi lần đọc có thể tạo thêm tài khoản và lease; nên lấy theo nhu cầu có quản lý vòng đời.

### 4.2. Static role: username bền vững, password được xoay vòng

```mermaid
sequenceDiagram
    participant DBA as DBA / Provisioning
    participant Vault as Vault
    participant DB as PostgreSQL
    participant App as Java workload
    DBA->>DB: Tạo sẵn user orders_app
    DBA->>Vault: Cấu hình database/static-roles/orders-app
    Vault->>DB: Rotate password lúc onboarding (mặc định)
    App->>Vault: GET database/static-creds/orders-app
    Vault-->>App: orders_app + password hiện hành + rotation TTL
    App->>DB: Kết nối bằng password đó
    Note over Vault: Đến lịch hoặc rotate-role thủ công
    Vault->>DB: ALTER USER orders_app PASSWORD ...
    App->>Vault: Đọc lại static-creds
    Vault-->>App: Cùng username + password mới
    Note over App,DB: Cập nhật pool; kết nối mới dùng password mới
```

- Static account tồn tại **trước** khi đăng ký với Vault; tạo một static Vault role **không tương đương tạo DB user**.
- **Mặc định** Vault xoay mật khẩu ngay lúc onboarding static role. Điều này có thể khiến các client cũ mất khả năng tạo kết nối mới bằng mật khẩu cũ. Cần phối hợp cutover, hoặc dùng cơ chế trì hoãn/khởi tạo có kiểm soát nếu edition và phiên bản hỗ trợ.
- `rotation_period` là chu kỳ định kỳ; `rotation_schedule` là lịch cron và có thể kèm `rotation_window`. Hai chế độ **không dùng đồng thời**.
- `ttl` của static credential biểu diễn thời gian còn lại đến thời điểm rotate; **không phải lease có thể renew/revoke từng request**.
- Khi xóa định nghĩa static Vault role, user PostgreSQL bên ngoài **không tự bị xóa**; cần quy trình xử lý riêng.
- Đừng lấy account quản lý của Vault trong `database/config/…` rồi đưa vào static role. Việc đổi password account quản lý mà Vault không đồng bộ đúng cách có thể phá vỡ toàn bộ role trong connection đó. Dùng API rotate root riêng khi cần quản lý root credential.

## 5. Tình huống thiết kế thực tế

**Tình huống A — Dịch vụ báo cáo:** mỗi pod `report-worker` chỉ chạy một job và có quyền `SELECT` hạn chế. Muốn truy vết truy cập từng instance, thời gian sống ngắn và thu hồi khi job kết thúc. → **Dynamic role**.

**Tình huống B — Ứng dụng kế toán legacy:** hệ thống yêu cầu username `ledger_app` cố định vì cấu hình JDBC, firewall rule hoặc cơ chế phân quyền đã gắn cứng với account này. DBA muốn Vault tự đổi password hằng ngày. → **Static role**.

**Tình huống C — Ứng dụng Java với connection pool chạy hàng tuần:** có thể dùng dynamic role, nhưng phải triển khai lease lifecycle và thay credential trong DataSource trước khi hết hạn; nếu chưa có cơ chế chuyển pool an toàn, static role cũng cần một cơ chế refresh password và quản lý kết nối mới khi rotate. **Không có loại role nào tự động sửa tất cả JDBC connection pool của ứng dụng.**

### 5.1. Quy tắc lựa chọn nhanh

1. Có thể tạo, cấp quyền và thu hồi user DB mới an toàn không? Nếu có và muốn mỗi workload có danh tính riêng, ưu tiên dynamic role.
2. Hệ thống bắt buộc giữ DB username cố định hoặc DB hạn chế số user? Cân nhắc static role.
3. Có khả năng quản lý lease, xử lý max TTL và thay connection pool? Nếu chưa, phải bổ sung trước khi đưa dynamic role vào production.
4. Có khả năng đồng bộ password rotation cho **mọi** client chia sẻ static account? Nếu chưa, phải thiết kế lại hoặc tách account.
5. Muốn chứng minh ai đã truy cập DB bằng username? Dynamic giúp cô lập tốt hơn; static thường cần thêm audit của ứng dụng/Vault để truy được client.

## 6. Thực hành PostgreSQL: chuẩn bị Database Secrets Engine

Các ví dụ giả định PostgreSQL đã chạy, Vault CLI đã xác thực và database secrets engine được mount tại `database/`. Thực hiện trong môi trường **dev/lab** bằng credential giả; DBA chuẩn bị riêng account quản lý có quyền tối thiểu để tạo user, cấp membership, đổi mật khẩu và thu hồi theo yêu cầu của plugin.

### 6.1. Chuẩn bị quyền SQL tại PostgreSQL

DBA tạo **nhóm quyền** cho ứng dụng đọc để nhiều dynamic account có thể được cấp quyền nhất quán:

```sql
-- Chạy bởi DBA trong database "orders" (chỉ là ví dụ lab).
CREATE ROLE orders_reader NOLOGIN;
GRANT USAGE ON SCHEMA public TO orders_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO orders_reader;

-- Nếu muốn áp dụng cho các bảng sinh trong tương lai,
-- DBA cần cấu hình ALTER DEFAULT PRIVILEGES cho đúng owner/schema.
```

Quyền của `orders_reader` chỉ bao phủ các đối tượng mà các lệnh GRANT thực sự áp dụng. Người vận hành cần kiểm tra owner, schema khác, row-level security và quyền truy cập bảng mới; một câu `GRANT SELECT ON ALL TABLES` không tự bảo đảm sẽ có quyền với các bảng được tạo trong tương lai.

Tạo user cố định dùng cho ví dụ static role:

```sql
-- User này tồn tại trước khi đăng ký static role trong Vault.
CREATE ROLE orders_app LOGIN;
GRANT orders_reader TO orders_app;
```

Tài khoản `orders_app` ban đầu chưa có mật khẩu đăng nhập trong ví dụ này; Vault sẽ đặt password khi onboarding theo hành vi mặc định. Nếu đang migrate account đang dùng thực tế, cần kế hoạch cutover vì Vault có thể **đổi password ngay khi đăng ký**.

### 6.2. Bật engine và cấu hình kết nối

```bash
# Chỉ chạy nếu chưa có mount database/:
vault secrets enable database

# Tham số minh họa. Thay host, chứng chỉ TLS và credential
# theo cấu hình PostgreSQL / Vault thực tế.
vault write database/config/orders-pg \
  plugin_name=postgresql-database-plugin \
  allowed_roles=orders-readonly,orders-app \
  connection_url='postgresql://{{username}}:{{password}}@db.example.internal:5432/orders?sslmode=verify-full' \
  username='vault_db_manager' \
  password='<mat-khau-quan-ly-tu-kho-an-toan>'
```

`vault_db_manager` là **account mà Vault sử dụng để thao tác quản lý users trong PostgreSQL**, không phải dynamic user cấp cho ứng dụng hoặc static account `orders_app`. Account này cần đặc quyền SQL phù hợp với plugin, được giới hạn tới môi trường/database cần quản lý. `sslmode=verify-full` cần chứng chỉ/CA và hostname đúng trong môi trường triển khai; không tắt kiểm tra chứng chỉ để “sửa” lỗi kết nối production.

Đoạn CLI mang tính minh họa: truyền password literal trên dòng lệnh có thể làm lộ credential qua history/process list. Quy trình thực tế phải dùng cơ chế inject credential an toàn (automation/IaC được bảo vệ, API/client có quản lý bí mật), đồng thời hạn chế truy cập vào cấu hình database và audit log của Vault.

`allowed_roles` là danh sách role Vault được phép dùng connection này; không để `*` khi không có yêu cầu. Kiểm tra mount/path và tên role đúng trước khi đưa workload vào hoạt động.

## 7. Tạo **dynamic role**: mỗi lần đọc cấp một database user mới

### 7.1. Định nghĩa SQL khởi tạo

Trong môi trường lab, chuẩn bị một file SQL đầu vào cho Vault CLI tên `create-orders-readonly.sql`:

```sql
CREATE ROLE "{{name}}" WITH LOGIN PASSWORD '{{password}}'
    VALID UNTIL '{{expiration}}';
GRANT orders_reader TO "{{name}}";
```

Các placeholder như `{{name}}`, `{{password}}` và `{{expiration}}` được Vault PostgreSQL plugin thay bằng dữ liệu sinh ra. `orders_reader` là DB role đã tạo ở bước trước. Không để workload quyết định SQL template; nội dung này là cấu hình nhạy cảm do người vận hành/DBA kiểm soát.

### 7.2. Đăng ký dynamic role

```bash
vault write database/roles/orders-readonly \
  db_name=orders-pg \
  creation_statements=@create-orders-readonly.sql \
  default_ttl=1h \
  max_ttl=24h

# Chỉ admin được đọc metadata role:
vault read database/roles/orders-readonly
```

`default_ttl=1h` là TTL yêu cầu mặc định cho credential mới; `max_ttl=24h` giới hạn khả năng gia hạn tùy các giới hạn thực tế khác của Vault. Tùy DB/plugin, có thể cần thêm `revocation_statements`, `renew_statements` hoặc `rollback_statements`; kiểm chứng SQL và hành vi revoke trước khi triển khai.

### 7.3. Lấy credential động và kiểm tra lease

```bash
# Gọi bằng token workload có ACL read tại path này.
vault read database/creds/orders-readonly
```

Dạng kết quả minh họa, **không phải credential thật**:

```text
Key                Value
---                -----
lease_id           database/creds/orders-readonly/...
lease_duration     1h
lease_renewable    true
username           v-orders-readonly-abc123
password           <mat-khau-duoc-tao>
```

Ở dạng JSON API, `username` và `password` nằm trong `data`; `lease_id`, `lease_duration`, `renewable` là metadata ở lớp response bên ngoài. Gọi `vault read database/creds/orders-readonly` lần thứ hai thường tạo DB user khác với lease khác. Vì vậy **không polling endpoint này để kiểm tra sức khỏe**.

### 7.4. Renew, revoke và giới hạn lease

```bash
# Dùng lease_id THỰC được cấp bởi thao tác read.
vault lease lookup <lease-id-thuc-te>

# Gia hạn chỉ khi lease renewable và policy/TTL cho phép:
vault lease renew <lease-id-thuc-te>

# Thu hồi sớm một credential trong môi trường lab:
vault lease revoke <lease-id-thuc-te>
```

`vault lease revoke` không phải lệnh xóa Vault dynamic role. Nó yêu cầu thu hồi **một lease/DB credential đã cấp**. Còn lệnh xóa role definition là thao tác quản trị riêng trên `database/roles/orders-readonly`; việc xóa định nghĩa role không thay thế quy trình thu hồi những credential đang tồn tại.

Nếu plugin/SQL revoke thành công, user bị vô hiệu hoặc thu hồi quyền phù hợp. Tùy DB và transaction/connection đang mở, ứng dụng phải được kiểm thử thực tế về cách kết nối hiện hữu phản ứng; **không** giả định tất cả phiên JDBC lập tức bị cắt ở đúng thời điểm Vault trả ACK.

**Lưu ý bảo mật:** token dùng để đọc credentials có thể tự hết hạn, và các lease liên quan có thể bị thu hồi khi token chủ bị revoke. Lease duration và token duration phải được thiết kế cùng nhau; không kéo dài token bằng cách hardcode credential vào file cấu hình.

## 8. Tạo **static role**: quản lý mật khẩu của database user đã có

### 8.1. Định nghĩa câu lệnh đổi mật khẩu

Chuẩn bị file SQL tên `rotate-orders-app.sql` trong môi trường lab:

```sql
ALTER ROLE "{{name}}" WITH PASSWORD '{{password}}';
```

Ở đây `{{name}}` sẽ ứng với **username hiện có** (`orders_app`), không phải một username mới sinh ra. Vault cần đủ quyền `ALTER ROLE` phù hợp. Tránh dùng root/superuser database cho static role của ứng dụng.

### 8.2. Đăng ký và quan sát

```bash
# Thực hiện bằng token quản trị được ủy quyền.
vault write database/static-roles/orders-app \
  db_name=orders-pg \
  username=orders_app \
  rotation_statements=@rotate-orders-app.sql \
  rotation_period=24h

# Metadata cấu hình (không phải mật khẩu):
vault read database/static-roles/orders-app

# Lấy credential hiện tại bằng token workload được phép:
vault read database/static-creds/orders-app
```

Ví dụ kết quả `static-creds` (đã ẩn mật khẩu):

```text
Key                  Value
---                  -----
username             orders_app
password             <mat-khau-hien-hanh>
last_vault_rotation  2026-11-25T03:00:00Z
rotation_period      24h
ttl                  23h59m
```

Trong HTTP JSON, `ttl` thường là số giây còn lại, có thể khác cách định dạng CLI. Trong ví dụ này:

- `username` **giữ nguyên** khi đọc lại.
- `password` giữ nguyên cho tới khi Vault thực hiện rotation thành công.
- `ttl` biểu thị thời gian tới lịch rotation; **không phải lease của lần đọc**, không có `lease_id` tương ứng để renew/revoke riêng.
- Mặc định lần đăng ký static role có thể **đổi mật khẩu ngay**, nên đừng onboard trực tiếp production khi các client cũ vẫn dùng mật khẩu trước đó.

### 8.3. Xoay vòng thủ công và theo lịch

```bash
# Rotate password của đúng static role, có thể ảnh hưởng ứng dụng đang dùng:
vault write -f database/rotate-role/orders-app

# Đọc lại sau khi rotate, xác nhận password mới và thời gian xoay vòng:
vault read database/static-creds/orders-app
```

Ngoài `rotation_period=24h`, có thể cấu hình `rotation_schedule` kiểu cron (chẳng hạn `0 0 * * SAT`); tùy thời điểm phiên bản Vault, lịch được diễn giải theo quy ước timezone trong tài liệu của phiên bản đó. `rotation_window` (nếu dùng schedule) giới hạn thời gian được phép xoay vòng. **Không** đặt đồng thời `rotation_period` và `rotation_schedule`.

Các cách trì hoãn vòng rotate ban đầu hoặc nạp password ban đầu (`skip_import_rotation`, v.v.) phụ thuộc tính năng/edition Vault cụ thể. Nếu cần migration mềm cho account đang vận hành, hãy kiểm tra tài liệu phiên bản triển khai và thử quy trình trên hệ thống staging trước khi cutover.

**Phân biệt hai API rotation:**

| API | Ý nghĩa |
| --- | --- |
| `POST database/rotate-role/orders-app` | Rotate password cho **static application account** được quản lý bởi Vault role |
| `POST database/rotate-root/orders-pg` | Rotate password cho **account quản lý của Vault** trong cấu hình connection, do đội vận hành kiểm soát |

Không đưa account quản lý Vault vào static role để “tiện” rotate. Khi account quản lý mất khả năng đăng nhập, Vault sẽ khó tạo, thu hồi hoặc rotate tất cả credential khác gắn với database connection này.

### 8.4. Tình huống lỗi rotation

Giả sử `orders_app` được dùng bởi ba pod cùng một thời điểm. Vault rotate password lúc 02:00:

1. Pod A vẫn giữ password cũ trong JDBC pool.
2. Pod B đọc lại `static-creds` và nhận password mới.
3. Pod A mở connection mới bằng password cũ và bị authentication failure.
4. Kết nối cũ có thể còn sống tùy driver/database, nhưng không nên dựa vào điều này để bảo đảm liên tục dịch vụ.
5. Cần cập nhật mọi client, làm mới pool một cách có kiểm soát và giám sát lỗi đăng nhập.

Đây là vấn đề **đồng bộ client khi đổi password**, không phải lỗi Vault static role. Lịch rotation phải phù hợp với cách ứng dụng làm mới cấu hình JDBC/DataSource.

## 9. Policy và xác thực theo workload

Vault policy kiểm soát **ai được gọi endpoint**, còn SQL role kiểm soát **credential trả về được làm gì trong database**. Không cấp quyền quản trị engine cho workload chỉ cần lấy username/password.

### 9.1. Workload dùng dynamic credentials

Policy `orders-report-worker.hcl`:

```hcl
path "database/creds/orders-readonly" {
  capabilities = ["read"]
}
```

Mỗi lần workload dùng token này gọi `GET /v1/database/creds/orders-readonly`, Vault tạo credential theo dynamic role tương ứng. Workload không cần quyền `database/roles/...`, `database/config/...` hoặc danh sách mọi role.

### 9.2. Workload dùng static credentials

Policy `orders-legacy-app.hcl`:

```hcl
path "database/static-creds/orders-app" {
  capabilities = ["read"]
}
```

Bất kỳ workload token nào có quyền `read` trên static path này đều có thể lấy **password hiện hành của cùng DB account**. Do đó phải kiểm soát identity và số người/service được phép đọc, tránh chia sẻ account quá rộng.

### 9.3. Tách quyền quản trị

Ví dụ policy minh họa cho người vận hành quản lý **đúng hai Vault role**:

```hcl
# Điều chỉnh mẫu tạo dynamic user và TTL.
path "database/roles/orders-readonly" {
  capabilities = ["create", "read", "update"]
}

# Điều chỉnh static role, username và lịch rotate.
path "database/static-roles/orders-app" {
  capabilities = ["create", "read", "update"]
}

# Cho phép chủ động xoay mật khẩu static role.
path "database/rotate-role/orders-app" {
  capabilities = ["update"]
}
```

Đây chỉ là ví dụ giới hạn phạm vi; các quyền tạo/sửa connection, rotate root, xóa role, quản lý mount và lease revoke hàng loạt cần được cấp riêng theo quy trình vận hành. Các policy ở trên **không** bao gồm quyền đọc credentials: quản trị role có thể tách khỏi người sử dụng account.

Lưu policy vào Vault (thực hiện bởi người vận hành có quyền):

```bash
vault policy write orders-report-worker orders-report-worker.hcl
vault policy write orders-legacy-app orders-legacy-app.hcl
vault policy write orders-db-operator orders-db-operator.hcl
```

Ánh xạ policy với Kubernetes Auth, AppRole hoặc danh tính workload thực. Kiểm tra token/capability bằng chính role runtime. Một token có thể mang nhiều policy, và quyền thường được hợp nhất; **thêm policy hẹp không thu hẹp policy rộng đã gắn sẵn**.

### 9.4. Ma trận phân quyền kỳ vọng

| Endpoint | `report-worker` | `legacy-app` | `db-operator` |
| --- | :---: | :---: | :---: |
| `GET database/creds/orders-readonly` | Được | Chặn | Chặn |
| `GET database/static-creds/orders-app` | Chặn | Được | Chặn |
| `POST database/roles/orders-readonly` | Chặn | Chặn | Được |
| `POST database/static-roles/orders-app` | Chặn | Chặn | Được |
| `POST database/rotate-role/orders-app` | Chặn | Chặn | Được |
| `POST database/rotate-root/orders-pg` | Chặn | Chặn | Chặn |

Ma trận phản ánh **ba policy ví dụ độc lập**, không bao gồm các policy hệ thống khác. Để kiểm thử, cần tạo token theo từng workload role và xác nhận cả **trường hợp được phép** lẫn **HTTP 403 khi thiếu quyền**.

## 10. Gọi Database Secrets Engine từ Spring Vault bằng `VaultTemplate`

Ứng dụng Spring Boot/Java có thể gọi trực tiếp path đã cấp quyền. Ví dụ dùng Java 17+ và bean `VaultTemplate` đã được cấu hình endpoint HTTPS cùng cơ chế xác thực workload. Không cấu hình Vault token trong code.

```java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class DatabaseCredentialsClient {

    private final VaultTemplate vaultTemplate;

    public DatabaseCredentialsClient(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public record DynamicCredential(
            String username, String password, String leaseId) {}

    public record StaticCredential(
            String username, String password, long secondsToRotation) {}

    public DynamicCredential issueDynamicReadonlyCredential() {
        VaultResponse response = requireData(
                vaultTemplate.read("database/creds/orders-readonly"));

        String leaseId = response.getLeaseId();
        if (leaseId == null || leaseId.isBlank()) {
            throw new IllegalStateException(
                    "Dynamic credential response missing lease id");
        }

        return new DynamicCredential(
                requiredText(response.getData(), "username"),
                requiredText(response.getData(), "password"),
                leaseId);
    }

    public StaticCredential readStaticOrdersCredential() {
        VaultResponse response = requireData(
                vaultTemplate.read("database/static-creds/orders-app"));

        Object ttl = response.getData().get("ttl");
        if (!(ttl instanceof Number)) {
            throw new IllegalStateException(
                    "Static credential response missing rotation TTL");
        }

        return new StaticCredential(
                requiredText(response.getData(), "username"),
                requiredText(response.getData(), "password"),
                ((Number) ttl).longValue());
    }

    private static VaultResponse requireData(VaultResponse response) {
        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Vault database credential response has no data");
        }
        return response;
    }

    private static String requiredText(
            Map<String, Object> data, String key) {
        Object value = data.get(key);
        if (!(value instanceof String)
                || ((String) value).isBlank()) {
            throw new IllegalStateException(
                    "Vault response missing required field: " + key);
        }
        return (String) value;
    }
}
```

**Cách hiểu kết quả Java:**

- `issueDynamicReadonlyCredential()` gọi `database/creds/...` và **cấp credential mới mỗi lần thực hiện**. Không gọi phương thức này trước mỗi SQL query, cho mỗi HTTP request hoặc mỗi lần health check.
- `DynamicCredential.leaseId()` dành cho quản lý vòng đời credential; không ghi nguyên username/password/lease vào log. Lease ID là metadata nhạy cảm vận hành, cần giới hạn truy cập.
- `readStaticOrdersCredential()` đọc mật khẩu hiện hành của tài khoản `orders_app`; `secondsToRotation` là TTL lịch rotate, **không** biến nó thành dynamic lease ID.
- Hai phương thức cần **hai policy khác nhau**. Một workload chỉ có quyền dynamic path không thể tự đọc static path; nếu có cả hai quyền, đó phải là lựa chọn có chủ ý của policy.
- Trong môi trường thật, validate cẩn thận kiểu dữ liệu/phiên bản response và dùng error handler không làm lộ password. `VaultTemplate` có thể ném exception khi thiếu quyền, connection lỗi hoặc Vault trả lỗi.

### 10.1. Vì sao lấy credential xong chưa đủ cho JDBC pool?

Giả sử đọc credential động và cấu hình một `DataSource` lúc startup. Ban đầu các connection sử dụng user động v1. Khi max TTL kết thúc, Vault có thể thu hồi v1; nếu ứng dụng **chỉ lưu user/password ban đầu**, pool sẽ không tự chuyển sang v2.

Với static role, username không đổi nhưng password có thể đổi theo lịch, cũng khiến connection mới dùng password cũ thất bại.

Quy trình cần thiết:

```mermaid
flowchart LR
    A["Vault cấp credential"] --> B["Ứng dụng lưu trong bộ nhớ"]
    B --> C["DataSource / connection pool"]
    C --> D{"Lease hết hạn<br/>hoặc password rotate?"}
    D -- "Chưa" --> C
    D -- "Sắp/đã" --> E["Lấy credential còn hiệu lực"]
    E --> F["Cập nhật cấu hình pool<br/>và tạo connection mới"]
    F --> G["Cho connection cũ kết thúc<br/>theo chính sách cutover"]
    G --> C
```

**Một chiến lược tốt cho dynamic credentials:**

1. Yêu cầu Vault cấp credential một lần cho lifecycle của workload.
2. Quản lý lease và gia hạn trước TTL nếu được phép.
3. Khi gần max TTL hoặc cần rotate, lấy credential mới và kiểm tra đăng nhập.
4. Cập nhật/đổi pool để connection mới dùng credential mới; cho request đang chạy hoàn thành theo chính sách.
5. Revoke credential cũ sau cutover thành công (hoặc xử lý khi lease tự hết hạn).
6. Quan sát kết nối lỗi và số credential còn tồn tại trong database.

**Một chiến lược tốt cho static credentials:** theo dõi TTL rotation, chuẩn bị refresh/đổi pool của tất cả client dùng `orders_app`. Không nên để N client độc lập giả định password bất biến hoặc chỉ đọc static credential lúc khởi động.

### 10.2. Spring Vault lease management và Spring Cloud Vault

Spring Vault cung cấp **`SecretLeaseContainer`**, cùng các cơ chế quản lý vòng đời secret như `ManagedSecret` trong phiên bản hỗ trợ, để theo dõi lease, gia hạn và phát sự kiện khi credential được thay. Với dynamic credentials, nên dùng cơ chế managed lifecycle thay vì tự đặt thread polling `database/creds/...`. Các event như lease renewed, expired hoặc rotated cần được ứng dụng kết nối với việc cập nhật JDBC pool.

Trong Spring Cloud Vault, có thể bật database backend để nạp dynamic credential vào cấu hình Spring:

```yaml
spring:
  cloud:
    vault:
      database:
        enabled: true
        backend: database
        role: orders-readonly
        username-property: spring.datasource.username
        password-property: spring.datasource.password
```

Đoạn cấu hình phụ thuộc phiên bản Spring Cloud Vault và các dependency tương ứng; đây là ví dụ về **dynamic database backend**. Đối với static role, endpoint lấy dữ liệu là `static-creds/…`, nên không giả định cấu hình dynamic ở trên tự chuyển sang static role khi chỉ thay `role`.

Tài liệu của một số phiên bản Spring Cloud Vault cũng nêu giới hạn: khi credential động đạt **max TTL**, framework không tự cấu hình lại `DataSource` bằng credential mới trong mọi trường hợp. Vì vậy phải **kiểm chứng end-to-end** trên đúng phiên bản Spring Vault/Spring Cloud Vault, driver JDBC và pool (ví dụ HikariCP) thực tế.

## 11. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Khả năng xảy ra | Hướng xử lý |
| --- | --- | --- |
| HTTP 403 khi lấy `database/creds/...` | Token workload thiếu `read` trên role/path đúng | Kiểm tra role xác thực, mount path, ACL hiệu lực; không dùng root token để “sửa” |
| HTTP 404 / role không tồn tại | Nhầm tên Vault role hoặc nhầm `creds` và `static-creds` | Kiểm tra `database/roles/...` so với `database/static-roles/...` và path runtime |
| Dynamic read báo DB permission lỗi | Account quản lý Vault không có quyền CREATE/GRANT, hoặc SQL template sai | DBA kiểm tra grant, query, PostgreSQL logs, database plugin |
| Nhiều dynamic users không cần thiết | Ứng dụng đọc `database/creds` mỗi request/health check | Quản lý credential theo lifecycle; renew/rotate có kiểm soát |
| Sau max TTL pool bắt đầu lỗi login | User động đã bị thu hồi, `DataSource` vẫn dùng credentials cũ | Triển khai pool rotation trước max TTL và health check bằng kết nối mới |
| Static role tạo xong ứng dụng cũ mất login | Password bị rotate ngay khi onboarding | Thử staging, lập kế hoạch cutover, kiểm tra tùy chọn onboarding hỗ trợ |
| Static role vẫn cùng username nhưng password khác | Đây là hành vi rotation bình thường | Lấy password mới, cập nhật pool, giảm thời gian dùng credential cũ |
| Static role rotation thất bại | Vault không thể `ALTER USER`, DB down hoặc SQL template sai | Kiểm tra rotation errors, độ trễ và cửa sổ retry; phối hợp DBA |
| Revoke dynamic lease không xóa được user | DB tạm lỗi hoặc revocation SQL/plugin có vấn đề | Theo dõi lỗi, đối soát users/leases và xử lý manual theo runbook |
| Static credential có `ttl` nhưng không có `lease_id` | `ttl` là thời gian tới rotation | Không gọi lease renew; dùng cơ chế đọc lại và đồng bộ client |
| SQL vẫn truy vấn bằng quyền quá cao | GRANT hoặc database role sai, dù Vault ACL đúng | Kiểm thử quyền DB trực tiếp bằng credential được cấp |
| Vault 5xx/timeout | Kết nối/tình trạng Vault/backend | Retry giới hạn cho lỗi tạm thời, theo dõi availability; không fallback password hardcode |

**Không dùng fallback “Vault lỗi thì lấy password cũ đã commit vào Git”**. Luồng an toàn phải thất bại có kiểm soát và quan sát được. Không in password vào exception, trace, metric label, debug SQL log hoặc ticket hỗ trợ.

Các chỉ số vận hành hữu ích: tỷ lệ cấp dynamic credential thất bại, số lease đang hoạt động, thời gian tới max TTL, tỷ lệ revoke lỗi, số user DB tồn dư, thời gian đổi pool, login failure khi static rotation, số lần rotate thất bại, Vault 403/5xx và độ trễ API.

## 12. Bài thực hành và tiêu chí đánh giá

**Đề bài:** Hệ thống đơn hàng có worker tạo báo cáo (`report-worker`) và một ứng dụng cũ (`legacy-app`). Cả hai chỉ cần đọc bảng `orders`. Worker chạy theo job; legacy app phải dùng tên database account cố định.

**Phần A — Chuẩn bị**

1. Tạo role quyền SQL `orders_reader` và tài khoản cố định `orders_app` trong PostgreSQL lab.
2. Mount `database/`, cấu hình `orders-pg` bằng `postgresql-database-plugin`, giới hạn `allowed_roles`.
3. Xác minh credential quản lý của Vault có quyền cần thiết và kết nối TLS đúng.

**Phần B — Dynamic role**

1. Tạo `database/roles/orders-readonly` với SQL `CREATE ROLE` và `GRANT orders_reader`, TTL 1 giờ, max TTL 24 giờ.
2. Đăng nhập bằng token `report-worker`, gọi `vault read database/creds/orders-readonly` **hai lần**.
3. So sánh hai username, hai `lease_id`; kiểm tra tài khoản tồn tại trong PostgreSQL và chỉ có quyền đọc.
4. Renew một lease nếu được phép; revoke lease còn lại và quan sát DB account bị vô hiệu/thu hồi.
5. Dùng token `report-worker` thử đọc `database/static-creds/orders-app` và xác nhận bị 403.

**Phần C — Static role**

1. Tạo `database/static-roles/orders-app` ánh xạ username `orders_app`, thiết lập `rotation_period=24h`.
2. Đăng nhập bằng token `legacy-app`, đọc `static-creds` **hai lần**, xác minh username/password không đổi khi chưa rotate.
3. Dùng token operator gọi `database/rotate-role/orders-app`; đọc lại static-creds và xác minh password mới nhưng username giữ nguyên.
4. Kiểm tra PostgreSQL đã nhận password mới; chứng minh password cũ không dùng để tạo kết nối mới.
5. Dùng token `legacy-app` thử đọc dynamic path và xác nhận bị 403.

**Phần D — Java và vòng đời**

1. Gọi `DatabaseCredentialsClient` với workload token tương ứng.
2. Dùng dynamic credential để tạo JDBC connection và chạy một truy vấn `SELECT` hợp lệ; thử `INSERT/UPDATE` và xác minh bị từ chối nếu SQL policy cấm.
3. Chạy tình huống credential thay đổi trong khi connection pool đang sống; quan sát connection mới, exception và quy trình refresh.
4. Đảm bảo logs không lộ password, token hay dữ liệu database nhạy cảm.
5. Thử lỗi DB không sẵn sàng khi Vault cấp/revoke/rotate, ghi nhận thông báo/metrics và phương án phục hồi.

**Tiêu chí hoàn thành:** dynamic role cấp credential mới kèm lease cho mỗi lần yêu cầu; static role giữ username và xoay password; ACL Vault tách biệt, quyền SQL đúng mức đọc; pool xử lý credential thay đổi theo kế hoạch; test thu hồi/rotation có bằng chứng ở cả Vault và PostgreSQL.

## 13. Checklist áp dụng production

- [ ] Xác định role là dynamic hay static dựa trên **yêu cầu username và vòng đời account**, không chỉ dựa vào nhãn “secret”.
- [ ] Vault connection dùng tài khoản quản lý riêng, quyền SQL tối thiểu; TLS xác minh chứng chỉ.
- [ ] `allowed_roles` giới hạn chính xác, dynamic creation/revocation SQL đã kiểm thử.
- [ ] Dynamic role có `default_ttl`, `max_ttl` và kế hoạch renew, rotate, revoke, DB user cleanup.
- [ ] Static role dùng **account đã tồn tại**; onboarding/initial rotation có cutover được duyệt.
- [ ] Static role có lịch rotation phù hợp và client/pool được thiết kế để đổi password.
- [ ] Không dùng API `lease renew/revoke` cho `static-creds.ttl`; phân biệt rotation TTL với lease duration.
- [ ] Vault ACL `read` đúng path và DB GRANT đúng bảng/schema; kiểm thử cả trường hợp bị từ chối.
- [ ] Workload token đến từ Kubernetes Auth/AppRole hoặc cơ chế phù hợp, có TTL/renewal riêng và không hardcode.
- [ ] Có giám sát số DB user tạm, lỗi revoke, lỗi rotate, Vault 403/5xx, timeout và JDBC authentication failures.
- [ ] Không in username/password/lease ID nhạy cảm trong log, không lưu password dài hạn trong repo.
- [ ] Đã kiểm tra end-to-end cơ chế cập nhật DataSource trên đúng phiên bản Java, Spring Vault và JDBC driver.

## 14. Tài liệu tham khảo

- [HashiCorp Vault — Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [HashiCorp Vault — Database Secrets Engine HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/databases)
- [HashiCorp Vault — PostgreSQL Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases/postgresql)
- [HashiCorp Vault — Dynamic Secrets for Database Credential Management](https://developer.hashicorp.com/vault/tutorials/db-credentials/database-secrets)
- [HashiCorp Vault — Lease, Renew and Revoke](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [Spring Vault — Credentials Rotation và SecretLeaseContainer](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [Spring Vault — VaultResponse Java API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultResponse.html)
- [Spring Cloud Vault — Secret Backends: Database](https://docs.spring.io/spring-cloud-vault/reference/secret-backends.html)
