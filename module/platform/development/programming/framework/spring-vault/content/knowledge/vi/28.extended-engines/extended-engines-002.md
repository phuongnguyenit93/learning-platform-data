# Database secrets engine và thông tin đăng nhập động theo role

## 1. Bài toán: không lưu mật khẩu cơ sở dữ liệu cố định trong ứng dụng

Trong module **SPRING_VAULT**, chúng ta đã biết ứng dụng Java có thể dùng `VaultTemplate` để truy cập HashiCorp Vault và đăng nhập bằng danh tính workload. Một nhu cầu tiếp theo là kết nối đến PostgreSQL, MySQL hoặc một database khác mà không phải đặt một cặp username/password dùng chung, tồn tại lâu dài trong `application.yml`, biến môi trường hoặc file triển khai.

**Database secrets engine** giải quyết bài toán này bằng cách để Vault tạo **thông tin đăng nhập động (dynamic credentials)** theo một **database role** đã được người vận hành cấu hình. Mỗi lần workload yêu cầu thông tin đăng nhập qua `database/creds/<role>`, Vault có thể tạo một tài khoản database riêng, gắn giới hạn quyền SQL và cấp một **lease** có thời hạn. Khi lease hết hạn hoặc bị thu hồi, Vault sử dụng database plugin để thu hồi tài khoản tương ứng.

Ví dụ: dịch vụ `orders-api` chỉ được đọc bảng đơn hàng, còn `orders-worker` có thể cập nhật trạng thái đơn hàng. Thay vì hai ứng dụng dùng chung `db_admin`, quản trị viên tạo hai role của Vault: `orders-readonly` và `orders-readwrite`. Các role cấp phát tài khoản database với quyền khác nhau.

### Static secret khác gì với dynamic credential?

| Tiêu chí | Mật khẩu DB cố định trong cấu hình/KV | Database dynamic credential |
|---|---|---|
| Nguồn username/password | Quản trị viên tạo trước và lưu lâu dài | Vault tạo theo database role khi có yêu cầu |
| Danh tính trên DB | Có thể dùng chung giữa nhiều instance | Có thể tách tài khoản theo lần cấp, workload/instance |
| Vòng đời | Xoay vòng thủ công hoặc bằng cơ chế ngoài | Có lease, TTL, renewal/revocation qua Vault |
| Phân quyền | Có thể kiểm soát ở DB nhưng dễ dùng account chung | SQL quyền thực tế được xác định bởi câu lệnh cấp tài khoản |
| Theo dõi | Khó truy vết khi nhiều service cùng một username | Dễ gắn database login với lần cấp và audit record |
| Rủi ro vận hành | Mật khẩu có thể quá hạn và khó thay trên nhiều nơi | Cần quản lý lease, connection pool, token và mất kết nối Vault |

Vault cũng có **database static roles** (đường dẫn `database/static-creds/<role>`) để xoay mật khẩu của một tài khoản database có tên cố định. Đây là cơ chế khác với **dynamic roles** (đường dẫn `database/creds/<role>`) sẽ được thực hành trong bài.

## 2. Kiến trúc và luồng cấp phát động

Có ba lớp danh tính dễ bị nhầm:

1. **Vault auth role / workload identity**: quyết định ứng dụng đăng nhập Vault bằng Kubernetes auth, AppRole hoặc auth method khác và nhận những Vault policies nào.
2. **Database role trong Vault**: định nghĩa cách sinh tài khoản database, SQL creation/renew/revocation statements, TTL và tên database connection.
3. **Database account/role thực trong PostgreSQL**: tài khoản do database plugin tạo, dùng cho JDBC và nhận quyền SQL như `SELECT`, `INSERT` hoặc `UPDATE`.

Cùng từ “role” nhưng ba lớp thực hiện chức năng khác nhau. **Vault policy không tự cấp quyền `SELECT` trên PostgreSQL**; quyền SQL phát sinh khi các câu lệnh SQL ở database role được thực thi.

~~~mermaid
sequenceDiagram
    participant App as Java orders-api
    participant Auth as Vault Auth
    participant Vault as Vault Database Engine
    participant DB as PostgreSQL

    App->>Auth: Đăng nhập bằng danh tính workload
    Auth-->>App: Vault token với policy giới hạn
    App->>Vault: GET /v1/database/creds/orders-readonly
    Vault->>Vault: Kiểm tra ACL + role + allowed_roles
    Vault->>DB: CREATE ROLE + GRANT quyền đọc
    DB-->>Vault: Tạo tài khoản thành công
    Vault-->>App: username, password, lease_id, TTL
    App->>DB: Kết nối JDBC bằng tài khoản vừa cấp
    DB-->>App: Kết quả SELECT hợp lệ
    Note over App,Vault: Renew lease hoặc yêu cầu credentials mới
    Vault->>DB: Thu hồi tài khoản khi lease hết hạn/bị revoke
~~~

Điều kiện thiết yếu: **Vault server phải kết nối được database** và có một **tài khoản quản lý DB** đủ quyền thực hiện SQL đã cấu hình. Tài khoản quản lý này không phải tài khoản mà ứng dụng Java sử dụng để truy vấn nghiệp vụ.

### Phân biệt các đường dẫn dưới mount `database/`

