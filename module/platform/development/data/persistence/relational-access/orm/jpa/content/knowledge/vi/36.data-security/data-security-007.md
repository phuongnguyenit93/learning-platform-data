# Bảo vệ thông tin xác thực và cấu hình nguồn dữ liệu trong JPA

Một ứng dụng Java sử dụng **Jakarta Persistence (JPA)** cần có khả năng kết nối đến cơ sở dữ liệu quan hệ. Để kết nối, hệ thống thường dùng JDBC URL, tài khoản database, mật khẩu hoặc một cơ chế xác thực khác. Những thông tin này nằm ở điểm rất nhạy cảm: **ai lấy được thông tin xác thực và có quyền truy cập mạng tới database có thể thực hiện các thao tác theo quyền của tài khoản đó**, ngay cả khi ứng dụng có đăng nhập, phân quyền và các API được bảo vệ.

Ví dụ cấu hình nguy hiểm:

```properties
# KHÔNG dùng cho cấu hình được commit vào Git.
jakarta.persistence.jdbc.url=jdbc:postgresql://db.example.internal:5432/shop
jakarta.persistence.jdbc.user=shop_admin
jakarta.persistence.jdbc.password=real-password-written-here
```

Đoạn cấu hình không chỉ có nguy cơ lộ mật khẩu qua Git. Nó còn dùng tài khoản mang tên `shop_admin`, làm tăng thiệt hại nếu secret bị lộ. Một application server có thể bị xâm nhập, pipeline CI có thể in môi trường ra log, file cấu hình có thể được đưa vào image, hoặc thông tin kết nối có thể được gửi kèm exception.

Thiết kế tốt cần giải quyết nhiều lớp:

1. **Không hard-code secrets** trong Java source, `persistence.xml`, `application.properties`, container image hoặc repository.
2. **Cấp secrets ở runtime** từ một nguồn được kiểm soát, có thể là secret manager, cơ chế identity của cloud hoặc một hệ thống secret injection phù hợp.
3. **Phân quyền tối thiểu** cho database user chạy ứng dụng; tách migration/administration khỏi runtime.
4. **Bảo vệ kênh kết nối** bằng TLS có xác minh danh tính server, cùng network isolation.
5. **Giới hạn nơi secrets xuất hiện**: process arguments, URL, environment, filesystem, logs, monitoring, crash dumps và backups.
6. **Có cơ chế rotation, revocation và incident response** khi credentials sắp hết hạn hoặc bị lộ.
7. **Kiểm thử thực tế** rằng application chỉ có các quyền cần dùng, fail an toàn khi TLS/authentication sai, và không lộ secrets trong log.

Bài thuộc chủ đề **Data Persistence Relational Access ORM JPA**, chương **Bảo mật dữ liệu**, với đề mục trực tiếp **“Bảo vệ thông tin xác thực và cấu hình nguồn dữ liệu”**.

**Nguyên tắc cốt lõi:** *Thông tin kết nối là quyền truy cập thực tế vào database, không phải chỉ là một chuỗi cấu hình. Bảo vệ secret, giới hạn quyền của identity, xác thực endpoint, kiểm soát đường triển khai và thiết kế vòng đời credential là một phần của cùng hệ thống bảo mật.*

---

## 1. Phân biệt JPA, DataSource, JDBC driver và database

JPA là lớp quản lý persistence entities. Thông thường JPA provider không tự phát minh một hệ thống bảo mật mật khẩu; nó dùng kết nối được cung cấp qua JDBC hoặc DataSource.

```text
REST API / background job
           |
           v
Business service
           |
           v
EntityManager / Spring Data Repository
           |
           v
JPA provider (Hibernate, EclipseLink, ...)
           |
           v
DataSource / JDBC connection pool
           |
           v
JDBC driver + authentication + TLS
           |
           v
Database endpoint / DB role / permissions
```

Trong thực tế:

- **EntityManager** quản lý persistence context và entity lifecycle.
- **EntityManagerFactory** tạo hoặc điều phối EntityManagers.
- **DataSource** cung cấp JDBC connections.
- **Connection pool** tái sử dụng connections để giảm chi phí mở kết nối.
- **JDBC driver** thực hiện kết nối theo driver protocol, authentication và TLS configuration.
- **Database role/user** quyết định SQL privileges thực tế.

Các thành phần có trách nhiệm khác nhau. Giấu `DB_PASSWORD` khỏi Java source sẽ chưa đủ nếu connection dùng superuser hoặc kết nối chấp nhận server certificate không đáng tin.

### 1.1. Các loại thông tin cần bảo vệ

| Thành phần | Có luôn là secret? | Vì sao cần bảo vệ |
| --- | --- | --- |
| Database password | Có | Cho phép xác thực với DB identity |
| Cloud DB access token | Có | Có thể cấp quyền kết nối trong thời gian hiệu lực |
| Client private key | Có | Có thể chứng minh danh tính client với mTLS |
| JDBC URL | Không luôn là secret, nhưng nhạy cảm | Có thể lộ topology, username, query options, hoặc chứa password |
| Database username | Thường không phải secret một mình | Là thông tin hữu ích cho attacker; không nên tiết lộ tùy tiện |
| Server CA certificate | Thường là public trust material | Tính đúng và integrity của trust configuration quan trọng |
| Truststore password | Tùy mục đích/truststore | Có thể bảo vệ integrity/private material theo loại store |
| Database hostname/port | Không phải credential | Có thể lộ vị trí/kiến trúc mạng |
| Migration user password | Có, thường nhạy cảm hơn runtime | Có thể có DDL và schema-wide permissions |
| Connection pool parameters | Không phải password | Có ảnh hưởng availability và resource exhaustion |
| Application encryption key | Có | Có thể giải mã dữ liệu, không thay thế DB credential |

Một tập cấu hình chưa có password nhưng chứa endpoint production, schema names và network information vẫn nên được quản lý theo mức độ nhạy cảm phù hợp.

---

## 2. Threat model: secret có thể rò rỉ từ đâu?

Hãy xét đường đi của một password:

```text
Secret manager
      |
      v
Deployment runtime
      |
      v
Application configuration
      |
      v
DataSource / pool
      |
      v
JDBC driver
      |
      v
Database authentication
```

Dọc đường có nhiều điểm rò rỉ.

### 2.1. Repository và lịch sử Git

Sai:

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(
    "jdbc:postgresql://db.internal:5432/shop"
);
config.setUsername("shop_runtime");
config.setPassword("hard-coded-real-password");
```

Mật khẩu có thể tồn tại trong:

- Git commit.
- Fork/clone của repository.
- Pull request diff.
- Code review comments.
- Cache của CI.
- Package/binary đã build.
- Screenshot hoặc terminal recording.
- Developer machine backups.

**Xóa mật khẩu ở commit mới không tự xóa được lịch sử rò rỉ.** Khi credential thực bị commit, nên coi nó đã bị lộ và thực hiện rotation/revocation.

### 2.2. Image và build artifacts

Sai:

```dockerfile
# KHÔNG làm:
ENV DB_PASSWORD=real-production-secret
```

Một image có thể được copy, push lên registry, scan hoặc dùng làm cache. `ARG` dùng trong build cũng không nên được xem là kênh an toàn cho secret vì có thể rò qua build metadata/layers/logs tùy workflow.

Nên inject secrets ở **runtime** bằng cơ chế quản lý secrets của môi trường, không bake vào image.

### 2.3. CI/CD logs và process arguments

Sai:

```text
java -Dspring.datasource.password=real-password -jar app.jar
```

Command-line arguments có thể xuất hiện trong process listings, diagnostics và pipeline logs tùy OS/quyền truy cập.

Một shell script `echo $DB_PASSWORD` hoặc chạy `set -x` khi xử lý secret cũng có thể làm lộ trực tiếp.

### 2.4. Environment variables

Biến môi trường thường thuận tiện hơn hard-code, nhưng **không phải một secret manager hoàn chỉnh**:

- Một process có đặc quyền phù hợp có thể đọc môi trường của process khác.
- Crash dumps và diagnostics có thể chứa dữ liệu.
- Một số công cụ debug/monitoring có thể thu thập environment.
- Thông tin có thể bị in khi triển khai hoặc troubleshooting.
- Rotation có thể cần restart process vì giá trị môi trường đã được đọc vào ứng dụng.

Dùng environment variables **có kiểm soát** khi nền tảng phù hợp, không coi chúng tự động an toàn tuyệt đối.

### 2.5. Exceptions, logs, metrics và tracing

Nếu cấu hình hoặc JDBC URL chứa username/password, việc log toàn bộ config object hoặc connection properties có thể khiến secret xuất hiện ở nơi nhiều người truy cập.

Tương tự, SQL bind parameter TRACE có thể làm lộ dữ liệu nghiệp vụ nhạy cảm dù DB password không bị log.

---

## 3. Xác định mục tiêu bảo mật

Thiết kế cần bảo vệ cả ba mục tiêu:

| Mục tiêu | Ví dụ |
| --- | --- |
| Confidentiality | Không lộ DB password, access token, private key |
| Integrity | Không bị thay endpoint, truststore, DB role hoặc migration setting để chuyển hướng/ghi sai dữ liệu |
| Availability | Secret rotation, expired token, connection pool và TLS không làm ứng dụng ngừng hoạt động ngoài kế hoạch |

Một ứng dụng có “password được mã hóa trong file” nhưng chứa luôn khóa giải mã bên cạnh file đó chỉ chuyển vị trí vấn đề, không giải quyết secret ownership.

### 3.1. Hỏi ai có thể truy cập secret

- Developer nào được quyền xem production credentials?
- CI workflow nào có quyền lấy secret?
- Service account nào được phép đọc secret theo environment?
- Ai có thể thay đổi secret value hoặc JDBC URL?
- Ai có quyền xem pod environment, log và backup?
- Ai có quyền yêu cầu rotate/revoke credential?
- Có audit trail cho hoạt động đọc/đổi secret không?

Giải pháp phù hợp phụ thuộc threat model, không chỉ lựa chọn cú pháp cấu hình.

---

# Phần I — Cấu hình nguồn dữ liệu an toàn

## 4. Đối chiếu cấu hình không an toàn và an toàn

**Không nên commit:**

```properties
spring.datasource.url=jdbc:postgresql://prod-db:5432/shop
spring.datasource.username=postgres
spring.datasource.password=production-password
```

**Mẫu nhận cấu hình từ runtime:**

```properties
spring.datasource.url=${DB_JDBC_URL}
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${DB_PASSWORD}
```

Đây là cú pháp placeholder thường dùng trong Spring Boot. Các giá trị thực được cấp ở runtime qua nguồn cấu hình được kiểm soát.

### 4.1. Placeholder không tự cung cấp secret

Cấu hình trên chỉ yêu cầu framework **đọc giá trị từ environment/property sources**. Nó không quyết định:

- Ai được phép cấp giá trị?
- Credential được lưu ở đâu?
- Có encryption at rest không?
- Secret được rotate như thế nào?
- Logs có redaction không?
- Có nên restart application khi secret đổi không?

Secret manager và deployment process phải giải quyết các câu hỏi đó.

### 4.2. Đừng để fallback password thực

Sai:

```properties
spring.datasource.password=${DB_PASSWORD:secret123}
```

Khi môi trường thiếu biến, ứng dụng dùng một password mặc định mà đôi khi vẫn tồn tại trong DB test hoặc production.

Với production, **thiếu credential cần làm service fail configuration hoặc fail readiness một cách rõ ràng**, không tự chọn password yếu.

### 4.3. Không log toàn bộ resolved properties

Sai:

```java
log.info("Database config = {}", environment);
```

hoặc:

```java
log.info(
    "Datasource password={}",
    environment.getProperty(
        "spring.datasource.password"
    )
);
```

Nếu cần xác nhận cấu hình, chỉ log non-secret metadata đã được phê duyệt, chẳng hạn environment label và loại DB, không in password/token/private keys.

---

## 5. Spring Boot với DataSource được cấu hình từ environment

Một cấu hình tối thiểu:

```yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 15
      minimum-idle: 3
      connection-timeout: 30000
  jpa:
    open-in-view: false
