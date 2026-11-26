# Tích hợp cơ sở dữ liệu với thông tin xác thực động

## 1. Vì sao ứng dụng nên dùng thông tin xác thực động?

Một ứng dụng Spring Boot thường cần `username` và `password` để kết nối PostgreSQL, MySQL hoặc một cơ sở dữ liệu khác. Nếu dùng cùng một tài khoản tĩnh trong nhiều tháng, việc lộ mật khẩu từ biến môi trường, cấu hình CI/CD, log hay bản sao lưu có thể cho phép truy cập lâu dài. Đổi mật khẩu chung cũng khó vì phải cập nhật đồng bộ nhiều service, pod và connection pool.

**HashiCorp Vault Database secrets engine** cho phép một workload **yêu cầu thông tin xác thực cơ sở dữ liệu được cấp động**. Vault giao tiếp với database thông qua plugin, tạo hoặc quản lý một tài khoản theo role đã cấu hình, trả `username`/`password` và một **lease** có thời gian sử dụng giới hạn. Ứng dụng dùng credential để tạo kết nối; Vault có thể gia hạn lease khi được phép và thu hồi credential khi hết hạn hoặc có yêu cầu revoke.

Trong module **Spring Vault (SPRING_VAULT)**, Java có thể truy cập Vault bằng `VaultTemplate`/`VaultOperations`, xác thực theo workload và policy tối thiểu. Khi tích hợp với Spring Boot, cần hiểu cả hai phía: **lấy và quản lý lease trong Vault** và **quản lý vòng đời connection pool JDBC ở ứng dụng**.

Bài này thuộc chương **Tích hợp ứng dụng** với chủ đề **Tích hợp cơ sở dữ liệu với thông tin xác thực động**. Mục tiêu:

- Phân biệt Database dynamic credentials với KV secret chứa mật khẩu tĩnh.
- Cấu hình khái niệm database connection, database role, TTL và policy.
- Lấy `database/creds/<role>` từ Spring Vault hoặc dùng tích hợp Spring Cloud Vault.
- Phân biệt vòng đời **Vault auth token**, **database credential lease** và **JDBC connection**.
- Xử lý cấp mới, gia hạn, hết hạn, thu hồi và chuyển pool khi credential thay đổi.
- Thiết kế lỗi, metrics, kiểm thử tích hợp và quy trình ứng cứu phù hợp.

## 2. Kiến trúc và các thành phần

### 2.1. Vault không thay ứng dụng kết nối database

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Spring Boot / Spring Vault
    participant Vault as Vault Database engine
    participant DB as PostgreSQL
    App->>Vault: GET database/creds/orders-readonly
    Note over App,Vault: TLS + workload Vault token
    Vault->>DB: Tạo account tạm + gán quyền
    DB-->>Vault: Account tạo thành công
    Vault-->>App: username, password, lease_id, TTL
    App->>DB: JDBC/TLS login bằng credential tạm
    DB-->>App: Kết nối hợp lệ
    Note over App,DB: Hikari pool giữ connection đã tạo
    App->>Vault: Renew lease trước hạn nếu được phép
    Vault-->>App: Lease duration mới (nếu gia hạn thành công)
    Note over Vault,DB: Hết hạn/revoke: Vault chạy logic thu hồi của plugin
~~~

Ứng dụng vẫn gửi SQL qua JDBC như bình thường; Vault **không** đứng giữa mọi câu truy vấn. Vault điều khiển việc **cấp quyền kết nối**, quản lý lease và thực hiện thao tác thu hồi credential với database. Vì vậy tốc độ truy vấn sau khi kết nối chủ yếu chịu ảnh hưởng database, driver, SQL và pool, chứ không đi qua Vault ở mỗi câu lệnh.

### 2.2. Ba loại vòng đời phải phân biệt

| Thành phần | Ví dụ | Quyết định điều gì? | Cần quản lý ở đâu? |
| --- | --- | --- | --- |
| **Vault authentication token** | Kubernetes/JWT/AppRole login | Workload có được gọi API Vault hay không | Spring Vault session và auth method |
| **Dynamic credential lease** | `database/creds/orders-readonly/…`, TTL 15 phút | Credential DB có thời gian hợp lệ bao lâu, có thể gia hạn/thu hồi không | Vault Database engine và lease lifecycle |
| **JDBC connection / pool** | PostgreSQL connection trong HikariCP | Kết nối đang tồn tại, thời gian tái sử dụng, mở kết nối mới bằng credential nào | Driver JDBC/HikariCP/ứng dụng |