| Vault path | Công việc | Ai cần quyền? |
|---|---|---|
| `database/config/orders-db` | Cấu hình database plugin, địa chỉ kết nối, tài khoản quản lý, danh sách role | Operator |
| `database/roles/orders-readonly` | Định nghĩa dynamic role và SQL/TTL tương ứng | Operator |
| `database/creds/orders-readonly` | Sinh một username/password mới kèm lease | Workload có quyền `read` |
| `sys/leases/lookup`, `sys/leases/renew`, `sys/leases/revoke` | Xem/gia hạn/thu hồi lease theo quyền được cấp | Bộ phận quản lý lease hoặc thành phần Spring Vault có quyền phù hợp |
| `database/static-roles/...`, `database/static-creds/...` | Quản lý và đọc thông tin của static roles | Chỉ khi dùng static roles |

Một yêu cầu `GET database/creds/orders-readonly` thường là **yêu cầu cấp mới**, không phải đọc lại cùng credential. Việc gọi nhiều lần vô ý có thể tạo nhiều database accounts và leases không cần thiết.

## 3. Chuẩn bị PostgreSQL cho ví dụ

Giả sử database thử nghiệm có:

- Database: `orders`.
- Schema: `public`.
- Bảng nghiệp vụ: `orders`.
- Vault database mount: `database/`.
- Tên kết nối khai báo trong Vault: `orders-db`.
- Database dynamic role trong Vault: `orders-readonly`.
- Tài khoản quản lý DB dành riêng cho Vault: `vault_db_manager`.

Chạy trong môi trường thử nghiệm hoặc staging cô lập. Người vận hành DB cần cấp cho `vault_db_manager` quyền đủ để tạo và thu hồi tài khoản động theo plugin; **không nên dùng superuser lâu dài nếu có thể phân quyền thấp hơn**. Thiết kế quyền này cần kiểm tra trên PostgreSQL thật, vì `CREATEROLE`, quyền membership và quyền đổi trạng thái role khác nhau theo phiên bản PostgreSQL.

Một cách giới hạn quyền đọc là tạo **group role** ổn định trong PostgreSQL, sau đó để Vault chỉ thêm người dùng động vào group:

~~~sql
-- Chạy bởi quản trị viên PostgreSQL trong database orders.
CREATE ROLE orders_reader NOLOGIN;

GRANT CONNECT ON DATABASE orders TO orders_reader;
GRANT USAGE ON SCHEMA public TO orders_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO orders_reader;

-- Ví dụ tùy chọn: người sở hữu object mới là app_schema_owner.
-- Thực thi với quyền phù hợp trên role tạo bảng.
ALTER DEFAULT PRIVILEGES FOR ROLE app_schema_owner IN SCHEMA public
    GRANT SELECT ON TABLES TO orders_reader;
~~~

`GRANT SELECT ON ALL TABLES` áp dụng với các bảng đã có tại thời điểm chạy; câu lệnh `ALTER DEFAULT PRIVILEGES` cần cấu hình phù hợp với **role thực sự tạo bảng mới**. Thử nghiệm quyền `SELECT` trên cả bảng cũ lẫn bảng mới thay vì suy đoán rằng thay đổi schema luôn tự giữ nguyên quyền.

Database manager cũng phải được cấp đúng quyền để tạo user và gán membership `orders_reader`. Nếu sử dụng PostgreSQL nâng cấp khác nhau, cần kiểm tra tương thích của SQL statements và mặc định `INHERIT`.

## 4. Bật Database secrets engine và đăng ký kết nối

Các lệnh quản trị sau là **minh họa**, chạy bằng tài khoản Vault operator đã được phân quyền, không chạy với workload token.

~~~bash
# Chỉ bật một lần trên Vault instance nếu mount chưa tồn tại.
vault secrets enable -path=database database

# Đăng ký PostgreSQL database plugin và giới hạn role có thể sử dụng.
# Giá trị DB_ADMIN_PASSWORD phải được đưa vào từ nguồn bí mật an toàn;
# không hardcode mật khẩu thật trong script chia sẻ.
vault write database/config/orders-db \
  plugin_name="postgresql-database-plugin" \
  allowed_roles="orders-readonly" \
  connection_url='postgresql://{{username}}:{{password}}@postgres.internal:5432/orders?sslmode=verify-full' \
  username="vault_db_manager" \
  password="$DB_ADMIN_PASSWORD"
~~~

Điểm cần hiểu:

- `plugin_name` chọn database plugin, trong ví dụ là `postgresql-database-plugin`.
- `connection_url` chứa hai biến do Vault thay thế bằng thông tin của database manager. Tham số TLS như `sslmode=verify-full` phải đi kèm CA/trust và hostname phù hợp với môi trường.
- `allowed_roles=orders-readonly` giới hạn những Vault database roles nào có thể sử dụng connection này. Giá trị `*` cho tất cả role có thể mở rộng phạm vi ngoài mục đích.
- `username` / `password` ở `database/config` là **tài khoản quản lý DB** để Vault tạo tài khoản khác, không phải credentials trả về cho ứng dụng.
- Ví dụ truyền `password` qua đối số CLI nên chỉ phù hợp minh họa/harness kín. Trong thực tế, chọn phương thức bootstrap an toàn tránh lộ bí mật qua shell history, process arguments, CI log và hệ thống quản lý lệnh; xoay credentials quản trị theo chính sách tổ chức.