```

Các giá trị connection pool ở đây là ví dụ minh họa, **không phải khuyến nghị cố định cho mọi workload**.

### 5.1. Vai trò của từng trường

| Trường | Ý nghĩa |
| --- | --- |
| `spring.datasource.url` | JDBC endpoint/database/driver options |
| `spring.datasource.username` | DB principal |
| `spring.datasource.password` | Credential được inject |
| `maximum-pool-size` | Giới hạn connections trong pool |
| `minimum-idle` | Mức pool idle dự kiến, theo Hikari version/config |
| `connection-timeout` | Thời gian chờ lấy connection, tính theo milliseconds theo Hikari semantics |
| `open-in-view` | Cấu hình persistence context ở web request; không phải cơ chế giữ secret |

### 5.2. Không nhầm container secret với ứng dụng đã an toàn

Một kẻ có quyền điều khiển code đang chạy dưới application identity có thể dùng chính DataSource để truy vấn dữ liệu theo DB role, kể cả khi không đọc được password ở dạng văn bản.

Vì vậy bảo mật không chỉ là “không ai thấy password”; còn là:

- Runtime role có quyền tối thiểu.
- Network policy.
- Authorization trong ứng dụng.
- Database auditing.
- Hardening host/container.
- Secret access auditing.

### 5.3. Không đưa password vào JDBC URL

Tránh cấu hình kiểu:

```text
jdbc:postgresql://db.internal:5432/shop?user=shop_runtime&password=...
```

URL thường được log ở debug, metrics hoặc exception diagnostics. Tách password khỏi URL để giảm nguy cơ vô tình lộ.

Dù password được inject từ secret manager, nếu cuối cùng bị nối vào URL rồi in ra log thì vẫn là rò rỉ.

### 5.4. Chọn profile theo môi trường

Ví dụ các môi trường:

```text
local -> database dev riêng
test  -> test database ephemeral/isolated
staging -> staging DB/role riêng
prod -> production DB/role riêng
```

Không sử dụng production credentials trong developer laptop, unit tests hoặc pull-request CI.

---

## 6. Thuần Jakarta Persistence và persistence.xml

Khi dùng JPA application-managed RESOURCE_LOCAL, có thể thấy cấu hình:

```xml
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="shopPU"
                      transaction-type="RESOURCE_LOCAL">

        <class>com.example.shop.domain.Product</class>

        <properties>
            <property
                name="jakarta.persistence.jdbc.driver"
                value="org.postgresql.Driver"/>
            <property
                name="jakarta.persistence.jdbc.url"
                value="jdbc:postgresql://db.internal:5432/shop"/>
            <property
                name="jakarta.persistence.jdbc.user"
                value="shop_runtime"/>
        </properties>
    </persistence-unit>
</persistence>
```

Ví dụ cố ý **không chứa password**. Nó cũng chưa phải cấu hình production hoàn chỉnh: JDBC URL/identity nên được quản lý theo môi trường và kết nối cần thiết lập TLS phù hợp.

### 6.1. Cấp runtime properties khi tạo factory

Một cách cho application-managed JPA:

```java
Map<String, Object> properties = new HashMap<>();

properties.put(
    "jakarta.persistence.jdbc.url",
    config.jdbcUrl()
);
properties.put(
    "jakarta.persistence.jdbc.user",
    config.username()
);
properties.put(
    "jakarta.persistence.jdbc.password",
    config.secretPassword()
);

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "shopPU",
        properties
    );
```

`config` là một abstraction do application cấp từ nguồn cấu hình đáng tin. Cần import:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import java.util.HashMap;
import java.util.Map;
```

### 6.2. Lợi ích và giới hạn

Cách này không cần commit password trong `persistence.xml`, nhưng password vẫn tồn tại trong process memory và trong properties truyền cho provider.

Vì vậy:

- Không `toString()` cả `properties`.
- Không dump map vào debug logs.
- Không log object `config` nếu chứa secret.
- Kiểm soát heap dumps và diagnostics.
- Có chiến lược factory/pool lifecycle khi credential đổi.

### 6.3. Container-managed JPA có phương án khác

Nếu ứng dụng chạy trong Jakarta EE container, thường nên cấu hình DataSource/JNDI qua application server thay vì tự dựng JDBC credentials trong persistence unit.

Đây là trách nhiệm triển khai và container resource management.

---

## 7. JTA và DataSource qua JNDI

Một JTA persistence unit có thể tham chiếu một DataSource do container quản lý:

```xml
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="shopPU"
                      transaction-type="JTA">

        <jta-data-source>
            java:app/jdbc/ShopDataSource
        </jta-data-source>

        <class>com.example.shop.domain.Product</class>
    </persistence-unit>
</persistence>
```

Lúc này:

- `persistence.xml` tham chiếu tên resource.
- Container định nghĩa connection pool, driver, URL, TLS và identity.
- Secret có thể được container lấy từ secret-management integration.
- JPA provider dùng DataSource của container.
- Transaction manager điều phối JTA transactions.

### 7.1. JNDI name không phải secret

Tên `java:app/jdbc/ShopDataSource` không phải database password. **Đừng nhầm ẩn JNDI name là biện pháp bảo vệ credential chính**.

Cần bảo vệ configuration của resource ở container/deployment layer.

### 7.2. Không ghi password ở hai nơi

Nếu container đã quản lý credentials của DataSource, không sao chép password vào `persistence.xml` hoặc Java annotations.

### 7.3. JTA DataSource và non-JTA DataSource

JPA có thể tham chiếu `jta-data-source` hoặc `non-jta-data-source` tùy environment và transaction model. Chọn loại phù hợp với transaction management, không chỉ để “làm cho kết nối chạy được”.

Dùng sai transaction type có thể dẫn đến lỗi tham gia transaction, flush/commit hoặc resource enlistment.

---

## 8. Khởi tạo DataSource bằng Java không nên làm lộ secret

Ví dụ minh họa khi cần cấu hình pool có kiểm soát:

```java
HikariConfig hikari = new HikariConfig();

hikari.setJdbcUrl(config.jdbcUrl());
hikari.setUsername(config.username());
hikari.setPassword(config.password());
hikari.setMaximumPoolSize(15);

HikariDataSource dataSource =
    new HikariDataSource(hikari);
```

Trong Spring Boot thường không cần tự tạo `HikariDataSource` nếu auto-configuration đã phù hợp. Khi tự tạo, phải quản lý lifecycle/close và tránh tạo nhiều pools không cần thiết.

### 8.1. Không dùng `toString()` để debug HikariConfig

Một số library có thể mask password ở những vị trí nhất định, nhưng **không mặc định mọi custom serializer/log exporter sẽ mask mọi secret field**.