Ví dụ: Vault token của service có TTL một giờ nhưng credential database có TTL 15 phút. Token hết hạn **không mặc nhiên khiến các kết nối JDBC hiện tại bị đóng**; ngược lại, credential bị revoke có thể làm kết nối mới thất bại dù auth token vẫn hợp lệ. Tùy DB và revocation statements, các session đã mở có thể tiếp tục hoạt động hoặc bị gián đoạn: phải kiểm thử thực tế trên database đang dùng.

**KV secrets engine** chứa một mật khẩu lưu sẵn, có thể phiên bản hóa (KV v2); việc đọc lại KV không tự tạo user database mới. **Database dynamic secrets** tạo/ghi nhận credential theo database role và lease; `lease_id` là phần nhận diện quan trọng trong quy trình gia hạn hoặc thu hồi.

## 3. Thiết lập Database secrets engine và vai trò database

Các ví dụ sau dùng PostgreSQL và tên minh họa:

- Mount: `database`
- Database connection của Vault: `orders-postgres`
- Role cấp động: `orders-readonly`
- Bảng ứng dụng được đọc: `public.orders`
- Workload: `orders-api`

**Chỉ người quản trị hạ tầng/database** thực hiện provisioning engine và plugin. Ứng dụng không cần quyền tạo hoặc sửa database roles. Credential tài khoản quản trị DB dùng bởi plugin phải được cấp qua kênh bảo mật, không đưa vào source code, ví dụ học tập hay CI logs.

### 3.1. Bật engine và khai báo kết nối

~~~bash
# Quản trị viên: bật engine tại mount "database" (chỉ khi chưa bật).
vault secrets enable -path=database database

# Kiểm tra các đường dẫn config/roles đã được chuẩn bị.
vault list database/config
vault list database/roles
~~~

Để Vault có thể tạo tài khoản PostgreSQL, quản trị viên cần cấu hình database connection thông qua endpoint `database/config/orders-postgres` với plugin tương ứng, connection URL, tài khoản quản trị được cấp quyền tạo/revoke user và `allowed_roles`. Ví dụ cấu trúc khai báo (giá trị mật khẩu được cấp qua cơ chế bí mật khi deploy, **không hardcode vào lệnh này**):

~~~text
POST /v1/database/config/orders-postgres
  plugin_name:    postgresql-database-plugin
  allowed_roles:  orders-readonly
  connection_url: postgresql://{{username}}:{{password}}@db.internal:5432/orders?sslmode=verify-full
  username:       <VAULT_DB_ADMIN_USER>
  password:       <PROVIDED_SECURELY_AT_PROVISIONING>
~~~

Vault Database plugin dùng tài khoản quản trị kết nối trực tiếp tới PostgreSQL để tạo user theo quyền được cấp. Mẫu trên mang tính mô tả cấu trúc API; **cần thiết lập chứng chỉ TLS/CA cho PostgreSQL và sử dụng phương thức cung cấp password bảo mật** trong provisioning thật.

### 3.2. Database role và câu lệnh cấp quyền

Database role `orders-readonly` xác định *cách Vault tạo credential* và *quyền SQL user mới có*. Ví dụ `creation_statements` của PostgreSQL:

~~~sql
-- Template do Vault PostgreSQL plugin render khi cấp credential.
-- Dấu {{...}} là placeholder của plugin, không phải biến Java.
CREATE ROLE "{{name}}" WITH LOGIN PASSWORD '{{password}}'
    VALID UNTIL '{{expiration}}';
GRANT CONNECT ON DATABASE orders TO "{{name}}";
GRANT USAGE ON SCHEMA public TO "{{name}}";
GRANT SELECT ON TABLE public.orders TO "{{name}}";
~~~

Cấu hình database role (hình dạng CLI, đường dẫn SQL đọc từ file provisioning được quản trị kiểm soát):

~~~bash
vault write database/roles/orders-readonly \
  db_name=orders-postgres \
  creation_statements=@orders-readonly.sql \
  default_ttl=15m \
  max_ttl=1h
~~~

Đây là ví dụ cho hệ thống test có plugin hỗ trợ file argument. Cần kiểm chứng cú pháp tạo user, cách quote tên, schema/table privileges và câu lệnh thu hồi theo phiên bản PostgreSQL/Vault đang triển khai. PostgreSQL còn cần xử lý quyền và phụ thuộc object khi drop role; test quy trình revoke trước khi áp dụng vào production.