Kiểm tra cấu hình bằng danh tính operator:

~~~bash
vault read database/config/orders-db
~~~

Phản hồi đọc config có thể ẩn trường password; điều đó là hành vi bảo vệ bí mật, không phải bằng chứng kết nối sai. Cần thêm phép cấp phát thật để xác minh DB manager kết nối và tạo account được.

## 5. Định nghĩa dynamic role và SQL phát hành credential

Dynamic role ánh xạ tên `orders-readonly` tới connection `orders-db` và SQL để tạo user trên PostgreSQL.

~~~bash
vault write database/roles/orders-readonly \
  db_name="orders-db" \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN INHERIT PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT orders_reader TO \"{{name}}\";" \
  renew_statements="ALTER ROLE \"{{name}}\" VALID UNTIL '{{expiration}}';" \
  default_ttl="1h" \
  max_ttl="4h"

vault read database/roles/orders-readonly
~~~

Trong SQL template:

- `{{name}}` là username được Vault sinh ra, không phải tên role `orders-readonly`.
- `{{password}}` là mật khẩu động do plugin cấp.
- `{{expiration}}` là mốc hết hạn được Vault tính theo lease để PostgreSQL áp dụng `VALID UNTIL`.
- `GRANT orders_reader` gán quyền đọc cho account mới qua group role đã cấu hình.
- `renew_statements` điều chỉnh hiệu lực trên **database account** khi lease được gia hạn. Nếu renewal trong Vault thành công nhưng DB account vẫn giữ expiration cũ thì ứng dụng có thể đăng nhập thất bại; phải kiểm tra cả hai phía.
- `default_ttl=1h` và `max_ttl=4h` là giá trị minh họa. TTL thực còn chịu giới hạn mount, hệ thống và session/token; không nên diễn giải rằng bất kỳ lease nào cũng có thể gia hạn vô hạn.

Với PostgreSQL, plugin hỗ trợ `creation_statements`, `renew_statements`, `revocation_statements` và các statement khác tùy khả năng plugin. **Phải kiểm tra hành vi thu hồi**: nếu không cung cấp `revocation_statements`, plugin có thể dùng câu lệnh mặc định không phù hợp với quy ước role, session và object ownership trong hệ thống. Một ví dụ cấu hình thu hồi tường minh, chỉ sử dụng sau khi đã thử thành công trên PostgreSQL:

~~~bash
# Tùy chọn: chỉ áp dụng nếu SQL này đúng với mô hình DB thực tế.
vault write database/roles/orders-readonly \
  db_name="orders-db" \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN INHERIT PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT orders_reader TO \"{{name}}\";" \
  renew_statements="ALTER ROLE \"{{name}}\" VALID UNTIL '{{expiration}}';" \
  revocation_statements="REVOKE orders_reader FROM \"{{name}}\"; DROP ROLE IF EXISTS \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="4h"
~~~

**Lưu ý:** lệnh `vault write database/roles/orders-readonly` là cập nhật cấu hình role; khi cập nhật phải truyền lại các trường cần giữ, không giả định mọi field cũ luôn được tự bảo toàn. SQL `DROP ROLE` có thể gặp trở ngại nếu account còn session đang mở, sở hữu object hoặc có dependency. Một hệ thống production phải kiểm tra plugin, thiết kế revocation statements phù hợp và giám sát lỗi cleanup.

Không đưa những SQL vượt quyền (như `SUPERUSER`, `CREATEDB`, `BYPASSRLS`, `GRANT ALL PRIVILEGES`) vào role chỉ cần đọc dữ liệu. Dynamic credentials có thời hạn ngắn vẫn gây thiệt hại nếu quyền SQL quá lớn.

## 6. Cấp credentials và phân tích lease

Sau khi cấu hình xong, **workload có token hợp lệ** yêu cầu thông tin đăng nhập:

~~~bash
vault read database/creds/orders-readonly
~~~

Một phản hồi minh họa đã che mật khẩu:

~~~text
Key             Value
---             -----
lease_id        database/creds/orders-readonly/<id-duoc-cap>
lease_duration  1h
lease_renewable true
username        v-orders-...-duoc-cap
password        <REDACTED>
~~~

Nếu dùng HTTP API, endpoint tương ứng thường là:

~~~http
GET /v1/database/creds/orders-readonly
X-Vault-Token: <token-cua-workload>
~~~

Trong đó phản hồi Vault thường có metadata lease ở cấp ngoài:

~~~json
{
  "lease_id": "database/creds/orders-readonly/<id-thuc-te>",
  "lease_duration": 3600,
  "renewable": true,
  "data": {
    "username": "v-orders-<username-vi-du>",
    "password": "<REDACTED>"
  }
}
~~~

Đây là **giá trị minh họa**, không dùng chúng làm credential thật.

### Các thuộc tính cần ghi nhớ

| Trường | Ý nghĩa | Tác động đến ứng dụng |
|---|---|---|
| `data.username` | Tài khoản DB vừa tạo | Cấu hình username cho JDBC/DataSource |
| `data.password` | Mật khẩu dùng với tài khoản đó | Chỉ lưu trong vùng nhớ/bộ quản lý secret cần thiết |
| `lease_id` | Định danh lease của lần cấp | Dùng để theo dõi, gia hạn hoặc thu hồi nếu được phép |
| `lease_duration` | Thời gian hiệu lực tính theo giây (trong JSON API) | Lập lịch renewal và chuyển credentials trước khi hết hạn |
| `renewable` | Lease có hỗ trợ gia hạn hay không | Không bảo đảm gia hạn vô hạn: vẫn có giới hạn TTL/max TTL khác |