Dùng log metadata tự chọn:

```java
log.info(
    "DataSource initialized for environment={}",
    deploymentEnvironment
);
```

Không ghi `config.password()`.

### 8.2. Không truyền config object có secret vào exception message

Sai:

```java
throw new IllegalStateException(
    "Could not connect using config " + config
);
```

Nếu `config.toString()` bao gồm password, exception có thể được gửi lên log aggregator hoặc client.

### 8.3. Không gắn secret vào metrics labels

Metrics tags thường được lưu, index và hiển thị rộng. Không dùng JDBC URL có user/password, token hoặc raw exception diagnostics làm metric label.

---

# Phần II — Quản lý secrets

## 9. Secret manager là hệ thống điều phối vòng đời credential

Một secret manager thường cung cấp một hoặc nhiều khả năng:

- Lưu trữ secret có bảo vệ.
- Kiểm soát access theo workload identity.
- Phát hành credential hoặc token động.
- Audit ai đã đọc/đổi secret.
- Versioning.
- Rotation/revocation.
- Tích hợp deployment/runtime.
- Phân tách quyền production/staging/dev.

Các lựa chọn có thể gồm secret service của cloud, Vault hoặc secret-management stack nội bộ, tùy tổ chức.

### 9.1. Hai cách đưa secret vào application

**Cách A — Inject qua environment variable hoặc mounted file:**

```text
Secret manager
    |
    v
Deployment agent / platform
    |
    v
DB_PASSWORD environment variable
hoặc secret file mount
    |
    v
Spring/JPA config
```

**Cách B — Application lấy secret qua identity có kiểm soát:**

```text
Application workload identity
    |
    v
Secret manager API
    |
    v
Short-lived credential/token
    |
    v
DataSource/DB authentication
```

Không có cách nào luôn tốt nhất. Cần xem support của platform, rotation, startup availability, audit và quyền đọc secret.

### 9.2. Chú ý vòng đời secrets trong bộ nhớ

Secret được lấy rồi chuyển thành Java `String` hoặc JDBC driver property thường vẫn tồn tại trong heap và có thể xuất hiện trong dumps. Java `String` không thể xóa nội dung một cách đáng tin cậy sau khi dùng.

Không hứa rằng “sử dụng `char[]` là đã xóa hoàn toàn password khỏi memory” nếu cuối cùng driver vẫn yêu cầu String/copies.

### 9.3. Đừng cache secret mãi mãi

Với short-lived credentials, application cần hiểu token expiration và khả năng pool mở connection mới sau khi token hết hạn.

Nếu DataSource giữ credential cũ trong cấu hình cố định, secret manager đã rotate không tự khiến pool dùng credential mới.

### 9.4. Secret availability và startup

Nếu không lấy được secret:

- Fail startup/readiness an toàn khi không thể phục vụ.
- Không tự fallback sang default password.
- Log loại lỗi/secret reference ID ở mức an toàn.
- Không log secret value.
- Có alert phù hợp và retry lấy secret theo backoff nếu nền tảng cho phép.

---

## 10. Môi trường container và Kubernetes

Ví dụ Kubernetes manifest minh họa reference secret:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shop-api
  template:
    metadata:
      labels:
        app: shop-api
    spec:
      containers:
        - name: shop-api
          image: example/shop-api:1.0.0
          env:
            - name: DB_USERNAME
              valueFrom:
                secretKeyRef:
                  name: shop-db-credentials
                  key: username
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: shop-db-credentials
                  key: password
```

Manifest chỉ tham chiếu secret name/key; không có giá trị thực.

### 10.1. Kubernetes Secret không phải tự động “vault an toàn tuyệt đối”

Kubernetes Secret có nhiều rủi ro nếu RBAC, etcd encryption, admission policy và node isolation cấu hình yếu.

Dữ liệu trong trường `data` thường được base64-encode trong YAML. **Base64 không phải mã hóa bảo mật**.

Cần kiểm soát:

- RBAC ai được `get/list/watch` Secrets.
- Namespace isolation.
- Encryption at rest phù hợp.
- API audit.
- Pod/service account privileges.
- Secret mounting và file permissions.
- Node access.
- GitOps workflows không commit secret values.

### 10.2. Environment variable không tự cập nhật trong process

Khi secret backing value đổi, environment variables đã inject khi process khởi chạy **không tự refresh** bên trong process. Rotation có thể yêu cầu rollout/restart hoặc tích hợp cơ chế secret refresh khác.

Với mounted volumes có cơ chế cập nhật, application và connection pool cũng phải đọc lại values đúng lúc; file đổi không tự cập nhật credentials đang giữ trong pool.

### 10.3. Tránh debug bằng cách in toàn bộ environment

Lệnh tương đương `env`, `printenv` hoặc tooldump môi trường trong production container có thể lộ mọi injected secret. Chỉ inspect các thuộc tính không nhạy cảm cần thiết.

---

## 11. Secrets trong local development và test

Development cần database riêng, ít quyền, không chứa dữ liệu khách hàng thực.

Một setup local có thể dùng:

```properties
spring.datasource.url=${LOCAL_DB_JDBC_URL}
spring.datasource.username=${LOCAL_DB_USERNAME}
spring.datasource.password=${LOCAL_DB_PASSWORD}
```

Các biến được cấp qua local secret store, IDE run configuration có bảo vệ hoặc một tệp local không commit tùy policy tổ chức.

### 11.1. `.gitignore` chỉ là lớp dự phòng

`.gitignore` giúp tránh add nhầm file chưa tracked, nhưng:

- Không bảo vệ file đã tracked.
- Không xóa secret trong Git history.
- Không ngăn screenshot, log hoặc backup leak.
- Không thay secret scanning và review.

### 11.2. File `.env` có rủi ro

Một tệp `.env` tiện cho local development nhưng phải được bảo vệ quyền truy cập, không commit, không copy vào container image và không chia sẻ qua chat/email tùy tiện.

Có thể commit file mẫu:

```text
DB_JDBC_URL=<set-in-local-environment>
DB_USERNAME=<set-in-local-environment>
DB_PASSWORD=<set-in-local-environment>
```

Dấu placeholder là dữ liệu minh họa, **không phải credential dùng được**.

### 11.3. CI không dùng production credentials

Pull-request tests có thể chạy trên ephemeral database hoặc isolated test instance. Nếu CI cần credential, cấp secret scope riêng với least privilege và access restrictions; workflow từ contributor không đáng tin không được tự động đọc production secret.

### 11.4. Testcontainers không thay security policy

Database ephemeral cho integration test giúp tái tạo schema/driver behavior, nhưng credentials dùng trong test không nên tái sử dụng ở production.

---

# Phần III — Quyền tối thiểu và ranh giới trách nhiệm

## 12. Không dùng database superuser cho runtime ứng dụng

Một ứng dụng CRUD thường không cần quyền:

- Tạo/drop databases.
- Tạo roles/superusers.
- Thay đổi server configuration.
- Đọc mọi schemas của tenant khác.
- Cài extensions.
- Tạo hoặc xóa tables trong production runtime.
- Đổi permissions cho roles khác.

Nếu runtime user là superuser, rò rỉ credential có thể dẫn tới tổn thất lớn hơn nhiều so với quyền CRUD trên schema cụ thể.

### 12.1. Tách hai identities

**Migration identity:**

- Có các quyền DDL cần thiết.
- Chỉ dùng trong deployment/migration job.
- Audit và kiểm soát chặt.
- Không dùng cho HTTP application requests.

**Runtime identity:**

- Chỉ có DML/EXECUTE cần thiết.
- Có phạm vi schema/table rõ ràng.
- Không được tạo/drop objects khi không cần.
- Secret được quản lý riêng.

### 12.2. Ví dụ quyền PostgreSQL

Một mẫu minh họa (tùy schema ownership và phiên bản):

```sql
-- Thực hiện bởi DBA hoặc role quản trị có thẩm quyền.
CREATE ROLE shop_runtime LOGIN;