**Principle of least privilege:** role đọc đơn thuần không cần `INSERT`, `UPDATE`, `DELETE`, `CREATE`, quyền quản trị database hay quyền đọc mọi schema. Đối với API có nhu cầu ghi, nên tạo database role riêng với grant rõ ràng.

### 3.3. Policy Vault dành cho workload

Workload chỉ cần đọc credential thuộc role:

~~~hcl
# orders-api-database.hcl
path "database/creds/orders-readonly" {
  capabilities = ["read"]
}
~~~

Quản trị viên áp dụng policy:

~~~bash
vault policy write orders-api-database orders-api-database.hcl
~~~

Quyền `read` trên `database/creds/orders-readonly` cho phép yêu cầu **credential mới**, không phải đọc lại một tài khoản dùng chung. Không cấp quyền `database/config/*`, `database/roles/*`, `sys/mounts/*` hay token root cho service. Nếu ứng dụng phải chủ động gia hạn hoặc thu hồi lease, chính sách cho các endpoint liên quan cần được cấp **có giới hạn và kiểm tra riêng**, tránh wildcard bao trùm mọi lease.

## 4. Cấp credential động qua Vault CLI và HTTP API

### 4.1. Lấy thông tin xác thực

~~~bash
# Chỉ chạy trong môi trường test có token hợp lệ.
vault read database/creds/orders-readonly
~~~

Vault trả về giá trị như sau (đã thay bằng dữ liệu minh họa):

~~~text
Key                Value
---                -----
lease_id           database/creds/orders-readonly/abcd...
lease_duration     15m
lease_renewable    true
username           v-orders-ro-xyz
password           <SECRET>
~~~

API tương ứng là `GET /v1/database/creds/orders-readonly`. JSON phản hồi thường có dạng:

~~~json
{
  "lease_id": "database/creds/orders-readonly/abcd...",
  "renewable": true,
  "lease_duration": 900,
  "data": {
    "username": "v-orders-ro-xyz",
    "password": "<REDACTED_PASSWORD>"
  }
}
~~~

**Lưu ý:** đọc endpoint lần thứ hai có thể phát hành credential **khác**, lease mới và DB user mới. Không coi đây là thao tác `getCurrentPassword()` để lấy lại cùng giá trị. Chương trình phải quản lý đúng lease của tài khoản được pool đang sử dụng.

### 4.2. Cách dùng credential

Một ứng dụng Java có thể nhận username/password từ Spring Vault, rồi tạo JDBC `DataSource` dùng TLS:

~~~text
Vault: database/creds/orders-readonly
          |
          v
username + password + lease metadata
          |
          v
Spring DataSource / HikariCP
          |
          v
JDBC connections -> PostgreSQL
~~~

Nếu pool chỉ đọc credential khi khởi động, nó sẽ tiếp tục dùng credential đó khi cần mở thêm kết nối. Nếu lease hết hạn và Vault thu hồi user, tạo connection mới có thể thất bại. Vì vậy **cấu hình datasource một lần không đồng nghĩa hệ thống tự luân chuyển credential**.

## 5. Đọc credential bằng Spring Vault

Spring Vault có `VaultOperations` để gọi API, còn `VaultTemplate` là một implementation. Ví dụ Java 17+ dưới đây đọc endpoint database và giữ lease metadata.

### 5.1. Cấu trúc dữ liệu an toàn

~~~java
package com.example.orders.security;

public record LeasedDbCredentials(
        String username,
        String password,
        String leaseId,
        long leaseSeconds,
        boolean renewable) {}
~~~

Trong production, không để record này bị log qua `toString()`, JSON serialize hoặc debug/trace. Dạng `record` chỉ phục vụ học tập; với credential nhạy cảm có thể dùng class chuyên biệt kiểm soát việc hiển thị dữ liệu.

### 5.2. Service lấy lease mới

~~~java
package com.example.orders.security;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class DatabaseCredentialService {

    private static final String PATH = "database/creds/orders-readonly";

    private final VaultOperations vault;

    public DatabaseCredentialService(VaultOperations vault) {
        this.vault = vault;
    }

    public LeasedDbCredentials issue() {
        VaultResponse response = vault.read(PATH);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("No database credentials");
        }

        Map<String, Object> data = response.getData();

        String username = requireString(data, "username");
        String password = requireString(data, "password");

        String leaseId = response.getLeaseId();
        if (leaseId == null || leaseId.isBlank()) {
            throw new IllegalStateException("Missing database lease");
        }

        long leaseSeconds = response.getLeaseDuration();
        if (leaseSeconds <= 0L) {
            throw new IllegalStateException("Invalid database lease duration");
        }

        return new LeasedDbCredentials(
                username,
                password,
                leaseId,
                leaseSeconds,
                response.isRenewable());
    }

    private static String requireString(
            Map<String, Object> data, String key) {
        Object value = data.get(key);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalStateException(
                    "Missing database credential field: " + key);
        }
        return text;
    }
}
~~~