Mỗi lần đọc `database/creds/orders-readonly` có thể tạo **một tài khoản mới**. Không gọi endpoint này cho từng request HTTP của dịch vụ hoặc từng câu SQL. Thay vào đó, quản lý credentials theo vòng đời **một instance ứng dụng hoặc một nhóm connection pool**, tái sử dụng cho những connection còn hợp lệ và xoay khi cần.

## 7. Hai loại thời hạn: token và secret lease

**Vault token** là danh tính cho phép ứng dụng nói chuyện với Vault. **Database secret lease** là vòng đời riêng của username/password vừa được cấp.

| Đối tượng | Được tạo khi nào? | Hết hạn/thành phần quản lý | Điều dễ nhầm |
|---|---|---|---|
| Vault service token | Workload đăng nhập auth method | Session manager/Token TTL, renewal hoặc re-auth | Token không phải mật khẩu PostgreSQL |
| Database credentials lease | Workload đọc `database/creds/<role>` | Vault lease manager và database plugin | Lease này không đương nhiên kéo dài theo token |
| PostgreSQL account validity | Plugin tạo role với `VALID UNTIL` hoặc logic tương đương | PostgreSQL và SQL renew/revoke | Có thể khác hiệu lực lease nếu SQL/plugin không hoạt động như mong đợi |
| JDBC connection đang mở | DataSource tạo physical connection | PostgreSQL và pool quản lý | Một kết nối đang mở có thể tồn tại sau khi password hoặc account thay đổi; không mặc định bị ngắt tức thời |

Ví dụ vòng đời:

~~~mermaid
flowchart TD
    A["Workload đăng nhập Vault"] --> B["GET database/creds/orders-readonly"]
    B --> C["Vault tạo account DB và lease 1 giờ"]
    C --> D["JDBC pool kết nối bằng credentials mới"]
    D --> E{"Lease còn renewal được?"}
    E -->|Có| F["Gia hạn trước khi hết hạn"]
    F --> G["Kiểm chứng TTL mới và account còn sử dụng được"]
    G --> E
    E -->|Không hoặc gần giới hạn cuối| H["Yêu cầu credentials mới và khởi tạo pool mới"]
    H --> I["Chuyển traffic và drain kết nối cũ"]
    I --> J["Revoke lease cũ theo quy trình"]
    J --> K["Giám sát DB account cleanup"]
~~~

Các lệnh Lease CLI dành cho operator hoặc chủ thể có capability cần thiết:

~~~bash
# Thay <LEASE_ID_THUC_TE> bằng lease_id Vault đã trả về.
vault lease lookup "<LEASE_ID_THUC_TE>"

# Gia hạn khi lease hợp lệ và có thể gia hạn.
vault lease renew "<LEASE_ID_THUC_TE>"

# Thu hồi khi credential không còn cần sử dụng.
vault lease revoke "<LEASE_ID_THUC_TE>"
~~~

Nên lưu ý:

1. Gia hạn lease chỉ được thực hiện khi hợp lệ, còn quyền, chưa hết hạn và chưa vượt giới hạn TTL; có thể phải **xin credential mới** khi chạm max TTL.
2. Thu hồi lease có thể làm tài khoản DB không đăng nhập được nữa; tránh revoke trước khi đổi DataSource và xử lý giao dịch đang hoạt động.
3. Khi token cha bị thu hồi/hết hạn, các leases gắn với token có thể bị Vault thu hồi theo cây phụ thuộc. Workload re-auth phải có cơ chế tiếp tục quản lý secrets/leases hợp lệ.
4. PostgreSQL có thể không ngắt ngay mọi session đã thiết lập chỉ vì `VALID UNTIL` hoặc password thay đổi. Cần kiểm thử cụ thể hành vi plugin, DB, pool và quy trình revoke.
5. Vault không nhất thiết xóa tài khoản tại đúng từng mili-giây của thời điểm TTL; quan sát cả trạng thái lease và trạng thái account trong DB, đặc biệt khi DB không truy cập được.

## 8. Phân quyền workload: Vault ACL và quyền SQL

Ví dụ **policy tối thiểu** để ứng dụng lấy credential của đúng role:

~~~hcl
# orders-api-database.hcl
path "database/creds/orders-readonly" {
  capabilities = ["read"]
}
~~~

Không nên cấp các quyền này cho ứng dụng chỉ đọc đơn hàng:

~~~hcl
# Ví dụ anti-pattern, không triển khai cho workload thông thường:
path "database/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

path "sys/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
~~~

Những quyền cần chia rõ:

- **Database operator** quản lý `database/config/*`, `database/roles/*`, cấu hình SQL tạo/thu hồi và root credential rotation.
- **Workload** chỉ có `read` ở `database/creds/orders-readonly`, có thể thêm quyền quản lý lease theo đúng cơ chế triển khai.
- **Database account được cấp** chỉ có quyền SQL từ `creation_statements` / group `orders_reader`; không tự có quyền ghi chỉ vì Vault token từng mang quyền đọc secret.