GRANT CONNECT ON DATABASE shop TO shop_runtime;
GRANT USAGE ON SCHEMA app TO shop_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO shop_runtime;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA app
TO shop_runtime;
```

Đây là ví dụ khởi đầu, không phải cấu hình least-privilege hoàn chỉnh:

- Có thể cần chỉ cấp quyền trên **những bảng nhất định**, không toàn schema.
- Một ứng dụng read-only không nên nhận INSERT/UPDATE/DELETE.
- Có thể cần quyền sequence cụ thể.
- Default privileges cho future objects cần cấu hình riêng nếu policy cho phép.
- Schema ownership và migration identity cần được quản lý rõ.
- Role có LOGIN cần thiết lập credential/authentication method qua secure channel; ví dụ không nhúng password.

### 12.3. Không mở rộng quyền chỉ vì thấy lỗi 42501

PostgreSQL có thể trả SQLSTATE `42501` cho `insufficient_privilege`. Khi gặp lỗi, xác định application thực sự cần thao tác gì và migration đã đúng chưa.

Không giải quyết bằng:

```sql
GRANT ALL PRIVILEGES ON DATABASE shop TO shop_runtime;
```

một cách máy móc.

### 12.4. Privileges theo truy vấn thực

Ví dụ ứng dụng chỉ gọi:

```sql
SELECT ...
INSERT INTO orders ...
UPDATE orders SET status ...
```

có thể cần quyền hẹp hơn full CRUD trên mọi bảng.

Những quyền hẹp hơn làm giảm blast radius nếu service bị khai thác.

---

## 13. Database role không thay application authorization

Nếu một database user có quyền SELECT bảng `orders` cho mọi tenants, application vẫn phải enforce object-level/tenant access.

Ví dụ JPA:

```java
List<PurchaseOrder> orders = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
    """,
    PurchaseOrder.class
)
.setParameter("tenantId", authenticatedTenantId)
.getResultList();
```

`authenticatedTenantId` phải được lấy từ security context đã xác minh, không lấy tùy tiện từ client.

### 13.1. RLS là một lớp bổ sung

PostgreSQL Row-Level Security (RLS) có thể dùng để enforce tenant-level policies trong database. Khi dùng, cần thiết kế:

- Session/transaction-scoped tenant identity.
- Connection pooling và session state cleanup.
- Role capabilities và bypass permissions.
- Test cross-tenant reads/writes.
- Behavior khi tenant identity không được set.

RLS không thay parameterized JPQL, không thay authorization và không mặc định hoạt động chỉ vì bảng có `tenant_id`.

### 13.2. Pool reuse có thể làm rò session state

Nếu ứng dụng set tenant/session variables trên JDBC connection, connection được trả vào pool rồi dùng lại cho request khác có thể giữ state ngoài ý muốn nếu không reset đúng.

Cần xác định rõ lifecycle của session-local settings, transaction-local settings và pool reset behavior trên DB/provider thật.

---

## 14. Tách runtime account và schema migration

Trong nhiều Spring Boot projects, cùng một datasource được dùng cho cả ứng dụng lẫn Flyway/Liquibase. Cách đó tiện nhưng có thể khiến runtime role cần DDL permissions.

Một thiết kế chặt hơn:

```text
Deployment/migration job
  -> migration identity
  -> CREATE/ALTER/DROP theo kế hoạch

Running application
  -> runtime identity
  -> SELECT/INSERT/UPDATE/DELETE cần thiết
```

### 14.1. Migrations nên chạy có kiểm soát

- Dùng một job hoặc deployment step được cấp quyền phù hợp.
- Không nhúng migration password trong application artifact.
- Có quy trình phê duyệt/rollback.
- Theo dõi schema version.
- Không để mỗi app instance tự cạnh tranh schema migrations nếu không có chiến lược.
- Sau migration, runtime application không cần giữ DDL credentials.

### 14.2. Hibernate schema generation ở production

Không dựa vào việc ORM tự sửa schema để thay thế migration có kiểm soát, đặc biệt nếu yêu cầu runtime DB user có quyền DDL.

Ví dụ cấu hình Spring Boot có thể dùng:

```properties
spring.jpa.hibernate.ddl-auto=validate
```

`validate` giúp kiểm tra một số sai lệch mapping/schema, nhưng **không phải kiểm chứng đầy đủ privileges hoặc mọi constraints**, và không thay kiểm thử migration.

### 14.3. App runtime không cần migration credential làm fallback

Nếu migration role secret bị cấp nhầm cho runtime pod, thiệt hại khi compromised service có thể lớn hơn.

Tách cả **identity** lẫn **đường cấp secret**.

---

# Phần IV — Bảo vệ kênh kết nối và endpoint

## 15. JDBC TLS: mã hóa chưa đủ nếu không xác minh server

Một kết nối database thường đi qua network giữa application host/pod và DB service. Không nên giả định mạng nội bộ luôn là đáng tin.

TLS giúp bảo vệ dữ liệu trên đường truyền, nhưng cấu hình phải xác định:

- Có bật mã hóa không?
- Chứng chỉ server có được kiểm tra với trust anchor đáng tin không?
- **Hostname/server identity** có được xác minh không?
- Có chấp nhận certificate không đáng tin chỉ vì app đang lỗi kết nối không?
- Có chính sách version/cipher phù hợp với môi trường không?

### 15.1. PostgreSQL JDBC minh họa

Một URL dùng pgJDBC có thể cấu hình:

```text
jdbc:postgresql://db.example.internal:5432/shop?sslmode=verify-full
```

`verify-full` là chế độ nhằm yêu cầu kết nối TLS và xác minh certificate/hostname theo semantics pgJDBC. Cần cung cấp trust material đúng và dùng hostname trùng certificate hợp lệ.

Một URL chỉ có `sslmode=require` không được đồng nhất với hostname verification đầy đủ trong mọi pgJDBC configurations.

### 15.2. MySQL Connector/J minh họa

Với driver/version hỗ trợ, có thể dùng chế độ như:

```text
jdbc:mysql://db.example.internal:3306/shop?sslMode=VERIFY_IDENTITY
```

Tên thuộc tính và semantics phụ thuộc MySQL Connector/J version. `VERIFY_IDENTITY` thể hiện mục tiêu xác minh server identity, không chỉ mã hóa transport.

### 15.3. SQL Server JDBC minh họa

Một chuỗi kết nối phổ biến:

```text
jdbc:sqlserver://db.example.internal:1433;databaseName=shop;encrypt=true;trustServerCertificate=false
```

Cấu hình TLS/certificate store phải tương thích với Microsoft JDBC driver version thực tế. Không dùng `trustServerCertificate=true` làm lựa chọn production mặc định chỉ để bỏ lỗi certificate.

### 15.4. Các URL là ví dụ, không phải config đa DB portable

Không có một cặp TLS parameter áp dụng cho mọi JDBC driver. Với PostgreSQL, MySQL, SQL Server, Oracle hoặc DB khác, phải kiểm tra driver documentation và thử certificate/hostname verification trên môi trường tương ứng.

---

## 16. CA trust, hostname verification và certificate rotation

Một kết nối có thể mã hóa nhưng **chưa xác minh đúng endpoint** nếu client chấp nhận bất kỳ server certificate nào.

### 16.1. Tại sao hostname verification quan trọng?

Giả sử DNS hoặc routing bị thay đổi:

```text
Application
   |
   v
db.example.internal  -> máy không phải database dự kiến
```

Nếu client không xác minh certificate/hostname, application có thể kết nối đến endpoint giả mà không nhận biết.

### 16.2. Trust material phải được quản lý

- Cập nhật CA bundle theo chính sách.
- Giới hạn quyền sửa truststore.
- Có kế hoạch khi CA/cert hết hạn.
- Kiểm tra SAN/hostname.
- Dùng cùng hostname mà server certificate được cấp cho.
- Không vô hiệu hóa validation khi incident.

### 16.3. Rotation certificate cần triển khai nhiều bước

Ví dụ kế hoạch:

1. Xác định certificate mới và chain hợp lệ.
2. Triển khai trust material để clients tin được cả giai đoạn chuyển đổi.
3. Cập nhật server certificate theo kế hoạch.
4. Tạo kết nối mới để kiểm tra handshake.
5. Theo dõi handshake/authentication failures.
6. Gỡ trust material cũ khi an toàn.

Không thay certificate/truststore đồng thời thiếu overlap nếu hệ thống cần zero-downtime.

### 16.4. mTLS là lớp xác thực thêm

Một số môi trường hỗ trợ client certificate authentication. Private key của client là secret đặc biệt nhạy cảm, cần storage/permissions/rotation tương ứng.

mTLS không tự thay authorization SQL của database role.

---

## 17. Không chỉ bảo vệ mật khẩu: bảo vệ cả destination

JDBC URL có thể bị thay đổi từ:

```text
jdbc:postgresql://prod-db.internal:5432/shop
```

sang một endpoint khác nếu người tấn công kiểm soát deployment config.

Vì vậy:

- Configuration write access phải bị giới hạn.
- TLS hostname verification phải hoạt động.
- DNS/routing/network policy phải được kiểm soát.
- Deploy artifacts và config changes cần audit.
- Không cho client request chọn JDBC URL tùy ý.
- Không cho một môi trường production dùng nhầm staging/test DB.

### 17.1. Không lấy DB host từ HTTP request

Rất nguy hiểm:

```java
String url =
    "jdbc:postgresql://" + request.getParameter("host")
    + ":5432/shop";
```

Kết nối database phải do trusted deployment configuration quyết định, không do user input. Tùy use case, nhận arbitrary host còn có thể tạo rủi ro SSRF, credential exfiltration hoặc internal network probing.

### 17.2. Connection validation không thay endpoint identity

Pool health check có thể chỉ chứng minh server phản hồi SQL, không chứng minh đó là database production đúng nếu TLS/certificate checks bị vô hiệu hóa.

---

## 18. Network isolation và firewall policy

Kể cả khi password mạnh và TLS đúng, database không nên mở rộng hơn phạm vi cần thiết.

Một kiến trúc thường gặp:

```text
Public Internet
       |
       v
API gateway / load balancer
       |
       v
Application private network
       |
       | allowed egress to DB
       v
Database private subnet / private endpoint
```

Biện pháp:

- Không public DB port khi không cần.
- Chỉ cho application subnets/service identities kết nối.
- Tách staging/prod network.
- Chặn lateral movement.
- Giới hạn admin access qua VPN/bastion hoặc cơ chế có audit.
- Theo dõi connection attempts từ nguồn lạ.
- Quản lý DNS và route changes có kiểm soát.

### 18.1. Network isolation không thay authentication

Một host trong cùng VPC không tự là trusted. Database vẫn phải xác thực danh tính và kiểm tra privileges.

### 18.2. Authentication cũng không thay network isolation

Một password mạnh không phải lý do công khai database endpoint ra toàn Internet nếu kiến trúc không cần.

---

# Phần V — Connection pool và vòng đời xác thực

## 19. Pool giữ connections qua nhiều request

HikariCP hoặc một pool tương đương giữ nhiều JDBC connections đã xác thực.

```text
API request 1  ─┐
API request 2  ─┼─> Connection pool ─> DB
API request 3  ─┘
```

Khi password thay đổi, hai nhóm kết nối có thể khác trạng thái:

- **Connections đang mở** có thể tiếp tục dùng trong một khoảng thời gian tùy database/session policy.
- **Connections mới** có thể cần credential mới.
- Pool đã khởi tạo bằng password cũ có thể tiếp tục cố mở connection bằng password đó.

### 19.1. Rotation không đồng nghĩa sửa một biến môi trường

Một phương án vận hành:

1. Tạo/cấp credential mới.
2. Cho DB chấp nhận credential mới.
3. Cập nhật secret manager.
4. Rollout application/pools dùng credential mới.
5. Xác nhận connections mới thành công.
6. Thu hồi credential cũ sau khoảng chuyển đổi phù hợp.

Không phải DB authentication method nào cũng cho phép hai password đồng thời trên cùng account. Nếu cần overlap, có thể dùng **hai DB users/roles tương đương quyền** hoặc cơ chế rotation phù hợp hệ thống.

### 19.2. Không để secret manager đổi rồi mặc định pool đã đổi

Một process đang giữ `HikariConfig.password` cũ không tự refresh khi secret manager thay version. Cần xác nhận cơ chế reload của pool/framework hoặc thực hiện controlled rollout.

### 19.3. Active connections và revoked credentials

Việc đổi password/thu hồi secret không phải lúc nào cũng hủy tức thì các DB sessions đang được mở. Cần xem cơ chế database để terminate sessions hoặc giảm thời gian tồn tại nếu incident đòi thu hồi nhanh.

### 19.4. Connection lifetime liên quan rotation

Pool settings như `maxLifetime`, `idleTimeout`, `minimumIdle` ảnh hưởng việc kết nối mới xuất hiện, nhưng **không phải giải pháp rotation hoàn chỉnh**. Một pool vẫn có thể dùng credential cũ để mở những connections mới nếu không được cập nhật.

### 19.5. Kiểm thử connection acquisition sau rotation

Chỉ test một truy vấn trên connection còn mở chưa chứng minh pool có thể mở connection mới bằng credential mới. Cần test khi connection cũ bị đóng/evicted và new connection được tạo.

---

## 20. Xác thực ngắn hạn và cloud workload identity

Một số môi trường hỗ trợ IAM/database tokens hoặc federated/workload identity thay vì static password dài hạn.

Lợi ích tiềm năng:

- Không lưu long-lived password trong application config.
- Có TTL ngắn.
- Quyền cấp token dựa trên identity của workload.
- Audit tốt hơn.
- Thu hồi qua IAM policy/session controls.

Nhưng có yêu cầu riêng:

- Token expiry và refresh.
- Database/JDBC driver compatibility.
- Kết nối mới phải dùng token còn hiệu lực.
- Pool integration.
- Thời gian clock skew và auth service availability.
- Recovery khi token issuer tạm thời không sẵn sàng.

### 20.1. Token ngắn hạn vẫn là secret

Một token bị lộ trong thời gian hiệu lực vẫn có thể bị sử dụng trái phép. Không log token hoặc đưa vào metrics labels.

### 20.2. Kết nối đang mở và token hết hạn

Nhiều hệ thống dùng token để **xác thực khi tạo connection**, không kiểm tra token trên từng SQL statement; behavior tùy DB/provider. Khi token hết hạn, một connection đang mở có thể tiếp tục tồn tại, nhưng kết nối mới cần token mới.

Không suy rằng “token 15 phút” sẽ làm mọi DB session tự bị đóng sau 15 phút trong mọi môi trường.

### 20.3. Không nhúng cloud key tĩnh nếu có workload identity phù hợp

Nếu nền tảng hỗ trợ identity gắn với deployment workload, tránh tạo thêm static cloud access keys được commit hoặc đặt dài hạn trong container.

---

## 21. Pool sizing cũng là bảo mật availability

Một ứng dụng có thể vô tình tự làm cạn database bằng quá nhiều connections.

Ví dụ:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
```

Nếu có 20 app instances, giới hạn lý thuyết có thể tới khoảng:

```text
20 instances × 20 connections = 400 connections
```

chưa kể jobs/admin tools và các pools khác.

### 21.1. Không tự đặt pool thật lớn

Quá nhiều connections có thể tăng contention, memory usage hoặc vượt DB max connections, dẫn đến outage.

Cần tính:

- Số replicas tối đa.
- Tổng số pools trên mỗi replica.
- DB max connections.
- Concurrency thực tế.
- Query duration/transaction duration.
- Connection acquisition latency.
- Backpressure/retry behavior.

### 21.2. Connection leak làm giảm availability

Nếu application-managed JDBC connections không được đóng đúng hoặc transactions giữ connection quá lâu, pool có thể cạn. Với Spring/JPA framework-managed context, cần theo đúng lifecycle của transaction manager.

### 21.3. Retry bừa bãi sau lỗi authentication

Nếu password sai, retry mở connection hàng trăm lần mỗi giây thường không giúp và có thể kích hoạt account lockout hoặc gây tải.

Phân biệt **lỗi cấu hình/credentials** với transient network/database outage.

---

# Phần VI — Ghi log, giám sát và điều tra

## 22. Hibernate SQL logs khác database credential logs

Hibernate có thể log SQL text và bind values khi debug:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Bind TRACE thường liên quan **dữ liệu truy vấn** như email, address, tokens hoặc thông tin khách hàng — không nhất thiết là DB password.

Tuy nhiên, các thư viện có thể log JDBC URL, connection properties hoặc authentication diagnostics ở mức debug. Cần quản lý cả hai nhóm rò rỉ.

### 22.1. Không in Config hoặc DataSource object tùy tiện

```java
log.info("DataSource config {}", config);
```

có thể không an toàn nếu `toString`/serializer expose secrets.

### 22.2. Không trả raw exception cho client

Sai:

```java
return ResponseEntity.status(500)
    .body(exception.toString());
```

Một exception có thể chứa endpoint, username, SQL và driver details. API nên trả error code an toàn:

```json
{
  "code": "DATABASE_UNAVAILABLE",
  "message": "Service is temporarily unavailable"
}
```

Thông tin kỹ thuật nằm ở log nội bộ có access controls, đã được redact.

### 22.3. Không đưa DB password vào structured context

MDC, tracing baggage, metric tags và audit events đôi khi được chuyển tới hệ thống ngoài. Không gắn secrets vào đó.

### 22.4. Secrets có thể lọt qua screenshots và support bundles

Khi thu thập diagnostics, bảo đảm secret redaction áp dụng cho:

- Config dumps.
- Environment snapshots.
- Support archives.
- Thread/heap dumps.
- IDE debugging snapshots.
- Kubernetes pod describe/logs.
- Pipeline execution reports.

---

## 23. Actuator và các endpoint chẩn đoán

Một ứng dụng Spring Boot có thể dùng Actuator cho health và metrics. Các endpoint như environment/configprops có thể chứa metadata nhạy cảm hoặc cho thấy phần cấu hình đã được mask tùy version/setting.

**Không nên công khai các endpoint cấu hình/diagnostic tới người dùng Internet** chỉ vì framework mặc định mask một số keys.

Cần:

- Chỉ expose endpoints cần thiết.
- Authentication/authorization.
- Network restrictions.
- Mask/redact secrets.
- Kiểm tra hành vi theo Spring Boot version.
- Không gắn password, token hoặc JDBC URL có secrets vào metrics.

### 23.1. Health check cần tiết lộ tối thiểu

Một health endpoint public có thể chỉ trả:

```json
{"status":"UP"}
```

Khi database không sẵn sàng, endpoint nội bộ có thể cung cấp status phục vụ orchestration, nhưng không trả username/password/hostname topology không cần thiết cho mọi caller.

### 23.2. Readiness khác liveness

Nếu DB credential hết hạn hoặc DB không kết nối được, readiness có thể cần thất bại để tạm dừng nhận traffic. Liveness không nên restart vô hạn chỉ vì DB outage tạm thời nếu điều đó làm tình hình xấu hơn.

Chính sách phải dựa trên kiến trúc deployment, không dùng một câu trả lời chung cho mọi service.

---

## 24. Phân loại lỗi authentication và TLS

Các lỗi thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Authentication failed | Sai password/token, user bị thu hồi | Secret version, DB role |
| Connection refused | Host/port/network/service không sẵn sàng | Network, firewall, listener |
| Unknown host | DNS/config sai | Endpoint, resolver |
| Certificate verify failed | CA/cert/hostname không phù hợp | Truststore, SAN, hostname |
| Connection timeout | Network block, DB quá tải | Route, firewall, DB health |
| Pool exhausted | Leaked/slow transactions, pool quá nhỏ | Pool metrics/transactions |
| Permission denied | Runtime role thiếu SQL privilege | Grants, role, schema |
| Migration errors | Runtime role bị dùng làm migration | Tách identities |
| Auth failures sau rotation | Pool dùng secret cũ | Pool lifecycle/restart |
| Lỗi khi commit | Network mất hoặc DB failure | Transaction outcome, idempotency |

### 24.1. PostgreSQL SQLSTATE tham khảo

Một số mã có thể gặp:

- `28P01`: invalid_password.
- `28000`: invalid_authorization_specification.
- SQLSTATE class `08`: nhóm connection exceptions.
- `42501`: insufficient_privilege.
- `3D000`: invalid_catalog_name (ví dụ database không tồn tại).

Các mã này **theo PostgreSQL**, không phải hợp đồng của tất cả JDBC drivers.

### 24.2. Authentication failure thường không phải transient query error

Nếu credential bị revoke, retry cùng password không giúp. Cần điều tra secret rotation/configuration; hạn chế retry để tránh lockout và alert fatigue.

### 24.3. TLS verify failure không nên tự bật chế độ insecure

Sai phản ứng:

> “Certificate không khớp, hãy tắt hostname verification để app lên lại.”

Phải sửa DNS, trust chain, SAN hoặc certificate lifecycle. Chuyển sang `trustServerCertificate=true`/`sslmode` yếu có thể tạo đường MITM mới.

---

## 25. Monitoring mà không lộ dữ liệu

Nên đo:

- Pool active/idle/pending connections.
- Connection acquisition time.
- Connection timeouts.
- Authentication failures theo loại.
- TLS handshake failures.
- DB unavailable events.
- Secret rotation age/success status.
- Unauthorized secret access attempts.
- Migration permission failures.
- DB query latency và error rates.
- Số sessions vượt ngưỡng.
- Readiness failure duration.

Ví dụ labels an toàn hơn:

```text
service=shop-api
environment=prod
database_role=runtime
failure_type=authentication
```

Không dùng:

```text
database_password=...
full_jdbc_url_with_password=...
access_token=...
```

### 25.1. Không dùng username làm metric label nếu không cần

Trong một số tổ chức, DB username cũng là một thông tin nhạy cảm của hệ thống. Dùng role category (`runtime`, `migration`, `readonly`) có thể đủ cho observability.

### 25.2. Cardinality của metrics

Không gắn request IDs, raw JDBC URLs hoặc exception messages làm high-cardinality labels. Điều này vừa làm lộ thông tin vừa tăng chi phí metrics.

---

# Phần VII — Rotation, revocation và incident response

## 26. Credential rotation theo kế hoạch

Mục tiêu là đổi secret mà không để ứng dụng tiếp tục dùng secret cũ hoặc gặp downtime ngoài ý muốn.

### 26.1. Trình tự tổng quát

1. Inventory những services/jobs dùng credential.
2. Xác định DB role/privileges hiện tại.
3. Chuẩn bị credential mới (password/token/identity) theo policy.
4. Đảm bảo database chấp nhận credential mới.
5. Cập nhật secret manager/version.
6. Rollout/reconfigure application và pool.
7. Kiểm tra **kết nối mới** thành công.
8. Quan sát authentication failures/latency.
9. Revoke credential cũ.
10. Xác nhận không còn service phụ thuộc secret cũ.
11. Cập nhật audit/change record.

Thứ tự chi tiết phụ thuộc authentication method: một số DB chỉ có một password cho một user, một số hỗ trợ overlap/dual roles/tokens.

### 26.2. Dual-identity rotation

Một giải pháp khi DB không hỗ trợ song song hai password của cùng identity:

```text
shop_runtime_a (đang dùng)
shop_runtime_b (credential mới, quyền tương đương cần thiết)
```

Quy trình:

```text
Provision role B
  -> grant quyền tối thiểu như A
  -> rollout app dùng B
  -> verify new connections/workload
  -> revoke/drop role A sau khi an toàn
```

Cần kiểm tra object ownership, grants, RLS policies, default privileges và auditing; không mặc định đổi username là xong.

### 26.3. Khả năng quay lại phiên bản cũ

Nếu rollout lỗi, cần kế hoạch rollback có kiểm soát. Nhưng không nên phục hồi một credential **đã được xác nhận bị lộ** chỉ để rollback nhanh.

Sự cố bảo mật cần ưu tiên credential mới an toàn và khôi phục service đúng cách.

### 26.4. Service account và batch job bị quên

Một credential có thể được dùng trong:

- API service.
- Background worker.
- Scheduler.
- Migration job.
- Reporting job.
- DBA automation.
- Disaster recovery job.

Rotation sẽ thất bại nếu inventory thiếu consumers.

---

## 27. Khi nghi ngờ secret bị lộ

Không chỉ xóa dòng chứa secret rồi đóng issue.

Quy trình ứng phó:

1. **Phân loại mức độ**: secret nào, môi trường nào, quyền gì, có thể truy cập từ đâu.
2. **Giới hạn phơi nhiễm**: đóng lỗ hổng hoặc vô hiệu hóa đường phát tán.
3. **Revoke/rotate credential** theo mức khẩn cấp.
4. **Kiểm tra phiên đang hoạt động**, terminate nếu threat model đòi hỏi.
5. **Audit DB access/queries** trong cửa sổ nghi ngờ.
6. **Xem xét dữ liệu có thể bị đọc/sửa/xóa** theo DB privileges.
7. **Xử lý Git history/artifacts/logs** theo quy trình phù hợp.
8. **Cập nhật secrets** cho mọi consumers.
9. **Thông báo và lập hồ sơ incident** theo chính sách tổ chức/quy định áp dụng.
10. **Ngăn tái diễn** bằng secret scanning, least privilege, access controls.

### 27.1. Git history có tính lan truyền

Force-push xóa commit không bảo đảm mọi clone, fork, artifact, review cache đã mất bản copy. Rotation/revocation mới là biện pháp cốt lõi khi credential thực đã lộ.

### 27.2. Không gửi secret cho AI/chat/support ticket

Khi nhờ debug, thay bằng placeholder hoặc redacted URL:

```text
jdbc:postgresql://<host>:5432/<database>
username=<redacted>
password=<redacted>
```

Chỉ chia sẻ loại lỗi, driver/provider version, sanitized config và các thông tin đủ để điều tra.

---

## 28. Backup, restore và disaster recovery

Credential và secret-management system cũng là một phần của kế hoạch phục hồi:

- Backup database được bảo vệ riêng.
- Backup encryption key quản lý đúng.
- DB restore environment không dùng nhầm production secrets.
- Quyền truy cập backup có audit.
- Test restore với identity và network policy phù hợp.
- Khi restore sang môi trường khác, tránh phát lại jobs/emails/batch effects ngoài ý muốn.
- Không để secrets tồn tại vĩnh viễn trong backup mà không có rotation strategy.

### 28.1. DB backup không chỉ là dữ liệu vô hại

Backup có thể chứa toàn bộ dữ liệu khách hàng, bảng token hoặc hashed credentials của ứng dụng. Bảo vệ backup độc lập với DB password.

### 28.2. Restore không được mang theo quyền quá mức

Một restore dump có thể chứa roles, grants, schema ownership hoặc security settings tùy cách export. Cần kiểm tra privileges và endpoint sau restore.

---

# Phần VIII — Kiểm thử cấu hình và thực hành

## 29. Test cấu hình không có secret hard-coded

Một pipeline có thể dùng:

- Secret scanning trước merge.
- Repository history scanning khi có rủi ro.
- Configuration linting.
- Artifact/image inspection.
- Policy checks cho env/secrets.
- Review những thay đổi ở `application.yml`, `persistence.xml` và CI workflows.

### 29.1. Không coi regex đơn giản là đủ

Một scanner có thể có false positives và false negatives. Cần duy trì patterns, allowlist các test placeholders và quy trình xử lý findings.

### 29.2. Test không in secret

Khi kiểm tra Spring Environment hoặc DataSource:

```java
assertNotNull(
    environment.getProperty(
        "spring.datasource.password"
    )
);
```

Test dạng này chỉ xác nhận property được cung cấp, **không chứng minh secret được bảo vệ**. Không in property value vào assertion message.

Tốt hơn là test integration chứng minh kết nối thành công bằng test credentials tách biệt và secret không xuất hiện trong captured logs.

### 29.3. Không tạo test bằng production password

Kể cả CI có access production secret, không vì tiện mà dùng nó trong test. Hãy cấp database test độc lập.

---

## 30. Integration test quyền runtime role

Giả sử runtime app chỉ cần SELECT/INSERT/UPDATE trên schema ứng dụng.

Các test có thể kiểm chứng:

- SELECT hợp lệ.
- INSERT hợp lệ.
- UPDATE hợp lệ.
- Không thể CREATE/DROP TABLE nếu không được cấp quyền.
- Không thể đọc schema nhạy cảm khác.
- Không thể thay quyền DB users.
- Không thể bypass tenant policies nếu có RLS.
- Application vẫn chạy khi migration user không hiện diện trong runtime.

### 30.1. Tách môi trường kiểm thử

Không thử `DROP TABLE` vào production để chứng minh runtime role không có quyền. Test trong isolated database được dựng theo migration/grants thực tế.

### 30.2. Kiểm tra bằng role thực

Nếu integration test chạy bằng superuser, nó không chứng minh runtime role đã được cấp quyền tối thiểu. Hãy chạy test dưới **chính loại DB role** mà production service sử dụng.

### 30.3. Kiểm tra mặc định khi thiếu quyền

Một ứng dụng fail vì thiếu quyền cần thiết nên cung cấp log nội bộ đủ điều tra, nhưng không tự yêu cầu GRANT ALL làm giải pháp.

---

## 31. Integration test TLS và endpoint identity

Một tập tests có thể bao gồm:

1. Kết nối tới DB server hợp lệ với trusted CA và đúng hostname → thành công.
2. Server certificate không trusted → kết nối bị từ chối.
3. Certificate hostname không khớp → kết nối bị từ chối trong chế độ identity-verifying.
4. TLS bị vô hiệu hóa ở server/client trái policy → kết nối bị từ chối.
5. Certificate rotation có trust overlap → kết nối mới tiếp tục thành công.
6. Sau khi gỡ old trust/cert → old endpoint/cert không còn được chấp nhận.

### 31.1. Test đúng JDBC driver

Không suy từ kết quả pgJDBC rằng MySQL Connector/J hay SQL Server JDBC driver có cấu hình y hệt.

### 31.2. Không “fix test” bằng cách tắt validation

Nếu hostname mismatch test fail theo nghĩa kết nối vẫn thành công, cần điều tra trust policy thay vì thay `verify-full` thành `require` hoặc `trustServerCertificate=true`.

---

## 32. Test rotation với connection pool

Một test quy trình rotation:

```text
A. App pool dùng credential A
B. Verify query thành công
C. Cấp credential B/role B
D. Cập nhật secret source
E. Refresh/redeploy pool dùng B
F. Buộc tạo JDBC connection mới
G. Verify query thành công bằng B
H. Revoke A
I. Verify new connections không còn dùng A
J. Quan sát lỗi/pool counters
```

Nếu muốn zero-downtime, test thêm request liên tục trong thời gian rolling deployment.

### 32.1. Test active connection sau revoke

Có thể DB vẫn cho connection cũ tiếp tục chạy. Nếu chính sách yêu cầu thu hồi tức thì khi credential compromised, cần thêm bước terminate sessions hoặc account disable phù hợp.

### 32.2. Test retry policy

Authentication failure vì password sai thường không nên trigger retry vô hạn. Database unavailable có thể có retry giới hạn, backoff và readiness phù hợp.

### 32.3. Test logs sau failure

Capture logs khi intentionally invalid password/TLS error và kiểm tra **không có secret value**; vẫn nên có error category/correlation ID giúp vận hành.

---

## 33. Test data-source config drift

Một production incident có thể bắt nguồn từ việc app dùng nhầm database:

```text
app=shop-api-prod
JDBC URL=staging-db
```

Không nhất thiết là credential leak, nhưng có thể vi phạm isolation hoặc ghi dữ liệu sai.

Có thể áp dụng:

- Environment identity labeling.
- Database connection tags/application name.
- Migrations/version checks.
- Trusted endpoint allowlists.
- Deployment policy constraints.
- TLS hostname verification.
- Startup assertion trên **non-secret database identity metadata** khi phù hợp.

**Không** làm startup assertion bằng cách in full JDBC URL/password vào log.

---

# Phần IX — Những sai lầm thường gặp

## 34. “Mật khẩu đặt trong application.properties là đủ vì repository private”

Không đúng. Private repository vẫn có clones, pipeline, reviewer, build artifacts, backups và nguy cơ credential tồn tại trong lịch sử.

## 35. “Environment variable là bí mật tuyệt đối”

Không đúng. Nó có thể bị đọc bởi process có quyền, diagnostics hoặc logs; cần host/pod security và lifecycle controls.

## 36. “Kubernetes Secret base64 nghĩa là đã mã hóa”

Không đúng. Base64 là encoding, không phải encryption. Cần RBAC và encryption at rest phù hợp.

## 37. “Đổi password trong secret manager là pool tự dùng password mới”

Không chắc. Pool có thể giữ config cũ và active connections; cần kiểm thử refresh/rollout.

## 38. “Thu hồi DB password sẽ tự đóng mọi session”

Không mặc định. Session đang mở có thể cần terminate riêng tùy DB/authentication method.

## 39. “Bật TLS là đủ, không cần xác minh hostname”

Không đúng. Kết nối được mã hóa tới server giả vẫn có thể nguy hiểm. Cần xác minh danh tính server.

## 40. “Trong VPC riêng không cần TLS”

Không nên mặc định. Network isolation giảm rủi ro nhưng không thay xác thực/mã hóa kênh khi policy yêu cầu.

## 41. “Runtime app nên dùng cùng user với Flyway để dễ triển khai”

Không nên mặc định. Nó mở rộng quyền DDL cho service runtime; cần tách migration identity khi kiến trúc cho phép.

## 42. “Nếu thấy permission denied, GRANT ALL là xong”

Sai cách tiếp cận. Cần cấp đúng quyền cần thiết, đúng object, đúng role.

## 43. “Mật khẩu không log thì mọi thứ an toàn”

Chưa đủ. Pool, endpoint, TLS, DB role, authorization và session state đều phải được bảo vệ.

## 44. “Giấu tên database khỏi log là cơ chế security chính”

Không đúng. Endpoint metadata có thể nhạy cảm, nhưng identity/authentication, TLS, network và least privilege mới là hàng rào quan trọng.

## 45. “Dùng mã hóa password trong YAML với khóa cũng ở YAML là an toàn”

Không giải quyết bản chất nếu attacker đọc được cả ciphertext và key. Cần một trust boundary và key management độc lập.

## 46. “Chỉ cần xóa secret khỏi commit mới”

Không đủ. Secret thực đã xuất hiện trong history có thể cần revoke/rotate, audit và xử lý artifacts/caches.

## 47. “Health endpoint có thể trả toàn bộ JDBC URL cho tiện debug”

Rủi ro lộ topology và parameters, thậm chí credentials nếu URL chứa secret. Health response nên tối thiểu.

## 48. “Token ngắn hạn không cần bảo vệ”

Sai. Token còn hiệu lực vẫn là credential; phải giới hạn phân phối và không log.

## 49. “Mọi SQL authentication error nên retry nhiều lần”

Sai. Một password sai hoặc user bị disable không thành công chỉ nhờ retry; cần phát hiện config/rotation incident.

---

# Phần X — Bài tập tình huống có lời giải

## 50. Các tình huống

### Bài 1. Password nằm trong `persistence.xml` commit lên Git

**Lời giải:** Không chỉ di chuyển password sang environment/secret manager; nếu là credential thật, đánh giá exposure và rotate/revoke.

### Bài 2. Spring Boot dùng `${DB_PASSWORD}`

**Lời giải:** Đó là cách lấy value từ configuration source, không tự giải quyết permission, rotation và logging. Cần bảo vệ đường cấp secret.

### Bài 3. Fallback `${DB_PASSWORD:changeme}`

**Lời giải:** Tránh default credential; khi thiếu secret production phải fail configuration rõ.

### Bài 4. JDBC URL chứa `password=...`

**Lời giải:** Tách password sang secret binding. URL có thể xuất hiện trong logs và diagnostics.

### Bài 5. Database runtime role là superuser

**Lời giải:** Tạo runtime role least privilege, kiểm tra DML cần thiết, tách migration role và rollout bằng migration/grants đúng.

### Bài 6. Flyway dùng cùng account với API

**Lời giải:** Cân nhắc migration identity và runtime identity riêng để app không giữ DDL privileges.

### Bài 7. SQLSTATE 42501

**Lời giải:** Điều tra object-level privilege theo query, không grant toàn quyền vô điều kiện.

### Bài 8. Environment chứa secret và debug script chạy `printenv`

**Lời giải:** Không xuất toàn bộ môi trường; giới hạn diagnostics và scrub/redact.

### Bài 9. Secret được đặt trong Dockerfile ENV

**Lời giải:** Có thể bị bake vào image metadata/layers. Inject runtime qua platform secret mechanism.

### Bài 10. Git history đã có password nhưng đã xóa khỏi HEAD

**Lời giải:** Credential vẫn có thể đã bị lộ; rotate/revoke và kiểm tra lịch sử/artifacts theo quy trình.

### Bài 11. Kubernetes Secret có field `data` dạng base64

**Lời giải:** Base64 không phải encryption; cần RBAC, etcd encryption và access controls.

### Bài 12. JPA JTA persistence unit có `<jta-data-source>`

**Lời giải:** Cấu hình credential ở container-managed DataSource, không ở source/persistence.xml.

### Bài 13. Application tự `emf.createEntityManager()` RESOURCE_LOCAL

**Lời giải:** Có thể truyền JDBC properties khi tạo factory, nhưng không log map và phải quản lý EMF/EM lifecycle.

### Bài 14. TLS bật với `trustServerCertificate=true`

**Lời giải:** Có thể bỏ kiểm tra server identity. Sửa certificate/truststore và bật verification theo driver.

### Bài 15. pgJDBC `sslmode=require` được xem là verify-full

**Lời giải:** Không mặc định tương đương. Cần chế độ xác minh certificate/hostname phù hợp (ví dụ `verify-full`) và test.

### Bài 16. Database hostname không trùng certificate SAN

**Lời giải:** Sửa DNS/certificate và trust config. Không tắt hostname verification để “cho chạy”.

### Bài 17. Secret manager đã rotate nhưng HikariCP mở connection vẫn bằng password cũ

**Lời giải:** Pool giữ credentials/config cũ. Cần refresh/redeployment hoặc cơ chế integration đã kiểm chứng.

### Bài 18. Đổi password xong ứng dụng vẫn truy vấn được trên connection cũ

**Lời giải:** Active DB session có thể tiếp tục sống. Muốn revoke tức thời có thể cần terminate sessions.

### Bài 19. Cloud DB token ngắn hạn hết hạn

**Lời giải:** New connection phải nhận token mới; kiểm thử refresh path/pool behavior và expiry handling.

### Bài 20. App có 20 replicas, mỗi replica pool max 30

**Lời giải:** Có thể tới khoảng 600 DB connections từ ứng dụng; cần tính budget chung, DB limits, jobs và sizing.

### Bài 21. Authentication failures bị retry liên tục

**Lời giải:** Không retry không giới hạn với password sai. Phân biệt lỗi cấu hình/revocation với transient network.

### Bài 22. Metrics label chứa full JDBC URL có password

**Lời giải:** Coi đây là secret exposure. Redact/delete/rotate tùy mức độ; không đặt secrets vào metric tags.

### Bài 23. Actuator `env` endpoint public

**Lời giải:** Hạn chế exposure/authentication và xác minh redaction theo phiên bản, không dựa hoàn toàn vào masking mặc định.

### Bài 24. Staging và production dùng chung DB user

**Lời giải:** Tách credentials/roles, network, DB resources để tránh truy cập chéo và tăng audit quality.

### Bài 25. Development laptop dùng production password

**Lời giải:** Ngừng dùng chung; cấp dev/test credentials riêng, rotate production secret nếu bị phơi nhiễm.

### Bài 26. Test DB privileges bằng superuser

**Lời giải:** Test không chứng minh runtime role ít quyền. Phải dùng chính runtime role trong môi trường kiểm thử.

### Bài 27. App thiếu quyền tạo bảng khi khởi động

**Lời giải:** Có thể đang dùng ORM schema generation/migration bằng runtime identity. Tách migration flow, không grant DDL mù quáng.

### Bài 28. TLS certificate sắp hết hạn

**Lời giải:** Chuẩn bị trust overlap/certificate rotation, test connections mới và theo dõi handshake failure.

### Bài 29. Logs in cả `HikariConfig` object

**Lời giải:** Không mặc định serializer luôn mask password. Chỉ log non-secret metadata.

### Bài 30. Runtime app có quyền đọc mọi tenants

**Lời giải:** DB role least privilege vẫn có thể rộng ở hàng dữ liệu; cần application authorization/tenant scoping và cân nhắc RLS.

### Bài 31. RLS tenant setting giữ trên pooled connection

**Lời giải:** Session-state leakage qua pool rất nguy hiểm. Dùng transaction-local semantics/reset policy đúng và test cross-tenant request sequencing.

### Bài 32. Password rotation không có inventory consumers

**Lời giải:** Batch jobs, reporting và admin automations có thể ngừng hoạt động; phải inventory trước.

### Bài 33. Commit response bị mất lúc DB token gần hết hạn

**Lời giải:** Không kết luận transaction rollback. Reconcile bằng idempotency/outcome tracking, tách transaction ambiguity khỏi authentication renewal.

### Bài 34. Secret hiện trong support ticket

**Lời giải:** Giới hạn exposure, redact, rotate khi cần và sửa quy trình support/debug.

### Bài 35. CI pull request từ contributor ngoài có quyền đọc production secrets

**Lời giải:** Sai ranh giới tin cậy. Giới hạn secret access theo trusted jobs/branches/environment approvals; dùng test credentials độc lập.

---

## 51. Checklist triển khai nguồn dữ liệu an toàn

### Credentials và cấu hình

1. Không có DB password/token/private key trong Java source, `persistence.xml`, YAML commit hoặc container image?
2. JDBC URL có tách khỏi password và được quản lý theo environment?
3. Có một nguồn cấp secret đáng tin và access policy rõ?
4. Thiếu production secret có làm service fail an toàn thay vì fallback yếu?
5. Có quản lý history Git/build artifacts để tránh rò rỉ không?
6. Local/test/prod credentials có tách biệt?
7. CI untrusted workflows có bị chặn đọc production secrets?
8. Có redaction cho config/exception/metrics/support bundles?
9. Có hạn chế diagnostics/heap dumps chứa secrets?
10. Có audit secret access/changes?

### Database privileges và network

11. Runtime role có least privilege, không dùng superuser?
12. Migration identity có tách runtime identity?
13. Runtime account có tránh quyền DDL/admin không cần thiết?
14. Database endpoint có private network/isolation phù hợp?
15. Có firewall/allowlist cho các workloads được phép kết nối?
16. Có dùng TLS theo security policy?
17. TLS có xác minh server CA và hostname?
18. Certificate/truststore có rotation plan?
19. Có tránh insecure driver switches trong production?
20. Có kiểm soát config changes cho JDBC URL và DNS?

### Pool và vận hành

21. Pool size có tính tổng replicas và DB connection budget?
22. Pool có retry/backoff hợp lý khi DB tạm thời không sẵn sàng?
23. Authentication failure có được xử lý khác transient network failure?
24. Rotation có làm new connections dùng credential mới?
25. Revoke có tính đến active sessions?
26. Token ngắn hạn có refresh và expiry handling?
27. Readiness/liveness có tránh restart loops không cần thiết?
28. Có monitoring auth/TLS/pool failures nhưng không lộ secrets?
29. Có process incident response khi secret bị lộ?
30. Có kiểm thử rotation/rollback deployment?

### Application/JPA correctness

31. JPA provider có dùng DataSource đúng môi trường?
32. JTA/RESOURCE_LOCAL transaction management có phù hợp?
33. Có tránh close container-managed EntityManager thủ công?
34. Native SQL/JPQL có bind values để tránh injection?
35. Application có enforce tenant/ownership policy?
36. Nếu dùng DB RLS, pooled connection session state có được quản lý đúng?
37. Migrations và ORM mappings có nhất quán?
38. Có integration tests trên DB/driver/TLS setup mục tiêu?
39. Có test role permissions dưới runtime account thật?
40. Có test không rò secret khi authentication/TLS failures?

---

## 52. Sơ đồ kiến trúc gợi ý

```text
               Trusted deployment pipeline
                          |
                 Workload identity
                          |
                          v
                Secret manager / IAM
                          |
                  scoped credential
                          |
                          v
   +----------------------------------------------+
   | Application runtime                          |
   |                                              |
   |  Spring/Jakarta configuration                |
   |       |                                      |
   |       v                                      |
   |  JPA EntityManager -> DataSource pool         |
   |                            |                 |
   +----------------------------|-----------------+
                                |
                     TLS + server identity check
                                |
                                v
                     Private DB endpoint
                                |
                                v
                       Runtime DB role
                    (minimum required DML)
                                |
                                v
                    Application database

   Separate migration pipeline
         |
         v
   Migration identity -> controlled DDL
```

Các hàng rào được phân bố theo trách nhiệm:

- **Secret manager/IAM** cấp và quản lý credential.
- **Runtime configuration** cung cấp secret cho đúng workload, không commit vào source.
- **DataSource/JDBC** thiết lập kết nối và TLS.
- **Database role** giới hạn SQL privileges.
- **Network isolation** giới hạn nơi kết nối được phép bắt đầu.
- **JPA/application authorization** xác định thao tác nào và bản ghi nào được phép.
- **Monitoring/audit** phát hiện cấu hình sai, rò rỉ, auth failures và hoạt động bất thường.
- **Rotation/incident response** thu hồi quyền khi credential hết hạn hoặc bị lộ.

---

## 53. Tổng kết

Bảo vệ thông tin xác thực và cấu hình nguồn dữ liệu trong JPA không chỉ là chuyển một dòng `password=...` ra khỏi file cấu hình.

Cần nhớ:

1. **JPA làm việc qua DataSource/JDBC; bảo mật phải bao phủ cả provider, pool, driver, network và DB identity.**
2. **Không hard-code passwords/tokens/private keys** trong source, artifacts, Git history hoặc container image.
3. **Environment variable là kênh cấp cấu hình tiện lợi, không phải secret vault tuyệt đối.**
4. **Secret manager và workload identity** giúp giới hạn phân phối, audit và hỗ trợ rotation.
5. **Runtime DB role cần ít quyền nhất**, tách migration/admin credentials khi phù hợp.
6. **TLS cần xác minh danh tính server**, không chỉ mã hóa traffic rồi bỏ qua certificate/hostname verification.
7. **Kết nối private và firewall policy** bổ sung cho authentication, không thay authentication.
8. **Connection pool có thể giữ secret và sessions cũ**, do đó rotation phải kiểm tra new connections, rollout và revoke.
9. **Expired/invalid credential thường không sửa được bằng retry vô hạn**; cần phân loại authentication, network và TLS failures.
10. **Không lộ secrets qua logs, metrics, diagnostics, support bundles hoặc health endpoints.**
11. **Không dùng production credentials cho local dev, PR CI hoặc integration tests.**
12. **Cấu hình an toàn không thay authorization**: application vẫn phải kiểm tra tenant/owner và bind dữ liệu truy vấn.
13. **Secret bị commit hoặc phát tán phải được xử lý như một security exposure**, không chỉ xóa dòng code.
14. **Kiểm thử security configuration bằng runtime identity, driver, database và TLS setup thực tế**, không chỉ kiểm tra YAML có placeholder.

**Một kết nối database an toàn cần đúng danh tính, đúng quyền, đúng endpoint và đúng vòng đời. Khi credential được quản lý riêng, kết nối được xác thực bằng TLS, quyền DB được giới hạn và rotation được thử nghiệm, ứng dụng JPA mới giảm được thiệt hại từ lỗi cấu hình lẫn các tình huống xâm nhập thực tế.**