Ví dụ chỉ mô tả **giai đoạn phát hành**. Không gọi `issue()` cho mỗi HTTP request hoặc mỗi câu SQL: mỗi lần đọc có thể tạo một user và lease mới. Nên dùng **một lease được quản lý cho mỗi generation của connection pool**, theo thiết kế HA và chính sách của hệ thống.

Nếu app sử dụng API nâng cao của Spring Vault cho vòng đời lease, hãy gắn chúng vào cơ chế phát hành từ đầu thay vì chạy song song hai bộ quản lý lease.

### 5.3. Khởi tạo một pool từ credential vừa cấp

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

static HikariDataSource newPool(LeasedDbCredentials c) {
    HikariConfig config = new HikariConfig();
    config.setJdbcUrl(
            "jdbc:postgresql://db.internal:5432/orders?sslmode=verify-full");
    config.setUsername(c.username());
    config.setPassword(c.password());
    config.setPoolName("orders-readonly-pool");
    config.setMaximumPoolSize(10);

    // Chỉ là giới hạn tuổi connection, không tự gia hạn DB lease.
    config.setMaxLifetime(300_000L);

    return new HikariDataSource(config);
}
~~~

Đoạn mã là một ví dụ về mặt kỹ thuật, không phải hệ thống pool có thể tự vận hành mãi mãi. Driver cần cấu hình trust CA/database TLS theo môi trường; username và password vẫn có thể tồn tại trong cấu hình pool và bộ nhớ JVM.

**Điểm cốt lõi:** thiết lập `maxLifetime` thấp hơn TTL của lease có thể hạn chế thời gian tái sử dụng connection, nhưng **không tự cập nhật username/password** ở Hikari. Khi credential cũ bị revoke, pool cần được **chuyển sang credential mới** hoặc cần gia hạn lease phù hợp. Kết nối đang hoạt động có thể chưa bị đóng ngay, tùy DB/plugin. Không dùng `maxLifetime` như bằng chứng đã xử lý rotation.

## 6. Tích hợp qua Spring Cloud Vault

Spring Cloud Vault có khả năng đưa secret từ Vault vào Spring Environment khi ứng dụng khởi động. Với backend database, có thể map `username` và `password` thành property của Spring datasource.

Ví dụ minh họa cho ứng dụng Spring Boot có Spring Cloud Vault tương thích, dùng Kubernetes auth:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-api
        kubernetes-path: kubernetes
      database:
        enabled: true
        backend: database
        role: orders-readonly
        username-property: spring.datasource.username
        password-property: spring.datasource.password
  datasource:
    url: "jdbc:postgresql://db.internal:5432/orders?sslmode=verify-full"
    driver-class-name: org.postgresql.Driver
~~~

Đây là mẫu **cấu hình có điều kiện**: thuộc tính, cơ chế import, phiên bản starter và cách bootstrap Vault có thể khác nhau giữa Spring Cloud Vault/Spring Boot releases. Cần xác minh dependencies đang khóa trong dự án; đảm bảo Kubernetes ServiceAccount được Vault auth role cho phép và chứng chỉ TLS của Vault/database được tin cậy.

**Cảnh báo về cập nhật runtime:** việc Spring Cloud Vault đọc secret và có cơ chế quản lý lease không đồng nghĩa `HikariDataSource` đang chạy được tự động dựng lại với account mới. Spring Environment property đã cập nhật **không bảo đảm** bean datasource đã khởi tạo sẽ đổi credentials hoặc các kết nối cũ biến mất. Phải kiểm chứng hành vi làm mới property, lease manager và pool ở phiên bản đang dùng; nếu chưa có cơ chế dựng lại pool an toàn, hãy **gia hạn lease để dùng tiếp** hoặc **thực hiện rotation/recreate pool có điều phối**.

### 6.1. Hai chiến lược quản lý phổ biến