Kiểm tra khả năng nhận diện role và ranh giới bằng token của workload:

~~~bash
vault token capabilities database/creds/orders-readonly
vault token capabilities database/creds/orders-readwrite
vault token capabilities database/roles/orders-readonly
vault token capabilities database/config/orders-db
~~~

Kỳ vọng token ứng dụng được `read` tại `database/creds/orders-readonly` và không có quyền quản trị role/config hoặc sinh credentials của role khác. **Việc role được liệt kê trong `allowed_roles` của database connection không thay thế kiểm tra ACL của Vault token.**

Quyền đối với endpoint lease của Vault phụ thuộc session và policy; dùng quản lý lease có sẵn của Spring Vault khi phù hợp. Nếu một ứng dụng cần quyền bổ sung để thực hiện renew/revoke theo thiết kế, kiểm chứng bằng token thật với tài liệu phiên bản Vault hiện dùng, tránh gán toàn quyền `sys/leases/*`.

## 9. Đọc dynamic credentials bằng Spring Vault

`VaultTemplate` cung cấp thao tác đọc API Vault qua `VaultOperations`. Đoạn mã Java sau minh họa một lần nhận credential cùng metadata lease cho dịch vụ, không triển khai scheduler/connection pool:

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

public final class OrdersDatabaseCredentialProvider {

    private static final String CREDS_PATH =
            "database/creds/orders-readonly";

    private final VaultOperations vault;

    public OrdersDatabaseCredentialProvider(VaultOperations vault) {
        this.vault = Objects.requireNonNull(vault);
    }

    public IssuedCredential issue() {
        VaultResponse response = vault.read(CREDS_PATH);
        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Vault returned no database credentials");
        }

        Map<String, Object> data = response.getData();
        Object username = data.get("username");
        Object password = data.get("password");

        if (!(username instanceof String) || !(password instanceof String)) {
            throw new IllegalStateException("Vault response missing username/password");
        }

        return new IssuedCredential(
                (String) username,
                (String) password,
                response.getLeaseId(),
                response.getLeaseDuration(),
                response.isRenewable());
    }

    // Không dùng record.toString() trong log vì chứa password.
    public record IssuedCredential(
            String username,
            String password,
            String leaseId,
            long leaseDurationSeconds,
            boolean renewable) {
    }
}
~~~

Cách sử dụng tổng thể:

1. `VaultOperations` được Spring cấu hình với Vault URI, TLS trust và session manager. Auth method thực tế có thể là Kubernetes auth hoặc AppRole, tùy môi trường; tuyệt đối không nhúng root token.
2. `issue()` gọi endpoint cấp mới; **không chạy mỗi lần lấy một JDBC connection**.
3. Username/password phải được chuyển có kiểm soát sang DataSource/connection pool, trong khi `leaseId` và TTL được giao cho thành phần quản lý vòng đời.
4. Nếu một lần gọi bị lỗi, không tự động retry vô hạn vì có thể tạo thêm account khi request đầu đã được server xử lý nhưng client timeout.
5. `IssuedCredential` chứa password dạng `String` nên không đưa object này vào log, trace, exception message hoặc metric tags; giữ thời gian lưu trong bộ nhớ ngắn nhất có thể.

Ví dụ cấu hình JDBC ở mức khởi tạo pool (sử dụng HikariCP):

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public HikariDataSource createPool(
        OrdersDatabaseCredentialProvider.IssuedCredential issued) {

    HikariConfig config = new HikariConfig();
    config.setJdbcUrl("jdbc:postgresql://postgres.internal:5432/orders");
    config.setUsername(issued.username());
    config.setPassword(issued.password());
    config.setMaximumPoolSize(10);
    config.setPoolName("orders-readonly");

    return new HikariDataSource(config);
}
~~~

Đây là phần minh họa cách **áp dụng** credential mới; việc gắn lifecycle bean, đóng pool và chuyển pool khi rotation phải được thiết kế ở tầng application. Với JDBC TLS, bổ sung cấu hình trust/hostname phù hợp; không coi tên `postgres.internal` là URL thật có thể truy cập.

## 10. Renewal và rotation trong Spring Vault

Spring Vault có **`SecretLeaseContainer`** để đăng ký secrets theo path và theo dõi các sự kiện renewal, rotation, expiry và lỗi. Với đường dẫn `database/creds/orders-readonly`, cơ chế này giúp tránh phải tự viết vòng `sleep` đọc Vault liên tục.

Hai hướng tích hợp:

| Cách | Khi nên dùng | Việc ứng dụng vẫn cần xử lý |
|---|---|---|
| `VaultTemplate` / `VaultOperations.read` trực tiếp | Muốn kiểm soát rõ từng lệnh đọc/renew/revoke | Xây dựng một lifecycle manager và đồng bộ connection pool |
| `SecretLeaseContainer` hoặc abstraction quản lý secret của Spring Vault | Cần gia hạn hoặc xoay theo sự kiện lease | Lắng nghe secret mới, đổi DataSource, chuyển connection an toàn |
| Spring Cloud Vault Database integration | Ứng dụng Spring Boot cần lấy credentials qua cấu hình property source | Kiểm chứng cơ chế refresh/rotation thực sự cập nhật DataSource/pool trong phiên bản dùng |

Sơ lược cách yêu cầu secret xoay vòng với API `SecretLeaseContainer`:

~~~java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.lease.SecretLeaseContainer;
import org.springframework.vault.core.lease.domain.RequestedSecret;
import org.springframework.scheduling.TaskScheduler;

// Các bean này được tạo/điều phối trong Spring configuration.
SecretLeaseContainer container =
        new SecretLeaseContainer(vaultOperations, taskScheduler);

RequestedSecret requested =
        container.requestRotatingSecret("database/creds/orders-readonly");

// Đăng ký listener xử lý sự kiện cấp/rotate/error trước khi start.
// Listener nghiệp vụ phải cập nhật DataSource theo credentials mới
// và thực hiện chuyển pool an toàn, không log nội dung secret.

container.afterPropertiesSet();
container.start();
~~~

Mẫu này chỉ thể hiện quá trình đăng ký, chưa phải cấu hình production hoàn chỉnh: container cần được quản lý bởi Spring lifecycle, có listeners phù hợp và cleanup khi bean bị hủy. **`requestRotatingSecret` có thể renew lease trong thời gian hợp lệ rồi mới xin credentials mới khi cần**, tùy trạng thái, giới hạn lease và chính sách. Event không bảo đảm xảy ra chính xác tại thời điểm TTL; phải thiết kế biên an toàn.

### Vì sao thay password trên DataSource chưa đủ?

Một `HikariDataSource` có thể đang giữ nhiều kết nối vật lý đã đăng nhập bằng username cũ. Khi có credentials mới:

1. Chuẩn bị một pool mới với username/password mới (hoặc triển khai luồng reconfigure được thư viện hỗ trợ).
2. Kiểm tra pool mới kết nối được bằng một câu lệnh đơn giản, ví dụ `SELECT 1`.
3. Chuyển request mới sang pool mới; chờ hoàn tất giao dịch đang chạy trên pool cũ.
4. Đóng/drain pool cũ rồi mới thu hồi lease cũ khi quy trình cho phép.
5. Nếu rotation thất bại, phát cảnh báo và giữ trạng thái an toàn; không âm thầm kéo dài việc dùng account đã hết hiệu lực.

Không tự giả định rằng Spring Cloud Vault cập nhật `spring.datasource.password` là tất cả JDBC connections đã nhận credentials mới. Phần ứng dụng sử dụng DataSource phải có cơ chế tái tạo hoặc cập nhật pool tương thích.

## 11. Kiểm thử tích hợp từ cấp phát đến revoke

Kiểm thử thực sự cần Vault và PostgreSQL chạy trong môi trường có thể kiểm soát. Mock `VaultTemplate` chỉ kiểm chứng logic Java, **không chứng minh** database plugin tạo user, ACL được thực thi, SQL grants đúng hoặc lease được revoke. Có thể dùng Testcontainers/containers trong môi trường CI nếu dự án hỗ trợ; không phụ thuộc tài nguyên database production.

### Bộ ca kiểm thử chính

| Mã | Điều kiện đầu vào | Hành vi kiểm tra | Kỳ vọng |
|---|---|---|---|
| P01 | Workload token được `read` path role | `GET database/creds/orders-readonly` | Nhận username/password và `lease_id`/TTL hợp lệ |
| P02 | Credential vừa được cấp | JDBC `SELECT` trên bảng đơn hàng | Thành công |
| N01 | Cùng credential readonly | JDBC `INSERT` hoặc `UPDATE` vào bảng đơn hàng | DB từ chối do thiếu SQL privileges |
| N02 | Workload token readonly | Đọc `database/creds/orders-readwrite` | Vault từ chối ACL |
| N03 | Workload token readonly | Sửa `database/roles/orders-readonly` | Vault từ chối ACL |
| P03 | Lease hỗ trợ gia hạn, còn trong giới hạn | Renew qua cơ chế phù hợp | TTL mới được phản ánh; user DB vẫn đăng nhập được |
| P04 | Lease bị revoke bằng danh tính đủ quyền | Kiểm tra login **mới** của account cũ | Login mới bị từ chối sau khi DB thu hồi thành công |
| P05 | Sau rotation | App kết nối bằng credential mới | Truy vấn tiếp tục chạy; pool cũ được giải phóng |
| N04 | Vault bị ngắt hoặc token hết hạn | Yêu cầu credential mới | Hệ thống báo lỗi rõ, không in secret và không tạo vòng cấp phát vô hạn |
| N05 | DB không thể chạy SQL revoke | Quan sát lease cleanup/audit | Lỗi revocation được phát hiện và xử lý theo runbook |

Các ca P03–P05 cần chờ/sắp lịch có kiểm soát, không viết test chờ hết TTL hàng giờ. Đối với revoke, dùng lệnh tường minh và kiểm chứng bằng **phiên JDBC mới**. Một connection được mở trước khi account bị thu hồi có thể vẫn hoạt động tùy DB/plugin, nên không dùng nó làm bằng chứng duy nhất về kết quả revoke.

### Ví dụ JUnit 5: credential được tạo và chỉ có quyền đọc

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.core.VaultOperations;

// Bài test tích hợp: Vault + PostgreSQL đã có fixture riêng.
@SpringBootTest
class DynamicDatabaseCredentialIT {

    @Autowired
    private VaultOperations vault;