| Chiến lược | Cách hoạt động | Phù hợp khi | Rủi ro cần kiểm tra |
| --- | --- | --- | --- |
| **Giữ credential và renew lease** | Pool tiếp tục dùng account; lease manager renew trước TTL | Job/service dài hạn, database plugin cho renew | Renewal thất bại, bị giới hạn max TTL, Vault/DB sự cố |
| **Lấy credential mới và thay pool** | Issuer cấp user mới, ứng dụng tạo pool mới, chuyển traffic, nghỉ pool cũ | Chống giữ account quá lâu, có HA và điều phối kết nối | Tài nguyên pool đôi, truy vấn đang chạy, rollback và revoke quá sớm |

Hai chiến lược có thể kết hợp: renew trong một khoảng thời gian và chủ động rotate khi đạt giới hạn hoặc theo lịch bảo mật. Với mỗi lần cấp credential mới, phải quản lý đúng lease tương ứng; không làm rơi lease cũ trước khi xử lý cleanup.

## 7. Lease lifecycle: renew, revoke và expiration

### 7.1. Gia hạn một lease

Nếu phản hồi có `renewable: true`, consumer có thể yêu cầu renew khi còn hợp lệ, trong giới hạn cho phép của role/engine:

~~~http
POST /v1/sys/leases/renew
X-Vault-Token: <AUTHORIZED_TOKEN>
Content-Type: application/json

{
  "lease_id": "database/creds/orders-readonly/abcd...",
  "increment": "15m"
}
~~~

Vault có quyền giới hạn thời hạn gia hạn thực tế, từ chối nếu đã hết hạn/bị thu hồi hoặc không cho phép theo role. **Không giả định TTL vừa yêu cầu chính là TTL được chấp nhận**: đọc lại thời hạn từ response mới và lên lịch renew tiếp.

Ví dụ dùng `VaultOperations` cho một lease đã được quản lý:

~~~java
VaultResponse renewed = vaultOperations.write(
        "sys/leases/renew",
        Map.of(
                "lease_id", leaseId,
                "increment", "15m"));

if (renewed == null
        || renewed.getLeaseId() == null
        || renewed.getLeaseDuration() <= 0L) {
    throw new IllegalStateException("Database lease renewal not confirmed");
}
// Ghi lại thời hạn mới; không in leaseId/credential vào log.
~~~

Quyền truy cập lease API phải theo policy và danh tính được cấp, không trao quyền quản lý mọi lease một cách rộng rãi cho toàn bộ ứng dụng. Spring Vault còn có các cơ chế **`SecretLeaseContainer`** và Spring Cloud Vault lease lifecycle để theo dõi gia hạn/rotation. Nếu sử dụng chúng, nên để **một** lease manager chịu trách nhiệm thay vì tự thêm scheduler cạnh tranh.

### 7.2. Thu hồi khi không còn sử dụng

Khi một generation của pool đã được nghỉ hoàn toàn, có thể chủ động revoke lease phù hợp với phân quyền đã cấp:

~~~http
POST /v1/sys/leases/revoke
X-Vault-Token: <AUTHORIZED_TOKEN>
Content-Type: application/json

{
  "lease_id": "database/creds/orders-readonly/abcd..."
}
~~~

Trong triển khai thật, quy trình gồm: ngừng nhận truy vấn mới trên pool cũ → chờ hoặc kết thúc các request đang sử dụng theo timeout/SLA → đóng pool cũ → revoke lease cũ khi an toàn. **Không revoke credential đang được active pool sử dụng** rồi hy vọng mọi truy vấn vẫn thành công.

### 7.3. Gia hạn có thể không thành công

Lease không được bảo đảm có thể renew vô thời hạn: `max_ttl`, cấu hình hệ thống, trạng thái token, chính sách hoặc database plugin có thể chặn. Nếu gần hết thời hạn mà renew thất bại, cần chuẩn bị account/pool thay thế hoặc giảm traffic và báo lỗi có kiểm soát.

Đừng dùng credential hết hạn như một fallback cho lỗi Vault. Một số connection đang mở có thể tiếp tục hoạt động, nhưng không phải cam kết về tính hợp lệ hoặc bảo mật; việc tiếp tục sử dụng ngoài TTL có thể vi phạm chính sách vận hành.

## 8. Vòng đời HikariCP khi credential thay đổi

Đây là phần dễ bị bỏ sót nhất khi tích hợp database dynamic secrets.

### 8.1. Kết nối đã mở và kết nối mới là hai chuyện khác nhau

Khi tạo pool, HikariCP sử dụng username/password để **mở JDBC connection**. Pool tái sử dụng những connection đã mở. Sau khi tài khoản được Vault renew hoặc revoke:

- **Renew lease:** có thể kéo dài hạn sử dụng của DB user mà pool hiện tại đang dùng, nếu plugin/database hỗ trợ và renewal thành công.
- **Revoke lease:** các kết nối mới với user đó thường không thể xác thực; session cũ có thể tiếp tục hoặc bị ngắt tùy database và revocation statements.
- **Cấp username/password mới:** pool hiện tại không mặc nhiên đổi sang user mới chỉ vì Vault Environment có property mới.
- **Credential rotation:** cần cơ chế cấp pool mới hoặc cập nhật cấu hình datasource đồng bộ với connection lifecycle.

### 8.2. Quy trình pool rotation an toàn

~~~mermaid
flowchart TD
    A[Pool A dùng lease A] --> B{Sắp hết hạn hoặc buộc rotate?}
    B -- Chưa --> C[Renew lease A và tiếp tục giám sát]
    B -- Có --> D[Lấy credential mới lease B]
    D --> E[Tạo Pool B, kiểm tra TLS + SELECT 1]
    E --> F{Pool B hoạt động?}
    F -- Không --> G[Giữ A nếu còn lease hợp lệ; cảnh báo]
    F -- Có --> H[Chuyển request mới sang Pool B]
    H --> I[Chờ request cũ hoàn tất hoặc timeout]
    I --> J[Đóng Pool A]
    J --> K[Revoke lease A theo quy trình]
    K --> L[Ghi audit và metrics]
~~~

Sơ đồ chỉ mô tả quy trình logic; để làm thật cần một **routing datasource** hoặc cơ chế lifecycle/rolling deployment phù hợp. Thay `DataSource` bean trong một luồng bất kỳ giữa lúc ứng dụng xử lý transaction có thể làm lỗi các truy vấn đang chạy.

Khi có nhiều Pod, hai phương án thường được cân nhắc:

- Mỗi Pod/instance có credential/lease và pool riêng, cấp và revoke theo lifecycle của Pod.
- Dùng cơ chế triển khai cuốn chiếu (rolling restart) để Pod mới nhận credential mới, Pod cũ drain và dừng trước khi lease cũ hết hạn.

Mỗi phương án đều cần giới hạn số DB role/connection tạo ra, vì rollout nhiều instance cùng lúc có thể gây áp lực cho PostgreSQL và Vault.

## 9. Xử lý lỗi thực tế

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `403` từ `database/creds/...` | Vault token/policy sai hoặc token hết hạn | Kiểm tra auth role/workload policy; không cấp root để chữa tạm |
| `404` | Sai mount/role hoặc chưa được cấu hình | Kiểm tra provisioning database engine và role |
| `400/5xx` từ Vault Database | Database plugin lỗi, SQL tạo user thất bại hoặc backend không sẵn sàng | Kiểm tra health, audit, plugin logs; dừng cấp hàng loạt |
| Hikari báo authentication failed | Credential DB bị revoke/hết hạn, thiếu grant hoặc cấu hình sai | Kiểm tra lease, database role và thời điểm tạo pool |
| Pool cũ còn chạy rồi đột nhiên lỗi | Lease hết, DB plugin revoke hoặc restart DB | Chuyển pool có kiểm soát; quan sát connection errors |
| Renew lease thất bại | Lease không renewable, max TTL, policy hoặc Vault lỗi | Cấp credential/pool mới khi được phép, giảm traffic nếu cần |
| Timeout khi cấp credential | Không biết Vault đã tạo user/lease hay chưa | Đối soát audit/lease, tránh retry vô hạn gây dư user |
| Database từ chối SELECT | SQL grants của role chưa đầy đủ | Sửa database role/câu lệnh grant, không cấp quyền admin cho app |

### 9.1. Trạng thái không chắc chắn sau timeout

Một cuộc gọi `GET database/creds/orders-readonly` có thể **tạo user mới** trước khi kết nối bị ngắt và ứng dụng không nhận được response. Retry ngay có thể phát hành thêm user/lease. Do đó cần:

1. Giới hạn retry, backoff và số credential phát hành trong một thời gian.
2. Dùng audit từ Vault/DB để đối soát khi có bất thường.
3. Theo dõi số lease đang hoạt động và tình trạng cleanup.
4. Thiết kế quy trình thu hồi những credential bị bỏ quên theo khả năng quan sát thực tế, không đưa một account không rõ nguồn vào pool.

### 9.2. Không log secret và hạn chế bề mặt truy cập