    @Test
    void issuedUserCanReadButCannotWrite() throws Exception {
        var issued = new OrdersDatabaseCredentialProvider(vault).issue();

        assertFalse(issued.username().isBlank());
        assertFalse(issued.password().isBlank());
        assertNotNull(issued.leaseId());

        // Sau test, fixture phải đóng connection và thu hồi lease
        // bằng quyền quản trị phù hợp (kể cả khi assertion thất bại).
        try (Connection connection = DriverManager.getConnection(
                "jdbc:postgresql://postgres.internal:5432/orders",
                issued.username(), issued.password());
             Statement statement = connection.createStatement()) {

            try (ResultSet rows =
                     statement.executeQuery("SELECT id FROM orders LIMIT 1")) {
                // Query thành công chứng minh có quyền SELECT trên bảng orders.
            }

            SQLException denied = assertThrows(SQLException.class, () ->
                    statement.executeUpdate(
                            "INSERT INTO orders(id) VALUES (-1)"));
            assertEquals("42501", denied.getSQLState());
        }
    }
}
~~~

Đoạn này minh họa phương pháp, **chưa phải class test có thể chạy ngay**: thay phần `provider` bằng dependency injection/fixture, cấp database/role đúng tên và chọn một phép ghi không hợp lệ về **quyền SQL** (không phải lỗi schema, constraint hay cú pháp). Để chứng minh `readonly`, nên dùng một bảng test chuyên biệt với schema cố định, cấp `SELECT` nhưng không cấp `INSERT`, sau đó phân tích SQLSTATE `insufficient_privilege` (PostgreSQL `42501`). Nếu lệnh `INSERT` thất bại do bảng không tồn tại, test chưa chứng minh quyền bị từ chối.

Một harness hoàn chỉnh còn phải quản lý cleanup trong `finally` hoặc test lifecycle hook, tránh tích lũy username và lease sau mỗi lần chạy. Không ghi password trong exception hoặc toàn bộ đối tượng `IssuedCredential` vào báo cáo test.

## 12. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| `permission denied` khi `GET database/creds/...` | Vault token thiếu `read`, namespace/role sai | Kiểm tra ACL và workload identity; không mở `database/*` |
| `role not allowed` / không cấp được credential | Role không nằm trong `allowed_roles` của DB config | Đối chiếu `database/config/...` và `database/roles/...` |
| Database plugin báo authentication failure | Credentials quản trị DB sai, bị rotate, TLS trust sai hoặc thiếu quyền | Kiểm tra kết nối DB manager từ Vault và cấu hình TLS |
| Lỗi SQL khi cấp user | `creation_statements` sai cú pháp, thiếu quyền tạo/grant role | Thử SQL trên PostgreSQL test với quyền quản trị tương ứng |
| Vault cấp credential nhưng JDBC kết nối lỗi | Host/port/TLS, Pg `pg_hba.conf`, account hết hiệu lực | Kiểm tra từ máy chạy app bằng username được cấp, không log password |
| JDBC đọc được nhưng ghi cũng thành công | Role SQL quá rộng hoặc group grants sai | Rà soát membership, object privileges và `PUBLIC` grants |
| Renewal trả thành công nhưng login mới fail | PostgreSQL `VALID UNTIL` không được cập nhật, SQL renewal sai | Kiểm tra `renew_statements` và trạng thái DB account |
| Lỗi sau vài giờ chạy | Lease chạm max TTL, token hết hạn, không rotate pool | Giám sát lease, renewal, auth và pool switching |
| Revoke thất bại | User có dependency hoặc DB mất kết nối | Kiểm tra plugin revocation statements, session, ownership và retry theo runbook |
| Nhiều user rác trong PostgreSQL | App đọc `database/creds` quá thường xuyên hoặc revoke lỗi | Chỉ cấp theo vòng đời instance/pool, quan sát số lease và cleanup |

### Phân biệt bốn nguồn lỗi quan trọng

- **Vault ACL:** workload không được gọi endpoint để xin username/password.
- **Vault database role/plugin:** request đến Vault thành công về mặt ACL nhưng cấu hình connection, SQL hoặc quyền DB manager không cho phép tạo user.
- **PostgreSQL SQL privilege:** username/password hợp lệ, nhưng SQL `INSERT`/`UPDATE` bị từ chối.
- **Lease và connection lifecycle:** credential từng dùng được, sau đó không còn hợp lệ do TTL, token revocation hoặc pool chưa được xoay.

Khi xử lý sự cố, log đường dẫn request (đã lọc dữ liệu nhạy cảm), `request_id` của Vault, loại lỗi, role name, TTL còn lại và thông tin kết nối đã che danh tính nếu cần. **Không log password, token, raw Vault response hay URL kết nối có mật khẩu**.

## 13. Bảo mật và giám sát khi đưa vào production

**Thiết kế policy theo workload:** một service chỉ đọc có role riêng, một service ghi có role khác. Dùng token cấp theo Kubernetes/AppRole thực tế, tránh token root, và đặt tên role giúp điều tra được các account sinh ra.

**Giới hạn quyền ở database:** chỉ cấp những quyền SQL bắt buộc, kiểm thử quyền âm tính. Không để credential động sở hữu bảng hoặc schema trừ khi nhiệm vụ thật sự cần; quyền sở hữu object dễ khiến revoke không thể `DROP ROLE`.

**Giám sát tuổi thọ credential:** thống kê lần cấp mới, renewal, rotation và revoke, tỉ lệ thất bại của plugin, số dynamic DB accounts còn tồn tại, số kết nối đang mở, TTL còn lại và token authentication errors. Đối chiếu audit log Vault với PostgreSQL login/role, nhưng không log secret values.

**Thận trọng với kết nối quản trị:** database manager trong Vault là tài sản đặc biệt nhạy cảm. Hạn chế đường mạng từ Vault đến DB, cấu hình TLS verify và xem xét xoay password quản trị qua chức năng được plugin hỗ trợ.

**Xử lý mất Vault tạm thời:** không yêu cầu DB credentials trên mỗi truy vấn. Khi Vault bị gián đoạn, những connection đã được mở và lease còn hợp lệ có thể giúp duy trì luồng công việc hiện tại, nhưng **không giả định credential cũ sẽ được chấp nhận vô hạn**. Có chiến lược retry có giới hạn, cảnh báo sớm trước expiry, và chính sách ứng dụng khi không thể lấy secret mới.

**Khôi phục sự cố:** nếu token bị thu hồi hoặc database plugin không revoke được user, cần quy trình đối soát username/lease, xử lý DB account tồn dư và cấp lại credential. Xác nhận quyền làm cleanup trước khi can thiệp; không tự ý xóa các account có thể thuộc workload khác.

## 14. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành A: hai role khác nhau

Từ connection `orders-db`, cấu hình hai role:

- `orders-readonly`: chỉ `SELECT` trên các bảng dữ liệu đơn hàng.
- `orders-readwrite`: `SELECT` và quyền cập nhật đúng bảng/trường cần cho worker, không tự do tạo/xóa schema.

Gán mỗi role cho một Vault policy. Đăng nhập bằng hai workload tokens và chứng minh:

1. Token readonly không xin được credential của role readwrite.
2. User được cấp từ role readonly thực hiện `SELECT` thành công nhưng `INSERT` hoặc `UPDATE` bị PostgreSQL từ chối với lý do đúng quyền.
3. User role readwrite chỉ thực hiện được những câu SQL nằm trong quyền đã cấp.
4. Mỗi lần cấp tạo lease riêng; thu hồi một lease không được làm ảnh hưởng nhầm account của lease khác.

### Bài thực hành B: vòng đời lease

Tạo role test với TTL đủ ngắn để quan sát, nhưng không thấp đến mức test bị lỗi do lệch lịch trình. Thực hiện cấp mới → dùng JDBC → renew (nếu được phép) → yêu cầu credential mới → chuyển connection → revoke credential cũ. Ghi lại các mốc **lease ID**, **TTL**, trạng thái đăng nhập PostgreSQL và số connection còn sống, tuyệt đối không ghi password.

### Câu hỏi

1. Vì sao `GRANT SELECT` trong PostgreSQL mới là nguồn quyền đọc SQL, còn Vault ACL `read` trên `database/creds/<role>` chỉ cho phép xin credential?
2. Vì sao không nên đọc `database/creds/orders-readonly` mỗi lần xử lý HTTP request?
3. Khi lease được renew nhưng PostgreSQL account không đăng nhập được sau một giờ, nên kiểm tra cấu hình nào?
4. Việc nhận một username/password mới từ Vault có bảo đảm mọi connection trong HikariCP dùng tài khoản mới không?
5. Vì sao test `SELECT 1` thành công chưa đủ để chứng minh role có quyền đọc bảng nghiệp vụ và bị cấm ghi?
6. Dynamic role và static role của Database secrets engine khác nhau ra sao?

## 15. Tổng kết

**Database secrets engine** cho phép ứng dụng Java nhận database credentials **động theo role** thay vì giữ một mật khẩu dùng chung dài hạn. Role trong Vault định nghĩa connection, câu lệnh SQL tạo/renew/revoke và thời hạn credential; ACL của token quyết định workload có được xin credential theo role đó không. Quyền truy cập dữ liệu thực tế vẫn được thực thi bởi PostgreSQL hoặc hệ quản trị CSDL tương ứng.

Với Spring Vault, `VaultTemplate`/`VaultOperations` dùng để lấy secret và metadata lease, còn `SecretLeaseContainer` cùng cơ chế Spring Cloud Vault liên quan có thể hỗ trợ renewal/rotation. Thành công trong production đòi hỏi **hai chu kỳ vòng đời phối hợp**: token/lease của Vault và database account/JDBC connection pool. Kiểm thử phải chứng minh vừa cấp phát đúng và giới hạn SQL đúng, vừa xử lý được renewal, cấp lại, revoke và failure cleanup.

### Tài liệu tham khảo

- [HashiCorp Vault — Database secrets engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [HashiCorp Vault — PostgreSQL database secrets engine](https://developer.hashicorp.com/vault/docs/secrets/databases/postgresql)
- [HashiCorp Vault — Database secrets engine HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/databases)
- [HashiCorp Vault — PostgreSQL plugin HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/databases/postgresql)
- [HashiCorp Vault — Lease, renew, revoke](https://developer.hashicorp.com/vault/docs/concepts/lease)
- [Spring Vault — Credentials Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [Spring Vault — `VaultResponse` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultResponse.html)