Không ghi `password`, Vault token, request/response chứa secret, SQL chứa mật khẩu hoặc đối tượng `LeasedDbCredentials.toString()`. Chỉ log tên role, trạng thái, loại lỗi, thời gian, request ID hoặc dữ liệu audit đã được phê duyệt.

Dùng TLS cho cả **ứng dụng → Vault** và **ứng dụng → PostgreSQL** với xác minh chứng chỉ đúng cách; bảo vệ tài khoản plugin quản trị DB, tránh cấp mọi quyền cho service. Không mở Actuator endpoint hoặc Spring Environment để lộ password datasource.

## 10. Monitoring và năng lực vận hành

Theo dõi đồng thời Vault, DB và connection pool. Một dashboard ứng dụng có thể bao gồm:

| Metric/sự kiện | Ý nghĩa |
| --- | --- |
| `vault_db_credentials_issued_total` | Số lần tạo credential theo role/workload |
| `vault_db_lease_renew_success_total` | Số lần gia hạn thành công |
| `vault_db_lease_renew_failure_total` | Gia hạn lỗi, cần cảnh báo trước TTL |
| `vault_db_lease_seconds_remaining` | Thời gian còn lại của lease đang dùng |
| `vault_db_pool_rotation_total` | Số lần chuyển pool và kết quả |
| Hikari active/idle/pending connections | Pool đang hoạt động và mức chờ connection |
| PostgreSQL authentication failures | Login thất bại do user/TTL/grant |
| Vault HTTP latency và 4xx/5xx | Phát hiện policy/config/network/backend lỗi |

Tên metric `vault_db_*` chỉ là **đề xuất do ứng dụng tự định nghĩa**, không khẳng định Vault tự xuất ra những metric này. Đừng gắn password, token hoặc username ngẫu nhiên của mỗi credential vào metric labels vì thông tin nhạy cảm và cardinality lớn.

Một số cảnh báo có ích: lease còn rất ngắn mà renew chưa xác nhận; số credential phát hành tăng nhanh khi retry; pool không mở được kết nối mới; Vault Database plugin không kết nối được backend; lượng DB role còn tồn tăng ngoài mức dự kiến.

## 11. Kiểm thử tích hợp với Vault và PostgreSQL thật

Unit test có thể xác minh phân loại lỗi, state machine và mapping response, nhưng cần **integration test cô lập** để đánh giá cách database plugin tạo user, renew, revoke và tương tác với JDBC pool.

Một môi trường kiểm thử có thể chạy Vault test cùng PostgreSQL test (chẳng hạn containers có vòng đời rõ ràng), tạo Vault database mount/connection/role test và cấp token theo policy riêng. Không dùng DB production hoặc credential thật trong fixture.

Những kịch bản quan trọng:

1. **Cấp credential:** đọc `database/creds/orders-readonly`, nhận username/password/lease_id/TTL, đăng nhập JDBC và `SELECT` dữ liệu được phép.
2. **Least privilege:** thử `INSERT`, `DROP TABLE` hoặc đọc bảng ngoài grants; xác nhận bị từ chối.
3. **Cấp lại:** đọc endpoint hai lần, kiểm tra lease/user mới, không nhầm credential cũ và mới.
4. **Renew:** gia hạn khi lease renewable, đọc TTL thực tế từ response và xác minh kết nối mới vẫn dùng được trong khoảng gia hạn.
5. **Revoke:** đóng pool cũ, thu hồi lease, xác minh kết nối mới bằng credential cũ không còn được chấp nhận theo cơ chế plugin đang dùng.
6. **Lease hết hạn:** dùng TTL ngắn trong test, kiểm tra lỗi xác thực và cách ứng dụng chuyển/đóng pool.
7. **Vault token hết hạn:** kiểm tra ứng dụng đăng nhập lại đúng auth method; phân biệt với lease database vẫn còn sống.
8. **Lỗi Vault/DB:** dừng PostgreSQL hoặc chặn network trong test, xác nhận ứng dụng báo lỗi theo tầng và không log secret.
9. **Pool rotation:** tạo Pool A, cấp credential mới tạo Pool B, kiểm tra SELECT trên B, chuyển traffic và đóng A an toàn.
10. **Concurrency:** nhiều Pod/job cùng cấp credential, kiểm tra giới hạn connection/roles và cleanup.

Một test skeleton dùng JUnit 5/AssertJ:

~~~java
@Test
void issuedDatabaseCredentialsCanReadButNotWrite() throws Exception {
    LeasedDbCredentials issued = credentialService.issue();

    HikariDataSource pool = newPool(issued);
    try (pool; var connection = pool.getConnection();
         var stmt = connection.createStatement()) {

        try (var rs = stmt.executeQuery("SELECT count(*) FROM public.orders")) {
            assertThat(rs.next()).isTrue();
        }

        assertThatThrownBy(() ->
                stmt.executeUpdate(
                        "DELETE FROM public.orders WHERE id = -1"))
                .isInstanceOf(java.sql.SQLException.class);

    } finally {
        // Fixture/lease manager dọn lease sau khi pool đã đóng,
        // theo đúng quyền và quy trình test.
        testLeaseManager.revokeWhenSafe(issued.leaseId());
    }
}
~~~

Đây là **mẫu khung**: `credentialService`, `newPool` và `testLeaseManager` cần fixture tương ứng; bảng `orders` và cấu hình PostgreSQL test phải tồn tại. Không thực thi test phá dữ liệu trên DB thật. Với Postgres, lỗi quyền bên trong transaction có thể làm transaction bị đánh dấu lỗi; nên dùng test connection/transaction riêng khi cần kiểm tra nhiều tình huống.

## 12. Bài thực hành: dịch vụ Orders đọc dữ liệu bằng credential động

**Bối cảnh:** `orders-api` dùng Spring Boot để đọc trạng thái đơn hàng từ PostgreSQL. Yêu cầu: không lưu password lâu dài trong repo, chỉ có quyền `SELECT` và cần đổi account mà không làm gián đoạn API.

Thực hiện trong môi trường thử nghiệm:

1. Thiết lập Vault Database engine, PostgreSQL connection và database role `orders-readonly` với `default_ttl=15m`, `max_ttl=1h`; bảo vệ credential quản trị của plugin.
2. Tạo Vault policy chỉ `read` trên `database/creds/orders-readonly` và workload auth cho `orders-api`.
3. Cấu hình Spring Vault client HTTPS và lấy dynamic credential qua `VaultOperations`; xác minh `lease_id` và `lease_duration`.
4. Dựng Hikari pool với account vừa cấp; thực hiện `SELECT` thành công và thử thao tác ghi để chứng minh least privilege.
5. Gia hạn lease khi được phép hoặc phát hành credential mới tạo Pool B rồi chuyển traffic và nghỉ Pool A.
6. Kiểm thử token hết hạn, lease hết hạn, Vault timeout, PostgreSQL downtime và một lần renew thất bại.
7. Thêm metrics cho số lần cấp credential, trạng thái lease, pool rotation, authentication failures và tỷ lệ lỗi truy vấn.
8. Đảm bảo không có password/token trong log, dump cấu hình được chia sẻ hoặc metrics labels.

**Câu hỏi tự kiểm tra:**

1. Tại sao một lệnh đọc `database/creds/orders-readonly` có thể tạo tài khoản mới mỗi lần?
2. Vault authentication token, DB lease và JDBC connection khác nhau ở đâu?
3. Vì sao cập nhật `spring.datasource.password` trong Environment không tự bảo đảm Hikari pool đổi account?
4. Khi nào nên renew lease và khi nào nên phát hành credential/pool mới?
5. Tại sao phải drain pool cũ trước khi revoke lease?
6. Tại sao phải kiểm thử quyền SELECT/INSERT thực tế trên PostgreSQL?
7. Nếu Vault timeout sau request cấp credential, có được giả định không user nào được tạo không?
8. Cần giám sát gì để phát hiện lease sắp hết mà renew không thành công?

## 13. Tổng kết

**Vault Database dynamic credentials** giúp ứng dụng Java lấy username/password theo role và lease có thời hạn, giảm việc giữ mật khẩu database lâu dài. Spring Vault cung cấp `VaultTemplate`/`VaultOperations` để lấy credential và tương tác với Vault; Spring Cloud Vault hỗ trợ đưa secret vào cấu hình Spring tùy phiên bản và cách bootstrap.

Để tích hợp vận hành an toàn, phải coi **Vault token, database credential lease và JDBC connection pool** là ba vòng đời khác nhau. Thiết kế tốt cần policy theo workload, SQL grants tối thiểu, renew hoặc rotation có điều phối, xử lý timeout và cleanup lease, giám sát Hikari/Vault/DB và kiểm thử tích hợp với PostgreSQL thật.

**Tham khảo:** [HashiCorp Vault Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases) và [Spring Cloud Vault Reference](https://docs.spring.io/spring-cloud-vault/reference/). Đối chiếu cú pháp plugin, Spring Boot/Spring Vault và database driver với phiên bản đang triển khai.
